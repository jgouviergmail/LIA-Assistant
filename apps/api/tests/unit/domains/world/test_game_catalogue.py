"""Compiled game identities and approaches agree with the native collision authority."""

import json

import pytest
from pydantic import ValidationError

from src.domains.world.collision import fits
from src.domains.world.game_catalogue import CABINETS, GameCatalogue
from src.domains.world.game_rules import new_game

pytestmark = pytest.mark.unit


def test_each_authored_cabinet_has_a_distinct_real_rule_and_walkable_approach() -> None:
    assert set(CABINETS) == {"arcade-tic-tac-toe", "arcade-four-in-row", "arcade-reversi"}
    assert len({cabinet.game for cabinet in CABINETS.values()}) == 3
    for cabinet in CABINETS.values():
        assert fits(**cabinet.approach)
        assert new_game(cabinet.game).game == cabinet.game


@pytest.mark.parametrize("corruption", ["duplicate_id", "duplicate_prop", "swapped_rules"])
def test_a_malformed_or_misbound_catalogue_is_refused_at_startup(corruption: str) -> None:
    cabinets = [cabinet.model_dump(mode="json") for cabinet in CABINETS.values()]
    if corruption == "duplicate_id":
        cabinets[1]["id"] = cabinets[0]["id"]
    elif corruption == "duplicate_prop":
        cabinets[1]["prop"] = cabinets[0]["prop"]
    else:
        cabinets[0]["game"], cabinets[1]["game"] = cabinets[1]["game"], cabinets[0]["game"]
    with pytest.raises(ValidationError, match="world_arcade_binding"):
        GameCatalogue.model_validate_json(json.dumps({"version": 1, "cabinets": cabinets}))
