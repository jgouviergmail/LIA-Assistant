"""A known saved restore retains its indexing follow-up across a failed reread."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.meetings.report_gateway import SavedMeetingReports
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.meeting_reports import ReportWriteConfirmation

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "committed,no_op,expected", [(False, False, 0), (True, False, 1), (True, True, 0)]
)
async def test_indexing_requires_known_ack_and_is_retained_after_read_failure(
    committed: bool, no_op: bool, expected: int
) -> None:
    receipt = PreferenceWriteReceipt()

    async def restore(*args, **kwargs) -> None:
        receipt.committed = committed
        receipt.no_op = no_op
        raise OSError("read after commit failed")

    confirmation = ReportWriteConfirmation(validate=AsyncMock(), check=AsyncMock(), receipt=receipt)
    identity = uuid4()
    with (
        patch("src.domains.meetings.report_gateway.MeetingService") as service,
        patch("src.domains.meetings.indexing.schedule_reindex") as index,
    ):
        service.return_value.reset_report = AsyncMock(side_effect=restore)
        with pytest.raises(OSError):
            await SavedMeetingReports().restore(MagicMock(), uuid4(), identity, confirmation)
    assert index.call_count == expected
