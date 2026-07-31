# ADR-183 : Clôture du catalogue — un catalogue filtré doit permettre l'existence d'un plan valide

**Statut**: ✅ IMPLEMENTED (2026-07-31)
**Date**: 2026-07-31
**Décideurs**: Utilisateur (« ok pour tout y compris sur tes propositions d'arbitrage ») + mesures runtime prod

## Contexte

Signalement du 2026-07-30 : « résume ce mail X et propose une réponse » échouait
en production. Trente minutes plus tard, la **même** demande fonctionnait. Le
caractère intermittent a d'abord été lu comme une bonne nouvelle ; c'était la
signature du défaut.

### Le tirage de dé, mesuré

Deux exécutions du même utilisateur, même intention (`primary_domain=email`,
`confidence=0.95` dans les deux cas), extraites des logs prod :

| | Échec 22:51 (`617dd423`) | Succès 23:25 (`fb44ab80`) |
|---|---|---|
| `semantic_pivot_translation` | `"Summarize the email …"` | `"Summarize the email …"` — identique |
| Chaîne vue par le planner | `"Summarize the email titled…"` | `"Find the email titled…"` |
| Raisonnement analyzer | *"User wants email read/summarized"* | *"User requests email **retrieval** and analysis"* |
| `tools_count` | 3 | 4 |
| `get_emails_tool` | **0,010 → exclu** (seuil 0,07) | au-dessus du seuil |
| Résultat | ❌ `search_emails_tool` inventé | ✅ |

La chaîne comparée aux `semantic_keywords` n'est **pas la phrase de
l'utilisateur** : c'est `intelligence.english_query`, une paraphrase anglaise
régénérée à chaque tour par `deepseek-v4-flash` à `temperature: 0.2`
([router_node_v3.py:222-224](../../apps/api/src/domains/agents/nodes/router_node_v3.py#L222-L224)).
« Find » ressemble à `get_emails_tool`, « Summarize » non. Tous les scores ont
glissé en conséquence (`forward` 0,035→0,051, `delete` 0,006→0,035).

### Pourquoi aucun réglage de score ne pouvait corriger ça

Le pipeline enchaîne un étirement min-max puis un softmax `T=0.1` : un
**amplificateur de rang**, conçu pour faire émerger l'acte dominant d'une
phrase. Une requête composite (« résume » **et** « propose une réponse ») porte
deux actes et est réduite à un seul vecteur. Deux approches ont été écartées
après mesure :

- **Enrichir les mots-clés** (« summarize », « find », « retrieve »…) : on
  calerait des mots-clés sur une chaîne qu'un LLM réécrit à chaque tour. Le
  prochain tour invente un autre verbe.
- **Déplacer le seuil sur le score brut** (candidat-indépendant, contrairement
  au min-max et au softmax) : cela calibre un signal dont **l'entrée** est
  aléatoire. La campagne de mesure aurait mesuré du bruit.

Dans l'exécution en échec, le planner a reçu `reply_email_tool` — dont
`message_id` est `required=True` — sans aucun outil capable de produire un
`message_id`. **L'espace des plans valides était vide avant que le modèle ne
commence.** Il n'a pas halluciné par faiblesse : il n'avait aucun plan correct
à écrire.

## Décision

Une règle structurelle qui ne regarde jamais la requête :

> **Un catalogue est CLOS quand chaque type sémantique REQUIS par un outil qu'il
> contient est PRODUIT par un autre outil qu'il contient.**

C'est un éditeur de liens résolvant des symboles indéfinis, pas une recherche
devinant quelle bibliothèque est pertinente. La règle est **permissive** : elle
rend un plan correct *possible*, elle n'impose jamais une étape.

Implémentation : [`services/catalogue/closure.py`](../../apps/api/src/domains/agents/services/catalogue/closure.py),
câblée dans `NormalFilteringStrategy._apply_closure` sur le jeu **final**, donc
après le plafond, là où l'on voit exactement ce qui a survécu.

### Les deux règles qui la rendent correcte et non seulement plausible

Sans elles, le mécanisme aurait été **inopérant sur l'incident même qui l'a
motivé** — les deux ont été trouvées en simulant sur les manifests réels avant
d'écrire la moindre ligne de production.

1. **Un outil ne satisfait jamais sa propre exigence.** `reply_email_tool`
   consomme un `message_id` (l'original) **et** en produit un (la réponse
   envoyée). Une règle naïve l'aurait cru auto-satisfait.
2. **Un fournisseur doit être en lecture seule.** `send_email_tool` déclare lui
   aussi une sortie `message_id`, et il **était** dans le catalogue en échec :
   accepter n'importe quel producteur aurait de nouveau conclu « satisfait ».
   On ne déclenche pas un effet de bord pour découvrir un identifiant.
   Réutilise `is_read_only_tool` (catégories `search`/`readonly`/`system`).

### Choix de conception

- **Un fournisseur par type requis**, pas tous : la mesure donnait jusqu'à 9
  producteurs pour `URL`, 3,5 en moyenne. Aucun outil mesuré n'a plus de 2 types
  requis distincts → **croissance bornée à +2, typiquement +1**.
- **Départage déterministe** : même domaine qu'un consommateur, puis meilleur
  score, puis nom. Le score ne sert plus qu'à *classer* entre fournisseurs —
  jamais à décider d'en garder zéro. Une paraphrase malheureuse peut changer
  *quel* fournisseur est offert, plus *s'il y en a un*.
- **Consommateurs capturés AVANT tout ajout** : un fournisseur couvre souvent
  plusieurs consommateurs (`get_emails_tool` source à la fois le `message_id` de
  `reply` et l'`email_address` de `send`). Les dériver après aurait omis le
  second, le laissant évinçable et rendant l'ajout orphelin.
- **Arbitrage explicite de `max_tools`** (5 par défaut, 10 en multi-domaine — le
  plafond contraint réellement) : un fournisseur de clôture prime sur un outil de
  remplissage, éviction du moins bien scoré parmi les non-protégés ; si rien
  n'est évinçable, l'ajout est **abandonné et loggé** (`catalogue_closure_capped`)
  — une troncature invisible se lirait « le catalogue allait bien ».
- **Fail-safe** : la clôture qui lève dégrade le catalogue, ne fait jamais échouer
  la requête (même patron que la protection sémantique voisine).

## Consolidation des manifests

L'audit des 89 manifests a d'abord produit une liste de 8 domaines « à trous ».
La contre-vérification l'a réduite à **un seul**, et c'est le résultat le plus
important de ce lot. Le critère nécessaire (paramètre obligatoire typable) n'est
pas suffisant. Le critère juste :

> Un *handle* est une valeur que l'utilisateur **ne peut pas prononcer** et que
> l'outil **ne résout pas en interne**.

| Candidat | Résolution interne | Verdict |
|---|---|---|
| `get_peer_availability_tool.peer_name` | `fold_name` exact sur les connexions | ❌ faux positif |
| `control_hue_light_tool.light_name_or_id` | `_find_resource_by_name` (id **ou** nom minusculé) | ❌ faux positif |
| `get_wikipedia_article_tool.title` | valeur prononçable | ❌ faux positif |
| **`toggle_scheduled_action_tool.action_id`** | `UUID()` strict, échec immédiat | ✅ **vrai trou** |

Ce critère **valide rétroactivement** les annotations existantes (`message_id`,
`event_id`, `task_id` : tous des identifiants opaques) — les auteurs d'origine
avaient raison. Sur 51 paramètres obligatoires non annotés, **44 le sont à juste
titre** (texte libre : `query`, `prompt`, `body`, `objective`).

Ajouté : type `automation_id` dans un module extrait
[`semantic/resource_handle_types.py`](../../apps/api/src/domains/agents/semantic/resource_handle_types.py)
— `core_types.py` est gelé par le ratchet à 974 SLOC (mesuré 954, marge +20) et
CLAUDE.md interdit de relever un plafond. Le module porte surtout **le critère**,
pour que l'erreur coûteuse (annoter un paramètre que l'outil résout déjà) ne se
reproduise pas.

### Défaut préexistant corrigé au passage

`list_hue_lights_tool` déclarait des sorties `lights[].name` / `is_on` /
`brightness`. Son payload réel ne contient que `count` et `on_count` : ses
données partent en `registry_updates`, que l'exécuteur expose sous `meta.domain`,
soit `CONTEXT_DOMAIN_HUE = "hues"`. Toute référence
`$steps.list_hue_lights.lights[0].name` ne résolvait **rien**. Manifest corrigé
vers `hues[]` (véridique, zéro changement runtime, zéro token) — asymétrie
interne au domaine, `rooms` et `scenes` posant leur `structured_data`
explicitement étaient exacts.

**Hypothèse rejetée** : Wikipédia semblait mentir aussi (aucun `structured_data`
dans le code de l'outil). Faux — [parallel_executor.py:2939-2959](../../apps/api/src/domains/agents/orchestration/parallel_executor.py#L2939-L2959)
synthétise `structured_data[meta.domain]` depuis le registre. Sans cette
vérification, du code sain aurait été « corrigé ».

## Dérive de l'ontologie

`core_types.py` portait ~70 types au `used_in_tools` incomplet, et
`get_semantic_provider_tool_names` saute tout type au `used_in_tools` vide — la
dérive désactivait donc silencieusement la protection. **Retenu** :
`used_in_tools` **et** `source_domains` sont désormais **dérivés des manifests au
point d'usage** (`collect_manifest_output_providers`, symétrique du
`collect_manifest_param_consumers` existant), et la clôture ne lit **jamais**
l'ontologie. Écarté : dérivation au boot — elle imposerait au layer sémantique
d'importer les modules de manifests au niveau module (aujourd'hui uniquement en
imports différés) et de muter des dataclasses `frozen`.

## Gardes

- `test_catalogue_closure.py` (17 tests) : l'incident rejoué, les deux pièges
  d'auto-satisfaction, les catalogues déjà clos laissés intacts, le départage
  déterministe, les cycles bornés.
- `test_closure_wiring.py` (5 tests) : la clôture dans la passe réelle, avec les
  scores de production verbatim, et l'arbitrage du plafond.
- `TestEveryRequiredHandleHasAReadOnlySource` : aucun type requis ne peut être
  introduit sans source en lecture seule — la clôture répare un catalogue qui a
  *omis* la source, elle ne peut pas en inventer une.

## Conséquences

- L'exécution en échec du 22:51 produit désormais un catalogue clos (`+1` outil,
  `tools_count` 3→4) ; celle de 23:25 est inchangée. La clôture supprime le
  tirage de dé sans toucher à ce qui marchait.
- Généralise sur 5 domaines mesurés (email, automation, event, task, contact) :
  `delete_event_tool` tire `get_events_tool`, `complete_task_tool` tire
  `get_tasks_tool`, etc.
- `REPLAN_MODIFIED` redevient un filet de sécurité au lieu d'être la béquille
  d'un catalogue mal formé. La boucle de récupération reste non câblée (ADR-128,
  D4) : les décisions du replanner restent consultatives.

## Alternatives écartées

- **Mots-clés sémantiques enrichis** : réglage à l'instance sur une chaîne
  régénérée par un LLM à chaque tour.
- **Seuil sur le score brut + campagne de calibration** : calibre un signal dont
  l'entrée est stochastique ; introduit une constante magique par domaine.
- **Tirer tous les producteurs d'un type** : jusqu'à 9 outils ajoutés pour un
  seul `URL` — le catalogue explose et l'économie de tokens (96 %) disparaît.
- **Accepter n'importe quel producteur** : `send_email_tool` produit un
  `message_id` ; le mécanisme aurait été inopérant sur son propre cas fondateur.
- **Étendre la clôture aux paramètres optionnels** : le planner peut simplement
  les omettre, leur absence ne vide jamais l'espace des plans ; la croissance
  deviendrait non bornée.
