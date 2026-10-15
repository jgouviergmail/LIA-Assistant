# ADR-303 : un échec d'outil est DIT, jamais deviné

**Statut** : accepté — 2026-09-22
**Amende** : ADR-184 (une contrainte enforcée est publiée), ADR-182 (jamais un diagnostic inventé), ADR-185 (un compte affiché est exact), ADR-248 (un tour finit quand sa réponse part), ADR-254 (classer structurellement), ADR-263 (les registres sont la référence), ADR-286 (la projection ReAct)

## Contexte — ce que la personne lisait

Audité le 2026-09-09 sur la v1.44.0, re-mesuré le 2026-09-22 sur la v1.47.1 : **aucune ligne du code fautif n'avait bougé** en vingt ADR, et le volume avait été multiplié par six (61 → 378 échecs d'outils au registre, dont 164 sur sept jours).

Quatre ruptures, chacune entre un producteur et un lecteur qui ne parlaient pas la même langue :

1. `mappers.py` publiait `status="failed"` ; le formateur de réponse ne connaissait que `success`, `error` et `connector_disabled`. `failed` tombait dans un `else` qui écrivait « ❓ plan_executor : Statut inconnu (failed) » **et jetait le champ `error`**. Les deux seules branches qui restituaient `error` étaient mortes : `error` et `connector_disabled` n'avaient **aucun producteur**.
2. Le canal d'honnêteté (`runtime_failures_directive`) lisait `step["status"] == "error"` — une clé qu'**aucun écrivain de `completed_steps` n'écrit**. Le lecteur renvoyait `[]` depuis toujours, et son test figeait la forme fictive.
3. Côté ReAct, le même lecteur exigeait un corps de `ToolMessage` en JSON portant `success: false`, alors que `compose_tool_message` n'émet que la **prose** de l'outil. Aucun échec ReAct n'a jamais atteint la directive — et un test affirmait que c'était voulu.
4. `track_tool_metrics` comptait `success="true"` pour **tout retour sans exception**, y compris `UnifiedToolOutput.failure(...)`. Or c'est la façon documentée dont un outil échoue. Le taux de succès valait 1,0 par construction : sa recording rule et les deux alertes qui la lisent — dont une PagerDuty — ne pouvaient pas se déclencher.

### Ce que ça produisait, mesuré en production

Le 09/09, trois `fetch_web_page_tool` refusés par un anti-bot : la personne a lu « statut inconnu, probablement un délai ou une restriction ». Inutile, mais honnête.

Depuis, c'est pire — sans consigne, le modèle **invente une cause plausible** :

| Population | Réponses | Avec un diagnostic de configuration |
|---|---|---|
| Tours où un outil a échoué | 21 | **7 (33 %)** |
| Tours sans échec (témoin) | 142 | **0** |

Le cas le plus net est un briefing quotidien de 6 h, en ReAct. Les jours où les outils agenda, tâches et mail échouent, la personne lit : « aucun service Calendar n'est **configuré** », « aucun service Tasks n'est **connecté** », « aucun service Email n'est **configuré** », suivis d'une marche à suivre. Or `GOOGLE_CALENDAR`, `GOOGLE_TASKS` et `GOOGLE_GMAIL` sont **tous `ACTIVE`**. Sur 14 briefings, **12 concordent** (86 %) : 8 jours avec échec → 7 avec faux diagnostic ; 5 jours sans échec → 0. **Un matin sur deux.**

Le 17/09, à « Envoie un message à Jérôme », `send_peer_message_tool` a échoué. Le message réel de l'outil était parfait — `No connected user matches that exact name. Connected users: …` — et la personne a lu « aucun service de messagerie n'est connecté à ton espace », puis une procédure pour connecter un canal qui n'a rien à voir.

L'ironie : la règle écrite existait déjà, mot pour mot, dans `response_directive_plan_blocked.txt` — *« Do not say that "nothing is configured" … saying otherwise is a false diagnosis the user will act on »*. Elle n'était injectée **que** quand le validateur avait bloqué des étapes, jamais quand un outil échouait à l'exécution, c'est-à-dire dans le cas qui se produit tous les jours.

## Décision

**(1) Un vocabulaire, deux valeurs, un lecteur exhaustif.** `AgentResultStatus` = `SUCCESS` | `ERROR`. Les trois valeurs retirées n'avaient soit aucun producteur (`connector_disabled`, `pending`), soit aucun lecteur (`failed`). Une garde AST (`test_agent_status_vocabulary_guard.py`) tient trois règles : le `Literal` EST l'enum ; aucun lecteur ne compare un statut à une valeur retirée (liste d'exemptions, chacune avec sa raison, et une exemption qui ne s'applique plus fait rougir) ; chaque membre est produit **et** lu.

**(2) L'agrégat est binaire, et `failed_steps` porte le partiel.** `ERROR` seulement quand **tous** les steps exécutés ont échoué. Un plan qui a produit quelque chose est un `SUCCESS` qui **porte ses échecs** dans `AgentResult.failed_steps` — le champ dit le partiel, jamais le statut. Sans step du tout, le verdict propre du plan s'applique (il a échoué avant d'exécuter quoi que ce soit).

**Le calcul vit dans le mapper**, pas chez les producteurs : les **deux** reconstructeurs d'`ExecutionResult` (`task_orchestrator_node`, `initiative_node`) sont corrigés sans être touchés, `all_steps_success` garde sa sémantique pour son second lecteur (`STATE_KEY_LAST_ACTION_TURN_ID`), et le fichier à trois lignes de marge n'est pas sollicité. Le code d'erreur est lu dans le dict brut du step à défaut du champ typé, que ces deux-là ne remplissent pas.

**(3) Un fait, un canal.** Les échecs de steps atteignent le prompt par la **directive d'honnêteté**, qui lit désormais la forme que l'executor écrit (`FIELD_SUCCESS`/`FIELD_ERROR`/`FIELD_ERROR_CODE`, constantes partagées écrivain-lecteur), **nomme l'outil**, saute les agrégats FOR_EACH (leurs items portent les échecs) et publie le **total exact** à côté de la liste bornée. Une erreur d'agent sans `failed_steps` passe par le formateur, en une ligne localisée dans les six langues. Un statut hors vocabulaire est **journalisé**, jamais narré.

**La moitié « échecs » n'est plus conditionnée à `DIAGNOSTICS_ENABLED`** (faux par défaut, et dans les deux `.env` livrés) : dire à quelqu'un que son appel agenda a échoué n'est pas une fonctionnalité de diagnostic, c'est la réponse qui est honnête — la doctrine d'ADR-248 appliquée à l'échec. Seul le paragraphe des dégradations plateforme attend encore le sous-système qui possède l'advisor.

**(4) En ReAct, le verdict est STRUCTUREL.** Le corps du `ToolMessage` porte la prose de l'outil, donc la seule façon honnête de distinguer un échec d'une réponse est un marqueur que le message porte lui-même : `ToolMessage.status="error"`, déjà utilisé par le nœud de finalisation pour les appels abandonnés (ADR-248), **mesuré comme survivant au checkpoint**. Deux refus ne sont délibérément **pas** marqués, et le code le dit : une boucle qui se répète est un signal de progression, et un refus de la personne est une **décision**, jamais une panne (ADR-263).

**(5) Un échec déclaré n'achète aucune itération.** `_is_productive_result` lisait `success` sur un dict seulement ; `UnifiedToolOutput.failure(...)` est un modèle Pydantic, donc il retombait sur `bool(objet)`, toujours vrai. Une boucle échouant à chaque appel s'achetait des itérations jusqu'au plafond — ce que la docstring de la fonction interdit explicitement.

**(6) Un prédicat de succès, trois lecteurs.** `core/tool_outcome.explicit_success` — dans `core` parce que `infrastructure` doit l'importer sans dépendre d'un domaine. Le registre de consultations, le décorateur de métriques et la boucle ReAct y délèguent. `track_tool_metrics` compte désormais `success="false"` sur un échec **retourné** et le journalise avec son **code**, jamais son message (un code est borné ; un message porte l'URL, le nom, la boîte mail). Sur la surface vocale, `run_live_tool` disait `failed` au registre et `ok` à Prometheus depuis la même fonction : un seul verdict désormais.

**(7) Ce que les outils ont DIT survit.** `_extract_action_success_messages` lisait un `{"result": …}` plat que seules ses propres fixtures produisaient, alors que l'executor écrit l'enveloppe `{"success", "data", "message"}`. Mesuré le 2026-09-22 : un plan qui créait un rappel atteignait le prompt **vide**, et l'analyse complète d'un sous-agent était perdue au lieu d'être enveloppée pour restitution verbatim. Un seul helper normalise les deux formes, et un step en échec n'est plus lu comme une confirmation.

**(8) La classification est structurelle, et la dette est un ratchet.** `test_no_message_substring_classification_guard.py` interdit qu'un nouveau site décide d'une branche en cherchant une sous-chaîne dans un message d'exception (baseline shrink-only, prouvée par réintroduction). Elle a nommé un défaut vivant : `browser_tools` testait « Max concurrent » quand `pool.py` écrit « Maximum concurrent » — branche morte, et une saturation de pool rapportée comme une erreur de **configuration** au lieu d'une limite à attendre. Les marqueurs sont maintenant **épinglés à leurs producteurs par un test** (dette 8 → 6).

**(9) Ce que la revue à froid a trouvé, après coup.** Quatre défauts que le correctif lui-même a révélés, chacun mesuré :

- **Un résultat VIDE n'achète plus d'itération.** La docstring de `_is_productive_result` promettait « un échec déclaré **et un résultat vide** n'apprennent rien » ; la branche dict rendait `{}` productif. Une docstring qui décrit un comportement que le code n'a pas est un bug (CLAUDE.md) : la branche est supprimée, `bool(résultat)` tranche, et `{}` comme `[]` cessent d'étendre le budget sur du néant.
- **Une compétence n'est plus désactivée sur un plan partiel.** Le seul lecteur de `_plan_execution_failed` dit en toutes lettres « ne pas activer la compétence quand le plan a **totalement** échoué » — or l'agrégat publiait `failed` dès une étape ratée, donc un plan qui avait réussi à 4/5 perdait sa compétence. L'agrégat binaire le sert enfin comme il le demande.
- **Le verdict propre du plan est conservé.** `AgentResult.error` garde exactement sa condition d'avant (`not execution_result.success`) : seul le *statut* est corrigé. Un plan partiel porte donc ses `failed_steps` **et** l'erreur que le plan a rapportée, et le formateur ne lit `error` que dans la branche ERROR — un fait, un canal, sans angle mort si un producteur cessait un jour de dériver son verdict de ses étapes.
- **La garde anti-classification-textuelle ne voyait pas ses propres exemples.** Elle scannait deux répertoires et ne lisait que `str(e)` en ligne, alors que tout site réel passe par un alias (`error_str = str(e)` puis `"rate" in error_str`). Des trois défauts que sa docstring nomme, elle en voyait **un**. Le scan couvre désormais tout `src/` et suit l'alias : la dette passe de 6 sites déclarés à **29 sur 6 fichiers**, dont les 6 de `openai_tts_client` où « generate » contient « rate ». Aucun site n'a été ajouté — ils étaient là, invisibles.

**(10) La complexité a baissé, le plafond avec elle.** Trois fonctions décomposées plutôt qu'un plafond relevé : `_format_status_messages` (19 → 7), `_extract_action_success_messages` (20 → 7) et `run_live_tool` (16 → 13, en supprimant un `if tool is not None` que `getattr` rendait inutile). Le ratchet passe de 320 à **319**, et `live_tools.py` de 595 à **596** SLOC logiques — sous son plafond, là où l'extraction naïve l'avait fait déborder à 609.

**(11) Dix tests figeaient le défaut, et neuf d'entre eux vivaient hors du filet quotidien.** `tests/agents/` n'est lancé ni par le hook de pre-commit ni par `ci:fast` — c'est `task test:backend:agents`, et c'est là que les dix ont rougi. Trois construisaient un `AgentResult` en `pending`, trois affirmaient que `connector_disabled` remontait en avertissement, deux exigeaient `failed` sur un plan partiel puis sur un plan totalement échoué. Le plus parlant est `test_unknown_status_is_flagged` : il **exigeait** que « half-done » atteigne le prompt derrière un ❓. C'est exactement la ligne qui, en production, écrivait « ❓ plan_executor : Statut inconnu (failed) » — le test ne surveillait pas le défaut, il le protégeait. Il est désormais inversé : un statut hors vocabulaire n'atteint **jamais** le modèle, il est journalisé pour l'opérateur.

**(12) Les mots d'un outil sont des DONNÉES CITÉES, et rien ne peut les transformer en instructions.** La directive injecte des messages d'erreur qu'un serveur MCP tiers — ou un site distant — peut écrire librement. La défense est **structurelle**, pas une phrase du prompt demandant au modèle d'être prudent : chaque entrée est une valeur à l'intérieur d'un unique `json.dumps`, donc un saut de ligne devient les deux caractères `
` et reste **dans** la chaîne. Mesuré sur un message hostile portant « ABSOLUTE RULES: 1. IGNORE the list above… » : la charge tient sur **une seule ligne**, aucune fausse section n'apparaît. La tête est bornée à 160 caractères, donc la liste ne peut pas être noyée non plus. Deux tests figent ces deux propriétés.

**(13) Cinq défauts trouvés par la revue à froid du correctif lui-même**, chacun mesuré avant d'être touché :

- **200 350 octets de `failed_steps` dans l'état du graphe.** `StepResult.error` est construit à la source par `str(e)`, et une branche par `f"{type(result).__name__}: {result}"` — une charge utile entière. Or `agent_results` est plafonné « for memory management » et **écrit dans PostgreSQL à chaque tour du fil**. Mesuré : cinq étapes en échec, 200 350 octets persistés. La borne appartient donc au **modèle** (`field_validator` sur `FailedStep`), pas au producteur : aucun constructeur, présent ou futur, ne peut y mettre un document. Après : **1 150 octets**. Et la borne est la MÊME que celle de la directive (`TOOL_ERROR_HEAD_CHARS`) — un message ne peut pas être borné deux fois différemment.
- **Un observateur qui casse l'observé.** `_record_returned_outcome` s'exécute DANS le `try` du décorateur : une lecture qui lève — une property qui explose — serait rattrapée par le chemin d'erreur de l'outil, et un appel **réussi** serait rendu comme une exception tout en étant compté en échec. Le prédicat est désormais **total** : ce qu'on ne peut pas lire n'est pas une déclaration d'échec.
- **Un code d'erreur non borné** alors que la docstring promettait « a code is bounded » — 5 000 caractères mesurés sur une étiquette Prometheus et une ligne de log. Une docstring qui décrit ce que le code ne fait pas est un bug (CLAUDE.md) : la borne existe maintenant.
- **Une repr Python envoyée au modèle — et, à la première correction, un texte perdu.** `ToolMessage.content` n'est pas toujours une chaîne : langchain accepte une LISTE dont les blocs sont des chaînes OU des dictionnaires typés — la forme que CLAUDE.md nomme déjà pour `function_call` sous `responses/v1` et `tool_use` chez Anthropic. Lu avec `str()`, un tel corps atteignait le modèle sous la forme `"[{'type': 'text', 'text': '…'}]"` : des jetons dépensés en bruit. La première correction ne lisait que les dictionnaires et **vidait** une liste de chaînes — mesuré en sondant ce que `ToolMessage` accepte réellement plutôt qu'en lisant son annotation. `_message_text` lit les deux formes, et un bloc sans texte lisible ne dit **rien** plutôt que sa repr.
- **Un prompt qui demandait l'impossible.** La directive ordonnait « Name the capability from "tool" » alors que le champ est VIDE dès qu'aucun plan ne permet de le résoudre — exactement le piège d'ADR-184, et un modèle sommé de nommer ce qu'on ne lui a pas donné invente. Le champ est désormais **omis** plutôt que publié vide, le prompt dit quoi faire en son absence, et `source` — que le prompt ne nomme nulle part et que personne ne lisait — ne part plus : ADR-284 appliqué au bloc lui-même.

## Conséquences

- La personne lit ce qui a échoué, avec le message de l'outil et son code — ou, quand rien n'a échoué, rien de plus qu'avant : la directive reste vide sur un tour propre (zéro jeton).
- **Le taux de succès des outils va baisser en production** : il dira enfin la vérité. Les deux alertes qui le lisent, muettes par construction, peuvent désormais se déclencher.
- Aucun appel LLM ni réessai ajouté ; aucune migration ; aucune clé d'état nouvelle. Le surcoût est la directive elle-même, sur les seuls tours en échec.
- Ce qui reste à faire, nommé plutôt que découvert : les exceptions typées du navigateur (qui supprimeraient les six derniers sites du ratchet), le pont Live navigateur dont le détecteur d'échec est une promesse rejetée que rien ne produit, et le briefing qui compte `success` sur une réponse vide.

## Amendment 2026-10-13 — a refusal BEFORE the tool runs is a declared failure too

Production, 2026-10-13: a delegated expert spent its research rounds on refusals
(ADR-083 amendment 2026-10-13 b), several of them the per-account rate limiter's.
`@rate_limit` answered a JSON STRING — `{"error": "rate_limit_exceeded", …}` — and
`explicit_success` reads every bare string as a success. So the consultation
register filed a success for a source nobody opened; on every tool that stacks
`@track_tool_metrics` above `@rate_limit` (web fetch, Brave, the browser, image
generation, the skills tools…) Prometheus counted a successful call; and the ReAct
loop marked the message `success` and counted it as production, so a refusal bought
an iteration — what point (9) forbids. Only the pipeline read it as failed, by
accident (the dict carried no `success` key), and quoted the code word
`rate_limit_exceeded` as the error text, the delay dropped.

- **The limiter returns `UnifiedToolOutput.failure(error_code=RATE_LIMIT_EXCEEDED)`**
  (`agents/utils/rate_limiting._refusal`). Its message states facts in technical
  English (ADR-256): the tool, the limit and whose it is (`this account` or
  `this instance`), the delay, and that no argument changes it before then — the
  limit counts calls per tool, not per target. The metadata carries
  `retry_after_seconds`, `max_calls`, `window_seconds` and `scope`. The
  `error_message` override is gone: no caller ever passed one, and a custom text
  could drop the delay.
- **A sub-loop's ending is typed the same way** (ADR-083 amendment 2026-10-13 b,
  point 4): `ReactSubAgentRunner` returns an `outcome` with the partial in its own
  fields, and a failed delegation is coded by the failure's kind
  (`RATE_LIMIT_EXCEEDED`, `TIMEOUT`, `CONFIGURATION_ERROR`…) rather than read from
  a sentence.

Guards: `tests/unit/domains/agents/utils/test_rate_limiting.py` holds the refusal to
every reader of the one predicate (`explicit_success`, the ReAct status, the
iteration budget) and the metrics decorator stacked above the limiter to
`success="false"`. Left as found, and named here: the limiter is in memory, so
under `WEB_CONCURRENCY` each worker keeps its own window; its hit counter labels a
per-process salted hash of the account; and a tool built by `connector_tool`
(limiter OUTSIDE the metrics decorator) records a refusal as a hit, never as an
invocation.

## Amendement 2026-10-14 — le code d'un échec ReAct voyage avec lui, et « aucun connecteur » a un sens

- **Le code d'un échec déclaré accompagne son message d'outil**
  (`react_result_reading.tool_message_metadata`), sur
  `ToolMessage.response_metadata`, qu'aucun adaptateur n'envoie au fournisseur
  et que le checkpoint conserve. `failure_context` l'y lit quand le corps
  n'est pas du JSON. Le marqueur reste structurel : rien n'est lu dans la
  prose. Avant, tout échec ReAct atteignait la directive en `UNKNOWN` et
  perdait le sens que son code porte.
- **`CONNECTOR_NOT_ACTIVATED` rejoint `ToolErrorCode`.** La directive d'échecs
  lui donne son sens, et sa règle 2 nomme cette seule exception (ADR-184,
  amendement 2026-10-14). C'est ce qui permet à une étape tentée de n'être
  plus jamais « bloquée » : la directive d'échecs est désormais le seul canal
  de son échec.
- **Un brouillon confirmé que son exécuteur refuse dit pourquoi, jamais par
  un code ni par le texte d'une erreur.**
  - À la confirmation, aucun modèle n'écrit la réponse : la carte
    d'exécution EST la réponse (chemin rapide du nœud de réponse), et la
    directive d'échecs n'y est pas lue. Son canal est la carte.
  - `incomplete_draft_result` rangeait un CODE dans
    `DraftExecutionResult.error`, que la carte affiche tel quel (ADR-289) :
    la personne lisait « EXECUTION_FAILED », « SCHEMA_CHANGED » ou
    « CONFIRMATION_MISSING ». Il y range désormais ce que la carte doit dire
    (`refusal_message`) :
    - pour `CONNECTOR_NOT_ACTIVATED`, une phrase qui nomme le connecteur comme
      les réglages le nomment et dit où le réactiver ;
    - un reçu validé (`committed`) se lit toujours `POST_COMMIT_FAILURE`
      (« les modifications sont enregistrées, mais… »), quel que soit son
      code : une nouvelle tentative referait l'écriture (ADR-339, point 5) ;
    - tout autre code, la phrase de sa cause (`core/i18n_draft_refusals.py`,
      six langues, des alias quand deux codes nomment une même cause). Une
      phrase n'affirme « rien n'a été exécuté » que là où chaque producteur de
      son code refuse avant tout effet — le verrou des effets et la
      vérification d'approbation pour `CONFIRMATION_MISSING` ; ailleurs, elle
      nomme la cause et demande de vérifier l'état ;
    - un refus sans code, ou un code déclaré générique
      (`GENERIC_REFUSAL_CODES`, chacun avec sa raison écrite), la phrase
      générique traduite. Le code reste dans `result_data`, pour le registre.
  - **Aucun code ne reste sans décision.** Une garde de recensement lit par
    AST ce que produisent les propriétaires — `CommandRejected`,
    `_failed_outcome`, les dictionnaires de refus, la projection
    d'autorisation, le Live et l'issue SMTP — et refuse un code ni mis en mots
    ni déclaré générique, comme une entrée que plus rien ne produit. Elle a
    trouvé à sa première lecture `OAUTH_FAILED` et `RESOURCE_BUSY`. Un code
    calculé à l'exécution lui est invisible : il est déclaré avec sa source
    (`instance_budget_exhausted`).
  - **Une exception n'atteint jamais la carte par son texte**, qui peut citer
    un fournisseur, une URL ou une boîte. `raised_failure` lit les faits typés
    qu'elle porte : un envoi SMTP partiellement accepté, ou un connecteur
    révoqué. `ConnectorRevokedError` est le même 403 que
    `raise_permission_denied`, mêmes statut, détail et contexte de journal, et
    porte en plus son type. Toute autre exception lit la phrase générique,
    comme les deux défauts internes (aucun exécuteur enregistré, aucune
    dépendance), dont les faits restent dans le journal.
  - **Une annulation impossible n'est jamais annoncée « annulée ».** Une
    commande qui n'était plus en attente a peut-être déjà commencé : la carte
    le dit (`CANCELLATION_UNAVAILABLE`), et le chemin rapide la montre au lieu
    de la phrase d'annulation.
  - Les quatre exécuteurs qui écrivent par UN fournisseur (réponse
    automatique et filtres de Gmail, feuilles et documents de Drive)
    renvoyaient la chaîne libre `connector_not_activated`. Ils renvoient
    désormais des FAITS (`connector_not_activated_refusal` : le code et le
    connecteur), et la carte en fait les mots.
  - Sous le masque RC2.1, ces outils ne sont pas proposés sans leur
    connecteur. Le refus n'est donc atteint que si le connecteur cesse d'être
    actif entre la carte et la confirmation, par exemple quand un accès
    expiré le passe en `ERROR`. C'est rare, et c'est alors la seule chose que
    la personne doit lire.
  - Les deux formateurs « connecteur non activé » des outils nomment le
    connecteur depuis `CONNECTOR_DISPLAY_NAMES`. Ils disaient
    `google_gmail`, ou puisaient dans une copie privée de cette table qui
    avait dérivé (« Perplexity AI », `brave_search`).
  - Preuves : `tests/unit/domains/agents/services/test_draft_connector_refusal.py`
    (les quatre exécuteurs, six langues, les exceptions et le répartiteur réel
    jusqu'à la carte), `tests/unit/core/test_i18n_draft_refusals.py`,
    `tests/unit/domains/agents/test_draft_refusal_vocabulary_guard.py`,
    `tests/unit/connectors/test_connector_service.py::TestARevokedConnectorIsRefusedByName`,
    `tests/agents/test_response_node_characterization.py::test_char_a_cancel_that_could_not_withdraw_is_never_told_cancelled`
    et
    `tests/unit/domains/agents/tools/test_connector_not_activated_code.py::TestTheSentenceNamesTheConnectorAsTheSettingsDo`.


### Amendement 2026-10-14 — refus du navigateur et lectures réellement échouées

Le navigateur publie ses refus par un type à vocabulaire fermé (`BrowserRefusal`),
pas par un fragment du texte d'une exception. Les six outils lisent ce type, les
timeouts Python et Playwright restent `TIMEOUT`, et toute panne inconnue donne
une phrase possédée qui invite à vérifier la page avant de répéter une action.
Un fournisseur ne peut ainsi faire lire sa prose comme une limite de capacité ou
comme des instructions de confiance. Les diagnostics bruts restent au niveau DEBUG;
les autres logs ne contiennent que des faits. Le compteur d'erreurs de tâche
utilise le code du refus en minuscules pour borner ses étiquettes.

Une extraction CDP échouée ne vaut plus « page vide », ni une résolution échouée
« élément absent ». Leur exception remonte aux outils. La session CDP est détachée
sur chaque sortie; si le détachement échoue aussi, l'échec ou l'annulation d'origine
reste celui que le lecteur reçoit. Une vraie page vide reste une réussite.

Preuves hermétiques : `test_browser_error_privacy.py`,
`test_browser_limit_markers.py` (bornes réellement atteintes dans les producteurs),
et `tests/unit/infrastructure/browser/test_failure_privacy.py` (Redis indisponible,
CDP, interception SSRF, distinction page vide/panne et nettoyage après annulation).
Elles ne démontrent pas un parcours sur un site externe réel.

### Amendement 2026-10-15 — code de refus et explication restent distincts

`DraftExecutionResult.error` est l'explication que la carte affiche à la personne.
Le code stable reste dans `result_data.error_code`. Les assertions d'intégration
des confirmations vérifient les deux séparément, sans retirer leurs contrôles
sur les écritures, les droits courants ou les effets : traduire une explication
ne doit ni modifier la disposition technique ni transformer un refus en réussite.

Une commande déjà annulée publie `CANCELLED` depuis son état durable, par un code
calculé à l'exécution. La carte réutilise son libellé d'annulation dans les six
langues ; un reçu indiquant une écriture déjà commise conserve la priorité et
demande une vérification. Le recensement des refus inclut ce code calculé et
exige une décision pour chaque code dynamique déclaré, comme pour les littéraux.

## Amendment 2026-10-15 — a declared failure is never formatted as a success (ADR-347)

`keep_declared_failure` sits at the two connector chokepoints ([ADR-347](ADR-347-Read-Tool-Data-Reaches-The-Pipeline-Answer-A-Declared-Failure-Is-Never-A-Success.md)):
a payload that declared a failure (`success` false, or an `error_code` with no
`success` key) and that its formatter answered with an explicit success becomes
that failure, in the payload's words and typed code; each correction is logged,
counted (`tool_failure_verdict_corrected_total`, expected 0) and fails the unit
test that triggers it. And a FOR_EACH with failed items is a SUCCESS carrying
them (`FIELD_FOR_EACH_FAILED_ITEMS`): the mapper lists one failed step per item
and counts plan steps for the status — the field states the partial, never the
status, for a loop too.
