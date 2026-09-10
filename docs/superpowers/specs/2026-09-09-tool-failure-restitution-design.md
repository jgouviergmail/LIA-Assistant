# Restitution honnête des échecs d'outils — spécification

**Date** : 2026-09-09 · **Statut** : validé par le propriétaire (sémantique binaire + `failed_steps`, deux PR, gardes G1/G2) · **Plans** : `../plans/2026-09-09-tool-failure-restitution-pr1.md` (lots A, B, C, G1, G2) et `../plans/2026-09-09-tool-failure-restitution-pr2.md` (lots D, E).

## 1. Le fait déclencheur, et ce qu'il a révélé

Production, 2026-09-09 09:06 UTC, tour `514706d6-1d91-4d5c-bca5-bddb405d1815` : trois `fetch_web_page_tool` vers lacentrale.fr répondent **403 en ~80 ms** (DataDome derrière CloudFront, interstitiel « Please enable JS », `geo.captcha-delivery.com`). Mesuré identique avec `httpx` et avec le Chromium du pool, depuis le Pi et depuis une IP résidentielle, avec l'UA `LIA/1.0` et avec un UA Chrome : **le site refuse toute lecture automatisée, rien chez nous ne l'explique**.

Ce que l'utilisateur a lu : « la tentative de récupération des pages a échoué (**statut inconnu**, probablement un délai ou une restriction d'accès) », suivi d'une grille générique de 2 571 caractères. Ce que le prompt de synthèse avait reçu, rejoué dans le conteneur de production : `'❓ plan_executor: Statut inconnu (failed)'`. Le message exact de l'outil — `HTTP error 403 fetching https://www.lacentrale.fr/…` (88 caractères, longueur confirmée par `summary_length: 88` dans les logs) — n'a jamais atteint le modèle.

Trois surfaces de preuve se contredisaient sur le même événement :

| Surface | Ce qu'elle disait |
|---|---|
| Registre des consultations (ADR-263, `agent_treatments`) | 3 × `failed`, 206–222 ms — **juste** |
| Prometheus `agent_tool_invocations_total{tool_name="web_fetch"}` sur 7 jours | `success="true"` = 4, aucune série `false` — **faux** |
| Réponse de LIA | « statut inconnu » — **faux** |

Et sur 30 jours de registre, `fetch_web_page_tool` compte **4 issues, toutes `failed`, zéro succès** — un trou que personne ne pouvait voir.

## 2. Les défauts, chacun prouvé

| # | Défaut | Preuve | Portée |
|---|---|---|---|
| D1 | Le mapper écrit `status="failed"` ; le formateur ne connaît que `success`/`connector_disabled`/`error` ; `failed` tombe dans le `else` « Statut inconnu » qui **ne lit jamais le champ `error`** | rejeu prod dans le conteneur | tout échec d'outil en mode pipeline |
| D2 | Plan **mixte** (rappel créé + fetch 403) : `status="failed"` dès qu'UN step échoue ⇒ la confirmation du rappel est perdue elle aussi | simulation H1b | tout plan multi-étapes partiellement échoué |
| D3 | Seul le **premier** échec survit (`first_error`) | simulation H5 | plans à N échecs |
| D4 | Garde D3 de `response_node` : docstring « failed seulement si TOUS les steps échouent », code « dès qu'un échoue » ⇒ skill non activé sur succès partiel | simulation H1b | skills + planner |
| D5 | `infer_conversation_outcome` lit des **attributs** sur des **dicts** (`hasattr(result, "status")` est faux pour un `model_dump()`) ⇒ tout plan, échoué ou non, est classé `success` ; son test unitaire utilise un faux objet à attributs qui contourne la frontière | simulation + lecture du test | `agent_success_rate_total`, `cost_per_successful_conversation_usd` |
| D6 | `track_tool_metrics` compte `success="true"` pour **tout retour sans exception**, y compris `UnifiedToolOutput.failure(...)` | Prometheus prod : 4 « succès » = 4 `failed` du registre | ~80 outils |
| D7 | Branches d'échec de `fetch_web_page_tool` sans log ; 401/403/429/5xx écrasés en `EXTERNAL_API_ERROR` ; **113 blocs sur 168** dans `tools/*.py` retournent un échec sans aucun log | balayage AST | tous les outils |
| D8 | Replanner : permanence décidée par **sous-chaînes du message** (« forbidden », « unauthorized ») alors que `error_code` est dans `completed_steps` ; « HTTP error 403 » ⇒ « transient » ; 62 sites de classification par message dans le code | log prod `replan_decision_made` + grep | conseil faux (advisory, ADR-128) |
| D9 | Le TODO D4 de l'orchestrateur repose sur une prémisse fausse : « the failed-step results flow to response_node, which surfaces the failure » | code | doctrine |
| D10 | i18n : « Statut inconnu », « Erreur inconnue », « Service non activé » en français inline ; `_()` du replanner sans langue | code | règle CLAUDE.md |
| D11 | Code mort : `create_pending_agent_result` (tests seulement), branche `tool_results` du response node (aucun producteur), `should_execute_agent` (tests seulement), valeurs `pending`/`failed`/`connector_disabled` du `Literal` (aucun producteur pour les deux dernières hors le mapper) | grep | maintenance |
| D12 | Navigateur : `session.navigate` **ne lit jamais** `response.status` ⇒ un interstitiel anti-bot est rendu comme une page réussie, et `browser_actions_total{navigate,success}` compte un succès | mesure prod : 403, `annonce visible: False` | `browser_navigate_tool` |
| D13 | Trace UI : `Literal["started","completed","failed"]` déclaré, **seul `started` émis** ; le type front n'a pas de statut ⇒ un step échoué s'affiche comme les autres | code | chat, mobile inclus |
| D14 | `docs/technical/RESPONSE.md` : copie périmée du code | lecture | docs |
| **D15** | **Le mécanisme d'honnêteté existe déjà et est aveugle** : `runtime_failures_directive` est alimentée par `extract_failures_from_steps`, qui lit `step["status"] == "error"` et `result.error.code` — **aucun écrivain de `completed_steps` n'écrit `status`** ; l'executor écrit `{"success": False, "error", "error_code"}`. Son test encode la forme fictive. En prod `DIAGNOSTICS_ENABLED=true` : le bloc a tourné et n'a rien trouvé. Et la moitié « échecs » est conditionnée au drapeau diagnostics, contrairement à la doctrine ADR-248 | code + valeur prod du drapeau | même classe que D1, sur le correctif lui-même |
| D16 | Agrégat FOR_EACH : `success` fusionne en « dernier gagne » ⇒ un item échoué au milieu est invisible | `_aggregate_for_each_results` | plans FOR_EACH |

Ce qui n'est **pas** un défaut (contre-vérifié) : ReAct transmet `result.message` au modèle ; le registre ADR-263 est juste ; les décorateurs de nœuds sont justes (un nœud lève) ; `EffectStatus` a tous ses membres écrits et lus ; les deux tours « Remember this » sans réponse ont été **annulés par le bouton Stop** (`POST /runs/active/cancel` à +2 s, seule origine possible) — conséquence produit : aucune mémoire créée, extraction planifiée par le response node ; hors périmètre, ticket séparé.

## 3. Décisions de conception

### 3.1 Un vocabulaire, deux valeurs, un lecteur exhaustif
`AgentResultStatus(StrEnum)` = `SUCCESS`, `ERROR` dans `domains/agents/constants.py`. Le `Literal` d'`AgentResult.status` est **prouvé égal** aux valeurs de l'enum par la garde G1. `failed`, `pending`, `connector_disabled` disparaissent : le premier n'était produit que par le mapper, les deux autres par personne. `should_execute_agent` (seul lecteur de `connector_disabled`, aucun appelant hors tests) est supprimé avec ses tests.

### 3.2 Sémantique de l'agrégat : binaire, et `failed_steps` toujours présent
`ERROR` seulement quand **tous** les steps ont échoué ; `SUCCESS` sinon (au moins un step a produit). `AgentResult.failed_steps: list[FailedStep]` (`step_index`, `tool_name`, `error`, `error_code`) est rempli depuis les steps échoués dans les deux cas. C'est ce champ, pas le statut, qui porte la vérité du partiel — et la garde G1 teste chaque lecteur avec un cas partiel.

### 3.3 Chaque fait a UN canal vers le prompt
- **Échecs de steps pipeline** → `runtime_failures_directive` (`diagnostics/failure_context.py`), qui lit `completed_steps` sous la forme que l'executor écrit (`FIELD_SUCCESS`, `FIELD_ERROR`, `FIELD_ERROR_CODE`, constantes partagées écrivain/lecteur), liste **tous** les échecs (borne `MAX_FAILURES`, **total exact** publié), nomme l'outil, et n'est **plus conditionnée au drapeau diagnostics** — seule la moitié « dégradations de plateforme » l'est encore (elle a besoin de l'advisor).
- **Erreurs au niveau agent** (agents de domaine `base_agent_builder`, ReAct, `runtime_helpers`) → le formateur `format_agent_results_for_prompt`, branche `ERROR`, ligne localisée `APIMessages.agent_error_line`.
- **Règle de démarcation structurelle** : une entrée `ERROR` qui porte `failed_steps` est un agrégat de plan ⇒ le formateur n'émet rien pour elle (la directive s'en charge) ; sans `failed_steps`, c'est une erreur d'agent ⇒ ligne. Un statut hors vocabulaire ⇒ `logger.warning("agent_result_status_unknown")`, jamais une phrase inventée.
- Le prompt versionné `runtime_failures_directive.txt` gagne les codes `ToolErrorCode` (`FORBIDDEN`/`UNAUTHORIZED` : le site ou le service refuse l'accès automatisé — ne pas réessayer, demander le contenu ou l'autorisation ; `NOT_FOUND` ; `EXTERNAL_API_ERROR` transitoire ; `INVALID_INPUT`). Aucune valeur numérique en prose.

### 3.4 Lecteurs alignés
`_plan_execution_failed` lit `AgentResultStatus.ERROR` (sa docstring devient vraie). `infer_conversation_outcome` lit des **dicts** (forme réelle) : `ERROR` ⇒ échec, `SUCCESS` + `failed_steps` ⇒ `partial_success`. Ses tests utilisent la sortie réelle du mapper, jamais un faux objet.

### 3.5 FOR_EACH
L'agrégat porte `_for_each_aggregate: True` (marqueur structurel), `success = any(item succeeded)`, `error` = « k/n items failed: <premier> ». La directive liste les **items** échoués (entrées `step_x_item_i` de `completed_steps`) et saute les agrégats marqués — pas de double compte.

### 3.6 Observabilité honnête
`track_tool_metrics` décide le succès par `core/tool_outcome.explicit_success` (le prédicat du registre, déplacé dans `core/` pour ne pas inverser la couche infrastructure→domaines ; `effects/outcome.py` le réexporte) : `success="false"` + `logger.warning("tool_returned_failure", tool_name, error_code, duration_ms)` — jamais l'URL ni les paramètres. Un panneau Grafana 07 « Tool failures (returned) » avec `or vector(0)` et `"noValue": "0"`. `fetch_web_page_tool` : taxonomie **structurelle** `http_status_to_error_code` (401→`UNAUTHORIZED`, 403→`FORBIDDEN`, 404/410→`NOT_FOUND`, 429→`RATE_LIMIT_EXCEEDED`, 408/5xx→`EXTERNAL_API_ERROR`, autres 4xx→`INVALID_INPUT`), détection anti-bot par **en-têtes** (`x-datadome`, `cf-mitigated: challenge`) — jamais un contournement —, logs `web_fetch_failed` avec le **domaine**, pas l'URL.

### 3.7 Replanner
`StepAnalysis.error_code` lu depuis `completed_steps` ; permanence par code (final quand il existe), marqueurs de message seulement sans code ; `_()` avec la langue de l'utilisateur ; message d'abandon avec total exact. Reste advisory (ADR-128).

### 3.8 Gardes
- **G1 — parité de vocabulaire** (`test_agent_status_vocabulary_guard.py`) : Literal == enum ; aucune comparaison de `status` à `"failed"`/`"pending"`/`"connector_disabled"`/`"failure"` sous `domains/agents` (liste d'exemptions shrink-only, avec raison) ; chaque membre a un producteur et un consommateur ; le formateur ne produit jamais « inconnu » pour un membre.
- **G2 — classification structurelle** (`test_no_message_substring_classification_guard.py`) : aucune nouvelle comparaison `in str(e)` / `.lower() in` sur un message d'exception sous `tools/` et `orchestration/` ; baseline JSON par fichier, shrink-only, mesurée à l'implémentation (62 sites aujourd'hui dans `domains/`+`infrastructure/`, 7 dans `browser_tools.py`).

### 3.9 Trace (PR 2, lot D)
`_extract_pipeline_tool_steps` lit déjà `accumulated_state` à la fin de `task_orchestrator` : il y lit `completed_steps` et émet `status="completed"|"failed"` avec `failed_count`/`total_count` — aucun nouveau hook. ReAct : issue lue sur les `ToolMessage`. `TraceCapture` **met à jour** l'entrée déjà vue (dédup par `i18n_key` conservée) avec `outcome`. Front : `ExecutionTraceStep.outcome?: 'failed'`, glyphe ✗ + nom accessible traduit (6 locales), aucun changement de largeur (mobile), hydratation rétro-compatible (trace sans `outcome` ⇒ rendu inchangé).

### 3.10 Navigateur (PR 2, lot E)
`session.navigate` lit `response.status` ; ≥ 400 ⇒ `BrowserHttpError(status, url, anti_bot)` ⇒ `browser_navigate_tool` classe par `http_status_to_error_code` (une implémentation partagée avec le fetch), `browser_actions_total{navigate,"http_error"}`. Les sept classifications par message de `browser_tools.py` deviennent des exceptions typées (`infrastructure/browser/errors.py`).

## 4. Invariants (à tester, pas à promettre)
1. Un statut d'agent est un membre de `AgentResultStatus`, et chaque membre est produit et lu.
2. Un step échoué atteint le prompt exactement une fois, par la directive, avec son code et son message, borné avec total exact.
3. Un succès d'action atteint le prompt même quand un autre step a échoué.
4. Un `failure()` retourné est compté `success="false"` et journalisé sans PII.
5. Le lecteur d'un dict lit un dict (jamais `hasattr` sur un `model_dump()`).
6. Aucun nombre réglable dans un prompt ; aucune chaîne utilisateur inline en Python.

## 5. Coût, quotas, registres, responsive
Aucun appel LLM ajouté, aucun retry ajouté, quotas inchangés ; la directive existait déjà (zéro jeton sur un tour propre) : +≤ ~200 jetons sur les seuls tours échoués, réponse plus courte en pratique. Registres ADR-263 inchangés (ils sont la référence). Aucune migration, aucun schéma. Lot D : un événement SSE par step outil, un glyphe de 1 caractère.

## 6. Hors périmètre (tickets)
Mémoire perdue quand l'utilisateur clique Stop avant la synthèse ; `data_prefix` inline du response node ; échec `unified_web_search_tool` du 07/09 ; les 55 autres sites de classification par message hors `browser_tools.py` (la baseline G2 les tient).
