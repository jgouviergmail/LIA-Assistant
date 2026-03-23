# Debug Panel Architecture - Flow Analysis

## Vue d'ensemble

Le Debug Panel affiche les métriques de scoring (domaines, outils, intents) pour le tuning des thresholds. Le flow complet est :

```
router_node_v3 → StreamingService → SSE → useChat → Reducer → DebugPanel
```

## Flow détaillé

### 1. Backend - Génération des métriques (router_node_v3.py)

**Fichier**: `apps/api/src/domains/agents/nodes/router_node_v3.py`

**Responsabilités**:
- Appelle `QueryIntelligenceService.analyze()` pour obtenir intent + domaines + contexte
- Appelle `SemanticToolSelector.select_tools()` si route vers planner
- Stocke les résultats dans le state LangGraph :
  - `STATE_KEY_QUERY_INTELLIGENCE` → objet `QueryIntelligence` complet
  - `tool_selection_result` → dict sérialisé (pour compatibilité LangGraph)

**Code clé** (lignes 143-151, 237-240):
```python
intelligence = await intelligence_service.analyze(
    query=query,
    messages=messages,
    state=enriched_state,
    config=config,
)

state_update = {
    STATE_KEY_QUERY_INTELLIGENCE: intelligence,  # Objet complet
    "tool_selection_result": tool_selection_dict,  # Dict sérialisé
}
```

**Pourquoi un cache dans StreamingService ?**
- Ces valeurs ne sont présentes que dans le **premier chunk values** (après router_node)
- Les chunks suivants (planner, response) ne contiennent PAS ces valeurs
- Le cache permet de les **persister** à travers tous les chunks d'une même requête

---

### 2. Backend - Émission SSE (StreamingService)

**Fichier**: `apps/api/src/domains/agents/services/streaming/service.py`

**Responsabilités**:
- Intercepte chaque chunk "values" de LangGraph
- Cache `query_intelligence` et `tool_selection_result` au premier passage
- Émet `debug_metrics` SSE chunk **à chaque chunk values** (si DEBUG=true)

**Code clé** (_process_values_chunk, lignes 538-546):
```python
# Cache query_intelligence for reuse across all chunks
query_intelligence = chunk.get("query_intelligence")
if query_intelligence is not None:
    self._cached_query_intelligence = query_intelligence
# Always use cached value (persists across all chunks after router_node)
query_intelligence = self._cached_query_intelligence
if query_intelligence is not None:
    debug_metrics = query_intelligence.to_debug_metrics()
    # ... enrichissement avec token_budget, planner_intelligence, tool_selection
    sse_chunks.append((ChatStreamChunk(type="debug_metrics", ...), ""))
```

**Fréquence d'émission**:
- `debug_metrics` est émis **plusieurs fois** par requête (à chaque chunk values)
- Cela garantit que le frontend reçoit TOUJOURS les métriques, même si connecté tard

**Instanciation**:
- `StreamingService` est créé **par requête** (api/service.py ligne 478)
- Le cache est donc **automatiquement réinitialisé** entre requêtes
- ❌ PAS besoin de clearing manuel dans `stream_sse_chunks()`

---

### 3. Frontend - Réception SSE (useChat.ts)

**Fichier**: `apps/web/src/hooks/useChat.ts`

**Responsabilités**:
- Reçoit le chunk SSE `debug_metrics`
- Dispatche action `DEBUG_METRICS` avec `messageId: assistantMessageId`
- Log console pour debugging (ligne 401-409)

**Code clé** (lignes 387-410):
```typescript
case 'debug_metrics':
  const debugMetricsData = chunk.metadata as DebugMetrics;
  if (debugMetricsData) {
    dispatch({
      type: 'DEBUG_METRICS',
      payload: {
        messageId: assistantMessageId,  // ⚠️ POINT CRITIQUE
        metrics: debugMetricsData,
      },
    });
    logger.debug('chat_debug_metrics', ...);  // Console log navigateur
  }
  break;
```

**⚠️ POINT CRITIQUE - assistantMessageId**:
- `assistantMessageId` est généré au **début** de `sendMessage()` (ligne 261)
- Toutes les actions utilisent ce même ID : `debug_metrics`, `router_decision`, `token`, `done`
- **SAUF** : HITL utilise un `messageId` différent venant du backend (ligne 578)

**Potentiel problème** :
- Si HITL survient, le message a un ID différent de `assistantMessageId`
- Les métriques sont stockées sous `assistantMessageId` mais le message a un autre ID
- ❓ À vérifier : Est-ce que les requêtes testées passent par HITL ?

---

### 4. Frontend - Stockage (chat-reducer.ts)

**Fichier**: `apps/web/src/reducers/chat-reducer.ts`

**Responsabilités**:
- Stocke les métriques dans un dictionnaire indexé par `messageId`
- Crée un **nouvel objet** à chaque ajout (React détecte le changement)

**Code clé** (lignes 424-433):
```typescript
case 'DEBUG_METRICS':
  return {
    ...state,
    debugMetrics: {
      ...state.debugMetrics,
      [action.payload.messageId]: action.payload.metrics,  // Nouvel objet
    },
  };
```

**Accumulation**:
- Le reducer **accumule** les métriques de tous les messages passés
- Exemple après 3 requêtes : `{ "msg1": {...}, "msg2": {...}, "msg3": {...} }`
- ❓ Est-ce voulu ? Ou devrait-on nettoyer les anciennes métriques ?

---

### 5. Frontend - Affichage (chat/page.tsx)

**Fichier**: `apps/web/src/app/[lng]/dashboard/chat/page.tsx`

**Responsabilités**:
- Sélectionne les métriques du **dernier message**
- Force re-render du DebugPanel via `key` prop

**Code clé** (lignes 51-65):
```typescript
// Sélectionne les métriques du dernier message
const latestDebugMetrics = useMemo(() => {
  if (!DEBUG_ENABLED) return null;
  const messageIds = Object.keys(debugMetrics);
  if (messageIds.length === 0) return null;
  const lastId = messageIds[messageIds.length - 1];  // ⚠️ POINT CRITIQUE
  return debugMetrics[lastId] || null;
}, [debugMetrics]);

// Génère key pour forcer re-render
const latestMetricsKey = useMemo(() => {
  if (!DEBUG_ENABLED || !latestDebugMetrics) return 'no-metrics';
  const messageIds = Object.keys(debugMetrics);
  return messageIds[messageIds.length - 1] || 'no-metrics';  // ⚠️ POINT CRITIQUE
}, [debugMetrics, latestDebugMetrics]);

<DebugPanel key={latestMetricsKey} metrics={latestDebugMetrics} />
```

**⚠️ POINT CRITIQUE - Ordre des clés**:
- `Object.keys(debugMetrics)` retourne les clés dans l'**ordre d'insertion** (ES2015+)
- `messageIds[messageIds.length - 1]` suppose que la dernière clé = dernier message
- **MAIS** : Si un message est ajouté APRÈS (reminder, HITL), la correspondance est cassée

**Exemple de bug potentiel** :
1. Requête 1 → message ID `msg1` → métriques stockées sous `msg1`
2. Requête 2 → message ID `msg2` → métriques stockées sous `msg2`
3. Un reminder arrive → message ID `reminder_123` (sans métriques)
4. `Object.keys(debugMetrics)` → `["msg1", "msg2"]` (pas "reminder_123")
5. `lastId` → `"msg2"` → Affiche les métriques de msg2 (correct)

**Mais si** :
1. Requête 1 avec HITL → message ID `hitl_abc` (différent de `assistantMessageId`)
2. Métriques stockées sous `assistantMessageId_xyz`
3. `lastId` → `assistantMessageId_xyz`
4. Mais le dernier message dans `messages` a l'ID `hitl_abc`
5. **Mismatch** : on affiche les métriques de la mauvaise requête

---

### 6. Frontend - Composant (DebugPanel.tsx)

**Fichier**: `apps/web/src/components/debug/DebugPanel.tsx`

**Responsabilités**:
- Affiche les métriques reçues
- Log console pour debugging (lignes 523-536)

**Code clé** (lignes 523-536):
```typescript
React.useEffect(() => {
  console.log('[DebugPanel] Domain Selection:', {
    all_scores: domain_selection.all_scores,
    all_scores_keys: domain_selection.all_scores ? Object.keys(...) : [],
    all_scores_length: domain_selection.all_scores ? Object.keys(...).length : 0,
  });
  if (tool_selection) {
    console.log('[DebugPanel] Tool Selection:', { ... });
  }
}, [domain_selection, tool_selection]);
```

**Debug** :
- Ces logs apparaissent dans la **console du navigateur**
- Ils montrent si les données arrivent au composant
- ⚠️ Ces logs sont TEMPORAIRES (pour debug) - à enlever en prod

---

## Points de défaillance identifiés

### ❌ 1. Mismatch messageId (HITL)
**Symptôme** : Métriques stockées sous un ID différent du message réel

**Cause** :
- `assistantMessageId` généré au début
- HITL utilise un `messageId` différent du backend
- Métriques stockées sous `assistantMessageId`, message créé avec HITL `messageId`

**Test** :
```typescript
// Dans useChat, après dispatch DEBUG_METRICS (ligne 409)
logger.debug('chat_debug_metrics_id', {
  assistantMessageId,
  messageIds: Object.keys(state.messages.map(m => m.id)),
});
```

**Solution potentielle** :
- Stocker aussi `assistantMessageId` dans le state au début
- Utiliser ce même ID pour HITL (au lieu du backend messageId)
- Ou mapper les métriques au message via autre moyen (timestamp ? index ?)

---

### ❌ 2. Ordre des clés dans debugMetrics
**Symptôme** : Affichage des métriques d'un message précédent

**Cause** :
- `Object.keys(debugMetrics)[length-1]` suppose ordre = chronologie
- Si reminders/HITL sont intercalés, l'ordre peut ne pas correspondre

**Test** :
```typescript
// Dans chat/page.tsx, ligne 56 (après messageIds)
console.log('[DebugPanel] messageIds order:', {
  messageIds,
  lastId: messageIds[messageIds.length - 1],
  actualLastMessage: messages[messages.length - 1]?.id,
  match: messageIds[messageIds.length - 1] === messages[messages.length - 1]?.id,
});
```

**Solution potentielle** :
- Au lieu de `messageIds[length-1]`, chercher les métriques du dernier message ASSISTANT :
```typescript
const lastAssistantMsg = [...messages].reverse().find(m => m.role === 'assistant');
const latestDebugMetrics = lastAssistantMsg ? debugMetrics[lastAssistantMsg.id] : null;
```

---

### ❌ 3. React ne détecte pas le changement
**Symptôme** : Même avec `key` différent, le composant ne re-render pas

**Cause possible** :
- `useMemo` ne se re-déclenche pas malgré dépendances changées
- Le `key` reste "no-metrics" si `latestDebugMetrics` est null
- React batching les updates

**Test** :
```typescript
// Dans chat/page.tsx, ligne 65
console.log('[DebugPanel] Key changed:', {
  key: latestMetricsKey,
  metricsAvailable: !!latestDebugMetrics,
  debugMetricsKeys: Object.keys(debugMetrics),
});
```

**Solution potentielle** :
- Utiliser `key={Date.now()}` temporairement pour forcer re-render à chaque render
- Ou utiliser un compteur incrémental au lieu de messageId

---

## Plan d'action de debug

### Étape 1 : Vérifier la réception SSE

**Console navigateur** - Chercher log `chat_debug_metrics` (useChat.ts ligne 401) :
```
chat_debug_metrics { route_to: "planner", domains: ["calendar"], intent: "ACTION" }
```

**✅ Si présent** : Le backend émet et le frontend reçoit → Problème dans useChat/reducer/page
**❌ Si absent** : Le backend n'émet pas ou SSE ne transmet pas → Problème backend/réseau

---

### Étape 2 : Vérifier le stockage reducer

**Console navigateur** - Ajouter log dans reducer (chat-reducer.ts ligne 432) :
```typescript
case 'DEBUG_METRICS':
  console.log('[Reducer] Storing debug metrics:', {
    messageId: action.payload.messageId,
    keys: Object.keys({ ...state.debugMetrics, [action.payload.messageId]: ... }),
    domainCount: action.payload.metrics.domain_selection?.all_scores ?
      Object.keys(action.payload.metrics.domain_selection.all_scores).length : 0,
  });
  return { ...state, debugMetrics: { ... } };
```

**✅ Si log présent avec domainCount > 0** : Les métriques sont stockées → Problème dans page.tsx
**❌ Si log absent ou domainCount = 0** : Les métriques ne sont pas stockées/vides

---

### Étape 3 : Vérifier la sélection des métriques

**Console navigateur** - Les logs TEMPORAIRES existent déjà (DebugPanel.tsx ligne 523) :
```
[DebugPanel] Domain Selection: { all_scores: {...}, all_scores_keys: [...], all_scores_length: 10 }
```

**✅ Si présent avec all_scores_length > 0** : Les données arrivent au composant → Problème de rendering CSS/UI
**❌ Si absent ou all_scores_length = 0** : La sélection dans page.tsx échoue

---

### Étape 4 : Vérifier le messageId matching

**Console navigateur** - Ajouter log dans page.tsx (après ligne 56) :
```typescript
console.log('[DebugPanel Selection]', {
  debugMetricsKeys: Object.keys(debugMetrics),
  lastMetricId: messageIds[messageIds.length - 1],
  lastMessageId: messages[messages.length - 1]?.id,
  match: messageIds[messageIds.length - 1] === messages[messages.length - 1]?.id,
  metricsFound: !!latestDebugMetrics,
});
```

**✅ Si match = true** : Les IDs correspondent → Pas de problème de mismatch
**❌ Si match = false** : Mismatch entre dernier message et dernières métriques

---

## Consolidation du code

### Corrections appliquées

1. ✅ **Enlever le cache clearing inutile** (streaming/service.py lignes 197-200)
   - Raison : StreamingService instancié par requête, pas besoin de clearing manuel

2. ✅ **Ajouter `tool_selection_result` au schema MessagesState** (models.py ligne 325)
   - Raison : LangGraph ne streame que les champs déclarés dans TypedDict

---

## Unified LLM Tracking (v3.3)

### Overview

As of v3.3, the debug panel tracks ALL LLM call types in a unified way:
- **Chat completions** (router, planner, response, sub-agents) — via `TokenTrackingCallback`
- **Embedding calls** (journal context, memory search, RAG retrieval) — via `persist_embedding_tokens()` recording into the conversation's `TrackingContext`
- **TTS** (voice synthesis) — via direct `tracker.record_node_tokens()` call

### Architecture: Embedding Token Tracking

Previously, embedding tokens were persisted via a separate `TrackingContext` in `persist_embedding_tokens()`, making them invisible in the debug panel.

v3.3 fixes this by using the `current_tracker` ContextVar (from `src/core/context.py`):

```
TrackedOpenAIEmbeddings.aembed_query()
  → persist_embedding_tokens()
    → current_tracker.get()  ← conversation's TrackingContext
    → conv_tracker.record_node_tokens(call_type="embedding")
    → Visible in debug panel via get_llm_calls_breakdown()
```

Fallback: when no conversation tracker exists (background operations), the existing standalone `TrackingContext` path is preserved.

### New Fields

- `TokenUsageRecord.call_type` — `"chat"` (default) or `"embedding"`
- `TokenUsageRecord.sequence` — monotonic counter for chronological ordering

### New Debug Panel Section: LLM Pipeline

The `llm_pipeline` section in `debug_metrics` provides a chronological reconciliation of ALL LLM calls, sorted by `sequence`. Built in `StreamingService._add_debug_metrics_sections()` from the `llm_calls` data.

Frontend component: `LLMPipelineSection.tsx`

### Impact on Existing Sections

- **LLM Calls**: Now shows embedding calls with `EMB` badge (teal color)
- **Request Lifecycle**: Embedding nodes appear automatically (uses `getNodeColor()`)
- **Token Budget**: Totals automatically include embedding tokens (cascade via `llm_summary`)
- **LLM Summary**: Aggregates all call types (chat + embedding)

3. ✅ **Fixer l'initialization SemanticToolSelector** (agent_registry.py lignes 1414-1432)
   - Raison : Utiliser les nouveaux paramètres V3 calibrés au lieu des anciens

4. ✅ **Ajouter V3_TOOL_* variables dans .env** (.env, .env.example, .env.prod.example)
   - Raison : Variables référencées dans le code mais non définies

### Refactorings à considérer (NON APPLIQUÉS - pour discussion)

1. **Simplifier la sélection des métriques** (chat/page.tsx) :
   ```typescript
   // Au lieu de Object.keys(debugMetrics)[length-1]
   const lastAssistantMsg = [...messages].reverse().find(m => m.role === 'assistant');
   const latestDebugMetrics = lastAssistantMsg?.id ? debugMetrics[lastAssistantMsg.id] : null;
   ```

2. **Nettoyer les anciennes métriques** (chat-reducer.ts) :
   ```typescript
   case 'DEBUG_METRICS':
     // Garder seulement les N dernières métriques pour éviter memory leak
     const existingKeys = Object.keys(state.debugMetrics);
     const recentKeys = existingKeys.slice(-10); // Garder 10 dernières
     const recentMetrics = Object.fromEntries(
       recentKeys.map(k => [k, state.debugMetrics[k]])
     );
     return {
       ...state,
       debugMetrics: {
         ...recentMetrics,
         [action.payload.messageId]: action.payload.metrics,
       },
     };
   ```

3. **Unifier les messageIds** (useChat.ts) :
   - Utiliser le même `assistantMessageId` pour HITL au lieu du backend messageId
   - Ou créer un mapping explicite entre backend IDs et frontend IDs

---

## État actuel du code

### v1.8.1 — Supplementary Debug Metrics (`debug_metrics_update`)

**Contexte** : Certaines données de debug ne sont disponibles qu'après la fin des tâches en arrière-plan (ex. journal extraction). Un nouveau type de chunk SSE `debug_metrics_update` permet de les envoyer après coup.

**Flow** :
```
response_node → fire-and-forget extraction_service → _store_extraction_debug(run_id)
    │
    ▼
streaming_service (après await_run_id_tasks)
    │
    ├── pop_extraction_debug(run_id) → données d'extraction
    │
    ▼
ChatStreamChunk(type="debug_metrics_update", metadata={"journal_extraction": {...}})
    │
    ▼
Frontend: handleDebugMetricsUpdate() → dispatch({ type: 'DEBUG_METRICS_UPDATE', payload: { metrics } })
    │
    ▼
Reducer: merge supplementary metrics into currentDebugMetrics + latest debugMetricsHistory entry
```

**Reducer `DEBUG_METRICS_UPDATE`** :
```typescript
case 'DEBUG_METRICS_UPDATE': {
  // Merge supplementary metrics into current + latest history
  const update = action.payload.metrics;
  const updatedCurrent = state.currentDebugMetrics
    ? { ...state.currentDebugMetrics, ...update }
    : null;
  // Also update the most recent history entry (index 0)
  const updatedHistory = state.debugMetricsHistory.length > 0
    ? [{ ...history[0], metrics: { ...history[0].metrics, ...update } }, ...rest]
    : [];
  return { ...state, currentDebugMetrics: updatedCurrent, debugMetricsHistory: updatedHistory };
}
```

**Points clés** :
- `debug_metrics_update` est émis UNE SEULE FOIS par requête (après les tâches en arrière-plan)
- Il est distinct de `debug_metrics` (émis à chaque chunk values)
- Le frontend merge les données supplémentaires dans l'état existant (pas de remplacement)
- Le registre d'extraction (`_extraction_debug_results`) a un TTL de 5 minutes pour éviter les fuites mémoire

---

### ✅ Ce qui fonctionne

1. **Backend émet debug_metrics** (logs montrent `debug_metrics_emitted`)
2. **Backend émet debug_metrics_update** pour les données post-background (journal extraction)
3. **Frontend dispatch DEBUG_METRICS** (reducer stocke les données)
4. **Frontend dispatch DEBUG_METRICS_UPDATE** (reducer merge les données supplémentaires)
5. **Cache StreamingService** fonctionne correctement (persiste dans une requête)
6. **Tool selector** initialisé avec bons paramètres
7. **MessagesState schema** inclut tool_selection_result

### ⚠️ Ce qui est incertain

1. **Correspondance messageIds** : HITL peut créer un mismatch
2. **Ordre des clés** dans debugMetrics : Fiable mais fragile
3. **React re-render** : Le `key` prop devrait fonctionner, mais à vérifier

### ❌ Ce qui doit être debuggé

**Méthode** : Exécuter le plan d'action ci-dessus (4 étapes)
**Priorité** : Étape 1 d'abord (vérifier réception SSE)
**Output attendu** : Logs console montrant où le flow échoue

---

## Recommandations

1. **Immédiat** : Exécuter le plan de debug (étapes 1-4) pour identifier la cause exacte
2. **Court terme** : Appliquer le fix ciblé une fois la cause identifiée
3. **Moyen terme** : Simplifier la sélection des métriques (refactoring 1)
4. **Long terme** : Nettoyer les anciennes métriques (refactoring 2)

**Principe** : Un fix ciblé vaut mieux que 5 correctifs superposés.
