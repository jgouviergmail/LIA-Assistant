# Chaîne d'autorité et registre des effets — rendre l'exécution agentique gouvernable et vérifiable après coup

**Date** : 2026-09-03 · **Statut** : APPROUVÉE par le propriétaire le 2026-09-03 (8 décisions, §7), zéro code, plan des lots 0-1 écrit · **ADR cible** : ADR-263 (260/261/262 pris par les boucles silencieuses, publiées en v1.40.0 le 2026-09-03 — vérifié par `ls docs/architecture/`)

## 0. Origine et verdict

Un interlocuteur externe décrit sa « Control Plane » : chaîne d'autorité
(demande → autorité → scope → capacités → préconditions → autorisation de
mutation → **consommation** → exécution → preuve), séparation observer/muter,
`unknown ≠ pass`, autorisation transactionnelle (pas de simple réessai après
arrêt inattendu), preuves hashées reliées en graphe de provenance. Il propose
de faire passer un même scénario dans nos deux modèles et de comparer, frontière
par frontière, qui garantit quoi.

**Verdict, chaque affirmation ayant été contre-vérifiée dans le code** : la
réflexion est véridique et pertinente pour LIA, mais **pas au niveau où elle
est formulée**. Ce qui manque n'est pas un graphe de provenance générique
hashant chaque artefact : c'est trois choses précises que l'exécution actuelle
ne sait pas faire, mesurées par sept simulations (§1) :

1. **Une mutation n'est pas déclarée : elle est devinée, et la doctrine qui
   l'exempte de confirmation n'est écrite nulle part.** 13 outils natifs
   classés « mutation » par le catalogue n'ont aucune porte de confirmation
   dans aucun des deux modes (simulation 1), et la garde CI existante vérifie
   l'invariant **inverse** seulement.
2. **Une autorisation n'est pas consommée.** Un brouillon confirmé reste
   `action=confirm` dans l'état tant que le nœud de réponse n'a pas rendu ;
   entre l'effet (envoi) et le nettoyage, tout échec rejoue l'envoi au tour
   suivant. Prouvé par test : la même confirmation exécute deux fois
   (simulations 2 et 4). En ReAct, un appel exécuté avant un appel interrompu
   dans la même itération est rejoué à la reprise, mutation non confirmée
   comprise. Une action planifiée relance le tour entier sur `TimeoutError`,
   effets compris.
3. **Il n'existe aucune trace durable de ce qui a été exécuté** : la trace
   persistée ne contient que des clés i18n (garde PII, délibérée), le traçage
   Langfuse par outil est du code mort (`trace_tool_call` : 0 appelant), et les
   `ToolMessage` ReAct sont fenêtrés puis compactés. « Quel outil, quels
   arguments, sous quelle approbation, avec quel résultat » n'est pas
   reconstructible après coup.

Ce que LIA fait déjà **mieux** que le modèle décrit, et qu'il ne faut pas
reconstruire : verdict ≠ fait (ADR-184, `plan_blockers.py`), provenance du
contenu tiers (ADR-167/257), HITL rejouable (ADR-092), historique valide par
construction (ADR-248 inv. 4), idempotence ReAct par `tool_call_id`, empreinte
HMAC des appels (`loop_guard.compute_call_digest`), `unknown` plafonné à
`degraded` (diagnostics), bac à sable conteneur seul (ADR-249).

## 1. Ce qui a été vérifié (preuves)

Chaque ligne cite le code lu ; rien n'est déduit d'un docstring.

| # | Hypothèse de l'interlocuteur | Verdict pour LIA | Preuve |
|---|---|---|---|
| H1 | « capability exists ≠ admissible ≠ caller authorized ≠ mutation authorized » | **VRAI, et LIA les confond** : le validateur calcule `requires_hitl`, `allowed_roles`, scopes, mais son verdict n'est lu par personne à l'exécution | `validator.py:469,727,952` ; `plan_blockers.py` docstring (« the router never reads is_valid ») ; `approval_gate_node.py:115-128` (auto-approve même si `requires_hitl`) |
| H2 | « exposer un outil via MCP court-circuite une politique qui n'existe qu'au niveau du graphe » | **VRAI en mode pipeline, prouvé à l'exécution (sim. 5)** : `hitl_required` (MCP par serveur, ou `mcp_hitl_required`, défaut `False`) n'est lu que par ReAct et par le validateur ; `parallel_executor.py` ne contient ni `interrupt(` ni `hitl_required`, appelle `tool.coroutine(**args)` directement (`:2714`) ; les vérificateurs runtime `requires_approval` / `requires_tool_approval` n'ont **aucun appelant** hors de leurs docstrings | sim. 5 ; `react_tool_selector.py:126-150` ; `core/config/mcp.py:153` ; `infrastructure/mcp/registration.py:370-378` ; `utils/hitl_config.py:30`, `agent_registry.py:1529` (morts) ; `test_hitl_required_consistency.py` docstring |
| H3 | « unknown n'est jamais pass » | **FAUX dans la porte d'approbation** : sans verdict, « assuming approval not required » → `PLAN_APPROVED=True` | `approval_gate_node.py:101-107` |
| H4 | « l'autorisation doit être consommée, et aucune mutation avant elle » | **Pipeline : pas de consommation** (sim. 2 au niveau exécuteur, sim. 4 au niveau graphe avec le vrai `MessagesState` + checkpointer) ; le repli d'erreur du nœud (`_response_error_fallback`) ne rend que `messages`, donc une exception **attrapée** laisse aussi `confirm` en place. **ReAct : consommation par construction entre deux itérations seulement** (`tc_id in existing_tool_msg_ids`) ; dans une itération qui s'interrompt, tout appel placé AVANT l'appel interrompu est rejoué à la reprise — mutation non confirmée comprise (« Measured, not yet prevented », compteur `react_tool_executions_before_interrupt_total`) | `response_node.py:2479` (effet) vs `:3760` (nettoyage) et `:3255-3284` (repli) ; `router_node_v3.py` ne remet pas `draft_action_result` à zéro ; `react_nodes.py:614-630,643-648` |
| H5 | « un arrêt inattendu ne doit pas simplement réessayer » | **FAUX pour les actions planifiées** : nouveau thread par tentative, tour entier rejoué sur `TimeoutError`/`ConnectionError`/`OSError` ; `recover_stale_executing` remet `EXECUTING→ACTIVE` après 10 min | `scheduled_action_executor.py:315-323,398-415` ; `scheduled_actions/repository.py:100-118` |
| H6 | « observer ≠ muter, structurellement » | **Partiel** : la phase d'initiative valide lecture seule (`_validate_read_only`) ; le sous-agent « READ-ONLY » n'est protégé que par une liste manuelle de 17 noms — hue, navigateur, bascule d'action planifiée, `delete_task_tool` passent (sim. 3) ; la liste blanche `.env` n'est validée qu'en forme | `sub_agents/constants.py:16` ; `core/config/agents.py:3374-3410` ; `sub_agents/skill_resolver.py:57-67` |
| H7 | « preuve de ce qui a été exécuté » | **ABSENTE** : trace persistée = `{emoji, i18n_key, category}` ; `trace_tool_call` sans appelant ; les deux exécuteurs appellent `tool.coroutine(**args)` directement, donc aucun callback LangChain/Langfuse ne voit un appel d'outil ; `completed_steps` écrasés à chaque tour ; seul `TokenUsageLog` (run_id, nœud, modèle) trace les appels LLM | `streaming/trace_capture.py:1-30` ; grep `trace_tool_call` ; `parallel_executor.py:2714`, `react_nodes.py:775` ; `chat/models.py:53-80` |
| H8 | « identités stables : source, configuration, exécuteur » | **Partiel** : modèle par appel LLM oui ; `calculate_prompt_hash` exporté et jamais appelé ; ni `app_version`, ni mode, ni version de catalogue attachés à un run | `prompts/prompt_loader.py:244` ; `prompts/__init__.py:905` |
| H9 | « une autorité (bail, verrou) a un jeton propriétaire » | **Violé par l'élection de leader** : `expire` et `delete` inconditionnels (règle systémique CLAUDE.md « SET NX puis EXPIRE/DELETE inconditionnel interdit ») ; le verrou de run actif, lui, est conditionnel en Lua | `scheduler/leader_elector.py:177,268,298` ; `streaming/run_stream_broker.py:340-350` |
| H10 | « liaison de l'approbation à l'opération exacte » | **BON** : confirmation = `draft_content` affiché (ADR-092), `draft_id` différent → cancel, décision un-clic liée à `message_id` (`HitlDecisionStaleError`) ; le canal langage naturel (« oui ») se lie à « ce qui est en attente », et la fenêtre de validité est un effet de bord d'un TTL Redis documenté « pour les métriques de temps de réponse » | `hitl_dispatch_node.py:706-712,288-300` ; `orchestration/approval_decision.py:750-755` ; `core/config/advanced.py:296-298` |
| H11 | « les 4 mutateurs sans garde » | Déjà traité (ADR-256 §C : classification) ; **mais la classification n'a pas fermé la porte** : 13 outils mutation restent sans confirmation (sim. 1) | ci-dessous |

### Simulation 1 — mutateurs natifs sans aucune porte (catalogue chargé dans le registre global)

`activate_hue_scene_tool`, `control_hue_light_tool`, `control_hue_room_tool`,
`apply_labels_tool`, `remove_labels_tool`, `complete_task_tool`,
`toggle_scheduled_action_tool`, `browser_task_tool` (agit sur des pages web),
`edit_image`, `generate_image`, `generate_document`, `import_user_skill`,
`run_skill_script` — tous `pipeline`+`react`, aucun `hitl_required`, aucun
brouillon. Le commentaire de la porte d'approbation (« every mutation tool has
its own downstream HITL », `approval_gate_node.py:112-114`) est faux pour ces
13 outils. Plusieurs sont **légitimement** non confirmés (réversibles,
artefacts locaux, bac à sable) : le défaut est que l'exemption n'est
**déclarée nulle part** et qu'aucune garde ne peut donc distinguer une
exemption voulue d'un oubli — la classe de défaut d'ADR-256 §C, un cran plus
haut.

### Simulation 2 — la même confirmation exécutée deux fois (3 tests, verts)

`test_router_reset_omits_draft_action_result`,
`test_response_node_clears_only_in_final_return`,
`test_same_confirmation_executes_twice` (exécuteur compté : 2 appels pour un
seul `draft_action_result`). Fenêtre réelle : tout ce qui lève dans
`response_node` après `_execute_draft_if_confirmed` (synthèse LLM, timeout,
kill), **y compris les exceptions attrapées** : le repli
`_response_error_fallback` ne rend que `messages`. Le checkpoint garde
`confirm`, le routeur ne le purge pas, le tour suivant renvoie l'email.

### Simulation 4 — la même chose au niveau du graphe (1 test, vert)

`StateGraph(MessagesState)` réel + `InMemorySaver` : un nœud écrit `confirm`
(comme `hitl_dispatch`), le nœud suivant appelle le vrai
`_execute_draft_if_confirmed` puis lève (comme une synthèse LLM en échec).
`aget_state` montre `confirm` conservé ; l'invocation suivante, avec un
message sans rapport (« merci »), exécute l'envoi une deuxième fois :
`CALLS == ["S", "S"]`.

### Simulation 3 — le sous-agent reçoit des mutateurs

Le validateur accepte `send_email_tool,control_hue_light_tool,...` (forme
seule) ; `resolve_tools_for_subagent` rend `activate_hue_scene_tool,
browser_task_tool, control_hue_light_tool, delete_task_tool,
toggle_scheduled_action_tool` — sur un fil isolé où aucun HITL ne fonctionne
(mémoire `reference_skill_subagent_no_hitl`).

### Simulation 5 — le pipeline exécute un outil `hitl_required=True` sans interruption (1 test, vert)

Catalogue réel chargé dans le registre global, un manifeste cloné de
`get_tasks_tool` avec `tool_category="update"` et
`PermissionProfile(hitl_required=True)` (`requires_tool_approval` rend bien
`True`), un `StructuredTool` enregistré sous le même nom, puis
`parallel_executor._execute_tool(...)` : l'outil s'exécute (`CALLS == [{"x": 7}]`),
aucune `GraphInterrupt`, aucune consultation d'approbation. C'est exactement le
chemin d'un outil MCP dont le serveur exige la confirmation, en mode pipeline.

Les cinq outils que la simulation 1 désigne comme les plus sensibles ont été
lus : `complete_task_tool` (`client.complete_task`), `apply_labels_tool`
(`client.resolve_label_with_disambiguation`), `toggle_scheduled_action_tool`
(docstring « direct — reversible, no draft »), `hue_tools.py` et
`browser_tools.py` (zéro occurrence de `requires_confirmation`/`DraftService`).

### Défaut bloquant pré-existant, hors périmètre — RÉSOLU le 2026-09-03

Au moment de l'analyse, `alembic heads` levait `CycleDetected` : la migration
non suivie de la bibliothèque de modèles réutilisait l'identifiant
`d9e0f1a2b3c4` d'une migration du 2026-08-08. La session ADR-259 l'a
réattribuée (`e0f1a2b3c4d5`, tête unique vérifiée). Toute migration de ce
programme s'enchaîne donc sur `e0f1a2b3c4d5`.

## 2. La matrice demandée — colonne LIA, aujourd'hui

| Frontière | Ce que LIA garantit | Par quoi | Ce qui reste indémontrable |
|---|---|---|---|
| INTENT → AUTHORITY | L'acteur est un utilisateur authentifié par cookie de session ; `LiaRuntimeContext.user_id` unique, non checkpointé ; `is_automated_source` distingue les runs non tapés | `core/session_dependencies.py`, `context/runtime_context.py` | Un run planifié/heartbeat/sous-agent porte **toute** l'autorité de l'utilisateur, jamais un sous-ensemble (`derive_sub_agent_context` ne change que `thread_id`) |
| AUTHORITY → PLAN | Le plan est un DSL validé structurellement + sémantiquement ; scopes, rôles, HITL calculés | `orchestration/validator.py` | Le verdict n'engage rien : un plan rejeté s'exécute (doctrine ADR-184, voulue) ; l'absence de verdict vaut approbation (H3) |
| PLAN → CAPABILITY | Catalogue unique, catégorie déclarée ou déduite d'une convention, complétude au boot (ADR-256) ; annotations MCP tierces jamais crues quand elles relâchent (ADR-255) | `registry/catalogue.py`, `mcp/registration.py:420-465` | La **politique de mutation** (confirmer / réversible / artefact / bac à sable) n'existe pas comme donnée |
| CAPABILITY → EXECUTION | Brouillon HITL pour 18 outils ; interrupt ReAct pour `hitl_required` ; sous-agent délégué confirmé ; conteneur jetable pour tout code | `hitl_dispatch_node.py`, `react_nodes.py:717-760`, `skills/executor.py` | Pipeline : 13 natifs + tout outil MCP `hitl_required` s'exécutent sans confirmation (H2) ; sous-agent : liste manuelle (H6) |
| EXECUTION → RESULT | Résultat typé `ToolResponse`/`ToolErrorCode` ; `success: false` n'est pas une production (ADR-248) ; timeouts bornés dans les deux modes (ADR-256) | `tools/common.py`, `orchestration/step_timeouts.py` | Pas de « claim avant effet » : un effet peut avoir eu lieu sans qu'aucun enregistrement ne le dise (H4, H5) |
| RESULT → EVIDENCE | Trace i18n persistée, widgets, `TokenUsageLog` par appel LLM, `PeerAccessLog` pour les accès pairs, journal d'audit de conversation (cycle de vie) | `streaming/trace_capture.py`, `chat/models.py`, `peers/models.py:318` | Aucun enregistrement d'effet : outil, empreinte d'arguments, approbation, résultat, référence fournisseur (H7) |
| EVIDENCE → VERDICT | La réponse ne peut annoncer un blocage que si la capacité n'a rien produit (`executed_tool_names`) ; provenance tierce marquée jusqu'au compacteur (ADR-257) | `services/plan_blockers.py` | Impossible de répondre après coup à « cet envoi a-t-il été fait sous cette approbation-là ? » autrement qu'en lisant un checkpoint mutable et fenêtré |

## 3. Approches envisagées

**A — Déclaration seule.** Ajouter `mutation_policy` aux manifestes, une garde
de complétude, corriger la porte (H3). Ferme H1/H3/H11, ne ferme ni la
consommation (H4/H5) ni la preuve (H7). Coût faible, insuffisant seul.

**B — Registre des effets (ledger) + claim avant effet.** Une table
append-only `agent_effects` : une ligne par effet externe, réclamée **avant**
l'effet, close par un résultat explicite. Donne consommation, idempotence,
preuve, et le refus structurel d'un rejeu. Ferme H4/H5/H7/H8. Ne dit pas quel
outil doit être confirmé.

**C — Un seul point de passage d'autorisation à l'exécution.**
`authorize_effect()` appelé par les trois exécuteurs (étape pipeline, appel
ReAct, brouillon confirmé), qui lit la politique déclarée et le registre.
Ferme H2/H6 dans les deux modes. Sans A, il n'a rien à lire ; sans B, il ne
peut pas refuser un rejeu.

**Recommandation : A + B + C, dans cet ordre, en quatre lots** — chacun
livrable et testable seul, aucun ne bloque l'autre au-delà de la dépendance
naturelle (C lit A et B).

Écarté : un graphe de provenance hashant plan, prompts, sorties et rapports.
Le checkpoint LangGraph est déjà l'état de référence ; hasher chaque artefact
ajoute du coût sans changer une décision. Les identités stables utiles se
limitent à ce qui manque : empreinte HMAC de l'opération (primitive existante),
référence fournisseur du résultat, `app_version` et mode d'exécution par run.
Écarté aussi : ressusciter l'approbation au niveau du plan (retirée en
v1.14.5 pour double confirmation, ADR-092).

## 4. Conception

### 4.1 Politique de mutation déclarée (lot 0)

`PermissionProfile.mutation_policy: MutationPolicy | None` avec
`MutationPolicy = Literal["confirm", "reversible", "artefact", "sandboxed"]`
et `mutation_policy_reason: str | None` (obligatoire pour toute valeur autre
que `confirm`).

- `confirm` : brouillon ou interruption avant effet, **dans les deux modes**.
- `reversible` : effet externe annulable en un appel (labels, tâche complétée,
  bascule d'action planifiée, lumières) — exécuté sans confirmation, journalisé.
- `artefact` : produit local pour l'utilisateur, aucun effet chez un tiers
  (image, document).
- `sandboxed` : code exécuté dans le conteneur jetable SEC-001.

Règle : **un manifeste non lecture seule (`is_read_only_tool` faux) doit
porter une politique explicite ou être producteur de brouillon** ; la
déduction par convention de nommage n'est jamais une politique.
`assert_mutation_policy_completeness()` refuse de démarrer sinon (patron
ADR-085/256, appelé depuis `run_failfast_validations` **et** un test). Un outil
MCP tiers reçoit `confirm` si le serveur est `hitl_required`, sinon la
politique dérivée d'ADR-255 (`delete`/`update` déclaré → `confirm`), sinon
`reversible` seulement si `readOnlyHint` faux ET `destructiveHint` faux — jamais
plus permissif que la déclaration.

**Règle arrêtée par le propriétaire (2026-09-03)** : une confirmation est due
pour une mutation qui *modifie*, *supprime* ou *communique vers un tiers* ;
jamais pour une lecture ; et sans paranoïa — ni les lumières, ni le navigateur
ne doivent faire pleuvoir des cartes sur l'utilisateur. Affectation des 13 :
`reversible` → `activate_hue_scene_tool`, `control_hue_light_tool`,
`control_hue_room_tool`, `apply_labels_tool`, `remove_labels_tool`,
`complete_task_tool`, `toggle_scheduled_action_tool`, `import_user_skill`,
`browser_task_tool` (raison consignée dans le manifeste : navigation et
formulaires sous le contrôle visible de l'utilisateur ; une soumission vers un
tiers passe par un brouillon si un tel outil apparaît un jour) ; `artefact` →
`generate_image`, `edit_image`, `generate_document` ; `sandboxed` →
`run_skill_script`, `run_python_tool`. Aucun natif ne reçoit `confirm` par ce
lot : les 18 outils à brouillon le sont déjà, et c'est la règle ci-dessus, pas
une liste, que la garde de complétude applique à tout nouveau manifeste.

Porte d'approbation (H3) : sans `validation_result`, `PLAN_APPROVED=False` avec
raison `no_verdict` — et comme le routeur n'agit pas sur le verdict, c'est le
point de passage (4.3) qui refuse les effets `confirm` d'un plan sans verdict.
`unknown` cesse de valoir `pass`.

### 4.2 Registre des effets (lot 1)

Table `agent_effects` (nouveau bounded context `domains/agents/effects/`,
modèles enregistrés aux trois endroits, migration Alembic, `ondelete=CASCADE`
sur `user_id`) :

| Colonne | Rôle |
|---|---|
| `id`, `created_at`, `updated_at` | UUIDMixin/TimestampMixin, UTC |
| `user_id`, `conversation_id`, `thread_id`, `run_id` | ancrage (même clé que `TokenUsageLog`) |
| `source` | `user` / `scheduled` / `heartbeat` / `initiative` / `sub_agent` (Enum) |
| `execution_mode` | pipeline / react |
| `tool_name`, `operation_digest` | `compute_call_digest(tool, args, secret_key)` — jamais les arguments bruts (PII) |
| `draft_id`, `draft_digest` | pour un brouillon : id + empreinte du `draft_content` affiché |
| `policy` | la `MutationPolicy` appliquée |
| `approval_kind`, `approval_ref`, `approved_at` | `draft_critique` / `tool_confirmation` / `for_each` / `none` ; `message_id` de la carte ou `tool_call_id` |
| `status` | `CLAIMED` → `SUCCEEDED` / `FAILED` / `REFUSED` / `ABANDONED` |
| `attempt`, `retry_of` | numéro de tentative, lien vers l'effet rejoué |
| `provider_ref` | identifiant rendu par le fournisseur (message_id Gmail, event_id…) |
| `result_digest`, `error_code` | empreinte du résultat, `ToolErrorCode` |
| `app_version`, `catalogue_fingerprint` | configuration C : version LIA + empreinte des manifestes chargés |

Contrat (règles systémiques « Persistence ») :

- **Claim avant effet** : `INSERT … ON CONFLICT (thread_id, idempotency_key) DO NOTHING RETURNING` ; clé = `tool_call_id` (ReAct), `draft_id` (brouillon), `step_id+run_id` (pipeline). Pas de ligne rendue → lire la ligne existante : `SUCCEEDED` → **ne pas rejouer**, rendre le résultat consigné ; `CLAIMED` plus vieux que la borne de l'outil → `ABANDONED` puis nouveau claim ; `FAILED` → nouveau claim avec `retry_of`. La clé `tool_call_id` ferme au passage le rejeu ReAct « avant interruption » (H4) : à la reprise, l'appel déjà `SUCCEEDED` est servi depuis le registre au lieu d'être réexécuté, et son `ToolMessage` est reconstruit à partir du résultat consigné. Cela impose une colonne de plus que la table ci-dessus ne listait pas : `result_payload` **chiffré** (`encrypt_data`, comme toute PII en base), à côté de `result_digest` qui le vérifie — sans elle un rejeu ne pourrait rendre au modèle que « déjà exécuté », pas la donnée dont il a besoin. Décision propriétaire n° 6 (§7).
- **Un statut terminal ne vient que d'un résultat explicite** (`success: true` + `provider_ref` si l'outil en rend un). Une exception après l'appel fournisseur : le registre ne sait pas si l'effet a eu lieu ; il note `FAILED` avec `error_code` et **le rejeu automatique est refusé** tant qu'un humain n'a pas redonné l'autorité (le point de l'interlocuteur : geler, classifier, réobtenir).
- Session propre par écriture (`get_db_context()`), jamais la session du tour ; écriture **avant** l'appel fournisseur, mise à jour **après**, dans deux transactions courtes.
- Échec du registre lui-même : `confirm` → refus (fail-closed, message technique anglais au modèle, le modèle reformule) ; `reversible`/`artefact`/`sandboxed` → l'effet passe et l'échec est compté (`agent_effect_ledger_failures_total`) — notre propre registre ne doit pas être la raison d'un échec pour un effet que l'utilisateur n'avait pas à confirmer.

### 4.3 Point de passage unique (lot 2)

`effects/gate.py::authorize_effect(tool_name, args, *, runtime_context, approval) -> EffectTicket | EffectRefusal`, appelé par :

1. `parallel_executor` avant chaque étape TOOL non lecture seule ;
2. `react_execute_tools_node` juste après l'interrupt (à la place du bloc
   « Execute tool ») ;
3. `draft_executor._execute_confirmed_draft` / `_execute_confirmed_batch`.

Décision, dans l'ordre : politique déclarée (4.1) → source (`scheduled`,
`heartbeat`, `initiative`, `sub_agent` + `confirm` → **refus avant tout
effet**, plus d'interruption orpheline puis `RuntimeError` après travail
partiel) → approbation liée (brouillon : `draft_id` + `draft_digest` égal au
contenu affiché ; ReAct : `tool_call_id` ; pipeline non-brouillon : voir
ci-dessous) → claim (4.2). Le ticket porte l'id de ligne ; l'exécuteur le clôt.

**Pipeline, outil `confirm` sans brouillon (MCP `hitl_required` ou déclaré destructif, et tout futur natif `confirm`)** :
compléter le chemin **mort** existant plutôt qu'en créer un — le producteur
(`PendingDraftInfo(draft_type="tool_confirmation", draft_content={tool, args})`
depuis l'exécuteur, comme `task_orchestrator_node.py:1049` l'attend) et le
consommateur (un exécuteur générique `tool_confirmation` dans
`EXECUTOR_REGISTRY` qui ré-invoque l'outil avec les arguments approuvés, sous
ticket). `hitl_dispatch_node._handle_tool_confirmation` et
`ToolConfirmationInteraction` existent déjà et rendent la carte.

### 4.4 Sources non humaines et sous-agent (lot 2)

- Liste blanche du sous-agent validée **au boot contre le catalogue** : tout
  nom dont le manifeste n'est pas lecture seule est refusé
  (`_validate_research_tools_whitelist_format` reste, une seconde validation
  lit le registre dans `run_failfast_validations`). La liste manuelle
  `SUBAGENT_DEFAULT_BLOCKED_TOOLS` devient dérivée du catalogue (règle
  « jamais une table de domaine maintenue à la main »).
- Exécuteur d'actions planifiées : avant la tentative N>1, lire le registre du
  `run_id` de la tentative N-1 ; un effet `SUCCEEDED` ou `FAILED` → pas de
  rejeu, action marquée en erreur avec un motif i18n ×6 et notification ;
  sinon rejeu comme aujourd'hui.
- Élection de leader : renouvellement et libération conditionnels au
  `worker_id` (script Lua, comme `refresh_active_run`). Risque réel faible
  (une instance) ; corrigé parce que c'est une autorité sans preuve de
  possession et une règle systémique écrite.

### 4.5 Surface de preuve (lot 3)

- Le message assistant archivé reçoit `effects: [ids]` (enrichisseur
  branch-free, patron `with_persisted_trace`).
- `GET /agents/effects?conversation_id=&run_id=` (propriétaire seulement,
  `check_resource_ownership(hide_existence=True)`), pagination
  `tuple[list, int]`, **total exact** (règle « un compte est exact ou n'existe pas »).
- Panneau debug : section « Effects » (statut, politique, approbation,
  fournisseur) — pas d'arguments (le registre n'en a pas).
- `trace_tool_call` : supprimé (code mort) ; `calculate_prompt_hash` : soit
  utilisé pour `catalogue_fingerprint`/empreinte du jeu de prompts, soit
  supprimé — ADR court.
- Métriques : `agent_effects_total{policy,source,outcome}`,
  `agent_effect_replays_refused_total{reason}`,
  `agent_effect_ledger_failures_total{operation}` ; un panneau Grafana chacun
  avec `or vector(0)` (ratchet `test_metric_coverage_ratchet_guard`).

### 4.6 Registres exportables (lot 3b — besoin propriétaire du 2026-09-03, affiné)

Le registre n'a de valeur que s'il **sort** : pour l'utilisateur qui veut
contre-vérifier et apprendre, pour l'administrateur qui veut diagnostiquer et
optimiser sur un volume que seul un modèle lit. Deux produits, une même table,
deux niveaux de contenu.

### Le registre lisible

- **Ce qu'il montre** : une ligne par effet, dans l'ordre du temps, dans le
  fuseau d'affichage de l'utilisateur, en Markdown (et CSV) : quand, à la
  demande de qui (`source`), quel outil, **quoi** (un libellé court), sous
  quelle autorité (brouillon confirmé / carte / politique déclarée), avec quel
  résultat (référence fournisseur, succès, échec avec motif, refus, abandon),
  et le lien vers la conversation. Un en-tête par jour, un total exact par
  période.
- **Le libellé est construit, jamais improvisé** : un registre de
  constructeurs par outil (`EFFECT_LABEL_BUILDERS`, assert de complétude au
  boot, ADR-085) rend une phrase courte à partir des arguments au moment du
  claim (« Email envoyé à M. D., objet “Devis” » ; « Lampe Salon éteinte » ;
  « Tâche “Appeler la banque” terminée »). Il est **chiffré** au repos
  (`encrypt_data`, colonne `label`), comme le résultat, et rendu dans la
  langue de l'utilisateur au moment de l'export (clés i18n ×6 + valeurs
  brutes, jamais une phrase figée en base).
- **Pour l'utilisateur** : page « Journal des actions » (réglages), filtres
  période / outil / statut, pagination à total exact (ADR-185), bouton
  « Exporter » sur la période ; et **inclus dans l'export de compte** existant
  (`account_export`, table `agent_effects` ajoutée à `exportable_tables()`,
  rendu Markdown par `_render_markdown`).
- **Pour l'administrateur** : la même vue sur tous les utilisateurs, mais les
  libellés, références fournisseur et identités sont **masqués par défaut**
  ; un « dévoiler » explicite, par utilisateur et par période, est lui-même
  consigné dans `AdminAuditLog` (un accès croisé est un fait qu'on journalise,
  comme `PeerAccessLog`). Le doute ne dévoile jamais.

### Le registre technique

- **Ce qu'il contient** : toutes les colonnes, une ligne par effet, en
  **JSON Lines** (une ligne = un objet, streamé depuis un curseur serveur,
  jamais chargé en mémoire — la classe de bug « streaming qui charge tout »
  est documentée), plus un **dictionnaire de données** (`schema.json`) et un
  en-tête de contexte (instance, version, période, filtres, compte exact)
  pour qu'un modèle sache ce qu'il lit sans qu'on le lui explique.
- **Filtres** : période, utilisateur(s), outil, politique, statut, source,
  mode d'exécution, `run_id` ; tri par `claimed_at`.
- **Pseudonymisé par construction** : `user_id` → HMAC(`secret_key`) stable
  (les statistiques par utilisateur restent possibles, l'identité non) ;
  `label` et `result_payload` **absents** ; `provider_ref` remplacé par son
  empreinte ; `thread_id`/`run_id`/`tool_call_id` conservés (identifiants
  techniques, pas des personnes). Un mode « nominatif » n'existe pas dans ce
  registre : qui veut un nom passe par le registre lisible et son
  dévoilement journalisé.
- **Livraison** : export admin par le socle ADR-228 (même page, même
  téléchargement), asynchrone au-delà d'un seuil de lignes lu dans
  `Settings` (patron du job `account_export` : `pending → running → ready`,
  balayage d'expiration, notification), synchrone en dessous.

### Ce qui n'est pas PII et ce qui l'est

| Colonne | Registre lisible (utilisateur) | Registre lisible (admin) | Registre technique |
|---|---|---|---|
| `label` (chiffré) | en clair, sa langue | masqué, dévoilement journalisé | absent |
| `provider_ref` | en clair | masqué | empreinte |
| `result_payload` (chiffré) | jamais exporté | jamais exporté | absent |
| `user_id` | implicite | pseudonyme + dévoilement | pseudonyme HMAC |
| `args_digest`, `draft_digest`, `result_digest` | absents | absents | présents |
| `tool_name`, `mutation_policy`, `status`, `source`, `execution_mode`, `error_code`, horodatages, `retry_of`, `catalogue_fingerprint` | présents | présents | présents |

Deux gardes CI : un test qui exporte une ligne complète en technique et
vérifie qu'aucune valeur du libellé, du résultat ni de la référence
fournisseur n'y apparaît (ni en clair, ni chiffrée) ; un test de complétude
de `EFFECT_LABEL_BUILDERS` sur le catalogue chargé.

**Valeur ajoutée** : le registre lisible est ce que l'utilisateur peut
opposer et ce dont il apprend ; le registre technique est ce qu'un modèle
peut lire par millions de lignes pour dire où l'assistant refuse trop,
rejoue, échoue, ou coûte — sans jamais voir une personne.

## 5. Plan d'actions consolidé

| Lot | Contenu | Dépend de | Régression surveillée |
|---|---|---|---|
| **0 — Doctrine** | `mutation_policy` + raison sur les 13 manifestes et MCP ; assert de complétude au boot + test ; porte d'approbation `no_verdict` ; doc (HITL.md : la porte est « pass-through auto-approve » et le pipeline ignore `hitl_required` — vrai, mais la conséquence pour un outil MCP `hitl_required` n'y est pas dite ; AGENT_MANIFEST.md ; GUIDE_TOOL_CREATION.md) — note : `interactions/destructive_confirm.py` existe bien, une lecture antérieure de cette analyse l'avait déclaré absent à tort | aucune (Alembic à tête unique `e0f1a2b3c4d5` depuis le 2026-09-03) | `test_hitl_required_consistency`, ratchet taille (`catalogue.py`), `lint:docs` |
| **1 — Registre** | Modèles, migration, repository (claim/close/replay), `compute_call_digest` réutilisé, tests d'intégration DB à deux acteurs | 0 | `db:migrate:replay-check`, garde JSONB, garde timezone, 3 enregistrements de modèles |
| **2 — Point de passage** | porte enveloppant `StructuredTool.coroutine` à l'enregistrement (`_register_tool`, `register_external_tool`) et chaque exécuteur de brouillon (`register_executor`) — §9.1 ; `EffectScope` (ContextVar) posé par les 3 exécuteurs ; `assert_effect_gate_completeness` boot + CI ; chemin `tool_confirmation` complété ; sources non humaines ; liste blanche sous-agent dérivée de la politique ; leader Lua ; i18n ×6 du motif d'échec planifié | 0, 1 | rejeu HITL (`test_hitl_dispatch_replay`, `test_for_each_confirm_replay`), idempotence ReAct, `tests/agents/` (angle mort connu : lancer explicitement), ratchets taille (`parallel_executor.py`, `react_nodes.py`, `response_node.py` gelés → tout en nouveaux modules) |
| **3 — Preuve** | métadonnées message, endpoint, section debug, six métriques + tableau `28-effect-ledger.json` + un panneau dans `08-hitl.json` + deux alertes avec runbooks (§8.3), suppression code mort, ADR-263, ARCHITECTURE_AGENT.md, DATABASE_SCHEMA.md, OBSERVABILITY_AGENTS.md, SECURITY.md (chaîne d'autorité), CLAUDE.md (2 règles systémiques) | 1, 2 | ratchet métriques, `lint:i18n`, `lint:docs`, couverture front (nouvelle section) |
| **3b — Registres** (§4.6) | `EFFECT_LABEL_BUILDERS` + assert ; page « Journal des actions » (liste paginée, filtres, export Markdown/CSV) ; `agent_effects` dans l'export de compte ; vue admin masquée + dévoilement journalisé (`AdminAuditLog`) ; export technique JSONL + `schema.json` pseudonymisé (socle ADR-228, asynchrone au-delà du seuil) ; i18n ×6 des libellés | 1, 2 | garde « aucune PII dans le technique », complétude des constructeurs, `lint:i18n`, couverture front, taille de l'export (`ExportTooLargeError` existant) |

Chaque lot : TDD inline, `task lint` + `task test:backend:unit:fast` (+
`test:frontend` au lot 3), preuve runtime Docker (`lia-api-dev`) : un envoi
d'email confirmé puis un crash forcé du nœud de réponse → **un seul** envoi ;
une action planifiée qui bascule une lumière puis expire → **pas** de second
effet ; un outil MCP `hitl_required` en pipeline → carte de confirmation.

## 6. Plan de test (enrichi pendant l'implémentation, déroulé en revue)

**Gardes structurelles (CI)** — `assert_mutation_policy_completeness` sur le
catalogue par défaut ET tous drapeaux allumés (anti-vacuité `> 96`) ;
`assert_effect_gate_completeness` (tout outil non lecture seule de
`get_all_tools()` et tout exécuteur de `EXECUTOR_REGISTRY` porte
`__effect_gated__`, sur les deux catalogues) ; `test_hitl_required_consistency`
dérivé ; `test_subagent_tools_never_mutate` (le résolveur filtre par
politique, quelle que soit la liste) ; garde « aucune PII dans l'export
technique » ; complétude `EFFECT_LABEL_BUILDERS` ; round-trip `EffectScope`.

**Consommation / idempotence** — la sim. 2 devient un test permanent
**inversé** (deuxième exécution refusée, résultat consigné rendu) ; brouillon
édité → nouveau digest → nouveau claim ; lot `CONFIRM_BATCH` → une ligne par
item, même approbation ; rejeu ReAct après interrupt → zéro double claim ;
claim `CLAIMED` périmé → `ABANDONED` puis nouveau claim ; deux acteurs
(intégration PostgreSQL) sur la même clé → un seul gagne.

**Autorité** — plan sans verdict + effet `confirm` → refus ; source
`scheduled` + `confirm` → refus avant effet, aucune interruption dans le
checkpoint ; MCP `hitl_required` en pipeline → `tool_confirmation` puis
exécution sous ticket après confirm, rien après cancel ; `reversible` sous
`scheduled` → exécuté et journalisé ; échec du registre : `confirm` refusé,
`reversible` passé + compteur.

**Reprise** — action planifiée : tentative 2 après effet `SUCCEEDED` en
tentative 1 → pas de rejeu, motif i18n ×6, notification ; sans effet →
rejeu ; `recover_stale_executing` idem.

**Registres (§4.6)** — export technique d'une ligne complète : aucune
sous-chaîne du libellé, du résultat ni de la référence fournisseur, en clair
ou chiffrée, n'apparaît dans le JSONL ni dans `schema.json` ; `user_id`
pseudonymisé stable (deux exports, même pseudonyme) ; complétude de
`EFFECT_LABEL_BUILDERS` sur le catalogue chargé ; libellé rendu dans les six
langues (clé + valeurs, `lint:i18n`) ; export utilisateur = ses lignes
seulement (`hide_existence=True` sur un `run_id` étranger) ; dévoilement admin
→ une ligne `AdminAuditLog` par (utilisateur, période) ; export de compte
contient `agent_effects` en JSON + Markdown ; au-delà du seuil, job
asynchrone `pending → running → ready`, expiration balayée, notification.

**Preuve** — endpoint : propriété, `hide_existence`, total exact, pagination ;
métadonnées message : ids présents après archive, absents sur un tour sans
effet ; round-trip sérialisation de toute structure passant par l'état.

**Non-régression** — suites HITL rejouables, `tests/agents/`, e2e HITL
hermétique (Chromium) sur brouillon email + carte `tool_confirmation` ;
`task ci:fast` avant tout push.

## 7. Décisions propriétaire — PRISES le 2026-09-03

1. **Périmètre : les quatre lots**, livrés en deux releases (lots 0 et 1 sans
   changement de comportement visible, puis lots 2 et 3).
2. **Politique** : confirmation pour une mutation qui modifie, supprime ou
   communique vers un tiers ; jamais pour une lecture ; ni Hue ni navigateur
   (« l'utilisateur ne doit pas être spammé »). Affectation en §4.1.
3. **Échec du registre** : `confirm` refusé ; `reversible`/`artefact`/
   `sandboxed` passent et sont comptés.
4. **Alembic** : plus d'arbitrage, tête unique `e0f1a2b3c4d5`.
5. **Rétention** : jusqu'à suppression du compte, résultat chiffré purgé au
   même moment.
6. **Résultat d'outil** : conservé chiffré (`encrypt_data`) pour servir un
   rejeu ReAct sans réexécuter.
7. **Changement de comportement visible** (carte pour un outil MCP
   `hitl_required` en pipeline, refus explicite avant effet pour une action
   planifiée) : accepté, à annoncer dans la note de version et la doc HITL.
8. **Expérience croisée** : le scénario partagé est documenté après le lot 2,
   frontières et garanties seulement, aucun inventaire privé.

## 8. Exploitation — ce que le registre rend possible une fois livré

Le registre n'est pas une table de plus : c'est la source des **faits**
d'effet, là où l'état LangGraph ne porte que des *verdicts* et des
*intentions*. Quatre consommateurs, par ordre de livraison :

1. **La réponse dit ce qui a été fait, pas ce que le modèle croit avoir
   fait.** Le nœud de réponse reçoit la liste des effets `SUCCEEDED` du run
   (outil, référence fournisseur, horodatage) dans une directive versionnée,
   exactement comme `plan_blockers` lui donne aujourd'hui les capacités
   bloquées (ADR-184). Une phrase « l'email est parti » sans ligne `SUCCEEDED`
   devient impossible à produire honnêtement ; une ligne `FAILED` produit une
   phrase honnête. C'est la doctrine « un verdict n'est pas un fait » étendue
   aux effets.
2. **L'utilisateur voit, retrouve et emporte ses actions.** Une ligne
   « Actions effectuées » sous chaque bulle (les effets du run, référence
   cliquable quand le fournisseur en donne une), puis le **registre lisible**
   (§4.6) : page « Journal des actions » dans les réglages, paginée avec un
   total exact (ADR-185), filtrable, exportable en Markdown/CSV et incluse
   dans l'export de compte. Pour l'administrateur, la même vue sur tous les
   comptes, masquée par défaut, dévoilement journalisé. Et le **registre
   technique** : JSON Lines pseudonymisé avec son dictionnaire de données,
   filtrable par période/utilisateur/outil/statut, fait pour être lu par un
   modèle sur des millions de lignes — diagnostics, statistiques,
   optimisations — sans jamais voir une personne.
3. **Le système se surveille et se diagnostique.** Un tableau Grafana dédié,
   `28-effect-ledger.json`, parce que le registre pose ses propres questions
   opérationnelles et que le ratchet de couverture (`test_metric_coverage_ratchet_guard`)
   refuse toute métrique sans panneau, règle ou alerte — ce n'est pas une
   option. Six séries, toutes sans PII (labels bornés : `policy`, `status`,
   `source`, `execution_mode`, `reason` ; jamais `tool_name` libre d'un
   modèle) : `agent_effects_total{policy,status,source,execution_mode}`,
   `agent_effect_replays_avoided_total{execution_mode}` (chaque rejeu évité
   est une double mutation qui n'a pas eu lieu), `agent_effect_refusals_total{reason}`,
   `agent_effect_ledger_failures_total{operation}`, `agent_effects_unscoped_total{policy}`,
   `agent_effect_claim_duration_seconds` (histogramme, latence ajoutée par la
   porte). Deux alertes : `CLAIMED` orphelins (`abandoned` > 0 sur 15 min) et
   échecs du registre (> 0 sur 5 min), chacune avec son runbook. Les panneaux
   des compteurs rares portent `or vector(0)` et `"noValue": "0"` (piège
   ADR-148). Le tableau `08-hitl.json` gagne un seul panneau : approbations
   confirmées vs effets `SUCCEEDED` sur la même fenêtre — l'écart est le
   nombre d'approbations dont l'effet n'a pas été consigné, et il doit
   valoir zéro. **Le tableau répond « la porte est-elle saine ? » ; les
   registres (§4.6) répondent « que s'est-il passé ? » — deux surfaces,
   deux publics, jamais confondues.**
   L'auto-diagnostic (ADR-247) gagne une requête nommée « effets du dernier
   run » : quand un utilisateur demande « tu l'as vraiment envoyé ? », LIA
   répond depuis le registre, pas depuis sa mémoire de conversation.
4. **Les automatisations deviennent sûres par construction.** Une action
   planifiée relancée retrouve ses effets `SUCCEEDED` et ne les refait pas ;
   un tour ReAct repris après interruption sert le résultat conservé au lieu
   de réexécuter ; un sous-agent ne peut plus muter par oubli de liste.

Et deux suites naturelles, hors périmètre de ce programme mais rendues
possibles par la référence fournisseur consignée : **annuler la dernière action
réversible** (« rallume », « remets l'étiquette ») depuis la ligne du registre,
et le **scénario croisé** avec l'interlocuteur, où chaque frontière de la
matrice (§2) est désormais attestée par une ligne plutôt que par un log.

## 9. Maintenabilité — un registre de preuve ne vaut que s'il ne peut pas se désynchroniser

Un registre qui manque un effet ment par omission, et personne ne le voit. La
question n'est donc pas « avons-nous branché tous les appelants ? » mais
« un appelant oublié peut-il exister ? ». Trois décisions de conception,
chacune contre-vérifiée par simulation le 2026-09-03.

### 9.1 La porte vit à l'enregistrement de la capacité, pas chez ses appelants

Le plan initial prévoyait `authorize_effect` appelé par les trois exécuteurs
et une garde AST interdisant tout `coroutine(**` hors de la porte. C'est la
classe de garde qui pourrit le plus vite : un quatrième exécuteur, un outil
appelé depuis un service, un sous-agent nouveau, et la garde regarde
ailleurs. Mesuré : les deux exécuteurs actuels appellent
`tool.coroutine(**args)` directement (`parallel_executor.py:2714`,
`react_nodes.py:805`) et le runner de sous-agent passe par `ainvoke` —
trois chemins pour une capacité.

**Décision** : la porte enveloppe `StructuredTool.coroutine` **au moment de
l'enregistrement** (`tool_registry._register_tool`, par où passent les natifs
via `registered_tool` ET les adaptateurs MCP via `register_external_tool`),
et `EXECUTOR_REGISTRY` enveloppe de même chaque exécuteur de brouillon
(`register_executor`). Quel que soit l'appelant, l'effet traverse la porte.

- Sim. 6 : une coroutine remplacée sur un outil réel est atteinte par
  `tool.coroutine(**)` **et** par `tool.ainvoke(...)` (2 passages sur 2).
- Sim. 7 : `runtime_context_if_running()` rend le contexte du run depuis une
  coroutine d'outil appelée directement dans un nœud d'un graphe compilé
  avec `context_schema=LiaRuntimeContext` ; hors graphe, `None` — rien ne
  fuit.
- Ce que l'appelant sait et la porte non (clé d'idempotence, approbation,
  source) voyage par un `ContextVar` `EffectScope` posé par l'exécuteur autour
  de l'appel (patron `_CURRENT_SIDE_CHANNEL_QUEUE` de `draft_executor.py`).
  **Absence de scope = pas d'autorité** : un outil `confirm` appelé sans scope
  est refusé ; un `reversible` est exécuté sous une clé générée et compté
  (`agent_effects_unscoped_total`), jamais silencieux.
- La politique est lue **à l'appel**, depuis le registre global, pas capturée
  à l'enregistrement : les manifestes se chargent après les outils, et un
  outil sans manifeste (registre non initialisé) est traité comme `confirm`
  — le doute ferme.
- Une garde de boot + CI, `assert_effect_gate_completeness`, parcourt
  `get_all_tools()` et `EXECUTOR_REGISTRY` et refuse tout outil non lecture
  seule ou tout exécuteur dont la coroutine ne porte pas le marqueur de la
  porte (`__effect_gated__`). Elle remplace la garde AST.

### 9.2 Le catalogue de la CI est le catalogue de la production

`initialize_catalogue` enregistre huit familles derrière des drapeaux
(`telephony_enabled`, `devops_enabled`, `sub_agents_enabled`,
`python_sandbox_tool_enabled`, `image_generation_enabled`,
`document_generation_enabled`, `diagnostics_enabled`,
`health_metrics_enabled`). `place_phone_call_tool` — un appel téléphonique,
donc une communication vers un tiers — n'était pas dans les 119 outils de
la simulation 1 parce que le drapeau était éteint dans l'environnement de
mesure. Toute garde de complétude de ce programme s'exécute donc **deux
fois** en CI : sur le catalogue par défaut et sur le catalogue « tous
drapeaux allumés », avec l'assertion anti-vacuité de
`test_tool_category_completeness.py` (`len(manifests) > 96`). Le patron
existe déjà ; il devient obligatoire pour toute garde du registre.

### 9.3 Le schéma du registre évolue sans réécrire le passé

- `schema_version` (entier) sur chaque ligne : une colonne ajoutée porte une
  version, jamais un `NULL` ambigu ; l'export technique le publie dans
  `schema.json`, un modèle qui lit deux versions sait lesquelles.
- Migrations **additives seulement** sur `agent_effects` (une garde de
  revue, pas de code : le fichier ADR l'énonce, `db:migrate:replay-check`
  prouve le rejeu).
- `result_payload` est **plafonné** (`effect_result_payload_max_bytes`,
  `Settings`, défaut dans `core/constants.py`) et `result_truncated` le dit :
  un résultat d'outil peut peser des dizaines de kilo-octets, et un registre
  qui grossit sans borne finit purgé à la hache.
- Le vocabulaire est fermé et petit : `EffectSource` = `user | scheduled |
  subagent` (le heartbeat n'exécute aucun outil ; un pair ne mute jamais pour
  un autre — deux valeurs mortes retirées avant de naître), `EffectStatus` =
  cinq états, `MutationPolicy` = cinq valeurs.

### 9.4 Inventaire des gardes du programme

| Garde | Ce qu'elle refuse | Où elle tourne | Qui la casse si elle est fausse |
|---|---|---|---|
| `assert_mutation_policy_completeness` | un outil non lecture seule sans politique, une exemption sans raison, `hitl_required` sans `confirm` | boot (`init_agent_registry`) + CI (défaut et tous drapeaux) | l'auteur d'un manifeste |
| `assert_effect_gate_completeness` | un outil ou un exécuteur de brouillon non enveloppé | boot + CI | l'auteur d'un nouveau chemin d'enregistrement |
| `test_hitl_required_consistency` (dérivé) | un `draft` avec `hitl_required=True` | CI | l'auteur d'un manifeste |
| garde « aucune PII dans l'export technique » | une valeur de libellé/résultat/référence dans le JSONL | CI | l'auteur d'un exporteur |
| complétude `EFFECT_LABEL_BUILDERS` | un outil non lecture seule sans constructeur de libellé | boot + CI | l'auteur d'un outil |
| round-trip `EffectScope`/ticket | un champ ajouté d'un seul côté de la sérialisation | CI | l'auteur d'un champ |
| ratchet métriques | une métrique du registre sans panneau | CI | l'auteur d'une métrique |
| `db:migrate:replay-check` | une migration non rejouable | CI | l'auteur d'une migration |
| `lint:docs` (`doc_audit`) | un chemin de garde cité par l'ADR-263 qui n'existe plus | CI | qui renomme une garde |
| `test_demo_instance_exposed_routes` | une route du registre exposée au démonstrateur sans décision | CI | l'auteur d'une route |

La dernière ligne est la garde des gardes : l'ADR-263 cite chaque garde par
son chemin, et `doc_audit` refuse un chemin mort. Renommer une garde sans
mettre l'ADR à jour rougit la CI.

### 9.5 Vérifié hors périmètre, à ne pas rouvrir

- Sauvegarde : `pg_dump` du sidecar (ADR-109) couvre la base entière, donc
  la table.
- Suppression de compte : cascade sur `users.id`.
- Chiffrement : même clé Fernet que les autres PII ; la rotation est un
  sujet existant, pas un sujet nouveau.
- Limitation de débit des exports : `create_user_rate_limiter` (patron
  `account_export/router.py:34`).
- Démonstrateur : chaque nouvelle route est ajoutée à
  `EXPECTED_EXPOSED_ROUTES` ou explicitement refusée.
