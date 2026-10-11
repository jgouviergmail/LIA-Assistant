"""Durable one-use proposal attempts; a lost import acknowledgement never buys another click."""

import asyncio
import uuid
from dataclasses import dataclass, replace
from uuid import UUID

from src.domains.skills.import_commit import SkillImportCompletionUnknown
from src.domains.skills.import_hooks import BeforeSkillSwap
from src.domains.skills.import_service import SkillImportService
from src.domains.skills.models import Skill
from src.domains.skills.proposal_errors import (
    COMPLETION_UNKNOWN,
    STALE,
    UNAVAILABLE,
    ProposalRefusal,
)
from src.domains.skills.proposals import ProposalStore, SkillProposal
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ProposalAttempt:
    store: ProposalStore
    original: SkillProposal
    attempted: SkillProposal
    committed: bool = False

    async def settle(self, changed: SkillProposal) -> None:
        try:
            await self.store.transition(self.attempted, changed)
        except Exception as error:
            # The pre-effect installing marker survives; the next click refuses.
            logger.warning("skill_proposal_settlement_pending", error_type=type(error).__name__)


async def begin_proposal_attempt(store: ProposalStore, proposal: SkillProposal) -> ProposalAttempt:
    attempted = replace(proposal, status="installing", attempt_id=uuid.uuid4().hex)
    try:
        accepted = await store.transition(proposal, attempted)
    except Exception as error:
        raise ProposalRefusal(UNAVAILABLE) from error
    if not accepted:
        raise ProposalRefusal(STALE)
    return ProposalAttempt(store, proposal, attempted)


async def execute_proposal_attempt(
    service: SkillImportService,
    attempt: ProposalAttempt,
    *,
    owner_id: UUID,
    before_swap: BeforeSkillSwap,
    before_commit: BeforeSkillSwap,
) -> SkillProposal:
    def committed(skill: Skill) -> None:
        attempt.committed = True

    cache_pending = False
    try:
        await service.import_files(
            attempt.original.files,
            owner_id=owner_id,
            before_swap=before_swap,
            before_commit=before_commit,
            after_commit=committed,
        )
        attempt.committed = True
    except SkillImportCompletionUnknown as error:
        await attempt.settle(replace(attempt.attempted, status="unknown"))
        raise ProposalRefusal(COMPLETION_UNKNOWN) from error
    except (Exception, asyncio.CancelledError) as error:
        if not attempt.committed:
            await attempt.settle(attempt.original)
            raise
        cache_pending = True
        logger.warning("skill_proposal_cache_refresh_pending", error_type=type(error).__name__)
        if isinstance(error, asyncio.CancelledError):
            await attempt.settle(replace(attempt.attempted.installed(), cache_refresh_pending=True))
            raise
    installed = replace(attempt.attempted.installed(), cache_refresh_pending=cache_pending)
    await attempt.settle(installed)
    return installed
