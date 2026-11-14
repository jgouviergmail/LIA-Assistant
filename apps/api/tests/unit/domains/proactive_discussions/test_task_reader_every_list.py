"""The discussions' tasks source reads every list, each fenced as its own container (2026-11-10).

The default list is where a NEW task goes; a discussion reads them all. What makes it a
discussion read is kept: a reference is read back in the list it was minted under and nowhere
else, the read's call budget bounds the lists read and says so, a provider's failure stays the
read's, and a task's text is the provider's record.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from src.core.constants import TASK_LIST_NAMES_SCAN_MAX
from src.core.read_budget import ReadCallLimit
from src.domains.connectors import discussion_sources, discussion_tasks
from src.domains.connectors.active_client import ActiveClient, ClientUnavailable
from src.domains.connectors.discussion_authority import require_reader_authorities
from src.domains.connectors.discussion_projections import provider_reference, task_evidence
from src.domains.connectors.discussion_sources import TaskDiscussionSource
from src.domains.connectors.models import ConnectorType
from src.domains.shared.discussion_sources import (
    ResearchRequest,
    SourceKey,
    SourceReadRequest,
    SourceSnapshot,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 11, 10, 10, tzinfo=UTC)
OWNER = UUID(int=1)
KIND = ConnectorType.GOOGLE_TASKS


def _scope(container: str) -> str:
    return f"{KIND.value}:fictional-account:{container}"


def _request(
    *,
    operation: str = "recent",
    query: str | None = None,
    reference: str | None = None,
    item_limit: int = 5,
    call_limit: int = 8,
) -> SourceReadRequest:
    return SourceReadRequest(
        owner_id=OWNER,
        run_id=UUID(int=2),
        policy_revision=0,
        request=ResearchRequest(
            source=SourceKey.TASKS,
            operation="detail" if reference else operation,
            query=query,
            reference=reference,
            # A read that looks ahead names its dates (the request's own rule).
            start=NOW - timedelta(days=3) if operation == "future" else None,
            end=NOW + timedelta(days=7) if operation == "future" else None,
        ),
        now=NOW,
        window_start=NOW - timedelta(days=3),
        window_end=NOW + timedelta(days=7),
        allowed_sources=(SourceKey.TASKS,),
        item_limit=item_limit,
        item_max_chars=4000,
        call_limit=call_limit,
        timeout_seconds=10,
    )


def _task(task_id: str, due: str | None = None, **fields: Any) -> dict[str, Any]:
    return {
        "id": task_id,
        "title": f"Fictional {task_id}",
        **({"due": due} if due else {}),
        **fields,
    }


class _Door:
    """The shared door and the authority seam, recording what they were asked."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, pages: dict[str, Any]) -> None:
        self.pages = pages
        self.opened_with: list[dict[str, Any]] = []
        self.identity = "fictional-account"

        async def read(list_id: str, **_kwargs: Any) -> dict[str, Any]:
            answer = pages[list_id]
            if isinstance(answer, Exception):
                raise answer
            return {"items": [dict(task) for task in answer], "next_page_token": None}

        async def get(list_id: str, task_id: str) -> dict[str, Any]:
            held = pages.get(list_id) if list_id in pages else pages["home"]
            return next(dict(task) for task in held if task["id"] == task_id)

        self.client = MagicMock(
            list_tasks=AsyncMock(side_effect=read),
            get_task=AsyncMock(side_effect=get),
            list_task_lists=AsyncMock(
                side_effect=lambda limit: {
                    "items": [{"id": key, "title": key.title()} for key in list(pages)[:limit]],
                    "next_page_token": "more" if len(pages) > limit else None,
                }
            ),
        )

        @asynccontextmanager
        async def door(category: str, owner: UUID, **options: Any) -> Any:
            self.opened_with.append({"category": category, "owner": owner, **options})
            yield ActiveClient(client=self.client, connector_type=KIND, preferred_name=None)

        async def authorities(
            owner: UUID, kind: Any, client: Any, containers: Any
        ) -> dict[str, str]:
            return {name: f"{kind.value}:{self.identity}:{name}" for name in containers}

        monkeypatch.setattr(discussion_sources, "open_active_client", door)
        monkeypatch.setattr(discussion_tasks, "require_reader_authorities", authorities)

    async def read(self, **asked: Any) -> SourceSnapshot:
        return await TaskDiscussionSource().read(_request(**asked))


class TestEveryList:
    async def test_the_tasks_of_every_list_are_read_the_earliest_due_first(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        door = _Door(
            monkeypatch,
            {
                "home": [_task("later", "2026-11-20T00:00:00Z"), _task("undated")],
                "work": [_task("soon", "2026-11-12T00:00:00Z")],
            },
        )

        page = await door.read()

        assert [item.object_id for item in page.items] == ["soon", "later", "undated"]
        assert page.status == "ok" and not page.complete
        assert door.opened_with == [
            {"category": "tasks", "owner": OWNER, "fresh": True}
        ], "no default list is asked for"

    async def test_each_task_is_fenced_by_the_scope_of_its_own_list(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        door = _Door(monkeypatch, {"home": [_task("a")], "work": [_task("b")]})

        page = await door.read()

        fenced = {item.object_id: item.source_account for item in page.items}
        assert fenced == {"a": _scope("home"), "b": _scope("work")}
        assert {item.object_id: item.reference for item in page.items} == {
            "a": provider_reference(SourceKey.TASKS, _scope("home"), "a"),
            "b": provider_reference(SourceKey.TASKS, _scope("work"), "b"),
        }

    async def test_a_task_s_text_is_the_provider_s_record_whatever_list_it_came_from(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An admitted fact keeps its version: the list's name never enters the record."""
        raw = _task("a", "2026-11-12T00:00:00Z", notes="Fictional note")
        door = _Door(monkeypatch, {"home": [raw]})

        [item] = (await door.read()).items

        alone = task_evidence(raw, account=_scope("home"), now=NOW, chars=4000)
        assert (item.version, item.excerpt) == (alone.version, alone.excerpt)
        assert "Home" not in item.excerpt

    async def test_the_window_is_asked_of_every_list_when_the_read_looks_ahead(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        door = _Door(monkeypatch, {"home": [], "work": []})

        page = await door.read(operation="future")

        assert page.status == "empty"
        for asked in door.client.list_tasks.await_args_list:
            assert asked.kwargs["due_min"] == (NOW - timedelta(days=3)).isoformat()
            assert asked.kwargs["due_max"] == (NOW + timedelta(days=7)).isoformat()
            assert asked.kwargs["show_completed"] is True and asked.kwargs["show_hidden"] is False

    async def test_a_page_past_its_item_limit_is_truncated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        door = _Door(monkeypatch, {"home": [_task("a"), _task("b")], "work": [_task("c")]})

        page = await door.read(item_limit=2)

        assert len(page.items) == 2 and page.status == "truncated"

    async def test_a_query_filters_the_page_read(self, monkeypatch: pytest.MonkeyPatch) -> None:
        door = _Door(monkeypatch, {"home": [_task("alpha")], "work": [_task("beta")]})

        page = await door.read(query="BETA")

        assert [item.object_id for item in page.items] == ["beta"]


class TestTheReadsBudgetBoundsTheLists:
    async def test_one_call_lists_them_and_one_reads_each(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        door = _Door(monkeypatch, {"a": [_task("1")], "b": [_task("2")], "c": [_task("3")]})

        page = await door.read(call_limit=3)

        door.client.list_task_lists.assert_awaited_once_with(2)
        assert [asked.args[0] for asked in door.client.list_tasks.await_args_list] == ["a", "b"]
        assert page.status == "truncated", "more lists exist than the budget reads"

    async def test_a_budget_of_one_call_still_asks_for_a_list(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        door = _Door(monkeypatch, {"a": [_task("1")]})

        await door.read(call_limit=1)

        door.client.list_task_lists.assert_awaited_once_with(1)

    async def test_a_list_the_budget_stopped_leaves_the_others_and_truncates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        door = _Door(monkeypatch, {"a": [_task("1")], "b": ReadCallLimit("spent")})

        page = await door.read()

        assert [item.object_id for item in page.items] == ["1"]
        assert page.status == "truncated"

    async def test_nothing_beside_a_stopped_list_is_the_budget_s_refusal(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        door = _Door(monkeypatch, {"a": [], "b": ReadCallLimit("spent")})

        with pytest.raises(ReadCallLimit):
            await door.read()

    async def test_a_provider_s_failure_stays_the_read_s_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Set aside as a list unread, a backoff would never reach the gateway."""
        door = _Door(monkeypatch, {"a": [_task("1")], "b": TimeoutError()})

        with pytest.raises(TimeoutError):
            await door.read()


class TestAReference:
    async def test_it_is_read_back_in_the_list_it_was_minted_under(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        door = _Door(monkeypatch, {"home": [_task("a")], "work": [_task("b")]})
        minted = {item.object_id: item.reference for item in (await door.read()).items}

        page = await door.read(reference=minted["b"])

        door.client.get_task.assert_awaited_once_with("work", "b")
        assert page.status == "ok", "one task asked, one task read: nothing was cut"
        door.client.list_task_lists.assert_awaited_with(TASK_LIST_NAMES_SCAN_MAX)
        [item] = page.items
        assert (item.object_id, item.source_account, item.reference) == (
            "b",
            _scope("work"),
            minted["b"],
        )

    async def test_one_minted_under_the_provider_s_alias_is_still_read(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Before every list was read, an account with no default configured fenced under it."""
        door = _Door(monkeypatch, {"home": [_task("a")]})
        old = provider_reference(SourceKey.TASKS, _scope("@default"), "a")

        page = await door.read(reference=old)

        door.client.get_task.assert_awaited_once_with("@default", "a")
        assert page.items[0].reference == old

    async def test_another_account_s_reference_reads_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        door = _Door(monkeypatch, {"home": [_task("a")]})
        foreign = provider_reference(SourceKey.TASKS, "google_tasks:someone-else:home", "a")

        with pytest.raises(ValueError, match="no task list of this account"):
            await door.read(reference=foreign)

        door.client.get_task.assert_not_awaited()

    async def test_a_reference_of_a_list_that_is_gone_reads_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        door = _Door(monkeypatch, {"home": [_task("a")]})
        gone = provider_reference(SourceKey.TASKS, _scope("deleted-list"), "a")

        with pytest.raises(ValueError):
            await door.read(reference=gone)

        door.client.get_task.assert_not_awaited()


class TestTheAccountMustNotMoveWhileReading:
    @pytest.mark.parametrize("asked", [{}, {"reference": "x"}])
    async def test_a_changed_account_refuses_the_page(
        self, monkeypatch: pytest.MonkeyPatch, asked: dict[str, Any]
    ) -> None:
        door = _Door(monkeypatch, {"home": [_task("a")]})
        if asked:
            asked = {"reference": provider_reference(SourceKey.TASKS, _scope("home"), "a")}

        async def swap_account(list_id: str, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
            door.identity = "another-account"
            return {"items": [_task("a")], "next_page_token": None} if not _args else _task("a")

        door.client.list_tasks = AsyncMock(side_effect=swap_account)
        door.client.get_task = AsyncMock(side_effect=swap_account)

        with pytest.raises(ValueError, match="changed while reading"):
            await door.read(**asked)

    async def test_no_tasks_provider_is_a_closed_source(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        @asynccontextmanager
        async def door(*_args: Any, **_kwargs: Any) -> Any:
            yield ClientUnavailable.NO_CONNECTOR

        monkeypatch.setattr(discussion_sources, "open_active_client", door)

        page = await TaskDiscussionSource().read(_request())

        assert page.status != "ok" and page.items == ()


class TestOneScopeReadFencesEveryContainer:
    async def test_each_container_gets_what_a_read_of_it_alone_would(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.domains.connectors import discussion_authority

        scope_reads = AsyncMock(return_value="google_tasks:binding:policy")
        monkeypatch.setattr(discussion_authority, "read_connector_scope", scope_reads)
        monkeypatch.setattr(
            discussion_authority, "content_source_binding", lambda _client: "binding"
        )

        together = await require_reader_authorities(OWNER, KIND, object(), ["home", "work", ""])
        alone = {
            name: await discussion_authority.require_reader_authority(
                OWNER, KIND, object(), container=name
            )
            for name in ("home", "work", "")
        }

        assert together == alone
        assert len(set(together.values())) == 3, "each container has a scope of its own"
        assert scope_reads.await_count == 1 + 3, "one read for the three together"
