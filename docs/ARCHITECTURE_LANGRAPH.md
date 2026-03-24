# Architecture LangGraph - LIA

**Version**: 5.8 (INTELLIPLANNER + INTELLIA v10.1 + SEMANTIC + REMINDERS + Architecture v3.5 + Sub-Agents + Browser Control + Journals + Philips Hue + Initiative Phase + MCP Iterative)
**Date**: 2026-03-24
**Status**: Production

---

## Vue d'Ensemble

LIA utilise **LangGraph v1.1.2** avec exécution parallèle native **asyncio** pour orchestrer un assistant intelligent multi-domaines. L'architecture supporte:

**Domaines actifs**: Contacts, Emails, Calendar, Drive, Tasks, Weather, Wikipedia, Perplexity, Places, Routes, Brave Search, Web Fetch, Browser, MCP, Sub-Agents

- Routing intelligent avec classification binaire
- Planification LLM avec validation sémantique
- HITL (Human-in-the-Loop) à 3 niveaux
- Exécution parallèle via `asyncio.gather()`
- Streaming SSE temps réel
- Data Registry pour rendu riche frontend
- **INTELLIA v10.1**: Formatage JSON + Few-Shot avec détection dynamique d'action (search/details)
- **Dual Connector Architecture**: OAuth (Google) + API Key (Weather, Perplexity)
- **INTELLIPLANNER**: Flux de données structurées + Re-planning adaptatif intelligent

---

## 1. Schéma Global du Graph

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              ENTRÉE UTILISATEUR                                  │
│                                      │                                           │
│                                      ▼                                           │
│                         ┌────────────────────────┐                              │
│                         │   compaction_node (F4) │                              │
│                         │  (Context summarization │                              │
│                         │   if > threshold)       │                              │
│                         └──────────┬─────────────┘                              │
│                                    │ (always)                                    │
│                                    ▼                                           │
│                         ┌────────────────────────┐                              │
│                         │      router_node       │                              │
│                         │  (Classification 0-1)  │                              │
│                         │   Actionable vs Conv   │                              │
│                         └──────────┬─────────────┘                              │
│                                    │                                             │
│              ┌─────────────────────┴─────────────────────┐                      │
│              │                                           │                      │
│              ▼                                           ▼                      │
│   ┌──────────────────┐                       ┌──────────────────┐              │
│   │   planner_node   │                       │   response_node  │              │
│   │  (Plan LLM Gen)  │                       │    (Réponse)     │──────┐       │
│   └────────┬─────────┘                       └──────────────────┘      │       │
│            │                                                           │       │
│            ▼                                                           │       │
│   ┌──────────────────────┐                                            │       │
│   │semantic_validator    │                                            │       │
│   │ (Validation Phase 2) │                                            │       │
│   └────────┬─────────────┘                                            │       │
│            │                                                           │       │
│   ┌────────┴────────┬───────────────┐                                 │       │
│   │                 │               │                                 │       │
│   ▼                 ▼               ▼                                 │       │
│ ┌─────────┐  ┌────────────┐  ┌─────────────┐                         │       │
│ │clarifi- │  │  planner   │  │approval_gate│                         │       │
│ │cation   │  │ (re-plan)  │  │  (HITL P8)  │                         │       │
│ │(HITL)   │  └─────┬──────┘  └──────┬──────┘                         │       │
│ └────┬────┘        │                │                                 │       │
│      │             │         ┌──────┴──────┬───────────┐             │       │
│      └─────────────┘         │             │           │             │       │
│                              ▼             ▼           ▼             │       │
│                    ┌──────────────┐ ┌─────────┐ ┌──────────┐        │       │
│                    │task_         │ │planner  │ │response  │        │       │
│                    │orchestrator  │ │(REPLAN) │ │(REJECT)  │────────┤       │
│                    └──────┬───────┘ └─────────┘ └──────────┘        │       │
│                           │                                          │       │
│            ┌──────────────┼──────────────┐                          │       │
│            │              │              │                          │       │
│            ▼              ▼              ▼                          │       │
│   ┌────────────┐  ┌────────────┐  ┌────────────┐                   │       │
│   │contacts_   │  │emails_     │  │draft_      │                   │       │
│   │agent       │  │agent       │  │critique    │                   │       │
│   │(SubGraph)  │  │(SubGraph)  │  │(HITL LOT6) │                   │       │
│   └─────┬──────┘  └─────┬──────┘  └─────┬──────┘                   │       │
│         │               │               │                          │       │
│         └───────────────┴───────────────┘                          │       │
│                         │                                          │       │
│                         ▼                                          │       │
│               ┌──────────────────┐                                 │       │
│               │   response_node  │◄────────────────────────────────┘       │
│               │  (Synthèse LLM)  │                                         │
│               │  JSON + Few-Shot │                                         │
│               └────────┬─────────┘                                         │
│                        │                                                    │
│                        ▼                                                    │
│                      [END]                                                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Nodes et Responsabilités

### 2.1 router_node

**Fichier**: `nodes/router_node_v3.py`

> ⚠️ **Architecture v3**: Toute l'intelligence est externalisée dans `QueryAnalyzerService.analyze_full()`

```
┌─────────────────────────────────────────────────────────────────┐
│                      router_node                                │
├─────────────────────────────────────────────────────────────────┤
│ INPUT                                                           │
│   • messages: Liste des messages conversation                   │
│   • metadata: Contexte session                                  │
├─────────────────────────────────────────────────────────────────┤
│ TRAITEMENT                                                      │
│   1. Extraire dernier message utilisateur                       │
│   2. Classification LLM (gpt-4.1-nano, cache activé)                  │
│   3. Score confiance: high/medium/low/very_low                  │
│   4. Détection multi-domaines (contacts, emails, calendar)      │
├─────────────────────────────────────────────────────────────────┤
│ OUTPUT                                                          │
│   • routing_history: [RouterOutput]                             │
│     - intention: "actionable" | "conversational"                │
│     - confidence: 0.0 - 1.0                                     │
│     - detected_domains: ["contacts", "emails", ...]             │
│     - next_node: "planner" | "response"                         │
├─────────────────────────────────────────────────────────────────┤
│ ROUTING                                                         │
│   • Actionable (conf ≥ 0.45) → planner_node                     │
│   • Conversational          → response_node                     │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 planner_node

**Fichier**: `nodes/planner_node_v3.py`

> ⚠️ **Architecture v3**: Utilise `SmartPlannerService` avec catalogue filtré (89% token savings)

```
┌─────────────────────────────────────────────────────────────────┐
│                      planner_node                               │
├─────────────────────────────────────────────────────────────────┤
│ INPUT                                                           │
│   • messages (windowed: 10 derniers turns)                      │
│   • routing_history (domaines détectés)                         │
│   • agent_results (résultats turn précédent)                    │
│   • resolved_context (références résolues)                      │
│   • clarification_response (si re-plan)                         │
├─────────────────────────────────────────────────────────────────┤
│ TRAITEMENT                                                      │
│   1. Charger catalogue (filtré par domaines ou complet)         │
│   2. Charger contextes actifs (Store)                           │
│   3. Injecter array counts                                      │
│   4. Générer plan via LLM (GPT-4)                               │
│   5. Parser en ExecutionPlan (Pydantic)                         │
│   6. Valider:                                                   │
│      - Références ($steps.X.field)                              │
│      - Coût vs budget                                           │
│      - Permissions                                              │
│      - Dépendances                                              │
│   7. Retry si validation échoue (max 2)                         │
├─────────────────────────────────────────────────────────────────┤
│ OUTPUT                                                          │
│   • execution_plan: ExecutionPlan avec steps                    │
│   • planner_metadata: Pour streaming frontend                   │
│   • validation_result: requires_hitl flag                       │
│   • planner_error: Si génération échoue                         │
│   • needs_replan: Reset à False                                 │
├─────────────────────────────────────────────────────────────────┤
│ ROUTING                                                         │
│   • requires_hitl=True  → approval_gate_node                    │
│   • requires_hitl=False → task_orchestrator_node                │
└─────────────────────────────────────────────────────────────────┘
```

### 2.3 semantic_validator_node

**Fichier**: `nodes/semantic_validator_node.py`

```
┌─────────────────────────────────────────────────────────────────┐
│                 semantic_validator_node                         │
├─────────────────────────────────────────────────────────────────┤
│ INPUT                                                           │
│   • execution_plan: Plan généré                                 │
│   • messages: Pour intent utilisateur                           │
│   • user_language: Langue pour questions                        │
├─────────────────────────────────────────────────────────────────┤
│ TRAITEMENT                                                      │
│   1. Feature flag check (skip si désactivé)                     │
│   2. Pattern bypass (skip si ≥90% confiance pattern connu)      │
│   3. Short-circuit: Pass si ≤1 step                             │
│   4. Validation sémantique:                                     │
│      - Cardinalité (single vs "pour chaque")                    │
│      - Dépendances manquantes                                   │
│      - Hypothèses implicites                                    │
│      - Scope overflow/underflow                                 │
│   5. LLM rapide (gpt-4.1-mini, <2s)                             │
│   6. Timeout fallback (1s → pass optimiste)                     │
│   7. Pattern Learning: record_plan_success/failure (async)      │
├─────────────────────────────────────────────────────────────────┤
│ OUTPUT                                                          │
│   • semantic_validation: SemanticValidationResult               │
│     - is_valid: Plan correspond à l'intent                      │
│     - issues: Problèmes détectés                                │
│     - requires_clarification: Input user requis                 │
│     - clarification_questions: Questions pour user              │
│     - confidence: Score validation                              │
├─────────────────────────────────────────────────────────────────┤
│ ROUTING                                                         │
│   • requires_clarification=True → clarification_node            │
│   • is_valid=False (fixable)    → planner_node (auto-replan)    │
│   • is_valid=True               → approval_gate_node            │
└─────────────────────────────────────────────────────────────────┘
```

### 2.4 clarification_node

**Fichier**: `nodes/clarification_node.py`

```
┌─────────────────────────────────────────────────────────────────┐
│                   clarification_node                            │
│                     (HITL Interrupt)                            │
├─────────────────────────────────────────────────────────────────┤
│ INPUT                                                           │
│   • semantic_validation.clarification_questions                 │
│   • user_language                                               │
├─────────────────────────────────────────────────────────────────┤
│ TRAITEMENT                                                      │
│   1. Extraire questions de semantic_validation                  │
│   2. Préparer payload HITL                                      │
│   3. interrupt() → LangGraph pause + checkpoint                 │
│   4. Attendre Command(resume={...}) du frontend                 │
│   5. Incrémenter planner_iteration                              │
├─────────────────────────────────────────────────────────────────┤
│ OUTPUT                                                          │
│   • clarification_response: Réponse utilisateur                 │
│   • needs_replan: True                                          │
│   • planner_iteration: +1                                       │
├─────────────────────────────────────────────────────────────────┤
│ ROUTING                                                         │
│   Toujours → planner_node (avec contexte clarification)         │
└─────────────────────────────────────────────────────────────────┘
```

### 2.5 approval_gate_node

**Fichier**: `nodes/approval_gate_node.py`

```
┌─────────────────────────────────────────────────────────────────┐
│                   approval_gate_node                            │
│                     (HITL Phase 8)                              │
├─────────────────────────────────────────────────────────────────┤
│ INPUT                                                           │
│   • execution_plan: Plan à approuver                            │
│   • validation_result.requires_hitl                             │
│   • user_language                                               │
├─────────────────────────────────────────────────────────────────┤
│ TRAITEMENT                                                      │
│   1. Kill switch global check                                   │
│   2. Si !requires_hitl → pass-through                           │
│   3. Construire résumé plan + coûts                             │
│   4. Générer question approbation (LLM streamé)                 │
│   5. interrupt() → Attendre décision user                       │
│   6. Traiter décision:                                          │
│      - APPROVE: plan_approved=True                              │
│      - REJECT:  Expliquer rejet                                 │
│      - EDIT:    Appliquer modifications, re-valider             │
│      - REPLAN:  Nouvelles instructions                          │
├─────────────────────────────────────────────────────────────────┤
│ OUTPUT                                                          │
│   • plan_approved: True/False/None                              │
│   • plan_rejection_reason: Si rejeté                            │
│   • execution_plan: Modifié si EDIT                             │
│   • needs_replan: Si REPLAN                                     │
│   • replan_instructions: Nouvelles instructions                 │
├─────────────────────────────────────────────────────────────────┤
│ ROUTING                                                         │
│   • APPROVE → task_orchestrator_node                            │
│   • REJECT  → response_node                                     │
│   • EDIT    → task_orchestrator_node (si valid)                 │
│   • REPLAN  → planner_node                                      │
└─────────────────────────────────────────────────────────────────┘
```

### 2.6 task_orchestrator_node

**Fichier**: `nodes/task_orchestrator_node.py`

```
┌─────────────────────────────────────────────────────────────────┐
│                 task_orchestrator_node                          │
│              (Dispatcher Exécution Parallèle)                   │
├─────────────────────────────────────────────────────────────────┤
│ INPUT                                                           │
│   • execution_plan: Plan validé/approuvé                        │
│   • Agent functions (contacts_agent, emails_agent, hue_agent, ...)│
├─────────────────────────────────────────────────────────────────┤
│ TRAITEMENT                                                      │
│   1. Dispatch vers parallel_executor                            │
│   2. Calcul waves via DependencyGraph                           │
│   3. asyncio.gather() par wave                                  │
│   4. Résolution paramètres ($steps.X.field)                     │
│   5. Exécution steps (TOOL → agents)                            │
│   6. Accumulation résultats + Data Registry                     │
│   7. Détection requires_confirmation (drafts)                   │
├─────────────────────────────────────────────────────────────────┤
│ OUTPUT                                                          │
│   • completed_steps: {step_id → StepResult}                     │
│   • registry: Data Registry items de tous les tools             │
│   • pending_hitl_interaction: Si interaction HITL en attente    │
│   • agent_results: "turn_id:agent_name" → result                │
├─────────────────────────────────────────────────────────────────┤
│ ROUTING                                                         │
│   • pending_hitl_interaction → hitl_dispatch_node               │
│   • Plus d'agents à exécuter → agent node suivant               │
│   • Terminé → initiative_node                                    │
└─────────────────────────────────────────────────────────────────┘
```

### 2.7 initiative_node (ADR-062)

**Fichier**: `nodes/initiative_node.py`

```
┌─────────────────────────────────────────────────────────────────┐
│                    initiative_node                               │
│               (Post-Execution Enrichment)                        │
├─────────────────────────────────────────────────────────────────┤
│ INPUT                                                           │
│   • agent_results: Résultats d'exécution du tour                │
│   • query_intelligence: Domaines exécutés                       │
│   • Memory facts + User interests (injected)                    │
├─────────────────────────────────────────────────────────────────┤
│ TRAITEMENT                                                      │
│   1. Pre-filter: domaines adjacents read-only disponibles?      │
│   2. Format execution summary + adjacent tools                  │
│   3. LLM structured output → InitiativeDecision                 │
│   4. Si should_act: execute_plan_parallel (read-only tools)     │
│   5. Merge initiative results into agent_results + registry     │
│   6. Suggestion field for response_node context                 │
├─────────────────────────────────────────────────────────────────┤
│ OUTPUT                                                          │
│   • initiative_results: Résultats des actions complémentaires   │
│   • initiative_suggestion: Suggestion write-action (optional)   │
│   • agent_results: Merged with initiative data                  │
│   • registry: Merged with initiative registry items             │
├─────────────────────────────────────────────────────────────────┤
│ ROUTING                                                         │
│   • Toujours → response_node                                    │
└─────────────────────────────────────────────────────────────────┘
```

### 2.8 hitl_dispatch_node

**Fichier**: `nodes/hitl_dispatch_node.py`

```
┌─────────────────────────────────────────────────────────────────┐
│                   hitl_dispatch_node                            │
│                     (HITL Phase 8.1)                            │
├─────────────────────────────────────────────────────────────────┤
│ INPUT                                                           │
│   • pending_hitl_interaction: HitlInteraction                   │
│     - interaction_type, severity, context                       │
│   • user_language                                               │
├─────────────────────────────────────────────────────────────────┤
│ TRAITEMENT                                                      │
│   1. Dispatcher vers l'interaction appropriée                   │
│   2. DRAFT_CRITIQUE, DESTRUCTIVE_CONFIRM, etc.                  │
│   3. interrupt() → Présenter interaction à l'utilisateur        │
│   4. Attendre Command(resume={action: ...})                     │
│   5. Exécuter l'action via interaction handler                  │
├─────────────────────────────────────────────────────────────────┤
│ OUTPUT                                                          │
│   • hitl_result: {action, result}                               │
│     - action: "confirm" | "edit" | "cancel"                     │
│     - result: Résultat exécution si confirm                     │
├─────────────────────────────────────────────────────────────────┤
│ ROUTING                                                         │
│   Toujours → response_node                                      │
└─────────────────────────────────────────────────────────────────┘
```

### 2.9 response_node (INTELLIA v10)

**Fichier**: `nodes/response_node.py`

```
┌─────────────────────────────────────────────────────────────────┐
│                     response_node                               │
│              (INTELLIA v10 - JSON + Few-Shot)                   │
├─────────────────────────────────────────────────────────────────┤
│ INPUT                                                           │
│   • messages: Historique conversation complet                   │
│   • agent_results: Résultats exécution ce turn                  │
│   • planner_error: Si génération plan échouée                   │
│   • plan_rejection_reason: Si approval rejeté                   │
│   • draft_action_result: Si draft exécuté                       │
│   • registry: Data Registry items pour données                  │
├─────────────────────────────────────────────────────────────────┤
│ TRAITEMENT (INTELLIA v10)                                       │
│   1. Check conditions erreur:                                   │
│      - planner_error → réponse fallback erreur                  │
│      - plan_rejected → explication rejet                        │
│   2. Détecter domaines depuis registry:                         │
│      → _detect_result_domains_from_registry()                   │
│   3. Charger few-shot examples dynamiques:                      │
│      → load_fewshot_examples(domain_operations)                 │
│   4. Formater données registry en JSON:                         │
│      → _format_registry_mode_results()                          │
│      → _format_type_as_json() + _simplify_*_payload()           │
│   5. Appeler LLM Response avec:                                 │
│      - JSON blocks structurés                                   │
│      - Few-shot examples pour formatage                         │
│   6. LLM génère réponse Markdown conversationnelle              │
│   7. Pattern Learning: record_plan_success/failure (async)      │
│      (pour plans simples ayant bypassé semantic_validator)      │
├─────────────────────────────────────────────────────────────────┤
│ OUTPUT                                                          │
│   • messages: +1 AIMessage (réponse formatée par LLM)           │
│   • content_final_replacement: None (pas de post-processing)    │
├─────────────────────────────────────────────────────────────────┤
│ ROUTING                                                         │
│   → END (fin du graph)                                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Architecture de Formatage (INTELLIA v10)

### 3.1 Principe JSON + Few-Shot

**INTELLIA v10** utilise une architecture où:
1. Les données sont passées au LLM en **blocs JSON structurés**
2. Le LLM formate ces données en **Markdown conversationnel** grâce aux **few-shot examples**
3. Cette approche permet un formatage **naturel et contextuel** par le LLM

```
┌─────────────────────────────────────────────────────────────────┐
│                   INTELLIA v10 - Data Flow                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   Tool Execution (parallel_executor)                             │
│        │                                                         │
│        ▼                                                         │
│   RegistryItem payloads (contacts, emails, events, ...)          │
│        │                                                         │
│        ▼                                                         │
│   _format_registry_mode_results()                                │
│        │                                                         │
│        ├── Group by type (CONTACT, EMAIL, EVENT, ...)            │
│        ├── _format_type_as_json()                                │
│        │      │                                                  │
│        │      └── _simplify_*_payload() (9 fonctions)            │
│        │           • _simplify_contact_payload()                 │
│        │           • _simplify_email_payload()                   │
│        │           • _simplify_event_payload()                   │
│        │           • _simplify_task_payload()                    │
│        │           • _simplify_file_payload()                    │
│        │           • _simplify_place_payload()                   │
│        │           • _simplify_weather_payload()                 │
│        │           • _simplify_wikipedia_payload()               │
│        │           • _simplify_search_payload()                  │
│        │                                                         │
│        ▼                                                         │
│   JSON Blocks (```json ... ```)                                  │
│        │                                                         │
│        ▼                                                         │
│   response_node → LLM avec:                                      │
│     • JSON data blocks                                           │
│     • Few-shot examples (prompts/v1/fewshot/*.txt)               │
│        │                                                         │
│        ▼                                                         │
│   LLM génère réponse Markdown conversationnelle                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Structure JSON Générée

Chaque type de données est converti en JSON avec cette structure:

```json
{
  "domain": "contacts",
  "action": "search",
  "count": 3,
  "contacts": [
    {
      "id": "contact_abc123",
      "name": "Jean Dupont",
      "url": "https://contacts.google.com/person/abc123",
      "emails": [{"type": "Travail", "value": "jean@company.com"}],
      "phones": [{"type": "Mobile", "value": "+33 6 12 34 56 78"}],
      "organization": "Tech Lead @ Acme Corp"
    }
  ]
}
```

### 3.3 Mapping Types → Domaines

| Registry Type | Domain | Items Key | Few-Shot (search) | Few-Shot (details) |
|---------------|--------|-----------|-------------------|---------------------|
| `CONTACT` | contacts | contacts | `contacts_search.txt` | `contacts_details.txt` |
| `EMAIL` | emails | emails | `emails_search.txt` | `emails_details.txt` |
| `EVENT` | calendar | events | `calendar_search.txt` | `calendar_details.txt` |
| `TASK` | tasks | tasks | `tasks_search.txt` | `tasks_details.txt` |
| `FILE` | drive | files | `drive_search.txt` | — |
| `PLACE` | places | places | `places_search.txt` | `places_details.txt` |
| `WEATHER` | weather | forecasts | `weather_search.txt` | — |
| `WIKIPEDIA_ARTICLE` | wikipedia | articles | `wikipedia_search.txt` | — |
| `SEARCH_RESULT` | search | results | `search_search.txt` | — |

### 3.4 Détection Automatique d'Action (search vs details)

**Fonction**: `_detect_action_from_items(type_name, items)`

La détection d'action utilise des heuristiques basées sur:
1. **Nombre d'items**: Multiple items → toujours "search"
2. **Indicateurs de détails**: Présence de champs riches spécifiques par domaine

```python
# Indicateurs par type (présents dans details mais pas dans search)
detail_indicators_by_type = {
    "CONTACT": ["photos", "relations", "organizations", "biographies", "events", ...],
    "EMAIL": ["body", "cc", "attachments"],
    "EVENT": ["attendees", "description", "reminders", "organizer"],
    "PLACE": ["hours", "opening_hours", "features", "website", "phone", ...],
    "TASK": ["notes", "subtasks", "priority", "created", "updated"],
}
```

**Flux de détection**:
```
Items count > 1? ────► YES ────► action = "search"
     │
     NO
     │
     ▼
Has detail indicators? ────► YES ────► action = "details"
     │
     NO
     │
     ▼
action = "search" (default)
```

### 3.5 Few-Shot Examples

**Fichiers**: `prompts/v1/fewshot/*.txt`

Chaque fichier few-shot contient:
1. Les données JSON d'entrée (format attendu)
2. La présentation Markdown attendue

Exemple (`contacts_search.txt`):
```
### Exemple: Contacts Google (resultats)

Donnees recues:
```json
{
  "domain": "contacts",
  "action": "search",
  "count": 2,
  "contacts": [...]
}
```

Presentation attendue:

---
👤 **[Jean Dupont](https://contacts.google.com/person/abc123)**
- 📧 Email (Travail): jean@example.com
- 📱 Mobile: +33 6 12 34 56 78
- 🏢 Tech Lead @ Acme Corp
---
```

### 3.6 Fonctions Clés

| Fonction | Rôle |
|----------|------|
| `_format_registry_mode_results()` | Point d'entrée: groupe et formate tous les items |
| `_format_type_as_json()` | Génère un bloc JSON pour un type donné |
| `_detect_action_from_items()` | **Nouveau v10.1**: Détecte search vs details par heuristiques |
| `_simplify_payload_for_json()` | Dispatcher vers les simplifiers |
| `_simplify_*_payload()` | 9 fonctions: extraient les champs pertinents |
| `_detect_result_domains_from_registry()` | Détecte les domaines présents dans le registry |
| `_detect_domain_operations()` | Génère les tuples (domain, operation) pour few-shot |
| `_format_resolved_context_for_prompt()` | Formate contexte résolu en JSON pour références |
| `load_fewshot_examples()` | Charge dynamiquement les few-shot pertinents |

---

## 4. State Management (MessagesState)

**Fichier**: `models.py`

```python
class MessagesState(TypedDict):
    # ═══════════════════════════════════════════════════════════
    # CORE CONVERSATION
    # ═══════════════════════════════════════════════════════════
    messages: Annotated[list[BaseMessage], add_messages_with_truncate]
    metadata: dict[str, Any]

    # ═══════════════════════════════════════════════════════════
    # ROUTING (router_node)
    # ═══════════════════════════════════════════════════════════
    routing_history: list[RouterOutput]  # Décisions avec confidence

    # ═══════════════════════════════════════════════════════════
    # PLANNING (planner_node)
    # ═══════════════════════════════════════════════════════════
    execution_plan: ExecutionPlan        # Plan LLM généré
    planner_metadata: dict | None        # Pour streaming frontend
    planner_error: dict | None           # Détails erreur
    validation_result: Any | None        # Résultat validation

    # ═══════════════════════════════════════════════════════════
    # SEMANTIC VALIDATION (Phase 2 OPTIMPLAN)
    # ═══════════════════════════════════════════════════════════
    semantic_validation: SemanticValidationResult
    clarification_response: str | None   # Input user clarification
    needs_replan: bool                   # Trigger re-génération
    planner_iteration: int               # Compteur (max: 2)

    # ═══════════════════════════════════════════════════════════
    # HITL APPROVAL (Phase 8)
    # ═══════════════════════════════════════════════════════════
    approval_evaluation: Any | None      # Évaluation stratégies
    plan_approved: bool | None           # Décision user
    plan_rejection_reason: str | None    # Raison rejet

    # ═══════════════════════════════════════════════════════════
    # EXECUTION (task_orchestrator_node)
    # ═══════════════════════════════════════════════════════════
    completed_steps: dict[str, dict]     # Résultats par step_id
    agent_results: dict[str, Any]        # "turn_id:agent_name" → result

    # ═══════════════════════════════════════════════════════════
    # HITL INTERACTIONS (Phase 8.1)
    # ═══════════════════════════════════════════════════════════
    pending_hitl_interaction: dict | None  # HitlInteraction
    hitl_result: dict | None               # Decision user sur interaction

    # ═══════════════════════════════════════════════════════════
    # DATA REGISTRY (Rendu Frontend + INTELLIA v10)
    # ═══════════════════════════════════════════════════════════
    registry: Annotated[dict[str, RegistryItem], merge_registry]

    # ═══════════════════════════════════════════════════════════
    # SESSION/USER CONTEXT
    # ═══════════════════════════════════════════════════════════
    current_turn_id: int                 # Compteur turns
    session_id: str                      # Thread ID persistance
    user_timezone: str                   # IANA (ex: "Europe/Paris")
    user_language: str                   # Code langue (fr, en, es)
    oauth_scopes: list[str]              # Scopes connecteurs actifs
```

---

## 5. Exécution Parallèle (parallel_executor)

**Fichier**: `orchestration/parallel_executor.py`

### Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    execute_plan_parallel()                          │
│                                                                     │
│   ExecutionPlan                                                     │
│        │                                                            │
│        ▼                                                            │
│   ┌─────────────────────────────────────────────────────────────┐  │
│   │              DependencyGraph.calculate_waves()               │  │
│   │                                                              │  │
│   │   Step 0 ──────┬──────── Step 1                             │  │
│   │                │                                             │  │
│   │   Step 2 ──────┴──────── Step 3 ──────── Step 4             │  │
│   │                                                              │  │
│   │   Wave 0: [Step 0, Step 2]  (parallèle)                     │  │
│   │   Wave 1: [Step 1, Step 3]  (parallèle, après Wave 0)       │  │
│   │   Wave 2: [Step 4]          (après Wave 1)                  │  │
│   └─────────────────────────────────────────────────────────────┘  │
│        │                                                            │
│        ▼                                                            │
│   ┌─────────────────────────────────────────────────────────────┐  │
│   │                Pour chaque Wave                              │  │
│   │                                                              │  │
│   │   asyncio.gather(                                            │  │
│   │       _execute_single_step_async(step_0),                    │  │
│   │       _execute_single_step_async(step_2),                    │  │
│   │   )                                                          │  │
│   │                     │                                        │  │
│   │                     ▼                                        │  │
│   │   ┌─────────────────────────────────────────────────────┐   │  │
│   │   │         _execute_single_step_async(step)            │   │  │
│   │   │                                                     │   │  │
│   │   │  1. Resolve parameters ($steps.X.field → values)    │   │  │
│   │   │  2. Route to agent (contacts/emails/calendar)       │   │  │
│   │   │  3. Execute tool via agent                          │   │  │
│   │   │  4. Capture result + registry items                 │   │  │
│   │   │  5. Check requires_confirmation                     │   │  │
│   │   │  6. Return StepResult (frozen Pydantic)             │   │  │
│   │   └─────────────────────────────────────────────────────┘   │  │
│   │                     │                                        │  │
│   │                     ▼                                        │  │
│   │   Merge wave results → completed_steps                       │  │
│   └─────────────────────────────────────────────────────────────┘  │
│        │                                                            │
│        ▼                                                            │
│   ┌─────────────────────────────────────────────────────────────┐  │
│   │              ParallelExecutionResult                         │  │
│   │                                                              │  │
│   │   • completed_steps: {step_id → StepResult}                  │  │
│   │   • registry: {item_id → RegistryItem}                       │  │
│   │   • pending_draft: PendingDraftInfo | None                   │  │
│   └─────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### Résolution des Références

```python
# Dans les paramètres du plan:
"contact_id": "$steps.0.contacts[0].resource_name"

# Résolution via ReferenceResolver:
1. Parser "$steps.0.contacts[0].resource_name"
2. Lookup completed_steps["0"].result
3. Navigate: result["contacts"][0]["resource_name"]
4. Retourner valeur réelle: "people/c123456"
```

---

## 6. HITL (Human-in-the-Loop)

### 3 Niveaux d'Interaction

```
┌─────────────────────────────────────────────────────────────────────┐
│                        NIVEAU 1                                      │
│                 Clarification Sémantique                            │
│                   (Phase 2 OPTIMPLAN)                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   Trigger: semantic_validation.requires_clarification = True         │
│   Node: clarification_node                                          │
│   Interaction: ClarificationInteraction                             │
│                                                                      │
│   Flux:                                                             │
│   planner → semantic_validator → clarification → planner            │
│                                     ↑                               │
│                            interrupt()                              │
│                            User répond                              │
│                                                                      │
│   Questions générées automatiquement:                               │
│   • "Voulez-vous envoyer à tous les contacts ou un seul?"           │
│   • "Quel type de réunion créer: call ou présentiel?"               │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                        NIVEAU 2                                      │
│                    Approbation du Plan                              │
│                       (Phase 8)                                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   Trigger: validation_result.requires_hitl = True                    │
│   Node: approval_gate_node                                          │
│   Interaction: PlanApprovalInteraction                              │
│                                                                      │
│   Flux:                                                             │
│   planner → approval_gate → task_orchestrator                       │
│                  ↑                                                  │
│             interrupt()                                             │
│             User: APPROVE/REJECT/EDIT/REPLAN                        │
│                                                                      │
│   Décisions:                                                        │
│   • APPROVE → Exécuter le plan                                      │
│   • REJECT  → Expliquer pourquoi, fin                               │
│   • EDIT    → Modifier paramètres, re-valider                       │
│   • REPLAN  → Nouvelles instructions, re-générer                    │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                        NIVEAU 3                                      │
│                   Confirmation Draft                                │
│                       (Phase 8.1)                                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   Trigger: tool.requires_confirmation = True                         │
│   Node: hitl_dispatch_node → DRAFT_CRITIQUE interaction             │
│   Interaction: DraftCritiqueInteraction                             │
│                                                                      │
│   Flux:                                                             │
│   task_orchestrator → hitl_dispatch_node → response                 │
│                           ↑                                         │
│                      interrupt()                                    │
│                      User: CONFIRM/EDIT/CANCEL                      │
│                                                                      │
│   Types de drafts:                                                  │
│   • Email a envoyer                                                 │
│   • Evenement a creer                                               │
│   • Contact a ajouter                                               │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Pattern interrupt()

```python
# Dans un node HITL:
async def node_function(state: MessagesState) -> dict:
    # Preparer payload
    payload = {
        "action_requests": [{
            "type": "clarification",  # ou "plan_approval", "destructive_confirm"
            "questions": [...],
            "metadata": {...}
        }]
    }

    # PAUSE: LangGraph sauvegarde checkpoint
    decision = interrupt(payload)

    # RESUME: Après Command(resume={...}) du frontend
    # decision contient la réponse user

    return {"state_key": decision["value"]}
```

---

## 7. Data Registry (Rendu Frontend)

**Fichiers**: `data_registry/models.py`, `data_registry/state.py`

### Structure

```
┌─────────────────────────────────────────────────────────────────────┐
│                         RegistryItem                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   {                                                                  │
│     "id": "contact_abc123",                                         │
│     "type": "CONTACT",           # CONTACT|EMAIL|EVENT|DRAFT|...    │
│     "payload": {                                                    │
│       "resourceName": "people/c123",                                │
│       "names": [{"displayName": "Jean Dupont"}],                    │
│       "emailAddresses": [{"value": "jean@example.com"}],            │
│       ...                                                           │
│     },                                                              │
│     "meta": {                                                       │
│       "source": "google_contacts",                                  │
│       "domain": "contacts",                                         │
│       "timestamp": "2025-11-27T10:30:00Z",                          │
│       "ttl": 300,                                                   │
│       "from_cache": true,                                           │
│       "cached_at": "2025-11-27T10:25:00Z"                           │
│     }                                                               │
│   }                                                                  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Flux Données (INTELLIA v10)

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                      │
│   Tool Execution                                                     │
│        │                                                            │
│        ▼                                                            │
│   ToolOutput.registry_items: [RegistryItem, ...]                    │
│        │                                                            │
│        ▼                                                            │
│   parallel_executor accumule                                        │
│        │                                                            │
│        ▼                                                            │
│   ParallelExecutionResult.registry: {id → RegistryItem}             │
│        │                                                            │
│        ▼                                                            │
│   state.registry (merge_registry reducer)                           │
│        │                                                            │
│        ├────────────────────────┬───────────────────────┐           │
│        │                        │                       │           │
│        ▼                        ▼                       ▼           │
│   SSE: registry_update     response_node           Frontend        │
│   (AVANT réponse LLM)      (INTELLIA v10)         pré-render       │
│        │                        │                  composants       │
│        │                        │                                   │
│        │                        ▼                                   │
│        │            _format_registry_mode_results()                 │
│        │                        │                                   │
│        │                        ▼                                   │
│        │            JSON blocks pour LLM                            │
│        │                        │                                   │
│        │                        ▼                                   │
│        │            LLM formate via few-shots                       │
│        │                        │                                   │
│        ▼                        ▼                                   │
│   Frontend affiche         Réponse Markdown                         │
│   composants riches        conversationnelle                        │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 8. Streaming SSE

**Fichier**: `services/streaming/service.py`

### Types d'Événements

| Event Type | Source | Contenu |
|-----------|--------|---------|
| `token` | response_node | Token LLM pour streaming |
| `router_decision` | router_node | Décision routing + confidence |
| `execution_step` | graph transitions | Entrée/sortie node |
| `planner_metadata` | planner_node | Structure plan + coût |
| `registry_update` | tools | Data Registry items |
| `hitl_interrupt_metadata` | HITL nodes | Payload interrupt |
| `content_replacement` | response_node | Contenu post-traité (rare) |
| `planner_error` | planner_node | Erreur génération |
| `error` | Any node | Message exception |
| `done` | Graph completion | Chunk final |

### Flux Streaming

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                      │
│   OrchestrationService.async_stream()                               │
│        │                                                            │
│        ▼                                                            │
│   graph.astream(input, config, stream_mode=["messages", "updates"]) │
│        │                                                            │
│        ▼                                                            │
│   yield (mode, chunk) tuples                                        │
│        │                                                            │
│        ▼                                                            │
│   StreamingService._process_chunk()                                 │
│        │                                                            │
│        ├─── mode="messages" ───► Extraire tokens → SSE token        │
│        │                                                            │
│        ├─── mode="updates" ────► Extraire metadata:                 │
│        │                         • router_decision                  │
│        │                         • planner_metadata                 │
│        │                         • registry_update                  │
│        │                         • execution_step                   │
│        │                         • hitl_interrupt_metadata          │
│        │                                                            │
│        ▼                                                            │
│   yield ChatStreamChunk(type=..., content=...)                      │
│        │                                                            │
│        ▼                                                            │
│   Frontend SSE EventSource                                          │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 9. Configuration Clé

### Router

| Setting | Default | Description |
|---------|---------|-------------|
| `router_llm_model` | gpt-4.1-nano | Modèle classification rapide |
| `router_confidence_high` | 0.85 | Seuil haute confiance |
| `router_confidence_medium` | 0.65 | Seuil moyenne confiance |
| `router_confidence_low` | 0.45 | Seuil basse confiance |
| `llm_cache_enabled` | True | Cache réponses router |

### Planner

| Setting | Default | Description |
|---------|---------|-------------|
| `planner_llm_model` | gpt-4 | Modèle génération plan |
| `planner_timeout_seconds` | 30 | Timeout génération |
| `planner_max_retries` | 2 | Retries validation échec |
| `planner_max_cost_usd` | 5.0 | Budget exécution |
| `planner_max_steps` | 20 | Max steps dans plan |
| `planner_max_replans` | 2 | Max itérations clarification |

### HITL

| Setting | Default | Description |
|---------|---------|-------------|
| `tool_approval_enabled` | True | Activer approval gate |
| `hitl_plan_approval_enabled` | True | Activer approbation plan |
| `semantic_validation_enabled` | True | Activer validation sémantique |

### Messages

| Setting | Default | Description |
|---------|---------|-------------|
| `max_tokens_history` | 100000 | Max tokens historique |
| `max_messages_history` | 50 | Max messages fallback |

---

## 10. Métriques Prometheus

### Nodes

```
agent_node_executions_total{node_name, status}
agent_node_duration_seconds{node_name}
```

### Router

```
router_decisions_total{confidence_tier}
router_confidence_score
router_fallback_total
```

### Planner

```
planner_plans_created_total{execution_mode}
planner_errors_total{error_type}
planner_catalogue_size_tools{filtering_applied}
```

### HITL

```
hitl_plan_approval_requests{strategy}
hitl_plan_decisions{decision}
hitl_plan_approval_latency
semantic_validation_clarification_requests
```

### Streaming

```
sse_time_to_first_token_seconds
sse_tokens_generated_total
sse_streaming_duration_seconds
```

---

## 11. Tools & Agents

### 11.1 Architecture des Connecteurs (Dual-Mode)

**Fichier**: `tools/base.py`

L'architecture supporte **deux types de connecteurs** avec des patterns distincts:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    ARCHITECTURE DES CONNECTEURS                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   ┌───────────────────────────────────────────────────────────────┐ │
│   │                    ToolDependencies (DI)                       │ │
│   │                                                                │ │
│   │   • db_session: AsyncSession                                  │ │
│   │   • get_connector_service() → ConcurrencySafeConnectorService │ │
│   │   • get_or_create_client() → Cached client                    │ │
│   └───────────────────────────────────────────────────────────────┘ │
│                              │                                       │
│                              ▼                                       │
│   ┌───────────────────────────────────────────────────────────────┐ │
│   │              ConcurrencySafeConnectorService                   │ │
│   │                                                                │ │
│   │   Thread-safe wrapper avec asyncio.Lock pour:                 │ │
│   │                                                                │ │
│   │   ├── get_connector_credentials(user_id, type)                │ │
│   │   │   → OAuth tokens (Google)                                 │ │
│   │   │                                                           │ │
│   │   └── get_api_key_credentials(user_id, type)                  │ │
│   │       → API keys chiffrées (Weather, Perplexity)              │ │
│   └───────────────────────────────────────────────────────────────┘ │
│                              │                                       │
│              ┌───────────────┴───────────────┐                      │
│              │                               │                      │
│              ▼                               ▼                      │
│   ┌──────────────────┐            ┌──────────────────┐             │
│   │  ConnectorTool   │            │ APIKeyConnector  │             │
│   │     (OAuth)      │            │      Tool        │             │
│   ├──────────────────┤            ├──────────────────┤             │
│   │ • Google Contacts│            │ • OpenWeatherMap │             │
│   │ • Google Gmail   │            │ • Perplexity AI  │             │
│   │ • Google Calendar│            │ • (futurs...)    │             │
│   │ • Google Drive   │            └──────────────────┘             │
│   │ • Google Tasks   │                                              │
│   │ • Google Places  │                                              │
│   └──────────────────┘                                              │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 11.2 ConnectorTool (OAuth)

**Classe abstraite pour les connecteurs OAuth** (Google, Microsoft, etc.)

```python
class ConnectorTool[ClientType](ABC):
    """Base class for OAuth-based connector tools."""

    # Subclasses must define:
    connector_type: ConnectorType       # e.g., GOOGLE_CONTACTS
    client_class: type[ClientType]      # e.g., GooglePeopleClient

    # Optional:
    registry_enabled: bool = False      # Enable Data Registry mode

    async def execute(self, runtime: ToolRuntime, **kwargs) -> str:
        # 1. Validate runtime, extract user_id
        # 2. Get dependencies (DI)
        # 3. Get OAuth credentials from DB
        # 4. Get or create cached client
        # 5. Execute API call (subclass)
        # 6. Format response

    @abstractmethod
    async def execute_api_call(self, client, user_id, **kwargs) -> dict:
        """Subclass implements business logic only."""
        pass

    def create_client_factory(self, user_uuid, credentials, connector_service):
        """Returns async factory for client instantiation."""
        async def create_client():
            return self.client_class(user_uuid, credentials, connector_service)
        return create_client
```

**Flux OAuth:**
```
User Request → ConnectorTool.execute()
                    │
                    ▼
    get_connector_credentials(user_id, GOOGLE_*)
                    │
                    ▼
    DB: connectors table (encrypted tokens)
                    │
                    ▼
    ConnectorCredentials {
        access_token: str
        refresh_token: str
        expires_at: datetime
    }
                    │
                    ▼
    Create/Cache API Client → Execute API Call
```

### 11.3 APIKeyConnectorTool (API Keys)

**Classe abstraite pour les connecteurs à clé API** (Weather, Perplexity, etc.)

```python
class APIKeyConnectorTool[ClientType](ABC):
    """Base class for API key-based connector tools."""

    # Subclasses must define:
    connector_type: ConnectorType       # e.g., OPENWEATHERMAP
    client_class: type[ClientType]      # e.g., OpenWeatherMapClient

    # Optional:
    registry_enabled: bool = False      # Enable Data Registry mode

    async def execute(self, runtime: ToolRuntime, **kwargs) -> str:
        # 1. Validate runtime, extract user_id
        # 2. Get dependencies (DI)
        # 3. Get API key credentials from DB
        # 4. Create client with user's key
        # 5. Execute API call (subclass)
        # 6. Format response

    @abstractmethod
    def create_client(self, credentials: APIKeyCredentials, user_id: UUID) -> ClientType:
        """Create client instance from API key."""
        pass

    @abstractmethod
    async def execute_api_call(self, client, user_id, **kwargs) -> dict:
        """Subclass implements business logic only."""
        pass
```

**Flux API Key:**
```
User Request → APIKeyConnectorTool.execute()
                    │
                    ▼
    get_api_key_credentials(user_id, OPENWEATHERMAP)
                    │
                    ▼
    DB: connectors table (Fernet encrypted)
                    │
                    ▼
    APIKeyCredentials {
        api_key: str          # Clé déchiffrée
        key_name: str | None  # Nom optionnel
    }
                    │
                    ▼
    create_client(credentials, user_id) → Execute API Call
```

### 11.4 Différences Clés OAuth vs API Key

| Aspect | ConnectorTool (OAuth) | APIKeyConnectorTool (API Key) |
|--------|----------------------|------------------------------|
| **Auth Type** | OAuth 2.0 tokens | API Key simple |
| **DB Storage** | access_token, refresh_token, expires_at | api_key (Fernet encrypted) |
| **Token Refresh** | Automatique via ConnectorService | N/A |
| **Client Caching** | Via `get_or_create_client()` | Non (création à chaque appel) |
| **Exemples** | Google Contacts, Gmail, Calendar, Drive, Tasks, Places | OpenWeatherMap, Perplexity |
| **User Setup** | OAuth flow (redirect) | Saisie clé API dans settings |

### 11.5 Tool Registry Architecture

**Fichier**: `orchestration/parallel_executor.py` (ToolRegistry)

```
┌─────────────────────────────────────────────────────────────────────┐
│                         ToolRegistry                                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   Initialisation au démarrage de parallel_executor:                  │
│                                                                      │
│   _tools = {                                                         │
│     # Contacts (OAuth)                                               │
│     "search_contacts_tool", "list_contacts_tool",                    │
│     "get_contact_details_tool",                                      │
│     # Emails (OAuth)                                                 │
│     "search_emails_tool", "get_email_details_tool", "send_email_tool"│
│     # Calendar (OAuth)                                               │
│     "search_events_tool", "get_event_details_tool",                  │
│     "create_event_tool", "update_event_tool", "delete_event_tool",   │
│     # Drive (OAuth)                                                  │
│     "search_files_tool", "list_files_tool", "get_file_content_tool", │
│     # Tasks (OAuth)                                                  │
│     "list_tasks_tool", "create_task_tool", "complete_task_tool",     │
│     "list_task_lists_tool",                                          │
│     # Weather (API Key)                                              │
│     "get_current_weather_tool", "get_weather_forecast_tool",         │
│     "get_hourly_forecast_tool",                                      │
│     # Wikipedia (Public API - no auth)                               │
│     "search_wikipedia_tool", "get_wikipedia_summary_tool",           │
│     "get_wikipedia_article_tool", "get_wikipedia_related_tool",      │
│     # Perplexity (API Key)                                           │
│     "perplexity_search_tool", "perplexity_ask_tool",                 │
│     # Places (OAuth)                                                 │
│     "search_places_tool", "get_place_details_tool",                  │
│     # Context & Query                                                │
│     "resolve_reference", "get_context_list", "set_current_item",     │
│     "get_context_state", "list_active_domains",                      │
│     "local_query_engine_tool",                                       │
│   }                                                                  │
│                                                                      │
│   Lookup: registry.get_tool(step.tool_name) → Tool instance          │
│   Invocation: tool.ainvoke({params}, config)                         │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 11.6 Domain Tools (par type de connecteur)

#### OAuth Connectors (Google)

##### Contacts Agent
**Fichier**: `tools/google_contacts_tools.py`

| Tool | Description | Catégorie |
|------|-------------|-----------|
| `search_contacts_tool` | Recherche contacts (query fuzzy) | READ |
| `list_contacts_tool` | Liste paginée (pageSize, pageToken) | READ |
| `get_contact_details_tool` | Détails complet d'un contact | READ |

##### Emails Agent
**Fichier**: `tools/emails_tools.py`

| Tool | Description | Catégorie |
|------|-------------|-----------|
| `search_emails_tool` | Recherche Gmail (query syntax) | READ |
| `get_email_details_tool` | Contenu email complet | READ |
| `send_email_tool` | Envoi email (→ Draft HITL) | WRITE |

##### Calendar Agent
**Fichier**: `tools/calendar_tools.py`

| Tool | Description | Catégorie | HITL |
|------|-------------|-----------|------|
| `search_events_tool` | Recherche events (query, time_range) | READ | — |
| `get_event_details_tool` | Détails event complet | READ | — |
| `create_event_tool` | Création event | WRITE | Draft |
| `update_event_tool` | Modification event | WRITE | Draft |
| `delete_event_tool` | Suppression event | WRITE | Draft |

##### Drive Agent
**Fichier**: `tools/drive_tools.py`

| Tool | Description | Catégorie |
|------|-------------|-----------|
| `search_files_tool` | Recherche fichiers Drive (query) | READ |
| `list_files_tool` | Liste fichiers d'un dossier | READ |
| `get_file_content_tool` | Contenu/métadonnées fichier | READ |

##### Tasks Agent
**Fichier**: `tools/tasks_tools.py`

| Tool | Description | Catégorie | HITL |
|------|-------------|-----------|------|
| `list_tasks_tool` | Liste tâches d'une liste | READ | — |
| `list_task_lists_tool` | Liste des listes de tâches | READ | — |
| `create_task_tool` | Création tâche | WRITE | Draft |
| `complete_task_tool` | Marquer tâche complète | WRITE | — |

##### Places Agent
**Fichier**: `tools/places_tools.py`

| Tool | Description | Catégorie |
|------|-------------|-----------|
| `search_places_tool` | Recherche lieux (query texte ou proximité) | READ |
| `get_place_details_tool` | Détails d'un lieu | READ |

#### API Key Connectors

##### Weather Agent
**Fichier**: `tools/weather_tools.py`
**Connecteur**: OpenWeatherMap (API Key)

| Tool | Description | Catégorie |
|------|-------------|-----------|
| `get_current_weather_tool` | Météo actuelle (ville/coords) | READ |
| `get_weather_forecast_tool` | Prévisions 5 jours | READ |
| `get_hourly_forecast_tool` | Prévisions horaires | READ |

**Architecture**:
```python
class GetCurrentWeatherTool(APIKeyConnectorTool[OpenWeatherMapClient]):
    connector_type = ConnectorType.OPENWEATHERMAP
    client_class = OpenWeatherMapClient

    def create_client(self, credentials: APIKeyCredentials, user_id: UUID):
        return OpenWeatherMapClient(
            api_key=credentials.api_key,
            user_id=user_id
        )

    async def execute_api_call(self, client, user_id, **kwargs):
        return await client.get_current_weather(
            location=kwargs["location"],
            units=kwargs.get("units", "metric")
        )
```

##### Perplexity Agent
**Fichier**: `tools/perplexity_tools.py`
**Connecteur**: Perplexity AI (API Key)

| Tool | Description | Catégorie |
|------|-------------|-----------|
| `perplexity_search_tool` | Recherche web via Perplexity | READ |
| `perplexity_ask_tool` | Question/réponse via Perplexity | READ |

**Architecture**:
```python
class PerplexitySearchTool(APIKeyConnectorTool[PerplexityClient]):
    connector_type = ConnectorType.PERPLEXITY
    client_class = PerplexityClient

    def create_client(self, credentials: APIKeyCredentials, user_id: UUID):
        return PerplexityClient(
            api_key=credentials.api_key,
            user_id=user_id
        )

    async def execute_api_call(self, client, user_id, **kwargs):
        return await client.search(
            query=kwargs["query"],
            search_recency_filter=kwargs.get("recency")
        )
```

#### Public API (No Auth)

##### Wikipedia Agent
**Fichier**: `tools/wikipedia_tools.py`
**Connecteur**: Wikipedia (API publique)

| Tool | Description | Catégorie |
|------|-------------|-----------|
| `search_wikipedia_tool` | Recherche articles Wikipedia | READ |
| `get_wikipedia_summary_tool` | Résumé d'un article | READ |
| `get_wikipedia_article_tool` | Article complet | READ |
| `get_wikipedia_related_tool` | Articles connexes | READ |

### 11.7 Tool Output Standards

Tous les tools retournent `StandardToolOutput` (défini dans `tools/output.py`):

```python
class StandardToolOutput(BaseModel):
    summary_for_llm: str          # Résumé textuel pour LLM (compact)
    registry_updates: dict[str, RegistryItem]  # Items pour frontend + INTELLIA v10
    tool_metadata: dict[str, Any] # Stats, pagination, etc.
    requires_confirmation: bool = False  # Trigger draft HITL
```

### 11.8 Ajouter un Nouveau Connecteur

#### Pour un connecteur OAuth (ex: Microsoft)

```python
# 1. Ajouter le type dans ConnectorType (models.py)
class ConnectorType(str, Enum):
    MICROSOFT_OUTLOOK = "microsoft_outlook"

# 2. Créer le client (connectors/clients/microsoft_outlook_client.py)
class MicrosoftOutlookClient:
    def __init__(self, user_id: UUID, credentials: ConnectorCredentials, connector_service):
        self.credentials = credentials
        # ...

# 3. Créer les tools (tools/microsoft_outlook_tools.py)
class SearchOutlookTool(ConnectorTool[MicrosoftOutlookClient]):
    connector_type = ConnectorType.MICROSOFT_OUTLOOK
    client_class = MicrosoftOutlookClient

    async def execute_api_call(self, client, user_id, **kwargs):
        return await client.search_emails(kwargs["query"])
```

#### Pour un connecteur API Key (ex: OpenAI)

```python
# 1. Ajouter le type dans ConnectorType (models.py)
class ConnectorType(str, Enum):
    OPENAI = "openai"

# 2. Créer le client (connectors/clients/openai_client.py)
class OpenAIClient:
    def __init__(self, api_key: str, user_id: UUID):
        self.api_key = api_key
        self.user_id = user_id

# 3. Créer les tools (tools/openai_tools.py)
class OpenAICompletionTool(APIKeyConnectorTool[OpenAIClient]):
    connector_type = ConnectorType.OPENAI
    client_class = OpenAIClient

    def create_client(self, credentials: APIKeyCredentials, user_id: UUID):
        return OpenAIClient(api_key=credentials.api_key, user_id=user_id)

    async def execute_api_call(self, client, user_id, **kwargs):
        return await client.complete(kwargs["prompt"])
```

---

## 12. Fichiers Clés

| Catégorie | Fichier | Description |
|-----------|---------|-------------|
| **Graph** | `graph.py` | Définition principale graph |
| **State** | `models.py` | MessagesState schema |
| **Nodes** | `nodes/router_node_v3.py` | Classification intent (Architecture v3) |
| | `nodes/planner_node_v3.py` | Génération plan LLM (SmartPlannerService) |
| | `nodes/semantic_validator_node.py` | Validation sémantique |
| | `nodes/clarification_node.py` | HITL clarification |
| | `nodes/approval_gate_node.py` | HITL approbation |
| | `nodes/task_orchestrator_node.py` | Dispatch parallèle |
| | `nodes/hitl_dispatch_node.py` | HITL interactions (Phase 8.1) |
| | `nodes/response_node.py` | Synthèse réponse (INTELLIA v10) |
| | `nodes/routing.py` | Fonctions routing |
| **Orchestration** | `orchestration/parallel_executor.py` | Exécution asyncio + ToolRegistry |
| | `orchestration/plan_schemas.py` | DSL ExecutionPlan |
| | `orchestration/dependency_graph.py` | Calcul waves |
| | `orchestration/condition_evaluator.py` | Résolution refs |
| **Tools Base** | `tools/base.py` | **ConnectorTool + APIKeyConnectorTool** |
| | `tools/output.py` | StandardToolOutput |
| | `tools/mixins.py` | ToolOutputMixin |
| | `tools/decorators.py` | @connector_tool |
| **Tools OAuth** | `tools/google_contacts_tools.py` | Contacts tools |
| | `tools/emails_tools.py` | Gmail tools |
| | `tools/calendar_tools.py` | Calendar tools |
| | `tools/drive_tools.py` | Drive tools |
| | `tools/tasks_tools.py` | Tasks tools |
| | `tools/places_tools.py` | Places tools |
| **Tools API Key** | `tools/weather_tools.py` | Weather tools (OpenWeatherMap) |
| | `tools/perplexity_tools.py` | Perplexity tools |
| **Tools Public** | `tools/wikipedia_tools.py` | Wikipedia tools |
| **Dependencies** | `dependencies.py` | ToolDependencies + get_dependencies() |
| **Data Registry** | `data_registry/models.py` | RegistryItem, RegistryItemType |
| | `data_registry/state.py` | merge_registry reducer |
| **Prompts** | `prompts/v1/response_system_prompt.txt` | Prompt response LLM |
| | `prompts/v1/fewshot/*.txt` | Few-shot examples (10 domaines) |
| | `prompts/v1/prompt_loader.py` | Chargement dynamique prompts |
| **Drafts** | `drafts/models.py` | Draft types & lifecycle |
| | `drafts/service.py` | create_*_draft functions |
| **Streaming** | `services/streaming/service.py` | SSE formatting |
| **HITL** | `services/hitl/registry.py` | Types interactions |
| **Connectors** | `connectors/service.py` | ConnectorService |
| | `connectors/schemas.py` | ConnectorCredentials, APIKeyCredentials |

---

## 13. INTELLIPLANNER - Orchestration Avancée

**Version**: 1.1 (2025-12-06)
**Status**: Phase B+ ✅ Production Ready | Phase E ⚠️ Partiellement Implémenté

INTELLIPLANNER est un ensemble d'améliorations architecturales pour le système d'orchestration multi-agents. Il comprend deux composants principaux:

> **Note**: La Phase E (AdaptiveRePlanner) est partiellement implémentée. Les décisions `RETRY_SAME`, `REPLAN_MODIFIED` et `REPLAN_NEW` ne sont pas encore opérationnelles (voir section 13.8).

### 13.1 Phase B+: Flux de Données Structurées

#### Problème Résolu

Les templates Jinja2 comme `{{ steps.list_all_calendars.calendars }}` échouaient car seul `summary_for_llm` (texte) était stocké dans `completed_steps`, pas les données structurées provenant de `registry_updates`.

#### Architecture du Flux

```
StandardToolOutput (tool)
    ↓ get_step_output()
ToolExecutionResult.structured_data
    ↓ _build_step_result()
StepResult.structured_data
    ↓ _merge_single_step_result()
completed_steps[step_id]
    ↓ Jinja2 context
{{ steps.step_id.field }}
```

#### Composants Modifiés

| Fichier | Modification |
|---------|--------------|
| `tools/output.py` | Ajout `structured_data`, `get_step_output()`, `REGISTRY_TYPE_TO_KEY` |
| `orchestration/parallel_executor.py` | `StepResult.structured_data` + `_merge_single_step_result()` |
| `orchestration/schemas.py` | `StepResult` export pour orchestration |
| `orchestration/jinja_evaluator.py` | `JinjaEvaluator` pour évaluation templates sécurisée |
| `query_engine/models.py` | Source "steps" acceptée dans `validate_source()` |

#### API: StandardToolOutput

```python
from src.domains.agents.tools.output import StandardToolOutput, REGISTRY_TYPE_TO_KEY

output = StandardToolOutput(
    summary_for_llm="Found 3 calendars",
    registry_updates={...},  # RegistryItems pour SSE
    structured_data={        # NOUVEAU - Pour Jinja2
        "calendars": [{"id": "cal1"}, {"id": "cal2"}],
        "count": 2,
        "primary_id": "cal1",
    },
)

# Accès aux données pour Jinja2
step_output = output.get_step_output()
# → {"calendars": [...], "count": 2, "primary_id": "cal1"}
```

#### Fallback Automatique

Si `structured_data` n'est pas peuplé, `get_step_output()` extrait automatiquement les payloads depuis `registry_updates` groupés par type:

```python
output = StandardToolOutput(
    summary_for_llm="Found 2 contacts",
    registry_updates={
        "contact_abc": RegistryItem(type=CONTACT, payload={"name": "John"}),
        "contact_def": RegistryItem(type=CONTACT, payload={"name": "Jane"}),
    },
)

output.get_step_output()
# → {"contacts": [{"name": "John"}, {"name": "Jane"}], "count": 2}
```

#### Mapping Type → Clé

```python
REGISTRY_TYPE_TO_KEY = {
    CONTACT: "contacts",
    EMAIL: "emails",
    EVENT: "events",
    TASK: "tasks",
    FILE: "files",
    CALENDAR: "calendars",
    PLACE: "places",
    WEATHER: "weather",      # Singulier pour météo
    WIKIPEDIA_ARTICLE: "articles",
    SEARCH_RESULT: "results",
    DRAFT: "drafts",
    CHART: "charts",
    NOTE: "notes",
    CALENDAR_SLOT: "slots",
}
```

### 13.2 Phase E: AdaptiveRePlanner

#### Architecture

```
Execution Complete
    ↓
should_trigger_replan()
    ↓ [trigger detected]
analyze_execution_results()
    ↓
AdaptiveRePlanner.analyze_and_decide()
    ↓
RePlanResult (decision, strategy, user_message)
    ↓
Handle Decision (PROCEED / RETRY / REPLAN / ESCALATE / ABORT)
```

#### Triggers Détectés

| Trigger | Description |
|---------|-------------|
| `EMPTY_RESULTS` | Tous les outils ont retourné 0 résultat |
| `PARTIAL_EMPTY` | Certains outils sans résultat (> seuil configurable) |
| `PARTIAL_FAILURE` | Certains steps ont échoué avec erreurs |
| `SEMANTIC_MISMATCH` | Résultats ne correspondent pas à l'intention utilisateur |
| `REFERENCE_ERROR` | `$steps.X.field` n'a pas pu être résolu |
| `DEPENDENCY_ERROR` | Données de dépendance manquantes |
| `TIMEOUT` | Exécution a dépassé la limite de temps |
| `NONE` | Aucun trigger (exécution réussie) |

#### Décisions

| Décision | Signification |
|----------|---------------|
| `PROCEED` | Continuer normalement vers response_node |
| `RETRY_SAME` | Réexécuter le même plan (erreur transitoire) |
| `REPLAN_MODIFIED` | Régénérer avec paramètres modifiés |
| `REPLAN_NEW` | Nouvelle stratégie complète |
| `ESCALATE_USER` | Demander clarification utilisateur |
| `ABORT` | Abandonner et expliquer l'échec |

#### Stratégies de Recovery

| Stratégie | Usage |
|-----------|-------|
| `BROADEN_SEARCH` | Élargir critères de recherche |
| `ALTERNATIVE_SOURCE` | Utiliser source alternative |
| `REDUCE_SCOPE` | Réduire l'étendue |
| `SKIP_OPTIONAL` | Ignorer steps optionnels |
| `ADD_VERIFICATION` | Ajouter step de vérification |

#### API

```python
from src.domains.agents.orchestration import (
    AdaptiveRePlanner,
    RePlanContext,
    RePlanDecision,
    analyze_execution_results,
    should_trigger_replan,
)

# Quick check
should_replan, trigger = should_trigger_replan(
    execution_plan=plan,
    completed_steps=results,
)

if should_replan:
    # Full analysis
    analysis = analyze_execution_results(plan, results)

    context = RePlanContext(
        user_request="Find contacts named John",
        execution_plan=plan,
        completed_steps=results,
        execution_analysis=analysis,
        replan_attempt=0,
        max_attempts=3,
    )

    replanner = AdaptiveRePlanner()
    result = replanner.analyze_and_decide(context)

    if result.decision == RePlanDecision.PROCEED:
        # Continue to response
        pass
    elif result.decision == RePlanDecision.ESCALATE_USER:
        # Show result.user_message to user
        pass
```

### 13.3 Configuration

Dans `.env` ou `core/config/agents.py` et `core/config/advanced.py`:

```env
# INTELLIPLANNER Phase E Configuration (agents.py)
ADAPTIVE_REPLANNING_MAX_ATTEMPTS=3        # Max tentatives avant abandon (1-5)
ADAPTIVE_REPLANNING_EMPTY_THRESHOLD=0.8   # 80% empty → trigger re-planning

# INTELLIPLANNER Phase B+ Configuration (advanced.py)
JINJA_MAX_RECURSION_DEPTH=10              # Profondeur max évaluation Jinja2 (5-50)
```

### 13.4 Métriques Prometheus

```prometheus
# Triggers détectés par type
# Labels: empty_results, partial_empty, partial_failure, semantic_mismatch, reference_error, dependency_error, timeout, none
# Usage: Identifier les patterns d'échec fréquents. High empty_results = critères de recherche trop restrictifs
adaptive_replanner_triggers_total{trigger="empty_results|partial_empty|partial_failure|..."}

# Décisions prises par type
# Labels: proceed, retry_same, replan_modified, replan_new, escalate_user, abort
# Usage: Mesurer l'efficacité des stratégies de recovery. High abort = patterns irrécupérables
adaptive_replanner_decisions_total{decision="proceed|retry_same|replan_modified|..."}

# Tentatives de re-planning par numéro
# Labels: 1, 2, 3, etc.
# Usage: Idéalement la plupart des succès à attempt=1
adaptive_replanner_attempts_total{attempt_number="1|2|3"}

# Récupérations réussies par stratégie
# Labels: broaden_search, alternative_source, reduce_scope, skip_optional, add_verification
# Usage: Identifier les stratégies les plus efficaces pour optimiser le replanner
adaptive_replanner_recovery_success_total{strategy="broaden_search|alternative_source|..."}
```

### 13.5 Modèles de Données Phase E

```python
# Dataclasses pour l'analyse d'exécution
@dataclass
class StepAnalysis:
    """Analyse d'un step exécuté."""
    step_id: str
    tool_name: str | None
    success: bool
    has_results: bool
    result_count: int
    error: str | None
    execution_time_ms: int

@dataclass
class ExecutionAnalysis:
    """Analyse agrégée de l'exécution du plan."""
    total_steps: int
    completed_steps: int
    successful_steps: int
    failed_steps: int
    empty_steps: int  # Réussis mais sans résultats
    total_results: int
    execution_time_ms: int
    step_analyses: list[StepAnalysis]
    # Propriétés: success_rate, empty_rate, is_complete_failure, is_partial_failure, is_all_empty

@dataclass
class RePlanContext:
    """Contexte complet pour la décision de re-planning."""
    user_request: str
    user_language: str
    execution_plan: ExecutionPlan
    plan_id: str
    completed_steps: dict[str, Any]
    execution_analysis: ExecutionAnalysis
    replan_attempt: int
    max_attempts: int
    previous_triggers: list[RePlanTrigger] = []
    accumulated_errors: list[str] = []

class RePlanResult(BaseModel):
    """Résultat de l'analyse de re-planning."""
    decision: RePlanDecision
    trigger: RePlanTrigger
    confidence: float  # 0.0-1.0
    reasoning: str
    recovery_strategy: RecoveryStrategy = RecoveryStrategy.NONE
    modified_parameters: dict[str, Any] = {}
    user_message: str | None = None
    analysis_duration_ms: int = 0
```

### 13.6 Fichiers Clés

| Catégorie | Fichier | Description |
|-----------|---------|-------------|
| **Phase B+** | `tools/output.py` | `StandardToolOutput.structured_data` + `get_step_output()` + `REGISTRY_TYPE_TO_KEY` |
| | `orchestration/parallel_executor.py` | `StepResult.structured_data` + `_merge_single_step_result()` |
| | `orchestration/schemas.py` | `StepResult` export pour orchestration |
| | `orchestration/jinja_evaluator.py` | `JinjaEvaluator` pour évaluation templates sécurisée |
| | `orchestration/query_engine/models.py` | Source "steps" dans `validate_source()` |
| **Phase E** | `orchestration/adaptive_replanner.py` | Service complet (~900 lignes) avec enums, dataclasses, `AdaptiveRePlanner` |
| | `orchestration/__init__.py` | Exports publics (enums, fonctions utilitaires) |
| | `nodes/task_orchestrator_node.py` | Intégration post-exécution |
| | `core/config/agents.py` | `adaptive_replanning_*` settings |
| | `core/config/advanced.py` | `jinja_max_recursion_depth` setting |
| **Tests** | `tests/agents/orchestration/test_adaptive_replanner.py` | Tests unitaires replanner |
| | `tests/unit/.../test_standard_tool_output_structured_data.py` | Tests structured_data |

### 13.7 Backward Compatibility

- Tools existants sans `structured_data` → fallback automatique via `registry_updates`
- Tools legacy retournant `str` ou `dict` → comportement inchangé
- Aucun breaking change pour les API existantes
- `get_step_output()` gère gracieusement les cas edge (empty, None, etc.)

### 13.8 Status d'Implémentation Phase E

| Décision | Status | Notes |
|----------|--------|-------|
| `PROCEED` | ✅ Implémenté | Continue vers `response_node` |
| `ESCALATE_USER` | ✅ Implémenté | Message affiché à l'utilisateur |
| `ABORT` | ✅ Implémenté | Abandonne avec message explicatif |
| `RETRY_SAME` | ⏳ En cours | TODO - Requiert restructuration du graphe |
| `REPLAN_MODIFIED` | ⏳ En cours | TODO - Requiert appel au `planner_node` |
| `REPLAN_NEW` | ⏳ En cours | TODO - Stratégie complète nouvelle |

**Fonctionnalités opérationnelles:**
- ✅ Détection de tous les triggers (EMPTY_RESULTS, PARTIAL_FAILURE, etc.)
- ✅ Analyse des résultats d'exécution (`analyze_execution_results()`)
- ✅ Vérification rapide (`should_trigger_replan()`)
- ✅ Métriques Prometheus pour monitoring
- ✅ Configuration via `.env` (`ADAPTIVE_REPLANNING_*`)

**Prochaines étapes:**
Les flows `RETRY` et `REPLAN` nécessitent une restructuration du graphe LangGraph pour permettre une transition de `task_orchestrator_node` vers `planner_node` avec les paramètres de recovery.

### 13.9 Exemples d'Accès Templates Jinja2

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

**Note**: Le `JinjaEvaluator` utilise `SandboxedEnvironment` pour la sécurité et supporte la conversion automatique `.length` → `| length` pour compatibilité JavaScript.

---

## 14. Évolution Versions

| Phase | Feature | Status |
|-------|---------|--------|
| Core | Routing & Response basiques | ✓ |
| Phase 5 | Génération plan LLM | ✓ |
| Phase 5.2B-asyncio | Exécution parallèle asyncio | ✓ |
| Phase 2 OPTIMPLAN | Validation sémantique | ✓ |
| Phase 3 | Filtrage domaines | ✓ |
| Phase 8 | Approbation plan HITL | ✓ |
| LOT 6 | Draft critique HITL | ✓ |
| Data Registry | Rendu frontend riche | ✓ |
| LOT 5.4 | Calendar tools | ✓ |
| LOT 9 | Drive tools + Tasks tools | ✓ |
| LOT 10 | Weather tools + Wikipedia tools | ✓ |
| LOT 11 | Perplexity tools + Places tools | ✓ |
| **INTELLIA v10** | **JSON + Few-Shot Architecture** | ✓ |
| **INTELLIA v10.1** | **Détection dynamique search/details** | ✓ |
| **v4.2** | **APIKeyConnectorTool (Weather, Perplexity)** | ✓ |
| **INTELLIPLANNER B+** | **Flux données structurées (Jinja2 templates)** | ✓ |
| **INTELLIPLANNER E** | **Re-planning adaptatif intelligent** | ✓ |

---

## 15. Migration Notes

### v4.2 - APIKeyConnectorTool

**Nouveaux fichiers/classes**:
- `tools/base.py`: Ajout de `APIKeyConnectorTool[ClientType]`
- `dependencies.py`: Ajout de `get_api_key_credentials()` dans `ConcurrencySafeConnectorService`

**Outils migrés**:
- `weather_tools.py`: Utilise maintenant `APIKeyConnectorTool` au lieu d'un singleton global
- `perplexity_tools.py`: Idem

**Avantages**:
- **Clés per-user**: Chaque utilisateur utilise sa propre clé API (pas de clé partagée)
- **Sécurité**: Clés stockées chiffrées en DB (Fernet)
- **Maintenabilité**: Architecture générique pour futurs connecteurs API Key

**Breaking changes**: Aucun pour les utilisateurs finaux. Les tests doivent utiliser le pattern:
```python
with patch("src.domains.agents.tools.base.get_dependencies", return_value=mock_deps):
    result = await tool.execute(runtime, **kwargs)
```

### INTELLIA v10/v10.1

**Code supprimé**:
- `data_registry/formatters.py` - FormatterRegistry et BaseRegistryFormatter
- `data_registry/formatters_impl.py` - Toutes les implémentations de formatters

**Fonctions supprimées de response_node.py**:
- `_is_contacts_result_data()` - Détection par structure
- `_is_emails_result_data()` - Détection par structure
- `_format_unknown_type()` - Formatage Markdown fallback
- `_format_non_domain_results()` - Remplacé par `_format_status_messages()`
- `_detect_result_domains()` - Remplacé par `_detect_result_domains_from_registry()`

**Nouveau flux**:
1. Les données passent par le Data Registry (inchangé)
2. `_format_registry_mode_results()` génère des blocs JSON
3. `load_fewshot_examples()` charge les exemples pertinents
4. Le LLM formate les données en Markdown conversationnel

**Avantages**:
- **Formatage contextuel**: Le LLM adapte le format à la conversation
- **Maintenance simplifiée**: Un seul point de formatage (few-shots)
- **Extensibilité**: Ajouter un domaine = ajouter un fichier few-shot
- **Cohérence**: Tous les domaines utilisent le même pattern

**Nouveautés v10.1**:
- `_detect_action_from_items()` - Détection automatique search vs details
- Fichiers few-shot `*_details.txt` pour contacts, emails, calendar, tasks, places
- `_detect_domain_operations()` retourne maintenant des tuples `(domain, action)` dynamiques

### INTELLIPLANNER v1.0

**Phase B+ - Flux de Données Structurées**:

**Nouvelles API**:
```python
# tools/output.py
StandardToolOutput.structured_data  # Dict pour Jinja2
StandardToolOutput.get_step_output()  # Récupère données structurées
REGISTRY_TYPE_TO_KEY  # Mapping type → clé plurielle

# step_executor_node.py & parallel_executor.py
StepResult.structured_data  # Propagation données structurées
ToolExecutionResult.structured_data  # Résultat intermédiaire
```

**Comportement modifié**:
- `completed_steps[step_id]` contient maintenant `structured_data` (dict) au lieu de `summary_for_llm` (str)
- Templates Jinja2 `{{ steps.X.field }}` fonctionnent avec les données complètes

**Backward Compatibility**:
- Tools sans `structured_data` → fallback automatique depuis `registry_updates`
- Tools legacy retournant `str` → comportement inchangé

**Phase E - AdaptiveRePlanner**:

**Nouveaux modules**:
```python
# orchestration/adaptive_replanner.py
AdaptiveRePlanner  # Service principal
RePlanTrigger  # Enum triggers
RePlanDecision  # Enum décisions
RecoveryStrategy  # Enum stratégies
RePlanContext  # Context complet
RePlanResult  # Résultat analyse
ExecutionAnalysis  # Métriques exécution
analyze_execution_results()  # Helper analyse
should_trigger_replan()  # Quick check
```

**Configuration**:
```env
ADAPTIVE_REPLANNING_MAX_ATTEMPTS=3
ADAPTIVE_REPLANNING_EMPTY_THRESHOLD=0.8
```

**Métriques Prometheus** (4 nouvelles):
- `adaptive_replanner_triggers_total{trigger}`
- `adaptive_replanner_decisions_total{decision}`
- `adaptive_replanner_attempts_total{attempt_number}`
- `adaptive_replanner_recovery_success_total{strategy}`

**Breaking changes**: Aucun. L'intégration est opt-in via `task_orchestrator_node.py`.
