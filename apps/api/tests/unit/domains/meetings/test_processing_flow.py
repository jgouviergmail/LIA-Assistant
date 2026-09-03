"""The processing job and the regeneration job, classified end to end (ADR-258).

Everything below the job — repositories, the LLM, the engines — is a double;
what is under test is the CONTRACT of the job: which failure lands where,
what a lost lease forbids, and that a stage is never left dangling.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.meetings import processing, regeneration
from src.domains.meetings.models import MeetingStage, MeetingStatus, MeetingSttProvider
from src.domains.meetings.processing import LeaseLostError, process_meeting
from src.domains.meetings.regeneration import regenerate_minutes
from src.domains.meetings.schemas import MeetingReport, TemplateSelection
from src.domains.meetings.synthesis import SynthesisResult, SynthesisUsage
from src.domains.meetings.template_ref import TemplateRef
from src.domains.meetings.template_resolution import TemplateDecision
from src.domains.meetings.transcription import TranscriptionError
from src.infrastructure.llm.structured_output import StructuredOutputError

pytestmark = pytest.mark.unit


@pytest.fixture
def db_context(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """``get_db_context`` yields one MagicMock session (nothing here awaits it)."""
    db = MagicMock()

    @asynccontextmanager
    async def _ctx():
        yield db

    monkeypatch.setattr(processing, "get_db_context", _ctx)
    monkeypatch.setattr(regeneration, "get_db_context", _ctx)
    return db


@pytest.fixture
def repo(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    instance = AsyncMock()
    monkeypatch.setattr(processing, "MeetingRepository", MagicMock(return_value=instance))
    monkeypatch.setattr(regeneration, "MeetingRepository", MagicMock(return_value=instance))
    return instance


def _meeting(**overrides: Any) -> MagicMock:
    meeting = MagicMock()
    meeting.id = uuid.uuid4()
    meeting.user_id = uuid.uuid4()
    meeting.attempts = 1
    meeting.segment_count = 3
    meeting.status = MeetingStatus.PROCESSING
    meeting.stage = MeetingStage.SYNTHESIZING
    meeting.transcript_encrypted = "ciphertext"
    meeting.client_timezone = "Europe/Paris"
    meeting.audio_gaps = 0
    meeting.audio_duration_seconds = 90.0
    meeting.location_label = None
    meeting.stt_diarized = True
    for key, value in overrides.items():
        setattr(meeting, key, value)
    return meeting


# ----------------------------------------------------------------- process


class TestProcessMeeting:
    async def test_a_lost_claim_touches_nothing(
        self, db_context: MagicMock, repo: AsyncMock
    ) -> None:
        repo.claim_stopped.return_value = False
        await process_meeting(uuid.uuid4())
        repo.get_by_id.assert_not_awaited()
        repo.fail_or_retry.assert_not_awaited()

    @pytest.mark.parametrize(
        ("raised", "code", "transient"),
        [
            (
                TranscriptionError("provider_rate_limited", "429", transient=True),
                "provider_rate_limited",
                True,
            ),
            (TranscriptionError("no_speech", "silence", transient=False), "no_speech", False),
            (
                StructuredOutputError("bad json", "openai", "MeetingReport"),
                processing.ERROR_SYNTHESIS,
                True,
            ),
            (RuntimeError("boom"), processing.ERROR_UNEXPECTED, True),
        ],
    )
    async def test_each_failure_lands_on_the_row_with_its_class(
        self,
        db_context: MagicMock,
        repo: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
        raised: Exception,
        code: str,
        transient: bool,
    ) -> None:
        repo.claim_stopped.return_value = True
        repo.get_by_id.return_value = _meeting()
        repo.fail_or_retry.return_value = MeetingStatus.STOPPED
        monkeypatch.setattr(processing, "_run", AsyncMock(side_effect=raised))
        await process_meeting(uuid.uuid4())
        if transient:
            repo.fail_or_retry.assert_awaited_once()
            assert repo.fail_or_retry.await_args.kwargs["code"] == code
            repo.fail_permanently.assert_not_awaited()
        else:
            repo.fail_permanently.assert_awaited_once()
            assert repo.fail_permanently.await_args.kwargs["code"] == code
            repo.fail_or_retry.assert_not_awaited()

    async def test_a_lost_lease_writes_no_verdict(
        self, db_context: MagicMock, repo: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo.claim_stopped.return_value = True
        repo.get_by_id.return_value = _meeting()
        monkeypatch.setattr(processing, "_run", AsyncMock(side_effect=LeaseLostError("gone")))
        await process_meeting(uuid.uuid4())
        repo.fail_or_retry.assert_not_awaited()
        repo.fail_permanently.assert_not_awaited()


# -------------------------------------------------------------- regenerate


def _synthesis() -> SynthesisResult:
    report = MeetingReport(title="Rebuilt", participants=[], sections=[])
    return SynthesisResult(
        report=report,
        usage=SynthesisUsage(tokens_in=1, tokens_out=1, tokens_cache=0, model_name="m"),
        condensed=False,
    )


@pytest.fixture
def regenerate_world(
    monkeypatch: pytest.MonkeyPatch, db_context: MagicMock, repo: AsyncMock
) -> dict[str, Any]:
    """Template repo, user repo, transcript and reindex are doubles; the LLM is scripted."""
    decision = TemplateDecision(
        sections=[],
        ref=TemplateRef.builtin("default_minutes"),
        name="Minutes",
        selection=TemplateSelection.PREFERENCE,
        reason=None,
    )
    monkeypatch.setattr(regeneration, "template_for_regeneration", AsyncMock(return_value=decision))
    user_repo = AsyncMock()
    user_repo.get_by_id.return_value = MagicMock(language="fr")
    monkeypatch.setattr(
        "src.domains.users.repository.UserRepository", MagicMock(return_value=user_repo)
    )
    monkeypatch.setattr(
        "src.domains.meetings.service.MeetingService.decrypt_transcript",
        staticmethod(lambda _encrypted: []),
    )
    reindex = MagicMock()
    monkeypatch.setattr("src.domains.meetings.indexing.schedule_reindex", reindex)
    synthesize = AsyncMock(return_value=_synthesis())
    monkeypatch.setattr(regeneration, "synthesize_minutes", synthesize)
    tracked = AsyncMock(return_value="run-1")
    monkeypatch.setattr("src.infrastructure.proactive.tracking.track_proactive_tokens", tracked)
    monkeypatch.setattr(processing, "get_cached_cost_usd_eur", lambda **kwargs: (0.002, 0.0017))
    return {"repo": repo, "reindex": reindex, "synthesize": synthesize, "tracked": tracked}


class TestRegenerateMinutes:
    async def test_new_minutes_replace_both_copies_and_reindex(
        self, regenerate_world: dict[str, Any]
    ) -> None:
        repo = regenerate_world["repo"]
        repo.get_by_id.return_value = _meeting()
        await regenerate_minutes(uuid.uuid4())
        repo.finish_regenerate.assert_awaited_once()
        values = repo.finish_regenerate.await_args.kwargs["values"]
        assert values["report_generated"] == values["report_current"]
        assert values["report_generated"]["title"] == "Rebuilt"
        assert values["report_edited_at"] is None
        # The rebuild is paid: tracked for the platform, added to the meeting's total.
        regenerate_world["tracked"].assert_awaited_once()
        assert regenerate_world["tracked"].await_args.kwargs["tokens_in"] == 1
        spend = repo.finish_regenerate.await_args.kwargs
        assert (spend["tokens_in"], spend["tokens_out"], spend["tokens_cache"]) == (1, 1, 0)
        assert spend["cost_eur"] == 0.0017 and values["synthesis_model"] == "m"
        # The meeting's own template (ADR-259) wrote the rebuild, and the row says so.
        assert values["template_ref"] == "builtin:default_minutes"
        assert values["template_name"] == "Minutes" and values["template_selection"] == "preference"
        regenerate_world["reindex"].assert_called_once()

    async def test_a_row_not_in_regeneration_is_left_alone(
        self, regenerate_world: dict[str, Any]
    ) -> None:
        repo = regenerate_world["repo"]
        repo.get_by_id.return_value = _meeting(stage=None)
        await regenerate_minutes(uuid.uuid4())
        regenerate_world["synthesize"].assert_not_awaited()
        repo.finish_regenerate.assert_not_awaited()
        repo.fail_regenerate.assert_not_awaited()

    async def test_a_purged_transcript_fails_before_the_model(
        self, regenerate_world: dict[str, Any]
    ) -> None:
        repo = regenerate_world["repo"]
        repo.get_by_id.return_value = _meeting(transcript_encrypted=None)
        await regenerate_minutes(uuid.uuid4())
        regenerate_world["synthesize"].assert_not_awaited()
        assert repo.fail_regenerate.await_args.kwargs["code"] == "transcript_unavailable"

    @pytest.mark.parametrize(
        ("raised", "code"),
        [
            (
                StructuredOutputError("bad json", "openai", "MeetingReport"),
                regeneration.ERROR_SYNTHESIS,
            ),
            (RuntimeError("provider down"), regeneration.ERROR_UNEXPECTED),
        ],
    )
    async def test_any_failure_clears_the_stage_and_keeps_the_old_minutes(
        self, regenerate_world: dict[str, Any], raised: Exception, code: str
    ) -> None:
        """A stage left at SYNTHESIZING answers ``regeneration_in_progress`` forever."""
        repo = regenerate_world["repo"]
        repo.get_by_id.return_value = _meeting()
        regenerate_world["synthesize"].side_effect = raised
        await regenerate_minutes(uuid.uuid4())
        repo.finish_regenerate.assert_not_awaited()
        repo.fail_regenerate.assert_awaited_once()
        assert repo.fail_regenerate.await_args.kwargs["code"] == code
        regenerate_world["reindex"].assert_not_called()


class TestAfterReadyGuard:
    async def test_a_post_ready_failure_never_reaches_the_classifier(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The row is READY once ``complete`` returned; a notification or indexing
        failure is logged, not turned into a failed meeting."""
        monkeypatch.setattr(
            processing, "_after_ready", AsyncMock(side_effect=RuntimeError("notifier down"))
        )
        await processing._after_ready_guarded(
            uuid.uuid4(), synthesis=None, outcome=None, preference=None, language="fr", gaps=0
        )

    async def test_the_effects_run_with_the_arguments_given(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        inner = AsyncMock()
        monkeypatch.setattr(processing, "_after_ready", inner)
        meeting_id = uuid.uuid4()
        await processing._after_ready_guarded(meeting_id, language="fr", gaps=2)
        inner.assert_awaited_once_with(meeting_id, language="fr", gaps=2)


class TestNotifyReady:
    """The archived message links to the token log and states what the exchange cost."""

    async def test_metadata_carries_run_id_tokens_and_both_costs(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.domains.meetings.transcription import TranscriptionOutcome

        tracked = AsyncMock(return_value="meeting-run")
        monkeypatch.setattr("src.infrastructure.proactive.tracking.track_proactive_tokens", tracked)
        monkeypatch.setattr(
            "src.infrastructure.proactive.tracking.generate_proactive_run_id",
            lambda task_type, target: f"{task_type}-{target}-run",
        )
        dispatcher = MagicMock()
        dispatcher.dispatch = AsyncMock()
        monkeypatch.setattr(
            "src.infrastructure.proactive.notification.NotificationDispatcher",
            MagicMock(return_value=dispatcher),
        )
        meeting = _meeting(synthesis_cost_eur=0.0121, index_state=None)
        outcome = TranscriptionOutcome(
            turns=[],
            language_code="fr",
            audio_duration_seconds=53.3,
            provider=MeetingSttProvider.OPENAI,
            model="gpt-4o-transcribe-diarize",
            diarized=True,
            cost_usd=0.005,
            cost_eur=0.0046,
        )
        synthesis = _synthesis()
        await processing._notify_ready(
            MagicMock(),
            meeting=meeting,
            user=MagicMock(),
            synthesis=synthesis,
            outcome=outcome,
            language="fr",
            gaps=0,
        )
        run_id = f"{processing.MEETINGS_PROACTIVE_TASK_TYPE}-{meeting.id}-run"
        assert tracked.await_args.kwargs["run_id"] == run_id
        kwargs = dispatcher.dispatch.await_args.kwargs
        assert kwargs["run_id"] == run_id
        meta = kwargs["metadata"]
        assert (meta["tokens_in"], meta["tokens_out"], meta["model_name"]) == (1, 1, "m")
        assert meta["stt_cost_eur"] == 0.0046 and meta["llm_cost_eur"] == 0.0121
        assert meta["cost_eur"] == 0.0167 and meta["stt_audio_duration_seconds"] == 53.3
