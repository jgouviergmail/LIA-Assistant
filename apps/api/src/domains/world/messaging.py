"""Private human correspondence: native authority, durable spend and ephemeral text."""

import asyncio
from datetime import UTC, datetime
from functools import partial
from uuid import UUID

import structlog
from pydantic import Field
from redis.exceptions import RedisError

from src.core.config import settings
from src.core.i18n import normalize_language
from src.core.i18n_types import Language
from src.domains.world.mailbox import WorldMailbox
from src.domains.world.message_access import MessageAccess, MessageContext
from src.domains.world.message_attempts import (
    ATTEMPT_SECONDS,
    QUEUE_SECONDS,
    MessageAttempts,
)
from src.domains.world.message_content import (
    MessageAddress,
    MessageVariant,
    MessageView,
    StoredMessage,
    project_message,
)
from src.domains.world.message_identity import message_fingerprint
from src.domains.world.message_results import AcceptedSend, MessageAccepted
from src.domains.world.message_worker import (
    MessageWorker,
    TranslationJob,
    TranslationPort,
)
from src.domains.world.messages import (
    MESSAGE_TTL,
    MailboxScope,
    MessageRequest,
    MessageStatusRequest,
    RetranslateRequest,
    TimedMessageRequest,
    message_pair,
)
from src.domains.world.public_messaging import PublicMessaging
from src.domains.world.public_models import (
    PUBLIC_RESPONSE_BYTES,
    PublicContent,
    PublicMessageView,
    project_public,
)
from src.domains.world.public_translation import (
    BatchTranslationPort,
    translate_public_message,
)
from src.domains.world.schemas import StrictModel, WorldState
from src.domains.world.store import WorldStore, WorldUnavailable
from src.domains.world.translation import translate_message


class MailboxView(StrictModel):
    server_time: float = Field(
        default=0,
        ge=0,
        description="Authoritative Unix-seconds clock anchor for client freshness and expiry display.",
    )
    ttl_seconds: int = Field(
        default=MESSAGE_TTL,
        description="Declared lifetime in seconds for this ticket or ephemeral mailbox content.",
    )
    messages: list[MessageView] = Field(
        default_factory=list,
        max_length=50,
        description="Bounded recipient-scoped private message projections.",
    )
    truncated: bool = Field(
        default=False,
        description="True when the private response budget omitted whole messages.",
    )
    public_messages: list[PublicMessageView] = Field(
        default_factory=list,
        max_length=50,
        description="Bounded own-language views of messages in this account frozen public audiences.",
    )
    public_available: bool = Field(
        default=True,
        description="Whether the public correspondence projection was available for this read.",
    )
    public_truncated: bool = Field(
        default=False,
        description="True when the public response budget omitted whole messages.",
    )


def _fingerprint(account: str, payload: TimedMessageRequest, extra: str = "") -> str:
    """Bind a private intent to its account and complete request with the instance secret."""
    return message_fingerprint(settings.secret_key, account, payload, extra)


def _reusable(message: StoredMessage, target: Language, now: float) -> bool:
    """Check for original-language text or a live pending/translated variant without new spending."""
    if target == message.source_language:
        return True
    variant = message.variants.get(target)
    return variant is not None and (
        (variant.status == "translated" and variant.text is not None)
        or (variant.status == "pending" and variant.deadline > now)
    )


def _ack(message: str, status: str, ready: bool) -> MessageAccepted:
    """Project only an acknowledged durable outcome; unresolved staging remains uncertain."""
    if not ready or status in {"reserved", "succeeded", "failed", "uncertain"}:
        return MessageAccepted(id=message, status="uncertain")
    return MessageAccepted(
        id=message,
        status="delivered" if status == "delivered" else "pending",
    )


def _pending_variant(request_id: str, account: str, now: float) -> MessageVariant:
    """Reserve a payer-owned pending translation until its queue and execution deadlines."""
    return MessageVariant(
        job_id=request_id,
        payer=account,
        status="pending",
        deadline=now + QUEUE_SECONDS + ATTEMPT_SECONDS,
    )


def _stage_retranslation(
    source: StoredMessage,
    account: str,
    target: Language,
    needs_model: bool,
    request_id: str,
    message: StoredMessage,
    _state: WorldState,
    now: float,
) -> bool:
    """Reserve a missing variant only for the unchanged message and its original recipient."""
    if message.recipient.account != account or message.original != source.original:
        raise ValueError("world_message_unavailable")
    if _reusable(message, target, now):
        return False
    if not needs_model:
        raise ValueError("world_translation_changed")
    message.variants[target] = _pending_variant(request_id, account, now)
    return True


class WorldMessaging:
    def __init__(
        self,
        world: WorldStore,
        *,
        translate: TranslationPort = translate_message,
        translate_public: BatchTranslationPort = translate_public_message,
    ) -> None:
        """Compose authoritative access, durable fences, bounded mailboxes and translation ports."""
        self.world = world
        self.public = PublicMessaging(world, translate=translate_public)
        self.mailbox = WorldMailbox(world)
        self.access = MessageAccess(world)
        self.attempts = MessageAttempts(world.message_namespace)
        self.worker = MessageWorker(self.access, self.mailbox, self.attempts, translate)

    async def status(
        self, cookie: str, account: str, payload: MessageStatusRequest
    ) -> MessageAccepted:
        """Return an owned durable request outcome after live session/controller authorization."""
        await self.access.context(cookie, account, payload)
        async with asyncio.timeout(settings.world_policy_timeout):
            status = await self.attempts.owned_status(
                UUID(payload.id), UUID(account), now=datetime.now(UTC)
            )
        if status is None:
            raise ValueError("world_message_unavailable")
        return MessageAccepted(id=payload.id, status=status)

    async def send(self, cookie: str, account: str, payload: MessageRequest) -> AcceptedSend:
        """Fence a private intent, stage ephemeral text and return at most one newly owned translation job."""
        context = await self.access.context(cookie, account, payload)
        own, other = message_pair(context.state, context.scope, payload.recipient, context.now)
        source = normalize_language(context.policy.language)
        target = context.policy.languages[other.account_id]
        translated = source != target
        if translated and not payload.translation_consent:
            raise ValueError("world_translation_consent_required")
        payload.require_fresh(context.now)
        fingerprint = _fingerprint(account, payload)
        async with asyncio.timeout(settings.world_policy_timeout):
            row, created = await self.attempts.enqueue(
                UUID(payload.id),
                UUID(account),
                UUID(other.account_id),
                fingerprint,
                translated=translated,
                now=datetime.now(UTC),
            )
        if not created:
            return AcceptedSend(_ack(payload.id, row.status, row.content_ready))
        message = StoredMessage(
            id=payload.id,
            epoch=payload.epoch,
            sender=MessageAddress(account=own.account_id, public_id=own.public_id, alias=own.alias),
            recipient=MessageAddress(
                account=other.account_id, public_id=other.public_id, alias=other.alias
            ),
            original=payload.text,
            source_language=source,
            created_at=context.now,
            expires_at=context.now + MESSAGE_TTL,
        )
        if translated:
            message.variants[target] = _pending_variant(payload.id, account, context.now)
        await self.mailbox.stage(message, context.scope)
        async with asyncio.timeout(settings.world_policy_timeout):
            if not await self.attempts.mark_ready(
                UUID(payload.id), row.token, now=datetime.now(UTC)
            ):
                return AcceptedSend(MessageAccepted(id=payload.id, status="uncertain"))
        if not translated:
            return AcceptedSend(MessageAccepted(id=payload.id, status="delivered"))
        job = TranslationJob(
            cookie=cookie,
            account=account,
            scope=MailboxScope(epoch=payload.epoch, controller=payload.controller),
            message=message,
            request_id=payload.id,
            kind="send",
            token=row.token,
            target=target,
            other_controller=other.controller,
            queued_until=row.queued_until,
        )
        return AcceptedSend(MessageAccepted(id=payload.id, status="pending"), self.worker.run(job))

    async def retranslate(
        self, cookie: str, account: str, payload: RetranslateRequest
    ) -> AcceptedSend:
        """Reuse an authorized variant or reserve one explicitly consented recipient-paid translation."""
        context = await self.access.context(cookie, account, payload)
        messages = await self.mailbox.inbox(context.scope)
        source = next((message for message in messages if message.id == payload.message_id), None)
        if source is None or source.recipient.account != account:
            raise ValueError("world_message_unavailable")
        context = await self.access.context(cookie, account, payload, {source.sender.account})
        if (
            source.sender.account not in context.policy.eligible
            or source.sender.account in context.policy.blocked
        ):
            raise ValueError("world_message_unavailable")
        payload.require_fresh(context.now)
        target = normalize_language(context.policy.language)
        needs_model = not _reusable(source, target, context.now)
        if needs_model:
            candidate = source.model_copy(deep=True)
            candidate.variants[target] = _pending_variant(payload.id, account, context.now)
            self.mailbox.require_translation_capacity(candidate)
        fingerprint = _fingerprint(account, payload, source.original + "\n" + target)
        async with asyncio.timeout(settings.world_policy_timeout):
            row, created = await self.attempts.enqueue(
                UUID(payload.id),
                UUID(account),
                UUID(source.sender.account),
                fingerprint,
                translated=needs_model,
                now=datetime.now(UTC),
            )
        if not created:
            return AcceptedSend(_ack(payload.id, row.status, row.content_ready))

        stage = partial(_stage_retranslation, source, account, target, needs_model, payload.id)
        dispatch = await self.mailbox.transition(source.id, context.scope, stage)
        async with asyncio.timeout(settings.world_policy_timeout):
            ready = (
                await self.attempts.mark_ready(UUID(payload.id), row.token, now=datetime.now(UTC))
                if dispatch
                else await self.attempts.mark_cached(
                    UUID(payload.id), row.token, now=datetime.now(UTC)
                )
            )
        if not ready:
            return AcceptedSend(MessageAccepted(id=payload.id, status="uncertain"))
        if not dispatch:
            return AcceptedSend(MessageAccepted(id=payload.id, status="delivered"))
        job = TranslationJob(
            cookie=cookie,
            account=account,
            scope=MailboxScope(epoch=payload.epoch, controller=payload.controller),
            message=source,
            request_id=payload.id,
            kind="translate",
            token=row.token,
            target=target,
            other_controller=None,
            queued_until=row.queued_until,
        )
        return AcceptedSend(MessageAccepted(id=payload.id, status="pending"), self.worker.run(job))

    async def read(self, cookie: str, account: str, payload: MailboxScope) -> MailboxView:
        """Revalidate ownership and return bounded private/public correspondence without provider calls."""
        context = await self.access.context(cookie, account, payload)
        messages = await self.mailbox.inbox(context.scope)
        public_messages = []
        public_available = True
        try:
            public_messages = await self.public.mailbox.inbox(context.scope)
        except (WorldUnavailable, RedisError, TimeoutError) as exc:
            structlog.get_logger(__name__).warning(
                "world_public_read_unavailable", error_type=type(exc).__name__
            )
            public_available = False
        participants = {
            address.account
            for message in messages
            for address in (message.sender, message.recipient)
        }
        participants.update(message.sender.account for message in public_messages)
        context = await self.access.context(cookie, account, payload, participants)
        language = normalize_language(context.policy.language)
        result = MailboxView(server_time=context.now, public_available=public_available)
        size = 0
        for message in reversed(messages):
            others = {message.sender.account, message.recipient.account} - {account}
            if others & context.policy.blocked or not others <= context.policy.eligible:
                continue
            view = project_message(message, account, language, context.now)
            item_size = len(view.model_dump_json().encode("utf-8"))
            if len(result.messages) >= 50 or size + item_size > 128 * 1024:
                result.truncated = True
                break
            result.messages.append(view)
            size += item_size
        result.messages.reverse()
        self._project_public(public_messages, context, result)
        return result

    @staticmethod
    def _project_public(
        messages: list[PublicContent], context: MessageContext, result: MailboxView
    ) -> None:
        """Build bounded own-language public views and explicitly report whole-message truncation."""
        account = context.scope.account
        language = normalize_language(context.policy.language)
        public_size = 0
        for public_message in reversed(messages):
            if (
                public_message.sender.account in context.policy.blocked
                or public_message.sender.account not in context.policy.eligible
            ):
                continue
            public_view = project_public(public_message, account, language, context.now)
            item_size = len(public_view.model_dump_json().encode())
            if len(result.public_messages) >= 50 or public_size + item_size > PUBLIC_RESPONSE_BYTES:
                result.public_truncated = True
                break
            result.public_messages.append(public_view)
            public_size += item_size
        result.public_messages.reverse()
