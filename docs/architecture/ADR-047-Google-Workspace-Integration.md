# ADR-047: Google Workspace Integration

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Deciders**: Équipe architecture LIA
**Technical Story**: OAuth scopes unification and API patterns for Google Workspace services
**Related ADRs**: ADR-006, ADR-008, ADR-045

---

## Context and Problem Statement

L'application intègre plusieurs services Google Workspace :

1. **Multiple Services** : Gmail, Calendar, Contacts, Drive, Tasks
2. **OAuth Complexity** : Scopes différents par service
3. **Token Management** : Refresh automatique et distributed locking
4. **Rate Limiting** : Quotas API différents par service

**Question** : Comment unifier l'intégration Google Workspace avec des patterns cohérents ?

---

## Decision Drivers

### Must-Have (Non-Negotiable):

1. **BaseGoogleClient** : Abstraction commune pour tous les services
2. **Centralized Scopes** : Configuration unifiée des OAuth scopes
3. **Token Refresh** : Refresh automatique avec Redis locking
4. **Rate Limiting** : Protection contre les quotas API

### Nice-to-Have:

- Field projection pour optimisation tokens
- Redis caching par service
- Circuit breaker pattern

---

## Decision Outcome

**Chosen option**: "**BaseGoogleClient Abstraction + Centralized Scopes + Redis Rate Limiting**"

### Client Inheritance Hierarchy

```
BaseOAuthClient[ConnectorType]
    ↓ (implements OAuth-agnostic token refresh, rate limiting, circuit breaker)
BaseGoogleClient(BaseOAuthClient)
    ↓ (implements Google-specific token refresh)
    ├── GoogleGmailClient
    ├── GoogleCalendarClient
    ├── GooglePeopleClient (Contacts)
    ├── GoogleDriveClient
    ├── GoogleTasksClient
    └── GooglePlacesClient
```

### Centralized OAuth Scopes

```python
# apps/api/src/core/constants.py

# Google Contacts API scopes
GOOGLE_CONTACTS_SCOPES = [
    "https://www.googleapis.com/auth/contacts",
    "https://www.googleapis.com/auth/contacts.readonly",
    "https://www.googleapis.com/auth/contacts.other.readonly",
]

# Gmail API scopes
GOOGLE_GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]

# Google Calendar API scopes
GOOGLE_CALENDAR_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]

# Google Drive API scopes
GOOGLE_DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
]

# Google Tasks API scopes
GOOGLE_TASKS_SCOPES = [
    "https://www.googleapis.com/auth/tasks.readonly",
    "https://www.googleapis.com/auth/tasks",
]
```

### OAuth Provider Factory

```python
# apps/api/src/core/oauth/providers/google.py

@dataclass
class GoogleOAuthProvider:
    """Google OAuth 2.0 provider configuration."""

    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: list[str]
    authorization_endpoint: str = "https://accounts.google.com/o/oauth2/v2/auth"
    token_endpoint: str = "https://oauth2.googleapis.com/token"

    @classmethod
    def for_gmail(cls, settings: Settings) -> "GoogleOAuthProvider":
        return cls(
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            redirect_uri=f"{settings.api_url}/api/v1/connectors/gmail/callback",
            scopes=GOOGLE_GMAIL_SCOPES,
        )

    @classmethod
    def for_contacts(cls, settings: Settings) -> "GoogleOAuthProvider":
        return cls(
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            redirect_uri=f"{settings.api_url}/api/v1/connectors/google-contacts/callback",
            scopes=GOOGLE_CONTACTS_SCOPES,
        )

    @classmethod
    def for_calendar(cls, settings: Settings) -> "GoogleOAuthProvider":
        return cls(
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            redirect_uri=f"{settings.api_url}/api/v1/connectors/google-calendar/callback",
            scopes=GOOGLE_CALENDAR_SCOPES,
        )

    @classmethod
    def for_drive(cls, settings: Settings) -> "GoogleOAuthProvider":
        return cls(
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            redirect_uri=f"{settings.api_url}/api/v1/connectors/google-drive/callback",
            scopes=GOOGLE_DRIVE_SCOPES,
        )
```

### BaseGoogleClient Abstraction

```python
# apps/api/src/domains/connectors/clients/base_google_client.py

class BaseGoogleClient(BaseOAuthClient[ConnectorType]):
    """
    Abstract base class for Google API clients.

    Provides:
    - Token refresh via Google OAuth2 endpoints
    - Connector invalidation on OAuth failures
    - Google API error handling
    - Retry logic with exponential backoff
    - Rate limiting (configurable per client)
    """

    connector_type: ConnectorType
    api_base_url: str

    def __init__(
        self,
        user_id: UUID,
        credentials: ConnectorCredentials,
        connector_service: Any,
        rate_limit_per_second: int | None = None,
    ) -> None:
        effective_rate_limit = (
            rate_limit_per_second
            if rate_limit_per_second is not None
            else settings.client_rate_limit_google_per_second
        )
        super().__init__(user_id, credentials, connector_service, effective_rate_limit)
```

### Token Refresh with Redis Locking

```python
async def _refresh_access_token(self) -> str:
    """
    Refresh Google OAuth token using Redis lock.

    Process:
    1. Check if token expiration is within safety margin (5 min)
    2. Acquire distributed Redis lock
    3. Double-check if another coroutine already refreshed
    4. Call connector_service._refresh_oauth_token()
    5. Update credentials with new tokens
    """
    time_until_expiry = (
        (self.credentials.expires_at - datetime.now(UTC)).total_seconds()
        if self.credentials.expires_at
        else 0
    )

    redis_session = await get_redis_session()
    async with OAuthLock(redis_session, self.user_id, self.connector_type):
        # Double-check if another coroutine already refreshed
        fresh_credentials = await self.connector_service.get_connector_credentials(
            self.user_id, self.connector_type
        )

        if fresh_credentials and fresh_credentials.expires_at:
            fresh_threshold = datetime.now(UTC) + timedelta(
                seconds=OAUTH_TOKEN_REFRESH_MARGIN_SECONDS
            )
            if fresh_credentials.expires_at > fresh_threshold:
                self.credentials = fresh_credentials
                return str(fresh_credentials.access_token)

        # Perform actual refresh
        async with self.connector_service.db as db:
            repo = ConnectorRepository(db)
            connector = await repo.get_by_user_and_type(
                self.user_id, self.connector_type
            )

            refreshed_credentials = await self.connector_service._refresh_oauth_token(
                connector, fresh_credentials
            )
            self.credentials = refreshed_credentials

    return self.credentials.access_token
```

### Distributed Rate Limiting

```python
async def _rate_limit(self) -> None:
    """
    Apply distributed rate limiting using Redis sliding window.

    Default: 10 requests per second per user per connector type
    """
    if not settings.rate_limit_enabled:
        return

    try:
        limiter = await self._get_redis_rate_limiter()
        rate_limit_key = self._get_rate_limit_key()

        max_calls = self._rate_limit_per_second * 60
        window_seconds = 60

        max_retries = 5
        for attempt in range(max_retries):
            allowed = await limiter.acquire(
                key=rate_limit_key,
                max_calls=max_calls,
                window_seconds=window_seconds,
            )

            if allowed:
                return

            wait_time = 1.0 * (attempt + 1)
            logger.warning(
                "rate_limit_exceeded_retrying",
                user_id=str(self.user_id),
                attempt=attempt + 1,
                wait_time_seconds=wait_time,
            )
            await asyncio.sleep(wait_time)

        logger.error("rate_limit_max_retries_exceeded")
        self._on_rate_limit_exceeded()

    except Exception as e:
        # Fallback to local throttling
        logger.warning("rate_limit_redis_fallback", error=str(e))
        await self._local_rate_limit()
```

### HTTP Request with Retry Logic

```python
async def _make_request(
    self,
    method: str,
    endpoint: str,
    params: dict[str, Any] | None = None,
    json_data: dict[str, Any] | None = None,
    max_retries: int = 3,
) -> dict[str, Any]:
    """
    Make HTTP request with retry logic.

    Retry on:
    - 429 (Rate Limited)
    - 5xx (Server Error)

    Invalidate on:
    - 401 (Unauthorized) → Connector invalidation required
    """
    await self._rate_limit()
    access_token = await self._ensure_valid_token()

    url = f"{self.api_base_url}{endpoint}"
    headers = {"Authorization": f"Bearer {access_token}"}

    for attempt in range(max_retries):
        try:
            response = await self._execute_request(method, url, headers, params, json_data)

            if response.status_code < 400:
                return response.json() if response.content else {}

            if response.status_code == 429:
                wait_time = self._calculate_backoff(attempt)
                await asyncio.sleep(wait_time)
                continue

            if response.status_code >= 500:
                wait_time = self._calculate_backoff(attempt)
                await asyncio.sleep(wait_time)
                continue

            if response.status_code == 401:
                await self._invalidate_connector_on_auth_failure(response.text)
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Authentification {self.connector_type.value} invalide.",
                    headers={"X-Requires-Reconnect": "true"},
                )

            raise HTTPException(
                status_code=response.status_code,
                detail=f"{self.connector_type.value} API error: {response.text}",
            )

        except httpx.RequestError as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(self._calculate_backoff(attempt))
                continue
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"{self.connector_type.value} API unavailable",
            ) from e

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"{self.connector_type.value} API: max retries exceeded",
    )
```

### Gmail Client Example

```python
# apps/api/src/domains/connectors/clients/google_gmail_client.py

class GoogleGmailClient(BaseGoogleClient):
    connector_type = ConnectorType.GOOGLE_GMAIL
    api_base_url = "https://gmail.googleapis.com/gmail/v1"

    async def search_emails(
        self,
        query: str,
        max_results: int = 10,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """Search emails using Gmail query syntax."""
        cache_key = f"gmail:search:{self.user_id}:{hashlib.md5(query.encode()).hexdigest()}"

        if use_cache:
            cached = await self._get_cached(cache_key)
            if cached:
                return {**cached, "from_cache": True}

        response = await self._make_request(
            "GET",
            "/users/me/messages",
            {"q": query, "maxResults": max_results}
        )

        # Fetch message details
        messages = []
        for msg_id in [m["id"] for m in response.get("messages", [])]:
            msg = await self.get_message(msg_id)
            messages.append(msg)

        result = {"messages": messages}

        if use_cache:
            await self._set_cached(cache_key, result, ttl=settings.emails_cache_search_ttl_seconds)

        return result

    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str | None = None,
        bcc: str | None = None,
        is_html: bool = False,
    ) -> dict[str, Any]:
        """Send email via Gmail API."""
        message = MIMEText(body, "html" if is_html else "plain", "utf-8")
        message["To"] = self._encode_email_header(to)
        message["Subject"] = subject

        if cc:
            message["Cc"] = self._encode_email_header(cc)
        if bcc:
            message["Bcc"] = self._encode_email_header(bcc)

        raw_message = self._encode_base64url(message.as_string())

        return await self._make_request(
            "POST",
            "/users/me/messages/send",
            json_data={"raw": raw_message}
        )
```

### Calendar Client Example

```python
# apps/api/src/domains/connectors/clients/google_calendar_client.py

class GoogleCalendarClient(BaseGoogleClient):
    connector_type = ConnectorType.GOOGLE_CALENDAR
    api_base_url = "https://www.googleapis.com/calendar/v3"

    async def create_event(
        self,
        summary: str,
        start_datetime: str,
        end_datetime: str,
        timezone: str | None = None,
        description: str | None = None,
        location: str | None = None,
        attendees: list[str] | None = None,
        calendar_id: str = "primary",
    ) -> dict[str, Any]:
        """Create calendar event."""
        event_body = {
            "summary": summary,
            "start": {"dateTime": start_datetime, "timeZone": timezone or "Europe/Paris"},
            "end": {"dateTime": end_datetime, "timeZone": timezone or "Europe/Paris"},
        }

        if description:
            event_body["description"] = description
        if location:
            event_body["location"] = location
        if attendees:
            event_body["attendees"] = [{"email": email} for email in attendees]

        return await self._make_request(
            "POST",
            f"/calendars/{calendar_id}/events",
            json_data=event_body,
        )

    async def list_events(
        self,
        time_min: str | None = None,
        time_max: str | None = None,
        max_results: int = 10,
        calendar_id: str = "primary",
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """List events with optional field projection."""
        params = {
            "maxResults": max_results,
            "singleEvents": True,
            "orderBy": "startTime",
        }

        if time_min:
            params["timeMin"] = time_min
        if time_max:
            params["timeMax"] = time_max

        # Field projection for token optimization
        if fields:
            fields_str = ",".join(fields)
            params["fields"] = f"items({fields_str}),nextPageToken"

        return await self._make_request(
            "GET",
            f"/calendars/{calendar_id}/events",
            params=params,
        )
```

### Contacts Client Example

```python
# apps/api/src/domains/connectors/clients/google_people_client.py

class GooglePeopleClient(BaseGoogleClient):
    connector_type = ConnectorType.GOOGLE_CONTACTS
    api_base_url = "https://people.googleapis.com/v1"

    async def search_contacts(
        self,
        query: str,
        max_results: int = 10,
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """Search contacts with field projection."""
        read_mask = ",".join(fields) if fields else ",".join(GOOGLE_CONTACTS_SEARCH_FIELDS)

        params = {
            "query": query,
            "readMask": read_mask,
            "pageSize": min(max_results, 100),
        }

        return await self._make_request("GET", "/people:searchContacts", params=params)

    async def create_contact(
        self,
        name: str,
        email: str | None = None,
        phone: str | None = None,
        organization: str | None = None,
    ) -> dict[str, Any]:
        """Create contact."""
        contact_body = {"names": [{"givenName": name}]}

        if email:
            contact_body["emailAddresses"] = [{"value": email}]
        if phone:
            contact_body["phoneNumbers"] = [{"value": phone}]
        if organization:
            contact_body["organizations"] = [{"name": organization}]

        response = await self._make_request(
            "POST",
            "/people:createContact",
            json_data=contact_body,
        )

        # Invalidate cache after write
        await self._invalidate_user_cache()
        return response
```

### Connector Invalidation on Auth Failure

```python
async def _invalidate_connector_on_auth_failure(
    self,
    error_detail: str | None = None
) -> None:
    """Mark connector as ERROR after OAuth failure."""
    async with self.connector_service.db as db:
        repo = ConnectorRepository(db)
        connector = await repo.get_by_user_and_type(
            self.user_id, self.connector_type
        )

        if connector:
            connector.status = ConnectorStatus.ERROR
            connector.connector_metadata = {
                "last_error": error_detail[:500] if error_detail else "OAuth failed",
                "error_at": datetime.now(UTC).isoformat(),
                "error_type": "oauth_authentication_failed",
            }
            await db.commit()

            logger.warning(
                "connector_invalidated_auth_failure",
                connector_id=str(connector.id),
                connector_type=self.connector_type.value,
            )

            await self.connector_service._invalidate_user_connectors_cache(self.user_id)
```

### Client Registry

```python
# apps/api/src/domains/connectors/clients/registry.py

class ClientRegistry:
    """Registry mapping ConnectorType to API client classes."""

    _registry: dict[ConnectorType, type] = {}

    @classmethod
    def _ensure_initialized(cls) -> None:
        if cls._initialized:
            return

        from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
        from src.domains.connectors.clients.google_calendar_client import GoogleCalendarClient
        from src.domains.connectors.clients.google_people_client import GooglePeopleClient
        from src.domains.connectors.clients.google_drive_client import GoogleDriveClient
        from src.domains.connectors.clients.google_tasks_client import GoogleTasksClient

        cls.register_client(ConnectorType.GOOGLE_GMAIL, GoogleGmailClient)
        cls.register_client(ConnectorType.GOOGLE_CALENDAR, GoogleCalendarClient)
        cls.register_client(ConnectorType.GOOGLE_CONTACTS, GooglePeopleClient)
        cls.register_client(ConnectorType.GOOGLE_DRIVE, GoogleDriveClient)
        cls.register_client(ConnectorType.GOOGLE_TASKS, GoogleTasksClient)

        cls._initialized = True

    @classmethod
    def get_client_class(cls, connector_type: ConnectorType) -> type | None:
        cls._ensure_initialized()
        return cls._registry.get(connector_type)
```

### Consequences

**Positive**:
- ✅ **Unified Abstraction** : BaseGoogleClient pour tous les services
- ✅ **Centralized Scopes** : Configuration unifiée dans constants.py
- ✅ **Distributed Rate Limiting** : Redis sliding window
- ✅ **Token Refresh** : Automatique avec Redis locking
- ✅ **Connector Invalidation** : Graceful degradation sur 401
- ✅ **Field Projection** : Optimisation tokens via readMask/fields

**Negative**:
- ⚠️ Complexité de l'abstraction multi-niveaux
- ⚠️ Debugging des refresh tokens distribués

---

## Validation

**Acceptance Criteria**:
- [x] ✅ Scopes centralisés dans constants.py
- [x] ✅ GoogleOAuthProvider factory methods
- [x] ✅ BaseGoogleClient avec retry logic
- [x] ✅ Redis-based distributed rate limiting
- [x] ✅ Token refresh avec double-check locking
- [x] ✅ Connector invalidation sur 401
- [x] ✅ Client registry pour auto-discovery

---

## References

### Source Code
- **Constants**: `apps/api/src/core/constants.py` (scopes)
- **OAuth Provider**: `apps/api/src/core/oauth/providers/google.py`
- **Base Client**: `apps/api/src/domains/connectors/clients/base_google_client.py`
- **Gmail Client**: `apps/api/src/domains/connectors/clients/google_gmail_client.py`
- **Calendar Client**: `apps/api/src/domains/connectors/clients/google_calendar_client.py`
- **Contacts Client**: `apps/api/src/domains/connectors/clients/google_people_client.py`
- **Registry**: `apps/api/src/domains/connectors/clients/registry.py`

---

**Fin de ADR-047** - Google Workspace Integration Decision Record.
