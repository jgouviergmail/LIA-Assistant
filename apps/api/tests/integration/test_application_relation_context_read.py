"""Provider-card reading projects source cache/status metadata and rechecks access."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from langgraph.store.memory import InMemoryStore
from redis.exceptions import ConnectionError as RedisConnectionError

from src.core.config import settings
from src.domains.agents.tools import application_relation_tools
from src.domains.relations.providers.schemas import (
    ContactCard,
    ContextSection,
    ContextStatus,
    RelationContext,
)
from src.domains.relations.providers.service import RelationContextService
from src.infrastructure.rate_limiting.redis_limiter import get_rate_limiter
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    ["observed", "subset", "late_off", "rate_off", "rate_limit", "redis_failure", "oversized"],
)
async def test_context_read_uses_owned_source_without_refresh(
    async_session, test_user, monkeypatch, scenario
):
    owner = test_user.id
    await async_session.commit()

    @asynccontextmanager
    async def session():
        yield async_session

    monkeypatch.setattr(application_relation_tools, "get_db_context", session)
    now = datetime.now(UTC)
    contact = ContextSection(
        status=ContextStatus.OK,
        generated_at=now,
        from_cache=True,
        contact=ContactCard(display_name="Alice", biography="Stored note"),
    )
    source = RelationContext(
        contact=contact,
        emails=ContextSection(status=ContextStatus.ERROR, generated_at=now),
        events=ContextSection(status=ContextStatus.NO_ADDRESS, generated_at=now),
        addresses_used=1,
        window_days=7,
        email_window_days=90,
    )

    async def fetch(service, name, **kwargs):
        assert service.user_id == owner and name == "Alice"
        assert not kwargs.get("refresh")
        if scenario == "late_off":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        return await build(name, **kwargs)

    build = AsyncMock(return_value=source)
    monkeypatch.setattr(RelationContextService, "build", fetch)
    if scenario == "rate_off":
        limiter = await get_rate_limiter()
        acquire = limiter.acquire

        async def acquire_then_disable(**kwargs):
            allowed = await acquire(**kwargs)
            monkeypatch.setattr(settings, "application_tools_enabled", False)
            return allowed

        monkeypatch.setattr(limiter, "acquire", acquire_then_disable)
    if scenario == "rate_limit":
        monkeypatch.setattr(settings, "relations_provider_rate_limit_calls", 1)
        limiter = await get_rate_limiter()
        assert await limiter.acquire(
            key=f"auth:relations_context:user:{owner}",
            max_calls=1,
            window_seconds=settings.relations_provider_rate_limit_window_seconds,
        )
    if scenario == "redis_failure":
        monkeypatch.setattr(
            "src.domains.agents.application.relation_context_read.get_rate_limiter",
            AsyncMock(side_effect=RedisConnectionError("Unavailable")),
        )
    if scenario == "oversized":
        source = source.model_copy(
            update={
                "contact": contact.model_copy(
                    update={"contact": ContactCard(display_name="Alice", biography="X" * 70_000)}
                )
            }
        )
        build.return_value = source
    with installed_runtime_context(user_id=owner, deps=object()):
        result = await application_relation_tools.get_lia_relation_context_tool.coroutine(
            query=(
                {"name": "Alice", "sections": ["contact"]}
                if scenario == "subset"
                else {"name": "Alice"}
            ),
            runtime=make_tool_runtime(user_id=owner, store=InMemoryStore()),
        )
    if scenario in {"late_off", "rate_off", "rate_limit", "redis_failure", "oversized"}:
        assert not result.success and not result.structured_data
        if scenario == "rate_off":
            build.assert_not_awaited()
        if scenario in {"rate_limit", "redis_failure"}:
            build.assert_not_awaited()
            assert result.error_code == (
                "RATE_LIMIT_EXCEEDED" if scenario == "rate_limit" else "DEPENDENCY_ERROR"
            )
        return
    assert result.success
    assert result.structured_data["contact"]["from_cache"]
    assert result.structured_data["emails"]["status"] == "error"
    assert result.structured_data["events"]["status"] == "no_address"
    assert result.structured_data["email_window_days"] == 90
    if scenario == "subset":
        assert build.await_args.kwargs["sections"] == frozenset({"contact"})
