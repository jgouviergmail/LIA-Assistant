"""
Database configuration module.

Contains settings for:
- PostgreSQL (connection URL, pool size)
- Redis (connection URL, session/cache DBs)
- LLM caching configuration

Phase: PHASE 2.1 - Config Split
Created: 2025-11-20
"""

from pydantic import Field, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings

from src.core.constants import (
    DATABASE_MAX_OVERFLOW_DEFAULT,
    DATABASE_POOL_RECYCLE_DEFAULT,
    DATABASE_POOL_SIZE_DEFAULT,
    DATABASE_POOL_TIMEOUT_DEFAULT,
    LLM_CACHE_TTL_SECONDS_DEFAULT,
    REDIS_CACHE_DB,
    REDIS_CONVERSATION_ID_TTL_SECONDS_DEFAULT,
    REDIS_HEALTH_CHECK_INTERVAL_DEFAULT,
    REDIS_MAX_CONNECTIONS_DEFAULT,
    REDIS_SESSION_DB,
    REDIS_SOCKET_CONNECT_TIMEOUT_DEFAULT,
    REDIS_SOCKET_TIMEOUT_DEFAULT,
)


class DatabaseSettings(BaseSettings):
    """Database and caching settings."""

    # Database
    database_url: PostgresDsn = Field(
        ...,
        description="PostgreSQL connection URL with asyncpg driver",
    )
    database_pool_size: int = Field(
        default=DATABASE_POOL_SIZE_DEFAULT,
        description="DB connection pool size (persistent connections)",
    )
    database_max_overflow: int = Field(
        default=DATABASE_MAX_OVERFLOW_DEFAULT,
        description="DB max overflow connections (burst capacity)",
    )
    database_pool_timeout: int = Field(
        default=DATABASE_POOL_TIMEOUT_DEFAULT,
        description="Seconds to wait for connection before TimeoutError",
    )
    database_pool_recycle: int = Field(
        default=DATABASE_POOL_RECYCLE_DEFAULT,
        description="Recycle connections after N seconds (avoid stale connections)",
    )

    # Redis
    redis_url: RedisDsn = Field(..., description="Redis connection URL")
    redis_session_db: int = Field(default=REDIS_SESSION_DB, description="Redis DB for sessions")
    redis_cache_db: int = Field(default=REDIS_CACHE_DB, description="Redis DB for cache")
    # Redis connection pool settings
    redis_max_connections: int = Field(
        default=REDIS_MAX_CONNECTIONS_DEFAULT,
        description="Max connections per Redis pool",
    )
    redis_socket_timeout: int = Field(
        default=REDIS_SOCKET_TIMEOUT_DEFAULT,
        description="Seconds before closing idle Redis connection",
    )
    redis_socket_connect_timeout: int = Field(
        default=REDIS_SOCKET_CONNECT_TIMEOUT_DEFAULT,
        description="Seconds to wait for Redis connection (fail-fast)",
    )
    redis_health_check_interval: int = Field(
        default=REDIS_HEALTH_CHECK_INTERVAL_DEFAULT,
        description="Seconds between Redis PING health checks",
    )

    # LLM Caching (Phase 3.2.8.2)
    llm_cache_enabled: bool = Field(
        default=True,
        description="Enable LLM response caching for Router and Planner (reduces latency and cost)",
    )
    llm_cache_ttl_seconds: int = Field(
        default=LLM_CACHE_TTL_SECONDS_DEFAULT,
        ge=60,
        le=3600,
        description="Cache TTL in seconds (default: 300 = 5 minutes)",
    )

    # Conversation ID Cache (PERF 2026-01-13)
    conversation_id_cache_ttl_seconds: int = Field(
        default=REDIS_CONVERSATION_ID_TTL_SECONDS_DEFAULT,
        ge=60,
        le=3600,
        description="Conversation ID cache TTL in seconds (avoids DB lookup per request)",
    )
