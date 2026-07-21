"""Widget sentinels are host-owned — the stripper that enforces it.

The fixtures below are the EXACT production content that exposed the defect
(assistant message ``28eaa427``, run ``9fe3d6ba``, 2026-07-21): the same
``data-registry-id`` twice, once written by the LLM inside its own
``lia-response`` wrapper (paraphrased icon and loading label), once appended
deterministically by ``_render_response_html``.
"""

from __future__ import annotations

import pytest

from src.domains.agents.display.sentinel_filter import (
    count_widget_sentinels,
    strip_widget_sentinels,
)

# LLM-authored copy: note the `map` icon and "Chargement de la carte…" — the
# canonical renderer emits `psychology` and "Chargement du skill…".
LLM_SENTINEL = (
    '<div class="lia-skill-app" data-registry-id="skill_app_545e26">'
    '<div class="lia-skill-app__placeholder">'
    '<span class="lia-badge lia-badge--accent">'
    '<span class="lia-icon" aria-hidden="true">'
    '<span class="material-symbols-outlined">map</span></span> Map: 23 ter Bd</span>'
    '<div class="lia-skill-app__loading">Chargement de la carte…</div>'
    "</div></div>"
)
CANONICAL_SENTINEL = (
    '<div class="lia-skill-app" data-registry-id="skill_app_545e26">'
    '<div class="lia-skill-app__placeholder">'
    '<span class="lia-badge lia-badge--accent">Map: 23 ter Bd</span>'
    '<div class="lia-skill-app__loading">Chargement du skill…</div>'
    "</div></div>"
)
PROD_DUPLICATE = (
    '<div class="lia-response">\n\n<p>Voilà, tu es pile ici.</p>\n\n'
    f"{LLM_SENTINEL}\n\n<ul>\n<li>🌤️ <strong>Vent à 13 km/h</strong></li>\n</ul>\n\n"
    f"</div>\n\n{CANONICAL_SENTINEL}"
)


class TestStripWidgetSentinels:
    def test_removes_both_copies_of_the_production_duplicate(self) -> None:
        cleaned, removed = strip_widget_sentinels(PROD_DUPLICATE)
        assert removed == 2
        assert "lia-skill-app" not in cleaned
        # Everything else survives byte for byte — including the wrapper.
        assert "<p>Voilà, tu es pile ici.</p>" in cleaned
        assert "<strong>Vent à 13 km/h</strong>" in cleaned
        assert cleaned.startswith('<div class="lia-response">')
        assert cleaned.rstrip().endswith("</div>")

    def test_nested_divs_do_not_end_the_block_early(self) -> None:
        """A non-greedy regex would stop at the first `</div>` and leave orphans."""
        cleaned, removed = strip_widget_sentinels(f"before{LLM_SENTINEL}after")
        assert (cleaned, removed) == ("beforeafter", 1)

    def test_leaves_content_without_sentinels_untouched(self) -> None:
        html = '<div class="lia-response"><p>Just prose</p></div>'
        assert strip_widget_sentinels(html) == (html, 0)

    def test_does_not_match_sentinel_child_classes_as_sentinels(self) -> None:
        """`lia-skill-app__placeholder` merely CONTAINS the token — substring
        matching would excise unrelated markup."""
        html = '<div class="lia-skill-app__placeholder">kept</div>'
        assert strip_widget_sentinels(html) == (html, 0)

    def test_does_not_match_the_widget_wrapper_class(self) -> None:
        html = '<div class="lia-skill-app-widget">kept</div>'
        assert strip_widget_sentinels(html) == (html, 0)

    def test_matches_the_class_token_among_several(self) -> None:
        html = '<div class="foo lia-mcp-app bar" data-registry-id="mcp_app_1">x</div>'
        assert strip_widget_sentinels(html) == ("", 1)

    def test_removes_mcp_sentinels_too(self) -> None:
        html = (
            "<p>a</p>"
            '<div class="lia-mcp-app" data-registry-id="mcp_app_9d8d9d">'
            '<div class="lia-mcp-app__placeholder">…</div></div>'
            "<p>b</p>"
        )
        assert strip_widget_sentinels(html) == ("<p>a</p><p>b</p>", 1)

    def test_substitutes_the_replacement_marker(self) -> None:
        cleaned, removed = strip_widget_sentinels(f"x{LLM_SENTINEL}y", replacement="[widget]")
        assert (cleaned, removed) == ("x[widget]y", 1)

    def test_unclosed_sentinel_removes_only_the_opening_tag(self) -> None:
        """Truncation must not swallow the prose that follows."""
        html = '<p>keep</p><div class="lia-skill-app" data-registry-id="x">tail'
        cleaned, removed = strip_widget_sentinels(html)
        assert removed == 1
        assert cleaned == "<p>keep</p>tail"

    def test_self_closing_sentinel_removes_the_tag_alone(self) -> None:
        html = '<p>a</p><div class="lia-skill-app" data-registry-id="x"/><p>b</p>'
        cleaned, removed = strip_widget_sentinels(html)
        assert removed == 1
        assert "lia-skill-app" not in cleaned
        assert "<p>a</p>" in cleaned and "<p>b</p>" in cleaned

    def test_end_tag_with_whitespace_is_handled(self) -> None:
        html = '<div class="lia-mcp-app" data-registry-id="m">inner</div >tail'
        assert strip_widget_sentinels(html) == ("tail", 1)

    @pytest.mark.parametrize("content", ["", None])
    def test_empty_input_is_a_no_op(self, content: str | None) -> None:
        assert strip_widget_sentinels(content or "") == (content or "", 0)


class TestCountWidgetSentinels:
    def test_counts_without_mutating(self) -> None:
        assert count_widget_sentinels(PROD_DUPLICATE) == 2
        assert count_widget_sentinels("<p>none</p>") == 0
