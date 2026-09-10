"""Removing a generated file, and what the answer may claim (ADR-279).

Two claims are pinned here, because both were wrong somewhere before:

- **« deleted » means gone.** An id the caller does not own, an id that is an
  UPLOAD, and an id the retention sweep removed between the listing and the
  click are all SKIPPED — never folded into the deleted count (ADR-185).
- **Why a file went is recorded on the one label the dashboard groups by.**
  Before this, a person emptying their gallery was indistinguishable from a
  conversation reset, and the panel showed one line for two very different
  events.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from prometheus_client import CollectorRegistry, Counter

from src.domains.attachments.models import AttachmentOrigin
from src.domains.attachments.service import AttachmentService

pytestmark = pytest.mark.unit

_USER = uuid.UUID("11111111-1111-4111-8111-111111111111")
_OTHER = uuid.UUID("22222222-2222-4222-8222-222222222222")


class _Row:
    """The three columns the deletion reads. A full ORM row proves nothing more."""

    def __init__(self, row_id: uuid.UUID, origin: str) -> None:
        self.id = row_id
        self.origin = origin
        self.file_path = f"/tmp/{row_id}.bin"


class _Repo:
    """Owns nothing but the rows it was handed."""

    def __init__(self, rows: list[_Row]) -> None:
        self._rows = rows
        self.deleted: list[uuid.UUID] = []

    async def get_owned_batch(self, ids: list[uuid.UUID], user_id: uuid.UUID) -> list[_Row]:
        wanted = set(ids)
        return [row for row in self._rows if row.id in wanted]

    async def delete(self, row: _Row) -> None:
        self.deleted.append(row.id)


class _Db:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


def _service(rows: list[_Row], monkeypatch: pytest.MonkeyPatch) -> tuple[AttachmentService, _Repo]:
    """A service whose repository and disk are stubs, and nothing else."""
    service = AttachmentService.__new__(AttachmentService)
    repo = _Repo(rows)
    service.db = _Db()  # type: ignore[assignment]
    service.repo = repo  # type: ignore[assignment]
    removed: list[str] = []
    monkeypatch.setattr(
        AttachmentService,
        "_remove_file_from_disk",
        lambda _self, path: removed.append(path),
    )
    service._removed_paths = removed  # type: ignore[attr-defined]
    return service, repo


@pytest.fixture
def counter(monkeypatch: pytest.MonkeyPatch) -> Counter:
    """The cleanup counter, on a registry of its own so nothing leaks between tests."""
    isolated = Counter(
        "attachments_cleanup_deleted_total",
        "test double",
        ["reason"],
        registry=CollectorRegistry(),
    )
    monkeypatch.setattr(
        "src.domains.attachments.service.attachments_cleanup_deleted_total", isolated
    )
    return isolated


def _value(counter: Counter, reason: str) -> float:
    raw: Any = counter.labels(reason=reason)._value.get()
    return float(raw)


class TestWhatABatchDeletionClaims:
    async def test_it_deletes_what_the_person_owns(
        self, monkeypatch: pytest.MonkeyPatch, counter: Counter
    ) -> None:
        mine = uuid.uuid4()
        service, repo = _service([_Row(mine, AttachmentOrigin.GENERATED_IMAGE.value)], monkeypatch)

        deleted, skipped = await service.delete_generated_batch(_USER, [mine])

        assert deleted == [mine]
        assert skipped == []
        assert repo.deleted == [mine]

    async def test_an_id_nobody_returned_is_skipped_never_counted(
        self, monkeypatch: pytest.MonkeyPatch, counter: Counter
    ) -> None:
        # The retention sweep removed it between the listing and the click.
        gone = uuid.uuid4()
        service, _ = _service([], monkeypatch)

        deleted, skipped = await service.delete_generated_batch(_USER, [gone])

        assert deleted == []
        assert skipped == [gone]

    async def test_an_upload_is_never_removed_from_the_gallery(
        self, monkeypatch: pytest.MonkeyPatch, counter: Counter
    ) -> None:
        # This surface never showed it: deleting it here would remove a file
        # the person attached to a conversation.
        upload = uuid.uuid4()
        service, repo = _service([_Row(upload, AttachmentOrigin.UPLOAD.value)], monkeypatch)

        deleted, skipped = await service.delete_generated_batch(_USER, [upload])

        assert deleted == []
        assert skipped == [upload]
        assert repo.deleted == []

    async def test_it_partitions_a_mixed_selection(
        self, monkeypatch: pytest.MonkeyPatch, counter: Counter
    ) -> None:
        ok, upload, gone = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        service, _ = _service(
            [
                _Row(ok, AttachmentOrigin.GENERATED_DOCUMENT.value),
                _Row(upload, AttachmentOrigin.UPLOAD.value),
            ],
            monkeypatch,
        )

        deleted, skipped = await service.delete_generated_batch(_USER, [ok, upload, gone])

        # Every id is in exactly one of the two lists: a caller must be able to
        # read the answer without recomputing it.
        assert deleted == [ok]
        assert sorted(skipped) == sorted([upload, gone])
        assert len(deleted) + len(skipped) == 3

    async def test_nothing_is_committed_when_nothing_went(
        self, monkeypatch: pytest.MonkeyPatch, counter: Counter
    ) -> None:
        service, _ = _service([], monkeypatch)

        await service.delete_generated_batch(_USER, [uuid.uuid4()])

        assert service.db.commits == 0  # type: ignore[attr-defined]

    async def test_the_file_leaves_the_disk_too(
        self, monkeypatch: pytest.MonkeyPatch, counter: Counter
    ) -> None:
        mine = uuid.uuid4()
        service, _ = _service([_Row(mine, AttachmentOrigin.BROWSER_SCREENSHOT.value)], monkeypatch)

        await service.delete_generated_batch(_USER, [mine])

        assert service._removed_paths == [f"/tmp/{mine}.bin"]  # type: ignore[attr-defined]


class TestWhyAFileWentIsRecorded:
    async def test_a_batch_counts_once_per_file_that_actually_went(
        self, monkeypatch: pytest.MonkeyPatch, counter: Counter
    ) -> None:
        ok_a, ok_b, gone = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        service, _ = _service(
            [
                _Row(ok_a, AttachmentOrigin.GENERATED_IMAGE.value),
                _Row(ok_b, AttachmentOrigin.GENERATED_IMAGE.value),
            ],
            monkeypatch,
        )

        await service.delete_generated_batch(_USER, [ok_a, ok_b, gone])

        # Two, not three: the counter says what LEFT, like the answer does.
        assert _value(counter, "user_deleted") == 2.0

    async def test_an_empty_batch_counts_nothing(
        self, monkeypatch: pytest.MonkeyPatch, counter: Counter
    ) -> None:
        service, _ = _service([], monkeypatch)

        await service.delete_generated_batch(_USER, [uuid.uuid4()])

        assert _value(counter, "user_deleted") == 0.0

    async def test_a_person_emptying_their_gallery_is_not_a_conversation_reset(
        self, monkeypatch: pytest.MonkeyPatch, counter: Counter
    ) -> None:
        mine = uuid.uuid4()
        service, _ = _service([_Row(mine, AttachmentOrigin.GENERATED_IMAGE.value)], monkeypatch)

        await service.delete_generated_batch(_USER, [mine])

        # The dashboard groups on this label; one line for two events is what
        # this separation exists to prevent.
        assert _value(counter, "conversation_reset") == 0.0
        assert _value(counter, "expired") == 0.0


class TestTheVocabularyIsClosed:
    def test_every_reason_the_service_uses_is_declared(self) -> None:
        from src.infrastructure.observability import metrics_attachments as m

        used = {
            m.DELETION_REASON_EXPIRED,
            m.DELETION_REASON_CONVERSATION_RESET,
            m.DELETION_REASON_USER,
        }
        assert used == m.DELETION_REASONS

    async def test_the_owner_of_the_batch_is_the_only_one_asked(self) -> None:
        # The ownership filter lives in the repository statement; this pins that
        # the service passes the CALLER's id and never a row's own.
        seen: list[uuid.UUID] = []

        class _Spy(_Repo):
            async def get_owned_batch(self, ids: list[uuid.UUID], user_id: uuid.UUID) -> list[_Row]:
                seen.append(user_id)
                return []

        service = AttachmentService.__new__(AttachmentService)
        service.db = _Db()  # type: ignore[assignment]
        service.repo = _Spy([])  # type: ignore[assignment]

        await service.delete_generated_batch(_OTHER, [uuid.uuid4()])

        assert seen == [_OTHER]


class TestTheSameIdTwiceIsOneFile:
    """Cold review, 2026-09-10.

    The loop walked `ids` and looked each one up in a dict it never consumed,
    so the same id twice deleted the same row twice, counted two removals for
    one file and returned it twice in `deleted` — « 2 supprimés » for one file
    is exactly the claim ADR-185 forbids. The UI sends a `Set`, so nothing
    reached it from the app; the API is a public surface and answers whatever a
    client posts.
    """

    async def test_a_duplicated_id_is_deleted_once(
        self, monkeypatch: pytest.MonkeyPatch, counter: Counter
    ) -> None:
        mine = uuid.uuid4()
        service, repo = _service([_Row(mine, AttachmentOrigin.GENERATED_IMAGE.value)], monkeypatch)

        deleted, skipped = await service.delete_generated_batch(_USER, [mine, mine, mine])

        assert deleted == [mine]
        assert skipped == []
        assert repo.deleted == [mine]

    async def test_it_counts_the_file_once(
        self, monkeypatch: pytest.MonkeyPatch, counter: Counter
    ) -> None:
        mine = uuid.uuid4()
        service, _ = _service([_Row(mine, AttachmentOrigin.GENERATED_IMAGE.value)], monkeypatch)

        await service.delete_generated_batch(_USER, [mine, mine])

        assert _value(counter, "user_deleted") == 1.0

    async def test_it_unlinks_the_file_once(
        self, monkeypatch: pytest.MonkeyPatch, counter: Counter
    ) -> None:
        mine = uuid.uuid4()
        service, _ = _service([_Row(mine, AttachmentOrigin.GENERATED_IMAGE.value)], monkeypatch)

        await service.delete_generated_batch(_USER, [mine, mine])

        assert service._removed_paths == [f"/tmp/{mine}.bin"]  # type: ignore[attr-defined]

    async def test_a_duplicated_MISSING_id_is_skipped_once(
        self, monkeypatch: pytest.MonkeyPatch, counter: Counter
    ) -> None:
        gone = uuid.uuid4()
        service, _ = _service([], monkeypatch)

        deleted, skipped = await service.delete_generated_batch(_USER, [gone, gone])

        assert deleted == []
        assert skipped == [gone]

    async def test_the_partition_still_covers_every_DISTINCT_id(
        self, monkeypatch: pytest.MonkeyPatch, counter: Counter
    ) -> None:
        ok, gone = uuid.uuid4(), uuid.uuid4()
        service, _ = _service([_Row(ok, AttachmentOrigin.GENERATED_IMAGE.value)], monkeypatch)

        deleted, skipped = await service.delete_generated_batch(_USER, [ok, gone, ok, gone])

        assert len(deleted) + len(skipped) == 2
        assert set(deleted) | set(skipped) == {ok, gone}

    async def test_the_first_occurrence_keeps_its_place(
        self, monkeypatch: pytest.MonkeyPatch, counter: Counter
    ) -> None:
        # The answer reads in the order the caller asked, minus the repeats:
        # re-sorting would make a client match rows by luck.
        first, second = uuid.uuid4(), uuid.uuid4()
        service, _ = _service(
            [
                _Row(first, AttachmentOrigin.GENERATED_IMAGE.value),
                _Row(second, AttachmentOrigin.GENERATED_IMAGE.value),
            ],
            monkeypatch,
        )

        deleted, _skipped = await service.delete_generated_batch(_USER, [second, first, second])

        assert deleted == [second, first]
