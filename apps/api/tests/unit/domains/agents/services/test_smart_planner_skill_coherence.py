"""Unit tests for the planner skill_name coherence lock (audit D2).

The planner LLM may emit a plausible-but-wrong ``skill_name`` (observed:
``interactive-map`` for a "draw me a diagram" request whose steps targeted the
Excalidraw MCP). ``resolve_plan_skill_name`` drops any value that contradicts
the authoritative QueryAnalyzer detection or the skill catalog, so the response
node never activates a skill unrelated to the request.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.domains.agents.services.planner.plan_skill import resolve_plan_skill_name


@pytest.mark.unit
class TestResolvePlanSkillName:
    @staticmethod
    def _intel(detected: str | None, domains: tuple[str, ...] = ()) -> SimpleNamespace:
        # _resolve_plan_skill_name reads .detected_skill_name and .domains
        return SimpleNamespace(detected_skill_name=detected, domains=list(domains))

    def test_none_skill_name_returns_none(self):
        assert resolve_plan_skill_name(None, self._intel("interactive-map")) is None

    def test_matching_detection_is_kept(self):
        assert (
            resolve_plan_skill_name("interactive-map", self._intel("interactive-map"))
            == "interactive-map"
        )

    def test_mismatch_with_detection_is_dropped(self):
        """The exact incident: LLM said interactive-map, analyzer detected mcp_excalidraw."""
        result = resolve_plan_skill_name("interactive-map", self._intel("mcp_excalidraw"))
        assert result is None

    def test_unknown_skill_when_no_detection_is_dropped(self):
        with patch("src.domains.skills.cache.SkillsCache.get_by_name_for_user", return_value=None):
            result = resolve_plan_skill_name("made-up-skill", self._intel(None))
        assert result is None

    @pytest.mark.parametrize("primary", ["interactive_page", "mcp_excalidraw"])
    def test_a_domain_that_rules_a_skill_out_keeps_it_off_the_plan(self, primary):
        """Measured 2026-11-05: the plan wrote a page, then its tag ran a neighbouring skill."""
        with patch(
            "src.domains.skills.cache.SkillsCache.get_by_name_for_user",
            return_value={"name": "tic-tac-toe", "scripts": ["play.py"]},
        ):
            result = resolve_plan_skill_name("tic-tac-toe", self._intel(None, (primary,)))
        assert result is None

    def test_known_skill_when_no_detection_is_kept(self):
        with patch(
            "src.domains.skills.cache.SkillsCache.get_by_name_for_user",
            return_value={"name": "interactive-map", "scripts": ["render_map.py"]},
        ):
            result = resolve_plan_skill_name("interactive-map", self._intel(None))
        assert result == "interactive-map"

    def test_user_scoped_skill_when_no_detection_is_kept(self):
        with patch(
            "src.domains.skills.cache.SkillsCache.get_by_name_for_user",
            return_value={"name": "my-user-skill", "scripts": []},
        ):
            result = resolve_plan_skill_name("my-user-skill", self._intel(None))
        assert result == "my-user-skill"
