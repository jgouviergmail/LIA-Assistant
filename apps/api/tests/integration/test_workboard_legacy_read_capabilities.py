"""Historical compact readers cannot bypass global application controls."""

from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import update

from src.core.config import settings
from src.domains.agents.tools import workboard_tools
from src.domains.feature_switches.registry import PlatformCapability, disabled_tool_names
from src.domains.peers.models import PeerConnection, PeerConnectionStatus, canonical_pair
from src.domains.users.models import User
from src.domains.workboard.models import WorkboardTicket
from src.domains.workboard.schemas import TicketCreate
from src.domains.workboard.service import WorkboardService
from tests.helpers.runtime_context import make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("tool_name", ["get_ticket_tool", "list_tickets_tool"])
@pytest.mark.parametrize("scenario", ["enabled", "disabled", "late_disabled"])
async def test_legacy_readers_respect_current_application_capability(
    async_session, test_user, monkeypatch, tool_name, scenario
):
    monkeypatch.setattr(settings, "workboard_enabled", True)
    actor_id = test_user.id
    ticket = await WorkboardService(async_session).create(
        test_user, TicketCreate(title="Controlled old reader target")
    )
    identity = ticket.id
    await async_session.commit()

    @asynccontextmanager
    async def session():
        yield async_session

    monkeypatch.setattr(workboard_tools, "get_db_context", session)
    if scenario == "disabled":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    elif scenario == "late_disabled":
        method = "get" if tool_name == "get_ticket_tool" else "board"
        source = getattr(WorkboardService, method)

        async def fetched(service, *args, **kwargs):
            result = await source(service, *args, **kwargs)
            monkeypatch.setattr(settings, "application_tools_enabled", False)
            return result

        monkeypatch.setattr(WorkboardService, method, fetched)
    params = {"runtime": make_tool_runtime(user_id=actor_id, store=InMemoryStore())}
    if tool_name == "get_ticket_tool":
        params["ticket"] = str(identity)
    result = await getattr(workboard_tools, tool_name).coroutine(**params)
    assert result.success == (scenario == "enabled"), result.model_dump()
    if scenario != "enabled":
        assert result.error_code == "CAPABILITY_DISABLED" and not result.registry_updates


def test_global_capability_hides_all_six_original_workboard_tools():
    state = dict.fromkeys(PlatformCapability, True)
    state[PlatformCapability.APPLICATION_TOOLS] = False
    denied = disabled_tool_names(state)
    assert {
        "create_ticket_tool",
        "update_ticket_tool",
        "comment_ticket_tool",
        "delete_ticket_tool",
        "get_ticket_tool",
        "list_tickets_tool",
    } <= denied


@pytest.mark.parametrize("tool_name", ["get_ticket_tool", "list_tickets_tool"])
@pytest.mark.parametrize("revocation", ["assignment", "account"])
async def test_legacy_readers_publish_nothing_after_current_authority_is_revoked(
    async_session, test_user, monkeypatch, tool_name, revocation
):
    monkeypatch.setattr(settings, "workboard_enabled", True)
    monkeypatch.setattr(settings, "peers_enabled", True)
    actor_id = test_user.id
    owner = User(id=uuid4(), email=f"reader-owner-{uuid4()}@example.test", is_active=True)
    async_session.add(owner)
    await async_session.flush()
    lo, hi = canonical_pair(owner.id, actor_id)
    async_session.add(
        PeerConnection(
            user_a_id=lo,
            user_b_id=hi,
            requested_by_id=owner.id,
            status=PeerConnectionStatus.ACCEPTED.value,
        )
    )
    await async_session.flush()
    ticket = await WorkboardService(async_session, assignment_notices=[]).create(
        owner, TicketCreate(title="Private assigned reader target", assignee_user_id=actor_id)
    )
    identity = ticket.id
    await async_session.commit()

    @asynccontextmanager
    async def session():
        yield async_session

    monkeypatch.setattr(workboard_tools, "get_db_context", session)
    method = "get" if tool_name == "get_ticket_tool" else "board"
    source = getattr(WorkboardService, method)

    async def fetched(service, *args, **kwargs):
        result = await source(service, *args, **kwargs)
        statement = (
            update(WorkboardTicket)
            .where(WorkboardTicket.id == identity)
            .values(assignee_user_id=None)
            if revocation == "assignment"
            else update(User).where(User.id == actor_id).values(is_active=False)
        )
        await async_session.execute(statement.execution_options(synchronize_session=False))
        await async_session.flush()
        return result

    monkeypatch.setattr(WorkboardService, method, fetched)
    params = {"runtime": make_tool_runtime(user_id=actor_id, store=InMemoryStore())}
    if tool_name == "get_ticket_tool":
        params["ticket"] = str(identity)
    result = await getattr(workboard_tools, tool_name).coroutine(**params)
    assert not result.success, result.model_dump()
    assert result.error_code == ("NOT_FOUND" if revocation == "assignment" else "FORBIDDEN")
    assert not result.registry_updates and not result.structured_data
