"""
Embedding utility functions.

Provides cosine similarity calculation used by:
- SemanticToolSelector (tool routing)
- Interest extraction (topic deduplication)
- Interest content sources (content deduplication)

Note: The former LocalE5Embeddings class has been replaced by OpenAI
text-embedding-3-small via memory_embeddings.py (v1.14.0).
"""

import numpy as np
import numpy.typing as npt

from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def cosine_similarity(vec_a: npt.ArrayLike, vec_b: npt.ArrayLike) -> float:
    """Calculate cosine similarity between two embedding vectors.

    Accepts lists of floats as the embedders hand them and float32 arrays as
    the selector stores them (ADR-283 amendment 2026-10-12): an array is used
    as it is, a list is converted once. A width mismatch or a zero vector
    scores ``0.0`` rather than raising.

    Args:
        vec_a: First embedding vector.
        vec_b: Second embedding vector.

    Returns:
        Similarity score between -1.0 and 1.0 (0.0 on mismatch or zero norm).

    Example:
        >>> from src.infrastructure.llm.local_embeddings import cosine_similarity
        >>> vec1 = [0.1, 0.2, 0.3]
        >>> vec2 = [0.15, 0.25, 0.35]
        >>> similarity = cosine_similarity(vec1, vec2)
        >>> print(f"Similarity: {similarity:.3f}")
    """
    a = np.asarray(vec_a, dtype=np.float32)
    b = np.asarray(vec_b, dtype=np.float32)
    if a.shape != b.shape or a.ndim != 1:
        logger.warning(
            "cosine_similarity_dimension_mismatch",
            len_a=int(a.size),
            len_b=int(b.size),
        )
        return 0.0

    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return float(np.dot(a, b) / (norm_a * norm_b))
