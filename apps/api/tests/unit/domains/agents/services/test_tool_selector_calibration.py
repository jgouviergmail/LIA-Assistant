"""Unit tests for the pure scoring/calibration logic of the semantic tool selector.

``SemanticToolSelector`` decides which tools an agent is offered for a query.
The embedding machinery needs a model, but three pieces are pure and decide the
OUTCOME: the softmax calibration that turns raw cosine similarities into
comparable probabilities, the confidence banding on ``ToolMatch``, and the
content hash that gates the (paid) embedding refresh. A regression in the
calibration silently changes which tools clear the threshold; a regression in
the hash silently reuses a stale embedding cache or burns API calls every boot.
"""

from unittest.mock import MagicMock

import pytest

from src.domains.agents.services.tool_selector import (
    SemanticToolSelector,
    ToolMatch,
    ToolSelectionResult,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def selector() -> SemanticToolSelector:
    return SemanticToolSelector()


# ============================================================================
# SOFTMAX CALIBRATION
# ============================================================================


class TestSoftmaxCalibration:
    """Raw cosine similarities → a probability-like distribution."""

    def test_empty_scores_return_empty(self, selector: SemanticToolSelector) -> None:
        assert selector._apply_softmax_calibration({}) == {}

    def test_single_tool_gets_full_probability(self, selector: SemanticToolSelector) -> None:
        assert selector._apply_softmax_calibration({"only": 0.42}) == {"only": 1.0}

    def test_probabilities_sum_to_one(self, selector: SemanticToolSelector) -> None:
        result = selector._apply_softmax_calibration({"a": 0.70, "b": 0.68, "c": 0.65})
        assert sum(result.values()) == pytest.approx(1.0)

    def test_ranking_is_preserved(self, selector: SemanticToolSelector) -> None:
        """The highest raw similarity must remain the highest calibrated score."""
        result = selector._apply_softmax_calibration({"lo": 0.65, "hi": 0.72, "mid": 0.68})
        assert max(result, key=lambda k: result[k]) == "hi"
        assert min(result, key=lambda k: result[k]) == "lo"

    def test_identical_scores_yield_a_uniform_distribution(
        self, selector: SemanticToolSelector
    ) -> None:
        result = selector._apply_softmax_calibration({"a": 0.7, "b": 0.7, "c": 0.7})
        assert result == {
            "a": pytest.approx(1 / 3),
            "b": pytest.approx(1 / 3),
            "c": pytest.approx(1 / 3),
        }

    def test_lower_temperature_sharpens_the_distribution(
        self, selector: SemanticToolSelector
    ) -> None:
        scores = {"a": 0.70, "b": 0.66}
        sharp = selector._apply_softmax_calibration(scores, temperature=0.05)
        soft = selector._apply_softmax_calibration(scores, temperature=0.5)
        # A sharper temperature concentrates more mass on the top tool.
        assert sharp["a"] > soft["a"]

    def test_all_probabilities_are_in_range(self, selector: SemanticToolSelector) -> None:
        result = selector._apply_softmax_calibration({"a": 0.9, "b": 0.1, "c": 0.5})
        assert all(0.0 <= p <= 1.0 for p in result.values())


# ============================================================================
# CONFIDENCE BANDING (ToolMatch.__post_init__)
# ============================================================================


class TestToolMatchConfidence:
    @staticmethod
    def _match(score: float) -> ToolMatch:
        return ToolMatch(tool_name="t", tool_manifest=MagicMock(), score=score)

    @pytest.mark.parametrize(
        ("score", "expected"),
        [
            (0.80, "high"),
            (0.40, "high"),
            (0.39, "medium"),
            (0.15, "medium"),
            (0.14, "low"),
            (0.0, "low"),
        ],
    )
    def test_confidence_bands(self, score: float, expected: str) -> None:
        assert self._match(score).confidence == expected


# ============================================================================
# RESULT ACCESSORS
# ============================================================================


class TestToolSelectionResult:
    def test_empty_result_has_no_tools(self) -> None:
        result = ToolSelectionResult()
        assert result.tool_names == []
        assert result.tools_with_scores == []

    def test_tool_names_lists_in_order(self) -> None:
        result = ToolSelectionResult(
            selected_tools=[
                ToolMatch("first", MagicMock(), 0.6),
                ToolMatch("second", MagicMock(), 0.3),
            ]
        )
        assert result.tool_names == ["first", "second"]

    def test_tools_with_scores_rounds_and_includes_confidence(self) -> None:
        result = ToolSelectionResult(selected_tools=[ToolMatch("t", MagicMock(), 0.123456)])
        row = result.tools_with_scores[0]
        assert row == {"tool": "t", "score": 0.123, "confidence": "low"}


# ============================================================================
# SEMANTIC DESCRIPTION EXTRACTION
# ============================================================================


class TestExtractSemanticDescription:
    def test_first_line_is_kept_and_markdown_stripped(self, selector: SemanticToolSelector) -> None:
        result = selector._extract_semantic_description(
            "**Tool: search** - Find contacts.\nMODE: detailed\nPARAMETERS: ..."
        )
        assert result == "Tool: search - Find contacts."

    def test_single_line_description_is_returned_whole(
        self, selector: SemanticToolSelector
    ) -> None:
        assert selector._extract_semantic_description("Just a summary") == "Just a summary"

    def test_empty_description_is_empty(self, selector: SemanticToolSelector) -> None:
        assert selector._extract_semantic_description("") == ""


# ============================================================================
# CONTENT HASH (gates the paid embedding refresh)
# ============================================================================


class TestComputeContentHash:
    TEXTS = ["desc one", "keyword a"]
    META = [("tool_a", "description"), ("tool_a", "keyword")]

    def test_hash_is_deterministic(self) -> None:
        h1 = SemanticToolSelector._compute_content_hash(self.TEXTS, self.META, "gemini-embed")
        h2 = SemanticToolSelector._compute_content_hash(self.TEXTS, self.META, "gemini-embed")
        assert h1 == h2

    def test_changing_a_text_changes_the_hash(self) -> None:
        base = SemanticToolSelector._compute_content_hash(self.TEXTS, self.META, "gemini-embed")
        changed = SemanticToolSelector._compute_content_hash(
            ["desc one", "keyword b"], self.META, "gemini-embed"
        )
        assert base != changed

    def test_changing_the_model_changes_the_hash(self) -> None:
        """A new embedding model must invalidate the cache."""
        base = SemanticToolSelector._compute_content_hash(self.TEXTS, self.META, "gemini-embed")
        other = SemanticToolSelector._compute_content_hash(self.TEXTS, self.META, "other-model")
        assert base != other

    def test_reordering_tools_changes_the_hash(self) -> None:
        """Order matters: the embeddings are stored positionally."""
        base = SemanticToolSelector._compute_content_hash(self.TEXTS, self.META, "gemini-embed")
        reordered = SemanticToolSelector._compute_content_hash(
            list(reversed(self.TEXTS)), list(reversed(self.META)), "gemini-embed"
        )
        assert base != reordered

    def test_mismatched_lengths_raise(self) -> None:
        """``strict=True`` zip: a metadata/text length mismatch is a bug, not silent."""
        with pytest.raises(ValueError):
            SemanticToolSelector._compute_content_hash(["a", "b"], [("t", "description")], "m")
