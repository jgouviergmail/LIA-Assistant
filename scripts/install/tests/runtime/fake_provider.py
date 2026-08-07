"""Hermetic OpenAI-compatible fake provider (ADR-215, G3/G4).

Serves the three endpoints the backend adapters consume — ``GET
/v1/models``, ``POST /v1/chat/completions`` (plain + SSE streaming), and
``POST /v1/responses`` (SSE event shapes) — for BOTH required providers
(the seeded core runs on DeepSeek through the same base URL override).

Any request whose bearer token is not the fixed non-secret fixture value
``sk-fake-qualification-key`` is rejected 401. Only method/path metadata is
ever logged: no prompt, no authorization header.

Stdlib only: this runs inside a bare python container in the disposable
workflow. Usage: ``python fake_provider.py [port]`` (default 18080).
"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FIXTURE_KEY = "sk-fake-qualification-key"

_CHAT_BODY = {
    "id": "chatcmpl-fake-1",
    "object": "chat.completion",
    "created": 0,
    "model": "fake-model",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "Hermetic OK."},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
}


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        # Method/path metadata only — never bodies or headers.
        sys.stderr.write(f"{self.command} {self.path}\n")

    def _authorized(self) -> bool:
        return self.headers.get("Authorization") == f"Bearer {FIXTURE_KEY}"

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_sse(self, events: list[str]) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for event in events:
            self.wfile.write(f"data: {event}\n\n".encode())
        self.wfile.flush()

    def do_GET(self) -> None:  # noqa: N802
        if not self._authorized():
            self._send_json(401, {"error": {"message": "invalid key"}})
            return
        if self.path.rstrip("/").endswith("/models"):
            self._send_json(
                200,
                {"object": "list", "data": [{"id": "fake-model", "object": "model"}]},
            )
            return
        self._send_json(404, {"error": {"message": "not found"}})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        if not self._authorized():
            self._send_json(401, {"error": {"message": "invalid key"}})
            return
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._send_json(400, {"error": {"message": "bad json"}})
            return
        if self.path.rstrip("/").endswith("/chat/completions"):
            if payload.get("stream"):
                delta = {
                    "id": "chatcmpl-fake-1",
                    "object": "chat.completion.chunk",
                    "created": 0,
                    "model": "fake-model",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"role": "assistant", "content": "Hermetic OK."},
                            "finish_reason": None,
                        }
                    ],
                }
                final = {
                    "id": "chatcmpl-fake-1",
                    "object": "chat.completion.chunk",
                    "created": 0,
                    "model": "fake-model",
                    "choices": [
                        {"index": 0, "delta": {}, "finish_reason": "stop"}
                    ],
                    "usage": {
                        "prompt_tokens": 1,
                        "completion_tokens": 2,
                        "total_tokens": 3,
                    },
                }
                self._send_sse([json.dumps(delta), json.dumps(final), "[DONE]"])
                return
            self._send_json(200, _CHAT_BODY)
            return
        if self.path.rstrip("/").endswith("/responses"):
            events = [
                json.dumps(
                    {
                        "type": "response.output_text.delta",
                        "delta": "Hermetic OK.",
                    }
                ),
                json.dumps(
                    {
                        "type": "response.completed",
                        "response": {
                            "id": "resp-fake-1",
                            "status": "completed",
                            "output": [
                                {
                                    "type": "message",
                                    "content": [
                                        {
                                            "type": "output_text",
                                            "text": "Hermetic OK.",
                                        }
                                    ],
                                }
                            ],
                            "usage": {
                                "input_tokens": 1,
                                "output_tokens": 2,
                                "total_tokens": 3,
                            },
                        },
                    }
                ),
            ]
            self._send_sse(events)
            return
        self._send_json(404, {"error": {"message": "not found"}})


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 18080
    server = ThreadingHTTPServer(("0.0.0.0", port), _Handler)
    sys.stderr.write(f"fake-provider listening on :{port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
