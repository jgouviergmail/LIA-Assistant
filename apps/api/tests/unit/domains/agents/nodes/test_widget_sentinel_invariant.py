"""Sentinels are host-owned — the invariant `_render_response_html` must hold.

Production evidence (2026-07-21): message ``28eaa427`` carried
``skill_app_545e26`` TWICE — once written by the response LLM inside its own
``lia-response`` wrapper, once appended deterministically — and the frontend
really mounted two iframes. Two later answers carried a LONE sentinel the
backend never injected, pointing at a registry id from an earlier turn: a
phantom widget, alive by accident while the client registry still held the id,
dead on reload.

The invariant asserted here covers both: for a registry holding N interactive
widgets, the final content carries exactly N sentinels, one per registry id —
regardless of what the model wrote.
"""

from __future__ import annotations

from typing import Any

from src.core.field_names import FIELD_REGISTRY_ID
from src.domains.agents.display.sentinel_filter import count_widget_sentinels
from src.domains.agents.nodes.response_node import _render_response_html

_LLM_SENTINEL = (
    '<div class="lia-skill-app" data-registry-id="{rid}">'
    '<div class="lia-skill-app__placeholder">'
    '<span class="lia-badge lia-badge--accent">Map</span>'
    '<div class="lia-skill-app__loading">Chargement de la carte…</div>'
    "</div></div>"
)


def _skill_app_item(registry_id: str, skill_name: str = "interactive-map") -> dict[str, Any]:
    return {
        "id": registry_id,
        "type": "SKILL_APP",
        "payload": {
            # `_registry_id` is the field the sentinel renderer reads — the
            # exact key `build_skill_app_output` writes (output_builder.py).
            FIELD_REGISTRY_ID: registry_id,
            "skill_name": skill_name,
            "title": f"Map: {registry_id}",
            "frame_url": "https://www.google.com/maps/embed?pb=x",
            "is_system_skill": True,
        },
        "meta": {"source": "skill", "timestamp": "2026-07-21T09:13:00Z"},
    }


def _render(content: str, registry: dict[str, Any]) -> str:
    return _render_response_html(
        final_content=content,
        current_turn_registry=registry,
        resolved_context_for_html=None,
        user_display_mode="html",
        user_viewport="desktop",
        user_language="fr",
        user_timezone="Europe/Paris",
        run_id="test-run",
    )


class TestSentinelInvariant:
    def test_llm_copy_is_replaced_not_duplicated(self) -> None:
        """The exact production shape: the model wrote the sentinel itself."""
        registry = {"skill_app_545e26": _skill_app_item("skill_app_545e26")}
        content = (
            '<div class="lia-response"><p>Voilà.</p>'
            + _LLM_SENTINEL.format(rid="skill_app_545e26")
            + "</div>"
        )

        out = _render(content, registry)

        assert count_widget_sentinels(out) == 1
        assert out.count('data-registry-id="skill_app_545e26"') == 1
        assert "<p>Voilà.</p>" in out

    def test_phantom_sentinel_with_a_stale_id_is_removed(self) -> None:
        """A sentinel pointing at a registry id that is NOT in this turn renders
        an error box on reload — the model must not be able to create one."""
        content = (
            '<div class="lia-response"><p>Je n\'ai pas ta position.</p>'
            + _LLM_SENTINEL.format(rid="skill_app_from_a_previous_turn")
            + "</div>"
        )

        out = _render(content, {})

        assert count_widget_sentinels(out) == 0
        assert "skill_app_from_a_previous_turn" not in out
        assert "<p>Je n'ai pas ta position.</p>" in out

    def test_one_sentinel_per_registry_widget(self) -> None:
        registry = {
            "skill_app_a": _skill_app_item("skill_app_a"),
            "skill_app_b": _skill_app_item("skill_app_b", skill_name="tic-tac-toe"),
        }

        out = _render("<p>deux widgets</p>", registry)

        assert count_widget_sentinels(out) == 2
        assert out.count('data-registry-id="skill_app_a"') == 1
        assert out.count('data-registry-id="skill_app_b"') == 1

    def test_no_widget_no_sentinel(self) -> None:
        out = _render("<p>simple réponse</p>", {})
        assert count_widget_sentinels(out) == 0

    def test_non_widget_registry_items_never_produce_a_sentinel(self) -> None:
        """Data cards are a different path (cards mode); in html mode they are
        neither injected nor allowed to leak a sentinel."""
        registry = {
            "weather_1": {
                "id": "weather_1",
                "type": "WEATHER",
                "payload": {"city": "Paris"},
                "meta": {"source": "tool", "timestamp": "2026-07-21T09:13:00Z"},
            }
        }
        out = _render("<p>météo</p>", registry)
        assert count_widget_sentinels(out) == 0
