"""One SQL snapshot of ALL active procedural rules, with no semantic ranking or usage writes."""

from collections.abc import Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.memories.models import Memory, MemoryCategory
from src.domains.shared.discussion_directives import (
    DirectiveBudgetExceeded,
    DirectiveRule,
    DirectiveSnapshot,
    render_directives,
)
from src.domains.shared.discussion_sources import semantic_version
from src.domains.users.active_reader import require_active_owner_read
from src.domains.users.models import User


async def _enabled(db: AsyncSession, owner: UUID) -> bool:
    await require_active_owner_read(db, owner)
    # The native MEMORY operator capability stops learning. Already recorded
    # instructions still bind while this person's automatic memory use is on.
    return bool(await db.scalar(select(User.memory_enabled).where(User.id == owner)))


async def read_procedural_directives(
    db: AsyncSession,
    owner: UUID,
    *,
    count_tokens: Callable[[str], int],
    max_tokens: int,
) -> DirectiveSnapshot:
    """Read every active procedural memory as the complete rule snapshot, or refuse.

    Nothing is ranked or truncated: a set whose work exceeds twice the budget, or
    whose rendering exceeds it, is refused rather than read in part. While the
    person keeps automatic memory off, the snapshot holds no rule.

    Args:
        db: The session to read with.
        owner: The account.
        count_tokens: The token counter of the prompt the rules enter.
        max_tokens: The rules' token budget.

    Returns:
        The snapshot and its revision.

    Raises:
        ValueError: The budget is not positive.
        DirectiveBudgetExceeded: The complete rules do not fit.
    """
    if max_tokens <= 0:
        raise ValueError("directive token budget must be positive")
    enabled = await _enabled(db, owner)
    rules: list[DirectiveRule] = []
    if enabled:
        query = (
            select(
                Memory.id, Memory.content.label("text"), Memory.usage_nuance, Memory.trigger_topic
            )
            .where(
                Memory.user_id == owner,
                Memory.invalidated_at.is_(None),
                Memory.category == MemoryCategory.PROCEDURAL.value,
            )
            .order_by(Memory.id)
            .execution_options(yield_per=100)
        )
        rows = await db.stream(query)
        work_tokens = 0
        try:
            async for row in rows.mappings():
                rule = DirectiveRule.model_validate(dict(row))
                rules.append(rule)
                work_tokens += count_tokens(render_directives((rule,)))
                if work_tokens > 2 * max_tokens:
                    raise DirectiveBudgetExceeded(
                        "complete directives exceed the input work budget"
                    )
        finally:
            await rows.close()
    frame = render_directives(tuple(rules))
    if count_tokens(frame) > max_tokens:
        raise DirectiveBudgetExceeded("complete directives exceed the input token budget")
    return DirectiveSnapshot(
        owner_id=owner,
        enabled=enabled,
        revision=semantic_version((str(enabled), frame)),
        rules=tuple(rules),
    )
