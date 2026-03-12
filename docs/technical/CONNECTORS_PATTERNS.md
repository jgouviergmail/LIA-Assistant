# Patterns des Connecteurs - LIA

> Guide de référence des patterns établis pour l'implémentation de connecteurs

Version: 2.0
Date: 2025-12-25
Updated: Added new Google clients, API Key pattern, Circuit Breaker

---

## 📋 Table des Matières

- [Vue d'Ensemble](#vue-densemble)
- [Architecture Standard](#architecture-standard)
- [Pattern ConnectorTool Class](#pattern-connectortool-class)
- [Helpers Centralisés](#helpers-centralisés)
- [Checklist Nouveau Connecteur](#checklist-nouveau-connecteur)
- [Exemples de Référence](#exemples-de-référence)

---

## 🎯 Vue d'Ensemble

Ce document définit les patterns obligatoires pour l'implémentation de nouveaux connecteurs basés sur le retour d'expérience de Google, Apple iCloud et Microsoft 365.

**Objectifs** :
- Cohérence architecturale entre tous les connecteurs
- Réduction du boilerplate (80% minimum)
- Réutilisation des helpers centralisés
- Maintenabilité à long terme

---

## 🏗️ Architecture Standard

### Structure de fichiers obligatoire

```
apps/api/src/
├── domains/
│   ├── connectors/
│   │   └── clients/
│   │       └── {service}_client.py      # Client API (OAuth, HTTP)
│   │
│   └── agents/
│       ├── tools/
│       │   ├── {service}_tools.py       # Tools du connecteur
│       │   └── formatters.py            # Formatter (ajout ou enrichissement)
│       │
│       ├── {service}/
│       │   └── catalogue_manifests.py   # Tool manifests uniquement
│       │
│       └── prompts/
│           └── v1/
│               └── {service}_agent_prompt.txt
│
└── infrastructure/
    └── observability/
        └── metrics_agents.py            # Métriques Prometheus
```

### Registrations obligatoires

1. **catalogue_loader.py** : AgentManifest
2. **domain_taxonomy.py** : DomainConfig
3. **router_system_prompt.txt** : Domaine dans les exemples

---

## 🔷 Pattern ConnectorTool Class

### Pattern obligatoire

Tous les nouveaux connecteurs DOIVENT utiliser le pattern classe :

```python
from src.domains.agents.tools.base import ConnectorTool
from src.domains.connectors.clients.{service}_client import {Service}Client
from src.domains.connectors.models import ConnectorType


class Search{Items}Tool(ConnectorTool[{Service}Client]):
    """
    Search {items} by query.

    Uses ConnectorTool base class for:
    - Automatic dependency injection
    - OAuth token management
    - Error handling standardization
    - Metrics tracking
    """

    connector_type = ConnectorType.{SERVICE_TYPE}
    client_class = {Service}Client

    async def execute_api_call(
        self,
        client: {Service}Client,
        user_id: UUID,
        query: str,
        max_results: int = 10,
        **kwargs
    ) -> dict:
        """
        Execute API call with business logic only.

        Args:
            client: Injected API client with valid credentials
            user_id: User UUID
            query: Search query
            max_results: Maximum results to return

        Returns:
            dict: Formatted response for LLM
        """
        # 1. API call
        items = await client.search_items(query, max_results)

        # 2. Format response
        formatter = {Service}Formatter(
            tool_name="search_{items}_tool",
            operation="search",
            user_timezone=kwargs.get("user_timezone", "UTC"),
            locale=kwargs.get("locale", "fr-FR"),
        )

        return formatter.format_list_response(
            items=items,
            query=query,
            total=len(items),
        )
```

### Pourquoi ce pattern ?

| Aspect | Pattern Classe | Pattern Fonction |
|--------|---------------|------------------|
| Lignes de code | ~30 | ~150 |
| Boilerplate DI | 0 | ~50 |
| Client caching | Automatique | Manuel |
| Error handling | Hérité | Dupliqué |
| Tests | Mock client | Mock tout |

---

## 🔧 Helpers Centralisés

### runtime_helpers.py

```python
from src.domains.agents.tools.runtime_helpers import (
    # Parsing
    parse_user_id,                    # Parse UUID/ULID → UUID

    # Error handling
    handle_connector_api_error,        # Gestion erreurs unifiée
    handle_tool_exception,             # Gestion exceptions génériques

    # Validation
    validate_runtime_config,           # Valide config runtime
    extract_session_id_from_state,     # Extrait session_id
)
```

### Utilisation standard

```python
from src.domains.agents.tools.runtime_helpers import (
    parse_user_id,
    handle_connector_api_error,
)

# Dans un tool
try:
    user_id = parse_user_id(user_id_raw)  # Supporte UUID + ULID
    result = await client.api_call()
    return result

except Exception as e:
    return handle_connector_api_error(
        error=e,
        operation="search",
        tool_name="search_items_tool",
        params={"query": query},
        user_id_str=str(user_id),
        metrics_counter=my_api_calls,  # Optional Prometheus counter
    )
```

### Formatters

Pour les extractors de données, utiliser le Formatter approprié :

```python
from src.domains.agents.tools.formatters import ContactsFormatter, GmailFormatter

# Ne PAS dupliquer les extractors
name = ContactsFormatter._extract_name(person)
emails = ContactsFormatter._extract_emails(person)
```

---

## ✅ Checklist Nouveau Connecteur

### Phase 1 : Setup

- [ ] Créer `{service}_client.py` dans `connectors/clients/`
- [ ] Créer `{service}_tools.py` dans `agents/tools/`
- [ ] Ajouter/enrichir Formatter dans `formatters.py`
- [ ] Créer `catalogue_manifests.py` dans `agents/{service}/`

### Phase 2 : Registrations

- [ ] AgentManifest dans `catalogue_loader.py`
- [ ] DomainConfig dans `domain_taxonomy.py`
- [ ] Domaine dans `router_system_prompt.txt`

### Phase 3 : Implémentation

- [ ] Utiliser pattern ConnectorTool class
- [ ] Importer `parse_user_id` depuis runtime_helpers
- [ ] Importer `handle_connector_api_error` depuis runtime_helpers
- [ ] Ne PAS dupliquer de fonctions existantes

### Phase 4 : Observabilité

- [ ] Créer métriques Prometheus dans `metrics_agents.py`
- [ ] Configurer Langfuse tags
- [ ] Créer/enrichir dashboard Grafana

### Phase 5 : Tests

- [ ] Tests unitaires tools (mock client)
- [ ] Tests intégration agent
- [ ] Validation naming cohérent

### Phase 6 : Documentation

- [ ] Prompt agent créé
- [ ] Documentation technique mise à jour
- [ ] INDEX.md mis à jour

---

## 📚 Exemples de Référence

### Connecteurs implémentés

#### Google API Clients (OAuth 2.0)

| Connecteur | Lines | Key Features |
|------------|-------|--------------|
| **GoogleGmailClient** | 1,365 | Search, send, reply, forward, trash, labels |
| **GooglePeopleClient** | 631 | Search, CRUD contacts, caching |
| **GoogleDriveClient** | 408 | Search, list, get content, export |
| **GoogleCalendarClient** | 477 | Create events (LOT 5.4 HITL) |
| **GoogleTasksClient** | 419 | List, create, update, delete tasks |
| **GooglePlacesClient** | 689 | Search text/nearby, place details, autocomplete |

#### API Key Clients

| Connecteur | Lines | Key Features |
|------------|-------|--------------|
| **PerplexityClient** | 420 | AI web search (Sonar models) |
| **OpenWeatherMapClient** | 630 | Current weather, forecast, geocoding |
| **WikipediaClient** | 644 | Search, articles, multi-language |

#### Microsoft 365 Clients (OAuth — Microsoft Graph API)

| Connecteur | Key Features |
|------------|--------------|
| **MicrosoftOutlookClient** | Email search ($search KQL), send, reply, forward, trash |
| **MicrosoftCalendarClient** | calendarView for ranges, PATCH updates |
| **MicrosoftContactsClient** | OData pagination, search, CRUD |
| **MicrosoftTasksClient** | @default resolution, status mapping, no subtasks |

#### Base Classes

| Class | Purpose |
|-------|---------|
| **BaseOAuthClient** | Template Method with 3 hooks (_parse_error_detail, _get_retry_delay, _enrich_request_params) |
| **BaseGoogleClient** | Google-specific: _get_paginated_list (pageToken), _make_raw_request |
| **BaseMicrosoftClient** | Microsoft-specific: 3 hook overrides + _get_paginated_odata (@odata.nextLink) |
| **BaseAPIKeyClient** | API key auth + rate limiting |

### Fichiers clés

- **Pattern référence** : `apps/api/src/domains/agents/tools/google_contacts_tools.py`
- **Helpers centralisés** : `apps/api/src/domains/agents/tools/runtime_helpers.py`
- **Formatters** : `apps/api/src/domains/agents/tools/formatters.py`
- **Base class** : `apps/api/src/domains/agents/tools/base.py`

### Guides associés

- [GUIDE_AGENT_CREATION.md](../guides/GUIDE_AGENT_CREATION.md) - Création d'agent complet
- [GUIDE_TOOL_CREATION.md](../guides/GUIDE_TOOL_CREATION.md) - Création d'outils
- [TOOLS.md](./TOOLS.md) - Architecture tools complète

---

## ⚠️ Anti-patterns à éviter

### 1. Duplication de helpers

```python
# ❌ NE PAS FAIRE
def _parse_user_id(user_id):  # Duplication !
    if isinstance(user_id, UUID):
        return user_id
    # ...

# ✅ FAIRE
from src.domains.agents.tools.runtime_helpers import parse_user_id
```

### 2. Pattern decorator pour nouveaux connecteurs

```python
# ❌ NE PAS FAIRE pour nouveau connecteur
@connector_tool(...)
async def search_items_tool(..., runtime: ToolRuntime):
    # 150 lignes de boilerplate...

# ✅ FAIRE
class SearchItemsTool(ConnectorTool[MyClient]):
    async def execute_api_call(self, client, user_id, **kwargs):
        # Business logic uniquement
```

### 3. Error handling custom

```python
# ❌ NE PAS FAIRE
try:
    result = await client.call()
except Exception as e:
    # Debug prints, custom logging...
    print(f"Error: {e}")
    return {"error": str(e)}

# ✅ FAIRE
try:
    result = await client.call()
except Exception as e:
    return handle_connector_api_error(
        e, "operation", "tool_name", params
    )
```

---

---

## 🔄 OAuth Token Lifecycle Management

### Automatic Token Refresh

```python
# BaseGoogleClient - Automatic token refresh with Redis locking

async def _refresh_access_token(self) -> str:
    """
    Refresh OAuth token with race condition protection.

    Features:
        - 5-minute safety margin before expiration
        - Redis lock to prevent concurrent refresh
        - Double-check pattern (verify after lock acquisition)
    """
    if not self._token_needs_refresh():
        return self.credentials["access_token"]

    # Acquire Redis lock (prevents thundering herd)
    async with OAuthLock(self.redis, self.user_id):
        # Double-check (another process may have refreshed)
        if not self._token_needs_refresh():
            return self.credentials["access_token"]

        # Perform refresh
        new_tokens = await self.connector_service._refresh_oauth_token(
            self.user_id, self.connector_type
        )

        self.credentials.update(new_tokens)
        return new_tokens["access_token"]
```

### Token Refresh Safety Margin

```python
OAUTH_TOKEN_REFRESH_MARGIN_SECONDS = 300  # 5 minutes

def _token_needs_refresh(self) -> bool:
    expires_at = self.credentials.get("expires_at")
    if not expires_at:
        return True

    margin = timedelta(seconds=OAUTH_TOKEN_REFRESH_MARGIN_SECONDS)
    return datetime.utcnow() + margin >= expires_at
```

---

## ⚡ Circuit Breaker Pattern

Intégré dans les clients Base pour la gestion des pannes.

```python
class CircuitBreaker:
    """
    Circuit breaker for external API calls.

    States:
        - CLOSED: Normal operation, requests pass through
        - OPEN: Failures exceeded threshold, fast-fail all requests
        - HALF_OPEN: Testing if service recovered
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        half_open_requests: int = 3,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: datetime | None = None
```

---

## 🚦 Rate Limiting

### Distributed Rate Limiting (Redis)

```python
class RedisRateLimiter:
    """
    Distributed rate limiting with sliding window.

    Features:
        - Redis-based for horizontal scaling
        - Sliding window algorithm
        - Per-user tracking
        - Local fallback when Redis unavailable
    """

    async def check_rate_limit(
        self,
        key: str,
        limit: int = 10,
        window_seconds: int = 1
    ) -> bool:
        """Check if request is within rate limit."""
        current = await self.redis.incr(key)
        if current == 1:
            await self.redis.expire(key, window_seconds)
        return current <= limit
```

### Key Format

```
rate_limit:user:{user_id}:{connector_type}
```

---

## 🔒 Error Handling

### Error Classification

```python
# error_handlers.py - Centralized error handling

class OAuthCallbackErrorCode(StrEnum):
    OAUTH_FAILED = "oauth_failed"
    INVALID_STATE = "invalid_state"           # CSRF validation
    USER_NOT_FOUND = "user_not_found"
    TOKEN_EXCHANGE_FAILED = "token_exchange_failed"
    CONNECTOR_DISABLED = "connector_disabled"
    USER_INACTIVE = "user_inactive"

def classify_http_error(status_code: int, response_body: dict) -> dict:
    """
    Classify HTTP error for appropriate handling.

    Returns:
        {
            "error_type": str,
            "retryable": bool,
            "requires_user_action": bool,
            "message": str
        }
    """
```

### HTTP Status Mapping

| Status | Error Type | Retryable | Action |
|--------|------------|-----------|--------|
| 401 | auth_error | No | Invalidate connector, re-auth |
| 403 (rate limit) | rate_limit | Yes | Wait and retry |
| 403 (permissions) | insufficient_permissions | No | Request new scopes |
| 429 | rate_limit | Yes | Respect Retry-After header |
| 5xx | server_error | Yes | Exponential backoff |

---

## 📦 API Key Client Pattern

```python
class BaseAPIKeyClient:
    """
    Base class for API key authenticated clients.

    Features:
        - API key header/query authentication
        - Circuit breaker integration
        - Redis rate limiting (distributed)
        - Local fallback rate limiting
        - Secure key masking in logs
    """

    async def _make_request(
        self,
        method: str,
        url: str,
        **kwargs
    ) -> dict:
        # Check circuit breaker
        if self.circuit_breaker.is_open():
            raise CircuitOpenError("Service temporarily unavailable")

        # Check rate limit
        if not await self.rate_limiter.check_rate_limit(self._rate_limit_key):
            raise RateLimitError("Rate limit exceeded")

        # Make request with retry
        return await self._request_with_retry(method, url, **kwargs)
```

---

**CONNECTORS_PATTERNS.md** - Version 2.0 - Décembre 2025

*Guide des patterns de connecteurs - LIA*
