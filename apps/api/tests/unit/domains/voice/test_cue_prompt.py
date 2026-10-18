"""The cue block a spoken-comment writer reads states what the code enforces (ADR-345, ADR-284).

Four promises, each one a way the block could lie: it names exactly the cues
the engine that will speak performs (a cue it cannot perform would be dropped
in silence, the writer believing it was obeyed), each with the meaning that
says when it fits (measured 2026-10-17: told only the names, writers of two
model families opened nearly every comment with ``[warm]`` or ``[cheerful]``,
failures included, and none ever laughed or sighed), its example shows one of
them, and the budget it publishes is the bound :class:`AuthoredCues` enforces.
"""

from __future__ import annotations

import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core.prompt_store import parse_prompt_sections, read_prompt_file
from src.domains.voice import cue_prompt, expressive_cues
from src.domains.voice import service as voice_service
from src.domains.voice.cue_prompt import CUE_PROMPT_LINES, expressive_cues_block
from src.domains.voice.expressive_cues import (
    DELIVERY_CUES,
    ELEVENLABS_SSML_BREAK,
    EVENT_CUES,
    FISH_S1_CUES,
    GEMINI_VOCAL_TAGS,
    NO_CUES,
    AuthoredCues,
    Cue,
    CueDialect,
)
from src.domains.voice.schemas import VoiceCommentRequest
from src.domains.voice.service import VoiceCommentService

pytestmark = pytest.mark.unit

#: Every dialect an engine is mapped to, the silent one included.
_DIALECTS = sorted(
    {dialect.name: dialect for *_, dialect in expressive_cues._RULES}.values(),
    key=lambda dialect: dialect.name,
)
_CUE_WORDS = re.compile(r"\[([^\[\]]+)\]")
_LINES = dict(parse_prompt_sections(read_prompt_file(CUE_PROMPT_LINES), 2))


def _section(block: str, header: str) -> list[str]:
    """The indented cue lines listed under the line that starts with ``header``."""
    lines = block.splitlines()
    start = next((index for index, line in enumerate(lines) if line.startswith(header)), None)
    if start is None:
        return []
    listed: list[str] = []
    for line in lines[start + 1 :]:
        if not line.startswith("  "):
            break
        listed.append(line.strip())
    return listed


def _listed(block: str, header: str) -> set[Cue]:
    return {Cue(_CUE_WORDS.findall(line)[0]) for line in _section(block, header)}


def _example(block: str) -> str:
    return next(line for line in block.splitlines() if line.startswith("Example"))


def _rules(block: str) -> str:
    return next(line for line in block.splitlines() if line.startswith("- A cue colours"))


#: The rules row as every engine performing both kinds and a night cue reads it —
#: byte for byte the text measured on 2026-10-17, before its clauses were split.
_FULL_RULES = (
    "- A cue colours the NEWS, never the outcome of your own act. What you did or could not "
    "do — a confirmation that it is done, a status, a failure to get the result, nothing "
    "found — is said plainly, with no cue at all, whatever your personality (Heuristic 9); "
    "only late at night may a cue meant for the night above soften it. News that matters to "
    "the person — an approval, a cancellation, a risk, a surprise, something funny — may open "
    "with the one cue whose meaning above fits it, or carry a sound where the moment has one, "
    "coloured by `<personality_profile>` and `<user_cognitive_state>`. At most 2 in the whole "
    "comment; when in doubt, none."
)
#: First-person words: how LIA reports an act of its own, never how it tells news.
_FIRST_PERSON = re.compile(r"\b(?:I|I'm|I've|I'll|I'd|me|my|mine|myself)\b")


@pytest.mark.parametrize("dialect", _DIALECTS, ids=lambda dialect: dialect.name)
def test_the_block_names_exactly_the_cues_the_engine_performs(dialect: CueDialect) -> None:
    block = expressive_cues_block(dialect, budget=2)

    assert _listed(block, "- How a sentence") == dialect.performs() & DELIVERY_CUES
    assert _listed(block, "- A sound") == dialect.performs() & EVENT_CUES


@pytest.mark.parametrize("dialect", _DIALECTS, ids=lambda dialect: dialect.name)
def test_each_listed_cue_says_when_it_fits(dialect: CueDialect) -> None:
    """A cue name alone is a mood board, not a rule: each one carries its meaning."""
    block = expressive_cues_block(dialect, budget=2)
    listed = _section(block, "- How a sentence") + _section(block, "- A sound")

    assert listed
    for line in listed:
        cue = Cue(_CUE_WORDS.findall(line)[0])
        assert line == f"[{cue.value}] — {_LINES[f'meaning.{cue.name.lower()}']}"


@pytest.mark.parametrize("cue", list(Cue), ids=lambda cue: cue.name.lower())
def test_every_cue_has_a_meaning_and_an_example_of_its_own(cue: Cue) -> None:
    meaning = _LINES.get(f"meaning.{cue.name.lower()}", "")
    example = _LINES.get(f"example.{cue.name.lower()}", "")

    assert meaning and "[" not in meaning
    # The example shows its own cue, once, and no other bracket.
    assert _CUE_WORDS.findall(example) == [cue.value]


@pytest.mark.parametrize("cue", list(Cue), ids=lambda cue: cue.name.lower())
def test_every_example_is_news_never_a_report_of_lias_own_act(cue: Cue) -> None:
    """The rules keep LIA's own acts plain; an example cueing one teaches the opposite.

    ``[warm] I kept the table by the window`` was a confirmation of LIA's own act,
    and warm is the example most engines are shown (ElevenLabs v3/v4, Fish S2,
    drama-3, Gemini 3.8)."""
    example = _LINES[f"example.{cue.name.lower()}"]

    assert not _FIRST_PERSON.search(example), example


def test_the_night_cues_are_the_cues_whose_meaning_names_the_night() -> None:
    """The night clause is stated by a code table: it must name what the file means."""
    named = {cue for cue in Cue if "night" in _LINES[f"meaning.{cue.name.lower()}"]}

    assert named == cue_prompt._NIGHT_CUES


@pytest.mark.parametrize("dialect", _DIALECTS, ids=lambda dialect: dialect.name)
def test_the_example_shows_a_cue_the_engine_performs(dialect: CueDialect) -> None:
    shown = _CUE_WORDS.findall(_example(expressive_cues_block(dialect, 2)))

    assert len(shown) == 1
    assert Cue(shown[0]) in dialect.performs()


def test_the_example_prefers_warm_when_the_engine_performs_it() -> None:
    block = expressive_cues_block(expressive_cues.ELEVENLABS_AUDIO_TAGS, 2)

    assert _example(block) == f"Example: {_LINES['example.warm']}"


def test_an_engine_without_warm_is_shown_a_delivery_it_performs() -> None:
    """Fish ``s1``'s fixed set has no warm: the example must not teach one."""
    block = expressive_cues_block(FISH_S1_CUES, 2)

    assert "[warm]" not in block
    assert _example(block) == f"Example: {_LINES['example.calm']}"


def test_an_engine_with_a_pause_only_is_never_told_about_delivery() -> None:
    block = expressive_cues_block(ELEVENLABS_SSML_BREAK, 2)

    assert "How a sentence is said" not in block
    assert _listed(block, "- A sound") == {Cue.SHORT_PAUSE}
    assert _example(block) == f"Example: {_LINES['example.short_pause']}"
    # Neither do its rules invite a delivery to open with, nor a cue for the night:
    # it performs neither (ADR-284).
    rules = _rules(block)
    assert _LINES["rules.news.delivery"] not in rules
    assert "night" not in rules
    assert rules == (
        "- A cue colours the NEWS, never the outcome of your own act. What you did or could "
        "not do — a confirmation that it is done, a status, a failure to get the result, "
        "nothing found — is said plainly, with no cue at all, whatever your personality "
        "(Heuristic 9). News that matters to the person — an approval, a cancellation, a "
        "risk, a surprise, something funny — may carry a sound where the moment has one, "
        "coloured by `<personality_profile>` and `<user_cognitive_state>`. At most 2 in the "
        "whole comment; when in doubt, none."
    )


@pytest.mark.parametrize(
    "dialect",
    [d for d in _DIALECTS if d.performs() & DELIVERY_CUES and d.performs() & EVENT_CUES],
    ids=lambda dialect: dialect.name,
)
def test_an_engine_performing_every_kind_reads_the_measured_rules_unchanged(
    dialect: CueDialect,
) -> None:
    """Splitting the clauses changed nothing for an engine that performs them all."""
    assert dialect.performs() & cue_prompt._NIGHT_CUES
    assert _rules(expressive_cues_block(dialect, 2)) == _FULL_RULES


@pytest.mark.parametrize("dialect", _DIALECTS, ids=lambda dialect: dialect.name)
def test_each_rules_clause_is_stated_iff_its_cues_are_listed(dialect: CueDialect) -> None:
    rules = _rules(expressive_cues_block(dialect, 2))
    performed = dialect.performs()

    assert (_LINES["rules.news.delivery"] in rules) is bool(performed & DELIVERY_CUES)
    assert (_LINES["rules.news.sound"] in rules) is bool(performed & EVENT_CUES)
    assert (_LINES["rules.night"] in rules) is bool(performed & cue_prompt._NIGHT_CUES)
    assert not re.search(r"\{\w+\}", rules)


@pytest.mark.parametrize(
    ("spellings", "night"),
    [({Cue.SERIOUS: "[serious]"}, False), ({Cue.CALM: "[calm]"}, True)],
    ids=["a delivery alone", "a night cue alone"],
)
def test_an_engine_without_sounds_is_never_told_to_carry_one(
    spellings: dict[Cue, str], night: bool
) -> None:
    rules = _rules(expressive_cues_block(CueDialect("delivery_only", spellings), 2))

    assert f"may {_LINES['rules.news.delivery']}, coloured by" in rules
    assert _LINES["rules.news.sound"] not in rules
    assert (_LINES["rules.night"] in rules) is night


def test_a_style_engine_is_told_about_delivery_too() -> None:
    """Gemini 3.8 performs a delivery as the sentence's style: the writer may ask for one."""
    block = expressive_cues_block(GEMINI_VOCAL_TAGS, 2)

    assert _listed(block, "- How a sentence") == DELIVERY_CUES
    assert _listed(block, "- A sound") == EVENT_CUES


@pytest.mark.parametrize("budget", [0, -1])
def test_no_budget_or_no_cue_writes_no_block(budget: int) -> None:
    assert expressive_cues_block(expressive_cues.FISH_S2_CUES, budget) == ""
    assert expressive_cues_block(NO_CUES, 3) == ""


@pytest.mark.parametrize("budget", [1, 2, 5])
def test_the_published_budget_is_the_one_the_renderer_enforces(budget: int) -> None:
    dialect = expressive_cues.ELEVENLABS_AUDIO_TAGS
    published = re.search(
        r"at most (\d+) in the whole comment",
        expressive_cues_block(dialect, budget),
        re.IGNORECASE,
    )
    assert published is not None

    over = " ".join(f"[{Cue.SIGHS.value}] word{index}." for index in range(budget + 3))
    spoken = AuthoredCues(dialect, budget).render(over).text

    assert spoken.count("[sighs]") == int(published.group(1)) == budget


async def test_the_comment_prompt_carries_the_block_of_the_engine_that_speaks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(voice_service, "get_llm", lambda llm_type: SimpleNamespace())
    budget = voice_service.settings.voice_expressive_cues_max

    def request(cue_budget: int) -> VoiceCommentRequest:
        return VoiceCommentRequest(
            context_summary="Booked.",
            personality_instruction="",
            user_language="en",
            current_datetime="2026-10-14 09:00",
            cue_budget=cue_budget,
        )

    async def prompt_for(provider: str, model: str, cue_budget: int = budget) -> str:
        service = VoiceCommentService()
        config = SimpleNamespace(provider=provider, model=model)
        client = SimpleNamespace(provider_name=provider)
        service._serve_tts = AsyncMock(return_value=(config, client))  # type: ignore[method-assign]
        return (await service._build_voice_llm_invocation(request(cue_budget)))[1]

    expressive = await prompt_for("elevenlabs", "eleven_v4")
    plain = await prompt_for("openai", "tts-1")
    # A comment reading the answer itself has no cue budget: no block, whatever the engine.
    reading_the_answer = await prompt_for("elevenlabs", "eleven_v4", cue_budget=0)

    assert (f"at most {budget} in the whole comment" in expressive.lower()) is (budget > 0)
    assert "<expressive_cues>" not in plain
    assert "<expressive_cues>" not in reading_the_answer
    # The block comes after every rule it makes an exception to.
    if budget > 0:
        assert (
            expressive.index("</output_specifications>")
            < expressive.index("<expressive_cues>")
            < expressive.index("<execution_context>")
        )
