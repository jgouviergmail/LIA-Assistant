# Guide API REST - LIA

**Version** : 2.0
**Dernière mise à jour** : 2026-03-08
**Statut** : ✅ Stable

> **Documentation complète de l'API REST FastAPI v1**
>
> Base URL: `http://localhost:8000/api/v1`
> Documentation interactive: `http://localhost:8000/docs` (Swagger UI)
> OpenAPI Schema: `http://localhost:8000/openapi.json`

---

## Table des Matières

1. [Vue d'Ensemble](#vue-densemble)
2. [Authentication & Sessions](#authentication--sessions)
3. [Chat & Agents](#chat--agents)
4. [Connectors (OAuth)](#connectors-oauth)
5. [Conversations](#conversations)
6. [Users](#users)
7. [Admin Endpoints](#admin-endpoints)
8. [MCP Admin](#mcp-admin)
9. [MCP User (Per-User)](#mcp-user-per-user)
10. [Channels (Telegram)](#channels-telegram)
11. [Heartbeat (Notifications Proactives)](#heartbeat-notifications-proactives)
12. [Scheduled Actions (Actions Planifiees)](#scheduled-actions-actions-planifiees)
13. [Error Handling](#error-handling)
14. [Rate Limiting](#rate-limiting)
15. [SSE Streaming](#sse-streaming)
16. [Security (OWASP 2024)](#security-owasp-2024)
17. [Examples cURL](#examples-curl)
18. [Client SDKs](#client-sdks)
19. [Troubleshooting](#troubleshooting)

---

## Vue d'Ensemble

### Architecture API

```
FastAPI v3.0 (async/await)
├── BFF Pattern (Backend-For-Frontend)
│   ├── Sessions HTTP-only cookies (XSS protection)
│   ├── Redis SessionStore (data minimization GDPR)
│   └── No JWT tokens exposed to frontend
├── OpenAPI 3.1.0 (automatic documentation)
├── Pydantic V2 (validation + serialization)
├── PostgreSQL (persistence)
└── Redis (cache + sessions)
```

### Base URLs

| Environment | Base URL | Documentation |
|-------------|----------|---------------|
| **Development** | `http://localhost:8000/api/v1` | `http://localhost:8000/docs` |
| **Staging** | `https://staging-api.yourdomain.com/api/v1` | `https://staging-api.yourdomain.com/docs` |
| **Production** | `https://api.yourdomain.com/api/v1` | `https://api.yourdomain.com/docs` |

### API Versioning

```
/api/v1/...  # Current stable version
/api/v2/...  # Future version (breaking changes)
```

**Versioning Strategy:**
- Semantic versioning dans headers: `X-API-Version: 1.0.0`
- URL versioning pour breaking changes (`/v1` → `/v2`)
- Backward compatibility dans v1 (additive changes OK)

### Response Format Standard

**Success Response:**

```json
{
  "id": "uuid",
  "field1": "value1",
  "field2": 123,
  "created_at": "2025-11-14T10:30:00Z",
  "updated_at": "2025-11-14T10:30:00Z"
}
```

**List Response:**

```json
{
  "items": [...],
  "total": 42,
  "page": 1,
  "page_size": 20,
  "has_next": true
}
```

**Error Response:**

```json
{
  "detail": "Error message",
  "error_code": "AUTH_001",
  "timestamp": "2025-11-14T10:30:00Z",
  "request_id": "req_abc123"
}
```

---

## Authentication & Sessions

### POST /auth/register

**Register new user with BFF Pattern (HTTP-only cookie)**

**Request:**

```http
POST /api/v1/auth/register
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "SecurePassword123!",
  "full_name": "John Doe",
  "remember_me": false,
  "timezone": "Europe/Paris",
  "language": "fr"
}
```

**Response:** `201 Created`

```json
{
  "user": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "user@example.com",
    "full_name": "John Doe",
    "is_active": false,
    "is_verified": false,
    "timezone": "Europe/Paris",
    "language": "fr",
    "created_at": "2025-11-14T10:30:00Z"
  },
  "message": "Registration successful"
}
```

**Set-Cookie Header:**

```
session_id=xxx; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=86400
```

**Security (BFF Pattern):**
- ✅ No JWT tokens in response body
- ✅ Session stored server-side in Redis
- ✅ HTTP-only cookie prevents XSS
- ✅ SameSite=Lax prevents CSRF
- ✅ Password hashed with bcrypt (rounds=12)

**Validation Rules:**
- Email: Valid email format, unique
- Password: Min 8 chars, 1 uppercase, 1 lowercase, 1 digit
- Timezone: IANA timezone name (e.g., "Europe/Paris")
- Language: ISO 639-1 code (fr, en, es, de, it, zh-CN)

---

### POST /auth/login

**Login with email/password and create session**

**Request:**

```http
POST /api/v1/auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "SecurePassword123!",
  "remember_me": true
}
```

**Response:** `200 OK`

```json
{
  "user": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "user@example.com",
    "full_name": "John Doe",
    "is_active": true,
    "is_verified": true,
    "timezone": "Europe/Paris",
    "language": "fr"
  },
  "message": "Login successful"
}
```

**Set-Cookie Header (remember_me=true):**

```
session_id=xxx; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=2592000  # 30 days
```

**Set-Cookie Header (remember_me=false):**

```
session_id=xxx; HttpOnly; Secure; SameSite=Lax; Path=/;  # Session cookie (expires on browser close)
```

**Errors:**
- `401 Unauthorized`: Invalid credentials
- `403 Forbidden`: Account not verified (email verification required)

---

### POST /auth/logout

**Logout and invalidate session**

**Request:**

```http
POST /api/v1/auth/logout
Cookie: session_id=xxx
```

**Response:** `200 OK`

```json
{
  "message": "Logout successful"
}
```

**Behavior:**
- Deletes session from Redis
- Clears session_id cookie
- Single session logout (use `/auth/logout-all` for all devices)

---

### POST /auth/logout-all

**Logout from all devices (invalidate all user sessions)**

**Request:**

```http
POST /api/v1/auth/logout-all
Cookie: session_id=xxx
```

**Response:** `200 OK`

```json
{
  "message": "Logged out from all devices",
  "sessions_invalidated": 3
}
```

**Use Case:** User wants to logout from all devices (security)

---

### GET /auth/me

**Get current authenticated user info**

**Request:**

```http
GET /api/v1/auth/me
Cookie: session_id=xxx
```

**Response:** `200 OK`

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com",
  "full_name": "John Doe",
  "is_active": true,
  "is_verified": true,
  "is_superuser": false,
  "timezone": "Europe/Paris",
  "language": "fr",
  "picture_url": "https://lh3.googleusercontent.com/...",
  "oauth_provider": "google",
  "created_at": "2025-11-01T10:00:00Z",
  "updated_at": "2025-11-14T10:30:00Z"
}
```

**Errors:**
- `401 Unauthorized`: No session cookie or invalid session

---

### POST /auth/password-reset/request

**Request password reset email**

**Request:**

```http
POST /api/v1/auth/password-reset/request
Content-Type: application/json

{
  "email": "user@example.com"
}
```

**Response:** `200 OK`

```json
{
  "message": "Password reset email sent"
}
```

**Behavior:**
- Sends email with reset token (expires in 1h)
- Always returns 200 OK (even if email doesn't exist - security)

---

### POST /auth/password-reset/confirm

**Confirm password reset with token**

**Request:**

```http
POST /api/v1/auth/password-reset/confirm
Content-Type: application/json

{
  "token": "abc123def456",
  "new_password": "NewSecurePassword123!"
}
```

**Response:** `200 OK`

```json
{
  "message": "Password reset successful"
}
```

**Errors:**
- `400 Bad Request`: Invalid or expired token

---

## Chat & Agents

### POST /agents/chat/stream

**Stream chat response with SSE (Server-Sent Events)**

**Request:**

```http
POST /api/v1/agents/chat/stream
Cookie: session_id=xxx
Content-Type: application/json

{
  "message": "Trouve-moi les contacts dont le prénom commence par 'Jean'",
  "conversation_id": "optional-conversation-uuid",
  "metadata": {
    "client_version": "1.0.0",
    "platform": "web"
  }
}
```

**Response:** `200 OK` (SSE stream)

```
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive

event: start
data: {"run_id": "run_abc123", "conversation_id": "uuid", "session_id": "session_xyz"}

event: token
data: {"content": "Je", "delta": "Je"}

event: token
data: {"content": " vais", "delta": " vais"}

event: token
data: {"content": " chercher", "delta": " chercher"}

event: metadata
data: {"intention": "actionable", "confidence": 0.95, "node_name": "router"}

event: tool_call_start
data: {"tool_name": "search_contacts_tool", "tool_call_id": "call_123"}

event: tool_call_end
data: {"tool_name": "search_contacts_tool", "tool_call_id": "call_123", "status": "success"}

event: token
data: {"content": " J'ai trouvé 3 contacts:", "delta": " J'ai trouvé 3 contacts:"}

event: done
data: {"run_id": "run_abc123", "total_tokens": 1250, "cost_eur": 0.005}

event: end
data: {}
```

**SSE Event Types:**

| Event | Description | Data Schema |
|-------|-------------|-------------|
| `start` | Stream started | `{run_id, conversation_id, session_id}` |
| `token` | Token generated | `{content, delta}` |
| `metadata` | Node metadata | `{intention, confidence, node_name}` |
| `tool_call_start` | Tool invocation started | `{tool_name, tool_call_id}` |
| `tool_call_end` | Tool invocation ended | `{tool_name, status}` |
| `hitl_approval_request` | HITL approval required | `{action_requests, review_configs}` |
| `plan_approval_request` | Plan approval required (Phase 8) | `{plan_summary, approval_question}` |
| `done` | Generation complete | `{run_id, total_tokens, cost_eur}` |
| `error` | Error occurred | `{error_type, message}` |
| `end` | Stream closed | `{}` |

**SSE Heartbeat:**

```
: heartbeat  # Comment line every 15s to keep connection alive
```

**Error Events:**

```
event: error
data: {"error_type": "RATE_LIMIT_EXCEEDED", "message": "Too many requests", "retry_after": 60}

event: end
data: {}
```

**Client Reconnection:**

```javascript
const eventSource = new EventSource('/api/v1/agents/chat/stream', {
  withCredentials: true  // Include cookies
});

eventSource.addEventListener('error', (e) => {
  if (eventSource.readyState === EventSource.CLOSED) {
    // Reconnect after 3s
    setTimeout(() => location.reload(), 3000);
  }
});
```

**HITL Plan Approval Flow (Phase 8):**

```
1. User: "Supprime tous mes contacts"
2. event: plan_approval_request
   data: {
     "plan_summary": {
       "steps": [{"type": "TOOL", "tool_name": "delete_all_contacts"}],
       "estimated_cost_eur": 0.05
     },
     "approval_question": "Je prévois de supprimer TOUS vos contacts. Êtes-vous certain(e) ?"
   }
3. User responds: "oui, confirme"
4. Backend resumes graph execution
5. event: tool_call_start / tool_call_end
6. event: done
```

---

### GET /agents/chat/history

**Get chat history (paginated)**

**Request:**

```http
GET /api/v1/agents/chat/history?page=1&page_size=20
Cookie: session_id=xxx
```

**Response:** `200 OK`

```json
{
  "messages": [
    {
      "id": "msg_uuid_1",
      "role": "user",
      "content": "Bonjour",
      "metadata": {"run_id": "run_123"},
      "created_at": "2025-11-14T10:00:00Z"
    },
    {
      "id": "msg_uuid_2",
      "role": "assistant",
      "content": "Bonjour! Comment puis-je vous aider?",
      "metadata": {"run_id": "run_123", "intention": "conversation"},
      "created_at": "2025-11-14T10:00:05Z"
    }
  ],
  "total": 42,
  "page": 1,
  "page_size": 20,
  "has_next": true
}
```

---

## Connectors (OAuth)

### GET /connectors

**List user's connectors**

**Request:**

```http
GET /api/v1/connectors
Cookie: session_id=xxx
```

**Response:** `200 OK`

```json
{
  "connectors": [
    {
      "id": "connector_uuid",
      "connector_type": "google_contacts",
      "status": "active",
      "scopes": [
        "https://www.googleapis.com/auth/contacts.readonly"
      ],
      "metadata": {
        "email": "user@example.com",
        "connection_count": 450
      },
      "created_at": "2025-11-01T10:00:00Z",
      "updated_at": "2025-11-14T10:00:00Z"
    }
  ],
  "total": 1
}
```

---

### GET /connectors/types

**List supported connector types**

**Request:**

```http
GET /api/v1/connectors/types
```

**Response:** `200 OK`

```json
[
  "gmail",
  "google_drive",
  "google_calendar",
  "google_contacts",
  "slack",
  "notion",
  "github"
]
```

---

### POST /connectors/oauth/google-contacts/initiate

**Initiate Google Contacts OAuth flow**

**Request:**

```http
POST /api/v1/connectors/oauth/google-contacts/initiate
Cookie: session_id=xxx
Content-Type: application/json

{
  "scopes": [
    "https://www.googleapis.com/auth/contacts.readonly"
  ]
}
```

**Response:** `200 OK`

```json
{
  "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth?client_id=...&redirect_uri=...&scope=...&state=...",
  "state": "random_state_token"
}
```

**Client Flow:**

```javascript
// 1. Initiate OAuth
const response = await fetch('/api/v1/connectors/oauth/google-contacts/initiate', {
  method: 'POST',
  credentials: 'include',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({scopes: [...]})
});
const {authorization_url} = await response.json();

// 2. Redirect to Google OAuth
window.location.href = authorization_url;

// 3. Google redirects back to: /api/v1/connectors/oauth/google-contacts/callback?code=...&state=...
// Backend handles callback and creates connector

// 4. Frontend receives redirect to success page
```

---

### GET /connectors/oauth/google-contacts/callback

**OAuth callback handler (automatic - not called by client)**

**Request:**

```http
GET /api/v1/connectors/oauth/google-contacts/callback?code=xxx&state=yyy
Cookie: session_id=xxx
```

**Response:** `303 See Other`

```
Location: https://app.yourdomain.com/connectors/success?connector_id=uuid
```

**Errors:**
- `400 Bad Request`: Missing or invalid state parameter
- `401 Unauthorized`: No active session
- `500 Internal Server Error`: OAuth token exchange failed

---

### PATCH /connectors/{connector_id}

**Update connector status or metadata**

**Request:**

```http
PATCH /api/v1/connectors/550e8400-e29b-41d4-a716-446655440000
Cookie: session_id=xxx
Content-Type: application/json

{
  "status": "inactive"
}
```

**Response:** `200 OK`

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "connector_type": "google_contacts",
  "status": "inactive",
  "scopes": [...],
  "updated_at": "2025-11-14T10:30:00Z"
}
```

---

### DELETE /connectors/{connector_id}

**Delete connector and revoke OAuth tokens**

**Request:**

```http
DELETE /api/v1/connectors/550e8400-e29b-41d4-a716-446655440000
Cookie: session_id=xxx
```

**Response:** `204 No Content`

**Behavior:**
- Deletes connector from database
- Revokes OAuth tokens with provider
- Clears cached data (Redis)

---

### GET /connectors/{connector_id}/calendars

**List calendars from a connected calendar provider**

Returns the list of calendars available on the connected provider (Google Calendar, Apple Calendar, or Microsoft Calendar). Used by the frontend to populate the default calendar preference dropdown.

**Request:**

```http
GET /api/v1/connectors/550e8400-e29b-41d4-a716-446655440000/calendars
Cookie: session_id=xxx
```

**Response:** `200 OK`

```json
{
  "items": [
    {
      "name": "Personal",
      "is_default": true,
      "access_role": "owner"
    },
    {
      "name": "Work",
      "is_default": false,
      "access_role": "owner"
    },
    {
      "name": "Holidays",
      "is_default": false,
      "access_role": "reader"
    }
  ]
}
```

**Errors:**
- `400 Bad Request`: Connector is not a calendar type (`google_calendar`, `apple_calendar`, `microsoft_calendar`)
- `404 Not Found`: Connector not found or not owned by user
- `502 Bad Gateway`: Failed to fetch calendars from provider (API unreachable, token expired, etc.)

---

### GET /connectors/{connector_id}/task-lists

**List task lists from a connected tasks provider**

Returns the list of task lists available on the connected provider (Google Tasks or Microsoft To Do). Used by the frontend to populate the default task list preference dropdown.

**Request:**

```http
GET /api/v1/connectors/550e8400-e29b-41d4-a716-446655440000/task-lists
Cookie: session_id=xxx
```

**Response:** `200 OK`

```json
{
  "items": [
    {
      "name": "My Tasks",
      "is_default": true
    },
    {
      "name": "Shopping",
      "is_default": false
    }
  ]
}
```

**Errors:**
- `400 Bad Request`: Connector is not a tasks type (`google_tasks`, `microsoft_tasks`)
- `404 Not Found`: Connector not found or not owned by user
- `502 Bad Gateway`: Failed to fetch task lists from provider (API unreachable, token expired, etc.)

---

## Conversations

### POST /conversations

**Create new conversation (lazy initialization)**

**Request:**

```http
POST /api/v1/conversations
Cookie: session_id=xxx
Content-Type: application/json

{
  "title": "Ma conversation avec l'assistant"
}
```

**Response:** `201 Created`

```json
{
  "id": "conversation_uuid",
  "user_id": "user_uuid",
  "title": "Ma conversation avec l'assistant",
  "message_count": 0,
  "total_tokens": 0,
  "created_at": "2025-11-14T10:30:00Z",
  "updated_at": "2025-11-14T10:30:00Z"
}
```

**Note:** Conversations are created lazily on first message if not exists.

---

### POST /conversations/reset

**Reset conversation (delete checkpoints)**

**Request:**

```http
POST /api/v1/conversations/reset
Cookie: session_id=xxx
```

**Response:** `200 OK`

```json
{
  "message": "Conversation reset successfully",
  "conversation_id": "uuid",
  "checkpoints_deleted": 15
}
```

**Behavior:**
- Deletes LangGraph checkpoints from PostgreSQL
- Keeps conversation metadata (message_count, total_tokens)
- Logs audit trail (conversation_audit_log table)

---

### GET /conversations/history

**Get conversation history with token summaries**

**Request:**

```http
GET /api/v1/conversations/history?limit=50&offset=0
Cookie: session_id=xxx
```

**Response:** `200 OK`

```json
{
  "conversation": {
    "id": "conversation_uuid",
    "title": "Ma conversation",
    "message_count": 42,
    "total_tokens": 125000
  },
  "messages": [
    {
      "id": "msg_uuid",
      "role": "user",
      "content": "Bonjour",
      "metadata": {"run_id": "run_123"},
      "token_summary": {
        "run_id": "run_123",
        "total_prompt_tokens": 150,
        "total_completion_tokens": 50,
        "total_cost_eur": 0.0025
      },
      "created_at": "2025-11-14T10:00:00Z"
    }
  ],
  "total": 42,
  "limit": 50,
  "offset": 0
}
```

---

## Users

### GET /users/me

**Get current user profile (alias for /auth/me)**

**Request:**

```http
GET /api/v1/users/me
Cookie: session_id=xxx
```

**Response:** `200 OK`

```json
{
  "id": "user_uuid",
  "email": "user@example.com",
  "full_name": "John Doe",
  "timezone": "Europe/Paris",
  "language": "fr",
  "picture_url": "https://...",
  "created_at": "2025-11-01T10:00:00Z"
}
```

---

### PATCH /users/me

**Update user profile**

**Request:**

```http
PATCH /api/v1/users/me
Cookie: session_id=xxx
Content-Type: application/json

{
  "full_name": "Jean Dupont",
  "timezone": "America/New_York",
  "language": "en"
}
```

**Response:** `200 OK`

```json
{
  "id": "user_uuid",
  "email": "user@example.com",
  "full_name": "Jean Dupont",
  "timezone": "America/New_York",
  "language": "en",
  "updated_at": "2025-11-14T10:30:00Z"
}
```

---

### GET /users/me/statistics

**Get user usage statistics (tokens, cost, messages)**

**Request:**

```http
GET /api/v1/users/me/statistics
Cookie: session_id=xxx
```

**Response:** `200 OK`

```json
{
  "lifetime": {
    "total_prompt_tokens": 1250000,
    "total_completion_tokens": 450000,
    "total_cached_tokens": 850000,
    "total_cost_eur": 12.50,
    "total_messages": 1523
  },
  "current_cycle": {
    "cycle_start": "2025-11-01T00:00:00Z",
    "cycle_prompt_tokens": 125000,
    "cycle_completion_tokens": 45000,
    "cycle_cached_tokens": 85000,
    "cycle_cost_eur": 1.25,
    "cycle_messages": 152
  },
  "last_updated_at": "2025-11-14T10:30:00Z"
}
```

**Use Case:** Billing dashboard, quota tracking

---

## Admin Endpoints

### GET /admin/connectors/global-config

**Get global connector configuration (admin only)**

**Request:**

```http
GET /api/v1/admin/connectors/global-config
Cookie: session_id=xxx  # Superuser session required
```

**Response:** `200 OK`

```json
{
  "configs": [
    {
      "connector_type": "google_contacts",
      "is_enabled": true,
      "disabled_reason": null
    },
    {
      "connector_type": "gmail",
      "is_enabled": false,
      "disabled_reason": "API quota exceeded - maintenance until 2025-11-20"
    }
  ]
}
```

---

### PATCH /admin/connectors/global-config/{connector_type}

**Update global connector configuration**

**Request:**

```http
PATCH /api/v1/admin/connectors/global-config/gmail
Cookie: session_id=xxx
Content-Type: application/json

{
  "is_enabled": false,
  "disabled_reason": "Scheduled maintenance"
}
```

**Response:** `200 OK`

```json
{
  "connector_type": "gmail",
  "is_enabled": false,
  "disabled_reason": "Scheduled maintenance",
  "updated_at": "2025-11-14T10:30:00Z"
}
```

**Behavior:**
- Updates connector_global_config table
- Logs admin action in admin_audit_log table
- Affects all users (no new connections until re-enabled)

---

## User Consumption Export (v1.9.1)

> Prefix: `/usage/export`. Auth: `get_current_active_session` (any authenticated user).

Users can export their own consumption data as CSV. Security: `user_id` is forced server-side — no parameter exposed.

### GET /usage/export/token-usage

**Export the current user's LLM token usage as CSV.**

**Query Parameters:**

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `start_date` | string | No | Start date filter (YYYY-MM-DD) |
| `end_date` | string | No | End date filter (YYYY-MM-DD) |

**Response:** `200 OK` — CSV file download (`text/csv; charset=utf-8`)

### GET /usage/export/google-api-usage

**Export the current user's Google API usage as CSV.**

Same query parameters as above.

### GET /usage/export/consumption-summary

**Export the current user's aggregated consumption summary as CSV.**

Same query parameters as above. Returns a single-row CSV with totals (tokens, calls, costs).

---

## MCP Admin

> **Feature Flag** : `MCP_ENABLED=true` requis. Prefix : `/mcp/admin-servers`

### GET /mcp/admin-servers

**Lister les serveurs MCP admin avec statut par utilisateur**

**Request :**

```http
GET /api/v1/mcp/admin-servers
Cookie: session_id=xxx
```

**Response :** `200 OK`

```json
[
  {
    "server_key": "google_flights",
    "name": "Google Flights",
    "description": "Flight search and booking assistant",
    "tools_count": 3,
    "tools": [
      {"name": "search_flights", "description": "Search for flights"}
    ],
    "enabled_for_user": true
  }
]
```

**Response Model :** `list[AdminMCPServerResponse]`

**cURL :**

```bash
curl http://localhost:8000/api/v1/mcp/admin-servers \
  -b cookies.txt
```

---

### PATCH /mcp/admin-servers/{server_key}/toggle

**Activer/desactiver un serveur MCP admin pour l'utilisateur courant**

**Request :**

```http
PATCH /api/v1/mcp/admin-servers/google_flights/toggle
Cookie: session_id=xxx
```

**Parametres Path :**

| Parametre | Type | Description |
|-----------|------|-------------|
| `server_key` | string | Cle du serveur MCP admin (ex: `google_flights`) |

**Response :** `200 OK`

```json
{
  "server_key": "google_flights",
  "enabled_for_user": false
}
```

**Response Model :** `AdminMCPToggleResponse`

**Errors :**
- `404 Not Found` : Serveur MCP admin introuvable

**cURL :**

```bash
curl -X PATCH http://localhost:8000/api/v1/mcp/admin-servers/google_flights/toggle \
  -b cookies.txt
```

---

### POST /mcp/admin-servers/{server_key}/app/call-tool

**Proxy un appel d'outil depuis un MCP App (iframe) vers un serveur MCP admin**

**Request :**

```http
POST /api/v1/mcp/admin-servers/google_flights/app/call-tool
Cookie: session_id=xxx
Content-Type: application/json

{
  "tool_name": "search_flights",
  "arguments": {"origin": "CDG", "destination": "JFK"}
}
```

**Parametres Path :**

| Parametre | Type | Description |
|-----------|------|-------------|
| `server_key` | string | Cle du serveur MCP admin |

**Body :** `McpAppCallToolRequest`

| Champ | Type | Requis | Description |
|-------|------|--------|-------------|
| `tool_name` | string | Oui | Nom de l'outil a appeler |
| `arguments` | object | Non | Arguments de l'outil (defaut: `{}`) |

**Response :** `200 OK`

```json
{
  "success": true,
  "result": "{\"flights\": [...]}",
  "error": null
}
```

**Response Model :** `McpAppCallToolResponse`

**cURL :**

```bash
curl -X POST http://localhost:8000/api/v1/mcp/admin-servers/google_flights/app/call-tool \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{"tool_name": "search_flights", "arguments": {"origin": "CDG"}}'
```

---

### POST /mcp/admin-servers/{server_key}/app/read-resource

**Proxy une lecture de ressource depuis un MCP App (iframe) vers un serveur MCP admin**

**Request :**

```http
POST /api/v1/mcp/admin-servers/google_flights/app/read-resource
Cookie: session_id=xxx
Content-Type: application/json

{
  "uri": "resource://flights/results"
}
```

**Body :** `McpAppReadResourceRequest`

| Champ | Type | Requis | Description |
|-------|------|--------|-------------|
| `uri` | string | Oui | URI de la ressource a lire |

**Response :** `200 OK`

```json
{
  "success": true,
  "content": "<html>...</html>",
  "mime_type": "text/html",
  "error": null
}
```

**Response Model :** `McpAppReadResourceResponse`

**cURL :**

```bash
curl -X POST http://localhost:8000/api/v1/mcp/admin-servers/google_flights/app/read-resource \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{"uri": "resource://flights/results"}'
```

---

## MCP User (Per-User)

> **Feature Flags** : `MCP_ENABLED=true` ET `MCP_USER_ENABLED=true` requis. Prefix : `/mcp/servers`

### GET /mcp/servers

**Lister les serveurs MCP de l'utilisateur**

**Request :**

```http
GET /api/v1/mcp/servers
Cookie: session_id=xxx
```

**Response :** `200 OK`

```json
{
  "servers": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "Mon serveur GitHub",
      "url": "https://mcp.github.com/sse",
      "auth_type": "oauth2",
      "status": "active",
      "is_enabled": true,
      "domain_description": "GitHub repository management",
      "timeout_seconds": 30,
      "hitl_required": null,
      "header_name": null,
      "has_credentials": false,
      "has_oauth_credentials": true,
      "oauth_scopes": "repo project read:org",
      "tool_count": 5,
      "tools": [
        {
          "tool_name": "list_repos",
          "description": "List repositories",
          "input_schema": {}
        }
      ],
      "last_connected_at": "2026-03-01T10:00:00Z",
      "last_error": null,
      "created_at": "2026-02-28T10:00:00Z",
      "updated_at": "2026-03-01T10:00:00Z"
    }
  ],
  "total": 1
}
```

**Response Model :** `UserMCPServerListResponse`

**cURL :**

```bash
curl http://localhost:8000/api/v1/mcp/servers \
  -b cookies.txt
```

---

### POST /mcp/servers

**Creer un serveur MCP utilisateur**

**Request :**

```http
POST /api/v1/mcp/servers
Cookie: session_id=xxx
Content-Type: application/json

{
  "name": "Mon serveur GitHub",
  "url": "https://mcp.github.com/sse",
  "auth_type": "oauth2",
  "oauth_client_id": "client_xxx",
  "oauth_client_secret": "secret_xxx",
  "oauth_scopes": "repo project read:org",
  "domain_description": "GitHub repository management",
  "timeout_seconds": 30,
  "hitl_required": true
}
```

**Body :** `UserMCPServerCreate`

| Champ | Type | Requis | Description |
|-------|------|--------|-------------|
| `name` | string (1-100) | Oui | Nom du serveur (unique par utilisateur) |
| `url` | string (HTTPS) | Oui | URL du endpoint Streamable HTTP |
| `auth_type` | enum | Non | `none`, `api_key`, `bearer`, `oauth2` (defaut: `none`) |
| `api_key` | string | Conditionnel | Requis si `auth_type=api_key` |
| `header_name` | string | Non | Nom du header pour API key (defaut: `X-API-Key`) |
| `bearer_token` | string | Conditionnel | Requis si `auth_type=bearer` |
| `oauth_client_id` | string | Non | Client ID OAuth pre-enregistre |
| `oauth_client_secret` | string | Non | Client secret OAuth pre-enregistre |
| `oauth_scopes` | string | Non | Scopes OAuth (separes par espaces) |
| `domain_description` | string (max 500) | Non | Description pour le routage des requetes |
| `timeout_seconds` | int (5-120) | Non | Timeout par appel (defaut: 30s) |
| `hitl_required` | bool | Non | Override HITL par serveur (`null` = herite du global) |

**Response :** `201 Created` — `UserMCPServerResponse`

**Errors :**
- `400 Bad Request` : Validation des credentials vs auth_type
- `422 Unprocessable Entity` : URL non HTTPS, champs invalides

**cURL :**

```bash
curl -X POST http://localhost:8000/api/v1/mcp/servers \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{
    "name": "Mon serveur",
    "url": "https://mcp.example.com/sse",
    "auth_type": "api_key",
    "api_key": "sk-xxx"
  }'
```

---

### PATCH /mcp/servers/{server_id}

**Mettre a jour un serveur MCP utilisateur (update partiel)**

**Request :**

```http
PATCH /api/v1/mcp/servers/550e8400-e29b-41d4-a716-446655440000
Cookie: session_id=xxx
Content-Type: application/json

{
  "domain_description": "Updated description",
  "timeout_seconds": 60
}
```

**Parametres Path :**

| Parametre | Type | Description |
|-----------|------|-------------|
| `server_id` | UUID | ID du serveur MCP |

**Body :** `UserMCPServerUpdate` (tous les champs optionnels, memes champs que `Create`)

**Response :** `200 OK` — `UserMCPServerResponse`

**Errors :**
- `404 Not Found` : Serveur non trouve ou non appartenant a l'utilisateur

**cURL :**

```bash
curl -X PATCH http://localhost:8000/api/v1/mcp/servers/550e8400-e29b-41d4-a716-446655440000 \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{"timeout_seconds": 60}'
```

---

### DELETE /mcp/servers/{server_id}

**Supprimer un serveur MCP utilisateur**

**Request :**

```http
DELETE /api/v1/mcp/servers/550e8400-e29b-41d4-a716-446655440000
Cookie: session_id=xxx
```

**Response :** `204 No Content`

**Errors :**
- `404 Not Found` : Serveur non trouve ou non appartenant a l'utilisateur

**cURL :**

```bash
curl -X DELETE http://localhost:8000/api/v1/mcp/servers/550e8400-e29b-41d4-a716-446655440000 \
  -b cookies.txt
```

---

### PATCH /mcp/servers/{server_id}/toggle

**Activer/desactiver un serveur MCP utilisateur**

**Request :**

```http
PATCH /api/v1/mcp/servers/550e8400-e29b-41d4-a716-446655440000/toggle
Cookie: session_id=xxx
```

**Response :** `200 OK` — `UserMCPServerResponse`

**Errors :**
- `404 Not Found` : Serveur non trouve

**cURL :**

```bash
curl -X PATCH http://localhost:8000/api/v1/mcp/servers/550e8400-e29b-41d4-a716-446655440000/toggle \
  -b cookies.txt
```

---

### POST /mcp/servers/{server_id}/test

**Tester la connexion a un serveur MCP et decouvrir les outils**

**Request :**

```http
POST /api/v1/mcp/servers/550e8400-e29b-41d4-a716-446655440000/test
Cookie: session_id=xxx
```

**Response :** `200 OK`

```json
{
  "success": true,
  "tool_count": 5,
  "tools": [
    {
      "tool_name": "list_repos",
      "description": "List repositories",
      "input_schema": {"type": "object", "properties": {}}
    }
  ],
  "error": null,
  "domain_description": "GitHub repository management and code collaboration tools"
}
```

**Response Model :** `UserMCPTestConnectionResponse`

**Note :** En cas d'echec de connexion, `success=false` et `error` contient le message. Le statut HTTP reste `200 OK` (les erreurs de connexion sont dans le body, pas en HTTP).

**cURL :**

```bash
curl -X POST http://localhost:8000/api/v1/mcp/servers/550e8400-e29b-41d4-a716-446655440000/test \
  -b cookies.txt
```

---

### POST /mcp/servers/{server_id}/generate-description

**Forcer la (re)generation de la description de domaine a partir des outils decouverts**

**Request :**

```http
POST /api/v1/mcp/servers/550e8400-e29b-41d4-a716-446655440000/generate-description
Cookie: session_id=xxx
```

**Response :** `200 OK`

```json
{
  "domain_description": "GitHub repository management and code collaboration",
  "tool_count": 5
}
```

**Response Model :** `UserMCPGenerateDescriptionResponse`

**Errors :**
- `400 Bad Request` : Pas de cache d'outils disponible (effectuer un `test` d'abord)
- `404 Not Found` : Serveur non trouve

**cURL :**

```bash
curl -X POST http://localhost:8000/api/v1/mcp/servers/550e8400-e29b-41d4-a716-446655440000/generate-description \
  -b cookies.txt
```

---

### POST /mcp/servers/{server_id}/oauth/authorize

**Initier le flux OAuth 2.1 pour un serveur MCP**

**Request :**

```http
POST /api/v1/mcp/servers/550e8400-e29b-41d4-a716-446655440000/oauth/authorize
Cookie: session_id=xxx
```

**Response :** `200 OK`

```json
{
  "authorization_url": "https://github.com/login/oauth/authorize?client_id=...&state=..."
}
```

**Response Model :** `UserMCPOAuthInitiateResponse`

**Errors :**
- `400 Bad Request` : `auth_type` du serveur n'est pas `oauth2`
- `404 Not Found` : Serveur non trouve
- `502 Bad Gateway` : Serveur MCP injoignable ou mal configure

**cURL :**

```bash
curl -X POST http://localhost:8000/api/v1/mcp/servers/550e8400-e29b-41d4-a716-446655440000/oauth/authorize \
  -b cookies.txt
```

---

### POST /mcp/servers/{server_id}/oauth/disconnect

**Deconnecter OAuth (purger les tokens, forcer re-autorisation)**

**Request :**

```http
POST /api/v1/mcp/servers/550e8400-e29b-41d4-a716-446655440000/oauth/disconnect
Cookie: session_id=xxx
```

**Response :** `200 OK` — `UserMCPServerResponse` (statut revient a `auth_required`)

**Comportement :**
- Supprime les tokens OAuth (access_token, refresh_token)
- Conserve les credentials client (client_id, client_secret)
- Le statut du serveur revient a `auth_required`

**cURL :**

```bash
curl -X POST http://localhost:8000/api/v1/mcp/servers/550e8400-e29b-41d4-a716-446655440000/oauth/disconnect \
  -b cookies.txt
```

---

### POST /mcp/servers/{server_id}/app/call-tool

**Proxy un appel d'outil depuis un MCP App (iframe) vers un serveur MCP utilisateur**

**Request :**

```http
POST /api/v1/mcp/servers/550e8400-e29b-41d4-a716-446655440000/app/call-tool
Cookie: session_id=xxx
Content-Type: application/json

{
  "tool_name": "list_repos",
  "arguments": {"org": "my-org"}
}
```

**Body :** `McpAppCallToolRequest`

**Response :** `200 OK` — `McpAppCallToolResponse`

**cURL :**

```bash
curl -X POST http://localhost:8000/api/v1/mcp/servers/550e8400-e29b-41d4-a716-446655440000/app/call-tool \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{"tool_name": "list_repos", "arguments": {}}'
```

---

### POST /mcp/servers/{server_id}/app/read-resource

**Proxy une lecture de ressource depuis un MCP App (iframe) vers un serveur MCP utilisateur**

**Request :**

```http
POST /api/v1/mcp/servers/550e8400-e29b-41d4-a716-446655440000/app/read-resource
Cookie: session_id=xxx
Content-Type: application/json

{
  "uri": "resource://repos/list"
}
```

**Body :** `McpAppReadResourceRequest`

**Response :** `200 OK` — `McpAppReadResourceResponse`

**cURL :**

```bash
curl -X POST http://localhost:8000/api/v1/mcp/servers/550e8400-e29b-41d4-a716-446655440000/app/read-resource \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{"uri": "resource://repos/list"}'
```

---

## Channels (Telegram)

> **Feature Flag** : `CHANNELS_ENABLED=true` requis. Prefix : `/channels`

### POST /channels/otp/generate

**Generer un code OTP pour lier un canal de messagerie externe**

**Request :**

```http
POST /api/v1/channels/otp/generate?channel_type=telegram
Cookie: session_id=xxx
```

**Parametres Query :**

| Parametre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `channel_type` | enum | Non | Type de canal (defaut: `telegram`) |

**Response :** `200 OK`

```json
{
  "code": "ABC123",
  "expires_in_seconds": 300,
  "bot_username": "lia_bot",
  "channel_type": "telegram"
}
```

**Response Model :** `OTPGenerateResponse`

**Flux de liaison :**
1. L'utilisateur appelle cet endpoint pour obtenir un code OTP
2. L'utilisateur envoie `/start ABC123` au bot Telegram
3. Le bot verifie le code et cree le binding automatiquement

**cURL :**

```bash
curl -X POST "http://localhost:8000/api/v1/channels/otp/generate?channel_type=telegram" \
  -b cookies.txt
```

---

### GET /channels

**Lister les bindings de canaux de l'utilisateur**

**Request :**

```http
GET /api/v1/channels
Cookie: session_id=xxx
```

**Response :** `200 OK`

```json
{
  "bindings": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "channel_type": "telegram",
      "channel_user_id": "123456789",
      "channel_username": "@john_doe",
      "is_active": true,
      "created_at": "2026-03-03T10:00:00Z",
      "updated_at": "2026-03-03T10:00:00Z"
    }
  ],
  "total": 1,
  "telegram_bot_username": "lia_bot"
}
```

**Response Model :** `ChannelBindingListResponse`

**cURL :**

```bash
curl http://localhost:8000/api/v1/channels \
  -b cookies.txt
```

---

### PATCH /channels/{binding_id}/toggle

**Activer/desactiver un binding de canal**

**Request :**

```http
PATCH /api/v1/channels/550e8400-e29b-41d4-a716-446655440000/toggle
Cookie: session_id=xxx
```

**Parametres Path :**

| Parametre | Type | Description |
|-----------|------|-------------|
| `binding_id` | UUID | ID du binding de canal |

**Response :** `200 OK`

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "is_active": false
}
```

**Response Model :** `ChannelBindingToggleResponse`

**cURL :**

```bash
curl -X PATCH http://localhost:8000/api/v1/channels/550e8400-e29b-41d4-a716-446655440000/toggle \
  -b cookies.txt
```

---

### DELETE /channels/{binding_id}

**Supprimer un binding de canal (deliaison)**

**Request :**

```http
DELETE /api/v1/channels/550e8400-e29b-41d4-a716-446655440000
Cookie: session_id=xxx
```

**Response :** `204 No Content`

**cURL :**

```bash
curl -X DELETE http://localhost:8000/api/v1/channels/550e8400-e29b-41d4-a716-446655440000 \
  -b cookies.txt
```

---

## Heartbeat (Notifications Proactives)

> **Feature Flag** : `HEARTBEAT_ENABLED=true` requis. Prefix : `/heartbeat`

### GET /heartbeat/settings

**Recuperer les parametres de heartbeat de l'utilisateur**

**Request :**

```http
GET /api/v1/heartbeat/settings
Cookie: session_id=xxx
```

**Response :** `200 OK`

```json
{
  "heartbeat_enabled": true,
  "heartbeat_max_per_day": 3,
  "heartbeat_push_enabled": true,
  "heartbeat_notify_start_hour": 8,
  "heartbeat_notify_end_hour": 22,
  "available_sources": ["calendar", "weather", "interests", "memories"]
}
```

**Response Model :** `HeartbeatSettingsResponse`

**Note :** `available_sources` est calcule dynamiquement selon les connecteurs actifs de l'utilisateur (Google Calendar, Tasks, OpenWeatherMap, interests, memories).

**cURL :**

```bash
curl http://localhost:8000/api/v1/heartbeat/settings \
  -b cookies.txt
```

---

### PATCH /heartbeat/settings

**Mettre a jour les parametres de heartbeat (update partiel)**

**Request :**

```http
PATCH /api/v1/heartbeat/settings
Cookie: session_id=xxx
Content-Type: application/json

{
  "heartbeat_enabled": true,
  "heartbeat_max_per_day": 5,
  "heartbeat_notify_start_hour": 9,
  "heartbeat_notify_end_hour": 21
}
```

**Body :** `HeartbeatSettingsUpdate`

| Champ | Type | Requis | Description |
|-------|------|--------|-------------|
| `heartbeat_enabled` | bool | Non | Activer/desactiver le heartbeat |
| `heartbeat_max_per_day` | int (1-8) | Non | Nombre max de notifications par jour |
| `heartbeat_push_enabled` | bool | Non | Activer les push (FCM/Telegram) |
| `heartbeat_notify_start_hour` | int (0-23) | Non | Debut de la fenetre de notification |
| `heartbeat_notify_end_hour` | int (0-23) | Non | Fin de la fenetre de notification |

**Response :** `200 OK` — `HeartbeatSettingsResponse`

**cURL :**

```bash
curl -X PATCH http://localhost:8000/api/v1/heartbeat/settings \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{"heartbeat_max_per_day": 5}'
```

---

### GET /heartbeat/history

**Recuperer l'historique des notifications heartbeat (pagine)**

**Request :**

```http
GET /api/v1/heartbeat/history?limit=20&offset=0
Cookie: session_id=xxx
```

**Parametres Query :**

| Parametre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `limit` | int (1-100) | Non | Nombre de resultats (defaut: 20) |
| `offset` | int (>=0) | Non | Decalage pour la pagination (defaut: 0) |

**Response :** `200 OK`

```json
{
  "notifications": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "created_at": "2026-03-08T09:30:00Z",
      "content": "Bonjour ! Vous avez 2 reunions aujourd'hui et il va pleuvoir cet apres-midi.",
      "sources_used": ["calendar", "weather"],
      "priority": "medium",
      "user_feedback": null
    }
  ],
  "total": 42
}
```

**Response Model :** `HeartbeatHistoryResponse`

**cURL :**

```bash
curl "http://localhost:8000/api/v1/heartbeat/history?limit=10&offset=0" \
  -b cookies.txt
```

---

### PATCH /heartbeat/notifications/{notification_id}/feedback

**Soumettre un feedback sur une notification heartbeat**

**Request :**

```http
PATCH /api/v1/heartbeat/notifications/550e8400-e29b-41d4-a716-446655440000/feedback
Cookie: session_id=xxx
Content-Type: application/json

{
  "feedback": "thumbs_up"
}
```

**Parametres Path :**

| Parametre | Type | Description |
|-----------|------|-------------|
| `notification_id` | UUID | ID de la notification |

**Body :** `HeartbeatFeedbackRequest`

| Champ | Type | Requis | Description |
|-------|------|--------|-------------|
| `feedback` | enum | Oui | `thumbs_up` ou `thumbs_down` |

**Response :** `200 OK`

```json
{
  "message": "Feedback submitted successfully"
}
```

**Errors :**
- `404 Not Found` : Notification non trouvee

**cURL :**

```bash
curl -X PATCH http://localhost:8000/api/v1/heartbeat/notifications/550e8400-e29b-41d4-a716-446655440000/feedback \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{"feedback": "thumbs_up"}'
```

---

## Scheduled Actions (Actions Planifiees)

> Prefix : `/scheduled-actions`. Feature flag : `SCHEDULED_ACTIONS_ENABLED=true`

### GET /scheduled-actions

**Lister les actions planifiees de l'utilisateur**

**Request :**

```http
GET /api/v1/scheduled-actions
Cookie: session_id=xxx
```

**Response :** `200 OK`

```json
{
  "scheduled_actions": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "user_id": "user_uuid",
      "title": "Meteo quotidienne",
      "action_prompt": "Donne-moi la meteo du jour",
      "days_of_week": [1, 2, 3, 4, 5],
      "trigger_hour": 7,
      "trigger_minute": 30,
      "user_timezone": "Europe/Paris",
      "next_trigger_at": "2026-03-09T06:30:00Z",
      "is_enabled": true,
      "status": "active",
      "last_executed_at": "2026-03-08T06:30:00Z",
      "execution_count": 15,
      "consecutive_failures": 0,
      "last_error": null,
      "schedule_display": "Lun-Ven a 07:30",
      "created_at": "2026-02-20T10:00:00Z",
      "updated_at": "2026-03-08T06:30:00Z"
    }
  ],
  "total": 1
}
```

**Response Model :** `ScheduledActionListResponse`

**cURL :**

```bash
curl http://localhost:8000/api/v1/scheduled-actions \
  -b cookies.txt
```

---

### POST /scheduled-actions

**Creer une action planifiee**

**Request :**

```http
POST /api/v1/scheduled-actions
Cookie: session_id=xxx
Content-Type: application/json

{
  "title": "Meteo quotidienne",
  "action_prompt": "Donne-moi la meteo du jour",
  "days_of_week": [1, 2, 3, 4, 5],
  "trigger_hour": 7,
  "trigger_minute": 30
}
```

**Body :** `ScheduledActionCreate`

| Champ | Type | Requis | Description |
|-------|------|--------|-------------|
| `title` | string (1-200) | Oui | Titre de l'action |
| `action_prompt` | string (1-2000) | Oui | Prompt envoye au pipeline agent |
| `days_of_week` | list[int] | Oui | Jours ISO : 1=Lundi..7=Dimanche |
| `trigger_hour` | int (0-23) | Oui | Heure d'execution (timezone utilisateur) |
| `trigger_minute` | int (0-59) | Oui | Minute d'execution |

**Validation :**
- `days_of_week` : valeurs 1-7, pas de doublons
- L'heure d'execution est interpretee dans le timezone de l'utilisateur

**Response :** `201 Created` — `ScheduledActionResponse`

**cURL :**

```bash
curl -X POST http://localhost:8000/api/v1/scheduled-actions \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{
    "title": "Meteo quotidienne",
    "action_prompt": "Donne-moi la meteo du jour",
    "days_of_week": [1, 2, 3, 4, 5],
    "trigger_hour": 7,
    "trigger_minute": 30
  }'
```

---

### PATCH /scheduled-actions/{action_id}

**Mettre a jour une action planifiee (update partiel)**

**Request :**

```http
PATCH /api/v1/scheduled-actions/550e8400-e29b-41d4-a716-446655440000
Cookie: session_id=xxx
Content-Type: application/json

{
  "trigger_hour": 8,
  "days_of_week": [1, 2, 3, 4, 5, 6]
}
```

**Parametres Path :**

| Parametre | Type | Description |
|-----------|------|-------------|
| `action_id` | UUID | ID de l'action planifiee |

**Body :** `ScheduledActionUpdate` (tous les champs optionnels)

**Response :** `200 OK` — `ScheduledActionResponse`

**cURL :**

```bash
curl -X PATCH http://localhost:8000/api/v1/scheduled-actions/550e8400-e29b-41d4-a716-446655440000 \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{"trigger_hour": 8}'
```

---

### DELETE /scheduled-actions/{action_id}

**Supprimer une action planifiee**

**Request :**

```http
DELETE /api/v1/scheduled-actions/550e8400-e29b-41d4-a716-446655440000
Cookie: session_id=xxx
```

**Response :** `204 No Content`

**cURL :**

```bash
curl -X DELETE http://localhost:8000/api/v1/scheduled-actions/550e8400-e29b-41d4-a716-446655440000 \
  -b cookies.txt
```

---

### PATCH /scheduled-actions/{action_id}/toggle

**Activer/desactiver une action planifiee**

**Request :**

```http
PATCH /api/v1/scheduled-actions/550e8400-e29b-41d4-a716-446655440000/toggle
Cookie: session_id=xxx
```

**Response :** `200 OK` — `ScheduledActionResponse`

**cURL :**

```bash
curl -X PATCH http://localhost:8000/api/v1/scheduled-actions/550e8400-e29b-41d4-a716-446655440000/toggle \
  -b cookies.txt
```

---

### POST /scheduled-actions/{action_id}/execute

**Executer immediatement une action planifiee (fire-and-forget)**

**Request :**

```http
POST /api/v1/scheduled-actions/550e8400-e29b-41d4-a716-446655440000/execute
Cookie: session_id=xxx
```

**Response :** `202 Accepted`

```json
{
  "status": "executing"
}
```

**Comportement :**
- L'execution est asynchrone (fire-and-forget)
- Le resultat apparaitra dans la conversation de l'utilisateur et comme notification
- Le statut passe a `executing` pour eviter les executions concurrentes

**Errors :**
- `404 Not Found` : Action non trouvee
- `409 Conflict` : Action deja en cours d'execution

**cURL :**

```bash
curl -X POST http://localhost:8000/api/v1/scheduled-actions/550e8400-e29b-41d4-a716-446655440000/execute \
  -b cookies.txt
```

---

## Error Handling

### HTTP Status Codes

| Code | Status | Usage |
|------|--------|-------|
| **200** | OK | Successful GET/PATCH/POST (non-creation) |
| **201** | Created | Successful resource creation |
| **204** | No Content | Successful DELETE |
| **400** | Bad Request | Validation error, malformed request |
| **401** | Unauthorized | Missing or invalid session |
| **403** | Forbidden | Insufficient permissions |
| **404** | Not Found | Resource not found |
| **409** | Conflict | Resource conflict (e.g., duplicate email) |
| **422** | Unprocessable Entity | Pydantic validation error |
| **429** | Too Many Requests | Rate limit exceeded |
| **500** | Internal Server Error | Server error (logged) |
| **503** | Service Unavailable | Maintenance mode |

---

### Error Response Format

**Validation Error (422):**

```json
{
  "detail": [
    {
      "loc": ["body", "email"],
      "msg": "value is not a valid email address",
      "type": "value_error.email"
    }
  ]
}
```

**Application Error (400):**

```json
{
  "detail": "Email already registered",
  "error_code": "AUTH_002",
  "timestamp": "2025-11-14T10:30:00Z"
}
```

**Rate Limit Error (429):**

```json
{
  "detail": "Rate limit exceeded",
  "retry_after": 60,
  "limit": "10/minute"
}
```

---

## Rate Limiting

### Global Rate Limits

| Endpoint Pattern | Limit | Scope |
|------------------|-------|-------|
| `/auth/*` | 10 req/min | Per IP |
| `/agents/chat/stream` | 20 req/min | Per user |
| `/connectors/*` | 30 req/min | Per user |
| Global | 100 req/min | Per IP |

### Headers

**Request:**

```http
X-RateLimit-Limit: 20
X-RateLimit-Remaining: 15
X-RateLimit-Reset: 1699876543
```

**Response (429):**

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 60
X-RateLimit-Limit: 20
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1699876543
```

---

## SSE Streaming

### Client Implementation (JavaScript)

```javascript
async function streamChat(message) {
  const response = await fetch('/api/v1/agents/chat/stream', {
    method: 'POST',
    credentials: 'include',  // Include cookies
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({message})
  });

  const reader = response.body
    .pipeThrough(new TextDecoderStream())
    .getReader();

  let buffer = '';
  while (true) {
    const {value, done} = await reader.read();
    if (done) break;

    buffer += value;
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('event:')) {
        const event = line.slice(7).trim();
        const data = lines[lines.indexOf(line) + 1]?.slice(6);
        if (data) handleEvent(event, JSON.parse(data));
      }
    }
  }
}

function handleEvent(event, data) {
  switch (event) {
    case 'token':
      appendToken(data.delta);
      break;
    case 'hitl_approval_request':
      showApprovalDialog(data);
      break;
    case 'error':
      showError(data.message);
      break;
    case 'done':
      showMetrics(data);
      break;
  }
}
```

---

## Security (OWASP 2024)

### BFF Pattern (Backend-For-Frontend)

**Migration JWT → BFF (v0.1.0 → v0.3.0):**

| Aspect | JWT (v0.1.0) | BFF (v0.3.0) |
|--------|--------------|--------------|
| **Token Storage** | LocalStorage (XSS vulnerable) | HTTP-only cookie (XSS immune) |
| **Session Storage** | Stateless (token) | Server-side (Redis) |
| **CSRF Protection** | None | SameSite=Lax cookie |
| **Data Exposure** | User data in JWT (90% overhead) | Minimal cookie (session_id only) |
| **Revocation** | Impossible (stateless) | Instant (Redis delete) |

---

### CORS Configuration

**Development:**

```python
CORS_ORIGINS = ["http://localhost:3000", "http://localhost:5173"]
CORS_CREDENTIALS = True  # Allow cookies
```

**Production:**

```python
CORS_ORIGINS = ["https://app.yourdomain.com"]
CORS_CREDENTIALS = True
```

---

### Cookie Security

```
Set-Cookie: session_id=xxx;
  HttpOnly;           # Prevent JavaScript access (XSS protection)
  Secure;             # HTTPS only (production)
  SameSite=Lax;       # CSRF protection
  Path=/;             # All paths
  Max-Age=86400       # 24h (or 30 days if remember_me=true)
```

---

### OWASP Top 10 2024 Compliance

| Vulnerability | Mitigation |
|---------------|------------|
| **A01: Broken Access Control** | Session-based auth, resource ownership checks |
| **A02: Cryptographic Failures** | TLS 1.3, bcrypt (rounds=12), Fernet encryption |
| **A03: Injection** | Pydantic validation, SQLAlchemy ORM (parameterized) |
| **A04: Insecure Design** | Threat modeling, security by design (BFF Pattern) |
| **A05: Security Misconfiguration** | Secrets in .env, CORS strict, secure headers |
| **A06: Vulnerable Components** | Dependabot, regular updates, SBOM |
| **A07: Auth Failures** | Rate limiting, bcrypt, session timeout |
| **A08: Software Integrity Failures** | Docker image verification, SBOM |
| **A09: Security Logging Failures** | Structlog audit trail, admin_audit_log |
| **A10: SSRF** | URL validation, no user-controlled URLs |

---

## Examples cURL

### Register User

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "SecurePass123!",
    "full_name": "Test User",
    "timezone": "Europe/Paris",
    "language": "fr"
  }' \
  -c cookies.txt  # Save cookies to file
```

---

### Login

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "SecurePass123!",
    "remember_me": true
  }' \
  -c cookies.txt
```

---

### Stream Chat (cURL with SSE)

```bash
curl -X POST http://localhost:8000/api/v1/agents/chat/stream \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -N \
  -d '{
    "message": "Bonjour, comment vas-tu?"
  }'
```

**Output:**

```
event: start
data: {"run_id": "run_abc", "conversation_id": "uuid"}

event: token
data: {"content": "Bonjour", "delta": "Bonjour"}

...

event: done
data: {"run_id": "run_abc", "total_tokens": 150}

event: end
data: {}
```

---

### Get User Stats

```bash
curl http://localhost:8000/api/v1/users/me/statistics \
  -b cookies.txt
```

---

## Client SDKs

### Python SDK

```python
from lia_sdk import LIAClient

client = LIAClient(base_url="http://localhost:8000")

# Login
user = client.auth.login(
    email="user@example.com",
    password="password"
)

# Stream chat
for event in client.agents.stream_chat("Bonjour"):
    if event.type == "token":
        print(event.data.delta, end="", flush=True)
    elif event.type == "done":
        print(f"\n\nTokens: {event.data.total_tokens}")

# Get connectors
connectors = client.connectors.list()
```

---

### TypeScript SDK

```typescript
import {LIAClient} from '@lia/sdk';

const client = new LIAClient({
  baseUrl: 'http://localhost:8000'
});

// Login
const user = await client.auth.login({
  email: 'user@example.com',
  password: 'password'
});

// Stream chat
const stream = client.agents.streamChat({
  message: 'Bonjour'
});

for await (const event of stream) {
  if (event.type === 'token') {
    process.stdout.write(event.data.delta);
  }
}
```

---

## Troubleshooting

### Problème 1: 401 Unauthorized (Session Invalid)

**Symptôme:**

```json
{
  "detail": "Not authenticated"
}
```

**Diagnostic:**

```bash
# Check cookies
curl http://localhost:8000/api/v1/auth/me \
  -b cookies.txt \
  -v  # Verbose mode shows headers
```

**Solutions:**

1. **Session expired** → Re-login
2. **Cookie not sent** → Check `credentials: 'include'` (JavaScript)
3. **CORS issue** → Verify CORS_ORIGINS includes client URL

---

### Problème 2: SSE Stream Timeout

**Symptôme:** Stream closes after 30s with no events.

**Diagnostic:**

```bash
# Check SSE heartbeat
curl -N http://localhost:8000/api/v1/agents/chat/stream \
  -b cookies.txt \
  -d '{"message": "test"}' | grep heartbeat
```

**Solution:**

```javascript
// Client: Handle reconnection
eventSource.addEventListener('error', (e) => {
  if (eventSource.readyState === EventSource.CONNECTING) {
    console.log('Reconnecting...');
  }
});
```

---

### Problème 3: Rate Limit 429

**Symptôme:**

```json
{
  "detail": "Rate limit exceeded",
  "retry_after": 60
}
```

**Solution:**

```javascript
// Exponential backoff
async function retryWithBackoff(fn, retries = 3) {
  for (let i = 0; i < retries; i++) {
    try {
      return await fn();
    } catch (error) {
      if (error.status === 429) {
        const delay = Math.pow(2, i) * 1000;
        await new Promise(resolve => setTimeout(resolve, delay));
      } else {
        throw error;
      }
    }
  }
}
```

---

**Fin de GUIDE_API.md** - Documentation complète de l'API REST FastAPI LIA.
