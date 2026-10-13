"""Repair, validate and prepare maintenance actions, then apply them without provider calls."""

from enum import Enum
from typing import Any, Literal, cast
from uuid import UUID

from src.domains.journals.consolidation_output import (
    MaintenanceAction,
    MaintenanceOutput,
    changed_entry_ids,
)
from src.domains.journals.models import JournalEntry, JournalEntryLevel
from src.domains.journals.service import JournalService, prepare_embeddings
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

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


def repair_maintenance(output: MaintenanceOutput, entries: list[JournalEntry]) -> MaintenanceOutput:
    """Apply an abstraction at the level its supports carry, never refuse the batch.

    One synthesis citing immature rules used to void the whole paid consolidation —
    its maintenance AND its portrait (measured 2026-10-12 c: 2 runs of 8 on the
    measurement persona). The level is what the evidence decides, exactly like the
    confidence ``_confidence`` lowers instead of refusing (ADR-184): a new entry is
    created at L1, an update keeps the entry's level, and a rewrite of a validated
    L2/L3 keeps its words. Every other refusal of ``validate_maintenance`` stays.

    Args:
        output: The parsed proposal.
        entries: The snapshot's active entries.

    Returns:
        ``output`` itself when nothing needed a repair, else a repaired copy.
    """
    by_id = {str(entry.id): entry for entry in entries}
    changed_ids = changed_entry_ids(output)
    actions: list[MaintenanceAction] = []
    repairs = {"created_at_l1": 0, "level_kept": 0, "words_kept": 0}
    for action in output.actions:
        repaired, kind = _repaired_abstraction(action, by_id, changed_ids)
        actions.append(repaired)
        if kind is not None:
            repairs[kind] += 1
    if not any(repairs.values()):
        return output
    logger.info(
        "journal_maintenance_abstractions_repaired",
        repaired=sum(repairs.values()),
        **repairs,
    )
    return output.model_copy(update={"actions": actions})


def _repaired_abstraction(
    action: MaintenanceAction, by_id: dict[str, JournalEntry], changed_ids: set[str]
) -> tuple[MaintenanceAction, str | None]:
    """The action at the level its supports carry, and which repair it took (None: none)."""
    if action.action not in ("create", "update"):
        return action, None
    previous = by_id.get(action.entry_id or "")
    if action.action == "update" and previous is None:
        return action, None  # an unknown entry is the validation's refusal, not a level
    level = action.level.value if action.level else (previous.level if previous else "L1")
    if not _new_abstraction(action, previous, level) or _supports_carry(action, by_id, changed_ids):
        return action, None
    if previous is None:
        created = action.model_copy(update={"level": JournalEntryLevel.L1, "support_ids": []})
        return created, "created_at_l1"
    if previous.level in ("L2", "L3") and action.content not in (None, previous.content):
        # The words of a validated abstraction stay what its supports validated.
        kept = action.model_copy(
            update={"level": None, "content": None, "title": None, "support_ids": []}
        )
        return kept, "words_kept"
    return action.model_copy(update={"level": None, "support_ids": []}), "level_kept"


def _supports_carry(
    action: MaintenanceAction, by_id: dict[str, JournalEntry], changed_ids: set[str]
) -> bool:
    """Whether the cited supports carry the abstraction (the validation's own rule)."""
    try:
        _validate_supports(action, by_id, changed_ids)
    except ValueError:
        return False
    return True


def admit_maintenance(
    output: MaintenanceOutput, entries: list[JournalEntry], max_entry_chars: int
) -> MaintenanceOutput:
    """Drop the actions this snapshot refuses, one by one; the batch goes on.

    One refused action used to void the whole paid consolidation, its other
    actions and its portrait included (2026-10-13). Each action is checked by the
    validation's own rule and dropped alone, counted with what the parser
    rejected. Dropping only shrinks the set of entries the batch changes, so what
    stays validates as a whole (the settlement checks it again). Call it once, on
    the parser's output: the proposal indices are derived from its rejections.

    Args:
        output: The parsed (and repaired) proposal.
        entries: The snapshot's active entries.
        max_entry_chars: The account's complete-entry limit.

    Returns:
        ``output`` itself when the snapshot refused nothing, else the admitted copy.

    Raises:
        ValueError: Every proposed action was refused and the answer carries no
            portrait claims — nothing of it can be used.
    """
    by_id = {str(entry.id): entry for entry in entries}
    changed_ids = changed_entry_ids(output)
    admitted: list[MaintenanceAction] = []
    refused: list[dict[str, Any]] = []
    for index, action in zip(_proposal_indices(output), output.actions, strict=True):
        try:
            _validate_action(action, by_id, changed_ids, max_entry_chars)
        except ValueError as exc:
            refused.append({"action_index": index, "reason": str(exc)})
            continue
        admitted.append(action)
    rejected = sorted(
        [*output.rejected_actions, *refused], key=lambda item: int(item["action_index"])
    )
    if rejected and not admitted and output.portrait_claims is None:
        raise ValueError("every maintenance action was refused")
    if rejected:
        logger.warning(
            "journal_maintenance_actions_dropped",
            proposed=len(admitted) + len(rejected),
            dropped=len(rejected),
            reasons=sorted({str(item["reason"]) for item in rejected}),
        )
    if not refused:
        return output
    return output.model_copy(update={"actions": admitted, "rejected_actions": rejected})


def _proposal_indices(output: MaintenanceOutput) -> list[int]:
    """The proposal index of each readable action: the positions the parser kept."""
    rejected = {int(item["action_index"]) for item in output.rejected_actions}
    total = len(output.actions) + len(rejected)
    return [index for index in range(total) if index not in rejected]


def validate_maintenance(
    output: MaintenanceOutput, entries: list[JournalEntry], max_entry_chars: int
) -> None:
    """Refuse semantic errors before embedding preparation incurs spend."""
    by_id = {str(entry.id): entry for entry in entries}
    changed_ids = changed_entry_ids(output)
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
