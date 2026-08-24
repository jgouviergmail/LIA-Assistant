"""Prometheus metrics for the health of the LLM configuration itself.

Not about a request: about whether what the admin configured still matches what
the catalogue says the model can do. These series answer "is this deployment
configured coherently", which is a different question from "did this call
succeed" (``metrics_agents``) or "how did it fail" (``metrics_errors``).

Every series here is labelled by ``llm_type`` -- the configured slot, a closed
vocabulary of 58 values from ``LLM_TYPES_REGISTRY``. None of them is ever
labelled by ``node_name``: that dimension carries 101 distinct unbounded values,
some of which are prompt fragments, and would make a series both unusable and a
privacy hazard.
"""

from prometheus_client import Counter

# ============================================================================
# CAPABILITY COHERENCE (ADR-244)
# ============================================================================

llm_capability_mismatch_total = Counter(
    "llm_capability_mismatch_total",
    "Configured model does not satisfy its slot's declared capabilities",
    ["llm_type"],
)


llm_agent_unmapped_total = Counter(
    "llm_agent_unmapped_total",
    "Agent built with no llm_type mapping (its calls fall back to another slot)",
    ["agent_name"],
)


# ============================================================================
# REASONING COERCION (ADR-245)
# ============================================================================

llm_reasoning_coerced_total = Counter(
    "llm_reasoning_coerced_total",
    "Configured reasoning level was not on the model's ladder and was moved",
    ["model", "from_level", "to_level"],
)
"""Every runtime coercion, so a silent downgrade is never invisible.

A coercion is not an error -- the ladder is model-specific and a stale value
must not become an outage -- but it does mean the model is not doing what the
admin asked. Bounded by construction: ``model`` comes from the catalogue and
both levels from the eight-member ladder, and only configured slots reach it.
The label is ``from_level``/``to_level`` rather than ``from``/``to`` because
PromQL treats neither as a keyword but the shorter pair reads as one in a
recording rule.
"""
