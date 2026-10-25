"""
PII (Personally Identifiable Information) filtering for structured logs.

This module provides processors for structlog to automatically detect and redact
sensitive personal information from logs, ensuring GDPR compliance and data privacy.

Features:
- Email address detection and pseudonymization (SHA-256 hash): in any script,
  masked (``fir***@``, ``f…@m….test``) or whole, at any depth of any container
  (list, tuple, set, dict), and under any field named for one (``email``,
  ``recipient_email``, ``sample_emails``) whatever the value's shape
- Phone number detection and masking
- Credit card number detection and masking
- SSN redacted by field name (no pattern: nine digits are also an order number)
- Provider key and token detection (signature-prefixed formats only)
- OAuth state fingerprinting (correlatable, non-reversible) and PKCE/code
  redaction (SEC-012)
- URL credential stripping — verification/reset/OAuth query strings
  (SEC-012), provider keys (`key=`, `appid=`), userinfo and Firecrawl path keys
- Above DEBUG: content field names and suffixes redacted (a count, a flag or
  an absence kept, except under a coordinate name), URLs reduced to their
  origin, and what an error text QUOTES of a row or an input
  (PostgreSQL DETAIL, Pydantic input_value, tracebacks included) withheld —
  `quoted_content.py` (ADR-317)
- Configurable field-based filtering
- Hybrid approach: field-based + pattern-based detection

Industry Standards Used:
- Email: RFC 5322 simplified pattern
- Credit cards: any 16-digit grouping (Visa, MC, ...) masked as written; Amex
  (15 digits) masked when the Luhn check passes
- Phones: Conservative international format (+country code required)
- Tokens: Stripe, GitHub, OpenAI, Anthropic, Google (API key, OAuth access
  token), JWT; a quoted Bearer credential or api_key value

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

from src.core.credential_fields import CREDENTIAL_FIELD_NAMES
from src.infrastructure.observability.log_locations import (
    sanitize_url_locations as _sanitize_url_locations,
)
from src.infrastructure.observability.quoted_content import redact_quoted_content

# Sensitive field names to always redact (exact match, case-insensitive)
SENSITIVE_FIELD_NAMES = set(CREDENTIAL_FIELD_NAMES) | {
    "session",
    "credit_card",
    "card_number",
    "cvv",
    "ssn",
    "social_security",
    # OAuth / PKCE credentials (SEC-012): single-use codes and verifiers are
    # as sensitive as long-lived tokens. `oauth_state`/`state` are handled
    # separately (fingerprinted, not redacted) so init↔callback correlation
    # survives — see `_STATE_FIELD_NAMES` and `fingerprint_secret`.
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
    "ticket",
    "session_token",
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
    # Provider keys carried in the query string itself: Google Maps Platform
    # (`?key=AIza…`) and OpenWeatherMap (`?appid=…`). An httpx status error
    # renders the full request URL, so a failed call logged `error=str(e)`
    # with the platform's key in it.
    "key",
    "appid",
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

# Query-string parameters whose value IS the person's text — a search, an
# address, a subject. Not credentials, so DEBUG keeps them (contents at DEBUG);
# above it the value is withheld like any other content (inventory of
# 2026-09-24: Gmail `q=`, Brave `q=`, Wikipedia `srsearch=`, Microsoft Graph
# `$search=`/`$filter=`, OpenWeatherMap geocoding `q=<city>`).
_CONTENT_QUERY_PARAMS = (
    "q",
    "query",
    "search",
    "search_query",
    "srsearch",
    "$search",
    "$filter",
    "input",
    "text",
    "textquery",
    "keyword",
    "keywords",
    "term",
    "terms",
    "titles",
    "name",
    "address",
    "prompt",
    "question",
    "subject",
    "body",
)

# PII field names that should be pseudonymized (not fully redacted)
PII_FIELD_NAMES = {
    "email",
    "e_mail",
    "email_address",
    "user_email",
}

# An address named for what it is, whatever surrounds the name:
# ``recipient_email``, ``sample_emails``, ``owner_email_address``. The four exact
# names above were the only ones recognised, so a masked address under
# ``sample_emails`` reached INFO (2026-10-25). A count, a flag or an absence under
# such a name stays (``total_emails``, ``has_email``).
_ADDRESS_FIELD_NAMES = frozenset({"emails", "email_addresses"})
_ADDRESS_FIELD_SUFFIXES = ("_email", "_emails", "_e_mail", "_email_address", "_email_addresses")

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
# systemic net so a future `subject=`/`lat=` at INFO cannot leak PII again. A
# count, a flag or an absence under one of them stays (`_is_content_field`),
# except under a coordinate name; a fact of any other shape is withheld, so it
# is logged under a name saying what it is (`origin_id=`, never `origin=` —
# guarded by `test_log_content_guard.py`).
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
    "lng",
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
    #   - agent_results_summary: the block handed to the response synthesizer,
    #                   logged verbatim (1000 chars) by two INFO events in
    #                   response_node. It was mostly short status text until the
    #                   tools' own messages started reaching it (ADR-191) — the
    #                   360° briefing puts a person's name, addresses, relayed
    #                   MESSAGE BODIES and long-term MEMORIES in there. Observed
    #                   on the dev API 2026-08-01. The two events keep their
    #                   diagnostic value (lengths, domains, keys, counts); only
    #                   the content is withheld above DEBUG.
    "agent_results_summary",
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
    # Inventory of 2026-09-24 (every log call above DEBUG, read field by field):
    # these names carried the person's words on every line that used them —
    # `query=` on 43 lines, `topic=` (a person's interests, health included) on
    # 35 — while the net above knew none of them. A name joins this list only
    # when NO line uses it for anything else; `reason`, `message`, `name`,
    # `task` and `detail` stay out (mostly codes or developer text) and are
    # held line by line by `test_log_content_guard.py`.
    "query",
    "queries",
    "question",
    "instructions",
    "modification_instructions",
    "clarification",
    "reasoning",
    "topic",
    "topics",
    "keyword",
    "keywords",
    "terms",
    "matched_terms",
    "transcript",
    "snippet",
    "excerpt",
    "stdout",
    "stderr",
    "purpose",
    "input",
    "selected_value",
    "search_value",
    "conversation",
    "display_name",
    "full_name",
    "first_name",
    "last_name",
    "entity_name",
    "resolved_name",
    "place_name",
    "label_name",
    "folder_name",
    "file_name",
    "filename",
    "name_filter",
}

# Suffixes that make a name content (`user_query_preview`, `result_content`,
# `new_topic`). Unlike the exact names above, a suffix only redacts TEXT — a
# string or a list of them — so metadata sharing the suffix survives:
# `has_content=True`, `extra_body={...}` (a request's configuration),
# `query_length=42`. An `*_id_preview` is an identifier prefix, never content.
_CONTENT_FIELD_SUFFIXES = (
    "_preview",
    "_query",
    "_queries",
    "_question",
    "_instructions",
    "_topic",
    "_topics",
    "_reasoning",
    "_keywords",
    "_snippet",
    "_excerpt",
    "_transcript",
    "_stdout",
    "_stderr",
    "_content",
    "_text",
    "_body",
    "_subject",
    "_title",
    "_prompt",
    "_input",
)
_IDENTIFIER_PREVIEW_SUFFIX = "_id_preview"

# Content names whose NUMBERS are the content: a coordinate is a number, and even
# a rounded one places a person on a map (`lng` is Google's spelling, already
# withheld in a URL). Every other content name holds words, so an integer under
# it is a count — `location=3` is how many places, not where one is — and stays
# readable above DEBUG (2026-09-25: the semantic type registry's `by_category`
# census logged its `location` and `content` counts as `[REDACTED]`).
_COORDINATE_FIELD_NAMES = frozenset({"lat", "lng", "lon", "latitude", "longitude"})

# Structlog metadata fields — never sanitize these. They are the developer-controlled
# log envelope (event name, logger module, level, timestamp) and never contain user
# data. Treating them like payload values causes false-positive redactions on event
# names that happen to resemble token patterns (e.g. `database_connection_pool_exhausted`
# matches the generic token regex).
#
# The four envelope fields the chain in `logging.py` writes and no caller does
# (`exception`, `stack` and the trace ids it also writes are payload, filtered
# like any value). The call-site names (`filename`, `func_name`, `lineno`,
# `module`, `thread`…) used to be listed too, but no processor of that chain
# adds them — so the bypass only ever applied to APPLICATION fields of the same
# name, where `filename=` is an attachment's or a generated document's name and
# escaped every rule, emails included (2026-09-24).
STRUCTLOG_META_FIELDS = {
    "event",
    "logger",
    "level",
    "timestamp",
}

# Regex patterns for PII detection (using industry-standard patterns)

# The marks a writer shortens an address with (``fir***@``, ``f…@m….test``): a
# masked address still names a domain and the start of a name.
_ADDRESS_MARKS = "*•…"

# Email pattern (RFC 5322 simplified). Letters and digits of every script — an
# address is no less a person's for its accents: ``zoë@mail.test`` and
# ``contact@café.fr`` went through whole, ``andré.martin@…`` kept its first name
# — and the masking marks above (2026-10-25). The local part is bounded (RFC
# 5321: 64) and starts where a run of its characters starts: unbounded, a try at
# every word boundary re-read the rest of the run — 40 000 characters of
# ``a.b+c-`` took 4.5 s, and every log line goes through here (ADR-326).
EMAIL_PATTERN = re.compile(
    rf"(?<![\w.%+{_ADDRESS_MARKS}-])[\w.%+{_ADDRESS_MARKS}-]{{1,64}}"
    rf"@[\w{_ADDRESS_MARKS}-]{{1,63}}(?:\.[\w{_ADDRESS_MARKS}-]{{1,63}}){{0,8}}"
    rf"\.[^\W\d_]{{2,63}}(?![\w{_ADDRESS_MARKS}-])"
)

# Phone pattern: Conservative approach - only match clear phone number formats
# Requires + prefix with country code to avoid false positives
PHONE_PATTERN = re.compile(
    r"\+\d{1,3}[\s.-]?\d{1,4}[\s.-]?\d{1,4}[\s.-]?\d{1,4}[\s.-]?\d{1,4}",
)

# 16-digit card numbers (Visa, MC, Discover...), masked WITHOUT a Luhn check:
# masking a 16-digit identifier that is not a card costs nothing. Amex has its
# own pattern below, with the check.
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
    # The deployment's own providers (points 21 and 39): OpenAI (legacy and
    # project keys), Anthropic, Google API keys and OAuth access tokens.
    r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}|"
    r"\bAIza[0-9A-Za-z_-]{35}\b|"
    r"\bya29\.[0-9A-Za-z_-]{20,}|"
    # JWT: three URL-safe-base64 segments separated by dots; the header almost
    # always starts with ``eyJ`` (encoded ``{"alg``).
    r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"
)

# A bearer credential quoted in free text — an HTTP error echoing its request
# headers. The scheme stays, so the log still says what kind of auth was used.
_BEARER_PATTERN = re.compile(r"(\bBearer\s+)[A-Za-z0-9._~+/=-]{20,}")

# An API key quoted in free text — a JSON body, a header dict, an assignment.
# A field NAMED api_key is already redacted by name; this is the key inside a
# string value (an exception message quoting the request).
_QUOTED_API_KEY_PATTERN = re.compile(
    r"""(["']?(?:x-)?api[_-]?key["']?\s*[:=]\s*["']?)[^"'\s,;}&]{6,}""", re.IGNORECASE
)

# American Express: 15 digits grouped 4-6-5, starting 34 or 37. Masked only when
# the Luhn check passes — fifteen digits are also an order or a parcel number.
AMEX_PATTERN = re.compile(r"\b3[47]\d{2}[-\s]?\d{6}[-\s]?\d{5}\b")

# URL query-string secret pattern (SEC-012). Matches a sensitive parameter and
# its value on a `?`/`&` boundary, e.g. ``?token=abc`` or ``&code=xyz``. Only the
# VALUE is replaced (group 2); the parameter name is kept so the log still shows
# which link was involved. Anchoring on `[?&]` prevents false positives on
# free-text ``code=200``-style content that is not a query parameter.
_URL_QUERY_SECRET_PATTERN = re.compile(
    r"([?&](?:" + "|".join(_SENSITIVE_QUERY_PARAMS) + r")=)([^&\s#\"']+)",
    re.IGNORECASE,
)
# The same shape for the content parameters (escaped: `$search` is one).
_URL_QUERY_CONTENT_PATTERN = re.compile(
    r"([?&](?:" + "|".join(re.escape(name) for name in _CONTENT_QUERY_PARAMS) + r")=)"
    r"([^&\s#\"']+)",
    re.IGNORECASE,
)

# HTTP clients put whole URLs in free-text log messages, including an MCP
# credential inside the PATH (Firecrawl) and names inside article/file paths.
# Query-only filtering cannot see either. Match locations independently of
# field names, including stdlib records carried by ``event``.

# Opaque-token shape (SEC-012): a single URL-safe-base64 / hex run of >= 20 chars
# with no separators. Matches OAuth state (`secrets.token_urlsafe(32)` → 43
# chars) and similar high-entropy secrets, while sparing short application state
# strings like ``running`` / ``pending_approval`` (< 20 chars).
_OPAQUE_TOKEN_PATTERN = re.compile(r"\A[A-Za-z0-9_-]{20,}\Z")


def pseudonymize_email(email: str) -> str:
    """
    Pseudonymize an email address using SHA-256 hash.

    The same input bytes produce the same correlation key without writing the
    address literally. This is an unkeyed digest: a known or guessed address can
    be hashed and matched. The public prefix adds no protection against guessing,
    and the result must not be treated as anonymous data or encryption.

    Args:
        email: Email address to pseudonymize

    Returns:
        Truncated SHA-256 digest with the ``email_hash_`` prefix.

    Example:
        >>> pseudonymize_email("user@example.com")
        "email_hash_b4c9a289323b21a0"
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


def sanitize_url_query(text: str, *, redact_content: bool = False) -> str:
    """Strip the values of sensitive query parameters from any URL in ``text``.

    Neutralizes single-use credentials embedded in logged links — e.g. an email
    verification/reset URL (``.../verify?token=<secret>``) or an OAuth redirect
    (``...?code=<secret>&state=<secret>``). The parameter NAME is preserved so
    the log stays useful; only the value becomes ``[REDACTED]`` (SEC-012).

    Args:
        text: Free-text log value that may contain one or more URLs.
        redact_content: Also withhold the parameters whose value is the
            person's text (``?q=``, ``$search=``) — above DEBUG.

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
    text = _URL_QUERY_SECRET_PATTERN.sub(r"\1[REDACTED]", text)
    if redact_content:
        text = _URL_QUERY_CONTENT_PATTERN.sub(r"\1[REDACTED]", text)
    return text


def sanitize_string(text: str, *, redact_content: bool = False) -> str:
    """
    Sanitize a string by detecting and redacting PII patterns.

    This function scans text for common PII patterns (emails, phones, credit cards, tokens)
    and replaces them with redacted or pseudonymized versions.

    Args:
        text: Text to sanitize
        redact_content: Also withhold what the text QUOTES of the person's data
            — a database row, a refused input, a URL's search term
            (``quoted_content.py``). Enabled above DEBUG.

    Returns:
        Sanitized text with PII redacted

    Example:
        >>> sanitize_string("Contact user@example.com or call +1-555-123-4567")
        "Contact email_hash_a1b2c3d4e5f6g7h8 or call ***-***-4567"
    """
    text = _sanitize_url_locations(text, redact_content=redact_content)

    # Strip single-use credentials embedded in URL query strings (SEC-012):
    # verification/reset links and OAuth redirects carry `?token=`/`?code=`.
    text = sanitize_url_query(text, redact_content=redact_content)

    if redact_content:
        text = redact_quoted_content(text)

    # Replace emails with pseudonymized hashes
    text = _pseudonymize_addresses_in_text(text)

    # Mask phone numbers
    text = PHONE_PATTERN.sub(lambda m: mask_phone(m.group(0)), text)

    # Mask credit cards
    text = CREDIT_CARD_PATTERN.sub(lambda m: mask_credit_card(m.group(0)), text)
    text = AMEX_PATTERN.sub(_mask_amex, text)

    # Redact generic tokens/API keys
    text = TOKEN_PATTERN.sub("[REDACTED_TOKEN]", text)
    text = _BEARER_PATTERN.sub(r"\1[REDACTED_TOKEN]", text)
    text = _QUOTED_API_KEY_PATTERN.sub(r"\1[REDACTED]", text)

    return text


def _pseudonymize_addresses_in_text(text: str) -> str:
    """Pseudonymize every address in free text.

    No ``@``, no address: the substring test is an exact pre-filter, and the
    overwhelming majority of logged strings (event names, codes) carry none.
    """
    if "@" not in text:
        return text
    return EMAIL_PATTERN.sub(lambda m: pseudonymize_email(m.group(0)), text)


def _luhn_valid(digits: str) -> bool:
    """The Luhn checksum every payment card number satisfies."""
    total = 0
    for index, char in enumerate(reversed(digits)):
        digit = int(char) * (2 if index % 2 else 1)
        total += digit - 9 if digit > 9 else digit
    return total % 10 == 0


def _mask_amex(match: re.Match[str]) -> str:
    """Mask an Amex-shaped number when it is one (Luhn), leave it otherwise."""
    digits = re.sub(r"\D", "", match.group(0))
    return mask_credit_card(digits) if _luhn_valid(digits) else match.group(0)


def _sanitize_event_text(text: str, *, redact_content: bool) -> str:
    """Sanitize the structlog ``event`` field without mangling event names.

    Deliberately NOT ``sanitize_string``: that one also applies
    ``TOKEN_PATTERN``, which would rewrite legitimate snake_case event names
    that happen to look like opaque tokens. Only the patterns that cannot match
    an event name are applied — a URL location/query string, an email address, and
    (above DEBUG) an error text's quotation, whose layouts all need spaces or
    punctuation a snake_case name never has.

    Args:
        text: Raw ``event`` value.
        redact_content: Whether the record is above DEBUG.

    Returns:
        The text with URL secrets redacted and addresses pseudonymized.
    """
    text = _sanitize_url_locations(text, redact_content=redact_content)
    text = sanitize_url_query(text, redact_content=redact_content)
    if redact_content:
        text = redact_quoted_content(text)
    return _pseudonymize_addresses_in_text(text)


def _is_count_or_flag(value: Any) -> bool:
    """Whether a value can only be a count, a flag or an absence — never words.

    Args:
        value: A field's value.

    Returns:
        True for ``None``, a boolean or an integer (``bool`` is an ``int``);
        False for a float, which may be a coordinate, and for anything else.
    """
    return value is None or isinstance(value, int)


def _is_address_field(key_lower: str) -> bool:
    """Whether a field is named for an e-mail address (``email``, ``*_emails``…)."""
    return (
        key_lower in PII_FIELD_NAMES
        or key_lower in _ADDRESS_FIELD_NAMES
        or key_lower.endswith(_ADDRESS_FIELD_SUFFIXES)
    )


def _pseudonymize_addresses(value: Any, *, redact_content: bool) -> Any:
    """Pseudonymize every text under an address name, whatever its shape.

    A masked or local-only value is still the person's, so a string is hashed
    whole without being matched first.

    Args:
        value: The field's value.
        redact_content: Whether the record is above DEBUG (for a nested dict).

    Returns:
        Each string hashed, at any depth of any container (as a list); a
        dict sanitized; a count, a flag or an absence as it was.
    """
    if isinstance(value, str):
        return pseudonymize_email(value)
    if isinstance(value, list | tuple | set | frozenset):
        return [_pseudonymize_addresses(item, redact_content=redact_content) for item in value]
    if isinstance(value, dict):
        return sanitize_dict(value, redact_content=redact_content)
    return value


def _sanitize_items(items: Any, *, redact_content: bool) -> list[Any]:
    """Sanitize every item of a container, at any depth, into a list.

    Only a list's strings and dicts used to be read: a tuple, a set, or a list
    of them went to the log as it was, full addresses included (2026-10-25).

    Args:
        items: A list, a tuple, a set or a frozenset.
        redact_content: Whether the record is above DEBUG.

    Returns:
        The sanitized items, in iteration order.
    """
    sanitized: list[Any] = []
    for item in items:
        if isinstance(item, dict):
            sanitized.append(sanitize_dict(item, redact_content=redact_content))
        elif isinstance(item, str):
            sanitized.append(sanitize_string(item, redact_content=redact_content))
        elif isinstance(item, list | tuple | set | frozenset):
            sanitized.append(_sanitize_items(item, redact_content=redact_content))
        else:
            sanitized.append(item)
    return sanitized


def _is_content_field(key_lower: str, value: Any) -> bool:
    """Whether a field carries the person's words, by its name (and its type).

    Args:
        key_lower: The field name, lower-cased.
        value: Its value — a suffix only ever redacts text, and an exact
            content name spares a count, a flag or an absence unless the name
            is a coordinate's.

    Returns:
        True for an exact content name holding anything but a count, a flag or
        an absence (any value at all for a coordinate name), or a content
        suffix holding a string or a list of them.
    """
    if key_lower in CONTENT_FIELD_NAMES:
        return key_lower in _COORDINATE_FIELD_NAMES or not _is_count_or_flag(value)
    return (
        isinstance(value, str | list | tuple | set | frozenset)
        and key_lower.endswith(_CONTENT_FIELD_SUFFIXES)
        and not key_lower.endswith(_IDENTIFIER_PREVIEW_SUFFIX)
    )


def sanitize_dict(data: dict[str, Any], *, redact_content: bool = False) -> dict[str, Any]:
    """
    Recursively sanitize a dictionary using field-based detection.

    This function uses a conservative **field-based approach** to avoid false positives:
    1. Redacts values for known sensitive field names (passwords, tokens, secrets)
    2. Pseudonymizes fields named for an address (``email``, ``*_email``,
       ``*_emails``) whatever the value's shape (emails → hash)
    3. Masks phone field names (phones → last 4 digits)
    4. Recursively processes nested dictionaries and every container
       (lists, tuples, sets), at any depth
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
        # `event` gets narrow transformations (FN-4): it is the only meta field
        # that can carry free text rather than an identifier. A stdlib record
        # routed into structlog puts the whole log MESSAGE here — an access line
        # such as `GET /auth/google/callback?code=..&state=..`, or an SMTP error
        # naming the recipient — and the full sanitizer is not an option (it is
        # exactly what this bypass exists to prevent: `TOKEN_PATTERN` would
        # mangle legitimate event names).
        #
        # The transformations only rewrite shapes a snake_case event name
        # cannot contain: URL locations/queries, quoted error content and
        # addresses with an `@` followed by a dotted domain. Identifiers stay
        # intact; user data and credentials do not reach retained logs.
        if key_lower in STRUCTLOG_META_FIELDS:
            sanitized[key] = (
                _sanitize_event_text(value, redact_content=redact_content)
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
        if redact_content and _is_content_field(key_lower, value):
            sanitized[key] = redact_value(value)
            continue

        # A field named for an address (``email``, ``recipient_email``,
        # ``sample_emails``): its text is pseudonymized whatever its shape
        if _is_address_field(key_lower):
            sanitized[key] = _pseudonymize_addresses(value, redact_content=redact_content)
            continue

        # Check if field is a known phone field
        if key_lower in PHONE_FIELD_NAMES and isinstance(value, str):
            sanitized[key] = mask_phone(value)
            continue

        # Recursively sanitize nested structures, every container at every depth
        if isinstance(value, dict):
            sanitized[key] = sanitize_dict(value, redact_content=redact_content)
        elif isinstance(value, list | tuple | set | frozenset):
            sanitized[key] = _sanitize_items(value, redact_content=redact_content)
        elif isinstance(value, str):
            # Sanitize string values for PII patterns (emails, tokens in free
            # text) and, above DEBUG, what an error text quotes of a row.
            sanitized[key] = sanitize_string(value, redact_content=redact_content)
        else:
            # Keep a number, a flag, an absence or an object as it is
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
