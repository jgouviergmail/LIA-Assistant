# Plan Global Révisé : HITL Streaming + Validation Sémantique

**Version**: 2.0 - Revue Professionnelle
**Date**: 2025-11-25
**Références**: Issue #56, LangGraph v1.0.4, Langfuse v3, Prometheus Best Practices 2025

---

## Table des Matières

1. [Analyse Root Cause Approfondie](#1-analyse-root-cause-approfondie)
2. [Architecture Cible Générique](#2-architecture-cible-générique)
3. [Phase 1: HITL Streaming Natif](#3-phase-1-hitl-streaming-natif)
4. [Phase 2: Validation Sémantique](#4-phase-2-validation-sémantique)
5. [Phase 3: EDIT & REJECT Flow](#5-phase-3-edit--reject-flow)
6. [Métriques & Observabilité](#6-métriques--observabilité)
7. [Plan d'Implémentation](#7-plan-dimplémentation)
8. [Rollback & Migration](#8-rollback--migration)
9. [Critères de Succès](#9-critères-de-succès)
10. [Références](#10-références)
11. [Fichiers Critiques à Modifier](#11-fichiers-critiques-à-modifier)
12. [Estimations & Priorisation](#12-estimations--priorisation)

---

# 1. Analyse Root Cause Approfondie

## 1.1 Problème Principal: Double Blocage en Cascade

Le vrai problème n'est PAS le `split()` dans le streaming service. C'est un symptôme.

### Timeline Réelle d'un HITL Request

```
T+0ms     approval_gate_node() appelé
          │
T+0ms     └─ await _build_approval_request()
          │   │
T+0ms     │   └─ await generator.generate_plan_approval_question()
          │       │
          │       └─ ❌ BLOQUANT: LLM génère la question complète (2000-4000ms)
          │          └─ self.plan_approval_llm.ainvoke(prompt)
          │             └─ Client voit RIEN pendant ce temps
          │
T+2500ms  │   └─ question complète stockée dans approval_request.user_message
          │
T+2500ms  └─ interrupt(payload) avec user_message = chaîne COMPLÈTE
          │
T+2500ms  StreamingService._handle_hitl_interrupt() reçoit payload
          │
T+2510ms  └─ for word in user_message.split():  ← PSEUDO-STREAMING (trop tard)
                └─ yield hitl_question_token(word)
```

**Cause Racine**: La génération de question (`ainvoke()`) BLOQUE dans le node LangGraph AVANT l'`interrupt()`. Le client ne reçoit rien pendant 2-4 secondes.

### 1.2 Contrainte Architecturale LangGraph

```python
# Ce qui N'EST PAS POSSIBLE:
interrupt_payload = {
    "question_stream": async_generator,  # ❌ Non sérialisable JSON
}

# LangGraph checkpointer sérialise le payload
# Les AsyncGenerator ne peuvent pas être dans le payload
```

**Implication**: On ne peut PAS passer un stream dans `interrupt()`. La solution doit générer la question APRÈS l'interrupt, côté StreamingService.

### 1.3 Pattern Existant Non Exploité

Le code contient DÉJÀ une méthode de streaming fonctionnelle:

```python
# question_generator.py:210-335
async def generate_confirmation_question_stream(
    self,
    tool_name: str,
    tool_args: dict[str, Any],
    ...
) -> AsyncGenerator[str, None]:
    """Utilisé pour tool-level HITL - FONCTIONNE CORRECTEMENT"""
    async for chunk in self.tool_question_llm.astream(prompt, config=config):
        yield chunk.content
```

Cette méthode est utilisée pour tool-level mais **jamais pour plan-level**.

---

## 1.4 Root Cause Synthèse

| Aspect | Problème | Impact | Solution |
|--------|----------|--------|----------|
| **Génération** | `ainvoke()` bloquant dans node | 2-4s sans feedback | Flag + génération lazy dans StreamingService |
| **Transport** | Question dans payload (non-streamable) | Pas d'AsyncGen possible | Passer données brutes, générer après |
| **Tokenization** | `split()` par mots | Pas vrais tokens LLM | Utiliser `astream()` natif |
| **Pattern existant** | `generate_confirmation_question_stream()` orphelin | Code dupliqué | Réutiliser et généraliser |

---

# 2. Architecture Cible Générique

## 2.1 Principe: Question Generation on Demand

```
AVANT (Bloquant):
┌─────────────────────────────────────────────────────────┐
│ approval_gate_node                                       │
│   ├─ await generate_plan_approval_question() ← 2-4s     │
│   └─ interrupt({user_message: "Question complète..."})  │
└─────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────┐
│ StreamingService._handle_hitl_interrupt()               │
│   └─ for word in user_message.split(): yield word      │
└─────────────────────────────────────────────────────────┘

APRÈS (Streaming Natif):
┌─────────────────────────────────────────────────────────┐
│ approval_gate_node                                       │
│   └─ interrupt({                                         │
│        generate_question: true,  ← FLAG, pas question   │
│        plan_summary: {...},      ← Données brutes       │
│        approval_reasons: [...],                          │
│      })                                                  │
└─────────────────────────────────────────────────────────┘
                    ↓ (Immédiat, ~10ms)
┌─────────────────────────────────────────────────────────┐
│ StreamingService._handle_hitl_interrupt()               │
│   ├─ if generate_question:                               │
│   │    async for token in question_generator.astream(): │
│   │      yield hitl_question_token(token)  ← VRAI LLM   │
│   └─ else: fallback word split                          │
└─────────────────────────────────────────────────────────┘
```

## 2.2 Architecture Générique: HitlInteractionProtocol

Pour supporter de futurs types d'interaction (clarification, tool confirmation, etc.):

```python
# Fichier: src/domains/agents/services/hitl/protocols.py

from typing import Protocol, AsyncGenerator, Any
from enum import Enum

class HitlInteractionType(str, Enum):
    """Types d'interactions HITL supportées."""
    PLAN_APPROVAL = "plan_approval"
    TOOL_CONFIRMATION = "tool_confirmation"
    CLARIFICATION = "clarification"          # Issue #56
    EDIT_CONFIRMATION = "edit_confirmation"  # Phase 3

class HitlInteractionProtocol(Protocol):
    """
    Protocol pour toutes les interactions HITL.

    Permet d'ajouter de nouveaux types sans modifier le StreamingService.
    Pattern: Strategy + Protocol (Python 3.8+)
    """

    @property
    def interaction_type(self) -> HitlInteractionType:
        """Type d'interaction."""
        ...

    async def generate_question_stream(
        self,
        context: dict[str, Any],
        user_language: str,
    ) -> AsyncGenerator[str, None]:
        """
        Génère la question en streaming.

        Args:
            context: Données spécifiques au type (plan_summary, tool_args, etc.)
            user_language: Code langue (fr, en, es)

        Yields:
            Tokens de la question générée par LLM
        """
        ...

    def build_metadata_chunk(
        self,
        context: dict[str, Any],
        message_id: str,
    ) -> dict[str, Any]:
        """
        Construit les metadata pour le chunk initial.

        Returns:
            Dict avec action_requests, is_plan_approval, etc.
        """
        ...
```

## 2.3 Registry Pattern pour Extensibilité

```python
# Fichier: src/domains/agents/services/hitl/registry.py

class HitlInteractionRegistry:
    """
    Registry pour interactions HITL.

    Permet d'enregistrer de nouveaux types sans modifier le code existant.
    Pattern: Service Locator + Factory
    """

    _interactions: dict[HitlInteractionType, type[HitlInteractionProtocol]] = {}

    @classmethod
    def register(
        cls,
        interaction_type: HitlInteractionType,
    ) -> Callable[[type], type]:
        """Decorator pour enregistrer une interaction."""
        def decorator(interaction_class: type) -> type:
            cls._interactions[interaction_type] = interaction_class
            return interaction_class
        return decorator

    @classmethod
    def from_action_type(cls, action_type: str, **kwargs) -> HitlInteractionProtocol:
        """Factory depuis le type d'action dans le payload."""
        try:
            interaction_type = HitlInteractionType(action_type)
        except ValueError:
            # Fallback pour backward compatibility
            interaction_type = HitlInteractionType.PLAN_APPROVAL
        return cls.get(interaction_type, **kwargs)
```

---

# 3. Phase 1: HITL Streaming Natif

## 3.1 Modifications Requises

### Fichier 1: `approval_gate_node.py` - Skip Question Generation

```python
async def _build_approval_request(
    plan_summary: PlanSummary,
    validation_result: ValidationResult,
    approval_evaluation: Any | None = None,
    user_language: str = "fr",
    config: RunnableConfig | None = None,
    skip_question_generation: bool = True,  # NOUVEAU: Par défaut True
) -> PlanApprovalRequest:
    """
    Construit la requête d'approbation.

    Args:
        skip_question_generation: Si True, ne génère pas la question ici.
            La question sera générée en streaming par StreamingService.
    """
    if skip_question_generation:
        user_message = None
    else:
        user_message = await generator.generate_plan_approval_question(...)

    return PlanApprovalRequest(
        plan_summary=plan_summary,
        approval_reasons=reasons,
        strategies_triggered=strategies,
        user_message=user_message,
    )

# Payload interrupt enrichi
interrupt_payload = {
    "action_requests": [{
        "type": "plan_approval",
        "plan_summary": plan_summary.model_dump(mode="json"),
        "approval_reasons": approval_request.approval_reasons,
        "strategies_triggered": approval_request.strategies_triggered,
        "user_message": approval_request.user_message,
    }],
    "generate_question_streaming": True,  # NOUVEAU FLAG
    "user_language": user_language,
}
```

### Fichier 2: `question_generator.py` - Ajouter Streaming Method

```python
async def generate_plan_approval_question_stream(
    self,
    plan_summary: PlanSummary,
    approval_reasons: list[str],
    user_language: str = "fr",
    tracker: TokenTrackingCallback | None = None,
) -> AsyncGenerator[str, None]:
    """
    Stream plan approval question tokens (TTFT optimization).

    Best Practices:
    - LangChain v1.0: astream() pour streaming natif
    - Langfuse v3: create_instrumented_config() avec tags
    - Prometheus: TTFT histogram, token counter
    """
    prompt = self._build_plan_prompt(plan_summary, approval_reasons, user_language)

    config = create_instrumented_config(
        llm_type="hitl_plan_approval_question",
        tags=["hitl", "plan_approval", "streaming"],
        metadata={
            "plan_id": plan_summary.plan_id,
            "total_steps": plan_summary.total_steps,
            "streaming": True,
        },
    )

    start_time = time.time()
    first_token = True

    async for chunk in self.plan_approval_llm.astream(prompt, config=config):
        if first_token:
            ttft = time.time() - start_time
            hitl_question_ttft_seconds.labels(type="plan_approval").observe(ttft)
            first_token = False

        if chunk.content:
            yield chunk.content
```

### Fichier 3: `streaming/service.py` - Intégration Streaming

```python
async def _handle_hitl_interrupt(
    self,
    chunk: dict,
    conversation_id: uuid.UUID,
    run_id: str,
) -> AsyncGenerator[ChatStreamChunk, None]:
    """Handle HITL interrupt avec vrai streaming LLM."""
    interrupt_data = chunk.get("__interrupt__", [])[0].value
    action_requests = interrupt_data.get("action_requests", [])
    first_action = action_requests[0] if action_requests else {}

    action_type = first_action.get("type", "unknown")
    generate_streaming = interrupt_data.get("generate_question_streaming", False)
    user_message = first_action.get("user_message")
    user_language = interrupt_data.get("user_language", "fr")

    message_id = f"hitl_{conversation_id}_{run_id}"

    # Step 1: Metadata (immédiat)
    yield self._build_hitl_metadata_chunk(message_id, action_requests, action_type)

    # Step 2: Question tokens
    if generate_streaming and not user_message:
        # VRAI STREAMING via HitlInteractionRegistry
        interaction = HitlInteractionRegistry.from_action_type(
            action_type,
            question_generator=self._get_question_generator(),
        )

        question_buffer = ""
        async for token in interaction.generate_question_stream(
            context=first_action,
            user_language=user_language,
        ):
            question_buffer += token
            yield ChatStreamChunk(
                type="hitl_question_token",
                content=token,
                metadata={"message_id": message_id},
            )
        final_question = _normalize_markdown(question_buffer)
    else:
        # FALLBACK: Split par mots (backward compatibility)
        hitl_question = user_message or "Confirmation requise."
        for word in hitl_question.split():
            yield ChatStreamChunk(
                type="hitl_question_token",
                content=word + " ",
                metadata={"message_id": message_id},
            )
        final_question = hitl_question

    # Step 3: Complete
    yield ChatStreamChunk(
        type="hitl_interrupt_complete",
        content="",
        metadata={
            "message_id": message_id,
            "requires_approval": True,
            "generated_question": final_question,
        },
    )
```

---

# 4. Phase 2: Validation Sémantique (Issue #56)

## 4.1 Architecture Intégrée au Graph LangGraph

```
               ┌──────────────────────────────────────────────┐
               │           Graph LangGraph Étendu             │
               └──────────────────────────────────────────────┘

START → Router → Planner → SemanticValidator → ApprovalGate → Executor → Response → END
                     ↑           │                    │
                     │      ┌────┴────┐          ┌───┴───┐
                     │      ↓         ↓          ↓       ↓
                     │   valid    clarify    approve  reject
                     │      │         │          │       │
                     │      │    ┌────┘          │       └→ Response
                     │      │    ↓               │
                     │      │ Clarification ─────┘
                     │      │    (interrupt)
                     └──────┴────────────────────┘
                         (feedback loop max 3x)
```

## 4.2 PlanSemanticValidator

```python
# Fichier: src/domains/agents/orchestration/semantic_validator.py

class SemanticIssueType(str, Enum):
    """Types d'issues sémantiques."""
    CARDINALITY_MISMATCH = "cardinality_mismatch"  # "pour chaque" → N ops
    MISSING_DEPENDENCY = "missing_dependency"
    IMPLICIT_ASSUMPTION = "implicit_assumption"
    SCOPE_OVERFLOW = "scope_overflow"
    SCOPE_UNDERFLOW = "scope_underflow"


@dataclass
class SemanticValidationResult:
    is_valid: bool
    issues: list[SemanticIssue]
    confidence: float
    requires_clarification: bool
    clarification_questions: list[str]


class PlanSemanticValidator:
    """
    Valide la conformité sémantique plan vs requête.

    Utilise un LLM distinct du planner (évite self-validation bias).

    Best Practices:
    - LangChain v1.0: with_structured_output() pour parsing fiable
    - Langfuse v3: Trace séparée "semantic_validation"
    - Prometheus: Duration histogram, issue type counter
    """
```

## 4.3 ClarificationNode avec Interrupt

```python
# Fichier: src/domains/agents/nodes/clarification_node.py

async def clarification_node(
    state: MessagesState,
    config: RunnableConfig,
) -> dict[str, Any]:
    """
    Node avec interrupt pour clarification utilisateur.

    Pattern LangGraph v1.0:
    - interrupt() suspend le workflow
    - Command(resume=response) reprend avec la réponse
    - Utilise HitlInteractionRegistry pour le streaming
    """
    validation = state.get("semantic_validation")

    if not validation or not validation.requires_clarification:
        return state

    clarification_payload = {
        "action_requests": [{
            "type": HitlInteractionType.CLARIFICATION.value,
            "clarification_questions": validation.clarification_questions,
            "semantic_issues": [
                {"type": i.issue_type.value, "description": i.description}
                for i in validation.issues
            ],
        }],
        "generate_question_streaming": True,
        "user_language": state.get("user_language", "fr"),
    }

    # Interrupt - suspend jusqu'à Command(resume=...)
    clarification_response = interrupt(clarification_payload)

    return {
        "clarification_response": clarification_response,
        "needs_replan": True,
        "planner_iteration": state.get("planner_iteration", 0) + 1,
    }
```

---

# 5. Phase 3: EDIT & REJECT Flow

## 5.1 EDIT Handling Amélioré

### Problèmes Corrigés

1. **Validation schéma paramètres** - Utiliser Pydantic du tool
2. **Détection références cassées** - Vérifier depends_on après suppression
3. **Multi-domaines** - Mettre à jour MultiDomainComposer
4. **Undo** - Historique des modifications

```python
# Fichier: src/domains/agents/orchestration/plan_editor.py

class EnhancedPlanEditor(PlanEditor):
    """PlanEditor avec validations avancées."""

    def __init__(self, tool_registry: ToolRegistry | None = None):
        self.tool_registry = tool_registry
        self._history: list[ExecutionPlan] = []

    async def apply_with_validation(
        self,
        plan: ExecutionPlan,
        modifications: list[PlanModification],
    ) -> tuple[ExecutionPlan, list[str]]:
        """
        Applique modifications avec validation.

        Returns:
            (modified_plan, warnings)
        """
        self._history.append(plan)
        warnings = []

        modified = self.apply_modifications(plan, modifications)

        if self.tool_registry:
            for mod in modifications:
                if mod.modification_type == "edit_params":
                    step = self._find_step(modified, mod.step_id)
                    if step:
                        schema_warnings = self._validate_params(
                            step.tool_name, mod.new_parameters
                        )
                        warnings.extend(schema_warnings)

        modified, ref_warnings = self._repair_references(modified)
        warnings.extend(ref_warnings)

        return modified, warnings

    def undo(self) -> ExecutionPlan | None:
        """Annule la dernière modification."""
        return self._history.pop() if self._history else None
```

## 5.2 REJECT Flow - SSE Dédié

### Problème

Le rejet HITL utilise actuellement le type "error" alors que c'est un flow normal.

### Solution: Nouveaux Types SSE

```python
# Fichier: src/domains/agents/api/schemas.py

class ChatStreamChunkType(str, Enum):
    # NOUVEAUX - Rejection explicite
    HITL_REJECTION = "hitl_rejection"
    HITL_REJECTION_TOKEN = "hitl_rejection_token"
    HITL_REJECTION_COMPLETE = "hitl_rejection_complete"
```

### Frontend Adaptation

```typescript
// Fichier: apps/web/src/reducers/chat-reducer.ts

case 'HITL_REJECTION':
  return {
    ...state,
    status: 'idle',  // PAS 'error'
    hitlState: {
      ...state.hitlState,
      isRejection: true,
      rejectionReason: action.payload.rejection_reason,
      canRetry: action.payload.can_retry,
    },
  };
```

---

# 6. Métriques & Observabilité

## 6.1 Nouvelles Métriques Prometheus

```python
# Fichier: src/infrastructure/observability/metrics_hitl.py

# HITL Streaming
hitl_question_ttft_seconds = Histogram(
    "hitl_question_ttft_seconds",
    "Time to first token for HITL questions",
    ["type"],
    buckets=[0.1, 0.2, 0.3, 0.5, 1.0, 2.0, 3.0, 5.0],
)

hitl_streaming_tokens_total = Counter(
    "hitl_streaming_tokens_total",
    "Total tokens streamed for HITL questions",
    ["type"],
)

hitl_streaming_fallback_total = Counter(
    "hitl_streaming_fallback_total",
    "HITL streaming fallbacks (LLM failure)",
    ["type", "error_type"],
)

# Semantic Validation
semantic_validation_total = Counter(
    "semantic_validation_total",
    "Plan semantic validations",
    ["result"],
)

semantic_validation_duration_seconds = Histogram(
    "semantic_validation_duration_seconds",
    "Semantic validation duration",
    buckets=[0.5, 1.0, 2.0, 3.0, 5.0],
)

# Clarification
planner_clarification_requests_total = Counter(
    "planner_clarification_requests_total",
    "Clarification requests to user",
)

# Feedback Loop
planner_iterations_histogram = Histogram(
    "planner_iterations",
    "Planner iterations before valid plan",
    buckets=[1, 2, 3, 4, 5],
)

# EDIT & REJECT
plan_edit_operations_total = Counter(
    "plan_edit_operations_total",
    "Plan edit operations",
    ["operation"],
)

hitl_rejection_total = Counter(
    "hitl_rejection_total",
    "HITL rejections",
    ["reason"],
)
```

## 6.2 Langfuse v3 Traces

```python
# Pattern: create_instrumented_config() avec metadata riche

config = create_instrumented_config(
    llm_type="hitl_plan_approval_question",
    tags=["hitl", "plan_approval", "streaming"],
    metadata={
        "plan_id": plan_summary.plan_id,
        "total_steps": plan_summary.total_steps,
        "streaming": True,
        "user_language": user_language,
    },
    trace_name="hitl_question_streaming",
)
```

---

# 7. Plan d'Implémentation

## 7.1 Phases et Dépendances

```
Phase 1 (6h) ─────────────────────────────────────────────────────────────────
│ HITL Streaming Natif                                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│ 1.1 HitlInteractionProtocol + Registry         (protocols.py, registry.py)  │
│ 1.2 PlanApprovalInteraction                    (interactions/)              │
│ 1.3 generate_plan_approval_question_stream()   (question_generator.py)      │
│ 1.4 Modification approval_gate_node            (approval_gate_node.py)      │
│ 1.5 Intégration StreamingService               (streaming/service.py)       │
│ 1.6 Tests unitaires                            (tests/)                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓
Phase 2 (4h) ─────────────────────────────────────────────────────────────────
│ Validation Sémantique + Clarification (Issue #56)                           │
├─────────────────────────────────────────────────────────────────────────────┤
│ 2.1 PlanSemanticValidator                      (semantic_validator.py)      │
│ 2.2 ClarificationInteraction                   (interactions/)              │
│ 2.3 clarification_node                         (clarification_node.py)      │
│ 2.4 Intégration Graph LangGraph                (graph.py)                   │
│ 2.5 Tests unitaires + intégration              (tests/)                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓
Phase 3 (3h) ─────────────────────────────────────────────────────────────────
│ EDIT & REJECT Flow                                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│ 3.1 EnhancedPlanEditor                         (plan_editor.py)             │
│ 3.2 Nouveaux types SSE REJECT                  (schemas.py)                 │
│ 3.3 ResponseNode REJECT handler                (response_node.py)           │
│ 3.4 Frontend chat-reducer                      (chat-reducer.ts)            │
│ 3.5 Tests                                      (tests/)                      │
└─────────────────────────────────────────────────────────────────────────────┘

TOTAL: 13-14h
```

## 7.2 Fichiers par Phase

### Phase 1: HITL Streaming

| Action | Fichier | Lignes |
|--------|---------|--------|
| NOUVEAU | `services/hitl/protocols.py` | ~50 |
| NOUVEAU | `services/hitl/registry.py` | ~40 |
| NOUVEAU | `services/hitl/interactions/__init__.py` | ~15 |
| NOUVEAU | `services/hitl/interactions/plan_approval.py` | ~60 |
| MODIFIER | `services/hitl/question_generator.py` | +50 |
| MODIFIER | `nodes/approval_gate_node.py` | +20 |
| MODIFIER | `services/streaming/service.py` | +40 |
| NOUVEAU | `tests/unit/.../test_hitl_streaming.py` | ~100 |

### Phase 2: Validation Sémantique

| Action | Fichier | Lignes |
|--------|---------|--------|
| NOUVEAU | `orchestration/semantic_validator.py` | ~120 |
| NOUVEAU | `nodes/clarification_node.py` | ~60 |
| NOUVEAU | `services/hitl/interactions/clarification.py` | ~50 |
| MODIFIER | `graph.py` | +30 |
| MODIFIER | `models.py` (MessagesState) | +10 |
| NOUVEAU | `tests/unit/.../test_semantic_validator.py` | ~80 |

### Phase 3: EDIT & REJECT

| Action | Fichier | Lignes |
|--------|---------|--------|
| MODIFIER | `orchestration/plan_editor.py` | +80 |
| MODIFIER | `api/schemas.py` | +10 |
| MODIFIER | `nodes/response_node.py` | +50 |
| MODIFIER | `apps/web/.../chat-reducer.ts` | +30 |
| NOUVEAU | `tests/unit/.../test_enhanced_editor.py` | ~60 |

---

# 8. Rollback & Migration

## 8.1 Feature Flags

```python
# Fichier: src/core/config/features.py

class FeatureFlags:
    # Phase 1
    HITL_STREAMING_ENABLED: bool = True  # False = fallback word split

    # Phase 2
    SEMANTIC_VALIDATION_ENABLED: bool = True  # False = skip validation
    CLARIFICATION_LOOP_ENABLED: bool = True   # False = skip clarification

    # Phase 3
    ENHANCED_PLAN_EDITOR: bool = True  # False = use base PlanEditor
    REJECT_DEDICATED_SSE: bool = True  # False = use "error" type
```

## 8.2 Rollback Par Phase

| Phase | Rollback | Impact |
|-------|----------|--------|
| 1 | `HITL_STREAMING_ENABLED=False` | Word split (2-4s delay) |
| 2 | `SEMANTIC_VALIDATION_ENABLED=False` | Skip validation, direct approval |
| 3 | `ENHANCED_PLAN_EDITOR=False` | No schema validation |
| 3 | `REJECT_DEDICATED_SSE=False` | Use "error" type |

## 8.3 Migration Sans Downtime

1. Deploy Phase 1 avec flag OFF
2. Test en staging
3. Activer flag en production progressivement (canary)
4. Répéter pour chaque phase

---

# 9. Critères de Succès

## 9.1 Métriques Cibles

| Métrique | Avant | Après | Cible |
|----------|-------|-------|-------|
| TTFT Plan Approval | 2000-4000ms | 200-400ms | < 500ms |
| TTFT Clarification | N/A | 200-400ms | < 500ms |
| Streaming Success Rate | 0% (fake) | 98%+ | > 95% |
| Semantic Validation Coverage | 0% | 100% | 100% |
| EDIT Schema Validation | Non | Oui | Oui |
| REJECT UX | "error" | Dédié | Dédié |

## 9.2 Tests

- [ ] Tests unitaires: Coverage > 80%
- [ ] Tests intégration: E2E flow complet
- [ ] Tests performance: TTFT < 500ms (p95)
- [ ] Tests fallback: Graceful degradation

## 9.3 Documentation

- [ ] HITL.md mis à jour
- [ ] Issue #56 fermée avec commentaire
- [ ] Dashboard Grafana déployé

---

# 10. Références

## Best Practices 2025

- [LangGraph Human-in-the-Loop](https://langchain-ai.github.io/langgraph/concepts/human_in_the_loop/)
- [LangGraph Interrupt Pattern](https://langchain-ai.github.io/langgraph/how-tos/human_in_the_loop/wait-user-input/)
- [LangChain Streaming](https://docs.langchain.com/oss/python/langchain/streaming)
- [Langfuse v3 OpenTelemetry](https://langfuse.com/integrations/native/opentelemetry)
- [Prometheus Best Practices](https://prometheus.io/docs/practices/naming/)

---

# 11. Fichiers Critiques à Modifier

## Phase 1 - HITL Streaming

| Fichier | Type | Description |
|---------|------|-------------|
| `services/hitl/streaming.py` | NOUVEAU | HitlStreamingService + HitlStreamingContext |
| `services/hitl/question_generator.py` | MODIFIER | Ajouter `generate_plan_approval_question_stream()` |
| `nodes/approval_gate_node.py` | MODIFIER | Flag `skip_question_generation` + payload enrichi |
| `services/streaming/service.py` | MODIFIER | Intégration HitlStreamingService |
| `orchestration/approval_schemas.py` | MODIFIER | `user_message` optionnel |

## Phase 2 - Validation Sémantique

| Fichier | Type | Description |
|---------|------|-------------|
| `orchestration/semantic_validator.py` | NOUVEAU | PlanSemanticValidator + SemanticIssue |
| `nodes/approval_gate_node.py` | MODIFIER | Intégrer validation avant interrupt |
| `services/hitl/interactions/clarification.py` | NOUVEAU | ClarificationInteraction |

## Phase 3 - EDIT & REJECT

| Fichier | Type | Description |
|---------|------|-------------|
| `orchestration/plan_editor.py` | MODIFIER | Validation schéma JSON + undo |
| `handlers/*.py` | MODIFIER | Intégrer EnhancedPlanEditor |
| `services/streaming/service.py` | MODIFIER | Type SSE "hitl_rejected" |

---

# 12. Estimations & Priorisation

| Phase | Description | Estimation | Priorité | Dépendances |
|-------|-------------|------------|----------|-------------|
| 1 | HITL Streaming Natif | 6h | P0 | - |
| 2 | Validation Sémantique | 4h | P1 | Phase 1 |
| 3 | EDIT & REJECT Flow | 3h | P1 | Phase 1 |
| **Total** | | **13-14h** | | |

---

**FIN DU PLAN**
