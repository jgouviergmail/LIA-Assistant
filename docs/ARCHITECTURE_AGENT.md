# Architecture des Agents - Guide d'Intégration

> **Version**: 1.2.0 (INTELLIPLANNER + Architecture v3)
> **Dernière mise à jour**: 2026-01-12
> **Auteur**: Documentation générée à partir de l'implémentation réelle

Ce document est le guide de référence exhaustif pour l'ajout d'un nouveau connecteur, d'un nouvel agent ou d'un nouveau tool dans LIA. Il est basé sur l'architecture réelle du système et les patterns établis.

---

## Table des Matières

1. [Vue d'Ensemble de l'Architecture](#1-vue-densemble-de-larchitecture)
2. [Ajouter un Connecteur (Client API)](#2-ajouter-un-connecteur-client-api)
3. [Ajouter un Agent](#3-ajouter-un-agent)
4. [Ajouter un Tool](#4-ajouter-un-tool)
5. [Data Registry](#5-data-registry)
6. [Système de Manifestes](#6-système-de-manifestes)
7. [Enregistrement dans l'Orchestrateur](#7-enregistrement-dans-lorchestrateu)
8. [Cache Redis](#8-cache-redis)
9. [Préférences Connecteur (PostgreSQL)](#9-préférences-connecteur-postgresql)
10. [Checklist d'Intégration](#10-checklist-dintégration)
11. [Cas Particuliers et Subtilités](#11-cas-particuliers-et-subtilités)
12. [Système de Prompts Versionnés](#12-système-de-prompts-versionnés)
13. [Restitution à l'Utilisateur (Response Node)](#13-restitution-à-lutilisateur-response-node)
14. [Exemples Complets](#14-exemples-complets)
15. [Injection de Dépendances (ToolDependencies)](#15-injection-de-dépendances-tooldependencies)
16. [Gestion du Contexte (ToolContextManager)](#16-gestion-du-contexte-toolcontextmanager)
17. [HITL (Human-In-The-Loop) Complet](#17-hitl-human-in-the-loop-complet)
18. [Streaming SSE et Callbacks](#18-streaming-sse-et-callbacks)
19. [Validation des Plans](#19-validation-des-plans)
20. [Métriques et Observabilité](#20-métriques-et-observabilité)
21. [Tests et Patterns](#21-tests-et-patterns)
22. [INTELLIPLANNER - Orchestration Avancée](#22-intelliplanner---orchestration-avancée)

---

## 1. Vue d'Ensemble de l'Architecture

### 1.1 Composants Principaux

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FRONTEND (SSE)                               │
│   ← registry_update events (RegistryItem)                           │
└───────────────────────────────────────────────────────────────────────┘
                                  ↑
┌─────────────────────────────────────────────────────────────────────┐
│                         API LAYER                                    │
│   routes.py → AgentService → Graph (LangGraph)                       │
└───────────────────────────────────────────────────────────────────────┘
                                  ↑
┌─────────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATION LAYER                               │
│   ┌─────────────┐   ┌─────────────┐   ┌─────────────────────────┐  │
│   │   Router    │ → │   Planner   │ → │   ParallelExecutor      │  │
│   │  (routing)  │   │ (planning)  │   │   (tool execution)      │  │
│   └─────────────┘   └─────────────┘   └─────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────┘
                                  ↑
┌─────────────────────────────────────────────────────────────────────┐
│                         TOOLS LAYER                                  │
│   ┌─────────────────────────────────────────────────────────────┐  │
│   │  ConnectorTool / APIKeyConnectorTool (base.py)              │  │
│   │  + ToolOutputMixin (mixins.py)                              │  │
│   │  → StandardToolOutput (output.py)                           │  │
│   └─────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────┘
                                  ↑
┌─────────────────────────────────────────────────────────────────────┐
│                       CLIENTS LAYER                                  │
│   ┌─────────────────────────────────────────────────────────────┐  │
│   │  BaseGoogleClient (OAuth) / BaseAPIKeyClient (API Key)      │  │
│   │  → Rate Limiting, Token Refresh, HTTP Pooling               │  │
│   └─────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────┘
```

### 1.2 Flux de Données

1. **Request** → Router détermine le domaine (calendar, contacts, emails...)
2. **Planner** → Génère un plan d'exécution avec les tools disponibles
3. **ParallelExecutor** → Exécute les tools en parallèle si possible
4. **Tool** → Utilise le Client API pour faire les appels
5. **StandardToolOutput** → Contient `summary_for_llm` + `registry_updates`
6. **SSE** → Envoie les `RegistryItem` au frontend pour rendu riche

> **F6 — Sub-Agent Delegation**: Le planner peut décider de déléguer des tâches complexes à des sous-agents éphémères via `delegate_to_sub_agent_tool` (tool transversal, toujours dans le catalogue). Chaque sous-agent exécute un pipeline simplifié (query analysis → planner → parallel executor → LLM synthesis) sans semantic validator ni approval gate. Les sous-agents sont read-only (V1), invisibles pour l'utilisateur, et ne peuvent pas spawner d'autres sous-agents (depth limit = 1). Détails : `docs/technical/SUB_AGENTS.md`.

### 1.3 Fichiers Clés par Composant

| Composant | Fichiers |
|-----------|----------|
| **Client API** | `src/domains/connectors/clients/{nom}_client.py` |
| **Tool** | `src/domains/agents/tools/{domain}_tools.py` |
| **Agent Builder** | `src/domains/agents/graphs/{domain}_agent_builder.py` |
| **Manifeste Agent** | `src/domains/agents/registry/catalogue_loader.py` |
| **Manifeste Tool** | `src/domains/agents/{domain}/catalogue_manifests.py` |
| **Enregistrement Executor** | `src/domains/agents/orchestration/parallel_executor.py` |
| **Data Registry Types** | `src/domains/agents/data_registry/models.py` |

---

## 2. Ajouter un Connecteur (Client API)

### 2.1 Types de Connecteurs

Il existe deux types de connecteurs selon le mode d'authentification :

| Type | Base Class | Authentification | Exemples |
|------|------------|------------------|----------|
| **OAuth** | `BaseGoogleClient` | OAuth 2.0 avec refresh token | Google Calendar, Gmail, Drive |
| **API Key** | `BaseAPIKeyClient` | Clé API statique | OpenWeatherMap, Perplexity |

### 2.2 Créer un Client OAuth (BaseGoogleClient)

**Fichier**: `src/domains/connectors/clients/google_{domain}_client.py`

```python
"""
Google {Domain} API client.

Provides access to Google {Domain} API with:
- OAuth token management with automatic refresh
- Rate limiting (configurable)
- HTTP client with connection pooling
- Retry logic with exponential backoff
"""

from uuid import UUID
from typing import Any

import structlog
from fastapi import HTTPException, status

from src.core.config import settings
from src.domains.connectors.clients.base_google_client import BaseGoogleClient
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import ConnectorCredentials

logger = structlog.get_logger(__name__)


class Google{Domain}Client(BaseGoogleClient):
    """
    Client for Google {Domain} API.

    Inherits from BaseGoogleClient which provides:
    - Automatic OAuth token refresh with Redis lock
    - Distributed rate limiting via Redis
    - HTTP connection pooling
    - Retry with exponential backoff
    """

    # OBLIGATOIRE: Définir le type de connecteur
    connector_type = ConnectorType.GOOGLE_{DOMAIN}

    # OBLIGATOIRE: URL de base de l'API
    api_base_url = "https://{domain}.googleapis.com/v1"

    def __init__(
        self,
        user_id: UUID,
        credentials: ConnectorCredentials,
        connector_service: Any,
        rate_limit_per_second: int = 10,
    ) -> None:
        """
        Initialize {Domain} client.

        Args:
            user_id: User UUID
            credentials: OAuth credentials (access_token, refresh_token)
            connector_service: ConnectorService for token refresh
            rate_limit_per_second: Max requests per second (default: 10)
        """
        super().__init__(user_id, credentials, connector_service, rate_limit_per_second)

    async def list_items(
        self,
        max_results: int = 100,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        List items from the API.

        Args:
            max_results: Maximum number of items to return
            **kwargs: Additional API parameters

        Returns:
            API response with items list
        """
        params = {
            "maxResults": max_results,
            **kwargs,
        }

        # _make_request est fourni par BaseGoogleClient
        # Gère automatiquement: auth, rate limiting, retries, errors
        return await self._make_request(
            method="GET",
            endpoint="/items",
            params=params,
        )

    async def get_item(self, item_id: str) -> dict[str, Any]:
        """Get a single item by ID."""
        return await self._make_request(
            method="GET",
            endpoint=f"/items/{item_id}",
        )

    async def create_item(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new item."""
        return await self._make_request(
            method="POST",
            endpoint="/items",
            json=data,
        )
```

### 2.3 Créer un Client API Key (BaseAPIKeyClient)

**Fichier**: `src/domains/connectors/clients/{service}_client.py`

```python
"""
{Service} API client with API key authentication.
"""

from uuid import UUID
from typing import Any

import httpx
import structlog

from src.core.config import settings
from src.domains.connectors.clients.base_api_key_client import BaseAPIKeyClient
from src.domains.connectors.models import ConnectorType

logger = structlog.get_logger(__name__)


class {Service}Client(BaseAPIKeyClient):
    """
    Client for {Service} API.

    Uses API key authentication stored in user's connector settings.
    """

    connector_type = ConnectorType.{SERVICE}
    api_base_url = "https://api.{service}.com/v1"

    def __init__(self, api_key: str, user_id: UUID | None = None) -> None:
        """
        Initialize client with API key.

        Args:
            api_key: User's API key for the service
            user_id: Optional user ID for logging/metrics
        """
        super().__init__(api_key, user_id)

    async def search(self, query: str, **kwargs: Any) -> dict[str, Any]:
        """Search the service."""
        return await self._make_request(
            method="GET",
            endpoint="/search",
            params={"q": query, **kwargs},
        )
```

### 2.4 Enregistrer le ConnectorType

**Fichier**: `src/domains/connectors/models.py`

```python
class ConnectorType(str, Enum):
    """Types de connecteurs supportés."""

    # Google Workspace
    GOOGLE_CONTACTS = "google_contacts"
    GOOGLE_GMAIL = "google_gmail"
    GOOGLE_CALENDAR = "google_calendar"
    GOOGLE_DRIVE = "google_drive"
    GOOGLE_TASKS = "google_tasks"

    # AJOUTER ICI:
    GOOGLE_{DOMAIN} = "google_{domain}"

    # API Key services
    OPENWEATHERMAP = "openweathermap"
    PERPLEXITY = "perplexity"
```

### 2.5 Exporter le Client

**Fichier**: `src/domains/connectors/clients/__init__.py`

```python
from .google_{domain}_client import Google{Domain}Client

__all__ = [
    # ... autres exports
    "Google{Domain}Client",
]
```

---

## 3. Ajouter un Agent

### 3.1 Structure d'un Agent

Un agent est composé de :
1. **Agent Builder** - Construit le graphe LangChain avec les tools
2. **Agent Manifest** - Décrit l'agent (nom, tools, description)
3. **System Prompt** - Instructions pour le LLM

### 3.2 Créer l'Agent Builder

**Fichier**: `src/domains/agents/graphs/{domain}_agent_builder.py`

```python
"""
{Domain} Agent Builder (LangChain v1.0) - Using Generic Template.

Builds a compiled LangChain v1 agent for {Domain} operations using the
generic agent builder template for consistency and maintainability.
"""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from src.core.config import settings
from src.domains.agents.graphs.base_agent_builder import (
    build_generic_agent,
    create_agent_config_from_settings,
)
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


# System prompt pour l'agent
{DOMAIN}_AGENT_SYSTEM_PROMPT = """Tu es un agent spécialisé dans {description du domaine}.

**Contexte temporel actuel :** {current_datetime}

## Tes capacités

Tu peux :
1. **Action 1** - Description
2. **Action 2** - Description
3. **Action 3** - Description (avec confirmation utilisateur HITL)

## Instructions importantes

- Point important 1
- Point important 2
- **Opérations d'écriture** : Toujours créer un brouillon (draft) validé par l'utilisateur

## Contexte multi-domaines

{context_instructions}

## Format de réponse

- Format de réponse attendu
"""


def build_{domain}_agent() -> Any:
    """
    Build and compile the {Domain} agent using the generic agent builder template.

    Returns:
        Compiled LangChain agent ready to be wrapped in a parent graph node.
    """
    logger.info("building_{domain}_agent_with_generic_template")

    from typing import cast
    from langchain_core.tools import BaseTool

    # IMPORTER LES TOOLS DU DOMAINE
    from src.domains.agents.tools.{domain}_tools import (
        search_{domain}_tool,
        get_{domain}_details_tool,
        # ... autres tools
    )

    # IMPORTER LES TOOLS DE CONTEXTE (communs à tous les agents)
    from src.domains.agents.tools.context_tools import (
        get_context_list,
        get_context_state,
        list_active_domains,
        resolve_reference,
        set_current_item,
    )

    # LISTE DES TOOLS DISPONIBLES
    tools: list[BaseTool] = cast(
        list[BaseTool],
        [
            # Domain tools
            search_{domain}_tool,
            get_{domain}_details_tool,
            # Context resolution tools (communs)
            resolve_reference,
            get_context_list,
            set_current_item,
            get_context_state,
            list_active_domains,
        ],
    )

    def _get_current_datetime_formatted() -> str:
        """Generate formatted datetime using centralized settings."""
        tz = ZoneInfo(settings.prompt_timezone)
        return datetime.now(tz).strftime(settings.prompt_datetime_format)

    # Instructions de contexte spécifiques au domaine
    context_instructions = """
## Contexte Multi-Domaines ({Domain})

Le domaine "{domain}" est actif pour stocker les résultats.
Les outils resolve_reference, get_context_state fonctionnent avec domain="{domain}".

**Exemples de références contextuelles** :
- $context.{domain}.0 → Premier élément des résultats
- $context.{domain}.current → Élément actuellement sélectionné
    """.strip()

    system_prompt_template = {DOMAIN}_AGENT_SYSTEM_PROMPT.format(
        current_datetime="{current_datetime}",
        context_instructions=context_instructions,
    )

    # Créer la config de l'agent
    config = create_agent_config_from_settings(
        agent_name="{domain}_agent",
        tools=tools,
        system_prompt=system_prompt_template,
        datetime_generator=_get_current_datetime_formatted,
    )

    # Construire l'agent
    agent = build_generic_agent(config)

    logger.info(
        "{domain}_agent_built_successfully",
        tools_count=len(tools),
        llm_model=settings.{domain}_agent_llm_model,
    )

    return agent


__all__ = ["build_{domain}_agent"]
```

### 3.3 Créer le Manifeste de l'Agent

**Fichier**: `src/domains/agents/registry/catalogue_loader.py`

Ajouter dans la section des manifestes d'agents :

```python
# ============================================================================
# Agent Manifest: {domain}_agent
# ============================================================================

{DOMAIN}_AGENT_MANIFEST = AgentManifest(
    name="{domain}_agent",
    description=(
        "Agent spécialisé dans les opérations {description}. "
        "Description des capacités principales. "
        "Les opérations d'écriture nécessitent une confirmation utilisateur via HITL."
    ),
    tools=[
        "search_{domain}_tool",
        "get_{domain}_details_tool",
        "create_{domain}_tool",
        # ... liste de TOUS les tools de l'agent
    ],
    max_parallel_runs=1,
    default_timeout_ms=DEFAULT_TOOL_TIMEOUT_MS,
    prompt_version="v1",
    owner_team="Team AI",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)
```

### 3.4 Enregistrer l'Agent dans le Catalogue

Toujours dans `catalogue_loader.py`, dans la fonction `initialize_catalogue()` :

```python
def initialize_catalogue(registry: "AgentRegistry") -> None:
    """Initialize the catalogue with all manifests."""

    # ... autres registrations

    # Register agent
    registry.register_agent_manifest({DOMAIN}_AGENT_MANIFEST)
```

---

## 4. Ajouter un Tool

### 4.1 Architecture d'un Tool

Un tool complet nécessite :

| Composant | Fichier | Description |
|-----------|---------|-------------|
| **Tool Class** | `{domain}_tools.py` | Classe héritant de `ConnectorTool` |
| **Tool Function** | `{domain}_tools.py` | Fonction décorée `@connector_tool` |
| **Tool Manifest** | `catalogue_manifests.py` | Description complète pour le planner |
| **Registration Executor** | `parallel_executor.py` | Enregistrement pour l'exécution |
| **Registry Type** (optionnel) | `data_registry/models.py` | Type pour le Data Registry |

### 4.2 Créer la Classe Tool

**Fichier**: `src/domains/agents/tools/{domain}_tools.py`

```python
"""
{Domain} tools for agent operations.

Provides tools for:
- Searching {domain} items
- Getting {domain} details
- Creating/updating/deleting items (with HITL)
"""

from typing import Annotated, Any
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime, InjectedToolArg

from src.domains.agents.tools.base import ConnectorTool
from src.domains.agents.tools.common import connector_tool
from src.domains.agents.tools.mixins import ToolOutputMixin
from src.domains.agents.tools.output import StandardToolOutput
from src.domains.connectors.clients.google_{domain}_client import Google{Domain}Client
from src.domains.connectors.models import ConnectorType

logger = structlog.get_logger(__name__)

# Constantes du domaine
AGENT_{DOMAIN} = "{domain}_agent"
CONTEXT_DOMAIN_{DOMAIN} = "{domain}"


# ============================================================================
# TOOL CLASS: Search{Domain}Tool
# ============================================================================

class Search{Domain}Tool(ToolOutputMixin, ConnectorTool[Google{Domain}Client]):
    """
    Search {domain} tool with Data Registry support.

    Benefits:
    - Returns structured data for frontend rich rendering
    - Compact summary for LLM context
    - Full data in registry_updates for SSE
    """

    # OBLIGATOIRE: Type de connecteur
    connector_type = ConnectorType.GOOGLE_{DOMAIN}

    # OBLIGATOIRE: Classe du client API
    client_class = Google{Domain}Client

    # ACTIVER le mode Data Registry
    registry_enabled = True

    def __init__(self) -> None:
        """Initialize with tool name and operation type."""
        super().__init__(
            tool_name="search_{domain}_tool",
            operation="search",  # Utilisé pour logs/metrics
        )

    async def execute_api_call(
        self,
        client: Google{Domain}Client,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Execute the API call - business logic only.

        La classe de base gère automatiquement:
        - Injection des dépendances (ToolDependencies)
        - Récupération des credentials OAuth
        - Création/cache du client API
        - Gestion des erreurs
        - Rate limiting

        Args:
            client: Client API injecté automatiquement
            user_id: UUID de l'utilisateur
            **kwargs: Paramètres du tool (query, max_results, etc.)

        Returns:
            Dict avec les résultats de l'API
        """
        query: str | None = kwargs.get("query")
        max_results: int = kwargs.get("max_results", 10)

        # Appel API via le client
        result = await client.search(
            query=query,
            max_results=max_results,
        )

        items = result.get("items", [])

        logger.info(
            "search_{domain}_success",
            user_id=str(user_id),
            query=query,
            results_count=len(items),
        )

        return {
            "items": items,
            "query": query,
            "total": len(items),
        }

    def format_registry_response(self, result: dict[str, Any]) -> StandardToolOutput:
        """
        Format response for Data Registry mode.

        OBLIGATOIRE si registry_enabled=True.

        Returns:
            StandardToolOutput avec:
            - summary_for_llm: Résumé compact pour le LLM
            - registry_updates: Dict de RegistryItem pour le frontend
        """
        from src.domains.agents.data_registry.models import (
            RegistryItem,
            RegistryItemMeta,
            RegistryItemType,
            generate_registry_id,
        )

        items = result.get("items", [])
        query = result.get("query")

        # Construire les registry items
        registry_updates: dict[str, RegistryItem] = {}
        summary_parts = []

        for item in items:
            item_id = item.get("id", "")
            if not item_id:
                continue

            # ID déterministe basé sur l'ID source
            registry_id = generate_registry_id(RegistryItemType.{DOMAIN}, item_id)

            # Créer le RegistryItem
            registry_updates[registry_id] = RegistryItem(
                id=registry_id,
                type=RegistryItemType.{DOMAIN},
                payload=item,  # Données complètes pour le frontend
                meta=RegistryItemMeta(
                    source="google_{domain}",
                    domain="{domain}",
                    tool_name="search_{domain}_tool",
                ),
            )

            # Résumé pour le LLM
            name = item.get("name", "Sans nom")
            summary_parts.append(f"- {name} [{registry_id}]")

        # Construire le summary pour le LLM
        if items:
            summary_for_llm = f"[search] {len(items)} résultat(s):\n" + "\n".join(
                summary_parts[:5]  # Limiter pour économiser les tokens
            )
            if len(items) > 5:
                summary_for_llm += f"\n... et {len(items) - 5} autre(s)"
        else:
            summary_for_llm = f"[search] Aucun résultat pour '{query}'"

        return StandardToolOutput(
            success=True,
            summary_for_llm=summary_for_llm,
            registry_updates=registry_updates,
            requires_confirmation=False,
            tool_metadata={
                "tool_name": "search_{domain}_tool",
                "query": query,
                "total": len(items),
            },
        )


# Instance singleton du tool
_search_{domain}_tool_instance = Search{Domain}Tool()


# ============================================================================
# TOOL FUNCTION: Décorateur LangChain
# ============================================================================

@connector_tool(
    name="search_{domain}",
    agent_name=AGENT_{DOMAIN},
    context_domain=CONTEXT_DOMAIN_{DOMAIN},
    category="read",
)
async def search_{domain}_tool(
    query: Annotated[
        str | None,
        "Search query to find {domain} items",
    ] = None,
    max_results: Annotated[
        int,
        "Maximum number of results to return (default: 10, max: 50)",
    ] = 10,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> StandardToolOutput:
    """
    Search for {domain} items.

    **Use Cases:**
    - User asks "recherche mes {domain}"
    - User wants to find specific items

    **Output includes:**
    - id: Item unique identifier
    - name: Item name/title
    - Additional fields specific to domain

    Args:
        query: Search query (optional)
        max_results: Max results (default: 10)
        runtime: Tool runtime (injected by LangChain)

    Returns:
        StandardToolOutput with {DOMAIN} registry items

    Example:
        User: "Recherche mes documents sur le projet X"
        -> Returns list of matching items
    """
    return await _search_{domain}_tool_instance.execute(
        runtime=runtime,
        query=query,
        max_results=max_results,
    )


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Tool functions
    "search_{domain}_tool",
    "get_{domain}_details_tool",
    # Tool classes
    "Search{Domain}Tool",
    # Constants
    "CONTEXT_DOMAIN_{DOMAIN}",
]
```

### 4.3 Utiliser ToolOutputMixin pour les Helpers

La classe `ToolOutputMixin` fournit des méthodes helper pré-construites pour les domaines courants :

```python
# Dans format_registry_response(), utiliser les helpers si disponibles:

def format_registry_response(self, result: dict[str, Any]) -> StandardToolOutput:
    # Pour les contacts
    return self.build_contacts_output(
        contacts=result["contacts"],
        query=result.get("query"),
    )

    # Pour les emails
    return self.build_emails_output(
        emails=result["emails"],
        query=result.get("query"),
        user_timezone="Europe/Paris",
        locale="fr",
    )

    # Pour les événements
    return self.build_events_output(
        events=result["events"],
        user_timezone="Europe/Paris",
        locale="fr",
    )

    # Pour les fichiers
    return self.build_files_output(
        files=result["files"],
        query=result.get("query"),
    )

    # Pour les tâches
    return self.build_tasks_output(
        tasks=result["tasks"],
    )

    # Pour la météo
    return self.build_weather_output(
        weather_data=result,
        location=result.get("location"),
    )

    # Pour les lieux (Places)
    return self.build_places_output(
        places=result["places"],
        query=result.get("query"),
    )
```

---

## 5. Data Registry

### 5.1 Concept

Le Data Registry sépare ce que voit le LLM (summary compact) de ce que reçoit le frontend (données complètes).

```
┌─────────────────────────────────────────────────────────────┐
│                      StandardToolOutput                      │
├─────────────────────────────────────────────────────────────┤
│  summary_for_llm: "Found 3 contacts: John, Jane, Bob"       │ → LLM Context
├─────────────────────────────────────────────────────────────┤
│  registry_updates: {                                         │
│    "contact_abc123": RegistryItem(                          │
│      type=CONTACT,                                          │
│      payload={full contact data...}                         │ → Frontend SSE
│    ),                                                        │
│    ...                                                       │
│  }                                                           │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 Ajouter un Nouveau RegistryItemType

**Fichier**: `src/domains/agents/data_registry/models.py`

```python
class RegistryItemType(str, Enum):
    """
    Types of items that can be stored in the Data Registry.

    Naming Convention:
    - Use singular form (CONTACT, not CONTACTS)
    - Use SCREAMING_SNAKE_CASE
    """

    # Google Workspace domain types
    CONTACT = "CONTACT"
    EMAIL = "EMAIL"
    EVENT = "EVENT"
    TASK = "TASK"
    FILE = "FILE"
    CALENDAR = "CALENDAR"  # <-- EXEMPLE AJOUTÉ

    # External API domain types
    PLACE = "PLACE"
    WEATHER = "WEATHER"
    WIKIPEDIA_ARTICLE = "WIKIPEDIA_ARTICLE"
    SEARCH_RESULT = "SEARCH_RESULT"

    # AJOUTER VOTRE TYPE ICI:
    {DOMAIN} = "{DOMAIN}"

    # HITL/Draft types
    DRAFT = "DRAFT"

    # Utility types
    CHART = "CHART"
    NOTE = "NOTE"
```

### 5.3 Générer un Registry ID

```python
from src.domains.agents.data_registry.models import (
    generate_registry_id,
    RegistryItemType,
)

# ID déterministe basé sur le type et l'identifiant source
registry_id = generate_registry_id(
    item_type=RegistryItemType.CALENDAR,
    unique_key="primary@gmail.com",  # ID de la source
)
# Résultat: "calendar_7f8a9b" (préfixe + hash court)
```

---

## 6. Système de Manifestes

### 6.1 ToolManifest - Description Complète d'un Tool

**Fichier**: `src/domains/agents/{domain}/catalogue_manifests.py`

```python
"""
Catalogue manifests for {Domain} agent tools.

These declarative manifests serve as the single source of truth for:
- Planner LLM (plan generation)
- Validator (permissions, costs, parameters)
- Orchestrator (execution)
- Documentation (auto-generated API docs)
"""

from datetime import UTC, datetime

from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterConstraint,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)
from src.domains.agents.tools.formatters import enrich_description_with_examples

# Scopes OAuth requis
GOOGLE_{DOMAIN}_SCOPES = [
    "https://www.googleapis.com/auth/{domain}.readonly",
]


# =============================================================================
# SEARCH TOOL MANIFEST
# =============================================================================

_search_{domain}_base_description = (
    "Search for {domain} items.\n\n"
    "**When to use**: User wants to find or list {domain} items\n"
    "- Keywords: 'search', 'find', 'list', 'show'\n\n"
    "**Output**: List of items with:\n"
    "- id: Unique identifier\n"
    "- name: Item name\n"
    "- Additional relevant fields\n\n"
    "**DO NOT use for**:\n"
    "- Getting details of a specific item -> use get_{domain}_details_tool"
)

_search_{domain}_examples = [
    {
        "description": "Search all items",
        "input": {"max_results": 10},
        "output": {
            "items": [
                {"id": "123", "name": "Item 1"},
                {"id": "456", "name": "Item 2"},
            ],
            "total": 2,
        },
    },
    {
        "description": "Search with query",
        "input": {"query": "project", "max_results": 5},
        "output": {
            "items": [{"id": "789", "name": "Project Document"}],
            "total": 1,
        },
    },
]

search_{domain}_catalogue_manifest = ToolManifest(
    # === IDENTITY ===
    name="search_{domain}_tool",
    agent="{domain}_agent",
    description=enrich_description_with_examples(
        _search_{domain}_base_description,
        _search_{domain}_examples,
        max_examples=2,
        format_style="minimal",
    ),

    # === CONTRACT - PARAMETERS ===
    parameters=[
        ParameterSchema(
            name="query",
            type="string",
            required=False,
            description="Search query to filter results",
            constraints=[
                ParameterConstraint(kind="min_length", value=1),
                ParameterConstraint(kind="max_length", value=500),
            ],
        ),
        ParameterSchema(
            name="max_results",
            type="integer",
            required=False,
            description="Maximum number of results (default: 10, max: 50)",
            constraints=[
                ParameterConstraint(kind="minimum", value=1),
                ParameterConstraint(kind="maximum", value=50),
            ],
        ),
    ],

    # === CONTRACT - OUTPUTS ===
    outputs=[
        OutputFieldSchema(
            path="items",
            type="array",
            description="List of matching items",
        ),
        OutputFieldSchema(
            path="items[].id",
            type="string",
            description="Unique item identifier",
        ),
        OutputFieldSchema(
            path="items[].name",
            type="string",
            description="Item name/title",
        ),
        OutputFieldSchema(
            path="total",
            type="integer",
            description="Total number of results",
        ),
    ],

    # === COST & PERFORMANCE ===
    cost=CostProfile(
        est_tokens_in=150,
        est_tokens_out=500,
        est_cost_usd=0.002,
        est_latency_ms=500,
    ),

    # === SECURITY ===
    permissions=PermissionProfile(
        required_scopes=GOOGLE_{DOMAIN}_SCOPES,
        hitl_required=False,  # Read operation, no approval needed
        data_classification="CONFIDENTIAL",
    ),

    # === BEHAVIOR ===
    max_iterations=1,
    supports_dry_run=False,
    reference_fields=["id", "name"],

    # === CONTEXT KEY (IMPORTANT) ===
    # Si défini, les résultats sont sauvegardés dans le contexte conversationnel
    # Le context_key DOIT être enregistré dans ContextTypeRegistry
    # Laisser None si les données sont juste des références (pas de contexte)
    context_key="{domain}",  # ou None si pas de contexte

    # === DOCUMENTATION ===
    examples=_search_{domain}_examples,
    examples_in_prompt=True,  # Inclure exemples dans prompt du planner
    reference_examples=[
        "items[0].id",
        "items[*].name",
        "total",
    ],

    # === VERSIONING ===
    version="1.0.0",
    maintainer="Team AI",

    # === DISPLAY (UI) ===
    display=DisplayMetadata(
        emoji="🔍",
        i18n_key="search_{domain}",
        visible=True,
        category="tool",
    ),
)


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "search_{domain}_catalogue_manifest",
    "get_{domain}_details_catalogue_manifest",
    # ... autres manifestes
]
```

### 6.2 Enregistrer les Manifestes dans le Catalogue

**Fichier**: `src/domains/agents/registry/catalogue_loader.py`

```python
def initialize_catalogue(registry: "AgentRegistry") -> None:
    """Initialize the catalogue with all manifests."""

    # === IMPORT DES MANIFESTES ===
    from src.domains.agents.{domain}.catalogue_manifests import (
        search_{domain}_catalogue_manifest,
        get_{domain}_details_catalogue_manifest,
    )

    # === ENREGISTREMENT DES TOOL MANIFESTS ===
    registry.register_tool_manifest(search_{domain}_catalogue_manifest)
    registry.register_tool_manifest(get_{domain}_details_catalogue_manifest)

    # === LOG DE VÉRIFICATION ===
    logger.info(
        "catalogue_initialized",
        tools_{domain}=[
            "search_{domain}_tool",
            "get_{domain}_details_tool",
        ],
    )
```

---

## 7. Enregistrement dans l'Orchestrateur

### 7.1 Pourquoi c'est Nécessaire

Le `ParallelExecutor` maintient son propre registry de tools pour l'exécution. **Un tool non enregistré ici ne sera pas exécutable**, même s'il est dans le manifeste du planner.

**Erreur typique si oublié:**
```
Tool 'search_{domain}_tool' not found in registry. Available tools: [...]
```

### 7.2 Enregistrer dans parallel_executor.py

**Fichier**: `src/domains/agents/orchestration/parallel_executor.py`

#### Étape 1: Ajouter aux OPTIONAL_PARAMS

```python
# Dictionnaire des paramètres requis par tool
OPTIONAL_PARAMS: dict[str, list[str]] = {
    # ... autres tools

    # {Domain} tools
    "search_{domain}_tool": [],  # Tous optionnels
    "get_{domain}_details_tool": ["item_id"],  # item_id requis
    "create_{domain}_tool": ["name", "data"],  # Requis
}
```

#### Étape 2: Importer le Tool

```python
class ToolRegistry:
    def _initialize_registry(self) -> None:
        # ... autres imports

        # {Domain} tools
        from src.domains.agents.tools.{domain}_tools import (
            search_{domain}_tool,
            get_{domain}_details_tool,
            create_{domain}_tool,
        )
```

#### Étape 3: Ajouter à la Liste tools

```python
        # Register all tools by name
        tools = [
            # ... autres tools

            # {Domain} tools
            search_{domain}_tool,
            get_{domain}_details_tool,
            create_{domain}_tool,
        ]
```

---

## 8. Cache Redis

Le système utilise Redis pour le cache à plusieurs niveaux :
- **Cache API** : Résultats des appels API (contacts, places, etc.)
- **Cache LLM** : Réponses du router/planner (appels déterministes)

### 8.1 Architecture du Cache

```
┌─────────────────────────────────────────────────────────────────────┐
│                          REDIS CACHE                                 │
├─────────────────────────────────────────────────────────────────────┤
│  LLM Cache (Router/Planner)                                         │
│  ├── llm_cache:router:{hash}     → RouterOutput (TTL: 5min)        │
│  └── llm_cache:planner:{hash}    → PlannerOutput (TTL: 5min)       │
├─────────────────────────────────────────────────────────────────────┤
│  API Cache (Connectors)                                              │
│  ├── contacts_list:{user_id}         → Contacts list (TTL: 5min)   │
│  ├── contacts_search:{user_id}:{h}   → Search results (TTL: 3min)  │
│  ├── contacts_details:{user_id}:{rn} → Contact details (TTL: 5min) │
│  ├── places_search:{user_id}:{h}     → Places results (TTL: 5min)  │
│  ├── places_nearby:{user_id}:...     → Nearby results (TTL: 5min)  │
│  └── places_details:{user_id}:{pid}  → Place details (TTL: 5min)   │
└─────────────────────────────────────────────────────────────────────┘
```

### 8.2 Cache LLM avec Décorateur

**Fichier**: `src/infrastructure/cache/llm_cache.py`

Le décorateur `@cache_llm_response` permet de cacher les appels LLM déterministes (température=0.0) :

```python
from src.infrastructure.cache import cache_llm_response

@cache_llm_response(ttl_seconds=300, enabled=settings.llm_cache_enabled)
async def classify_intent(query: str, model: str = "gpt-4") -> dict:
    """
    Appel LLM déterministe (temperature=0.0).

    Premier appel: Cache MISS → appel LLM → cache → return
    Second appel (mêmes args): Cache HIT → return cached → économie 2s + $0.02
    """
    # ... appel LLM ...
    return {"intent": "search", "confidence": 0.95}
```

**Caractéristiques:**
- Génération de clé déterministe (SHA256 des arguments)
- Exclut automatiquement le paramètre `config` (callbacks, connections)
- Format V2 avec métadonnées (usage tokens pour métriques)
- Métriques Prometheus: `llm_cache_hits_total`, `llm_cache_misses_total`

**Usage dans le code existant:**

```python
# src/domains/agents/nodes/router_node_v3.py (Architecture v3)
# Note: Le router utilise maintenant QueryAnalyzerService pour l'analyse
async def router_node_v3(state: AgentState, config: RunnableConfig) -> dict:
    # ... appel routeur LLM ...
```

### 8.3 Cache API (Contacts, Places, etc.)

Pour les données API, créez une classe de cache dédiée.

**Fichier**: `src/infrastructure/cache/{domain}_cache.py`

```python
"""
Redis cache for {Domain} data.
Reduces API calls and improves response time.

V2 Features (Freshness Transparency):
- Metadata wrapper with cached_at timestamp (ISO 8601 UTC)
- Returns (data, from_cache, cached_at, cache_age_seconds) tuple
"""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import redis.asyncio as aioredis
import structlog

from src.core.config import get_settings
from src.core.field_names import FIELD_CACHED_AT

logger = structlog.get_logger(__name__)
settings = get_settings()


class {Domain}Cache:
    """
    Redis-based cache for {Domain} queries.

    Cache strategies:
    - List: 5 min TTL
    - Search: 3 min TTL (query-specific)
    - Details: 5 min TTL
    """

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self.redis = redis_client

    def _make_search_key(self, user_id: UUID, query: str) -> str:
        """Generate cache key for search."""
        query_hash = hashlib.md5(query.lower().encode()).hexdigest()[:8]
        return f"{domain}_search:{user_id}:{query_hash}"

    def _make_details_key(self, user_id: UUID, item_id: str) -> str:
        """Generate cache key for details."""
        return f"{domain}_details:{user_id}:{item_id}"

    def _calculate_cache_age(self, cached_at: str) -> int:
        """Calculate cache age in seconds from ISO 8601 timestamp."""
        try:
            cached_dt = datetime.fromisoformat(cached_at.replace("Z", "+00:00"))
            delta = datetime.now(UTC) - cached_dt
            return int(delta.total_seconds())
        except Exception:
            return 0

    async def get_search(
        self, user_id: UUID, query: str
    ) -> tuple[dict[str, Any] | None, bool, str | None, int | None]:
        """
        Get cached search results with metadata.

        Returns:
            Tuple of (data, from_cache, cached_at, cache_age_seconds)
        """
        key = self._make_search_key(user_id, query)
        try:
            cached = await self.redis.get(key)
            if cached:
                parsed = json.loads(cached)
                if isinstance(parsed, dict) and "data" in parsed and FIELD_CACHED_AT in parsed:
                    data = parsed["data"]
                    cached_at = parsed[FIELD_CACHED_AT]
                    cache_age = self._calculate_cache_age(cached_at)

                    logger.debug(
                        "{domain}_cache_hit",
                        cache_type="search",
                        user_id=str(user_id),
                        cache_age_seconds=cache_age,
                    )
                    return data, True, cached_at, cache_age

            logger.debug("{domain}_cache_miss", cache_type="search", user_id=str(user_id))
            return None, False, None, None

        except Exception as e:
            logger.warning("{domain}_cache_get_failed", error=str(e))
            return None, False, None, None

    async def set_search(
        self, user_id: UUID, query: str, data: dict[str, Any], ttl_seconds: int = 180
    ) -> None:
        """Cache search results with metadata wrapper (V2 format)."""
        key = self._make_search_key(user_id, query)
        try:
            cache_entry = {
                "data": data,
                FIELD_CACHED_AT: datetime.now(UTC).isoformat(),
                "ttl": ttl_seconds,
            }
            await self.redis.set(key, json.dumps(cache_entry), ex=ttl_seconds)
            logger.debug("{domain}_cache_set", cache_type="search", ttl_seconds=ttl_seconds)
        except Exception as e:
            logger.warning("{domain}_cache_set_failed", error=str(e))

    async def invalidate_user(self, user_id: UUID) -> None:
        """Invalidate all cached data for a user (on write operations)."""
        patterns = [
            f"{domain}_search:{user_id}:*",
            f"{domain}_details:{user_id}:*",
        ]
        # ... scan and delete matching keys ...
```

### 8.4 Utilisation du Cache dans un Client

```python
# src/domains/connectors/clients/google_{domain}_client.py

from src.infrastructure.cache import {Domain}Cache
from src.infrastructure.cache.redis import get_redis_cache

class Google{Domain}Client(BaseGoogleClient):

    async def search(self, query: str, use_cache: bool = True) -> dict[str, Any]:
        """Search with optional caching."""

        if use_cache:
            # Get Redis client
            redis = await get_redis_cache()
            cache = {Domain}Cache(redis)

            # Try cache first
            cached_data, from_cache, cached_at, cache_age = await cache.get_search(
                self.user_id, query
            )

            if from_cache and cached_data:
                logger.info(
                    "{domain}_search_cache_hit",
                    query=query,
                    cache_age_seconds=cache_age,
                )
                # Ajouter metadata pour transparence UX
                cached_data[FIELD_CACHED_AT] = cached_at
                return cached_data

        # Cache miss - appel API
        result = await self._make_request("GET", "/search", params={"q": query})

        if use_cache:
            # Cache le résultat
            await cache.set_search(self.user_id, query, result)

        return result
```

### 8.5 Export du Cache

**Fichier**: `src/infrastructure/cache/__init__.py`

```python
from .{domain}_cache import {Domain}Cache
from .llm_cache import cache_llm_response, invalidate_llm_cache
from .redis import CacheService, get_redis_cache

__all__ = [
    "CacheService",
    "{Domain}Cache",
    "cache_llm_response",
    "get_redis_cache",
    "invalidate_llm_cache",
]
```

---

## 9. Préférences Connecteur (PostgreSQL)

Certains connecteurs supportent des préférences utilisateur persistées en base (ex: calendrier par défaut).

### 9.1 Architecture des Préférences

```
┌─────────────────────────────────────────────────────────────────────┐
│                      PostgreSQL - Table connectors                   │
├─────────────────────────────────────────────────────────────────────┤
│  id | user_id | type          | credentials_encrypted | preferences_encrypted │
│  ───────────────────────────────────────────────────────────────────│
│  1  | uuid1   | google_calendar| {oauth_tokens}       | {default_cal: "Famille"} │
│  2  | uuid1   | google_tasks   | {oauth_tokens}       | {default_list: "Perso"}  │
└─────────────────────────────────────────────────────────────────────┘
                                  ↓
┌─────────────────────────────────────────────────────────────────────┐
│              ConnectorPreferencesService                             │
│  - validate_and_encrypt() : Validation Pydantic + Fernet encrypt    │
│  - decrypt_and_get()      : Décryptage + désérialisation            │
│  - get_preference_value() : Accès direct à une préférence           │
└─────────────────────────────────────────────────────────────────────┘
```

### 9.2 Créer un Schéma de Préférences

**Fichier**: `src/domains/connectors/preferences/schemas.py`

```python
from pydantic import BaseModel, ConfigDict, Field
from typing import ClassVar


class BaseConnectorPreferences(BaseModel):
    """Base class for connector preferences."""

    connector_type: ClassVar[str]

    model_config = ConfigDict(
        extra="forbid",           # Rejette champs inconnus
        str_strip_whitespace=True,
    )


class Google{Domain}Preferences(BaseConnectorPreferences):
    """
    Preferences for Google {Domain} connector.

    Security:
    - max_length=100 prevents excessive data storage
    - Values are sanitized before encryption (dangerous chars removed)
    """

    connector_type: ClassVar[str] = "google_{domain}"

    default_{item}_name: str | None = Field(
        default=None,
        max_length=100,
        description="Nom de l'élément par défaut",
    )

    # Ajouter d'autres préférences si nécessaire
    notification_enabled: bool = Field(
        default=True,
        description="Activer les notifications",
    )
```

### 9.3 Enregistrer dans le Registry

**Fichier**: `src/domains/connectors/preferences/registry.py`

```python
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.preferences.schemas import (
    BaseConnectorPreferences,
    GoogleCalendarPreferences,
    GoogleTasksPreferences,
    Google{Domain}Preferences,  # AJOUTER
)

# Registry of connector types that support preferences
CONNECTOR_PREFERENCES_REGISTRY: dict[str, type[BaseConnectorPreferences]] = {
    ConnectorType.GOOGLE_CALENDAR.value: GoogleCalendarPreferences,
    ConnectorType.GOOGLE_TASKS.value: GoogleTasksPreferences,
    ConnectorType.GOOGLE_{DOMAIN}.value: Google{Domain}Preferences,  # AJOUTER
}


def get_preference_schema(connector_type: str) -> type[BaseConnectorPreferences] | None:
    """Get the preference schema class for a connector type."""
    return CONNECTOR_PREFERENCES_REGISTRY.get(connector_type)


def has_preferences(connector_type: str) -> bool:
    """Check if a connector type supports user preferences."""
    return connector_type in CONNECTOR_PREFERENCES_REGISTRY
```

### 9.4 Utiliser les Préférences dans un Tool

```python
# Dans execute_api_call() d'un tool

async def execute_api_call(self, client, user_id, **kwargs):
    from src.domains.connectors.preferences.service import ConnectorPreferencesService
    from src.domains.connectors.repository import ConnectorRepository

    # Récupérer le connecteur avec ses préférences
    repo = ConnectorRepository(client.connector_service.db)
    connector = await repo.get_by_user_and_type(user_id, ConnectorType.GOOGLE_{DOMAIN})

    # Lire une préférence spécifique
    default_item = None
    if connector and connector.preferences_encrypted:
        default_item = ConnectorPreferencesService.get_preference_value(
            "google_{domain}",
            connector.preferences_encrypted,
            "default_{item}_name",
        )

        if default_item:
            logger.debug(
                "{domain}_using_default_preference",
                default_item=default_item,
                user_id=str(user_id),
            )

    # Utiliser la préférence ou fallback
    item_to_use = kwargs.get("{item}_id") or default_item or "primary"

    # ... reste de la logique ...
```

### 9.5 Sécurité des Préférences

Le service applique automatiquement :

1. **Validation Pydantic** : Schéma strict avec `extra="forbid"`
2. **Sanitization** : Suppression des caractères dangereux (injection prompt)
   - Caractères supprimés: `\n`, `\r`, `\t`, `"`, `'`, `` ` ``, `\`, `{`, `}`
   - Longueur max: 100 caractères
3. **Encryption Fernet** : Même algorithme que les credentials OAuth

```python
# Caractères dangereux pour prompt injection
DANGEROUS_CHARS_PATTERN = re.compile(r'[\n\r\t"\'`\\{}]')
MAX_PREFERENCE_LENGTH = 100

# La sanitization est appliquée automatiquement par ConnectorPreferencesService
```

---

## 10. Checklist d'Intégration

### 10.1 Nouveau Connecteur (Client API)

- [ ] Créer `src/domains/connectors/clients/{service}_client.py`
- [ ] Hériter de `BaseGoogleClient` (OAuth) ou `BaseAPIKeyClient` (API Key)
- [ ] Définir `connector_type` et `api_base_url`
- [ ] Implémenter les méthodes API (search, get, create, etc.)
- [ ] Ajouter le `ConnectorType` dans `models.py`
- [ ] Exporter dans `clients/__init__.py`

### 10.2 Nouvel Agent

- [ ] Créer `src/domains/agents/graphs/{domain}_agent_builder.py`
- [ ] Définir le system prompt
- [ ] Lister tous les tools dans `tools: list[BaseTool]`
- [ ] Créer le `AgentManifest` dans `catalogue_loader.py`
- [ ] Enregistrer via `registry.register_agent_manifest()`

### 10.3 Nouveau Tool

- [ ] **Classe Tool**: Créer dans `{domain}_tools.py` héritant de `ConnectorTool`
- [ ] **Fonction Tool**: Décorer avec `@connector_tool`
- [ ] **Data Registry** (si applicable):
  - [ ] Ajouter `RegistryItemType` dans `data_registry/models.py`
  - [ ] Activer `registry_enabled = True`
  - [ ] Implémenter `format_registry_response()`
- [ ] **Manifeste Tool**: Créer `ToolManifest` dans `catalogue_manifests.py`
- [ ] **Enregistrer Manifeste**: Dans `catalogue_loader.py`:
  - [ ] Import du manifeste
  - [ ] `registry.register_tool_manifest()`
- [ ] **Enregistrer Executor**: Dans `parallel_executor.py`:
  - [ ] Ajouter à `OPTIONAL_PARAMS`
  - [ ] Import du tool
  - [ ] Ajouter à la liste `tools`
- [ ] **Agent Builder**: Ajouter le tool dans la liste `tools`
- [ ] **Agent Manifest**: Ajouter le nom du tool dans `tools[]`
- [ ] **Exports**: Ajouter dans `__all__` des fichiers concernés

---

## 11. Cas Particuliers et Subtilités

### 11.1 context_key dans ToolManifest

**ATTENTION**: Le `context_key` définit si les résultats du tool sont stockés dans le contexte conversationnel.

```python
# CAS 1: Tool avec contexte (pour références comme "$context.contacts.0")
context_key="contacts"  # DOIT être enregistré dans ContextTypeRegistry

# CAS 2: Tool sans contexte (données de référence seulement)
context_key=None  # Ou ne pas définir du tout
# Exemple: list_calendars_tool - les calendriers sont des références, pas du contexte
```

**Si vous définissez un context_key, il DOIT être enregistré:**
```python
# Dans src/domains/agents/context/manager.py
class ContextTypeRegistry:
    VALID_TYPES = {"contacts", "emails", "events", "tasks", ...}
```

**Erreur si context_key non enregistré:**
```
ValueError: Context type registration validation FAILED. '{key}' used by: {tool_name}
```

### 11.2 Tools avec HITL (Human-In-The-Loop)

Pour les opérations d'écriture nécessitant confirmation :

```python
# Dans le ToolManifest
permissions=PermissionProfile(
    hitl_required=True,  # Déclenche le flow d'approbation
    data_classification="SENSITIVE",
),

# Dans format_registry_response()
return StandardToolOutput(
    summary_for_llm="Draft créé: ...",
    registry_updates=registry_updates,
    requires_confirmation=True,  # Indique qu'une confirmation est requise
)
```

### 11.3 Tools avec Préférences Utilisateur

Pour utiliser les préférences du connecteur (ex: calendrier par défaut) :

```python
async def execute_api_call(self, client, user_id, **kwargs):
    from src.domains.connectors.preferences.service import ConnectorPreferencesService
    from src.domains.connectors.repository import ConnectorRepository

    # Récupérer les préférences
    repo = ConnectorRepository(client.connector_service.db)
    connector = await repo.get_by_user_and_type(user_id, ConnectorType.GOOGLE_CALENDAR)

    if connector and connector.preferences_encrypted:
        default_value = ConnectorPreferencesService.get_preference_value(
            "google_calendar",
            connector.preferences_encrypted,
            "default_calendar_name",
        )
```

### 11.4 Helpers ToolOutputMixin Non Disponible

Si votre domaine n'a pas de helper pré-construit dans `ToolOutputMixin`, utilisez la méthode générique :

```python
def format_registry_response(self, result: dict[str, Any]) -> StandardToolOutput:
    # Méthode générique avec create_registry_item()
    item_id, registry_item = self.create_registry_item(
        item_type=RegistryItemType.MY_CUSTOM_TYPE,
        unique_key=result["id"],
        payload=result,
        source="my_service",
        domain="my_domain",
    )

    return StandardToolOutput(
        summary_for_llm=f"[result] {result['name']}",
        registry_updates={item_id: registry_item},
    )
```

### 11.5 Rate Limiting Personnalisé

Le rate limiting est géré automatiquement par `BaseGoogleClient`, mais peut être personnalisé :

```python
class MyCustomClient(BaseGoogleClient):
    def __init__(self, user_id, credentials, connector_service):
        super().__init__(
            user_id,
            credentials,
            connector_service,
            rate_limit_per_second=5,  # Custom limit (default: 10)
        )
```

---

## 12. Système de Prompts Versionnés

Le système utilise des prompts versionnés avec chargement dynamique de few-shots pour optimiser la qualité des réponses et les coûts en tokens.

### 12.1 Architecture des Prompts

```
apps/api/src/domains/agents/prompts/
├── prompt_loader.py              # Chargeur avec cache LRU
├── v1/                           # Version courante des prompts
│   ├── router_system_prompt.txt
│   ├── router_system_prompt_template.txt
│   ├── planner_system_prompt.txt
│   ├── response_system_prompt_base.txt
│   ├── hitl_classifier_prompt.txt
│   ├── hitl_question_generator_prompt.txt
│   ├── {domain}_agent_prompt.txt     # Prompts par agent
│   └── fewshot/                      # Exemples few-shot par domaine
│       ├── contacts_search.txt
│       ├── contacts_details.txt
│       ├── emails_search.txt
│       ├── emails_details.txt
│       ├── calendar_search.txt
│       ├── calendar_details.txt
│       └── ...
└── prompt_loader.py              # Chargement unifié des prompts
```

> **Note**: Tous les prompts sont actuellement consolidés dans `v1/`. Le versioning se fait via les headers changelog dans chaque fichier.

### 12.2 Charger un Prompt Versionné

**Fichier**: `src/domains/agents/prompts/prompt_loader.py`

```python
from src.domains.agents.prompts.prompt_loader import load_prompt, load_fewshot_examples

# Charger un prompt avec cache LRU (maxsize=32)
prompt = load_prompt("router_system_prompt", version="v1")

# Charger avec validation d'intégrité (SHA256)
prompt = load_prompt(
    "router_system_prompt",
    version="v1",
    validate_hash=True,
    expected_hash="abc123..."
)

# Lister les prompts disponibles
from src.domains.agents.prompts.prompt_loader import (
    list_available_prompts,
    get_available_versions,
)
prompts = list_available_prompts("v1")  # ["router_system_prompt", "response_system_prompt_base", ...]
versions = get_available_versions()     # ["v1"]  # Dossier unique consolidé
```

**Caractéristiques:**
- Cache LRU (maxsize=32) pour réutilisation cross-requests
- Validation d'intégrité SHA256 optionnelle
- Dossier unique `v1/` avec versioning via changelog headers
- Fallback automatique si fichier manquant

### 12.3 Few-Shot Dynamique

Le système charge **uniquement** les exemples few-shot pertinents pour réduire la taille des prompts de ~80%.

**Fichier**: `src/domains/agents/prompts/prompt_loader.py`

```python
# Chargement dynamique basé sur les domaines détectés
from src.domains.agents.prompts.prompt_loader import load_fewshot_examples

# Requête mono-domaine: charge uniquement contacts
fewshot = load_fewshot_examples([("contacts", "search")])

# Requête multi-domaines: charge contacts + emails
fewshot = load_fewshot_examples([
    ("contacts", "search"),
    ("emails", "details"),
])

# Format retourné (injecté dans response_system_prompt_base.txt)
"""
================================================================================
EXEMPLES DE FORMATAGE (Few-Shot)
================================================================================

### Exemple: Liste de contacts
...

### Exemple: Details d'un email
...
"""
```

### 12.4 Structure d'un Fichier Few-Shot

**Fichier**: `src/domains/agents/prompts/v1/fewshot/contacts_search.txt`

```text
### Exemple: Liste de contacts

Donnees JSON structure:

```json
{{{{
  "domain": "contacts",
  "action": "search",
  "count": 2,
  "contacts": [
    {{{{
      "id": "contact_a1b2c3",
      "name": "Jean jean",
      "url": "https://contacts.google.com/person/c123",
      "emails": [{{{{"type": "Travail", "value": "jean@company.com"}}}}],
      "phones": [{{{{"type": "Mobile", "value": "+33 6 82 51 16 39"}}}}]
    }}}}
  ]
}}}}
```

TOUJOURS trier par ordre alphabetique croissant sur le name.
Formatage des donnees JSON:

?? **[Jean jean](https://contacts.google.com/person/c123)**

- ?? Email travail : jean@company.com
- ?? Tel mobile : 06.82.51.16.39
```

**Conventions:**
- `{{{{` et `}}}}` = accolades échappées pour double-templating
- `??` = placeholder emoji (remplacé par le LLM selon le contexte)
- Domaines supportés: `contacts`, `emails`, `calendar`, `tasks`, `drive`, `places`, `weather`, `wikipedia`, `perplexity`
- Actions: `search` (liste), `details` (item unique)

### 12.5 Ajouter un Few-Shot pour un Nouveau Domaine

**Étape 1**: Créer `prompts/v1/fewshot/{domain}_search.txt`

```text
### Exemple: Liste de {domain}

Donnees JSON structure:

```json
{{{{
  "domain": "{domain}",
  "action": "search",
  "count": 2,
  "{domain}s": [
    {{{{
      "id": "{domain}_a1b2c3",
      "name": "Item Name",
      "url": "https://...",
      ...champs spécifiques...
    }}}}
  ]
}}}}
```

Formatage des donnees JSON:

?? **[Item Name](https://...)**

- ?? Champ 1 : valeur
- ?? Champ 2 : valeur
```

**Étape 2**: Créer `prompts/v1/fewshot/{domain}_details.txt` (même structure, `action: "details"`)

**Étape 3**: Enregistrer dans `prompt_loader.py`

```python
# Dans DOMAIN_FILE_MAP
DOMAIN_FILE_MAP: dict[str, str] = {
    "contacts": "contacts",
    "emails": "emails",
    "{domain}": "{domain}",  # AJOUTER
}

# Dans OPERATION_FILE_MAP (généralement pas de changement)
OPERATION_FILE_MAP: dict[str, str] = {
    "search": "search",
    "list": "search",
    "details": "details",
}
```

### 12.6 Configuration des Versions

**Fichier**: `.env` ou `src/core/config/agents.py`

```bash
# Versions des prompts (défaut: v1)
ROUTER_PROMPT_VERSION=v1
RESPONSE_PROMPT_VERSION=v1
PLANNER_PROMPT_VERSION=v1
HITL_CLASSIFIER_PROMPT_VERSION=v1
```

**Usage dans le code:**
```python
from src.core.config import settings

# Les fonctions get_*_prompt() utilisent automatiquement la version configurée
prompt = get_response_prompt(user_timezone="Europe/Paris", user_language="fr")
```

---

## 13. Restitution à l'Utilisateur (Response Node)

Le `response_node` orchestre la génération de la réponse finale en combinant les résultats du Data Registry avec les exemples few-shot.

### 13.1 Flux de Restitution

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      RESPONSE NODE FLOW                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  1. Vérification conditions d'erreur                                    │
│     ↓                                                                    │
│     Check: plan_rejected, error_state, empty_results                    │
│     → Si erreur: réponse d'erreur directe                               │
│                                                                          │
│  2. Exécution Draft si confirmé (LOT 5.4)                               │
│     ↓                                                                    │
│     _execute_draft_if_confirmed(state, config)                          │
│     → Si draft CONFIRMED: execute_email_draft(), execute_event_draft()  │
│     → Ajoute résultat exécution à agent_results                         │
│                                                                          │
│  3. Détection domaines/opérations                                       │
│     ↓                                                                    │
│     _detect_domain_operations(agent_results, registry)                   │
│     → [("contacts", "search"), ("emails", "details")]                   │
│                                                                          │
│  4. Chargement few-shot dynamique                                        │
│     ↓                                                                    │
│     load_fewshot_examples(domain_operations)                            │
│     → Exemples pertinents uniquement (~80% tokens économisés)           │
│                                                                          │
│  5. Formatage des résultats en JSON                                     │
│     ↓                                                                    │
│     _format_registry_mode_results(agent_results, registry)              │
│     → Blocs ```json { "domain": "contacts", ... } ```                   │
│                                                                          │
│  6. Injection de contexte                                                │
│     ↓                                                                    │
│     Memory injection (psychological profile, long-term memory)          │
│     RAG Spaces injection (retrieve_rag_context → hybrid search)         │
│     Knowledge enrichment (domain-specific)                               │
│     → Contexte additionnel injecté dans le prompt                       │
│                                                                          │
│  7. Construction du prompt complet                                       │
│     ↓                                                                    │
│     get_response_prompt(timezone, language, domain_operations)          │
│     → System prompt + context + few-shots + agent_results               │
│                                                                          │
│  8. Génération LLM (streaming)                                          │
│     ↓                                                                    │
│     chain.ainvoke({messages, rejection_override, agent_results})        │
│     → Réponse Markdown formatée selon few-shots                         │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

**Notes**:
- L'étape 2 (Exécution Draft) n'est déclenchée que si un draft a été confirmé via HITL. Les types de drafts supportés sont : EMAIL, EVENT, EVENT_UPDATE, EVENT_DELETE, CONTACT, TASK, etc.
- L'étape 6 (Injection de contexte) inclut l'injection RAG Spaces : si l'utilisateur a des espaces actifs, `retrieve_rag_context()` effectue une recherche hybride (semantic + BM25) et injecte les chunks pertinents dans le prompt. Le coût d'embedding de la requête est tracké via `TrackedOpenAIEmbeddings`.

### 13.2 Formatage des Résultats du Registry

**Fichier**: `src/domains/agents/nodes/response_node.py`

Les résultats du Data Registry sont convertis en JSON structuré pour le LLM :

```python
def _format_registry_mode_results(
    agent_results: dict[str, Any],
    current_turn_id: int | None,
    data_registry: dict[str, Any],
) -> str:
    """
    Convertit les RegistryItem en JSON pour formatage LLM via few-shot.

    Input (Data Registry):
        {
            "contact_a1b2c3": RegistryItem(
                type=RegistryItemType.CONTACT,
                payload={"names": [{"displayName": "Jean"}], ...}
            )
        }

    Output (JSON pour LLM):
        ```json
        {
          "domain": "contacts",
          "action": "search",
          "count": 1,
          "contacts": [
            {"id": "contact_a1b2c3", "name": "Jean", ...}
          ]
        }
        ```
    """
```

### 13.3 Simplification des Payloads par Type

Chaque type a une fonction `_simplify_{type}_payload()` qui extrait les champs pertinents :

```python
# Contact: _simplify_contact_payload()
{
    "id": "contact_a1b2c3",
    "name": "Jean jean",
    "url": "https://contacts.google.com/person/c123",
    "emails": [{"type": "Travail", "value": "jean@company.com"}],
    "phones": [{"type": "Mobile", "value": "+33 6 12 34 56 78"}],
    "birthday": "10/08/1976",
    # Details only:
    "photos": ["https://..."],
    "organizations": [{"name": "Google", "title": "Engineer"}],
    "relations": [{"type": "Conjoint", "name": "Marie"}],
}

# Email: _simplify_email_payload()
{
    "id": "email_xyz",
    "url": "https://mail.google.com/mail/u/0/#inbox/...",
    "from": "sender@example.com",
    "subject": "Réunion demain",
    "date": "2025-01-15",
    "snippet": "Bonjour, voici...",
    # Details only:
    "body": "Contenu complet...",
    "attachments": [{"filename": "doc.pdf", ...}],
}

# Event: _simplify_event_payload()
# Task: _simplify_task_payload()
# File: _simplify_file_payload()
# Place: _simplify_place_payload()
# Weather: _simplify_weather_payload()
# etc.
```

### 13.4 Détection Search vs Details

Le système détecte automatiquement si c'est une recherche (liste) ou des détails (item unique) :

```python
def _detect_action_from_items(type_name: str, items: list[dict]) -> str:
    """
    Détecte "search" ou "details" basé sur:
    - Nombre d'items (1 item = potentiellement details)
    - Présence de champs riches (body pour email, attendees pour event, etc.)

    Indicateurs de détails par type:
    - CONTACT: relations, organizations, biographies, skills...
    - EMAIL: body, cc, attachments
    - EVENT: attendees, description, reminders, conferenceData
    - PLACE: opening_hours, website, phone, reviews
    - etc.
    """
```

### 13.5 Ajouter un Nouveau Type de Restitution

**Étape 1**: Ajouter la fonction de simplification dans `response_node.py`

```python
def _simplify_{domain}_payload(
    item_id: str, payload: dict[str, Any], action: str = "search"
) -> dict[str, Any]:
    """Simplify {domain} payload for few-shot JSON format."""
    result = {
        "id": item_id,
        "name": payload.get("name", "Sans nom"),
        "url": payload.get("webLink", ""),
        # ... champs communs search + details
    }

    if action == "details":
        # Champs supplémentaires pour les détails
        if payload.get("description"):
            result["description"] = payload["description"]
        # ...

    return result
```

**Étape 2**: Enregistrer dans le mapping type → domain

```python
# Dans _format_type_as_json()
type_to_domain = {
    "CONTACT": ("contacts", "contacts"),
    "EMAIL": ("emails", "emails"),
    "{NEW_TYPE}": ("{domain}", "{domain}s"),  # AJOUTER
}
```

**Étape 3**: Ajouter le routage dans `_simplify_payload_for_json()`

```python
def _simplify_payload_for_json(type_name, item_id, payload, action):
    if type_name == "CONTACT":
        return _simplify_contact_payload(item_id, payload, action)
    elif type_name == "{NEW_TYPE}":
        return _simplify_{domain}_payload(item_id, payload, action)  # AJOUTER
    # ...
```

**Étape 4**: Ajouter les indicateurs de détails

```python
# Dans _detect_action_from_items()
detail_indicators_by_type = {
    "CONTACT": ["relations", "organizations", ...],
    "{NEW_TYPE}": ["rich_field_1", "rich_field_2"],  # AJOUTER
}
```

### 13.6 Flux SSE vers le Frontend

Les `RegistryItem` sont envoyés au frontend via SSE **AVANT** la réponse LLM :

```
Timeline:
─────────────────────────────────────────────────────────────────────
     Tool Execution          Response Node           Frontend
─────────────────────────────────────────────────────────────────────
     │                        │                        │
     ├──registry_update──────►│                        │
     │  {id, type, payload}   ├───SSE event───────────►│
     │                        │  "registry_update"     │  Render rich
     │                        │                        │  component
     │                        │                        │
     │                        ├───LLM streaming───────►│
     │                        │  "Voici les 2 contacts"│  Display text
     │                        │                        │  with references
─────────────────────────────────────────────────────────────────────
```

**Frontend reçoit:**
```json
{
  "type": "registry_update",
  "data": {
    "contact_a1b2c3": {
      "id": "contact_a1b2c3",
      "type": "CONTACT",
      "payload": {...}
    }
  }
}
```

**LLM génère:**
```markdown
## 👤 Contacts trouvés (2)

👤 **[Jean jean](https://contacts.google.com/person/c123)**
- ✉️ Email travail : jean@company.com
- 📞 Tel mobile : 06.12.34.56.78
```

---

## 14. Exemples Complets

### 14.1 Exemple: list_calendars_tool (Tool de Lecture Simple)

Cet exemple montre l'ajout complet d'un tool de lecture sans contexte conversationnel.

**Particularités:**
- `context_key=None` (les calendriers sont des références, pas du contexte)
- `hitl_required=False` (lecture seule)
- Nouveau `RegistryItemType.CALENDAR`

<details>
<summary>Voir le code complet</summary>

**1. Data Registry Type** (`data_registry/models.py`):
```python
class RegistryItemType(str, Enum):
    CALENDAR = "CALENDAR"  # Ajouté
```

**2. Tool Class & Function** (`calendar_tools.py`):
```python
class ListCalendarsTool(ToolOutputMixin, ConnectorTool[GoogleCalendarClient]):
    connector_type = ConnectorType.GOOGLE_CALENDAR
    client_class = GoogleCalendarClient
    registry_enabled = True

    def __init__(self) -> None:
        super().__init__(tool_name="list_calendars_tool", operation="list")

    async def execute_api_call(self, client, user_id, **kwargs):
        result = await client.list_calendars(
            max_results=kwargs.get("max_results", 100),
            show_hidden=kwargs.get("show_hidden", False),
        )
        return {"calendars": result.get("items", []), "total": len(result.get("items", []))}

    def format_registry_response(self, result):
        # ... création des RegistryItem avec type=CALENDAR
        return StandardToolOutput(...)

@connector_tool(name="list_calendars", agent_name=AGENT_CALENDAR, ...)
async def list_calendars_tool(show_hidden=False, max_results=100, runtime=None):
    return await _list_calendars_tool_instance.execute(runtime=runtime, ...)
```

**3. Manifeste** (`calendar/catalogue_manifests.py`):
```python
list_calendars_catalogue_manifest = ToolManifest(
    name="list_calendars_tool",
    agent="calendar_agent",
    # ... parameters, outputs, cost, permissions
    context_key=None,  # PAS de contexte - données de référence
)
```

**4. Enregistrements**:
- `catalogue_loader.py`: Import + `register_tool_manifest()`
- `parallel_executor.py`: Import + ajout à `OPTIONAL_PARAMS` + ajout à `tools`
- `calendar_agent_builder.py`: Ajout dans la liste `tools`
- `CALENDAR_AGENT_MANIFEST.tools`: Ajout du nom

</details>

### 14.2 Exemple: create_event_tool (Tool d'Écriture avec HITL)

<details>
<summary>Voir les particularités HITL</summary>

```python
# Dans le manifeste
permissions=PermissionProfile(
    hitl_required=True,
    data_classification="CONFIDENTIAL",
),

# Dans format_registry_response()
return StandardToolOutput(
    summary_for_llm="Draft créé pour: Réunion projet",
    registry_updates={
        draft_id: RegistryItem(
            type=RegistryItemType.DRAFT,
            payload=draft_data,
            ...
        )
    },
    requires_confirmation=True,
)
```

</details>

---

## 15. Injection de Dépendances (ToolDependencies)

Le système utilise un container d'injection pour partager les ressources entre tools durant une exécution.

### 15.1 Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      TOOL DEPENDENCIES FLOW                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Request arrives                                                         │
│       ↓                                                                  │
│  async with get_db_context() as db:                                     │
│       ↓                                                                  │
│  deps = ToolDependencies(db_session=db)                                 │
│       ↓                                                                  │
│  config = {"configurable": {"__deps": deps, "user_id": ...}}           │
│       ↓                                                                  │
│  agent.ainvoke(state, config)                                           │
│       ↓                                                                  │
│  Tool.execute() → get_dependencies(runtime) → deps                      │
│       ↓                                                                  │
│  deps.get_connector_service() → ConcurrencySafeConnectorService         │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 15.2 ToolDependencies Container

**Fichier**: `src/domains/agents/dependencies.py`

```python
class ToolDependencies:
    """
    Container pour ressources partagées dans une exécution de graph.

    Features:
    - Lazy initialization des services
    - Cache des clients API (évite re-création)
    - Thread-safe via asyncio.Lock
    """

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session
        self._connector_service: ConnectorService | None = None
        self._pricing_service: PricingService | None = None
        self._client_cache: dict[str, Any] = {}
        self._lock = asyncio.Lock()

    async def get_connector_service(self) -> ConcurrencySafeConnectorService:
        """Get or create connector service (thread-safe)."""
        if self._connector_service is None:
            self._connector_service = ConnectorService(self.db_session)
        return ConcurrencySafeConnectorService(self._connector_service)

    async def get_or_create_client(
        self,
        client_class: type[T],
        cache_key: str,
        factory: Callable[[], Awaitable[T]],
    ) -> T:
        """
        Get cached client or create new one.

        Évite de re-créer le même client Google/API multiple fois
        dans une même exécution (ex: search + details).
        """
        async with self._lock:
            if cache_key not in self._client_cache:
                self._client_cache[cache_key] = await factory()
            return self._client_cache[cache_key]
```

### 15.3 ConcurrencySafeConnectorService

Wrapper qui utilise `asyncio.Lock` pour prévenir les race conditions SQLAlchemy lors d'exécutions parallèles :

```python
class ConcurrencySafeConnectorService:
    """
    Thread-safe wrapper pour ConnectorService.

    Nécessaire car parallel_executor exécute plusieurs tools
    en asyncio.gather() qui peuvent accéder au même connector.
    """

    def __init__(self, service: ConnectorService) -> None:
        self._service = service
        self._lock = asyncio.Lock()

    async def get_oauth_credentials(self, user_id: UUID, connector_type: ConnectorType):
        async with self._lock:
            return await self._service.get_oauth_credentials(user_id, connector_type)

    async def refresh_token_if_needed(self, connector_id: int, credentials: dict):
        async with self._lock:
            return await self._service.refresh_token_if_needed(connector_id, credentials)
```

### 15.4 Utilisation dans un Tool

```python
from src.domains.agents.dependencies import get_dependencies

class MyTool(ConnectorTool[MyAPIClient]):
    async def execute(
        self,
        runtime: Annotated[ToolRuntime, InjectedToolArg],
        **kwargs,
    ) -> str:
        # Récupérer les dépendances depuis runtime
        deps = get_dependencies(runtime)

        # Service thread-safe
        connector_service = await deps.get_connector_service()

        # Client caché (réutilisé si déjà créé)
        client = await deps.get_or_create_client(
            MyAPIClient,
            cache_key=f"my_client_{user_id}",
            factory=lambda: MyAPIClient(credentials),
        )

        return await client.do_something()
```

### 15.5 Injection dans le Graph

```python
# Dans AgentService ou équivalent
async def run_agent(self, user_id: UUID, message: str):
    async with get_db_context() as db:
        # Créer container de dépendances
        deps = ToolDependencies(db_session=db)

        # Injecter dans config LangGraph
        config: RunnableConfig = {
            "configurable": {
                "user_id": str(user_id),
                "session_id": str(session_id),
                "__deps": deps,  # Clé spéciale pour injection
            },
            "callbacks": [metrics_handler],
        }

        # Exécuter graph
        result = await self.agent.ainvoke(state, config)
```

---

## 16. Gestion du Contexte (ToolContextManager)

Le `ToolContextManager` gère la persistence des résultats de recherche et détails dans le LangGraph BaseStore.

### 16.1 Architecture Multi-Keys Store

**Pattern**: Namespace hiérarchique avec 3 clés par domaine

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    LANGGRAPH BASESTORE NAMESPACE                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Namespace: (user_id, session_id, "context", domain)                    │
│                                                                          │
│  Keys per domain:                                                        │
│  ├── "list"    → ToolContextList (search results, OVERWRITE behavior)  │
│  ├── "details" → ToolContextDetails (item details, MERGE LRU, max 10)  │
│  └── "current" → ToolContextCurrentItem (single focused item)          │
│                                                                          │
│  Example for contacts:                                                   │
│  (user123, session456, "context", "contacts")                           │
│  ├── "list"    → {items: [{name: "Jean"}, {name: "Marie"}], meta: ...} │
│  ├── "details" → {items: [{name: "Jean", full_details: ...}], meta: ...}│
│  └── "current" → {item: {name: "Jean", ...}, meta: ...}                │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 16.2 Classification Automatique (Save Mode)

**Fichier**: `src/domains/agents/context/manager.py`

```python
def classify_save_mode(
    tool_name: str,
    item_count: int,
    explicit_mode: str | None = None,
) -> Literal["list", "details"]:
    """
    Détermine automatiquement le mode de sauvegarde.

    Priorité:
    1. Mode explicite du manifest
    2. Patterns dans le nom du tool
    3. Nombre d'items
    """
    if explicit_mode:
        return explicit_mode

    # Patterns pour LIST
    list_patterns = ["search", "list", "find", "query"]
    if any(p in tool_name.lower() for p in list_patterns):
        return "list"

    # Patterns pour DETAILS
    detail_patterns = ["get", "show", "detail", "fetch"]
    if any(p in tool_name.lower() for p in detail_patterns):
        return "details"

    # Heuristique par count
    return "list" if item_count > 10 else "details"
```

### 16.3 Sauvegarde de Liste (Overwrite)

```python
await manager.save_list(
    user_id=user_id,
    session_id=session_id,
    domain="contacts",
    items=[
        {"resourceName": "people/c123", "displayName": "Jean"},
        {"resourceName": "people/c456", "displayName": "Marie"},
    ],
    metadata={
        FIELD_TURN_ID: turn_id,
        FIELD_QUERY: "recherche jean",
        FIELD_TIMESTAMP: datetime.now(UTC).isoformat(),
    },
    store=store,
)
# Comportement:
# - Remplace complètement la liste précédente
# - Auto-enrichit items avec "index" (1-based)
# - Si 1 item → auto-set current_item
# - Si >1 items → clear current_item
```

### 16.4 Sauvegarde de Détails (Merge LRU)

```python
await manager.save_details(
    user_id=user_id,
    session_id=session_id,
    domain="contacts",
    items=[{"resourceName": "people/c123", "full_data": {...}}],
    metadata={...},
    max_items=10,  # Éviction LRU si dépassé
    store=store,
)
# Comportement:
# - Merge avec détails existants
# - Déduplique par primary_id_field (resourceName pour contacts)
# - Évince items les plus anciens si > max_items
```

### 16.5 Décorateur @auto_save_context

**Fichier**: `src/domains/agents/context/decorators.py`

```python
from src.domains.agents.context.decorators import auto_save_context

@tool
@auto_save_context(domain="contacts")
async def search_contacts_tool(
    runtime: Annotated[ToolRuntime, InjectedToolArg],
    query: str,
) -> str:
    """
    Le décorateur intercepte le retour et sauvegarde automatiquement
    dans le context store.
    """
    result = await search_contacts(query)
    return json.dumps({"success": True, "contacts": result})
```

**Fonctionnement:**
1. Intercepte le retour du tool
2. Détecte le mode (registry ou legacy JSON)
3. Extrait les items à sauvegarder
4. Appelle `manager.auto_save()` avec classification automatique
5. **Fail-safe**: Erreurs de sauvegarde n'affectent jamais le tool

```python
def auto_save_context(domain: str):
    """
    Décorateur pour persistence automatique des résultats.

    Supporte deux modes:
    - Legacy: Parse JSON, extrait items
    - Registry: Extrait de StandardToolOutput.registry_updates
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)

            try:
                # Mode Registry (nouveau)
                if isinstance(result, StandardToolOutput):
                    items = _extract_items_from_registry(result.registry_updates)
                # Mode Legacy (JSON string)
                else:
                    items = _extract_items_from_json(result)

                if items:
                    await manager.auto_save(
                        user_id, session_id, domain,
                        items=items,
                        tool_name=func.__name__,
                        store=store,
                    )
            except Exception as e:
                # FAIL-SAFE: Ne jamais bloquer le tool
                logger.warning("auto_save_context_failed", error=str(e))

            return result
        return wrapper
    return decorator
```

### 16.6 Récupération du Contexte

```python
# Current item (pour références $context.contacts.current)
current = await manager.get_current_item(
    user_id, session_id, "contacts", store
)

# Liste complète (pour références $context.contacts.0)
context_list = await manager.get_list(
    user_id, session_id, "contacts", store
)

# Détails (pour enrichissement)
details = await manager.get_details(
    user_id, session_id, "contacts", store
)
```

### 16.7 Truncation Intelligente

Pour éviter de dépasser les limites de tokens, le manager tronque intelligemment :

```python
def _truncate_items(
    items: list[dict],
    max_items: int = 50,
) -> list[dict]:
    """
    Truncation intelligente:
    - 70% items récents
    - 30% items haute confiance (si score disponible)
    - Préserve l'ordre original
    """
    if len(items) <= max_items:
        return items

    recent_count = int(max_items * 0.7)
    high_conf_count = max_items - recent_count

    recent = items[:recent_count]
    remaining = items[recent_count:]

    # Trier par confiance si disponible
    if remaining and "confidence" in remaining[0]:
        remaining.sort(key=lambda x: x.get("confidence", 0), reverse=True)

    high_conf = remaining[:high_conf_count]

    logger.warning(
        "context_truncated",
        original_count=len(items),
        truncated_count=max_items,
    )

    return recent + high_conf
```

---

## 17. HITL (Human-In-The-Loop) Complet

Le système HITL v2 permet d'interrompre l'exécution pour demander confirmation à l'utilisateur.

### 17.1 Niveaux d'Interruption

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      HITL INTERRUPTION LEVELS                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  LEVEL 1: Plan Approval (approval_gate_node.py)                         │
│  ─────────────────────────────────────────────────────────────────────  │
│  Quand: Plan généré avec opérations sensibles                           │
│  Question: "Je vais rechercher X et envoyer Y. Confirmes-tu ?"          │
│  Actions: APPROVE / REJECT / EDIT                                       │
│                                                                          │
│  LEVEL 2: Tool Confirmation (parallel_executor.py)                      │
│  ─────────────────────────────────────────────────────────────────────  │
│  Quand: Tool individuel requires_confirmation=True                      │
│  Trigger: parallel_executor détecte requires_confirmation sur le tool   │
│           → Crée Draft avec status PENDING                              │
│           → GraphInterrupt pour confirmation                            │
│  Question: "Supprimer le contact Jean Dupont ?"                         │
│  Actions: CONFIRM / CANCEL                                              │
│                                                                          │
│  LEVEL 3: Draft Critique (hitl_dispatch_node.py → DRAFT_CRITIQUE)       │
│  ─────────────────────────────────────────────────────────────────────  │
│  Quand: Draft genere (email, evenement)                                 │
│  Trigger: parallel_executor detecte output.draft sur tool result        │
│           → Cree HitlInteraction(type=DRAFT_CRITIQUE)                   │
│           → Route vers hitl_dispatch_node                               │
│  Question: "Voici le brouillon. Modifications ?"                        │
│  Actions: SEND / EDIT / CANCEL                                          │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 17.2 Flow Plan Approval

```python
# 1. Planner génère ExecutionPlan
plan = await planner_node(state)

# 2. Validator détecte requires_hitl
validation = await validate_plan(plan)
if validation.requires_hitl:

    # 3. Approval Gate génère question (streaming)
    question = await question_generator.generate_plan_approval_question(
        plan_summary=plan.to_summary(),
        approval_reasons=validation.hitl_reasons,
    )

    # 4. Interrupt LangGraph (pause execution)
    raise GraphInterrupt(
        interrupt_type="plan_approval",
        question=question,
        context={"plan": plan, "reasons": validation.hitl_reasons},
    )

# 5. User répond (via API resume)
# 6. Resumption strategy appliquée
decision = classify_user_response(user_message)  # APPROVE/REJECT/EDIT

if decision == "APPROVE":
    # Continue execution
    return await task_orchestrator(state)
elif decision == "REJECT":
    # Skip execution, return rejection message
    return {"response": "Plan annulé comme demandé."}
elif decision == "EDIT":
    # Modify plan, re-validate, loop back
    edited_plan = await plan_editor.apply_edits(plan, user_edits)
    return await approval_gate(state_with_edited_plan)
```

### 17.3 Draft System

**Fichier**: `src/domains/agents/drafts/models.py`

```python
class DraftType(str, Enum):
    """Types de drafts supportés."""
    EMAIL = "EMAIL"
    EVENT = "EVENT"
    EVENT_UPDATE = "EVENT_UPDATE"
    EVENT_DELETE = "EVENT_DELETE"
    CONTACT = "CONTACT"
    CONTACT_UPDATE = "CONTACT_UPDATE"
    CONTACT_DELETE = "CONTACT_DELETE"
    TASK = "TASK"
    TASK_UPDATE = "TASK_UPDATE"
    TASK_DELETE = "TASK_DELETE"
    FILE_DELETE = "FILE_DELETE"

class DraftStatus(str, Enum):
    """Lifecycle status."""
    PENDING = "PENDING"        # Awaiting user decision
    MODIFIED = "MODIFIED"      # User edited, back to pending
    CONFIRMED = "CONFIRMED"    # User approved
    CANCELLED = "CANCELLED"    # User rejected
    EXECUTED = "EXECUTED"      # Successfully executed
    FAILED = "FAILED"          # Execution failed

class Draft(BaseModel):
    """Draft awaiting user confirmation."""
    id: str
    type: DraftType
    status: DraftStatus
    payload: dict[str, Any]  # Domain-specific data
    created_at: datetime
    updated_at: datetime
    execution_result: dict | None = None
```

### 17.4 Interactions HITL

**Fichier**: `src/domains/agents/services/hitl/interactions/`

```python
# Plan Approval
class PlanApprovalInteraction(HITLInteraction):
    async def generate_question_stream(self, context: dict) -> AsyncGenerator[str, None]:
        """Stream question tokens via LLM."""
        async for token in llm.astream(prompt):
            yield token

    async def process_response(self, response: str) -> HITLDecision:
        """Classify user response."""
        return await classifier.classify(response)

# Clarification (demande d'infos manquantes)
class ClarificationInteraction(HITLInteraction):
    async def generate_question_stream(self, context: dict) -> AsyncGenerator[str, None]:
        """Ex: 'Quel calendrier utiliser pour l'événement ?'"""
        ...

# Draft Critique
class DraftCritiqueInteraction(HITLInteraction):
    async def generate_question_stream(self, context: dict) -> AsyncGenerator[str, None]:
        """Ex: 'Voici le brouillon d'email. Envoyer tel quel ?'"""
        ...

# Tool Confirmation
class ToolConfirmationInteraction(HITLInteraction):
    async def generate_question_stream(self, context: dict) -> AsyncGenerator[str, None]:
        """Ex: 'Confirmer la suppression du contact X ?'"""
        ...
```

### 17.5 Classification des Réponses

**Fichier**: `src/domains/agents/services/hitl_classifier.py`

```python
class HITLClassifier:
    """Classifie la réponse utilisateur en décision."""

    async def classify(
        self,
        action_desc: str,
        user_response: str,
    ) -> HITLDecision:
        """
        Utilise LLM pour classifier réponse naturelle.

        Input: "non recherche paul"
        Output: HITLDecision(
            action=EDIT,
            confidence=0.95,
            new_params={"query": "paul"}
        )
        """
        prompt = get_hitl_classifier_prompt(action_desc, user_response)
        result = await llm.ainvoke(prompt)
        return HITLDecision.parse(result)

class HITLDecision(BaseModel):
    action: Literal["APPROVE", "REJECT", "EDIT", "CLARIFY"]
    confidence: float
    new_params: dict | None = None  # Pour EDIT
    clarification: str | None = None  # Pour CLARIFY
```

### 17.6 Resumption Strategies

**Fichier**: `src/domains/agents/services/hitl/resumption_strategies.py`

```python
class ResumptionStrategy(ABC):
    """Stratégie de reprise après interruption HITL."""

    @abstractmethod
    async def apply(
        self,
        state: MessagesState,
        decision: HITLDecision,
    ) -> MessagesState:
        """Applique la décision et retourne nouvel état."""

class ApproveStrategy(ResumptionStrategy):
    async def apply(self, state, decision):
        """Continue execution normale."""
        state.metadata["plan_approved"] = True
        return state

class RejectStrategy(ResumptionStrategy):
    async def apply(self, state, decision):
        """Skip execution, prépare message rejet."""
        state.metadata["plan_rejected"] = True
        state.metadata["rejection_reason"] = decision.clarification
        return state

class EditStrategy(ResumptionStrategy):
    async def apply(self, state, decision):
        """Modifie le plan avec nouveaux paramètres."""
        plan = state.metadata["execution_plan"]
        edited_plan = await plan_editor.apply_edits(plan, decision.new_params)
        state.metadata["execution_plan"] = edited_plan
        state.metadata["requires_revalidation"] = True
        return state
```

---

## 18. Streaming SSE et Callbacks

### 18.1 Types d'Événements SSE

**Fichier**: `src/domains/agents/api/schemas.py`

```python
# Types SSE validés (20 types au total)
VALID_SSE_TYPES = [
    # ═══════════════════════════════════════════════════════════════════
    # CORE EVENTS
    # ═══════════════════════════════════════════════════════════════════
    "token",                      # Token de réponse LLM
    "content_replacement",        # Remplacement contenu (édition)
    "router_decision",            # Décision du router (domaine sélectionné)
    "execution_step",             # Progression step du plan
    "registry_update",            # Data Registry items (avant LLM)
    "planner_metadata",           # Métadonnées du plan généré
    "planner_error",              # Erreur du planner
    "error",                      # Erreur générale
    "done",                       # Fin de réponse

    # ═══════════════════════════════════════════════════════════════════
    # HITL EVENTS (Human-In-The-Loop)
    # ═══════════════════════════════════════════════════════════════════
    "hitl_interrupt",             # Interruption HITL (legacy)
    "hitl_interrupt_metadata",    # Métadonnées interruption
    "hitl_question_token",        # Token streaming question HITL
    "hitl_interrupt_complete",    # Fin interruption HITL
    "hitl_streaming_fallback",    # Fallback si streaming LLM échoue
    "hitl_question",              # Question HITL complète (legacy)

    # ═══════════════════════════════════════════════════════════════════
    # HITL CLARIFICATION EVENTS
    # ═══════════════════════════════════════════════════════════════════
    "hitl_clarification_token",   # Token question clarification
    "hitl_clarification_complete", # Fin clarification

    # ═══════════════════════════════════════════════════════════════════
    # HITL REJECTION EVENTS
    # ═══════════════════════════════════════════════════════════════════
    "hitl_rejection",             # Plan rejeté par utilisateur
    "hitl_rejection_token",       # Token réponse rejet
    "hitl_rejection_complete",    # Fin rejet
]
```

**Catégorisation:**

| Catégorie | Events | Usage |
|-----------|--------|-------|
| **Core** | token, done, error | Streaming LLM de base |
| **Routing** | router_decision, execution_step | Progression du plan |
| **Registry** | registry_update | Envoi données avant LLM |
| **Planner** | planner_metadata, planner_error | Métadonnées/erreurs plan |
| **HITL Base** | hitl_interrupt, hitl_interrupt_metadata, hitl_interrupt_complete | Interruption générique |
| **HITL Question** | hitl_question_token, hitl_question, hitl_streaming_fallback | Question streaming |
| **HITL Clarification** | hitl_clarification_token, hitl_clarification_complete | Demande d'infos |
| **HITL Rejection** | hitl_rejection, hitl_rejection_token, hitl_rejection_complete | Rejet plan |

### 18.2 Structure des Chunks

```python
class ChatStreamChunk(BaseModel):
    """Chunk SSE envoyé au frontend."""

    type: SSEEventType
    content: str | None = None  # Pour CHUNK, DONE
    registry_updates: dict[str, RegistryItem] | None = None  # Pour REGISTRY_UPDATE
    question: str | None = None  # Pour HITL_INTERRUPT
    context: dict | None = None  # Données additionnelles
    metadata: TokenSummaryDTO | None = None  # Pour DONE

# Exemples:
# Token streaming
ChatStreamChunk(type="chunk", content="Voici")

# Registry update (avant LLM)
ChatStreamChunk(
    type="registry_update",
    registry_updates={
        "contact_abc": RegistryItem(type="CONTACT", payload={...})
    }
)

# HITL interrupt
ChatStreamChunk(
    type="hitl_interrupt",
    question="Confirmer l'envoi de l'email ?",
    context={"draft_id": "draft_123", "type": "EMAIL"}
)

# Done avec métriques
ChatStreamChunk(
    type="done",
    content="Voici les 3 contacts trouvés.",
    metadata=TokenSummaryDTO(
        input_tokens=150,
        output_tokens=89,
        total_cost=0.0023,
        latency_ms=1234,
    )
)
```

### 18.3 StreamingService

**Fichier**: `src/domains/agents/services/streaming/service.py`

```python
class StreamingService:
    """Orchestre le streaming SSE vers le frontend."""

    async def stream_agent_response(
        self,
        user_id: UUID,
        conversation_id: UUID,
        message: str,
        config: RunnableConfig,
    ) -> AsyncGenerator[ChatStreamChunk, None]:
        """
        Stream complet avec gestion HITL et registry.
        """
        try:
            async for event in self.agent.astream_events(state, config):

                # Token LLM
                if event["event"] == "on_chat_model_stream":
                    yield ChatStreamChunk(
                        type="chunk",
                        content=event["data"]["chunk"].content,
                    )

                # Registry update
                elif event["event"] == "on_tool_end":
                    if registry_updates := self._extract_registry(event):
                        yield ChatStreamChunk(
                            type="registry_update",
                            registry_updates=registry_updates,
                        )

                # HITL interrupt
                elif event["event"] == "on_interrupt":
                    yield ChatStreamChunk(
                        type="hitl_interrupt",
                        question=event["data"]["question"],
                        context=event["data"]["context"],
                    )

            # Final
            yield ChatStreamChunk(
                type="done",
                content=final_response,
                metadata=self._build_token_summary(),
            )

        except Exception as e:
            yield ChatStreamChunk(
                type="error",
                content=str(e),
            )
```

### 18.4 Callbacks LangChain pour Métriques

**Fichier**: `src/infrastructure/observability/callbacks.py`

```python
class MetricsCallbackHandler(AsyncCallbackHandler):
    """Collecte métriques durant exécution LLM."""

    def __init__(self):
        self.start_times: dict[UUID, float] = {}
        self.token_usage: dict[str, int] = {
            "input": 0,
            "output": 0,
        }
        self.costs: float = 0.0

    async def on_llm_start(
        self,
        serialized: dict,
        prompts: list[str],
        *,
        run_id: UUID,
        **kwargs,
    ):
        """Enregistre début appel LLM."""
        self.start_times[run_id] = time.time()

    async def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        **kwargs,
    ):
        """Extrait métriques de la réponse."""
        latency = time.time() - self.start_times.pop(run_id, time.time())

        # Extraire tokens (provider-agnostic)
        usage = TokenExtractor.extract(response, self.llm_name)
        self.token_usage["input"] += usage.input_tokens
        self.token_usage["output"] += usage.output_tokens

        # Calculer coût
        self.costs += self.pricing_service.calculate_cost(
            model=self.model_name,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
        )

        # Prometheus metrics
        llm_tokens_total.labels(type="input").inc(usage.input_tokens)
        llm_tokens_total.labels(type="output").inc(usage.output_tokens)
        llm_latency_histogram.observe(latency)

    async def on_tool_error(self, error: Exception, *, run_id: UUID, **kwargs):
        """Log erreur tool."""
        tools_errors_total.labels(tool=self.current_tool).inc()
```

### 18.5 Injection des Callbacks

```python
# Dans la configuration du graph
config: RunnableConfig = {
    "configurable": {...},
    "callbacks": [
        MetricsCallbackHandler(
            llm_name="gpt-4",
            pricing_service=pricing_service,
        ),
        LangfuseCallbackHandler(
            trace_name=f"agent_{user_id}",
            user_id=str(user_id),
        ),
    ],
}

# Enrichissement par node
def enrich_config_with_node_metadata(config: RunnableConfig, node_name: str):
    """Ajoute metadata du node aux callbacks."""
    for callback in config.get("callbacks", []):
        if hasattr(callback, "set_node_name"):
            callback.set_node_name(node_name)
    return config
```

---

## 19. Validation des Plans

Le système valide les plans générés par le Planner avant exécution.

### 19.1 Pipeline de Validation

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      VALIDATION PIPELINE                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ExecutionPlan (from Planner)                                           │
│       ↓                                                                  │
│  1. Schema Validation (plan_validator.py)                               │
│     - Structure ExecutionPlan correcte                                  │
│     - Types des champs                                                  │
│       ↓                                                                  │
│  2. Reference Validation (reference_validator.py)                       │
│     - $steps.X.field existe                                             │
│     - Pas de références circulaires                                     │
│       ↓                                                                  │
│  3. Tool Validation (plan_validator.py)                                 │
│     - Tools existent dans le catalogue                                  │
│     - Paramètres requis présents                                        │
│       ↓                                                                  │
│  4. Semantic Validation (semantic_validator_node.py) [CONDITIONNEL]     │
│     - Activé via: settings.semantic_validation_enabled = True           │
│     - LLM distinct vérifie cohérence                                    │
│     - Détecte hallucinations, scope issues                              │
│     - 3 routes possibles:                                               │
│       → clarification_node (si infos manquantes)                        │
│       → planner_node (si auto-replan nécessaire)                        │
│       → approval_gate_node (si validation OK)                           │
│       ↓                                                                  │
│  PlanValidationResult                                                   │
│  ├── is_valid: bool                                                     │
│  ├── errors: list[ValidationError]                                      │
│  ├── requires_hitl: bool                                                │
│  └── issues: list[SemanticIssue]                                        │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

**Configuration Feature Flag:**
```python
# .env ou src/core/config/agents.py
SEMANTIC_VALIDATION_ENABLED=true  # Active la validation sémantique

# Dans le code (routing.py)
if settings.semantic_validation_enabled:
    # Route: planner → semantic_validator → (3 routes) → approval_gate
else:
    # Route: planner → approval_gate (directement, sans validation sémantique)
```

### 19.2 Validation Sémantique

**Fichier**: `src/domains/agents/orchestration/semantic_validator.py`

```python
class SemanticIssueType(str, Enum):
    """Types d'issues sémantiques détectées."""

    HALLUCINATED_CAPABILITY = "HALLUCINATED_CAPABILITY"
    # Plan utilise un tool qui n'existe pas

    GHOST_DEPENDENCY = "GHOST_DEPENDENCY"
    # Référence à un step output qui n'existera pas

    LOGICAL_CYCLE = "LOGICAL_CYCLE"
    # Dépendances circulaires entre steps

    CARDINALITY_MISMATCH = "CARDINALITY_MISMATCH"
    # "Pour chaque contact" mais opération unique

    SCOPE_OVERFLOW = "SCOPE_OVERFLOW"
    # Plan fait plus que demandé

    SCOPE_UNDERFLOW = "SCOPE_UNDERFLOW"
    # Plan fait moins que demandé

class SemanticValidator:
    """
    Validation sémantique par LLM distinct.

    Utilise un LLM différent du planner pour éviter
    le biais d'auto-validation.
    """

    async def validate(
        self,
        plan: ExecutionPlan,
        user_query: str,
        available_tools: list[ToolManifest],
    ) -> SemanticValidationResult:
        """
        Valide la cohérence sémantique du plan.

        Timeout: 1s (optimistic, ne bloque pas TTFT)
        """
        prompt = self._build_validation_prompt(plan, user_query, available_tools)

        try:
            result = await asyncio.wait_for(
                self.llm.ainvoke(prompt),
                timeout=1.0,
            )
            return SemanticValidationResult.parse(result)
        except asyncio.TimeoutError:
            # Fail-open: assume valid si timeout
            return SemanticValidationResult(is_valid=True, issues=[])
```

### 19.3 Validation des Références

**Fichier**: `src/domains/agents/orchestration/reference_validator.py`

```python
class ReferenceValidator:
    """Valide les expressions de référence dans le plan."""

    REFERENCE_PATTERN = re.compile(r'\$steps\.(\w+)\.(.+)')

    def validate_references(
        self,
        plan: ExecutionPlan,
    ) -> list[ValidationError]:
        """
        Vérifie que toutes les références $steps.X.field sont valides.
        """
        errors = []
        step_outputs = self._collect_step_outputs(plan)

        for step in plan.steps:
            for param_value in step.params.values():
                if refs := self._extract_references(param_value):
                    for ref in refs:
                        if not self._reference_exists(ref, step_outputs, step.id):
                            errors.append(ValidationError(
                                type="GHOST_DEPENDENCY",
                                message=f"Reference {ref} does not exist",
                                step_id=step.id,
                            ))

        return errors

    def _reference_exists(
        self,
        ref: str,
        step_outputs: dict[str, set[str]],
        current_step_id: str,
    ) -> bool:
        """Vérifie qu'une référence pointe vers un output existant."""
        match = self.REFERENCE_PATTERN.match(ref)
        if not match:
            return False

        step_id, field_path = match.groups()

        # Le step référencé doit exister
        if step_id not in step_outputs:
            return False

        # Le step référencé doit être exécuté AVANT current_step
        # (vérifié via dependency graph)

        return True
```

---

## 20. Métriques et Observabilité

### 20.1 Métriques Prometheus

**Fichier**: `src/infrastructure/observability/metrics_agents.py`

```python
# ═══════════════════════════════════════════════════════════════════════
# TOOL METRICS
# ═══════════════════════════════════════════════════════════════════════

tools_execution_total = Counter(
    "tools_execution_total",
    "Total tool executions",
    ["tool_name", "status"],  # status: success, error
)

tools_latency_seconds = Histogram(
    "tools_latency_seconds",
    "Tool execution latency",
    ["tool_name"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# ═══════════════════════════════════════════════════════════════════════
# PLANNER METRICS
# ═══════════════════════════════════════════════════════════════════════

planner_plans_created_total = Counter(
    "planner_plans_created_total",
    "Total plans created",
    ["plan_type"],  # SIMPLE, MULTI_STEP, MULTI_AGENT
)

planner_validation_errors_total = Counter(
    "planner_validation_errors_total",
    "Validation errors by type",
    ["error_type"],
)

# ═══════════════════════════════════════════════════════════════════════
# HITL METRICS
# ═══════════════════════════════════════════════════════════════════════

hitl_interrupts_total = Counter(
    "hitl_interrupts_total",
    "Total HITL interruptions",
    ["interrupt_type"],  # plan_approval, tool_confirmation, draft_critique
)

hitl_decisions_total = Counter(
    "hitl_decisions_total",
    "User decisions on HITL",
    ["decision"],  # approve, reject, edit
)

hitl_response_latency_seconds = Histogram(
    "hitl_response_latency_seconds",
    "Time for user to respond to HITL",
    buckets=[5, 15, 30, 60, 120, 300],
)

# ═══════════════════════════════════════════════════════════════════════
# LLM METRICS
# ═══════════════════════════════════════════════════════════════════════

llm_tokens_total = Counter(
    "llm_tokens_total",
    "Total tokens consumed",
    ["model", "type"],  # type: input, output
)

llm_cost_total = Counter(
    "llm_cost_total",
    "Total LLM costs in USD",
    ["model"],
)

llm_latency_seconds = Histogram(
    "llm_latency_seconds",
    "LLM API latency",
    ["model", "node"],
)

# ═══════════════════════════════════════════════════════════════════════
# CACHE METRICS
# ═══════════════════════════════════════════════════════════════════════

cache_hits_total = Counter(
    "cache_hits_total",
    "Cache hits",
    ["cache_type"],  # llm, contacts, places
)

cache_misses_total = Counter(
    "cache_misses_total",
    "Cache misses",
    ["cache_type"],
)
```

### 20.2 Utilisation dans le Code

```python
# Dans un tool
async def execute_api_call(self, client, user_id, **kwargs):
    start_time = time.time()
    try:
        result = await client.search(**kwargs)
        tools_execution_total.labels(
            tool_name=self.tool_name,
            status="success",
        ).inc()
        return result
    except Exception as e:
        tools_execution_total.labels(
            tool_name=self.tool_name,
            status="error",
        ).inc()
        raise
    finally:
        latency = time.time() - start_time
        tools_latency_seconds.labels(tool_name=self.tool_name).observe(latency)
```

### 20.3 Tracing Langfuse

**Fichier**: `src/infrastructure/observability/tracing.py`

```python
from langfuse import Langfuse
from langfuse.callback import CallbackHandler as LangfuseCallbackHandler

# Initialisation globale
langfuse = Langfuse(
    public_key=settings.langfuse_public_key,
    secret_key=settings.langfuse_secret_key,
    host=settings.langfuse_host,
)

def create_langfuse_handler(
    user_id: str,
    session_id: str,
    trace_name: str,
) -> LangfuseCallbackHandler:
    """Crée handler Langfuse avec contexte."""
    return LangfuseCallbackHandler(
        trace_name=trace_name,
        user_id=user_id,
        session_id=session_id,
        tags=[
            f"env:{settings.environment}",
            f"version:{settings.app_version}",
        ],
        metadata={
            "user_id": user_id,
            "session_id": session_id,
        },
    )
```

### 20.4 Structured Logging

```python
import structlog

logger = structlog.get_logger(__name__)

# Configuration globale
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

# Utilisation avec contexte
logger = logger.bind(
    user_id=user_id,
    session_id=session_id,
    tool_name="search_contacts_tool",
)

logger.info(
    "tool_executed",
    duration_ms=123,
    result_count=5,
    cache_hit=True,
)

# Output JSON:
# {
#   "event": "tool_executed",
#   "user_id": "user123",
#   "session_id": "sess456",
#   "tool_name": "search_contacts_tool",
#   "duration_ms": 123,
#   "result_count": 5,
#   "cache_hit": true,
#   "timestamp": "2025-01-15T10:30:00Z",
#   "level": "info"
# }
```

---

## 21. Tests et Patterns

### 21.1 Structure des Tests

```
apps/api/tests/
├── agents/
│   ├── tools/
│   │   ├── test_contacts_tools.py
│   │   ├── test_calendar_tools.py
│   │   └── ...
│   ├── nodes/
│   │   ├── test_planner_node.py   # Tests pour planner_node_v3
│   │   ├── test_response_node.py
│   │   └── ...
│   ├── services/
│   │   ├── test_hitl_classifier.py
│   │   ├── test_question_generator.py
│   │   └── ...
│   ├── orchestration/
│   │   ├── test_parallel_executor.py
│   │   ├── test_semantic_validator.py
│   │   └── ...
│   └── integration/
│       ├── test_hitl_streaming_e2e.py
│       └── ...
├── conftest.py  # Fixtures globales
└── ...
```

### 21.2 Fixtures Communes

**Fichier**: `tests/conftest.py`

```python
import pytest
from unittest.mock import MagicMock, AsyncMock
from langgraph.store.memory import InMemoryStore

@pytest.fixture
def mock_runtime():
    """Mock ToolRuntime avec config minimale."""
    runtime = MagicMock()
    runtime.config = {
        "configurable": {
            "user_id": "test-user-123",
            "session_id": "test-session-456",
        }
    }
    runtime.store = InMemoryStore()
    return runtime

@pytest.fixture
async def db_session():
    """Session SQLAlchemy in-memory pour tests."""
    from src.infrastructure.database.session import get_db_context
    async with get_db_context() as session:
        yield session

@pytest.fixture
def mock_connector_service():
    """Mock ConnectorService."""
    service = AsyncMock()
    service.get_oauth_credentials.return_value = {
        "access_token": "mock_token",
        "refresh_token": "mock_refresh",
    }
    return service

@pytest.fixture
def mock_llm():
    """Mock LLM pour tests sans API calls."""
    llm = AsyncMock()
    llm.ainvoke.return_value = AIMessage(content="Mocked response")
    return llm

@pytest.fixture
def agent_registry():
    """Registry avec manifests de test."""
    from src.domains.agents.registry import AgentRegistry
    registry = AgentRegistry()
    # Enregistrer manifests de test
    registry.register_tool(MOCK_SEARCH_MANIFEST)
    return registry
```

### 21.3 Test Pattern pour Tools

```python
# tests/agents/tools/test_contacts_tools.py

import pytest
from unittest.mock import AsyncMock, patch

from src.domains.agents.tools.google_contacts_tools import SearchContactsTool

class TestSearchContactsTool:
    """Tests pour SearchContactsTool."""

    @pytest.fixture
    def tool(self):
        return SearchContactsTool()

    @pytest.fixture
    def mock_client(self):
        client = AsyncMock()
        client.search_contacts.return_value = {
            "connections": [
                {"resourceName": "people/c123", "names": [{"displayName": "Jean"}]},
            ],
            "totalPeople": 1,
        }
        return client

    @pytest.mark.asyncio
    async def test_search_returns_contacts(self, tool, mock_runtime, mock_client):
        """Test recherche retourne contacts formatés."""
        with patch.object(tool, "_get_client", return_value=mock_client):
            result = await tool.execute(
                runtime=mock_runtime,
                query="jean",
            )

        assert "contacts" in result or isinstance(result, StandardToolOutput)
        mock_client.search_contacts.assert_called_once_with(query="jean")

    @pytest.mark.asyncio
    async def test_search_empty_query_returns_error(self, tool, mock_runtime):
        """Test query vide retourne erreur."""
        result = await tool.execute(
            runtime=mock_runtime,
            query="",
        )

        assert "error" in result.lower() or "erreur" in result.lower()

    @pytest.mark.asyncio
    async def test_search_handles_api_error(self, tool, mock_runtime, mock_client):
        """Test gestion erreur API."""
        mock_client.search_contacts.side_effect = Exception("API Error")

        with patch.object(tool, "_get_client", return_value=mock_client):
            result = await tool.execute(
                runtime=mock_runtime,
                query="jean",
            )

        assert "error" in result.lower()
```

### 21.4 Test Pattern pour HITL

```python
# tests/agents/integration/test_hitl_e2e.py

import pytest
from langgraph.errors import GraphInterrupt

class TestHITLFlow:
    """Tests end-to-end du flow HITL."""

    @pytest.mark.asyncio
    async def test_plan_approval_interrupt(self, agent, mock_config):
        """Test interruption pour approbation plan."""
        state = {"messages": [HumanMessage("Envoie un email à Jean")]}

        with pytest.raises(GraphInterrupt) as exc_info:
            await agent.ainvoke(state, mock_config)

        interrupt = exc_info.value
        assert interrupt.interrupt_type == "plan_approval"
        assert "question" in interrupt.data

    @pytest.mark.asyncio
    async def test_plan_approval_resume_approve(self, agent, mock_config):
        """Test reprise après approbation."""
        # Premier appel → interrupt
        try:
            await agent.ainvoke(state, mock_config)
        except GraphInterrupt:
            pass

        # Resume avec approbation
        resume_state = {
            "messages": [HumanMessage("oui")],
            "__resume": {"decision": "approve"},
        }

        result = await agent.ainvoke(resume_state, mock_config)

        assert "done" in result or result.get("response")

    @pytest.mark.asyncio
    async def test_plan_approval_resume_reject(self, agent, mock_config):
        """Test reprise après rejet."""
        # ... similar pattern with reject
```

### 21.5 Mocks pour APIs Externes

```python
# tests/mocks/google_api.py

import responses
from unittest.mock import AsyncMock

def mock_google_people_api():
    """Mock Google People API responses."""
    responses.add(
        responses.GET,
        "https://people.googleapis.com/v1/people:searchContacts",
        json={
            "results": [
                {
                    "person": {
                        "resourceName": "people/c123",
                        "names": [{"displayName": "Jean Dupont"}],
                    }
                }
            ]
        },
        status=200,
    )

def create_mock_google_client():
    """Crée mock client Google complet."""
    client = AsyncMock()

    # Contacts
    client.search_contacts.return_value = {"connections": [...]}
    client.get_contact.return_value = {"resourceName": "people/c123", ...}

    # Calendar
    client.list_events.return_value = {"items": [...]}
    client.create_event.return_value = {"id": "event123", ...}

    return client
```

---

## 22. INTELLIPLANNER - Orchestration Avancée

**Version**: 1.1 (2025-12-06)

INTELLIPLANNER améliore l'orchestration multi-agents avec deux composants clés :
- **Phase B+**: Flux de données structurées pour templates Jinja2 ✅ **Production Ready**
- **Phase E**: Re-planning adaptatif intelligent ⚠️ **Partiellement implémenté**

> **Note**: Les décisions `RETRY_SAME` et `REPLAN_MODIFIED` ne sont pas encore implémentées (voir section Status d'Implémentation).

### 22.1 Phase B+: Données Structurées pour Templates

#### Problème Résolu

Les templates Jinja2 comme `{{ steps.list_all_calendars.calendars[0].id }}` échouaient car seul le texte `summary_for_llm` était stocké dans `completed_steps`, pas les données structurées.

#### Impact sur les Tools

**Avant (non fonctionnel pour Jinja2):**
```python
return StandardToolOutput(
    summary_for_llm="Found 3 calendars",
    registry_updates={...},
)
# → completed_steps["list_calendars"] = "Found 3 calendars" (string)
```

**Après (INTELLIPLANNER B+):**
```python
return StandardToolOutput(
    summary_for_llm="Found 3 calendars",
    registry_updates={...},
    structured_data={  # NOUVEAU
        "calendars": [{"id": "cal1"}, {"id": "cal2"}],
        "count": 2,
        "primary_id": "cal1",
    },
)
# → completed_steps["list_calendars"] = {"calendars": [...], "count": 2}
```

#### Méthode get_step_output()

```python
# tools/output.py
class StandardToolOutput:
    def get_step_output(self) -> dict[str, Any]:
        """
        Retourne les données pour completed_steps.

        Priorités:
        1. structured_data si peuplé (explicit)
        2. Extraction depuis registry_updates groupés par type (fallback)
        3. {"summary": summary_for_llm, "count": 0} (ultimate fallback)
        """
```

#### Mapping RegistryItemType → Clé

Pour le fallback automatique, un mapping explicite gère les pluriels :

```python
REGISTRY_TYPE_TO_KEY = {
    CONTACT: "contacts",    # Standard plural
    EMAIL: "emails",
    EVENT: "events",
    TASK: "tasks",
    FILE: "files",
    CALENDAR: "calendars",
    PLACE: "places",
    WEATHER: "weather",     # Singular (not "weathers")
    WIKIPEDIA_ARTICLE: "articles",
    SEARCH_RESULT: "results",
    DRAFT: "drafts",
    CHART: "charts",
    NOTE: "notes",
    CALENDAR_SLOT: "slots", # Not "calendar_slots"
}
```

#### Migration de Tools Existants

**Aucune action requise** - Le fallback `get_step_output()` extrait automatiquement depuis `registry_updates` si `structured_data` n'est pas fourni.

**Recommandé pour nouveaux tools** - Peupler explicitement `structured_data` avec les clés attendues par les templates Jinja2:

```python
def format_registry_response(self, result: dict[str, Any]) -> StandardToolOutput:
    calendars = result.get("calendars", [])

    return StandardToolOutput(
        summary_for_llm=f"Found {len(calendars)} calendars",
        registry_updates=self._build_registry_items(calendars),
        structured_data={  # Clés explicites pour templates
            "calendars": [self._simplify(c) for c in calendars],
            "count": len(calendars),
            "primary_id": self._find_primary_id(calendars),
        },
    )
```

### 22.2 Phase E: AdaptiveRePlanner

#### Concept

Le replanner détecte les échecs d'exécution et décide de la stratégie de récupération.

```
Execute Plan
    ↓
Analyze Results
    ↓
Detect Trigger (empty_results? failure? timeout?)
    ↓ [trigger found]
Decide Action (proceed? retry? escalate?)
    ↓
Execute Decision
```

#### Intégration dans task_orchestrator_node.py

```python
from src.domains.agents.orchestration import (
    AdaptiveRePlanner,
    RePlanContext,
    RePlanDecision,
    analyze_execution_results,
    should_trigger_replan,
)

async def task_orchestrator_node(state, config):
    # ... execute plan ...

    # Quick check
    should_replan, trigger = should_trigger_replan(
        execution_plan=plan,
        completed_steps=results,
    )

    if not should_replan:
        return proceed_to_response(state, results)

    # Full analysis
    analysis = analyze_execution_results(plan, results)

    context = RePlanContext(
        user_request=state["user_request"],
        execution_plan=plan,
        completed_steps=results,
        execution_analysis=analysis,
        replan_attempt=state.get("replan_attempt", 0),
        max_attempts=settings.adaptive_replanning_max_attempts,
    )

    replanner = AdaptiveRePlanner()
    result = replanner.analyze_and_decide(context)

    match result.decision:
        case RePlanDecision.PROCEED:
            return proceed_to_response(state, results)

        case RePlanDecision.RETRY_SAME:
            return retry_execution(state, plan)

        case RePlanDecision.REPLAN_MODIFIED:
            return regenerate_plan(state, result.recovery_strategy)

        case RePlanDecision.ESCALATE_USER:
            return ask_user_clarification(state, result.user_message)

        case RePlanDecision.ABORT:
            return abort_with_message(state, result.user_message)
```

#### Configuration

```python
# core/config/agents.py
class AgentsSettings(BaseSettings):
    # INTELLIPLANNER Phase E
    adaptive_replanning_max_attempts: int = Field(
        default=3,
        ge=1, le=5,
        description="Max re-planning attempts before giving up"
    )
    adaptive_replanning_empty_threshold: float = Field(
        default=0.8,
        ge=0.0, le=1.0,
        description="Empty rate threshold for re-planning trigger"
    )

# core/config/advanced.py
class AdvancedSettings(BaseSettings):
    # INTELLIPLANNER Phase B+
    jinja_max_recursion_depth: int = Field(
        default=10,
        ge=5, le=50,
        description="Max recursion depth for Jinja2 template parameter evaluation"
    )
```

#### Triggers et Décisions

| Trigger | Description |
|---------|-------------|
| `EMPTY_RESULTS` | Tous les outils ont retourné 0 résultat |
| `PARTIAL_EMPTY` | Certains outils sans résultat (> seuil) |
| `PARTIAL_FAILURE` | Certains steps ont échoué |
| `SEMANTIC_MISMATCH` | Résultats ne correspondent pas à l'intention |
| `REFERENCE_ERROR` | `$steps.X.field` non résolu |
| `DEPENDENCY_ERROR` | Données de dépendance manquantes |
| `TIMEOUT` | Exécution trop longue |

| Décision | Action |
|----------|--------|
| `PROCEED` | Continuer vers response_node |
| `RETRY_SAME` | Réexécuter le plan tel quel |
| `REPLAN_MODIFIED` | Régénérer avec paramètres modifiés |
| `REPLAN_NEW` | Nouvelle stratégie complète |
| `ESCALATE_USER` | Demander clarification |
| `ABORT` | Abandonner et expliquer |

#### Métriques Prometheus

```python
# infrastructure/observability/metrics_agents.py

# Triggers détectés
adaptive_replanner_triggers_total = Counter(
    "adaptive_replanner_triggers_total",
    "Total re-planning triggers detected by type",
    ["trigger"],  # empty_results, partial_failure, reference_error...
)

# Décisions prises
adaptive_replanner_decisions_total = Counter(
    "adaptive_replanner_decisions_total",
    "Total re-planning decisions by type",
    ["decision"],  # proceed, retry_same, replan_modified, escalate_user, abort
)

# Tentatives
adaptive_replanner_attempts_total = Counter(
    "adaptive_replanner_attempts_total",
    "Total re-planning attempts",
    ["attempt_number"],  # 1, 2, 3
)

# Récupérations réussies
adaptive_replanner_recovery_success_total = Counter(
    "adaptive_replanner_recovery_success_total",
    "Successful recoveries by strategy",
    ["strategy"],  # broaden_search, alternative_source...
)
```

### 22.3 Fichiers INTELLIPLANNER

| Catégorie | Fichier | Description |
|-----------|---------|-------------|
| **Phase B+** | `tools/output.py` | `StandardToolOutput.structured_data` + `get_step_output()` + `REGISTRY_TYPE_TO_KEY` |
| | `orchestration/parallel_executor.py` | `StepResult.structured_data` + `_merge_single_step_result()` |
| | `orchestration/schemas.py` | `StepResult` export pour orchestration |
| | `orchestration/jinja_evaluator.py` | `JinjaEvaluator` pour évaluation templates |
| | `orchestration/query_engine/models.py` | Source "steps" dans `validate_source()` |
| **Phase E** | `orchestration/adaptive_replanner.py` | `AdaptiveRePlanner` service complet (~900 lignes) |
| | `orchestration/__init__.py` | Exports publics (enums, dataclasses, fonctions) |
| | `nodes/task_orchestrator_node.py` | Point d'intégration post-exécution |
| | `core/config/agents.py` | Configuration `adaptive_replanning_*` |
| | `core/config/advanced.py` | Configuration `jinja_max_recursion_depth` |
| **Tests** | `tests/agents/orchestration/test_adaptive_replanner.py` | Tests unitaires replanner |
| | `tests/unit/.../test_standard_tool_output_structured_data.py` | Tests structured_data |

### 22.4 Status d'Implémentation Phase E

| Décision | Status | Notes |
|----------|--------|-------|
| `PROCEED` | ✅ Implémenté | Continue vers response_node |
| `ESCALATE_USER` | ✅ Implémenté | Message affiché à l'utilisateur |
| `ABORT` | ✅ Implémenté | Abandonne avec message explicatif |
| `RETRY_SAME` | ⏳ En cours | TODO - Requiert restructuration du graphe |
| `REPLAN_MODIFIED` | ⏳ En cours | TODO - Requiert appel au planner_node |
| `REPLAN_NEW` | ⏳ En cours | TODO - Stratégie complète nouvelle |

> **Impact**: La détection des triggers fonctionne pleinement. Les décisions `PROCEED`, `ESCALATE_USER` et `ABORT` sont opérationnelles. Les flows `RETRY` et `REPLAN` nécessitent une restructuration du graphe LangGraph pour pouvoir reboucler vers `planner_node`.

### 22.5 Bonnes Pratiques

1. **Toujours peupler `structured_data`** pour les nouveaux tools utilisant Jinja2
2. **Utiliser les clés standard** (contacts, emails, events...) pour la cohérence
3. **Inclure un `count`** dans `structured_data` pour faciliter les conditions
4. **Logger les décisions de replanning** pour le debugging production
5. **Ne pas dépasser 3 tentatives** de replanning (éviter les boucles infinies)

### 22.6 Exemples d'Accès Templates Jinja2

Une fois les tools exécutés, les données sont accessibles via `{{ steps.step_id.field }}`:

```jinja2
{# Accès au premier calendrier #}
{{ steps.list_calendars.calendars[0].id }}

{# Condition sur le nombre de résultats #}
{% if steps.search_contacts.contacts | length >= 2 %}
    Plusieurs contacts trouvés
{% endif %}

{# Itération sur les emails #}
{% for email in steps.search_emails.emails %}
    - {{ email.subject }}
{% endfor %}

{# Accès conditionnel avec fallback #}
{{ steps.get_details.contact.name | default("Inconnu") }}
```

**Structure completed_steps après exécution:**
```python
completed_steps = {
    "list_calendars": {
        "calendars": [{"id": "cal1", "name": "Primary"}, ...],
        "count": 3,
        "primary_id": "cal1"
    },
    "search_contacts": {
        "contacts": [{"name": "John", "email": "john@example.com"}, ...],
        "count": 5
    }
}
```

---

## Annexe: Structure des Fichiers

```
apps/api/src/
├── domains/
│   ├── agents/
│   │   ├── tools/
│   │   │   ├── base.py              # ConnectorTool, APIKeyConnectorTool
│   │   │   ├── output.py            # StandardToolOutput + INTELLIPLANNER B+
│   │   │   ├── mixins.py            # ToolOutputMixin
│   │   │   ├── common.py            # @connector_tool decorator
│   │   │   ├── {domain}_tools.py    # Tools du domaine
│   │   │   └── ...
│   │   ├── graphs/
│   │   │   ├── base_agent_builder.py
│   │   │   ├── {domain}_agent_builder.py
│   │   │   └── ...
│   │   ├── nodes/                   # Architecture v3
│   │   │   ├── router_node_v3.py    # Query analysis + routing
│   │   │   ├── planner_node_v3.py   # Smart planning
│   │   │   ├── task_orchestrator_node.py  # Execution + INTELLIPLANNER
│   │   │   ├── response_node.py     # Generation reponse finale
│   │   │   └── approval_gate_node.py # HITL approbation
│   │   ├── registry/
│   │   │   ├── catalogue.py         # ToolManifest, AgentManifest
│   │   │   ├── catalogue_loader.py  # initialize_catalogue()
│   │   │   └── agent_registry.py
│   │   ├── {domain}/
│   │   │   ├── __init__.py
│   │   │   └── catalogue_manifests.py
│   │   ├── data_registry/
│   │   │   ├── models.py            # RegistryItemType, RegistryItem
│   │   │   └── state.py
│   │   └── orchestration/
│   │       ├── parallel_executor.py # ToolRegistry + StepResult + INTELLIPLANNER B+
│   │       ├── schemas.py           # StepResult, ExecutionResult, AgentResult
│   │       ├── jinja_evaluator.py   # JinjaEvaluator pour templates
│   │       ├── adaptive_replanner.py # INTELLIPLANNER Phase E (~900 lignes)
│   │       ├── condition_evaluator.py # Évaluation conditions
│   │       ├── dependency_graph.py  # Graphe de dépendances
│   │       └── query_engine/
│   │           ├── models.py        # validate_source("steps")
│   │           └── executor.py      # LocalQueryExecutor
│   └── connectors/
│       ├── clients/
│       │   ├── base_google_client.py
│       │   ├── base_api_key_client.py
│       │   ├── google_{domain}_client.py
│       │   └── __init__.py
│       └── models.py               # ConnectorType enum
├── core/
│   └── config/
│       ├── agents.py              # adaptive_replanning_* settings
│       └── advanced.py            # jinja_max_recursion_depth setting
```

---

**Document maintenu par l'équipe LIA**
