"""The shared queue boundary preserves authorization, failure and commit facts."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.account_export.commands import queue_account_export
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("denial", ["disabled", "proof", "authority"])
async def test_no_export_is_queued_after_a_current_refusal(
    monkeypatch: pytest.MonkeyPatch, denial: str
) -> None:
    monkeypatch.setattr(settings, "account_export_enabled", denial != "disabled")
    db = AsyncMock()
    db.add = MagicMock()
    user = MagicMock(id=uuid4())
    check = AsyncMock(side_effect=AuthorizationError(detail={"error_code": denial.upper()}))
    with pytest.raises(AuthorizationError):
        await queue_account_export(db, user, check=check)
    db.add.assert_not_called()
    db.commit.assert_not_awaited()


async def test_receipt_records_committed_job_before_a_projection_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "account_export_enabled", True)
    db = AsyncMock()
    db.add = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute.return_value = result
    db.refresh.side_effect = RuntimeError("projection unavailable")
    receipt = PreferenceWriteReceipt()
    identity = uuid4()
    with pytest.raises(RuntimeError, match="projection unavailable"):
        await queue_account_export(
            db, MagicMock(id=uuid4()), job_id=identity, receipt=receipt, check=AsyncMock()
        )
    assert receipt.committed is True
    assert db.add.call_args.args[0].id == identity
    db.commit.assert_awaited_once()
