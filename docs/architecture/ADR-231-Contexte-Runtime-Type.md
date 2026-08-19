# ADR-231 : le contexte d'exécution devient typé — et LIA n'adopte pas Agent Server

**Statut**: 🟡 PARTIELLEMENT IMPLÉMENTÉ (2026-08-19) — voir « État de l'implémentation »
**Date**: 2026-08-19
**Décideurs**: Propriétaire (arbitrages « F1 = amorce du lot 2 », « lot 3 instruit puis reporté ») + Équipe LIA

## Contexte

Une étude d'opportunité sur « LangChain Agent Server v0.13 — standardisation AAA
et contextes » a produit deux réponses distinctes. La première est un refus. La
seconde est un chantier, et il n'a jamais eu besoin d'Agent Server.

### 1. Agent Server est incompatible avec LIA, pour cinq raisons indépendantes

**Licence.** `langgraph-api` — le runtime d'Agent Server — est sous **Elastic
License 2.0** (métadonnées PyPI, et le fichier `LICENSE` extrait de la roue
`0.13.0rc5`). LIA est sous **AGPL-3.0-or-later** (`LICENSE`,
`apps/api/pyproject.toml`, les deux `package.json`). Le modèle de déploiement
d'Agent Server charge **le graphe de l'hôte dans son propre processus**
(`langgraph.json`, clé `graphs`), et `HttpConfig.app` va jusqu'à monter le
FastAPI de l'hôte dedans : c'est une œuvre combinée, pas une simple agrégation.
L'AGPL §10 interdit d'imposer aux destinataires les restrictions supplémentaires
que l'ELv2 impose.

**Maturité.** La v0.13 n'a **aucune version stable** : le dernier artefact publié
est `0.13.0rc5` (2026-08-17) ; la ligne stable en cours est `0.12.6`. Le pipeline
de release qualifiée (ADR-215) ne peut pas livrer une release candidate.

**Redondance.** Agent Server apporte threads, runs, assistants, crons et file de
tâches durable. LIA possède déjà, et a durci, `conversations` (repository de
1 207 lignes, messages, feedback, archives, export RGPD), `background_runner`,
`scheduled_actions` avec `FOR UPDATE SKIP LOCKED`, APScheduler derrière une
élection de leader, `AsyncPostgresStore`, et un flux SSE avec keepalive, gates et
HITL.

**L'AAA ne se transpose pas.** `langgraph_sdk.Auth` gouverne exactement cinq
ressources (runs, threads, crons, assistants, store). Il ignore tout des sessions
d'appareil, du step-up, de WebAuthn/TOTP, des pairs, des plafonds d'usage et des
~70 routeurs de `src/api/v1/routes.py`. L'adopter donnerait **deux** plans
d'autorisation, pas un. La frontière est documentée dans le code même de
LangGraph : `Runtime.server_info` est *« None when running open-source LangGraph
without LangSmith deployments »*.

**Ressources.** La production est de 17 services sur un Raspberry Pi 5 —
3 376 Mo réservés, 12 736 Mo de plafonds, 8,6 CPU de plafonds — l'API réservant à
elle seule 2 Go. Un second runtime Python chargeant le même graphe, plus grpcio,
protobuf et uvloop, n'y tient pas.

La variante « Studio en développement seulement » est également refusée :
`build_graph()` dépend du registre global qu'initialise tout le lifespan, donc un
`langgraph.json` devrait dupliquer le chemin de boot et le maintenir en phase —
pour une interface de debug qu'ADR-209 a déjà livrée en interne.

### 2. Le contexte d'exécution existait déjà, à moitié, et personne ne le lisait

Ce que LIA fait aujourd'hui, mesuré :

- `graph.astream(context=context_dict)` est appelé sur les deux chemins
  (`services/orchestration/service.py`), avec un dictionnaire de trois clés.
  **Zéro fichier de `src/` ne lit `runtime.context`.** Le commentaire qui le
  justifiait prétendait alimenter `ToolRuntime` — c'était faux.
- `_build_tool_runtime` (`orchestration/parallel_executor.py`), **unique** point
  de construction partagé par le mode pipeline et le mode ReAct, câble
  `context=None` en dur. Un run porte donc un contexte qu'aucun outil ne peut
  voir.
- Le graphe ne déclare **aucun** `context_schema`, donc le contexte est un `dict`
  brut : aucune validation, aucune couverture MyPy.
- Le vrai plan de contexte est `config["configurable"]` : **17 clés** écrites en
  un point, **43 fichiers** lecteurs, dont quatre clés privées non publiées
  (`__deps`, `__browser_context`, `__user_message`, `__side_channel_queue`) — un
  contrat imposé mais non publié, la classe qu'ADR-184 avait déjà nommée.
- La même identité y circule **sous deux clés et deux types** : `user_id` reçoit
  un `uuid.UUID` brut au point d'entrée mais un `str` depuis l'exécuteur
  parallèle, tandis que `langgraph_user_id` duplique la valeur en `str` sur
  **25 sites de lecture**, justifié par un commentaire sur LangMem —
  **`langmem` n'est pas installé**. La preuve que l'ambiguïté est subie :
  `parse_user_id(str | UUID)` n'existe que pour l'absorber.

Et une lacune de couverture rendait tout cela dangereux à corriger : **aucune
garde CI ne convertissait un outil vers le schéma exposé au LLM**. Ni
`test_tool_registry_smoke`, ni aucun autre fichier de `src/` ou `tests/`
n'appelait `convert_to_openai_tool` ; les trois tests utilisant `bind_tools`
passent par un faux modèle qui ignore ses outils.

## Décision

**Agent Server : NON.** Aucune adoption, ni en production, ni en développement.

**Contexte d'exécution typé : OUI**, sur LangGraph OSS seul — `context_schema` et
`Runtime[ContextT]` sont dans le paquet MIT déjà installé.

### 1. Fermer d'abord la lacune de garde

`tests/unit/domains/agents/tools/test_tool_schema_contract.py` convertit **chaque**
outil enregistré vers son schéma OpenAI et vérifie qu'aucun argument injecté
(`runtime`, `config`, `state`, `store`, `tool_call_id`) n'atteint le modèle. Cette
garde a une valeur autonome — le mode de défaillance est atteignable, mesuré : une
annotation nue `runtime: ToolRuntime | None = None` lève
`PydanticInvalidForJsonSchema` et rend l'outil impossible à lier à un modèle. Elle
est aussi l'oracle de non-régression de la migration qui suit.

### 2. Un contrat gelé, construit en un point, injecté en trois

`LiaRuntimeContext` est une dataclass gelée portant les 17 valeurs du point
d'entrée, avec deux corrections intégrées : `user_id` devient un `uuid.UUID`
**canonique et unique** (`langgraph_user_id` disparaît), et les quatre clés
privées deviennent des champs nommés et typés.

Elle est construite en **un** point (le chokepoint existant, dans un module dédié
car `services/orchestration/service.py` est gelé à 713 SLOC) et injectée en
**quatre** : `graph.astream`, `_build_tool_runtime`, `skill_location_context`, et
l'`ainvoke` du sous-agent ReAct — qui reçoit le contexte du parent **dérivé**
(`derive_sub_agent_context`), jamais reprojeté à la main.

### 3. L'ordre n'est pas négociable, et il est mesuré

Les quatre quadrants ont été simulés :

| annotation | contexte | résultat |
|---|---|---|
| `ToolRuntime` nu | `None` | propre *(état actuel)* |
| `ToolRuntime[Ctx, …]` | `None` | **propre** *(état intermédiaire)* |
| `ToolRuntime[Ctx, …]` | instance | **propre** *(état final)* |
| `ToolRuntime` nu | instance | **avertissement Pydantic à chaque appel d'outil** |

Donc : **paramétrer les 117 signatures d'abord, remplir le contexte ensuite.**
L'ordre inverse pollue stderr en production comme en CI.

### 4. La bascule et l'assert sont un seul commit

Simulé : avec `context_schema` déclaré mais aucun contexte passé, une reprise
après interruption **réussit silencieusement** et chaque nœud lit `None`. Livrer
la bascule un déploiement avant l'assert ouvrirait exactement cette fenêtre sur
les conversations HITL en vol. Un commit, ou aucun.

L'assert suit la doctrine ADR-085 : un contexte absent ou incomplet fait échouer
**bruyamment**, jamais dégrader.

### 5. La lecture du contexte hors nœud passe par le ContextVar, pas par un sac

`get_runtime()` traverse `asyncio.gather`, `asyncio.to_thread`,
`asyncio.create_task`, et même une tâche détachée attendue après la fin du run
(simulé). L'exécuteur parallèle tourne dans un nœud, derrière un `gather` : il lit
donc le contexte directement. **Aucune nouvelle clé n'est ajoutée à
`configurable`** — ce serait réintroduire le sac que ce chantier supprime. Hors
d'un run, la lecture lève `RuntimeError` : bruyante, jamais silencieuse.

## Ne pas corriger — constats réfutés

Consignés pour qu'aucune session future ne « répare » un non-problème. Chacun a
été suspecté, puis réfuté par lecture du code ou par simulation.

- **La mutation en place de `configurable["oauth_scopes"]` dans le planificateur
  fuirait.** Non : LangGraph remet à **chaque nœud une copie fraîche** de
  `configurable`. Ni l'appelant, ni le run suivant, ni la branche parallèle sœur
  ne sont pollués. La valeur atteint `skill_bypass` parce qu'elle descend l'arbre
  d'appel du nœud lui-même.
- **Les onze signatures `runtime: ToolRuntime | None` nues casseraient leurs
  outils.** Non : ce sont toutes des fonctions privées `_xxx` ou des méthodes,
  aucune n'est un `@tool`. Mesuré : 105 outils, 0 échec de conversion.
- **Le mélange de 113 annotations `Annotated[...]` et 39 nues serait nuisible.**
  Non : les deux formes masquent correctement `runtime` au modèle. Inélégant,
  pas fautif.
- **Un `RunnableConfig` ne portant que `thread_id` amputerait le contexte.** Non :
  ces trois sites ne font que `aget_state` ou lire un checkpoint.
- **Les actions planifiées contourneraient le point d'entrée.** Non : elles
  passent par `AgentService.stream_chat_response`.
- **`@auto_save_context` ne serait jamais appliqué.** Non : il l'est via
  `connector_tool(context_domain=...)`.
- **`__parent_thread_id`, `resolved_person_names`, `node_name` seraient
  orphelines.** Non : toutes écrites ailleurs.
- **Le contexte fuirait dans le checkpoint.** Non : retesté avec une sentinelle
  jamais écrite en état, elle est absente du dernier checkpoint **et des trois
  entrées d'historique**. (La première mesure était un faux positif introduit par
  le test lui-même, dont un nœud écrivait la valeur dans l'état.)
- **`@pytest.mark.unit` violerait `--strict-markers`.** Non : le marqueur est
  enregistré à l'exécution par `apps/api/tests/conftest.py`.
- **Le frontend aurait un contrat sur ce contexte.** Non : toutes les occurrences
  de `configurable` sous `apps/web/` sont des descripteurs de propriété
  JavaScript. Ce chantier est purement backend.

## Alternatives écartées

- **Adopter Agent Server malgré la licence** : les cinq bloquants sont
  indépendants ; en lever un ne lèverait pas les autres.
- **Monter Agent Server en développement seulement pour LangGraph Studio** :
  duplique le chemin de boot pour une surface de debug déjà livrée (ADR-209).
- **Adopter le format de fil `langchain-protocol`** : réécriture complète du
  transport de chat des deux côtés, pour aucun gain visible par l'utilisateur.
  Le vocabulaire SSE de LIA (`start`, `chunk`, `end`, `error`, `hitl_required`)
  reste.
- **Fusionner les 9 `ContextVar` de `core/context.py` dans `LiaRuntimeContext`** :
  ils sont à portée de **requête**, pas de **run**. Ce serait une seconde
  migration, distincte.
- **Supprimer `context=context_dict` plutôt que le typer** (arbitrage
  propriétaire) : il est **conservé** comme amorce du contexte typé ; seul son
  commentaire mensonger est corrigé dans l'intervalle.
- **Ajouter les onze clés manquantes à la reprojection du sous-runner ReAct**
  plutôt que de dériver du parent : ajouter des clés laisse la classe de bug
  intacte — le prochain champ serait perdu de la même façon.

## Conséquences

### Acquis

- Une garde CI couvre enfin le schéma que le LLM voit réellement, et elle a été
  prouvée capable d'échouer (trois mutations injectées, trois détections).
- Une identité, un type : `uuid.UUID`, sur un seul nom de champ.
- Le contrat de contexte est publié et typé — ce que MyPy peut vérifier, une
  relecture n'a plus à deviner.
- La migration est **déployable sans casse** : un fil interrompu avant la bascule
  reprend après, et un fil démarré après reprend avant (rollback vérifié).

### Coût assumé

- 117 signatures d'outils touchées mécaniquement, sans changement de comportement,
  avant tout gain visible.
- Les lectures migrent par vagues : `configurable` reste source de vérité jusqu'à
  la dernière, donc les deux plans coexistent le temps du chantier — coexistence
  bornée par un ratchet shrink-only qui interdit tout nouveau lecteur.

### Reporté par décision propriétaire

**Lot 3 — exposer LIA comme serveur MCP.** Instruit jusqu'à la conception
d'authentification, puis reporté (« assez structurant, pas de besoin immédiat »).
Ce qui est établi et ne sera pas à réinstruire :

- Faisabilité prouvée : `mcp` 2.0.0 est **déjà dans le lock** (MIT),
  `MCPServer.streamable_http_app()` se monte dans le FastAPI existant, l'identité
  authentifiée atteint le code outil et **8 appelants concurrents restent isolés**.
- Deux pièges de déploiement : la protection anti-DNS-rebinding rejette tout en
  **421** si l'hôte n'est pas listé ; et monter le serveur place les métadonnées
  RFC 9728 sous le préfixe, là où **aucun client ne les cherche**.
- **Le bloquant n'est pas l'authentification, c'est le HITL** : il est appliqué
  dans les **nœuds du graphe**, jamais dans l'outil. Un client MCP appelant un
  outil directement ne déclenche aucune confirmation. Mesuré sur le catalogue :
  63 outils en lecture seule, 14 mutations à brouillon (inertes hors du graphe),
  et **4 mutations sans aucune garde**. Une exposition MCP est donc **lecture
  seule** en phase 1.
- Authentification retenue : jeton personnel **par utilisateur**, haché en
  SHA-256 — jamais bcrypt, mesuré à 163 ms contre 0,0004 ms par vérification, et
  une vérification a lieu à **chaque** requête MCP. Le mode `static_headers` de
  Claude est **refusé** : le secret y est partagé par l'organisation, incompatible
  avec des données personnelles par utilisateur.

**A2A est refusé** : le domaine `peers` est intra-instance et humain-à-humain, pas
de l'interopérabilité entre systèmes d'agents distincts.

## État de l'implémentation

**Atterri et vérifié** (MyPy strict propre sur 1 156 fichiers) :

- La garde de contrat sur le schéma d'outil, prouvée capable d'échouer (trois
  mutations injectées, trois détectées).
- Les corrections isolées : branches mortes supprimées et factorisées, fallbacks
  de langue et de fuseau canoniques, commentaires rendus véridiques, montée
  couplée `langchain-core` 1.5.6 / `langchain-openai` 1.5.2 (le risque nommé sur
  `_get_request_payload` clos par comparaison directe des signatures).
- `LiaRuntimeContext` gelé, construit en un point, injecté aux trois autres ;
  `context_schema` déclaré sur le graphe principal **et** sur le sous-agent ReAct ;
  assert de complétude au nœud d'entrée ; 145 annotations `ToolRuntime`
  paramétrées ; le sous-runner **dérive** son contexte au lieu de le reprojeter.

**Reste à faire — la récolte, pas la fondation** : les ~43 fichiers qui lisent
encore le contexte dans `config["configurable"]` n'ont pas migré. C'est délibéré
et sans risque : `configurable` reste peuplé et source de vérité, les deux plans
coexistent, et l'état actuel est cohérent et déployable. Tant que la migration
n'est pas faite, une valeur reste lue en deux endroits — le gain de typage est
acquis sur les signatures et sur le contrat, pas encore sur les lectures.

**Conséquence à connaître** : le contexte du sous-agent ReAct est désormais
complet (dérivé), mais son `configurable` reste la projection à 7 clés. Un
lecteur qui passe encore par `configurable` dans un sous-run voit donc toujours
les 11 clés manquantes. Cela disparaît exactement quand la migration des lectures
aboutit — pas avant.

## Références

- ADR-085 (asserts de complétude), ADR-112 (manifestes et lockfiles), ADR-123
  (décomposition du lifespan), ADR-184 (une contrainte imposée doit être publiée),
  ADR-194 (références mortes), ADR-215 (pipeline de release qualifiée).
- Spécification : `docs/superpowers/specs/2026-08-19-runtime-context-standardization-design.md`.
- Plan d'implémentation : `docs/superpowers/plans/2026-08-19-runtime-context-standardization.md`.
- `apps/api/src/domains/agents/context/runtime_context.py`,
  `apps/api/src/domains/agents/services/orchestration/service.py`,
  `apps/api/src/domains/agents/orchestration/parallel_executor.py`,
  `apps/api/tests/unit/domains/agents/tools/test_tool_schema_contract.py`.
