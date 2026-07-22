"""Tasks & Documents briefing cards (P15 extension, 2026-07-22).

- Tasks: strictly pending/overdue (user arbitration) from the active tasks
  provider (Google Tasks / Microsoft To Do), date-only due semantics in the
  USER's local frame (a task due today is NOT overdue — birthdays doctrine).
- Documents: latest modified Google Drive files (user arbitration: Drive
  source), pre-formatted local modification time + external link.

Both fetchers own their provider client and must close it on every path.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from src.domains.briefing.exceptions import (
    ConnectorAccessError,
    ConnectorNotConfiguredError,
)
from src.domains.briefing.fetchers import fetch_documents, fetch_tasks
from src.domains.briefing.schemas import DocumentsData, TasksData

TZ = ZoneInfo("Europe/Paris")


def _user():
    return SimpleNamespace(id=uuid4())


def _db_ctx():
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _ctx():
        yield MagicMock()

    return _ctx


def _task(title: str, due_days_offset: int | None):
    """Provider-normalized task dict; due is RFC 3339 date-only (00:00Z)."""
    due = None
    if due_days_offset is not None:
        due_date = (datetime.now(TZ) + timedelta(days=due_days_offset)).date()
        due = f"{due_date.isoformat()}T00:00:00.000Z"
    return {"title": title, "due": due, "status": "needsAction"}


def _settings(**overrides):
    defaults = {
        "briefing_max_tasks_items": 5,
        "briefing_tasks_horizon_days": 7,
        "briefing_max_documents_items": 5,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _tasks_env(tasks, *, resolved=True):
    """Patch context for fetch_tasks: provider resolution + client."""
    client = MagicMock()
    client.close = AsyncMock()
    client.list_tasks = AsyncMock(return_value={"items": tasks})

    connector_service = MagicMock()
    connector_service.get_connector_credentials = AsyncMock(return_value=MagicMock())

    repo = MagicMock()
    repo.get_by_user_and_type = AsyncMock(return_value=None)

    patches = [
        patch("src.domains.briefing.fetchers.get_db_context", new=_db_ctx()),
        patch("src.domains.briefing.fetchers.ConnectorService", return_value=connector_service),
        patch(
            "src.domains.briefing.fetchers.resolve_active_connector",
            AsyncMock(return_value=MagicMock(value="google_tasks") if resolved else None),
        ),
        patch(
            "src.domains.briefing.fetchers.ClientRegistry.get_client_class",
            return_value=lambda *a, **k: client,
        ),
        patch("src.domains.connectors.repository.ConnectorRepository", return_value=repo),
        patch("src.domains.briefing.fetchers.settings", _settings()),
    ]
    return client, patches


@pytest.mark.unit
class TestFetchTasks:
    async def test_not_configured_without_provider(self):
        _, patches = _tasks_env([], resolved=False)
        from contextlib import ExitStack

        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            with pytest.raises(ConnectorNotConfiguredError):
                await fetch_tasks(user=_user(), user_tz=TZ)

    async def test_overdue_is_strictly_before_today_local(self):
        """Date-only semantics in the user's local frame: due today is ON
        TIME (never 'overdue' just because 00:00 UTC passed)."""
        tasks = [_task("aujourd'hui", 0), _task("hier", -1), _task("demain", 1)]
        _, patches = _tasks_env(tasks)
        from contextlib import ExitStack

        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            data = await fetch_tasks(user=_user(), user_tz=TZ)

        assert isinstance(data, TasksData)
        by_title = {t.title: t for t in data.items}
        assert by_title["hier"].overdue is True
        assert by_title["hier"].days_until_due == -1
        assert by_title["aujourd'hui"].overdue is False
        assert by_title["aujourd'hui"].days_until_due == 0
        assert by_title["demain"].overdue is False
        assert data.overdue_count == 1

    async def test_sorted_overdue_first_then_due_ascending(self):
        tasks = [_task("j+2", 2), _task("j-3", -3), _task("j+1", 1), _task("j-1", -1)]
        _, patches = _tasks_env(tasks)
        from contextlib import ExitStack

        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            data = await fetch_tasks(user=_user(), user_tz=TZ)

        assert [t.title for t in data.items] == ["j-3", "j-1", "j+1", "j+2"]

    async def test_capped_to_settings_limit(self):
        tasks = [_task(f"t{i}", i) for i in range(8)]
        _, patches = _tasks_env(tasks)
        from contextlib import ExitStack

        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            data = await fetch_tasks(user=_user(), user_tz=TZ)

        assert len(data.items) == 5

    async def test_client_closed_on_success_and_error(self):
        client, patches = _tasks_env([_task("x", 1)])
        from contextlib import ExitStack

        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            await fetch_tasks(user=_user(), user_tz=TZ)
        client.close.assert_awaited_once()

        client2, patches2 = _tasks_env([])
        client2.list_tasks = AsyncMock(side_effect=RuntimeError("api down"))
        with ExitStack() as stack:
            for p in patches2:
                stack.enter_context(p)
            with pytest.raises(RuntimeError):
                await fetch_tasks(user=_user(), user_tz=TZ)
        client2.close.assert_awaited_once()


def _documents_env(files, *, credentials=True):
    client = MagicMock()
    client.close = AsyncMock()
    client.search_files = AsyncMock(return_value={"files": files})

    connector_service = MagicMock()
    connector_service.get_connector_credentials = AsyncMock(
        return_value=MagicMock() if credentials else None
    )

    patches = [
        patch("src.domains.briefing.fetchers.get_db_context", new=_db_ctx()),
        patch("src.domains.briefing.fetchers.ConnectorService", return_value=connector_service),
        patch("src.domains.briefing.fetchers.GoogleDriveClient", return_value=client),
        patch("src.domains.briefing.fetchers.settings", _settings()),
    ]
    return client, patches


@pytest.mark.unit
class TestFetchDocuments:
    async def test_not_configured_without_drive_credentials(self):
        _, patches = _documents_env([], credentials=False)
        from contextlib import ExitStack

        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            with pytest.raises(ConnectorNotConfiguredError):
                await fetch_documents(user=_user(), user_tz=TZ, language="fr")

    async def test_maps_recent_files_with_local_time_and_link(self):
        now = datetime.now(UTC)
        files = [
            {
                "id": "f1",
                "name": "Devis plomberie.pdf",
                "mimeType": "application/pdf",
                "modifiedTime": now.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                "webViewLink": "https://drive.google.com/file/d/f1/view",
            }
        ]
        _, patches = _documents_env(files)
        from contextlib import ExitStack

        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            data = await fetch_documents(user=_user(), user_tz=TZ, language="fr")

        assert isinstance(data, DocumentsData)
        assert len(data.items) == 1
        doc = data.items[0]
        assert doc.name == "Devis plomberie.pdf"
        assert doc.web_view_link == "https://drive.google.com/file/d/f1/view"
        assert doc.mime_type == "application/pdf"
        # Modified today → bare local HH:MM (reminders formatting doctrine)
        assert ":" in doc.modified_local and "?" not in doc.modified_local

    async def test_client_closed_on_http_error_and_mapped(self):
        import httpx

        client, patches = _documents_env([])
        client.search_files = AsyncMock(side_effect=httpx.ConnectError("boom"))
        from contextlib import ExitStack

        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            with pytest.raises(ConnectorAccessError):
                await fetch_documents(user=_user(), user_tz=TZ, language="fr")
        client.close.assert_awaited_once()


@pytest.mark.unit
class TestBundleIntegration:
    def test_bundle_carries_nine_sections(self):
        from src.domains.briefing.constants import SECTION_NAMES
        from src.domains.briefing.schemas import CardsBundle

        assert {"tasks", "documents"} <= set(CardsBundle.model_fields.keys())
        # Per-section refresh validates against SECTION_NAMES — a missing
        # entry silently kills the refresh button (registry completeness).
        assert {"tasks", "documents"} <= set(SECTION_NAMES)

    def test_iter_cards_yields_tasks_and_documents(self):
        from src.domains.briefing.llm import _iter_cards
        from src.domains.briefing.schemas import CardsBundle, CardSection, CardStatus

        empty = CardSection(
            status=CardStatus.EMPTY, data=None, generated_at=datetime.now(UTC).isoformat()
        )
        bundle = CardsBundle(**dict.fromkeys(CardsBundle.model_fields, empty))
        assert len(list(_iter_cards(bundle))) == len(CardsBundle.model_fields)

    def test_has_content_on_tasks_and_documents(self):
        from src.domains.briefing.schemas import TaskItem
        from src.domains.briefing.service import _has_content

        assert _has_content(TasksData(items=[], overdue_count=0)) is False
        assert (
            _has_content(
                TasksData(
                    items=[
                        TaskItem(title="x", due_date_iso=None, days_until_due=None, overdue=False)
                    ],
                    overdue_count=0,
                )
            )
            is True
        )
        assert _has_content(DocumentsData(items=[])) is False
