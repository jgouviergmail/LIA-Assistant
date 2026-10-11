"""Zero is an actual personality trait, never the absence of a configured trait."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.domains.personalities.models import Personality
from src.domains.psyche.service import PsycheService

pytestmark = pytest.mark.unit


async def test_source_personality_traits_keep_all_explicit_zeroes() -> None:
    row = Personality(
        trait_openness=0.0,
        trait_conscientiousness=0.0,
        trait_extraversion=0.0,
        trait_agreeableness=0.0,
        trait_neuroticism=0.0,
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    db = AsyncMock()
    db.execute.return_value = result
    traits, _ = await PsycheService(db)._load_personality_traits_and_override(uuid4())
    assert (
        traits.openness,
        traits.conscientiousness,
        traits.extraversion,
        traits.agreeableness,
        traits.neuroticism,
    ) == (0.0,) * 5
