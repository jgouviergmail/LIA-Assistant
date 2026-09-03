"""The transcript rewrite (ADR-259): part by part, cut at turn boundaries, every index answered.

The model is a double everywhere: what is under test is the contract of the
pipeline — how a transcript is cut, how an answer is validated, and what
happens when the model drops a turn or comes back short.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.constants import (
    MEETINGS_CHARS_PER_TOKEN_ESTIMATE,
    MEETINGS_REWRITE_OUTPUT_SAFETY,
    MEETINGS_REWRITE_PART_CHARS,
)
from src.domains.meetings import transcript_rewrite as module
from src.domains.meetings.schemas import SectionKind, TemplateSection, TranscriptTurn
from src.domains.meetings.transcript_rewrite import (
    RewrittenTurn,
    RewrittenTurns,
    part_chars_for,
    rewrite_for_template,
    rewrite_transcript,
    split_turns,
)
from src.infrastructure.llm.structured_output import StructuredOutputError

pytestmark = pytest.mark.unit


def _turns(count: int, chars: int = 12) -> list[TranscriptTurn]:
    return [
        TranscriptTurn(
            speaker=f"S{i % 2 + 1}",
            start=float(i * 10),
            end=float(i * 10 + 8),
            text=f"turn {i} " + "w" * (chars - 8),
        )
        for i in range(count)
    ]


# ---------------------------------------------------------------- cutting


def test_parts_are_cut_at_turn_boundaries_and_cover_every_turn_once() -> None:
    turns = _turns(50, chars=100)
    parts = split_turns(turns, part_chars=1000)
    assert len(parts) > 1
    flat = [index for part in parts for index in part]
    assert flat == list(range(50))
    for part in parts:
        assert sum(len(turns[i].text) for i in part) <= 1000 or len(part) == 1


def test_a_single_oversize_turn_is_its_own_part() -> None:
    turns = _turns(3, chars=100)
    turns[1] = TranscriptTurn(speaker="S1", start=10, end=18, text="x" * 5000)
    parts = split_turns(turns, part_chars=1000)
    assert parts == [[0], [1], [2]]


def test_the_part_size_follows_the_effective_max_tokens() -> None:
    generous = part_chars_for(SimpleNamespace(max_tokens=8000))
    assert generous == MEETINGS_REWRITE_PART_CHARS
    tight = part_chars_for(SimpleNamespace(max_tokens=2000))
    assert tight == int(2000 * MEETINGS_CHARS_PER_TOKEN_ESTIMATE * MEETINGS_REWRITE_OUTPUT_SAFETY)
    assert tight < generous


# ---------------------------------------------------------------- rewriting


@pytest.fixture
def llm(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """A model that rewrites every turn as ``clean <index>`` unless told otherwise."""

    async def _answer(_llm, messages, _schema, **kwargs):
        human = messages[-1].content
        indexes = [int(line.split(" | ")[0]) for line in human.split("TURNS:\n")[1].splitlines()]
        return RewrittenTurns(turns=[RewrittenTurn(index=i, text=f"clean {i}") for i in indexes])

    call = AsyncMock(side_effect=_answer)
    monkeypatch.setattr(module, "get_structured_output_with_retry", call)
    monkeypatch.setattr(module, "get_llm", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(module, "part_chars_for", lambda config: 1000)
    return call


async def test_every_turn_comes_back_rewritten_in_order_with_its_speaker(
    llm: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    turns = _turns(25)
    monkeypatch.setattr(module, "part_chars_for", lambda config: 60)
    lines = await rewrite_transcript(turns, "Clean it.", provider="openai", capture=MagicMock())
    assert [line.text for line in lines] == [f"clean {i}" for i in range(25)]
    assert [line.speaker for line in lines] == [t.speaker for t in turns]
    assert [line.start for line in lines] == [t.start for t in turns]
    parts = split_turns(turns, part_chars=60)
    assert len(parts) == 5 and llm.await_count == len(parts)
    human = llm.await_args_list[0].args[1][-1].content
    assert human.startswith("INSTRUCTION:\nClean it.")


async def test_the_selection_capture_rides_along_and_the_node_is_named(llm: AsyncMock) -> None:
    capture = MagicMock()
    await rewrite_transcript(_turns(3), "Clean it.", provider="openai", capture=capture)
    kwargs = llm.await_args.kwargs
    assert kwargs["config"]["callbacks"] == [capture]
    assert kwargs["node_name"].endswith("_rewrite")


async def test_an_omitted_index_makes_the_part_split_and_retry_once(
    llm: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    turns = _turns(8)
    calls: list[list[int]] = []

    async def _answer(_llm, messages, _schema, **kwargs):
        human = messages[-1].content
        indexes = [int(line.split(" | ")[0]) for line in human.split("TURNS:\n")[1].splitlines()]
        calls.append(indexes)
        # The first (whole) part comes back truncated: index 7 is missing.
        answered = indexes if len(calls) > 1 else [i for i in indexes if i != 7]
        return RewrittenTurns(turns=[RewrittenTurn(index=i, text=f"clean {i}") for i in answered])

    llm.side_effect = _answer
    monkeypatch.setattr(module, "part_chars_for", lambda config: 10_000)
    lines = await rewrite_transcript(turns, "Clean it.", provider="openai", capture=MagicMock())
    assert calls[0] == list(range(8))
    assert calls[1] == [0, 1, 2, 3] and calls[2] == [4, 5, 6, 7]
    assert [line.text for line in lines] == [f"clean {i}" for i in range(8)]


async def test_a_turn_still_missing_after_the_retry_keeps_its_original_text(
    llm: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    turns = _turns(4)

    async def _answer(_llm, messages, _schema, **kwargs):
        human = messages[-1].content
        indexes = [int(line.split(" | ")[0]) for line in human.split("TURNS:\n")[1].splitlines()]
        return RewrittenTurns(
            turns=[RewrittenTurn(index=i, text=f"clean {i}") for i in indexes if i != 2]
        )

    llm.side_effect = _answer
    monkeypatch.setattr(module, "part_chars_for", lambda config: 10_000)
    lines = await rewrite_transcript(turns, "Clean it.", provider="openai", capture=MagicMock())
    assert lines[2].text == turns[2].text
    assert [line.text for line in lines if line.text.startswith("clean")] == [
        "clean 0",
        "clean 1",
        "clean 3",
    ]


async def test_an_index_the_input_never_had_is_dropped(llm: AsyncMock) -> None:
    turns = _turns(2)

    async def _answer(_llm, messages, _schema, **kwargs):
        return RewrittenTurns(
            turns=[
                RewrittenTurn(index=0, text="clean 0"),
                RewrittenTurn(index=1, text="clean 1"),
                RewrittenTurn(index=99, text="ghost"),
            ]
        )

    llm.side_effect = _answer
    lines = await rewrite_transcript(turns, "Clean it.", provider="openai", capture=MagicMock())
    assert [line.text for line in lines] == ["clean 0", "clean 1"]


async def test_a_short_answer_is_retried_once_then_kept(
    llm: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    turns = _turns(4, chars=200)
    attempts = 0

    async def _answer(_llm, messages, _schema, **kwargs):
        nonlocal attempts
        attempts += 1
        human = messages[-1].content
        indexes = [int(line.split(" | ")[0]) for line in human.split("TURNS:\n")[1].splitlines()]
        return RewrittenTurns(turns=[RewrittenTurn(index=i, text="ok") for i in indexes])

    llm.side_effect = _answer
    monkeypatch.setattr(module, "part_chars_for", lambda config: 10_000)
    lines = await rewrite_transcript(turns, "Clean it.", provider="openai", capture=MagicMock())
    assert attempts == 2  # the whole part once, then once more — never a third time
    assert all(line.text == "ok" for line in lines)


async def test_a_model_failure_propagates_for_the_job_to_classify(llm: AsyncMock) -> None:
    llm.side_effect = StructuredOutputError("no", "openai", "RewrittenTurns")
    with pytest.raises(StructuredOutputError):
        await rewrite_transcript(_turns(3), "Clean it.", provider="openai", capture=MagicMock())


async def test_rewrite_for_template_runs_one_pass_per_distinct_instruction(llm: AsyncMock) -> None:
    template = [
        TemplateSection(key="summary", label="S", instruction="sum", kind=SectionKind.PARAGRAPH),
        TemplateSection(
            key="clean", label="C", instruction="Clean it.", kind=SectionKind.TRANSCRIPT
        ),
        TemplateSection(
            key="again", label="A", instruction="Clean it.", kind=SectionKind.TRANSCRIPT
        ),
        TemplateSection(key="pro", label="P", instruction="Pro.", kind=SectionKind.TRANSCRIPT),
    ]
    turns = _turns(3)
    rewritten = await rewrite_for_template(turns, template, provider="openai", capture=MagicMock())
    assert set(rewritten) == {"clean", "again", "pro"}
    assert rewritten["clean"] is rewritten["again"]
    assert llm.await_count == 2  # one pass per distinct instruction, parts folded


async def test_rewrite_for_template_is_a_no_op_without_transcript_sections(
    llm: AsyncMock,
) -> None:
    template = [
        TemplateSection(key="summary", label="S", instruction="sum", kind=SectionKind.PARAGRAPH)
    ]
    assert (
        await rewrite_for_template(_turns(3), template, provider="openai", capture=MagicMock())
        == {}
    )
    llm.assert_not_awaited()
