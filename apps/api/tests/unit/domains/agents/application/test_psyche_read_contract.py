"""Source public schemas grow together; read inputs never introduce side effects."""

import pytest
from pydantic import ValidationError

from src.domains.agents.application.psyche_read_schemas import (
    PsycheExpressionProjection,
    PsycheHistoryProjection,
    PsycheRead,
    PsycheStateProjection,
)
from src.domains.psyche.schemas import (
    PsycheExpressionResponse,
    PsycheHistoryEntry,
    PsycheStateResponse,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {"limit": True},
        {"limit": 51},
        {"hours": 2161},
        {"hours": 0},
        {"user_id": "other"},
        {"generate_summary": True},
        {"create": True},
        {"as_of": "2026-01-01"},
    ],
)
def test_psyche_read_refuses_authority_effects_and_bad_bounds(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        PsycheRead.model_validate(payload)


def test_psyche_read_keeps_all_public_source_fields_and_only_those() -> None:
    assert set(PsycheStateProjection.model_fields) == set(PsycheStateResponse.model_fields)
    assert set(PsycheExpressionProjection.model_fields) == set(
        PsycheExpressionResponse.model_fields
    )
    assert set(PsycheHistoryProjection.model_fields) == set(PsycheHistoryEntry.model_fields)
