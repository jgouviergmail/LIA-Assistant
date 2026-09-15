"""The delegation section tells the planner what the executor actually does.

Prompt audit 2026-09-12 (A.4): the section was 3 038 characters of inline prose in
``smart_planner_service.py`` and three of its facts were false — « a bounded 2-pass
LLM call » (a ReAct loop of up to ``subagent_default_max_iterations``), « 4 research
tools (…Wikipedia…) » (a settings-driven whitelist of three, without Wikipedia),
« Set timeout_seconds: 120 » (the executor floors it at ``subagent_tool_timeout_seconds``)
— and it handed the model the NAME of an environment variable where a number was
meant. It also contradicted the tool's own manifest on whether user data may be
referenced through ``$steps``. Now: one versioned file, every number read from
settings, and the manifest agrees.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.core.config import get_settings
from src.domains.agents.services.smart_planner_service import (
    SmartPlannerService,
    exclude_sub_agents_from_prompt,
)
from src.domains.agents.sub_agents.catalogue_manifests import (
    delegate_to_sub_agent_catalogue_manifest,
)


def _settings_with(enabled: bool) -> MagicMock:
    """The real settings, with the feature switch forced (get_settings builds a fresh one)."""
    real = get_settings()
    fake = MagicMock(wraps=real)
    fake.sub_agents_enabled = enabled
    for name in (
        "subagent_default_max_iterations",
        "subagent_instruction_max_tokens_resolved",
        "subagent_tool_timeout_seconds",
        "subagent_research_tools_whitelist_parsed",
    ):
        setattr(fake, name, getattr(real, name))
    return fake


@pytest.fixture
def section() -> str:
    with patch("src.core.config.get_settings", return_value=_settings_with(True)):
        return SmartPlannerService._build_sub_agents_section()


class TestEveryNumberIsTheSetting:
    def test_iterations_tools_cap_and_floor_come_from_settings(self, section: str) -> None:
        settings = get_settings()
        assert f"at most {settings.subagent_default_max_iterations} model calls" in section
        assert f"capped at {settings.subagent_instruction_max_tokens_resolved} tokens" in section
        assert f"at least {int(settings.subagent_tool_timeout_seconds)} s" in section
        for tool_name in settings.subagent_research_tools_whitelist_parsed:
            assert tool_name in section

    def test_no_stale_claim_survives(self, section: str) -> None:
        assert "2-pass" not in section
        assert "timeout_seconds: 120" not in section
        assert "SUBAGENT_INSTRUCTION_MAX_TOKENS_RESOLVED" not in section
        if "wikipedia" not in ",".join(get_settings().subagent_research_tools_whitelist_parsed):
            assert "Wikipedia" not in section

    def test_no_unfilled_placeholder(self, section: str) -> None:
        import re

        assert not re.findall(r"(?<!\{)\{[a-zA-Z_]+\}(?!\})", section)


class TestGating:
    def test_empty_when_sub_agents_are_disabled(self) -> None:
        with patch("src.core.config.get_settings", return_value=_settings_with(False)):
            assert SmartPlannerService._build_sub_agents_section() == ""

    def test_empty_when_the_user_rejected_a_delegation(self) -> None:
        token = exclude_sub_agents_from_prompt.set(True)
        try:
            with patch("src.core.config.get_settings", return_value=_settings_with(True)):
                assert SmartPlannerService._build_sub_agents_section() == ""
        finally:
            exclude_sub_agents_from_prompt.reset(token)


class TestManifestAgreesWithTheSection:
    def _instruction_description(self) -> str:
        parameter = next(
            p
            for p in delegate_to_sub_agent_catalogue_manifest.parameters
            if p.name == "instruction"
        )
        return parameter.description

    def test_user_data_travels_through_step_references(self) -> None:
        description = self._instruction_description()
        assert "$steps.step_N" in description
        assert "Never reference raw tool outputs" not in description
        assert "DO NOT paste raw data" not in description

    def test_the_cap_has_one_authority(self) -> None:
        """The number lives in the delegation section (settings); the manifest points at it."""
        description = self._instruction_description()
        assert "3000" not in description and "10000" not in description
        assert "SUBAGENT_INSTRUCTION_MAX_TOKENS_RESOLVED" not in description
