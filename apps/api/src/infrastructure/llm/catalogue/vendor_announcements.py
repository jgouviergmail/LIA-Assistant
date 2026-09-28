"""Shutdown dates a VENDOR announced, which outrank what the registries copied.

The vendored registries (LiteLLM, models.dev) are third-party copies of vendor
pages. When the vendor's own page says otherwise, the vendor wins — owner rule
of 2026-09-26, « the Google Gemini site is the reference ». Measured that day:
LiteLLM dated the three Gemini 2.5 chat models 2026-10-20 and the two 3.5
models in 2027, while Google's deprecations page announces no shutdown for any
of them (the 2.5 models « will continue to be served until further notice »).

An entry maps ``(provider, model)`` to the announced shutdown date, or to
``None`` when the vendor lists the model and announces no shutdown. A model the
table does not hold falls back to the registries, unchanged. Google calls these
dates the EARLIEST possible shutdown: a past date announces, it does not prove
the model gone — only the API's own model list does (see the catalogue
alignment migration ``70fd39bf9e8d``).
"""

from __future__ import annotations

from datetime import date
from typing import Final

#: The page every Gemini entry was read on.
GEMINI_DEPRECATIONS_URL: Final[str] = "https://ai.google.dev/gemini-api/docs/deprecations"
#: When it was read.
GEMINI_DEPRECATIONS_READ_ON: Final[date] = date(2026, 9, 26)

#: Google's page, for every model it lists that LIA's catalogue may hold. Two
#: rows spell the model as the API does where the page abbreviates it:
#: ``gemini-2.5-flash-preview-09-2025`` (« …-09-25 » on the page, released the
#: same day as its « -lite-preview-09-2025 » sibling) and
#: ``gemini-embedding-2-preview`` (« embedding-2-preview »).
VENDOR_SHUTDOWNS: Final[dict[tuple[str, str], date | None]] = {
    ("gemini", "gemini-3.8-flash"): None,
    ("gemini", "gemini-3.8-flash-tts"): None,
    ("gemini", "gemini-3.8-flash-lite-tts"): None,
    ("gemini", "gemini-3.8-live"): None,
    ("gemini", "gemini-3.8-live-extended-thinking"): None,
    ("gemini", "gemini-3.7-flash"): None,
    ("gemini", "gemini-3.6-flash"): None,
    ("gemini", "gemini-3.5-flash"): None,
    ("gemini", "gemini-3.5-flash-lite"): None,
    ("gemini", "gemini-3.1-flash-lite"): date(2027, 5, 7),
    ("gemini", "gemini-3.1-flash-lite-preview"): date(2026, 5, 25),
    ("gemini", "gemini-3.1-flash-tts-preview"): None,
    ("gemini", "gemini-3.1-flash-live-preview"): None,
    ("gemini", "gemini-3.1-pro-preview"): None,
    ("gemini", "gemini-3-flash-preview"): None,
    ("gemini", "gemini-3-pro-preview"): date(2026, 3, 9),
    ("gemini", "gemini-3-pro-image-preview"): date(2026, 6, 25),
    ("gemini", "gemini-2.5-pro"): None,
    ("gemini", "gemini-2.5-pro-preview-tts"): None,
    ("gemini", "gemini-2.5-flash"): None,
    ("gemini", "gemini-2.5-flash-preview-tts"): None,
    ("gemini", "gemini-2.5-flash-preview-09-2025"): date(2026, 2, 17),
    ("gemini", "gemini-2.5-flash-image"): date(2026, 10, 2),
    ("gemini", "gemini-2.5-flash-image-preview"): date(2026, 1, 15),
    ("gemini", "gemini-2.5-flash-lite"): None,
    ("gemini", "gemini-2.5-flash-lite-preview-09-2025"): date(2026, 3, 31),
    ("gemini", "gemini-2.5-flash-native-audio-preview-12-2025"): None,
    ("gemini", "gemini-2.0-flash"): date(2026, 6, 1),
    ("gemini", "gemini-2.0-flash-001"): date(2026, 6, 1),
    ("gemini", "gemini-2.0-flash-lite"): date(2026, 6, 1),
    ("gemini", "gemini-2.0-flash-lite-001"): date(2026, 6, 1),
    ("gemini", "gemini-2.0-flash-live-001"): date(2025, 12, 9),
    ("gemini", "gemini-2.0-flash-preview-image-generation"): date(2025, 11, 14),
    ("gemini", "gemini-embedding-2"): None,
    ("gemini", "gemini-embedding-2-preview"): date(2026, 8, 10),
    ("gemini", "gemini-embedding-001"): date(2028, 5, 14),
    ("gemini", "text-embedding-004"): date(2026, 1, 14),
    ("gemini", "embedding-001"): date(2025, 10, 30),
}


def announced_shutdown(provider: str, model: str) -> tuple[bool, date | None]:
    """What the vendor announced about a model's shutdown.

    Args:
        provider: LIA provider id.
        model: LIA model name.

    Returns:
        ``(True, date)`` when the vendor announced one, ``(True, None)`` when it
        lists the model with no shutdown announced, ``(False, None)`` when the
        table does not hold the model (the registries then decide).
    """
    key = (provider, model)
    if key not in VENDOR_SHUTDOWNS:
        return False, None
    return True, VENDOR_SHUTDOWNS[key]


__all__ = [
    "GEMINI_DEPRECATIONS_READ_ON",
    "GEMINI_DEPRECATIONS_URL",
    "VENDOR_SHUTDOWNS",
    "announced_shutdown",
]
