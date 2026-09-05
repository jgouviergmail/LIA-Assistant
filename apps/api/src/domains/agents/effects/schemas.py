"""Request and outcome shapes of the effect ledger (ADR-263)."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.domains.agents.registry.catalogue import MUTATION_POLICIES

#: The three sources that can produce an effect. Mirrors ``EffectSource``; the
#: Literal exists so a request is rejected at the API boundary rather than at
#: the INSERT.
EffectSourceName = Literal["user", "scheduled", "subagent"]


class ClaimRequest(BaseModel):
    """Everything a claim must know BEFORE the effect happens.

    Frozen: a claim describes one moment — the tool, the arguments and the
    authority as they were when the right to act was taken. Mutating it
    afterwards would make the ledger describe something that never happened.
    """

    model_config = ConfigDict(frozen=True)

    user_id: uuid.UUID = Field(description="Acting user.")
    thread_id: str = Field(min_length=1, max_length=100, description="LangGraph thread.")
    run_id: str = Field(min_length=1, max_length=100, description="Billing/correlation run id.")
    source: EffectSourceName = Field(description="Who asked for the turn.")
    execution_mode: str = Field(
        min_length=1, max_length=20, description="pipeline | react | subagent."
    )
    tool_name: str = Field(min_length=1, max_length=100, description="The tool about to act.")
    mutation_policy: str = Field(
        description="The policy that applies (one of MUTATION_POLICIES, ADR-263)."
    )
    idempotency_key: str = Field(
        min_length=1,
        max_length=200,
        description="Unique per thread: tool_call_id, draft_id or run_id:step_id.",
    )
    args_digest: str = Field(min_length=64, max_length=64, description="Keyed digest of the call.")
    approval_kind: str | None = Field(
        default=None, max_length=30, description="How the effect was approved."
    )
    approval_ref: str | None = Field(
        default=None, max_length=200, description="Card message_id, or draft_id."
    )
    draft_digest: str | None = Field(
        default=None,
        min_length=64,
        max_length=64,
        description="Digest of the draft content the user was shown.",
    )
    catalogue_fingerprint: str | None = Field(
        default=None, max_length=64, description="Digest of the catalogue that offered the tool."
    )
    retry_of: uuid.UUID | None = Field(
        default=None, description="The row this claim retries, when it retries one."
    )
    label: dict[str, Any] | None = Field(
        default=None,
        description=(
            "{i18n_key, values} for the human-readable register; stored encrypted. "
            "Filled by the label builders of lot 3b — None until then."
        ),
    )

    @field_validator("mutation_policy")
    @classmethod
    def _policy_is_declared(cls, value: str) -> str:
        """Refuse a policy the catalogue does not define.

        Args:
            value: The candidate policy.

        Returns:
            The value, unchanged.

        Raises:
            ValueError: When the policy is not one the catalogue declares — the
                ledger records what applied, and an invented policy records
                nothing.
        """
        if value not in MUTATION_POLICIES:
            raise ValueError(f"unknown mutation_policy {value!r}")
        return value
