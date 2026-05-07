"""Reasoning effort discriminated union types.

Stored in:
- LLMConfigOverride.reasoning_effort (JSONB column)
- LLMAgentConfig.reasoning_effort (Pydantic field)

Shape is determined by the model's reasoning_widget on llm_models.
Lives in src/core/ (not src/domains/) to avoid circular imports between
domains/llm_config/schemas.py and core/llm_agent_config.py.
"""

from pydantic import BaseModel, ConfigDict, Field


class ReasoningEffortEnum(BaseModel):
    """Used when the model's reasoning_widget == 'enum'."""

    model_config = ConfigDict(extra="forbid")
    effort: str


class ReasoningEffortBudget(BaseModel):
    """Used when the model's reasoning_widget == 'budget_int'."""

    model_config = ConfigDict(extra="forbid")
    budget: int = Field(
        ...,
        ge=-1,
        description="-1 = dynamic, 0 = off (model-dependent), N = exact budget",
    )


class ReasoningEffortToggleBudget(BaseModel):
    """Used when the model's reasoning_widget == 'toggle_budget' (Qwen3 hybrid)."""

    model_config = ConfigDict(extra="forbid")
    enabled: bool
    budget: int | None = Field(None, ge=0, description="None = model default max")


ReasoningEffortValue = (
    ReasoningEffortEnum | ReasoningEffortBudget | ReasoningEffortToggleBudget | None
)


class ReasoningBudgetRange(BaseModel):
    """Numeric range for budget-based reasoning widgets."""

    model_config = ConfigDict(extra="forbid")
    min: int = Field(..., ge=0)
    max: int = Field(..., ge=0)
    off_sentinel: int | None = None
    dynamic_sentinel: int | None = None


__all__ = [
    "ReasoningBudgetRange",
    "ReasoningEffortBudget",
    "ReasoningEffortEnum",
    "ReasoningEffortToggleBudget",
    "ReasoningEffortValue",
]
