"""Hermetic fake provider (ADR-215, G3/G4), in the two wire formats a seeded core answers on.

OpenAI-compatible — ``GET /v1/models``, ``POST /v1/chat/completions`` (plain +
SSE streaming) and ``POST /v1/responses`` (SSE event shapes): the response and
the ReAct loop of a fresh install run on DeepSeek through the base URL override.

Anthropic — ``GET /v1/models``, ``POST /v1/messages`` (plain + the NAMED
server-sent events its SDK reads) and ``POST /v1/messages/count_tokens``: the
other core slots answer there. The two formats share nothing but the fixture
key, so a path decides which one answers.

Any request whose key is not the fixed non-secret fixture value
``sk-fake-qualification-key`` — a bearer token, or Anthropic's ``x-api-key`` —
is rejected 401. Only method/path metadata is ever logged: no prompt, no
authorization header.

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

_ANSWER = "Hermetic OK."


def _anthropic_message(model: str, *, answered: bool) -> dict:
    """An Anthropic ``message``: whole when ``answered``, else the stream's opening."""
    return {
        "id": "msg_fake_1",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [{"type": "text", "text": _ANSWER}] if answered else [],
        "stop_reason": "end_turn" if answered else None,
        "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 2 if answered else 0},
    }


def _anthropic_stream(model: str) -> list[dict]:
    """The events of one streamed text answer, in the order the SDK expects them."""
    return [
        {"type": "message_start", "message": _anthropic_message(model, answered=False)},
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "text", "text": ""},
        },
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": _ANSWER},
        },
        {"type": "content_block_stop", "index": 0},
        {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn", "stop_sequence": None},
            "usage": {"output_tokens": 2},
        },
        {"type": "message_stop"},
    ]


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        # Method/path metadata only — never bodies or headers.
        sys.stderr.write(f"{self.command} {self.path}\n")

    def _authorized(self) -> bool:
        return (
            self.headers.get("Authorization") == f"Bearer {FIXTURE_KEY}"
            or self.headers.get("x-api-key") == FIXTURE_KEY
        )

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

    def _send_named_sse(self, events: list[dict]) -> None:
        """Anthropic's stream: each event is NAMED after its ``type``."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for event in events:
            self.wfile.write(f"event: {event['type']}\ndata: {json.dumps(event)}\n\n".encode())
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
        path = self.path.split("?", 1)[0].rstrip("/")
        if path.endswith("/messages/count_tokens"):
            self._send_json(200, {"input_tokens": 1})
            return
        if path.endswith("/messages"):
            model = str(payload.get("model") or "fake-model")
            if payload.get("stream"):
                self._send_named_sse(_anthropic_stream(model))
                return
            self._send_json(200, _anthropic_message(model, answered=True))
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
