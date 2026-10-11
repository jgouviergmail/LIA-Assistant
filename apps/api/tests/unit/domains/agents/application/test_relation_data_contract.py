"""Local CRM reads have finite public selectors, never actor or provider authority."""

import pytest
from pydantic import ValidationError

from src.domains.agents.application.relation_data_schemas import RelationDataRead

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {"user_id": "other"},
        {"limit": True},
        {"limit": 51},
        {"limit": 0},
        {"name": " "},
        {"name": "x" * 256},
        {"force": True},
        {"offset": True},
        {"offset": -1},
    ],
)
def test_relationship_query_rejects_authority_and_unbounded_pages(payload):
    with pytest.raises(ValidationError):
        RelationDataRead.model_validate(payload)
