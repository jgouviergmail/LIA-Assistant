# Dette laissée par ADR-194 — dossier d'action ultérieure

**Date** : 2026-08-02
**Statut** : **Lot 1 FAIT · Lot 2 OUVERT (arbitrage) · Lot 3 partiellement fait
(9 outils sur 17)**

## État au 2026-08-02, après traitement

| Lot | État | Résultat |
|---|---|---|
| 1 — `formatters.py` | ✅ **FAIT** | 392 lignes retirées (1355 → 963). Le fichier **sort du ratchet de taille** : 519 SLOC, sous le plafond global de 600 — il quitte le régime dérogatoire. `BaseFormatter` supprimée ; les deux formatters sont désormais 100 % statiques, sans attribut ni méthode d'instance. Un effet domino non prévu a été trouvé et traité : `_format_metadata_timestamp` (×2, 46 lignes) n'avait déjà **aucun appelant**. |
| 2 — mutations à brouillon | ⏸️ **OUVERT** | Demande un arbitrage produit (voir plus bas). Inchangé. |
| 3 — outils sans couture | 🔶 **9 sur 17** | Couverts : wikipedia ×4, `create_reminder`, `list_reminders`, `get_route`, `get_route_matrix`, `get_open_loops`. **5 manifestes menteurs de plus** corrigés au passage. |

**Méthode retenue pour le lot 3, différente de celle prévue ici** : plutôt
qu'extraire une couture `format_registry_response` dans 17 outils de production,
la garde **pilote la vraie coroutine du `@tool` avec le client simulé**
(`test_manifest_reference_examples_provider_tools`). Zéro modification de code
vivant, et la couverture est plus large — tout le chemin de l'outil, pas
seulement sa moitié formatage. Le pattern existait déjà (`test_devops_tools`).

**Les doubles descendent aussi bas que possible, et sont les types de
production partout où il en existe un** — c'est ce qui les distingue d'une
fiction :

| Élément | Ce qui est simulé | Ce qui reste réel |
|---|---|---|
| `WikipediaClient` | uniquement `_make_request` (la frontière HTTP) | le client entier : construction des paramètres, dépliage de `query.search` / `query.pages`, branches d'erreur |
| `RelationDetail` | rien — le **schéma Pydantic de production** | validation complète : un champ renommé lève `ValidationError` |
| `Reminder` | rien — le **modèle SQLAlchemy de production** | un nom de colonne inconnu lève `TypeError` |
| `GoogleRoutesClient` | `compute_route` / `compute_route_matrix` / `close` | les helpers statiques (`parse_duration`, `meters_to_km`, `format_duration`) |

Vérifié par expérience et non par raisonnement : une réponse MediaWiki privée
de son enveloppe fait échouer l'outil, preuve que le parsing réel est bien
traversé ; un champ renommé sur `RelationDetail` lève à la construction.

**Ce que l'extension a trouvé** : `get_wikipedia_summary_tool`,
`get_wikipedia_article_tool` et `get_wikipedia_related_tool` publiaient à la
racine ce qui vit sous `wikipedias[0]` ; `create_reminder_tool` et
`list_reminders_tool` déclaraient des sorties `success`/`message` que
l'exécution ne produit pas ; `get_route_tool` annonçait un `alternatives_count`
calculé mais jamais remonté au niveau de l'étape.

**Restent non couverts (8)** et pourquoi :

| Outil(s) | Raison |
|---|---|
| `fetch_web_page_tool`, `unified_web_search_tool` | Simuler un **stream httpx** (context manager async + corps lu en flux) — harnais nettement plus lourd |
| `local_query_engine_tool`, `delegate_to_sub_agent_tool` | Dépendent d'un moteur RAG / d'un sous-agent, pas d'un simple client |
| `get_calls_tool`, `get_peer_messages_tool`, `place_phone_call_tool` | **Familles derrière un feature flag** : le catalogue chargé en test ne les contient pas (81 manifestes contre 104 outils enregistrés). Leur harnais existe déjà (`_run_relation_read`) et fonctionnera dès que les flags seront actifs. |
| `cancel_reminder_tool` | Relève du **lot 2** : c'est une mutation à brouillon |

---

## Contexte d'origine (avant traitement)
**Origine** : [ADR-194](../architecture/ADR-194-Reference-Truth-Is-A-CI-Guard.md)
(suppression du validateur de références et extension de la garde CI).
**Nature** : dossier de passation. Ce n'est ni un ADR, ni un changelog.

Chaque lot ci-dessous a été **mesuré**, pas supposé. Aucun n'a été traité, et
pour chacun la raison est un arbitrage de conception, pas un manque de temps.

---

## Lot 1 — `formatters.py` : deux méthodes abstraites sans consommateur

### Ce qui est mesuré

`SchemaExtractor` était le dernier appelant de `BaseFormatter.format_item()` et
de `_get_items_key()`. Sa suppression (ADR-194) laisse sans consommateur :

| Symbole | Ce qui l'utilisait |
|---|---|
| `BaseFormatter.format_item()` (abstrait) + ses 2 implémentations | `SchemaExtractor.extract_from_formatter` |
| `BaseFormatter._get_items_key()` (abstrait) + ses 3 implémentations | idem |
| `ContactsFormatter.FIELD_EXTRACTORS` (18 entrées) | `format_item` uniquement |
| `ContactsFormatter.OPERATION_DEFAULT_FIELDS` / `DEFAULT_FIELDS` | `format_item` uniquement |
| `GmailFormatter.OPERATION_DEFAULT_FIELDS` / `DEFAULT_FIELDS` | idem |

Vérifié par recherche exhaustive : `grep -rn '\.format_item(' src/ tests/` ne
renvoie que des mentions en docstring.

**Volume mesuré (AST, pas estimé)** :

| Bloc | Lignes |
|---|---|
| `format_item` × 3 (base + 2 impl.) | 110 |
| `_get_items_key` × 3 | 14 |
| `OPERATION_DEFAULT_FIELDS` × 2 + `DEFAULT_FIELDS` × 2 | 73 |
| `FIELD_EXTRACTORS` × 2 | 48 |
| **Total dans `formatters.py`** (sur 1355) | **245** |
| + 3 instanciations mortes dans `google_contacts_tools` | 3 |

**Aucun effet domino** — le point qui décidait de l'ampleur : les **32** méthodes
`_extract_*` comptent **38 usages externes**, donc **aucune** ne devient orpheline
en retirant `FIELD_EXTRACTORS`. Elles restent toutes vivantes.

**Reste vivant et ne doit pas être touché** : les méthodes statiques
`_extract_*`, appelées directement sur la classe (jamais sur une instance) par
`google_contacts_tools` et `emails_tools`.

### Dette adjacente, antérieure à ADR-194

`self.formatter = ContactsFormatter(...)` / `GmailFormatter(...)` est assigné
dans les outils contacts et emails, et **jamais lu** :
`grep -rn 'self\.formatter\b' src/ --include=*.py` hors affectations renvoie
**0 résultat**. Ces instanciations sont mortes indépendamment de ADR-194.

### Pourquoi non traité

Retirer les deux méthodes abstraites vide `BaseFormatter` de tout contrat : il
ne resterait qu'un `__init__`, lui-même sans appelant une fois les 3
instanciations mortes retirées. La classe cesserait d'être une ABC et les deux
formatters deviendraient des **conteneurs de fonctions statiques** — ce qu'ils
sont déjà de fait, puisque tous leurs usages passent par la classe et non par
une instance.

C'est donc un changement de **rôle** du module plus qu'une refonte, et à la
mesure il est petit. Il a été laissé de côté pour ne pas mêler un changement de
forme à la suppression d'ADR-194, pas parce qu'il serait risqué.

**Effort : 1 à 2 heures**, mécanique, avec `test_formatters_extractors.py`
comme filet (les `_extract_*` qu'il couvre ne bougent pas).

### Options

| Option | Contenu | Risque |
|---|---|---|
| **A** (recommandée) | Supprimer `format_item`, `_get_items_key`, les 3 dicts et les instanciations mortes ; `formatters.py` devient un module de fonctions d'extraction statiques, `BaseFormatter` disparaît | Faible : aucun appelant, `_extract_*` intact |
| B | Ne garder que les instanciations mortes en suppression | Trivial, mais laisse 250 lignes mortes |
| C | Statu quo | Le module ment sur sa propre architecture (« Abstract base with format_item() template method ») |

**Vérification attendue après action** : `task lint:backend`,
`tests/unit/domains/agents/tools/test_formatters_extractors.py`, et les suites
contacts/emails. Puis `task ratchet:update` — `formatters.py` (1358 lignes
physiques) perdrait ~250 lignes.

---

## Lot 2 — Mutations à brouillon : le manifeste décrit l'effet, pas la sortie de l'étape

### Ce qui est mesuré

**15 manifestes** publient des `reference_examples` que `$steps` ne peut pas
résoudre pendant l'exécution du plan :

```
complete_task_tool   create_contact_tool  create_event_tool   create_task_tool
delete_contact_tool  delete_email_tool    delete_event_tool   delete_label_tool
delete_task_tool     forward_email_tool   reply_email_tool    send_email_tool
update_contact_tool  update_event_tool    update_task_tool
```

Cause, tracée dans le code : ces outils ne réalisent pas l'action, ils créent un
**brouillon HITL**. `parallel_executor` écrit
`completed_steps[step_id] = step_result.structured_data`, et le brouillon est
exécuté **plus tard**, dans `response_node._execute_draft_if_confirmed` →
`draft_executor` → `execute_*_draft`. Le résultat final n'atteint donc jamais
`completed_steps`.

Mesuré sur `delete_email_tool` : le manifeste publie `success` et `message_id`,
l'exécution produit `{draft, drafts, result}`.

### Pourquoi non traité

Deux lectures légitimes du champ `outputs`, et le choix est un arbitrage produit :

- **« ce que l'étape rend »** — alors ces manifestes doivent publier `draft` /
  `drafts[0].*`, et le planificateur cesse de croire qu'il peut chaîner un
  `message_id` ;
- **« ce que l'action produit »** — alors ils sont justes, mais ils décrivent un
  effet **hors du plan**, et rien ne dit au planificateur que ce chemin n'est
  pas chaînable.

Trancher au jugé aurait produit 15 manifestes faux dans l'autre sens, ce qui est
pire que l'état actuel : un manifeste faux est lu comme un contrat.

### Options

| Option | Contenu |
|---|---|
| **A** | `outputs`/`reference_examples` décrivent la sortie de l'étape → corriger les 15 vers `draft.*`, puis les couvrir par la garde forte |
| B | Ajouter au `ToolManifest` un champ distinct (`effects` ?) séparant « sortie référençable » et « effet de l'action confirmée » ; plus juste, plus coûteux |
| C | Statu quo + note explicite dans chaque manifeste concerné |

### Fait mesuré depuis : le plan ne s'arrête PAS sur un brouillon

Le préalable qui figurait ici — « le HITL interrompt-il le plan ? » — a été
tranché en lisant `parallel_executor` : les brouillons sont **accumulés**
(`accumulated_drafts` → `pending_drafts`) et remontés à la fin du plan. Aucune
interruption : les étapes suivantes s'exécutent.

**L'enjeu est donc fonctionnel, pas documentaire.** Une étape placée après une
mutation peut référencer `$steps.envoi.message_id`, chemin que le manifeste
publie et que l'exécution ne produit pas — le plan échoue à la résolution.

La **fréquence réelle** n'a pas pu être mesurée en production : l'instance Loki
refuse tout filtre de ligne au-delà d'une fenêtre d'environ une heure (vérifié
par contrôle positif — même une requête sans filtre échoue sur 24 h, alors
qu'elle passe sur 1 h). Les compteurs par label `event=` fonctionnent, mais
aucun événement nommé ne couvre l'échec de résolution. À reprendre autrement
(instrumenter un événement dédié, ou interroger la base de conversations).

**Effort** : la correction elle-même est de **1 à 2 heures** (15 manifestes +
couverture). Ce qui coûte, c'est la **décision**, pas le code.

### Et si on choisissait l'option B (reprendre le plan après confirmation) ?

Question posée : ce chantier moteur est-il complexe ou risqué ? Réponse mesurée
dans le code : **peu complexe, franchement risqué** — et le risque n'est pas où
on l'attend.

**Les briques de reprise existent déjà et sont éprouvées.** Le FOR_EACH HITL
« replay-safe » (2026-07) fait exactement cela : `task_orchestrator` pré-exécute,
persiste tout dans `for_each_hitl_ctx` par un state-update **checkpointé AVANT
l'interrupt**, et un nœud dédié (`for_each_confirm_node`) porte la boucle. Côté
exécuteur, `execute_plan_parallel` accepte déjà `initial_completed_steps` et
`pre_executed_registry` — c'est-à-dire *reprendre sans ré-exécuter*. La
confirmation partielle a elle aussi son précédent (`filtered_indices` + boucle
sur soi). Rien n'est à inventer.

**Le risque est ailleurs : il faudrait d'abord SUSPENDRE le plan.** Vérifié :
aucune logique de suspension n'existe. Une étape qui dépend d'une mutation
s'exécute aujourd'hui quand même — c'est ce qui produit l'échec de résolution.
Reprendre suppose donc de ne plus exécuter la suite, donc de toucher le **cœur
de l'exécuteur, sur le chemin de TOUS les plans**, pas seulement de ceux qui
chaînent.

Et une suspension globale serait une régression nette : sur « envoie un mail à
Marie **et** donne-moi la météo de demain », la météo n'arriverait plus. Il
faudrait suspendre **sélectivement** les seules étapes dépendantes — faisable
(le graphe `depends_on` + `$steps` existe), mais c'est de la logique fine au
centre du moteur.

| Partie | Effort | Risque |
|---|---|---|
| Suspension sélective des étapes dépendantes | 2–3 j | **Élevé** — chemin d'exécution de tous les plans |
| Reprise après confirmation | 1–2 j | Faible — pattern FOR_EACH réutilisable |
| Cas limites : multi-brouillons, refus, expiration d'un plan suspendu, rattachement au tour | 2–3 j | Moyen |
| **Total** | **1 à 2 semaines** | |

**Ce chantier n'est pas justifié aujourd'hui**, et pour une raison de méthode
autant que de coût : personne n'a mesuré qu'un utilisateur demande un plan qui
chaîne après une mutation. Investir deux semaines dans le cœur du moteur pour un
besoin supposé serait refaire exactement l'erreur qu'ADR-194 vient de défaire —
un sous-système bâti sur une hypothèse jamais vérifiée.

**Ordre raisonnable** : appliquer l'option A (1–2 h), instrumenter un événement
sur l'échec de résolution, et ne rouvrir le sujet que si la mesure montre une
demande réelle.

---

## Lot 3 — 17 outils sans couture `format_registry_response`

### Ce qui est mesuré

Après ADR-194, la garde forte couvre **27 des 59** manifestes publiant des
`reference_examples`. Sur les 32 restants, 15 relèvent du lot 2 ; les **17**
autres n'exposent aucun point d'entrée de formatage instanciable sans réseau :

```
cancel_reminder_tool        create_reminder_tool        list_reminders_tool
get_route_tool              get_route_matrix_tool
search_wikipedia_tool       get_wikipedia_summary_tool
get_wikipedia_article_tool  get_wikipedia_related_tool
unified_web_search_tool     fetch_web_page_tool         local_query_engine_tool
place_phone_call_tool       get_calls_tool              get_peer_messages_tool
get_open_loops_tool         delegate_to_sub_agent_tool
```

Ils construisent leur sortie dans le corps de la fonction `@tool`, sans méthode
`format_registry_response` séparée — il n'y a donc pas de point où injecter une
réponse fournisseur déjà analysée.

Les plus risqués sont ceux à chemins profonds : `get_route_matrix_tool`
(`matrix[0][0].distance_km`), `list_reminders_tool` (`reminders[*].content`),
`unified_web_search_tool` (`synthesis`, `results[0].title`, `wikipedia.summary`),
la famille wikipedia (`wikipedias[0].title`, `related[0].title`, `sections`).

### Pourquoi non traité

Les couvrir suppose soit un **client fournisseur simulé** par famille, soit
d'extraire un `format_registry_response` de chaque fonction `@tool` — le second
étant un refactoring des outils, pas un travail de test.

Ils restent tenus par la **garde faible** de cohérence interne
(`TestEveryManifestIsInternallyConsistent`), qui couvre **tout** le catalogue et
qui a déjà attrapé six défauts Hue à sa création.

### Options

| Option | Contenu |
|---|---|
| **A** (recommandée, incrémentale) | Extraire `format_registry_response` famille par famille, en commençant par routes et rappels (chemins les plus profonds), et ajouter chaque outil à `COVERED_TOOLS` |
| B | Harnais à client simulé par famille — plus lourd, mais sans toucher le code de production |

### Effort, par famille (ce lot n'est pas un chantier unique)

Chaque famille est indépendante et livrable seule. Ces outils construisent leur
`UnifiedToolOutput` directement dans la fonction `@tool`, après l'appel client :
extraire une fonction pure `_format_*(raw) -> UnifiedToolOutput` déplace 20 à 40
lignes, sans changer la logique.

| Famille | Outils | Effort estimé | Note |
|---|---|---|---|
| wikipedia | 4 | 1–2 h | construction localisée (`data_success` en 2 points) |
| rappels | 3 | ~1 h | `structured_data` déjà explicite |
| routes | 2 | 2–3 h | fichier de 2008 lignes, chemins les plus profonds (`matrix[0][0]`) |
| web_search + web_fetch | 2 | ~1 h | |
| téléphonie | 2 | ~1 h | |
| peer / sub-agents / query | 3 | ~1 h | |
| **Total** | **17** | **1 à 2 jours** | découpable, aucune dépendance entre familles |

---

## Récapitulatif

| Lot | Volume mesuré | Nature du blocage | Effort | Priorité |
|---|---|---|---|---|
| 1 — `formatters.py` | 245 lignes, **zéro cascade** | Changement de rôle du module | **1–2 h** | Basse (propreté) |
| 2 — mutations à brouillon | 15 manifestes | **Arbitrage produit** — seul point qui demande une décision | 1–2 h après décision | **Haute** |
| 3 — 17 outils non couverts | 6 familles indépendantes | Extraction d'une couture de formatage | **1–2 j**, découpable | Moyenne |

**Aucun n'est un gros chantier.** Le total tient en 2 à 3 jours, et un seul
point — le sens à donner aux `outputs` d'une mutation à brouillon — appelle une
décision plutôt que du code.

Aucun n'est bloquant pour la production : le lot 1 est de la propreté, le lot 3
est un manque de vérification et non un défaut. Le lot 2, en revanche, décrit un
contrat que l'exécution ne tient pas, et le plan **ne s'arrête pas** sur un
brouillon — sa fréquence réelle reste à mesurer.

---

## Lot 4 — ✅ TRAITÉ (2026-08-02, ADR-195)

Les deux gardes décrites ici ont été supprimées, et une troisième découverte au
passage a été corrigée. Le détail vit désormais dans
ADR-195 (`docs/architecture/ADR-195-A-Diagnosis-Is-Not-A-Question.md`) ; en résumé :

- **4a** — la reconstruction du plan à la reprise ne pouvait jamais réparer quoi
  que ce soit (démonstration par cas + 0 dict sur 47 plans et 44 verdicts réels).
  Supprimée, avec sa jumelle `ValidationResult` qui reconstruisait `errors=[]` et
  aurait vidé les blocages d'ADR-184. Ce qui tient la propriété est une garde CI.
- **4b** — `nodes/response_builders.py` (342 lignes) et ses 462 lignes de tests
  supprimés : jamais importé depuis `src/`, depuis le commit initial.
- **4c, non prévu** — `ExecutionStep` acceptait à la construction ce qu'il
  refusait à la relecture (Pydantic ne valide pas les défauts), ce qui dégradait
  l'étape en `dict` après un checkpoint, sans erreur. Un `model_validator` ferme
  la classe entière ; 18 tests portaient des données qu'aucun producteur ne
  génère.

**L'enseignement méthodologique**, lui, mérite d'être retenu : le diagnostic
initial de 4a — « les `steps` reviennent dégradés » — était **faux**, et il l'a
été jusqu'à ce que des checkpoints RÉELS soient lus. Le test qui le « prouvait »
construisait une étape que le domaine interdit. Une propriété mesurée sur des
données inventées ne mesure que l'invention.


---

## Lot 5 — le filtre PII ne voit pas les numéros au format national (trouvé en revue, 2026-08-02)

`add_pii_filter` est bien branché dans la chaîne structlog et **pseudonymise les
adresses e-mail** — vérifié :

```
"Envoie un mail a marie@client.example et appelle le 0612345678"
  -> "Envoie un mail a email_hash_<...> et appelle le 0612345678"
```

Le numéro, lui, passe intact. `PHONE_PATTERN`
(`infrastructure/observability/pii_filter.py`) exige un indicatif explicite :

```python
r"\+\d{1,3}[\s.-]?\d{1,4}..."
```

`+33 6 12 34 56 78` est donc masqué, `0612345678` ne l'est pas — soit la forme
la plus courante dans un produit francophone, sur lequel un domaine téléphonie
est actif (`place_phone_call_tool`).

**Pourquoi ce n'est pas corrigé ici** : élargir le motif touche *tous* les logs
de l'application, et un motif trop large masquerait des dates, des montants et
des identifiants — un log muet coûte autant qu'un log bavard. Le bon geste est
un motif par région, mesuré contre un corpus de logs réels pour compter les faux
positifs. C'est un chantier de confidentialité à part entière, pas un ajustement
en marge d'ADR-195.

**Ce qui a été fait entre-temps** : les deux sites de ce chantier qui écrivaient
du contenu utilisateur au niveau INFO (`planner_v3_replan_with_feedback`,
`semantic_validator_node_validating`) ne publient plus que des compteurs et des
types à ce niveau ; le contenu est passé en DEBUG, conformément à la doctrine
« counters and IDs at INFO, contents at DEBUG ». La portée du filtre n'est donc
plus le seul rempart sur ces deux chemins.

---

## Lot 6 — la clarification n'a pas de sortie (trouvé en test réel, 2026-08-02)

**Ce qui a été corrigé** (cause du cas signalé) : le validateur exigeait un
`for_each` sur une collection qu'aucune étape du plan ne produit. La demande
était **insatisfaisable par construction**, donc le verdict ne convergeait
jamais. Mesuré sur la requête « navigateur → email des 3 premiers résultats » :
16 cycles de planification, 10 routages vers clarification, `for_each_detected`
vrai sur 14 analyses avec `for_each_collection_key="browsers"` alors que
`browser_task_tool` ne déclare aucune collection. La règle réclame désormais une
source itérable, en s'appuyant sur les manifestes qu'ADR-194 a rendus véridiques,
et compte les demandes abandonnées
(`semantic_validation_for_each_demand_dropped_total`).

**Ce qui reste ouvert** : rien ne borne le nombre de tours de clarification.

- `planner_iteration` est resté **figé à 2** sur 8 clarifications consécutives ;
  le commentaire de `clarification_node` prétendait qu'il protégeait de la
  boucle — il n'est jamais incrémenté sur ce chemin. Commentaire rectifié.
- La branche ABORT voisine traite le seul cas « l'utilisateur annule », et son
  propre commentaire admet que sans elle « une annulation boucle pour toujours ».

**L'arbitrage à rendre** est la SORTIE, pas le compteur. Au bout de N tours :

- *exécuter le plan malgré le verdict* serait cohérent avec ADR-184 (« un verdict
  n'est pas un échec ») — **mais ce n'est pas sûr ici** : `send_email_tool` porte
  `hitl_required=False` (vérifié), donc un courriel que personne n'a confirmé
  partirait ;
- *renoncer en le disant* (« je n'arrive pas à structurer cette demande, peux-tu
  la reformuler ? ») ne risque rien, au prix d'un aveu d'échec ;
- *distinguer lecture et mutation* — exécuter la première, renoncer sur la
  seconde — est probablement le bon compromis, et demande de vérifier que la
  lecture non convergée ne trompe pas l'utilisateur sur ce qu'elle a fait.

Une quatrième piste s'attaque à la cause plutôt qu'au symptôme : **déclarer
quelles issues sont clarifiables**. `for_each_missing_cardinality` naît d'une
analyse, pas d'une information manquante ; aucune réponse ne peut la lever, donc
elle ne devrait jamais déclencher de question. C'est la doctrine du drapeau
`user_facing` d'ADR-195, appliquée un cran plus haut.

---

## Lot 7 — les mêmes domaines, mesurés : deux registres qui se contredisent

La question « d'autres domaines peuvent-ils déclencher ce blocage ? » a été
tranchée par la mesure, pas par l'intuition. **Cinq types de contexte sur dix-huit**
sont déclarés sans qu'aucun manifeste ne produise une collection de ce nom :

| Type de contexte | Ce que l'outil déclare vraiment |
|---|---|
| `browsers` | `content` — une chaîne (le cas rencontré) |
| `routes` | `route` — un objet, dont `route.steps` est le tableau |
| `querys` | `summary_for_llm` — une chaîne |
| `health_signals` | `overview` — un objet |
| `web_searchs` | `results` — un tableau, sous un AUTRE nom |

La cause est structurelle : **l'analyseur parle le vocabulaire du
`ContextTypeRegistry`, le plan ne peut satisfaire que celui des manifestes**, et
rien ne tenait les deux d'accord. `browsers` n'était pas une hallucination du
modèle : c'est un type déclaré, avec ses `reference_fields`.

Traité : la règle FOR_EACH exige désormais une source réellement itérable et,
quand une collection existe, **son feedback nomme celle que le plan produit** —
`$steps.step_1.results` et non `$steps.step_1.web_searchs`, `$steps.step_1.route.steps`
et non `$steps.step_1.route` (un objet). Les quatre premiers cas ne bloquent
plus du tout ; le cinquième bloque encore mais indique une référence qui résout.

Reste ouvert : `test_context_types_have_a_producer` **signale** l'écart sans le
corriger, avec une liste shrink-only. Aligner pour de bon suppose de décider, par
domaine, si le manifeste doit déclarer la collection (`web_searchs` → `results`
est un simple renommage) ou si le domaine ne produit légitimement qu'un objet.
C'est une revue de vocabulaire, pas un correctif mécanique.
