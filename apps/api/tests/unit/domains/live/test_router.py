"""The live routes (ADR-299): auth binding, published bounds, typed refusals."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.config import settings
from src.core.constants import LIVE_DELEGATION_TOOL_NAME, LIVE_SESSION_BUDGET_EUR_MAX
from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.live.router import router

pytestmark = pytest.mark.unit

USER_ID = uuid.uuid4()
MODULE = "src.domains.live.router"


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_active_session] = lambda: SimpleNamespace(
        id=USER_ID,
        language="fr",
        timezone="Europe/Paris",
        full_name="Alex",
        email="a@x.y",
        live_preferences={"end_of_speech": "calm"},
    )
    app.dependency_overrides[get_db] = lambda: MagicMock()
    # The capability switch is a dependency of its own; the wiring guard checks it.
    for dependency in router.dependencies:
        app.dependency_overrides[dependency.dependency] = lambda: None
    return TestClient(app)


def test_config_publishes_the_settings_and_the_bridge_lines(client: TestClient) -> None:
    body = client.get("/live/config").json()
    assert body["session_max_minutes"] == settings.live_session_max_minutes
    # The per-model bounds are published because they are enforced (ADR-184).
    assert body["idle_timeout_bounds"] == {"min": 5, "max": 3600}
    assert body["session_max_bounds"] == {"min": 1, "max": 240}
    assert body["unlimited_value"] == 0
    # The delivery notes travel with the config: one per register (ADR-253).
    assert set(body["tone_lines"]) == {
        "celebratory",
        "playful",
        "warm",
        "curious",
        "assured",
        "factual",
        "careful",
        "questioning",
        "surprised",
        "concerned",
        "apologetic",
        "weary",
    }
    assert body["delegation_timeout_seconds"] == settings.live_delegation_timeout_seconds
    assert body["delegation_tool_name"] == LIVE_DELEGATION_TOOL_NAME
    # The browser reads four of them; the three others are the server-side
    # bridge's (ADR-301), published from the same reader so the two cannot drift.
    assert set(body["delegation_lines"]) == {
        "timed_out",
        "result_cut",
        "superseded",
        "empty_request",
        "busy",
        "quota_blocked",
        "failed",
        "budget_exhausted",
    }
    # A direct session's browser-held line (ADR-300 wave 4).
    assert set(body["direct_lines"]) == {"lookup_failed"}
    assert body["direct_lines"]["lookup_failed"].strip()


def test_missing_connectors_read_as_an_empty_list_not_as_a_failure(client: TestClient) -> None:
    # The header asks « is there one? » on every load: an absence is an
    # answer. Only STARTING a session without one is a 409 (service tests).
    from src.domains.live.schemas import LiveConnectorsResponse

    with patch(f"{MODULE}.LiveConnectorService") as service:
        service.return_value.connectors_response = AsyncMock(
            return_value=LiveConnectorsResponse(connectors=[], active_provider=None)
        )
        response = client.get("/live/connectors")
    assert response.status_code == 200
    assert response.json() == {"connectors": [], "active_provider": None}


def test_put_connector_names_its_provider(client: TestClient) -> None:
    from src.domains.live.schemas import (
        LiveConnectorResponse,
        LiveConnectorSettings,
        LiveModelCapabilitiesResponse,
    )

    saved = LiveConnectorResponse(
        provider="gemini",
        connector_type="gemini_live",
        status="active",
        settings=LiveConnectorSettings(
            model="gemini-3.8-live",
            voice="Kore",
            thinking_level=None,
            idle_timeout_seconds=60,
            session_max_minutes=10,
        ),
        functionally_verified=True,
        capabilities=LiveModelCapabilitiesResponse(
            **dict.fromkeys(LiveModelCapabilitiesResponse.model_fields, True)
        ),
        active=True,
    )
    with patch(f"{MODULE}.LiveConnectorService") as service:
        service.return_value.update_connector_settings = AsyncMock(return_value=saved)
        response = client.put(
            "/live/connectors/gemini",
            json={
                "model": "gemini-3.8-live",
                "voice": "Kore",
                "thinking_level": None,
                "idle_timeout_seconds": 0,
                "session_max_minutes": 30,
            },
        )
    assert response.status_code == 200 and response.json()["active"] is True
    args = service.return_value.update_connector_settings.call_args.args
    assert args[1] == "gemini" and args[2].voice == "Kore"
    assert args[2].idle_timeout_seconds == 0 and args[2].session_max_minutes == 30
    # An out-of-bounds duration is refused by the schema (the bounds are published).
    with patch(f"{MODULE}.LiveConnectorService") as service:
        refused = client.put(
            "/live/connectors/gemini",
            json={
                "model": "m",
                "voice": "Kore",
                "idle_timeout_seconds": 2,
                "session_max_minutes": 10,
            },
        )
        assert refused.status_code == 422
        service.return_value.update_connector_settings.assert_not_called()


def test_offer_route_hands_the_sdp_and_the_credential_to_the_service(client: TestClient) -> None:
    from src.domains.live.schemas import LiveOfferResponse

    with patch(f"{MODULE}.LiveService") as service:
        service.return_value.exchange_offer = AsyncMock(return_value=LiveOfferResponse(sdp="v=0 a"))
        response = client.post(
            "/live/sessions/abc/offer", json={"credential": "n" * 40, "sdp": "v=0 " + "o" * 20}
        )
    assert response.status_code == 200 and response.json() == {"sdp": "v=0 a"}
    args = service.return_value.exchange_offer.call_args
    assert args.args[1] == "abc" and args.args[2].credential == "n" * 40
    # A short credential or a bare SDP is refused by the schema before any service call.
    with patch(f"{MODULE}.LiveService") as service:
        assert (
            client.post(
                "/live/sessions/abc/offer", json={"credential": "x", "sdp": "v=0"}
            ).status_code
            == 422
        )
        service.return_value.exchange_offer.assert_not_called()


def test_voices_take_the_provider_as_a_query(client: TestClient) -> None:
    from src.domains.live.schemas import LiveVoicesResponse

    with patch(f"{MODULE}.LiveConnectorService") as service:
        service.return_value.list_voices = AsyncMock(
            return_value=LiveVoicesResponse(provider="gemini", voices=[], provenance="published")
        )
        response = client.get("/live/voices?provider=gemini")
    assert response.status_code == 200
    assert service.return_value.list_voices.call_args.kwargs["provider_id"] == "gemini"


def test_preferences_read_the_column_tolerantly(client: TestClient) -> None:
    body = client.get("/live/preferences").json()
    assert body["end_of_speech"] == "calm"
    assert body["interruptions"] is True


def test_preferences_refuse_a_word_off_the_ladder(client: TestClient) -> None:
    response = client.put(
        "/live/preferences",
        json={
            "interruptions": True,
            "end_of_speech": "shout",
            "result_delivery": "interrupt",
        },
    )
    assert response.status_code == 422


def test_start_relays_the_service(client: TestClient) -> None:
    started = {
        "credential": "auth_tokens/t",
        "credential_expires_at": "2030-01-01T00:00:00Z",
        "connect_deadline_at": "2030-01-01T00:00:00Z",
        "setup": {"model": "models/m"},
        "session_id": "a" * 32,
        "provider": "gemini",
        "model": "m",
        "run_id": "live_session_" + "a" * 32,
        "expires_at": "2026-09-19T10:10:00+00:00",
        "preferences": {
            "interruptions": True,
            "end_of_speech": "normal",
            "result_delivery": "interrupt",
        },
        "capabilities": {
            "async_delegation": True,
            "delivery_scheduling": True,
            "reports_idle": False,
            "cancels_on_interruption": True,
            "configurable_vad": True,
            "resumes": True,
            "thinking": False,
        },
        "connection": "token",
        "session_max_minutes": 10,
        "idle_timeout_seconds": 60,
        "delegation_tool_name": LIVE_DELEGATION_TOOL_NAME,
        "delegation_timeout_seconds": 90,
        "delegation_result_max_tokens": 600,
        "turn_text_max_chars": 4000,
        "rates": {
            "pricing_unit": "per_1m_tokens",
            "input_unit_price": 0.75,
            "output_unit_price": 4.5,
            "audio_input_unit_price": 3.0,
            "audio_output_unit_price": 12.0,
            "usd_eur_rate": 0.9,
        },
    }
    from src.domains.live.schemas import LiveSessionStartResponse

    with patch(f"{MODULE}.LiveService") as service:
        service.return_value.start = AsyncMock(return_value=LiveSessionStartResponse(**started))
        response = client.post("/live/sessions")
    assert response.status_code == 200
    assert response.json()["credential"] == "auth_tokens/t"
    kwargs = service.return_value.start.call_args.kwargs
    assert kwargs["display_name"] == "Alex" and kwargs["timezone"] == "Europe/Paris"
    # No body is a delegated session (the shape every earlier client sends).
    assert kwargs["mode"] == "delegated"


def test_start_names_the_mode_from_its_body(client: TestClient) -> None:
    with patch(f"{MODULE}.LiveService") as service:
        service.return_value.start = AsyncMock(side_effect=RuntimeError("stop here"))
        with pytest.raises(RuntimeError):
            client.post("/live/sessions", json={"mode": "direct"})
    assert service.return_value.start.call_args.kwargs["mode"] == "direct"
    # A word off the vocabulary is a 422, never a delegated session by accident.
    assert client.post("/live/sessions", json={"mode": "relay"}).status_code == 422


def test_tool_door_relays_the_service_with_the_person_s_facts(client: TestClient) -> None:
    from src.domains.live.schemas import LiveToolCallResponse

    with patch(f"{MODULE}.LiveService") as service:
        service.return_value.run_tool = AsyncMock(
            return_value=LiveToolCallResponse(text="Two events tomorrow.", ok=True)
        )
        response = client.post(
            "/live/sessions/" + "a" * 32 + "/tools",
            json={"name": "get_events_tool", "arguments": {"query": "tomorrow"}},
        )
    assert response.status_code == 200
    assert response.json() == {"text": "Two events tomorrow.", "ok": True, "activity": None}
    args, kwargs = service.return_value.run_tool.call_args
    assert args[1] == "a" * 32
    assert args[2].name == "get_events_tool" and args[2].arguments == {"query": "tomorrow"}
    assert kwargs == {"language": "fr", "timezone": "Europe/Paris", "display_name": "Alex"}


def test_tool_door_bounds_the_arguments_it_accepts(client: TestClient) -> None:
    from src.core.constants import LIVE_TOOL_CALL_MAX_ARGUMENTS

    too_many = {f"k{i}": i for i in range(LIVE_TOOL_CALL_MAX_ARGUMENTS + 1)}
    with patch(f"{MODULE}.LiveService"):
        response = client.post(
            "/live/sessions/" + "a" * 32 + "/tools",
            json={"name": "get_events_tool", "arguments": too_many},
        )
    assert response.status_code == 422
    with patch(f"{MODULE}.LiveService"):
        assert (
            client.post("/live/sessions/" + "a" * 32 + "/tools", json={"name": ""}).status_code
            == 422
        )


def test_voice_sample_relays_the_service(client: TestClient) -> None:
    from src.domains.live.schemas import LiveVoiceSampleResponse

    with patch(f"{MODULE}.LiveConnectorService") as service:
        service.return_value.sample_voice = AsyncMock(
            return_value=LiveVoiceSampleResponse(audio_base64="UklGRg==", sample_rate=24_000)
        )
        response = client.post("/live/voices/sample", json={"voice": "Kore"})
    assert response.status_code == 200
    assert response.json()["format"] == "wav"
    payload = service.return_value.sample_voice.call_args.args[1]
    assert payload.voice == "Kore" and payload.api_key is None and payload.provider == "gemini"


def test_config_publishes_the_cap_the_idle_and_the_extension_bounds(client: TestClient) -> None:
    # Every bound the client enforces is published (ADR-184).
    body = client.get("/live/config").json()
    assert body["session_max_minutes"] == settings.live_session_max_minutes
    assert body["idle_timeout_seconds"] == settings.live_idle_timeout_seconds
    assert body["extension_minutes"] == settings.live_extension_minutes
    assert body["extension_prompt_seconds"] == settings.live_extension_prompt_seconds


def test_extend_relays_the_service(client: TestClient) -> None:
    from src.domains.live.schemas import LiveExtendResponse

    with patch(f"{MODULE}.LiveService") as service:
        service.return_value.extend = AsyncMock(
            return_value=LiveExtendResponse(
                expires_at=datetime(2026, 9, 19, 10, 0, tzinfo=UTC), extensions=1
            )
        )
        response = client.post(f"/live/sessions/{'a' * 32}/extend")
    assert response.status_code == 200
    assert response.json()["extensions"] == 1
    assert service.return_value.extend.call_args.args[1] == "a" * 32


def test_end_carries_the_clients_technical_detail_bounded(client: TestClient) -> None:
    # An outcome alone left a provider close unexplained (measured 2026-09-19:
    # a session that died in five seconds): the client's technical word (the
    # close code and reason) rides the end request, bounded, for the log.
    from src.domains.live.schemas import LiveEndResponse

    with patch(f"{MODULE}.LiveService") as service:
        service.return_value.end = AsyncMock(
            return_value=LiveEndResponse(
                summary_message_id=None,
                duration_seconds=5,
                delegations=0,
                voice_turns=0,
                usage=None,
            )
        )
        response = client.post(
            f"/live/sessions/{'a' * 32}/end",
            json={
                "outcome": "provider_closed",
                "detail": "close 1007: Request contains an invalid argument.",
            },
        )
        assert response.status_code == 200
        payload = service.return_value.end.call_args.args[2]
        assert payload.outcome == "provider_closed"
        assert payload.detail == "close 1007: Request contains an invalid argument."
        refused = client.post(
            f"/live/sessions/{'a' * 32}/end", json={"outcome": "ended", "detail": "x" * 201}
        )
        assert refused.status_code == 422


def test_discover_needs_a_plausible_key(client: TestClient) -> None:
    assert client.post("/live/models/discover", json={"api_key": "short"}).status_code == 422


def test_published_voices_need_no_connector(client: TestClient) -> None:
    body = client.get("/live/voices/published").json()
    assert body["provenance"] == "published" and len(body["voices"]) == 30


# -- the per-session spend ceiling (ADR-300 wave 3) -----------------------------


def test_config_publishes_the_ceilings_bound(client: TestClient) -> None:
    body = client.get("/live/config").json()
    assert body["session_budget_eur_max"] == LIVE_SESSION_BUDGET_EUR_MAX


def test_put_refuses_a_ceiling_over_the_published_bound(client: TestClient) -> None:
    with patch(f"{MODULE}.LiveConnectorService") as service:
        refused = client.put(
            "/live/connectors/gemini",
            json={
                "model": "gemini-3.8-live",
                "voice": "Kore",
                "idle_timeout_seconds": 60,
                "session_max_minutes": 10,
                "session_budget_eur": LIVE_SESSION_BUDGET_EUR_MAX + 1,
            },
        )
    assert refused.status_code == 422
    service.return_value.update_connector_settings.assert_not_called()
