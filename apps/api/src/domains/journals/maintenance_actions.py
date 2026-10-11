"""Validate and prepare maintenance actions, then apply them without provider calls."""

from enum import Enum
from typing import Literal, cast
from uuid import UUID

from src.domains.journals.consolidation_output import MaintenanceAction, MaintenanceOutput
from src.domains.journals.models import JournalEntry
from src.domains.journals.service import JournalService, prepare_embeddings

PreparedEmbeddings = tuple[list[float] | None, list[float] | None]


def _mature(entry: JournalEntry | None) -> bool:
    return bool(
        entry
        and entry.confidence == "high"
        and entry.contradiction_count == 0
        and entry.level in ("L1", "L2")
    )


def _new_abstraction(action: MaintenanceAction, previous: JournalEntry | None, level: str) -> bool:
    if level not in ("L2", "L3"):
        return False
    return (
        previous is None
        or previous.level != level
        or (action.content is not None and action.content != previous.content)
    )


def _validate_supports(
    action: MaintenanceAction, by_id: dict[str, JournalEntry], changed_ids: set[str]
) -> None:
    ids = {str(identifier) for identifier in action.support_ids}
    if ids.intersection(changed_ids):
        raise ValueError("synthesis supports must survive this batch unchanged")
    if len(ids) < 2 or not all(_mature(by_id.get(identifier)) for identifier in ids):
        raise ValueError("higher-level synthesis requires multiple independently mature rules")
    propositions = {by_id[identifier].content.strip() for identifier in ids}
    if len(propositions) < 2:
        raise ValueError("synthesis supports must contain distinct complete propositions")


def _validate_merge(
    action: MaintenanceAction, previous: JournalEntry | None, by_id: dict[str, JournalEntry]
) -> None:
    if action.action != "merge":
        return
    assert previous is not None
    for identifier in action.merge_source_ids:
        source = by_id[str(identifier)]
        if (source.content.strip(), source.theme, source.level) != (
            previous.content.strip(),
            previous.theme,
            previous.level,
        ):
            raise ValueError("merge requires equivalent complete propositions, themes and levels")


def _validate_action(
    action: MaintenanceAction, by_id: dict[str, JournalEntry], changed_ids: set[str], limit: int
) -> None:
    if action.entry_id is not None and action.entry_id not in by_id:
        raise ValueError("unknown maintenance entry")
    if any(str(source) not in by_id for source in action.merge_source_ids):
        raise ValueError("unknown merge source")
    if action.content is not None and (not action.content.strip() or len(action.content) > limit):
        raise ValueError("maintenance content exceeds the user's complete-entry limit")
    previous = by_id.get(action.entry_id or "")
    _validate_merge(action, previous, by_id)
    _validate_level(action, previous, by_id, changed_ids)


def _validate_level(
    action: MaintenanceAction,
    previous: JournalEntry | None,
    by_id: dict[str, JournalEntry],
    changed_ids: set[str],
) -> None:
    level = action.level.value if action.level else (previous.level if previous else "L1")
    if _new_abstraction(action, previous, level):
        _validate_supports(action, by_id, changed_ids)
    theme = action.theme.value if action.theme else (previous.theme if previous else None)
    if action.action in ("create", "update") and level == "L3" and theme != "user_observations":
        raise ValueError("method lessons cannot become identity facets")


def validate_maintenance(
    output: MaintenanceOutput, entries: list[JournalEntry], max_entry_chars: int
) -> None:
    """Refuse semantic errors before embedding preparation incurs spend."""
    by_id = {str(entry.id): entry for entry in entries}
    changed_ids = {action.entry_id for action in output.actions if action.entry_id is not None}
    changed_ids.update(
        str(identifier) for action in output.actions for identifier in action.merge_source_ids
    )
    for action in output.actions:
        _validate_action(action, by_id, changed_ids, max_entry_chars)


def _needs_embedding(action: MaintenanceAction, entry: JournalEntry | None) -> bool:
    if action.action == "create":
        return True
    if entry is None:
        return False
    return any(
        value is not None and value != getattr(entry, key)
        for key, value in (
            ("title", action.title),
            ("content", action.content),
            ("search_hints", action.search_hints),
        )
    )


def _text(
    action: MaintenanceAction, entry: JournalEntry | None, key: Literal["title", "content"]
) -> str:
    value = getattr(action, key)
    if value is not None:
        return cast(str, value)
    return cast(str, getattr(entry, key)) if entry else ""


async def prepare_action(
    service: JournalService, action: MaintenanceAction, by_id: dict[str, JournalEntry]
) -> PreparedEmbeddings:
    entry = by_id.get(action.entry_id or "")
    if action.action == "merge":
        assert entry is not None
        return await service.prepare_merge_embeddings(
            entry, [by_id[str(i)] for i in action.merge_source_ids]
        )
    if not _needs_embedding(action, entry):
        return None, None
    hints = action.search_hints
    if hints is None and entry is not None:
        hints = entry.search_hints
    return await prepare_embeddings(
        _text(action, entry, "title"), _text(action, entry, "content"), hints
    )


def _enum(value: Enum | None) -> str | None:
    return str(value.value) if value is not None else None


def _confidence(action: MaintenanceAction, entry: JournalEntry) -> str | None:
    requested = _enum(action.confidence)
    if entry.level in ("L2", "L3") and entry.confidence != "high" and requested == "high":
        return "medium"
    return requested


async def _create(
    service: JournalService,
    action: MaintenanceAction,
    user_id: UUID,
    embeddings: PreparedEmbeddings,
    personality_code: str | None,
    limit: int,
) -> int:
    assert action.theme and action.title and action.content
    await service.create_entry(
        user_id=user_id,
        theme=action.theme.value,
        title=action.title,
        content=action.content,
        mood=_enum(action.mood) or "reflective",
        source="consolidation",
        personality_code=personality_code,
        max_entry_chars=limit,
        search_hints=action.search_hints,
        confidence=_enum(action.confidence) or "medium",
        level=_enum(action.level) or "L1",
        precomputed_embeddings=embeddings,
    )
    return 1


async def _update(
    service: JournalService,
    action: MaintenanceAction,
    entry: JournalEntry,
    embeddings: PreparedEmbeddings,
    revision: int,
    limit: int,
) -> int:
    fields = (
        "revision",
        "title",
        "content",
        "mood",
        "search_hints",
        "confidence",
        "level",
        "theme",
    )
    before = tuple(getattr(entry, key) for key in fields)
    updated = await service.update_entry(
        entry,
        title=action.title,
        content=action.content,
        mood=_enum(action.mood),
        max_entry_chars=limit,
        search_hints=action.search_hints,
        confidence=_confidence(action, entry),
        level=_enum(action.level),
        theme=_enum(action.theme),
        expected_revision=revision,
        precomputed_embeddings=embeddings,
    )
    return int(tuple(getattr(updated, key) for key in fields) != before)


async def apply_action(
    service: JournalService,
    action: MaintenanceAction,
    user_id: UUID,
    by_id: dict[str, JournalEntry],
    revisions: dict[str, int],
    embeddings: PreparedEmbeddings,
    *,
    personality_code: str | None,
    limit: int,
) -> int:
    """Return actual mutations, including a checked update that changed nothing."""
    if action.action == "create":
        return await _create(service, action, user_id, embeddings, personality_code, limit)
    entry = by_id[action.entry_id or ""]
    if action.action == "update":
        return await _update(service, action, entry, embeddings, revisions[str(entry.id)], limit)
    if action.action == "delete":
        await service.delete_entry(entry, expected_revision=revisions[str(entry.id)])
        return 1
    await service.merge_entries(
        entry, list(action.merge_source_ids), revisions, precomputed_embeddings=embeddings
    )
    return 1
