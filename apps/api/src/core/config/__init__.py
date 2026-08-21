"""
Main settings module with domain-specific composition.

This module uses constants from src.core.constants.py for default values.
Environment variables take precedence over these defaults.

Phase: PHASE 2.1 - Config Split
Created: 2025-11-20
Refactored: Monolithic config.py (1782 lines) → 7 domain modules
"""

import os
from enum import Enum
from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.core.constants import (
    DEFAULT_CURRENCY,
    HTTP_LOG_EXCLUDE_PATHS_DEFAULT,
    MULTIPART_ENVELOPE_OVERHEAD_BYTES,
    SESSION_COOKIE_SECURE_PRODUCTION,
    SUPPORTED_LANGUAGES,
)

from .account_export import AccountExportSettings
from .activity import ActivitySettings
from .adaptive import AdaptiveSettings
from .advanced import AdvancedSettings
from .agents import AgentsSettings
from .attachments import AttachmentsSettings
from .automation import AutomationSettings
from .background_runs import BackgroundRunsSettings
from .briefing import BriefingSettings
from .browser import BrowserSettings
from .channels import ChannelsSettings
from .connectors import ConnectorsSettings
from .database import DatabaseSettings
from .demo import DemoSettings
from .devops import DevOpsSettings
from .document_generation import DocumentGenerationSettings
from .habits import HabitsSettings
from .health_metrics import HealthMetricsSettings
from .image_generation import ImageGenerationSettings
from .journals import JournalsSettings
from .llm import (
    DEFAULT_CONTEXT_WINDOW,
    MODEL_CONTEXT_WINDOWS,
    LLMSettings,
    get_model_context_window,
)
from .locks import LocksSettings
from .mcp import MCPSettings
from .mfa import MFASettings
from .notifications import NotificationSettings
from .observability import ObservabilitySettings
from .open_loops import OpenLoopsSettings
from .peers import PeersSettings
from .plugins import PluginsSettings
from .product import ProductSettings
from .psyche import PsycheSettings
from .rag_spaces import RAGSpacesSettings
from .relations import RelationsSettings
from .scheduler import SchedulerSettings
from .security import SecuritySettings
from .skills import SkillsSettings
from .telephony import TelephonySettings
from .usage_limits import UsageLimitsSettings
from .voice import VoiceSettings


class SupportedCurrency(str, Enum):
    """
    Enum for supported currencies in cost tracking.

    Purpose:
        - Enforce strict validation at config level
        - Prevent unsupported currencies from being configured
        - Ensure Prometheus label cardinality stays low (<10)
        - Self-documenting API (IDE autocomplete)

    Usage:
        DEFAULT_CURRENCY=USD  # Valid
        DEFAULT_CURRENCY=EUR  # Valid
        DEFAULT_CURRENCY=GBP  # ValidationError: unsupported currency

    Context:
        RC2 - Misleading metric names (llm_cost_usd_total returns EUR)
        Solution: Enum validation + metric renaming with currency labels
    """

    USD = "USD"
    EUR = "EUR"


class Settings(
    SecuritySettings,
    AdaptiveSettings,
    DatabaseSettings,
    ObservabilitySettings,
    LLMSettings,
    AgentsSettings,
    ConnectorsSettings,
    AdvancedSettings,
    VoiceSettings,
    NotificationSettings,
    MCPSettings,
    ChannelsSettings,
    AttachmentsSettings,
    BriefingSettings,
    ActivitySettings,
    RAGSpacesSettings,
    RelationsSettings,
    SkillsSettings,
    PluginsSettings,
    BrowserSettings,
    JournalsSettings,
    PsycheSettings,
    UsageLimitsSettings,
    ImageGenerationSettings,
    DocumentGenerationSettings,
    DevOpsSettings,
    HealthMetricsSettings,
    AutomationSettings,
    HabitsSettings,
    OpenLoopsSettings,
    PeersSettings,
    SchedulerSettings,
    LocksSettings,
    BackgroundRunsSettings,
    TelephonySettings,
    MFASettings,
    AccountExportSettings,
    ProductSettings,
    DemoSettings,
    BaseSettings,
):
    """
    Main settings class combining all domain modules.

    Architecture:
        Uses multiple inheritance to compose domain-specific settings.
        Order matters for MRO (Method Resolution Order):
        1. SecuritySettings (environment, debug, API config, OAuth)
        2. DatabaseSettings (PostgreSQL, Redis, caching)
        3. ObservabilitySettings (OTEL, Prometheus, Langfuse)
        4. LLMSettings (provider configs, model settings)
        5. AgentsSettings (SSE, HITL, Router, Planner, Context)
        6. ConnectorsSettings (Google APIs, rate limiting, tools)
        7. AdvancedSettings (pricing, i18n, streaming, feature flags)
        8. VoiceSettings (TTS, voice comments)
        9. NotificationSettings (push notifications)
        10. MCPSettings (MCP external tool servers)
        11. ChannelsSettings (multi-channel messaging: Telegram, etc.)
        12. AttachmentsSettings (file uploads in chat: images, PDF)
        13. RAGSpacesSettings (user knowledge spaces: upload, embed, retrieve)
        14. SkillsSettings (Agent Skills: agentskills.io standard)
        14b. PluginsSettings (Agent Plugins: agent-plugins.org standard, ADR-225)
        15. BrowserSettings (Browser automation: Playwright/Chromium)
        16. JournalsSettings (Personal Journals: assistant logbooks)
        17. UsageLimitsSettings (Per-user usage limits: tokens, messages, cost)
        18. ImageGenerationSettings (AI image generation: gpt-image-1, multi-provider)
        19. DevOpsSettings (Claude CLI remote server management via SSH)
        20. HealthMetricsSettings (iPhone Shortcuts health metrics ingestion + visualization)
        21. SchedulerSettings (Background job scheduling, scheduled-actions executor)
        22. LocksSettings (Distributed locks: OAuth refresh)
        23. MFASettings (Strong authentication: WebAuthn passkeys, TOTP)
        24. AccountExportSettings (GDPR full-account export jobs)
        25. BaseSettings (Pydantic base class)

    All settings can be overridden via .env file or environment variables.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_parse_none_str="null",  # Parse 'null' string as None, not JSON
    )

    # ========================================================================
    # Additional Settings (not in domain modules)
    # ========================================================================
    default_currency: SupportedCurrency = Field(
        default=SupportedCurrency(DEFAULT_CURRENCY),
        description="Default currency for cost reporting (USD or EUR). Enum validation prevents unsupported currencies.",
    )

    # ========================================================================
    # Field Validators (from original config.py)
    # ========================================================================
    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> list[str]:
        """Parse CORS origins from string or list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        if isinstance(v, list):
            return v
        return []

    @field_validator("http_log_exclude_paths", mode="before")
    @classmethod
    def parse_http_log_exclude_paths(cls, v: Any) -> list[str]:
        """Parse HTTP log exclude paths from string or list."""
        # Handle None or empty string
        if v is None or v == "":
            return HTTP_LOG_EXCLUDE_PATHS_DEFAULT
        # Handle string (comma-separated)
        if isinstance(v, str):
            return [path.strip() for path in v.split(",") if path.strip()]
        # Handle list (already parsed)
        if isinstance(v, list):
            return v
        # Fallback to default
        return HTTP_LOG_EXCLUDE_PATHS_DEFAULT

    @field_validator("supported_languages", mode="before")
    @classmethod
    def parse_supported_languages(cls, v: Any) -> list[str]:
        """Parse supported languages from string or list."""
        if isinstance(v, str):
            return [lang.strip() for lang in v.split(",") if lang.strip()]
        if isinstance(v, list):
            return v
        return SUPPORTED_LANGUAGES  # Default fallback from constants

    @field_validator("session_cookie_secure", mode="before")
    @classmethod
    def auto_secure_in_production(cls, v: Any) -> bool:
        """
        Auto-enable secure cookies in production if not explicitly set.

        If SESSION_COOKIE_SECURE env var is explicitly set, respect that.
        Otherwise, use SESSION_COOKIE_SECURE_PRODUCTION constant for production envs.

        This ensures HTTPS-only cookies in production by default for security.
        """
        # If explicitly set via environment variable, respect that value
        if v is not None and not isinstance(v, bool):
            # Convert string to bool if needed
            if isinstance(v, str):
                return v.lower() in ("true", "1", "yes", "on")
            return bool(v)

        # If explicitly set as boolean, respect it
        if isinstance(v, bool):
            return v

        # Auto-configure based on environment
        # Note: We can't access self.environment here in mode="before"
        # So we check the environment directly from the context
        environment = os.getenv("ENVIRONMENT", "development").lower()

        if environment in ("production", "prod"):
            return SESSION_COOKIE_SECURE_PRODUCTION

        return False  # Default for dev/staging

    @field_validator("default_currency", mode="before")
    @classmethod
    def validate_currency(cls, v: str | SupportedCurrency) -> str:
        """
        Validate that the default currency is supported.

        Ensures only currencies defined in SUPPORTED_CURRENCIES can be used.
        This prevents configuration errors and ensures currency conversion works.

        Context:
            RC2 - Misleading metric naming (llm_cost_usd_total returns EUR)
            Enum validation prevents unsupported currencies at startup.
            Prometheus label cardinality stays low (<10 currencies).

        Args:
            v: Currency code (string "USD"/"EUR" or SupportedCurrency enum)

        Returns:
            Normalized uppercase currency string (Pydantic will convert to Enum)

        Raises:
            ValueError: If currency not in SupportedCurrency enum values
        """
        # Handle both string and enum inputs (backward compatibility)
        if isinstance(v, SupportedCurrency):
            return v.value

        # Normalize string input
        v_upper = v.upper() if isinstance(v, str) else str(v).upper()

        # Validate against enum values
        valid_currencies = [c.value for c in SupportedCurrency]
        if v_upper not in valid_currencies:
            raise ValueError(
                f"Unsupported currency: {v}. "
                f"Must be one of {valid_currencies}. "
                f"See .env.example for reference."
            )

        return v_upper

    @field_validator("router_confidence_high")
    @classmethod
    def _validate_router_confidence_high(cls, v: float, info: Any) -> float:
        """Validate high confidence threshold is greater than medium."""
        if "router_confidence_medium" in info.data:
            medium = info.data["router_confidence_medium"]
            if v <= medium:
                raise ValueError(
                    f"router_confidence_high ({v}) must be > router_confidence_medium ({medium})"
                )
        return v

    @field_validator("router_confidence_medium")
    @classmethod
    def _validate_router_confidence_medium(cls, v: float, info: Any) -> float:
        """Validate medium confidence threshold is between low and high."""
        if "router_confidence_low" in info.data:
            low = info.data["router_confidence_low"]
            if v <= low:
                raise ValueError(
                    f"router_confidence_medium ({v}) must be > router_confidence_low ({low})"
                )
        return v

    @field_validator("planner_llm_max_tokens")
    @classmethod
    def _validate_planner_max_tokens(cls, v: int) -> int:
        """Validate planner max tokens is reasonable (> 0 and < 100k)."""
        if v <= 0:
            raise ValueError(f"planner_llm_max_tokens must be > 0, got {v}")
        if v > 100000:
            raise ValueError(f"planner_llm_max_tokens too high ({v}), max recommended: 100000")
        return v

    @field_validator("database_pool_size", "database_max_overflow")
    @classmethod
    def _validate_pool_size(cls, v: int, info: Any) -> int:
        """Validate database pool sizes are positive."""
        field_name = info.field_name
        if v < 1:
            raise ValueError(f"{field_name} must be >= 1, got {v}")
        if v > 100:
            raise ValueError(
                f"{field_name} too high ({v}), max recommended: 100 for production safety"
            )
        return v

    @model_validator(mode="after")
    def _validate_body_ceiling_covers_uploads(self) -> Settings:
        """Refuse to boot when the global body cap is below a legitimate upload.

        ``BodySizeLimitMiddleware`` (SEC-031) runs BEFORE any handler, so a cap
        smaller than an endpoint's own ceiling turns a valid upload into a 413
        that no endpoint log explains. Both upload ceilings are configurable up
        to 100 MB while the cap defaults to 21 MB — raising one without the
        other is a silent, remote-only breakage. Failing here makes the
        contradiction impossible to ship.

        Returns:
            The validated settings instance.

        Raises:
            ValueError: The cap cannot carry the largest configured upload.
        """
        largest_upload_mb = max(
            self.attachments_max_doc_size_mb,
            self.attachments_max_image_size_mb,
            self.rag_spaces_max_file_size_mb,
        )
        required = largest_upload_mb * 1024 * 1024 + MULTIPART_ENVELOPE_OVERHEAD_BYTES
        if self.max_request_body_bytes < required:
            raise ValueError(
                "max_request_body_bytes "
                f"({self.max_request_body_bytes}) is below the largest configured "
                f"upload ({largest_upload_mb} MB + multipart envelope = {required} "
                "bytes): raise MAX_REQUEST_BODY_BYTES or lower the upload ceilings."
            )
        return self

    # ========================================================================
    # Properties (from original config.py)
    # ========================================================================
    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment.lower() in ("production", "prod")

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment.lower() in ("development", "dev")

    @property
    def database_url_sync(self) -> str:
        """
        Get synchronous database URL (for Alembic migrations).
        Uses psycopg (v3) synchronous driver instead of asyncpg.
        """
        return str(self.database_url).replace("+asyncpg", "+psycopg")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Global settings instance
settings = get_settings()


__all__ = [
    "Settings",
    "SupportedCurrency",
    "get_settings",
    "settings",
    # Domain modules
    "SecuritySettings",
    "DatabaseSettings",
    "ObservabilitySettings",
    "LLMSettings",
    "AgentsSettings",
    "ConnectorsSettings",
    "AdvancedSettings",
    "VoiceSettings",
    "NotificationSettings",
    "MCPSettings",
    "ChannelsSettings",
    "AttachmentsSettings",
    "PluginsSettings",
    "SkillsSettings",
    "ActivitySettings",
    "RAGSpacesSettings",
    "BrowserSettings",
    "JournalsSettings",
    "UsageLimitsSettings",
    "ImageGenerationSettings",
    "DevOpsSettings",
    "HealthMetricsSettings",
    "SchedulerSettings",
    "LocksSettings",
    "MFASettings",
    "AccountExportSettings",
]
