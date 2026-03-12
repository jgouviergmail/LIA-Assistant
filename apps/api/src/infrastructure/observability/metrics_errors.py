"""
Prometheus metrics for error taxonomy and observability.

Tracks application errors by type, LLM API failures, and external service errors.
Critical for incident response, debugging, and error budget tracking.

Error Taxonomy:
- HTTP errors: 4xx (client) vs 5xx (server) with exception type breakdown
- LLM API errors: Rate limits, timeouts, invalid requests, context length
- External service errors: Google API, OAuth providers, etc.

Reference:
- OWASP API Security Top 10
- Site Reliability Engineering (Google SRE Book) - Error Budgets
- OpenAI API Error Codes
- Anthropic API Error Handling
"""

from prometheus_client import Counter

# ============================================================================
# HTTP ERROR METRICS
# ============================================================================

http_errors_total = Counter(
    "http_errors_total",
    "Total HTTP errors by status code and exception type",
    ["status_code", "exception_type", "endpoint"],
    # status_code: 400, 401, 403, 404, 409, 422, 500, 503, etc.
    # exception_type: AuthenticationError, AuthorizationError, ValidationError, etc.
    # endpoint: /api/v1/chat, /api/v1/auth/login, etc.
)

http_client_errors_total = Counter(
    "http_client_errors_total",
    "Total HTTP 4xx client errors by specific type",
    ["error_type"],
    # error_type: authentication_failed, authorization_failed, validation_failed,
    #             resource_not_found, resource_conflict, rate_limit_exceeded
)

http_server_errors_total = Counter(
    "http_server_errors_total",
    "Total HTTP 5xx server errors by specific type",
    ["error_type"],
    # error_type: internal_server_error, database_error, external_service_error,
    #             llm_service_error, timeout_error
)

# ============================================================================
# LLM API ERROR METRICS
# ============================================================================

llm_api_errors_total = Counter(
    "llm_api_errors_total",
    "Total LLM API errors by provider and error type",
    ["provider", "error_type"],
    # provider: openai, anthropic, google
    # error_type: rate_limit, timeout, invalid_request, context_length_exceeded,
    #             api_error, authentication, content_filter, model_not_found
)

llm_rate_limit_hit_total = Counter(
    "llm_rate_limit_hit_total",
    "Total LLM rate limit hits by provider and limit type",
    ["provider", "limit_type"],
    # provider: openai, anthropic, google
    # limit_type: requests_per_minute, tokens_per_minute, requests_per_day
)

llm_context_length_exceeded_total = Counter(
    "llm_context_length_exceeded_total",
    "Total context length exceeded errors by provider and model",
    ["provider", "model"],
    # Tracks when prompts exceed model's context window
    # Critical for cost optimization (signals need for prompt compression)
)

llm_content_filter_violations_total = Counter(
    "llm_content_filter_violations_total",
    "Total content filter violations by provider",
    ["provider"],
    # Tracks when LLM refuses to generate response due to content policy
)

# ============================================================================
# EXTERNAL SERVICE ERROR METRICS
# ============================================================================

external_service_errors_total = Counter(
    "external_service_errors_total",
    "Total external service errors by service and error type",
    ["service_name", "error_type"],
    # service_name: google_api, google_people, google_oauth, currency_api, etc.
    # error_type: api_error, unauthorized, timeout, rate_limit, not_found
)

external_service_timeouts_total = Counter(
    "external_service_timeouts_total",
    "Total external service timeouts by service",
    ["service_name"],
    # Separate counter for timeouts (critical for SLA tracking)
)

# ============================================================================
# VALIDATION ERROR METRICS
# ============================================================================

validation_errors_total = Counter(
    "validation_errors_total",
    "Total validation errors by field and error type",
    ["field", "error_type"],
    # field: email, password, connector_type, message, etc.
    # error_type: missing, invalid_format, too_long, too_short, invalid_choice
)

# ============================================================================
# SECURITY ERROR METRICS
# ============================================================================

security_violations_total = Counter(
    "security_violations_total",
    "Total security violations by violation type",
    ["violation_type"],
    # violation_type: csrf_token_mismatch, oauth_state_mismatch, pkce_failed,
    #                 invalid_session, expired_token, unauthorized_access
)
