"""Commit evidence and the durable attempt fence outlive later cache/Redis failures."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.skills.import_service import SkillImportService
from src.domains.skills.models import Skill
from src.domains.skills.proposal_attempt import ProposalAttempt, execute_proposal_attempt
from src.domains.skills.proposals import ProposalStore, SkillProposal
from tests.unit.domains.skills.test_proposal_service import OWNER, _proposal

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled", [False, True])
async def test_known_commit_survives_cache_failure(cancelled: bool) -> None:
    store = MagicMock(spec=ProposalStore)
    attempt = ProposalAttempt(
        store, _proposal(), _proposal(status="installing", attempt_id="b" * 32)
    )
    service = MagicMock(spec=SkillImportService)

    async def import_files(*args: object, **kwargs: object) -> None:
        after_commit = kwargs["after_commit"]
        assert callable(after_commit)
        after_commit(MagicMock(spec=Skill))
        if cancelled:
            raise asyncio.CancelledError
        raise ConnectionError("cache down")

    service.import_files.side_effect = import_files
    if cancelled:
        with pytest.raises(asyncio.CancelledError):
            await execute_proposal_attempt(
                service, attempt, owner_id=OWNER, before_swap=AsyncMock(), before_commit=AsyncMock()
            )
    else:
        result = await execute_proposal_attempt(
            service, attempt, owner_id=OWNER, before_swap=AsyncMock(), before_commit=AsyncMock()
        )
        assert result.status == "installed" and result.cache_refresh_pending
    assert attempt.committed
    settled: SkillProposal = store.transition.await_args.args[1]
    assert settled.status == "installed" and settled.cache_refresh_pending
    service.import_files.assert_awaited_once()


@pytest.mark.asyncio
async def test_redis_settlement_loss_retains_known_commit_and_no_second_write() -> None:
    store = MagicMock(spec=ProposalStore)
    store.transition.side_effect = ConnectionError("lost Redis")
    attempt = ProposalAttempt(
        store, _proposal(), _proposal(status="installing", attempt_id="b" * 32)
    )
    service = MagicMock(spec=SkillImportService)
    result = await execute_proposal_attempt(
        service, attempt, owner_id=OWNER, before_swap=AsyncMock(), before_commit=AsyncMock()
    )
    assert result.status == "installed" and attempt.committed
    service.import_files.assert_awaited_once()
