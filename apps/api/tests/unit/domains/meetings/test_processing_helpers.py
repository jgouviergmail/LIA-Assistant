"""The processing job's pure parts and its failure classification (ADR-258)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.core.config import settings
from src.domains.meetings import processing
from src.domains.meetings.models import MeetingStatus, MeetingSttProvider
from src.domains.meetings.processing import (
    _completion_values,
    _fail,
    _keep_audio_until,
    _language_hint,
    _summary_text,
    _template_sections,
)
from src.domains.meetings.schemas import (
    ActionItem,
    MeetingReport,
    ReportSection,
    SectionKind,
    TemplateSection,
    TranscriptTurn,
)
from src.domains.meetings.synthesis import SynthesisResult, SynthesisUsage
from src.domains.meetings.transcription import TranscriptionOutcome

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 2, 10, 0, tzinfo=UTC)


def test_keep_audio_until_is_none_for_zero_and_capped_by_the_admin_ceiling() -> None:
    assert _keep_audio_until(None, NOW) is None
    assert _keep_audio_until(SimpleNamespace(keep_audio_hours=0), NOW) is None
    assert _keep_audio_until(SimpleNamespace(keep_audio_hours=2), NOW) == NOW + timedelta(hours=2)
    ceiling = settings.meetings_audio_retention_hours_max
    assert _keep_audio_until(
        SimpleNamespace(keep_audio_hours=ceiling + 500), NOW
    ) == NOW + timedelta(hours=ceiling)


def test_language_hint_prefers_the_meeting_then_the_preference_and_drops_auto() -> None:
    assert _language_hint(None, SimpleNamespace(stt_language_hint="de")) == "de"
    assert (
        _language_hint(SimpleNamespace(language="fr"), SimpleNamespace(stt_language_hint=None))
        == "fr"
    )
    assert (
        _language_hint(SimpleNamespace(language="auto"), SimpleNamespace(stt_language_hint=None))
        is None
    )
    assert _language_hint(None, SimpleNamespace(stt_language_hint=None)) is None


def test_summary_text_takes_the_first_paragraph_then_the_first_bullets() -> None:
    bullets = ReportSection(
        key="decisions", label="D", kind=SectionKind.BULLETS, bullets=["a", "b"]
    )
    paragraph = ReportSection(
        key="summary", label="S", kind=SectionKind.PARAGRAPH, paragraph="Résumé."
    )
    assert _summary_text(MeetingReport(title="T", sections=[bullets, paragraph])) == "Résumé."
    assert _summary_text(MeetingReport(title="T", sections=[bullets])) == "- a\n- b"
    assert _summary_text(MeetingReport(title="T", sections=[])) == ""


def test_template_sections_read_the_row_or_fall_back_to_the_localized_default() -> None:
    row = SimpleNamespace(
        sections=[{"key": "extra", "label": "X", "instruction": "i", "kind": "bullets"}]
    )
    assert [s.key for s in _template_sections(row, "fr")] == ["extra"]
    default = _template_sections(None, "fr")
    assert default[0].label == "Résumé" and default[0].kind is SectionKind.PARAGRAPH


def test_completion_values_carry_every_derived_fact_and_encrypt_the_transcript(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(processing, "encrypt_data", lambda text: f"enc:{text}")
    monkeypatch.setattr(processing, "get_cached_cost_usd_eur", lambda **kwargs: (0.0023, 0.0021))
    monkeypatch.setattr(processing.settings, "rag_spaces_enabled", True)
    turns = [TranscriptTurn(speaker="S1", start=0, end=1, text="Bonjour")]
    outcome = TranscriptionOutcome(
        turns=turns,
        language_code="fr",
        audio_duration_seconds=61.5,
        provider=MeetingSttProvider.OPENAI,
        model="gpt-4o-transcribe-diarize",
        diarized=True,
        cost_usd=0.01,
        cost_eur=0.009,
    )
    report = MeetingReport(
        title="T",
        sections=[
            ReportSection(
                key="actions",
                label="A",
                kind=SectionKind.ACTION_ITEMS,
                action_items=[ActionItem(description="x")],
            )
        ],
    )
    synthesis = SynthesisResult(
        report=report, usage=SynthesisUsage(1, 2, 3, "gpt-4.1"), condensed=False
    )
    template = [
        TemplateSection(key="actions", label="A", instruction="i", kind=SectionKind.ACTION_ITEMS)
    ]
    calendar = SimpleNamespace(
        event_id="evt-1", provider="google_calendar", title="P", attendees=[], location=None
    )
    values = _completion_values(
        meeting=SimpleNamespace(calendar_event_id=None, calendar_provider=None),
        audio_path="u/m/audio.webm",
        duration=61.5,
        outcome=outcome,
        synthesis=synthesis,
        template=template,
        calendar=calendar,
        location_label="Salle B",
        keep_audio_until=None,
        gaps=2,
    )
    assert values["audio_path"] == "u/m/audio.webm" and values["audio_gaps"] == 2
    assert values["stt_provider"] is MeetingSttProvider.OPENAI and values["stt_diarized"] is True
    assert values["stt_cost_eur"] == 0.009 and values["stt_detected_language"] == "fr"
    assert (
        values["calendar_event_id"] == "evt-1" and values["calendar_provider"] == "google_calendar"
    )
    assert values["location_label"] == "Salle B" and values["keep_audio_until"] is None
    # The minutes' own spend rides on the row (model, tokens, priced cost).
    assert values["synthesis_model"] == "gpt-4.1"
    assert (
        values["synthesis_tokens_in"],
        values["synthesis_tokens_out"],
        values["synthesis_tokens_cache"],
    ) == (1, 2, 3)
    assert values["synthesis_cost_eur"] == 0.0021
    assert values["template_snapshot"] == [
        {"key": "actions", "label": "A", "instruction": "i", "kind": "action_items"}
    ]
    assert values["report_generated"] == values["report_current"] == report.model_dump(mode="json")
    assert values["report_edited_at"] is None
    assert json.loads(values["transcript_encrypted"].removeprefix("enc:")) == [
        turns[0].model_dump()
    ]
    assert values["index_state"].value == "pending"


async def test_fail_retries_transient_causes_and_dead_letters_permanent_ones() -> None:
    repo = AsyncMock()
    repo.fail_or_retry.return_value = MeetingStatus.STOPPED
    job = SimpleNamespace(meeting_id=uuid.uuid4())
    await _fail(repo, job, code="provider_timeout", message="x" * 2000, transient=True)  # type: ignore[arg-type]
    repo.fail_or_retry.assert_awaited_once()
    assert len(repo.fail_or_retry.call_args.kwargs["message"]) == 1000
    assert repo.fail_or_retry.call_args.kwargs["max_attempts"] == settings.meetings_job_max_attempts
    repo.fail_permanently.assert_not_awaited()

    repo.reset_mock()
    await _fail(repo, job, code="no_speech", message="silence", transient=False)  # type: ignore[arg-type]
    repo.fail_permanently.assert_awaited_once()
    repo.fail_or_retry.assert_not_awaited()


async def test_process_meeting_does_nothing_when_another_worker_won_the_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = AsyncMock()
    repo.claim_stopped.return_value = False

    class _Ctx:
        async def __aenter__(self) -> Any:
            return object()

        async def __aexit__(self, *exc: Any) -> None:
            return None

    monkeypatch.setattr(processing, "get_db_context", lambda: _Ctx())
    monkeypatch.setattr(processing, "MeetingRepository", lambda db: repo)
    await processing.process_meeting(uuid.uuid4())
    repo.claim_stopped.assert_awaited_once()
    repo.get_by_id.assert_not_awaited()


class TestSynthesisCost:
    """An unknown price is None, a free pass is 0.0, a priced pass is its EUR figure."""

    def test_a_priced_model_gives_its_eur_cost(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: dict[str, object] = {}

        def _cost(**kwargs: object) -> tuple[float, float]:
            seen.update(kwargs)
            return (0.011, 0.0094)

        monkeypatch.setattr(processing, "get_cached_cost_usd_eur", _cost)
        assert processing.synthesis_cost_eur(SynthesisUsage(1200, 300, 100, "gpt-4.1")) == 0.0094
        assert seen == {
            "model": "gpt-4.1",
            "prompt_tokens": 1200,
            "completion_tokens": 300,
            "cached_tokens": 100,
        }

    def test_an_unpriced_model_gives_none_not_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(processing, "get_cached_cost_usd_eur", lambda **kwargs: (0.0, 0.0))
        assert processing.synthesis_cost_eur(SynthesisUsage(10, 5, 0, "unknown-model")) is None

    def test_a_pass_without_tokens_is_an_exact_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(processing, "get_cached_cost_usd_eur", lambda **kwargs: (0.0, 0.0))
        assert processing.synthesis_cost_eur(SynthesisUsage(0, 0, 0, "gpt-4.1")) == 0.0


class TestCostMetadata:
    """The notification carries both paid units and their honest sum."""

    def test_both_units_priced_sum_into_cost_eur(self) -> None:
        meeting = SimpleNamespace(synthesis_cost_eur=0.0121)
        outcome = _outcome(cost_eur=0.0046)
        meta = processing._cost_metadata(meeting, outcome, SynthesisUsage(1200, 300, 0, "gpt-4.1"))
        assert meta["tokens_in"] == 1200 and meta["model_name"] == "gpt-4.1"
        assert meta["llm_cost_eur"] == 0.0121 and meta["stt_cost_eur"] == 0.0046
        assert meta["stt_audio_duration_seconds"] == 61.5
        assert meta["cost_eur"] == 0.0167

    def test_an_unknown_price_neither_hides_the_other_nor_reads_as_free(self) -> None:
        only_stt = processing._cost_metadata(
            SimpleNamespace(synthesis_cost_eur=None),
            _outcome(cost_eur=0.0046),
            SynthesisUsage(1, 1, 0, "m"),
        )
        assert only_stt["cost_eur"] == 0.0046 and only_stt["llm_cost_eur"] is None
        nothing = processing._cost_metadata(
            SimpleNamespace(synthesis_cost_eur=None),
            _outcome(cost_eur=None),
            SynthesisUsage(1, 1, 0, "m"),
        )
        assert nothing["cost_eur"] is None


def _outcome(*, cost_eur: float | None) -> TranscriptionOutcome:
    return TranscriptionOutcome(
        turns=[],
        language_code="fr",
        audio_duration_seconds=61.5,
        provider=MeetingSttProvider.OPENAI,
        model="gpt-4o-transcribe-diarize",
        diarized=True,
        cost_usd=None if cost_eur is None else cost_eur * 1.1,
        cost_eur=cost_eur,
    )
