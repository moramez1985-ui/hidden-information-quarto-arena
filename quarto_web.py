from __future__ import annotations

from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from typing import Any
from urllib.parse import unquote, urlsplit

from quarto_engine import (
    MODES,
    GameState,
    apply_action,
    legal_actions,
    new_game,
    piece_attributes,
    state_to_dict,
)


ROOT = Path(__file__).resolve().parent
MAX_REQUEST_BYTES = 16_384
STATIC_FILES = {
    "/": (ROOT / "index.html", "text/html; charset=utf-8"),
    "/index.html": (ROOT / "index.html", "text/html; charset=utf-8"),
    "/qurto.-simple.css": (ROOT / "qurto.-simple.css", "text/css; charset=utf-8"),
    "/quarto-ui.js": (ROOT / "quarto-ui.js", "text/javascript; charset=utf-8"),
    "/bootstrap-5.3.0-dist/bootstrap-5.3.0-dist/css/bootstrap.min.css": (
        ROOT / "bootstrap-5.3.0-dist/bootstrap-5.3.0-dist/css/bootstrap.min.css",
        "text/css; charset=utf-8",
    ),
    "/bootstrap-5.3.0-dist/bootstrap-5.3.0-dist/js/bootstrap.bundle.min.js": (
        ROOT / "bootstrap-5.3.0-dist/bootstrap-5.3.0-dist/js/bootstrap.bundle.min.js",
        "text/javascript; charset=utf-8",
    ),
    "/images/paper-texture.webp": (
        ROOT / "images/paper-texture.webp",
        "image/webp",
    ),
}


@dataclass(slots=True)
class GameSession:
    state: GameState | None = None
    lock: threading.RLock = field(default_factory=threading.RLock)


class QuartoHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, port: int) -> None:
        self.session = GameSession()
        super().__init__(("127.0.0.1", port), QuartoRequestHandler)

    def handle_error(self, request: Any, client_address: Any) -> None:
        self.log_error("Request handling failed for local client %s", client_address[0])


class QuartoRequestHandler(BaseHTTPRequestHandler):
    server: QuartoHTTPServer
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        try:
            path = self._decoded_path()
            if path == "/api/state":
                self._send_state()
                return
            if path == "/api/pieces":
                self._send_json(
                    200,
                    {
                        "pieces": [
                            {"id": piece_id, "attributes": piece_attributes(piece_id)}
                            for piece_id in range(16)
                        ]
                    },
                )
                return
            self._send_static(path)
        except ValueError as error:
            self._send_json(400, {"error": {"code": "invalid_path", "message": str(error)}})
        except Exception as error:
            self.log_error("Internal GET error: %s", type(error).__name__)
            self._send_json(500, {"error": {"code": "internal_error", "message": "Internal server error."}})

    def do_POST(self) -> None:
        try:
            path = self._decoded_path()
            if path not in ("/api/games", "/api/actions"):
                self._send_not_found()
                return
            payload = self._read_json()
            if path == "/api/games":
                self._start_game(payload)
                return
            if path == "/api/actions":
                self._apply_action(payload)
                return
        except RequestProblem as problem:
            self._send_json(
                problem.status,
                {"error": {"code": problem.code, "message": problem.message}},
            )
        except ValueError as error:
            self._send_json(400, {"error": {"code": "invalid_path", "message": str(error)}})
        except Exception as error:
            self.log_error("Internal POST error: %s", type(error).__name__)
            self._send_json(500, {"error": {"code": "internal_error", "message": "Internal server error."}})

    def do_PUT(self) -> None:
        self._method_not_allowed()

    def do_PATCH(self) -> None:
        self._method_not_allowed()

    def do_DELETE(self) -> None:
        self._method_not_allowed()

    def do_OPTIONS(self) -> None:
        self._method_not_allowed()

    def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
        del explain
        self._send_json(code, {"error": {"code": "http_error", "message": message or "Request failed."}})

    def log_message(self, format_string: str, *args: Any) -> None:
        del format_string, args

    def _decoded_path(self) -> str:
        raw_path = urlsplit(self.path).path
        try:
            path = unquote(raw_path, errors="strict")
        except UnicodeDecodeError as error:
            raise ValueError("Malformed URL path.") from error
        if "\x00" in path or "\\" in path:
            raise ValueError("Invalid path.")
        if any(part in (".", "..") for part in path.split("/")):
            raise ValueError("Path traversal is not allowed.")
        return path

    def _send_static(self, path: str) -> None:
        entry = STATIC_FILES.get(path)
        if entry is None:
            self._send_not_found()
            return
        file_path, content_type = entry
        resolved = file_path.resolve()
        if resolved.parent != ROOT and ROOT not in resolved.parents:
            self._send_not_found()
            return
        try:
            body = resolved.read_bytes()
        except OSError:
            self._send_not_found()
            return
        self._send_bytes(200, content_type, body)

    def _send_state(self) -> None:
        with self.server.session.lock:
            state = self.server.session.state
            body = {
                "state": state_to_dict(state) if state is not None else None,
                "legal_actions": legal_actions(state) if state is not None else None,
            }
        self._send_json(200, body)

    def _start_game(self, payload: Any) -> None:
        if not isinstance(payload, dict) or set(payload) != {"mode"}:
            raise RequestProblem(400, "invalid_request", "Expected an object with a mode.")
        mode = payload["mode"]
        if mode not in MODES:
            raise RequestProblem(400, "invalid_mode", "Mode must be classic or self_selection.")
        with self.server.session.lock:
            state = new_game(mode)
            self.server.session.state = state
            response = self._state_response(state)
        self._send_json(200, response)

    def _apply_action(self, payload: Any) -> None:
        if not isinstance(payload, dict):
            raise RequestProblem(400, "invalid_action", "Action must be a JSON object.")
        with self.server.session.lock:
            state = self.server.session.state
            if state is None:
                raise RequestProblem(409, "game_not_started", "Start a new game first.")
            try:
                next_state = apply_action(state, payload)
            except ValueError as error:
                raise RequestProblem(400, "invalid_action", str(error)) from error
            self.server.session.state = next_state
            response = self._state_response(next_state)
        self._send_json(200, response)

    def _state_response(self, state: GameState) -> dict[str, Any]:
        return {
            "state": state_to_dict(state),
            "legal_actions": legal_actions(state),
        }

    def _read_json(self) -> Any:
        if self.headers.get_content_type() != "application/json":
            raise RequestProblem(415, "unsupported_media_type", "Send JSON with Content-Type: application/json.")
        try:
            content_length = int(self.headers.get("Content-Length", ""))
        except ValueError as error:
            raise RequestProblem(400, "invalid_content_length", "Invalid Content-Length.") from error
        if content_length < 0:
            raise RequestProblem(400, "invalid_content_length", "Invalid Content-Length.")
        if content_length > MAX_REQUEST_BYTES:
            raise RequestProblem(413, "request_too_large", "Request body is too large.")
        try:
            raw_body = self.rfile.read(content_length)
            return json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RequestProblem(400, "invalid_json", "Request body must contain valid JSON.") from error

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self._send_bytes(status, "application/json; charset=utf-8", body)

    def _send_not_found(self) -> None:
        self._send_json(404, {"error": {"code": "not_found", "message": "Resource not found."}})

    def _method_not_allowed(self) -> None:
        self._send_json(405, {"error": {"code": "method_not_allowed", "message": "Method not allowed."}})

    def _send_bytes(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "script-src 'self'; connect-src 'self'; font-src 'self' data: https://fonts.gstatic.com; "
            "object-src 'none'; base-uri 'self'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(body)


class RequestProblem(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def create_server(port: int = 8000) -> QuartoHTTPServer:
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError("Port must be an integer from 0 to 65535.")
    return QuartoHTTPServer(port)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run the local Quarto web game.")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    try:
        server = create_server(args.port)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f"Quarto is available at http://127.0.0.1:{server.server_address[1]}/")
    print("Press Ctrl+C to stop the local server.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Quarto server.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
