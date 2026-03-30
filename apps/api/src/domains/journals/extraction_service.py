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

import json
import re
import time as _time
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

if TYPE_CHECKING:
    from src.domains.journals.models import JournalEntry

from src.core.config import settings
from src.core.llm_config_helper import get_llm_config_for_agent
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.journals.constants import (
    JOURNAL_ENTRY_CONTENT_MAX_LENGTH,
    JOURNAL_EXTRACTION_CONTEXT_MESSAGES,
    JOURNAL_EXTRACTION_DEDUP_MIN_SCORE,
    JOURNAL_EXTRACTION_MESSAGE_MAX_CHARS,
    JOURNAL_EXTRACTION_RECENT_ENTRIES_FULL,
    JOURNAL_EXTRACTION_RECENT_LIMIT,
    JOURNAL_EXTRACTION_SEMANTIC_LIMIT,
)
from src.domains.journals.models import JournalEntryMood, JournalEntrySource
from src.domains.journals.schemas import ExtractedJournalEntry
from src.infrastructure.llm.factory import get_llm
from src.infrastructure.llm.invoke_helpers import invoke_with_instrumentation
from src.infrastructure.observability.logging import get_logger

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


def _store_extraction_debug(run_id: str, data: dict[str, Any]) -> None:
    """Store extraction debug results for a given run_id with a timestamp.

    Args:
        run_id: The pipeline run_id to associate the results with.
        data: Debug dict with actions_parsed, actions_applied, entries.
    """
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
    # Evict stale entries
    now = _time.monotonic()
    stale_keys = [
        k
        for k, (ts, _) in _extraction_debug_results.items()
        if now - ts > _EXTRACTION_DEBUG_TTL_SECONDS
    ]
    for k in stale_keys:
        del _extraction_debug_results[k]

    entry = _extraction_debug_results.pop(run_id, None)
    return entry[1] if entry is not None else None


# =============================================================================
# Prompt Helpers
# =============================================================================


def _get_introspection_prompt() -> str:
    """Load the journal introspection prompt from file."""
    return str(load_prompt("journal_introspection_prompt"))


def _get_analyst_persona_prompt() -> str:
    """Load the journal analyst persona prompt from file."""
    return str(load_prompt("journal_analyst_persona"))


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
            prefix = "USER"
        elif isinstance(msg, AIMessage):
            # Skip proactive notifications (interest/heartbeat) — not meaningful for journals
            if msg.additional_kwargs.get("proactive_notification"):
                continue
            prefix = "ASSISTANT"
        else:
            continue  # Skip tool messages, system messages

        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        if len(content) > max_chars:
            content = content[:max_chars] + "..."

        lines.append(f"{prefix}: {content}")

    return "\n".join(lines)


def _format_existing_entries_for_context(
    entries: list[JournalEntry],
    full_count: int = JOURNAL_EXTRACTION_RECENT_ENTRIES_FULL,
) -> str:
    """Format existing journal entries for the extraction prompt.

    After semantic pre-filter, we only have ~13 entries max (10 semantic + 3 recent).
    All entries are shown in full with IDs in headers (no separate ID table needed).

    Args:
        entries: Pre-filtered entries (semantic + recent, deduplicated)
        full_count: Number of entries to show in full (all if <= this)

    Returns:
        Formatted entries string for prompt injection
    """
    if not entries:
        return "No existing entries yet."

    entry_lines = []
    for i, entry in enumerate(entries):
        date_str = entry.created_at.strftime("%Y-%m-%d")
        if i < full_count:
            # Full content (all entries after pre-filter are shown in full)
            hints_str = f" | hints: {', '.join(entry.search_hints)}" if entry.search_hints else ""
            entry_lines.append(
                f"[id={entry.id} | {date_str} | {entry.theme} | {entry.mood}{hints_str}] "
                f"**{entry.title}** — {entry.content}"
            )
        else:
            # Compact summary for overflow (unlikely with pre-filter but safe)
            entry_lines.append(f"[id={entry.id} | {date_str} | {entry.theme}] {entry.title}")

    return "\n".join(entry_lines)


def _parse_journal_extraction_result(result_text: str) -> list[ExtractedJournalEntry]:
    """Parse LLM extraction result into ExtractedJournalEntry objects.

    Robust JSON parsing with fallback (same pattern as memory_extractor).

    Args:
        result_text: Raw LLM output

    Returns:
        List of validated ExtractedJournalEntry objects
    """
    cleaned = result_text.strip()

    # Remove markdown code fences if present
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        start_idx = 0
        end_idx = len(lines)
        for i, line in enumerate(lines):
            if line.startswith("```") and i == 0:
                start_idx = 1
            elif line.startswith("```") and i > 0:
                end_idx = i
                break
        cleaned = "\n".join(lines[start_idx:end_idx])

    # Remove single-line comments
    cleaned = re.sub(r"//.*$", "", cleaned, flags=re.MULTILINE)

    # Remove trailing commas before ] or }
    cleaned = re.sub(r",\s*([\]}])", r"\1", cleaned)

    def _extract_json_array(text: str) -> str | None:
        """Extract first valid-looking JSON array from text."""
        start = text.find("[")
        if start == -1:
            return None
        depth = 0
        in_string = False
        escape_next = False
        for i, char in enumerate(text[start:], start):
            if escape_next:
                escape_next = False
                continue
            if char == "\\":
                escape_next = True
                continue
            if char == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if char == "[":
                depth += 1
            elif char == "]":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
        return None

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

    # Try direct parsing first
    try:
        data = json.loads(cleaned)
        if not isinstance(data, list):
            logger.warning(
                "journal_extraction_result_not_list",
                type=type(data).__name__,
            )
            return []
        return _parse_items(data)

    except json.JSONDecodeError as e:
        logger.warning(
            "journal_extraction_json_parse_failed",
            error=str(e),
            result_length=len(cleaned),
            result_preview=cleaned[:500] if cleaned else "empty",
        )

        # Fallback: extract JSON array from potentially malformed response
        extracted = _extract_json_array(cleaned)
        if extracted:
            try:
                extracted = re.sub(r",\s*([\]}])", r"\1", extracted)
                data = json.loads(extracted)
                if isinstance(data, list):
                    items = _parse_items(data)
                    if items:
                        logger.info(
                            "journal_extraction_json_recovered",
                            recovered_count=len(items),
                        )
                        return items
            except json.JSONDecodeError:
                logger.debug("journal_extraction_json_recovery_failed")

        return []


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

        from src.domains.auth.models import User

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
        last_human_message: HumanMessage | None = None
        last_human_index = -1

        for i in range(len(messages) - 1, -1, -1):
            msg = messages[i]
            if isinstance(msg, HumanMessage):
                last_human_message = msg
                last_human_index = i
                break

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

            from src.domains.auth.models import User

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
        existing_context = _format_existing_entries_for_context(
            existing_entries, full_count=len(existing_entries)
        )

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

        # Build prompt
        prompt = _get_introspection_prompt().format(
            conversation=conversation,
            existing_entries=existing_context,
            current_chars=total_chars,
            max_chars=max_total_chars,
            size_warning=size_warning,
            user_language=user_language,
            max_entry_chars=max_entry_chars,
        )

        # Add analyst persona (always injected, independent of conversational personality)
        prompt += "\n\n" + _get_analyst_persona_prompt().format(
            personality_code=personality_code or "none"
        )

        # Call LLM
        import time as _time

        llm = get_llm("journal_extraction")
        _llm_start = _time.time()
        result = await invoke_with_instrumentation(
            llm=llm,
            llm_type="journal_extraction",
            messages=prompt,
            session_id=session_id,
            user_id=user_id,
        )
        _llm_duration_ms = (_time.time() - _llm_start) * 1000
        result_content = result.content if isinstance(result.content, str) else str(result.content)

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
                    try:
                        if (
                            action.action == "create"
                            and action.theme
                            and action.title
                            and action.content
                        ):
                            await service.create_entry(
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

        # Store debug results for the debug panel (consumed by streaming service)
        if parent_run_id:
            _store_extraction_debug(
                parent_run_id,
                {
                    "actions_parsed": len(actions),
                    "actions_applied": applied_count,
                    "entries": [
                        {
                            "action": a.action,
                            "theme": a.theme.value if a.theme else None,
                            "title": (
                                (a.title[:30] + "…") if a.title and len(a.title) > 30 else a.title
                            ),
                            "full_title": a.title,
                            "content": a.content,
                            "mood": a.mood.value if a.mood else None,
                            "entry_id": a.entry_id,
                        }
                        for a in actions
                    ],
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
