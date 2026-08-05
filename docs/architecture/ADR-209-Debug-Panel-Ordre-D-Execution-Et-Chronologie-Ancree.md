# ADR-209 : le panneau de debug lit dans l'ordre d'exécution, sur une chronologie ancrée au run

**Date** : 2026-08-05
**Statut** : Accepté
**Contexte** : panneau de debug du chat (`apps/web/src/components/debug/`), émission backend (`streaming/debug_metrics_builder.py`, `debug_metrics_stages.py`, `chat/run_records.py`)

## Contexte

Le panneau de debug avait grandi par itérations (v3.1 → v3.3) et présentait quatre classes de défauts, toutes vérifiées sur le code avant décision :

1. **Ordre d'affichage ≠ ordre d'exécution.** Query Info s'affichait après la décision de routage ; Context Resolution et FOR_EACH (produits par le router) étaient rangés dans « Planning & Execution » ; les vagues *prévues* s'affichaient après la timeline *réelle*. La section « Execution Times » ordonnait les nœuds par une liste manuelle (`DEBUG_PIPELINE_NODE_ORDER`) et apposait tout nœud inconnu **après** `response` — en mode ReAct, `react_call_model` apparaissait après la réponse.
2. **Chronologie trompeuse inter-contextes.** Le tri du pipeline LLM reposait sur `sequence`, un compteur **par TrackingContext** : chaque extraction d'arrière-plan repart à 1 et entrait en collision avec l'appel n° 1 du routeur.
3. **Étapes invisibles.** Verdict du validateur sémantique, boucle ReAct, HITL, génération d'images (payload émis mais jamais affiché), TTS, coût LLM des open loops, compaction, mode d'exécution : aucun n'existait dans le panneau.
4. **Présentation hétérogène.** Trois langues mélangées, deux patrons de construction, quatre barres de score divergentes, palette sombre-seulement (`text-green-400`) côtoyant du clair-seulement (`bg-gray-200`), état vide en badge rouge « FAIL » pour une étape simplement non exécutée.

## Décision

### 1. Une chronologie ancrée au run, pas une liste manuelle

Chaque appel LLM porte désormais `started_offset_ms`, mesuré contre un **t0 run-level** (`chat/run_records.py`) partagé par tous les TrackingContexts du run (pipeline + tâches d'arrière-plan). `request_lifecycle` ordonne les nœuds par première apparition chronologique et `llm_pipeline` trie par `(started_offset_ms, sequence)` — `sequence` ne sert plus que de départage intra-contexte et de repli pour les données historiques. `DEBUG_PIPELINE_NODE_ORDER` est supprimée : une liste manuelle qui prétend être la chronologie est exactement le genre de table à la main que la doctrine des registres interdit.

Le front en tire un **waterfall** : chaque appel est positionné sur la ligne de temps du run (départ + durée), rendant lisible d'un coup d'œil ce qui s'est exécuté en série ou en parallèle.

### 2. Le panneau lit dans l'ordre d'exécution : 7 phases numérotées

`1 · Request → 2 · Analysis (router) → 3 · Planning → 4 · Execution → 5 · Response context → 6 · Background extraction → 7 · Totals & pipeline`. Chaque section est déclarée dans une table de phases de l'orchestrateur ; les sections sans données se replient derrière un disclosure « N idle sections » par phase (sur un tour conversationnel, deux tiers des sections sont vides — du bruit pur pour l'analyse).

### 3. Chaque étape du run est visible

Nouvelles sections émises par le backend (chacune isolée dans son try/except, toutes optionnelles, compatibles avec l'historique sessionStorage existant) : `semantic_validation` (verdict **informatif** — ADR-184 affichée en place : un plan rejeté s'exécute quand même), `react_execution` (itérations vs borne **publiée** `react_agent_max_iterations`), `hitl` (interrompu / repris + décision), `compaction` (stratégie, tokens économisés — nouvelle clé d'état `compaction_debug`), `execution_mode`, `voice` (dépense TTS, émise via `debug_metrics_update` car le chemin sync-fallback termine après le chunk principal), `llm_metadata` des open loops, et l'affichage front de `image_generation_calls/summary` que le backend émettait déjà.

### 4. Une grammaire de présentation, sur les tokens du design system

Anglais uniquement (surface technique). Tons sémantiques via les tokens (`success`/`warning`/`destructive`/`primary`, chips rendues par `Badge` — héritant de la garde de contraste 5 thèmes × clair/sombre) ; identités de nœuds par **familles bi-thèmes** (`utils/tones.ts`, chaque teinte brute avec sa variante `dark:`) ; barres de score uniques (`ScoreBar`, seuil **dessiné sur la barre**) avec table de seuils unique (`SCORE_SPACES`) ; état vide **neutre**. Anomalies collectées par passe pure (`collectAnomalies`) et affichées sur l'en-tête d'entrée + bandeau de synthèse scannable (route, moteur, durée, tokens, coût) pour comparer les requêtes sans les déplier. Zod est branché en **détecteur** (`SECTION_SCHEMAS`) : un payload dévié alimente le canal d'anomalies, jamais une disparition de section.

## Conséquences

- Les enregistrements historiques (sessionStorage) sans `started_offset_ms` retombent sur le tri par `sequence` — aucun crash, chronologie best-effort.
- `chat/service.py` décroît (extraction `run_records.py`), `debug_metrics_stages.py` héberge les sections d'étapes (ratchet de taille respecté partout).
- Le ratchet CC frontend a été **resserré** (50 → 48 hotspots) après décomposition.
- Toute nouvelle étape du pipeline devient visible automatiquement dans lifecycle/pipeline (chronologie auto) ; une nouvelle *section* reste un ajout dans la table des phases + `sectionPresence`.

## Références

- ADR-070 (mode ReAct), ADR-184 (verdict informatif, bornes publiées), ADR-205/206/207 (doctrine tons et densité)
- `docs/technical/DEBUG_PANEL.md` (architecture détaillée)
