"""Capabilities the user can invoke directly, and the guarantee that they run.

A button is not a sentence. When the user presses "run the 360°" on a named
relationship card, the system already knows — exactly, and before any model is
consulted — which capability must run and on whom. Today that certainty is
serialised into French prose and handed to three stochastic stages (analyser,
planner, validator) whose job becomes recovering what was just thrown away.

Measured in production on 2026-08-01: the 360° tool scored 0.853, the best of
the whole catalogue, and the plan named ``get_emails_tool`` instead. Prose
cannot carry a guarantee.

So the directive travels as data, on the same seam as ``hitl_decision`` — the
one-click HITL answer that already bypasses the reply classifier rather than
asking an LLM to re-read the user's click. Here it reaches the planner and is
honoured in the SAME repair stage that already clamps out-of-bounds parameters
and auto-corrects ``for_each_max`` (``planner/parameter_bounds.py``): what is
mechanically repairable is repaired BEFORE validation, never reported as a
defect (ADR-184 doctrine, ADR-191 application).

Three properties this design keeps:

- **The plan is enriched, not replaced.** Every step that ADDS something
  survives untouched — a sub-agent, a web search, a task lookup. The user asked
  for the surrounding tool calls to be kept, and they are.
- **What the capability already answers is removed** (``supersedes``). A
  calendar lookup that ignores the person does not enrich a stated gap, it
  contradicts it: the overview honestly reported no shared meeting and the
  assistant presented an event from the user's own calendar as the peer's
  (measured 2026-08-01). Removal happens ONLY under a directive, and never for
  a step another one still reads.
- **The client names a capability, never a tool.** ``DirectiveCapability`` is a
  closed Literal, so an unknown value is rejected by Pydantic at the HTTP
  boundary; the tool behind it is chosen here, server-side, and may only be
  read-only. A browser cannot reach ``delete_email_tool`` through this door.

Lives at the domain ROOT, not under ``services/planner/``, because it is a
contract SHARED by the HTTP boundary (``api/schemas``) and the planner. Under
``services/`` it formed a real import cycle — ``api.schemas`` →
``services.__init__`` → ``hitl`` → ``api.schemas`` — caught by the suite on the
first run. ``domains/agents/__init__`` is a bare docstring, so this module is a
true leaf.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, get_args

import structlog

if TYPE_CHECKING:
    from src.domains.agents.orchestration.plan_schemas import ExecutionPlan
    from src.domains.agents.registry import AgentRegistry

logger = structlog.get_logger(__name__)

#: Capabilities a client may invoke directly. Closed on purpose: Pydantic
#: rejects anything else at the HTTP boundary, so the allowlist IS the type.
DirectiveCapability = Literal["person_overview"]

#: Step id for the seeded step. Distinct from the planner's ``step_N`` scheme so
#: it can never collide with an LLM-generated id, and recognisable in traces.
DIRECTIVE_STEP_ID = "directive_1"


@dataclass(frozen=True)
class CapabilityDirectiveSpec:
    """How one user-invocable capability maps onto a concrete tool call.

    Attributes:
        tool_name: Registered tool the capability resolves to. Read-only tools
            only — this path is reachable from the browser.
        agent_name: Owning agent, as the orchestrator expects on a TOOL step.
        subject_parameter: Tool parameter that receives the directive subject.
        description: Human-readable step description for the UI and traces.
        supersedes: Tools this capability already covers, BY SUBJECT. When the
            capability is guaranteed, these steps are dropped from the plan —
            not to save tokens, but because they answer a DIFFERENT question.
    """

    tool_name: str
    agent_name: str
    subject_parameter: str
    description: str
    supersedes: frozenset[str] = frozenset()


#: One entry per DirectiveCapability. Exhaustivity enforced at boot by
#: :func:`assert_registry_completeness` (ADR-085 pattern).
CAPABILITY_DIRECTIVE_REGISTRY: dict[str, CapabilityDirectiveSpec] = {
    "person_overview": CapabilityDirectiveSpec(
        tool_name="get_person_overview_tool",
        agent_name="contact_agent",
        subject_parameter="person_name",
        description="360° overview requested from the relationship card",
        # These three answer "what is in MY mail / calendar / address book",
        # not "what do I have WITH this person". Measured 2026-08-01: the
        # overview honestly reported no shared meeting, and the assistant
        # presented an event from the user's own calendar — one the peer
        # neither organised nor attended — as part of the 360°. An unrelated
        # answer offered next to a stated gap does not enrich it, it
        # contradicts it. The manifest already declares the tool
        # SELF-CONTAINED; this makes that declaration binding when the user
        # invoked the capability themselves.
        supersedes=frozenset({"get_emails_tool", "get_events_tool", "get_contacts_tool"}),
    ),
}


def assert_registry_completeness(registry: AgentRegistry) -> None:
    """Assert every capability has a spec, and every spec a registered tool.

    Called from the lifespan right after the catalogue is loaded, so both
    halves are checkable, and from a unit test so CI catches it before merge.
    Either half missing degrades the directive silently back to the prose-only
    path — the exact failure this module exists to remove — or points the
    orchestrator at a tool that does not exist.

    Args:
        registry: Agent registry with the tool catalogue already initialised.

    Raises:
        AssertionError: If a capability has no spec, or a spec names a tool
            absent from the catalogue.
    """
    missing = [c for c in get_args(DirectiveCapability) if c not in CAPABILITY_DIRECTIVE_REGISTRY]
    if missing:
        raise AssertionError(
            f"CAPABILITY_DIRECTIVE_REGISTRY is missing {len(missing)} capability/ies: "
            f"{', '.join(sorted(missing))}. Every DirectiveCapability must declare a "
            "CapabilityDirectiveSpec — see "
            "src/domains/agents/capability_directives.py."
        )

    known_tools = {manifest.name for manifest in registry.list_tool_manifests()}
    unknown = sorted(
        f"{capability} -> {name}"
        for capability, spec in CAPABILITY_DIRECTIVE_REGISTRY.items()
        for name in {spec.tool_name, *spec.supersedes}
        if name not in known_tools
    )
    if unknown:
        raise AssertionError(
            f"CAPABILITY_DIRECTIVE_REGISTRY points at {len(unknown)} unregistered tool(s): "
            f"{', '.join(unknown)}. A directive resolving to a tool the orchestrator "
            "cannot run is worse than no directive at all."
        )


def ensure_directive_step(
    plan: ExecutionPlan | None,
    directive: dict[str, str] | None,
) -> ExecutionPlan | None:
    """Guarantee the directive's capability appears in the plan, and only it.

    Entirely a no-op without a resolvable directive. With one, two things
    happen: the capability's step is prepended when missing — first, and
    depending on nothing, so it runs immediately while the LLM's steps keep
    their own ordering — and the steps the capability supersedes are dropped
    (see :func:`_drop_superseded`).

    Supersession applies in BOTH cases, including when the planner reached the
    capability on its own: getting there first does not make the redundant
    steps any less contradictory.

    When the planner already produced the call, its parameters win: the model
    may have resolved an alias or a fuller spelling than the raw subject, and
    overwriting that would be the system second-guessing a correct plan.

    A plan with NO steps is left alone. ``ExecutionPlan`` only permits that
    shape for two stubs — ``needs_clarification`` (the system is asking the user
    a question) and ``skill_bypass_noop`` (execution delegated to a skill) — and
    seeding into either would answer a pending question by force, or run the
    capability twice. A guarantee that overrides a question is not a guarantee,
    it is a bug.

    Args:
        plan: Plan produced by the planner, or None when planning yielded none.
        directive: Validated ``{"capability", "subject"}`` payload, or None.

    Returns:
        The plan, with the guaranteed step present. ``None`` in and no
        directive gives ``None`` out — a directive with no plan is impossible
        by construction, since the planner always yields a plan object.
    """
    if not directive or plan is None:
        return plan

    if not plan.steps:
        logger.info(
            "capability_directive_skipped_stub_plan",
            capability=directive.get("capability"),
            reason="clarification or skill-bypass plan — nothing to enrich",
        )
        return plan

    capability = directive.get("capability", "")
    subject = (directive.get("subject") or "").strip()
    spec = CAPABILITY_DIRECTIVE_REGISTRY.get(capability)
    if spec is None or not subject:
        # Unknown capability cannot happen through the HTTP boundary (closed
        # Literal); reaching here means an internal caller built the payload by
        # hand. Log it rather than raising: the prose path still stands.
        logger.warning(
            "capability_directive_unresolvable",
            capability=capability or None,
            has_subject=bool(subject),
        )
        return plan

    if any(step.tool_name == spec.tool_name for step in plan.steps):
        # The capability is present, so the same supersession applies: the
        # planner reaching it on its own does not make the redundant steps any
        # less contradictory.
        dropped = _drop_superseded(plan, spec)
        logger.info(
            "capability_directive_already_planned",
            capability=capability,
            tool_name=spec.tool_name,
            step_count=len(plan.steps),
            superseded_dropped=dropped,
        )
        return plan

    # Local import: ``orchestration/__init__`` eagerly pulls the replanner and
    # the orchestrator, so importing plan_schemas at module level would drag
    # half the graph into the HTTP schema module. The edge is declared for
    # readers and mypy in the TYPE_CHECKING block above.
    from src.domains.agents.orchestration.plan_schemas import ExecutionStep, StepType

    plan.steps.insert(
        0,
        ExecutionStep(
            step_id=DIRECTIVE_STEP_ID,
            step_type=StepType.TOOL,
            agent_name=spec.agent_name,
            tool_name=spec.tool_name,
            parameters={spec.subject_parameter: subject},
            description=spec.description,
        ),
    )
    dropped = _drop_superseded(plan, spec)
    logger.info(
        "capability_directive_seeded",
        capability=capability,
        tool_name=spec.tool_name,
        step_count=len(plan.steps),
        superseded_dropped=dropped,
    )
    return plan


def _steps_read_by(steps: list[Any]) -> set[str]:
    """Step ids these steps read, both ways a plan expresses a dependency.

    The declared ``depends_on`` list AND a ``$steps.<id>.…`` reference anywhere
    inside the step. The two are not equivalent — a plan may reference a step's
    output without declaring the edge — and reading only the declaration would
    let a step be dropped while its value is still being consumed.

    Args:
        steps: The steps whose reads matter (the survivors of a removal pass).

    Returns:
        Every step id they depend on or reference.
    """
    # Local import: `orchestration/__init__` is heavy (replanner, orchestrator),
    # and this module is a leaf the HTTP schemas import.
    from src.domains.agents.orchestration.reference_validator import ReferenceValidator

    # The repository's ONE definition of what a step reference looks like —
    # re-deriving it here would make this a second authority on the syntax.
    return {dep for step in steps for dep in step.depends_on} | {
        match.group(1)
        for step in steps
        for match in ReferenceValidator.STEPS_REFERENCE_PATTERN.finditer(step.model_dump_json())
    }


def _drop_superseded(plan: ExecutionPlan, spec: CapabilityDirectiveSpec) -> list[str]:
    """Remove the steps the guaranteed capability already answers.

    Only steps NOTHING depends on are removed: a superseded step feeding a
    later one is load-bearing whatever it duplicates, and dropping it would
    leave a dangling ``$steps`` reference — trading a wrong sentence for a
    broken plan.

    "Depends on" is read BOTH ways a plan expresses it: the declared
    ``depends_on`` list AND a ``$steps.<id>.…`` reference anywhere inside
    another step. The two are not equivalent — a plan may reference a step's
    output without declaring the edge — and reading only the declaration would
    drop a step whose value is still being read.

    Only a SURVIVING step rescues: being read by another superseded step is no
    reason to stay, since that reader is leaving too. Resolved to a fixed point
    (removals only ever shrink the doomed set, so it terminates), because one
    pass would keep the head of a superseded chain alive for a consumer that no
    longer exists — and its user-scoped payload with it, which is the whole
    point of removing it.

    Args:
        plan: Plan carrying the seeded step (mutated).
        spec: Spec whose ``supersedes`` set drives the removal.

    Returns:
        Ids of the steps removed, for the trace.
    """
    if not spec.supersedes:
        return []

    doomed = {step.step_id for step in plan.steps if step.tool_name in spec.supersedes}
    while doomed:
        survivors = [step for step in plan.steps if step.step_id not in doomed]
        rescued = doomed & _steps_read_by(survivors)
        if not rescued:
            break
        doomed -= rescued
    if not doomed:
        return []
    # Rebuilt by step_id, never `list.remove`: ExecutionStep compares by VALUE,
    # so two structurally identical steps would drop the wrong one.
    plan.steps[:] = [step for step in plan.steps if step.step_id not in doomed]
    return sorted(doomed)


__all__ = [
    "CAPABILITY_DIRECTIVE_REGISTRY",
    "DIRECTIVE_STEP_ID",
    "CapabilityDirectiveSpec",
    "DirectiveCapability",
    "assert_registry_completeness",
    "ensure_directive_step",
]
