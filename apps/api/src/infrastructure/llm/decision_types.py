"""Portable result and accounting values for a native decision call."""

from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, Field

from src.infrastructure.llm.jev_debug_models import JevCallTrace
from src.infrastructure.llm.typesafe_client import ChoiceAnswer


class DecisionCharge(BaseModel):
    """A billed attempt, independent of any subsequent generative fallback."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    model: str = Field(description="Reported model.")
    input_tokens: int = Field(ge=0, description="Actual input counter.")
    output_tokens: int = Field(ge=0, description="Actual output counter.")
    cost_usd: float = Field(
        ge=0, allow_inf_nan=False, description="Cost at the snapshotted tariff."
    )
    cost_eur: float = Field(ge=0, allow_inf_nan=False, description="Converted cost.")


@dataclass(frozen=True)
class DecisionAttempt:
    """A usable answer or a fallback code, keeping even unsuccessful paid usage."""

    answer: ChoiceAnswer | None = None
    charge: DecisionCharge | None = None
    outcome: str = "disabled"
    diagnostic: JevCallTrace | None = None
    answers: dict[str, ChoiceAnswer] = field(default_factory=dict)
