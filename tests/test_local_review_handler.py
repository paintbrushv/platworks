"""Offline HTTP handler checks supplement, and do not replace, live socket tests."""

import io
import json
from types import SimpleNamespace

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


def dispatch(handler, method, path, body=None, *, auth=True, origin=True, host="127.0.0.1:8765"):
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
        headers.append("Origin: http://127.0.0.1:8765")
    stream = RequestStream("\r\n".join(headers).encode() + b"\r\n\r\n" + raw)
    handler(stream, ("127.0.0.1", 50000), SimpleNamespace(server_port=8765))
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
