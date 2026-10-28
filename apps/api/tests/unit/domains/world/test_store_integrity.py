"""A record a transition produced invalid is named by its rule code and counted, never quoted.

The strict reader's refusal carries the record's values (a person's alias, an
account id used as a key); the integrity failure keeps only the authored rule
code — or Pydantic's error type — and the top-level area of the record.
"""

import json

import pytest
import structlog
from prometheus_client import REGISTRY
from pydantic import ValidationError

from src.domains.world.schemas import WorldState
from src.domains.world.store import WorldStore, _integrity_failure
from tests.unit.domains.world.test_games import CABINET, human_table, setup

pytestmark = pytest.mark.unit
PRIVATE = "Private visitor words"
FIELDS = frozenset(WorldState.model_fields)


def _failures(area: str) -> float:
    value = REGISTRY.get_sample_value("world_authority_integrity_failures_total", {"area": area})
    return value or 0.0


def _refusal(document: dict[str, object]) -> ValidationError:
    with pytest.raises(ValidationError) as refused:
        WorldStore.decode(json.dumps(document))
    return refused.value


def test_an_authored_rule_is_named_by_its_code_and_counted_under_its_area() -> None:
    state, _ = human_table()
    for member in state.games[CABINET].members:
        member.number = 1
    error = _refusal(state.model_dump(mode="json"))
    before = _failures("games")
    with structlog.testing.capture_logs() as captured:
        failure = _integrity_failure(error, FIELDS)
    assert (failure.code, failure.area) == ("game_members", "games")
    assert _failures("games") == before + 1
    assert captured == [
        {
            "event": "world_authority_integrity_failed",
            "error_code": "game_members",
            "area": "games",
            "log_level": "error",
        }
    ]


def test_a_built_in_refusal_is_named_by_its_type_without_its_value_or_its_key() -> None:
    state, (host, _, _) = setup()
    document = state.model_dump(mode="json")
    actors = document["actors"]
    assert isinstance(actors, dict)
    actors[host.account]["position"] = {"x": PRIVATE, "y": 0.0}
    error = _refusal(document)
    assert PRIVATE in str(error)
    with structlog.testing.capture_logs() as captured:
        failure = _integrity_failure(error, FIELDS)
    assert (failure.code, failure.area) == ("float_type", "actors")
    assert PRIVATE not in str(captured) and host.account not in str(captured)
    assert PRIVATE not in str(failure) and failure.args == ("float_type",)


def test_a_record_level_rule_has_no_field_area() -> None:
    state, _ = human_table()
    document = state.model_dump(mode="json")
    games = document["games"]
    assert isinstance(games, dict)
    games["arcade-reversi"] = games.pop(CABINET)
    with structlog.testing.capture_logs():
        failure = _integrity_failure(_refusal(document), FIELDS)
    assert (failure.code, failure.area) == ("game_cabinet_integrity", "record")
