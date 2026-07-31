# ADR-184 : Une borne appliquée doit être publiée, et un verdict de validation ne vaut pas échec

**Statut**: ✅ IMPLEMENTED (2026-07-31)
**Contexte**: `smart_planner_prompt.txt`, `smart_catalogue_service.py`, `plan_blockers.py`, `validator.py`
**Supersede**: complète ADR-182 (couche d'honnêteté) sur son angle mort

---

## Contexte — « donne mes 3 derniers emails reçus » échoue une fois sur deux

Mesuré en production le 2026-07-31 sur douze requêtes consécutives du même
utilisateur (v1.27.3 déployée, images `lia-api:local` du même jour) :

| requête | `max_results` demandé | verdict | résultat |
|---|---|---|---|
| « mes 2 derniers emails » (×3) | 2 | valide | correct |
| « mes **3** derniers emails » (×3 sur 4) | **20** | **invalide** | **« je n'ai pas pu »** |
| « mes 4 derniers emails » (×3) | 4 | valide | correct |
| « mes 5 derniers emails » | 5 | valide | correct |

Le tour qui échoue (requête `83c98053`) est intégralement traçable :
`get_emails_query_success total_results=10`, `registry_execution_complete
current_turn_items=10`, `response_node_registry_mode_enabled
registry_items_count=10` — **les dix emails étaient dans le contexte du modèle
rédacteur** — et la réponse persistée dit :

> « Alors, mauvaise nouvelle : je n'ai pas pu récupérer tes 3 derniers emails
> reçus. La récupération des emails a été bloquée par une limite imposée sur
> cette fonctionnalité […] Vérifie les paramètres du connecteur email dans les
> réglages. »

Le connecteur était sain. Le diagnostic était inventé — exactement le défaut
qu'ADR-182 avait éliminé, reproduit à l'identique dans l'autre sens.

## Les trois couches qui ne s'accordaient pas

**1. Le prompt ordonnait un nombre.** `smart_planner_prompt.txt` portait
« set max_results = 20–50 » en dur, avec pour exemple littéral « the 3 most
important emails » — d'où la corrélation mesurée avec la cardinalité 3 : la
requête s'apparie au few-shot, la règle se déclenche, le modèle écrit 20.

**2. Le catalogue cachait la borne.** `_manifest_to_dict` ne publiait la
description d'un paramètre que s'il était `required`, sémantique, `pattern`é ou
ID-like. `max_results` n'est aucun des quatre, et la contrainte `maximum`
n'était transmise dans aucun cas. Vérifié au runtime sur l'image de production :

```
ce que le planner reçoit : {"name": "max_results", "type": "integer", "required": false}
ce que le manifeste déclare : maximum=10  (settings.emails_tool_default_max_results)
```

Le modèle obéissait à la seule instruction qu'il avait, contre une borne qu'il
n'avait aucun moyen de connaître. **Une borne appliquée mais non publiée n'est
pas un contrat, c'est un piège.**

**3. Le verdict était consultatif à l'exécution, prescriptif à la réponse.**
`route_from_planner` ne lit jamais `is_valid` : le plan rejeté part au
`task_orchestrator` inchangé, l'outil écrête lui-même (`get_emails_limit_capped
20 → 10`) et réussit. Le verdict ne bloque rien — mais depuis v1.27.3
`summarize_plan_blockers` en déduisait « bloqué » pour la seule raison que
`is_valid` valait `False`, et la directive `response_directive_plan_blocked`
ordonnait au modèle d'annoncer un échec. Le commentaire du code portait
l'hypothèse fausse : *« the turn ran on anyway »*, les outils « retournent
vide ». Vrai du cas fondateur (scopes OAuth manquants), faux d'une contrainte
écrêtable.

Périmètre : 5 domaines sur 8 plafonnés sous la cible du prompt en production
(emails, contacts, drive, places, tasks à 10 ; calendar à 25 passait, ce qui
explique que « mes 3 prochains rendez-vous » ne déclenchait rien), et ~30 sites
`add_error` dans le validateur pouvant chacun produire la même fausse réponse.

## Décision

**Trois correctifs, chacun à sa racine, aucun ne suffisant seul.**

### D1a — le catalogue publie ce que le validateur applique

`_manifest_to_dict` ajoute `min` / `max` sur tout paramètre déclarant une
contrainte numérique, dans la forme compacte déjà utilisée pour `pattern`.
Deux clés par paramètre borné : le coût en tokens est marginal, l'asymétrie
disparaît. Les valeurs non numériques (contrainte mal seedée) ne sont pas
publiées.

### D1b — le prompt cesse de porter un nombre

« 20–50 » est remplacé par `{semantic_broad_batch}`, **le setting qui existait
déjà** (`planner_semantic_broad_batch`, défaut 25) et que l'autocorrect du
semantic-leak utilisait de son côté. Une seule source de vérité au lieu de deux
nombres pouvant diverger. Le prompt subordonne explicitement la cible à la
borne publiée : *« NEVER exceed the `max` […] those are hard limits enforced
before execution, not suggestions »*.

### D1c — l'écrêtage est déterministe, pas espéré

Un prompt correct reste une instruction à un modèle non déterministe.
`services/planner/parameter_bounds.py` ramène tout paramètre hors bornes dans
ses bornes au moment où `_build_plan` construit l'étape — même doctrine que
l'auto-correction `for_each_max` déjà présente au même endroit : *corriger ce
qui est mécaniquement corrigible, le logger, et ne jamais perdre un tour pour
ça*. Le plan dit alors ce que l'outil ferait de toute façon, et le verdict ne
porte plus un défaut déjà réparé.

Ne sont **pas** écrêtés, parce que les réparer inventerait une intention :
`pattern`, `enum`, `min_length`/`max_length`, les types incorrects, les
références `$steps`, les templates Jinja, les booléens (`isinstance(True, int)`
est vrai en Python), et les bornes incohérentes (`minimum > maximum`, défaut de
seeding). Le validateur doit continuer à les voir.

Défaut de la même famille corrigé au passage, **armé en production** (`PLANNER_
SEMANTIC_LEAK_MODE=autocorrect`) : l'autocorrect du semantic-leak écrivait
`max_results = broad_batch` sans consulter le manifeste — le validateur aurait
donc lui-même produit la `CONSTRAINT_VIOLATION` qu'il rapporte. Il passe par le
même écrêtage.

### D2 — un verdict ne devient un échec qu'à défaut d'exécution

`summarize_plan_blockers` prend désormais l'ensemble des outils qui ont
réellement produit. Une capacité qui a tourné n'est jamais déclarée bloquée ;
un blocage de niveau plan (`tool_name=None`) est tu dès que quoi que ce soit a
produit. La source est `execution_plan.steps` × `completed_steps` — le seul
enregistrement de ce que le tour a fait (les expansions FOR_EACH sont agrégées
par l'exécuteur sous le `step_id` d'origine, la correspondance reste totale).

Un pas de trois cas, tous épinglés par des tests :

| verdict | exécution | directive |
|---|---|---|
| invalide | l'outil a produit | **aucune** (le défaut du jour) |
| invalide | l'outil a échoué | émise (cas fondateur ADR-182) |
| invalide | l'outil n'a pas tourné | émise (cas fondateur ADR-182) |

Le défaut par défaut est « émettre » : un état absent ou revenu déformé d'un
aller-retour msgpack (reprise HITL, tour ReAct) rend un ensemble vide et
restaure exactement le comportement antérieur. Jamais l'inverse.

Enfin la directive traite le tour partiel : une capacité bloquée pendant qu'une
autre produit ne doit plus être annoncée comme un échec total — *« a partial
result announced as a total failure is itself a false diagnosis »*.

## Conséquences

- Une contrainte de manifeste n'est plus applicable sans être publiée : le
  producteur du plan et son juge lisent la même source, qui est le
  paramétrage (`settings.*_tool_default_max_results`).
- `CONSTRAINT_VIOLATION` de type borne devient structurellement impossible sur
  un paramètre déclaré — l'écrêtage précède la validation.
- Le contrat du validateur est explicite : son verdict classe, il ne prononce
  pas d'échec. Ce qui prononce l'échec, c'est l'absence de résultat.
- Métrique `planner_parameter_bounds_corrections_total{bound}` : un débit
  soutenu signale une instruction de prompt qui a débordé une borne configurée.

## Alternatives écartées

- **Faire bloquer le validateur** (rendre `is_valid` prescriptif à
  l'exécution) : régression majeure et immédiate — les plans invalides du jour
  réussissaient (dix emails livrés) ; les bloquer aurait transformé une réponse
  fausse en absence de réponse.
- **Une sévérité « réparable » dans `ValidationResult`** : catégorise le défaut
  au lieu de le supprimer, et impose quand même la réparation.
- **Relever les caps à 20–50 pour suivre le prompt** : déplace le nombre en dur
  d'un fichier à l'autre, ne dit rien pour `weather` (max 5) ou `health`
  (max 14), et laisse le planner aveugle.
- **Ne corriger que D2** : la réponse cesse de mentir, mais l'utilisateur
  continue de recevoir 10 emails quand il en demande 3, et chaque tour reste
  compté comme un plan rejeté dans le dashboard 07.
- **Ne corriger que D1** : supprime le déclencheur mesuré, laisse intacte la
  classe — n'importe lequel des ~30 sites `add_error` reproduit la fausse
  réponse dès qu'un plan invalide s'exécute avec succès.
- **Publier toutes les contraintes au catalogue** (`min_length`, `enum`…) :
  coût en tokens sur chaque outil pour des contraintes que le planner ne peut
  pas exploiter aussi directement ; à reconsidérer si un défaut le motive.

## Vérification

- 15 230 tests unitaires verts, mypy strict (1038 modules), ruff, black.
- 79 tests ciblés : bornes du catalogue, écrêtage (types, degradation,
  non-mutation, bornes incohérentes), `executed_tool_names`, filtrage des
  blockers, directive de bout en bout, prompt paramétré.
- Preuve runtime dans le conteneur (`lia-api-dev`, source montée) : entrée de
  catalogue `{"name":"max_results",…,"max":10}`, écrêtage 20/25/50 → 10, et la
  chaîne complète — verdict invalide + étape ayant produit → directive vide ;
  verdict invalide + rien produit → directive émise.
- La garde `test_prompt_cache_hygiene` a été honorée : `semantic_broad_batch`
  est déclaré dans `ALLOWED_BEFORE_MARKER` au même titre que `max_actions`
  (valeur invariante par déploiement, ne fragmente pas le préfixe caché).
