"""Nullable game fields retain top-level constraints and wire discriminators."""

import pytest
from pydantic import TypeAdapter, ValidationError

from src.domains.world.game_models import (
    GameMove,
    GamePosition,
    OptionalGameMove,
    OptionalGamePosition,
    OptionalPlayer,
)

pytestmark = pytest.mark.unit


def test_nullable_move_and_position_keep_the_tagged_wire_contract() -> None:
    adapters: list[tuple[TypeAdapter[GameMove | GamePosition | None], dict[str, str | int]]] = [
        (TypeAdapter(OptionalGameMove), {"game": "tic_tac_toe", "cell": 0}),
        (TypeAdapter(OptionalGamePosition), {"game": "tic_tac_toe"}),
    ]
    for adapter, payload in adapters:
        assert adapter.validate_python(None) is None
        value = adapter.validate_python(payload)
        assert value is not None and value.game == "tic_tac_toe"
        schema = adapter.json_schema()
        branches = schema.get("anyOf", [])
        assert any(
            branch.get("discriminator", {}).get("propertyName") == "game" for branch in branches
        )
        with pytest.raises(ValidationError):
            adapter.validate_python({"game": "unknown"})


def test_nullable_winner_keeps_strict_number_and_bounds() -> None:
    adapter: TypeAdapter[int | None] = TypeAdapter(OptionalPlayer)
    assert adapter.validate_python(None) is None
    for value in (1, 2):
        assert adapter.validate_python(value) == value
    for invalid in (True, False, 0, 3, "1"):
        with pytest.raises(ValidationError):
            adapter.validate_python(invalid)
