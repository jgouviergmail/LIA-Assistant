"""
Security configuration module.

Contains settings for:
- Environment and debugging
- HTTP logging
- API configuration (CORS, host, port)
- JWT and encryption (secret keys, algorithms)
- Session cookies (BFF Pattern)
- OAuth (Google, Microsoft)
- Email/SMTP

Phase: PHASE 2.1 - Config Split
Created: 2025-11-20
"""

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    API_PREFIX_DEFAULT,
    HTTP_LOG_EXCLUDE_PATHS_DEFAULT,
    HTTP_LOG_LEVEL_DEFAULT,
    JWT_ALGORITHM_DEFAULT,
    LOG_LEVEL_DEFAULT,
    RATE_LIMIT_BURST_DEFAULT,
    RATE_LIMIT_PER_MINUTE_DEFAULT,
    SECRET_KEY_MIN_LENGTH,
    SESSION_COOKIE_NAME,
    SESSION_DURATION_DEFAULT,
    SESSION_DURATION_REMEMBER_ME,
)


class SecuritySettings(BaseSettings):
    """Security and authentication settings."""

    # Environment
    environment: str = Field(default="development", description="Environment name")
    debug: bool = Field(default=False, description="Debug mode")
    log_level: str = Field(default=LOG_LEVEL_DEFAULT, description="Logging level")

    # HTTP request logging configuration
    http_log_level: str = Field(
        default=HTTP_LOG_LEVEL_DEFAULT,
        description="Log level for HTTP requests/responses (DEBUG = minimal, INFO = verbose)",
    )
    http_log_exclude_paths: str | list[str] = Field(
        default=",".join(HTTP_LOG_EXCLUDE_PATHS_DEFAULT),
        description="Paths to exclude from HTTP request logging (e.g., /metrics, /health)",
    )

    # Third-party library log levels
    log_level_httpx: str = Field(
        default="WARNING",
        description="Log level for httpx library (OpenAI API calls). Use DEBUG to see all HTTP requests.",
    )
    log_level_sqlalchemy: str = Field(
        default="WARNING",
        description="Log level for SQLAlchemy engine. Use INFO to see SQL queries.",
    )
    log_level_uvicorn: str = Field(
        default="WARNING",
        description="Log level for Uvicorn server.",
    )
    log_level_uvicorn_access: str = Field(
        default="WARNING",
        description="Log level for Uvicorn access logs.",
    )

    # API Configuration
    api_host: str = Field(default="0.0.0.0", description="API host")
    api_port: int = Field(default=8000, description="API port")
    api_prefix: str = Field(default=API_PREFIX_DEFAULT, description="API URL prefix")
    cors_origins: str | list[str] = Field(
        default="http://localhost:3000",
        description="CORS allowed origins (comma-separated or list)",
    )

    # HTTP Rate Limiting (SlowAPI - FastAPI Endpoints)
    rate_limit_per_minute: int = Field(
        default=RATE_LIMIT_PER_MINUTE_DEFAULT,
        gt=0,
        description="Default HTTP rate limit (requests per minute per IP)",
    )
    rate_limit_burst: int = Field(
        default=RATE_LIMIT_BURST_DEFAULT,
        gt=0,
        description="Burst allowance for rate limiting",
    )

    # Security
    secret_key: str = Field(
        ...,
        min_length=SECRET_KEY_MIN_LENGTH,
        description="Secret key for token signing (email verification, password reset)",
    )
    algorithm: str = Field(
        default=JWT_ALGORITHM_DEFAULT,
        description="JWT algorithm for email verification and password reset tokens",
    )
    fernet_key: str = Field(
        ...,
        description="Fernet encryption key for sensitive data",
    )

    # Session Cookies (BFF Pattern)
    session_cookie_name: str = Field(
        default=SESSION_COOKIE_NAME,
        description="Name of the session cookie",
    )
    session_cookie_max_age: int = Field(
        default=SESSION_DURATION_DEFAULT,
        description="Session cookie max age in seconds (default, no remember me)",
    )
    session_cookie_max_age_remember: int = Field(
        default=SESSION_DURATION_REMEMBER_ME,
        description="Session cookie max age in seconds (remember me enabled)",
    )
    session_cookie_secure: bool = Field(
        default=False,  # Set to True in production with HTTPS
        description="Require HTTPS for session cookie",
    )
    session_cookie_httponly: bool = Field(
        default=True,
        description="HTTP-only flag for session cookie (prevents XSS)",
    )
    session_cookie_samesite: str = Field(
        default="lax",
        description="SameSite policy for session cookie (strict/lax/none)",
    )
    session_cookie_domain: str | None = Field(
        default=None,
        description="Domain for session cookie (None = current domain only)",
    )

    # Frontend URL for redirects (BFF Pattern)
    frontend_url: str = Field(
        default="http://localhost:3000",
        description="Frontend application URL for OAuth redirects",
    )

    # API URL for OAuth callbacks
    api_url: str = Field(
        default="http://localhost:8000",
        description="API base URL for OAuth callback endpoints",
    )

    # OAuth Google
    google_client_id: str = Field(default="", description="Google OAuth client ID")
    google_client_secret: str = Field(default="", description="Google OAuth client secret")
    google_redirect_uri: str = Field(default="", description="Google OAuth redirect URI")

    # OAuth Microsoft 365 (Entra ID / Azure AD)
    microsoft_client_id: str = Field(default="", description="Microsoft Entra ID client ID")
    microsoft_client_secret: str = Field(default="", description="Microsoft Entra ID client secret")
    microsoft_tenant_id: str = Field(
        default="common",
        description="Microsoft tenant ID ('common' = multi-tenant personal + enterprise)",
    )

    # Email (SMTP) - Unified configuration using AlertManager SMTP settings
    # Application emails use APPLICATION_SMTP_FROM for user-facing notifications
    # Monitoring alerts use ALERTMANAGER_SMTP_FROM (configured in docker-compose)
    # Note: Both use the same SMTP server but different sender addresses
    alertmanager_smtp_smarthost: str = Field(
        default="localhost:587",
        description="SMTP server (format: host:port, e.g., smtp.gmail.com:587)",
    )
    alertmanager_smtp_auth_username: str = Field(
        default="",
        description="SMTP authentication username",
    )
    alertmanager_smtp_auth_password: str = Field(
        default="",
        description="SMTP authentication password",
    )
    application_smtp_from: str = Field(
        default="noreply@lia-assistant.com",
        description="Application email sender address for user-facing notifications",
    )

    # Properties for backward compatibility with EmailService
    @property
    def smtp_host(self) -> str:
        """Extract host from smarthost (e.g., 'smtp.gmail.com:587' -> 'smtp.gmail.com')"""
        return self.alertmanager_smtp_smarthost.split(":")[0]

    @property
    def smtp_port(self) -> int:
        """Extract port from smarthost (e.g., 'smtp.gmail.com:587' -> 587)"""
        parts = self.alertmanager_smtp_smarthost.split(":")
        return int(parts[1]) if len(parts) > 1 else 587

    @property
    def smtp_user(self) -> str:
        """Alias for alertmanager_smtp_auth_username"""
        return self.alertmanager_smtp_auth_username

    @property
    def smtp_password(self) -> str:
        """Alias for alertmanager_smtp_auth_password"""
        return self.alertmanager_smtp_auth_password

    @property
    def smtp_from(self) -> str:
        """Alias for application_smtp_from"""
        return self.application_smtp_from
