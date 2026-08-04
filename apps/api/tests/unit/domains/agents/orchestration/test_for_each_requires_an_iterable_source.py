"""A ``for_each`` can only be demanded when something in the plan produces a list.

Production dev, 2026-08-02. The request was::

    "Utilise le navigateur pour aller sur Amazon, chercher un macbook pro m5,
     puis envoie-moi par email les 3 premiers résultats"

The analyzer read "les 3 premiers résultats" as *do it for EACH browsers* and
set ``for_each_detected=True`` with ``for_each_collection_key="browsers"``. The
validator then required a ``for_each`` step — but ``browser_task_tool`` declares
a single ``content`` string and NO collection at all, so no plan could ever
carry ``for_each: "$steps.step_1.browsers"``.

The result was a demand no planner can satisfy: 16 planning cycles, 10 routes to
clarification, and the same question re-asked forever whatever the user replied
(the answer cannot change ``for_each_detected``, which comes from the analysis
of the original message).

Doctrine ADR-184 — "whatever a validator can reject, its producer must be able
to read", and here to PRODUCE: an unsatisfiable requirement is not validation,
it is a dead end. So the rule now needs a source to iterate over, and the source
of truth for that is the manifests ADR-194 made truthful.
"""

from __future__ import annotations

import pytest

from src.domains.agents.orchestration.plan_schemas import ExecutionPlan, ExecutionStep, StepType
from src.domains.agents.orchestration.semantic_validator import (
    SemanticIssueType,
    validate_for_each_patterns,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True, scope="module")
def _catalogue_loaded() -> None:
    """Populate the GLOBAL registry, as the lifespan does at boot.

    The rule reads manifests through ``get_global_registry`` (same seam as
    ``tool_is_mutation``). Left empty, every tool looks unknown and the
    conservative branch fires — which would make this suite measure the fallback
    instead of the rule.

    IDEMPOTENT on purpose. The registry is global to the PROCESS, and
    ``register_agent_manifest`` raises ``AgentManifestAlreadyRegistered`` on a
    second registration. Under ``pytest-xdist`` the worker that runs this module
    may already have run another test that initialised the same registry, so the
    unconditional call raised at SETUP — an intermittent error that depends
    purely on how the workers were partitioned, and therefore reappears whenever
    the suite's size changes.
    """
    from src.domains.agents.registry.agent_registry import get_global_registry
    from src.domains.agents.registry.catalogue_loader import initialize_catalogue

    registry = get_global_registry()
    if not registry.list_agent_manifests():
        initialize_catalogue(registry)


def _step(step_id: str, tool_name: str) -> ExecutionStep:
    return ExecutionStep(
        step_id=step_id,
        step_type=StepType.TOOL,
        tool_name=tool_name,
        agent_name="test_agent",
        parameters={"query": "test"},
    )


def _plan(*steps: ExecutionStep) -> ExecutionPlan:
    return ExecutionPlan(plan_id="test", user_id="test_user", steps=list(steps))


#: What the analyzer produced on the production request.
_CARDINALITY_ON_A_NON_COLLECTION = {
    "for_each_detected": True,
    "for_each_collection_key": "browsers",
    "cardinality_magnitude": 3,
}


class TestAnUnsatisfiableForEachIsNotDemanded:
    def test_the_production_case_is_no_longer_rejected(self) -> None:
        """browser + email: nothing in the plan yields a list to iterate over."""
        plan = _plan(_step("step_1", "browser_task_tool"), _step("step_2", "send_email_tool"))

        is_valid, feedback, issue_type = validate_for_each_patterns(
            plan, _CARDINALITY_ON_A_NON_COLLECTION
        )

        assert is_valid, (
            f"the plan was rejected for missing a for_each over a collection no step "
            f"produces — an unsatisfiable demand, which is how the loop started: {feedback}"
        )
        assert issue_type is None

    def test_a_plan_that_does_produce_a_collection_is_still_checked(self) -> None:
        """The protection must survive: a real missing for_each is still caught.

        ``get_contacts_tool`` declares ``contacts[]``, so iterating IS possible
        and a plan omitting ``for_each`` is genuinely under-delivering.
        """
        plan = _plan(_step("step_1", "get_contacts_tool"), _step("step_2", "send_email_tool"))

        is_valid, _, issue_type = validate_for_each_patterns(
            plan,
            {
                "for_each_detected": True,
                "for_each_collection_key": "contacts",
                "cardinality_magnitude": None,
            },
        )

        assert not is_valid
        assert issue_type is SemanticIssueType.FOR_EACH_MISSING_CARDINALITY

    def test_an_unknown_tool_keeps_the_previous_behaviour(self) -> None:
        """No manifest means no proof of absence — stay conservative and reject.

        Disabling a safety net requires evidence, not ignorance.
        """
        plan = _plan(_step("step_1", "a_tool_with_no_manifest_at_all"))

        is_valid, _, issue_type = validate_for_each_patterns(plan, _CARDINALITY_ON_A_NON_COLLECTION)

        assert not is_valid
        assert issue_type is SemanticIssueType.FOR_EACH_MISSING_CARDINALITY


class TestTheFeedbackNamesACollectionThatExists:
    """Telling the planner to iterate over a key nothing produces is a dead end.

    Measured across the catalogue: 5 context types out of 18 are declared without
    any manifest producing a collection of that name. Four of them produce no
    collection at all and are handled above. ``web_searchs`` is the fifth and
    behaves differently: ``unified_web_search_tool`` DOES return a list, but it
    is called ``results``. Suggesting ``$steps.step_1.web_searchs`` sends the
    planner after a key that will never resolve.
    """

    def test_the_suggested_reference_uses_a_declared_collection(self) -> None:
        plan = _plan(_step("step_1", "unified_web_search_tool"), _step("step_2", "send_email_tool"))

        is_valid, feedback, _ = validate_for_each_patterns(
            plan,
            {
                "for_each_detected": True,
                "for_each_collection_key": "web_searchs",
                "cardinality_magnitude": None,
            },
        )

        assert not is_valid, "a real collection exists, so the rule must still apply"
        assert feedback is not None
        assert "$steps.step_1.results" in feedback, (
            f"the fix must point at a collection the plan actually produces, not at "
            f"the context key the analyzer guessed: {feedback}"
        )

    def test_a_nested_collection_is_suggested_at_its_real_depth(self) -> None:
        """`get_route_tool` publishes `route.steps` (array) under `route` (object).

        Suggesting `$steps.step_1.route` would tell the planner to iterate over
        an object — unreachable advice of exactly the kind this rule exists to
        stop producing.
        """
        plan = _plan(_step("step_1", "get_route_tool"), _step("step_2", "send_email_tool"))

        _, feedback, _ = validate_for_each_patterns(
            plan,
            {
                "for_each_detected": True,
                "for_each_collection_key": "routes",
                "cardinality_magnitude": None,
            },
        )

        assert feedback is not None
        assert "$steps.step_1.route.steps" in feedback, feedback
