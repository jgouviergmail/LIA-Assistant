"""The Gmail label source (ADR-262): rendering, per-thread ingestion, both ways in.

- rendering is pure: subject, messages in date order, plain text preferred,
  attachment names only, a hard size cap, never an address in the name;
- an unchanged thread is skipped, a changed one replaces its document;
- the full sync anchors the history id BEFORE listing, removes what left the
  label, and completes with an EXACT ready count;
- the incremental path revisits exactly the threads the history names,
  removes what no longer carries the label, advances the anchor, and falls
  back to a full sync when the anchor is missing or expired;
- a push serves every source under its own lock, and one failure never
  keeps a source locked.
"""

from __future__ import annotations

import base64
import contextlib
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.exceptions import ConnectorAPIError
from src.domains.rag_spaces import mail_render, mail_sync
from src.domains.rag_spaces.drive_ingest import IngestResult
from src.domains.rag_spaces.mail_render import document_name, render_thread, thread_carries
from src.domains.rag_spaces.mail_sync import (
    apply_history,
    ingest_thread,
    sync_source,
    threads_to_revisit,
)

pytestmark = pytest.mark.unit

LABEL = "Label_42"


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


def _message(
    *,
    message_id: str,
    at_ms: int,
    sender: str,
    to: str,
    subject: str | None,
    body: str,
    labels: list[str] | None = None,
    html: bool = False,
    attachments: list[str] | None = None,
) -> dict[str, Any]:
    headers = [{"name": "From", "value": sender}, {"name": "To", "value": to}]
    if subject is not None:
        headers.append({"name": "Subject", "value": subject})
    parts: list[dict[str, Any]] = [
        {
            "mimeType": "text/html" if html else "text/plain",
            "body": {"data": _b64(body)},
        }
    ]
    for name in attachments or []:
        parts.append({"filename": name, "body": {"attachmentId": "a1", "size": 10}})
    return {
        "id": message_id,
        "threadId": "t1",
        "internalDate": str(at_ms),
        "labelIds": labels if labels is not None else [LABEL, "INBOX"],
        "payload": {"mimeType": "multipart/mixed", "headers": headers, "parts": parts},
    }


def _thread(*messages: dict[str, Any], thread_id: str = "t1") -> dict[str, Any]:
    return {"id": thread_id, "historyId": "900", "messages": list(messages)}


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def test_render_orders_messages_and_keeps_only_attachment_names() -> None:
    thread = _thread(
        _message(
            message_id="m2",
            at_ms=2_000_000,
            sender="bob@example.com",
            to="alice@example.com",
            subject="Re: Budget 2027",
            body="Sounds good.",
            attachments=["budget.xlsx"],
        ),
        _message(
            message_id="m1",
            at_ms=1_000_000,
            sender="alice@example.com",
            to="bob@example.com",
            subject="Budget 2027",
            body="<p>Please <b>review</b> the numbers.</p>",
            html=True,
        ),
    )
    rendered = render_thread(thread, max_chars=10_000)
    assert rendered.subject == "Budget 2027"
    assert rendered.message_count == 2
    assert rendered.truncated is False
    assert rendered.last_message_at == datetime.fromtimestamp(2000, tz=UTC)
    lines = rendered.markdown.splitlines()
    assert lines[0] == "# Budget 2027"
    first = rendered.markdown.index("alice@example.com")
    second = rendered.markdown.index("bob@example.com")
    assert first < second
    assert "Please review the numbers." in rendered.markdown
    assert "<b>" not in rendered.markdown
    assert "Attachments: budget.xlsx" in rendered.markdown
    assert "attachmentId" not in rendered.markdown


def test_render_caps_the_size_and_falls_back_to_the_thread_id() -> None:
    thread = _thread(
        _message(
            message_id="m1",
            at_ms=1_000,
            sender="a@x.io",
            to="b@x.io",
            subject=None,
            body="x" * 5_000,
        ),
        thread_id="thread-7",
    )
    rendered = render_thread(thread, max_chars=300)
    assert rendered.truncated is True
    assert len(rendered.markdown) <= 300 + 3
    assert rendered.markdown.rstrip().endswith("…")
    assert rendered.subject == "thread-7"


def test_document_name_is_the_subject_never_a_participant() -> None:
    rendered = render_thread(
        _thread(
            _message(
                message_id="m1",
                at_ms=1,
                sender="secret@example.com",
                to="b@x.io",
                subject="  Quarterly  ",
                body="-",
            )
        ),
        max_chars=1_000,
    )
    name = document_name(rendered, "t1")
    assert name == "Quarterly.md"
    assert "secret" not in name
    assert document_name(mail_render.RenderedThread("", "", None, 0, False), "t9") == "t9.md"


def test_thread_carries_the_label_when_any_message_does() -> None:
    thread = _thread(
        _message(message_id="m1", at_ms=1, sender="a", to="b", subject="s", body="-", labels=[]),
        _message(message_id="m2", at_ms=2, sender="a", to="b", subject="s", body="-"),
    )
    assert thread_carries(thread, LABEL) is True
    assert thread_carries(thread, "Label_other") is False


# ---------------------------------------------------------------------------
# Per-thread ingestion
# ---------------------------------------------------------------------------


def _ids() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    return uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


@pytest.fixture
def settings_patch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mail_sync,
        "settings",
        SimpleNamespace(
            rag_mail_max_thread_chars=10_000,
            rag_spaces_max_docs_per_space=100,
            rag_mail_max_threads_per_sync=200,
            rag_job_lease_ttl_seconds=60,
            rag_spaces_mail_sync_enabled=True,
            rag_mail_max_sources_per_space=3,
        ),
    )


@pytest.mark.usefixtures("settings_patch")
async def test_an_unchanged_thread_is_skipped_and_a_changed_one_replaced() -> None:
    space_id, source_id, user_id = _ids()
    thread = _thread(
        _message(message_id="m1", at_ms=2_000_000, sender="a", to="b", subject="s", body="hi")
    )
    client = AsyncMock()
    client.get_thread = AsyncMock(return_value=thread)
    existing = MagicMock(mail_last_message_at=datetime.fromtimestamp(2000, tz=UTC))
    doc_repo = MagicMock()
    doc_repo.get_by_mail_thread_id = AsyncMock(return_value=existing)
    doc_repo.count_for_space = AsyncMock(return_value=0)
    with (
        patch.object(mail_sync, "RAGDocumentRepository", return_value=doc_repo),
        patch.object(mail_sync, "discard_document", AsyncMock()) as discard,
        patch.object(mail_sync, "create_pending_document", AsyncMock()) as create,
    ):
        result = await ingest_thread(
            AsyncMock(),
            client,
            space_id=space_id,
            source_id=source_id,
            user_id=user_id,
            thread_id="t1",
        )
        assert result.outcome == "skipped"
        discard.assert_not_awaited()
        create.assert_not_awaited()

        existing.mail_last_message_at = datetime.fromtimestamp(1000, tz=UTC)
        create.return_value = {"document_id": uuid.uuid4()}
        result = await ingest_thread(
            AsyncMock(),
            client,
            space_id=space_id,
            source_id=source_id,
            user_id=user_id,
            thread_id="t1",
        )
    assert result.outcome == "queued"
    discard.assert_awaited_once()
    fields = create.await_args.kwargs
    assert fields["content_type"] == "text/markdown"
    assert fields["extension"] == ".md"
    assert fields["original_name"] == "s.md"
    assert fields["source_fields"] == {
        "source_type": "mail",
        "mail_source_id": source_id,
        "mail_thread_id": "t1",
        "mail_last_message_at": datetime.fromtimestamp(2000, tz=UTC),
    }


@pytest.mark.usefixtures("settings_patch")
async def test_a_fetch_failure_is_contained_and_counted() -> None:
    space_id, source_id, user_id = _ids()
    client = AsyncMock()
    client.get_thread = AsyncMock(side_effect=RuntimeError("boom"))
    before = mail_sync.rag_mail_sync_threads_total.labels(result="failed")._value.get()
    with patch.object(mail_sync, "RAGDocumentRepository", return_value=MagicMock()):
        result = await ingest_thread(
            AsyncMock(),
            client,
            space_id=space_id,
            source_id=source_id,
            user_id=user_id,
            thread_id="t1",
        )
    assert result.outcome == "failed"
    assert mail_sync.rag_mail_sync_threads_total.labels(result="failed")._value.get() == before + 1


# ---------------------------------------------------------------------------
# Full sync
# ---------------------------------------------------------------------------


def _source(**overrides: Any) -> MagicMock:
    source = MagicMock()
    source.id = uuid.uuid4()
    source.space_id = uuid.uuid4()
    source.user_id = uuid.uuid4()
    source.label_id = LABEL
    source.last_history_id = None
    for key, value in overrides.items():
        setattr(source, key, value)
    return source


def _sync_harness(*, indexed: set[str], ready: int = 0) -> tuple[Any, ...]:
    doc_repo = MagicMock()
    doc_repo.get_mail_thread_ids_for_source = AsyncMock(return_value=indexed)
    doc_repo.count_ready_mail_documents = AsyncMock(return_value=ready)
    source_repo = MagicMock()
    source_repo.update = AsyncMock()
    jobs = MagicMock()
    jobs.heartbeat_source = AsyncMock(return_value=True)
    return doc_repo, source_repo, jobs


@pytest.mark.usefixtures("settings_patch")
async def test_full_sync_anchors_before_listing_removes_leavers_and_counts_exactly() -> None:
    source = _source()
    order: list[str] = []
    client = AsyncMock()

    async def _profile() -> dict[str, Any]:
        order.append("profile")
        return {"historyId": "777"}

    async def _list(**_: Any) -> dict[str, Any]:
        order.append("list")
        return {"threads": [{"id": "t1"}, {"id": "t2"}]}

    client.get_profile = _profile
    client.list_threads = _list
    doc_repo, source_repo, jobs = _sync_harness(indexed={"t1", "t9"}, ready=2)
    ingest = AsyncMock(
        side_effect=[
            IngestResult("queued", {"document_id": uuid.uuid4()}),
            IngestResult("skipped"),
        ]
    )
    remove = AsyncMock(return_value=True)
    process = AsyncMock(return_value=(1, 0))
    db = AsyncMock()
    with (
        patch.object(mail_sync, "RAGDocumentRepository", return_value=doc_repo),
        patch.object(mail_sync, "RAGMailSourceRepository", return_value=source_repo),
        patch.object(mail_sync, "RAGJobsRepository", return_value=jobs),
        patch.object(mail_sync, "ingest_thread", ingest),
        patch.object(mail_sync, "remove_thread_document", remove),
        patch.object(mail_sync, "process_queued", process),
    ):
        await sync_source(db, client, source, user_id=source.user_id)

    assert order == ["profile", "list"]
    assert [c.kwargs["thread_id"] for c in ingest.await_args_list] == ["t1", "t2"]
    assert [c.kwargs["thread_id"] for c in remove.await_args_list] == ["t9"]
    assert jobs.heartbeat_source.await_count == 2
    assert jobs.heartbeat_source.await_args.kwargs["table"] == "rag_mail_sources"
    fields = source_repo.update.await_args.args[1]
    assert fields["sync_status"] == "completed"
    assert fields["thread_count"] == 2
    assert fields["last_history_id"] == 777
    # The count shown is the exact READY count, never a sum of guesses.
    assert fields["synced_thread_count"] == 2
    assert fields["lease_expires_at"] is None and fields["worker_id"] is None


@pytest.mark.usefixtures("settings_patch")
async def test_full_sync_is_bounded_by_the_thread_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mail_sync.settings, "rag_mail_max_threads_per_sync", 3)
    client = AsyncMock()
    client.get_profile = AsyncMock(return_value={"historyId": "1"})
    pages = iter(
        [
            {"threads": [{"id": "a"}, {"id": "b"}], "nextPageToken": "p2"},
            {"threads": [{"id": "c"}, {"id": "d"}], "nextPageToken": "p3"},
        ]
    )
    calls: list[int] = []

    async def _list(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs["max_results"])
        return next(pages)

    client.list_threads = _list
    ids = await mail_sync._list_label_threads(client, LABEL, 3)
    assert ids == ["a", "b", "c", "d"][:4]  # the page is read whole
    assert calls == [3, 1]


# ---------------------------------------------------------------------------
# Incremental path
# ---------------------------------------------------------------------------


def test_threads_to_revisit_names_exactly_the_threads_worth_reading() -> None:
    records = [
        {"labelsAdded": [{"message": {"threadId": "added"}, "labelIds": [LABEL]}]},
        {"labelsRemoved": [{"message": {"threadId": "removed"}, "labelIds": [LABEL]}]},
        {"labelsAdded": [{"message": {"threadId": "other"}, "labelIds": ["Label_x"]}]},
        {"messagesAdded": [{"message": {"threadId": "indexed", "labelIds": ["INBOX"]}}]},
        {"messagesAdded": [{"message": {"threadId": "fresh", "labelIds": [LABEL]}}]},
        {"messagesAdded": [{"message": {"threadId": "noise", "labelIds": ["INBOX"]}}]},
    ]
    assert threads_to_revisit(records, LABEL, indexed={"indexed"}) == {
        "added",
        "removed",
        "indexed",
        "fresh",
    }


@pytest.mark.usefixtures("settings_patch")
async def test_apply_history_reindexes_carriers_removes_leavers_and_advances() -> None:
    source = _source(last_history_id=500)
    client = AsyncMock()
    client.get_history = AsyncMock(
        return_value={
            "historyId": "600",
            "history": [
                {"labelsAdded": [{"message": {"threadId": "keep"}, "labelIds": [LABEL]}]},
                {"labelsRemoved": [{"message": {"threadId": "gone"}, "labelIds": [LABEL]}]},
            ],
        }
    )
    threads = {
        "keep": _thread(
            _message(message_id="k", at_ms=1, sender="a", to="b", subject="k", body="-"),
            thread_id="keep",
        ),
        "gone": _thread(
            _message(message_id="g", at_ms=1, sender="a", to="b", subject="g", body="-", labels=[]),
            thread_id="gone",
        ),
    }
    client.get_thread = AsyncMock(side_effect=lambda tid: threads[tid])
    doc_repo, source_repo, jobs = _sync_harness(indexed={"gone"}, ready=1)
    ingest = AsyncMock(return_value=IngestResult("queued", {"document_id": uuid.uuid4()}))
    remove = AsyncMock(return_value=True)
    process = AsyncMock(return_value=(1, 0))
    with (
        patch.object(mail_sync, "RAGDocumentRepository", return_value=doc_repo),
        patch.object(mail_sync, "RAGMailSourceRepository", return_value=source_repo),
        patch.object(mail_sync, "RAGJobsRepository", return_value=jobs),
        patch.object(mail_sync, "ingest_thread", ingest),
        patch.object(mail_sync, "remove_thread_document", remove),
        patch.object(mail_sync, "process_queued", process),
    ):
        outcome = await apply_history(AsyncMock(), client, source, user_id=source.user_id)

    assert outcome == "indexed"
    history_kwargs = client.get_history.await_args.kwargs
    assert history_kwargs["label_id"] == LABEL
    assert history_kwargs["history_types"] == ("messageAdded", "labelAdded", "labelRemoved")
    assert ingest.await_args.kwargs["thread_id"] == "keep"
    assert ingest.await_args.kwargs["thread"] is threads["keep"]
    assert remove.await_args.kwargs["thread_id"] == "gone"
    fields = source_repo.update.await_args.args[1]
    assert fields["last_history_id"] == 600
    assert fields["sync_status"] == "completed"


@pytest.mark.usefixtures("settings_patch")
async def test_apply_history_reports_a_missing_or_expired_anchor() -> None:
    assert await apply_history(AsyncMock(), AsyncMock(), _source(), user_id=uuid.uuid4()) == (
        "no_anchor"
    )
    client = AsyncMock()
    client.get_history = AsyncMock(
        side_effect=ConnectorAPIError(
            connector_type="google_gmail", status_code=404, detail="history expired"
        )
    )
    outcome = await apply_history(
        AsyncMock(), client, _source(last_history_id=5), user_id=uuid.uuid4()
    )
    assert outcome == "expired"


@pytest.mark.usefixtures("settings_patch")
async def test_one_unreadable_thread_does_not_stop_the_pass() -> None:
    source = _source(last_history_id=5)
    client = AsyncMock()
    client.get_history = AsyncMock(
        return_value={
            "historyId": "6",
            "history": [
                {"labelsAdded": [{"message": {"threadId": "bad"}, "labelIds": [LABEL]}]},
                {"labelsAdded": [{"message": {"threadId": "good"}, "labelIds": [LABEL]}]},
            ],
        }
    )

    async def _get(tid: str) -> dict[str, Any]:
        if tid == "bad":
            raise RuntimeError("410")
        return _thread(
            _message(message_id="g", at_ms=1, sender="a", to="b", subject="g", body="-"),
            thread_id=tid,
        )

    client.get_thread = AsyncMock(side_effect=_get)
    doc_repo, source_repo, jobs = _sync_harness(indexed=set())
    ingest = AsyncMock(return_value=IngestResult("queued", {"document_id": uuid.uuid4()}))
    with (
        patch.object(mail_sync, "RAGDocumentRepository", return_value=doc_repo),
        patch.object(mail_sync, "RAGMailSourceRepository", return_value=source_repo),
        patch.object(mail_sync, "RAGJobsRepository", return_value=jobs),
        patch.object(mail_sync, "ingest_thread", ingest),
        patch.object(mail_sync, "process_queued", AsyncMock(return_value=(1, 0))),
    ):
        outcome = await apply_history(AsyncMock(), client, source, user_id=source.user_id)
    assert outcome == "indexed"
    assert ingest.await_args.kwargs["thread_id"] == "good"


# ---------------------------------------------------------------------------
# Push entry
# ---------------------------------------------------------------------------


@contextlib.asynccontextmanager
async def _fake_db_context():  # type: ignore[no-untyped-def]
    yield AsyncMock()


@pytest.mark.usefixtures("settings_patch")
async def test_push_serves_every_source_under_its_lock_and_resyncs_without_anchor() -> None:
    fresh, anchored, busy = _source(), _source(last_history_id=9), _source(last_history_id=9)
    source_repo = MagicMock()
    source_repo.get_all_for_user = AsyncMock(return_value=[fresh, anchored, busy])
    service = MagicMock()
    service.try_acquire_sync_lock = AsyncMock(side_effect=[True, True, False])
    client = AsyncMock()
    with (
        patch.object(mail_sync, "get_db_context", _fake_db_context),
        patch.object(mail_sync, "RAGMailSourceRepository", return_value=source_repo),
        patch.object(mail_sync, "gmail_client_or_none", AsyncMock(return_value=client)),
        patch.object(mail_sync, "RAGMailSyncService", return_value=service),
        patch.object(mail_sync, "apply_history", AsyncMock(side_effect=["no_anchor", "nothing"])),
        patch.object(mail_sync, "sync_source", AsyncMock()) as full,
    ):
        outcome = await mail_sync.index_mail_sources_from_push(uuid.uuid4())
    assert outcome == "resynced"
    full.assert_awaited_once()
    assert full.await_args.args[2] is fresh
    client.close.assert_awaited_once()


@pytest.mark.usefixtures("settings_patch")
async def test_push_without_a_source_touches_nothing() -> None:
    source_repo = MagicMock()
    source_repo.get_all_for_user = AsyncMock(return_value=[])
    with (
        patch.object(mail_sync, "get_db_context", _fake_db_context),
        patch.object(mail_sync, "RAGMailSourceRepository", return_value=source_repo),
        patch.object(mail_sync, "gmail_client_or_none", AsyncMock()) as get_client,
    ):
        assert await mail_sync.index_mail_sources_from_push(uuid.uuid4()) == "no_source"
    get_client.assert_not_awaited()


@pytest.mark.usefixtures("settings_patch")
async def test_a_failing_source_is_released_and_counted_as_error() -> None:
    source = _source(last_history_id=9)
    service = MagicMock()
    service.try_acquire_sync_lock = AsyncMock(return_value=True)
    with (
        patch.object(mail_sync, "apply_history", AsyncMock(side_effect=RuntimeError("io"))),
        patch.object(mail_sync, "_fail_source", AsyncMock()) as fail,
    ):
        outcome = await mail_sync._serve_source(
            AsyncMock(), AsyncMock(), service, source, source.user_id
        )
    assert outcome == "error"
    fail.assert_awaited_once()
    assert fail.await_args.args[1] is source
