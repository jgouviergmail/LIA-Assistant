"""Pure game policy scope and bounded lifecycle configuration."""

from dataclasses import dataclass

from src.core.constants import (
    WORLD_ARCADE_RECONNECT_SECONDS_DEFAULT,
    WORLD_ARCADE_REQUEST_SECONDS_DEFAULT,
    WORLD_ARCADE_RESULT_SECONDS_DEFAULT,
    WORLD_ARCADE_ROUND_SECONDS_DEFAULT,
    WORLD_ARCADE_TURN_SECONDS_DEFAULT,
    WORLD_ARCADE_WAIT_SECONDS_DEFAULT,
)


@dataclass(frozen=True)
class GameLimits:
    wait_seconds: float = WORLD_ARCADE_WAIT_SECONDS_DEFAULT
    request_seconds: float = WORLD_ARCADE_REQUEST_SECONDS_DEFAULT
    reconnect_seconds: float = WORLD_ARCADE_RECONNECT_SECONDS_DEFAULT
    turn_seconds: float = WORLD_ARCADE_TURN_SECONDS_DEFAULT
    round_seconds: float = WORLD_ARCADE_ROUND_SECONDS_DEFAULT
    result_seconds: float = WORLD_ARCADE_RESULT_SECONDS_DEFAULT


@dataclass(frozen=True)
class GameScope:
    account: str
    controller: str
    eligible: frozenset[str]
    blocked: frozenset[str] = frozenset()
