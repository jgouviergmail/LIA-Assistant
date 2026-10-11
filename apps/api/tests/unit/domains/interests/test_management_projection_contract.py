"""UI management projections must populate every declared field from the source."""

from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.domains.interests.models import UserInterest
from src.domains.interests.repository import InterestRepository
from src.domains.interests.router import _interest_to_response
from src.domains.interests.schemas import InterestResponse

pytestmark = pytest.mark.unit


def test_every_source_ui_field_is_explicitly_projected_and_weight_uses_the_source_policy() -> None:
    now = datetime.now(UTC)
    row = UserInterest(
        id=uuid4(),
        user_id=uuid4(),
        topic="Typed interest",
        category="technology",
        subject="Shared subject",
        status="active",
        positive_signals=3,
        negative_signals=0,
        last_mentioned_at=now,
        last_notified_at=None,
        created_at=now,
    )
    repo = InterestRepository(MagicMock())
    response = _interest_to_response(row, repo)
    assert response.model_fields_set == set(InterestResponse.model_fields)
    assert response.subject == row.subject and response.negative_signals == 0
    assert 0 <= response.weight <= 1
