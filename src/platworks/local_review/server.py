"""Loopback-only browser capability. No remote approval or arbitrary file endpoint."""

import base64
import binascii
import hmac
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from urllib.parse import parse_qs, quote, urlsplit

from .common import MAX_BODY, MAX_FILE, ReviewError, decode, encode, refuse
from .examples import example
from .normalize import CATEGORIES
from .store import Workspace

STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/review.js": ("review.js", "text/javascript; charset=utf-8"),
    "/review.css": ("review.css", "text/css; charset=utf-8"),
}


def create_handler(workspace, token):
    workspace = workspace if isinstance(workspace, Workspace) else Workspace(workspace)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # No URLs, filenames, business identifiers, tokens or source content in logs.

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def send(self, status, body, content_type="application/json", filename=None):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; script-src 'self'; "
                "style-src 'self'; connect-src 'self'; base-uri 'none'; "
                "frame-ancestors 'none'; form-action 'self'",
            )
            if filename:
                self.send_header(
                    "Content-Disposition", "attachment; filename*=UTF-8''" + quote(filename)
                )
            self.end_headers()
            self.wfile.write(body)

        def boundary(self, private):
            host = f"127.0.0.1:{self.server.server_port}"
            allowed_hosts = {host}
            if self.server.server_port == 80:
                allowed_hosts.add("127.0.0.1")  # Browsers omit the default HTTP port.
            supplied_hosts = self.headers.get_all("Host", [])
            if len(supplied_hosts) != 1 or supplied_hosts[0] not in allowed_hosts:
                refuse("LOCAL_ORIGIN_REQUIRED", "Use the exact local review address.")
            origin = self.headers.get_all("Origin", [])
            allowed_origins = {"http://" + value for value in allowed_hosts}
            if origin and (len(origin) != 1 or origin[0] not in allowed_origins):
                refuse("LOCAL_ORIGIN_REQUIRED", "Cross-origin access is refused.")
            if private:
                auth = self.headers.get_all("Authorization", [])
                if len(auth) != 1 or not hmac.compare_digest(
                    auth[0].encode("utf-8"), ("Bearer " + token).encode("utf-8")
                ):
                    refuse("LOCAL_SESSION_REQUIRED", "Open the session link printed by the CLI.")
            if self.command == "POST" and not origin:
                refuse("LOCAL_ORIGIN_REQUIRED", "A local browser review origin is required.")

        def dispatch(self):
            split = urlsplit(self.path)
            path = split.path
            if self.command == "GET" and path in STATIC:
                self.boundary(False)
                resource, content_type = STATIC[path]
                raw = files("platworks.local_review").joinpath("static", resource).read_bytes()
                return self.send(200, raw, content_type)
            self.boundary(True)
            params = parse_qs(split.query, strict_parsing=True)
            if self.command == "GET":
                if path == "/api/state":
                    offset = int(params.get("offset", ["0"])[0])
                    limit = int(params.get("limit", ["100"])[0])
                    if offset < 0 or not 1 <= limit <= 100:
                        refuse("INVALID_INPUT", "Use a nonnegative offset and page size of 1–100.")
                    drafts = workspace.list_drafts(offset=offset, limit=limit + 1)
                    reports = workspace.list_reports(offset=offset, limit=limit + 1)
                    value = {
                        "drafts": drafts[:limit],
                        "reports": reports[:limit],
                        "categories": CATEGORIES,
                        "history": {
                            "offset": offset,
                            "page_size": limit,
                            "has_more": len(drafts) > limit or len(reports) > limit,
                        },
                    }
                elif path == "/api/draft":
                    value = workspace.get(params["id"][0])
                elif path == "/api/report":
                    value = workspace.report(params["id"][0])
                    return self.send(200, encode(value), filename="platworks-reviewed-report.json")
                elif path == "/api/source":
                    name, raw = workspace.source(params["sha"][0])
                    return self.send(200, raw, "application/octet-stream", name)
                elif path == "/api/example":
                    kind = params["kind"][0]
                    if kind not in {"acquisition", "operations"}:
                        refuse("INVALID_INPUT", "Unknown example.")
                    value = example(kind)
                else:
                    refuse("NOT_FOUND", "Unknown local review endpoint.")
            elif self.command == "POST":
                if self.headers.get("Transfer-Encoding"):
                    refuse("INVALID_INPUT", "Chunked requests are not supported.")
                lengths = self.headers.get_all("Content-Length", [])
                if (
                    len(lengths) != 1
                    or not lengths[0].isdigit()
                    or not 0 < int(lengths[0]) <= MAX_BODY
                ):
                    refuse("INPUT_LIMIT", "Request must contain at most 12 MiB.")
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    refuse("INVALID_INPUT", "Use a JSON review request.")
                length = int(lengths[0])
                raw = self.rfile.read(length)
                if len(raw) != length:
                    refuse("INVALID_INPUT", "Incomplete request body.")
                request = decode(raw)
                if path == "/api/prepare":
                    if set(request) != {"kind", "files", "settings"} or not isinstance(
                        request["files"], dict
                    ):
                        refuse("INVALID_INPUT", "Invalid source selection.")
                    if not 1 <= len(request["files"]) <= 4:
                        refuse("INPUT_LIMIT", "Select one to four files.")
                    sources = {}
                    for role, item in request["files"].items():
                        if set(item) == {"sha256"}:
                            sources[role] = workspace.source(item["sha256"])
                        elif set(item) == {"filename", "data_base64"}:
                            if len(item["data_base64"]) > (MAX_FILE + 2) // 3 * 4:
                                refuse("INPUT_LIMIT", "Each source is limited to 2 MiB.")
                            sources[role] = (
                                item["filename"],
                                base64.b64decode(item["data_base64"], validate=True),
                            )
                        else:
                            refuse("INVALID_INPUT", "Invalid source selection.")
                    value = workspace.prepare(request["kind"], sources, request["settings"])
                elif path in {"/api/execute", "/api/issue"}:
                    if set(request) != {
                        "draft_id",
                        "review_sha256",
                        "reviewer",
                        "note",
                        "confirmed",
                    }:
                        refuse("INVALID_INPUT", "Invalid human decision request.")
                    value = workspace.decide(path.rsplit("/", 1)[1], **request)
                else:
                    refuse("NOT_FOUND", "Unknown local review endpoint.")
            else:
                refuse("NOT_FOUND", "Unsupported local review method.")
            self.send(200, encode(value))

        def handle_request(self):
            try:
                self.dispatch()
            except ReviewError as error:
                status = (
                    403
                    if error.code in {"LOCAL_SESSION_REQUIRED", "LOCAL_ORIGIN_REQUIRED"}
                    else 409
                )
                if error.code == "NOT_FOUND":
                    status = 404
                self.send(status, encode({"error": {"code": error.code, "message": error.message}}))
            except (KeyError, ValueError, TypeError, binascii.Error):
                self.send(
                    400,
                    encode(
                        {
                            "error": {
                                "code": "INVALID_INPUT",
                                "message": "Request does not match the local review layout.",
                            }
                        }
                    ),
                )
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                pass
            except Exception:
                self.send(
                    500,
                    encode(
                        {
                            "error": {
                                "code": "LOCAL_REVIEW_FAILED",
                                "message": "Review failed. Run platworks doctor --analysis.",
                            }
                        }
                    ),
                )

        do_GET = handle_request
        do_POST = handle_request
        do_OPTIONS = handle_request

    return Handler


def create_server(workspace, *, port=0):
    token = secrets.token_urlsafe(32)

    class LocalServer(ThreadingHTTPServer):
        def handle_error(self, request, client_address):
            pass  # Do not emit request exceptions or private paths to stderr.

    server = LocalServer(("127.0.0.1", port), create_handler(workspace, token))
    server.daemon_threads = True
    return server, token
