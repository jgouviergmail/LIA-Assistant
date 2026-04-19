"""Unit tests for SkillAppSentinel.

Ensures the rendered HTML carries the data-registry-id attribute and the
expected class so the frontend MarkdownContent.tsx can detect it and
mount the SkillAppWidget React component.
"""

from __future__ import annotations

from src.core.field_names import FIELD_REGISTRY_ID
from src.domains.agents.display.components.base import RenderContext
from src.domains.agents.display.components.skill_app_sentinel import SkillAppSentinel


def _ctx(language: str = "en") -> RenderContext:
    return RenderContext(language=language, timezone="UTC")


class TestSkillAppSentinel:
    def test_includes_class_attribute(self) -> None:
        html = SkillAppSentinel().render(
            data={FIELD_REGISTRY_ID: "skill_app_test", "skill_name": "demo", "title": "Demo"},
            ctx=_ctx(),
        )
        assert 'class="lia-skill-app"' in html

    def test_includes_registry_id_attribute(self) -> None:
        html = SkillAppSentinel().render(
            data={FIELD_REGISTRY_ID: "skill_app_abc123", "skill_name": "demo"},
            ctx=_ctx(),
        )
        assert 'data-registry-id="skill_app_abc123"' in html

    def test_escapes_registry_id(self) -> None:
        """Defense in depth — registry ids should never contain HTML but escape anyway."""
        html = SkillAppSentinel().render(
            data={FIELD_REGISTRY_ID: "<script>alert(1)</script>", "skill_name": "x"},
            ctx=_ctx(),
        )
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html

    def test_escapes_skill_name(self) -> None:
        html = SkillAppSentinel().render(
            data={FIELD_REGISTRY_ID: "rid", "skill_name": "<img src=x>", "title": "<img src=x>"},
            ctx=_ctx(),
        )
        assert "<img src=x>" not in html

    def test_loading_text_language(self) -> None:
        fr_html = SkillAppSentinel().render(
            data={FIELD_REGISTRY_ID: "rid", "skill_name": "x"},
            ctx=_ctx("fr"),
        )
        en_html = SkillAppSentinel().render(
            data={FIELD_REGISTRY_ID: "rid", "skill_name": "x"},
            ctx=_ctx("en"),
        )
        # Different languages must produce different loading text
        assert fr_html != en_html

    def test_fallback_title_to_skill_name(self) -> None:
        html = SkillAppSentinel().render(
            data={FIELD_REGISTRY_ID: "rid", "skill_name": "my-skill"},
            ctx=_ctx(),
        )
        assert "my-skill" in html
