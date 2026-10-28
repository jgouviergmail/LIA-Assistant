"""Closed scene game commands and owner-only correlated outcomes."""

import hashlib
from typing import Literal

from pydantic import Field, model_validator

from src.domains.world.game_models import CabinetId, OptionalGameMove
from src.domains.world.socket_models import SocketVersionedModel

GameAction = Literal[
    "wait", "start_computer", "request", "accept", "decline", "move", "leave", "rematch", "rejoin"
]


class GameCommand(SocketVersionedModel):
    version: Literal[2] = Field(description="Required explicit shared-scene socket generation.")
    type: Literal["game"] = Field(
        description="Finite authoritative cabinet command; no board, identity or score input."
    )
    epoch: str = Field(
        min_length=36,
        max_length=36,
        description="Current scene lifetime, fencing all game commands.",
    )
    seq: int = Field(
        ge=1,
        le=2**31 - 1,
        description="Common controller-monotonic sequence, consumed on explicit refusal too.",
    )
    cabinet: CabinetId = Field(description="One stable authored cabinet key.")
    action_id: str = Field(
        min_length=36,
        max_length=36,
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        description="Opaque UUIDv4 operation identity retained only in the bounded cabinet receipt ring.",
    )
    action: GameAction = Field(
        description="Explicit lobby, consent, legal move or lifecycle intent."
    )
    round_id: str | None = Field(
        default=None,
        min_length=36,
        max_length=36,
        description="Observed round lifetime, or null for a currently empty cabinet.",
    )
    expected_revision: int = Field(
        ge=0,
        le=2**31 - 1,
        description="Observed match revision for moves/consent; own departure stays fenced by its round lifetime.",
    )
    move: OptionalGameMove = Field(
        default=None, description="Closed game-specific coordinate for a move command only."
    )

    @model_validator(mode="after")
    def move_shape(self) -> GameCommand:
        """Refuse missing move coordinates and hidden move data on auxiliary actions."""
        if (self.action == "move") != (self.move is not None):
            raise ValueError("game_move_shape")
        return self


def command_hash(command: GameCommand) -> str:
    """Canonical fixed-size identity of the complete validated command, including sequence and move."""
    return hashlib.sha256(command.model_dump_json().encode("utf-8")).hexdigest()
