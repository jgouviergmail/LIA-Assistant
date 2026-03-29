# Guide Création d'Outils - LIA

> Guide pratique pour créer des outils (tools) extensibles pour les agents LangGraph

Version: 1.1
Date: 2025-12-27

---

## 📋 Table des Matières

- [Introduction](#introduction)
- [Architecture Outils](#architecture-outils)
- [Creer un Tool Simple](#créer-un-tool-simple)
- [Pattern ConnectorTool](#pattern-connectortool)
- [Decorator @connector_tool](#decorator-connectortool)
- [Tool Manifests](#tool-manifests)
- [Testing](#testing)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)
- [Outils MCP — Adaptateurs Dynamiques](#outils-mcp--adaptateurs-dynamiques)

---

## 🎯 Introduction

### Qu'est-ce qu'un Tool ?

Un **tool** (outil) est une fonction que les agents LangGraph peuvent invoquer pour interagir avec des APIs externes, des bases de données, ou effectuer des calculs.

**Exemples** :
- `search_contacts_tool` → Recherche contacts Google
- `get_weather_tool` → Récupère météo via API
- `send_email_tool` → Envoie email via Gmail API

### Hiérarchie Tools

```
Tools LIA
├── Standard Tools (simple functions)
│   └── @tool decorator (LangChain)
└── Connector Tools (OAuth + caching)
    └── @connector_tool decorator (custom)
```

**Standard Tools** : Fonctions simples sans OAuth
**Connector Tools** : Outils avec OAuth, caching, rate limiting (Google Contacts, Gmail, etc.)

---

## 🏗️ Architecture Outils

### Vue d'Ensemble

```
┌─────────────────────────────────────────────┐
│ Layer 1: LangChain @tool                    │
│ - Standard tools (no OAuth)                 │
│ - Simple function → LangChain tool          │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────┴──────────────────────────┐
│ Layer 2: ConnectorTool (Base)               │
│ - OAuth token management                    │
│ - Dependency injection                      │
│ - Abstract execute() method                 │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────┴──────────────────────────┐
│ Layer 3: @connector_tool Decorator          │
│ - OAuth refresh automatique                 │
│ - Rate limiting (sliding window)            │
│ - Caching Redis (LRU)                       │
│ - Metrics Prometheus                        │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────┴──────────────────────────┐
│ Layer 4: Tool Manifest                      │
│ - Parameters schema                         │
│ - Permissions required                      │
│ - Cost profile                              │
│ - Usage examples                            │
└─────────────────────────────────────────────┘
```

### Réduction de Boilerplate

**Avant** (150+ lignes) :
```python
class SearchContactsTool(BaseTool):
    def __init__(self, session, redis, client, ...):
        # 10+ dependencies injection
        ...

    async def _run(self, query: str):
        # OAuth refresh (30 lines)
        # Rate limiting (20 lines)
        # Caching (25 lines)
        # API call (10 lines)
        # Result formatting (30 lines)
        # Metrics (10 lines)
```

**Après** (8 lignes) :
```python
@connector_tool
class SearchContactsTool(ConnectorTool):
    async def execute(self, query: str, max_results: int = 10) -> dict:
        """Recherche contacts par query."""
        return await self.client.search_contacts(query, max_results)
```

**Réduction : 94.7%** (150 → 8 lignes)

---

## ✍️ Créer un Tool Simple

### Étape 1 : Tool Function (Sans OAuth)

**Cas d'usage** : Calculator, formatter, ou toute fonction sans API externe nécessitant OAuth.

```python
# apps/api/src/domains/agents/tools/calculator_tools.py
from langchain_core.tools import tool

@tool
async def add_numbers(a: float, b: float) -> float:
    """
    Add two numbers.

    Args:
        a: First number
        b: Second number

    Returns:
        Sum of a and b

    Examples:
        >>> await add_numbers(5, 3)
        8.0
    """
    return a + b

@tool
async def multiply_numbers(a: float, b: float) -> float:
    """
    Multiply two numbers.

    Args:
        a: First number
        b: Second number

    Returns:
        Product of a and b
    """
    return a * b
```

### Étape 2 : Register Tool

```python
# apps/api/src/domains/agents/registry.py
from src.domains.agents.tools.calculator_tools import add_numbers, multiply_numbers

# Register tools
CALCULATOR_TOOLS = [
    add_numbers,
    multiply_numbers,
]

# Agent registry
agent_registry.register_agent(
    "calculator_agent",
    tools=CALCULATOR_TOOLS,
    description="Agent pour calculs mathématiques",
)
```

### Étape 3 : Test

```python
# tests/agents/tools/test_calculator_tools.py
import pytest
from src.domains.agents.tools.calculator_tools import add_numbers, multiply_numbers

@pytest.mark.asyncio
async def test_add_numbers():
    """Test add_numbers tool."""
    result = await add_numbers.ainvoke({"a": 5, "b": 3})
    assert result == 8.0

@pytest.mark.asyncio
async def test_multiply_numbers():
    """Test multiply_numbers tool."""
    result = await multiply_numbers.ainvoke({"a": 5, "b": 3})
    assert result == 15.0
```

**✅ C'est tout !** Pour un tool simple sans OAuth.

---

## 🔷 Pattern ConnectorTool

### Quand Utiliser ConnectorTool ?

**Utiliser ConnectorTool si** :
- ✅ Nécessite OAuth (Google, Microsoft, etc.)
- ✅ Nécessite caching Redis
- ✅ Nécessite rate limiting
- ✅ Appelle API externe avec credentials

**NE PAS utiliser si** :
- ❌ Fonction pure sans API
- ❌ Pas d'OAuth requis
- ❌ Tool interne (calculs, formatage)

### Architecture ConnectorTool

```python
# apps/api/src/domains/agents/tools/base.py
from abc import ABC, abstractmethod

class ConnectorTool(ABC):
    """
    Base class pour connector tools.

    Responsibilities:
        - OAuth token management
        - Dependency injection (client, session, redis)
        - Abstract execute() method

    Attributes:
        client: API client (Google, Microsoft, etc.)
        session: AsyncSession (database)
        redis: Redis client
        uow: Unit of Work
        runtime: ToolRuntime (config, store, state)
    """

    def __init__(self, runtime: ToolRuntime):
        """Initialize tool avec runtime dependencies."""
        self.runtime = runtime
        self.client = runtime.client  # API client (OAuth)
        self.session = runtime.session
        self.redis = runtime.redis
        self.uow = runtime.uow

    @abstractmethod
    async def execute(self, **kwargs) -> dict:
        """
        Execute tool logic.

        Args:
            **kwargs: Tool parameters

        Returns:
            dict with tool results

        Raises:
            ToolExecutionError: If execution fails
        """
        raise NotImplementedError
```

### Exemple Complet - Weather Tool

**Scénario** : Créer un tool qui récupère la météo via OpenWeatherMap API (OAuth API key).

#### 1. Créer API Client

```python
# apps/api/src/domains/connectors/clients/openweathermap_client.py
import httpx
from src.core.config import get_settings

class OpenWeatherMapClient:
    """Client pour OpenWeatherMap API."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.openweathermap.org/data/2.5"

    async def get_current_weather(
        self,
        city: str,
        units: str = "metric"
    ) -> dict:
        """
        Get current weather for a city.

        Args:
            city: City name (e.g., "Paris", "London")
            units: Units system ("metric" or "imperial")

        Returns:
            dict with weather data:
                - temp: Temperature
                - humidity: Humidity %
                - description: Weather description
                - wind_speed: Wind speed

        Raises:
            HTTPException: If API call fails
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/weather",
                params={
                    "q": city,
                    "appid": self.api_key,
                    "units": units,
                },
                timeout=10.0
            )
            response.raise_for_status()
            data = response.json()

            return {
                "temp": data["main"]["temp"],
                "humidity": data["main"]["humidity"],
                "description": data["weather"][0]["description"],
                "wind_speed": data["wind"]["speed"],
                "city": city,
            }
```

#### 2. Créer ConnectorTool

```python
# apps/api/src/domains/agents/tools/weather_tools.py
from src.domains.agents.tools.base import ConnectorTool
from src.domains.agents.tools.decorators import connector_tool

@connector_tool
class GetCurrentWeatherTool(ConnectorTool):
    """Tool pour récupérer météo actuelle."""

    async def execute(
        self,
        city: str,
        units: str = "metric"
    ) -> dict:
        """
        Get current weather for a city.

        Args:
            city: City name (e.g., "Paris")
            units: "metric" (Celsius) or "imperial" (Fahrenheit)

        Returns:
            dict with weather data
        """
        # self.client est injecté automatiquement par ConnectorTool
        weather_data = await self.client.get_current_weather(city, units)

        return {
            "success": True,
            "data": {
                "city": weather_data["city"],
                "temperature": weather_data["temp"],
                "humidity": weather_data["humidity"],
                "conditions": weather_data["description"],
                "wind_speed": weather_data["wind_speed"],
                "units": "°C" if units == "metric" else "°F",
            },
            "message": f"Météo à {city}: {weather_data['temp']}°"
        }
```

#### 3. Register Tool

```python
# apps/api/src/domains/agents/registry.py
from src.domains.agents.tools.weather_tools import GetCurrentWeatherTool
from src.domains.connectors.clients.openweathermap_client import OpenWeatherMapClient

# Initialize client
weather_client = OpenWeatherMapClient(api_key=settings.openweathermap_api_key)

# Register tool
weather_tool = GetCurrentWeatherTool(
    runtime=ToolRuntime(client=weather_client, ...)
)

# Register agent
agent_registry.register_agent(
    "weather_agent",
    tools=[weather_tool],
    description="Agent météo",
)
```

#### 4. Test

```python
# tests/agents/tools/test_weather_tools.py
import pytest
from unittest.mock import AsyncMock, patch
from src.domains.agents.tools.weather_tools import GetCurrentWeatherTool

@pytest.mark.asyncio
async def test_get_current_weather():
    """Test GetCurrentWeatherTool returns weather data."""
    # Mock client
    mock_client = AsyncMock()
    mock_client.get_current_weather.return_value = {
        "temp": 22.5,
        "humidity": 65,
        "description": "Partly cloudy",
        "wind_speed": 5.2,
        "city": "Paris",
    }

    # Create tool with mocked client
    tool = GetCurrentWeatherTool(
        runtime=ToolRuntime(client=mock_client, ...)
    )

    # Execute tool
    result = await tool.execute(city="Paris", units="metric")

    # Assertions
    assert result["success"] is True
    assert result["data"]["city"] == "Paris"
    assert result["data"]["temperature"] == 22.5
    assert result["data"]["units"] == "°C"
    assert "Météo à Paris" in result["message"]

    # Verify client called
    mock_client.get_current_weather.assert_called_once_with("Paris", "metric")
```

---

## 🎨 Decorator @connector_tool

### Qu'est-ce que @connector_tool ?

Le decorator `@connector_tool` combine **4 decorators** en un seul :

1. **@structured_tool** : LangChain integration
2. **@with_oauth_refresh** : OAuth token refresh automatique
3. **@with_rate_limiting** : Sliding window rate limiter
4. **@with_caching** : Redis LRU cache

### Code Source (Simplifié)

```python
# apps/api/src/domains/agents/tools/decorators.py
from functools import wraps

def connector_tool(cls):
    """
    Decorator combining 4 decorators for connector tools.

    Applies (in order):
        1. @structured_tool - LangChain integration
        2. @with_oauth_refresh - Auto token refresh
        3. @with_rate_limiting - Rate limiting (600 req/min)
        4. @with_caching - Redis caching (5min TTL)

    Usage:
        @connector_tool
        class MyTool(ConnectorTool):
            async def execute(self, param: str) -> dict:
                return await self.client.api_call(param)
    """
    # Apply decorators in reverse order (inner → outer)
    cls = with_caching(cls)
    cls = with_rate_limiting(cls)
    cls = with_oauth_refresh(cls)
    cls = structured_tool(cls)
    return cls
```

### Avantages

**Avant (sans decorator)** :
```python
class MyTool(ConnectorTool):
    async def execute(self, param: str) -> dict:
        # Manual OAuth refresh
        if self.credentials.expires_at < datetime.now(UTC):
            await self._refresh_token()

        # Manual rate limiting
        async with self.rate_limiter:
            # Manual caching
            cache_key = f"tool:my_tool:{param}"
            cached = await self.redis.get(cache_key)
            if cached:
                return json.loads(cached)

            # API call
            result = await self.client.api_call(param)

            # Cache result
            await self.redis.setex(cache_key, 300, json.dumps(result))
            return result
```

**Après (avec @connector_tool)** :
```python
@connector_tool
class MyTool(ConnectorTool):
    async def execute(self, param: str) -> dict:
        return await self.client.api_call(param)
```

**Réduction : 20 lignes → 2 lignes = 90% reduction**

### Configuration

```python
# apps/api/src/core/config/ (modular)
class Settings(BaseSettings):
    # OAuth refresh
    oauth_token_refresh_threshold_seconds: int = 300  # 5min avant expiration

    # Rate limiting
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 600  # 600 req/min = 10 req/s
    rate_limit_burst: int = 10

    # Caching
    cache_ttl_seconds: int = 300  # 5min TTL
    cache_enabled: bool = True
```

---

## 📋 Tool Manifests

### Qu'est-ce qu'un Tool Manifest ?

Un **Tool Manifest** déclare les **métadonnées** d'un tool : paramètres, permissions, coût, exemples.

**Utilisé par** :
- **Planner Node** : Charge catalogue filtré par domaine
- **HITL Classifier** : Évalue si outil nécessite approbation
- **Pricing Service** : Calcule coût estimé avant exécution

### Manifest Schema

```python
# apps/api/src/domains/agents/tools/schemas.py
from pydantic import BaseModel, Field

class ParameterSchema(BaseModel):
    """Schema for a tool parameter."""
    name: str
    type: str  # "string", "number", "boolean", "array"
    required: bool = True
    description: str
    default: Any | None = None
    examples: list[Any] = Field(default_factory=list)

class PermissionProfile(BaseModel):
    """Permissions required for tool."""
    scopes: list[str] = Field(default_factory=list)
    resource_types: list[str] = Field(default_factory=list)
    approval_required: bool = False

class CostProfile(BaseModel):
    """Cost profile for tool execution."""
    estimated_cost_usd: float = 0.0
    api_credits: int = 0
    rate_limit_cost: int = 1  # 1 request

class ToolManifest(BaseModel):
    """Complete tool manifest."""
    tool_name: str
    domain: str  # "contacts", "email", "calendar"
    agent_name: str
    description: str
    parameters: list[ParameterSchema]
    permissions: PermissionProfile
    cost: CostProfile
    examples: list[dict] = Field(default_factory=list)
```

### Exemple Complet

```python
# apps/api/src/domains/agents/tools/manifests/contacts_manifests.py
from src.domains.agents.tools.schemas import (
    ToolManifest,
    ParameterSchema,
    PermissionProfile,
    CostProfile,
)

SEARCH_CONTACTS_MANIFEST = ToolManifest(
    tool_name="search_contacts_tool",
    domain="contacts",
    agent_name="contacts_agent",
    description="Search contacts by query string (name, email, phone)",
    parameters=[
        ParameterSchema(
            name="query",
            type="string",
            required=True,
            description="Search query (name, email, phone)",
            examples=["Jean", "jean@example.com", "+33612345678"]
        ),
        ParameterSchema(
            name="max_results",
            type="number",
            required=False,
            description="Maximum number of results (default: 10)",
            default=10,
            examples=[5, 10, 20]
        ),
    ],
    permissions=PermissionProfile(
        scopes=["https://www.googleapis.com/auth/contacts.readonly"],
        resource_types=["contacts"],
        approval_required=False,  # Search is low-risk
    ),
    cost=CostProfile(
        estimated_cost_usd=0.0001,  # Very cheap (cached)
        api_credits=1,  # 1 Google API call
        rate_limit_cost=1,  # 1 request
    ),
    examples=[
        {
            "input": {"query": "Jean", "max_results": 10},
            "output": {
                "success": True,
                "contacts": [
                    {"display_name": "Jean Dupont", "email": "jean@example.com"}
                ],
                "count": 1
            }
        }
    ]
)
```

### Semantic Keywords (ADR-048)

Les `semantic_keywords` permettent la découverte sémantique des outils via OpenAI embeddings et max-pooling.

#### Pourquoi semantic_keywords ?

```
┌─────────────────────────────────────────────────────────────────┐
│                    SEMANTIC TOOL ROUTING                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  User Query: "remind me to call mom tomorrow"                   │
│                          │                                      │
│                          ▼                                      │
│              ┌───────────────────────┐                         │
│              │  OpenAI Embedding     │                         │
│              │  query → 1536 dims    │                         │
│              └───────────┬───────────┘                         │
│                          │                                      │
│                          ▼                                      │
│     ┌────────────────────────────────────────────┐             │
│     │         MAX-POOLING COMPARISON             │             │
│     │                                            │             │
│     │  Tool Keywords:                            │             │
│     │  - "create reminder" ─────→ embed ──┐     │             │
│     │  - "set alert"       ─────→ embed ──┼──▶ MAX            │
│     │  - "schedule task"   ─────→ embed ──┤     │             │
│     │  - "notification"    ─────→ embed ──┘     │             │
│     │                                     │     │             │
│     │                         similarity ◀┘     │             │
│     └────────────────────────────────────────────┘             │
│                          │                                      │
│                          ▼                                      │
│              ┌───────────────────────┐                         │
│              │ Top-3 tools by score  │                         │
│              │ → CREATE_REMINDER     │                         │
│              └───────────────────────┘                         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

#### Règles pour semantic_keywords

| Règle | Description | Exemple |
|-------|-------------|---------|
| **Langue** | Anglais uniquement (optimisé pour le semantic pivot) | ✅ "create reminder" ❌ "créer rappel" |
| **Nombre** | 10-20 mots-clés par outil | Couverture complète des cas d'usage |
| **Style** | Phrases naturelles courtes | ✅ "set alert for meeting" |
| **Verbes** | Actions variées synonymes | "create", "add", "set", "make", "schedule" |
| **Contexte** | Inclure objets typiques | "reminder for appointment", "alert for deadline" |
| **Discriminant** | Distinguish read vs write intent | ✅ "which appointment do I have" for read, "schedule appointment" for write |

#### Exemple Complet

```python
# apps/api/src/domains/reminders/manifests.py

CREATE_REMINDER_MANIFEST = ToolManifest(
    name="CREATE_REMINDER",
    domain="reminders",
    description="Crée un rappel avec notification push",

    # Semantic keywords pour max-pooling
    semantic_keywords=[
        # Verbes d'action principaux
        "create reminder",
        "set reminder",
        "add reminder",
        "make reminder",
        "schedule reminder",

        # Variantes alertes
        "set alert",
        "create notification",
        "schedule alert",

        # Contextes d'usage
        "remind me to",
        "don't forget to",
        "remember to",
        "alert me about",

        # Objets typiques
        "reminder for meeting",
        "reminder for appointment",
        "reminder for task",
        "reminder for deadline",

        # Temporels
        "remind tomorrow",
        "remind later",
        "set alarm",
    ],

    parameters=[
        ToolParameter(
            name="title",
            type=ParameterType.STRING,
            required=True,
            description="Titre du rappel"
        ),
        ToolParameter(
            name="scheduled_at",
            type=ParameterType.DATETIME,
            required=True,
            description="Date/heure ISO8601"
        ),
    ],
    # ...
)
```

#### Impact Performance

```
┌─────────────────────────────────────────────────────────────────┐
│              COMPARAISON AVEC/SANS SEMANTIC KEYWORDS            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  SANS semantic_keywords (approche catalogue complet):           │
│  ├── Tokens envoyés au LLM: 40,000+ tokens                     │
│  ├── Latence: 2-3 secondes                                     │
│  └── Coût: $0.12/requête (GPT-4)                               │
│                                                                 │
│  AVEC semantic_keywords (two-level routing ADR-048):           │
│  ├── 1. Semantic match: OpenAI embeddings                      │
│  ├── 2. Tokens envoyés: 4,000 tokens (top-3 tools)             │
│  ├── Latence totale: 0.5-1 seconde                             │
│  └── Coût: $0.012/requête (90% réduction)                      │
│                                                                 │
│  Performance:                                                   │
│  ├── Précision routing: 94% (validé sur 500 requêtes)          │
│  ├── Token reduction: 80-90%                                   │
│  └── Latency improvement: 60-70%                               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

> 📖 **Références**: [ADR-048-Semantic-Tool-Router.md](../architecture/ADR-048-Semantic-Tool-Router.md), [SEMANTIC_ROUTER.md](../technical/SEMANTIC_ROUTER.md)

### Export pour Planner

```python
# apps/api/src/domains/agents/catalogue.py
def export_manifests_for_planner(domain: str | None = None) -> str:
    """
    Export tool manifests pour Planner LLM prompt.

    Args:
        domain: Optional domain filter (e.g., "contacts")

    Returns:
        Markdown formatted catalogue

    Token Reduction:
        - No filtering: 40K tokens (all tools)
        - Single domain: 4K tokens (90% reduction)
    """
    manifests = get_manifests(domain_filter=domain)

    catalogue = "# Tool Catalogue\n\n"

    for manifest in manifests:
        catalogue += f"## {manifest.tool_name}\n"
        catalogue += f"**Domain**: {manifest.domain}\n"
        catalogue += f"**Description**: {manifest.description}\n"
        catalogue += f"**Parameters**:\n"

        for param in manifest.parameters:
            required = "required" if param.required else "optional"
            catalogue += f"- `{param.name}` ({param.type}, {required}): {param.description}\n"

        catalogue += "\n"

    return catalogue
```

**Usage dans Planner** :

```python
# apps/api/src/domains/agents/nodes/planner.py
from src.domains.agents.catalogue import export_manifests_for_planner

# Load filtered catalogue based on router detected domains
domains_detected = state["routing_decision"]["domains"]  # ["contacts"]
filtered_catalogue = export_manifests_for_planner(domain=domains_detected[0])

# Inject dans prompt
planner_prompt = PLANNER_SYSTEM_PROMPT.format(tool_catalogue=filtered_catalogue)
```

---

## 🧪 Testing

### Test Unitaire - Tool Execution

```python
# tests/agents/tools/test_my_tool.py
import pytest
from unittest.mock import AsyncMock, patch
from src.domains.agents.tools.my_tools import MyTool

@pytest.mark.asyncio
async def test_my_tool_execution():
    """Test MyTool executes successfully."""
    # Mock client
    mock_client = AsyncMock()
    mock_client.api_call.return_value = {"data": "success"}

    # Create tool
    tool = MyTool(runtime=ToolRuntime(client=mock_client, ...))

    # Execute
    result = await tool.execute(param="test")

    # Assertions
    assert result["success"] is True
    assert result["data"] == "success"
    mock_client.api_call.assert_called_once_with("test")
```

### Test d'Intégration - OAuth + API

```python
@pytest.mark.asyncio
@pytest.mark.integration
async def test_my_tool_with_real_api(async_session, redis_client):
    """Test MyTool avec API réelle (credentials de test)."""
    # Setup real client
    client = MyAPIClient(api_key=settings.test_api_key)

    # Create tool
    tool = MyTool(runtime=ToolRuntime(client=client, session=async_session, redis=redis_client))

    # Execute
    result = await tool.execute(param="test_query")

    # Verify real API call succeeded
    assert result["success"] is True
    assert "data" in result
```

### Test Rate Limiting

```python
@pytest.mark.asyncio
async def test_tool_rate_limiting():
    """Test tool respects rate limiting."""
    tool = MyTool(...)

    # Execute 100 calls rapidly
    import time
    start = time.time()

    results = []
    for i in range(100):
        result = await tool.execute(param=f"query_{i}")
        results.append(result)

    elapsed = time.time() - start

    # Should take at least 10 seconds (10 req/s = 600/min)
    assert elapsed >= 10, f"Rate limiting not working (elapsed: {elapsed:.2f}s)"
    assert all(r["success"] for r in results), "Some requests failed"
```

### Test Caching

```python
@pytest.mark.asyncio
async def test_tool_caching(redis_client):
    """Test tool uses caching."""
    mock_client = AsyncMock()
    mock_client.api_call.return_value = {"data": "cached"}

    tool = MyTool(runtime=ToolRuntime(client=mock_client, redis=redis_client))

    # First call - cache miss
    result1 = await tool.execute(param="same_query")
    assert mock_client.api_call.call_count == 1

    # Second call with same param - cache hit
    result2 = await tool.execute(param="same_query")
    assert mock_client.api_call.call_count == 1  # NOT 2 (cache hit)

    # Results identical
    assert result1 == result2
```

---

## 📚 Best Practices

### 1. Naming Conventions

**Tool Names** :
- Format : `{verb}_{resource}_{optional_scope}_tool`
- Examples :
  - ✅ `search_contacts_tool`
  - ✅ `get_contact_details_tool`
  - ✅ `list_emails_unread_tool`
  - ❌ `searchContacts` (pas snake_case)
  - ❌ `contacts_search` (verb pas en premier)

**Class Names** :
- Format : `{Verb}{Resource}{OptionalScope}Tool`
- Examples :
  - ✅ `SearchContactsTool`
  - ✅ `GetContactDetailsTool`
  - ✅ `ListEmailsUnreadTool`

### 2. Docstrings

```python
@connector_tool
class MyTool(ConnectorTool):
    async def execute(self, param: str, optional: int = 10) -> dict:
        """
        [One-liner summary - what the tool does]

        [Detailed description if needed - 2-3 sentences max]

        Args:
            param: [Description with examples]
                Examples: "value1", "value2"
            optional: [Description with default]
                Default: 10

        Returns:
            dict with structure:
                - success: bool - Execution status
                - data: dict - Tool output
                - message: str - Human-readable message

        Raises:
            ToolExecutionError: If API call fails
            ValidationError: If parameters invalid

        Examples:
            >>> result = await tool.execute(param="test", optional=5)
            >>> print(result["success"])
            True
        """
        ...
```

### 3. Error Handling

```python
from src.domains.agents.tools.runtime_helpers import handle_tool_exception

@connector_tool
class MyTool(ConnectorTool):
    async def execute(self, param: str) -> dict:
        """Execute tool with error handling."""
        try:
            # API call
            data = await self.client.api_call(param)

            return {
                "success": True,
                "data": data,
                "message": "Success"
            }

        except httpx.HTTPStatusError as e:
            # Handle HTTP errors (4xx, 5xx)
            return handle_tool_exception(
                e,
                tool_name="my_tool",
                user_message="API call failed. Please try again.",
            )

        except ValueError as e:
            # Handle validation errors
            return handle_tool_exception(
                e,
                tool_name="my_tool",
                user_message=f"Invalid parameter: {e}",
            )

        except Exception as e:
            # Catch-all for unexpected errors
            return handle_tool_exception(
                e,
                tool_name="my_tool",
                user_message="Unexpected error occurred.",
            )
```

### 4. Result Format

**Standard Response** :

```python
{
    "success": bool,           # True if execution succeeded
    "data": dict,              # Tool output (structure varies)
    "message": str,            # Human-readable message
    "metadata": {              # Optional metadata
        "cache_hit": bool,
        "latency_ms": float,
        "api_calls": int,
    }
}
```

**Error Response** :

```python
{
    "success": False,
    "error": {
        "type": "ValidationError",
        "message": "Invalid parameter 'param'",
        "details": {...}
    },
    "message": "Tool execution failed: Invalid parameter"
}
```

### 5. Paramètres Validation

```python
from pydantic import BaseModel, Field, validator

class MyToolInput(BaseModel):
    """Input schema for MyTool."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Search query",
        examples=["search term"]
    )

    max_results: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Max results (1-100)"
    )

    @validator("query")
    def validate_query(cls, v):
        """Validate query is not only whitespace."""
        if not v.strip():
            raise ValueError("Query cannot be empty")
        return v.strip()

# Usage in tool
@connector_tool
class MyTool(ConnectorTool):
    async def execute(self, query: str, max_results: int = 10) -> dict:
        """Execute with validated input."""
        # Validate using Pydantic
        validated = MyToolInput(query=query, max_results=max_results)

        # Use validated values
        result = await self.client.api_call(
            query=validated.query,
            limit=validated.max_results
        )
        return result
```

---

## 🔍 Troubleshooting

### Problème 1 : Tool Non Reconnu par Agent

**Symptômes** :
```
PlanExecutionError: Tool 'my_tool' not found in agent registry
```

**Causes** :
1. Tool pas enregistré dans agent registry
2. Typo dans tool_name
3. Tool pas dans catalogue du domain détecté

**Solutions** :

```python
# ✅ Vérifier registration
from src.domains.agents.registry import agent_registry

# List all tools pour un agent
agent = agent_registry.get_agent("my_agent")
print(agent.tools)  # [my_tool, other_tool, ...]

# ✅ Vérifier tool_name exact
tool_name = "search_contacts_tool"  # Exact match required

# ✅ Vérifier domain dans manifest
manifest = get_manifest("my_tool")
print(manifest.domain)  # Must match router detected domain
```

### Problème 2 : OAuth Token Expired

**Symptômes** :
```
HTTPException: 401 Unauthorized - Token expired
```

**Causes** :
1. `@with_oauth_refresh` decorator pas appliqué
2. OAuth credentials pas valides
3. Refresh token expiré (> 7 jours inactif)

**Solutions** :

```python
# ✅ Vérifier decorator
@connector_tool  # Includes @with_oauth_refresh
class MyTool(ConnectorTool):
    ...

# ✅ Vérifier credentials valides
from src.domains.connectors.service import ConnectorService

connector = await connector_service.get_connector_by_type(
    user_id=user_id,
    connector_type=ConnectorType.MY_SERVICE
)
print(connector.credentials.expires_at)  # Check expiration

# ✅ Force refresh
await connector_service.refresh_oauth_token(
    user_id=user_id,
    connector_type=ConnectorType.MY_SERVICE
)
```

### Problème 3 : Rate Limiting Trop Strict

**Symptômes** :
```
Tool execution slow, taking 30s for 10 calls
```

**Causes** :
1. Rate limit trop bas (10 req/s par défaut)
2. Burst trop bas
3. Sliding window trop strict

**Solutions** :

```python
# ✅ Ajuster rate limit config
# apps/api/src/core/config/ (modular)
class Settings(BaseSettings):
    rate_limit_per_minute: int = 600  # Increase to 600 (10 req/s)
    rate_limit_burst: int = 20        # Allow 20 burst

# ✅ Disable rate limiting pour testing
settings.rate_limit_enabled = False

# ✅ Tool-specific rate limit
@connector_tool(rate_limit_per_minute=1200)  # 20 req/s
class FastTool(ConnectorTool):
    ...
```

### Problème 4 : Cache Hit Rate Bas (<50%)

**Symptômes** :
```
Grafana dashboard shows cache_hit_rate = 30%
```

**Causes** :
1. Cache TTL trop court (< 5min)
2. Queries trop variées (pas de réutilisation)
3. Cache key pas normalisé (ex: "Jean" vs "jean")

**Solutions** :

```python
# ✅ Augmenter TTL
settings.cache_ttl_seconds = 600  # 10min au lieu de 5min

# ✅ Normaliser cache keys
def normalize_query(query: str) -> str:
    """Normalize query for caching."""
    return query.strip().lower()

@connector_tool
class MyTool(ConnectorTool):
    async def execute(self, query: str) -> dict:
        # Normalize before execution (cache key based on normalized)
        query = normalize_query(query)
        result = await self.client.api_call(query)
        return result

# ✅ Monitor cache metrics
from src.infrastructure.observability.metrics_agents import (
    google_contacts_cache_hits,
    google_contacts_cache_misses,
)

# Check Grafana dashboard "Contacts Cache Hit Rate"
```

---

## 🔧 Helpers Centralisés (IMPORTANT)

### Ne pas dupliquer - Réutiliser

Le module `runtime_helpers.py` contient les helpers communs à tous les tools.

**AVANT de créer un helper**, vérifier s'il existe dans :
- `apps/api/src/domains/agents/tools/runtime_helpers.py`
- `apps/api/src/domains/agents/tools/formatters.py`

### Imports standards

```python
from src.domains.agents.tools.runtime_helpers import (
    # Parsing
    parse_user_id,                    # Parse UUID/ULID vers UUID

    # Error handling
    handle_connector_api_error,        # Gestion erreurs unifiée
    handle_tool_exception,             # Gestion exceptions génériques

    # Validation
    validate_runtime_config,           # Valide config runtime
    extract_session_id_from_state,     # Extrait session_id
)
```

### Exemple d'utilisation

```python
from src.domains.agents.tools.runtime_helpers import (
    parse_user_id,
    handle_connector_api_error,
)
from src.infrastructure.observability.metrics_agents import my_api_calls

async def my_tool(user_id_raw, runtime):
    try:
        user_id = parse_user_id(user_id_raw)
        result = await client.api_call()
        return result
    except Exception as e:
        return handle_connector_api_error(
            error=e,
            operation="my_operation",
            tool_name="my_tool",
            params={"key": "value"},
            user_id_str=str(user_id),
            metrics_counter=my_api_calls,
        )
```

---

## 📋 Best Practice #6 : Centralisation des helpers

**Ne pas dupliquer** les fonctions helpers :

| Helper | Source | Usage |
|--------|--------|-------|
| `parse_user_id` | `runtime_helpers.py` | Parse UUID/ULID |
| `handle_connector_api_error` | `runtime_helpers.py` | Error handling unifié |
| `emit_side_channel_chunk` | `runtime_helpers.py` | Emit SSE chunks directly to frontend via side-channel queue |
| `_extract_name`, `_extract_emails`, etc. | `ContactsFormatter` | Extraction données contacts |

**Exemple CORRECT** :
```python
from src.domains.agents.tools.runtime_helpers import parse_user_id
from src.domains.agents.tools.formatters import ContactsFormatter

user_id = parse_user_id(user_id_raw)
name = ContactsFormatter._extract_name(person)
```

**Exemple INCORRECT** :
```python
# ❌ Duplication !
def _parse_user_id(user_id):
    if isinstance(user_id, UUID):
        return user_id
    # ... logique dupliquée
```

---

## SSE Side-Channel (Direct Tool-to-Frontend Events)

Tools can emit SSE events directly to the frontend without going through the LLM
response stream. This is used for progressive browser screenshots but is generic
and reusable by any tool.

### How it works

1. The graph runner creates an `asyncio.Queue` and stores it in
   `RunnableConfig.configurable["__side_channel_queue"]`.
2. Tools call `emit_side_channel_chunk(runtime, chunk)` to put a
   `ChatStreamChunk` into the queue. Fire-and-forget, never raises.
3. `_interleave_side_channel()` in `service.py` polls the queue every 300ms
   and yields chunks to the SSE generator, even when the graph is blocked in
   long node executions.

### Usage

```python
from src.domains.agents.tools.runtime_helpers import emit_side_channel_chunk
from src.domains.agents.api.schemas import ChatStreamChunk

# Build a ChatStreamChunk with your custom type
chunk = ChatStreamChunk(type="my_custom_event", data={"key": "value"})
emit_side_channel_chunk(runtime, chunk)
```

### Nested agents (ReAct)

When creating a nested agent (e.g., `create_react_agent` for browser), forward
the `__side_channel_queue` in the nested `RunnableConfig.configurable` so that
tools inside the nested agent can also emit side-channel events. See
`browser_tools.py` for an example with `__parent_thread_id` forwarding.

---

## Outils MCP — Adaptateurs Dynamiques

### Vue d'ensemble

Les outils MCP ne suivent pas le pattern `@tool` / `@connector_tool` classique. Ils sont decouverts dynamiquement depuis des serveurs MCP externes et wrapes dans des classes `BaseTool` dediees. Deux types d'adaptateurs coexistent :

| Adaptateur | Fichier | Scope | Connexion |
|------------|---------|-------|-----------|
| `MCPToolAdapter` | `infrastructure/mcp/tool_adapter.py` | Admin (global) | Persistante (pool au demarrage) |
| `UserMCPToolAdapter` | `infrastructure/mcp/user_tool_adapter.py` | Per-user | Ephemere (connexion HTTP par appel) |

### MCPToolAdapter (Admin)

Wrapper pour les outils MCP administres globalement. Cree via `MCPToolAdapter.from_mcp_tool()` lors de la decouverte des serveurs au demarrage.

```python
# Nommage : "mcp_{server_name}_{tool_name}"
adapter = MCPToolAdapter.from_mcp_tool(
    server_name="google_flights",
    tool_name="search_flights",
    description="Search for flights...",
    input_schema={...},  # JSON Schema depuis list_tools()
)
```

Points cles :
- `_arun()` appelle `MCPClientManager.call_tool()` (connexion persistante)
- Metriques Prometheus manuelles (pas de `@track_tool_metrics` — incompatible avec BaseTool dynamique)
- Gere le cas MCP Apps (fetch HTML via `read_resource()` si `app_resource_uri` est present)
- `build_args_schema()` convertit le JSON Schema MCP en modele Pydantic pour la validation LangChain

### UserMCPToolAdapter (Per-User)

Wrapper pour les outils MCP personnels de chaque utilisateur. Cree via `UserMCPToolAdapter.from_discovered_tool()`.

```python
# Nommage : "mcp_user_{server_id[:8]}_{tool_name}"
adapter = UserMCPToolAdapter.from_discovered_tool(
    server_id=uuid,
    user_id=uuid,
    server_name="Mon GitHub",
    tool_name="search_repositories",
    description="Search repos...",
    input_schema={...},
)
```

Points cles :
- `_arun()` appelle `UserMCPClientPool.call_tool()` (connexion ephemere par appel)
- **Parsing JSON structure** : `_parse_mcp_structured_items()` analyse le resultat brut et cree N `RegistryItem` (un par element) quand le resultat est un tableau JSON de dicts
- **Collection key derivee** : `_derive_collection_key()` extrait une cle pluralisee du nom d'outil (ex: `search_repositories` → `"repositories"`) pour le `structured_data`
- **Cap d'items** : `MCP_MAX_STRUCTURED_ITEMS_PER_CALL` (defaut 50) empeche l'explosion du registry
- **Fallback** : si le resultat n'est pas un JSON structurable, un seul `RegistryItem` wrapper est cree

#### Flux de parsing structure (UserMCPToolAdapter._arun)

```
raw_result (string MCP)
  → _parse_mcp_structured_items(raw_result)
    → JSON array de dicts ? → (items_list, None)
    → JSON object avec une cle contenant un array de dicts ? → (items_list, detected_key)
    → Sinon → None (fallback single wrapper)
  → Si structure :
    → Pour chaque item (max MCP_MAX_STRUCTURED_ITEMS_PER_CALL) :
      → RegistryItem(type=MCP_RESULT, payload={...item_data, tool_name, server_name})
    → UnifiedToolOutput.data_success(structured_data={collection_key: items})
  → Si fallback :
    → RegistryItem unique avec payload.result = raw_result
    → UnifiedToolOutput.data_success(structured_data={mcps: [...]})
```

### MCP Apps — Helpers partages (`utils.py`)

Le module `infrastructure/mcp/utils.py` centralise les helpers MCP Apps utilises par les deux adaptateurs :

#### `build_mcp_app_output()`

Construit un `UnifiedToolOutput` contenant un `RegistryItem` de type `MCP_APP` pour les widgets interactifs iframe :

```python
output = build_mcp_app_output(
    raw_result=result,           # Resultat brut du call_tool()
    html_content=html,           # HTML fetche via read_resource()
    tool_name="create_view",
    adapter_name="mcp_excalidraw_create_view",
    server_display_name="Excalidraw",
    server_id="",                # UUID pour user, "" pour admin
    server_key="excalidraw",     # Cle config pour admin, "" pour user
    server_source="admin",       # "admin" ou "user"
    resource_uri="ui://...",
    source_label="excalidraw",
    tool_arguments=kwargs,       # Arguments originaux (pour ui/notifications/tool-input)
    tool_input_schema=schema,    # JSON Schema (pour PostMessage bridge)
)
```

Le payload du `RegistryItem` MCP_APP contient `html_content`, `tool_result`, `tool_arguments`, `tool_input_schema` — tout le necessaire pour le bridge PostMessage JSON-RPC cote frontend.

#### `is_app_only()`

Verifie si un outil est en mode iframe-only (`visibility: ["app"]`). Ces outils sont exclus du catalogue LLM dans `registration.py` :

```python
if is_app_only(tool.app_visibility):
    continue  # Skip — iframe uniquement, pas d'appel LLM
```

#### `extract_app_meta()`

Extrait les metadonnees MCP Apps (`resourceUri`, `visibility`) depuis l'objet `Tool.meta.ui` du SDK MCP.

### Excalidraw — Override dans `tool_adapter.py`

La methode `MCPToolAdapter._prepare_excalidraw()` intercepte les appels au tool `create_view` du serveur Excalidraw pour enrichir ou corriger les elements :

```
_prepare_excalidraw(kwargs)
  → Si server != excalidraw OU tool != create_view → passthrough
  → Si elements contient {"intent": true, ...} (mode intent) :
    → build_from_intent(intent, cheat_sheet) : 1 appel LLM unique
      → _generate_diagram() : genere tous les elements (shapes + labels + arrows)
    → Resultat : JSON array d'elements Excalidraw complets
  → Sinon si elements commence par "[" (mode fallback) :
    → correct_positions(elements_str) : corrige overlaps et centrage texte
  → Sinon → passthrough
```

Configuration LLM dediee via `MCP_EXCALIDRAW_LLM_*` dans `.env`. Le suffix `EXCALIDRAW_SPATIAL_SUFFIX` (defini dans `infrastructure/mcp/excalidraw/overrides.py`) est ajoute a la description du tool dans le catalogue pour guider le LLM vers le mode intent.

### Convention `read_me` — Auto-decouverte et filtrage

Les serveurs MCP exposant un outil nomme `read_me` beneficient d'un traitement special :

1. **Au demarrage / connexion** : le contenu de `read_me` est auto-fetche et stocke dans `reference_content`
2. **Filtrage catalogue** : l'outil `read_me` est exclu de l'`AgentManifest` et du catalogue LLM (le contenu est deja disponible)
3. **Injection planner** : le contenu est injecte dans le prompt du planner via `_build_mcp_reference()` (max `MCP_REFERENCE_CONTENT_MAX_CHARS` = 30000 chars)
4. **Supporte** par admin MCP (`MCPClientManager._fetch_reference_content()`) et user MCP (`UserMCPClientPool`)

Cela permet au planner de connaitre les capacites detaillees du serveur sans consommer un slot d'outil dans le catalogue.

### Coercion d'arguments — `_coerce_args_to_schema()`

La fonction `_coerce_args_to_schema()` dans `parallel_executor.py` est appelee avant chaque invocation d'outil pour corriger les types d'arguments generes par le LLM :

- **String → List** : `"item1, item2, item3"` est converti en `["item1", "item2", "item3"]` quand le schema attend un `list`
- **Separateurs multiples** : supporte virgules, points-virgules, retours a la ligne, patterns LLM (`1. item`, `- item`)
- **Delegation** : utilise `type_coercion.coerce_string_to_list()` et `type_coercion.is_list_type()`

Ce mecanisme est particulierement important pour les outils MCP dont le `build_args_schema()` genere des types `list` a partir du JSON Schema, alors que le LLM planner peut produire des strings separees par des virgules.

### Fichiers cles

| Fichier | Role |
|---------|------|
| `infrastructure/mcp/tool_adapter.py` | `MCPToolAdapter` (admin), `build_args_schema()`, `_prepare_excalidraw()` |
| `infrastructure/mcp/user_tool_adapter.py` | `UserMCPToolAdapter` (user), `_parse_mcp_structured_items()` |
| `infrastructure/mcp/utils.py` | `build_mcp_app_output()`, `is_app_only()`, `extract_app_meta()` |
| `infrastructure/mcp/registration.py` | `register_mcp_tools()`, `build_mcp_tool_manifest()`, `json_schema_to_parameters()` |
| `infrastructure/mcp/excalidraw/overrides.py` | `EXCALIDRAW_SPATIAL_SUFFIX`, constantes serveur |
| `infrastructure/mcp/excalidraw/iterative_builder.py` | `build_from_intent()` — builder LLM iteratif (intent-only mode) |
| `domains/agents/orchestration/parallel_executor.py` | `_coerce_args_to_schema()` |
| `domains/agents/orchestration/type_coercion.py` | `coerce_string_to_list()`, `is_list_type()` |

---

## Ressources

### Documentation Interne

- [docs/technical/TOOLS.md](../technical/TOOLS.md) - Architecture tools complete
- [docs/technical/CONNECTORS_PATTERNS.md](../technical/CONNECTORS_PATTERNS.md) - Patterns des connecteurs
- [docs/technical/GOOGLE_CONTACTS_INTEGRATION.md](../technical/GOOGLE_CONTACTS_INTEGRATION.md) - Exemple complet
- [docs/technical/MCP_INTEGRATION.md](../technical/MCP_INTEGRATION.md) - Integration MCP (admin + per-user + OAuth)
- [docs/guides/GUIDE_AGENT_CREATION.md](GUIDE_AGENT_CREATION.md) - Creer un agent

### Code Exemples

- `apps/api/src/domains/agents/tools/google_contacts_tools.py` - 3 tools Google Contacts
- `apps/api/src/domains/agents/tools/emails_tools.py` - 3 tools Emails (multi-provider)
- `apps/api/src/domains/agents/tools/context_tools.py` - Context management tools
- `apps/api/src/domains/agents/tools/base.py` - ConnectorTool base class

### Helpers Centralisés

- `apps/api/src/domains/agents/tools/runtime_helpers.py` - Helpers communs
- `apps/api/src/domains/agents/tools/formatters.py` - Formatters et extractors

### Tests

- `apps/api/tests/agents/tools/test_google_contacts_tools.py` - Tests complets
- `apps/api/tests/agents/tools/test_rate_limiting.py` - Rate limiting tests

---

**Fin de GUIDE_TOOL_CREATION.md**

**Version** : 1.2
**Derniere mise a jour** : 2026-03-08
*v1.2 : Ajout section Outils MCP (UserMCPToolAdapter, MCPToolAdapter, MCP Apps, Excalidraw, read_me, coerce_args)*
*v1.1 : Helpers centralises et retour d'experience Gmail*
