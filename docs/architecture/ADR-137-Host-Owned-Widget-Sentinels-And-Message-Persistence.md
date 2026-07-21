# ADR-137 : Les sentinelles de widget appartiennent à l'hôte, et voyagent avec leur message

**Statut** : Accepté — implémenté (backend + frontend), défauts prouvés sur la base de production.
**Date** : 2026-07-21
**Contexte** : quatre défauts du chemin widget mis au jour par l'investigation qui a produit [ADR-136](ADR-136-COEP-Posture-And-Widget-Failure-States.md). Complète [ADR-075](ADR-075-Rich-Skill-Outputs.md) (sorties riches de skills) et [ADR-098](ADR-098-CSP-Widget-Airlock.md) (sas CSP).

## Contexte

Quatre défauts distincts, tous prouvés par la mesure sur la production du 2026-07-21.

### 1. Sentinelles dupliquées

Le message assistant `28eaa427` (run `9fe3d6ba`) portait **deux fois** le même
`data-registry-id="skill_app_545e26"`, et le frontend montait réellement deux
iframes. L'arithmétique le confirme au octet près : `response_node_completed`
1195 + `"\n\n"` + `interactive_widgets_injected_post_llm` 400 = 1597 =
`final_content_length` = longueur en base.

Les deux copies n'ont ni la même icône ni le même texte de chargement : elles
n'ont pas le même auteur. Chaîne de contamination :

1. `_render_response_html` ajoute le sentinelle à la réponse ;
2. le contenu enrichi retourne dans `state["messages"]` et est checkpointé ;
3. `_window_messages_for_react` sert cet historique **brut** à la boucle ReAct —
   le chemin réponse neutralise le HTML, celui-là ne l'a jamais fait ;
4. le modèle imite le motif, et l'injection déterministe en ajoute une seconde.

### 2. Sentinelles fantômes

Deux réponses ultérieures (`e8f42f65`, `c633273b`) portaient un sentinelle que
le backend n'a **jamais** injecté, pointant vers un identifiant du tour de 09:13.
Rendu par accident tant que le registre client détenait encore l'identifiant,
mort au rechargement. L'une d'elles disait « je n'ai pas accès à ta position »
tout en affichant une carte.

### 3. Registre jamais persisté

Le payload d'un widget vivait **uniquement** dans l'état React du navigateur,
alimenté exclusivement par le SSE. Vérifié en base : les clés de
`message_metadata` des messages assistant sont exactement `run_id`,
`intention`, `psyche_state`. Rendu du contenu de production réel avec un
registre vide : **2 encadrés d'erreur, 0 iframe**.

### 4. Deux défauts de contrat

- `react_result` portait **deux formes incompatibles** sous un nom typé `Any` :
  le `dict` du contrat d'état et la dataclass `ReactSubAgentResult` du runner.
  Le run `117ce96f` est mort sur `AttributeError: 'ReactSubAgentResult' object
  has no attribute 'get'`, tour entier réduit à un repli de 98 caractères.
- `_plan_already_produced_skill_app` balayait **tout** `agent_results` (l'état
  de production portait des clés des tours 41 à 48) alors que sa docstring
  annonçait « earlier in the same turn ». Un widget produit au tour 47
  neutralisait le runner à tous les tours suivants : run `d0fad28b`, la garde
  se déclenche, le registre du tour ne contient que `weather`/`location`, la
  carte n'est jamais rendue.

## Décision

### 1. Invariant : le LLM n'écrit jamais de markup de widget

`display/sentinel_filter.py` retire tout bloc sentinelle, avec `html.parser` et
**non une regex** : le sentinelle imbrique des `<div>`, une regex non gloutonne
s'arrête au premier `</div>` et laisse des orphelins. Les positions sont
résolues sur la chaîne d'origine et seules les plages identifiées sont excisées
— le reste survit octet pour octet.

Trois points d'étranglement :

| point | rôle |
| --- | --- |
| `_render_response_html` | supprime les copies du LLM **avant** l'injection canonique — supprime le doublon ET les fantômes |
| `_window_messages_for_react` | remplace les sentinelles de l'historique par `CONTEXT_WIDGET_DISPLAYED_PLACEHOLDER` — supprime l'incitation, et récupère les tokens |
| `_apply_react_passthrough` | nettoie la réponse ReAct au moment où elle devient AUTORITAIRE pour le LLM de réponse |

Métrique `widget_sentinels_stripped_total{source}` : un taux non nul dit que le
modèle imite encore, au lieu de le supposer.

**Verrou** : pour un registre de N widgets interactifs, le contenu final porte
exactement N sentinelles, une par identifiant. Sa non-vacuité est prouvée — avec
le strip neutralisé, le duplicata de production se reproduit (2 sentinelles, 2
fois le même identifiant).

### 2. Le widget voyage avec son message

`data_registry/message_widgets.py` extrait les widgets à l'archivage et les
réhydrate à la lecture de l'historique.

Réhydrater depuis le checkpoint LangGraph a été **évalué puis rejeté par la
mesure** : le canal `registry` est plafonné en LRU à `REGISTRY_MAX_ITEMS` (75 en
production, ~70 déjà utilisés), donc les widgets anciens sont évincés
silencieusement. Le payload voyage donc avec le message qui l'affiche : une
seule écriture, atomique, un seul cycle de vie (supprimer le message supprime le
widget, `CASCADE` compris).

Deux restrictions délibérées :

- **Types** : `SKILL_APP` et `MCP_APP` seulement. `DRAFT` est exclu — c'est un
  état HITL avec son propre cycle de vie, et un brouillon persisté périmé
  inviterait à confirmer une action que le graphe ne connaît plus.
- **Taille** : au-delà de `widget_persist_max_bytes` le widget est **abandonné,
  jamais tronqué** — un `html_content` coupé en deux rend plus mal qu'un état
  d'échec honnête. Le budget est **calibré sur la mesure, pas sur une
  estimation** : la première valeur livrée (64 ko) venait d'un raisonnement sur
  les seuls skills et s'est révélée 7× trop petite. La production a journalisé
  `widget_persist_skipped_too_large size_bytes=473503` pour une MCP App
  Excalidraw, qui affichait alors « erreur de chargement de l'application » à
  chaque rechargement — exactement le défaut que la persistance existe pour
  fermer. Plage observée : ~1 ko pour une carte (une URL), ~6 ko pour un
  plateau de jeu, ~473 ko pour un widget de diagramme qui inline sa scène.
  Défaut porté à 1 Mo (~2× la pire mesure), soit ~60 ko sur le fil une fois
  compressé au bord.

**Sécurité** : `is_system_skill` n'est **pas cru** à la lecture. Il gouverne
l'attribut `credentialless` et le drapeau `allow-same-origin` du bac à sable ;
un skill rétrogradé de *system* à *user* garderait sinon ses privilèges de frame
dans tous les anciens messages. Le drapeau est recalculé contre l'ensemble des
skills système courants.

Côté client, `mergeRegistryWithHistory` fusionne les widgets de l'historique
**sous** le registre live — le tour courant est la vérité — et retourne le
registre live par identité quand l'historique n'apporte rien, pour ne pas
provoquer de rendu inutile.

### 3. Une seule forme pour `react_result`

La branche skill-runner normalise le résultat du runner sur le contrat d'état
`react_agent_result` (`final_message` / `iteration_count` / `mode`) et garde la
dataclass dans son propre nom. Les trois annotations passent de `Any` à
`dict[str, Any] | None` : le typage est le correctif, pas un accesseur
défensif.

### 4. La garde de skip est scopée au tour courant

Deux axes désormais : le nom du skill **et** le préfixe `{turn_id}:` de la clé
composite. La docstring décrit ce que le code fait.

## Conséquences

- Un widget ne peut plus apparaître en double, ni apparaître sans que le backend
  l'ait produit.
- Une conversation rouverte affiche ses widgets ; c'est ce qui rend l'ordre
  d'application obligatoire — persister avant de corriger le doublon aurait fait
  rendre **pour de vrai** les sentinelles fantômes.
- Un tour ne meurt plus sur un `AttributeError` de contrat.
- La carte ne disparaît plus silencieusement au tour suivant.
- Coût : jusqu'à 1 Mo par widget dans `message_metadata` (JSONB, TOASTé au-delà
  de 2 ko, donc la ligne reste légère ; ~60 ko sur le fil après compression au
  bord pour le pire cas mesuré) et une requête cache-mémoire par
  page d'historique pour l'ensemble des skills système.

## Alternatives écartées

| Alternative | Raison |
| --- | --- |
| Injection idempotente (ne pas ré-ajouter si l'identifiant est déjà présent) | Corrige le doublon visible mais **laisse les fantômes** : un sentinelle inventé avec un identifiant périmé passerait tel quel. |
| Regex pour retirer les sentinelles | Le sentinelle imbrique des `<div>` ; une regex non gloutonne laisse des balises orphelines. Rejeté par construction. |
| Réhydrater depuis le checkpoint LangGraph | Plafonné en LRU à 75 items, ~70 déjà utilisés : perte de données silencieuse. |
| Table dédiée `message_widgets` + endpoint paresseux | Historique plus léger, mais migration, endpoint, contrôle de propriété, N+1 au scroll et état de chargement. À reconsidérer si la taille des payloads devient un problème mesuré. |
| Accesseur tolérant sur `react_result` | Déplace la complexité au lieu de la supprimer, et laisse `Any` autoriser une troisième forme demain. |

## Vérification

- `tests/unit/domains/agents/display/test_sentinel_filter.py` — 14 cas dont les `<div>` imbriqués, les classes enfants homonymes, le sentinelle tronqué, la balise fermante espacée.
- `tests/unit/domains/agents/nodes/test_widget_sentinel_invariant.py` — l'invariant N widgets = N sentinelles, sur le contenu de production réel.
- `tests/unit/domains/agents/nodes/test_react_history_sentinels.py` — la neutralisation de l'historique, et surtout la **préservation de `tool_calls` / `additional_kwargs`** : reconstruire le message au lieu de le copier orphelinerait ses `ToolMessage` et ferait rejeter la requête entière par le fournisseur.
- `tests/unit/domains/agents/services/streaming/test_persistable_widgets_scope.py` — exerce la vraie méthode d'émission : le SSE émet bien le registre transverse pendant que la persistance reste vide.
- `tests/unit/domains/agents/data_registry/test_message_widgets.py` — types persistés, budget, recalcul de `is_system_skill`, absence de mutation en place, attachement sans branche.
- `tests/unit/domains/agents/nodes/test_skill_runner_skip_scope.py` — la régression du tour précédent, le cas légitime du même tour, le préfixe non confondu avec un numéro plus long.
- `tests/unit/domains/agents/nodes/test_react_result_shape.py` — le contrat de mapping, et l'interdiction du `Any` nu.
- `apps/web/src/lib/__tests__/message-widgets.test.ts` — le cas rechargement, la précédence du live, l'identité préservée.

### Défauts trouvés par auto-revue, après la première implémentation

Consignés parce qu'ils sont représentatifs de ce que ce chemin de code fait rater :

1. **Reconstruction de message** au lieu d'une copie dans la neutralisation de
   l'historique → perte silencieuse de `tool_calls`. Aurait produit un rejet
   fournisseur, ou pire une suppression muette par `enforce_tool_message_pairing`.
2. **Capture depuis `serialized_items`** alors que l'émission retombe sur le
   registre transverse (70 items observés en production) → on aurait attaché à
   chaque message des widgets d'anciens tours.
3. **Sonde d'embarquement testant la capacité du moteur** sans vérifier que
   l'attribut serait posé → iframe condamné rendu sur Chromium, où le refus est
   invisible (`load` se déclenche sur la page d'erreur).
4. **Ratchet de complexité franchi** par deux conditions ajoutées dans des
   fonctions déjà lourdes → corrigé par extraction (`_current_turn_widgets`,
   `with_persisted_widgets`), jamais en relevant la baseline.
5. **Une extraction faite pour ce ratchet avait fait perdre `run_id`** au log
   `message_widgets_persisted` — or c'est le seul témoin que la capture atteint
   le message archivé, et un log incorrélable ne prouve rien. `run_id` est
   redevenu un paramètre obligatoire.
6. **Budget de persistance sous-évalué d'un facteur 7** (voir ci-dessus) : une
   estimation là où une mesure était possible.

### Défaut post-livraison (prouvé en production le 2026-07-21, même jour)

7. **Le filtre de réhydratation lisait `entry.get("is_system")` sur les entrées
   du SkillsCache** — une clé qui n'existe que sur la table SQL `skills`,
   jamais sur les entrées du cache (le loader disque estampille `scope:
   "admin" | "user"`). L'ensemble des skills système était donc **toujours
   vide** : chaque widget réhydraté revenait rétrogradé, et la sonde ADR-136
   refusait l'iframe sur tout desktop isolé (« Ouvrir dans un navigateur »).
   Le chemin d'écriture portait la même confusion **avec un défaut permissif
   `True`** : il fonctionnait par accident, et aurait accordé à un skill
   utilisateur les privilèges de frame système (escalade latente).
   Correctif : prédicat canonique unique `SkillsCache.entry_is_system`
   (`scope == "admin"` — l'expression que la sync DB utilisait déjà) +
   `get_system_skill_names(user_id)`, consommés par les trois sites. Le set
   est **scopé utilisateur** (mêmes sémantiques d'override que le chemin
   d'écriture) : un skill utilisateur qui masque un nom système ferait sinon
   re-promouvoir à la lecture un widget produit par du code utilisateur —
   trou trouvé en contre-revue, fermé et épinglé par test avant livraison.
   **Leçon** : les tests unitaires des fonctions pures passaient avec un
   frozenset synthétique — la glu cache→filtre n'était couverte par rien. Le
   test de non-régression (`test_system_skill_predicate.py`) passe désormais
   par le **vrai loader** sur un arbre temporaire et épingle la forme réelle
   des entrées (`scope` présent, `is_system` absent).
