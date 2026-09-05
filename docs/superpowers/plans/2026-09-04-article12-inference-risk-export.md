# Lots 7 à 9 — paramètres d'inférence, situations à risque, extraction unifiée

> ADR-263, suite des lots 5 (scellement) et 6 (registre des décisions).
> Analyse menée le 2026-09-04 **contre le code et la base**, pas contre le souvenir.

---

## 1. Ce qui existe déjà — vérifié, pas supposé

L'erreur qui guette ces trois lots est de construire un quatrième registre par-dessus
des données déjà enregistrées ailleurs. Inventaire factuel :

| Donnée attendue par l'article 12 | Où elle est déjà | Vérifié par |
|---|---|---|
| Modèle utilisé par appel | `token_usage_logs.model_name` | lecture du modèle |
| Créneau LLM configuré | `token_usage_logs.llm_type` (ADR-244) | idem |
| Latence, statut, nature de l'échec | `token_usage_logs.latency_ms / status / failure_kind` | idem |
| Jetons et coût | `token_usage_logs`, `message_token_summary` | idem |
| Version du catalogue d'outils | `agent_effects.catalogue_fingerprint` | ADR-263 lot 1 |
| Refus faute d'autorité | `agent_effects.status = refused` + `error_code` | ADR-263 lot 1 |
| Tour en échec | `agent_decisions.outcome = failed` | ADR-263 lot 6 |
| Appel LLM en échec | `token_usage_logs.status = 'error'` | ADR-244 |

**`token_usage_logs` est déjà le journal d'inférence, une ligne par appel, clé
`run_id` — la même clé que les trois registres.** Mesuré sur l'instance de
développement : 53 801 lignes, 28 Mo, soit ~545 octets par ligne.

Manquent, et seulement eux : le **fournisseur**, les **paramètres
d'échantillonnage** et l'**intention de raisonnement** effectivement envoyés.

---

## 2. Le piège que l'analyse a évité (lot 7)

Les paramètres existent en **trois versions différentes**, et une seule est
« les paramètres de l'inférence » :

1. `llm_config_overrides` — la **configuration**. Mutable, sans historique : la lire
   demain ne dit pas ce qui a tourné hier.
2. `LLMAgentConfig` résolu dans `get_llm()` — ce que LIA a **décidé**. Mais ADR-245
   **coerce** un niveau de raisonnement qu'un modèle refuse : la valeur décidée n'est
   donc pas toujours la valeur envoyée.
3. `invocation_params` remis au callback — ce qui est **réellement envoyé**.

Seule la troisième est vraie. Sonde exécutée (`FakeListChatModel`) :
`kwargs["invocation_params"]` **est** transmis à `on_chat_model_start`, où
`_store_call_context` lit déjà `metadata`. **Aucune plomberie nouvelle n'est
nécessaire.**

Deux découvertes que seule la sonde sur les vrais adaptateurs a révélées :

- **Le plafond de sortie s'écrit de trois façons** : `max_completion_tokens`
  (OpenAI), `max_tokens` (Anthropic), `max_output_tokens` (Google). Le raisonnement
  aussi : `reasoning_effort`, `thinking`, `thinking_level` / `thinking_budget`.
  Enregistrer l'orthographe du fournisseur produirait un registre où le même concept
  porte trois noms et n'est comparable avec rien.
- **Une capture aveugle est un risque de secret.** Aucun des quatre adaptateurs testés
  ne fait fuiter de clé aujourd'hui, mais rien ne le garantit du prochain. La règle est
  donc la même que pour l'export technique : **liste blanche**, jamais un vidage.

**Décision** : colonnes normalisées sur `token_usage_logs` (une seule orthographe),
plus un `params_digest` de l'ensemble des paramètres retenus, pour que « autre chose
a-t-il été réglé ? » reste une question à laquelle on peut répondre. Le digest réutilise
`chain_digest.row_digest` — l'encodage canonique existe déjà et est gelé par des vecteurs.

---

## 3. Le piège que l'analyse a évité (lot 8)

Inventaire des « situations à risque ». **Quatre seulement** ne laissent aucune trace
durable ; les autres sont déjà enregistrées (tableau §1) :

| Risque | Durable ? | Point de détection (unique) |
|---|---|---|
| Effet exécuté SANS ligne de registre | ❌ métrique seule | `effects/runtime.py` (2 raisons) |
| Consultations collectées par personne | ❌ métrique seule | `effects/treatments.py` |
| Rupture de chaîne | ❌ métrique seule | `chain_verify.py`, `notary.py` |
| Tour arrêté par le budget / un délai | ❌ rien | `react_exit_reason` (prédicat UNIQUE, ADR-248) |

Ces quatre-là se répartissent en **deux natures différentes**, et les confondre dans une
seule table serait la même faute qu'un seul registre pour les actions et les
consultations :

- **Le tour s'est arrêté avant d'aboutir** → c'est un fait DU TOUR. Sa place est une
  colonne `stop_reason` sur `agent_decisions`, **pas une table**. Le registre des
  décisions dit déjà `interrupted` ; il dira désormais *pourquoi*.
- **Le registre lui-même est incomplet** → cela ne peut pas être écrit dans le registre
  qui défaille. Une petite table `agent_integrity_events` s'impose, avec des espèces
  bornées, et elle doit être **LUE** par une surface, sinon c'est le sous-système non
  câblé que CLAUDE.md interdit.

Une métrique compte ; elle ne peut pas dire **quels** tours sont touchés. C'est
exactement la question qu'un utilisateur et qu'un régulateur posent, et c'est ce qui
justifie la table plutôt qu'un compteur de plus.

---

## 4. Lot 9 — une extraction, pas une machinerie

Tout existe : `TechnicalSpec`, `technical_row`, `pseudonymise`, `export_header`,
`render_jsonl`. Le lot 9 est une **composition** : un JSONL dont chaque ligne porte un
discriminant `kind`, couvrant les quatre registres plus l'inférence, sur une période et
un périmètre de comptes. Aucune nouvelle machinerie de rendu.

---

## 5. Plan d'actions

### Lot 7 — les paramètres de l'inférence
1. `llm/inference_params.py` : liste blanche + normalisation des trois orthographes vers
   un vocabulaire unique, plus le digest. **Pur**, testable sans réseau ni base.
2. Six colonnes nullables sur `token_usage_logs` (+ migration) : `provider`,
   `temperature`, `top_p`, `max_output_tokens`, `reasoning_level`,
   `reasoning_budget_tokens`, `params_digest`. Nullables **sans reprise d'historique** :
   elles décrivent les appels postérieurs, et inventer le passé serait pire que
   d'admettre son absence (même doctrine qu'ADR-244).
3. `callbacks.py::_store_call_context` capture depuis `invocation_params` ;
   `TokenUsageRecord` (NamedTuple à valeurs par défaut → additif) les porte ;
   `chat/service.py` et le dépôt les écrivent.
4. Déclaration dans `technical_export` (4e spec) et dans la carte des données.

### Lot 8 — les situations à risque
1. `stop_reason` sur `agent_decisions` + `note_stop_reason` appelé là où
   `react_exit_reason` est **déjà** résolu (un seul prédicat, ADR-248 invariant 2).
2. `agent_integrity_events` : espèces bornées, `user_id` et `run_id` nullables,
   aucun contenu. Écrit **aux points de détection existants**, à côté de la métrique —
   une détection, deux destinations, jamais un second détecteur.
3. Surfaces : la carte de scellement dit à l'utilisateur si SON tour est concerné ;
   la section admin les liste ; l'export les porte.

### Lot 9 — l'extraction unifiée
1. `article12_export.py` : composition des specs existantes, discriminant `kind`.
2. Un endpoint admin, un format (JSONL), le plafond ÉNONCÉ comme partout.

---

## 6. Plan de test (enrichi pendant l'implémentation, déroulé en revue)

**Famille A — normalisation des paramètres (pure, sans réseau)**
1. Les trois orthographes du plafond de sortie donnent la même colonne.
2. Un paramètre absent reste absent (`None`), jamais 0 ni une valeur inventée.
3. Une clé suspecte (`api_key`, `authorization`…) n'est JAMAIS retenue, même si un
   futur adaptateur la publie.
4. Le digest change quand un paramètre hors liste blanche change (sinon il ne sert à rien).
5. Le digest est stable pour deux appels identiques.
6. Un `invocation_params` vide ou absent ne lève pas.
7. L'intention de raisonnement est lue dans le vocabulaire d'ADR-245, jamais dans
   l'orthographe du fournisseur.

**Famille B — le chemin de bout en bout (back)**
8. Un appel enregistré porte le fournisseur et la température réellement envoyés.
9. Un appel en échec porte quand même les paramètres (c'est là qu'on les regarde).
10. Aucune régression sur les colonnes existantes de `token_usage_logs`.
11. Le `NamedTuple` étendu n'a cassé aucun appelant.

**Famille C — l'arrêt du tour**
12. Une sortie par budget écrit `stop_reason`, l'issue restant `interrupted`.
13. Un tour normal n'a pas de `stop_reason`.
14. La reprise HITL ne l'efface pas (COALESCE).

**Famille D — les événements d'intégrité**
15. Chaque point de détection écrit UNE ligne et incrémente sa métrique.
16. L'écriture ne peut jamais faire échouer le chemin qu'elle observe.
17. Les espèces sont bornées (garde de complétude au boot).
18. Suppression de compte : les lignes partent avec lui.

**Famille E — l'extraction unifiée**
19. Chaque ligne porte un `kind` connu.
20. Rien d'identifiant ne sort en clair (mêmes assertions que l'export technique).
21. Le plafond est ÉNONCÉ, jamais appliqué en silence.
22. La période filtre les cinq espèces de la même façon.

**Famille F — surfaces**
23. La carte n'affirme rien sur un tour dont le registre est incomplet sans le dire.
24. Responsive et composition `AlertIcon` + `AlertContent` (leçon de la revue du lot 6).
25. Six langues, parité stricte.

---

## 7. Ce que ce plan ne fait PAS

- **Aucune reprise d'historique.** Les lignes antérieures n'ont pas ces colonnes et le
  diront par `NULL`.
- **Aucun contenu de requête ni de réponse** n'entre nulle part : le lot 6 a établi le
  pointeur, il reste la règle.
- **Aucun nouveau système de journalisation.** Les événements d'intégrité sont bornés,
  doivent valoir zéro en production, et sont écrits là où la métrique est déjà émise.
