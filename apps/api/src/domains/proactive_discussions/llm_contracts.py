"""Closed LLM outputs and full-prompt envelopes for the three dedicated native slots.

The output models are MODEL-FACING: their JSON schema is what the model reads.
They carry comments, never docstrings, because a docstring becomes the schema's
description and would change every request without a measurement.
"""

import json
from collections import Counter
from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, ModelWrapValidatorHandler, PrivateAttr, model_validator

from src.core.constants import DISCUSSION_CONTEXT_PROPOSALS_MAX, DISCUSSION_PROMPT_FRAMING_TOKENS
from src.core.token_budget import count_external_tokens
from src.domains.proactive_discussions.context_store.schemas import (
    ContextProposal,
    ProposalRefusal,
)
from src.domains.proactive_discussions.contextualization.proposal_reading import read_proposals
from src.domains.proactive_discussions.decision_reading import repaired_decision
from src.domains.proactive_discussions.schemas import ContextResolution, DiscussionDecision
from src.domains.shared.discussion_sources import DiscussionValue, NonEmpty, SensitiveTopic

DiscussionPhase = Literal["context", "decision", "message"]


# MODEL-FACING (context call): the sensitive topics the model read in one evidence.
class EvidenceClassification(DiscussionValue):
    reference: NonEmpty
    sensitive_topics: Annotated[tuple[SensitiveTopic, ...], Field(max_length=5)]


# MODEL-FACING (context call): what one call returns, and how the context resolves.
class ContextInterpretation(DiscussionValue):
    classifications: Annotated[tuple[EvidenceClassification, ...], Field(max_length=100)] = ()
    proposals: Annotated[
        tuple[ContextProposal, ...], Field(max_length=DISCUSSION_CONTEXT_PROPOSALS_MAX)
    ] = ()
    resolution: ContextResolution
    # Not in the schema: why each proposal set aside while this answer was read was.
    _refused: Counter[ProposalRefusal] = PrivateAttr(default_factory=Counter)

    # One malformed proposal never refuses the whole answer, whatever model wrote it:
    # each is read alone, repaired when the repair is mechanical, else set aside and
    # counted. A classification or the resolution stays strict: dropping a topic label
    # would read a sensitive fact as an ordinary one.
    @model_validator(mode="wrap")
    @classmethod
    def _proposals_read_one_by_one(
        cls, data: object, handler: ModelWrapValidatorHandler[Self]
    ) -> Self:
        if not isinstance(data, dict) or not isinstance(data.get("proposals"), list | tuple):
            return handler(data)
        kept, refused = read_proposals(data["proposals"])
        value = handler({**data, "proposals": kept})
        value._refused = refused
        return value

    # The proposals set aside while this answer was read, by reason.
    @property
    def refused_proposals(self) -> Counter[ProposalRefusal]:
        return Counter(self._refused)


# MODEL-FACING (decision call): the decision union in the object a tool schema needs.
class DecisionEnvelope(DiscussionValue):
    decision: DiscussionDecision

    # Whatever model wrote it, a decision is never refused for what is mechanical: a
    # free text past its published length is cut at it, a reference listed twice is
    # read once. The action, the references and the delay stay strict.
    @model_validator(mode="before")
    @classmethod
    def _mechanical_repairs(cls, data: object) -> object:
        if isinstance(data, dict) and isinstance(data.get("decision"), dict):
            return {**data, "decision": repaired_decision(data["decision"])}
        return data


class PromptBudgetExceeded(ValueError):
    """Do not call a provider with an incomplete prompt or no answer room."""


def bounded_prompt_tokens(
    system: str,
    content: str,
    *,
    schema: type[BaseModel] | None,
    window: int,
    output: int,
) -> int:
    """Measure a complete prompt and refuse it when it does not fit the configured slot.

    The measure counts the system and user text, the structured-output schema
    twice (a native adapter may send it as a tool and as a JSON-mode instruction)
    and a framing margin. The ceiling is what the configured slot leaves: its
    window less its output budget and the same margin. No envelope is written here:
    what a model accepts is the slot's (ADR-244, ADR-278); what a call may cost is the
    run's reservation (ADR-360).

    Args:
        system: The system prompt.
        content: The user message.
        schema: The structured-output schema, or None for free text.
        window: The slot's context window, in tokens.
        output: The slot's output budget, in tokens.

    Returns:
        The measured prompt size, in tokens.

    Raises:
        PromptBudgetExceeded: The prompt exceeds its ceiling, or no output room
            is left.
    """
    schema_text = (
        json.dumps(schema.model_json_schema(), ensure_ascii=False, separators=(",", ":"))
        if schema
        else ""
    )
    # Native structured adapters may include both the tool schema and a JSON-mode
    # instruction. Reserve both plus framing/tokenizer margin, without cutting facts.
    measured = (
        count_external_tokens(system)
        + count_external_tokens(content)
        + 2 * count_external_tokens(schema_text)
        + DISCUSSION_PROMPT_FRAMING_TOKENS
    )
    ceiling = window - output - DISCUSSION_PROMPT_FRAMING_TOKENS
    if output <= 0 or measured > ceiling:
        raise PromptBudgetExceeded("complete discussion prompt exceeds its slot envelope")
    return measured
