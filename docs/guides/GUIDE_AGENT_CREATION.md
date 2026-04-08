# Guide de Création d'Agent - LIA

> **Guide exhaustif et définitif** pour créer un nouvel agent, tool ou connecteur de A à Z.
> Version 2.2 - 2025-12-28 - Corrections imports, scopes OAuth, valeurs par défaut.

---

## Table des Matières

- [Vue d'Ensemble](#vue-densemble)
- [Architecture du Système](#architecture-du-système)
- [Structure des Fichiers](#structure-des-fichiers)
- [PARTIE 1 : Créer un Nouvel Agent](#partie-1--créer-un-nouvel-agent)
  - [Étape 1 : Planification](#étape-1--planification)
  - [Étape 2 : Domain Taxonomy](#étape-2--domain-taxonomy)
  - [Étape 3 : Agent Manifest](#étape-3--agent-manifest)
  - [Étape 4 : Tool Manifests](#étape-4--tool-manifests)
  - [Étape 5 : Semantic Keywords](#étape-5--semantic-keywords-critique)
  - [Étape 6 : Intent Anchors](#étape-6--intent-anchors-critique)
  - [Étape 7 : Tool Implementation](#étape-7--tool-implementation)
  - [Étape 8 : Registration](#étape-8--registration)
  - [Étape 9 : Tests](#étape-9--tests)
- [PARTIE 2 : Référence Complète des Schémas](#partie-2--référence-complète-des-schémas)
- [PARTIE 3 : Patterns d'Implémentation](#partie-3--patterns-dimplémentation)
- [PARTIE 4 : Checklist de Validation](#partie-4--checklist-de-validation)
- [PARTIE 5 : Erreurs Courantes et Solutions](#partie-5--erreurs-courantes-et-solutions)
- [PARTIE 6 : Outils de Débogage](#partie-6--outils-de-débogage)
- [PARTIE 7 : Scopes OAuth Google](#partie-7--scopes-oauth-google)
- [PARTIE 8 : Métriques Prometheus](#partie-8--métriques-prometheus)
- [PARTIE 9 : Hot-Reload Development](#partie-9--hot-reload-development)
- [PARTIE 10 : Exemple Complet - Agent de A à Z](#partie-10--exemple-complet---agent-de-a-à-z)
- [PARTIE 11 : Agents MCP Dynamiques](#partie-11--agents-mcp-dynamiques)
- [PARTIE 12 : Agents avec Notifications Proactives (Heartbeat)](#partie-12--agents-avec-notifications-proactives-heartbeat)

---

## Vue d'Ensemble

### Objectif de ce Guide

Ce guide fournit **toutes les informations nécessaires** pour créer ou modifier un agent, tool ou connecteur dans LIA. Chaque étape est documentée avec :

- Les champs **obligatoires** et **optionnels**
- Les **valeurs attendues** et leurs formats
- Les **exemples concrets** tirés du codebase
- Les **erreurs courantes** à éviter

### Principes Fondamentaux

1. **Déclaratif first** : Manifestes déclaratifs avant implémentation
2. **Semantic routing** : Le système utilise des embeddings pour router les requêtes
3. **Fail-fast** : Validation au démarrage, pas en runtime
4. **DRY** : Réutilisation maximale des patterns existants

---

## Architecture du Système

### Flux de Traitement d'une Requête

```
User Query
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  1. ROUTER NODE                                              │
│     - Semantic Intent Detection (INTENT_ANCHORS)            │
│     - Domain Detection (DOMAIN_REGISTRY keywords)           │
│     - Output: {intention, domains[], next_node}             │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  2. PLANNER NODE                                             │
│     - Semantic Tool Selection (semantic_keywords)           │
│     - Filter tools by detected domains + intent             │
│     - Generate execution plan                               │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  3. TOOL EXECUTOR NODE                                       │
│     - Execute tool instances                                │
│     - Handle errors, metrics, caching                       │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  4. ADAPTIVE REPLANNER                                       │
│     - Analyze results (check for empty_results, errors)     │
│     - Decide if replanning needed                           │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
Response to User
```

### Composants Clés

| Composant | Fichier | Rôle |
|-----------|---------|------|
| **Domain Taxonomy** | `domain_taxonomy.py` | Configuration des domaines (keywords, agents) |
| **Agent Manifest** | `catalogue_loader.py` | Définition des agents (nom, tools) |
| **Tool Manifest** | `{domain}/catalogue_manifests.py` | Définition des tools (params, semantic_keywords) |
| **Intent Anchors** | `semantic_intent_detector.py` | Classification d'intention (create, list, search...) |
| **Tool Implementation** | `tools/{domain}_tools.py` | Code exécutable des tools |
| **Tool Registration** | `catalogue_loader.py` | Enregistrement des instances |

---

## Structure des Fichiers

### Pour un Nouveau Domain : `{domain}`

```
apps/api/src/domains/agents/
├── {domain}/                           # Nouveau domain
│   ├── __init__.py
│   ├── catalogue_manifests.py          # Tool manifests UNIQUEMENT
│   └── prompts/
│       └── v1/
│           └── {domain}_agent_prompt.txt
│
├── tools/
│   └── {domain}_tools.py               # Implémentation des tools
│
├── registry/
│   ├── catalogue_loader.py             # Agent manifest + registration
│   ├── catalogue.py                    # Schémas (ToolManifest, AgentManifest)
│   └── domain_taxonomy.py              # DomainConfig
│
└── services/
    └── semantic_intent_detector.py     # INTENT_ANCHORS
```

### Fichiers à Modifier (Checklist Rapide)

1. `domain_taxonomy.py` - Ajouter DomainConfig
2. `catalogue_loader.py` - Ajouter AgentManifest + imports + registration
3. `{domain}/catalogue_manifests.py` - Créer Tool manifests
4. `semantic_intent_detector.py` - Ajouter Intent anchors si nouveau type d'intent
5. `tools/{domain}_tools.py` - Implémenter tools
6. `catalogue_loader.py` - Enregistrer tool instances dans `_register_tool_instances()`

---

## PARTIE 1 : Créer un Nouvel Agent

### Étape 1 : Planification

Avant de coder, répondre à ces questions :

| Question | Exemples de Réponse |
|----------|---------------------|
| **Nom du domain** | `weather`, `reminders`, `tasks` |
| **Type de connecteur** | OAuth (Google), API Key (OpenWeatherMap), Internal (Reminders) |
| **Outils nécessaires** | `search_*`, `get_*_details`, `create_*`, `update_*`, `delete_*` |
| **Actions destructives ?** | Si oui, HITL required |
| **Nouveau type d'intent ?** | Si actions non couvertes par create/update/delete/search/list/detail |

### Étape 2 : Domain Taxonomy

**Fichier** : `apps/api/src/domains/agents/registry/domain_taxonomy.py`

**Action** : Ajouter une entrée `DomainConfig` dans `DOMAIN_REGISTRY`

```python
# =============================================================================
# SCHÉMA COMPLET : DomainConfig
# =============================================================================

@dataclass(frozen=True)
class DomainConfig:
    # OBLIGATOIRES
    name: str                    # Identifiant interne (ex: "contacts", "emails")
    display_name: str            # Nom affichable (ex: "Google Contacts")
    description: str             # Description courte des capacités
    keywords: list[str]          # Mots-clés pour détection par Router LLM
    agent_names: list[str]       # Liste des agents (ex: ["contacts_agent"])

    # OPTIONNELS
    related_domains: list[str]   # Domaines souvent utilisés ensemble
    priority: int = 5            # Priorité 1-10 (10 = toujours chargé)
    is_routable: bool = True     # False pour domaines techniques (context, query)
    metadata: dict[str, Any]     # Métadonnées additionnelles
```

**Exemple Complet** :

```python
"reminder": DomainConfig(
    name="reminder",
    display_name="Rappels",
    description="Create, list, cancel reminders",
    keywords=[
        # Mots-clés primaires (Français)
        "rappel", "rappelle", "rappelle-moi", "rappeler", "notification",
        # Mots-clés primaires (Anglais)
        "remind", "remind me", "reminder", "reminders",
        # Déclencheurs temporels
        "dans", "d'ici", "à", "vers", "demain", "plus tard",
        "in", "at", "later", "tomorrow",
        # Actions
        "annule rappel", "cancel reminder", "mes rappels", "my reminders",
    ],
    agent_names=["reminder_agent"],
    related_domains=[],  # Rappels sont standalone
    priority=9,  # Haute priorité : action directe utilisateur
    metadata={
        "provider": "internal",
        "requires_oauth": False,
        "requires_hitl": False,
        "notification_type": "fcm",
    },
),
```

**Règles CRITIQUES** :

| Règle | Explication |
|-------|-------------|
| `name` doit correspondre au préfixe de `agent_names` | `name="emails"` → `agent_names=["emails_agent"]` |
| `keywords` doit être exhaustif | Inclure FR + EN + variations courantes |
| `is_routable=False` pour domaines techniques | Ex: `context`, `query` |

---

### Étape 3 : Agent Manifest

**Fichier** : `apps/api/src/domains/agents/registry/catalogue_loader.py`

> **NOTE** : AgentManifest est généralement défini dans `catalogue_loader.py`.
> **Exception** : Pour les agents internes (ex: `reminder_agent`), l'AgentManifest peut être défini dans `{domain}/catalogue_manifests.py` puis importé dans `catalogue_loader.py`.

```python
# =============================================================================
# SCHÉMA COMPLET : AgentManifest
# =============================================================================

@dataclass
class AgentManifest:
    # OBLIGATOIRES
    name: str                              # Format: "{domain}_agent"
    description: str                       # Description complète des capacités
    tools: list[str]                       # Noms des tools (doivent exister)

    # OPTIONNELS (avec valeurs par défaut)
    max_parallel_runs: int = 1             # Instances parallèles (1 = séquentiel)
    default_timeout_ms: int = 30000        # Timeout par défaut
    prompt_version: str = "v1"             # Version du prompt
    owner_team: str = "Team AI"            # Équipe propriétaire
    version: str = "1.0.0"                 # Version semver
    updated_at: datetime                   # Date de mise à jour
    display: DisplayMetadata | None        # Métadonnées UI (optionnel)
```

**Exemple Complet** :

```python
from datetime import UTC, datetime
from src.core.constants import DEFAULT_TOOL_TIMEOUT_MS

REMINDER_AGENT_MANIFEST = AgentManifest(
    name="reminder_agent",
    description=(
        "Agent spécialisé dans la gestion des rappels. "
        "Création, liste et annulation de rappels. "
        "Les rappels sont envoyés via notification push (FCM) à l'heure programmée. "
        "Supporte les références temporelles naturelles ('dans 5 minutes', 'demain à midi')."
    ),
    tools=[
        "create_reminder_tool",
        "list_reminders_tool",
        "cancel_reminder_tool",
    ],
    max_parallel_runs=1,
    default_timeout_ms=DEFAULT_TOOL_TIMEOUT_MS,
    prompt_version="v1",
    owner_team="Team AI",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)
```

**Emplacement dans `catalogue_loader.py`** :

```python
# 1. Définir le manifest (en haut du fichier)
REMINDER_AGENT_MANIFEST = AgentManifest(...)

# 2. L'enregistrer dans initialize_catalogue()
def initialize_catalogue(registry: AgentRegistry) -> None:
    # ...
    registry.register_agent_manifest(REMINDER_AGENT_MANIFEST)
```

---

### Étape 4 : Tool Manifests

**Fichier** : `apps/api/src/domains/agents/{domain}/catalogue_manifests.py`

> Ce fichier contient UNIQUEMENT les Tool manifests, PAS l'Agent manifest.

```python
# =============================================================================
# SCHÉMA COMPLET : ToolManifest
# =============================================================================

@dataclass
class ToolManifest:
    # === IDENTITÉ (OBLIGATOIRES) ===
    name: str                              # Format: "{action}_{domain}_tool"
    agent: str                             # Agent propriétaire
    description: str                       # Description pour LLM

    # === CONTRAT (OBLIGATOIRES) ===
    parameters: list[ParameterSchema]      # Paramètres d'entrée
    outputs: list[OutputFieldSchema]       # Champs de sortie

    # === COÛT (OBLIGATOIRE) ===
    cost: CostProfile                      # Estimation coûts

    # === SÉCURITÉ (OBLIGATOIRE) ===
    permissions: PermissionProfile         # Scopes, HITL

    # === COMPORTEMENT (OPTIONNELS) ===
    max_iterations: int = 1
    supports_dry_run: bool = False
    reference_fields: list[str] = []       # Champs pour références contextuelles
    context_key: str | None = None         # Clé pour auto-save Store

    # === SEMANTIC ROUTING (CRITIQUE) ===
    semantic_keywords: list[str] = []      # Phrases pour matching sémantique

    # === DOCUMENTATION (OPTIONNELS) ===
    examples: list[dict] = []              # Exemples input/output
    reference_examples: list[str] = []     # Patterns $steps.ID.PATH

    # === VERSIONING ===
    version: str = "1.0.0"
    updated_at: datetime

    # === UI (OPTIONNEL) ===
    display: DisplayMetadata | None = None

    # === CATÉGORIE (POUR FILTRAGE PAR INTENT) ===
    tool_category: ToolCategory | None = None  # "search", "list", "create", etc.

    # === INITIATIVE (OPTIONNEL) ===
    initiative_eligible: bool | None = None        # Eligible pour enrichissement proactif cross-domain
                                                   # None = auto-déterminé depuis category
                                                   #   (search/readonly = eligible, system = not eligible)
                                                   # False = exclure (browser, web search, listing structurel, context tools)

    # === CHAMPS OPTIONNELS AVANCÉS ===
    field_mappings: dict[str, str] | None = None   # Mapping de noms de champs
    examples_in_prompt: bool = True                # Inclure exemples dans prompt LLM
    maintainer: str = ""                           # Contact du mainteneur
    voice_weight: VoiceWeight | None = None        # Pondération pour mode vocal
```

**Exemple Complet** :

```python
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

list_reminders_catalogue_manifest = ToolManifest(
    name="list_reminders_tool",
    agent="reminder_agent",
    description=(
        "Liste les rappels en attente de l'utilisateur. "
        "Retourne tous les rappels avec statut 'pending' (en attente), "
        "triés par date de déclenchement croissante."
    ),
    parameters=[],  # Aucun paramètre requis
    outputs=[
        OutputFieldSchema(
            path="success", type="boolean",
            description="Si la requête a réussi",
        ),
        OutputFieldSchema(
            path="reminders", type="array",
            description="Liste des rappels en attente",
        ),
        OutputFieldSchema(
            path="reminders[].id", type="string",
            description="UUID du rappel",
        ),
        OutputFieldSchema(
            path="reminders[].content", type="string",
            description="Contenu du rappel",
        ),
        OutputFieldSchema(
            path="total", type="integer",
            description="Nombre total de rappels",
        ),
    ],
    cost=CostProfile(
        est_tokens_in=30,
        est_tokens_out=200,
        est_cost_usd=0.0001,
        est_latency_ms=150,
    ),
    permissions=PermissionProfile(
        required_scopes=[],  # Internal tool, no OAuth
        data_classification="CONFIDENTIAL",
        hitl_required=False,
    ),
    # === SEMANTIC KEYWORDS (CRITIQUE - voir Étape 5) ===
    semantic_keywords=[
        # Core patterns
        "list reminders", "show reminders", "my reminders", "pending reminders",
        # Variations
        "display reminders", "view reminders", "check reminders", "get reminders",
        "show my reminders", "list my reminders", "all my reminders",
        # Intent patterns
        "see my reminders", "any reminders", "do I have reminders",
    ],
    reference_examples=[
        "reminders[0].id",
        "reminders[*].content",
        "total",
    ],
    examples=[
        {
            "input": {},
            "output": {
                "success": True,
                "reminders": [
                    {"id": "uuid...", "content": "appeler le médecin", "trigger_at_formatted": "29/12 à 10:00"},
                ],
                "total": 1,
            },
        },
    ],
    display=DisplayMetadata(
        emoji="📋",
        i18n_key="list_reminders",
        visible=True,
        category="tool",
    ),
    tool_category="list",  # Important pour filtrage par intent
    initiative_eligible=False,  # Listing tool, not useful for proactive enrichment
    version="1.0.0",
    updated_at=datetime.now(UTC),
)

# === EXPORTS ===
__all__ = [
    "create_reminder_catalogue_manifest",
    "list_reminders_catalogue_manifest",
    "cancel_reminder_catalogue_manifest",
]
```

---

### Étape 5 : Semantic Keywords (CRITIQUE)

> **C'est l'élément le plus important pour le routing.** Sans semantic_keywords appropriés, le tool ne sera jamais sélectionné.

**Fichier** : Dans le `ToolManifest` de chaque tool

**Objectif** : Permettre au `SemanticToolSelector` de matcher les requêtes utilisateur avec les tools appropriés via embeddings.

**Règles de Rédaction** :

| Règle | Exemple |
|-------|---------|
| Utiliser des phrases naturelles EN | "list my reminders", "show all reminders" |
| Couvrir toutes les variations | "list", "show", "display", "view", "get", "check" |
| Inclure les patterns d'intent | "do I have reminders", "any reminders" |
| 20-35 keywords par tool | Assez pour couvrir les variations |
| Pas de mots isolés | "reminders" seul est trop ambigu |

**Template Semantic Keywords** :

```python
semantic_keywords=[
    # === Core patterns (action + objet) ===
    "{action} {object}",           # "list reminders"
    "{action} my {object}",        # "list my reminders"
    "{action} all {object}",       # "list all reminders"

    # === Variations de verbes ===
    "show {object}",
    "display {object}",
    "view {object}",
    "get {object}",
    "check {object}",
    "see {object}",

    # === Patterns interrogatifs ===
    "what {object} do I have",
    "do I have any {object}",
    "any {object}",

    # === Patterns avec contexte ===
    "my pending {object}",
    "active {object}",
    "upcoming {object}",
]
```

**Exemples par Catégorie de Tool** :

```python
# === SEARCH TOOL ===
semantic_keywords=[
    "search contacts", "find contacts", "look for contacts",
    "search for people", "find people named",
    "look up contact", "who is",
]

# === LIST TOOL ===
semantic_keywords=[
    "list contacts", "show contacts", "display contacts",
    "my contacts", "all contacts", "get contacts",
    "show all my contacts", "list all contacts",
]

# === DETAILS TOOL ===
semantic_keywords=[
    "get contact details", "show contact details",
    "contact information", "more info about",
    "details of", "full information",
]

# === CREATE TOOL ===
semantic_keywords=[
    "create contact", "add contact", "new contact",
    "add a new contact", "create new contact",
    "save contact", "add person",
]

# === DELETE TOOL ===
semantic_keywords=[
    "delete contact", "remove contact",
    "delete this contact", "remove this person",
    "erase contact",
]
```

---

### Étape 6 : Intent Anchors (CRITIQUE)

> **Si le type d'intent de votre tool n'existe pas**, vous devez l'ajouter dans `INTENT_ANCHORS`.

**Fichier** : `apps/api/src/domains/agents/services/semantic_intent_detector.py`

**Intents Existants** :

| Intent | Description | Exemples |
|--------|-------------|----------|
| `send` | Envoi message/email | "send email", "reply to" |
| `create` | Création d'élément | "create event", "add reminder" |
| `update` | Modification | "update contact", "reschedule" |
| `delete` | Suppression | "delete email", "cancel event" |
| `detail` | Détails d'un item | "show details", "more info" |
| `search` | Recherche | "find contacts", "search emails" |
| `list` | Énumération | "list my reminders", "show events" |
| `chat` | Conversation | "hello", "how are you" |
| `full` | Fallback | (confidence < threshold) |

**Quand Ajouter des Anchors** :

Vérifiez si vos tools correspondent à un intent existant. Si un type d'action de votre domain n'est pas bien représenté, ajoutez des anchors.

**Exemple - Ajout d'anchors pour "list" avec reminders** :

```python
INTENT_ANCHORS: dict[IntentType, list[str]] = {
    # ... autres intents ...

    "list": [
        # Anchors existants
        "list all items",
        "show everything",
        "display all entries",

        # === AJOUT REMINDERS (CRITIQUE) ===
        # Ces anchors permettent de détecter "list" pour les reminders
        "list my reminders",
        "show my reminders",
        "display my reminders",
        "get my reminders",
        "view my reminders",
        "what reminders do I have",
        "show all reminders",
        "check my reminders",
        "see my reminders",
        "any reminders",
    ],
}
```

**Règles** :

| Règle | Explication |
|-------|-------------|
| 5-15 anchors par sous-catégorie | Assez pour bon coverage |
| Phrases naturelles EN | Embeddings optimisés pour anglais |
| Distincts entre intents | "show reminders" = list, "show details" = detail |

---

### Étape 7 : Tool Implementation

**Fichier** : `apps/api/src/domains/agents/tools/{domain}_tools.py`

#### Pattern 1 : ConnectorTool (OAuth - Google)

```python
from src.domains.agents.tools.base import ConnectorTool
from src.domains.connectors.models import ConnectorType

class SearchContactsTool(ConnectorTool[GooglePeopleClient]):
    """Recherche de contacts Google."""

    connector_type = ConnectorType.GOOGLE_CONTACTS
    client_class = GooglePeopleClient

    def __init__(self):
        super().__init__(
            tool_name="search_contacts_tool",
            operation="search"
        )

    async def execute_api_call(
        self,
        client: GooglePeopleClient,
        user_id: UUID,
        **kwargs
    ) -> dict[str, Any]:
        query = kwargs["query"]
        max_results = kwargs.get("max_results", 10)
        return await client.search_contacts(query, max_results)
```

#### Pattern 2 : APIKeyConnectorTool (API Key)

```python
from src.domains.agents.tools.base import APIKeyConnectorTool

class GetWeatherTool(APIKeyConnectorTool[OpenWeatherMapClient]):
    """Météo actuelle."""

    connector_type = ConnectorType.OPENWEATHERMAP
    client_class = OpenWeatherMapClient

    def __init__(self):
        super().__init__(
            tool_name="get_current_weather_tool",
            operation="get_weather"
        )

    def create_client(self, credentials, user_id: UUID) -> OpenWeatherMapClient:
        return OpenWeatherMapClient(api_key=credentials.api_key)

    async def execute_api_call(
        self,
        client: OpenWeatherMapClient,
        user_id: UUID,
        **kwargs
    ) -> dict[str, Any]:
        location = kwargs["location"]
        return await client.get_current_weather(location)
```

#### Pattern 3 : Function-based Tool (Internal)

```python
import json
from typing import Annotated

from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg, tool

from src.domains.agents.tools.runtime_helpers import parse_user_id
from src.infrastructure.observability.decorators import track_tool_metrics
from src.infrastructure.observability.metrics_agents import (
    agent_tool_duration_seconds,
    agent_tool_invocations,
)

@track_tool_metrics(
    tool_name="list_reminders",
    agent_name="reminder_agent",
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
@tool
async def list_reminders_tool(
    runtime: Annotated[ToolRuntime, InjectedToolArg],
) -> str:
    """Liste les rappels en attente de l'utilisateur."""

    # 1. Extraire user_id depuis runtime.config
    config = runtime.config.get("configurable", {})
    user_id_raw = config.get("user_id")
    if not user_id_raw:
        return json.dumps({"error": "user_id_required"}, ensure_ascii=False)

    user_id = parse_user_id(user_id_raw)

    # 2. Get database session and execute logic
    from src.domains.reminders.service import ReminderService
    from src.infrastructure.database.session import get_db_context

    async with get_db_context() as db:
        reminder_service = ReminderService(db)
        reminders = await reminder_service.get_pending_by_user(user_id)

        # 3. Format response
        return json.dumps({
            "success": True,
            "reminders": [
                {
                    "id": str(r.id),
                    "content": r.content,
                    "trigger_at": r.trigger_at.isoformat(),
                }
                for r in reminders
            ],
            "total": len(reminders),
        }, ensure_ascii=False)
```

> **IMPORTANT** :
> - `runtime` DOIT être `Annotated[ToolRuntime, InjectedToolArg]` (pas juste `ToolRuntime`)
> - `@tool` vient de `langchain_core.tools`, PAS de `langchain.tools`
> - `ToolRuntime` vient de `langchain.tools`

---

### Étape 8 : Registration

**Fichier** : `apps/api/src/domains/agents/registry/catalogue_loader.py`

#### 8.1 Importer les Manifests

```python
# En haut de initialize_catalogue()
from src.domains.agents.reminders.catalogue_manifests import (
    REMINDER_AGENT_MANIFEST,  # Si défini dans catalogue_manifests.py
    cancel_reminder_catalogue_manifest,
    create_reminder_catalogue_manifest,
    list_reminders_catalogue_manifest,
)
```

#### 8.2 Enregistrer Agent Manifest

```python
def initialize_catalogue(registry: AgentRegistry) -> None:
    # ... imports ...

    # Register agent manifests
    registry.register_agent_manifest(REMINDER_AGENT_MANIFEST)
```

#### 8.3 Enregistrer Tool Manifests

```python
    # Register tool manifests
    registry.register_tool_manifest(create_reminder_catalogue_manifest)
    registry.register_tool_manifest(list_reminders_catalogue_manifest)
    registry.register_tool_manifest(cancel_reminder_catalogue_manifest)
```

#### 8.4 Enregistrer Tool Instances

```python
def _register_tool_instances(registry: AgentRegistry, logger) -> None:
    # ...

    # ========================================================================
    # Reminder Tools (Internal - No OAuth)
    # ========================================================================
    try:
        from src.domains.agents.tools.reminder_tools import (
            cancel_reminder_tool,
            create_reminder_tool,
            list_reminders_tool,
        )

        registry.register_tool_instance("create_reminder_tool", create_reminder_tool)
        registry.register_tool_instance("list_reminders_tool", list_reminders_tool)
        registry.register_tool_instance("cancel_reminder_tool", cancel_reminder_tool)
        registered_count += 3
    except ImportError as e:
        failed_imports.append(f"reminder_tools: {e}")
        logger.warning("tool_instance_import_failed", module="reminder_tools", error=str(e))
```

---

### Étape 9 : Tests

#### 9.1 Tests Unitaires

```python
# apps/api/tests/agents/{domain}/test_{domain}_tools.py

import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_list_reminders_success():
    """Test list_reminders_tool retourne les rappels."""
    # Arrange
    mock_runtime = MagicMock()
    mock_runtime.configurable = {"user_id": str(uuid4())}

    # Act
    result = await list_reminders_tool.ainvoke({}, config={"configurable": mock_runtime.configurable})

    # Assert
    data = json.loads(result)
    assert data["success"] is True
    assert "reminders" in data
    assert "total" in data
```

#### 9.2 Tests d'Intégration

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_reminder_agent_end_to_end():
    """Test agent complet avec graph."""
    # Test le flux complet : router → planner → executor → response
```

#### 9.3 Test Manuel

```bash
# Lancer le serveur
cd apps/api
uvicorn src.main:app --reload

# Tester via curl
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <TOKEN>" \
  -d '{"message": "liste mes rappels", "conversation_id": "..."}'
```

---

## PARTIE 2 : Référence Complète des Schémas

### ParameterSchema

```python
from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class ParameterSchema:
    name: str                                                      # Nom du paramètre
    type: str                                                      # "string", "integer", "boolean", "array", "object"
    required: bool                                                 # Obligatoire ou non
    description: str                                               # Description pour LLM
    constraints: list[ParameterConstraint] = field(default_factory=list)  # Validation (optionnel)
    schema: dict[str, Any] | None = None                           # JSON Schema complet (optionnel)
```

### ParameterConstraint

```python
@dataclass(frozen=True)
class ParameterConstraint:
    kind: Literal["min_length", "max_length", "minimum", "maximum", "pattern", "enum"]
    value: Any
```

**Exemples** :

```python
# String avec longueur min
ParameterConstraint(kind="min_length", value=1)

# Nombre max
ParameterConstraint(kind="maximum", value=100)

# Regex pattern
ParameterConstraint(kind="pattern", value=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")

# Enum
ParameterConstraint(kind="enum", value=["ASC", "DESC"])
```

### OutputFieldSchema

```python
@dataclass(frozen=True)
class OutputFieldSchema:
    path: str           # JSONPath (ex: "contacts[].name")
    type: str           # Type du champ
    description: str    # Description
    nullable: bool = False
```

### CostProfile

```python
@dataclass(frozen=True)
class CostProfile:
    est_tokens_in: int = 0      # Tokens d'entrée estimés
    est_tokens_out: int = 0     # Tokens de sortie estimés
    est_cost_usd: float = 0.0   # Coût estimé en USD
    est_latency_ms: int = 0     # Latence estimée en ms
```

### PermissionProfile

```python
@dataclass(frozen=True)
class PermissionProfile:
    required_scopes: list[str] = []        # Scopes OAuth requis
    allowed_roles: list[str] = []          # Roles autorisés (vide = tous)
    data_classification: str = "CONFIDENTIAL"  # PUBLIC, INTERNAL, CONFIDENTIAL, SENSITIVE, RESTRICTED
    hitl_required: bool = False            # Approbation utilisateur requise
```

### DisplayMetadata

```python
@dataclass(frozen=True)
class DisplayMetadata:
    emoji: str                             # Emoji visuel (ex: "🔍")
    i18n_key: str                          # Clé traduction (ex: "search_contacts")
    visible: bool = True                   # Afficher dans UI
    category: Literal["system", "agent", "tool", "context"] = "tool"
```

### ToolCategory

```python
ToolCategory = Literal[
    "search",    # search_contacts, search_emails
    "list",      # list_calendars, list_reminders
    "details",   # get_contact_details
    "create",    # create_event, create_reminder
    "update",    # update_contact
    "delete",    # delete_email, cancel_reminder
    "send",      # send_email, reply_email
    "readonly",  # get_weather (external, read-only)
    "system",    # resolve_reference, get_context
]
```

---

## PARTIE 3 : Patterns d'Implémentation

### Pattern OAuth (Google Services)

```
ConnectorTool[ClientType]
    ├── connector_type = ConnectorType.GOOGLE_*
    ├── client_class = Google*Client
    └── execute_api_call() → business logic only
```

### Pattern API Key (External Services)

```
APIKeyConnectorTool[ClientType]
    ├── connector_type = ConnectorType.OPENWEATHERMAP
    ├── client_class = OpenWeatherMapClient
    ├── create_client() → instantiate with api_key
    └── execute_api_call() → business logic
```

### Pattern Internal (No Auth)

```
@tool decorator
    └── async function
        ├── Parse user_id from runtime
        ├── Get dependencies
        ├── Execute logic with UoW
        └── Return JSON string
```

### Store Async (CRITIQUE)

```python
# ✅ CORRECT - dans contexte async (tools, endpoints)
await runtime.store.aput(namespace, key, value)
await runtime.store.aget(namespace, key)

# ❌ INCORRECT - provoque InvalidStateError
await runtime.store.put(namespace, key, value)  # Sync dans async!
```

### Redis Serialization (CRITIQUE)

```python
# ✅ CORRECT
await redis.setex(key, ttl, json.dumps(data))
cached = json.loads(await redis.get(key)) if await redis.get(key) else None

# ❌ INCORRECT - Redis n'accepte pas les dicts
await redis.setex(key, ttl, data)  # DataError!
```

---

## PARTIE 4 : Checklist de Validation

### Avant de Commencer

- [ ] Le domain n'existe pas déjà (vérifier `domain_taxonomy.py`)
- [ ] Le nom suit la convention : `{domain}_agent`
- [ ] Le type de connecteur est identifié (OAuth/API Key/Internal)

### Après Création Domain Taxonomy

- [ ] `name` correspond au préfixe de l'agent (`emails` → `emails_agent`)
- [ ] `keywords` exhaustifs (20+ mots FR+EN)
- [ ] `agent_names` contient le bon nom d'agent
- [ ] `is_routable=False` si domain technique
- [ ] `priority` appropriée (1-10)

### Après Création Agent Manifest

- [ ] Défini dans `catalogue_loader.py`, PAS dans `catalogue_manifests.py`
- [ ] `name` format `{domain}_agent`
- [ ] `tools` liste tous les tools (noms exacts)
- [ ] Enregistré avec `registry.register_agent_manifest()`

### Après Création Tool Manifests

- [ ] `name` format `{action}_{domain}_tool`
- [ ] `agent` correspond au nom de l'agent
- [ ] `semantic_keywords` exhaustifs (20-35 phrases)
- [ ] `tool_category` correspond à l'action (search, list, create, etc.)
- [ ] `parameters` avec tous les `ParameterSchema`
- [ ] `outputs` avec tous les `OutputFieldSchema`
- [ ] `permissions` avec `required_scopes` et `hitl_required`
- [ ] Enregistré avec `registry.register_tool_manifest()`

### Après Création Tool Implementation

- [ ] Import ajouté dans `_register_tool_instances()`
- [ ] `registry.register_tool_instance()` appelé
- [ ] Gestion d'erreurs appropriée
- [ ] Logging avec structlog
- [ ] Metrics Prometheus si applicable

### Après Intent Anchors (si applicable)

- [ ] Anchors ajoutés pour nouveau type d'intent
- [ ] 5-15 anchors par sous-catégorie
- [ ] Phrases naturelles en anglais
- [ ] Distincts des autres intents

### Tests

- [ ] Tests unitaires créés
- [ ] Tests d'intégration créés
- [ ] Test manuel via API fonctionne
- [ ] Logs vérifiés (pas de warnings `unknown_domain`)

---

## PARTIE 5 : Erreurs Courantes et Solutions

### Erreur #1 : AgentManifest dans mauvais fichier

**Symptôme** :
```
TypeError: AgentManifest.__init__() got an unexpected keyword argument 'capabilities'
```

**Cause** : AgentManifest défini dans `catalogue_manifests.py` avec paramètres invalides.

**Solution** : Définir AgentManifest UNIQUEMENT dans `catalogue_loader.py`.

---

### Erreur #2 : Domain absent du DOMAIN_REGISTRY

**Symptôme** :
```
WARNING - domain_index_agent_unknown_domain - domain=emails
```

**Cause** : Agent enregistré mais domain non ajouté à `domain_taxonomy.py`.

**Solution** : Ajouter `DomainConfig` dans `DOMAIN_REGISTRY`.

---

### Erreur #3 : Naming incohérent

**Symptôme** : Router détecte `"email"` mais agent s'appelle `"emails_agent"`.

**Cause** : Mismatch entre `domain_taxonomy.py`, `catalogue_loader.py` et router prompt.

**Solution** : Cohérence stricte :
```
Domain name:     emails
Agent name:      emails_agent
DomainConfig:    "emails"
```

---

### Erreur #4 : Redis Serialization

**Symptôme** :
```
redis.exceptions.DataError: Invalid input of type: 'dict'
```

**Solution** :
```python
await redis.setex(key, ttl, json.dumps(data))  # Pas data directement
```

---

### Erreur #5 : AsyncPostgresStore Sync Call

**Symptôme** :
```
InvalidStateError: Synchronous calls to AsyncPostgresStore detected
```

**Solution** :
```python
await store.aput(...)   # PAS store.put()
await store.aget(...)   # PAS store.get()
```

---

### Erreur #6 : Semantic Keywords manquants

**Symptôme** : Tool jamais sélectionné par le planner.

**Cause** : `semantic_keywords` vide ou insuffisant.

**Solution** : Ajouter 20-35 phrases naturelles couvrant toutes les variations.

---

### Erreur #7 : Intent Anchors manquants

**Symptôme** : Intent détecté incorrect (ex: "create" au lieu de "list").

**Cause** : `INTENT_ANCHORS` ne contient pas de phrases pour ce cas.

**Solution** : Ajouter anchors spécifiques dans `semantic_intent_detector.py`.

---

### Erreur #8 : Tool Instance non enregistrée

**Symptôme** :
```
Tool 'my_tool' not found in registry
```

**Cause** : Tool non enregistré dans `_register_tool_instances()`.

**Solution** : Ajouter import + `registry.register_tool_instance()`.

---

### Erreur #9 : Adaptive Replanner détecte empty_results

**Symptôme** : Tool retourne des données mais replanner dit "empty_results".

**Cause** : Le pattern de détection ne reconnaît pas la clé de résultats.

**Solution** : Dans `adaptive_replanner.py`, ajouter la clé dans le pattern :
```python
for key in ["contacts", "emails", "events", "reminders", "items", ...]:
```

Et vérifier la clé de count :
```python
count_value = step_data.get("count") or step_data.get("total") or 0
```

---

## PARTIE 6 : Outils de Débogage

### Vérifier Domain Config

```python
from src.domains.agents.registry.domain_taxonomy import get_domain_config

config = get_domain_config("reminder")
print(config.agent_names if config else "DOMAIN NOT FOUND")
```

### Vérifier Agent Manifest

```python
from src.domains.agents.registry.catalogue_loader import REMINDER_AGENT_MANIFEST

print(REMINDER_AGENT_MANIFEST.name)
print(REMINDER_AGENT_MANIFEST.tools)
```

### Vérifier Tool Manifest

```python
from src.domains.agents.reminders.catalogue_manifests import list_reminders_catalogue_manifest

print(list_reminders_catalogue_manifest.semantic_keywords)
print(list_reminders_catalogue_manifest.tool_category)
```

### Vérifier Intent Detection

```python
from src.domains.agents.services.semantic_intent_detector import (
    SemanticIntentDetector,
    INTENT_ANCHORS
)

# Voir les anchors pour un intent
print(INTENT_ANCHORS["list"])
```

### Logs Docker

```bash
# Voir les logs de détection d'intent
docker logs api 2>&1 | grep "semantic_intent_detected"

# Voir les logs de sélection de tools
docker logs api 2>&1 | grep "semantic_tool_selection"

# Voir les warnings de domain inconnu
docker logs api 2>&1 | grep "unknown_domain"
```

### Script de Validation (Recommandé)

Créer `scripts/validate_domain_consistency.py` :

```python
#!/usr/bin/env python
"""Valide la cohérence entre domain_taxonomy, catalogue_loader, et semantic_intent_detector."""

from src.domains.agents.registry.domain_taxonomy import DOMAIN_REGISTRY
from src.domains.agents.registry.catalogue_loader import (
    CONTACTS_AGENT_MANIFEST,
    EMAILS_AGENT_MANIFEST,
    REMINDER_AGENT_MANIFEST,
    # ... autres manifests
)

def validate():
    errors = []

    # 1. Vérifier que chaque domain a un agent manifest correspondant
    for domain_name, config in DOMAIN_REGISTRY.items():
        for agent_name in config.agent_names:
            # Vérifier que le manifest existe
            # ...

    # 2. Vérifier cohérence naming
    # ...

    return errors

if __name__ == "__main__":
    errors = validate()
    if errors:
        print("ERRORS FOUND:")
        for e in errors:
            print(f"  - {e}")
        exit(1)
    print("All validations passed!")
```

---

## PARTIE 7 : Scopes OAuth Google

### Référence des Scopes par Service

Les scopes OAuth sont définis dans `src/core/constants.py` et importés via les constantes.

#### Gmail (GOOGLE_GMAIL_SCOPES)

```python
from src.core.constants import GOOGLE_GMAIL_SCOPES

# Scopes:
"https://www.googleapis.com/auth/gmail.readonly"   # Lecture emails
"https://www.googleapis.com/auth/gmail.send"       # Envoi emails
"https://www.googleapis.com/auth/gmail.modify"     # Modification (labels, etc.)
```

#### Contacts (GOOGLE_CONTACTS_SCOPES)

```python
from src.core.constants import GOOGLE_CONTACTS_SCOPES

# Scopes:
"https://www.googleapis.com/auth/contacts"                  # Lecture/écriture contacts
"https://www.googleapis.com/auth/contacts.readonly"         # Lecture seule
"https://www.googleapis.com/auth/contacts.other.readonly"   # Autres contacts (suggestions)
```

#### Calendar (GOOGLE_CALENDAR_SCOPES)

```python
from src.core.constants import GOOGLE_CALENDAR_SCOPES

# Scopes:
"https://www.googleapis.com/auth/calendar"          # Accès complet calendrier
"https://www.googleapis.com/auth/calendar.readonly" # Lecture seule
"https://www.googleapis.com/auth/calendar.events"   # Gestion événements
```

#### Drive (GOOGLE_DRIVE_SCOPES)

```python
from src.core.constants import GOOGLE_DRIVE_SCOPES

# Scopes:
"https://www.googleapis.com/auth/drive.readonly"          # Lecture seule
"https://www.googleapis.com/auth/drive.file"              # Fichiers créés par l'app
"https://www.googleapis.com/auth/drive"                   # Accès complet
"https://www.googleapis.com/auth/drive.metadata.readonly" # Métadonnées seulement
```

#### Tasks (GOOGLE_TASKS_SCOPES)

```python
from src.core.constants import GOOGLE_TASKS_SCOPES

# Scopes:
"https://www.googleapis.com/auth/tasks.readonly"  # Lecture seule
"https://www.googleapis.com/auth/tasks"           # Accès complet
```

#### Places (GOOGLE_PLACES_SCOPES)

```python
from src.core.constants import GOOGLE_PLACES_SCOPES

# Scopes:
"openid"                                             # OpenID Connect (OBLIGATOIRE)
"https://www.googleapis.com/auth/userinfo.profile"  # Profil utilisateur
"https://www.googleapis.com/auth/cloud-platform"    # Plateforme cloud
```

> **Note** : L'API Places (New) utilise OAuth avec des scopes minimaux. L'accès est contrôlé par l'activation de l'API dans Google Cloud Console, pas par les scopes OAuth.

### Utilisation dans ToolManifest

```python
from src.core.constants import GOOGLE_GMAIL_SCOPES

search_emails_manifest = ToolManifest(
    # ...
    permissions=PermissionProfile(
        required_scopes=GOOGLE_GMAIL_SCOPES,  # Importer la constante
        hitl_required=False,
        data_classification="CONFIDENTIAL",
    ),
    # ...
)
```

---

## PARTIE 8 : Métriques Prometheus

### Décorateur @track_tool_metrics

Le décorateur `@track_tool_metrics` ajoute automatiquement des métriques Prometheus pour chaque tool.

**Fichier** : `src/infrastructure/observability/decorators.py`

### Usage Direct

```python
from typing import Annotated

from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg, tool

from src.infrastructure.observability.decorators import track_tool_metrics
from src.infrastructure.observability.metrics_agents import (
    agent_tool_duration_seconds,
    agent_tool_invocations,
)

@track_tool_metrics(
    tool_name="list_reminders",
    agent_name="reminder_agent",
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
    log_execution=True,
    log_errors=True,
)
@tool
async def list_reminders_tool(
    runtime: Annotated[ToolRuntime, InjectedToolArg],
) -> str:
    """Liste les rappels."""
    # ...
```

> **Ordre des décorateurs** (de l'extérieur vers l'intérieur) :
> 1. `@track_tool_metrics` - Tracking métriques (extérieur)
> 2. `@tool` - Registration LangChain (intérieur, plus proche de la fonction)

### Usage via @connector_tool (Recommandé)

Le décorateur `@connector_tool` combine automatiquement :
- `@tool` (LangChain)
- `@track_tool_metrics` (métriques)
- `@rate_limit` (limitation)
- `@auto_save_context` (sauvegarde contexte)

**Fichier** : `src/domains/agents/tools/decorators.py`

```python
from src.domains.agents.tools.decorators import connector_tool

@connector_tool(
    name="search_contacts",
    agent_name="contacts_agent",
    context_domain="contacts",
    category="read",  # Rate limit: 20 calls/min
)
async def search_contacts_tool(
    query: str,
    runtime: Annotated[ToolRuntime, InjectedToolArg],
) -> str:
    """Recherche des contacts."""
    # ...
```

### Catégories de Rate Limit

| Catégorie | Rate Limit | Usage |
|-----------|------------|-------|
| `read` | 20 calls/min | search, list, get |
| `write` | 5 calls/min | create, update, delete, send |
| `expensive` | 2 calls/5min | export, bulk operations |

### Presets Disponibles

```python
from src.domains.agents.tools.decorators import (
    connector_tool,  # Full control
    read_tool,       # Preset for read operations
    write_tool,      # Preset for write operations
    expensive_tool,  # Preset for expensive operations
)

# Preset read (20 calls/min)
@read_tool(
    name="search_contacts",
    agent_name="contacts_agent",
    context_domain="contacts",
)
async def search_contacts_tool(...): ...

# Preset write (5 calls/min, no context save)
@write_tool(
    name="send_email",
    agent_name="emails_agent",
)
async def send_email_tool(...): ...

# Preset expensive (custom rate limit)
@expensive_tool(
    name="export_contacts",
    agent_name="contacts_agent",
    max_calls=1,
    window_seconds=3600,  # 1 call/hour
)
async def export_contacts_tool(...): ...
```

### Métriques Générées

| Métrique | Type | Labels |
|----------|------|--------|
| `agent_tool_duration_seconds` | Histogram | tool_name, agent_name, status |
| `agent_tool_invocations_total` | Counter | tool_name, agent_name, status |

---

## PARTIE 9 : Hot-Reload Development

### Configuration Docker (Recommandé)

**Fichier** : `docker-compose.dev.yml`

```yaml
services:
  api:
    command: uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
    volumes:
      - ./apps/api:/app  # Mount pour hot-reload
```

### Lancement Local

```bash
# Option 1: Via Docker Compose
docker-compose -f docker-compose.dev.yml up api

# Option 2: Directement avec uvicorn
cd apps/api
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# Option 3: Avec debugging (debugpy)
python -m debugpy --listen 0.0.0.0:5678 -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

# Option 4: Via Taskfile
task dev:api
```

### Fichiers Surveillés

Uvicorn avec `--reload` surveille automatiquement :
- Tous les fichiers `.py` dans `src/`
- Les fichiers de configuration `.env`, `.yaml`

### Rechargement Manuel

Si le hot-reload ne détecte pas un changement :

```bash
# Toucher un fichier pour forcer le reload
touch apps/api/src/main.py

# Ou redémarrer le container
docker-compose -f docker-compose.dev.yml restart api
```

### VSCode Configuration

**Fichier** : `.vscode/launch.json`

```json
{
  "configurations": [
    {
      "name": "API Debug",
      "type": "python",
      "request": "attach",
      "connect": {
        "host": "localhost",
        "port": 5678
      },
      "pathMappings": [
        {
          "localRoot": "${workspaceFolder}/apps/api",
          "remoteRoot": "/app"
        }
      ]
    }
  ]
}
```

---

## PARTIE 10 : Exemple Complet - Agent de A à Z

### Objectif

Créer un agent `notes_agent` avec 3 tools :
- `create_note_tool` (create)
- `list_notes_tool` (list)
- `delete_note_tool` (delete)

### Fichier 1 : Domain Taxonomy

**Fichier** : `src/domains/agents/registry/domain_taxonomy.py`

```python
# Ajouter dans DOMAIN_REGISTRY:

"notes": DomainConfig(
    name="notes",
    display_name="Notes",
    description="Create, list, delete personal notes",
    keywords=[
        # French
        "note", "notes", "mémo", "pense-bête",
        "créer note", "nouvelle note", "ajouter note",
        "mes notes", "liste notes", "voir notes",
        "supprimer note", "effacer note",
        # English
        "note", "notes", "memo", "reminder note",
        "create note", "new note", "add note",
        "my notes", "list notes", "show notes",
        "delete note", "remove note",
    ],
    agent_names=["notes_agent"],
    related_domains=[],
    priority=6,
    metadata={
        "provider": "internal",
        "requires_oauth": False,
        "requires_hitl": False,
    },
),
```

### Fichier 2 : Tool Manifests

**Fichier** : `src/domains/agents/notes/catalogue_manifests.py`

```python
"""Catalogue manifests for Notes tools."""

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

# =============================================================================
# create_note_tool
# =============================================================================

create_note_catalogue_manifest = ToolManifest(
    name="create_note_tool",
    agent="notes_agent",
    description="Crée une nouvelle note personnelle.",
    parameters=[
        ParameterSchema(
            name="title",
            type="string",
            required=True,
            description="Titre de la note",
            constraints=[
                ParameterConstraint(kind="min_length", value=1),
                ParameterConstraint(kind="max_length", value=200),
            ],
        ),
        ParameterSchema(
            name="content",
            type="string",
            required=True,
            description="Contenu de la note",
            constraints=[
                ParameterConstraint(kind="min_length", value=1),
            ],
        ),
    ],
    outputs=[
        OutputFieldSchema(path="success", type="boolean", description="Si création réussie"),
        OutputFieldSchema(path="note_id", type="string", description="UUID de la note"),
        OutputFieldSchema(path="message", type="string", description="Confirmation"),
    ],
    cost=CostProfile(est_tokens_in=50, est_tokens_out=100, est_cost_usd=0.0001, est_latency_ms=100),
    permissions=PermissionProfile(required_scopes=[], data_classification="CONFIDENTIAL", hitl_required=False),
    semantic_keywords=[
        # Core patterns
        "create note", "add note", "new note", "write note",
        "create a note", "add a note", "make a note",
        # Variations
        "save note", "store note", "jot down",
        "take a note", "note this", "remember this",
        "create memo", "add memo", "new memo",
    ],
    display=DisplayMetadata(emoji="📝", i18n_key="create_note", visible=True, category="tool"),
    tool_category="create",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)

# =============================================================================
# list_notes_tool
# =============================================================================

list_notes_catalogue_manifest = ToolManifest(
    name="list_notes_tool",
    agent="notes_agent",
    description="Liste toutes les notes de l'utilisateur.",
    parameters=[],
    outputs=[
        OutputFieldSchema(path="success", type="boolean", description="Si requête réussie"),
        OutputFieldSchema(path="notes", type="array", description="Liste des notes"),
        OutputFieldSchema(path="notes[].id", type="string", description="UUID"),
        OutputFieldSchema(path="notes[].title", type="string", description="Titre"),
        OutputFieldSchema(path="total", type="integer", description="Nombre total"),
    ],
    cost=CostProfile(est_tokens_in=30, est_tokens_out=200, est_cost_usd=0.0001, est_latency_ms=100),
    permissions=PermissionProfile(required_scopes=[], data_classification="CONFIDENTIAL", hitl_required=False),
    semantic_keywords=[
        # Core patterns
        "list notes", "show notes", "my notes", "all notes",
        "display notes", "view notes", "get notes",
        # Variations
        "show my notes", "list my notes", "see notes",
        "what notes", "check notes", "any notes",
    ],
    display=DisplayMetadata(emoji="📋", i18n_key="list_notes", visible=True, category="tool"),
    tool_category="list",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)

# =============================================================================
# delete_note_tool
# =============================================================================

delete_note_catalogue_manifest = ToolManifest(
    name="delete_note_tool",
    agent="notes_agent",
    description="Supprime une note par son ID.",
    parameters=[
        ParameterSchema(
            name="note_id",
            type="string",
            required=True,
            description="UUID de la note à supprimer",
            constraints=[ParameterConstraint(kind="min_length", value=1)],
        ),
    ],
    outputs=[
        OutputFieldSchema(path="success", type="boolean", description="Si suppression réussie"),
        OutputFieldSchema(path="message", type="string", description="Confirmation"),
    ],
    cost=CostProfile(est_tokens_in=30, est_tokens_out=50, est_cost_usd=0.0001, est_latency_ms=100),
    permissions=PermissionProfile(required_scopes=[], data_classification="CONFIDENTIAL", hitl_required=False),
    semantic_keywords=[
        # Core patterns
        "delete note", "remove note", "erase note",
        # Variations
        "delete this note", "remove this note",
        "delete my note", "trash note",
    ],
    display=DisplayMetadata(emoji="🗑️", i18n_key="delete_note", visible=True, category="tool"),
    tool_category="delete",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)

__all__ = [
    "create_note_catalogue_manifest",
    "list_notes_catalogue_manifest",
    "delete_note_catalogue_manifest",
]
```

### Fichier 3 : Tool Implementation

**Fichier** : `src/domains/agents/tools/notes_tools.py`

```python
"""Notes tools implementation."""

import json
from typing import Annotated
from uuid import UUID, uuid4

from langchain_core.tools import InjectedToolArg, tool
from langchain.tools import ToolRuntime

from src.domains.agents.dependencies import get_dependencies
from src.domains.agents.tools.runtime_helpers import parse_user_id
from src.infrastructure.observability.decorators import track_tool_metrics
from src.infrastructure.observability.metrics_agents import (
    agent_tool_duration_seconds,
    agent_tool_invocations,
)

# In-memory storage (replace with DB in production)
_notes_store: dict[str, list[dict]] = {}


@track_tool_metrics(
    tool_name="create_note",
    agent_name="notes_agent",
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
@tool
async def create_note_tool(
    title: str,
    content: str,
    runtime: Annotated[ToolRuntime, InjectedToolArg],
) -> str:
    """Crée une nouvelle note personnelle."""
    config = runtime.configurable or {}
    user_id = config.get("user_id")
    if not user_id:
        return json.dumps({"error": "user_id_required"}, ensure_ascii=False)

    note_id = str(uuid4())
    if user_id not in _notes_store:
        _notes_store[user_id] = []

    _notes_store[user_id].append({
        "id": note_id,
        "title": title,
        "content": content,
    })

    return json.dumps({
        "success": True,
        "note_id": note_id,
        "message": f"Note '{title}' créée avec succès.",
    }, ensure_ascii=False)


@track_tool_metrics(
    tool_name="list_notes",
    agent_name="notes_agent",
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
@tool
async def list_notes_tool(
    runtime: Annotated[ToolRuntime, InjectedToolArg],
) -> str:
    """Liste toutes les notes de l'utilisateur."""
    config = runtime.configurable or {}
    user_id = config.get("user_id")
    if not user_id:
        return json.dumps({"error": "user_id_required"}, ensure_ascii=False)

    notes = _notes_store.get(user_id, [])

    return json.dumps({
        "success": True,
        "notes": notes,
        "total": len(notes),
    }, ensure_ascii=False)


@track_tool_metrics(
    tool_name="delete_note",
    agent_name="notes_agent",
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
@tool
async def delete_note_tool(
    note_id: str,
    runtime: Annotated[ToolRuntime, InjectedToolArg],
) -> str:
    """Supprime une note par son ID."""
    config = runtime.configurable or {}
    user_id = config.get("user_id")
    if not user_id:
        return json.dumps({"error": "user_id_required"}, ensure_ascii=False)

    notes = _notes_store.get(user_id, [])
    original_len = len(notes)
    _notes_store[user_id] = [n for n in notes if n["id"] != note_id]

    if len(_notes_store[user_id]) < original_len:
        return json.dumps({
            "success": True,
            "message": "Note supprimée avec succès.",
        }, ensure_ascii=False)
    else:
        return json.dumps({
            "success": False,
            "error": "note_not_found",
            "message": f"Note {note_id} non trouvée.",
        }, ensure_ascii=False)
```

### Fichier 4 : Catalogue Loader (Registration)

**Fichier** : `src/domains/agents/registry/catalogue_loader.py`

```python
# Ajouter les imports en haut de initialize_catalogue():

from src.domains.agents.notes.catalogue_manifests import (
    create_note_catalogue_manifest,
    delete_note_catalogue_manifest,
    list_notes_catalogue_manifest,
)

# Ajouter l'agent manifest (dans initialize_catalogue):

NOTES_AGENT_MANIFEST = AgentManifest(
    name="notes_agent",
    description="Agent de gestion des notes personnelles. Création, liste et suppression.",
    tools=[
        "create_note_tool",
        "list_notes_tool",
        "delete_note_tool",
    ],
    max_parallel_runs=1,
    default_timeout_ms=DEFAULT_TOOL_TIMEOUT_MS,
    prompt_version="v1",
    owner_team="Team AI",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)

# Enregistrer l'agent manifest:
registry.register_agent_manifest(NOTES_AGENT_MANIFEST)

# Enregistrer les tool manifests:
registry.register_tool_manifest(create_note_catalogue_manifest)
registry.register_tool_manifest(list_notes_catalogue_manifest)
registry.register_tool_manifest(delete_note_catalogue_manifest)

# Dans _register_tool_instances():

try:
    from src.domains.agents.tools.notes_tools import (
        create_note_tool,
        delete_note_tool,
        list_notes_tool,
    )

    registry.register_tool_instance("create_note_tool", create_note_tool)
    registry.register_tool_instance("list_notes_tool", list_notes_tool)
    registry.register_tool_instance("delete_note_tool", delete_note_tool)
    registered_count += 3
except ImportError as e:
    failed_imports.append(f"notes_tools: {e}")
```

### Fichier 5 : Intent Anchors (si nécessaire)

Si les intents `create`, `list`, `delete` ne matchent pas bien pour "notes", ajouter dans `semantic_intent_detector.py` :

```python
# Dans INTENT_ANCHORS["create"]:
"create a note",
"add a note",
"new note",
"write a note",

# Dans INTENT_ANCHORS["list"]:
"list my notes",
"show my notes",
"my notes",

# Dans INTENT_ANCHORS["delete"]:
"delete note",
"remove note",
```

### Fichier 6 : Tests

**Fichier** : `tests/agents/notes/test_notes_tools.py`

```python
import pytest
import json
from unittest.mock import MagicMock

from src.domains.agents.tools.notes_tools import (
    create_note_tool,
    list_notes_tool,
    delete_note_tool,
)


@pytest.mark.asyncio
async def test_create_note_success():
    runtime = MagicMock()
    runtime.configurable = {"user_id": "test-user-123"}

    result = await create_note_tool.ainvoke(
        {"title": "Test", "content": "Content"},
        config={"configurable": runtime.configurable}
    )

    data = json.loads(result)
    assert data["success"] is True
    assert "note_id" in data


@pytest.mark.asyncio
async def test_list_notes_success():
    runtime = MagicMock()
    runtime.configurable = {"user_id": "test-user-123"}

    result = await list_notes_tool.ainvoke(
        {},
        config={"configurable": runtime.configurable}
    )

    data = json.loads(result)
    assert data["success"] is True
    assert "notes" in data
    assert "total" in data
```

### Checklist de Vérification

- [x] `domain_taxonomy.py` : DomainConfig ajouté
- [x] `notes/catalogue_manifests.py` : 3 ToolManifests créés
- [x] `notes_tools.py` : 3 tools implémentés avec `@track_tool_metrics`
- [x] `catalogue_loader.py` : AgentManifest + imports + registration
- [x] `semantic_intent_detector.py` : Anchors ajoutés (si nécessaire)
- [x] Tests unitaires créés

---

## PARTIE 11 : Agents MCP Dynamiques

### Principe

Contrairement aux agents statiques (contacts, email, calendar, etc.) qui sont definis en code et charges au demarrage, les **agents MCP** sont crees dynamiquement au runtime a partir des outils decouverts sur des serveurs MCP externes. Chaque serveur MCP genere automatiquement un agent dedie (ex: `mcp_google_flights_agent`) avec son propre `AgentManifest`, sans ecrire une seule ligne de code agent.

### Creation dynamique via `registration.py`

Le point d'entree est `register_mcp_tools()` dans `infrastructure/mcp/registration.py`. Au demarrage de l'application (`main.py` lifespan), le `MCPClientManager` se connecte aux serveurs MCP configures, decouvre leurs outils, puis appelle `register_mcp_tools()` :

```
Startup → MCPClientManager.initialize()
  → list_tools() sur chaque serveur MCP
  → register_mcp_tools(registry, discovered_tools, adapters, ...)
    → Pour chaque serveur :
      1. slugify_mcp_server_name(server_name) → domain_slug (ex: "mcp_google_flights")
      2. agent_name = f"{domain_slug}_agent"
      3. auto_generate_server_description() → description pour le routing semantique
      4. Stockage dans _admin_mcp_domains (module-level dict)
      5. Creation d'un AgentManifest avec les noms d'outils du serveur
      6. registry.register_agent_manifest(agent_manifest)
      7. Pour chaque outil :
         - _mcp_tool_to_manifest() → ToolManifest
         - registry.register_tool_manifest() + register_tool_instance()
         - _register_tool_in_central_registry() → tool_registry (pour parallel_executor)
```

### Agents statiques vs agents MCP dynamiques

| Aspect | Agent statique | Agent MCP dynamique |
|--------|----------------|---------------------|
| Definition | Code Python dans `registry/catalogue_loader.py` | Genere automatiquement par `registration.py` |
| Outils | `@tool` + `@track_tool_metrics` decorateurs | `MCPToolAdapter` / `UserMCPToolAdapter` (BaseTool) |
| Manifests | Fichiers `catalogue_manifests.py` par domaine | Generes depuis le JSON Schema MCP (`json_schema_to_parameters()`) |
| Semantic keywords | Definis manuellement dans les manifests | Extraits automatiquement de la description (`build_semantic_keywords_from_description()`) |
| Lifecycle | Charges une fois au demarrage | Admin: charges au demarrage. User: crees a la volee par requete |
| Nommage | `contacts_agent`, `email_agent` | `mcp_google_flights_agent`, `mcp_user_xx_tool_name` |

### Routing semantique et agents MCP

Le routing vers les agents MCP fonctionne de maniere transparente grace a l'injection des domaines MCP dans le query analyzer :

1. **Au demarrage** : `_admin_mcp_domains` (dict `slug → description`) est peuple par `register_mcp_tools()`
2. **Par requete** : `collect_all_mcp_domains()` dans `domain_taxonomy.py` fusionne les domaines admin MCP et user MCP (via `ContextVar`)
3. **Dans le prompt** : Les domaines MCP sont injectes dans le prompt du query analyzer au meme niveau que les domaines statiques
4. **Description auto-generee** : Si le serveur n'a pas de `description` dans sa config, `auto_generate_server_description()` en genere une a partir des descriptions des outils. Un appel LLM optionnel (configure via `MCP_DESCRIPTION_LLM_*`) peut produire une description plus riche lors du `test_connection()`

Le LLM routeur voit donc les domaines MCP comme n'importe quel autre domaine et peut les selectionner naturellement.

### Agents MCP dans le catalogue (SmartCatalogueService)

Le `SmartCatalogueService` filtre les outils par agent/domaine exactement de la meme maniere pour les outils statiques et MCP. Cas speciaux :

- **Outils app-only** (`visibility: ["app"]`) : filtres du catalogue LLM via `is_app_only()` — ils ne sont rendus qu'en iframe
- **Outils `read_me`** : si leur contenu a ete auto-fetche au demarrage, ils sont exclus du catalogue et leur contenu est injecte dans le prompt du planner via `_build_mcp_reference()`
- **Outils user MCP** : charges dans le ContextVar `UserMCPToolsContext` pour isolation par requete

### Fichiers cles

| Fichier | Role |
|---------|------|
| `infrastructure/mcp/registration.py` | Bridge d'enregistrement (AgentRegistry + tool_registry) |
| `infrastructure/mcp/tool_adapter.py` | `MCPToolAdapter` — wrapper BaseTool pour admin MCP |
| `infrastructure/mcp/user_tool_adapter.py` | `UserMCPToolAdapter` — wrapper BaseTool pour user MCP |
| `domains/agents/registry/domain_taxonomy.py` | `collect_all_mcp_domains()`, `slugify_mcp_server_name()` |
| `core/config/mcp.py` | `MCPSettings` — feature flags et limites |

---

## PARTIE 12 : Agents avec Notifications Proactives (Heartbeat)

### Principe

Le systeme **Heartbeat Autonome** utilise un pattern de "pseudo-agents" LLM qui ne sont pas des agents LangGraph classiques : ils n'ont pas de graph, pas de tools, et ne sont pas enregistres dans l'`AgentRegistry`. Leur role est de decider proactivement s'il faut notifier l'utilisateur, puis de generer un message personnalise.

### Pattern ProactiveTask

L'infrastructure proactive (`infrastructure/proactive/`) definit un Protocol `ProactiveTask` que toute notification proactive doit implementer :

```python
class ProactiveTask(Protocol):
    task_type: str

    async def check_eligibility(self, user_id, user_settings, now) -> bool: ...
    async def select_target(self, user_id) -> Any | None: ...
    async def generate_content(self, user_id, target, user_settings) -> ProactiveTaskResult: ...
    async def on_notification_sent(self, user_id, target, result) -> None: ...
```

### Approche deux phases du Heartbeat

Le `HeartbeatProactiveTask` (`domains/heartbeat/proactive_task.py`) implemente ce Protocol avec deux appels LLM distincts :

```
Scheduler Job (APScheduler, periodique)
  → ProactiveTaskRunner.run()
    → Pour chaque utilisateur eligible :
      1. check_eligibility() → verifie heartbeat_enabled + time window
      2. select_target() [Phase 1 — LLM Decision]
         → ContextAggregator.aggregate() : 8 sources en parallele (asyncio.gather)
           (calendrier, meteo, memoires, interets, taches, emails, contacts, historique)
         → get_heartbeat_decision() : appel LLM modele economique (structured output)
           → HeartbeatDecision { action: "notify" | "skip", reason, topic, tone }
         → Si "skip" → return None → runner enregistre "no_target"
      3. generate_content() [Phase 2 — Message Rewrite]
         → generate_heartbeat_message() : appel LLM avec personnalite utilisateur
         → Reecrit le message dans la langue et le ton de l'utilisateur
         → ProactiveTaskResult avec content, tokens, metadata
      4. on_notification_sent()
         → Enregistre HeartbeatNotification (audit trail)
         → Stocke le contexte conversationnel pour references futures
```

### Difference avec les agents classiques

| Aspect | Agent classique (LangGraph) | Heartbeat "agent" LLM |
|--------|---------------------------|----------------------|
| Graph | Oui (LangGraph StateGraph) | Non — appels LLM directs |
| Tools | Oui (BaseTool instances) | Non — ContextAggregator fetch direct |
| Registry | AgentRegistry + catalogue | Aucun — scheduler job direct |
| Declenchement | Requete utilisateur → Router → Planner | APScheduler periodique (cron) |
| Isolation | ContextVar par requete | `get_db_context()` (hors lifecycle FastAPI) |
| Output | UnifiedToolOutput → RegistryItem → HTML cards | ProactiveTaskResult → NotificationDispatcher (SSE + FCM + Telegram) |

### Ajouter un nouveau type de notification proactive

Pour creer un nouveau type (au-dela de Heartbeat et Interests) :

1. Implementer `ProactiveTask` Protocol dans un nouveau fichier `domains/<domaine>/proactive_task.py`
2. Creer un `EligibilityChecker` config (time windows, quotas, cooldowns)
3. Ajouter un scheduler job dans `infrastructure/scheduler/`
4. Le `ProactiveTaskRunner` orchestre automatiquement le flow

### Fichiers cles

| Fichier | Role |
|---------|------|
| `infrastructure/proactive/base.py` | `ProactiveTask` Protocol, `ProactiveTaskResult` |
| `infrastructure/proactive/runner.py` | `ProactiveTaskRunner` — orchestration batch |
| `domains/heartbeat/proactive_task.py` | `HeartbeatProactiveTask` implementation |
| `domains/heartbeat/context_aggregator.py` | `ContextAggregator` — fetch multi-sources parallele |
| `domains/heartbeat/prompts.py` | Prompts LLM decision + message |
| `domains/heartbeat/schemas.py` | `HeartbeatDecision`, `HeartbeatTarget` |

---

## References

### Documentation Interne

- [ARCHITECTURE.md](../ARCHITECTURE.md) - Architecture globale
- [GRAPH_AND_AGENTS_ARCHITECTURE.md](../technical/GRAPH_AND_AGENTS_ARCHITECTURE.md) - Systeme multi-agents
- [TOOLS.md](../technical/TOOLS.md) - Systeme d'outils
- [MCP_INTEGRATION.md](../technical/MCP_INTEGRATION.md) - Integration MCP (admin + per-user + OAuth)
- [HEARTBEAT_AUTONOME.md](../technical/HEARTBEAT_AUTONOME.md) - Heartbeat autonome (notifications proactives)
- [CHANNELS_INTEGRATION.md](../technical/CHANNELS_INTEGRATION.md) - Integration multi-canal (Telegram)

### Fichiers de Référence

| Composant | Fichier |
|-----------|---------|
| Domain Taxonomy | `src/domains/agents/registry/domain_taxonomy.py` |
| Catalogue Schemas | `src/domains/agents/registry/catalogue.py` |
| Catalogue Loader | `src/domains/agents/registry/catalogue_loader.py` |
| Intent Detector | `src/domains/agents/services/semantic_intent_detector.py` |
| Base Tools | `src/domains/agents/tools/base.py` |

### Exemples Concrets

| Domain | Agent Manifest | Tool Manifests | Tools |
|--------|---------------|----------------|-------|
| Contacts | `catalogue_loader.py:45` | `google_contacts/catalogue_manifests.py` | `google_contacts_tools.py` |
| Emails | `catalogue_loader.py:98` | `emails/catalogue_manifests.py` | `emails_tools.py` |
| Reminders | `reminders/catalogue_manifests.py:26` | `reminders/catalogue_manifests.py` | `reminder_tools.py` |
| Weather | `catalogue_loader.py:207` | `weather/catalogue_manifests.py` | `weather_tools.py` |

---

**GUIDE_AGENT_CREATION.md** - Version 2.3 - 2026-03-08

*Guide Exhaustif pour la Creation d'Agents, Tools et Connecteurs - LIA*

**Historique des versions :**
- v2.3 (2026-03-08) : Ajout Agents MCP Dynamiques (PARTIE 11) et Agents Notifications Proactives / Heartbeat (PARTIE 12)
- v2.1 (2025-12-28) : Ajout Scopes OAuth Google, Metriques Prometheus, Hot-reload, Exemple complet Notes Agent
- v2.0 (2025-12-28) : Refonte complete avec patterns consolides (Gmail, Reminders, corrections semantiques)
