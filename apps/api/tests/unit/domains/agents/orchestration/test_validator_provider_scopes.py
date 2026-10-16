"""The plan validator judges a step's OAuth scopes against the provider serving it (RC1.1).

Measured in production (2026-10-07): an Outlook account's every e-mail,
contacts and calendar step was judged UNAUTHORIZED — 16 times in 7 days —
because the catalogue's multi-provider tools declare their GOOGLE scopes. The
verdict then reached the answer as « this capability is not connected », about
a mailbox that had just answered the same turn.
"""

from __future__ import annotations

import pytest

from src.domains.agents.emails.get_emails_manifest import get_emails_catalogue_manifest
from src.domains.agents.orchestration.plan_schemas import ExecutionPlan, ExecutionStep, StepType
from src.domains.agents.orchestration.validator import PlanValidator, ValidationContext
from src.domains.agents.registry.agent_manifest_definitions import EMAIL_AGENT_MANIFEST
from src.domains.agents.registry.agent_registry import AgentRegistry
from src.domains.agents.tools.common import ToolErrorCode

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _tool_classes_loaded() -> None:
    from src.domains.agents.tools import tool_registry

    tool_registry.ensure_tools_loaded()


def _unauthorized(active_connector_types: frozenset[str] | None) -> list[str]:
    registry = AgentRegistry()
    registry.register_agent_manifest(EMAIL_AGENT_MANIFEST)
    registry.register_tool_manifest(get_emails_catalogue_manifest, override=True)
    plan = ExecutionPlan(
        plan_id="p",
        user_id="u",
        session_id="s",
        steps=[
            ExecutionStep(
                step_id="step_1",
                step_type=StepType.TOOL,
                agent_name="email_agent",
                tool_name="get_emails_tool",
                parameters={"query": "is:unread"},
            )
        ],
    )
    context = ValidationContext(
        user_id="u",
        session_id="s",
        available_scopes=[],
        active_connector_types=active_connector_types,
    )

    result = PlanValidator(registry).validate_execution_plan(plan, context)

    return [str(e.tool_name) for e in result.errors if e.code == ToolErrorCode.UNAUTHORIZED]


@pytest.mark.parametrize("provider", ["microsoft_outlook", "apple_email"])
def test_a_mailbox_on_another_provider_is_not_judged_unauthorized(provider: str) -> None:
    assert _unauthorized(frozenset({provider})) == []


def test_an_account_with_no_mailbox_is_still_told_to_connect_one() -> None:
    assert _unauthorized(frozenset()) == ["get_emails_tool"]


def test_a_gmail_account_lacking_the_scope_is_still_judged() -> None:
    assert _unauthorized(frozenset({"google_gmail"})) == ["get_emails_tool"]


@pytest.mark.parametrize("other", ["microsoft_outlook", "apple_email"])
def test_a_dual_active_account_cannot_skip_the_gmail_scope_check(other: str) -> None:
    assert _unauthorized(frozenset({"google_gmail", other})) == ["get_emails_tool"]
