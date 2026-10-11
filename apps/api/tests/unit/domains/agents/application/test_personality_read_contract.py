"""Only the public source schema can enrich this non-administrative read."""

import pytest
from pydantic import ValidationError

from src.domains.agents.application.personality_schemas import (
    PersonalityProjection,
    PersonalityRead,
)
from src.domains.personalities.schemas import PersonalityListResponse, UserPersonalityResponse

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [{"limit": True}, {"limit": 0}, {"limit": 51}, {"user_id": "other"}, {"include_prompts": True}],
)
def test_personality_read_rejects_authority_and_excessive_pages(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        PersonalityRead.model_validate(payload)


def test_personality_projection_inherits_both_public_source_contracts() -> None:
    assert set(PersonalityListResponse.model_fields) <= set(PersonalityProjection.model_fields)
    assert set(UserPersonalityResponse.model_fields) <= set(PersonalityProjection.model_fields)
    assert {"prompt_instruction", "translations", "trait_openness", "is_active"}.isdisjoint(
        PersonalityProjection.model_fields
    )
