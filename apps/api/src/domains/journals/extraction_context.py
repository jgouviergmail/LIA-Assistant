"""Conversation and evidence rendering for journal extraction, without writes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from src.core.config import settings
from src.domains.journals.constants import JOURNAL_EXTRACTION_MESSAGE_MAX_CHARS
from src.domains.shared.extraction_targets import find_last_user_message, is_synthetic_message
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from src.domains.journals.models import JournalEntry
    from src.domains.journals.service import JournalService

logger = get_logger(__name__)


async def _maybe_build_inner_state_section(user_id: str) -> str:
    """Build the 'inner state' section from the assistant's psyche (ADR-079, commit 3).

    Reads ``PsycheState.last_appraisal`` (a JSONB blob holding valence, arousal,
    mood_label, dominant emotions, quality, resonance) and renders it as a
    compact prompt section so the journal LLM can ground its directives in
    LIA's own affective state at the turn that just ended.

    Returns an empty string when:
    - Psyche feature is disabled (system or user level)
    - The user has no psyche state yet (first interactions)
    - Any error occurs (graceful degradation)

    Args:
        user_id: Owner user UUID as string.

    Returns:
        A "## YOUR INNER STATE THIS TURN" section or an empty string.
    """
    if not getattr(settings, "psyche_enabled", False):
        return ""
    try:
        from sqlalchemy import select

        from src.domains.psyche.models import PsycheState
        from src.infrastructure.database.session import get_db_context

        async with get_db_context() as db:
            from src.domains.users.models import User

            user_result = await db.execute(
                select(User.psyche_enabled).where(User.id == UUID(user_id))
            )
            user_psyche_enabled = user_result.scalar_one_or_none()
            if not user_psyche_enabled:
                return ""

            state_result = await db.execute(
                select(PsycheState.last_appraisal).where(PsycheState.user_id == UUID(user_id))
            )
            appraisal = state_result.scalar_one_or_none()

        if not appraisal or not isinstance(appraisal, dict):
            return ""

        return _render_inner_state(appraisal)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "journal_inner_state_load_failed",
            user_id=user_id,
            error=str(exc),
        )
        return ""


def _render_inner_state(appraisal: dict[str, Any]) -> str:
    valence = appraisal.get("valence")
    arousal = appraisal.get("arousal")
    mood_label = appraisal.get("mood_label")
    emotions = appraisal.get("emotions") or []
    quality = appraisal.get("quality")
    resonance = appraisal.get("resonance")

    # Compact line — never reproduce raw values verbatim, just summarize
    parts: list[str] = []
    if mood_label:
        parts.append(f"mood: {mood_label}")
    if isinstance(valence, int | float):
        parts.append(f"valence: {valence:+.2f}")
    if isinstance(arousal, int | float):
        parts.append(f"arousal: {arousal:+.2f}")
    if isinstance(quality, int | float):
        parts.append(f"self-quality: {quality:.2f}")
    if isinstance(resonance, int | float):
        parts.append(f"resonance: {resonance:.2f}")
    emo_str = ""
    if isinstance(emotions, list) and emotions:
        emo_str = " | emotions: " + ", ".join(str(e) for e in emotions[:5])

    if not parts and not emo_str:
        return ""

    return (
        "## YOUR INNER STATE THIS TURN (your own psyche, not the user's)\n"
        f"{' | '.join(parts)}{emo_str}\n"
        "Use this to write situated reflections (e.g. 'I noticed I felt frustration "
        "and may have been sharper than I intended — be more patient when this returns'). "
        "Never attribute these states to the user. Never reference them in your reply."
    )


async def _build_previous_turn_directives_section(
    user_id: str,
    previous_turn_injected_ids: list[str],
    *,
    expected_revisions: dict[str, int] | None = None,
    entry_revisions: dict[str, int] | None = None,
    entry_levels: dict[str, str] | None = None,
) -> tuple[str, set[str]]:
    """Build the deferred self-evaluation section for the extraction prompt.

    Loads the entries that were injected at turn T-1 and renders them as a
    block the LLM can use to observe the user's reaction at turn T (visible
    in the conversation excerpt) and signal `evidence_outcome` accordingly.

    Returns:
        ``(section, verified_ids)`` — the rendered block (empty string when
        there is nothing to evaluate: conversation reset, first turn, or all
        IDs disappeared between T-1 and T) and the ownership-verified entry
        ids it lists. The caller feeds these ids to the hallucinated-id
        filter: without them, an evidence signal targeting a T-1 directive
        outside the semantic/recent prefilter was silently dropped as
        hallucinated (audit B-01, 2026-08-19 — latent while journals hold
        ≤3 entries, structural beyond).
    """
    if not previous_turn_injected_ids:
        return "", set()

    try:
        from src.infrastructure.database import get_db_context

        async with get_db_context() as db:
            from src.domains.journals.service import JournalService

            service = JournalService(db)
            entries = await _load_previous_entries(
                service,
                user_id,
                previous_turn_injected_ids,
                expected_revisions,
                entry_revisions,
                entry_levels,
            )

        if not entries:
            return "", set()

        return _render_previous_entries(entries), {str(entry.id) for entry in entries}
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning(
            "journal_previous_turn_directives_load_failed",
            user_id=user_id,
            error=str(exc),
        )
        return "", set()


async def _matching_previous_entry(
    service: JournalService, user_id: str, raw_id: str, expected: dict[str, int] | None
) -> JournalEntry | None:
    try:
        identifier = UUID(raw_id)
    except ValueError:
        return None
    entry = await service.repo.get_by_id(identifier)
    if entry is None or str(entry.user_id) != user_id:
        return None
    # Diagnostic callers may inspect legacy checkpoints; runtime extraction
    # always supplies a map, so no absent or changed version is verified.
    if expected is not None and expected.get(raw_id) != entry.revision:
        return None
    return entry


async def _load_previous_entries(
    service: JournalService,
    user_id: str,
    ids: list[str],
    expected_revisions: dict[str, int] | None,
    entry_revisions: dict[str, int] | None,
    entry_levels: dict[str, str] | None,
) -> list[JournalEntry]:
    entries: list[JournalEntry] = []
    for raw_id in ids:
        entry = await _matching_previous_entry(service, user_id, raw_id, expected_revisions)
        if entry is None:
            continue
        entries.append(entry)
        if entry_revisions is not None:
            entry_revisions[str(entry.id)] = entry.revision
        if entry_levels is not None:
            entry_levels[str(entry.id)] = entry.level
    return entries


def _render_previous_entries(entries: list[JournalEntry]) -> str:
    from src.domains.agents.prompts.prompt_loader import load_prompt

    scaffolding = load_prompt("journal_self_eval_directives_section").rstrip()
    lines = [scaffolding, ""]
    for entry in entries:
        hints = f" | hints: {', '.join(entry.search_hints)}" if entry.search_hints else ""
        lines.append(
            f"[id={entry.id} | conf={entry.confidence} "
            f"| ev={entry.evidence_count}/co={entry.contradiction_count} "
            f"| {entry.theme}{hints}] **{entry.title}** — {entry.content}"
        )
    return "\n".join(lines)


async def _maybe_build_health_context(user_id: str) -> str:
    """Return the Health Metrics context block for the journal prompt.

    Mirror of the memory extractor helper — empty string when the global
    feature flag is off, the user has not opted in, or health data is
    unavailable. The prompt template includes a ``{health_context}``
    placeholder flagged ``(optional)``.
    """
    from src.core.config import settings as global_settings
    from src.core.constants import HEALTH_METRICS_USER_TOGGLE_ATTR

    if not getattr(global_settings, "health_metrics_enabled", False):
        return ""

    try:
        from src.infrastructure.database.session import get_db_context

        async with get_db_context() as db:
            from src.domains.health_metrics.service import HealthMetricsService
            from src.domains.users.repository import UserRepository

            user = await UserRepository(db).get_by_id(UUID(user_id))
            if user is None or not getattr(user, HEALTH_METRICS_USER_TOGGLE_ATTR, False):
                return ""
            service = HealthMetricsService(db)
            return await service.build_health_context_for_prompt(UUID(user_id))
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "journal_extraction_health_context_failed",
            user_id=user_id,
            error=str(exc),
        )
        return ""


def _format_messages_for_extraction(messages: list[BaseMessage]) -> str:
    """Format messages for the extraction prompt context.

    Converts LangChain messages to readable conversation format.
    Historical messages are bounded; the latest genuine human turn is whole.
    Its final corrections define the scope of any rule we retain.

    Args:
        messages: List of conversation messages

    Returns:
        Formatted conversation string
    """
    lines = []
    max_chars = JOURNAL_EXTRACTION_MESSAGE_MAX_CHARS
    _last_user, last_user_index = find_last_user_message(messages)

    for index, msg in enumerate(messages):
        if isinstance(msg, HumanMessage):
            # System-fabricated HITL scaffolding is not conversation.
            if is_synthetic_message(msg):
                continue
            prefix = "USER"
        elif isinstance(msg, AIMessage):
            # Skip proactive notifications (interest/heartbeat) — not meaningful for journals
            if msg.additional_kwargs.get("proactive_notification"):
                continue
            prefix = "ASSISTANT"
        else:
            continue  # Skip tool messages, system messages

        content = str(msg.text)
        if index != last_user_index and len(content) > max_chars:
            content = content[:max_chars] + "..."

        lines.append(f"{prefix}: {content}")

    return "\n".join(lines)


def _format_existing_entries_for_context(entries: list[JournalEntry]) -> str:
    """Format existing journal entries for the extraction prompt.

    After semantic pre-filter, we have ~13 entries max (10 semantic + 3 recent).
    All entries are shown in full with IDs in headers and the full epistemic
    metadata so the LLM can reason about which directives have been validated,
    contradicted, or never injected — and update them accordingly.

    The metadata exposed:
        - created: when the entry was first written
        - last_inj: when it was last used in a prompt (or "never")
        - uses: how many times it has been injected
        - conf: epistemic status (low/medium/high)
        - ev/co: evidence and contradiction counters from deferred self-evaluation

    Args:
        entries: Pre-filtered entries (semantic + recent, deduplicated)

    Returns:
        Formatted entries string for prompt injection
    """
    if not entries:
        return "No existing entries yet."

    entry_lines = []
    for entry in entries:
        created_str = entry.created_at.strftime("%Y-%m-%d")
        last_inj_str = (
            entry.last_injected_at.strftime("%Y-%m-%d") if entry.last_injected_at else "never"
        )
        hints_str = f" | hints: {', '.join(entry.search_hints)}" if entry.search_hints else ""
        entry_lines.append(
            f"[id={entry.id} | created={created_str} | last_inj={last_inj_str} "
            f"| uses={entry.injection_count} | conf={entry.confidence} "
            f"| ev={entry.evidence_count}/co={entry.contradiction_count} "
            f"| level={entry.level} "
            f"| {entry.theme} | {entry.mood}{hints_str}] "
            f"**{entry.title}** — {entry.content}"
        )

    return "\n".join(entry_lines)
