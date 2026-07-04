"""Unit tests for the planner skill_name coherence lock (audit D2).

The planner LLM may emit a plausible-but-wrong ``skill_name`` (observed:
``interactive-map`` for a "draw me a diagram" request whose steps targeted the
Excalidraw MCP). ``_resolve_plan_skill_name`` drops any value that contradicts
the authoritative QueryAnalyzer detection or the skill catalog, so the response
node never activates a skill unrelated to the request.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.domains.agents.services.smart_planner_service import SmartPlannerService


@pytest.mark.unit
class TestResolvePlanSkillName:
    @pytest.fixture
    def planner(self) -> SmartPlannerService:
        return SmartPlannerService()

    @staticmethod
    def _intel(detected: str | None) -> SimpleNamespace:
        # _resolve_plan_skill_name only reads .detected_skill_name
        return SimpleNamespace(detected_skill_name=detected)

    @staticmethod
    def _config() -> dict:
        return {"configurable": {"user_id": "user-1"}}

    def test_none_skill_name_returns_none(self, planner):
        assert (
            planner._resolve_plan_skill_name(None, self._intel("interactive-map"), self._config())
            is None
        )

    def test_matching_detection_is_kept(self, planner):
        assert (
            planner._resolve_plan_skill_name(
                "interactive-map", self._intel("interactive-map"), self._config()
            )
            == "interactive-map"
        )

    def test_mismatch_with_detection_is_dropped(self, planner):
        """The exact incident: LLM said interactive-map, analyzer detected mcp_excalidraw."""
        result = planner._resolve_plan_skill_name(
            "interactive-map", self._intel("mcp_excalidraw"), self._config()
        )
        assert result is None

    def test_unknown_skill_when_no_detection_is_dropped(self, planner):
        with (
            patch("src.domains.skills.cache.SkillsCache.get_by_name_for_user", return_value=None),
            patch("src.domains.skills.cache.SkillsCache.get_by_name", return_value=None),
        ):
            result = planner._resolve_plan_skill_name(
                "made-up-skill", self._intel(None), self._config()
            )
        assert result is None

    def test_known_skill_when_no_detection_is_kept(self, planner):
        with (
            patch(
                "src.domains.skills.cache.SkillsCache.get_by_name_for_user",
                return_value=None,
            ),
            patch(
                "src.domains.skills.cache.SkillsCache.get_by_name",
                return_value={"name": "interactive-map", "scripts": ["render_map.py"]},
            ),
        ):
            result = planner._resolve_plan_skill_name(
                "interactive-map", self._intel(None), self._config()
            )
        assert result == "interactive-map"

    def test_user_scoped_skill_when_no_detection_is_kept(self, planner):
        with patch(
            "src.domains.skills.cache.SkillsCache.get_by_name_for_user",
            return_value={"name": "my-user-skill", "scripts": []},
        ):
            result = planner._resolve_plan_skill_name(
                "my-user-skill", self._intel(None), self._config()
            )
        assert result == "my-user-skill"
