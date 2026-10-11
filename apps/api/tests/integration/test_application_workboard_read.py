"""Native Workboard reads preserve source visibility, exact totals and bounded detail pages."""

from uuid import uuid4

import pytest
from sqlalchemy import update

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceNotFoundError
from src.domains.agents.application.workboard_read import read_workboard_ui
from src.domains.agents.application.workboard_read_schemas import WorkboardUIQuery
from src.domains.users.models import User
from src.domains.workboard.models import WorkboardTicket
from src.domains.workboard.schemas import CommentCreate, TicketCreate
from src.domains.workboard.service import WorkboardService

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "section", ["board", "summary", "ticket", "comments", "events", "children", "needs_me"]
)
async def test_owned_board_sections_and_exact_pages(async_session, test_user, monkeypatch, section):
    monkeypatch.setattr(settings, "workboard_enabled", True)
    service = WorkboardService(async_session)
    first = await service.create(test_user, TicketCreate(title="100% _literal_", status="todo"))
    second = await service.create(test_user, TicketCreate(title="Other", status="todo"))
    child = await service.create(test_user, TicketCreate(title="Step", parent_id=first.id))
    for index in range(3):
        await service.comment(
            test_user, first.id, CommentCreate(body=f"Literal <script>{index}</script>")
        )
    identities = first.id, second.id, child.id
    await async_session.commit()
    query = WorkboardUIQuery(
        section=section,
        ticket_id=(
            identities[0] if section in {"ticket", "comments", "events", "children"} else None
        ),
        limit=1,
    )
    result = await read_workboard_ui(async_session, test_user.id, query)
    if section == "board":
        assert len(result.tickets) == 1 and result.total == 3 and result.next_offset == 1
        assert result.counts_by_status["todo"] == 3
        literal = await read_workboard_ui(
            async_session, test_user.id, WorkboardUIQuery(section="board", query="100% _literal_")
        )
        assert literal.total == 1 and literal.tickets[0].id == identities[0]
    elif section == "summary":
        assert (
            result.summary.total == 3
            and result.summary.max_tickets == settings.workboard_max_tickets_per_user
        )
    elif section == "ticket":
        assert result.ticket.id == identities[0]
        assert result.ticket.total_cost_eur == 0
    elif section == "comments":
        assert result.total == 3 and len(result.comments) == 1 and result.next_offset == 1
        assert result.comments[0].body == "Literal <script>0</script>"
        page = await read_workboard_ui(
            async_session, test_user.id, query.model_copy(update={"offset": 2})
        )
        assert page.comments[0].body == "Literal <script>2</script>" and page.next_offset is None
    elif section == "children":
        assert result.total == 1 and result.tickets[0].id == identities[2]
    elif section == "events":
        assert result.total >= 1 and len(result.events) == 1
    else:
        assert result.total == 0 and result.tickets == []


@pytest.mark.parametrize("scenario", ["foreign", "native_off", "workboard_off", "late_off"])
async def test_board_current_authority(async_session, test_user, monkeypatch, scenario):
    monkeypatch.setattr(settings, "workboard_enabled", True)
    service = WorkboardService(async_session)
    peer = User(
        id=uuid4(), email=f"board-read-{uuid4()}@example.com", full_name="Private", is_active=True
    )
    async_session.add(peer)
    await async_session.flush()
    ticket = await service.create(
        peer if scenario == "foreign" else test_user, TicketCreate(title="Private ticket")
    )
    identity, owner = ticket.id, test_user.id
    await async_session.commit()
    if scenario == "native_off":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    if scenario == "workboard_off":
        monkeypatch.setattr(settings, "workboard_enabled", False)
    if scenario == "late_off":
        source = WorkboardService.summary

        async def switched(service, actor):
            result = await source(service, actor)
            monkeypatch.setattr(settings, "workboard_enabled", False)
            return result

        monkeypatch.setattr(WorkboardService, "summary", switched)
    with pytest.raises((ResourceNotFoundError, AuthorizationError)):
        await read_workboard_ui(
            async_session,
            owner,
            (
                WorkboardUIQuery(section="ticket", ticket_id=identity)
                if scenario == "foreign"
                else WorkboardUIQuery()
            ),
        )


@pytest.mark.parametrize("section", ["board", "ticket", "comments"])
async def test_workboard_reads_fresh_rows_and_refuses_late_visibility_loss(
    async_session, test_user, monkeypatch, section
):
    monkeypatch.setattr(settings, "workboard_enabled", True)
    service = WorkboardService(async_session)
    ticket = await service.create(test_user, TicketCreate(title="Old title"))
    identity, owner = ticket.id, test_user.id
    peer = User(
        id=uuid4(), email=f"board-loss-{uuid4()}@example.com", full_name="Other", is_active=True
    )
    async_session.add(peer)
    await async_session.flush()
    peer_id = peer.id
    await async_session.commit()
    await async_session.execute(
        update(WorkboardTicket)
        .where(WorkboardTicket.id == identity)
        .values(title="Fresh title")
        .execution_options(synchronize_session=False)
    )
    await async_session.commit()
    query = WorkboardUIQuery(section=section, ticket_id=None if section == "board" else identity)
    actual = await read_workboard_ui(async_session, owner, query)
    if section != "comments":
        assert (actual.ticket if section == "ticket" else actual.tickets[0]).title == "Fresh title"
    from src.domains.agents.application import workboard_read

    source_access = workboard_read._read_access
    calls = 0

    async def lose_visibility(db, actor_id):
        nonlocal calls
        calls += 1
        if calls == 2:
            await db.execute(
                update(WorkboardTicket)
                .where(WorkboardTicket.id == identity)
                .values(owner_user_id=peer_id)
                .execution_options(synchronize_session=False)
            )
        return await source_access(db, actor_id)

    monkeypatch.setattr(workboard_read, "_read_access", lose_visibility)
    with pytest.raises(ResourceNotFoundError):
        await read_workboard_ui(async_session, owner, query)


async def test_oversized_history_page_is_refused_without_cutting_words(
    async_session, test_user, monkeypatch
):
    monkeypatch.setattr(settings, "workboard_enabled", True)
    service = WorkboardService(async_session)
    ticket = await service.create(test_user, TicketCreate(title="Long history"))
    identity = ticket.id
    from src.domains.workboard.constants import ActorKind
    from src.domains.workboard.models import WorkboardComment

    async_session.add_all(
        [
            WorkboardComment(
                ticket_id=identity,
                author_kind=ActorKind.USER.value,
                author_user_id=test_user.id,
                body="界" * 25_000,
            )
            for _ in range(2)
        ]
    )
    await async_session.commit()
    with pytest.raises(ValueError, match="too large"):
        await read_workboard_ui(
            async_session, test_user.id, WorkboardUIQuery(section="comments", ticket_id=identity)
        )


async def test_native_workboard_tool_reads_real_source_shape(async_session, test_user, monkeypatch):
    from contextlib import asynccontextmanager

    from langgraph.store.memory import InMemoryStore

    from src.domains.agents.tools import application_workboard_tools
    from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

    monkeypatch.setattr(settings, "workboard_enabled", True)
    await WorkboardService(async_session).create(
        test_user, TicketCreate(title="Read from native tool")
    )
    await async_session.commit()

    @asynccontextmanager
    async def session():
        yield async_session

    monkeypatch.setattr(application_workboard_tools, "get_db_context", session)
    with installed_runtime_context(user_id=test_user.id, deps=object()):
        result = await application_workboard_tools.get_lia_workboard_tool.coroutine(
            query={"section": "board"},
            runtime=make_tool_runtime(user_id=test_user.id, store=InMemoryStore()),
        )
    assert result.success
    assert result.structured_data["total"] == 1
    assert result.structured_data["tickets"][0]["title"] == "Read from native tool"
    assert not result.metadata.get("requires_confirmation")
