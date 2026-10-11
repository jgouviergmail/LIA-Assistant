"""
Background journal extraction service.

Analyzes conversations post-response to extract journal entries for the assistant.
Runs as a fire-and-forget background task (same pattern as memory_extractor.py).

Key design decisions:
- Targeted analysis: only last user message + 4 context messages (not full conversation)
- Loads a subset of existing entries for context (not all — consolidation handles full review)
- Uses JournalService for CRUD (ensures char_count + embedding consistency)
- Complete JSON batch validation before any mutation (no partial recovery)
- Token tracking via TrackingContext (real costs, integrated into dashboard)
"""

from __future__ import annotations

from contextlib import suppress
from typing import Any
from uuid import UUID

from langchain_core.messages import BaseMessage

from src.core.config import settings
from src.core.i18n import get_language_name, resolve_language
from src.core.llm_config_helper import get_llm_config_for_agent
from src.core.prompt_layout import single_call_messages
from src.core.prompt_store import parse_prompt_sections, read_prompt_file
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.domains.agents.services.jev_extraction_observer import (
    observe_extractor,
    start_extraction_observation,
)
from src.domains.agents.utils.json_parser import extract_json_from_llm_response
from src.domains.feature_switches.registry import PlatformCapability, is_capability_enabled
from src.domains.journals.billing import (
    _persist_journal_tokens,
    _update_user_last_cost,
)
from src.domains.journals.constants import (
    JOURNAL_ENTRY_CONTENT_MAX_LENGTH,
    JOURNAL_EXTRACTION_CONTEXT_MESSAGES,
    JOURNAL_EXTRACTION_DEDUP_MIN_SCORE,
    JOURNAL_EXTRACTION_MESSAGE_MAX_CHARS,
    JOURNAL_EXTRACTION_RECENT_LIMIT,
    JOURNAL_EXTRACTION_SEMANTIC_LIMIT,
)
from src.domains.journals.extraction_actions import (
    extraction_event_key,
    validate_extraction_actions,
)
from src.domains.journals.extraction_context import (
    _build_previous_turn_directives_section as _build_previous_turn_directives_section,
)
from src.domains.journals.extraction_context import (
    _format_existing_entries_for_context as _format_existing_entries_for_context,
)
from src.domains.journals.extraction_context import (
    _format_messages_for_extraction as _format_messages_for_extraction,
)
from src.domains.journals.extraction_context import (
    _maybe_build_health_context as _maybe_build_health_context,
)
from src.domains.journals.extraction_context import (
    _maybe_build_inner_state_section as _maybe_build_inner_state_section,
)
from src.domains.journals.extraction_debug_store import (
    pop_extraction_debug,
    store_extraction_debug,
)
from src.domains.journals.extraction_output import (
    parse_extraction_output as _parse_extraction_output,
)
from src.domains.journals.extraction_preparation import (
    load_embedding_inputs,
    prepare_embedding_inputs,
)
from src.domains.journals.extraction_settlement import (
    ExtractionSettlement,
    apply_extraction_actions,
)
from src.domains.journals.prompt_builders import build_introspection_prompt
from src.domains.journals.schemas import ConsolidationParseResult, ExtractedJournalEntry
from src.domains.journals.self_eval import (
    count_evidence_signals,
    record_self_eval_funnel,
)
from src.domains.llm_config.jev_registry import JevUsage
from src.domains.shared.extraction_targets import (
    find_last_user_message,
)
from src.domains.shared.provenance_capture import record_origin
from src.domains.users.extraction_consent import ExtractionKind, snapshot_extraction_consent
from src.infrastructure.llm.factory import get_llm
from src.infrastructure.llm.invoke_helpers import invoke_with_instrumentation
from src.infrastructure.llm.output_truncation import is_output_truncated
from src.infrastructure.llm.token_capture import TokenCaptureHandler
from src.infrastructure.llm.usage_metadata import (
    model_name_of,
    model_name_of_response,
)
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_journals import (
    journal_extraction_duration_seconds,
)
from src.infrastructure.proactive.tracking import settle_known_billing

logger = get_logger(__name__)


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

    Legacy diagnostic parser; runtime settlement uses extraction_output instead.
    Keeps tolerant recovery for historical diagnostic callers and fixtures.
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
# Main Extraction Function
# =============================================================================


@observe_extractor(JevUsage.OBSERVE_JOURNAL)
async def extract_journal_entry_background(
    user_id: str,
    messages: list[BaseMessage],
    session_id: str,
    personality_instruction: str | None = None,
    conversation_id: str | None = None,
    user_language: str | None = None,
    parent_run_id: str | None = None,
    assistant_response: str | None = None,
    query_embedding: list[float] | None = None,
    previous_turn_injected_ids: list[str] | None = None,
    previous_turn_injected_revisions: dict[str, int] | None = None,
) -> int:
    """
    Background journal extraction from conversation.

    Analyzes the LAST user message + context to determine if
    a journal entry should be written. Deterministic validation bounds the
    model's proposals before settlement.

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
        previous_turn_injected_revisions: Exact revisions exposed at T-1;
            an absent or changed revision cannot receive a reaction signal.

    Returns:
        Number of actions applied (create/update/delete)
    """
    try:
        # Guard: system feature flag
        if not settings.journals_enabled or not settings.journal_extraction_enabled:
            logger.debug("journal_extraction_disabled", user_id=user_id)
            return 0
        if not await is_capability_enabled(PlatformCapability.JOURNALS):
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
        from src.infrastructure.database import get_db_context

        run_context = runtime_context_if_running()
        if run_context is not None and run_context.extraction_revision is None:
            return 0
        async with get_db_context() as db:
            extraction_revision = await snapshot_extraction_consent(
                db,
                UUID(user_id),
                ExtractionKind.JOURNAL,
                expected_revision=run_context.extraction_revision if run_context else None,
            )
        if extraction_revision is None:
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

        # Build size warning — the words are the consolidation's own lines (ADR-284)
        usage_pct = (total_chars / max_total_chars * 100) if max_total_chars > 0 else 0
        size_lines = dict(parse_prompt_sections(read_prompt_file("journal_consolidation_lines"), 2))
        size_warning = ""
        if usage_pct > 100:
            size_warning = size_lines["size_exceeded"]
        elif usage_pct > 80:
            size_warning = size_lines["size_approaching"]

        # Health Metrics context — empty string unless the user opted in.
        health_context = await _maybe_build_health_context(user_id)

        # Inner state — the assistant's own psyche at this turn (ADR-079, commit 3).
        inner_state_section = await _maybe_build_inner_state_section(user_id)

        # Deferred self-evaluation section (ADR-079).
        # Lists the directives that were injected at the PREVIOUS turn so the LLM
        # can observe how the user reacted (in the conversation it now sees) and
        # signal `evidence_outcome=evidence|contradiction` on update actions.
        previous_entry_revisions: dict[str, int] = {}
        entry_levels = {str(e.id): e.level for e in existing_entries}
        loaded_revisions = {str(e.id): e.revision for e in existing_entries}
        (
            previous_turn_directives_section,
            previous_turn_verified_ids,
        ) = await _build_previous_turn_directives_section(
            user_id=user_id,
            previous_turn_injected_ids=previous_turn_injected_ids or [],
            expected_revisions=previous_turn_injected_revisions or {},
            entry_revisions=previous_entry_revisions,
            entry_levels=entry_levels,
        )
        record_self_eval_funnel(previous_turn_injected_ids or [], previous_turn_directives_section)

        # Build prompt (shared renderer — see domains/journals/prompt_builders.py)
        prompt = build_introspection_prompt(
            conversation=conversation,
            existing_entries=existing_context,
            current_chars=total_chars,
            max_chars=max_total_chars,
            size_warning=size_warning,
            # The model reads the language's NAME, never a code (ADR-284).
            language_name=get_language_name(resolve_language(user_language)),
            max_entry_chars=max_entry_chars,
            health_context=health_context,
            inner_state_section=inner_state_section,
            previous_turn_directives_section=previous_turn_directives_section,
            personality_code=personality_code,
        )

        # Call LLM
        if not await is_capability_enabled(PlatformCapability.JOURNALS):
            return 0
        async with get_db_context() as db:
            if (
                await snapshot_extraction_consent(
                    db, UUID(user_id), ExtractionKind.JOURNAL, expected_revision=extraction_revision
                )
                is None
            ):
                return 0
        import time as _time

        requested_model = get_llm_config_for_agent(settings, "journal_extraction").model
        llm = get_llm("journal_extraction")
        configured_model = model_name_of(llm) or requested_model
        _llm_start = _time.time()
        from src.infrastructure.cache.pricing_cache import capture_pricing_snapshot

        pricing_snapshot = capture_pricing_snapshot()
        capture = TokenCaptureHandler(configured_model)
        result = None
        observation = start_extraction_observation(prompt)
        try:
            result = await invoke_with_instrumentation(
                llm=llm,
                llm_type="journal_extraction",
                # The fixed rules and persona as the system message, the turn's
                # data as the question: a prompt cache reads the first (ADR-309).
                messages=single_call_messages(prompt),
                session_id=session_id,
                user_id=user_id,
                config={"callbacks": [capture]},
            )
        except Exception:
            with suppress(Exception):
                journal_extraction_duration_seconds.labels(outcome="error").observe(
                    _time.time() - _llm_start
                )
            raise
        finally:
            model_name = model_name_of_response(result) or configured_model
            if result is not None:
                capture.ensure_response_record(
                    result, model_name=model_name, started_at=_llm_start, snapshot=pricing_snapshot
                )
            await settle_known_billing(
                _persist_journal_tokens(
                    user_id=user_id,
                    session_id=session_id,
                    conversation_id=conversation_id,
                    result=result,
                    model_name=model_name,
                    parent_run_id=parent_run_id,
                    duration_ms=(_time.time() - _llm_start) * 1000,
                    started_at=_llm_start,
                    requested_model=requested_model,
                    capture=capture,
                    failed=result is None,
                )
            )
        _llm_duration_ms = (_time.time() - _llm_start) * 1000
        observation.set_output(result.text)
        with suppress(Exception):
            journal_extraction_duration_seconds.labels(outcome="success").observe(
                _llm_duration_ms / 1000.0
            )
        result_content = result.text

        # Update user's last cost for Settings UI
        await _update_user_last_cost(
            user_id, result, model_name, source="extraction", started_at=_llm_start, capture=capture
        )

        if is_output_truncated(result):
            logger.warning("journal_extraction_output_truncated", user_id=user_id)
            return 0

        # Parse result
        actions = _parse_extraction_output(result_content, max_entry_chars=max_entry_chars)
        # Funnel: signals counted BEFORE the hallucinated-id filter below, so
        # a dropped signal stays visible as a signaled-vs-applied gap.
        count_evidence_signals(actions)

        if not actions:
            logger.debug("journal_extraction_no_actions", user_id=user_id)
            if parent_run_id:
                store_extraction_debug(
                    parent_run_id,
                    {
                        "actions_parsed": 0,
                        "actions_applied": 0,
                        "entries": [],
                    },
                )
            return 0

        # Filter out hallucinated entry_ids. The known set is the union of the
        # prefiltered entries AND the ownership-verified T-1 directives: an
        # evidence signal on a directive outside the prefilter must not be
        # dropped as hallucinated (audit B-01, 2026-08-19).
        known_ids = set(loaded_revisions) | previous_turn_verified_ids
        actions = validate_extraction_actions(
            actions,
            known_ids=known_ids,
            previous_verified_ids=previous_turn_verified_ids,
            entry_levels=entry_levels,
            max_entry_chars=max_entry_chars,
        )
        if not actions:
            return 0
        event_key = extraction_event_key(user_id, session_id, last_human_message, parent_run_id)

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
            settlement_context = ExtractionSettlement(
                user_id=user_id,
                session_id=session_id,
                personality_code=personality_code,
                max_entry_chars=max_entry_chars,
                event_key=event_key,
                known_ids=known_ids,
                previous_verified_ids=previous_turn_verified_ids,
                loaded_revisions=loaded_revisions,
                previous_revisions=previous_entry_revisions,
            )
            async with get_db_context() as db:
                if not await is_capability_enabled(PlatformCapability.JOURNALS):
                    return 0
                if (
                    await snapshot_extraction_consent(
                        db,
                        UUID(user_id),
                        ExtractionKind.JOURNAL,
                        expected_revision=extraction_revision,
                    )
                    is None
                ):
                    return 0
                inputs = await load_embedding_inputs(
                    JournalService(db), actions, settlement_context
                )
            settlement_context.prepared_inputs.update(
                {
                    action.entry_id: item
                    for action, item in zip(actions, inputs, strict=True)
                    if action.action == "update" and action.entry_id
                }
            )
            # The read session has closed. No connection or owner lock is held
            # while the provider prepares embeddings under this run's attribution.
            prepared = await prepare_embedding_inputs(inputs)
            async with get_db_context() as db:
                if not await is_capability_enabled(PlatformCapability.JOURNALS):
                    return 0
                if (
                    await snapshot_extraction_consent(
                        db,
                        UUID(user_id),
                        ExtractionKind.JOURNAL,
                        expected_revision=extraction_revision,
                        lock=True,
                    )
                    is None
                ):
                    return 0
                service = JournalService(db)

                applied_count = await apply_extraction_actions(
                    db,
                    service,
                    actions,
                    settlement_context,
                    record_origin,
                    prepared,
                )

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

            store_extraction_debug(
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
            pop_extraction_debug(parent_run_id)
        logger.error(
            "journal_extraction_failed",
            user_id=user_id,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        return 0
