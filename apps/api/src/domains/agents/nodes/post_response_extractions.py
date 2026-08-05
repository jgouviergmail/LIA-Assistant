"""Post-response background extractions (fire-and-forget side effects).

Extracted verbatim from ``response_node`` (file-size ratchet — a logical
file never grows): the six background extractions — long-term memory,
interests, open loops (P5, ADR-139), journal, psyche and the recurrence
ledger (P12, ADR-140) — all gated by the single ``is_automated_source`` flag
and each running under its own guard + graceful-degradation try/except. Pure
side effects after state_update; the node is unaffected observably.

Every decision is counted through ``post_response_extraction_scheduled_total``
(L1): a skipped extraction used to be a debug log nobody aggregated, which is
how two production defects stayed invisible.
"""

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING, Any

import structlog

from src.core.config import settings
from src.core.field_names import FIELD_IS_AUTOMATED_SOURCE
from src.domains.agents.constants import STATE_KEY_MESSAGES
from src.domains.agents.services.memory_extractor import extract_memories_background
from src.domains.agents.services.open_loop_extractor import extract_open_loops_background
from src.domains.interests.services import extract_interests_background
from src.infrastructure.async_utils import safe_fire_and_forget
from src.infrastructure.observability.metrics_extractions import (
    post_response_extraction_scheduled_total,
)

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig

    from src.domains.agents.models import MessagesState

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Extraction observability (metric label vocabulary)
# ---------------------------------------------------------------------------
# Every branch of the scheduler below emits exactly one (kind, outcome) pair, so
# a skipped extraction is countable instead of merely logged at debug level.
#
# Not every kind emits every outcome — the guards genuinely differ:
#   memory      : scheduled | automated_source | user_disabled | trivial | no_user | error
#   interests   : scheduled | automated_source | trivial | no_user | error
#   open_loops  : scheduled | automated_source | trivial | feature_disabled | no_user | error
#   journal     : scheduled | automated_source | user_disabled | trivial | no_user | error
#   psyche      : scheduled | automated_source | user_disabled | feature_disabled | trivial
#                 | no_user | error
#   recurrence  : scheduled | automated_source | trivial | feature_disabled
#                 | not_applicable | error
#
# `recurrence` deliberately has no `no_user`: its walrus guard has no else branch,
# and adding one would grow a CC-41 hotspot for an outcome the code never reached.
KIND_MEMORY = "memory"
KIND_INTERESTS = "interests"
KIND_OPEN_LOOPS = "open_loops"
KIND_JOURNAL = "journal"
KIND_PSYCHE = "psyche"
KIND_RECURRENCE = "recurrence"

OUTCOME_SCHEDULED = "scheduled"
OUTCOME_AUTOMATED_SOURCE = "automated_source"
OUTCOME_USER_DISABLED = "user_disabled"
OUTCOME_FEATURE_DISABLED = "feature_disabled"
OUTCOME_TRIVIAL = "trivial"
OUTCOME_NO_USER = "no_user"
OUTCOME_NOT_APPLICABLE = "not_applicable"
OUTCOME_ERROR = "error"


def _record_extraction(kind: str, outcome: str) -> None:
    """Count one extraction decision.

    Args:
        kind: Extraction subsystem; one of the ``KIND_*`` constants.
        outcome: Decision taken; one of the ``OUTCOME_*`` constants.
    """
    # Metrics emission is best-effort: an observability failure must never break
    # the response node (same contract as the rollback counter in
    # infrastructure/database/session.py).
    with suppress(Exception):
        post_response_extraction_scheduled_total.labels(kind=kind, outcome=outcome).inc()


def _record_either(kind: str, condition: bool, when_true: str, when_false: str) -> None:
    """Count a decision whose branch covers two distinct causes.

    Two guards below are disjunctions (``A or B``) that the scheduler cannot split
    without adding a branch to a CC-41 hotspot. The choice is resolved here instead,
    so the metric stays precise while the caller's complexity is unchanged.

    Args:
        kind: Extraction subsystem; one of the ``KIND_*`` constants.
        condition: Discriminator between the two causes.
        when_true: Outcome recorded when ``condition`` holds.
        when_false: Outcome recorded otherwise.
    """
    _record_extraction(kind, when_true if condition else when_false)


def _schedule_post_response_extractions(
    state: MessagesState,
    config: RunnableConfig,
    run_id: str,
    *,
    user_msg_is_trivial: bool,
    personality_instruction: str | None,
    user_message_embedding: Any,
    user_language: str,
    final_content: str,
    previous_journal_injected_ids: list[str],
    psyche_appraisal: Any,
) -> None:
    """Schedule the six post-response background extractions (fire-and-forget).

    Extracted verbatim from ``response_node`` (behavior-preserving): long-term
    memory, interests, open loops, journal, psyche and the recurrence ledger are
    all gated by the single ``_is_automated_source`` flag (computed here from
    config, exactly as before) and each runs under its own guard +
    graceful-degradation try/except. The node is unaffected observably — these
    are pure side effects after state_update.

    Each branch records one ``(kind, outcome)`` pair; see the label vocabulary
    at module level for which outcomes a given kind can emit.

    Args:
        state: Graph state carrying the conversation messages.
        config: RunnableConfig holding the user id, thread id and feature flags.
        run_id: Current run identifier (metric/log correlation, task awaiting).
        user_msg_is_trivial: True when the user's message carries nothing to
            extract ("ok", "merci", an emoji) — every subsystem skips it.
        personality_instruction: Optional personality context for memory/journal.
        user_message_embedding: Pre-computed embedding shared by the consumers.
        user_language: User language for the interest/journal prompts.
        final_content: Assistant response text, consumed by journal extraction.
        previous_journal_injected_ids: Journal entries injected on the previous
            turn, for deferred self-evaluation (T → T+1, ADR-079).
        psyche_appraisal: Parsed self-report from the response, or None.
    """
    user_memory_enabled = config.get("configurable", {}).get("user_memory_enabled", True)
    user_psyche_enabled = config.get("configurable", {}).get("user_psyche_enabled", False)

    # ===================================================================
    # PHASE 4 - LONG-TERM MEMORY EXTRACTION (Background)
    # ===================================================================
    # Extract psychological profile data from conversation asynchronously.
    # Uses safe_fire_and_forget to prevent GC issues with background tasks.
    # Non-blocking: extraction runs after response is returned to user.
    # Check user memory preference before scheduling extraction
    #
    # GUARD: Skip extraction for automated sources (e.g. scheduled actions).
    # Only direct user-typed messages should feed long-term memory / interests /
    # journal / psyche. The signal is an explicit configurable flag set by the
    # caller (scheduled_action_executor passes is_automated_source=True). It is
    # read from `configurable` — NOT metadata — because configurable survives the
    # Langfuse config enrichment (which rebuilds metadata and would drop the key).
    # Proactive notifications (heartbeat, interests) never reach response_node.
    _is_automated_source = bool(
        config.get("configurable", {}).get(FIELD_IS_AUTOMATED_SOURCE, False)
    )

    try:
        # user_memory_enabled already defined above for injection
        if _is_automated_source:
            _record_extraction(KIND_MEMORY, OUTCOME_AUTOMATED_SOURCE)
            logger.info(
                "memory_extraction_skipped_automated_source",
                run_id=run_id,
            )
        elif not user_memory_enabled:
            _record_extraction(KIND_MEMORY, OUTCOME_USER_DISABLED)
            logger.info(
                "memory_extraction_skipped_user_disabled",
                run_id=run_id,
                user_memory_enabled=user_memory_enabled,
            )
        elif user_msg_is_trivial:
            _record_extraction(KIND_MEMORY, OUTCOME_TRIVIAL)
            logger.info(
                "memory_extraction_skipped_trivial",
                run_id=run_id,
            )
        else:
            user_id = config.get("configurable", {}).get("langgraph_user_id")
            thread_id = config.get("configurable", {}).get("thread_id", "unknown")

            if user_id:
                msg_count = len(state.get(STATE_KEY_MESSAGES, []))
                safe_fire_and_forget(
                    extract_memories_background(
                        user_id=user_id,
                        messages=state[STATE_KEY_MESSAGES],
                        session_id=thread_id,
                        personality_instruction=personality_instruction,
                        conversation_id=thread_id,
                        parent_run_id=run_id,
                        query_embedding=user_message_embedding,
                    ),
                    name=f"memory_extraction_{user_id}_{thread_id[:8]}",
                    run_id=run_id,
                )
                _record_extraction(KIND_MEMORY, OUTCOME_SCHEDULED)
                logger.info(
                    "memory_extraction_scheduled",
                    run_id=run_id,
                    user_id=user_id,
                    thread_id=thread_id,
                    message_count=msg_count,
                )
            else:
                _record_extraction(KIND_MEMORY, OUTCOME_NO_USER)
                logger.warning(
                    "memory_extraction_skipped_no_user",
                    run_id=run_id,
                    has_configurable="configurable" in config,
                )
    except (ValueError, KeyError, RuntimeError, AttributeError, ImportError, OSError) as e:
        # Graceful degradation - memory extraction failure must not break response_node
        _record_extraction(KIND_MEMORY, OUTCOME_ERROR)
        logger.error(
            "memory_extraction_scheduling_failed",
            run_id=run_id,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )

    # ===================================================================
    # INTEREST EXTRACTION (Background)
    # ===================================================================
    # Extract user interests from conversation asynchronously.
    # Uses safe_fire_and_forget to prevent GC issues with background tasks.
    # Non-blocking: extraction runs after response is returned to user.
    # GUARD: Same automated source filter as memory extraction above.
    try:
        if _is_automated_source:
            _record_extraction(KIND_INTERESTS, OUTCOME_AUTOMATED_SOURCE)
            logger.info(
                "interest_extraction_skipped_automated_source",
                run_id=run_id,
            )
        elif user_msg_is_trivial:
            _record_extraction(KIND_INTERESTS, OUTCOME_TRIVIAL)
            logger.info(
                "interest_extraction_skipped_trivial",
                run_id=run_id,
            )
        elif not (user_id := config.get("configurable", {}).get("langgraph_user_id")):
            _record_extraction(KIND_INTERESTS, OUTCOME_NO_USER)
            logger.debug(
                "interest_extraction_skipped_no_user",
                run_id=run_id,
            )
        else:
            thread_id = config.get("configurable", {}).get("thread_id", "unknown")
            msg_count = len(state.get(STATE_KEY_MESSAGES, []))
            safe_fire_and_forget(
                extract_interests_background(
                    user_id=user_id,
                    messages=state[STATE_KEY_MESSAGES],
                    session_id=thread_id,
                    conversation_id=thread_id,
                    user_language=user_language,
                    parent_run_id=run_id,  # UPSERT into originating message's token summary
                ),
                name=f"interest_extraction_{user_id}_{thread_id[:8]}",
                run_id=run_id,  # Register for awaiting before SSE done
            )
            _record_extraction(KIND_INTERESTS, OUTCOME_SCHEDULED)
            logger.info(
                "interest_extraction_scheduled",
                run_id=run_id,
                user_id=user_id,
                thread_id=thread_id,
                message_count=msg_count,
            )
    except (ValueError, KeyError, RuntimeError, AttributeError, ImportError, OSError) as e:
        # Graceful degradation - interest extraction failure must not break response_node
        _record_extraction(KIND_INTERESTS, OUTCOME_ERROR)
        logger.error(
            "interest_extraction_scheduling_failed",
            run_id=run_id,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )

    # ===================================================================
    # OPEN LOOP EXTRACTION (Background) — P5, ADR-139
    # ===================================================================
    # Track commitments surfaced in the conversation (things the user owes /
    # is waiting on). Same guards as the sibling extractions; additionally
    # gated by the global OPEN_LOOPS_ENABLED flag (checked here so a disabled
    # deployment never even schedules the task).
    try:
        if _is_automated_source:
            _record_extraction(KIND_OPEN_LOOPS, OUTCOME_AUTOMATED_SOURCE)
            logger.debug("open_loop_extraction_skipped_automated_source", run_id=run_id)
        elif user_msg_is_trivial:
            _record_extraction(KIND_OPEN_LOOPS, OUTCOME_TRIVIAL)
            logger.debug("open_loop_extraction_skipped_trivial", run_id=run_id)
        elif not settings.open_loops_enabled:
            _record_extraction(KIND_OPEN_LOOPS, OUTCOME_FEATURE_DISABLED)
            logger.debug("open_loop_extraction_skipped_disabled", run_id=run_id)
        elif not (user_id := config.get("configurable", {}).get("langgraph_user_id")):
            _record_extraction(KIND_OPEN_LOOPS, OUTCOME_NO_USER)
            logger.debug("open_loop_extraction_skipped_no_user", run_id=run_id)
        else:
            thread_id = config.get("configurable", {}).get("thread_id", "unknown")
            safe_fire_and_forget(
                extract_open_loops_background(
                    user_id=user_id,
                    messages=state[STATE_KEY_MESSAGES],
                    session_id=thread_id,
                    run_id=run_id,
                ),
                name=f"open_loop_extraction_{user_id}_{thread_id[:8]}",
                run_id=run_id,
            )
            _record_extraction(KIND_OPEN_LOOPS, OUTCOME_SCHEDULED)
            logger.info(
                "open_loop_extraction_scheduled",
                run_id=run_id,
                user_id=user_id,
                thread_id=thread_id,
            )
    except (ValueError, KeyError, RuntimeError, AttributeError, ImportError, OSError) as e:
        # Graceful degradation - open-loop extraction failure must not break response_node
        _record_extraction(KIND_OPEN_LOOPS, OUTCOME_ERROR)
        logger.error(
            "open_loop_extraction_scheduling_failed",
            run_id=run_id,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )

    # ===================================================================
    # JOURNAL ENTRY EXTRACTION (Background)
    # ===================================================================
    # Extract journal entries from conversation asynchronously.
    # Uses safe_fire_and_forget to prevent GC issues with background tasks.
    # Non-blocking: extraction runs after response is returned to user.
    # GUARD: Same automated source filter as memory/interest extraction.
    try:
        user_journals_enabled = config.get("configurable", {}).get("user_journals_enabled", False)
        if _is_automated_source:
            _record_extraction(KIND_JOURNAL, OUTCOME_AUTOMATED_SOURCE)
            logger.info(
                "journal_extraction_skipped_automated_source",
                run_id=run_id,
            )
        elif not user_journals_enabled:
            _record_extraction(KIND_JOURNAL, OUTCOME_USER_DISABLED)
            logger.debug(
                "journal_extraction_skipped_user_disabled",
                run_id=run_id,
            )
        elif user_msg_is_trivial:
            _record_extraction(KIND_JOURNAL, OUTCOME_TRIVIAL)
            logger.info(
                "journal_extraction_skipped_trivial",
                run_id=run_id,
            )
        elif not (user_id := config.get("configurable", {}).get("langgraph_user_id")):
            _record_extraction(KIND_JOURNAL, OUTCOME_NO_USER)
            logger.debug(
                "journal_extraction_skipped_no_user",
                run_id=run_id,
            )
        else:
            from src.domains.journals.extraction_service import (
                extract_journal_entry_background,
            )

            thread_id = config.get("configurable", {}).get("thread_id", "unknown")
            msg_count = len(state.get(STATE_KEY_MESSAGES, []))
            safe_fire_and_forget(
                extract_journal_entry_background(
                    user_id=user_id,
                    messages=state[STATE_KEY_MESSAGES],
                    session_id=thread_id,
                    personality_instruction=personality_instruction,
                    conversation_id=thread_id,
                    user_language=user_language,
                    parent_run_id=run_id,
                    assistant_response=final_content,
                    query_embedding=user_message_embedding,
                    previous_turn_injected_ids=previous_journal_injected_ids,
                ),
                name=f"journal_extraction_{user_id}_{thread_id[:8]}",
                run_id=run_id,
            )
            _record_extraction(KIND_JOURNAL, OUTCOME_SCHEDULED)
            logger.info(
                "journal_extraction_scheduled",
                run_id=run_id,
                user_id=user_id,
                thread_id=thread_id,
                message_count=msg_count,
            )
    except (ValueError, KeyError, RuntimeError, AttributeError, ImportError, OSError) as e:
        # Graceful degradation - journal extraction failure must not break response_node
        _record_extraction(KIND_JOURNAL, OUTCOME_ERROR)
        logger.error(
            "journal_extraction_scheduling_failed",
            run_id=run_id,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )

    # ===================================================================
    # PSYCHE ENGINE: Post-response update (Background)
    # ===================================================================
    # Applies parsed appraisal to psyche state, updates relationship,
    # self-efficacy, and stores summary for SSE done metadata.
    # Non-blocking: runs as fire-and-forget via safe_fire_and_forget.
    try:
        if _is_automated_source:
            _record_extraction(KIND_PSYCHE, OUTCOME_AUTOMATED_SOURCE)
            logger.info(
                "psyche_update_skipped_automated_source",
                run_id=run_id,
            )
        elif not user_psyche_enabled or not settings.psyche_enabled:
            # Still silent in the logs (no log needed for a disabled feature), but
            # now countable: the user preference and the global flag are told apart.
            _record_either(
                KIND_PSYCHE, user_psyche_enabled, OUTCOME_FEATURE_DISABLED, OUTCOME_USER_DISABLED
            )
        elif user_msg_is_trivial:
            _record_extraction(KIND_PSYCHE, OUTCOME_TRIVIAL)
            logger.debug("psyche_update_skipped_trivial", run_id=run_id)
        elif not (user_id := config.get("configurable", {}).get("langgraph_user_id")):
            _record_extraction(KIND_PSYCHE, OUTCOME_NO_USER)
            logger.debug("psyche_update_skipped_no_user", run_id=run_id)
        else:
            from src.domains.psyche.service import psyche_post_response_background

            safe_fire_and_forget(
                psyche_post_response_background(
                    user_id=user_id,
                    appraisal=psyche_appraisal,
                    run_id=run_id,
                ),
                name=f"psyche_update_{user_id}_{run_id[:8]}",
                run_id=run_id,
            )
            _record_extraction(KIND_PSYCHE, OUTCOME_SCHEDULED)
            logger.info(
                "psyche_update_scheduled",
                run_id=run_id,
                user_id=user_id,
                has_appraisal=psyche_appraisal is not None,
            )
    except Exception as e:
        _record_extraction(KIND_PSYCHE, OUTCOME_ERROR)
        logger.error(
            "psyche_update_scheduling_failed",
            run_id=run_id,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )

    # ===================================================================
    # RECURRENCE LEDGER (Background) — P12, ADR-140
    # ===================================================================
    # Deterministic, no LLM: append one occurrence of the request shape
    # (primary+secondary domains @ local-hour bucket) so the initiative
    # suggestion can detect "same ask, same moment, day after day".
    try:
        from src.domains.agents.analysis.query_intelligence_helpers import get_qi_attr

        qi_intent = get_qi_attr(state, "intent", default=None)
        qi_primary = get_qi_attr(state, "primary_domain", default=None)
        if _is_automated_source or user_msg_is_trivial:
            # same exclusions as the sibling extractions
            _record_either(
                KIND_RECURRENCE,
                _is_automated_source,
                OUTCOME_AUTOMATED_SOURCE,
                OUTCOME_TRIVIAL,
            )
        elif not settings.recurrence_suggestion_enabled:
            _record_extraction(KIND_RECURRENCE, OUTCOME_FEATURE_DISABLED)  # no ledger writes
        elif qi_intent != "action" or not qi_primary:
            # only actionable domain queries can recur into automations
            _record_extraction(KIND_RECURRENCE, OUTCOME_NOT_APPLICABLE)
        elif user_id := config.get("configurable", {}).get("langgraph_user_id"):
            from zoneinfo import ZoneInfo

            from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
            from src.domains.agents.services.recurrence_ledger import (
                build_signature,
                record_occurrence,
            )

            try:
                user_tz = ZoneInfo(state.get("user_timezone", DEFAULT_USER_DISPLAY_TIMEZONE))
            except (KeyError, ValueError, TypeError):
                user_tz = ZoneInfo(DEFAULT_USER_DISPLAY_TIMEZONE)
            from datetime import datetime

            # v2 (ADR-214): the signature is the domains only — the local
            # date and hour are recorded as DATA for the shape locks.
            now_local = datetime.now(user_tz)
            signature = build_signature(
                str(qi_primary),
                list(get_qi_attr(state, "secondary_domains", default=[]) or []),
            )
            safe_fire_and_forget(
                record_occurrence(
                    user_id,
                    signature,
                    local_date=now_local.date(),
                    local_hour=now_local.hour + now_local.minute / 60.0,
                    settings=settings,
                ),
                name=f"recurrence_record_{user_id}",
                run_id=run_id,
            )
            _record_extraction(KIND_RECURRENCE, OUTCOME_SCHEDULED)
    except Exception as e:
        # Graceful degradation — the ledger is advisory
        _record_extraction(KIND_RECURRENCE, OUTCOME_ERROR)
        logger.debug(
            "recurrence_record_scheduling_failed",
            run_id=run_id,
            error=str(e),
        )
