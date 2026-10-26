"""Bounded owned asynchronous translation, without recovery of uncertain spend."""

import asyncio
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial
from typing import Literal, Protocol
from uuid import UUID

import structlog

from src.core.config import settings
from src.core.i18n_types import Language
from src.domains.world.mailbox import WorldMailbox
from src.domains.world.message_access import MessageAccess, MessageContext
from src.domains.world.message_attempts import MessageAttempts
from src.domains.world.message_content import MessageReceipt, StoredMessage
from src.domains.world.messages import MailboxScope, MessageScope, message_pair
from src.domains.world.schemas import WorldState
from src.domains.world.tickets import cookie_binding
from src.domains.world.translation import TranslatedMessage

logger = structlog.get_logger(__name__)


class TranslationPort(Protocol):
    async def __call__(
        self, text: str, *, source: Language, target: Language, user_id: UUID, request_id: UUID
    ) -> TranslatedMessage:
        """Translate one literal body through the accounting port for this payer and request."""
        ...


@dataclass(frozen=True)
class TranslationJob:
    cookie: str = field(repr=False)
    account: str
    scope: MailboxScope = field(repr=False)
    message: StoredMessage = field(repr=False)
    request_id: str
    kind: Literal["send", "translate"]
    token: UUID = field(repr=False)
    target: Language
    other_controller: str | None
    queued_until: datetime


class MessageWorker:
    def __init__(
        self,
        access: MessageAccess,
        mailbox: WorldMailbox,
        attempts: MessageAttempts,
        translate: TranslationPort,
    ) -> None:
        """Bind authorization, publication and durable attempt ownership to one translation port."""
        self.access, self.mailbox, self.attempts, self.translate = (
            access,
            mailbox,
            attempts,
            translate,
        )

    async def _claim(self, job: TranslationJob) -> bool:
        """Wait only until the job's queue deadline for an owned paid execution slot."""
        while datetime.now(UTC) < job.queued_until:
            async with asyncio.timeout(settings.world_policy_timeout):
                if await self.attempts.start(
                    UUID(job.request_id), job.token, now=datetime.now(UTC)
                ):
                    return True
            await asyncio.sleep(0.5)
        return False

    async def run(self, job: TranslationJob) -> None:
        """Claim once, authorize before and after translation, then publish or close failure/cancellation books."""
        try:
            if not await self._claim(job):
                await self._fail(job, "failed")
                return
            await self._authorized(job)
            result = await self.translate(
                job.message.original,
                source=job.message.source_language,
                target=job.target,
                user_id=UUID(job.account),
                request_id=UUID(job.request_id),
            )
            context = await self._authorized(job)
            if result.translation.language != job.target:
                raise ValueError("world_translation_language")
            async with asyncio.timeout(settings.world_policy_timeout):
                committed = await self.attempts.finish(
                    UUID(job.request_id), job.token, "succeeded", now=datetime.now(UTC)
                )
            if not committed:
                await self._fail(job, "uncertain")
                return

            await self._deliver(job, context, result)
        except asyncio.CancelledError:
            with suppress(Exception):
                await asyncio.shield(self._fail(job, "uncertain"))
            raise
        except Exception as exc:
            logger.warning("world_translation_unavailable", error_type=type(exc).__name__)
            with suppress(Exception):
                await self._fail(job, "uncertain" if isinstance(exc, TimeoutError) else "failed")

    async def _deliver(
        self, job: TranslationJob, context: MessageContext, result: TranslatedMessage
    ) -> None:
        """Acknowledge delivery only after the owned Redis variant explicitly commits."""
        publish = partial(self._publish, job, context.scope, result)
        if not await self.mailbox.change(job.message.id, context.scope, publish):
            raise ValueError("world_message_unavailable")
        async with asyncio.timeout(settings.world_policy_timeout):
            await self.attempts.mark_delivered(
                UUID(job.request_id), job.token, now=datetime.now(UTC)
            )

    @staticmethod
    def _publish(
        job: TranslationJob,
        scope: MessageScope,
        result: TranslatedMessage,
        message: StoredMessage,
        state: WorldState,
        now: float,
    ) -> None:
        """Publish only the matching pending variant, rechecking the recipient controller for a send."""
        if job.kind == "send":
            _, other = message_pair(state, scope, message.recipient.public_id, now)
            if other.controller != job.other_controller:
                raise ValueError("world_message_unavailable")
        variant = message.variants.get(job.target)
        if variant is None or variant.job_id != job.request_id or variant.status != "pending":
            raise ValueError("world_message_unavailable")
        variant.text, variant.status = result.translation.text, "translated"
        usage = result.usage
        variant.receipt = MessageReceipt(
            run_id="world_message_" + UUID(job.request_id).hex,
            tokens_in=usage.tokens_in,
            tokens_out=usage.tokens_out,
            cost_eur=float(usage.cost_eur) if usage.cost_eur > 0 else None,
        )

    async def _authorized(self, job: TranslationJob) -> MessageContext:
        """Revalidate participants, blocking, controller and target language before exposing output."""
        if job.kind == "translate":
            context = await self.access.context(
                job.cookie, job.account, job.scope, {job.message.sender.account}
            )
            if (
                job.account != job.message.recipient.account
                or job.message.sender.account not in context.policy.eligible
                or job.message.sender.account in context.policy.blocked
                or context.policy.languages.get(job.account) != job.target
            ):
                raise ValueError("world_message_unavailable")
            return context
        context = await self.access.context(job.cookie, job.account, job.scope)
        _, other = message_pair(
            context.state, context.scope, job.message.recipient.public_id, context.now
        )
        if (
            other.controller != job.other_controller
            or context.policy.languages.get(other.account_id) != job.target
        ):
            raise ValueError("world_message_unavailable")
        return context

    async def _fail(self, job: TranslationJob, status: Literal["failed", "uncertain"]) -> None:
        """Close the owned attempt and mark its pending variant without publishing model output."""
        async with asyncio.timeout(settings.world_policy_timeout):
            await self.attempts.finish(
                UUID(job.request_id), job.token, status, now=datetime.now(UTC)
            )
        # Failure publication never contains model output. A lost controller cannot
        # update even this status; its replacement sees the bounded pending deadline.
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

        def fail(message: StoredMessage, current: WorldState, timestamp: float) -> None:
            """Mark only this request's pending variant with the failed or uncertain outcome."""
            variant = message.variants.get(job.target)
            if variant and variant.job_id == job.request_id and variant.status == "pending":
                variant.status, variant.text = status, None

        await self.mailbox.change(job.message.id, scope, fail)
