"""Concurrent startup indexations must leave exactly one corpus behind.

The production defect this pins could only ever be reproduced against a real
PostgreSQL: four uvicorn workers ran the startup FAQ indexation at the same time,
the staleness check was a read with no claim, so all four passed it and all four
ran their own delete-then-insert. Because each ``DELETE`` only removes what was
visible when it started, rows inserted by a peer survived — measured on
2026-07-27 in production: **807 chunks for 269 distinct contents**, three copies
of every answer, and three ``lia-faq.md`` documents. Retrieval sorts by score and
truncates, and exact duplicates score identically, so the top five carried two
distinct answers instead of five.

The claim (``FOR UPDATE SKIP LOCKED`` on the space row) is what closes this. The
last test in this module removes it and shows the duplication coming straight
back, so the guard is known to bite rather than merely known to pass.

These tests use their own sessions rather than the savepoint-isolated ``db``
fixture: two transactions on one connection cannot contend for a row lock, which
is the entire subject. They clean up after themselves.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import delete, distinct, func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.constants import RAG_SPACES_SYSTEM_FAQ_NAME_DEFAULT
from src.domains.rag_spaces import system_indexer as system_indexer_module
from src.domains.rag_spaces.models import RAGChunk, RAGDocument, RAGSpace
from src.domains.rag_spaces.repository import RAGSpaceRepository
from src.domains.rag_spaces.system_indexer import SystemSpaceIndexer

pytestmark = pytest.mark.integration

CHUNK_COUNT = 3
STALE_HASH = "stale-hash-forcing-a-reindex"


@pytest.fixture
def knowledge_dir(tmp_path: Path) -> Path:
    """A knowledge directory holding exactly ``CHUNK_COUNT`` Q/A chunks.

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


async def _embedding_dimensions(engine: AsyncEngine) -> int:
    """Read the vector width the live schema declares.

    Hard-coding 1536 would turn a future dimension change into a puzzling
    insert error rather than a passing test.

    Args:
        engine: Engine bound to the test database.

    Returns:
        Declared dimensionality of ``rag_chunks.embedding``.
    """
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT atttypmod FROM pg_attribute "
                "WHERE attrelid = 'rag_chunks'::regclass AND attname = 'embedding'"
            )
        )
        return int(result.scalar_one())


def _session(engine: AsyncEngine) -> AsyncSession:
    """A session configured exactly like the application's.

    ``AsyncSessionLocal`` sets ``expire_on_commit=False`` and ``autoflush=False``;
    SQLAlchemy defaults to True for both. The difference is not cosmetic here:
    ``expire_on_commit=False`` is *why* the claim needs ``populate_existing`` (no
    commit elsewhere invalidates the instance we already hold), and autoflush
    silently writes pending mutations before a SELECT — a test on default settings
    can therefore pass on behaviour production never exhibits, or fail on
    behaviour it never would.

    Args:
        engine: Engine bound to the test database.

    Returns:
        A session with the production configuration.
    """
    return AsyncSession(engine, expire_on_commit=False, autoflush=False)


@pytest_asyncio.fixture
async def stale_system_space(async_engine: AsyncEngine) -> Any:
    """A committed system FAQ space whose hash does not match the files.

    Any pre-existing space of the same name is removed first: the indexer looks
    the space up by name, so a leftover from another module would be indexed
    instead of ours.

    Args:
        async_engine: Engine bound to the test database.

    Yields:
        The identifier of the space under test.
    """
    async with _session(async_engine) as session:
        await session.execute(
            delete(RAGSpace).where(
                RAGSpace.is_system.is_(True),
                RAGSpace.name == RAG_SPACES_SYSTEM_FAQ_NAME_DEFAULT,
            )
        )
        space = RAGSpace(
            name=RAG_SPACES_SYSTEM_FAQ_NAME_DEFAULT,
            is_system=True,
            is_active=True,
            content_hash=STALE_HASH,
        )
        session.add(space)
        await session.commit()
        space_id = space.id

    yield space_id

    async with _session(async_engine) as session:
        await session.execute(delete(RAGChunk).where(RAGChunk.space_id == space_id))
        await session.execute(delete(RAGDocument).where(RAGDocument.space_id == space_id))
        await session.execute(delete(RAGSpace).where(RAGSpace.id == space_id))
        await session.commit()


@pytest_asyncio.fixture
async def indexing_environment(
    async_engine: AsyncEngine,
    knowledge_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stub the embedding provider and pin the knowledge directory.

    Args:
        async_engine: Engine bound to the test database.
        knowledge_dir: Directory the indexer must read.
        monkeypatch: pytest monkeypatch fixture.
    """
    dimensions = await _embedding_dimensions(async_engine)

    class _StubEmbeddings:
        """Deterministic embeddings of the right width."""

        async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
            """Return one zero vector per text.

            Args:
                texts: Batch to embed.

            Returns:
                One vector per text.
            """
            return [[0.0] * dimensions for _ in texts]

    monkeypatch.setattr(system_indexer_module, "get_rag_embeddings", lambda: _StubEmbeddings())
    monkeypatch.setattr(
        SystemSpaceIndexer, "_resolve_knowledge_dir", staticmethod(lambda: knowledge_dir)
    )


async def _corpus_state(engine: AsyncEngine, space_id: Any) -> tuple[int, int, int]:
    """Count what the space actually holds.

    Args:
        engine: Engine bound to the test database.
        space_id: Space to inspect.

    Returns:
        ``(chunks, distinct_contents, documents)``.
    """
    async with _session(engine) as session:
        chunks = await session.scalar(
            select(func.count()).select_from(RAGChunk).where(RAGChunk.space_id == space_id)
        )
        contents = await session.scalar(
            select(func.count(distinct(RAGChunk.content))).where(RAGChunk.space_id == space_id)
        )
        documents = await session.scalar(
            select(func.count()).select_from(RAGDocument).where(RAGDocument.space_id == space_id)
        )
    return int(chunks or 0), int(contents or 0), int(documents or 0)


async def _index_once(engine: AsyncEngine) -> dict:
    """Run one indexation on its own session, as a worker would.

    Args:
        engine: Engine bound to the test database.

    Returns:
        The indexer's result dict.
    """
    async with _session(engine) as session:
        return await SystemSpaceIndexer(session).index_faq_space()


class TestTheClaimItself:
    """``FOR UPDATE SKIP LOCKED`` on the space row, in isolation."""

    async def test_a_second_transaction_is_declined_not_queued(
        self, async_engine: AsyncEngine, stale_system_space: Any
    ) -> None:
        """The loser must return immediately, not wait for the winner.

        Queuing would serialise four workers behind a ~20 s embedding call and
        add that delay to every boot.

        Args:
            async_engine: Engine bound to the test database.
            stale_system_space: Space under test.
        """
        async with _session(async_engine) as winner, _session(async_engine) as loser:
            claimed = await RAGSpaceRepository(winner).claim_system_space_for_reindex(
                stale_system_space
            )
            assert claimed is not None

            declined = await asyncio.wait_for(
                RAGSpaceRepository(loser).claim_system_space_for_reindex(stale_system_space),
                timeout=5,
            )

            assert declined is None
            await winner.rollback()

    async def test_the_claim_is_released_by_the_commit(
        self, async_engine: AsyncEngine, stale_system_space: Any
    ) -> None:
        """Once the winner commits, the row is claimable again.

        Args:
            async_engine: Engine bound to the test database.
            stale_system_space: Space under test.
        """
        async with _session(async_engine) as first:
            assert await RAGSpaceRepository(first).claim_system_space_for_reindex(
                stale_system_space
            )
            await first.commit()

        async with _session(async_engine) as second:
            assert await RAGSpaceRepository(second).claim_system_space_for_reindex(
                stale_system_space
            )
            await second.rollback()

    async def test_the_claim_reloads_the_row_it_locks(
        self, async_engine: AsyncEngine, stale_system_space: Any
    ) -> None:
        """A stale identity-mapped instance would defeat the whole mechanism.

        The exact production sequence: a worker reads the space for the staleness
        pre-check, the winner commits a new hash while that read is still in
        flight, and the worker then claims. Without ``populate_existing``
        SQLAlchemy returns the identity-mapped instance it already has, the
        worker sees the old hash, and re-indexes over fresh work.

        Args:
            async_engine: Engine bound to the test database.
            stale_system_space: Space under test.
        """
        async with _session(async_engine) as loser:
            repository = RAGSpaceRepository(loser)
            pre_check = await repository.get_by_id(stale_system_space)
            assert pre_check is not None
            assert pre_check.content_hash == STALE_HASH

            # The winner finishes and commits while the loser holds that read.
            async with _session(async_engine) as winner:
                winning_space = await RAGSpaceRepository(winner).get_by_id(stale_system_space)
                assert winning_space is not None
                winning_space.content_hash = "committed-by-the-winner"
                await winner.commit()

            claimed = await repository.claim_system_space_for_reindex(stale_system_space)

            assert claimed is not None
            assert claimed is pre_check, "same identity-mapped instance, by design"
            assert claimed.content_hash == "committed-by-the-winner"
            await loser.rollback()


class TestConcurrentIndexations:
    """End to end: many workers, one corpus."""

    async def test_two_workers_produce_exactly_one_corpus(
        self,
        async_engine: AsyncEngine,
        stale_system_space: Any,
        indexing_environment: None,
    ) -> None:
        """One indexes, the other declines, and no answer is stored twice.

        Args:
            async_engine: Engine bound to the test database.
            stale_system_space: Space under test.
            indexing_environment: Stubbed provider and pinned knowledge dir.
        """
        first, second = await asyncio.gather(_index_once(async_engine), _index_once(async_engine))

        statuses = sorted([first["status"], second["status"]])
        assert statuses == ["skipped", "success"]
        loser = first if first["status"] == "skipped" else second
        # Either the claim was declined, or the winner had already committed a
        # matching hash. Both are correct; duplicating the corpus is not.
        assert loser["reason"] in {"claimed_by_another_worker", "up_to_date"}

        chunks, contents, documents = await _corpus_state(async_engine, stale_system_space)
        assert (chunks, contents, documents) == (CHUNK_COUNT, CHUNK_COUNT, 1)

    async def test_four_workers_reproduce_the_production_fleet(
        self,
        async_engine: AsyncEngine,
        stale_system_space: Any,
        indexing_environment: None,
    ) -> None:
        """Four is the production worker count that produced 807 chunks.

        Args:
            async_engine: Engine bound to the test database.
            stale_system_space: Space under test.
            indexing_environment: Stubbed provider and pinned knowledge dir.
        """
        results = await asyncio.gather(*(_index_once(async_engine) for _ in range(4)))

        assert [r["status"] for r in results].count("success") == 1
        assert [r["status"] for r in results].count("skipped") == 3

        chunks, contents, documents = await _corpus_state(async_engine, stale_system_space)
        assert (chunks, contents, documents) == (CHUNK_COUNT, CHUNK_COUNT, 1)

    async def test_a_second_boot_with_unchanged_files_indexes_nothing(
        self,
        async_engine: AsyncEngine,
        stale_system_space: Any,
        indexing_environment: None,
    ) -> None:
        """Idempotence: the corpus must not be rebuilt on every restart.

        Args:
            async_engine: Engine bound to the test database.
            stale_system_space: Space under test.
            indexing_environment: Stubbed provider and pinned knowledge dir.
        """
        first = await _index_once(async_engine)
        assert first["status"] == "success"

        second = await _index_once(async_engine)

        assert second["status"] == "skipped"
        assert second["reason"] == "up_to_date"
        chunks, contents, documents = await _corpus_state(async_engine, stale_system_space)
        assert (chunks, contents, documents) == (CHUNK_COUNT, CHUNK_COUNT, 1)


class TestRepairOfADivergedCorpus:
    """The production state must heal itself, not be frozen by a matching hash."""

    async def test_a_duplicated_corpus_with_a_correct_hash_is_repaired(
        self,
        async_engine: AsyncEngine,
        stale_system_space: Any,
        knowledge_dir: Path,
        indexing_environment: None,
    ) -> None:
        """Reproduce production and prove the next boot fixes it.

        Production carried the *correct* content hash over 807 chunks and 3
        documents for 269 parsed entries. Checking the hash alone would have
        skipped that space on every boot from then on, so the corpus that four
        concurrent workers built would have kept serving triplicated answers long
        after the concurrency itself was fixed. Here the same shape is seeded at a
        smaller scale, and one boot restores the invariant.

        Args:
            async_engine: Engine bound to the test database.
            stale_system_space: Space under test.
            knowledge_dir: Directory the indexer reads.
            indexing_environment: Stubbed provider and pinned knowledge dir.
        """
        dimensions = await _embedding_dimensions(async_engine)

        async with _session(async_engine) as session:
            indexer = SystemSpaceIndexer(session)
            texts = indexer._chunk_texts(indexer._parse_all_markdown(knowledge_dir))
            assert len(texts) == CHUNK_COUNT

            # Two documents, each owning a full copy of the corpus.
            for _ in range(2):
                document = RAGDocument(
                    space_id=stale_system_space,
                    filename="lia-faq.md",
                    original_filename="lia-faq.md",
                    file_size=0,
                    content_type="text/markdown",
                    status="ready",
                    chunk_count=CHUNK_COUNT,
                )
                session.add(document)
                await session.flush()
                for index, content in enumerate(texts):
                    session.add(
                        RAGChunk(
                            document_id=document.id,
                            space_id=stale_system_space,
                            chunk_index=index,
                            content=content,
                            embedding=[0.0] * dimensions,
                            embedding_model="test-model",
                        )
                    )
            # The hash the files really produce: the trap is that it is correct.
            space = await session.get(RAGSpace, stale_system_space)
            assert space is not None
            space.content_hash = indexer.compute_content_hash(knowledge_dir)
            await session.commit()

        assert await _corpus_state(async_engine, stale_system_space) == (
            2 * CHUNK_COUNT,
            CHUNK_COUNT,
            2,
        ), "the duplicated state must be seeded before the repair is claimed"

        result = await _index_once(async_engine)

        assert result["status"] == "success", "a matching hash must not mask a broken corpus"
        assert await _corpus_state(async_engine, stale_system_space) == (
            CHUNK_COUNT,
            CHUNK_COUNT,
            1,
        )

    async def test_the_repair_does_not_fire_on_an_intact_corpus(
        self,
        async_engine: AsyncEngine,
        stale_system_space: Any,
        indexing_environment: None,
    ) -> None:
        """Re-embedding on every boot is the cost this check must not add.

        Args:
            async_engine: Engine bound to the test database.
            stale_system_space: Space under test.
            indexing_environment: Stubbed provider and pinned knowledge dir.
        """
        assert (await _index_once(async_engine))["status"] == "success"

        for _ in range(3):
            assert (await _index_once(async_engine))["status"] == "skipped"

        assert await _corpus_state(async_engine, stale_system_space) == (
            CHUNK_COUNT,
            CHUNK_COUNT,
            1,
        )


class TestFalsification:
    """Remove the claim and the production duplication must return."""

    async def test_without_the_claim_the_corpus_is_duplicated(
        self,
        async_engine: AsyncEngine,
        stale_system_space: Any,
        indexing_environment: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """This is the pre-fix code path, and it must fail the invariant.

        Replacing the claim with the plain read it used to be lets both workers
        through. Neither has old rows to contend over, so both insert their own
        corpus and both documents survive — exactly the shape production ended up
        in, at a smaller scale.

        Args:
            async_engine: Engine bound to the test database.
            stale_system_space: Space under test.
            indexing_environment: Stubbed provider and pinned knowledge dir.
            monkeypatch: pytest monkeypatch fixture.
        """

        async def _claim_without_locking(
            self: RAGSpaceRepository, space_id: Any
        ) -> RAGSpace | None:
            """The pre-fix behaviour: read, do not claim."""
            return await self.get_by_id(space_id)

        monkeypatch.setattr(
            RAGSpaceRepository, "claim_system_space_for_reindex", _claim_without_locking
        )

        results = await asyncio.gather(
            _index_once(async_engine), _index_once(async_engine), return_exceptions=True
        )
        successes = [r for r in results if isinstance(r, dict) and r["status"] == "success"]
        assert len(successes) == 2, f"expected both workers to index, got {results}"

        chunks, contents, documents = await _corpus_state(async_engine, stale_system_space)
        assert documents == 2
        assert chunks == 2 * CHUNK_COUNT
        assert contents == CHUNK_COUNT
