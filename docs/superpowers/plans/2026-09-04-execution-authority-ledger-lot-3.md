# ADR-263 — Lot 3 : surface de preuve, registres exportables, observabilité

État : plan écrit le 2026-09-04, après vérification factuelle de chaque hypothèse.
Prérequis livrés et verts : lots 0 (politique déclarée), 1 (registre `agent_effects`),
2 (portail + demande de confirmation + sous-agent filtré par politique).

Ce plan ne contient aucune étape git : le propriétaire commite.

---

## 0. Ce que la mesure a changé par rapport à la spec

Sept hypothèses de la spec §4.6/§8 ont été vérifiées dans le code ce jour. **Quatre
étaient fausses ou incomplètes** et changent la conception.

| # | Hypothèse de la spec | Mesure | Conséquence |
|---|---|---|---|
| 1 | « socle ADR-228 » pour l'export technique | `infrastructure/tabular_io/` est un constructeur **XLSX** (openpyxl) pour l'aller-retour des tarifs. Aucun flux JSONL. | L'export technique **n'utilise pas** `tabular_io`. Il imite `account_export` : job + archive + `FileResponse`. |
| 2 | `requires_approval`, `requires_tool_approval`, `calculate_prompt_hash` sont morts | **Vivants** : `requires_approval` est lu par `task_orchestrator_node.py:494` et `parallel_executor.py:3615` (portée FOR_EACH) ; `requires_tool_approval` par `hitl_config.py:65,75` ; `calculate_prompt_hash` 3× dans `prompt_loader`. | **Ne rien supprimer** de ces trois. Seul `trace_tool_call` est mort (0 appelant réel). |
| 3 | Le registre couvrira « ce que l'assistant a fait » | Hors outils/exécuteurs, la seule écriture vers l'extérieur dans `src/domains/` est le relais push (`push_relay/service.py:183`) et les e-mails de sécurité d'`auth`. | Frontière à **écrire dans l'ADR** : le registre consigne ce qu'une **capacité** a fait dans un tour. Les notifications système et la tuyauterie interne (embeddings, sync, indexation) n'en sont pas. |
| 4 | La garde de complétude couvre les outils | `assert_mutation_policy_completeness(manifests)` parcourt les **manifestes**. **23 outils enregistrés n'ont aucun manifeste** et lui sont invisibles. | Aucun trou aujourd'hui (les deux modes sélectionnent par manifeste — `manifests_for_mode` — et le filtre sous-agent refuse tout ce qui n'est pas `read`), mais **faux négatif par construction** pour demain → nouvelle garde de domaine « registre ». |
| 5 | Les fichiers de la surface de preuve sont extensibles | Marges au plafond gelé : `api/service.py` **3**, `response_node.py` **5**, `agent_registry.py` **4**, `debug_metrics_builder.py` **7**, `metrics_agents.py` **11**, `task_orchestrator_node.py` **14**. | **Contrainte structurante** : tout code nouveau va dans des modules neufs ; ces fichiers ne reçoivent qu'un import + un appel. |
| 6 | Le coût du portail est négligeable | Mesuré : **0,64 µs** par lecture, **0 session** de base de données sur le chemin `PASS_THROUGH`. | Confirmé. Aucune optimisation nécessaire sur le chemin chaud. |
| 7 | L'export de compte doit être créé | `agent_effects` est **déjà** déclaré : `user_data_map.TABLE_RULES` (FULL, USER_PURGED), `account_deletion_service.py:119`, et `_DECRYPTED_COLUMNS` (`label`, `result_payload`). | Le lot 3b n'ajoute qu'un **rendu lisible**, pas la plomberie. |

Volumétrie réelle du registre (catalogue chargé dans le registre global) :
`draft` 24 · `read` 26 · `reversible` 11 · `artefact` 3 · `sandboxed` 2 · `confirm` 0
(les `confirm` sont les outils MCP tiers, enregistrés à l'exécution) ; **24 exécuteurs**
de brouillon écrivent des lignes. Le registre sera donc **peuplé** : ce sont les
24 exécuteurs et les 16 outils agissants qui l'alimentent.

---

## 0 bis. Seconde passe : six points que le plan lui-même n'avait pas vérifiés

Relecture adversariale du plan ci-dessus, le 2026-09-04. Deux points sont
confirmés, quatre corrigent la conception.

| # | Point | Mesure | Effet sur le plan |
|---|---|---|---|
| 8 | Identité du run : la mémoire signale `stream_id ≠ run_id` (ADR-117) | `FIELD_RUN_ID` **est** posé dans `configurable` au site de construction unique (`services/orchestration/service.py`), et `scope_from_config` le lit. | **Confirmé** : `list_for_run(run_id)` trouvera bien les effets du tour. |
| 9 | Index nécessaires au journal et au tour | Le lot 1 a créé `ix_agent_effects_user_claimed (user_id, claimed_at)` et `ix_agent_effects_run (run_id)`. | **Confirmé : aucune migration** dans le lot 3. |
| 10 | « une ligne d'appel dans `api/service.py` » pour « Actions effectuées » | Le patron réel est une **chaîne d'enrichisseurs sans branche** (`with_persisted_trace`, `with_followup_suggestions`, `with_initiative_motivation`) et le fichier n'a que **3 SLOC** de marge ; un quatrième appel en coûte ~4. | La chaîne entière est **extraite** dans un module neuf (`api/archive_metadata.py`) qui accueille le nouvel enrichisseur : le fichier gelé **rétrécit** au lieu de grossir. |
| 11 | Section de debug alimentée par le registre | `debug_metrics_builder.py` ne fait **aucune** I/O : ni `await`, ni session. Y lire la base romprait sa pureté synchrone. | Les effets sont **passés en argument** (lecture unique du tour, partagée avec « Actions effectuées »), jamais lus dans le constructeur. |
| 12 | Alerte « lignes `CLAIMED` orphelines > 15 min » | Prometheus ne voit pas des lignes de base. L'alerte n'avait **aucun producteur** — exactement la métrique aveugle que la doctrine interdit. | Jauge **adossée à la base**, sur le patron existant `lifetime_metrics.py` / `metrics_product.py`, rafraîchie par une boucle périodique à intervalle réglé par `Settings`. |
| 13 | Le front (directives `apps/web/CLAUDE.md`, non lues à la première passe) | « Les contrats back livrent des données structurées + des `label_key` résolus côté client — **jamais** de chaînes pré-traduites dans les charges utiles. » | Confirme `{i18n_key, values}` **et l'impose à l'API**. La table `core/i18n_effects.py` sert **uniquement l'export** (là où il n'y a pas de client) ; les mêmes clés vivent dans les 6 locales du front → **garde de parité** back/front à ajouter. |

### Obligations front qui en découlent (design system)

- Accès API par un **hook typé** `src/hooks/useEffectsJournal.ts` (`useApiQuery`), jamais `fetch`.
- Vide : `<EmptyState>`, `variant="page"` **exige** une action, et `reason` distingue
  « aucun effet encore » de « le filtre n'a rien trouvé ».
- Premier chargement : `<Skeleton>` à la géométrie réelle ; **rafraîchissement :
  `aria-busy`, jamais un démontage** (le piège documenté du `loading ? spinner : contenu`).
- Barre de section via `SectionToolbar`, actions de ligne via `RowActions`
  (jamais `opacity-0 group-hover`), altitudes d'action selon ADR-207.
- Titres avec icône en `text-primary` ; parité stricte des 6 locales ;
  nom accessible testé en anglais et en français.
- Validation runtime **dans le conteneur `lia-web-dev`**, jamais par un `pnpm build` local.

---

## 1. Lot 3a — la surface de preuve

### 3a-1 · Métriques (nouveau module)

`src/infrastructure/observability/metrics_effects.py` — six compteurs, **libellés
bornés, jamais `tool_name`** (cardinalité libre) :

| Métrique | Libellés | Question |
|---|---|---|
| `lia_effect_claims_total` | `policy`, `source`, `execution_mode` | combien d'effets réclamés |
| `lia_effect_outcomes_total` | `policy`, `status` | combien aboutis / échoués |
| `lia_effect_refusals_total` | `reason` | pourquoi le portail a refusé |
| `lia_effect_unrecorded_total` | `policy`, `reason` | effets exécutés sans trace (registre indisponible / pas d'identité) |
| `lia_effect_already_performed_total` | `served` (`record`\|`none`) | doublons évités, et si le résultat a pu être servi |
| `lia_effect_ledger_failures_total` | `operation` (`claim`\|`close`\|`refuse`) | santé du registre lui-même |

Émission dans `effects/runtime.py` uniquement (marge 302 SLOC).
Le ratchet de couverture découvre tout `*.py` (`rglob`) : chacune doit atteindre
un panneau, une règle ou une alerte — sinon build rouge. Compteurs rares :
`or vector(0)` + `"noValue": "0"`.

### 3a-2 · Tableau de bord et alertes

- `infrastructure/observability/grafana/dashboards/28-effect-ledger.json` (le dernier
  est `27-meetings.json`) — « le portail est-il sain ? »
- un panneau **approbations vs effets aboutis** dans `08-hitl.json`
- deux alertes avec runbooks : lignes `CLAIMED` orphelines > 15 min ; échecs de
  registre > 5 min. **Producteur de la première** : une jauge adossée à la base,
  sur le patron `lifetime_metrics.py` / `metrics_product.py`, rafraîchie par une
  boucle périodique (intervalle en `Settings`) — Prometheus ne voit pas des
  lignes, et une alerte sans producteur est précisément la métrique aveugle que
  la doctrine interdit.

### 3a-3 · Endpoint et section de debug

- Nouveau routeur `src/domains/agents/effects/router.py` : `GET /effects?run_id=…`,
  **portée utilisateur** (`check_resource_ownership`), limité par
  `create_user_rate_limiter`, réponse typée. Mise à jour de `EXPECTED_EXPOSED_ROUTES`
  (`tests/unit/test_demo_instance_exposed_routes.py`).
- Nouveau module de construction `effects/debug_section.py` + **une ligne** d'appel
  dans `debug_metrics_builder.py` (marge 7). Les effets lui sont **passés en
  argument** : ce constructeur ne fait aucune I/O aujourd'hui et ne doit pas
  commencer (mesuré : ni `await`, ni session).
- Front : `EffectsSection.tsx` dans `apps/web/src/components/debug/components/sections/`,
  type dans `DebugMetrics`, tests, clés i18n × 6.

### 3a-4 · « Actions effectuées » sous la réponse

Source de vérité = le registre, lu par `run_id` (`EffectLedgerRepository.list_for_run`,
déjà présent), jamais l'état LangGraph. Nouveau module `effects/turn_summary.py` ;
`response_node.py` ne reçoit qu'un import + un appel (marge 5).
Métadonnée de message sur le patron `FIELD_EXECUTION_TRACE` : un enrichisseur
**sans branche** (nouveau dict) appliqué à l'archivage. Comme `api/service.py`
n'a que 3 SLOC de marge, la chaîne existante (`with_persisted_trace`,
`with_followup_suggestions`, `with_initiative_motivation`) est **extraite** dans
`api/archive_metadata.py`, qui accueille le nouvel enrichisseur : le fichier gelé
rétrécit. L'API livre des `label_key` + valeurs, **jamais** de chaîne traduite
(règle `apps/web/CLAUDE.md`).
**À mesurer pendant l'implémentation** : la latence ajoutée par ce SELECT indexé.
Un indice `ContextVar` (« ce tour a-t-il réclamé quelque chose ? ») ne sera ajouté
que si la mesure le justifie — pas avant.

### 3a-5 · La garde de domaine « registre » (faux négatif n° 4)

Nouvelle garde : **tout outil enregistré possède un manifeste**, sinon il figure
dans une liste d'exemption *shrink-only* avec une raison écrite (idiome ADR-085 +
ratchet). Les 23 actuels y entrent avec leur raison mesurée (sous-outils du
navigateur pilotés par la boucle ; lecteurs hérités qu'aucun sélecteur n'atteint ;
`delete_file_tool`, qui construit un brouillon — l'effet est enregistré par
l'exécuteur `file_delete`).

### 3a-6 · Code mort — strictement ce qui est prouvé mort

> **Correction du 2026-09-04, en cours d'implémentation.** Le plan annonçait le
> chemin HITL `tool_confirmation` comme mort des deux côtés. **Faux.**
> `react_nodes.py:739` lève un `interrupt()` portant
> `hitl_type: HitlInteractionType.TOOL_CONFIRMATION` pour toute mutation : la
> classe d'interaction (270 lignes) et son entrée i18n sont **la carte de
> confirmation de ReAct**, bien vivante. Seules les clés d'état du PIPELINE
> (`pending_tool_confirmation`, `tool_confirmation_result`) n'ont aucun
> producteur — et le piège qu'elles représentaient est déjà fermé par un test
> du lot 2 (`test_pipeline_confirmation_plumbing` exige que le brouillon
> `tool_call` n'y aille pas). **Rien n'est supprimé de cette famille** :
> l'hygiène ne vaut pas le risque de toucher une machinerie HITL vivante pour
> ~40 lignes inatteignables déjà gardées.

- `infrastructure/llm/tool_tracing.py` (`trace_tool_call`) : 0 appelant réel.
- Chemin HITL `tool_confirmation` : producteur inexistant (`DraftType` n'a pas ce
  membre) et supplanté par `DraftType.TOOL_CALL` du lot 2. Suppression de la clé
  d'état, de la branche de routage, de l'interaction et de la vérification de
  compaction. **PIÈGE À NE PAS RATER** : la chaîne `"tool_confirmation"` est AUSSI
  le vocabulaire `approval_kind` du registre (`effects/scope.py:166`,
  `effects/models.py:138`) — elle doit survivre.
- **Ne pas toucher** `requires_approval`, `requires_tool_approval`,
  `calculate_prompt_hash` (mesurés vivants).

### 3a-7 · La décision reportée du lot 2

`export_for_prompt` publie `requires_approval = permissions.hitl_required`, **faux
pour les 24 outils à brouillon** : le planificateur lit qu'aucune confirmation
n'est due alors que l'utilisateur en verra une. Correction : dériver la valeur de
`mutation_policy` (`draft`/`confirm` ⇒ vrai). `agent_registry.py` n'a que 4 SLOC de
marge → la dérivation vit dans `registry/catalogue.py` et le registre l'appelle.

---

## 2. Lot 3b — les deux registres exportables

### 3b-1 · Le libellé, écrit au moment de la réclamation

- `core/i18n_effects.py` (**module de données**, exempt du ratchet de taille) :
  une entrée par libellé × 6 langues.
- `effects/labels.py` : `EFFECT_LABEL_BUILDERS` (16 outils agissants + 24 exécuteurs),
  assert de complétude au boot (`StartupCompletenessError`), **repli dérivé** pour les
  outils MCP tiers (`_readable_tool_name`) — même doctrine que la politique : les
  natifs déclarent, le tiers est dérivé.
- Stocké `{i18n_key, values}` dans `ClaimRequest.label` (colonne **déjà** créée et
  chiffrée), rendu **à l'export** dans la langue de l'utilisateur. La table back
  sert l'export SEUL (il n'y a pas de client) ; à l'écran, le front résout les
  mêmes clés depuis ses locales — d'où une **garde de parité** : toute clé
  d'effet du back existe dans les 6 fichiers de locale du front.

### 3b-2 · Registre lisible

- Rendu Markdown dans `account_export/builder.py` (marge 405) — en **table de
  dispatch**, à l'image de `preview_renderer._PREVIEW_RENDERERS`, plutôt qu'une
  quatrième branche d'une cascade `if`.
- Page « Journal des actions » (front) : période, outil, statut ; réutilise
  l'endpoint 3a-3 étendu.
- Vue admin tous comptes : **masquée par défaut**, dévoilement journalisé dans
  `AdminAuditLog`.

### 3b-3 · Registre technique

- **Pseudonymisé par construction** : `user_id` → HMAC(`secret_key`) ; `label` et
  `result_payload` **absents** ; `provider_ref` → empreinte.
- JSON Lines + `schema.json` + en-tête de contexte, livré comme l'export de compte
  (job + archive + `FileResponse`), asynchrone au-delà d'un seuil `Settings`.
- **Garde CI « aucune PII dans le technique »** : la garde lit les colonnes du
  modèle et échoue si une colonne non listée dans un ensemble autorisé apparaît
  dans la sortie — ainsi une colonne ajoutée demain ne fuit pas par défaut.

---

## 3. Plan de test — tel qu'implémenté

Le plan initial comptait 19 cas nommés. L'implémentation en a produit **11
fichiers** ; les écarts sont notés, car un plan de test qui ne bouge pas
pendant l'implémentation n'a pas été suivi.

**Unitaires — back**

| Fichier | Ce qu'il refuse |
|---|---|
| `effects/test_effect_metrics.py` | un compteur qui monte sur le mauvais chemin ; une lecture qui compte quoi que ce soit (anti-vacuité) |
| `observability/test_effect_metric_label_bounds.py` | un libellé non borné, un libellé non déclaré, plus de 3 libellés — lu dans l'AST, donc refusé avant le premier tir |
| `observability/test_effect_orphans_gauge.py` | un seuil codé en dur ; une jauge non publiée à zéro ; un appel non isolé dans la boucle (lu dans l'AST) |
| `effects/test_effect_labels.py` | un libellé manquant (les DEUX familles), une clé non traduite, un rendu qui lève sur une donnée d'une version antérieure |
| `effects/test_turn_summary.py` | un refus ou une réclamation ouverte présentés comme faits ; une phrase traduite dans la charge utile ; une panne de base qui coûterait la réponse |
| `effects/test_effects_router.py` | les lignes d'autrui ; un total dérivé de la page ; une route qui écrit |
| `effects/test_admin_router.py` | un non-superutilisateur ; un dévoilement non journalisé ; un masque qui saute hors FastAPI |
| `effects/test_technical_export.py` | **une colonne ajoutée demain qui fuirait** ; une colonne ni exportée ni interdite ; un identifiant en clair |
| `agents/test_registered_tool_declaration_guard.py` | un outil enregistré sans manifeste ni exemption écrite — mesuré dans un interpréteur NEUF |
| `registry/test_planner_sees_the_confirmation.py` | un outil à brouillon annoncé au planificateur comme silencieux |
| `api/test_archive_metadata.py` | une extraction qui change la métadonnée (caractérisation écrite AVANT le déplacement) |
| `account_export/test_effect_register_rendering.py` | un registre qui ne montrerait que les succès ; une langue figée à l'écriture |
| `streaming/test_debug_performed_effects.py` | un panneau qui interrogerait le registre lui-même au lieu du lecteur partagé |
| `startup/test_agents_startup_guards.py` (étendu) | **un assert qui tournerait contre un registre d'exécuteurs vide** ; une capacité sans libellé qui laisserait démarrer |

**Unitaires — front**

| Fichier | Ce qu'il refuse |
|---|---|
| `lib/__tests__/performed-effects-hydration.test.ts` | un statut non affichable ; une valeur non scalaire ; une charge utile malformée qui lèverait |
| `components/chat/__tests__/PerformedEffects.test.tsx` | une clé i18n affichée telle quelle ; un nom d'outil montré à l'utilisateur ; un bloc rendu pour un tour sans effet |
| `components/effects/__tests__/EffectsJournal.test.tsx` | un total dérivé de la page ; un rafraîchissement qui démonte la liste ; un filtre qui `disabled` le bouton cliqué ; une vacuité confondue avec un filtre sans résultat |
| `hooks/__tests__/useEffectsJournal.test.ts` | une page qui remplace au lieu d'accumuler ; un doublon entre deux pages ; un `firstLoad` dérivé de l'erreur |

**Observabilité**

`promtool` sur `alerts_core_test.yml` : quatre cas ajoutés (chaque alerte qui
tire, et la même chronologie qui NE tire pas — sinon le cas négatif s'évalue
contre l'absence de données et ne prouve rien).

**Écarts assumés par rapport au plan initial**

1. Le cas « index effectivement utilisé (EXPLAIN) » n'a pas été écrit : le lot 1
   avait déjà créé les deux index, et un test d'EXPLAIN fige un plan que
   PostgreSQL peut légitimement changer.
2. Le cas e2e Playwright n'a pas été ajouté : la page réutilise entièrement les
   primitives déjà couvertes par la matrice hermétique, et les oracles
   spécifiques (focus, `aria-busy`, vacuité distincte) sont au niveau composant.
3. La suppression du chemin `tool_confirmation` — et donc son test — est
   annulée : la mesure a montré qu'il est VIVANT côté ReAct (voir 3a-6).
