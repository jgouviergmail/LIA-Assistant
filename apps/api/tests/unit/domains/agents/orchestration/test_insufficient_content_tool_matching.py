"""A tool is matched by its NAME, never by a fragment of it.

``detect_insufficient_content`` used to read its tool table as substrings:
« send_email » is a fragment of ``send_email_to_me_tool``, a tool whose
recipient is never a parameter (ADR-314), so in pipeline mode « e-mail me the
weather » was answered « Who would you like to send this email to? » even with
a subject and a body. Proven on the real function, 2026-10-13.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from src.domains.agents.orchestration.plan_schemas import (
    ExecutionPlan,
    ExecutionStep,
    StepType,
)
from src.domains.agents.orchestration.semantic_validator import detect_insufficient_content
from src.domains.agents.registry.agent_registry import AgentRegistry

pytestmark = pytest.mark.unit


def _plan(tool_name: str, parameters: dict[str, Any]) -> ExecutionPlan:
    step = ExecutionStep(
        step_id="step_1",
        step_type=StepType.TOOL,
        agent_name="email_agent",
        tool_name=tool_name,
        parameters=parameters,
    )
    return ExecutionPlan(user_id="test-user", steps=[step])


class TestToolsAreMatchedByTheirExactName:
    def test_a_self_send_with_subject_and_body_is_not_asked_for_a_recipient(self) -> None:
        plan = _plan("send_email_to_me_tool", {"subject": "Weather", "body": "Sunny, 21 degrees"})

        assert detect_insufficient_content(plan, "send me the weather by email", "fr") is None

    def test_a_self_send_with_an_instruction_is_not_asked_anything(self) -> None:
        plan = _plan("send_email_to_me_tool", {"content_instruction": "today's forecast"})

        assert detect_insufficient_content(plan, "email me today's forecast", "fr") is None

    def test_the_send_tool_still_asks_for_its_missing_recipient(self) -> None:
        plan = _plan("send_email_tool", {"subject": "Hello", "body": "See you tomorrow"})

        result = detect_insufficient_content(plan, "send an email", "fr")

        assert result is not None
        assert result.requires_clarification is True
        assert result.clarification_field == "recipient"

    def test_the_reply_tool_still_asks_for_its_missing_body(self) -> None:
        plan = _plan("reply_email_tool", {"message_id": "m-1"})

        result = detect_insufficient_content(plan, "reply", "fr")

        assert result is not None
        assert result.clarification_field == "body"

    def test_a_tool_name_is_read_case_insensitively(self) -> None:
        plan = _plan("Send_Email_Tool", {"subject": "Hello", "body": "See you"})

        result = detect_insufficient_content(plan, "send an email", "fr")

        assert result is not None
        assert result.clarification_field == "recipient"


@pytest.fixture
def _loaded_catalogue() -> Iterator[AgentRegistry]:
    """The real catalogue, so the guard below cannot pass on an empty registry."""
    from src.domains.agents.registry import reset_global_registry, set_global_registry
    from src.domains.agents.registry.catalogue_loader import initialize_catalogue
    from src.domains.agents.tools import tool_registry

    tool_registry.ensure_tools_loaded()
    registry = AgentRegistry()
    initialize_catalogue(registry)
    set_global_registry(registry)
    try:
        yield registry
    finally:
        reset_global_registry()


def test_every_tool_the_table_names_is_a_catalogue_tool(_loaded_catalogue: AgentRegistry) -> None:
    """An entry naming no catalogue tool would guard nothing, silently."""
    from src.core.constants import INSUFFICIENT_CONTENT_TOOL_DOMAINS

    catalogue = {manifest.name for manifest in _loaded_catalogue.list_tool_manifests()}

    assert set(INSUFFICIENT_CONTENT_TOOL_DOMAINS) <= catalogue
