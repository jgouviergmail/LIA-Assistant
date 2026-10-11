"""The same source evidence helpers explain manual changes before provider work."""

from dataclasses import dataclass

from pydantic import JsonValue
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.journals.evidence import (
    _certified_evidence,
    _changed_values,
    _invalidates_portrait,
    _retire_validation,
    effective_confidence,
)
from src.domains.journals.models import JournalEntry
from src.domains.journals.schemas import JournalEntryResponse, JournalEntryUpdate


@dataclass(frozen=True)
class ManualJournalUpdate:
    before: dict[str, JsonValue]
    after: dict[str, JsonValue]
    invalidates_portrait: bool
    needs_embeddings: bool
    changed: bool


async def preview_manual_journal_update(
    db: AsyncSession, current: JournalEntry, patch: JournalEntryUpdate
) -> ManualJournalUpdate:
    raw = patch.model_dump(mode="json", exclude_unset=True, exclude_none=True)
    requested_confidence = raw.pop("confidence", current.confidence)
    if "content" in raw:
        raw["char_count"] = len(patch.content or "")
    values = _changed_values(current, raw)
    replaced = any(name in values for name in ("content", "level", "theme"))
    certified = 0 if replaced else await _certified_evidence(db, current)
    if replaced:
        _retire_validation(current, values, None)
        requested_confidence = "medium"
    final = effective_confidence(
        requested_confidence,
        str(values.get("level", current.level)),
        certified,
        0 if replaced else current.contradiction_count,
    )
    if final != current.confidence:
        values["confidence"] = final
    invalidates = _invalidates_portrait(values, replaced, False, None, current.confidence, final)
    before = JournalEntryResponse.model_validate(current).model_dump(
        mode="json", exclude={"updated_at", "injection_count", "last_injected_at"}
    )
    return ManualJournalUpdate(
        before=before,
        after={**before, **values},
        invalidates_portrait=invalidates,
        needs_embeddings=any(name in values for name in ("title", "content", "search_hints")),
        changed=bool(values),
    )
