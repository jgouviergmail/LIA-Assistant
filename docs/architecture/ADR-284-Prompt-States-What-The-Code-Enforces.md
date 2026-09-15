# ADR-284 — Un prompt énonce ce que le code impose, et rien d'autre

- **Statut** : Accepté
- **Date** : 2026-09-12
- **Amende** : ADR-184 (une borne imposée est publiée — ici la borne publiée
  était FAUSSE), ADR-025 (versionnage des prompts — le repli inline est retiré),
  ADR-245 (une valeur stockée ne passe jamais par un chemin qui la reformule),
  ADR-248 (le prompt ReAct promet ce que le tour peut faire), ADR-263 (la
  politique de mutation d'un outil, pas le prompt, décide qui est consulté),
  ADR-272 (un seul lecteur de l'usage fournisseur, sur TOUS les sites)
- **Périmètre** : `prompts/v1/` (131 fichiers, 20 nouveaux), `prompts/__init__.py`
  (`get_response_prompt`), `core/prompt_store.py` (`parse_prompt_sections`),
  `core/i18n.py` (`get_language_name`), `hitl/question_generator.py`,
  `brave_tools.py` + `brave/catalogue_manifests.py` + `brave_agent_builder.py`,
  `smart_planner_service.py`, `sub_agents/catalogue_manifests.py`,
  `nodes/react_nodes.py`, `briefing/` (schéma `BriefingWindows`, six locales),
  `psyche/engine.py` + `psyche/service.py`, `rag_spaces/retrieval.py`, quatre
  réglages `*_prompt_version` supprimés, cinq lecteurs manuels de
  `usage_metadata`, et trois gardes CI nouveaux

## Contexte

L'audit des prompts du 2026-09-12 (113 fichiers, 61 nés ou modifiés depuis la
revue de juillet) a trouvé les gardes existantes vertes — `Literal` en phase
avec les fichiers, marqueur de cache présent, noms d'outils exacts — et,
derrière elles, six endroits où le modèle lisait quelque chose de **faux**,
chacun prouvé par assemblage du prompt réel puis mesuré sur Docker dev :

| Défaut | Ce que le modèle lisait | Depuis |
|---|---|---|
| Générateur de questions HITL | `Tool name: {tool_name}` — trois placeholders sans producteur, et les exemples `{{…}}` d'un gabarit `str.format` jamais formaté | v1.0.0 |
| Prompt de réponse | `<RAGDocuments>` (« synthesize ») DANS `<UserDocuments>` (« always cite »), et à chaque tour sans contexte **246 jetons** d'enveloppes vides sous leur consigne, dans la queue jamais cachée ; toute valeur échappée DEUX fois, si bien que `r={x}` arrivait `r={{x}}` | v1.25.3 |
| Brave `count` | prompt « max 20 / 50 », manifeste `maximum=20/50` publié au planner, outil `min(count, 10)` — la borne publiée était fausse, l'ADR-184 pointé à l'envers | v1.0.0 |
| Bloc de délégation | « bounded 2-pass » (boucle ReAct à 20), « 4 outils dont Wikipedia » (3, sans), « timeout 120 » (plancher 300), et le NOM d'une variable d'environnement à la place de son nombre ; le manifeste de l'outil disait le contraire du bloc sur `$steps` | v1.20.5 |
| ReAct | `<Computation>` promet `run_python_tool` sur le démonstrateur où il n'est pas enregistré ; « mutation tools require user approval automatically » faux pour 22 outils `reversible`/`artefact`/`sandboxed` | ADR-249 |
| Briefing | « 14 days » en prose, descriptions « Default 14 / 5 », constantes 7 / 10, six locales « 14 prochains jours » — cinq autorités pour une fenêtre | v1.18.0 |

Trois mesures ont réorienté la correction avant tout code. Le défaut HITL n'a
**aucun effet mesurable** (24 appels, 0 fuite, chaque question nomme ses
arguments) : c'est une dette d'hygiène, pas de qualité. La contradiction
cite/synthétise n'a **aucun effet** non plus (12/12 réponses citent quelle que
soit l'enveloppe) — parce qu'une TROISIÈME consigne, dans l'en-tête que
`retrieval.py` collait au contenu, décidait à la place des deux autres. Et
`get_language_name("zh")` rendait `"zh"` : le lot « nommer la langue » aurait
fait fuir un locale frontend tel quel.

## Décision

**Un prompt énonce ce que le code impose, et rien d'autre.** Cinq règles, une
garde chacune quand elle se mécanise.

1. **Tout `{placeholder}` d'un fichier a un producteur, et un fichier qui
   contient `{{` est rendu par `.format()`.**
   `test_prompt_placeholders_are_produced.py` lit, par fichier, les modules qui
   citent son nom (plus un renderer DÉCLARÉ quand le nom voyage par une
   constante — `RENDERED_BY`, chaque entrée vérifiée par le même AST) et les
   clés qu'ils produisent. Il a isolé exactement le défaut HITL sur 113
   fichiers ; la syntaxe `{{var}}` d'un fournisseur tiers (ElevenLabs) est
   déclarée, jamais devinée.

2. **Une consigne par contexte, dans le fichier, émise seulement quand le
   contenu existe.** `response_context_sections.txt` déclare, en ordre
   d'injection, `clé|Balise|consigne` ; `get_response_prompt` n'enveloppe plus
   rien lui-même et n'échappe plus rien (le nœud de réponse échappe le prompt
   entier UNE fois). L'en-tête RAG (`rag_context_format.txt`) NOMME son contenu
   sans l'instruire. Un tour nu ne porte plus aucune enveloppe vide.

3. **La borne publiée est la borne imposée, depuis UNE constante.**
   `BRAVE_WEB_SEARCH_MAX_COUNT` / `BRAVE_NEWS_SEARCH_MAX_COUNT` (les maxima de
   l'API, 20 et 50 — Brave facture la requête, pas le résultat) nourrissent le
   manifeste, le rognage de l'outil, la description du paramètre et le prompt
   de l'agent ; un test lit les quatre. Les outils Brave portent enfin
   `@rate_limit` (règle systémique, `brave_rate_limit_*`).

4. **Un nombre vient d'un réglage, un fait vient du code qui l'applique.** Le
   bloc de délégation est un fichier versionné dont chaque nombre est LU dans
   `settings` ; le manifeste dit la même chose que lui (les données utilisateur
   passent par `$steps`, le plafond a UNE autorité). Le bloc `<Computation>`
   n'est rendu que si `run_python_tool` est lié ET la capacité allumée
   (`_sandbox_available`), avec le budget qu'impose `python_sandbox_tools`. La
   ligne « approval automatically » dit désormais que c'est l'OUTIL qui décide.
   Les fenêtres du briefing sont publiées (`CardsResponse.windows`) et l'UI les
   interpole (`birthdays.empty_one/_other`) ; les descriptions « Default N » sont
   dérivées des constantes et un test les compare.

5. **La prose d'un prompt n'habite jamais un `.py`, un repli inline non plus.**
   Douze sites ont migré : un fichier par bloc (`hitl_item_filter_prompt`,
   `heartbeat_decision_user_prompt`, `smart_planner_mcp_format_reference_prompt`…)
   et, pour les scaffolds d'une phrase, un fichier de lignes `clé|gabarit` lu
   par **un** parseur, `parse_prompt_sections` (`core/prompt_store.py`), qui a
   remplacé trois copies. Les goldens psyche ont été capturés AVANT le
   déplacement. `load_prompt_with_fallback` est supprimé avec ses deux replis :
   l'un avait déjà perdu la règle du fichier (« an interruption still has to
   earn itself »), et un fichier manquant est un déploiement cassé qui doit
   échouer fort. Les messages d'outil restants sont en anglais technique
   (ADR-256).

Corollaires : `get_language_name` vit dans `core/i18n.py` et **normalise avant
de nommer** (le lookup brut a quitté `i18n_types`) ; quatre réglages
`*_prompt_version` sans lecteur sont supprimés et un garde exige un lecteur
par réglage ; `telephony_agent_prompt` rejoint `MARKER_REQUIRED` et tout
fichier portant le marqueur doit y figurer ; les cinq lecteurs manuels de
`usage_metadata` passent par `tokens_from_usage_metadata` — le heartbeat et la
livraison entre pairs passaient le TOTAL d'entrée à un tarificateur qui ajoute
le cache par-dessus, et lisaient 0 cache sur OpenAI ; `token_efficiency`
mesure sur l'entrée entière (un prompt entièrement caché n'est pas une entrée
nulle).

## Conséquences

- Le préfixe statique de quatre prompts change : une invalidation du cache
  fournisseur, une fois, au déploiement.
- Le prompt de réponse perd ~246 jetons par tour nu et une consigne sur un
  contenu absent (`Weave ONE or TWO`) à chaque tour.
- `CardsResponse`, `BriefingResponse` portent `windows` (requis) : les mocks
  e2e complets le portent aussi.
- Ce que l'ADR ne règle pas : la migration des tables de vocabulaire psyche
  (`MOOD_EXPRESSION_GRAMMAR`…), données et non prose, restées dans
  `psyche/constants.py` ; le déplacement du bloc de délégation avant le
  marqueur de cache (~700 jetons par plan), qui demanderait une entrée
  `ALLOWED_BEFORE_MARKER` à deux variantes.
