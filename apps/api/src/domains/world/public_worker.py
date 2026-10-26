"""One native accounted batch; no retry or late broadening of a public audience."""

import asyncio
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial
from typing import Literal
from uuid import UUID

import structlog

from src.core.config import settings
from src.domains.world.message_access import MessageAccess, MessageContext
from src.domains.world.message_attempts import MessageAttempts
from src.domains.world.message_content import MessageReceipt
from src.domains.world.messages import MailboxScope, MessageScope
from src.domains.world.public_mailbox import PublicMailbox
from src.domains.world.public_models import PublicContent
from src.domains.world.public_policy import authorized_recipients
from src.domains.world.public_translation import BatchTranslationPort, TranslatedBatch
from src.domains.world.schemas import WorldState
from src.domains.world.tickets import cookie_binding

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class PublicJob:
    cookie: str = field(repr=False)
    account: str
    scope: MailboxScope = field(repr=False)
    message: PublicContent = field(repr=False)
    token: UUID = field(repr=False)
    queued_until: datetime


class PublicWorker:
    def __init__(
        self,
        access: MessageAccess,
        mailbox: PublicMailbox,
        attempts: MessageAttempts,
        translate: BatchTranslationPort,
    ) -> None:
        """Bind public authorization, frozen-audience storage and durable ownership to one batch port."""
        self.access, self.mailbox, self.attempts, self.translate = (
            access,
            mailbox,
            attempts,
            translate,
        )

    async def _claim(self, job: PublicJob) -> bool:
        """Wait for this acknowledged job's paid slot only until its queue deadline."""
        while datetime.now(UTC) < job.queued_until:
            async with asyncio.timeout(settings.world_policy_timeout):
                if await self.attempts.start(
                    UUID(job.message.id), job.token, now=datetime.now(UTC)
                ):
                    return True
            await asyncio.sleep(0.5)
        return False

    async def _context(self, job: PublicJob) -> tuple[MessageContext, set[str]]:
        """Recheck the sender and return only recipients matching the frozen authorized audience."""
        context = await self.access.context(
            job.cookie, job.account, job.scope, set(job.message.recipients)
        )
        valid = authorized_recipients(
            job.message,
            context.scope,
            context.state,
            context.now,
            context.policy.languages,
        )
        return context, valid

    async def run(self, job: PublicJob) -> None:
        """Claim and translate once, then reauthorize publication and close failed or cancelled attempts."""
        try:
            if not await self._claim(job):
                await self._fail(job, False)
                return
            _, valid = await self._context(job)
            targets = tuple(
                sorted(
                    {
                        r.language
                        for account, r in job.message.recipients.items()
                        if account in valid and r.language != job.message.source_language
                    }
                )
            )
            if not targets:
                raise ValueError("world_public_no_targets")
            result = await self.translate(
                job.message.original,
                source=job.message.source_language,
                targets=targets,
                user_id=UUID(job.account),
                request_id=UUID(job.message.id),
            )
            if set(result.translations) != set(targets):
                raise ValueError("world_public_languages")
            context, _ = await self._context(job)
            async with asyncio.timeout(settings.world_policy_timeout):
                committed = await self.attempts.finish(
                    UUID(job.message.id), job.token, "succeeded", now=datetime.now(UTC)
                )
            if not committed:
                await self._fail(job, True)
                return

            await self._deliver(job, context, result)
        except asyncio.CancelledError:
            with suppress(Exception):
                await asyncio.shield(self._fail(job, True))
            raise
        except Exception as exc:
            logger.warning("world_public_translation_unavailable", error_type=type(exc).__name__)
            with suppress(Exception):
                await self._fail(job, isinstance(exc, TimeoutError))

    async def _deliver(
        self, job: PublicJob, context: MessageContext, result: TranslatedBatch
    ) -> None:
        """Acknowledge delivery only after the frozen-audience Redis body explicitly commits."""
        publish = partial(self._publish, context=context, result=result)
        if not await self.mailbox.change(job.message.id, context.scope, publish):
            raise ValueError("world_message_unavailable")
        async with asyncio.timeout(settings.world_policy_timeout):
            await self.attempts.mark_delivered(
                UUID(job.message.id), job.token, now=datetime.now(UTC)
            )

    @staticmethod
    def _publish(
        message: PublicContent,
        state: WorldState,
        now: float,
        context: MessageContext,
        result: TranslatedBatch,
    ) -> None:
        """Publish returned variants only to authorized frozen recipients and record payer usage."""
        valid = authorized_recipients(message, context.scope, state, now, context.policy.languages)
        for language, variant in message.variants.items():
            text = result.translations.get(language)
            variant.text = text
            variant.status = "translated" if text is not None else "failed"
        for account, recipient in message.recipients.items():
            if recipient.language == message.source_language:
                continue
            recipient.delivery = (
                "authorized"
                if account in valid and recipient.language in result.translations
                else "unavailable"
            )
        usage = result.usage
        message.receipt = MessageReceipt(
            run_id="world_message_" + UUID(message.id).hex,
            tokens_in=usage.tokens_in,
            tokens_out=usage.tokens_out,
            cost_eur=float(usage.cost_eur) if usage.cost_eur > 0 else None,
        )
        message.status = "translated"

    async def _fail(self, job: PublicJob, uncertain: bool) -> None:
        """Close the owned attempt and mark pending public variants without exposing provider output."""
        status: Literal["uncertain", "failed"] = "uncertain" if uncertain else "failed"
        async with asyncio.timeout(settings.world_policy_timeout):
            await self.attempts.finish(
                UUID(job.message.id), job.token, status, now=datetime.now(UTC)
            )
        state, _ = await self.access.world.read()
        scope = MessageScope(
            job.account,
            cookie_binding(job.cookie),
            job.scope.controller,
            job.scope.epoch,
            frozenset(state.actors),
            frozenset(),
            settings.world_idle_seconds,
        )

        def fail(message: PublicContent, _state: WorldState, _now: float) -> None:
            """Replace only pending variants with the job's failed or uncertain outcome."""
            if message.status == "pending":
                message.status = status
            for variant in message.variants.values():
                if variant.status == "pending":
                    variant.text, variant.status = None, status

        await self.mailbox.change(job.message.id, scope, fail)
