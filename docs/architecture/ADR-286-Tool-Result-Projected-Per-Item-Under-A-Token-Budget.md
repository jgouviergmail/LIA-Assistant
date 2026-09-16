# ADR-286 — Un résultat d'outil est projeté item par item sous un budget de tokens, et la coupe est annoncée

- **Statut** : Accepté
- **Date** : 2026-09-15
- **Amende** : ADR-070 (le mode ReAct — son wrapper d'outils coupait le résultat
  au caractère), ADR-248 (« un tour se termine quand sa réponse est envoyée » —
  ici le tour tournait en rond parce qu'il ne voyait rien), ADR-256 (les budgets
  de la boucle — celui-ci est le troisième : ce qu'un résultat peut occuper),
  ADR-184 (une borne imposée est une borne publiée — 8 000 caractères imposés,
  jamais annoncés), ADR-249 (un mode ne voit jamais un outil qu'il ne peut pas
  exécuter — `local_query_engine_tool` était offert au ReAct sans son registre)
- **Périmètre** : `domains/agents/tools/react_tool_wrapper.py`
  (`render_data_block`, `extract_data_block`, `compose_tool_message`),
  `domains/agents/utils/react_budget.py` (`tool_result_token_budget`,
  `tool_result_budget_note`), `domains/agents/nodes/react_nodes.py`
  (`_tool_result_budget`), `domains/agents/tools/mcp_react_tools.py`,
  `domains/agents/tools/mixins.py` (`build_emails_output` retire `payload`),
  `domains/agents/tools/emails_tools.py`, `domains/agents/emails/catalogue_manifests.py`,
  `domains/agents/query/catalogue_manifests.py`, `domains/agents/tools/context_tools.py`,
  `core/constants.py`, `core/config/agents.py`, `observability/metrics_react.py`,
  dashboard Grafana 20, les trois `.env`

## Contexte

Le 2026-09-15, sur Docker dev, un tour ReAct « recherche mes 5 derniers
emails » a été relu depuis le checkpoint LangGraph (les logs ne portent pas le
contenu des `ToolMessage`). Chaque réponse de `get_emails_tool` faisait 8 200 à
8 380 caractères : la ligne JSON, exactement 8 015 (8 000 + `... (truncated)`),
s'arrêtait dans le corps base64 du **premier** e-mail. Comptage dans ce que le
modèle lisait : `subject` = 0, `message_id` = 0, `date_formatted` = 0, `from` = 0.
Même une recherche rendant un seul e-mail (8 223 caractères) était coupée.

La chaîne : `build_emails_output` place dans `structured_data["emails"]` les
dicts Gmail `format=full` complets — `payload` (en-têtes SMTP `Received`,
`ARC-Seal`, `DKIM`, parties MIME, corps `body.data` en base64) pèse 10 450 à
127 922 caractères par e-mail, 85 à 98 % de l'item, en cinquième position des
clés, **avant** `from`, `subject`, `date`, `body`, `date_formatted`. Puis
`extract_data_for_llm` sérialisait le tout en JSON et coupait la **chaîne** à
8 000 caractères — un littéral posé à la naissance du mode ReAct (v1.16.0),
sans réglage, sans annonce au modèle, sans test. Mesuré aussi : le base64 se
tokenise à **1,45 caractère par token** (10 656 caractères → 7 327 tokens),
2,75 fois plus cher que de la prose.

Effet : le modèle ne disposait que de la ligne de résumé (trois sujets et
« +2 more ») ; sa propre pensée disait « Payloads systématiquement tronqués
après le 1er item ». Onze itérations au lieu d'une, ~74 000 tokens de contexte
à la dernière, 43 puis 67 secondes de calcul, une réponse fausse sur deux
entrées sur cinq. Ses trois replis étaient morts : `get_context_list` (même
coupe, 8 053 caractères), `local_query_engine_tool` (son registre n'est
injecté que par `parallel_executor` — « No registry data available » à chaque
appel en ReAct, sur un outil que rien ne lui interdisait), `resolve_reference`
(`UnifiedToolOutput.action_success(data=…)`, un mot-clé que le constructeur n'a
jamais eu — `TypeError` à chaque résolution réussie depuis la v1.0.0, invisible
au test de fumée qui n'atteint que la branche « pas de contexte »).

Le pipeline n'était pas touché : le nœud de réponse projette chaque item en
une ligne (`payload_to_text`) et ignore `payload`. Le ReAct, lui, faisait un
« dump puis coupe ».

## Décision

1. **Un résultat d'outil est projeté item par item.** `render_data_block`
   prend la liste de dicts la plus lourde de `structured_data` (ou des
   payloads du registre groupés par type) et admet ses items un par un tant que
   le budget tient ; les scalaires et les autres clés voyagent entiers, dans
   leur ordre, si bien qu'un `count` exact reste à côté d'une liste raccourcie
   et `<clé>_shown` dit combien sont passés. Un item admis est **complet** ; le
   bloc reste du JSON valide. Au moins un item passe toujours ; un premier item
   qui excède seul le budget, ou une forme sans liste, est coupé **en le
   disant** (`[cut: N of M tokens]`).
2. **Le budget est en tokens, dérivé de la fenêtre du slot.**
   `tool_result_token_budget` = `min(react_tool_result_max_tokens, fenêtre ×
   react_tool_result_window_fraction)`, la fenêtre étant celle du slot
   `react_agent` (ADR-278). Défauts : 25 000 tokens — la référence documentée
   pour les résultats d'outils d'agents — et 0,25, pour qu'un petit modèle
   local ne soit pas avalé par un seul résultat. Les deux sont des réglages ;
   le nœud calcule le budget une fois par passage.
3. **La coupe est annoncée et comptée.** `compose_tool_message` ajoute, **après**
   la balise `</external_content>` (la note est nôtre, jamais du contenu tiers),
   `tool_result_budget_note` : combien d'items sur combien, le budget, et la
   voie vers le reste — affiner la requête, baisser `max_results`, demander des
   ids — avec la consigne de ne jamais rapporter les items omis comme absents.
   `react_tool_result_truncated_total{tool_name}` compte chaque coupe (panneau
   « Tool Result Budget Cuts » du dashboard 20) ; le journal ne porte que des
   nombres.
4. **L'arbre natif ne quitte pas le builder.** `build_emails_output` retire
   `payload` une fois ses deux lecteurs passés (promotion des en-têtes,
   conversion des dates) : le registre, le checkpoint, le flux SSE, l'entrée
   du sandbox Python et le bloc ReAct perdent 85 à 98 % du poids d'un e-mail.
   Le manifeste cesse de publier `emails[].headers`, un chemin qu'aucun item
   construit n'a jamais porté (ADR-184 appliqué aux sorties).
5. **`local_query_engine_tool` est réservé au pipeline**
   (`execution_modes={pipeline}`), le miroir de la règle ADR-249 de
   `run_python_tool` : `manifests_for_mode`, que le sélecteur ReAct applique
   déjà, cesse de l'offrir.
6. **`resolve_reference` répond** (`structured_data=`), et son chemin de
   succès a un test.

7. **Le bloc est enveloppé sauf provenance INTERNE établie** (revue à froid du
   2026-09-15). `mark_untrusted_data` ne lisait que `registry_updates` et
   rendait nu tout bloc qui n'en portait pas, au motif qu'un `structured_data`
   seul « est écrit par l'outil » — faux : `get_context_list` et
   `resolve_reference` resservent des items du registre (corps d'e-mails)
   par `structured_data` seul, et la réparation de `resolve_reference`
   (décision 6) en avait fait une porte vivante et non marquée. Désormais un
   bloc sans registre est enveloppé comme un bloc externe
   (`type="structured_data"`), la règle « fail closed » du module de
   confiance ; un bloc dont tous les items sont INTERNES reste nu.

Le wrapper MCP (`_MCPReActWrapper`) passe par la même porte, `compose_tool_message`.

## Conséquences

- Un `ToolMessage` ne contient plus jamais un item coupé : le modèle lit des
  valeurs exactes (identifiants, ISO, sujets) ou lit qu'il lui en manque.
- Le budget est la seule borne : `EMAILS_BODY_MAX_LENGTH` continue de borner le
  corps d'un e-mail à la construction (ADR-287 le rendra propre à l'affichage).
- Deux réglages nouveaux, un compteur nouveau, un panneau nouveau ; aucune
  entrée dans les `.env` du démonstrateur, qui ne portent pas le bloc ReAct.
- Ce que cette décision **n'est pas** : une compaction.
  `window_messages_for_react` exclut déjà les `ToolMessage` des tours
  précédents ; dans le tour, la projection borne chaque résultat.

## Preuves

- Tests : `tests/unit/domains/agents/tools/test_react_tool_result_projection.py`
  (le cas mesuré — cinq messages au format Gmail `full`, cinq sujets lisibles —
  et le contrat : frontière d'item, JSON valide, un item minimum, note, compteur,
  budget), `test_mixins_structured_data.py::TestBuildEmailsOutputDropsTheProviderTree`
  (arbre retiré, chemins publiés vérifiés sur un item construit),
  `test_execution_mode_restriction.py::TestLocalQueryEngineIsPipelineOnly`,
  `test_resolve_reference_success.py`.
- Mesure Docker dev avant : 11 itérations, 73 728 tokens en cache à l'appel
  final, 2 entrées fausses sur 5 ; un `ToolMessage` de 8 328 caractères pour
  zéro champ lisible.
- Mesure Docker dev après, sur la vraie boîte du compte, par le chemin exact
  du nœud (`tool.coroutine` → `ReactToolWrapper._process_result`), sans appel
  de modèle : au budget par défaut, **5 e-mails sur 5 lisibles** (sujet, date
  formatée, `message_id`), 9 958 caractères et 3 686 tokens pour tout le
  message, aucune clé `payload`, aucune note ; un item réel pèse 688 tokens
  (corps de 1 500 caractères inclus). À un budget de 600 tokens : un item
  **entier**, `emails_shown: 1`, la note « 1 of 5 'emails' items shown » après
  la balise fermante, bloc JSON valide.
- Rejeu du tour complet par le propriétaire, dans l'interface, le 2026-09-15
  (après ADR-287, qui ajoute les niveaux de détail) : « recherche mes 5
  derniers emails recus » se termine en **2 itérations** (11 avant), un seul
  appel d'outil (`detail="metadata"`, 219 ms), second appel du modèle à
  2 216 tokens neufs + 29 568 en cache (73 728 avant), réponse listant les
  cinq messages, 15,5 s en tout ; `react_tool_result_truncated_total` n'a
  compté aucune coupe.
- Un premier item qui excède seul le budget passe **entier** : la première
  version le coupait explicitement, et le probe sur la vraie boîte a rendu un
  JSON inutilisable (`Expecting property name … char 1577`). Un item coupé
  est perdu, un item trop lourd coûte : le budget est dépassé d'au plus un
  item, et `used_tokens` dit de combien.

## Non traité

- Le contenu lui-même (HTML, citations, signatures), les niveaux de détail et
  le condensé par message : ADR-287.
- La rétention des checkpoints (ADR-283, laissée ouverte) : allégée ici, non
  résolue.
