# ADR-194 : la vérité d'un chemin de référence est une garde CI, pas un validateur runtime

**Statut**: ✅ IMPLEMENTED (2026-08-02)
**Date**: 2026-08-02
**Décideurs**: Équipe LIA
**Complète**: [ADR-190](ADR-190-Overview-Scope-And-Full-Contact-Card.md) (le manifeste qui promettait `contacts[0].name`), [ADR-184](ADR-184-Published-Bounds-And-Non-Prescriptive-Verdicts.md) (ce qui est appliqué doit être publié), [ADR-085](ADR-085-Draft-Display-Registry.md) (assert de complétude au démarrage)

## Contexte

Un plan multi-étapes lit la sortie d'une étape antérieure par une référence
`$steps.<step_id>.<chemin>`. Le planificateur écrit ce chemin **avant** que
l'étape n'ait tourné : s'il est faux, on ne le découvre qu'à l'exécution, après
avoir engagé des appels API payants et l'attente de l'utilisateur.

Le dépôt contenait un sous-système entier bâti pour ce cas — `ToolSchemaRegistry`,
`SchemaExtractor`, `schema_registration`, `ReferenceValidator`,
`build_schema_reference_guide` — soit ~1 900 lignes, câblées du démarrage
(`main.py` → `registries.init_tool_schemas`) jusqu'au validateur de plan
(`PlanValidator._validate_reference_field_paths`).

Le 2026-08-01, un plan a généré `$steps.step_1.contacts[0].name`, chemin publié
par le manifeste, et l'exécution est morte sur `path 'contacts[0].name' not
found in step result`. Aucune des gardes n'a parlé.

### Ce que la mesure établit

**Le sous-système n'a jamais rien validé, depuis le premier commit.** Les deux
bras du validateur sont inertes, chacun pour sa propre raison :

| Bras | Défaut | Preuve |
|---|---|---|
| Schéma | Le registre est indexé sur les **noms de fonctions Python** (`search_contacts_tool`), le plan porte les **noms de manifeste** (`get_contacts_tool`) | Intersection registre ∩ catalogue = **∅** (3 clés vs 85 outils) |
| Manifeste | Appelle `AgentRegistry.get_instance()`, méthode qui **n'existe pas** — `AttributeError` avalée par un `except Exception` | `hasattr(AgentRegistry, "get_instance")` = False ; `git log -S` : jamais définie |
| Bornes runtime | `step_results` n'est pas passé par l'appelant | `validator.py` n'en fournit aucun |

Exécuté sur le catalogue réel, `validate_references_in_step` retourne **0 erreur
sur 254 références** — publiées, réellement produites, absurdes (`$steps.s1.zzz_top.foo`)
et cas limites confondus. Y compris sur le chemin `CONDITIONAL`.

Confirmé en production (Loki, 30 jours) : **28** `reference_validation_no_schema`
pour **201** plans validés, soit **0 succès sur 28 tentatives**. Le
`reference_examples_validation_error` du bras manifeste n'apparaît pas : il est
émis en `debug`, niveau absent de la production.

**Réparer produit des faux positifs massifs.** Les deux réparations ont été
simulées contre les chemins **réellement produits** par les outils :

| Réparation | Faux positifs mesurés | Exemples de rejets |
|---|---|---|
| Bras manifeste (ajout de `get_instance`) | **63** sur 112 chemins réels, 6 outils | `events[0].summary`, `emails[0].snippet`, `tasks[0].status`, `contacts[0].names[0].displayName` |
| Bras schéma (schéma le plus riche, `details`) | **13** sur 35 chemins réels de `get_contacts_tool` | `contacts[0].name` — le chemin même que le correctif de la veille a rendu vrai —, `_registry_id`, `index`, `count` |

La cause est une **erreur de sémantique** : `reference_examples` est une liste
d'**exemples** (illustrative), que le validateur traitait comme une
**énumération exhaustive** (normative). Et `SchemaExtractor` décrivait la sortie
du *formatter*, alors que `$steps.…` adresse la sortie du *merge
`parallel_executor`* — sans `_registry_id`, sans `index`, sans les promotions du
mixin, sans les clés top-level (`count`, `operation`, `from_cache`).

Une troisième voie a été testée — ne valider que le premier segment : non viable
également, `from_cache` / `result` / `user_timezone` / `operation` étant des
clés réelles qu'aucun manifeste ne publie.

**Le filet d'exécution existe déjà et fonctionne.** `ReferenceResolver` lève un
`KeyError` explicite sur index hors bornes, champ inexistant et clé top-level
inconnue. Ce qui manquait n'était pas la détection, mais sa position dans le temps.

## Décision

**La vérité d'un chemin de référence se vérifie avant le merge, pas à
l'exécution.** Le sous-système est supprimé ; la garde qui tient le contrat est
`test_manifest_reference_examples_truthful`.

**L'asymétrie est délibérée** : la garde vérifie que *tout ce qui est publié est
produit*, jamais l'inverse. C'est précisément ce qui lui évite les 63 faux
positifs — un outil a le droit de produire plus que ce qu'il documente, il n'a
pas le droit de documenter ce qu'il ne produit pas.

**L'oracle est le pipeline réel** : le builder de l'outil (ou son
`format_registry_response`), le vrai `ReferenceResolver`, et la reconstruction
fidèle du merge de `parallel_executor` — pas une inférence sur données simulées.

**Ce qui survit à la suppression** : `STEPS_REFERENCE_PATTERN` migre vers
`orchestration/step_references.py`. Il est porteur — `capability_directives`
l'utilise pour savoir quelles étapes une étape survivante référence encore, et
supprimer une étape dont une autre dépend casserait le plan. Le module documente
pourquoi il ne doit **pas** être fusionné avec le pattern plus étroit de
`semantic_validator`, qui s'arrête à la clé de domaine pour la détection de
dépendances fantômes : `$steps.s1.contacts[0].name` donne `contacts[0].name`
pour l'un, `contacts` pour l'autre.

## Conséquences

**Aucune régression fonctionnelle possible** : le bras supprimé n'a jamais
ajouté d'erreur à `validation_result`. `is_valid`, `planner_plans_rejected_total`,
`summarize_plan_blockers` (ADR-184) et le routage reçoivent exactement la même
chose qu'avant.

**Défauts trouvés et corrigés par l'extension de la garde** (6 → **27** des 59
manifestes publiant des `reference_examples`) :

| Outil | Ce qui était publié | Ce que l'exécution produit |
|---|---|---|
| `get_current_weather_tool` | `location`, `temperature`, `description` | `weathers[0].*` |
| `get_weather_forecast_tool` | `forecast[0].datetime`, `forecast[0].temperature` | `forecasts[0].date`, `.temp_min/max/avg` |
| `get_hourly_forecast_tool` | `hourly[0].datetime_text`, `hourly[0].temp` | `weathers[0].hourly[0].*` |
| `perplexity_search_tool` | `answer`, `citations[0].url`, `related_queries` | `perplexitys[0].*` ; `related_queries` jamais produit |
| `perplexity_ask_tool` | `answer`, `confidence` | `perplexitys[0].*` ; `confidence` jamais produit |
| `list_task_lists_tool` | `task_lists[0].id/title` | `tasks[0].*` (clé de contexte `tasks`) |
| `list_labels_tool` | `name_filter` en `outputs` | produit **seulement** sur appel filtré — retiré |

Soit **7 manifestes menteurs** au-delà de celui d'ADR-190 : le défaut pressenti
comme pluriel l'était largement, et il a la même forme à chaque fois — un outil
adossé au registre publie à la racine ce qui vit sous sa clé de contexte.

Un huitième cas, `list_labels_tool`, illustre une variante : un champ
**conditionnel** ne peut pas être un contrat, puisque l'appel courant ne le
produit pas.

**Un chemin peut résoudre et mentir quand même** — sur son type. La revue a
confronté chaque `outputs[].type` déclaré au type réellement produit, ce que la
résolution seule ne voit pas :

| Outil | Déclaré | Produit |
|---|---|---|
| `get_current_weather_tool` | `weathers[].location` : `string` + `semantic_type=locality` | un **record** `{name, country, lat, lon}` |
| `get_hourly_forecast_tool` | `weathers[].hourly[].temp` : `string` | un **float** |
| `get_places_tool` | `places[].opening_hours` : `object` | une **liste** (`weekdayDescriptions`) |

Le planificateur lit le type pour décider dans quoi il peut chaîner une valeur :
annoncer un enregistrement là où vit une liste l'envoie échouer à l'exécution,
comme un mauvais chemin, un cran plus tard. `weathers[0].location` a donc été
remplacé dans les `reference_examples` par `weathers[0].location.name` — un
exemple de référence est ce que le planificateur **chaînera**. Une troisième
garde (`TestDeclaredTypesMatchProducedTypes`) ferme cette classe de défaut.

**Un neuvième défaut, trouvé sans exécuter quoi que ce soit.** Les gardes
ci-dessus valent par outil et demandent de savoir construire sa sortie — 27 des
88. Restait une question qu'on peut poser à **tout** le catalogue sans le faire
tourner : une déclaration se contredit-elle elle-même ? Passée mécaniquement sur
les 390 `outputs`, elle a trouvé `run_skill_script` publiant
`skill_apps[].skill_name`, `[]._registry_id` et `[].title` **sans jamais
déclarer `skill_apps`** — le planificateur recevait les membres d'une collection
dont l'existence ne lui était pas dite. Même forme que les huit précédents, et
invisible aux deux autres gardes : celles-ci vérifient que les
`reference_examples` adressent un champ déclaré, pas que les `outputs` tiennent
ensemble.

La leçon de méthode est le vrai apport : relire 2 900 lignes de manifestes à
l'œil n'est pas une preuve. `TestEveryManifestOutputIsStructurallySound` pose la
question une fois pour toutes, sur le catalogue entier, et coûte 0,6 s.

**Une seconde vague a porté la couverture à 36 des 59** manifestes publiant des
chemins. Les outils qui construisent leur sortie dans le corps du `@tool` sont
couverts par une garde sœur qui **pilote la vraie coroutine avec un client
simulé** (`test_manifest_reference_examples_provider_tools`) — zéro modification
de code de production, et une couverture plus large que l'extraction d'une
couture n'en aurait donné. Cinq manifestes menteurs de plus y sont tombés : les
trois outils wikipedia de détail (racine au lieu de `wikipedias[0]`), les deux
outils de rappel (`success`/`message` jamais produits), plus un
`alternatives_count` calculé par `get_route_tool` mais jamais remonté à l'étape.

**Ce qui reste non couvert est chiffré et daté**, dans
[le dossier de dette](../plans/2026-08-02-dette-post-adr194.md) : 15 mutations à
brouillon dont la sortie d'étape est un `draft` et non le résultat de l'action
(arbitrage produit, pas correction mécanique), et 8 outils dont le harnais
demande un stream HTTP, un moteur RAG, ou l'activation d'un feature flag. Tous
restent tenus par la garde faible de cohérence interne, qui couvre **tout** le
catalogue.

**Dette laissée consciemment** : `format_item()`, `_get_items_key()`,
`FIELD_EXTRACTORS` et `OPERATION_DEFAULT_FIELDS` de `formatters.py` perdent leur
dernier consommateur avec `SchemaExtractor`. Les supprimer vide `BaseFormatter`
de ses deux méthodes abstraites — changement de conception du module, pas
retrait d'une branche morte. Documenté dans le module et dans le dossier de dette.

## Alternatives écartées

**Réparer le registre** (~3-5 jours) : réécrire `SchemaExtractor` contre les
builders du mixin, gérer un schéma par opération pour un outil qui en couvre
trois, puis une campagne de non-régression. Pour un résultat structurellement
inférieur à un test qui existe déjà, et 13 faux positifs mesurés sur le seul
domaine contacts.

**Réparer le bras manifeste** (1 ligne) : 63 faux positifs mesurés. Un
validateur qui rejette `events[0].summary` coûte plus cher que l'absence de
validation.

**Ne rien faire** : ~1 900 lignes qui simulent une garantie, dont 652 sous
ratchet de taille et couvertes par 106 tests verts qui n'exécutaient rien de
réel. Le coût n'est pas le stockage, c'est la croyance qu'un filet existe.
