"""Personal controls stay reachable independently of the background producer and tools."""

import pytest

from src.core.config import settings
from src.core.session_dependencies import get_current_active_session
from src.main import app

pytestmark = pytest.mark.integration


@pytest.fixture
def discussion_session(test_user, monkeypatch):
    import src.domains.proactive_discussions.router as routes

    monkeypatch.setattr(routes, "kick_context_rebuild", lambda owner, epoch: None)
    app.dependency_overrides[get_current_active_session] = lambda: test_user
    yield
    app.dependency_overrides.pop(get_current_active_session, None)


async def test_settings_and_context_are_visible_while_producer_is_off(
    async_client,
    discussion_session,
    monkeypatch,
):
    monkeypatch.setattr(settings, "proactive_discussions_enabled", False, raising=False)
    response = await async_client.get("/api/v1/proactive-discussions/settings")
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    value = response.json()
    assert value["policy"]["enabled"] is False
    assert value["policy"]["sources"] == []
    assert len(value["sources"]) == 22
    assert value["producer_enabled"] is False
    context = await async_client.get("/api/v1/proactive-discussions/context")
    assert context.status_code == 200, context.text
    assert context.json()["items"] == []


async def test_settings_patch_distinguishes_unlimited_from_absent_and_enforces_cas(
    async_client,
    discussion_session,
):
    response = await async_client.patch(
        "/api/v1/proactive-discussions/settings",
        json={
            "expected_revision": 0,
            "changes": {"enabled": True, "daily_max": None, "sources": ["portrait"]},
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["policy"]["daily_max"] is None
    response = await async_client.patch(
        "/api/v1/proactive-discussions/settings",
        json={
            "expected_revision": 0,
            "changes": {"enabled": False},
        },
    )
    assert response.status_code == 409
    value = (await async_client.get("/api/v1/proactive-discussions/settings")).json()["policy"]
    assert value["enabled"] is True and value["sources"] == ["portrait"]


@pytest.mark.parametrize(
    "payload",
    [
        {"expected_revision": 0, "changes": {"enabled": "true"}},
        {"expected_revision": 0, "changes": {"sources": ["unknown"]}},
        {"expected_revision": 0, "changes": {"is_superuser": True}},
        {"expected_revision": 0, "changes": {"sources": None}},
    ],
)
async def test_bad_settings_never_echo_private_values(async_client, discussion_session, payload):
    response = await async_client.patch("/api/v1/proactive-discussions/settings", json=payload)
    assert response.status_code == 422
    assert response.json() == {"detail": {"error_code": "INVALID_INPUT"}}


async def test_context_purge_and_rebuild_keep_explicit_epoch_fences(
    async_client, discussion_session
):
    purge = await async_client.post(
        "/api/v1/proactive-discussions/context/purge",
        json={"expected_epoch": 0, "expected_generation": 0},
    )
    assert purge.status_code == 200, purge.text
    assert purge.json()["context_epoch"] == 1
    stale = await async_client.post(
        "/api/v1/proactive-discussions/context/rebuild", json={"expected_epoch": 0}
    )
    assert stale.status_code == 409
    rebuild = await async_client.post(
        "/api/v1/proactive-discussions/context/rebuild", json={"expected_epoch": 1}
    )
    assert rebuild.status_code == 200, rebuild.text
    assert rebuild.json()["refresh_requested"] is True


async def test_purge_refuses_a_generation_newer_than_the_preview(async_client, discussion_session):
    response = await async_client.post(
        "/api/v1/proactive-discussions/context/purge",
        json={"expected_epoch": 0, "expected_generation": 7},
    )
    assert response.status_code == 409


async def test_rebuild_kicks_owned_background_work_only_after_a_valid_request(
    async_client, discussion_session, test_user, monkeypatch
):
    import src.domains.proactive_discussions.router as routes

    calls = []
    monkeypatch.setattr(
        routes,
        "kick_context_rebuild",
        lambda owner, epoch: calls.append((owner, epoch)),
        raising=False,
    )
    response = await async_client.post(
        "/api/v1/proactive-discussions/context/rebuild", json={"expected_epoch": 0}
    )
    assert response.status_code == 200
    assert calls == [(test_user.id, response.json()["context_epoch"])]
    stale = await async_client.post(
        "/api/v1/proactive-discussions/context/rebuild", json={"expected_epoch": 0}
    )
    assert stale.status_code == 409
    assert len(calls) == 1


async def test_a_second_rebuild_request_never_fences_off_the_one_in_flight(
    async_client, discussion_session, monkeypatch
):
    import src.domains.proactive_discussions.router as routes

    calls = []
    monkeypatch.setattr(
        routes, "kick_context_rebuild", lambda owner, epoch: calls.append(epoch), raising=False
    )
    first = await async_client.post(
        "/api/v1/proactive-discussions/context/rebuild", json={"expected_epoch": 0}
    )
    epoch = first.json()["context_epoch"]
    again = await async_client.post(
        "/api/v1/proactive-discussions/context/rebuild", json={"expected_epoch": epoch}
    )
    assert again.status_code == 200, again.text
    assert again.json()["context_epoch"] == epoch and again.json()["refresh_requested"] is True
    # The repeat only re-wakes a worker for the SAME epoch: nothing in flight is invalidated.
    assert calls == [epoch, epoch]


async def test_activity_reads_a_requested_rebuild_and_a_closed_allowance(
    async_client, discussion_session, monkeypatch
):
    for name in (
        "discussion_owner_daily_budget_usd",
        "discussion_instance_daily_budget_usd",
        "discussion_run_budget_usd",
    ):
        monkeypatch.setattr(settings, name, None)
    idle = await async_client.get("/api/v1/proactive-discussions/activity")
    assert idle.status_code == 200, idle.text
    assert idle.headers["cache-control"] == "no-store"
    assert idle.json() == {
        "rebuild": "idle",
        "obstacle": None,
        "last_rebuild": None,
        "last_update": None,
        "last_run": None,
        "budget": {"configured": False, "reached": None, "resets_at": None},
        "awaiting_reply": None,
    }
    await async_client.post(
        "/api/v1/proactive-discussions/context/rebuild", json={"expected_epoch": 0}
    )
    requested = (await async_client.get("/api/v1/proactive-discussions/activity")).json()
    assert requested["rebuild"] == "requested" and requested["obstacle"] is None
