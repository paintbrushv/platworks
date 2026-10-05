"""Actual transport, privacy, concurrency and subprocess lifecycle acceptance."""

import asyncio
import json
import os
import sys

import pytest

from platworks.library_tools import synthetic_example
from platworks.mcp_http import create_app
from platworks.scenarios import MAX_INPUT, ScenarioExecutor, calculate, validate_request
from platworks.verify_integrations import verify


def test_real_stdio_and_http_profiles_and_calculations():
    result = verify(analysis=True)
    assert result["common_schema_parity"]
    assert result["private_logs_and_retained_files_absent"]
    assert result["assistant_host_acceptance"] is False


def test_preview_coverage_precision_and_source_conflicts():
    inputs = synthetic_example("operations")["inputs"]
    inputs["budgets"] = []
    result = calculate("preview_operations", {"inputs": inputs})
    assert result["status"] != "calculated"
    assert result["human_approval"] == "not_granted"
    inputs = synthetic_example("operations")["inputs"]
    inputs["actuals"][0]["amount"] = "0.301"
    assert "error" in calculate("preview_operations", {"inputs": inputs})
    inputs["actuals"][0]["category"] = "unknown-canary"
    result = calculate("preview_operations", {"inputs": inputs})
    assert result["error"]["code"] == "INVALID_MAPPING"
    assert "canary" not in json.dumps(result)


def test_scenario_limits():
    for args in (
        {"inputs": {}, "db_path": "/tmp/db"},
        {"inputs": float("nan")},
        {"inputs": {"x": "x" * 16001}},
        {"inputs": [[[]]] * 10001},
    ):
        with pytest.raises((ValueError, TypeError)):
            validate_request("underwrite_run", args)
    inputs = synthetic_example("acquisition")["inputs"]
    inputs["time_grid"]["analysis_end_date"] = "9999-12"
    with pytest.raises(ValueError, match="INPUT_LIMIT"):
        validate_request("underwrite_run", {"inputs": inputs})


def test_worker_saturation_timeout_and_cancellation(tmp_path, monkeypatch):
    from platworks import scenarios

    original = asyncio.create_subprocess_exec
    pidfile = tmp_path / "children.txt"
    # A real controlled child tree replaces only the producer command. The
    # production pipe draining, process group, cancellation and slot code run.
    program = (
        "import subprocess,sys,time,os; "
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); "
        f"open({str(pidfile)!r},'a').write(str(os.getpid())+','+str(child.pid)+'\\n'); "
        "time.sleep(30)"
    )

    async def spawn(*args, **kwargs):
        return await original(sys.executable, "-c", program, **kwargs)

    monkeypatch.setattr(scenarios.asyncio, "create_subprocess_exec", spawn)

    async def run():
        executor = ScenarioExecutor(timeout=0.7)
        tasks = [
            asyncio.create_task(executor.call("underwrite_run", {"inputs": {}})) for _ in range(2)
        ]
        for _ in range(100):
            if pidfile.exists() and len(pidfile.read_text().splitlines()) == 2:
                break
            await asyncio.sleep(0.005)
        else:
            pytest.fail("Controlled workers did not start")
        busy = await executor.call("underwrite_run", {"inputs": {}})
        assert busy["error"]["code"] == "BUSY"
        tasks[0].cancel()
        with pytest.raises(asyncio.CancelledError):
            await tasks[0]
        assert (await tasks[1])["error"]["code"] == "TIMEOUT"
        assert executor.slots.acquire(False) and executor.slots.acquire(False)

    asyncio.run(run())
    if os.name != "nt":
        import time
        from pathlib import Path

        for line in pidfile.read_text().splitlines():
            for pid in line.split(","):
                status = Path("/proc") / pid / "stat"
                # SIGKILL delivery and reaping occur asynchronously in the kernel.
                # Wait for termination, never merely assume the signal succeeded.
                deadline = time.monotonic() + 2
                while status.exists():
                    try:
                        if status.read_text().split()[2] == "Z":
                            break
                    except FileNotFoundError:
                        break
                    assert time.monotonic() < deadline, "Descendant survived termination"
                    time.sleep(0.01)


def test_worker_output_bound(monkeypatch):
    from platworks import scenarios

    original = asyncio.create_subprocess_exec

    async def spawn(*args, **kwargs):
        return await original(sys.executable, "-c", "print('x' * 200000)", **kwargs)

    monkeypatch.setattr(scenarios.asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setattr(scenarios, "MAX_OUTPUT", 100000)
    result = asyncio.run(ScenarioExecutor().call("underwrite_run", {"inputs": {}}))
    assert result["error"]["code"] == "OUTPUT_LIMIT"


async def boundary_request(headers, chunks, *, path="/mcp", method="POST"):
    app = create_app(hosts=["test.local"], origins=["https://chat.example"])
    sent = []
    messages = iter(
        [
            {"type": "http.request", "body": body, "more_body": i < len(chunks) - 1}
            for i, body in enumerate(chunks)
        ]
    )

    async def receive():
        return next(messages)

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "path": path, "method": method, "headers": headers}
    await app(scope, receive, send)
    return sent[0]["status"], b"".join(m.get("body", b"") for m in sent)


@pytest.mark.parametrize(
    ("headers", "chunks", "expected"),
    [
        ([(b"host", b"evil-canary")], [b"{}"], 403),
        ([(b"host", b"test.local"), (b"host", b"test.local")], [b"{}"], 403),
        ([(b"host", b"test.local"), (b"origin", b"http://evil")], [b"{}"], 403),
        ([(b"host", b"test.local"), (b"content-type", b"text/plain")], [b"{}"], 415),
        (
            [(b"host", b"test.local"), (b"content-type", b"application/json")],
            [b"x" * MAX_INPUT, b"x"],
            413,
        ),
        (
            [(b"host", b"test.local"), (b"content-type", b"application/json")],
            [b'{"secret-canary":NaN}'],
            400,
        ),
        (
            [(b"host", b"test.local"), (b"content-type", b"application/json")],
            [b'{"a":1,"a":2}'],
            400,
        ),
    ],
)
def test_http_boundary_before_protocol(headers, chunks, expected, caplog):
    status, body = asyncio.run(boundary_request(headers, chunks))
    assert status == expected
    assert b"canary" not in body
    assert "canary" not in caplog.text


def test_mcp_rejects_coercion_and_undeclared_arguments():
    from platworks.mcp_server import build_server

    async def run():
        server = build_server(profile="public")
        for name, arguments in (
            ("search_library", {"query": "NOI", "limit": True}),
            ("underwrite_backsolve", {"inputs": {}, "target_coc_pct": True}),
            ("renovation_roi", {"total_cost_high": "1000"}),
            ("get_reference", {"reference_id": "mf.noi", "path": "secret-canary"}),
        ):
            result = await server.call_tool(name, arguments)
            payload = json.loads(result.content[0].text)
            assert payload["error"]["code"] == "INVALID_INPUT"
            assert "canary" not in json.dumps(payload)

    asyncio.run(run())


def test_http_disconnect_cancels_sdk_dispatcher_and_worker(tmp_path, monkeypatch):
    from platworks import scenarios

    original = asyncio.create_subprocess_exec
    pidfile = tmp_path / "disconnected-worker.txt"
    program = f"import os,time; open({str(pidfile)!r},'w').write(str(os.getpid())); time.sleep(30)"

    async def spawn(*args, **kwargs):
        return await original(sys.executable, "-c", program, **kwargs)

    monkeypatch.setattr(scenarios.asyncio, "create_subprocess_exec", spawn)

    async def run():
        app = create_app(hosts=["test.local"])
        raw = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "underwrite_run", "arguments": {"inputs": {}}},
            }
        ).encode()
        delivered = False

        async def receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": raw, "more_body": False}
            while not pidfile.exists():
                await asyncio.sleep(0.01)
            return {"type": "http.disconnect"}

        async def send(message):
            pass

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/mcp",
            "raw_path": b"/mcp",
            "query_string": b"",
            "root_path": "",
            "server": ("test.local", 80),
            "client": ("127.0.0.1", 12345),
            "headers": [
                (b"host", b"test.local"),
                (b"content-type", b"application/json"),
                (b"accept", b"application/json, text/event-stream"),
            ],
        }
        async with app.app.router.lifespan_context(app.app):
            await asyncio.wait_for(app(scope, receive, send), timeout=3)
            # The SDK starts the per-request dispatcher in its lifespan task
            # group. It must finish after the transport closes, while the server
            # remains live; shutdown must not be what kills the worker.
            for _ in range(100):
                try:
                    os.kill(int(pidfile.read_text()), 0)
                except ProcessLookupError:
                    break
                await asyncio.sleep(0.01)
            else:
                pytest.fail("Disconnected HTTP request left its worker running")

    asyncio.run(run())
