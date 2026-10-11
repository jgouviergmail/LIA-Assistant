"""Bounded ephemeral memory-extraction diagnostics; consumed by the SSE finalizer."""

import time
from collections.abc import Mapping

from pydantic import JsonValue, TypeAdapter, ValidationError

_memory_extraction_debug_cache: dict[str, tuple[float, dict[str, JsonValue]]] = {}
_MEMORY_DEBUG_CACHE_MAX_SIZE = 100
_MEMORY_DEBUG_CACHE_TTL_SECONDS = 120.0
_JSON: TypeAdapter[dict[str, JsonValue]] = TypeAdapter(dict[str, JsonValue])


def _cache_debug_result(run_id: str, data: Mapping[str, object]) -> None:
    """Store debug data with timestamp and size enforcement."""
    try:
        payload = _JSON.validate_python(dict(data))
    except ValidationError:
        # Diagnostics cannot change a committed extraction or retain live objects.
        return
    while len(_memory_extraction_debug_cache) >= _MEMORY_DEBUG_CACHE_MAX_SIZE:
        oldest_key = min(
            _memory_extraction_debug_cache,
            key=lambda k: _memory_extraction_debug_cache[k][0],
        )
        _memory_extraction_debug_cache.pop(oldest_key, None)
    _memory_extraction_debug_cache[run_id] = (time.monotonic(), payload)


def get_memory_extraction_debug(run_id: str) -> dict[str, JsonValue] | None:
    """Retrieve and consume debug data for streaming service.

    Args:
        run_id: Pipeline run_id.

    Returns:
        Debug dict or None.
    """
    now = time.monotonic()
    stale_keys = [
        k
        for k, (ts, _) in _memory_extraction_debug_cache.items()
        if now - ts > _MEMORY_DEBUG_CACHE_TTL_SECONDS
    ]
    for k in stale_keys:
        _memory_extraction_debug_cache.pop(k, None)

    entry = _memory_extraction_debug_cache.pop(run_id, None)
    if entry is None:
        return None
    return entry[1]
