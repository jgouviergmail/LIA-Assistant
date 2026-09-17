"""The ReAct loop must know the user's knowledge spaces, exactly as the pipeline does.

Measured on a dev instance (2026-09-17): a kept answer holding the very fact
a question asked for was RETRIEVED (above the retrieval gate) and injected
into the response prompt as ``<UserDocuments>``, yet the turn ran in ReAct
mode, whose loop carried no knowledge-space block and whose only door to the
spaces (``search_user_documents_tool``) had been dropped by the tool cap. The
loop spent its iterations on other records and presented a partial source
as the only one, although the passive block said otherwise. Same structural
gap as the memory profile (2026-08-28): what only reaches the response node
can reword an answer, never decide one.

The block is the pipeline's own (``rag_context`` of the prefetched bundle,
wrapped by the same section directive), read WITHOUT consuming the bundle so
the response node still pops it; when nothing was prefetched the loop fetches
inline through the pipeline's own function — never a second implementation.
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import HumanMessage

from src.domains.agents.nodes import react_context
from src.domains.agents.services import response_context as rc

pytestmark = [pytest.mark.unit]

DOCS = (
    "## Your documents\n\n[Space: Kept answers]\nThe meeting room booked for the workshop is B12."
)
_CONFIG: dict[str, Any] = {
    "configurable": {"thread_id": "thread-1"},
    "metadata": {"run_id": "run-k"},
}


def _state(text: str = "which room did we book for the workshop?") -> dict[str, Any]:
    return {"messages": [HumanMessage(content=text)]}


@pytest.fixture(autouse=True)
def _clean_registry() -> Any:
    rc.reset_response_context_prefetch()
    yield
    rc.reset_response_context_prefetch()


class TestTheLoopReceivesTheDocuments:
    async def test_the_prefetched_block_becomes_a_system_block_and_stays_for_the_pop(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Zero extra cost: the bundle the router prefetched is read, not consumed."""

        async def _fake_fetch(*_a: Any, **_k: Any) -> rc.ResponseContextBundle:
            return rc.ResponseContextBundle(rag_context=DOCS)

        monkeypatch.setattr(rc, "fetch_response_context", _fake_fetch)
        monkeypatch.setattr(rc.settings, "response_context_prefetch_enabled", True, raising=False)
        rc.start_response_context_prefetch({}, {}, "run-k")

        block = await react_context.build_knowledge_block(_state(), _CONFIG)

        assert block is not None
        assert DOCS in block
        assert block.startswith("<UserDocuments>")
        # The pipeline's own directive wraps it — one instruction per context.
        assert "PASSIVE UNTRUSTED REFERENCE" in block
        # The response node still finds its bundle afterwards.
        popped = await rc.pop_response_context("run-k")
        assert popped is not None and popped.rag_context == DOCS

    async def test_without_a_prefetch_the_loop_fetches_through_the_pipeline_function(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[dict[str, Any]] = []

        async def _fake_user_rag(**kwargs: Any) -> tuple[str | None, dict[str, Any] | None]:
            calls.append(kwargs)
            return DOCS, {"chunks_injected": 1}

        monkeypatch.setattr(react_context, "fetch_user_rag_context", _fake_user_rag)

        block = await react_context.build_knowledge_block(_state(), _CONFIG)

        assert block is not None and DOCS in block
        assert len(calls) == 1
        assert calls[0]["last_user_message"] == "which room did we book for the workshop?"
        assert calls[0]["run_id"] == "run-k"

    async def test_no_document_means_no_block(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def _nothing(**_kwargs: Any) -> tuple[str | None, dict[str, Any] | None]:
            return None, None

        monkeypatch.setattr(react_context, "fetch_user_rag_context", _nothing)

        assert await react_context.build_knowledge_block(_state(), _CONFIG) is None

    async def test_a_prefetched_bundle_without_documents_means_no_block(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _fake_fetch(*_a: Any, **_k: Any) -> rc.ResponseContextBundle:
            return rc.ResponseContextBundle(rag_context=None)

        inline: list[Any] = []

        async def _never(**kwargs: Any) -> tuple[str | None, dict[str, Any] | None]:
            inline.append(kwargs)
            return DOCS, None

        monkeypatch.setattr(rc, "fetch_response_context", _fake_fetch)
        monkeypatch.setattr(react_context, "fetch_user_rag_context", _never)
        monkeypatch.setattr(rc.settings, "response_context_prefetch_enabled", True, raising=False)
        rc.start_response_context_prefetch({}, {}, "run-k")

        assert await react_context.build_knowledge_block(_state(), _CONFIG) is None
        assert inline == [], "a prefetched answer is final — no second search is paid for"


class TestItNeverBreaksTheTurn:
    async def test_a_failing_fetch_is_swallowed_loudly(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _boom(**_kwargs: Any) -> tuple[str | None, dict[str, Any] | None]:
            raise RuntimeError("pgvector unavailable")

        monkeypatch.setattr(react_context, "fetch_user_rag_context", _boom)

        assert await react_context.build_knowledge_block(_state(), _CONFIG) is None


class TestTheSetupNodeMountsIt:
    def test_the_setup_node_asks_for_the_knowledge_block(self) -> None:
        """The builder exists to be mounted: the setup lists it with its siblings."""
        import inspect

        from src.domains.agents.nodes import react_nodes

        source = inspect.getsource(react_nodes.react_setup_node)
        assert "react_context.build_setup_blocks(state, config, intelligence)" in source
        assembler = inspect.getsource(react_context.build_setup_blocks)
        assert "build_knowledge_block(state, config)" in assembler
