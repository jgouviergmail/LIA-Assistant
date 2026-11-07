# Rationalisation JEV — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retirer les deux chaînes JEV sans lecteur (aperçus de collections, évaluateur d'initiative), déclarer les seuils JEV en un registre réglable depuis l'écran d'administration, écrire des statistiques durables par usage (jugements, issues, coût, accord des observateurs) et les afficher sur ce même écran, pour qu'un seuil se décide sur la distribution réelle et non sur un corpus.

**Architecture :** une porte unique (`infrastructure/llm/jev_runtime.py`) écrit la distribution des jugements et l'issue de chaque tentative ; les consommateurs ne lisent plus une constante mais le seuil résolu que `DecisionAttempt` transporte ; les seuils vivent dans `system_settings` (une clé JSON par usage), lus dans la même requête que les interrupteurs, figés dans l'instantané par opération. Les suppressions sont des lots indépendants, chacun avec sa migration qui efface les lignes des clés et créneaux retirés (une clé inconnue lue sans filtre lève `LookupError`, reproduit le 06/11).

**Tech Stack :** FastAPI, SQLAlchemy 2 + Alembic, Pydantic 2, Next.js 16 / React 19, react-i18next (6 langues), pytest, vitest, Playwright.

**Spec :** la section « Décisions » ci-dessous, arrêtée avec le propriétaire le 2026-11-06 après les mesures de la journée (relevé du 26 octobre : `docs/superpowers/qualification/jev-audit-2026-10-25/README.md` ; ADR à écrire au lot 0). Aucun code n'a été écrit avant ce plan.

## Décisions (spec)

1. **Les 8 aperçus de collections sont supprimés** (`filter_email`, `filter_event`, `filter_task`, `filter_file`, `filter_reminder`, `filter_ticket`, `filter_mcp`, `filter_document`). Qualité mesurée bonne (0 faux sur 122 éléments à 0,94), mais leur seul affichage, la fenêtre « Premiers résultats », a été masqué par le propriétaire le 2026-10-04 et `resultPreviews` n'est lu par aucun composant.
2. **L'évaluateur d'initiative post-exécution est supprimé** (nœud `initiative`, ADR-062/ADR-070 ; sa porte JEV `initiative_utility` ; les puces de relance et la ligne de motivation qu'il seul produit). Diagnostic du 06/11 : 0 acte, 0 suggestion, 0 puce sur 89 évaluations en 7 jours de production, pour 8,24 € par mois et jusqu'à 2,9 s par tour outillé ; l'évaluateur répond et refuse conformément à ses règles (inter-domaines seulement, adresse vérifiée, retenue par défaut). **La suggestion de routine (ADR-140), qui voyageait dans son créneau, est conservée et déplacée** ; sa refonte appartient au programme « habitudes », pas à celui-ci.
3. **Les usages qualifiés mais éteints restent** (compte rendu, radio, consultations ×2, exclusions et refus HITL, références personnelles, 4 observateurs) : le propriétaire les rallume lui-même. **Paramètres protégés** reste : garde qui ne peut qu'ajouter un refus.
4. **Les seuils deviennent des réglages** : un registre déclaratif (clé de question → nature du score, défaut, bornes, portée « chacun » ou « tous », option d'abstention), stocké dans `system_settings`, réglable depuis l'écran « Intégrations JEV », avec la mention « hors relevé qualifié » dès qu'une valeur s'écarte du défaut. Aucune valeur par défaut ne change dans ce plan (le seuil de priorité des e-mails à 0,50 ne gagne qu'un e-mail sur 134 au corpus indépendant : il reste réglable, pas modifié).
5. **Statistiques durables** par usage : distribution des jugements au centième (écrite par le runtime, indépendante du seuil), issues des tentatives et des consommateurs (« a conclu », « incertain », « repli », « échec »), volume, coût et latence (lus dans `token_usage_logs`), **accord des observateurs** (verdict JEV contre ce que l'extracteur a proposé). Jamais d'écriture pour une issue `disabled`.
6. **Nouveaux usages JEV** : (a) les observateurs comme tri avant extraction — d'abord en observation avec la mesure d'accord (lot D), puis, **si l'accord réel tient et après amendement de l'ADR-325**, un saut d'extraction (lot G, conditionnel) ; (b) « réponse attendue » sur les e-mails (lot F, après le lot D) ; (c) rien d'autre : la question compagne des rendez-vous et le tri des notifications proactives ne sont pas validés.
7. **Corrections** : la batterie `scripts/measure_extraction_selectivity.py` (import cassé, fenêtre rendue en entier alors que les extracteurs lisent quatre messages), les clés `usageHelp.email_classification` / `event_classification` absentes des 6 locales, le délai JEV plafonné à 5 s malgré la règle « la base d'abord ».

## Global Constraints

- CLAUDE.md s'applique en entier ; en particulier : jamais d'action git (le propriétaire commite), prompts en fichiers versionnés, `structlog` seul, exceptions centralisées, i18n sur 6 langues avec parité stricte, `AGENTS.md` régénéré (`task docs:sync-agents`), cartes vivantes (`task docs:maps`) à chaque ADR ou module de dos retiré.
- Toute valeur stockée dans `system_settings` tient dans `value String(255)` ; la clé est le NOM de l'enum `SystemSettingKey` (`native_enum=False`, longueur 50).
- Un changement de valeur PAR DÉFAUT d'un seuil de classification exige un rejeu natif payant (31 appels, ≈ 0,0074 €) et un budget validé ; ce plan n'en change aucun.
- Une migration de retrait efface les lignes `system_settings` et `llm_config_overrides` des clés et créneaux retirés AVANT que le code sans ces membres ne tourne (l'entrypoint applique les migrations au démarrage).
- Pas de nouveau coût de modèle sur un chemin de requête sans sa déclaration (`LLM_SPEND_ROADS`, `LLM_CHOKEPOINTS`) ; les statistiques JEV n'ouvrent aucune session sur la session de l'appelant.
- Deux sens du mot « initiative » coexistent : le nœud post-exécution (retiré ici) et le **registre des initiatives** de LIA (`effects/origin.py`, `InitiativeJournal.tsx`, origine `proactive`), qui ne bouge pas.

## Review Focus

1. Un administrateur saisit un seuil hors bornes, non numérique ou pour une clé inconnue → 422, aucune écriture (lot C, tâche C3).
2. Une instance dont la base garde une ligne `JEV_FILTER_EMAIL_ENABLED` ou un créneau `initiative` démarre un code qui ne connaît plus ces membres → la migration les efface avant le boot (lots A2, B2 ; test de rejeu de migration).
3. Un seuil de classification abaissé par l'écran ne doit pas laisser vivre une étiquette publiée sous l'ancien seuil → l'empreinte de politique hache les seuils EFFECTIFS (lot C, tâche C2).
4. Un onglet ouvert avant le déploiement reçoit encore `result_preview` ou `followups` dans un événement SSE → ignoré sans erreur (lots A3, B3 ; test de symétrie SSE).
5. Un travailleur tué pendant un vidage de statistiques perd au plus un intervalle de comptes, jamais une ligne partielle → UPSERT trié et atomique (lot D, tâche D1).

---

## Lot 0 — Décision écrite

### Task 0.1 : ADR-373 et amendement ADR-325

**Files:**
- Create: `docs/architecture/ADR-373-JEV-Retirements-Declared-Thresholds-And-Durable-Statistics.md`
- Modify: `docs/architecture/ADR-325-JEV-Bounded-Decisions-With-Hot-Switches-And-Accounted-Fallbacks.md` (un amendement daté 2026-11-06 : aperçus et porte d'initiative retirés, observateurs mesurés ; le saut d'extraction reste interdit jusqu'à un amendement du lot G)
- Modify: `docs/architecture/ADR_INDEX.md`, `apps/web/src/data/maps/` (entrée et mots de l'ADR en six langues), `docs/INDEX.md`

- [ ] **Step 1 :** écrire l'ADR en anglais : contexte (mesures du 06/11 : 0/89, 8,24 €, 2,9 s ; aperçus sans lecteur ; corpus indépendant), décision (les sept points ci-dessus), conséquences (coût, latence, ce qui est perdu : les puces de relance), alternatives rejetées (garder la porte JEV avec une autre question : ne discrimine pas, p 0,67-0,77 contre 0,41-0,81).
- [ ] **Step 2 :** ajouter l'entrée aux cartes vivantes dans les six langues, puis `task docs:maps`.
- [ ] **Step 3 :** `task release:sync-counts` puis `task lint:docs:preview` → 0 constat.

---

## Lot A — Suppression des 8 aperçus

### Task A.1 : chaîne de dos

**Files:**
- Delete: `apps/api/src/domains/agents/display/collection_preview.py`, `display/document_preview.py`, `display/jev_qualification.py`, `apps/api/src/domains/agents/prompts/v1/jev_collection_question.txt`, `prompts/v1/jev_document_question.txt`, `apps/api/scripts/measure_jev_collections.py`
- Delete tests : `tests/unit/domains/agents/display/test_collection_preview.py`, `test_jev_collection_time.py`, `test_jev_extra_collections.py`, `test_jev_qualification.py`, `tests/unit/infrastructure/llm/test_jev_collection_coverage.py` ; fixtures `tests/fixtures/jev_collection_cases.json`, `jev_extra_collection_cases.json`, `jev_extra_collection_holdout.json`
- Modify: `apps/api/src/domains/agents/nodes/response_node.py` (lignes ~95, ~2902-2943, ~3464 : création, `start`, `close` de `CollectionPreview` et `DocumentPreview`), `apps/api/src/domains/agents/services/streaming/service.py` (émission SSE `result_preview`), `apps/api/src/domains/agents/api/schemas.py:309`, `apps/api/src/infrastructure/llm/jev_debug_models.py` (`JevCollectionCoverage`, champ `collection_coverage`, action `preview`), `apps/api/src/infrastructure/llm/jev_debug_store.py` (paramètres propres aux collections), `apps/api/src/domains/agents/prompts/prompt_loader.py` (`PromptName`), `apps/api/scripts/jev_alignment/compare.py` (retirer la partie collections, garder le reste)
- Modify tests : `tests/integration/test_jev_debug.py`, `tests/agents/test_agent_service_stream_characterization.py`, `tests/unit/domains/agents/services/test_journey_timing.py`, `tests/unit/infrastructure/llm/test_jev_operation_snapshot.py`

**Interfaces :** rien n'est produit ; le nœud de réponse perd deux tâches parallèles et le flux SSE un type d'événement.

- [ ] **Step 1 :** écrire le test de garde `tests/unit/domains/agents/display/test_no_collection_preview_guard.py` : `grep` AST sur `apps/api/src` refusant tout import de `collection_preview`, `document_preview`, `jev_qualification` et tout littéral `"result_preview"`.
- [ ] **Step 2 :** le lancer → FAIL (les modules existent).
- [ ] **Step 3 :** supprimer les fichiers, retirer les appels du nœud de réponse et l'événement SSE ; `tests/unit/domains/agents/nodes/test_response_node*.py` ne doivent plus patcher `CollectionPreview`.
- [ ] **Step 4 :** `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents tests/unit/infrastructure/llm tests/agents -q` → vert ; la garde passe.

### Task A.2 : registre, interrupteurs, créneaux, migration

**Files:**
- Modify: `apps/api/src/domains/llm_config/jev_registry.py` (retirer 8 membres de `JevUsage` et leurs `JevUsageSpec`), `apps/api/src/domains/system_settings/models.py` (8 clés `JEV_FILTER_*_ENABLED`), `apps/api/src/domains/system_settings/registry.py` (8 `SETTING_SPECS`), `apps/api/src/domains/llm_config/constants.py` (8 créneaux `jev_filter_*` de `LLM_DEFAULTS`), `apps/api/src/infrastructure/llm/factory.py` (entrées `LLM_TYPES_REGISTRY`), `infrastructure/database/seeds/llm_config_seed.sql` (lignes des créneaux retirés, s'il y en a)
- Create: `apps/api/alembic/versions/<date>-<rev>_retire_collection_previews.py`

**Interfaces :**
- Produces: `JevUsage` sans les 8 membres ; `assert_jev_registry_complete()` reste vrai.

- [ ] **Step 1 :** test `tests/unit/domains/llm_config/test_jev_registry.py::test_retired_preview_usages_are_gone` : `assert not {u.value for u in JevUsage} & {"filter_email", …, "filter_document"}` et `assert_jev_registry_complete()` ne lève pas.
- [ ] **Step 2 :** le lancer → FAIL.
- [ ] **Step 3 :** retirer les membres, clés, specs et créneaux.
- [ ] **Step 4 :** écrire la migration : `upgrade()` = `DELETE FROM system_settings WHERE key IN (…8 noms…)` puis `DELETE FROM llm_config_overrides WHERE llm_type IN (…8 créneaux…)` ; `downgrade()` = ré-insère les 8 clés à `'false'` (les créneaux ne se recréent pas : ils reprennent `LLM_DEFAULTS` du code d'avant).
- [ ] **Step 5 :** `task db:migrate:replay-check` → vert ; `alembic heads` → une seule tête.
- [ ] **Step 6 :** `cd apps/api && .venv/Scripts/pytest tests/unit/domains/llm_config tests/unit/domains/system_settings -q` → vert.

### Task A.3 : chaîne web et locales

**Files:**
- Delete: `apps/web/src/lib/sse-handlers/result-preview.ts`, `apps/web/src/lib/sse-handlers/__tests__/result-preview.test.ts`, `apps/web/src/types/result-preview.ts`, `apps/web/e2e/smoke/chat-result-preview.spec.ts`
- Modify: `apps/web/src/lib/sse-handlers/index.ts`, `apps/web/src/lib/sse-handlers/__tests__/sse-symmetry.test.ts`, `apps/web/src/reducers/chat-reducer.ts` (champ `resultPreviews`, action associée), `apps/web/src/types/chat-state.ts:148,413`, `apps/web/src/types/chat.ts`, `apps/web/src/types/jev.ts` (union des usages), `apps/web/src/components/debug/components/sections/JevDebugSection.tsx` et son test (couverture de collection), `apps/web/e2e/smoke/settings-jev.spec.ts` (liste des usages), `apps/web/locales/{en,fr,de,es,it,zh}/translation.json` (clés `settings.admin.jev.usages.filter_*`, `settings.admin.jev.usageHelp.filter_*`, `settings.admin.llmConfig.types.jev_filter_*`)

- [ ] **Step 1 :** dans `sse-symmetry.test.ts`, ajouter l'assertion : un événement `result_preview` reçu est ignoré sans erreur ni changement d'état (Review Focus 4).
- [ ] **Step 2 :** `cd apps/web && pnpm vitest run src/lib/sse-handlers` → FAIL (le gestionnaire existe encore et mute l'état).
- [ ] **Step 3 :** supprimer le gestionnaire, le type, le champ du reducer et les clés des six locales.
- [ ] **Step 4 :** `task test:frontend` et `task lint:frontend` (parité i18n, tsc non incrémental) → vert.
- [ ] **Step 5 :** `task test:e2e` (hermétique) → vert.

### Task A.4 : documentation

**Files:**
- Modify: `docs/technical/JEV_INTEGRATION.md` (§ « Lot 2 : qualification des collections » → retiré, renvoi ADR-373), `docs/technical/JEV_SEMANTIC_QUALIFICATION.md` (si elle décrit les aperçus), `apps/web/src/data/maps/technical.json` (modules `display/*` revendiqués), `docs/INDEX.md`

- [ ] **Step 1 :** `task lint:docs:preview` → liste les liens et chemins morts.
- [ ] **Step 2 :** corriger, `task docs:maps`, relancer → 0 constat.

---

## Lot B — Suppression de l'évaluateur d'initiative

### Task B.1 : la suggestion de routine survit au nœud

**Files:**
- Create: `apps/api/src/domains/agents/nodes/recurrence_suggestion.py` (déplace `_resolve_recurrence_suggestion` de `nodes/initiative_recurrence.py`, sans son enveloppe de nœud)
- Rename: `prompts/v1/initiative_suggestion_directive.txt` → `prompts/v1/recurrence_suggestion_directive.txt` ; `STATE_KEY_INITIATIVE_SUGGESTION` → `STATE_KEY_RECURRENCE_SUGGESTION` (`core/constants.py`), clé d'état `initiative_suggestion` → `recurrence_suggestion` (`domains/agents/models.py:560,784`)
- Modify: `apps/api/src/domains/agents/nodes/response_node.py` (là où il lit la suggestion : appelle `resolve_recurrence_suggestion(state, config)` et rend la directive), `nodes/router_node_v3.py` (remise à zéro par tour), `prompts/prompt_loader.py` (`PromptName`), `nodes/post_response_extractions.py:516` (commentaire)

**Interfaces :**
- Produces: `async def resolve_recurrence_suggestion(state: MessagesState, config: RunnableConfig) -> str | None` dans `nodes/recurrence_suggestion.py` ; même texte, même garde `recurrence_evaluation_skipped_total`.

- [ ] **Step 1 :** adapter `tests/unit/domains/agents/nodes/test_recurrence_suggestion_wiring.py` au nouveau module ; ajouter `test_response_node_renders_recurrence_directive_without_initiative_node` (état avec suggestion → la directive est dans le prompt rendu).
- [ ] **Step 2 :** lancer → FAIL (module absent).
- [ ] **Step 3 :** créer le module, brancher le nœud de réponse, renommer la clé et la directive.
- [ ] **Step 4 :** `pytest tests/unit/domains/agents/nodes -q -k "recurrence or response_node"` → vert ; `test_prompt_placeholders_are_produced.py` vert.

### Task B.2 : le nœud, sa porte JEV, ses réglages, ses créneaux

**Files:**
- Delete: `nodes/initiative_node.py`, `nodes/initiative_recurrence.py`, `nodes/initiative_plan.py`, `nodes/initiative_schemas.py`, `nodes/initiative_semantic_bridges.py`, `nodes/jev_initiative.py`, `nodes/jev_initiative_context.py`, `nodes/jev_initiative_evidence.py`, `prompts/v1/initiative_prompt.txt`, `prompts/v1/jev_initiative_question.txt`
- Modify: `domains/agents/graph.py:71,82,371-372,672-718` (nœud et arêtes), `nodes/routing.py:698-841,1038-1060` (`route_from_initiative`, retours `"initiative"` → `"response"`), `domains/agents/models.py:555-561,781-785` (clés `initiative_iteration`, `initiative_results`, `initiative_skipped_reason`, `initiative_followups`), `core/config/agents.py:3126-3182` (`initiative_enabled`, `initiative_max_iterations`, `initiative_max_actions`, `initiative_react_enabled` ; fusion de `response_context_prefetch_at_router_enabled` dans `response_context_prefetch_enabled`), `core/constants.py` (défauts `INITIATIVE_*`, `STATE_KEY_INITIATIVE_*`, `INITIATIVE_MEMORY_*`), `.env.example`, `.env.prod.example`, `.env.demo-instance.example`, `.env.demo-instance.prod.example` et les deux `.env` vivants du démonstrateur (lignes `INITIATIVE_*`, `RESPONSE_CONTEXT_PREFETCH_AT_ROUTER_ENABLED` ; `.env.min.prod` n'en porte aucune), `nodes/router_node_v3.py:188-194` (le préchargement devient inconditionnel sous `response_context_prefetch_enabled`), `services/response_context.py:10` (docstring), `infrastructure/llm/spend_roads.py` (route du module), `domains/llm_config/constants.py` (créneaux `initiative` et `jev_initiative_utility`), `infrastructure/llm/factory.py` (`LLM_TYPES_REGISTRY`), `domains/llm_config/jev_registry.py` (`INITIATIVE_UTILITY`), `domains/system_settings/{models,registry}.py` (`JEV_INITIATIVE_UTILITY_ENABLED`), `infrastructure/database/seeds/llm_config_seed.sql:38`, `domains/agents/registry/catalogue.py:736,1256-1290` (champ `initiative_eligible` et `is_initiative_eligible`), les ~130 manifestes qui déclarent `initiative_eligible=` (liste par `grep -rl initiative_eligible apps/api/src`), `domains/agents/registry/domain_taxonomy.py` et `semantic/type_registry.py` (ponts sémantiques du nœud), `services/turn_catalogue.py:5`, `services/planner_capability_filter.py:11`, `orchestration/mappers.py`, `api/service.py` (section initiative du panneau debug), `infrastructure/startup/agents.py:86` (commentaire), `infrastructure/observability/metrics_agents.py` (`initiative_evaluations_total`, `initiative_duration_seconds`, `initiative_followups_total`, `initiative_actions_executed_total`), `infrastructure/observability/grafana/dashboards/13-proactive-heartbeat.json` (4 panneaux), `apps/api/tests/unit/metric_coverage_baseline.json` (2 entrées : la ratchet ne fait que retirer)
- Create: `apps/api/alembic/versions/<date>-<rev>_retire_initiative_evaluator.py` (efface `JEV_INITIATIVE_UTILITY_ENABLED` et les créneaux `initiative`, `jev_initiative_utility`)

**Interfaces :**
- Consumes: `resolve_recurrence_suggestion` (B.1).
- Produces: un graphe où chaque arête qui menait à `initiative` mène à `response` ; `MessagesState` sans clé `initiative_*`.

- [ ] **Step 1 :** garde `tests/unit/domains/agents/test_no_initiative_node_guard.py` : aucun module de `apps/api/src` n'importe `initiative_node`, `jev_initiative*`, ni ne nomme `NODE_INITIATIVE`, `initiative_eligible`, `is_initiative_eligible`.
- [ ] **Step 2 :** lancer → FAIL.
- [ ] **Step 3 :** retirer le nœud et ses arêtes ; supprimer `tests/unit/domains/agents/nodes/test_routing_initiative.py` et `test_routing_react_initiative.py`, et dans `test_routing_react.py` chaque test qui attendait `"initiative"` attend `"response"` ; les 20 fichiers de tests qui nomment le nœud ou ses puces (liste : `grep -rl "initiative_node\|NODE_INITIATIVE\|jev_initiative\|route_from_initiative\|push_followups" apps/api/tests`) sont supprimés ou réécrits.
- [ ] **Step 4 :** retirer le champ des manifestes par édition mécanique (`initiative_eligible=…,` sur sa ligne), puis `task test:backend:agents` → vert ; `tests/unit/domains/agents/tools/test_tool_registry_smoke.py` vert.
- [ ] **Step 5 :** migration + `task db:migrate:replay-check` → vert ; `tests/unit/test_env_template_parity_guard.py` vert ; `test_metric_coverage_ratchet_guard.py` vert après `task ratchet:metrics`.
- [ ] **Step 6 :** `task test:backend:unit:fast` → vert ; `task lint:backend` → vert.

### Task B.3 : puces de relance et motivation

**Files:**
- Delete: `apps/api/src/domains/agents/services/streaming/followup_metadata.py`, `apps/web/src/components/chat/FollowupChips.tsx` (+ test)
- Modify: `services/streaming/done_metadata.py`, `services/streaming/service.py`, `services/streaming/voice_scope.py` (champs `followups`, `motivation` de l'événement de fin), `api/archive_metadata.py:4,59,193-220` (`with_initiative_motivation` retiré ; les métadonnées déjà archivées gardent leur clé, personne ne la lit), `apps/web/src/lib/chat-surfaces.ts:60,94,125` (surface `followups`), `apps/web/src/components/chat/ChatConditionalSurfaces.tsx:36,60-63`, `ChatWorkspace.tsx`, `SelectionActions.tsx`, `reducers/chat-reducer.ts`, `types/chat-state.ts`, `types/chat.ts`, `apps/web/locales/*/translation.json` (clés des puces et de la motivation), `apps/web/src/lib/sse-handlers/__tests__/sse-symmetry.test.ts`

- [ ] **Step 1 :** test vitest `apps/web/src/lib/__tests__/chat-surfaces.test.ts` : `CHAT_SURFACES` ne contient plus `'followups'` ; `sse-symmetry` : un événement de fin portant `followups` est accepté et le champ ignoré (Review Focus 4).
- [ ] **Step 2 :** lancer → FAIL.
- [ ] **Step 3 :** retirer la surface, le composant, les champs et les clés ; `tests/unit/domains/agents/api/test_archive_metadata.py` sans motivation.
- [ ] **Step 4 :** `task test:frontend`, `task lint:frontend`, `pytest tests/unit/domains/agents/services/streaming tests/unit/domains/agents/api -q` → vert.

### Task B.4 : FAQ, guides, documentation, CLAUDE.md

**Files:**
- Modify: `apps/web/locales/*/translation.json` (entrée `faq.intro.features.proactiveInitiative`, et `FAQContent.tsx:176,262`), `apps/web/src/data/guides/how.*.md` (le passage sur les puces de relance, s'il existe dans les six), `docs/ARCHITECTURE_LANGRAPH.md`, `docs/technical/REACT_EXECUTION_MODE.md`, `docs/technical/RESPONSE.md`, `docs/technical/ROUTER.md`, `docs/technical/STATE_AND_CHECKPOINT.md`, `docs/technical/AGENT_MANIFEST.md`, `docs/guides/GUIDE_TOOL_CREATION.md` (champ `initiative_eligible`), `docs/technical/MCP_INTEGRATION.md`, `docs/technical/VOICE.md`, `docs/technical/HEARTBEAT_AUTONOME.md`, `docs/GETTING_STARTED.md`, `docs/INDEX.md`, `CLAUDE.md` (deux phrases : « the initiative node is bounded by `is_initiative_eligible` » dans « Ephemeral Python » ; « the planner, the ReAct loop, the router, the initiative, a sub-agent » dans « What a turn may offer is filtered once »), `apps/web/src/data/maps/technical.json:388` et `functional.json`, `history.json`
- Run: `task docs:sync-agents`, `task docs:maps`, `task docs:budget`

- [ ] **Step 1 :** `task lint:docs:preview` → liste.
- [ ] **Step 2 :** corriger chaque document (le registre des initiatives de LIA, lui, reste décrit) ; la FAQ perd la fonctionnalité dans les six langues (parité stricte).
- [ ] **Step 3 :** `task lint:docs:preview`, `task lint:i18n` → 0 constat ; `scripts/audit/claude_md_budget.py` vert.

### Task B.5 : preuve de bout en bout

- [ ] **Step 1 :** `task test:backend:unit:fast`, `task test:backend:agents`, `task test:frontend`, `task test:e2e` → verts.
- [ ] **Step 2 :** `task ci:fast` → vert.
- [ ] **Step 3 :** sur dev (`task dev:detach`), un tour outillé en ReAct et un en pipeline : la réponse arrive, le panneau debug n'a plus de section initiative, `token_usage_logs` ne porte aucune ligne `initiative` ni `jev_initiative_utility` pour ces tours.

---

## Lot C — Seuils déclarés et réglables

### Task C.1 : le registre des portes

**Files:**
- Create: `apps/api/src/domains/llm_config/jev_gates.py`
- Create: `apps/api/tests/unit/domains/llm_config/test_jev_gates.py`
- Modify: `apps/api/src/core/constants.py` (les cinq constantes `JEV_*_MIN_CONFIDENCE` deviennent les défauts déclarés dans le registre et disparaissent du module), `apps/api/src/domains/meetings/jev_selection.py` (`MIN_CONFIDENCE`), `domains/radio/jev_checker.py` (`DECISION_MARGIN`), `domains/agents/services/planner/jev_consultation.py` (`MIN_CONFIDENCE`), `domains/agents/services/hitl/jev_item_filter.py` (`MIN_CONFIDENCE`, `REFERENCE_SCOPE_MIN_CONFIDENCE`), `domains/agents/services/hitl/jev_rejection.py`, `domains/agents/services/analysis/jev_memory_presence.py`, `domains/agents/semantic/jev_value_kind.py`, `domains/agents/services/qualification/policy.py`

**Interfaces :**
- Produces:
  ```python
  class GateKind(StrEnum): CHOICE_CONFIDENCE = "choice_confidence"; NOUL_PROBABILITY = "noul_probability"; MARGIN = "margin"
  class GateScope(StrEnum): EACH = "each"; ALL = "all"
  @dataclass(frozen=True)
  class JevGate: key: str; kind: GateKind; default: Decimal; minimum: Decimal; maximum: Decimal; scope: GateScope; abstains_to: str
  JEV_GATES: Mapping[JevUsage, tuple[JevGate, ...]]
  def gate_defaults(usage: JevUsage) -> dict[str, Decimal]
  def passes(gate: JevGate, score: float, threshold: Decimal) -> bool   # Decimal(str(score)) comparé en exact ; MARGIN : score >= 1 - threshold
  def assert_jev_gates_complete() -> None   # chaque usage de JevUsage hors observateurs a ≥ 1 porte ; chaque clé est unique par usage
  ```
- Valeurs par défaut (celles livrées) : `meeting_template.template 0.85` ; `radio_verification.line_margin 0.16 (ALL)` ; `consultation_path.path 0.98` ; `consultation_bounded.path 0.98` ; `hitl_exclusion.item 0.90 (ALL)`, `hitl_exclusion.reference_scope 0.80` ; `hitl_rejection.rejection 0.80` ; `memory_reference_presence.absence 0.99` ; `parameter_kind.kind 0.30` ; `email_classification.category 0.80`, `email_classification.priority 0.80`, `email_classification.alert 0.80` ; `event_classification.category 0.80`. Bornes : `[0.50, 1.00]` pour les confiances de choix sauf `parameter_kind.kind [0.10, 1.00]` ; `radio_verification.line_margin [0.02, 0.40]`. Observateurs : `observe_*.empty 0.90`, lu seulement par le lot G.

- [ ] **Step 1 :** écrire `test_jev_gates.py` : `test_defaults_equal_shipped_values` (la table ci-dessus, valeur par valeur), `test_margin_compares_exactly` (`passes(margin 0.18, score 0.82, Decimal("0.18"))` est vrai — faux en flottants, mesuré le 06/11), `test_registry_complete_at_boot`.
- [ ] **Step 2 :** lancer → FAIL.
- [ ] **Step 3 :** écrire le registre ; chaque consommateur lit `gate_defaults(usage)[key]` à la place de sa constante (le seuil effectif arrive à la tâche C.2) ; `assert_jev_gates_complete()` est appelé à l'import du module, comme `assert_jev_registry_complete()` l'est dans `jev_registry.py:180`.
- [ ] **Step 4 :** test de caractérisation `tests/unit/domains/agents/services/test_jev_gates_match_consumers.py` : les réponses enregistrées dans `tests/fixtures/jev_classification_qualified_*.json` rejouées par `classify_answers` donnent exactement les `predictions` enregistrées (0 écart ; vérifié hors ligne le 06/11).
- [ ] **Step 5 :** `pytest tests -q -k "jev or typesafe or classification or decision_slot or template_resolution"` → vert (ligne de base : 1 105 tests).

### Task C.2 : seuils stockés, lus avec les interrupteurs, transportés par la tentative

**Files:**
- Modify: `apps/api/src/domains/system_settings/models.py` (une clé `JEV_<USAGE>_THRESHOLDS` par usage ayant une porte), `system_settings/registry.py` (specs : valeur JSON, défaut `"{}"`), `domains/llm_config/jev_settings.py` (`read_flags` lit aussi les clés de seuils dans la MÊME requête ; `JevSnapshot` gagne `thresholds: Mapping[str, Decimal]` ; `read_configuration` ne plafonne plus le délai : `config.timeout_seconds` s'il est défini, sinon une constante `JEV_DEFAULT_TIMEOUT_SECONDS = 2.0` ajoutée à `core/constants.py` — le `min(…, 5.0)` de la ligne 108 disparaît), `infrastructure/llm/decision_types.py` (`DecisionAttempt.thresholds: Mapping[str, Decimal]`), `infrastructure/llm/jev_runtime.py` (copie les seuils de l'instantané dans la tentative ; un consommateur à question unique les reçoit donc aussi), les neuf consommateurs (lisent `attempt.thresholds[key]`, plus jamais `gate_defaults` directement), `domains/agents/services/qualification/service.py` (`policy_fingerprint(thresholds: Mapping[str, Decimal] | None = None)` : défauts quand `None` ; la clé de cache utilise les seuils effectifs), `domains/agents/services/qualification/cache.py`
- Create: migration `<date>-<rev>_jev_threshold_settings.py` (insère chaque clé à `'{}'`, `downgrade` les efface)

**Interfaces :**
- Produces: `def resolve_thresholds(usage: JevUsage, stored: str | None) -> dict[str, Decimal]` dans `jev_settings.py` : JSON valide et clés connues → valeurs bornées ; JSON invalide, clé inconnue ou valeur hors bornes → la valeur par défaut pour cette clé et un `logger.warning("jev_threshold_ignored", usage=, key=)`.

- [ ] **Step 1 :** tests `tests/unit/domains/llm_config/test_jev_thresholds.py` : `test_stored_value_overrides_default`, `test_invalid_json_falls_back_to_defaults`, `test_out_of_bounds_value_ignored`, `test_snapshot_carries_thresholds_into_attempt` (runtime avec client factice) ; `tests/unit/domains/agents/services/test_classification_native_record.py` reste tel quel (l'empreinte des DÉFAUTS ne change pas) ; nouveau `test_policy_fingerprint_changes_with_effective_thresholds`.
- [ ] **Step 2 :** lancer → FAIL.
- [ ] **Step 3 :** implémenter ; `test_llm_wall_clock_guard.py` doit accepter la lecture du délai du créneau (règle « la base d'abord »).
- [ ] **Step 4 :** `task db:migrate:replay-check` ; `pytest tests -q -k "jev or classification"` → vert.

### Task C.3 : API d'administration des seuils

**Files:**
- Modify: `apps/api/src/domains/llm_config/jev_admin.py` (`JevUsageStatus` gagne `gates: list[JevGateStatus]` — clé, nature, défaut, bornes, valeur effective, `qualified: bool` vrai quand toutes les valeurs égalent les défauts), `domains/llm_config/router.py` (`PATCH /admin/llm-config/jev/thresholds`)
- Create: `apps/api/tests/unit/domains/llm_config/test_jev_admin_thresholds.py`

**Interfaces :**
- Produces:
  ```python
  class JevThresholdUpdate(BaseModel): usage: JevUsage; values: dict[str, Decimal]   # une clé absente garde sa valeur courante
  async def update_jev_thresholds(db: AsyncSession, body: JevThresholdUpdate, *, admin_user_id: UUID, request: Request) -> JevSettingsResponse
  ```
  Écrit par `write_setting` (audit), sous le même verrou consultatif `hashtextextended('jev-routing', 0)` que les interrupteurs ; `raise_invalid_input` (`core/exceptions.py:872`) pour une clé inconnue ou une valeur hors bornes, rien n'est écrit.

- [ ] **Step 1 :** tests : `test_patch_writes_bounded_value_and_audits`, `test_unknown_key_is_422_and_writes_nothing`, `test_out_of_bounds_is_422`, `test_get_reports_qualified_false_after_change`.
- [ ] **Step 2 :** lancer → FAIL ; implémenter ; relancer → vert.

### Task C.4 : écran d'administration — seuils

**Files:**
- Modify: `apps/web/src/components/settings/AdminJevSection.tsx` (par usage : une ligne par porte avec `Slider` de `components/ui/slider.tsx` borné aux bornes publiées, valeur, défaut, badge « hors relevé qualifié » quand `qualified === false`, bouton « valeur par défaut »), `apps/web/src/types/jev.ts` (schéma zod : `gates`, `qualified`), `apps/web/src/hooks/useJev*.ts` ou le hook local de la section (mutation `PATCH …/thresholds` via `useApiMutation`), `apps/web/locales/*/translation.json` (libellés des portes, « hors relevé qualifié », aide), `apps/web/e2e/smoke/settings-jev.spec.ts`
- Test: `apps/web/src/components/settings/__tests__/AdminJevSection.test.tsx`

- [ ] **Step 1 :** tests vitest : rendu des portes depuis une réponse factice ; le curseur a un nom accessible traduit et des bornes `min`/`max` égales à celles publiées ; un changement envoie `PATCH` avec `{usage, values: {key: value}}` ; le badge apparaît quand `qualified` est faux.
- [ ] **Step 2 :** lancer → FAIL ; implémenter ; `task test:frontend`, `task lint:frontend` (ratchets a11y/complexité) → vert.
- [ ] **Step 3 :** e2e `settings-jev.spec.ts` : régler un seuil, recharger, la valeur tient ; `task test:e2e` → vert.

---

## Lot D — Statistiques durables et accord des observateurs

### Task D.1 : tables, écriture agrégée, vidage possédé

**Files:**
- Create: `apps/api/src/domains/llm_config/jev_statistics_models.py` (`JevJudgementDaily(usage String(50), gate_key String(40), day Date, bucket SmallInteger, count Integer, PK sur les quatre)`, `JevOutcomeDaily(usage, day, outcome String(32), count)`, `JevObserverAgreementDaily(usage, day, verdict String(16), bucket SmallInteger, proposed Boolean, count)`), `domains/llm_config/jev_statistics_repository.py`, `domains/llm_config/jev_statistics_sink.py`, migration `<date>-<rev>_jev_statistics.py`
- Modify: `apps/api/src/infrastructure/database/registry.py` (`import_all_models`), `infrastructure/llm/jev_runtime.py` (après chaque tentative payée : un compartiment par réponse — `floor(Decimal(str(score)) * 100)`, plafonné à 100 pour un Noul — et l'issue de la tentative ; rien pour `disabled`), les 13 sites qui incrémentent `jev_decisions_total` (remplacés par `count_jev_outcome(usage, outcome)` dans `infrastructure/observability/metrics_jev.py`, qui incrémente la métrique ET empile la ligne ; garde AST refusant tout autre `jev_decisions_total.labels`), `infrastructure/startup/observability.py` ou `schedulers.py` (démarre le vidage), `startup/shutdown.py` (le vide une dernière fois et l'attend)

**Interfaces :**
- Produces:
  ```python
  def count_jev_outcome(usage: JevUsage, outcome: str) -> None                       # metrics_jev.py, seule porte
  def record_judgements(usage: JevUsage, scores: Mapping[str, float]) -> None        # jev_statistics_sink.py, gate_key → score
  def record_observer_agreement(usage: JevUsage, verdict: str, score: float, proposed: bool) -> None
  async def flush_jev_statistics() -> int                                             # lignes écrites ; UPSERT trié par clé, ON CONFLICT DO UPDATE count = count + EXCLUDED.count
  class JevStatisticsFlusher: start(), async stop()                                   # une tâche par travailleur, période JEV_STATISTICS_FLUSH_SECONDS (défaut 30), jitter
  ```
  L'accumulateur agrège en mémoire sous un verrou ; une instruction ne porte jamais deux fois la même clé (`CardinalityViolationError`, reproduit le 06/11).

- [ ] **Step 1 :** tests unitaires `tests/unit/domains/llm_config/test_jev_statistics_sink.py` : `test_bucket_is_exact_floor_of_decimal` (0.29 → 29, 1.0 → 100, Noul 1.0 → 100), `test_disabled_writes_nothing`, `test_rows_are_sorted_and_deduplicated_before_upsert`, `test_flusher_is_awaited_at_shutdown` ; intégration `tests/integration/domains/llm_config/test_jev_statistics_upsert.py` sur PostgreSQL réel : 8 écrivains concurrents, 0 interblocage, somme exacte (simulé le 06/11 : 150 022 = 150 022, p95 4,3 ms).
- [ ] **Step 2 :** lancer → FAIL ; implémenter ; `task test:backend:unit:fast` puis `task test:backend:integration` → vert ; `task db:migrate:replay-check` → vert.
- [ ] **Step 3 :** `tests/unit/test_jsonb_mutation_guard.py`, `test_scheduler_jitter.py` verts ; la nouvelle métrique `jev_statistics_rows_total` est référencée par un panneau du tableau 13 (ratchet de couverture).

### Task D.2 : accord des observateurs

**Files:**
- Modify: `apps/api/src/domains/agents/services/jev_extraction_observer.py` (`_record` : après l'enregistrement de diagnostic, `record_observer_agreement(usage, verdict=attempt.answer.choice, score=choice_confidence(attempt.answer), proposed=_proposed_anything(observed.result))`)
- Create: `apps/api/tests/unit/domains/agents/services/test_jev_extraction_observer_agreement.py`

**Interfaces :**
- Produces: `def _proposed_anything(result: ContextPreview | None) -> bool` : vrai quand la sortie de l'extracteur contient au moins un élément proposé (liste non vide ou action `create`/`update`/`delete`) ; une sortie illisible compte `proposed=True` (jamais lue comme vide).

- [ ] **Step 1 :** tests : sortie `[]` → `proposed=False` ; sortie avec un élément → `True` ; sortie illisible → `True` ; `attempt.outcome != "success"` → aucune ligne d'accord.
- [ ] **Step 2 :** lancer → FAIL ; implémenter ; vert.

### Task D.3 : lecture

**Files:**
- Modify: `apps/api/src/domains/llm_config/router.py` (`GET /admin/llm-config/jev/statistics?days=30`, `days` ∈ [1, 90]), `domains/llm_config/jev_admin.py` ou nouveau `jev_statistics_read.py`
- Create: `apps/api/tests/unit/domains/llm_config/test_jev_statistics_read.py`, `tests/integration/domains/llm_config/test_jev_statistics_read.py`

**Interfaces :**
- Produces:
  ```python
  class JevGateStatistics(BaseModel): key: str; threshold: Decimal; buckets: list[int]   # 101 entrées, 0..100
  class JevAgreementRow(BaseModel): verdict: str; bucket: int; proposed: bool; count: int
  class JevUsageStatistics(BaseModel): usage: JevUsage; calls: int; cost_eur: Decimal; latency_p50_ms: int | None; outcomes: dict[str, int]; gates: list[JevGateStatistics]; agreement: list[JevAgreementRow] | None
  class JevStatisticsResponse(BaseModel): days: int; usages: list[JevUsageStatistics]
  async def read_jev_statistics(db: AsyncSession, *, days: int) -> JevStatisticsResponse
  ```
  Coût, volume et latence viennent d'UN agrégat sur `token_usage_logs` groupé par `llm_type` (index `controller_window`, 16,7 ms sur 109 178 lignes en production) ; les compartiments d'une même requête viennent d'UN `SELECT … GROUP BY` sur chaque table ; aucune boucle par usage.

- [ ] **Step 1 :** tests : un usage sans ligne → `buckets` de 101 zéros et `calls 0` ; `days=0` → 422 ; les sommes par usage égalent les lignes insérées (intégration).
- [ ] **Step 2 :** lancer → FAIL ; implémenter ; vert.

### Task D.4 : écran d'administration — statistiques

**Files:**
- Modify: `apps/web/src/components/settings/AdminJevSection.tsx` (par usage, un panneau repliable : volume, coût, latence p50, répartition des issues, histogramme des jugements par porte — `components/effects/SeriesChart.tsx` — avec la ligne du seuil, et « part conclue à ce seuil » recalculée côté client depuis les compartiments quand le curseur de la tâche C.4 bouge ; pour les observateurs, le tableau d'accord : verdict × l'extracteur a proposé / n'a rien proposé), `apps/web/src/types/jev.ts` (schéma zod de la réponse), hook `useApiQuery` sur `/admin/llm-config/jev/statistics`, `apps/web/locales/*/translation.json`
- Test: `AdminJevSection.test.tsx`, `apps/web/e2e/smoke/settings-jev.spec.ts`

- [ ] **Step 1 :** tests vitest : la part conclue est `somme(buckets[b] pour b ≥ seuil×100) / somme(buckets)`, affichée en pour cent exact ou « — » sans donnée ; un usage à `calls 0` n'affiche pas d'histogramme vide mais « aucune décision sur la période » ; les figures ont un nom accessible traduit.
- [ ] **Step 2 :** lancer → FAIL ; implémenter ; `task test:frontend:coverage`, `task lint:frontend` → vert.
- [ ] **Step 3 :** e2e : la section lit l'API moquée et affiche les six langues (lint i18n).

### Task D.5 : documentation du lot

**Files:**
- Modify: `docs/technical/JEV_INTEGRATION.md` (sections « Seuils » et « Statistiques » : où ils vivent, qui écrit, ce que signifie « hors relevé qualifié », la perte bornée d'un vidage), `docs/architecture/ADR-373-…md` (statut des lots C et D), `docs/INDEX.md`, cartes (`task docs:maps`)

- [ ] **Step 1 :** `task lint:docs:preview` → 0 constat.

---

## Lot E — Corrections

### Task E.1 : la batterie de sélectivité tourne et lit la fenêtre réelle

**Files:**
- Modify: `apps/api/scripts/measure_extraction_selectivity.py:555-590` (`from src.core.i18n import get_language_name` ; `_to_messages` est suivi de la coupe `messages[last_human - 3 : last_human + 1]` avant le rendu, comme `extraction_service._analyze_interests_core` et `memory_extractor.extract_memories_background`)
- Create: `apps/api/tests/unit/scripts/test_measure_extraction_selectivity_renders_runtime_window.py`

- [ ] **Step 1 :** test : importer le script (sans appel de modèle) ; pour `pos_deep_dive` (cinq messages), le prompt rendu contient exactement deux lignes `USER:`.
- [ ] **Step 2 :** lancer → FAIL (ImportError) ; corriger ; vert.
- [ ] **Step 3 :** noter dans le docstring du scénario `pos_deep_dive` que le motif « trois tours » n'est observable qu'à deux tours dans la fenêtre livrée (fait, pas une correction de ce plan).

### Task E.2 : locales de l'écran

**Files:**
- Modify: `apps/web/locales/{en,fr,de,es,it,zh}/translation.json` (`settings.admin.jev.usageHelp.email_classification`, `settings.admin.jev.usageHelp.event_classification`)

- [ ] **Step 1 :** test vitest `AdminJevSection.test.tsx` : aucune clé brute n'est rendue pour un usage du registre (`screen.queryByText(/usageHelp\./)` est nul).
- [ ] **Step 2 :** lancer → FAIL ; ajouter les six textes ; `task lint:i18n` → vert.

---

## Lot F — « Réponse attendue » sur les e-mails (après le lot D)

### Task F.1 : corpus et rejeu qualifié

**Files:**
- Modify: `apps/api/tests/fixtures/jev_classification_cases.json`, `_holdout.json`, `_adversarial.json` (champ `expected_reply: bool | null` sur chaque e-mail ; `Case` et `score` dans `tests/fixtures/classification_corpus.py` ; `Gate.minimum_positive_coverage` s'applique aussi à la nouvelle dimension), `apps/api/src/domains/agents/prompts/v1/jev_email_reply_expected_question.txt` (Noul ; critères : « le message demande explicitement une réponse ou une action de la personne, avec ou sans échéance » / « aucune réponse n'est attendue : notification, promotion, confirmation, bulletin »), `domains/agents/services/qualification/{policy,service,batches}.py` (troisième question par e-mail ; un e-mail dont la catégorie acceptée est `spam` ou `phishing_scam` est publié `reply_expected=False` quel que soit le Noul — mesuré le 06/11 : l'hameçonnage lit 0,33-0,92), `core/content_classification.py` (champ `reply_expected: bool | None`, version `email-event-v2-reply`), `jev_gates.py` (`email_classification.reply_expected 0.70`, bornes `[0.50, 0.95]`)
- Run: `scripts/analysis/jev_classification_replay.py` (racine du dépôt) sur les trois jeux (31 appels, ≈ 0,01 €, budget à faire valider) → nouveaux `jev_classification_qualified_*.json`

- [ ] **Step 1 :** `test_classification_native_record.py` → FAIL (empreinte changée) tant que le rejeu n'est pas enregistré ; après rejeu → vert avec `wrong_accepted == 0`.

### Task F.2 : contrat d'affichage

**Files:**
- Modify: `apps/web/src/lib/content-classification.ts` (nouveau littéral de version, champ optionnel `reply_expected`), `apps/web/src/components/chat/ClassificationBadges.tsx`, `apps/api/src/domains/agents/display/components/classification_badges.py`, `core/classification_projection.py` (`classification_text` dit « réponse attendue » dans la langue de l'utilisateur via `core.i18n_*`), `prompts/v1/response_system_prompt_base.txt` (`<ContentQualification>` : une ligne), `apps/web/locales/*/translation.json`, `docs/technical/JEV_SEMANTIC_QUALIFICATION.md`
- Test: `apps/web/src/lib/__tests__/content-classification.test.ts` (une annotation v1 reste lue ; une v2 sans `reply_expected` aussi), tests des deux rendus de badge, `test_classification_projection.py`

- [ ] **Step 1 :** tests → FAIL ; implémenter ; `task test:frontend`, `task lint:i18n`, `pytest -k classification` → vert.

---

## Lot G — Saut d'extraction (conditionnel)

**Condition d'ouverture :** après au moins quatre semaines de statistiques (lot D) sur les observateurs rallumés, la table d'accord montre, pour un extracteur donné, zéro ligne `verdict=empty, bucket ≥ 90, proposed=true` sur au moins 200 observations. Alors, et seulement alors :

### Task G.1 : amendement ADR-325 et saut sous seuil

**Files:**
- Modify: `docs/architecture/ADR-325-…md` (amendement : « an observer whose confident "empty" verdict has never contradicted a write over N observations may skip that extractor ; measured on … »), `jev_extraction_observer.py` (`observe_extractor` gagne `skip_when_empty: bool` lu d'une clé `JEV_OBSERVE_<KIND>_SKIP_ENABLED` ; l'observateur court AVANT l'extracteur ; verdict `empty` à confiance ≥ `observe_<kind>.empty` → l'extracteur n'est pas appelé, `count_jev_outcome(usage, "skipped")`), `jev_registry.py`, `system_settings`, écran (interrupteur par extracteur, à côté de l'accord)
- Test: `test_jev_extraction_observer_skip.py` : sous le seuil l'extracteur tourne ; au-dessus il ne tourne pas ; une panne de l'observateur fait tourner l'extracteur (jamais « indisponible » lu comme « vide »).

---

## Ordre d'exécution et estimation (à mon rythme : portes + preuves)

| Ordre | Lot | Dépend de | Estimation |
|---|---|---|---|
| 1 | 0 — ADR | — | 2 h |
| 2 | A — aperçus | 0 | 6-8 h |
| 3 | B — évaluateur d'initiative | 0 (indépendant de A) | 14-18 h |
| 4 | E — corrections | — | 2-3 h |
| 5 | C — seuils réglables | A, B (le registre ne déclare que les usages restants) | 10-12 h |
| 6 | D — statistiques et accord | C | 12-16 h |
| 7 | F — réponse attendue | D (lire d'abord la distribution réelle) | 8-10 h + rejeu payant |
| 8 | G — saut d'extraction | D + condition mesurée | 4-6 h |

Après chaque lot : `task ci:fast` ; après A, B, C, D : `task test:backend:integration` ; la mise en production reste au propriétaire (`lia-release`, puis `lia-deploy-prod`), qui rallume les usages depuis l'écran une fois le lot C déployé.

## Hors périmètre, signalé

- Le motif `deep_dive` de l'extraction d'intérêts demande trois tours que la fenêtre de quatre messages ne peut montrer : à mesurer avec le vrai extracteur (appels génératifs).
- Le tri des notifications proactives (2 638 appels, 1,91 €) et la question compagne des rendez-vous : non validés, non planifiés.
- Le programme « habitudes » décidera du sort de la suggestion de routine ; ce plan la déplace sans la changer.
