"""RAGMailSyncService (ADR-262): link, unlink, labels, lock — and who may.

Ownership is the space's and hides existence (404), the feature flag refuses
at the door (403), the bounds are the published settings, and a label that
does not exist on the account is refused before any row is written.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status

from src.core.exceptions import BaseAPIException
from src.domains.rag_spaces import mail_source_service
from src.domains.rag_spaces.mail_source_service import RAGMailSyncService

pytestmark = pytest.mark.unit


@pytest.fixture
def service(monkeypatch: pytest.MonkeyPatch) -> RAGMailSyncService:
    monkeypatch.setattr(
        mail_source_service,
        "settings",
        SimpleNamespace(
            rag_spaces_mail_sync_enabled=True,
            rag_mail_max_sources_per_space=2,
            rag_job_lease_ttl_seconds=60,
        ),
    )
    svc = RAGMailSyncService(AsyncMock())
    svc.space_repo = AsyncMock()
    svc.doc_repo = AsyncMock()
    svc.source_repo = AsyncMock()
    return svc


def _space(user_id: uuid.UUID) -> MagicMock:
    space = MagicMock()
    space.id = uuid.uuid4()
    space.user_id = user_id
    return space


def _client(labels: dict[str, str] | None = None, label: dict | None = None) -> AsyncMock:
    client = AsyncMock()
    client.list_labels = AsyncMock(return_value=labels or {})
    client.get_label = AsyncMock(return_value=label)
    client.close = AsyncMock()
    return client


async def test_another_users_space_is_a_404(service: RAGMailSyncService) -> None:
    owner, intruder = uuid.uuid4(), uuid.uuid4()
    space = _space(owner)
    service.space_repo.get_by_id = AsyncMock(return_value=space)
    with pytest.raises(BaseAPIException) as exc:
        await service.link_label(space.id, intruder, "Label_1", "Projects")
    assert exc.value.status_code == status.HTTP_404_NOT_FOUND
    service.source_repo.create.assert_not_awaited()


async def test_the_flag_refuses_at_the_door(
    service: RAGMailSyncService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mail_source_service.settings, "rag_spaces_mail_sync_enabled", False)
    with pytest.raises(BaseAPIException) as exc:
        await service.link_label(uuid.uuid4(), uuid.uuid4(), "Label_1", "Projects")
    assert exc.value.status_code == status.HTTP_403_FORBIDDEN
    with pytest.raises(BaseAPIException) as exc:
        await service.list_labels(uuid.uuid4(), uuid.uuid4())
    assert exc.value.status_code == status.HTTP_403_FORBIDDEN


async def test_link_checks_the_bound_the_duplicate_and_the_label(
    service: RAGMailSyncService,
) -> None:
    user_id = uuid.uuid4()
    space = _space(user_id)
    service.space_repo.get_by_id = AsyncMock(return_value=space)

    service.source_repo.count_for_space = AsyncMock(return_value=2)
    with pytest.raises(BaseAPIException) as exc:
        await service.link_label(space.id, user_id, "Label_1", "Projects")
    assert exc.value.status_code == status.HTTP_400_BAD_REQUEST

    service.source_repo.count_for_space = AsyncMock(return_value=0)
    service.source_repo.exists_for_space_and_label = AsyncMock(return_value=True)
    with pytest.raises(BaseAPIException) as exc:
        await service.link_label(space.id, user_id, "Label_1", "Projects")
    assert exc.value.status_code == status.HTTP_409_CONFLICT

    service.source_repo.exists_for_space_and_label = AsyncMock(return_value=False)
    client = _client(label=None)
    with (
        patch.object(service, "_get_gmail_client", AsyncMock(return_value=client)),
        pytest.raises(BaseAPIException) as exc,
    ):
        await service.link_label(space.id, user_id, "Label_1", "Projects")
    assert exc.value.status_code == status.HTTP_400_BAD_REQUEST
    client.close.assert_awaited_once()
    service.source_repo.create.assert_not_awaited()


async def test_link_stores_the_accounts_label_name(service: RAGMailSyncService) -> None:
    user_id = uuid.uuid4()
    space = _space(user_id)
    service.space_repo.get_by_id = AsyncMock(return_value=space)
    service.source_repo.count_for_space = AsyncMock(return_value=0)
    service.source_repo.exists_for_space_and_label = AsyncMock(return_value=False)
    created = MagicMock()
    created.id = uuid.uuid4()
    service.source_repo.create = AsyncMock(return_value=created)
    client = _client(label={"id": "Label_1", "name": "Projects/2027"})
    with patch.object(service, "_get_gmail_client", AsyncMock(return_value=client)):
        source = await service.link_label(space.id, user_id, "Label_1", "stale name")
    assert source is created
    row = service.source_repo.create.await_args.args[0]
    assert row["label_id"] == "Label_1"
    assert row["label_name"] == "Projects/2027"
    assert row["sync_status"] == "idle"


async def test_list_labels_offers_the_users_labels_only_sorted(
    service: RAGMailSyncService,
) -> None:
    user_id = uuid.uuid4()
    space = _space(user_id)
    service.space_repo.get_by_id = AsyncMock(return_value=space)
    client = _client(
        labels={
            "INBOX": "INBOX",
            "CATEGORY_PROMOTIONS": "CATEGORY_PROMOTIONS",
            "Label_2": "zebra",
            "Label_1": "Alpha",
        }
    )
    with patch.object(service, "_get_gmail_client", AsyncMock(return_value=client)):
        labels = await service.list_labels(space.id, user_id)
    assert labels == [{"id": "Label_1", "name": "Alpha"}, {"id": "Label_2", "name": "zebra"}]
    assert client.list_labels.await_args.kwargs == {"use_cache": False}
    client.close.assert_awaited_once()


async def test_unlink_keeps_or_deletes_the_documents(service: RAGMailSyncService) -> None:
    user_id = uuid.uuid4()
    space = _space(user_id)
    service.space_repo.get_by_id = AsyncMock(return_value=space)
    source = MagicMock()
    source.id = uuid.uuid4()
    service.source_repo.get_by_id_and_space = AsyncMock(return_value=source)
    docs = [MagicMock(), MagicMock()]
    service.doc_repo.get_mail_documents_for_source = AsyncMock(return_value=docs)

    with patch.object(mail_source_service, "discard_document", AsyncMock()) as discard:
        await service.unlink_label(space.id, source.id, user_id, delete_documents=False)
    discard.assert_not_awaited()
    executed = service.db.execute.await_args.args[0]
    assert "SET mail_source_id = NULL" in str(executed.text)
    service.source_repo.delete.assert_awaited_once_with(source)

    with patch.object(mail_source_service, "discard_document", AsyncMock()) as discard:
        await service.unlink_label(space.id, source.id, user_id, delete_documents=True)
    assert discard.await_count == 2


async def test_the_lock_is_one_conditional_update(service: RAGMailSyncService) -> None:
    service.db.execute = AsyncMock(return_value=MagicMock(rowcount=1))
    assert await service.try_acquire_sync_lock(uuid.uuid4()) is True
    sql = str(service.db.execute.await_args.args[0].text)
    assert "UPDATE rag_mail_sources" in sql
    assert "WHERE id = :id AND sync_status != :syncing" in sql
    service.db.execute = AsyncMock(return_value=MagicMock(rowcount=0))
    assert await service.try_acquire_sync_lock(uuid.uuid4()) is False
