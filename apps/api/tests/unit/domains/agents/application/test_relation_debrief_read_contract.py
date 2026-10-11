"""Stored synthesis selectors reject authority input and publish the source output contract."""

import pytest
from pydantic import ValidationError

from src.domains.agents.application.relation_debrief_read import (
    RelationStoredDebriefProjection,
    RelationStoredDebriefQuery,
)
from src.domains.relations.debrief.schemas import RelationDebriefRead

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "query",
    [
        {},
        {"name": " "},
        {"name": 123},
        {"name": "A" * 256},
        {"name": "Alice", "user_id": "other"},
        {"name": "Alice", "force": True},
    ],
)
def test_stored_debrief_query_is_explicit_and_never_a_build(query):
    with pytest.raises(ValidationError):
        RelationStoredDebriefQuery.model_validate(query)


def test_stored_read_extends_source_contract_instead_of_shadowing_it():
    assert set(RelationStoredDebriefProjection.model_fields) == {
        *RelationDebriefRead.model_fields,
        "observed_at",
    }
