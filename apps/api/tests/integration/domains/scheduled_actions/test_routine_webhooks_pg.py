"""A signed call starts a routine — through the real API, on a real PostgreSQL (ADR-386).

What the unit tests cannot execute is proven here: the address's door with its
real dependencies (the capability guard, the client window in Redis, the body
bound), the duplicate index and the backlog bound on the real schema, the owner's
secret shown once, the executor's tick reading and serving the calls with only
the ENGINE replaced, the race between a call and a tick that found nothing, and
the migration both ways.
"""

from __future__ import annotations

import importlib.util
import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from alembic.migration import MigrationContext
from alembic.operations import Operations
from httpx import AsyncClient
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.config import settings
from src.core.constants import ROUTINE_WEBHOOK_FAILURE_RETRY_SECONDS
from src.core.security.utils import decrypt_data, encrypt_data
from src.core.time_utils import now_utc
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.scheduled_actions.models import (
    RoutineWebhookDelivery,
    ScheduledAction,
    ScheduledActionRun,
    ScheduledActionStatus,
    ScheduledRunOutcome,
)
from src.domains.scheduled_actions.repository import ScheduledActionRepository
from src.domains.scheduled_actions.schemas import ScheduledActionUpdate
from src.domains.scheduled_actions.service import ScheduledActionService
from src.domains.scheduled_actions.webhook_repository import RoutineWebhookRepository
from src.domains.scheduled_actions.webhook_service import CallOutcome, RoutineWebhookService
from src.domains.scheduled_actions.webhooks import (
    draw_webhook_key,
    draw_webhook_secret,
    signature_of,
)
from src.domains.users.models import User
from src.infrastructure.scheduler import routine_webhook_gate
from src.infrastructure.scheduler import scheduled_action_executor as executor
from src.infrastructure.scheduler.out_of_turn_run import RunOutcome, RunResult, StreamRequest

pytestmark = pytest.mark.integration

HOOKS = "/api/v1/hooks/routines"
ROUTINES = "/api/v1/scheduled-actions"
_MIGRATION = (
    Path(__file__).resolve().parents[4]
    / "alembic"
    / "versions"
    / "2026_11_13_2100-7c2e5b9d4a18_routine_webhooks.py"
)


@pytest_asyncio.fixture(autouse=True)
async def _fresh_windows() -> AsyncIterator[None]:
    """Every test starts with fresh call windows (they live in Redis, not the database)."""

    async def purge() -> None:
        from src.infrastructure.rate_limiting.redis_limiter import get_rate_limiter

        limiter = await get_rate_limiter()
        keys = [key async for key in limiter.redis.scan_iter(match="routine_webhook:*")]
        if keys:
            await limiter.redis.delete(*keys)

    await purge()
    yield
    await purge()


def _signed(secret: str, body: bytes, **headers: str) -> dict[str, str]:
    return {
        "X-LIA-Signature-256": signature_of(secret, body),
        "Content-Type": "application/json",
        **headers,
    }


@dataclass(frozen=True)
class _Hooked:
    """A webhook routine as plain values: a request sharing the test's session
    rolls its read back, which expires every row the session holds."""

    id: UUID
    user_id: UUID
    webhook_key: str


async def _webhook_routine(
    session: AsyncSession, *, enabled: bool = True, email: str | None = None
) -> tuple[_Hooked, str]:
    """A webhook routine of a fresh account, committed, and its secret in clear."""
    user = User(
        email=email or f"hook_{uuid4().hex}@example.com",
        hashed_password="x",
        is_active=True,
        is_verified=True,
    )
    session.add(user)
    await session.flush()
    secret = draw_webhook_secret()
    action = ScheduledAction(
        user_id=user.id,
        title="Door",
        action_prompt="Tell me who rang",
        user_timezone="Europe/Paris",
        trigger_kind="webhook",
        webhook_key=draw_webhook_key(),
        webhook_secret=encrypt_data(secret),
        next_trigger_at=None,
        status=ScheduledActionStatus.ACTIVE.value,
        is_enabled=enabled,
    )
    session.add(action)
    await session.commit()
    assert action.webhook_key is not None
    return _Hooked(id=action.id, user_id=user.id, webhook_key=action.webhook_key), secret


async def _calls(session: AsyncSession, action_id: UUID) -> list[RoutineWebhookDelivery]:
    result = await session.execute(
        select(RoutineWebhookDelivery)
        .where(RoutineWebhookDelivery.scheduled_action_id == action_id)
        .order_by(RoutineWebhookDelivery.received_at)
        .execution_options(populate_existing=True)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# The address's door
# ---------------------------------------------------------------------------


async def test_a_signed_call_is_kept_encrypted_and_arms_the_routine(
    async_client: AsyncClient, async_session: AsyncSession
) -> None:
    action, secret = await _webhook_routine(async_session)
    body = b'{"door": "front", "at": "18:42"}'

    answer = await async_client.post(
        f"{HOOKS}/{action.webhook_key}", content=body, headers=_signed(secret, body)
    )

    assert answer.status_code == 202, answer.text
    assert answer.json() == {"status": "accepted"}
    assert answer.headers["cache-control"] == "no-store"
    (call,) = await _calls(async_session, action.id)
    assert call.status == "pending" and call.served_at is None
    assert call.body is not None and call.body != body.decode()
    assert decrypt_data(call.body) == body.decode()
    assert (call.body_bytes, call.content_type) == (len(body), "application/json")
    stored = await async_session.get(ScheduledAction, action.id, populate_existing=True)
    assert stored is not None and stored.next_trigger_at is not None
    assert abs((stored.next_trigger_at - now_utc()).total_seconds()) < 60


async def test_a_call_is_logged_by_its_facts_never_its_words(
    async_client: AsyncClient, async_session: AsyncSession
) -> None:
    """One line per call a routine was found for: its id, the outcome, the size."""
    from structlog.testing import capture_logs

    action, secret = await _webhook_routine(async_session)
    body = b'{"door": "front"}'

    with capture_logs() as logs:
        await async_client.post(
            f"{HOOKS}/{action.webhook_key}", content=body, headers=_signed(secret, body)
        )
        await async_client.post(
            f"{HOOKS}/{action.webhook_key}", content=body, headers=_signed("not-it", body)
        )

    ours = [entry for entry in logs if str(entry["event"]).startswith("routine_webhook")]
    assert [
        (entry["action_id"], entry["outcome"], entry["body_bytes"])
        for entry in ours
        if entry["event"] == "routine_webhook_call"
    ] == [(str(action.id), "accepted", len(body)), (str(action.id), "bad_signature", len(body))]
    flat = json.dumps(ours, default=str)
    assert action.webhook_key not in flat and secret not in flat and "front" not in flat


async def test_a_retried_delivery_is_kept_once(
    async_client: AsyncClient, async_session: AsyncSession
) -> None:
    action, secret = await _webhook_routine(async_session)
    body = b'{"n": 1}'
    headers = _signed(secret, body, **{"X-LIA-Delivery": "delivery-1"})

    first = await async_client.post(f"{HOOKS}/{action.webhook_key}", content=body, headers=headers)
    again = await async_client.post(f"{HOOKS}/{action.webhook_key}", content=body, headers=headers)

    assert (first.status_code, first.json()) == (202, {"status": "accepted"})
    assert (again.status_code, again.json()) == (202, {"status": "duplicate"})
    assert len(await _calls(async_session, action.id)) == 1


async def test_a_code_forge_signs_with_its_own_header_names(
    async_client: AsyncClient, async_session: AsyncSession
) -> None:
    action, secret = await _webhook_routine(async_session)
    body = b'{"action": "published"}'
    headers = {
        "X-Hub-Signature-256": signature_of(secret, body),
        "X-GitHub-Delivery": "72d3162e-cc78-11e3-81ab-4c9367dc0958",
        "Content-Type": "application/json",
    }

    answer = await async_client.post(f"{HOOKS}/{action.webhook_key}", content=body, headers=headers)

    assert answer.status_code == 202
    (call,) = await _calls(async_session, action.id)
    assert call.delivery_id == "72d3162e-cc78-11e3-81ab-4c9367dc0958"


async def test_a_wrong_signature_is_refused_and_keeps_nothing(
    async_client: AsyncClient, async_session: AsyncSession
) -> None:
    action, _secret = await _webhook_routine(async_session)
    body = b'{"door": "front"}'

    answer = await async_client.post(
        f"{HOOKS}/{action.webhook_key}", content=body, headers=_signed("not-the-secret", body)
    )
    unsigned = await async_client.post(f"{HOOKS}/{action.webhook_key}", content=body)

    assert answer.status_code == 403 and unsigned.status_code == 403
    assert await _calls(async_session, action.id) == []


async def test_an_unknown_and_a_paused_address_answer_alike(
    async_client: AsyncClient, async_session: AsyncSession
) -> None:
    paused, secret = await _webhook_routine(async_session, enabled=False)
    body = b"{}"

    unknown = await async_client.post(
        f"{HOOKS}/{draw_webhook_key()}", content=body, headers=_signed(secret, body)
    )
    asleep = await async_client.post(
        f"{HOOKS}/{paused.webhook_key}", content=body, headers=_signed(secret, body)
    )

    assert unknown.status_code == asleep.status_code == 404
    assert unknown.json() == asleep.json()
    assert await _calls(async_session, paused.id) == []


async def test_a_body_over_the_bound_is_refused_before_it_is_kept(
    async_client: AsyncClient, async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "routine_webhook_max_body_bytes", 1_024)
    action, secret = await _webhook_routine(async_session)
    body = json.dumps({"blob": "x" * 2_000}).encode()

    answer = await async_client.post(
        f"{HOOKS}/{action.webhook_key}", content=body, headers=_signed(secret, body)
    )

    assert answer.status_code == 413
    assert await _calls(async_session, action.id) == []


async def test_a_full_backlog_refuses_a_further_call(
    async_client: AsyncClient, async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "routine_webhook_max_pending", 1)
    action, secret = await _webhook_routine(async_session)

    first = await async_client.post(
        f"{HOOKS}/{action.webhook_key}", content=b"1", headers=_signed(secret, b"1")
    )
    second = await async_client.post(
        f"{HOOKS}/{action.webhook_key}", content=b"2", headers=_signed(secret, b"2")
    )

    assert first.status_code == 202
    assert second.status_code == 429
    assert second.headers["retry-after"]
    assert len(await _calls(async_session, action.id)) == 1


async def test_the_address_has_its_own_call_window(
    async_client: AsyncClient, async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "routine_webhook_rate_per_minute", 1)
    action, secret = await _webhook_routine(async_session)
    other, other_secret = await _webhook_routine(async_session)

    first = await async_client.post(
        f"{HOOKS}/{action.webhook_key}", content=b"1", headers=_signed(secret, b"1")
    )
    second = await async_client.post(
        f"{HOOKS}/{action.webhook_key}", content=b"2", headers=_signed(secret, b"2")
    )
    elsewhere = await async_client.post(
        f"{HOOKS}/{other.webhook_key}", content=b"3", headers=_signed(other_secret, b"3")
    )

    assert (first.status_code, second.status_code, elsewhere.status_code) == (202, 429, 202)


async def test_a_closed_switch_closes_the_address(
    async_client: AsyncClient, async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    action, secret = await _webhook_routine(async_session)
    monkeypatch.setattr(settings, "routine_webhooks_enabled", False)

    answer = await async_client.post(
        f"{HOOKS}/{action.webhook_key}", content=b"{}", headers=_signed(secret, b"{}")
    )

    assert answer.status_code == 403
    assert "routine_webhooks" in answer.text
    assert await _calls(async_session, action.id) == []


# ---------------------------------------------------------------------------
# The owner's side
# ---------------------------------------------------------------------------


_WEBHOOK_FORM: dict[str, Any] = {
    "title": "Door",
    "action_prompt": "Tell me who rang",
    "trigger_kind": "webhook",
}


async def test_a_new_webhook_routine_shows_its_secret_once(
    authenticated_client: tuple[AsyncClient, User], async_session: AsyncSession
) -> None:
    client, _user = authenticated_client

    created = await client.post(ROUTINES, json=_WEBHOOK_FORM)

    assert created.status_code == 201, created.text
    routine = created.json()
    assert created.headers["cache-control"] == "no-store"
    secret = routine["new_webhook_secret"]
    url = routine["webhook_url"]
    key = url.rsplit("/", 1)[1]
    assert url == f"{settings.api_url}{settings.api_prefix}{HOOKS.removeprefix('/api/v1')}/{key}"
    assert "webhook_key" not in routine and "webhook_secret" not in routine

    listed = await client.get(ROUTINES)
    stored = await async_session.get(ScheduledAction, UUID(routine["id"]), populate_existing=True)
    assert stored is not None and stored.webhook_secret is not None
    (shown,) = listed.json()["scheduled_actions"]
    assert shown["webhook_url"] == url and shown["new_webhook_secret"] is None
    assert secret not in listed.text and stored.webhook_secret not in listed.text

    body = b'{"door": "back"}'
    call = await client.post(f"{HOOKS}/{key}", content=body, headers=_signed(secret, body))
    assert call.status_code == 202


async def test_a_new_secret_retires_the_old_one_at_once(
    authenticated_client: tuple[AsyncClient, User],
) -> None:
    client, _user = authenticated_client
    routine = (await client.post(ROUTINES, json=_WEBHOOK_FORM)).json()
    key = routine["webhook_url"].rsplit("/", 1)[1]
    old = routine["new_webhook_secret"]

    drawn = await client.post(f"{ROUTINES}/{routine['id']}/webhook-secret")

    assert drawn.status_code == 200 and drawn.headers["cache-control"] == "no-store"
    new = drawn.json()["webhook_secret"]
    assert new != old and drawn.json()["webhook_url"] == routine["webhook_url"]
    body = b"{}"
    refused = await client.post(f"{HOOKS}/{key}", content=body, headers=_signed(old, body))
    accepted = await client.post(f"{HOOKS}/{key}", content=body, headers=_signed(new, body))
    assert (refused.status_code, accepted.status_code) == (403, 202)


async def test_leaving_the_clock_forgets_the_address_and_its_calls(
    authenticated_client: tuple[AsyncClient, User], async_session: AsyncSession
) -> None:
    client, _user = authenticated_client
    routine = (await client.post(ROUTINES, json=_WEBHOOK_FORM)).json()
    key = routine["webhook_url"].rsplit("/", 1)[1]
    body = b"{}"
    await client.post(
        f"{HOOKS}/{key}", content=body, headers=_signed(routine["new_webhook_secret"], body)
    )

    moved = await client.patch(
        f"{ROUTINES}/{routine['id']}",
        json={
            "trigger_kind": "time",
            "recurrence": {
                "freq": "daily",
                "times": {"mode": "at", "at": [{"hour": 8, "minute": 0}]},
                "anchor_date": "2026-11-01",
            },
        },
    )

    assert moved.status_code == 200, moved.text
    assert moved.json()["webhook_url"] is None
    stored = await async_session.get(ScheduledAction, UUID(routine["id"]), populate_existing=True)
    assert stored is not None
    assert (stored.webhook_key, stored.webhook_secret) == (None, None)
    assert await _calls(async_session, stored.id) == []
    gone = await client.post(f"{HOOKS}/{key}", content=body)
    assert gone.status_code == 404


async def test_a_routine_moved_onto_calls_is_answered_with_its_secret(
    authenticated_client: tuple[AsyncClient, User],
) -> None:
    client, _user = authenticated_client
    timed = await client.post(
        ROUTINES,
        json={
            "title": "Morning",
            "action_prompt": "Summarise my day",
            "recurrence": {
                "freq": "daily",
                "times": {"mode": "at", "at": [{"hour": 8, "minute": 0}]},
                "anchor_date": "2026-11-01",
            },
        },
    )
    assert timed.json()["new_webhook_secret"] is None

    moved = await client.patch(f"{ROUTINES}/{timed.json()['id']}", json={"trigger_kind": "webhook"})

    assert moved.status_code == 200, moved.text
    assert moved.json()["recurrence"] is None
    assert moved.json()["webhook_url"] and moved.json()["new_webhook_secret"]


async def test_a_webhook_routine_is_not_run_by_hand(
    authenticated_client: tuple[AsyncClient, User],
) -> None:
    client, _user = authenticated_client
    routine = (await client.post(ROUTINES, json=_WEBHOOK_FORM)).json()

    answer = await client.post(f"{ROUTINES}/{routine['id']}/execute")

    # The domain's validation refusal: a webhook routine is started by a call.
    assert answer.status_code == 400, answer.text
    assert "signed call" in answer.text


async def test_a_closed_switch_refuses_a_new_webhook_routine(
    authenticated_client: tuple[AsyncClient, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _user = authenticated_client
    monkeypatch.setattr(settings, "routine_webhooks_enabled", False)

    answer = await client.post(ROUTINES, json=_WEBHOOK_FORM)

    assert answer.status_code == 403
    assert "routine_webhooks" in answer.text


# ---------------------------------------------------------------------------
# The executor's tick, on committed rows, the engine alone replaced
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def maker(async_engine: Any, test_database_url: str) -> AsyncIterator[Any]:
    """A sessionmaker whose writes really commit, plus its clean-up."""
    engine = create_async_engine(test_database_url, echo=False)
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    marker = f"hook_tick_{uuid4().hex}@example.com"
    yield sessions, marker
    async with sessions() as session:
        await session.execute(delete(User).where(User.email == marker))
        await session.commit()
    await engine.dispose()


@pytest.fixture
def tick_world(
    maker: Any, monkeypatch: pytest.MonkeyPatch
) -> Callable[[RunResult | None], list[StreamRequest]]:
    """Route the executor's sessions to the test database and replace its engine.

    Returns a function installing the engine's answer (None = must not be
    called) and returning the list of requests it received.
    """
    sessions, _marker = maker

    @asynccontextmanager
    async def db_context() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            yield session
            await session.commit()

    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", db_context)
    monkeypatch.setattr(executor, "_usage_ceiling_reached", _never)
    monkeypatch.setattr(executor, "notify_result", _quiet)
    monkeypatch.setattr(executor, "send_routine_notice", _quiet)

    def install(answer: RunResult | None) -> list[StreamRequest]:
        received: list[StreamRequest] = []

        async def engine(request: StreamRequest) -> RunResult:
            received.append(request)
            assert answer is not None, "the engine must not run"
            return answer

        monkeypatch.setattr(executor, "stream_instruction", engine)
        return received

    return install


async def _never(*_args: Any, **_kwargs: Any) -> bool:
    return False


async def _quiet(*_args: Any, **_kwargs: Any) -> None:
    return None


async def _due_with_calls(sessions: Any, email: str, bodies: list[bytes]) -> tuple[UUID, UUID]:
    """A due webhook routine holding ``bodies`` as calls, reserved like a tick reserves it."""
    async with sessions() as session:
        action, _secret = await _webhook_routine(session, email=email)
        repo = RoutineWebhookRepository(session)
        start = now_utc() - timedelta(minutes=10)
        for index, body in enumerate(bodies):
            assert await repo.store(
                action.id,
                delivery_id=f"d-{index}",
                content_type="application/json",
                body=body,
                at=start + timedelta(minutes=index),
            )
        token = uuid4()
        await session.execute(
            update(ScheduledAction)
            .where(ScheduledAction.id == action.id)
            .values(
                next_trigger_at=start,
                status=ScheduledActionStatus.EXECUTING.value,
                execution_token=token,
            )
        )
        await session.commit()
        return action.id, token


async def _tick(sessions: Any, action_id: UUID, token: UUID) -> str:
    async with sessions() as session:
        action = await session.get(ScheduledAction, action_id)
        assert action is not None
        user_id = action.user_id
    return await executor.execute_single_action(action_id, user_id, execution_token=token)


async def _state(
    sessions: Any, action_id: UUID
) -> tuple[ScheduledAction, list[RoutineWebhookDelivery], list[ScheduledActionRun]]:
    async with sessions() as session:
        action = await session.get(ScheduledAction, action_id)
        assert action is not None
        runs = (
            await session.execute(
                select(ScheduledActionRun).where(
                    ScheduledActionRun.scheduled_action_id == action_id
                )
            )
        ).scalars()
        return action, await _calls(session, action_id), list(runs)


async def test_a_run_reads_the_calls_after_its_instruction_and_serves_them(
    maker: Any, tick_world: Any
) -> None:
    sessions, email = maker
    action_id, token = await _due_with_calls(
        sessions, email, [b'{"door": "front"}', b'{"door": "back"}']
    )
    received = tick_world(RunResult(outcome=RunOutcome.SUCCESS, text="Two rings.", attempts=1))

    await _tick(sessions, action_id, token)

    (request,) = received
    assert request.prompt.startswith(
        "Tell me who rang\n\n[Trigger context] This run was started by 2"
    )
    assert request.prompt.index('"front"') < request.prompt.index('"back"')
    action, calls, runs = await _state(sessions, action_id)
    assert [call.status for call in calls] == ["served", "served"]
    assert all(call.body is None and call.served_at is not None for call in calls)
    assert action.status == ScheduledActionStatus.ACTIVE.value and action.execution_count == 1
    assert action.next_trigger_at is not None  # looks again at the next pass
    assert [run.outcome for run in runs] == [ScheduledRunOutcome.SUCCESS]


async def test_a_tick_with_nothing_waiting_rests_and_writes_no_row(
    maker: Any, tick_world: Any
) -> None:
    sessions, email = maker
    action_id, token = await _due_with_calls(sessions, email, [])
    tick_world(None)

    await _tick(sessions, action_id, token)

    action, calls, runs = await _state(sessions, action_id)
    assert (action.status, action.next_trigger_at, action.execution_token) == (
        ScheduledActionStatus.ACTIVE.value,
        None,
        None,
    )
    assert calls == [] and runs == []


async def test_a_failed_run_keeps_the_calls_and_backs_off(maker: Any, tick_world: Any) -> None:
    sessions, email = maker
    action_id, token = await _due_with_calls(sessions, email, [b'{"door": "front"}'])
    tick_world(RunResult(outcome=RunOutcome.FAILED, error="TimeoutError", attempts=2))
    before = now_utc()

    await _tick(sessions, action_id, token)

    action, calls, runs = await _state(sessions, action_id)
    assert [call.status for call in calls] == ["pending"] and calls[0].body is not None
    assert action.consecutive_failures == 1
    assert action.next_trigger_at is not None
    assert action.next_trigger_at >= before + timedelta(
        seconds=ROUTINE_WEBHOOK_FAILURE_RETRY_SECONDS
    )
    assert [run.outcome for run in runs] == [ScheduledRunOutcome.FAILURE]


async def test_a_call_during_the_back_off_waits_for_it(maker: Any, tick_world: Any) -> None:
    """ADR-386 §7: a provider down for minutes is not a model call a minute and a
    pause after five. A sender that keeps calling does not cut a failed run's
    back-off short: its call waits with the others for the instant already armed."""
    sessions, email = maker
    action_id, token = await _due_with_calls(sessions, email, [b'{"door": "front"}'])
    tick_world(RunResult(outcome=RunOutcome.FAILED, error="TimeoutError", attempts=2))
    await _tick(sessions, action_id, token)
    backed_off, _waiting, _runs = await _state(sessions, action_id)
    assert backed_off.next_trigger_at is not None and backed_off.next_trigger_at > now_utc()
    assert backed_off.webhook_key is not None and backed_off.webhook_secret is not None
    body = b'{"door": "back"}'

    async with sessions() as session:
        outcome = await RoutineWebhookService(session).receive(
            backed_off.webhook_key,
            body=body,
            headers={
                "x-lia-signature-256": signature_of(decrypt_data(backed_off.webhook_secret), body)
            },
            at=now_utc(),
        )

    assert outcome is CallOutcome.ACCEPTED
    action, calls, _runs = await _state(sessions, action_id)
    assert [call.status for call in calls] == ["pending", "pending"]
    assert action.next_trigger_at == backed_off.next_trigger_at


async def test_leaving_the_clock_holds_the_routine_while_its_calls_are_forgotten(
    maker: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A call that lands while its owner moves the routine off calls is never kept
    for a routine that no longer reads calls: the forgetting runs under the
    routine's row lock, the one the door's write takes, so the door waits and then
    finds no address."""
    sessions, email = maker
    async with sessions() as session:
        action, secret = await _webhook_routine(session, email=email)
    forget = RoutineWebhookRepository.discard
    door: list[str] = []
    body = b'{"door": "side"}'

    async def forget_then_a_call_lands(self: RoutineWebhookRepository, action_id: UUID) -> int:
        gone = await forget(self, action_id)
        # Another connection, which gives up waiting for a lock after a moment.
        async with sessions.kw["bind"].connect() as connection:
            await connection.execute(text("SET lock_timeout = '300ms'"))
            await connection.commit()
            async with AsyncSession(bind=connection, expire_on_commit=False) as other:
                try:
                    outcome = await RoutineWebhookService(other).receive(
                        action.webhook_key,
                        body=body,
                        headers={"x-lia-signature-256": signature_of(secret, body)},
                        at=now_utc(),
                    )
                    door.append(outcome.value)
                except DBAPIError:
                    await other.rollback()
                    door.append("waits")
        return gone

    monkeypatch.setattr(RoutineWebhookRepository, "discard", forget_then_a_call_lands)
    edit = ScheduledActionUpdate.model_validate(
        {
            "trigger_kind": "time",
            "recurrence": {
                "freq": "daily",
                "times": {"mode": "at", "at": [{"hour": 8, "minute": 0}]},
                "anchor_date": "2026-11-01",
            },
        }
    )

    async with sessions() as session:
        await ScheduledActionService(session).update(action.id, action.user_id, edit)
        await session.commit()

    assert door == ["waits"]
    async with sessions() as session:
        assert await _calls(session, action.id) == []
        moved = await session.get(ScheduledAction, action.id)
        assert moved is not None and (moved.trigger_kind, moved.webhook_key) == ("time", None)


async def test_a_run_serves_its_share_and_the_rest_waits(
    maker: Any, tick_world: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "routine_webhook_max_per_run", 1)
    sessions, email = maker
    action_id, token = await _due_with_calls(sessions, email, [b"first", b"second"])
    received = tick_world(RunResult(outcome=RunOutcome.SUCCESS, text="One.", attempts=1))

    await _tick(sessions, action_id, token)

    assert "first" in received[0].prompt and "second" not in received[0].prompt
    action, calls, _runs = await _state(sessions, action_id)
    assert [call.status for call in calls] == ["served", "pending"]
    assert action.next_trigger_at is not None


async def test_a_closed_switch_stops_the_act_and_keeps_the_calls(
    maker: Any, tick_world: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessions, email = maker
    action_id, token = await _due_with_calls(sessions, email, [b'{"door": "front"}'])
    tick_world(None)
    monkeypatch.setattr(settings, "routine_webhooks_enabled", False)
    before = now_utc()

    await _tick(sessions, action_id, token)

    action, calls, runs = await _state(sessions, action_id)
    assert [call.status for call in calls] == ["pending"] and runs == []
    # It looks again after the back-off: a switch that reopens finds them served.
    assert action.next_trigger_at is not None
    assert action.next_trigger_at >= before + timedelta(
        seconds=ROUTINE_WEBHOOK_FAILURE_RETRY_SECONDS
    )


async def test_the_switch_is_read_once_before_the_routine_is_locked(
    maker: Any, tick_world: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-304: the rest is decided under the routine's row lock on the switch the
    tick read BEFORE taking it — never a store read while the row is held."""
    sessions, email = maker
    action_id, token = await _due_with_calls(sessions, email, [b'{"door": "front"}'])
    tick_world(None)
    reads: list[PlatformCapability] = []

    async def closed(capability: PlatformCapability) -> bool:
        reads.append(capability)
        return False

    monkeypatch.setattr(routine_webhook_gate, "is_capability_enabled", closed)
    before = now_utc()

    await _tick(sessions, action_id, token)

    assert reads == [PlatformCapability.ROUTINE_WEBHOOKS]
    action, calls, runs = await _state(sessions, action_id)
    assert [call.status for call in calls] == ["pending"] and runs == []
    assert action.next_trigger_at is not None
    assert action.next_trigger_at >= before + timedelta(
        seconds=ROUTINE_WEBHOOK_FAILURE_RETRY_SECONDS
    )


async def test_a_call_that_lands_while_the_tick_found_nothing_is_not_lost(
    maker: Any, tick_world: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessions, email = maker
    action_id, token = await _due_with_calls(sessions, email, [])
    tick_world(None)
    read = executor.waiting_calls

    async def read_then_a_call_lands(db: AsyncSession, action: ScheduledAction) -> Any:
        found = await read(db, action)
        # Another actor accepts a call between the tick's read and its settle.
        async with sessions() as other:
            assert await RoutineWebhookRepository(other).store(
                action_id, delivery_id=None, content_type=None, body=b"late", at=now_utc()
            )
            await other.commit()
        return found

    monkeypatch.setattr(executor, "waiting_calls", read_then_a_call_lands)

    await _tick(sessions, action_id, token)

    action, calls, _runs = await _state(sessions, action_id)
    assert [call.status for call in calls] == ["pending"]
    assert action.next_trigger_at is not None  # armed again, not asleep


async def test_an_idle_webhook_routine_is_never_closed_as_finished(maker: Any) -> None:
    sessions, email = maker
    async with sessions() as session:
        action, _secret = await _webhook_routine(session, email=email)

    async with sessions() as session:
        await ScheduledActionRepository(session).close_finished()
        await session.commit()

    async with sessions() as session:
        stored = await session.get(ScheduledAction, action.id)
        assert stored is not None
        assert (stored.is_enabled, stored.status) == (True, ScheduledActionStatus.ACTIVE.value)


# ---------------------------------------------------------------------------
# The repository's retention and the schema's invariants
# ---------------------------------------------------------------------------


async def test_served_calls_go_after_their_retention_and_waiting_ones_stay(
    async_session: AsyncSession,
) -> None:
    action, _secret = await _webhook_routine(async_session)
    repo = RoutineWebhookRepository(async_session)
    long_ago = now_utc() - timedelta(days=30)
    for index in range(3):
        # One second apart: the waiting calls are read oldest first.
        await repo.store(
            action.id,
            delivery_id=f"r-{index}",
            content_type=None,
            body=b"x",
            at=long_ago + timedelta(seconds=index),
        )
    calls = await repo.pending(action.id, limit=10)
    await repo.serve(action.id, [calls[0].id], at=long_ago)
    await repo.serve(action.id, [calls[1].id], at=now_utc())

    purged = await repo.purge_served_before(now_utc() - timedelta(days=7))

    assert purged == 1
    kept = await _calls(async_session, action.id)
    assert sorted(call.status for call in kept) == ["pending", "served"]
    # A served call's id is still recognised: the same delivery is not kept twice.
    assert await repo.already_received(action.id, "r-1")
    # Past its retention, a delivery is forgotten: sent again, it would be a new call.
    assert not await repo.already_received(action.id, "r-0")


async def test_the_table_refuses_a_routine_half_on_calls(async_session: AsyncSession) -> None:
    action, _secret = await _webhook_routine(async_session)

    with pytest.raises(IntegrityError, match="ck_scheduled_actions_webhook_address"):
        async with async_session.begin_nested():
            await async_session.execute(
                update(ScheduledAction)
                .where(ScheduledAction.id == action.id)
                .values(webhook_secret=None)
            )


async def test_the_table_refuses_a_served_call_that_kept_its_body(
    async_session: AsyncSession,
) -> None:
    action, _secret = await _webhook_routine(async_session)
    await RoutineWebhookRepository(async_session).store(
        action.id, delivery_id=None, content_type=None, body=b"x", at=now_utc()
    )

    with pytest.raises(IntegrityError, match="ck_routine_webhook_deliveries_served_body"):
        async with async_session.begin_nested():
            await async_session.execute(
                update(RoutineWebhookDelivery)
                .where(RoutineWebhookDelivery.scheduled_action_id == action.id)
                .values(status="served", served_at=now_utc())
            )


# ---------------------------------------------------------------------------
# The migration, both ways and back
# ---------------------------------------------------------------------------


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("routine_webhooks_migration", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _migrate(session: AsyncSession, step: Callable[[], None]) -> None:
    def _run(sync_session: Any) -> None:
        context = MigrationContext.configure(sync_session.connection())
        with Operations.context(context):
            step()

    await session.run_sync(_run)


async def test_the_migration_both_ways_and_back(async_session: AsyncSession) -> None:
    migration = _load_migration()
    action, _secret = await _webhook_routine(async_session)

    await _migrate(async_session, migration.downgrade)
    # A webhook routine has no clock the older schema can state: it went.
    remaining = await async_session.execute(
        text("SELECT count(*) FROM scheduled_actions WHERE id = :id"), {"id": action.id}
    )
    assert remaining.scalar_one() == 0
    columns = await async_session.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'scheduled_actions' AND column_name LIKE 'webhook%'"
        )
    )
    assert columns.scalars().all() == []

    await _migrate(async_session, migration.upgrade)
    again, _again_secret = await _webhook_routine(async_session)
    with pytest.raises(IntegrityError, match="ck_scheduled_actions_one_clock"):
        async with async_session.begin_nested():
            await async_session.execute(
                update(ScheduledAction)
                .where(ScheduledAction.id == again.id)
                .values(condition_config={"type": "task_overdue"})
            )
