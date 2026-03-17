"""Unit tests for build_skills_catalog with active_skills (positive set) filtering."""

from unittest.mock import patch

from src.domains.skills.injection import build_skills_catalog


def _make_skill(name: str, scope: str = "admin", **kwargs) -> dict:
    """Build a minimal cache skill dict."""
    return {
        "name": name,
        "scope": scope,
        "description": f"Desc for {name}",
        "priority": kwargs.get("priority", 50),
        "disable_model_invocation": kwargs.get("disable_model_invocation", False),
        "source_path": f"/fake/{name}/SKILL.md",
        **kwargs,
    }


class TestBuildSkillsCatalog:
    """Tests for build_skills_catalog with active_skills parameter."""

    @patch("src.domains.skills.cache.SkillsCache.get_for_user")
    def test_active_skills_none_returns_all(self, mock_cache):
        """When active_skills is None, all non-disabled skills are included."""
        mock_cache.return_value = [
            _make_skill("skill-a"),
            _make_skill("skill-b"),
        ]
        result = build_skills_catalog("user-1", active_skills=None)
        assert "skill-a" in result
        assert "skill-b" in result

    @patch("src.domains.skills.cache.SkillsCache.get_for_user")
    def test_active_skills_filters_by_inclusion(self, mock_cache):
        """Only skills in active_skills set are included."""
        mock_cache.return_value = [
            _make_skill("skill-a"),
            _make_skill("skill-b"),
            _make_skill("skill-c"),
        ]
        result = build_skills_catalog("user-1", active_skills={"skill-a", "skill-c"})
        assert "skill-a" in result
        assert "skill-b" not in result
        assert "skill-c" in result

    @patch("src.domains.skills.cache.SkillsCache.get_for_user")
    def test_empty_active_skills_returns_empty(self, mock_cache):
        """Empty active_skills set means no skills are active."""
        mock_cache.return_value = [
            _make_skill("skill-a"),
        ]
        result = build_skills_catalog("user-1", active_skills=set())
        assert result == ""

    @patch("src.domains.skills.cache.SkillsCache.get_for_user")
    def test_disable_model_invocation_filtered(self, mock_cache):
        """Skills with disable_model_invocation are always hidden."""
        mock_cache.return_value = [
            _make_skill("hidden", disable_model_invocation=True),
            _make_skill("visible"),
        ]
        result = build_skills_catalog("user-1", active_skills={"hidden", "visible"})
        assert "hidden" not in result
        assert "visible" in result

    @patch("src.domains.skills.cache.SkillsCache.get_for_user")
    def test_no_skills_returns_empty_string(self, mock_cache):
        """No skills → empty string (zero token overhead)."""
        mock_cache.return_value = []
        result = build_skills_catalog("user-1", active_skills={"any"})
        assert result == ""
