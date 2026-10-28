"""The single typed receipt registry shared by owner state and socket projections."""

from typing import Annotated, Literal

from pydantic import Field

from src.domains.world.wire_models import PoseResult, StrictModel


class ReceiptBase(StrictModel):
    seq: int = Field(
        ge=1,
        le=2**31 - 1,
        description="Exact accepted or explicitly refused command sequence, never a generic movement acknowledgment.",
    )


class PoseReceipt(ReceiptBase):
    kind: Literal["pose"] = Field(
        default="pose", description="Receipt belongs exclusively to a furniture-pose command."
    )
    result: PoseResult = Field(description="Authoritative bounded pose transition outcome.")


class EmoteReceipt(ReceiptBase):
    kind: Literal["emote"] = Field(
        default="emote", description="Receipt belongs exclusively to a finite social gesture."
    )
    result: Literal["accepted", "rate_limited", "unavailable"] = Field(
        description="Authoritative gesture acceptance, cooldown or visibility refusal."
    )


class MoveReceipt(ReceiptBase):
    kind: Literal["move"] = Field(
        default="move", description="Receipt belongs exclusively to a movement command."
    )
    result: Literal["accepted"] = Field(
        default="accepted",
        description="Fresh valid movement sequence was consumed, including a collision-limited move.",
    )


GameOutcomeKind = Literal[
    "accepted",
    "unavailable",
    "rate_limited",
    "conflict",
    "wrong_turn",
    "illegal_move",
    "full",
    "occupied",
    "not_participant",
    "action_reused",
    "suspended",
    "out_of_reach",
]


class GameOutcome(StrictModel):
    action_id: str = Field(
        min_length=36, max_length=36, description="Exact operation whose result this acknowledges."
    )
    result: GameOutcomeKind = Field(
        description="Closed authoritative acceptance/refusal; uncertainty is never a winner."
    )
    round_id: str | None = Field(
        default=None, description="Round produced or observed by this exact operation."
    )
    revision: int = Field(
        ge=0, description="Committed match revision attached to the acknowledged outcome."
    )


class GameReceipt(ReceiptBase):
    kind: Literal["game"] = Field(
        default="game", description="Exact game command receipt, never a pose confirmation."
    )
    outcome: GameOutcome = Field(
        description="Owner-only operation identity and authoritative match outcome."
    )


CommandReceipt = Annotated[
    PoseReceipt | EmoteReceipt | MoveReceipt | GameReceipt, Field(discriminator="kind")
]
