"""The mail source endpoints are mounted on the RAG Spaces router (ADR-262).

Registered under the router's own prefix, with the HTTP methods the frontend
hook relies on — and the sync trigger refuses a second concurrent sync.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status

from src.core.exceptions import BaseAPIException
from src.domains.rag_spaces import mail_router
from src.domains.rag_spaces.router import router

pytestmark = pytest.mark.unit


def _methods(path: str) -> set[str]:
    methods: set[str] = set()
    for route in router.routes:
        if getattr(route, "path", None) == path:
            methods |= set(route.methods or set())
    return methods


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/rag-spaces/{space_id}/mail-labels", {"GET"}),
        ("/rag-spaces/{space_id}/mail-sources", {"GET", "POST"}),
        ("/rag-spaces/{space_id}/mail-sources/{source_id}", {"DELETE"}),
        ("/rag-spaces/{space_id}/mail-sources/{source_id}/sync", {"POST"}),
        ("/rag-spaces/{space_id}/mail-sources/{source_id}/sync-status", {"GET"}),
    ],
)
def test_mail_routes_are_mounted_with_their_methods(path: str, expected: set[str]) -> None:
    assert expected <= _methods(path), path


async def test_sync_refuses_a_second_concurrent_run() -> None:
    service = MagicMock()
    service.get_sync_status = AsyncMock(return_value=MagicMock())
    service.try_acquire_sync_lock = AsyncMock(return_value=False)
    user = MagicMock()
    user.id = uuid.uuid4()
    with (
        patch.object(mail_router, "RAGMailSyncService", return_value=service),
        patch.object(mail_router, "safe_fire_and_forget") as fire,
        pytest.raises(BaseAPIException) as exc,
    ):
        await mail_router.sync_mail_label(uuid.uuid4(), uuid.uuid4(), user=user, db=AsyncMock())
    assert exc.value.status_code == status.HTTP_409_CONFLICT
    fire.assert_not_called()


async def test_sync_launches_the_background_sync_once_locked() -> None:
    source = MagicMock(
        sync_status="syncing",
        last_sync_at=None,
        thread_count=0,
        synced_thread_count=0,
        error_message=None,
    )
    service = MagicMock()
    service.get_sync_status = AsyncMock(return_value=source)
    service.try_acquire_sync_lock = AsyncMock(return_value=True)
    user = MagicMock()
    user.id = uuid.uuid4()
    source_id = uuid.uuid4()
    with (
        patch.object(mail_router, "RAGMailSyncService", return_value=service),
        patch.object(mail_router, "sync_label_background", MagicMock(return_value="coro")),
        patch.object(mail_router, "safe_fire_and_forget") as fire,
    ):
        response = await mail_router.sync_mail_label(
            uuid.uuid4(), source_id, user=user, db=AsyncMock()
        )
    assert response.sync_status == "syncing"
    fire.assert_called_once_with("coro", name=f"mail_sync_{source_id}")
