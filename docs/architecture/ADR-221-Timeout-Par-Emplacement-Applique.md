# ADR-221 : le réglage que l'exploitant voit est le réglage que le système applique

**Statut**: ✅ IMPLEMENTED (2026-08-16)
**Date**: 2026-08-16
**Origine**: contre-audit « Tokens fantômes » (F2)

## Contexte

Le champ `timeout_seconds` existait de bout en bout — dialogue
d'administration (libellé, infobulle, badge « modifié »), validation API
(`gt=0`), colonne `llm_config_overrides.timeout_seconds`, résolution
`LLMAgentConfig`, valeur déclarée pour les 57 emplacements — puis la chaîne
s'arrêtait : ni la factory ni l'adaptateur ne le lisaient, aucun client ne
recevait de timeout. Pendant ce temps, un second mécanisme fonctionnait sans
être visible : une quarantaine de sites enveloppent leur appel dans
`asyncio.wait_for` avec des durées lues dans les settings d'environnement.
Miroir exact de la doctrine ADR-184 : une valeur que le producteur peut
écrire mais que le système n'applique pas est un piège. S'y ajoutait
`router_llm_timeout_seconds`, défini depuis des années et lu nulle part — le
nœud routeur ne fait aucun appel LLM direct.

## Décision

### 1. Deux couches, deux rôles — et les deux sont vraies

Le `timeout_seconds` par emplacement devient la **borne transport par
tentative**, transmise au client de chaque provider (l'alias `timeout` est
accepté par les quatre SDK installés — vérifié : openai/deepseek
`request_timeout`, anthropic `default_request_timeout`, gemini `timeout` ;
le chemin Responses API le reçoit par paramètre explicite). Les barrières
`asyncio.wait_for` existantes restent la **borne d'expérience utilisateur**
au niveau des nœuds du graphe, inchangées — elles peuvent être plus serrées
(la barrière chat `response` reste à 60 s pendant que le client du même
emplacement, à 120 s, protège ses appelants SANS barrière : notification de
rappel, jobs de fond). Un `timeout` explicite dans le JSON `provider_config`
garde la priorité (échappatoire documentée).

### 2. Aucun défaut appliqué sans mesure préalable

Appliquer un timeout là où il n'y en avait pas peut couper des appels lents
qui aboutissaient. Plutôt qu'un déploiement en deux temps, les défauts ont
été confrontés à 30 jours de latences de production (p99 par nœud +
comptage des appels au-delà de 60 s) AVANT application. Six relèvements,
chacun commenté avec sa mesure dans `LLM_DEFAULTS` : `response` 60→120
(p99 47,4 s), `planner` 60→90 (44,7 s), `heartbeat_decision` 60→120
(59,7 s + 2 dépassements observés), `interest_content` 60→120 (~60 s + 1
dépassement), `open_loop_extraction` 45→90 (35,1 s),
`memory_reference_extraction` 30→45 (15,3 s). Les autres défauts dominent
leur p99 mesuré avec au moins ~2× de marge. Le test
`TestDefaultsHoldAgainstProduction` épingle chaque relèvement AVEC sa mesure.

### 3. Le réglage mort disparaît

`router_llm_timeout_seconds` et sa constante sont supprimés. Le champ visible
dans l'UI d'administration cesse d'être décoratif sans qu'une ligne de l'UI
ne change : c'est la couche d'application qui manquait.

## Conséquences

- L'administrateur qui règle un timeout règle réellement un timeout ; la
  clé de cache d'instances LLM intègre déjà `timeout_seconds` (model_dump),
  donc un changement d'override produit un client neuf.
- Les retries SDK (2 par défaut) peuvent porter l'attente cumulée d'une
  tentative au-delà du timeout unitaire — c'est le rôle assumé de la
  barrière externe, qui coupe l'expérience utilisateur comme avant.
- Tout futur emplacement déclare son timeout (test : aucun
  `timeout_seconds=None` dans `LLM_DEFAULTS`).
