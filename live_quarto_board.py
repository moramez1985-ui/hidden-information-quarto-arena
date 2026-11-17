from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import webbrowser

from build_visualizer import render_visualizer_html


def run_live_server(state_json_path: Path, port: int = 8050) -> None:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def do_GET(self) -> None:
            if self.path.startswith("/api/live"):
                if state_json_path.is_file():
                    raw = json.loads(state_json_path.read_text(encoding="utf-8"))
                    if isinstance(raw, dict) and isinstance(raw.get("results"), list):
                        for item in raw["results"]:
                            if isinstance(item, dict) and isinstance(item.get("dictResult"), dict):
                                raw = item["dictResult"]
                                break
                else:
                    raw = {"matches": [], "evaluator": {}}
                body = json.dumps(raw, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            initial_payload = {"matches": [], "evaluator": {}}
            if state_json_path.is_file():
                initial_payload = json.loads(state_json_path.read_text(encoding="utf-8"))
                if isinstance(initial_payload, dict) and isinstance(initial_payload.get("results"), list):
                    for item in initial_payload["results"]:
                        if isinstance(item, dict) and isinstance(item.get("dictResult"), dict):
                            initial_payload = item["dictResult"]
                            break
            html = render_visualizer_html(initial_payload, live_endpoint="/api/live").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"Live Quarto Board running at {url} (watching {state_json_path}) — Ctrl+C to stop.")
    webbrowser.open(url)
    server.serve_forever()


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("live_match_state.json")
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8050
    run_live_server(target, port=port)
