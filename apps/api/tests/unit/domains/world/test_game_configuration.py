"""Arcade is a subordinate deployment ceiling, with bounded native World deadlines."""

import pytest
from pydantic import ValidationError

from src.core.config import settings
from src.core.config.world import WorldSettings
from src.domains.world.configuration import configured_arcade_enabled, configured_game_limits

pytestmark = pytest.mark.unit


def test_arcade_is_optional_default_on_beneath_the_world_deployment_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Default on: an operator who never set WORLD_ARCADE_ENABLED gets the arcade
    # whenever World itself is enabled.
    monkeypatch.delenv("WORLD_ARCADE_ENABLED", raising=False)
    assert WorldSettings.model_fields["world_arcade_enabled"].default is True
    assert WorldSettings(_env_file=None).world_arcade_enabled is True
    monkeypatch.setattr(settings, "world_enabled", True)
    monkeypatch.setattr(settings, "world_arcade_enabled", True)
    assert configured_arcade_enabled()
    monkeypatch.setattr(settings, "world_arcade_enabled", False)
    assert not configured_arcade_enabled()
    monkeypatch.setattr(settings, "world_enabled", False)
    monkeypatch.setattr(settings, "world_arcade_enabled", True)
    assert not configured_arcade_enabled()


def test_configured_pure_limits_use_effective_settings_instead_of_copied_deadlines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "world_arcade_turn_seconds", 180)
    monkeypatch.setattr(settings, "world_arcade_reconnect_seconds", 25)
    limits = configured_game_limits()
    assert limits.turn_seconds == 180 and limits.reconnect_seconds == 25


@pytest.mark.parametrize(
    "field,value",
    [
        ("world_arcade_input_rate", 0),
        ("world_arcade_turn_seconds", 0),
        ("world_arcade_round_seconds", 99999),
        ("world_arcade_bot_seconds", 0),
        ("world_arcade_reconnect_seconds", 600),
    ],
)
def test_unbounded_or_immediate_game_deadlines_are_refused(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        WorldSettings(_env_file=None, **{field: value})
