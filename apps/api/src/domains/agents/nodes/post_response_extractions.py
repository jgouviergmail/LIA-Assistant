"""Post-response background extractions (fire-and-forget side effects).

Extracted verbatim from ``response_node`` (file-size ratchet — a logical
file never grows): the five background extractions — long-term memory,
interests, open loops (P5, ADR-139), journal and psyche — all gated by the
single ``is_automated_source`` flag and each running under its own guard +
graceful-degradation try/except. Pure side effects after state_update; the
node is unaffected observably.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from src.core.config import settings
from src.core.field_names import FIELD_IS_AUTOMATED_SOURCE
from src.domains.agents.constants import STATE_KEY_MESSAGES
from src.domains.agents.services.memory_extractor import extract_memories_background
from src.domains.agents.services.open_loop_extractor import extract_open_loops_background
from src.domains.interests.services import extract_interests_background
from src.infrastructure.async_utils import safe_fire_and_forget

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig

    from src.domains.agents.models import MessagesState

logger = structlog.get_logger(__name__)


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
    """Schedule the four post-response background extractions (fire-and-forget).

    Extracted verbatim from ``response_node`` (behavior-preserving): long-term
    memory, interests, journal and psyche updates are all gated by the single
    ``_is_automated_source`` flag (computed here from config, exactly as before)
    and each runs under its own guard + graceful-degradation try/except. The node
    is unaffected observably — these are pure side effects after state_update.
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
            logger.info(
                "memory_extraction_skipped_automated_source",
                run_id=run_id,
            )
        elif not user_memory_enabled:
            logger.info(
                "memory_extraction_skipped_user_disabled",
                run_id=run_id,
                user_memory_enabled=user_memory_enabled,
            )
        elif user_msg_is_trivial:
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
                logger.info(
                    "memory_extraction_scheduled",
                    run_id=run_id,
                    user_id=user_id,
                    thread_id=thread_id,
                    message_count=msg_count,
                )
            else:
                logger.warning(
                    "memory_extraction_skipped_no_user",
                    run_id=run_id,
                    has_configurable="configurable" in config,
                )
    except (ValueError, KeyError, RuntimeError, AttributeError, ImportError, OSError) as e:
        # Graceful degradation - memory extraction failure must not break response_node
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
            logger.info(
                "interest_extraction_skipped_automated_source",
                run_id=run_id,
            )
        elif user_msg_is_trivial:
            logger.info(
                "interest_extraction_skipped_trivial",
                run_id=run_id,
            )
        elif not (user_id := config.get("configurable", {}).get("langgraph_user_id")):
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
            logger.info(
                "interest_extraction_scheduled",
                run_id=run_id,
                user_id=user_id,
                thread_id=thread_id,
                message_count=msg_count,
            )
    except (ValueError, KeyError, RuntimeError, AttributeError, ImportError, OSError) as e:
        # Graceful degradation - interest extraction failure must not break response_node
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
            logger.debug("open_loop_extraction_skipped_automated_source", run_id=run_id)
        elif user_msg_is_trivial:
            logger.debug("open_loop_extraction_skipped_trivial", run_id=run_id)
        elif not settings.open_loops_enabled:
            logger.debug("open_loop_extraction_skipped_disabled", run_id=run_id)
        elif not (user_id := config.get("configurable", {}).get("langgraph_user_id")):
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
            logger.info(
                "open_loop_extraction_scheduled",
                run_id=run_id,
                user_id=user_id,
                thread_id=thread_id,
            )
    except (ValueError, KeyError, RuntimeError, AttributeError, ImportError, OSError) as e:
        # Graceful degradation - open-loop extraction failure must not break response_node
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
            logger.info(
                "journal_extraction_skipped_automated_source",
                run_id=run_id,
            )
        elif not user_journals_enabled:
            logger.debug(
                "journal_extraction_skipped_user_disabled",
                run_id=run_id,
            )
        elif user_msg_is_trivial:
            logger.info(
                "journal_extraction_skipped_trivial",
                run_id=run_id,
            )
        elif not (user_id := config.get("configurable", {}).get("langgraph_user_id")):
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
            logger.info(
                "journal_extraction_scheduled",
                run_id=run_id,
                user_id=user_id,
                thread_id=thread_id,
                message_count=msg_count,
            )
    except (ValueError, KeyError, RuntimeError, AttributeError, ImportError, OSError) as e:
        # Graceful degradation - journal extraction failure must not break response_node
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
            logger.info(
                "psyche_update_skipped_automated_source",
                run_id=run_id,
            )
        elif not user_psyche_enabled or not settings.psyche_enabled:
            pass  # Silently skip — no log needed for disabled feature
        elif user_msg_is_trivial:
            logger.debug("psyche_update_skipped_trivial", run_id=run_id)
        elif not (user_id := config.get("configurable", {}).get("langgraph_user_id")):
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
            logger.info(
                "psyche_update_scheduled",
                run_id=run_id,
                user_id=user_id,
                has_appraisal=psyche_appraisal is not None,
            )
    except Exception as e:
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
            pass  # same exclusions as the sibling extractions
        elif not settings.recurrence_suggestion_enabled:
            pass  # flag off — no ledger writes at all
        elif qi_intent != "action" or not qi_primary:
            pass  # only actionable domain queries can recur into automations
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

            signature = build_signature(
                str(qi_primary),
                list(get_qi_attr(state, "secondary_domains", default=[]) or []),
                local_hour=datetime.now(user_tz).hour,
            )
            safe_fire_and_forget(
                record_occurrence(user_id, signature, settings=settings),
                name=f"recurrence_record_{user_id}",
                run_id=run_id,
            )
    except Exception as e:
        # Graceful degradation — the ledger is advisory
        logger.debug(
            "recurrence_record_scheduling_failed",
            run_id=run_id,
            error=str(e),
        )
