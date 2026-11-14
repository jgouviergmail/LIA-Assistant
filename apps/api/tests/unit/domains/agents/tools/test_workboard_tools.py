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
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import ResourceNotFoundError, ValidationError
from src.core.i18n import SUPPORTED_LANGUAGES
from src.core.i18n_workboard_categories import WORKBOARD_CATEGORY_PLACES
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.workboard_create_schemas import (
    WorkboardCreateInput,
    WorkboardCreatePatch,
    WorkboardCreateSelection,
)
from src.domains.agents.application.workboard_create_spec import WORKBOARD_CREATE_OPERATION
from src.domains.agents.application.workboard_delete_schemas import (
    WorkboardDeleteInput,
    WorkboardDeletePatch,
    WorkboardDeleteSelection,
    WorkboardDeleteTarget,
)
from src.domains.agents.application.workboard_delete_spec import WORKBOARD_DELETE_OPERATION
from src.domains.agents.tools import workboard_tools
from src.domains.agents.workboard.category_manifest import categories_managed_from
from src.domains.users.models import User
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
        "category_id": None,
        "start_at": None,
        "due_at": None,
        "last_run_outcome": None,
        "last_run_at": None,
        "last_run_error": None,
        "last_run_cost_eur": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


#: The language the fake turn of these tests runs in.
RUNTIME_LANGUAGE = "fr"


def _runtime() -> Any:
    return SimpleNamespace(
        context=SimpleNamespace(
            user_id=str(USER), user_timezone="Europe/Paris", language=RUNTIME_LANGUAGE
        ),
        config={"configurable": {"thread_id": "t"}},
        store=MagicMock(),
    )


@asynccontextmanager
async def _session(db: Any) -> Any:
    yield db


def _service(**methods: Any) -> Any:
    service = MagicMock()
    service.create = AsyncMock(return_value=_ticket_row())
    service.validate_creation = AsyncMock()
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
    service.repo.count_visible = AsyncMock(side_effect=lambda identities, actor_id: len(identities))
    service.repo.get_visible = AsyncMock(return_value=_ticket_row())
    service.deletable = AsyncMock(return_value=(_ticket_row(), 2))
    service.categories.names_for = AsyncMock(return_value={})
    service.categories.own_named = AsyncMock(return_value=uuid.uuid4())
    service.categories.visible_named = AsyncMock(return_value=(uuid.uuid4(),))
    service.categories.lanes = AsyncMock(return_value=[])
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
        patch(f"{MODULE}.creation_access", AsyncMock(return_value=User(id=USER, is_active=True))),
        patch(
            f"{MODULE}.validate_runtime_config",
            return_value=SimpleNamespace(user_id=str(USER), session_id="s", store=MagicMock()),
        ),
    ):
        yield service


@asynccontextmanager
async def _creation_running(service: MagicMock) -> AsyncIterator[MagicMock]:
    """Adapter unit tests observe source validation, while real HITL is SQL-tested separately."""
    actor = User(id=USER, is_active=True)
    db = AsyncMock(spec=AsyncSession)

    async def prepare(
        db: AsyncSession,
        owner: uuid.UUID,
        request: WorkboardCreateInput,
        *,
        command_id: uuid.UUID | None = None,
    ) -> ApplicationActionDraftContent:
        await service.validate_creation(actor, request)
        selected = WorkboardCreateSelection(
            request=request,
            assignee_kind="lia" if request.assignee == "lia" else "human",
            holder_id=request.assignee_user_id,
            holder_name=None,
            parent_title=None,
            owned_count=0,
            max_tickets=5,
            state_digest="e" * 64,
        )
        return build_action_content(
            owner,
            WORKBOARD_CREATE_OPERATION,
            WorkboardCreatePatch(workboard_create=selected),
            {"workboard_create": selected.public_scope()},
            {"workboard_create": selected.public_scope(after=True)},
            command_id=command_id,
        )

    boundary = "src.domains.agents.tools.workboard_creation_tool"
    with (
        patch(f"{boundary}.get_db_context", lambda: _session(db)),
        patch(f"{boundary}.WorkboardService", return_value=service),
        patch(f"{boundary}.creation_access", AsyncMock(return_value=actor)),
        patch(f"{boundary}.prepare_workboard_creation", prepare),
        patch(f"{boundary}.save_command", AsyncMock()),
        patch(f"{boundary}.get_user_preferences", AsyncMock(return_value=("UTC", "fr", "fr-FR"))),
        patch(
            f"{boundary}.validate_runtime_config", return_value=SimpleNamespace(user_id=str(USER))
        ),
    ):
        yield service
        service.create.assert_not_awaited()


@asynccontextmanager
async def _deletion_running(service: MagicMock) -> AsyncIterator[MagicMock]:
    """Observe source resolution/refusal; the real subtree and HITL have SQL oracles."""
    actor = User(id=USER, is_active=True)
    db = AsyncMock(spec=AsyncSession)

    async def prepare(
        db: AsyncSession, owner: uuid.UUID, request: WorkboardDeleteInput
    ) -> ApplicationActionDraftContent:
        row, children = await service.deletable(actor, request.ticket_id)
        selected = WorkboardDeleteSelection(
            request=request,
            items=[
                WorkboardDeleteTarget(
                    ticket_id=request.ticket_id,
                    title=row.title,
                    status=row.status,
                    running=False,
                    has_pending_action=False,
                )
            ]
            + [
                WorkboardDeleteTarget(
                    ticket_id=uuid.uuid4(),
                    title=f"Step {index}",
                    status="todo",
                    running=False,
                    has_pending_action=False,
                )
                for index in range(children)
            ],
            comments=0,
            events=0,
            owned_count=children + 1,
            state_digest="e" * 64,
        )
        return build_action_content(
            owner,
            WORKBOARD_DELETE_OPERATION,
            WorkboardDeletePatch(workboard_delete=selected),
            {"workboard_delete": selected.public_scope()},
            {"workboard_delete": selected.public_scope(after=True)},
        )

    boundary = "src.domains.agents.tools.workboard_delete_tool"
    common = "src.domains.agents.application.native_tool_preparation"
    with (
        patch(f"{boundary}.get_db_context", lambda: _session(db)),
        patch(f"{boundary}.WorkboardService", return_value=service),
        patch(f"{boundary}.creation_access", AsyncMock(return_value=actor)),
        patch(f"{boundary}.prepare_workboard_delete", prepare),
        patch(f"{common}.save_command", AsyncMock()),
        patch(f"{common}.validate_runtime_config", return_value=SimpleNamespace(user_id=str(USER))),
    ):
        yield service
        service.delete.assert_not_awaited()


@asynccontextmanager
async def _update_running(service: MagicMock, prepared: Any = None) -> AsyncIterator[MagicMock]:
    """The update tool up to the source preparation; the real HITL is SQL-tested apart.

    Args:
        service: The stubbed workboard service — it resolves the words.
        prepared: What the source preparation does once the words are fields;
            by default it is never reached.
    """
    actor = User(id=USER, is_active=True)
    db = AsyncMock(spec=AsyncSession)
    boundary = "src.domains.agents.tools.workboard_update_tool"
    common = "src.domains.agents.application.native_tool_preparation"
    validated = SimpleNamespace(user_id=str(USER))
    with (
        patch(f"{boundary}.get_db_context", lambda: _session(db)),
        patch(f"{boundary}.WorkboardService", return_value=service),
        patch(f"{boundary}.creation_access", AsyncMock(return_value=actor)),
        patch(f"{boundary}.prepare_workboard_update", prepared or AsyncMock()),
        patch(f"{boundary}.get_user_preferences", AsyncMock(return_value=("UTC", "fr", "fr-FR"))),
        patch(f"{boundary}.validate_runtime_config", return_value=validated),
        patch(f"{common}.validate_runtime_config", return_value=validated),
        patch(f"{common}.save_command", AsyncMock()),
    ):
        yield service
        service.update.assert_not_awaited()


@asynccontextmanager
async def _comment_running(service: MagicMock, prepared: Any = None) -> AsyncIterator[MagicMock]:
    """The comment tool up to the source preparation; the real flow is SQL-tested apart.

    Args:
        service: The stubbed workboard service — it resolves the ticket.
        prepared: What the source preparation does once the ticket is known;
            by default it is never reached.
    """
    actor = User(id=USER, is_active=True)
    db = AsyncMock(spec=AsyncSession)
    boundary = "src.domains.agents.tools.workboard_comment_tool"
    common = "src.domains.agents.application.native_tool_preparation"
    with (
        patch(f"{boundary}.get_db_context", lambda: _session(db)),
        patch(f"{boundary}.WorkboardService", return_value=service),
        patch(f"{boundary}.creation_access", AsyncMock(return_value=actor)),
        patch(f"{boundary}.prepare_workboard_comment", prepared or AsyncMock()),
        patch(f"{common}.save_command", AsyncMock()),
        patch(f"{common}.validate_runtime_config", return_value=SimpleNamespace(user_id=str(USER))),
    ):
        yield service
        service.comment.assert_not_awaited()


class TestARefusalTravelsAsItsCode:
    async def test_a_validation_refusal_keeps_its_stable_code(self) -> None:
        service = _service(
            validate_creation=AsyncMock(
                side_effect=ValidationError(WorkboardError.TITLE_TOO_LONG.value)
            )
        )
        async with _creation_running(service):
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
            validate_creation=AsyncMock(
                side_effect=ValidationError(WorkboardError.TOO_MANY_TICKETS.value)
            )
        )
        async with _creation_running(service):
            result = await workboard_tools.create_ticket_tool.coroutine(
                title="x", runtime=_runtime()
            )

        assert result.message == WorkboardError.TOO_MANY_TICKETS.value


class TestWhoHoldsIt:
    async def test_me_and_lia_are_keywords_not_names(self) -> None:
        service = _service()
        async with _creation_running(service):
            await workboard_tools.create_ticket_tool.coroutine(
                title="x", assignee="lia", runtime=_runtime()
            )

        service.resolve_connected_user_id.assert_not_awaited()
        assert service.validate_creation.await_args.args[1].assignee == "lia"

    async def test_anything_else_is_a_name_the_service_resolves(self) -> None:
        service = _service()
        async with _creation_running(service):
            await workboard_tools.create_ticket_tool.coroutine(
                title="x", assignee="Marie", runtime=_runtime()
            )

        service.resolve_connected_user_id.assert_awaited_once()
        assert service.resolve_connected_user_id.await_args.args[1] == "Marie"
        assert service.validate_creation.await_args.args[1].assignee_user_id is not None

    async def test_a_name_matching_nobody_connected_refuses(self) -> None:
        service = _service(
            resolve_connected_user_id=AsyncMock(
                side_effect=ValidationError(WorkboardError.ASSIGNEE_NOT_CONNECTED.value)
            )
        )
        async with _creation_running(service):
            result = await workboard_tools.create_ticket_tool.coroutine(
                title="x", assignee="Nobody", runtime=_runtime()
            )

        assert result.success is False
        assert WorkboardError.ASSIGNEE_NOT_CONNECTED.value in result.message

    async def test_the_keyword_is_read_case_insensitively(self) -> None:
        service = _service()
        async with _creation_running(service):
            await workboard_tools.create_ticket_tool.coroutine(
                title="x", assignee=" LIA ", runtime=_runtime()
            )

        service.resolve_connected_user_id.assert_not_awaited()


class TestDeletionAsksFirst:
    """The native shape of every destructive tool: a draft, then an executor."""

    async def test_the_tool_returns_a_draft_and_deletes_nothing(self) -> None:
        service = _service()
        async with _deletion_running(service):
            result = await workboard_tools.delete_ticket_tool.coroutine(
                ticket="Book the venue", runtime=_runtime()
            )

        service.delete.assert_not_awaited()
        assert result.metadata.get("requires_confirmation") is True
        assert result.metadata.get("draft_type") == "application_action"

    async def test_the_draft_names_the_ticket_and_its_steps(self) -> None:
        """What the person confirms must be what goes: the title they know
        and how many steps follow it out."""
        service = _service(deletable=AsyncMock(return_value=(_ticket_row(), 2)))
        async with _deletion_running(service):
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
        async with _deletion_running(service):
            result = await workboard_tools.delete_ticket_tool.coroutine(
                ticket="Book the venue", runtime=_runtime()
            )

        assert result.success is False and not result.registry_updates
        # Said by its code: « not yours to delete » is not « no such ticket ».
        assert result.message == WorkboardError.PEER_CANNOT_DELETE.value
        assert result.error_code == "CONSTRAINT_VIOLATION"

    async def test_legacy_executor_refuses_without_deleting(self) -> None:
        service = _service()
        async with _running(service):
            result = await workboard_tools.execute_ticket_delete_draft(
                {"ticket_id": str(uuid.uuid4()), "title": "Book the venue", "children": 2},
                USER,
                None,
            )

        service.delete.assert_not_awaited()
        assert result == {"success": False, "error": "STALE_STATE"}

    async def test_legacy_executor_never_attempts_source_mutation(self) -> None:
        service = _service(
            delete=AsyncMock(side_effect=ValidationError(WorkboardError.PEER_CANNOT_DELETE.value))
        )
        async with _running(service):
            result = await workboard_tools.execute_ticket_delete_draft(
                {"ticket_id": str(uuid.uuid4()), "title": "x", "children": 0}, USER, None
            )

        assert result["success"] is False
        assert result["error"] == "STALE_STATE"
        service.delete.assert_not_awaited()

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
        async with _creation_running(service):
            with patch(
                "src.domains.agents.tools.workboard_creation_tool.get_user_preferences", preferences
            ):
                await workboard_tools.create_ticket_tool.coroutine(
                    title="x", start_at="2026-09-10T09:00:00", runtime=_runtime()
                )

        preferences.assert_awaited_once()
        start_at = service.validate_creation.await_args.args[1].start_at
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
        from src.domains.agents.data_registry.card_payload import card_payload
        from src.domains.agents.display.components.base import RenderContext
        from src.domains.agents.display.components.snapshot_cards import TicketCard

        item = next(iter(result.registry_updates.values()))
        markup = TicketCard().render(card_payload(item), RenderContext(language="en"))
        for fact in ("Twelve people", "Step one", "Done."):
            assert fact in markup
        assert "description" not in item.payload


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

    def test_a_shown_ticket_is_designated_by_its_category_when_no_title_matches(self) -> None:
        """« The one in Home » — a category is not an identity (several tickets
        share it), so it is read only when no title carries the words, and two
        tickets of one category stay two: the chat then asks which."""
        from src.domains.agents.constants import CONTEXT_DOMAIN_TICKETS
        from src.domains.agents.context.descriptor_match import items_matching
        from src.domains.agents.context.registry import ContextTypeRegistry

        definition = ContextTypeRegistry.get_definition(CONTEXT_DOMAIN_TICKETS)
        shown = [
            {"id": "1", "title": "Paint the hall", "status": "todo", "category": "Home"},
            {"id": "2", "title": "Call the bank", "status": "todo", "category": "Work"},
            {"id": "3", "title": "Home insurance", "status": "todo", "category": None},
            {"id": "4", "title": "Fix the tap", "status": "todo", "category": "Home"},
        ]

        # A title wins: the category is read only when no identity matches.
        assert [item["id"] for item in items_matching("home", shown, definition)] == ["3"]
        assert [item["id"] for item in items_matching("work", shown, definition)] == ["2"]
        without_title = [item for item in shown if item["id"] != "3"]
        assert [item["id"] for item in items_matching("home", without_title, definition)] == [
            "1",
            "4",
        ]

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

    def test_the_agent_owns_exactly_the_seven_tools(self) -> None:
        from src.domains.agents.workboard.catalogue_manifests import TICKET_AGENT_MANIFEST

        assert sorted(TICKET_AGENT_MANIFEST.tools) == [
            "comment_ticket_tool",
            "create_ticket_tool",
            "delete_ticket_tool",
            "get_ticket_tool",
            "list_ticket_categories_tool",
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


def _lane(name: str | None, owner: uuid.UUID | None, **counts: int) -> Any:
    """One lane as the category rules hand it out."""
    return SimpleNamespace(
        category_id=None if name is None else uuid.uuid4(),
        name=name,
        owner_user_id=owner,
        counts_by_status=counts,
    )


class TestTheCategoryOfATicket:
    """The assistant reads a ticket's category, narrows the board to one and
    files a ticket under one — by its NAME. It administers none: creating,
    renaming, reordering and deleting a category stay on the board
    (owner arbitration, 2026-11-11)."""

    async def test_a_listing_names_the_category_of_each_ticket(self) -> None:
        home = uuid.uuid4()
        filed, loose = _ticket_row(category_id=home), _ticket_row(title="Sort the mail")
        service = _service(board=AsyncMock(return_value=([filed, loose], 2, {"todo": 2})))
        service.categories.names_for = AsyncMock(return_value={home: "Home"})
        async with _running(service):
            result = await workboard_tools.list_tickets_tool.coroutine(runtime=_runtime())

        assert [row["category"] for row in result.structured_data["tickets"]] == ["Home", None]
        # ONE question for the page, about the rows it read.
        service.categories.names_for.assert_awaited_once_with(USER, [filed, loose])
        # The context keeps it too: « the one in Home » must stay answerable.
        assert [item.payload["category"] for item in result.registry_updates.values()] == [
            "Home",
            None,
        ]

    async def test_the_board_is_narrowed_to_a_category_by_its_name(self) -> None:
        ids = (uuid.uuid4(), uuid.uuid4())
        service = _service()
        service.categories.visible_named = AsyncMock(return_value=ids)
        async with _running(service):
            await workboard_tools.list_tickets_tool.coroutine(category="Home", runtime=_runtime())

        service.categories.visible_named.assert_awaited_once_with(USER, "Home")
        filters = service.board.await_args.args[1]
        assert filters.categories == ids
        assert filters.uncategorized is False

    async def test_the_board_is_narrowed_to_what_is_not_filed(self) -> None:
        service = _service()
        async with _running(service):
            await workboard_tools.list_tickets_tool.coroutine(
                uncategorized=True, runtime=_runtime()
            )

        service.categories.visible_named.assert_not_awaited()
        filters = service.board.await_args.args[1]
        assert filters.categories is None
        assert filters.uncategorized is True

    async def test_no_category_asked_narrows_nothing(self) -> None:
        service = _service()
        async with _running(service):
            await workboard_tools.list_tickets_tool.coroutine(runtime=_runtime())

        filters = service.board.await_args.args[1]
        assert filters.categories is None and filters.uncategorized is False

    async def test_an_unknown_category_is_refused_by_code_never_an_empty_page(self) -> None:
        """« No ticket in Garden » and « no category Garden » are not one answer."""
        service = _service()
        service.categories.visible_named = AsyncMock(
            side_effect=ValidationError(WorkboardError.CATEGORY_UNKNOWN.value)
        )
        async with _running(service):
            result = await workboard_tools.list_tickets_tool.coroutine(
                category="Garden", runtime=_runtime()
            )

        assert result.success is False
        assert result.error_code == "INVALID_INPUT"
        assert result.metadata["workboard_error"] == WorkboardError.CATEGORY_UNKNOWN.value
        service.board.assert_not_awaited()

    async def test_one_ticket_comes_back_with_its_category_and_its_steps_theirs(self) -> None:
        home, work = uuid.uuid4(), uuid.uuid4()
        ticket = _ticket_row(category_id=home)
        step = _ticket_row(title="Step one", category_id=work)
        service = _service(
            get=AsyncMock(
                return_value=SimpleNamespace(ticket=ticket, children=[step], comments=[], events=[])
            )
        )
        service.categories.names_for = AsyncMock(return_value={home: "Home", work: "Work"})
        async with _running(service):
            result = await workboard_tools.get_ticket_tool.coroutine(
                ticket="Book the venue", runtime=_runtime()
            )

        assert result.structured_data["ticket"]["category"] == "Home"
        assert result.structured_data["children"][0]["category"] == "Work"
        service.categories.names_for.assert_awaited_once_with(USER, [ticket, step])

    async def test_a_ticket_is_created_in_the_category_named(self) -> None:
        home = uuid.uuid4()
        service = _service()
        service.categories.own_named = AsyncMock(return_value=home)
        async with _creation_running(service):
            await workboard_tools.create_ticket_tool.coroutine(
                title="Paint the hall", category="Home", runtime=_runtime()
            )

        service.categories.own_named.assert_awaited_once_with(USER, "Home")
        assert service.validate_creation.await_args.args[1].category_id == home

    async def test_a_ticket_created_with_no_category_asks_nothing(self) -> None:
        service = _service()
        async with _creation_running(service):
            await workboard_tools.create_ticket_tool.coroutine(title="x", runtime=_runtime())

        service.categories.own_named.assert_not_awaited()
        assert service.validate_creation.await_args.args[1].category_id is None

    async def test_creating_under_a_category_the_user_does_not_have_refuses(self) -> None:
        service = _service()
        service.categories.own_named = AsyncMock(
            side_effect=ValidationError(WorkboardError.CATEGORY_UNKNOWN.value)
        )
        async with _creation_running(service):
            result = await workboard_tools.create_ticket_tool.coroutine(
                title="x", category="Garden", runtime=_runtime()
            )

        assert result.success is False
        assert result.metadata["workboard_error"] == WorkboardError.CATEGORY_UNKNOWN.value
        service.validate_creation.assert_not_awaited()


class TestTheLegacyWordsOfACategory:
    """`category` is a NAME and becomes an id; `clear_category` is the only way
    to say « none » — a keyword would collide with a category called that."""

    async def test_a_name_is_resolved_among_the_ACTORS_categories(self) -> None:
        """A holder naming a category must never learn, from the refusal,
        whether the ticket's OWNER has one called that."""
        from src.domains.agents.tools.workboard_legacy_input import normalize_workboard_legacy

        owner, holder, home = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        service = _service()
        service.categories.own_named = AsyncMock(return_value=home)

        values = await normalize_workboard_legacy(
            service, owner, "UTC", {"category": "Home"}, actor_id=holder
        )

        service.categories.own_named.assert_awaited_once_with(holder, "Home")
        assert values == {"category_id": home}

    async def test_leaving_a_category_is_said_and_asks_nothing(self) -> None:
        from src.domains.agents.tools.workboard_legacy_input import normalize_workboard_legacy

        service = _service()
        values = await normalize_workboard_legacy(
            service, USER, "UTC", {"clear_category": True}, actor_id=USER
        )

        assert values == {"clear_category": True}
        service.categories.own_named.assert_not_awaited()

    async def test_a_category_that_is_not_a_name_is_refused(self) -> None:
        from src.domains.agents.tools.workboard_legacy_input import normalize_workboard_legacy

        with pytest.raises(ValueError):
            await normalize_workboard_legacy(_service(), USER, "UTC", {"category": 7})

    def test_the_update_tool_takes_both_words(self) -> None:
        properties = workboard_tools.update_ticket_tool.tool_call_schema.model_json_schema()[
            "properties"
        ]
        assert {"category", "clear_category"} <= set(properties)
        # Creation has nothing to leave: it takes the name alone.
        created = workboard_tools.create_ticket_tool.tool_call_schema.model_json_schema()[
            "properties"
        ]
        assert "category" in created and "clear_category" not in created


class TestAnUpdateSaysWhyItIsRefused:
    """``update_ticket`` goes through the native tools' shared preparation, whose
    answer to a refused validation is one sentence naming no cause. A WORKBOARD
    refusal is a stable code the model can act on — « no category called that »
    is not « you do not own this ticket » — so it travels, as creation's does."""

    async def test_an_unknown_category_is_refused_by_its_stable_code(self) -> None:
        service = _service()
        service.categories.own_named = AsyncMock(
            side_effect=ValidationError(WorkboardError.CATEGORY_UNKNOWN.value)
        )
        async with _update_running(service):
            result = await workboard_tools.update_ticket_tool.coroutine(
                ticket="Book the venue", category="Garden", runtime=_runtime()
            )

        assert result.success is False and not result.registry_updates
        assert result.message == WorkboardError.CATEGORY_UNKNOWN.value
        assert result.error_code == "CONSTRAINT_VIOLATION"

    async def test_a_refusal_of_the_source_itself_travels_too(self) -> None:
        """A holder who names one of THEIR OWN categories passes the words and is
        stopped by the source: the ticket is not theirs to refile."""
        refused = AsyncMock(
            side_effect=ValidationError(WorkboardError.PEER_CANNOT_EDIT_FIELD.value)
        )
        async with _update_running(_service(), prepared=refused):
            result = await workboard_tools.update_ticket_tool.coroutine(
                ticket="Book the venue", category="Mine", runtime=_runtime()
            )

        refused.assert_awaited_once()
        assert result.success is False
        assert result.message == WorkboardError.PEER_CANNOT_EDIT_FIELD.value
        assert result.error_code == "CONSTRAINT_VIOLATION"

    async def test_a_refusal_that_is_no_workboard_code_stays_the_shared_sentence(self) -> None:
        """Only the workboard's own finite vocabulary travels: whatever else a
        validation carries — a sentence, somebody's words — never reaches the model."""
        refused = AsyncMock(side_effect=ValidationError("a sentence somebody typed, not a code"))
        async with _update_running(_service(), prepared=refused):
            result = await workboard_tools.update_ticket_tool.coroutine(
                ticket="Book the venue", status="done", runtime=_runtime()
            )

        assert result.success is False
        assert result.message == "Source constraint refused."
        assert result.error_code == "CONSTRAINT_VIOLATION"

    async def test_an_unknown_ticket_keeps_its_own_answer(self) -> None:
        """Not a validation: the ticket is not found, and that stays what is said."""
        service = _service(resolve_reference=AsyncMock(side_effect=ResourceNotFoundError("ticket")))
        async with _update_running(service):
            result = await workboard_tools.update_ticket_tool.coroutine(
                ticket="nothing", category="Home", runtime=_runtime()
            )

        assert result.success is False
        assert result.error_code == "NOT_FOUND_OR_UNAUTHORIZED"
        service.categories.own_named.assert_not_awaited()

    def test_only_a_member_of_the_workboards_vocabulary_is_a_code(self) -> None:
        """The predicate the update tool reads: every stable code, and nothing
        else — not a sentence, and not a structured detail, which is no text."""
        from src.domains.agents.tools.workboard_refusal import workboard_code_of

        for member in WorkboardError:
            assert workboard_code_of(ValidationError(member.value)) == member.value
        assert workboard_code_of(ValidationError("workboard_but_not_a_code")) is None
        assert workboard_code_of(ValidationError({"error_code": "STALE_STATE"})) is None


class TestACommentAndADeletionSayWhyTheyAreRefused:
    """The comment and the deletion go through the same shared preparation as the
    update, whose answer to a refused validation names no cause. Their refusals
    are the workboard's own finite vocabulary too, and travel the same way —
    an ambiguous title above all: told nothing, the model cannot ask WHICH."""

    async def test_an_ambiguous_title_is_said_so_the_model_can_ask_which(self) -> None:
        service = _service(
            resolve_reference=AsyncMock(
                side_effect=ValidationError(WorkboardError.AMBIGUOUS_REFERENCE.value)
            )
        )
        async with _comment_running(service):
            result = await workboard_tools.comment_ticket_tool.coroutine(
                ticket="Book the venue", body="Done", runtime=_runtime()
            )

        assert result.success is False and not result.registry_updates
        assert result.message == WorkboardError.AMBIGUOUS_REFERENCE.value
        assert result.error_code == "CONSTRAINT_VIOLATION"

    async def test_a_refusal_of_the_comment_itself_travels_too(self) -> None:
        refused = AsyncMock(side_effect=ValidationError(WorkboardError.COMMENT_TOO_LONG.value))
        async with _comment_running(_service(), prepared=refused):
            result = await workboard_tools.comment_ticket_tool.coroutine(
                ticket="Book the venue", body="Done", runtime=_runtime()
            )

        refused.assert_awaited_once()
        assert result.success is False
        assert result.message == WorkboardError.COMMENT_TOO_LONG.value
        assert result.error_code == "CONSTRAINT_VIOLATION"

    async def test_a_comment_refusal_that_is_no_workboard_code_stays_the_shared_sentence(
        self,
    ) -> None:
        """Only the workboard's own vocabulary travels: a validation that carries
        somebody's words never reaches the model."""
        refused = AsyncMock(side_effect=ValidationError("a sentence somebody typed, not a code"))
        async with _comment_running(_service(), prepared=refused):
            result = await workboard_tools.comment_ticket_tool.coroutine(
                ticket="Book the venue", body="Done", runtime=_runtime()
            )

        assert result.success is False
        assert result.message == "Source constraint refused."
        assert result.error_code == "CONSTRAINT_VIOLATION"

    async def test_an_ambiguous_title_stops_a_deletion_by_its_code(self) -> None:
        service = _service(
            resolve_reference=AsyncMock(
                side_effect=ValidationError(WorkboardError.AMBIGUOUS_REFERENCE.value)
            )
        )
        async with _deletion_running(service):
            result = await workboard_tools.delete_ticket_tool.coroutine(
                ticket="Book the venue", runtime=_runtime()
            )

        assert result.success is False and not result.registry_updates
        assert result.message == WorkboardError.AMBIGUOUS_REFERENCE.value
        assert result.error_code == "CONSTRAINT_VIOLATION"
        service.deletable.assert_not_awaited()

    async def test_an_unknown_ticket_keeps_its_own_answer_for_both(self) -> None:
        """Not a validation: not found stays not found, and names no code."""
        service = _service(resolve_reference=AsyncMock(side_effect=ResourceNotFoundError("ticket")))
        async with _comment_running(service):
            commented = await workboard_tools.comment_ticket_tool.coroutine(
                ticket="nothing", body="Done", runtime=_runtime()
            )
        async with _deletion_running(service):
            deleted = await workboard_tools.delete_ticket_tool.coroutine(
                ticket="nothing", runtime=_runtime()
            )

        assert commented.error_code == deleted.error_code == "NOT_FOUND_OR_UNAUTHORIZED"
        assert commented.message == deleted.message == "Selected resource unavailable."


class TestListingTheCategories:
    """What the board is split into, with the EXACT number of tickets in each."""

    async def test_every_lane_is_named_counted_and_said_whose_it_is(self) -> None:
        peer = uuid.uuid4()
        service = _service()
        service.categories.lanes = AsyncMock(
            return_value=[
                _lane(None, None, todo=2),
                _lane("Home", USER, todo=3, done=1),
                _lane("Work", USER),
                _lane("Site", peer, waiting=1),
            ]
        )
        async with _running(service):
            result = await workboard_tools.list_ticket_categories_tool.coroutine(runtime=_runtime())

        assert result.success is True
        assert result.structured_data == {
            "categories": [
                {"name": "Home", "mine": True, "tickets": 4},
                {"name": "Work", "mine": True, "tickets": 0},
                {"name": "Site", "mine": False, "tickets": 1},
            ],
            "managed_from": categories_managed_from(RUNTIME_LANGUAGE),
            "unfiled_tickets": 2,
        }
        # Categories are not things the chat points at: nothing for the registry.
        assert not result.registry_updates

    async def test_a_board_with_no_category_claims_no_count_it_did_not_read(self) -> None:
        """No lane, no aggregate: « 0 unfiled » would be a figure nobody counted."""
        service = _service()
        async with _running(service):
            result = await workboard_tools.list_ticket_categories_tool.coroutine(runtime=_runtime())

        assert result.structured_data == {
            "categories": [],
            "managed_from": categories_managed_from(RUNTIME_LANGUAGE),
        }

    async def test_the_result_says_where_categories_are_administered(self) -> None:
        """The pipeline's answer is written by a model that reads a tool's DATA
        and never its description: « create a category » can only be answered
        with where it is done if the result itself says so — on a board that
        has no category yet above all."""
        service = _service()
        async with _running(service):
            result = await workboard_tools.list_ticket_categories_tool.coroutine(runtime=_runtime())

        said = result.structured_data["managed_from"]
        assert "no tool" in said
        # Measured on a real pipeline turn (2026-11-11): « the workboard page »
        # came out as « la page du tableau de bord » — the home dashboard. The
        # page is NAMED, in quotes, as the application's menu names it.
        assert "the page named 'Workboard'" in said
        # And the button as the board labels it for THIS person: the runtime
        # of these tests speaks French.
        assert RUNTIME_LANGUAGE == "fr"
        assert "the 'Catégories' button" in said

    @pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
    async def test_the_place_is_named_in_the_words_the_person_s_screen_shows(
        self, language: str
    ) -> None:
        """The answer quotes the two names, and the person then looks for those
        exact words: a German account is sent to « Kategorien », never to a
        « Categories » button its screen does not show. The sentence around
        the names stays technical English — only a model reads it."""
        runtime = _runtime()
        runtime.context.language = language
        service = _service()
        async with _running(service):
            result = await workboard_tools.list_ticket_categories_tool.coroutine(runtime=runtime)

        said = result.structured_data["managed_from"]
        place = WORKBOARD_CATEGORY_PLACES[language]
        assert f"the '{place.button}' button" in said
        assert f"the page named '{place.page}'" in said
        assert "the user creates, renames, reorders and deletes categories there" in said

    async def test_a_chinese_account_reads_its_own_two_labels(self) -> None:
        """Pinned by hand, so the test above cannot agree with a wrong table."""
        runtime = _runtime()
        runtime.context.language = "zh-CN"
        service = _service()
        async with _running(service):
            result = await workboard_tools.list_ticket_categories_tool.coroutine(runtime=runtime)

        said = result.structured_data["managed_from"]
        assert "the '分类' button" in said
        assert "the page named '工作看板'" in said

    async def test_it_reads_the_whole_board_never_a_filtered_one(self) -> None:
        from src.domains.workboard.board_queries import BoardFilters

        service = _service()
        async with _running(service):
            await workboard_tools.list_ticket_categories_tool.coroutine(runtime=_runtime())

        assert service.categories.lanes.await_args.args[1] == BoardFilters()

    async def test_nothing_is_published_once_the_authority_is_gone(self) -> None:
        """The same double check as the two older readers: an account or a
        capability revoked WHILE the read ran publishes nothing."""
        from src.domains.agents.tools.output import UnifiedToolOutput

        refused = UnifiedToolOutput.failure(message="refused", error_code="CAPABILITY_DISABLED")
        service = _service()
        service.categories.lanes = AsyncMock(return_value=[_lane("Home", USER, todo=1)])
        async with _running(service):
            with patch(
                f"{MODULE}._actor",
                AsyncMock(side_effect=[User(id=USER, is_active=True), refused]),
            ):
                result = await workboard_tools.list_ticket_categories_tool.coroutine(
                    runtime=_runtime()
                )

        assert result.success is False
        assert result.error_code == "CAPABILITY_DISABLED"
        assert not result.structured_data


class TestTheManifestsAndTheCategory:
    """What a model is told about categories is what the tools do — no more.

    It reads them, narrows the board to one and files a ticket under one. It
    creates, renames, reorders and deletes none: those stay on the board
    (owner arbitration, 2026-11-11), and no manifest may suggest otherwise.
    """

    @staticmethod
    def _manifests() -> dict[str, Any]:
        from src.domains.agents.registry.catalogue import ToolManifest
        from src.domains.agents.workboard import (
            catalogue_manifests,
            category_manifest,
            creation_manifest,
        )

        found: dict[str, Any] = {}
        for module in (catalogue_manifests, category_manifest, creation_manifest):
            for value in vars(module).values():
                if isinstance(value, ToolManifest):
                    found[value.name] = value
        return found

    @pytest.mark.parametrize(
        "tool_name", ["create_ticket_tool", "update_ticket_tool", "list_tickets_tool"]
    )
    def test_a_category_name_is_published_with_the_bound_that_is_enforced(
        self, tool_name: str
    ) -> None:
        """ADR-184: a name longer than a category can be is a name that cannot
        match one — the producer must be able to read the bound."""
        parameter = next(p for p in self._manifests()[tool_name].parameters if p.name == "category")
        assert parameter.type == "string" and parameter.required is False
        bounds = {c.kind: c.value for c in parameter.constraints}
        assert bounds["max_length"] == settings.workboard_category_name_max_chars
        assert bounds["min_length"] == 1

    @pytest.mark.parametrize(
        "tool",
        [
            "create_ticket_tool",
            "update_ticket_tool",
            "list_tickets_tool",
            "list_ticket_categories_tool",
        ],
    )
    def test_every_parameter_a_tool_takes_is_one_its_manifest_declares(self, tool: str) -> None:
        """The planner reads the manifest and the loop binds the schema: a
        parameter on one side only is a capability half the modes cannot use."""
        taken = set(
            getattr(workboard_tools, tool).tool_call_schema.model_json_schema()["properties"]
        )
        declared = {p.name for p in self._manifests()[tool].parameters}
        assert taken == declared

    def test_leaving_a_category_is_a_switch_never_a_magic_name(self) -> None:
        manifests = self._manifests()
        update = {p.name: p for p in manifests["update_ticket_tool"].parameters}
        assert update["clear_category"].type == "boolean"
        listing = {p.name: p for p in manifests["list_tickets_tool"].parameters}
        assert listing["uncategorized"].type == "boolean"
        assert "clear_category" not in {p.name for p in manifests["create_ticket_tool"].parameters}

    @pytest.mark.parametrize("prefix", ["tickets[]", "ticket", "children[]"])
    def test_every_ticket_a_reader_returns_declares_its_category(self, prefix: str) -> None:
        manifests = self._manifests()
        declared = {
            output.path
            for name in ("list_tickets_tool", "get_ticket_tool")
            for output in manifests[name].outputs
        }
        assert f"{prefix}.category" in declared

    def test_the_category_reader_reads_and_nothing_else(self) -> None:
        manifest = self._manifests()["list_ticket_categories_tool"]
        assert manifest.mutation_policy == "read"
        assert manifest.agent == "ticket_agent"
        assert manifest.parameters == []
        # Categories are not things the chat points at afterwards.
        assert manifest.context_key is None
        paths = {output.path for output in manifest.outputs}
        assert {"categories[].name", "categories[].mine", "categories[].tickets"} <= paths
        assert "unfiled_tickets" in paths

    def test_a_request_to_administer_a_category_lands_on_the_reader(self) -> None:
        """Measured 2026-11-11 on three models: told to « say » where a category
        is administered, a model answered without calling anything (17 of 18),
        and the pipeline's answer then knew nothing of it. The reader is the
        landing point: its description asks for the call, and it publishes
        what its result adds."""
        manifest = self._manifests()["list_ticket_categories_tool"]
        described = manifest.description
        for verb in ("create", "rename", "reorder", "delete"):
            assert verb in described, verb
        assert "say it is done" not in described
        assert "managed_from" in {output.path for output in manifest.outputs}
        assert "create a category" in " ".join(manifest.semantic_keywords).lower()

    def test_the_reader_is_not_a_step_before_every_filing(self) -> None:
        """The same measurement: « before filing a ticket when the user names a
        category you have not seen » sent five requests to create or file a
        ticket to the reader instead. An unknown name is refused by its stable
        code, and the parameter that refuses names the reader."""
        manifests = self._manifests()
        assert "before filing" not in manifests["list_ticket_categories_tool"].description
        for name in ("create_ticket_tool", "update_ticket_tool"):
            category = next(p for p in manifests[name].parameters if p.name == "category")
            assert "list_ticket_categories_tool" in category.description, name

    def test_no_tool_administers_a_category(self) -> None:
        """Lot 5 was withdrawn by the owner: the day one exists, this is the
        test that must be changed on purpose."""
        from src.domains.agents.workboard.catalogue_manifests import TICKET_AGENT_MANIFEST

        assert [name for name in TICKET_AGENT_MANIFEST.tools if "categor" in name] == [
            "list_ticket_categories_tool"
        ]
        # And the model is TOLD so, where it would otherwise try to: the two
        # tools that file a ticket say a category is never created by them.
        manifests = self._manifests()
        for name in ("create_ticket_tool", "update_ticket_tool", "list_ticket_categories_tool"):
            assert "on the board" in manifests[name].description, name

    def test_the_new_reader_is_hidden_with_the_application_tools(self) -> None:
        """It asks the same application authority as the two older readers,
        so the same switch must take it out of the catalogue."""
        from src.domains.feature_switches.registry import PlatformCapability, disabled_tool_names

        state = dict.fromkeys(PlatformCapability, True)
        state[PlatformCapability.APPLICATION_TOOLS] = False
        assert "list_ticket_categories_tool" in disabled_tool_names(state)

    def test_the_new_reader_is_registered_with_the_six_others(self) -> None:
        from unittest.mock import MagicMock as Registry

        from src.domains.agents.workboard.catalogue_registration import (
            register_workboard_manifests,
        )

        registry = Registry()
        register_workboard_manifests(registry)
        registered = {call.args[0].name for call in registry.register_tool_manifest.call_args_list}
        assert "list_ticket_categories_tool" in registered
        assert len(registered) == 7
