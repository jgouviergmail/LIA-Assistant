"""BM25 index manager: one index per key, replaced when its corpus changes (ADR-283 amendment)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.infrastructure.store.bm25_index import BM25IndexManager

pytestmark = pytest.mark.unit


def _manager(max_users: int = 3) -> BM25IndexManager:
    return BM25IndexManager(SimpleNamespace(memory_bm25_cache_max_users=max_users))  # type: ignore[arg-type]


CORPUS = ["the quick brown fox", "jumps over the lazy dog", "a fox in the box"]
IDS = ["c1", "c2", "c3"]


class TestOneIndexPerKey:
    def test_the_same_corpus_is_served_from_the_cache(self) -> None:
        manager = _manager()
        first, _ = manager.get_or_build_index("u1:gen", CORPUS, IDS)
        second, ids = manager.get_or_build_index("u1:gen", list(CORPUS), list(IDS))

        assert second is first
        assert ids == IDS
        assert len(manager._local_cache) == 1

    def test_a_changed_corpus_replaces_the_index_instead_of_adding_one(self) -> None:
        manager = _manager()
        first, _ = manager.get_or_build_index("u1:gen", CORPUS, IDS)
        changed = [*CORPUS, "a new chunk about cats"]
        second, _ = manager.get_or_build_index("u1:gen", changed, [*IDS, "c4"])

        assert second is not first
        assert len(manager._local_cache) == 1, "the stale index must leave with its corpus"

    def test_an_edited_text_under_a_kept_id_is_a_changed_corpus(self) -> None:
        manager = _manager()
        first, _ = manager.get_or_build_index("u1:gen", CORPUS, IDS)
        edited = ["the quick brown cat", *CORPUS[1:]]
        second, _ = manager.get_or_build_index("u1:gen", edited, IDS)

        assert second is not first

    def test_the_same_corpus_in_another_order_is_the_same_corpus(self) -> None:
        manager = _manager()
        first, _ = manager.get_or_build_index("u1:gen", CORPUS, IDS)
        second, _ = manager.get_or_build_index(
            "u1:gen", list(reversed(CORPUS)), list(reversed(IDS))
        )

        assert second is first

    def test_scores_still_come_from_the_served_index(self) -> None:
        manager = _manager()
        bm25, ids = manager.get_or_build_index("u1:gen", CORPUS, IDS)
        from src.infrastructure.store.bm25_index import tokenize_text

        scores = bm25.get_scores(tokenize_text("fox"))

        assert len(scores) == len(ids)
        assert scores[0] > 0 and scores[2] > 0 and scores[1] == 0


class TestTheBound:
    def test_the_least_recently_used_key_leaves_past_the_bound(self) -> None:
        manager = _manager(max_users=2)
        manager.get_or_build_index("a", CORPUS, IDS)
        manager.get_or_build_index("b", CORPUS, IDS)
        manager.get_or_build_index("a", CORPUS, IDS)  # a is recent again
        manager.get_or_build_index("c", CORPUS, IDS)

        assert set(manager._local_cache) == {"bm25:a", "bm25:c"}

    def test_the_bound_is_at_least_one(self) -> None:
        manager = _manager(max_users=0)
        manager.get_or_build_index("a", CORPUS, IDS)
        manager.get_or_build_index("b", CORPUS, IDS)

        assert len(manager._local_cache) == 1


class TestInvalidation:
    def test_the_bare_key_and_every_scoped_key_of_a_user_are_removed(self) -> None:
        manager = _manager(max_users=10)
        manager.get_or_build_index("u1", CORPUS, IDS)
        manager.get_or_build_index("u1:gen1", CORPUS, IDS)
        manager.get_or_build_index("u10", CORPUS, IDS)

        manager.invalidate_user_cache("u1")

        assert set(manager._local_cache) == {"bm25:u10"}


class TestTheHash:
    def test_mismatched_ids_and_documents_are_refused(self) -> None:
        with pytest.raises(ValueError):
            BM25IndexManager._compute_hash(["a", "b"], ["x"])

    def test_the_hash_is_short_and_deterministic(self) -> None:
        assert BM25IndexManager._compute_hash(CORPUS, IDS) == BM25IndexManager._compute_hash(
            CORPUS, IDS
        )
        assert len(BM25IndexManager._compute_hash(CORPUS, IDS)) == 16
