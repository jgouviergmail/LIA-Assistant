# ADR-179 : Sortie structurée — chokepoint unique gardé par AST et plancher de budget de complétion sous raisonnement

**Statut**: ✅ IMPLEMENTED (2026-07-29)
**Date**: 2026-07-29
**Décideurs**: Utilisateur (verrou systémique approuvé « avec un message explicite pour l'utilisateur ») + investigation prod

> **Note de mise à jour (2026-08-27, v1.32.0)** — la décision de cet ADR (le
> chokepoint gardé par AST et le plancher de budget) reste en vigueur. Seul le
> mécanisme cité dans les alternatives a changé : les **formes stockées** du
> raisonnement et le `reasoning_widget` qui les discriminait n'existent plus
> ([ADR-245](ADR-245-Reasoning-Unification.md)). Le prédicat de lourdeur lit
> désormais le `level` d'un `ReasoningIntent` unique, ce qui rend l'argument
> d'alors — « ne pas dupliquer la connaissance des constructeurs » — plus vrai
> encore : il n'y a plus qu'un traducteur.

## Contexte

Incident production du 2026-07-29 (second signalement utilisateur sur le même
symptôme) : chaque retour d'appel téléphonique était livré en **anglais**, sans
le débrief structuré ADR-174 — le texte reçu était le résumé brut du vendor
(ElevenLabs, 3ᵉ personne). Deux défauts emboîtés, chacun prouvé
indépendamment :

1. **Contournement du chokepoint.** `telephony/return_synthesis.py` appelait
   `llm.with_structured_output(...)` en direct — le seul site du dépôt à ne pas
   passer par `infrastructure/llm/structured_output.py`. Or ce chokepoint porte
   les contraintes provider qu'un appel brut ignore : DeepSeek V4 avec thinking
   actif **rejette le `tool_choice` forcé** (`400 — Thinking mode does not
   support this tool_choice`), et doit être servi par le fallback JSON-mode.
   Quand l'override admin a basculé `telephony_synthesis` sur
   `deepseek-v4-flash` effort `high` (09:04 UTC), chaque synthèse a échoué et le
   fallback best-effort a livré le résumé vendor anglais, débrief vide. Le
   correctif langue v1.26.2 (directive LANGUAGE dans le contexte) était déployé
   mais en aval d'un appel LLM qui mourait avant exécution.
2. **Budget calibré avant l'ère thinking.** Même via le chokepoint, la synthèse
   échouait encore : `LLM_DEFAULTS["telephony_synthesis"].max_tokens = 600`
   (calibré avant le débrief ADR-174, sortie bien plus longue) était consommé
   **entièrement par le raisonnement** (mesuré en dev : contenu vide, puis JSON
   tronqué à ~370 caractères). Les tokens de raisonnement sont facturés dans la
   fenêtre de complétion ; l'admin ne voyait aucun lien entre les deux champs —
   laisser `max_tokens` vide hérite silencieusement d'un défaut inadapté.

## Décision

1. **Le chokepoint est le seul chemin de sortie structurée** —
   `synthesize_return` passe par `get_structured_output_with_retry` (provider
   réel transmis, usage capturé par callback) ; la classe de défaut est fermée
   par un **garde AST** (`tests/unit/test_no_direct_structured_output_guard.py`,
   pattern du garde timezone : scan des `ast.Call`, allowlist réduite au module
   chokepoint, self-checks anti-rot). Prouvé ROUGE sur le site fautif avant le
   correctif.
2. **`TokenCaptureHandler` partagé** (`infrastructure/llm/token_capture.py`) —
   consolide les deux copies privées divergentes (heartbeat lisait
   `usage_metadata`, open-loops lisait `llm_output.token_usage`) : lecture des
   deux surfaces, fallback seulement, jamais de double comptage.
3. **Recalibration** de `telephony_synthesis` : `max_tokens` 600 → 5000,
   `timeout` 20 s → 60 s (parité `heartbeat_decision`, même forme de tâche).
4. **Plancher systémique** `LLM_THINKING_MAX_TOKENS_FLOOR` (défaut 4000,
   paramétrable) : sauvegarder une config dont le raisonnement **consomme le
   budget de complétion** (enum hors `none/off/minimal/low`, toggle Qwen
   activé, budget Gemini non nul — prédicat par FORME, pas de matrice provider
   qui pourrirait) avec un `max_tokens` **effectif** sous le plancher est
   rejeté en **422 structurée** (`thinking_budget_below_floor`). Évalué sur la
   config effective (override fusionné sur les défauts via le même
   `merge_config` que le runtime), au chemin d'écriture admin ET au boot sur
   `LLM_DEFAULTS` (fail-fast). Le frontend cesse d'avaler les 422 structurées :
   message localisé ×6 avec les chiffres interpolés pour ce type d'erreur,
   `msg` backend en description pour les autres.

## Alternatives écartées

- **Avertir sans bloquer** : l'incident a prouvé qu'un signal non bloquant est
  invisible — le toast générique masquait déjà le 422 explicite de la matrice
  de raisonnement.
- **Plancher uniforme incluant `minimal`/`low`** : aurait interdit 10 défauts
  légitimes (extractions OpenAI à raisonnement mesuré négligeable, budgets
  500-1000) ; l'exemption est documentée dans le prédicat.
- **Matrice de lourdeur par provider** : dupliquerait la connaissance des
  builders de raisonnement et divergerait ; les formes stockées sont déjà
  discriminées par le `reasoning_widget` du modèle.
- **Relever silencieusement `max_tokens` au save** : mutation cachée du choix
  admin ; le refus explicite avec les chiffres rend la contrainte apprenable.

## Conséquences

- Tout futur consommateur de sortie structurée hérite des parades provider
  (DeepSeek V4 thinking, Anthropic extended thinking, strict mode OpenAI) par
  construction — un contournement ne compile plus (CI rouge).
- Une config admin « thinking lourd × petit budget » est impossible à
  enregistrer ; les 24 types à petit budget par défaut restent des
  configurations valides tant que le raisonnement n'y est pas activé.
- Le spend de la synthèse téléphonie reste tracké (G-1) via le handler partagé.

## Références

- `apps/api/src/infrastructure/llm/structured_output.py` (chokepoint)
- `apps/api/src/domains/llm_config/reasoning_validation.py::validate_thinking_token_budget`
- `apps/api/tests/unit/test_no_direct_structured_output_guard.py` (garde AST)
- [ADR-174](ADR-174-Call-Debrief-Persistence.md) (débrief), [ADR-127](ADR-127-Agentic-Telephony.md) (téléphonie)
- `docs/technical/TELEPHONY.md`, `docs/technical/LLM_CONFIG_ADMIN.md`
