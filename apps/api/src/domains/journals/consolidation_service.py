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

from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from src.domains.journals.models import JournalEntry

from src.core.config import settings
from src.core.llm_config_helper import get_llm_config_for_agent
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.journals.constants import JOURNAL_ENTRY_CONTENT_MAX_LENGTH
from src.domains.journals.extraction_service import (
    _parse_consolidation_result,
    _persist_journal_tokens,
    _update_user_last_cost,
)
from src.domains.journals.models import JournalEntryMood, JournalEntrySource
from src.infrastructure.llm.factory import get_llm
from src.infrastructure.llm.invoke_helpers import invoke_with_instrumentation
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_journals import (
    journal_portrait_compile_duration_seconds,
)

logger = get_logger(__name__)


async def _build_usage_patterns_section(user_id: UUID) -> str:
    """Build a compact 'observed usage patterns' block for the consolidation prompt.

    Aggregates lightweight signals over the past 7 days (no LLM, plain SQL):
    - Total user messages count
    - Dominant time-of-day buckets (morning / afternoon / evening / night)

    These are factual, never PII, and meant to help the LLM situate the user's
    current rhythm without ever reproducing message content. Returns an empty
    string when there is no recent activity (degrades gracefully).

    Args:
        user_id: Owner user UUID.

    Returns:
        A "## OBSERVED USAGE PATTERNS" section or an empty string.
    """
    try:
        from sqlalchemy import and_, case, func, select

        from src.infrastructure.database.session import get_db_context

        async with get_db_context() as db:
            from src.domains.conversations.models import Conversation, ConversationMessage

            conv_result = await db.execute(
                select(Conversation.id).where(Conversation.user_id == user_id)
            )
            conversation_id = conv_result.scalar_one_or_none()
            if not conversation_id:
                return ""

            since = datetime.now(UTC) - timedelta(days=7)
            hour_local = func.extract("hour", ConversationMessage.created_at)
            bucket = case(
                (hour_local.between(5, 11), "morning"),
                (hour_local.between(12, 17), "afternoon"),
                (hour_local.between(18, 22), "evening"),
                else_="night",
            )

            stmt = (
                select(bucket.label("bucket"), func.count(ConversationMessage.id).label("n"))
                .where(
                    and_(
                        ConversationMessage.conversation_id == conversation_id,
                        ConversationMessage.role == "human",
                        ConversationMessage.created_at > since,
                    )
                )
                .group_by(bucket)
            )
            rows = (await db.execute(stmt)).all()

        if not rows:
            return ""

        counts: dict[str, int] = {row[0]: int(row[1]) for row in rows}
        total = sum(counts.values())
        if total == 0:
            return ""

        # Format compactly — let the LLM interpret without fixed thresholds.
        ordered = ("morning", "afternoon", "evening", "night")
        details = ", ".join(
            f"{label} {counts[label]}" for label in ordered if counts.get(label, 0) > 0
        )

        return (
            "## OBSERVED USAGE PATTERNS (past 7 days)\n"
            f"User messages: {total}. Distribution: {details}.\n"
            "Use these factual signals to situate the user's current rhythm "
            "in the portrait (phase, contexts) — never reference them explicitly "
            "to the user."
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "journal_usage_patterns_load_failed",
            user_id=str(user_id),
            error=str(exc),
        )
        return ""


async def _persist_compiled_portrait(
    user_id: UUID, portrait_full: str | None, portrait_brief: str | None
) -> None:
    """Persist the compiled portrait pair on the user record.

    Both fields are optional. If only one is provided, the other is left
    untouched. Updates ``journal_portrait_compiled_at`` to NOW() whenever at
    least one portrait was supplied.

    Args:
        user_id: Owner user UUID.
        portrait_full: Compiled full portrait (~200 tokens) or None.
        portrait_brief: Compiled brief portrait (~60 tokens) or None.
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


def _get_consolidation_prompt() -> str:
    """Load the journal consolidation prompt from file."""
    return str(load_prompt("journal_consolidation_prompt"))


def _get_analyst_persona_prompt() -> str:
    """Load the journal analyst persona prompt from file."""
    return str(load_prompt("journal_analyst_persona"))


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
            return (
                "## HEALTH SIGNALS (factual, not medical)\n"
                f"{block}\n"
                "Use these signals to enrich your consolidation — e.g. to "
                "notice a pattern the user may not have articulated. Never "
                "reproduce raw sensor values in entries."
            )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "journal_consolidation_health_context_failed",
            user_id=str(user_id),
            error=str(exc),
        )
        return ""


def _format_all_entries(entries: list[JournalEntry]) -> str:
    """Format all active entries for the consolidation prompt.

    Shows full content for every entry with the full epistemic metadata so the
    LLM can reason about lifecycle (entries never injected, validated directives,
    contradicted hypotheses) and act accordingly during maintenance.

    The metadata exposed in each entry header:
        - created: original creation date
        - last_inj: last time the entry was injected into a prompt (or "never")
        - uses: total injection count
        - conf: epistemic status (low/medium/high)
        - ev/co: evidence and contradiction counters from deferred self-evaluation
        - char_count: content character count
        - hints: search hints (or "MISSING")

    Args:
        entries: All active entries ordered by created_at desc

    Returns:
        Formatted entries string
    """
    if not entries:
        return "No entries to review."

    # ID reference table for easy copy-paste
    id_lines = ["### ENTRY ID REFERENCE (copy-paste these exact IDs for update/delete):"]
    for entry in entries:
        id_lines.append(f"- {entry.id}  →  {entry.title}")

    # Full entries with epistemic metadata
    entry_lines = []
    for entry in entries:
        created_str = entry.created_at.strftime("%Y-%m-%d")
        last_inj_str = (
            entry.last_injected_at.strftime("%Y-%m-%d") if entry.last_injected_at else "never"
        )
        hints_str = (
            f" | hints: {', '.join(entry.search_hints)}"
            if entry.search_hints
            else " | hints: MISSING"
        )
        entry_lines.append(
            f"[id={entry.id} | created={created_str} | last_inj={last_inj_str} "
            f"| uses={entry.injection_count} | conf={entry.confidence} "
            f"| ev={entry.evidence_count}/co={entry.contradiction_count} "
            f"| level={entry.level} "
            f"| {entry.theme} | {entry.mood} | {entry.char_count} chars{hints_str}]\n"
            f"**{entry.title}**\n{entry.content}\n"
        )

    return "\n".join(id_lines) + "\n\n---\n" + "\n---\n".join(entry_lines)


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
    max_entry_chars: int = JOURNAL_ENTRY_CONTENT_MAX_LENGTH,
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
        max_entry_chars: User's configured max characters per entry (prompt constraint)
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

        # Observed usage patterns (factual, lightweight — no LLM, no PII reproduction)
        usage_patterns_section = await _build_usage_patterns_section(user_id)

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

        # Health Metrics signals — empty string when disabled / no data.
        health_signals_section = await _maybe_build_health_signals_section(user_id)

        # Build prompt
        prompt = _get_consolidation_prompt().format(
            all_entries=all_entries_text,
            current_chars=total_chars,
            max_chars=max_total_chars,
            size_warning=size_warning,
            current_datetime=current_datetime,
            conversation_history_section=conversation_history_section,
            usage_patterns_section=usage_patterns_section,
            user_language=user_language,
            max_entry_chars=max_entry_chars,
            size_management_instruction=size_management_instruction,
            health_signals_section=health_signals_section,
        )

        # Add analyst persona (always injected, independent of conversational personality)
        prompt += "\n\n" + _get_analyst_persona_prompt().format(
            personality_code=personality_code or "none"
        )

        # Call LLM
        llm = get_llm("journal_consolidation")
        result = await invoke_with_instrumentation(
            llm=llm,
            llm_type="journal_consolidation",
            messages=prompt,
            user_id=str(user_id),
        )
        result_content = result.text

        # Persist token usage (use effective config, not defaults — admin overrides matter)
        model_name = get_llm_config_for_agent(settings, "journal_consolidation").model
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

        # Parse result — supports both legacy array format and the enriched
        # object format with portrait_full + portrait_brief (commit 3+).
        import time as _time

        _portrait_compile_start = _time.time()
        parsed = _parse_consolidation_result(result_content)
        actions = parsed.actions

        # Persist the compiled portraits if the LLM produced them. Done before
        # applying the actions so a partial failure on actions still preserves
        # the portrait — the two are independent products of the same call.
        if parsed.portrait_full or parsed.portrait_brief:
            await _persist_compiled_portrait(user_id, parsed.portrait_full, parsed.portrait_brief)
            with suppress(Exception):
                journal_portrait_compile_duration_seconds.observe(
                    _time.time() - _portrait_compile_start
                )

        if not actions:
            logger.debug(
                "journal_consolidation_no_actions",
                user_id=str(user_id),
            )
            return 0

        # Filter out hallucinated entry_ids (only keep IDs that exist in loaded entries)
        known_ids = {str(e.id) for e in entries}
        valid_actions = []
        for action in actions:
            if action.action in ("update", "delete") and action.entry_id:
                if action.entry_id not in known_ids:
                    logger.warning(
                        "journal_consolidation_unknown_entry_id",
                        user_id=str(user_id),
                        action=action.action,
                        entry_id=action.entry_id,
                    )
                    continue
            valid_actions.append(action)

        if len(valid_actions) < len(actions):
            logger.info(
                "journal_consolidation_filtered_hallucinated_ids",
                user_id=str(user_id),
                original_count=len(actions),
                valid_count=len(valid_actions),
                filtered_count=len(actions) - len(valid_actions),
            )
        actions = valid_actions

        # Apply actions (with embedding cost tracking)
        from src.infrastructure.llm.embedding_context import (
            clear_embedding_context,
            set_embedding_context,
        )

        set_embedding_context(
            user_id=str(user_id),
            session_id="journal_consolidation",
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
                                max_entry_chars=max_entry_chars,
                                search_hints=action.search_hints,
                                confidence=(
                                    action.confidence.value if action.confidence else "medium"
                                ),
                                level=(action.level.value if action.level else "L1"),
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
        finally:
            clear_embedding_context()

        # Update last_consolidated_at
        async with get_db_context() as db:
            from sqlalchemy import select

            from src.domains.users.models import User

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
