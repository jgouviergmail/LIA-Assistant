"""Truthful reporting of a plan the validator refused (defect 2026-07-30).

Measured failure (dev logs 303d7ce3 / 43e9bded): the planner built a plan over
``get_events_tool`` and ``get_contacts_tool``, the validator rejected BOTH
steps for missing OAuth scopes, and the turn continued anyway. The response LLM
saw only empty tool results and improvised a diagnosis — "aucun service de
contacts ni d'agenda n'est configuré... nous frôlons le bégaiement
technologique" — which was wrong in the way that matters most: it blamed the
user's configuration for a routing mistake, three turns in a row, with
increasing sarcasm.

The rule this module encodes: when the validator blocks steps, the response
states EXACTLY which capabilities were blocked and why, and generalises to
nothing else. It is deliberately not specific to OAuth scopes — every
``ToolErrorCode`` the validator can emit produces the same shape of honest
report, because the failure mode (an LLM inventing a plausible diagnosis to
fill a silence) is a property of the silence, not of the error code.
"""

import pytest

from src.domains.agents.orchestration.plan_schemas import (
    ExecutionPlan,
    ExecutionStep,
    StepType,
)
from src.domains.agents.orchestration.validator import ValidationIssue, ValidationResult
from src.domains.agents.services.plan_blockers import (
    BLOCKER_REASONS,
    PlanBlocker,
    attempted_tool_names,
    format_plan_blockers,
    summarize_plan_blockers,
)
from src.domains.agents.tools.common import ToolErrorCode


def _issue(
    code: ToolErrorCode = ToolErrorCode.UNAUTHORIZED,
    tool_name: str = "get_events_tool",
    step_index: int = 0,
    severity: str = "error",
    message: str = "Missing required scopes: https://www.googleapis.com/auth/calendar",
) -> ValidationIssue:
    return ValidationIssue(
        severity=severity,
        code=code,
        message=message,
        step_index=step_index,
        tool_name=tool_name,
    )


def _result(*issues: ValidationIssue, is_valid: bool = False) -> ValidationResult:
    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity != "error"]
    return ValidationResult(
        is_valid=is_valid,
        errors=errors,
        warnings=warnings,
        total_steps=max((i.step_index or 0) + 1 for i in issues) if issues else 0,
    )


# =========================================================================
# summarize_plan_blockers
# =========================================================================


def test_valid_plan_produces_no_blockers():
    """The overwhelmingly common case must cost nothing and say nothing."""
    assert summarize_plan_blockers(ValidationResult(is_valid=True)) == []


def test_missing_validation_result_produces_no_blockers():
    """Conversation turns never run the validator."""
    assert summarize_plan_blockers(None) == []


@pytest.mark.parametrize(
    "stale",
    [
        {"is_valid": False, "errors": [{"code": "UNAUTHORIZED"}]},
        {},
        "not-a-result",
        42,
    ],
)
def test_non_dataclass_state_value_is_ignored_instead_of_raising(stale):
    """LangGraph state survives msgpack: a resumed turn may hold a mapping.

    Reading it with attribute access would raise INSIDE the response node,
    where an exception costs the entire answer — strictly worse than the
    silence this whole module exists to replace.
    """
    assert summarize_plan_blockers(stale) == []


def test_production_defect_is_reported_per_capability():
    """Request 303d7ce3: two steps, two capabilities, one truthful report."""
    blockers = summarize_plan_blockers(
        _result(
            _issue(tool_name="get_contacts_tool", step_index=0),
            _issue(tool_name="get_events_tool", step_index=1),
        )
    )

    assert [b.tool_name for b in blockers] == ["get_contacts_tool", "get_events_tool"]
    assert {b.reason for b in blockers} == {BLOCKER_REASONS[ToolErrorCode.UNAUTHORIZED]}


def test_warnings_are_not_blockers():
    """A warning did not block anything — reporting it would be a new lie."""
    assert summarize_plan_blockers(_result(_issue(severity="warning"))) == []


def test_same_tool_blocked_twice_is_reported_once():
    """Two steps on one tool is one capability the user must hear about."""
    blockers = summarize_plan_blockers(
        _result(
            _issue(tool_name="get_events_tool", step_index=0),
            _issue(tool_name="get_events_tool", step_index=2),
        )
    )

    assert len(blockers) == 1


@pytest.mark.parametrize("code", list(ToolErrorCode))
def test_every_error_code_is_reportable(code):
    """Generalisation contract: no code may fall through to a silent gap.

    An unmapped code must still produce a blocker with a usable reason — the
    honesty layer degrades to "blocked, cause unnamed", never to nothing.
    """
    blockers = summarize_plan_blockers(_result(_issue(code=code)))

    assert len(blockers) == 1
    assert blockers[0].reason
    assert blockers[0].code == code.value


def test_global_error_without_a_tool_is_still_reported():
    """A plan-level rejection (no step, no tool) must not vanish."""
    blockers = summarize_plan_blockers(
        _result(_issue(code=ToolErrorCode.INVALID_INPUT, tool_name=None, step_index=None))
    )

    assert len(blockers) == 1
    assert blockers[0].tool_name is None


def test_blockers_are_capped():
    """A pathological plan must not flood the response prompt."""
    issues = [_issue(tool_name=f"tool_{i}", step_index=i) for i in range(50)]

    assert len(summarize_plan_blockers(_result(*issues))) <= 10


# =========================================================================
# format_plan_blockers
# =========================================================================


def test_formatted_block_names_the_tool_and_the_reason():
    formatted = format_plan_blockers(
        [PlanBlocker(tool_name="get_events_tool", code="UNAUTHORIZED", reason="not authorized")]
    )

    assert "get_events_tool" in formatted
    assert "not authorized" in formatted


def test_formatted_block_never_leaks_raw_scope_urls():
    """Raw scope URLs are token waste and mean nothing to the user.

    The validator message carries them; the directive must carry the
    capability and the cause instead.
    """
    blockers = summarize_plan_blockers(
        _result(
            _issue(
                message=(
                    "Missing required scopes: https://www.googleapis.com/auth/calendar, "
                    "https://www.googleapis.com/auth/calendar.readonly"
                )
            )
        )
    )

    assert "https://" not in format_plan_blockers(blockers)


def test_empty_blockers_format_to_nothing():
    """No blockers, no directive — an empty system block breaks Anthropic."""
    assert format_plan_blockers([]) == ""


# =========================================================================
# attempted_tool_names — what the turn actually tried
# =========================================================================


def _plan(*tool_names: str) -> ExecutionPlan:
    return ExecutionPlan(
        plan_id="p1",
        user_id="u1",
        session_id="s1",
        steps=[
            ExecutionStep(
                step_id=f"step_{index + 1}",
                step_type=StepType.TOOL,
                agent_name="emails_agent",
                tool_name=name,
                parameters={},
            )
            for index, name in enumerate(tool_names)
        ],
    )


def test_a_step_that_returned_data_counts_as_attempted():
    """A successful TOOL step stores its payload, with no `success` key."""
    completed = {"step_1": {"emails": [{"id": "a"}], "total": 1}}

    assert attempted_tool_names(_plan("get_emails_tool"), completed) == frozenset(
        {"get_emails_tool"}
    )


def test_a_step_that_ran_empty_still_counts_as_attempted():
    """Zero results is an answer; "blocked" would be a different claim."""
    completed = {"step_1": {"emails": [], "total": 0}}

    assert attempted_tool_names(_plan("get_emails_tool"), completed) == frozenset(
        {"get_emails_tool"}
    )


def test_a_step_that_ran_and_failed_counts_as_attempted():
    """RC1.2 (production 2026-10-07): the step reached its provider and failed.

    Its failure is the runtime failures directive's to tell. Counted as never
    run, it kept a verdict the plan carried, and the « blocked » directive —
    which said « not connected » — overrode the failures directive, which
    forbids saying it.
    """
    completed = {"step_1": {"success": False, "error": "boom"}}

    assert attempted_tool_names(_plan("get_emails_tool"), completed) == frozenset(
        {"get_emails_tool"}
    )


def test_a_step_whose_data_is_a_list_counts_as_attempted():
    """The executor stores a step's ``data`` as-is, and ``data`` may be a list."""
    completed = {"step_1": [{"id": "a"}]}

    assert attempted_tool_names(_plan("get_emails_tool"), completed) == frozenset(
        {"get_emails_tool"}
    )


def test_a_for_each_step_counts_through_its_items():
    """Items are stored under ``step_2_item_N`` before (or without) an aggregate."""
    completed = {"step_1": {"contacts": []}, "step_2_item_0": {"success": False}}

    assert attempted_tool_names(
        _plan("get_contacts_tool", "send_email_tool"), completed
    ) == frozenset({"get_contacts_tool", "send_email_tool"})


def test_an_item_key_never_matches_a_longer_step_id():
    """``step_1_item_0`` belongs to ``step_1``, never to ``step_10`` or ``step_1x``."""
    plan = ExecutionPlan(
        plan_id="p1",
        user_id="u1",
        session_id="s1",
        steps=[
            ExecutionStep(
                step_id="step_10",
                step_type=StepType.TOOL,
                agent_name="emails_agent",
                tool_name="get_emails_tool",
                parameters={},
            )
        ],
    )

    assert attempted_tool_names(plan, {"step_1_item_0": {"ok": True}}) == frozenset()


def test_a_step_that_never_ran_does_not_count_as_attempted():
    assert attempted_tool_names(_plan("get_emails_tool"), {}) == frozenset()


def test_only_the_steps_with_an_outcome_are_reported():
    completed = {"step_1": {"contacts": []}}

    assert attempted_tool_names(
        _plan("get_contacts_tool", "get_events_tool"), completed
    ) == frozenset({"get_contacts_tool"})


@pytest.mark.parametrize("plan", [None, "stale", 42, {}])
def test_a_stale_or_absent_plan_reports_nothing(plan):
    """State survives msgpack; never raise inside the response node."""
    assert attempted_tool_names(plan, {"step_1": {"ok": True}}) == frozenset()


@pytest.mark.parametrize("completed", [None, "stale", 42, []])
def test_stale_completed_steps_report_nothing(completed):
    assert attempted_tool_names(_plan("get_emails_tool"), completed) == frozenset()


# =========================================================================
# The v1.27.3 regression: a blocked verdict on a step that actually ran
# =========================================================================


def test_a_tool_that_ran_is_not_reported_as_blocked():
    """Production 2026-07-31, request 83c98053.

    ``max_results=20`` broke a cap of 10, so the plan was invalid — but the
    step ran, ten emails reached the registry, and the answer still told the
    user the retrieval "had been blocked" and to go check their connector.
    """
    blockers = summarize_plan_blockers(
        _result(_issue(code=ToolErrorCode.CONSTRAINT_VIOLATION, tool_name="get_emails_tool")),
        attempted_tools=frozenset({"get_emails_tool"}),
    )

    assert blockers == []


def test_the_founding_defect_still_reports_its_blockers():
    """Request 303d7ce3 must keep working: nothing ran, so nothing is hidden."""
    blockers = summarize_plan_blockers(
        _result(
            _issue(tool_name="get_contacts_tool", step_index=0),
            _issue(tool_name="get_events_tool", step_index=1),
        ),
        attempted_tools=frozenset(),
    )

    assert [b.tool_name for b in blockers] == ["get_contacts_tool", "get_events_tool"]


def test_a_failed_attempt_is_never_reported_as_blocked():
    """Production 2026-10-07 (run b148e908): the verdict of a step that ran.

    The validator judged three steps ``UNAUTHORIZED``; the two contact reads
    succeeded and the reply failed on its own reference. The answer said the
    reply capability was « not connected »: the failure was real, the cause
    was the verdict's.
    """
    blockers = summarize_plan_blockers(
        _result(
            _issue(tool_name="get_contacts_tool", step_index=0),
            _issue(tool_name="reply_email_tool", step_index=2),
        ),
        attempted_tools=attempted_tool_names(
            _plan("get_contacts_tool", "get_contacts_tool", "reply_email_tool"),
            {
                "step_1": {"contacts": [{"id": "c1"}]},
                "step_2": {"contacts": [{"id": "c2"}]},
                "step_3": {"success": False, "error": "reference_resolution_failed"},
            },
        ),
    )

    assert blockers == []


def test_a_partial_turn_reports_only_what_did_not_run():
    """Half a truth told as a total failure is still a false diagnosis."""
    blockers = summarize_plan_blockers(
        _result(
            _issue(tool_name="get_contacts_tool", step_index=0),
            _issue(tool_name="get_events_tool", step_index=1),
        ),
        attempted_tools=frozenset({"get_contacts_tool"}),
    )

    assert [b.tool_name for b in blockers] == ["get_events_tool"]


def test_a_plan_level_blocker_is_silenced_once_anything_ran():
    """`the plan itself` cannot be claimed blocked when steps produced data."""
    blockers = summarize_plan_blockers(
        _result(_issue(code=ToolErrorCode.FORBIDDEN, tool_name=None)),
        attempted_tools=frozenset({"get_emails_tool"}),
    )

    assert blockers == []


def test_a_plan_level_blocker_survives_when_nothing_ran():
    blockers = summarize_plan_blockers(
        _result(_issue(code=ToolErrorCode.FORBIDDEN, tool_name=None)),
        attempted_tools=frozenset(),
    )

    assert [b.tool_name for b in blockers] == [None]


def test_the_default_reports_every_blocker():
    """Callers with no execution knowledge keep the pre-existing behaviour."""
    blockers = summarize_plan_blockers(_result(_issue(tool_name="get_events_tool")))

    assert [b.tool_name for b in blockers] == ["get_events_tool"]


def test_non_tool_steps_are_ignored_when_listing_what_ran():
    """A CONDITIONAL step names no capability — it cannot unblock one."""
    plan = ExecutionPlan(
        plan_id="p1",
        user_id="u1",
        session_id="s1",
        steps=[
            ExecutionStep(
                step_id="step_1",
                step_type=StepType.CONDITIONAL,
                condition="$steps.step_0.success",
                agent_name="emails_agent",
                tool_name="get_emails_tool",
                parameters={},
            )
        ],
    )

    assert attempted_tool_names(plan, {"step_1": {"condition_result": True}}) == frozenset()
