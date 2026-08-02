"""The checkpoint allowlist must name classes where they are DEFINED.

``JsonPlusSerializer`` matches allowlist entries against a value's real
``__module__``. A re-export therefore does NOT satisfy it: moving a class to a
new module while leaving an ``as``-alias behind silently breaks deserialization,
and the object comes back as a plain ``dict``/``str`` instead of its type.

The defect this closes, observed in production 2026-08-01::

    Blocked deserialization of
    src.domains.agents.orchestration.validation_models.SemanticValidationResult
    - not in allowed_msgpack_modules

``SemanticValidationResult`` & co. moved to ``validation_models`` on 2026-07-17
(``semantic_validator`` only re-exports them), but the allowlist still named the
old module. Downstream, ``planner_node_v3`` gates the replan feedback behind
``hasattr(semantic_validation, "issues")`` — false on a dict — so a resumed turn
silently lost its validation feedback.

Two oracles, deliberately:

* the structural one (``__module__`` is the definition site) catches the drift
  at the moment a class moves, naming the fix;
* the behavioral one (a fully-populated object survives a real round-trip)
  catches whatever the structural one cannot foresee — a nested type nobody
  thought to allowlist shows up as a degraded member, not as a passing test.

What needs an entry is narrower than it looks, and worth stating precisely
because a first reading of these measurements got it backwards: a value stored
at the ROOT of a channel always needs one, whatever its kind. A NESTED value
needs one only under a dataclass — a Pydantic container re-validates and
recreates its members by itself. See the dedicated test class below.
"""

from __future__ import annotations

import importlib
from typing import Any

import pytest
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from src.domains.agents.orchestration.validation_models import (
    CriticalityLevel,
    SemanticIssue,
    SemanticIssueType,
    SemanticValidationResult,
)
from src.domains.agents.orchestration.validator import ValidationIssue, ValidationResult
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.conversations.checkpointer import _CHECKPOINT_ALLOWED_MODULES

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def serde() -> JsonPlusSerializer:
    """The serializer built exactly as ``get_checkpointer`` builds it."""
    return JsonPlusSerializer(allowed_msgpack_modules=_CHECKPOINT_ALLOWED_MODULES)


def _round_trip(serde: JsonPlusSerializer, obj: Any) -> Any:
    """Serialize and deserialize through the production serializer."""
    return serde.loads_typed(serde.dumps_typed(obj))


def _valid_tool_step() -> Any:
    """A TOOL step exactly as every producer builds it — ``agent_name`` included.

    Not a detail: an omitted ``agent_name`` used to slip through construction and
    then degrade the step to a mapping on the way back. Test data that skips it
    measures the defect instead of the behaviour.
    """
    from src.domains.agents.orchestration.plan_schemas import ExecutionStep, StepType

    return ExecutionStep(
        step_id="step_1",
        step_type=StepType.TOOL,
        agent_name="emails_agent",
        tool_name="send_email_tool",
        parameters={"to": "someone@example.org"},
    )


def _plan_with(*steps: Any) -> Any:
    from src.domains.agents.orchestration.plan_schemas import ExecutionPlan

    return ExecutionPlan(plan_id="p1", user_id="u1", session_id="s1", steps=list(steps))


def _verdict_with_one_issue() -> SemanticValidationResult:
    return SemanticValidationResult(
        is_valid=False,
        issues=[
            SemanticIssue(
                issue_type=SemanticIssueType.MISSING_STEP,
                description="d",
                severity="high",
            )
        ],
        confidence=1.0,
        requires_clarification=False,
        clarification_questions=[],
        validation_duration_seconds=0.1,
    )


@pytest.mark.parametrize(("module_path", "class_name"), _CHECKPOINT_ALLOWED_MODULES)
class TestAllowlistEntriesAreCanonical:
    """Every entry must point at a real, canonical definition site."""

    def test_entry_resolves_to_an_existing_class(self, module_path: str, class_name: str) -> None:
        module = importlib.import_module(module_path)
        assert hasattr(module, class_name), (
            f"{module_path}.{class_name} is in the checkpoint allowlist but does not "
            f"exist. A stale entry is dead weight: it allowlists nothing, and the type "
            f"it was meant to protect deserializes into a plain dict/str."
        )

    def test_entry_is_the_definition_site_not_a_re_export(
        self, module_path: str, class_name: str
    ) -> None:
        cls = getattr(importlib.import_module(module_path), class_name)
        assert cls.__module__ == module_path, (
            f"Allowlist names {module_path}.{class_name}, but the class is defined in "
            f"{cls.__module__}. msgpack matches on the DEFINITION module, so this entry "
            f"protects nothing and {class_name} will come back degraded after a "
            f"checkpoint resume. Fix: point the allowlist at {cls.__module__}."
        )


class TestNestingBehaviourDependsOnTheContainerKind:
    """What a nested custom type needs depends on the KIND of its container.

    Measured, not assumed — and measured a second time after a first reading of
    these results proved wrong. The serializer rebuilds an allowlisted type by
    calling its constructor, so a Pydantic container **re-validates** its
    members:

    * under a **dataclass**, nothing re-validates: a nested custom type needs
      its OWN allowlist entry, or it comes back as a plain ``dict``;
    * under a **BaseModel**, the parent's validation recreates the member from
      its dict — no entry needed, ``ExecutionStep`` is proof (it is absent from
      the allowlist and still comes back typed);
    * unless that member **fails its own validation**, in which case the
      constructor call raises, the hook falls back, and the member silently
      degrades to ``dict``.

    That last case is the trap: a model that ACCEPTS at construction what it
    REFUSES on re-read degrades in silence. Pydantic does not validate default
    values, so an omitted field slips through construction and then trips its
    own validator on the way back (``ExecutionStep.agent_name``, ADR-195).
    """

    def test_a_dataclass_rebuilds_its_nested_models(self, serde: JsonPlusSerializer) -> None:
        original = SemanticValidationResult(
            is_valid=False,
            issues=[
                SemanticIssue(
                    issue_type=SemanticIssueType.MISSING_STEP,
                    description="d",
                    severity="high",
                )
            ],
            confidence=1.0,
            requires_clarification=False,
            clarification_questions=[],
            validation_duration_seconds=0.1,
        )

        restored = _round_trip(serde, original)

        assert isinstance(restored, SemanticValidationResult)
        assert isinstance(restored.issues[0], SemanticIssue), (
            "a dataclass serializes each field on its own, so the nested model "
            "keeps its type marker — if this ever fails, the allowlist lost an entry"
        )

    def test_a_dataclass_member_without_its_own_entry_degrades(self) -> None:
        """The reason ``SemanticIssue`` has an entry of its own.

        Re-measured with that single entry removed: nothing under a dataclass
        re-validates, so the member comes back as a bare mapping.
        """
        allowlist_without_issue = [
            e for e in _CHECKPOINT_ALLOWED_MODULES if e[1] != "SemanticIssue"
        ]
        crippled = JsonPlusSerializer(allowed_msgpack_modules=allowlist_without_issue)

        restored = _round_trip(crippled, _verdict_with_one_issue())

        assert isinstance(restored.issues[0], dict), (
            "if this stops degrading, a dataclass member no longer needs its own "
            "entry and the allowlist can shrink — verify before removing any."
        )

    def test_a_valid_basemodel_member_survives_without_an_entry(
        self, serde: JsonPlusSerializer
    ) -> None:
        """A Pydantic container re-validates, so its members need no entry.

        ``ExecutionStep`` is deliberately ABSENT from the allowlist and still
        comes back typed. Adding an entry for it would be cargo cult.
        """
        from src.domains.agents.orchestration.plan_schemas import ExecutionPlan, ExecutionStep

        assert not any(
            e[1] == "ExecutionStep" for e in _CHECKPOINT_ALLOWED_MODULES
        ), "precondition: this test proves an entry is unnecessary, so there must not be one"

        restored = _round_trip(serde, _plan_with(_valid_tool_step()))

        assert isinstance(restored, ExecutionPlan)
        assert isinstance(restored.steps[0], ExecutionStep), (
            "a valid nested model must come back typed. If this fails, the "
            "container stopped re-validating and every reader of plan.steps "
            "needs a mapping fallback."
        )
        assert restored.steps[0].parameters["to"] == "someone@example.org"

    def test_a_member_that_fails_its_own_validation_degrades_silently(
        self, serde: JsonPlusSerializer
    ) -> None:
        """The trap, pinned: accepted at construction, refused on re-read.

        ``agent_name`` is required for a TOOL step, but Pydantic does not
        validate defaults — so omitting it slips through construction. On the
        way back it is passed EXPLICITLY as None, the validator fires, the
        constructor raises, and the member degrades to a mapping with no error
        surfaced anywhere. This is why the model gained a ``model_validator``
        (ADR-195): the object can no longer reach a checkpoint in that state.
        """
        plan = _plan_with(_valid_tool_step())
        # Post-construction mutation: the ONLY way left to reach this state now
        # that both the step and its plan refuse it up front. `frozen=False` is
        # deliberate (steps carry resolved parameters during execution), so a
        # future writer can still produce it — hence this test.
        object.__setattr__(plan.steps[0], "agent_name", None)

        restored = _round_trip(serde, plan)

        assert isinstance(restored.steps[0], dict), (
            "a member failing its own validation must be shown to degrade — this "
            "is the mechanism the model_validator now prevents upstream"
        )
        assert (
            restored.steps[0]["parameters"]["to"] == "someone@example.org"
        ), "the DATA survives intact; only the type is lost"


class TestCheckpointedVerdictsSurviveResume:
    """A verdict must come back as its type, not as a bare mapping.

    Composite objects on purpose: allowlisting the container is not enough when
    its members carry their own custom types.
    """

    def test_semantic_validation_result_survives(self, serde: JsonPlusSerializer) -> None:
        original = SemanticValidationResult(
            is_valid=False,
            issues=[
                SemanticIssue(
                    issue_type=SemanticIssueType.MISSING_DEPENDENCY,
                    description="step_2 references step_1 which produces no contacts",
                    severity="error",
                    # A deterministic rejection: technical English, never shown.
                    user_facing=False,
                )
            ],
            confidence=0.8,
            requires_clarification=False,
            clarification_questions=[],
            validation_duration_seconds=0.42,
            criticality=CriticalityLevel.HIGH,
        )

        restored = _round_trip(serde, original)

        assert isinstance(restored, SemanticValidationResult), (
            f"SemanticValidationResult degraded to {type(restored).__name__} across a "
            f"checkpoint round-trip. planner_node_v3 gates the replan feedback behind "
            f"hasattr(semantic_validation, 'issues'), which is False on a mapping — the "
            f"turn silently loses its validation feedback."
        )
        assert restored.criticality is CriticalityLevel.HIGH
        assert len(restored.issues) == 1
        assert isinstance(restored.issues[0], SemanticIssue), (
            "The nested SemanticIssue degraded: allowlisting the container is not "
            "enough, every custom member type needs its own entry."
        )
        assert restored.issues[0].issue_type is SemanticIssueType.MISSING_DEPENDENCY
        assert restored.issues[0].user_facing is False, (
            "user_facing decides whether the description reaches the USER (ADR-195). "
            "Lost across a resume it defaults back to True, and a resumed turn shows "
            "the English technical literal as its clarification question — the very "
            "defect ADR-195 closed, brought back by a checkpoint."
        )

    def test_plan_validation_result_survives(self, serde: JsonPlusSerializer) -> None:
        original = ValidationResult(is_valid=False)
        original.add_error(
            code=ToolErrorCode.INVALID_INPUT,
            message="unknown tool",
            step_index=0,
            tool_name="ghost_tool",
        )

        restored = _round_trip(serde, original)

        assert isinstance(restored, ValidationResult), (
            f"ValidationResult degraded to {type(restored).__name__}. "
            f"summarize_plan_blockers (ADR-184) narrows on isinstance and would "
            f"silently stop reporting blocked capabilities after a HITL resume."
        )
        assert isinstance(restored.errors[0], ValidationIssue)
        assert restored.errors[0].code is ToolErrorCode.INVALID_INPUT
