"""Turn raw extraction output into validated memory operations.

Split out of ``memory_extractor`` (which sits at its size cap): one
responsibility — parse what the model returned, keep what validates, and report
what it refused **without echoing it**. That last part is not incidental: this
branch is logged at WARNING since 2026-08-28, and a Pydantic message renders
``input_value=...``, which here is the user's own sentence.
"""

from __future__ import annotations

import re

from pydantic import ValidationError

from src.domains.agents.utils.json_parser import extract_json_from_llm_response
from src.domains.memories.schemas import ExtractedMemory
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


_CLASSIFICATION_TOKEN = re.compile(r"^[a-z_]{1,32}$")


def _loggable_token(item: object, field: str) -> str | None:
    """Return a model-provided classification value only when it looks like one.

    ``action`` and ``category`` are what makes a dropped entry diagnosable — a
    drift is greppable precisely because the refused value is printed. But the
    fields come from an LLM: anything can be in them, the user's own sentence
    included. A value that is not a vocabulary token is reported as unexpected
    rather than printed (repo rule: no PII at INFO level or above).

    Args:
        item: The raw extraction entry, of unknown shape.
        field: The classification field to read.

    Returns:
        The token, ``"<unexpected>"`` when the value is not one, or ``None``
        when the field is absent.
    """
    if not isinstance(item, dict):
        return None
    value = item.get(field)
    if value is None:
        return None
    if isinstance(value, str) and _CLASSIFICATION_TOKEN.match(value):
        return value
    return "<unexpected>"


def _validation_failure_summary(exc: Exception) -> list[str]:
    """Describe WHAT failed without repeating WHAT WAS SUBMITTED.

    ``str(ValidationError)`` renders ``input_value=...``; for this parser that
    value is the memory content. Only the field path and the error type are
    kept — which is also the more useful signal: ``category:literal_error`` is
    exactly the vocabulary drift this log line exists to surface.

    Args:
        exc: The exception raised while building an ``ExtractedMemory``.

    Returns:
        One ``"<field>:<error_type>"`` entry per validation error, or the
        exception class name for anything that is not a validation error.
    """
    if not isinstance(exc, ValidationError):
        return [type(exc).__name__]
    return [
        f"{'.'.join(str(part) for part in error['loc']) or '<root>'}:{error['type']}"
        for error in exc.errors()
    ]


def parse_extraction_result(result_text: str) -> list[ExtractedMemory]:
    """Parse LLM extraction result into ExtractedMemory objects.

    Handles common JSON parsing issues and supports both old format
    (no action field → create) and new format (with action field).

    Args:
        result_text: Raw LLM output.

    Returns:
        List of validated ExtractedMemory objects.
    """

    def _parse_items(data: list) -> list[ExtractedMemory]:
        entries = []
        for item in data:
            try:
                entry = ExtractedMemory(**item)
                # Reject create actions missing required content/category
                if entry.action == "create" and (not entry.content or not entry.category):
                    logger.debug(
                        "memory_item_missing_required_fields",
                        item=item,
                        action=entry.action,
                    )
                    continue
                entries.append(entry)
            except Exception as e:
                # WARNING, not debug: this branch is where a vocabulary drift
                # hides. `procedural` was taught by the prompt and rejected
                # here for months (2026-08-28) — every dropped rule looked
                # exactly like "the user said nothing worth remembering".
                # Above DEBUG, nothing submitted may be echoed: the field that
                # failed and how it failed, never the value it carried.
                logger.warning(
                    "memory_item_validation_failed",
                    action=_loggable_token(item, "action"),
                    category=_loggable_token(item, "category"),
                    errors=_validation_failure_summary(e),
                )
                continue
        return entries

    # Central parser handles fences, array extraction, trailing commas and //
    # comments (strict-first, instrumented via json_parse_* with this context).
    result = extract_json_from_llm_response(
        result_text, expected_type=list, context="memory_extraction"
    )
    if not result.success or not isinstance(result.data, list):
        return []
    return _parse_items(result.data)
