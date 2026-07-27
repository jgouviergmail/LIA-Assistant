"""Startup FAQ indexation: one writer, and embeddings before destruction.

Production ran four uvicorn workers, each executing the whole startup
indexation. The staleness check was a plain read, so all four passed it, all four
embedded the 269-chunk corpus, and all four ran a delete-then-insert whose
interleaving left duplicates behind — measured on 2026-07-27: **807 chunks for
269 distinct contents**, three copies of every answer. Retrieval sorts by score
and truncates, and exact duplicates score identically, so the top five held two
distinct answers instead of five.

Two properties are pinned here, both of which the pre-fix code violated:

1. **One writer.** The space row is claimed with ``FOR UPDATE SKIP LOCKED``;
   losers return "skipped" without embedding or writing anything.
2. **Embed, then destroy.** Nothing is deleted until every vector is in hand, so
   a quota rejection costs nothing and cannot empty the corpus.

Plus the bounded retry: the Gemini SDK is built with no retry options, which
selects its "never retry" strategy, so a single transient 429 used to cost a full
staleness cycle. Retrying must stay bounded in attempts *and* wall clock, because
it happens while the claim on the space row is held.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.exceptions import BaseAPIException
from src.domains.rag_spaces import system_indexer as system_indexer_module
from src.domains.rag_spaces.system_indexer import SystemSpaceIndexer, _retry_reason

CHUNKS_IN_KNOWLEDGE_DIR = 3

# ==========================================================================
# Doubles
# ==========================================================================


class _FakeApiError(Exception):
    """Stand-in for ``google.genai.errors.APIError`` — only ``code`` matters."""

    def __init__(self, code: int) -> None:
        """Store the HTTP status the way the SDK does.

        Args:
            code: HTTP status code.
        """
        super().__init__(f"{code} from provider")
        self.code = code


def _wrapped(code: int) -> Exception:
    """An embedding failure shaped like the real one.

    langchain re-raises every provider failure as ``GoogleGenerativeAIError``
    with the SDK error as ``__cause__``, so the status is never on the exception
    the caller sees.

    Args:
        code: HTTP status carried by the cause.

    Returns:
        The outer exception, with its cause attached.
    """
    outer = RuntimeError("Error embedding content")
    outer.__cause__ = _FakeApiError(code)
    return outer


class _ScriptedEmbeddings:
    """Embedding client replaying a scripted sequence of outcomes."""

    def __init__(self, outcomes: list[Exception | None] | None = None) -> None:
        """Prepare the script.

        Args:
            outcomes: One entry per call; an exception is raised, None succeeds.
                Exhausting the script means "succeed from now on".
        """
        self._outcomes = list(outcomes or [])
        self.calls: list[list[str]] = []

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        """Record the call and honour the script.

        Args:
            texts: Batch to embed.

        Returns:
            One two-dimensional vector per text.

        Raises:
            Exception: When the script says so.
        """
        self.calls.append(list(texts))
        outcome = self._outcomes.pop(0) if self._outcomes else None
        if outcome is not None:
            raise outcome
        return [[0.1, 0.2] for _ in texts]


# ==========================================================================
# Fixtures
# ==========================================================================


@pytest.fixture
def knowledge_dir(tmp_path: Any) -> Any:
    """A knowledge directory holding three Q/A chunks.

    Args:
        tmp_path: pytest temporary directory.

    Returns:
        The directory path.
    """
    (tmp_path / "01_intro.md").write_text(
        "# Intro\n\n## What is LIA?\nAn assistant.\n\n## How to start?\nJust talk.\n",
        encoding="utf-8",
    )
    (tmp_path / "02_features.md").write_text(
        "# Features\n\n## Email support?\nYes.\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def indexer(knowledge_dir: Any) -> Any:
    """An indexer whose collaborators are mocks, wired for a stale space.

    Args:
        knowledge_dir: Directory the indexer will read.

    Returns:
        The indexer, with ``order`` recording the sequence of side effects.
    """
    with (
        patch("src.domains.rag_spaces.system_indexer.RAGSpaceService"),
        patch("src.domains.rag_spaces.system_indexer.RAGDocumentRepository"),
        patch("src.domains.rag_spaces.system_indexer.RAGChunkRepository"),
    ):
        idx = SystemSpaceIndexer(AsyncMock())

    idx.service = AsyncMock()
    idx.doc_repo = AsyncMock()
    idx.chunk_repo = AsyncMock()

    stale = MagicMock()
    stale.id = "space-uuid"
    stale.content_hash = "stale-hash"
    idx.service.space_repo.get_system_space_by_name = AsyncMock(return_value=stale)
    idx.service.space_repo.claim_system_space_for_reindex = AsyncMock(return_value=stale)

    # An intact corpus of the size ``knowledge_dir`` parses to, so the staleness
    # decision is driven by the hash alone unless a test says otherwise.
    idx.chunk_repo.count_for_space = AsyncMock(return_value=CHUNKS_IN_KNOWLEDGE_DIR)
    idx.doc_repo.count_for_space = AsyncMock(return_value=1)

    order: list[str] = []
    idx.chunk_repo.delete_by_space = AsyncMock(side_effect=lambda *_: order.append("delete_chunks"))
    idx.doc_repo.get_all_for_space = AsyncMock(return_value=[])

    def _insert(objs: list[Any]) -> int:
        order.append("insert")
        return len(objs)

    idx.chunk_repo.bulk_create_chunks = AsyncMock(side_effect=_insert)
    idx.service.update_system_space_hash = AsyncMock(
        side_effect=lambda *_: order.append("update_hash")
    )
    idx.order = order  # type: ignore[attr-defined]
    idx.knowledge_dir = knowledge_dir  # type: ignore[attr-defined]
    return idx


@pytest.fixture
def embeddings(monkeypatch: pytest.MonkeyPatch, indexer: Any) -> _ScriptedEmbeddings:
    """Install a scripted embedding client and record its position in the order.

    Args:
        monkeypatch: pytest monkeypatch fixture.
        indexer: Indexer under test.

    Returns:
        The scripted client.
    """
    stub = _ScriptedEmbeddings()
    original = stub.aembed_documents

    async def _recording(texts: list[str]) -> list[list[float]]:
        indexer.order.append("embed")
        return await original(texts)

    stub.aembed_documents = _recording  # type: ignore[method-assign]
    monkeypatch.setattr(system_indexer_module, "get_rag_embeddings", lambda: stub)
    return stub


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Record backoff delays instead of waiting them out.

    Args:
        monkeypatch: pytest monkeypatch fixture.

    Returns:
        The list of requested delays, in order.
    """
    delays: list[float] = []

    async def _sleep(seconds: float) -> None:
        delays.append(seconds)

    # Swap the module's handle, not ``asyncio.sleep`` itself: rewiring the
    # stdlib for the duration of a test reaches everything else running under
    # the same loop. ``system_indexer`` uses nothing else from asyncio.
    monkeypatch.setattr(system_indexer_module, "asyncio", SimpleNamespace(sleep=_sleep))
    return delays


def _run(indexer: Any) -> Any:
    """Invoke the indexation against the fixture's knowledge directory.

    Args:
        indexer: Indexer under test.

    Returns:
        The coroutine to await.
    """
    return indexer.index_faq_space()


# ==========================================================================
# One writer
# ==========================================================================


@pytest.mark.unit
class TestSingleWriter:
    """Only the worker that claims the space row may index it."""

    async def test_a_worker_that_loses_the_claim_does_nothing(
        self, indexer: Any, embeddings: _ScriptedEmbeddings
    ) -> None:
        """No claim means no embedding, no delete, and an honest reason.

        Args:
            indexer: Indexer under test.
            embeddings: Scripted embedding client.
        """
        indexer.service.space_repo.claim_system_space_for_reindex = AsyncMock(return_value=None)

        with patch.object(indexer, "_resolve_knowledge_dir", return_value=indexer.knowledge_dir):
            result = await _run(indexer)

        assert result["status"] == "skipped"
        assert result["reason"] == "claimed_by_another_worker"
        assert result["chunks_created"] == 0
        assert embeddings.calls == []
        assert indexer.order == []

    async def test_hash_that_turned_fresh_under_the_claim_is_respected(
        self, indexer: Any, embeddings: _ScriptedEmbeddings
    ) -> None:
        """The winner may have committed between our read and our claim.

        The pre-check at step 3 read a stale row; the claim at step 4 reloads it.
        Without ``populate_existing`` the identity map would return the stale
        instance and this worker would re-index over fresh work.

        Args:
            indexer: Indexer under test.
            embeddings: Scripted embedding client.
        """
        with patch.object(indexer, "_resolve_knowledge_dir", return_value=indexer.knowledge_dir):
            fresh = MagicMock()
            fresh.id = "space-uuid"
            fresh.content_hash = indexer.compute_content_hash(indexer.knowledge_dir)
            indexer.service.space_repo.claim_system_space_for_reindex = AsyncMock(
                return_value=fresh
            )

            result = await _run(indexer)

        assert result["status"] == "skipped"
        assert result["reason"] == "up_to_date"
        assert embeddings.calls == []
        assert indexer.order == []

    async def test_the_claim_is_taken_before_any_embedding(
        self, indexer: Any, embeddings: _ScriptedEmbeddings
    ) -> None:
        """Claiming after embedding would still bill four workers for the work.

        Args:
            indexer: Indexer under test.
            embeddings: Scripted embedding client.
        """
        with patch.object(indexer, "_resolve_knowledge_dir", return_value=indexer.knowledge_dir):
            await _run(indexer)

        indexer.service.space_repo.claim_system_space_for_reindex.assert_awaited_once_with(
            "space-uuid"
        )
        assert embeddings.calls, "the winner must still do the work"


# ==========================================================================
# Embed, then destroy
# ==========================================================================


@pytest.mark.unit
class TestEmbedBeforeDestroy:
    """Nothing is deleted until every vector is in hand."""

    async def test_the_nominal_order_is_embed_delete_insert_update(
        self, indexer: Any, embeddings: _ScriptedEmbeddings
    ) -> None:
        """Embedding first is what makes a quota rejection free.

        Args:
            indexer: Indexer under test.
            embeddings: Scripted embedding client.
        """
        with patch.object(indexer, "_resolve_knowledge_dir", return_value=indexer.knowledge_dir):
            result = await _run(indexer)

        assert indexer.order == ["embed", "delete_chunks", "insert", "update_hash"]
        assert result["status"] == "success"
        # The count comes back from the repository, not from len(parsed): a
        # bulk insert that writes fewer rows than it was given must be visible.
        assert result["chunks_created"] == 3
        assert result["content_hash"] == indexer.compute_content_hash(indexer.knowledge_dir)

    async def test_a_permanent_embedding_failure_deletes_nothing(
        self, indexer: Any, embeddings: _ScriptedEmbeddings, no_sleep: list[float]
    ) -> None:
        """The previous corpus keeps serving when embedding cannot be done.

        This is the property the production incident lacked in spirit: 69 startup
        indexations failed on a 429 over 14 days, and the only reason the corpus
        survived was a rollback — now it is never touched at all.

        Args:
            indexer: Indexer under test.
            embeddings: Scripted embedding client.
            no_sleep: Recorded backoff delays.
        """
        embeddings._outcomes = [_wrapped(400)]

        with patch.object(indexer, "_resolve_knowledge_dir", return_value=indexer.knowledge_dir):
            with pytest.raises(RuntimeError):
                await _run(indexer)

        assert indexer.order == ["embed"]
        indexer.chunk_repo.delete_by_space.assert_not_awaited()
        indexer.service.update_system_space_hash.assert_not_awaited()

    async def test_vectors_are_paired_with_their_chunks(
        self, indexer: Any, embeddings: _ScriptedEmbeddings
    ) -> None:
        """One vector per chunk, or ``zip(strict=True)`` must fail loudly.

        Args:
            indexer: Indexer under test.
            embeddings: Scripted embedding client.
        """
        with patch.object(indexer, "_resolve_knowledge_dir", return_value=indexer.knowledge_dir):
            await _run(indexer)

        stored = indexer.chunk_repo.bulk_create_chunks.await_args.args[0]
        assert len(stored) == 3
        assert [chunk.chunk_index for chunk in stored] == [0, 1, 2]
        assert all(chunk.embedding == [0.1, 0.2] for chunk in stored)


# ==========================================================================
# Bounded retry
# ==========================================================================


@pytest.mark.unit
class TestBoundedRetry:
    """Transient failures are retried; permanent ones are not; both are bounded."""

    async def test_a_429_is_retried_and_then_succeeds(
        self,
        indexer: Any,
        embeddings: _ScriptedEmbeddings,
        no_sleep: list[float],
    ) -> None:
        """One transient rejection must not cost a whole staleness cycle.

        Args:
            indexer: Indexer under test.
            embeddings: Scripted embedding client.
            no_sleep: Recorded backoff delays.
        """
        embeddings._outcomes = [_wrapped(429)]

        with patch.object(indexer, "_resolve_knowledge_dir", return_value=indexer.knowledge_dir):
            result = await _run(indexer)

        assert result["status"] == "success"
        assert len(embeddings.calls) == 2
        assert no_sleep == [2.0]

    async def test_a_permanent_status_is_not_retried(
        self,
        indexer: Any,
        embeddings: _ScriptedEmbeddings,
        no_sleep: list[float],
    ) -> None:
        """A 400 will fail identically on every attempt — do not wait for it.

        Args:
            indexer: Indexer under test.
            embeddings: Scripted embedding client.
            no_sleep: Recorded backoff delays.
        """
        embeddings._outcomes = [_wrapped(400)]

        with patch.object(indexer, "_resolve_knowledge_dir", return_value=indexer.knowledge_dir):
            with pytest.raises(RuntimeError):
                await _run(indexer)

        assert len(embeddings.calls) == 1
        assert no_sleep == []

    async def test_attempts_are_capped_and_the_original_error_survives(
        self,
        indexer: Any,
        embeddings: _ScriptedEmbeddings,
        no_sleep: list[float],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Wrapping the failure would erase the status code that diagnoses it.

        Args:
            indexer: Indexer under test.
            embeddings: Scripted embedding client.
            no_sleep: Recorded backoff delays.
            monkeypatch: pytest monkeypatch fixture.
        """
        monkeypatch.setattr(
            system_indexer_module.settings,
            "rag_spaces_system_index_embed_max_attempts",
            2,
            raising=False,
        )
        embeddings._outcomes = [_wrapped(429), _wrapped(429), _wrapped(429)]

        with patch.object(indexer, "_resolve_knowledge_dir", return_value=indexer.knowledge_dir):
            with pytest.raises(RuntimeError) as caught:
                await _run(indexer)

        assert len(embeddings.calls) == 2
        assert len(no_sleep) == 1
        assert _retry_reason(caught.value) == "http_429"

    async def test_a_zero_budget_disables_waiting(
        self,
        indexer: Any,
        embeddings: _ScriptedEmbeddings,
        no_sleep: list[float],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The time budget bounds how long the claim on the row is held.

        Args:
            indexer: Indexer under test.
            embeddings: Scripted embedding client.
            no_sleep: Recorded backoff delays.
            monkeypatch: pytest monkeypatch fixture.
        """
        monkeypatch.setattr(
            system_indexer_module.settings,
            "rag_spaces_system_index_embed_retry_budget_seconds",
            0.0,
            raising=False,
        )
        embeddings._outcomes = [_wrapped(429)]

        with patch.object(indexer, "_resolve_knowledge_dir", return_value=indexer.knowledge_dir):
            with pytest.raises(RuntimeError):
                await _run(indexer)

        assert len(embeddings.calls) == 1
        assert no_sleep == []

    async def test_the_delay_never_exceeds_the_remaining_budget(
        self,
        indexer: Any,
        embeddings: _ScriptedEmbeddings,
        no_sleep: list[float],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A backoff longer than the budget would silently overrun it.

        Args:
            indexer: Indexer under test.
            embeddings: Scripted embedding client.
            no_sleep: Recorded backoff delays.
            monkeypatch: pytest monkeypatch fixture.
        """
        monkeypatch.setattr(
            system_indexer_module.settings,
            "rag_spaces_system_index_embed_retry_budget_seconds",
            0.5,
            raising=False,
        )
        embeddings._outcomes = [_wrapped(503)]

        with patch.object(indexer, "_resolve_knowledge_dir", return_value=indexer.knowledge_dir):
            result = await _run(indexer)

        assert result["status"] == "success"
        assert no_sleep and no_sleep[0] <= 0.5


# ==========================================================================
# Self-repair of a diverged corpus
# ==========================================================================


@pytest.mark.unit
class TestCorpusIntegrity:
    """A matching hash over a wrong corpus must trigger the repair, not a skip."""

    @staticmethod
    def _make_current(indexer: Any) -> None:
        """Point the space's hash at the files on disk.

        Args:
            indexer: Indexer under test.
        """
        current = indexer.compute_content_hash(indexer.knowledge_dir)
        indexer.service.space_repo.get_system_space_by_name.return_value.content_hash = current

    async def test_an_intact_corpus_with_a_matching_hash_is_skipped(
        self, indexer: Any, embeddings: _ScriptedEmbeddings
    ) -> None:
        """The common boot: nothing changed, nothing to do, nothing spent.

        Args:
            indexer: Indexer under test.
            embeddings: Scripted embedding client.
        """
        self._make_current(indexer)

        with patch.object(indexer, "_resolve_knowledge_dir", return_value=indexer.knowledge_dir):
            result = await _run(indexer)

        assert result["status"] == "skipped"
        assert result["reason"] == "up_to_date"
        assert embeddings.calls == []

    async def test_too_many_chunks_forces_a_reindex(
        self, indexer: Any, embeddings: _ScriptedEmbeddings
    ) -> None:
        """This is the production state: correct hash, triplicated corpus.

        A hash-only check skipped it on every boot, so the damage would have
        outlived the fix that prevented it.

        Args:
            indexer: Indexer under test.
            embeddings: Scripted embedding client.
        """
        self._make_current(indexer)
        indexer.chunk_repo.count_for_space = AsyncMock(return_value=3 * CHUNKS_IN_KNOWLEDGE_DIR)
        indexer.doc_repo.count_for_space = AsyncMock(return_value=3)

        with patch.object(indexer, "_resolve_knowledge_dir", return_value=indexer.knowledge_dir):
            result = await _run(indexer)

        assert result["status"] == "success"
        assert result["chunks_created"] == CHUNKS_IN_KNOWLEDGE_DIR
        assert indexer.order == ["embed", "delete_chunks", "insert", "update_hash"]

    async def test_too_few_chunks_forces_a_reindex(
        self, indexer: Any, embeddings: _ScriptedEmbeddings
    ) -> None:
        """A half-written corpus is as wrong as a duplicated one, and as invisible.

        Args:
            indexer: Indexer under test.
            embeddings: Scripted embedding client.
        """
        self._make_current(indexer)
        indexer.chunk_repo.count_for_space = AsyncMock(return_value=CHUNKS_IN_KNOWLEDGE_DIR - 1)

        with patch.object(indexer, "_resolve_knowledge_dir", return_value=indexer.knowledge_dir):
            result = await _run(indexer)

        assert result["status"] == "success"

    async def test_a_split_corpus_forces_a_reindex(
        self, indexer: Any, embeddings: _ScriptedEmbeddings
    ) -> None:
        """The right chunk count spread over two documents is still wrong.

        Args:
            indexer: Indexer under test.
            embeddings: Scripted embedding client.
        """
        self._make_current(indexer)
        indexer.doc_repo.count_for_space = AsyncMock(return_value=2)

        with patch.object(indexer, "_resolve_knowledge_dir", return_value=indexer.knowledge_dir):
            result = await _run(indexer)

        assert result["status"] == "success"

    async def test_divergence_is_reported_exactly_once(
        self, indexer: Any, embeddings: _ScriptedEmbeddings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Silent self-repair would hide a recurring cause — and so would noise.

        The corpus is assessed twice per indexation (before the claim and under
        it). Reporting from inside that predicate filed the same divergence up to
        five times across four workers for one event, which is the very habit the
        misfiled ``database_session_error`` taught us to avoid.

        Args:
            indexer: Indexer under test.
            embeddings: Scripted embedding client.
            monkeypatch: pytest monkeypatch fixture.
        """
        warnings: list[tuple[str, dict[str, Any]]] = []
        monkeypatch.setattr(
            system_indexer_module.logger,
            "warning",
            lambda event, **kwargs: warnings.append((event, kwargs)),
        )
        self._make_current(indexer)
        indexer.chunk_repo.count_for_space = AsyncMock(return_value=807)

        with patch.object(indexer, "_resolve_knowledge_dir", return_value=indexer.knowledge_dir):
            await _run(indexer)

        diverged = [
            payload for event, payload in warnings if event == "system_indexer_corpus_diverged"
        ]
        assert len(diverged) == 1, f"expected exactly one report, got {[e for e, _ in warnings]}"
        assert diverged[0]["stored_chunks"] == 807
        assert diverged[0]["expected_chunks"] == CHUNKS_IN_KNOWLEDGE_DIR
        assert diverged[0]["stored_documents"] == 1


# ==========================================================================
# First boot: everyone tries to create the space
# ==========================================================================


@pytest.mark.unit
class TestConcurrentSpaceCreation:
    """A benign creation race must not read as a failure."""

    async def test_a_duplicate_name_adopts_the_winner_row(
        self, indexer: Any, embeddings: _ScriptedEmbeddings
    ) -> None:
        """On a fresh database every worker tries to create the space.

        The partial unique index lets one through; the others must adopt its row
        instead of logging a failure for the whole indexation.

        Args:
            indexer: Indexer under test.
            embeddings: Scripted embedding client.
        """
        winner_row = MagicMock()
        winner_row.id = "winner-space"
        winner_row.content_hash = "stale-hash"
        lookups = [None, winner_row]
        indexer.service.space_repo.get_system_space_by_name = AsyncMock(
            side_effect=lambda _name: lookups.pop(0)
        )
        indexer.service.create_system_space = AsyncMock(
            side_effect=BaseAPIException(
                status_code=409,
                detail="A system space named 'lia-faq' already exists",
                log_event="rag_system_space_duplicate_name",
            )
        )
        indexer.service.space_repo.claim_system_space_for_reindex = AsyncMock(
            return_value=winner_row
        )

        with patch.object(indexer, "_resolve_knowledge_dir", return_value=indexer.knowledge_dir):
            result = await _run(indexer)

        assert result["status"] == "success"
        assert result["space_id"] == "winner-space"

    async def test_a_real_creation_failure_still_surfaces(
        self, indexer: Any, embeddings: _ScriptedEmbeddings
    ) -> None:
        """Absence of the row after the error means the failure was genuine.

        Adopting on the status code alone would swallow a broken schema, a
        permission problem, or an exhausted connection pool.

        Args:
            indexer: Indexer under test.
            embeddings: Scripted embedding client.
        """
        indexer.service.space_repo.get_system_space_by_name = AsyncMock(return_value=None)
        indexer.service.create_system_space = AsyncMock(
            side_effect=BaseAPIException(
                status_code=500,
                detail="boom",
                log_event="rag_system_space_creation_failed",
            )
        )

        with patch.object(indexer, "_resolve_knowledge_dir", return_value=indexer.knowledge_dir):
            with pytest.raises(BaseAPIException):
                await _run(indexer)

        assert embeddings.calls == []
        assert indexer.order == []


# ==========================================================================
# Classification
# ==========================================================================


@pytest.mark.unit
class TestRetryReason:
    """What counts as transient is decided on structure, never on wording."""

    @pytest.mark.parametrize("code", [408, 429, 500, 502, 503, 504])
    def test_transient_statuses_are_retryable(self, code: int) -> None:
        """The documented retryable set.

        Args:
            code: HTTP status under test.
        """
        assert _retry_reason(_wrapped(code)) == f"http_{code}"

    @pytest.mark.parametrize("code", [400, 401, 403, 404, 409, 422])
    def test_client_errors_are_permanent(self, code: int) -> None:
        """Retrying a malformed or unauthorised request only wastes the budget.

        Args:
            code: HTTP status under test.
        """
        assert _retry_reason(_wrapped(code)) is None

    def test_the_cause_chain_is_walked(self) -> None:
        """langchain wraps, and something may wrap langchain."""
        inner = _FakeApiError(429)
        middle = RuntimeError("provider call failed")
        middle.__cause__ = inner
        outer = ValueError("indexation failed")
        outer.__cause__ = middle

        assert _retry_reason(outer) == "http_429"

    @pytest.mark.parametrize(
        "exc",
        [
            pytest.param(TimeoutError("read timed out"), id="timeout"),
            pytest.param(ConnectionResetError("peer reset"), id="connection_reset"),
        ],
    )
    def test_transport_failures_are_retryable(self, exc: Exception) -> None:
        """On a Raspberry Pi over WiFi these are ordinary, not exceptional.

        Args:
            exc: Transport-level exception.
        """
        assert _retry_reason(exc) is not None

    def test_an_unrelated_error_is_permanent(self) -> None:
        """No status, no transport failure, no retry."""
        assert _retry_reason(ValueError("bad chunk")) is None

    def test_a_non_integer_code_attribute_is_ignored(self) -> None:
        """``code`` is not a reserved word — any exception may carry one."""
        exc = ValueError("nope")
        exc.code = "429"  # type: ignore[attr-defined]

        assert _retry_reason(exc) is None

    def test_a_cyclic_cause_chain_terminates(self) -> None:
        """A self-referential chain must not hang the boot."""
        first = ValueError("a")
        second = ValueError("b")
        first.__cause__ = second
        second.__cause__ = first

        assert _retry_reason(first) is None


# ==========================================================================
# The admin endpoint must not report a declined claim as success
# ==========================================================================


@pytest.mark.unit
class TestAdminReindexEndpoint:
    """A reindex that did not happen must not answer 200."""

    @staticmethod
    async def _reindex(result: dict[str, Any]) -> Any:
        """Call the endpoint with a stubbed indexer.

        Args:
            result: What ``index_faq_space`` returns.

        Returns:
            The endpoint's response.
        """
        from src.domains.rag_spaces import router as router_module

        with patch.object(SystemSpaceIndexer, "index_faq_space", AsyncMock(return_value=result)):
            return await router_module.reindex_system_space(
                space_name="lia-faq", user=MagicMock(), db=AsyncMock()
            )

    async def test_a_declined_claim_is_a_conflict(self) -> None:
        """Answering "already up to date" would be a lie the admin acts on.

        The admin UI ignores ``message`` and toasts success from
        ``chunks_created``, so a 200 with 0 chunks reads as "reindexed" for an
        indexation that never ran.
        """
        with pytest.raises(BaseAPIException) as caught:
            await self._reindex(
                {
                    "status": "skipped",
                    "reason": "claimed_by_another_worker",
                    "chunks_created": 0,
                    "content_hash": "h",
                    "space_id": "s",
                }
            )

        assert caught.value.status_code == 409
        assert "already in progress" in caught.value.detail

    async def test_a_genuine_no_op_still_answers_up_to_date(self) -> None:
        """Nothing to do is a success, and must stay one."""
        response = await self._reindex(
            {
                "status": "skipped",
                "reason": "up_to_date",
                "chunks_created": 0,
                "content_hash": "h",
                "space_id": "s",
            }
        )

        assert response.status == "skipped"
        assert response.chunks_created == 0
        assert "already up to date" in response.message

    async def test_a_successful_reindex_reports_its_count(self) -> None:
        """The nominal path is unchanged."""
        response = await self._reindex(
            {
                "status": "success",
                "chunks_created": 269,
                "content_hash": "h",
                "space_id": "s",
            }
        )

        assert response.status == "success"
        assert response.chunks_created == 269
        assert "reindexed successfully" in response.message

    async def test_an_error_is_a_500(self) -> None:
        """A genuine failure must not be mistaken for a conflict."""
        with pytest.raises(BaseAPIException) as caught:
            await self._reindex(
                {
                    "status": "error",
                    "error": "Knowledge directory not found",
                    "chunks_created": 0,
                    "content_hash": "",
                }
            )

        assert caught.value.status_code == 500
