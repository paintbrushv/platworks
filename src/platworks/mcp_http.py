"""Stateless public Streamable HTTP MCP service with a bounded request boundary."""

import argparse
import asyncio
import json
import logging
import os
import sys
import threading
from contextlib import suppress

import anyio
from mcp.server.transport_security import TransportSecuritySettings

from platworks.local_review.common import decode
from platworks.mcp_server import build_server
from platworks.scenarios import MAX_INPUT


class PublicBoundary:
    def __init__(self, app, *, hosts, origins):
        self.app = app
        self.hosts = frozenset(hosts)
        self.origins = frozenset(origins)
        if not self.hosts or any("*" in value or not value for value in self.hosts | self.origins):
            raise ValueError("Configure explicit hosts and origins without wildcards")
        self.slots = threading.BoundedSemaphore(8)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        started = False

        async def reply(status, code):
            body = json.dumps({"status": code}).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": status,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"cache-control", b"no-store"),
                        (b"x-content-type-options", b"nosniff"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})

        async def safe_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                message["headers"] = [
                    (k, v) for k, v in message.get("headers", []) if k.lower() != b"cache-control"
                ] + [(b"cache-control", b"no-store")]
            await send(message)

        headers = {}
        for name, value in scope["headers"]:
            headers.setdefault(name.lower(), []).append(value.decode("latin-1"))
        if (
            len(headers.get(b"host", [])) != 1
            or headers[b"host"][0] not in self.hosts
            or len(headers.get(b"origin", [])) > 1
            or (b"origin" in headers and headers[b"origin"][0] not in self.origins)
        ):
            return await reply(403, "forbidden")
        if scope["path"] == "/healthz" and scope["method"] == "GET":
            return await reply(200, "ready")
        if scope["path"] != "/mcp":
            return await reply(404, "not_found")
        if scope["method"] != "POST":
            return await reply(405, "use_post")
        if (
            len(headers.get(b"content-type", [])) != 1
            or headers[b"content-type"][0].split(";")[0].strip().lower() != "application/json"
            or b"content-encoding" in headers
        ):
            return await reply(415, "json_required")
        lengths = headers.get(b"content-length", [])
        if len(lengths) > 1 or (
            lengths
            and (not lengths[0].isdigit() or len(lengths[0]) > 10 or int(lengths[0]) > MAX_INPUT)
        ):
            return await reply(413, "input_limit")
        if not self.slots.acquire(blocking=False):
            return await reply(503, "busy")
        try:

            async def read_body():
                body = bytearray()
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        raise ConnectionError()
                    body.extend(message.get("body", b""))
                    if len(body) > MAX_INPUT:
                        raise OverflowError()
                    if not message.get("more_body", False):
                        break
                request = decode(bytes(body))
                # JSON-RPC batches and path/data-bearing envelope extensions aren't needed.
                if not isinstance(request, dict):
                    raise ValueError()
                return bytes(body)

            try:
                body = await asyncio.wait_for(read_body(), timeout=10)
            except TimeoutError:
                return await reply(408, "request_timeout")
            except OverflowError:
                return await reply(413, "input_limit")
            except ConnectionError:
                return
            except Exception:
                return await reply(400, "invalid_json")
            delivered = False
            disconnected = asyncio.Event()

            async def watch_disconnect():
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        disconnected.set()
                        return

            async def replay():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": body, "more_body": False}
                await disconnected.wait()
                return {"type": "http.disconnect"}

            # JSON responses otherwise wait for the entire calculation without
            # observing a closed socket. Terminating the per-request SDK transport
            # cancels its dispatcher and the financial worker promptly.
            request_task = asyncio.create_task(self.app(scope, replay, safe_send))
            disconnect_task = asyncio.create_task(watch_disconnect())
            try:
                done, _ = await asyncio.wait(
                    {request_task, disconnect_task}, return_when=asyncio.FIRST_COMPLETED
                )
                if disconnect_task in done and disconnected.is_set():
                    request_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await request_task
                else:
                    await request_task
            except Exception:
                if not started and not disconnected.is_set():
                    await reply(500, "request_failed")
            finally:
                request_task.cancel()
                disconnect_task.cancel()
                with anyio.CancelScope(shield=True):
                    await asyncio.gather(request_task, disconnect_task, return_exceptions=True)
        finally:
            self.slots.release()


def create_app(*, hosts, origins=()):
    server = build_server(profile="public")
    app = server.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
        max_request_body_size=MAX_INPUT,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=list(hosts),
            allowed_origins=list(origins),
        ),
    )
    return PublicBoundary(app, hosts=hosts, origins=origins)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--allowed-host", action="append")
    parser.add_argument("--allowed-origin", action="append", default=[])
    args = parser.parse_args()
    hosts = args.allowed_host or [f"127.0.0.1:{args.port}", f"localhost:{args.port}"]
    if os.environ.get("PLATWORKS_ALLOWED_HOSTS"):
        hosts = os.environ["PLATWORKS_ALLOWED_HOSTS"].split(",")
    origins = args.allowed_origin
    if os.environ.get("PLATWORKS_ALLOWED_ORIGINS"):
        origins = os.environ["PLATWORKS_ALLOWED_ORIGINS"].split(",")
    # SDK validation errors can contain supplied values. The standalone public
    # process deliberately emits no request, result, exception or access logs.
    logging.disable(sys.maxsize)
    import uvicorn

    uvicorn.run(
        create_app(hosts=hosts, origins=origins),
        host=args.host,
        port=args.port,
        workers=1,
        access_log=False,
        log_config=None,
        proxy_headers=False,
        server_header=False,
        limit_concurrency=32,
        timeout_keep_alive=5,
    )


if __name__ == "__main__":
    main()
