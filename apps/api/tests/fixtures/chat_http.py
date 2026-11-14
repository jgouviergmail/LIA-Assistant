"""Real SQL/Redis HTTP harness with authentication and model boundaries substituted."""

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass, field
from uuid import UUID

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.core.config import settings
from src.core.conversation_execution import RunAdmission
from src.core.run_authority import current_run_authority
from src.core.session_dependencies import (
    get_current_active_session,
    get_current_active_session_for_stream,
)
from src.domains.agents.api import router, stream_gates, waiting_router
from src.domains.agents.api.background_runner import drain_chat_producers
from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.agents.api.service import AgentService
from src.domains.usage_limits.schemas import UsageLimitStatus
from src.domains.usage_limits.service import UsageLimitCheckResult, UsageLimitService
from src.domains.users.models import User
from src.infrastructure.database import session


@dataclass
class HttpHarness:
    """Record actual engine entry, without replacing the ownership boundary."""

    client: AsyncClient
    admission: RunAdmission
    calls: list[RunAdmission] = field(default_factory=list)
    hold: bool = False
    entered: asyncio.Event = field(default_factory=asyncio.Event)
    release: asyncio.Event = field(default_factory=asyncio.Event)

    def payload(self) -> dict[str, object]:
        """The body contains only public business identity, never private authority."""
        return {
            "user_id": str(self.admission.target.owner_id),
            "session_id": "integration-session",
            "message": "A question",
            "conversation_id": str(self.admission.target.id),
            "conversation_revision": self.admission.target.revision,
        }


@pytest_asyncio.fixture
async def http(
    reserved: RunAdmission,
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[HttpHarness]:
    """Production SQL sessions and route, substituting authentication and the model only."""
    monkeypatch.setattr(
        session, "AsyncSessionLocal", async_sessionmaker(async_engine, expire_on_commit=False)
    )
    monkeypatch.setattr(settings, "background_runs_enabled", False)
    monkeypatch.setattr(settings, "agent_stream_sleep_interval", 0)
    async with AsyncSession(async_engine) as db:
        user = await db.get(User, reserved.target.owner_id)
        assert user is not None
        db.expunge(user)

    async def authenticated() -> User:
        return user

    async def allowed(owner: UUID) -> UsageLimitCheckResult:
        return UsageLimitCheckResult(True, UsageLimitStatus.OK, None, None)

    async def no_limit(owner: UUID) -> None:
        return None

    async def body(*args: object, **kwargs: object) -> AsyncGenerator[ChatStreamChunk]:
        authority = current_run_authority()
        assert authority is not None
        assert kwargs["target"] == authority.admission.target
        harness.calls.append(authority.admission)
        harness.entered.set()
        if harness.hold:
            await harness.release.wait()
        yield ChatStreamChunk(type="done", content="", metadata=None)

    monkeypatch.setattr(UsageLimitService, "check_user_allowed", allowed)
    monkeypatch.setattr(stream_gates, "usage_limit_error_chunk", no_limit)
    monkeypatch.setattr(stream_gates, "capture_location_fire_and_forget", lambda *_: None)
    monkeypatch.setattr(AgentService, "_stream_with_new_services", body)
    app = FastAPI()
    app.include_router(router.router)
    app.include_router(waiting_router.router)
    app.dependency_overrides[get_current_active_session_for_stream] = authenticated
    app.dependency_overrides[get_current_active_session] = authenticated
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        harness = HttpHarness(client, reserved)
        yield harness
        _, pending = await drain_chat_producers(timeout=5)
        assert pending == 0, "An HTTP fixture cannot retire SQL while its producer still owns it"
