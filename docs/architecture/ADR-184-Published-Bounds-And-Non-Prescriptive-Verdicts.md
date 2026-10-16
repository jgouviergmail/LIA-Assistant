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

## Amendement 2026-10-13 — un scope Google ne juge que le fournisseur qu'il décrit (RC1.1)

**Constat.** Les outils multi-fournisseurs du catalogue (e-mail, agenda,
contacts, tâches) déclarent les scopes de leur implémentation GOOGLE. Le
validateur de plan et le contournement par skill les comparaient aux scopes
accordés par le compte, quel que soit son fournisseur : chaque étape e-mail,
contacts ou agenda d'un compte Outlook ou iCloud était jugée `UNAUTHORIZED`
(16 fois en sept jours sur un compte de production, relevé le 2026-10-07), et
un skill retirait ces étapes de son plan. Le verdict atteignait la réponse en
« capacité non connectée », à propos d'une boîte qui venait de répondre dans le
même tour.

**Décision.**

- **Le fournisseur d'une étape est lu là où il se décide.** Une CLASSE
  d'outil qui sert une catégorie fonctionnelle (`functional_category`) tourne
  sur le connecteur ACTIF de cette catégorie (`provider_resolver`).
  `agents/tools/connector_requirements.py` dérive nom d'outil → catégorie en
  parcourant les classes concrètes de `ConnectorTool` : aucune table tenue à la
  main, rien d'inscrit dans un constructeur (les outils de libellés sont
  construits par appel). Une garde exige que chaque manifeste à scopes soit
  nommé par une classe, ou déclaré propre à Google avec sa raison
  (`set_vacation_responder_tool`) : une classe dont le nom manquerait son
  manifeste remettrait le contrôle en silence.
- **Un seul prédicat, `ungranted_scopes`**, lu par le validateur et par le
  contournement par skill. Aucun scope n'est dû quand un autre fournisseur que
  Google sert la catégorie. Le contrôle demeure pour un outil lié à Google
  (libellés, filtres, Drive) et pour une catégorie sans aucun fournisseur
  actif : « connectez-en un » est alors la réponse honnête (le cas du
  2026-07-30).
- **Les connecteurs actifs sont ceux de la REQUÊTE**
  (`core.context.active_connector_types_ctx`). `AgentService` le pose à côté
  de la directive, depuis les lignes qui accordent les scopes du tour : un
  connecteur iCloud n'accorde aucun scope mais sert sa catégorie. Hors
  requête, rien n'est affirmé, et l'exécution, qui résout le fournisseur, est
  l'autorité : la règle de cet ADR, un verdict ne vaut pas échec, appliquée au
  cas où le verdict ne sait pas contre quoi il juge.

**Non traité, dit.** RC1.2 (`plan_blockers` garde le verdict d'une étape qui
a tourné puis échoué) et RC2.1 (le catalogue propose aux comptes sans Gmail
les outils liés à Gmail) restent ouverts ; RC1.1 en était le déclencheur le
plus fréquent. Traités le 2026-10-14 (amendement suivant).

**Preuves.** `tests/unit/domains/agents/tools/test_connector_requirements.py`
(le prédicat et la garde de complétude),
`tests/unit/domains/agents/orchestration/test_validator_provider_scopes.py`,
`tests/unit/domains/agents/services/test_skill_bypass_strategy.py::TestAStepAnotherProviderServes`,
`test_conversation_orchestrator.py` (un connecteur iCloud sans scope est nommé).

## Amendement 2026-10-14 — une capacité qui a tourné n'est jamais « bloquée », et une capacité que rien ne sert n'est pas proposée (RC1.2, RC2.1)

**Constats** (production 2026-10-07, compte Outlook).

- **RC1.2.** `plan_blockers.executed_tool_names` ne comptait une étape comme
  exécutée que si elle n'avait PAS échoué. La réponse à un e-mail avait échoué
  sur sa propre référence, et son verdict `UNAUTHORIZED` restait un
  « blocage ». La directive « plan bloqué », marquée autoritaire, disait « non
  connectée ». Dans le même temps, la directive d'échecs, qui portait l'échec
  réel, interdisait de le dire. Deux canaux pour un seul fait.
- **RC2.1.** Le catalogue proposait les outils liés à Gmail (réglages,
  filtres, libellés) et à Drive à un compte qui n'avait ni l'un ni l'autre. La
  sélection a retenu `get_gmail_settings_tool` pour une question de courrier,
  et le tour a échoué alors que la boîte Outlook venait de répondre.

**Décision.**

- **Un fait, un canal** (`attempted_tool_names`).
  - Une étape compte dès que l'orchestrateur a rangé une issue pour elle, sous
    son id ou sous celui d'un élément FOR_EACH. Peu importe que cette issue
    soit des données, une réponse vide ou un échec typé.
  - Le verdict ne parle plus que pour ce qui n'a jamais tourné. L'échec d'une
    étape tentée passe par la seule directive d'échecs (ADR-303).
  - Le cas du 2026-08-17 (relais refusé) y reste dit : cette directive lit
    `success=False`.
- **« Aucun connecteur actif » devient un code typé, que la directive d'échecs
  explique.**
  - `ToolErrorCode.CONNECTOR_NOT_ACTIVATED` remplace les chaînes libres
    `connector_not_activated` et `category_not_activated`. L'exécuteur les
    dégradait en `UNKNOWN` avant qu'elles n'atteignent la directive. Les
    quatre exécuteurs de brouillons qui renvoyaient encore la première le
    portent aussi, et c'est la carte d'exécution qui le dit (ADR-303,
    amendement 2026-10-14).
  - La directive dit qu'aucun connecteur du compte de la personne ne sert
    cette capacité : le dire une fois, et indiquer que les réglages des
    connecteurs le corrigent. Cela ne dit rien des données d'autrui.
  - Sa règle 2 (« ne jamais dire non connecté ») nomme cette seule exception.
  - La réponse juste du 2026-07-30 et du 2026-10-07 à 18:13 (« aucun service
    de courrier n'est connecté ») survit donc sans la directive « bloqué ».
- **Le code voyage dans les deux modes.** En ReAct, le corps du message
  d'outil est la prose de l'outil. Le code d'un échec déclaré voyage donc À
  CÔTÉ, sur `ToolMessage.response_metadata` : aucun adaptateur ne l'envoie au
  fournisseur, et le checkpoint le conserve. La directive le lit. Avant, tout
  échec ReAct y arrivait en `UNKNOWN`.
- **Rien ne propose un outil qui ne peut pas tourner** (la règle d'ADR-249,
  appliquée aux connecteurs).
  - Un outil lié à UN fournisseur (sans catégorie, sur un connecteur que la
    personne doit connecter) n'est proposé qu'à un compte dont un connecteur
    ACTIF de ce type le ferait tourner (`unconnected_tool_names`).
  - La liste est dérivée des classes, comme pour RC1.1.
    `PROVIDER_BOUND_WITHOUT_A_CLASS` déclare le seul outil sans classe, la
    réponse automatique de Gmail, sous la même garde.
  - Un outil de catégorie reste proposé : son « connectez un fournisseur » est
    la réponse honnête.
  - Un connecteur sans clé, ou à clé de plateforme, appartient à l'instance
    (ADR-307) et n'est jamais masqué.
  - Deux lecteurs : le catalogue du tour (`AgentService`, où lisent le
    routeur, le planificateur, ReAct et l'initiative), et la voix
    (`available_live_tools(user_id=…)`, lu par l'appel sortant, le rappel du
    fournisseur, la mise en place et la porte d'outils du Live direct).
  - Hors requête, rien n'est masqué.
  - Une ligne héritée `GMAIL` ne sert pas ces outils : leurs identifiants sont
    lus par type exact.

**Mesuré** (base de dev, 2026-10-14, sans appel de modèle).

- Compte Gmail, Google entièrement connecté : 311 outils proposés sur 311.
- Compte Outlook, Outlook et agenda en erreur, contacts et tâches actifs : 297
  outils proposés sur 311. L'ensemble masqué compte 17 outils liés à Gmail et
  à Drive : 14 ont une entrée au catalogue, d'où les 14 retirés ; les 3
  autres (`delete_file_direct_tool`, `delete_file_tool`,
  `delete_label_direct_tool`) n'en ont pas.
- La directive d'échecs passe d'environ 487 à 546 jetons pour un échec. Le
  plafond anti-emballement de son test passe de 500 à 600, la mesure écrite
  dans le test.

**Non traité, dit.** Les outils à clé personnelle (Brave, Perplexity,
OpenWeatherMap) et Hue sont construits à l'appel, avec leur nom. Ils restent
proposés sans leur connecteur ; leur échec est désormais typé
`CONNECTOR_NOT_ACTIVATED`, que la directive explique.

**Preuves.** `tests/unit/domains/agents/services/test_plan_blockers.py`,
`tests/unit/domains/agents/nodes/test_response_plan_blocked_directive.py`
(rejeux b148e908, 18:13 et 2ecc670c),
`tests/unit/domains/agents/tools/test_connector_not_activated_code.py`,
`tests/unit/domains/agents/tools/test_connector_requirements.py::TestATurnIsOfferedWhatItsConnectorsServe`,
`tests/unit/domains/agents/telephony/test_live_tools.py`,
`test_live_tools_router.py`, `tests/unit/domains/live/test_direct_mode.py`,
`tests/unit/domains/telephony/test_call_me_tool.py`.
