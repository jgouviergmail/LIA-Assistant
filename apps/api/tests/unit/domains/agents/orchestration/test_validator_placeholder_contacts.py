"""Placeholder-contact guard — fabricated emails are rejected before the LLM.

Prod 2026-07-17: the planner filled ``attendees=['jane.doe@example.com']``
for a real contact instead of resolving or omitting. RFC 2606 reserved domains
in a non-free-text MUTATION parameter are always an hallucination: the
deterministic pre-LLM check rejects the plan with replanning feedback. Reads
and free-text fields (a body quoting example.com) are exempt.
"""

from __future__ import annotations

import pytest

from src.domains.agents.orchestration.plan_schemas import (
    ExecutionPlan,
    ExecutionStep,
    StepType,
)
from src.domains.agents.orchestration.semantic_validator import (
    PlanSemanticValidator,
    SemanticIssueType,
    detect_placeholder_contacts,
)

pytestmark = pytest.mark.unit


def _step(tool_name: str, parameters: dict, step_id: str = "step_1") -> ExecutionStep:
    return ExecutionStep(
        step_id=step_id,
        step_type=StepType.TOOL,
        agent_name="event_agent",
        tool_name=tool_name,
        parameters=parameters,
    )


def _plan(*steps: ExecutionStep) -> ExecutionPlan:
    return ExecutionPlan(plan_id="p", user_id="u", session_id="s", steps=list(steps))


def test_detects_placeholder_email_in_mutation_list_param() -> None:
    plan = _plan(
        _step(
            "create_event_tool",
            {
                "summary": "Petit-déjeuner",
                "start_datetime": "2026-07-18T09:30:00",
                "attendees": ["jane.doe@example.com"],
            },
        )
    )
    findings = detect_placeholder_contacts(plan)
    assert findings == ["step_1.attendees='jane.doe@example.com'"]


@pytest.mark.parametrize(
    "email",
    ["a@example.org", "b@mail.example.net", "c@foo.invalid", "d@bar.test"],
)
def test_detects_every_rfc2606_reserved_domain(email: str) -> None:
    plan = _plan(_step("send_email_tool", {"to": email, "body": "hello"}))
    assert detect_placeholder_contacts(plan)


def test_read_only_steps_are_exempt() -> None:
    plan = _plan(_step("get_emails_tool", {"query": "from test@example.com"}))
    assert detect_placeholder_contacts(plan) == []


def test_free_text_params_are_exempt() -> None:
    """A dictated body may legitimately QUOTE a placeholder address."""
    plan = _plan(
        _step(
            "send_email_tool",
            {"to": "marie@gmail.com", "body": "use demo@example.com for the sandbox"},
        )
    )
    assert detect_placeholder_contacts(plan) == []


def test_real_emails_pass() -> None:
    plan = _plan(
        _step(
            "create_event_tool",
            {
                "summary": "Petit-déjeuner",
                "start_datetime": "2026-07-18T09:30:00",
                "attendees": ["alex.martin@gmail.com"],
            },
        )
    )
    assert detect_placeholder_contacts(plan) == []


@pytest.mark.parametrize(
    "email",
    ["a@test.com", "b@invalid-corp.fr", "c@example-industries.com", "d@testard.io"],
)
def test_lookalike_real_domains_never_false_positive(email: str) -> None:
    """test.com / invalid-* / example-* are REAL registrable domains — the
    reserved TLDs only match as the final dotted label."""
    plan = _plan(_step("send_email_tool", {"to": email, "body": "x"}))
    assert detect_placeholder_contacts(plan) == []


async def test_validate_rejects_placeholder_deterministically() -> None:
    """Integration through validate(): rejected BEFORE any LLM call, with the
    resolve-or-omit feedback the replanner needs."""
    plan = _plan(
        _step(
            "create_event_tool",
            {
                "summary": "Petit-déjeuner avec Paul Lemoine",
                "start_datetime": "2026-07-18T09:30:00",
                "end_datetime": "2026-07-18T10:30:00",
                "timezone": "Europe/Paris",
                "attendees": ["jane.doe@example.com"],
            },
        )
    )
    result = await PlanSemanticValidator().validate(
        plan, "crée le rdv petit déjeuner avec Jérôme", user_language="fr"
    )
    assert result.is_valid is False
    assert result.confidence == 1.0  # programmatic detection
    assert result.issues[0].issue_type == SemanticIssueType.WRONG_PARAMETERS
    assert "get_contacts_tool" in (result.issues[0].suggested_fix or "")
