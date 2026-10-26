"""CAS-fenced ephemeral bodies, never part of shared world snapshots."""

import asyncio
import hashlib
from collections.abc import Callable
from typing import Annotated

from pydantic import Field, ValidationError
from redis.exceptions import WatchError

from src.core.constants import REDIS_KEY_WORLD_MESSAGE_PREFIX
from src.domains.world.message_content import StoredMessage
from src.domains.world.messages import (
    MESSAGE_INBOX_LIMIT,
    MESSAGE_TTL,
    TRANSLATION_BYTES,
    UUID_PATTERN,
    MessageScope,
    mailbox_actor,
    message_pair,
)
from src.domains.world.schemas import ActorState, StrictModel, WorldState
from src.domains.world.store import MAX_CAS_ATTEMPTS, WorldStore, WorldUnavailable

MAX_BODY_BYTES = 32768
# The validated UTF-8 translation maximum, plus its small native usage receipt.
# Reserve every outstanding variant together before any worker can spend tokens.
PENDING_VARIANT_BYTES = TRANSLATION_BYTES + 512


class Inbox(StrictModel):
    ids: list[Annotated[str, Field(pattern=UUID_PATTERN)]] = Field(
        default_factory=list,
        max_length=MESSAGE_INBOX_LIMIT,
        description="Bounded ordered message identifiers in this private account inbox.",
    )


def participant(message: StoredMessage, actor: ActorState) -> bool:
    """Check membership in a private message's sender/recipient pair."""
    return any(
        address.account == actor.account_id for address in (message.sender, message.recipient)
    )


class WorldMailbox:
    @staticmethod
    def require_translation_capacity(message: StoredMessage) -> None:
        """Reserve serialized space for every pending translation before model dispatch."""
        pending = sum(variant.status == "pending" for variant in message.variants.values())
        required = len(message.model_dump_json().encode("utf-8")) + pending * PENDING_VARIANT_BYTES
        if required > MAX_BODY_BYTES:
            raise WorldUnavailable("world_translation_capacity")

    def __init__(self, world: WorldStore) -> None:
        """Bind private correspondence keys to the exact instance and scene namespace."""
        self.world = world
        namespace = world.message_namespace
        self.prefix = REDIS_KEY_WORLD_MESSAGE_PREFIX + namespace + ":"

    def body_key(self, message: str) -> str:
        """Derive a bounded hashed body key from the message identifier."""
        return self.prefix + "body:" + hashlib.sha256(message.encode()).hexdigest()

    def inbox_key(self, account: str) -> str:
        """Derive the private account inbox key within this mailbox namespace."""
        return self.prefix + "inbox:" + account

    @staticmethod
    def decode(raw: str | bytes) -> StoredMessage:
        """Validate a bounded private body, failing closed on corruption or excessive size."""
        if len(raw) > MAX_BODY_BYTES:
            raise WorldUnavailable("world_message_limit")
        try:
            return StoredMessage.model_validate_json(raw)
        except ValidationError:
            raise WorldUnavailable("world_message_corrupt") from None

    @staticmethod
    def decode_index(raw: str | bytes | None) -> Inbox:
        """Read a bounded inbox index; only an absent key means an empty inbox."""
        if raw is None:
            return Inbox()
        if len(raw) > MESSAGE_INBOX_LIMIT * 50:
            raise WorldUnavailable("world_mailbox_limit")
        try:
            return Inbox.model_validate_json(raw)
        except ValidationError:
            raise WorldUnavailable("world_mailbox_corrupt") from None

    async def inbox(self, scope: MessageScope) -> list[StoredMessage]:
        """Read the live controller's unexpired participant messages from its bounded private index."""
        async with asyncio.timeout(self.world.timeout):
            state, now = await self.world.read()
            own = mailbox_actor(state, scope, now)
            index = self.decode_index(await self.world.redis.get(self.inbox_key(scope.account)))
            if not index.ids:
                return []
            values = await self.world.redis.mget([self.body_key(key) for key in index.ids])
            messages = [self.decode(value) for value in values if value is not None]
            return [
                message
                for message in messages
                if message.epoch == state.epoch
                and message.expires_at > now
                and participant(message, own)
            ]

    async def stage(self, message: StoredMessage, scope: MessageScope) -> bool:
        """Atomically stage an initial private body and both participant indexes."""
        async with asyncio.timeout(self.world.timeout):
            return await self._write(message.id, scope, None, message)

    async def change(
        self,
        message: str,
        scope: MessageScope,
        change: Callable[[StoredMessage, WorldState, float], None],
    ) -> bool:
        """Apply an owned mutation under a world/body CAS fence and the store timeout."""
        async with asyncio.timeout(self.world.timeout):
            return await self._write(message, scope, change, None)

    async def transition[R](
        self,
        message: str,
        scope: MessageScope,
        transition: Callable[[StoredMessage, WorldState, float], R],
    ) -> R:
        """Return a mutation's result only after its CAS-fenced private body commits."""
        result: list[R] = []

        def apply(content: StoredMessage, state: WorldState, now: float) -> None:
            """Capture the transition result from the snapshot whose private-body mutation commits."""
            result[:] = [transition(content, state, now)]

        await self.change(message, scope, apply)
        return result[0]

    async def _write(
        self,
        message_id: str,
        scope: MessageScope,
        change: Callable[[StoredMessage, WorldState, float], None] | None,
        initial: StoredMessage | None,
    ) -> bool:
        """Retry watched world/body/index transactions while preserving controller and participant fences."""
        body_key = self.body_key(message_id)
        index_keys = (
            [
                self.inbox_key(initial.sender.account),
                self.inbox_key(initial.recipient.account),
            ]
            if initial
            else []
        )
        for _ in range(MAX_CAS_ATTEMPTS):
            try:
                async with self.world.redis.pipeline(transaction=True) as pipe:
                    await pipe.watch(self.world.key, body_key, *index_keys)
                    state = self.world.decode(await pipe.get(self.world.key))
                    seconds, micros = await self.world.redis.time()
                    now = float(seconds) + float(micros) / 1e6
                    own = mailbox_actor(state, scope, now)
                    raw = await pipe.get(body_key)
                    message = self._resolve_content(raw, initial, scope, state, now)
                    if message is None:
                        return False
                    if (
                        message.epoch != state.epoch
                        or message.expires_at <= now
                        or not participant(message, own)
                    ):
                        raise ValueError("world_message_unavailable")
                    if change is not None:
                        change(message, state, now)
                    message, encoded = self._validated_content(message)
                    indexes = [self.decode_index(await pipe.get(key)) for key in index_keys]
                    pipe.multi()
                    pipe.set(body_key, encoded, exat=int(message.expires_at))
                    for key, index in zip(index_keys, indexes, strict=True):
                        index.ids = [item for item in index.ids if item != message_id]
                        index.ids = [*index.ids, message_id][-MESSAGE_INBOX_LIMIT:]
                        pipe.set(key, index.model_dump_json(), ex=MESSAGE_TTL)
                    await pipe.execute()
                    return True
            except WatchError:
                continue
        raise WorldUnavailable("world_message_contention")

    @classmethod
    def _validated_content(cls, message: StoredMessage) -> tuple[StoredMessage, str]:
        # Assignment on nested Pydantic instances is not validation. Rebuild the
        # whole tree before the transactional write or its capacity reservation.
        """Revalidate the whole mutated body and reserve pending-variant bytes before serialization."""
        try:
            message = StoredMessage.model_validate(message.model_dump())
        except ValidationError:
            raise WorldUnavailable("world_message_corrupt") from None
        cls.require_translation_capacity(message)
        encoded = message.model_dump_json()
        if len(encoded.encode("utf-8")) > MAX_BODY_BYTES:
            raise WorldUnavailable("world_message_limit")
        return message, encoded

    def _resolve_content(
        self,
        raw: str | bytes | None,
        initial: StoredMessage | None,
        scope: MessageScope,
        state: WorldState,
        now: float,
    ) -> StoredMessage | None:
        """Resolve initial staging versus an existing body without accepting a conflicting duplicate."""
        if initial is not None:
            self._validate_initial(initial, scope, state, now)
            if raw is None:
                return initial.model_copy(deep=True)
            if self.decode(raw) != initial:
                raise ValueError("world_message_conflict")
            return None
        if raw is None:
            raise ValueError("world_message_unavailable")
        return self.decode(raw)

    @staticmethod
    def _validate_initial(
        message: StoredMessage, scope: MessageScope, state: WorldState, now: float
    ) -> None:
        """Verify a new body's live pair, immutable identities and bounded lifetime."""
        own, other = message_pair(state, scope, message.recipient.public_id, now)
        if (
            (
                message.sender.account,
                message.sender.public_id,
                message.sender.alias,
                message.recipient.account,
                message.recipient.alias,
            )
            != (own.account_id, own.public_id, own.alias, other.account_id, other.alias)
            or message.expires_at > message.created_at + MESSAGE_TTL
            or message.created_at > now + 5
        ):
            raise ValueError("world_message_unavailable")
