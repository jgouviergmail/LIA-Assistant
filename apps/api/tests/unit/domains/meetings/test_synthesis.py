"""Minutes synthesis (ADR-258): the template is the contract, the model is repaired.

The repair folds the permissive model answer into the strict report; the
prompt blocks carry every fact the model needs; the window budget decides the
condense pass. The LLM itself is a fake here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.meetings import synthesis
from src.domains.meetings.schemas import (
    SectionKind,
    TemplateSection,
    TranscriptLine,
    TranscriptTurn,
)
from src.domains.meetings.synthesis import (
    SynthesisContext,
    SynthesizedAction,
    SynthesizedMinutes,
    SynthesizedParticipant,
    SynthesizedSection,
    SynthesizedTopic,
    estimate_tokens,
    render_context,
    render_template,
    render_transcript,
    repair_report,
    split_transcript,
    synthesize_minutes,
    transcript_budget_tokens,
)

pytestmark = pytest.mark.unit


def _template() -> list[TemplateSection]:
    return [
        TemplateSection(
            key="summary", label="Résumé", instruction="Prose.", kind=SectionKind.PARAGRAPH
        ),
        TemplateSection(
            key="decisions", label="Décisions", instruction="Puces.", kind=SectionKind.BULLETS
        ),
        TemplateSection(
            key="topics", label="Sujets", instruction="Sujets.", kind=SectionKind.TOPICS
        ),
        TemplateSection(
            key="actions", label="Actions", instruction="Actions.", kind=SectionKind.ACTION_ITEMS
        ),
    ]


def _context(**over: Any) -> SynthesisContext:
    base: dict[str, Any] = {
        "language": "fr",
        "timezone": "Europe/Paris",
        "started_at": datetime(2026, 9, 2, 8, 0, tzinfo=UTC),
        "stopped_at": datetime(2026, 9, 2, 9, 5, tzinfo=UTC),
        "duration_seconds": 3900.0,
        "location_label": "Salle B",
        "calendar_title": "Point projet",
        "calendar_attendees": ["Marie", "Paul"],
        "gaps": 1,
        "diarized": True,
    }
    base.update(over)
    return SynthesisContext(**base)


# ---------------------------------------------------------------------------
# Repair
# ---------------------------------------------------------------------------


def test_repair_keeps_the_template_order_and_fills_missing_sections_empty() -> None:
    minutes = SynthesizedMinutes(
        title="  Point projet  ",
        participants=[],
        sections=[
            SynthesizedSection(
                key="topics", topics=[SynthesizedTopic(title="Budget", summary="Validé.")]
            ),
            SynthesizedSection(key="invented", paragraph="dropped"),
        ],
    )
    report = repair_report(minutes, _template(), speaker_labels=["S1"], language="fr")
    assert [s.key for s in report.sections] == ["summary", "decisions", "topics", "actions"]
    assert report.title == "Point projet"
    assert report.sections[0].is_empty() and report.sections[1].is_empty()
    assert report.sections[2].topics[0].title == "Budget"
    assert report.sections[3].is_empty()


def test_repair_converts_a_payload_given_in_the_wrong_shape() -> None:
    minutes = SynthesizedMinutes(
        title="T",
        sections=[
            # bullets given for a paragraph section → joined prose
            SynthesizedSection(key="summary", bullets=["Un.", "Deux."]),
            # a paragraph given for a bullets section → one bullet per line
            SynthesizedSection(key="decisions", paragraph="- Oui\n- Non\n"),
            # plain bullets given for topics → title + summary from the line
            SynthesizedSection(key="topics", bullets=["Budget validé"]),
            # bullets given for action items → descriptions
            SynthesizedSection(key="actions", bullets=["Envoyer le devis"]),
        ],
    )
    report = repair_report(minutes, _template(), speaker_labels=["S1"], language="fr")
    assert report.sections[0].paragraph == "Un. Deux."
    assert report.sections[1].bullets == ["Oui", "Non"]
    assert report.sections[2].topics[0].title == "Budget validé"
    assert report.sections[3].action_items[0].description == "Envoyer le devis"
    assert report.sections[3].action_items[0].owner is None


def test_repair_restricts_participants_to_labels_that_spoke_and_adds_the_silent_ones() -> None:
    minutes = SynthesizedMinutes(
        title="T",
        participants=[
            SynthesizedParticipant(label="S2", name="Marie", role=" Chef "),
            SynthesizedParticipant(label="S9", name="Fantôme"),
            SynthesizedParticipant(label="S2", name="dup"),
        ],
        sections=[],
    )
    report = repair_report(minutes, _template(), speaker_labels=["S1", "S2"], language="fr")
    assert [(p.label, p.name, p.role) for p in report.participants] == [
        ("S1", None, None),
        ("S2", "Marie", "Chef"),
    ]


def test_repair_clips_over_long_fields_and_localizes_an_empty_title() -> None:
    minutes = SynthesizedMinutes(
        title="",
        sections=[SynthesizedSection(key="summary", paragraph="x" * 9000)],
    )
    report = repair_report(minutes, _template(), speaker_labels=[], language="fr")
    assert report.title == "Compte rendu de réunion"
    assert len(report.sections[0].paragraph or "") == 8000
    assert (report.sections[0].paragraph or "").endswith("…")


def test_action_items_keep_owner_and_absolute_due_date() -> None:
    minutes = SynthesizedMinutes(
        title="T",
        sections=[
            SynthesizedSection(
                key="actions",
                action_items=[
                    SynthesizedAction(description="Relancer", owner="S1", due_date="2026-09-05")
                ],
            )
        ],
    )
    report = repair_report(minutes, _template(), speaker_labels=["S1"], language="fr")
    action = report.sections[3].action_items[0]
    assert (action.description, action.owner, action.due_date) == ("Relancer", "S1", "2026-09-05")


# ---------------------------------------------------------------------------
# Prompt blocks and budget
# ---------------------------------------------------------------------------


def test_render_context_states_every_fact_in_the_users_timezone() -> None:
    block = render_context(_context())
    assert "LANGUAGE: fr" in block
    assert "DATE: 2026-09-02 (Wednesday)" in block
    assert "START: 10:00" in block and "END: 11:05" in block  # UTC+2 in September
    assert "DURATION: 1:05:00" in block
    assert "LOCATION: Salle B" in block
    assert "CALENDAR EVENT: Point projet" in block
    assert "CALENDAR ATTENDEES (hints): Marie, Paul" in block
    assert "GAPS: 1" in block and "SPEAKERS SEPARATED: yes" in block


def test_render_context_names_the_unknowns_instead_of_omitting_them() -> None:
    block = render_context(
        _context(
            stopped_at=None,
            duration_seconds=None,
            location_label=None,
            calendar_title=None,
            calendar_attendees=[],
            diarized=False,
        )
    )
    assert "END: unknown" in block and "DURATION: unknown" in block
    assert "LOCATION: unknown" in block and "CALENDAR EVENT: none found" in block
    assert "CALENDAR ATTENDEES (hints): none" in block and "SPEAKERS SEPARATED: no" in block


def test_render_template_and_transcript_carry_the_fields_the_prompt_describes() -> None:
    template_block = render_template(_template()[:1])
    assert "key=summary | kind=paragraph | label=Résumé" in template_block
    assert "instruction: Prose." in template_block
    turns = [TranscriptTurn(speaker="S1", start=65.0, end=70.0, text="Bonjour")]
    assert render_transcript(turns) == "[01:05] S1: Bonjour"


def test_split_transcript_cuts_at_line_boundaries_under_the_part_size() -> None:
    text = "\n".join(f"[00:0{i}] S1: ligne {i}" for i in range(10))
    parts = split_transcript(text, part_chars=60)
    assert "".join(parts).replace("\n", "") == text.replace("\n", "")
    assert all(len(part) <= 60 for part in parts)
    assert len(parts) > 1


def test_budget_derives_from_the_effective_context_window(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(synthesis, "get_effective_context_window", lambda model: 20_000)
    monkeypatch.setattr(synthesis, "MEETINGS_SYNTHESIS_RESERVE_TOKENS", 12_000)
    assert transcript_budget_tokens("any") == 8_000
    assert estimate_tokens("a" * 300) == 100


# ---------------------------------------------------------------------------
# The call
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_llm(monkeypatch: pytest.MonkeyPatch):
    """Replace the LLM seam with a scripted answer and record the prompts sent."""
    calls: list[dict[str, Any]] = []
    answers: list[Any] = []

    async def _structured(llm: Any, messages: Any, schema: Any, **kwargs: Any) -> Any:
        calls.append({"schema": schema, "messages": messages, **kwargs})
        return answers.pop(0)

    monkeypatch.setattr(synthesis, "get_structured_output_with_retry", _structured)
    monkeypatch.setattr(synthesis, "get_llm", lambda llm_type: object())
    monkeypatch.setattr(
        synthesis,
        "get_llm_config_for_agent",
        lambda settings, llm_type: SimpleNamespace(provider="openai", model="gpt-4.1"),
    )
    monkeypatch.setattr(synthesis, "load_meeting_prompt", lambda name: f"PROMPT({name})")
    return {"calls": calls, "answers": answers}


async def test_synthesize_sends_context_template_and_transcript_in_one_call(
    fake_llm: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(synthesis, "get_effective_context_window", lambda model: 1_000_000)
    fake_llm["answers"].append(
        SynthesizedMinutes(
            title="Point", sections=[SynthesizedSection(key="summary", paragraph="Ok.")]
        )
    )
    turns = [TranscriptTurn(speaker="S1", start=0, end=2, text="Bonjour")]
    result = await synthesize_minutes(turns, _template(), _context())
    assert result.condensed is False
    assert result.report.sections[0].paragraph == "Ok."
    assert result.usage.model_name == "gpt-4.1"
    (call,) = fake_llm["calls"]
    assert call["schema"] is SynthesizedMinutes and call["node_name"] == "meeting_synthesis"
    system, human = call["messages"]
    assert system.content == "PROMPT(meeting_synthesis_prompt)"
    assert "CONTEXT:" in human.content and "TEMPLATE:" in human.content
    assert "TRANSCRIPT:\n[00:00] S1: Bonjour" in human.content


async def test_synthesize_condenses_part_by_part_when_the_transcript_overflows(
    fake_llm: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        synthesis, "get_effective_context_window", lambda model: 12_100
    )  # 100-token budget
    monkeypatch.setattr(synthesis, "MEETINGS_CONDENSE_PART_CHARS", 200)
    turns = [TranscriptTurn(speaker="S1", start=i, end=i + 1, text="mot " * 20) for i in range(6)]
    parts = len(split_transcript(render_transcript(turns), part_chars=200))
    assert parts > 1
    fake_llm["answers"].extend(
        [synthesis.CondensedNotes(notes=f"notes part {i + 1}") for i in range(parts)]
        + [SynthesizedMinutes(title="Long", sections=[])]
    )
    result = await synthesize_minutes(turns, _template(), _context())
    assert result.condensed is True
    schemas = [call["schema"] for call in fake_llm["calls"]]
    assert schemas == [synthesis.CondensedNotes] * parts + [SynthesizedMinutes]
    final_human = fake_llm["calls"][-1]["messages"][1].content
    assert "CONDENSED NOTES (from the transcript):" in final_human
    assert f"PART 1/{parts}" + chr(10) + "notes part 1" in final_human
    assert f"PART {parts}/{parts}" + chr(10) + f"notes part {parts}" in final_human


# ---------------------------------------------------------------------------
# ADR-259: the transcript kind
# ---------------------------------------------------------------------------


def _transcript_template() -> list[TemplateSection]:
    return [
        TemplateSection(key="summary", label="Résumé", instruction="s", kind=SectionKind.PARAGRAPH),
        TemplateSection(
            key="transcript",
            label="Transcription",
            instruction="clean",
            kind=SectionKind.TRANSCRIPT,
        ),
    ]


def test_repair_injects_the_rewritten_transcript_and_ignores_what_the_model_put_there() -> None:
    minutes = SynthesizedMinutes(
        title="T",
        sections=[
            SynthesizedSection(key="summary", paragraph="Court."),
            SynthesizedSection(key="transcript", paragraph="the model tried to fill it"),
        ],
    )
    lines = [TranscriptLine(speaker="S1", start=0.0, text="Propre.")]
    report = repair_report(
        minutes,
        _transcript_template(),
        speaker_labels=["S1"],
        language="fr",
        rewritten={"transcript": lines},
    )
    assert report.sections[1].kind is SectionKind.TRANSCRIPT
    assert report.sections[1].transcript == lines
    assert report.sections[1].paragraph is None
    # Without an injection the section is empty, never the model's improvisation.
    bare = repair_report(minutes, _transcript_template(), speaker_labels=["S1"], language="fr")
    assert bare.sections[1].is_empty()


def test_render_template_hides_transcript_sections_from_the_single_call() -> None:
    block = render_template(_transcript_template())
    assert "key=summary" in block and "key=transcript" not in block


async def test_synthesize_rewrites_transcript_sections_and_asks_the_rest_of_the_template(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lines = [TranscriptLine(speaker="S1", start=0.0, text="Propre.")]
    rewrite = AsyncMock(return_value={"transcript": lines})
    monkeypatch.setattr(synthesis, "rewrite_for_template", rewrite)
    seen: dict[str, str] = {}

    async def _answer(_llm, messages, _schema, **kwargs):
        seen["human"] = messages[-1].content
        return SynthesizedMinutes(
            title="T", sections=[SynthesizedSection(key="summary", paragraph="C.")]
        )

    monkeypatch.setattr(
        synthesis, "get_structured_output_with_retry", AsyncMock(side_effect=_answer)
    )
    monkeypatch.setattr(synthesis, "get_llm", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(
        synthesis,
        "get_llm_config_for_agent",
        MagicMock(return_value=SimpleNamespace(provider="openai", model="gpt-x")),
    )
    monkeypatch.setattr(synthesis, "transcript_budget_tokens", lambda model: 10_000_000)
    capture = MagicMock(tokens_in=3, tokens_out=4, tokens_cache=0)
    turns = [TranscriptTurn(speaker="S1", start=0, end=1, text="Bonjour, euh, bonjour.")]
    result = await synthesize_minutes(turns, _transcript_template(), _context(), capture=capture)
    rewrite.assert_awaited_once()
    assert rewrite.await_args.kwargs["capture"] is capture
    assert "key=transcript" not in seen["human"] and "key=summary" in seen["human"]
    assert result.report.sections[1].transcript == lines
    assert result.report.sections[0].paragraph == "C."
    assert result.usage.tokens_in == 3
