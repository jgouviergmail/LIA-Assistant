"""
Local HuggingFace Embeddings for Semantic Memory Search.

Provides a LangChain-compatible embedding wrapper for local sentence-transformers models,
specifically optimized for the multilingual-e5-small model.

Key features:
- Inherits from LangChain Embeddings ABC for full ecosystem compatibility
- Lazy model loading (only loads on first use)
- Thread-safe singleton pattern
- Optimized for CPU inference on Raspberry Pi 5
- No API costs (runs locally)
- Better Q/A matching than OpenAI text-embedding-3-small (0.90 vs 0.61 avg score)

Usage:
    embeddings = get_local_embeddings()
    vector = embeddings.embed_query("je me suis marié quand ?")
    vectors = embeddings.embed_documents(["Je me suis marié en 2008"])

References:
    - Model: https://huggingface.co/intfloat/multilingual-e5-small
    - Benchmark: apps/api/scripts/test_embedding_models.py
    - LangChain Embeddings: https://python.langchain.com/docs/how_to/custom_embeddings/
"""

import threading
from typing import TYPE_CHECKING

from langchain_core.embeddings import Embeddings

from src.core.config import settings
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = get_logger(__name__)

# Thread-safe singleton for the embedding model
_model_lock = threading.Lock()
_embedding_model: "SentenceTransformer | None" = None
_model_loading = False


class LocalE5Embeddings(Embeddings):
    """
    LangChain-compatible embeddings using local sentence-transformers E5 model.

    Inherits from langchain_core.embeddings.Embeddings ABC for full ecosystem
    compatibility with LangChain and LangGraph components.

    The model is loaded lazily on first use and cached as a singleton to avoid
    repeated loading overhead (~9s per load on Raspberry Pi 5).

    Attributes:
        model_name: HuggingFace model identifier (default: intfloat/multilingual-e5-small)
        dimensions: Output embedding dimensions (384 for E5-small)

    Example:
        >>> embeddings = LocalE5Embeddings()
        >>> vectors = embeddings.embed_documents(["Hello", "World"])
        >>> query_vec = embeddings.embed_query("Hi")
    """

    # Pydantic model config for LangChain compatibility
    model_name: str = "intfloat/multilingual-e5-small"
    dimensions: int = 384

    def __init__(
        self,
        model_name: str = "intfloat/multilingual-e5-small",
        dimensions: int = 384,
        **kwargs,
    ):
        """
        Initialize the E5 embeddings wrapper.

        Args:
            model_name: HuggingFace model identifier
            dimensions: Expected output dimensions (for validation)
            **kwargs: Additional arguments for LangChain Embeddings base class
        """
        super().__init__(**kwargs)
        self.model_name = model_name
        self.dimensions = dimensions
        self._model: SentenceTransformer | None = None

    def _get_model(self) -> "SentenceTransformer":
        """
        Get or load the sentence-transformers model (thread-safe singleton).

        Returns:
            Loaded SentenceTransformer model

        Raises:
            ImportError: If sentence-transformers is not installed
        """
        global _embedding_model, _model_loading

        if _embedding_model is not None:
            return _embedding_model

        with _model_lock:
            # Double-check after acquiring lock
            if _embedding_model is not None:
                return _embedding_model

            if _model_loading:
                # Another thread is loading, wait for it
                logger.warning("e5_model_concurrent_load_detected")

            _model_loading = True

            try:
                logger.info(
                    "e5_model_loading",
                    model_name=self.model_name,
                    message="Loading E5 embedding model (one-time, ~9s on Pi 5)...",
                )

                from sentence_transformers import SentenceTransformer

                model = SentenceTransformer(
                    self.model_name,
                    device="cpu",  # Explicit CPU for Raspberry Pi
                )

                # Validate dimensions
                test_emb = model.encode("test", normalize_embeddings=True)
                actual_dims = len(test_emb)

                if actual_dims != self.dimensions:
                    logger.warning(
                        "e5_dimensions_mismatch",
                        expected=self.dimensions,
                        actual=actual_dims,
                        message="Dimension mismatch - using actual dimensions",
                    )
                    self.dimensions = actual_dims

                _embedding_model = model

                logger.info(
                    "e5_model_loaded",
                    model_name=self.model_name,
                    dimensions=self.dimensions,
                )

                return model

            except ImportError as e:
                logger.error(
                    "e5_model_import_error",
                    error=str(e),
                    message="sentence-transformers not installed. Run: pip install sentence-transformers",
                )
                raise

            finally:
                _model_loading = False

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a list of documents (memories).

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors (normalized for cosine similarity)
        """
        if not texts:
            return []

        model = self._get_model()

        # E5 models work best in symmetric mode (no prefixes needed)
        # Based on benchmark: symmetric mode scores 0.901 avg vs 0.869 with prefixes
        embeddings = model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )

        return embeddings.tolist()

    def embed_query(self, text: str) -> list[float]:
        """
        Embed a single query text.

        Args:
            text: Query string to embed

        Returns:
            Embedding vector (normalized for cosine similarity)
        """
        model = self._get_model()

        # E5 symmetric mode - no query prefix needed
        embedding = model.encode(
            text,
            normalize_embeddings=True,
            show_progress_bar=False,
        )

        return embedding.tolist()

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        """
        Async wrapper for embed_documents (runs synchronously in thread pool).

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors
        """
        import asyncio

        return await asyncio.to_thread(self.embed_documents, texts)

    async def aembed_query(self, text: str) -> list[float]:
        """
        Async wrapper for embed_query (runs synchronously in thread pool).

        Args:
            text: Query string to embed

        Returns:
            Embedding vector
        """
        import asyncio

        return await asyncio.to_thread(self.embed_query, text)

    def __call__(self, texts: list[str]) -> list[list[float]]:
        """
        Make the embeddings callable for LangGraph compatibility.

        LangGraph's AsyncPostgresStore expects `embed` to be callable with signature:
            Callable[[Sequence[str]], list[list[float]]]

        This method delegates to embed_documents for compatibility.

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors
        """
        return self.embed_documents(texts)


# Module-level singleton instance
_local_embeddings: LocalE5Embeddings | None = None


def get_local_embeddings() -> LocalE5Embeddings:
    """
    Get the singleton LocalE5Embeddings instance.

    Uses settings for model configuration.

    Returns:
        LocalE5Embeddings instance (singleton)
    """
    global _local_embeddings

    if _local_embeddings is None:
        _local_embeddings = LocalE5Embeddings(
            model_name=settings.memory_embedding_model,
            dimensions=settings.memory_embedding_dimensions,
        )

    return _local_embeddings


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """
    Calculate cosine similarity between two embedding vectors.

    Optimized implementation using numpy when available, with pure Python fallback.
    Used for semantic similarity comparisons across interests, content, and tools.

    Args:
        vec_a: First embedding vector
        vec_b: Second embedding vector

    Returns:
        Similarity score between 0.0 and 1.0

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
        # Try numpy for performance (if available from sentence-transformers)
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


def preload_embedding_model() -> None:
    """
    Preload the embedding model during application startup.

    Call this during FastAPI lifespan startup to avoid first-request latency.
    Loading takes ~9s on Raspberry Pi 5.

    Usage:
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            preload_embedding_model()
            yield

    NOTE: Memory and local embeddings are always enabled.
    """
    logger.info("e5_preload_starting")
    embeddings = get_local_embeddings()
    # Trigger model load
    embeddings._get_model()
    logger.info("e5_preload_completed")


def reset_embedding_model() -> None:
    """
    Reset the embedding model singleton (for testing only).

    WARNING: Only use in tests to force model reload.
    """
    global _embedding_model, _local_embeddings

    with _model_lock:
        _embedding_model = None
        _local_embeddings = None

    logger.warning("e5_model_reset")
