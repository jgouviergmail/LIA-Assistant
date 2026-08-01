"""A capability the user invoked by clicking must end up in the plan.

**The production defect (2026-08-01).** Pressing "run the 360°" on a named
relationship card sent a French sentence and nothing else. Three stochastic
stages then had to recover a certainty the browser already held: the tool scored
0.853, the best of the whole catalogue, and the plan called ``get_emails_tool``
instead. Reachability alone (ADR-191 half one) makes the right tool VISIBLE; it
cannot make the planner pick it. This is the half that makes it CERTAIN.

The contract has two halves and both are tested here, because either one alone
is a regression waiting to happen:

- the capability IS in the plan afterwards — always, whatever the LLM produced;
- everything the LLM produced that ADDS something is still there — the user
  asked to keep the surrounding tool calls, so the directive enriches rather
  than replaces. What the capability already answers is the exception, and it
  has its own class: a calendar lookup that ignores the person contradicts a
  stated gap instead of filling it.
"""

from __future__ import annotations

import pytest

from src.domains.agents.capability_directives import (
    CAPABILITY_DIRECTIVE_REGISTRY,
    DIRECTIVE_STEP_ID,
    DirectiveCapability,
    assert_registry_completeness,
    ensure_directive_step,
)
from src.domains.agents.orchestration.plan_schemas import (
    ExecutionPlan,
    ExecutionStep,
    StepType,
)

pytestmark = pytest.mark.unit

DIRECTIVE = {"capability": "person_overview", "subject": "Paul Martin"}


def _step(step_id: str, tool_name: str, **kwargs: object) -> ExecutionStep:
    return ExecutionStep(
        step_id=step_id,
        step_type=StepType.TOOL,
        agent_name="email_agent",
        tool_name=tool_name,
        **kwargs,  # type: ignore[arg-type]
    )


def _plan(*steps: ExecutionStep) -> ExecutionPlan:
    return ExecutionPlan(user_id="00000000-0000-0000-0000-000000000001", steps=list(steps))


class TestTheGuarantee:
    def test_the_capability_is_added_when_the_planner_missed_it(self) -> None:
        """The production plan, verbatim: three generic tools, no 360°."""
        plan = _plan(
            _step("step_1", "get_emails_tool"),
            _step("step_2", "get_events_tool"),
            _step("step_3", "get_contacts_tool"),
        )

        ensure_directive_step(plan, DIRECTIVE)

        assert [s.tool_name for s in plan.steps][0] == "get_person_overview_tool"
        assert plan.steps[0].parameters == {"person_name": "Paul Martin"}

    def test_the_planners_own_steps_survive_untouched(self) -> None:
        """Steps the capability does NOT cover are kept, parameters and all.

        "On conserve quand même les appels de tools en plus du 360" — yes, for
        everything that adds something. What the capability already answers is
        a different matter (see TestSupersededStepsAreDropped).
        """
        plan = _plan(
            _step("step_1", "get_tasks_tool", parameters={"query": "devis"}),
            _step("step_2", "unified_web_search_tool", depends_on=["step_1"]),
        )

        ensure_directive_step(plan, DIRECTIVE)

        assert [s.tool_name for s in plan.steps[1:]] == [
            "get_tasks_tool",
            "unified_web_search_tool",
        ]
        assert plan.steps[1].parameters == {"query": "devis"}
        assert plan.steps[2].depends_on == ["step_1"]

    def test_the_seeded_step_depends_on_nothing(self) -> None:
        """It is the user's own request: it must not wait on a generated step."""
        plan = _plan(_step("step_1", "get_emails_tool"))

        ensure_directive_step(plan, DIRECTIVE)

        assert plan.steps[0].depends_on == []
        assert plan.steps[0].step_id == DIRECTIVE_STEP_ID

    def test_the_step_id_cannot_collide_with_a_generated_one(self) -> None:
        """The planner numbers `step_N`; a collision would break depends_on."""
        plan = _plan(_step("step_1", "get_emails_tool"))

        ensure_directive_step(plan, DIRECTIVE)

        ids = [s.step_id for s in plan.steps]
        assert len(ids) == len(set(ids))
        assert not DIRECTIVE_STEP_ID.startswith("step_")


class TestTheNoOps:
    def test_no_directive_changes_nothing(self) -> None:
        """The overwhelming majority of turns. Byte-identical behaviour."""
        plan = _plan(_step("step_1", "get_emails_tool"))
        before = plan.model_dump()

        ensure_directive_step(plan, None)

        assert plan.model_dump() == before

    def test_an_already_planned_capability_is_left_alone(self) -> None:
        """The planner's parameters win — it may have resolved a fuller name."""
        plan = _plan(
            ExecutionStep(
                step_id="step_1",
                step_type=StepType.TOOL,
                agent_name="contact_agent",
                tool_name="get_person_overview_tool",
                parameters={"person_name": "Paul MARTIN (bureau)"},
            )
        )

        ensure_directive_step(plan, DIRECTIVE)

        assert len(plan.steps) == 1
        assert plan.steps[0].parameters == {"person_name": "Paul MARTIN (bureau)"}

    @pytest.mark.parametrize(
        "directive",
        [
            pytest.param({"capability": "nope", "subject": "X"}, id="unknown_capability"),
            pytest.param({"capability": "person_overview", "subject": "  "}, id="blank_subject"),
            pytest.param({"capability": "person_overview"}, id="missing_subject"),
            pytest.param({}, id="empty_payload"),
        ],
    )
    def test_an_unresolvable_directive_degrades_to_the_prose_path(
        self, directive: dict[str, str]
    ) -> None:
        """Never raise on a malformed payload: the sentence still stands."""
        plan = _plan(_step("step_1", "get_emails_tool"))

        ensure_directive_step(plan, directive)

        assert [s.tool_name for s in plan.steps] == ["get_emails_tool"]

    def test_no_plan_stays_no_plan(self) -> None:
        assert ensure_directive_step(None, DIRECTIVE) is None

    def test_the_subject_is_trimmed(self) -> None:
        plan = _plan(_step("step_1", "get_emails_tool"))

        ensure_directive_step(plan, {"capability": "person_overview", "subject": "  Marie  "})

        assert plan.steps[0].parameters == {"person_name": "Marie"}

    @pytest.mark.parametrize(
        "flag",
        [
            pytest.param("needs_clarification", id="the_system_is_asking_a_question"),
            pytest.param("skill_bypass_noop", id="execution_delegated_to_a_skill"),
        ],
    )
    def test_a_stub_plan_is_never_turned_into_an_execution(self, flag: str) -> None:
        """The only two shapes ExecutionPlan allows with zero steps.

        Seeding here would answer a pending clarification by force, or run the
        capability a second time alongside the skill. A guarantee that
        overrides a question is a bug, not a guarantee.
        """
        plan = ExecutionPlan(
            user_id="00000000-0000-0000-0000-000000000001",
            steps=[],
            metadata={flag: True},
        )

        ensure_directive_step(plan, DIRECTIVE)

        assert plan.steps == []


class TestTheRegistry:
    def test_every_capability_maps_to_a_registered_tool(self) -> None:
        """The boot assert, run in CI so a typo never reaches a lifespan."""
        from src.domains.agents.registry.agent_registry import AgentRegistry
        from src.domains.agents.registry.catalogue_loader import initialize_catalogue

        registry = AgentRegistry()
        initialize_catalogue(registry)

        assert_registry_completeness(registry)

    def test_a_capability_without_a_spec_is_refused(self) -> None:
        from unittest.mock import MagicMock

        registry = MagicMock()
        registry.list_tool_manifests.return_value = []
        original = dict(CAPABILITY_DIRECTIVE_REGISTRY)
        CAPABILITY_DIRECTIVE_REGISTRY.clear()
        try:
            with pytest.raises(AssertionError, match="person_overview"):
                assert_registry_completeness(registry)
        finally:
            CAPABILITY_DIRECTIVE_REGISTRY.update(original)

    def test_a_spec_pointing_at_an_unregistered_tool_is_refused(self) -> None:
        """Worse than no directive: the orchestrator would fail the step."""
        from unittest.mock import MagicMock

        registry = MagicMock()
        registry.list_tool_manifests.return_value = []

        with pytest.raises(AssertionError, match="get_person_overview_tool"):
            assert_registry_completeness(registry)

    def test_the_wire_literal_and_the_registry_agree(self) -> None:
        """The HTTP allowlist IS the registry's key set — one vocabulary."""
        from typing import get_args

        assert set(get_args(DirectiveCapability)) == set(CAPABILITY_DIRECTIVE_REGISTRY)

    def test_every_directive_tool_is_read_only(self) -> None:
        """This channel is reachable from a browser: no mutation may sit here."""
        from src.domains.agents.registry.agent_registry import AgentRegistry
        from src.domains.agents.registry.catalogue import is_read_only_tool
        from src.domains.agents.registry.catalogue_loader import initialize_catalogue

        registry = AgentRegistry()
        initialize_catalogue(registry)
        manifests = {m.name: m for m in registry.list_tool_manifests()}

        writable = [
            spec.tool_name
            for spec in CAPABILITY_DIRECTIVE_REGISTRY.values()
            if not is_read_only_tool(manifests[spec.tool_name])
        ]

        assert not writable, f"directive capabilities must be read-only, got {writable}"


class TestTheHttpBoundary:
    def test_an_unknown_capability_is_rejected_by_the_schema(self) -> None:
        """The closed Literal is the allowlist — no server-side check needed."""
        from pydantic import ValidationError

        from src.domains.agents.api.schemas import CapabilityDirectiveRequest

        with pytest.raises(ValidationError):
            CapabilityDirectiveRequest(capability="delete_email_tool", subject="X")  # type: ignore[arg-type]

    def test_a_valid_directive_round_trips(self) -> None:
        from src.domains.agents.api.schemas import CapabilityDirectiveRequest

        model = CapabilityDirectiveRequest(capability="person_overview", subject="Marie Dupont")

        assert model.model_dump() == DIRECTIVE | {"subject": "Marie Dupont"}

    def test_the_chat_request_stays_valid_without_a_directive(self) -> None:
        """Purely additive: every existing client keeps working untouched."""
        import uuid

        from src.domains.agents.api.schemas import ChatRequest

        request = ChatRequest(message="bonjour", user_id=uuid.uuid4(), session_id="s")

        assert request.directive is None


class TestSupersededStepsAreDropped:
    """An unrelated answer next to a stated gap contradicts it.

    Measured on the dev API, 2026-08-01: the 360° on a connected peer honestly
    reported no shared meeting — the peer is not in the address book, so no
    address could match an attendee — and the plan ALSO called
    ``get_events_tool``, which returned the user's own next event. The
    assistant presented "Goûter à la maison" as part of the 360°. The peer
    neither organised nor attended it.

    The user's rule, verbatim: *"si pas de mail dispo ou si pas de rdv peer
    organisateur ou invité → on ne déborde pas sur le calendrier du user, car
    cela transmet une fausse information."* The manifest already declared the
    tool SELF-CONTAINED; supersession is what makes that binding.
    """

    def test_the_calendar_lookup_that_ignores_the_person_is_dropped(self) -> None:
        plan = _plan(
            _step("step_1", "get_events_tool"),
            _step("step_2", "get_tasks_tool"),
        )

        ensure_directive_step(plan, DIRECTIVE)

        assert [s.tool_name for s in plan.steps] == [
            "get_person_overview_tool",
            "get_tasks_tool",
        ]

    def test_mail_and_address_book_go_the_same_way(self) -> None:
        plan = _plan(
            _step("step_1", "get_emails_tool"),
            _step("step_2", "get_contacts_tool"),
            _step("step_3", "get_tasks_tool"),
        )

        ensure_directive_step(plan, DIRECTIVE)

        assert [s.tool_name for s in plan.steps] == [
            "get_person_overview_tool",
            "get_tasks_tool",
        ]

    def test_a_superseded_step_someone_depends_on_is_kept(self) -> None:
        """Load-bearing beats redundant: dropping it would dangle a reference.

        A `$steps.step_1.…` reference into a removed step is a broken plan —
        strictly worse than the sentence supersession exists to prevent.
        """
        plan = _plan(
            _step("step_1", "get_contacts_tool"),
            _step("step_2", "send_email_tool", depends_on=["step_1"]),
        )

        ensure_directive_step(plan, DIRECTIVE)

        assert [s.tool_name for s in plan.steps] == [
            "get_person_overview_tool",
            "get_contacts_tool",
            "send_email_tool",
        ]

    def test_supersession_applies_when_the_planner_got_there_first(self) -> None:
        """Reaching the capability alone does not make the rest less wrong."""
        plan = _plan(
            ExecutionStep(
                step_id="step_1",
                step_type=StepType.TOOL,
                agent_name="contact_agent",
                tool_name="get_person_overview_tool",
                parameters={"person_name": "Paul Martin"},
            ),
            _step("step_2", "get_events_tool"),
        )

        ensure_directive_step(plan, DIRECTIVE)

        assert [s.tool_name for s in plan.steps] == ["get_person_overview_tool"]

    def test_nothing_is_dropped_without_a_directive(self) -> None:
        """Supersession is the price of a GUARANTEE, never a global rule.

        A freely-planned turn that happens to call the overview alongside a
        calendar lookup is the planner's own reasoning, and stays untouched.
        """
        plan = _plan(
            _step("step_1", "get_events_tool"),
            _step("step_2", "get_emails_tool"),
        )
        before = [s.tool_name for s in plan.steps]

        ensure_directive_step(plan, None)

        assert [s.tool_name for s in plan.steps] == before


class TestSupersessionNeverBreaksAPlan:
    """A dangling reference is worse than the sentence supersession prevents."""

    def test_a_step_referenced_without_depends_on_is_kept(self) -> None:
        """The two ways a plan expresses a dependency are not equivalent.

        `depends_on` is the declared edge; `$steps.<id>.…` inside parameters is
        the actual read. A plan may carry the second without the first, and
        dropping on the declaration alone would leave the reference dangling.
        """
        plan = _plan(
            _step("step_1", "get_contacts_tool"),
            _step(
                "step_2",
                "send_email_tool",
                parameters={"to": "$steps.step_1.contacts[0].emailAddresses[0].value"},
            ),
        )

        ensure_directive_step(plan, DIRECTIVE)

        assert "step_1" in [s.step_id for s in plan.steps]

    def test_an_unreferenced_twin_still_goes(self) -> None:
        """The guard must not become "keep everything": only what is read."""
        plan = _plan(
            _step("step_1", "get_contacts_tool"),
            _step("step_2", "get_contacts_tool"),
            _step(
                "step_3",
                "send_email_tool",
                parameters={"to": "$steps.step_1.contacts[0].emailAddresses[0].value"},
            ),
        )

        ensure_directive_step(plan, DIRECTIVE)

        kept = [s.step_id for s in plan.steps]
        assert "step_1" in kept
        assert "step_2" not in kept

    def test_the_plan_never_ends_up_empty(self) -> None:
        """Every step superseded: the guaranteed one is what remains."""
        plan = _plan(
            _step("step_1", "get_emails_tool"),
            _step("step_2", "get_events_tool"),
            _step("step_3", "get_contacts_tool"),
        )

        ensure_directive_step(plan, DIRECTIVE)

        assert [s.tool_name for s in plan.steps] == ["get_person_overview_tool"]
        assert len(plan.steps) >= 1


class TestSupersededChainsGoWhole:
    """Being read by a step that is also leaving is no reason to stay.

    One pass over the whole plan keeps the head of a superseded chain alive for
    a consumer that no longer exists — and its user-scoped payload with it,
    which is exactly what supersession removes.
    """

    def test_a_chain_of_superseded_steps_leaves_entirely(self) -> None:
        plan = _plan(
            _step("step_1", "get_contacts_tool"),
            _step(
                "step_2",
                "get_emails_tool",
                depends_on=["step_1"],
                parameters={"from": "$steps.step_1.contacts[0].emailAddresses[0].value"},
            ),
        )

        ensure_directive_step(plan, DIRECTIVE)

        assert [s.tool_name for s in plan.steps] == ["get_person_overview_tool"]

    def test_a_surviving_consumer_still_rescues_the_whole_chain(self) -> None:
        """The rescue must propagate: step_3 needs step_2, which needs step_1."""
        plan = _plan(
            _step("step_1", "get_contacts_tool"),
            _step("step_2", "get_emails_tool", depends_on=["step_1"]),
            _step("step_3", "send_email_tool", depends_on=["step_2"]),
        )

        ensure_directive_step(plan, DIRECTIVE)

        assert [s.step_id for s in plan.steps] == [
            DIRECTIVE_STEP_ID,
            "step_1",
            "step_2",
            "step_3",
        ]
