"""Deterministic limits on model-proposed journal actions for a single turn."""

from collections import Counter
from hashlib import sha256

from langchain_core.messages import HumanMessage

from src.domains.journals.schemas import ExtractedJournalEntry
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)
_MUTABLE_FIELDS = ("theme", "title", "content", "mood", "search_hints", "confidence", "level")


def extraction_event_key(
    user_id: str, session_id: str, message: HumanMessage, parent_run_id: str | None
) -> str:
    """Identify the source message independently from an SDK or graph attempt."""
    if message.id:
        identity = f"message:{message.id}"
    elif parent_run_id:
        identity = f"run:{parent_run_id}"
    else:
        identity = f"text:{message.text}"
    digest = sha256(f"{user_id}\0{session_id}\0{identity}".encode()).hexdigest()
    return f"journal-turn:{digest}"


def _common_rejection(
    action: ExtractedJournalEntry, counts: Counter[str], max_entry_chars: int
) -> str:
    proposed_level = action.level.value if action.level else None
    if action.entry_id and counts[action.entry_id] != 1:
        return "ambiguous_uuid"
    if action.content is not None and len(action.content) > max_entry_chars:
        return "content_exceeds_user_limit"
    if proposed_level not in (None, "L0", "L1"):
        return "synthesis_level"
    return ""


def _creation_rejection(action: ExtractedJournalEntry, l0_created: int) -> str:
    if action.entry_id:
        return "unexpected_create_id"
    if not (action.theme and action.title and action.content):
        return "incomplete_create"
    if action.level and action.level.value == "L0" and l0_created:
        return "l0_turn_limit"
    return ""


def _filter_mutation(
    action: ExtractedJournalEntry,
    known_ids: set[str],
    previous_verified_ids: set[str],
    synthesis: bool,
) -> tuple[ExtractedJournalEntry, str]:
    if not action.entry_id or action.entry_id not in known_ids:
        return action, "unknown_id"
    if action.action == "delete" and synthesis:
        return action, "synthesis_lifecycle"
    if action.action == "update":
        if action.entry_id not in previous_verified_ids:
            action = action.model_copy(update={"evidence_outcome": None})
        if not action.evidence_outcome and not any(
            getattr(action, field) is not None for field in _MUTABLE_FIELDS
        ):
            return action, "no_permitted_update"
    return action, ""


def validate_extraction_actions(
    actions: list[ExtractedJournalEntry],
    *,
    known_ids: set[str],
    previous_verified_ids: set[str],
    entry_levels: dict[str, str],
    max_entry_chars: int,
) -> list[ExtractedJournalEntry]:
    """Bound creation and refuse ambiguous mutations or unexposed reinforcement.

    Maintenance may still refine L0/L1 without an outcome. L2/L3 syntheses
    are only observed here: consolidation owns their content and lifecycle.
    A repeated UUID is ambiguous even if one action looks safe; none applies.
    """
    counts = Counter(a.entry_id for a in actions if a.entry_id)
    accepted: list[ExtractedJournalEntry] = []
    l0_created = 0
    for action in actions:
        synthesis = entry_levels.get(action.entry_id or "") in ("L2", "L3")
        if action.action == "update" and synthesis:
            action = action.model_copy(update=dict.fromkeys(_MUTABLE_FIELDS))
        reason = _common_rejection(action, counts, max_entry_chars)
        if not reason:
            if action.action == "create":
                reason = _creation_rejection(action, l0_created)
                if not reason:
                    l0_created += int(action.level is not None and action.level.value == "L0")
            else:
                action, reason = _filter_mutation(
                    action, known_ids, previous_verified_ids, synthesis
                )
        if reason:
            logger.info("journal_extraction_action_refused", action=action.action, reason=reason)
        else:
            accepted.append(action)
    return accepted
