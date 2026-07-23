"""Skills API response builders (UXR Lot 8, A4) — the `dialogue` flag
(ADR-118) must reach the frontend slash-command registry through BOTH
serialization paths, defaulting to False when absent from the cache."""

from unittest.mock import patch

from src.domains.skills.router import _merge_with_cache, _skill_to_response


class TestDialogueExposure:
    def test_merge_with_cache_exposes_dialogue(self) -> None:
        cached = {"category": "info", "priority": 10, "dialogue": True}
        with patch("src.domains.skills.cache.SkillsCache.get_by_name", return_value=cached):
            out = _merge_with_cache(
                {"name": "quiz", "description": "d", "scope": "admin", "is_active": True}
            )
        assert out["dialogue"] is True

    def test_merge_with_cache_defaults_dialogue_false(self) -> None:
        with patch("src.domains.skills.cache.SkillsCache.get_by_name", return_value=None):
            out = _merge_with_cache({"name": "x", "description": "d", "scope": "admin"})
        assert out["dialogue"] is False

    def test_skill_to_response_exposes_dialogue(self) -> None:
        out = _skill_to_response({"name": "quiz", "description": "d", "dialogue": True}, "user")
        assert out["dialogue"] is True
        out2 = _skill_to_response({"name": "quiz", "description": "d"}, "user")
        assert out2["dialogue"] is False
