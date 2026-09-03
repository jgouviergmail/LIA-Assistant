"""Template resolution (ADR-259): one precedence, a bounded excerpt, a fallback that never fails the meeting."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.config import settings
from src.core.constants import MEETINGS_DEFAULT_BUILTIN_TEMPLATE_KEY
from src.core.exceptions import BaseAPIException
from src.domains.meetings import template_resolution as module
from src.domains.meetings.schemas import (
    SectionKind,
    TemplateCategory,
    TemplateSection,
    TemplateSelection,
    TranscriptTurn,
)
from src.domains.meetings.template_ref import TemplateRef
from src.domains.meetings.template_resolution import (
    TemplateChoice,
    decide_template,
    render_candidates,
    template_for_regeneration,
    transcript_excerpt,
)
from src.domains.meetings.template_service import ResolvedTemplate
from src.infrastructure.llm.structured_output import StructuredOutputError
from src.infrastructure.observability.metrics_meetings import meeting_template_selection_total

pytestmark = pytest.mark.unit

USER = uuid.uuid4()


def _section(key: str) -> TemplateSection:
    return TemplateSection(key=key, label=key.title(), instruction="i", kind=SectionKind.BULLETS)


def _resolved(ref: str, name: str, *keys: str, description: str | None = None) -> ResolvedTemplate:
    return ResolvedTemplate(
        ref=TemplateRef.parse(ref),
        name=name,
        category=TemplateCategory.MEETING,
        sections=[_section(k) for k in keys],
        auto_selectable=True,
        description=description,
    )


DEFAULT = _resolved(f"builtin:{MEETINGS_DEFAULT_BUILTIN_TEMPLATE_KEY}", "Minutes", "summary")
MEDICAL = _resolved(
    "builtin:medical_appointment", "Medical", "findings", "treatment", description="For doctors."
)
MINE = _resolved(f"user:{uuid.uuid4()}", "Mine", "notes")


def _turns() -> list[TranscriptTurn]:
    return [
        TranscriptTurn(speaker="S1", start=float(i * 5), end=float(i * 5 + 4), text=f"turn {i}")
        for i in range(40)
    ]


def _meeting(**over):
    meeting = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=USER,
        template_ref=None,
        template_name=None,
        template_selection=None,
        template_selection_reason=None,
        template_snapshot=None,
    )
    for key, value in over.items():
        setattr(meeting, key, value)
    return meeting


@pytest.fixture
def fake_service(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    service = MagicMock()

    async def _resolve(user_id, ref: str, language):
        table = {str(DEFAULT.ref): DEFAULT, str(MEDICAL.ref): MEDICAL, str(MINE.ref): MINE}
        if ref not in table:
            raise BaseAPIException(status_code=404, detail={"code": "template_not_found"})
        return table[ref]

    service.resolve = AsyncMock(side_effect=_resolve)
    service.candidates = AsyncMock(return_value=[DEFAULT, MEDICAL, MINE])
    monkeypatch.setattr(module, "MeetingTemplateService", MagicMock(return_value=service))
    return service


@pytest.fixture
def fake_llm(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    call = AsyncMock(
        return_value=TemplateChoice(
            template_ref=str(MEDICAL.ref), confidence=0.9, reason="A doctor speaks."
        )
    )
    monkeypatch.setattr(module, "get_structured_output_with_retry", call)
    monkeypatch.setattr(module, "get_llm", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(
        module,
        "get_llm_config_for_agent",
        MagicMock(return_value=SimpleNamespace(provider="openai", model="gpt-x")),
    )
    monkeypatch.setattr(settings, "meetings_template_auto_select_enabled", True)
    monkeypatch.setattr(settings, "meetings_template_auto_min_confidence", 0.5)
    return call


def _outcome(outcome: str) -> float:
    return meeting_template_selection_total.labels(outcome=outcome)._value.get()


async def _decide(meeting, preference=None, capture=None):
    return await decide_template(
        MagicMock(),
        meeting=meeting,
        preference=preference,
        turns=_turns(),
        calendar_title="Point projet",
        language="fr",
        capture=capture or MagicMock(),
    )


# ---------------------------------------------------------------- pure helpers


def test_the_excerpt_is_bounded_keeps_the_head_and_samples_the_rest() -> None:
    text = "\n".join(f"[{i:02d}:00] S1: line {i} " + "x" * 80 for i in range(200))
    excerpt = transcript_excerpt(text, 2000)
    assert len(excerpt) <= 2000
    assert excerpt.startswith("[00:00] S1: line 0")
    assert "line 1" in excerpt and any(f"line {i}" in excerpt for i in range(150, 200))


def test_a_short_transcript_is_the_excerpt_itself() -> None:
    assert transcript_excerpt("short", 100) == "short"


def test_candidates_render_one_line_each_with_ref_category_name_and_description() -> None:
    lines = render_candidates([DEFAULT, MEDICAL]).splitlines()
    assert lines[0].startswith(f"- {DEFAULT.ref} | meeting | Minutes")
    assert lines[1] == f"- {MEDICAL.ref} | meeting | Medical: For doctors."


# ---------------------------------------------------------------- precedence


async def test_an_explicit_meeting_choice_wins_without_a_model_call(
    fake_service: MagicMock, fake_llm: AsyncMock
) -> None:
    decision = await _decide(_meeting(template_ref=str(MINE.ref)))
    assert decision.selection is TemplateSelection.USER
    assert str(decision.ref) == str(MINE.ref) and decision.name == "Mine"
    assert [s.key for s in decision.sections] == ["notes"]
    fake_llm.assert_not_awaited()


async def test_the_preference_wins_next_without_a_model_call(
    fake_service: MagicMock, fake_llm: AsyncMock
) -> None:
    preference = SimpleNamespace(default_template_ref=str(MEDICAL.ref))
    decision = await _decide(_meeting(), preference)
    assert decision.selection is TemplateSelection.PREFERENCE
    assert str(decision.ref) == str(MEDICAL.ref) and decision.reason is None
    fake_llm.assert_not_awaited()


async def test_a_dangling_explicit_ref_falls_through_to_the_preference(
    fake_service: MagicMock, fake_llm: AsyncMock
) -> None:
    preference = SimpleNamespace(default_template_ref=str(MEDICAL.ref))
    decision = await _decide(_meeting(template_ref=f"user:{uuid.uuid4()}"), preference)
    assert decision.selection is TemplateSelection.PREFERENCE
    assert str(decision.ref) == str(MEDICAL.ref)


async def test_automatic_selection_keeps_a_confident_candidate_and_counts_it(
    fake_service: MagicMock, fake_llm: AsyncMock
) -> None:
    before = _outcome("auto")
    capture = MagicMock()
    decision = await _decide(_meeting(), None, capture)
    assert decision.selection is TemplateSelection.AUTO
    assert str(decision.ref) == str(MEDICAL.ref)
    assert [s.key for s in decision.sections] == ["findings", "treatment"]
    assert decision.reason == "A doctor speaks."
    assert _outcome("auto") == before + 1
    # The excerpt, the candidates and the calendar hint reach the model; the capture rides along.
    messages = fake_llm.await_args.args[1]
    human = messages[-1].content
    assert "CANDIDATES:" in human and str(MEDICAL.ref) in human and "Point projet" in human
    assert "EXCERPT:" in human and "turn 0" in human
    assert fake_llm.await_args.kwargs["config"]["callbacks"] == [capture]


async def test_a_hesitant_model_falls_back_to_the_default_and_says_why(
    fake_service: MagicMock, fake_llm: AsyncMock
) -> None:
    fake_llm.return_value = TemplateChoice(
        template_ref=str(MEDICAL.ref), confidence=0.3, reason="maybe"
    )
    before = _outcome("fallback")
    decision = await _decide(_meeting())
    assert decision.selection is TemplateSelection.AUTO
    assert str(decision.ref) == str(DEFAULT.ref)
    assert decision.reason is not None and "0.3" in decision.reason
    assert _outcome("fallback") == before + 1


async def test_a_ref_outside_the_candidates_falls_back(
    fake_service: MagicMock, fake_llm: AsyncMock
) -> None:
    fake_llm.return_value = TemplateChoice(
        template_ref="builtin:invented", confidence=0.99, reason="x"
    )
    decision = await _decide(_meeting())
    assert str(decision.ref) == str(DEFAULT.ref) and decision.selection is TemplateSelection.AUTO


async def test_a_model_failure_never_fails_the_meeting(
    fake_service: MagicMock, fake_llm: AsyncMock
) -> None:
    fake_llm.side_effect = StructuredOutputError("no answer", "openai", "TemplateChoice")
    before = _outcome("fallback")
    decision = await _decide(_meeting())
    assert str(decision.ref) == str(DEFAULT.ref) and decision.selection is TemplateSelection.AUTO
    assert _outcome("fallback") == before + 1


async def test_disabled_automatic_selection_applies_the_default_as_a_preference(
    fake_service: MagicMock, fake_llm: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "meetings_template_auto_select_enabled", False)
    decision = await _decide(_meeting())
    assert decision.selection is TemplateSelection.PREFERENCE and decision.reason is None
    assert str(decision.ref) == str(DEFAULT.ref)
    fake_llm.assert_not_awaited()


# ---------------------------------------------------------------- regeneration


async def test_regeneration_uses_the_meetings_own_template_when_it_still_exists(
    fake_service: MagicMock,
) -> None:
    meeting = _meeting(
        template_ref=str(MINE.ref),
        template_name="Old name",
        template_selection="user",
        template_snapshot=[{"key": "old", "label": "Old", "instruction": "i", "kind": "bullets"}],
    )
    decision = await template_for_regeneration(MagicMock(), meeting=meeting, language="fr")
    assert [s.key for s in decision.sections] == ["notes"] and decision.name == "Mine"
    assert decision.selection is TemplateSelection.USER


async def test_regeneration_falls_back_to_the_snapshot_when_the_template_is_gone(
    fake_service: MagicMock,
) -> None:
    gone = f"user:{uuid.uuid4()}"
    meeting = _meeting(
        template_ref=gone,
        template_name="Gone but named",
        template_selection="preference",
        template_snapshot=[{"key": "old", "label": "Old", "instruction": "i", "kind": "bullets"}],
    )
    decision = await template_for_regeneration(MagicMock(), meeting=meeting, language="fr")
    assert [s.key for s in decision.sections] == ["old"]
    assert decision.name == "Gone but named" and str(decision.ref) == gone
    assert decision.selection is TemplateSelection.PREFERENCE


async def test_regeneration_of_a_historical_meeting_uses_its_snapshot_and_the_default_name(
    fake_service: MagicMock,
) -> None:
    meeting = _meeting(
        template_snapshot=[{"key": "old", "label": "Old", "instruction": "i", "kind": "bullets"}]
    )
    decision = await template_for_regeneration(MagicMock(), meeting=meeting, language="fr")
    assert [s.key for s in decision.sections] == ["old"]
    assert decision.name == "Compte rendu de réunion"
    assert str(decision.ref) == str(DEFAULT.ref)
