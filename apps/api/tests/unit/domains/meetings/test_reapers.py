"""Meetings reapers (ADR-258): thresholds come from settings, transitions are counted."""

from __future__ import annotations

import contextlib
import uuid
from types import SimpleNamespace

import pytest

import src.domains.meetings.reapers as rp
from src.core.config import settings

pytestmark = pytest.mark.unit


def _install_db(monkeypatch: pytest.MonkeyPatch, repo_cls: type) -> dict:
    captured: dict = {}

    async def _commit() -> None:
        captured["committed"] = True

    @contextlib.asynccontextmanager
    async def _ctx():
        yield SimpleNamespace(commit=_commit)

    monkeypatch.setattr(rp, "MeetingRepository", repo_cls)
    monkeypatch.setattr(rp, "get_db_context", _ctx)
    return captured


async def test_job_reaper_uses_settings_thresholds_and_redrives_orphans(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict = {}
    orphan = uuid.uuid4()

    class _Repo:
        def __init__(self, db) -> None:  # noqa: ANN001
            pass

        async def interrupt_stale_recordings(self, stale_minutes: int) -> int:
            seen["stale"] = stale_minutes
            return 2

        async def fail_stale_imports(self, stale_minutes: int) -> list:
            seen["import_stale"] = stale_minutes
            return []

        async def requeue_expired_leases(self, max_attempts: int) -> tuple[int, int]:
            seen["max_attempts"] = max_attempts
            return 1, 0

        async def fetch_stopped_orphans(self, grace_seconds: int, limit: int) -> list[uuid.UUID]:
            seen["grace"] = grace_seconds
            return [orphan]

        async def clear_stale_regenerations(self, older_than_seconds: int) -> int:
            seen["stale_regen"] = older_than_seconds
            return 1

    launched: list[uuid.UUID] = []
    import src.domains.meetings.processing as processing

    monkeypatch.setattr(processing, "launch_processing", lambda mid: launched.append(mid))
    db = _install_db(monkeypatch, _Repo)

    await rp.meetings_job_reaper()

    assert seen["stale"] == settings.meetings_recording_stale_minutes  # never hard-coded
    assert seen["import_stale"] == settings.meetings_import_stale_minutes
    assert seen["grace"] == settings.meetings_reaper_interval_seconds
    assert seen["max_attempts"] == settings.meetings_job_max_attempts
    # ADR-259: a regeneration killed mid-flight is cleared after the lease TTL.
    assert seen["stale_regen"] == settings.meetings_job_lease_ttl_seconds
    assert launched == [orphan]
    assert db["committed"] is True


async def test_job_reaper_counts_the_workers_it_dead_letters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An expired lease past the retry budget is dead-lettered by the reaper itself.

    Re-driving it would spend an attempt the budget no longer has; the row
    must reach ``failed`` with a reason the user can read.
    """
    from src.infrastructure.observability.metrics_meetings import (
        meeting_reaper_transitions_total,
    )

    class _Repo:
        def __init__(self, db) -> None:  # noqa: ANN001
            pass

        async def interrupt_stale_recordings(self, stale_minutes: int) -> int:
            return 0

        async def fail_stale_imports(self, stale_minutes: int) -> list:
            return []

        async def requeue_expired_leases(self, max_attempts: int) -> tuple[int, int]:
            return 1, 2

        async def fetch_stopped_orphans(self, grace_seconds: int, limit: int) -> list[uuid.UUID]:
            return []

        async def clear_stale_regenerations(self, older_than_seconds: int) -> int:
            return 0

    _install_db(monkeypatch, _Repo)
    requeued = meeting_reaper_transitions_total.labels(outcome="requeued")
    dead_lettered = meeting_reaper_transitions_total.labels(outcome="dead_lettered")
    before = (requeued._value.get(), dead_lettered._value.get())

    await rp.meetings_job_reaper()

    assert requeued._value.get() == before[0] + 1
    assert dead_lettered._value.get() == before[1] + 2


async def test_job_reaper_fails_silent_imports_then_deletes_their_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A half file is no meeting: failed by the sweep, its chunks deleted AFTER the commit."""
    from src.domains.meetings.models import MeetingAudioFormat
    from src.infrastructure.observability.metrics_meetings import meeting_imports_total

    meeting_id, user_id = uuid.uuid4(), uuid.uuid4()
    marked: list[uuid.UUID] = []
    purged: list[tuple[uuid.UUID, uuid.UUID]] = []

    class _Repo:
        def __init__(self, db) -> None:  # noqa: ANN001
            pass

        async def interrupt_stale_recordings(self, stale_minutes: int) -> int:
            return 0

        async def fail_stale_imports(self, stale_minutes: int) -> list:
            return [(meeting_id, user_id, MeetingAudioFormat.IMPORT_MP3)]

        async def requeue_expired_leases(self, max_attempts: int) -> tuple[int, int]:
            return 0, 0

        async def fetch_stopped_orphans(self, grace_seconds: int, limit: int) -> list[uuid.UUID]:
            return []

        async def clear_stale_regenerations(self, older_than_seconds: int) -> int:
            return 0

        async def mark_audio_purged(
            self, meeting_id: uuid.UUID, *, purged_at
        ) -> None:  # noqa: ANN001
            marked.append(meeting_id)

    class _Store:
        def __init__(self, root) -> None:  # noqa: ANN001
            pass

        async def purge_meeting(self, owner: uuid.UUID, meeting: uuid.UUID) -> bool:
            purged.append((owner, meeting))
            return True

    _install_db(monkeypatch, _Repo)
    monkeypatch.setattr(rp, "MeetingAudioStore", _Store)
    abandoned = meeting_imports_total.labels(format="import_mp3", outcome="abandoned")
    before = abandoned._value.get()

    await rp.meetings_job_reaper()

    assert purged == [(user_id, meeting_id)]
    assert marked == [meeting_id]
    assert abandoned._value.get() == before + 1


@pytest.mark.parametrize("cleanup_succeeded", [True, False])
async def test_retention_reaper_purges_files_then_marks_the_row(
    monkeypatch: pytest.MonkeyPatch,
    cleanup_succeeded: bool,
) -> None:
    meeting = SimpleNamespace(id=uuid.uuid4(), user_id=uuid.uuid4())
    marked: list[uuid.UUID] = []
    purged: list[tuple[uuid.UUID, uuid.UUID]] = []

    class _Repo:
        def __init__(self, db) -> None:  # noqa: ANN001
            pass

        async def fetch_audio_to_purge(self, limit: int) -> list:
            return [meeting]

        async def mark_audio_purged(
            self, meeting_id: uuid.UUID, *, purged_at
        ) -> None:  # noqa: ANN001
            marked.append(meeting_id)

    class _Store:
        def __init__(self, root) -> None:  # noqa: ANN001
            pass

        async def purge_meeting(self, user_id: uuid.UUID, meeting_id: uuid.UUID) -> bool:
            purged.append((user_id, meeting_id))
            return cleanup_succeeded

    monkeypatch.setattr(rp, "MeetingAudioStore", _Store)
    _install_db(monkeypatch, _Repo)

    await rp.meetings_audio_retention_reaper()

    assert purged == [(meeting.user_id, meeting.id)]
    assert marked == ([meeting.id] if cleanup_succeeded else [])
