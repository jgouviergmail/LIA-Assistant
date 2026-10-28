"""Closed public cabinet hints and owner-filtered game views; no persistence identities."""

from typing import Literal

from pydantic import Field

from src.domains.world.game_models import CabinetId, GameMove, GamePosition, OptionalPlayer, Player
from src.domains.world.game_state import GameEndReason, GamePhase
from src.domains.world.wire_models import StrictModel


class CabinetView(StrictModel):
    cabinet: CabinetId = Field(description="One stable authored cabinet key.")
    availability: Literal["empty", "joinable", "full"] = Field(
        description=(
            "Coarse availability only; never a spectator board, score or player name. "
            "A policy-hidden table reads as full, like any other full table."
        )
    )
    round_id: str | None = Field(
        default=None,
        description="Observed join intent fence, present only on a joinable cabinet.",
    )
    revision: int = Field(
        default=0,
        ge=0,
        description="Observed match-specific join intent fence, zero unless joinable.",
    )


class GamePlayerView(StrictModel):
    id: str = Field(description="Existing opaque public World actor identity.")
    alias: str = Field(
        max_length=24, description="Current public World alias, never a copied private profile."
    )
    number: Player = Field(description="Human rule color in this round.")


class GameRequestView(StrictModel):
    id: str = Field(description="Existing opaque public requester identity, host-visible only.")
    alias: str = Field(
        max_length=24, description="Current public requester alias after mutual block filtering."
    )
    expires_at: float = Field(ge=0, description="Original non-renewable host-consent deadline.")


class GameWaitingView(StrictModel):
    cabinet: CabinetId = Field(description="The owner's outstanding join request cabinet.")
    round_id: str = Field(description="Observed host round lifetime, never a board access grant.")
    revision: int = Field(ge=0, description="Observed revision for withdrawal.")
    expires_at: float = Field(ge=0, description="Original non-renewable request deadline.")


class GameView(StrictModel):
    cabinet: CabinetId = Field(description="Participant's stable cabinet identity.")
    round_id: str = Field(description="Fresh lifetime for this consenting round.")
    revision: int = Field(ge=0, description="Match revision independent of scene movement.")
    phase: GamePhase = Field(description="Current explicit lifecycle phase.")
    computer: bool = Field(description="Whether the opponent is the deterministic local computer.")
    position: GamePosition = Field(
        description="Authoritative board, disclosed to consenting participants only."
    )
    players: list[GamePlayerView] = Field(
        max_length=2, description="Current unblocked consenting humans."
    )
    your_number: Player = Field(description="This participant's rule color.")
    needs_rejoin: bool = Field(
        description="A new World controller must explicitly resume the game."
    )
    paused: bool = Field(
        description="Transport loss suspends legal turns without resetting their clock."
    )
    turn_until: float = Field(ge=0, description="Redis-time deadline for the next human turn.")
    expires_at: float = Field(ge=0, description="Absolute match or short-lived result deadline.")
    reconnect_until: float | None = Field(
        default=None, description="Earliest original reconnect deadline, if suspended."
    )
    pending: GameRequestView | None = Field(
        default=None, description="One requester shown only to the current host."
    )
    legal_moves: list[GameMove] = Field(
        default_factory=list,
        max_length=64,
        description="Server-derived legal controls; never a client-authoritative legality claim.",
    )
    reason: GameEndReason | None = Field(
        default=None, description="Generic terminal cause; never a block/deletion attribution."
    )
    winner: OptionalPlayer = Field(
        default=None, description="Actual rule/resignation result; unavailable awards no winner."
    )
    rematch_ready: list[Player] = Field(
        default_factory=list,
        max_length=2,
        description="Colors whose humans explicitly consented to a fresh round.",
    )
