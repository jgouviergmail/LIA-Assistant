# ADR-133 : Coulisses par message — la trace d'exécution survit à la réponse (Lot 2 P2-V1)

**Statut** : Accepté — implémenté. V1 frontend session-only (preuve runtime dev) ;
V2 persistance `message_metadata` livrée 2026-07-22 (backend + hydratation, preuve
runtime dev + navigateur — voir Périmètre).
**Date** : 2026-07-18
**Contexte produit** : P2 du chantier « UX cœur conversationnel » (specs 2026-07-18), suit [ADR-132](ADR-132-HITL-Approval-Cards.md).

## Contexte

Pendant l'exécution, le chat affiche les étapes agentiques (`execution_step` :
router → planner → validator → outils…) et le raisonnement en direct (💭)
dans une bulle de progression. **Ces éléments sont effacés en bloc au premier
token de réponse** (`handleToken` vide `executionStepsRef`/`reasoningBufRef`) —
comportement documenté comme volontaire (« the whole block is ephemeral »,
`ReasoningScroll.tsx`). Après coup, il ne reste que tokens/coût.

Conséquence : l'utilisateur non-admin n'a **aucun moyen** de savoir ce que LIA
a réellement fait — quels outils, combien d'étapes, quelle durée — alors que
l'éthique produit affiche déjà le coût au centime et que la landing vend la
visibilité des coulisses. Le seul substitut (panneau debug) est admin-only et
desktop-only.

## Décision

Renverser l'éphémère : **capturer la trace et l'attacher au message** au lieu
de la détruire.

- **Accumulateurs parallèles flip-survivants** : deux refs de handler
  (`traceStepsRef`, `traceReasoningRef`) accumulent en parallèle des refs
  éphémères existantes mais **ne sont PAS vidés au flip progress→answer**. Ils
  vivent du début du tour (`router_decision` / nouvel envoi les ré-initialisent)
  jusqu'au `done`. C'est le mécanisme précis qui fait survivre le record.
- **Steps structurés, pas des strings** : `{ emoji, label, category }` où le
  label réutilise les mêmes traductions `execution.steps.<i18n_key>` que la
  bulle live (déjà i18n ×6), donc la trace conservée correspond à ce que
  l'utilisateur a vu. `category` (system/agent/tool/context) vient du metadata.
- **Attache au `done`** : `TRACE_ATTACH` attache `{ steps, reasoning,
  durationMs }` au message (durée depuis le `done` metadata). No-op quand aucun
  step n'a été capturé (une réponse pure-conversation n'affiche pas de
  disclosure vide). Fonctionne dans les deux modes : `content_replacement`
  (ReAct/HTML) crée le message sous le même id sans toucher aux refs de trace.
- **Cap** : `MAX_TRACE_STEPS = 100` (la queue est conservée) — un FOR_EACH sur
  des centaines d'items ne fait pas gonfler l'état/DOM.
- **Rendu** : `ExecutionTraceDisclosure` — ligne repliée « ⚙ N étapes · X s »
  sous la bulle, dépliable vers les steps groupés par catégorie + le bloc
  raisonnement. Sans dépendance, monté paresseusement (le contenu déplié n'est
  dans le DOM que quand ouvert). i18n `chat.trace.*` ×6.

## Périmètre

- **V1 (livré)** : session-only. La trace vit dans l'état React du tour ; un
  rechargement d'historique ne la reconstruit pas.
- **V2 (livré 2026-07-22, chantier Quick Wins UX Lot 1)** : persistance dans
  `message_metadata` à l'archivage. Capture serveur miroir de l'accumulateur
  frontend — module `services/streaming/trace_capture.py` : reset + seed
  routeur sur `router_decision`, dédup par `i18n_key` par tour (une occurrence
  par clé, comme l'early-return `emittedStepKeysRef` du live), exclusion
  `reasoning`/`tool_error`, cap queue-conservée settings-driven
  (`EXECUTION_TRACE_PERSIST_MAX_STEPS`). Garde PII **structurelle** : la forme
  persistée est `{emoji, i18n_key, category}` — ni `detail` ni raisonnement
  n'ont de slot (la trace rechargée n'a pas de bloc 💭, assumé). Attache
  branch-free à l'archive (`with_persisted_trace`, à côté de
  `with_persisted_widgets`, clé `FIELD_EXECUTION_TRACE` + `duration_ms`).
  Hydratation : `lib/execution-trace-hydration.ts` re-résout les libellés
  depuis les clés (`toUiMessage`) — même type `ExecutionTrace`, même
  `ExecutionTraceDisclosure`, zéro changement de rendu. Tests : 16 unitaires
  capture/attache (reset, dédup, cap, PII), 10 hydratation (malformés,
  catégories, cap), round-trip des champs sérialisés couvert par les deux.
- **Différé** : éventuel step-par-outil en ReAct si la granularité par nœud
  s'avère trop grossière à l'usage.
- **Hors périmètre** : la trace sur une carte HITL (la carte est le focus
  visuel là ; le prochain `router_decision` de reprise ré-initialise les refs).

## Conséquences

- La confiance par la preuve, dans le produit et plus seulement le marketing ;
  et un outil de diagnostic quotidien (« pourquoi cette réponse a pris 40 s »)
  lisible dans la bulle au lieu de Grafana.
- **Renversement assumé** d'un choix explicite : l'éphémère devient
  persistant-au-message, globalement, sans réglage supplémentaire. Les tests
  qui vérifiaient l'effacement au flip restent valides (les refs *live* sont
  toujours vidées — seuls les refs *trace* survivent).
- Changement purement frontend : aucun contrat SSE modifié (les steps portaient
  déjà emoji/i18n_key/category), aucun backend touché.

## Preuves

- Reducer `TRACE_ATTACH` : 5 tests (attache par id, no-op id inconnu, remplace
  une trace antérieure, cap+queue, isolation des autres slices).
- Handlers : 2 tests prouvant le cœur — les steps survivent au flip (les refs
  live sont vidées, les refs trace non) et s'attachent au `done` ; skip quand
  aucun step (pure conversation).
- Composant : 6 tests (rien sans trace/steps, résumé replié, dépli, bloc
  raisonnement, durée optionnelle) — oracles rôle/nom.
- Suite frontend complète 1 357 verts ; tsc clean ; eslint clean ; ratchets
  a11y/react-hooks/CC tenus. Parité i18n ×6 vérifiée.
- Runtime dev : trace visible et dépliable après une requête météo réelle.
