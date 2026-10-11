"""Provider-card selection has finite source vocabulary and no implicit refresh/authority."""

import pytest
from pydantic import ValidationError

from src.domains.agents.application.relation_context_schemas import (
    RelationContextProjection,
    RelationContextQuery,
)
from src.domains.relations.providers.schemas import RelationContext

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "query",
    [
        {"name": "Alice", "sections": ["emails", "emails"]},
        {"name": "Alice", "sections": ["notes"]},
        {"name": "Alice", "refresh": ["contact"]},
        {"name": "Alice", "user_id": "other"},
    ],
)
def test_context_rejects_duplicates_unknown_sources_refresh_and_authority(query):
    with pytest.raises(ValidationError):
        RelationContextQuery.model_validate(query)


def test_context_output_inherits_the_source_contract():
    assert set(RelationContextProjection.model_fields) == {
        *RelationContext.model_fields,
        "observed_at",
    }
