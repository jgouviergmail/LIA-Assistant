"""Atomic frozen audience and bounded ephemeral bodies; no public-room replay."""

import asyncio
import hashlib
from collections.abc import Callable

from pydantic import ValidationError
from redis.exceptions import WatchError

from src.domains.world.mailbox import MAX_BODY_BYTES, WorldMailbox
from src.domains.world.messages import (
    MESSAGE_INBOX_LIMIT,
    MESSAGE_TTL,
    MessageScope,
    mailbox_actor,
    message_pair,
)
from src.domains.world.public_models import PUBLIC_TRANSLATION_CHARS, PublicContent
from src.domains.world.schemas import WorldState
from src.domains.world.store import MAX_CAS_ATTEMPTS, WorldStore, WorldUnavailable


def audience_signature(message: PublicContent) -> tuple[object, ...]:
    """Freeze sender and recipient identities/controllers/languages across every body mutation."""
    return (
        message.id,
        message.epoch,
        message.sender.model_dump_json(),
        message.original,
        message.source_language,
        message.created_at,
        message.expires_at,
        tuple(
            (account, r.public_id, r.controller, r.language)
            for account, r in sorted(message.recipients.items())
        ),
    )


class PublicMailbox:
    def __init__(self, world: WorldStore) -> None:
        """Bind public body and recipient-index keys to the exact authority namespace."""
        self.world = world
        self.prefix = WorldMailbox(world).prefix

    def body_key(self, message: str) -> str:
        """Derive a hashed ephemeral public-body key from the stable intent identifier."""
        return self.prefix + "public-body:" + hashlib.sha256(message.encode()).hexdigest()

    def inbox_key(self, account: str) -> str:
        """Derive the recipient's bounded public inbox index in this namespace."""
        return self.prefix + "public-inbox:" + account

    @staticmethod
    def decode(raw: str | bytes) -> PublicContent:
        """Decode a bounded strict public body or fail closed on corruption."""
        if len(raw) > MAX_BODY_BYTES:
            raise WorldUnavailable("world_public_limit")
        try:
            return PublicContent.model_validate_json(raw)
        except ValidationError:
            raise WorldUnavailable("world_public_corrupt") from None

    @staticmethod
    def _encoded(message: PublicContent) -> str:
        """Revalidate a public body and reserve all pending translation bytes before writing."""
        message = PublicContent.model_validate(message.model_dump())
        encoded = message.model_dump_json()
        reserved = sum(v.status == "pending" for v in message.variants.values()) * (
            PUBLIC_TRANSLATION_CHARS * 4 + 512
        )
        if len(encoded.encode()) + reserved > MAX_BODY_BYTES:
            raise WorldUnavailable("world_public_capacity")
        return encoded

    async def inbox(self, scope: MessageScope) -> list[PublicContent]:
        """Read unexpired public messages only for their original sender or frozen recipients."""
        async with asyncio.timeout(self.world.timeout):
            state, now = await self.world.read()
            own = mailbox_actor(state, scope, now)
            index = WorldMailbox.decode_index(
                await self.world.redis.get(self.inbox_key(scope.account))
            )
            if not index.ids:
                return []
            values = await self.world.redis.mget([self.body_key(key) for key in index.ids])
            result = []
            for raw in values:
                if raw is None:
                    continue
                message = self.decode(raw)
                recipient = message.recipients.get(scope.account)
                member = (
                    message.sender.account == scope.account
                    and message.sender.public_id == own.public_id
                ) or (recipient is not None and recipient.public_id == own.public_id)
                if member and message.epoch == state.epoch and message.expires_at > now:
                    result.append(message)
            return result

    async def stage(self, message: PublicContent, scope: MessageScope) -> bool:
        """Stage one frozen public audience and its bounded recipient indexes under CAS."""
        async with asyncio.timeout(self.world.timeout):
            return await self._write(message.id, scope, message, None)

    async def change(
        self,
        message: str,
        scope: MessageScope,
        change: Callable[[PublicContent, WorldState, float], None],
    ) -> bool:
        """Mutate a public body while preserving its original sender and frozen audience."""
        async with asyncio.timeout(self.world.timeout):
            return await self._write(message, scope, None, change)

    @staticmethod
    def _validate_initial(
        message: PublicContent, scope: MessageScope, state: WorldState, now: float
    ) -> None:
        """Validate a new sender, audience controllers and lifetime against current authority."""
        own = mailbox_actor(state, scope, now)
        if (message.sender.account, message.sender.public_id, message.sender.alias) != (
            own.account_id,
            own.public_id,
            own.alias,
        ):
            raise ValueError("world_message_unavailable")
        if message.created_at > now + 5 or message.expires_at > message.created_at + MESSAGE_TTL:
            raise ValueError("world_message_unavailable")
        for account, recipient in message.recipients.items():
            _, other = message_pair(state, scope, recipient.public_id, now)
            if other.account_id != account or other.controller != recipient.controller:
                raise ValueError("world_message_unavailable")

    def _current(
        self,
        raw: str | bytes | None,
        initial: PublicContent | None,
        scope: MessageScope,
        state: WorldState,
        now: float,
    ) -> PublicContent | None:
        """Resolve initial staging or an existing public body without accepting a conflicting replay."""
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
    def _require_owned(message: PublicContent, account: str, epoch: str, now: float) -> None:
        """Require the original sender, current epoch and an unexpired body before mutation."""
        if message.sender.account != account or message.epoch != epoch or message.expires_at <= now:
            raise ValueError("world_message_unavailable")

    async def _write(
        self,
        message_id: str,
        scope: MessageScope,
        initial: PublicContent | None,
        change: Callable[[PublicContent, WorldState, float], None] | None,
    ) -> bool:
        """Commit watched world/body/index mutations only while ownership and audience remain unchanged."""
        body = self.body_key(message_id)
        owners = sorted({initial.sender.account, *initial.recipients}) if initial else []
        indexes = [self.inbox_key(owner) for owner in owners]
        for _ in range(MAX_CAS_ATTEMPTS):
            try:
                async with self.world.redis.pipeline(transaction=True) as pipe:
                    await pipe.watch(self.world.key, body, *indexes)
                    state = self.world.decode(await pipe.get(self.world.key))
                    seconds, micros = await self.world.redis.time()
                    now = float(seconds) + float(micros) / 1e6
                    own = mailbox_actor(state, scope, now)
                    raw = await pipe.get(body)
                    message = self._current(raw, initial, scope, state, now)
                    if message is None:
                        return False
                    self._require_owned(message, own.account_id, state.epoch, now)
                    signature = audience_signature(message)
                    if change is not None:
                        change(message, state, now)
                    if signature != audience_signature(message):
                        raise ValueError("world_public_audience_changed")
                    encoded = self._encoded(message)
                    prior = [WorldMailbox.decode_index(await pipe.get(key)) for key in indexes]
                    pipe.multi()
                    pipe.set(body, encoded, exat=int(message.expires_at))
                    for key, index in zip(indexes, prior, strict=True):
                        index.ids = [
                            *filter(lambda value: value != message_id, index.ids),
                            message_id,
                        ][-MESSAGE_INBOX_LIMIT:]
                        pipe.set(key, index.model_dump_json(), ex=MESSAGE_TTL)
                    await pipe.execute()
                    return True
            except WatchError:
                continue
        raise WorldUnavailable("world_public_contention")
