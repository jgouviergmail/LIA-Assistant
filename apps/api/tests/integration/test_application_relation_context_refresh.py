"""Refresh is an exact confirmed source request, never an implicit read side effect."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from langgraph.store.memory import InMemoryStore

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.relation_context_refresh import (
    execute_relation_context_refresh,
    prepare_relation_context_refresh,
)
from src.domains.agents.application.relation_context_refresh_schemas import (
    RelationContextRefreshRequest,
)
from src.domains.agents.tools import application_relation_tools
from src.domains.relations.providers.schemas import ContextSection, ContextStatus, RelationContext
from src.domains.relations.providers.service import RelationContextService
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.rate_limiting.redis_limiter import get_rate_limiter
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


async def test_refresh_preparation_never_fetches_provider(async_session, test_user, monkeypatch):
    owner = test_user.id
    await async_session.commit()

    @asynccontextmanager
    async def session():
        yield async_session

    monkeypatch.setattr(application_relation_tools, "get_db_context", session)
    build = AsyncMock(side_effect=AssertionError("Confirmation is required"))
    monkeypatch.setattr(RelationContextService, "build", build)
    with installed_runtime_context(user_id=owner, deps=object()):
        result = await application_relation_tools.refresh_lia_relation_context_tool.coroutine(
            request={"name": "Alice", "sections": ["emails"]},
            runtime=make_tool_runtime(user_id=owner, store=InMemoryStore()),
        )
    assert result.success and result.metadata["requires_confirmation"]
    build.assert_not_awaited()


@pytest.mark.parametrize(
    "scenario", ["partial", "expired", "rate_limit", "rate_off", "late_off", "timeout"]
)
async def test_refresh_guards_source_and_reports_partial_outcomes(
    async_session, test_user, monkeypatch, scenario
):
    owner = test_user.id
    await async_session.commit()
    draft = await prepare_relation_context_refresh(
        async_session, owner, RelationContextRefreshRequest(name="Alice", sections=["emails"])
    )
    section = ContextSection(status=ContextStatus.ERROR, generated_at=datetime.now(UTC))
    source = RelationContext(contact=section, emails=section, events=section)
    calls = AsyncMock(return_value=source)

    async def fetch(service, name, **kwargs):
        assert service.user_id == owner and name == "Alice"
        assert kwargs["refresh"] == frozenset({"emails"})
        assert kwargs["sections"] == frozenset({"emails"})
        if scenario == "timeout":
            raise TimeoutError("Unknown cache outcome")
        if scenario == "late_off":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        return await calls(name, **kwargs)

    monkeypatch.setattr(RelationContextService, "build", fetch)
    if scenario == "expired":
        draft = draft.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    if scenario in {"rate_limit", "rate_off"}:
        limiter = await get_rate_limiter()
        if scenario == "rate_limit":
            monkeypatch.setattr(settings, "relations_provider_rate_limit_calls", 1)
            assert await limiter.acquire(
                key=f"auth:relations_context:user:{owner}",
                max_calls=1,
                window_seconds=settings.relations_provider_rate_limit_window_seconds,
            )
        else:
            acquire = limiter.acquire

            async def withdraw(**kwargs):
                allowed = await acquire(**kwargs)
                monkeypatch.setattr(settings, "application_tools_enabled", False)
                return allowed

            monkeypatch.setattr(limiter, "acquire", withdraw)
    receipt = PreferenceWriteReceipt()
    if scenario == "partial":
        await execute_relation_context_refresh(async_session, owner, draft, receipt)
        assert receipt.committed
        assert receipt.values["relation_context"]["emails"]["status"] == "error"
        assert receipt.values["relation_context"]["refresh_requested"] == ["emails"]
    else:
        expected = AuthorizationError if scenario in {"rate_off", "late_off"} else CommandRejected
        with pytest.raises(expected):
            await execute_relation_context_refresh(async_session, owner, draft, receipt)
        assert not receipt.values
        if scenario in {"expired", "rate_limit", "rate_off"}:
            calls.assert_not_awaited()
