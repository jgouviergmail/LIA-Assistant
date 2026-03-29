"""
Embedding utility functions.

Provides cosine similarity calculation used by:
- SemanticToolSelector (tool routing)
- Interest extraction (topic deduplication)
- Interest content sources (content deduplication)

Note: The former LocalE5Embeddings class has been replaced by OpenAI
text-embedding-3-small via memory_embeddings.py (v1.14.0).
"""

from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Calculate cosine similarity between two embedding vectors.

    Optimized implementation using numpy when available, with pure Python fallback.
    Used for semantic similarity comparisons across interests, content, and tools.

    Args:
        vec_a: First embedding vector.
        vec_b: Second embedding vector.

    Returns:
        Similarity score between 0.0 and 1.0.

    Example:
        >>> from src.infrastructure.llm.local_embeddings import cosine_similarity
        >>> vec1 = [0.1, 0.2, 0.3]
        >>> vec2 = [0.15, 0.25, 0.35]
        >>> similarity = cosine_similarity(vec1, vec2)
        >>> print(f"Similarity: {similarity:.3f}")
    """
    if len(vec_a) != len(vec_b):
        logger.warning(
            "cosine_similarity_dimension_mismatch",
            len_a=len(vec_a),
            len_b=len(vec_b),
        )
        return 0.0

    try:
        import numpy as np

        a = np.array(vec_a)
        b = np.array(vec_b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return float(np.dot(a, b) / (norm_a * norm_b))

    except ImportError:
        # Fallback to pure Python implementation
        dot_product: float = sum(a * b for a, b in zip(vec_a, vec_b, strict=False))
        norm_a = sum(a * a for a in vec_a) ** 0.5
        norm_b = sum(b * b for b in vec_b) ** 0.5

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return float(dot_product / (norm_a * norm_b))
