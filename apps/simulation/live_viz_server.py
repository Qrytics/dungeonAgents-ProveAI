"""HTTP helper for the React visualizer during an in-progress simulation.

Serves the current ``runs/<run_id>.jsonl`` contents so the browser can poll
and redraw the grid as new outcome lines are appended.

Binds to 127.0.0.1 only. Used when ``python -m apps.simulation.main --live-viz`` is set.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

_live_server: ThreadingHTTPServer | None = None
_live_thread: threading.Thread | None = None


def start_live_viz_server(runs_dir: Path, port: int = 8765) -> None:
    """Start a daemon thread serving run logs from *runs_dir* on 127.0.0.1:*port*.

    Idempotent: if a server is already running on this module, does nothing.
    """
    global _live_server, _live_thread

    if _live_server is not None:
        return

    runs_root = runs_dir.resolve()

    class _Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, _format: str, *_args: object) -> None:
            return

        def _send_json(self, status: int, body: object) -> None:
            raw = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/api/health":
                self._send_json(200, {"ok": True})
                return

            # GET /api/runs/<run_id>/raw
            parts = parsed.path.strip("/").split("/")
            if (
                len(parts) == 4
                and parts[0] == "api"
                and parts[1] == "runs"
                and parts[3] == "raw"
            ):
                run_id = unquote(parts[2])
                if not run_id or "/" in run_id or "\\" in run_id or ".." in run_id:
                    self._send_json(400, {"exists": False, "error": "invalid run id"})
                    return
                safe_name = f"{run_id}.jsonl"
                log_path = (runs_root / safe_name).resolve()
                try:
                    log_path.relative_to(runs_root)
                except ValueError:
                    self._send_json(400, {"exists": False, "error": "invalid path"})
                    return

                if not log_path.is_file():
                    self._send_json(200, {"exists": False, "text": ""})
                    return

                try:
                    text = log_path.read_text(encoding="utf-8")
                except OSError as exc:
                    self._send_json(500, {"exists": False, "error": str(exc)})
                    return

                self._send_json(200, {"exists": True, "text": text})
                return

            self._send_json(404, {"error": "not found"})

    server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _live_server = server
    _live_thread = thread
