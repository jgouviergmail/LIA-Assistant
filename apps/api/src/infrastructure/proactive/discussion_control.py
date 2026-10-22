"""Complete control snapshot, independent from optional factual source selection."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.token_budget import count_external_tokens
from src.domains.proactive_discussions.directives import (
    DirectiveBudgetExceeded,
    load_directive_snapshot,
)
from src.domains.proactive_discussions.replies import (
    pending_controls,
    render_pending_controls,
    synchronize_replies,
)
from src.domains.proactive_discussions.rule_controls import ControlSupport
from src.domains.shared.discussion_sources import semantic_version
from src.domains.users.models import User


@dataclass(frozen=True)
class ControlSnapshot:
    """The person's complete controls a run reads: revision, rendered text, supports."""

    revision: str
    text: str
    supports: tuple[ControlSupport, ...] = ()


async def load_controls(db: AsyncSession, owner: UUID, *, now: datetime) -> ControlSnapshot:
    """The person's complete rules and live reply guards, or a refusal to act.

    The replies to the previous opening are settled first, so the snapshot binds
    what the person answered.

    Args:
        db: The caller's session.
        owner: The account whose controls bind the run.
        now: The run's clock (reply binding window, guard lifetime).

    Returns:
        The snapshot and its revision, which a later check compares.

    Raises:
        DirectiveBudgetExceeded: When the complete controls cannot fit their budget.
    """
    await synchronize_replies(db, owner, now=now)
    return await preview_controls(db, owner, now=now)


async def preview_controls(db: AsyncSession, owner: UUID, *, now: datetime) -> ControlSnapshot:
    """The controls as a run would read them now, without settling any reply.

    The settings page reads it to price a run's first call and to say why a
    requested rebuild waits; only :func:`load_controls` writes.

    Args:
        db: The caller's session.
        owner: The account whose controls are read.
        now: The clock bounding the reply guards.

    Returns:
        The snapshot and its revision.

    Raises:
        DirectiveBudgetExceeded: When the complete controls cannot fit their budget.
    """
    canonical = await load_directive_snapshot(
        db,
        owner,
        count_tokens=count_external_tokens,
        max_tokens=settings.discussion_directives_max_tokens,
    )
    memory = await db.scalar(select(User.memory_enabled).where(User.id == owner))
    replies = await pending_controls(db, owner, memory_enabled=bool(memory), now=now)
    guard = render_pending_controls(replies)
    identity = (
        await db.execute(select(User.language, User.personality_id).where(User.id == owner))
    ).one()
    return ControlSnapshot(
        semantic_version(
            (canonical.revision, guard, identity.language, str(identity.personality_id))
        ),
        canonical.prompt_text() + "\n" + guard,
        tuple(
            ControlSupport(
                id=f"memory:{rule.id}",
                text="\n".join((rule.text, rule.usage_nuance, rule.trigger_topic)),
            )
            for rule in canonical.rules
        )
        + replies,
    )


async def controls_fit(db: AsyncSession, owner: UUID, *, now: datetime) -> bool:
    """Whether a run could read the complete controls, without binding or locking anything.

    The settings page asks it to say why a requested rebuild cannot start; the
    run itself asks :func:`load_controls`, which also settles replies.

    Args:
        db: A read session.
        owner: The account whose controls are measured.
        now: The clock bounding the reply guards.

    Returns:
        False when the rules or the live reply guards exceed their budget.
    """
    try:
        await preview_controls(db, owner, now=now)
    except DirectiveBudgetExceeded:
        return False
    return True
