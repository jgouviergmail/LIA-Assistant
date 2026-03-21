"""
Connectors configuration module.

Contains settings for:
- Connector Cache TTL configuration
- Google Contacts Cache TTLs (granular)
- HTTP Client Timeouts
- Tool Rate Limiting
- Contacts Tools Configuration
- Emails Tools Configuration
- Global API Security Limits
- Gmail Configuration

Phase: PHASE 2.1 - Config Split
Created: 2025-11-20
"""

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    BRAVE_SEARCH_CACHE_TTL,
    CALENDAR_CACHE_DETAILS_TTL,
    CALENDAR_CACHE_LIST_TTL,
    CALENDAR_CACHE_SEARCH_TTL,
    DRIVE_CACHE_DETAILS_TTL,
    DRIVE_CACHE_LIST_TTL,
    DRIVE_CACHE_SEARCH_TTL,
    EMAILS_BODY_MAX_LENGTH_DEFAULT,
    EMAILS_CACHE_DETAILS_TTL_SECONDS,
    EMAILS_CACHE_LIST_TTL_SECONDS,
    EMAILS_CACHE_SEARCH_TTL_SECONDS,
    EMAILS_URL_SHORTEN_THRESHOLD_DEFAULT,
    GMAIL_DEFAULT_SEARCH_DAYS,
    GOOGLE_CONTACTS_DETAILS_CACHE_TTL,
    GOOGLE_CONTACTS_LIST_CACHE_TTL,
    GOOGLE_CONTACTS_SEARCH_CACHE_TTL,
    HTTP_TIMEOUT_CURRENCY_API,
    HTTP_TIMEOUT_EXTERNAL_API,
    HTTP_TIMEOUT_GEOCODING_API,
    HTTP_TIMEOUT_HUE_API,
    HTTP_TIMEOUT_OAUTH,
    HTTP_TIMEOUT_PLACES_API,
    HTTP_TIMEOUT_ROUTES_API,
    HTTP_TIMEOUT_TOKEN,
    HUE_DEFAULT_RATE_LIMIT_PER_SECOND,
    INTEREST_PERPLEXITY_RECENCY_FILTER_DEFAULT,
    INTEREST_PERPLEXITY_RETURN_RELATED_QUESTIONS_DEFAULT,
    INTEREST_WIKIPEDIA_SEARCH_LIMIT_DEFAULT,
    OAUTH_HEALTH_CHECK_INTERVAL_MINUTES_DEFAULT,
    OAUTH_HEALTH_CRITICAL_COOLDOWN_HOURS_DEFAULT,
    OAUTH_PROACTIVE_REFRESH_INTERVAL_MINUTES,
    OAUTH_PROACTIVE_REFRESH_MARGIN_SECONDS,
    ROUTES_CACHE_MATRIX_TTL,
    ROUTES_CACHE_STATIC_TTL,
    ROUTES_CACHE_TRAFFIC_TTL,
    ROUTES_HITL_DISTANCE_THRESHOLD_KM,
    ROUTES_MAX_MATRIX_ELEMENTS,
    ROUTES_MAX_STEPS,
    ROUTES_MAX_WAYPOINTS,
    ROUTES_WALK_THRESHOLD_KM,
    SSE_CONNECTION_TTL_SECONDS_DEFAULT,
    TASKS_CACHE_DETAILS_TTL,
    TASKS_CACHE_LIST_TTL,
    WEATHER_CACHE_CURRENT_TTL,
    WEATHER_CACHE_FORECAST_TTL,
    WEATHER_FORECAST_MAX_DAYS,
    WIKIPEDIA_CACHE_ARTICLE_TTL,
    WIKIPEDIA_CACHE_SEARCH_TTL,
    WIKIPEDIA_SUMMARY_MAX_CHARS,
)


class ConnectorsSettings(BaseSettings):
    """External connectors and integrations settings."""

    # ========================================================================
    # Cache TTL Configuration - Calendar (granular)
    # ========================================================================
    calendar_cache_list_ttl_seconds: int = Field(
        default=CALENDAR_CACHE_LIST_TTL,
        gt=0,
        description="Cache TTL for calendar event lists (seconds, default: 1 minute - volatile)",
    )
    calendar_cache_search_ttl_seconds: int = Field(
        default=CALENDAR_CACHE_SEARCH_TTL,
        gt=0,
        description="Cache TTL for calendar search results (seconds, default: 1 minute - volatile)",
    )
    calendar_cache_details_ttl_seconds: int = Field(
        default=CALENDAR_CACHE_DETAILS_TTL,
        gt=0,
        description="Cache TTL for calendar event details (seconds, default: 2 minutes - moderate)",
    )

    # ========================================================================
    # Cache TTL Configuration - Drive (granular)
    # ========================================================================
    drive_cache_list_ttl_seconds: int = Field(
        default=DRIVE_CACHE_LIST_TTL,
        gt=0,
        description="Cache TTL for Drive file lists (seconds, default: 1 minute - volatile)",
    )
    drive_cache_search_ttl_seconds: int = Field(
        default=DRIVE_CACHE_SEARCH_TTL,
        gt=0,
        description="Cache TTL for Drive search results (seconds, default: 1 minute - volatile)",
    )
    drive_cache_details_ttl_seconds: int = Field(
        default=DRIVE_CACHE_DETAILS_TTL,
        gt=0,
        description="Cache TTL for Drive file details (seconds, default: 5 minutes - stable metadata)",
    )

    # ========================================================================
    # Cache TTL Configuration - Tasks (granular)
    # ========================================================================
    tasks_cache_list_ttl_seconds: int = Field(
        default=TASKS_CACHE_LIST_TTL,
        gt=0,
        description="Cache TTL for task lists (seconds, default: 1 minute - volatile)",
    )
    tasks_cache_details_ttl_seconds: int = Field(
        default=TASKS_CACHE_DETAILS_TTL,
        gt=0,
        description="Cache TTL for task details (seconds, default: 2 minutes - moderate)",
    )

    # ========================================================================
    # Cache TTL Configuration - Weather (granular)
    # ========================================================================
    weather_cache_current_ttl_seconds: int = Field(
        default=WEATHER_CACHE_CURRENT_TTL,
        gt=0,
        description="Cache TTL for current weather data (seconds, default: 10 minutes)",
    )
    weather_cache_forecast_ttl_seconds: int = Field(
        default=WEATHER_CACHE_FORECAST_TTL,
        gt=0,
        description="Cache TTL for weather forecast data (seconds, default: 30 minutes)",
    )
    weather_forecast_max_days: int = Field(
        default=WEATHER_FORECAST_MAX_DAYS,
        ge=1,
        le=16,
        description="Maximum days for weather forecast (OpenWeatherMap free tier: 5, paid: up to 16)",
    )

    # ========================================================================
    # Cache TTL Configuration - Wikipedia (granular)
    # ========================================================================
    wikipedia_cache_search_ttl_seconds: int = Field(
        default=WIKIPEDIA_CACHE_SEARCH_TTL,
        gt=0,
        description="Cache TTL for Wikipedia search results (seconds, default: 1 hour - static)",
    )
    wikipedia_cache_article_ttl_seconds: int = Field(
        default=WIKIPEDIA_CACHE_ARTICLE_TTL,
        gt=0,
        description="Cache TTL for Wikipedia articles (seconds, default: 24 hours - very stable)",
    )
    wikipedia_summary_max_chars: int = Field(
        default=WIKIPEDIA_SUMMARY_MAX_CHARS,
        gt=0,
        description="Maximum characters for Wikipedia article summaries in display/LLM context (default: 5000)",
    )

    # Interest content generation - Wikipedia settings
    interest_wikipedia_search_limit: int = Field(
        default=INTEREST_WIKIPEDIA_SEARCH_LIMIT_DEFAULT,
        ge=1,
        le=10,
        description="Max Wikipedia search results for interest content generation (default: 3)",
    )

    # Interest content generation - Perplexity settings
    interest_perplexity_recency_filter: str = Field(
        default=INTEREST_PERPLEXITY_RECENCY_FILTER_DEFAULT,
        description="Perplexity recency filter for interest content: day, week, month, year (default: week)",
    )
    interest_perplexity_return_related_questions: bool = Field(
        default=INTEREST_PERPLEXITY_RETURN_RELATED_QUESTIONS_DEFAULT,
        description="Include related questions in Perplexity response for interests (default: False)",
    )

    # ========================================================================
    # Cache TTL Configuration - Routes (Google Routes API)
    # ========================================================================
    routes_cache_traffic_ttl_seconds: int = Field(
        default=ROUTES_CACHE_TRAFFIC_TTL,
        gt=0,
        description="Cache TTL for routes with traffic (seconds, default: 5 minutes - volatile)",
    )
    routes_cache_static_ttl_seconds: int = Field(
        default=ROUTES_CACHE_STATIC_TTL,
        gt=0,
        description="Cache TTL for routes without traffic (seconds, default: 30 minutes - stable)",
    )
    routes_cache_matrix_ttl_seconds: int = Field(
        default=ROUTES_CACHE_MATRIX_TTL,
        gt=0,
        description="Cache TTL for route matrix (seconds, default: 10 minutes - moderately stable)",
    )

    # Routes Tool Configuration
    routes_max_waypoints: int = Field(
        default=ROUTES_MAX_WAYPOINTS,
        gt=0,
        le=25,
        description="Maximum waypoints per route request (Google API limit: 25)",
    )
    routes_max_matrix_elements: int = Field(
        default=ROUTES_MAX_MATRIX_ELEMENTS,
        gt=0,
        le=625,
        description="Maximum matrix elements (origins x destinations, limit: 625 = 25x25)",
    )
    routes_walk_threshold_km: float = Field(
        default=ROUTES_WALK_THRESHOLD_KM,
        gt=0,
        description="Distance threshold below which WALK mode is default (km)",
    )
    routes_hitl_distance_threshold_km: float = Field(
        default=ROUTES_HITL_DISTANCE_THRESHOLD_KM,
        gt=0,
        description="Distance threshold above which HITL confirmation is triggered (km)",
    )
    routes_max_steps: int = Field(
        default=ROUTES_MAX_STEPS,
        gt=0,
        le=50,
        description="Maximum number of steps in condensed route response (default: 10)",
    )

    # ========================================================================
    # Cache TTL Configuration - Contacts (uses centralized constants)
    # ========================================================================
    contacts_cache_list_ttl_seconds: int = Field(
        default=GOOGLE_CONTACTS_LIST_CACHE_TTL,
        gt=0,
        description="Cache TTL for contact list operations (seconds, default: 5 minutes)",
    )
    contacts_cache_search_ttl_seconds: int = Field(
        default=GOOGLE_CONTACTS_SEARCH_CACHE_TTL,
        gt=0,
        description="Cache TTL for contact search operations (seconds, default: 3 minutes)",
    )
    contacts_cache_details_ttl_seconds: int = Field(
        default=GOOGLE_CONTACTS_DETAILS_CACHE_TTL,
        gt=0,
        description="Cache TTL for contact details operations (seconds, default: 10 minutes - stable data)",
    )

    # ========================================================================
    # Cache TTL Configuration - Emails
    # ========================================================================
    emails_cache_list_ttl_seconds: int = Field(
        default=EMAILS_CACHE_LIST_TTL_SECONDS,
        gt=0,
        description="Cache TTL for email list operations (seconds, default: 1 minute)",
    )
    emails_cache_search_ttl_seconds: int = Field(
        default=EMAILS_CACHE_SEARCH_TTL_SECONDS,
        gt=0,
        description="Cache TTL for email search operations (seconds, default: 1 minute)",
    )
    emails_cache_details_ttl_seconds: int = Field(
        default=EMAILS_CACHE_DETAILS_TTL_SECONDS,
        gt=0,
        description="Cache TTL for email details/message operations (seconds, default: 5 minutes - stable data)",
    )

    # ========================================================================
    # HTTP Client Timeouts (external requests)
    # ========================================================================
    http_timeout_oauth: float = Field(
        default=HTTP_TIMEOUT_OAUTH,
        gt=0.0,
        description="Timeout for OAuth authorization requests (seconds)",
    )
    http_timeout_token: float = Field(
        default=HTTP_TIMEOUT_TOKEN,
        gt=0.0,
        description="Timeout for token exchange endpoint (seconds)",
    )
    http_timeout_external_api: float = Field(
        default=HTTP_TIMEOUT_EXTERNAL_API,
        gt=0.0,
        description="Timeout for generic external API calls (seconds)",
    )
    http_timeout_currency_api: float = Field(
        default=HTTP_TIMEOUT_CURRENCY_API,
        gt=0.0,
        description="Timeout for currency exchange rate API (seconds)",
    )
    http_timeout_routes_api: float = Field(
        default=HTTP_TIMEOUT_ROUTES_API,
        gt=0.0,
        description="Timeout for Google Routes API (seconds, default: 30s)",
    )
    http_timeout_places_api: float = Field(
        default=HTTP_TIMEOUT_PLACES_API,
        gt=0.0,
        description="Timeout for Google Places API (seconds, default: 10s)",
    )
    http_timeout_geocoding_api: float = Field(
        default=HTTP_TIMEOUT_GEOCODING_API,
        gt=0.0,
        description="Timeout for Google Geocoding API (seconds, default: 5s)",
    )

    # ========================================================================
    # Global Rate Limiting
    # ========================================================================
    rate_limit_enabled: bool = Field(
        default=True,
        description="Enable rate limiting globally (affects tools AND API clients)",
    )
    rate_limit_scope: str = Field(
        default="user",
        description="Rate limit scope: 'user' (per-user isolation) or 'global' (shared)",
    )

    # ========================================================================
    # API Client Rate Limits (Redis-based, for external API calls)
    # ========================================================================
    # These control how fast clients can make requests to external APIs (Google, etc.)
    # Uses Redis sliding window for distributed rate limiting (horizontal scaling)
    # Falls back to local rate limiting if Redis unavailable
    client_rate_limit_google_per_second: int = Field(
        default=10,
        gt=0,
        description="Google APIs: max requests per second per user (default: 10)",
    )
    client_rate_limit_perplexity_per_second: float = Field(
        default=2.0,
        gt=0,
        description="Perplexity API: max requests per second per user (default: 2)",
    )
    perplexity_search_model: str = Field(
        default="sonar",
        description="Perplexity API search model (sonar, sonar-pro, sonar-reasoning)",
    )
    # Brave Search API (user connector - API key per user, like Perplexity)
    # Note: No global API key - each user configures their own via connector settings
    client_rate_limit_brave_search_per_second: float = Field(
        default=20.0,
        gt=0.1,
        le=100.0,
        description="Brave Search API: max requests per second per user (default: 20)",
    )
    brave_search_cache_ttl_seconds: int = Field(
        default=BRAVE_SEARCH_CACHE_TTL,
        ge=60,
        le=86400,
        description="Cache TTL for Brave Search knowledge enrichment results (seconds, default: 1 hour)",
    )
    client_rate_limit_microsoft_per_second: int = Field(
        default=4,
        gt=0,
        description="Microsoft Graph API: max requests per second per user (default: 4)",
    )
    client_rate_limit_openweathermap_per_second: int = Field(
        default=1,
        gt=0,
        description="OpenWeatherMap API: max requests per second per user (default: 1, free tier)",
    )
    client_rate_limit_wikipedia_per_second: float = Field(
        default=0.5,
        gt=0,
        description="Wikipedia API: max requests per second per user (default: 0.5, conservative)",
    )

    # ========================================================================
    # Tool Rate Limiting (per-user protection against tool abuse)
    # ========================================================================
    # These control how many times a user can invoke specific agent tools
    # All tools use these default limits based on operation type (read/write/expensive)

    # ========================================================================
    # Default Rate Limits (applies to ALL tools: Contacts, Gmail, Calendar, etc.)
    # ========================================================================
    rate_limit_default_read_calls: int = Field(
        default=20,
        gt=0,
        description="Default max calls for read operations (search, list, get) per window",
    )
    rate_limit_default_read_window: int = Field(
        default=60,
        gt=0,
        description="Default time window for read operations (seconds)",
    )
    rate_limit_default_write_calls: int = Field(
        default=5,
        gt=0,
        description="Default max calls for write operations (create, update, delete, send) per window",
    )
    rate_limit_default_write_window: int = Field(
        default=60,
        gt=0,
        description="Default time window for write operations (seconds)",
    )
    rate_limit_default_expensive_calls: int = Field(
        default=2,
        gt=0,
        description="Default max calls for expensive operations (export, bulk) per window",
    )
    rate_limit_default_expensive_window: int = Field(
        default=300,
        gt=0,
        description="Default time window for expensive operations (seconds, default: 5 minutes)",
    )

    # ========================================================================
    # Contacts Tools Configuration
    # ========================================================================
    contacts_tool_default_max_results: int = Field(
        default=10,
        gt=0,
        description="Default max results for contact search operations",
    )
    contacts_tool_default_limit: int = Field(
        default=10,
        gt=0,
        description="Default limit for contact list operations",
    )
    calendar_tool_default_max_results: int = Field(
        default=10,
        gt=0,
        description="Default max results for calendar search operations",
    )
    tasks_tool_default_max_results: int = Field(
        default=10,
        gt=0,
        description="Default max results for tasks list/search operations",
    )
    places_tool_default_max_results: int = Field(
        default=10,
        gt=0,
        le=20,
        description="Default max results for places search operations (Google Places max 20)",
    )
    places_tool_default_radius_meters: int = Field(
        default=500,
        gt=0,
        le=50000,
        description="Default search radius in meters for nearby places search (max 50km)",
    )
    drive_tool_default_max_results: int = Field(
        default=10,
        gt=0,
        description="Default max results for Drive search/list operations",
    )

    # ========================================================================
    # Emails Tools Configuration
    # ========================================================================
    emails_tool_default_max_results: int = Field(
        default=10,
        gt=0,
        description="Default max results for email search operations",
    )
    emails_tool_default_limit: int = Field(
        default=10,
        gt=0,
        description="Default limit for email list operations",
    )

    # ========================================================================
    # Global API Security Limits
    # ========================================================================
    api_max_items_per_request: int = Field(
        default=50,
        gt=0,
        le=50,
        description=(
            "Maximum number of items that can be returned by any API call to external services "
            "(Google Contacts, Gmail, Calendar, etc.). This is a hard security limit applied "
            "to all domain API calls: search, list, warmup, and batch operations."
        ),
    )

    # ========================================================================
    # Emails Configuration
    # ========================================================================
    # Emails body truncation (for LLM token optimization)
    emails_body_max_length: int = Field(
        default=EMAILS_BODY_MAX_LENGTH_DEFAULT,
        gt=0,
        description="Maximum email body length in characters before truncation (default: 2000)",
    )

    # Emails URL shortening threshold (for readability)
    emails_url_shorten_threshold: int = Field(
        default=EMAILS_URL_SHORTEN_THRESHOLD_DEFAULT,
        gt=0,
        description="URL length threshold for shortening to [lien](url) format (default: 50)",
    )

    # Gmail default search window (days)
    gmail_default_search_days: int = Field(
        default=GMAIL_DEFAULT_SEARCH_DAYS,
        gt=0,
        le=365,
        description=(
            "Default search window in days when user doesn't specify a date range. "
            "Prevents token explosion from retrieving years of emails. Default: 90 days."
        ),
    )

    # ========================================================================
    # OAuth Proactive Token Refresh (Background Job)
    # ========================================================================
    # Refreshes OAuth tokens BEFORE they expire to prevent disconnections
    # when users return after periods of inactivity.
    oauth_proactive_refresh_interval_minutes: int = Field(
        default=OAUTH_PROACTIVE_REFRESH_INTERVAL_MINUTES,
        ge=5,
        le=60,
        description="How often to check for expiring tokens (minutes, default: 15)",
    )
    oauth_proactive_refresh_margin_seconds: int = Field(
        default=OAUTH_PROACTIVE_REFRESH_MARGIN_SECONDS,
        ge=300,
        le=7200,
        description="Refresh tokens expiring within this window (seconds, default: 1800 = 30 min)",
    )

    # ========================================================================
    # OAuth Health Check (Push Notifications for Broken Connectors)
    # ========================================================================
    # SIMPLIFIED DESIGN: Only alerts on status=ERROR (refresh failed).
    # Normal token expiration is handled silently by proactive refresh job.
    # Sends push notifications to offline users so they know to reconnect.
    oauth_health_check_enabled: bool = Field(
        default=True,
        description="Enable OAuth health checks and push notifications for ERROR connectors",
    )
    oauth_health_check_interval_minutes: int = Field(
        default=OAUTH_HEALTH_CHECK_INTERVAL_MINUTES_DEFAULT,
        ge=1,
        le=60,
        description="How often to check OAuth connector status (minutes, default: 5)",
    )
    oauth_health_critical_cooldown_hours: int = Field(
        default=OAUTH_HEALTH_CRITICAL_COOLDOWN_HOURS_DEFAULT,
        ge=1,
        le=72,
        description="Cooldown before re-notifying for ERROR connector (hours, default: 24)",
    )
    sse_connection_ttl_seconds: int = Field(
        default=SSE_CONNECTION_TTL_SECONDS_DEFAULT,
        ge=30,
        le=300,
        description="TTL for SSE connection tracking in Redis (seconds, default: 120)",
    )

    # ========================================================================
    # Circuit Breaker Configuration (Sprint 16 - Gold-Grade Resilience)
    # ========================================================================
    circuit_breaker_failure_threshold: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Number of consecutive failures before opening circuit",
    )
    circuit_breaker_success_threshold: int = Field(
        default=3,
        ge=1,
        le=20,
        description="Number of consecutive successes to close circuit from half-open",
    )
    circuit_breaker_timeout_seconds: int = Field(
        default=60,
        ge=10,
        le=600,
        description="Time in seconds before half-open retry after circuit opens",
    )
    circuit_breaker_half_open_max_calls: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Max calls allowed in half-open state for testing recovery",
    )

    # ========================================================================
    # Apple iCloud Configuration
    # ========================================================================
    # IMAP / SMTP (Apple Mail)
    apple_imap_host: str = Field(
        default="imap.mail.me.com",
        description="Apple iCloud IMAP server hostname",
    )
    apple_imap_port: int = Field(
        default=993,
        ge=1,
        le=65535,
        description="Apple iCloud IMAP server port (SSL)",
    )
    apple_smtp_host: str = Field(
        default="smtp.mail.me.com",
        description="Apple iCloud SMTP server hostname",
    )
    apple_smtp_port: int = Field(
        default=587,
        ge=1,
        le=65535,
        description="Apple iCloud SMTP server port (STARTTLS)",
    )
    apple_smtp_daily_limit: int = Field(
        default=1000,
        gt=0,
        description="Apple SMTP daily sending limit (Apple imposes 1000 messages/day)",
    )
    apple_smtp_max_recipients: int = Field(
        default=500,
        gt=0,
        description="Apple SMTP max recipients per message (Apple imposes 500)",
    )
    apple_smtp_max_size_mb: int = Field(
        default=20,
        gt=0,
        description="Apple SMTP max message size in MB (Apple imposes 20MB)",
    )
    # CalDAV (Apple Calendar)
    apple_caldav_url: str = Field(
        default="https://caldav.icloud.com",
        description="Apple iCloud CalDAV discovery URL",
    )
    # CardDAV (Apple Contacts)
    apple_carddav_url: str = Field(
        default="https://contacts.icloud.com",
        description="Apple iCloud CardDAV discovery URL",
    )
    # Common Apple settings
    apple_connection_timeout: float = Field(
        default=30.0,
        gt=0.0,
        description="Timeout for Apple iCloud connections (seconds)",
    )
    client_rate_limit_apple_per_second: int = Field(
        default=5,
        gt=0,
        description="Apple iCloud APIs: max requests per second per user (default: 5)",
    )
    apple_contacts_cache_ttl: int = Field(
        default=600,
        gt=0,
        description="Cache TTL for full Apple contacts list in Redis (seconds, default: 10 minutes)",
    )
    apple_email_message_cache_ttl: int = Field(
        default=60,
        gt=0,
        description="Cache TTL for individual IMAP messages in Redis (seconds, default: 60s). "
        "Solves the N+1 IMAP connection problem: search_emails caches messages, "
        "get_message reads from cache.",
    )

    # ========================================================================
    # Philips Hue Configuration (Smart Home)
    # ========================================================================
    hue_rate_limit_per_second: int = Field(
        default=HUE_DEFAULT_RATE_LIMIT_PER_SECOND,
        ge=1,
        le=20,
        description="Rate limit per second for Hue Bridge API calls",
    )
    hue_bridge_timeout_seconds: float = Field(
        default=HTTP_TIMEOUT_HUE_API,
        ge=1.0,
        le=30.0,
        description="HTTP timeout for Hue Bridge API calls (seconds)",
    )
    hue_remote_client_id: str = Field(
        default="",
        description="Hue Remote API OAuth client ID (from developers.meethue.com)",
    )
    hue_remote_client_secret: str = Field(
        default="",
        description="Hue Remote API OAuth client secret",
    )
    hue_remote_app_id: str = Field(
        default="",
        description="Hue Remote API application ID",
    )

    # ========================================================================
    # Connector Cache TTL Method
    # ========================================================================
    def get_connector_cache_ttl(self, connector_type: str) -> int:
        """
        Get cache TTL for a specific connector type.

        Args:
            connector_type: Connector identifier (e.g., "google_contacts", "google_gmail").

        Returns:
            Cache TTL in seconds for the specified connector.
            Falls back to 300 seconds (5 minutes) if connector not configured.

        Example:
            >>> settings.get_connector_cache_ttl("google_contacts")
            300
            >>> settings.get_connector_cache_ttl("google_contacts_search")
            180
            >>> settings.get_connector_cache_ttl("google_gmail")
            60
        """
        # Comprehensive cache TTL mapping for all connectors
        cache_mapping = {
            # Contacts
            "google_contacts": self.contacts_cache_list_ttl_seconds,
            "google_contacts_list": self.contacts_cache_list_ttl_seconds,
            "google_contacts_search": self.contacts_cache_search_ttl_seconds,
            "google_contacts_details": self.contacts_cache_details_ttl_seconds,
            # Emails
            "google_gmail": self.emails_cache_list_ttl_seconds,
            "google_gmail_list": self.emails_cache_list_ttl_seconds,
            "google_gmail_search": self.emails_cache_search_ttl_seconds,
            "google_gmail_details": self.emails_cache_details_ttl_seconds,
            # Calendar
            "google_calendar": self.calendar_cache_list_ttl_seconds,
            "google_calendar_list": self.calendar_cache_list_ttl_seconds,
            "google_calendar_search": self.calendar_cache_search_ttl_seconds,
            "google_calendar_details": self.calendar_cache_details_ttl_seconds,
            # Drive
            "google_drive": self.drive_cache_list_ttl_seconds,
            "google_drive_list": self.drive_cache_list_ttl_seconds,
            "google_drive_search": self.drive_cache_search_ttl_seconds,
            "google_drive_details": self.drive_cache_details_ttl_seconds,
            # Tasks
            "google_tasks": self.tasks_cache_list_ttl_seconds,
            "google_tasks_list": self.tasks_cache_list_ttl_seconds,
            "google_tasks_details": self.tasks_cache_details_ttl_seconds,
            # Weather
            "openweathermap": self.weather_cache_current_ttl_seconds,
            "weather_current": self.weather_cache_current_ttl_seconds,
            "weather_forecast": self.weather_cache_forecast_ttl_seconds,
            # Wikipedia
            "wikipedia": self.wikipedia_cache_search_ttl_seconds,
            "wikipedia_search": self.wikipedia_cache_search_ttl_seconds,
            "wikipedia_article": self.wikipedia_cache_article_ttl_seconds,
            # Routes (Google Routes API)
            "google_routes": self.routes_cache_traffic_ttl_seconds,
            "google_routes_traffic": self.routes_cache_traffic_ttl_seconds,
            "google_routes_static": self.routes_cache_static_ttl_seconds,
            "google_routes_matrix": self.routes_cache_matrix_ttl_seconds,
            # Apple iCloud (reuse same TTLs as Google equivalents)
            "apple_email": self.emails_cache_list_ttl_seconds,
            "apple_calendar": self.calendar_cache_list_ttl_seconds,
            "apple_contacts": self.apple_contacts_cache_ttl,
            # Microsoft 365 (reuse same TTLs as Google equivalents)
            "microsoft_outlook": self.emails_cache_list_ttl_seconds,
            "microsoft_calendar": self.calendar_cache_list_ttl_seconds,
            "microsoft_contacts": self.contacts_cache_list_ttl_seconds,
            "microsoft_tasks": self.tasks_cache_list_ttl_seconds,
        }

        if connector_type in cache_mapping:
            return cache_mapping[connector_type]

        # Fallback: 5 minutes
        return 300
