"""The documented System One request, with Choice AND Noul questions (measurement only).

The application's transport (``infrastructure/llm/typesafe_client.py``) carries
Choice questions alone; the documented API (docs.typesafe.ai/api) also serves
Noul — the probability that a condition holds — which the vendor recommends for
yes/no judgments and for multi-label sets (one Noul per label). This module sends
the documented request shape, bounded, without retry, and returns the usage so the
caller settles it.
"""

import json
from dataclasses import dataclass

import httpx

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
# The documented budget is 64k tokens per request; bytes are a conservative proxy.
MAX_REQUEST_BYTES = 180_000
MAX_RESPONSE_BYTES = 262_144


class NativeError(Exception):
    """A refused or unreadable request; ``billed`` tells whether usage came back."""

    def __init__(self, code: str, input_tokens: int = 0, output_tokens: int = 0) -> None:
        super().__init__(code)
        self.code = code
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


@dataclass(frozen=True)
class NativeResult:
    """Answers keyed by question id, and the billed usage."""

    model: str
    answers: dict[str, dict[str, object]]
    input_tokens: int
    output_tokens: int


async def system_one(
    http: httpx.AsyncClient,
    api_key: str,
    model: str,
    state: object,
    questions: dict[str, dict[str, object]],
    timeout_seconds: float,
) -> NativeResult:
    """One documented System One request; every question answered or a NativeError."""
    body = json.dumps(
        {"state": state, "model": model, "questions": questions}, ensure_ascii=False
    ).encode("utf-8")
    if len(body) > MAX_REQUEST_BYTES:
        raise NativeError("request_too_large")
    try:
        response = await http.post(
            ENDPOINT,
            content=body,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=timeout_seconds,
        )
    except httpx.TimeoutException as exc:
        raise NativeError("timeout") from exc
    except httpx.HTTPError as exc:
        raise NativeError("transport_error") from exc
    if len(response.content) > MAX_RESPONSE_BYTES:
        raise NativeError("response_too_large")
    try:
        payload = response.json()
    except ValueError as exc:
        raise NativeError(f"http_{response.status_code}_unreadable") from exc
    usage = payload.get("usage") if isinstance(payload, dict) else None
    tokens_in = int(usage.get("input_tokens", 0)) if isinstance(usage, dict) else 0
    tokens_out = int(usage.get("output_tokens", 0)) if isinstance(usage, dict) else 0
    if response.status_code != 200:
        raise NativeError(f"http_{response.status_code}", tokens_in, tokens_out)
    answers = payload.get("answers")
    if not isinstance(answers, dict) or set(answers) != set(questions):
        raise NativeError("answer_set", tokens_in, tokens_out)
    return NativeResult(str(payload.get("model")), answers, tokens_in, tokens_out)
