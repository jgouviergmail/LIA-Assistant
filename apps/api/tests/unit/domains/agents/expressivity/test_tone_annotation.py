"""The per-turn tone annotation: vocabulary, parsing, and the per-run hand-off.

These tests exist because of a measurement. The avatar used to pick its
post-answer face from the psyche's dominant emotion; over fourteen consecutive
production turns that emotion was ``enthusiasm`` on thirteen of them, drifting
by 0.02, so every answer earned the same face. A psyche is a TRAIT and an argmax
over a near-constant vector is a constant.

What is guarded here is the replacement's contract, and every assertion below
maps to a way the tag could reach a user's screen or a face nobody designed.
"""

from __future__ import annotations

import pytest

from src.domains.agents.expressivity import (
    TONE_ACCENTS,
    TONE_REGISTERS,
    ToneAnnotation,
    normalize_accent,
    normalize_intensity,
    normalize_register,
    parse_tone_annotation,
    pop_tone_annotation,
    store_tone_annotation,
)
from src.domains.agents.expressivity.annotation import (
    TONE_TAG_MARKER,
    strip_tone_fragments,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------


class TestVocabulary:
    """The vocabulary is closed, and normalization is its only door."""

    @pytest.mark.parametrize("register", TONE_REGISTERS)
    def test_every_declared_register_normalizes_to_itself(self, register: str) -> None:
        assert normalize_register(register) == register

    def test_case_and_whitespace_are_forgiven(self) -> None:
        assert normalize_register("  WARM ") == "warm"
        assert normalize_accent(" Nod ") == "nod"

    def test_an_invented_register_yields_none_not_a_default(self) -> None:
        """A fallback here would render a face nobody designed.

        None is distinguishable from "the model chose the plainest register",
        which is what lets the caller drop the annotation instead of playing it.
        """
        assert normalize_register("smug") is None
        assert normalize_register("") is None
        assert normalize_register(None) is None

    def test_an_invented_accent_degrades_to_none_and_keeps_the_tone(self) -> None:
        """Losing a wink is not worth losing the register with it."""
        assert normalize_accent("shrug") == "none"
        assert normalize_accent(None) == "none"

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("0.5", 0.5), (0.5, 0.5), ("7", 1.0), (-3, 0.0), ("0", 0.0), (1, 1.0)],
    )
    def test_intensity_out_of_bounds_is_REPAIRED(self, raw: object, expected: float) -> None:
        """Clamp what is mechanically repairable; that is the house doctrine."""
        assert normalize_intensity(raw) == expected  # type: ignore[arg-type]

    @pytest.mark.parametrize("raw", ["", "loud", None, float("nan"), True])
    def test_a_non_numeric_intensity_is_not_repairable(self, raw: object) -> None:
        """Repairing this would mean inventing intent, so it is refused.

        ``True`` is in the list on purpose: Python would happily read it as
        1.0, and a model writing ``intensity="true"`` has not declared a dial.
        """
        assert normalize_intensity(raw) is None  # type: ignore[arg-type]

    def test_accents_and_registers_do_not_overlap(self) -> None:
        assert set(TONE_REGISTERS) & set(TONE_ACCENTS) == set()


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


class TestParsing:
    """Whatever happens, the tag never reaches the reader."""

    def test_a_well_formed_tag_is_read_and_removed(self) -> None:
        annotation, cleaned = parse_tone_annotation(
            'Voici la reponse.\n<lia_tone register="warm" intensity="0.62" accent="nod"/>'
        )
        assert annotation == ToneAnnotation(register="warm", intensity=0.62, accent="nod")
        assert cleaned == "Voici la reponse."

    def test_content_without_a_tag_is_returned_untouched(self) -> None:
        annotation, cleaned = parse_tone_annotation("Rien ici.")
        assert annotation is None
        assert cleaned == "Rien ici."

    def test_an_unknown_register_loses_the_annotation_but_STILL_strips(self) -> None:
        """The worse failure is markup in front of the user, not a missing face."""
        annotation, cleaned = parse_tone_annotation('Bla <lia_tone register="smug"/>')
        assert annotation is None
        assert "lia_tone" not in cleaned

    def test_a_TRUNCATED_tag_is_swept_too(self) -> None:
        """A model that starts the tag and stops mid-way still owes the reader
        a clean answer."""
        annotation, cleaned = parse_tone_annotation('Bla <lia_tone register="warm"')
        assert annotation is None
        assert "lia_tone" not in cleaned
        assert cleaned.startswith("Bla")

    def test_a_missing_intensity_still_earns_a_played_face(self) -> None:
        annotation, _ = parse_tone_annotation('Ok <lia_tone register="assured"/>')
        assert annotation is not None
        assert annotation.intensity == 0.5
        assert annotation.accent == "none"

    def test_the_marker_test_is_case_insensitive(self) -> None:
        annotation, cleaned = parse_tone_annotation('Ok <LIA_TONE register="weary"/>')
        assert annotation is not None
        assert annotation.register == "weary"
        assert "LIA_TONE" not in cleaned

    def test_streaming_fragments_are_stripped_by_the_SAME_pattern(self) -> None:
        """Two independent strippers is how a tag ends up in a database row."""
        assert strip_tone_fragments("texte <lia_ton").strip() == "texte <lia_ton"
        assert strip_tone_fragments("texte <lia_tone regi").strip() == "texte"
        assert strip_tone_fragments('texte <lia_tone register="warm"/>').strip() == "texte"

    def test_the_cheap_marker_matches_the_expensive_pattern(self) -> None:
        """The streaming path pre-tests with a substring before any regex; a
        marker that did not appear in a real tag would disable the filter."""
        assert TONE_TAG_MARKER in '<lia_tone register="warm"/>'

    def test_the_wire_shape_is_the_frontend_contract(self) -> None:
        wire = ToneAnnotation(register="playful", intensity=0.8, accent="wink").to_wire()
        assert wire == {"register": "playful", "intensity": 0.8, "accent": "wink"}


# ---------------------------------------------------------------------------
# The per-run hand-off
# ---------------------------------------------------------------------------


class TestPerRunRegistry:
    """Parsed deep in the graph, popped where the `done` chunk is assembled."""

    def test_store_then_pop_returns_the_annotation_once(self) -> None:
        annotation = ToneAnnotation(register="curious", intensity=0.4, accent="tilt")
        store_tone_annotation("run-a", annotation)
        assert pop_tone_annotation("run-a") == annotation
        assert pop_tone_annotation("run-a") is None

    def test_an_unknown_run_is_not_an_error(self) -> None:
        assert pop_tone_annotation("never-stored") is None

    def test_a_run_that_never_completes_does_not_leak_forever(self, monkeypatch) -> None:
        """An HITL interrupt or a dropped connection leaves an entry behind.

        Without the sweep the registry would grow for the life of the process,
        which is the shape of a slow leak nobody attributes to an avatar.

        The clock is frozen BEFORE the write, not after: patching it afterwards
        would leave the entry stamped with the real monotonic clock and the
        comparison would read as fresh forever.
        """
        from src.domains.agents.expressivity import annotation as module

        clock = [1000.0]
        monkeypatch.setattr(module._time, "monotonic", lambda: clock[0])
        store_tone_annotation("abandoned", ToneAnnotation("warm", 0.5, "none"))
        assert "abandoned" in module._tone_annotations

        clock[0] += module._ANNOTATION_TTL_SECONDS + 1
        # Popping ANY run sweeps the stale ones.
        assert pop_tone_annotation("other") is None
        assert "abandoned" not in module._tone_annotations

    def test_an_entry_INSIDE_the_ttl_survives_a_sweep(self, monkeypatch) -> None:
        """The other half of the same contract: a sweep that evicts a live run
        would drop the annotation of the very turn that is completing."""
        from src.domains.agents.expressivity import annotation as module

        clock = [2000.0]
        monkeypatch.setattr(module._time, "monotonic", lambda: clock[0])
        annotation = ToneAnnotation("assured", 0.6, "nod")
        store_tone_annotation("live", annotation)

        clock[0] += module._ANNOTATION_TTL_SECONDS - 1
        assert pop_tone_annotation("live") == annotation


# ---------------------------------------------------------------------------
# What is ENFORCED must be PUBLISHED (ADR-184 doctrine)
# ---------------------------------------------------------------------------


class TestPromptPublishesTheVocabulary:
    """The prompt is the only place the model learns what it may say.

    A register offered in the prompt but unknown to the vocabulary produces a
    tag that parses to nothing — a turn with no face, silently. A register the
    code accepts but the prompt never mentions is a face that can never happen.
    Both are the same defect ADR-184 named: whatever a validator can reject, its
    producer must be able to read.
    """

    @staticmethod
    def _prompt_text() -> str:
        from src.domains.agents.prompts.prompt_loader import load_prompt

        return str(load_prompt("expressivity_tone_instruction"))

    def test_every_register_the_code_accepts_is_offered_to_the_model(self) -> None:
        prompt = self._prompt_text()
        missing = [register for register in TONE_REGISTERS if register not in prompt]
        assert not missing, f"registers the model is never told about: {missing}"

    def test_every_accent_the_code_accepts_is_offered_to_the_model(self) -> None:
        prompt = self._prompt_text()
        missing = [accent for accent in TONE_ACCENTS if accent not in prompt]
        assert not missing, f"accents the model is never told about: {missing}"

    def test_the_prompt_shows_the_tag_the_parser_actually_matches(self) -> None:
        """A worked example the parser would reject teaches the wrong shape."""
        prompt = self._prompt_text()
        assert TONE_TAG_MARKER in prompt
        annotation, cleaned = parse_tone_annotation(
            'Answer.\n<lia_tone register="assured" intensity="0.4" accent="nod"/>'
        )
        assert annotation is not None and cleaned == "Answer."

    def test_the_prompt_anchors_the_DEFAULT_away_from_the_bright_registers(self) -> None:
        """The defect that started this was a model defaulting to one bright
        label every turn. The psyche prompt already forbade that in prose and
        was ignored, so this one states the plain registers as the norm."""
        prompt = self._prompt_text()
        assert 'MOST answers are "factual" or "assured"' in prompt


class TestTheTagIsReadWHERETheInstructionPutsIt:
    """LIA documents herself, so she can QUOTE the tag inside an answer.

    The instruction says the tag comes after the response, so the LAST one is
    the declaration and anything earlier is quotation. Reading the first match
    let a quoted example decide the face — and a quoted example is, by
    construction, the one a user asked about rather than the one the model
    meant.

    Every occurrence is still stripped: showing raw markup to a reader is the
    worse failure, and it is the same choice the psyche tag has made for months.
    """

    def test_the_LAST_tag_wins_over_a_quoted_one(self) -> None:
        content = (
            "Le marqueur ressemble a ceci :\n"
            '<lia_tone register="celebratory" intensity="1.0"/>\n'
            "Voila.\n"
            '<lia_tone register="factual" intensity="0.3"/>'
        )
        annotation, cleaned = parse_tone_annotation(content)
        assert annotation is not None
        assert annotation.register == "factual"
        assert annotation.intensity == 0.3
        assert "lia_tone" not in cleaned

    def test_every_occurrence_is_stripped_not_only_the_declaration(self) -> None:
        content = '<lia_tone register="warm"/> milieu <lia_tone register="weary"/>'
        _, cleaned = parse_tone_annotation(content)
        assert "lia_tone" not in cleaned
        assert "milieu" in cleaned

    def test_a_lone_quoted_tag_still_decides_because_it_is_the_last(self) -> None:
        """Not a defect: with one tag there is nothing to disambiguate, and the
        alternative — refusing a tag that is not strictly final — would drop
        the annotation whenever the model adds a closing line."""
        annotation, _ = parse_tone_annotation('<lia_tone register="warm"/> puis du texte.')
        assert annotation is not None and annotation.register == "warm"
