# ADR-011: Utility Tools vs Connector Tools Pattern

**Status**: ✅ ACCEPTED (2025-12-21)
**Deciders**: Équipe architecture LIA
**Technical Story**: Question architecture - Organisation des outils utilitaires

---

## Context and Problem Statement

Le projet LIA dispose de deux catégories de tools :

1. **Connector Tools** : Interagissent avec des services externes (Gmail, Google Contacts, OpenWeatherMap, etc.)
2. **Utility Tools** : Opèrent sur des données internes (contexte, registre, mémoire)

**Question soulevée** : Faut-il créer un "Connecteur Technique Utilitaire" pour regrouper les outils utilitaires à l'instar des connecteurs fonctionnels ?

**Outils utilitaires concernés** :

| Fichier | Tools | Fonction |
|---------|-------|----------|
| `context_tools.py` | `resolve_reference`, `list_active_domains`, `set_current_item`, `get_context_state`, `get_context_list` | Résolution références contextuelles |
| `entity_resolution_tool.py` | `resolve_entity_for_action` | Résolution entités avec HITL |
| `local_query_tool.py` | `local_query_engine_tool` | Requêtes déclaratives sur Registry |
| `memory_tools.py` | `memorize`, `recall` | Mémoire long-terme LangMem |

---

## Decision Drivers

### Must-Have (Non-Negotiable):

1. **Cohérence sémantique** : Les abstractions doivent avoir une signification claire
2. **Simplicité** : Ne pas ajouter de complexité sans bénéfice
3. **Conformité architecturale** : Respecter les patterns établis
4. **Maintenabilité** : Faciliter la compréhension pour les futurs développeurs

### Nice-to-Have:

- Organisation physique claire des fichiers
- Découvrabilité des outils par catégorie
- Documentation explicite de la distinction

---

## Considered Options

### Option 1: Créer un "Connecteur Technique Utilitaire"

**Approach** : Ajouter `ConnectorType.UTILITY` dans l'enum et créer une structure de connecteur pour les outils utilitaires.

```python
# ❌ ANTI-PATTERN
class ConnectorType(str, enum.Enum):
    GOOGLE_GMAIL = "google_gmail"
    UTILITY = "utility"  # ← Incohérent

class ResolveReferenceTool(ConnectorTool):
    connector_type = ConnectorType.UTILITY  # ← Pas de service externe
    client_class = ???  # ← Aucun client nécessaire
```

**Pros**:
- ✅ Structure uniforme apparente

**Cons**:
- ❌ **Violation sémantique** : Un `Connector` représente une intégration avec un service EXTERNE
- ❌ **Pas de credentials** : Les connecteurs gèrent des tokens OAuth/API keys - les utilitaires n'en ont pas
- ❌ **Pas de Client** : Les connecteurs ont un `Client` pour encapsuler les appels API - inutile pour opérations locales
- ❌ **Boilerplate inutile** : `ConnectorTool` impose DI, OAuth, client caching - non pertinent pour utilitaires
- ❌ **Confusion architecturale** : Mélange deux concepts distincts

**Verdict**: ❌ REJECTED (violation architecturale)

---

### Option 2: Garder l'Architecture Actuelle avec Documentation ⭐

**Approach** : Conserver la séparation implicite existante (agents virtuels `context_agent`, `query_agent`) et documenter explicitement la distinction.

**Architecture actuelle** :

```
apps/api/src/domains/agents/tools/
├── context_tools.py           # → context_agent (utilitaire)
├── entity_resolution_tool.py  # → context_agent (utilitaire)
├── local_query_tool.py        # → query_agent (utilitaire)
├── memory_tools.py            # → LangMem (utilitaire)
├── google_contacts_tools.py   # → contacts_agent (connecteur)
├── emails_tools.py            # → emails_agent (connecteur)
├── calendar_tools.py          # → calendar_agent (connecteur)
└── ...
```

**Agents virtuels définis** (`constants.py`) :

```python
# Agents "connecteurs" (API externes)
AGENT_CONTACTS = "contacts_agent"
AGENT_EMAILS = "emails_agent"
AGENT_CALENDAR = "calendar_agent"
AGENT_WEATHER = "weather_agent"

# Agents "utilitaires" (opérations locales)
AGENT_QUERY = "query_agent"
# Note: AGENT_CONTEXT devrait être centralisé ici
```

**Pros**:
- ✅ Architecture déjà correcte et fonctionnelle
- ✅ Séparation conceptuelle claire
- ✅ Pas de boilerplate inutile
- ✅ Simplicité maximale

**Cons**:
- ⚠️ Distinction implicite (non documentée)
- ⚠️ `AGENT_CONTEXT` défini localement (pas dans `constants.py`)

**Verdict**: ✅ ACCEPTED (avec amélioration documentation)

---

### Option 3: Créer un Package `tools/utilities/`

**Approach** : Réorganiser physiquement les fichiers pour une distinction visuelle claire.

```
apps/api/src/domains/agents/tools/
├── utilities/                    # Nouveau package
│   ├── __init__.py
│   ├── context_tools.py
│   ├── entity_resolution_tool.py
│   ├── local_query_tool.py
│   └── memory_tools.py
├── connectors/                   # Explicite
│   ├── google_contacts_tools.py
│   ├── emails_tools.py
│   └── ...
```

**Pros**:
- ✅ Clarté visuelle
- ✅ Organisation explicite

**Cons**:
- ⚠️ Refactoring imports (breaking changes potentiels)
- ⚠️ Complexité accrue sans bénéfice fonctionnel

**Verdict**: ⏸️ DEFERRED (peut être fait plus tard si nécessaire)

---

## Decision Outcome

**Chosen option**: "**Option 2: Garder l'Architecture Actuelle avec Documentation**"

**Justification** :

L'architecture actuelle est **correcte et conforme aux bonnes pratiques**. La distinction entre Connector Tools et Utility Tools est implicite mais fonctionnelle. Un "connecteur utilitaire" serait une **violation architecturale** car :

1. **`Connector`** = Intégration service EXTERNE avec credentials chiffrés
2. **Utility Tools** = Opérations LOCALES sans API externe

### Architecture Overview

```mermaid
graph TB
    subgraph "CONNECTOR TOOLS"
        CT[ConnectorTool Base Class]
        CT --> GC[Google Contacts Tools]
        CT --> EM[Emails Tools]
        CT --> CA[Calendar Tools]
        CT --> WE[Weather Tools]

        GC --> API1[Google People API]
        EM --> API2[Gmail API]
        CA --> API3[Google Calendar API]
        WE --> API4[OpenWeatherMap API]
    end

    subgraph "UTILITY TOOLS"
        UT[@tool Decorator]
        UT --> CTX[Context Tools]
        UT --> ER[Entity Resolution]
        UT --> LQ[Local Query Engine]
        UT --> MM[Memory Tools]

        CTX --> ST[LangGraph Store]
        ER --> REG[Data Registry]
        LQ --> REG
        MM --> LM[LangMem Store]
    end

    subgraph "CREDENTIALS"
        CR[Connector Model]
        CR --> OAuth[OAuth Tokens]
        CR --> APIKey[API Keys]
        CR --> Encrypted[AES Encryption]
    end

    CT -.-> CR
    UT -.->|No credentials| NC[N/A]

    style CT fill:#2196F3,stroke:#1565C0,color:#fff
    style UT fill:#4CAF50,stroke:#2E7D32,color:#fff
    style CR fill:#FF9800,stroke:#F57C00,color:#fff
    style NC fill:#9E9E9E,stroke:#616161,color:#fff
```

### Caractéristiques Comparées

| Aspect | Connector Tools | Utility Tools |
|--------|-----------------|---------------|
| **Base Class** | `ConnectorTool[ClientType]` | `@tool` decorator (LangChain) |
| **ConnectorType** | Requis (enum) | Non applicable |
| **Client Class** | Requis (API wrapper) | Non applicable |
| **Credentials** | OAuth/API Key chiffrés | Aucun |
| **Service** | Externe (Google, Weather, etc.) | Interne (Store, Registry) |
| **Rate Limiting** | API quotas externes | Opérations locales |
| **Token Refresh** | Automatique | Non applicable |
| **Agent** | `contacts_agent`, `emails_agent`, etc. | `context_agent`, `query_agent` |

### Implementation Details

**Connector Tool Pattern** (`base.py`) :

```python
class ConnectorTool[ClientType](ABC):
    """Pour intégrations API externes"""
    connector_type: ConnectorType  # Requis
    client_class: type[ClientType]  # Requis

    async def execute(self, runtime: ToolRuntime, **kwargs):
        # 1. Récupérer credentials (OAuth/API Key)
        credentials = await connector_service.get_credentials(...)
        # 2. Créer/récupérer client API
        client = await deps.get_or_create_client(self.client_class, ...)
        # 3. Appeler API externe
        return await self.execute_api_call(client, user_id, **kwargs)
```

**Utility Tool Pattern** (`context_tools.py`, `local_query_tool.py`) :

```python
@tool
async def resolve_reference(
    reference: str,
    runtime: Annotated[ToolRuntime, InjectedToolArg],
    domain: str | None = None,
) -> str:
    """Pour opérations locales - pas d'API externe"""
    # 1. Valider config (user_id, session_id)
    config = validate_runtime_config(runtime, "resolve_reference")
    # 2. Accéder au Store local
    store = config.store
    # 3. Opération locale (pas d'appel API)
    result = resolver.resolve(reference, context_list.items)
    return json.dumps(result)
```

### Consequences

**Positive**:
- ✅ **Architecture préservée** : Pas de violation sémantique
- ✅ **Simplicité** : Pas de boilerplate inutile pour utilitaires
- ✅ **Clarté documentée** : ADR explicite pour futurs développeurs
- ✅ **Évolutivité** : Pattern clair pour nouveaux outils

**Negative**:
- ⚠️ Distinction reste implicite dans le code (mais documentée)

**Risks**:
- ⚠️ Nouveau développeur pourrait créer un "utility connector" par méconnaissance → Mitigé par cet ADR

---

## Améliorations Mineures Identifiées

Bien que l'architecture soit correcte, les points suivants pourraient être harmonisés :

### 1. Centraliser `AGENT_CONTEXT` dans `constants.py`

**Actuel** (`context_tools.py:68`) :
```python
AGENT_CONTEXT = "context_agent"  # Défini localement
```

**Recommandé** (`constants.py`) :
```python
# Agents "utilitaires"
AGENT_CONTEXT = "context_agent"  # ← Centraliser ici
AGENT_QUERY = "query_agent"      # Déjà centralisé
```

### 2. Optionnel : Ajouter `ALL_UTILITY_AGENTS`

```python
# constants.py
ALL_UTILITY_AGENTS = [
    AGENT_CONTEXT,
    AGENT_QUERY,
]

ALL_CONNECTOR_AGENTS = [
    AGENT_CONTACTS,
    AGENT_EMAILS,
    AGENT_CALENDAR,
    # ...
]
```

**Status** : Ces améliorations sont optionnelles et non-bloquantes.

---

## Validation

**Acceptance Criteria**:
- [x] ✅ Aucun "connecteur utilitaire" créé
- [x] ✅ Architecture actuelle préservée
- [x] ✅ ADR documentant la distinction créé
- [ ] 🔄 (Optionnel) `AGENT_CONTEXT` centralisé dans `constants.py`

---

## Related Decisions

- [ADR-009: Config Module Split](ADR-009-Config-Module-Split.md) - Pattern de modularisation sans breaking changes
- [ADR-010: Email Domain Renaming](ADR-010-Email-Domain-Renaming.md) - Abstraction provider dans connecteurs

---

## References

### Internal Documentation
- **Connector Pattern**: `docs/technical/CONNECTORS_PATTERNS.md`
- **Tool Creation Guide**: `docs/guides/GUIDE_TOOL_CREATION.md`
- **Base Classes**: `apps/api/src/domains/agents/tools/base.py`
- **Connector Model**: `apps/api/src/domains/connectors/models.py`

### Source Code
- **Context Tools**: `apps/api/src/domains/agents/tools/context_tools.py`
- **Entity Resolution**: `apps/api/src/domains/agents/tools/entity_resolution_tool.py`
- **Local Query**: `apps/api/src/domains/agents/tools/local_query_tool.py`
- **Memory Tools**: `apps/api/src/domains/agents/tools/memory_tools.py`
- **Constants**: `apps/api/src/domains/agents/constants.py`

---

**Fin de ADR-011** - Utility Tools vs Connector Tools Pattern Decision Record.
