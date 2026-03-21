# Human-in-the-Loop (HITL) - Architecture Phase 8

> Système d'approbation plan-level avant exécution avec génération de questions LLM multilingues
>
> Version: 8.3 (Janvier 2026 - FOR_EACH Confirmation + HITL Consolidation + Destructive Confirm)
> Date: 2026-01-22

## 📋 Table des Matières

- [Vue d'Ensemble](#vue-densemble)
- [Architecture 6 Couches](#architecture-6-couches)
- [Schemas & Structures](#schemas--structures)
- [Nouveaux Composants Phase 8.1](#-nouveaux-composants-phase-81)
  - [Unified Schemas (schemas.py)](#unified-schemas-schemaspy)
  - [Scope Detector (scope_detector.py)](#scope-detector-scope_detectorpy)
  - [Destructive Confirm (destructive_confirm.py)](#destructive-confirm-destructive_confirmpy)
  - [FOR_EACH Confirmation (for_each_confirmation.py)](#for_each-confirmation-for_each_confirmationpy)
- [Question Generation](#question-generation)
- [Approval Strategies](#approval-strategies)
- [Approval Gate Node](#approval-gate-node)
- [HITL Orchestrator](#hitl-orchestrator)
- [Configuration & Storage](#configuration--storage)
- [Métriques](#métriques)
- [Migration Phase 7 → Phase 8](#migration-phase-7--phase-8)

---

## 🎯 Vue d'Ensemble

Le système HITL (Human-in-the-Loop) de LIA permet d'**interrompre l'exécution pour demander l'approbation utilisateur** avant d'effectuer des actions à risque.

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

---

## 🏗️ Architecture 6 Couches

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

class PlanApprovalRequest(BaseModel):
    """Requête d'approbation présentée à l'utilisateur."""
    plan_summary: PlanSummary
    approval_reasons: list[str]  # ["Coût élevé", "Action destructive"]
    strategies_triggered: list[str]  # ["ManifestBasedStrategy", "CostThresholdStrategy"]
    user_message: str  # Question LLM générée

class PlanApprovalDecision(BaseModel):
    """Décision utilisateur."""
    decision: Literal["APPROVE", "REJECT", "EDIT", "REPLAN"]
    rejection_reason: str | None
    modifications: list[dict] | None  # [{step_id, field, new_value}]
    replan_instructions: str | None
    decided_at: datetime

class ApprovalEvaluation(BaseModel):
    """Résultat de l'évaluation des stratégies."""
    requires_approval: bool
    reasons: list[str]
    strategies_triggered: list[str]
    details: dict[str, Any]
```

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

**Architecture** :
```
Planner génère ExecutionStep avec for_each
    → Parallel Executor détecte FOR_EACH pattern
    → count_items_at_path() compte les items
    → Évalue thresholds (mutation vs non-mutation)
    → Si threshold dépassé → FOR_EACH_CONFIRMATION HITL
    → Utilisateur voit preview des items affectés
    → Approve/Reject → Continue ou abort
```

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

## 🎯 Approval Strategies

### 1. ManifestBasedStrategy (PRINCIPALE)

```python
# apps/api/src/domains/agents/services/approval/strategies.py

class ManifestBasedStrategy:
    """
    Stratégie basée sur manifest.permissions.hitl_required.

    Source de vérité unique : ToolManifest.
    """

    def evaluate(self, plan: ExecutionPlan, context: dict) -> ApprovalEvaluation:
        requires_approval = False
        reasons = []

        for step in plan.steps:
            manifest = get_tool_manifest(step.tool_name)

            if manifest and manifest.permissions.hitl_required:
                requires_approval = True
                reasons.append(f"Tool '{step.tool_name}' requires approval (manifest)")

            # Step-level override
            if step.approvals_required:
                requires_approval = True
                reasons.append(f"Step '{step.step_id}' marked as requiring approval")

        return ApprovalEvaluation(
            requires_approval=requires_approval,
            reasons=reasons,
            strategies_triggered=["ManifestBasedStrategy"],
            details={}
        )
```

### 2. CostThresholdStrategy

```python
class CostThresholdStrategy:
    """Déclenche si cost > threshold."""

    def __init__(self, threshold: float = 0.50):
        self.threshold = threshold

    def evaluate(self, plan: ExecutionPlan, context: dict) -> ApprovalEvaluation:
        if plan.estimated_cost_usd > self.threshold:
            return ApprovalEvaluation(
                requires_approval=True,
                reasons=[f"Plan cost ${plan.estimated_cost_usd:.2f} exceeds threshold ${self.threshold:.2f}"],
                strategies_triggered=["CostThresholdStrategy"],
                details={"cost": plan.estimated_cost_usd}
            )

        return ApprovalEvaluation(requires_approval=False, reasons=[], strategies_triggered=[], details={})
```

### 3. DataSensitivityStrategy

```python
class DataSensitivityStrategy:
    """Déclenche si data classification sensible."""

    def __init__(self, sensitive_classifications: list[str] = None):
        self.sensitive = sensitive_classifications or ["sensitive", "pii", "financial"]

    def evaluate(self, plan: ExecutionPlan, context: dict) -> ApprovalEvaluation:
        for step in plan.steps:
            manifest = get_tool_manifest(step.tool_name)
            if manifest and manifest.data_classification in self.sensitive:
                return ApprovalEvaluation(
                    requires_approval=True,
                    reasons=[f"Step '{step.step_id}' handles sensitive data"],
                    strategies_triggered=["DataSensitivityStrategy"],
                    details={"classification": manifest.data_classification}
                )

        return ApprovalEvaluation(requires_approval=False, reasons=[], strategies_triggered=[], details={})
```

### 4. RoleBasedStrategy

```python
class RoleBasedStrategy:
    """Auto-approve pour certains rôles (admin, power users)."""

    def __init__(self, auto_approve_roles: list[str] = None):
        self.auto_approve_roles = auto_approve_roles or ["admin", "power_user"]

    def evaluate(self, plan: ExecutionPlan, context: dict) -> ApprovalEvaluation:
        user_role = context.get("user_role", "user")

        if user_role in self.auto_approve_roles:
            return ApprovalEvaluation(
                requires_approval=False,
                reasons=[f"User role '{user_role}' auto-approved"],
                strategies_triggered=["RoleBasedStrategy"],
                details={"auto_approved": True}
            )

        return ApprovalEvaluation(requires_approval=False, reasons=[], strategies_triggered=[], details={})
```

### 5. CompositeStrategy

```python
class CompositeStrategy:
    """Combine multiple strategies avec AND/OR logic."""

    def __init__(self, strategies: list[ApprovalStrategy], logic: Literal["AND", "OR"] = "OR"):
        self.strategies = strategies
        self.logic = logic

    def evaluate(self, plan: ExecutionPlan, context: dict) -> ApprovalEvaluation:
        evaluations = [s.evaluate(plan, context) for s in self.strategies]

        if self.logic == "OR":
            # Déclenche si AU MOINS UNE stratégie = True
            requires = any(e.requires_approval for e in evaluations)
        else:  # AND
            # Déclenche si TOUTES les stratégies = True
            requires = all(e.requires_approval for e in evaluations)

        all_reasons = [r for e in evaluations for r in e.reasons]
        all_strategies = [s for e in evaluations for s in e.strategies_triggered]

        return ApprovalEvaluation(
            requires_approval=requires,
            reasons=all_reasons,
            strategies_triggered=all_strategies,
            details={"logic": self.logic}
        )
```

---

## 🚪 Approval Gate Node

**Fichier** : `apps/api/src/domains/agents/nodes/approval_gate_node.py`

**Complete Flow** :
```python
@node_with_metrics(node_name=NODE_APPROVAL_GATE)
async def approval_gate_node(state: MessagesState) -> dict:
    """
    Approval Gate : HITL plan-level approval.

    Flow :
        1. Evaluate strategies
        2. IF requires_approval:
            a. Build PlanSummary
            b. Generate LLM question
            c. Interrupt user (NodeInterrupt)
            d. Wait for decision
            e. Process decision
        3. Return state updates
    """
    plan = state["execution_plan"]

    if not plan:
        return {}

    # 1. Evaluate approval strategies
    evaluator = ApprovalEvaluator(strategies=[
        ManifestBasedStrategy(),
        CostThresholdStrategy(threshold=settings.approval_cost_threshold_usd),
    ])

    evaluation = evaluator.evaluate(plan, context={
        "user_id": state["metadata"]["user_id"],
        "user_timezone": state["user_timezone"],
        "user_language": state["user_language"],
    })

    # 2. Store evaluation
    state_updates = {"approval_evaluation": evaluation}

    # 3. Check if approval required
    if not evaluation.requires_approval:
        logger.info("approval_gate_auto_approved", reasons=evaluation.reasons)
        hitl_plan_decisions.labels(decision="AUTO_APPROVE").inc()
        return {**state_updates, "plan_approved": True}

    # 4. Build plan summary
    plan_summary = _build_plan_summary(plan, state)

    # 5. Generate LLM question
    question = await _build_approval_request(
        plan_summary,
        evaluation,
        state["user_language"]
    )

    # 6. Store approval request in DB
    await store_approval_request(
        plan_id=plan.plan_id,
        user_id=state["metadata"]["user_id"],
        plan_summary=plan_summary,
        evaluation=evaluation,
    )

    # 7. Interrupt user
    logger.info("approval_gate_interrupt", question_length=len(question))

    raise NodeInterrupt(
        value={
            "type": "plan_approval",
            "question": question,
            "plan_summary": plan_summary.dict(),
            "approval_reasons": evaluation.reasons,
        }
    )

    # 8. After resumption, process decision
    # (code below runs when graph is resumed)
    decision = state.get("plan_approved")

    if decision is True:
        logger.info("approval_gate_approved")
        hitl_plan_decisions.labels(decision="APPROVE").inc()

        await store_approval_decision(
            plan_id=plan.plan_id,
            decision="APPROVE",
        )

        return {**state_updates, "plan_approved": True}

    elif decision is False:
        reason = state.get("plan_rejection_reason", "User rejected")
        logger.info("approval_gate_rejected", reason=reason)
        hitl_plan_decisions.labels(decision="REJECT").inc()

        await store_approval_decision(
            plan_id=plan.plan_id,
            decision="REJECT",
            rejection_reason=reason,
        )

        return {**state_updates, "plan_approved": False, "plan_rejection_reason": reason}

    # --- F6: Sub-agent rejection fallback ---
    # If the rejected plan contains `delegate_to_sub_agent_tool` steps, the rejection
    # is automatically converted to a REPLAN without sub-agents:
    # 1. Sets `needs_replan=True` + `exclude_sub_agent_tools=True` in state
    # 2. Planner regenerates using `exclude_tools` to filter delegation from catalogue
    # 3. User gets a new plan with direct tools (web_search, etc.) instead
    # 4. Flags cleared after single replan cycle to prevent infinite loops
    # Metric: hitl_plan_decisions{decision="REPLAN_SUB_AGENT_FALLBACK"}

    else:
        # EDIT case
        logger.info("approval_gate_edited")
        hitl_plan_decisions.labels(decision="EDIT").inc()

        # Modifications handled in service layer via plan_editor
        return state_updates
```

---

## 🎭 HITL Orchestrator

**Fichier** : `apps/api/src/domains/agents/services/hitl_orchestrator.py`

**Responsabilités** :
- Classifier réponses utilisateur (APPROVE/REJECT/EDIT/AMBIGUOUS)
- Build structured decisions pour LangChain
- Store tool_call_id mappings (pour REJECT)
- Error handling + clarification

**Message Counting (Phase 5.2B)** :
```
APPROVE:   NOT counted (trivial response)
REJECT:    NOT counted (trivial response)
EDIT:      NOT counted (replaces original message)
AMBIGUOUS: COUNTED (meaningful clarification request)
```

**Implementation** :
```python
class HITLOrchestrator:
    async def classify_user_response(
        self,
        user_message: str,
        context: dict,
    ) -> HITLClassification:
        """
        Classify user response via LLM.

        Returns:
            HITLClassification with decision, confidence, edited_params
        """
        # Fast-path detection (règles simples)
        if user_message.lower().strip() in ["oui", "ok", "yes", "vas-y", "confirme"]:
            return HITLClassification(
                decision="APPROVE",
                confidence=0.95,
                reasoning="Fast-path approval keyword",
            )

        if user_message.lower().strip() == "non":
            return HITLClassification(
                decision="REJECT",
                confidence=0.90,
                reasoning="Fast-path rejection keyword",
            )

        # LLM classification
        classifier_llm = create_llm(llm_type="hitl_classifier")
        structured_llm = classifier_llm.with_structured_output(HITLClassification)

        prompt = load_prompt("hitl_classifier_prompt", version="v2")

        classification = await structured_llm.ainvoke([
            SystemMessage(content=prompt),
            HumanMessage(content=json.dumps({
                "user_message": user_message,
                "context": context,
            }))
        ])

        return classification

    async def build_decision_for_graph(
        self,
        classification: HITLClassification,
        state: MessagesState,
    ) -> dict:
        """
        Build state updates basé sur classification.

        Returns:
            Dict avec plan_approved, plan_rejection_reason, etc.
        """
        if classification.decision == "APPROVE":
            return {"plan_approved": True}

        elif classification.decision == "REJECT":
            return {
                "plan_approved": False,
                "plan_rejection_reason": classification.reasoning,
            }

        elif classification.decision == "EDIT":
            # Apply modifications via PlanEditor
            editor = PlanEditor()
            modified_plan = editor.apply_modifications(
                state["execution_plan"],
                classification.edited_params
            )

            # Re-validate modified plan
            validator = PlanValidator()
            validation_result = validator.validate(modified_plan)

            if not validation_result.is_valid:
                return {
                    "plan_approved": False,
                    "plan_rejection_reason": "Modified plan invalid: " + format_validation_errors(validation_result.errors),
                }

            return {
                "execution_plan": modified_plan,
                "plan_approved": True,  # Auto-approve après modification
            }

        else:  # AMBIGUOUS
            # Increment message count (meaningful clarification)
            return {
                "plan_approved": None,  # Still pending
                "clarification_needed": True,
            }
```

---

## 💾 Configuration & Storage

### Variables .env - HITL Thresholds

| Variable | Default | Description |
|----------|---------|-------------|
| `HITL_CLASSIFIER_CONFIDENCE_THRESHOLD` | 0.7 | Seuil confidence classifier |
| `HITL_AMBIGUOUS_CONFIDENCE_THRESHOLD` | 0.7 | Seuil detection ambiguite |
| `HITL_FUZZY_MATCH_AMBIGUITY_THRESHOLD` | 0.05 | Seuil fuzzy match (scores dans 5% = ambigu) |
| `HITL_LOW_CONFIDENCE_THRESHOLD` | 0.5 | Seuil basse confidence → clarification |

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
            "timestamp": datetime.utcnow().isoformat(),
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

# Approval requests
hitl_plan_approval_requests = Counter(
    "hitl_plan_approval_requests_total",
    "Total plan approval requests",
    ["strategy"]  # ManifestBasedStrategy, CostThresholdStrategy, etc.
)

# Decisions
hitl_plan_decisions = Counter(
    "hitl_plan_decisions_total",
    "Plan approval decisions",
    ["decision"]  # APPROVE, REJECT, EDIT, REPLAN, AUTO_APPROVE
)

# Latency
hitl_plan_approval_latency = Histogram(
    "hitl_plan_approval_latency_seconds",
    "Time from request to decision",
    buckets=[1, 5, 10, 30, 60, 120, 300, 600]  # 1s to 10min
)

# Question generation
hitl_plan_approval_question_duration = Histogram(
    "hitl_plan_approval_question_duration_seconds",
    "LLM question generation time",
    buckets=[0.1, 0.2, 0.5, 1, 2, 5, 10]
)

# Fallbacks
hitl_plan_approval_question_fallback = Counter(
    "hitl_plan_approval_question_fallback_total",
    "Question generation fallbacks",
    ["error_type"]  # llm_failure, timeout, etc.
)

# Modifications
hitl_plan_modifications = Counter(
    "hitl_plan_modifications_total",
    "Plan modifications (EDIT)",
    ["modification_type"]  # parameter_change, step_removed, etc.
)
```

### Tool-Level Metrics (Legacy, Phase 7)

```python
# Kept for backward compatibility
hitl_user_response_time_seconds = Histogram(...)
hitl_tool_rejections_by_reason = Counter(...)
hitl_rejection_type_total = Counter(...)
hitl_edit_actions_total = Counter(...)
```

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
- `apps/api/src/domains/agents/services/approval/strategies.py`
- `apps/api/src/domains/agents/services/hitl_orchestrator.py`
- `apps/api/src/domains/agents/orchestration/plan_editor.py`

### Phase 8 Documents
- `apps/api/docs/PHASE_8_COMPLETE_SUMMARY.md` - Résumé complet Phase 8
- `apps/api/docs/HITL_PLAN_LEVEL_ARCHITECTURE.md` - Architecture détaillée

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

### Fichiers HITL Interactions

```
services/hitl/interactions/
├── draft_critique.py (647 lines) - Draft review logic
├── entity_disambiguation.py (313 lines) - Multiple match resolution
├── tool_confirmation.py (257 lines) - Sensitive action confirmation
├── plan_approval.py (305 lines) - Plan-level approval
└── clarification.py (300 lines) - Clarification questions
```

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

### Skill Guard Bypass (v1.8.1)

Early detection is **skipped** when a deterministic skill has high domain overlap with the query. This prevents false-positive clarification requests on multi-domain skills (e.g., daily briefing = event+task+weather+email). The guard function `_has_potential_skill_match()` in `planner_node_v3.py` checks active deterministic skills and allows up to `SKILLS_EARLY_DETECTION_MAX_MISSING_DOMAINS` (default: 1) domains to be missing. When a match is found, the full planner pipeline decides instead of short-circuiting to clarification.

See [Skills Integration Guide — Early Detection Guard](SKILLS_INTEGRATION.md#5-early-detection-guard-v181) for details.

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
| hitl_orchestrator.py | 1,401 | Main HITL coordination |
| hitl_classifier.py | 801 | User response classification |
| question_generator.py | 766 | LLM question generation |
| resumption_strategies.py | 1,437 | **Plan resumption logic** |
| draft_modifier.py | 360 | Draft editing during HITL |
| validator.py | 464 | HITL security validation |
| schema_validator.py | 322 | Schema compliance |
| parameter_enrichment.py | 337 | Parameter enrichment |
| registry.py | 267 | HITL interaction registry |
| hitl_keyboard.py | 158 | Telegram inline keyboards (evolution F3) |
| **Total** | **~6,400** | |

---

**HITL.md** - Version 2.2 - Phase evolution F3 - Mars 2026

*Human-in-the-Loop Plan-Level Approval System with Destructive Confirm + Unified Schemas + Telegram Inline Keyboards*
