"""Tiny sandboxed HTTP server providing two facts:
   GET /weather/berlin → JSON {temp_c, condition, source}
   GET /rates/eur-usd  → JSON {rate, as_of}
   GET /health         → liveness
   Anything else      → 404
"""

from __future__ import annotations

import json
import os
import socket
from http.server import BaseHTTPRequestHandler, HTTPServer

WEATHER_BERLIN = {"temp_c": 14, "condition": "partly cloudy", "city": "Berlin", "source": "sandbox-met"}
RATE = {"rate": 1.0832, "pair": "EUR/USD", "as_of": "2026-04-09T08:00:00Z"}


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, body: dict) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        if path == "/health":
            self._send_json(200, {"ok": True})
        elif path in ("/weather/berlin", "/weather/berlin/"):
            self._send_json(200, WEATHER_BERLIN)
        elif path in ("/rates/eur-usd", "/rates/eur-usd/"):
            self._send_json(200, RATE)
        else:
            self._send_json(404, {"error": "not found", "path": path})

    def log_message(self, format, *args):  # noqa: A002
        pass


def main() -> None:
    port = int(os.environ.get("PORT", "0"))
    host = "127.0.0.1"
    server = HTTPServer((host, port), Handler)
    actual_port = server.server_address[1]
    print(f"sandbox facts site listening on http://{host}:{actual_port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
