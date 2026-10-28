"""Fresh native game policy under the same canonical account fence as block/unblock."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import or_, select

from src.core.exceptions import AuthorizationError
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.peers.models import PeerBlock
from src.domains.users.models import User
from src.domains.world.game_context import GameScope
from src.infrastructure.database.session import get_db_context


@asynccontextmanager
async def locked_game_scope(
    account: str, controller: str, participants: frozenset[str]
) -> AsyncIterator[GameScope]:
    """Hold at most three canonical account fences through only the bounded Redis commit.

    This is a deliberate, bounded exception to "no transaction across a network
    call" (ADR-365 amendment 2026-10-28): blocks, deactivation and deletion are
    written in SQL while the game is committed in Redis, and only a fence held
    through that one commit orders them. A block committed before the policy read
    refuses the command; one committed after it waits for the commit to end.

    The fence is ``FOR NO KEY UPDATE``, the strength of the peers pair fence: it
    orders the canonical fence takers and every UPDATE/DELETE of those accounts,
    never an insert merely referencing them (``FOR KEY SHARE``). Authentication and
    computer search run before this door; the caller bounds it with the policy and
    authority deadlines. All policy reads here use this very session; opening a
    second session could self-deadlock.

    Args:
        account: The commanding account.
        controller: The commanding controller generation.
        participants: The table's members and pending requester, observed before.

    Yields:
        The fresh eligibility and block policy of the commanding account.

    Raises:
        ValueError: More than three accounts would be fenced.
        AuthorizationError: The World capability is off, or the account is no
            longer active.
    """
    ids = {UUID(key) for key in participants | {account}}
    if len(ids) > 3:
        raise ValueError("game_policy_scope")
    async with get_db_context() as db:
        await db.execute(
            select(User.id)
            .where(User.id.in_(ids))
            .order_by(User.id)
            .with_for_update(key_share=True)
        )
        await require_capability_fresh(db, PlatformCapability.WORLD)
        eligible = frozenset(
            str(key)
            for key in (
                await db.scalars(
                    select(User.id).where(
                        User.id.in_(ids), User.is_active.is_(True), User.deleted_at.is_(None)
                    )
                )
            ).all()
        )
        if account not in eligible:
            raise AuthorizationError(detail={"error_code": "SESSION_UNAVAILABLE"})
        owner = UUID(account)
        pairs = (
            await db.execute(
                select(PeerBlock.blocker_id, PeerBlock.blocked_id).where(
                    PeerBlock.blocker_id.in_(ids),
                    PeerBlock.blocked_id.in_(ids),
                    or_(PeerBlock.blocker_id == owner, PeerBlock.blocked_id == owner),
                )
            )
        ).all()
        blocked = frozenset(str(second if first == owner else first) for first, second in pairs)
        yield GameScope(account, controller, eligible, blocked)
