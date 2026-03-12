"""
Base cache utilities and helpers.

Provides reusable components for cache implementations:
- Cache age calculation
- Cache entry format (V2 with metadata)
- Query hash generation
- Standard key patterns

All domain caches should use these helpers to ensure consistency.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, TypedDict
from uuid import UUID

import structlog

from src.infrastructure.observability.metrics import cache_hit_total, cache_miss_total

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)


# ============================================================================
# Cache Entry Format (V2)
# ============================================================================


class CacheEntryV2(TypedDict):
    """V2 cache entry format with metadata wrapper."""

    data: dict[str, Any]
    cached_at: str  # ISO 8601 UTC timestamp
    ttl: int  # Original TTL in seconds


@dataclass(frozen=True)
class CacheResult:
    """Result from cache get operations with metadata."""

    data: dict[str, Any] | None
    from_cache: bool
    cached_at: str | None
    cache_age_seconds: int | None

    @classmethod
    def miss(cls) -> CacheResult:
        """Create a cache miss result."""
        return cls(data=None, from_cache=False, cached_at=None, cache_age_seconds=None)

    @classmethod
    def hit(cls, data: dict[str, Any], cached_at: str, cache_age: int) -> CacheResult:
        """Create a cache hit result."""
        return cls(data=data, from_cache=True, cached_at=cached_at, cache_age_seconds=cache_age)

    def as_tuple(self) -> tuple[dict[str, Any] | None, bool, str | None, int | None]:
        """Convert to legacy tuple format for backward compatibility."""
        return (self.data, self.from_cache, self.cached_at, self.cache_age_seconds)


# ============================================================================
# Cache Age Calculation
# ============================================================================


def calculate_cache_age(cached_at: str) -> int:
    """
    Calculate cache age in seconds from ISO 8601 timestamp.

    Args:
        cached_at: ISO 8601 timestamp string (UTC).

    Returns:
        Age in seconds (rounded to nearest integer).
        Returns 0 if parsing fails (assume fresh).

    Example:
        >>> age = calculate_cache_age("2025-01-26T14:30:00Z")
        >>> # Returns: 120 (if current time is 14:32:00)
    """
    try:
        cached_dt = datetime.fromisoformat(cached_at.replace("Z", "+00:00"))
        now_dt = datetime.now(UTC)
        delta = now_dt - cached_dt
        return int(delta.total_seconds())
    except Exception as e:
        logger.warning("cache_age_calculation_failed", cached_at=cached_at, error=str(e))
        return 0


# ============================================================================
# Cache Entry Creation
# ============================================================================


def create_cache_entry(data: dict[str, Any], ttl_seconds: int) -> CacheEntryV2:
    """
    Create a V2 cache entry with metadata wrapper.

    Args:
        data: The data to cache.
        ttl_seconds: Time-to-live in seconds.

    Returns:
        CacheEntryV2 dict ready for JSON serialization.

    Example:
        >>> entry = create_cache_entry({"contacts": [...]}, ttl_seconds=300)
        >>> json_str = json.dumps(entry)
    """
    return CacheEntryV2(
        data=data,
        cached_at=datetime.now(UTC).isoformat(),
        ttl=ttl_seconds,
    )


def parse_cache_entry(
    cached_json: str,
    cache_type: str,
    context_info: dict[str, Any] | None = None,
) -> CacheResult:
    """
    Parse a cached JSON entry and return CacheResult.

    Handles both V2 format (with metadata) and legacy V1 format.

    Args:
        cached_json: JSON string from Redis.
        cache_type: Type identifier for logging (e.g., "contacts_search").
        context_info: Additional context for logging.

    Returns:
        CacheResult with data and metadata.
    """
    try:
        parsed = json.loads(cached_json)
        if isinstance(parsed, dict) and "data" in parsed and "cached_at" in parsed:
            # V2 format with metadata
            data = parsed["data"]
            cached_at = parsed["cached_at"]
            cache_age = calculate_cache_age(cached_at)
            cache_hit_total.labels(cache_type=cache_type).inc()
            return CacheResult.hit(data, cached_at, cache_age)
        elif isinstance(parsed, dict):
            # V1 format (backward compatibility - no metadata)
            logger.debug(
                "cache_hit_v1_format",
                cache_type=cache_type,
                **(context_info or {}),
            )
            cache_hit_total.labels(cache_type=cache_type).inc()
            return CacheResult(
                data=parsed,
                from_cache=True,
                cached_at=None,
                cache_age_seconds=None,
            )
    except json.JSONDecodeError as e:
        logger.warning(
            "cache_parse_failed",
            cache_type=cache_type,
            error=str(e),
            **(context_info or {}),
        )
    return CacheResult.miss()


# ============================================================================
# Cache Key Generation
# ============================================================================


def make_query_hash(query: str, algorithm: str = "md5", length: int = 8) -> str:
    """
    Generate a hash for a query string.

    Args:
        query: The query string to hash.
        algorithm: Hash algorithm ("md5" or "sha256").
        length: Number of hex characters to return.

    Returns:
        Truncated hex hash of the query.

    Example:
        >>> make_query_hash("John Doe", algorithm="md5", length=8)
        'a7b9c8d1'
    """
    normalized = query.lower().strip()
    if algorithm == "sha256":
        h = hashlib.sha256(normalized.encode())
    else:
        h = hashlib.md5(normalized.encode())
    return h.hexdigest()[:length]


def make_payload_hash(payload: dict[str, Any], length: int = 16) -> str:
    """
    Generate a stable hash for a payload dict.

    Args:
        payload: Dict to hash (will be JSON-serialized with sorted keys).
        length: Number of hex characters to return.

    Returns:
        SHA256 hash of the payload.

    Example:
        >>> make_payload_hash({"query": "test", "type": "restaurant"})
        'a7b9c8d1e2f3g4h5'
    """
    payload_str = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(payload_str.encode()).hexdigest()[:length]


def make_search_key(
    prefix: str,
    user_id: UUID,
    query: str,
    algorithm: str = "md5",
    hash_length: int = 8,
) -> str:
    """
    Generate cache key for search queries.

    Standard format: {prefix}:{user_id}:{query_hash}

    Args:
        prefix: Cache key prefix (e.g., "contacts_search").
        user_id: User UUID.
        query: Search query string.
        algorithm: Hash algorithm for query.
        hash_length: Length of query hash.

    Returns:
        Cache key string.

    Example:
        >>> make_search_key("contacts_search", user_id, "John")
        'contacts_search:550e8400-...:a7b9c8d1'
    """
    query_hash = make_query_hash(query, algorithm=algorithm, length=hash_length)
    return f"{prefix}:{user_id}:{query_hash}"


def make_resource_key(prefix: str, user_id: UUID, resource_id: str) -> str:
    """
    Generate cache key for resource details.

    Standard format: {prefix}:{user_id}:{resource_id}

    Args:
        prefix: Cache key prefix (e.g., "contacts_details").
        user_id: User UUID.
        resource_id: Resource identifier.

    Returns:
        Cache key string.

    Example:
        >>> make_resource_key("contacts_details", user_id, "people/c12345")
        'contacts_details:550e8400-...:people/c12345'
    """
    return f"{prefix}:{user_id}:{resource_id}"


def make_user_key(prefix: str, user_id: UUID) -> str:
    """
    Generate cache key for user-level data.

    Standard format: {prefix}:{user_id}

    Args:
        prefix: Cache key prefix (e.g., "contacts_list").
        user_id: User UUID.

    Returns:
        Cache key string.

    Example:
        >>> make_user_key("contacts_list", user_id)
        'contacts_list:550e8400-...'
    """
    return f"{prefix}:{user_id}"


def sanitize_key_part(value: str, max_length: int = 20) -> str:
    """
    Sanitize a string for use in cache key (readable prefix).

    Args:
        value: String to sanitize.
        max_length: Maximum length of result.

    Returns:
        Lowercase alphanumeric ASCII string.

    Example:
        >>> sanitize_key_part("Paris, France!")
        'parisfrance'
    """
    sanitized = "".join(c for c in value if c.isascii() and c.isalnum())
    return sanitized[:max_length].lower()


# ============================================================================
# Exports
# ============================================================================


def record_cache_miss(cache_type: str) -> None:
    """Record a cache miss in Prometheus metrics.

    Call this at the caller level when Redis returns None or parse fails.
    Cache hits are tracked automatically inside ``parse_cache_entry()``.
    """
    cache_miss_total.labels(cache_type=cache_type).inc()


__all__ = [
    # Types
    "CacheEntryV2",
    "CacheResult",
    # Cache age
    "calculate_cache_age",
    # Cache entry
    "create_cache_entry",
    "parse_cache_entry",
    # Metrics
    "record_cache_miss",
    # Key generation
    "make_query_hash",
    "make_payload_hash",
    "make_search_key",
    "make_resource_key",
    "make_user_key",
    "sanitize_key_part",
]
