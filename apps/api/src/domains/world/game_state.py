"""Bounded ephemeral cabinet records, separate from public projections and durable preferences."""

from typing import Literal
from uuid import uuid4

from pydantic import Field, model_validator

from src.core.constants import WORLD_RECEIPT_RING_SIZE
from src.domains.world.game_integrity import validate_game_table
from src.domains.world.game_models import CabinetId, GamePosition, OptionalPlayer, Player
from src.domains.world.receipt_models import GameOutcome
from src.domains.world.wire_models import StrictModel

GamePhase = Literal["empty", "waiting", "playing_computer", "playing_human", "finished"]
GameEndReason = Literal["win", "draw", "resigned", "unavailable", "abandoned"]


class GameMember(StrictModel):
    account: str = Field(
        min_length=36,
        max_length=36,
        description="Private native account identity, never directly projected.",
    )
    public_id: str = Field(
        min_length=36,
        max_length=36,
        description="Existing opaque World actor identity, without a copied profile or alias.",
    )
    controller: str = Field(
        min_length=1,
        max_length=128,
        description="Explicit match-controller generation, rotated only by deliberate rejoin.",
    )
    number: Player = Field(description="Rule color/number held by this human in the current round.")
    offline_until: float | None = Field(
        default=None,
        ge=0,
        description="First transport-loss grace deadline; repeated ticks never extend it.",
    )


class GameJoinRequest(StrictModel):
    account: str = Field(
        min_length=36,
        max_length=36,
        description="Private requesting account, not yet a board participant.",
    )
    public_id: str = Field(
        min_length=36,
        max_length=36,
        description="Existing public actor identity shown only to the host.",
    )
    controller: str = Field(
        min_length=1,
        max_length=128,
        description="Requesting transport generation; stale requests cannot be accepted.",
    )
    expires_at: float = Field(ge=0, description="Redis-time deadline for explicit host consent.")


class GameOperationReceipt(StrictModel):
    account: str = Field(
        min_length=36,
        max_length=36,
        description="Private receipt owner, inspected by account erasure.",
    )
    controller: str = Field(
        min_length=1,
        max_length=128,
        description="Controller generation that authored the operation.",
    )
    payload_hash: str = Field(
        min_length=64,
        max_length=64,
        description="Bounded SHA256 of the exact command, never a retained arbitrary payload.",
    )
    outcome: GameOutcome = Field(
        description="Original deterministic result for exact delivery deduplication."
    )


class GameTable(StrictModel):
    cabinet: CabinetId = Field(
        description="Stable authored cabinet identity, matching its authority-map key."
    )
    round_id: str = Field(
        default_factory=lambda: str(uuid4()),
        min_length=36,
        max_length=36,
        description="Fresh round lifetime; rematches never inherit an old command generation.",
    )
    revision: int = Field(
        default=0,
        ge=0,
        le=2**31 - 1,
        description="Match-specific revision; unrelated walking never changes it.",
    )
    phase: GamePhase = Field(
        description="Lobby, active opponent mode or short-lived terminal/tombstone state."
    )
    computer: bool = Field(
        default=False,
        description="Opponent mode retained through a terminal result for explicit rematch consent.",
    )
    position: GamePosition = Field(
        description="Immutable strictly typed rule position, authored exclusively by the server."
    )
    members: list[GameMember] = Field(
        default_factory=list,
        max_length=2,
        description="At most two human members; a computer has no native account identity.",
    )
    pending: GameJoinRequest | None = Field(
        default=None,
        description="At most one short-lived request awaiting the first member's consent.",
    )
    receipts: list[GameOperationReceipt] = Field(
        default_factory=list,
        max_length=WORLD_RECEIPT_RING_SIZE,
        description="Bounded per-cabinet idempotency ring; private to operation owners.",
    )
    created_at: float = Field(ge=0, description="Redis timestamp at this round's creation.")
    expires_at: float = Field(
        ge=0, description="Independent absolute round or lobby lifetime ceiling."
    )
    turn_until: float = Field(
        ge=0, description="Deadline for the next legal human move, paused on transport loss."
    )
    paused_at: float | None = Field(
        default=None,
        ge=0,
        description="First loss-of-presence timestamp; null while actively connected.",
    )
    remaining_turn: float | None = Field(
        default=None,
        ge=0,
        description="Remaining turn seconds saved once on suspension, restored without a reset.",
    )
    ended_at: float | None = Field(
        default=None,
        ge=0,
        description="Terminal/tombstone creation time, bounding its display and receipt retention.",
    )
    reason: GameEndReason | None = Field(
        default=None,
        description="Distinct server-derived terminal reason, without disclosure of block policy.",
    )
    winner: OptionalPlayer = Field(
        default=None,
        description="Rule color winner or resignation winner; unavailable/abandoned never awards one.",
    )
    rematch: list[str] = Field(
        default_factory=list,
        max_length=2,
        description="Private member accounts explicitly consenting to a fresh human rematch.",
    )

    @model_validator(mode="after")
    def identities(self) -> GameTable:
        """Reject duplicated slots/accounts and mismatched cabinet/rule data at the storage boundary."""
        if len({member.account for member in self.members}) != len(self.members) or len(
            {member.number for member in self.members}
        ) != len(self.members):
            raise ValueError("game_members")
        if self.cabinet != "arcade-" + self.position.game.replace("_", "-"):
            raise ValueError("game_rule_binding")
        validate_game_table(self)
        return self
