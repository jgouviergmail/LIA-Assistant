"""Contract of the RAG hybrid fusion (ADR-242).

Until 2026-08-22 the fusion was ``alpha*semantic + (1-alpha)*bm25_normalised``
with ``min_score`` applied to the *result*. Two properties of that formula made
it destroy retrieval outside English:

- BM25 was normalised by the **corpus-wide maximum**, so the least-bad lexical
  match always scored 1.0 — pure noise on a query whose language does not match
  the documents' — and injected up to ``1-alpha`` onto an arbitrary chunk.
- ``min_score`` was compared against a score already shrunk by ``alpha``, so a
  chunk with no lexical overlap needed ``min_score/alpha`` in cosine terms:
  0.786 for a threshold documented as 0.55, well above the median of a correct
  answer.

Reproduced on the live production database (2026-08-22): the query
« C'est quoi un espace de connaissances ? » dropped its exact answer
(semantic 0.683, bm25 0) and returned one unrelated chunk instead; « Est-ce que
mes données sont chiffrées ? » returned nothing at all.

The fusion now gates on the **semantic** score — restoring the documented
meaning of ``min_score`` — and uses BM25 only as a bounded re-ordering bonus.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from src.domains.rag_spaces.retrieval import retrieve_rag_context
from tests.unit.domains.rag_spaces.retrieval_harness import (
    FakeChunk,
    retrieval_settings,
    retrieval_stack,
)

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]

GATE = 0.62


async def _retrieve(chunks, *, min_score=GATE, bonus=0.05, limit=5, corpus_extra=None):
    """Run the public retrieval path over one corpus and return its chunks."""
    space_id = uuid4()
    with (
        retrieval_settings(min_score=min_score, bm25_bonus_weight=bonus, limit=limit),
        retrieval_stack(chunks, space_id=space_id, corpus_extra=corpus_extra),
    ):
        result = await retrieve_rag_context(user_id=uuid4(), query="q", db=object())
    return result.chunks if result else []


class TestSemanticGate:
    """``min_score`` applies to the semantic score, nothing else."""

    async def test_relevant_chunk_without_lexical_overlap_is_kept(self) -> None:
        """The live production defect, pinned.

        A cross-language query has BM25 0 on its own answer. Under the old
        fusion 0.7*0.683 = 0.478 < 0.55 and the answer was dropped.
        """
        chunks = await _retrieve([FakeChunk("Knowledge Spaces are…", semantic=0.683, bm25=0.0)])

        assert [c.content for c in chunks] == ["Knowledge Spaces are…"]

    async def test_every_relevant_chunk_survives_a_zero_bm25_query(self) -> None:
        """« Est-ce que mes données sont chiffrées ? » returned 0 chunks in prod."""
        corpus = [
            FakeChunk("Your conversations are private.", semantic=0.676),
            FakeChunk("How your data is protected.", semantic=0.668),
            FakeChunk("Export all your data (GDPR).", semantic=0.630),
        ]

        chunks = await _retrieve(corpus)

        assert len(chunks) == 3

    async def test_chunk_below_the_gate_is_dropped(self) -> None:
        chunks = await _retrieve([FakeChunk("Off topic.", semantic=0.58, bm25=0.0)])

        assert chunks == []

    async def test_strong_lexical_match_cannot_rescue_a_chunk_below_the_gate(self) -> None:
        """The bonus re-orders what passed; it never re-opens the gate.

        This is what stops an off-topic turn from pulling documents in: on such
        a turn the corpus-wide BM25 maximum is itself noise, so admitting a
        chunk on lexical evidence alone re-creates the defect being fixed
        (measured: 1.05 -> 2.75 chunks injected per irrelevant turn).
        """
        chunks = await _retrieve(
            [
                FakeChunk("Lexically similar, semantically wrong.", semantic=0.55, bm25=99.0),
                FakeChunk("Actually relevant.", semantic=0.70, bm25=0.0),
            ]
        )

        assert [c.content for c in chunks] == ["Actually relevant."]

    async def test_gate_is_inclusive_at_the_threshold(self) -> None:
        """A chunk exactly at ``min_score`` is kept — the setting is a floor."""
        chunks = await _retrieve([FakeChunk("Exactly at the gate.", semantic=GATE)])

        assert len(chunks) == 1


class TestBm25Bonus:
    """BM25 re-orders the chunks that passed the gate, within a bounded budget."""

    async def test_bonus_reorders_two_chunks_that_both_passed(self) -> None:
        chunks = await _retrieve(
            [
                FakeChunk("Semantically first.", semantic=0.700, bm25=0.0),
                FakeChunk("Lexically supported.", semantic=0.690, bm25=10.0),
            ]
        )

        assert [c.content for c in chunks] == ["Lexically supported.", "Semantically first."]
        assert len(chunks) == 2, "re-ordering must not drop the runner-up"

    async def test_bonus_cannot_overturn_a_large_semantic_gap(self) -> None:
        """A 0.05 budget must not let a weak match outrank a clearly better one."""
        chunks = await _retrieve(
            [
                FakeChunk("Clearly the best answer.", semantic=0.80, bm25=0.0),
                FakeChunk("Shares a stray token.", semantic=0.65, bm25=99.0),
            ]
        )

        assert chunks[0].content == "Clearly the best answer."

    async def test_score_is_the_semantic_score_plus_at_most_the_bonus(self) -> None:
        chunks = await _retrieve([FakeChunk("Top lexical match too.", semantic=0.70, bm25=5.0)])

        assert chunks[0].score == pytest.approx(0.75, abs=1e-4)

    async def test_score_equals_the_semantic_score_when_bm25_is_zero(self) -> None:
        """No lexical evidence must cost nothing — that was the whole defect."""
        chunks = await _retrieve([FakeChunk("No shared token.", semantic=0.683, bm25=0.0)])

        assert chunks[0].score == pytest.approx(0.683, abs=1e-4)

    async def test_a_zero_bonus_weight_disables_lexical_reordering(self) -> None:
        chunks = await _retrieve(
            [
                FakeChunk("Semantically first.", semantic=0.700, bm25=0.0),
                FakeChunk("Lexically supported.", semantic=0.690, bm25=99.0),
            ],
            bonus=0.0,
        )

        assert [c.content for c in chunks] == ["Semantically first.", "Lexically supported."]

    async def test_bonus_is_normalised_over_the_whole_corpus_not_the_candidates(self) -> None:
        """A candidate's bonus is relative to the best lexical match in the SPACE.

        Normalising over the candidates alone would hand 1.0 to the best of a
        weak field, which is the same lie one scope down.
        """
        strong_elsewhere = (uuid4(), "A much stronger lexical match lives here.")
        with (
            retrieval_settings(min_score=GATE, bm25_bonus_weight=0.05),
            retrieval_stack(
                [FakeChunk("Candidate.", semantic=0.70, bm25=2.0)],
                space_id=uuid4(),
                corpus_extra=[strong_elsewhere],
            ) as mocks,
        ):
            mocks["bm25"].get_scores.return_value = [2.0, 10.0]
            result = await retrieve_rag_context(user_id=uuid4(), query="q", db=object())

        # 2.0 / 10.0 = 0.2 of the budget, not the whole of it.
        assert result is not None
        assert result.chunks[0].score == pytest.approx(0.70 + 0.05 * 0.2, abs=1e-4)


class TestPublishedScoreStaysInRange:
    """The score handed to the UI and to the LLM stays in its documented [0, 1].

    The fused value is ``semantic + beta * bm25``, so a chunk that is both a
    near-perfect semantic match and the corpus's best lexical match exceeds 1.
    Every consumer documents ``[0, 1]``: the repository docstring, the
    ``search_user_documents`` tool ("relevance score"), and the debug ScoreBar,
    which silently clamps. Publishing 1.03 as a relevance score would be a claim
    nobody can read correctly — the ordering keeps the exact value, the
    published number is bounded.
    """

    async def test_a_score_that_would_exceed_one_is_published_as_one(self) -> None:
        chunks = await _retrieve([FakeChunk("Perfect match.", semantic=0.99, bm25=10.0)])

        assert chunks[0].score == 1.0

    async def test_ordering_still_uses_the_exact_fused_value(self) -> None:
        """Two chunks both clamped to 1.0 must still come out in the right order."""
        chunks = await _retrieve(
            [
                FakeChunk("Slightly better overall.", semantic=0.99, bm25=10.0),
                FakeChunk("Slightly worse overall.", semantic=0.985, bm25=10.0),
            ]
        )

        assert [c.content for c in chunks] == [
            "Slightly better overall.",
            "Slightly worse overall.",
        ]
        assert [c.score for c in chunks] == [1.0, 1.0]

    async def test_scores_below_the_bound_are_untouched(self) -> None:
        chunks = await _retrieve([FakeChunk("Ordinary match.", semantic=0.70, bm25=5.0)])

        assert chunks[0].score == pytest.approx(0.75, abs=1e-4)


class TestFusionResilience:
    """Degradation paths keep the semantic signal intact."""

    async def test_bm25_failure_leaves_the_semantic_ranking_untouched(self) -> None:
        space_id = uuid4()
        corpus = [
            FakeChunk("First.", semantic=0.72, bm25=0.0),
            FakeChunk("Second.", semantic=0.68, bm25=0.0),
        ]
        with (
            retrieval_settings(min_score=GATE, bm25_bonus_weight=0.05),
            retrieval_stack(corpus, space_id=space_id) as mocks,
        ):
            mocks["chunk_repo"].get_corpus_for_spaces.side_effect = RuntimeError("bm25 down")
            result = await retrieve_rag_context(user_id=uuid4(), query="q", db=object())

        assert result is not None
        assert [c.content for c in result.chunks] == ["First.", "Second."]
        assert result.chunks[0].score == pytest.approx(0.72, abs=1e-4)

    async def test_an_all_zero_bm25_corpus_does_not_divide_by_zero(self) -> None:
        chunks = await _retrieve(
            [
                FakeChunk("First.", semantic=0.72, bm25=0.0),
                FakeChunk("Second.", semantic=0.68, bm25=0.0),
            ]
        )

        assert [c.score for c in chunks] == pytest.approx([0.72, 0.68], abs=1e-4)

    async def test_results_are_capped_at_the_configured_limit(self) -> None:
        corpus = [FakeChunk(f"Chunk {i}.", semantic=0.90 - i / 100) for i in range(9)]

        chunks = await _retrieve(corpus, limit=5)

        assert len(chunks) == 5
        assert [c.content for c in chunks] == [f"Chunk {i}." for i in range(5)]

    async def test_results_stay_sorted_by_descending_score(self) -> None:
        corpus = [
            FakeChunk("Low semantic, high lexical.", semantic=0.64, bm25=10.0),
            FakeChunk("High semantic.", semantic=0.81, bm25=0.0),
            FakeChunk("Middle.", semantic=0.70, bm25=5.0),
        ]

        chunks = await _retrieve(corpus)

        scores = [c.score for c in chunks]
        assert scores == sorted(scores, reverse=True)
