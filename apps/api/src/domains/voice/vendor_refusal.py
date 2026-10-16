"""What a vendor's refusal may carry out of a voice client: its facts, never its words.

A refused body may quote the request — the line being voiced, the words being
transcribed, a voice's name — so it never travels (ADR-317): a refusal is its
HTTP status and the vendor's error code when that code is a bounded identifier,
in the shape every voice provider error carries (``details`` holding
``status_code`` and ``vendor_code``). An answer LIA could not read travels by its
SHAPE alone (:func:`payload_shape`): a transcription's values are the person's
words. The ElevenLabs, OpenAI and Fish Audio clients read their refusals here
(ADR-345); the Gemini client names its symbolic status (``INVALID_ARGUMENT``)
by the same rule, in its own reader, and takes its ``Retry-After`` from here.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

import httpx

#: An error code worth keeping is a bounded identifier, never prose.
_VENDOR_CODE: Final[re.Pattern[str]] = re.compile(r"[a-z][a-z0-9_]{0,63}")
#: How many keys of an unreadable answer are named, at most.
_SHAPE_KEYS_MAX: Final[int] = 16

#: Where ElevenLabs names a refusal's cause: ``detail.code``, documented, and
#: ``detail.status``, its legacy name — the one the key-ID refusal measured on
#: 2026-09-02 carried (https://elevenlabs.io/docs/eleven-api/resources/errors).
ELEVENLABS_CODE_PATHS: Final[tuple[tuple[str, ...], ...]] = (
    ("detail", "code"),
    ("detail", "status"),
)
#: Where OpenAI names it: ``error.code``.
OPENAI_CODE_PATHS: Final[tuple[tuple[str, ...], ...]] = (("error", "code"),)


@dataclass(frozen=True, slots=True)
class Refusal:
    """The facts of a refused request.

    Attributes:
        status: The HTTP status.
        vendor_code: The vendor's bounded error code, when it named one.
    """

    status: int
    vendor_code: str | None

    def details(self) -> dict[str, object]:
        """The facts, in the shape provider errors carry them."""
        return {"status_code": self.status, "vendor_code": self.vendor_code}


def bounded_code(value: object) -> str | None:
    """``value`` when it is a bounded vendor identifier, else ``None`` (never prose)."""
    return value if isinstance(value, str) and _VENDOR_CODE.fullmatch(value) else None


def _at(node: object, path: tuple[str, ...]) -> object:
    """The value ``path`` leads to in a decoded JSON body, or ``None``."""
    for key in path:
        if not isinstance(node, Mapping):
            return None
        node = node.get(key)
    return node


def body_code(response: httpx.Response, *paths: tuple[str, ...]) -> str | None:
    """The first bounded code the response's JSON body names along ``paths``.

    Args:
        response: A response whose body was read.
        *paths: The key paths a vendor names its code at, first match winning
            (``("error", "code")``).

    Returns:
        The code, or ``None`` when the body is no JSON or no path leads to a
        bounded identifier.
    """
    try:
        body: object = response.json()
    except ValueError:
        return None
    for path in paths:
        if (code := bounded_code(_at(body, path))) is not None:
            return code
    return None


def refusal_from_body(response: httpx.Response, *paths: tuple[str, ...]) -> Refusal:
    """The facts of ``response``: its status and the code its JSON body names along ``paths``."""
    return Refusal(status=response.status_code, vendor_code=body_code(response, *paths))


def retry_after_of(response: httpx.Response) -> float | None:
    """The seconds a refusal's ``Retry-After`` header asks for, when it states a delay.

    Args:
        response: The refused response.

    Returns:
        The delay, or ``None`` for an absent header, a date, or a value that is
        no finite, non-negative number of seconds.
    """
    try:
        seconds = float(response.headers.get("Retry-After", ""))
    except ValueError:
        return None
    return seconds if math.isfinite(seconds) and seconds >= 0 else None


def payload_shape(payload: object) -> dict[str, object]:
    """What an answer LIA could not read may say about itself: its keys, never its values."""
    if isinstance(payload, Mapping):
        return {"keys": sorted(str(key) for key in payload)[:_SHAPE_KEYS_MAX]}
    return {"type": type(payload).__name__}


__all__ = [
    "ELEVENLABS_CODE_PATHS",
    "OPENAI_CODE_PATHS",
    "Refusal",
    "body_code",
    "bounded_code",
    "payload_shape",
    "refusal_from_body",
    "retry_after_of",
]
