"""Synthetic installed-package MCP checks; does not establish assistant-host acceptance."""

import argparse
import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path

import httpx2
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

from platworks.library import sha256
from platworks.library_tools import synthetic_example


@contextmanager
def local_http():
    with socket.socket() as available:
        available.bind(("127.0.0.1", 0))
        port = available.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix="plat-http-check-") as folder:
        root = Path(folder)
        log = root / "service.log"
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("PLAT", "PYTHON", "OTEL"))
        }
        env.update(TMPDIR=folder, TEMP=folder, TMP=folder)
        with log.open("wb") as output:
            process = subprocess.Popen(
                [sys.executable, "-I", "-B", "-m", "platworks.mcp_http", "--port", str(port)],
                cwd=folder,
                env=env,
                stdout=output,
                stderr=output,
            )
        url = f"http://127.0.0.1:{port}"
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError("Public MCP process exited during startup")
                try:
                    with opener.open(url + "/healthz", timeout=0.5) as response:
                        if response.status == 200:
                            break
                except (OSError, urllib.error.URLError):
                    time.sleep(0.1)
            else:
                raise RuntimeError("Public MCP health check timed out")
            yield url, root, log
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


async def exercise(client, *, analysis):
    await client.initialize()
    tools = {tool.name: tool for tool in (await client.list_tools()).tools}

    async def call(name, arguments):
        response = await client.call_tool(name, arguments)
        assert not response.is_error
        return json.loads(response.content[0].text)

    search = await call("search_library", {"query": "DSCR debt coverage"})
    assert search["results"][0]["id"] == "mf.debt"
    reference = await call("get_reference", {"reference_id": "mf.debt", "version": "1.0.0"})
    assert reference["reference_sha256"] == sha256(reference["reference"])
    example = await call("get_synthetic_example", {"kind": "operations"})
    assert example["data_class"] == "synthetic"
    scenario = await call("preview_operations", {"inputs": example["inputs"]})
    if analysis:
        assert scenario["variance"]["noi_bridge"]["noi_variance"] == "0.01"
        assert scenario["human_approval"] == "not_granted"
        assert scenario["scenario"]["certified"] is False
        assert scenario["scenario"]["input_status"] == "unverified_scenario"
        body = dict(scenario)
        proof = body.pop("scenario")
        assert proof["result_sha256"] == sha256(body)
        assert proof["input_sha256"] == sha256(
            {
                "tool": "preview_operations",
                "arguments": proof["supplied_arguments"],
            }
        )
        assert proof["supplied_arguments"]["inputs"] == example["inputs"]
        acquisition = await call(
            "underwrite_run",
            {
                "inputs": synthetic_example("acquisition")["inputs"],
            },
        )
        assert acquisition["metrics"]["noi"]["year_1_noi"] == 1050154.8
        assert acquisition["scenario"]["human_approval"] == "not_granted"
    else:
        assert scenario["error"]["code"] == "BACKEND_UNAVAILABLE"
    assert (await call("underwrite_run", {"inputs": {}, "db_path": "private-canary"}))["error"][
        "code"
    ] == "INVALID_INPUT"
    return {name: tool.input_schema for name, tool in tools.items()}


async def verify_stdio(analysis):
    async with stdio_client(
        StdioServerParameters(
            command=sys.executable,
            args=["-I", "-B", "-m", "platworks.mcp_server"],
        )
    ) as (read, write):
        async with ClientSession(read, write) as client:
            return await exercise(client, analysis=analysis)


async def verify_http(url, analysis):
    async with httpx2.AsyncClient(trust_env=False, timeout=90) as http:
        async with streamable_http_client(url + "/mcp", http_client=http) as (read, write):
            async with ClientSession(read, write) as client:
                schemas = await exercise(client, analysis=analysis)
                assert "ops_review" not in schemas and "read_local_source" not in schemas
                response = await client.call_tool("ops_review", {"db_path": "private-canary"})
                assert json.loads(response.content[0].text)["error"]["code"] == "UNKNOWN_TOOL"
                return schemas


def verify(*, analysis=False, endpoint=None):
    if not __debug__:
        raise RuntimeError("Run acceptance checks without Python optimization")
    local = asyncio.run(verify_stdio(analysis))
    if endpoint:
        public = asyncio.run(verify_http(endpoint.rstrip("/"), analysis))
        quiet = None
    else:
        with local_http() as (url, root, log):
            public = asyncio.run(verify_http(url, analysis))
            assert not list(root.glob("plat-scenario-*")), "Scenario files retained"
            assert log.read_bytes() == b"", "Service emitted logs"
            quiet = True
    assert len(local) == 25 and len(public) == 22
    assert all(local[name] == schema for name, schema in public.items())
    return {
        "status": "passed",
        "profile": "analysis" if analysis else "catalog",
        "local_tools": len(local),
        "public_tools": len(public),
        "common_schema_parity": True,
        "library_version": "1.0.0",
        "transports": ["stdio", "streamable-http"],
        "synthetic_only": True,
        "private_logs_and_retained_files_absent": quiet,
        "assistant_host_acceptance": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", action="store_true")
    parser.add_argument("--endpoint", help="Existing HTTP service base URL for a container probe")
    args = parser.parse_args()
    print(json.dumps(verify(analysis=args.analysis, endpoint=args.endpoint), indent=2))


if __name__ == "__main__":
    main()
