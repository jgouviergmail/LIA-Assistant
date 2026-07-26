# ADR-153: Taxonomie d'action HITL — classification par verbe et exemples à couverture close

**Statut**: ✅ IMPLEMENTED (2026-07-26)
**Date**: 2026-07-26
**Décideurs**: Équipe LIA
**Contexte technique**: `src/domains/agents/services/hitl/action_taxonomy.py`, `src/domains/agents/services/hitl_classifier.py`, `src/domains/agents/services/orchestration/approval_decision.py`, `src/core/i18n_hitl.py`

---

## Contexte

Quand l'utilisateur répond en langage naturel à une interruption HITL (« oui »,
« plutôt à 15 h », « non annule »), `HitlResponseClassifier` demande à un LLM de
traduire cette réponse en décision `APPROVE / REJECT / EDIT / REPLAN / AMBIGUOUS`.
Le prompt qu'il assemble contient deux éléments dérivés du nom de l'outil en
attente :

1. une ligne `Action type: <type>` — ce que l'utilisateur est en train de confirmer ;
2. un bloc d'exemples *few-shot* propre à ce type — quel paramètre un `EDIT`
   a le droit de toucher.

La dérivation était une échelle `if/elif` de sous-chaînes, dans laquelle un **nom
de domaine** siégeait à l'intérieur d'une branche portant sur un **verbe** :

```python
elif "send" in name or "envoi" in name or "email" in name:
    return ACTION_TYPE_SEND
elif "delete" in name or "suppr" in name:
    return ACTION_TYPE_DELETE
```

Mesuré sur les 96 outils réellement enregistrés : `delete_email_tool`,
`get_emails_tool` et `get_email_details_tool` étaient annoncés comme des
**envois**. Pour une suppression d'e-mail, le prompt affirmait donc au modèle
qu'il s'agissait d'un envoi, lui injectait les exemples d'envoi (« *no send to
jean* → EDIT `{"to": "jean"}` »), et surtout **empêchait sa propre règle de
sûreté de s'appliquer** — le prompt versionné contient : *« If Delete action and
user says Wait, default to REPLAN/REJECT, never APPROVE »*, règle inatteignable
quand le type annoncé n'est pas une suppression. `cancel_reminder_tool`,
`remove_labels_tool` et les quatre outils `update_*` retombaient sur le type
générique.

Le défaut a survécu parce que les tests d'extraction de type ne lui fournissaient
que des noms **fabriqués** et sans ambiguïté (`delete_contact`, `send_email`) —
jamais un nom du catalogue réel — et parce que le fichier entier qui les
contenait ne s'exécutait jamais (voir « Ce qui rendait le défaut invisible »).

## Décision

**1. Classification par verbe, repli par sous-chaîne ordonné.** Un module dédié
`services/hitl/action_taxonomy.py` porte la table `verbe → type d'action`. Les
noms d'outils du dépôt sont `<verbe>_<domaine>_tool` : classer sur le verbe de
tête supprime la collision nom/verbe *par construction*. Un second passage par
sous-chaîne subsiste pour les noms non préfixés (`unified_web_search_tool`,
outils MCP, skills utilisateur) ; il est **ordonné destructif d'abord**, de sorte
qu'un nom ambigu dégrade vers la lecture conservatrice, et il ne contient **que
des verbes** — un nom de domaine y serait exactement le défaut corrigé.

Les verbes dont le type serait une supposition (`activate`, `control`, `run`,
`import`) sont **délibérément absents** : le type générique est honnête, un type
faux induit le classifieur en erreur.

**2. `ACTION_TYPE_UPDATE / FORWARD / REPLY` sont câblés.** Ces trois constantes
étaient déclarées et exportées sans aucun usage. Les brancher rend l'annonce
exacte pour 6 outils, et corrige un second cas de la même famille : une
**réponse** à un e-mail n'a pas de paramètre destinataire (`reply_email_tool`
prend `message_id`, `body`, `reply_all`), alors que les exemples d'envoi
poussaient le modèle à produire `{"to": …}` — un paramètre que l'outil ne peut
pas accepter. Trois blocs d'exemples sont ajoutés (`transfert`, `réponse`,
`modification`).

**3. La couverture des exemples est close, pas silencieuse.**
`assert_examples_coverage()` dérive l'attendu **de la taxonomie elle-même** :
tout type qu'elle peut émettre doit avoir sa section, ou figurer explicitement
dans `EXAMPLES_INTENTIONAL_DEFAULT` (les lectures à faible risque et le
générique). L'assertion tourne au boot (`startup/registries.py`, modèle ADR-085)
et en CI. La garde précédente listait l'attendu **à la main** : elle ne pouvait
par construction pas voir un type nouvellement émissible.

**4. Les avis statiques de reprise sont localisés.** Trois messages français
étaient codés en dur sur le chemin de reprise (`hitl_classifier` en posait deux,
`approval_decision` trois). Ils ne sont pas décoratifs :
`draft_critique.py` **les diffuse mot pour mot** à l'utilisateur. Un utilisateur
allemand ou chinois recevait du français sur la branche HITL la plus fréquente.
La localisation est placée là où la langue est connue : le classifieur n'invente
plus de question (il ne connaît pas la langue de l'utilisateur), le *mapper* de
reprise émet `HitlResumeMessage` dans les 6 langues, et `service.py` lui passe la
langue lue dans l'état checkpointé. Effet de bord corrigé au passage : la seconde
branche de rétrogradation **écrasait** une question produite par le LLM, plus
spécifique que n'importe quel repli.

**5. `_parse_result` tient son contrat.** Sa docstring promettait `ValueError` ;
le code re-levait n'importe quelle exception, si bien qu'une charge non-textuelle
sortait en `AttributeError` — l'échec dépendait du provider configuré. Toute
défaillance de parsing sort désormais en `ValueError`, le type que les appelants
attrapent. Dans la même veine, `rejection_reason` ne contient plus le message
d'exception brut : il nomme le **type** d'échec, parce que cette chaîne est
résumée dans le prompt du nœud de réponse (règle #18 — pas de charge brute vers
un LLM) ; le message complet reste dans le log structuré.

## Ce qui rendait le défaut invisible

Dix fichiers de test portaient un `pytestmark = pytest.mark.skipif(not
os.getenv("OPENAI_API_KEY"), …)` au niveau module — copié-collé d'un fichier à
l'autre. **219 fonctions de test n'avaient jamais tourné** — 234 cas une fois le
paramétrage déplié, et 225 fonctions en comptant les gardes posées test par test
dans un onzième fichier. Un test sauté est vert, rien ne le
signale. Réactivées avec une clé factice, **142 revenaient au rouge** (125
échecs, 17 erreurs) contre 92 vertes — écrites contre
`AIMessage.content` avant la migration LangChain 1.x vers `.text`, et contre un
classifieur antérieur à la sortie structurée. Le fichier de 70 tests du
classifieur en faisait partie, dont les 12 tests d'extraction de type.

Deux traitements selon la nature réelle du fichier :

- **Réparable en test hermétique** → la garde tombe, le harnais est corrigé, le
  fichier tourne en CI. Huit suites soldées : `test_hitl_classifier` (**+75** :
  70 réparés + 5 ajoutés pour le chemin primaire de sortie structurée, que les
  70 n'exerçaient pas), `test_phase32_e2e_integration` (**23**),
  `test_draft_executor` (**30**), `test_resumption_strategies` (**25**),
  `test_graph_build` (**13**), `test_hitl_question_streaming` (**12**),
  `mixins/test_streaming` (**11**), `test_context_cleanup_on_reset` (**6**).
  Les harnais manquants : un store LangGraph en mémoire au lieu du store
  Postgres, un registre d'agents stub au lieu de douze agents réels, un
  `get_tcm_session` neutralisé.
- **Appelle un vrai provider ou pilote le graphe entier** → c'est une **éval**
  ou un vrai bout-en-bout, pas un test de code : `services/test_hitl_classifier`
  (27), `test_hitl_cache_integration` (5), `test_router_state` (6) portent
  désormais `pytest.mark.e2e` **en plus** de la garde d'identifiant. L'exclusion
  devient visible dans la commande CI (`-m "not e2e"`) au lieu d'être un
  silence. L'invariant que `test_router_state` était censé protéger — le routeur
  écrit dans `routing_history`, jamais dans `messages` — est désormais prouvé
  **hermétiquement au niveau du nœud** (16 tests, `test_router_state_isolation`)
  : il tenait à la valeur de retour d'UNE fonction, pas au graphe complet.

Ce que la réanimation a exhumé, au-delà des API migrées (`AIMessage.content` →
`.text`, `tracker.get_summary()` → `get_summary_dto()`, `llm` scindé en
`tool_question_llm`/`plan_approval_llm`) :

- un **alias rétro-compatible** `draft_executor._EXECUTOR_REGISTRY` que 11 tests
  patchaient — sans effet, puisque le moteur lit `EXECUTOR_REGISTRY` : ils
  exécutaient le **vrai** exécuteur d'e-mail contre une vraie résolution de
  connecteur. L'alias est supprimé, une garde vérifie qu'il ne revient pas ;
- des mocks qui ne ressemblaient pas à l'objet réel : `AsyncMock()` dont le
  `return_value` est un `AsyncMock`, si bien que `snapshot.values.get(...)`
  rendait une **coroutine** et poussait chaque test reject/edit dans son repli
  d'erreur, où il assertait — en croyant couvrir le chemin nominal ;
- des tests **non hermétiques** : appels réseau réels vers un provider (401
  observé), connexions Postgres à 5 s de timeout (41 s pour un seul fichier,
  ramené à 6 s), `async for i, x in enumerate(agen)` qui n'est pas une boucle
  mais un `TypeError`.

La non-récurrence est structurelle : `tests/unit/test_no_env_skipped_suite_guard.py`
échoue sur tout module qui se désactive entièrement faute d'identifiant de
provider, sauf s'il déclare aussi un marqueur exclu (`integration`/`e2e`/`slow`)
— l'échappatoire sanctionnée, celle qui reste lisible dans la commande. Sa liste
d'exemption est **décroissante uniquement** et chaque entrée porte le nombre de
tests qu'elle masque, pour que le coût reste visible. Elle est **vide** : plus
aucune suite ne se désactive en silence.

## Conséquences

**Positives**
- Un outil destructif ne peut plus être annoncé autrement — invariant vérifié sur
  le **catalogue réel** (96 outils), pas sur des noms inventés.
- Un type d'action livré sans exemples refuse de démarrer l'application.
- Les six langues reçoivent les avis de reprise dans leur langue.
- Le job CI « agents » passe de **978 à 1158** tests exécutés, **0 sauté**
  (202 auparavant) : chaque test y tourne, ou est exclu par un marqueur lisible.

**Négatives / limites**
- Les 3 blocs d'exemples ajoutés modifient le prompt : effet mesurable en
  production seulement (aucune éval automatisée n'est branchée en CI, par choix).
- Le repli par sous-chaîne reste heuristique pour les outils MCP, dont les noms
  ne suivent aucune convention imposable — d'où l'ordre destructif d'abord.
- Trois suites (38 tests) ne tournent que sur demande avec une clé — elles
  appellent un provider payant ou pilotent le graphe entier ; leur exclusion
  est désormais lisible dans la commande CI au lieu d'être silencieuse.

## Alternatives écartées

- **Réordonner l'échelle `if/elif`** (retirer `"email"`, remonter `delete`) :
  corrige les trois cas mesurés sans corriger la classe. Le prochain nom de
  domaine glissé dans une branche de verbe repasse.
- **Supprimer `ACTION_TYPE_UPDATE/FORWARD/REPLY`** comme code mort : c'était
  l'autre lecture cohérente de la doctrine. Écartée parce que le défaut de
  paramètre sur `reply_email_tool` prouve que la distinction porte une
  information utile au classifieur.
- **Traduire les avis dans le classifieur** : il faudrait lui passer la langue,
  alors que la couche de rendu la connaît déjà. Le classifieur reste agnostique.
- **Supprimer les 27 tests d'éval** : ils n'ont jamais tourné et n'en ont pas le
  droit en CI (coût, non-déterminisme). Conservés parce qu'exécutables à la
  demande avec une clé, et désormais honnêtement étiquetés.

## Références

- [ADR-085](ADR_INDEX.md#adr-085) — modèle d'assertion de complétude au boot
- [ADR-132](ADR_INDEX.md#adr-132-hitl-approval-cards) — cartes d'approbation HITL
- `src/domains/agents/prompts/v1/hitl_classifier_examples.txt` — blocs *few-shot*
- `tests/unit/domains/agents/services/hitl/test_action_taxonomy.py` — invariants sur le catalogue réel
- `tests/unit/domains/agents/services/hitl/test_hitl_no_french_e2e.py` — garde « aucun français » étendue à la branche AMBIGUOUS
