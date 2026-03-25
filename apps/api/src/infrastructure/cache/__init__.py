"""Cache infrastructure for LIA."""

from .base import (
    CacheEntryV2,
    CacheResult,
    calculate_cache_age,
    create_cache_entry,
    make_payload_hash,
    make_query_hash,
    make_resource_key,
    make_search_key,
    make_user_key,
    parse_cache_entry,
    sanitize_key_part,
)
from .contacts_cache import ContactsCache
from .conversation_cache import (
    ConversationIdCache,
    get_conversation_id_cached,
    invalidate_conversation_id_cache,
)
from .invalidation import (
    publish_cache_invalidation,
    register_cache,
    run_invalidation_subscriber,
)
from .llm_cache import cache_llm_response, invalidate_llm_cache
from .places_cache import PlacesCache
from .pricing_cache import (
    TokenUsageRecord,
    calculate_total_cost_from_logs,
    get_cached_cost,
    is_cache_initialized,
    refresh_pricing_cache,
)
from .redis import CacheService, SessionService, get_redis_cache, get_redis_session
from .routes_cache import RoutesCache
from .web_search_cache import WebSearchCache

__all__ = [
    # Base cache utilities
    "CacheEntryV2",
    "CacheResult",
    "calculate_cache_age",
    "create_cache_entry",
    "make_payload_hash",
    "make_query_hash",
    "make_resource_key",
    "make_search_key",
    "make_user_key",
    "parse_cache_entry",
    "sanitize_key_part",
    # Cache services
    "CacheService",
    "ContactsCache",
    "ConversationIdCache",
    "PlacesCache",
    "RoutesCache",
    "WebSearchCache",
    "SessionService",
    "TokenUsageRecord",
    "cache_llm_response",
    "calculate_total_cost_from_logs",
    "get_cached_cost",
    "get_conversation_id_cached",
    "get_redis_cache",
    "get_redis_session",
    "invalidate_conversation_id_cache",
    "invalidate_llm_cache",
    "is_cache_initialized",
    "publish_cache_invalidation",
    "refresh_pricing_cache",
    "register_cache",
    "run_invalidation_subscriber",
]
