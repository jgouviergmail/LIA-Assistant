"""Which engine plans a turn, and why (ADR-070, automatic mode: ADR-390).

An explicit choice is obeyed. « auto » is a rule, qualified on a held-out corpus
(``scripts/agents/execution_mode_corpus.py``): the pipeline plans the turn only
when the analysis reads no shape one plan cannot finish AND the decision provider
judged every loop property absent. Anything else — a property present, a
judgement undecided, no judgement at all — goes to the loop: a complete answer
comes before a fast one.

Pure: the router owns the inputs (its analysis, the shape judgement it started)
and settles what this returns on the turn's context.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from src.core.constants import (
    EXECUTION_MODE_AUTO,
    EXECUTION_MODE_PIPELINE,
    EXECUTION_MODE_REACT,
)
from src.domains.agents.analysis.query_intelligence import QueryIntelligence
from src.domains.agents.constants import DOMAIN_CALCULATION

__all__ = ["EngineReason", "EngineResolution", "SHAPE_VERDICTS", "resolve_engine"]


class EngineReason(StrEnum):
    """Why a turn runs in its engine — a bounded vocabulary, register and metric label."""

    #: The person, the routine or the ticket chose this engine.
    REQUESTED = "requested"
    #: The loop is switched off on the instance: the pipeline plans every turn.
    LOOP_DISABLED = "loop_disabled"
    #: The analysis read an act: confirmed on a card the loop carries end to end.
    ACT = "act"
    #: Something must be done for each item a lookup returns.
    ITEM_WISE = "item_wise"
    #: A skill was detected: its instructions unfold step by step.
    SKILL = "skill"
    #: The turn refers to what an earlier one showed.
    REFERENCE = "reference"
    #: A calculation over what another domain returns.
    CALCULATION = "calculation"
    #: The provider judged a figure must be worked out from fetched data.
    COMPUTED = "computed"
    #: The provider judged results must be checked against each other.
    CROSS_CHECK = "cross_check"
    #: The provider judged the work open-ended.
    OPEN_ENDED = "open_ended"
    #: The provider judged that a later lookup is about someone or something only an
    #: item's written content names: a plan's reference passes a field, never that.
    NAMED_IN_TEXT = "named_in_text"
    #: No judgement: the usage off, no provider, a failure, a timeout, a doubt.
    NO_DECISION = "no_decision"
    #: Every property judged absent: one plan answers it.
    DIRECT = "direct"


#: What a shape judgement may answer: one of these, nothing else.
SHAPE_VERDICTS: frozenset[EngineReason] = frozenset(
    {
        EngineReason.COMPUTED,
        EngineReason.CROSS_CHECK,
        EngineReason.OPEN_ENDED,
        EngineReason.NAMED_IN_TEXT,
        EngineReason.NO_DECISION,
        EngineReason.DIRECT,
    }
)


@dataclass(frozen=True, slots=True)
class EngineResolution:
    """The engine that plans a turn, and the reason it was chosen.

    Attributes:
        engine: ``pipeline`` or ``react``.
        reason: Why.
    """

    engine: str
    reason: EngineReason


def _shape_reason(intelligence: QueryIntelligence) -> EngineReason | None:
    """A shape the analysis reads that one plan cannot finish, or None."""
    if intelligence.is_mutation_intent:
        return EngineReason.ACT
    if intelligence.for_each_detected:
        return EngineReason.ITEM_WISE
    if intelligence.detected_skill_name:
        return EngineReason.SKILL
    if (
        intelligence.is_reference_turn()
        or intelligence.resolved_references
        or intelligence.resolved_context is not None
    ):
        return EngineReason.REFERENCE
    if DOMAIN_CALCULATION in intelligence.domains and len(intelligence.domains) > 1:
        return EngineReason.CALCULATION
    return None


def resolve_engine(
    requested: str,
    intelligence: QueryIntelligence,
    verdict: EngineReason,
    *,
    loop_enabled: bool,
) -> EngineResolution:
    """The engine of a turn the router sends to planning.

    Args:
        requested: What the turn was asked to run in, as stored.
        intelligence: The router's analysis of the turn.
        verdict: The shape judgement (:data:`SHAPE_VERDICTS`); read only when
            ``requested`` is « auto ».
        loop_enabled: Whether the instance runs the loop at all.

    Returns:
        The engine and its reason.

    Raises:
        ValueError: ``verdict`` is not a shape judgement.
    """
    if verdict not in SHAPE_VERDICTS:
        raise ValueError(f"not a shape verdict: {verdict!r}")
    if requested not in (EXECUTION_MODE_REACT, EXECUTION_MODE_AUTO):
        return EngineResolution(EXECUTION_MODE_PIPELINE, EngineReason.REQUESTED)
    if not loop_enabled:
        return EngineResolution(EXECUTION_MODE_PIPELINE, EngineReason.LOOP_DISABLED)
    if requested == EXECUTION_MODE_REACT:
        return EngineResolution(EXECUTION_MODE_REACT, EngineReason.REQUESTED)
    shape = _shape_reason(intelligence)
    if shape is not None:
        return EngineResolution(EXECUTION_MODE_REACT, shape)
    if verdict is EngineReason.DIRECT:
        return EngineResolution(EXECUTION_MODE_PIPELINE, EngineReason.DIRECT)
    return EngineResolution(EXECUTION_MODE_REACT, verdict)
