"""
Mixin for lazy-loading Redis cache in Google API clients.

Eliminates code duplication in GooglePeopleClient and GooglePlacesClient.
Both clients use the same pattern for cache initialization.

Usage:
    class GooglePeopleClient(CacheableMixin[ContactsCache], BaseGoogleClient):
        _cache_class = ContactsCache
        ...
        # Use self._get_cache() to get the cache instance
"""

from typing import Generic, TypeVar

from src.infrastructure.cache.redis import get_redis_cache

T = TypeVar("T")


class CacheableMixin(Generic[T]):
    """
    Mixin providing lazy-loaded Redis cache for Google API clients.

    Type parameter T is the cache class (ContactsCache, PlacesCache).

    Subclasses must define:
        _cache_class: type[T] - The cache class to instantiate

    Example:
        >>> class GooglePeopleClient(CacheableMixin[ContactsCache], BaseGoogleClient):
        ...     _cache_class = ContactsCache
        ...
        ...     async def search(self, query: str):
        ...         cache = await self._get_cache()
        ...         return await cache.get(query)
    """

    _cache: T | None = None
    _cache_class: type[T]  # Must be defined in subclass

    async def _get_cache(self) -> T:
        """
        Get or create cache instance.

        Lazy initialization ensures Redis connection is only established
        when cache is actually needed.

        Returns:
            Cache instance of type T
        """
        if self._cache is None:
            redis_client = await get_redis_cache()
            self._cache = self._cache_class(redis_client)
        return self._cache
