"""Native session, account, operator and pair-policy reads; no long DB session."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import and_, or_, select

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.core.i18n import normalize_language
from src.core.i18n_types import Language
from src.core.session_dependencies import (
    get_current_active_session_for_stream,
    get_current_session_for_stream,
)
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.peers.models import PeerBlock
from src.domains.users.models import User
from src.domains.users.repository import UserRepository
from src.domains.world.avatar import (
    PublicWorldIdentity,
    public_world_name,
    read_avatar_preferences,
)
from src.domains.world.schemas import WorldState
from src.domains.world.store import WorldStore
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore
from src.infrastructure.database.session import get_db_context


@dataclass(frozen=True)
class WorldPolicy:
    language: str
    blocked: frozenset[str]
    eligible: frozenset[str]
    languages: dict[str, Language] = field(default_factory=dict)
    public_identity: PublicWorldIdentity | None = None


async def commit_admission[R](
    account: str, store: WorldStore, transition: Callable[[WorldState, float], R]
) -> tuple[WorldState, R]:
    """Serialize admission with native deactivation/deletion, never with a socket.

    The existing fresh owner lock is held only through the bounded Redis commit;
    ordinary movement does not open a database transaction.
    """
    async with asyncio.timeout(settings.world_policy_timeout + settings.world_authority_timeout):
        async with get_db_context() as db:
            user = await UserRepository(db).get_by_id_for_preference_update(UUID(account))
            if user is None:
                raise AuthorizationError(detail={"error_code": "SESSION_UNAVAILABLE"})
            await require_capability_fresh(db, PlatformCapability.WORLD)
            return await store.update(transition)


async def bound_user(cookie: str) -> User:
    """Resolve the live native cookie and active account under its account-lifecycle row lock."""
    user = await get_current_session_for_stream(
        lia_session=cookie, session_store=SessionStore(await get_redis_session())
    )
    return await get_current_active_session_for_stream(user=user)


async def read_policy(cookie: str, account: str, participants: set[str]) -> WorldPolicy:
    """Read current World authority with a bounded policy timeout."""
    async with asyncio.timeout(settings.world_policy_timeout):
        return await _read_policy(cookie, account, participants)


async def _read_policy(cookie: str, account: str, participants: set[str]) -> WorldPolicy:
    """Resolve current identity, eligible accounts, languages and mutual blocking from native SQL."""
    user = await bound_user(cookie)
    if str(user.id) != account:
        raise AuthorizationError(detail={"error_code": "SESSION_UNAVAILABLE"})
    async with get_db_context() as db:
        await require_capability_fresh(db, PlatformCapability.WORLD)
        participant_ids = [UUID(key) for key in participants | {str(user.id)}]
        pairs = (
            await db.execute(
                select(PeerBlock.blocker_id, PeerBlock.blocked_id).where(
                    or_(
                        and_(
                            PeerBlock.blocker_id == user.id,
                            PeerBlock.blocked_id.in_(participant_ids),
                        ),
                        and_(
                            PeerBlock.blocked_id == user.id,
                            PeerBlock.blocker_id.in_(participant_ids),
                        ),
                    )
                )
            )
        ).all()
        blocked = frozenset(str(b if a == user.id else a) for a, b in pairs)
        participant_rows = (
            await db.execute(
                select(User.id, User.language).where(
                    User.id.in_(participant_ids),
                    User.is_active.is_(True),
                    User.deleted_at.is_(None),
                )
            )
        ).all()
        languages = {str(key): normalize_language(language) for key, language in participant_rows}
    preferences, _ = read_avatar_preferences(user.world_avatar_preferences)
    return WorldPolicy(
        public_identity=PublicWorldIdentity(
            public_world_name(user.full_name, user.language),
            preferences.appearance,
            preferences.revision,
        ),
        language=normalize_language(user.language),
        blocked=blocked,
        eligible=frozenset(languages),
        languages=languages,
    )
