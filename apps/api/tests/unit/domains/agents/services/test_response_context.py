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
        async def _fake_fetch(
            state: Any, config: Any, run_id: str, **_kw: Any
        ) -> rc.ResponseContextBundle:
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
        async def _fake_fetch(
            state: Any, config: Any, run_id: str, **_kw: Any
        ) -> rc.ResponseContextBundle:
            return _make_bundle()

        monkeypatch.setattr(rc, "fetch_response_context", _fake_fetch)
        monkeypatch.setattr(rc.settings, "response_context_prefetch_enabled", True, raising=False)

        rc.start_response_context_prefetch({}, {}, "run-1")
        assert await rc.pop_response_context("run-1") is not None
        assert await rc.pop_response_context("run-1") is None

    async def test_start_is_idempotent_per_run_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []

        async def _fake_fetch(
            state: Any, config: Any, run_id: str, **_kw: Any
        ) -> rc.ResponseContextBundle:
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
        async def _boom(
            state: Any, config: Any, run_id: str, **_kw: Any
        ) -> rc.ResponseContextBundle:
            raise RuntimeError("fetch exploded")

        monkeypatch.setattr(rc, "fetch_response_context", _boom)
        monkeypatch.setattr(rc.settings, "response_context_prefetch_enabled", True, raising=False)

        rc.start_response_context_prefetch({}, {}, "run-1")

        assert await rc.pop_response_context("run-1") is None

    async def test_pop_times_out_and_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def _slow_fetch(
            state: Any, config: Any, run_id: str, **_kw: Any
        ) -> rc.ResponseContextBundle:
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
        async def _fake_fetch(
            state: Any, config: Any, run_id: str, **_kw: Any
        ) -> rc.ResponseContextBundle:
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
@pytest.mark.asyncio
class TestSystemRagDeferral:
    """Latency lot R2 — router-entry prefetch defers the QI-dependent system RAG.

    `_inject_system_rag` reads `is_app_help_query` from query_intelligence,
    which does not exist yet when the prefetch starts at router entry: the
    bundle must flag the deferral so the response node resolves it inline
    with the fresh, current-turn intelligence.
    """

    async def test_include_system_rag_false_sets_deferred_flag(self) -> None:
        bundle = await rc.fetch_response_context(
            {}, {"configurable": {}}, "run-x", include_system_rag=False
        )

        assert bundle.system_rag_deferred is True
        assert bundle.app_knowledge_context == ""

    async def test_default_keeps_system_rag_inline(self) -> None:
        bundle = await rc.fetch_response_context({}, {"configurable": {}}, "run-x")

        assert bundle.system_rag_deferred is False

    async def test_start_prefetch_propagates_include_system_rag(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: dict[str, Any] = {}

        async def _fake_fetch(
            state: Any, config: Any, run_id: str, include_system_rag: bool = True
        ) -> rc.ResponseContextBundle:
            seen["include_system_rag"] = include_system_rag
            return _make_bundle()

        monkeypatch.setattr(rc, "fetch_response_context", _fake_fetch)
        monkeypatch.setattr(rc.settings, "response_context_prefetch_enabled", True, raising=False)

        rc.start_response_context_prefetch({}, {}, "run-1", include_system_rag=False)
        assert await rc.pop_response_context("run-1") is not None
        assert seen["include_system_rag"] is False

    async def test_fetch_app_knowledge_context_empty_when_not_app_help(self) -> None:
        assert await rc.fetch_app_knowledge_context({}, "any question", "run-x") == ""

    async def test_fetch_app_knowledge_context_marker_on_app_help(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # System RAG chunks disabled → the bare APP_HELP_QUERY marker is
        # returned (get_response_prompt then loads the app identity prompt).
        monkeypatch.setattr(rc.settings, "rag_spaces_system_enabled", False, raising=False)
        state = {"query_intelligence": {"is_app_help_query": True}}

        ctx = await rc.fetch_app_knowledge_context(state, "how do I use LIA?", "run-x")

        assert ctx == "APP_HELP_QUERY"


@pytest.mark.unit
@pytest.mark.asyncio
class TestUserRagDebugPayload:
    """The RAG debug payload publishes the bounds it enforced (ADR-242).

    A score shown next to a threshold nobody can see is unreadable: the debug
    panel draws ``min_score`` as a tick on every bar, and explains an empty
    result with the value that caused it. That only works if the backend ships
    the number alongside the results.
    """

    async def _run(self, monkeypatch: pytest.MonkeyPatch, chunks: list[Any]) -> dict[str, Any]:
        from uuid import uuid4

        class _Ctx:
            async def __aenter__(self) -> Any:
                return object()

            async def __aexit__(self, *_a: Any) -> bool:
                return False

        result = type(
            "R",
            (),
            {
                "chunks": chunks,
                "spaces_searched": 1,
                "total_results": len(chunks),
                "to_prompt_context": lambda self: "CTX",
            },
        )()

        async def _fake_retrieve(**_kw: Any) -> Any:
            return result

        monkeypatch.setattr(rc.settings, "rag_spaces_enabled", True, raising=False)
        monkeypatch.setattr(rc.settings, "rag_spaces_retrieval_min_score", 0.62, raising=False)
        monkeypatch.setattr(rc.settings, "rag_spaces_retrieval_limit", 5, raising=False)
        monkeypatch.setattr(
            "src.domains.rag_spaces.retrieval.retrieve_rag_context", _fake_retrieve, raising=False
        )
        monkeypatch.setattr(
            "src.infrastructure.database.session.get_db_context", lambda: _Ctx(), raising=False
        )

        from langchain_core.messages import HumanMessage

        bundle = await rc.fetch_response_context(
            {"messages": [HumanMessage(content="what does my contract say?")]},
            {"configurable": {"langgraph_user_id": str(uuid4()), "thread_id": "t-1"}},
            "run-1",
        )
        return bundle.rag_injection_debug or {}

    async def test_payload_carries_the_enforced_bounds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        chunk = type(
            "C", (), {"space_name": "Legal", "original_filename": "c.pdf", "score": 0.74}
        )()

        debug = await self._run(monkeypatch, [chunk])

        assert debug.get("settings") == {"min_score": 0.62, "max_results": 5}

    async def test_bounds_are_published_even_when_nothing_matched(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The empty case is precisely when the reader needs the threshold."""
        debug = await self._run(monkeypatch, [])

        assert debug == {} or debug.get("settings") == {"min_score": 0.62, "max_results": 5}


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


@pytest.mark.unit
@pytest.mark.asyncio
class TestPeerContextInjectionFailsSoft:
    """An enrichment must never be able to cost the user their answer.

    The injection promises its "own failure boundary", but the UUID conversion
    that feeds it sat OUTSIDE the try — so a malformed `langgraph_user_id`
    raised straight through `asyncio.gather` and took the whole response node
    with it. Same shape as the psyche injection right above it, which wraps its
    own `UUID(...)` for exactly this reason.
    """

    async def test_a_malformed_user_id_degrades_to_no_context(self) -> None:
        from langchain_core.messages import HumanMessage

        bundle = await rc.fetch_response_context(
            {"messages": [HumanMessage(content="des nouvelles de Marie ?")]},
            {"configurable": {"langgraph_user_id": "not-a-uuid"}},
            "run-x",
        )

        assert bundle.peer_context == ""
