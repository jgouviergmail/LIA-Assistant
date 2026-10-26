"""A public intent freezes its audience once and uses one native spend tombstone."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from src.core.config import settings
from src.core.i18n import normalize_language
from src.domains.world.message_access import MessageAccess
from src.domains.world.message_attempts import (
    ATTEMPT_SECONDS,
    QUEUE_SECONDS,
    MessageAttempts,
)
from src.domains.world.message_content import MessageAddress
from src.domains.world.message_identity import message_fingerprint
from src.domains.world.message_results import AcceptedSend, MessageAccepted
from src.domains.world.messages import MESSAGE_TTL, MailboxScope
from src.domains.world.public_mailbox import PublicMailbox
from src.domains.world.public_models import (
    PublicContent,
    PublicMessageRequest,
    PublicVariant,
)
from src.domains.world.public_policy import capture_recipients
from src.domains.world.public_translation import (
    BatchTranslationPort,
    translate_public_message,
)
from src.domains.world.public_worker import PublicJob, PublicWorker
from src.domains.world.store import WorldStore


class PublicMessaging:
    def __init__(
        self, world: WorldStore, *, translate: BatchTranslationPort = translate_public_message
    ) -> None:
        """Compose fresh audience policy, durable fences and the accounted batch translation port."""
        self.world = world
        self.access = MessageAccess(world)
        self.mailbox = PublicMailbox(world)
        self.attempts = MessageAttempts(world.message_namespace)
        self.worker = PublicWorker(self.access, self.mailbox, self.attempts, translate)

    async def _status(self, message: str, account: str) -> MessageAccepted:
        """Read this payer's durable public-intent outcome without replaying translation."""
        async with asyncio.timeout(settings.world_policy_timeout):
            status = await self.attempts.owned_status(
                UUID(message), UUID(account), now=datetime.now(UTC)
            )
        return MessageAccepted(id=message, status=status or "uncertain")

    async def send(self, cookie: str, account: str, payload: PublicMessageRequest) -> AcceptedSend:
        """Freeze eligible recipients, reserve one intent and dispatch at most one consented language batch."""
        context = await self.access.context(cookie, account, payload)
        payload.require_fresh(context.now)
        fingerprint = message_fingerprint(settings.secret_key, account, payload)
        async with asyncio.timeout(settings.world_policy_timeout):
            existing = await self.attempts.replay(
                UUID(payload.id), UUID(account), UUID(account), fingerprint
            )
        if existing is not None:
            return AcceptedSend(await self._status(payload.id, account))
        recipients = capture_recipients(context)
        source = normalize_language(context.policy.language)
        targets = {r.language for r in recipients.values()} - {source}
        if targets and not payload.translation_consent:
            raise ValueError("world_translation_consent_required")
        async with asyncio.timeout(settings.world_policy_timeout):
            row, created = await self.attempts.enqueue(
                UUID(payload.id),
                UUID(account),
                UUID(account),
                fingerprint,
                translated=bool(targets),
                now=datetime.now(UTC),
            )
        if not created:
            return AcceptedSend(await self._status(payload.id, account))
        own = context.state.actors[account]
        message = PublicContent(
            id=payload.id,
            epoch=payload.epoch,
            sender=MessageAddress(account=account, public_id=own.public_id, alias=own.alias),
            recipients=recipients,
            original=payload.text,
            source_language=source,
            created_at=context.now,
            expires_at=context.now + MESSAGE_TTL,
            status="pending" if targets else "original",
        )
        for language in targets:
            message.variants[language] = PublicVariant(
                job_id=payload.id,
                payer=account,
                status="pending",
                deadline=context.now + QUEUE_SECONDS + ATTEMPT_SECONDS,
            )
        await self.mailbox.stage(message, context.scope)
        async with asyncio.timeout(settings.world_policy_timeout):
            ready = await self.attempts.mark_ready(
                UUID(payload.id), row.token, now=datetime.now(UTC)
            )
        if not ready:
            return AcceptedSend(MessageAccepted(id=payload.id, status="uncertain"))
        if not targets:
            return AcceptedSend(MessageAccepted(id=payload.id, status="delivered"))
        job = PublicJob(
            cookie,
            account,
            MailboxScope(epoch=payload.epoch, controller=payload.controller),
            message,
            row.token,
            row.queued_until,
        )
        return AcceptedSend(MessageAccepted(id=payload.id, status="pending"), self.worker.run(job))
