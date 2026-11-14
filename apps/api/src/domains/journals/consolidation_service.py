"""
Periodic journal consolidation service.

Runs as an APScheduler background task to review and maintain journal entries.
The assistant autonomously manages its own journals: deepening reflections,
merging similar entries, summarizing verbose ones, and cleaning up obsolete notes.

Key design decisions:
- Loads ALL active entries for full review (unlike extraction which is targeted)
- Optional conversation history analysis (user-configurable, higher cost)
- Size enforcement: if over limit, the prompt instructs cleanup
- Uses JournalService for CRUD (char_count + embedding consistency)
- Token tracking via TrackingContext (real costs)
- ONE run per consolidation: the model call, every embedding its actions write,
  and its row in the decision register — LIA's own initiative, filed once the
  model answered (ADR-263 amendment 2026-09-27; before, 84 consolidations in twelve days
  billed their call and their embeddings under two runs each and reached the
  register not once)
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from functools import lru_cache
from time import time
from typing import Any, Final
from uuid import UUID, uuid4

from src.core.config import settings
from src.core.i18n import get_language_name, normalize_language
from src.core.llm_config_helper import (
    get_effective_context_window_for_slot,
    get_llm_config_for_agent,
)
from src.core.prompt_store import parse_prompt_sections, read_prompt_file
from src.domains.agents.effects.decision_recorder import record_decision_once
from src.domains.agents.effects.decisions import out_of_turn_decision
from src.domains.agents.effects.models import DecisionOutcome, EffectSource
from src.domains.journals.consolidation_controls import (
    ConsolidationCompletionUnknown,
    ConsolidationControlRefused,
)
from src.domains.journals.consolidation_entries import format_all_entries as _format_all_entries
from src.domains.journals.consolidation_lifecycle import (
    ConsolidationAttempt,
    ConsolidationSnapshot,
    claim_consolidation,
    consolidation_bound_seconds,
    current_snapshot,
    finish_attempt,
)
from src.domains.journals.consolidation_output import (
    MaintenanceOutput,
)
from src.domains.journals.consolidation_output import (
    parse_maintenance_output as _parse_consolidation_result,
)
from src.domains.journals.consolidation_settlement import settle_maintenance
from src.domains.journals.constants import JOURNAL_ENTRY_CONTENT_MAX_LENGTH
from src.domains.journals.conversation_sources import (
    build_usage_patterns_section as _build_usage_patterns_section,
)
from src.domains.journals.conversation_sources import (
    load_conversation_history as _load_conversation_history,
)
from src.domains.journals.conversation_sources import (
    render_usage_patterns_section as render_usage_patterns_section,
)
from src.domains.journals.extraction_service import (
    _persist_journal_tokens,
    _update_user_last_cost,
)
from src.domains.journals.maintenance_actions import admit_maintenance, repair_maintenance
from src.domains.journals.portrait_diagnostics import (
    log_consolidation_failure,
    log_consolidation_rejection,
)
from src.domains.journals.portrait_sources import build_portrait_source_sections
from src.domains.journals.prompt_builders import build_consolidation_prompt
from src.infrastructure.llm.factory import get_llm
from src.infrastructure.llm.invoke_helpers import invoke_with_instrumentation
from src.infrastructure.llm.token_capture import TokenCaptureHandler
from src.infrastructure.llm.usage_metadata import model_name_of, model_name_of_response
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.proactive.tracking import settle_known_billing

logger = get_logger(__name__)

#: The route a consolidation reads as in the decision register.
CONSOLIDATION_ROUTE: Final[str] = "journal_consolidation"


@lru_cache(maxsize=1)
def _consolidation_lines() -> dict[str, str]:
    """Size-management lines of the consolidation prompt, read once from the store."""
    return dict(parse_prompt_sections(read_prompt_file("journal_consolidation_lines"), 2))


@lru_cache(maxsize=1)
def _scaffold_lines() -> dict[str, str]:
    """The INPUT sections' scaffolds (headers, lines, directives), read once."""
    return dict(parse_prompt_sections(read_prompt_file("journal_portrait_source_lines"), 2))


def render_health_signals_section(block: str) -> str:
    """The health block around what the health service produced (pure).

    Args:
        block: The health context lines.

    Returns:
        The section text.
    """
    lines = _scaffold_lines()
    return "\n".join([lines["health_header"], block, lines["health_directive"]])


def size_directives(usage_pct: float) -> tuple[str, str]:
    """The size warning and the management instruction for a measured usage.

    Args:
        usage_pct: Journal size as a percentage of the limit.

    Returns:
        ``(warning, instruction)`` — the warning is empty under 80 %.
    """
    lines = _consolidation_lines()
    if usage_pct > 100:
        return lines["size_exceeded"], lines["size_reduce"]
    if usage_pct > 80:
        return lines["size_approaching"], lines["size_reduce"]
    return "", lines["size_within"]


async def _persist_compiled_portrait(
    user_id: UUID,
    portrait_full: str | None,
    portrait_brief: str | None,
    *,
    provenance: dict[str, Any] | None = None,
) -> None:
    """Persist the compiled portrait pair on the user record.

    Both fields are optional. If only one is provided, the other is left
    untouched. Updates ``journal_portrait_compiled_at`` to NOW() whenever at
    least one portrait was supplied — and writes the provenance in the SAME
    update, so the words and their sources travel together (part B): a run
    that produced no portrait leaves both untouched.

    Args:
        user_id: Owner user UUID.
        portrait_full: Compiled full portrait or None.
        portrait_brief: Compiled brief portrait or None.
        provenance: What the portrait was compiled from (a NEW dict — the
            JSONB column is reassigned, never mutated in place).
    """
    if not portrait_full and not portrait_brief:
        return
    try:
        from sqlalchemy import select

        from src.domains.users.models import User
        from src.infrastructure.database import get_db_context

        async with get_db_context() as db:
            res = await db.execute(select(User).where(User.id == user_id))
            user = res.scalar_one_or_none()
            if not user:
                return
            if portrait_full:
                user.journal_portrait_full = portrait_full
            if portrait_brief:
                user.journal_portrait_brief = portrait_brief
            if provenance is not None:
                user.journal_portrait_sources = dict(provenance)
            user.journal_portrait_compiled_at = datetime.now(UTC)
            await db.commit()

        logger.info(
            "journal_portrait_persisted",
            user_id=str(user_id),
            full_chars=len(portrait_full or ""),
            brief_chars=len(portrait_brief or ""),
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "journal_portrait_persistence_failed",
            user_id=str(user_id),
            error=str(exc),
        )


async def _stamp_last_consolidated(user_id: UUID) -> None:
    """Mark the user's consolidation cooldown as consumed.

    Called on EVERY completed run, including runs whose LLM answer contained no
    maintenance action. The scheduler's eligibility gate reads this column, so
    skipping the stamp on a no-action run left the user permanently eligible and
    the consolidation LLM re-ran at every tick — measured in dev on 2026-07-27,
    where the portrait had been recompiled 40 h after the last stamp, i.e. eight
    wasted runs at ``journal_consolidation_interval_hours=5``.

    Args:
        user_id: Owner user UUID.
    """
    from sqlalchemy import select

    from src.domains.users.models import User
    from src.infrastructure.database import get_db_context

    async with get_db_context() as db:
        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if user:
            user.journal_last_consolidated_at = datetime.now(UTC)
            await db.commit()


async def _maybe_build_health_signals_section(user_id: UUID) -> str:
    """Return the Health Metrics block for the consolidation prompt.

    Returns an empty string when the global feature flag is off, the user
    has not opted into Health Metrics assistant integrations, or their
    history is empty. The prompt template uses ``{health_signals_section}``
    as an optional placeholder.

    Args:
        user_id: Owner user UUID.

    Returns:
        A "## HEALTH SIGNALS" section or an empty string.
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

            user = await UserRepository(db).get_by_id(user_id)
            if user is None or not getattr(user, HEALTH_METRICS_USER_TOGGLE_ATTR, False):
                return ""
            service = HealthMetricsService(db)
            block = await service.build_health_context_for_prompt(user_id)
            if not block:
                return ""
            return render_health_signals_section(block)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "journal_consolidation_health_context_failed",
            user_id=str(user_id),
            error=str(exc),
        )
        return ""


def _size_directives_for(total_chars: int, max_total_chars: int) -> tuple[str, str]:
    usage_pct = (total_chars / max_total_chars * 100) if max_total_chars > 0 else 0
    return size_directives(usage_pct)


async def _conversation_section(user_id: UUID, since: datetime | None, *, enabled: bool) -> str:
    if not enabled:
        return ""
    history = await _load_conversation_history(
        user_id=user_id,
        since=since,
        max_messages=settings.journal_consolidation_history_max_messages,
        max_days=settings.journal_consolidation_history_max_days,
    )
    if not history:
        return ""
    return history


def _sources_unavailable(provenance: dict[str, Any]) -> bool:
    return any(
        source.get("status") == "unavailable" and source.get("reason") != "over_budget"
        for source in provenance.get("sources", {}).values()
    )


def _validated_model_output(result: Any, text: str) -> MaintenanceOutput:
    from src.infrastructure.llm.output_truncation import is_output_truncated

    if is_output_truncated(result):
        return MaintenanceOutput(error="provider output was truncated")
    return _parse_consolidation_result(text)


async def _finish_consolidation_attempt(
    user_id: UUID,
    snapshot: ConsolidationSnapshot | None,
    status: str,
    attempt: ConsolidationAttempt | None,
) -> None:
    if snapshot is None:
        return
    if attempt is not None:
        attempt.status = status
    await finish_attempt(user_id, snapshot, status)


async def _current_personality_code(db: Any, user: Any) -> str | None:
    """Resolve the personality captured by the current account preferences."""
    from src.domains.personalities.service import PersonalityService

    personality_id = getattr(user, "personality_id", None)
    if personality_id is None:
        return None
    personality = await PersonalityService(db).get_by_id(personality_id)
    return personality.code if personality else None


async def _run_consolidation(
    user_id: UUID,
    personality_instruction: str | None,
    personality_code: str | None,
    user_language: str,
    consolidation_with_history: bool = False,
    max_total_chars: int = 40000,
    max_entry_chars: int = JOURNAL_ENTRY_CONTENT_MAX_LENGTH,
    last_consolidated_at: datetime | None = None,
    *,
    manual: bool = False,
    attempt: ConsolidationAttempt | None = None,
) -> int:
    """
    Run journal consolidation for a single user.

    The LLM reviews all active entries and decides what maintenance is needed:
    deepen, merge, create, summarize, or delete entries.

    Args:
        user_id: User UUID
        personality_instruction: Active personality prompt text
        personality_code: Active personality code (e.g., "cynic")
        user_language: User's configured language
        consolidation_with_history: Whether to include conversation history
        max_total_chars: User's configured max total characters
        max_entry_chars: User's configured max characters per entry (prompt constraint)
        last_consolidated_at: Timestamp of previous consolidation (for history lookback)

    Returns:
        Number of actions applied
    """
    from src.infrastructure.database import get_db_context

    run_id = f"journal_consolidation_{uuid4().hex}"
    started_at = datetime.now(UTC)
    model_answered = False
    failed = False
    snapshot = None
    status = "failed"
    result = None
    capture = None
    model_name = ""
    llm_started_at = 0.0
    try:
        snapshot = await claim_consolidation(user_id, uuid4(), manual=manual, attempt=attempt)
        if snapshot is None:
            return 0
        # Load all active entries
        async with get_db_context() as db:
            from src.domains.journals.service import JournalService

            user = await current_snapshot(db, user_id, snapshot, manual=manual)
            if user is None:
                status = "stale"
                return 0
            # Caller preferences may already be stale when the lease is taken.
            user_language = normalize_language(getattr(user, "language", user_language))
            consolidation_with_history = bool(
                getattr(user, "journal_consolidation_with_history", consolidation_with_history)
            )
            max_total_chars = getattr(user, "journal_max_total_chars", max_total_chars)
            max_entry_chars = getattr(user, "journal_max_entry_chars", max_entry_chars)
            last_consolidated_at = getattr(
                user, "journal_last_consolidated_at", last_consolidated_at
            )
            personality_code = await _current_personality_code(db, user)
            service = JournalService(db)
            entries = await service.get_all_active(user_id)
            total_chars = await service.repo.get_total_chars(user_id)

        # Format entries for prompt
        all_entries_text = _format_all_entries(entries)

        # Size warning
        size_warning, size_management_instruction = _size_directives_for(
            total_chars, max_total_chars
        )

        # Observed usage patterns (factual, lightweight — no LLM, no PII reproduction)
        usage_patterns_section = await _build_usage_patterns_section(user_id)

        # Optional conversation history
        conversation_history_section = await _conversation_section(
            user_id, last_consolidated_at, enabled=consolidation_with_history
        )

        # Current datetime
        current_datetime = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

        # Health Metrics signals — empty string when disabled / no data.
        health_signals_section = await _maybe_build_health_signals_section(user_id)

        # The portrait sources (part B, nine since 2026-10-12), each under its own
        # gates, whole, under one share of the slot's window, with the provenance
        # the portrait will be persisted with.
        context_window = get_effective_context_window_for_slot("journal_consolidation")
        sources = await build_portrait_source_sections(
            user_id,
            user_language,
            journal_entries=len(entries),
            window_tokens=context_window,
        )
        if _sources_unavailable(sources.provenance):
            failed = True
            status = "sources_unavailable"
            return 0

        # Build prompt (shared renderer — see domains/journals/prompt_builders.py)
        prompt = build_consolidation_prompt(
            all_entries=all_entries_text,
            current_chars=total_chars,
            max_chars=max_total_chars,
            size_warning=size_warning,
            current_datetime=current_datetime,
            conversation_history_section=conversation_history_section,
            usage_patterns_section=usage_patterns_section,
            # The model reads the language's NAME, never a code (ADR-284).
            language_name=get_language_name(user_language),
            max_entry_chars=max_entry_chars,
            size_management_instruction=size_management_instruction,
            health_signals_section=health_signals_section,
            personality_code=personality_code,
            portrait_sources=sources.sections,
        )

        # Recheck the same consent/source snapshot immediately before paying.
        async with get_db_context() as db:
            if await current_snapshot(db, user_id, snapshot, manual=manual) is None:
                status = "stale"
                return 0
        # Call LLM
        requested_model = get_llm_config_for_agent(settings, "journal_consolidation").model
        llm = get_llm("journal_consolidation")
        configured_model = model_name_of(llm) or requested_model
        llm_started_at = time()
        from src.infrastructure.cache.pricing_cache import capture_pricing_snapshot

        pricing_snapshot = capture_pricing_snapshot()
        capture = TokenCaptureHandler(configured_model)
        known_calls_before = len(capture.get_billing_records(configured_model))
        try:
            result = await invoke_with_instrumentation(
                llm=llm,
                llm_type="journal_consolidation",
                messages=prompt,
                user_id=str(user_id),
                config={"callbacks": [capture]},
            )
            # Billing may fail next; the received answer still owns a journal act.
            model_answered = True
        finally:
            model_name = model_name_of_response(result) or configured_model
            if result is not None:
                capture.ensure_response_record(
                    result,
                    model_name=model_name,
                    started_at=llm_started_at,
                    snapshot=pricing_snapshot,
                    known_calls_before=known_calls_before,
                )
            await settle_known_billing(
                _persist_journal_tokens(
                    user_id=str(user_id),
                    session_id="consolidation",
                    conversation_id=None,
                    result=result,
                    model_name=model_name,
                    parent_run_id=run_id,
                    node_name="journal_consolidation",
                    duration_ms=(time() - llm_started_at) * 1000,
                    started_at=llm_started_at,
                    requested_model=requested_model,
                    capture=capture,
                    failed=result is None,
                )
            )
        result_content = result.text

        parsed = _validated_model_output(result, result_content)
        if not parsed.valid:
            failed = True
            status = "invalid_output"
            logger.warning(
                "journal_consolidation_invalid_output", user_id=str(user_id), reason=parsed.error
            )
            return 0
        # An abstraction its supports cannot carry is filed at the level they carry,
        # and an action the snapshot refuses is dropped alone: neither voids the paid
        # batch any more (measured 2026-10-12 c and 2026-10-13, ADR-343).
        parsed = repair_maintenance(parsed, entries)
        parsed = admit_maintenance(parsed, entries, max_entry_chars)
        from src.infrastructure.llm.embedding_context import (
            get_embedding_context,
            restore_embedding_context,
            set_embedding_context,
        )

        previous_embedding_context = get_embedding_context()
        set_embedding_context(
            user_id=str(user_id), session_id="journal_consolidation", run_id=run_id
        )
        try:
            applied_count, status = await settle_maintenance(
                user_id,
                snapshot,
                parsed,
                entries,
                sources,
                manual=manual,
                personality_code=personality_code,
                max_entry_chars=max_entry_chars,
            )
        finally:
            restore_embedding_context(previous_embedding_context)
        failed = status not in ("success", "no_op")
        logger.info(
            "journal_consolidation_completed",
            user_id=str(user_id),
            actions_applied=applied_count,
            status=status,
        )
        return applied_count

    except ConsolidationControlRefused, ConsolidationCompletionUnknown:
        failed = True
        status = "failed"
        raise
    except ValueError as e:
        failed = True
        status = "invalid_output"
        log_consolidation_rejection(logger, user_id, e)
        return 0
    except Exception as e:
        failed = True
        status = "failed"
        log_consolidation_failure(logger, user_id, e)
        return 0
    except asyncio.CancelledError:
        failed = True
        status = "failed"
        raise
    finally:
        known_spend = capture is not None and bool(capture.get_billing_records(model_name))
        if capture is not None and (result is not None or known_spend):
            # Both sequential phases belong to this run and to its cost display.
            await _update_user_last_cost(
                str(user_id),
                result,
                model_name,
                source="consolidation",
                started_at=llm_started_at,
                capture=capture,
            )
        await _finish_consolidation_attempt(user_id, snapshot, status, attempt)
        # No answer, no known spend: no turn (the register's own rule).
        if model_answered or known_spend:
            await _file_consolidation(user_id, run_id, started_at, failed=failed)


async def consolidate_journals_for_user(
    user_id: UUID,
    personality_instruction: str | None,
    personality_code: str | None,
    user_language: str,
    consolidation_with_history: bool = False,
    max_total_chars: int = 40000,
    max_entry_chars: int = JOURNAL_ENTRY_CONTENT_MAX_LENGTH,
    last_consolidated_at: datetime | None = None,
    *,
    manual: bool = False,
    attempt: ConsolidationAttempt | None = None,
) -> int:
    """Run bounded maintenance behind the same account lease for every caller."""
    try:
        async with asyncio.timeout(consolidation_bound_seconds()):
            return await _run_consolidation(
                user_id,
                personality_instruction,
                personality_code,
                user_language,
                consolidation_with_history,
                max_total_chars,
                max_entry_chars,
                last_consolidated_at,
                manual=manual,
                attempt=attempt,
            )
    except TimeoutError:
        logger.warning("journal_consolidation_timeout", user_id=str(user_id))
        return 0


async def _file_consolidation(
    user_id: UUID, run_id: str, started_at: datetime, *, failed: bool
) -> None:
    """File one consolidation in the decision register, as LIA's own act. Never raises.

    Args:
        user_id: Whose journal was consolidated.
        run_id: The run its model call and its embeddings were billed under.
        started_at: When the consolidation began.
        failed: Whether it broke after the model answered.
    """
    decision = out_of_turn_decision(
        run_id=run_id, user_id=user_id, thread_id=run_id, source=EffectSource.PROACTIVE.value
    )
    decision.route = CONSOLIDATION_ROUTE
    decision.started_at = started_at
    decision.outcome = DecisionOutcome.FAILED if failed else DecisionOutcome.ANSWERED
    await record_decision_once(decision)
