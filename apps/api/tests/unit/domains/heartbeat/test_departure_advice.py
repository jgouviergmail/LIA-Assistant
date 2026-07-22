"""Smart departure advice (P6, Lot 6) — calendar × route × weather fusion.

Second-pass consumer of the already-fetched calendar events: for the first
located event within the lookahead, computes a traffic-aware ETA and a
leave-by time. Strict budget: ≤ 1 Routes call per cycle, Redis-cached.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.heartbeat.context_sources import fetch_departure_advice
from src.domains.heartbeat.schemas import HeartbeatContext, HeartbeatDecision

NOW = datetime.now(UTC)


def _settings(**overrides):
    defaults = {
        "heartbeat_departure_enabled": True,
        "heartbeat_departure_lookahead_hours": 3,
        "heartbeat_departure_cache_ttl_seconds": 900,
        # Mirrors the real Settings contract (language fallback source).
        "default_language": "en",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _user():
    return SimpleNamespace(timezone="Europe/Paris")


def _event(hours_ahead=2.0, location="10 rue de la Paix, Paris"):
    start = NOW + timedelta(hours=hours_ahead)
    return {
        "summary": "Réunion client",
        "start": "14:00",
        "end": "15:00",
        "location": location,
        "start_raw": {"dateTime": start.isoformat()},
    }


def _redis(cached=None):
    redis = MagicMock()
    redis.get = AsyncMock(return_value=cached)
    redis.set = AsyncMock()
    return redis


def _location_service():
    svc = MagicMock()
    svc.get_effective_location_for_proactive = AsyncMock(
        return_value=SimpleNamespace(lat=45.75, lon=4.85, source="home")
    )
    return svc


async def _call(events, *, settings=None, redis=None, route_result=None, route_error=None):
    routes_client = MagicMock()
    if route_error is not None:
        routes_client.compute_route = AsyncMock(side_effect=route_error)
    else:
        routes_client.compute_route = AsyncMock(
            return_value=route_result or {"routes": [{"duration": "1800s"}]}
        )
    routes_client.close = AsyncMock()

    with (
        patch(
            "src.infrastructure.cache.redis.get_redis_cache",
            AsyncMock(return_value=redis if redis is not None else _redis()),
        ),
        patch(
            "src.domains.users.user_location_service.UserLocationService",
            return_value=_location_service(),
        ),
        patch(
            "src.domains.connectors.clients.google_routes_client.GoogleRoutesClient",
            return_value=routes_client,
        ),
    ):
        result = await fetch_departure_advice(uuid4(), _user(), settings or _settings(), events)
    return result, routes_client


@pytest.mark.unit
class TestFetchDepartureAdvice:
    async def test_flag_off_returns_none(self):
        result, client = await _call(
            [_event()], settings=_settings(heartbeat_departure_enabled=False)
        )
        assert result is None
        client.compute_route.assert_not_awaited()

    async def test_no_located_event_returns_none(self):
        result, client = await _call([_event(location=None)])
        assert result is None
        client.compute_route.assert_not_awaited()

    async def test_event_beyond_lookahead_returns_none(self):
        result, client = await _call([_event(hours_ahead=8.0)])
        assert result is None
        client.compute_route.assert_not_awaited()

    async def test_happy_path_computes_leave_by(self):
        result, client = await _call([_event(hours_ahead=2.0)])

        assert result is not None
        assert result["event_title"] == "Réunion client"
        assert result["eta_minutes"] == 30
        assert result["destination"] == "10 rue de la Paix, Paris"
        # leave_by = start − ETA, rendered in the user's local timezone
        assert "leave_by_local" in result and result["leave_by_local"]
        client.compute_route.assert_awaited_once()
        kwargs = client.compute_route.await_args.kwargs
        assert kwargs["destination"] == "10 rue de la Paix, Paris"
        assert kwargs["arrival_time"] is not None

    async def test_cache_hit_skips_routes_call(self):
        import json

        cached = {"event_title": "Réunion client", "eta_minutes": 25}
        result, client = await _call([_event()], redis=_redis(cached=json.dumps(cached)))
        assert result == cached
        client.compute_route.assert_not_awaited()

    async def test_routes_failure_degrades_to_none(self):
        result, _ = await _call([_event()], route_error=RuntimeError("quota"))
        assert result is None

    async def test_cache_key_is_deterministic_across_processes(self):
        """The budget cache must survive worker restarts: no builtin hash().

        Python's str hash is randomized per process (PYTHONHASHSEED), so a
        hash()-derived key would miss the cache on every other worker and
        defeat the paid-Routes budget. The recipe is pinned: sha1 of the
        event identity triple.
        """
        import hashlib

        from src.domains.heartbeat.context_sources import _departure_cache_key

        user_id = uuid4()
        event = _event(hours_ahead=2.0)
        start = datetime.fromisoformat(event["start_raw"]["dateTime"])

        key = _departure_cache_key(user_id, event, start)
        digest = hashlib.sha1(
            f"{event['summary']}|{event['location']}|{start.isoformat()}".encode(),
            usedforsecurity=False,
        ).hexdigest()[:16]
        assert key == f"heartbeat:departure:{user_id}:{digest}"
        # Stable on recall (same inputs, same key — the cache contract)
        assert _departure_cache_key(user_id, event, start) == key

    async def test_no_home_location_is_a_silent_gate_not_a_warning(self):
        """No configured home location is an EXPECTED state (bonus source):
        it must return None without emitting the failure warning every cycle."""
        from src.domains.users.user_location_service import NoLocationAvailableError

        svc = MagicMock()
        svc.get_effective_location_for_proactive = AsyncMock(
            side_effect=NoLocationAvailableError("no home")
        )
        routes_client = MagicMock()
        routes_client.compute_route = AsyncMock()
        routes_client.close = AsyncMock()

        with (
            patch(
                "src.infrastructure.cache.redis.get_redis_cache",
                AsyncMock(return_value=_redis()),
            ),
            patch(
                "src.domains.users.user_location_service.UserLocationService",
                return_value=svc,
            ),
            patch(
                "src.domains.connectors.clients.google_routes_client.GoogleRoutesClient",
                return_value=routes_client,
            ),
            patch("src.domains.heartbeat.context_sources.logger") as mock_logger,
        ):
            result = await fetch_departure_advice(uuid4(), _user(), _settings(), [_event()])

        assert result is None
        routes_client.compute_route.assert_not_awaited()
        mock_logger.warning.assert_not_called()

    async def test_language_fallback_is_central_default_not_inline_french(self):
        """A user without a language must get the deployment's configured
        default language, never a hardcoded 'fr' literal (i18n systemic rule).
        The settings view carries default_language='it' so a literal fails."""
        routes_client = MagicMock()
        routes_client.compute_route = AsyncMock(return_value={"routes": [{"duration": "600s"}]})
        routes_client.close = AsyncMock()

        with (
            patch(
                "src.infrastructure.cache.redis.get_redis_cache",
                AsyncMock(return_value=_redis()),
            ),
            patch(
                "src.domains.users.user_location_service.UserLocationService",
                return_value=_location_service(),
            ),
            patch(
                "src.domains.connectors.clients.google_routes_client.GoogleRoutesClient",
                return_value=routes_client,
            ) as client_cls,
        ):
            user = SimpleNamespace(timezone="Europe/Paris", language=None)
            result = await fetch_departure_advice(
                uuid4(), user, _settings(default_language="it"), [_event()]
            )

        assert result is not None
        client_cls.assert_called_once_with(language="it")


@pytest.mark.unit
class TestDepartureContextRendering:
    def test_prompt_section_and_label(self):
        ctx = HeartbeatContext(
            departure_advice={
                "event_title": "Réunion client",
                "event_start_local": "14:00",
                "eta_minutes": 30,
                "leave_by_local": "13:30",
                "destination": "10 rue de la Paix, Paris",
            }
        )
        rendered = ctx.to_prompt_context()
        assert "DEPARTURE ADVICE" in rendered
        assert "13:30" in rendered

        decision = HeartbeatDecision(
            action="notify",
            reason="leave soon",
            message_draft="Pars vers 13:30 !",
            sources_used=["DEPARTURE_ADVICE"],
        )
        assert decision.sources_used == ["DEPARTURE_ADVICE"]

    def test_rule_20_present_in_decision_prompt(self):
        from src.domains.agents.prompts.prompt_loader import load_prompt

        content = load_prompt("heartbeat_decision_prompt")
        assert "20." in content and "DEPARTURE ADVICE" in content
