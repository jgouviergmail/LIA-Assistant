"""Structured-output schemas of the Initiative node (ADR-062, Lot 1-A3).

Extracted from ``initiative_node.py`` (file-size ratchet — a logical file
never grows: extract instead). One-way dependency: the node imports these
schemas, never the reverse. ``initiative_node`` re-exports them so every
historical import path keeps working.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domains.agents.orchestration.plan_schemas import ParameterItem


class InitiativeAction(BaseModel):
    """A single read-only complementary action.

    Uses ``list[ParameterItem]`` for parameters to ensure OpenAI strict mode
    compatibility.
    ``dict[str, Any]`` is not allowed in strict JSON schema.
    """

    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(description="Exact tool name from available tools")
    parameters: list[ParameterItem] = Field(
        default_factory=list,
        description="Tool parameters as name/value pairs",
    )
    rationale: str = Field(description="Why this adds concrete value (one sentence)")

    @model_validator(mode="before")
    @classmethod
    def _tool_named_in_name(cls, data: object) -> object:
        """Read ``name`` as ``tool_name`` when the action names its tool nowhere else.

        Measured 2026-11-08: the evaluator sometimes keys an action's tool with the
        parameters' own field name, and the strict schema then discarded the whole
        decision. An action can only name its tool, so the slip is mechanically
        repaired before validation; an action carrying both keys stays an error.

        Args:
            data: The raw action as the model wrote it.

        Returns:
            The action with its tool under ``tool_name``, otherwise unchanged.
        """
        if isinstance(data, dict) and "name" in data and "tool_name" not in data:
            return {"tool_name": data["name"], **{k: v for k, v in data.items() if k != "name"}}
        return data


class InitiativeDecision(BaseModel):
    """LLM decision for the initiative phase."""

    model_config = ConfigDict(extra="forbid")

    analysis: str = Field(description="Actionable signals found (one sentence)")
    should_act: bool = Field(
        description="True when a read-only cross-domain check would plausibly enrich the answer"
    )
    reasoning: str = Field(description="Why acting or not (one sentence)")
    actions: list[InitiativeAction] = Field(
        default_factory=list,
        description="Read-only actions (empty if should_act=false)",
    )
    suggestion: str | None = Field(
        default=None,
        description="Question for user when a write action would help but is not allowed here",
    )
    followup_suggestions: list[str] = Field(
        default_factory=list,
        description=(
            "0-3 short follow-up requests (max ~12 words each) the user might "
            "send next, phrased as user messages in the user's language"
        ),
    )
    motivation: str | None = Field(
        default=None,
        description=(
            "One short sentence in the user's language naming the stored "
            "memory, interest or visible result that motivated the chips or "
            "suggestion (null when none were proposed)"
        ),
    )
