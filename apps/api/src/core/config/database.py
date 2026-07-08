"""
Database configuration module.

Contains settings for:
- PostgreSQL (connection URL, pool size)
- Redis (connection URL, session/cache DBs)
- LLM caching configuration

Phase: PHASE 2.1 - Config Split
Created: 2025-11-20
"""

from pydantic import Field, PostgresDsn, RedisDsn, ValidationInfo, field_validator
from pydantic_settings import BaseSettings

from src.core.constants import (
    DATABASE_MAX_OVERFLOW_DEFAULT,
    DATABASE_POOL_RECYCLE_DEFAULT,
    DATABASE_POOL_SIZE_DEFAULT,
    DATABASE_POOL_TIMEOUT_DEFAULT,
    LANGGRAPH_CHECKPOINT_POOL_MAX_SIZE_DEFAULT,
    LANGGRAPH_CHECKPOINT_POOL_MIN_SIZE_DEFAULT,
    LANGGRAPH_STORE_POOL_MAX_SIZE_DEFAULT,
    LANGGRAPH_STORE_POOL_MIN_SIZE_DEFAULT,
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

    # LangGraph PostgreSQL pools (checkpointer + store, per worker — ADR-111).
    # Sizing rationale and the global connection budget vs postgres
    # max_connections live next to the defaults in src/core/constants.py.
    langgraph_checkpoint_pool_min_size: int = Field(
        default=LANGGRAPH_CHECKPOINT_POOL_MIN_SIZE_DEFAULT,
        ge=1,
        le=100,
        description="Persistent connections of the LangGraph checkpointer pool (per worker)",
    )
    langgraph_checkpoint_pool_max_size: int = Field(
        default=LANGGRAPH_CHECKPOINT_POOL_MAX_SIZE_DEFAULT,
        ge=1,
        le=100,
        description=(
            "Max connections of the LangGraph checkpointer pool (per worker); "
            "1 reproduces the former fully-serialized single-connection behavior"
        ),
    )
    langgraph_store_pool_min_size: int = Field(
        default=LANGGRAPH_STORE_POOL_MIN_SIZE_DEFAULT,
        ge=1,
        le=100,
        description="Persistent connections of the LangGraph store pool (per worker)",
    )
    langgraph_store_pool_max_size: int = Field(
        default=LANGGRAPH_STORE_POOL_MAX_SIZE_DEFAULT,
        ge=1,
        le=100,
        description="Max connections of the LangGraph store pool (per worker)",
    )

    @field_validator("langgraph_checkpoint_pool_max_size", "langgraph_store_pool_max_size")
    @classmethod
    def _validate_langgraph_pool_max_ge_min(cls, v: int, info: ValidationInfo) -> int:
        """Validate that each LangGraph pool max_size is >= its min_size.

        Args:
            v: The max_size value being validated.
            info: Validation context exposing already-validated fields.

        Returns:
            The validated max_size value.

        Raises:
            ValueError: If max_size is lower than the matching min_size.
        """
        min_field = str(info.field_name).replace("_max_size", "_min_size")
        min_value = info.data.get(min_field)
        if min_value is not None and v < min_value:
            raise ValueError(f"{info.field_name} ({v}) must be >= {min_field} ({min_value})")
        return v

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
