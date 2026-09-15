"""Characterization of the psyche prompt blocks BEFORE their wording left the code.

Prompt audit 2026-09-12 (lot B): ``engine.format_embodied_prompt_injection`` and the
legacy compact block of ``service.build_psyche_prompt_block`` assembled their sentences
from inline f-strings — prose in ``.py`` that no prompt guard could read. The wording
moved to ``psyche_embodied_lines.txt`` (one ``key|template`` per sentence) and
``psyche_legacy_compact_prompt.txt``; these goldens were captured on the inline
version so the move changes nothing the model reads.
"""

from __future__ import annotations

from src.domains.psyche.constants import (
    MOOD_BEHAVIORAL_DIRECTIVES,
    RELATIONSHIP_STAGE_DIRECTIVES,
)
from src.domains.psyche.engine import ExpressionProfile, PsycheEngine
from src.domains.psyche.service import render_legacy_compact_block

LF = chr(10)

FAINT = ExpressionProfile(mood_label="calm", mood_intensity="slightly", pad_magnitude=0.05)
FULL = ExpressionProfile(
    mood_label="cheerful",
    mood_intensity="noticeably",
    active_emotions=[("joy", 0.7)],
    relationship_stage="FRIENDSHIP",
    drive_curiosity=0.9,
    drive_engagement=0.8,
    confidence_weaknesses=["calendar"],
    previous_mood="neutral",
    previous_emotion="calm",
    pad_magnitude=0.8,
    current_pad=(0.6, 0.4, 0.3),
    previous_pad=(0.0, 0.0, 0.0),
    gap_hours=2.0,
)
FULL_NO_EXTRAS = ExpressionProfile(
    mood_label="cheerful", mood_intensity="strongly", pad_magnitude=0.8, current_pad=(0.6, 0.4, 0.3)
)


class TestEmbodiedGolden:
    def test_faint(self) -> None:
        dynamic, frame = PsycheEngine.format_embodied_prompt_injection(FAINT)
        assert frame == "psyche_embodied_faint"
        assert dynamic == (
            "BASE: Respond with calm equilibrium. Steady rhythm, no extremes."
            + LF
            + "A faint calm undercurrent colours your voice — Even, plain tone. "
        )

    def test_full_with_every_optional_line(self) -> None:
        dynamic, frame = PsycheEngine.format_embodied_prompt_injection(FULL)
        assert frame == "psyche_embodied_frame"
        assert dynamic == (
            "You are the assistant described in <Personality>. Right now, inside, you are "
            "noticeably cheerful — joy colours this moment. This is NOT a label to note; it IS "
            "your voice this turn. Speak FROM it."
            + LF
            + "How it sounds: Even, plain tone."
            + LF
            + "Let joy genuinely lead: Warmer word choices. Brighter energy. Genuine but not "
            "forced positivity."
            + LF
            + "RELATIONSHIP (FRIENDSHIP): Be polite and professional."
            + LF
            + "You're curious right now — explore an angle, ask. You're engaged — go a little "
            "further than strictly asked."
            + LF
            + "Less sure of calendar here — hedge a little and offer to double-check."
            + LF
            + "EVOLUTION: calm has given way to joy. Let the transition show — don't jump, but "
            "don't linger on what was."
            + LF
            + "Lean in — it should be unmistakable in how you speak."
            + LF
        )

    def test_full_without_optional_lines(self) -> None:
        dynamic, frame = PsycheEngine.format_embodied_prompt_injection(FULL_NO_EXTRAS)
        assert frame == "psyche_embodied_frame"
        assert dynamic == (
            "BASE: Respond with calm equilibrium. Steady rhythm, no extremes."
            + LF
            + "You are the assistant described in <Personality>. Right now, inside, you are "
            "strongly cheerful. This is NOT a label to note; it IS your voice this turn. Speak "
            "FROM it."
            + LF
            + "How it sounds: Even, plain tone."
            + LF
            + "RELATIONSHIP (ORIENTATION): Be polite and professional. Don't assume familiarity. "
            "Formal suggestions, clear explanations." + LF + "Let it permeate every line." + LF
        )


class TestLegacyCompactGolden:
    def test_legacy_block_is_the_inline_wording(self) -> None:
        profile = FULL
        compact = PsycheEngine.format_prompt_injection(profile)
        rendered = render_legacy_compact_block(profile, compact)
        assert rendered == (
            "<PsycheContext>"
            + LF
            + compact
            + LF
            + "You have an inner life. Inhabit this state noticeably:"
            + LF
            + f"- MOOD (cheerful): {MOOD_BEHAVIORAL_DIRECTIVES.get('cheerful', '')}"
            + LF
            + f"- RELATIONSHIP (FRIENDSHIP): {RELATIONSHIP_STAGE_DIRECTIVES.get('FRIENDSHIP', '')}"
            + LF
            + "- EMOTIONS: let each named emotion color specific moments. Higher intensity = more "
            "visible in tone and word choice."
            + LF
            + "- NEVER say 'I feel X'. Express through word choice, rhythm, energy. Never guilt-trip "
            "or express disappointment about user behavior."
            + LF
            + "- NEVER attribute your emotions or mood to the user. These are YOUR internal states — "
            "express them through your own tone and style, never by describing the user's feelings "
            "or state of mind." + LF + "</PsycheContext>"
        )

    def test_intensity_hint_maps_the_three_levels(self) -> None:
        for intensity, hint in (
            ("strongly", "strongly"),
            ("noticeably", "noticeably"),
            ("slightly", "subtly"),
        ):
            profile = ExpressionProfile(mood_label="calm", mood_intensity=intensity)
            assert f"Inhabit this state {hint}:" in render_legacy_compact_block(profile, "c")
