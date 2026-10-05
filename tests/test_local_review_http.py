"""Real loopback HTTP access controls; no approval routes on the MCP server."""

import http.client
import json
import threading

import pytest

from platworks.local_review.server import create_server


@pytest.fixture
def server(tmp_path):
    server, token = create_server(tmp_path / "review")
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield server, token
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


def request(server, method, path, *, data=None, token=True, origin=True, extra=None):
    httpd, capability = server
    connection = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=5)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + capability
    if origin:
        headers["Origin"] = f"http://127.0.0.1:{httpd.server_port}"
    headers.update(extra or {})
    try:
        connection.request(
            method, path, body=json.dumps(data) if data is not None else None, headers=headers
        )
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def test_private_reads_and_decisions_need_session_capability(server):
    for method, path in [
        ("GET", "/api/state"),
        ("GET", "/api/source?sha=0"),
        ("POST", "/api/issue"),
        ("POST", "/api/execute"),
    ]:
        status, _, raw = request(server, method, path, token=False, data={})
        assert status == 403
        assert json.loads(raw)["error"]["code"] == "LOCAL_SESSION_REQUIRED"


def test_foreign_origin_and_dns_rebinding_host_refuse(server):
    for headers in ({"Origin": "https://untrusted.example"}, {"Host": "attacker.example"}):
        assert request(server, "GET", "/api/state", extra=headers)[0] == 403
    assert request(server, "POST", "/api/issue", data={}, origin=False)[0] == 403


def test_static_ui_has_no_token_or_remote_resources(server):
    status, headers, raw = request(server, "GET", "/", token=False, origin=False)
    assert status == 200
    assert server[1].encode() not in raw
    assert headers["Cache-Control"] == "no-store"
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert b"https://" not in raw
    assert b"decision-form" in raw


def test_http_prepare_and_issue_explicit_human_decision(server):
    status, _, raw = request(server, "GET", "/api/example?kind=operations")
    assert status == 200
    payload = json.loads(raw)
    status, _, raw = request(server, "POST", "/api/prepare", data=payload)
    assert status == 200, raw
    draft = json.loads(raw)
    decision = {
        "draft_id": draft["id"],
        "review_sha256": draft["review_sha256"],
        "reviewer": "Synthetic HTTP reviewer",
        "note": "All synthetic sources reviewed.",
        "confirmed": False,
    }
    assert request(server, "POST", "/api/issue", data=decision)[0] == 409
    decision["confirmed"] = True
    status, _, raw = request(server, "POST", "/api/issue", data=decision)
    assert status == 200, raw
    issued = json.loads(raw)
    status, _, body = request(server, "GET", "/api/report?id=" + issued["report_id"])
    assert status == 200
    assert json.loads(body)["result"]["variance"]["noi_bridge"]["noi_variance"] == "0.01"


def test_no_mcp_tool_can_approve():
    from platworks.tools import TOOL_SPECS

    assert not any("approv" in str(tool).lower() for tool in TOOL_SPECS)
