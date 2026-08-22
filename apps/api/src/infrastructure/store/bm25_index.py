"""
BM25 Index Manager for Hybrid Memory Search.

Provides cached BM25 indices per user with LRU eviction.
Follows codebase patterns: singleton, structured logging, metrics.

Usage:
    manager = get_bm25_manager()
    bm25, doc_ids = manager.get_or_build_index(user_id, docs, doc_ids)
    scores = bm25.get_scores(tokenize_text(query))
"""

import hashlib
import re
from functools import lru_cache
from typing import TYPE_CHECKING

from rank_bm25 import BM25Okapi

from src.core.config import get_settings
from src.core.constants import CJK_SCRIPT_RANGES
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics import (
    bm25_cache_hits_total,
    bm25_cache_misses_total,
    bm25_cache_size,
)

if TYPE_CHECKING:
    from src.core.config import Settings

logger = get_logger(__name__)

# `\w` matches every space-less script, so a whole Chinese sentence came out as
# ONE token and BM25 degenerated into exact-sentence matching (ADR-242). The
# range list lives in core.constants because the embedding token estimator needs
# exactly the same one.
_CJK_RANGES = CJK_SCRIPT_RANGES

# One alternation per token family, so a single pass keeps their relative order:
#   group 1 = a run of space-less script, split into bigrams below
#   group 2 = a word in a space-separated script, apostrophes kept only INSIDE
#             the word (``l'assistant`` is one token, ``users'`` is ``users``)
_TOKEN_PATTERN = re.compile(
    rf"([{_CJK_RANGES}]+)|([^\W{_CJK_RANGES}]+(?:'[^\W{_CJK_RANGES}]+)*)",
    re.UNICODE,
)

# Character n-gram width for space-less scripts. 2 is the standard choice for
# CJK retrieval: it needs no dictionary or segmenter (no extra dependency, no
# per-language model to ship on the Pi) and it makes any substring of the query
# share tokens with the document. Measured on a zh corpus of 98 chunks with 80
# native queries: BM25-only hit@5 0.062 -> 0.487 (2026-08-22).
_CJK_NGRAM = 2


def tokenize_text(text: str) -> list[str]:
    """
    Tokenize text for BM25 scoring, across all 6 supported languages.

    Space-separated scripts (fr, en, de, es, it) are split on word boundaries,
    accents preserved via the UNICODE flag and intra-word apostrophes kept.
    Space-less scripts (zh, and any Japanese/Korean content a user uploads) are
    split into overlapping character bigrams, because word boundaries do not
    exist there and a whole sentence would otherwise be a single token.

    Single-character tokens are dropped as noise in space-separated scripts; a
    lone CJK character is kept, since one ideograph is already a full morpheme
    and there is no bigram to form.

    Args:
        text: Input text to tokenize

    Returns:
        List of lowercase tokens
    """
    tokens: list[str] = []
    for cjk_run, word in _TOKEN_PATTERN.findall(text.lower()):
        if cjk_run:
            if len(cjk_run) <= _CJK_NGRAM:
                tokens.append(cjk_run)
            else:
                tokens.extend(
                    cjk_run[i : i + _CJK_NGRAM] for i in range(len(cjk_run) - _CJK_NGRAM + 1)
                )
        elif len(word) > 1:
            tokens.append(word)
    return tokens


class BM25IndexManager:
    """
    Manages BM25 indices with per-user caching.

    Thread-safe for read operations. Cache uses content hash
    for automatic invalidation on corpus changes.

    Usage:
        manager = get_bm25_manager()
        bm25, doc_ids = manager.get_or_build_index(user_id, docs, doc_ids)
        scores = bm25.get_scores(tokenize_text(query))
    """

    def __init__(self, settings: Settings) -> None:
        self._local_cache: dict[str, tuple[BM25Okapi, list[str]]] = {}
        self._max_users = settings.memory_bm25_cache_max_users
        logger.info(
            "bm25_manager_initialized",
            max_users=self._max_users,
        )

    def get_or_build_index(
        self,
        user_id: str,
        documents: list[str],
        document_ids: list[str],
    ) -> tuple[BM25Okapi, list[str]]:
        """
        Get cached BM25 index or build new one.

        Args:
            user_id: User ID for cache scoping
            documents: List of document contents
            document_ids: List of document IDs (for result mapping)

        Returns:
            Tuple of (BM25Okapi instance, document_ids)
        """
        content_hash = self._compute_hash(documents)
        cache_key = f"bm25:{user_id}:{content_hash}"

        # Cache hit
        if cache_key in self._local_cache:
            bm25_cache_hits_total.inc()
            logger.debug(
                "bm25_cache_hit",
                user_id=user_id,
                cache_key=cache_key,
            )
            return self._local_cache[cache_key]

        # Cache miss - build index
        bm25_cache_misses_total.inc()
        tokenized = [tokenize_text(doc) for doc in documents]
        bm25 = BM25Okapi(tokenized)

        # LRU eviction
        if len(self._local_cache) >= self._max_users:
            evicted_key = next(iter(self._local_cache))
            del self._local_cache[evicted_key]
            logger.debug("bm25_cache_eviction", evicted_key=evicted_key)

        self._local_cache[cache_key] = (bm25, document_ids)
        bm25_cache_size.set(len(self._local_cache))

        logger.debug(
            "bm25_index_built",
            user_id=user_id,
            document_count=len(documents),
            cache_size=len(self._local_cache),
        )

        return bm25, document_ids

    def _compute_hash(self, documents: list[str]) -> str:
        """Compute content hash for cache invalidation."""
        content = "".join(sorted(documents))
        return hashlib.md5(content.encode()).hexdigest()[:8]

    def invalidate_user_cache(self, user_id: str) -> None:
        """Invalidate all BM25 caches for a user."""
        keys_to_remove = [k for k in self._local_cache if k.startswith(f"bm25:{user_id}:")]
        for k in keys_to_remove:
            del self._local_cache[k]

        if keys_to_remove:
            bm25_cache_size.set(len(self._local_cache))
            logger.info(
                "bm25_cache_invalidated",
                user_id=user_id,
                keys_removed=len(keys_to_remove),
            )


@lru_cache
def get_bm25_manager() -> BM25IndexManager:
    """Get singleton BM25IndexManager instance."""
    return BM25IndexManager(get_settings())
