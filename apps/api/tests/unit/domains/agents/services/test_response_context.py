"""Unit tests for the response-context prefetch module.

Covers the prefetch registry lifecycle (start / pop / eviction / kill-switch)
and the neutral-degradation contract of fetch_response_context.

Reference: services/response_context.py (initiative ∥ response latency overlap).
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.domains.agents.services import response_context as rc


@pytest.fixture(autouse=True)
def _isolated_registry() -> Any:
    """Guarantee an empty prefetch registry around every test."""
    rc.reset_response_context_prefetch()
    yield
    rc.reset_response_context_prefetch()


def _make_bundle(**overrides: Any) -> rc.ResponseContextBundle:
    return rc.ResponseContextBundle(**overrides)


@pytest.mark.unit
@pytest.mark.asyncio
class TestPrefetchRegistry:
    """start_response_context_prefetch / pop_response_context lifecycle."""

    async def test_start_then_pop_returns_bundle_marked_prefetched(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _fake_fetch(state: Any, config: Any, run_id: str) -> rc.ResponseContextBundle:
            return _make_bundle(psyche_context="XML")

        monkeypatch.setattr(rc, "fetch_response_context", _fake_fetch)
        monkeypatch.setattr(rc.settings, "response_context_prefetch_enabled", True, raising=False)

        rc.start_response_context_prefetch({}, {}, "run-1")
        bundle = await rc.pop_response_context("run-1")

        assert bundle is not None
        assert bundle.prefetched is True
        assert bundle.psyche_context == "XML"

    async def test_pop_without_start_returns_none(self) -> None:
        assert await rc.pop_response_context("never-started") is None

    async def test_pop_consumes_the_task(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def _fake_fetch(state: Any, config: Any, run_id: str) -> rc.ResponseContextBundle:
            return _make_bundle()

        monkeypatch.setattr(rc, "fetch_response_context", _fake_fetch)
        monkeypatch.setattr(rc.settings, "response_context_prefetch_enabled", True, raising=False)

        rc.start_response_context_prefetch({}, {}, "run-1")
        assert await rc.pop_response_context("run-1") is not None
        assert await rc.pop_response_context("run-1") is None

    async def test_start_is_idempotent_per_run_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []

        async def _fake_fetch(state: Any, config: Any, run_id: str) -> rc.ResponseContextBundle:
            calls.append(run_id)
            return _make_bundle()

        monkeypatch.setattr(rc, "fetch_response_context", _fake_fetch)
        monkeypatch.setattr(rc.settings, "response_context_prefetch_enabled", True, raising=False)

        rc.start_response_context_prefetch({}, {}, "run-1")
        rc.start_response_context_prefetch({}, {}, "run-1")
        await rc.pop_response_context("run-1")

        assert calls == ["run-1"]

    async def test_kill_switch_disables_prefetch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(rc.settings, "response_context_prefetch_enabled", False, raising=False)

        rc.start_response_context_prefetch({}, {}, "run-1")

        assert await rc.pop_response_context("run-1") is None

    async def test_unknown_run_id_is_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(rc.settings, "response_context_prefetch_enabled", True, raising=False)

        rc.start_response_context_prefetch({}, {}, "unknown")
        rc.start_response_context_prefetch({}, {}, "")

        assert await rc.pop_response_context("unknown") is None
        assert await rc.pop_response_context("") is None

    async def test_failed_fetch_returns_none_from_pop(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _boom(state: Any, config: Any, run_id: str) -> rc.ResponseContextBundle:
            raise RuntimeError("fetch exploded")

        monkeypatch.setattr(rc, "fetch_response_context", _boom)
        monkeypatch.setattr(rc.settings, "response_context_prefetch_enabled", True, raising=False)

        rc.start_response_context_prefetch({}, {}, "run-1")

        assert await rc.pop_response_context("run-1") is None

    async def test_pop_times_out_and_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def _slow_fetch(state: Any, config: Any, run_id: str) -> rc.ResponseContextBundle:
            await asyncio.sleep(30)
            return _make_bundle()

        monkeypatch.setattr(rc, "fetch_response_context", _slow_fetch)
        monkeypatch.setattr(rc.settings, "response_context_prefetch_enabled", True, raising=False)
        monkeypatch.setattr(
            rc.settings, "response_context_prefetch_await_timeout_seconds", 0.01, raising=False
        )

        rc.start_response_context_prefetch({}, {}, "run-1")

        assert await rc.pop_response_context("run-1") is None

    async def test_registry_bounded_with_eviction(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def _fake_fetch(state: Any, config: Any, run_id: str) -> rc.ResponseContextBundle:
            await asyncio.sleep(30)  # keep tasks pending so they stay registered
            return _make_bundle()

        monkeypatch.setattr(rc, "fetch_response_context", _fake_fetch)
        monkeypatch.setattr(rc.settings, "response_context_prefetch_enabled", True, raising=False)
        monkeypatch.setattr(rc.settings, "response_context_prefetch_max_entries", 2, raising=False)

        rc.start_response_context_prefetch({}, {}, "run-1")
        rc.start_response_context_prefetch({}, {}, "run-2")
        rc.start_response_context_prefetch({}, {}, "run-3")

        # Oldest evicted (and cancelled), newest two remain
        assert await rc.pop_response_context("run-1") is None
        assert "run-2" in rc._prefetch_tasks
        assert "run-3" in rc._prefetch_tasks


@pytest.mark.unit
@pytest.mark.asyncio
class TestFetchResponseContextNeutral:
    """fetch_response_context degrades to a neutral bundle without I/O."""

    async def test_empty_state_and_config_yield_neutral_bundle(self) -> None:
        bundle = await rc.fetch_response_context({}, {"configurable": {}}, "run-x")

        assert bundle.prefetched is False
        assert bundle.psychological_profile is None
        assert bundle.rag_context is None
        assert bundle.app_knowledge_context == ""
        assert bundle.journal_context == ""
        assert bundle.journal_injected_ids == []
        assert bundle.user_model_block == ""
        assert bundle.psyche_context == ""
        assert bundle.user_msg_is_trivial is True
        assert bundle.user_message_embedding is None


@pytest.mark.unit
class TestExtractLastUserMessage:
    """extract_last_user_message mirrors the response-node convention."""

    def test_returns_last_human_message_text(self) -> None:
        from langchain_core.messages import AIMessage, HumanMessage

        state = {
            "messages": [
                HumanMessage(content="first"),
                AIMessage(content="reply"),
                HumanMessage(content="second"),
            ]
        }
        assert rc.extract_last_user_message(state) == "second"

    def test_empty_state_returns_empty_string(self) -> None:
        assert rc.extract_last_user_message({}) == ""
