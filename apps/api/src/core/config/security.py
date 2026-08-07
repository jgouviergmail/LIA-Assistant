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

import base64
import binascii

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

from src.core.constants import (
    API_PREFIX_DEFAULT,
    HSTS_MAX_AGE_SECONDS_DEFAULT,
    HTTP_LOG_EXCLUDE_PATHS_DEFAULT,
    HTTP_LOG_LEVEL_DEFAULT,
    JWT_ALGORITHM_DEFAULT,
    LOG_LEVEL_DEFAULT,
    MAX_REQUEST_BODY_BYTES_DEFAULT,
    RATE_LIMIT_BURST_DEFAULT,
    RATE_LIMIT_GLOBAL_PER_MINUTE_DEFAULT,
    RATE_LIMIT_PER_MINUTE_DEFAULT,
    SECRET_KEY_MIN_LENGTH,
    SESSION_COOKIE_NAME,
    SESSION_DURATION_DEFAULT,
    SESSION_DURATION_REMEMBER_ME,
    JwtAlgorithm,
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
        default="ERROR",
        description="Log level for httpx library (OpenAI API calls). Use DEBUG to see all HTTP requests.",
    )
    log_level_sqlalchemy: str = Field(
        default="ERROR",
        description="Log level for SQLAlchemy engine. Use INFO to see SQL queries.",
    )
    log_level_uvicorn: str = Field(
        default="ERROR",
        description="Log level for Uvicorn server.",
    )
    log_level_uvicorn_access: str = Field(
        default="ERROR",
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

    hsts_max_age: int = Field(
        default=HSTS_MAX_AGE_SECONDS_DEFAULT,
        ge=0,
        description=(
            "SEC-025. `Strict-Transport-Security` max-age in seconds, emitted in "
            "production only. Raised in steps because a browser cannot be told to "
            "forget the pin early. Same ladder as the web app's HSTS_MAX_AGE — "
            "one variable so the two surfaces cannot drift apart. 0 disables the "
            "header, which exists as an escape hatch, not as a target."
        ),
    )

    rate_limit_global_per_minute: int = Field(
        default=RATE_LIMIT_GLOBAL_PER_MINUTE_DEFAULT,
        ge=1,
        description=(
            "SEC-016. Requests per minute per client for the globally enforced "
            "rate limit (RateLimitMiddleware, Redis-backed). A flood backstop: "
            "the specialised per-endpoint limiters stay stricter. Sized well above "
            "a real session — one measured at 67 req/min on a single page — so it "
            "never fires on legitimate use."
        ),
    )

    max_request_body_bytes: int = Field(
        default=MAX_REQUEST_BODY_BYTES_DEFAULT,
        ge=1024,
        description=(
            "Global ceiling on an HTTP request body, in bytes (SEC-031). A memory "
            "bound applied by BodySizeLimitMiddleware before any handler runs; "
            "per-endpoint limits stay in place and are stricter. Must remain above "
            "the largest legitimate upload (RAG document + multipart envelope)."
        ),
    )

    # HTTP Rate Limiting (RateLimitMiddleware + per-endpoint limiters)
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
    algorithm: JwtAlgorithm = Field(
        default=JWT_ALGORITHM_DEFAULT,
        description=(
            "JWT algorithm for email verification and password reset tokens. "
            "HMAC only — an EC/RSA value would route python-jose through its "
            "vulnerable ecdsa backend (CVE-2024-23342, exempted in CI on the "
            "strength of this constraint) and would not accept `secret_key` "
            "as a signing key."
        ),
    )
    fernet_key: str = Field(
        ...,
        description="Fernet encryption key for sensitive data",
    )

    @field_validator("fernet_key")
    @classmethod
    def _fernet_key_structure(cls, value: str) -> str:
        """Require a URL-safe base64-encoded 32-byte Fernet key (B07).

        A malformed key otherwise survives every pre-start check and only
        explodes on the first encryption call, deep inside a request.

        Args:
            value: Candidate key from the environment.

        Returns:
            The original string when structurally valid.

        Raises:
            ValueError: On any structural mismatch (never echoes the value).
        """
        error = "must be a URL-safe base64-encoded 32-byte Fernet key"
        try:
            encoded = value.encode("ascii")
        except UnicodeEncodeError as exc:
            raise ValueError(error) from exc
        if len(encoded) != 44:
            raise ValueError(error)
        try:
            decoded = base64.b64decode(encoded, altchars=b"-_", validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError(error) from exc
        if len(decoded) != 32:
            raise ValueError(error)
        return value

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
        # None = "not explicitly set": the auto_secure_in_production validator
        # (validate_default=True) resolves it to True in production and False in
        # dev/staging. A hard default of True here would bypass that env-based intent.
        default=None,
        validate_default=True,
        description="Require HTTPS for session cookie (auto: True in production)",
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
        # None, and never a real domain. This is deployment IDENTITY, not a
        # tuned value: a hard-coded domain makes the cookie unusable on every
        # other host — a fresh clone cannot even sign in, since the browser
        # drops a cookie whose Domain does not match. It also widens the
        # cookie's reach: a parent domain (".example.com") is shared with
        # every sibling host, so a throwaway public demonstrator would hand
        # its sessions to the main instance and back.
        #
        # Set it per deployment in the env file, host by host.
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
