"""Tasks & Documents briefing cards (P15 extension, 2026-07-22).

- Tasks: strictly pending/overdue (user arbitration) from the active tasks
  provider (Google Tasks / Microsoft To Do), date-only due semantics in the
  USER's local frame (a task due today is NOT overdue — birthdays doctrine).
- Documents: latest modified files of the account's drive (Google Drive or
  OneDrive), pre-formatted local modification time + external link.

Both open through the shared door (``open_active_client``, whose own tests hold
the no-session and always-closed contract).
"""

from contextlib import ExitStack, asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from src.core.exceptions import ConnectorAPIError
from src.domains.briefing.exceptions import (
    ConnectorAccessError,
    ConnectorNotConfiguredError,
)
from src.domains.briefing.fetchers import fetch_documents, fetch_tasks
from src.domains.briefing.schemas import DocumentsData, TasksData
from src.domains.connectors.active_client import ActiveClient, ClientUnavailable
from src.domains.connectors.clients.normalizers.onedrive_normalizer import normalize_drive_item
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.preferences.owner_defaults import TASK_LIST

TZ = ZoneInfo("Europe/Paris")


def _user():
    return SimpleNamespace(id=uuid4())


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
    """Patch context for fetch_tasks: the shared door + the list resolution."""
    client = MagicMock()
    client.list_tasks = AsyncMock(return_value={"items": tasks})
    asked: list[tuple[str, object]] = []

    @asynccontextmanager
    async def _door(category, user_id, *, container=None):
        asked.append((category, container))
        yield (
            ActiveClient(client=client, connector_type=MagicMock(), preferred_name="Perso")
            if resolved
            else ClientUnavailable.NO_CONNECTOR
        )

    resolve = AsyncMock(return_value="list-perso")
    patches = [
        patch("src.domains.connectors.active_client.open_active_client", _door),
        patch(
            "src.domains.connectors.preferences.owner_defaults.resolve_owner_container_id",
            resolve,
        ),
        patch("src.domains.briefing.fetchers.settings", _settings()),
    ]
    return SimpleNamespace(client=client, asked=asked, resolve=resolve), patches


@pytest.mark.unit
class TestFetchTasks:
    async def test_not_configured_without_provider(self):
        _, patches = _tasks_env([], resolved=False)
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
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            data = await fetch_tasks(user=_user(), user_tz=TZ)

        assert [t.title for t in data.items] == ["j-3", "j-1", "j+1", "j+2"]

    async def test_capped_to_settings_limit(self):
        tasks = [_task(f"t{i}", i) for i in range(8)]
        _, patches = _tasks_env(tasks)
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            data = await fetch_tasks(user=_user(), user_tz=TZ)

        assert len(data.items) == 5

    async def test_a_routine_reads_the_whole_page_not_the_cards_cut(self):
        # Oldest overdue first: behind five older ones, the task that became
        # overdue yesterday is sixth — cut from the card, and exactly what a
        # task routine waits for (ADR-322).
        tasks = [_task(f"old{i}", -10 - i) for i in range(5)] + [_task("yesterday", -1)]
        _, patches = _tasks_env(tasks)
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            card = await fetch_tasks(user=_user(), user_tz=TZ)
            routine = await fetch_tasks(user=_user(), user_tz=TZ, whole_page=True)

        assert "yesterday" not in [t.title for t in card.items]
        assert "yesterday" in [t.title for t in routine.items]

    async def test_reads_the_owners_preferred_list(self):
        """The door is asked for the TASK LIST container, and the list read is
        the one resolved from the owner's preferred name."""
        env, patches = _tasks_env([_task("x", 1)])
        user = _user()
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            await fetch_tasks(user=user, user_tz=TZ)

        assert env.asked == [("tasks", TASK_LIST)]
        assert env.resolve.await_args.kwargs["name"] == "Perso"
        assert env.resolve.await_args.kwargs["owner_id"] == user.id
        assert env.client.list_tasks.await_args.kwargs["task_list_id"] == "list-perso"

    async def test_http_failure_is_a_classified_access_error(self):
        import httpx

        env, patches = _tasks_env([])
        env.client.list_tasks = AsyncMock(side_effect=httpx.ConnectError("boom"))
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            with pytest.raises(ConnectorAccessError):
                await fetch_tasks(user=_user(), user_tz=TZ)


def _documents_env(files, *, resolved=True, connector_type=ConnectorType.MICROSOFT_ONEDRIVE):
    client = MagicMock()
    client.recent_files = AsyncMock(return_value={"files": files})
    client.folder_path = AsyncMock(return_value="Documents/Factures")
    asked: list[str] = []

    @asynccontextmanager
    async def _door(category, user_id):
        asked.append(category)
        yield (
            ActiveClient(client=client, connector_type=connector_type, preferred_name=None)
            if resolved
            else ClientUnavailable.NO_CONNECTOR
        )

    patches = [
        patch("src.domains.connectors.active_client.open_active_client", _door),
        patch("src.domains.briefing.fetchers.settings", _settings()),
    ]
    return SimpleNamespace(client=client, asked=asked), patches


@pytest.mark.unit
class TestFetchDocuments:
    async def test_not_configured_without_a_drive(self):
        _, patches = _documents_env([], resolved=False)
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

    async def test_it_reads_the_accounts_own_drive_within_the_cards_bound(self):
        env, patches = _documents_env([])
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            await fetch_documents(user=_user(), user_tz=TZ, language="fr")

        assert env.asked == ["files"]
        env.client.recent_files.assert_awaited_once_with(5)

    async def test_a_onedrive_file_reads_as_any_other(self):
        item = normalize_drive_item(
            {
                "id": "f1",
                "name": "Budget.xlsx",
                "file": {"mimeType": "application/vnd.ms-excel"},
                "webUrl": "https://onedrive.live.com/edit?id=f1",
                "lastModifiedDateTime": "2026-11-02T09:00:00Z",
            }
        )
        _, patches = _documents_env([item])
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            data = await fetch_documents(user=_user(), user_tz=TZ, language="fr")

        doc = data.items[0]
        assert doc.id == "f1"
        assert doc.web_view_link == "https://onedrive.live.com/edit?id=f1"
        assert doc.mime_type == "application/vnd.ms-excel"
        assert doc.modified_local != "?"

    async def test_each_file_says_where_it_lives_and_on_which_drive(self):
        env, patches = _documents_env([{"id": "f1", "name": "a"}])
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            data = await fetch_documents(user=_user(), user_tz=TZ, language="fr")

        assert data.provider == "microsoft_onedrive"
        assert data.items[0].path == "Documents/Factures"

    async def test_a_folder_read_is_shared_by_the_files_of_the_card(self):
        env, patches = _documents_env([{"id": "f1", "name": "a"}, {"id": "f2", "name": "b"}])
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            await fetch_documents(user=_user(), user_tz=TZ, language="fr")

        first, second = env.client.folder_path.await_args_list
        assert first.args[1] is second.args[1]

    @pytest.mark.parametrize("failure", ["http", "api"])
    async def test_a_path_that_cannot_be_read_leaves_the_file_on_the_card(self, failure):
        import httpx

        env, patches = _documents_env([{"id": "f1", "name": "a"}])
        refused = (
            httpx.ConnectError("boom")
            if failure == "http"
            else ConnectorAPIError("microsoft_onedrive", 404, "gone")
        )
        env.client.folder_path = AsyncMock(side_effect=refused)
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            data = await fetch_documents(user=_user(), user_tz=TZ, language="fr")

        assert data.items[0].name == "a"
        assert data.items[0].path is None

    async def test_a_failure_of_the_provider_is_a_classified_access_error(self):
        import httpx

        env, patches = _documents_env([])
        env.client.recent_files = AsyncMock(side_effect=httpx.ConnectError("boom"))
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            with pytest.raises(ConnectorAccessError):
                await fetch_documents(user=_user(), user_tz=TZ, language="fr")


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
        from src.domains.briefing.constants import SECTIONS_NOT_SUMMARISED

        # Every card the prompts summarise — and only those: a card the
        # synthesis never reads must not count toward its threshold.
        assert len(list(_iter_cards(bundle))) == len(CardsBundle.model_fields) - len(
            SECTIONS_NOT_SUMMARISED
        )
        assert set(SECTIONS_NOT_SUMMARISED) <= set(CardsBundle.model_fields)

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
