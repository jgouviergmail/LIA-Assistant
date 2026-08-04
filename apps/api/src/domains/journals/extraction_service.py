"""
Background journal extraction service.

Analyzes conversations post-response to extract journal entries for the assistant.
Runs as a fire-and-forget background task (same pattern as memory_extractor.py).

Key design decisions:
- Targeted analysis: only last user message + 4 context messages (not full conversation)
- Loads a subset of existing entries for context (not all — consolidation handles full review)
- Uses JournalService for CRUD (ensures char_count + embedding consistency)
- Robust JSON parsing with fallback (same pattern as memory_extractor)
- Token tracking via TrackingContext (real costs, integrated into dashboard)
"""

from __future__ import annotations

import time as _time
import uuid
from contextlib import suppress
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

if TYPE_CHECKING:

    from src.domains.journals.models import JournalEntry

from src.core.config import settings
from src.core.llm_config_helper import get_llm_config_for_agent
from src.domains.agents.utils.json_parser import extract_json_from_llm_response
from src.domains.journals.constants import (
    JOURNAL_ENTRY_CONTENT_MAX_LENGTH,
    JOURNAL_EXTRACTION_CONTEXT_MESSAGES,
    JOURNAL_EXTRACTION_DEDUP_MIN_SCORE,
    JOURNAL_EXTRACTION_MESSAGE_MAX_CHARS,
    JOURNAL_EXTRACTION_RECENT_LIMIT,
    JOURNAL_EXTRACTION_SEMANTIC_LIMIT,
)
from src.domains.journals.models import JournalEntryMood, JournalEntrySource
from src.domains.journals.prompt_builders import build_introspection_prompt
from src.domains.journals.schemas import ConsolidationParseResult, ExtractedJournalEntry
from src.domains.shared.extraction_targets import (
    find_last_user_message,
    is_synthetic_message,
)
from src.domains.shared.provenance_capture import record_origin
from src.infrastructure.llm.factory import get_llm
from src.infrastructure.llm.invoke_helpers import invoke_with_instrumentation
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_journals import (
    journal_extraction_duration_seconds,
)

logger = get_logger(__name__)


# =============================================================================
# Debug Results Registry (per run_id, consumed by streaming service)
# =============================================================================
# In-process dict storing extraction debug data keyed by run_id.
# Entries are written by extract_journal_entry_background() and consumed
# (popped) by the SSE streaming service via pop_extraction_debug().
# A TTL-based eviction prevents unbounded growth when entries are never
# consumed (e.g., streaming error, debug panel disabled).

_EXTRACTION_DEBUG_TTL_SECONDS: int = 300  # 5 minutes

_extraction_debug_results: dict[str, tuple[float, dict[str, Any]]] = {}


def _evict_stale_debug_entries() -> None:
    """Drop entries older than the TTL — called on BOTH store and pop.

    Store-side eviction is what actually honours the "debug panel
    disabled" promise above: with pop-only eviction, a deployment that
    never opens the panel never pops, and the cache grew one entry per
    turn for the process lifetime (2026-07-22 counter-review).
    """
    now = _time.monotonic()
    stale_keys = [
        k
        for k, (ts, _) in _extraction_debug_results.items()
        if now - ts > _EXTRACTION_DEBUG_TTL_SECONDS
    ]
    for k in stale_keys:
        del _extraction_debug_results[k]


def _store_extraction_debug(run_id: str, data: dict[str, Any]) -> None:
    """Store extraction debug results for a given run_id with a timestamp.

    Args:
        run_id: The pipeline run_id to associate the results with.
        data: Debug dict with actions_parsed, actions_applied, entries.
    """
    _evict_stale_debug_entries()
    _extraction_debug_results[run_id] = (_time.monotonic(), data)


def pop_extraction_debug(run_id: str) -> dict[str, Any] | None:
    """Pop and return extraction debug results for a given run_id.

    Called by the streaming service after await_run_id_tasks to include
    journal extraction details in the debug panel.

    Also evicts stale entries older than ``_EXTRACTION_DEBUG_TTL_SECONDS``
    to prevent unbounded memory growth when entries are never consumed.

    Args:
        run_id: The pipeline run_id whose extraction results to retrieve.

    Returns:
        Debug dict with actions_parsed, actions_applied, entries details,
        or None if no results found for this run_id.
    """
    _evict_stale_debug_entries()
    entry = _extraction_debug_results.pop(run_id, None)
    return entry[1] if entry is not None else None


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
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "journal_inner_state_load_failed",
            user_id=user_id,
            error=str(exc),
        )
        return ""


async def _build_previous_turn_directives_section(
    user_id: str,
    previous_turn_injected_ids: list[str],
) -> str:
    """Build the deferred self-evaluation section for the extraction prompt.

    Loads the entries that were injected at turn T-1 and renders them as a
    block the LLM can use to observe the user's reaction at turn T (visible
    in the conversation excerpt) and signal `evidence_outcome` accordingly.

    Returns an empty string when there is nothing to evaluate (e.g. conversation
    reset, first turn, or all IDs disappeared between T-1 and T).
    """
    if not previous_turn_injected_ids:
        return ""

    try:
        from src.infrastructure.database import get_db_context

        async with get_db_context() as db:
            from src.domains.journals.service import JournalService

            service = JournalService(db)
            entries = []
            for entry_id_str in previous_turn_injected_ids:
                try:
                    entry_uuid = UUID(entry_id_str)
                except ValueError:
                    continue
                entry = await service.repo.get_by_id(entry_uuid)
                if entry and str(entry.user_id) == user_id:
                    entries.append(entry)

        if not entries:
            return ""

        lines = [
            "## DIRECTIVES INJECTED AT THE PREVIOUS TURN",
            (
                "The directives below were injected into your previous response. "
                "Look at the conversation above and consider the user's reaction "
                "AT THE CURRENT TURN. For each directive that was clearly applied "
                "and where you can read a signal in the user's reaction:"
            ),
            (
                "- If the user pushed back, reformulated, or corrected → propose `update` with "
                '`evidence_outcome="contradiction"` on that entry.'
            ),
            (
                "- If the user engaged smoothly, thanked you, or visibly benefited → propose "
                '`update` with `evidence_outcome="evidence"`.'
            ),
            "- If the directive was not relevant to what unfolded → leave it alone (no signal).",
            "- The system increments the counters atomically; you only signal the outcome.",
            "",
        ]
        for entry in entries:
            hints_str = f" | hints: {', '.join(entry.search_hints)}" if entry.search_hints else ""
            lines.append(
                f"[id={entry.id} | conf={entry.confidence} "
                f"| ev={entry.evidence_count}/co={entry.contradiction_count} "
                f"| {entry.theme}{hints_str}] **{entry.title}** — {entry.content}"
            )
        return "\n".join(lines)
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning(
            "journal_previous_turn_directives_load_failed",
            user_id=user_id,
            error=str(exc),
        )
        return ""


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
    Truncates very long messages.

    Args:
        messages: List of conversation messages

    Returns:
        Formatted conversation string
    """
    lines = []
    max_chars = JOURNAL_EXTRACTION_MESSAGE_MAX_CHARS

    for msg in messages:
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
        if len(content) > max_chars:
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


def _parse_consolidation_result(result_text: str) -> ConsolidationParseResult:
    """Parse a consolidation LLM result into actions + compiled portraits.

    The consolidation prompt may return either:
    - A bare JSON array of actions (legacy format, pre-commit 3): backwards
      compatible — portraits remain None.
    - A JSON object ``{actions: [...], portrait_full: "...", portrait_brief: "..."}``
      (commit 3+): the LLM produces the two compiled portrait formats in the
      same call as the maintenance actions.

    Args:
        result_text: Raw LLM output

    Returns:
        ConsolidationParseResult with actions and (optional) portraits.
    """
    actions = _parse_journal_extraction_result(result_text)

    # Best-effort: also parse a JSON object carrying portrait fields. Delegates
    # fence/comment/trailing-comma handling to the central parser; a bare array
    # (legacy format) yields a type mismatch → portraits stay None.
    portrait_full: str | None = None
    portrait_brief: str | None = None
    portrait_result = extract_json_from_llm_response(
        result_text, expected_type=dict, context="journal_portraits"
    )
    if portrait_result.success and isinstance(portrait_result.data, dict):
        pf = portrait_result.data.get("portrait_full")
        pb = portrait_result.data.get("portrait_brief")
        if isinstance(pf, str) and pf.strip():
            portrait_full = pf.strip()
        if isinstance(pb, str) and pb.strip():
            portrait_brief = pb.strip()

    return ConsolidationParseResult(
        actions=actions,
        portrait_full=portrait_full,
        portrait_brief=portrait_brief,
    )


def _parse_journal_extraction_result(result_text: str) -> list[ExtractedJournalEntry]:
    """Parse LLM extraction result into ExtractedJournalEntry objects.

    Robust JSON parsing with fallback (same pattern as memory_extractor).
    Supports BOTH formats:
    - Bare JSON array of action objects (legacy / extraction prompt).
    - JSON object ``{actions: [...], ...}`` (consolidation enriched format
      from commit 3+) — extracts the ``actions`` field.

    Args:
        result_text: Raw LLM output

    Returns:
        List of validated ExtractedJournalEntry objects
    """

    def _parse_items(data: list) -> list[ExtractedJournalEntry]:
        """Validate items against schema, skip invalid ones."""
        entries = []
        for item in data:
            try:
                entry = ExtractedJournalEntry(**item)
                entries.append(entry)
            except Exception as e:
                logger.debug(
                    "journal_extraction_item_validation_failed",
                    item=item,
                    error=str(e),
                )
                continue
        return entries

    # Central parser handles fences, array/object extraction, trailing commas
    # and // comments. expected_type=object accepts BOTH supported shapes: a
    # bare array (legacy) and the enriched {actions: [...]} object.
    result = extract_json_from_llm_response(
        result_text, expected_type=object, context="journal_extraction"
    )
    if not result.success:
        return []
    data = result.data
    if isinstance(data, dict):
        inner = data.get("actions")
        if isinstance(inner, list):
            return _parse_items(inner)
        logger.warning(
            "journal_extraction_object_missing_actions",
            keys=list(data.keys())[:5],
        )
        return []
    if not isinstance(data, list):
        logger.warning(
            "journal_extraction_result_not_list",
            type=type(data).__name__,
        )
        return []
    return _parse_items(data)


# =============================================================================
# Token Persistence (same pattern as _persist_memory_tokens)
# =============================================================================


async def _persist_journal_tokens(
    user_id: str,
    session_id: str,
    conversation_id: str | None,
    result: AIMessage,
    model_name: str,
    parent_run_id: str | None = None,
    node_name: str = "journal_extraction",
    duration_ms: float = 0.0,
) -> None:
    """Persist token usage from journal LLM call to database.

    Uses TrackingContext for real cost calculation and dashboard integration.
    Same pattern as memory_extractor._persist_memory_tokens().

    Args:
        user_id: User ID for statistics
        session_id: Session/thread ID
        conversation_id: Conversation UUID (optional)
        result: AIMessage with usage_metadata
        model_name: LLM model used
        parent_run_id: UPSERT into parent message's summary if provided
        node_name: Node name for cost attribution
    """
    from src.domains.chat.service import TrackingContext

    try:
        usage_metadata = getattr(result, "usage_metadata", None)
        if not usage_metadata:
            return

        raw_input_tokens = usage_metadata.get("input_tokens", 0)
        output_tokens = usage_metadata.get("output_tokens", 0)

        input_details = usage_metadata.get("input_token_details", {})
        cached_tokens = input_details.get("cache_read", 0) if input_details else 0
        input_tokens = raw_input_tokens - cached_tokens

        if input_tokens == 0 and output_tokens == 0:
            return

        run_id = parent_run_id or f"journal_{uuid.uuid4().hex[:12]}"

        conv_uuid: UUID | None = None
        if conversation_id:
            try:
                conv_uuid = UUID(conversation_id)
            except ValueError:
                logger.debug(
                    "journal_invalid_conversation_id",
                    conversation_id=conversation_id,
                )

        async with TrackingContext(
            run_id=run_id,
            user_id=UUID(user_id),
            session_id=session_id,
            conversation_id=conv_uuid,
            auto_commit=False,
        ) as tracker:
            await tracker.record_node_tokens(
                node_name=node_name,
                model_name=model_name,
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
                cached_tokens=cached_tokens,
                duration_ms=duration_ms,
            )
            await tracker.commit()

        logger.info(
            "journal_tokens_persisted",
            user_id=user_id,
            node_name=node_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model_name=model_name,
        )

    except Exception as e:
        logger.error(
            "journal_tokens_persistence_failed",
            user_id=user_id,
            error=str(e),
            exc_info=True,
        )


# =============================================================================
# User Cost Update
# =============================================================================


async def _update_user_last_cost(
    user_id: str,
    result: AIMessage,
    model_name: str,
    source: str = "extraction",
) -> None:
    """Update user's journal_last_cost_* fields for Settings UI display.

    Args:
        user_id: User ID
        result: AIMessage with usage_metadata
        model_name: LLM model used
        source: 'extraction' or 'consolidation'
    """
    from src.infrastructure.database import get_db_context

    try:
        usage_metadata = getattr(result, "usage_metadata", None)
        if not usage_metadata:
            return

        input_tokens = usage_metadata.get("input_tokens", 0)
        output_tokens = usage_metadata.get("output_tokens", 0)

        # Calculate real cost
        from src.infrastructure.cache.pricing_cache import get_cached_cost_usd_eur

        _, cost_eur = get_cached_cost_usd_eur(
            model=model_name,
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
            cached_tokens=0,
        )

        from src.domains.users.models import User

        async with get_db_context() as db:
            from sqlalchemy import select

            result_user = await db.execute(select(User).where(User.id == UUID(user_id)))
            user = result_user.scalar_one_or_none()
            if user:
                user.journal_last_cost_tokens_in = input_tokens
                user.journal_last_cost_tokens_out = output_tokens
                user.journal_last_cost_eur = Decimal(str(cost_eur))
                user.journal_last_cost_at = datetime.now(UTC)
                user.journal_last_cost_source = source
                await db.commit()

    except Exception as e:
        logger.warning(
            "journal_user_cost_update_failed",
            user_id=user_id,
            error=str(e),
        )


# =============================================================================
# Main Extraction Function
# =============================================================================


async def extract_journal_entry_background(
    user_id: str,
    messages: list[BaseMessage],
    session_id: str,
    personality_instruction: str | None = None,
    conversation_id: str | None = None,
    user_language: str = "fr",
    parent_run_id: str | None = None,
    assistant_response: str | None = None,
    query_embedding: list[float] | None = None,
    previous_turn_injected_ids: list[str] | None = None,
) -> int:
    """
    Background journal extraction from conversation.

    Analyzes the LAST user message + context to determine if
    a journal entry should be written. The LLM decides freely
    how many entries to create/update/delete.

    Non-blocking: executed via safe_fire_and_forget.

    Args:
        user_id: Target user ID
        messages: Conversation messages
        session_id: Current session/thread ID
        personality_instruction: Active personality prompt instruction
        conversation_id: Conversation UUID for token cost linking
        user_language: User's language code (fr, en, etc.)
        parent_run_id: Run ID for token UPSERT into originating message
        assistant_response: Assistant's response text for this turn. Passed
            explicitly because the state_update with the AIMessage has not
            been applied by the LangGraph reducer yet at scheduling time.
        previous_turn_injected_ids: UUIDs of journal entries that were
            injected at the PREVIOUS turn (T-1). Enables deferred self-evaluation:
            the LLM observes how the user reacted in this conversation and
            signals `evidence_outcome=evidence|contradiction` on the relevant
            entries. Empty/None on conversation reset (gracefully skipped).

    Returns:
        Number of actions applied (create/update/delete)
    """
    try:
        # Guard: system feature flag
        if not settings.journals_enabled or not settings.journal_extraction_enabled:
            logger.debug("journal_extraction_disabled", user_id=user_id)
            return 0

        # Guard: minimum messages
        if len(messages) < settings.journal_extraction_min_messages:
            logger.debug(
                "journal_extraction_skipped_few_messages",
                user_id=user_id,
                message_count=len(messages),
                min_required=settings.journal_extraction_min_messages,
            )
            return 0

        # Find last HumanMessage + context (same pattern as memory_extractor)
        last_human_message, last_human_index = find_last_user_message(messages)

        if not last_human_message:
            logger.debug("journal_extraction_skipped_no_human_message", user_id=user_id)
            return 0

        # Get context messages around last user message
        context_start = max(0, last_human_index - JOURNAL_EXTRACTION_CONTEXT_MESSAGES)
        context_messages = messages[context_start : last_human_index + 1]

        # Format conversation excerpt
        conversation = _format_messages_for_extraction(context_messages)

        # Append assistant's response (not yet in state at scheduling time)
        if assistant_response:
            truncated_response = assistant_response[:JOURNAL_EXTRACTION_MESSAGE_MAX_CHARS]
            conversation += f"\nASSISTANT: {truncated_response}"

        # Load existing entries for context (recent full + older summary)
        from src.infrastructure.database import get_db_context

        # Load existing entries via semantic pre-filter (replaces get_all_active)
        async with get_db_context() as db:
            from src.domains.journals.service import JournalService

            service = JournalService(db)

            # 1. Semantic search: top N entries close to current conversation
            if query_embedding:
                semantic_results = await service.repo.search_by_relevance(
                    user_id=UUID(user_id),
                    query_embedding=query_embedding,
                    limit=JOURNAL_EXTRACTION_SEMANTIC_LIMIT,
                    min_score=JOURNAL_EXTRACTION_DEDUP_MIN_SCORE,
                )
                semantic_entries = [entry for entry, _ in semantic_results]
            else:
                semantic_entries = []

            # 2. Recent entries: K most recent (temporal continuity)
            recent_entries = await service.repo.get_recent_for_user(
                user_id=UUID(user_id),
                limit=JOURNAL_EXTRACTION_RECENT_LIMIT,
            )

            # 3. Merge + dedup by ID
            seen_ids = {e.id for e in semantic_entries}
            existing_entries = semantic_entries + [
                e for e in recent_entries if e.id not in seen_ids
            ]

            logger.info(
                "journal_extraction_semantic_prefilter",
                user_id=user_id,
                semantic_count=len(semantic_entries),
                recent_count=len(recent_entries),
                merged_count=len(existing_entries),
                has_embedding=query_embedding is not None,
            )

            # 4. total_chars from ALL entries (for global size warning)
            total_chars = await service.repo.get_total_chars(UUID(user_id))

            # Load user's max_total_chars setting
            from sqlalchemy import select

            from src.domains.users.models import User

            user_result = await db.execute(select(User).where(User.id == UUID(user_id)))
            user = user_result.scalar_one_or_none()
            max_total_chars = (
                user.journal_max_total_chars if user else settings.journal_default_max_total_chars
            )
            max_entry_chars = (
                user.journal_max_entry_chars
                if user and hasattr(user, "journal_max_entry_chars")
                else JOURNAL_ENTRY_CONTENT_MAX_LENGTH
            )

            # Load personality code
            personality_code = None
            if user and user.personality_id:
                try:
                    from src.domains.personalities.service import PersonalityService

                    ps = PersonalityService(db)
                    personality = await ps.get_by_id(user.personality_id)
                    if personality:
                        personality_code = personality.code
                except Exception as e:
                    logger.warning(
                        "journal_personality_load_failed",
                        error=str(e),
                        user_id=str(user.id),
                    )

        # Format pre-filtered entries for prompt context (all in full since pre-filtered)
        existing_context = _format_existing_entries_for_context(existing_entries)

        # Build size warning
        usage_pct = (total_chars / max_total_chars * 100) if max_total_chars > 0 else 0
        size_warning = ""
        if usage_pct > 100:
            size_warning = (
                "CRITICAL: You have EXCEEDED the size limit. "
                "You MUST summarize or delete entries to get back within the limit."
            )
        elif usage_pct > 80:
            size_warning = (
                "WARNING: You are approaching the size limit. "
                "Consider summarizing or deleting older entries to make room."
            )

        # Health Metrics context — empty string unless the user opted in.
        health_context = await _maybe_build_health_context(user_id)

        # Inner state — the assistant's own psyche at this turn (ADR-079, commit 3).
        inner_state_section = await _maybe_build_inner_state_section(user_id)

        # Deferred self-evaluation section (ADR-079).
        # Lists the directives that were injected at the PREVIOUS turn so the LLM
        # can observe how the user reacted (in the conversation it now sees) and
        # signal `evidence_outcome=evidence|contradiction` on update actions.
        previous_turn_directives_section = await _build_previous_turn_directives_section(
            user_id=user_id,
            previous_turn_injected_ids=previous_turn_injected_ids or [],
        )

        # Build prompt (shared renderer — see domains/journals/prompt_builders.py)
        prompt = build_introspection_prompt(
            conversation=conversation,
            existing_entries=existing_context,
            current_chars=total_chars,
            max_chars=max_total_chars,
            size_warning=size_warning,
            user_language=user_language,
            max_entry_chars=max_entry_chars,
            health_context=health_context,
            inner_state_section=inner_state_section,
            previous_turn_directives_section=previous_turn_directives_section,
            personality_code=personality_code,
        )

        # Call LLM
        import time as _time

        llm = get_llm("journal_extraction")
        _llm_start = _time.time()
        try:
            result = await invoke_with_instrumentation(
                llm=llm,
                llm_type="journal_extraction",
                messages=prompt,
                session_id=session_id,
                user_id=user_id,
            )
        except Exception:
            with suppress(Exception):
                journal_extraction_duration_seconds.labels(outcome="error").observe(
                    _time.time() - _llm_start
                )
            raise
        _llm_duration_ms = (_time.time() - _llm_start) * 1000
        with suppress(Exception):
            journal_extraction_duration_seconds.labels(outcome="success").observe(
                _llm_duration_ms / 1000.0
            )
        result_content = result.text

        # Persist token usage (use effective config, not defaults — admin overrides matter)
        model_name = get_llm_config_for_agent(settings, "journal_extraction").model
        await _persist_journal_tokens(
            user_id=user_id,
            session_id=session_id,
            conversation_id=conversation_id,
            result=result,
            model_name=model_name,
            parent_run_id=parent_run_id,
            duration_ms=_llm_duration_ms,
        )

        # Update user's last cost for Settings UI
        await _update_user_last_cost(user_id, result, model_name, source="extraction")

        # Parse result
        actions = _parse_journal_extraction_result(result_content)

        if not actions:
            logger.debug("journal_extraction_no_actions", user_id=user_id)
            if parent_run_id:
                _store_extraction_debug(
                    parent_run_id,
                    {
                        "actions_parsed": 0,
                        "actions_applied": 0,
                        "entries": [],
                    },
                )
            return 0

        # Filter out hallucinated entry_ids (only keep IDs that exist in loaded entries)
        known_ids = {str(e.id) for e in existing_entries}
        valid_actions = []
        for action in actions:
            if action.action in ("update", "delete") and action.entry_id:
                if action.entry_id not in known_ids:
                    logger.warning(
                        "journal_extraction_unknown_entry_id",
                        user_id=user_id,
                        action=action.action,
                        entry_id=action.entry_id,
                    )
                    continue
            valid_actions.append(action)

        if len(valid_actions) < len(actions):
            logger.info(
                "journal_extraction_filtered_hallucinated_ids",
                user_id=user_id,
                original_count=len(actions),
                valid_count=len(valid_actions),
                filtered_count=len(actions) - len(valid_actions),
            )
        actions = valid_actions

        # NOTE: Semantic dedup guard removed (v1.14.0) — the LLM now sees existing
        # entries with IDs via semantic pre-filter and can directly update/delete.
        # The guard was redundant and added unnecessary embedding + LLM merge calls.

        # Apply actions via JournalService (handles char_count + embeddings)
        # Set embedding tracking context for cost attribution to parent message
        from src.infrastructure.llm.embedding_context import (
            clear_embedding_context,
            set_embedding_context,
        )

        set_embedding_context(
            user_id=user_id,
            session_id=session_id,
            conversation_id=conversation_id,
            run_id=parent_run_id,
        )

        applied_count = 0
        try:
            async with get_db_context() as db:
                service = JournalService(db)

                for action in actions:
                    # One SAVEPOINT per action — see the same guard in
                    # consolidation_service: without it the first DB-level error
                    # poisons the transaction and every later action fails on the
                    # aborted session, so this `except ... continue` degrades into
                    # all-or-nothing instead of skipping the bad action.
                    try:
                        async with db.begin_nested():
                            if (
                                action.action == "create"
                                and action.theme
                                and action.title
                                and action.content
                            ):
                                created = await service.create_entry(
                                    user_id=UUID(user_id),
                                    theme=action.theme.value,
                                    title=action.title,
                                    content=action.content,
                                    mood=(
                                        action.mood.value
                                        if action.mood
                                        else JournalEntryMood.REFLECTIVE.value
                                    ),
                                    source=JournalEntrySource.CONVERSATION.value,
                                    session_id=session_id,
                                    personality_code=personality_code,
                                    max_entry_chars=max_entry_chars,
                                    search_hints=action.search_hints,
                                    confidence=(
                                        action.confidence.value if action.confidence else "medium"
                                    ),
                                    level=(action.level.value if action.level else "L1"),
                                )
                                # Where this belief came from, as a BOUNDED
                                # pointer (never a copy of the turn): the
                                # entry could state a conclusion and never
                                # what produced it, which is precisely what
                                # makes a wrong one uncorrectable. The
                                # conversation is nulled if the user later
                                # deletes it, leaving a dated tombstone
                                # instead of resurrected content.
                                await record_origin(
                                    db,
                                    user_id=UUID(user_id),
                                    source=session_id,
                                    journal_entry_id=created.id,
                                )
                                applied_count += 1

                            elif action.action == "update" and action.entry_id:
                                entry = await service.repo.get_by_id(UUID(action.entry_id))
                                if entry and str(entry.user_id) == user_id:
                                    await service.update_entry(
                                        entry=entry,
                                        title=action.title,
                                        content=action.content,
                                        mood=(action.mood.value if action.mood else None),
                                        max_entry_chars=max_entry_chars,
                                        search_hints=action.search_hints,
                                        confidence=(
                                            action.confidence.value if action.confidence else None
                                        ),
                                        evidence_outcome=action.evidence_outcome,
                                        level=(action.level.value if action.level else None),
                                        theme=(action.theme.value if action.theme else None),
                                    )
                                    applied_count += 1

                            elif action.action == "delete" and action.entry_id:
                                entry = await service.repo.get_by_id(UUID(action.entry_id))
                                if entry and str(entry.user_id) == user_id:
                                    await service.delete_entry(entry)
                                    applied_count += 1

                    except Exception as e:
                        logger.warning(
                            "journal_extraction_action_failed",
                            user_id=user_id,
                            action=action.action,
                            error=str(e),
                        )
                        continue

                await db.commit()
        finally:
            clear_embedding_context()

        logger.info(
            "journal_extraction_completed",
            user_id=user_id,
            session_id=session_id,
            actions_parsed=len(actions),
            actions_applied=applied_count,
        )

        # Store debug results for the debug panel (consumed by streaming service).
        # For update/delete actions, the LLM often omits unchanged fields (title,
        # content, theme, mood). Fall back to the existing entry's values so the
        # debug panel renders something readable, not just the UUID prefix.
        if parent_run_id:
            existing_by_id = {str(e.id): e for e in existing_entries}
            debug_entries: list[dict[str, Any]] = []
            for a in actions:
                fb_title: str | None = None
                fb_content: str | None = None
                fb_theme: str | None = None
                fb_mood: str | None = None
                if a.action in ("update", "delete") and a.entry_id:
                    existing = existing_by_id.get(a.entry_id)
                    if existing is not None:
                        fb_title = existing.title
                        fb_content = existing.content
                        fb_theme = existing.theme
                        fb_mood = existing.mood

                title = a.title if a.title else fb_title
                content = a.content if a.content else fb_content
                theme_value = (a.theme.value if a.theme else None) or fb_theme
                mood_value = (a.mood.value if a.mood else None) or fb_mood

                debug_entries.append(
                    {
                        "action": a.action,
                        "theme": theme_value,
                        "title": ((title[:30] + "…") if title and len(title) > 30 else title),
                        "full_title": title,
                        "content": content,
                        "mood": mood_value,
                        "entry_id": a.entry_id,
                    }
                )

            _store_extraction_debug(
                parent_run_id,
                {
                    "actions_parsed": len(actions),
                    "actions_applied": applied_count,
                    "entries": debug_entries,
                },
            )

        return applied_count

    except Exception as e:
        # Graceful degradation — extraction failure must never break the response
        # Clean up debug entry to avoid orphaned data in the registry
        if parent_run_id:
            _extraction_debug_results.pop(parent_run_id, None)
        logger.error(
            "journal_extraction_failed",
            user_id=user_id,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        return 0
