"""Tool vectors as compact float32 arrays, parsed once per catalogue and per worker.

Measured on production on 2026-10-12 (ADR-283, amendment): a worker held 2,650 to
3,722 embedding vectors of 1,536 Python floats — the native catalogue's 1,585,
plus one copy of the person's MCP servers' vectors for every request context
still alive — and each vector cost 49 KB as ``list[float]`` (a float object is
24 bytes, its list slot 8 more). The same vector is 6 KB as a float32 array,
and a cosine is a dot product either way. This module is the ONE place a
vector takes its compact form:

- :func:`as_vector` / :func:`as_matrix` convert what the embedder or a JSON
  envelope hands over; the selector stores nothing else.
- :func:`cosine_rows` scores a query against every row of a matrix at once.
- :class:`ServerVectorCache` keeps a person's MCP servers' vectors per worker,
  keyed by the server, the embedding model and the catalogue fingerprint, so a
  turn re-reads and re-parses the persisted envelope only when the catalogue
  or the model changed — never on every turn, and never once per context.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Mapping
from functools import lru_cache
from typing import Any, Final

import numpy as np
import numpy.typing as npt

from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

Vector = npt.NDArray[np.float32]
Matrix = npt.NDArray[np.float32]

#: Key of a server's vectors in :class:`ServerVectorCache`: server id, the
#: embedding model (name and width), the catalogue fingerprint.
ServerVectorKey = tuple[str, str, str]

DESCRIPTION_KEY: Final = "description"
KEYWORDS_KEY: Final = "keywords"
KEYWORD_NAMES_KEY: Final = "keyword_names"


def as_vector(values: npt.ArrayLike) -> Vector:
    """One embedding as a float32 1-D array (no copy when it already is one).

    Args:
        values: The embedding, as the embedder or a JSON envelope hands it.

    Returns:
        The float32 array.

    Raises:
        ValueError: When the values do not form a 1-D vector.
    """
    vector = np.asarray(values, dtype=np.float32)
    if vector.ndim != 1:
        raise ValueError(f"a vector is one-dimensional, got shape {vector.shape}")
    return vector


def as_matrix(rows: npt.ArrayLike) -> Matrix:
    """Several embeddings of one width as a float32 ``(rows, width)`` array.

    Args:
        rows: The embeddings, one per row.

    Returns:
        The matrix; ``(0, 0)`` when there is no row.

    Raises:
        ValueError: When the rows differ in width.
    """
    matrix = np.asarray(rows, dtype=np.float32)
    if matrix.size == 0:
        return np.zeros((0, 0), dtype=np.float32)
    if matrix.ndim == 1:
        matrix = matrix.reshape(1, -1)
    if matrix.ndim != 2:
        raise ValueError(f"a matrix is two-dimensional, got shape {matrix.shape}")
    return matrix


def cosine_rows(query: Vector, rows: Matrix) -> npt.NDArray[np.float32]:
    """Cosine of ``query`` against every row of ``rows`` — ``0.0`` where a norm is zero.

    A row of another width than the query scores ``0.0`` for every row, as the
    scalar :func:`~src.infrastructure.llm.local_embeddings.cosine_similarity`
    does, and the mismatch is logged once per call rather than once per row.

    Args:
        query: The query vector.
        rows: The candidate vectors, one per row.

    Returns:
        One cosine per row, in row order.
    """
    if rows.size == 0:
        return np.zeros(0, dtype=np.float32)
    if rows.shape[1] != query.shape[0]:
        logger.warning(
            "cosine_similarity_dimension_mismatch",
            len_a=int(query.shape[0]),
            len_b=int(rows.shape[1]),
            rows=int(rows.shape[0]),
        )
        return np.zeros(rows.shape[0], dtype=np.float32)
    query_norm = float(np.linalg.norm(query))
    if query_norm == 0.0:
        return np.zeros(rows.shape[0], dtype=np.float32)
    norms = np.linalg.norm(rows, axis=1)
    dots = rows @ query
    with np.errstate(divide="ignore", invalid="ignore"):
        sims = np.where(norms > 0, dots / (norms * query_norm), 0.0)
    return np.asarray(sims, dtype=np.float32)


def compact_tool_vectors(tools: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """A persisted envelope's per-tool vectors as arrays, same keys, same shape of dict.

    ``description`` becomes a 1-D array, ``keywords`` a ``(k, width)`` matrix,
    ``keyword_names`` travels unchanged. A tool whose vectors cannot be read
    (ragged, non-numeric) is left out: it would have scored ``0.0`` anyway,
    and the count is logged so a corrupt envelope is not a silence.

    Args:
        tools: ``{raw tool name: {"description": [...], "keywords": [[...]], ...}}``.

    Returns:
        The same mapping with compact vectors; an empty dict for an empty input.
    """
    compact: dict[str, dict[str, Any]] = {}
    unreadable = 0
    for name, entry in tools.items():
        if not isinstance(entry, Mapping):
            unreadable += 1
            continue
        try:
            vectors: dict[str, Any] = {}
            description = entry.get(DESCRIPTION_KEY)
            if description is not None:
                vectors[DESCRIPTION_KEY] = as_vector(description)
            keywords = entry.get(KEYWORDS_KEY)
            if keywords:
                vectors[KEYWORDS_KEY] = as_matrix(keywords)
        except TypeError, ValueError:
            unreadable += 1
            continue
        names = entry.get(KEYWORD_NAMES_KEY)
        if names:
            vectors[KEYWORD_NAMES_KEY] = list(names)
        compact[name] = vectors
    if unreadable:
        logger.warning("tool_vectors_unreadable", tool_count=unreadable, total=len(tools))
    return compact


class ServerVectorCache:
    """Per-worker, bounded, least-recently-used store of compact server vectors.

    One entry per ``(server, model, catalogue fingerprint)``: a new catalogue or
    a new model is a new key, and the stale entry leaves when the bound is
    reached. The bound counts servers, not vectors: a person's server holds its
    whole catalogue in one entry.
    """

    def __init__(self, max_entries: int) -> None:
        """Create an empty cache bounded at ``max_entries`` (at least one)."""
        self._entries: OrderedDict[ServerVectorKey, dict[str, dict[str, Any]]] = OrderedDict()
        self._max_entries = max(1, int(max_entries))

    def __len__(self) -> int:
        return len(self._entries)

    def get(self, key: ServerVectorKey) -> dict[str, dict[str, Any]] | None:
        """The vectors cached under ``key``, marking it recently used; None when absent."""
        entry = self._entries.get(key)
        if entry is not None:
            self._entries.move_to_end(key)
        return entry

    def put(self, key: ServerVectorKey, vectors: dict[str, dict[str, Any]]) -> None:
        """Cache ``vectors`` under ``key``, evicting the least recently used past the bound."""
        self._entries[key] = vectors
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_entries:
            evicted, _ = self._entries.popitem(last=False)
            logger.debug("server_vector_cache_evicted", server_id=evicted[0])

    def clear(self) -> None:
        """Forget every entry (tests, and a model change at runtime)."""
        self._entries.clear()


@lru_cache(maxsize=1)
def get_server_vector_cache() -> ServerVectorCache:
    """The process-wide cache, bounded by ``MCP_SERVER_VECTOR_CACHE_MAX``."""
    from src.core.config import settings

    return ServerVectorCache(settings.mcp_server_vector_cache_max)


def reset_server_vector_cache() -> None:
    """Drop the process-wide cache (tests)."""
    get_server_vector_cache.cache_clear()


__all__ = [
    "DESCRIPTION_KEY",
    "KEYWORDS_KEY",
    "KEYWORD_NAMES_KEY",
    "Matrix",
    "ServerVectorCache",
    "ServerVectorKey",
    "Vector",
    "as_matrix",
    "as_vector",
    "compact_tool_vectors",
    "cosine_rows",
    "get_server_vector_cache",
    "reset_server_vector_cache",
]
