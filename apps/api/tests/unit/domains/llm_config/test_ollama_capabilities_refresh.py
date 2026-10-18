"""The Ollama address drives the capability refresh (ADR-267).

The Ollama URL travels as a provider key, so ``LLMConfigOverrideCache.load_from_db``
is the one moment every reader agrees it may have changed: boot, an admin key edit,
a cross-worker invalidation. But that path also runs when an admin saves ANY slot,
and the discovery is network I/O: refreshing there unconditionally would make each
of those saves wait for the timeout whenever the server is unreachable. So the
refresh is driven by the ADDRESS, and what a running server holds is refreshed by
the admin's own model listing (which discovers on every open, TTL-bounded). An
address that answered nothing is retried by a later reload, at most once per
``ollama_discovery_retry_seconds``.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import AbstractContextManager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.core.config import settings
from src.domains.llm_config import cache as cache_module
from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache
from src.infrastructure.llm.model_profiles import ModelProfile

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _reset() -> Generator[None]:
    LLMConfigOverrideCache._ollama_refreshed_url = None
    LLMConfigOverrideCache._ollama_refreshed_at = 0.0
    ModelCapabilitiesCache.reset()
    yield
    LLMConfigOverrideCache._ollama_refreshed_url = None
    LLMConfigOverrideCache._ollama_refreshed_at = 0.0
    ModelCapabilitiesCache.reset()


def _clock(value: float) -> AbstractContextManager[object]:
    """Freeze the cache's own clock, and nobody else's."""
    return patch.object(cache_module, "time", SimpleNamespace(monotonic=lambda: value))


def _window(seconds: float) -> AbstractContextManager[object]:
    return patch.object(settings, "ollama_discovery_retry_seconds", seconds)


def _url(value: str | None) -> AbstractContextManager[object]:
    return patch(
        "src.infrastructure.llm.providers.ollama_urls.resolve_ollama_url", return_value=value
    )


def _refresh() -> AbstractContextManager[AsyncMock]:
    return patch(
        "src.infrastructure.llm.providers.ollama_discovery.refresh_ollama_capabilities",
        new_callable=AsyncMock,
    )


def _publish(model: str = "qwen3.8:27b") -> None:
    ModelCapabilitiesCache.merge_discovered(
        "ollama", {model: ModelProfile(model_id=model, capability_provenance="discovered")}
    )


async def test_no_configured_url_means_no_network_at_all() -> None:
    with _url(None), _refresh() as refresh:
        await LLMConfigOverrideCache._refresh_ollama_capabilities()
    refresh.assert_not_awaited()


async def test_the_first_reload_with_an_address_discovers() -> None:
    with _url("http://h:11434"), _refresh() as refresh:
        await LLMConfigOverrideCache._refresh_ollama_capabilities()
    refresh.assert_awaited_once()


async def test_an_unchanged_address_does_no_network_on_the_next_reload() -> None:
    """An admin saving an unrelated slot must not wait for a discovery."""
    with _url("http://h:11434"), _refresh() as refresh:
        await LLMConfigOverrideCache._refresh_ollama_capabilities()
        _publish()  # the discovery populated the layer
        await LLMConfigOverrideCache._refresh_ollama_capabilities()
    assert refresh.await_count == 1


async def test_a_changed_address_discovers_again() -> None:
    with _url("http://old:11434"), _refresh() as refresh:
        await LLMConfigOverrideCache._refresh_ollama_capabilities()
        _publish()
    with _url("http://new:11434"), _refresh() as refresh_2:
        await LLMConfigOverrideCache._refresh_ollama_capabilities()
    assert refresh.await_count == 1
    refresh_2.assert_awaited_once()


async def test_an_unreachable_address_is_not_rediscovered_by_every_reload() -> None:
    """Production 2026-10-17: every slot an admin saved waited 5 s for a server that was down."""
    with _url("http://h:11434"), _refresh() as refresh, _window(600.0):
        with _clock(1000.0):
            await LLMConfigOverrideCache._refresh_ollama_capabilities()
        with _clock(1599.0):
            await LLMConfigOverrideCache._refresh_ollama_capabilities()
    assert refresh.await_count == 1


async def test_an_empty_layer_is_retried_once_the_window_has_passed() -> None:
    """A server that was down at boot is still picked up by a later reload."""
    with _url("http://h:11434"), _refresh() as refresh, _window(600.0):
        with _clock(1000.0):
            await LLMConfigOverrideCache._refresh_ollama_capabilities()
        with _clock(1600.0):
            await LLMConfigOverrideCache._refresh_ollama_capabilities()
    assert refresh.await_count == 2


async def test_a_zero_window_retries_on_every_reload() -> None:
    with _url("http://h:11434"), _refresh() as refresh, _window(0.0), _clock(1000.0):
        await LLMConfigOverrideCache._refresh_ollama_capabilities()
        await LLMConfigOverrideCache._refresh_ollama_capabilities()
    assert refresh.await_count == 2


async def test_removing_the_address_drops_what_the_server_had_declared() -> None:
    with _url("http://h:11434"), _refresh():
        await LLMConfigOverrideCache._refresh_ollama_capabilities()
        _publish()
    with _url(None), _refresh() as refresh:
        await LLMConfigOverrideCache._refresh_ollama_capabilities()
    refresh.assert_not_awaited()
    assert ModelCapabilitiesCache.get("qwen3.8:27b") is None


async def test_a_failing_refresh_never_fails_the_config_reload() -> None:
    with (
        _url("http://h:11434"),
        patch(
            "src.infrastructure.llm.providers.ollama_discovery.refresh_ollama_capabilities",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ),
    ):
        await LLMConfigOverrideCache._refresh_ollama_capabilities()  # must not raise
