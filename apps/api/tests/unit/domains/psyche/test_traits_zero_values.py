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


@pytest.mark.parametrize("values", [(0.8, 0.7, 0.6, 0.4, 0.2), (0.0,) * 5])
async def test_absent_explicit_preference_reads_default_personality_traits(
    values: tuple[float, float, float, float, float],
) -> None:
    """NULL means the catalogue default, exactly as in the public selector."""
    default = Personality(
        trait_openness=values[0],
        trait_conscientiousness=values[1],
        trait_extraversion=values[2],
        trait_agreeableness=values[3],
        trait_neuroticism=values[4],
        pad_pleasure_override=-0.2,
    )
    selected_result = MagicMock()
    selected_result.scalar_one_or_none.return_value = None
    default_result = MagicMock()
    default_result.scalar_one_or_none.return_value = default
    db = AsyncMock()
    db.execute.side_effect = [selected_result, default_result]

    traits, override = await PsycheService(db)._load_personality_traits_and_override(uuid4())

    assert (
        traits.openness,
        traits.conscientiousness,
        traits.extraversion,
        traits.agreeableness,
        traits.neuroticism,
    ) == values
    assert override is not None and override.pleasure == -0.2
    assert db.execute.await_count == 2
    assert "personalities.is_default" in str(db.execute.await_args_list[1].args[0])


async def test_no_selected_or_default_personality_retains_neutral_traits() -> None:
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db = AsyncMock()
    db.execute.return_value = result

    traits, override = await PsycheService(db)._load_personality_traits_and_override(uuid4())

    assert traits.openness == traits.conscientiousness == traits.extraversion == 0.5
    assert traits.agreeableness == traits.neuroticism == 0.5
    assert override is None
