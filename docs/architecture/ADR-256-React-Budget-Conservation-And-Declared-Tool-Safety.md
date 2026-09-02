# ADR-256 — Un budget qui ne compte que la moitié du travail

**Statut** : Accepté — 2026-09-02
**Portée** : `domains/agents/nodes/react_nodes.py`, `domains/agents/nodes/react_history.py` (nouveau), `domains/agents/utils/react_budget.py`, `domains/agents/orchestration/step_timeouts.py`, `domains/agents/registry/catalogue.py`, `domains/agents/services/react_tool_selector.py`, `domains/agents/tools/tool_resolution.py`, `infrastructure/observability/metrics_react.py`, `components/debug/components/shared/BudgetBar.tsx` (nouveau)
**Voisins** : [ADR-170](ADR-170-React-Compute-Budget-And-Loop-Guard.md) (le budget de calcul et le frein anti-répétition), [ADR-083](ADR-083-Sub-Agent-Delegation-React.md) (le sous-agent devenu un outil), [ADR-248](ADR-248-React-Memory-Parity-And-Progress-Earned-Budget.md) (le budget gagné par la production), [ADR-085](ADR-085-Draft-Display-Registry.md) (l'assert de complétude au boot), [ADR-148](ADR-148-Health-Daily-Rollup.md) (une métrique que personne ne voit), [ADR-255](ADR-255-MCP-Tool-Declaration-Conformance.md) (une seule autorité sur ce qu'un serveur déclare)

## Le défaut, mesuré

Trois défauts indépendants, une seule cause commune : **une décision juste a
cessé de l'être quand son contexte a changé, et rien ne l'a signalé.**

| Fait | Valeur |
|---|---|
| Nœuds ReAct qui débitent le budget de calcul | **1 sur 4** (`react_call_model_node`) |
| Outils bornés par `asyncio.wait_for` en mode pipeline | **tous** (30 s à 300 s selon la famille) |
| Outils bornés en mode ReAct | **aucun** |
| Budget de calcul ReAct | 300 s — que le travail délégué ne peut pas atteindre |
| Borne haute d'un tour ReAct, constantes réelles | **~30 h** |
| Outils résolus possibles vs plafond ReAct | **896 vs 100** (89 % coupés) |
| Trace laissée par ce plafonnement | un `warning`, **aucun compteur** |
| Trace laissée par un appel d'outil inconnu | **aucune** |
| Manifestes retombant sur le défaut « lecture seule » | **17 sur 96** |
| Dont des outils qui écrivent réellement | **4** |

Aucun de ces trois défauts n'a produit d'incident connu. Ils sont réunis ici
parce qu'ils partagent la même forme : **une garde existe, mais elle ne couvre
plus ce qu'elle croit couvrir.**

## A — Le budget ne compte que le raisonnement

### Ce qui a été décidé, et pourquoi c'était juste

ADR-170 a corrigé un défaut réel : `time.time() - react_start_time` facturait à
la boucle le temps qu'un humain passait à approuver une action. La correction
est élégante — `react_elapsed_seconds` est débité **par le nœud, de sa propre
durée**, et `interrupt()` lève, donc un nœud interrompu ne débite rien. Le temps
d'attente humaine est **structurellement** exclu, sans horodatage à maintenir.

Le 2026-07-27, ce nœud était le seul à consommer du temps qui vaille la peine
d'être compté.

### Ce qui a changé depuis

- **ADR-083 Phase 2** a fait du sous-agent une boucle ReAct **exposée comme un
  outil** — 20 itérations LLM derrière un `tool_call`. La même ADR note que le
  plafond de dépense (`SubAgentTokenGuard`, `subagent_max_token_budget=50000`)
  *« was never wired »*, et que le budget journalier Redis a été **supprimé**
  avec la voie persistante. Aucun des deux n'a été remplacé.
- **ADR-249** a ajouté l'exécution de code en bac à sable.
- Le mode itératif MCP et l'agent navigateur ouvrent chacun leur propre boucle,
  respectivement 50 et 50 itérations.

Le nœud qui n'exécute que des outils est donc devenu celui qui dépense le plus,
et c'est précisément celui qui ne débite rien.

### Les quatre conséquences, vérifiées

1. **Le budget ne peut pas se déclencher sur du travail délégué.** Un tour dont
   le modèle a raisonné 10 s et dont les outils ont tourné trois heures rend
   `react_exit_reason() is None` : la boucle continue.
2. **Le même outil est borné en pipeline et non borné en ReAct.**
   `compute_step_timeout` — la politique par famille, complète et testée — n'a
   qu'un seul appelant, `parallel_executor.py`. `react_nodes.py` ne contient
   aucun `asyncio.wait_for`.
3. **Rien ne se conserve du parent vers l'enfant.** Chaque boucle imbriquée
   reçoit une constante indépendante, jamais une part de ce qui reste.
4. **La mesure affirme le contraire de ce qu'elle mesure.** La durée envoyée à
   Prometheus est `_loop_compute_seconds`, donc le seul temps du modèle. Le
   panneau `20-react-browser` s'intitule « Duration P95 » et se décrit
   « ReAct agent **total execution** duration ». Le panneau `26-product-value`
   compare « Pipeline vs ReAct p95 » : le pipeline compte ses outils, le ReAct
   non — **la comparaison favorise le ReAct par construction**.

Deux contre-hypothèses ont été testées et **écartées** :

- Le frein anti-répétition d'ADR-170 ne borne rien ici : il compare des
  empreintes d'appels **identiques**, et deux délégations aux instructions
  différentes ne se ressemblent jamais.
- Les timeouts de transport par slot LLM ne bornent pas non plus : 20 itérations
  × 60 s = 20 minutes pour **une** délégation.

### Décision A

1. **Le ReAct lit la politique de timeout que le pipeline applique déjà.**
   `compute_step_timeout` gagne un second appelant, pas un second corps. Un
   dépassement devient un `ToolMessage` récupérable — le modèle apprend que
   l'outil a expiré et peut faire autrement — jamais une exception qui tue le
   nœud. C'est le traitement que le pipeline applique déjà à ses étapes.

   **Notre borne n'est jamais la plus stricte de la chaîne.** Un appel MCP
   direct était sur le plancher générique de 30 s alors que la couche MCP
   applique déjà le sien : `mcp_tool_timeout_seconds` pour un serveur admin, et
   pour un serveur utilisateur le `timeout_seconds` que son propriétaire a
   choisi (5 à 120 s). Couper à 30 s aurait placé une seconde autorité, plus
   stricte, au-dessus d'un réglage utilisateur — et coupé un appel que la
   couche du dessous acceptait encore. Ces outils forment donc leur propre
   famille, dimensionnée sur cette borne. Le pipeline en bénéficie au passage :
   il les coupait déjà trop tôt.

   **Le message dit QUELLE borne a sauté.** Un outil peut lever un timeout qui
   lui appartient — un `wait_for` interne, un appel MCP atteignant sa borne par
   serveur — bien avant la nôtre. Annoncer « arrêté après 300 s » là où le tour
   n'a duré que 10 s énonce un nombre que l'exécution n'a jamais atteint : le
   diagnostic inventé qu'ADR-182 a supprimé. L'écoulé décide, avec une marge
   (`TIMEOUT_ATTRIBUTION_MARGIN`) parce que le `wait_for` se réveille un cheveu
   en retard. La formulation vit avec ses deux sœurs — `abandoned_call_message`
   et `repeated_call_message` — dans le même module : trois messages de même
   nature, une seule doctrine (message technique anglais, le modèle reformule).

2. **Deux compteurs, deux seuils, une seule condition d'arrêt.**
   `react_elapsed_seconds` continue de ne compter que le raisonnement : son
   seuil ne bouge pas, donc **aucun tour qui aboutit aujourd'hui ne peut être
   coupé demain**. Le temps délégué s'accumule dans une clé distincte,
   `react_tool_seconds`, avec son propre seuil. `react_exit_reason` reste
   l'unique prédicat (ADR-248) et gagne une troisième réponse, `tool_budget`.

   Additionner les deux dans un seul compteur a été écarté : une seule
   délégation à sa borne pipeline (300 s) consommerait **100 %** du budget de
   raisonnement, et couperait des tours qui se terminent aujourd'hui.

3. **La doctrine d'ADR-170 est préservée gratuitement.** Le temps d'attente
   humaine reste exclu pour la raison d'origine : un nœud interrompu ne retourne
   pas, donc il ne débite ni l'un ni l'autre compteur.

4. **Les descriptions des deux panneaux disent ce qu'elles mesurent.** La série
   `react_agent_duration_seconds` n'est pas modifiée — rompre une série
   historique pour corriger une phrase serait payer trop cher. Le temps outil
   est déjà mesuré par `agent_tool_duration_seconds` (le décorateur
   `@track_tool_metrics` est actif quel que soit le mode) : un panneau le
   rapproche, et les descriptions cessent de promettre un total.

## B — Ce que le plafond d'outils coupe, personne ne le voit

96 outils natifs, et jusqu'à 20 serveurs MCP de 40 outils : **896** outils
résolus possibles pour un plafond de **100**. Le sélecteur trie bien — les
outils des domaines détectés survivent en priorité — mais il n'émet qu'un
`logger.warning`.

Et quand un `tool_call` ne trouve pas son outil, la branche correspondante
ajoute un `ToolMessage` et fait `continue`. **Ni log, ni compteur.** Un modèle
qui invente un nom d'outil, ou qui rejoue depuis l'historique un outil que le
plafond vient de retirer, est aujourd'hui structurellement invisible.

Un point est en revanche correct et le reste : le `continue` précède
l'incrément de `productive_calls`, donc **un appel inconnu ne peut pas acheter
d'extension de budget** (ADR-248).

### Décision B

Deux compteurs, et un log là où il n'y en avait pas :

- `react_tool_selector_capped_total` — le plafond a mordu ;
  `react_tools_resolved` (histogramme) montre la distribution **avant** qu'il
  morde, ce qu'un compteur d'événement ne dira jamais.
- `react_unknown_tool_calls_total{reason}`, `reason` valant `not_selected`
  (l'outil existe au catalogue mais n'était pas lié à ce tour — le plafond ou
  le filtrage l'a écarté) ou `unknown` (aucun outil de ce nom n'existe : le
  modèle l'a inventé). **Le nom de l'outil ne devient jamais un label** : il
  vient d'un modèle, sa cardinalité n'est pas bornée. Il part dans le log.

Les deux valeurs de `reason` ne demandent pas le même correctif — l'une dit que
le plafond est trop bas, l'autre que le catalogue est mal présenté. Les
confondre en un compteur unique aurait rendu la métrique inutile.

## C — Une catégorie devinée là où elle devait être déclarée

`infer_tool_category` déduit la catégorie d'un outil des conventions de nommage
(`get_*` → search, `create_*` → create…) et, quand aucune ne s'applique, retourne
`"readonly"  # Default (safe)`.

Ce défaut est sûr pour la donnée et faux pour la classification. Mesuré :
**17 manifestes sur 96** l'atteignent, et quatre d'entre eux écrivent —
`write_spreadsheet_tool`, `append_document_text_tool`,
`set_vacation_responder_tool`, `activate_skill_tool`. Tous sont donc
`initiative_eligible` (la phase d'initiative est censée être en lecture seule)
et `tool_is_mutation() is False` (ils échappent au filet qui reroute un plan
non convergé vers une clarification HITL).

**Aucune écriture non confirmée n'en découle** : ces trois premiers passent par
un brouillon HITL, et leurs manifestes le déclarent. Le défaut est de
classification, pas de sûreté des données.

Ce qui le rend structurel, c'est qu'il **récidive**. `plan_predicates.py`
documente déjà trois victimes de la même classe — `cancel_reminder_tool`,
`edit_image`, `generate_image` — corrigées une par une, sans que rien n'empêche
la quatrième.

### Décision C

**Deviner d'après une convention est légitime ; inventer une intention ne l'est
pas.** La distinction est celle d'ADR-184 : ce qui est mécaniquement réparable
est réparé, ce qui ne peut pas l'être sans inventer reste une erreur.

- Une fonction rend la différence lisible : elle retourne la catégorie quand une
  convention s'applique, et `None` quand aucune ne s'applique.
  `infer_tool_category` garde son contrat public — elle retombe sur `"readonly"`
  comme avant, pour les outils tiers dont nous ne maîtrisons pas les noms.
- **`assert_tool_category_completeness()` refuse de démarrer** quand un manifeste
  du catalogue natif n'a ni catégorie déclarée, ni convention applicable —
  exactement le patron de `assert_trust_registry_completeness` (ADR-085) : appelé
  depuis `run_failfast_validations` **et** depuis un test, donc la CI l'attrape
  avant le boot.
- Les 17 manifestes déclarent leur catégorie. Treize déclarent la valeur qu'ils
  avaient déjà : **aucun changement de comportement**. Quatre déclarent la
  vérité, et entrent de ce fait dans le filet anti-mutation et sortent de
  l'initiative — ce qui est le correctif.

La garde ne s'applique **qu'au catalogue natif**. Un serveur MCP tiers nomme ses
outils comme il veut ; c'est ADR-255 qui traite sa déclaration, et le repli
`readonly` y reste le bon comportement puisqu'une annotation ne peut que
resserrer.

## Conséquences

**Positives**

- Un outil qui ne rend pas la main est borné en ReAct comme il l'est en
  pipeline, avec la même politique, lue au même endroit.
- Un tour ne peut plus dépenser un temps délégué non borné sans qu'aucun
  prédicat ne le voie.
- Le plafonnement du catalogue et les appels d'outils inconnus deviennent des
  séries observables, donc calibrables.
- Un outil natif ne peut plus être classé « lecture seule » par omission.

**Négatives / limites assumées**

- Un outil légitimement plus lent que la borne de sa famille sera coupé en
  ReAct comme il l'est déjà en pipeline. Les bornes sont dans `Settings`, et
  `agent_tool_duration_seconds` permet de les calibrer sur des mesures.
- **La borne temporelle est lue un nœud après avoir été chargée.**
  `react_tool_seconds` est débité par `react_execute_tools` et
  `react_exit_reason` est appliqué au routage qui suit `react_call_model` : un
  appel au modèle sépare donc le dépassement de l'arrêt. C'est délibéré et
  c'est le comportement du frein anti-répétition, dont le commentaire dit
  pourquoi — couper l'arête depuis `execute_tools` sauterait `react_finalize`,
  dont le nœud de réponse lit le contrat. Cet appel n'est d'ailleurs pas perdu :
  il donne au modèle une chance de répondre avec ce qu'il a déjà.
- Les quatre outils reclassés déclencheront davantage de clarifications HITL sur
  des plans non convergés. C'est l'effet recherché, et c'est un changement de
  comportement visible.
- `react_tool_seconds` est une clé d'état supplémentaire : un checkpoint
  antérieur reprend à zéro (migration additive), donc un tour repris n'est
  jamais coupé par un état qu'il n'a pas eu — même propriété qu'ADR-170.
- **Le temps dépensé avant une interruption HITL n'est pas facturé.** Le nœud
  interrompu ne retourne pas, donc son cumul part avec le reste de son travail
  partiel ; à la reprise, les appels sont rejoués et comptés une fois. Le budget
  sous-estime donc un tour interrompu — fail-open de quelques secondes, jamais
  fail-closed, exactement l'arbitrage d'ADR-170 sur le budget de raisonnement.
  `react_tool_executions_before_interrupt_total` mesure déjà ce rejeu.
- La borne temporelle du ReAct reste appliquée **entre** deux appels, jamais au
  milieu d'un appel LLM déjà parti. C'est la limite que le pipeline a aussi.

## Alternatives écartées

- **Additionner le temps outil dans `react_elapsed_seconds`.** Mesuré : une
  seule délégation à sa borne pipeline consomme 100 % du budget de raisonnement.
  Des tours qui aboutissent aujourd'hui seraient coupés.
- **Réécrire `react_agent_duration_seconds` pour inclure le temps outil.** Rend
  la métrique honnête au prix d'une rupture de série historique, alors que
  corriger la description du panneau et rapprocher `agent_tool_duration_seconds`
  donne la même information sans rien casser.
- **Un budget en tokens ou en euros par tour.** Plus proche du coût réel, mais
  les plafonds d'usage existants (`UsageLimitService`) sont un contrôle
  d'**admission** vérifié avant le tour ; en faire un contrôle d'exécution est
  une décision de produit distincte, pas la correction d'une garde qui a cessé
  de couvrir.
- **Rendre `tool_category` obligatoire sur les 96 manifestes.** 75 d'entre eux
  suivent une convention de nommage fiable et testée ; exiger une déclaration
  redondante ajoute du bruit sans ajouter de garantie, et l'assert ne dirait
  plus rien de ce qui compte.
- **Un label `tool_name` sur le compteur d'outils inconnus.** Le nom vient d'un
  modèle : cardinalité non bornée, la série exploserait.
- **Imposer la borne de la famille MCP contre un `timeout_seconds` demandé par
  le planificateur.** Un timeout explicitement demandé est une intention, pas
  un défaut ; et le pipeline l'honorait déjà ainsi. Ce que corrige ADR-256 est
  le PLANCHER que nous appliquons faute de demande — en mode ReAct, où aucune
  demande n'existe, la borne de la famille s'applique toujours.

## Références

- Code : `utils/react_budget.py` (fusionné avec le module ADR-238 du même nom —
  le budget initial et le budget effectif sont la même question posée deux
  fois), `nodes/react_nodes.py`, `nodes/react_history.py` (extrait pour rendre
  sa place au fichier), `orchestration/step_timeouts.py::compute_step_timeout`,
  `registry/catalogue.py::assert_tool_category_completeness`,
  `tools/tool_resolution.py::classify_unresolved_tool_call`,
  `services/react_tool_selector.py`
- Interface : `components/debug/components/shared/BudgetBar.tsx` — une seule
  barre d'allocation pour les deux budgets, là où deux copies du même balisage
  avaient déjà divergé (la seconde était arrivée sans la ligne d'avertissement
  de la première)
- Métriques : `react_tool_selector_capped_total`, `react_tools_resolved`,
  `react_unknown_tool_calls_total`, `agent_tool_duration_seconds` (existante)
- Tableaux : `20-react-browser.json`, `26-product-value.json`
