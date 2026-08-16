# ADR-220 : un comptage qui repose sur la générosité du fournisseur n'est pas un comptage

**Statut**: ✅ IMPLEMENTED (2026-08-16)
**Date**: 2026-08-16
**Origine**: contre-audit « Tokens fantômes » (F1, F3, F4, F5, F7 + angles morts G1/G2)

## Contexte

Un fournisseur OpenAI-compatible n'émet l'objet `usage` sur une réponse
diffusée que si la requête le demande (`stream_options.include_usage`).
L'adaptateur posait cette demande pour deux branches (openai, qwen) et
l'avait omise pour deepseek — précisément le provider que le seed de
référence place sur les trois emplacements diffusés (`response` et les deux
générateurs de questions HITL).

La production n'a jamais cessé de compter — 510/510 appels `response`
comptabilisés sur 30 jours, mesuré avant correctif — mais uniquement parce
que DeepSeek envoie l'usage **sans qu'on le lui demande**. Rien ne demandait
ce comportement, rien ne le testait (zéro occurrence de `stream_options` /
`stream_usage` dans toute la suite), rien ne le surveillait : un appel payant
terminé sans usage produisait un libellé `model="unknown"` et un log DEBUG.
Le grand livre, le plafond de dépense quotidien (ADR-216) et tous les
tableaux de coût reposaient sur une politesse d'API.

Le même audit a confirmé quatre défauts voisins de la couche : une branche
« désactiver le streaming » inatteignable dont l'unique appelant croyait se
servir (F3) ; un cache qui mémorisait une complétion vide et la rejouait
pendant tout le TTL (F4) ; deux extractions JSON divergentes dont la
principale échouait sur trois formes courantes (F5) ; un module provider mort
de 259 lignes avec les tests qui simulaient sa couverture (F7). Le
contre-audit a ajouté deux angles morts : l'emplacement
`hitl_question_generator` n'a jamais écrit une ligne de tokens de toute
l'histoire de la base (chemin câblé mais rarement emprunté — le jour où il
l'est, rien ne garantissait l'attribution), et le pivot sémantique loguait la
requête utilisateur à INFO.

## Décision

### 1. La demande d'usage est déclarée, appliquée et vérifiée au boot

`PROVIDER_USAGE_CAPABILITIES` (`domains/llm_config/constants.py`) déclare le
mode de comptage de CHAQUE provider de chat : `stream_usage_flag` (openai,
qwen, deepseek — le client reçoit `stream_usage=True`), `native` (anthropic,
gemini — le SDK porte l'usage sans demande), `excluded` (ollama local et
gratuit, perplexity sur la clé de l'utilisateur final — demander l'usage
imputerait à LIA une dépense qu'elle ne porte pas). `validate_provider_usage_
capabilities` (doctrine ADR-085) refuse de démarrer sur un provider non
déclaré ; `test_provider_usage_options.py` épingle que la déclaration EST le
comportement de l'adaptateur, et fige sur le paquet installé le contrat
langchain qui avait rendu l'omission silencieuse (l'auto-activation ne joue
jamais quand `base_url` est posé).

Le drapeau retenu est `stream_usage=True` — champ de première classe de
`BaseChatOpenAI`, appliqué par `_should_stream_usage` aux seules requêtes
diffusées — et non le `model_kwargs["stream_options"]` historique qui
polluait chaque requête et exigeait une garde `if streaming` (DashScope
rejette `stream_options` quand `stream=false`).

### 2. Un appel payant sans usage devient un signal exploitable

`llm_calls_without_usage_total{node_name}` compte l'événement
(`MetricsCallbackHandler`, une seule incrémentation par appel), les deux
callbacks logguent en WARNING (node_name seulement — jamais de contenu),
et l'alerte `LLMCallsWithoutUsage` (seuil zéro, runbook dédié) le fait
remonter. C'est la partie du correctif qui couvre aussi les classes futures :
changement d'API amont, nouveau provider, chemin `hitl_question_generator`
le jour où il s'exécute (son câblage tracker est épinglé par
`test_question_generator_tracking.py`).

### 3. Les défauts voisins sont soldés à la racine

La branche morte `config_override["streaming"]` de la factory est supprimée
(le streaming est une fonction pure du `llm_type`) et le commentaire mensonger
du reminder corrigé (F3). `json_recovery.extract_json_payload` devient LA
seule extraction JSON depuis du texte modèle — fences, prose des deux côtés,
troncature, virgules traînantes, string-aware — consommée par le rescue des
tool-calls ET par le repli JSON-mode ; le corpus de l'audit (dix formes, trois
échecs historiques) est son contrat (F5). Le cache refuse d'écrire un résultat
dégénéré (None, chaîne blanche — les conteneurs vides restent cachables : un
négatif légitime n'est pas un échec) et le pivot sémantique traite une
traduction vide comme un échec, avec ses logs de contenu redescendus à DEBUG
(F4, G2). `openai_provider.py` et ses tests sont supprimés (F7) ; les champs
settings `{type}_llm_*` qu'il était seul à lire sont identifiés comme surface
morte résiduelle, à purger dans une passe dédiée (balayage `.env.example` +
parité des trois environnements).

## Conséquences

- Le comptage des trois emplacements diffusés est demandé contractuellement,
  plus subi ; s'il disparaît, l'alerte le dit en une heure.
- Toute extension du catalogue provider passe par une déclaration explicite
  de son mode de comptage — l'oubli est un échec de boot, plus un trou
  silencieux de plusieurs mois.
- Les gardes sont épinglés : registre ↔ adaptateur, contrat langchain
  installé, tracker HITL, corpus JSON, garde d'écriture cache.
