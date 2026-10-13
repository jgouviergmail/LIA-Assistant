"""Tool vectors: compact arrays, vectorised cosines and the per-server cache (ADR-283 amendment)."""

from __future__ import annotations

import sys

import numpy as np
import pytest

from src.domains.agents.services import tool_vectors
from src.domains.agents.services.tool_vectors import (
    ServerVectorCache,
    as_matrix,
    as_vector,
    compact_tool_vectors,
    cosine_rows,
    get_server_vector_cache,
    reset_server_vector_cache,
)
from src.infrastructure.llm.local_embeddings import cosine_similarity

pytestmark = pytest.mark.unit


class TestCompactForm:
    def test_a_vector_is_float32_and_one_dimensional(self) -> None:
        vector = as_vector([0.1, 0.2, 0.3])

        assert vector.dtype == np.float32
        assert vector.shape == (3,)

    def test_an_array_is_not_copied(self) -> None:
        original = np.asarray([1.0, 2.0], dtype=np.float32)

        assert as_vector(original) is original

    def test_a_nested_list_is_not_a_vector(self) -> None:
        with pytest.raises(ValueError):
            as_vector([[0.1, 0.2]])

    def test_a_matrix_stacks_rows_of_one_width(self) -> None:
        matrix = as_matrix([[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]])

        assert matrix.dtype == np.float32
        assert matrix.shape == (3, 2)

    def test_a_single_row_is_a_one_row_matrix(self) -> None:
        assert as_matrix([1.0, 2.0]).shape == (1, 2)

    def test_no_row_is_an_empty_matrix(self) -> None:
        assert as_matrix([]).shape == (0, 0)

    def test_ragged_rows_are_refused(self) -> None:
        with pytest.raises(ValueError):
            as_matrix([[1.0, 2.0], [1.0]])

    def test_the_compact_vector_costs_a_fraction_of_the_list(self) -> None:
        """The reason this module exists: 1,536 Python floats against 1,536 float32."""
        values = [float(i) / 1536 for i in range(1536)]
        as_list = sys.getsizeof(values) + sum(sys.getsizeof(v) for v in values)

        compact = as_vector(values)

        assert compact.nbytes * 6 < as_list


class TestCosineRows:
    def test_matches_the_scalar_cosine_row_by_row(self) -> None:
        rng = np.random.default_rng(7)
        query = rng.normal(size=64)
        rows = rng.normal(size=(5, 64))

        sims = cosine_rows(as_vector(query), as_matrix(rows))

        for i in range(5):
            assert sims[i] == pytest.approx(cosine_similarity(query, rows[i]), abs=1e-5)

    def test_a_zero_row_scores_zero_not_nan(self) -> None:
        sims = cosine_rows(as_vector([1.0, 0.0]), as_matrix([[0.0, 0.0], [1.0, 0.0]]))

        assert sims.tolist() == [0.0, 1.0]

    def test_a_zero_query_scores_every_row_zero(self) -> None:
        sims = cosine_rows(as_vector([0.0, 0.0]), as_matrix([[1.0, 0.0]]))

        assert sims.tolist() == [0.0]

    def test_another_width_scores_zero_for_every_row(self) -> None:
        sims = cosine_rows(as_vector([1.0, 0.0, 0.0]), as_matrix([[1.0, 0.0], [0.0, 1.0]]))

        assert sims.tolist() == [0.0, 0.0]

    def test_no_row_gives_no_score(self) -> None:
        assert cosine_rows(as_vector([1.0]), as_matrix([])).shape == (0,)


class TestScalarCosineAcceptsBothForms:
    def test_lists_and_arrays_agree(self) -> None:
        a = [0.1, 0.2, 0.3]
        b = [0.3, 0.2, 0.1]

        assert cosine_similarity(a, b) == pytest.approx(
            cosine_similarity(as_vector(a), as_vector(b)), abs=1e-6
        )

    def test_a_width_mismatch_is_zero(self) -> None:
        assert cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0]) == 0.0

    def test_a_zero_vector_is_zero(self) -> None:
        assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


class TestCompactToolVectors:
    def test_keeps_the_envelope_shape_with_arrays_inside(self) -> None:
        compact = compact_tool_vectors(
            {
                "search": {
                    "description": [0.1, 0.2],
                    "keywords": [[0.3, 0.4], [0.5, 0.6]],
                    "keyword_names": ["srv", "search"],
                }
            }
        )

        assert compact["search"]["description"].dtype == np.float32
        assert compact["search"]["keywords"].shape == (2, 2)
        assert compact["search"]["keyword_names"] == ["srv", "search"]

    def test_a_tool_without_keywords_has_no_keywords_key(self) -> None:
        compact = compact_tool_vectors({"t": {"description": [0.1], "keywords": []}})

        assert "keywords" not in compact["t"]
        assert compact["t"]["description"].shape == (1,)

    def test_an_unreadable_tool_is_left_out_and_counted(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        compact = compact_tool_vectors(
            {
                "good": {"description": [0.1, 0.2]},
                "ragged": {"keywords": [[0.1], [0.1, 0.2]]},
                "junk": 3,
            }
        )

        assert set(compact) == {"good"}

    def test_an_empty_envelope_is_empty(self) -> None:
        assert compact_tool_vectors({}) == {}


class TestServerVectorCache:
    def test_a_hit_returns_the_same_object(self) -> None:
        cache = ServerVectorCache(max_entries=4)
        vectors = {"t": {"description": as_vector([1.0])}}
        cache.put(("srv", "model:1536", "fp"), vectors)

        assert cache.get(("srv", "model:1536", "fp")) is vectors

    def test_a_miss_is_none(self) -> None:
        assert ServerVectorCache(max_entries=4).get(("srv", "m", "fp")) is None

    def test_a_new_fingerprint_is_another_entry(self) -> None:
        cache = ServerVectorCache(max_entries=4)
        cache.put(("srv", "m", "fp1"), {})
        cache.put(("srv", "m", "fp2"), {})

        assert len(cache) == 2

    def test_the_least_recently_used_leaves_past_the_bound(self) -> None:
        cache = ServerVectorCache(max_entries=2)
        cache.put(("a", "m", "fp"), {})
        cache.put(("b", "m", "fp"), {})
        cache.get(("a", "m", "fp"))  # a is now the most recently used
        cache.put(("c", "m", "fp"), {})

        assert cache.get(("b", "m", "fp")) is None
        assert cache.get(("a", "m", "fp")) is not None
        assert len(cache) == 2

    def test_the_bound_is_at_least_one(self) -> None:
        cache = ServerVectorCache(max_entries=0)
        cache.put(("a", "m", "fp"), {})
        cache.put(("b", "m", "fp"), {})

        assert len(cache) == 1

    def test_the_process_cache_reads_its_bound_from_settings(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.config import settings

        reset_server_vector_cache()
        monkeypatch.setattr(settings, "mcp_server_vector_cache_max", 3)
        try:
            cache = get_server_vector_cache()
            assert cache is get_server_vector_cache()
            assert cache._max_entries == 3
        finally:
            reset_server_vector_cache()

    def test_the_module_exports_what_the_selector_and_the_context_read(self) -> None:
        assert {"as_vector", "as_matrix", "cosine_rows", "compact_tool_vectors"} <= set(
            tool_vectors.__all__
        )
