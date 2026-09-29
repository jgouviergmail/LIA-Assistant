"""Encrypted, bounded diagnostics are private across real Redis/API readers."""

import importlib
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.users.models import User

pytestmark = pytest.mark.integration


async def test_store_replaces_one_call_and_bounds_retention_by_account() -> None:
    store = importlib.import_module("src.infrastructure.llm.jev_debug_store")
    models = importlib.import_module("src.infrastructure.llm.jev_debug_models")
    from src.infrastructure.cache.redis import get_redis_cache

    redis = await get_redis_cache()
    owner, other = uuid4(), uuid4()
    now = datetime.now(UTC)
    trace = models.JevCallTrace(
        id=uuid4(),
        run_id="recording-run",
        caller="meeting_template_selection",
        usage="meeting_template",
        started_at=now,
        requested_model="jev-1.13.0",
        context=models.context_preview("private transcript"),
    )
    try:
        await store.write_trace(owner, trace)
        await store.record_action(
            owner,
            trace,
            action="preview",
            outcome="uncertain",
            target="result_preview",
            applied_decisions={"q0": "unknown"},
            decision_labels={"q0": "Private source title"},
        )
        stored_preview = (await store.read_traces(owner)).calls[0]
        assert stored_preview.action == "preview"
        assert stored_preview.applied_decisions == {"q0": "unknown"}
        assert stored_preview.decision_labels == {"q0": "Private source title"}
        await store.record_action(
            owner,
            trace,
            action="observed",
            outcome="success",
            target="existing_extraction_unchanged",
            observed_result=models.context_preview({"actions": ["private extractor proposal"]}),
        )
        observed = (await store.read_traces(owner)).calls[0]
        assert observed.action == "observed"
        assert "private extractor proposal" in observed.observed_result.text
        assert all(
            "private extractor proposal" not in str(value)
            for value in await redis.hvals(store.trace_keys(owner)[0])
        )
        await store.write_trace(
            owner, trace.model_copy(update={"action": "selected", "action_target": "Minutes"})
        )
        page = await store.read_traces(owner)
        assert len(page.calls) == 1 and page.calls[0].action == "selected"
        # A timed-out earlier Redis write may arrive after the consumer update.
        await store.write_trace(owner, trace)
        assert (await store.read_traces(owner)).calls[0].action == "selected"
        assert (await store.read_traces(other)).calls == []
        values = await redis.hvals(store.trace_keys(owner)[0])
        assert values and all("private transcript" not in str(value) for value in values)
        assert 0 < await redis.ttl(store.trace_keys(owner)[0]) <= 3600
        deadline = await redis.execute_command(
            "HPEXPIRETIME", store.trace_keys(owner)[0], "FIELDS", 1, str(trace.id)
        )
        assert deadline == [int((trace.started_at.timestamp() + 3600) * 1000)]
        # Expiration is per call: a later update cannot revive an old entry.
        old = trace.model_copy(update={"id": uuid4(), "started_at": now - timedelta(hours=2)})
        await redis.delete(*store.trace_keys(owner))
        await store.write_trace(owner, old)
        await store.write_trace(owner, old.model_copy(update={"action": "selected"}))
        assert (await store.read_traces(owner)).calls == []
        for index in range(35):
            await store.write_trace(
                owner,
                trace.model_copy(
                    update={
                        "id": uuid4(),
                        "started_at": now + timedelta(milliseconds=index),
                        "run_id": f"run-{index}",
                    }
                ),
            )
        page = await store.read_traces(owner)
        assert len(page.calls) == 30 and page.calls[0].run_id == "run-34"
        assert await redis.hlen(store.trace_keys(owner)[0]) == 30
    finally:
        await redis.delete(*store.trace_keys(owner), *store.trace_keys(other))


async def test_anonymous_cannot_read_jev_context(async_client: AsyncClient) -> None:
    response = await async_client.get("/api/v1/debug/jev")
    assert response.status_code == 401


async def test_disabled_debug_panel_cannot_read_context(
    authenticated_client: tuple[AsyncClient, User],
) -> None:
    client, _ = authenticated_client
    response = await client.get("/api/v1/debug/jev")
    assert response.status_code == 403


async def test_real_session_capture_ownership_and_hot_revocation(
    admin_client: tuple[AsyncClient, User],
    async_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.domains.llm_config.jev_registry import JevUsage
    from src.infrastructure.cache.redis import get_redis_cache
    from src.infrastructure.llm import jev_debug_store as store
    from src.infrastructure.llm.typesafe_client import ChoiceQuestion

    client, owner = admin_client

    # Background sessions must join this test's outer transaction, whose
    # savepoint commits deliberately remain invisible to other connections.
    @asynccontextmanager
    async def background_session():
        async with AsyncSession(
            bind=async_session.bind,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        ) as session:
            yield session

    monkeypatch.setattr(store, "get_db_context", background_session)
    monkeypatch.setattr("src.infrastructure.database.get_db_context", background_session)
    other = uuid4()
    enabled = await client.put("/api/v1/admin/system-settings/debug-panel", json={"enabled": True})
    assert enabled.status_code == 200
    args = {
        "user_id": owner.id,
        "usage": JevUsage.MEETING_TEMPLATE,
        "run_id": "background-run",
        "model": "jev-1.13.0",
        "state": {"transcript": "private own content"},
        "question": ChoiceQuestion(instructions="Select", criteria={"a": "A", "b": "B"}),
    }
    redis = await get_redis_cache()
    try:
        trace = await store.begin_trace(**args)
        assert trace is not None and trace.caller == "meeting_template_selection"
        await store.save_trace(owner.id, trace)
        await store.write_trace(
            other, trace.model_copy(update={"id": uuid4(), "run_id": "other-owner"})
        )
        response = await client.get(f"/api/v1/debug/jev?user_id={other}")
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "no-store"
        assert [row["run_id"] for row in response.json()["calls"]] == ["background-run"]
        from unittest.mock import AsyncMock

        with monkeypatch.context() as broken:
            broken.setattr(
                "src.domains.llm_config.jev_debug_router.read_traces",
                AsyncMock(side_effect=ConnectionError("private-provider-body")),
            )
            failure = await client.get("/api/v1/debug/jev")
            assert failure.status_code == 503
            assert failure.headers["Cache-Control"] == "no-store"
            assert "private-provider-body" not in failure.text
        disabled = await client.put(
            "/api/v1/admin/system-settings/debug-panel", json={"enabled": False}
        )
        assert disabled.status_code == 200
        assert (await client.get("/api/v1/debug/jev")).status_code == 403
        assert await store.begin_trace(**args) is None
    finally:
        await redis.delete(*store.trace_keys(owner.id), *store.trace_keys(other))
