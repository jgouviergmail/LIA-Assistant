"""The workboard, from the chat (ADR-276, lot 3).

The tools hold no business rule, so what is worth testing is the SEAM between
words and the service:

- **a refusal travels as its CODE**, untouched. The frontend translates it and
  the model rephrases it; a sentence composed here would be right in one
  language and wrong in five.
- **« me », « lia » and a NAME are three different things**, and only the third
  needs resolving — by the service, which already owns who may hold a ticket.
- **``None`` means « not mentioned », never « clear it »**: passing it through
  would overwrite a schema default with nothing.
- **deletion ASKS first.** It returns a confirmation card and deletes on the
  approved replay — so an unattended run, where the gate refuses a ``draft``
  policy, deletes nothing at all.

The manifests are checked against the SETTINGS they publish: an enforced bound
the planner cannot read is a trap, not a contract (ADR-184).
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.config import settings
from src.core.exceptions import ResourceNotFoundError, ValidationError
from src.domains.agents.tools import workboard_tools
from src.domains.workboard.constants import STATUS_ORDER, WorkboardError

pytestmark = pytest.mark.unit

MODULE = "src.domains.agents.tools.workboard_tools"
USER = uuid.uuid4()


def _ticket_row(**overrides: Any) -> Any:
    values: dict[str, Any] = {
        "id": uuid.uuid4(),
        "owner_user_id": USER,
        "title": "Book the venue",
        "description": "Twelve people, the 20th.",
        "status": "todo",
        "priority": "medium",
        "assignee_kind": "human",
        "start_at": None,
        "due_at": None,
        "last_run_outcome": None,
        "last_run_at": None,
        "last_run_error": None,
        "last_run_cost_eur": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _runtime() -> Any:
    return SimpleNamespace(
        context=SimpleNamespace(user_id=str(USER), user_timezone="Europe/Paris"),
        config={"configurable": {"thread_id": "t"}},
        store=MagicMock(),
    )


@asynccontextmanager
async def _session(db: Any) -> Any:
    yield db


def _service(**methods: Any) -> Any:
    service = MagicMock()
    service.create = AsyncMock(return_value=_ticket_row())
    service.update = AsyncMock(return_value=_ticket_row(status="done"))
    service.run_now = AsyncMock(return_value=_ticket_row(status="todo"))
    service.comment = AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4()))
    service.delete = AsyncMock(return_value=3)
    service.resolve_reference = AsyncMock(return_value=_ticket_row())
    service.resolve_connected_user_id = AsyncMock(return_value=uuid.uuid4())
    service.board = AsyncMock(return_value=([_ticket_row()], 42, {"todo": 42}))
    service.get = AsyncMock(
        return_value=SimpleNamespace(ticket=_ticket_row(), children=[], comments=[], events=[])
    )
    service.deletable = AsyncMock(return_value=(_ticket_row(), 2))
    for name, value in methods.items():
        setattr(service, name, value)
    return service


@asynccontextmanager
async def _running(service: Any) -> Any:
    """Every boundary replaced: the session, the service and the account row."""
    db = AsyncMock()
    db.get = AsyncMock(return_value=SimpleNamespace(id=USER, is_active=True))
    with (
        patch(f"{MODULE}.get_db_context", lambda: _session(db)),
        patch(f"{MODULE}.WorkboardService", return_value=service),
        patch(f"{MODULE}.get_user_preferences", AsyncMock(return_value=("UTC", "fr", "fr-FR"))),
        patch(
            f"{MODULE}.validate_runtime_config",
            return_value=SimpleNamespace(user_id=str(USER), session_id="s", store=MagicMock()),
        ),
    ):
        yield service


class TestARefusalTravelsAsItsCode:
    async def test_a_validation_refusal_keeps_its_stable_code(self) -> None:
        service = _service(
            create=AsyncMock(side_effect=ValidationError(WorkboardError.TITLE_TOO_LONG.value))
        )
        async with _running(service):
            result = await workboard_tools.create_ticket_tool.coroutine(
                title="x", runtime=_runtime()
            )

        assert result.success is False
        assert WorkboardError.TITLE_TOO_LONG.value in result.message
        assert result.metadata["workboard_error"] == WorkboardError.TITLE_TOO_LONG.value

    async def test_an_unknown_ticket_is_a_not_found_not_an_invalid_input(self) -> None:
        service = _service(resolve_reference=AsyncMock(side_effect=ResourceNotFoundError("ticket")))
        async with _running(service):
            result = await workboard_tools.get_ticket_tool.coroutine(
                ticket="nothing", runtime=_runtime()
            )

        assert result.success is False
        assert result.error_code == "NOT_FOUND"

    async def test_no_french_sentence_is_composed_here(self) -> None:
        """The code is a translation key; a sentence would freeze one language
        into the payload the frontend renders."""
        service = _service(
            create=AsyncMock(side_effect=ValidationError(WorkboardError.TOO_MANY_TICKETS.value))
        )
        async with _running(service):
            result = await workboard_tools.create_ticket_tool.coroutine(
                title="x", runtime=_runtime()
            )

        assert result.message == WorkboardError.TOO_MANY_TICKETS.value


class TestWhoHoldsIt:
    async def test_me_and_lia_are_keywords_not_names(self) -> None:
        service = _service()
        async with _running(service):
            await workboard_tools.create_ticket_tool.coroutine(
                title="x", assignee="lia", runtime=_runtime()
            )

        service.resolve_connected_user_id.assert_not_awaited()
        assert service.create.await_args.args[1].assignee == "lia"

    async def test_anything_else_is_a_name_the_service_resolves(self) -> None:
        service = _service()
        async with _running(service):
            await workboard_tools.create_ticket_tool.coroutine(
                title="x", assignee="Marie", runtime=_runtime()
            )

        service.resolve_connected_user_id.assert_awaited_once()
        assert service.resolve_connected_user_id.await_args.args[1] == "Marie"
        assert service.create.await_args.args[1].assignee_user_id is not None

    async def test_a_name_matching_nobody_connected_refuses(self) -> None:
        service = _service(
            resolve_connected_user_id=AsyncMock(
                side_effect=ValidationError(WorkboardError.ASSIGNEE_NOT_CONNECTED.value)
            )
        )
        async with _running(service):
            result = await workboard_tools.create_ticket_tool.coroutine(
                title="x", assignee="Nobody", runtime=_runtime()
            )

        assert result.success is False
        assert WorkboardError.ASSIGNEE_NOT_CONNECTED.value in result.message

    async def test_the_keyword_is_read_case_insensitively(self) -> None:
        service = _service()
        async with _running(service):
            await workboard_tools.create_ticket_tool.coroutine(
                title="x", assignee=" LIA ", runtime=_runtime()
            )

        service.resolve_connected_user_id.assert_not_awaited()


class TestWhatWasNotSaidIsNotChanged:
    def test_none_means_not_mentioned(self) -> None:
        assert workboard_tools._optional(a=None, b="x", c=False) == {"b": "x", "c": False}

    async def test_an_update_touches_only_what_was_given(self) -> None:
        service = _service()
        async with _running(service):
            await workboard_tools.update_ticket_tool.coroutine(
                ticket="Book the venue", status="done", runtime=_runtime()
            )

        changes = service.update.await_args.args[2]
        assert changes.status == "done"
        assert changes.priority is None
        assert changes.title is None

    async def test_run_now_is_a_second_call_not_a_field(self) -> None:
        service = _service()
        async with _running(service):
            await workboard_tools.update_ticket_tool.coroutine(
                ticket="Book the venue", run_now=True, runtime=_runtime()
            )

        service.run_now.assert_awaited_once()

    async def test_without_run_now_nothing_is_launched(self) -> None:
        service = _service()
        async with _running(service):
            await workboard_tools.update_ticket_tool.coroutine(
                ticket="Book the venue", status="todo", runtime=_runtime()
            )

        service.run_now.assert_not_awaited()


class TestDeletionAsksFirst:
    """The native shape of every destructive tool: a draft, then an executor."""

    async def test_the_tool_returns_a_draft_and_deletes_nothing(self) -> None:
        service = _service()
        async with _running(service):
            result = await workboard_tools.delete_ticket_tool.coroutine(
                ticket="Book the venue", runtime=_runtime()
            )

        service.delete.assert_not_awaited()
        assert result.metadata.get("requires_confirmation") is True
        assert result.metadata.get("draft_type") == "ticket_delete"

    async def test_the_draft_names_the_ticket_and_its_steps(self) -> None:
        """What the person confirms must be what goes: the title they know
        and how many steps follow it out."""
        service = _service(deletable=AsyncMock(return_value=(_ticket_row(), 2)))
        async with _running(service):
            result = await workboard_tools.delete_ticket_tool.coroutine(
                ticket="Book the venue", runtime=_runtime()
            )

        draft = next(iter(result.registry_updates.values()))
        content = draft.data if hasattr(draft, "data") else draft
        payload = getattr(content, "content", None) or content
        text = str(payload)
        assert "Book the venue" in text
        assert "2" in text

    async def test_a_holder_is_refused_before_being_asked(self) -> None:
        """A card a person could only ever have refused is a question with
        one answer — the rights check comes first."""
        service = _service(
            deletable=AsyncMock(
                side_effect=ValidationError(WorkboardError.PEER_CANNOT_DELETE.value)
            )
        )
        async with _running(service):
            result = await workboard_tools.delete_ticket_tool.coroutine(
                ticket="Book the venue", runtime=_runtime()
            )

        assert result.success is False
        assert WorkboardError.PEER_CANNOT_DELETE.value in result.message

    async def test_the_executor_deletes_on_the_confirmed_replay(self) -> None:
        service = _service()
        async with _running(service):
            result = await workboard_tools.execute_ticket_delete_draft(
                {"ticket_id": str(uuid.uuid4()), "title": "Book the venue", "children": 2},
                USER,
                None,
            )

        service.delete.assert_awaited_once()
        assert result["success"] is True
        assert result["deleted"] == 3
        # The success sentence (« Ticket '…' supprimé ») reads the title from
        # the RESULT: an executor that drops it renders an empty quote.
        assert result["title"] == "Book the venue"

    async def test_the_executor_re_checks_the_rights(self) -> None:
        """An arbitrary delay separates the question from the answer, and the
        ticket may have changed hands in between."""
        service = _service(
            delete=AsyncMock(side_effect=ValidationError(WorkboardError.PEER_CANNOT_DELETE.value))
        )
        async with _running(service):
            result = await workboard_tools.execute_ticket_delete_draft(
                {"ticket_id": str(uuid.uuid4()), "title": "x", "children": 0}, USER, None
            )

        assert result["success"] is False
        assert WorkboardError.PEER_CANNOT_DELETE.value in result["error"]

    def test_the_executor_is_registered_for_its_draft_type(self) -> None:
        """A confirmed draft must always resolve to an executor."""
        from src.domains.agents.drafts.models import DraftType
        from src.domains.agents.services.draft_executor_registry import (
            ensure_executors_registered,
        )
        from src.domains.agents.services.draft_executor_types import EXECUTOR_REGISTRY

        ensure_executors_registered()
        registered = EXECUTOR_REGISTRY[DraftType.TICKET_DELETE.value]
        # The registry installs the effect gate AROUND the executor — the
        # executor is what claims and settles the deletion (ADR-263) — so what
        # it holds is a wrapper whose `__wrapped__` is ours.
        assert getattr(registered, "__wrapped__", registered) is (
            workboard_tools.execute_ticket_delete_draft
        )


class TestDatesAreThePersons:
    async def test_a_date_is_normalised_in_the_persons_zone(self) -> None:
        """The first version read an attribute the context does not have and
        normalised every date in UTC — a 9 a.m. start became 11 a.m. in Paris."""
        service = _service()
        preferences = AsyncMock(return_value=("Europe/Paris", "fr", "fr-FR"))
        async with _running(service):
            with patch(f"{MODULE}.get_user_preferences", preferences):
                await workboard_tools.create_ticket_tool.coroutine(
                    title="x", start_at="2026-09-10T09:00:00", runtime=_runtime()
                )

        preferences.assert_awaited_once()
        start_at = service.create.await_args.args[1].start_at
        assert start_at is not None
        assert start_at.utcoffset() is not None
        assert start_at.hour == 9 and start_at.utcoffset().total_seconds() == 2 * 3600


class TestReading:
    async def test_the_total_is_the_aggregate_not_the_page_length(self) -> None:
        """A count shown to somebody is exact or it does not exist (ADR-185)."""
        service = _service()
        async with _running(service):
            result = await workboard_tools.list_tickets_tool.coroutine(runtime=_runtime())

        assert result.structured_data["total"] == 42
        assert len(result.structured_data["tickets"]) == 1
        assert result.structured_data["counts"] == {"todo": 42}

    async def test_a_page_is_bounded_whatever_the_model_asks_for(self) -> None:
        service = _service()
        async with _running(service):
            await workboard_tools.list_tickets_tool.coroutine(limit=9999, runtime=_runtime())

        assert service.board.await_args.kwargs["limit"] == 100

    async def test_an_unknown_side_reads_the_whole_board(self) -> None:
        """A filter the model mis-spelled must not turn « what is on my board »
        into an error message."""
        assert workboard_tools._board_side("invented") == "all"
        assert workboard_tools._board_side(None) == "all"
        assert workboard_tools._board_side("lia") == "lia"

    async def test_one_ticket_comes_back_with_its_run(self) -> None:
        service = _service(
            get=AsyncMock(
                return_value=SimpleNamespace(
                    ticket=_ticket_row(last_run_outcome="success"),
                    children=[_ticket_row(title="Step one")],
                    comments=[SimpleNamespace(author_kind="lia", body="Done.")],
                    events=[],
                )
            )
        )
        async with _running(service):
            result = await workboard_tools.get_ticket_tool.coroutine(
                ticket="Book the venue", runtime=_runtime()
            )

        assert result.structured_data["last_run"]["outcome"] == "success"
        assert result.structured_data["children"][0]["title"] == "Step one"
        assert result.structured_data["comments"][0]["author"] == "lia"


class TestTheContextSystemKnowsATicket:
    """The plan's task 2: an item type and a context key, so a ticket can be
    pointed at after the turn that listed it (« passe le deuxième en cours »)."""

    async def test_a_listing_offers_every_ticket_to_the_registry_by_its_id(self) -> None:
        first, second = _ticket_row(title="First"), _ticket_row(title="Second")
        service = _service(board=AsyncMock(return_value=([first, second], 2, {"todo": 2})))
        async with _running(service):
            result = await workboard_tools.list_tickets_tool.coroutine(runtime=_runtime())

        from src.domains.agents.data_registry.models import RegistryItemType

        assert list(result.registry_updates) == [str(first.id), str(second.id)]
        item = result.registry_updates[str(second.id)]
        assert item.type is RegistryItemType.TICKET
        # The key IS the payload id: what the FOR_EACH filter compares.
        assert item.payload["id"] == item.id
        assert item.payload["title"] == "Second"
        assert item.meta.domain == "tickets"
        assert item.meta.tool_name == "list_tickets_tool"
        assert result.context_save_mode is None  # a listing: the default LIST

    async def test_a_read_makes_the_ticket_current_without_touching_the_list(self) -> None:
        """« celui-là » is the ticket just read; « le deuxième » stays the board."""
        from src.domains.agents.context.schemas import ContextSaveMode

        ticket = _ticket_row(title="Read me")
        service = _service(
            get=AsyncMock(
                return_value=SimpleNamespace(
                    ticket=ticket, children=[_ticket_row(title="Step")], comments=[], events=[]
                )
            )
        )
        async with _running(service):
            result = await workboard_tools.get_ticket_tool.coroutine(
                ticket="Read me", runtime=_runtime()
            )

        assert list(result.registry_updates) == [str(ticket.id)]
        assert result.context_save_mode is ContextSaveMode.CURRENT
        # The registry payload is the BOUNDED view: no description.
        assert "description" not in result.registry_updates[str(ticket.id)].payload
        assert result.structured_data["ticket"]["description"] == "Twelve people, the 20th."

    def test_the_context_type_is_registered_on_the_domains_result_key(self) -> None:
        from src.domains.agents.constants import AGENT_TICKET, CONTEXT_DOMAIN_TICKETS
        from src.domains.agents.context.registry import ContextTypeRegistry
        from src.domains.agents.registry.domain_taxonomy import get_result_key

        definition = ContextTypeRegistry.get_definition(CONTEXT_DOMAIN_TICKETS)
        assert definition.agent_name == AGENT_TICKET
        assert definition.primary_id_field == "id"
        assert definition.display_name_field == "title"
        # One name for the collection: the store, the plan reference and the
        # manifests must not spell it three ways.
        assert get_result_key("ticket") == CONTEXT_DOMAIN_TICKETS

    def test_the_read_manifests_declare_the_key_and_the_write_ones_do_not(self) -> None:
        from src.domains.agents.constants import CONTEXT_DOMAIN_TICKETS
        from src.domains.agents.registry.catalogue import ToolManifest
        from src.domains.agents.workboard import catalogue_manifests

        manifests = [m for m in vars(catalogue_manifests).values() if isinstance(m, ToolManifest)]
        keys = {m.name: m.context_key for m in manifests}
        assert keys["list_tickets_tool"] == CONTEXT_DOMAIN_TICKETS
        assert keys["get_ticket_tool"] == CONTEXT_DOMAIN_TICKETS
        assert all(
            keys[name] is None
            for name in (
                "create_ticket_tool",
                "update_ticket_tool",
                "comment_ticket_tool",
                "delete_ticket_tool",
            )
        )

    def test_a_confirmed_deletion_is_synced_out_of_the_context(self) -> None:
        from src.domains.agents.services.draft_executor import (
            _DRAFT_TYPE_TO_ID_KEYS,
            _DRAFT_TYPE_TO_TCM_DOMAIN,
        )

        assert _DRAFT_TYPE_TO_TCM_DOMAIN["ticket_delete"] == "tickets"
        assert _DRAFT_TYPE_TO_ID_KEYS["ticket_delete"] == ("ticket_id",)

    @pytest.mark.parametrize("language", ["fr", "en", "es", "de", "it", "zh-CN"])
    def test_the_summary_block_has_a_heading_for_tickets(self, language: str) -> None:
        from src.domains.agents.formatters.text_summary import DOMAIN_LABELS

        assert DOMAIN_LABELS[language]["tickets"]
        # Side by side in one prompt block, the two headings must differ.
        assert DOMAIN_LABELS[language]["tickets"] != DOMAIN_LABELS[language]["tasks"]


class TestTheManifestsPublishWhatTheServiceEnforces:
    """ADR-184: whatever a validator can reject, its producer must be able to
    read. Compared against the SETTINGS, so a `.env` change moves both."""

    @staticmethod
    def _bound(manifest: Any, parameter: str, kind: str) -> Any:
        schema = next(p for p in manifest.parameters if p.name == parameter)
        return next(c.value for c in schema.constraints if c.kind == kind)

    def test_the_title_bound_is_the_one_that_is_enforced(self) -> None:
        from src.domains.agents.workboard.catalogue_manifests import (
            create_ticket_catalogue_manifest,
        )

        assert (
            self._bound(create_ticket_catalogue_manifest, "title", "max_length")
            == settings.workboard_title_max_chars
        )

    def test_the_description_bound_is_the_one_that_is_enforced(self) -> None:
        from src.domains.agents.workboard.catalogue_manifests import (
            create_ticket_catalogue_manifest,
        )

        assert (
            self._bound(create_ticket_catalogue_manifest, "description", "max_length")
            == settings.workboard_description_max_chars
        )

    def test_the_comment_bound_is_the_one_that_is_enforced(self) -> None:
        from src.domains.agents.workboard.catalogue_manifests import (
            comment_ticket_catalogue_manifest,
        )

        assert (
            self._bound(comment_ticket_catalogue_manifest, "body", "max_length")
            == settings.workboard_comment_max_chars
        )

    def test_every_column_the_board_has_is_offered(self) -> None:
        """A model offered a column the API refuses is a model set up to fail;
        one the API accepts but the model never sees is a column nobody uses."""
        from src.domains.agents.workboard.catalogue_manifests import (
            create_ticket_catalogue_manifest,
            list_tickets_catalogue_manifest,
            update_ticket_catalogue_manifest,
        )

        for manifest in (
            create_ticket_catalogue_manifest,
            update_ticket_catalogue_manifest,
            list_tickets_catalogue_manifest,
        ):
            offered = self._bound(manifest, "status", "enum")
            assert sorted(offered) == sorted(STATUS_ORDER), manifest.name

    def test_the_agent_owns_exactly_the_six_tools(self) -> None:
        from src.domains.agents.workboard.catalogue_manifests import TICKET_AGENT_MANIFEST

        assert sorted(TICKET_AGENT_MANIFEST.tools) == [
            "comment_ticket_tool",
            "create_ticket_tool",
            "delete_ticket_tool",
            "get_ticket_tool",
            "list_tickets_tool",
            "update_ticket_tool",
        ]

    def test_the_description_tells_the_three_neighbours_apart(self) -> None:
        """A ticket is confused with a provider to-do, a reminder and a
        routine; the router has only these sentences to separate them."""
        from src.domains.agents.workboard.catalogue_manifests import (
            create_ticket_catalogue_manifest,
        )

        described = create_ticket_catalogue_manifest.description.lower()
        assert "task" in described
        assert "reminder" in described
        assert "automation" in described
