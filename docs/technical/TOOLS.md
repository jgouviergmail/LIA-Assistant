# Système d'Outils (Tools) - Architecture Extensible

> Architecture complète du système d'outils : ConnectorTool, decorators, formatters, manifests et patterns d'extension

**Version**: 2.2
**Date**: 2026-03-02
**Updated**: 16 domaines natifs + MCP externe, 50+ tools implémentés

## 📋 Table des Matières

- [Vue d'Ensemble](#vue-densemble)
- [Architecture en 5 Couches](#architecture-en-5-couches)
- [ConnectorTool (Base)](#connectortool-base)
- [Decorator Pattern](#decorator-pattern)
- [Formatters System](#formatters-system)
- [Tool Manifests](#tool-manifests)
- [Google Contacts Tools](#google-contacts-tools) *(Exemple de référence)*
- [Runtime Helpers](#runtime-helpers)
- [Création d'un Nouveau Tool](#création-dun-nouveau-tool)
- [MCP Tools Integration](#mcp-tools-integration)
- [Best Practices](#best-practices)
- [Performance & Caching](#performance--caching)

### Domaines Implémentés (50+ tools)

| Domaine | Type | Tools | Fichier Tools |
|---------|------|-------|---------------|
| **Contacts** | Google OAuth | 6 | `google_contacts_tools.py` |
| **Emails** | Google OAuth | 6 | `emails_tools.py` |
| **Calendar** | Google OAuth | 6 | `google_calendar_tools.py` |
| **Drive** | Google OAuth | 3 | `google_drive_tools.py` |
| **Tasks** | Google OAuth | 7 | `google_tasks_tools.py` |
| **Places** | Google OAuth | 3 | `google_places_tools.py` |
| **Weather** | API Key | 3 | `weather_tools.py` |
| **Wikipedia** | API Key | 4 | `wikipedia_tools.py` |
| **Perplexity** | API Key | 2 | `perplexity_tools.py` |
| **Brave** | API Key | 2 | `brave_tools.py` |
| **Web Search** | API Key | 1 | `web_search_tools.py` |
| **Web Fetch** | Standalone | 1 | `web_fetch_tools.py` |
| **Routes** | Google OAuth | 1 | `routes_tools.py` |
| **Reminders** | Local | 3 | `reminder_tools.py` |
| **Context** | Local | 5 | `context_tools.py` |
| **Query** | Local | 1 | `query_tools.py` |
| **MCP (per-user)** | MCP External | dynamic | `infrastructure/mcp/user_tool_adapter.py` |

> **Types de connexion** : **Google OAuth** = authentification OAuth2 via Google ; **API Key** = clé API tierce configurée en `.env` ; **Standalone** = aucune authentification requise (accès direct HTTP) ; **Local** = outil interne sans appel externe ; **MCP External** = outils découverts dynamiquement via Model Context Protocol.

> **Note**: Google Contacts est utilisé comme exemple de référence dans ce document.
> Tous les domaines suivent les mêmes patterns architecturaux.

---

## 🎯 Vue d'Ensemble

Le système d'outils de LIA permet d'**étendre facilement les capacités des agents** via une architecture en couches qui élimine 96% du boilerplate code.

### Réduction de Boilerplate

**Avant** (150+ lignes par tool) :
```python
class SearchContactsTool(BaseTool):
    def __init__(self, session, redis, client, ...):
        self.session = session
        self.redis = redis
        self.client = client
        # ... 10+ dependencies

    async def _run(self, query: str):
        # OAuth token refresh logic (30 lines)
        # Rate limiting logic (20 lines)
        # Cache management (25 lines)
        # Error handling (15 lines)
        # API call (10 lines)
        # Result formatting (30 lines)
        # Logging (10 lines)
        # Metrics (10 lines)
```

**Après** (8 lignes par tool) :
```python
@connector_tool
class SearchContactsTool(ConnectorTool):
    async def execute(self, query: str, max_results: int = 10) -> dict:
        """Recherche contacts par query."""
        return await self.client.search_contacts(query, max_results)
```

**Réduction : 150 lignes → 8 lignes = 94.7% reduction**

### Principes Clés

1. **Abstraction** : ConnectorTool encapsule OAuth, caching, rate limiting
2. **Composition** : @connector_tool combine 4 decorators en 1
3. **Type Safety** : Pydantic schemas pour validation
4. **Observability** : Metrics et logs automatiques
5. **Extensibility** : Nouveau tool en 8 lignes

---

## 🏗️ Architecture en 5 Couches

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: BASE ABSTRACTION (ConnectorTool)                   │
│ - OAuth token management automatique                        │
│ - Dependency injection (client, session, redis, uow)        │
│ - Abstract execute() method                                 │
│ - Error handling base                                       │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────┴────────────────────────────────────────┐
│ Layer 2: DECORATOR COMPOSITION (@connector_tool)            │
│ - @structured_tool (LangChain integration)                  │
│ - @with_oauth_refresh (auto token refresh)                  │
│ - @with_rate_limiting (sliding window)                      │
│ - @with_caching (Redis LRU)                                 │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────┴────────────────────────────────────────┐
│ Layer 3: FORMATTERS (Result Transformation)                 │
│ - BaseFormatter abstract                                    │
│ - ContactFormatter (Google Contacts specific)               │
│ - EmailFormatter, CalendarFormatter (future)                │
│ - Field mapping, filtering, enrichment                      │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────┴────────────────────────────────────────┐
│ Layer 4: MANIFESTS (Tool Declaration)                       │
│ - ToolManifest (parameters, permissions, cost)              │
│ - ToolManifestBuilder (fluent API)                          │
│ - Catalogue (aggregation par domain)                        │
│ - Single source of truth pour planner                       │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────┴────────────────────────────────────────┐
│ Layer 5: CATALOGUE LOADER (Dynamic Discovery)               │
│ - Scan all tools via inspect                               │
│ - Build manifests automatiquement                           │
│ - Domain grouping                                           │
│ - Filtering par domain (80% token reduction)                │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔷 ConnectorTool (Base)

**Fichier** : `apps/api/src/domains/agents/tools/base.py`

### Abstract Base Class

```python
from abc import ABC, abstractmethod
from typing import Any

class ConnectorTool(ABC):
    """
    Base class abstraite pour tous les connector tools.

    Responsibilities :
        - OAuth token management (via runtime)
        - Dependency injection (client, session, redis, uow)
        - Common error handling
        - Abstract execute() method

    Usage :
        class MyTool(ConnectorTool):
            async def execute(self, param: str) -> dict:
                # Tool logic avec self.client disponible
                return await self.client.some_api_call(param)
    """

    def __init__(
        self,
        runtime: ToolRuntime,  # Injecté automatiquement
    ):
        """
        Initialize tool avec runtime.

        Args:
            runtime : ToolRuntime avec client, session, redis, uow, etc.
        """
        self.runtime = runtime
        self.client = runtime.client
        self.session = runtime.session
        self.redis = runtime.redis
        self.uow = runtime.uow
        self.user_id = runtime.user_id
        self.connector_type = runtime.connector_type

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """
        Execute tool logic.

        MUST be implemented by subclasses.

        Args:
            **kwargs : Tool parameters (validated by Pydantic)

        Returns:
            Tool result (dict, list, str, etc.)

        Raises:
            ToolExecutionError : Si erreur durant exécution
        """
        pass

    async def refresh_token_if_needed(self) -> None:
        """
        Refresh OAuth token si expiré.

        Called automatiquement par @with_oauth_refresh decorator.
        """
        if not self.runtime.connector:
            raise RuntimeError("No connector available for token refresh")

        # Check if token expired
        if self.runtime.connector.is_token_expired():
            logger.info("oauth_token_expired", user_id=self.user_id)

            # Refresh with lock (prevent concurrent refreshes)
            async with OAuthLock(
                self.redis,
                self.user_id,
                self.connector_type
            ):
                # Double-check after acquiring lock
                if self.runtime.connector.is_token_expired():
                    await oauth_service.refresh_access_token(
                        self.runtime.connector.id
                    )

                    # Reload connector
                    async with self.uow:
                        self.runtime.connector = await self.uow.connectors.get_by_id(
                            self.runtime.connector.id
                        )

    def format_error(self, error: Exception) -> dict:
        """
        Format error pour retour standardisé.

        Returns:
            {"error": str, "error_type": str, "details": dict}
        """
        return {
            "error": str(error),
            "error_type": type(error).__name__,
            "details": getattr(error, "__dict__", {}),
        }
```

### ToolRuntime (Dependency Injection)

```python
# apps/api/src/domains/agents/tools/runtime_helpers.py

from dataclasses import dataclass
from typing import Any

@dataclass
class ToolRuntime:
    """
    Runtime context pour tool execution.

    Injected automatiquement via @connector_tool.
    """
    # OAuth & Auth
    user_id: UUID
    connector_type: ConnectorType
    connector: Connector | None

    # API Client
    client: Any  # GooglePeopleClient, GmailClient, etc.

    # Database
    session: AsyncSession
    uow: UnitOfWork

    # Cache
    redis: Redis
    cache_ttl: int = 300  # 5 minutes default

    # Rate Limiting
    rate_limit_config: dict | None = None

    # Metadata
    metadata: dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
```

---

## 🎨 Decorator Pattern

**Fichier** : `apps/api/src/domains/agents/tools/decorators.py`

### @connector_tool (Composite)

```python
def connector_tool(
    tool_class: type[ConnectorTool]
) -> Callable:
    """
    Composite decorator combinant 4 decorators en 1.

    Applied decorators (order matters) :
        1. @structured_tool - LangChain integration
        2. @with_oauth_refresh - Auto token refresh
        3. @with_rate_limiting - Sliding window rate limiting
        4. @with_caching - Redis LRU cache

    Usage :
        @connector_tool
        class MyTool(ConnectorTool):
            async def execute(self, param: str) -> dict:
                return {"result": param}

    Returns:
        StructuredTool ready for LangChain agents
    """
    # Step 1: Get tool metadata from class
    tool_name = tool_class.__name__.replace("Tool", "").lower()
    tool_description = tool_class.__doc__ or f"{tool_name} tool"

    # Step 2: Extract parameters from execute() signature
    execute_method = tool_class.execute
    sig = inspect.signature(execute_method)

    # Build Pydantic schema
    parameters_schema = _build_pydantic_schema_from_signature(sig)

    # Step 3: Create wrapped execute function
    async def wrapped_execute(**kwargs) -> Any:
        """Wrapped execute avec runtime injection."""
        # Get runtime from context (InjectedStore)
        runtime = _get_runtime_from_context(kwargs)

        # Instantiate tool
        tool_instance = tool_class(runtime=runtime)

        # Apply decorators in order
        execute_fn = tool_instance.execute

        # 4. Cache (innermost)
        execute_fn = with_caching(
            cache_key_fn=lambda **kw: f"{tool_name}:{hash(frozenset(kw.items()))}",
            ttl=runtime.cache_ttl
        )(execute_fn)

        # 3. Rate limiting
        execute_fn = with_rate_limiting(
            max_calls=20,
            window_seconds=60,
            scope="user"
        )(execute_fn)

        # 2. OAuth refresh
        execute_fn = with_oauth_refresh()(execute_fn)

        # 1. Structured tool (outermost)
        # (handled by @structured_tool below)

        # Execute with runtime
        return await execute_fn(**kwargs)

    # Step 4: Create StructuredTool
    structured_tool_instance = StructuredTool(
        name=tool_name,
        description=tool_description,
        args_schema=parameters_schema,
        coroutine=wrapped_execute,
    )

    return structured_tool_instance
```

### Individual Decorators

#### @with_oauth_refresh

```python
def with_oauth_refresh():
    """
    Decorator pour auto-refresh OAuth token si expiré.

    Flow :
        1. Check if token expired
        2. If yes: Acquire lock (prevent concurrent refreshes)
        3. Double-check after lock
        4. Refresh token via OAuth service
        5. Reload connector
        6. Execute tool
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(self: ConnectorTool, **kwargs):
            # Refresh token if needed
            await self.refresh_token_if_needed()

            # Execute tool
            return await func(self, **kwargs)

        return wrapper
    return decorator
```

#### @with_rate_limiting

```python
def with_rate_limiting(
    max_calls: int = 20,
    window_seconds: int = 60,
    scope: Literal["user", "global"] = "user"
):
    """
    Decorator pour rate limiting sliding window.

    Algorithm :
        1. Key = "{scope}:{user_id}:{tool_name}"
        2. ZADD timestamp to sorted set
        3. ZREMRANGEBYSCORE remove expired (< now - window)
        4. ZCARD count current window
        5. If count > max_calls: Raise RateLimitExceeded

    Args:
        max_calls : Max calls per window
        window_seconds : Window duration
        scope : "user" (per-user) ou "global" (tous users)
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(self: ConnectorTool, **kwargs):
            tool_name = self.__class__.__name__

            # Build key
            if scope == "user":
                key = f"rate_limit:{self.user_id}:{tool_name}"
            else:
                key = f"rate_limit:global:{tool_name}"

            # Current timestamp
            now = time.time()
            window_start = now - window_seconds

            # Remove expired entries
            await self.redis.zremrangebyscore(key, 0, window_start)

            # Count current window
            current_count = await self.redis.zcard(key)

            if current_count >= max_calls:
                logger.warning(
                    "rate_limit_exceeded",
                    tool=tool_name,
                    user_id=self.user_id,
                    max_calls=max_calls,
                    window_seconds=window_seconds
                )

                rate_limit_exceeded_total.labels(
                    tool_name=tool_name,
                    scope=scope
                ).inc()

                raise RateLimitExceeded(
                    f"Rate limit exceeded: {max_calls} calls per {window_seconds}s"
                )

            # Add current call
            await self.redis.zadd(key, {str(uuid4()): now})
            await self.redis.expire(key, window_seconds)

            # Execute tool
            return await func(self, **kwargs)

        return wrapper
    return decorator
```

#### @with_caching

```python
def with_caching(
    cache_key_fn: Callable[..., str],
    ttl: int = 300
):
    """
    Decorator pour Redis LRU cache.

    Args:
        cache_key_fn : Function pour générer cache key
        ttl : Time-to-live en secondes

    Returns:
        Cached result if available, otherwise execute + cache
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(self: ConnectorTool, **kwargs):
            # Generate cache key
            cache_key = cache_key_fn(**kwargs)
            full_key = f"tool_cache:{self.__class__.__name__}:{cache_key}"

            # Try cache
            cached = await self.redis.get(full_key)

            if cached:
                logger.debug("tool_cache_hit", key=full_key)
                cache_hit_total.labels(cache_type="tool").inc()
                return json.loads(cached)

            # Cache miss
            logger.debug("tool_cache_miss", key=full_key)
            cache_miss_total.labels(cache_type="tool").inc()

            # Execute tool
            result = await func(self, **kwargs)

            # Cache result
            await self.redis.setex(
                full_key,
                ttl,
                json.dumps(result, default=str)
            )

            return result

        return wrapper
    return decorator
```

---

## 🎨 Formatters System

**Fichier** : `apps/api/src/domains/agents/tools/formatters.py`

### BaseFormatter

```python
from abc import ABC, abstractmethod

class BaseFormatter(ABC):
    """
    Base formatter pour transformation de résultats.

    Responsibilities :
        - Field mapping (API fields → display fields)
        - Field filtering (remove internal fields)
        - Field enrichment (add computed fields)
        - Type coercion (ensure correct types)
    """

    @abstractmethod
    def format(self, data: dict | list) -> dict | list:
        """
        Format data pour présentation.

        Args:
            data : Raw data from API

        Returns:
            Formatted data ready for display/LLM
        """
        pass

    @abstractmethod
    def format_list(self, items: list[dict]) -> list[dict]:
        """Format list of items."""
        pass

    def filter_fields(
        self,
        data: dict,
        allowed_fields: list[str]
    ) -> dict:
        """Filter dict to only allowed fields."""
        return {
            k: v for k, v in data.items()
            if k in allowed_fields
        }

    def map_fields(
        self,
        data: dict,
        field_mapping: dict[str, str]
    ) -> dict:
        """
        Map fields selon mapping dict.

        Args:
            data : Source data
            field_mapping : {source_field: target_field}

        Returns:
            Mapped dict

        Example:
            map_fields(
                {"resourceName": "people/c123", "names": [...]},
                {"resourceName": "resource_name", "names": "name_list"}
            )
            → {"resource_name": "people/c123", "name_list": [...]}
        """
        return {
            field_mapping.get(k, k): v
            for k, v in data.items()
        }
```

### ContactFormatter

```python
# apps/api/src/domains/agents/tools/formatters.py

class ContactFormatter(BaseFormatter):
    """
    Formatter pour Google Contacts API results.

    Field Sets (3 levels) :
        - MINIMAL : resource_name, display_name only
        - SEARCH : + emails, phones, organizations (for search results)
        - COMPLETE : All fields including photos, addresses, events
    """

    # Field definitions
    MINIMAL_FIELDS = ["resource_name", "display_name"]

    SEARCH_FIELDS = MINIMAL_FIELDS + [
        "emails", "phones", "organizations",
        "biographies", "nicknames"
    ]

    COMPLETE_FIELDS = SEARCH_FIELDS + [
        "addresses", "birthdays", "events", "relations",
        "urls", "photos", "user_defined", "metadata"
    ]

    def format(
        self,
        contact: dict,
        field_set: Literal["minimal", "search", "complete"] = "search"
    ) -> dict:
        """
        Format single contact.

        Args:
            contact : Raw Google Contacts API response
            field_set : Level of detail

        Returns:
            Formatted contact dict
        """
        # Select fields based on field_set
        if field_set == "minimal":
            allowed_fields = self.MINIMAL_FIELDS
        elif field_set == "search":
            allowed_fields = self.SEARCH_FIELDS
        else:  # complete
            allowed_fields = self.COMPLETE_FIELDS

        # Extract and format fields
        formatted = {}

        # Resource name (always included)
        formatted["resource_name"] = contact.get("resourceName")

        # Display name (compute from names)
        names = contact.get("names", [])
        if names:
            primary_name = next((n for n in names if n.get("metadata", {}).get("primary")), names[0])
            formatted["display_name"] = primary_name.get("displayName")
        else:
            formatted["display_name"] = "Unknown"

        # Emails (if in field_set)
        if "emails" in allowed_fields:
            emails = contact.get("emailAddresses", [])
            formatted["emails"] = [
                {
                    "value": e.get("value"),
                    "type": e.get("type", "other"),
                    "primary": e.get("metadata", {}).get("primary", False)
                }
                for e in emails
            ]

        # Phones (if in field_set)
        if "phones" in allowed_fields:
            phones = contact.get("phoneNumbers", [])
            formatted["phones"] = [
                {
                    "value": p.get("value"),
                    "type": p.get("type", "other"),
                    "primary": p.get("metadata", {}).get("primary", False)
                }
                for p in phones
            ]

        # Organizations (if in field_set)
        if "organizations" in allowed_fields:
            orgs = contact.get("organizations", [])
            formatted["organizations"] = [
                {
                    "name": o.get("name"),
                    "title": o.get("title"),
                    "department": o.get("department"),
                    "current": o.get("current", False)
                }
                for o in orgs
            ]

        # Photos (if in field_set)
        if "photos" in allowed_fields:
            photos = contact.get("photos", [])
            formatted["photos"] = [
                {
                    "url": p.get("url"),
                    "primary": p.get("metadata", {}).get("primary", False)
                }
                for p in photos
            ]

            # Generate photo HTML (for response rendering)
            if photos:
                formatted["photo_html"] = self._generate_photo_html(photos[0])

        # ... autres fields selon field_set

        return formatted

    def format_list(
        self,
        contacts: list[dict],
        field_set: Literal["minimal", "search", "complete"] = "search"
    ) -> list[dict]:
        """Format list of contacts."""
        return [self.format(c, field_set) for c in contacts]

    def _generate_photo_html(self, photo: dict) -> str:
        """
        Generate HTML pour affichage photo dans response.

        Returns:
            HTML string avec img tag + alt + lazy loading
        """
        url = photo.get("url")
        if not url:
            return ""

        return f'<img src="{url}" alt="Contact photo" loading="lazy" style="max-width: 150px; border-radius: 50%;" />'
```

---

## 📋 Tool Manifests

**Fichier** : `apps/api/src/domains/agents/registry/manifest_builder.py`

### ToolManifest Schema

```python
# apps/api/src/domains/agents/registry/catalogue.py

@dataclass(frozen=True)
class ParameterSchema:
    """Schema pour un paramètre de tool."""
    name: str
    type: str  # "string", "integer", "boolean", "array", "object"
    description: str
    required: bool = False
    semantic_type: str | None = None  # "URL", "EMAIL", etc.
    constraints: list[ParameterConstraint] = field(default_factory=list)

@dataclass(frozen=True)
class PermissionProfile:
    """Permissions et sécurité pour un tool."""
    required_scopes: list[str] = field(default_factory=list)  # OAuth scopes
    allowed_roles: list[str] = field(default_factory=list)
    data_classification: Literal["PUBLIC", "INTERNAL", "CONFIDENTIAL", "SENSITIVE", "RESTRICTED"] = "CONFIDENTIAL"
    hitl_required: bool = False  # HITL approval required

@dataclass(frozen=True)
class CostProfile:
    """Profil de coût pour estimation."""
    est_tokens_in: int = 0       # Tokens en entrée (prompt + params)
    est_tokens_out: int = 0      # Tokens en sortie (réponse)
    est_cost_usd: float = 0.0    # Coût estimé en USD
    est_latency_ms: int = 0      # Latence estimée en ms

@dataclass(frozen=True)
class OutputFieldSchema:
    """Schema d'un champ de sortie (JSONPath)."""
    path: str  # JSONPath (ex: "contacts[].name.display")
    type: str
    description: str
    semantic_type: str | None = None
    nullable: bool = False

@dataclass
class ToolManifest:
    """
    Manifest complet d'un tool.

    Single source of truth pour :
        - Planner (catalogue de tools disponibles)
        - Validator (validation parameters)
        - Orchestrator (permissions check)
        - Approval Gate (HITL decision)
    """
    name: str
    agent: str  # Agent qui possède ce tool
    description: str

    # Contract
    parameters: list[ParameterSchema]
    outputs: list[OutputFieldSchema]

    # Cost & Performance
    cost: CostProfile

    # Security
    permissions: PermissionProfile

    # Behavior
    context_key: str | None = None  # Clé pour auto-save dans Store
    semantic_keywords: list[str] = field(default_factory=list)
    reference_examples: list[str] = field(default_factory=list)

    # Versioning
    version: str = "1.0.0"
    maintainer: str = "Team AI"

    # Display (optional)
    display: DisplayMetadata | None = None
```

### ToolManifestBuilder (Fluent API)

```python
# apps/api/src/domains/agents/registry/manifest_builder.py

class ToolManifestBuilder:
    """
    Builder pattern (fluent API) pour construction de manifests.
    Immutable: chaque méthode retourne une nouvelle instance.

    Usage :
        manifest = (
            ToolManifestBuilder("search_contacts_tool", "contact_agent")
            .with_description("Search contacts by query")
            .add_parameter("query", "string", required=True, description="Search query")
            .add_parameter("max_results", "integer", description="Max results")
            .add_output("contacts", "array", "List of contacts found")
            .with_permissions(
                required_scopes=["contacts.readonly"],
                hitl_required=False,
                data_classification="CONFIDENTIAL",
            )
            .with_cost_profile(
                est_tokens_in=150, est_tokens_out=400,
                est_cost_usd=0.001, est_latency_ms=500,
            )
            .with_context_key("contacts")
            .build()
        )
    """

    def __init__(self, name: str, agent: str, *, _manifest=None): ...

    # Core
    def with_description(self, description: str) -> Self: ...
    def with_version(self, version: str) -> Self: ...
    def with_maintainer(self, maintainer: str) -> Self: ...

    # Parameters & Outputs
    def add_parameter(self, name, type, required=False, description="", **constraints) -> Self: ...
    def add_output(self, path, type, description="", nullable=False) -> Self: ...

    # Cost & Performance
    def with_cost_profile(self, est_tokens_in=0, est_tokens_out=0,
                          est_cost_usd=0.0, est_latency_ms=0) -> Self: ...

    # Security
    def with_permissions(self, required_scopes=None, allowed_roles=None,
                         hitl_required=False, data_classification=None) -> Self: ...
    def with_hitl(self, data_classification="CONFIDENTIAL") -> Self: ...

    # Behavior
    def with_context_key(self, context_key: str) -> Self: ...
    def with_reference_fields(self, fields: list[str]) -> Self: ...

    # Presets (domain-agnostic)
    def with_api_integration(self, provider, scopes, rate_limit=None) -> Self: ...

    # Build
    def build(self, validate=True) -> ToolManifest: ...
```

---

## 🔍 Google Contacts Tools

**Fichier** : `apps/api/src/domains/agents/tools/google_contacts_tools.py`

### Liste des Tools (7 tools)

1. **search_contacts_tool** - Recherche par query
2. **list_contacts_tool** - Liste avec pagination
3. **get_contact_details_tool** - Détails complets d'un contact
4. **create_contact_tool** - Création nouveau contact
5. **update_contact_tool** - Mise à jour contact existant
6. **delete_contact_tool** - Suppression (HITL required)
7. **resolve_reference** - Résolution de référence ("2", "premier", "Jean")

### Exemple Complet : search_contacts_tool

```python
@connector_tool
class SearchContactsTool(ConnectorTool):
    """
    Recherche contacts Google par query.

    Parameters:
        - query (str) : Search query (name, email, phone, company)
        - max_results (int) : Max results to return (default: 10, max: 50)
        - fields (str) : Field set - "minimal", "search", "complete" (default: "search")
        - force_refresh (bool) : Bypass cache (default: False)

    Returns:
        {
            "contacts": [Contact],
            "total_found": int,
            "query": str
        }

    Examples:
        - search_contacts_tool(query="Jean", max_results=5)
        - search_contacts_tool(query="@startup.io", fields="complete")
        - search_contacts_tool(query="06 12 34", max_results=1)

    Permissions:
        - Required scopes: ["contacts.readonly"]
        - HITL required: False
        - Rate limit: 20 calls/min per user

    Cost Profile:
        - Estimated tokens: 500 (input) + 300 (output) = 800
        - Estimated latency: 2000ms (Google API)
        - Estimated cost: $0.002 (gpt-4.1-mini)
    """

    async def execute(
        self,
        query: str,
        max_results: int = 10,
        fields: Literal["minimal", "search", "complete"] = "search",
        force_refresh: bool = False
    ) -> dict:
        """
        Execute search avec caching automatique.

        Flow :
            1. Validate parameters
            2. Build cache key
            3. Check cache (sauf si force_refresh)
            4. Call Google API si cache miss
            5. Format results via ContactFormatter
            6. Store in cache
            7. Return formatted results
        """
        # 1. Validate
        if not query or not query.strip():
            raise ValueError("query cannot be empty")

        if max_results < 1 or max_results > 50:
            raise ValueError("max_results must be between 1 and 50")

        # 2. Build cache key (handled by @with_caching decorator)
        # Cache key: "search_contacts:{query_hash}:{max_results}:{fields}"

        # 3. OAuth refresh (handled by @with_oauth_refresh decorator)

        # 4. Rate limiting (handled by @with_rate_limiting decorator)

        # 5. Call Google API
        logger.info(
            "search_contacts_start",
            query=query,
            max_results=max_results,
            user_id=self.user_id
        )

        start_time = time.perf_counter()

        try:
            # Call via GooglePeopleClient
            raw_contacts = await self.client.search_contacts(
                query=query,
                page_size=max_results,
                read_mask=self._build_read_mask(fields)
            )

            duration = time.perf_counter() - start_time

            # Record metrics
            google_contacts_api_calls.labels(
                operation="search",
                status="success"
            ).inc()

            google_contacts_api_latency.labels(
                operation="search"
            ).observe(duration)

            google_contacts_results_count.labels(
                operation="search"
            ).observe(len(raw_contacts))

        except Exception as e:
            google_contacts_api_calls.labels(
                operation="search",
                status="error"
            ).inc()

            logger.error(
                "search_contacts_error",
                query=query,
                error=str(e),
                exc_info=True
            )

            raise ToolExecutionError(f"Failed to search contacts: {str(e)}")

        # 6. Format results
        formatter = ContactFormatter()
        formatted_contacts = formatter.format_list(raw_contacts, field_set=fields)

        # 7. Return
        result = {
            "contacts": formatted_contacts,
            "total_found": len(formatted_contacts),
            "query": query,
            "fields": fields
        }

        logger.info(
            "search_contacts_complete",
            query=query,
            results_count=len(formatted_contacts),
            duration_ms=round(duration * 1000)
        )

        return result

    def _build_read_mask(self, fields: str) -> str:
        """Build Google API readMask from field_set."""
        if fields == "minimal":
            return "names"
        elif fields == "search":
            return "names,emailAddresses,phoneNumbers,organizations"
        else:  # complete
            return "names,emailAddresses,phoneNumbers,organizations,addresses,birthdays,events,photos,biographies"
```

### Manifests Déclaration

```python
# apps/api/src/domains/agents/google_contacts/catalogue_manifests.py

def build_search_contacts_manifest() -> ToolManifest:
    """Build manifest pour search_contacts_tool."""
    return (
        ToolManifestBuilder("search_contacts_tool", "contact_agent")
        .with_description("Recherche contacts Google par query (nom, email, téléphone, entreprise)")
        .add_parameter("query", "string", required=True, description="Search query")
        .add_parameter("max_results", "integer", description="Max results (1-50)")
        .add_parameter("fields", "string", description="Field set: minimal, search, complete", enum=["minimal", "search", "complete"])
        .add_parameter("force_refresh", "boolean", description="Bypass cache")
        .with_permissions(
            required_scopes=["https://www.googleapis.com/auth/contacts.readonly"],
            hitl_required=False,
            data_classification="CONFIDENTIAL",
        )
        .with_cost_profile(
            est_tokens_in=150, est_tokens_out=400,
            est_cost_usd=0.002, est_latency_ms=2000,
        )
        .with_context_key("contacts")
        .build()
    )

# Register all manifests
GOOGLE_CONTACTS_MANIFESTS = [
    build_search_contacts_manifest(),
    build_list_contacts_manifest(),
    build_get_contact_details_manifest(),
    build_create_contact_manifest(),
    build_update_contact_manifest(),
    build_delete_contact_manifest(),
    build_resolve_reference_manifest(),
]
```

---

## 🛠️ Runtime Helpers

**Fichier** : `apps/api/src/domains/agents/tools/runtime_helpers.py`

### Build Runtime

```python
async def build_tool_runtime(
    user_id: UUID,
    connector_type: ConnectorType,
    session: AsyncSession,
    redis: Redis,
    uow: UnitOfWork,
) -> ToolRuntime:
    """
    Build ToolRuntime for tool execution.

    Args:
        user_id : User ID
        connector_type : Connector type (GOOGLE_CONTACTS, etc.)
        session : Database session
        redis : Redis client
        uow : Unit of Work

    Returns:
        ToolRuntime ready for injection

    Raises:
        ConnectorNotFoundError : Si connector not found
        ConnectorNotActiveError : Si connector inactive
    """
    # 1. Load connector
    async with uow:
        connector = await uow.connectors.get_by_user_and_type(
            user_id=user_id,
            connector_type=connector_type
        )

    if not connector:
        raise ConnectorNotFoundError(
            f"Connector {connector_type} not found for user {user_id}"
        )

    if not connector.is_active:
        raise ConnectorNotActiveError(
            f"Connector {connector_type} is not active"
        )

    # 2. Build API client
    client = await build_connector_client(connector_type, connector)

    # 3. Build runtime
    runtime = ToolRuntime(
        user_id=user_id,
        connector_type=connector_type,
        connector=connector,
        client=client,
        session=session,
        redis=redis,
        uow=uow,
        cache_ttl=300,  # 5 minutes
        metadata={}
    )

    return runtime


async def build_connector_client(
    connector_type: ConnectorType,
    connector: Connector
) -> Any:
    """
    Build API client pour connector.

    Args:
        connector_type : Type de connector
        connector : Connector instance

    Returns:
        API client (GooglePeopleClient, GmailClient, etc.)
    """
    if connector_type == ConnectorType.GOOGLE_CONTACTS:
        from domains.connectors.clients.google_people_client import GooglePeopleClient

        # Decrypt credentials
        credentials = decrypt_connector_credentials(connector)

        return GooglePeopleClient(
            access_token=credentials.access_token,
            refresh_token=credentials.refresh_token,
            redis=redis,
            user_id=connector.user_id,
        )

    elif connector_type == ConnectorType.GOOGLE_GMAIL:
        # Future implementation
        pass

    else:
        raise ValueError(f"Unsupported connector type: {connector_type}")
```

### resolve_contact_to_email (Contact Resolution)

```python
async def resolve_contact_to_email(
    runtime: ToolRuntime,
    name: str,
) -> str | None:
    """
    Resolve a contact name to email address using Google Contacts.

    Uses Google People API searchContacts to find matching contacts
    and extracts the primary email address.

    Args:
        runtime: ToolRuntime with user credentials for Google Contacts API
        name: Contact name to resolve (e.g., "Marie Dupont", "ma femme" after memory resolution)

    Returns:
        Email address if found, None otherwise

    Usage:
        # In SendEmailDraftTool.execute()
        if to and not validate_email(to):
            resolved_email = await resolve_contact_to_email(runtime, to)
            if resolved_email:
                kwargs["to"] = f"{to} <{resolved_email}>"  # RFC 5322 format

    Notes:
        - Uses CONTACT_RESOLUTION_MAX_RESULTS constant (default: 5)
        - Google People API structure: results[].person.emailAddresses[].value
        - Returns first matching email, prioritizing primary email
        - Fails silently (returns None) on errors to allow fallback
    """
    from src.core.constants import CONTACT_RESOLUTION_MAX_RESULTS
    from src.domains.connectors.clients.google_people_client import GooglePeopleClient

    if not runtime or not runtime.config:
        return None

    try:
        # Build Google People client from runtime credentials
        configurable = runtime.config.get("configurable", {})
        deps = configurable.get("__deps")
        user_id = configurable.get("user_id")

        if not deps or not user_id:
            return None

        # Get connector and build client
        connector = await deps.uow.connectors.get_by_user_and_type(
            user_id=user_id,
            connector_type=ConnectorType.GOOGLE_CONTACTS
        )

        if not connector:
            return None

        client = GooglePeopleClient(
            access_token=connector.access_token,
            refresh_token=connector.refresh_token,
        )

        # Search contacts
        response = await client.search_contacts(
            query=name,
            max_results=CONTACT_RESOLUTION_MAX_RESULTS
        )

        # Extract email from results
        # Structure: {"results": [{"person": {"emailAddresses": [{"value": "..."}]}}]}
        results = response.get("results", [])

        for result in results:
            person = result.get("person", {})
            emails = person.get("emailAddresses", [])
            if emails:
                email = emails[0].get("value")
                if email:
                    return email

        return None

    except Exception as e:
        logger.warning(
            "resolve_contact_to_email_error",
            name=name,
            error=str(e),
        )
        return None
```

**Constant associée** :

```python
# apps/api/src/core/constants.py

# Maximum results to fetch when resolving contact name to email
# Used by runtime_helpers.resolve_contact_to_email()
CONTACT_RESOLUTION_MAX_RESULTS = 5
```

---

## ✨ Création d'un Nouveau Tool

### Template Minimal (8 lignes)

```python
@connector_tool
class MyNewTool(ConnectorTool):
    """
    Description de mon nouveau tool.

    Détaille les paramètres, le comportement, les exemples.
    """

    async def execute(self, param1: str, param2: int = 10) -> dict:
        """Execute tool logic."""
        result = await self.client.some_api_call(param1, param2)
        return {"result": result}
```

### Étapes Complètes

#### 1. Créer la Classe Tool

```python
# apps/api/src/domains/agents/tools/my_new_tools.py

@connector_tool
class GetWeatherTool(ConnectorTool):
    """
    Get current weather for a city.

    Parameters:
        - city (str) : City name
        - units (str) : "metric" or "imperial" (default: "metric")

    Returns:
        {
            "city": str,
            "temperature": float,
            "conditions": str,
            "humidity": int
        }
    """

    async def execute(
        self,
        city: str,
        units: Literal["metric", "imperial"] = "metric"
    ) -> dict:
        """Get weather via external API."""
        # Call weather API (assume self.client is WeatherClient)
        weather_data = await self.client.get_current_weather(city, units)

        return {
            "city": city,
            "temperature": weather_data["temp"],
            "conditions": weather_data["description"],
            "humidity": weather_data["humidity"],
            "units": units
        }
```

#### 2. Créer le Manifest

```python
# apps/api/src/domains/agents/my_domain/catalogue_manifests.py

def build_get_weather_manifest() -> ToolManifest:
    """Build manifest pour get_weather_tool."""
    return (
        ToolManifestBuilder("get_weather_tool", "weather_agent")
        .with_description("Get current weather for a city")
        .add_parameter("city", "string", required=True, description="City name")
        .add_parameter("units", "string", description="Units: metric or imperial", enum=["metric", "imperial"])
        .with_permissions(
            required_scopes=[],  # No OAuth required
            hitl_required=False,
            data_classification="PUBLIC",
        )
        .with_cost_profile(
            est_tokens_in=100, est_tokens_out=200,
            est_cost_usd=0.0005, est_latency_ms=500,
        )
        .with_context_key("weathers")
        .build()
    )
```

#### 3. Enregistrer dans le Catalogue

```python
# apps/api/src/domains/agents/my_domain/catalogue_manifests.py

MY_DOMAIN_MANIFESTS = [
    build_get_weather_manifest(),
    # ... autres tools
]

# Add to global catalogue
# apps/api/src/domains/agents/registry/catalogue_loader.py
def load_all_manifests() -> list[ToolManifest]:
    """Load all tool manifests."""
    return [
        *GOOGLE_CONTACTS_MANIFESTS,
        *MY_DOMAIN_MANIFESTS,  # <-- Add ici
    ]
```

#### 4. Créer l'Agent (si nouveau domain)

```python
# apps/api/src/domains/agents/graphs/weather_agent_builder.py

class WeatherAgentBuilder(BaseAgentBuilder):
    """Builder pour weather agent."""

    def build_agent(self) -> CompiledStateGraph:
        """Build weather agent graph."""
        # Similar to contacts_agent_builder
        pass
```

#### 5. Tester

```python
# apps/api/tests/agents/tools/test_weather_tools.py

@pytest.mark.asyncio
async def test_get_weather_tool(mock_weather_client):
    """Test get_weather_tool execution."""
    runtime = ToolRuntime(
        user_id=uuid4(),
        connector_type=ConnectorType.WEATHER,
        connector=None,  # No OAuth needed
        client=mock_weather_client,
        session=mock_session,
        redis=mock_redis,
        uow=mock_uow,
    )

    tool = GetWeatherTool(runtime=runtime)

    result = await tool.execute(city="Paris", units="metric")

    assert result["city"] == "Paris"
    assert "temperature" in result
    assert result["units"] == "metric"
```

**Total : ~60 lignes pour un nouveau tool complet (classe + manifest + test)**

---

## 🔌 MCP Tools Integration

> Documentation complète : [MCP_INTEGRATION.md](MCP_INTEGRATION.md)

### Architecture : Tools Natifs vs MCP

Les tools natifs (Google, Weather, etc.) sont **compilés** dans le code source. Les tools MCP sont **découverts dynamiquement** au runtime depuis des serveurs externes.

| Aspect | Tools Natifs | Tools MCP |
|--------|-------------|-----------|
| Déclaration | Code Python + ToolManifest statique | Découverte runtime via MCP `list_tools()` |
| Authentification | OAuth Google / API Key | None, API Key, Bearer, OAuth 2.1 |
| Enregistrement | `tool_registry.py` + `catalogue_loader.py` | `MCPToolAdapter` (admin) / `UserMCPToolAdapter` (per-user) |
| Lifecycle | Toujours disponibles | Connexions éphémères (connect → call → close) |
| Isolation | Tous les users | Per-user via `ContextVar` |

### Deux types d'adapters MCP

**1. Admin MCP (`MCPToolAdapter`)** — Serveurs configurés en `.env` (globaux) :
- Wrappent chaque tool MCP en `BaseTool` LangChain
- Enregistrés dans `AgentRegistry` + `tool_registry` au démarrage (`main.py` lifespan)
- Domain : `"mcp"` dans `TYPE_TO_DOMAIN_MAP`

**2. Per-User MCP (`UserMCPToolAdapter`)** — Serveurs configurés par l'utilisateur en DB :
- Découverts dynamiquement par request via `ContextVar[UserMCPToolsContext]`
- Injectés dans le catalogue par `SmartCatalogueService` (strategies normal + panic)
- Résolus dans `parallel_executor.py` via le ContextVar en fallback
- Domain : `"mcp_user"` (ou per-server slug `mcp_<server_name>`)
- Naming : `mcp_user_{server_id}_{tool_name}`

### Manifest pour tools MCP

Les manifests MCP sont construits dynamiquement depuis la schema MCP `list_tools()` :

```python
# UserMCPToolAdapter construit un ToolManifest dynamique
ToolManifest(
    name=f"mcp_user_{server_id}_{tool_name}",
    display_name=humanized_tool_name,
    description=tool.description,
    parameters=_json_schema_to_parameters(tool.inputSchema),
    domain=f"mcp_{slugified_server_name}",
    category="mcp",
    cost_tokens=0,  # Pas de coût LLM token pour les appels MCP
    timeout_seconds=server.timeout_seconds,
    hitl_required=server.hitl_required or MCP_HITL_REQUIRED,
)
```

### Résultats structurés

Les tools MCP retournent des `UnifiedToolOutput` avec `registry_updates` :

- **Structured Items** (F2.4) : Si le résultat est un JSON array, chaque élément devient un `RegistryItem` individuel avec `RegistryItemType.MCP_RESULT`
- **Raw** : Si le résultat est du texte ou un objet unique, un seul `RegistryItem` est créé
- **McpResultCard** : Composant HTML pour l'affichage dans le chat (2 modes : structured/raw)

### Pipeline d'intégration

```
User Query → Router → Planner → SmartCatalogueService
                                       │
                          ┌─────────────┼──────────────┐
                          │             │              │
                     Native Tools   Admin MCP    User MCP Tools
                     (registry)     (registry)   (ContextVar)
                          │             │              │
                          └─────────────┼──────────────┘
                                        ↓
                              ParallelExecutor
                                        │
                          ┌─────────────┼──────────────┐
                          │             │              │
                      tool_registry  tool_registry  ContextVar
                      .get_tool()    .get_tool()    fallback
```

3 points d'injection dans `parallel_executor.py` résolvent les tools MCP per-user via le ContextVar quand le tool n'est pas trouvé dans le registry natif.

### Fichiers clés MCP

| Fichier | Rôle |
|---------|------|
| `infrastructure/mcp/tool_adapter.py` | `MCPToolAdapter` (admin servers → BaseTool) |
| `infrastructure/mcp/user_tool_adapter.py` | `UserMCPToolAdapter` (per-user → BaseTool + UnifiedToolOutput) |
| `infrastructure/mcp/user_context.py` | `UserMCPToolsContext` + ContextVar + manifest builder |
| `infrastructure/mcp/client_manager.py` | `MCPClientManager` (admin server lifecycle) |
| `infrastructure/mcp/user_pool.py` | `UserMCPClientPool` (ephemeral connections, rate limiting) |
| `infrastructure/mcp/security.py` | SSRF prevention, URL validation |
| `infrastructure/mcp/auth.py` | `MCPNoAuth`, `MCPStaticTokenAuth`, `MCPOAuth2Auth` |
| `domains/user_mcp/service.py` | Business logic CRUD + credential management |
| `domains/user_mcp/router.py` | 8 API endpoints `/api/v1/mcp/servers/*` |

---

## 💡 Best Practices

### 1. Single Responsibility

Chaque tool fait UNE chose bien :
- ✅ `search_contacts_tool` - Recherche uniquement
- ✅ `get_contact_details_tool` - Détails uniquement
- ❌ `manage_contacts_tool` - Trop générique

### 2. Idempotence

Tools doivent être idempotents si possible :
```python
# ✅ GOOD: Idempotent
async def get_contact_details(resource_name: str):
    # Lecture seule, peut être appelé N fois sans effet de bord
    return await client.get(resource_name)

# ❌ BAD: Non-idempotent sans garde
async def create_contact(name: str):
    # Crée N fois si appelé N fois
    return await client.create({"name": name})

# ✅ GOOD: Idempotent avec garde
async def create_contact_if_not_exists(email: str, name: str):
    existing = await client.search(email)
    if existing:
        return existing[0]
    return await client.create({"email": email, "name": name})
```

### 3. Error Handling

Toujours retourner des erreurs structurées :
```python
try:
    result = await self.client.api_call()
    return {"success": True, "data": result}
except APIError as e:
    logger.error("api_error", error=str(e))
    return {
        "success": False,
        "error": str(e),
        "error_type": "api_error",
        "recoverable": True
    }
except Exception as e:
    logger.error("unexpected_error", error=str(e), exc_info=True)
    return {
        "success": False,
        "error": "Unexpected error occurred",
        "error_type": "internal_error",
        "recoverable": False
    }
```

### 4. Parameter Validation

Valider tôt, échouer vite :
```python
async def execute(self, email: str, max_results: int = 10):
    # Validate email format
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        raise ValueError(f"Invalid email format: {email}")

    # Validate range
    if max_results < 1 or max_results > 100:
        raise ValueError("max_results must be between 1 and 100")

    # Proceed with validated params
    ...
```

### 5. Caching Strategy

Cacher intelligemment :
```python
# ✅ GOOD: Cache search results (5 min)
@with_caching(
    cache_key_fn=lambda query, **kw: f"search:{query}",
    ttl=300
)
async def search_contacts(query: str):
    pass

# ✅ GOOD: Cache contact details (10 min)
@with_caching(
    cache_key_fn=lambda resource_name, **kw: f"details:{resource_name}",
    ttl=600
)
async def get_contact_details(resource_name: str):
    pass

# ❌ BAD: Cache mutations
@with_caching(...)  # NO!
async def update_contact(resource_name: str, data: dict):
    # Mutations should NOT be cached
    pass
```

---

## ⚡ Performance & Caching

### Cache Hit Rates (Observed)

| Tool | Cache Type | TTL | Hit Rate | Latency Reduction |
|------|------------|-----|----------|-------------------|
| **search_contacts** | Redis LRU | 5 min | 75% | 2000ms → 10ms (99.5%) |
| **list_contacts** | Redis LRU | 5 min | 60% | 2500ms → 10ms (99.6%) |
| **get_contact_details** | Redis LRU | 10 min | 85% | 1500ms → 10ms (99.3%) |
| **unified_web_search** | Redis TTL | 5 min | TBD | ~3000ms → 1ms (API savings) |
| **fetch_web_page** | Redis TTL | 10 min | TBD | ~2000ms → 1ms (no HTTP fetch) |

### Rate Limiting Impact

```
Without rate limiting :
  - User fait 100 requêtes en 10s
  - Google API rate limit hit (quota exceeded)
  - All requests fail

With rate limiting (20 req/min) :
  - User fait 25 requêtes en 10s
  - 20 succeed, 5 rejected avec RateLimitExceeded
  - User informé : "Trop de requêtes, attendre 50s"
  - Évite quota exceeded Google
```

### Connection Pooling

```python
# GooglePeopleClient avec httpx persistent connections

client = httpx.AsyncClient(
    limits=httpx.Limits(
        max_connections=100,
        max_keepalive_connections=20,
        keepalive_expiry=30.0
    )
)

# Benefits :
# - Reuse TCP connections
# - Reduce SSL handshake overhead
# - 30-50% latency improvement for repeated calls
```

---

## 📚 Références

### Documentation Interne
- [GRAPH_AND_AGENTS_ARCHITECTURE.md](./GRAPH_AND_AGENTS_ARCHITECTURE.md) - Task Orchestrator
- [AGENT_MANIFEST.md](./AGENT_MANIFEST.md) - Manifests détaillés (10 agents, 50+ tools)
- [CONNECTORS_PATTERNS.md](./CONNECTORS_PATTERNS.md) - Patterns clients OAuth/API Key
- [MCP_INTEGRATION.md](./MCP_INTEGRATION.md) - MCP (Model Context Protocol) intégration complète
- [GUIDE_TOOL_CREATION.md](../guides/GUIDE_TOOL_CREATION.md) - Tutorial création tool

### Fichiers Core
- `apps/api/src/domains/agents/tools/base.py` - ConnectorTool base class
- `apps/api/src/domains/agents/tools/decorators.py` - @connector_tool decorator
- `apps/api/src/domains/agents/tools/formatters.py` - Formatters (Contacts, Emails, Calendar, etc.)
- `apps/api/src/domains/agents/tools/runtime_helpers.py` - Helpers centralisés
- `apps/api/src/domains/agents/registry/manifest_builder.py` - ToolManifestBuilder

### Fichiers Tools par Domaine
- `apps/api/src/domains/agents/tools/google_contacts_tools.py` - Contacts (6 tools)
- `apps/api/src/domains/agents/tools/emails_tools.py` - Emails (6 tools)
- `apps/api/src/domains/agents/tools/google_calendar_tools.py` - Calendar (6 tools)
- `apps/api/src/domains/agents/tools/google_drive_tools.py` - Drive (3 tools)
- `apps/api/src/domains/agents/tools/google_tasks_tools.py` - Tasks (7 tools)
- `apps/api/src/domains/agents/tools/google_places_tools.py` - Places (3 tools)
- `apps/api/src/domains/agents/tools/weather_tools.py` - Weather (3 tools)
- `apps/api/src/domains/agents/tools/wikipedia_tools.py` - Wikipedia (4 tools)
- `apps/api/src/domains/agents/tools/perplexity_tools.py` - Perplexity (2 tools)
- `apps/api/src/domains/agents/tools/context_tools.py` - Context (5 tools)
- `apps/api/src/domains/agents/tools/query_tools.py` - Query (1 tool)

### LangChain Documentation
- **Tools** : https://python.langchain.com/docs/modules/tools/
- **StructuredTool** : https://python.langchain.com/docs/modules/tools/custom_tools/

---

**TOOLS.md** - Version 2.2 - Mars 2026

*Système d'Outils Extensible - Architecture 5 Couches - 17 Domaines Natifs + MCP*
