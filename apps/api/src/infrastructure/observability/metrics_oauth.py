"""
Prometheus metrics for OAuth 2.0/2.1 authentication flows.

Tracks OAuth callback performance, success rates, and errors for:
- Google OAuth authentication
- Google Contacts connector
- Gmail connector (future)
- Other OAuth providers (future)

Security & compliance monitoring:
- PKCE validation success/failure rates
- State token validation (CSRF protection)
- OAuth provider latency
- Token exchange duration

Reference:
- OAuth 2.1 Draft 14 (2025)
- RFC 7636 (PKCE)
- BFF Pattern security best practices
"""

from prometheus_client import Counter, Histogram

# ============================================================================
# OAUTH CALLBACK METRICS
# ============================================================================

oauth_callback_total = Counter(
    "oauth_callback_total",
    "Total OAuth callbacks received",
    ["provider", "status"],  # status: success, failed
)

oauth_callback_duration_seconds = Histogram(
    "oauth_callback_duration_seconds",
    "OAuth callback processing duration (code exchange + user creation)",
    ["provider"],
    buckets=[0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 7.0, 10.0],
)

oauth_callback_errors_total = Counter(
    "oauth_callback_errors_total",
    "OAuth callback errors by type",
    [
        "provider",
        "error_type",
    ],  # error_type: state_mismatch, pkce_failed, token_exchange_failed, user_creation_failed
)

# ============================================================================
# OAUTH INITIATION METRICS
# ============================================================================

oauth_initiate_total = Counter(
    "oauth_initiate_total",
    "Total OAuth flow initiations (user clicks 'Sign in with Google')",
    ["provider", "flow_type"],  # flow_type: authentication, connector
)

oauth_initiate_duration_seconds = Histogram(
    "oauth_initiate_duration_seconds",
    "OAuth initiation duration (PKCE generation + authorization URL construction)",
    ["provider"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
)

# ============================================================================
# SECURITY METRICS (PKCE & STATE)
# ============================================================================

oauth_pkce_validation_total = Counter(
    "oauth_pkce_validation_total",
    "PKCE code_verifier validation results",
    ["provider", "result"],  # result: success, failed
)

oauth_state_validation_total = Counter(
    "oauth_state_validation_total",
    "State token validation results (CSRF protection)",
    ["provider", "result"],  # result: success, failed, expired
)

# ============================================================================
# OAUTH PROVIDER METRICS
# ============================================================================

oauth_token_exchange_duration_seconds = Histogram(
    "oauth_token_exchange_duration_seconds",
    "Duration of token exchange with OAuth provider",
    ["provider"],
    buckets=[0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0],
)

oauth_user_info_fetch_duration_seconds = Histogram(
    "oauth_user_info_fetch_duration_seconds",
    "Duration of user info fetch from OAuth provider",
    ["provider"],
    buckets=[0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0],
)

oauth_provider_errors_total = Counter(
    "oauth_provider_errors_total",
    "Errors from OAuth provider API",
    ["provider", "endpoint"],  # endpoint: token, userinfo
)

# ============================================================================
# USER METRICS (OAuth-specific)
# ============================================================================

oauth_user_creation_total = Counter(
    "oauth_user_creation_total",
    "New users created via OAuth",
    ["provider"],
)

oauth_user_login_total = Counter(
    "oauth_user_login_total",
    "Existing users logged in via OAuth",
    ["provider"],
)

# ============================================================================
# CONNECTOR METRICS (OAuth)
# ============================================================================

oauth_connector_activation_total = Counter(
    "oauth_connector_activation_total",
    "Connectors activated via OAuth",
    ["connector_type", "status"],  # status: success, failed
)

oauth_connector_activation_duration_seconds = Histogram(
    "oauth_connector_activation_duration_seconds",
    "Connector activation duration",
    ["connector_type"],
    buckets=[0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0],
)
