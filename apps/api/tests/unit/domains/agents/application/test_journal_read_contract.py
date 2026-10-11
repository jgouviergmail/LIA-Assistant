"""Source management fields grow together; the semantic lookup is a distinct behavior."""

import pytest
from pydantic import ValidationError

from src.domains.agents.application.journal_read_schemas import (
    JournalProjection,
    JournalRead,
    JournalsProjection,
)
from src.domains.journals.schemas import JournalEntryListResponse, JournalEntryResponse

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {"limit": True},
        {"limit": 51},
        {"user_id": "other"},
        {"consolidate": True},
        {"embedding": True},
        {"theme": "unknown"},
    ],
)
def test_journal_read_never_accepts_effects_authority_or_bad_bounds(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        JournalRead.model_validate(payload)


def test_journal_read_inherits_every_public_management_field() -> None:
    assert set(JournalProjection.model_fields) == set(JournalEntryResponse.model_fields)
    assert set(JournalEntryListResponse.model_fields) <= set(JournalsProjection.model_fields)
