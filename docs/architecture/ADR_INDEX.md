# Architecture Decision Records (ADR) - Index LIA

> **Catalogue des décisions architecturales majeures du projet**
>
> Format: [MADR](https://adr.github.io/madr/) (Markdown Any Decision Records)
> Principe: Documenter les décisions importantes pour maintenir la cohérence architecturale

> [!NOTE]
> **ADR-001 à ADR-006 reconstitués le 2026-07-21.** Ces six ADR fondateurs étaient
> résumés ici mais n'avaient jamais eu de fichier (`git log --diff-filter=A` vide).
> Leurs fichiers ont été recréés sous `docs/architecture/` à partir de ce résumé et
> confirmés contre le code courant ; chacun porte une note de provenance. Les
> décisions restent en vigueur (implémentation parfois évoluée — voir les fichiers).
>
> Deux entrées de la section « ADRs Archivés » (Unit of Work *rejeté*, Workflow-Based
> HITL *déprécié*) n'ont volontairement pas de fichier : le résumé suffit à une
> décision sans implémentation. Leur pointeur `**Fichier**` l'indique explicitement.

---

## Table des Matières

1. [Qu'est-ce qu'un ADR ?](#quest-ce-quun-adr-)
2. [Quand créer un ADR ?](#quand-créer-un-adr-)
3. [Template ADR](#template-adr)
4. [ADRs Actifs](#adrs-actifs)
5. [ADRs Archivés](#adrs-archivés)
6. [Process de Décision](#process-de-décision)

---

## Qu'est-ce qu'un ADR ?

Un **Architecture Decision Record** est un document qui capture une **décision architecturale importante** et son contexte.

### Pourquoi documenter les décisions ?

1. **Mémoire institutionnelle**: Comprendre pourquoi une décision a été prise
2. **Onboarding**: Nouveaux développeurs comprennent l'architecture rapidement
3. **Éviter les régressions**: Ne pas refaire les mêmes erreurs
4. **Débat structuré**: Forcer l'analyse des alternatives

### Principe MADR

**MADR** (Markdown Any Decision Records):
- Format Markdown simple
- Template standardisé
- Versionné avec le code (Git)
- Immuable (une fois accepté, on ne modifie plus → on crée un nouveau ADR)

---

## Quand créer un ADR ?

✅ **Créer un ADR pour**:
- Choix d'architecture majeur (LangGraph vs alternatives)
- Changement de pattern (JWT → BFF)
- Nouvelle intégration (OAuth, Langfuse)
- Décision impactant la performance/coût (message windowing, domain filtering)
- Choix de technology stack (PostgreSQL, Redis, FastAPI)

❌ **Ne PAS créer d'ADR pour**:
- Détails d'implémentation mineurs
- Refactoring sans impact architectural
- Bug fixes
- Changements de configuration

---

## Template ADR

```markdown
# ADR-XXX: [Titre Court]

**Status**: 🎯 PROPOSED | ✅ ACCEPTED | ❌ REJECTED | 🔄 SUPERSEDED | 🗑️ DEPRECATED
**Date**: YYYY-MM-DD
**Deciders**: [Nom équipe/personnes]
**Technical Story**: [Lien vers issue/PR si applicable]

---

## Context and Problem Statement

[Décrivez le contexte et le problème à résoudre]

**Question**: [Question clé à laquelle cette ADR répond]

---

## Decision Drivers

### Must-Have (Non-Negotiable):
1. ...
2. ...

### Nice-to-Have:
- ...

---

## Considered Options

### Option 1: [Nom]
**Approach**: [Description]

**Pros**:
- ✅ ...

**Cons**:
- ❌ ...

**Verdict**: ✅ ACCEPTED | ❌ REJECTED

---

### Option 2: [Nom]
[Même structure]

---

## Decision Outcome

**Chosen option**: "[Nom option choisie]"

**Justification**: [Pourquoi cette option]

### Architecture Overview

[Diagramme Mermaid si pertinent]

### Implementation Details

[Code snippets clés]

### Consequences

**Positive**:
- ✅ ...

**Negative**:
- ❌ ...

**Risks**:
- ⚠️ ...

---

## Validation

**Acceptance Criteria**:
- [ ] Critère 1
- [ ] Critère 2

**Metrics to Track**:
- Métrique 1: [baseline → target]
- Métrique 2: [baseline → target]

---

## Related Decisions

- [ADR-XXX: Titre](link)
- [ADR-YYY: Titre](link)

---

## References

- [Documentation externe]
- [Articles/papers]
- [Code references]
```

---

## ADRs Actifs

### ADR-001: LangGraph pour Orchestration Multi-Agents

**Status**: ✅ ACCEPTED (2025-10-15)
**Fichier**: `docs/architecture/ADR-001-LangGraph-Orchestration.md`

**Décision**: Utiliser **LangGraph** pour orchestrer les agents conversationnels.

**Alternatives considérées**:
- ❌ LangChain only (pas de state management)
- ❌ Custom orchestration (reinventing the wheel)
- ✅ **LangGraph** (state management + cycles + checkpoints)

**Impact**:
- ✅ State persistence via PostgreSQL checkpoints
- ✅ HITL (Human-In-The-Loop) via interrupt pattern
- ✅ Streaming support (SSE)
- ❌ Courbe d'apprentissage LangGraph

**Métriques**:
- Checkpoint save: P95 < 50ms ✅
- Checkpoint load: P95 < 100ms ✅
- State bloat: Moyenne 15KB/conversation ✅

---

### ADR-002: BFF Pattern pour Authentication

**Status**: ✅ ACCEPTED (2025-10-20)
**Fichier**: `docs/architecture/ADR-002-BFF-Pattern-Authentication.md`

**Décision**: Migrer de **JWT tokens** vers **BFF Pattern** (Backend-For-Frontend) avec sessions HTTP-only cookies.

**Problème résolu**:
- ❌ JWT in LocalStorage vulnérable XSS
- ❌ JWT size 90% overhead (user data embedded)
- ❌ JWT revocation impossible (stateless)

**Solution BFF**:
- ✅ HTTP-only cookies (immune XSS)
- ✅ Server-side sessions (Redis)
- ✅ SameSite=Lax (CSRF protection)
- ✅ Instant revocation (delete Redis key)
- ✅ 90% memory reduction (session_id only)

**Métriques**:
- Memory usage: 1.2MB → 120KB (90% reduction) ✅
- Session lookup: P95 < 5ms (Redis) ✅
- Security score: B+ → A (OWASP 2024) ✅

**Migration**: v0.1.0 (JWT) → v0.3.0 (BFF)

---

### ADR-003: Multi-Domain Dynamic Filtering

**Status**: ✅ ACCEPTED (2025-11-09, Finalized 2025-11-11)
**Fichier**: `docs/architecture/ADR-003-Multi-Domain-Dynamic-Filtering.md`

**Décision**: Implémenter **filtrage dynamique par domaine** pour éviter token explosion lors du scaling à 10+ domaines.

**Problème**:
- 3 tools (contacts) → 30+ tools (10 domains) = **10x prompt size**
- $0.01/query → $0.10/query = **10x cost**

**Solution Hybrid Pattern**:
1. Router LLM détecte domaines: `domains: ["contacts", "email"]`
2. Planner charge catalogue filtré: 8 tools au lieu de 30+
3. Fallback to full catalogue si confidence < 0.75

**Impact**:
- ✅ Token reduction: 60-90% (mesurée)
- ✅ Generic architecture (zero code changes pour new domains)
- ✅ Safe (fallback + metrics)

**Métriques**:
- Catalogue size: 30 tools → 5-8 tools (73-83% reduction) ✅
- Cache hit rate: 35% (TTL 5min) ✅
- Low confidence fallback: < 10% ✅

---

### ADR-004: Analytical Reasoning Patterns (Planner v5)

**Status**: ✅ ACCEPTED (2025-11-10)
**Fichier**: `docs/architecture/ADR-004-Analytical-Reasoning-Patterns.md`

**Décision**: Intégrer **Progressive Enrichment + Structured Analysis** dans Planner prompt v5 pour améliorer qualité des plans.

**Problème**:
- Planner v4 générait plans trop simplistes
- Manque de raisonnement analytique
- Pas de décomposition user intent

**Solution v5**:
- **Phase 1**: Analyse user intent (WHAT + WHY)
- **Phase 2**: Décomposition en sub-tasks
- **Phase 3**: Génération ExecutionPlan avec justifications

**Impact**:
- ✅ Plan quality: +25% (mesure subjective via HITL approval rate)
- ✅ Retry success: 80% (up from 60%)
- ❌ Latency: +300ms (acceptable trade-off)

---

### ADR-005: Sequential Fallback Execution

**Status**: ✅ IMPLEMENTED (2025-11-14)
**Fichier**: `docs/architecture/ADR-005-Sequential-Fallback-Execution.md`

**Décision**: Filtrer steps skipped AVANT `asyncio.gather()` pour éviter exécution parallèle des branches conditionnelles.

**Problème**:
- Plan principal ET fallback s'exécutent EN PARALLÈLE
- 2x appels API, 2x tokens, 2x cost
- Comportement non déterministe

**Solution**:
```python
# Filter out skipped steps BEFORE execution
skipped_steps = _identify_skipped_steps(execution_plan, completed_steps)
next_wave_filtered = next_wave - skipped_steps

# Execute FILTERED wave
tasks = [... for step_id in next_wave_filtered]
step_results = await asyncio.gather(*tasks)
```

**Impact**:
- ✅ Cost reduction: 50% sur plans avec fallback
- ✅ Déterminisme: 100% (plus de race conditions)
- ✅ Metrics: `langgraph_plan_steps_skipped_total`

---

### ADR-006: Prevent Unbounded List Operations

**Status**: ✅ IMPLEMENTED (2025-11-14)
**Fichier**: `docs/architecture/ADR-006-Prevent-Unbounded-List-Operations.md`

**Décision**: Ajouter **soft warnings + hard safeguards** pour prévenir `list_contacts()` sans query (450+ results).

**Problème**:
- Planner générait `list_contacts(query=None)` → 450 contacts
- Token explosion (100k+ tokens)
- User frustration ("trop de résultats")

**Solution Multi-Layer**:
1. **Planner Validation**: Soft warning si `list_contacts` sans query
2. **Tool Safeguard**: Hard cap à 50 résultats si no query
3. **Logging**: Warning logs pour debugging

**Impact**:
- ✅ Resource waste: -95% (50 results max vs 450)
- ✅ User satisfaction: Improved (no overwhelming lists)
- ✅ Metrics: `langgraph_plan_validation_warnings_total`

---

### ADR-007: Service Layer Pattern for Node Complexity Reduction

**Status**: ✅ Accepted & Implemented (2025-11-16) — SUPERSEDED par Architecture v3 (Smart Services)
**Fichier**: `docs/architecture/ADR-007-Service-Layer-Pattern-For-Node-Complexity.md`

**Décision**: Extraire la logique des nœuds LangGraph volumineux (router, planner) vers une **couche de services** dédiée pour réduire leur complexité. L'architecture v3 a poussé le pattern plus loin avec les Smart Services (`QueryAnalyzerService`, `SmartPlannerService`, `SmartCatalogueService`) — voir [SMART_SERVICES.md](../technical/SMART_SERVICES.md).

> **Conflit de numérotation résolu (2026-07-21).** Le numéro ADR-007 appartient au
> Service Layer Pattern ci-dessus (fichier réel, référencé par ADR-127). L'entrée
> « Message Windowing Strategy » qui occupait ce numéro n'était pas un ADR mais une
> note technique ; elle est déclassée juste en dessous.

---

### Note technique — Message Windowing Strategy (pas un ADR)

> Anciennement catalogué à tort sous « ADR-007 ». Ce n'est pas une décision
> architecturale distincte mais une **stratégie technique**, documentée dans
> [`MESSAGE_WINDOWING_STRATEGY.md`](../technical/MESSAGE_WINDOWING_STRATEGY.md).
> Conservée ici pour la traçabilité.

**Décision**: message windowing par nœud pour réduire la latence des longues conversations.

**Problème**: conversations > 50 messages → 100k+ tokens de contexte, latence router élevée, coût.

**Solution**: fenêtres de messages par nœud (valeurs à jour dans `MESSAGE_WINDOWING_STRATEGY.md` — router et planner héritent de `DEFAULT_MESSAGE_WINDOW_SIZE`, il n'existe pas de variable dédiée par nœud) + Store pour le contexte business.

**Impact**: latence E2E ~-50 %, coût ~-77 % sur longues conversations, qualité préservée via le Store.

---

### ADR-008: HITL Plan-Level Approval (Phase 8)

**Status**: ✅ IMPLEMENTED (2025-11-09)
**Fichier**: Documenté dans `docs/technical/HITL.md` (Phase 8 section)

**Décision**: Migrer de **tool-level HITL** (mid-execution interrupts) vers **plan-level HITL** (approval AVANT exécution).

**Problème Tool-Level HITL**:
- ❌ Mid-execution interrupts → rollback complexe
- ❌ State corruption (partial execution)
- ❌ UX friction (approuver 3-5 outils séparément)

**Solution Plan-Level**:
1. Planner génère ExecutionPlan
2. Approval Evaluator check strategies (ManifestBased, CostThreshold)
3. Si requires_approval → send plan summary to user
4. User approves/rejects AVANT exécution
5. Clean execution (no mid-execution interrupts)

**Impact**:
- ✅ State cleanliness: 100% (no partial execution)
- ✅ UX: Improved (1 approval vs 3-5)
- ✅ Rollback: Simple (plan not executed yet)
- ✅ Metrics: `hitl_plan_approval_requests_total`

**Strategies**:
- **ManifestBasedStrategy**: Tool manifest `requires_approval=true`
- **CostThresholdStrategy**: Plan cost > €0.10
- **AlwaysApproveStrategy**: Bypass for trusted actions

---

### ADR-009: Configuration Module Split

**Status**: ✅ IMPLEMENTED (2025-11-20) - Updated 2025-12-25
**Fichier**: `docs/architecture/ADR-009-Config-Module-Split.md`

**Décision**: Split du fichier monolithique `config.py` (1782 lignes) en **9 modules thématiques** via multiple inheritance.

**Problème résolu**:
- ❌ Fichier monolithique 1782 lignes (difficulté maintenance)
- ❌ Testabilité limitée (impossible tests unitaires par module)
- ❌ Performance IDE dégradée (autocomplétion lente)
- ❌ Single Responsibility Principle violé (9 responsabilités en 1 classe)

**Solution**:
- ✅ **9 modules**: security, database, observability, llm, agents, connectors, voice, advanced
- ✅ **Multiple inheritance**: Composition dans `Settings` class
- ✅ **Rétrocompatibilité 100%**: Import `from src.core.config import settings` inchangé
- ✅ **Pydantic v2**: Validation et field validators préservés

**Structure**:
```
src/core/config/
├── __init__.py           # Settings (composition)
├── security.py           # OAuth, JWT, session cookies
├── database.py           # PostgreSQL, Redis
├── observability.py      # OTEL, Prometheus, Langfuse
├── llm.py                # LLM providers configs
├── agents.py             # SSE, HITL, Router, Planner, Memory
├── connectors.py         # Google APIs, rate limiting
├── voice.py              # Google Cloud TTS, voice comments
└── advanced.py           # Pricing, i18n, feature flags
```

**Métriques**:
- Taille max fichier: 1782 lignes → 380 lignes (llm.py) ✅
- Fichiers config: 1 → 9 modules ✅
- Tests config: 5 → 17 tests ✅
- Coverage: 45% → 72% (+27 points) ✅
- IDE autocomplete: ~800ms → ~250ms (3× plus rapide) ✅

---

### ADR-010: Email Domain Renaming (Gmail → Emails)

**Status**: ✅ IMPLEMENTED (2025-11-20)
**Fichier**: `docs/architecture/ADR-010-Email-Domain-Renaming.md`

**Décision**: Renommer domaine `gmail/` en `emails/` pour architecture **multi-provider** (Gmail, Outlook, IMAP, Exchange).

**Problème résolu**:
- ❌ Naming "gmail" trop spécifique Google
- ❌ Scalabilité limitée (ajout Outlook/IMAP = renommage massif)
- ❌ Architecture rigide (couplage fort domaine/provider)

**Solution**:
- ✅ **Nom générique**: "emails" fonctionne pour tous providers
- ✅ **Provider abstraction**: `BaseEmailClient` pattern (Strategy)
- ✅ **DDD cohérent**: 1 domaine = 1 bounded context ("emails")
- ✅ **Future-proof**: Ajout providers sans renommage domaine

**Renames**:
- Directory: `src/domains/agents/gmail/` → `emails/`
- Files: `gmail_tools.py` → `emails_tools.py`
- Builder: `gmail_agent_builder.py` → `emails_agent_builder.py`
- Prompts: `gmail_agent_prompt.txt` → `emails_agent_prompt.txt`
- Classes: `GmailHandler` → `EmailsHandler`

**Architecture Future**:
```python
class BaseEmailClient(ABC):
    """Abstract base for email providers"""
    async def list_emails(...): ...

class GoogleEmailClient(BaseEmailClient): ...  # Gmail
class OutlookEmailClient(BaseEmailClient): ... # Outlook (future)
class IMAPEmailClient(BaseEmailClient): ...    # IMAP (future)
```

**Métriques**:
- Fichiers renommés: 18 fichiers ✅
- Tests: 100% pass rate (12/12) ✅
- Breaking changes: 0 (architecture interne) ✅
- Documentation: 90 fichiers à mettre à jour (Phase 3) 🔄

---

### ADR-011: Utility Tools vs Connector Tools Pattern

**Status**: ✅ ACCEPTED (2025-12-21)
**Fichier**: `docs/architecture/ADR-011-Utility-Tools-vs-Connector-Tools.md`

**Décision**: **NE PAS** créer de "connecteur utilitaire" - les outils utilitaires (context_tools, entity_resolution, local_query, memory_tools) restent distincts des connecteurs.

**Problème analysé**:
- Question : Faut-il regrouper les utility tools dans un ConnectorType.UTILITY ?

**Verdict**: ❌ REJECTED (violation architecturale)

**Raisons**:
- ❌ `Connector` = Intégration service EXTERNE avec credentials chiffrés
- ❌ Utility Tools = Opérations LOCALES (Store, Registry, contexte)
- ❌ Pas de Client, pas d'OAuth, pas de credentials pour utilitaires
- ✅ Architecture actuelle correcte avec agents virtuels (context_agent, query_agent)

**Classification**:
| Type | Base Class | Credentials | Service |
|------|------------|-------------|---------|
| Connector Tools | `ConnectorTool[ClientType]` | OAuth/API Key | Externe |
| Utility Tools | `@tool` decorator | Aucun | Interne |

---

### ADR-012: Data Registry & StandardToolOutput Pattern

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Fichier**: `docs/architecture/ADR-012-Data-Registry-StandardToolOutput-Pattern.md`

**Décision**: Implémenter **StandardToolOutput** comme format unifié de sortie des tools avec support Data Registry.

**Problème résolu**:
- ❌ Tools retournaient strings JSON brutes (pas de contexte persistant)
- ❌ Pas de structure pour HITL drafts
- ❌ Response Node sans accès aux items structurés

**Solution StandardToolOutput**:
```python
class StandardToolOutput(BaseModel):
    summary_for_llm: str          # Pour LLM (planner, response)
    data: dict                    # Données structurées
    registry_updates: dict        # Items pour Data Registry
    requires_confirmation: bool   # HITL trigger
    draft_id: str | None         # Pour drafts
    draft_content: dict | None   # Contenu draft
```

**Impact**:
- ✅ Contexte persistant via RegistryItem
- ✅ HITL structuré (drafts)
- ✅ resolve_reference accède aux items
- ✅ Format unifié tous domaines

---

### ADR-013: LangMem Long-Term Memory Architecture

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Fichier**: `docs/architecture/ADR-013-LangMem-Long-Term-Memory.md`

**Décision**: Implémenter mémoire long-terme avec **LangMem** et **profil psychologique** utilisateur.

**Problème résolu**:
- ❌ Amnésie inter-sessions (préférences perdues)
- ❌ Pas de gestion sujets sensibles

**Solution MemorySchema**:
```python
class MemorySchema(BaseModel):
    content: str              # Fait mémorisé
    category: Literal[...]    # preference, personal, relationship, event, pattern, sensitivity
    emotional_weight: int     # -10 (trauma) à +10 (joie)
    trigger_topic: str        # Mot-clé activateur
    usage_nuance: str         # Comment utiliser cette info
    pinned: bool              # Protection contre purge
```

**Features**:
- ✅ Profil psychologique avec poids émotionnel
- ✅ Injection dans system prompt
- ✅ Extraction automatique depuis conversations
- ✅ Purge automatique mémoires obsolètes
- ✅ Protection pinned pour mémoires critiques

---

### ADR-014: ExecutionPlan & Parallel Executor Pattern

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Fichier**: `docs/architecture/ADR-014-ExecutionPlan-Parallel-Executor.md`

**Décision**: Implémenter **ExecutionPlan** (DAG) avec **Parallel Executor** pour exécution parallèle des tools.

**Problème résolu**:
- ❌ Exécution séquentielle lente (5 tools × 500ms = 2.5s)
- ❌ Pas de dépendances inter-tools
- ❌ Pas de fallbacks ni conditions

**Solution ExecutionPlan**:
```python
class ExecutionStep(BaseModel):
    step_id: str
    step_type: StepType  # TOOL, CONDITIONAL, PARALLEL, RESPONSE
    tool_name: str
    parameters: dict     # Avec $steps.X.field références
    depends_on: list[str]
    condition: str       # Jinja2 expression
    on_success: str      # Branch si True
    on_fail: str         # Branch si False
```

**Parallel Executor**:
- ✅ Exécution par waves (topological sort)
- ✅ asyncio.gather pour parallélisme
- ✅ Résolution `$steps.X.field` automatique
- ✅ Conditional branching
- ✅ Fallback steps

---

### ADR-015: ConnectorTool Base Class Pattern

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Fichier**: `docs/architecture/ADR-015-ConnectorTool-Base-Class-Pattern.md`

**Décision**: Implémenter **ConnectorTool[ClientType]** comme base class générique pour tous les tools OAuth/API Key.

**Problème résolu**:
- ❌ Code dupliqué massif (150+ lignes par tool)
- ❌ Gestion OAuth incohérente
- ❌ Rate limiting non uniforme
- ❌ Error handling variable

**Solution Generic Base Class**:
```python
class ConnectorTool[ClientType](BaseTool, ABC):
    connector_type: ConnectorType
    client_class: type[ClientType]

    @abstractmethod
    async def execute_api_call(self, client: ClientType, user_id: str, **kwargs):
        pass
```

**Impact**:
- ✅ Réduction 80% code (150 → 30 lignes par tool)
- ✅ Pattern uniforme tous domaines
- ✅ Token refresh automatique
- ✅ Rate limiting intégré
- ✅ Error handling standardisé

---

### ADR-016: ContextTypeRegistry Pattern

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Fichier**: `docs/architecture/ADR-016-ContextTypeRegistry-Pattern.md`

**Décision**: Implémenter **ContextTypeRegistry** (singleton) pour enregistrer les types de contexte dynamiquement.

**Problème résolu**:
- ❌ resolve_reference avec if/elif pour chaque domaine
- ❌ Couplage fort context_tools ↔ domaines
- ❌ Ajout domaine = modification context_tools.py

**Solution Registry Pattern**:
```python
class ContextTypeDefinition(BaseModel):
    domain_key: str           # "contacts", "events", etc.
    display_name: str         # Pour UI
    id_extractor: Callable    # Extract ID from item
    label_extractor: Callable # Extract display label
    search_fields: list[str]  # Fields for keyword search

@singleton
class ContextTypeRegistry:
    def register(self, definition: ContextTypeDefinition): ...
    def resolve(self, domain: str, reference: str, items: list): ...
```

**Impact**:
- ✅ resolve_reference générique (0 if/elif)
- ✅ Open/Closed Principle respecté
- ✅ Ajout domaine = 5 lignes de registration
- ✅ Auto-discovery via decorators

---

### ADR-017: Rate Limiting Architecture

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Fichier**: `docs/architecture/ADR-017-Rate-Limiting-Architecture.md`

**Décision**: Implémenter **Redis Sliding Window + Local Token Bucket Fallback** pour rate limiting distribué.

**Problème résolu**:
- ❌ Single-instance rate limiting (scaling horizontal)
- ❌ Pas de fallback si Redis down
- ❌ Incohérence entre tools

**Solution Dual-Layer**:
```python
@rate_limit(
    max_calls=20,
    window_seconds=60,
    scope="user",
)
async def search_contacts_tool(...):
    ...
```

**Architecture**:
- ✅ Redis sliding window (Lua script atomic)
- ✅ Local token bucket fallback
- ✅ Per-user isolation
- ✅ 3 catégories (read: 20/min, write: 5/min, expensive: 2/5min)
- ✅ Métriques Prometheus

---

### ADR-018: SSE Streaming Pattern

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Fichier**: `docs/architecture/ADR-018-SSE-Streaming-Pattern.md`

**Décision**: Implémenter **Server-Sent Events (SSE)** pour streaming temps réel des réponses LLM.

**Problème résolu**:
- ❌ Latence perçue (5-10s avant affichage)
- ❌ Pas de feedback progressif
- ❌ HITL interrupts difficiles

**Solution SSE Manager**:
```python
class SSEEventType(str, Enum):
    START = "start"       # Metadata
    CHUNK = "chunk"       # Token LLM
    PLAN = "plan"         # ExecutionPlan
    STEP = "step"         # Step result
    HITL_REQUIRED = "hitl_required"
    END = "end"
    ERROR = "error"
```

**Impact**:
- ✅ Token streaming temps réel
- ✅ 7 event types structurés
- ✅ HITL via événements
- ✅ Reconnection automatique (EventSource)
- ✅ Heartbeat keep-alive

---

### ADR-019: Agent Manifest & Catalogue System

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Fichier**: `docs/architecture/ADR-019-Agent-Manifest-Catalogue-System.md`

**Décision**: Implémenter **AgentManifest** et **ToolManifest** comme système déclaratif de métadonnées pour agents et tools.

**Problème résolu**:
- ❌ Métadonnées tools dispersées (docstrings, hardcoded)
- ❌ Pas de cost profiles centralisés
- ❌ Permission profiles implicites
- ❌ Discovery tools manuelle

**Solution Manifest System**:
```python
class ToolManifest(BaseModel):
    name: str
    domain: str
    operation_type: Literal["read", "write", "search", "action"]
    cost_profile: CostProfile
    permission_profile: PermissionProfile
    requires_approval: bool
```

**Impact**:
- ✅ AgentRegistry singleton avec filtering par domaine
- ✅ Catalogue export JSON pour LLM Planner
- ✅ Auto-registration via decorators
- ✅ Cost-based HITL triggers
- ✅ Schema versioning intégré

---

### ADR-020: Triple-Layer Observability Stack

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Fichier**: `docs/architecture/ADR-020-Observability-Stack.md`

**Décision**: Implémenter **triple-layer observability**: Prometheus (métriques) + OpenTelemetry (traces) + Langfuse (LLM-specific).

**Problème résolu**:
- ❌ Aucun outil unique ne couvre tous les besoins LLM
- ❌ Single point of failure observability
- ❌ Pas de cost tracking LLM

**Solution Triple-Layer**:
- **Layer 1 - Prometheus**: `PrometheusMiddleware`, `llm_tokens_consumed_total`, `llm_cost_total`
- **Layer 2 - OpenTelemetry**: `@trace_node` decorator, OTLP exporter vers Tempo
- **Layer 3 - Langfuse**: `CallbackFactory` singleton, prompt versioning, evaluation scores

**Impact**:
- ✅ Independence layers (continue si un layer down)
- ✅ ~173 Prometheus series (low cardinality)
- ✅ Subgraph hierarchy tracing (depth tracking)
- ✅ Token + USD cost tracking per call

---

### ADR-021: OAuth Token Lifecycle Management

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Fichier**: `docs/architecture/ADR-021-OAuth-Token-Lifecycle-Management.md`

**Décision**: Implémenter **Fernet Encryption + Redis Distributed Lock + Proactive Refresh** pour cycle de vie OAuth.

**Problème résolu**:
- ❌ Tokens lisibles en DB
- ❌ Token expiration mid-request
- ❌ Race conditions refresh parallèles
- ❌ Pas de PKCE (vulnérabilité interception)

**Solution OAuth Lifecycle**:
```python
# Proactive refresh 5 minutes avant expiration
OAUTH_TOKEN_REFRESH_MARGIN_SECONDS = 300

# Redis distributed lock
async with OAuthLock(redis, user_id, connector_type):
    # Double-check pattern
    ...
```

**Impact**:
- ✅ Fernet encryption at rest
- ✅ PKCE flow (OAuth 2.1)
- ✅ Redis SETNX distributed lock
- ✅ Token rotation handling
- ✅ Best-effort revocation on delete

---

### ADR-022: LangGraph State & Checkpointing

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Fichier**: `docs/architecture/ADR-022-LangGraph-State-Checkpointing.md`

**Décision**: Implémenter **PostgreSQL AsyncSaver** avec **MessagesState TypedDict** et custom reducers.

**Problème résolu**:
- ❌ Perte état entre redémarrages
- ❌ Pas de HITL interrupt/resume
- ❌ Message history overflow (tokens)
- ❌ Registry growth unbounded

**Solution State Management**:
```python
class MessagesState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages_with_truncate]
    registry: Annotated[dict[str, RegistryItem], merge_registry]
    current_turn_id: int
    plan_approved: bool | None  # HITL gate
```

**Custom Reducers**:
- `add_messages_with_truncate`: Token-based trimming (o200k_base)
- `merge_registry`: LRU eviction (REGISTRY_MAX_ITEMS)

**Impact**:
- ✅ Persistence via PostgreSQL checkpoints
- ✅ Thread-based isolation (thread_id)
- ✅ HITL interrupt detection
- ✅ InstrumentedAsyncPostgresSaver (metrics)
- ✅ Schema versioning (_schema_version)

---

### ADR-023: Error Handling Strategy

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Fichier**: `docs/architecture/ADR-023-Error-Handling-Strategy.md`

**Décision**: Implémenter **BaseAPIException + ToolResponse + Connector Error Handlers** pattern unifié.

**Problème résolu**:
- ❌ Formats erreur inconsistants
- ❌ Pas de logging automatique
- ❌ Messages non traduits
- ❌ Pas de recovery guidance

**Solution Error Handling**:
```python
class ToolResponse(BaseModel):
    success: bool
    data: dict | None
    error: str | None
    message: str | None

class BaseAPIException(HTTPException):
    # Auto-logging structuré
    # Auto-Prometheus metrics
```

**Error Handlers**:
- `handle_oauth_error`: Invalidate connector, prompt reconnect
- `handle_rate_limit_error`: Retry-After header
- `retry_with_exponential_backoff`: 3 attempts, 2-10s

**Impact**:
- ✅ ToolResponse unified format
- ✅ BaseAPIException hierarchy (401, 403, 404, 503)
- ✅ SSEErrorMessages i18n (6 langues)
- ✅ ErrorCategory/Severity/RecoveryAction enums
- ✅ OWASP enumeration prevention

---

### ADR-024: Internationalization (i18n) Architecture

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Fichier**: `docs/architecture/ADR-024-i18n-Architecture.md`

**Décision**: Implémenter **dual i18n system**: i18next (React/JSON) + gettext (Python/PO) avec French fallback.

**Problème résolu**:
- ❌ Interface non traduite
- ❌ Messages erreur API en anglais only
- ❌ Pas de fallback structuré
- ❌ Pas d'URL SEO multilingues

**Solution i18n**:
```
Frontend: i18next + locales/{lng}/translation.json
Backend: gettext + locales/{lng}/LC_MESSAGES/messages.mo
Fallback: French (default)
```

**Supported Languages**:
| Code | Language |
|------|----------|
| `fr` | French (default) |
| `en` | English |
| `es` | Spanish |
| `de` | German |
| `it` | Italian |
| `zh` | Chinese |

**Impact**:
- ✅ 6 langues complètes
- ✅ URL-based routing (`/en/dashboard`)
- ✅ Accept-Language header parsing
- ✅ Instance caching (i18next + @lru_cache)
- ✅ Date/month localization

---

### ADR-025: Prompt Engineering & Versioning

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Fichier**: `docs/architecture/ADR-025-Prompt-Engineering-Versioning.md`

**Décision**: Implémenter **Python .format() + Filesystem Versioning + LRU Cache** pour gestion des prompts.

**Problème résolu**:
- ❌ Pas de rollback prompts (changements irreversibles)
- ❌ Pas d'A/B testing versions
- ❌ Disk I/O répétitif (prompts lus à chaque requête)

**Solution**:
```python
@lru_cache(maxsize=32)
def load_prompt(name: PromptName, version: PromptVersion = "v1") -> str:
    # Cached filesystem read
    ...
```

**Impact**:
- ✅ A/B Testing via `*_PROMPT_VERSION` env vars
- ✅ LRU cache: 98% réduction disk I/O
- ✅ SHA256 hash validation (tamper detection)
- ✅ Dynamic few-shot loading (~80% token reduction)
- ✅ i18n temporal context (6 langues)

---

### ADR-026: LLM Model Selection Strategy

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Fichier**: `docs/architecture/ADR-026-LLM-Model-Selection-Strategy.md`

**Décision**: Implémenter **Factory Pattern + ProviderAdapter + Middleware Stack** pour sélection LLM multi-provider.

**Problème résolu**:
- ❌ Provider switching = code changes
- ❌ Pas de fallback automatique
- ❌ Configuration dispersée

**Solution**:
```python
def get_llm(llm_type: LLMType) -> BaseChatModel:
    config = get_llm_config_for_agent(llm_type)
    return ProviderAdapter.create_llm(
        provider=config["provider"],  # openai, anthropic, deepseek, ollama
        model=config["model"],
        ...
    )
```

**Impact**:
- ✅ Multi-Provider: OpenAI, Anthropic, DeepSeek, Ollama, Gemini
- ✅ Per-component config (Router=nano, Response=mini)
- ✅ Retry middleware (3 attempts, exp backoff)
- ✅ Fallback middleware (claude → deepseek)
- ✅ Structured output (native + JSON fallback)

---

### ADR-027: Structured Logging (structlog)

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Fichier**: `docs/architecture/ADR-027-Structured-Logging.md`

**Décision**: Implémenter **structlog + stdlib + PII Filter + OTEL Context** pour logging production.

**Problème résolu**:
- ❌ Logs non parsables (Loki/Promtail)
- ❌ Context propagation manquant (request_id, user_id)
- ❌ PII dans logs (GDPR violation)

**Solution**:
```python
shared_processors = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.processors.TimeStamper(fmt="iso"),
    add_opentelemetry_context,  # trace_id, span_id
    add_pii_filter,             # GDPR: field + pattern detection
    structlog.processors.JSONRenderer(),
]
```

**Impact**:
- ✅ JSON output toujours (Loki-ready)
- ✅ Context binding via RequestIDMiddleware
- ✅ PII filtering (email, phone, cards)
- ✅ OTEL trace correlation (trace_id in logs)
- ✅ Per-library log levels

---

### ADR-028: Database Schema Design

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Fichier**: `docs/architecture/ADR-028-Database-Schema-Design.md`

**Décision**: Implémenter **Mixin-Based Models + UUID + Soft Deletes + JSONB** pour schéma PostgreSQL.

**Problème résolu**:
- ❌ Integer PKs (distributed unfriendly)
- ❌ Hard deletes (audit compliance)
- ❌ Timestamps non-UTC (ambiguïté)

**Solution**:
```python
class BaseModel(Base, UUIDMixin, TimestampMixin):
    __abstract__ = True
    # UUID primary key + created_at/updated_at (timezone-aware)

class Conversation(BaseModel):
    deleted_at: Mapped[datetime | None]  # Soft delete pattern
```

**Impact**:
- ✅ UUID primary keys everywhere
- ✅ Timezone-aware timestamps (ISO 8601)
- ✅ Soft delete patterns (deleted_at, is_active)
- ✅ JSONB metadata (scopes, connector_metadata)
- ✅ Immutable audit logs (no updated_at)

---

### ADR-029: Redis Multi-Purpose Architecture

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Fichier**: `docs/architecture/ADR-029-Redis-Multi-Purpose-Architecture.md`

**Décision**: Implémenter **Multi-DB Redis + Lua Scripts + Singleton Connections** pour sessions, cache, rate limiting, locks.

**Problème résolu**:
- ❌ Session/cache pollution (same DB)
- ❌ Rate limiting non-atomic (race conditions)
- ❌ OAuth refresh race conditions

**Solution**:
```python
# Separate DBs
DB 1: Sessions (BFF pattern)
DB 2: Cache (LLM, contacts, rate limiting)

# Atomic rate limiting via Lua
SLIDING_WINDOW_SCRIPT = """
redis.call('ZREMRANGEBYSCORE', key, '-inf', current_time - window_seconds)
local count = redis.call('ZCARD', key)
if count < max_calls then
    redis.call('ZADD', key, current_time, request_id)
    return 1
else
    return 0
end
"""
```

**Impact**:
- ✅ DB isolation (sessions vs cache)
- ✅ Sliding window rate limiting (Lua atomic)
- ✅ SETNX distributed locks (OAuthLock)
- ✅ Single-use OAuth state tokens
- ✅ Cache helpers with TTL

---

### ADR-030: Context Resolution & Follow-up Handling

**Status**: ✅ IMPLEMENTED (2025-12-21) - Updated 2025-12-25
**Fichier**: `docs/architecture/ADR-030-Context-Resolution-Follow-up.md`

**Décision**: Implémenter **Turn-Based Resolution + Regex Patterns + Multi-Level Extraction** pour références contextuelles.

**Update 2025-12-25**: Ajout de l'enrichissement des items avec `_item_type`/`_registry_id` et détection de domaine multi-stratégie (agent_results + fallback _item_type via TYPE_TO_DOMAIN_MAP).

**Problème résolu**:
- ❌ "le deuxième" ne résolvait pas
- ❌ Cross-domain contamination
- ❌ Follow-up questions échouaient

**Solution**:
```python
# Turn type detection
TURN_TYPE_ACTION = "action"
TURN_TYPE_REFERENCE = "reference"  # Contains ordinal/demonstrative refs
TURN_TYPE_CONVERSATIONAL = "conversational"

# Multi-level extraction (never crosses domains)
Strategy 1: registry_updates from agent_results
Strategy 2: Filter by turn_id in RegistryItem.meta
Strategy 3: Filter by domain
Strategy 4: Return empty (safe fallback)
```

**Impact**:
- ✅ Ordinal patterns (6 langues): "le 2ème", "the first", "il terzo"
- ✅ Demonstrative patterns: "celui-ci", "this one"
- ✅ Turn isolation via last_action_turn_id
- ✅ Domain filtering in planner
- ✅ Confidence scoring for resolutions

---

### ADR-031: Testing Strategy for LLM Applications

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Fichier**: `docs/architecture/ADR-031-Testing-Strategy-LLM-Applications.md`

**Décision**: Implémenter **pytest-asyncio + LLM Mocking via ProviderAdapter + Database Isolation** pour tests applications LLM.

**Problème résolu**:
- ❌ Tests LLM non-déterministes
- ❌ Coûts API pour tests
- ❌ Database pollution entre tests

**Solution**:
```python
@pytest.fixture
async def mock_llm_response(monkeypatch):
    async def mock_invoke(self, messages, *args, **kwargs):
        return AIMessage(content=MOCK_RESPONSE)
    monkeypatch.setattr(ChatOpenAI, "ainvoke", mock_invoke)

# Database isolation
@pytest.fixture(scope="session")
def test_database():
    # DROP/CREATE database per session
```

**Impact**:
- ✅ 4000+ tests, 85%+ pass rate
- ✅ LLM mocking via ProviderAdapter patch
- ✅ Factory pattern (UserFactory, ConnectorFactory)
- ✅ Database isolation (DROP/CREATE)
- ✅ pytest markers (unit, integration, e2e)

---

### ADR-032: API Design & Versioning

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Fichier**: `docs/architecture/ADR-032-API-Design-Versioning.md`

**Décision**: Implémenter **FastAPI Domain Routers + Pydantic Schemas + URL Versioning** pour API REST.

**Problème résolu**:
- ❌ Couplage monolithique routes
- ❌ Validation input manuelle
- ❌ Pas de versioning API

**Solution**:
```python
# apps/api/src/main.py
app.include_router(auth_router, prefix="/api/v1/auth")
app.include_router(conversations_router, prefix="/api/v1/conversations")
app.include_router(connectors_router, prefix="/api/v1/connectors")

# Pydantic schemas
class UserRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
```

**Impact**:
- ✅ Domain routers (DDD patterns)
- ✅ Pydantic v2 validation
- ✅ URL versioning (`/api/v1/`)
- ✅ BFF authentication (session cookies)
- ✅ Rate limiting per endpoint

---

### ADR-033: Deployment Architecture

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Fichier**: `docs/architecture/ADR-033-Deployment-Architecture.md`

**Décision**: Implémenter **Multi-Environment Docker Compose + Multi-Stage Builds** pour orchestration services.

**Problème résolu**:
- ❌ Pas de distinction dev/prod
- ❌ Images Docker trop larges
- ❌ Startup order non garanti

**Solution**:
```yaml
# docker-compose.dev.yml (26 services)
# docker-compose.prod.yml (8 services)

services:
  api:
    deploy:
      resources:
        limits: {cpus: "2", memory: 4G}
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
```

**Impact**:
- ✅ Dev (26 services) vs Prod (8 services)
- ✅ Multi-stage Dockerfiles (non-root)
- ✅ Health checks with dependencies
- ✅ Resource limits (Raspberry Pi 5: 4 CPU, 16GB)
- ✅ Multi-platform builds (amd64/arm64)

---

### ADR-034: Security Hardening

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Fichier**: `docs/architecture/ADR-034-Security-Hardening.md`

**Décision**: Implémenter **BFF + Bcrypt + Fernet + Redis Rate Limiting** pour sécurité production.

**Problème résolu**:
- ❌ JWT vulnérable XSS
- ❌ Passwords en clair
- ❌ API keys lisibles
- ❌ Rate limiting absent

**Solution**:
```python
# HTTP-only cookies (XSS protection)
response.set_cookie(
    key=settings.session_cookie_name,
    httponly=True,
    samesite="lax",
)

# Bcrypt password hashing
hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())

# Fernet AES-128 for API keys
encrypted = cipher_suite.encrypt(api_key.encode())
```

**Impact**:
- ✅ BFF pattern (HTTP-only cookies)
- ✅ Bcrypt with automatic salt
- ✅ Fernet AES-128 encryption
- ✅ PKCE for OAuth (RFC 7636)
- ✅ Redis sliding window rate limiting
- ✅ OWASP enumeration prevention

---

### ADR-035: Graceful Degradation

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Fichier**: `docs/architecture/ADR-035-Graceful-Degradation.md`

**Décision**: Implémenter **Circuit Breakers + Retry + Fail-Open + Health Checks** pour résilience production.

**Problème résolu**:
- ❌ Cascade failures (service down → all down)
- ❌ Transient errors non gérés
- ❌ Pas de monitoring dépendances

**Solution**:
```python
class CircuitBreaker:
    CLOSED = "closed"     # Normal
    OPEN = "open"         # Failing, reject
    HALF_OPEN = "half_open"  # Testing recovery

@retry_with_backoff(max_retries=3, backoff_factor=2.0)
async def make_api_call():
    # 2s → 4s → 8s
```

**Impact**:
- ✅ Circuit breaker (3 states)
- ✅ Retry with exponential backoff
- ✅ Model fallback (claude → deepseek)
- ✅ Health endpoint (/health)
- ✅ Fail-open for rate limiting
- ✅ Background task safety

---

### ADR-036: Personality System Architecture

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Fichier**: `docs/architecture/ADR-036-Personality-System-Architecture.md`

**Décision**: Implémenter **Database Models + Prompt Injection + Translation Fallback** pour personnalités LLM.

**Problème résolu**:
- ❌ Ton assistant unique
- ❌ Pas de personnalisation utilisateur
- ❌ Pas de support i18n personnalités

**Solution**:
```python
class Personality(BaseModel):
    code: str              # "enthusiastic", "professor"
    emoji: str             # "🎉", "🎓"
    prompt_instruction: str  # Injected in prompts

# Prompt injection via {personnalite} placeholder
formatted = template.format(personnalite=personality.prompt_instruction)
```

**Impact**:
- ✅ 7 default personalities (normal, enthusiastic, professor, friend, influencer, philosopher, cynic)
- ✅ Per-user selection
- ✅ Translation support (6 languages)
- ✅ Prompt injection via placeholder
- ✅ Fallback chain (user → default → hardcoded)

---

### ADR-037: Semantic Memory Store

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Fichier**: `docs/architecture/ADR-037-Semantic-Memory-Store.md`

**Décision**: Implémenter **LangGraph Store + pgvector + Background Extraction + Emotional State** pour mémoire psychologique.

**Problème résolu**:
- ❌ Pas de mémoire long-terme
- ❌ Pas de gestion sujets sensibles
- ❌ Extraction bloque les réponses

**Solution**:
```python
class MemorySchema(BaseModel):
    content: str                    # Fait en une phrase
    category: MemoryCategoryType    # preference, personal, sensitivity...
    emotional_weight: int           # -10 (trauma) à +10 (joie)
    trigger_topic: str              # Mots-clés activation
    pinned: bool                    # Protection purge

class EmotionalState(Enum):
    COMFORT = "comfort"   # Positif dominant
    DANGER = "danger"     # Sensibilité détectée
    NEUTRAL = "neutral"   # Mode factuel
```

**Impact**:
- ✅ pgvector semantic search (1536 dimensions)
- ✅ Background extraction (fire-and-forget)
- ✅ Emotional state computation
- ✅ Profile injection in prompts
- ✅ GDPR endpoints (export, delete)
- ✅ Retention scoring + auto-purge
- ✅ Pinned memory protection

---

### ADR-038: Frontend Architecture (Next.js App Router)

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Fichier**: `docs/architecture/ADR-038-Frontend-Architecture-NextJS.md`

**Décision**: Implémenter **Next.js 16 App Router + BFF + i18next + Radix UI** pour frontend moderne.

**Problème résolu**:
- ❌ Pas de SSR optimisé
- ❌ Streaming LLM complexe
- ❌ Authentification exposée (tokens localStorage)

**Solution**:
```typescript
// App Router + Server Components
export default async function RootLayout({ children, params }) {
  const { lng } = await params;
  const i18n = await initI18next(lng);
  return <TranslationsProvider>{children}</TranslationsProvider>;
}

// SSE Streaming avec Fetch API
const response = await fetch('/api/v1/agents/chat/stream', {
  credentials: 'include', // BFF pattern
});
```

**Impact**:
- ✅ Next.js 16 App Router avec [lng] routing
- ✅ Server Components pour i18n
- ✅ SSE streaming (Fetch + ReadableStream)
- ✅ BFF authentication (HTTP-only cookies)
- ✅ Radix UI + Tailwind design system
- ✅ Custom hooks (useApiQuery, useChat)

---

### ADR-039: Cost Optimization & Token Management

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Fichier**: `docs/architecture/ADR-039-Cost-Optimization-Token-Management.md`

**Décision**: Implémenter **Tiktoken + Redis Caching + Progressive Degradation** pour optimisation coûts LLM.

**Problème résolu**:
- ❌ Coûts LLM non trackés
- ❌ Appels API redondants
- ❌ Token explosion sur longues conversations

**Solution**:
```python
# Token counting multi-provider
encoding = tiktoken.get_encoding("o200k_base")
tokens = len(encoding.encode(text))

# LLM caching (temperature=0 only)
@cached_llm_call(ttl=300)
async def deterministic_call(...): ...

# Progressive degradation
TOKEN_THRESHOLDS = {
    "SAFE": 80_000,      # Full catalogue
    "WARNING": 100_000,  # Filtered domains
    "CRITICAL": 110_000, # Reduced descriptions
}
```

**Impact**:
- ✅ tiktoken + Anthropic SDK token counting
- ✅ Redis LLM cache (400x faster, 100% cost reduction)
- ✅ Progressive token degradation (4 levels)
- ✅ Cost-based HITL triggers ($1.00 threshold)
- ✅ Prometheus metrics (llm_cost_total)

---

### ADR-040: Database Migration Strategy

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Fichier**: `docs/architecture/ADR-040-Database-Migration-Strategy.md`

**Décision**: Implémenter **Alembic + Sync Migrations + Timestamped Naming** pour migrations PostgreSQL.

**Problème résolu**:
- ❌ App async, migrations bloquantes
- ❌ Pas de rollback support
- ❌ Naming convention incohérente

**Solution**:
```python
# alembic.ini
file_template = %%(year)d_%%(month).2d_%%(day).2d_%%(hour).2d%%(minute).2d-%%(rev)s_%%(slug)s

# env.py - Model registration
from src.domains.auth.models import User
from src.domains.conversations.models import Conversation
# ... all models imported for autogenerate

# Idempotent data migrations
ON CONFLICT (model_name, effective_from) DO NOTHING
```

**Impact**:
- ✅ Timestamped naming (YYYY_MM_DD_HHMM)
- ✅ Full downgrade support (21+ migrations)
- ✅ Sync migrations + async app separation
- ✅ Idempotent data migrations
- ✅ Zero-downtime patterns (server_default)

---

### ADR-041: LangGraph State Schema Evolution

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Fichier**: `docs/architecture/ADR-041-LangGraph-State-Schema-Evolution.md`

**Décision**: Implémenter **Schema Versioning + Migration Functions + Custom Reducers** pour évolution MessagesState.

**Problème résolu**:
- ❌ Breaking changes cassent anciens checkpoints
- ❌ Token explosion sur longues conversations
- ❌ Registry growth unbounded

**Solution**:
```python
class MessagesState(TypedDict):
    _schema_version: str  # "1.0" current
    messages: Annotated[list[BaseMessage], add_messages_with_truncate]
    registry: Annotated[dict[str, RegistryItem], merge_registry]

def migrate_state_to_current(state):
    if state.get("_schema_version") == "0.0":
        state["_schema_version"] = "1.0"
    return state
```

**Impact**:
- ✅ `_schema_version` field tracking
- ✅ Migration functions (v0.0 → v1.0)
- ✅ add_messages_with_truncate (93% token reduction)
- ✅ merge_registry avec LRU eviction
- ✅ validate_state_consistency()
- ✅ InstrumentedAsyncPostgresSaver metrics

---

### ADR-042: Conversation Lifecycle Management

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Fichier**: `docs/architecture/ADR-042-Conversation-Lifecycle-Management.md`

**Décision**: Implémenter **Lazy Creation + Soft Delete + Audit Log + Cascade Cleanup** pour cycle de vie conversations.

**Problème résolu**:
- ❌ Conversations créées inutilement
- ❌ Suppression hard delete (pas d'audit)
- ❌ Données orphelines après reset

**Solution**:
```python
class Conversation(BaseModel):
    user_id: Mapped[UUID] = mapped_column(unique=True)  # 1:1 mapping
    deleted_at: Mapped[datetime | None]  # Soft delete

class ConversationAuditLog(Base):
    action: str  # created, reset, deleted, reactivated
    # Immutable: no updated_at

async def reset_conversation():
    await delete_messages()
    await checkpointer.adelete_thread(thread_id)
    await cleanup_redis_cache()
```

**Impact**:
- ✅ Lazy creation (first message triggers)
- ✅ Soft delete avec deleted_at
- ✅ ConversationAuditLog immutable
- ✅ Memory cleanup scheduler (daily 4 AM)
- ✅ GDPR export/delete endpoints
- ✅ Thread isolation via conversation ID

---

### ADR-043: Subgraph Architecture

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Fichier**: `docs/architecture/ADR-043-Subgraph-Architecture.md`

**Décision**: Implémenter **Supervisor Pattern + Agent Registry + Agent Wrappers** pour architecture LangGraph multi-agents.

**Problème résolu**:
- ❌ Pas d'isolation par domaine
- ❌ Callbacks non propagés aux subgraphs
- ❌ State incohérent entre parent et enfants

**Solution**:
```python
# Agent wrapper avec deep callback propagation
async def agent_wrapper_node(state, config):
    merged_config = {
        **config,
        "callbacks": config.get("callbacks", []),  # Propagate!
        "metadata": {**config.get("metadata", {}), "subgraph": agent_constant},
    }
    return await agent_runnable.ainvoke(state, merged_config)
```

**Impact**:
- ✅ Domain isolation (contacts, emails, calendar, etc.)
- ✅ 100% tokens trackés (vs 35% avant fix)
- ✅ Turn-based result isolation
- ✅ Lazy agent initialization
- ✅ Custom reducers (messages, registry)

---

### ADR-044: Draft & HITL Approval Flow

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Fichier**: `docs/architecture/ADR-044-Draft-HITL-Approval-Flow.md`

**Décision**: Implémenter **Draft Service + Critique Node + Executor Registry** pour pattern HITL actions sensibles.

**Problème résolu**:
- ❌ Actions exécutées sans confirmation
- ❌ Pas de preview avant envoi
- ❌ Pas d'édition possible

**Solution**:
```python
# Draft lifecycle
DraftStatus: PENDING → MODIFIED → CONFIRMED → EXECUTED

# HITL interrupt
decision_data = interrupt(payload)  # Pause for user

# Executor registry
register_executor(DraftType.EMAIL.value, execute_email_draft)
```

**Impact**:
- ✅ Confirm/Edit/Cancel pour actions sensibles
- ✅ 15 types de drafts (email, event, contact, task, file)
- ✅ Immutable draft lifecycle
- ✅ Metrics tracking (created/executed)
- ✅ i18n 6 langues

---

### ADR-045: Dependency Injection Pattern

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Fichier**: `docs/architecture/ADR-045-Dependency-Injection-Pattern.md`

**Décision**: Implémenter **FastAPI Depends() + Generic Repository + Service Layer + UoW** pour injection dépendances.

**Problème résolu**:
- ❌ Dépendances hardcodées
- ❌ Tests difficiles (mocking)
- ❌ Transactions non gérées

**Solution**:
```python
# Dependency chain
async def get_current_superuser_session(
    user: User = Depends(get_current_active_session),
) -> User:
    if not user.is_superuser:
        raise_admin_required(user.id)
    return user

# Generic repository
class BaseRepository[ModelType: DeclarativeBase]:
    async def get_by_id(self, id: UUID) -> ModelType | None: ...
```

**Impact**:
- ✅ Type-safe dependency chains
- ✅ Generic repository pattern
- ✅ Unit of Work avec nested transactions
- ✅ Module-level singletons (Redis, Store)
- ✅ Thread-safe service singletons

---

### ADR-046: Background Job Scheduling

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Fichier**: `docs/architecture/ADR-046-Background-Job-Scheduling.md`

**Décision**: Implémenter **APScheduler AsyncIOScheduler + Fire-and-Forget Pattern** pour jobs background.

**Problème résolu**:
- ❌ Pas de tâches planifiées
- ❌ Extraction mémoire bloquante
- ❌ Currency rates obsolètes

**Solution**:
```python
# APScheduler with lifespan
scheduler = AsyncIOScheduler()
scheduler.add_job(sync_currency_rates, trigger="cron", hour=3, minute=0)
scheduler.add_job(cleanup_memories, trigger="cron", hour=4, minute=0)

# Fire-and-forget (GC-safe)
safe_fire_and_forget(extract_memories_background(...), name="memory_extraction")
```

**Impact**:
- ✅ Currency sync @3AM UTC (audit trail)
- ✅ Memory cleanup @4AM UTC (retention algorithm)
- ✅ Fire-and-forget extraction (non-bloquant)
- ✅ Prometheus metrics (duration, errors)
- ✅ Graceful shutdown via lifespan

---

### ADR-047: Google Workspace Integration

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Fichier**: `docs/architecture/ADR-047-Google-Workspace-Integration.md`

**Décision**: Implémenter **BaseGoogleClient + Centralized Scopes + Redis Rate Limiting** pour intégration Google Workspace.

**Problème résolu**:
- ❌ OAuth scopes dispersés
- ❌ Token refresh race conditions
- ❌ Rate limiting incohérent

**Solution**:
```python
# Centralized scopes
GOOGLE_GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.send", ...]
GOOGLE_CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar", ...]

# Token refresh with Redis lock
async with OAuthLock(redis, user_id, connector_type):
    # Double-check pattern
    fresh = await get_credentials()
    if still_valid(fresh): return fresh
    return await refresh()
```

**Impact**:
- ✅ 5 services (Gmail, Calendar, Contacts, Drive, Tasks)
- ✅ Centralized OAuth scopes
- ✅ Redis distributed rate limiting (sliding window)
- ✅ Token refresh avec double-check locking
- ✅ Connector invalidation sur 401
- ✅ Client registry auto-discovery

---

### ADR-048: Semantic Tool Router

**Status**: ✅ IMPLEMENTED (2025-12-23)
**Fichier**: `docs/architecture/ADR-048-Semantic-Tool-Router.md`

**Décision**: Implémenter **SemanticToolSelector + OpenAI text-embedding-3-small + Max-Pooling Strategy** pour routing intelligent des tools.

**Problème résolu**:
- ❌ Routing par mots-clés nécessitait maintenance i18n par langue
- ❌ Dilution sémantique avec average-pooling (scores ~0.60)
- ❌ Coût API OpenAI embeddings ($0.02/1M tokens)
- ❌ Latence réseau pour chaque embedding

**Solution**:
```python
# Max-pooling strategy: MAX(sim(query, keyword_i)) per tool
score = max(cosine(query_emb, kw_emb) for kw_emb in tool_keywords)

# Double threshold decision
if score >= 0.70:  # High confidence
    inject_tool_directly()
elif score >= 0.60:  # Medium confidence
    inject_with_uncertainty_flag()
```

**Impact**:
- ✅ Zero i18n maintenance (embeddings multilingues natifs)
- ✅ +48% accuracy (0.90 vs 0.61 baseline OpenAI)
- ✅ OpenAI text-embedding-3-small (1536 dims)
- ✅ Max-pooling évite dilution keywords
- ✅ Double threshold avec uncertainty flags

---

### ADR-049: Local E5 Embeddings

**Status**: ⛔ SUPERSEDED (2026-03-29) — Originally implemented 2025-12-23
**Fichier**: `docs/architecture/ADR-049-local-e5-embeddings.md`

**Décision**: ~~Remplacer OpenAI text-embedding-3-small par intfloat/multilingual-e5-small via sentence-transformers pour embeddings zero-cost.~~

**Superseded**: Migrated back to **OpenAI text-embedding-3-small** (1536 dims) in v1.14.0 for operational simplicity. The local E5 model (470MB, 9s startup, sentence-transformers dependency) was replaced across all subsystems (memory, semantic routing, interests, journals). See `memory_embeddings.py`.

**Historical impact** (no longer active):
- ~~+48% accuracy (0.90 vs 0.61 on Q/A matching)~~
- ~~Zero API cost~~
- ~~Zero network latency (~50ms local)~~
- ~~ARM64 native (Raspberry Pi 5 compatible)~~

---

### ADR-050: Voice Domain TTS Architecture

**Status**: ✅ IMPLEMENTED (2025-12-24)
**Fichier**: `docs/architecture/ADR-050-Voice-Domain-TTS-Architecture.md`

**Décision**: Implémenter la génération vocale avec **Google Cloud TTS Neural2** pour commentaires audio personnalisés.

**Problème résolu**:
- ❌ Engagement limité (texte seul)
- ❌ Pas de support accessibilité audio
- ❌ Personnalité difficile à transmettre via texte
- ❌ Pas adapté aux contextes mains-libres

**Solution**:
```python
class VoiceCommentService:
    """Two-stage pipeline: LLM + TTS streaming."""

    async def stream_voice_comment(
        self, context: str, personality: str, language: str
    ) -> AsyncGenerator[VoiceAudioChunk, None]:
        # 1. LLM generates 4-6 sentence comment
        comment = await self._generate_comment(context, personality)

        # 2. Stream TTS phrase-by-phrase
        for phrase in self._split_sentences(comment):
            audio = await self.tts_client.synthesize(phrase)
            yield VoiceAudioChunk(audio_base64=b64encode(audio))
```

**Impact**:
- ✅ TTFA < 2s (streaming phrase-par-phrase)
- ✅ Voix Neural2 naturelles (50+ langues)
- ✅ Personnalité vocale cohérente avec avatar
- ✅ Opt-in utilisateur (voice_enabled)
- ✅ 12+ métriques Prometheus
- ✅ Coût optimisé (~$210/mois pour 10K users)

---

### ADR-051: Reminder & Notification System

**Status**: ✅ IMPLEMENTED (2025-12-28)
**Fichier**: `docs/architecture/ADR-051-Reminder-Notification-System.md`

**Décision**: Implémenter système de rappels avec **APScheduler @minute + FCM Push + LLM Personalization + FOR UPDATE SKIP LOCKED**.

**Problème résolu**:
- ❌ Pas de rappels programmés
- ❌ Pas de notifications push
- ❌ Messages rappel génériques (pas personnalisés)
- ❌ Concurrence multi-worker non gérée

**Solution**:
```python
# APScheduler job @every minute
async def process_pending_reminders():
    # 1. Lock with FOR UPDATE SKIP LOCKED (concurrency-safe)
    reminders = await repo.get_and_lock_pending_reminders(limit=100)

    for reminder in reminders:
        # 2. Load user context + personality + memories
        context = await load_user_context(reminder.user_id)
        memories = await get_relevant_memories(reminder.content)

        # 3. Generate personalized message via LLM
        message = await generate_reminder_message(reminder, context, memories)

        # 4. Send FCM push notification
        await fcm_service.send_reminder_notification(reminder.user_id, message)

        # 5. DELETE reminder (one-shot behavior)
        await repo.delete(reminder)
```

**Impact**:
- ✅ Timezone conversion (user local → UTC storage)
- ✅ FOR UPDATE SKIP LOCKED for multi-worker concurrency
- ✅ LLM personalized messages with personality + memories
- ✅ FCM push notifications (Android, iOS, Web)
- ✅ One-shot behavior (no accumulation)
- ✅ Retry logic with MAX_RETRIES=3
- ✅ SSE real-time via Redis Pub/Sub
- ✅ Natural language cancel ("annule le prochain rappel")
- ✅ Token tracking per reminder

---

### ADR-052: Union Validation Strategy for AgentResult.data

**Status**: ✅ ACCEPTED (2026-01-24)
**Fichier**: `docs/architecture/ADR-052-Union-Validation-Strategy-AgentResult.md`

**Décision**: Utiliser **`extra="forbid"`** sur la base class `AgentResultData` pour protéger contre la coercion silencieuse des Union types Pydantic v2.

**Problème résolu**:
- ❌ Pydantic v2 essaie chaque type Union dans l'ordre
- ❌ Si tous les champs ont des defaults, n'importe quel dict peut matcher
- ❌ Risque de perte silencieuse de données

**Solution**:
```python
class AgentResultData(BaseModel):
    """Base class with extra='forbid' protection."""
    model_config = ConfigDict(extra="forbid")
```

**Alternatives considérées**:
- ❌ Discriminated Union (`result_type` discriminant) - ROI insuffisant
- ❌ Nested Unions par domaine - Complexité accrue

**Impact**:
- ✅ Zero migration (protection déjà en place)
- ✅ Héritage automatique pour classes dérivées
- ⚠️ Pattern implicite (dépend de l'héritage)

**Conditions de reconsidération**:
- Ajout de ≥5 nouveaux types `*ResultData`
- Bug de désérialisation découvert
- Refactoring majeur des schemas

---

### ADR-053: Interest Learning System

**Status**: ✅ IMPLEMENTED (2026-01-27)
**Fichier**: `docs/architecture/ADR-053-Interest-Learning-System.md`

**Décision**: Implémenter un système d'apprentissage automatique des centres d'intérêt utilisateur avec **LLM extraction + Bayesian weighting + Proactive notifications**.

**Problème résolu**:
- ❌ Pas de personnalisation basée sur les intérêts
- ❌ Pas de notifications proactives intelligentes
- ❌ Profil utilisateur statique

**Solution**:
```python
# Fire-and-forget extraction in response_node
safe_fire_and_forget(extract_interests_background(user_id, message))

# Bayesian weight (Beta(2,1) prior)
weight = (PRIOR_ALPHA + positive) / (PRIOR_ALPHA + PRIOR_BETA + positive + negative)
effective_weight = weight * max(0.1, 1.0 - days_since * decay_rate)

# Proactive notifications (max_instances=1 + cooldowns)
scheduler.add_job(process_interest_notifications, trigger="interval", minutes=15, max_instances=1)
```

**Impact**:
- ✅ Extraction automatique via LLM (gpt-4o-mini)
- ✅ Poids Bayesian Beta(2,1) avec decay 1%/jour
- ✅ Deduplication par string similarity (embedding OpenAI text-embedding-3-small prévu phase 2)
- ✅ Notifications proactives FCM + SSE
- ✅ Pattern "transactions autonomes" (pas de FOR UPDATE pour user batch)
- ✅ User feedback (thumbs up/down, block)

---

### ADR-054: Voice Input Architecture

**Status**: ✅ IMPLEMENTED (2026-02-02)
**Fichier**: `docs/architecture/ADR-054-Voice-Input-Architecture.md`

**Décision**: Architecture Voice Input avec STT offline (Sherpa-ONNX Whisper), Wake Word detection, et Push-to-Talk.

---

### ADR-055: RAG Spaces Architecture

**Status**: ✅ IMPLEMENTED (2026-03-14)
**Fichier**: `docs/architecture/ADR-055-RAG-Spaces-Architecture.md`

**Décision**: Implémenter des **espaces de connaissances RAG** avec table dédiée `rag_chunks` (pgvector), **hybrid search** (semantic + BM25), et injection dans le Response Node.

**Problème résolu**:
- ❌ Pas de contexte documentaire personnel dans les conversations
- ❌ `AsyncPostgresStore` incompatible (insufficient schema flexibility)
- ❌ Pas de recherche hybride sur documents utilisateur

**Solution**:
- ✅ Table dédiée `rag_chunks` avec colonne `Vector(1536)` pgvector
- ✅ Hybrid search : `score = α × semantic + (1-α) × BM25`
- ✅ `TrackedOpenAIEmbeddings` pour tracking automatique coûts
- ✅ Pipeline background : extract → chunk → embed → persist
- ✅ Admin reindexation (changement modèle embedding)

**Impact**:
- ✅ Espaces personnels activables/désactivables par utilisateur
- ✅ Formats supportés : PDF, TXT, MD, DOCX
- ✅ Coûts RAG intégrés dans le tracking existant
- ✅ 14 métriques Prometheus + dashboard Grafana dédié

---

### ADR-056: RAG Spaces — Google Drive Folder Sync

**Status**: ✅ IMPLEMENTED (2026-03-17)
**Fichier**: `docs/architecture/ADR-056-RAG-Drive-Sync.md`

**Décision**: Permettre aux utilisateurs de **lier des dossiers Google Drive** à leurs RAG Spaces et de **synchroniser** le contenu via un bouton "Sync Now" (sync manuelle V1).

**Problème résolu**:
- ❌ Upload manuel obligatoire (download Drive → upload RAG)
- ❌ Pas de synchronisation avec les fichiers cloud existants
- ❌ Workflow fastidieux décourageant l'adoption

---

### ADR-057: Personal Journals (Carnets de Bord)

**Status**: ✅ IMPLEMENTED (2026-03-19) — étendu par [ADR-064](#adr-064-journal-analyst-persona-replaces-personality-addon) (analyst persona, 2026-03-25), [ADR-069](#adr-069-gemini-embedding-migration-openai--google) (Gemini dual-vector, 2026-04-09), et **superseded pour la cognition stratifiée par [ADR-079](#adr-079-stratified-journal-consciousness)** (2026-05-06)
**Fichier**: `docs/architecture/ADR-057-Personal-Journals.md`

**Décision**: Implémenter des **carnets de bord thématiques** où l'assistant IA enregistre ses propres réflexions, observations et apprentissages. Gestion autonome du cycle de vie via prompt engineering, recherche sémantique pour l'injection contextuelle dans les prompts response et planner.

**Problème résolu**:
- ❌ L'assistant n'évolue pas — pas de mémoire de ses propres réflexions
- ❌ La personnalité est statique — pas de dimension introspective dynamique
- ❌ Pas de continuité dans la perspective de l'assistant au fil du temps

**Solution**:
- ✅ Domaine DDD complet `src/domains/journals/` (models, repository, service, router, schemas)
- ✅ Double déclencheur : extraction post-conversation (fire-and-forget) + consolidation APScheduler (4h)
- ✅ Injection sémantique OpenAI text-embedding-3-small dans prompts response ET planner (deux requêtes distinctes)
- ✅ Gestion autonome du cycle de vie via prompt engineering (pas de règles hardcodées)
- ✅ Feature flags : `JOURNALS_ENABLED` (système) + toggle utilisateur

**Impact**:
- ✅ 4 thèmes : self-reflection, user observations, ideas & analyses, learnings
- ✅ CRUD complet + export JSON/CSV (GDPR) dans Settings > Features
- ✅ Coûts réels traçés via TrackingContext (tokens in/out + EUR)
- ✅ 35 tests unitaires
- ✅ 13 colonnes ajoutées au modèle User

---

### ADR-058: System RAG Spaces for App Self-Knowledge

**Status**: ✅ IMPLEMENTED (2026-03-19)
**Fichier**: `docs/architecture/ADR-058-System-RAG-Spaces.md`

**Décision**: Ajouter des espaces de connaissances système (FAQ) indexés depuis des fichiers Markdown backend, avec détection `is_app_help_query` et injection conditionnelle dans le prompt de réponse.

**Problème résolu**:
- ❌ L'assistant ne connaît pas ses propres fonctionnalités
- ❌ Les utilisateurs doivent naviguer vers la page FAQ au lieu de poser des questions en conversation
- ❌ Pas de mécanisme pour des connaissances système non-supprimables

**Solution**:
- ✅ `SystemSpaceIndexer` — parse Markdown → embed → store chunks (hash-based staleness)
- ✅ `is_app_help_query` détecté par QueryAnalyzer → RoutingDecider Rule 0 → response
- ✅ App Identity Prompt + System RAG context injectés conditionnellement (lazy loading)
- ✅ 3 endpoints admin + UI section avec badge staleness et bouton reindex

**Impact**:
- ✅ 17 fichiers FAQ Markdown (119+ Q/A) dans `docs/knowledge/`
- ✅ Zero overhead sur les requêtes normales (lazy loading)
- ✅ 3 métriques Prometheus (indexation, retrieval, duration)
- ✅ i18n : 11 clés en 6 langues pour l'admin UI

---

### ADR-059: Browser Control Architecture (Playwright)

**Status**: ✅ IMPLEMENTED (2026-03-19)
**Fichier**: `docs/architecture/ADR-059-Browser-Control.md`

**Décision**: Ajouter un connecteur browser autonome basé sur Playwright pour l'interaction web interactive (navigation, recherche, clic, remplissage de formulaires, extraction de contenu JS-rendered).

**Problème résolu**:
- ❌ web_fetch ne peut pas exécuter JavaScript (contenu dynamique invisible)
- ❌ Pas d'interaction web (recherche, formulaires, navigation multi-page)
- ❌ Pas d'extraction de données depuis les SPAs modernes

**Solution**:
- ✅ `browser_task_tool` — tool autonome avec ReAct loop (create_react_agent)
- ✅ Session pool avec coordination Redis cross-workers
- ✅ Anti-détection (UA Chrome, webdriver supprimé, locale dynamique)
- ✅ Cookie banner auto-dismiss multi-langue
- ✅ Activation via admin connector panel (pas de feature flag .env)

**Impact**:
- ✅ Agent ReAct autonome (navigation multi-étapes sans intervention)
- ✅ Extraction accessibilité via CDP (accessibility tree)
- ✅ Prévention SSRF (réutilise validateur web_fetch)
- ✅ 6 métriques Prometheus (gauges/counters/histograms)
- ✅ 36 tests unitaires

### ADR-060: Per-User Usage Limits

**Status**: ✅ IMPLEMENTED (2026-03-21)
**Fichier**: `docs/architecture/ADR-060-Usage-Limits.md`

**Décision**: Implémenter un système de quotas par utilisateur (tokens, messages, coût) avec enforcement multi-couche et gestion admin en temps réel.

**Problème résolu**:
- ❌ Aucun contrôle de la consommation LLM par utilisateur
- ❌ Risque financier non maîtrisé sur les coûts API
- ❌ Pas de capacité à bloquer un utilisateur abusif

**Solution**:
- ✅ Table `user_usage_limits` (1:1 avec User, null = illimité)
- ✅ 5 layers d'enforcement (router → service → LLM invoke → proactive runner → migration)
- ✅ Cache Redis 60s avec invalidation après chaque message
- ✅ Admin WebSocket temps réel + section dédiée

**Impact**:
- ✅ Contrôle financier par utilisateur (tokens, messages, coût × période/absolu)
- ✅ Kill switch admin instantané (blocage/déblocage)
- ✅ Fail-open (panne infra → utilisateur autorisé)
- ✅ Extensible automatiquement (Layer 2 couvre tout service utilisant invoke_with_instrumentation)
- ✅ 42 tests unitaires

---

### ADR-061: Centralized Component Activation/Deactivation Control

**Status**: ✅ IMPLEMENTED (2026-03-23)
**Fichier**: `docs/architecture/ADR-061-Centralized-Component-Activation.md`

**Décision**: Centraliser le contrôle d'activation/désactivation des composants (MCP, skills, sub-agents) via validation des domaines LLM + ContextVar catalogue pré-filtré.

**Problème résolu**:
- ❌ Un utilisateur désactive un MCP app mais l'outil est quand même exécuté
- ❌ Filtrage dispersé dans 7+ fichiers (chaque consommateur filtre indépendamment)
- ❌ Les domaines LLM ne sont jamais validés contre la liste `available_domains`

**Solution**:
- ✅ Gate-keeper domaine : validation post-LLM dans `query_analyzer_service.py`
- ✅ `request_tool_manifests_ctx` : ContextVar pré-filtré, set once, lu partout
- ✅ API guard : 403 + defense-in-depth pour chemins hors-pipeline (proxy iframe)

**Impact**:
- ✅ Un domaine inéligible ne peut plus traverser le pipeline
- ✅ Ajout d'un nouveau composant toggleable = 1 point de modification (pas 7)
- ✅ Sub-agents héritent automatiquement les restrictions via propagation ContextVar

---

### ADR-062: Agent Initiative Phase + MCP Iterative Sub-Agent

**Status**: ✅ IMPLEMENTED (2026-03-24) — Phase 1 + Phase 2
**Fichier**: `docs/architecture/ADR-062-Agent-Initiative-Phase.md`

**Décision**: Ajouter une phase d'initiative post-exécution (read-only) et un sub-agent ReAct pour les MCP servers nécessitant des interactions multi-étapes.

**Problème résolu**:
- ❌ L'assistant ne peut pas réagir aux résultats d'exécution (ex: email propose un rdv → pas de vérification du calendrier)
- ❌ Les MCP servers complexes (Excalidraw) produisent des résultats incohérents car le planner pré-génère tous les paramètres

**Solution**:
- ✅ `ReactSubAgentRunner` : runner générique pour agents ReAct (factorise browser + MCP)
- ✅ `mcp_server_task_tool` + `_MCPReActWrapper` : interaction MCP itérative avec propagation des MCP App widgets
- ⏳ `initiative_node` : évaluation post-exécution avec actions read-only proactives (Phase 2)

**Impact**:
- ✅ Excalidraw génère des diagrammes cohérents (l'agent lit la doc d'abord)
- ✅ Pattern réutilisable pour tout futur sub-agent ReAct
- ✅ Feature flags (defaut: off) — zero impact sur le comportement existant

---

### ADR-063: Cross-Worker Cache Invalidation via Redis Pub/Sub

**Status**: ✅ IMPLEMENTED (2026-03-24)
**Fichier**: `docs/architecture/ADR-063-Cross-Worker-Cache-Invalidation.md`

**Décision**: Utiliser Redis Pub/Sub pour synchroniser les caches in-memory entre les workers uvicorn. Chaque cache expose `load_*()` (startup/subscriber) et `invalidate_and_reload()` (runtime = load + publish).

**Problème résolu**:
- ❌ Avec `--workers 4`, modifier une config admin ne met à jour que 1 worker sur 4
- ❌ Bug constaté : changement de modèle LLM Initiative ignoré par 75% des requêtes

**Solution**:
- ✅ `src/infrastructure/cache/invalidation.py` : registry + publisher + subscriber centralisés
- ✅ Pattern `load_*()` / `invalidate_and_reload()` sur 4 caches (LLMConfig, Skills, Pricing, GoogleApiPricing)
- ✅ `verify_registry_completeness()` au startup pour détecter les oublis

**Impact**:
- ✅ Toute modification admin est propagée instantanément à tous les workers
- ✅ Pattern documenté et extensible pour les futurs caches

---

### ADR-064: Journal Analyst Persona Replaces Personality Addon

**Status**: ✅ IMPLEMENTED (2026-03-25)
**Fichier**: `docs/architecture/ADR-064-Journal-Analyst-Persona.md`

**Décision**: Remplacer l'injection de la personnalité conversationnelle dans les journaux par un persona analyste fixe optimisé pour la production de directives comportementales actionnables.

**Problème résolu**:
- ❌ La personnalité conversationnelle (ex: `cynic`) contaminait la rédaction → prose littéraire sans valeur opérationnelle
- ❌ 0 `learnings` en prod, taux d'injection <10%, redondance massive

**Solution**:
- ✅ `journal_analyst_persona.txt` : persona analyste fixe, toujours injecté
- ✅ Format directif : WHEN [context] → DO [action] (BECAUSE [observation])
- ✅ Consolidation avec dedup obligatoire en premier pas
- ✅ Taille max réduite de 2000 à 800 chars

**Impact**:
- ✅ Entrées journal actionnables qui améliorent effectivement le planner et le response node
- ✅ Personnalité conversationnelle découplée de l'écriture journal

---

### ADR-065: Legacy Domain Agent LangGraph Nodes — Dead Code Analysis

**Status**: ✅ ACCEPTED (2026-03-26)
**Fichier**: `docs/architecture/ADR-065-Legacy-Domain-Agent-Nodes.md`

**Décision**: Documenter que les 15 domain agent LangGraph nodes (event_agent, contact_agent, etc.) sont du code mort depuis Phase 5.2B (parallel executor) et ne sont jamais invoqués en conditions normales.

**Problème résolu**:
- ❌ Les LLM types "Agents domaine" en admin n'apparaissaient pas dans le debug panel
- ❌ Investigation a révélé que ces LLM ne sont jamais appelés (les outils sont exécutés directement par le `parallel_executor`)
- ❌ ~300 lignes de code mort dans graph.py, orchestrator.py, base_agent_builder.py

**Solution**:
- ✅ ADR documentant l'analyse complète et les preuves (logs Docker, analyse du routing)
- ✅ Identification du chemin mort : Router (binaire) → Planner → ExecutionPlan → parallel_executor (appels outils directs)
- ✅ Recommandation de cleanup futur (Phase 2) avec suppression des nodes et du routing legacy

**Impact**:
- ✅ Clarification architecturale pour les contributeurs
- ✅ Le debug panel montre correctement tous les LLM réellement invoqués
- ✅ Base pour un futur nettoyage du graphe

---

### ADR-066: Memory Storage Migration — LangGraph Store to PostgreSQL Custom

**Status**: ✅ ACCEPTED (2026-03-30)
**Fichier**: `docs/architecture/ADR-066-Memory-PostgreSQL-Migration.md`

**Décision**: Migrer le stockage des memories du LangGraph AsyncPostgresStore vers un modèle SQLAlchemy dédié avec pgvector, aligné sur le pattern journal. Centraliser l'embedding du message utilisateur via un service partagé avec cache text-hash.

**Problème résolu**:
- ❌ 5 embeddings redondants du même message par tour de conversation
- ❌ 3 appels LLM d'extraction sur messages triviaux ("ok", "merci")
- ❌ ~7 500 tokens input par extraction journal (toutes les entries chargées)
- ❌ Memory extraction create-only (pas d'update/delete)
- ❌ Patterns divergents entre memory (LangGraph store) et journal (PostgreSQL)

**Solution**:
- ✅ UserMessageEmbeddingService : 1 embedding centralisé par tour, cache text-hash, filtre trivialité
- ✅ Modèle Memory SQLAlchemy + pgvector (même pattern que JournalEntry)
- ✅ Memory extraction avec create/update/delete (micro-consolidation)
- ✅ Journal extraction avec pre-filtre sémantique (top 10 + 3 récentes)
- ✅ 14 fichiers consommateurs migrés, LangGraph store conservé pour tool context

---

### ADR-067: Account Lifecycle (Active / Deactivated / Deleted / Erased)

**Status**: ✅ ACCEPTED (2026-03-31)
**Fichier**: `docs/architecture/ADR-067-Account-Lifecycle.md`

**Décision**: Implémenter un cycle de vie à 4 états (Actif → Désactivé → Supprimé → Effacé GDPR) avec `deleted_at` timestamp + `is_deleted` property. La suppression purge toutes les données personnelles (22 tables, LangGraph store/checkpoints, Redis, fichiers disque) tout en préservant le row user (email/nom) et l'historique de facturation (token_usage_logs, user_statistics, google_api_usage_logs).

**Problème résolu**:
- ❌ Pas de mécanisme de suppression préservant l'historique de facturation
- ❌ Tâches de fond exécutées pour utilisateurs désactivés (tokens LLM gaspillés)
- ❌ `check_user_allowed()` ne vérifiait pas `is_active` (bypass pour users sans limits)
- ❌ FK `admin_broadcasts.sent_by` sans `ondelete` (bloque le GDPR hard-delete)

**Solution**:
- ✅ `AccountDeletionService` orchestre la purge complète (22 tables + external)
- ✅ `_compute_status()` check `is_active`/`deleted_at` en priorité 0 (avant limits)
- ✅ `check_user_allowed()` check account status AVANT `_has_limit_record()`
- ✅ 7 tâches de fond protégées (defense in depth: SQL filters + centralized check)
- ✅ Précondition : Désactivé avant Supprimé, Supprimé avant Effacé (GDPR)

**Impact**:
- ✅ 5→1 embedding calls par tour
- ✅ 3→0 LLM calls sur message trivial
- ✅ ~67% réduction tokens extraction journal
- ✅ Patterns unifiés memory/journal

---

### ADR-068: Psyche Engine — Dynamic Psychological State

**Status**: ✅ ACCEPTED (2026-04-01)
**Fichier**: `docs/architecture/ADR-068-Psyche-Engine.md`

**Décision**: Implémenter un moteur psychologique multi-couches (ALMA-inspired) pour l'assistant IA: Big Five traits → PAD mood space (14 humeurs) → 22 émotions discrètes → relation 4 stades → drives + auto-efficacité. Self-report via `<psyche_eval/>` tag (0 appel LLM supplémentaire). Engine pur stateless (87 tests unitaires). Feature flag indépendant (`PSYCHE_ENABLED` + `user.psyche_enabled`).

**Problème résolu**:
- ❌ Personnalité statique (simple prompt texte)
- ❌ Conscience émotionnelle limitée (3 états: COMFORT/DANGER/NEUTRAL)
- ❌ Pas d'évolution relationnelle ni de mémoire émotionnelle

**Solution**:
- ✅ Architecture 5 couches (Personality → Mood → Emotions → Relationship → Drives)
- ✅ Espace PAD continu avec decay exponentiel vers baseline personnalité
- ✅ Mood-congruent memory recall (boost mémoire congruente à l'humeur)
- ✅ Inertie émotionnelle, rupture-repair, learning rate adaptatif
- ✅ Palette daltonien-safe (MoodRing), settings complet avec palette légende
- ✅ i18n 6 langues, GDPR cascade, 14 personnalités seedées

**Impact**:
- +65 tokens input + ~25 tokens output par message
- +2ms latence bloquante (DB read + math)
- ~$0.58/mois/utilisateur actif

---

### ADR-069: Gemini Embedding Migration (OpenAI → Google)

**Status**: ✅ ACCEPTED (2026-04-02)
**Fichier**: `docs/architecture/ADR-069-Gemini-Embedding-Migration.md`

**Décision**: Migrer tous les embeddings de OpenAI `text-embedding-3-small` vers Google `gemini-embedding-001` avec task types asymétriques (RETRIEVAL_QUERY/RETRIEVAL_DOCUMENT) et dual-vector (content + keywords séparés).

**Problème résolu**:
- ❌ Biais de langue: textes français non liés scoraient 0.25-0.35 (plancher trop élevé)
- ❌ Discrimination insuffisante: mémoires pertinentes (0.29) vs bruit (0.30) indiscernables
- ❌ Résolution relationnelle cassée ("ma femme" ne résolvait plus son nom complet)
- ❌ Perte de la stratégie multi-vecteurs lors de la migration LangGraph → PostgreSQL

**Solution**:
- ✅ Gemini embedding-001 avec task_type RETRIEVAL_QUERY/RETRIEVAL_DOCUMENT
- ✅ Dual-vector: `embedding` (content) + `keyword_embedding` (trigger_topic/search_hints)
- ✅ Wrapper GeminiRetrievalEmbeddings avec tracking Prometheus + DB billing
- ✅ Singletons dédiés par domaine (memory, journal, interest, RAG)
- ✅ Clé API Google dédiée (Generative Language API)

**Impact**:
- Coût embedding x7.5 ($0.15 vs $0.02 /1M tokens)
- Reindex complet nécessaire (mémoires, journaux, intérêts, RAG)
- Scores cibles à 0.64+ vs bruit à 0.60 (meilleure discrimination)

---

### ADR-070: ReAct Execution Mode

**Status**: ✅ ACCEPTED (2026-04-08)
**Fichier**: `docs/architecture/ADR-070-ReAct-Execution-Mode.md`

**Décision**: Ajouter un mode d'exécution ReAct (Reasoning + Acting) alternatif comme préférence utilisateur, à côté du pipeline existant (Planner → Orchestrator → Response).

**Problème résolu**:
- ❌ Pipeline rigide: impossible d'adapter l'exécution en cours de route
- ❌ Pas de réaction aux résultats inattendus des outils
- ❌ Tâches exploratoires mal servies par un plan fixe

**Solution**:
- ✅ 4 nodes dans le graphe parent: `react_setup` → `react_call_model` ←→ `react_execute_tools` → `react_finalize`
- ✅ HITL via `interrupt()` natif dans `react_execute_tools` (pas de subgraph)
- ✅ Pattern d'idempotence pour re-exécution multi-interrupt
- ✅ LLM type dédié `react_agent` (qwen3.5-plus, thinking medium)
- ✅ Toggle utilisateur sur la page chat (persisté en DB)
- ✅ (Amendement 2026-05-20) Parité HITL des drafts: les outils de mutation (create/update/delete) basculent vers le flux partagé `hitl_dispatch → draft_critique → response` via `pending_draft_critique` au lieu de boucler — confirmation/édition/annulation puis exécution réelle, comme en pipeline
- ✅ (Amendement 2026-05-21) Parité Initiative en ReAct: le chemin nominal `react_finalize` route optionnellement vers `initiative` (nouvelle edge `route_from_react_finalize`, flag `INITIATIVE_REACT_ENABLED` défaut off) — enrichissement proactif cross-domaine identique au pipeline ; la réponse ReAct et les résultats Initiative sont fusionnés (pas de perte)

**Trade-offs**:
- ReAct: 3-10x plus d'appels LLM, mais adaptatif et autonome
- Pipeline: Rapide, économique, mais rigide
- Les deux modes partagent outils, registry et infrastructure HITL

---

### ADR-071: Skill Semantic Identification

**Status**: ✅ ACCEPTED (2026-04-15)
**Fichier**: `docs/architecture/ADR-071-Skill-Semantic-Identification.md`

**Décision**: Unifier l'identification des skills autour d'un seul signal sémantique (`QueryIntelligence.detected_skill_name`) produit par `QueryAnalyzer` depuis la description de chaque skill. Suppression définitive du matching par overlap de domaines et du champ `max_missing_domains`.

**Problème résolu**:
- ❌ Incident prod 2026-04-15: *"Je veux mon briefing quotidien"* → QueryAnalyzer introduit `web_search` comme domaine parasite → overlap insuffisant → bypass refusé → plan incomplet (pas d'emails/tasks/reminders)
- ❌ Dualité structurelle entre matching déterministe (overlap) et non-déterministe (LLM sur description) — deux chemins, deux logiques, deux manières de rater
- ❌ Faux positifs possibles: requête couvrant les mêmes domaines qu'un skill mais d'intention différente

**Solution**:
- ✅ `QueryAnalyzer` voit toutes les skills actives (déterministes + dynamiques) et identifie par description
- ✅ `SkillBypassStrategy.can_handle` = check de présence sur `detected_skill_name` ; `plan` fait le lookup user-scopé et vérifie le contrat (déterministe + active)
- ✅ `_has_potential_skill_match` simplifié à une vérification de présence
- ✅ Isolation utilisateur renforcée: `SkillsCache.get_by_name_for_user` exclusivement dans le hot path (plus de `get_all()`)
- ✅ Suppression de `max_missing_domains`, `SKILLS_EARLY_DETECTION_MAX_MISSING_DOMAINS`, et de la logique d'overlap

**Trade-offs**:
- Plus de filet structurel en cas de raté QueryAnalyzer — on préfère faire remonter les défauts de prompt/description plutôt que de les masquer
- Qualité des descriptions skill devient un contrat critique
- Légère augmentation de tokens QueryAnalyzer (toutes skills exposées)

---

### ADR-072: TCM Two-Keys Simplification

**Status**: ✅ ACCEPTED (2026-04-18)
**Fichier**: `docs/architecture/ADR-072-TCM-Two-Keys-Simplification.md`

**Décision**: Supprimer la clé `details` du Tool Context Manager. Le TCM n'expose plus que 2 clés par domaine : `list` (overwrite) et `current` (item focalisé). Les tools unifiés opt-in explicitement via `UnifiedToolOutput.context_save_mode` ∈ {`LIST`, `CURRENT`, `NONE`}.

**Problème résolu**:
- ❌ Bug 1 : double auto_save (décorateur + parallel_executor) avec pollution du cache `details` car `classify_save_mode` matchait « get » dans `get_events_tool` et retournait DETAILS par défaut
- ❌ Bug 2 : après création/mise à jour HITL, `save_details` cherchait l'item par `primary_id_field="id"` mais le payload portait `event_id` → `save_details_missing_primary_id` warning, `current_item` pointait sur un ancien rdv
- ❌ Bug 3 : après évocation linguistique (`"le premier rdv"`), `ResolvedContext` retournait le bon item mais `current_item` restait sur la dernière valeur posée par une action HITL → `"ce rdv"` suivant ciblait le mauvais item
- ❌ La clé `details` (cache LRU) n'était lue en source primaire par aucun appelant — simple fallback jamais activé en pratique

**Solution**:
- ✅ `ContextSaveMode` réduit à `{LIST, CURRENT, NONE}` ; `classify_save_mode` à 1 règle (explicit wins, défaut LIST)
- ✅ Écriture directe via `set_current_item()` dans `_set_current_item_after_execution` (pas de lookup `primary_id_field`)
- ✅ Flag sentinel `tool_metadata["_tcm_saved"]` posé par le décorateur → `parallel_executor._auto_save_wave_contexts` skip pour éviter le double save
- ✅ `ContextResolutionService._update_current_after_resolution()` : le résolveur écrit `current_item` après toute résolution réussie (N=1 → set, N>1 → clear)
- ✅ Suppression de `save_details`, `get_details`, `ToolContextDetails`, des 2 fallbacks DETAILS dans `calendar_tools` et `parameter_enrichment`
- ✅ Invariant unifié : `current_item` = dernier item **manipulé, recherché, évoqué** par l'utilisateur
- ✅ **Follow-up 2026-04** : `_sync_tcm_after_draft_execution` dispatcher unifié (create→current, update→current+list, delete→remove+clear) + nouvelle méthode `manager.update_item_in_list()` symétrique à `remove_item_from_list()`
- ✅ **Follow-up 2026-04** : unification convention `turn_type` via `utils/turn_type.py` (helpers case-tolerant) + normalisation à l'écriture dans le router
- ✅ **Follow-up 2026-04** : refonte HITL update prompt en 2 blocs `{L_Modifications}` + `{L_Full_post_update}`, labels i18n 6 langues

**Trade-offs**:
- Plus de cache LRU persistant d'items précédemment vus hors search courant — acceptable (aucun usage observé)
- Les clés `"details"` existantes en Postgres sont orphelines (jamais lues/réécrites), nettoyage optionnel

---

### ADR-073: Last-Known Location Persistence for Proactive Weather

**Status**: ✅ ACCEPTED (2026-04-19)
**Fichier**: `docs/architecture/ADR-073-Last-Known-Location-Persistence.md`

**Décision**: Persister côté serveur la géolocalisation navigateur (opt-in, chiffrée Fernet, non historisée) pour que les notifications météo proactives utilisent la position réelle de l'utilisateur en déplacement plutôt que son domicile. Cascade miroir de celle du tool météo conversationnel cas implicite (`browser > home` → `last_known > home`).

**Problème résolu**:
- ❌ Notifs météo du heartbeat toujours basées sur `home_location_encrypted` → faux positifs systématiques quand l'utilisateur voyage
- ❌ Asymétrie entre chat (geoloc runtime dispo) et heartbeat (geoloc runtime inaccessible car job scheduler out-of-session)

**Solution**:
- ✅ 3 colonnes users : `last_known_location_encrypted` (Fernet JSON), `last_known_location_updated_at` (TTL + throttle), `weather_use_last_known_location` (opt-in)
- ✅ `UserLocationService.get_effective_location_for_proactive` : cascade home | last_known selon opt-in + fraîcheur (TTL env-configurable, default 24h) + distance (env-configurable, default 50 km)
- ✅ Capture fire-and-forget dans `stream_chat_response` avec throttle 30 min serveur
- ✅ Endpoints PATCH preference, PUT last-location (403 si opt-out), GET last-location (transparence RGPD)
- ✅ Auto-wipe sur opt-out ET sur suppression home
- ✅ Reverse geocoding OpenWeatherMap avec cache Redis 3 décimales / TTL 30j → ville dans prompt de notif
- ✅ Métriques Prometheus dédiées (source, put result, geocode cache, active users)
- ✅ UI settings avec toggle + zone transparence + bouton "Clear now" + libellé privacy + i18n 6 langues

**Trade-offs**:
- One-tick staleness acceptée (pas de trigger dynamique de heartbeat sur changement de position)
- Pas de multi-home / work location / travel mode manuel — à introduire via table `user_locations` dans un futur ADR si le besoin émerge
- Dépendance OpenWeatherMap reverse pour city name (notifs fonctionnent sans, mais sans ville)

---

### ADR-074: `structured_data` Contract for Tool Outputs

**Status**: ✅ ACCEPTED (2026-04-19)
**Fichier**: `docs/architecture/ADR-074-Structured-Data-Contract.md`

**Décision**: Promouvoir `UnifiedToolOutput.structured_data` au rang de contrat explicite et unique pour exposer les entités métier d'un tool aux consommateurs downstream (parallel_executor → `completed_steps` → chaînage `$steps.X.Y`, scripts skills, templates Jinja2). `metadata` reste strictement réservé au debug/observabilité.

**Problème résolu**:
- ❌ Anti-pattern : certains tools (ex. `brave_tools`) exposaient leurs résultats dans `metadata` → chaînage `$steps.search.braves` silencieusement cassé
- ❌ Dépendance invisible : chaînage fonctionnait via reconstruction registry dans `parallel_executor` (groupement par `meta.domain`), mais échouait pour les tools sans `registry_updates` (ex. Hue rooms/scenes, actions)
- ❌ Skill scripts B1 (plans déterministes) impossibles à écrire de manière fiable sur certains domaines

**Solution**:
- ✅ Helper central `ToolOutputMixin._build_items_structured_data(items, plural_key, **meta)` → format plat, clés plurielles alignées avec `REGISTRY_TYPE_TO_KEY`, `count` toujours présent, `None` métadata stripped
- ✅ 7 helpers mixins enrichis : `build_contacts_output`, `build_emails_output`, `build_events_output`, `build_tasks_output`, `build_files_output`, `build_places_output`, `build_weather_output` + `build_standard_output` + `create_tool_formatter`
- ✅ `brave_tools.py` : `braves` déplacé de `metadata` vers `structured_data`
- ✅ `hue_tools.py` : 6 tools (list/control/activate lights/rooms/scenes) exposent leurs entités et payloads d'action dans `structured_data`
- ✅ 22 nouveaux tests ciblés + 852 non-régression (`tests/unit/domains/agents/tools/test_mixins_structured_data.py`, `test_brave_hue_structured_data.py`)
- ✅ Coexistence avec reconstruction registry dans `parallel_executor` préservée (merge gentle, registry gagne en cas de conflit pour conserver `_registry_id`)

**Trade-offs**:
- Duplication assumée entre registry reconstruction et `structured_data` sur les clés plurielles (ex. `contacts`) — le merge gentle tranche en faveur du registry qui porte `_registry_id`, le surcoût est une copie shallow sans impact runtime
- Règle simple à faire respecter en code review : toute donnée métier exposée → `structured_data`, jamais `metadata`

---

### ADR-075: Rich Skill Outputs — Interactive Frames and Images

**Status**: ✅ ACCEPTED (2026-04-20)
**Fichier**: `docs/architecture/ADR-075-Rich-Skill-Outputs.md`

**Décision**: Formaliser un contrat JSON typé `SkillScriptOutput` permettant à un script Python de skill de retourner — en plus du texte — une frame HTML interactive (iframe srcDoc ou URL externe) et/ou une image, rendue comme widget sandboxé dans le chat. Réutilisation de la pipeline Data Registry → SSE → sentinel → widget React (déjà vivante pour MCP Apps depuis F2.5) via un nouveau type `RegistryItemType.SKILL_APP`.

**Problème résolu**:
- ❌ Skills limités au texte : une carte, un QR code ou un dashboard ne peuvent pas être rendus fidèlement
- ❌ Pas de voie canonique pour un skill qui produit un artefact visuel
- ❌ Dupliquer l'infrastructure MCP Apps pour les skills augmenterait la surface de maintenance

**Solution**:
- ✅ Contrat `{text, frame?, image?}` sur stdout — `text` requis, `frame`/`image` indépendants et combinables, `frame.html` XOR `frame.url`, taille `frame.html ≤ 200 KB`
- ✅ `RegistryItemType.SKILL_APP` + `INTERACTIVE_WIDGET_TYPES = {SKILL_APP, MCP_APP, DRAFT}` — les widgets interactifs s'affichent indépendamment du `user_display_mode` (Rich HTML / Markdown / Cards)
- ✅ Defence in depth : iframe sandbox `allow-scripts allow-popups` (jamais `allow-same-origin`), CSP stricte auto-injectée pour les skills utilisateur (`connect-src 'none'; frame-src 'none'`), bridge minimaliste sans `tools/call` / `resources/read`
- ✅ Conventions runtime : `_lang` et `_tz` auto-injectés dans `parameters`, thème/locale synchronisés en live via `postMessage` + `MutationObserver`, auto-resize via `getBoundingClientRect().bottom` (pattern iframe-resizer), CSPRNG pour le pseudo-aléatoire
- ✅ Primacy effect : `skills_context` injecté comme 2ᵉ message système préfixé `"SKILL INSTRUCTIONS CONTRACT (PRIORITY: HIGHEST)"` — les `references/*.md` du skill actif l'emportent sur les `<ResponseGuidelines>` génériques
- ✅ Rétrocompatibilité totale : stdout non-JSON est auto-wrappé en `{text: <stdout>}`
- ✅ Sept skills système pilotes : `interactive-map`, `weather-dashboard`, `calendar-month`, `qr-code`, `pomodoro-timer`, `unit-converter`, `dice-roller`

**Trade-offs**:
- Pas de persistance localStorage dans les frames (skills stateful → futur tool backend dédié)
- Frames perdues au rechargement d'historique (même limite que MCP Apps, résolution orthogonale)
- Pas de listes `frames`/`images` en v1 (grille HTML comme contournement, extension additive possible)

---

### ADR-076: Health Metrics Ingestion via Per-User Tokens

**Status**: ✅ ACCEPTED (2026-04-20, revisé 2026-04-21 — batch upsert polymorphe ; revisé 2026-04-22 — assistant integrations + extensibilité)
**Fichier**: `docs/architecture/ADR-076-Health-Metrics-Ingestion.md`

**Décision**: Créer un domaine DDD `health_metrics` exposant deux endpoints par-kind authentifiés par token (`POST /api/v1/ingest/health/steps`, `POST /api/v1/ingest/health/heart_rate`) qu'une automatisation iPhone Shortcuts peut appeler en **batches quotidiens** avec samples auto-horodatés. Stockage polymorphe en table unique `health_samples(kind, date_start, date_end, value, source)` avec UPSERT idempotent, visualisation côté Settings (graphiques heure/jour/semaine/mois/année). **v1.17.2** : registre central `HEALTH_KINDS` rendant l'ajout d'un kind trivial (une entrée + quelques tools), un unique `health_agent` LangGraph avec 7 tools (convention 1 agent ↔ 1 domaine, `time_min`/`time_max` ISO 8601 comme `calendar_tools`), source Heartbeat `health_signals`, enrichissement mémoire (`context_biometric` JSONB) et journal (extraction + consolidation) derrière un toggle utilisateur unique opt-in.

**Problème résolu**:
- ❌ Exposer `user_id` en paramètre rendrait trivialement falsifiable n'importe quelle ingestion (un ID est public par design — URLs, JWT, logs)
- ❌ La chaîne cookie-auth n'est pas utilisable depuis un Raccourci iOS
- ❌ iOS n'exécute pas fiablement un automatisme horaire (iPhone doit être déverrouillé), le design initial « one POST per hour » n'était pas tenable
- ❌ Données santé = catégorie spéciale RGPD (art. 9), besoin d'un droit d'effacement granulaire

**Solution**:
- ✅ Tokens hashés (SHA-256) avec préfixe d'affichage `hm_xxxxxxxx`, valeur brute révélée une seule fois à la création, révocables individuellement
- ✅ **Batch upsert client-timestamped** : samples `[{date_start, date_end, value, o}, …]`, UPSERT PostgreSQL `ON CONFLICT (user_id, kind, date_start, date_end) DO UPDATE … RETURNING (xmax = 0)` pour split inserts/updates en un round-trip. Re-sender la même journée = idempotent
- ✅ **Parser flexible** acceptant 4 enveloppes (tableau, NDJSON, `{"data":[…]}`, wrapping iOS « Dictionnaire » `{"<ndjson>":{}}`) — pas de contrainte sur le Raccourci utilisateur
- ✅ **Dedupe intra-batch avec arbitrage per-kind** : MAX pour `steps` (Watch+iPhone comptent sous-ensembles complémentaires), AVG arrondi pour `heart_rate` (fusion deux capteurs même signal) — prévient `CardinalityViolationError` sur samples overlap Apple Watch+iPhone
- ✅ Validation mixte par sample : hors plage → rejeté individuellement avec index + reason, voisins valides préservés (plus de NULL-ing)
- ✅ Aggregator polymorphe : AVG/MIN/MAX sur HR, SUM sur steps, par bucket, gaps préservés (`has_data=False`)
- ✅ Suppression par kind (DELETE WHERE kind=?) ou globale, CASCADE sur `users` couvre l'erasure RGPD
- ✅ Métriques Prometheus bornées (`health_samples_upserted_total{kind, operation}`, `health_samples_batch_duplicates_total{kind}`, `health_metrics_validation_rejected_total{field, reason}`, auth/rate-limit/tokens/deletions) + dashboard Grafana 21
- ✅ Feature flag `HEALTH_METRICS_ENABLED` (default `false`), rate limit 60 req/h/token, plafond 1000 samples/batch
- ✅ **v1.17.2 — Registre central + extensibilité** : `HEALTH_KINDS: dict[str, HealthKindSpec]` porte validation/merge/aggregation/baseline/agent par kind. Ingestion/repo/aggregator/heartbeat/memory/journal itèrent ce registre — ajouter sleep/SpO2/calories = une entrée + pack de tools
- ✅ **v1.17.2 — Baseline adaptive** `bootstrap` (< 7 jours, mode exposé au LLM) → `rolling` 28 j, thresholds configurables
- ✅ **v1.17.2 — Assistant integrations** derrière toggle utilisateur unique `User.health_metrics_agents_enabled` (migration `health_metrics_004`, default false, opt-in) : 3 agents LangGraph (steps/heart_rate/overview, 7 tools, 3 prompts v1, manifests catalogue), source Heartbeat `health_signals` (timeout 2s + fallback), enrichissement mémoire (`context_biometric` JSONB sur `memories`, migration `health_metrics_005`), injection journal (extraction + consolidation). Zéro valeur brute en aval — uniquement deltas/tendances/événements
- ✅ **v1.17.2 — Endpoint** `PATCH /auth/me/health-metrics-agents-preference` + section « Assistant » dans Settings 6 langues

**Trade-offs**:
- Modèle polymorphe single-table `value INT` → limite aux mesures scalaires (un futur `workout` carrying multiple scalars demanderait JSON ou seconde table — non prioritaire)
- Dedupe iOS wrapping via heuristique (clé unique avec newline + valeur vide) → fragile si iOS change le format ; mitigé par fallback NDJSON
- Pas d'encryption applicative sur FC/pas (encryption at rest PostgreSQL jugée suffisante pour des scalaires numériques non-PII)

---

### ADR-077: Today Briefing as a Standalone Bounded Context

**Status**: ✅ ACCEPTED (2026-04-22)
**Fichier**: `docs/architecture/ADR-077-Today-Briefing-Domain.md`

**Décision**: Créer un nouveau bounded context `apps/api/src/domains/briefing/` pour la home page « Today », orchestré directement (sans passer par la chaîne LangGraph) via `asyncio.gather` parallèle des services existants (OpenWeatherMap, calendar/email multi-provider, GooglePeople, ReminderService, HealthMetricsService). Cache Redis par section avec TTL différenciés (météo 1 h, agenda 10 min, mails 5 min, anniversaires 24 h, rappels live, santé 15 min). Deux appels LLM légers (greeting + synthèse) sur un slot unique `briefing` dans `LLM_TYPES_REGISTRY`, avec deux prompts versionnés distincts. Tracking via `track_proactive_tokens(task_type="briefing")`.

**Problème résolu**:
- ❌ Le dashboard actuel = écran de stats (messages/tokens/coût) sans valeur opérationnelle quotidienne
- ❌ Étendre le heartbeat domain mélangerait deux préoccupations : décision LLM proactive (heartbeat) vs. lecture UI synchrone (briefing)
- ❌ Faire passer le briefing par la chaîne LangGraph ajouterait 2-5 s de latence et coûterait ~10× plus en tokens pour zéro valeur (pas de raisonnement, pas de HITL)

**Solution**:
- ✅ Bounded context dédié `briefing/` (constants, exceptions, schemas, formatters, fetchers, llm, service, router) — séparation DDD claire
- ✅ Aucun modèle DB, aucune migration, aucun scheduler obligatoire — lecture pure
- ✅ 6 fetchers indépendants (weather/agenda/mails/birthdays/reminders/health) testables isolément, raise `ConnectorNotConfiguredError` ou `ConnectorAccessError` mappés vers `CardStatus` (OK/EMPTY/ERROR/NOT_CONFIGURED)
- ✅ Cards `NOT_CONFIGURED` totalement masquées côté frontend (`return null`) — l'écran s'adapte à l'état d'onboarding
- ✅ Stratégie stale-while-revalidate côté client : skeleton immédiat, `animate-in fade-in` + stagger 50 ms, refresh par card avec cascade greeting + synthèse
- ✅ Métriques Prometheus dédiées (`briefing_build_duration_seconds`, `briefing_section_status_total`, `briefing_refresh_requests_total`, `briefing_llm_invocations_total`)
- ✅ i18n complet 6 langues sous `dashboard.briefing.*` (16 clés, 6 cards localisées)

**Trade-offs**:
- Légère duplication de logique avec `heartbeat/context_aggregator.py` (fetchers similaires) — acceptable car les contextes ont des contrats stables différents et les clients sous-jacents sont mutualisés
- Deux contextes à maintenir en parallèle quand on ajoute une nouvelle source — mais les besoins ne sont pas symétriques (heartbeat = decision LLM, briefing = UI render)

---

### ADR-078: LLM Catalogue DB-Source-of-Truth

**Status**: ✅ IMPLEMENTED (2026-05-05) — étendu v1.19.1 (2026-05-05) avec section *Adding a New Provider* (DeepSeek V4 worked example)
**Fichier**: `docs/architecture/ADR-078-LLM-Catalogue-DB-Source-Of-Truth.md`

**Décision**: Migrer le catalogue LLM (chat + image) des constantes Python figées (`FALLBACK_PROFILES` ~750 lignes, `IMAGE_GENERATION_MODELS`, `REASONING_MODELS_PATTERN`) vers la base de données comme source de vérité unique. Trois tables : `llm_models` (catalogue avec `provider` enum + 8 capacités), `llm_model_pricing` refactorée (FK sur `llm_models.id`, suppression de la colonne `model_name`), `image_generation_pricing` étendue avec une colonne `provider` NOT NULL. Deux singletons en mémoire (`ModelCapabilitiesCache`, `ImageOptionsCache`) chargés au boot et invalidés cross-worker via Redis Pub/Sub (ADR-063). Frontend admin avec un formulaire 14 champs (provider + 8 capacités + tarification) et propagation cross-sibling live via un React Context (`CatalogueInvalidationProvider`).

**Problème résolu**:
- ❌ Ajouter ou ajuster un modèle exigeait code change + tag + redéploiement
- ❌ Le toggle admin `is_reasoning_model` était silencieusement bypassé par 3 sites de détection regex (frontend constraints, OpenAI Responses adapter, generic adapter)
- ❌ La table `llm_model_pricing` n'avait ni FK ni capabilities, et `image_generation_pricing` n'avait pas de colonne provider

**Solution**:
- ✅ Catalogue éditable depuis l'UI admin sans redéploiement, source de vérité unique pour la factory LangChain, les contraintes des agents, les dropdowns de préférences images et le cost tracker
- ✅ Migrations en 3 étapes (schéma → backfill 47 modèles → contraintes), réversibles
- ✅ Invalidation cross-worker via Pub/Sub (ADR-063) en < 50 ms ; invalidation cross-sibling frontend via React Context, sans rafraîchissement de page
- ✅ Détection `is_reasoning_model` consolidée : DB authoritative, regex en fallback uniquement pour les modèles inconnus du cache
- ✅ Versioning temporel via `is_active=false` (préserve l'historique sans casser les FK)
- ✅ Seeds remaniés : 119 modèles chat (catalogue + pricing par JOIN) + 27 lignes image avec `provider='openai'`

**Trade-offs**:
- Boot dependency : la factory exige le cache populé avant le premier appel LLM (atténué par chargement synchrone dans le lifespan startup avant l'enregistrement des routes)
- Fenêtre regex-fallback : pour un modèle inséré juste après le boot d'un worker et avant son tick Pub/Sub, la regex décide encore — fenêtre bornée à la latence de publish (typiquement < 50 ms)

---

### ADR-079: Stratified Journal Consciousness

**Status**: ✅ IMPLEMENTED (2026-05-06) — **raffiné par [ADR-088](#adr-088-journal-write-restraint--level-routed-operational-injection--react-directive-coherence)** (2026-06-02)
**Fichier**: `docs/architecture/ADR-079-Stratified-Journal-Consciousness.md`

**Décision**: Refondre le carnet de bord introspectif (ADR-057 / ADR-064) en organe de méta-cognition stratifiée. Quatre niveaux d'abstraction (`L0` observation brute, `L1` directive opérationnelle, `L2` pattern transversal, `L3` facette de portrait), un statut épistémique par entrée (`confidence` + compteurs `evidence_count` / `contradiction_count`), une auto-évaluation différée T → T+1 (l'extracteur du tour T voit les directives injectées au tour T-1 et les compare à la réaction utilisateur), et un portrait utilisateur compilé en deux formats (full ~200 tokens, brief ~60 tokens) diffusé dans 9 flux où LIA parle. Trois leviers correctifs côté utilisateur (édition L3, signalement avec consolidation synchrone, recompilation manuelle) — sans édition directe du portrait synthèse.

**Problème résolu**:
- ❌ Le journal était sourd à sa propre efficacité : `injection_count` / `last_injected_at` peuplés en base mais invisibles au LLM lors de l'écriture
- ❌ Plat — un seul niveau, pas de portrait, pas de gradient hypothèse / confirmé / contredit
- ❌ Cloisonné — n'irriguait que `response_node` et `planner_node` ; ReAct, voice, reminders, heartbeat, proactive interest, fallback restaient aveugles à la nuance accumulée
- ❌ Boucles auto-renforçantes : pas de mécanisme pour détecter qu'une directive injectée la veille s'est révélée inutile

**Solution**:
- ✅ Migration unique réversible (toutes nouvelles colonnes nullable / server_default) : `level`, `confidence`, `evidence_count`, `contradiction_count` sur `journal_entries` ; `journal_portrait_full`, `journal_portrait_brief`, `journal_portrait_compiled_at` sur `users`
- ✅ Auto-évaluation à coût LLM nul : enrichissement du prompt d'extraction existant avec les directives du tour précédent (transportées via `MessagesState.injected_journal_ids`, symétrique de `injected_memories`) ; le LLM signale `evidence_outcome="evidence" | "contradiction"` et le service incrémente atomiquement les compteurs (anti-hallucination niveau 4)
- ✅ Portrait compilé dans le même appel LLM que la consolidation (zéro appel additionnel) ; standalone `portrait_builder.build_journal_user_model_block(user_id, format, flow)` symétrique à `build_psyche_prompt_block`, retournant un bloc `<UserModelContext>...</UserModelContext>` avec dégradation gracieuse
- ✅ Diffusion dans 8 flux : 2 primaires en format full (`response_node`, `planner_node_v3`) et 6 secondaires en format brief (`react_setup_node`, `interests/proactive_task`, `scheduler/reminder_notification`, `voice/service`, `heartbeat/prompts`, `agents/services/fallback_response` sync + async)
- ✅ Trois leviers utilisateur (édition L3, 🚩 signalement → consolidation synchrone, 🔄 recompile) — portrait jamais directement éditable
- ✅ Discipline de dédoublonnage déplacée du write-time guard (retiré, ADR-064) vers consolidation STEP 1 (scan pairwise mandatory) ; `JOURNAL_DEDUP_SIMILARITY_THRESHOLD` supprimé
- ✅ 11 métriques Prometheus dédiées (`journal_evidence_total{outcome}`, `journal_consolidation_promotions_total{from_level,to_level}`, `journal_portrait_present_total{flow,format}`, `journal_dedup_actions_total`, etc.)
- ✅ Endpoints `POST /journals/consolidate`, `GET /journals/portrait`, `POST /journals/portrait/feedback` ; export GDPR enrichi du portrait ; scrub portrait au `_mark_user_deleted`

**Trade-offs**:
- Coût opérationnel : ~+1240 tokens cumulés par utilisateur typique sur 24 h, +1 ms SQL par flux (read portrait) — soutenable, mesurable via `journal_portrait_present_total`
- Maturité du portrait : ~3-5 cycles de consolidation (quelques jours à quelques semaines) avant que le L3 stabilise pour un utilisateur existant
- Consolidation synchrone du levier 2 : ~5-10 s LLM sur action utilisateur (loader visible) ; throttling à prévoir si saturation observée

---

### ADR-080: Remote Voice STT (ElevenLabs Scribe) and pricing-unit extension

**Status**: ✅ IMPLEMENTED (2026-05-07)
**Fichier**: `docs/architecture/ADR-080-Voice-STT-Remote-Pricing-Unit.md`

**Décision**: Ajouter ElevenLabs Scribe comme provider STT distant **opt-in par utilisateur** (préférence `voice_stt_mode = local | remote`) sans casser le pipeline 100 % local existant. Étendre le modèle `llm_model_pricing` d'une colonne `pricing_unit` (`per_1m_tokens` / `per_audio_minute` / `per_audio_hour`) — les colonnes prix sont renommées (`input_unit_price`, `output_unit_price`, `cached_input_unit_price`) car leur sémantique dépend désormais de l'unité. Scribe v2 est seedé avec `pricing_unit=per_audio_hour`, `input_unit_price=0.22`, miroir verbatim du tarif ElevenLabs ($0.22/h). Une factory STT (`get_stt_service_for_mode`) avec un `SttServiceProtocol` route le buffer PCM Int16 LE 16 kHz mono soit vers Sherpa-onnx local, soit vers `POST /v1/speech-to-text` (`file_format=pcm_s16le_16`, pas de wrap WAV). Le coût STT est imputé à la **bulle utilisateur** (5 nouvelles colonnes nullables sur `conversation_messages`) et agrégé dans `user_statistics.cycle_stt_cost_eur` qui contribue à `cycle_cost_eur` (la card "Cost" du dashboard et les `user_usage_limits` globales l'incluent automatiquement). Push-to-talk et wake-word partagent la même préférence backend via le ticket WebSocket étendu.

**Problème résolu**:
- ❌ Le mode vocal local (Sherpa-onnx Whisper-small) avait une qualité limitée — pas de moteur STT haut de gamme disponible
- ❌ Pas de sémantique "prix par durée audio" dans le modèle `llm_model_pricing` actuel (token-bound) — empêchait une refacturation auditable
- ❌ Aucune attribution de coût côté `conversation_messages.role='user'` — tous les coûts existants étaient sur les runs assistant
- ❌ Push-to-talk et wake-word étaient couplés UI : impossible de tester ElevenLabs en push-to-talk sans activer le mode mains libres

**Solution**:
- ✅ 3 migrations Alembic (rename colonnes + `pricing_unit_enum` + `'elevenlabs'` ajouté à `llm_provider_enum` ; colonnes STT sur `conversation_messages` ; agrégats STT sur `user_statistics` + `voice_stt_mode` sur `users`) — la rename utilise une boucle `pg_attribute` dynamique pour migrer toutes les colonnes dépendantes de l'ENUM, robuste à toute table future
- ✅ Pricing cache sync-safe : `get_cached_cost_audio_usd_eur(model, duration_seconds)` + garde croisée avec `get_cached_cost_usd_eur` (token) pour empêcher tout miscompute silencieux
- ✅ Nouveau type LLM `voice_transcription` (kind=audio) dans `LLM_TYPES_REGISTRY` / `LLM_DEFAULTS` — l'admin Configuration LLM filtre automatiquement les modèles audio
- ✅ Abstraction `SttServiceProtocol` + factory : `SherpaSttService` (local, gratuit) et `ElevenLabsSttService` (remote, $0.22/h) implémentent la même interface ; `transcribe_pcm_int16_async(bytes, sample_rate, language)` reçoit le buffer brut Int16 LE 16 kHz mono — Scribe l'accepte tel quel via `file_format=pcm_s16le_16`
- ✅ Ticket WebSocket étendu (`{user_id, language, voice_stt_mode}`) — un seul lookup au `/voice/ticket`, le handler `/ws/audio` route ensuite sans DB
- ✅ Check `usage_limits` AVANT chaque appel ElevenLabs (close 4029 si bloqué) ; mise à jour `user_statistics.cycle_stt_cost_eur` + `cycle_cost_eur` côté handler dès la transcription remote réussie ; persistance détail par message via `archive_message` étendu et propagation `stt_*` via `ChatRequest`
- ✅ Découplage UI : le RadioGroup local/distant est toujours visible (utilisé par push-to-talk ET wake-word), le toggle `voice_mode_enabled` n'active que le mode mains libres
- ✅ Exports CSV étendus : `consumption-summary` inclut désormais STT par utilisateur, nouveau type `stt-usage` (user + admin) pour le détail par message
- ✅ Badge UI sur la bulle user (`🎤 X.Xs • €X.XXX`) avec persistance DB pour le retour au reload

**Trade-offs**:
- Audio sort du périmètre serveur LIA en mode `remote` (transmis à ElevenLabs cloud) — mitigé par une InfoBox de confidentialité sous le switch et par la persistance par-message pour l'audit volume
- Renommage des colonnes prix (~40 call sites Python + ~5 fichiers TS) — coût one-shot, l'API admin Tarification est la seule surface affectée
- Le wake-word reste anglais-only (modèle `whisper-tiny.en` bundlé en WASM côté browser) — un plan séparé futur traitera la migration vers un Whisper multilingue

---

### ADR-081: Voice TTS configuration driven by the LLM catalogue

**Status**: ✅ IMPLEMENTED (2026-05-07)
**Fichier**: `docs/architecture/ADR-081-Voice-TTS-Catalogue-Driven.md`

**Décision**: Promouvoir le TTS au rang de type LLM `voice_tts` (kind=tts) dans `LLM_TYPES_REGISTRY` et faire vivre la sélection (provider, modèle, voix male/female, réglages spécifiques) sur `llm_config_overrides.voice_tts` — exactement comme les modèles chat (ADR-078). Trois providers TTS dès le jour 1 (Edge / OpenAI / ElevenLabs) avec leurs catalogues séedés dans `llm_models` + `llm_model_pricing`. Les voix et tuning provider-spécifique (Edge: SSML rate/pitch/volume, OpenAI: speed/response_format, ElevenLabs: output_format + voice_settings) vivent dans le blob JSONB `provider_config` du même row d'override. Un nouvel endpoint admin `GET /admin/voice/voices?provider=X` peuple dynamiquement le voice picker (statique pour Edge/OpenAI, live `GET /v1/voices` pour ElevenLabs avec scope `voices_read`). La binarité `system_settings.voice_tts_mode ∈ {standard, hd}` et les 14 env vars `VOICE_TTS_*` sont retirés.

**Problème résolu**:
- ❌ La binarité `standard|hd` cachait que le choix de voix dépend du modèle (pas du tier qualité) — un voice_id Edge crashe l'API OpenAI et inversement
- ❌ Trois providers TTS = trois surfaces de tuning hétérogènes (SSML strings, numériques, objet `voice_settings`) impossibles à plier dans un schéma plat env-driven sans dégrader des champs
- ❌ Tarification TTS hors catalogue (constants en code) — pas d'auditabilité dans la même surface admin que les modèles chat (ADR-078)
- ❌ Switch de provider en runtime impossible sans redéploiement (les env vars étaient résolues au boot)

**Solution**:
- ✅ Migration Alembic `2026_05_07_0004` : ajoute `'edge'` à `llm_provider_enum` (boucle `pg_attribute` dynamique migrant toutes les colonnes dépendantes), supprime la row `system_settings.voice_tts_mode`
- ✅ Seed étendu : 6 modèles TTS (Edge $0, OpenAI tts-1 $15 / tts-1-hd $30, ElevenLabs eleven_multilingual_v2 $100 / eleven_turbo_v2_5 $50 / eleven_flash_v2_5 $50), tous en `per_1m_tokens` (chars-as-tokens — calcul correct, label admin générique)
- ✅ Type `voice_tts` dans `LLM_TYPES_REGISTRY` avec `required_kind=tts` ; `LLM_DEFAULTS` carrying Edge + voix françaises canoniques + SSML neutre dans `provider_config` JSONB
- ✅ Factory `apps/api/src/domains/voice/factory.py` réécrite : lit `LLMConfigOverrideCache.get_override("voice_tts")` mergé avec `LLM_DEFAULTS`, parse `provider_config` en `TTSConfig` typé, fallback transparent vers Edge si la clé d'un provider payant manque
- ✅ Endpoint admin `GET /admin/voice/voices?provider=X` (router dédié `apps/api/src/domains/voice/admin_router.py`) + nouveau `ElevenLabsTTSClient` implémentant le protocol `TTSClient`
- ✅ UI Configuration LLM enrichie : détection `required_kind === 'tts'` dans `LLMConfigDialog` → bloc voix male/female + inputs provider-spécifiques + reset `provider_config` au switch de provider + sérialisation canonique (sorted keys) au save
- ✅ Cleanup complet : `AdminVoiceSettingsSection.tsx` supprimé, endpoints `/admin/system-settings/voice-mode` retirés, `VoiceTTSModeCache` + `get_voice_tts_mode()` + `invalidate_voice_tts_mode_cache()` retirés du domaine `system_settings`, 14 env vars `VOICE_TTS_*` retirés des 3 fichiers `.env*`

**Trade-offs**:
- Les opérateurs avec env override custom perdent leur réglage à l'upgrade (fallback aux seeds : Edge / Rémy-Vivienne / +10% rate — les anciens defaults `standard mode`)
- TTS facturé sur l'axe `per_1m_tokens` même si les providers facturent au caractère — le cost tracker fait passer le char count comme token count, math correcte, label à internaliser ("tokens = chars" pour les rows TTS)
- Le `provider_config` peut techniquement contenir des clés étrangères au provider actif (ex: `output_format` sous Edge) — la factory ignore silencieusement les clés irrelevantes et l'UI clear le JSON au switch de provider, donc en pratique non-issue
- L'alias back-compat `mode == "hd"` survit sur `TTSConfig` (calculé via `is_paid`) le temps que tous les call sites downstream migrent vers `is_paid` explicite

---

### ADR-082: Progressive sentence streaming for low-latency TTS

**Status**: ✅ IMPLEMENTED (2026-05-07)
**Fichier**: `docs/architecture/ADR-082-Progressive-Sentence-Streaming.md`

**Décision**: Pipeliner la TTS au niveau **phrase** au lieu d'attendre la fin du LLM. Trois optimisations cumulées : (1) `httpx.AsyncClient` persistant sur `ElevenLabsTTSClient` pour réutiliser la connexion entre phrases (~100-300 ms gagnées par appel sur les phrases #2..N) ; (2) nouvelle classe `ProgressiveSentenceStreamer` qui buffer les tokens, dispatche une `asyncio.Task` TTS dès qu'un délimiteur de fin de phrase (`[.!?]+`) est détecté, garantit l'ordre (in-order delivery via `_pending: dict[int, VoiceAudioChunk]` + `_drain_lock`), saute les slots échoués sans bloquer le drain (`_failed: set[int]`), pousse une sentinel idempotente (flag `_sentinel_pushed`) ; (3) deux points d'intégration : mode chat (`router_decision.intention=conversation` → `start_progressive_chat_stream` qui consomme les tokens du chat LLM en live) et mode agent (`stream_voice_comment` réécrite pour utiliser `llm.astream()` au lieu de `ainvoke()`). Cleanup contract : tout chemin de sortie du SSE generator (HITL `GraphInterrupt`, exception, fin nominale) appelle `_cleanup_chat_voice_pipeline` qui cancel le drain task, le streamer et le service (close du httpx persistant).

**Problème résolu**:
- ❌ TTFA de 5-15 s en mode chat (attente du response complet) et 3-8 s en mode agent (attente du voice LLM complet)
- ❌ TLS handshake répété sur ElevenLabs (~150 ms par phrase × N phrases = 0.5-1.5 s perdues sur 5 phrases)
- ❌ Une phrase TTS échouée bloquait l'émission des suivantes (séquentialité de la boucle)
- ❌ Couplage triple LLM streaming + sentence detection + TTS dispatch dans une seule fonction `stream_direct_tts(text=full_response)`

**Solution**:
- ✅ Persistent httpx client : `httpx.AsyncClient(limits=Limits(max_keepalive_connections=10, ...))` instancié dans `ElevenLabsTTSClient.__init__`, réutilisé pour chaque `synthesize()`, fermé dans `close()` via `aclose()`
- ✅ `ProgressiveSentenceStreamer` (`apps/api/src/domains/voice/sentence_streamer.py`, 350 lignes, 12 unit tests) : `feed(text)` accumule, dispatche les phrases ; `close_input()` flush trailing ; `audio_chunks()` async iterator avec in-order garantie ; `cancel_pending()` annule proprement
- ✅ Mode chat : `agents/api/service.py` détecte `router_decision.intention=conversation` au début du stream → `VoiceCommentService.start_progressive_chat_stream(...)` retourne `(streamer, drain_task)`, chaque token est passé à `streamer.feed()`, drain task pousse dans la même `voice_chunk_queue` que la PATH 1 existante (réutilise la drain logic SSE)
- ✅ Mode agent : `stream_voice_comment` consume `llm.astream(prompt, config=config)`, callback `TokenTrackingCallback` toujours actif pour le tracking LLM tokens, sentence streamer pour les TTS calls
- ✅ Cleanup contract : helper `AgentService._cleanup_chat_voice_pipeline(streamer, drain_task, run_id, service)` idempotent, appelé sur HITL fallback, top-level except, fin nominale ; ferme aussi le service (close persistent httpx client)
- ✅ `tracker.commit()` early-return guard étendu pour inclure `pending_tts > 0` (sinon le sync-fallback voice flow skippe le persist)

**TTFA mesurée**:
- Mode chat (réponse 5 s, 5 phrases) : 5,5 s → **0,8-1,2 s** (5×)
- Mode agent (voice LLM 2 s, 3 phrases) : 3,5 s → **1-1,5 s** (2×)
- Mode agent registry tardif (5 s) : 6 s → **3 s**

**Trade-offs**:
- Surface de concurrence augmentée : N TTS tasks parallèles + 1 drain task par requête (mémoire négligeable, mais N chemins d'annulation à raisonner — d'où le helper `_cleanup_chat_voice_pipeline` idempotent)
- Burst rate provider : 5 calls TTS en ~1 s vs séquentiel sur 2-3 s ; ElevenLabs Starter/Creator n'atteint pas la limite de 1 burst/s en pratique
- `duration_ms` reste une heuristique `len(sentence) × 80 ms` (UI hint, pas un contrat précis) — durée réelle encodée dans le payload base64
- Échec d'une phrase TTS produit un trou audio mais ne bloque pas les suivantes (slot marqué `failed`, drain skip)

---

### ADR-083: Sub-Agent Delegation as a Parameterized ReAct Loop

**Status**: ✅ PARTIALLY IMPLEMENTED (2026-05-13 → 2026-05-14, with rollback)
**Fichier**: `docs/architecture/ADR-083-Sub-Agent-Delegation-React.md`

**Décision**: Recâbler la délégation éphémère du planner (`delegate_to_sub_agent_tool`) sur le runner ReAct générique `ReactSubAgentRunner` (déjà utilisé par `browser_task_tool` et `mcp_server_task_tool`), au lieu du pipeline bespoke `SubAgentExecutor` (`_analyze_instruction → SmartPlannerService → execute_plan_parallel → _synthesize_results`). Le sous-agent devient une boucle ReAct cadrée : `llm_type="subagent"`, prompt `subagent_react_prompt` (scaffold + `{expertise}` + contraintes read-only), tools = sous-ensemble read-only, `recursion_limit = subagent_default_max_iterations`. Token attribution automatique via `metadata["node_name_override"]` dans le `TokenTrackingCallback` du parent. Plus aucune création/suppression de record ORM éphémère, plus de budget journalier Redis sur cette voie. La Phase 2 (même journée) a supprimé la voie persistante (`SubAgentExecutor`, `/sub-agents` REST API, `SubAgent` ORM, scheduler stale-recovery, toggle utilisateur — voir ADR §Phase 2 completion).

**Problème résolu (incident 2026-05-12)**: «résume mes 5 derniers emails envoyés par ma femme» a consommé **485 930 tokens (€0.56, ~95 s)** — un sous-agent éphémère a re-tourné une mini-pipeline 3-LLM, chaque appel recevant ~114 K tokens d'`instruction` (corps HTML d'emails inlinés via `$steps.step_1.<field>` non borné par le `ReferenceResolver`).

**Garde-fou structurel retenu** : cap `SUBAGENT_INSTRUCTION_MAX_TOKENS_RESOLVED=3000` sur l'`instruction` résolue (`parallel_executor._execute_tool_step`) — tue le pattern «raw payload via `$steps.X.<data>`» au seul endroit où la taille résolue est connue. C'est la seule défense structurelle qui a survécu à l'analyse.

**Rolled back (2026-05-14)** : la veto `validate_sub_agent_delegation_justified` dans `semantic_validator` (basée sur `query_intelligence.domains` — mauvais signal, s'abstient pile sur les cas qu'elle devait attraper quand QI ajoute un domaine incident comme «contact» pour une mention personnelle) ET la réécriture du `_build_sub_agents_section` du planner prompt (introduisait «DO NOT DELEGATE for data retrieval + summarization» + un exemple BAD/GOOD interdisant `[fetch, delegate]`, ce qui sabote le cas d'usage dominant : appliquer une persona experte à des données que le principal peut fetcher proprement). Le setting `SUBAGENT_VETO_POINTLESS_ENABLED` et les tests associés ont été supprimés. La décision «quand déléguer» est entièrement déléguée au LLM du planner sans backstop runtime, comme avant l'incident — mais avec le cap comme seule garde dure. Un vrai redesign basé sur une taxonomie des cas d'usage est différé à un follow-up.

**Effet réel sur le code livré** : (a) la voie persistante n'existe plus, (b) le runtime de la délégation utilise le runner ReAct générique, (c) le pattern incident (raw bodies inlinés) est structurellement impossible. Les coûts de délégation hors-pattern-incident dépendent du plan que le LLM émet (non-déterministe) ; aucune métrique stable promise tant que le redesign n'est pas fait.

**Trade-offs**:
- **Aucune garde structurelle sur la forme du plan de délégation** — le cap n'attrape que l'inlining de payload brut. Un plan bien formé `[fetch_metadata, delegate(persona, instruction)]` où le sub-agent refetche les bodies en 5–8 itérations ReAct passe et coûte 200–300 K tokens traités (majoritairement cache-hit, donc cher en compute mais pas en €).
- **HITL de délégation reste passthrough** (régression v1.14.5 non corrigée, hors scope ici).

---

### ADR-084: Indexable vs Semantic Criteria — Universal Planning Principle + Leak Detector

**Status**: ✅ IMPLEMENTED — Phase 1 shipped in `observe` mode (2026-05-15)
**Fichier**: `docs/architecture/ADR-084-Indexable-vs-Semantic-Criteria.md`

**Décision**: Introduire un principe universel de planification (`INDEXABLE vs SEMANTIC CRITERIA`) appliqué uniformément à tout connecteur (Google, Microsoft, Apple, Notion, Slack, JIRA, MCPs futurs), backed par une défense en profondeur à 4 couches : (1) section dédiée dans `smart_planner_prompt.txt` placée avant `PLANNING RULES` pour cadrer conceptuellement toutes les règles applicatives ; (2) champ structuré `semantic_filter_terms: list[str]` sur `QueryAnalysisOutput`, propagé via `QueryAnalysisResult → QueryIntelligence (frozen tuple) → ValidationContext`, framé comme **hint probabiliste non-autoritaire** ; (3) méthode `_check_semantic_leak` universelle sur `PlanValidator`, invoquée par `validate_execution_plan` pour chaque step de chaque plan (single/multi domain), gated par `PLANNER_SEMANTIC_LEAK_MODE` (`off` / `observe` / `autocorrect`), avec word-boundary match et deux escape hatches (quote literal + `text_search_mode != "literal"`) ; (4) champ `text_search_mode: Literal["literal", "semantic", "hybrid"]` sur `ToolManifest` (défaut `"literal"` préserve 100% des tools existants), permettant aux futurs MCPs vectoriels d'opter out structurellement.

**Problème résolu (diagnostic 2026-05-15)** : sur «mes deux prochains rdv médicaux» (anglais pivoté `"my next two medical appointments"`), seul `gpt-5.2` trouvait les bons événements. Deux failure modes distincts : (a) sans `reasoning_effort`, `deepseek-v4-flash` au query_analyzer mal-classifiait en `skill_name="briefing-quotidien"` → `SkillBypassStrategy` court-circuitait le LLM planner → plan template 5-step générique → 0 events médicaux ; (b) avec `reasoning_effort=high`, classification skill correcte mais planner LLM générait `query="medical" + max_results=2` → Google Calendar ne fait que du match littéral sur le titre → 0 events. La règle 4 pré-existante du prompt smart_planner («Non-searchable field criteria → broad results, Response filters») requérait un raisonnement multi-couche (inférer la sémantique du connecteur cible + respecter la séparation Planner/Response + anticiper l'attrition du filtrage aval) que seuls les top-tier reasoning models maîtrisent.

**Stratégie de rollout** : strict `observe → measure → autocorrect`. Phase 1 shipped en `observe` (log + métriques uniquement, plan inchangé) — **zéro régression possible par construction**. Phase 2 (flip via `.env`, aucun redéploiement code) après 1–2 semaines d'accumulation de `lia_planner_semantic_leak_detected_total{mode="observe"}` et review manuelle d'absence de faux positifs.

**Observabilité (3 compteurs Prometheus)** : `lia_planner_semantic_filter_terms_emitted_total{model, term_count_bucket}` (émission de hint par modèle), `lia_planner_semantic_leak_detected_total{tool_name, param_name, mode}` (détection), `lia_planner_semantic_leak_autocorrected_total{tool_name, param_name}` (autocorrect). Le `query` fuitant n'est **pas loggé** (PII potentiel) — seuls les termes matchés, le step_id, le param_name et le tool_name apparaissent dans le warning structuré.

**Trade-offs**:
- **~370 tokens ajoutés au prompt planner** — récupérés par le cache provider en steady state (Anthropic 5-min TTL, OpenAI Responses API caching), mais coût payé au cold start.
- **Word-boundary heuristic intentionnellement simple** (`split + strip(".,;:!?()[]") + lowercase set intersection`) — peut manquer des variantes morphologiques marginales. Acceptable car coût faux-positif > coût faux-négatif pendant le rollout.
- **Phase 2 (`autocorrect`) n'est pas inconditionnellement safe** — gated sur review opérationnelle des logs `observe`, précisément parce qu'un tool à sémantique de recherche non-standard pourrait voir un plan légitime réécrit. Le flag de fallback `text_search_mode="hybrid"` reste l'échappatoire structurelle si un cas pathologique émerge.

---

### ADR-085: Draft Display Registry — Single Source of Truth for Post-HITL Rendering

**Status**: ✅ IMPLEMENTED (2026-05-17)
**Fichier**: `docs/architecture/ADR-085-Draft-Display-Registry.md`

**Décision**: Centraliser toute la connaissance d'affichage post-exécution d'un `DraftType` dans un **registre déclaratif unique** (`DRAFT_DISPLAY_REGISTRY` dans `apps/api/src/domains/agents/drafts/display.py`), exhaustif sur les 16 valeurs de l'énum, avec garde-fous *runtime + CI*. Le registre déclare par type : (1) emoji domaine (préfixe de header), (2) `item_label_fields` ordonnés pour extraire le libellé d'une ligne batch, (3) clé optionnelle `item_secondary_datetime_key` pour suffixer un contexte temporel (` — 16 mai 14h00`), (4) `detail_fields` ordonnés pour la vue détaillée single-confirm, (5) `noun_key` + `verb_past_key` qui pilotent la composition du header localisé via deux nouvelles tables i18n (`DRAFT_RESULT_NOUNS`, `DRAFT_RESULT_VERBS_PAST`) avec accord genre/nombre par langue. `assert_registry_completeness()` est appelé au lifespan startup *et* en CI, donc un nouveau `DraftType` non enregistré ne peut ni démarrer ni merger.

**Problème résolu (diagnostic 2026-05-17)** : `Supprime tous mes rappels` rendait après confirmation `✅ 3/3 / ✅ Action exécutée avec succès × 3`, sans emoji, sans libellé, sans datetime — alors que le scénario fonctionnait visuellement bien sur les autres domaines. La forensic a exposé **4 sources de vérité disjointes** par `DraftType` (`DRAFT_TYPE_EMOJIS` dans `i18n_hitl.py`, `DRAFT_SUCCESS_MESSAGES`/`DRAFT_CANCEL_MESSAGES` dans `i18n_drafts.py`, `_DRAFT_RESULT_FIELD_CONFIG` dans `response_node.py`, plus une chaîne d'extraction hard-codée dans la boucle batch) avec couvertures hétérogènes (13/16, 15/16, 6/16) — l'ajout antérieur de `REMINDER_DELETE` n'avait touché qu'une seule des quatre. `file_delete` et `label_delete` souffraient silencieusement du même défaut en batch, jamais détecté car jamais testé sous ce mode. La fragilité était structurelle, pas un oubli ponctuel.

**Grammaire i18n par langue** : le header de batch (`3 rappels supprimés`) exige un accord participe passé qui diffère par langue. Français/espagnol/italien : accord genre (m/f) × nombre (sing/plur), donc 4 formes par verbe (`m_sing` / `m_plur` / `f_sing` / `f_plur`) plus un champ `gender` sur chaque nom. Anglais/allemand : participe invariant (mais le nom allemand change de forme). Chinois : pas de genre, pas de nombre, ordre des mots différent (`已删除 3 个提醒`). Règle de pluralisation aussi par langue : français traite 0 et 1 comme singulier ; anglais/espagnol/allemand/italien traitent 1 comme singulier et tout le reste (0, ≥2) comme pluriel ; chinois invariant. `compose_result_header()` encapsule toute cette mécanique.

**Trade-offs**:
- **+~250 LoC** (registre + tables i18n + helpers + tests exhaustifs paramétrés sur `DraftType` × 6 langues) compensées par ~230 LoC de tables/conditions legacy supprimées. Net ≈ break-even, gros gain de cohésion.
- **2 nouvelles tables i18n** (`DRAFT_RESULT_NOUNS`, `DRAFT_RESULT_VERBS_PAST`) à maintenir, mais minuscules (7 noms × 6 langues, 4 verbes × 6 langues) et la parité par langue est testée — toute dérive échoue en CI avant merge.
- **Import local** dans `HitlMessages.get_draft_emoji()` pour éviter un cycle top-level `i18n_hitl ↔ drafts.display`. Idiomatique Python, callsite unique sur le warm path HITL.

---

### ADR-086: Conversation History Compaction v2 — Hardening, Observability, and User-Visible Truncation

**Status**: ✅ IMPLEMENTED (2026-05-19)
**Fichier**: `docs/architecture/ADR-086-Conversation-History-Compaction-v2.md`

**Décision**: Refonte de la couche de compaction de l'historique conversationnel (F4, 2026-03) pour éliminer la classe d'incident observée le 2026-05-16 (hang infini de 90 s+ pendant la compaction LLM, coupure SSE Cloudflare à 125 s, état non persisté, boucle de retry). Le périmètre couvre cinq axes : (1) résilience backend — `asyncio.wait_for` per-chunk (35 s) + tenacity retry × 3 + budget global 120 s + fallback explicite `_truncation_fallback` qui produit une `SystemMessage` lisible à la place du silencieux `descriptive_fallback` ; (2) consolidation des résumés précédents — les `"compaction #N"` antérieures sont injectées dans le prompt de merge et le node n'émet `RemoveMessage` pour elles que si le merge a réussi (`consolidated_previous_summaries=True`), pas en fallback ; (3) signal SSE — `compaction_start` / `compaction_done` émis par `compaction_node` via `langgraph.config.get_stream_writer` à travers un nouveau `stream_mode="custom"` traité par `_process_custom_chunk` du streaming service ; (4) keepalive concurrent — `iter_with_keepalive` enveloppe le générateur SSE avec un consumer task unique qui préserve la stabilité ContextVar et pulse `: heartbeat\n\n` **pendant** les await silencieux sans annuler la task en cours (le heartbeat router-level d'avant ne pulsait qu'entre chunks reçus) ; (5) UX frontend — nouveau `ChatStatus 'compacting'` + `CompactionState`, feedback via sonner toast `loading → success/warning` morphé sur un id stable (`COMPACTION_TOAST_ID`), i18n sur les 6 langues, `useChat.isTyping` étendu pour verrouiller automatiquement `ChatInput` via le wiring existant ; un composant `ContextUsagePill` dans l'en-tête du chat expose en continu le ratio `tokens / threshold` (badge clampé à 100 %, ratio réel dans le tooltip).

> **Note (pivot 2026-05-19)** : L'implémentation initiale utilisait un composant `CompactionBanner` rendu dans `ChatMessageList`. Un essai sticky-top a montré une UX fragile dans une conversation longue (banner invisible quand l'utilisateur est scrollé en bas, comportement instable sur les deux conteneurs `overflow-y: auto` imbriqués). Le rendu a été pivoté vers un `sonner` toast (composant et tests supprimés ; le contrat SSE backend reste inchangé). Voir la section *Update* de l'ADR pour les détails.

**Outillage opérationnel** : `scripts/admin/reset_user_checkpoints.sql` (recovery transactionnel pour les checkpoints LangGraph stuck) + dashboard Grafana `14-compaction.json` (7 panels : strategy mix, latence p50/p95/p99, chunk timeouts, global timeouts, errors by type, skipped reasons, tokens saved).

**Trade-offs**:
- **Aucun changement de schéma DB** ; settings additifs uniquement ; pas de feature flag (la nouvelle version ne peut pas régresser l'ancienne — les timeouts s'ajoutent là où il n'y en avait pas, le fallback explicite remplace un stub silencieux, les events SSE sont additifs). Rollback : monter `COMPACTION_*_TIMEOUT_SECONDS` à 600 s pour neutraliser.
- **`tenacity` déclaré explicitement** dans `requirements.txt` (était transitif via `langchain-core`).
- **5 défauts sciemment laissés hors scope v2** (Redis lock par thread, ingress node atomique, stratégies pluggables via Protocol, circuit breaker, modal HITL d'échec à 3 choix) — documentés dans *Alternatives Considered* avec la raison du report : aucun n'était requis pour résoudre la classe d'incident observée, le scope 5 jours ne les justifiait pas.

**Métriques de succès**: hangs > 125 s = **0**, p99 < 90 s sur conv 65 K tokens, `compaction_global_timeouts_total / compaction_executions_total` < 1 % sur 24 h, accumulation `"compaction #N"` = **0** (toujours ≤ 1), banner visible < 1 s après `compaction_start`.

---

### ADR-087: Native ChatOpenAI + Config-Driven Per-Provider Reasoning Strategy

**Status**: ✅ ACCEPTED (2026-05-31)
**Fichier**: `docs/architecture/ADR-087-Native-ChatOpenAI-And-Per-Provider-Reasoning.md`

**Décision**: Suppression du `ResponsesLLM` custom (~1800 lignes) au profit du `ChatOpenAI` natif (`use_responses_api=True`) ; seul `ChatOpenAICached` (~1 méthode) est conservé pour le routage `prompt_cache_key` par préfixe statique. Le raisonnement est **piloté par la config, jamais injecté** : activé uniquement par les kwargs per-modèle du factory (`reasoning_builders`) selon la matrice "Configuration LLM", donc un bloc de raisonnement n'apparaît que pour les agents où l'admin l'a activé. La sortie structurée sur OpenAI-avec-raisonnement / Anthropic-avec-thinking passe par un **chemin auto-tool** (`tool_choice="auto"` — la seule combinaison supportée par l'API ; un tool forcé supprime le résumé sur OpenAI et renvoie 400 sur Anthropic). Verrou température/top_p sur Anthropic quand le thinking est actif (UI + service + factory). Paramètre `effort` global séparé pour opus-4-5 uniquement. Lié à ADR-078.

---

### ADR-088: Journal Write Restraint + Level-Routed Operational Injection + ReAct Directive Coherence

**Status**: ✅ ACCEPTED (2026-06-02)
**Fichier**: `docs/architecture/ADR-088-Journal-Restraint-And-Level-Routed-Injection.md`

**Décision**: Raffinement systémique du journal post-[ADR-079](#adr-079-stratified-journal-consciousness) contre la production d'entrées inutiles/nuisibles (sur-généralisation d'un trait de surface, hallucination de capacité). Trois piliers. **(1) Discipline d'écriture** : prompt d'extraction réécrit *restraint-first* (défaut `[]`, barre d'ancrage = signal explicite citable + sûr à appliquer aveuglément, interdits génériques dont « ne jamais affirmer une limite de ses propres capacités/accès/outils », L0 = soupape plafonnée 1/tour) ; prompt de consolidation dépressuré (L2 conditionnel à une vraie convergence, fin du mandat « you MUST create L2 », garde-fou dedup, promotion L0→L1 sur récurrence) ; persona alignée. **(2) Lecture routée par niveau** : `build_journal_context` n'injecte plus que **L1+L2** ; L0 (feedstock privé) et L3 (porté par le portrait) exclus par défaut via `JOURNAL_OPERATIONAL_INJECTION_EXCLUDE_LEVELS=["L0","L3"]` + paramètre `exclude_levels` sur le repo (défaut `None` → extraction/consolidation voient tout). **(3) Cohérence ReAct** : injection des directives L1/L2 une fois au `react_setup` (plafond par nombre `JOURNAL_REACT_CONTEXT_MAX_ENTRIES=3`, entières, sans troncature) ; self-eval reste ancré à `response_node`. Aucun changement de schéma ni migration. Amende ADR-079.

---

### ADR-089: Multi-Worker Prometheus Metrics — Multiprocess Aggregation

**Status**: ✅ IMPLEMENTED (2026-06-03)
**Fichier**: `docs/architecture/ADR-089-Prometheus-Multiprocess-Metrics.md`

**Décision**: Activer le mode **multiprocess de `prometheus_client`** pour agréger correctement les métriques des 4 workers uvicorn (`--workers 4`, même famille multi-worker que [ADR-063](#adr-063-cross-worker-cache-invalidation-via-redis-pubsub)). Le worker qui bind 9091 sert l'**agrégat de tous les workers** via `MultiProcessCollector` (`PROMETHEUS_MULTIPROC_DIR` posé par l'entrypoint, **gaté sur `--workers`** donc dev mono-worker inchangé, RAM `/dev/shm`, création **non-fatale** ; `mark_process_dead` au shutdown, vérifié au recyclage `--limit-max-requests`). **Les 45 Gauges reçoivent un `multiprocess_mode` explicite** (sinon défaut `'all'` → 1 série par PID → dashboards ×N) : `mostrecent` (26 — valeurs DB/config identiques inter-workers), `livesum` (14 — ressources par-worker à totaliser), `livemax` (4), `livemin` (1 = `mcp_server_health`). `lifetime_metrics_error_total` devient un `Counter` (n'est plus une gauge). **5 bugs d'instrumentation pré-existants corrigés** au passage (contrats de requête Grafana préservés) : `mcp_server_health`→`livemin`, `lifetime_metrics_error_total` Gauge→**`Counter`**, `channel_active_bindings` rafraîchi depuis la DB par l'updater (fin du priming/`inc`/`dec` par-worker), `registry_size`→`mostrecent`, `circuit_breaker_*`→`livemax`. Empreinte `/dev/shm` mesurée ~824 Ko (marge 75×). Aucun changement de schéma. Complète [ADR-020](#adr-020-triple-layer-observability-stack).

---

### ADR-090: Semantic Layer Governance — Ontology ∪ Manifests + Test-Enforced Integrity

**Status**: ✅ IMPLEMENTED (2026-07-02)
**Fichier**: `docs/architecture/ADR-090-Semantic-Layer-Governance.md`

**Décision**: Les **consommateurs de types sémantiques = union** des liens éditoriaux de l'ontologie (`core_types.used_in_tools`) et des annotations `semantic_type` des **paramètres de ToolManifest** (source vivante, rename-proof, couvre les tools MCP/user par requête) — helper partagé `collect_manifest_param_consumers()` utilisé par le planner ET l'initiative. Contexte : ~50% des `used_in_tools` étaient des **tools fantômes** (renommage v3.2 jamais répercuté) → ponts initiative silencieusement morts (contact→places) + noms hallucinables dans le prompt planner ; les manifests étaient déjà corrects et plus riches. **5 verrous d'intégrité testés** (`test_semantic_registry_integrity.py`) : used_in_tools ∈ tools réels (hint difflib), source_domains ∈ DOMAIN_REGISTRY (vocabulaire SINGULIER verrouillé), semantic_type manifests ∈ TypeRegistry, références internes de l'ontologie, et chaque `related_domains` de la taxonomie justifié par ≥1 pont de type sauf allowlist consciente (`{(file,contact),(reminder,contact)}`). **Pas de fusion** taxonomie↔registre (granularités/rôles différents) — gouvernance croisée par test. Nouveaux usages : section `<SemanticBridges>` de l'initiative (candidats pré-calculés types-produits × tools adjacents, caps 3 tools/type + 20 lignes) et prompt ReAct (règle PRECISION + `<CrossDomainDataTypes>`). Règle d'enrichissement : **annoter les manifests, pas l'ontologie** ; params `query` génériques jamais tagués (ambigus). Amende [ADR-062](#adr-062-agent-initiative-phase--mcp-iterative-sub-agent) et [ADR-070](#adr-070-react-execution-mode).

---

### ADR-091: Response-Context Prefetch — Initiative ∥ Response Latency Overlap

**Status**: ✅ IMPLEMENTED (2026-07-02)
**Fichier**: `docs/architecture/ADR-091-Response-Context-Prefetch.md`

**Décision**: Extraire le bloc d'injections contextuelles du response_node (embedding + mémoire + RAG user/system + journal + portrait + psyché — dépendantes du seul message utilisateur) dans `services/response_context.py`, et le **précharger depuis l'initiative_node** (registre process-local borné keyé run_id : `start_response_context_prefetch`/`pop_response_context`, idempotent, éviction+cancel à 64, timeout 20s) pour qu'il tourne **en parallèle de l'appel LLM initiative** (~12s) dans les DEUX modes (pipeline et ReAct), sans changement de topologie du graphe. Fan-out graphe `[finalize ∥ initiative]` évalué et **rejeté** (finalize ≈ ms, risques de super-step avec la boucle initiative pipeline). Miss (tour conversation, initiative off/skip, timeout) → fetch inline **identique** (zéro delta). Process-local sûr : aucun interrupt HITL entre initiative et response. Kill-switch `RESPONSE_CONTEXT_PREFETCH_ENABLED`. Gain ~0,5-2s/tour enrichi. Référence aussi les optimisations sœurs de la campagne 2026-07 (cache d'instances LLM keyé config résolue + invalidation sur reload clés/capabilities, négative-cache reasoning-stream (provider,model,path), warmup contacts non-bloquant, cache+single-flight embeddings RAG, memoization tiktoken du reducer, token batching SSE frontend par animation-frame, CSS `.lia-response` externalisé du LLM ~550 tokens/réponse). Amende [ADR-062](#adr-062-agent-initiative-phase--mcp-iterative-sub-agent).

---

### ADR-092: Replay-Safe HITL Interrupts — One Interrupt Per Node Execution

**Status**: ✅ IMPLEMENTED (2026-07-02)
**Fichier**: `docs/architecture/ADR-092-Replay-Safe-HITL-Interrupts.md`

**Décision**: Pattern normatif pour tout nœud HITL du graphe : **un `interrupt()` par exécution de nœud, tout état de boucle transite par le state via le `return` du nœud (checkpointé), l'itération passe par un self-loop conditionnel** — jamais de boucle in-node autour de `interrupt()`. Contexte : la sémantique de resume LangGraph ré-exécute le **nœud entier** — la boucle draft critique (`hitl_dispatch_node`) rejouait chaque `modify()` LLM passé (le contenu envoyé pouvait diverger de la dernière version affichée/approuvée), et la boucle FOR_EACH (in-orchestrator) rejouait la pré-exécution providers (appels API réels) + tous les filtres LLM passés. Appliqué ×2 : draft critique **single-pass** (edit/replan/clarify → 1 mutation LLM, persistée, self-loop via `route_from_hitl_dispatch` ; clarify affiche enfin sa question) et **nœud dédié `for_each_confirm`** (l'orchestrateur pré-exécute 1×, persiste `for_each_hitl_ctx` gardé par `plan_id`+`turn_id` ; APPROVE → reprise depuis le ctx **sans re-fetch** ; EDIT → filtre LLM 1× + `filtered_indices` cumulatifs vers les items originaux ; REJECT → cancel historique). **Invariant : ce que l'utilisateur a vu en dernier est exactement ce qui est exécuté ; aucun side-effect LLM/provider ne tourne plus d'une fois par décision.** Au passage, 2 clés state historiquement non déclarées dans `MessagesState` (updates silencieusement droppés) corrigées. Prouvé par harnais de replay compilés (vrais nœuds + routeurs + `InMemorySaver` + `Command(resume)`). Amende [ADR-044](#adr-044-draft--hitl-approval-flow) et [ADR-070](#adr-070-react-execution-mode) ; complète [ADR-022](#adr-022-langgraph-state--checkpointing).

---

### ADR-093: Security Hardening — Trusted Proxy Chain & XSS Sanitization Boundary

**Status**: ✅ IMPLEMENTED (2026-07-03)
**Fichier**: `docs/architecture/ADR-093-Security-Hardening-Proxy-XSS.md`

**Décision**: Deux durcissements de posture couplés. **(1) Chaîne proxy de confiance** : ports prod 8000/9091 bindés loopback (cloudflared = seule entrée publique ; SSR interne `web → http://api:8000` et healthchecks inchangés — le trafic compose passe par le réseau interne, pas les ports publiés ; Postgres 5432 laissé exposé LAN par décision utilisateur) + uvicorn `--proxy-headers --forwarded-allow-ips="*"` (sûr UNIQUEMENT grâce au binding loopback — invariant couplé documenté aux deux sites) + plus aucune lecture applicative du header `X-Forwarded-For` brut (spoofable) : `request.client.host` validé par uvicorn devient l'unique source d'IP client (slowapi, GeoIP, logs, rate limit auth). Le rate limit « par IP » redevient réellement par visiteur (fini le bucket global partagé via la gateway Docker). **(2) Frontière XSS** : `rehype-sanitize` inséré dans le pipeline markdown du chat (`rehypeRaw → rehypeSanitize → rehypeMathInText → rehypeKatex`, tout ce qui suit la frontière = étape de rendu math) avec un schéma audité contre tout le HTML légitime (cartes, callouts, boutons `data-action`, sentinelles MCP, `tel:`, `className` libéré sur les 7 tags que defaultSchema contraint — régression carte attrapée en validation visuelle) ; `script`/`iframe`/`form`/handlers supprimés, `<style>` strippé (rétrocompat messages pré-v1.21.0) ; `rehypeMathInText` (v1.21.13) rend les formules `$…$`/`$$…$$` situées dans le HTML de l'assistant en ne lisant que du texte déjà sanitizé (aucune nouvelle surface XSS) ; les MCP/Skill Apps ne passent jamais par le markdown (sentinelle → widget sandboxé). CSP frontend à nonces = suite optionnelle en défense en profondeur. Complète [ADR-034](#adr-034-security-hardening).

---

### ADR-094: Remove Dead Per-Node Message-Windowing Helpers

**Status**: ✅ IMPLEMENTED (2026-07-03)
**Fichier**: `docs/architecture/ADR-094-Remove-Dead-Per-Node-Windowing-Helpers.md`

**Décision**: Suppression d'un micro-sous-système **mort** dans `message_windowing.py` — les helpers `get_router_windowed_messages` / `get_planner_windowed_messages` / `get_orchestrator_windowed_messages` n'avaient **aucun call site** en prod (le router lit `state[STATE_KEY_MESSAGES]` directement), et les 3 settings qui les alimentaient (`router/planner/orchestrator_message_window_size` + constantes + `.env`) n'étaient consommés que par ces helpers morts ; seuls des **tests** les exerçaient encore (fake coverage). Retirés avec leurs settings/constantes/`.env`/tests. **Conservé** ce qui est vivant : `get_windowed_messages` (utilisé par `react_nodes`) et `get_response_windowed_messages` (utilisé par `response_node`) + `response_message_window_size` / `default_message_window_size`. Aucun changement de comportement (la troncature de tokens est déjà bornée par le reducer state-level `add_messages_with_truncate`). Le windowing per-nœud router/planner/orchestrator (vrai levier latence) est **différé au chantier latence**, à réintroduire avec benchmarks de qualité de routage/planification plutôt qu'en scaffolding inutilisé. Application de la règle CLAUDE.md « dead code deleted, not kept for later — wire it or remove it, record in a short ADR ». Complète [ADR-007](#adr-007-service-layer-pattern-for-node-complexity-reduction).

---

### ADR-095: Systemic Guards from the Wave-2 Audit

**Status**: ✅ IMPLEMENTED (2026-07-03)
**Fichier**: `docs/architecture/ADR-095-Systemic-Guards-Wave2-Audit.md`

**Décision**: La vague 2 de l'audit ferme **7 classes systémiques** de défaut à risque quasi nul — la livraison est la **garde** anti-récidive, pas seulement le correctif. **(1) Mutation JSONB in-place** (SQLAlchemy saute l'UPDATE silencieusement) : 4 sites corrigés en réassignation d'objet neuf, garde = **test AST** (`test_jsonb_mutation_guard.py`) qui découvre les colonnes JSONB des modèles et échoue en CI sur toute mutation in-place dans `src/`. **(2) PII à INFO** : contenus (adresse domicile/GPS, noms/emails de contacts, destinataires/objets, previews mémoires, params bruts) retirés des sites d'appel, garde = filet **sensible au niveau** dans `pii_filter.py` (`CONTENT_FIELD_NAMES` rédigés à INFO et au-dessus, laissés passer à DEBUG). **(3) Perte silencieuse d'outils** : `_import_tool_modules` **lève hors prod** + compteur Prometheus `tool_module_import_failures_total`, garde = **smoke test registre 3 couches** (import + sentinelle + invocation des ~95 outils). **(4) Fuite inter-cycle de facturation** : 3 chemins divergents unifiés sur `UserStatistics.reset_cycle()` qui remet à zéro **toutes** les colonnes `cycle_*` par introspection, garde = test multi-silo + sentinelle de couverture. **(5) Divergence zh/zh-CN** : `normalize_language` canonique unique dans `core/i18n.py` (les copies délèguent). **(6) Fallback non localisé** : `get_simple_fallback_message(language)` via `SSEErrorMessages` (6 langues). **(7) Docstrings mensongères** : 5 corrigées. Changement le plus structurant = la **frontière de logging PII** (contrat plateforme : contenus jamais au-dessus de DEBUG). Aucun changement de schéma DB, aucune migration, aucune nouvelle clé `.env` ; 1 métrique Prometheus. Complète [ADR-027](#adr-027-structured-logging-structlog) et le durcissement de la vague 1 ([ADR-094](#adr-094-remove-dead-per-node-message-windowing-helpers)).

---

### ADR-096: Performance, Network & Trust Boundaries from the Wave-3 Audit

**Status**: ✅ IMPLEMENTED (2026-07-03)
**Fichier**: `docs/architecture/ADR-096-Performance-Boundary-Hardening-Wave3-Audit.md`

**Décision**: La vague 3 de l'audit cible **trois frontières** que les vagues 1-2 n'avaient pas traitées, plus 4 correctifs perf/exactitude localisés — chaque item **mesuré avant/après** (latence ou nombre d'appels) et couvert par un test rouge-d'abord. **(A6) Blocage de l'event loop** : `messaging.send` Firebase, resize Pillow et embeddings sync gelaient toute coroutine concurrente (SSE inclus) → `asyncio.to_thread` + embeddings async natifs (`aembed_documents`/`aembed_query`) ; garde = **tests de stall de l'event loop** (`tests/helpers/event_loop.py`) : 261→11 ms, 496→12 ms, 251→11 ms. **(N-129) Requête User par appel + locale invalide** : `get_user_preferences` (25+ outils) interrogeait `User` à chaque appel et dérivait la locale en `f"{lang}-{lang.upper()}"` (→ `en-EN`, `zh-ZH` inexistants, cassant aussi les dates zh) → cache TTL par worker (`UserPreferencesCache`, invalidé sur update profil) + mapping `LANGUAGE_TO_LOCALE` (assert de complétude au boot) ; nouvelle clé `USER_PREFERENCES_CACHE_TTL_SECONDS`. **(N-175) Scan séquentiel sur chemin chaud** : `list_active_domains` → `asyncio.gather` par domaine (631→63 ms/10 domaines ; gain plein avec le pool V5). **(N-194.8) N+1 Gmail** : `search_emails` fetchait chaque message en séquentiel → `gather` borné (`EMAILS_SEARCH_FETCH_CONCURRENCY`, défaut 8) : 331→62 ms/10 résultats. **(N-213.2) Traductions broadcast recalculées à chaque lecture** : nouvelle colonne JSONB `admin_broadcasts.message_translations` remplie à l'envoi + backfill lazy, merge atomique côté serveur → 0 appel LLM en relecture ; **migration** `admin_broadcast_translations_001`. **(N-219.1) LLM non registré** : `PersonalityTranslationService` avec modèle/temp en dur et `llm_type` fantôme → slot `personality_translation` dans `LLM_TYPES_REGISTRY`/`LLM_DEFAULTS` + `get_llm()` + prompt versionné (visible dans l'UI admin, override DB honoré). **(A3) Exposition LAN** : 13 ports internes publiés en `0.0.0.0` (Docker court-circuite ufw) → bind `127.0.0.1`, `cloudflared` seul point d'entrée public (13→1 port) ; documenté dans `infrastructure/README.md` (contournement ufw, chaîne `DOCKER-USER`). **(A4) XSS greeting + CSP** : greeting LLM rendu via `dangerouslySetInnerHTML` → enfant React auto-échappé + CSP stricte dans `next.config.ts` (0 violation vérifiée sur 5 pages). **(N-194.10) Reply Gmail double-encodé** : corps construit avant `MIMEText` (parité `apple_email`) — défaut latent uniquement (non reproduit sur les runtimes réels), consigné comme durcissement. Une migration DB + 2 clés `.env` (caches perf, désactivables). Complète [ADR-093](#adr-093-security-hardening--trusted-proxy-chain--xss-sanitization-boundary) (durcissement XSS/proxy) et les vagues 1-2 ([ADR-094](#adr-094-remove-dead-per-node-message-windowing-helpers), [ADR-095](#adr-095-systemic-guards-from-the-wave-2-audit)).

---

### ADR-097: Concurrency, GDPR Purge & Skill Sandbox from the Wave-4 Audit

**Status**: ✅ IMPLEMENTED (2026-07-04)
**Fichier**: `docs/architecture/ADR-097-Concurrency-GDPR-Sandbox-Wave4-Audit.md`

**Décision**: La vague 4 traite la classe la **plus insidieuse** de l'audit — les défauts qui ne se manifestent que sous **concurrence** ou dans les scénarios de **vie du compte** (invisibles au test unitaire et à l'analyse statique). Protocole renforcé : en plus du rouge-d'abord, **chaque item porte un test de concurrence/intégration qui reproduit le défaut avant le fix** — « pas de reproduction, pas de fix ». **(A5a) `AsyncSession` partagée sous `asyncio.gather`** : `compute_overview` (1 résumé/kind) et `ContextAggregator` (10 fetchers, 8 sur `self._db`, erreurs masquées en `failed_sources` par `return_exceptions=True`) → boucle séquentielle pour health, **une session `get_db_context()` par fetcher** pour heartbeat (pattern `briefing/fetchers.py`) ; garde = repro Postgres réel (moteur poolé) : 7 sources perdues → 0. **(A5b) Purge RGPD incomplète** : `health_samples`+`health_metric_tokens` absents (user soft-delete → CASCADE inerte) et `last_known_location` non scrubé ; ajout au Group 2 + scrub location + auth token joint `User` (`is_active AND NOT deleted`, défense en profondeur → l'iPhone d'un compte supprimé ne peut plus ingérer) ; garde = 0 ligne santé/localisation post-suppression, écriture refusée (401). **(B6) État par-requête sur singletons (fuite cross-user)** : `journal_context` de `SmartPlannerService` sur `self` relu après `await` → journal de B dans le prompt de A ; passé en **paramètre explicite** (planner + 5 stratégies), `_current_journal_context` supprimé. `ConnectorTool.runtime` → **ContextVar task-local** (fuite timezone/langue), `SmartCatalogueService._metrics` → ContextVar ; garde = 2 users entrelacés, aucune fuite. **(N-179b) ToolMessages orphelins** : filtre « 5 derniers ToolMessages » + trim par tokens dissociait un ToolMessage de son AIMessage porteur → 400 OpenAI/Anthropic ; regroupement en **unités atomiques** (AIMessage+ToolMessages) + filet `enforce_tool_message_pairing` (2 sens) ; garde = balayage 45 combinaisons. **(N-183) datetime figé + double comptage** : `{current_datetime}` rendu au **build** (agents cachés à vie) → `DynamicDatetimeMiddleware` per-invocation ; le wrapper re-comptait tous les AIMessages de l'état complet à chaque invocation (coût quadratique) → comptage par **diff d'index**. Fix opportuniste : `ContextEditingMiddleware` retombait sur un edit dict (API `TruncateToolResult` disparue) sans `.apply()` → **crashait tout appel modèle de tout agent** (masqué par le retry) → vrai `ClearToolUsesEdit`. **(A1/A2) Sandbox skills vs socket Docker** : `run_skill_script` (ouvert à tout user) exécutait en **root** avec `/var/run/docker.sock` visible ; le masquage par namespace est impossible (pas de `CAP_SYS_ADMIN`) → **drop de privilèges** (`setgroups([])`→`setgid`→`setuid` dans `preexec_fn`) rendant le socket root-owned inatteignable + `RLIMIT_NPROC` effectif, plus **RLIMIT_AS/NPROC/FSIZE/CPU** ; DevOps intact (chemin séparé, toujours root) ; garde en conteneur : script non-dropé ouvre le socket/liste les conteneurs, dropé refusé, fork/mémoire/fsize/cpu bornés. **Écart consigné** : `group_add docker`+mount socket non retirés du compose (le drop de privilèges ferme déjà le vecteur sans risque de régression DevOps ni déploiement) — socket-proxy recommandé en défense-en-profondeur deploy-gated. Fix systémique opportuniste : mypy `platform = "linux"` (aligne hook host et CI Linux sur les API POSIX, 0 erreur/865 fichiers). Aucun changement de schéma DB, aucune migration ; clés `.env` sandbox désactivables. Complète les vagues 1-3 ([ADR-094](#adr-094-remove-dead-per-node-message-windowing-helpers), [ADR-095](#adr-095-systemic-guards-from-the-wave-2-audit), [ADR-096](#adr-096-performance-network--trust-boundaries-from-the-wave-3-audit)) sur l'axe concurrence & cycle de vie.

---

### ADR-098: CSP Widget Airlock — Per-Document Policies for Third-Party Widgets

**Status**: ✅ IMPLEMENTED (2026-07-04)
**Fichier**: `docs/architecture/ADR-098-CSP-Widget-Airlock.md`

**Décision**: La CSP stricte introduite par la vague 3 (A4, ADR-096) a cassé **trois familles de fonctionnalités** à l'exécution, faute d'inventaire des consommateurs et de tests : (1) **toute la voix** — 5 chemins chargent du JS depuis des URL `blob:` (worklet PTT, worklets KWS/recording du mode vocal, loader glue Sherpa) et la destination fetch d'un worklet relève de **`script-src`**, pas de `worker-src` → ajout de `blob:` à `script-src` ; (2) **la skill interactive-map** — embed Google Maps bloqué par le repli `frame-src → default-src 'self'` → directive `frame-src 'self' https://www.google.com` explicite ; (3) **les widgets MCP Apps** (Excalidraw) — rendus en `srcDoc`, qui **hérite de la CSP parente sans échappatoire**, alors qu'ils chargent leur runtime depuis des CDN (esm.sh). Pour (3), plutôt qu'allowlister chaque CDN (whack-a-mole qui affaiblit toute l'app et forclot un futur `script-src` par nonces), le **sas** : une CSP étant liée à la *réponse HTTP*, `McpAppWidget` pointe son iframe sandboxée vers un shell statique same-origin (`public/widget-frame.html`) servi avec **sa propre CSP permissive** (entrée `headers()` dédiée, rule global en lookahead négatif — deux headers CSP = intersection), et lui livre le HTML par `postMessage` ; le shell fait `document.write()` (même Window → bridge JSON-RPC intact, origine opaque `"null"` inchangée). L'isolation des widgets n'a jamais été la CSP mais le `sandbox` sans `allow-same-origin` — la seule directive de sécurité réelle du sas est `frame-ancestors 'self'`, doublée de 5 verrous dans le shell (inerte hors sandbox/top-level, source=parent, origin=app, single-shot). Alternative « origine dédiée » (modèle web-sandbox ChatGPT) jugée disproportionnée (DNS/cert/proxy/tunnel RPi5) ; à revisiter si un widget exige `allow-same-origin`. Les skills user `frame.html` restent volontairement en `srcDoc` (auto-contenues + meta-CSP backend plus stricte). **Consolidation** : les deux politiques extraites dans `src/lib/csp.ts` (module pur importé par `next.config.ts` ET les tests) — chaque directive porteuse de fonctionnalité est épinglée par un test de non-régression (22 tests, `csp.test.ts` + `McpAppWidget.test.tsx`). Validation E2E dev : module esm.sh + importmap à travers le sas, worklet `blob:`, embed Maps, spoof frère rejeté, second payload ignoré, 0 violation console. Aucune migration, aucune clé `.env`.

---

### ADR-099: Remove Dead nginx Reverse-Proxy Config

**Status**: ✅ IMPLEMENTED (2026-07-04)
**Fichier**: `docs/architecture/ADR-099-Remove-Dead-Nginx-Config.md`

**Décision**: Suppression de `infrastructure/nginx/` (Dockerfile + nginx.conf, 8,9 Ko) — livré avec la v1.0.0 initiale et **jamais câblé** : aucun compose de tout l'historique ne l'a référencé (`git log -S` vide), aucun script de déploiement (l'ingress prod est le tunnel `cloudflared` hôte, ADR-096). Config morte **activement trompeuse** : sa CSP globale permissive (`default-src 'self' http: https: … 'unsafe-inline'`) contredit la politique réelle (`src/lib/csp.ts`, ADR-098) et a dû être écartée comme seconde source CSP potentielle pendant l'investigation du sas (deux headers CSP = intersection) ; ses autres headers divergent de `next.config.ts`. Application de la règle systémique dead-code (« wire it or remove it »). `infrastructure/ssl/` **conservé** (generate-certs.sh vivant, monté par `docker-compose.dev.yml` pour les certs HTTPS dev) ; `infrastructure/README.md` mis à jour. Un futur reverse proxy se réécrira contre les headers alors courants — ne pas ressusciter ce fichier.

---

### ADR-100: Native Structured Output vs "Output JSON" Prompt Conflict

**Status**: ✅ IMPLEMENTED (2026-07-04)
**Fichier**: `docs/architecture/ADR-100-Structured-Output-Prompt-Conflict-Guard.md`

**Décision**: Incident « dessine-moi le cycle de l'eau » (blocage 2 min puis carte Google au lieu d'un diagramme Excalidraw) → 5 défauts, dont une **classe systémique** (D5) : le validateur sémantique appelait `get_structured_output` (tool call forcé) sur un prompt disant « Output JSON only » — sur `deepseek-v4-flash` le modèle répondait en JSON texte 2 fois sur 3 → `None` → `StructuredOutputError` → validateur **fail-open** silencieusement mort (100 % d'échec). **Filet runtime** : `_get_native_structured_output` passe par un wrapper `include_raw=True` et `_rescue_structured_from_text` récupère le JSON du message brut (fences ```json```, JSON dans la prose, list-content Gemini 3.x) — protège TOUS les consommateurs natifs. **Convention de prompt** : les prompts en structured output natif ne doivent JAMAIS demander une sortie JSON-texte ; balayage complet → 4 prompts nettoyés (`semantic_validator`, `memory_reference_extraction` — corrige aussi un exemple en tableau nu contredisant le schéma, `heartbeat_decision`, `hitl_classifier`), 5 prompts laissés intacts car ils parsent le JSON **manuellement** (`extract_json`/`json.loads`, légitime : planner, emails, skill-translation). Distinction : parse manuel → « output JSON » requis ; natif → « output JSON » = bug. Corrige aussi D1 (timeout famille MCP `*_task` 120→300 s floor / 600 s ceiling + budget plan 120→600 s ; le create_view Excalidraw était tué à ~10 s du but), D2 (verrou `_resolve_plan_skill_name` : drop d'un `skill_name` incohérent avec la détection QueryAnalyzer), D3 (`_plan_execution_failed` : pas d'activation skill quand le plan a totalement échoué), D4 (logs replanner honnêtes — retry/replan non câblés — + suppression de messages FR inline morts). Repro modèle réel : validateur 3/3, memory 3/3, HITL 3/3. Nouveau setting `mcp_react_step_max_timeout_seconds` (+ .env). Aucune migration.

---
### ADR-101: Calendar Search Hardening (list-and-filter, date reset, volumetry cap)

**Status**: ✅ IMPLEMENTED (2026-07-04)
**Fichier**: `docs/architecture/ADR-101-Calendar-Search-Hardening.md`

**Décision**: « mes prochains rdv médicaux » / « le rdv hotel particulier » marchaient en ReAct mais échouaient aléatoirement en Pipeline. Causes racines multiples (analyse par API) : (1) le `q` Google Calendar est un plein-texte **faible** (échoue sur catégories « médical » ≠ « Dentiste » et accents « hôtel »), (2) le planner hallucine parfois un `time_max` étroit pour une requête ouverte, (3) asymétrie inter-API (Gmail fort → intouchable, Tasks sans recherche titre déjà en list-and-filter, Contacts/Drive dédiés), (4) le cap de volumétrie global était **contourné** par 5 clients. **4 volets déterministes** : (a) l'outil agenda n'envoie plus le texte-libre au `q` — seule une **personne résolue en email** (invité) est gardée, le reste est **droppé** et le Response LLM filtre le concept (modèle Tasks/ReAct) ; supprime la liste en dur `GENERIC_CALENDAR_QUERY_TERMS`. (b) nouveau booléen analyzer **`has_temporal_reference`** (12/12) → le validateur vide la borne de fin (`search_role="range_end"` déclaré au manifest) pour les requêtes **sans référence temporelle** (« prochains », « mes 3 prochains rdv »), préserve les dates explicites (« le 15 août », « les 2 prochains jours ») ; kill switch `planner_open_query_date_reset`. (c) **cap centralisé** via `apply_max_items_limit` — 5 bypass corrigés (Calendar Google, Apple ×3, Microsoft calendar) + **guard AST** anti-oubli + relèvement global 10→25 et calendar 10→25 (constants + .env). (d) **transparence** : flag `truncated` + fenêtre en metadata pour que la réponse indique la période et invite à affiner. Résidus documentés (ReAct les partage). Suite unit verte, lint/mypy propres.

---
### ADR-102: Domain Vocabulary Single Source (nom singulier vs result_key)

**Status**: ✅ IMPLEMENTED (2026-07-04)
**Fichier**: `docs/architecture/ADR-102-Domain-Vocabulary-Single-Source.md`

**Décision**: Le vocabulaire des domaines vit sur **deux axes**, tous deux dérivés de la source unique `DOMAIN_REGISTRY` : le **nom singulier** (clé du registre, porté au runtime par `primary_domain`/`domains`/`source_domain`) et le **result_key pluriel** (`DomainConfig.result_key`, porté par `$context.<key>`, `CONTEXT_DOMAIN_*`, `structured_data`). Des tables dérivées avaient dérivé vers le mauvais axe → comparaisons **silencieusement jamais satisfaites** (erreur silencieuse ou latence de retry), masquées par des tests nourrissant la même forme erronée. Audit exhaustif de tous les sites de comparaison → **4 défauts inertes corrigés** : (A) `CROSS_DOMAIN_MAPPINGS` cible `places`→`place` (vs `primary_domain` singulier) — réactive le bypass LLM cross-domain (~800 ms/plan économisés) ; (B) `_GOAL_PATTERNS` `contacts/emails/events/tasks/drive`→singulier `contact/email/event/task/file` (vs `domains` singulier) ; (C) `valid_context_domains` `drive`→`files` (vs `$context.<result_key>`) — `$context.files.0` n'est plus rejeté ; (D) table `_detect_domain_from_agent_results` `files→drive, weather, articles→wikipedia, results→perplexity`→result_keys `files/weathers/wikipedias/perplexitys` (vs `item.meta.domain`) — restaure la résolution ordinale par domaine (STRATEGY 3). **Garde permanente** : `test_domain_vocabulary_parity.py` (modèle ADR-085), stricte par axe sur les tables de comparaison + tolérante (types auxiliaires `calendar(s)/location(s)/mcp_app(s)/skill_app(s)` + alias d'affichage légacy) sur les tables définitionnelles/affichage ; ROUGE avant, VERT après, échoue sur tout futur token hors vocabulaire. C et D promus en constantes de module (`VALID_CONTEXT_REFERENCE_DOMAINS`, `_DATA_KEY_TO_RESULT_KEY`) ; tests masquants corrigés au singulier runtime. **Kill switch** `planner_cross_domain_bypass_enabled` (défaut `True`, `.env*`) pour le bypass réactivé (OFF = fallback planner LLM). Hors scope documenté : les maps d'affichage tolérantes aux alias (non des tests de condition). Non-régression : 8800 tests fast verts (+23), Black/Ruff/MyPy strict (865 fichiers) propres, runtime sain. Aucune migration.

---
### ADR-103: HITL Backend Internationalization (français en dur éliminé)

**Status**: ✅ IMPLEMENTED (2026-07-05)
**Fichier**: `docs/architecture/ADR-103-HITL-Backend-i18n.md`

**Décision**: La couche HITL backend restait structurellement francophone pour les 5 autres langues. Règle appliquée (déjà posée par `core/i18n.py` « LLM prompts are NOT translated ») distinguant **deux catégories** : (1) **scaffolding LLM** (fragments de prompt, labels de contexte, few-shot) → **anglais** (la langue de sortie est pilotée par l'instruction `{user_language}`) ; (2) **messages émis / visibles** (injectés dans la conversation, ou fournis au response node) → **localisés 6 langues** via les mécanismes i18n centraux. Traitements : `draft_modifier` scaffolding → anglais ; **few-shot du classifier externalisé** en prompt versionné `hitl_classifier_examples.txt` (anglais, sections par action_type, loader caché) + descriptions d'action → anglais (supprime le biais FR de classification) ; reformulations EDIT + message REJECT enrichi → 6 langues via `HitlMessages` (`get_reformulation`/`get_reject_enriched_message`, clés par **`ReformulationKind` StrEnum** + test d'exhaustivité anti-message-vide) ; fallback de refus `agent_results` → 6 langues (`get_user_refused_action`). Langue lue de l'**état checkpointé** (`MessagesState.user_language`) via `resolve_user_language`, threadée en paramètre (jamais sur `self`, concurrency-safe). **Garde permanente** : `test_i18n_parity.py` (modèle ADR-085) — scan récursif des modules `core.i18n_*`, échoue si une table lang-keyed manque une langue (a révélé + corrigé un trou `zh-CN` réel dans `_DISPLAY_OPEN_NOW`) ou si les clés d'une table `dict[lang, dict[key]]` divergent entre langues (`i18n_patterns` exclu de la key-parity car ses maps de mots-clés keyent sur les mots propres à chaque langue). E2E de/zh (EDIT+REJECT) sans FR. Hors scope documenté : fallbacks génériques non-HITL de `agent_results`. Non-régression : suite fast verte, Black/Ruff/MyPy strict propres, runtime sain. Aucune migration.

---

### ADR-104: Psyche De-Saturation (mood confiné → source-level fix)

**Status**: 🎯 PROPOSED (implémenté, validation Phase-2 en attente avant déploiement) (2026-07-05)
**Fichier**: `docs/architecture/ADR-104-Psyche-De-Saturation.md`

**Décision**: L'analyse de 3 mois de données prod (749 snapshots) a prouvé que la psyché v1 (ADR-068) n'était pas *faible* mais **confinée/saturée** : humeur bloquée dans l'hémisphère A+D+ (100%), **4 humeurs sur 14** atteintes, **pride 61%** dominant (pulse auto déclenché à chaque message), 4 émotions jamais activées (gratitude/empathy/nervousness/wonder), intensité ≥0.60 pour 61%, dominance jamais < 0.37 (= baseline Mehrabian `+0.60·C` de la personnalité). Correctif **au niveau de la source** : (**F3**) suppression du pride-pulse automatique — la fierté est désormais méritée via l'appraisal ; (**F6**) débiais du prompt de self-report (palette complète, intensités basses) ; supports (**F2**) `PSYCHE_BASELINE_DAMPING=0.75`, (**F4**) `PSYCHE_EMOTION_MAX_ACTIVE` 7→4 + `PSYCHE_EMOTION_DECAY_RATE` 0.3→0.4 ; (**F1**) relaxation anti-ratchet asymétrique `PSYCHE_AD_RELAXATION=0.15` — **d'abord livrée off, puis réactivée** : la sim synthétique suggérait qu'elle réduisait la variété, mais la **validation Phase-2a avec un vrai LLM** a montré le contraire (le self-report réémet les émotions high-arousal de la personnalité tour après tour → ratcheting A→0.84 sans elle ; 0.15 borne la montée tout en laissant, grâce à l'asymétrie, une conversation de deuil descendre l'arousal à −0.43 → serene/reflective). **Phase-2a validée** (gemini-2.5-flash, Cynic+Ami) : pride 61%→0-12%, palette ouverte (empathy/tenderness/serenity/melancholy émis), différenciation par personnalité, registre calme atteint. Tout paramétrable `.env`, aucune migration, 8 tests déterministes + 166 verts. **Reste** : re-mesure prod post-déploiement. L'ADR contient une **matrice de réajustement** (« si donnée X → action Y »). Voir [ADR-068](ADR-068-Psyche-Engine.md) et [ADR-105](ADR-105-Psyche-Embodied-Expression.md).

---

### ADR-105: Psyche Embodied Expression Layer (A-E)

**Status**: 🎯 PROPOSED (implémenté derrière un flag, validation prod élargie en attente) (2026-07-05)
**Fichier**: `docs/architecture/ADR-105-Psyche-Embodied-Expression.md`

**Décision**: Une fois l'état désaturé (ADR-104), une **éval aveugle** a montré que l'état ne *transparaissait* toujours pas : l'injection décrivait l'humeur par des **adjectifs abstraits** (`MOOD: melancholic — quiet, measured`) que le LLM ignore — un Cynic forcé mélancolique répondait *aussi brillamment que sans injection*. Correctif : remplacer les directives-adjectifs par un bloc `<InnerVoice>` de **grammaire d'expression incarnée** — (A) moves de FORME concrets (ouverture, longueur de phrase, rythme, registre, énergie, licence d'être bref/expansif) par humeur (`MOOD_EXPRESSION_GRAMMAR`, 14 humeurs, assert boot) ; (C) cadrage « c'est ta voix maintenant », pas un label ; (D) réconciliation avec `<Personality>` ; (B/E) autorité explicite sur la forme (longueur, nb de suggestions). `format_embodied_prompt_injection` + branchement dans `process_pre_response` sur le flag **`PSYCHE_EMBODIED_INJECTION`** (défaut on ; le format gradué legacy reste le rollback `.env`). Wrapper `<InnerState>` (« invisible/not content ») supprimé ; clause d'autorité ajoutée à `<ResponseGuidelines>`. `format_rich` mort supprimé. **Éval aveugle validée** (Cynic, gemini-2.5-flash) : l'humain a choisi l'incarné pour les 2 humeurs — seul rendu *subtil* sur le mélancolique. 7 tests déterministes, 171 verts, mypy/ruff/black clean, aucune migration. **Reste** : rounds aveugles élargis + re-mesure prod, puis retrait du flag/legacy. Voir [ADR-104](ADR-104-Psyche-De-Saturation.md).

---

### ADR-106: HITL Contract Coherence — Unified Confirmation Across Pipeline & ReAct

**Status**: ✅ IMPLEMENTED (2026-07-06)
**Fichier**: `docs/architecture/ADR-106-HITL-Contract-Coherence.md`

**Décision**: **Un seul contrat HITL : tout interrupt porte un `action_requests` typé, est rendu par son interaction et résumé par sa branche `_parse_approval_decision` ; ReAct n'a plus de dialecte propre — sa confirmation pré-exécution réutilise l'interaction partagée `tool_confirmation`, comme le pipeline.** Contexte : deux mécanismes de déclenchement câblés incohéremment — **output-driven** (`requires_confirmation` → draft → `hitl_dispatch`, marche dans les deux modes) et **flag-driven** (`permissions.hitl_required`, consommé **uniquement** par `react_tool_selector` ; le pipeline ne gate pas dessus, `approval_gate` = pass-through). Trois défauts : (1) l'interrupt `react_tool_approval` de ReAct n'avait **pas d'`action_requests`** → non rendu par le streaming (hang silencieux) ni résumable ; (2) **4 tools delete/cancel** (`delete_email/event/label`, `cancel_reminder`) draft-based portaient un `hitl_required=True` **périmé** (vs `delete_contact`/`delete_task` à False) → suppression en ReAct = hang ; (3) le batch `draft_critique` codait en dur le vocabulaire de **suppression** pour tout type (un envoi affichait « Confirmes-tu cette suppression ? » sans destinataire). Décision ×4 : (a) **sémantique `hitl_required`** = confirmation pré-exécution pour mutation **non-draft** uniquement ; 4 flags corrigés à False + **invariant testé** (`test_hitl_required_consistency.py` scanne les 95 tools, allowlist = `{delegate_to_sub_agent_tool}` + tools MCP utilisateur runtime) ; (b) **gate ReAct unifié** sur `tool_confirmation` (`action_requests` typé → rendu par `ToolConfirmationInteraction` + persisté Redis) ; (c) **branche resume `tool_confirmation`** → `{"action": "confirm"|"cancel"}` (répare aussi le **pipeline** : `tool_confirmation` tombait sur `{"decision":"APPROVE"}` que `_handle_tool_confirmation` annulait toujours ; défaut sûr = cancel ; ReAct exécute seulement sur `confirm`/`approve`) ; (d) **wording batch dérivé du registre ADR-085** (`verb_past_key=="deleted"` → destructif ; sinon question neutre FOR_EACH) + `item_recipient_field="to"` sur les drafts d'envoi → lignes `📧 Email à <destinataire> : <sujet>` (0 chaîne i18n neuve, 6 langues réutilisées + connecteur `DRAFT_RECIPIENT_CONNECTOR`). Conséquences : plus de dialecte ReAct ni de hang silencieux ; défaut plus sûr ; bonus systémique (pipeline tool_confirmation réparé) ; classe de dérive verrouillée en CI. Aucune migration/config/front. Vérifié : 896+ tests verts, ruff/black/mypy clean, boot conteneur sain, l'interrupt ReAct émet enfin un chunk `hitl_interrupt_metadata`. Amende [ADR-044](#adr-044-draft--hitl-approval-flow) et [ADR-070](#adr-070-react-execution-mode) ; étend le registre [ADR-085](#adr-085-draft-display-registry--single-source-of-truth-for-post-hitl-rendering).

### ADR-107: Dead-Code Remediation (S7) — moteurs v3, framework d'approbation plan-level, orchestrateur HITL fantôme

**Status**: ✅ IMPLEMENTED (2026-07-07)
**Fichier**: `docs/architecture/ADR-107-Dead-Code-Remediation-S7.md`

**Décision**: **Suppression de ~13 600 lignes de code mort en 5 clusters validés un à un**, chaque frontière vivante étant prouvée avant retrait (grep tous-scopes → graphe d'imports AST/clôture de démarrage → « simulated deletion » par import-hook sur `src.main` + suite complète → baseline verte / suppression / suite verte / boot Docker frais healthy). Retirés : (1) `manifest_builder.py` (builder fluent jamais appelé, `ToolManifest` vit dans `catalogue.py` — repoint TYPE_CHECKING) ; (2) `state_keys.py` (copie parallèle inutilisée des constantes d'état) ; (3) contacts v2 (`contacts_models`/`contacts_validators` + script debug) ; (4) **moteurs v3** (`autonomous_executor`/`feedback_loop`/`relevance_engine` + barrel `v3/`, configs/settings/constantes inertes, 9 vars `.env` ×2, sections mortes de `get_debug_thresholds`) ; (5) **framework d'approbation plan-level** (`plan_editor.py`, package `services/approval/`, 4 helpers morts d'`approval_gate_node` 626→130 L, classes schemas mortes, champ state `approval_evaluation` jamais écrit) **+ `hitl_orchestrator.py` (987 L) : service fantôme instancié dans `graph_management` mais jamais accédé** — preuve empirique : suite complète avec le module bloqué au runtime, seuls ses tests fantômes tombent — et son package `hitl/policies/` (importé uniquement par lui). Nettoyés dans la foulée : 18 métriques Prometheus orphelines (labellisées → n'émettaient déjà aucune série), 7 méthodes + 11 dicts orphelins d'`i18n_v3` (−381 L), 11 recording rules + 7 alertes mortes (`promtool` vert), 23 panels morts des dashboards Grafana 07/08, ~10 fichiers de tests fantômes (dont `test_hitl_flows_e2e.py` qui patchait un module supprimé avant ce chantier). **Gardés (prouvés vivants)** : `approval_gate_node` pass-through câblé (réactivation plan-level = restaurer un `interrupt()`, pas de re-câblage), `PlanSummary`/`StepSummary`/`PlanApprovalInteraction` (= **fallback du registry HITL** pour tout `action_type` inconnu), `V3RoutingConfig` (alias `get_routing_thresholds` du query analyzer), `V3DisplayConfig`, `i18n_v3.V3Messages` (cartes), métriques `for_each_*` et `hitl_plan_approval_question_duration`. Vérifié : 0 nouvel échec sur toute la chaîne (deltas = exactement les tests fantômes), 10 982 tests collectés sans erreur d'import, ruff/black/mypy verts sur tout le backend (848 fichiers), 5 boots Docker healthy, `/metrics` contrôlé (gardées présentes / retirées absentes), chaque frontière vivante exercée au runtime dans le conteneur. Couverture réelle stable (les tests retirés ne couvraient que du code retiré). Voir [ADR-106](#adr-106-hitl-contract-coherence--unified-confirmation-across-pipeline--react) (documentait déjà le pass-through).

### ADR-108: BaseAPIKeyClient Adoption — base durcie, cycle de vie déterministe, migration des clients API-key

**Status**: ✅ IMPLEMENTED (2026-07-07)
**Fichier**: `docs/architecture/ADR-108-BaseAPIKeyClient-Adoption.md`

**Décision**: **Adoption de `BaseAPIKeyClient` par les 3 clients API-key (Brave, OpenWeatherMap, Perplexity) en 5 étapes caractérisation-d'abord** — le contrat public de chaque client est figé par des tests écrits contre l'ANCIENNE implémentation et conservés verbatim à travers la migration (37 tests : 13+14+10, verts avant/après). (**F0**) La base est durcie AVANT adoption : contrat d'erreurs domaine (`ExternalServiceError` circuit-open/401-403 [modèle `raise_google_api_error`], `httpx.HTTPStatusError` 4xx non-auth, `MaxRetriesExceededError` épuisement avec `last_error`, `RateLimitError`), `rate_limit_per_second` **float** (free tiers) + `max(1,int(×60))`, hook `_get_http_timeout()` + `follow_redirects`, `user_id: UUID | None` ; **`CircuitBreaker.check()` public créé** (corps d'`__aenter__`, DRY avec `protect()`) et l'usage des privés du CB éliminé des 3 bases (api-key, oauth, apple — apple y gagne lock/état réel/retry_after/métrique rejected). (**F1**) Cycle de vie déterministe : **`ToolDependencies.aclose()`** ferme les clients cachés en fin de run (chemins succès+erreur de `stream_chat_response` + warmup) ; try/finally sur les 4 sites directs (web_search ×2, heartbeat aggregator+geocoding) — fuite réelle : zéro `close()` nulle part (briefing fermait déjà, pattern exemplaire ; caches KE/interests = singletons bornés, pooling voulu). (**F2-F4**) Migrations à **constructeurs/signatures inchangés** : Brave garde son None-on-error, OWM son contrat levant + geo listes + agrégation timezone, Perplexity ses payloads/fallbacks. Deltas intentionnels documentés : 5xx retryé, épuisement → `MaxRetriesExceededError` (except du fetch météo briefing synchronisé, classification via `last_error`), 401 → `ExternalServiceError` (consommateurs en except large — vérifié), CB par service + Redis-RL quand activé. **EXCLUS (analyse profonde ayant renversé l'intuition « Hue d'abord »)** : PhilipsHue (dual-mode, OAuth refresh, composition BaseAppleClient délibérée), Wikipedia (keyless), geocoding Google, clients image/TTS (axe LLM). Vérifié : 0 nouvel échec à chaque jalon (F0 10 102 / F1 10 107 / F2 10 120 / final), mypy vert sur les 38 fichiers clients, boots Docker healthy, smoke runtime conteneur (héritage, close idempotent, None-on-error live). Harnais de caractérisation MockTransport réutilisable + isolation du registry CB par test (piège d'ordre latent corrigé). Suit [ADR-107](#adr-107-dead-code-remediation-s7--moteurs-v3-framework-dapprobation-plan-level-orchestrateur-hitl-fantôme).

### ADR-109: PostgreSQL Backup Strategy — sidecar pg_dump avec restauration testée

**Status**: ✅ IMPLEMENTED (2026-07-08)
**Fichier**: `docs/architecture/ADR-109-PostgreSQL-Backup-Strategy.md`

**Décision**: **Sauvegarde automatisée de la base prod (RPi5) par sidecar `prodrigestivill/postgres-backup-local:16-alpine`** dans les deux compose — clôt le premier risque opérationnel relevé par l'audit 360° du 2026-07-07 (aucun outillage de backup versionné, RPO indéfini). Choix sidecar vs script cron custom tranché sur preuves : rétention native jours/semaines/mois (= exigence exacte), arm64 vérifié au manifest, `pg_dump 16.10` embarqué aligné sur le serveur `pg16`, healthcheck intégré à l'image (vérifié par inspect), déclenchement manuel en une commande (`/backup.sh`) — un script custom = ~200 lignes de rotation/verrouillage réinventées à coût runtime égal. Tout paramètre en `.env` section **[80]** (`POSTGRES_BACKUP_SCHEDULE/KEEP_DAYS/KEEP_WEEKS/KEEP_MONTHS/HOST_DIR/EXTRA_OPTS/TZ`), consommé par compose uniquement — pas de module Settings (pattern `GRAFANA_ADMIN_USER`). `POSTGRES_EXTRA_OPTS` épinglé explicitement à `-Z6 --clean --if-exists` (base complète sans filtre de schéma, restauration auto-nettoyante en UNE commande) — ne jamais dépendre des défauts de l'image. Stockage prod = bind mount hôte `chmod 700` créé par `deploy.sh` AVANT le `up` (prêt pour l'rclone off-site phase 2) ; dev = volume nommé (hardlinks non fiables sur bind Windows) — le script de vérif lit via `docker cp`, rendant le type de stockage transparent. **La restauration est prouvée, pas déclarée** : `infrastructure/docker/backup/verify-backup.sh` (livré au Pi via le bundle PROD) restaure le dernier dump dans un conteneur `pgvector:pg16` jetable et compare `alembic_version`, nombre de tables public et comptages de 3 tables de référence (dérive live = WARN ; erreur SQL / mismatch schéma / table vide = FAIL). Tasks `backup:now` / `backup:verify` ; runbook complet `DATABASE_BACKUP_RESTORE.md` (restauration jetable ET prod avec suites systémiques : contrôle alembic vs code déployé, FLUSHALL Redis, restart API). RPO : indéfini → **≤ 24 h** paramétrable ; RTO en minutes. Limites assumées phase 2 : copie off-site chiffrée rclone (les dumps partagent le NVMe de la base), volumes `attachments_data`/`skills_data` non couverts, pas de PITR, pas d'alerte push sur échec (hooks webhook disponibles). Vérifié : backup réel + restauration jetable en dev (0 erreur SQL, alembic identique repo/source/restauré, comptages identiques), `docker compose -f docker-compose.prod.yml config` sans erreur.

### ADR-110: Backup Encryption — analyse d'options (différée)

**Status**: 🧊 DEFERRED (options analysées le 2026-07-08, mise en œuvre volontairement reportée — pas d'urgence)
**Fichier**: `docs/architecture/ADR-110-Backup-Encryption-Options.md`

**Décision**: **Différer le chiffrement des sauvegardes, avec la voie tracée pour le jour venu.** Constat systémique qui structure l'analyse : la base vivante (`postgres_data`) est elle-même en clair sur le même NVMe (Fernet couvre les colonnes PII, pas les datafiles) — chiffrer seulement les dumps sur ce disque n'apporte quasi rien contre le vol/la mise au rebut du support ; chaque menace a son mécanisme propre. Trois options instruites : (**A — recommandée à la reprise**) job `rclone crypt` vers une cible locale (idéalement SSD USB sur le Pi → protège aussi de la mort du NVMe, limite n°1 de l'ADR-109) ; ne touche pas à la rotation du sidecar et EST le mécanisme de la phase 2 off-site (bascule de backend le jour venu) ; ~une demi-journée avec drill de restauration depuis la copie chiffrée. (**B — rejetée sous cette forme**) chiffrement asymétrique age au moment du dump via hooks : la propriété est la plus forte (clé privée hors du Pi) mais les hooks se battent contre le moteur de rotation de l'image (hardlinks daily/weekly/monthly + purge par suffixe `.sql.gz`) — reviendrait au script custom écarté par l'ADR-109 ; la propriété arrive proprement avec rclone crypt off-site. (**C — décision distincte**) LUKS au niveau du disque : seule vraie réponse au vol physique (couvre base vivante + dumps), mais chantier d'exploitation sérieux sur un Pi headless (déverrouillage au boot, migration des volumes Docker, reboot non assisté) — à traiter par son propre ADR si le vol physique entre dans le modèle de menace. Déclencheurs de reprise : support USB disponible (A local), cible off-site choisie (A complète), vol physique au modèle de menace (étude C). D'ici là : dumps en clair `chmod 700` sur le NVMe — posture ADR-109 inchangée, désormais avec les options et leurs modèles de menace au dossier. Suit [ADR-109](#adr-109-postgresql-backup-strategy--sidecar-pg_dump-avec-restauration-testée).

### ADR-111: LangGraph Postgres Connection Pooling — checkpointer & store

**Status**: ✅ IMPLEMENTED (2026-07-08)
**Fichier**: `docs/architecture/ADR-111-LangGraph-Postgres-Connection-Pooling.md`

**Décision**: **Remplacement des connexions PostgreSQL uniques du checkpointer et du store LangGraph par des `psycopg_pool.AsyncConnectionPool`** — lève le goulot de scalabilité n°1 de l'audit S2/A7 (toutes les conversations concurrentes d'un worker faisaient la queue sur UNE connexion, verrouillée par l'`asyncio.Lock` d'instance de langgraph, pour CHAQUE lecture/écriture de checkpoint). Piège amont découvert et contourné : en `langgraph-checkpoint-postgres==3.1.0` (dernière version PyPI, `main` non corrigé, issue langchain-ai/langgraph#7259), seul le **store** est pool-aware — le `_cursor` du **saver** tient `self.lock` inconditionnellement, pool inclus, donc un pool seul n'apporte AUCUNE concurrence au checkpointer. Correctif : **override ciblé de `_cursor` dans `InstrumentedAsyncPostgresSaver`** répliquant verbatim le corps amont, seul le choix du lock change (lock frais no-op si pool, lock partagé sinon — comportement mono-connexion bit-for-bit identique) ; preuve de sûreté : la prod tourne déjà avec 4 workers écrivant concurremment dans les mêmes tables sans verrou inter-process — le lock d'instance ne peut pas porter de garantie de cohérence, seulement l'exclusivité d'une connexion, que le checkout du pool garantit déjà (raisonnement écrit par les auteurs langgraph dans le `_cursor` du store). Risque d'override borné : versions pinnées, **test canari** qui échoue au premier bump corrigeant #7259 (ordre de retrait explicite), canari secondaire sur le pattern du store, précédent assumé `_deepseek_patched.py`. Tailles par worker en settings Pydantic + `.env` (`LANGGRAPH_CHECKPOINT_POOL_MIN/MAX_SIZE=1/8`, `LANGGRAPH_STORE_POOL_MIN/MAX_SIZE=1/4` — store plus petit : `AsyncBatchedBaseStore` traite les batches séquentiellement, son gain est la résilience pas la concurrence), budget connexions documenté dans `constants.py` (baseline persistante ≈130 ≤ 197 utilisables ; l'overcommit pire-cas préexiste et est dominé par l'overflow SQLAlchemy ×4 workers — right-sizing SQLA en follow-up). Cycle de vie : factories lazy conservées (déjà appelées au lifespan startup → fail-fast au boot via `open=False` + `await pool.open(wait=True)` ; l'open implicite du constructeur async est déprécié), `setup()` une fois par process (garde singleton, échec = pool fermé pas fuité), shutdown via les `cleanup_*` existants (`await pool.close()`), `check=check_connection` au checkout (parité `pool_pre_ping` SQLAlchemy — corrige au passage le défaut silencieux « connexion morte = checkpointer HS jusqu'au restart », aucune logique de reconnexion n'existait). Métriques Prometheus `checkpoint_*` et serde msgpack intouchés (wrapper `aput`/`aget` orthogonal au transport) ; `psycopg-pool==3.3.0` pinné (devenu import direct) ; les `# type: ignore[arg-type]` des factories supprimés (pool typé via cast, pattern amont). **Rollback sans redéploiement** : `LANGGRAPH_CHECKPOINT_POOL_MAX_SIZE=1` reproduit la sérialisation historique. Prouvé : tests unitaires mockés cross-platform (config pool depuis settings, singleton, cleanup, échec setup, chevauchement des `_cursor` poolés + sérialisation mono-connexion préservée), intégration PG réel (20 `ainvoke` concurrents d'un graphe compilé, checkpoints tous persistés et relisibles + 20 put/get store concurrents), micro-benchmark avant/après 20 tâches × 5 rounds aput/aget payload 4 Ko (chiffres dans la PR), suites `tests/unit` + `tests/agents` vertes, boot Docker healthy, `/metrics` inchangé. Résout la contradiction doc/code de `STATE_AND_CHECKPOINT.md` (qui documentait un pool inexistant) dans le sens de la doc. Suit [ADR-110](#adr-110-backup-encryption--analyse-doptions-différée).

### ADR-112: Python Dependency Locking — lockfiles universels via uv

**Status**: ✅ IMPLEMENTED (2026-07-08)
**Fichier**: `docs/architecture/ADR-112-Python-Dependency-Locking.md`

**Décision**: **Builds backend reproductibles par lockfiles compilés avec `uv pip compile --universal`** — clôt la dérive silencieuse des dépendances (74 paquets déclarés → 194 installés, ~20 pins souples et TOUS les transitifs libres ; mesuré le 2026-07-08 : **88 versions divergentes** entre le venv Windows et le conteneur Linux dev issus du même manifeste, dont starlette 0.50→1.3 et google-genai 1.67→2.10). `requirements.txt`/`requirements-dev.txt` deviennent des **manifestes d'intention** (pins souples autorisés) ; `requirements.lock.txt` (runtime, 195 pins) et `requirements-dev.lock.txt` (compilé avec `-c requirements.lock.txt`, layering bit-identique) sont les fichiers réellement installés PARTOUT (Dockerfile.prod via pip vanilla `--require-hashes`, Dockerfile.dev, CI lint/test, venv local via `task setup:backend`, `PROD/` via prepare-prod.ps1). pip-tools disqualifié par le critère décisif : résolution mono-plateforme alors que le repo a des branches Linux-only (`uvloop`) et Windows-only (`pywin32`) — `--universal` produit UN fichier à markers d'environnement valide linux/amd64 + linux/arm64 + Windows + Python ≥3.12 (venv 3.13 / Docker 3.12), au format requirements standard, **zéro adhérence uv dans l'image finale**. Hashes inclus (`--generate-hashes` embarque les SHA256 de TOUS les fichiers publiés — wheels toutes plateformes + sdist) ; audit PyPI des 194 versions : couverture wheels aarch64+x86_64 cp312 complète sauf `odfpy` (pur Python, sdist triviale, inchangé) et `pywin32` (marker win32) ; risque résiduel assumé : wheel AJOUTÉE a posteriori à une release → régénérer le lock (détecté par le job CI docker-build). Piège découvert par la validation venv-propre : métadonnées de wheels INCOHÉRENTES chez `sherpa-onnx` (la wheel armv7l ne déclare aucune dépendance, les wheels manylinux/win exigent `sherpa-onnx-core==<même version>`) — uv lit UNE metadata par version et omettait core, `pip --require-hashes` refusait ; correctif : `sherpa-onnx-core` déclaré explicitement dans le manifeste avec obligation de bump conjoint (un mismatch futur échoue bruyamment à l'install, jamais silencieusement). **Zéro bump silencieux à l'adoption** : locks initiaux compilés sous contrainte du freeze du venv testé (0 écart, seul ajout uvloop==0.22.1 == version conteneur) ; conséquence assumée : le conteneur dev reconverge vers les versions du venv au rebuild. **Régénération stable prouvée** : uv réutilise le lock existant comme préférences → `task deps:lock` n'applique QUE les changements de manifeste (recompilation = no-op byte-identique) ; bumps explicites via `task deps:upgrade -- <pkg>` / `deps:upgrade:all`. Garde CI (job code-hygiene) : `scripts/check_requirements_lock.py`, hors-ligne et déterministe (jamais flaky sur nouvelle release upstream) — échec si pin de manifeste absent/non satisfait par le lock ou lock dev désynchronisé du lock runtime (invariant de layering) ; testé par mutation. Bonus périmètre : `pip-audit` et le SBOM release (cyclonedx) lisent désormais le lock — les ~120 transitifs sont enfin audités et inventoriés ; process de bump documenté dans GUIDE_DEVELOPPEMENT.md. Suit [ADR-111](#adr-111-langgraph-postgres-connection-pooling--checkpointer--store).

### ADR-113: Backend Test Suite Rehabilitation — job integration, fin des quarantaines, ratchet couverture

**Status**: ✅ IMPLEMENTED (2026-07-08)
**Fichier**: `docs/architecture/ADR-113-Backend-Test-Suite-Rehabilitation.md`

**Décision**: **Réhabilitation complète de la suite de tests backend** — clôt les constats §3.12 et reco #4 de l'audit 2026-07 : `tests/integration/` (250 tests) ne tournait dans AUCUN job CI et avait pourri en silence (53 échecs mesurés sur 243, comme la suite agents avant elle), 13 fichiers Testcontainers étaient mal classés sous `tests/unit/` (l'audit en voyait 10 ; +`test_messages_search`, `test_feedback_persistence`, `test_checkpointer` — ce dernier ne tournait NULLE PART : skip win32 en local, désélection `-m` en CI), dont 10 quarantainés par une liste `--ignore` dans ci.yml **prouvée 100 % redondante** (collecte byte-identique avec/sans : 8916 tests). Reclassement des 13 (222 tests) vers `tests/integration/`, suppression de la liste, et interdiction explicite des quarantaines `--ignore` sans marker ni ticket. **Nouveau job `test-backend-integration`** (465 tests, `-m "not e2e and not benchmark and not multiprocess"`, slow inclus car ne tournant nulle part ailleurs, `--no-cov`) branché sur les services PG+Redis existants via **`TEST_DATABASE_URL`** — seule variable DB qui survit au `load_dotenv(.env.test, override=True)` du conftest ; `_detect_environment` l'honore explicitement avec fallback Testcontainers inchangé, credentials du service alignés sur `.env.test` pour les tests lisant `settings.database_url` en direct (checkpointer), branche « optimisation localhost » morte supprimée (règle docstring/code). Taxonomie des 53 échecs réparés : ~35 = UNE cause (rate-limiter auth 10 logins/min/IP non gaté par `RATE_LIMIT_ENABLED`, saturé par les fixtures `authenticated_client` — purge des buckets `auth:*` par le client Redis du limiter dans `tests/integration/conftest.py` + reset du singleton, zéro changement produit) ; 3×500 = extension PG `unaccent` créée par les migrations mais absente du conftest ; ~4 asserts i18n anglais en dur (l'API répond localisé) → assertions via le catalogue `APIMessages` ; ~10 tests obsolètes réécrits contre l'API actuelle (handlers connecteurs `*_stateless`, callback Gmail 302-redirect, schéma `ModelPriceCreate` 14 champs, cycle de vie compte pending-activation, MissingGreenlet sur attribut expiré, setup home-location sans connecteur Places). **Bug produit trouvé et corrigé au passage** : le handler custom `RequestValidationError` sérialisait `exc.errors()` brut (objets `ValueError` dans `ctx`) → **500 au lieu de 422 sur toute erreur de validation issue d'un `field_validator`** ; corrigé par `jsonable_encoder` (pattern du handler FastAPI par défaut). **Ratchet couverture 43→45 %** (pyproject + ci.yml synchrones, couverture réelle mesurée 52,31 % en CI Linux), doctrine « +2 points par release, jamais de baisse » vers l'objectif 75 % documentée dans GUIDE_TESTING.md. **6 tests llm_cache skippés « implementation changed » réparés, pas supprimés** (le code testé est vivant : mocks re-déclenchant le vrai chemin d'échec str(), patches sur le vrai site d'import `metrics_agents`, `estimate_cost_usd` devenu async). Dettes signalées hors périmètre : `test_metrics_langgraph_state.py` (module skippé « not implemented »), `test_database_session.py:66`, routes auth qui ne résolvent pas Accept-Language (réponses toujours FR), messages du validateur mot de passe en français inline, 209 skips suite agents (stratégie : provider fake-LLM déterministe pour le plumbing + tier nightly `llm_live` avec secret pour le petit noyau LLM réel). Suit [ADR-112](#adr-112-python-dependency-locking--lockfiles-universels-via-uv).

### ADR-114: Connector Client Domain Error Contract — alignement OAuth/Google/Microsoft/Places/Routes sur la taxonomie BaseAPIException

**Status**: ✅ IMPLEMENTED (2026-07-08)
**Fichier**: `docs/architecture/ADR-114-Connector-Client-Domain-Error-Contract.md`

**Décision**: **Élimination des 28 `raise HTTPException` bruts de la couche clients connecteurs** (base_oauth ×8, places ×6, routes ×6, base_microsoft ×4, base_google ×3, ms_tasks ×1) — clôt le constat d'audit « couche domaine qui lève du transport HTTP » en étendant le contrat F0 d'[ADR-108] à toute la famille OAuth et aux clients Google-direct. Levier structurel : `BaseAPIException` **est** une `HTTPException` (ADR-002), donc migrer vers des sous-classes typées préserve le contrat API externe **par construction** (mêmes status codes, même payload `{"detail"}`, mêmes headers via le handler FastAPI natif ; les deux chemins `isinstance(HTTPException)` — geocoding users/service et classification runtime_helpers — restent vrais, `str(e)` garde le format `"401: detail"`) — **aucun exception handler nouveau**, la famille `ConnectorError` découplée a été rejetée (casserait silencieusement ces chemins et transformerait les 503 en 500 via ErrorHandlerMiddleware). Mapping en 8 catégories : 401 → `AuthenticationError` (detail via `APIMessages.connector_auth_invalid()`, byte-identique au français inline qu'il remplace, header `X-Requires-Reconnect` conservé) ; passthrough amont ≥400 → **`ConnectorAPIError` (nouvelle classe, status amont forwardé tel quel)** ; 429 client-side → `RateLimitError` (nouvel override `detail`) ; circuit ouvert/réseau/max-retries/config manquante → `ExternalServiceError` avec `error_type` dédié (+ nouveau param `headers` sur BaseAPIException/AuthenticationError/ExternalServiceError pour Retry-After) ; 400/404 domaine → `ValidationError`/`ResourceNotFoundError`. **Divergence documentée vs ADR-108** : l'épuisement des retries OAuth reste un 503 (`ExternalServiceError`) et non `MaxRetriesExceededError` — les bases OAuth alimentent des routes REST où une plain Exception deviendrait un 500. **Quirk pré-existant documenté (partagé avec la base F0)** : le 429 de `_on_rate_limit_exceeded()` est avalé par l'`except Exception` du fallback Redis→local et ne se propage jamais. Durcissements arbitrés inclus : parité provider du message 401 Microsoft, troncature à 200 chars des corps amont dans les details (hygiène PII/tokens), coordonnées GPS déplacées à DEBUG dans les logs geocoding (règle no-PII). Vérification : `test_connector_client_error_contract.py` (34 tests — les 28 sites migrés exercés individuellement, mapping byte-identique, **parité de rendu FastAPI typée-vs-brute via TestClient**, classification tool inchangée), 490 tests connectors + 611 tools/heartbeat verbatim, ruff/black/mypy strict, boot Docker sain. Hors périmètre (phase 2) : les 35 sites routers/services (llm_config, health_metrics, heartbeat, user_mcp…) ; les handlers 401/429/403 morts d'`error_handlers.py` (candidat S7). Suit [ADR-113](#adr-113-backend-test-suite-rehabilitation--job-integration-fin-des-quarantaines-ratchet-couverture).

### ADR-115: Liveness/Readiness Probe Split — /health toujours 200, /ready porte le 503

**Status**: ✅ IMPLEMENTED (2026-07-09)
**Fichier**: `docs/architecture/ADR-115-Liveness-Readiness-Probes.md`

**Décision**: **Séparation liveness/readiness des sondes d'infrastructure** — clôt le constat d'audit « contrat mort » : `GET /health` sondait réellement PostgreSQL + Redis mais ne positionnait jamais que `degraded`, rendant sa branche `503 si unhealthy` **inatteignable depuis l'origine** (aucun consommateur n'a donc pu en dépendre — recensement exhaustif : healthchecks Docker dev/prod/Dockerfile, Taskfile, scripts monitoring, curls runbooks ; l'alerte `ServiceDown` passe par `up{job="api"}`). Nouveau module `src/api/health.py` (le chemin que GUIDE_DEPLOYMENT documentait **fictivement** — la doc redevient vraie) : `GET /health` = **liveness** (toujours 200 tant que le process sert, payload `healthy|degraded` + `checks` par dépendance — redémarrer l'API ne répare pas la DB, un 503 enverrait Docker en boucle de restart) ; `GET /ready` = **readiness** (200 seulement si PostgreSQL **et** Redis répondent, sinon **503** `not_ready`) pour la vérification post-deploy et le monitoring d'impact utilisateur. Périmètre readiness **assumé DB + Redis uniquement** : les subsystems LangGraph peuvent échouer au boot avec les deux sondes vertes — le contrôle compensatoire reste le scan des logs de démarrage (doctrine `CLAUDE.server.md` + runbook ServiceDown, table canonique « quel endpoint pour quel usage »). `/ready` rejoint les exclusions de logging HTTP (`HTTP_LOG_EXCLUDE_PATHS`). Corrections doc-vérité embarquées : commentaire `start_period: 60s # E5 model loading` des deux composes remplacé par la vraie raison **mesurée sur logs de boot** (migrations alembic ~13s + import complet de l'app ~14s/process ; Whisper STT est lazy, PAS chargé au boot — hypothèse d'audit réfutée) ; `CLAUDE.server.md` réaligné (prod = 4 workers uvicorn, pools ADR-111 avec health-check au checkout vs « single connection no auto-reconnect » périmé) ; `docker-entrypoint.sh` : `pg_isready` passe des littéraux `postgres/lia` aux variables d'env avec fallbacks miroir (un var absent aurait bouclé à l'infini) ; gauge `db_connection_pool_waiting_total` (suffixe `_total` non conforme) **conservé et documenté** au point de définition — référencé par le dashboard Grafana 03. Vérification : 8 tests unitaires (`tests/unit/api/`, 4 combinaisons up/down × 2 endpoints, sondes mockées), démo live Redis stoppé → `/ready` 503 + `/health` 200 `degraded` → Redis relancé → 200. Suit [ADR-114](#adr-114-connector-client-domain-error-contract--alignement-oauthgooglemicrosoftplacesroutes-sur-la-taxonomie-baseapiexception).

### ADR-116: Frontend Test Foundation — gate de couverture ratchet & symétrie du contrat SSE

**Status**: ✅ IMPLEMENTED (2026-07-09)
**Fichier**: `docs/architecture/ADR-116-Frontend-Test-Foundation.md`

**Décision**: **Fondation de tests frontend en 3 couches + invariant de symétrie du contrat SSE exécutable** — clôt le constat d'audit « la machine à états la plus critique du produit (chat SSE + HITL + voix) n'est protégée que par tsc/eslint » (19 fichiers de tests pour 448 sources) ET l'outillage fictif : `@vitest/coverage-v8` absent (`test:coverage` crashait) et la CI exécutait `pnpm test -- --coverage` dont pnpm avale le `--` — **aucun rapport de couverture n'avait jamais été produit ni uploadé** (upload Codecov masqué par `fail_ci_if_error: false`). Couche 1 — logique pure à **100 % (4 métriques)** : chat-reducer(-errors), les 19 handlers SSE, psycheStore/voiceModeStore, avec états d'entrée gelés en profondeur (immutabilité prouvée, pas affirmée). Couche 2 — hooks avec I/O scriptées : useChat piloté par séquences de chunks SSE à travers le vrai pipeline processSSEChunk→reducer (cycle HITL interrupt→resume complet), useVoiceMode sans audio réel (fakes AudioContext/Worklet/getUserMedia, callbacks KWS/VAD/WS capturés) — pas de MSW (driver scripté à la frontière chatSSEClient, cohérent avec le style vi.mock du repo). Couche 3 — **seuils ratchet** dans vitest.config.ts : répertoires 100 % verrouillés par globs, hooks aux valeurs mesurées, plancher global — fixés juste sous la mesure, montent seulement, ne descendent jamais (piège vérifié empiriquement : sur vitest 4.1 le plancher global couvre TOUT l'include, les fichiers des globs n'en sont PAS soustraits). **Symétrie SSE** (`sse-symmetry.test.ts`) : le Literal backend est pinné ET reparsé depuis `schemas.py` quand accessible (hôte + CI ; skip dans le container web) — tout type du contrat doit avoir un handler front ou une entrée justifiée dans `ACKNOWLEDGED_UNHANDLED` (vide) ; Pydantic força déjà le Literal à l'émission (passthrough custom-mode inclus), le contrat est donc clos aux deux bouts. **Purge du contrat mort** : 8 types jamais émis retirés du Literal + branches consommatrices (extraction métriques e2e du router — `agents_count` était figé à 0 depuis la mort de `planner_metadata` —, mapping Prometheus) ; côté front : types fantômes, handler zombie, ~60 lignes de branches de log mortes, 4 symboles morts ; `hitl_streaming_fallback` (émis mais ignoré depuis des mois en « unknown event type ») gagne un handler d'awareness. **4 bugs utilisateur trouvés et corrigés par l'écriture des tests (RED→GREEN)** : `voiceModeStore.setError` corrompait la clé `state` (`undefined` via Object.assign zustand v5) ; stale closure avalant les coupures WS pendant la transcription vocale (spinner « processing » infini) ; promesse de timeout orpheline → unhandled rejection ~10 s après chaque enregistrement wake word ; erreurs de stream rendues avec préfixe français en dur au lieu du mécanisme `ChatStreamError.i18nKey` livré mais jamais branché (+ clé `errors.chat.connection_error` ×6 locales). Vérification : 434 tests vitest verts sous seuils actifs, tsc/eslint/prettier verts (drift Prettier intégral de `src` résorbé), 62 pytest streaming SSE verts, black/ruff/mypy stricts, boot Docker sain des deux apps. Alternatives rejetées : MSW ; conserver les entrées mortes « au cas où » ; snapshot du handler map (pinne le front contre lui-même, pas contre le backend). Suit [ADR-115](#adr-115-livenessreadiness-probe-split--health-toujours-200-ready-porte-le-503).

### ADR-117: Background Chat Runs — exécution détachée survivant aux déconnexions (Lot 1 : durabilité)

**Status**: ✅ IMPLEMENTED (2026-07-09) — flag OFF par défaut
**Fichier**: `docs/architecture/ADR-117-Background-Chat-Runs.md`

**Décision**: **Découplage exécution/transport du chat** — clôt le bug produit « naviguer ou fermer la page pendant une génération perd le tour entier » (archivage user+assistant uniquement en fin de run dans le générateur SSE) et la **fuite de facturation** associée (`TrackingContext.__aexit__` ne persistait les tokens que si `exc_type is None`). Architecture : producteur asyncio **détaché** (`background_runner.py`) consommant `stream_chat_response` (déjà transport-agnostique — 3ᵉ consommateur après scheduled actions et channels) et publiant chaque chunk dans un **Redis Stream par run** (`chat:run:{run_id}`, broker `infrastructure/streaming/run_stream_broker.py`) ; l'endpoint SSE devient un simple abonné XREAD à **blocks courts** (piège prouvé par POC : XREAD bloquant ≥ `socket_timeout` → `TimeoutError` sur redis-py 8) ; marqueur terminal **d'enveloppe** (`end/status`), pas un type ChatStreamChunk — le contrat SSE et son test de symétrie frontend sont intacts. **Archive-first** : la row user est persistée AVANT l'exécution du graphe (run_id, attachments, STT, `hitl_response`) et les flags de fin de run (`decision_type`, `hitl_interrupted`) sont **patchés** via `patch_message_metadata` ; best-effort (un échec d'archivage ne bloque jamais le run) ; les retries scheduled actions passent `archive_user_message=(attempt==1)` (anti-doublon). `__aexit__` commite désormais sur TOUS les chemins de sortie (shield sur CancelledError) — sûr par construction, l'UPSERT est incrémental/idempotent. **Drain lifespan obligatoire** (POC-4 : sans drain, le recyclage worker `--limit-max-requests` tue un run en vol à 1/30 chunks ; avec drain 30/30) : `drain_chat_producers` (45 s) puis `wait_all_background_tasks` (15 s — code mort enfin câblé, corrige aussi le kill silencieux des extractions mémoire à chaque deploy), `stop_grace_period: 90s` sur le service api. Étude de dérisquage : 4 POCs sur la stack exacte (XADD 0,09 ms/chunk, replay 2000 chunks = 20 ms, latence 0,4 ms, ~122 Ko/1000 chunks ; annulation LangGraph mi-course = pas d'écriture partielle mais `AIMessage(tool_calls)` pendant si tué entre call_model et execute_tools — assainissement = Lot 3). Alternatives rejetées : task queue externe (over-engineering RPi5), pub/sub sans replay, archive-first seul, nouveau type de chunk. Métriques `chat_background_producers_active` / `chat_background_runs_total{status}`. Vérification : TDD intégral (26 nouveaux tests unit+intégration Redis réel), non-régression 8951 tests unit + suite intégration, E2E Docker flag ON (scénario du bug d'origine : envoi → navigation → retour → tour complet + tokens facturés), rollback flag OFF prouvé. **Lot 2 livré le même jour** (même flag) : verrou run-actif par conversation (SET NX EX + heartbeat producteur + release/refresh conditionnels Lua zombie-safe, POC-L2-1) → **409** sur POST concurrent avec le stream_id de reprise ; endpoints `GET /agents/runs/active` + `GET /agents/runs/{stream_id}/stream` (replay intégral sans pacing, voice périmé droppé côté serveur, frontière transport `: replay-end` ignorée par les parseurs legacy) ; **reprise auto silencieuse** frontend (mount + visibilitychange, `isReplay` supprimant toasts/audio pendant le backlog, seuils ratchet maintenus — 448 tests vitest) ; **TTS gaté par la présence d'auditeurs** (compteur `chat:listeners:{stream_id}`, fail-open, chemins legacy/scheduled/channels inchangés). E2E : 322 chunks rejoués + tail live après 10 s d'absence, verrou auto-libéré. **Lot 3 livré le même jour** : bouton stop → `POST /runs/active/cancel` (résolution serveur du run actif, ownership trivial, idempotent) → clé `chat:cancel:{stream_id}` pollée par un watcher côté producteur (latence ≈ 1 s, signal cross-worker, cancel asyncio local) ; statut terminal **`cancelled` distinct de `killed`** (métriques + métadonnées) ; `done` **synthétisé** avec `metadata.cancelled` (contrat de chunks intact, cycle SSE normal côté abonnés) ; partiel conservé et badgé `interrompue` (même flag live/historique) ; **tokens déjà consommés facturés** (prouvé E2E : 1348/748 persistés sur run annulé) ; annulation ≠ rollback (les tools déjà exécutés ont agi). **Assainissement checkpoint POC-3** : `sanitize_stale_dangling_tool_calls` répare les `AIMessage(tool_calls)` sans réponse EN DÉBUT DE TOUR (router_node, replacement par id / RemoveMessage via le reducer) — jamais dans le reducer où c'est un état mi-run légitime ; les résumptions HITL passent par `Command(resume)` sans re-router (approbations intactes) ; 7 tests-preuve TDD dérivés du POC-3. Hors périmètre : retrait du chemin legacy après preuve prod. Doc technique : `docs/technical/BACKGROUND_RUNS.md`. Suit [ADR-116](#adr-116-frontend-test-foundation--gate-de-couverture-ratchet--symétrie-du-contrat-sse).

### ADR-118: Import de skill piloté par le chat — livraison directe du skill-generator + pipeline d'import durci

**Status**: ✅ IMPLEMENTED (2026-07-09)
**Fichier**: `docs/architecture/ADR-118-Chat-Driven-Skill-Import.md`

**Décision**: **Import direct des skills générées depuis le chat** — clôt la friction produit « le skill-generator livre des blocs de code que l'utilisateur doit recopier, assembler en dossier, zipper et uploader » alors que le backend possède déjà tout le contenu. Nouveau `SkillImportService` **unique et durci** partagé par TOUS les chemins d'import (upload user, upload admin, outil chat), qui corrige au passage 4 défauts audités du pipeline existant : **S1 path traversal critique** (le `name` du frontmatter était concaténé dans le chemin destination sans validation — `name: ../../system/x` écrasait une skill système pour tous les utilisateurs ; validation stricte agentskills.io AVANT toute écriture), **S2 collision de noms inter-scopes** (unicité DB globale vs sémantique d'override du cache : un import user réécrivait la description d'une skill système ou la row d'un autre user ; rejet 409 du shadowing à l'import, ré-import de sa propre skill = upsert, sans migration de schéma), **S3 expansion zip** (aucune garde zip-bomb, `extractall` intégral d'archives multi-racines ; plafonds taille décompressée + nombre de fichiers, extraction limitée au sous-arbre SKILL.md, staging temporaire + swap atomique), **S4 divergence de validation** (importeur laxiste vs `validate_skill.py` strict — désormais alignés). Nouvel outil **`import_user_skill`** (files map path→contenu, extensions texte uniquement, `@rate_limit` 5/min, quota par user, flag `SKILLS_CHAT_IMPORT_ENABLED`) ; Phase 4 du skill-generator réécrite : valider → importer → **annoncer la skill par son nom** (pointer Réglages > Compétences LIA > Mes skills), livraison en blocs de code conservée en simple fallback. **S5** : le runner ReAct des skills (sous-agent neuf à chaque tour, ne voyait que le dernier message) reçoit désormais le `conversation_history` fenêtré dans un bloc `<conversation_history>` + consigne de REPRISE du dialogue dans le prompt — les dialogues multi-tours du générateur (clarifier → répondre → générer) fonctionnent enfin entre les tours. Modèle de risque assumé : gate HITL (bouton/stage-then-commit) **rejeté comme disproportionné** — blast radius borné (skill user-scoped, sandbox subprocess + CSP stricte sur frames user, badge visible à chaque activation, désactivation/suppression en un clic), import annoncé nommément dans le chat. Alternatives rejetées : migration unique(name, owner_id), ré-émission des fichiers par le LLM depuis l'historique (corruption silencieuse). Tests : `test_import_service.py` (36, S1-S4 épinglés), `test_import_tool.py` (9), `test_skill_runner_history.py` (2, contrat S5). Suit [ADR-117](#adr-117-background-chat-runs--exécution-détachée-survivant-aux-déconnexions-lot-1--durabilité).

### ADR-119: Réactivation de l'alerting — noyau minimal viable sur Alertmanager e-mail

**Status**: ✅ IMPLEMENTED (2026-07-10)
**Fichier**: `docs/architecture/ADR-119-Alerting-Reactivation-Minimal-Core.md`

**Décision**: **Réactivation de la chaîne d'alerte, éteinte le 2026-01-16 sans ADR** — ~71 règles maintenues et 22 runbooks dormaient, personne n'était notifié d'un incident (seul signal : digest logwatch quotidien), MTTR DORA immesurable. Choix : **règles évaluées par Prometheus + Alertmanager dédié (e-mail)** plutôt que Grafana unified alerting (rejeté : évaluation déplacée dans un Grafana taillé au plus juste, pas d'équivalent `promtool test rules`, SPOF silencieux). **Noyau de 13 alertes** (`alerts-core.yml` : Service/Database/Redis Down, disque, mémoire conteneur, restart-loop, 5xx, latence SSE p95, backup, endpoint public, expiration certificat, 2 méta) plutôt que réactiver les 71 legacy : l'audit a prouvé que **les seuils rendus legacy sont corrompus** (multiplicateurs aveugles ×1.5/×3/×7.5 appliqués à des pourcentages bornés — `DiskSpaceCritical` prod à 147 % de disque, littéralement impossible à déclencher ; recalibration obligatoire avant toute réactivation). Seuils `ALERT_CORE_*` dans `thresholds/{env}.env` (règle « paramétrable = .env ») et **descriptions référençant les mêmes variables Jinja2 que les expressions** (le bug de dérive « seuil: 95% » affiché vs 147 réel ne peut plus se reproduire) ; chaque alerte annote son runbook `docs/runbooks/alerts/` (4 nouveaux : RedisDown, BackupFailed, PublicEndpointDown, AlertmanagerDown). **blackbox-exporter** (64M) sonde ce qu'aucun exporter ne voyait : webhook healthcheck du sidecar backup (ADR-109) et URL publique de bout en bout (edge Cloudflare → tunnel systemd → web) — cible injectée au démarrage depuis `BLACKBOX_PUBLIC_PROBE_URL` (.env) dans un file_sd, le domaine réel ne rentre jamais dans le repo public, variable vide = sonde désactivée (défaut dev). Consolidation : config Alertmanager unifiée sous `infrastructure/observability/alertmanager/` (doublon orphelin supprimé, entrypoint email-only automatique conservé), 22 scripts one-shot/archives 2025-11 supprimés (récupérables via git), alertes custom jamais chargées regroupées sous `prometheus/alerts/`. Limites RPi5 : Alertmanager 128M/0.25 cpu, blackbox 64M/0.1 cpu. Limitation assumée : `AlertmanagerDown` ne peut pas s'auto-notifier (visible Prometheus UI + logwatch ; dead-man's-switch externe = durcissement futur). Validation : `promtool check config/rules` + tests unitaires de règles `promtool test rules`, E2E dev (stop Redis → e-mail reçu → resolved). Suit [ADR-118](#adr-118-import-de-skill-piloté-par-le-chat--livraison-directe-du-skill-generator--pipeline-dimport-durci).

### ADR-120: Expansion sémantique pilotée par l'évidence & garde runtime des paramètres

**Status**: ✅ IMPLEMENTED (2026-07-10) — évidence + garde actives ; expansion evidence-driven livrée éteinte (flag)
**Fichier**: `docs/architecture/ADR-120-Semantic-Evidence-Expansion-And-Param-Guard.md`

**Décision**: Clôture systémique du bug « trajet chez mon frère » (pipeline générait par intermittence une route vers un lieu arbitraire) — trois mécanismes, un par maillon défaillant. **(1) Évidence personne déterministe (toujours active)** : le déclencheur d'expansion `has_person_reference` devient l'union de trois sources — mappings du memory resolver (références personnelles par construction), références relationnelles extraites en Phase 1 **conservées même quand la résolution échoue** (nouveau résultat typé `MemoryResolution`), et refs typées du LLM analyzer (signal historique, jusqu'ici SEUL utilisé alors que la docstring du service d'expansion documentait le contrat inverse). Une seule liste de domaines alimente le catalogue planner, la section semantic-dependencies du prompt planner ET le prompt système ReAct : la correction amont soigne les deux modes. **(2) Expansion evidence-driven (sous flag, livrée éteinte)** : généralise personne→contact via l'ontologie — chaque entité référencée (personne → `Contact`, item de contexte → `CalendarEvent`/`Place`, mapping complété par un assert de complétude au boot, pattern ADR-085) dont les `properties` fournissent un type sémantique requis ajoute ses `source_domains`, plafonné (`SEMANTIC_EXPANSION_MAX_ADDED_DOMAINS`) et compté (`semantic_expansion_total`) ; l'ancrage sur l'entité empêche l'expansion aveugle (« quel temps demain ? » requiert une adresse mais ne référence personne → rien d'ajouté). Le code mort `expand_domains_semantic` + `SEMANTIC_EXPANSION_THRESHOLD` (jamais câblés) est **supprimé**. **(3) Garde runtime des paramètres (toujours active, fail-open)** : manifest-driven, zéro hardcode par outil — un appel dont l'argument est exactement un nom de personne résolu du tour sur un paramètre typé `physical_address`/`email_address` échoue en erreur *recoverable* AVANT l'appel API payant, aux deux chokepoints (parallel executor via `configurable.resolved_person_names` sourcé du state — seul conduit survivant à un resume HITL — et `react_execute_tools_node` avant l'interrupt HITL) ; et `get_route` refuse désormais une destination non-adresse introuvable par Places (`destination_unresolved`) au lieu du passthrough → géocodage arbitraire → mise en cache de la mauvaise route. Couvre les noms directs que la couche d'évidence ne voit pas. Métriques : `semantic_param_guard_blocks_total`, `semantic_expansion_total`. Suit [ADR-119](#adr-119-réactivation-de-lalerting--noyau-minimal-viable-sur-alertmanager-e-mail).

### ADR-121: Rétro-annotation sémantique des manifests & évidence EmailMessage

**Status**: ✅ IMPLEMENTED (2026-07-10)
**Fichier**: `docs/architecture/ADR-121-Semantic-Annotation-Backfill.md`

**Décision**: **Campagne de rétro-annotation `semantic_type` sur 15 fichiers de manifests (~120 annotations)** — l'inventaire exhaustif du catalogue réel (75 tools) a révélé que **73 des 99 types de l'ontologie n'étaient consommés par aucun manifest** (dont `contact_id`, `place_id`, `distance`, `travel_mode`, `birthday`…) : l'ontologie construite en 2026-01 n'avait jamais été rebranché sur les manifests, laissant le moteur ADR-120 (linking Jinja2, sections semantic-dependencies planner/ReAct, garde runtime, expansion) tourner sur une fraction du signal. Couverture : **params 14 % → 53 %, outputs 22 % → 40 %, 72/100 types consommés**. Chaînages vitrine débloqués et épinglés par tests sur les vrais manifests : participants d'un événement → destinataires d'un mail, expéditeur d'un mail → invités d'un événement, `route.origin/destination` → météo/places à destination, garde ADR-120 étendue gratuitement (email/adresse des contacts, waypoints). **Règle du lot : aucun output tagué sans vérification du payload réel** (les refs Jinja s'exécutent dessus) — `events[].attendees[].email` vérifié au format Google natif ; `emails[].from` n'existait pas (From enfoui dans `payload.headers[]`, inadressable en Jinja) → promotion top-level dans `build_emails_output`, calquée sur le pattern `subject` existant de la même fonction (seul changement hors manifests). **Entité `EmailMessage`** ajoutée à l'ontologie (+ `EVIDENCE_ENTITY_TYPE_BY_DOMAIN["email"]`, couverte par l'assert de boot ADR-120) : un mail référencé devient évidence d'expansion (« invite l'expéditeur de ce mail à la réunion »). Corrigé au passage : la fixture `agent_registry` des tests de linking chargait un **registre vide** (docstring mensongère « auto-loads ») — tous les tests historiques de suggestions passaient sur le chemin not-found ; elle appelle désormais `initialize_catalogue()`. Suit [ADR-120](#adr-120-expansion-sémantique-pilotée-par-lévidence--garde-runtime-des-paramètres).

### ADR-122: Décomposition du stream AgentService (B2) — extraction de la coordination voix/TTS

**Status**: ✅ IMPLEMENTED (2026-07-10)
**Fichier**: `docs/architecture/ADR-122-AgentService-Stream-Decomposition-B2.md`

**Décision**: Première couture de la série B2 sur `_stream_with_new_services` (1 135 SLOC logiques, la plus grosse fonction du backend, chemin critique de chaque tour de chat) — **extraction comportementalement neutre de la machine à états voix/TTS** vers `services/streaming/` : `VoiceStreamCoordinator` (stateful — TTS progressif chat-mode, voix parallèle agent-mode, émission progressive mid-stream, finalisation PATH 1/2A/2B, 2 passes de backfill TTS, teardowns exacts des 3 sorties du générateur) + `voice_stream_helpers.py` (primitives sans état : sanitisation TTS, gate `_should_start_voice` ADR-117, pompe de queue, formateur de chunk — scindé pour respecter le plafond ratchet 600 SLOC). Interface typée explicite (`VoiceStreamContext` dataclass, aucun dict fourre-tout) ; les 11 variables locales voix qui traversaient 8 phases + 3 chemins d'erreur deviennent l'état privé du coordinateur. **Méthode B1 (Feathers, characterization-first)** : filet golden de 11 scénarios (`test_agent_service_stream_characterization.py` — séquences SSE ordonnées + effets de persistance, `background_runs_enabled` figé pour épingler le producteur en amont du broker ADR-117) écrit et vert AVANT la coupe, repassé **identique et non modifié** après. Invariants tenus : ordre/contenu SSE inchangés, noms d'événements structlog conservés (seul le champ `logger` suit les nouveaux modules, précédent B1), aucune clé d'état LangGraph touchée. Chiffres : `service.py` 1 585 → **1 031 SLOC logiques (−35 %)**, plafond ratchet abaissé 1 617 → 1 052. Constat épinglé tel quel (fix = changement de comportement séparé, désormais localisé) : les `VoiceCommentService` des chemins sync PATH 2A/2B ne sont jamais fermés par le générateur (fuite potentielle du pool httpx). Coutures suivantes prévues (une par livraison) : n°2 finalisation/archivage, n°3 setup — coordonné avec R2-03 (retrait du chemin legacy du routeur), un seul chantier en vol à la fois.

### ADR-123: Décomposition du lifespan — modules d'initialisation par sous-système, lifespan seul orchestrateur

**Status**: ✅ IMPLEMENTED (2026-07-10)
**Fichier**: `docs/architecture/ADR-123-Lifespan-Startup-Decomposition.md`

**Décision**: Extraction du deuxième monolithe du backend, `src/main.py::lifespan` (~780 SLOC logiques / 1 133 lignes brutes : 23 étapes de startup + 20 de shutdown, en croissance à chaque release — drain ADR-117 en dernier), vers un nouveau paquet **`src/infrastructure/startup/`** : 7 modules par sous-système (`registries`, `observability`, `caches`, `agents`, `integrations`, `schedulers`, `shutdown`), chacun exposant **une fonction typée par segment contigu** de la séquence historique — la fonction unique par module est impossible sans réordonner (checkpointer initialisé entre deux groupes de caches ; MCP entre le registry et le sélecteur sémantique car ses tools doivent être dans le catalogue avant la construction des embeddings ; observabilité en 3 points non contigus). **Le lifespan reste l'unique point d'orchestration** : main.py (1 399 → 322 lignes) est une séquence de ~25 appels dans l'ordre historique EXACT, précédée d'un commentaire de tête documentant les 8 dépendances d'ordre du boot et l'ordre du shutdown (drain producteurs d'abord — ADR-117 ; Redis fermé en dernier) — la checklist « Startup initialization » de CLAUDE.md est inchangée. Identité stricte : mêmes événements structlog (seul le champ `logger` suit les nouveaux modules, précédent ADR-122), mêmes try/except par étape (tuples d'exceptions conservés un à un), **sémantique des objets partiels préservée** (échec en cours d'étape → `init_agent_registry`/`init_mcp` retournent l'objet partiellement construit, pas None — les étapes aval et les gates de shutdown le consomment historiquement), imports lazy conservés dans les corps de fonctions (timing d'import et surfaces `ImportError` identiques, ex. sonde playwright), état trans-`yield` explicité en dataclass `StartupHandles` possédée par son seul consommateur `shutdown.py`. Emplacement `infrastructure/` et non `core/` : les corps importent domains+infrastructure partout (sens établi — les 14 modules de `infrastructure/scheduler/` importent domains), `core/bootstrap.py` intact. Validation : script de comptabilité ligne-à-ligne vs git HEAD (0 ligne de code perdue, allowlist explicite des commentaires docstringifiés, 14/14 contrôles d'ordre en sous-séquence OK), diff des séquences d'événements structlog au boot Docker dev avant/après identique, `/health`+`/ready` 200, `scheduler_elected_jobs_summary` identique, suites unit+agents vertes, plafond ratchet de main.py abaissé. Limite dev préexistante documentée : uvicorn `--reload` n'exécute pas le shutdown gracieux tant que des SSE hôte restent ouverts — séquence de shutdown validée par le script de comptabilité + suites. Suit [ADR-122](#adr-122-décomposition-du-stream-agentservice-b2--extraction-de-la-coordination-voixtts).

### ADR-124: Contrat d'erreur routers/services — élimination des raise HTTPException bruts (règle #18 phase 2)

**Status**: ✅ IMPLEMENTED (2026-07-10)
**Fichier**: `docs/architecture/ADR-124-Router-Service-Error-Contract.md`

**Décision**: Achèvement de la phase 2 différée par [ADR-114](#adr-114-connector-client-domain-error-contract--alignement-oauthgooglemicrosoftplacesroutes-sur-la-taxonomie-baseapiexception) — **les 33 `raise HTTPException` bruts restants (13 fichiers : reasoning_validation ×7, llm_config router ×5 + service ×2, ingest health ×5, user_mcp ×4, heartbeat ×3, agents ×2, + 5 sites isolés) migrés vers la taxonomie centralisée `src/core/exceptions.py`, contrat externe byte-identique par construction** (chaque remplaçant IS-A HTTPException). Extensions du module central : `StructuredValidationError` (422 dict Pydantic-style `type/loc/msg/input/ctx` — les 9 sites de validation LLM-config), `UnprocessableEntityError` (422 str), `PayloadTooLargeError` (413), `BadGatewayError` (502), `GoneError` (410 dict), `RateLimitError`/`ResourceConflictError` dict-capable + `headers` (pattern `ConnectorValidationError`), 6 raisers minces. **Arbitrage ratchet** : exceptions.py était à 909/928 SLOC gelés → extraction façade (`_exceptions_base.py` 68 SLOC + `exceptions_domains.py` 189 SLOC — familles memory/interests/STT/WebSocket), ré-exports explicites, **aucun import consommateur modifié**, cap abaissé via `task ratchet:update` (801 après ajouts). **Unique changement de contrat (approuvé)** : le 422 « heartbeat min > max » était avalé par l'`except Exception` de l'endpoint et dégradé en 500 générique — un bras `except HTTPException: raise` le laisse désormais atteindre le client. Méthode ADR-114 reproduite et prouvée : 33 tests de pin écrits et verts AVANT migration sur le comportement legacy (status+detail+headers exacts, assertions portées par héritage), renforcés aux types précis après, + parité edge TestClient des 8 nouvelles classes contre leurs jumelles brutes (42 tests). Garde de non-récidive : step grep « raise HTTPException » dans le job CI code-hygiene (`::warning` une release, puis `::error`). Grep final : **0 hit, aucune exemption**. Corrigés au passage : le commentaire obsolète d'ingest_router justifiant le raw raise par une limitation levée par ADR-114, et l'exemple d'usage anti-pattern de la docstring `i18n_api_messages`. Suit [ADR-123](#adr-123-décomposition-du-lifespan--modules-dinitialisation-par-sous-système-lifespan-seul-orchestrateur).

### ADR-125: Extraction du renderer de preview des drafts — dispatch table hors du module models

**Status**: ✅ IMPLEMENTED (2026-07-11)
**Fichier**: `docs/architecture/ADR-125-Draft-Preview-Renderer-Extraction.md`

**Décision**: Extraction n°2 de la série de réduction de complexité (audit cycle 3, classement par complexité cyclomatique) : `Draft.get_detailed_preview` (`drafts/models.py`, CC ≈ 93, cascade de 14 `elif` sur les 16 `DraftType`, 295 lignes brutes — de la logique de présentation lourde dans un module **models**, double faute) extraite vers un module de présentation dédié **`drafts/preview_renderer.py`** : **dispatch table** `_PREVIEW_RENDERERS` (une petite fonction par type, EMAIL/EMAIL_REPLY partagent `_render_email_send`, le forward la réutilise et ajoute les pièces jointes) + 3 helpers factorisant le motif « modifié ✏️ / préservé » des types update. Méthode [ADR-122](#adr-122-décomposition-du-stream-agentservice-b2--extraction-de-la-coordination-voixtts) reproduite : **filet golden de 63 tests écrit et vert AVANT la coupe** (59 goldens en égalité stricte de chaîne — les cartes frontend rendent la chaîne verbatim —, tous les DraftType avec garde de complétude du filet, cas MIXTES un-champ-modifié/autres-préservés tuant le câblage croisé des conditions, fallbacks de clés, frontière de troncature à 5 sous-labels, 6 langues, timezones, type inconnu), **vert à l'identique, non modifié, après**. `get_detailed_preview` devient un délégué de 2 lignes (CC 1) ; **assert de complétude boot-time** `assert_preview_renderer_completeness` câblé dans `startup/registries.py` juste après celui du display registry (pattern ADR-085 : l'app refuse de booter sur une entrée manquante) + test unitaire miroir, fallback `get_summary` conservé en défense en profondeur. 3 comportements douteux épinglés tels quels pendant la coupe puis **corrigés en follow-up dans la même livraison** (changements délibérés, table golden régénérée avec **diff prouvant la chirurgicalité** — exactement 3 goldens changés, 2 cas ajoutés) : sujet manquant/vide d'un email delete → clé i18n `no_subject` ×6 langues appliquée au rendu (le français en dur était injecté à 5 couches, tool→modèle→renderer, toutes assainies pour stocker la vérité brute `""`), body `None` d'un forward rendu vide, reminder vide → ligne `?` cohérente avec les autres deletes. **Chiffres** : `models.py` 803 → **579 SLOC logiques**, sous le plafond global 600 → **sort entièrement du registre des fichiers gelés** (`task ratchet:update`, 55 fichiers gelés restants) ; `preview_renderer.py` 303 SLOC ; **CC max 9 par fonction**. Instrument CC : celui du cycle 3 n'étant ni committé ni exactement reproductible, le comptage AST strict utilisé pour la validation est **committé en `scripts/audit/measure_cc.py`** (ferme le chantier « complexity instrument due » du protocole d'audit). Hors périmètre assumé : `get_summary` (CC 25) reste dans models.py — couture suivante candidate. Suit [ADR-124](#adr-124-contrat-derreur-routersservices--élimination-des-raise-httpexception-bruts-règle-18-phase-2).

### ADR-126: Découplage des domaines auth/users — dépendances stables pour le domaine identité

**Status**: ✅ IMPLEMENTED (2026-07-11)
**Fichier**: `docs/architecture/ADR-126-Auth-Users-Domain-Decoupling.md`

**Décision**: Remédiation de la violation du principe des dépendances stables révélée par les métriques de couplage du cycle 3 (graphe d'imports AST au niveau domaine) : **auth**, domaine le plus central du système (Ca=26), dépendait lui-même de 14 domaines (I=0.35) et participait à 11 des 31 cycles bidirectionnels. Frontière clarifiée — **auth = identité/session ; users = agrégat User, profil et cycle de vie du compte** — en 3 lots à comportement identique, suites complètes vertes et boot Docker vérifiés à chaque frontière de lot : (1) **promotions utilitaires** : `haversine_distance` → `src/core/geo_utils.py` (l'emprunt historique du `_haversine` privé d'agents), sonde de clé provider → `get_provider_api_key()` dans `core/llm_config_helper.py` ; **instrument committé `scripts/audit/measure_coupling.py`** (reproduit exactement les chiffres du cycle 3, sémantique all-imports, + colonnes runtime-only — seuls les imports runtime peuvent produire des cycles d'import réels ; ferme le chantier « coupling measurement due » du protocole). (2) **Extraction du provisioning de création** vers `users/AccountProvisioningService` (pendant créationnel d'`AccountDeletionService`) — les deux sites historiques ayant des topologies transactionnelles différentes (register committe par étape, le callback OAuth committe une fois), le flag explicite `commit_per_step` préserve le comportement à l'identique, tests auth existants verts **sans modification** (imports lazy → cibles de patch à la source inchangées). (3) **Déplacement du modèle** : `class User` → `users/models.py` (**byte-identique**, prouvé par comparaison de blobs contre HEAD), `user_location_service` → users, ~84 sites d'import + tests migrés mécaniquement, shim transitoire supprimé ; bascule `TYPE_CHECKING` uniquement là où l'analyse AST le prouve sûr (annotations seules + `from __future__ import annotations` + zéro décorateur FastAPI — les routers gardent l'import runtime, `Depends` évalue les annotations à l'inclusion). **Chiffres** : Ce(auth) 14→**2** (users, shared), runtime 6→**2** ; Ca(auth) 26→**0** (seul importeur restant : `api/v1/routes.py`, hors graphe) ; **plus aucun cycle impliquant auth** (11→0). **Arbitrage assumé et documenté** : les cycles de hub se **relocalisent** (auth↔X → users↔X) — le hub accidentel (flux d'identité entraînant 14 domaines) devient un hub **cohérent** (l'orchestrateur de cycle de vie, dont la connaissance bidirectionnelle des domaines qu'il provisionne et purge est le rôle documenté) ; aucun cycle hors-hub créé ; le split runtime/typing de l'instrument est le levier de réduction future (tout nouvel importeur de `User` à usage typage seul passe sous `TYPE_CHECKING`). Zéro migration DB (la table `users` n'a jamais bougé), `users/models.py` à 495 SLOC logiques sous le plafond de 600. Suit [ADR-125](#adr-125-extraction-du-renderer-de-preview-des-drafts--dispatch-table-hors-du-module-models).

### ADR-127: Téléphonie agentique — connecteur par utilisateur, modèle de capacité read-only, zéro métrage de coût

**Status**: ✅ IMPLÉMENTÉ (2026-07-13, à blanc — E2E vendeur bloqué sur le spike P2.0)
**Fichier**: `docs/architecture/ADR-127-Agentic-Telephony.md`

**Décision**: LIA passe des **appels sortants agentiques** au nom de l'utilisateur (vendeur ElevenLabs Agents, dialing Twilio/SIP), poursuit un objectif read-only, puis réinjecte un **résumé + proposition** de façon **asynchrone** dans le chat. Décisions porteuses (spec D-1…D-9) : **connecteur par utilisateur BYO** (`ELEVENLABS_TELEPHONY` réutilise `activate_api_key_connector` : clé API + secret webhook chiffrés dans `credentials_encrypted`, ids non secrets en JSONB ; activation provisionne un agent gardé) ; **défense par capacité, pas par prompt** — la disponibilité est une **projection free/busy pré-fetchée et minimisée** (agenda lu en `fields=["start","end"]`, seuls les créneaux occupés sont projetés, jamais titres/participants/lieux) injectée en variable dynamique `{{availability_summary}}`, l'agent ne peut pas divulguer ce qu'il n'a jamais reçu (pas de gateway live en v1) ; **HITL par draft** (`DraftType.PHONE_CALL` via `draft_critique`→`draft_executor`, `hitl_required=False`, assert de complétude boot-time ADR-085) ; **retour de synthèse tool-less** (type LLM `telephony_synthesis` + prompt versionné + structured output → `summary` factuel + `proposal_text` première personne, livré par `NotificationDispatcher`) ; **aucun enregistrement, transcript jamais persisté** (`call_recording_enabled=false`, seuls `summary` + `StructuredCallData` minimisé survivent, reaper de rétention) ; **aucun métrage de coût côté LIA** (minutes vendeur = comptes de l'utilisateur ; `call_seconds` factuel jamais converti en argent — en revanche l'appel LLM de synthèse **est** tracé via `track_proactive_tokens` comme briefing/heartbeat) ; **webhook HMAC par utilisateur** (secret par connecteur → foreign-filter `call_id`→`PhoneCall`→connecteur AVANT la vérification de signature ; inconnu/étranger/malformé → 200 + compteur ignoré sans PII, appel connu + signature forgée → 4xx). **Correction de scoping transactionnel** : `initiate_call` committe la ligne `dialing` **avant** de composer et ne tient jamais de transaction DB à travers un I/O externe (un crash après le dial laisserait sinon un appel orphelin dont le retour serait perdu) ; un-appel-actif-par-utilisateur via index unique partiel (F12), traitement webhook exactly-once via UPDATE conditionnel atomique. **Observabilité** : métriques `telephony_calls_total{status}`, `telephony_call_duration_seconds`, `telephony_webhook_ignored_total{reason}` ; i18n backend centralisée (`core/i18n_telephony.py`, 6 langues), frontend sous `settings.connectors.telephony.*`. **Spike P2.0 dû** : formes exactes de l'API ElevenLabs (header de signature, chemins du payload post-appel, chemin de config data-collection du create-agent) marquées `spike:`, à confirmer sur un vrai compte avant go-live ; toutes les lectures de payload externe sont défensives. Doc technique : `docs/technical/TELEPHONY.md`. Suit [ADR-126](#adr-126-découplage-des-domaines-authusers--dépendances-stables-pour-le-domaine-identité).

### ADR-128: Re-planner adaptatif advisory-only — contrat acté, boucle de récupération D4 différée

**Statut**: ✅ ACCEPTED (2026-07-13)
**Fichier**: `docs/architecture/ADR-128-Adaptive-Replanner-Advisory-Only.md`

**Décision**: Remédiation de F017. Après exécution d'un plan, `task_orchestrator_node` appelle `AdaptiveRePlanner.analyze_and_decide()` qui classe l'échec et émet une **décision** de récupération (PROCEED / RETRY_SAME / REPLAN_MODIFIED / ESCALATE_USER / ABORT) — mais **l'orchestrateur n'agit jamais dessus** : il la journalise seulement et laisse les résultats d'étape en échec remonter à `response_node`. Aucune ré-exécution, `replan_attempt` ne progresse jamais au-delà de 0. Le contrat **advisory-only** est acté ici comme décision produit committée. **Honnêteté** (deux corrections) : (1) les métriques `attempts` / `recovery_success` — qui laissaient croire à une boucle active — ont été retirées ; seules `adaptive_replanner_triggers_total` et `adaptive_replanner_decisions_total` (réellement observées) subsistent ; le site appelant fixe `replan_attempt = 0` sans le lire d'une clé d'état (aucune n'est écrite → pas de « retry state » fantôme survivant au réducteur de checkpoint). (2) Les commentaires justifiaient le contrat par « ADR-100 / D4 », mais **ADR-100 concerne tout autre chose** (garde de conflit structured-output) ; les références sont corrigées vers cet ADR. **Le bound `attempt >= max_attempts` est conservé sciemment** : ce n'est pas de la scaffolding morte mais une garde de sécurité **testée** (`test_abort_on_max_attempts_exceeded`) appartenant à l'analyseur réutilisable, pour que la future boucle ne puisse pas tourner sans borne ; le caller advisory l'exerce simplement en mode single-pass (`attempt = 0`). **D4 différé assumé** (câblage de la vraie récupération = restructuration du builder LangGraph : arêtes conditionnelles vers l'exécuteur/planner, compteur `retry_attempt` **déclaré dans `MessagesState`**, message écrit dans un state key rendu par `response_node`). `adaptive_replanning_max_attempts` reste interne (non exposé en `.env`/UI/dashboard). Suit [ADR-127](#adr-127-téléphonie-agentique--connecteur-par-utilisateur-modèle-de-capacité-read-only-zéro-métrage-de-coût).

### ADR-129: RAG Durable Jobs — upload & Drive sync reprenables au crash

**Statut**: ✅ IMPLEMENTED (Phase 1, 2026-07-14)
**Fichier**: `docs/architecture/ADR-129-RAG-Durable-Jobs.md`

**Décision**: Remédiation de F001 (« Workflows RAG non durables »). L'ingestion RAG (upload, Drive sync) tournait en tâches asyncio `safe_fire_and_forget` in-process : un crash perdait la tâche, laissant un document bloqué en `PROCESSING`/une source en `SYNCING` sans reprise. **Approche A — entité-comme-job** (imite les patterns durables téléphonie/`scheduled_actions`, laisse le chemin heureux intact = risque de régression minimal) : `RAGDocument` (unité upload) et `RAGDriveSource` (job sync) reçoivent `lease_expires_at`/`heartbeat_at`/`attempts`/`worker_id` + index `(status, lease_expires_at)` ; les documents gagnent un statut **`PENDING`** (`PENDING → PROCESSING[lease] → READY | ERROR`). **Claim atomique** (`UPDATE ... WHERE status='pending'`, double-launch safe) ; `try_acquire_sync_lock` étendu au lease. **Heartbeat** renouvelle le lease avant chaque batch d'embedding/téléchargement (invariant `heartbeat < lease` validé au boot). **Swap atomique de chunks** : embed d'abord (hors transaction), puis delete+insert+`READY` dans UNE transaction → le retrieval ne voit jamais un document reprocessé à zéro chunk (remplace le delete-puis-rebuild). **Retry borné** : échec transitoire → retour `PENDING`/`SYNCING` ; `ERROR` (dead-letter) à `rag_job_max_attempts`. **Reaper de reprise** (`rag_job_reaper`, leader-élu, `max_instances=1`, **premier tick immédiat au boot** puis périodique) : requeue les documents `PROCESSING`/lease expiré + `PENDING` orphelins, et les sources `SYNCING` bloquées (re-lease en gardant SYNCING pour rester récupérable), re-pilote chacun avec batch + concurrence bornés ; métrique `rag_jobs_recovered_total{job_type,outcome}`. Seuils `RAG_JOB_*` en `.env` ; zéro `Any`/`cast`/ignore. **Périmètre** : Phase 1 = upload + Drive sync + reaper (livré) ; Phase 2 = reindex générationnel non destructif (pointeur `generation` + bascule atomique) ; Phase 3 = annulation + matrice de crash complète. Tests d'intégration PG réel : exclusivité du claim, heartbeat, recovery→READY sans chunk dupliqué, retry borné→ERROR, PENDING orphelin, reprise sync. Doc : `docs/architecture/ADR-055/056`, spec `docs/superpowers/specs/2026-07-14-rag-durable-jobs-design.md`. Suit [ADR-128](#adr-128-re-planner-adaptatif-advisory-only--contrat-acté-boucle-de-récupération-d4-différée).

### ADR-130: Audit V5 — bilan de remédiation (findings Partiel + Nouveau)

**Statut**: 🔄 IN PROGRESS (2026-07-14)
**Fichier**: `docs/architecture/ADR-130-Audit-V5-Remediation-Status.md`

**Décision**: ADR de **bilan** de la remédiation de l'audit V5 (7,3/10 ; 11 findings Partiel {F001, F006, F008, F009, F011, F015, F020, F028, T1} + Nouveau {F050, F051}). Acte l'état sans dupliquer les ADR spécifiques. **5 clôturés** : F050 (guards repo-portables `_repo_paths.py`), F051 (contrat API-key 2-niveaux), F028 (allowlist asyncpg bornée + guard), F006 (2ᵉ invocation intégration CI), **T1** (inbox retour téléphonie chiffrée → [ADR-127](#adr-127-téléphonie-agentique--connecteur-par-utilisateur-modèle-de-capacité-read-only-zéro-métrage-de-coût)). **3 chantiers majeurs avancés** : **F020** (exemptions mypy 481 → **91** paires, −81 %, 19 modules repassés strict, 2 vrais bugs corrigés) ; **F001** (jobs RAG durables Phase 1 → [ADR-129](#adr-129-rag-durable-jobs--upload--drive-sync-reprenables-au-crash), reste Phase 2/3) ; **F015** (hotspots CC backend cibles A+B, `over` 349→**347** : `_detect_and_normalize_contacts_result` 57→13 + `_parse_approval_decision` 59→1 via extraction module `approval_decision.py` −446 SLOC, **bug latent Redis corrigé**, 43 golden). **F008 clôturé (addendum même jour)** : suite Pester hermétique 25 tests (driver DryRun/retry/SOPS crash-safe, bundle LF-only + provenance SHA, **câblage réel** deploy.sh généré ↔ readiness-gate sous bash : verte/rollback/échec, zéro contact prod), fix portabilité pwsh/Unix, step CI + `task test:deploy`. **F011 entamé (addendum même jour)** : env vitest conteneur réparé (sync lockfile → vite 8.1.3), cible prioritaire **CC 96 `useMcpAppBridge` décomposée en table de décision** (28 golden, fichier à 0 hotspot), puis **cible #2 `AdminLLMConfigSection`** (3 hotspots dont max 86) — logique pure extraite dans `llm-config/configDialogHelpers.ts` (22 tests) + 12 sous-composants, 16 golden RTL sur le payload PATCH ; `over` 71→**66** / `max` 96→**74**, **ratchet renforcé** en empreinte per-file `{count, max}` (chemin d'échec prouvé). **Restants** : suite F011 (66 hotspots, max 74 = ChatMessage), F009 (cycles runtime 31, **arbitré low-ROI** : ratchet conservé, pas de réduction active). **Décisions transverses** : méthodo décomposition **caractérisation-first** ; gouvernance par **5 ratchets shrink-only** (CC back/front, mypy-debt, coupling-cycles, file-size) CI-enforced ; **pause assumée** sur les gros chantiers (F001 Ph2/3, suite F015 dont jauge `max` `_stream_with_new_services` CC 89, reliquat F020 framework-légitime) = sessions dédiées ; fix d'un défaut d'isolation de test (pollution déterministe du singleton `RoutingDecider`). Certif arbre non commité : unit-fast **11068 passed / 0 failed / 276 skipped**, black 1656 / ruff / mypy strict 896 clean, 5 ratchets verts, app HEALTHY. Suit [ADR-129](#adr-129-rag-durable-jobs--upload--drive-sync-reprenables-au-crash).

### ADR-131: Interest Subject Variety — clustering LLM batch + sélection rareté deux niveaux

**Statut**: ✅ IMPLEMENTED (2026-07-18)
**Fichier**: `docs/architecture/ADR-131-Interest-Subject-Variety.md`

**Décision**: Remédiation du manque de variété des notifications centres d'intérêt : mesuré en prod, ~50 % des notifications portaient sur un seul sujet perçu (IA, fragmenté en 9 intérêts sur 19) alors que le tirage était déjà uniforme (`INTEREST_TOP_PERCENT=1.0`) — la cause est la **composition du pool**, pas le tirage. **Toutes les briques validées par bancs d'essai avant implémentation** (snapshot prod réel) : cooldown sémantique par seuil cosinus **réfuté** (espace écrasé : android/USA 0,794 > langchain/langgraph 0,783 ; seule zone fiable ≥ 0,95) ; labellisation LLM **incrémentale réfutée** (dérive selon l'ordre d'arrivée, accord 89 %, fusion aberrante deepseek+qwen+Chine) vs **batch validée** (98,2 % d'accord, partition ~12 sujets stable) ; simulation 300×30 j (modèle validé : uniforme simulé 47,9 % vs ~50 % mesuré) → toutes variantes γ/β convergent vers l'équirépartition (~8 %/sujet, poids trop plats), IA 50 %→33 %, **variante V5 retenue** (rareté sujet + intra-sujet, famine 0,8→0,3 intérêt/30 j). **Implémentation** : colonne `subject` dérivée (NULL = stale) + job de clustering batch (scan stale 30 min + nocturne 04h15, protocole JSON indexé fail-open) ; sélection pure `selection.py` (cooldown sujet 36 h — un frère en cooldown topic gèle son sujet —, tirage rareté deux niveaux, RNG injecté, fail-open à chaque étage, kill-switch `INTEREST_SELECTION_MODE=uniform`) ; **hygiène doublons** (fallback string quand l'embedding échoue — le trou du doublon « Anthropic »/« anthropic » —, garde collision au rename, retro-merge nocturne ≥ 0,95 avec repointage des notifications) ; **liens sources cliquables** ajoutés déterministiquement (markdown chat, conversion plain FCM/Telegram) ; **i18n proactive centralisée** (`ProactiveMessages`, fix du bug titres keyés `zh` vs `User.language`=`zh-CN` — les utilisateurs chinois recevaient les titres anglais). 4 métriques (`interest_selection_total`, `interest_subject_recluster_total`, `interest_merge_total`, `interest_selection_eligible_subjects`) ; panels Grafana différés à la prochaine passe dashboards (explicite). Suit [ADR-130](#adr-130-audit-v5--bilan-de-remédiation-findings-partiel--nouveau).

### ADR-132: HITL Approval Cards — approbations one-click, classifier bypassé

**Statut**: ✅ IMPLEMENTED (2026-07-18)
**Fichier**: `docs/architecture/ADR-132-HITL-Approval-Cards.md`

**Décision**: Achèvement de la couche interface du HITL (Lot 6 jamais câblé : `<LARSCard>` cité dans les docstrings, `useDraftActions` orphelin) — le moment le plus critique du produit (approuver une action à effet de bord) devient un geste à un tap. **Préambule de sécurisation** (bugs latents prouvés rouges puis fixés) : cancel ADR-117 laissait un `pending_hitl` orphelin (nettoyage sur `cancelled`, préservation volontaire sur `killed`) ; cache de détection jamais invalidé (extrait vers `utils/hitl_cache.py`, invalidation au chokepoint `HITLStore.save/delete`, setting `HITL_DETECTION_CACHE_TTL_SECONDS`) ; **abort de clarification** (« annule » bouclait à l'infini — branche `_classify_clarification` + branche abort du nœud + edge conditionnel → response, signal auto-nettoyant, prouvé E2E runtime). **Option B** : `ChatRequest.hitl_decision` → `build_structured_decision` (parité octet-pour-octet testée avec le chemin conversationnel, **fail-closed** `hitl_decision_stale` i18n ×6 avec double garde router/service, `message_id` persisté, alias d'actions canonisés serveur — `confirm_delete`/`confirm_all`), un appel LLM classifier économisé par approbation (`classifier_bypassed: true` prouvé logs). **Réhydratation** : `GET /agents/hitl/pending` (lecture autoritaire, no-store) — seul moyen de reconstruire la carte après reload. **Frontend** : branche `hitl` de la FSM chat-reducer (via_text = le texte reste premier, erreur transport ré-arme, stale expire), normalisateur des formats de facto (fixtures = captures runtime), `HitlActionCard` 4 types, i18n `chat.hitl.*` ×6. Périmètre V1 = confirm/cancel ; **P1-V2 livrée 2026-07-19** (section dédiée dans l'ADR) : édition inline des drafts — `modification_instructions` sur le wire, `edit` accepté UNIQUEMENT sur draft_critique (route la boucle draft_modifier vivante ; `updated_content` par champs = code mort sur toute la chaîne, toujours rejeté), formulaire inline sur la carte (mode dérivé par messageId), preuve runtime `classifier_bypassed=true` → `modified_fields=[subject]` → re-présentation → annulation. Chips clarification = V3. **Onboarding volet B livré 2026-07-19** (section dédiée) : pages actionnables — CTA connecteurs (complète la persistance PUIS navigue, sinon le dialog se re-monte) et exemples cliquables → `chat?draft=` pré-rempli sans envoi (`ChatInput.initialMessage`). Inclut le fix onboarding (CTA final persiste `onboarding_completed`). Findings hors périmètre consignés : autonomie ReAct post-refus (skill importé sans confirmation), `wrong_parameters` jamais confirmable, `ConversationalHitlResumption` = chemin mort apparent. Preuves : ~180 tests backend dédiés + 10 420 unit fast, 1 344 frontend, 13 E2E hermétiques, carte prouvée navigateur réel (hydratation, reload, clic), ratchets CC/taille tenus par décomposition (`hitl_pending.py`, `attachments_injection.py`). Suit [ADR-131](#adr-131-interest-subject-variety--clustering-llm-batch--sélection-rareté-deux-niveaux).

### ADR-133: Execution Trace Per Message — les coulisses survivent à la réponse

**Statut**: ✅ IMPLEMENTED (2026-07-18)
**Fichier**: `docs/architecture/ADR-133-Execution-Trace-Per-Message.md`

**Décision**: P2 du chantier UX cœur conversationnel — renversement délibéré de l'éphémère (« the whole block is ephemeral ») : au lieu d'effacer les étapes agentiques + le raisonnement au premier token de réponse, on les **capture et attache au message**. Mécanisme : deux refs de handler (`traceStepsRef`, `traceReasoningRef`) accumulent en parallèle des refs éphémères mais **ne sont PAS vidés au flip progress→answer** — ils vivent du début du tour (réinit par `router_decision`/nouvel envoi) jusqu'au `done`, où `TRACE_ATTACH` attache `{steps, reasoning, durationMs}` au message (no-op si aucun step → pas de disclosure vide ; cap `MAX_TRACE_STEPS=100` queue conservée ; marche dans les deux modes car `content_replacement` ReAct crée sous le même id sans toucher les refs trace). Steps structurés `{emoji, label, category}` réutilisant les traductions `execution.steps.*` déjà i18n ×6. Rendu `ExecutionTraceDisclosure` : ligne repliée « ⚙ N étapes · X s » dépliable vers steps groupés par catégorie + bloc raisonnement, monté paresseusement, i18n `chat.trace.*` ×6. Périmètre V1 = session-only (pas de persistance `message_metadata` = V2, avec garde PII clés-i18n-seulement). Changement 100 % frontend, aucun contrat SSE modifié. Preuves : reducer 5 tests, handlers 2 tests (cœur du renversement : survie au flip + attache au done), composant 6 tests, 1 357 verts front, tsc/eslint/ratchets propres, parité i18n ×6, trace prouvée navigateur réel. **V2 livrée (v1.25.12, 2026-07-22)** : capture serveur miroir de l'accumulateur live (`trace_capture.py` — reset+seed au `router_decision`, une occurrence par `i18n_key` par tour, cap settings `EXECUTION_TRACE_PERSIST_MAX_STEPS`), garde PII structurelle (forme persistée `{emoji, i18n_key, category}` — ni `detail` ni raisonnement), attache branch-free à l'archive (`FIELD_EXECUTION_TRACE` + `duration_ms`), hydratation `execution-trace-hydration.ts` re-résolvant les libellés — même type, même disclosure ; preuve runtime + navigateur : trace de 6 steps relue et dépliée sur une ligne d'historique rechargée. Suit [ADR-132](#adr-132-hitl-approval-cards--approbations-one-click-classifier-bypassé).

### ADR-134: Actionable Connector Error Notices — bandeau « Reconnecter » sur échec connecteur

**Statut**: ✅ IMPLEMENTED (2026-07-18)
**Fichier**: `docs/architecture/ADR-134-Actionable-Connector-Error-Notices.md`

**Décision**: P3 du chantier UX cœur conversationnel. Le plan initial (whitelist `ToolErrorCode.UNAUTHORIZED` dans les résultats d'outils) invalidé par l'investigation : ces codes ne sont produits par AUCUN tool connecteur (feature morte évitée), `connectors/error_handlers.py` est décoratif (`handle_oauth_error` jamais appelé), et le chemin dominant (refresh `invalid_grant`) levait un générique ré-avalé par l'`except Exception` de `get_connector_credentials` (log mensonger « decryption_failed »). Design retenu : classification par TYPES d'exceptions, jamais par message — nouvelle `ConnectorTokenExpiredError(ValidationError)` portant `connector_type` (héritage → contrat HTTP 400 et `except ValidationError` existants intacts, 51 tests intégration verts sans modification), attributs typés sur `ConnectorAPIError`, module `connector_error_notice.py` (classify : TokenExpired/401/403→reconnect, 429→rate_limit, reste→None ; émission custom LangGraph `execution_step`/`step_type:"tool_error"` writer-défensif + métrique `connector_error_notices_total`). Trois points d'émission : `handle_tool_exception` (PRINCIPAL — `ConnectorToolBase` attrape tout à `base.py::except Exception`, rien n'atteint les exécuteurs pour les tools standard ; mappe aussi l'error_code LLM vers UNAUTHORIZED/RATE_LIMIT_EXCEEDED) + 2 filets (boucle `return_exceptions` du parallel_executor, `except` de react_execute_tools). Contrat SSE structuré `{connector_type, action, tool_name}`, libellés résolus client-side. Front : interception avant l'accumulateur (pattern compaction) → `CONNECTOR_NOTICE_ADD` dédupliqué reducer, bandeau ambre « Reconnecter » → `settings?section=connectors`, dismiss, clear au prochain envoi, i18n ×6. Limite documentée : bandeau au run qui casse (ensuite `status=ERROR` → provider non résolu → « pas de connecteur ») ; V2 = notice à la résolution. Preuve bout-en-bout dev : token corrompu réversible → invalid_grant → chunk SSE observé → bandeau navigateur réel → état restauré. **V2 livrée (v1.25.12, 2026-07-22)** : `find_error_connector_type` détecte le connecteur de la catégorie en `status=ERROR` à la résolution (REVOKED exclu — déconnexion volontaire), enrichissement des `ConnectorNotEnabledError` AU RAISE (le handler central est sync) + émission directe dans `ConnectorTool.execute` (qui RETOURNE son erreur sans la lever) — mêmes points d'émission, même contrat SSE ; preuve runtime : connecteur forgé en ERROR → chunk `tool_error {google_gmail, reconnect}` observé dans un flux réel. Suit [ADR-133](#adr-133-execution-trace-per-message--les-coulisses-survivent-à-la-réponse).

### ADR-135: Heartbeat Interest Quality — échantillon varié, ledger unifié, anti-répétition par contenu, enrichissement concret

**Statut**: ✅ IMPLEMENTED (2026-07-19)
**Fichier**: `docs/architecture/ADR-135-Heartbeat-Interest-Quality.md`

**Décision**: Suite d'[ADR-131](#adr-131-interest-subject-variety--clustering-llm-batch--sélection-rareté-deux-niveaux) côté flux heartbeat : mesuré en prod, ~14 des 20 heartbeats « intérêts » sur 45 j tournaient autour d'A24/SF-horreur, quasi quotidiens, **sans jamais nommer un film**. Trois causes structurelles prouvées : (1) `_fetch_interests` demandait le top 30 % par poids EN DUR (mêmes ~6 topics à chaque tick, ignorait les sujets ADR-131) ; (2) l'anti-répétition opérait au niveau SOURCE sur 5 notifications (<2 j) en n'exposant que sources+reason, jamais le contenu — le modèle ne pouvait pas savoir qu'il proposait A24 dix soirs de suite ; (3) le contexte n'injectait que des NOMS de topics : sans matière, « jette un œil à une sortie récente » est le maximum atteignable. **Bancs prod avant implémentation** : schéma décision étendu (`interest_topic` + labels `Literal`) 8/8 valides sur deepseek-v4-flash (risque structured-output retiré) ; fenêtre à contenus débloque les pivots (2 notify/4 vs 0/7) MAIS fuite vers « 1664 » (canal mémoires) avec 5 items → **10 items / 7 j** et règle au niveau topic/produit/activité ; chaîne d'enrichissement prouvée (Perplexity → « The Backrooms (Kane Parsons) » + 8 citations → notification concrète 2/2 avec tissage météo conservé). **Implémentation** : `pick_varied_sample` (1 intérêt par sujet, sujets les moins récemment servis d'abord — la rotation est mécanique, pas rhétorique) ; **ledger unifié** `InterestNotification(source='heartbeat')` avec embedding, et **frontière explicite** (quota/cooldown global/pacing du flux intérêts et burst check heartbeat EXCLUENT ces lignes ; rareté, cooldown sujet, dédup contenu et purge GDPR les INCLUENT — 19 sites recensés) ; fenêtre anti-redondance 10/7 j rendant les extraits de contenu + règle à deux niveaux explicitement cross-source ; **enrichissement à la demande** (InterestContentGenerator sous timeout dur, bloc VERIFIED FACTS « nomme 1-2 éléments concrets, n'invente jamais », liens sources déterministes, dédup par embeddings récents — symétrie avec le flux intérêts) ; labels sources canoniques (`HeartbeatSourceLabel`, la dérive texte libre faussait les stats) ; **bonus** : `_map_source` connaît enfin « brave » (141 notifications/60 j étiquetées « custom »). Limite hors périmètre documentée : la source mémoires utilise une requête d'embedding FIXE (mêmes mémoires à chaque tick) — atténué par la fenêtre à contenus, rotation à traiter séparément. Suit [ADR-134](#adr-134-actionable-connector-error-notices--bandeau--reconnecter--sur-échec-connecteur).

### ADR-136: Posture COEP `credentialless` et états d'échec des widgets

**Statut**: ✅ IMPLEMENTED (2026-07-21)
**Fichier**: `docs/architecture/ADR-136-COEP-Posture-And-Widget-Failure-States.md`

**Décision**: Sur iPhone, les widgets chargeant un document par le réseau (carte `interactive-map`, MCP Apps) rendaient un **cadre vide muet**, alors que le morpion (`srcDoc`) fonctionnait. Cinq hypothèses réfutées par la mesure avant d'atteindre la cause (registre non persisté, attribut avalé par React, config cassée sur Chromium mobile, course du handshake du sas — 10/10 conformes dont CPU ×20 sur Slow 3G, sous-ressources CDN bloquées — 5/5 passent) : c'est l'absence d'état d'échec qui a rendu cette élimination nécessaire depuis l'extérieur. **Cause racine** (banc Playwright WebKit 26.4 vs Chromium, en-têtes de prod répliqués, embed Maps réel) : `COEP: require-corp` global — posé pour le `SharedArrayBuffer` du mot-clé vocal — n'est levé pour un document imbriqué sans COEP que par l'attribut d'iframe `credentialless`, **Chromium-only** ; WebKit refuse le document Maps (« Cancelled load … violates the resource's Cross-Origin-Resource-Policy »). Mesuré aussi : **l'isolation cross-origin n'est pas délégable** (un iframe porteur de COEP dans un top-level non isolé n'obtient ni `crossOriginIsolated` ni `SharedArrayBuffer`, sur les deux moteurs) — isoler le KWS dans son propre document est donc impossible ; et le **sas MCP est innocenté** (verrous franchis, charge utile exécutée sur WebKit, 5/5 configurations). **Trois décisions** : (1) posture par défaut `credentialless` via `resolveCoepMode()`, réglable par `COEP_MODE` sans reconstruction (schéma `HSTS_MAX_AGE`), repli sur le défaut pour toute valeur non reconnue — Chromium inchangé (isolation + SAB + carte), WebKit perd le mot-clé vocal (dégradation **préexistante et déjà gérée** par `isSherpaKwsSupported()` / `VoiceModeBadge` → appui-pour-parler) et récupère tous les embeds ; (2) `canEmbedOpaqueCrossOriginFrame()` refuse de rendre un embed que le moteur rejettera, et affiche un lien actionnable à la place ; (3) `useFrameLoadWatchdog()` donne enfin un état d'échec à tout widget (message + Réessayer + lien) et journalise `widget_frame_load_timeout` avec `crossOriginIsolated` et `credentiallessSupported` — les deux faits qui rendent un signalement distant exploitable seul. Complète [ADR-098](#adr-098-csp-widget-airlock--per-document-policies-for-third-party-widgets), qui avait restauré ces widgets sur Chromium sans vérifier WebKit. Suit [ADR-135](#adr-135-heartbeat-interest-quality--échantillon-varié-ledger-unifié-anti-répétition-par-contenu-enrichissement-concret).

### ADR-137: Les sentinelles de widget appartiennent à l'hôte, et voyagent avec leur message

**Statut**: ✅ IMPLEMENTED (2026-07-21)
**Fichier**: `docs/architecture/ADR-137-Host-Owned-Widget-Sentinels-And-Message-Persistence.md`

**Décision**: Quatre défauts du chemin widget, tous prouvés sur la base de production. (1) **Doublon** : le message `28eaa427` portait deux fois `skill_app_545e26` et le frontend montait deux iframes — arithmétique exacte 1195 + 2 + 400 = 1597 = longueur en base. Chaîne prouvée : `_render_response_html` ajoute le sentinelle → le contenu enrichi retourne dans `state["messages"]` → `_window_messages_for_react` sert cet historique BRUT à la boucle ReAct (le chemin réponse neutralise le HTML, celui-là jamais) → le modèle imite → l'injection déterministe en ajoute une seconde. (2) **Fantômes** : deux réponses portaient un sentinelle jamais injecté, pointant vers un identifiant d'un tour antérieur (dont une disant « je n'ai pas accès à ta position » tout en affichant une carte). (3) **Registre jamais persisté** : `message_metadata` ne contenait que `run_id`/`intention`/`psyche_state` ; rendu du contenu de production réel avec registre vide = 2 encadrés d'erreur, 0 iframe. (4) `react_result` portait deux formes sous un `Any` (crash `AttributeError` sur le run `117ce96f`, tour réduit à 98 caractères) et `_plan_already_produced_skill_app` balayait tout `agent_results` (clés des tours 41→48) au lieu du tour courant, faisant disparaître la carte du run `d0fad28b`. **Décisions** : invariant « le LLM n'écrit jamais de markup de widget » via `sentinel_filter` (`html.parser`, jamais une regex — le sentinelle imbrique des `<div>`) posé à TROIS points d'étranglement, avec métrique `widget_sentinels_stripped_total{source}` et un verrou N widgets = N sentinelles dont la non-vacuité est prouvée ; persistance du payload sur le message (`message_metadata.widgets`) après avoir REJETÉ PAR LA MESURE la réhydratation depuis le checkpoint (canal `registry` plafonné LRU à 75, ~70 déjà utilisés → perte silencieuse), types restreints à SKILL_APP/MCP_APP (DRAFT exclu : état HITL), budget `widget_persist_max_bytes` avec abandon plutôt que troncature, et `is_system_skill` RECALCULÉ à la lecture (il gouverne `credentialless` + `allow-same-origin`) ; `react_result` normalisé sur le contrat d'état unique et typé `dict | None` ; garde de skip scopée au préfixe `{turn_id}:`. **Ordre d'application obligatoire** : corriger le doublon AVANT la persistance, sinon les fantômes deviennent réels au rechargement. Suit [ADR-136](#adr-136-posture-coep-credentialless-et-états-déchec-des-widgets).

---

### ADR-138: Feedback 👍/👎 sur les réponses ordinaires

**Statut**: ✅ IMPLEMENTED (2026-07-22)
**Fichier**: `docs/architecture/ADR-138-Response-Feedback.md`

**Décision**: Le pattern de feedback complet n'existait que pour les notifications proactives ; les réponses ordinaires n'avaient qu'un bouton Copier. QW-5 (chantier Quick Wins UX) ajoute `POST /conversations/me/messages/{id}/feedback` : verdict persisté dans `message_metadata.response_feedback` par UPDATE `jsonb_set` atomique scopé propriétaire (pattern `mark_interest_feedback_submitted`), identification du message par `archived_message_id` dans le chunk `done` (l'archive précède le done — vérifié) et `message_db_id` sur les lignes d'historique. Couplage journaux par **port injecté** (`JournalFeedbackHooks` Protocol côté conversations, implémentation `journals/feedback_hooks.py`, enregistrement au startup) — un import direct, même paresseux, fermait le cycle de domaine conversations↔journals (attrapé par le garde F009). Compteurs evidence/contradiction alimentés au PREMIER verdict seulement (pas de décrément — un changement de verdict ne re-compte jamais) ; commentaire du 👎 déposé comme entrée L0 `user_correction` SANS consolidation (pas de coût LLM par pouce) ; métrique `response_feedback_total{verdict}` ; jamais de re-génération automatique. Frontend : chips à côté de Copier, `aria-pressed`, hydratation cross-device, champ correction optionnel.

---

### ADR-139: Registre des boucles ouvertes (open loops) et relance heartbeat

**Statut**: ✅ IMPLEMENTED (2026-07-22)
**Fichier**: `docs/architecture/ADR-139-Open-Loops-Commitments-Ledger.md`

**Décision**: P5 du programme Interdomain Intelligence (pilier « l'assistant qui n'oublie rien ») — aucun sous-système ne suivait les engagements exprimés en conversation (« je dois rappeler le plombier », « Marie doit m'envoyer le devis »). Nouveau bounded context `domains/open_loops/` : table `open_loops` (direction user_owes/waiting_on_other, `due_hint` UTC consultatif, statuts open/closed/expired, `last_nudged_at`+`nudge_count` anti-harcèlement, index partiel WHERE status='open'), transitions par UPDATE conditionnel atomique. Extraction = **5e extraction post-réponse** (mêmes gardes que mémoire/intérêts/journaux/psyché ; nouveau type LLM `open_loop_extraction` tier LOW) : une passe structurée voit la queue de conversation ET les boucles existantes (ids) → `open` + `close` conversationnel (« c'est fait ») ; règles d'application déterministes testées à part (caps, doublons, ISO tolérant). Relance via nouvelle source heartbeat (expiry **paresseuse** — pas de job dédié ; filtre nudge-worthy échéance/stagnation hors cooldown ; règle 19 du prompt de décision, une boucle max par notification) ; bump du cooldown APRÈS notification délivrée et seulement si `sources_used` contient `OPEN_LOOPS` (même emplacement transactionnel que le ledger ADR-135). API v1 minimale sous flag `OPEN_LOOPS_ENABLED` (défaut false) ; clôture par scan email et UI reportées (v2 / Lot 4). Vérification : TDD intégral, migration tête unique, preuve runtime dev.

---

### ADR-140: Automatisations pilotées depuis le chat + suggestion de récurrence

**Statut**: ✅ IMPLEMENTED (2026-07-22)
**Fichier**: `docs/architecture/ADR-140-Chat-Piloted-Automations.md`

**Décision**: P11+P12 du programme Interdomain Intelligence — les scheduled actions s'exécutaient via le pipeline complet mais ne se pilotaient que depuis l'UI. Nouveau domaine routable `automation` (interne) + 3 outils : création = **draft SCHEDULED_ACTION confirmable** (D4 ; exécuteur → `ScheduledActionService.create`, cap par utilisateur), listing (ids réels), toggle direct (réversible, pas de draft) ; suppression = UI seulement en v1. Plomberie draft complète boot-assertée (display registry, preview renderer + goldens, i18n ×6 clés `zh-CN`). **Détecteur de récurrence déterministe** (P12, pas de table ni LLM) : ledger Redis par (user, signature domaines@bucket-4h heure locale), écrit en 7e bloc post-réponse ; suggestion one-shot par cooldown quand ≥ N jours DISTINCTS dans la fenêtre, texte ×6 injecté via le slot `STATE_KEY_INITIATIVE_SUGGESTION` existant — le nœud initiative devient wrapper fin (`_initiative_core` inchangé), flags indépendants (marche même si INITIATIVE_ENABLED off). Rejetés : PlanPatternLearner (stats globales sans timestamps par user — vérifié), injection response_node (ratchet taille), draft sur toggle (friction). Flag `RECURRENCE_SUGGESTION_ENABLED` défaut OFF ; mesure J+14 à l'activation.

---

### ADR-141: Couche de connaissance active — domaine documents et personne 360°

**Statut**: ✅ IMPLEMENTED (2026-07-22)
**Fichier**: `docs/architecture/ADR-141-Active-Knowledge-Layer.md`

**Décision**: P1+P3 du programme Interdomain Intelligence. **P1** : domaine routable `document` — `search_user_documents_tool` (read-only) sur `retrieve_rag_context` existant, extraits plafonnés ; routabilité filtrée au chokepoint `_build_available_domains` quand `RAG_SPACES_ENABLED` off (pattern téléphonie) ; l'injection passive du response node coexiste (appoint auto + capacité dirigée). **P3** : `get_person_overview_tool` sur contact_agent — 4 sous-fetches parallèles à sessions et frontières d'échec propres (fiche contact multi-provider pattern heartbeat, emails récents, événements 30 j, mémoires par embedding du nom), **partialité honnête** (`partial_failures` ; connecteur absent = bloc vide, contact introuvable = `person_not_found`). Enregistrements via l'agrégateur `registry/program_manifests.py` (coût net zéro dans le loader gelé). Rejetés : fusion avec le domaine `file` (sémantiques disjointes), `Memory.linked_contact_id` v1 (différé post-J+14 P5), sous-fetches Drive/rappels (différés). Vérification : TDD, suites vertes, runtime dev.

---

### ADR-142: Observabilité psyché & recentrage de la dominance

**Statut**: ✅ IMPLEMENTED (2026-07-22) — leviers livrés inertes ; activation conditionnée à la mesure production
**Fichier**: `docs/architecture/ADR-142-Psyche-Observability-And-Dominance-Recentering.md`

**Décision**: Suite d'ADR-104, dont la re-mesure production promise n'a jamais été outillée. Le rejeu déterministe du vrai moteur + le calcul sur le catalogue réel exposent deux défauts : (1) **l'axe dominance est structurellement décentré** — les 14 personnalités reposent toutes en D>0 (moyenne +0.216, confirmée live), 5 centroïdes d'humeur en D<0 inatteignables au repos, et le damping (homothétie) ne peut PAS recentrer — il faut une **translation** ; (2) le **pulse proactif joy** couronne joy dominante 55 % des tours indépendamment de l'appraisal réel (même mécanisme que le pulse pride supprimé). Livré, tout inerte au merge : `PSYCHE_DOMINANCE_CENTER` (défaut 0.0 ; candidat 0.20 **dérivé** du catalogue), `PSYCHE_PROACTIVE_JOY_PULSE` (défaut true), instrument de mesure read-only `apps/api/scripts/measure_psyche.py` (batterie ADR-104 par utilisateur + table de repos du catalogue ; dans le contexte de build prod), gardes CI `test_mood_reachability.py` (goldens 1e-9 = merge prouvé no-op, straddle à 0.20 ordre préservé, oracle bout-en-bout 3 humeurs/87 % → 5/40 %). kindalive examiné comme source : principe d'équilibre retenu comme grille de lecture, mécanismes testés et **rejetés** (τ par axe réfuté par ablation, équilibre symétrique contre-indiqué). Procédure d'activation mesurée avant/après + matrice de réajustement (fidélité de caractère via `pad_dominance_override`, repli 0.15). 24 tests nouveaux, suite psyché 207 verts, zéro migration.

---

### ADR-143: Authentification forte — passkeys WebAuthn, TOTP, step-up (D1)

**Statut**: 🚧 PHASED — Lot 1 (passkeys) IMPLEMENTED (2026-07-23) ; Lots 2 (TOTP) et 3 (step-up) conçus, en file
**Fichier**: `docs/architecture/ADR-143-Strong-Authentication-Passkeys.md`

**Décision**: L'instance publiquement exposée n'avait que mot de passe + OAuth Google. Lot 1 livré : passkeys WebAuthn (py_webauthn 2.8.0 épinglée — la 3.x exige cryptography ≥ 49) avec credentials **découvrables** (resident key + user verification requis, arbitrage A1) et **conditional UI** (autofill) + bouton explicite ; table `webauthn_credentials` (matériel public uniquement, classée USER_PURGED/EXCLUDED dans la user_data_map du Lot 0) ; challenges à usage unique en Redis (GETDEL, TTL 300 s) ; payload de session **v2** avec `auth_methods` (défauts rétro-compatibles testés en round-trip — socle du step-up Lot 3 et de l'affichage appareils D2) ; rejet des régressions de compteur (clone) en 401 générique ; rate limiting par IP (anonyme) ET par utilisateur (enrôlement) ; sonde publique `GET /auth/features` pour le gating UI sans sonder des routers démontés ; flag `MFA_ENABLED` défaut false (router non monté). E2E héritique Chromium avec virtual authenticator CDP (cérémonie réelle, API mockée). Conçus et actés pour la suite : TOTP chiffré Fernet + 10 codes de secours « révélés une fois » (pattern hm_), step-up en **403 + `step_up_required`** (jamais 401 — hard-redirect client), désactivation du mot de passe seulement avec ≥ 2 passkeys (A8). Doc maître : `docs/superpowers/specs/2026-07-23-security-account-program.md`.

---

### ADR-144: Sessions par appareil — visibilité et révocation « Mes appareils » (D2)

**Statut**: ✅ IMPLEMENTED (2026-07-23)
**Fichier**: `docs/architecture/ADR-144-Device-Sessions.md`

**Décision**: Les sessions BFF Redis existaient sans aucune visibilité ni contrôle utilisateur. Livré : payload de session **v4** avec réversion PII **bornée** (A3 — familles navigateur/OS via parser maison, IP tronquée /24, last-seen à grain ≥ 15 min en `keepttl`, chokepoint unique `core/client_metadata.py`, sessions legacy = « appareil inconnu ») ; identifiants d'affichage **opaques** (sha256[:16] — l'id de session brut ne quitte JAMAIS le serveur) ; endpoints `/auth/sessions` montés inconditionnellement (liste avec badge courant + noms d'appareils attestés, révocation unitaire en auth simple, `revoke-others` sous **step-up**) ; **coupure SSE** à chaque tick keepalive (`session_still_valid` fail-open, commentaire `: session-revoked`) sur le relay broker ADR-117 ET les deux boucles legacy — les producteurs détachés continuent par design ; **notification de nouvelle connexion attestée par FCM** (A4 révisé : token FCM actif du compte = preuve de possession de l'appareil ⇒ silencieux + nom réel affiché ; passkey = connu par définition ; OAuth = notifie toujours ; issue portée dans le pending token du login deux-étapes ; préférence `login_notifications_enabled` défaut TRUE, push localisé ×6, best-effort). Migration `a8c4e6f21b73`. Rejeté : registre d'appareils persistant (surface PII durable pour un gain marginal vs attestation FCM).

---

### ADR-145: Export complet du compte — portabilité RGPD (D3)

**Statut**: ✅ IMPLEMENTED (2026-07-23)
**Fichier**: `docs/architecture/ADR-145-Account-Export.md`

**Décision**: Aucun export de compte n'existait. Livré : jobs **durables** (A6 — table `account_export_jobs` + executor à intervalle sous flag `ACCOUNT_EXPORT_ENABLED`, `FOR UPDATE SKIP LOCKED`, transitions atomiques, un job non-terminal par utilisateur via index partiel unique, RUNNING > 30 min = `crashed`, sweep de rétention 24 h) ; builder **metadata-driven** : le périmètre dérive de `user_data_map.ExportPolicy.FULL` — les tables EXCLUDED (credentials, tokens, matériel WebAuthn/TOTP, codes de secours) ne peuvent PAS atteindre une archive **par construction**, garanti par la garde `test_export_completeness.py` (toute table FULL doit être scopable, specs de redaction/déchiffrement vérifiées colonne par colonne) ; `callee_phone` sort **déchiffré** (la portabilité = données lisibles) ; archive = JSON par table + Markdown lisible (conversations/journal/mémoires) + fichiers attachments/RAG sources en `ZIP_STORED` (A5, dérivés exclus), plafond 2 GiB, rename atomique ; demande sous **step-up**, téléchargement authentifié borné par la rétention, push FCM « export prêt » ×6. Migration `b9d5f7a32c84`. Rejeté : 25 exporters manuscrits (dérive garantie) et APScheduler `run_date` (perdu au restart).

---

### ADR-146: PWA hors ligne — service worker unifié et page offline (D5)

**Statut**: ✅ IMPLEMENTED (2026-07-23)
**Fichier**: `docs/architecture/ADR-146-Offline-PWA.md`

**Décision**: Seul un SW push-only existait, enregistré au scope `/` et uniquement dans le flux FCM. Livré (A7) : **SW unifié** — `firebase-messaging-sw.js` garde son URL historique (mises à jour in-place des registrations) et possède push ET offline (precache `offline.html` + icônes, navigations network-first avec fallback brandé, stale-while-revalidate des statiques same-origin ; **jamais** de cache `/api/*`, non-GET, cross-origin ni SSE — les données personnelles ne touchent pas le disque) ; **enregistrement inconditionnel** au layout (prod uniquement) réutilisé par FCM ; **versioning gardé par test exécutable** (`CACHE_VERSION` == package.json, purge des caches stales à l'activate, `Cache-Control: no-cache` sur le fichier SW) ; page offline autonome avec i18n ×6 inline (cookie i18next), clair/sombre, bouton réessayer, parité assertée par test. Rejeté : deux SW à scopes séparés (risque de migration pur) et l'injection de version au build (constante gardée plus simple).

---

### ADR-147: Grounding de la réponse sur les entités récentes

**Statut**: ✅ IMPLEMENTED (2026-07-23)
**Fichier**: `docs/architecture/ADR-147-Recent-Entities-Grounding.md`

**Décision**: Défaut prod — LIA annonçait un rendez-vous « à 16h » alors que l'outil agenda avait renvoyé **11h15** deux tours plus tôt. Cause structurelle : sur un tour sans outil, `filter_registry_by_current_turn` renvoie `{}` (correctif anti-contamination 2025-12-26), `{data_for_filtering}` en dérive donc vide, et `<History>` exclut délibérément les `ToolMessage` — le LLM n'a **aucune donnée autoritaire** et ne peut que recopier de la prose. Livré : re-grounding depuis le state, **uniquement** si le registre du tour est vide **et** que le tour n'est pas REFERENCE (exclusion de **sécurité** : leur registre vide est un fail-safe anti-fuite, pas un trou de grounding) ; sélection **par récence** via les clés `agent_results` (`{turn_id}:{agent}`), plus récent d'abord, dédupliqué, plafonné à `TOOL_CONTEXT_MAX_ITEMS` avec troncature **loguée** ; source = `state["registry"]` fusionné (**zéro I/O**) ; sérialiseur canonique `generate_data_for_filtering` ; section de prompt dédiée `<RecentEntities>` **après** le marqueur dynamique (préfixe cacheable intact), sans balise si vide, explicitement **non autoritaire** (« current turn data wins ») ; règle `<DataAuthority>` complémentaire interdisant d'inventer un attribut d'entité — et **citant `<RecentEntities>` parmi ses sources autorisées** (ne lister que « tour courant ou `<History>` » revenait à interdire le seul canal porteur sur un tour sans outil) ainsi que le cas « donnée demandée mais jamais reçue » (aucune température inventée). Réglage `RESPONSE_RECENT_ENTITIES_MAX_TURN_AGE` (0 = désactivé). Rejeté : ré-injection dans `current_turn_registry` (rejouerait le bug de contamination), **bornage par domaine de la requête** (implémenté puis abandonné : `RoutingDecider` route vers la réponse *précisément* quand aucun domaine n'est détecté → grounding inerte sur sa cible), lecture du Tool Context Manager (aller-retour store + mapping de domaines pour une donnée déjà en state), et réutilisation de `{data_for_filtering}` (brouillerait le contrat d'autorité du tour courant).

---

### ADR-148: Agrégation journalière côté SQL pour les signaux santé du heartbeat

**Statut**: ✅ IMPLEMENTED (2026-07-24)
**Fichier**: `docs/architecture/ADR-148-Health-Daily-Rollup.md`

**Décision**: Défaut prod — `heartbeat_health_signals_timeout` 40 fois en 7 jours pour 86 décisions (**46,5 %**), un heartbeat sur deux décidé sans signaux santé, en silence. Cause : `build_heartbeat_health_signals` émettait **6 requêtes / 30 662 lignes** par tick (dont deux paires de doublons exacts sur 36 jours) pour produire quelques dizaines de nombres. Le coût n'était **ni SQL** (PostgreSQL : 6,7 ms, index scan) **ni ORM** (+58,8 ms) mais le **décodage par ligne côté client** (~29 µs/ligne), une rafale synchrone bloquant l'event-loop du worker **483 ms d'un seul tenant**. Livré : primitive `fetch_daily_stats` renvoyant une ligne par jour UTC avec les **primitives entières brutes** `(total, count, minimum)` — toute agrégation s'en dérive, et `total / count` étant la même opération IEEE-754 que `sum/len`, l'équivalence est *démontrable* (un mapping `BaselineKind → fonction SQL`, première conception, aurait été infidèle à `detect_notable_events` pour tout futur kind `DAILY_AVG`) ; **inversion de couplage** dans `baseline.py`/`signals.py` (points d'entrée `*_from_stats` + enveloppes historiques → les 19 tests existants passent inchangés, par construction) ; normalisation `timezone('UTC', …)` explicite verrouillée par un test d'intégration sous session UTC+14 ; extractions `heartbeat_signals.py` et `health_context.py` plutôt que relèvement de plafond (cap de `context_aggregator.py` **abaissé** 783 → 753) ; budget de 2,0 s **non relevé** et sa docstring corrigée (il borne une part d'event-loop partagé, pas un temps de base) ; abandons désormais **comptés** (`heartbeat_source_dropped_total`) et **chronométrés**. Mesuré : **353 → 7,0 ms (×50)**, lag event-loop **124 → 1,1 ms**. Rejeté : relever le budget (traiter le symptôme), ajouter un index (plan déjà optimal), convertir `compute_kind_daily_breakdown` (exige sa propre preuve d'équivalence — hors périmètre, documenté).

### ADR-149: Remédiation sécurité 2026-07 — vague 1

**Statut**: ✅ IMPLEMENTED (2026-07-25)
**Fichier**: `docs/architecture/ADR-149-Security-Remediation-Wave-1.md`

**Décision**: Réponse à l'audit sécurité du 2026-07-13, chaque constat re-vérifié dans le code (plusieurs faux positifs écartés ; SEC-030/SEC-032/FN-3/FN-5 trouvés en plus par la vérification). Six décisions. **(1) Scripts de skills en conteneur jetable (SEC-001)** — la chute d'uid ne protégeait que si l'API tournait en root ; en prod elle tourne en `appuser`, membre du groupe `docker`, **hérité** par les fils : un script valait root sur l'hôte. `cap_add SETGID` mesuré inopérant (pas de capacité *ambiante* pour un non-root). Le **source** est passé en argument (`python -c`) et non monté — l'API étant elle-même un conteneur, un bind se résoudrait contre l'hôte — ce qui laisse stdin libre pour la charge JSON. Aucun mode dégradé : sans démon, exécution **refusée**. Prouvé : uid/groupes `65534`, socket absente, réseau coupé, rootfs en lecture seule, aucun secret exposé ; **9/10 scripts livrés produisent une sortie identique octet pour octet** aux deux modes (le 10e utilise `secrets`). Défaut trouvé et corrigé en chemin : tuer le client `docker run` **n'arrête pas le conteneur** (mesuré) et un script qui dort ne consomme aucun CPU → nom unique + `docker rm --force` dans le thread de travail. **(2) Plafond HTTP global appliqué (SEC-016)** — le `slowapi.Limiter` posé sur `app.state` n'était consulté par rien (ni middleware ni décorateur) et comptait en mémoire, soit un budget par worker ; remplacé par un middleware ASGI sur le `RedisRateLimiter` partagé, calibré sur la mesure (pic réel 67 req/min → défaut 300), sondes exemptées, **fail-open** assumé mais compté (`http_rate_limit_degraded_total` + alerte). Helpers devenus morts **supprimés**, pas conservés sous perfusion de tests. **(3) Corps de requête borné avant lecture (SEC-031)** — les endpoints validaient après matérialisation (webhooks : avant authentification) ; plafond global asserté **au démarrage** contre les plafonds d'upload configurables jusqu'à 100 Mo, pour qu'une incohérence ne devienne pas un 413 distant inexplicable. **(4) Confirmation systématique des tâches DevOps (FN-1)** — `hitl_required=True` seul ne couvre que ReAct (le pipeline auto-approuve) et changer `tool_category` cassait le validateur sémantique : le tool **n'exécute plus**, il produit un brouillon `DEVOPS_TASK` et la session SSH n'a lieu qu'après approbation, reprise de session comprise. Streaming de progression préservé par `ContextVar` (sinon confirmer transformait un flux en attente muette de 30 s). Deux défauts de la première implémentation corrigés en contre-revue : la carte masquait `context` — champ produit par le modèle qui atterrit dans `--append-system-prompt`, donc **le** vecteur d'injection — et les droits n'étaient vérifiés qu'à la création du brouillon (un admin révoqué voyait sa tâche s'exécuter). Plafond de taille **non relevé** : extraction registre/feuille. **(5) Validation à chaque saut sortant** — MCP OAuth (5 points, dont 2 manqués par l'audit, verrouillés par une garde AST prouvée par mutation), image de profil (redirections suivies à la main), navigateur (intercepteur **fail-closed**, déployé en `report-only` d'abord). **(6) Journaux (P1/P2)** — `uvicorn.access` a `propagate=False`, les URL d'accès partaient donc en clair hors du filtre PII ; loggers repris + paramètres GPS ajoutés aux paramètres sensibles, `code`/`state`/`lat`/`lng` vérifiés `[REDACTED]` en runtime. Non fait, et dit : `slowapi` reste épinglé (retrait = changement de dépendances à part, ADR-112), `BROWSER_SSRF_ENFORCE` reste à `false` tant que le taux de blocage réel n'est pas observé.

---

### ADR-150: Continuité générationnelle de la recherche RAG pendant une réindexation

**Statut**: ✅ IMPLEMENTED (2026-07-25)
**Fichier**: `docs/architecture/ADR-150-RAG-Generational-Continuity.md`

**Décision**: Réponse à l'audit qualité 2026-07-24 (AC-001). `retrieval.py` retournait `None` pour **toutes** les recherches sur espaces utilisateur pendant une réindexation (flag Redis global) — un changement de modèle d'embedding suspendait globalement la recherche. Comme `process_document` échange les chunks atomiquement **par document**, un simple filtre « ancienne génération » ferait disparaître chaque document reprocessé (fenêtre vide progressive) ; la continuité pleine exige donc des **générations côte-à-côte**. Colonne durable `rag_spaces.serving_embedding_model` (migration `c1d2e3f4a5b6`, `NULL` = régime permanent rétro-compatible) : au démarrage la réindexation **épingle** les espaces sur l'ANCIEN modèle dans la même transaction atomique que le requeue durable (F001/V8) ; `process_document`, piloté par ce pointeur durable (drain **ET** reaper), ne supprime que la génération cible et **préserve la génération servie** ; après le drain, chaque espace pleinement rebâti est **basculé atomiquement** (pointeur→`NULL` + suppression de l'ancienne génération en une transaction) — jamais de mélange ni de fenêtre vide. Résumable après crash : le reaper rebâtit puis `flip_pinned_spaces_if_ready` bascule ce que le drain interrompu n'a pas atteinte ; « échec → on garde N ». `retrieve_rag_context` groupe les espaces par génération servie (≤ 2), embed avec le modèle de chaque génération (clients per-modèle) et filtre les chunks — en régime permanent, un seul groupe sans filtre (chemin historique). **Changement de DIMENSION = fenêtre de maintenance documentée** (AC-001b, décision explicite) : deux dimensions ne cohabitent pas dans une colonne pgvector, le chemin destructif résumable est conservé et la continuité côte-à-côte ne s'active que si `current_dims == new_dims`. Uploads pendant la migration : **invisibilité temporaire assumée** (déjà dans la génération cible, aucun retraitement au flip), observable. Prouvé par 8 tests d'intégration PostgreSQL réels (lecture sans fenêtre vide ni mélange, bascule + reclaim, flip différé sur échec, reprise reaper) ; métrique `rag_reindex_space_flips_total{outcome}`.

---

### ADR-151: Le workflow CI orchestre, le Taskfile implémente

**Statut**: ✅ IMPLEMENTED (2026-07-25)
**Fichier**: `docs/architecture/ADR-151-Thin-CI-Workflow.md`

**Décision**: Des gates étaient systématiquement découverts par un build rouge **après** un local vert (gate de couverture par markers en v1.25.20, ratchet de complexité frontend et parcours a11y en v1.25.16, seuils de couverture par fichier en v1.25.12). La cause était structurelle : `ci.yml` contenait **144 lignes de commandes — dont 97 de gates inline — et zéro appel `task`** — CI et Taskfile étaient deux implémentations parallèles libres de diverger. Désormais chaque étape `run:` est un appel `task <nom>` (**15 appels**, −128 lignes nettes) : la CI exécute *littéralement* la commande du développeur. Les contrôles inline sont portés vers `scripts/audit/check_code_hygiene.py`, en **Python et non en bash** (l'hôte est Windows, le runner Linux : un contrôle bash-only n'est jouable que d'un côté), **sévérités inchangées par le portage**. Huit tâches créées pour des gates qui n'avaient aucun équivalent local, et deux paliers : `task ci:fast` (~10 min mesuré, sans service, à lancer avant un push) et `task ci`. La comparaison commande par commande a exhumé quatre divergences réelles, dont **le plancher de couverture de 60 % qui n'existait pas en local** (`unit:fast` troque la couverture contre xdist), un `lint:docs` sans `--fail-on-stale` (gate local plus permissif que le distant), et une **fuite d'environnement mesurée** : `dotenv: - .env` étant global, `NEXT_PUBLIC_API_URL` fait tomber `voice-input-service.ts` à 80 % de branches contre un plancher de 83 %. La propriété est rendue **structurelle** par `check_ci_parity.py` (`task lint:ci-parity`), qui échoue sur toute étape `run:` qui n'est ni un appel de tâche, ni un provisionnement déclaré, ni une des **trois** exceptions CI-only motivées par écrit (promtool natif vs conteneur ; replay des migrations in-container, F048 ; suite Python 3.13, F041). Trois jobs n'avaient **jamais tourné** avant la conversion (Code Hygiene, E2E + a11y, Test Backend Integration) : verts, et le job d'intégration est plus strict qu'avant (`LIA_REQUIRE_DB=1`, F019). Contrats parallèles supprimés au passage : seuil de couverture à source unique, expression de markers du hook alignée sur sa tâche, trois gardes dans `test_task_ci_pytest_parity_guard.py`. **Limite assumée et dite** : l'iso porte sur les **commandes**, pas sur l'**environnement** — une divergence de shell ou de permissions Windows/Linux échappe toujours au local.

---

### ADR-152: Suppression de trois hooks frontend orphelins

**Statut**: ✅ IMPLEMENTED (2026-07-25)
**Fichier**: `docs/architecture/ADR-152-Removal-Of-Orphan-Frontend-Hooks.md`

**Décision (ADR-152)**: Trois hooks avec **zéro consommateur** (recherche exhaustive sur `src/`, `e2e/` et `docs/` — seuls les ré-exports de `hooks/index.ts` apparaissaient) sont supprimés plutôt que testés : les couvrir aurait fabriqué de la couverture sur du code que personne n'exécute. `useDraftActions` (187 l.) sérialisait `{"type":"draft_action", …}` dans un message de chat — format que `grep -rn '"draft_action"' apps/api/src` ne trouve **nulle part** : [ADR-132](#adr-132-hitl-approval-cards) l'avait déjà signalé orphelin et remplacé par `ChatRequest.hitl_decision` → `HitlActionCard`, si bien que le hook n'était pas seulement mort mais **cassé** ; `src/types/draft.ts` (325 l.) n'existait que pour lui. `usePaginatedQuery` (190 l.) n'a jamais été câblé et portait déjà un défaut (un changement de `searchQuery` ne remet pas `page` à 1 alors qu'il fait partie des `deps` : recherche lancée depuis la page 5 → « aucun résultat »). `useFormHandler` (159 l.) est supplanté par `useApiMutation` et son exemple de docstring appelle `fetch` directement, ce que la convention frontend interdit — le garder laissait un exemple enseignant l'anti-pattern. **861 lignes retirées**, `tsc --noEmit --incremental false` vert sans un seul diagnostic après retrait. Alternative écartée : câbler `usePaginatedQuery` dans les sections d'administration (refonte à risque, sans bénéfice fonctionnel, et le hook devrait d'abord être corrigé).

---

### ADR-153: Taxonomie d'action HITL — classification par verbe et exemples à couverture close

**Statut**: ✅ IMPLEMENTED (2026-07-26)
**Fichier**: `docs/architecture/ADR-153-HITL-Action-Taxonomy.md`

**Décision**: Le type d'action annoncé au classifieur HITL (`Action type: …` dans le prompt, et le bloc d'exemples *few-shot* associé) était dérivé par une échelle `if/elif` de sous-chaînes où un **nom de domaine siégeait dans une branche de verbe** (`"email"` dans la branche SEND, testée **avant** DELETE). Mesuré sur les 96 outils réellement enregistrés : `delete_email_tool`, `get_emails_tool` et `get_email_details_tool` étaient annoncés comme des **envois** — pour une suppression d'e-mail, le prompt mentait au modèle, lui injectait les exemples d'envoi, et rendait **inatteignable sa propre règle de sûreté** (« *If Delete action and user says Wait, default to REPLAN/REJECT, never APPROVE* »). La classification passe sur le **verbe de tête** (`<verbe>_<domaine>_tool` est la convention du dépôt), dans un module dédié `services/hitl/action_taxonomy.py` ; le repli par sous-chaîne subsiste pour les noms non préfixés (MCP, skills) mais **ordonné destructif d'abord** et **sans aucun nom de domaine**. `ACTION_TYPE_UPDATE/FORWARD/REPLY`, déclarés et jamais utilisés, sont câblés : cela corrige un second cas de la même famille — une **réponse** n'a pas de paramètre destinataire, alors que les exemples d'envoi poussaient le modèle à produire un `{"to": …}` que `reply_email_tool` ne peut pas accepter. La couverture des exemples devient **close** : `assert_examples_coverage()` dérive l'attendu de la taxonomie (la garde précédente le listait à la main et ne pouvait pas voir un type nouvellement émissible), échoue au boot (modèle ADR-085) et en CI. Trois messages français codés en dur sur le chemin de reprise — **diffusés mot pour mot à l'utilisateur** par `draft_critique.py` — passent en `HitlResumeMessage` dans les 6 langues, localisés là où la langue est connue (le classifieur n'invente plus de question ; il ignore la langue). `_parse_result` tient enfin sa docstring (`ValueError` et non plus une `AttributeError` dépendant du provider), et `rejection_reason` ne convoie plus le message d'exception brut vers le prompt du nœud de réponse (règle #18). **Ce qui rendait tout cela invisible** : dix fichiers de test portaient un `skipif` sur `OPENAI_API_KEY` au niveau module — **219 fonctions de test n'avaient jamais tourné**, dont les 12 tests d'extraction de type ; réactivées avec une clé factice, **142 revenaient au rouge** (125 échecs, 17 erreurs) contre 92 vertes (écrites contre `AIMessage.content` avant la migration LangChain 1.x vers `.text`, `tracker.get_summary()` avant le DTO typé, un `llm` depuis scindé par famille de prompt). Huit suites sont réparées et tournent — le job CI « agents » passe de **978 à 1158 tests exécutés, 0 sauté** ; les deux fichiers qui appellent un vrai provider sont des **évals de qualité modèle** et portent désormais `pytest.mark.e2e`, ce qui rend leur exclusion **visible dans la commande CI** au lieu d'être un silence. La réanimation a exhumé trois défauts de plus : un **alias rétro-compatible** (`draft_executor._EXECUTOR_REGISTRY`) que 11 tests patchaient sans effet — ils exécutaient le **vrai** exécuteur d'e-mail ; la reformulation d'un EDIT tool-level **câblée sur un seul nom d'outil** (`get_contacts_tool`), si bien que pour tout autre outil le message qui **remplace le tour de l'utilisateur** perdait la valeur qu'il venait de corriger ; et le chunk d'erreur de reprise non localisé alors que la langue était sous la main. L'invariant que les tests de routeur sautés étaient censés protéger (le routeur écrit dans `routing_history`, jamais dans `messages`) est désormais prouvé **hermétiquement au niveau du nœud** — il tenait à la valeur de retour d'UNE fonction, pas au graphe complet. Non-récurrence : `test_no_env_skipped_suite_guard.py`, liste d'exemption décroissante portant le nombre de tests masqués — **vide** à ce jour.

---

### ADR-154: Frontière de phrase pour la synthèse vocale

**Statut**: ✅ IMPLEMENTED (2026-07-26)
**Fichier**: `docs/architecture/ADR-154-TTS-Sentence-Boundaries.md`

**Décision**: Les deux découpeurs de phrases du pipeline vocal — `_extract_sentences` (chemin direct) et `ProgressiveSentenceStreamer` (chemin progressif, le défaut) — traitaient **tout `.` comme une fin de phrase**, quel que soit ce qui suivait. Mesuré : « Il fait 3.5 degrés dehors. » était prononcé « il fait trois. » puis, dans un **chunk audio distinct**, « cinq degrés dehors » ; idem pour « 12.99 EUR », « Version 1.2.3 » et « exemple.fr ». Températures, prix, durées, versions, URL : tout ce que LIA énonce en chiffres était coupé en deux, sans qu'aucune exception ne soit levée ni aucun log écrit — le défaut n'est audible que par un humain qui écoute. Sur le chemin progressif, un second mécanisme aggravait le premier : le tampon grandit token par token, donc `"3."` est un état **transitoire normal**, et dispatcher dessus revient à parler avant d'avoir lu la suite. **Règle retenue** : un délimiteur ne ferme une phrase qu'en fin d'entrée ou **suivi d'une espace** — un point collé au caractère suivant appartient au token, pas à la prose. La queue sans espace finale est vidée par `close_input()`, qui existait déjà. Les deux implémentations sont épinglées par une **table de cas partagée** et une classe qui exige leur accord, le cas décisif étant joué **caractère par caractère** (seule façon de reproduire le tampon qui se termine sur un point). Limite assumée : `"Bonjour.Comment"` (délimiteur collé, faute du modèle) n'est plus découpé — prononcé correctement, premier chunk simplement plus tardif ; `"M. Dupont"` reste découpé, un lexique d'abréviations par langue ne se justifie pas.

---

### ADR-155: Aucune suite de tests ne se désactive sur une clé de provider absente

**Statut**: ✅ IMPLEMENTED (2026-07-26)
**Fichier**: `docs/architecture/ADR-155-No-Env-Skipped-Test-Suite.md`

**Décision**: Dix modules portaient `pytestmark = pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), …)` — variable absente du job CI `test-backend` comme du poste de qui n'en configure pas. Ces fichiers étaient donc **intégralement sautés depuis leur écriture**, et **rien ne le signalait** : un test sauté est vert, la couverture mesure les lignes atteintes et non les assertions exécutées, et la revue voit un fichier de tests et en conclut que la surface est protégée. Mesure du 2026-07-26 : **219 fonctions de test** (234 cas après paramétrage) n'avaient jamais tourné, sur le classifieur HITL, la reprise après approbation, l'exécuteur de brouillons, la construction du graphe LangGraph et le mixin de streaming — les points où une régression coûte le plus cher. Réactivées avec une clé factice, **142 revenaient au rouge** (125 échecs, 17 erreurs) contre 92 vertes : écrites contre `AIMessage.content` avant la migration LangChain 1.x vers `.text`, et contre un classifieur antérieur à la sortie structurée. Personne ne les avait cassées — elles avaient dérivé des mois sans contradicteur, et leur réparation a exhumé quatre défauts de production réels ([ADR-153](#adr-153-taxonomie-daction-hitl--classification-par-verbe-et-exemples-à-couverture-close), [ADR-154](#adr-154-frontière-de-phrase-pour-la-synthèse-vocale)). **Règle** : un module ne se désactive jamais sur une clé de provider ; on simule la forme de la réponse (cas quasi général), ou on marque le fichier `e2e`/`integration` pour que l'exclusion soit **lisible dans la commande CI**, ou on gate la seule fonction concernée. Portée par un balayage AST (`test_no_env_skipped_suite_guard.py`) sur six variables de credential, avec liste d'exemption **shrink-only et vide**, six auto-tests contre la pourriture du scan et un test refusant toute entrée périmée. Alternatives écartées : échouer sur tout test sauté (les sauts plateforme sont légitimes, le seuil serait relevé au premier faux positif) ; injecter une clé factice en CI (déplace le silence au lieu de le supprimer) ; documenter sans garde (la règle existait déjà dans `GUIDE_TESTING.md` et n'a pas empêché dix fichiers de dériver). **Coût assumé** : la liste d'exemption F006 passe de 11 à 49 entrées (catégorie `provider_eval`) — non parce qu'on crée de la dette, mais parce que F006 ne pouvait pas la voir : un test sauté sur credential reste *collecté et sélectionné* par le filtre `-m` du job, donc comptait comme couvert sans jamais s'exécuter.

---

### ADR-156: Suppression de neuf modules frontend orphelins

**Statut**: ✅ IMPLEMENTED (2026-07-26)
**Fichier**: `docs/architecture/ADR-156-Removal-Of-Nine-Orphan-Frontend-Modules.md`

**Décision**: Un scan **six vecteurs** (import statique, barrel `index.ts`, import dynamique `next/dynamic`, suites e2e, référence par chaîne, ré-export nommé) a isolé neuf modules à zéro consommateur applicatif : **1 561 lignes de code et 592 lignes de tests**. Deux d'entre eux étaient déjà **cassés** — `APIKeyConnectorForm` et `status-badge` interrogent des clés i18n (`settings.connectors.apiKey.*`, `status.blocked`) qui n'existent dans **aucune des six locales** : montés, ils afficheraient des identifiants bruts. Suppression du code, des tests, de deux entrées `.cc-baseline.json` et des clés i18n orphelines **clé par clé** (24 retirées, 24 conservées : `settings.location.*` et `chat.voice_mode.*` restent partagées avec `LocationSettings` et `VoiceModeBadge`, vivants). **Piège consigné** : `VoiceOverlay` avait un second fichier de tests sous un autre nom et dans un autre dossier — un scan qui apparie les tests par nom de module rate ce cas. **Conséquence couverture** : le code retiré étant mieux couvert que la moyenne (82 % de ses branches), son retrait a fait passer le seuil par répertoire `src/components/voice/**` sous son plancher. **Aucun seuil n'a été abaissé** : 15 tests comportementaux ont été ajoutés sur `VoiceModeBadge` (message d'erreur choisi selon la panne, annulations d'appui long, état d'initialisation du mot-clé, persistance serveur), et le **code inatteignable** du composant a été supprimé — il retourne `null` quand le mode vocal est désactivé, puis passait `enabled` (invariablement `true`) à quatre fonctions de rendu dont les branches `if (!enabled)` étaient structurellement mortes, ce qui expliquait l'essentiel des branches non couvertes. Les `default:` des `switch` sont conservés (l'état `idle` les rend atteignables). Bilan : statements 65.73 → **65.76 %**, lines 66.34 → **66.36 %**, ratchet CC abaissé (52 → 50 fonctions, 48 → 46 fichiers). Alternatives écartées : câbler `EmotionalStateIndicator` (livrerait une fonctionnalité non spécifiée sous couvert de nettoyage) ; abaisser le seuil du répertoire `voice` (interdit, et aurait masqué le code inatteignable) ; **conserver le code mort pour préserver la couverture** (raisonnement inversé : la métrique sert le code, jamais l'inverse). Prolonge [ADR-152](#adr-152-suppression-de-trois-hooks-frontend-orphelins).


---

### ADR-157: Corriger `brace-expansion` par un patch d'interop plutôt que par une simple montée de version

**Statut**: ✅ IMPLEMENTED (2026-07-27)
**Fichier**: `docs/architecture/ADR-157-Patched-Brace-Expansion.md`

**Décision**: Dependabot #192 (`GHSA-mh99-v99m-4gvg` / `CVE-2026-14257`, **high**) traînait, neutralisé dans `pnpm.auditConfig.ignoreGhsas`. Mesure : ce n'était **pas** un faux positif. `brace-expansion@2.1.2` est un **publish bâclé** — son `main` (`index.js`) porte l'ancien code **sans borne de longueur**, tandis que le build corrigé sous `dist/` est inatteignable (aucun champ `exports`) **et inexécutable** (il appelle `balanced_match_1.balanced(...)`, export nommé de `balanced-match@4`, alors que le paquet déclare `^1.0.0`). Le DoS se reproduit sur le point d'entrée réellement chargé : `'{a,b}'.repeat(1500)` → **`exit 134`** (SIGABRT, OOM V8 fatale et non rattrapable) sous un tas de 512 Mo. Mais `^5.0.8` — seule version corrigée, aucune publication sur 1.x–4.x après le 2026-07-23 — ne publie plus que l'export **nommé** `expand`, alors que `minimatch@3.1.5` fait `require('brace-expansion')(p)` et `minimatch@9.0.9` fait `__importDefault(...).default(p)` : l'override nu **tue ESLint** avant le premier fichier (`TypeError: expand is not a function`, `minimatch.js:271` — vérifié). Retenu : override `^5.0.8` **plus** un patch pnpm de **4 lignes de code** rétablissant l'interop (`module.exports = expand` + `.expand` conservé, `__esModule` volontairement non posé pour que `__importDefault` enveloppe la fonction). On ne porte **pas** à la main une correction de sécurité : le code qui borne est celui de l'amont, le patch ne touche que la surface d'export. `ignoreGhsas` est supprimé — garder la suppression masquerait le prochain avis. Preuves : DoS neutralisé (**1,15 s / 282 Mo**), **3 032 motifs** glob s'étendent à l'identique, sélection de fichiers ESLint inchangée (ratchet react-hooks **34/29**, chiffre identique avant/après), `pnpm audit` vert sans suppression, `task lint:frontend` vert. Piège traité : `pnpm install --frozen-lockfile` **échoue en dur** sans le répertoire (`ENOENT`, exit 127) — les deux Dockerfiles web copient désormais `patches/`. Non-récurrence : `brace-expansion-patch.guard.test.ts` (14 tests), prouvé rouge en retirant le shim. Alternatives écartées : laisser en l'état (le DoS est réel et reproductible), porter la borne à la main (nous rendrait propriétaires d'un correctif de sécurité sur du code que nous ne maintenons pas), forcer `minimatch@10` partout (casse les six consommateurs de la forme historique `require('minimatch')(path, pattern)`), router le `dist/` de 2.1.2 (build mort).

---

### ADR-158: La parité de clés ne mesure pas le contenu — cliquet sur la troncature des traductions

**Statut**: ✅ IMPLEMENTED (2026-07-27)
**Fichier**: `docs/architecture/ADR-158-Locale-Content-Truncation-Ratchet.md`

**Décision**: `validate_translations.py` compare les **ensembles de clés** des 6 locales et refuse toute clé manquante — c'est la seule garde i18n du dépôt, et elle est aveugle à ce qui se trouve **derrière** la clé. Une locale qui remplace une réponse de 500 caractères par un résumé de 150 la passe indéfiniment. Mesuré le 2026-07-27 : **23 chaînes sur 13 clés** portaient **31 à 58 %** du contenu servi par les autres locales latines (de 9, it 13, es 1). Deux n'étaient pas seulement plus courtes mais **fausses** : de/it envoyaient vers « Réglages > **Apparence** > Fuseau horaire » (Apparence est la section du thème, pas un parent — `settings/page.tsx:264-278`) et nommaient une **icône d'actualisation** pour un bouton qui est une **corbeille** (`Trash2`). Une troisième inexactitude était dans **les six langues** et dans `docs/knowledge/02_chat.md`, donc dans ce que LIA raconte d'elle-même : la FAQ annonçait que la réinitialisation supprime « l'historique », alors que `POST /conversations/me/reset` purge aussi **toutes les pièces jointes, images générées comprises**, les résumés de jetons, les checkpoints LangGraph et les contextes d'outils — le dialogue de confirmation disait déjà la vérité, la FAQ non. **52 chaînes réécrites** (10 clés × 6 langues) ; troncatures **23 → 5**. Cliquet posé : toute chaîne ≥ 150 caractères sous **60 % de la médiane** des locales latines est signalée, liste d'exemption **shrink-only** avec test anti-entrée-périmée et plafond à 5. `zh` est exclu de la comparaison (le chinois porte le même sens en ~⅓ des caractères ; un seuil par script serait une constante inventée). **Ce qui n'est PAS corrigé ici** : les 5 exemptions ne sont pas des troncatures mais des **permutations de section** — `tool_examples_services` est décalée entre `{en,fr}` et `{de,es,it}` sur q4→q14 (q11/q12 = Drive d'un côté, Gmail de l'autre), les deux jeux étant **complets** ; y coller la réponse de référence **détruirait** du contenu légitime. Le réalignement est un lot à part. Une mesure par empreinte invariante à la langue donne **126 entrées sur 223** divergentes — borne haute (elle signale aussi une perte d'emoji), consignée comme point de départ. Alternatives écartées : étendre `validate_translations.py` (mélange parité de clés et mesure de contenu sur le budget du hook) ; comparer à `en` seul (otage de sa propre verbosité) ; inclure `zh` avec un facteur d'échelle (constante inventée) ; traduire automatiquement les 126 divergences (produirait exactement la classe de défaut qu'on vient de corriger).

### ADR-159: Les quatre thèmes du journal doivent rester atteignables

**Statut**: ✅ IMPLEMENTED (2026-07-27)
**Fichier**: `docs/architecture/ADR-159-Journal-Theme-Reachability.md`

**Décision**: Mesuré le 2026-07-27, dev **et** prod : sur le compte principal, `self_reflection` et `ideas_analyses` totalisaient **0 entrée** depuis le 2026-06-02 (v1.20.19 / ADR-088), pendant que `learnings` en accumulait 11. Aucune suite ne rougissait — le défaut n'existait que dans la colonne `theme`. Deux mécanismes, tous deux mesurés. **(1) Création** : ADR-088 a remplacé l'arbre de classification par une barre d'entrée unique — « un signal EXPLICITE que tu pourrais citer » — que le modèle lit « dit avec des mots ». Or un `ideas_analyses` est par construction une abstraction inter-sujets *inférée*. La réécriture a de plus laissé `ideas_analyses` **seul thème sans illustration** et posé `learnings` en attracteur (« prefer it », « one good `learnings` note […] is a perfect output »). A/B à modèle, température et conversations constants : **0 entrée sur 24 exécutions** contre le prompt antérieur qui les produisait. L'ablation du persona donne le même résultat : la faute est dans le prompt principal. **(2) Survie** : la consolidation ordonnait de reclasser en `learnings` toute entrée `self_reflection` dont le `BECAUSE` cite un événement passé — alors que l'extraction **exige** qu'un `self_reflection` soit ancré dans une réaction utilisateur, donc porte exactement cette clause. Intersection vide. Contrôles : **6/6 reclassées** avec la clause, **5/6 intactes** sans. Preuve en prod : l'entrée `8bc35289`, créée par le code en `self_reflection`/L0, figure en base en `learnings`/L1. **(3)** Le seul producteur vivant restant (`feedback_hooks`, levier portrait) écrivait `self_reflection` en dur pour de simples retours utilisateurs. Retenu : classement **par SUJET** (échelle ordonnée de 4 questions, partagée par les deux prompts), ancrage à **trois voies** — (a) SAID citable, (b) SHOWN deux fois (ancrage plein, le plus fort quand les occurrences portent sur des sujets différents), (c) REACTED une seule réaction suffit — `self_reflection` exigeant **(c) et uniquement (c)**, interdit de surface durci (longueur/ton/ponctuation exclus de (b) **quelle que soit** la fréquence), et étiquetage des retours par sujet (`learnings` pour une réponse, `user_observations` pour le portrait). Résultat, 104 appels : rappel **1,00 sur les quatre thèmes**, volume 1,0 entrée/tour, **bruit négatif 0,00** (40/40 conversations sans matière restent silencieuses) — contre 1,00 / 0,58 / 0,00 / 0,00 et volume 0,65 avant. Non-récurrence : garde CI `test_theme_reachability.py` (parité + non-contradiction, sans LLM, falsifiée contre l'état antérieur) et instrument `scripts/measure_journal_themes.py` (13 scénarios dont **5 négatifs**, rendu via `prompt_builders.py` — le module du runtime, donc pas de dérive possible). Règle d'oracle posée : *un négatif n'est valide que si aucun ancrage (a)/(b)/(c) n'y existe* — deux négatifs initiaux la violaient et ont été **réparés** plutôt que de brider un comportement correct. Reste hors code : l'override en base fixe `journal_extraction` à `effort=none` alors que `LLM_DEFAULTS` dit `low` ; le prompt seul suffit à lever l'inatteignabilité (0,50 / 0,13 à bruit nul), `low` la transforme en fiabilité (1,00 / 1,00) pour **+114 jetons de sortie** par tour, entrée inchangée. **Contre-revue** : quatre défauts de plus, corrigés et couverts — jauge d'âge du portrait comptant des utilisateurs que l'ordonnanceur ne traitera jamais (un seul compte supprimé l'épinglait haut à vie, alerte inexploitable), prédicat d'éligibilité dupliqué entre l'ordonnanceur et la jauge (extrait en source unique), renvoi périmé du prompt de consolidation vers « Section 5 of the introspection prompt » devenue « INPUTS » depuis le 2026-06-02, et `GET /journals` renvoyant **500** sur un thème hors énumération (une ligne inattendue cassait toute la page ; désormais ignorée ET journalisée). Interface : le badge de groupe portait le total serveur au-dessus d'une liste paginée et filtrée — il compte maintenant les lignes rendues, et une liste tronquée le dit (`journals.listTruncated`, 6 locales). Alternatives écartées : revenir au prompt antérieur (mesuré à 2-3 entrées/tour, le bruit qu'ADR-088 avait supprimé), ne corriger qu'un des deux mécanismes (chacun suffit à vider un thème), régler par le seul effort (l'ancrage exclut `ideas_analyses` par construction), imposer une distribution cible (c'est la pression qu'ADR-088 a supprimée à raison — l'équilibre est un résultat, pas une consigne).

---

### ADR-160: Hygiène de la détection de skill, cumul avec le plan natif, et les deux plafonds qui rendaient une fonctionnalité impossible

**Statut**: ✅ IMPLEMENTED (2026-07-27)
**Fichier**: `docs/architecture/ADR-160-Skill-Detection-Hygiene-And-Native-Plan-Cumulation.md`

**Décision**: Six tentatives consécutives de « Crée une image réaliste d'un chat » en production, aucune image. Quatre défauts indépendants superposés, chacun suffisant. Les deux derniers tours portent **le même pivot anglais** (`Create a realistic image of a cat`) et divergent — la formulation française n'y est pour rien. **(1)** Le prompt demande en prose de « leave it null » et la sortie structurée tourne en `strict_mode: false` : le modèle écrit les quatre caractères `null`, chaîne non vide donc *truthy* pour chaque `if skill_name:` du pipeline. Mesuré sur **104 sondes** contre l'analyseur de production, dont 20/20 sur le vrai chemin `analyze_full` : **84 à 100 %** des analyses d'une simple demande d'image. Un `field_validator` Pydantic normalise désormais à la frontière de parsing (trim + sentinelles `null`/`none`/`nil`/`n/a`/`undefined`/`false`/`-`) — normaliser là plutôt qu'à chaque consommateur est ce qui supprime le log `chat_override_cleared_skill_name(skill_name="null")`, qui affirmait avoir effacé une skill jamais détectée. **(2)** `effective_skill_name` exige maintenant que le nom corresponde à une skill joignable par ce compte (`get_by_name_for_user`), **fail-open** si le cache n'est pas chargé (cache vide = démarrage, pas « aucune skill ») : le routeur donne à `detected_skill_name` une priorité absolue, et en 2026-07-21 `mcp_excalidraw` n'avait atterri sur le bon chemin que **par accident**, faute de skill homonyme. **(3)** Une skill *script-only* émettait un **plan vide** pour éviter les appels « parasites » du planificateur — choix délibéré dont le coût s'est vu : le plan vide a jeté `generate_image`, pourtant élu par la sélection sémantique à **score 1.0**, laissant au sous-agent quatre outils de skill. La stratégie cède désormais au planificateur LLM, et `response_node` (étape 3) active la skill depuis `query_intelligence` **indépendamment du plan** : les deux s'exécutent. Réversible par `SKILL_SCRIPT_ONLY_CUMULATES_NATIVE_PLAN=false`. **(4)** Latences mesurées sur `gpt-image-2` : `medium 1024x1536` = 47,2 s, `high 1024x1536` = **138,3 s** — au-dessus du plafond **générique** de 120 s, donc `quality=high` était impossible *à quelque réglage que ce soit* (relever le plancher dans `.env` ne pouvait rien y faire). Couple dédié 180 s / 300 s, comme navigateur, sous-agent et MCP-ReAct avant lui. **(5)** `skill_detection_retained_total{skill_name, primary_domain}` : le déclencheur du détournement n'a **jamais été reproduit** (0/104 sondes contre 4/6 tours de production, à état identique — `messages_count: 1, turn_id: 1` après purge du checkpoint), et les compteurs de suppression ne décrivaient que ce qui était jeté. Alternatives écartées : « l'outil natif à score élevé l'emporte » — vérification faite, `interactive-map` a la **même structure** que `skill-generator` (script-only, sans `plan_template`), le critère aurait supprimé la carte sur « montre-moi Paris » ; déclarer les domaines couverts en frontmatter (14 skills à renseigner, marqueur à inventer pour les méta-skills, skills utilisateur sans protection) ; retirer `skill-generator` de la détection automatique (une ligne, mais « crée-moi une compétence qui… » cesserait de la déclencher).

---

### ADR-161: Un flux SSE muet doit rendre la main — chien de garde client et reprise automatique

**Statut**: ✅ IMPLEMENTED (2026-07-27)
**Fichier**: `docs/architecture/ADR-161-SSE-Stall-Watchdog.md`

**Décision**: Une réponse visible sur ordinateur restait bloquée sur « Génération de la réponse… » sur mobile, indéfiniment — alors que les six flux se terminaient normalement côté serveur (`sse_stream_completed`) et que la réponse était persistée. Trois faits se verrouillaient : `readSseStream` faisait `await reader.read()` **sans délai de garde** (l'`AbortController` ne servait qu'au bouton stop), donc un onglet gelé par l'OS laisse une promesse jamais résolue ni rejetée ; `isTyping` dérive de `status === 'streaming'`, qui ne bouge plus ; et `handleVisibilityChange` — le gestionnaire qui recharge l'historique puis appelle `checkAndResumeActiveRun()` (ADR-117) — **sort immédiatement si `isTyping`**, son commentaire assumant que le garde « skips this when a stream is active ». La prémisse `isTyping` ⟺ flux vivant est fausse dès que la connexion meurt en silence : le garde censé protéger un flux actif verrouillait la seule issue. Preuve : **zéro** appel à `/runs/active` sur toute la période. Retenu : `readWithStallGuard` borne chaque lecture par `CHAT_SSE_STALL_TIMEOUT_MS` (90 s = **six battements manqués**, le serveur en émet un toutes les 15 s), annule le lecteur pour libérer la socket et lève une `StreamStalledError` typée (clé i18n dans les 6 langues) ; les minuteurs JS gelant *avec* l'onglet, l'expiration tombe au réveil — précisément le moment utile. Puis `useChat` quitte `streaming` **avant** d'appeler `checkAndResumeActiveRun()` (c'est `isTyping` qui bloque le gestionnaire), le run continuant côté serveur. Le garde `isTyping` est **conservé** : c'est sa prémisse qui est corrigée à la source. Un test vérifie qu'aucun minuteur ne survit à une fin normale — un minuteur fuité avorterait le tour **suivant**.

---

### ADR-162: L'indexation de la connaissance système a un seul écrivain, et son cache survit au déploiement

**Statut**: ✅ IMPLEMENTED (2026-07-27)
**Fichier**: `docs/architecture/ADR-162-System-Knowledge-Indexation-Single-Writer.md`

**Décision**: Deux classes d'erreur des journaux de production, une cause commune : rien ne coordonnait les quatre workers uvicorn au démarrage. `GoogleGenerativeAIError` = **19 minutes distinctes sur 8 jours** (70 lignes, 69 au démarrage), toujours le même `429 RESOURCE_EXHAUSTED` sur `embed_content_paid_tier_requests`, tombant **+17 à +21 s** après le début du boot sur les 4 workers en 1–3 s, et sur **11 démarrages sur 11** tracés en 4 jours — cette régularité d'horloge disqualifiait la course contre un consommateur externe. Volume calculé sur les données réelles : 4 × (713 textes du catalogue d'outils + 269 chunks FAQ) = **3 928 contenus en 72 requêtes par démarrage**, produits par deux mécanismes tous deux inutiles. **(1)** Le cache d'embeddings d'outils résolvait dans la couche inscriptible du conteneur, que `--force-recreate` détruit : **108 `cache_miss`, zéro `cache_hit` sur 27 démarrages**, pour une charge dont le `content_hash` était identique à celui du cache de dev vieux de 4 jours. **(2)** L'indexation FAQ lisait `content_hash` sans revendication, donc les 4 workers la passaient tous. Dégât invisible : l'entrelacement des 4 `delete`-puis-`insert` laissait **807 chunks pour 269 contenus distincts** et 3 documents, et comme `retrieval.py` trie par score puis tronque à 5 sans dédupliquer, le top-5 portait **2 réponses distinctes au lieu de 5**. Aggravant : l'exception s'échappait de `get_db_context`, qui classait 69 refus de quota en `database_session_error` ERREUR sous la couche base de données. Retenu : `FOR UPDATE SKIP LOCKED` sur la ligne du space (`SKIP LOCKED` et non l'attente — sérialiser 4 workers derrière ~20 s d'embedding ajouterait ce délai à chaque boot) avec `populate_existing=True`, sans quoi l'*identity map* rend le hash périmé et le perdant réindexe par-dessus le gagnant ; embeddings calculés **avant la première instruction destructrice**, si bien qu'un refus de quota ne supprime rien et ne tient aucun verrou sur `rag_chunks` ; péremption jugée sur le hash **et** `chunks == entrées parsées` **et** `documents == 1` (0,74 ms mesurés en prod) — sans ce comptage, le hash correct porté par les 807 chunks aurait figé le dégât pour de bon ; cache d'outils sur volume nommé avec chemin réglable ancré sur la racine applicative (le défaut résout vers le point de montage, donc aucune variable à poser) et écriture `tmp`+`os.replace` (persister sans atomicité transformerait un dégât invisible en corruption durable) ; retry borné en tentatives **et** en budget de temps partagé, classé sur le code de statut de la chaîne `__cause__` jamais sur le texte du message, exception d'origine relevée telle quelle. Résultat : **3 928 → 269 contenus, 72 → 10 requêtes** par démarrage, et le corpus dupliqué se répare au prochain boot. Alternatives écartées : verrou Redis (deux mécanismes à maintenir, dépendance au démarrage) ; `retry_with_backoff` maison (classe par type d'exception, pas de budget partagé, remplace l'erreur par `MaxRetriesExceededError` et perd le code 429) ; purge manuelle de la production (ne protège pas la récidive et suppose un geste d'opérateur).

---

### ADR-163: Un seul worker calcule les embeddings d'outils — revendication par fichier

**Statut**: ✅ IMPLEMENTED (2026-07-27)
**Fichier**: `docs/architecture/ADR-163-Tool-Embeddings-Cache-Claim.md`

**Décision**: ADR-162 a donné un volume au cache d'embeddings d'outils ; le premier démarrage sur ce volume neuf a montré ce que le volume seul ne règle pas. Les quatre workers uvicorn ont tous manqué le cache et embarqué **les mêmes 713 textes en même temps** (2 852 contenus). Le fournisseur a répondu un `429` de **capacité** — « Resource exhausted. Please try again later », lien Vertex AI, pas le quota nommé d'ADR-162 — et comme le sélecteur n'a aucun retry et que son échec remonte hors du lifespan, **deux workers sur quatre sont morts** (`Application startup failed. Exiting.` à 11:37:26 et 11:37:27). Ils ne se sont pas dégradés : uvicorn les a respawnés et leurs remplaçants ont relu le cache que les survivants venaient d'écrire (pids 51/54 à 5 min 21 contre 188/189 à 4 min 33) — ~48 s à deux workers. Ce rétablissement marche **par accident** : il exige qu'au moins un worker réussisse. Retenu : sur défaut de cache, une revendication exclusive par `os.open(lock, O_CREAT | O_EXCL)` — le système de fichiers désigne le gagnant, sans Redis ni base, entre processus qui ne partagent que le volume — et les autres attendent son résultat. Trois propriétés la rendent sûre : un détenteur mort ne bloque pas un démarrage (revendication trop vieille volée), un détenteur qui échoue passe la main (relâchement dans un `finally`, donc les tentatives se **sérialisent** à 713 textes au lieu de se paralléliser à 2 852), et perdre la coordination n'est jamais fatal (`miss_unclaimed` = comportement d'avant, visible sur un tableau de bord). Le seuil de péremption est **découplé** du délai d'attente à `max(délai, 30 s)` : les deux échouent en sens opposés, et une valeur unique rendait tout verrou instantanément périmé donc volé — la rafale même. Le délai par défaut de **40 s** est dérivé du budget de santé (`start_period 60 s + 3 × 30 s` = 150 s de tolérance, ~90 s de démarrage normal mesuré, donc ~60 s de budget) : un premier réglage à 90 s aurait mis le conteneur en `unhealthy` sur un démarrage. **Alternatives écartées** : rendre l'échec non fatal — première proposition, réfutée par les compteurs de production (4 réussites, 2 échecs, 4 workers finalement sains), car un worker survivant sans sélecteur saute le scoring sémantique **à vie** (`router_node_v3` garde sur `is_initialized()`, tous les outils du domaine partent sans classement) alors qu'un worker qui quitte revient pleinement fonctionnel ; `flock` ou `os.kill(pid, 0)` pour détecter un détenteur mort — plus précis mais exige une branche par plateforme, et les deux erreurs de l'heuristique mtime sont bornées par le comportement d'avant, donc n'inventent aucun mode de défaillance.

---

### ADR-164: Quels tours alimentent la mémoire, les intérêts et les journaux

**Statut**: ✅ IMPLEMENTED (2026-07-27)
**Fichier**: `docs/architecture/ADR-164-Post-Response-Extraction-Coverage.md`

**Décision**: Question posée : « les échanges simples ne sont-ils pas traités pour la mémoire, les intérêts et les journaux ? » Le chemin conversationnel nominal fonctionne — un test le prouvait déjà — et `user_msg_is_trivial` n'est pas un filtre « échange simple » (≤ 15 caractères **et** motif d'acquiescement). Mais **rien ne mesurait ces décisions** : chaque saut était journalisé en `debug` sans agrégat, et quatre défauts ont vécu dans cet angle mort. **D1** — `inbound_handler` n'envoyait ni `user_journals_enabled` ni `user_psyche_enabled`, donc les défauts de signature (`False`) s'appliquaient alors que les colonnes valent `true` en base : une conversation Telegram n'a **jamais** alimenté un journal. **D2** — un flux HITL avec brouillon n'extrayait **rien du tout** : le tour riche s'arrête sur `interrupt()` avant `response_node`, et le tour de confirmation sortait par le chemin rapide avant la planification ; le prompt ciblant le *dernier* message utilisateur, aucun tour ultérieur ne rattrapait. **D3** — au refus HITL, un `HumanMessage` **fabriqué** (bloc d'instructions localisé pour le LLM) devenait la cible de l'extraction : quatre appels LLM dépensés à analyser les consignes de l'assistant, avec risque de les persister. **D7** — l'heuristique s'appliquait au **nom de personne** que lui passe `person_tools`, or les motifs livrés contiennent `fine`, `cool`, `top`, `bien` : un contact ainsi nommé perdait tous ses souvenirs, sans message d'erreur. Retenu : un compteur `post_response_extraction_scheduled_total{kind, outcome}` posé sur les branches **existantes** (aucune ajoutée — le planificateur est à CC 41 et le cliquet est décroissant) ; `is_conversational` **obligatoire** sur `get_or_compute_embedding`, car le défaut silencieux est le mécanisme même de D7 ; cloisonnement livré **avant** l'extension des motifs aux six langues, l'inverse aurait aggravé le défaut (`vale`, `bene`, `gut` sont eux aussi des patronymes, délibérément exclus) ; un résolveur de préférences unique pour les deux points d'entrée des canaux, dont la duplication **était** la cause de D1 ; planification sur le chemin rapide brouillon, exacte parce que la reprise est un `Command(resume=...)` sans injection de message ; marquage des messages fabriqués par `additional_kwargs`, jamais par correspondance de texte (l'échafaudage existe en six langues), via un helper partagé qui **abaisse** les trois points chauds (mémoire 69 → 67, journal 76 → 74). **Attente calibrée** : le prompt mémoire exclut la logistique transitoire, qui constitue l'essentiel des tours HITL — le gain de D2 profite surtout aux journaux et aux intérêts. **Alternatives écartées** : extraire le libellé du refus (il n'existe qu'enchâssé dans l'échafaudage, le récupérer supposerait le parsing interdit) ; un défaut `is_conversational=True` ; une branche supplémentaire pour départager les gardes disjonctives (+1 CC sur un point chaud à 41, pour une information qu'un helper fournit sans coût).

---

### ADR-165: Modifier une skill, c'est la régénérer entièrement — et le confirmer dans l'outil

**Statut**: ✅ IMPLEMENTED (2026-07-27)
**Fichier**: `docs/architecture/ADR-165-Skill-Editing-By-Regeneration.md`

**Décision**: Question posée : « l'assistant peut créer des skills, mais pas en modifier une ». Le moteur d'écriture **existait déjà** — ADR-118 a fait du ré-import un upsert atomique, testé — mais trois verrous le rendaient inatteignable : le manifeste était **illisible** (`SKILL.md` hors de `all_resources`, et l'activation retire le frontmatter, donc `description`, `category`, `priority`, `plan_template`, `outputs` restaient invisibles) ; un remplacement **perdait** tout fichier non renvoyé, dont `assets/preview.png` que le chat ne peut pas transporter (**14/14** skills système en embarquent un) ; et le prompt ordonnait de **renommer** en cas de conflit, dirigeant l'assistant vers le doublon. Un quatrième fait a redéfini la confirmation : `_skill_needs_runner` renvoie `True` dès qu'une skill embarque un `scripts/`, et `skill-generator` embarque `validate_skill.py` — tout le dialogue tourne donc dans un `ReactSubAgentRunner` **à fil isolé**, qui ne connaît ni `draft` ni `interrupt`. Or `hitl_required` ne sert à rien (porte d'approbation passante) et le brouillon exige un appel depuis le graphe principal : **le HITL est inopérant là où le générateur s'exécute**. Retenu : régénération intégrale sous le même nom, jamais un patch (manifeste, scripts et références évoluent ensemble) ; **ré-import** plutôt que suppression puis recréation — résultat identique, mais « supprimer d'abord » exigerait d'exposer au modèle un outil de suppression (aucun n'existe ; l'endpoint fait `rmtree` sans sauvegarde) et ouvrirait une fenêtre où un échec perd la skill ; confirmation **en deux temps dans l'outil**, fermée par défaut, dont le premier appel refuse en énumérant ce qui serait ajouté, remplacé et **supprimé** — garantie **structurelle et non déclarative**, le modèle ne peut pas écraser en un appel même en ignorant son prompt ; report serveur des fichiers non transportables depuis la sauvegarde (chemin chat seul, jamais un fichier fourni, jamais un fichier texte — les retirer doit rester possible) ; intégrité du package **bloquante** (`outputs: [frame]` sans `scripts/`, ressource déclarée absente), là où le générateur ne validait que le texte du manifeste ; trois refus explicites — skill système (**sans proposer de fork**), skill d'autrui (indifférencié, sans révéler son existence), skill désactivée (le catalogue ne la montre pas, mais `get_by_name_for_user` ne filtre pas sur l'activité). **Arbitrage produit** : l'irréversibilité est **assumée**, aucune version précédente n'est conservée — la confirmation *est* le garde-fou, d'où un bilan qui énumère les pertes au lieu d'annoncer vaguement une modification. **Alternatives écartées** : fusion avec suppression explicite (`delete: [...]`) ; débloquer `SKILL.md` via `_discover_all_resources` (l'aurait ajouté au bloc `<skill_resources>` de **toutes** les activations, gonflant chaque prompt) ; un brouillon HITL (impossible depuis le sous-agent isolé).

### ADR-166: Ce qui mérite de devenir un centre d'intérêt ou un souvenir

**Statut**: ✅ IMPLEMENTED (2026-07-27)
**Fichier**: `docs/architecture/ADR-166-Extraction-Admission-Doctrine.md`

**Décision**: Question posée : « le prompt d'extraction des centres d'intérêt est trop permissif ». Il l'ordonnait : sa règle n°1 déclarait qu'une demande d'information (« search for X », « tell me about X ») **est** un centre d'intérêt, ce qui neutralisait la règle n°5 censée exiger un signe authentique — deux règles en conflit, tranchées du côté permissif par celle qui portait des exemples. Mesure de production : **7 des 10 intérêts créés en juillet ont été bloqués par l'utilisateur lui-même** (0 sur les 25 antérieurs), et le rejeu de 45 fenêtres de conversation réelles montrait une écriture sur **16 d'entre elles**, dont une proposant **19 suppressions — la totalité du profil actif**. Trois défauts structurels s'y ajoutaient, indépendants du prompt : la déduplication ne voyait que les intérêts **actifs** (chronologie prod : création 12:51, blocage utilisateur 19:14, **recréation 19:39** à 0,9821 de similarité — le blocage contourné en 25 minutes), les dormants étaient invisibles de la même façon (branche de réactivation inatteignable), et la fenêtre de dédup valait 20 lignes pour 19 intérêts actifs. Retenu : le prompt pose une autre question (**demander est une tâche, pas un goût**) et exige un **fondement nommé** parmi quatre (`stated_passion`, `own_practice`, `prior_knowledge`, `deep_dive`) plus la **citation** des mots qui le portent, `update` compris — sans quoi durcir `create` déplace le bruit ; la déduplication interroge **tous les statuts** et décide par statut (bloqué → rien, dormant → réactivation, actif → consolidation), fenêtre portée à 200 et distincte de la liste montrée au prompt ; un **plafond de suppressions** partagé par les deux extracteurs écarte **toutes** les suppressions d'un lot au-delà de 2, en conservant les actions non destructrices ; le plancher de confiance passe de 0,6 à **0,75** en `Settings`. **Mesures** : bruit sur négatifs 0,50 → **0,00** et rappel 0,75 → **1,00**, confirmés sur une batterie **held-out** (mêmes classes, sujets absents des prompts) ; sur les 45 fenêtres réelles, 16/45 écritures → **4/45**, aucune suppression. **Seuil de fusion inchangé à 0,89** : re-mesuré sur 16 couples réels, 0,83 fait jeu égal en nombre d'erreurs mais produit **2 fusions abusives** (android~ios, Caen~Strasbourg) là où 0,89 produit 2 doublons rattrapables. **Alternatives écartées** : palier « candidat » (migration + UI, sans perte de rappel mesurée à compenser) ; rejeter le lot entier au-dessus du plafond ; rendre `signal`/`evidence` opposables côté code dès maintenant (ils sont produits et ignorés par le parseur, ce qui rend le lot déployable sans toucher au code) ; baisser la température (inerte, les modèles utilisés déclarent `supports_temperature = false`).

---

### ADR-167: La provenance du contenu est portée par la donnée, pas par l'outil

**Statut**: ✅ IMPLEMENTED (2026-07-27)
**Fichier**: `docs/architecture/ADR-167-Content-Trust-Registry.md`

**Décision**: Une partie des données que LIA met dans ses prompts est **écrite par un tiers** : corps d'email, description d'invitation rédigée par son organisateur, page récupérée, résumé éditorial d'un lieu, résultat d'un serveur MCP. Le mécanisme existant (`wrap_external_content`) était appliqué **outil par outil** — et quatre l'avaient oublié (`perplexity`, `brave`, `mcp_react`, `emails`, ce dernier annonçant pourtant « Always returns FULL email content »). Surtout, il ne couvrait pas la bonne surface : le contenu atteint le LLM par `generate_data_for_filtering` (bloc `{data_for_filtering}` du prompt de réponse, **tous** les tours produisant des données, **les deux** modes, sans drapeau) et par `ReactToolWrapper._process_result` (bloc `Data:` de chaque `ToolMessage`). Preuve exécutée : un `content_summary` de navigateur est enveloppé sur le retour direct de `browser_tools` et **ressort nu** par le registre. **Retenu** : la classification porte sur le **type de donnée** (`RegistryItemType`), pas sur l'outil producteur — un nouvel outil émettant un item `EMAIL` est protégé sans toucher au module, et un nouveau type sans classification **refuse le démarrage** (doctrine ADR-085), résolution **fail-closed** sur type inconnu. Règle : EXTERNAL dès que le payload **peut** contenir du texte libre d'un tiers, l'ambiguïté se résolvant en EXTERNAL — ce qui classe `EVENT` (description de l'organisateur) et `PLACE` (avis, résumés éditoriaux) en EXTERNAL. Marquage `[EXT]` par ligne + **une** légende côté pipeline (ordre des lignes **préservé** : le prompt relit `[item_id]` pour `<relevant_ids>`, et la légende n'ouvre pas sur un crochet sous peine d'être lue comme un item d'id `EXT`), enveloppe `<external_content>` côté ReAct. Surveillance associée : 7 familles de motifs détectées **dans les 6 langues** (une détection anglaise seule est un contournement gratuit — l'attaquant écrit dans la langue de sa cible), comptées par `prompt_injection_patterns_total{surface,family}`, **sans jamais réécrire** le contenu. **Alternatives écartées** : liste d'outils de confiance (c'est le mécanisme qui a échoué) ; attribut sur `PermissionProfile` (`data_classification` est un axe de confidentialité, la provenance un axe d'intégrité — un rappel est INTERNAL et SENSITIVE, un article Wikipédia EXTERNAL et PUBLIC) ; n'envelopper qu'au-delà de 200 caractères (un objet d'email de 44 caractères est une injection complète : le seuil aurait été un trou de sécurité pour économiser des tokens) ; assainir le contenu (inefficace contre l'attaquant, destructeur pour un avis de sécurité transmis).

---

### ADR-168: Suppression de la recherche hybride mémoire, morte depuis v1.14.0

**Statut**: ✅ IMPLEMENTED (2026-07-27)
**Fichier**: `docs/architecture/ADR-168-Removal-Of-Dead-Hybrid-Memory-Search.md`

**Décision**: `infrastructure/store/semantic_store.py` (421 lignes) exposait une recherche hybride mémoire BM25 + pgvector. Recherche exhaustive sur `src/` **et** `tests/` : `search_hybrid` n'apparaissait que dans son propre module et dans le `__init__.py` qui le réexporte — **aucun appelant**, comme tous les autres symboles exportés. Le rapport de couverture le confirmait : **21 %**, 100 lignes sur 127 jamais atteintes alors que le module est importé au démarrage. Cause : la mémoire long terme a migré vers PostgreSQL/pgvector en v1.14.0 (`domains/memories/`), le chemin de recherche a suivi (multi-vecteurs contenu + mots-clés), le chemin hybride non ; `compute_emotional_state` a même été **dupliqué** côté vivant sans que l'original soit retiré. Trois conséquences : 421 lignes mortes importées à chaque boot, **quatre réglages orphelins** présents dans les deux `.env` plus deux métriques sans émetteur, et surtout **une affirmation fausse faite à l'utilisateur** — `app_identity_prompt.txt` annonçait « Long-term memory with hybrid search (BM25 + semantic) », reprise dans quatre documents et dans un témoin de debug « hybrid: ON/OFF » figé sur OFF. **Risque runtime nul et prouvé** : `MEMORY_HYBRID_ENABLED=false` figurait déjà dans `.env.example` et `.env.prod.example`, le chemin était inactif partout. Supprimés : le module, 4 champs `Settings` + 3 constantes, 8 lignes `.env`, 2 métriques, le champ du payload de debug et son affichage frontend, l'affirmation du prompt. **Conservés — ne pas confondre** : `bm25_index.py`, consommé par `domains/rag_spaces/retrieval.py` (la recherche hybride des **RAG Spaces** fonctionne, c'est celle des **mémoires** qui était morte), et `v3_tool_selector_hybrid_enabled`, homonyme sans rapport et bien actif. `HYBRID_SEARCH.md` conserve son corps sous un bandeau « historique » : le scoring et le calibrage y restent lisibles si le besoin revient — mais il repartira d'une mesure. **Alternatives écartées** : réactiver le chemin (il faudrait le rebrancher sur le modèle `Memory` actuel, le retester et le calibrer, pour un gain de rappel non mesuré) ; le garder « au cas où » (posture que la doctrine interdit) ; corriger seulement le prompt (supprime le mensonge en laissant la cause).

---

### ADR-169: Les blocs système du tour ReAct sont de l'état, pas des messages

**Statut**: ✅ IMPLEMENTED (2026-07-27)
**Fichier**: `docs/architecture/ADR-169-React-System-Blocks-Are-State.md`

**Décision**: `react_setup_node` ajoutait les blocs système du tour (prompt ReAct, contexte mémoire, portrait, catalogue de skills) à `state["messages"]`. Or le fenêtrage délègue à `get_windowed_messages(include_system=True)`, qui **hisse tous les `SystemMessage` en tête sans limite de fenêtre** : chaque tour ajoutait une copie du prompt, et toutes les copies passées repartaient au modèle à chaque appel. Trois conséquences mesurées : **coût** — `react_agent_prompt.txt` fait **840 tokens**, soit 2 520 dupliqués après 3 tours, 4 200 après 5, 8 400 après 10, à chaque appel LLM de chaque itération (bloc envoyé mesuré : 6 143 → 18 409 caractères entre 1 et 5 tours) ; **cache détruit** — un préfixe qui grossit à chaque tour ne peut jamais faire mouche, ce qui contredit la doctrine de `test_prompt_cache_hygiene.py` ; **incompatibilité Anthropic** — anciens blocs hissés + nouveaux ajoutés = messages système **non consécutifs**, et `langchain_anthropic._format_messages` lève `ValueError: Received multiple non-consecutive system messages.` dès le 2ᵉ tour ReAct (reproduit sur le code réel : positions `[0,1,5,6]`). Latent en pratique — `react_agent` vaut `qwen3.5-plus` par défaut — mais une bascule admin vers Claude casse le mode sans avertissement. **Retenu** : les blocs deviennent de l'**état** (`react_system_blocks`), recomposés **en tête** par `react_call_model_node` à chaque itération, plus un filtre de transition qui ne conserve de l'historique que les `SystemMessage` préfixés `COMPACTION_SUMMARY_MARKER`. **Mesuré sur 6 configurations** (1/3/5 tours × avec/sans compaction) : système contigu en tête, Anthropic accepte, compaction préservée, bloc **constant à ~3 150 caractères** (vs 18 409), préfixe **identique entre 1/3/5 tours** donc réellement cacheable, prompt transporté **exactement une fois**. **Alternative écartée et testée** : `include_system=False` sur l'historique corrigeait la contiguïté en une ligne mais **supprimait le résumé de compaction**, seul porteur de la mémoire conversationnelle après compression — le test l'a montré avant que le correctif ne soit écrit.

---

### ADR-170: Budget de calcul et garde anti-stagnation de la boucle ReAct

**Statut**: ✅ IMPLEMENTED (2026-07-27)
**Fichier**: `docs/architecture/ADR-170-React-Compute-Budget-And-Loop-Guard.md`

**Décision**: Deux défauts de la boucle ReAct. **(A) Le temps d'attente humain était facturé à la boucle** : le routage comparait `time.time() - react_start_time` au timeout (120 s), or `react_start_time` n'est remis à zéro **que par le routeur en début de tour**, et une reprise `Command(resume=…)` **ré-entre au nœud interrompu** — le routeur ne rejoue pas. Vérifié sur un graphe LangGraph réel : `router re-ran on resume? False`, **2,01 s d'horloge murale pour 0,0102 s de calcul**. Dès qu'une approbation dépassait 120 s, le tour repris était coupé au routage suivant : le dernier `AIMessage` portait ses `tool_calls` sans contenu, `final_message` revenait **vide**, le bypass ReAct ne se déclenchait pas et la réponse était **re-synthétisée par un second appel LLM** — travail perdu, coût doublé, et `react_agent_duration_seconds` incluait le temps de réflexion humain. **(B) Rien ne détectait la stagnation** : recherche exhaustive sur `src/` et `tests/` — aucun mécanisme ne remarquait le **même outil avec les mêmes arguments** répété en boucle. **Retenu** : le budget compte le temps de **calcul** (`react_elapsed_seconds`, chargé par le nœud d'appel), donc le temps d'interruption est structurellement exclu — un nœud interrompu ne retourne pas, ne charge rien ; `react_start_time` survit pour dériver `hitl_wait = mur − calcul`, transformant le défaut en indicateur produit. Plus une garde de non-progression (`utils/loop_guard.py`) : 4ᵉ appel identique refusé par un `ToolMessage` récupérable qui dit quoi faire d'autre, 5ᵉ termine le tour, seuils en `Settings` et dans les deux `.env`. Deux propriétés portent la conception — **empreinte HMAC avec le secret serveur** (seuls digest et compteur stockés, jamais le nom ni les arguments : la table vit dans PostgreSQL et les arguments portent les données de l'utilisateur ; clé partagée entre workers, sans quoi une reprise HITL sur un autre process réinitialiserait la garde) et **placement après le saut d'idempotence**, ce qui la rend replay-safe (les incréments d'une exécution interrompue sont écartés avec son travail partiel). Le dictionnaire attrape aussi l'oscillation A,B,A,B… qu'un compteur à créneau unique manquerait ; plafonné à 64 signatures. **Alternatives écartées** : repositionner `react_start_time` à la reprise (impossible — `interrupt()` lève, aucune mise à jour d'état n'est persistée) ; augmenter le timeout (déplace le seuil sans corriger la cause) ; registre en dict de module (viole la règle multi-worker) ; ne mémoriser que la dernière empreinte (rate l'oscillation).

---

### ADR-171: `position: sticky` était inopérant dans toute l'application

**Statut**: ✅ IMPLEMENTED (2026-07-28)
**Fichier**: `docs/architecture/ADR-171-Sticky-Positioning-Repair.md`

**Décision**: Le socle CSS déclarait `html, body { overflow-x: hidden }`. La spécification CSS Overflow impose qu'un seul axe non-`visible` fasse **calculer l'autre à `auto`** : `body` obtenait donc `overflow-y: auto` et devenait un **conteneur de défilement** — jamais défilé, puisque sa hauteur suit son contenu et que le défilement de page appartient au viewport. Tout descendant `position: sticky` s'ancrait sur ce scrollport immobile et ne collait jamais. **Mesuré dans Chrome, sur un élément réel** : le header de `/privacy` (`position: sticky; top: 0` confirmé par `getComputedStyle`) suit le document au pixel près — `top` vaut `−400` à `scrollY=400`, `−1200` à `1200`, `−2000` à `2000`. **Falsifié dans les deux sens** : `body` passé à `clip` ou à `visible` rétablit `overflow-y: visible`, le header se fixe à `0` et une barre `top: 64px` à `64`. Trois surfaces réclamaient ce comportement sans jamais l'obtenir (`dashboard/layout.tsx`, `privacy`, `terms`) ; le défaut est resté invisible faute de garde mesurant une position **pendant** un défilement, et la landing l'avait contourné sans le diagnostiquer via `position: fixed`. **Retenu** : `body { overflow-x: clip }` — `clip` clippe sans établir de scrollport ; `html` conserve `hidden`, propagé au viewport. Le repo employait déjà `clip` pour cette raison exacte sur les bulles de conversation. **Neutralité mesurée, pas supposée** : `scrollWidth − clientWidth` vaut **0 avant comme après** (y compris avec un enfant de 3 000 px injecté), donc les gardes de reflow gardent le même verdict ; les éléments `position: fixed` gardent un rectangle identique ; les `sticky` à défilement **interne** (bouton « revenir en bas » du chat, entête de l'overlay d'onboarding) ne sont pas concernés. **Dégradation gracieuse** : un moteur ignorant `clip` retombe sur `visible` et le clipping reste assuré par `html`. **Alternatives écartées** : positionner les barres en `fixed` comme la landing (contourne le symptôme, laisse trois headers cassés, impose de recalculer largeur et réservation d'espace à chaque redimensionnement) ; retirer `overflow-x` de `body` (fonctionne, mesuré, mais perd un filet de sécurité sans contrepartie) ; ne rien faire (la page Réglages ne peut pas offrir d'onglets persistants, et trois surfaces continuent de mentir sur leur propre comportement).

---

---

### ADR-172: Recherche de réglage — indexer ce qui existe, et le dire quand ce n'est pas là

**Statut**: ✅ IMPLEMENTED (2026-07-28)
**Fichier**: `docs/architecture/ADR-172-Settings-Quick-Search.md`

**Décision**: La table de liens profonds déclarait **17** jetons ; la page rend **43** `<SettingsSection>` (30 utilisateur, 13 administration). **Treize sections utilisateur en étaient absentes** — Langue, Apparence, Fuseau horaire, Police, Mode d'affichage, Authentification forte, Mes appareils, Exporter mes données, Génération d'images, Boucles ouvertes, MCP application, Panneau de debug, Export de consommation — donc un index limité aux 17 aurait rendu **zéro résultat** sur « thème », « langue » ou « mot de passe ». Les deux gardes existantes ne regardaient que le sens table → composant, et celle des onglets dérivait le nom du composant **du nom de fichier** : pour `theme-selector.tsx` l'aiguille `<theme-selector ` ne correspondait à rien et l'entrée passait **à vide** (falsifié dans les deux sens avant correction). **Retenu** : index des **30 sections utilisateur**, administration différée mais **énumérée** dans une liste exécutable et anti-rot (`settings-sections-coverage.guard.test.ts`), plus une garde qui refuse toute section rendue et non classée ; deux tables tenues par le TYPE (`Record<SettingsSectionToken, …>` — ajouter un jeton sans métadonnée ne compile pas). **Trois faits mesurés contraignent la conception** : Radix **démonte le panneau inactif** (rien ne peut observer l'autre onglet) ; **huit** sections peuvent ne rien rendre dont **six** indécidables à l'avance (404, liste vide, instance sans MFA, ou requête encore en vol) ; les locales mélangent **deux apostrophes** (212 courbes U+2019 en `fr`, 94 en `it`, 16 en `en`), ce qui rendait « application d’authentification » introuvable en tapant `d'authentification`. Les six indécidables **restent indexées** et la page, après navigation, attend (150 ms / 120 ms / 5 s) puis énonce l'**observation** — « ne s'affiche pas ici, peut-être pas disponible sur votre compte » — car affirmer l'indisponibilité serait un mensonge assuré sur connexion lente. Une porte ne reflète que la garde que le composant applique **vraiment** : `skills_enabled`, `channels_enabled`, `journals_enabled`, `rag_spaces_enabled` et `heartbeat_enabled` existent dans `/config` mais leurs composants ne les lisent pas, et filtrer dessus aurait caché des sections présentes à l'écran. Le focus n'appartient qu'au chemin recherche (un lien, un retour OAuth ou le raccourci portrait ne volent pas le curseur) et le défilement honore enfin `prefers-reduced-motion` sur les deux chemins. **Mesuré dans Chromium** : le champ rejoint la barre collante, qui passe de 117 à **161 px** (y 64 → 161), donc `scroll-mt-32` → `scroll-mt-44` (176 px, section atterrissant à 176, 15 px d'air) ; la garde e2e mesure désormais le **conteneur collant** et non `[role="tablist"]`, dont le bas n'est plus celui du chrome. `normalizeSearchText` replie apostrophes et espaces insécables **un point de code pour un point de code** — contrainte dure, `findNormalizedMatches` reconstituant les positions d'origine en sommant les longueurs par caractère — ce pourquoi le repli de ligatures (`ß`→`ss`) est écarté et traité en donnée. **Alternatives écartées** : s'en tenir aux 17 (zéro résultat sur les requêtes les plus probables) ; `forceMount` sur les panneaux (monterait trente sections et leurs requêtes à chaque visite pour lever une incertitude déjà traitée à l'arrivée) ; filtrer les six `runtime` au jugé (échange un cul-de-sac visible contre un faux négatif invisible) ; placer le champ hors de la barre collante (le rend inatteignable dès que la page défile, ce que la barre venait de corriger).

---

### ADR-173 : `?draft=` préremplit, `?intent=` exécute — deux verbes, deux liens

**Statut**: ✅ IMPLEMENTED (2026-07-29)
**Fichier**: `docs/architecture/ADR-173-Card-Intent-Autosend.md`

**Décision**: QW-24 ajoute aux items des cartes du briefing des **boutons d'action nommés** (« Résumer », « Terminé », « Itinéraire »…) dont le libellé EST la demande — le clic est l'acte délibéré, forcer un second Entrée n'ajoutait rien. **Retenu** : un second paramètre `?intent=` **disjoint** de `?draft=` (contrat A4 intact : préremplir, ne jamais envoyer) ; l'intent est envoyé une seule fois par **le chemin exact d'un message tapé** (`sendMessageFromPresent`, règle du retry W3), consommé via ref et retiré de l'URL **avant** l'envoi (rechargement/retour ne renvoient jamais). Garde-fous : quota bloqué → brouillon persistant + toast, jamais envoyé de force ; API indisponible ou streaming en cours → l'effet attend le changement d'état ; l'approbation **hérite exactement du pipeline chat** (les écritures draft-gated présentent leur carte HITL ; `complete_task` s'exécute directement car réversible — comportement du chat, pas une exception du lien). Une action exigeant les mots de l'utilisateur reste un `?draft=` (« Poser une question sur ce document »). Chips **frères** du bouton principal (bouton imbriqué = HTML invalide), nom accessible = phrase d'intent complète. **Alternatives écartées** : `&send=1` sur `?draft=` (rend le contrat A4 conditionnel) ; endpoints REST directs par action (duplique HITL et gestion d'erreurs hors du pipeline qui les possède) ; auto-envoi sans repli quota (un clic honnête devenu 429).

---

### ADR-174 : Le débriefing d'appel est persisté — extension consciente de D-8

**Statut**: ✅ IMPLEMENTED (2026-07-29)
**Fichier**: `docs/architecture/ADR-174-Call-Debrief-Persistence.md`

**Décision**: T01 demande un débriefing d'appel exploitable (engagements, tâches et rappels de suivi, brouillon, points à vérifier). Ces éléments sont un produit de **notre synthèse LLM** — c'est `ReturnProposal` qui s'étend (champs additifs, la forme v1 valide toujours), **pas** `StructuredCallData` (extraction fournisseur). **Retenu** : colonne `phone_calls.debrief` (JSONB nullable, migration e5f6a7b8c9d0) ; un débriefing vide persiste comme **NULL** (absence, pas du bruit — aussi le chemin du repli synthèse) ; **même rétention que `summary`** (le reaper D-8 l'efface dans le même UPDATE) ; il voyage aussi dans les metadata de notification (`proactive_phone_call`) pour la carte chat. Composant unique `CallDebrief`, deux postures : informatif en bulle chat, actionnable dans « Appels récents » (tâches/rappels en `?intent=` ADR-173, brouillon en `?draft=` — un message à un tiers exige la relecture de l'utilisateur). **Alternatives écartées** : débriefing seulement dans la notification (perdu à la première manquée — la leçon A6 réapprise) ; étendre `structured_data` (mélange extraction fournisseur / synthèse maison) ; étendre la collecte ElevenLabs (délègue au fournisseur un travail que notre synthèse fait mieux, transcript complet sous les yeux).

---

### ADR-175 : Studio de routines — déclencheurs conditionnels au tick cron

**Statut**: ✅ IMPLEMENTED (2026-07-29)
**Fichier**: `docs/architecture/ADR-175-Routine-Condition-Triggers.md`

**Décision**: Les actions planifiées (ADR-140) ne se déclenchaient que sur l'horloge. N-07 ajoute des routines réactives. **Retenu — phase 1 « horaire OU condition », l'horloge reste le cron pour les deux** : une routine CONDITION évalue sa condition à chaque tick et ne s'exécute que si elle est remplie ET que le fait est nouveau (dédup par empreinte). Modèle : `trigger_kind`, `condition_config` (JSONB), `condition_state` (ledger), `requires_approval` (migration f6a7b8c9d0e1 ; lignes existantes → `time`/false, zéro changement de comportement). Évaluateurs dans `infrastructure/scheduler/condition_evaluators.py` (PAS le domaine : l'évaluation lit via les fetchers briefing dont les caches Redis bornent le coût API, et `briefing.fetchers` importe déjà scheduled_actions — un import domaine→domaine fermerait un cycle) ; le domaine possède le VOCABULAIRE + le contrat API, l'infra l'évaluation ; **assert de complétude au boot** (ADR-085). Dédup : empreinte du FAIT, ledger écrit seulement à une exécution réelle (un échec réessaie). « Proposer d'abord » : le tick notifie avec un lien `?intent=` (ADR-173) — le run appartient au chat + HITL, jamais compté comme exécution. Chat (ADR-140) inchangé : crée des routines `time` (champs N-07 additifs à défaut time → même objet). Les évaluateurs ne lèvent jamais (panne = « non remplie », retry au tick suivant ; type inconnu = « non remplie » loggée). **Alternatives écartées** : event-driven réel (Gmail watch/PubSub — souscriptions par utilisateur/fournisseur, disproportionné) ; évaluateurs dans le domaine (ferme le cycle) ; un flag `SCHEDULED_ACTIONS_ENABLED` (n'existe pas, piège documenté) ; exécuter sans mode proposer-d'abord (une routine réactive à conséquence externe qui agit sans accord).

---

### ADR-176 : CRM personnel — agrégation en lecture seule, identité assumée best-effort

**Statut**: ✅ IMPLEMENTED (2026-07-29)
**Fichier**: `docs/architecture/ADR-176-Personal-CRM-Relations.md`

**Décision**: N-09 capitalise sur ce que LIA sait des personnes. Le point dur est la résolution d'identité (rien ne relie « Gérard Dupont » d'un open loop au « gérard dupont » d'un appel). **Retenu — v1 agrégation lecture seule sur le pattern `domains/briefing`** : nouveau domaine `relations/` (pas de LangGraph, **pas de nouvelle table** ; requêtes indexées séquentielles sur une session, pas de `gather` → pas de risque de session partagée), deux GET (`/relations`, `/relations/{name}`), aucune écriture (agir = `?intent=` chat, ADR-173). Identité **best-effort énoncée** : repli NFKD+casefold → `EXACT` si toutes les orthographes brutes coïncident, sinon `NORMALIZED` (bandeau d'avertissement affiché). Pas de cache v1 (2 requêtes indexées, la fraîcheur prime, aucun coût fournisseur). Anniversaires/contacts = **phase 2 documentée** (exige le connecteur contacts + surface d'identité) — champ retiré des schémas pour ne pas laisser de donnée morte. Accès via l'en-tête de la carte For-you + la recherche des réglages, PAS une 6ᵉ nav (R01 clippe déjà à 5). **Alternatives écartées** : table CRM + identité forte (référentiel de contacts = projet en soi, YAGNI avant preuve d'usage) ; 6ᵉ entrée nav (clip d'en-tête) ; cache overview (masque un engagement qu'on vient de clore) ; matching mémoire sémantique (surprend sans budget d'explication).

---

### ADR-177 : Mode HTML enrichi — vocabulaire de composants et extension du schéma de sanitisation

**Statut**: ✅ IMPLEMENTED (2026-07-29)
**Fichier**: `docs/architecture/ADR-177-Rich-HTML-Response-Components.md`

**Décision**: La directive du mode `html` n'exploitait qu'une fraction des capacités en place (callouts success/error stylés mais non documentés ; `details`/`dl`/`kbd` autorisés mais jamais proposés ; aucune classe `language-*` donc jamais de Prism). **Retenu — enrichissement purement déclaratif (prompt + CSS + allowlist), aucun nouveau chemin de code** : la directive documente 7 composants stylés `.lia-response` (callouts ×4 + titre, chips + icônes Material Symbols, `details.lia-collapsible`, `dl.lia-kv`, `div.lia-columns`, `ol.lia-steps`, `div.lia-stats`, code `language-*` → CodeBlock) + accents `mark`/`kbd`/`abbr`, avec règle de sobriété (2-3 composants max) et budget ≤96 lignes. Schéma de sanitisation étendu de **6 tags inertes** (`mark`, `caption`, `abbr`, `time`, `figure`, `figcaption`) — rien de scriptable, ordre des plugins et interdits (`script`/`iframe`/`form`/handlers) inchangés, pinné dans les deux sens. **Garde de sync directive↔CSS** (`test_html_directive_css_sync.py`) : une classe `lia-*` citée mais non stylée fait échouer CI (doctrine ADR-085 appliquée au couple prompt/CSS). Overrides `ol`/`ul` de MarkdownContent préservent désormais les classes `lia-*` (contrat `p`/`a`). Aplatissement client partagé `html-plain-text.ts` (miroir de `html_to_text` backend) → copie double-flavor, partage natif, export `.md` ; ligatures d'icônes exclues du surlignage de recherche (bug latent). Gate TTS (`route_to == "planner"`) inchangé. **Limite connue mesurée** : sur tour skill, le LLM de synthèse ignore parfois la directive (pré-existant, non aggravé). **Alternatives écartées** : composants React interceptés (complexité streaming/a11y — différé) ; ne pas étendre le schéma (dégradation en texte nu pour un coût d'extension quasi nul) ; `<progress>`/`<meter>` natifs (stylage cross-browser pénible, YAGNI).

---

### ADR-178 : Dashboard produit natif — outcomes durables, gauges DB-backed, datasource PostgreSQL en lecture seule

**Statut**: ✅ IMPLEMENTED (2026-07-29) — phases 0-4 ; alertes préparées non montées (baseline 4 semaines)
**Fichier**: `docs/architecture/ADR-178-Product-Value-Dashboard.md`

**Décision**: LIA n'avait aucune vue produit (25 dashboards techniques, zéro réponse à « combien d'utilisateurs obtiennent un résultat utile, à quel coût, reviennent-ils ? »). **Retenu — architecture 100 % native Grafana + Prometheus + PostgreSQL, aucune plateforme analytics tierce** (Langfuse dev-only, non référencé). PostgreSQL = vérité produit durable : contexte borné `domains/product/` (`product_outcomes` 1 ligne/`result_id`, états E1/E2/E3 **mutables** — un E2 exige 24 h sans correction/réversion — donc **North Star jamais calculée depuis Prometheus**, un Counter ne se dé-compte pas ; `product_events` inclus en v1 sur arbitrage). Prometheus = transport borné : compteurs + **gauges DB-backed** (pattern `lifetime_metrics.py`), histogrammes ≤ 2 labels (le PDF v1.1 aurait produit ~23 k séries × 26 domaines sur RPi5), label `refresh_job` (jamais `job`, réservé au scrape), coûts **EUR uniquement** (source `message_token_summary.total_cost_eur`). Dashboard `26-product-value` (convention `<numero>-<slug>`, titre anglais) : 42 panels en trois états — LIVE (séries existantes), PRE-WIRED (futur nom `product_*`, rend « n/a » puis s'allume sans retouche JSON), TEXT (source pas encore née). Datasource `postgres-product-readonly` provisionnée env-interpolée ; rôle `grafana_product_reader` créé par script + task (jamais un mot de passe en migration), `GRANT SELECT` sur les seules surfaces produit + `statement_timeout`. Purge GDPR câblée (`user_data_map` + `account_deletion_service`), rétention brute 180 j (`PRODUCT_OUTCOMES_RETENTION_DAYS`), `device_class` **dérivé** de l'`os_family` de session (ADR-144, aucune capture nouvelle), écritures hors chemin SSE, alertes produit différées après 4 semaines de baseline (hygiène ADR-119). **Alternatives écartées** : plateforme tierce (philosophie locale-first, PII) ; North Star depuis les compteurs (états mutables) ; `MATERIALIZED VIEW` (refresh verrouillant) ; capture client de `device_class` (contraire ADR-144) ; uid `lia-product-value` (viole la convention).

### ADR-179 : Sortie structurée — chokepoint unique gardé par AST et plancher de budget de complétion sous raisonnement

**Statut**: ✅ IMPLEMENTED (2026-07-29)
**Fichier**: `docs/architecture/ADR-179-Structured-Output-Chokepoint-And-Thinking-Budget-Floor.md`

**Décision**: Incident prod 2026-07-29 — chaque retour d'appel téléphonique livré en anglais sans débrief : `return_synthesis.py` appelait `llm.with_structured_output` **en direct** (seul site du dépôt), et l'override admin ayant basculé `telephony_synthesis` sur deepseek-v4-flash effort `high`, le `tool_choice` forcé prenait un 400 (« Thinking mode does not support this tool_choice ») → fallback = résumé vendor brut. Second défaut emboîté : `max_tokens=600` (calibré avant le débrief ADR-174) entièrement consommé par le raisonnement même via le fallback JSON. **Retenu** : (1) le chokepoint `infrastructure/llm/structured_output.py` est le **seul** chemin de sortie structurée — garde AST repo-wide (`test_no_direct_structured_output_guard.py`, allowlist réduite au chokepoint, self-checks anti-rot) ; (2) `TokenCaptureHandler` partagé (`infrastructure/llm/token_capture.py`) consolidant les deux copies privées divergentes (heartbeat/open-loops), deux surfaces d'usage lues sans double comptage ; (3) recalibration `telephony_synthesis` (5000 tokens / 60 s, parité heartbeat_decision) ; (4) **plancher** `LLM_THINKING_MAX_TOKENS_FLOOR` (défaut 4000) : config à raisonnement « lourd » (prédicat par FORME : enum hors none/off/minimal/low, toggle Qwen activé, budget Gemini ≠ 0) et `max_tokens` **effectif** (fusion `merge_config` identique au runtime) sous le plancher → 422 structurée `thinking_budget_below_floor` au save admin ET au boot ; le frontend surface désormais les 422 structurées (toast localisé ×6 interpolé, `msg` en description sinon). **Alternatives écartées** : avertir sans bloquer (l'incident a prouvé le signal non bloquant invisible) ; plancher incluant minimal/low (aurait interdit 10 défauts légitimes) ; matrice de lourdeur par provider (divergerait des builders) ; relèvement silencieux du `max_tokens` (mutation cachée du choix admin).

### ADR-180 : Connexions entre utilisateurs — découverte opt-in, relais assistant-à-assistant, partages lecture seule

**Statut**: ✅ IMPLEMENTED (2026-07-29) — lots 1-6, flag `PEERS_ENABLED` off par défaut
**Fichier**: `docs/architecture/ADR-180-Peer-Connections.md`

**Décision**: Les utilisateurs d'une instance ne pouvaient pas interagir. **Retenu — contexte borné `domains/peers/`** : une ligne par paire (UNIQUE+CHECK, doublons/auto-connexion irreprésentables, transitions claim-once conditionnelles), blocs directionnels silencieux, partages par connexion (absence=non partagé, deux directions visibles), registre de livraison au contenu purgé après remise, audit immuable consultable par le propriétaire. Découverte opt-in par **nom exact plié** (chokepoint hoisté du CRM), rate-limitée, homonymes discriminés par fragment d'email masqué ; **neutralité octet-à-octet** inconnu==bloqué==cooldown (testée en égalité de payload). Relais de message : draft PEER_MESSAGE = confirmation (doctrine FN-1, couvre skills sans HITL), livraison par sweep SKIP LOCKED dans `infrastructure/scheduler/` (cycle agents↔peers cassé par relocalisation — attrapé par la garde F009), génération **un appel LLM** avec personnalité+mémoire+psyché+portrait du DESTINATAIRE (`build_psychological_profile` délibéré — preuve d'ouverture Lot 4 : voie pipeline incompatible avec l'imputation émetteur), **tokens à l'émetteur** (oracles testés), message encadré données-jamais-instructions (ADR-167/170). Lecture croisée calendrier (libre/occupé ou +titres) et tâches (titres) : partage revérifié à l'exécution, chaque lecture journalisée. Agent `peer_agent` + domaine `peer` via **nouveaux points d'extension** `program_domain_configs` (taxonomy gelée délègue et rétrécit). Frontend : section « Connexions » auto-gatée sur `/config`, partages bilatéraux, codes `peers_*` = clés i18n épinglées des deux côtés, e2e complet + axe + mobile. RGPD : purge bilatérale explicite (CASCADE users ne tire jamais), export `_TWO_SIDED` avec scopes unilatéraux anti-fuite (blocs par bloqueur seul). **Alternatives écartées** : étendre le CRM relations (contrat violé) ; pipeline complet destinataire (imputation impossible) ; recherche par préfixe (énumération) ; notification de blocage (harcèlement) ; Enum natif (piège majuscules — String+str-Enum a permis `delivering` sans migration).

### ADR-181 : Identité « LIA Cosmos » — re-skin scopé de tout l'espace public, chorégraphies pilotées par le scroll

**Statut**: ✅ IMPLEMENTED (2026-07-30) — bascule complète (landing + 10 pages publiques), previews supprimés
**Fichier**: `docs/architecture/ADR-181-LIA-Cosmos-Public-Identity.md`

**Décision**: La landing éditoriale n'avait ni identité visuelle forte ni lien entre défilement et narration. **Retenu — re-skin par SCOPE CSS, pas par réécriture** : une classe `.cosmos` redéfinit les variables `--color-*` du design system → les sections réelles se rhabillent **sans une seule édition de composant de contenu** (les surfaces portalées Radix échappent au scope, voulu) ; sous-scope `cosmos-calm` pour les sept pages de lecture (fond atténué, cartes opaques, aucune chorégraphie). Primitives maison **sans dépendance nouvelle** (`components/landing/cosmic/`) : boucle rAF passive unique, driver `ScrollScrub` écrivant `--sp` par section (défaut CSS 1 → rendu complet sans JS/SEO, reduced-motion épingle 1), `PinnedScene` sticky (`--p`, fallback vertical mobile), `Planetarium` (8 fonctionnalités en orbite autour du vrai mockup), mots fantômes masqués, `CosmosDarkFirst` (script pre-paint : pas de préférence → sombre, le toggle gagne). Les scènes des six chapitres sont scrubbées **en réutilisant leurs délais inline existants** (copiés dans `--d`, fenêtres proportionnelles) — ordre original préservé, réversible. **Contraste AA divergent par thème** (sombre = bleu vif sous texte encre ≈5,5:1 ; clair = bleu profond `#2c56c4` sous blanc ≈6,5:1) : le jeton unique blanc-sur-bleu-vif mesurait 3,2:1, non conforme. Registre **tutoyé** sur fr/de/es (~1 150 chaînes, audits à zéro résidu ; it l'était déjà) — l'interlocuteur d'un exemple téléphonique reste vouvoyé. Gardes : pin mesuré **pendant** le scroll (ADR-171), overflow 375/320 sur 6 locales pendant tout le cycle d'animation (le garde distingue désormais débordement de LAYOUT — bloquant — de la projection 3D transitoire et de la décoration `aria-hidden`+`pointer-events:none`), balayage axe des deux thèmes sur `/`, `/faq`, `/demo`, `/more`. **Alternatives écartées** : bibliothèque d'animation (zéro dépendance arbitré) ; duplication des sections pour les rhabiller (double maintenance ×6 langues) ; IntersectionObserver one-shot (non réversible, conflit avec les révélations legacy) ; halos en pseudo-élément `z-index:-1` (cassés sous tout contexte d'empilement → box-shadow) ; garder deux identités en parallèle (code mort).

### ADR-182 : Conscience des connexions au routage, aveu d'échec fidèle, visibilité persistante des connecteurs cassés

**Statut**: ✅ IMPLEMENTED (2026-07-30)
**Fichier**: `docs/architecture/ADR-182-Peer-Routing-Awareness-And-Honest-Failure.md`

**Décision**: « Jerome G est-il disponible demain à 10h ? » répondait « aucun service n'est configuré » alors que connexion, partage et connecteur du peer étaient sains. Trois défauts emboîtés, tous prouvés sur logs+DB dev. **D1 — routage `peer` = tirage au sort** : la phrase identique a routé `peer` à 13:23 et `event`+`contact` à 13:25/13:26/13:34, ces trois plans visant l'agenda et le carnet du DEMANDEUR puis mourant sur des scopes absents ; cause racine = rien n'apprend à l'analyzer que ce nom est un autre UTILISATEUR. **Retenu** : (1) *conscience* — les connexions acceptées sont injectées dans un bloc `## CONNECTED USERS` du prompt versionné avec la règle de désambiguïsation (une requête indexée par tour, gatée par flag) ; (2) *déterminisme* — `peer` **AJOUTÉ** (jamais substitué : « suis-je libre pour voir X » a besoin des deux) quand un peer nommé côtoie un domaine confusable `event|task|contact`, rappel privilégié sur la précision mais borné par cette porte, accents pliés (mêmes sémantiques `fold_name` que les outils), frontières de mots, jetons < 3 caractères ignorés, corrections comptées et loggées **sans les noms** (PII) ; (3) défaut adjacent : le domaine `peer` n'était gaté par `peers_enabled` dans **aucun** chokepoint de disponibilité alors que le flag gate déjà routeur/manifests/outils → table `FLAG_GATED_DOMAINS` remplaçant trois `if` triplés. **D1bis — la donnée est lue puis jetée** : routage corrigé, `peer_availability_read slots=6`… et la réponse restait fausse, mais **exacte** (« les données actuelles ne contiennent aucun détail sur ses créneaux »). `UnifiedToolOutput` a trois destinataires et un seul est la réponse : `registry_updates` → frontend, `structured_data` → Jinja inter-étapes, `message` (= `summary_for_llm`) → le modèle qui rédige. Les outils peer mettaient la charge utile dans `structured_data` seul et laissaient `message` à une phrase *sur* les créneaux (`data_registry_items: 0`). **Retenu** : `agents/peer/summaries.py` rend les créneaux DANS `message`, heures converties dans le fuseau du **demandeur**, titres seulement au niveau `details`, cas vide explicite (« NOTHING is busy → answer they appear free », sinon le modèle dit « je ne sais pas »), sortie bornée, provenance ADR-167/170 conservée ; canal vérifié verbatim (`_extract_action_success_messages` ne tronque pas). **Sous-défaut fonctionnel** : les six créneaux mesurés étaient des anniversaires **journée entière**, qui ne bloquent pas 10 h — les injecter sans les qualifier aurait remplacé « je ne sais pas » par « occupé toute la journée » ; ils sont listés à part et décrits, sans verdict inféré à la place du modèle. **D1ter — on lisait le mauvais calendrier** : les lectures peer étaient câblées en dur sur `calendar_id="primary"` / `task_list_id="@default"` alors qu'une préférence `default_calendar_name` / `default_task_list_name` existe et que **tous** les autres chemins la respectent (briefing, calendar_tools ×5, tasks_tools). Mesuré : la préférence du peer vaut `Famille`, son `primary` (« Jgouvier ») ne contenait que des anniversaires, et son rdv de 10 h vivait dans `Famille` → « aucun créneau occupé » alors qu'il était pris (**libre-alors-qu'occupé**, la forme la plus coûteuse de réponse fausse). **Retenu** : `connectors/preferences/owner_defaults.py`, un helper unique (le bloc était écrit 7 fois) avec `owner_id` en **paramètre explicite** — une lecture peer tourne sous le runtime du DEMANDEUR, donc résoudre l'identité ambiante lirait la préférence de la mauvaise personne et paraîtrait correct dans tout test mono-utilisateur (un test épingle l'argument) ; toute défaillance retombe sur `primary`/`@default`. **D2 — le validateur refuse, la réponse invente** : verdict loggé puis abandonné, le LLM comblait le silence (« nous frôlons le bégaiement technologique », 3 tours) ; **retenu** : `plan_blockers.py` + directive versionnée `response_directive_plan_blocked.txt` en bloc système, interdisant nommément de généraliser (« nothing is configured »), de blâmer l'utilisateur, ou de faire passer une capacité manquante du demandeur pour une réponse sur la donnée d'un tiers — **généralisé à tout `ToolErrorCode`** (le défaut appartient au silence, pas au code), un refus explicite de l'utilisateur gardant la priorité. **D3 — 5 connecteurs cassés, 0 notification sur 35 runs** : le cooldown 12 h était correct mais **indiscernable d'un notifieur cassé** (deux `return False` muets ; dater la cause a demandé de lire 4 bases Redis et de faire l'arithmétique d'un TTL) → log+compteur par raison, **bandeau persistant** `role="status"` non masquable (le modal dit « regarde maintenant », le bandeau dit « toujours cassé »), et messages peer distinguant « jamais connecté » de « accès cassé côté peer » via `find_error_connector_type` (ADR-134 V2). **Alternatives écartées** : pré-filtrage du catalogue par scopes disponibles (préventif et séduisant, mais retire des familles entières d'outils, entre en conflit avec `kept_for_domain_coverage`, et exige de toute façon la couche d'honnêteté — lot mesuré à part) ; replanning sur plan invalidé (aucun plan n'accède à un connecteur non connecté : un appel LLM de plus et un risque de boucle) ; bandeau masquable (laisserait taire une condition qui ne disparaît pas d'elle-même).

### ADR-183 : Clôture du catalogue — un catalogue filtré doit permettre l'existence d'un plan valide

**Statut**: ✅ IMPLEMENTED (2026-07-31)
**Fichier**: `docs/architecture/ADR-183-Catalogue-Closure.md`

**Décision**: « résume ce mail X et propose une réponse » échouait en prod, puis réussissait 30 min plus tard sans qu'aucun code ne change. Deux exécutions prouvées sur logs (`617dd423` / `fb44ab80`), même intention et même `confidence=0.95` : la seule variable est la **paraphrase anglaise** produite par `deepseek-v4-flash` à `temperature: 0.2` et passée telle quelle au scoring sémantique (`select_tools(query=intelligence.english_query)`) — « Summarize the email titled… » (`get_emails_tool` à **0,010**, sous le seuil 0,07, exclu) contre « Find the email titled… » (retenu). Le planner recevait alors `reply_email_tool`, dont `message_id` est `required=True`, sans aucun outil capable de produire un `message_id` : **l'espace des plans valides était vide avant que le modèle ne commence**, d'où l'invention de `search_emails_tool` (outil réel du registre d'exécution, mais sans manifest catalogue → NOT_FOUND). **Retenu — une règle structurelle qui ne regarde jamais la requête** : *un catalogue est CLOS quand chaque type sémantique REQUIS par un outil qu'il contient est PRODUIT par un autre outil qu'il contient* — un éditeur de liens résolvant des symboles indéfinis, permissif (rend un plan possible, n'impose aucune étape). Deux règles la rendent correcte et non seulement plausible, toutes deux trouvées en simulant sur les manifests réels **avant** d'écrire du code de production : (1) un outil ne satisfait jamais sa propre exigence — `reply_email_tool` consomme ET produit un `message_id` ; (2) un fournisseur doit être **en lecture seule** — `send_email_tool` produit aussi un `message_id` et **était** dans le catalogue en échec, donc accepter n'importe quel producteur aurait rendu le mécanisme inopérant sur son propre cas fondateur. Un fournisseur par type requis (mesuré : jusqu'à 9 producteurs pour `URL`, mais ≤ 2 types requis distincts par outil → **croissance bornée à +2, typiquement +1**), départage déterministe (même domaine, puis score, puis nom — le score ne sert plus qu'à *classer*, jamais à garder zéro), consommateurs capturés AVANT tout ajout (un fournisseur en couvre souvent plusieurs ; les dériver après laisserait le second évinçable), arbitrage explicite de `max_tools` (5 par défaut : le plafond contraint réellement) avec abandon **loggé** plutôt que troncature muette, et fail-safe intégral. **Consolidation des manifests** : l'audit des 89 manifests annonçait 8 domaines « à trous » ; la contre-vérification en a laissé **un seul** — le critère nécessaire (paramètre obligatoire typable) n'est pas suffisant, il faut que la valeur soit *imprononçable par l'utilisateur* ET *non résolue en interne par l'outil*. Écartés comme faux positifs : `peer_name` (résolu par `fold_name`), les `*_name_or_id` Hue (`_find_resource_by_name`), les titres Wikipédia (prononçables) ; retenu : `automation_id` (`UUID()` strict). Le critère **valide rétroactivement** les annotations existantes. Défaut préexistant corrigé : `list_hue_lights_tool` déclarait `lights[].name` alors que le chemin réel est `hues[].name` (`meta.domain`), donc toute référence Jinja `$steps…lights[0].name` ne résolvait rien. **Dérive de l'ontologie** : ~70 types au `used_in_tools` incomplet désactivaient silencieusement la protection sémantique → `used_in_tools` et `source_domains` sont désormais **dérivés des manifests au point d'usage**, et la clôture ne lit jamais l'ontologie. **Alternatives écartées** : enrichir les `semantic_keywords` (on calerait des mots-clés sur une chaîne qu'un LLM réécrit à chaque tour) ; seuil sur le score brut + campagne de calibration (calibre un signal dont l'entrée est stochastique, et introduit une constante magique par domaine) ; tirer tous les producteurs (l'économie de tokens de 96 % disparaît) ; étendre aux paramètres optionnels (le planner peut les omettre — croissance non bornée pour rien) ; dérivation de l'ontologie au boot (imposerait au layer sémantique d'importer les manifests au niveau module et de muter des dataclasses `frozen`).

### ADR-184 : Une borne appliquée doit être publiée, et un verdict de validation ne vaut pas échec

**Statut**: ✅ IMPLEMENTED (2026-07-31)
**Fichier**: `docs/architecture/ADR-184-Published-Bounds-And-Non-Prescriptive-Verdicts.md`

**Décision**: « donne mes 3 derniers emails reçus » répondait « je n'ai pas pu récupérer tes emails […] vérifie les paramètres du connecteur email » alors que les dix emails étaient dans le contexte du modèle rédacteur (`registry_items_count=10`, requête `83c98053`). Douze requêtes consécutives mesurées : la cardinalité **3** produisait `max_results=20` trois fois sur quatre, jamais pour 2, 4 ou 5 — le prompt portait « set max_results = 20–50 » en dur avec pour exemple littéral « the 3 most important emails », donc la requête s'appariait au few-shot. **Trois couches désaccordées**, chacune corrigée à sa racine. (1) *Le catalogue cachait la borne* : `_manifest_to_dict` ne publiait la description que pour les paramètres `required`/sémantiques/`pattern`és/ID-like — `max_results` n'est aucun des quatre — et ne transmettait `maximum` dans aucun cas ; vérifié au runtime sur l'image de prod, le planner recevait `{"name":"max_results","type":"integer","required":false}` contre un manifeste déclarant `maximum=10`. **Une borne appliquée mais non publiée n'est pas un contrat, c'est un piège** → `min`/`max` publiés dans la forme compacte déjà utilisée pour `pattern`. (2) *Le prompt portait un nombre* → remplacé par `{semantic_broad_batch}`, **le setting qui existait déjà** (`planner_semantic_broad_batch`, défaut 25, utilisé par l'autocorrect du semantic-leak) : une source de vérité au lieu de deux nombres divergeables, et la cible explicitement subordonnée à la borne publiée. (3) *Un prompt correct reste une instruction à un modèle non déterministe* → `services/planner/parameter_bounds.py` écrête dans `_build_plan`, même doctrine que l'auto-correction `for_each_max` au même endroit ; ne sont PAS écrêtés `pattern`/`enum`/longueurs/types, références `$steps`, templates Jinja, booléens (`isinstance(True, int)` est vrai) et bornes incohérentes — les réparer inventerait une intention. Défaut de la même famille corrigé, **armé en prod** (`PLANNER_SEMANTIC_LEAK_MODE=autocorrect`) : l'autocorrect écrivait `max_results = broad_batch` sans consulter le manifeste, le validateur produisait donc lui-même la `CONSTRAINT_VIOLATION` qu'il rapporte. **D2 — le verdict était consultatif à l'exécution, prescriptif à la réponse** : `route_from_planner` ne lit jamais `is_valid`, le plan rejeté s'exécute inchangé et l'outil écrête lui-même (`get_emails_limit_capped 20 → 10`), mais depuis v1.27.3 `summarize_plan_blockers` déduisait « bloqué » du seul `is_valid=False` — le commentaire du code portait l'hypothèse fausse (« the turn ran on anyway », les outils « retournent vide »), vraie du cas fondateur ADR-182 (scopes OAuth), fausse d'une contrainte écrêtable. **Retenu** : un blocker n'est retenu que pour une capacité qui n'a **rien produit** (`execution_plan.steps` × `completed_steps`, les expansions FOR_EACH étant agrégées sous le `step_id` d'origine), un blocage de niveau plan étant tu dès que quoi que ce soit a produit ; le défaut par défaut reste « émettre » (état absent ou déformé par msgpack → ensemble vide → comportement antérieur restauré, jamais l'inverse), et la directive traite le tour partiel (« a partial result announced as a total failure is itself a false diagnosis »). Portée mesurée : 5 domaines sur 8 plafonnés sous la cible du prompt (emails/contacts/drive/places/tasks à 10 ; calendar à 25 passait, d'où l'absence de défaut sur « mes 3 prochains rendez-vous ») et ~30 sites `add_error` capables de produire la même fausse réponse. **Alternatives écartées** : rendre `is_valid` prescriptif à l'exécution (régression immédiate — les plans invalides du jour réussissaient : bloquer aurait transformé une réponse fausse en absence de réponse) ; une sévérité « réparable » dans `ValidationResult` (catégorise au lieu de supprimer, et impose quand même la réparation) ; relever les caps à 20–50 (déplace le nombre en dur, ne dit rien pour `weather` max 5 ou `health` max 14, laisse le planner aveugle) ; ne corriger que D2 (l'utilisateur reçoit toujours 10 emails pour 3 demandés) ; ne corriger que D1 (laisse la classe intacte sur les ~30 autres sites).

---

### ADR-185 : Un compteur est une affirmation, et la source lisible est la seule source

**Statut**: ✅ IMPLEMENTED (2026-07-31)
**Fichier**: `docs/architecture/ADR-185-Exact-CRM-Counts-And-Readable-Relayed-Messages.md`

**Décision**: deux chantiers convergents sur la même exigence d'honnêteté. **(1) Le pont CRM de la spec peers §11 (D2) n'avait livré qu'un booléen** : un peer connecté sans open loop ni appel n'avait **aucune carte** — le badge « LIA » n'avait personne à décorer — et les messages relayés, cœur de la fonctionnalité, restaient invisibles hors du fil. Le registre `peer_messages` **efface le contenu à la livraison** (§8.4, décision de confidentialité maintenue), donc le texte ne survit que dans l'archive du **destinataire** : le CRM lit **deux magasins, chacun pour ce que lui seul peut donner** — le registre comme épine dorsale (identité par **clé étrangère** : un renommage ne scinde pas une chronologie, un homonyme n'en fusionne pas deux, un compte supprimé disparaît seul), l'archive pour le texte et **uniquement des messages reçus** (un message envoyé n'a laissé aucune copie chez son auteur). **Un message dont le texte n'existe plus garde sa date et le dit** : une conversation réinitialisée dégrade l'entrée comme un envoi, jamais en entrée manquante — aucun compteur ne promet un texte inaffichable. Lecture d'archive **bornée de façon prouvable** par l'instant d'enfilement du plus ancien message hydraté (antérieur à son archivage par construction), plus une marge de 5 min car les deux `created_at` viennent de l'horloge **applicative** et de deux processus distincts. **(2) Les compteurs du CRM étaient faux et se taisaient** : l'aperçu comptait la longueur d'une fenêtre (`relations_max_items × 4`), la fiche chargeait 200 loops + 200 appels + **500 mémoires** avant de filtrer en Python — d'où une **incomplétude silencieuse** (le tri `due_hint asc nulls_last` faisait tomber hors fenêtre les engagements **sans échéance** au-delà de 200), un **coût invisible** (NFKD sur le contenu entier de 500 mémoires à chaque ouverture) et une **troncature muette** à 10. Correctif : l'aperçu interroge des **agrégats** (`GROUP BY` sur l'orthographe brute → `NameActivity`), la fiche interroge chaque source **pour cette personne** par ses orthographes exactes issues des mêmes agrégats — le SQL matche des chaînes brutes et **n'a jamais d'avis** sur qui est la même personne, `fold_name` restant l'unique implémentation de l'identité — et chaque section porte son **total exact** à côté de sa page. Seules les mémoires gardent un prédicat SQL (`unaccent` + `ILIKE`, pattern de la recherche de messages) : elles matchent par sous-chaîne, il n'y a pas d'orthographe à énumérer ; les deux divergences avec NFKD (ligatures, `ß`) sont documentées et testées, et le plafond de 500 disparaît — le rappel augmente. **Le bloc `lia_peer` de la spec §11 est enfin livré** : connectés depuis, ce que je partage, ce qu'ils partagent — les DEUX directions, parce que décrire seulement ce que l'utilisateur a réglé donnerait une vue unilatérale d'un arrangement bilatéral ; une SEULE lecture du domaine peers sert le badge ET le bloc (`list_accepted_peer_profiles`), interroger deux fois le même domaine pour la même page invitant les deux réponses à diverger. **Un silence de plus d'un trimestre porte une pastille « en sommeil »** — invitation à agir, jamais verdict sur la personne — qui sert aussi de filtre aux côtés d'un filtre « sur LIA » et d'un tri (récence/nom/volume), **tout en client** sur des lignes déjà chargées : une préférence d'affichage ne vaut pas un aller-retour serveur. **Les actions rapides utilisent `?draft=` et jamais `?intent=`** (auto-envoyé, QW-24/ADR-173) : légitime pour « préparer un point 360° » où le clic EST l'acte, interdit pour un relais vers un tiers (contrat A4) ; le bouton n'apparaît que sur une connexion active. **Alternatives écartées** : conserver le contenu dans le registre (régression de confidentialité) ; compter depuis le registre et lire le texte dans l'archive sans dégradation (« 3 messages » avec une section vide après une réinitialisation) ; prédicat SQL d'identité pour loops/appels (seconde autorité, divergente de `fold_name`) ; index partiel sur `message_metadata` (devenu inutile — l'aperçu ne lit plus l'archive) ; statut de présence « en ligne » (aucune utilité pour des messages asynchrones, divulgation forte des rythmes de vie, infrastructure entière à créer — la disponibilité issue du partage calendrier **déjà consenti** sert le même besoin).

---

### ADR-186 : Le fait survit aux mots, mais les mots ont droit à un délai

**Statut**: ✅ IMPLEMENTED (2026-07-31)
**Fichier**: `docs/architecture/ADR-186-Relayed-Message-Retention.md`

**Décision**: le relais effaçait le contenu **à la remise** (ADR-180 §8.4) — le CRM d'ADR-185 pouvait donc dire qu'un message avait existé, presque jamais ce qu'il disait. Rendre les **reçus** lisibles avait obligé à aller chercher le texte dans l'archive de conversation du destinataire, au prix d'une requête JSONB, d'un plancher temporel prouvable, d'une marge de décalage d'horloge et d'une dégradation assumée (réinitialiser sa conversation effaçait le texte) ; les **envoyés** n'avaient aucun texte, l'archive de l'émetteur ne contenant qu'un accusé de remise. **Le précédent invoqué par la demande produit (« comme les appels ») est plus précis qu'il n'y paraît** : `TelephonyRepository.purge_expired` efface `summary`/`structured_data`/`debrief` passé `expires_at` et **garde la ligne** (audit), rétention 30 j. Les messages relayés adoptent ce contrat exact : `delivered_text` (ce que l'assistant du destinataire a dit) et `expires_at` **posé à l'enfilement** — un message jamais parti doit expirer aussi, et son horizon ne doit pas dépendre de ce que le balayage a réussi à faire ; `content` cesse d'être vidé à la livraison ; le balayage peers, qui purgeait déjà le journal d'accès, devient le faucheur. **La ligne survit pour toujours, les mots trente jours** — pas un renoncement à §8.4 mais le même engagement exprimé par une fenêtre pilotable (`peers_message_retention_days`). **Chacun lit ses propres mots** : l'émetteur sa directive, le destinataire le texte livré ; les croiser déferait le relais (le destinataire lirait la directive brute au lieu du rendu de son assistant, l'émetteur découvrirait le ton de l'assistant d'en face) — pendant exact de `objective`/`summary` sur un appel. **Un message annulé garde sa directive** : « voici ce que vous avez tenté de faire passer, et ce n'est pas parti » vaut mieux qu'une ligne vide, et ce sont les mots de l'émetteur. **Le chemin d'archive disparaît** : JSONB, plancher prouvable et marge d'horloge supprimés, `relations/peer_messages.py` passe de 108 à 67 SLOC — la réponse durable était aussi la plus simple. **Assumé** : les messages déjà remis ont perdu leur texte pour de bon, ils gardent leur date et l'écran le dit (garder le chemin d'archive pour eux aurait conservé toute la complexité qu'on vient de retirer, pour un historique fini et décroissant). **Alternatives écartées** : conservation sans limite (rompt avec le seul précédent de contenu daté du produit) ; ne dé-effacer que `content` (l'émetteur servi, le destinataire toujours tributaire de son archive — le cas le plus courant) ; montrer les deux textes à chacun (le rendu personnalisé d'un assistant n'appartient pas à l'autre utilisateur).

---

### ADR-187 : Une seule boîte, deux identités, un seul arbitre

**Statut**: ✅ IMPLEMENTED (2026-07-31)
**Fichier**: `docs/architecture/ADR-187-Discovery-By-Address.md`

**Décision**: la découverte de pairs ne cherchait que par **nom complet exact** — on départageait les homonymes avec le fragment d'email masqué (garde A6), indice qui arrive APRÈS la recherche alors qu'on tenait déjà l'identifiant le plus discriminant. Le précédent invoqué contre (`/users/search/by-email` superuser-only, « prevents account enumeration ») **interdit un balayage `%pattern%` par sous-chaîne sur TOUS les comptes** ; la découverte est l'inverse sur les deux axes : **égalité stricte** et **uniquement des volontaires** (`discovery_enabled`, OFF par défaut). **Une seule boîte de recherche, et le backend décide** : `full_name` devient `query`, et `looks_like_email` (`peers/discovery.py`) est l'arbitre unique — laisser le frontend choisir le champ, ce serait lui faire porter une seconde heuristique qui finirait par contredire la première sur la même chaîne ; le prédicat ne fait que choisir une branche, donc une adresse à moitié tapée est cherchée comme un nom et répond « aucun résultat » au lieu d'un 422 (et le champ reste `type="text"`, sans quoi le navigateur refuserait « Marie Dupont »). **Deux plis, jamais mélangés** : `fold_name` reste NFKD + casefold (deux orthographes d'une personne sont la même personne), `fold_email` est volontairement plus faible — `strip()` + `lower()`, ni NFKD (`jérôme@` ≠ `jerome@`) ni `casefold()` (qui fusionnerait `straße@` et `strasse@`) : **sous-matcher coûte un « aucun résultat », sur-matcher coûte une identité** ; la casse en revanche se plie, l'inscription conservant la casse de la partie locale. **Le même balayage et les mêmes gardes** pour les deux branches (soi-même, opt-out, inactif, sans nom, blocage symétrique, annotation de relation), comparaison **en Python** des deux côtés — l'exprimer en SQL ferait de la base une seconde autorité sur l'identité des boîtes, la faute même qu'ADR-185 a corrigée sur les noms. **Assumé** : oracle d'appartenance sur les seuls comptes découvrables (même quota que par nom) ; deux boîtes ne différant que par la casse peuvent coexister et la recherche renvoie **les deux** plutôt qu'un choix arbitraire ; `full_name` disparaît du contrat sans alias de compatibilité (le frontend du dépôt est le seul appelant et part dans le même changement). **Alternatives écartées** : deux champs ou deux modes UI (font porter l'arbitrage au frontend ou à l'utilisateur) ; filtre SQL sur l'adresse ; réutiliser `fold_name` pour les adresses ; réserver l'email aux superusers.

---

### ADR-188 : Le CRM peut sortir de la base, à condition de dire ce qu'il a regardé

**Statut**: ✅ IMPLEMENTED (2026-07-31), amendé le même jour (§7-§12)
**Fichier**: `docs/architecture/ADR-188-CRM-Provider-Sections.md`

**Décision**: ADR-176 avait tranché « aucun appel fournisseur » en v1 et renvoyé contacts/anniversaires en **phase 2 documentée** ; cet ADR la ferme pour la fiche contact, les emails échangés et les rendez-vous partagés. **Le point dur est qu'une relation est un NOM et qu'un fournisseur veut une ADRESSE** — et trois faits vérifiés en code interdisent le raccourci : la recherche d'emails par nom d'affichage est appariée contre des **en-têtes MIME** (elle ramène des inconnus et en rate d'autres) ; `list_events(query=)` n'a **aucune parité** inter-fournisseurs et aucun ne promet « cette personne est participante » ; et une requête unique « from OU to » est impossible puisque `convert_imap_query` (Apple) construit un **ET** et `build_search_filter` (Microsoft) route par défaut vers la boîte de réception. **La fiche contact devient donc la clé de voûte**, et la recherche fournisseur y est une **piste, jamais un verdict** : chaque candidat est replié par `fold_name` et rejeté s'il ne correspond pas exactement — sur-matcher attacherait les adresses de quelqu'un d'autre, et tout le reste en découle. Le carnet est la SEULE source d'adresses : l'email de compte d'un pair, pourtant connu, n'est pas utilisé (il relève du réglage dédié C-bis, pas d'un effet de bord). **Deux recherches par adresse** (`from:` puis `in:sent to:`), chacune portant sa direction, l'une n'étant jamais vidée par l'échec de l'autre ; le calendrier demande une **fenêtre** et filtre les participants localement. **Aucun compte n'est affiché** : une page de fournisseur ne prouve pas de total (ADR-185), donc la section énonce sa **portée** (fenêtre en jours, nombre d'adresses utilisées). **Cinq statuts par section**, dont `no_address` — la fiche existe mais sans adresse, donc la question n'a jamais été posée ; le rendre comme « aucun email » serait le négatif non vérifié qu'ADR-184 a supprimé ailleurs. À l'écran, **une seule phrase à la fois**, classée par ce sur quoi l'utilisateur peut agir. **Endpoint séparé** `GET /relations/{name}/context` + **cache Redis par section** (6 h carnet, 15 min courrier/agenda), clé **hachée** sur l'identité repliée. Deux emprunts au briefing refusés : le stale-while-error et les comptes. Pilotable par `RELATIONS_PROVIDER_SECTIONS_ENABLED` (à false, le CRM retrouve exactement la posture ADR-176). **Assumé** : jusqu'à 1 + 2×N + 1 appels à l'ouverture d'une fiche, amortis par le cache ; sans fiche contact, ni emails ni rendez-vous — dit, pas caché ; anniversaires toujours hors périmètre (ils exigent une surface d'identité persistante). **Amendements §7-§12 (retour produit, même jour)** : `cc:` **appris aux deux convertisseurs** (critère imap_tools, terme KQL) car « envoyé à » inclut « en copie » et le résultat Microsoft n'était correct que **par accident** — trois recherches par adresse désormais ; **fenêtre sur le courrier** (365 j contre 90 pour l'agenda), qui borne la pertinence et le balayage du fournisseur, **pas le quota** (une recherche coûte un appel quelle que soit son étendue — le quota se borne par le NOMBRE d'appels et le garde-fou par utilisateur) ; **calendrier par défaut de l'utilisateur** via `resolve_owner_calendar_id` au lieu de `primary` — le défaut même que `connectors/preferences` existe pour fermer (un pair déclaré libre à 10 h alors que son agenda nommé contenait une réunion) ; **participant vs organisateur** distingués, avec Apple qui n'expose aucun organisateur → la distinction est déclarée **inconnue** (détectée sur les DONNÉES, pas sur le nom du fournisseur) plutôt que tout étiqueter d'un rôle non vérifié ; **rafraîchissement à la demande** `?refresh=` par section, en **appel impératif ponctuel** et non en clé de requête (collé à l'endpoint, un bouton pressé une fois serait devenu « ne plus jamais utiliser le cache »), un échec laissant la réponse en place ; **ordre demandé + repli** de chaque section (`aria-expanded`/`aria-controls`), **repliée par défaut** — le lecteur arrive sur un index compact où la pastille de compte, sur le bouton, est la seule chose qui reste pour choisir, fournisseurs **entrelacés** et non ajoutés en fin de page ; **sélection d'emails résumée dans le chat** en `?intent=` (l'acte délibéré) et non `?draft=` (réservé à ce qui écrit à un humain).

---

### ADR-189 : Être trouvable et donner son adresse sont deux consentements

**Statut**: ✅ IMPLEMENTED (2026-07-31)
**Fichier**: `docs/architecture/ADR-189-Peer-Email-Visibility.md`

**Décision**: le masque A6 (`j…@g….com`) protégeait à l'instant de la découverte, face à un inconnu ; il n'a plus grand sens entre deux personnes qui se sont **mutuellement acceptées**, qui échangent des messages relayés et se partagent un agenda — et depuis ADR-187 l'adresse est aussi ce qui permet de **retrouver** quelqu'un. Nouvelle colonne `users.peer_email_visible`, **défaut off**, **distincte de `discovery_enabled`** : en faire une seule case serait une régression de consentement, car **accepter d'être trouvé n'est pas accepter de donner son adresse** (deux verbes, deux tests qui vérifient qu'activer l'un ne touche jamais l'autre). **Seulement aux connexions ACCEPTÉES** : sur une demande en attente l'adresse est délibérément jetée — l'annuaire la charge, la liste des demandes la déballe et l'ignore, avec le commentaire qui dit pourquoi (*pas encore accepté n'est pas connecté*) — sans quoi un requérant obtiendrait en demandant ce qui s'obtient en étant accepté. La **découverte ne change pas** : un inconnu ne reçoit que le fragment masqué, opt-in ou pas, sinon l'oracle d'appartenance d'ADR-187 deviendrait un moissonneur d'adresses. **L'adresse OU le masque, jamais les deux** (deux informations sur une même personne se liraient comme deux faits). `PUT /peers/me` devient **partiel** (chaque champ indépendant, au moins un exigé) : envoyer les deux systématiquement laisserait un onglet écraser le réglage qu'un autre vient de changer. **Ce que l'opt-in ne fait PAS** : il n'alimente pas les sections fournisseurs du CRM (ADR-188), qui résolvent les adresses depuis le carnet de l'utilisateur — si l'email d'un pair devenait une source par effet de bord, ce réglage cesserait d'être le seul endroit qui décide de son exposition. **Assumé** : opt-in global et non par connexion (une table pour un besoin non prouvé ; le blocage couvre « pas celle-là »).

### ADR-190 : Le point 360° lit ce que le lecteur a coché, et la fiche contact ne montre pas quatre champs sur douze

**Statut**: ✅ IMPLEMENTED (2026-08-01)
**Fichier**: `docs/architecture/ADR-190-Overview-Scope-And-Full-Contact-Card.md`

**Décision**: trois défauts de la même fiche relation, fermés ensemble. **(1) Un manifeste sans outil est une promesse que l'exécuteur ne peut pas tenir** : en production, un point 360° répondait « je n'ai pas réussi à remonter ses interactions » parce que `_import_tool_modules` ne chargeait jamais `person_tools`, `documents_tools` ni `automation_tools` — trois familles **annoncées au catalogue, zéro enregistrée**. Le planificateur avait raison, c'est le registre qui mentait ; une garde CI (`test_catalogue_registry_parity.py`) compare désormais manifestes annoncés et outils enregistrés **après** import, comme le fait le boot. **(2) L'outil délègue aux services du CRM**, donc par **ADRESSE** (`build_detail` + `RelationContextService.build`) : même identité, même cache Redis, et surtout **la page et l'assistant répondent la même chose**. La recherche par nom survit en **repli de dernier recours**, uniquement sur `NO_ADDRESS` (sans adresse au carnet, une réponse vide serait pire qu'une réponse imprécise) et ses résultats sont **marqués** ; un connecteur absent ou en erreur n'est **jamais** rejoué par nom — réessayer autrement une question qu'on n'a pas pu poser, c'est fabriquer une réponse. **(3) La portée du 360° est écrite AVANT que le chat s'ouvre** (`users.relation_overview_scope` JSONB + `GET/PUT /relations/overview-scope`) : le `?intent=` ne porte que de la prose, donc laisser le planificateur déduire la portée d'une phrase ferait de la sélection une **suggestion** ; le bouton **attend** l'écriture puis navigue — et il est **le seul** point d'entrée, celui de l'entête ayant été retiré (un raccourci qui contourne le choix que la section existe pour offrir, et deux boutons qui peuvent diverger sur ce qui a été enregistré). Chaque champ est un **ensemble d'inclusions** — une liste vide veut dire « pas dans mon 360° », jamais « tout » : une portée qui grandit quand on la vide dépenserait le quota qu'on venait d'économiser. `max_items` est **borné ET publié** (5 par défaut, plafond 25, ADR-184), un champ vidé ne devient jamais 0, et une portée illisible **dégrade vers le défaut**. Le filtre participant/organisateur ne s'applique qu'aux événements dont le provider a **effectivement** exposé un organisateur : chez Apple il supprimerait sinon tous les rendez-vous au lieu d'admettre l'inconnu. **La fiche contact porte les treize blocs** du carnet (pseudonyme, fonction, anniversaire, note, adresses postales, relations, liens, dates importantes, messageries…) : quatre champs sur douze est une fiche que le lecteur cesse de croire. Un bloc qu'un provider ne stocke pas **ne s'affiche pas** (`relations`/`links`/`important_dates`/`messaging` n'existent que chez Google) — un texte de remplacement se lirait comme « le carnet ne contient rien » ; la fonction est lue dans `occupations` **ou** dans le `title` de l'organisation, sans quoi elle n'apparaîtrait jamais hors Google ; l'anniversaire reste une **chaîne** (`--MM-DD`, RFC 6350) car parser une date sans année inventerait l'année. **La photo est délibérément absente** : le portrait d'un tiers est une décision d'identité, pas une question de complétude. L'outil renvoie **la même** fiche que l'écran, blocs vides **absents** plutôt que `[]` (une clé vide inviterait le modèle à conclure « aucune famille enregistrée »). **Assumé** : portée **globale à l'utilisateur** et non par relation (une colonne, pas une table) ; trois blocs resteront vides hors Google — limite de provider, visible par omission ; `search_contacts` demande treize groupes de champs au lieu de quatre.

### ADR-191 : Un outil doit être joignable depuis le domaine qu'on lui adresse, et un clic n'est pas une phrase

**Statut**: ✅ IMPLEMENTED (2026-08-01)
**Fichier**: `docs/architecture/ADR-191-Reachable-Capabilities-And-Invoked-Directives.md`

**Décision**: un point 360° revenait amputé (ni engagements, ni appels, ni messages relayés) parce que l'assistant appelait trois outils génériques. La cause tient en trois faits vérifiables : l'outil 360° **n'a qu'un domaine** (`agent="contact_agent"` → `contact`) ; le **filtrage de domaine passe avant le score sémantique** (`normal_filtering.py` écarte tout manifeste hors domaine **avant** de lire la moindre pertinence) ; et le **prompt de l'analyseur impose** `peer` pour toute question sur un utilisateur connecté, en disant explicitement que le carnet d'adresses « ne peut pas répondre ». Reproduit sur le registre réel : `["peer"]` → catalogue d'**1 outil**, 360° **absent** ; `["peer","event"]` → 5 outils, **absent**. L'outil marquait **0,853**, le meilleur score de tout le catalogue, face à des génériques à 0,000-0,005 — il était éliminé sans que ce score soit jamais consulté. Quand ça marchait, c'est que le modèle avait émis `contact` **en plus**, contre la consigne : une bascule stochastique, pas un chemin nominal. **(1) Joignabilité** : `ToolManifest.serves_domains` déclare les domaines **additionnels** d'où l'outil est atteignable, et **une implémentation unique** (`SmartCatalogueService.placement_domain`) répond désormais à « cet outil est-il dans la portée ? » pour les **deux** stratégies de filtrage, qui posaient la même question chacune de son côté. Toute valeur est **validée à l'enregistrement** contre `DOMAIN_REGISTRY` — un domaine inconnu lève au lieu de rendre l'outil silencieusement injoignable. **Ce n'est PAS** ajouter `contact` aux `related_domains` de `peer` : ce correctif naïf a **déjà cassé la production** le 2026-07-30 (il tirait tout le CRUD Google Contacts dans chaque plan peer) — mesuré après correctif, un plan `peer` gagne **exactement un** outil, en lecture seule. **(2) Garantie** : rendre l'outil joignable le rend visible, pas certain. Or l'utilisateur n'a pas formulé une intention, il a **appuyé sur un bouton** — le système détient cette certitude avant qu'aucun modèle ne soit consulté, puis la sérialise en prose pour que trois étapes stochastiques tentent de la reconstituer. `ChatRequest.directive` porte donc `{capability, subject}` sur la couture exacte de `hitl_decision` : `capability` est un `Literal` **fermé** (le navigateur nomme une **capacité**, jamais un outil ; le serveur choisit quel outil **en lecture seule** l'implémente — cette porte ne mène pas à `delete_email_tool`), transport par `ContextVar` comme `active_skills_ctx`, et **application avant la validation**, au même titre que le clamp des bornes (doctrine ADR-184 : ce qui est mécaniquement réparable est réparé, jamais rapporté comme un défaut). **Le plan est enrichi, jamais remplacé** — les étapes du modèle survivent, et si le planificateur a déjà produit l'appel, **ses paramètres l'emportent**. **Un plan sans étape est laissé tel quel** : `ExecutionPlan` ne l'autorise que pour `needs_clarification` et `skill_bypass_noop`, et semer là répondrait de force à une question posée à l'utilisateur — **une garantie qui écrase une question est un bug**. **Écarté explicitement** : publier le score sémantique dans le catalogue (aucune preuve que le planificateur ignore l'outil *parce qu*'il ne voit pas le score, et cela modifierait le prompt de **toutes** les requêtes — une hypothèse non vérifiée ne se déploie pas). **Assumé** : `serves_domains` élargit l'ensemble des candidats pour toutes les requêtes du domaine ajouté ; la directive ne couvre que les surfaces qui l'émettent, le texte libre restant sur le chemin probabiliste — d'où le volet 1.

### ADR-192 : un lien profond du chat porte une demande, pas une transition de vue

**Statut**: ✅ IMPLEMENTED (2026-08-01)
**Fichier**: `docs/architecture/ADR-192-Chat-Deep-Links-Are-Real-Navigations.md`

**Décision**: après la v1.27.5, un point 360° sur un pair puis sur un second **reste figé sur le premier**. Le backend est innocent et la mesure le prouve : quatre lignes consécutives portant **la même phrase au caractère près** dans `conversation_messages`, et **trois succès** du cache de traduction (clé = SHA256 de la requête) — un succès de cache n'existe que si la chaîne reçue est identique. Reproduction hermétique, bundle de production, navigation client réelle : un clic qui pousse `?draft=Appelle Paul Martin…` **aboutit** sur `?intent=…Marie Dupont…&subject=Marie Dupont`, une URL que le code **ne peut pas fabriquer** (`chatIntentHref` est pure). C'est donc le routeur qui choisit l'URL : **il restaure les paramètres de l'entrée qu'il détient déjà pour la route**. Trois causes plausibles écartées **par l'expérience** : prérendu statique (route forcée dynamique, défaut inchangé), notre propre nettoyage d'URL (une première visite sans query, donc sans nettoyage, empoisonne quand même), réécriture i18n du locale par défaut (identique en `en`, non réécrit). La spécification e2e existante ne voyait rien car elle utilise `page.goto` — un chargement de document reconstruit le routeur depuis l'URL ; le défaut n'existe que sur navigation client vers une route déjà visitée. **Portée réelle** : les **treize** liens profonds du chat, pas le seul 360° — et le cas dangereux n'est pas le mauvais texte mais qu'un lien de **pré-remplissage** (`?draft=`, qui ne doit jamais envoyer) revienne en `?intent=` périmé, donc **auto-envoyé** : le clic exécute une demande que personne n'a faite. **Décision** : un lien profond du chat est une **navigation réelle**, jamais un `router.push` — le navigateur redevient seul maître de l'adresse, et la page démarre sur la barre d'adresse plutôt que sur une entrée de cache. **Une implémentation unique** (`openChatDeepLink`) sert les treize appelants, même doctrine que `placement_domain` (ADR-191) ou `fold_name` (ADR-185). **Uniforme et non réservé aux intentions** : corriger seulement `?intent=` laisserait ouverte la seule voie qui exécute sans consentement. **Le nettoyage du paramètre passe par l'API History** et non par `router.replace`, avalé pour la même raison — c'est ce qui laissait `?intent=` dans l'URL et faisait qu'un **rechargement rejouait la demande** ; ce défaut consigné la veille sans explication se ferme avec celui-ci. **Une garde CI** (`check_code_hygiene.py::chat_deep_link`, vérifiée voyante) refuse tout `router.push(chat*Href(…))` : une garantie qui repose sur la discipline de treize appelants n'en est pas une. **Le helper est épinglé par son propre test** — chaque appelant le simule, donc tous resteraient verts s'il redevenait un `router.push`. **Coût mesuré** : ~155 ms et un repeint par lien profond (108–214 ms sur trois exécutions) ; les arrivées externes le payaient déjà. **Écarté** : un transport interne one-shot (garderait tout instantané, mais deux sources de vérité sur la même page — à reconsidérer si la latence gêne), `experimental.staleTimes` (essayé, sans effet). **Assumé** : le correctif traite la conséquence dans notre code, la cause étant dans le routeur et hors de notre portée — le choix est de **ne plus en dépendre** pour ce qui porte une demande.

### ADR-193 : une capacité de lecture par domaine, et une identité que l'utilisateur peut corriger

**Statut**: ✅ IMPLEMENTED (2026-08-01)
**Fichier**: `docs/architecture/ADR-193-Read-Capabilities-And-Merged-Identity.md`

**Décision**: deux formulations de la même question — « de quand date mon dernier appel à ma femme ? » — ont produit, le même jour, un plan de LECTURE et un plan qui **téléphonait à la personne pour lui demander**. Ce n'est pas un caprice du modèle : le prompt annonce `Primary domain: telephony`, et le catalogue de ce domaine ne contenait **qu'une capacité, écrire**. **Décision**: trois capacités de lecture (`get_calls_tool`, `get_open_loops_tool`, `get_peer_messages_tool`), chacune **dans le domaine qui en manquait** — pas sur `contact_agent` avec `serves_domains`, mesuré comme évinçant six outils de mutation d'un catalogue plafonné : *une capacité de lecture ne doit pas coûter une capacité d'écriture*. Toutes projettent le même `build_detail` (une seule résolution d'identité, ADR-185), publient leur borne (ADR-184) et rendent le total exact. Elles n'appliquent **pas** la portée 360°, écrite pour une autre capacité — un refus fondé dessus serait inventé. **Une règle déterministe** ferme la voie inverse : intention non mutative + plan qui mute → rejet avec consigne de replanification, exécutée **avant** l'exemption `well_formed_cross_domain_mutation`, qui dispensait de vérification exactement la forme fautive (plus le plan était bien formé, moins il était vérifié). **Un chemin publié est un chemin qui existe** : `contacts[0].name` n'était produit par aucun des trois modes de `get_contacts_tool` alors que le validateur l'**approuvait** ; le champ est promu dans le payload (réparant du même geste la référence, la résolution conversationnelle et l'étiquette HITL), `total` devient `count`, et une garde CI résout chaque `reference_example` contre une sortie réelle. **Le domaine d'un outil est déclaré, pas deviné** : `place_phone_call_tool` appartenait au domaine `places` (son nom commence par `place_`), si bien que la règle de couverture criait au loup sur toute demande d'appel et se taisait sur le plan fautif. **L'identité est pliée par le système, corrigée par l'utilisateur** : table d'alias plate (compression à l'écriture, lecture en un lookup, **aucun cycle écrivable**), réversible, **affichée** avec son annulation, et qui ne touche **jamais** l'annuaire des pairs — une décision d'affichage ne doit pas rediriger un message vers un autre compte. **Nommer un pair injecte enfin ses faits locaux** (engagements, appels, messages relayés ; ni souvenirs ni blocs adossés à un connecteur), et là, à l'inverse, la portée 360° est souveraine : personne n'a rien demandé. **Les plafonds de catalogue deviennent des réglages**, avec une garde au démarrage — le plafond de secours n'est jamais inférieur au nominal, sans quoi le filet offrirait moins que ce qui vient d'échouer.

### ADR-194 : la vérité d'un chemin de référence est une garde CI, pas un validateur runtime

**Statut**: ✅ IMPLEMENTED (2026-08-02)
**Fichier**: `docs/architecture/ADR-194-Reference-Truth-Is-A-CI-Guard.md`

**Décision**: le dépôt portait ~1 900 lignes bâties pour valider les références `$steps.X.chemin` **avant** exécution — `ToolSchemaRegistry`, `SchemaExtractor`, `ReferenceValidator`, `build_schema_reference_guide` — câblées du démarrage jusqu'au validateur de plan. **Rien n'a jamais été validé, depuis le premier commit**, et pour deux raisons indépendantes : le registre est indexé sur les noms de **fonctions Python** quand le plan porte les noms de **manifeste** (intersection ∅ : 3 clés vs 85 outils), et le bras manifeste appelle `AgentRegistry.get_instance()`, méthode **jamais définie**, dont l'`AttributeError` est avalée par un `except Exception`. Mesure : **0 erreur sur 254 références** (publiées, réelles, absurdes, `CONDITIONAL` compris) ; en production sur 30 jours, **28 tentatives, 0 succès** pour 201 plans. **Réparer était pire que supprimer**, mesuré et non supposé : le bras manifeste réparé rejette **63 chemins légitimes sur 112** (`events[0].summary`, `emails[0].snippet`, `tasks[0].status`), le bras schéma réactivé **13 sur 35** dont `contacts[0].name` — le chemin même que le correctif de la veille venait de rendre vrai. La cause est sémantique : `reference_examples` est une liste d'**exemples**, traitée comme une **énumération exhaustive** ; et `SchemaExtractor` décrivait la sortie du *formatter*, pas celle du merge `parallel_executor` (sans `_registry_id`, `index`, ni clés top-level). **Décision** : la vérité d'un chemin se vérifie **avant le merge**, par `test_manifest_reference_examples_truthful`, dont l'**asymétrie est délibérée** — tout ce qui est publié doit être produit, jamais l'inverse : c'est exactement ce qui lui évite les 63 faux positifs. L'oracle est le **pipeline réel** (builder de l'outil, vrai `ReferenceResolver`, merge reconstruit), pas une inférence sur données simulées. `STEPS_REFERENCE_PATTERN` survit dans `orchestration/step_references.py` — porteur pour `capability_directives` — et le module documente pourquoi il ne doit **pas** fusionner avec le pattern plus étroit de `semantic_validator`. **Non-régression garantie par construction** : le bras supprimé n'ajoutait jamais d'erreur, donc `is_valid`, `summarize_plan_blockers` (ADR-184) et le routage reçoivent exactement la même chose. **L'extension de la garde (6 → 27 des 59 manifestes publiant des chemins) a immédiatement trouvé la suite du défaut d'ADR-190** : **sept manifestes mentaient**, toujours de la même façon — un outil adossé au registre publie à la racine ce qui vit sous sa clé de contexte (3 outils météo, 2 Perplexity, `list_task_lists_tool`), auxquels s'ajoute `list_labels_tool` qui déclarait un champ produit **seulement** sur appel filtré. **Un chemin peut résoudre et mentir quand même, sur son TYPE** : `weathers[].location` annoncé `string` alors que c'est un enregistrement, `hourly[].temp` annoncé `string` alors que c'est un float, `places[].opening_hours` annoncé `object` alors que l'API rend une liste — le planificateur lit ce type pour décider dans quoi chaîner la valeur, et une troisième garde le confronte désormais au type réellement produit. Ce qui reste non couvert (15 mutations à brouillon, 17 outils sans couture de formatage) est **chiffré dans un dossier de dette** plutôt que passé sous silence. Le filet d'exécution, lui, existait déjà : `ReferenceResolver` lève un `KeyError` explicite — ce qui manquait n'était pas la détection mais sa **position dans le temps**.

### ADR-195 : un diagnostic n'est pas une question, et un paramètre fourni ne se réinvente pas

**Statut**: ✅ IMPLEMENTED (2026-08-02)
**Fichier**: `docs/architecture/ADR-195-A-Diagnosis-Is-Not-A-Question.md`

**Décision**: quand un plan de **mutation** épuise ses replans, le filet de sécurité bascule vers une clarification — et la question posée était la **description de l'issue**. Un compte français a reçu en production `for_each pattern issue detected`, puis `Fabricated placeholder contact detail: step_2.to='jerome@example.com'` : du jargon, un chemin d'implémentation, et une adresse fabriquée que l'utilisateur pouvait croire vraie. **Mesuré, pas supposé** : 4 occurrences sur 205 plans en 30 jours, et reproduit en laboratoire au caractère près (31 + un espace par mot ajouté par le streaming = les 32 caractères observés). Le commentaire du code affirmait « the issue descriptions are already localized » — faux sur les **cinq** rejets déterministes, dont le docstring dit lui-même qu'ils sont « for the trace and the replan prompt ». **Mais vrai pour le chemin LLM**, ce qu'un test existant épinglait à raison : « La date de début est incorrecte (samedi 18 à 9h30 demandé) » vaut mieux que toute question générique, et la première version du correctif l'aurait détruit. **Décision** : une table `SemanticIssueType → question` (**15 types × 6 langues**) avec assert de complétude au boot (ADR-085), et un drapeau `user_facing` posé par **celui qui produit** — les rejets déterministes déclarent leurs descriptions techniques, le chemin LLM garde la sienne. Deviner en aval qu'un texte « a l'air technique » aurait été un pari renouvelé à chaque message. **Second volet** : un paramètre fabriqué (domaine réservé RFC 2606) est **réparé** depuis le plan précédent du même tour, jamais réinventé — doctrine ADR-184. Cette réparation **ne peut pas écraser un changement d'avis** : le déclencheur n'est pas « le paramètre a changé » mais « le paramètre est une adresse de documentation », que personne ne demande jamais. **La simulation a tué deux défauts avant toute ligne de production** : la règle ne traitait que les chaînes (donc pas `attendees`, le cas le plus courant) et n'exemptait pas les champs libres (elle **écrasait le corps d'un message rédigé**). **Trois hypothèses de diagnostic ont été infirmées par la mesure**, dont « `ExecutionStep` manque à l'allowlist » : l'ajouter ne change rien, le sérialiseur reconstruit par `model_construct` qui ne revalide pas — une dataclass reconstruit ses modèles imbriqués, un `BaseModel` non. Propriété désormais épinglée par un test, sans quoi les replis défensifs de `format_existing_plan_for_replan` passeraient pour du bruit. **Ratchet respecté par extraction**, jamais par relèvement.

### ADR-196 : l'identité d'une notification proactive est décidée avant son envoi

**Statut**: ✅ IMPLEMENTED (2026-08-03)
**Fichier**: `docs/architecture/ADR-196-Proactive-Notification-Identity.md`

**Décision**: une notification « heartbeat » est archivée comme message de chat, sa bulle porte 👍/👎, et le clic appelle `PATCH /heartbeat/notifications/{id}/feedback` avec la clé `target_id` de ses métadonnées — une route qui déclare `notification_id: UUID`. Or `generate_content` forgeait `target_id = f"heartbeat_{uuid4().hex[:8]}"`, chaîne que rien ne parse, pendant que la ligne d'audit recevait un UUID **neuf et sans rapport**. Trois conséquences silencieuses : le vote mourait en **422** (validé avant tout gestionnaire, et le composant avale l'échec par conception) ; `mark_proactive_feedback_submitted`, qui cherche la carte **par ce même `target_id`**, ne correspondait à aucune ligne — mécanisme pourtant correct pour les intérêts, dont le `target_id` **est** l'UUID ; et `run_id`, colonne qui se documente « Unique ID linking to token tracking », stockait le `target_id`, laissant **toute** notification heartbeat non joignable à `message_token_summary`. **Le défaut était actif** : `PROACTIVE_FEEDBACK_ENABLED` vaut `true` par défaut et dans les deux `.env.example`. **La suite ne pouvait pas le voir** : `test_router_feedback.py` portait en commentaire l'affirmation exacte « target_id is the notification id », les deux moitiés y étant simulées — il épinglait la **croyance**, pas le contrat. **Décision** : l'identifiant est la clé primaire, décidée par le producteur **avant** l'envoi (`str(uuid4())`), et la ligne est créée **sous** cet identifiant ; l'ordre l'impose, puisque le dispatcher fige les métadonnées de la carte avant que la ligne n'existe. `run_id` reçoit le vrai run injecté par le runner, avec repli sur l'identifiant — **jamais une constante**, la colonne étant `UNIQUE`. **Un contrôle qui ne peut pas aboutir n'est pas offert** : les notifications archivées avant le correctif gardent leur identifiant synthétique, donc `proactiveFeedbackProps` exige la forme `8-4-4-4-12` — la forme générique acceptée par `UUID()` côté Python, non un motif v4 qui masquerait des boutons que le serveur aurait honorés. **Aucune migration** (seule la valeur écrite change) ; les lignes historiques ne sont pas réparables, leur run de suivi n'ayant jamais été enregistré à côté d'elles.


### ADR-197 : être connecté à un service et être interrompu par lui sont deux décisions

**Statut**: ✅ IMPLEMENTED (2026-08-03)
**Fichier**: `docs/architecture/ADR-197-Interrupt-Permission-Is-Not-Connection.md`

**Décision**: le panneau du heartbeat affichait chaque source comme connectée ou non, sans offrir de décision : pour cesser de recevoir des notifications tirées des mails, la seule voie documentée était de **déconnecter le connecteur mail** — qui retire aussi l'outil avec lequel on demande ses mails. Un interrupteur pour deux questions sans rapport. **Trois faits vérifiés** : la liste affichée était fausse (sept noms codés en dur côté frontend contre **huit** calculés par le backend — `health_signals` n'a jamais été affiché) ; **onze** sources peuvent déclencher une notification, pas huit (anniversaires, engagements, conseil d'heure de départ compris) ; et le point de coupure est **unique** — `ContextAggregator.aggregate` n'a qu'un seul appelant, la tâche proactive, donc filtrer là n'affecte **aucun outil de l'agent**. **Décision** : onze interrupteurs, tous actifs par défaut, appliqués **avant la récupération** (une source refusée cesse aussi de coûter un appel d'API). La préférence stocke l'ensemble des **REFUS** : `NULL` = « jamais exprimé », donc zéro migration de données et une source ajoutée plus tard reste active jusqu'à refus — l'inverse d'une liste blanche, qui la rendrait muette pour tout le monde. **Le vocabulaire est publié** (`all_sources`, ADR-184) : le client ne redéclare jamais la liste qu'il n'applique pas, précisément la redéclaration qui avait perdu `health_signals`. **Lecture tolérante, écriture stricte** : un JSONB édité à la main est lu comme « tout activé » (faire taire une source par accident est le défaut à éviter), tandis qu'une clé inconnue est refusée en 422 — un refus silencieusement ignoré serait une préférence que l'utilisateur croit avoir posée. **Ce qui n'est pas une source ne se coupe pas** : les fenêtres d'anti-redondance disent ce qui a **déjà** été envoyé ; les couper ferait répéter l'assistant, pas se taire — elles sont hors registre et un test l'épingle. Complétude asservie **dans les deux sens** au démarrage (ADR-085). **L'agrégateur reste sous son plafond gelé** (697 / 705 SLOC), la table de spécifications remplaçant la liste de noms parallèle au `gather` et la seconde passe devenant une méthode à part — extraction imposée par le ratchet de complexité, que les trois gardes faisaient franchir à `aggregate` (CC 17 → 8). **Deux pièges mesurés à l'écriture** : une coroutine construite puis non attendue fuit et avertit (les sources refusées sont écartées **avant** création), et la note « non connecté » placée dans le `<label>` devenait une partie du **nom accessible** du contrôle (« Tâches Non connecté »), le faisant lire comme un état de l'interrupteur — elle passe par `aria-describedby`.

### ADR-198 : une routine s'exécute au plus une fois par jour local

**Statut**: ✅ IMPLEMENTED (2026-08-03)
**Fichier**: `docs/architecture/ADR-198-One-Run-Per-Local-Day.md`

**Décision**: le studio n'affichait qu'une prochaine exécution ; en instrumentant le planificateur pour en montrer cinq, un défaut de production est apparu, présent depuis toujours et invisible 364 jours par an. **Mesuré par simulation différentielle** contre APScheduler 3.11 — le moteur que l'exécuteur utilise — sur les transitions 2026 de sept fuseaux (décalages à la demi-heure, un à 45 minutes, hémisphère sud, et Lord Howe dont le changement vaut **30 minutes**) : au passage à l'heure d'hiver l'heure murale existe **deux fois**, et les dix sites de reprogrammation appellent `compute_next_trigger_utc` **sans référence** — « le prochain après maintenant ». Résultat : la routine s'exécute à 00:30 UTC puis **59 min 55 s plus tard**. **54 doubles exécutions**, et l'heure touchée dépend du fuseau — **Santiago est frappé à 23:00**, pas à 2 h du matin, si bien qu'un test limité à la nuit européenne aurait été faussement rassurant. **Décision** : le modèle n'autorisant qu'une heure par jour, la règle **au plus une exécution par jour local** est sûre par construction — un second instant pour le même jour est l'artefact de la transition. **Une exécution consommée n'est pas un test manuel** : `execute_single_action` sert le planificateur ET le bouton « tester maintenant », et appliquer la règle aveuglément **supprimerait** l'exécution à venir (tester une routine de 08:00 à 07:00 la repousserait à demain) — d'où la distinction `due_at <= now`. **L'affichage lit l'instant, jamais le datetime du déclencheur** : au passage à l'heure d'été l'heure murale peut ne pas exister et le déclencheur renvoie `02:30` portant l'ancien décalage, alors que l'exécution tombera à `03:30`. Les cinq occurrences voyagent en instants UTC, rendues avec `Intl` dans le fuseau **de la routine** (pas celui du navigateur), et un changement de nom de fuseau entre deux lignes est signalé — l'heure murale ne bouge pas, l'instant si. **Une condition n'est pas une exécution** : les mêmes occurrences deviennent des **fenêtres d'évaluation**, prétendre connaître quand la condition sera vraie serait une invention. **Non-régression prouvée, pas raisonnée** : 15 036 scénarios, **54 divergences — exactement les 54 défauts**, zéro ailleurs ; une première règle candidate avait été **réfutée** par la même méthode (elle décalait d'un jour même en UTC, `get_next_fire_time` étant inclusif). **Corollaire i18n** : `format_schedule_display` alimente les outils, donc son texte est lu par le modèle puis restitué — il ne servait que `fr`/`en` et donnait de l'**anglais** aux quatre autres langues ; les libellés passent par `i18n_dates`, avec des abréviations **déclarées** et non tronquées (`"Mittwoch"[:3]` donne `Mit`, l'allemand écrit `Mi`).

### ADR-199 : suggérer seulement ce qu'on sait déjà, et montrer les résultats avant les volumes

**Statut**: ✅ IMPLEMENTED (2026-08-03)
**Fichier**: `docs/architecture/ADR-199-Grounded-Suggestions-And-Results-First.md`

**Décision**: deux surfaces disaient la mauvaise chose. Le **chat vide** proposait trois exemples génériques alors qu'il pouvait prouver que LIA connaît la journée — mais la page ignore délibérément l'état des connecteurs, et proposer « montre mes derniers mails » à un compte sans connecteur mail transforme la première interaction en échec. Le **tableau de bord** ouvrait sur messages, tokens, requêtes Google et coût : des chiffres d'administration, pas le récit de ce à quoi le produit sert. **Décision, volet 1** : l'endpoint de suggestions lit **uniquement le cache du briefing**, jamais une récupération — récupérer aurait corrigé la connaissance et cassé trois autres choses (réveiller les connecteurs, dépenser des quotas, ralentir l'ouverture d'un chat vide). Cache froid = liste vide, repli sur les amorces génériques : cas **ordinaire**, pas dégradé. Aucun LLM. **Trois entrées toujours** — les ancrées devant, les génériques complètent : une seule appauvrirait l'écran, six en feraient un menu. Le **statut de section fait foi** : `ERROR` n'est pas une preuve (le connecteur peut être tombé) et `HIDDEN` signifie que le lecteur a retiré la carte. **Volet 2** : quatre **agrégats exacts** (résultats utiles confirmés, actions, routines, engagements clôturés), seules les lignes `validated` comptant — `produced` veut dire « présenté » (E3), pas « confirmé utile ». **Deux candidats écartés plutôt qu'estimés** : « temps gagné », sans aucune source, et « documents effectivement utilisés » — les extraits injectés ne sont persistés nulle part, et *injecté* n'est pas *utilisé*. **Une instance qui ne mesure pas le dit** : quatre zéros affirmeraient au lecteur qu'il n'a rien accompli, phrase différente de « rien n'est compté », et fausse. Les volumes restent, repliés dans un `<details>` **natif** (sémantique, clavier et annonce fournis par la plateforme). `BriefingService.read_cached_cards` devient **publique** : « ce qu'on sait déjà, sans rien payer » est une capacité du domaine — sans elle l'appelant lirait les clés Redis lui-même ou appellerait `build_cards`. Même **cycle de facturation** que les tuiles de consommation : deux blocs d'un écran ne doivent pas décrire des périodes différentes. Aucun titre d'événement ni sujet d'engagement dans les journaux.
---

### ADR-200 : un panneau de réglages montre ce qu'il a produit, et le montre plié

**Statut**: ✅ IMPLEMENTED (2026-08-03)
**Fichier**: `docs/architecture/ADR-200-A-Panel-Shows-What-It-Produced.md`

**Décision**: deux panneaux décident quand LIA peut interrompre le lecteur — proactivité et centres d'intérêt — et **aucun ne montrait ce qu'il avait produit**. ADR-199 avait fermé la moitié du trou. Restaient deux problèmes. **Le contenu des notifications d'intérêt n'était pas conservé** : `interest_notifications` est une table d'audit bâtie pour la déduplication, elle stocke un SHA-256 et un embedding ; le texte existe pourtant à l'écriture (`result.content`) et était jeté. Une colonne `content` **nullable** le garde désormais ; les lignes antérieures portent `NULL` et la carte s'affiche **sans son paragraphe** — un hash ne s'inverse pas, et un résumé reconstruit serait pire qu'une absence. **Les deux historiques partagent une seule carte** (`NotificationHistoryList`) qui porte la forme, l'ordre des états et les trois règles déjà corrigées une fois : erreur vérifiée AVANT la vacuité, spinner de premier chargement dérivé de l'absence de données et jamais de `error`, total exact à côté de la page (ADR-185). Chaque panneau ne fournit que son **vocabulaire** : pas de priorité côté intérêts (une actualité n'est jamais urgente), pastilles nommant le sujet puis le fournisseur. **Trois blocs se replient FERMÉS** — onze interrupteurs, historique proactif, historique d'intérêt : la section devient un index qu'on ouvre, même raisonnement que la fiche 360°. **Fermé signifie démonté, pas masqué** : un `<details>` garde son contenu dans le DOM, donc un hook à l'intérieur requêterait encore ; les enfants ne sont rendus qu'ouverts et l'état pilote le `enabled` de la requête — « non affiché » n'est pas « non payé ». **Le repli ne cache pas une décision** : le nombre de sources refusées reste porté par l'entête, seule chose à juger tant que tout est fermé. Écarté : rejoindre le message archivé par `run_id` (pas d'index sur `message_metadata->>'run_id'`, et disparaît à la première réinitialisation de conversation).
---
### ADR-201 : la provenance est une référence bornée, et une suppression laisse une pierre tombale

**Statut**: ✅ IMPLEMENTED (2026-08-04)
**Fichier**: `docs/architecture/ADR-201-Provenance-Is-A-Bounded-Reference.md`

**Décision**: LIA écrit souvenirs, entrées de journal et centres d'intérêt à partir de ce que le lecteur dit, et **rien ne reliait la conclusion au signal**. Les deux réponses naïves sont mauvaises : recopier le message d'origine fait survivre le contenu d'une conversation supprimée (fuite déguisée en fonctionnalité), régénérer l'explication par le modèle produit une reconstruction plausible — le diagnostic inventé qu'ADR-182 a retiré. **Une provenance est une référence, pas une copie** : `provenance_references` porte le sujet, la conversation, le message et un `outcome` parmi `origin` / `evidence` / `contradiction` ; aucun texte n'est dupliqué. **Une suppression laisse une pierre tombale** : `ON DELETE CASCADE` vers le sujet, `ON DELETE SET NULL` vers la conversation et le message — supprimer une conversation **vide la référence sans détruire la ligne**, le lecteur voit « ce signal a été supprimé » plutôt qu'une trace de ce qu'il a effacé ; `CASCADE` aurait fait disparaître jusqu'à la mention qu'une source ait existé, ce qui se lit comme « LIA a inventé cela ». **Bornée par construction** : cinq références au plus par sujet, les plus anciennes élaguées à l'écriture — non bornée, c'est une seconde copie de l'historique qui grossit au rythme de l'usage. **La borne est publiée** (`kept_at_most`, ADR-184). Une contrainte `CHECK` interdit une ligne sans sujet ou à deux sujets — une provenance orpheline ne serait jamais purgée. La table est classée `_PURGED_FULL` et purgée **explicitement avant ses sujets** : la cascade aurait suffi, mais l'inventaire RGPD ne l'aurait pas listée, et ce que l'inventaire ne liste pas, personne ne vérifie. Écarté : un champ JSON `sources` par sujet (trois schémas en miroir, aucune contrainte référentielle, pierre tombale devenue du code applicatif donc oubliable).
---

### ADR-202 : ce qui se lit a sa propre destination, ce qui se règle garde la sienne

**Statut**: ✅ IMPLEMENTED (2026-08-04)
**Fichier**: `docs/architecture/ADR-202-Reading-Has-Its-Own-Place.md`

**Décision**: cinq flux s'adressent au lecteur — messages relayés, notifications proactives, notifications d'intérêt, rappels en attente, actions programmées — et **aucun n'avait de lieu de lecture** : chacun vivait replié dans le panneau qui le configure. Savoir ce que LIA avait dit demandait donc d'ouvrir les réglages, trouver le bon panneau parmi une trentaine et déplier le bon bloc, cinq fois : consulter était devenu une opération de configuration. Deux flux n'étaient même **pas lisibles** — `peers` n'exposait aucune route de listage des messages délivrés, `reminders` n'avait que des écritures. **Une destination « Alertes »**, à droite de « Relations », cinq sections repliées par défaut, paginées à dix. **Les écrans existants restent les réglages avancés et leurs liens profonds restent valides** : le hub ne remplace ni ne déplace rien. **Les deux routes manquantes sont créées en LECTURE SEULE** — un domaine qui ne savait qu'écrire ne se met pas à muter depuis un écran de consultation. **Chaque section publie son total exact à côté de sa page** (agrégat sur l'ensemble, jamais la longueur de la page — ADR-185), et le **badge d'une section repliée le porte AVANT l'ouverture** : il affichait `—` jusqu'au dépliage, si bien que le seul nombre qui sert à décider d'ouvrir ne s'obtenait qu'en ouvrant. Les cinq totaux viennent d'une **lecture de comptage unique** (`GET /notifications/hub-counts`), même forme que la carte des capacités — sondes gathered, chacune sur sa propre session, chacune dégradant à 0 ; chaque compte réutilise le repository de la page qu'il décrit. « Fermé ne coûte rien » portait sur les LIGNES, pas sur l'arithmétique : la page et ses jointures attendent toujours le dépliage. **La pagination est un état de section** remis à 1 par ajustement pendant le rendu, pas dans un `useEffect` qui aurait ajouté une violation au ratchet pour un état purement dérivé. Conséquence : six destinations dans la barre, donc icônes seules sous `xl` et compteurs de jetons repoussés à `2xl` — mesuré au navigateur, la version précédente faisait chevaucher « Hilfe » et le sélecteur de mode en allemand à 1280 px. `SettingsDisclosure` reçoit une `description` rendue **dans le `<summary>`** : replié ne veut pas dire muet. Non fait : aucune notion de « lu », qu'il aurait fallu inventer sur cinq domaines à la fois.
---

### ADR-203 : aucune option proposée au téléphone n'est acceptée à votre place

**Statut**: ✅ IMPLEMENTED (2026-08-04)
**Fichier**: `docs/architecture/ADR-203-No-Option-Is-Accepted-On-Your-Behalf.md`

**Décision**: le débrief d'appel proposait des suites sous forme de puces qui **envoyaient le message immédiatement** (`?intent=`, auto-envoyé — ADR-173). Un appel où l'interlocuteur avait proposé une date, un lieu ou un supplément tarifaire produisait donc une puce qui, d'un clic, engageait le lecteur sur cette proposition. Pire : l'appel produisait déjà `StructuredCallData` (date proposée, lieu, coût supplémentaire, décision en attente) que **le schéma de réponse n'exposait pas** — ce que l'interlocuteur avait proposé restait invisible pendant que la puce qui l'acceptait, elle, était bien là. **Une puce PRÉ-REMPLIT, elle n'envoie pas** : `chatDraftHref` (`?draft=`), icône « écrire » et non « envoyer », nom accessible disant ce que le contrôle fait. **Ce qui a été proposé est publié** : `TelephonyCallSummary.structured_data`, rendu par `CallDecisions` **avant** le débrief — l'offre se voit avant les suites. **Chaque suite reste un brouillon ou une approbation distincte** ; aucun chemin ne transforme « l'interlocuteur a proposé X » en « vous avez accepté X ». Le débrief gagne un bloc et un clic : c'est le prix exact de la règle.
---

### ADR-204 : expliquer l'incertitude vaut mieux que la noter

**Statut**: ✅ IMPLEMENTED (2026-08-04)
**Fichier**: `docs/architecture/ADR-204-Explaining-Beats-Scoring.md`

**Décision**: deux surfaces manipulent un chiffre invisible au lecteur — le poids bayésien d'un intérêt, l'état d'activation de chaque sous-système — et toutes deux invitent à la même erreur : en faire un score, un niveau, un pourcentage. **Le poids s'explique, il ne se note pas** : `GET /interests/{id}/explanation` publie signal d'origine, dernière mention, dernière notification, `prior_alpha`/`prior_beta`, taux de décroissance, plancher, jours écoulés, poids de base et poids effectif — le calcul est reconstituable, aucun champ n'est un rang. Le blocage garde son explication (il est le fait du lecteur). **Le taux de décroissance avait DEUX valeurs par défaut** (`get_top_weighted_interests` et `calculate_effective_weight`) : deux surfaces pouvaient classer les mêmes intérêts différemment sans qu'aucune soit la bonne — une seule source désormais, `INTEREST_DECAY_FLOOR` extrait dans `core/constants.py`. **Les capacités sont résolues en UNE passe côté serveur** : la liste de démarrage sondait sept sous-systèmes via sept hooks, douze requêtes au montage et douze occasions de se contredire ; `GET /capabilities` agrège par `asyncio.gather`, **chaque sonde sur sa propre session** (`AsyncSession` n'est pas sûre en concurrence), une sonde en échec dégradant à « pas prête ». **Une capacité désactivée par l'instance est ABSENTE, jamais grisée** (gate-keeper, ADR-061) ; `live`/`total` décrivent les nœuds offerts et ne peuvent donc pas contredire la liste. **Rien de publié n'est un niveau** — un test l'énonce comme contrainte de schéma (`level`, `xp`, `score`, `percent`, `progress`, `rank`, `badge`, `streak` interdits). **Un compte affiché est exact ou n'existe pas** (ADR-185) : `personality` et `proactivity` sont des interrupteurs sans décompte, et `detail ?? 0` transformait cette absence en « Active — 0 élément(s) », lu comme une capacité vide ; un seul helper dit « Active » tout court. **Le dessin est décoratif, tout ce qui est atteignable est un `<Link>` nommé** — un `<circle>` avec `onClick` aurait le même rendu et serait inutilisable sans souris. **La figure joint les capacités actives en ordre ANGULAIRE** : sa forme est la configuration de ce compte, et joindre dans l'ordre de placement produisait un tracé qui se croise (mesuré au navigateur). **La scène garde sa nuit dans les deux thèmes** : en thème clair la lueur devenait une tache et la poussière se lisait comme de la saleté ; les jetons `--capability-*` sont donc indépendants du thème, anneau de focus compris (`--color-ring` s'inverse en quasi-noir et aurait donné un focus invisible). **Deux défauts de peinture, invisibles à tous les tests de rôle** : `hsl(var(--primary))` est un idiome Tailwind v3 dans un dépôt v4 (`--color-primary: oklch(…)`) — `fill` invalide, **rendu NOIR** ; et `--cosmos-*` n'existe que sous `.cosmos`, classe que le tableau de bord ne porte pas — le dégradé ne peignait rien. Une garde de test lit désormais la feuille de style et refuse les deux. Écartés : le pourcentage de complétion (score déguisé, compare l'incomparable) et le graphe de forces (non déterministe, aucune image mentale possible, et pour seul oracle « quelque chose a bougé »).
---
### ADR-205 : un statut nomme un ton, il n'écrit pas ses couleurs

**Statut**: ✅ IMPLEMENTED (2026-08-04)
**Fichier**: `docs/architecture/ADR-205-A-Status-Names-A-Tone.md`

**Décision**: trois composants portaient chacun leur `Record<string, string>` de classes Tailwind pour le même travail — rendre une étiquette d'état — avec trois conséquences toutes constatées à l'écran. **La distinction promise n'existait pas** : `high` en `bg-destructive/10` et `medium` en `bg-warning/10`, deux jetons séparés de **23° de teinte en OKLCH** (27° contre 50°) rendus à 10 % d'opacité ; sur un compte réel — **89 lignes `high`, 113 `medium`** — le lecteur ne pouvait pas les distinguer, et le premier correctif via `Badge variant="destructive"` n'a rien changé puisque ce variant est **lui aussi un fond pâle** (`bg-red-100`). **Ces classes échappaient à la garde de contraste** `design-contrast.guard.test.ts`, qui vérifie chaque paire réellement produite par le design system sur 5 thèmes × clair/sombre. **Un statut inconnu tombait sur le repli du `Record`**, ce qui pouvait afficher en rouge une valeur dont personne n'a dit qu'elle était urgente. **Retenu** : `lib/status-tone.ts` expose `priorityTone`/`outcomeTone`/`directionTone` qui renvoient un **variant de `Badge`**, jamais une classe — une seule fonction décide, et l'étiquette hérite de la garde. **La hiérarchie est portée par la DENSITÉ, pas par la teinte seule** : `Badge` gagne un variant `alert`, seul fond **solide** des statuts (`bg-destructive text-destructive-foreground`, la paire que `Button variant="destructive"` utilise déjà et que la garde couvre) ; mesuré au navigateur, son fond est à **L=32 avec un texte à L=98** quand `warning` reste une teinte à 10 %. La distinction survit à deux teintes que l'œil confond, et fonctionne en niveaux de gris. **Une valeur inconnue est NEUTRE**. **Une étiquette est un mot, pas une phrase** : `Badge` fixe sa hauteur (`size="sm"` = 16 px), et un objectif d'appel de trois lignes en débordait — il se lisait comme du texte barré ; ce qui est long est mis en valeur par le **poids typographique**, qui ne suppose rien de la longueur. **Conséquences** : le comptage a tranché la question des boutons — `outline` **137 fois**, `ghost` 83, `softPrimary` **une seule** (celle qui venait d'être introduite) — donc les actions d'une fiche de relation et les raccourcis du hub prennent `outline` ; et **une pastille de compteur est bleue partout** (arbitrage 2026-08-04), zéro compris — une section vide est un fait, pas une autre nature de chose —, seul l'état **inconnu** (`—`) restant neutre puisque ce n'est pas un compte. La couleur ne porte jamais seule le sens : chaque étiquette garde son mot. **Écartés** : ajouter une sixième teinte de statut au thème (à faire vivre dans 5 thèmes × clair/sombre pour un problème que la densité résout sans toucher la palette) ; corriger les trois `Record` sur place (trois copies à recorriger la fois suivante, aucune passant par la garde).

### ADR-206 : une primitive porte son contrat, et un écran vide a une porte de sortie

**Statut**: ✅ IMPLEMENTED (2026-08-05)
**Fichier**: `docs/architecture/ADR-206-A-Primitive-Owns-Its-Contract.md`

**Décision**: un audit UX/UI transversal a mesuré quatre écarts qu'aucune garde en place ne pouvait voir. **La garde d'accessibilité mesurait une fraction de l'interface** : `jsx-a11y` n'inspecte que le DOM natif, donc `<Input>`, `<Label>` et `<Button>` lui étaient invisibles et la baseline affichait `0` en ne regardant que le HTML écrit à la main ; la table de correspondance a été essayée puis **rejetée** — la règle analyse chaque élément isolément, donc un `<Label htmlFor="x">` voisin d'un `<Input id="x">` lui apparaît comme un champ sans étiquette (**96 signalements, échantillon intégralement composé de code correct**). **Une erreur de saisie était visible sans être annoncée** : `aria-invalid` n'apparaissait **nulle part** dans 643 fichiers — WCAG 3.3.1 et 1.3.1, tous deux niveau A — et l'identité du champ venait du texte de l'étiquette (`label.toLowerCase()`), donc deux champs homonymes partageaient un `id` qui changeait de langue. **Les primitives parlaient anglais** : « Loading… » sur ~90 appels, un `role="status"` par rectangle de squelette (**24 régions live pour un tableau de cinq lignes**), `CardSkeleton` en `bg-white` (carte blanche sur thème sombre) et des libellés **français** en valeurs par défaut de `Pagination`. **Un état vide était un cul-de-sac** : sept états vides, quatre remplissages verticaux, quatre manières d'atténuer une icône — et **un seul des sept proposait une action**. **Retenu** : `ui/field.tsx` porte le contrat une fois (`useId`, `aria-invalid`, `aria-describedby` **additif**, `Label` réutilisé au lieu d'un `<label>` copié) ; le nom accessible se garde sur le **DOM rendu** (`form-control-names.guard.test.tsx`) en ne signalant que ce qu'une analyse peut trancher sans deviner — ni `label`, ni `aria-label`, ni `aria-labelledby`, ni `id`, un `placeholder` n'étant pas un nom (WCAG 3.3.2) : **27 contrôles nommés, garde à zéro, liste de gel vide** ; une primitive n'invente jamais une chaîne, et la **contrainte de rendu décide comment** — `Skeleton` devient décoratif (`aria-hidden`) parce que `dashboard/{settings,spaces}/loading.tsx` sont des composants **serveur** où un hook client est une erreur de build ; `EmptyState` n'accepte `variant="page"` **qu'avec une action** (contrainte de type) et son `reason` sépare « rien n'existe » de « le filtre n'a rien trouvé » ; l'état sélectionné **se dit avec `aria-current`**, il ne se désactive pas — `disabled` sur le bouton qu'on vient d'activer le retire du parcours de tabulation et **défocalise**, renvoyant le clavier sur `<body>` ; et un jeton réclamé par un utilitaire **doit exister** — huit composants demandaient `ring-offset-background` sans que `--color-ring-offset-background` soit déclaré, donc l'écart retombait sur le **blanc** natif de Tailwind, un halo blanc autour de chaque contrôle focalisé en thème sombre. **Conséquences** : un `aria-label` redondant avec le texte visible est **retiré**, non traduit (WCAG 2.5.3) ; une clé existante est réutilisée avant d'en créer une (deux ajoutées seulement) ; le squelette des réglages cesse de dessiner des sections réservées aux administrateurs avec des gouttières en double ; la prop `error` reste inutilisée — les erreurs passent par `toast.error` (331 appels, 5 s), chantier distinct. **Le même statut porte le même ton, partout** : ADR-205 n'avait réglé qu'UNE famille (la priorité des notifications), et « fonctionne » restait bleu sur MCP et les actions programmées, vert sur Drive/documents/espaces, et **gris** sur les appels récents — où `failed` et `completed` étaient donc la MÊME pastille ; « en cours » était `info`, `outline` ou une teinte écrite à la main selon l'écran. `lifecycleTone` range le vocabulaire partagé (`error`, `completed`, `active`, `syncing`, `pending`) en **cinq familles** — `success` / `info` / `destructive` / `warning` / `secondary` — et ne renvoie **jamais** `alert`, qui reste le seul fond solide de la hiérarchie de priorité ; un domaine n'ajoute une table que s'il nomme autre chose (`callOutcomeTone` : un interlocuteur qui décline est un fait, pas une panne, donc neutre). **Tout variant de `Badge` vient d'un jeton** : `success` et `destructive` peignaient `green-100`/`red-100`, hors des cinq thèmes et hors garde, alors que `lifecycleTone` y route la majorité des statuts ; le commentaire qui les justifiait (« fonds opaques contre la transparence du dégradé ») décrivait un risque disparu — `Card variant="gradient"` n'a **aucun** site d'appel — et les deux paires résultantes étaient déjà couvertes. **Le bouton qui confirme dit ce qu'il fait** : `AlertDialogAction` rendait `buttonVariants()` sans variant, donc une suppression irréversible se validait dans le même bleu que « Enregistrer », et n'acceptait aucune prop `variant` — **dix-sept sites** réécrivaient les classes, dont trois oubliaient `text-destructive-foreground` et un atteignait `bg-orange-600` ; le variant est désormais une prop, et deux niveaux de destruction voisins se distinguent par `warning` et `destructive`. **Le déclencheur et la confirmation ne portent pas le même poids** : les icônes de suppression en bout de ligne restent `ghost` — dix-huit boutons rouges pleins dans une liste diluent le signal au lieu de le porter. **Écartés** : mapper les composants dans `jsx-a11y` (geler 96 faux positifs aurait masqué les vrais cas) ; rendre le spinner muet (dix suites s'appuient sur son `role="status"` — le rôle est l'information, seule la chaîne anglaise devait partir) ; migrer les 27 champs vers la prop `label` (`FieldFrame` ajoute `space-y-2`, donc 27 champs auraient bougé — `htmlFor`/`id` corrige à rendu strictement identique).

### ADR-207 : une action a une altitude, et l'altitude choisit la forme

**Statut**: ✅ IMPLEMENTED (2026-08-05)
**Fichier**: `docs/architecture/ADR-207-An-Action-Has-An-Altitude.md`

**Décision** (arbitrage propriétaire 2026-08-05) : des actions de même nature ne portaient pas la même forme — « Écrire un message » en contour quand « + Ajouter » des serveurs MCP est plein, cinq « Télécharger CSV » à cinq hauteurs, des suppressions de ligne grises jusqu'au survol, des étiquettes de skills toutes grises. ADR-205 avait conclu « une action prend `outline` » sur un comptage de 137 sites qui mélangeait **toutes les altitudes** (annulations, préréglages, secondaires ET CTA) ; re-mesuré à l'altitude CTA seulement, la convention majoritaire était déjà l'inverse (MCP, actions programmées, passkeys, jetons santé, diffusion admin, import de skills — tous pleins). **Quatre altitudes, quatre formes** : le **CTA de section** est plein et thémé (`default`) ; la **destruction de masse** est pleine et rouge, à la **même taille** que ses voisines de barre ; l'**action de ligne** reste `ghost size="icon"` mais la suppression y porte **son rouge au repos** (`text-destructive`, modèle passkeys — un code couleur que le pointeur doit révéler n'est pas un code) ; la **secondaire vraie** (annuler, fermer, préréglage, retry d'error-boundary, lien de remédiation d'un bandeau) garde `outline`, désormais sa seule signification. **Une étiquette est tonée par sa table** : `skillTraitTone` (identité en primaire, coût permanent `always_loaded` en ambre, capacités neutres) — la galerie utilisateur et la section admin avaient déjà divergé sur les mêmes libellés. **Une grille aligne ses actions** : les cinq cartes d'export CSV copiées à la main deviennent UNE carte `flex flex-col`+`mt-auto` — la ligne d'action est droite quelle que soit la prose, côté utilisateur comme admin (même composant). Conséquences : « + Nouvelle entrée » → « + Ajouter » aligné mot pour mot sur mémoire/intérêts dans les six locales ; les surcharges locales de géométrie (`h-9`, `gap-1.5`) disparaissent ; le bouton admin de suppression de clé LLM gagne un nom accessible ; `text-red-500` rejoint `text-destructive`. **Remplace** la conséquence « relations et hub prennent `outline` » d'ADR-205 — le reste (tons de statut, densité, `alert` solide) est inchangé.

### ADR-208 : une rangée expose ses actions d'une seule façon

**Statut**: ✅ IMPLEMENTED (2026-08-05)
**Fichier**: `docs/architecture/ADR-208-Une-Rangee-Expose-Ses-Actions-D-Une-Seule-Facon.md`

**Décision** (arbitrage propriétaire 2026-08-05) : les trois écrans « éléments dans des catégories » avaient **trois patrons d'actions** — hover-reveal (`opacity-0 group-hover`, sans révélation au focus : le clavier tabulait sur des boutons **invisibles**), tap-n'importe-où gardé par `window.innerWidth` ouvrant un Dialog plein écran dupliqué ~70 lignes par écran, et actions toujours visibles (journaux). **Retenu** : les actions d'une rangée passent par **`RowActions`** (`ui/row-actions.tsx`) — icônes ghost toujours visibles dès `sm`, suppression rouge au repos, « ⋮ » → `DropdownMenu` sous `sm` dont le déclencheur **nomme la rangée** (`common.actions_for`) ; la barre d'une section à liste passe par **`SectionToolbar`** — CTA plein **toujours labellisé** (le « + » perdait son libellé sur téléphone pendant que « Tout supprimer » gardait le sien), secondaires présents à toutes les tailles (menu « ⋯ » sous `sm` — l'export était **supprimé** sous `lg`), destruction de masse visible partout à la même géométrie ; **ce qui se consulte se replie** (`SettingsDisclosure` : métriques épistémiques des journaux, occurrences suivantes d'une routine, bloqués et journal d'accès des connexions) et **la planification se synthétise** (« En semaine à 08:00 », `lib/schedule-label.ts`) — la carte d'une routine passe de ~8 lignes à 3 ; les contrôles dupliqués deviennent **`FrequencyControls`** (`MinMaxPerDay`, `HourWindow` — les quatre Selects étaient anonymes dans les deux copies). Conséquences : ~250 lignes de duplication supprimées, le disclosure des intérêts revient dans sa carte, l'export redevient accessible sur mobile, les trois blocs d'authentification forte partagent l'en-tête empilable et le niveau `h4`, les connexions se lisent en trois zones et leur `<select>` natif artisanal rejoint le `Select` maison, cinq contrôles anonymes gagnent un nom. **Écartés** : tout en menu « ⋮ » (deux clics au desktop sans nécessité) ; hover-reveal + focus (corrige le clavier, conserve la divergence — et un contrôle invisible au repos reste indécouvrable à l'œil).

### ADR-209 : le panneau de debug lit dans l'ordre d'exécution, sur une chronologie ancrée au run

**Statut**: ✅ IMPLEMENTED (2026-08-05)
**Fichier**: `docs/architecture/ADR-209-Debug-Panel-Ordre-D-Execution-Et-Chronologie-Ancree.md`

**Décision** : le panneau de debug avait grandi par itérations et mentait sur la chronologie — l'ordre d'affichage ne suivait pas l'exécution (la requête après la décision de routage, les vagues *prévues* après la timeline *réelle*, la résolution de contexte rangée dans la planification), « Execution Times » ordonnait les nœuds par une **liste manuelle** qui apposait tout nœud inconnu APRÈS `response` (en ReAct, `react_call_model` s'affichait après la réponse), et le tri du pipeline reposait sur `sequence`, un compteur **par TrackingContext** dont chaque extraction d'arrière-plan repart à 1 — l'appel n° 1 d'une extraction entrait en collision avec celui du routeur. **Retenu** : chaque appel LLM (et génération d'image) porte `started_offset_ms`, mesuré contre un **t0 run-level** (`chat/run_records.py`, ancré par le premier TrackingContext, partagé pipeline + arrière-plan) ; lifecycle et pipeline s'ordonnent par cette chronologie (séquence en simple départage et repli historique), la liste manuelle est **supprimée**, et le front en tire un **waterfall** qui rend la sérialisation visible d'un coup d'œil. Le panneau lit en **7 phases numérotées** dans l'ordre du run, replie les sections vides derrière un disclosure par phase, et rend visibles les étapes qui n'existaient nulle part : verdict du validateur (**informatif**, ADR-184 affichée en place — un plan rejeté s'exécute), boucle ReAct (itérations vs borne **publiée**), HITL, compaction (nouvelle clé d'état `compaction_debug`), mode d'exécution, dépense TTS (via `debug_metrics_update`, le sync-fallback terminant après le chunk principal), coût LLM des open loops, et l'affichage des générations d'images que le backend émettait déjà sans consommateur. **Présentation** : anglais uniquement ; tons sémantiques par les tokens du design system (chips via `Badge`, garde de contraste héritée) ; identités de nœuds par familles **bi-thèmes** (l'ancienne palette était sombre-seulement) ; `ScoreBar` unique avec **seuil dessiné sur la barre** et table de seuils unique ; état vide **neutre** (l'ancien badge rouge « FAIL N/A » accusait une étape simplement non exécutée) ; anomalies collectées en passe pure (+ **Zod en détecteur** : un payload dévié devient une anomalie, jamais une section masquée) et bandeau de synthèse scannable par requête (route, moteur, durée, tokens, coût). **Conséquences** : `chat/service.py` décroît (extraction `run_records.py`), ratchet CC frontend resserré (50 → 48), planchers de couverture frontend relevés (68/62/64/69 → 70/66/66/71). Doc : `docs/technical/DEBUG_PANEL.md`.

### ADR-210 : un intent consommé ne se rejoue pas, quel que soit ce qui ressuscite son URL

**Statut**: ✅ IMPLEMENTED (2026-08-05)
**Fichier**: `docs/architecture/ADR-210-Un-Intent-Consomme-Ne-Se-Rejoue-Pas.md`

**Décision** : quatrième mode de défaillance des liens profonds du chat, mesuré en production v1.27.12 — une action de carte (« Prépare une réponse au mail… ») **se ré-exécute à chaque retour sur la page chat** (deux lignes identiques en base à 27 s d'écart, chacune suivie d'un « Annuler »). Les règles 1-3 de `useDeepLinkParams` policent le **support**, or le support est rejouable par construction : depuis ADR-192 le clic est une vraie navigation, l'URL `?intent=` est une **visite de premier rang dans la base d'historique du navigateur** (omnibox, sites les plus visités, restauration de session), que `history.replaceState` n'atteint jamais — et tout rechargement complet d'une URL portant encore `?intent=` ré-exécute (reproduit : deux bulles identiques au second chargement). **Retenu** : l'idempotence se pose au **point de consommation** — chaque clic frappe un `iid` à usage unique (`chatIntentHref`), consommé dans un registre borné `localStorage` (FIFO 50, inter-onglets, `lib/intent-replay-guard.ts`) au moment exact du `clearIntent` ; une URL ressuscitée porte un iid consommé et **dégrade en brouillon visible** dans le composer (`replayedIntent` → `lib/chat-initial-message.ts`, priorité testée `?draft=` > rejeu > brouillon persisté), sans la directive (non re-consentie) ; un intent **sans iid** garde le contrat clic-=-consentement (liens durables « Run it now » émis par le backend, volontairement rejouables) ; le registre **échoue ouvert** (sans stockage, comportement pré-ADR — une demande ré-exécutée se rattrape, une demande perdue non). **Preuve** : `e2e/smoke/chat-intent-replay.spec.ts` (bundle prod — résurrection, aller-retour client, rechargement : une seule exécution ; contrat sans-iid épinglé), mocks chat factorisés dans `e2e/fixtures/chat.ts`. **Écartés** : transport `sessionStorage` (incompatible liens backend, invalide la preuve ADR-192), registre valeur+TTL (bloque un re-clic légitime), clé d'idempotence backend (consigné pour un éventuel cinquième mode).

### ADR-211 : un déploiement ne dérange pas la pile qui sert

**Statut**: ✅ IMPLEMENTED (2026-08-05)
**Fichier**: `docs/architecture/ADR-211-Un-Deploiement-Ne-Derange-Pas-La-Pile-Qui-Sert.md`

**Décision** : le déploiement reconstruisait `~/lia` **en place** (`rm -rf`), or un bind mount est résolu vers un **inode** à la création du conteneur — constaté EN DIRECT le 2026-08-05 : le conteneur qui servait les utilisateurs voyait `/app/config`, `/app/docs/knowledge` et `/app/data/skills/system` **vides** pendant les ~10 min de build (d'où `firebase_init_failed` et `system_rag_startup_error` récurrents), et le même `rm -rf` **détruisait toutes les sauvegardes PostgreSQL** (`POSTGRES_BACKUP_HOST_DIR=./backups/postgres`, répertoire vide horodaté à l'heure du déploiement : rétention réelle nulle depuis ADR-109). **Retenu** : dépôt dans un **staging** (`~/lia.staging`) qu'aucun conteneur ne monte, puis bascule par **renommage** — `mv` préserve l'inode, donc les conteneurs vivants gardent des montages valides jusqu'à leur recréation ; deux générations `~/lia.prev.*` conservées puis purgées ; exécution hors staging sans effet (la relance manuelle reste possible) ; **sauvegardes hors de l'arborescence déployée**, avec avertissement explicite si le `.env` de l'exploitant remet une valeur interne. **Preuve** : `test_backup_dir_outside_deploy_guard.py` + 59 tests Pester (chemins **dérivés**, donc valables pour tout `-RemoteDir`).
---

### ADR-212 : un label Loki est un multiplicateur de streams, pas un champ de recherche

**Statut**: ✅ IMPLEMENTED (2026-08-05)
**Fichier**: `docs/architecture/ADR-212-Un-Label-Loki-Est-Un-Multiplicateur-De-Streams.md`

**Décision** : le pipeline Promtail promouvait `event`/`logger`/`trace_id`/`node_name`/`intention`/`error_type` en labels indexés, or les streams sont le **produit cartésien des valeurs** — mesuré en production : **1416** valeurs distinctes pour `event`, 140 pour `logger`, `trace_id` non borné (une par requête), 771 streams et **quatre OOM kernel de Loki** en une semaine, dont deux déclenchés par une seule requête de 7 jours (l'outil s'effondrait quand on en avait besoin). Second défaut : `output: source: message` **remplaçait la ligne**, donc toute entrée portant une clé `message` arrivait dépouillée de son JSON (l'audit les a d'abord prises pour des `print()`). **Retenu** : seul `level` est promu depuis le payload ; les champs démis se filtrent à la LECTURE (`|= "x" | json | event="x"`, le filtre de ligne précédant le parsing) ; aucun stage `output` ; le stage `json` réduit à ce que les stages suivants consomment. **Preuve** : `test_promtail_label_cardinality_guard.py`, dont une classe **dérive** l'ensemble interdit de la config Promtail pour vérifier les tableaux de bord — un sélecteur portant un non-label n'échoue pas, il rend un panneau vide qui a l'air sain. 4 requêtes Loki migrées (11 des 15 sélecteurs inventoriés étaient des métriques Prometheus).
---

### ADR-213 : l'identité de l'appelant vient d'un en-tête qu'il ne peut pas écrire

**Statut**: ✅ IMPLEMENTED (2026-08-05)
**Fichier**: `docs/architecture/ADR-213-L-Identite-De-L-Appelant-Vient-D-Un-En-Tete-Qu-Il-Ne-Peut-Pas-Ecrire.md`

**Décision** : trois sites résolvaient l'IP appelante indépendamment (rate limit global, GeoIP, limiteur auth) en lisant `scope["client"]`, qu'uvicorn **réécrit** depuis `X-Forwarded-For` sous `--forwarded-allow-ips "*"` en retenant l'entrée **la plus à gauche** — or Cloudflare AJOUTE l'adresse réelle au lieu de remplacer l'en-tête, donc cette entrée est celle du visiteur. Reproduit en conteneur isolé : `XFF: 127.0.0.1, 198.51.100.42` → client résolu `127.0.0.1`. Conséquences observées : le plafond de 300 req/min compartimente sur une valeur que l'appelant choisit (la faire tourner donne un budget neuf), et les 2600 avertissements du scan du 2026-07-30 portent tous `geo_country=local`. Le docstring affirmait l'inverse, ce qui a fait tenir le défaut pour impossible. **Retenu** : chokepoint unique `core/client_ip.py` préférant `CF-Connecting-IP` (Cloudflare l'ÉCRASE), fondé sur la topologie déjà documentée (port lié à la loopback) ; la valeur est **analysée avant d'être crue** (un en-tête illisible est ignoré, jamais accepté comme clé de compartiment) ; le résolveur **ne lève jamais** — un scope malformé retombe sur le pair. **Preuve** : `tests/unit/core/test_client_ip_resolution.py`, 18 tests.

### ADR-214 : les habitudes utilisateur s'apprennent par statistiques déterministes, sous contrôle utilisateur intégral

**Statut**: ✅ IMPLEMENTED (2026-08-05)
**Fichier**: `docs/architecture/ADR-214-Habitudes-Utilisateur-Apprentissage-Deterministe.md`

**Décision** : LIA n'a aucune représentation apprise du *quand* de son utilisateur (le heartbeat décide sur « dernier message il y a N heures » ; le détecteur de récurrence d'ADR-140 est éphémère et **mathématiquement aveugle aux habitudes hebdomadaires** — fenêtre 14 j < 3 lundis). Le programme Habitudes (plan : `docs/plans/2026-08-05-habitudes-utilisateur-programme.md`) apprend le rythme d'activité et les demandes récurrentes verrouillées par **statistiques déterministes calibrées par simulation** — pas de ML entraîné (RPi5, explicabilité doctrine intérêts, volumes faibles) ; l'unité statistique du rythme est **le jour**, jamais le message (comptage par message = FP 83-100 % mesurés). **Zéro écriture hot-path** : job nightly leader-elected + ledger ADR-140 réutilisé ; les deux seams du Lot 0 sont fermés — `product_outcomes.domain` capturé au streaming du tour COURANT (gaté sur `routing_history_changed` : le premier chunk values rejoue le checkpoint du tour précédent, l'enregistrer serait une donnée fausse), et `is_automated_source` stampé sur la ligne user archivée (`archive_first.py`, extrait de `AgentService` — sans marqueur, une action programmée quotidienne apprendrait « utilisateur actif à 7 h » : LIA apprendrait de ses propres automatisations). **Le contrôle précède l'exploitation** : bounded context `domains/habits/`, flag `HABITS_ENABLED` défaut OFF, réglages complets (consultation, formule expliquée, provenance, blocage, suppression, export, purge GDPR) livrés avant toute consommation ; le rythme appris **priorise à l'intérieur** des bornes utilisateur, jamais au-delà (invariant anti-famine du `min_per_day` testé) ; remarques d'écart bornées (budgets, cooldown, k par forme, règle d'arrêt à 2 non-adhésions) et tout commentaire de surveillance interdit.

### ADR-215 : installateur self-host — local d'abord, prebuilt gaté par digests, secrets stdin

**Statut**: ✅ ACCEPTED (2026-08-06)
**Fichier**: `docs/architecture/ADR-215-Self-Host-Installer.md`

**Décision** : `./install.sh` construit localement par défaut (`lia-*:local`) ; le mode prebuilt n'existe qu'à travers un manifest de release `qualification="passed"` référençant des digests immuables (`repository@sha256:...`, jamais un tag), activé UNIQUEMENT par la publication du manifest à côté du bundle déjà qualifié — aucun rebuild à la promotion. L'artefact Web de release est same-origin et neutre en hôte (`NEXT_PUBLIC_API_URL=""`, origine canonique via `APP_URL_SERVER` runtime). Les seeds d'installation fraîche sont explicites, atomiques (un seul `psql`, `ON_ERROR_STOP=1`, une transaction, postconditions bloquantes) et marqués `SELF_HOST_SEED_BUNDLE`. Les secrets de bootstrap (admin + clés provider) passent par stdin en un document JSON, jamais par argv ni par l'état de reprise. **Baseline provider = OpenAI + DeepSeek**, dérivée mécaniquement de la configuration EFFECTIVE post-seed (le seed override chaque défaut qwen ; Qwen reste optionnel) (arbitrage propriétaire B10-bis : le seed `llm_config_overrides` est la configuration éprouvée et reste intact). `/ready` est un prérequis, jamais la preuve : vérificateur backend non-secret + login/chat hermétique en qualification jetable (amd64 + arm64 natif) avant tout claim prebuilt ; socket Docker opt-in via overlay ; upgrades/désinstallations destructives hors v1. Gates G0-G6 dans l'addendum d'audit.
### ADR-216 : une limite par utilisateur ne borne pas une instance

**Statut**: ✅ IMPLEMENTED (2026-08-06)
**Fichier**: `docs/architecture/ADR-216-Plafond-De-Depense-D-Instance.md`

**Décision** : les limites d'usage par utilisateur (tokens/messages/coût, par cycle et absolues) répondent à « combien ce compte consomme », jamais à « combien cette instance dépense » — et la vérification du 2026-08-06 sur toute la base confirme qu'aucun plafond global n'existait (`global`/`instance_wide`/`daily_total` : zéro occurrence). Or N comptes × leur quota est non borné, et un démonstrateur public donne un compte à chaque visiteur. **Retenu** : un registre journalier d'instance (`instance_daily_budget`, une ligne par jour UTC) alimenté par un UPSERT atomique à arithmétique de colonne (mesuré : 3 runs concurrents de 0,30 € → exactement 0,900000 €), écrit **dans la transaction** du résumé de tokens et sous SAVEPOINT (un `execute` avalé sans savepoint empoisonne la transaction et emporte le commit de l'appelant). L'enregistrement est **inconditionnel** : le conditionner à l'existence d'un plafond laisserait une fenêtre où l'administrateur en pose un pendant que le compteur est muet — le piège du réglage inerte d'ADR-183. Deux bornes composées, **la plus petite s'applique** (env = plafond de déploiement, réglage admin = à l'intérieur) : un opérateur ne peut que resserrer, et l'interface affiche ce qui S'APPLIQUE à côté de ce qui est saisi. La vérification est composée dans le point d'étranglement unique `check_user_allowed` (chat, SSE, voix, jobs planifiés couverts par construction), **hors du cache par utilisateur** (un « autorisé » en cache dépenserait tout un TTL après épuisement) et **indépendamment de `usage_limits_enabled`** (borner un compte et borner une instance sont deux protections distinctes). Sens de l'argent : les limites par utilisateur échouent ouvertes, une dépense inconnue échoue **fermée** — avec le TYPE de l'erreur au log, jamais son message, parce qu'un fail-closed muet est indéfendable en exploitation. Un refus d'instance porte son propre code (`instance_budget_exhausted`) + `Retry-After` jusqu'au minuit UTC, localisé dans les 6 langues : « contactez votre administrateur » est faux quand c'est le déploiement qui est en pause. Effet de bord : `system_settings` devient un **magasin générique typé** (une déclaration par clé, assert de complétude au boot, ADR-085) et l'administration du plafond vit dans `usage_limits` — la placer côté magasin fermait un cycle d'imports (F009). **Budget arbitré : 1 €/jour**, premier arrivé premier servi.

### ADR-217 : un interrupteur qui n'enlève rien à l'assistant n'en est pas un

**Statut**: ✅ IMPLEMENTED (2026-08-06)
**Fichier**: `docs/architecture/ADR-217-Capacites-Administrables.md`

**Décision** : LIA savait désactiver une famille de CONNECTEURS pour toute l'application (`ConnectorGlobalConfig`) mais rien d'équivalent n'existait pour les capacités non connecteur (STT, TTS, images, téléversements, RAG, recherche web, navigation, compétences, MCP, téléphonie) : seul un drapeau d'environnement, donc un redéploiement pour changer d'avis — et trois n'avaient même aucun plafond (le sélecteur TTS avait migré vers `llm_config_overrides` en v1.20.x sans laisser d'interrupteur). **Retenu** : un registre `domains/feature_switches/` (nom choisi parce que `domains/capabilities/` existe déjà — c'est la carte des capacités d'UN COMPTE — et qu'y écrire ferme deux cycles d'imports), avec **deux bornes composées dont la plus petite gagne** (env = plafond de déploiement, réglage admin = à l'intérieur ; un déploiement qui interdit court-circuite la lecture du réglage) et **trois modes d'application déclarés honnêtement** : `agents` (les outils quittent le catalogue du planificateur, via `exclude_tools` qui EXISTAIT DÉJÀ pour le refus de sous-agent — un mécanisme, pas deux, et coût nul quand rien n'est coupé), `route_enforced` (dépendance de routeur, 403 + code stable `capability_disabled` + nom de la capacité, jamais une phrase anglaise), `service_enforced` (la synthèse vocale n'a AUCUNE route — elle est produite dans le flux de chat — donc la coupure vit à `_should_start_voice` ; la première rédaction la déclarait « route » et c'était faux). Les clés de réglage sont **générées** depuis le registre de capacités dans le magasin typé d'ADR-216, sens unique `feature_switches → system_settings` : un magasin ne connaît jamais ses clients. Deux gardes ADR-085 au démarrage : les agents nommés doivent EXISTER au catalogue (elle a immédiatement attrapé `image_agent`/`rag_agent`, inventés — les vrais sont `image_generation_agent` et `document_agent`) et chaque capacité « route » doit garder SON routeur réel (vérifié en parcourant les objets routeur, pas le texte). Lire un interrupteur ne casse jamais une requête : un magasin injoignable résout à la valeur de déploiement, jamais à un « activé » surprise. **Preuve runtime** : couper `browser` masque l'agent, retire `browser_task_tool` du planificateur, fait refuser la route en 403, et la restauration remet tout.

---

### ADR-218 : une protection qu'aucun test ne recalcule finit par protéger le passé

**Statut**: ✅ IMPLEMENTED (2026-08-06)
**Fichier**: `docs/architecture/ADR-218-Surface-Verifiee-Du-Demonstrateur.md`

**Décision** : les lots 1→5 du démonstrateur ont livré chaque protection avec ses tests, mais tous avaient la même forme — ils ÉPINGLAIENT ce que le code faisait le jour de la livraison (liste blanche comparée à une liste écrite à la main, chemins sensibles énumérés à la main, familles de coût additionnées depuis un tuple écrit à la main). Une liste à la main ne décrit pas le système, elle décrit ce que son auteur en savait. **Retenu** : trois gardes qui RECALCULENT la protection depuis la source de vérité (les routes réellement montées, les champs réellement publiés) et la confrontent à une classification exhaustive — non classé = rouge, classé mais disparu = rouge, exclusion sans raison écrite = rouge. Les trois ont trouvé une faille que les tests verts existants ne pouvaient pas voir. **(1) Le plafond ne voyait pas la voix** : `tts_cost_eur` était publié dans le résumé de run, transmis à `record_run_summary`, et absent de la somme ; le STT ne prenait même pas la route (session propre, écriture directe dans `user_statistics`) — sur un démonstrateur public, le plafond de 1 €/jour était aveugle à ce qu'un visiteur essaie en premier. La garde lit par AST les clés `*_cost_eur` que `get_summary` publie vraiment. **(2) La connexion Google était ouverte** : le lot 2 impose les CGU sur le chemin d'INSCRIPTION, `_find_or_create_google_user` crée le compte directement depuis les informations du fournisseur — le visiteur n'acceptait rien, et le document qui lui apprend que tout est effacé chaque nuit était celui qu'il ne voyait jamais, aux frais du client OAuth du propriétaire. Fermé en trois couches (bord par `path_regexp` AVANT la liste blanche, dépendance de routeur, et `/auth/features` qui publie `federated_signin_enabled` pour que l'interface ne dessine pas un bouton qui répond 404). La garde de surface énumère les routes montées, modélise l'ORDRE d'évaluation de Caddy et gèle 53 routes revues une par une ; elle a aussi montré que `/metrics` répondait 404 par accident (repli web) et non par décision. **(3) La moitié des chemins de liaison n'était pas gardée** : le garde du lot 2 ne connaissait que `authorize`/`callback` alors que le routeur expose `/apple/activate` (« tests credentials, then creates connectors »), `/api-key/activate`, `/{id}/rotate`, `/philips-hue/pair|discover|test` — la classification reconnaît désormais un segment de liaison N'IMPORTE OÙ dans le chemin (`/philips-hue/activate/local` ne finit pas par `activate`), par segments entiers pour que `/connectors/authorized-apps` survive. Cause structurelle commune : le garde vivait dans `domains/connectors/` et ne pouvait donc voir que `/connectors` — il devient `core/demo_mode.py`, un module pour une doctrine (rien qui attache une identité réelle à un compte jetable). Chaque garde a été mise en défaut volontairement pour vérifier qu'elle rougit, et le comportement du bord est prouvé contre un vrai Caddy.

---

### ADR-219 : une position mémorisée ne vaut que si tout le monde la lit — et si son âge voyage avec elle

**Statut**: ✅ IMPLEMENTED (2026-08-16)
**Fichier**: `docs/architecture/ADR-219-Derniere-Position-Connue-Generalisee.md`

**Décision** : l'ADR-073 avait livré une persistance saine de la dernière position navigateur (opt-in, chiffrée, non historisée, TTL, throttle) mais cloisonnée aux jobs proactifs — le chokepoint `resolve_location` des outils ne connaissait que « navigateur sinon domicile », les actions planifiées n'ont jamais de contexte navigateur, et sur PWA gelée puis réveillée rien ne rafraîchissait la position (cache 5 min expiré, `geolocation: null` sur chaque message) : en déplacement, tout répondait depuis le domicile. **Retenu** : (1) renommage complet `use_last_known_location` + `PATCH /auth/me/location-preference` (un nom qui revendique une portée météo que le code n'a plus est une docstring mensongère) ; (2) la cascade du chokepoint intègre la position mémorisée — implicite : navigateur > last_known (fraîche) > domicile ; « où suis-je »/« près de moi » : navigateur > last_known **avec son âge** > invitation (le domicile n'entre JAMAIS dans cette branche) ; « chez moi » : inchangé — et la branche implicite extraite en `resolve_implicit_location` remplace les trois recopies manuelles des outils places ; les actions planifiées héritent sans une ligne ; (3) une position datée s'annonce datée : `ResolvedLocation.as_of`, marqueur `(last_known <ts>)` dans le contexte skill, règle dans le prompt versionné — jamais un point daté présenté comme la position courante ; (4) cycle de vie PWA : `visibilitychange`/`pageshow` → permission re-vérifiée, refresh silencieux si `granted`, `needsReactivation` si retombée à `prompt`, consommé par la bannière chat en mode proactif dès l'ouverture (1×/session) dont le bouton fournit le geste qu'exige la feuille native — plafond de la plateforme, aucune réactivation sans geste ; (5) le push throttlé quitte le bloc réglages météo (qui ne tournait que page ouverte) pour `useLastKnownLocationSync` monté dans le layout authentifié, échec de push = pas de tampon de throttle ; (6) le réglage vit sur le connecteur Google Places seul (opt-in + transparence), le bloc des notifications proactives supprimé sans trace. Le seuil 50 km reste propre au proactif ; TTL unique 24 h ; consentement et chiffrement d'ADR-073 inchangés.

---

### ADR-220 : un comptage qui repose sur la générosité du fournisseur n'est pas un comptage

**Statut**: ✅ IMPLEMENTED (2026-08-16)
**Fichier**: `docs/architecture/ADR-220-Comptabilite-Usage-LLM-Declaree.md`

**Décision** : un provider OpenAI-compatible n'émet l'usage en streaming que si la requête le demande ; l'adaptateur le demandait pour openai et qwen mais pas pour deepseek — le provider des trois emplacements diffusés. La prod comptait quand même (510/510 appels sur 30 j, mesuré) uniquement parce que DeepSeek envoie l'usage spontanément — comportement non demandé, non testé, non surveillé (seuls signaux : `model="unknown"` + log DEBUG). **Retenu** : (1) registre `PROVIDER_USAGE_CAPABILITIES` (stream_usage_flag / native / excluded — ollama local gratuit et perplexity sur clé utilisateur restent délibérément exclus) avec assert de boot ADR-085 et test épinglant que la déclaration EST le comportement de l'adaptateur ; le drapeau retenu est `stream_usage=True` (appliqué aux seules requêtes diffusées — le piège DashScope `stream=false` disparaît par construction) ; (2) un appel payant sans usage devient un signal : compteur `llm_calls_without_usage_total{node_name}`, WARNING aux deux callbacks, alerte `LLMCallsWithoutUsage` à seuil zéro + runbook ; (3) défauts voisins soldés : branche morte `config_override["streaming"]` supprimée (F3), extraction JSON unifiée `json_recovery` sur le corpus de l'audit (F5, trois échecs historiques épinglés), garde d'écriture cache contre les résultats dégénérés + pivot sémantique traitant la traduction vide comme un échec et logs de contenu à DEBUG (F4/G2), `openai_provider.py` mort supprimé avec ses tests (F7), câblage tracker du chemin `hitl_question_generator` épinglé (G1).

---

### ADR-221 : le réglage que l'exploitant voit est le réglage que le système applique

**Statut**: ✅ IMPLEMENTED (2026-08-16)
**Fichier**: `docs/architecture/ADR-221-Timeout-Par-Emplacement-Applique.md`

**Décision** : `timeout_seconds` existait de l'UI d'administration jusqu'à la résolution `LLMAgentConfig` puis n'était lu par personne — pendant qu'une quarantaine de `asyncio.wait_for` invisibles dans l'UI faisaient le vrai travail (miroir d'ADR-184 : une valeur écrite mais non appliquée est un piège). **Retenu** : le timeout par emplacement devient la borne transport PAR TENTATIVE transmise au client de chaque provider (alias `timeout` vérifié sur les quatre SDK installés, chemin Responses API inclus) ; les barrières `wait_for` restent la borne d'expérience utilisateur, inchangées et éventuellement plus serrées (la barrière chat `response` reste à 60 s pendant que le client à 120 s protège les appelants sans barrière — rappels, jobs de fond) ; aucun défaut appliqué sans mesure : six relèvements fondés sur 30 j de p99 prod, chacun commenté avec sa mesure et épinglé par test (`response` 60→120, `planner` 60→90, `heartbeat_decision` et `interest_content` 60→120 — des appels > 60 s étaient observés —, `open_loop_extraction` 45→90, `memory_reference_extraction` 30→45) ; `router_llm_timeout_seconds`, défini depuis des années et lu nulle part, est supprimé.

---

### ADR-222 : suppression de la couche stratégie HITL jamais câblée

**Statut**: ✅ IMPLEMENTED (2026-08-16)
**Fichier**: `docs/architecture/ADR-222-Suppression-Strategie-HITL-Non-Cablee.md`

**Décision** : `ConversationalHitlResumption` (~1 200 lignes avec ses trois helpers privés, derrière le Protocol `HitlResumptionStrategy`) implémentait une seconde boucle de reprise HITL que rien en production n'appelait — le chemin réel passe par `_build_hitl_resume_command` + `StreamingService` (conçu pour, drapeau `is_hitl_resumption`, quatre modes de stream) et les payloads sont construits par `parse_approval_decision`/`build_structured_decision`. La boucle morte ne souscrivait que `["values", "messages"]` : câblée un jour, elle aurait silencieusement perdu compaction et enrichissements d'outils. ~50 tests dédiés (« coverage target: 85%+ ») la maintenaient verte — couverture factice, docstring affirmant à tort le chemin « very much live ». **Retenu** : suppression classe + Protocol + tests (règle « dead code is deleted ») ; conservation des trois helpers réellement consommés (`_build_plan_modifications_from_classifier`, `build_edit_reformulated_intent`, `resolve_user_language`) ; les quatre tests du contrat `ToolApprovalDecision` — qui épinglaient le schéma vivant, pas le mort — migrés vers `test_domain_schemas.py`. Clôt le finding « chemin mort apparent » consigné aux findings des cartes HITL. Une stratégie alternative future se branche sur `StreamingService`, pas sur une boucle parallèle.

---

### ADR-223 : un tarif qui varie avec l'heure est porté par la ligne de prix, pas par le code

**Statut**: ✅ IMPLEMENTED (2026-08-17)
**Fichier**: `docs/architecture/ADR-223-Tarification-LLM-Par-Plages-Horaires-UTC.md`

**Décision** : DeepSeek facture le texte selon l'heure UTC (pleines 01:00–04:00 et 06:00–10:00, −50 % ailleurs) ; LIA appliquait le tarif plein 24 h/24, démonstrateur inclus. **Retenu** : colonne JSONB nullable `time_slots` sur `llm_model_pricing` (fenêtres `[début, fin)` UTC à la minute, minuit enjambable, non-chevauchement validé à l'écriture ; base = tarif hors fenêtre ; NULL/[] = plat inchangé ; générique — tout provider, 1..n créneaux) ; résolution unique `pricing_time_slots.find_active_slot` consommée par les deux chokepoints via un paramètre `at` optionnel (défaut = instant d'appel, celui persisté au ledger) et par le recalcul historique à `at_date` ; arithmétique des jumeaux du service async factorisée (`_token_cost_usd`) ; contrat d'update : omis = héritage sur la nouvelle version temporelle, `[]` = effacement (le `null` explicite serait avalé par `exclude_none`), état fusionné validé côté service (`TimeSlotsUnitMismatchError` → 400, avant le ValueError → 409) ; UI admin : toggle + éditeur de fenêtres (rappel du fuseau local), validation miroir, badge « Horaire », i18n ×6 ; blob Redis compatible dans les deux sens de déploiement ; pas de backfill (décision propriétaire — saisie via l'UI, seed inchangé avec exigence d'emport à la prochaine extraction).

---

### ADR-224 : conformité MCP 2026-07-28 — client dual-era (SDK v2) et OAuth lié à l'issuer

**Statut**: ✅ IMPLEMENTED (2026-08-17)
**Fichier**: `docs/architecture/ADR-224-Conformite-MCP-2026-07-28-SDK-v2.md`

**Décision** : la révision MCP 2026-07-28 rend le protocole sans état (plus de handshake `initialize`) et sa matrice de compatibilité condamne les clients legacy face aux serveurs modern-only — ce que LIA était (SDK 1.28.1 ≤ 2025-11-25), avec en prime trois MUST OAuth violés (`iss` RFC 9207 ignoré au callback, credentials DCR non liés à l'issuer, `application_type` absent) et un client anonyme (`mcp/0.1.0`). **Retenu, en trois lots sans régression** : (1) conformité OAuth indépendante du SDK — issuer enregistré à l'initiation (state Redis + JSONB existant, zéro migration), `iss` présent validé AVANT l'échange du code, issuer embarqué dans le blob de credentials avec re-registration automatique sur changement d'AS positivement détecté (issuer inconnu = tolérance pour l'existant), `application_type` dérivé de l'hôte du callback, callback devenu vraie cible navigateur (refus utilisateur → `mcp_oauth=denied` + toast informatif i18n ×6, jamais de texte fournisseur réfléchi, fini le 422) ; (2) robustesse — dépliage récursif des `ExceptionGroup` anyio + détection des rejets de révision (`400`/`-32022`) factorisés dans un unique `_surface_root_cause`, message actionnable `MCPModernOnlyServerError`, `clientInfo` = `LIA/<version>` ; (3) migration `mcp>=2.0.0` — client **dual-era** (`Client` `mode="auto"` : parle 2026-07-28, retombe sur `initialize`), transports sur `httpx2` (coexiste avec `httpx`, classes d'auth portées à interface identique), pattern éphémère conservé et factorisé (`_ephemeral_client`), sessions admin lifespan inchangées. Preuves exécutées : dual-era contre serveur 1.28.1 réel (stdio + HTTP), E2E du code migré contre les deux ères, runtime Docker avec excalidraw connecté, 17 279 TU backend + 5 510 front verts, MyPy strict propre, ratchets tenus. Rollback atomique via manifeste+lock (ADR-112).

### ADR-225 : support du standard Agent Plugins v1.0.0 — profil « skills + streamable-http MCP »

**Statut**: ✅ IMPLEMENTED (2026-08-17)
**Fichier**: `docs/architecture/ADR-225-Standard-Agent-Plugins-v1.md`

**Décision** : LIA devient un client conformant du standard Agent Plugins v1.0.0 (agent-plugins.org — plugins portables `plugin.json` + `skills/` + `mcp.json`, adoptés par ChatGPT/Codex/Cursor/Copilot/Kiro/VS Code) sous le profil incrémental §11.2 : skills + serveurs MCP streamable-http. Sept lots TDD : validation pure à schémas fermés (taxonomie de raisons stables, pattern de nom officiel), pipeline d'import réutilisant les gardes S1–S4 avec import par-skill transactionnel et **rapport d'import exhaustif** (chargé/sauté/raison — doctrine anti-faux-succès), persistance additive (`user_plugins` + FK nullable `plugin_id`), API import/liste/désinstallation groupée, section réglages dédiée avec badges de provenance, docs. Déviations documentées sans perte de conformité : stdio exclu (serveur multi-utilisateur — entrées sautées §7.2.2 r.4, donc `PLUGIN_ROOT`/`PLUGIN_DATA` sans objet), HTTPS strict loopback inclus (SSRF), secrets jamais importés. Arbitrages : collision de nom de skill → skip+report ; headers fixes → colonne non-secrète `extra_headers` (l'auth garde la précédence §7.2.1) ; suppression individuelle d'un composant de plugin bloquée au profit de la désinstallation groupée ; quotas pré-vérifiés avant toute écriture.

---

### ADR-226 : agent de génération de documents — LLM structuré dédié + renderers purs sur le socle Attachments

**Statut**: ✅ IMPLEMENTED (2026-08-17)
**Fichier**: `docs/architecture/ADR-226-Document-Generation-Agent.md`

**Décision** : nouveau domaine `document_generation` décalqué sur `image_generation` (agent virtuel + outil `generate_document` + entrée taxonomie), dont le « générateur externe » est un type LLM dédié `document_generation` en sortie structurée typée par famille de format (tabulaire csv/xlsx, sectionné docx/pdf/md/txt, diapositives pptx — schéma choisi avant l'appel, strict-compatible). Renderers purs **zéro dépendance nouvelle** (openpyxl/python-docx/python-pptx/PyMuPDF Story/csv stdlib, round-trip testés par les lecteurs RAG déjà embarqués, registre asserté complet à l'import), stockage/purge intégralement réutilisés d'`Attachment` (TTL `attachments_ttl_hours`, échéance portée par la carte), livraison done chunk + `message_metadata` par **un unique sérialiseur**. Sécurité : neutralisation OWASP des cellules actives avec exemption des littéraux numériques signés (probe : openpyxl stocke `=1+2` comme formule), CSV `utf-8-sig`, noms de fichiers et titres de feuilles assainis. Coût = tokens LLM via le tracking standard (pas de table de pricing) ; flags 3 niveaux + rate limit + famille de timeouts ADR-160 ; PDF servi `inline` ; HITL non requis ; échec après appel LLM payé = échec explicite, jamais de carte fantôme (doctrine v1.30.4). Rejetées : contenu par paramètre planner seul, mécanisme Skills, reportlab, ODT/ODS (YAGNI). (agent-plugins.org — plugins portables `plugin.json` + `skills/` + `mcp.json`, adoptés par ChatGPT/Codex/Cursor/Copilot/Kiro/VS Code) sous le profil incrémental §11.2 : skills + serveurs MCP streamable-http. Sept lots TDD : validation pure à schémas fermés (taxonomie de raisons stables, pattern de nom officiel), pipeline d'import réutilisant les gardes S1–S4 avec import par-skill transactionnel et **rapport d'import exhaustif** (chargé/sauté/raison — doctrine anti-faux-succès), persistance additive (`user_plugins` + FK nullable `plugin_id`), API import/liste/désinstallation groupée, section réglages dédiée avec badges de provenance, docs. Déviations documentées sans perte de conformité : stdio exclu (serveur multi-utilisateur — entrées sautées §7.2.2 r.4, donc `PLUGIN_ROOT`/`PLUGIN_DATA` sans objet), HTTPS strict loopback inclus (SSRF), secrets jamais importés. Arbitrages : collision de nom de skill → skip+report ; headers fixes → colonne non-secrète `extra_headers` (l'auth garde la précédence §7.2.1) ; suppression individuelle d'un composant de plugin bloquée au profit de la désinstallation groupée ; quotas pré-vérifiés avant toute écriture.

---

### ADR-227 : Réglages en master-détail — le rail est la carte, le panneau est le territoire

**Statut**: ✅ IMPLEMENTED (2026-08-18)
**Fichier**: `docs/architecture/ADR-227-Reglages-Master-Detail.md`

**Décision** : la page Réglages empilait 51 sections en accordéons repliés (deux layouts écrits À LA MAIN, ~330 lignes dupliquées, deux gardes parsant la source par regex) — navigation et contenu se disputaient le même axe vertical, qu'ADR-171 (barre collante) et ADR-172 (recherche) palliaient sans le résoudre. **Retenu — coquille master-détail rendue DEPUIS les tables** (arbitrage propriétaire sur maquette haute fidélité, patron Linear/Slack/Notion/Stripe) : rail groupé (onglet→groupe, ordre = `SETTINGS_SECTIONS`, tie-break recherche préservé) + panneau qui monte UNE section via deux registres à complétude compilée (`SETTINGS_SECTION_ICONS` prouvé contre l'icône que chaque composant passe à `<SettingsSection>` alias lucide résolus ; `SETTINGS_SECTION_REGISTRY` prouvé contre `declaredIn` par identité de fonction) + Vue d'ensemble en cartes (descriptions enfin visibles, **zéro fetch** — résumés d'état = lot ultérieur arbitrable). Le mode panneau est un **contexte** (`SettingsShellModeProvider`) forçant la branche non-repliable de `SettingsSection` : les 50 sections inchangées ; hors provider l'accordéon demeure (tests). `?section=` devient l'**état de sélection** (conservé, plus nettoyé : reload/partage retombent sur le même panneau ; URL nue referme). **Phase 2 d'ADR-172 réalisée** : 15 jetons admin (gate `superuser`, mots-clés ×6 locales), `ADMIN_TAB_DEFERRED` vidée, notice `admin_not_indexed` supprimée — liens profonds et recherche couvrent toute la surface. Absence honnête reprise inline (`EmptyState` observation aux constantes ADR-172, **poll continué** : une section qui répond tard remplace le message) ; gate décidable négatif → la section ne monte pas (ses requêtes seraient rejetées). Focus à **cliquet** (`focusRequest` monotone honoré une fois — sans lui, toute sélection au rail après une recherche re-volait le focus ; défaut trouvé en revue, épinglé par test). Drill-down sous `lg`, `100dvh`. Comportement réseau changé assumé : les requêtes d'une section partent à sa sélection, plus au chargement de l'onglet (~20 sections). Supprimés : `SettingsTabsBar`, calibration `scroll-mt-44` (ADR-171/172), gardes de parsing (`settingsPageBlocks`, guard de couverture) — la classe de dérive « la page et la table divergent » est morte par construction, la page ne listant plus rien à la main. **Alternatives écartées** : rangées de navigation (modernise sans repositionner) ; hub seul (pas de navigation latérale) ; scrollspy tout-déplié (51 sections × requêtes) ; routes par section (touche au routage, `?section=` suffit) ; statuts sur cartes (requêtes sur le chemin d'accueil sans arbitrage).

---

### ADR-228 : import/export tabulaire des administrations — le classeur est le formulaire

**Statut**: ✅ IMPLEMENTED (2026-08-19)
**Fichier**: `docs/architecture/ADR-228-Import-Export-Tabulaire-Administration.md`

**Décision** : le catalogue LLM (124 modèles × 24 caractéristiques + tarif) s'administrait ligne par ligne, une boîte de dialogue par modèle — une grille tarifaire complète demandait 124 allers-retours. **Retenu — socle générique déclaratif + un consommateur** : `infrastructure/tabular_io/` décrit un classeur en `WorkbookSpec`/`SheetSpec`/`ColumnSpec` et en dérive les DEUX sens (writer + reader), sans importer aucun domaine ; le domaine ne fournit qu'une déclaration et un applicateur, si bien que **décliner à une autre administration, c'est écrire une déclaration, pas du code de format**. L'instruction préalable a mis au jour **5 défauts préexistants dont 2 de facturation en PRODUCTION**, corrigés en Lot 0 : (1) « le » tarif actif n'existait pas — aucune contrainte `UNIQUE(model_id) WHERE is_active` et 4 chemins de lecture sans `ORDER BY`, 96/114 modèles à ≥2 tarifs actifs en dev, sonde d'exécution montrant un **facteur 4** entre le cache et `AsyncPricingService` sur le même instant, et un changement d'**unité** sur `scribe_v2` ; (2) cache rempli par nom BRUT et lu par nom NORMALISÉ → `gpt-4o-2024-05-13` facturé 2,50/10,00 au lieu de son propre 5,00/15,00 ; (3) 9 modèles actifs sans tarif, facturés zéro en silence ; (4) prix de cache ineffaçable (`exclude_none` avalait le `None`, 73/206 lignes NULL) ; (5) `deactivate` sans inverse. **Une migration n'invente jamais un prix** : la règle « garder la plus récente » s'est révélée FAUSSE 4 fois sur 4 contre la production, donc la migration `6e7f8a9b0c1d` fusionne uniquement les doublons strictement identiques (92 modèles + 2 paires de devises, sans perte) et **s'arrête en nommant** les divergents. Le fichier **dit ce qui EST** : `time_slots_summary` porte le tarif fenêtré sur la ligne qui porte le prix (défaut trouvé par le propriétaire sur un export réel — une ligne DeepSeek affichait son tarif creux et se lisait comme plat), `statut` énonce ce que ferait l'exécution, et le mode exporté vaut `flat`/`windows`, jamais l'instruction neutre `inherit`. **Rien n'est supprimé implicitement** (une ligne absente ne supprime jamais rien ; le retrait passe par `is_active`, dont le retour à VRAI réactive). **Un aperçu qui engage** : `dry_run` n'écrit rien, l'application re-dérive le plan et refuse s'il diffère, verrou optimiste PAR LIGNE via empreinte en colonne masquée, import intégral ou nul, et ce qui n'a pas changé n'est pas écrit. **La complétude est gardée, pas mémorisée** : une 1re version exportait 16 colonnes sur un schéma de 24+11 sans que le test de fidélité le voie (il comparait une extraction à elle-même) — l'oracle est désormais le schéma de la base, doctrine ADR-085. Preuves sur les 124 modèles réels via le code de production : 0 écart aller-retour, idempotence 124/124 sans tarif réécrit, sensibilité 4/4 sans faux positif ni négatif, Excel réel sans réparation (15 listes déroulantes, 5 colonnes verrouillées), 41 Ko en 76+110 ms → synchrone. **Pièges épinglés par tests** : `sheetProtection` inversé (la feuille protégée INTERDISAIT d'ajouter un modèle), `showDropDown="1"` masque la flèche, `data_only=True` renvoie `None`, `max_row` gonflé, chaîne vide ≡ `None`, `Decimal("NaN")` franchit le contrôle de minimum puis casse l'échelle, et une clé de détail REGROUPE au lieu d'identifier (sans quoi tout export fenêtré était irrecevable). **Limites assumées** : `provider`/`effective_from`/`effort_values` en lecture seule (le contrat d'écriture ne sait pas les exprimer, et un changement de fournisseur est SIGNALÉ), famille de raisonnement inédite hors tableur, seul Excel/Windows validé, groupes de colonnes repliables incompatibles avec la protection.

---

### ADR-229 : la carte des capacités est la source unique de l'état — et elle ne peut plus prendre du retard

**Statut**: ✅ IMPLEMENTED (2026-08-18)
**Fichier**: `docs/architecture/ADR-229-Carte-Capacites-Source-Unique.md`

**Décision** : deux constats, une cause. (1) `/capabilities` publiait **13 nœuds figés** : images, **documents** (v1.30.8), **plugins** (v1.30.7), **habitudes** (v1.28.0), serveurs MCP et téléphonie manquaient — la surface qui répond « ce que ton assistant sait faire » était la moins à jour de l'application — et elle lisait les drapeaux `settings.*_enabled` BRUTS, donc pouvait annoncer disponible ce qu'un administrateur avait coupé à chaud. (2) La Vue d'ensemble d'ADR-227 ne disait que ce qu'une section EST, le suivi « résumés d'état » attendant un arbitrage. **Retenu — une seule agrégation, lue par les deux surfaces** (arbitrage propriétaire : « option (a), et bien documenter pour ne jamais oublier »). La carte passe à **19 nœuds** déclarés en tables (`COUNTED_NODES` comptés, `SWITCH_NODE_KEYS` sans décompte — ADR-185 : un compte est exact ou n'existe pas) ; `PLATFORM_CAPABILITY_NODES` + `CAPABILITIES_OFF_THE_MAP` **partitionnent** l'énumération `PlatformCapability` avec une raison écrite par exclusion, et `_assert_capability_map_coverage()` s'exécute **à l'import** : une capacité ajoutée sans décision fait échouer le BOOT (doctrine ADR-085) — une consigne écrite se périme, un assert non, et c'est précisément la consigne qui a échoué entre v1.28.0 et v1.30.9. La disponibilité publiée est l'**effective** (`disabled_capabilities()` lu une fois par requête, plafond de déploiement ET interrupteur opérateur) ; une capacité indisponible n'est même pas interrogée en base. `lib/capability-sections.ts` déclare la correspondance capacité ↔ section **une fois** et dérive l'inverse (la constellation demande « où configurer ? », la Vue d'ensemble « que contient cette section ? »). Les cartes du hub portent une ligne d'état **dans les mots de la liste des capacités** (`activeLabel`), avec trois garde-fous : une requête et non trente, **silence** pendant le premier chargement / en cas d'échec / pour une section dont l'agrégat ne dit rien, et `aria-hidden` pour que le nom accessible reste la destination. Garde `test_capability_coverage_guard.py` : il lit les **trois** surfaces clientes (emplacements de la constellation, liens « pas suivant », six locales) — un garde limité à Python aurait laissé passer la moitié TypeScript de la dérive. **Alternatives écartées** : second endpoint `/settings/overview` (deux réponses possibles au même fait) ; une requête par carte (~30 sur le chemin d'atterrissage, le problème qu'ADR-227 venait de supprimer) ; cache Redis court (un compte périmé juste après une modification est un mensonge visible) ; mélange valeurs client + comptes serveur sur la même ligne. **Défaut corrigé au passage** : `core/config/document_generation.py` documentait un opt-in par utilisateur qui n'a jamais existé — la carte s'apprêtait à publier un état « dormant » que personne n'aurait pu allumer.

---

### ADR-230 : l'historique des versions est une page publique, et les surfaces qui le promettent y mènent

**Statut**: ✅ IMPLEMENTED (2026-08-19)
**Fichier**: `docs/architecture/ADR-230-Page-Publique-Changelog.md`

**Décision** : la bande « Tout juste livré » de la landing proposait « Voir tout l'historique » vers `/faq` — or la FAQ **publique** (`PublicFAQContent`, 257 lignes) ne rend **aucun** changelog : l'historique n'a jamais existé que dans la FAQ du **tableau de bord, derrière l'authentification**, et les deux pieds de page renvoyaient « Nouveautés » sur `/#changelog`, c'est-à-dire le teaser de trois versions. Un visiteur non connecté n'atteignait l'historique complet **nulle part**, et le docstring du composant affirmait le contraire. **Retenu — `/changelog`, page publique de plein droit** (arbitrage propriétaire) : composants **serveur** (`<details>` natifs, zéro bundle client, indexable), coquille de lecture identique à `/faq` (scope `cosmos-calm`, canonical + hreflang ×6, `BreadcrumbJsonLd`), source unique `lib/changelog.ts` inchangée et **zéro nouvelle clé i18n** (titre et sous-titre réutilisent `faq.changelog.*`, déjà écrites ×6). `groupChangelogBySeries` plie les 166 versions en 28 séries mineures **sans jamais trier** — elle replie des suites déjà ordonnées, la liste restant seule autorité sur l'ordre — chaque série étant un `section` nommé avec son ancre et un rail de chips repris de la FAQ publique. Bande landing et les deux pieds de page pointent la page ; le **header garde son ancre** vers la bande (rail de sections avec scroll-spy) et son entrée « Nouveautés » passe **juste après « Présentation »** (arbitrage 2026-08-19 remplaçant « après Encore + »), l'exclusion de la rangée saturée sous `lg` étant portée par un drapeau `lgOnly` après fusion des deux tables d'ancres. **Défaut de classe corrigé au passage** : `sitemap.ts` et `robots.ts` portaient chacun sa copie de la liste des pages publiques et avaient déjà divergé (`/more` et `/demo` sitemappés, nommés dans aucune règle `allow`) — `lib/public-pages.ts` devient la source unique, `NON_INDEXED_SEGMENTS` nomme avec sa raison chaque route délibérément non indexable, et une garde scanne `app/[lng]` pour exiger que toute route soit d'un côté ou de l'autre. **Alternatives écartées** : section `/faq#changelog` (l'URL ne nomme pas l'historique, page déjà longue) ; déplier l'accordéon du dashboard (derrière l'authentification, donc hors d'atteinte du visiteur concerné) ; header pointant la page (perte du scroll-spy) ; fusion avec `PUBLIC_ROUTE_SEGMENTS` (« indexable » n'est pas « accessible sans session » — `/reset-password` est la contre-preuve).

---
---
---

### ADR-231 : le contexte d'exécution devient typé — et LIA n'adopte pas Agent Server

**Statut**: ✅ IMPLÉMENTÉ (2026-08-29)
**Fichier**: `docs/architecture/ADR-231-Contexte-Runtime-Type.md`

**Décision** : une étude d'opportunité sur « Agent Server v0.13 » a produit deux réponses. **(1) Agent Server : NON**, cinq bloquants indépendants — `langgraph-api` est sous **Elastic License 2.0** quand LIA est **AGPL-3.0** et que le modèle de déploiement charge le graphe de l'hôte DANS le processus ELv2 (œuvre combinée, pas agrégation) ; la v0.13 n'a **aucune version stable** (`0.13.0rc5`, ligne stable `0.12.6`) alors qu'ADR-215 interdit de livrer une RC ; threads/runs/crons/queue **dupliquent** `conversations`, `background_runner`, `scheduled_actions` et le flux SSE déjà durcis ; `langgraph_sdk.Auth` ne gouverne que cinq ressources et ignore sessions d'appareil, step-up, WebAuthn/TOTP, pairs et plafonds d'usage — on aurait **deux** plans d'autorisation ; et 17 services tiennent déjà sur un RPi5 (3 376 Mo réservés, l'API en réservant 2 Go à elle seule). La variante « Studio en dev » est refusée aussi : `build_graph()` dépend du registre global du lifespan, donc un `langgraph.json` dupliquerait le chemin de boot pour une surface de debug qu'ADR-209 a livrée. **(2) Le contexte typé : OUI**, et il n'a jamais eu besoin d'Agent Server — `context_schema`/`Runtime[ContextT]` sont dans le paquet MIT déjà installé. **Six défauts mesurés dans l'existant** : `context=context_dict` est passé aux deux `graph.astream` et **lu zéro fois** ; `_build_tool_runtime` câble `context=None` en dur, donc un run porte un contexte qu'aucun outil ne voit ; aucun `context_schema` déclaré, donc `dict` brut sans validation ni MyPy ; le vrai plan est `configurable`, **17 clés / 43 fichiers** dont quatre privées non publiées (classe ADR-184) ; la même identité y circule sous **deux clés et deux types** (`user_id` en `uuid.UUID` d'un écrivain, en `str` d'un autre ; `langgraph_user_id` la duplique sur **25 sites** au nom d'un LangMem **non installé** — `parse_user_id(str | UUID)` n'existe que pour absorber l'ambiguïté) ; et **aucune garde CI ne convertissait un outil vers le schéma vu par le LLM** (les trois tests `bind_tools` passent par un faux modèle qui ignore ses outils). **Ordre non négociable, mesuré sur les quatre quadrants** : annotation `ToolRuntime` nue + contexte non-`None` ⇒ **avertissement Pydantic à CHAQUE appel d'outil** ; donc paramétrer les 117 signatures d'abord, remplir ensuite. **Bascule et assert de complétude sont un seul commit** : avec `context_schema` déclaré mais sans contexte passé, une reprise après interruption **réussit silencieusement** et chaque nœud lit `None` — livrer la bascule un déploiement avant l'assert ouvrirait cette fenêtre sur les conversations HITL en vol. Migration **déployable sans casse** : un fil interrompu avant la bascule reprend après, et un fil démarré après reprend avant (rollback vérifié) ; le contexte n'est **jamais** checkpointé. La lecture hors nœud passe par le ContextVar de `get_runtime()` (qui traverse `gather`, `to_thread`, `create_task`) et **non par une nouvelle clé dans `configurable`** — ce serait réintroduire le sac que le chantier supprime ; hors run elle lève `RuntimeError`, bruyante. **Constats réfutés, à ne PAS « corriger »** : la mutation en place de `configurable["oauth_scopes"]` est saine (LangGraph remet une **copie fraîche** à chaque nœud) ; les onze `ToolRuntime | None` nues sont des helpers privés, pas des `@tool` ; le contexte ne fuit pas dans le checkpoint (le premier test qui le prétendait écrivait lui-même la valeur dans l'état) ; le frontend n'a **aucun** contrat sur ce contexte. **Lot 3 (exposer LIA en serveur MCP) instruit puis reporté** par arbitrage propriétaire, avec son bloquant nommé : le HITL est appliqué dans les **nœuds**, jamais dans l'outil, donc un client MCP appelant un outil directement ne déclenche **aucune** confirmation — 63 outils en lecture seule, 14 mutations à brouillon inertes hors graphe, **4 mutations sans aucune garde** ; authentification retenue = jeton personnel **par utilisateur** haché en SHA-256 (jamais bcrypt : 163 ms contre 0,0004 ms par vérification, et il y en a une à chaque requête), le mode `static_headers` de Claude étant **refusé** car partagé par l'organisation. **A2A refusé** : `peers` est intra-instance et humain-à-humain. **Récolte des lectures achevée (2026-08-29)** : les 43 fichiers lisent le contexte typé, l'allowlist du ratchet est vide, et le point de construction unique n'écrit plus dans `configurable` que `thread_id`. Vider le lecteur sans vider l'écrivain aurait laissé les **deux** plans faisant autorité, et le non typé gagne toujours parce qu'il est plus facile à atteindre — une seconde garde épingle donc l'écriture au chokepoint. **Le compteur mentait** : le scanner ne reconnaissait que les clés littérales, donc `configurable.get(FIELD_USER_ID)` n'était comptée nulle part ; il annonçait « 0 lecteur » quand **huit fichiers** lisaient encore, dont un dans `infrastructure/`. Il **découvre** désormais les alias (toute constante de module valant une clé) au lieu d'en tenir la liste, et un test épingle cette résolution sur un fichier synthétique pour qu'elle survive à l'absence de lecteur réel à attraper. `infrastructure/` ne pouvant pas importer `domains/`, l'attribution Langfuse lit l'identité sur son **propre** plan (`metadata["langfuse_user_id"]`, écrit par `create_instrumented_config`) plutôt que dans le sac du graphe.

---

### ADR-232 : fermeture des boucles cognitives (auto-évaluation du journal, garde proactive, seuils adaptatifs)

**Statut**: ✅ IMPLÉMENTÉ (2026-08-19)
**Fichier**: `docs/architecture/ADR-232-cognitive-loops-closure.md`

**Décision** : contre-audit de prod des quatre boucles d'auto-amélioration, chaque constat vérifié par données (PostgreSQL/Prometheus/Loki) et simulations exécutées (rejeu hors ligne du détecteur de rythme, rejeu d'extraction avec LLM réel, Monte-Carlo du tirage de quotas). **Corrigé** : le tunnel d'auto-évaluation T→T+1 du journal (zéro signal depuis avril) est instrumenté (`journal_self_eval_total{stage}`) et débloqué — IDs T-1 vérifiés ajoutés au filtre anti-hallucination, éligibilité de consolidation pilotée par delta (le plancher absolu 3 affamait les journaux élagués à 2, portraits gelés depuis juin), clamp épistémique (`high` interdit à L0/L1 sans `evidence_count`) ; le garde proactif « ne pas interrompre » (code mort : attribut fantôme + ImportError avalée) reconstruit en port injecté (`ActivityProbe`) câblé par les deux schedulers ; sélection de candidats équitable (flag en SQL + `ORDER BY random()` — le pré-filtre horaire SQL est REFUSÉ, motif documenté) ; **seuils adaptatifs par utilisateur** (`infrastructure/adaptive/`) : contrôleur générique borné/hystérétique/observable avec kill-switch, premier périmètre = injection journal (plancher 0,55, plafond 0,70, bande 10–35 %). Habitudes : la barre effective réellement appliquée (Wilson ⊃ presence_min : 0,572 semaine / 0,699 week-end) est **publiée** (API + panneau réglages, arrondi par excès) et le recensement des barrières de rejet est métriqué — publication sans recalibration (l'autorité reste le harnais). **Requalifiés avec preuve (aucune action)** : coût de décision heartbeat, puces de feedback, fraîcheur de la jauge de niveaux.

---

### ADR-233 : l'ontologie sémantique perd sa machinerie de raisonnement non consommée

**Statut**: ✅ IMPLÉMENTÉ (2026-08-19)
**Fichier**: `docs/architecture/ADR-233-ontology-simplification.md`

**Décision** : la subsomption transitive, la distance de Wu & Palmer, le graphe de relations SKOS et les accesseurs par catégorie/outil n'avaient **aucun consommateur runtime** — supprimés (doctrine : la capacité non câblée se supprime, elle ne se garde pas « pour plus tard »). Restent les trois lookups réellement consommés (`get`, `get_all`, `get_by_domain`), les champs de données, la hiérarchie parent/enfant (diagnostics `validate_hierarchy`) et une classe de tests épinglant la surface vivante. L'intelligence d'adjacence vit désormais là où elle est consommée : `related_domains` (gardé **bidirectionnellement** par le test de ponts d'identité, allowlist motivée — dont le piège peer↔contact du 2026-07-30 respecté) et les annotations `semantic_type` des manifestes (cliquet en valeurs absolues : ≥125 paramètres, ≥145 sorties, ≥71 types consommés). Dette datée : purge des champs SKOS de `core_types.py`.

---




---

---

---
## ADRs Archivés

### ADR-005 (Version Originale): Workflow-Based HITL

**Status**: 🗑️ DEPRECATED (Superseded by ADR-008)
**Date**: 2025-10-25
**Fichier**: *(décision archivée — résumée ci-dessous, pas de fichier séparé)*

**Décision originale**: Workflow-based HITL avec interruptions mid-execution.

**Pourquoi deprec ated**:
- Complexité excessive (200+ lignes de rollback logic)
- State corruption bugs
- UX friction (3-5 approvals par query)

**Leçons apprises**:
- ✅ Plan-level approval > Tool-level approval
- ✅ Prevention > Rollback
- ✅ Simple workflows > Complex workflows

**Superseded by**: ADR-008 (Plan-Level Approval)

---

### ADR-001 (Archive): Unit of Work Pattern

**Status**: ❌ REJECTED (2025-09-15)
**Fichier**: *(décision archivée — résumée ci-dessous, pas de fichier séparé)*

**Décision**: Utiliser Unit of Work pattern pour transactions database.

**Pourquoi rejeté**:
- Complexité inutile pour cas d'usage simple
- SQLAlchemy session suffisant pour nos besoins
- Over-engineering

**Alternative choisie**: Direct SQLAlchemy async sessions avec context managers.

---

## Process de Décision

### Workflow ADR

```mermaid
graph TD
    A[Problème Identifié] --> B{Impact Architectural?}
    B -->|Non| C[Simple PR]
    B -->|Oui| D[Créer ADR Draft]
    D --> E[Analyser Alternatives]
    E --> F[Discussion Team]
    F --> G{Consensus?}
    G -->|Non| E
    G -->|Oui| H[ADR Status: ACCEPTED]
    H --> I[Implementation]
    I --> J[Validation Metrics]
    J --> K{Success?}
    K -->|Non| L[ADR Status: DEPRECATED]
    K -->|Oui| M[ADR Finalized]
```

### Étapes Détaillées

1. **Identification** (Problème nécessitant décision architecturale)
   - Impact sur performance/coût/complexité
   - Affecte multiple composants
   - Long-term consequences

2. **Draft ADR** (Status: 🎯 PROPOSED)
   - Utiliser template MADR
   - Analyser 2-3 alternatives minimum
   - Inclure métriques de validation

3. **Discussion** (Review team)
   - Pull Request avec ADR
   - Code review comments
   - Itération sur alternatives

4. **Décision** (Status: ✅ ACCEPTED ou ❌ REJECTED)
   - Consensus team
   - Merge ADR dans main
   - Communication équipe

5. **Implementation**
   - Créer issues/PRs liées
   - Référencer ADR dans commits: `[ADR-003] Implement domain filtering`
   - Update ADR si deviations

6. **Validation** (Metrics tracking)
   - Mesurer métriques définies
   - Update ADR avec résultats réels
   - Status: ✅ IMPLEMENTED si success

7. **Deprecation** (Si échec ou superseded)
   - Status: 🗑️ DEPRECATED
   - Documenter lessons learned
   - Créer nouveau ADR si replacement

---

## Naming Conventions

**Format**: `ADR-XXX-Short-Title.md`

**Examples**:
- `ADR-001-LangGraph-Orchestration.md`
- `ADR-002-BFF-Pattern-Authentication.md`
- `ADR-003-Multi-Domain-Dynamic-Filtering.md`

**Numérotation**:
- ADR-001 à ADR-099: Décisions fondamentales (architecture globale)
- ADR-100+: Décisions spécifiques domaines

---

## Status Definitions

| Status | Emoji | Signification |
|--------|-------|---------------|
| **PROPOSED** | 🎯 | Draft, en discussion |
| **ACCEPTED** | ✅ | Décision prise, implementation en cours/complète |
| **IMPLEMENTED** | ✅ | Implémenté ET validé (metrics OK) |
| **REJECTED** | ❌ | Alternative choisie |
| **DEPRECATED** | 🗑️ | Plus d'actualité, superseded |
| **SUPERSEDED** | 🔄 | Remplacé par ADR plus récent |

---

## Best Practices

### ✅ DO:

1. **Être concis**: 2-3 pages max par ADR
2. **Inclure diagrammes**: Mermaid pour architecture
3. **Métriques concrètes**: Baseline → Target
4. **Alternatives sérieuses**: Minimum 2-3 options
5. **Code snippets**: Montrer impact implémentation
6. **Liens vers docs**: Technical docs, external references

### ❌ DON'T:

1. **Pas de roman**: Garder focus sur décision
2. **Pas de jargon inutile**: Accessible aux nouveaux
3. **Pas de décisions triviales**: Réserver pour décisions importantes
4. **Pas de modification post-acceptance**: Créer nouveau ADR
5. **Pas de décision sans alternatives**: Forcer analyse options

---

## Ressources

### Documentation MADR

- **MADR Homepage**: https://adr.github.io/madr/
- **GitHub Template**: https://github.com/adr/madr/tree/main/template
- **Examples**: https://github.com/adr/madr/tree/main/docs/decisions

### ADR Tools

- **adr-tools**: CLI pour gérer ADRs (https://github.com/npryce/adr-tools)
- **log4brains**: ADR management tool (https://github.com/thomvaill/log4brains)

### Internal Docs

- **[ARCHITECTURE.md](../ARCHITECTURE.md)**: Architecture overview
- **[ARCHITECTURE_LANGRAPH.md](../ARCHITECTURE_LANGRAPH.md)**: LangGraph architecture
- **[HITL.md](../technical/HITL.md)**: HITL architecture (ADR-008)
- **[MESSAGE_WINDOWING_STRATEGY.md](../technical/MESSAGE_WINDOWING_STRATEGY.md)**: Windowing (ADR-007)

---

**Fin de ADR_INDEX.md** - Index consolidé des Architecture Decision Records LIA.

### ADR-234 : timeline d'activité — le travail proactif devient visible

**Statut**: ✅ IMPLÉMENTÉ (2026-08-19)
**Fichier**: `docs/architecture/ADR-234-activity-timeline.md`

**Décision** : un contexte borné en lecture seule `domains/activity/` agrège les tables d'audit existantes (heartbeat, intérêts, journal automatique, habitudes détectées, cycle de vie des open loops, dernières exécutions d'actions planifiées) en une chronologie fusionnée paginée — doctrine briefing (fetchers parallèles à session propre, zéro LangGraph, zéro table, zéro LLM, zéro cache). Comptage ADR-185 de bout en bout : totaux exacts `COUNT(*)` par kind sur toute la fenêtre, cap par source **déclaré** (`truncated`), source en panne **listée** (`failed_kinds`), jamais complétée en silence. Les reminders sont **absents à dessein** (éphémères : aucune trace persistée, donc aucun événement inventé). Constructeurs de requêtes purs épinglés par tests SQL compilés. API `GET /activity/timeline` sous flag `ACTIVITY_TIMELINE_ENABLED`, kinds stables résolus en libellés côté client (×6 locales). Frontend : fil accumulant (`useActivityTimeline`, reset sur offset 0, dédup (kind, ref_id)), groupement par jour local, puces de totaux exacts, avertissement de données partielles ; portes d'entrée = CTA du hub notifications + pied de la carte « For you », toutes deux sous flag (ADR-061), aucun slot de nav ajouté (rangée saturée, piège ADR-229).

---

### ADR-235 : piste de supersession mémoire — les corrections automatiques préservent l'historique

**Statut**: ✅ IMPLÉMENTÉ (2026-08-19)
**Fichier**: `docs/architecture/ADR-235-memory-supersession-trail.md`

**Décision** : les chemins AUTOMATIQUES de correction mémoire cessent d'être destructifs (l'update d'extraction écrasait en place, la fusion de consolidation supprimait le perdant). Deux colonnes nullables sur `memories` (`invalidated_at`, `superseded_by_id` FK SET NULL, migration `7f8a9b0c1d2e`, index actif déclaré modèle+migration — piège ADR-228) ; extraction update → `supersede_with_update` (successeur hérite des champs non fournis, embeddings régénérés), extraction delete → `invalidate_memory`, fusion → `_apply_merge` (perdant supersédé par le survivant) ; le PATCH/DELETE manuel garde son autorité (une correction utilisateur n'est pas une évolution). TOUTES les lectures filtrent le set actif via le prédicat central `_active()` — oracle = tests capturant les statements et compilant le SQL. La piste se purge après `MEMORY_INVALIDATED_RETENTION_DAYS` (90 j) dans le job de nettoyage. Ratchet CC préservé par extraction de helpers (décomposer, jamais relever). Prépare D1 (continuité : « tu me disais avant… ») sans jamais re-servir un fait périmé.

---

### ADR-236 : mémoire procédurale — l'assistant apprend COMMENT travailler pour son utilisateur

**Statut**: ✅ IMPLÉMENTÉ (2026-08-19)
**Fichier**: `docs/architecture/ADR-236-procedural-memory.md`

**Décision** : septième catégorie de mémoire `procedural` — instruction permanente EXPLICITE sur le comportement de l'assistant (« réponds plus court », « ne me propose plus X »), critères d'extraction stricts (intention durable adressée à l'assistant ; jamais déduite d'une humeur ; les habitudes de l'utilisateur restent `pattern`) ; une instruction contradictoire émet un `update` → supersession avec piste (ADR-235). Injectée comme directives contraignantes JUSTE APRÈS les zones sensibles (fichier d'en-têtes = source unique, complétude assertée contre l'enum) — aucune mécanique nouvelle : mêmes caps, même rétention, mêmes protections. Directive de réparation (D6) dans le prompt de base : une correction fraîche est reconnue UNE fois, sans sur-excuse, et appliquée DANS la même réponse — le côté psyché (rupture-repair + bonus de confiance) était déjà câblé, vérifié. B3 (auto-réflexion sur ToolErrorCode) est explicitement REPORTÉ au chantier budget ReAct (Lot 5-C4) : un self-critique LLM sur chemin d'erreur sans borne de coût, ou une leçon déterministe robotique, seraient pires que l'attente. Aucune migration (colonne string ouverte) ; l'utilisateur voit et supprime chaque règle apprise dans l'UI mémoires (doctrine ADR-184).

---

### ADR-237 : prosodie vocale paramétrique, et l'inventaire de la modulation de forme

**Statut**: ✅ IMPLÉMENTÉ (D4) + PÉRIMÉTRÉ (2026-08-19)
**Fichier**: `docs/architecture/ADR-237-voice-prosody-and-form.md`

**Décision** : la voix respire avec l'humeur — `domains/voice/prosody.py` pur (arousal→style+/stability−, gains doux, bornes dures [0,1], dead-band ±0,1 qui rend l'objet de base = « aucun override »), résolu UNE fois par stream (best-effort : un échec psyché ne coûte jamais l'audio), passé par appel via les kwargs du protocole TTS, flag `VOICE_PSYCHE_PROSODY_ENABLED` ; parité : OpenAI TTS n'a pas de surface équivalente — asymétrie documentée, jamais silencieuse ; `pleasure` réservé (la chaleur exige une calibration par voix). **Deux constats vérifiés-déjà-satisfaits consignés pour que les audits futurs ne les re-proposent pas** (doctrine de requalification ADR-232) : D2 (les 4 directives de stade relationnel modulent DÉJÀ la forme) et D3-PAD (la clause <InnerVoice> du prompt de base module DÉJÀ longueur/chaleur/suggestions). **A2 livré ensuite dans le même ADR** : `POST /briefing/synthesis/audio` (bouton « écouter » la synthèse — readout complet possédé par `voice/text_readout.py`, un premier jet dans le router briefing fermait un cycle `briefing<->chat` attrapé par le garde F009 ; bornes de coût env, audio bufferisé, toggle front avec révocation d'object-URL). **Périmétrés hors de ce lot avec motif** : D3-canal (aucun paramètre de surface de sortie dans stream_chat_response ; à réconcilier avec le mécanisme display-mode existant — chantier propre) et D5 (registre de goûts dérivés Big Five = décision de voix produit, l'œil du propriétaire sur le contenu avant livraison).

---

### ADR-238 : inbox de propositions et budget ReAct adaptatif (autonomie bornée)

**Statut**: ✅ IMPLÉMENTÉ (2026-08-20)
**Fichier**: `docs/architecture/ADR-238-proposals-inbox-adaptive-react.md`

**Décision** : **C2** — l'inbox de propositions est une VUE sur l'existant, jamais une seconde autorité : une proposition ouverte EST une notification heartbeat à `habit_offer_id` sans `user_feedback` dans la fenêtre `HEARTBEAT_OFFERS_WINDOW_DAYS` ; `GET /heartbeat/offers` (builder pur testé au SQL, total exact ADR-185) ; décider passe par le endpoint feedback EXISTANT (accepter = 👍 puis chat PRÉREMPLI — rien ne s'envoie seul, HITL intact ; refuser = 👎), les signaux bayésiens ADR-214 continuent d'apprendre ; 6ᵉ section du hub EN TÊTE (un ensemble à décider prime sur les historiques — à montrer au propriétaire) + 6ᵉ badge dans la lecture unique des compteurs ; PULL pur donc aucune garde d'éligibilité. **C4** — budget d'itérations ReAct adaptatif (flag OFF par défaut) : le max configuré devient PLAFOND, budget par tour = base + (domaines−1)×pas depuis l'analyse, calculé au setup dans la clé d'état DÉCLARÉE `react_max_iterations_effective` ; complexité inconnue ⇒ plafond (on n'économise que sur le prouvé-simple, on ne sous-budgète jamais un dur). **B3 intra-run** : le message du garde de répétition exige désormais UNE phrase de diagnostic avant la prochaine action (pas Reflexion au coût zéro — aucun appel LLM ajouté sur chemin d'erreur) ; les leçons inter-sessions restent sur l'extraction `procedural` (ADR-236).

---

### ADR-239 : clôture du programme évolution — requalifications et arbitrages réservés

**Statut**: ✅ ACTÉ (2026-08-20)
**Fichier**: `docs/architecture/ADR-239-evolution-program-closure.md`

**Décision** : inventaire de clôture des 7 lots (ADR-234→238 livrés). **Requalifié avec preuve, aucune action** : C1 (l'ambient événementiel EST ADR-175 — évaluateurs mail/météo/document/calendrier, idempotence par fingerprint `last_fingerprint`, LLM payé au seul déclenchement ; la variante « sans opt-in » est REJETÉE au nom du pilier souveraineté : créer l'action conditionnelle EST le consentement). **Réservé à l'arbitrage propriétaire, évidence prête** : C3 missions à jalons (objet produit nouveau — maquette d'abord), C6 producer-critic (le seul candidat est le chemin auto-approuvé, qui journalise DÉJÀ last_error/consecutive_failures — un critic LLM récurrent sans taux de faux-succès mesuré = coût spéculatif), B5 compilation en skills (la forme sûre existe déjà via P12→scheduled actions ; le contenu d'un skill généré = voix produit, à voir avant livraison), B4 enregistrements de périmètres (sur l'évidence `adaptive_candidate_top_score` qui s'accumule désormais), D3-canal et D5 (ADR-237). Chaque réservé porte son déclencheur écrit.

---

### ADR-240 : widget yeux expressifs — moteur d'expressions pur sur signaux existants

**Statut**: ✅ ACTÉ (2026-08-20)
**Fichier**: `docs/architecture/ADR-240-expressive-eyes-widget.md`

**Décision** : deux yeux cartoon pleins, flottants sur la page chat (déplaçables, redimensionnables S/M/L, masquables → point de restauration), 100 % frontend. Toute l'expressivité dérive de signaux EXISTANTS (FSM du chat + `streaming.phase`, `execution_step` reasoning/outil, HITL, FSM vocale, notifications, psyché) via un moteur pur à table de priorités (20 expressions, RNG et horloges injectés — testé par matrice exhaustive). Réaction par tour : le self-report psyché du `done` (`active_emotions`) d'abord, heuristique de contenu neutre en langue (ponctuation/émoji/structure uniquement, zh pleine chasse inclus) en secours de la course fire-and-forget. Rendu 100 % CSS (`clip-path: polygon()` pour les paupières — indépendant du fond, squash & stretch, désynchronisation G/D 40-80 ms), tout timer coupé si onglet caché, widget réduit ou `prefers-reduced-motion`. Préférences en localStorage (hors registre SEC-035 : préférence d'affichage pure, décision documentée). La météo v1 est ÉCARTÉE (seule source = `/briefing/cards` qui déclenche les 9 fetchers) — un « peek » Redis read-only est la voie v2 documentée.

---

### ADR-241 : migration Python 3.14 / Debian trixie — contrat runtime mono-version

**Statut**: ✅ ACTÉ (2026-08-20)
**Fichier**: `docs/architecture/ADR-241-Python-3.14-Trixie-Migration.md`

**Décision** : toutes les surfaces d'exécution (venv hôte, Docker dev, Docker prod arm64/RPi5, sandbox skills, CI) convergent sur CPython 3.14 (build GIL standard — free-threading et JIT explicitement écartés) et `python:3.14-slim-trixie` : `requires-python = ">=3.14,<3.15"`, le job CI `python-compat` (F041) est retiré (plus de second interpréteur à prouver), l'installateur ADR-215 conserve son plancher 3.10 indépendant. Audit préalable intégral : 229 pins vérifiés wheel par wheel sur PyPI (win_amd64, manylinux x86_64, aarch64), delta de lock prouvé par dry-run = `+audioop-lts==0.2.2` seul (le stdlib `audioop` retiré en 3.13 cassait `import pydub` — voie vocale Telegram — silencieusement, zéro oracle de test). Trixie : dépôt Docker CE `trixie` + 5 renommages time64 (`libasound2t64`, `libcups2t64`, `libatk1.0-0t64`, `libatk-bridge2.0-0t64`, `libatspi2.0-0t64`). Trois gardes de non-récurrence : surfaces de version verrouillées sur le plancher pyproject (falsifiées avant adoption), smoke d'import des wheels natifs (audioop inclus), tests hermétiques de la chaîne audioop de `_ogg_to_pcm_float` (sans ffmpeg, classe ADR-155 respectée).

---

### ADR-242 : fusion hybride RAG — seuil sur le score sémantique, BM25 en bonus borné

**Statut**: ✅ ACTÉ (2026-08-22)
**Fichier**: `docs/architecture/ADR-242-RAG-Hybrid-Fusion-Semantic-Gate.md`

**Décision** : `RAG_SPACES_RETRIEVAL_MIN_SCORE` s'applique désormais au score **sémantique** (0,55 → **0,62**, recalibré sur l'axe brut), et BM25 devient un bonus borné de ré-ordonnancement (`RAG_SPACES_BM25_BONUS_WEIGHT=0.05` remplace `RAG_SPACES_HYBRID_ALPHA`, supprimé) : il peut promouvoir une correspondance de terme exact devant un quasi-ex æquo, jamais admettre ni évincer un chunk. Corrige un défaut de production prouvé sur la base réelle : la normalisation de BM25 **par le maximum du corpus** donnait 1,0 au « moins mauvais » appariement lexical — du bruit pur sur une requête dont la langue diffère de celle des documents — pendant que le seuil, comparé à un score déjà rétréci par α, exigeait en réalité 0,786 de cosinus ; **36 % des bonnes réponses passaient le seuil sémantique puis étaient écartées par la fusion** (« Est-ce que mes données sont chiffrées ? » ne renvoyait aucun chunk). Troisième défaut corrigé : `tokenize_text` réduisait une phrase chinoise entière à **un seul token** (`\w` matche les idéogrammes) — les écritures sans espaces sont maintenant découpées en bigrammes de caractères, sortie inchangée sur les écritures latines. Mesuré sur les corpus réels, 740 requêtes natives : hit@5 fr 0,525→0,867 · de 0,533→0,883 · es 0,425→0,867 · it 0,450→0,842 · **zh 0,208→0,817** · documents zh **0,075→0,887**, avec **moins** de bruit sur les tours hors-sujet (1,25→0,88). **Écarté** : l'union des candidats sur preuve lexicale forte (+14 pts sur les requêtes à jetons rares, mais 1,05→2,75 chunks injectés par tour hors-sujet — le même mensonge un cran plus bas) ; la migration vers `gemini-embedding-2` (ignore `task_type`, +33 % de coût, ~9 % plus lent, ré-embedding total + 9 seuils à recalibrer, et **moins bon** sur la prose française monolingue : R@5 0,800 contre 0,950).

---

### ADR-243 : mode d'affichage OLED — un raffinement du sombre, porté par un attribut, pas un quatrième thème

**Statut**: ✅ ACTÉ (2026-08-23)
**Fichier**: `docs/architecture/ADR-243-OLED-Display-Mode-Refinement.md`

**Décision** : le noir absolu est un **raffinement booléen** du mode sombre, porté par un attribut `data-oled` sur `<html>` et sélectionné par `html.dark[data-oled]` — `next-themes` continue de posséder `light | dark | system`, inchangé. Motif prouvé dans la source du fournisseur : `classList.add` ne prend qu'un seul jeton (une valeur `'dark oled'` lève `InvalidCharacterError`), et `attribute` accepte un tableau mais transmet la même valeur aux deux attributs — aucune configuration ne donne `class="dark"` **et** un marqueur OLED distinct. Un troisième thème aurait donc retiré `.dark`, basculant **9 comparaisons `resolvedTheme === 'dark'`** vers leur branche claire (coloration syntaxique, Mermaid, flocons, portraits) et **9 règles `html:not(.dark) .cosmos'`** vers la variante claire de tout le site public, tout en laissant `color-scheme` périmé. Spécificité choisie pour gagner **quel que soit l'ordre** : `html.dark[data-oled]` = (0,2,1) contre `[data-theme='x'].dark` = (0,2,0) ; exiger `.dark` rend le mode clair immunisé **sans aucun garde applicatif**. Six neutres seulement sont surchargés — chaque accent garde ses couleurs, `border`/`input` héritent du sombre car oklch(32 %) se détache **mieux** sur noir absolu (1,66) que sur le gras sombre (1,48). Surfaces calibrées pour ne rien dégrader : carte/fond 1,10 contre 1,09, bordure/carte 1,51 contre 1,37, vérifiées sur 25 paires × 5 accents. **Piège de cascade** : `lia-components.css` est importé **sans `layer()`**, donc son `.dark` (24 variables `--lia-*`) est hors calque et bat `@layer theme` quelle que soit la spécificité — les surcharges OLED de ces variables doivent vivre dans ce fichier, faute de quoi les cartes restent gris-bleu sur une page noire. **Persistance** : `users.theme` accepte `"oled"` (= sombre + OLED) sans migration, mais le champ **est** validé par un mixin éloigné de sa déclaration — l'oubli produisait un échec **muet** (l'écran devient noir, seul le rechargement révèle le 422) ; une garde inter-couches compare désormais la liste du serveur à celle du frontend. `system + OLED` volontairement non représentable ; le cycle de l'en-tête ne compte que trois arrêts et part de l'apparence **résolue** (lire la valeur stockée classait `system` comme « pas sombre »), les réglages conservant les quatre choix puisque `system` est le défaut de colonne.

---

### ADR-244 : le catalogue de modèles dit la vérité — deux registres publics, une provenance

**Statut**: ✅ ACTÉ (2026-08-24)
**Fichier**: `docs/architecture/ADR-244-LLM-Catalogue-Truth.md`

**Décision** : deux registres publics (LiteLLM, MIT, et models.dev) sont **vendorisés** en un instantané filtré (`task llm:catalogue:fetch`, aucun accès réseau sur un chemin d'exécution), et une colonne `llm_models.capability_provenance` (`declared` / `imported` / `verified`) dit **qui** a rempli les capacités. `get_effective_context_window` arbitre alors au lieu de deviner : une ligne `imported`/`verified` bat `MODEL_CONTEXT_WINDOWS`, une ligne `declared` lui cède. Corrige un défaut vivant : **89 des 114 lignes actives portaient les défauts de colonne** (8192/4096), donc `gpt-5.2` répondait 8 192 contre 272 000 réels — un seuil de compaction à 3 277 jetons au lieu de 108 800 — pendant que la table à la main est fausse sur **10 de ses 56 entrées**. Aucun des deux ne pouvait faire autorité seul. **Verrou fournisseur canonique** : models.dev publie 193 fournisseurs et `deepseek-v4-flash` y apparaît sous 23 d'entre eux avec des plafonds de 32 768 à 1 048 576 — apparier par nom de modèle seul ingère des métadonnées de revendeur. **Quatre familles de champs exclues sur mesure, pas par prudence** : les prix (85 modèles sur 87 stables sur deux mois, les 2 « changements » = artefacts de suivi de palier → 0 vrai positif, 2 faux positifs ; aucun registre ne sait exprimer les créneaux ADR-223), le raisonnement (un import naïf invalide `effort: off` sur 21 slots), le streaming et les 4 drapeaux d'échantillonnage, et le `kind` (le `mode` de LiteLLM nomme la surface d'API, le `kind` de LIA classe le produit : `mode=chat` → `kind=audio` 6 fois sur 103 appariements, divergence légitime). Chaque exclusion est **assertée par un test**. **Précédence par champ, mesurée des deux côtés** : LiteLLM remplit parfois `max_input_tokens` avec la fenêtre TOTALE (6 divergences sur 6 valent exactement `modelsdev.limit.context`), et models.dev met la **dimension du vecteur** dans `limit.output` des embeddings (3072 pour `text-embedding-3-large`) et publie un plafond égal à sa propre fenêtre sur 9 entrées ; les compteurs nuls (5 entrées image, 5 modération) valent absence, jamais valeur. **La désactivation exige corroboration** : sur 71 entrées LiteLLM passé leur date, models.dev en corrobore 1, en ignore 66 et en **contredit 4** — `gpt-5.2-chat-latest` et `gpt-5.3-chat-latest` (alias tournants qu'OpenAI repointe) y compris ; un `status=deprecated` seul ne désactive pas non plus (les 7 lignes concernées portent une date à deux mois). Asymétrie assumée, doctrine `utils/react_budget.py` : désactiver un modèle vivant retombe sur `CONSERVATIVE_DEFAULT` (`is_reasoning_model=False`) et l'adaptateur envoie des paramètres d'échantillonnage à un modèle de raisonnement → 400 ; laisser un modèle mort listé ne coûte qu'une entrée périmée que la garde signale. **Résultat mesuré** : 1 ligne manquante insérée (`gpt-image-2`, épinglée par le seed de configuration mais jamais créée par le seed de catalogue — `ModelCapabilitiesCache` répondait `None`), 3 lignes corrigées, 91 promues `imported`, 40 dates apposées, 14 modèles retirés désactivés, **0 conservé faute de référence** ; `task llm:catalogue:sync` retombe à `AUTO 0 / REVIEW 0`. **Aucun seuil de compaction ne bouge** — `deepseek-v4-flash` (27 slots) reste à 1 000 000 / 400 000. **Quatre bombes à retardement recalées** : `SUMMARIZATION_MODEL_DEFAULT` → `gpt-5.6-luna`, `FALLBACK_MODELS_DEFAULT` → `claude-sonnet-4-6,deepseek-v4-flash` (les deux précédents étaient l'un absent du catalogue, l'autre désactivé — la chaîne de repli n'avait **aucune** cible atteignable), le slot image → `gpt-image-2`, et les **21 slots** sur `gpt-4.1-nano` → `gpt-4.1-mini`, seul candidat à forme de capacité identique (non-raisonnement, accepte `temperature`/`top_p`, même fenêtre 1 047 576) ; `gpt-5-nano`, pourtant moins cher, écarté car modèle de raisonnement refusant les deux paramètres. **`verified` reçoit le producteur qui lui manquait** : `LLMModelService.update` l'appose quand un humain modifie une capacité pilotée par le registre (interface admin et aller-retour Excel ADR-228), la création non — les défauts non touchés du formulaire sont exactement ce que `declared` signifie. **Cinq gardes**, chacune vérifiée rouge sur correctif annulé, dont la postcondition SQL référentielle qui manquait à `verify_reference_seeds.sql` (des cardinalités seules, sans même compter `llm_models`). **Résidu déclaré, pas masqué** : les deux registres divergent sur le plafond de sortie de 25 modèles sur 143, sans motif structurel.

---

### ADR-245 : une intention de raisonnement, un traducteur, une autorité par question

**Statut**: ✅ ACTÉ (2026-08-26)
**Fichier**: `docs/architecture/ADR-245-Reasoning-Unification.md`

**Décision** : les **quatre formes stockées** de `reasoning_effort`, aiguillées par la colonne `llm_models.reasoning_widget` et lues par **sept constructeurs**, sont remplacées par **une seule** — `ReasoningIntent(level, budget_tokens, exclude_from_output)` — plus un `ReasoningProfile` dérivé de `(provider, model)` et un `translate` à une fonction par famille. Trois autorités devaient s'accorder pour qu'un appel parte (la colonne, la forme du JSONB, le `isinstance` du constructeur) ; leur désaccord produisait un `RuntimeError` **sur le chemin chaud**, pour une configuration que l'interface admin avait acceptée. Défauts mesurés avant correction : **21 slots stockaient `{"effort": "off"}` et 6 `{"effort": "none"}`** pour dire la même chose ; l'interface proposait `minimal` sur `gpt-5.2` que l'API d'OpenAI refuse (elle publiait les colonnes du catalogue pendant que l'écriture validait autre chose) ; et `llm_config_overrides.effort` alimentait **le même kwarg Anthropic** que `reasoning_effort`, `additional_kwargs.update()` décidant du gagnant par ordre de dictionnaire (aucun slot configuré ne l'utilisait — canal supprimé). **L'échelle est ordinale et indépendante du fournisseur** (`provider_default < none < minimal < low < medium < high < xhigh < max`), `provider_default` étant l'identité : elle ne produit **aucun** kwarg et n'est jamais cible de coercition. **Contrat de coercition, sûr par construction** : les égalités tranchent **vers le haut** (le moins cher sous-livre en silence, le plus cher se voit dans les coûts) ; `none` n'est **jamais** une cible ; et c'est **`can_disable`, pas l'appartenance à l'échelle**, qui gouverne l'extinction — une ligne de catalogue restreint les **profondeurs** (`claude-opus-4-6` déclare `["low","medium","high","max"]`) sans signifier « et on ne peut plus l'éteindre », si bien que lire l'échelle ici aurait **activé** le raisonnement sur un `none` explicite. Chaque coercition est **comptée et journalisée** (`llm_reasoning_coerced_total{model,from_level,to_level}`) : ce n'est pas une erreur, mais le modèle ne fait pas ce que l'admin a demandé. Le **rejet** reste sur le chemin d'écriture, où un humain peut corriger, et répond à **une seule** question via `resolve_reasoning_profile` — la fonction qu'utilise aussi le traducteur, donc validateur et traducteur ne peuvent plus diverger. `GET /llm-config/metadata` publie désormais le **profil résolu** (famille, échelle, `can_disable`, budget, exclusion) et non les colonnes : doctrine ADR-184 appliquée au raisonnement. `reasoning_supports_exclude` est **dérivé des rendus eux-mêmes** (rendre deux fois, comparer), donc l'interrupteur ne peut pas survivre au kwarg. **Migration `d3e4f5a6b7c8` sans jour J** : les deux modèles Pydantic lisent encore les formes héritées, donc prendre le code avant la migration ou l'inverse fonctionne ; le mapper est partagé par la migration, les seeds de référence et la preuve d'équivalence, et il est **total sur sa propre sortie** (rejouer un seed ne ré-encode rien). **Simulé sur données réelles avant écriture** : 36 lignes stockées, 29 défauts de code, **1 290 combinaisons (modèle × forme), 0 divergence** de kwargs ; **preuve permanente** `golden_kwargs.json` **54/54 identiques**. Le **downgrade ne reconstruit pas** les formes héritées (une intention ne dit pas de laquelle des quatre elle vient) : échec bruyant plutôt que mauvais mode silencieux. Colonnes `reasoning_widget` / `reasoning_budget_range` d'abord **rétrogradées**, puis **supprimées** en v1.32.0 (migration `f5a6b7c8d9e0`, plus le type énuméré qui n'avait plus qu'elles) : le formulaire continuait de les offrir à l'édition sans dire qu'elles ne décidaient plus rien — un champ curable que rien ne lit est pire que son absence. La règle de cohésion part avec elles (sa dernière clause interdisait la ligne la plus utile qui soit : « ce modèle raisonne, voici ses profondeurs »). Survit ce que la résolution lit : `reasoning_enum_values`, dont le **vocabulaire a dû être normalisé** — 4 lignes déclaraient encore `off`, et l'intersection produisait une échelle **sans interrupteur** que seul `can_disable` rattrapait (migration `e4f5a6b7c8d9` + garde de seed).

---

### ADR-246 : notifier un téléphone dont l'app ne vous appartient pas

**Statut**: ✅ ACTÉ (2026-08-24)
**Fichier**: `docs/architecture/ADR-246-Native-Push-And-Wake-Relay.md`

**Décision** : les coques natives étant publiées **une fois par store** et pointées vers le serveur de chacun, le push casse de façon **asymétrique**. **Android va bien** : FCM identifie un émetteur par *projet*, pas par éditeur, donc l'app initialise Firebase **au démarrage** avec les options que son propre serveur publie (les quatre valeurs que tout APK embarque déjà) et reçoit du projet **que ce serveur possède** — rien ne transite par l'éditeur ; embarquer un `google-services.json` aurait fait l'inverse. **iOS ne le peut pas du tout** : FCM n'atteint un iPhone que par APNs, qui authentifie un fournisseur avec une clé délivrée à l'équipe Apple **propriétaire du bundle id**, et une clé `.p8` vaut pour **toutes** les apps de l'équipe — la distribuer donnerait à chaque auto-hébergeur un droit de push sur le compte entier. Aucun réglage ne corrige cela. Conséquence mesurée sur le produit existant : **la PWA iOS reçoit déjà des push** (iOS 16.4+, écran d'accueil), donc une app iOS muette aurait été **en retrait de ce que les utilisateurs ont**. Arbitrage du propriétaire : **relais de réveil**. **Un contrat d'acquisition, deux routes** — `GET /notifications/push-config` répond par plateforme, la couche web transmet la réponse **entière** au shell et ne lit jamais un champ spécifique à une plateforme ; `null` est une vraie réponse, affichée (enregistrer un jeton que rien n'enverra ressemble exactement à un fonctionnement, jusqu'à la première notification absente). **Le relais est un mode de l'API**, `PUSH_RELAY_ENABLED` par défaut faux, servi par **exactement un** déploiement ; `PUSH_RELAY_URL` n'a **aucun défaut** (ce serait une décision de vie privée prise par une constante) et l'activer sans ses identifiants **refuse de démarrer** — un relais à moitié configuré accepte les enregistrements et rate tous les envois, ce qui se lit « le relais est en panne » d'un côté et « les notifications ne marchent pas » de l'autre. **Le relais ne porte aucun contenu et ne stocke rien** : une phrase fixe, table sans paramètre, six langues ; la poignée **est** le chiffré authentifié du jeton d'appareil, scellé par une clé Fernet délibérément distincte de `fernet_key` (la faire tourner invalide toutes les poignées d'un coup sans rechiffrer une seule colonne de connecteur), deux scellés d'un même appareil diffèrent (deux serveurs ne peuvent pas corréler leurs poignées) et elles expirent — le shell se réenregistre à chaque lancement, l'expiration se soigne seule. **Ce que le relais apprend malgré tout, écrit et non masqué** : qu'un appareil a été réveillé, quand, et l'IP du serveur demandeur. **La route voyage avec le jeton** (préfixe `relay:`) et non avec la configuration : un déploiement peut légitimement avoir les deux, et seul le shell **sait** laquelle il a empruntée. **Le doute n'efface jamais** : `should_forget_handle` n'est vrai que pour les deux verdicts qu'un réessai ne peut pas corriger ; un relais injoignable, un 5xx, un 429, une réponse illisible ou **un `apns-topic` que nous avons mal saisi** conservent la poignée — garder une poignée morte coûte un appel HTTP par notification, en jeter une vivante fait taire un téléphone jusqu'au prochain lancement, et une seule variable fausse de notre côté le ferait à tout le monde d'un coup. **iOS parle à Apple directement** (JWT ES256, HTTP/2 ; `h2`, `httpx`, `pyjwt`, `cryptography` déjà présents — **zéro nouvelle dépendance**) et n'embarque **aucun SDK Firebase** : une quarantaine de lignes de Swift. **L'enregistrement est natif des deux côtés** pour une raison déjà apprise : la page tourne sur l'origine du serveur de l'utilisateur, appeler un relais en JavaScript est cross-origin, et un relais servant tous les auto-hébergeurs ne peut pas énumérer leurs origines dans une politique CORS — c'est le même raisonnement qui avait déjà déplacé la sonde de santé dans le shell. **L'écran hors-ligne est groupé** (`server.errorPath`) : la page d'ADR-146 ne peut pas atteindre le shell iOS (`navigator.serviceWorker` absent de WKWebView, mesuré), et sans elle l'utilisateur voit l'erreur de WebKit dans une app ; elle propose un réessai qui **reconstruit le pont** et surtout un moyen d'**oublier** le serveur — une adresse mal saisie au premier lancement produit sinon cet écran à chaque démarrage, sans autre remède que réinstaller. **Le retour des flux OAuth suit la même doctrine** : les huit départs vers un fournisseur passaient déjà par `navigateToAuthorizationUrl` (garde SEC-002), donc la décision « partir vers le navigateur système » y est prise **une fois** — ce qui a **supprimé** le cas particulier que la connexion avait acquis. Et le retour se souvient de la surface : `OAuthFlowHandler.initiate_flow` est **la seule** fonction du dépôt qui construise un état OAuth, donc un connecteur ajouté demain hérite du comportement sans que son auteur sache que le marqueur existe — l'alternative était un booléen à faire passer par douze méthodes de service, où en oublier une échoue **en silence, un connecteur à la fois**. Le drapeau arrive par `ContextVar` depuis un en-tête `X-LIA-Native` ; le coût est énoncé et non masqué (un préflight CORS par méthode et par chemin toutes les dix minutes **dans la coque seulement**, contre une liste blanche de chemins OAuth côté web, qui pourrit). Le marqueur est **absent** pour un flux navigateur, pas `False` : un champ qui existe est un champ qu'on lit mollement, et l'échec serait un utilisateur de bureau redirigé vers un `lia://` que sa machine ne sait pas ouvrir. Le MCP a son propre gestionnaire et son propre espace Redis : même traitement par les mêmes briques, sinon la dépendance posée sur son routeur aurait été du code mort qui ressemble à une fonctionnalité. **`is True`, pas la véracité** : appelés directement par des tests unitaires, ces rappels reçoivent l'objet `Depends` — qui est *truthy* — et auraient pris le chemin du lien profond dans un navigateur ; un test MCP existant l'a fait échouer, c'est ainsi que le défaut a été trouvé. **Corrigé en chemin** : dix rappels construisaient leur redirection de succès à la main, ils en partagent une ; les trois marqueurs MCP étaient des fragments de requête tout faits (`"mcp_oauth=success"`) qu'un lien profond aurait encodés comme **une seule valeur opaque** ; et la fabrique de limitation par IP quitte `domains/auth/dependencies` pour `infrastructure/rate_limiting/ip_limiter` en gardant ses clés Redis **octet pour octet** (quatre domaines sans rapport importaient leur limiteur du domaine auth) ; `_get_client_ip` et son test doublon partent avec elle, tous deux redisant moins complètement, et sur une prémisse depuis réfutée, ce que `core/client_ip.py` documente déjà.

---

### ADR-247 : un assistant qui lit sa propre télémétrie

**Statut**: ✅ ACTÉ (2026-08-28)
**Fichier**: `docs/architecture/ADR-247-Self-Diagnostics-And-Answer-Resilience.md`

**Décision** : LIA émettait une observabilité complète (métriques Prometheus, logs structlog dans Loki, cœur d'alertes ADR-119 avec runbooks) et n'en **lisait rien** — instrumentée et aveugle sur elle-même : un job de fond mort n'atteignait personne, une alerte partait en e-mail mais jamais vers LIA ni un admin dans le produit, et un run en échec ne pouvait ni s'expliquer honnêtement ni contourner une panne pourtant connue. Un bounded context `domains/diagnostics/` + une couche de lecture `infrastructure/telemetry/`, le tout derrière `DIAGNOSTICS_ENABLED` (défaut **faux** : drapeau éteint, le sous-système n'existe pas). **La lecture ne lève jamais** : clients Prometheus/Loki/Alertmanager à timeouts courts, disjoncteur par source, tout échec devient un résultat typé `unavailable` ; une URL vide désactive la source, donc une installation sans stack d'observabilité est inchangée. **Aucun langage de requête libre, jamais** : un catalogue de requêtes nommées (assert de complétude au boot, patron ADR-085) est le seul producteur de PromQL — paramètres typés, bornés et **publiés** dans les manifestes (doctrine ADR-184) — et un constructeur contraint le seul producteur de LogQL (enum de services fermé, niveaux fermés, motif d'event strict, plafonds de plage et de lignes en constantes) : c'est ce qui protège Loki (historique d'OOM sur le Pi) et ferme l'injection par construction. **Boucle d'auto-contrôle déterministe** (leader élu) : registre déclaratif de contrôles — signaux dorés Prometheus + sondes in-process qui continuent quand Prometheus est mort — vers des instantanés persistés aux valeurs exactes ; `unknown` plafonne le verdict global à `degraded` (être aveugle n'est pas être sain, et la cécité n'est pas une panne). **Mémoire d'incidents à identité unique** : les livraisons Alertmanager (webhook Bearer injecté depuis des fragments commités, matrice rejouée en CI) et les verdicts critiques de l'auto-contrôle convergent vers UN incident ouvert par clé de corrélation — index unique partiel, upsert open-or-touch atomique sous la concurrence webhook-vs-leader ; notification des superusers in-app/push (jamais d'e-mail — Alertmanager le fait déjà) derrière un cooldown `SET NX EX` atomique qui échoue **ouvert**. **Diagnostic LLM ancré et budgété** : pompe pull sur le même tick, slot `diagnostician` dédié, preuves et runbook cités comme données, budget USD par jour UTC via un `INCRBYFLOAT` (0 = étape désactivée), incident sauté = diagnostic NULL donc réessayé ; **aucune action automatique ne dérive du texte du LLM**. **Surfaces admin uniquement** : quatre outils de chat en lecture seule (check superuser à l'appel — patron DevOps, via une garde partagée extraite de lui), REST `require_superuser`, section Réglages « Santé de la plateforme » (i18n ×6), comptes exacts partout. **Résilience de la réponse** : un advisor fail-open transforme incidents ouverts + disjoncteurs ouverts du worker en bloc de dégradations injecté au planner/ReAct **seulement s'il est non vide** (zéro token sur plateforme saine) ; l'extraction typée des échecs se fait sur ce que le run porte déjà (`completed_steps`, ToolMessages ReAct — délibérément **aucune clé d'état nouvelle**) et alimente une directive d'honnêteté dans la synthèse (ADR-182/184 tenus : l'explication dérive des codes typés, jamais des logs bruts). **Le graphe de domaines reste acyclique** : diagnostics n'importe jamais agents — les templates de prompt sont **injectés par les appelants** (adaptateur du response node, job du scheduler), ce que le ratchet de cycles F009 verrouille. `health_snapshots` et `incidents` sont **GLOBAL** (aucune donnée utilisateur ; hors export RGPD et purge de compte). Différés derrière des critères d'escalade **mesurés** (spec §3) : PromQL/LogQL libres, lecture Tempo, détection d'anomalies par baseline, auto-remédiation Tier-1 — les coutures d'extension existent, le code volontairement pas.

---

### ADR-248 : le budget ReAct s'achète avec des résultats, et la boucle connaît enfin les règles de l'utilisateur

**Statut**: ✅ ACTÉ (2026-08-28)
**Fichier**: `docs/architecture/ADR-248-React-Memory-Parity-And-Progress-Earned-Budget.md`

**Décision** : un tour de production a révélé trois défauts d'un coup. À une question sur les durées d'escale, LIA a répondu « je plonge dans tes emails, donne-moi une minute » — et le tour s'est arrêté là. Les logs contredisent la lecture évidente : **elle agissait bel et bien**, six itérations, six appels d'outils, coupée par son budget. **(1) Une promesse servie comme réponse** : `react_finalize_node` prenait le contenu du DERNIER `AIMessage`, lequel, sur une sortie par plafond, porte encore des `tool_calls` **non exécutés** — sa phrase est la narration de ce que le modèle allait faire. Désormais un message porteur d'appels en attente n'est jamais une réponse : `final_message` vide (le chemin qu'emprunte déjà le handoff de brouillon), la synthèse repart des résultats réellement obtenus, et la raison de l'arrêt voyage jusqu'à une directive versionnée qui impose de dire ce qui a été trouvé, d'annoncer l'interruption en une phrase, de proposer la suite — et **jamais d'annoncer un travail futur, puisqu'un tour se termine quand sa réponse part**. Cette directive n'est **pas** conditionnée à `DIAGNOSTICS_ENABLED` : dire la vérité sur son propre run est une question de qualité de réponse, pas d'observabilité. La condition d'arrêt devient **un seul prédicat** (`react_exit_reason`), lu par le routeur pour décider et par la finalisation pour expliquer — deux copies laisseraient la boucle s'arrêter pour une raison que la réponse ne mentionne jamais. **(2) Un budget qui mesure la mauvaise grandeur** : ADR-238 dimensionne l'allocation sur le SPAN de domaines, qui dit la LARGEUR d'une question et rien de sa PROFONDEUR — une enquête mono-domaine recevait donc le minimum. L'allocation adaptative devient l'allocation **initiale** : chaque fois que la boucle atteint son budget en l'ayant dépensé **productivement**, elle en gagne un bloc de plus ; une boucle qui cesse de produire cesse d'être prolongée. *Productif* signifie que le contexte a appris quelque chose — ni `success: false`, ni résultat vide : une tentative n'est pas une production, sinon la boucle achèterait des itérations avec ses propres échecs. Le plafond dur (`react_agent_max_iterations`) et le budget de calcul restent inchangés. **(3) Aucune mémoire dans la boucle** : `injected_memories` était déclarée dans `MessagesState`, **lue** par le setup ReAct et **écrite par personne** dans tout le dépôt — la boucle raisonnait sans mémoire, tandis que le profil psychologique n'atteignait que le nœud de réponse, où la réponse ReAct est déjà *autoritaire* (une règle y arrivant peut reformuler une promesse, jamais la transformer en action). Le setup injecte désormais le profil via `build_psychological_profile`, **le même constructeur que le pipeline**, mêmes réglages, même filtre de trivialité, même préférence utilisateur — exactement le traitement déjà appliqué aux directives de journal. La clé morte est supprimée plutôt que laissée comme un crochet crédible, et l'assemblage du contexte devient `nodes/react_context.py` : un constructeur par bloc, chacun best-effort, chacun rendant `None` quand il n'a rien à dire.

---

### ADR-249 : l'agent peut écrire et exécuter un script, dans le bac à sable qui existait déjà

**Statut**: ✅ ACTÉ (2026-08-29)
**Fichier**: `docs/architecture/ADR-249-Ephemeral-Python-In-The-Existing-Sandbox.md`

**Décision** : un modèle répond de façon *plausible* à l'arithmétique sur beaucoup de lignes, aux jointures par clé, aux durées entre fuseaux et à la déduplication — et l'utilisateur n'a aucun moyen de voir que c'est faux. Un script de cinq lignes, lui, donne une réponse vérifiable. La capacité nécessaire existait déjà, construite pour autre chose : le bac à sable des skills (SEC-001) — un conteneur jetable par exécution, sans socket Docker, `--network none`, rootfs en lecture seule, uid 65534, toutes capacités abandonnées, mémoire/pids/CPU bornés, source passée **en ligne** donc rien de monté, et stdin libre pour une charge JSON. **Mesuré sur le Pi de production avant toute décision** : 279 ms de démarrage à froid, 459 ms avec numpy — moins de 2 % du budget de 30 s. La question n'a donc jamais été de construire un bac à sable, mais de savoir si le **modèle** peut écrire ce qui y tourne, et sous quelles règles. **(1) L'agent décide** : l'outil est offert, jamais imposé ; le prompt ReAct dit ce que le modèle fait mal et l'invite à calculer là — et lui dit aussi explicitement de ne PAS s'en servir pour une recherche simple ou un calcul à deux nombres, sans quoi un outil capable devient un marteau. **(2) ReAct uniquement** (arbitrage propriétaire — le pipeline utilise skills et plugins) : le pipeline planifie à l'avance et ne peut pas lire une trace d'erreur pour réparer un script. Deux applications, car une seule serait un piège : le **manifeste** déclare `execution_modes={"react"}` et tout lecteur de la liste applique `manifests_for_mode` — le planner ne VOIT jamais l'outil, sinon il planifierait une étape refusée à l'exécution, c'est-à-dire une impasse inventée pour l'utilisateur ; et l'**outil** revérifie `execution_mode` à l'appel (le runtime typé d'ADR-231 portait déjà le mode, aucune plomberie nouvelle). **(3) Le mode bac à sable hérité est refusé** : il n'isole que si l'API tourne en root, compromis acceptable pour du code que l'utilisateur a installé, inacceptable pour du code qu'un modèle a écrit **en lisant un email**. Échec fermé, jamais de repli silencieux. **(4) Les données sont transmises, pas recopiées** : ce que les outils du tour ont déjà collecté arrive sur **stdin** en JSON ; recopier dans la source paierait les tokens deux fois et tronquerait précisément les gros cas qui justifient la fonctionnalité. **(5) Tout ce qui est imposé est publié** (ADR-184) : pas de réseau, pas de base, pas de système de fichiers hors `/tmp`, la liste exacte des bibliothèques et les budgets — sinon le modèle brûle une itération à le découvrir. **(6) Ce qu'une injection peut faire** : un conteneur sans réseau, sans identifiants, sans base et sans écriture ; au mieux imprimer du texte au modèle — ce que l'email hostile faisait déjà. La sortie est donc marquée `content_trust: "untrusted"` avant de rentrer dans le contexte. Exposition résiduelle **consignée et non masquée** : l'image du bac à sable est celle de l'API (c'est ce qui donne numpy et openpyxl), donc un script peut lire le code source — dépôt public, divulgation nulle, mais c'est un fait. **(7) pandas est ajouté, et numpy enfin déclaré** — sur mesure et contre l'intuition initiale : l'image fait 3,76 Go donc pandas pèse ~1,5 %, et **toutes** ses dépendances dures (numpy, dateutil, pytz, tzdata) étaient déjà présentes ; le verrou s'est résolu **sans montée de numpy**. Au passage, `numpy` était importé par quatre modules applicatifs sans être déclaré nulle part — une vraie violation d'entrée de build, corrigée. **(8) Le code est visible des administrateurs, et d'eux seuls** (arbitrage propriétaire) : les scripts du tour voyagent jusqu'au panneau de debug, jamais vers la réponse — les cacher entièrement n'achèterait aucune sécurité (le modèle les a écrits, ils sont déjà dans son contexte) et coûterait toute la vérifiabilité, qui est la raison même de préférer un script au calcul mental.

---

### ADR-250 : une connexion perdue n'est pas un déploiement raté

**Statut**: ✅ ACTÉ (2026-08-29)
**Fichier**: `docs/architecture/ADR-250-Detached-Deploy-And-Honest-Remote-Verdicts.md`

**Décision** : le pilote de déploiement se terminait sur un message d'erreur que l'opérateur avait appris à ignorer — le skill `lia-deploy-prod` l'écrivait noir sur blanc sous « **the exit code lies** » : `task deploy:prod` finit sur une session SSH réinitialisée **même quand le déploiement réussit**. Une consigne écrite demandant à un humain d'ignorer une erreur n'est pas un contournement, c'est le défaut déplacé dans la prose ; et il avait **deux causes indépendantes**. **(1) `ssh` réutilise un code pour deux événements sans rapport** : mesure du 2026-08-29, il propage fidèlement tout code distant (`exit 7` → 7, `exit 1` → 1) **sauf 255**, qu'il emploie aussi pour ses propres échecs de transport (hôte injoignable → 255, `ProxyCommand` cassé → 255). Sur 255, et sur lui seul, l'appelant ne sait **rien**. La règle vit désormais dans **une** bibliothèque (`lib/RemoteExit.ps1`) que les deux pilotes consomment — deux copies auraient divergé, et l'opérateur aurait appris deux fois ce qu'est une coupure ; les codes hors plage sont classés **échecs distants**, car les baptiser « coupure » serait exactement le diagnostic inventé qu'ADR-182 supprime. **(2) Le déploiement ne survivait pas à sa propre connexion** : onze minutes de travail (mesure v1.37.0, build 08:38:18Z → readiness 08:49:12Z) tenaient dans une session bloquante ; tuer le client fait mourir le script distant par **SIGPIPE (exit 141) en ~6 s** — pas au bout des 6 min 15 de keepalive, immédiatement — et sur un des deux essais **aucun verdict n'a même été écrit**. Le travail est donc **détaché** et son verdict **lu dans un fichier que le distant a écrit**, jamais déduit d'un code de transport. Le détachement ne s'obtient pas naïvement : **quatre formes ont échoué** (`nohup`, `+disown`, `setsid`, `setsid` sans `&`) parce que `&` met la **liste entière** en arrière-plan dans un sous-shell qui conserve le canal, alors que la redirection ne couvre que la dernière commande ; les **trois** flux doivent être redirigés, un seul descripteur laissé ouvert maintenant `ssh` jusqu'à la fin. Trois propriétés payées par une mesure : **guillemets simples structurels** autour du corps détaché (en guillemets doubles le shell EXTERNE expanse `$?` et le verdict valait **toujours 0**, y compris pour un script sorti en 23 — aucune vérification de forme ne l'aurait vu) ; **artefacts par exécution, donc aucune purge** (la forme précédente détruisait le journal du déploiement **en vol**, 3 lignes → 0, le premier processus continuant d'écrire dans un inode délié) ; **journal dans un fichier**, écrire sur le canal étant précisément ce qui tue le distant. Un seul déploiement à la fois par `flock` **pris par le processus détaché** (verrou noyau, donc libéré même si le processus est tué : pas de verrou fantôme) ; la vivacité est sondée **par le verrou** et non par `pgrep -f`, qui matche sa propre ligne de commande (deux diagnostics se sont auto-comptés, une commande de nettoyage s'est tuée elle-même). **Six issues, parce que six conduites différentes** : `RemoteFailure` est la **seule** où « le déploiement a échoué » est une phrase vraie (le code a été écrit par le serveur) ; `Busy` signifie qu'il **n'a pas eu lieu** ; `Interrupted` qu'il s'est arrêté en chemin ; `Unknown` qu'on a **cessé de regarder** ; `LaunchFailed` ne prouve que rien n'a démarré **que si son code est non ambigu** — sur 255 l'hôte a pu forker le travail avant de perdre le canal. Deux règles rendent la machine honnête plutôt que bavarde : **un sondage qui échoue est réessayé**, jamais converti en verdict, et **le `.rc` prime sur l'état du processus** (l'écrit gagne sur l'observé) ; un `.rc` illisible n'est pas un zéro. Les quatre chemins sans conclusion impriment les **mêmes trois commandes** pour trancher et disent tous **ne pas relancer** — l'étape 7 effacerait le staging sous un build en vol. Le budget de scrutation est un **paramètre** (`-DeployBudgetSeconds`, 2700 s) : un verdict prudent qu'on ne peut pas allonger est un verdict qu'on apprend à lire comme une panne. **(3) SEC-040, conséquence directe** : `PROD/.env` est la production **en clair**, l'étape 10 la supprime mais ne tourne que sur le chemin nominal — or **le chemin nominal était le chemin d'échec**, donc la fuite était systématique : **434 Mo de bundle** ont survécu à un déploiement réussi (2026-07-28). Un `finally` de premier niveau couvre les 14 sorties prématurées (PowerShell l'exécute sur `exit` comme sur `throw`, code de retour préservé, vérifié sur 5.1 **et** pwsh 7) ; la liste est **exacte, jamais un glob** (`provenance.env` vit au même endroit, n'est pas un secret et quatre tests le lisent) ; et il y a **deux ensembles** dont la différence est le sujet — la purge pré-transfert exclut délibérément `.env.prod`, que l'étape 4 doit encore renommer ; les confondre expédie un bundle **sans fichier d'environnement**. Le nettoyage est **chirurgical** (un `Remove-Item PROD` détruirait le bundle qu'on inspecte après un échec) et parle en `Write-Success` : rien ne s'est mal passé **ici**, et sur un chemin d'échec c'est même la seule bonne nouvelle. **Piège consigné plutôt que seulement corrigé** : `GetNewClosure()` recopie dans la closure toute variable visible à sa création, **`$LASTEXITCODE` compris** — la lecture nue rend la valeur **gelée**, pas celle que `ssh` vient de poser (mesure : 0 en nu, 255 en `$global:`, pour le même appel). Le harnais l'a montré en silence : un lancement dont la connexion tombait était rapporté **réussi**, soit exactement le verdict lu au mauvais endroit que cet ADR supprime.

---
### ADR-251 : la couleur ne sépare pas une forme répétée

**Statut**: ✅ ACTÉ (2026-08-30)
**Fichier**: `docs/architecture/ADR-251-Settings-Group-Tones-A-Measured-Fixed-Palette.md`

**Décision** : la coquille des réglages (ADR-227) liste **53 sections** sous **12 groupes**, dans deux surfaces — les cartes de la vue d'ensemble et le rail permanent. Les 53 dessinaient le même glyphe en `text-primary` sur la même pastille `bg-primary/10`, et l'audit du registre d'icônes a trouvé **16 sections portant le dessin d'une autre** (`Plug` servait quatre fois). L'œil n'avait donc qu'**une forme répétée dans une couleur répétée** pour naviguer cinquante-trois entrées, et la recherche (ADR-172) restait la seule vraie prise — or on cherche quand regarder a échoué. **(1) Deux défauts, deux correctifs, et la couleur n'en est pas un** : deux prises restent deux prises même en deux couleurs, donc les collisions de glyphes ont été corrigées **d'abord et séparément** ; la teinte s'ajoute à une liste déjà lisible sans elle. Une collision subsiste, écrite dans le registre : les deux exports de consommation partagent un composant qui se branche sur son mode, et ils vivent dans des onglets différents. **(2) Une teinte par GROUPE, jamais par item** : douze couleurs sont une carte que l'œil apprend, cinquante-trois seraient un bruit qu'il déchiffre — et personne ne retient cinquante-trois paires teinte↔sens. `toneForSection` est la **règle unique** partagée par la carte et la ligne du rail : deux lectures laisseraient les deux listes se contredire sur une section ; un appelant hors table retombe sur l'accent, jamais sur rien. **(3) Des tokens, pas des classes utilitaires** : la palette est **fixe**, hors du thème choisi — deuxième dérogation du produit après le badge cyan des skills, assumée, car une carte dont les couleurs suivent une préférence n'est pas une carte. Écrite en couleurs Tailwind littérales elle serait tombée **hors** de la garde de contraste, qui lit des paires de tokens : c'est exactement le trou que `badge.tsx` consigne pour les variantes fixes qu'il a supprimées. En `--color-settings-*` elle y entre par construction — 24 tokens, 12 en clarté 55 %, 12 en 72 % sous `.dark`, deux clartés obligatoires car une seule ne peut pas franchir 3:1 sur une carte quasi blanche **et** une carte quasi noire. **(4) La mesure a contredit l'intuition deux fois** : le gamut sRVB n'est pas un cylindre (à clarté 55 %, un violet porte 0,25 de chroma, un sarcelle 0,09), si bien qu'un chroma unique plaçait **6 des 24 teintes hors sRVB**, écrêtées en silence par le navigateur — ni la teinte ni le chroma écrits n'étaient rendus, et la promesse même que la clarté fixe existe pour tenir tombait ; et un espacement régulier de 30° n'est pas un espacement **perçu** : une fois le chroma soumis au gamut, deux couples se retrouvaient à **0,116**, sous le plancher de 0,12 que la garde impose elle-même. Les douze angles sont donc **cherchés**, sur le **pire des deux modes** — les deux clartés découpent des tranches différentes du gamut, et un jeu optimisé sur le seul thème clair laissait encore une paire à 0,113 en sombre. Paire la plus proche : **0,199**. Les deux faits sont **gardés, pas retenus** : la garde mesure les teintes sur les deux fonds qu'elles occupent réellement — la pastille (teinte à 12 % sur `card`) et le rail nu (`background`, plus le mélange de survol `accent/60`) — sur les 15 palettes, pire cas **3,64** sur pastille et **3,45** au survol pour un plancher de 3,0 (le glyphe est un objet graphique non textuel, WCAG 1.4.11 : le plancher est 3:1, pas 4,5). **(5) La couleur n'est jamais un état** (WCAG 1.4.1) : la ligne ouverte garde son fond, sa graisse et l'encre d'accent, et une capacité active reste une pastille pleine ou creuse — qui ne perçoit pas ces douze teintes ne perd **aucune** information. **(6) L'en-tête de la section ouverte garde l'accent**, conséquence acceptée et non découverte : `apps/web/CLAUDE.md` veut qu'une icône de titre soit en couleur du thème, et un en-tête de section est un titre ; les deux surfaces ne sont jamais affichées ensemble.

---


### ADR-252 : une transition n'est pas une interprétation

**Statut**: ✅ ACTÉ (2026-08-31)
**Fichier**: `docs/architecture/ADR-252-Expressive-Eyes-Animation-Rig.md`

**Décision** : le widget des yeux (ADR-240) avait atteint un plafond **structurel**, pas un plafond de réglage — **tout changement d'état était une `transition` CSS entre deux poses figées**, et une transition interpole en ligne droite. Cela exclut par construction l'**anticipation** (aucun contre-mouvement ne peut précéder l'action), les **arcs** (le regard voyageait sur un rail, un seul `translate`, une seule courbe), le **chevauchement** (paupières, masse et silhouette partaient à la même frame sur la même courbe), le **squash lié à la vitesse** (le seul écrasement disponible était gelé dans des keyframes) et surtout la **continuité à l'interruption** : une transition coupée en vol repart de là où l'interpolation se trouvait et **perd sa vélocité** — c'est celle que le spectateur ressent sans pouvoir la nommer, changer d'émotion en plein mouvement ressemblait à une interface qui coupe une transition, pas à une créature qui change d'avis. Deux autres plafonds : la **matière** (un aplat et un halo — le plus fort indice qu'une forme est une forme et non une chose) et le **vocabulaire** (le « sourcil » était l'inclinaison de l'œil, et il n'y avait pas de pupille hors d'un point décoratif dans un style). **(1) Le TypeScript possède ce qui BOUGE, le CSS ce qui est DESSINÉ** : un rig publie le mouvement en propriétés `--rig-*` à chaque frame, la feuille de style garde silhouette, peau, matière et l'identité des six styles. La frontière est **une règle greppable** — une feuille *lit* `--rig-*`, n'en *déclare* jamais, et ne pose jamais de `transition` sur une propriété que le rig écrit — donc **gardée par test**, y compris deux choses qu'un commentaire ne peut pas tenir : chaque `--rig-*` lu est un canal réel, et chaque `var(--rig-x, repli)` a un repli **égal à la valeur de repos du canal** (ces replis sont ce qui rend la pose neutre avant la première frame, et leur dérive serait invisible). Le DOM porte deux vocabulaires : `data-*` = l'**état** déclaré, `--rig-*` = le **mouvement** calculé. **(2) Trois mécanismes qui COMPOSENT** : des **ressorts analytiques** (solution fermée de l'oscillateur amorti — un onglet en arrière-plan rend un `dt` en secondes et un intégrateur numérique explose ; exact à tout `dt`, et **la vélocité survit au changement de cible**) ; des **bandes de clés** qui couvrent d'un seul mécanisme ce qui en demandait quatre (anticipation, clignement, battements ponctuels, chorégraphies d'arrivée), les clés étant **maintenues** et non interpolées, si bien que le ressort entre deux clés dessine la courbe ; des **boucles additives** pour le mouvement qui n'arrive jamais (souffle, tremblement, dérive) — elles devaient quitter le CSS car un `@keyframes` **remplace** la propriété qu'il anime, donc une boucle et une pose ne pouvaient jamais partager un transform. **(3) Les principes d'animation deviennent des mécanismes** : préréglage de ressort par émotion (dérivé des durées remplacées, `f = 1,057 / t99`), anticipation **sautée pour les réflexes** (un sursaut qui se télégraphie n'est pas un sursaut), départs échelonnés par groupe autant que les arrivées, biais vertical proportionnel à la vitesse horizontale (nul aux deux bouts, maximal à mi-course), squash à volume constant dérivé de la vélocité des ressorts, **maintien vivant** (deux sinus incommensurables par axe : un visage posé ne se fige jamais), pupille dans son propre groupe qui bouge **après** le visage, et exagération par famille d'humeur qui **ne touche ni paupières ni clignement ni rayons** — ceux-là énoncent un fait, pas une intensité : un `sleep` somnolent ramené à 92 % dort **les yeux ouverts à 8 %** (attrapé par un test, pas par une relecture). **(4) Deux organes, activés par style** : le **sourcil** est un élément réel hors de la couche paupière (un clignement ne clippe pas un sourcil), **invisible sur un visage neutre** — il n'apparaît que lorsqu'il a quelque chose à dire, donc aucun style ne le paie au repos ; sa grammaire (extrémités internes baissées = colère, levées = chagrin) est **tenue par test sur les vingt expressions** plutôt que confiée à vingt recettes écrites à la main. La **pupille** vit dans la forme (les paupières la couvrent comme le reste) et voyage **plus loin** que l'œil — cette différence est ce qui se lit comme « regarder à l'intérieur de l'œil ». Les deux sont conditionnés par des tokens (`--has-brow`, `--has-pupil`), jamais par une liste de noms de styles en dur. **(5) Matière dosée par style** : une source de lumière et une surface qui s'en éloigne, une lumière de bord et une occlusion de contact toutes deux **inset** (le clip de paupière les porte — une ombre externe avait autrefois étalé une traînée écrasée à chaque clignement), et **deux** reflets qui se déplacent de quantités **différentes** : ce rapport EST la cornée, égalisez-les et l'œil redevient plat. Ils suivent le regard sur un ressort lent, donc arrivent en retard et dépassent au retour — un reflet appartient à la pièce, pas à l'œil. `--matter` et `--gloss` sont de simples multiplicateurs : `traits` et `anneaux` les mettent à zéro, un trait et un contour n'ayant pas de surface. **(6) Une recherche est saccadique, et une émotion a une entrée** — deux décisions venues de l'observation du résultat : un balayage lisse gauche-droite est une **caméra de surveillance**, un œil qui cherche fait des **saccades** (bond, fixation brève, autre bond, à des endroits dispersés, jamais en rythme), et la mesure qui sépare les deux est le rapport pic/médiane du déplacement image à image — **> 6** pour le motif, ~1,5 pour un sinus ; et les ressorts seuls donnent à toutes les émotions la même chorégraphie, donc la colère **inspire puis frappe**, la peur recule, la tristesse se dégonfle, une question **penche la tête**, avec une **allure d'arrivée qui varie d'une interprétation à l'autre** depuis une source d'entropie que la liaison React fournit et que les tests omettent (le rig reste parfaitement déterministe sous test). **Coût assumé et mesuré** : une boucle d'animation JS sur un widget permanent, tenue par **une horloge de frames partagée** pour tous les rigs de la page, un **arrêt automatique** quand rien ne bouge, et une **cadence de repos** à ~30 Hz quand seules les boucles perpétuelles tournent (le souffle est un cycle de plusieurs secondes : un tiers des frames l'échantillonne indistinctement) — mesure sur les tests à horloge longue du widget : **3,08 s → 1,42 s** pour quinze minutes simulées ; le rig coûte ~3,5 µs par frame, l'écriture DOM domine, et un canal posé n'écrit rien. **Preuve navigateur hermétique** (le rig réel et la vraie feuille de style, sans application ni session) : matrice 20 × 6 dans les deux thèmes et frames gelées du clignement, de l'anticipation, de l'arc et du trajet de recherche — elle a attrapé **deux défauts qu'aucun test unitaire n'aurait vus** : sur `focused`, le clip de paupière soutenue rendait `traits` en deux points et `anneaux` en deux arcs disjoints. Le clignement avait déjà son exception d'écrasement pour ces deux langages ; les paupières **soutenues** ne l'avaient jamais eue. `STYLE_LID_MODE` la ferme, et une garde vérifie que le rig et la feuille de style s'accordent sur les styles qui écrasent.

---

### ADR-253 : une psyché est un trait, pas une réaction

**Statut**: ✅ ACTÉ (2026-09-01)
**Fichier**: `docs/architecture/ADR-253-Per-Turn-Expressivity-Annotation.md`

**Décision** : le visage choisissait son expression de fin de tour dans l'émotion dominante de la **psyché**, et la mesure a tranché — quatorze tours de production consécutifs, lus en base : `enthusiasm` sur **treize d'entre eux**, dans un mouchoir de **0,02**. C'est le comportement normal d'un modèle d'état lent ; le défaut est de lui avoir demandé de répondre d'un événement ponctuel, car **un `argmax` sur un vecteur quasi constant est une constante**. Le repli censé couvrir ce cas — une heuristique de ponctuation — n'avait rien à dire non plus : **neuf de ces quatorze réponses** ne contenaient ni « ! », ni emoji, ni bloc de code, et le multiplicateur d'emphase qui en découlait mesurait **0,94 à 1,21**, soit ±13 % sur deux groupes de canaux **sous une expression qui ne changeait jamais** — invisible par construction. Le prompt de la psyché interdisait déjà en toutes lettres de se rabattre sur `enthusiasm` à chaque tour, et était ignoré : ce n'était pas un problème de formulation. **(1) Le modèle qui écrit la réponse déclare le REGISTRE de cette réponse**, dans un vocabulaire qui appartient à l'animation et à rien d'autre : douze registres, douze visages **réellement distincts** — c'est la contrainte sous laquelle la liste a été construite et la raison pour laquelle elle n'est pas plus longue, *deux registres que l'avatar jouerait à l'identique sont un seul registre portant deux noms*. **(2) En BANDE, parce que deux exigences se croisent** : le signal doit venir du modèle qui a écrit la réponse (rien d'autre ne connaît le registre choisi) **et** arriver à l'instant où la réponse arrive (l'avatar réagit sur la complétion, et l'appraisal existant en fire-and-forget rate cette course sur la majorité des tours — `has_appraisal: false` dans les journaux). Une passe séparée aurait coûté un appel LLM par tour **et** serait arrivée après. Le motif n'est pas inventé : c'est **exactement celui de `<psyche_eval/>`**, en production depuis des mois — fragments filtrés dans le flux SSE, marqueur complet retiré du contenu persisté. **(3) L'intensité est une indication de JEU, pas une confiance** : le rendu la **surjoue**, et le **registre plafonne ce qu'elle peut acheter** — une réponse `factual` déclarée à 1,0 reste un visage neutre livré avec conviction, jamais une célébration ; l'intensité dit avec quelle force le registre est passé, jamais lequel c'était. **(4) La psyché garde ce qu'elle fait bien** : la famille d'humeur au repos. Un trait colore un comportement de repos, jamais une réaction ponctuelle — et le type `ReactionSource` n'a plus de porte pour elle, ce qui en fait une garantie de compilation. **(5) Ce qui est appliqué est publié** (doctrine ADR-184) : un registre proposé par le prompt mais refusé par le code produit un tour sans visage **en silence**, un registre accepté mais tu par le prompt est un visage qui n'arrivera jamais — un test tient les deux listes ensemble, un autre tient la copie TypeScript sur la copie Python. Un registre inconnu ne donne **aucune** annotation, jamais un défaut : un visage que personne n'a dessiné est pire qu'une absence de réaction ; et un marqueur malformé est **nettoyé quand même**, car mettre du balisage brut sous les yeux du lecteur est la pire des deux pannes. **(6) Le marqueur arrive une fois sur huit, et c'est MESURÉ** : premiers seize tours réels, le marqueur de ton et celui de la psyché ont été émis sur **exactement les deux mêmes tours**, zéro échec d'analyse, zéro fuite en base — le taux (~12 %) est une propriété du **modèle de réponse**, pas de la fonctionnalité, qui réussit précisément quand un mécanisme éprouvé réussit. Un visage qui ne réagit qu'un tour sur huit étant un visage cassé, **le repli ne renvoie plus jamais rien** : il lit la FORME de la réponse (longueur, blocs de code, densité de ponctuation, emoji — jamais les mots, donc six locales identiques) et parle **le même vocabulaire** que le marqueur déclaré. Une seule table de registres, une seule courbe d'amplitude : la voie parallèle (`deriveReaction`, `contentHeuristicExpression`, `responseEmphasis`, la table émotion→expression) a été **supprimée**, pas gardée en réserve. **(7) Le dessin, au passage** — deux corrections d'art direction venues de l'œil du propriétaire et vérifiées au navigateur : la bouche devient une **forme pleine** et non un trait (sous deux yeux pleins, un filet est un dessin au trait déguisé en écran de robot), d'où `mouthArc` publié **sans unité** puisque la feuille de style en a besoin comme hauteur **et** comme ratio de rayon et que CSS ne divise pas une longueur par une longueur ; et **un demi-cercle plein n'est pas une bouche** — trois écarts au compas mesurés sur un `joy` réel : dessus jamais plat (16,9 %), coins bas **différents** et penchés (55,07 % contre 44,93 %), forme qui **s'élargit** en se courbant (rapport largeur/hauteur **2,71**). Deux pièges attrapés au navigateur et non à la lecture : retourner la forme autour de son bord haut fait pousser la moue **dans le visage** (3,2 à 7,7 px de chevauchement sur les yeux avant correctif, 4,3 à 13,8 px de dégagement après), et **les coins doivent partir avant la courbe** — un vrai sourire commence aux coins, ce que le décalage par groupe ne pouvait pas exprimer puisque les trois canaux vivent dans `pose` : d'où `CHANNEL_LEAD_MS`, un décalage par CANAL qui prime sur celui du groupe.

---

### ADR-254 : trois mécanismes pour une convergence

**Statut**: ✅ ACTÉ (2026-09-01)
**Fichier**: `docs/architecture/ADR-254-Embedding-Convergence-And-Shock-Absorbers.md`

**Décision** : une heure de production sur une instance à un à trois utilisateurs, **11 échecs d'embedding sur 24 appels (46 %)**, tous `429 RESOURCE_EXHAUSTED` sur le quota **par minute** du modèle de base — et **zéro tour de chat impliqué**. Chaque échec dégradait en silence : contexte RAG absent d'une réponse, contexte de journaux absent, mémoire jamais écrite, message jamais indexé, scoring d'outils du routeur ignoré. Les deux du milieu ne sont pas une réponse dégradée mais une **perte définitive** : rien ne les rejoue. **Le volume n'a jamais été le problème** — un régime stable de quatre appels par minute passait sans une seule erreur ; ce qui casse est la **concentration**, et c'est une propriété du planificateur. **(1) La cause est arithmétique** : les périodes valaient 5, 5, 15, 30, 30 et 60 minutes — toutes multiples de cinq — toutes comptées depuis le démarrage, une seule portant un décalage et **aucune un `jitter`** : six tâches dans la même seconde, toutes les heures, chacune lançant un agent qui émet plusieurs embeddings. **(2) Trois mécanismes, trois rôles qu'il ne faut pas confondre** — les confondre conduit à mal dimensionner les deux autres. Le **jitter** traite la cause (15 % de la période, plancher à 5 s : un pourcentage d'une période courte s'arrondit à zéro et laisserait alignées précisément les tâches qui se télescopent le plus ; une exemption écrite, l'exécuteur d'actions **datées par l'utilisateur**, où décaler n'est pas étaler mais livrer en retard). Le **limiteur** traite l'échelle et ne change rien à l'incident observé — six appels en une seconde passent sous n'importe quel plafond par minute — d'où une fenêtre **courte** (8 appels / 10 s), parce que ce qu'il faut plafonner est la concurrence instantanée ; il **compose** le limiteur Redis distribué existant plutôt que d'en ajouter un second. Le **réessai** traite le résidu. **(3) Le régulateur est un régulateur, jamais une porte** : l'attente est bornée et **expire ouverte**, et il échoue **ouvert** si Redis est injoignable — notre propre étranglement ne doit jamais être la raison pour laquelle une réponse perd sa mémoire. **(4) Le budget reste hors du chemin critique** : `user_message_embedding` partage son singleton avec le domaine mémoire, donc la même instance sert le tour d'un utilisateur et un lot de fond — il n'y a **aucune instance** à qui donner un budget patient, et un drapeau par appel serait oublié un jour sur un site. Profil unique et serré (0,5 s d'attente, une seule reprise), plafond gardé par test. **(5) Le réessai exige une FABRIQUE, pas un awaitable** : une coroutine ne s'attend qu'une fois, un point de couture tenant `client.aembed_query(...)` ne peut pas réessayer — c'est cette contrainte qui a dicté le refactor du goulot, et elle supprime au passage tout risque de coroutine jamais attendue. **(6) Un seul classificateur, structurel d'abord** : le réindexeur RAG en avait déjà un, et sa docstring dit pourquoi il lit le **code de statut** en remontant `__cause__` — *lire le texte d'un message, c'est ainsi qu'un changement de formulation chez le fournisseur transforme silencieusement un réessai en échec dur*. La version texte écrite d'abord par ce chantier a été **supprimée au profit de la sienne** ; le message reste lu en repli, uniquement si aucun code n'existe dans la chaîne (c'est exactement ainsi que l'incident réel est arrivé), et quand un code EXISTE il est **final**, sinon un nombre cité dans une phrase renverserait le fait. **(7) L'alerte lit les ISSUES, pas les appels** : avec réessai un échec récupéré vaut deux appels, et alerter sur les appels ferait sonner des incidents réparés d'eux-mêmes. **(8) Un faux négatif de garde corrigé au passage** : deux agents (ADR-247, ADR-249) avertissaient à chaque reconstruction du catalogue parce que leur domaine n'était pas déclaré — un garde existait mais parcourt le registre **vers l'extérieur** et ne peut donc structurellement pas voir un agent dont le domaine n'existe pas. Impact fonctionnel **nul** (le seul consommateur de l'index par domaine n'a aucun appelant en production), risque latent : `diagnostics_agent` devient **`devops_diagnostics_agent`** (la description de `devops` couvre déjà mot pour mot « deployment diagnostics, production error analysis », et l'agent s'y réfère lui-même), tandis que `python_sandbox_agent` est déclaré **capacité de plateforme** — `DomainConfig` **exige** un `result_key` et cet agent ne produit qu'un calcul ; l'y forcer inventerait une référence `$steps.step_N.pythons` que rien ne peut produire. Garde **CI** et non assert au démarrage : un assert ferait planter la production au prochain agent nommé hors convention. **(9) Trois choses supprimées** : `retry_with_backoff` était écrit, documenté, testé et **sans aucun appelant** (il porte désormais le réessai, son décorateur déléguant au même cœur) ; le classificateur du réindexeur a cessé d'être une copie ; et `geo_lat`/`geo_lon`, liés au contexte de **chaque requête** — 1099 lignes en une heure dont **1054 en INFO**, ce que le dépôt interdit pour une localisation — avaient **zéro consommateur**, le compteur par pays, les deux panneaux du tableau géo et jusqu'à la carte du monde lisant le pays et la ville.

---

### ADR-255 : une seule autorité sur ce qu'un serveur MCP déclare

**Statut**: ✅ ACTÉ (2026-09-02)
**Fichier**: `docs/architecture/ADR-255-MCP-Tool-Declaration-Conformance.md`

**Décision** : un serveur MCP de finances ajouté, « Liste mes comptes bancaires » sans réponse — et la mesure : **30 des 40 outils du serveur n'étaient jamais construits**, 270 occurrences en 72 h de production, pour toute trace un `warning` et **aucun compteur**. Le routage était juste (score 1,0 sur le bon serveur) ; c'est l'outil qui manquait. **(1) La cause tient en une ligne de JSON** : `"type": ["boolean", "null"]` est légal depuis draft-04 et c'est la façon dominante d'écrire « optionnel » ; une liste n'est pas hachable, et **quatre** points du code s'en servaient comme clé de dictionnaire. Corriger le premier seul n'aurait rien changé en mode pipeline — le crash se serait déplacé de l'adaptateur au manifeste, **dans le même `try`**, une ligne plus bas : deux lectures d'une même déclaration finissent toujours par diverger. **(2) Un module, deux consommateurs** : `infrastructure/mcp/json_schema.py` devient l'autorité unique, lue par l'adaptateur LangChain et par le catalogue du planificateur, avec un test de **parité** qui compare les deux pour sept formes de déclaration. Toute fonction y est **totale** — elle ne lève jamais, parce que lever coûte un outil, et qu'un outil perdu est une capacité que l'utilisateur n'a plus sans en être averti. **(3) La conformité n'était pas partielle, elle était absente** : la spec 2026-07-28 admet *tout* mot-clé 2020-12 dans un `inputSchema`, or le repli renvoyait « pas de schéma » dès qu'une **seule** propriété utilisait `$ref`, `anyOf`, `oneOf`, `allOf` ou `const` — et ce repli, mesuré, publie l'outil au modèle sous la forme d'un `kwargs` **opaque** : ni noms de champs, ni descriptions, ni obligatoires. Listé et inappelable. `resolve_property` réduit désormais l'ensemble, avec déréférencement des `$ref` **locaux uniquement** (aucune requête réseau ne part d'un schéma tiers), garde de cycle et profondeur bornée ; deux réductions restent partielles et **écrites comme telles**, faute d'un seul cas dans les sept serveurs vivants mesurés. **(4) Un `enum` a deux lecteurs qui n'attendent pas la même chose** — trouvé en revue, après le vert des tests, et c'est le cœur : le validateur de plan teste `value not in expected`, donc son ensemble **garde** le membre `null` ; la déclaration provider le **retire**, la nullabilité voyageant dans l'annotation. Les confondre faisait d'un `direction: null` — valeur que le serveur accepte — une violation, donc `is_valid=False`, donc un re-planning injustifié. **(5) `pattern` n'est délibérément pas une contrainte** : le validateur le compilerait avec `re.match` sur un chemin async, où un motif ECMA-262 que Python refuse et un backtracker catastrophique qu'aucun `except` n'interrompt gèleraient la boucle d'événements et tous les flux SSE ; il reste publié aux providers, qui se contentent de le lire. **(6) Les annotations resserrent, jamais l'inverse**, parce que la spec l'exige (*clients **MUST** consider tool annotations to be untrusted*) : une mutation déclarée est crue — au pire une confirmation de trop — tandis qu'un `readOnlyHint: true` ne l'est pas, une catégorie déclarée **battant** l'heuristique de nom et pouvant donc retirer l'outil du filet anti-mutation, de la portée HITL et de la phase d'initiative sur la parole d'un tiers. Le gain se voit surtout en mode **itératif**, où tous les outils d'un serveur partagent **un seul** drapeau HITL : désactiver la confirmation pour un serveur consultatif la désactivait aussi pour `forget`, `cancel_subscription` et `disconnect_institution`, dont **aucun** ne porte l'un des neuf verbes de mutation. **(7) Un outil abandonné est désormais compté** — `mcp_tool_registration_failures_total`, labels bornés par construction, deux panneaux, et **un** événement de journal là où trois noms disaient la même chose. Parité des gardes au passage : le chemin admin protège par outil comme les chemins utilisateur le faisaient déjà. **(8) Quatre défauts trouvés par la revue à froid après le vert intégral**, dont le `null` de l'enum qu'aucun test ne pouvait voir puisqu'ils encodaient l'erreur ; et un « correctif » **annulé** par vérification (remplacer `text-[11px]` par `text-xs` au nom d'une charte que 108 fichiers contredisent).

---

### ADR-256 : un budget qui ne compte que la moitié du travail

**Statut**: ✅ ACTÉ (2026-09-02)
**Fichier**: `docs/architecture/ADR-256-React-Budget-Conservation-And-Declared-Tool-Safety.md`

**Décision** : trois défauts indépendants, une seule forme — **une garde existe, mais elle ne couvre plus ce qu'elle croit couvrir**, parce qu'une décision juste a cessé de l'être quand son contexte a changé. **(1) Le budget de la boucle ReAct ne compte que le raisonnement.** ADR-170 a eu raison de débiter `react_elapsed_seconds` depuis le nœud lui-même — `interrupt()` lève, donc l'attente humaine est exclue *structurellement*, sans horodatage à maintenir. Mais depuis, **ADR-083 Phase 2** a fait du sous-agent une boucle ReAct **exposée comme un outil** (20 itérations LLM derrière un `tool_call`, la même ADR notant que son plafond de dépense *« was never wired »* et que le budget journalier a été **supprimé** sans remplacement), ADR-249 a ajouté le bac à sable, et les modes itératif MCP et navigateur ouvrent chacun leur boucle (50 et 50). **Le nœud qui n'exécute que des outils est devenu celui qui dépense le plus, et c'est précisément celui qui ne débite rien** : mesuré, `react_elapsed_seconds` est écrit par **1 nœud sur 4**, un tour dont le modèle a raisonné 10 s et dont les outils ont tourné trois heures rend `react_exit_reason() is None`, et `compute_step_timeout` — la politique par famille, complète et testée — n'avait **qu'un seul appelant**, le pipeline : `react_nodes.py` ne contenait **aucun** `asyncio.wait_for`, si bien que le MÊME outil était borné à 300 s dans un mode et non borné dans l'autre, pour une borne haute de tour d'environ **30 h**. Deux contre-hypothèses testées et **écartées** : le frein anti-répétition ne compare que des appels **identiques** (deux délégations ne se ressemblent jamais) et le timeout de transport par slot laisse encore 20 × 60 s pour **une** délégation. **Correctif** : le ReAct lit la politique que le pipeline applique déjà — un second appelant, pas un second corps — et un dépassement devient un `ToolMessage` récupérable ; **deux compteurs, deux seuils, un seul prédicat** (`react_tool_seconds` à côté de `react_elapsed_seconds`, dont le seuil ne bouge pas, donc **aucun tour qui aboutit aujourd'hui ne peut être coupé demain** — additionner les deux a été **mesuré et rejeté** : une seule délégation à sa borne pipeline consomme **100 %** du budget de raisonnement). Le routeur, lui, teste désormais « une raison quelconque » et non une liste de noms : un `elif exit_reason == "compute_budget"` aurait laissé passer `tool_budget`, le prédicat disant stop pendant que la boucle continue. **Et la mesure affirmait le contraire de ce qu'elle mesure** : le panneau s'intitulait *« ReAct agent **total execution** duration »* et le comparatif « Pipeline vs ReAct » opposait un pipeline qui compte ses outils à un ReAct qui ne les compte pas — **la comparaison flattait le ReAct par construction** ; la série n'est pas rompue (le temps outil est déjà porté par `agent_tool_duration_seconds`), ce sont les descriptions et le panneau de debug qui cessent de promettre un total (« Elapsed » devient « Reasoning », « Tools » apparaît avec sa borne publiée, ADR-184). **(2) Ce que le plafond d'outils coupe, personne ne le voyait** : **896** outils résolus possibles pour un plafond de **100** (96 natifs + 20 serveurs MCP × 40), pour toute trace un `logger.warning` et **aucun compteur** ; et un `tool_call` sans outil correspondant ajoutait un `ToolMessage` puis `continue`, **ni log ni métrique**. Deux compteurs désormais, et surtout `reason` à **deux valeurs qui appellent des correctifs opposés** — `not_selected` (l'outil existe, le plafond l'a écarté : le plafond est trop bas) contre `unknown` (le modèle a inventé le nom : le catalogue est mal présenté) — les confondre aurait rendu la métrique inutile ; le **nom d'outil ne devient jamais un label**, il vient d'un modèle et sa cardinalité n'est pas bornée. Un point restait correct et le reste : le `continue` précède l'incrément de `productive_calls`, donc **un appel inconnu ne peut pas acheter d'extension de budget**. **(3) Une catégorie devinée là où elle devait être déclarée** : `infer_tool_category` finissait par `return "readonly"  # Default (safe)`, atteint par **17 manifestes sur 96**, dont **quatre qui écrivent** — `write_spreadsheet_tool`, `append_document_text_tool`, `set_vacation_responder_tool`, `activate_skill_tool`. Aucune écriture non confirmée n'en découlait (tous passent par un brouillon HITL, et leurs manifestes le déclarent) : le défaut est de **classification**, et il portait deux fois — ces outils étaient `initiative_eligible` alors que la phase d'initiative est censée être en lecture seule, et `tool_is_mutation()` les excluait du filet qui reroute un plan non convergé vers une clarification. Ce qui le rend structurel, c'est qu'il **récidive** : `plan_predicates.py` documente déjà trois victimes de la même forme (`cancel_reminder_tool`, `edit_image`, `generate_image`), corrigées une par une. **Deviner d'après une convention est légitime, inventer une intention ne l'est pas** (ADR-184) : une fonction rend la différence lisible en retournant `None` quand aucune convention ne s'applique, un **assert de complétude refuse de démarrer** sur un manifeste natif indécidable — placé après `initialize_catalogue` et non dans `run_failfast_validations`, qui s'exécute **avant** tout enregistrement et aurait donc validé un registre vide et passé pour toujours — et les 17 déclarent leur catégorie, treize à l'identique (**aucun changement**), quatre en disant la vérité. Les outils MCP tiers restent hors garde : ADR-255 gouverne déjà leur déclaration, et le repli y demeure correct puisqu'une annotation ne peut que resserrer. **(4) Six défauts trouvés par la revue à froid, après le vert des tests** : un appel MCP direct aurait hérité du plancher générique de 30 s alors que la couche MCP applique déjà le sien — jusqu'à **120 s réglés par l'utilisateur serveur par serveur** — donc notre borne serait devenue **la voix la plus stricte de la chaîne** et aurait coupé un appel que la couche du dessous acceptait encore ; un `TimeoutError` levé par l'outil lui-même aurait été rapporté comme « arrêté après 300 s », **un nombre que le tour n'a jamais atteint** (l'écoulé décide désormais laquelle des deux phrases est vraie) ; deux modules du même nom, `nodes/react_budget.py` créé face à `utils/react_budget.py` existant (ADR-238), ont été **fusionnés** — le budget initial et le budget effectif sont la même question posée deux fois ; la formulation du timeout était **inline** alors que ses deux sœurs (`repeated_call_message`, `abandoned_call_message`) sont des fonctions nommées du même paquet, et l'a rejointe ; la docstring de `compute_step_timeout` **énumère ses familles** et en ignorait une, ce qui est le défaut « le code fait ce que la doc ne dit pas » pris par l'autre bout ; et l'interface empilait **deux barres visuellement identiques et anonymes** — la seconde était d'ailleurs arrivée sans la ligne d'avertissement de la première, ce qui est exactement pourquoi elles n'ont plus qu'une implémentation (`BudgetBar`, qui les nomme). **Un risque écarté par simulation plutôt que par raisonnement** : `asyncio.wait_for` aurait pu exécuter l'outil dans une TÂCHE séparée, laquelle **copie** le contexte au lieu de le partager — toutes les écritures de `ContextVar` d'un outil auraient alors été perdues pour le nœud, **en silence**, à commencer par les scripts du bac à sable qu'ADR-249 draine après la boucle ; mesuré sur Python 3.14, `wait_for` délègue à `asyncio.timeouts.timeout` et attend sur place, donc le contexte est partagé — et un test épingle désormais ce comportement contre un futur runtime qui le changerait.

---

### ADR-257 : cinq défauts de couture — la provenance à travers la compaction, l'ancre du tour, la trace honnête, la validation par couverture, le contexte délivré mesuré

**Statut**: ✅ ACTÉ (2026-09-02)
**Fichier**: `docs/architecture/ADR-257-Seam-Defects-Provenance-Anchor-And-Delivered-Context.md`

**Décision** : une revue de littérature (299 articles arXiv triés, 12 retenus) a servi de grille de lecture sur le code ; chaque hypothèse a été validée par des preuves exécutables avant tout changement, et cinq défauts ont survécu à la contre-vérification. Tous ont la même forme : **une couture** — deux sous-systèmes corrects chacun sous son ADR, composés en un comportement que personne ne possède. **(1)** La compaction était une TROISIÈME surface LLM qu'ADR-167 n'énumérait pas : un corps d'e-mail marqué `<external_content>` ressortait du résumé comme fait établi, dans un `SystemMessage` que le fenêtrage ReAct retient préférentiellement — et la notice de repli republiait l'URL de l'attaquant comme « Key identifier ». Le résumé **hérite** désormais d'une bannière de provenance calculée à l'écriture sur les DEUX branches, posée APRÈS le marqueur (quatre lecteurs `startswith`), et le repli sépare les identifiants par provenance (fail-closed). **(2)** Le plafond de messages évincait **la question du tour lui-même** à l'itération ⌈cap/2⌉ = 75 (mesuré, invariant selon l'historique), après quoi le fenêtrage se court-circuitait : `_ensure_turn_anchor` ré-épingle le dernier HumanMessage sur les deux branches de troncature, no-op strict sous les seuils, et le couplage entre `react_agent_max_iterations` et `max_messages_history` a UN nom (`react_budget_exceeds_state_window`) — journalisé là où il mord, jamais un refus de boot qui casserait les déploiements 90/150 existants. **(3)** La trace visible gardait la queue seule et affichait le compte TRONQUÉ : `capTraceSteps` (une implémentation, live + rechargement) garde tête+queue et énonce le total exact — un compte affiché est une revendication. **(4)** `missing_step` était exposé au modèle par le schéma et jamais demandé par le prompt (0 puce d'absence sur 9) : le prompt énumère désormais d'abord les exigences puis vérifie la couverture (appliqué à v1 en place — les prompts ne sont pas versionnés, arbitrage propriétaire 2026-09-02), avec deux boucliers anti-faux-positifs, et un verdict route vers le replan SILENCIEUX borné (ADR-184 : un verdict n'est pas un échec). **(5)** Le contexte DÉLIVRÉ n'était pas mesuré (2,3 k tokens à l'itération 1, 112 k à la 90) et le cache Anthropic ne couvrait jamais l'historique — un commentaire affirmant le contraire : deux histogrammes via le compteur mémoïsé du réducteur + deux panneaux Grafana, le `cache_control` racine documenté (retenu sous 4 points de rupture explicites), et les commentaires corrigés. **Aucune politique de compression ne part avec cette ADR** : la mesure décide. S'y ajoute la sonde opérateur `personalization_probe.py` (fuite/complaisance/diversité, chaque nombre avec son seuil) — LIA injecte sept sources de personnalisation et n'en mesurait aucun effet de bord. Écartés en connaissance de cause : rétention apprise façon TRACER (le cache préfixe amortit déjà le coût), mémoire par graphe (mesurée inférieure au vecteur plat existant), tête+queue côté persistance backend (inatteignable via le dédoublonnage par clé).

