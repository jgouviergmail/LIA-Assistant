"""
PII (Personally Identifiable Information) filtering for structured logs.

This module provides processors for structlog to automatically detect and redact
sensitive personal information from logs, ensuring GDPR compliance and data privacy.

Features:
- Email address detection and pseudonymization (SHA-256 hash)
- Phone number detection and masking
- Credit card number detection and masking
- SSN, passport, driver license detection
- Generic token/secret detection
- OAuth state fingerprinting (correlatable, non-reversible) and PKCE/code
  redaction (SEC-012)
- URL query-string credential stripping — verification/reset/OAuth links
  (SEC-012)
- Configurable field-based filtering
- Hybrid approach: field-based + pattern-based detection

Industry Standards Used:
- Email: RFC 5322 simplified pattern
- Credit Cards: Luhn algorithm compatible (Visa, MC, Amex)
- Phones: Conservative international format (+country code required)
- Tokens: Stripe, GitHub, JWT patterns

Usage:
    from src.infrastructure.observability.pii_filter import add_pii_filter

    structlog.configure(
        processors=[
            ...
            add_pii_filter,  # Add before JSONRenderer
            structlog.processors.JSONRenderer(),
        ]
    )

References:
- GDPR Article 5: Data minimization
- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- RFC 5322: Email format
"""

import hashlib
import re
from typing import Any

from src.core.field_names import FIELD_SESSION_ID

# Sensitive field names to always redact (exact match, case-insensitive)
SENSITIVE_FIELD_NAMES = {
    "password",
    "hashed_password",
    "secret",
    "api_key",
    "apikey",
    "token",
    "access_token",
    "refresh_token",
    "auth_token",
    "id_token",
    "bearer",
    "authorization",
    "cookie",
    "session",
    FIELD_SESSION_ID,
    "csrf",
    "private_key",
    "credit_card",
    "card_number",
    "cvv",
    "ssn",
    "social_security",
    # OAuth / PKCE credentials (SEC-012): single-use codes and verifiers are
    # as sensitive as long-lived tokens. `oauth_state`/`state` are handled
    # separately (fingerprinted, not redacted) so init↔callback correlation
    # survives — see `_STATE_FIELD_NAMES` and `fingerprint_secret`.
    "code_verifier",
    "code_challenge",
    "client_secret",
    "authorization_code",
    "auth_code",
    "oauth_state",
}

# Field names carrying an opaque OAuth state / CSRF token. Unlike the fields
# above, these are *fingerprinted* (one-way HMAC-like digest) rather than fully
# redacted, so an OAuth flow can still be correlated across the initiation and
# callback log lines without exposing the single-use secret (SEC-012). The
# fingerprint only applies when the value actually LOOKS like an opaque token
# (see `_looks_like_opaque_token`) — a plain `state="running"` LangGraph/app
# state string is left untouched to preserve observability.
_STATE_FIELD_NAMES = {
    "state",
}

# Query-string parameter names whose VALUE must be stripped from any logged URL
# (SEC-012). A verification/reset link (`.../verify?token=<secret>`) or an OAuth
# redirect embeds single-use credentials in the query; the field name of the log
# key (`verification_url`, `auth_url`, …) is not sensitive, but the value is. The
# match is anchored on a `?`/`&` boundary so only real query parameters are hit —
# a free-text `code=200` is never touched.
_SENSITIVE_QUERY_PARAMS = (
    "token",
    "access_token",
    "refresh_token",
    "id_token",
    "code",
    "code_verifier",
    "code_challenge",
    "secret",
    "client_secret",
    "password",
    "passwd",
    "pwd",
    "api_key",
    "apikey",
    "state",
    "sig",
    "signature",
    "session",
    "sessionid",
    "jwt",
    "authorization",
    # Geolocation. Not credentials, but PII the logging policy forbids at INFO
    # ("no names, emails, GPS coordinates"). LIA builds static-map URLs carrying
    # the user's exact position — `?lat=..&lng=..` for a location card,
    # `?origin=48.85,2.35&dest=..` for a route — so a logged URL would pin the
    # user on a map. The parameter name survives the redaction, which keeps the
    # log readable for debugging.
    "lat",
    "lng",
    "lon",
    "latitude",
    "longitude",
    "origin",
    "dest",
    "destination",
)

# PII field names that should be pseudonymized (not fully redacted)
PII_FIELD_NAMES = {
    "email",
    "e_mail",
    "email_address",
    "user_email",
}

# Phone field names that should be masked
PHONE_FIELD_NAMES = {
    "phone",
    "phone_number",
    "mobile",
    "mobile_number",
    "telephone",
    "tel",
}

# Content-bearing field names: user contents (recipients, subjects, addresses,
# coordinates, resolved names, memory previews, raw tool params, query text).
# Policy (audit wave 2, C7): counters/IDs at INFO; contents at DEBUG or redacted.
# These fields are REDACTED at INFO and above, passed through at DEBUG — a
# systemic net so a future `subject=`/`lat=` at INFO cannot leak PII again.
CONTENT_FIELD_NAMES = {
    # Email / messaging contents
    "to",
    "cc",
    "bcc",
    "subject",
    "body",
    "recipient",
    "recipients",
    # Location contents
    "address",
    "address_preview",
    "lat",
    "lon",
    "latitude",
    "longitude",
    "origin",
    "destination",
    "location",
    # Resolved people / labels
    "contact_name",
    "display_label",
    "display_labels",
    "mappings",
    # Content previews (memories, tool results)
    "content_preview",
    "result_preview",
    # Raw user / entity content (CA-1, audit S9). These carried user content at
    # INFO through logger call-sites not previously covered:
    #   - user_message: HITL decision logs (orchestration/service.py)
    #   - summary:      calendar event titles (calendar_tools.py, mixins.py)
    #   - title:        task titles (tasks_tools.py)
    #   - content / new_content / original_content_preview:
    #                   reminder bodies, edited conversation messages
    #   - original_content / reformulated_intent:
    #                   HITL edit logs — the user's original message and the
    #                   reformulated edit request (orchestration/service.py,
    #                   hitl/resumption_strategies.py)
    #   - user_response / original_user_response / clarification_response:
    #                   HITL classifier & clarification logs — the user's raw
    #                   reply (hitl_classifier.py, clarification_node.py,
    #                   planner_node_v3.py, hitl/resumption_strategies.py)
    #   - original_filename: user-uploaded document / attachment names
    #                   (rag_spaces/service.py, rag_spaces/processing.py at INFO;
    #                   attachments/llm_content.py at WARNING) — file names embed
    #                   PII (e.g. "CV Jean Dupont.pdf", "IRM cerveau.png")
    #   - exclude_criteria: the user's FOR_EACH bulk-operation exclusion text
    #                   (for_each_confirm_node.py, hitl/item_filter.py,
    #                   orchestration/service.py)
    # `title`/`summary`/`content` are ambiguous field names that ALSO appear as
    # object-construction kwargs (WikipediaResult, BraveSearchItem, ...) and, at
    # a couple of web logger sites, as PUBLIC content. The net is field-name
    # based and only touches log event dicts, so construction kwargs are
    # unaffected; the rare public logger site (web_fetch_success /
    # wikipedia_search_success) already logs `url=`, making the redacted title
    # redundant. Any future public-content log that needs the raw value at INFO
    # must emit it at DEBUG (net off) or log a length/flag instead.
    "user_message",
    "summary",
    "title",
    "content",
    "new_content",
    "original_content_preview",
    "original_content",
    "reformulated_intent",
    "user_response",
    "original_user_response",
    "clarification_response",
    "original_filename",
    "exclude_criteria",
    # Raw tool parameters
    "params",
    # Query text (may embed names/emails)
    "query_preview",
    "original_query",
    "final_query",
    "normalized_query",
    "resolved_query",
    "combined_query",
    "enriched_query",
}

# Structlog metadata fields — never sanitize these. They are the developer-controlled
# log envelope (event name, logger module, level, timestamp, source position) and
# never contain user data. Treating them like payload values causes false-positive
# redactions on event names that happen to resemble token patterns
# (e.g. `database_connection_pool_exhausted` matches the generic token regex).
STRUCTLOG_META_FIELDS = {
    "event",
    "logger",
    "level",
    "timestamp",
    "func_name",
    "filename",
    "lineno",
    "module",
    "pathname",
    "process",
    "process_name",
    "thread",
    "thread_name",
}

# Regex patterns for PII detection (using industry-standard patterns)

# Email pattern (RFC 5322 simplified)
EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
    re.IGNORECASE,
)

# Phone pattern: Conservative approach - only match clear phone number formats
# Requires + prefix with country code to avoid false positives
PHONE_PATTERN = re.compile(
    r"\+\d{1,3}[\s.-]?\d{1,4}[\s.-]?\d{1,4}[\s.-]?\d{1,4}[\s.-]?\d{1,4}",
)

# Credit card pattern (Luhn algorithm compatible - matches Visa, MC, Amex, etc.)
CREDIT_CARD_PATTERN = re.compile(
    r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
)

# High-confidence token patterns only.
#
# Strategy: this regex is a defence-in-depth layer behind the field-based
# redaction (``SENSITIVE_FIELD_NAMES``). It MUST only match strings that look
# unambiguously like real tokens — every false positive on a developer
# identifier (snake_case event name, payload tag, ...) directly degrades log
# observability.
#
# What we removed (was the source of ~385 false positives in production logs):
#   ``[A-Za-z0-9]{8,}_[A-Za-z0-9_-]{24,}``
# That generic shape ``prefix_suffix`` matches no real token format from any
# major provider (Stripe uses sk_live_, GitHub uses ghp_, OpenAI uses sk-proj-,
# Google uses AIza..., none have underscore-separated alphanumeric blobs) but
# does match many legitimate snake_case identifiers
# (``langfuse_callbacks_added_via_config_enrichment``,
# ``database_connection_pool_exhausted``, ...).
#
# What we keep / add: signature-prefixed formats from well-known issuers and
# JWT tokens, all of which have unambiguous structure.
TOKEN_PATTERN = re.compile(
    r"\bsk_(?:live|test)_[A-Za-z0-9]{24,}\b|"  # Stripe secret keys
    r"\bgh[ps]_[A-Za-z0-9]{36,}\b|"  # GitHub personal / server / fine-grained tokens
    # JWT: three URL-safe-base64 segments separated by dots; the header almost
    # always starts with ``eyJ`` (encoded ``{"alg``).
    r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"
)

# URL query-string secret pattern (SEC-012). Matches a sensitive parameter and
# its value on a `?`/`&` boundary, e.g. ``?token=abc`` or ``&code=xyz``. Only the
# VALUE is replaced (group 2); the parameter name is kept so the log still shows
# which link was involved. Anchoring on `[?&]` prevents false positives on
# free-text ``code=200``-style content that is not a query parameter.
_URL_QUERY_SECRET_PATTERN = re.compile(
    r"([?&](?:" + "|".join(_SENSITIVE_QUERY_PARAMS) + r")=)([^&\s#\"']+)",
    re.IGNORECASE,
)

# Opaque-token shape (SEC-012): a single URL-safe-base64 / hex run of >= 20 chars
# with no separators. Matches OAuth state (`secrets.token_urlsafe(32)` → 43
# chars) and similar high-entropy secrets, while sparing short application state
# strings like ``running`` / ``pending_approval`` (< 20 chars).
_OPAQUE_TOKEN_PATTERN = re.compile(r"\A[A-Za-z0-9_-]{20,}\Z")


def pseudonymize_email(email: str) -> str:
    """
    Pseudonymize an email address using SHA-256 hash.

    Pseudonymization allows for consistent identification (same email = same hash)
    while protecting the actual email address. This is reversible if needed with
    a secure mapping table, unlike full anonymization.

    Args:
        email: Email address to pseudonymize

    Returns:
        SHA-256 hash of the email (first 16 characters for readability)

    Example:
        >>> pseudonymize_email("user@example.com")
        "email_hash_a1b2c3d4e5f6g7h8"
    """
    email_hash = hashlib.sha256(email.encode("utf-8")).hexdigest()[:16]
    return f"email_hash_{email_hash}"


def mask_phone(phone: str) -> str:
    """
    Mask a phone number, keeping only the last 4 digits.

    Args:
        phone: Phone number to mask

    Returns:
        Masked phone number

    Example:
        >>> mask_phone("+1 (555) 123-4567")
        "***-***-4567"
    """
    # Extract only digits
    digits = re.sub(r"\D", "", phone)
    if len(digits) >= 4:
        return f"***-***-{digits[-4:]}"
    return "***-***-****"


def mask_credit_card(card: str) -> str:
    """
    Mask a credit card number, keeping only the last 4 digits.

    Args:
        card: Credit card number to mask

    Returns:
        Masked credit card number

    Example:
        >>> mask_credit_card("4532 1234 5678 9010")
        "****-****-****-9010"
    """
    digits = re.sub(r"\D", "", card)
    if len(digits) >= 4:
        return f"****-****-****-{digits[-4:]}"
    return "****-****-****-****"


def redact_value(value: Any) -> str:
    """
    Redact a sensitive value.

    Args:
        value: Value to redact

    Returns:
        Redacted placeholder
    """
    return "[REDACTED]"


def fingerprint_secret(value: str) -> str:
    """Return a non-reversible correlation fingerprint of a high-entropy secret.

    Used for opaque OAuth ``state`` / CSRF tokens (SEC-012): the raw value must
    never reach the logs, but the initiation and callback log lines still need a
    shared key to be correlated. A truncated SHA-256 digest gives that shared
    key without exposing the secret. This is only safe for HIGH-ENTROPY values
    (e.g. ``secrets.token_urlsafe(32)`` = 256 bits) — a weak/guessable token
    could be brute-forced from its digest, so callers must not fingerprint
    low-entropy secrets (redact those instead).

    Args:
        value: The high-entropy secret to fingerprint.

    Returns:
        A short, stable, non-reversible tag of the form ``fp_<12 hex chars>``.

    Example:
        >>> fingerprint_secret("s" * 43).startswith("fp_")
        True
    """
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"fp_{digest}"


def _looks_like_opaque_token(value: str) -> bool:
    """Whether a string looks like an opaque high-entropy token (SEC-012).

    Guards the ``state`` fingerprinting so that only real OAuth/CSRF tokens are
    touched and short application-state strings are preserved for observability.

    Args:
        value: Candidate string.

    Returns:
        True if the value is a single URL-safe-base64/hex run of >= 20 chars.
    """
    return bool(_OPAQUE_TOKEN_PATTERN.match(value))


def sanitize_url_query(text: str) -> str:
    """Strip the values of sensitive query parameters from any URL in ``text``.

    Neutralizes single-use credentials embedded in logged links — e.g. an email
    verification/reset URL (``.../verify?token=<secret>``) or an OAuth redirect
    (``...?code=<secret>&state=<secret>``). The parameter NAME is preserved so
    the log stays useful; only the value becomes ``[REDACTED]`` (SEC-012).

    Args:
        text: Free-text log value that may contain one or more URLs.

    Returns:
        The text with sensitive query-parameter values redacted.

    Example:
        >>> sanitize_url_query("https://app/verify?token=abc123&lang=fr")
        'https://app/verify?token=[REDACTED]&lang=fr'
    """
    # Fast path. Since FN-4 this runs on the `event` of EVERY log line, and the
    # overwhelming majority are snake_case event names with no query string at
    # all. The pattern can only match on a `?`/`&` boundary, so their absence
    # means no match — the substring test is a cheap, exact pre-filter (both
    # characters are checked: a truncated URL can start at `&param=`).
    if "?" not in text and "&" not in text:
        return text
    return _URL_QUERY_SECRET_PATTERN.sub(r"\1[REDACTED]", text)


def sanitize_string(text: str) -> str:
    """
    Sanitize a string by detecting and redacting PII patterns.

    This function scans text for common PII patterns (emails, phones, credit cards, tokens)
    and replaces them with redacted or pseudonymized versions.

    Args:
        text: Text to sanitize

    Returns:
        Sanitized text with PII redacted

    Example:
        >>> sanitize_string("Contact user@example.com or call +1-555-123-4567")
        "Contact email_hash_a1b2c3d4e5f6g7h8 or call ***-***-4567"
    """
    # Strip single-use credentials embedded in URL query strings (SEC-012):
    # verification/reset links and OAuth redirects carry `?token=`/`?code=`.
    text = sanitize_url_query(text)

    # Replace emails with pseudonymized hashes
    text = EMAIL_PATTERN.sub(lambda m: pseudonymize_email(m.group(0)), text)

    # Mask phone numbers
    text = PHONE_PATTERN.sub(lambda m: mask_phone(m.group(0)), text)

    # Mask credit cards
    text = CREDIT_CARD_PATTERN.sub(lambda m: mask_credit_card(m.group(0)), text)

    # Redact generic tokens/API keys
    text = TOKEN_PATTERN.sub("[REDACTED_TOKEN]", text)

    return text


def _sanitize_event_text(text: str) -> str:
    """Sanitize the structlog ``event`` field without mangling event names.

    Deliberately NOT ``sanitize_string``: that one also applies
    ``TOKEN_PATTERN``, which would rewrite legitimate snake_case event names
    that happen to look like opaque tokens. Only the two patterns that cannot
    match an event name are applied — a URL query string, and an email address.

    Args:
        text: Raw ``event`` value.

    Returns:
        The text with URL secrets redacted and addresses pseudonymized.
    """
    return EMAIL_PATTERN.sub(lambda m: pseudonymize_email(m.group(0)), sanitize_url_query(text))


def sanitize_dict(data: dict[str, Any], *, redact_content: bool = False) -> dict[str, Any]:
    """
    Recursively sanitize a dictionary using field-based detection.

    This function uses a conservative **field-based approach** to avoid false positives:
    1. Redacts values for known sensitive field names (passwords, tokens, secrets)
    2. Pseudonymizes PII field names (emails → hash)
    3. Masks phone field names (phones → last 4 digits)
    4. Recursively processes nested dictionaries and lists
    5. Sanitizes string values for pattern-based PII detection (emails, tokens)

    This hybrid approach (field names + patterns) provides the best balance
    between security and avoiding false positives.

    Args:
        data: Dictionary to sanitize
        redact_content: When True, also redact content-bearing field names
            (CONTENT_FIELD_NAMES). Enabled for INFO-and-above log records —
            contents are only allowed at DEBUG (audit wave 2, C7).

    Returns:
        Sanitized dictionary with PII redacted
    """
    sanitized: dict[str, Any] = {}

    for key, value in data.items():
        key_lower = key.lower()

        # Structlog metadata fields are developer-controlled identifiers — never
        # user data — so they MUST bypass sanitization to avoid false-positive
        # redactions on event names that resemble token patterns.
        #
        # `event` gets TWO narrow exceptions (FN-4): it is the only meta field
        # that can carry free text rather than an identifier. A stdlib record
        # routed into structlog puts the whole log MESSAGE here — an access line
        # such as `GET /auth/google/callback?code=..&state=..`, or an SMTP error
        # naming the recipient — and the full sanitizer is not an option (it is
        # exactly what this bypass exists to prevent: `TOKEN_PATTERN` would
        # mangle legitimate event names).
        #
        # Both exceptions are safe for the same reason: they rewrite shapes a
        # snake_case event name cannot contain. `sanitize_url_query` only
        # rewrites `?param=value` on a `?`/`&` boundary; `EMAIL_PATTERN`
        # requires an `@` followed by a dotted domain. An event name has
        # neither, so no identifier can be corrupted — while an address that
        # reaches a log survives shipping, retention and backups long after the
        # account it belongs to is gone (SEC-012).
        if key_lower in STRUCTLOG_META_FIELDS:
            sanitized[key] = (
                _sanitize_event_text(value)
                if key_lower == "event" and isinstance(value, str)
                else value
            )
            continue

        # Check if field name is sensitive (case-insensitive)
        if key_lower in SENSITIVE_FIELD_NAMES:
            sanitized[key] = redact_value(value)
            continue

        # OAuth `state` / CSRF token: fingerprint (not redact) so init↔callback
        # log lines stay correlatable, but ONLY when the value looks like an
        # opaque high-entropy token — a plain LangGraph/app `state` string
        # (dict, or short label like "running") is left untouched (SEC-012).
        if (
            key_lower in _STATE_FIELD_NAMES
            and isinstance(value, str)
            and _looks_like_opaque_token(value)
        ):
            sanitized[key] = fingerprint_secret(value)
            continue

        # Content-bearing fields are redacted at INFO and above (C7 policy:
        # counters/IDs at INFO, contents at DEBUG or redacted)
        if redact_content and key_lower in CONTENT_FIELD_NAMES:
            sanitized[key] = redact_value(value)
            continue

        # Check if field is a known PII field (email)
        if key_lower in PII_FIELD_NAMES and isinstance(value, str):
            sanitized[key] = pseudonymize_email(value)
            continue

        # Check if field is a known phone field
        if key_lower in PHONE_FIELD_NAMES and isinstance(value, str):
            sanitized[key] = mask_phone(value)
            continue

        # Recursively sanitize nested structures
        if isinstance(value, dict):
            sanitized[key] = sanitize_dict(value, redact_content=redact_content)
        elif isinstance(value, list):
            sanitized_list: list[Any] = [
                (
                    sanitize_dict(item, redact_content=redact_content)
                    if isinstance(item, dict)
                    else sanitize_string(item) if isinstance(item, str) else item
                )
                for item in value
            ]
            sanitized[key] = sanitized_list
        elif isinstance(value, str):
            # Sanitize string values for PII patterns (emails, tokens in free text)
            sanitized[key] = sanitize_string(value)
        else:
            # Keep non-string, non-dict, non-list values as-is
            sanitized[key] = value

    return sanitized


def add_pii_filter(logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """
    Structlog processor to filter PII from log events.

    This processor is designed to be used in the structlog processing chain
    before the final renderer (JSONRenderer). It sanitizes the event dictionary
    by detecting and redacting PII.

    Args:
        logger: The logger instance
        method_name: The name of the log method called
        event_dict: The event dictionary to be logged

    Returns:
        Sanitized event dictionary with PII redacted

    Example log transformation:
        Input:
            {
                "event": "user_login",
                "email": "user@example.com",
                "password": "secret123",
                "phone": "+1-555-123-4567"
            }

        Output:
            {
                "event": "user_login",
                "email": "email_hash_a1b2c3d4e5f6g7h8",
                "password": "[REDACTED]",
                "phone": "***-***-4567"
            }
    """
    # Sanitize the entire event dictionary. Content-bearing fields are only
    # allowed through at DEBUG (C7 policy: counters/IDs at INFO, contents at
    # DEBUG or redacted).
    return sanitize_dict(event_dict, redact_content=method_name != "debug")


# Export public API
__all__ = [
    "CONTENT_FIELD_NAMES",
    "add_pii_filter",
    "fingerprint_secret",
    "mask_credit_card",
    "mask_phone",
    "pseudonymize_email",
    "sanitize_dict",
    "sanitize_string",
    "sanitize_url_query",
]
