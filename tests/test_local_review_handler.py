"""Offline HTTP handler checks supplement, and do not replace, live socket tests."""

import io
import json
from types import SimpleNamespace

import pytest

from platworks.local_review.server import create_handler


class RequestStream:
    def __init__(self, raw):
        self.input = io.BytesIO(raw)
        self.output = io.BytesIO()

    def makefile(self, *args):
        return self.input

    def sendall(self, data):
        self.output.write(data)

    def settimeout(self, value):
        pass


def dispatch(
    handler, method, path, body=None, *, auth=True, origin=True, host="127.0.0.1:8765", port=8765
):
    raw = json.dumps(body).encode() if body is not None else b""
    headers = [
        f"{method} {path} HTTP/1.0",
        "Host: " + host,
        "Content-Type: application/json",
        "Content-Length: " + str(len(raw)),
    ]
    if auth:
        headers.append("Authorization: Bearer synthetic-test-capability")
    if origin:
        headers.append(
            "Origin: " + (origin if isinstance(origin, str) else f"http://127.0.0.1:{port}")
        )
    stream = RequestStream("\r\n".join(headers).encode() + b"\r\n\r\n" + raw)
    handler(stream, ("127.0.0.1", 50000), SimpleNamespace(server_port=port))
    head, response = stream.output.getvalue().split(b"\r\n\r\n", 1)
    return int(head.split(b" ")[1]), head, response


def test_handler_boundaries_without_socket(tmp_path):
    handler = create_handler(tmp_path / "review", "synthetic-test-capability")
    for method, path in [("GET", "/api/state"), ("POST", "/api/issue")]:
        assert dispatch(handler, method, path, {}, auth=False)[0] == 403
        assert dispatch(handler, method, path, {}, host="attacker.example")[0] == 403
    assert dispatch(handler, "POST", "/api/issue", {}, origin=False)[0] == 403
    assert dispatch(handler, "GET", "/api/source?sha=../../private")[0] == 404
    status, headers, raw = dispatch(handler, "GET", "/", auth=False)
    assert status == 200
    assert b"synthetic-test-capability" not in raw
    assert b"Cache-Control: no-store" in headers


def test_handler_two_phase_acquisition_and_restart(tmp_path):
    root = tmp_path / "review"
    handler = create_handler(root, "synthetic-test-capability")
    _, _, raw = dispatch(handler, "GET", "/api/example?kind=acquisition")
    example = json.loads(raw)
    status, _, raw = dispatch(handler, "POST", "/api/prepare", example)
    assert status == 200, raw
    draft = json.loads(raw)
    decision = {
        "draft_id": draft["id"],
        "review_sha256": draft["review_sha256"],
        "reviewer": "Synthetic offline reviewer",
        "note": "Synthetic test decision.",
        "confirmed": True,
    }
    status, _, raw = dispatch(handler, "POST", "/api/execute", decision)
    assert status == 200, raw
    result = json.loads(raw)
    assert result["result"]["base"]["metrics"]
    assert dispatch(handler, "POST", "/api/issue", decision)[0] == 409
    decision["review_sha256"] = result["review_sha256"]
    # New handler instance and Workspace simulate restart, with retained state.
    handler = create_handler(root, "synthetic-test-capability")
    status, _, raw = dispatch(handler, "POST", "/api/issue", decision)
    assert status == 200, raw
    issued = json.loads(raw)
    status, _, raw = dispatch(handler, "GET", "/api/report?id=" + issued["report_id"])
    assert status == 200
    assert json.loads(raw)["data_class"] == "synthetic"


def test_handler_operations_has_no_implicit_approval(tmp_path):
    handler = create_handler(tmp_path / "review", "synthetic-test-capability")
    _, _, raw = dispatch(handler, "GET", "/api/example?kind=operations")
    status, _, raw = dispatch(handler, "POST", "/api/prepare", json.loads(raw))
    assert status == 200, raw
    draft = json.loads(raw)
    assert draft["report_id"] is None
    assert draft["result"]["human_approval"] == "not_granted"
    decision = {
        "draft_id": draft["id"],
        "review_sha256": draft["review_sha256"],
        "reviewer": "Synthetic offline reviewer",
        "note": "Synthetic test decision.",
        "confirmed": False,
    }
    assert dispatch(handler, "POST", "/api/issue", decision)[0] == 409
    decision["confirmed"] = True
    status, _, raw = dispatch(handler, "POST", "/api/issue", decision)
    assert status == 200, raw
    issued = json.loads(raw)
    assert issued["report_id"]
    assert dispatch(handler, "POST", "/api/issue", decision)[0] == 200


def test_handler_history_pagination_and_bounds(tmp_path):
    handler = create_handler(tmp_path / "review", "synthetic-test-capability")
    _, _, raw = dispatch(handler, "GET", "/api/example?kind=operations")
    example = json.loads(raw)
    for revision in ("first", "second"):
        example["settings"]["policy_note"] = "Synthetic " + revision
        assert dispatch(handler, "POST", "/api/prepare", example)[0] == 200
    status, _, raw = dispatch(handler, "GET", "/api/state?limit=1")
    newest = json.loads(raw)
    assert status == 200 and newest["history"]["has_more"] is True
    status, _, raw = dispatch(handler, "GET", "/api/state?limit=1&offset=1")
    older = json.loads(raw)
    assert status == 200 and older["history"]["has_more"] is False
    assert older["drafts"][0]["id"] != newest["drafts"][0]["id"]
    assert dispatch(handler, "GET", "/api/draft?id=" + older["drafts"][0]["id"])[0] == 200
    for query in ("offset=-1", "limit=101", "limit=0"):
        assert dispatch(handler, "GET", "/api/state?" + query)[0] == 409


@pytest.mark.parametrize(
    "host,origin",
    [
        ("127.0.0.1", "http://127.0.0.1"),
        ("127.0.0.1:80", "http://127.0.0.1:80"),
    ],
)
def test_default_http_port_accepts_browser_serialization(tmp_path, host, origin):
    handler = create_handler(tmp_path / "review", "synthetic-test-capability")
    options = {"port": 80, "host": host, "origin": origin}
    assert dispatch(handler, "GET", "/", auth=False, **options)[0] == 200
    status, _, raw = dispatch(handler, "GET", "/api/example?kind=operations", **options)
    assert status == 200
    assert dispatch(handler, "POST", "/api/prepare", json.loads(raw), **options)[0] == 200
    assert (
        dispatch(handler, "GET", "/api/state", port=80, host="127.0.0.1:81", origin=origin)[0]
        == 403
    )
    assert dispatch(handler, "GET", "/api/state", port=81, host=host, origin=origin)[0] == 403


def test_retained_sources_keep_role_filenames_for_identical_bytes(tmp_path):
    import base64

    handler = create_handler(tmp_path / "review", "synthetic-test-capability")
    _, _, raw = dispatch(handler, "GET", "/api/example?kind=operations")
    payload = json.loads(raw)
    data = json.loads(base64.b64decode(payload["files"]["dataset"]["data_base64"]))
    gl = (
        "property,period,account_code,account_name,category,amount\n"
        "synthetic-ops,2026-05,4000,Rent,rental income,0.30\n"
    ).encode()
    source_bytes = {"actuals": gl, "budgets": gl, "snapshot": json.dumps(data["snapshot"]).encode()}
    names = {"actuals": "actuals.csv", "budgets": "budgets.csv", "snapshot": "snapshot.json"}
    payload["settings"].update(property="synthetic-ops", period="2026-05", unit_count=10)
    payload["files"] = {
        role: {"filename": names[role], "data_base64": base64.b64encode(raw).decode()}
        for role, raw in source_bytes.items()
    }
    status, _, raw = dispatch(handler, "POST", "/api/prepare", payload)
    assert status == 200, raw
    original = json.loads(raw)
    assert original["sources"]["actuals"]["sha256"] == original["sources"]["budgets"]["sha256"]
    payload["files"] = {
        role: {"draft_id": original["id"], "sha256": ref["sha256"]}
        for role, ref in original["sources"].items()
    }
    payload["settings"]["policy_note"] = "Revised synthetic policy without changing sources"
    status, _, raw = dispatch(handler, "POST", "/api/prepare", payload)
    assert status == 200, raw
    revised = json.loads(raw)
    assert revised["sources"] == original["sources"]
    for role, ref in revised["sources"].items():
        status, headers, body = dispatch(
            handler,
            "GET",
            "/api/source?sha=" + ref["sha256"] + "&draft_id=" + revised["id"] + "&role=" + role,
        )
        assert status == 200 and names[role].encode() in headers
        assert body == source_bytes[role]
    # A hash alone cannot select a filename when several sources share its bytes.
    sha = original["sources"]["actuals"]["sha256"]
    status, _, raw = dispatch(handler, "GET", "/api/source?sha=" + sha)
    assert status == 409 and json.loads(raw)["error"]["code"] == "AMBIGUOUS_SOURCE"
    payload["files"]["actuals"]["sha256"] = original["sources"]["snapshot"]["sha256"]
    assert dispatch(handler, "POST", "/api/prepare", payload)[0] == 404
    payload["files"]["actuals"] = {"sha256": sha}
    assert dispatch(handler, "POST", "/api/prepare", payload)[0] == 409
