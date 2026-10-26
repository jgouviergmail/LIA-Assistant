"""Native private-message authority, re-read before spending and publication."""

from dataclasses import dataclass

from src.core.config import settings
from src.domains.world.messages import MailboxScope, MessageScope, mailbox_actor
from src.domains.world.policy import WorldPolicy, read_policy
from src.domains.world.schemas import WorldState
from src.domains.world.store import WorldStore
from src.domains.world.tickets import cookie_binding


@dataclass(frozen=True)
class MessageContext:
    state: WorldState
    now: float
    scope: MessageScope
    policy: WorldPolicy


class MessageAccess:
    def __init__(self, world: WorldStore) -> None:
        """Bind fresh message authorization to the shared authoritative store."""
        self.world = world

    async def context(
        self,
        cookie: str,
        account: str,
        payload: MailboxScope,
        participants: set[str] | None = None,
    ) -> MessageContext:
        """Recheck cookie identity, account policy and live controller before returning a message scope."""
        state, _ = await self.world.read()
        policy = await read_policy(cookie, account, set(state.actors) | (participants or set()))
        scope = MessageScope(
            account,
            cookie_binding(cookie),
            payload.controller,
            payload.epoch,
            policy.eligible,
            policy.blocked,
            settings.world_idle_seconds,
        )
        # Policy I/O may have overlapped a takeover or departure.
        state, now = await self.world.read()
        mailbox_actor(state, scope, now)
        return MessageContext(state, now, scope, policy)
