# Human-in-the-Loop (HITL) - Architecture Phase 8

> Système d'approbation plan-level avant exécution avec génération de questions LLM multilingues
>
> Version: 8.7 (July 2026 - One-click interactive layer over the resume contract: structured `hitl_decision` (classifier bypassed), `GET /agents/hitl/pending` rehydration, execution trace, actionable connector notices — ADR-132/133/134)
> Date: 2026-07-19

## 📋 Table des Matières

- [Vue d'Ensemble](#-vue-densemble)
- [Architecture 6 Couches](#-architecture-6-couches)
- [Schemas & Structures](#-schemas--structures)
- [Nouveaux Composants Phase 8.1](#-nouveaux-composants-phase-81)
  - [Unified Schemas (schemas.py)](#unified-schemas-schemaspy)
  - [Scope Detector (scope_detector.py)](#scope-detector-scope_detectorpy)
  - [Destructive Confirm (destructive_confirm.py)](#destructive-confirm-destructive_confirmpy)
  - [FOR_EACH Confirmation (for_each_confirmation.py)](#for_each-confirmation-for_each_confirmationpy)
- [Question Generation](#-question-generation)
- [Approval Strategies (removed)](#-approval-strategies-removed-in-v12116)
- [Approval Gate Node](#-approval-gate-node)
- [HITL Orchestrator (removed)](#-hitl-orchestrator-removed-in-v12116)
- [Configuration & Storage](#-configuration--storage)
- [Métriques](#-métriques)
- [Migration Phase 7 → Phase 8](#-migration-phase-7--phase-8)

---

## 🎯 Vue d'Ensemble

Le système HITL (Human-in-the-Loop) de LIA permet d'**interrompre l'exécution pour demander l'approbation utilisateur** avant d'effectuer des actions à risque.

### Contrat HITL unifié (ADR-106)

Toute interruption HITL suit **un seul contrat** : un `action_requests` **typé**
(`draft_critique`, `tool_confirmation`, `for_each_confirmation`,
`entity_disambiguation`, `plan_approval`, `clarification`) → rendu par son
interaction (couche streaming) → résumé par sa branche dans
`OrchestrationService._parse_approval_decision`. **Le pipeline et ReAct partagent
ce contrat** — ReAct n'a plus de dialecte propre (l'ancien interrupt
`react_tool_approval`, sans `action_requests`, était non rendu → hang silencieux).

Deux mécanismes de déclenchement, complémentaires :

| Mécanisme | Déclencheur | Portée |
|-----------|-------------|--------|
| **Output-driven** (post-exécution) | le tool renvoie `requires_confirmation=True` + un `draft_type` | drafts (`email`, `event`, `*_delete`, …) → `draft_critique` ; ou `draft_type="tool_confirmation"` |
| **Flag-driven** (pré-exécution) | `manifest.permissions.hitl_required=True` | mutations **non-draft** uniquement ; en ReAct → interaction `tool_confirmation` |

**Invariant `hitl_required`** : le flag signifie *« confirmation pré-exécution
d'une mutation **sans draft** »* — et rien d'autre. Un tool **draft-based** (qui
produit un draft, ex. `delete_email_tool`, `cancel_reminder_tool`) DOIT être
`hitl_required=False` : le draft **est** sa confirmation (via `draft_critique`),
exactement comme `send_email`/`create_event`/`delete_contact`. Verrouillé par
`tests/unit/domains/agents/tools/test_hitl_required_consistency.py` (allowlist :
`delegate_to_sub_agent_tool` + tools MCP utilisateur). En pipeline, `hitl_required`
n'est **pas** un gate (`approval_gate_node` = pass-through, la confirmation y est
entièrement output-driven) ; le flag pilote donc surtout le gate **pré-exécution
ReAct** (`react_execute_tools_node` → `tool_confirmation`).

### Évolution : Phase 7 → Phase 8

| Aspect | Phase 7 (Ancien) | Phase 8 (Actuel) |
|--------|------------------|-------------------|
| **Interrupts** | Mid-execution | **Before execution** |
| **UX** | Pauses inattendues | **Plan complet présenté** |
| **User Control** | Limité | **Peut éditer paramètres** |
| **Validation** | Tool-by-tool | **Plan-level centralisé** |
| **Performance** | Overhead par tool | **Single approval overhead** |

### Principes Clés

1. **Plan-Level** : Approbation AVANT exécution (pas mid-execution)
2. **Transparent** : Plan complet présenté à l'utilisateur
3. **Editable** : Utilisateur peut modifier paramètres
4. **Strategy-Driven** : 5 stratégies d'approbation composables
5. **Multilingue** : Questions générées en 6 langues

### Couche interactive one-click (ADR-132/133/134)

Au-dessus du contrat de resume conversationnel décrit ci-dessous, une couche
interface rend l'approbation tangible sans jamais fermer le canal texte/voix :

- **Cartes d'approbation (ADR-132)** — un interrupt en attente (tool
  confirmation, draft, destructive/FOR_EACH) s'affiche en carte avec des
  boutons pilotés par le backend (`available_actions`). Le clic envoie un
  `hitl_decision` structuré `{message_id, action[, modification_instructions]}`
  sur le send normal ; `build_structured_decision` le mappe **déterministiquement**
  vers le payload de resume — **sans appel classifier** (`classifier_bypassed`),
  parité octet-pour-octet avec le chemin langage naturel, **fail-closed**
  (`hitl_decision_stale`) sur tout clic périmé/désaligné. Le bouton *Modifier*
  d'un draft route la boucle `draft_modifier` vivante (édition structurée).
- **Réhydratation** — `GET /agents/hitl/pending` (lecture autoritaire no-store)
  reconstruit la carte après un rechargement de page ; le canal texte/voix
  reste pleinement fonctionnel en parallèle (règle : la conversation gagne
  toujours). Cache de détection en `utils/hitl_cache`, invalidé au chokepoint
  `HITLStore` save/delete.
- **Coulisses (ADR-133)** — les étapes agentiques et le raisonnement, jadis
  effacés au flip progress→answer, survivent désormais attachés au message
  (ligne repliée « ⚙ N étapes · X s ») — et, depuis v1.25.12 (ADR-133 V2),
  persistés dans `message_metadata` : la trace se relit après rechargement,
  sur tous les appareils (clés i18n uniquement, jamais le raisonnement).
- **Erreurs connecteurs actionnables (ADR-134)** — un échec d'outil sur OAuth
  expiré (typé, jamais par string) affiche un encart « Reconnecter » dans le
  chat ; depuis v1.25.12 (ADR-134 V2), l'encart revient aussi aux runs
  suivants, quand le connecteur requis est détecté en `status=ERROR` à la
  résolution du provider.

---

## 🏗️ Architecture 6 Couches

> ⚠️ **Note de lecture (2026-07-11)** : ce schéma en couches est **partiellement
> historique**. Les couches 3–4 (Approval Strategies, Approval Evaluator) et 6
> (HITL Orchestrator) ont été **supprimées en v1.21.16** (voir les sections
> « removed » plus bas), et la couche 5 (`approval_gate_node`) est aujourd'hui un
> **pass-through auto-approve** — la confirmation est entièrement output-driven /
> tool-level. Le contrat normatif actuel est la section
> [« Contrat HITL unifié (ADR-106) »](#contrat-hitl-unifié-adr-106) ci-dessus et le
> schéma [hitl-flow.mmd](../architecture/hitl-flow.mmd).

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: QUESTION GENERATION                                 │
│ - hitl_question_generator (tool-level, deprecated)          │
│ - hitl_plan_approval_question_generator (plan-level)        │
│ - Streaming support, markdown normalization                 │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────┴────────────────────────────────────────┐
│ Layer 2: VALIDATION FRAMEWORK                                │
│ - extract_tool_name() - 3 fallbacks                         │
│ - extract_tool_args() - 4 fallbacks                         │
│ - validate_action_count() - DoS protection (max 10)         │
│ - format_validation_errors() - i18n error messages          │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────┴────────────────────────────────────────┐
│ Layer 3: APPROVAL STRATEGIES                                 │
│ - ManifestBasedStrategy (main)                              │
│ - CostThresholdStrategy                                     │
│ - DataSensitivityStrategy                                   │
│ - RoleBasedStrategy                                         │
│ - CompositeStrategy (AND/OR combination)                    │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────┴────────────────────────────────────────┐
│ Layer 4: APPROVAL EVALUATOR                                  │
│ - Evaluate all strategies                                   │
│ - Aggregate reasons                                         │
│ - Return ApprovalEvaluation                                 │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────┴────────────────────────────────────────┐
│ Layer 5: APPROVAL GATE NODE                                  │
│ - Build PlanSummary                                         │
│ - Generate LLM question                                     │
│ - Interrupt user (LangGraph NodeInterrupt)                  │
│ - Process decision (APPROVE/REJECT/EDIT/REPLAN)             │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────┴────────────────────────────────────────┐
│ Layer 6: HITL ORCHESTRATOR                                   │
│ - Classify user responses (APPROVE/REJECT/EDIT/AMBIGUOUS)   │
│ - Build structured decisions for LangChain                  │
│ - Store tool_call_id mappings (for REJECT handling)         │
│ - Error handling + clarification questions                  │
└─────────────────────────────────────────────────────────────┘
```

---

## 📦 Schemas & Structures

### Approval Schemas

```python
# apps/api/src/domains/agents/orchestration/approval_schemas.py

class StepSummary(BaseModel):
    """Résumé d'une step pour présentation utilisateur."""
    step_id: str
    tool_name: str
    description: str
    parameters: dict[str, Any]
    estimated_cost_usd: float
    hitl_required: bool
    data_classification: str | None  # "sensitive", "public"
    required_scopes: list[str]

class PlanSummary(BaseModel):
    """Résumé complet du plan pour HITL."""
    plan_id: str
    total_steps: int
    total_cost_usd: float
    hitl_steps_count: int
    steps: list[StepSummary]
    generated_at: datetime

```

> **v1.21.16 (ADR-107)**: `PlanApprovalRequest`, `PlanApprovalDecision`,
> `PlanModification`, `ApprovalEvaluation` and `PlanApprovalAudit` were removed
> with the dead plan-approval framework. `StepSummary` and `PlanSummary` (above)
> remain: they feed the HITL question streaming and the interaction registry's
> `PLAN_APPROVAL` fallback. EDIT resumption uses plain modification dicts built
> by `hitl/resumption_strategies.py`.

---

## 🆕 Nouveaux Composants Phase 8.1

> Ajouts Janvier 2026 : HITL Consolidation + Safety Enrichment

### Unified Schemas (schemas.py)

**Fichier** : `apps/api/src/domains/agents/services/hitl/schemas.py`

Schemas Pydantic V2 unifiés comme source de vérité pour :
- Payloads d'interruption HITL
- Réponses utilisateur
- Métadonnées SSE chunks

```python
class HitlSeverity(str, Enum):
    """Niveau de sévérité pour l'UI."""
    INFO = "info"        # Confirmation standard (bleu)
    WARNING = "warning"  # Attention conseillée (jaune/orange)
    CRITICAL = "critical"  # Action destructive (rouge)

class HitlAction(BaseModel):
    """Option d'action présentée à l'utilisateur."""
    action: str            # Identifiant machine
    label: str             # Clé i18n pour le texte du bouton
    style: HitlActionStyle # Style visuel (PRIMARY, DESTRUCTIVE, etc.)
    description: str | None

class HitlInterruptPayload(BaseModel):
    """Payload complet d'interruption HITL."""
    interaction_type: HitlInteractionType
    severity: HitlSeverity
    title: str
    message: str
    actions: list[HitlAction]
    context: dict[str, Any]
    registry_ids: list[str]  # IDs pour preview
```

### Scope Detector (scope_detector.py)

**Fichier** : `apps/api/src/domains/agents/services/hitl/scope_detector.py`

Détecte les opérations à scope dangereux nécessitant une confirmation renforcée.

**Critères de détection** :
- Opérations bulk (3+ items)
- Opérations destructives (delete, remove, clear)
- Indicateurs de scope large ("tous", "every", "entire")
- Suppressions par plage temporelle ("tous les emails de la semaine dernière")

```python
class ScopeRisk(str, Enum):
    LOW = "low"          # Single item, réversible
    MEDIUM = "medium"    # Few items ou semi-destructif
    HIGH = "high"        # Many items ou destructif
    CRITICAL = "critical"  # Bulk destructif ("delete all")

@dataclass
class DangerousScope:
    requires_confirmation: bool
    risk_level: ScopeRisk
    operation_type: str
    affected_count: int
    reason: str
    indicators: list[str]

# Utilisation
scope = detect_dangerous_scope(
    operation_type="delete_emails",
    query="supprime tous les emails de Jean",
    affected_count=15,
)
if scope.requires_confirmation:
    # Déclencher DESTRUCTIVE_CONFIRM HITL
    ...
```

### Destructive Confirm (destructive_confirm.py)

**Fichier** : `apps/api/src/domains/agents/services/hitl/interactions/destructive_confirm.py`

> **v1.21.9 Change — Full HITL localization ([ADR-103](../architecture/ADR-103-HITL-Backend-i18n.md))**: the entire resume path is now language-clean for the 6 supported languages. EDIT reformulations (`HitlMessages.get_reformulation`, keyed by a `ReformulationKind` StrEnum), the REJECT enriched message (`get_reject_enriched_message`) and the rejection-summary fallback (`get_user_refused_action`) are localized; the response classifier's few-shot examples were externalized to a versioned **English** prompt (`hitl_classifier_examples.txt`) to remove the French-only classification bias, and the draft-modifier prompt scaffolding is English (LLM-facing; output stays in the user's language). The user language is read from the checkpointed `MessagesState.user_language` via `resolve_user_language`.
>
> **v1.14.5 Change — Action-Specific Titles**: The generic "Confirmation requise" / "Confirmation required" title is now replaced with action-specific titles based on the `draft_type` of the operation. Titles are generated by `HitlMessages.get_destructive_confirm_title()` and localized in all 6 languages (fr, en, de, es, it, zh). Examples:
>
> | draft_type | FR | EN |
> |------------|----|----|
> | delete | Confirmation de suppression | Delete confirmation |
> | send | Confirmation d'envoi | Send confirmation |
> | update | Confirmation de modification | Update confirmation |
> | create | Confirmation de creation | Create confirmation |
>
> This provides clearer visual cues to the user about what kind of action they are confirming.

Interaction HITL pour les opérations bulk destructives avec confirmation renforcée.

**Cas d'usage** :
- "Supprime tous mes emails de Jean"
- "Efface tous les contacts du groupe X"
- "Annule tous mes rdv de la semaine"

**Architecture** :
```
ScopeDetector détecte scope dangereux
    → Planner déclenche DESTRUCTIVE_CONFIRM
    → DestructiveConfirmInteraction génère question d'avertissement
    → Utilisateur doit confirmer explicitement
    → Opération procède ou avorte
```

```python
@HitlInteractionRegistry.register(HitlInteractionType.DESTRUCTIVE_CONFIRM)
class DestructiveConfirmInteraction:
    """
    Génère des questions d'avertissement renforcées pour les opérations
    affectant plusieurs items ou ayant des conséquences irréversibles.

    Utilise la sévérité CRITICAL pour le styling UI.
    """
    async def generate_question_stream(
        self,
        context: DestructiveConfirmContext,
        config: dict[str, Any],
        callbacks: list[BaseCallbackHandler],
    ) -> AsyncGenerator[str, None]:
        ...
```

### FOR_EACH Confirmation (for_each_confirmation.py)

**Fichier** : `apps/api/src/domains/agents/services/hitl/interactions/for_each_confirmation.py`

Interaction HITL pour les opérations bulk itératives via le pattern FOR_EACH.

**Cas d'usage** :
- "Envoie un email à tous mes contacts du groupe Marketing"
- "Supprime tous les emails de ce contact"
- "Mets à jour l'entreprise de tous ces contacts"

**Thresholds HITL** (configurable via `.env`) :

| Setting | Default | Description |
|---------|---------|-------------|
| `FOR_EACH_MUTATION_THRESHOLD` | 1 | Mutations ≥N → HITL approval obligatoire |
| `FOR_EACH_APPROVAL_THRESHOLD` | 5 | Non-mutations ≥N → advisory |
| `FOR_EACH_WARNING_THRESHOLD` | 10 | Non-mutations ≥N → HITL approval |

**Architecture (replay-safe, 2026-07)** :
```
Planner génère ExecutionStep avec for_each
    → task_orchestrator détecte FOR_EACH pattern + évalue thresholds
    → Pré-exécute les providers UNE FOIS (_pre_execute_for_each_providers)
    → Persiste for_each_hitl_ctx dans le state (return → checkpoint)
    → route_from_orchestrator → for_each_confirm (nœud dédié)
    → for_each_confirm : UN interrupt() par exécution de nœud
        ├── APPROVE → ctx.approved=True → retour task_orchestrator
        │             (reprend depuis le ctx persisté, AUCUN re-fetch)
        ├── EDIT    → ItemFilterService (LLM) UNE fois → indices cumulés
        │             persistés dans le ctx → self-loop → nouvel interrupt
        │             présente la liste filtrée
        └── REJECT / tous exclus / max itérations / décision inconnue
                    → cancel → draft_action_result action="cancel" → initiative
```

> **v1.21.x Change — Replay-safe FOR_EACH (nœud `for_each_confirm`)** : historiquement la
> confirmation vivait dans une boucle `while` + `interrupt()` à l'intérieur de
> `task_orchestrator`. Sémantique LangGraph : au resume, le **nœud entier se ré-exécute** —
> chaque décision utilisateur rejouait donc la pré-exécution des providers (appels API réels)
> et **tous** les filtres LLM passés (non déterministes) : la liste affichée pouvait diverger
> de la liste exécutée. La boucle vit désormais dans le nœud dédié
> `for_each_confirm_node.py` : un interrupt par exécution, tout état de boucle transite par le
> state (`for_each_hitl_ctx`, checkpointé AVANT l'interrupt suivant). Invariant garanti : **la
> liste que l'utilisateur a vue en dernier est exactement celle exécutée.** Le mapping
> `filtered_indices` est cumulatif et pointe toujours vers les items pré-exécutés d'origine ;
> le ctx est gardé par `plan_id` + `turn_id` (un ctx d'un turn abandonné ne matche jamais) et
> purgé au résultat final de l'orchestrateur.

> **v1.14.5 Change — Cancel Produces "OK, annule"**: When a user refuses a FOR_EACH HITL confirmation, the cancel result (now built by `for_each_confirm_node._cancel_result`, historically `_build_cancel_result()`) sets `draft_action_result` with `action: "cancel"` in the state. This triggers the response_node fast path (the same path used for draft cancellations), which produces a clean localized cancellation message (e.g., "OK, annule"). Previously, the cancel fell through to the initiative_node and response_node without proper context, producing broken or misleading error messages.

**Utilitaires FOR_EACH** :

```python
# apps/api/src/domains/agents/orchestration/for_each_utils.py

def parse_for_each_reference(ref: str) -> tuple[str, str]:
    """Extrait step_id et field_path depuis "$steps.get_contacts.contacts"."""
    ...

def get_for_each_provider_step_id(for_each_ref: str) -> str:
    """Extrait uniquement step_id depuis la référence FOR_EACH."""
    ...

def is_for_each_ready_for_expansion(
    for_each_ref: str,
    completed_steps: dict[str, Any]
) -> bool:
    """Vérifie si le provider step est complété et FOR_EACH peut être expand."""
    ...

def count_items_at_path(data: Any, field_path: str) -> int:
    """Compte le nombre d'items à la path spécifiée pour HITL pre-execution."""
    ...
```

**ExecutionStep DSL** :

```python
# Step qui itère sur les contacts trouvés
ExecutionStep(
    step_id="send_emails",
    tool_name="send_email_tool",
    for_each="$steps.get_contacts.contacts",  # Reference au provider
    for_each_max=10,  # Limite d'iterations
    parameters={
        "to": "$item.email",       # $item = current iteration item
        "subject": "Hello $item.name"
    }
)
```

**Severité HITL** :

| Situation | Sévérité | UI |
|-----------|----------|----|
| Mutation (send/update/delete) ≥1 item | CRITICAL | Rouge, confirmation explicite |
| Non-mutation ≥5 items | WARNING | Orange, advisory |
| Non-mutation ≥10 items | WARNING | Orange, HITL approval |

---

## 💬 Question Generation

### hitl_plan_approval_question_generator

**Fichier** : `apps/api/src/domains/agents/services/hitl/question_generator.py`

**Features** :
- **Multi-Provider** : OpenAI, Anthropic, DeepSeek, Perplexity, Ollama
- **Streaming** : TTFT < 200ms vs 2-4s blocking
- **Multilingue** : 6 langues (FR, EN, ES, DE, IT, ZH-CN)
- **Emojis** : 🔴 delete (danger), ⚠️ irreversible

**Prompt Key Rules** :
1. **Utiliser _display_label** : "Marie Martin", pas "people/c123"
2. **Ne jamais mentionner coûts** : Éviter stress utilisateur
3. **Emojis pour danger** : 🔴 delete, ⚠️ send/update
4. **Concis** : 2-4 phrases max
5. **Multilingue** : Détecter langue utilisateur automatiquement
6. **VARY structure** : Éviter "Tu veux continuer?" répétitif

**Examples** :

```
Recherche simple :
"Je vais rechercher les contacts contenant 'jean' (max 10 résultats).
 Besoin approbation. Je lance ?"

Suppression destructive :
"🔴 ATTENTION: suppression définitive de Jean Dupont. Irréversible. Tu confirmes ?"

Multi-step modification :
"⚠️ 3 étapes: (1) recherche 'startup' (max 20), (2-3) modification
 entreprise Sophie Durand + Marc Lefebvre → 'NewCorp'.
 Modifications multiples, autorisation requise. Je valide ?"
```

**Implémentation** :
```python
async def generate_plan_approval_question(
    plan_summary: PlanSummary,
    approval_reasons: list[str],
    user_language: str = "fr",
) -> str:
    """
    Génère une question d'approbation avec LLM.

    Args:
        plan_summary : Résumé du plan
        approval_reasons : Raisons de l'approbation
        user_language : Langue cible

    Returns:
        Question formatée markdown

    Performance:
        - Streaming : TTFT ~150ms
        - Blocking : ~2s
        - Tokens : ~200-300 input, ~100 output
    """
    # Load prompt
    prompt = load_prompt("hitl_plan_approval_question_prompt", version="v1")

    # Format context
    context = {
        "plan": plan_summary.dict(),
        "reasons": approval_reasons,
        "language": user_language,
    }

    # Create LLM
    llm = create_llm(llm_type="hitl_plan_approval_question_generator")

    # Invoke avec streaming
    full_question = ""
    async for chunk in llm.astream([
        SystemMessage(content=prompt),
        HumanMessage(content=json.dumps(context))
    ]):
        if hasattr(chunk, "content"):
            full_question += chunk.content

    # Markdown normalization (7 regex patterns)
    normalized = normalize_markdown(full_question)

    return normalized
```

---

## 🎯 Approval Strategies (removed in v1.21.16)

> **ADR-107**: the strategy evaluator (`services/approval/` —
> `ManifestBasedStrategy`, `CostThresholdStrategy`, `DataSensitivityStrategy`,
> `RoleBasedStrategy`, `CompositeStrategy`, `ApprovalEvaluator`) was removed:
> it was imported by nothing once `approval_gate_node` became a pass-through.
> The single live source of plan-time HITL truth is
> `manifest.permissions.hitl_required` consumed by the **plan validator**
> (`validation_result.requires_hitl`), and confirmation itself happens at
> tool level (draft_critique / for_each_confirmation — see ADR-106).

---

## 🚪 Approval Gate Node

**Fichier** : `apps/api/src/domains/agents/nodes/approval_gate_node.py`

> **v1.14.5 Change — Passthrough Mode**: The approval_gate_node no longer interrupts for plan-level HITL approval. It auto-approves all plans unconditionally because every mutation tool already has downstream HITL protection: FOR_EACH confirmation for bulk operations and draft_critique for individual actions (email sends, etc.). The plan-level approval was causing redundant double/triple confirmation prompts (plan approval + FOR_EACH + draft critique) which degraded UX. The node remains in the graph as a passthrough to preserve the architecture for future re-enablement if needed, but currently sets `plan_approved=True` immediately without evaluating strategies or generating LLM questions.

**Current Flow (pass-through)** :
```python
@track_metrics(node_name="approval_gate", ...)
async def approval_gate_node(state: MessagesState, config: RunnableConfig) -> dict[str, Any]:
    # 1. Already approved from clarification? -> return {"plan_approved": True}
    # 2. No execution_plan  -> {"plan_approved": False, "plan_rejection_reason": ...}
    # 3. No validation_result -> {"plan_approved": True}
    # 4. Otherwise: auto-approve (tool-level HITL supersedes plan-level)
    return {"plan_approved": True}
```

> **v1.21.16 (ADR-107)**: the dead plan-approval machinery this node used to
> carry (strategy evaluator, `PlanSummary` builder, LLM question generation,
> `PlanEditor` for EDIT decisions — none of it reachable since the node became
> a pass-through) was removed. The node file shrank from 626 to 130 lines.
> `PlanSummary`/`StepSummary` and `PlanApprovalInteraction` remain live: they
> are the HITL interaction registry's fallback for unknown `action_type`s.
> Re-enabling plan-level HITL means restoring an `interrupt()` here — the node
> is still wired in the graph, no rewiring needed.

---

## 🎭 HITL Orchestrator (removed in v1.21.16)

> **ADR-107**: `services/hitl_orchestrator.py` (987 lines) was a ghost service —
> instantiated during graph setup but never called afterwards (proven by running
> the full test suite with the module blocked at import time). It was removed
> together with its `hitl/policies/` package. The live equivalents are:
> - **Response classification / resumption**: `HitlResponseClassifier` +
>   `services/orchestration/service._parse_approval_decision()` +
>   `services/hitl/resumption_strategies.py` (replay-safe, ADR-092).
> - **Question generation**: `services/hitl/question_generator.py` streamed by
>   `StreamingService` through the interaction registry (`services/hitl/registry.py`).

---

## 💾 Configuration & Storage

### Variables .env - HITL Thresholds

| Variable | Default | Description |
|----------|---------|-------------|
| `HITL_CLASSIFIER_CONFIDENCE_THRESHOLD` | 0.7 | Seuil confidence classifier |
| `HITL_AMBIGUOUS_CONFIDENCE_THRESHOLD` | 0.7 | Seuil detection ambiguite |
| `HITL_FUZZY_MATCH_AMBIGUITY_THRESHOLD` | 0.05 | Seuil fuzzy match (scores dans 5% = ambigu) |
| `HITL_LOW_CONFIDENCE_THRESHOLD` | 0.5 | Seuil basse confidence → clarification |
| `HITL_PENDING_DATA_TTL_SECONDS` | 3600 | TTL Redis des données d'interrupt en attente |
| `HITL_DETECTION_CACHE_TTL_SECONDS` | 5 | TTL du cache mémoire de détection pending-HITL (borne la staleness cross-worker — ADR-132) |

### Variables .env - HITL Classifier LLM

| Variable | Default | Description |
|----------|---------|-------------|
| `HITL_CLASSIFIER_LLM_PROVIDER` | openai | Provider LLM |
| `HITL_CLASSIFIER_LLM_MODEL` | gpt-4.1-mini | Modele LLM |
| `HITL_CLASSIFIER_LLM_TEMPERATURE` | 0.2 | Temperature (basse = deterministic) |
| `HITL_CLASSIFIER_LLM_MAX_TOKENS` | 300 | Max tokens reponse |
| `HITL_CLASSIFIER_LLM_REASONING_EFFORT` | minimal | Effort raisonnement (o-series) |

### Variables .env - HITL Question Generator LLM

| Variable | Default | Description |
|----------|---------|-------------|
| `HITL_QUESTION_GENERATOR_LLM_PROVIDER` | openai | Provider LLM |
| `HITL_QUESTION_GENERATOR_LLM_MODEL` | gpt-4.1-nano | Modele LLM (fast) |
| `HITL_QUESTION_GENERATOR_LLM_TEMPERATURE` | 0.5 | Temperature (creative questions) |
| `HITL_QUESTION_GENERATOR_LLM_FREQUENCY_PENALTY` | 0.7 | Penalite frequence (evite repetition) |
| `HITL_QUESTION_GENERATOR_LLM_PRESENCE_PENALTY` | 0.3 | Penalite presence (diversite) |
| `HITL_QUESTION_GENERATOR_LLM_MAX_TOKENS` | 500 | Max tokens reponse |
| `HITL_QUESTION_GENERATOR_LLM_REASONING_EFFORT` | minimal | Effort raisonnement (o-series) |

### Variables .env - HITL Plan Approval Question LLM

| Variable | Default | Description |
|----------|---------|-------------|
| `HITL_PLAN_APPROVAL_QUESTION_LLM_PROVIDER` | openai | Provider LLM |
| `HITL_PLAN_APPROVAL_QUESTION_LLM_MODEL` | gpt-4.1-mini | Modele LLM |
| `HITL_PLAN_APPROVAL_QUESTION_LLM_TEMPERATURE` | 0.5 | Temperature |
| `HITL_PLAN_APPROVAL_QUESTION_LLM_FREQUENCY_PENALTY` | 0.7 | Penalite frequence |
| `HITL_PLAN_APPROVAL_QUESTION_LLM_PRESENCE_PENALTY` | 0.3 | Penalite presence |
| `HITL_PLAN_APPROVAL_QUESTION_LLM_MAX_TOKENS` | 500 | Max tokens reponse |
| `HITL_PLAN_APPROVAL_QUESTION_LLM_REASONING_EFFORT` | minimal | Effort raisonnement (o-series) |

### HITL Config

**Fichier** : `apps/api/src/domains/agents/utils/hitl_config.py`

```python
# Single source of truth : Tool manifests
def requires_approval(tool_name: str) -> bool:
    """Check if tool requires HITL approval."""
    manifest = get_tool_manifest(tool_name)
    return manifest.permissions.hitl_required if manifest else False

# Global kill switch
TOOL_APPROVAL_ENABLED = settings.tool_approval_enabled  # Default: True
```

### HITL Store (Redis)

**Fichier** : `apps/api/src/domains/agents/utils/hitl_store.py`

```python
class HITLStore:
    def __init__(self, redis: Redis):
        self.redis = redis

    async def save_interrupt(
        self,
        conversation_id: str,
        interrupt_data: dict,
        schema_version: str = "1.0",
    ):
        """Save interrupt avec schema_version pour migrations."""
        key = f"hitl_interrupt:{conversation_id}"
        data = {
            **interrupt_data,
            "schema_version": schema_version,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        await self.redis.setex(key, 3600, json.dumps(data))  # TTL 1h

    async def get_interrupt(self, conversation_id: str) -> dict | None:
        """Retrieve + auto-migration (v0→v1)."""
        key = f"hitl_interrupt:{conversation_id}"
        data = await self.redis.get(key)

        if not data:
            return None

        interrupt = json.loads(data)

        # Auto-migration
        if interrupt.get("schema_version") == "0.0":
            interrupt = migrate_interrupt_0_to_1(interrupt)

        return interrupt
```

### Database - plan_approvals Table

> **Note (v1.21.16)**: the table exists (migration 2025-11-09) but has never
> had a writer — the pass-through approval gate never audits. Kept as-is;
> candidate for a future migration cleanup.

```sql
CREATE TABLE plan_approvals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id VARCHAR(255) NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id),
    conversation_id UUID NOT NULL REFERENCES conversations(id),

    -- Plan details
    plan_summary JSONB NOT NULL,
    strategies_triggered TEXT[],

    -- Decision
    decision VARCHAR(20) NOT NULL,  -- APPROVE, REJECT, EDIT, REPLAN
    decision_timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    modifications JSONB,
    rejection_reason TEXT,

    -- Metrics
    approval_latency_seconds FLOAT,  -- Time to decision
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Indexes
    INDEX idx_user_id (user_id),
    INDEX idx_conversation_id (conversation_id),
    INDEX idx_decision (decision),
    INDEX idx_decision_timestamp (decision_timestamp),
    INDEX idx_user_decision_timestamp (user_id, decision, decision_timestamp)
);
```

---

## 📊 Métriques

### Plan-Level Metrics

```python
# apps/api/src/infrastructure/observability/metrics_agents.py

# Question generation (live — streamed by StreamingService)
hitl_plan_approval_question_duration = Histogram(
    "hitl_plan_approval_question_duration_seconds",
    "LLM question generation time",
    buckets=[0.1, 0.2, 0.5, 1, 2, 5, 10]
)


> **v1.21.16 (ADR-107)**: `hitl_plan_approval_requests_total`,
> `hitl_plan_decisions_total`, `hitl_plan_approval_latency_seconds` and
> `hitl_plan_approval_question_fallback_total` were removed (orphaned —
> only the deleted framework incremented them).

# Modifications
hitl_plan_modifications = Counter(
    "hitl_plan_modifications_total",
    "Plan modifications (EDIT)",
    ["modification_type"]  # parameter_change, step_removed, etc.
)
```

### Tool-Level Metrics (Legacy, Phase 7) — SUPPRIMÉES

> Vérifié le 2026-07-20 : **ces quatre métriques n'existent plus** dans le code.
> Elles étaient annoncées ici comme « conservées pour rétrocompatibilité », mais
> aucune n'est définie — un tableau Grafana ou une requête PromQL bâtis dessus
> restent vides sans erreur.
>
> ```python
> # N'EXISTENT PAS : hitl_user_response_time_seconds, hitl_tool_rejections_by_reason,
> #                 hitl_rejection_type_total, hitl_edit_actions_total
> ```
>
> Métriques HITL réellement définies (`metrics_agents.py`) : `hitl_clarification_requests_total`,
> `hitl_clarification_fallback_total`, `hitl_classification_duration_seconds`,
> `hitl_classification_method_total`, `hitl_classification_demoted_total`,
> `hitl_for_each_decisions_total`, `hitl_for_each_approval_latency_seconds`,
> `hitl_for_each_pre_execution_duration_seconds`.
> Liste à jour : `grep -rhoE '"hitl_[a-z_]*"' apps/api/src --include=*.py | sort -u`.

---

## 🔄 Migration Phase 7 → Phase 8

### Key Changes

| Aspect | Phase 7 | Phase 8 |
|--------|---------|---------|
| **Interrupt Timing** | Mid-execution (per tool) | Before execution (plan-level) |
| **User Visibility** | One tool at a time | Complete plan overview |
| **Edit Capability** | Limited | Full parameter editing |
| **Validation** | Tool-by-tool | Centralized plan validator |
| **Performance** | N interrupts | 1 interrupt |
| **UX** | Unexpected pauses | Transparent plan presentation |

### Backward Compatibility

- Tool-level HITL metadata preserved in manifests
- Legacy metrics still recorded
- Old interrupt format auto-migrated (v0→v1)
- Phase 7 code paths marked deprecated

### Migration Checklist

- [ ] Update all ToolManifests avec `permissions.hitl_required`
- [ ] Configure approval strategies in settings
- [ ] Set `approval_cost_threshold_usd`
- [ ] Test EDIT flow avec PlanEditor
- [ ] Verify plan_approvals table created (Alembic migration)
- [ ] Update Grafana dashboard pour plan-level metrics
- [ ] Document new HITL flow pour users

---

## 📚 Références

### Documentation Interne
- [GRAPH_AND_AGENTS_ARCHITECTURE.md](./GRAPH_AND_AGENTS_ARCHITECTURE.md) - Approval Gate Node
- [AGENT_MANIFEST.md](./AGENT_MANIFEST.md) - ToolManifest permissions
- [OBSERVABILITY_AGENTS.md](./OBSERVABILITY_AGENTS.md) - HITL metrics

### Fichiers Clés
- `apps/api/src/domains/agents/nodes/approval_gate_node.py`
- `apps/api/src/domains/agents/services/hitl/question_generator.py`
- `apps/api/src/domains/agents/services/hitl/` (interactions, registry, resumption)

### Phase 8 Documents
- Documents Phase 8 historiques supprimés du repo — voir [ADR-008 dans ADR_INDEX.md](../architecture/ADR_INDEX.md#adr-008-hitl-plan-level-approval-phase-8)

---

---

## 🆕 HITL Dispatch Node (Phase 7 - Generic Dispatcher)

**Fichier** : `apps/api/src/domains/agents/nodes/hitl_dispatch_node.py` (852 lignes)

Le `hitl_dispatch_node` est un dispatcher HITL générique qui combine 3 types d'interactions en un seul point d'entrée avec priorité ordering.

### Architecture

```python
@node_with_metrics(node_name="hitl_dispatch")
async def hitl_dispatch_node(state: MessagesState) -> dict:
    """
    Generic HITL dispatcher combining 3 interaction types.

    Priority Order (highest first):
        1. draft_critique - User reviews generated content before send
        2. entity_disambiguation - User clarifies which entity (multiple matches)
        3. tool_confirmation - User confirms sensitive action

    This pattern replaces multiple individual HITL nodes with a single
    unified dispatcher that determines which type of HITL is needed.
    """
```

### Interaction Types

| Type | Priority | Use Case | Example |
|------|----------|----------|---------|
| **draft_critique** | 1 (highest) | Review content before send | "Voici l'email, tu veux que je l'envoie?" |
| **entity_disambiguation** | 2 | Multiple matches found | "J'ai trouvé 3 Jean, lequel?" |
| **tool_confirmation** | 3 | Sensitive operation | "Supprimer ce contact?" |

### Boucle draft critique replay-safe (v1.21.x)

Historiquement `_handle_draft_critique` bouclait en interne autour de `interrupt()` : au resume,
LangGraph ré-exécute le **nœud entier**, donc chaque décision utilisateur rejouait toutes les
modifications LLM passées (`DraftModificationService.modify`, non déterministe) — le contenu
envoyé pouvait diverger de la dernière version affichée. La boucle est désormais **single-pass** :

- **UN `interrupt()` par exécution de nœud** ; toute continuation passe par le state
  (`pending_draft_critique`, `draft_edit_iteration`, `draft_clarification_question`) qui est
  **checkpointé avant l'interrupt suivant** ;
- `edit` → `modify()` s'exécute UNE fois, le draft modifié est persisté, puis **self-loop** via
  `route_from_hitl_dispatch` (le nœud se ré-exécute et présente le draft modifié dans un nouvel
  interrupt) ; idem `replan` (retypage du draft) et `clarify` (la question est persistée et
  affichée avec le draft au payload suivant) ;
- `confirm` / `cancel` → résultat terminal, les clés de boucle sont réinitialisées
  (`_loop_reset`) et le routage sort vers `initiative` ;
- garde de sécurité : `draft_edit_iteration >= settings.api_max_items_per_request` → cancel.

**Invariant garanti : le contenu exécuté est exactement le dernier contenu affiché à
l'utilisateur.** Le nœud `for_each_confirm` applique le même design pour les confirmations bulk
(voir la section FOR_EACH Confirmation).

### Fichiers HITL Interactions

```
services/hitl/interactions/
├── draft_critique.py (~900 lines) - Draft review logic
├── entity_disambiguation.py (~315 lines) - Multiple match resolution
├── tool_confirmation.py (~260 lines) - Sensitive action confirmation
├── plan_approval.py (~305 lines) - Plan-level approval
├── clarification.py (~300 lines) - Clarification questions
├── for_each_confirmation.py (~500 lines) - Bulk iteration confirmation
└── destructive_confirm.py (~430 lines) - Bulk destructive confirmation
```

### Unified per-item preview rendering (ADR-085 extension)

Both `DraftCritiqueInteraction._generate_batch_critique` (batch confirmation) and `ForEachConfirmationInteraction._build_item_previews_section` (FOR_EACH informed HITL) render the per-item bullet list via a single helper:

```python
from src.core.i18n_drafts import format_hitl_item_preview

row = format_hitl_item_preview(
    draft_type=draft_type,    # e.g. "reminder_delete"
    content=draft_content,    # the draft's typed content dict
    language=user_language,
    user_timezone=user_timezone,
)
# → "🔔 Rappel : Médecin - dimanche 17 mai 2026 à 19:00"
```

The helper consumes `DRAFT_DISPLAY_REGISTRY` (see ADR-085) for emoji, label-extraction fields, optional secondary datetime, and the localized capitalized noun. Output format is invariant across the two paths: `{emoji} {Noun_capitalized} : {label} - {datetime_with_day_name}`. For `ForEachConfirmationInteraction`, a static helper `_steps_to_draft_type(steps)` resolves the FOR_EACH `tool_name` to a canonical `DraftType` string (e.g. `cancel_reminder_tool` → `"reminder_delete"`); when the mapping fails (non-draft domains like places/weather/routes), a legacy generic renderer takes over.

### Draft Modification Service (v1.11.4)

**File**: `apps/api/src/domains/agents/services/hitl/draft_modifier.py`

When a user requests changes during draft critique (e.g., "non envoi à user@example.com"), the `DraftModificationService` regenerates the draft content via LLM. The service uses a three-layer approach for recipient changes:

1. **LLM-based modification** — The `draft_modifier_prompt.txt` instructs the LLM to modify all content fields including `to`/`cc` when the user explicitly requests it.
2. **Explicit recipient override (post-processing)** — `_apply_explicit_recipient_override()` detects email addresses in user instructions via regex. If the LLM failed to change the `to` field, the extracted email is applied directly. This handles cases where the LLM ignores recipient change instructions.
3. **Contact name resolution (fallback)** — If no email is found in instructions, the service matches contact names against the `contact_context` (from the user's connected accounts) and resolves to the first email address.

**Observability** (debug level):
- `draft_modification_prompt_built` — System prompt preview sent to LLM
- `draft_modification_llm_raw_response` — Raw LLM output for diagnosis
- `draft_modification_completed` with `actual_changes` — Fields that truly changed (not just returned by LLM)

---

## 🔄 Resumption Strategies (Advanced HITL)

**Fichier** : `apps/api/src/domains/agents/services/hitl/resumption_strategies.py` (1,437 lignes)

Le système de resumption strategies gère la reprise du graphe après une interruption HITL avec plusieurs stratégies de fallback.

### Architecture

```python
class ResumptionStrategyManager:
    """
    Manages plan resumption after HITL interrupts.

    Strategies (in order of preference):
        1. DirectResumption - Continue from exact checkpoint
        2. StateReconstruction - Rebuild state from DB
        3. PartialReexecution - Re-run failed steps only
        4. FullReplan - Generate new plan entirely
    """
```

### Strategies

| Strategy | Use Case | Performance |
|----------|----------|-------------|
| **DirectResumption** | Checkpoint valid, state intact | ~50ms |
| **StateReconstruction** | Checkpoint corrupted, DB available | ~200ms |
| **PartialReexecution** | Some steps failed, retry needed | ~1-5s |
| **FullReplan** | Context changed significantly | ~3-8s |

### Context Preservation

```python
class ResumptionContext:
    """Context preserved across HITL interrupts."""

    checkpoint_id: str           # LangGraph checkpoint ID
    interrupt_timestamp: datetime
    pending_steps: list[str]     # Steps not yet executed
    completed_steps: dict        # Results from completed steps
    user_decision: str           # APPROVE/REJECT/EDIT
    modifications: list[dict]    # User edits to parameters

    def can_direct_resume(self) -> bool:
        """Check if direct resumption is possible."""
        return (
            self.checkpoint_valid() and
            self.state_not_expired() and
            not self.context_changed_significantly()
        )
```

---

## 🔍 Insufficient Content Detection (Early HITL)

**Fichier** : `apps/api/src/domains/agents/services/smart_planner_service.py`

Le système détecte **AVANT** la génération du plan si les paramètres obligatoires sont manquants, évitant ainsi un appel LLM inutile.

### Architecture

```
User: "envoie un email à ma femme"
    │
    ▼
SmartPlannerService.detect_early_insufficient_content()
    │
    ├──▶ Reference resolved? "ma femme" → "Marie Dupont" ✓
    │
    ├──▶ Email resolvable? "Marie Dupont" → email via Google Contacts
    │    (runtime_helpers.resolve_contact_to_email)
    │
    ├──▶ Missing required params?
    │    • to: ✓ (resolved)
    │    • subject: ✗ MISSING
    │    • body: ✗ MISSING
    │
    ▼
semantic_validation = {
    "requires_clarification": True,
    "clarification_questions": ["Quel est le sujet de l'email?"],
    "clarification_field": "subject",  # Field being asked
    "issues": ["missing_parameter"]
}
    │
    ▼
Route: planner → semantic_validator → clarification_node
    │
    ▼
User provides subject → Replan → Ask for body → Replan → Execute
```

### Détection des Champs Manquants

```python
async def detect_early_insufficient_content(
    self,
    intelligence: QueryIntelligence,
    config: RunnableConfig | None = None,
) -> SemanticValidationResult | None:
    """
    Détecte si des paramètres obligatoires sont manquants AVANT le LLM.

    Returns:
        SemanticValidationResult si clarification requise, None sinon.
    """
    # Email domain: check to, subject, body
    if "emails" in intelligence.domains:
        if intelligence.immediate_intent in ["send", "create"]:
            # Check if 'to' is resolvable
            recipient = intelligence.resolved_references.get("recipient")
            if recipient:
                # Resolve name → email via Google Contacts
                email = await resolve_contact_to_email(runtime, recipient)
                if not email:
                    return self._build_clarification_result(
                        field="to",
                        question="Je n'ai pas trouvé d'email pour ce contact."
                    )

            # Check subject
            if not self._has_subject_in_query(intelligence):
                return self._build_clarification_result(
                    field="subject",
                    question="Quel est le sujet de l'email?"
                )

            # Check body
            if not self._has_body_in_query(intelligence):
                return self._build_clarification_result(
                    field="body",
                    question="Quel est le contenu de l'email?"
                )

    return None  # No missing params, proceed to LLM planning
```

### Skill Guard Bypass

Early detection is **skipped** when `QueryAnalyzer` has semantically identified a skill (deterministic or non-deterministic). The guard function `_has_potential_skill_match()` in `planner_node_v3.py` simply checks the presence of `QueryIntelligence.detected_skill_name`. When set, the full planner pipeline decides — `SkillBypassStrategy` for deterministic skills, LLM planner for the rest — rather than short-circuiting to clarification.

See [Skills Integration Guide — Early Detection Guard](SKILLS_INTEGRATION.md#6-early-detection-guard) for details.

### Clarification Multi-Turn

Le système supporte des clarifications successives pour collecter tous les paramètres :

```
Turn 1: "envoie un email à ma femme"
        → Missing: subject, body
        → Ask: "Quel est le sujet?"

Turn 2: "pour son anniversaire"
        → subject ✓, Missing: body
        → Ask: "Quel est le contenu?"

Turn 3: "Joyeux anniversaire mon amour"
        → body ✓, All params complete
        → Generate plan → Execute
```

### State Keys

```python
# apps/api/src/domains/agents/constants.py

STATE_KEY_CLARIFICATION_RESPONSE = "clarification_response"  # User answer
STATE_KEY_CLARIFICATION_FIELD = "clarification_field"        # Field asked (subject, body, to)
STATE_KEY_NEEDS_REPLAN = "needs_replan"                      # Trigger replanning
STATE_KEY_SEMANTIC_VALIDATION = "semantic_validation"        # Validation result
```

### Iteration Protection

```python
# Prevent infinite clarification loops
STATE_KEY_PLANNER_ITERATION = "planner_iteration"

# Max replans before forcing execution
PLANNER_MAX_REPLANS = 5  # From settings

# NOTE: User clarifications do NOT increment planner_iteration
# Only auto-replans (semantic_validator fixes) increment it
```

---

## 🔀 Clarification Node

**Fichier** : `apps/api/src/domains/agents/nodes/clarification_node.py`

Le `clarification_node` gère les interruptions HITL pour les clarifications sémantiques.

### Flow

```
semantic_validator_node
    │
    ├──▶ requires_clarification=True?
    │    ▼
    │    route_from_semantic_validator → "clarification"
    │
    ▼
clarification_node
    │
    ├──▶ Build interrupt payload
    │    • clarification_questions
    │    • semantic_issues
    │    • user_language
    │
    ├──▶ interrupt() ─────────────────────┐
    │                                      │
    │    [User sees question via SSE]      │
    │    [User responds]                   │
    │    [Frontend: Command(resume={...})] │
    │                                      │
    ◀──────────────────────────────────────┘
    │
    ├──▶ Extract clarification_response
    │
    ├──▶ Determine if confirmation-only or info clarification:
    │    • DANGEROUS_AMBIGUITY, IMPLICIT_ASSUMPTION → confirmation-only
    │    • missing_parameter, cardinality → info clarification
    │
    ▼
    Return state updates:
    • clarification_response: "user answer"
    • clarification_field: "subject"
    • needs_replan: True/False
    • plan_approved: True (if confirmation-only)
```

### Issue Type Handling

| Issue Type | Action | needs_replan | plan_approved |
|------------|--------|--------------|---------------|
| `DANGEROUS_AMBIGUITY` | User confirms | False | True |
| `IMPLICIT_ASSUMPTION` | User confirms | False | True |
| `missing_parameter` | User provides info | True | - |
| `cardinality_mismatch` | User clarifies | True | - |

### Implementation

```python
async def clarification_node(
    state: dict[str, Any],
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """
    HITL node for semantic validation clarification.

    Interrupts execution when semantic validation detects issues
    requiring user clarification.
    """
    semantic_validation = state.get("semantic_validation")
    requires_clarification = validation_dict.get("requires_clarification", False)

    if not requires_clarification:
        return state  # No-op

    # Build interrupt payload
    interrupt_payload = {
        "action_requests": [{
            "type": "clarification",
            "clarification_questions": clarification_questions,
            "semantic_issues": semantic_issues,
        }],
        "user_language": user_language,
    }

    # Trigger interrupt - workflow pauses
    clarification_data = interrupt(interrupt_payload)

    # Extract response from Command(resume={...})
    clarification_response = clarification_data.get("clarification", "")

    # Determine if confirmation-only or needs replan
    CONFIRMATION_ONLY_ISSUES = {"dangerous_ambiguity", "implicit_assumption"}
    all_confirmation_only = all(
        issue_type in CONFIRMATION_ONLY_ISSUES
        for issue_type in [extract_issue_type(i) for i in issues]
    )

    if all_confirmation_only:
        # User confirmed, proceed to execution
        return {
            STATE_KEY_CLARIFICATION_RESPONSE: clarification_response,
            STATE_KEY_CLARIFICATION_FIELD: clarification_field,
            STATE_KEY_NEEDS_REPLAN: False,
            STATE_KEY_PLAN_APPROVED: True,
        }
    else:
        # User provided new info, regenerate plan
        return {
            STATE_KEY_CLARIFICATION_RESPONSE: clarification_response,
            STATE_KEY_CLARIFICATION_FIELD: clarification_field,
            STATE_KEY_NEEDS_REPLAN: True,
        }
```

### Routing Integration

```python
# apps/api/src/domains/agents/nodes/routing.py

def route_from_semantic_validator(state: dict) -> str:
    """Route after semantic validation."""
    validation = state.get("semantic_validation")

    if validation and validation.get("requires_clarification"):
        return "clarification"

    if validation and not validation.get("is_valid"):
        # Auto-replan for fixable issues
        return "planner"

    return "approval_gate"
```

---

## Telegram HITL (evolution F3)

> Depuis la phase evolution F3, les interactions HITL sont aussi disponibles via Telegram grâce à des **inline keyboards** avec boutons localisés en 6 langues.

### Types HITL et Inline Keyboards

Les 6 types HITL se divisent en deux catégories pour Telegram :

| Type HITL | Mode Telegram | Boutons |
|-----------|--------------|---------|
| `plan_approval` | Inline Keyboard | Approuver / Rejeter |
| `destructive_confirm` | Inline Keyboard | Confirmer / Annuler |
| `for_each_confirm` | Inline Keyboard | Continuer / Arrêter |
| `clarification` | Texte libre | — (réponse texte) |
| `draft_critique` | Texte libre | — (réponse texte) |
| `modifier_review` | Texte libre | — (réponse texte) |

### Callback Data Format

```
hitl:{action}:{conversation_id}
```

Exemples :
- `hitl:approve:550e8400-e29b-41d4-a716-446655440000`
- `hitl:reject:550e8400-e29b-41d4-a716-446655440000`

### Boutons Localisés (6 langues)

```python
# infrastructure/channels/telegram/hitl_keyboard.py
HITL_BUTTON_LABELS = {
    "approve":  {"fr": "Approuver",  "en": "Approve",  "es": "Aprobar",  ...},
    "reject":   {"fr": "Rejeter",    "en": "Reject",   "es": "Rechazar", ...},
    "confirm":  {"fr": "Confirmer",  "en": "Confirm",  "es": "Confirmar", ...},
    "cancel":   {"fr": "Annuler",    "en": "Cancel",   "es": "Cancelar", ...},
    "continue": {"fr": "Continuer",  "en": "Continue", "es": "Continuar", ...},
    "stop":     {"fr": "Arrêter",    "en": "Stop",     "es": "Detener",  ...},
}
```

### Flow Telegram HITL

```
1. Agent pipeline atteint ApprovalGateNode
2. InboundMessageHandler détecte pending_hitl dans le state
3. build_hitl_keyboard() génère InlineKeyboardMarkup
4. TelegramSender envoie le message + keyboard au chat
5. Utilisateur clique un bouton → Telegram envoie callback_query
6. Webhook handler → parse_hitl_callback_data() → extrait (action, conversation_id)
7. Router background task → resume_hitl() avec la réponse utilisateur
8. Pipeline agent reprend depuis le checkpoint
```

> Voir [CHANNELS_INTEGRATION.md](./CHANNELS_INTEGRATION.md) pour l'architecture complète du module channels.

---

## 📊 HITL Services Summary

| Service | Lines | Purpose |
|---------|-------|---------|
| ~~hitl_orchestrator.py~~ | — | **SUPPRIMÉ (ADR-107)** — ghost service jamais câblé (cf. §ADR-107 plus haut). La coordination HITL passe par `hitl_classifier.py` + le contrat de resume, pas par un orchestrateur central. |
| hitl_classifier.py | 801 | User response classification |
| question_generator.py | 766 | LLM question generation |
| resumption_strategies.py | 1,437 | **Plan resumption logic** |
| draft_modifier.py | 480 | Draft editing during HITL (v1.11.4: recipient override post-processing, debug logging) |
| validator.py | 464 | HITL security validation |
| schema_validator.py | 322 | Schema compliance |
| parameter_enrichment.py | 337 | Parameter enrichment |
| registry.py | 267 | HITL interaction registry |
| hitl_keyboard.py | 158 | Telegram inline keyboards (evolution F3) |
| **Total** | **~6,400** | |

---

**HITL.md** - Version 2.3 - v1.14.5 - April 2026

*Human-in-the-Loop Plan-Level Approval System with Destructive Confirm + Unified Schemas + Telegram Inline Keyboards + Approval Gate Passthrough + Action-Specific Titles*
