"""Confirmed templates validate before mutation and acknowledge only known commits."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import OperationalError

from src.core.exceptions import ResourceConflictError
from src.domains.meetings.schemas import MeetingTemplateCreate, TemplateSection
from src.domains.meetings.template_service import MeetingTemplateService

pytestmark = pytest.mark.unit


def _service():
    db = MagicMock()
    db.scalar = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    db.commit = AsyncMock()
    service = MeetingTemplateService(db)
    service.repo = AsyncMock()
    service.repo.count_for_user.return_value = 0
    service.repo.create.return_value = SimpleNamespace(
        id=uuid4(),
        name="Controlled",
        description=None,
        category="custom",
        builtin_key=None,
        sections=[
            {
                "key": "summary",
                "label": "Summary",
                "instruction": "Literal template instruction",
                "kind": "paragraph",
            }
        ],
    )
    return service


def _request() -> MeetingTemplateCreate:
    return MeetingTemplateCreate(
        name="Controlled",
        sections=[
            TemplateSection(
                key="summary",
                label="Summary",
                instruction="Literal template instruction",
                kind="paragraph",
            )
        ],
    )


async def test_changed_facts_are_refused_before_any_source_write() -> None:
    from src.domains.meetings.template_confirmation import TemplateWriteConfirmation
    from src.domains.users.preference_cas import PreferenceWriteReceipt

    service = _service()
    receipt = PreferenceWriteReceipt()
    validate = AsyncMock(
        side_effect=ResourceConflictError("meeting_template", detail={"error_code": "STALE_STATE"})
    )
    confirmation = TemplateWriteConfirmation(
        validate=validate, check=AsyncMock(), receipt=receipt, created_id=uuid4()
    )
    with pytest.raises(ResourceConflictError):
        await service.create(uuid4(), _request(), "fr", confirmation=confirmation)
    service.repo.create.assert_not_awaited()
    service.db.commit.assert_not_awaited()
    assert not receipt.committed


async def test_lost_commit_acknowledgment_cannot_claim_a_created_template() -> None:
    from src.domains.meetings.template_confirmation import (
        TemplateCommitUnknown,
        TemplateWriteConfirmation,
    )
    from src.domains.users.preference_cas import PreferenceWriteReceipt

    service = _service()
    service.db.commit.side_effect = OperationalError("COMMIT", {}, Exception("lost acknowledgment"))
    receipt = PreferenceWriteReceipt()
    confirmation = TemplateWriteConfirmation(
        validate=AsyncMock(), check=AsyncMock(), receipt=receipt, created_id=uuid4()
    )
    with pytest.raises(TemplateCommitUnknown):
        await service.create(uuid4(), _request(), "fr", confirmation=confirmation)
    assert not receipt.committed and receipt.values is None
