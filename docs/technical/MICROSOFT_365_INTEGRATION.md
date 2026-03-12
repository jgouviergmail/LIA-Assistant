# Microsoft 365 Integration — Technical Documentation

## Overview

Microsoft 365 integration provides 4 connectors via the **Microsoft Graph REST API v1.0**:

| Connector | Graph API Resource | Scopes |
|-----------|-------------------|--------|
| `MICROSOFT_OUTLOOK` | `/me/messages` | `Mail.Read`, `Mail.ReadWrite`, `Mail.Send` |
| `MICROSOFT_CALENDAR` | `/me/events`, `/me/calendarView` | `Calendars.Read`, `Calendars.ReadWrite` |
| `MICROSOFT_CONTACTS` | `/me/contacts` | `Contacts.Read`, `Contacts.ReadWrite` |
| `MICROSOFT_TASKS` | `/me/todo/lists`, `/me/todo/lists/{id}/tasks` | `Tasks.Read`, `Tasks.ReadWrite` |

All connectors share `User.Read` and `offline_access` base scopes.

**Authentication**: OAuth 2.0 via **Microsoft Entra ID** (formerly Azure AD) with PKCE (S256). Multi-tenant transparent: `tenant=common` accepts both personal accounts (outlook.com, hotmail.com, live.com) and enterprise accounts (Azure AD). Microsoft detects the account type from the email entered by the user.

**Mutual exclusivity**: 3-way (Google / Apple / Microsoft) — only one provider per functional category (`email`, `calendar`, `contacts`, `tasks`) can be ACTIVE at a time. Activating Microsoft deactivates Google and Apple (set to `INACTIVE`, not deleted) and vice versa.

**Version**: v6.2
**Status**: Implemented (4 connectors + normalizers + preferences + OAuth flow).

---

## Architecture

### Module Structure

```
apps/api/src/domains/connectors/
├── models.py                          # ConnectorType enum (MICROSOFT_OUTLOOK, MICROSOFT_CALENDAR, ...)
│                                      # CONNECTOR_FUNCTIONAL_CATEGORIES (3-way), _MICROSOFT_CONNECTOR_TYPES
├── schemas.py                         # ConnectorCredentials (shared OAuth credentials)
├── service.py                         # OAuth flow methods per Microsoft connector
├── router.py                          # OAuth authorize/callback routes per connector
├── clients/
│   ├── base_microsoft_client.py       # BaseMicrosoftClient(BaseOAuthClient): OData pagination, error parsing
│   ├── microsoft_outlook_client.py    # MicrosoftOutlookClient: email search/read/send/reply/forward/trash
│   ├── microsoft_calendar_client.py   # MicrosoftCalendarClient: calendar + event CRUD, calendarView
│   ├── microsoft_contacts_client.py   # MicrosoftContactsClient: contact search/list/CRUD
│   └── microsoft_tasks_client.py      # MicrosoftTasksClient: task list + task CRUD
├── clients/normalizers/
│   ├── microsoft_email_normalizer.py  # Graph message → Gmail-compatible dict
│   ├── microsoft_calendar_normalizer.py # Graph event → Google Calendar event dict
│   ├── microsoft_contacts_normalizer.py # Graph contact → Google People person dict
│   └── microsoft_tasks_normalizer.py  # Graph To Do task → Google Tasks task dict
├── preferences/
│   ├── schemas.py                     # MicrosoftCalendarPreferences, MicrosoftTasksPreferences
│   └── registry.py                    # Connector type → preferences schema mapping
├── provider_resolver.py              # Runtime provider selection (Google vs Apple vs Microsoft)
apps/api/src/core/oauth/providers/
└── microsoft.py                       # MicrosoftOAuthProvider with 4 factory methods
```

### Design Patterns

- **Template Method (BaseOAuthClient)**: `BaseMicrosoftClient` inherits from `BaseOAuthClient[ConnectorType]` and overrides 3 hooks for Microsoft-specific behavior
- **Normalizer pattern**: Each client has a companion normalizer that converts Microsoft Graph data to Google API dict format. Domain tools (email, calendar, contacts, tasks) remain provider-agnostic
- **Provider resolver**: At tool execution time, resolves which client to instantiate based on user's active connector for the functional category
- **Factory methods**: `MicrosoftOAuthProvider` provides 4 `@classmethod` factories (`for_outlook`, `for_calendar`, `for_contacts`, `for_tasks`)

### BaseMicrosoftClient

Inherits from `BaseOAuthClient` (Template Method pattern). Provides shared functionality for all 4 Microsoft clients:

- **Rate limiting**: Redis sliding window (`client_rate_limit_microsoft_per_second`, default 4/s)
- **Token management**: Automatic refresh via `BaseOAuthClient._refresh_access_token()`
- **HTTP client**: Connection pooling via `httpx.AsyncClient` (inherited)
- **Circuit breaker**: Via `get_circuit_breaker(f"microsoft_{connector_type}")` (inherited)
- **Retry**: Exponential backoff with 3 attempts (inherited), honors `Retry-After` header

**3 hook overrides**:

| Hook | Behavior |
|------|----------|
| `_parse_error_detail()` | Parses Microsoft Graph JSON error format: `{"error": {"code": "...", "message": "..."}}` |
| `_get_retry_delay()` | Honors `Retry-After` header on 429 responses, falls back to exponential backoff |
| `_enrich_request_params()` | Default pass-through (safety net for subclasses) |

**Microsoft-specific addition**: `_get_paginated_odata()` — handles `@odata.nextLink` pagination pattern. Uses `_make_request_full_url()` for subsequent pages since Microsoft provides full URLs in `@odata.nextLink`.

---

## OAuth Flow

### MicrosoftOAuthProvider

Dataclass in `core/oauth/providers/microsoft.py` with 4 factory methods:

```python
MicrosoftOAuthProvider.for_outlook(settings)   # Mail.Read, Mail.ReadWrite, Mail.Send
MicrosoftOAuthProvider.for_calendar(settings)   # Calendars.Read, Calendars.ReadWrite
MicrosoftOAuthProvider.for_contacts(settings)   # Contacts.Read, Contacts.ReadWrite
MicrosoftOAuthProvider.for_tasks(settings)      # Tasks.Read, Tasks.ReadWrite
```

### Endpoints

| Endpoint | URL |
|----------|-----|
| Authorization | `https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize` |
| Token | `https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token` |
| Revocation | **None** (Microsoft has no revocation endpoint) |
| Graph API | `https://graph.microsoft.com/v1.0` |

### API Routes

Each connector has its own authorize/callback pair under `/api/v1/connectors/`:

| Route | ConnectorType |
|-------|---------------|
| `/microsoft-outlook/authorize` → `/microsoft-outlook/callback` | `MICROSOFT_OUTLOOK` |
| `/microsoft-calendar/authorize` → `/microsoft-calendar/callback` | `MICROSOFT_CALENDAR` |
| `/microsoft-contacts/authorize` → `/microsoft-contacts/callback` | `MICROSOFT_CONTACTS` |
| `/microsoft-tasks/authorize` → `/microsoft-tasks/callback` | `MICROSOFT_TASKS` |

---

## Normalizers

Each normalizer converts Microsoft Graph response objects to the dict format expected by domain tools (same format as Google API clients):

| Module | Key Functions | Purpose |
|--------|---------------|---------|
| `microsoft_email_normalizer.py` | `normalize_graph_message()`, `normalize_graph_folder()`, `build_search_filter()` | Graph message → Gmail dict. Maps folder names (inbox→INBOX, sentitems→SENT, etc.). Strips HTML for snippet generation |
| `microsoft_calendar_normalizer.py` | `normalize_graph_event()`, `normalize_graph_calendar()` | Graph event → Google Calendar dict. Maps attendee response statuses (tentativelyAccepted→tentative, etc.) |
| `microsoft_contacts_normalizer.py` | `normalize_graph_contact()`, `build_contact_body()`, `build_contact_update_body()` | Graph contact → Google People dict. Maps phone types (business→work) and address types |
| `microsoft_tasks_normalizer.py` | `normalize_graph_task()`, `normalize_graph_task_list()`, `build_task_body()` | Graph To Do task → Google Tasks dict. Maps statuses (notStarted/inProgress/waitingOnOthers/deferred→needsAction, completed→completed) |

---

## Mutual Exclusivity

Defined in `CONNECTOR_FUNCTIONAL_CATEGORIES` (`models.py`):

```python
CONNECTOR_FUNCTIONAL_CATEGORIES = {
    "email":    frozenset({ConnectorType.GOOGLE_GMAIL, ConnectorType.APPLE_EMAIL, ConnectorType.MICROSOFT_OUTLOOK}),
    "calendar": frozenset({ConnectorType.GOOGLE_CALENDAR, ConnectorType.APPLE_CALENDAR, ConnectorType.MICROSOFT_CALENDAR}),
    "contacts": frozenset({ConnectorType.GOOGLE_CONTACTS, ConnectorType.APPLE_CONTACTS, ConnectorType.MICROSOFT_CONTACTS}),
    "tasks":    frozenset({ConnectorType.GOOGLE_TASKS, ConnectorType.MICROSOFT_TASKS}),
}
```

**3-way exclusivity** for email, calendar, and contacts. **2-way** for tasks (no Apple Tasks — Apple Reminders are inaccessible via CalDAV since iOS 13).

Helper functions: `get_conflicting_connector_types()` (plural, returns frozenset of ALL conflicting types), `get_conflicting_connector_type()` (singular, returns first match — legacy convenience).

**Behavior**: When a Microsoft OAuth callback succeeds, `_handle_oauth_connector_callback()` deactivates conflicting Google and Apple connectors (status set to `INACTIVE`, credentials preserved).

---

## Preferences

Two connector-specific preference schemas in `preferences/schemas.py`:

### MicrosoftCalendarPreferences

- `default_calendar_name: str | None` — Name of the default calendar for creating events. Falls back to "primary" if not set.

### MicrosoftTasksPreferences

- `default_task_list_name: str | None` — Name of the default task list. Falls back to the first available task list if not set.

Registered in `preferences/registry.py` mapping `ConnectorType.MICROSOFT_CALENDAR` and `ConnectorType.MICROSOFT_TASKS` to their respective schemas.

---

## Configuration (.env)

**Security settings** (`core/config/security.py`):

| Setting | Default | Description |
|---------|---------|-------------|
| `MICROSOFT_CLIENT_ID` | `""` | Microsoft Entra ID application (client) ID |
| `MICROSOFT_CLIENT_SECRET` | `""` | Microsoft Entra ID client secret |
| `MICROSOFT_TENANT_ID` | `common` | Tenant ID (`common` = multi-tenant personal + enterprise) |

**Connector settings** (`core/config/connectors.py`):

| Setting | Default | Description |
|---------|---------|-------------|
| `CLIENT_RATE_LIMIT_MICROSOFT_PER_SECOND` | `4` | Max Graph API requests per second per user |

---

## Known Limitations & Gotchas

1. **Token refresh requires scope**: Unlike Google, Microsoft's token refresh endpoint requires the `scope` parameter. The OAuth flow handler includes scopes in refresh requests
2. **No revocation endpoint**: Microsoft does not provide a standard OAuth token revocation endpoint. `revocation_endpoint` is explicitly `None` on `MicrosoftOAuthProvider`. Users must revoke access via [myapps.microsoft.com](https://myapps.microsoft.com)
3. **OData pagination (`@odata.nextLink`)**: Microsoft Graph returns `@odata.nextLink` as a **full URL** (not a page token). `_get_paginated_odata()` uses `_make_request_full_url()` to follow these links
4. **`$search` uses KQL**: The `$search` query parameter uses Keyword Query Language (KQL), not plain text. Queries must be wrapped in double quotes (e.g., `$search="subject:meeting"`)
5. **`calendarView` for date ranges**: Use `/me/calendarView?startDateTime=...&endDateTime=...` instead of `$filter` on `/me/events` for date-range queries. `calendarView` automatically expands recurring events
6. **Message bodies are HTML by default**: Microsoft Graph returns `body.content` in HTML format by default. Use `Prefer: outlook.body-content-type="text"` header for plain text
7. **Task status mapping lossy**: Microsoft To Do has 5 statuses (`notStarted`, `inProgress`, `completed`, `waitingOnOthers`, `deferred`) but Google Tasks only has 2 (`needsAction`, `completed`). All non-completed Microsoft statuses map to `needsAction`, losing granularity
8. **No `@default` task list**: Unlike Google Tasks which has a magic `@default` list ID, Microsoft To Do requires listing all task lists first to find the default one
9. **No subtask hierarchy**: Microsoft To Do supports checklist items within tasks, but these are not exposed as nested tasks. The normalizer flattens to a single level matching Google Tasks' flat structure
10. **Multi-tenant transparent**: The `common` tenant endpoint works for both personal Microsoft accounts and Azure AD enterprise accounts. No configuration change needed per account type — Microsoft handles detection automatically
