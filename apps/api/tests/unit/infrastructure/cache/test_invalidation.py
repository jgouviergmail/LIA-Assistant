"""Unit tests for cross-worker cache invalidation (ADR-063)."""

from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.infrastructure.cache.invalidation import (
    _handle_message,
    _registry,
    publish_cache_invalidation,
    register_cache,
    verify_registry_completeness,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    """Reset registry before each test."""
    _registry.clear()
    yield
    _registry.clear()


# ── Registry ──────────────────────────────────────────────────────────────


class TestRegisterCache:
    def test_register_and_lookup(self) -> None:
        handler = AsyncMock()
        register_cache("test_cache", handler)
        assert _registry["test_cache"] is handler

    def test_register_overwrites(self) -> None:
        handler1 = AsyncMock()
        handler2 = AsyncMock()
        register_cache("test_cache", handler1)
        register_cache("test_cache", handler2)
        assert _registry["test_cache"] is handler2


# ── Publish ───────────────────────────────────────────────────────────────


class TestPublishCacheInvalidation:
    @pytest.mark.asyncio
    async def test_publish_sends_correct_payload(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.publish = AsyncMock(return_value=3)

        with patch(
            "src.infrastructure.cache.invalidation.get_redis_cache",
            return_value=mock_redis,
        ):
            await publish_cache_invalidation("llm_config")

        mock_redis.publish.assert_called_once()
        channel, payload = mock_redis.publish.call_args[0]
        assert channel == "cache:invalidation"
        data = json.loads(payload)
        assert data["cache_name"] == "llm_config"
        assert data["publisher_pid"] == os.getpid()

    @pytest.mark.asyncio
    async def test_publish_resilient_to_redis_failure(self) -> None:
        with patch(
            "src.infrastructure.cache.invalidation.get_redis_cache",
            side_effect=ConnectionError("Redis down"),
        ):
            # Should not raise
            await publish_cache_invalidation("llm_config")


# ── Message Handling ──────────────────────────────────────────────────────


class TestHandleMessage:
    @pytest.mark.asyncio
    async def test_dispatches_to_handler(self) -> None:
        handler = AsyncMock()
        register_cache("test_cache", handler)

        msg = json.dumps({"cache_name": "test_cache", "publisher_pid": -1})
        await _handle_message(msg)

        handler.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_self_pid(self) -> None:
        handler = AsyncMock()
        register_cache("test_cache", handler)

        msg = json.dumps({"cache_name": "test_cache", "publisher_pid": os.getpid()})
        await _handle_message(msg)

        handler.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unknown_cache_name(self) -> None:
        msg = json.dumps({"cache_name": "nonexistent", "publisher_pid": -1})
        # Should not raise
        await _handle_message(msg)

    @pytest.mark.asyncio
    async def test_bad_json(self) -> None:
        # Should not raise
        await _handle_message("not valid json {{{")

    @pytest.mark.asyncio
    async def test_missing_fields(self) -> None:
        # Should not raise
        await _handle_message(json.dumps({"cache_name": "test"}))

    @pytest.mark.asyncio
    async def test_handler_error_does_not_propagate(self) -> None:
        handler = AsyncMock(side_effect=RuntimeError("boom"))
        register_cache("test_cache", handler)

        msg = json.dumps({"cache_name": "test_cache", "publisher_pid": -1})
        # Should not raise
        await _handle_message(msg)
        handler.assert_awaited_once()


# ── Registry Verification ─────────────────────────────────────────────────


class TestVerifyRegistryCompleteness:
    @patch("src.core.config.settings")
    def test_all_registered(self, mock_settings: MagicMock) -> None:
        mock_settings.skills_enabled = True
        register_cache("llm_config", AsyncMock())
        register_cache("pricing", AsyncMock())
        register_cache("google_api_pricing", AsyncMock())
        register_cache("skills", AsyncMock())
        # Should not log error
        verify_registry_completeness()

    @patch("src.core.config.settings")
    def test_missing_handler_logs_error(self, mock_settings: MagicMock) -> None:
        mock_settings.skills_enabled = False
        # Only register one
        register_cache("llm_config", AsyncMock())
        # Should log error for missing pricing + google_api_pricing
        verify_registry_completeness()

    @patch("src.core.config.settings")
    def test_skills_excluded_when_disabled(self, mock_settings: MagicMock) -> None:
        mock_settings.skills_enabled = False
        register_cache("llm_config", AsyncMock())
        register_cache("pricing", AsyncMock())
        register_cache("google_api_pricing", AsyncMock())
        # Should pass — skills not expected when disabled
        verify_registry_completeness()
