"""Degradation advisor — fail-open, cached, never inventing alternatives.

Contract: any failure (Redis down, DB down, flag off) returns an EMPTY list —
callers behave exactly as before this feature existed. Alternatives come from
the declared map only; local circuit-breaker state merges live (per-worker is
correct: the breaker that matters is the one of the worker serving this run).
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.domains.diagnostics import advisor as advisor_module
from src.domains.diagnostics.degradation_map import (
    BREAKER_DEGRADATIONS,
    assert_degradation_map_completeness,
)


@pytest.fixture
def wired(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {"breakers": {}, "redis": AsyncMock()}
    state["redis"].get = AsyncMock(return_value=None)
    state["redis"].set = AsyncMock(return_value=True)

    async def fake_redis() -> Any:
        return state["redis"]

    def fake_breaker_status() -> dict[str, dict[str, Any]]:
        return state["breakers"]

    async def fake_open_incidents() -> list[dict[str, Any]]:
        return state.get("incidents", [])

    monkeypatch.setattr(advisor_module, "get_redis_cache", fake_redis)
    monkeypatch.setattr(advisor_module, "_breaker_statuses", fake_breaker_status)
    monkeypatch.setattr(advisor_module, "_open_incident_entries", fake_open_incidents)
    monkeypatch.setattr(advisor_module.settings, "diagnostics_enabled", True)
    return state


@pytest.mark.unit
class TestDegradationMap:
    def test_real_map_passes_the_boot_assert(self) -> None:
        assert_degradation_map_completeness()

    def test_alternatives_reference_real_connector_services(self) -> None:
        from src.domains.connectors.models import ConnectorType

        known = {member.value for member in ConnectorType}
        for entry in BREAKER_DEGRADATIONS.values():
            if entry.alternative is not None:
                assert entry.alternative in known, entry.alternative


@pytest.mark.unit
class TestAdvisor:
    async def test_flag_off_returns_empty(self, wired: dict[str, Any], monkeypatch: Any) -> None:
        monkeypatch.setattr(advisor_module.settings, "diagnostics_enabled", False)
        wired["breakers"] = {"brave_search": {"state": "open"}}
        assert await advisor_module.get_active_degradations() == []

    async def test_healthy_platform_returns_empty(self, wired: dict[str, Any]) -> None:
        assert await advisor_module.get_active_degradations() == []

    async def test_open_breaker_maps_to_capability_and_alternative(
        self, wired: dict[str, Any]
    ) -> None:
        wired["breakers"] = {"brave_search": {"state": "open"}}
        degradations = await advisor_module.get_active_degradations()
        assert len(degradations) == 1
        entry = degradations[0]
        assert entry.capability == "web_search"
        assert entry.alternative == "perplexity"
        assert entry.reason == "circuit_open:brave_search"

    async def test_apikey_prefixed_breaker_maps_through_normalization(
        self, wired: dict[str, Any]
    ) -> None:
        """API-key clients name their breaker `apikey_<connector>` (measured in
        the CI logs of this very release) — the advisor must still map them."""
        wired["breakers"] = {"apikey_brave_search": {"state": "open"}}
        degradations = await advisor_module.get_active_degradations()
        assert degradations[0].capability == "web_search"
        assert degradations[0].alternative == "perplexity"
        assert degradations[0].reason == "circuit_open:apikey_brave_search"

    async def test_unmapped_open_breaker_still_reported_without_alternative(
        self, wired: dict[str, Any]
    ) -> None:
        wired["breakers"] = {"philips_hue": {"state": "open"}}
        degradations = await advisor_module.get_active_degradations()
        assert degradations[0].capability == "philips_hue"
        assert degradations[0].alternative is None

    async def test_open_incident_becomes_platform_degradation(self, wired: dict[str, Any]) -> None:
        wired["incidents"] = [{"correlation_key": "RedisDown", "severity": "critical"}]
        degradations = await advisor_module.get_active_degradations()
        assert degradations[0].capability == "platform:RedisDown"
        assert degradations[0].status == "critical"

    async def test_incident_view_is_cached_and_cache_hit_skips_the_db(
        self, wired: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        wired["incidents"] = [{"correlation_key": "RedisDown", "severity": "critical"}]
        await advisor_module.get_active_degradations()
        wired["redis"].set.assert_awaited()  # view was cached with a TTL
        _, set_kwargs = wired["redis"].set.await_args
        assert set_kwargs.get("ex") is not None

        # Cache hit: the DB path must not run.
        cached = json.dumps([{"correlation_key": "RedisDown", "severity": "critical"}])
        wired["redis"].get = AsyncMock(return_value=cached)

        async def must_not_run() -> list[dict[str, Any]]:
            raise AssertionError("DB path must not run on cache hit")

        monkeypatch.setattr(advisor_module, "_open_incident_entries", must_not_run)
        degradations = await advisor_module.get_active_degradations()
        assert degradations[0].capability == "platform:RedisDown"

    async def test_any_exception_fails_open_to_empty(
        self, wired: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def broken() -> Any:
            raise ConnectionError("db down")

        wired["redis"].get = AsyncMock(side_effect=ConnectionError("redis down"))
        monkeypatch.setattr(advisor_module, "_open_incident_entries", broken)
        assert await advisor_module.get_active_degradations() == []


@pytest.mark.unit
class TestFormatBlock:
    def test_empty_list_formats_to_empty_string_zero_tokens(self) -> None:
        assert advisor_module.format_degradations_block([]) == ""

    def test_non_empty_block_names_capability_and_alternative(self) -> None:
        from src.domains.diagnostics.advisor import CapabilityDegradation

        block = advisor_module.format_degradations_block(
            [
                CapabilityDegradation(
                    capability="web_search",
                    status="degraded",
                    reason="circuit_open:brave_search",
                    alternative="perplexity",
                )
            ]
        )
        assert "web_search" in block
        assert "perplexity" in block
        assert block.startswith("PLATFORM DEGRADATIONS")
