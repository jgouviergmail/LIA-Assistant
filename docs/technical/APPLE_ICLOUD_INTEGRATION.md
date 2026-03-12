# Apple iCloud Integration — Technical Documentation

## Overview

Apple iCloud integration provides 3 connectors as alternatives to Google services:

| Connector | Protocol | Library |
|-----------|----------|---------|
| `APPLE_EMAIL` | IMAP + SMTP | `imap-tools` + `smtplib` |
| `APPLE_CALENDAR` | CalDAV | `caldav[async]` |
| `APPLE_CONTACTS` | CardDAV | `httpx` + `vobject` + `lxml` |

**Authentication**: Apple ID + app-specific password (not OAuth). No token refresh — credentials are static until the user's Apple ID password changes or the app-specific password is revoked.

**Mutual exclusivity**: Only one provider per functional category (`email`, `calendar`, `contacts`) can be ACTIVE at a time. Activating Apple deactivates Google (set to `INACTIVE`, not deleted) and vice versa.

**APPLE_TASKS excluded**: Apple Reminders are inaccessible via standard CalDAV VTODO since iOS 13 (2019). Google Tasks remains the sole Tasks provider.

**Version**: v6.2
**Status**: Implemented (3 connectors + validation + activation endpoints).

---

## Architecture

### Module Structure

```
apps/api/src/domains/connectors/
├── models.py                          # ConnectorType enum (APPLE_EMAIL, APPLE_CALENDAR, APPLE_CONTACTS)
│                                      # CONNECTOR_FUNCTIONAL_CATEGORIES, CATEGORY_DISPLAY_NAMES, _APPLE_CONNECTOR_TYPES
├── schemas.py                         # AppleCredentials, AppleValidationRequest/Response, AppleActivationRequest/Response
├── service.py                         # activate_apple_connectors(), test_apple_connection(), _handle_oauth_connector_callback()
├── router.py                          # POST /apple/validate, POST /apple/activate
├── clients/
│   ├── base_apple_client.py           # BaseAppleClient (ABC): rate limiting, circuit breaker, retry, auth error detection
│   ├── apple_email_client.py          # AppleEmailClient: IMAP search/fetch + SMTP send
│   ├── apple_calendar_client.py       # AppleCalendarClient: CalDAV events CRUD
│   └── apple_contacts_client.py       # AppleContactsClient: CardDAV contacts CRUD
├── normalizers/                       # Protocol-specific → Google API dict format normalizers
│   ├── email_normalizer.py            # IMAP message → Gmail-compatible dict
│   ├── calendar_normalizer.py         # iCalendar VEVENT → Google Calendar event dict
│   └── contacts_normalizer.py         # vCard → Google Contacts person dict
└── provider_resolver.py              # Runtime provider selection (Google vs Apple) per functional category
```

### Design Patterns

- **Composition over inheritance**: `BaseAppleClient` composes `RedisRateLimiter` + `CircuitBreaker` (not subclassed)
- **Normalizer pattern**: Each client has a companion normalizer that converts protocol-native data to Google API dict format. Domain tools (email, calendar, contacts) remain provider-agnostic
- **Provider resolver**: At tool execution time, resolves which client to instantiate based on user's active connector for the functional category
- **Protocol classes (PEP 544)**: Structural typing for client interfaces — tools depend on protocols, not concrete classes

### BaseAppleClient

Abstract base providing shared infrastructure for all 3 Apple clients:

- **Rate limiting**: Redis sliding window (`client_rate_limit_apple_per_second`, default 5/s)
- **Circuit breaker**: Via `get_circuit_breaker(f"apple_{connector_type}")` — 3 failures to open, 10s timeout
- **Retry**: Exponential backoff (default 3 retries, base delay 1s)
- **Auth error detection**: IMAP patterns (`LOGIN failed`, `AUTHENTICATIONFAILED`) and HTTP status codes (401, 403)
- **Credential revocation**: On auth failure, connector status set to `ERROR` via `ConnectorRepository`

Key classes: `BaseAppleClient` (ABC), `AppleAuthenticationError` (exception).

---

## Protocols & Libraries

### Email (IMAP + SMTP)

- **Read**: `imap-tools` for IMAP search/fetch, wrapped via `asyncio.to_thread()` (synchronous library)
- **Send**: `smtplib` with STARTTLS, also wrapped via `asyncio.to_thread()`
- Server: `imap.mail.me.com:993` (SSL) / `smtp.mail.me.com:587` (STARTTLS)

### Calendar (CalDAV)

- **Library**: `caldav[async]` — native async support
- Server: `https://caldav.icloud.com` (discovery URL, actual server is partitioned as `pXX-caldav.icloud.com`)

### Contacts (CardDAV)

- **Library**: Custom implementation using `httpx` (HTTP), `vobject` (vCard parsing), `lxml` (XML/WebDAV)
- Server: `https://contacts.icloud.com` (discovery URL, actual server is partitioned as `pXX-contacts.icloud.com`)
- No existing CardDAV Python library met the async + reliability requirements for iCloud

---

## Known Limitations

1. **No Tasks/Reminders**: Apple discontinued CalDAV VTODO support since iOS 13 (2019). `APPLE_TASKS` is explicitly excluded from `ConnectorType`
2. **CalDAV `event_by_uid()` broken**: iCloud does not reliably support UID-based lookup. Workaround: `search()` with date range + client-side UID filter
3. **CardDAV search unreliable**: iCloud's server-side REPORT search returns inconsistent results. Workaround: fetch all contacts → Redis cache (`apple_contacts_cache_ttl`, default 600s) → local filter
4. **SMTP limits**: 1000 messages/day, 500 recipients/message, 20MB/message (Apple-imposed, configured via `apple_smtp_*` settings)
5. **IMAP MOVE**: Not always supported by iCloud. Fallback: COPY to destination + DELETE from source
6. **CalDAV no PATCH**: iCloud does not support partial updates. Must GET full event → modify → PUT
7. **Recurring events**: `expand=True` is unreliable on iCloud CalDAV for recurring event expansion
8. **vCard 3.0 only**: iCloud CardDAV serves vCard 3.0 format (not 4.0)
9. **Contact photos**: Base64-encoded, up to 224KB per contact. Excluded from bulk fetch for performance

---

## App-Specific Password Setup

Apple iCloud connectors require an **app-specific password** (not the user's Apple ID password).

**Prerequisites**:
- Two-Factor Authentication (2FA) must be enabled on the Apple account

**Generation**:
1. Go to [appleid.apple.com](https://appleid.apple.com) > Sign-In and Security > App-Specific Passwords
2. Click "Generate an app-specific password"
3. Label it (e.g., "LIA")
4. Copy the generated password

**Format**: `xxxx-xxxx-xxxx-xxxx` (16 lowercase letters in 4 groups)

**Constraints**:
- Maximum 25 active app-specific passwords per Apple ID
- No expiration date — valid until the Apple ID password is changed or the app-specific password is manually revoked
- Revoking the Apple ID password invalidates ALL app-specific passwords

---

## iCloud Endpoints

| Protocol | Host | Port | Security |
|----------|------|------|----------|
| IMAP | `imap.mail.me.com` | 993 | SSL/TLS |
| SMTP | `smtp.mail.me.com` | 587 | STARTTLS |
| CalDAV | `caldav.icloud.com` | 443 | HTTPS |
| CardDAV | `contacts.icloud.com` | 443 | HTTPS |

**Important**: The public hostnames are discovery URLs. Actual servers are partitioned (e.g., `p73-caldav.icloud.com`). Always use the discovery URLs and let protocol-level redirection resolve to the correct partition.

---

## Mutual Exclusivity

Defined in `CONNECTOR_FUNCTIONAL_CATEGORIES` (`models.py`):

```python
CONNECTOR_FUNCTIONAL_CATEGORIES = {
    "email":    frozenset({ConnectorType.GOOGLE_GMAIL, ConnectorType.APPLE_EMAIL}),
    "calendar": frozenset({ConnectorType.GOOGLE_CALENDAR, ConnectorType.APPLE_CALENDAR}),
    "contacts": frozenset({ConnectorType.GOOGLE_CONTACTS, ConnectorType.APPLE_CONTACTS}),
}
```

**Behavior**:
- `activate_apple_connectors()`: For each requested Apple connector, finds conflicting Google connector via `get_conflicting_connector_type()` and sets it to `INACTIVE`
- `_handle_oauth_connector_callback()`: When a Google OAuth connector is activated, deactivates conflicting Apple connector
- Deactivation sets status to `INACTIVE` (not `REVOKED` or deleted) — credentials are preserved for easy re-activation

Helper functions: `get_functional_category()`, `get_conflicting_connector_type()` (both in `models.py`).

**Legacy GMAIL type**: The deprecated `ConnectorType.GMAIL` is NOT in `CONNECTOR_FUNCTIONAL_CATEGORIES` (which enforces 2-member categories). Instead, `provider_resolver.py` defines `_LEGACY_CONNECTOR_ALIASES` to map `GMAIL → GOOGLE_GMAIL` at resolution time.

---

## Configuration (.env)

All settings in `ConnectorsSettings` (`core/config/connectors.py`):

| Setting | Default | Description |
|---------|---------|-------------|
| `APPLE_IMAP_HOST` | `imap.mail.me.com` | IMAP server hostname |
| `APPLE_IMAP_PORT` | `993` | IMAP server port (SSL) |
| `APPLE_SMTP_HOST` | `smtp.mail.me.com` | SMTP server hostname |
| `APPLE_SMTP_PORT` | `587` | SMTP server port (STARTTLS) |
| `APPLE_SMTP_DAILY_LIMIT` | `1000` | Max messages per day (Apple-imposed) |
| `APPLE_SMTP_MAX_RECIPIENTS` | `500` | Max recipients per message |
| `APPLE_SMTP_MAX_SIZE_MB` | `20` | Max message size in MB |
| `APPLE_CALDAV_URL` | `https://caldav.icloud.com` | CalDAV discovery URL |
| `APPLE_CARDDAV_URL` | `https://contacts.icloud.com` | CardDAV discovery URL |
| `APPLE_CONNECTION_TIMEOUT` | `30.0` | Connection timeout (seconds) |
| `CLIENT_RATE_LIMIT_APPLE_PER_SECOND` | `5` | Max API requests per second per user |
| `APPLE_CONTACTS_CACHE_TTL` | `600` | Full contacts list Redis cache TTL (seconds) |
| `APPLE_EMAIL_MESSAGE_CACHE_TTL` | `60` | Individual IMAP message Redis cache TTL (seconds) |

---

## API Endpoints

Both endpoints are under `/api/v1/connectors/`:

### POST `/apple/validate`

Test Apple credentials without activating any service.

- **Request**: `AppleValidationRequest` — `apple_id`, `app_password`
- **Response**: `AppleValidationResponse` — `valid: bool`, `message: str`
- Tests all 3 protocols (IMAP, CalDAV, CardDAV) to verify the credentials work

### POST `/apple/activate`

Activate one or more Apple iCloud connectors.

- **Request**: `AppleActivationRequest` — `apple_id`, `app_password`, `services: list[ConnectorType]`
- **Response**: `AppleActivationResponse` — per-service activation results
- Credentials are Fernet-encrypted before storage (same pattern as OAuth tokens)
- Conflicting Google connectors are automatically set to `INACTIVE`

---

## N+1 IMAP Solution

IMAP requires a separate connection per message fetch, creating an N+1 problem for `search_emails()` → multiple `get_message()` calls.

**Solution**: Redis message caching in `AppleEmailClient`.

1. `search_emails()` fetches messages from IMAP, caches each in Redis with TTL (`apple_email_message_cache_ttl`, default 60s)
2. `get_message()` reads from Redis cache first; on cache miss, fetches from IMAP
3. Cache key: `apple_email_msg:{user_id}:{message_uid}`

This reduces IMAP connections from N+1 to 1 for typical list → detail workflows.

---

## Credential Revocation

`BaseAppleClient` detects authentication failures at the protocol level:

- **IMAP**: Checks error messages against `_IMAP_AUTH_ERRORS` (`LOGIN failed`, `AUTHENTICATIONFAILED`, `Invalid credentials`)
- **HTTP** (CalDAV/CardDAV): Checks status codes against `_HTTP_AUTH_STATUS_CODES` (401, 403)

**On detection**:
1. `AppleAuthenticationError` is raised (not retryable — skips retry loop)
2. `_handle_auth_failure()` sets connector status to `ConnectorStatus.ERROR`
3. User must re-enter credentials via the Apple activation form in Settings > Connectors

**Common causes**: Apple ID password changed (invalidates all app-specific passwords), app-specific password manually revoked, Apple account locked.
