"""Does this model satisfy what the slot declares, and what follows from that.

The verdict is one computation; what happens next depends entirely on where the
model came from, and that distinction is load-bearing:

- a **policy candidate** (a model the system proposed to itself) is hard
  filtered -- skip it and try the next;
- a model that came from ``LLM_DEFAULTS`` or from an admin override is a
  **human decision**. It is never rejected: the discrepancy is counted and
  logged so it is visible, and the call proceeds.

Getting that backwards breaks working features, and it nearly did. Before the
ADR-244 catalogue correction, ``vision_analysis``'s own default ``gpt-5-mini``
was recorded as ``supports_vision=false`` -- a column default nobody had ever
filled -- so a gate applied to explicit configuration would have disabled image
analysis over a placeholder. The correction fixed that particular row, but the
rule stands on its own: a catalogue is evidence, not authority over a human.

Absence of evidence is never a rejection either. A model outside the catalogue
(a live Ollama pull, for instance) yields no verdict at all rather than a
negative one.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.domains.llm_config.constants import LLM_TYPES_REGISTRY
from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache
from src.infrastructure.llm.model_profiles import ModelProfile
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

#: ``(slot, model)`` pairs already logged. The counter increments on every
#: call -- it is what a dashboard sums -- but the log line is a statement about
#: a configuration, not about a request, so it is said once per process and per
#: pair. Without this, a mismatched slot writes a WARNING on every LLM call.
_REPORTED: set[tuple[str, str]] = set()

#: Capability name -> the ``ModelProfile`` attribute that answers it. Mirrors
#: ``llm_config.service._CAPABILITY_CHECKS``, which answers the same question
#: over the API schema; a test pins the two vocabularies together so a new
#: capability cannot exist on one side only.
_CAPABILITY_ATTRS: dict[str, str] = {
    "vision": "supports_vision",
    "tools": "supports_tool_calling",
    "structured_output": "supports_structured_output",
}


@dataclass(frozen=True)
class GateVerdict:
    """Whether a model fits a slot, and precisely how it does not.

    Attributes:
        satisfied: Whether the model meets every declared requirement.
        missing: The declared capabilities the model does not have.
        wrong_kind: Whether the model's ``kind`` differs from the slot's
            ``required_kind``. Kept separate from ``missing`` because the two
            are different defects: a missing capability is a model too weak for
            the slot, a wrong kind is a model of the wrong nature entirely.
    """

    satisfied: bool
    missing: tuple[str, ...]
    wrong_kind: bool


def _declares(caps: ModelProfile, capability: str) -> bool | None:
    """Whether the profile answers this capability, or ``None`` when it is silent.

    Read defensively on purpose. This runs on the resolution chokepoint, once
    per LLM instantiation, and its only job is to *report*: a profile shaped
    differently from ``ModelProfile`` -- a stand-in, a future field rename --
    must produce "no evidence", never an exception that turns a reporting
    helper into a failed request.
    """
    attribute = _CAPABILITY_ATTRS.get(capability)
    if attribute is None:
        return None
    value = getattr(caps, attribute, None)
    return value if isinstance(value, bool) else None


def _verdict(slot_capabilities: list[str], required_kind: str, caps: ModelProfile) -> GateVerdict:
    """Compare one profile against one slot's declarations.

    A capability the profile is silent about is not a missing one: absence of
    evidence is never a rejection (see the module docstring).
    """
    missing = tuple(
        capability for capability in slot_capabilities if _declares(caps, capability) is False
    )
    kind = getattr(caps, "kind", None)
    wrong_kind = isinstance(kind, str) and kind != required_kind
    return GateVerdict(
        satisfied=not missing and not wrong_kind, missing=missing, wrong_kind=wrong_kind
    )


def evaluate_slot_fit(slot: str, model: str) -> GateVerdict | None:
    """Return how ``model`` fits ``slot``, or ``None`` when there is no evidence.

    Args:
        slot: An ``LLM_TYPES_REGISTRY`` key.
        model: A model name.

    Returns:
        The verdict, or ``None`` when the slot is unknown or the model has no
        catalogue profile.
    """
    metadata = LLM_TYPES_REGISTRY.get(slot)
    caps = ModelCapabilitiesCache.get(model)
    if metadata is None or caps is None:
        return None
    return _verdict(metadata.required_capabilities, metadata.required_kind.value, caps)


def report_configured_model(slot: str, model: str) -> None:
    """Count and log a configured model that does not satisfy its slot.

    Never raises and never substitutes: the model was chosen by a human, and
    silently overriding that is the failure this function exists to avoid. The
    counter is what makes the discrepancy visible on the slot's admin card.

    Called on the resolution chokepoint, so once per LLM instantiation: the
    counter increments every time, the log line is emitted once per
    ``(slot, model)`` pair and per process.

    Args:
        slot: An ``LLM_TYPES_REGISTRY`` key.
        model: The configured model name.
    """
    verdict = evaluate_slot_fit(slot, model)
    if verdict is None or verdict.satisfied:
        return

    from src.infrastructure.observability.metrics_llm_config import (
        llm_capability_mismatch_total,
    )

    llm_capability_mismatch_total.labels(llm_type=slot).inc()
    pair = (slot, model)
    if pair in _REPORTED:
        return
    _REPORTED.add(pair)
    logger.warning(
        "llm_configured_model_capability_mismatch",
        llm_type=slot,
        model=model,
        missing=list(verdict.missing),
        wrong_kind=verdict.wrong_kind,
    )
