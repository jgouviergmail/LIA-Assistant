"""Unit tests for the notification body flattener.

Notification surfaces render their body verbatim — the service worker hands
``body`` straight to ``showNotification`` and the frontend toast renders the
description as escaped React children — while the agent pipeline produces rich
content. Without flattening, users read ``<div class="lia-response"><h2>`` on
their lock screen (observed 2026-07 on scheduled-action pushes).

The regression oracles below are the real observed payload shapes, not
synthetic ones.
"""

import pytest

from src.domains.agents.display.plain_text import looks_like_html, strip_html_if_markup
from src.infrastructure.proactive.notification import plain_text_for_notification


@pytest.mark.unit
class TestStripHtmlIfMarkup:
    def test_strips_lia_response_wrapper(self) -> None:
        out = strip_html_if_markup('<div class="lia-response"><h2>Titre</h2><p>Corps</p></div>')
        assert "<" not in out
        assert "Titre" in out and "Corps" in out

    def test_preserves_angle_bracket_prose(self) -> None:
        # The guard that justifies detection: blind stripping would delete
        # "< 5 and y >" from this sentence.
        text = "x < 5 and y > 3 donc c'est bon"
        assert strip_html_if_markup(text) == text

    def test_preserves_markdown(self) -> None:
        text = "**Salut** ! Voici # un titre et - une liste"
        assert strip_html_if_markup(text) == text

    def test_empty_is_noop(self) -> None:
        assert strip_html_if_markup("") == ""

    def test_detection_ignores_class_name_in_prose(self) -> None:
        assert looks_like_html("The lia-response layout improved a lot") is False

    @pytest.mark.parametrize(
        "prose",
        [
            "if x<a and b>c: return True",
            "vérifie que count<b et total>i",
            "vector<i> v; map<p,tr> m;",
            "x < 5 and y > 3",
            "the lia-response system keeps x < 5 and y > 3 readable",
        ],
    )
    def test_unpaired_angle_brackets_are_not_markup(self, prose: str) -> None:
        """A lone ``<tag`` is not HTML — single-letter names collide with prose.

        Detecting these mutilated the text: "if x<a and b>c" became "if xc",
        "count<b et total>i" became "counti". Content destroyed, silently.
        """
        assert looks_like_html(prose) is False
        assert strip_html_if_markup(prose) == prose

    @pytest.mark.parametrize(
        "markup",
        [
            '<div class="lia-response"><p>Salut</p></div>',
            "<p>hello</p>",
            "<style>.x{color:red}</style>Hello",
            "ligne1<br>ligne2",  # void element: never closes
            '<div class="lia-card-top"><h3>Titre</h3></div>',
            '<div class="lia-response"><p>document tronqué',  # attribute signal
        ],
    )
    def test_real_markup_is_still_detected(self, markup: str) -> None:
        assert looks_like_html(markup) is True

    def test_detection_scales_linearly(self) -> None:
        """Rules out the backreference form, super-linear on unclosed tags."""
        import time

        payload = "<p>" * 16000 + "x"
        start = time.perf_counter()
        looks_like_html(payload)
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 250, f"detection over 48 KB took {elapsed_ms:.0f} ms"


@pytest.mark.unit
class TestPlainTextForNotification:
    def test_flattens_observed_regression_payload(self) -> None:
        """The exact shape that leaked to the lock screen (2026-07)."""
        raw = (
            '<div class="lia-response">\n'
            "<h2>Technologies 2026 : le monde tourne encore sans IA</h2>\n"
            "<p>On respire un peu.</p>\n"
            "</div>"
        )
        out = plain_text_for_notification(raw)

        assert "<" not in out and ">" not in out
        assert "lia-response" not in out
        assert out.startswith("Technologies 2026")
        assert "On respire un peu." in out

    def test_collapses_to_a_single_line(self) -> None:
        # A notification body is one line: the HTML stripper turns block
        # elements into newlines, which must not survive.
        out = plain_text_for_notification("<p>Un</p><p>Deux</p><p>Trois</p>")
        assert "\n" not in out
        assert out == "Un Deux Trois"

    def test_flattens_markdown_links(self) -> None:
        out = plain_text_for_notification("Sources : [lemonde.fr](https://lemonde.fr/a)")
        assert out == "Sources : lemonde.fr (https://lemonde.fr/a)"

    def test_strips_style_block_content_entirely(self) -> None:
        out = plain_text_for_notification(
            '<div class="lia-response"><style>.x{color:red}</style><p>Bonjour</p></div>'
        )
        assert "color" not in out
        assert out == "Bonjour"

    # Notification bodies reach this flattener truncated to a preview budget, so
    # a block element routinely arrives severed with no closing tag. Requiring
    # the pair let tag-stripping remove the marker and leave the body as prose —
    # a lock-screen notification read "body{color:red;font-size:12px}".
    #
    # Mirrored by `notification-preview.test.ts` on the frontend half; the two
    # strippers must agree, a preview can be built on either side.
    @pytest.mark.parametrize(
        ("payload", "expected"),
        [
            ('<div class="lia-response"><style>body{color:red;font-size:12px}', ""),
            ('<div class="x"><script>var a=1;alert(9)', ""),
            ('<div class="x"><style>a{b:c}</style>Texte<script>var z=1', "Texte"),
            # `<script src="x"/>` has no body: without the (?<!/) guard the lazy
            # body would run to end-of-input and eat the rest of the document.
            ('<div class="x"><script src="a.js"/>Texte</div>', "Texte"),
            # A </script> must not close a <style> (\1 backreference).
            ('<div class="x"><style>x</script>y</style>Fin</div>', "Fin"),
            ("<html><head><title>T</title></head><body><p>Corps</p></body></html>", "Corps"),
        ],
    )
    def test_drops_block_elements_even_when_truncated(self, payload: str, expected: str) -> None:
        assert plain_text_for_notification(payload) == expected

    def test_markdown_content_is_untouched_apart_from_whitespace(self) -> None:
        # Interest/heartbeat bodies are Markdown; flattening must not mangle them.
        assert plain_text_for_notification("**Salut** ! Un fait surprenant.") == (
            "**Salut** ! Un fait surprenant."
        )

    def test_empty_is_noop(self) -> None:
        assert plain_text_for_notification("") == ""

    def test_reclaims_the_budget_wasted_by_the_wrapper(self) -> None:
        """The wrapper alone ate 26 of the 150-character push budget."""
        raw = '<div class="lia-response"><p>' + ("a" * 200) + "</p></div>"
        assert plain_text_for_notification(raw) == "a" * 200

    def test_flattens_the_mixed_cards_mode_payload(self) -> None:
        """``cards`` mode ships Markdown prose + server-rendered HTML cards.

        This shape only reaches a notification since the executor started
        consuming ``content_replacement``; it is the payload that exposed the
        Material Symbols leak below.
        """
        mixed = (
            "Voici tes 2 prochains rendez-vous.\n\n"
            '<div class="lia-card-top">'
            '<div class="lia-illus lia-illus--blue">'
            '<span class="material-symbols-outlined">event</span></div>'
            '<div class="lia-card-top__info"><h3>Déjeuner avec Marie</h3>'
            '<div class="lia-card-top__subtitle">12:30</div></div></div>'
        )
        out = plain_text_for_notification(mixed)

        assert out.startswith("Voici tes 2 prochains rendez-vous.")
        assert "Déjeuner avec Marie" in out and "12:30" in out
        assert "<" not in out

    def test_drops_material_symbols_ligature_names(self) -> None:
        """Icon span text is a font ligature, not prose.

        Regression: a card read "… event Déjeuner avec Marie" on the lock
        screen, and the TTS engine spoke "event" before the sentence.
        """
        for ligature in ("event", "mail", "star"):
            out = plain_text_for_notification(
                f'<span class="material-symbols-outlined">{ligature}</span><p>Bonjour</p>'
            )
            assert out == "Bonjour", f"ligature {ligature!r} leaked: {out!r}"

    def test_icon_span_stripping_tolerates_extra_classes(self) -> None:
        """``icon()`` nests the glyph inside a ``lia-icon`` wrapper span."""
        out = plain_text_for_notification(
            '<span class="lia-icon">'
            '<span class="material-symbols-outlined notranslate">mail</span>'
            "</span><p>3 messages</p>"
        )
        assert out == "3 messages"

    def test_the_word_event_survives_in_real_prose(self) -> None:
        """Only icon spans are dropped — never the same word in text."""
        out = plain_text_for_notification("<p>Un event important a lieu demain.</p>")
        assert out == "Un event important a lieu demain."

    def test_icon_span_stripping_accepts_either_quote_style(self) -> None:
        """The pattern must not miss an icon over a quoting detail."""
        out = plain_text_for_notification(
            "<span class='material-symbols-outlined'>event</span><p>Bonjour</p>"
        )
        assert out == "Bonjour"

    def test_unclosed_icon_span_does_not_swallow_neighbouring_prose(self) -> None:
        """``[^<]*`` (not ``.*?``) bounds the match to the span's own text.

        A greedy/dotall body could run past the missing ``</span>`` and delete
        the paragraph that follows. Losing the ligature name is acceptable here;
        losing the user's content is not.
        """
        out = plain_text_for_notification(
            '<span class="material-symbols-outlined">event<p>Message important</p>'
        )
        assert "Message important" in out

    def test_flattening_scales_linearly(self) -> None:
        """Guards the event loop: this runs synchronously on an async path.

        Asserts an upper bound generous enough not to flake on a loaded CI box,
        but tight enough to catch a genuinely super-linear pattern (the same
        input took >1 s when the cost was mis-measured during review).
        """
        import time

        payload = '<span class="material-symbols-outlined">' * 4000 + "x"
        plain_text_for_notification("<p>warm up the lazy html_to_text import</p>")

        start = time.perf_counter()
        plain_text_for_notification(payload)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 250, f"flattening 160 KB took {elapsed_ms:.0f} ms"
