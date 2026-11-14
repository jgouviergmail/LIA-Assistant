"""Bounded account-wide journal inputs, with explicit independent dialogue boundaries."""

from datetime import UTC, datetime, timedelta
from functools import lru_cache
from uuid import UUID

import structlog
from sqlalchemy import case, func, select

from src.core.constants import (
    DEFAULT_USER_DISPLAY_TIMEZONE,
    JOURNAL_CONSOLIDATION_HISTORY_MESSAGE_MAX_CHARS,
)
from src.core.prompt_store import parse_prompt_sections, read_prompt_file
from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.users.models import User
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)


@lru_cache(maxsize=1)
def source_lines() -> dict[str, str]:
    """Read the versioned journal input scaffolds once."""
    return dict(parse_prompt_sections(read_prompt_file("journal_portrait_source_lines"), 2))


def render_usage_patterns_section(*, total: int, details: str) -> str:
    """Render exact activity totals and their local-time distribution."""
    lines = source_lines()
    return "\n".join(
        [
            lines["usage_header"],
            lines["usage_line"].format(total=total, details=details),
            lines["usage_directive"],
        ]
    )


async def build_usage_patterns_section(user_id: UUID) -> str:
    """Count visible human messages across all active discussions in one aggregate.

    The account's timezone determines the buckets. A failed read is explicitly
    unavailable; only a successful read with no messages returns an empty block.
    """
    try:
        async with get_db_context() as db:
            zone = await db.scalar(select(User.timezone).where(User.id == user_id))
            hour = func.extract(
                "hour",
                func.timezone(
                    zone or DEFAULT_USER_DISPLAY_TIMEZONE, ConversationMessage.created_at
                ),
            )
            bucket = case(
                (hour.between(5, 11), "morning"),
                (hour.between(12, 17), "afternoon"),
                (hour.between(18, 22), "evening"),
                else_="night",
            )
            rows = (
                await db.execute(
                    select(bucket, func.count(ConversationMessage.id))
                    .join(Conversation, Conversation.id == ConversationMessage.conversation_id)
                    .where(
                        Conversation.user_id == user_id,
                        Conversation.deleted_at.is_(None),
                        ConversationMessage.role == "user",
                        ConversationMessage.hidden.is_(False),
                        ConversationMessage.created_at > datetime.now(UTC) - timedelta(days=7),
                    )
                    .group_by(bucket)
                )
            ).all()
        if not rows:
            return ""
        counts = {label: int(count) for label, count in rows}
        details = ", ".join(
            f"{label} {counts[label]}"
            for label in ("morning", "afternoon", "evening", "night")
            if counts.get(label, 0)
        )
        return render_usage_patterns_section(total=sum(counts.values()), details=details)
    except Exception as exc:
        logger.warning(
            "journal_usage_patterns_load_failed",
            user_id=str(user_id),
            error_type=type(exc).__name__,
        )
        return source_lines()["usage_unavailable"]


async def load_conversation_history(
    user_id: UUID, since: datetime | None, max_messages: int, max_days: int
) -> str:
    """Read one global page and its exact total, grouping the page by discussion.

    Message bodies are bounded in SQL, so a large archived answer never needs
    to be loaded in full. UUID labels cannot inject a user-supplied title into
    the prompt scaffold. Ordering is deterministic even for equal timestamps.
    """
    earliest = datetime.now(UTC) - timedelta(days=max_days)
    effective_since = max(since, earliest) if since is not None else earliest
    cap = JOURNAL_CONSOLIDATION_HISTORY_MESSAGE_MAX_CHARS
    try:
        async with get_db_context() as db:
            rows = (
                await db.execute(
                    select(
                        ConversationMessage.conversation_id,
                        ConversationMessage.role,
                        func.left(ConversationMessage.content, cap),
                        ConversationMessage.created_at,
                        func.length(ConversationMessage.content) > cap,
                        func.count().over(),
                    )
                    .join(Conversation, Conversation.id == ConversationMessage.conversation_id)
                    .where(
                        Conversation.user_id == user_id,
                        Conversation.deleted_at.is_(None),
                        ConversationMessage.created_at > effective_since,
                        ConversationMessage.role.in_(["user", "assistant"]),
                        ConversationMessage.hidden.is_(False),
                    )
                    .order_by(ConversationMessage.created_at.desc(), ConversationMessage.id.desc())
                    .limit(max_messages)
                )
            ).all()
        if not rows:
            return ""
        lines = source_lines()
        discussions: dict[UUID, list[str]] = {}
        for identity, role, content, created_at, cut, _ in reversed(rows):
            discussions.setdefault(identity, []).append(
                lines["history_item"].format(
                    timestamp=created_at.isoformat(),
                    role=role.upper(),
                    content=content,
                    cut=lines["history_cut"] if cut else "",
                )
            )
        blocks = [
            lines["history_header"].format(shown=len(rows), total=rows[0][5], excerpt_max=cap),
            lines["history_directive"],
        ]
        for identity, messages in discussions.items():
            blocks.append(lines["history_discussion"].format(identity=identity))
            blocks.extend(messages)
        return "\n".join(blocks)
    except Exception as exc:
        logger.warning(
            "journal_consolidation_history_load_failed",
            user_id=str(user_id),
            error_type=type(exc).__name__,
        )
        return source_lines()["history_unavailable"]
