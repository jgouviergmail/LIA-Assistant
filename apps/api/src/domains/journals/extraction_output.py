"""Validate one complete extraction batch before any proposed mutation.

Unlike the legacy diagnostic parser, this execution boundary never extracts
a JSON substring, repairs a cut array or skips an invalid item. A complete
Markdown JSON fence is allowed; an ambiguous batch is discarded as a whole.
"""

from typing import Any

from pydantic import ConfigDict, ValidationError

from src.domains.journals.output_json import load_complete_json
from src.domains.journals.schemas import ExtractedJournalEntry
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)
_UPDATE_FIELDS = (
    "theme",
    "title",
    "content",
    "mood",
    "search_hints",
    "confidence",
    "level",
    "evidence_outcome",
)


class ExtractionAction(ExtractedJournalEntry):
    """Unknown mutation fields are malformed output, not harmless commentary."""

    model_config = ConfigDict(extra="forbid")


def _action_array(raw: str) -> list[Any]:
    payload = load_complete_json(raw, allow_fence=True)
    if isinstance(payload, dict):
        if set(payload) != {"actions"}:
            raise ValueError("extraction object must contain actions only")
        payload = payload["actions"]
    if not isinstance(payload, list):
        raise ValueError("complete action array required")
    return payload


def _validate_content(action: ExtractedJournalEntry, max_entry_chars: int) -> None:
    if action.content is not None and (
        not action.content.strip() or len(action.content) > max_entry_chars
    ):
        raise ValueError("content exceeds complete-entry contract")


def _validate_shape(action: ExtractedJournalEntry) -> None:
    if action.action == "create":
        if (
            action.entry_id
            or not (action.theme and action.title and action.content)
            or action.evidence_outcome
        ):
            raise ValueError("incomplete or ambiguous create")
        return
    if not action.entry_id:
        raise ValueError("mutation requires an entry ID")
    has_update = any(getattr(action, field) is not None for field in _UPDATE_FIELDS)
    if action.action == "delete" and has_update:
        raise ValueError("delete cannot carry update fields")
    if action.action == "update" and not has_update:
        raise ValueError("empty update")


def _parse_actions(payload: list[Any], max_entry_chars: int) -> list[ExtractedJournalEntry]:
    actions: list[ExtractedJournalEntry] = []
    seen: set[str] = set()
    for item in payload:
        action = ExtractionAction.model_validate(item)
        if action.entry_id:
            if action.entry_id in seen:
                raise ValueError("repeated UUID across actions")
            seen.add(action.entry_id)
        _validate_content(action, max_entry_chars)
        _validate_shape(action)
        actions.append(action)
    return actions


def parse_extraction_output(raw: str, *, max_entry_chars: int) -> list[ExtractedJournalEntry]:
    """Return all valid actions or none; paid-call accounting belongs to the caller."""
    try:
        return _parse_actions(_action_array(raw), max_entry_chars)
    except (ValueError, TypeError, ValidationError) as exc:
        logger.warning("journal_extraction_invalid_output", error_type=type(exc).__name__)
        return []
