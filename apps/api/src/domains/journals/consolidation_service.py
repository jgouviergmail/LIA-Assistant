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
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from src.domains.journals.models import JournalEntry

from src.core.config import settings
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.journals.constants import JOURNAL_ENTRY_CONTENT_MAX_LENGTH
from src.domains.journals.extraction_service import (
    _parse_journal_extraction_result,
    _persist_journal_tokens,
    _update_user_last_cost,
)
from src.domains.journals.models import JournalEntryMood, JournalEntrySource
from src.domains.llm_config.constants import LLM_DEFAULTS
from src.infrastructure.llm.factory import get_llm
from src.infrastructure.llm.invoke_helpers import invoke_with_instrumentation
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def _get_consolidation_prompt() -> str:
    """Load the journal consolidation prompt from file."""
    return str(load_prompt("journal_consolidation_prompt"))


def _get_personality_addon_prompt() -> str:
    """Load the journal personality addon prompt from file."""
    return str(load_prompt("journal_introspection_personality_addon"))


def _format_all_entries(entries: list[JournalEntry]) -> str:
    """Format all active entries for the consolidation prompt.

    Shows full content for every entry (unlike extraction which uses summaries).

    Args:
        entries: All active entries ordered by created_at desc

    Returns:
        Formatted entries string
    """
    if not entries:
        return "No entries to review."

    lines = []
    for entry in entries:
        date_str = entry.created_at.strftime("%Y-%m-%d")
        lines.append(
            f"[{entry.id} | {date_str} | {entry.theme} | {entry.mood} | "
            f"{entry.char_count} chars]\n"
            f"**{entry.title}**\n{entry.content}\n"
        )

    return "\n---\n".join(lines)


async def _load_conversation_history(
    user_id: UUID,
    since: datetime | None,
    max_messages: int,
    max_days: int,
) -> str:
    """Load recent conversation messages for consolidation enrichment.

    Only loaded when user has enabled journal_consolidation_with_history.
    Uses ConversationMessage model (1:1 user↔conversation).

    Args:
        user_id: User UUID
        since: Load messages since this timestamp (or fallback to max_days)
        max_messages: Maximum messages to load
        max_days: Maximum lookback days (bounds null/old since)

    Returns:
        Formatted conversation history string
    """
    from src.infrastructure.database import get_db_context

    try:
        async with get_db_context() as db:
            from sqlalchemy import and_, select

            from src.domains.conversations.models import Conversation, ConversationMessage

            # Find user's conversation
            conv_result = await db.execute(
                select(Conversation).where(Conversation.user_id == user_id)
            )
            conversation = conv_result.scalar_one_or_none()

            if not conversation:
                return ""

            # Determine lookback window
            lookback = since or (datetime.now(UTC) - timedelta(days=max_days))
            # Also enforce max_days as hard bound
            max_lookback = datetime.now(UTC) - timedelta(days=max_days)
            effective_since = max(lookback, max_lookback)

            # Query recent messages
            msg_result = await db.execute(
                select(ConversationMessage)
                .where(
                    and_(
                        ConversationMessage.conversation_id == conversation.id,
                        ConversationMessage.created_at > effective_since,
                        ConversationMessage.role.in_(["human", "ai"]),
                    )
                )
                .order_by(ConversationMessage.created_at.desc())
                .limit(max_messages)
            )
            messages = list(msg_result.scalars().all())

            if not messages:
                return ""

            # Format (oldest first)
            messages.reverse()
            lines = []
            for msg in messages:
                prefix = "USER" if msg.role == "human" else "ASSISTANT"
                content = msg.content[:500] if len(msg.content) > 500 else msg.content
                lines.append(f"{prefix}: {content}")

            return "\n".join(lines)

    except Exception as e:
        logger.warning(
            "journal_consolidation_history_load_failed",
            user_id=str(user_id),
            error=str(e),
        )
        return ""


async def consolidate_journals_for_user(
    user_id: UUID,
    personality_instruction: str | None,
    personality_code: str | None,
    user_language: str,
    consolidation_with_history: bool = False,
    max_total_chars: int = 40000,
    last_consolidated_at: datetime | None = None,
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
        last_consolidated_at: Timestamp of previous consolidation (for history lookback)

    Returns:
        Number of actions applied
    """
    from src.infrastructure.database import get_db_context

    try:
        # Load all active entries
        async with get_db_context() as db:
            from src.domains.journals.service import JournalService

            service = JournalService(db)
            entries = await service.get_all_active(user_id)
            total_chars = await service.repo.get_total_chars(user_id)

        # Format entries for prompt
        all_entries_text = _format_all_entries(entries)

        # Size warning
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

        size_management_instruction = (
            "You are within the size limit. Only act if genuinely useful."
            if usage_pct <= 80
            else "You need to reduce total size. Summarize verbose entries or delete obsolete ones."
        )

        # Optional conversation history
        conversation_history_section = ""
        if consolidation_with_history:
            history = await _load_conversation_history(
                user_id=user_id,
                since=last_consolidated_at,
                max_messages=settings.journal_consolidation_history_max_messages,
                max_days=settings.journal_consolidation_history_max_days,
            )
            if history:
                conversation_history_section = (
                    "## RECENT CONVERSATION HISTORY\n"
                    "Review these recent exchanges for insights you may have missed:\n\n"
                    f"{history}"
                )

        # Current datetime
        current_datetime = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

        # Build prompt
        prompt = _get_consolidation_prompt().format(
            all_entries=all_entries_text,
            current_chars=total_chars,
            max_chars=max_total_chars,
            size_warning=size_warning,
            current_datetime=current_datetime,
            conversation_history_section=conversation_history_section,
            user_language=user_language,
            max_entry_chars=JOURNAL_ENTRY_CONTENT_MAX_LENGTH,
            size_management_instruction=size_management_instruction,
        )

        # Add personality addon
        if personality_instruction:
            prompt += "\n\n" + _get_personality_addon_prompt().format(
                personality_instruction=personality_instruction
            )

        # Call LLM
        llm = get_llm("journal_consolidation")
        result = await invoke_with_instrumentation(
            llm=llm,
            llm_type="journal_consolidation",
            messages=prompt,
            user_id=str(user_id),
        )
        result_content = result.content if isinstance(result.content, str) else str(result.content)

        # Persist token usage
        model_name = LLM_DEFAULTS["journal_consolidation"].model
        await _persist_journal_tokens(
            user_id=str(user_id),
            session_id="consolidation",
            conversation_id=None,
            result=result,
            model_name=model_name,
            node_name="journal_consolidation",
        )

        # Update user's last cost
        await _update_user_last_cost(str(user_id), result, model_name, source="consolidation")

        # Parse result (reuse same parser as extraction)
        actions = _parse_journal_extraction_result(result_content)

        if not actions:
            logger.debug(
                "journal_consolidation_no_actions",
                user_id=str(user_id),
            )
            return 0

        # Apply actions
        applied_count = 0
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
                            user_id=user_id,
                            theme=action.theme.value,
                            title=action.title,
                            content=action.content,
                            mood=(
                                action.mood.value
                                if action.mood
                                else JournalEntryMood.REFLECTIVE.value
                            ),
                            source=JournalEntrySource.CONSOLIDATION.value,
                            personality_code=personality_code,
                        )
                        applied_count += 1

                    elif action.action == "update" and action.entry_id:
                        entry = await service.repo.get_by_id(UUID(action.entry_id))
                        if entry and entry.user_id == user_id:
                            await service.update_entry(
                                entry=entry,
                                title=action.title,
                                content=action.content,
                                mood=(action.mood.value if action.mood else None),
                            )
                            applied_count += 1

                    elif action.action == "delete" and action.entry_id:
                        entry = await service.repo.get_by_id(UUID(action.entry_id))
                        if entry and entry.user_id == user_id:
                            await service.delete_entry(entry)
                            applied_count += 1

                except Exception as e:
                    logger.warning(
                        "journal_consolidation_action_failed",
                        user_id=str(user_id),
                        action=action.action,
                        error=str(e),
                    )
                    continue

            await db.commit()

        # Update last_consolidated_at
        async with get_db_context() as db:
            from sqlalchemy import select

            from src.domains.auth.models import User

            user_result = await db.execute(select(User).where(User.id == user_id))
            user = user_result.scalar_one_or_none()
            if user:
                user.journal_last_consolidated_at = datetime.now(UTC)
                await db.commit()

        logger.info(
            "journal_consolidation_completed",
            user_id=str(user_id),
            actions_parsed=len(actions),
            actions_applied=applied_count,
            with_history=consolidation_with_history,
        )

        return applied_count

    except Exception as e:
        logger.error(
            "journal_consolidation_failed",
            user_id=str(user_id),
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        return 0
