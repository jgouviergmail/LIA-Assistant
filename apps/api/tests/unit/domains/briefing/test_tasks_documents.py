"""Tasks & Documents briefing cards (P15 extension, 2026-07-22).

- Tasks: strictly pending/overdue (user arbitration) from EVERY list of the
  active tasks provider (Google Tasks / Microsoft To Do), each naming its own
  list; date-only due semantics in the USER's local frame (a task due today is
  NOT overdue — birthdays doctrine). A list that fails leaves the others on the
  card, said partial; « nothing to do » is never told on a list nobody read.
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


def _tasks_env(tasks, *, resolved=True, more_lists=False):
    """Patch context for fetch_tasks: the shared door and a provider of task lists.

    ``tasks`` is the page of a single list (« Perso »), or a mapping of list id to
    what that list answers: its tasks, a whole page (a dict) or the error it raises.
    """
    pages = tasks if isinstance(tasks, dict) else {"list-perso": tasks}

    async def read(list_id, **kwargs):
        answer = pages[list_id]
        if isinstance(answer, Exception):
            raise answer
        return answer if isinstance(answer, dict) else {"items": answer}

    client = MagicMock()
    client.list_task_lists = AsyncMock(
        return_value={
            "items": [{"id": list_id, "title": list_id.removeprefix("list-")} for list_id in pages],
            "next_page_token": "next" if more_lists else None,
        }
    )
    client.list_tasks = AsyncMock(side_effect=read)
    asked: list[tuple[str, object]] = []

    @asynccontextmanager
    async def _door(category, user_id, *, container=None):
        asked.append((category, container))
        yield (
            ActiveClient(client=client, connector_type=MagicMock(), preferred_name="Perso")
            if resolved
            else ClientUnavailable.NO_CONNECTOR
        )

    patches = [
        patch("src.domains.connectors.active_client.open_active_client", _door),
        patch("src.domains.briefing.fetchers.settings", _settings()),
    ]
    return SimpleNamespace(client=client, asked=asked), patches


async def _fetch(env_patches, **kwargs):
    with ExitStack() as stack:
        for p in env_patches:
            stack.enter_context(p)
        return await fetch_tasks(user=_user(), user_tz=TZ, **kwargs)


@pytest.mark.unit
class TestFetchTasks:
    async def test_not_configured_without_provider(self):
        _, patches = _tasks_env([], resolved=False)
        with pytest.raises(ConnectorNotConfiguredError):
            await _fetch(patches)

    async def test_overdue_is_strictly_before_today_local(self):
        """Date-only semantics in the user's local frame: due today is ON
        TIME (never 'overdue' just because 00:00 UTC passed)."""
        tasks = [_task("aujourd'hui", 0), _task("hier", -1), _task("demain", 1)]
        _, patches = _tasks_env(tasks)

        data = await _fetch(patches)

        assert isinstance(data, TasksData)
        by_title = {t.title: t for t in data.items}
        assert by_title["hier"].overdue is True
        assert by_title["hier"].days_until_due == -1
        assert by_title["aujourd'hui"].overdue is False
        assert by_title["aujourd'hui"].days_until_due == 0
        assert by_title["demain"].overdue is False
        assert data.overdue_count == 1
        assert data.partial is False

    async def test_sorted_overdue_first_then_due_ascending(self):
        tasks = [_task("j+2", 2), _task("j-3", -3), _task("j+1", 1), _task("j-1", -1)]
        _, patches = _tasks_env(tasks)

        data = await _fetch(patches)

        assert [t.title for t in data.items] == ["j-3", "j-1", "j+1", "j+2"]

    async def test_capped_to_settings_limit(self):
        tasks = [_task(f"t{i}", i) for i in range(8)]
        _, patches = _tasks_env(tasks)

        data = await _fetch(patches)

        assert len(data.items) == 5

    async def test_a_routine_reads_the_whole_page_not_the_cards_cut(self):
        # Oldest overdue first: behind five older ones, the task that became
        # overdue yesterday is sixth — cut from the card, and exactly what a
        # task routine waits for (ADR-322).
        tasks = [_task(f"old{i}", -10 - i) for i in range(5)] + [_task("yesterday", -1)]
        _, patches = _tasks_env(tasks)

        card = await _fetch(patches)
        routine = await _fetch(patches, whole_page=True)

        assert "yesterday" not in [t.title for t in card.items]
        assert "yesterday" in [t.title for t in routine.items]

    async def test_every_list_is_read_and_each_task_names_its_own(self):
        """The card gathers the lists (owner, 2026-11-10): one order across them
        all, and each task says which list it is in, by its real id and its name."""
        env, patches = _tasks_env(
            {
                "list-perso": [_task("perso demain", 1)],
                "list-courses": [_task("courses hier", -1), _task("courses j+2", 2)],
            }
        )

        data = await _fetch(patches)

        assert env.asked == [("tasks", None)]
        assert [(t.title, t.list_id, t.list_name) for t in data.items] == [
            ("courses hier", "list-courses", "courses"),
            ("perso demain", "list-perso", "perso"),
            ("courses j+2", "list-courses", "courses"),
        ]
        assert [call.args for call in env.client.list_tasks.await_args_list] == [
            ("list-perso",),
            ("list-courses",),
        ]
        assert data.partial is False

    async def test_a_routine_reads_the_whole_page_of_every_list(self):
        _, patches = _tasks_env(
            {
                "list-perso": [_task(f"old{i}", -10 - i) for i in range(5)],
                "list-courses": [_task("yesterday", -1)],
            }
        )

        routine = await _fetch(patches, whole_page=True)

        assert len(routine.items) == 6
        assert routine.overdue_count == 6

    async def test_each_list_is_asked_one_page_of_open_tasks_within_the_horizon(self):
        env, patches = _tasks_env([_task("x", 1)])
        expected = datetime.now(UTC) + timedelta(days=7)

        await _fetch(patches)

        asked = env.client.list_tasks.await_args.kwargs
        assert asked["max_results"] == 5 * 4
        assert (asked["show_completed"], asked["show_hidden"]) == (False, False)
        due_max = datetime.strptime(asked["due_max"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        assert abs(due_max - expected) < timedelta(minutes=1)
        assert env.client.list_tasks.await_count == 1

    async def test_a_list_holding_more_than_its_page_makes_the_card_partial(self):
        page = {"items": [_task("x", 1)], "next_page_token": "more"}
        env, patches = _tasks_env({"list-perso": page})

        data = await _fetch(patches)

        assert env.client.list_tasks.await_count == 1
        assert data.partial is True

    async def test_more_lists_than_were_read_makes_the_card_partial(self):
        _, patches = _tasks_env([_task("x", 1)], more_lists=True)

        data = await _fetch(patches)

        assert data.partial is True

    async def test_a_list_without_a_name_carries_none(self):
        env, patches = _tasks_env([_task("x", 1)])
        env.client.list_task_lists.return_value = {"items": [{"id": "list-perso", "title": ""}]}

        data = await _fetch(patches)

        assert [(t.list_id, t.list_name) for t in data.items] == [("list-perso", None)]

    async def test_a_list_the_provider_gave_no_id_is_not_read(self):
        env, patches = _tasks_env([_task("x", 1)])
        env.client.list_task_lists.return_value = {
            "items": [{"title": "ghost"}, {"id": "list-perso", "title": "perso"}]
        }

        data = await _fetch(patches)

        assert [call.args for call in env.client.list_tasks.await_args_list] == [("list-perso",)]
        assert [t.title for t in data.items] == ["x"]

    @pytest.mark.parametrize("failure", ["http", "api"])
    async def test_a_list_that_fails_leaves_the_others_and_the_card_says_so(self, failure):
        import httpx

        refused = (
            httpx.ConnectError("boom")
            if failure == "http"
            else ConnectorAPIError("google_tasks", 404, "gone")
        )
        _, patches = _tasks_env({"list-perso": refused, "list-courses": [_task("pain", 0)]})

        data = await _fetch(patches)

        assert [t.title for t in data.items] == ["pain"]
        assert data.partial is True

    async def test_http_failure_is_a_classified_access_error(self):
        import httpx

        _, patches = _tasks_env({"list-perso": httpx.ConnectError("boom")})

        with pytest.raises(ConnectorAccessError):
            await _fetch(patches)

    async def test_nothing_to_show_beside_a_failed_list_is_never_an_empty_card(self):
        """« Nothing to do » cannot be told on a list nobody read (ADR-303)."""
        import httpx

        _, patches = _tasks_env({"list-perso": httpx.ConnectError("boom"), "list-courses": []})

        with pytest.raises(ConnectorAccessError):
            await _fetch(patches)

    async def test_a_providers_refusal_of_every_list_stays_what_it_is(self):
        refusal = ConnectorAPIError("google_tasks", 403, "forbidden")
        _, patches = _tasks_env({"list-perso": refusal})

        with pytest.raises(ConnectorAPIError) as raised:
            await _fetch(patches)

        assert raised.value is refusal

    async def test_lists_that_cannot_be_listed_are_a_classified_access_error(self):
        import httpx

        env, patches = _tasks_env([])
        env.client.list_task_lists = AsyncMock(side_effect=httpx.ConnectError("boom"))

        with pytest.raises(ConnectorAccessError):
            await _fetch(patches)

        env.client.list_tasks.assert_not_awaited()

    async def test_no_list_is_an_empty_card(self):
        _, patches = _tasks_env({})

        data = await _fetch(patches)

        assert (data.items, data.partial) == ([], False)


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
