"""
Classification Extractor Policy.

This policy extracts classification data from ClassificationResult objects or dicts,
providing a consistent interface for accessing classification fields.

Architecture:
- Handles both ClassificationResult objects and dicts for backward compatibility
- Extracts: decision, reasoning, edited_params, clarification_question
- Used by decision builders to normalize classification inputs
"""

from typing import Any


class ClassificationExtractor:
    """
    Policy class for extracting classification data.

    Handles both ClassificationResult objects (from HitlResponseClassifier)
    and dict formats for backward compatibility.
    """

    @staticmethod
    def extract(
        classification: Any,
    ) -> tuple[str, str, dict[str, Any] | None, str | None]:
        """
        Extract classification data from ClassificationResult or dict.

        Args:
            classification: ClassificationResult object or dict

        Returns:
            Tuple of (decision, reasoning, edited_params, clarification_question)

        Example:
            >>> extractor = ClassificationExtractor()
            >>> decision, reasoning, params, question = extractor.extract(classification)
            >>> print(decision)  # "approve", "reject", "edit", or "ambiguous"
        """
        if hasattr(classification, "decision"):
            # ClassificationResult object
            decision = classification.decision
            reasoning = classification.reasoning
            edited_params = classification.edited_params
            clarification_question = getattr(classification, "clarification_question", None)
        else:
            # Dict (backward compatibility)
            decision = classification.get("decision")
            reasoning = classification.get("reasoning", "")
            edited_params = classification.get("edited_params")
            clarification_question = classification.get("clarification_question")

        return decision, reasoning, edited_params, clarification_question


__all__ = [
    "ClassificationExtractor",
]
