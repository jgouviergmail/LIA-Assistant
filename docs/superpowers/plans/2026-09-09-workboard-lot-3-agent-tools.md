# Workboard, lot 3 — six tools and a measured routing corpus (ADR-276)

**Statut** : à exécuter. Écrit après le lot 2, contre le code livré et vérifié.

Le lot 1 a donné au tableau ses données et son API ; le lot 2 a donné à LIA le
droit d'exécuter un ticket toute seule. Ce lot lui donne le droit d'en **parler**
— créer, déplacer, commenter, lister, lire, supprimer depuis le chat — et il
ferme la boucle que le lot 2 a laissée ouverte : le lien `?intent=` d'un run
arrêté demande aujourd'hui à LIA de reprendre l'action, mais elle n'a aucun
moyen de commenter ni de déplacer le ticket ensuite.

## Ce que le lot 2 a livré et sur quoi ce lot s'appuie

| Ce qui existe | Où | Ce que le lot 3 en fait |
|---|---|---|
| `WorkboardService` (droits, bornes, transitions) | `domains/workboard/service.py` | les outils l'appellent, ils ne réimplémentent aucune règle |
| `resolve_reference` (id ou titre plié unique) | `service.py` | la résolution D11 des outils |
| `RUN_ORIGIN_KIND`, `RunOrigin`, `with_hidden_stamp` | `agents/api/run_origin.py` | rien à faire : un tour attendu n'a pas d'origine |
| la porte d'effets amendée (`draft` + `confirm`) | `agents/effects/gate.py` | `delete_ticket_tool` déclare `confirm` et obtient sa carte |
| `WorkboardEvent` + `recipients_for` | `domains/workboard/notifications.py` | l'événement `assigned`, qui manque encore |
| `worst_case_run_seconds` | `domains/workboard/constants.py` | rien à faire |

**Le piège d'architecture de ce lot, à traiter en premier.** `agents` importera
`workboard` (les outils), et `infrastructure/proactive/notification.py` importe
`agents`. Donc **`domains/workboard/*` ne peut pas importer le distributeur de
notifications** : le cycle se fermerait, et le ratchet de couplage compte les
imports LOCAUX — le cacher dans une fonction ne ferait que cacher l'arête.

C'est pourquoi `domains/workboard/notifications.py` est PUR aujourd'hui et que
le lot 2 a livré la notification depuis le runner (`infrastructure/`). Le lot 3
doit livrer la notification « ce ticket t'a été confié », qui part du SERVICE.
La solution est la couture déjà employée par le registre de consultations
(`domains/shared/consultation_sink.py`) : un module de `domains/shared/` porte
la couture, l'infrastructure s'y installe à l'import, et le domaine appelle la
couture sans importer personne.

---

## Tâche 1 : la couture de notification, et l'événement « assigné »

**Fichiers**
- Créer : `apps/api/src/domains/shared/proactive_sink.py`
- Modifier : `apps/api/src/infrastructure/proactive/notification.py` (installe
  la couture à l'import), `apps/api/src/domains/workboard/service.py`,
  `apps/api/src/domains/workboard/notifications.py`,
  `apps/api/src/core/i18n_proactive.py`
- Tester : `apps/api/tests/unit/domains/shared/test_proactive_sink.py`,
  `apps/api/tests/unit/domains/workboard/test_notifications.py` (étendu)

- [ ] **Étape 1 : la couture, sans rien importer**

Même forme que `consultation_sink` : un `Protocol` aux champs NOMMÉS (jamais
`**Any` — une couture qui accepte n'importe quoi laisse un appelant se tromper
de champ), un no-op installé par défaut (un script ou un test étroit n'a pas de
distributeur, et lever là transformerait une notification en panne), et un
`install_*` appelé UNE fois par son propriétaire.

Le no-op doit être OBSERVABLE (`sink_is_installed()`), sinon le test « la
notification part » serait vert par absence.

- [ ] **Étape 2 : l'événement `assigned`**

`WorkboardEvent.ASSIGNED`, sa ligne dans `recipients_for` — **toujours le
nouveau détenteur, une fois par attribution, quel que soit le drapeau** : on ne
peut pas suivre un ticket qu'on ne sait pas avoir. Le corps dans
`ProactiveMessages._WORKBOARD_BODIES`, six langues. Le test de recette est déjà
paramétré par événement : ajouter `ASSIGNED` y ajoute automatiquement les six
langues et la garde « aucun placeholder n'atteint un lecteur ».

- [ ] **Étape 3 : `_reassign` appelle la couture**

Dans `WorkboardService._reassign`, après le succès. Best-effort, jamais dans la
transaction : une notification qui ne part pas ne doit pas annuler une
attribution que la personne a demandée.

**Vérification** : un test qui installe une couture espionne et prouve qu'une
réattribution vers un pair l'appelle une fois ; un test qui prouve qu'une
réattribution vers soi-même n'appelle personne.

---

## Tâche 2 : le domaine d'agent `ticket`

**Fichiers**
- Modifier : `apps/api/src/domains/agents/registry/domain_taxonomy.py`,
  `PROGRAM_DOMAIN_CONFIGS`, `apps/api/src/domains/agents/registry/*` (item type,
  clé de contexte)
- Tester : `apps/api/tests/unit/domains/agents/registry/`

- [ ] **Étape 1 : l'entrée du registre**

`ticket` au SINGULIER (`DOMAIN_REGISTRY` est l'autorité, `result_key` en est
DÉRIVÉ — ne jamais écrire une seconde table). `related_domains = ["peer"]` pour
qu'un nom de pair dans la phrase garde l'annuaire des pairs en jeu.
`feature_flag = workboard_enabled`.

- [ ] **Étape 2 : les assertions de complétude au démarrage**

Toute table clavée par domaine doit recevoir son entrée, sinon l'application
refuse de démarrer (ADR-085). Faire l'inventaire par une recherche sur un
domaine existant (`habit`, par exemple) plutôt que de deviner : la liste est
longue et une omission est silencieuse jusqu'au boot.

**Attention** : `assert_treatment_domain_completeness` applique une règle PLUS
STRICTE — une capacité déclarée qui se résout en `unknown` est une erreur de
déclaration. Le nom `ticket` doit donc rejoindre `treatments.domains` dans les
six locales ET `TREATMENT_DOMAIN_LABELS`.

---

## Tâche 3 : les six outils

**Fichiers**
- Créer : `apps/api/src/domains/agents/tools/workboard_tools.py`
- Modifier : le catalogue de manifestes
- Tester : `apps/api/tests/unit/domains/agents/tools/test_workboard_tools.py`

- [ ] **Étape 1 : les manifestes AVANT le code**

Six manifestes, et pour chacun : `mutation_policy` (`reversible` ×3, `read` ×2,
`confirm` pour la suppression), et **chaque borne que le service applique
publiée comme `ParameterConstraint`** (ADR-184 : ce qu'un validateur peut
refuser, son producteur doit pouvoir le lire). Les bornes existent déjà en
réglages : titre, description, commentaire, enfants par ticket, tickets par
compte.

Un test lit les manifestes et les réglages et prouve qu'aucune borne appliquée
n'est absente du manifeste. C'est la garde qui empêche le piège d'ADR-184 de
revenir par une porte neuve.

- [ ] **Étape 2 : les outils eux-mêmes**

`@tool` + `@track_tool_metrics` + `@rate_limit` (politique, pas choix par
fichier), `ToolResponse` / `ToolErrorModel`, `safe_parse_json` et
`parse_list_field` pour les champs composites. **Aucune règle métier ici** :
tout passe par `WorkboardService`, qui possède déjà les droits, les bornes et
les transitions — un outil qui redécide est une seconde autorité.

Dates : `normalize_user_datetime` (les ISO locales de la personne), jamais un
parse maison.

- [ ] **Étape 3 : les refus sont des CODES**

Les `WorkboardError` remontent tels quels dans `ToolErrorModel`. Ne jamais
composer une phrase française dans l'outil : la traduction est au frontend, et
la reformulation est au modèle (ADR-256).

- [ ] **Étape 4 : la décomposition**

`create_ticket_tool` accepte `parent_ticket` et peut être appelé plusieurs fois
dans un même plan — c'est l'usage que le propriétaire a nommé en premier
(décomposer une tâche complexe). Vérifier que le plafond d'enfants publié est
celui que le service applique, et qu'un dépassement est CLAMPÉ ou refusé
proprement, jamais silencieux.

---

## Tâche 4 : le corpus de routage MESURÉ

**Fichiers**
- Créer : `apps/api/tests/unit/domains/agents/workboard/routing_corpus.json`,
  `apps/api/scripts/measure_workboard_routing.py`, la tâche
  `workboard:corpus:measure`
- Tester : `apps/api/tests/unit/domains/agents/workboard/test_routing_corpus.py`

- [ ] **Étape 1 : le corpus**

≥ 8 familles × 6 langues : créer pour moi / pour LIA / pour un pair, déplacer,
commenter, lister les miens, en retard, supprimer — **et des cas NÉGATIFS** qui
doivent rester `task`, `reminder`, `automation`. Un ticket n'est ni une tâche du
fournisseur, ni un rappel, ni une routine, et c'est la confusion la plus
probable.

- [ ] **Étape 2 : la moitié déterministe**

Un test unitaire prouve que le domaine et sa désambiguïsation atteignent le
prompt de l'analyseur, et que les manifestes portent les mots-clés. Il ne
demande rien à un fournisseur.

- [ ] **Étape 3 : la moitié fournisseur, en SCRIPT**

`task workboard:corpus:measure`, forme de `recurrence:corpus:measure`. **Jamais
un test qui se saute sur une clé absente** : un test sauté est vert, et la suite
quitte la CI en silence (ADR-155).

L'oracle est **l'outil sélectionné**, par phrase. Publier le taux mesuré dans le
plan de lot, comme la récurrence l'a fait (105/108).

---

## Tâche 5 : le lien `?intent=` devient exécutable

**Fichiers**
- Modifier : `apps/api/src/core/i18n_workboard.py`

Le lot 2 fait dire au lien : « reprends le ticket, fais l'action en attente,
puis dis-moi où ça en est. » Une fois les outils livrés, la phrase peut demander
ce qu'elle ne pouvait pas demander : **commenter le ticket et le déplacer**.

Ne l'écrire qu'ICI, à la fin du lot, et pas avant : une phrase qui demande une
action que LIA ne peut pas faire produit une promesse qu'elle ne tiendra pas
(ADR-182), et c'est précisément ce que le lot 2 a évité.

---

## Tâche 6 : revue à froid et portes complètes

```
task lint
task test:backend:unit:fast
task test:markers
LIA_REQUIRE_DB=1 pytest tests/integration/domains/workboard -q --no-cov
task workboard:corpus:measure     # publier le taux
docker restart lia-api-dev && docker logs lia-api-dev --tail 60
```

**Preuve runtime** (le lot 2 a montré ce qu'elle attrape) : depuis le chat,
créer un ticket, le décomposer en deux, en déplacer un, le commenter, lister,
supprimer le parent — et vérifier en base que chaque appel a laissé une ligne
d'effet, que la suppression a présenté une carte, et que le registre de
consultations a une ligne pour la lecture.

## Revue à froid des trois lots (2026-09-09) — ce qu'elle a trouvé et fermé

Exécutée APRÈS la livraison, sur le code et non sur les tests (la consigne),
avec une preuve runtime en conteneur pour chaque défaut qui en admettait une.

1. **La tâche 2 était inerte** : `context_domain="tickets"` sur `list_tickets` et
   `get_ticket` sans `RegistryItemType`, sans `ContextTypeDefinition`, sans
   `registry_updates` — rien n'était sauvé, et une suppression confirmée
   laissait le ticket « courant ». Fermé par `agents/workboard/context.py`
   (type + enregistrement + items), `RegistryItemType.TICKET` (EXTERNAL : un
   pair écrit dedans), `context_key` sur les deux manifestes de lecture, les
   trois tables de `type_domain_mapping`, `REGISTRY_TYPE_TO_KEY`,
   `DOMAIN_LABELS` ×6 (zh-CN « 工单 », distinct de « 任务 » des tâches dans le
   même bloc), `_DRAFT_TYPE_TO_TCM_DOMAIN` + `ticket_id` dans
   `PROVIDER_REF_ORDER`. Un ticket LU devient le COURANT sans toucher la liste.
2. **La relecture générique `TOOL_CALL` n'a pas de runtime** : la suppression
   a son exécuteur (`execute_ticket_delete_draft`), qui revérifie les droits et
   rend le titre (la phrase de succès lit le RÉSULTAT). Preuve en conteneur par
   `_execute_confirmed_draft` sous un contexte de run installé : une ligne
   d'effet `draft:ticket_delete` `succeeded`, `provider_ref` = le ticket, une
   seconde confirmation refusée.
3. **`user_timezone` n'existait pas** sur `LiaRuntimeContext` (`timezone`) :
   les dates passent par `get_user_preferences(runtime)`.
4. **Le heartbeat lisait les lignes cachées** : `conversations/message_readers.py`
   (11 lecteurs, deux portées) + garde AST ; `activity_probe` et
   `heartbeat/context_aggregator` excluent `hidden`.
5. **`RUN_STARTED` n'était jamais émis** (déclaré, jamais envoyé) : émis APRÈS
   le bail, dans les deux branches de `_run` ; preuve en conteneur :
   `['created', 'run_started', 'run_finished']` et deux lignes `proactive`
   soldées sous le `run_id` d'un ticket SUIVI.
6. **Le moissonneur ne nommait pas son code** (`workboard_run_reaped`),
   **`run_now` ne remettait pas les tentatives à zéro**, **les lignes cachées
   orphelines n'étaient jamais purgées** (ticket supprimé). Fermés, testés sur
   PostgreSQL (68 tests d'intégration).
7. **Le filet doré des aperçus** exigeait un cas par `DraftType` : quatre cas
   `ticket_delete` (fr plein, fr sans étape, fr vide, en).
8. **Le script de mesure répondait 401** : un script autonome doit réchauffer
   `LLMConfigOverrideCache.load_from_db` comme le démarrage — 72/72 sur deux
   modèles une fois fait.
9. **Le registre perdait la seconde notification d'un run** : la
   revendication proactive était UNE par run (`{run_id}:notification`) ;
   un ticket suivi reçoit « commencé » puis « terminé », les deux distribuées,
   une seule ligne. La couture porte `occurrence`, la clé le compose, le
   runner nomme ce qu'il dit, un transfert est un acte à part entière.
   Preuve en conteneur : deux lignes `proactive` soldées sous le `run_id`.

10. **Trois points arbitrés puis fermés (2026-09-09)** : la consolidation des
    journaux lisait des rôles inexistants (`human`/`ai`), l'heure UTC comme
    l'heure locale, et les lignes cachées — réparée, `VISIBLE_ONLY`, deux
    tests PostgreSQL ; la notification d'attribution nomme son run
    (`ticket-event:<id>`) et la couture exige un `run_id` ; « 工单 » partout
    pour un ticket en chinois, tenu par `test_wording.py`.

Un constat hors périmètre, documenté : la dépense du script de mesure n'entre
dans aucun registre (choix identique au script de récurrence).

## Ce que ce lot ne fait pas

Pas d'interface (lot 4), pas de crochet de suppression de connexion (lot 5),
pas de source heartbeat (lot 6). Aucun ticket créé par LIA de sa propre
initiative : D13 le prévoit dans la conception, mais l'initiative reste au
lot où elle aura une raison d'être.
