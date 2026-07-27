# LLM Configuration Admin

> Administration dynamique des configurations LLM via interface web, sans redémarrage serveur.

**Version**: 1.0
**Date**: 2026-03-08
**Statut**: Implémenté

---

## Vue d'Ensemble

Le système d'administration LLM permet de gérer dynamiquement :
1. **Clés API des providers** (OpenAI, Anthropic, Gemini, DeepSeek, Perplexity, Ollama)
2. **Configuration de chaque type LLM** (35 types : provider, model, temperature, etc.)

Les changements sont effectifs **immédiatement** via un cache in-memory, sans redémarrage.

### Principe Architectural : Code = Source de Vérité

Les valeurs de paramétrage LLM sont définies dans des **constantes code** (`LLM_DEFAULTS` dans `domains/llm_config/constants.py`). Ces valeurs éprouvées en production servent de baseline. La base de données stocke uniquement les **overrides** (modifications par l'administrateur).

```
Flux de résolution :
  LLM_DEFAULTS (code) → DB override (admin UI) → Config effective

Bouton "Réinitialiser" :
  Supprime l'override DB → retour aux constantes code
```

### Garantie d'Application (v1.16.1)

**Tous** les chemins runtime de résolution LLM passent par `get_llm_config_for_agent()` ou `get_llm()` (qui l'appelle). Aucun code ne lit `settings.*_llm_*` directement pour créer ou configurer un LLM.

**Règle pour les développeurs** : ne **jamais** construire un `LLMAgentConfig` à la main depuis `settings.*`. Utiliser :
- `get_llm("type")` pour obtenir une instance LLM (résolution automatique)
- `get_llm_config_for_agent(settings, "type").model` pour accéder aux valeurs effectives (ex: logging, métriques)

---

## Architecture

```
Admin UI (Next.js Settings > Administration)
  ↓ API calls (/admin/llm-config/)
FastAPI Router (superuser only)
  ↓
LLMConfigService (DB + Audit)
  ↓                          ↓
provider_api_keys table    llm_config_overrides table
  ↓                          ↓
LLMConfigOverrideCache (in-memory, sync read)
  ↓                          ↓
ProviderAdapter            get_llm_config_for_agent()
  ↓                          ↓
  ← ← ← ← ← ← ← ← ← ← ← get_llm() factory
  ↓
BaseChatModel
```

### Résolution Config

| Source | Rôle | Priorité |
|--------|------|----------|
| `LLM_DEFAULTS` (code) | Valeurs éprouvées, baseline | Fallback |
| DB override (cache) | Modifications admin | Prioritaire |

Le merge (`core/llm_config_helper.py::merge_config`) applique les champs non-null de l'override par-dessus les défauts code, avec deux réconciliations sur `reasoning_effort` (voir ci-dessous).

### Cohérence `reasoning_effort` ↔ modèle (robustesse au changement de modèle/provider)

La **forme** d'un `reasoning_effort` dépend du `reasoning_widget` du modèle : `none` → `null` ; `enum` → `{"effort": "<valeur>"}` ; `budget_int` → `{"budget": <int>}` ; `toggle_budget` → `{"enabled": <bool>, "budget"?: <int|null>}`. Changer de modèle ou de provider sur un type LLM ne doit **jamais** laisser une valeur de forme incompatible — sinon le builder de raisonnement typé (`infrastructure/llm/providers/reasoning_builders.py`) lèverait un `RuntimeError` à l'instanciation du LLM. Trois couches le garantissent :

1. **Frontend** (`components/settings/AdminLLMConfigSection.tsx`) — au changement de `model` ou de `provider`, `reasoning_effort` est conservé **uniquement** si sa forme matche le `reasoning_widget` du nouveau modèle (et, pour `enum`, si la valeur est dans `reasoning_enum_values`), sinon remis à `null`. Helper `coerceReasoningEffortForModel` dans `components/settings/llm-config/reasoningHelpers.ts`. Changement de provider → `model` reset à `''` → `reasoning_effort: null`.
2. **Write path** (`LLMConfigService.update_config`) — `reasoning_effort` est validé (`validate_reasoning_effort`) contre le **modèle effectif** (`update.model`, ou `LLM_DEFAULTS[llm_type].model` si `update.model` est `null`) ; une combinaison invalide est rejetée en `422` avec un `ctx` structuré (`domains/llm_config/reasoning_validation.py`).
3. **Merge runtime** (`merge_config` → `_reconcile_reasoning_effort`) — filet de sécurité ultime : si la config effective (défauts + override) porte un `reasoning_effort` dont la forme/valeur ne matche pas le `reasoning_widget` du modèle effectif (ligne d'override périmée après un changement de modèle non géré côté UI, seed obsolète, édition manuelle, bug antérieur), il est **droppé** (→ défaut intrinsèque du modèle) et un warning structuré `llm_config_reasoning_effort_dropped` est loggé. `get_llm()` ne plante donc jamais sur ce motif, quelle que soit l'origine de l'incohérence.

### Héritage du défaut au changement de modèle (v1.25.29)

Une quatrième situation manquait à la liste ci-dessus : l'override change le **modèle** sans fournir de `reasoning_effort`. Le merge y répondait par un abandon **inconditionnel** du défaut code — ce qui a produit un défaut mesuré le 2026-07-27 : les trois extracteurs de fond (mémoire, centres d'intérêt, journaux) tournaient **sans aucun bloc de raisonnement**.

La chaîne complète du défaut, chaque maillon étant individuellement raisonnable :

1. l'UI n'envoie que les champs qui **diffèrent des défauts** (sémantique d'override) — choisir `low` alors que `low` *est* le défaut du type n'envoie donc rien ;
2. l'écriture est un remplacement intégral (`model_dump(exclude_unset=False)`) — le champ absent devient `NULL` en base ;
3. le cache ne retient que les champs **non nuls** — la clé disparaît du dictionnaire d'override ;
4. `merge_config` lisait « modèle changé, aucun effort fourni » comme « aucun raisonnement », au lieu de « garder le défaut ».

Un réglage incapable d'exprimer sa propre valeur par défaut est un réglage cassé. L'héritage exige désormais une **preuve** de compatibilité (`_is_inheritable_reasoning_effort`) : le défaut n'est conservé que si le modèle effectif est connu du catalogue **et** que sa valeur convient à son `reasoning_widget`. Un modèle inconnu (tag Ollama découvert dynamiquement, catalogue non chargé) retombe sur l'abandon — la propriété de sûreté que l'abandon inconditionnel protégeait est préservée.


Prédicat partagé : `reasoning_effort_matches_widget(caps, value)` (jumeau non-levant de `validate_reasoning_effort`), réutilisé par les couches 1 et 3 — une seule source de vérité pour « cette valeur est-elle valide pour ce modèle ? ».

### Résolution Clé API

| Source | Rôle | Priorité |
|--------|------|----------|
| DB (Fernet encrypted) | Admin UI, source principale | 1 (prioritaire) |
| `.env` (variable d'environnement) | Fallback pour compatibilité | 2 (si DB vide) |

> **Note**: La résolution API key utilise le DB en priorité, avec fallback `.env`. La migration `llm_config_002` a importé les clés `.env` existantes en DB. `_require_api_key()` dans `adapter.py` lève `ValueError` si aucune des deux sources n'a de clé.

> **Scope de ce système**: Ce système Admin UI gère les **56 types LLM** (registre `LLM_TYPES_REGISTRY`) (router, planner, contacts_agent, etc.). Les configurations LLM d'infrastructure (Excalidraw, MCP description generation) restent dans `.env` via `MCPSettings`. Les clés API provider (OPENAI_API_KEY, etc.) sont dans `.env` comme fallback.

### Contraintes Provider (filtrage automatique dans `adapter.py`)

| Provider | temperature | top_p | frequency_penalty | presence_penalty | reasoning_effort | Notes |
|----------|:-----------:|:-----:|:-----------------:|:----------------:|:----------------:|-------|
| **OpenAI** (standard) | 0-2.0 | 0-1.0 | -2 à 2 | -2 à 2 | — | Tous paramètres supportés |
| **OpenAI** (standard: gpt-4o, gpt-4.1, etc.) | 0-2.0 | 0-1.0 | -2 à 2 | -2 à 2 | — | Tous paramètres supportés |
| **OpenAI** (reasoning: o-series, gpt-5, gpt-5-mini/nano) | **omis** | **omis** | **omis** | **omis** | varies¹ | `is_reasoning_model` flag from `llm_models` catalogue (DB-source-of-truth, [ADR-078](../architecture/ADR-078-LLM-Catalogue-DB-Source-Of-Truth.md)); `REASONING_MODELS_PATTERN` regex used as fallback |
| **OpenAI** (gpt-5.1/5.2 + effort=none) | 0-2.0 | 0-1.0 | **omis** | **omis** | incl. `none` | Sampling params réactivés |
| **Anthropic** (claude-3-7+, claude-4.x) | 0-**1.0** (cappé) | **omis** (conflit temp+top_p) | **omis** | **omis** | low/medium/high (→ `effort`) | |
| **Anthropic** (claude-3-5-sonnet) | 0-**1.0** (cappé) | **omis** | **omis** | **omis** | — | Pas de thinking |
| **Gemini** (2.5-flash, 2.5-pro, 3+) | 0-2.0 | 0-1.0 | **omis** | **omis** | low/high (→ `thinking_level`) | medium→low |
| **Gemini** (2.0-flash, *-lite) | 0-2.0 | 0-1.0 | **omis** | **omis** | — | Pas de thinking |
| **DeepSeek** (chat V3, legacy) | 0-2.0 | 0-1.0 | 0-2.0 | 0-2.0 | — | max_tokens cap 8192 |
| **DeepSeek** (reasoner R1, legacy) | **omis** | **omis** | **omis** | **omis** | — | Pas de tools, cap 64000 |
| **DeepSeek V4** (`deepseek-v4-flash`, `deepseek-v4-pro`) | 0-2.0⁷ | ✅⁷ | ✅⁷ | ✅⁷ | none/low/medium/high (→ `thinking.type` + `reasoning_effort`) | max_tokens cap 64000. Voir [LLM_PROVIDER_CONSTRAINTS.md §DeepSeek V4](./LLM_PROVIDER_CONSTRAINTS.md) pour le mapping complet et les contraintes structured output |
| **Perplexity** | 0-2.0 | 0-1.0 | 1.0-2.0³ | -2 à 2 | — | freq_penalty multiplicatif. Base URL paramétrable via `PERPLEXITY_BASE_URL` (v1.19.1+) |
| **Ollama** | 0-2.0 | 0-1.0 | ~² | ~² | — | Model-dependent. Base URL paramétrable via `OLLAMA_BASE_URL` |

¹ reasoning_effort par modèle : o1-mini (non supporté), o1/o3/o4-mini (low/medium/high), gpt-5/5-mini (minimal/low/medium/high), gpt-5.1 (none/low/medium/high), gpt-5.2 (none/minimal/low/medium/high/xhigh)
² Ollama: freq/pres penalty mappés en interne vers `repeat_penalty`
³ Perplexity: `frequency_penalty` utilise une plage multiplicative (1.0=pas de pénalité, 2.0=maximum), différent de l'additive OpenAI

⁷ DeepSeek V4: temperature/top_p/penalties sont **silencieusement ignorés par l'API** quand thinking est activé (`reasoning_effort != none`). L'adapter les strip localement pour fidélité du log. Avec thinking activé + structured output forcé via `tool_choice` (ce que LangChain `with_structured_output(method="function_calling")` produit), l'API retourne 400 — le dispatch automatique vers JSON-mode fallback dans `structured_output.py` rend cela transparent. Base URL hardcodée via `langchain-deepseek`.

> Les paramètres **omis** sont automatiquement filtrés par `ProviderAdapter` avant l'appel API.
>
> **Admin UI — DB-driven sampling matrix (v1.20.1+)** : la fenêtre Configuration LLM ne calcule plus la visibilité des sliders via une regex côté frontend. Chaque modèle de `llm_models` porte 4 colonnes booléennes (`supports_temperature`, `supports_top_p`, `supports_frequency_penalty`, `supports_presence_penalty`) qui drivent **paramètre par paramètre** l'affichage des sliders. Le widget de reasoning (`enum`, `budget_int`, `toggle_budget`, `none`) est lui aussi déclaré au niveau modèle via la colonne `reasoning_widget` et ses jeux de valeurs (`reasoning_enum_values` JSONB list, `reasoning_budget_range` JSONB `{min, max, off_sentinel, dynamic_sentinel}`). Le `ProviderAdapter` reste l'autorité finale (philosophie A : "raw truth"), mais l'admin n'a plus aucune chance de saisir une valeur que l'API rejetterait.
>
> Pour la matrice complète par modèle, voir [LLM_PROVIDER_CONSTRAINTS.md](./LLM_PROVIDER_CONSTRAINTS.md). Pour le mécanisme de templates dans l'admin Tarification, voir [LLM_PRICING_TEMPLATES.md](./LLM_PRICING_TEMPLATES.md).

---

## Fichiers Clés

### Backend

| Fichier | Rôle |
|---------|------|
| `domains/llm_config/constants.py` | `LLM_TYPES_REGISTRY` (metadata 35 types) + `LLM_DEFAULTS` (configs par défaut) |
| `domains/llm_config/models.py` | Tables `provider_api_keys` + `llm_config_overrides` |
| `domains/llm_config/schemas.py` | Schemas Pydantic (request/response) |
| `domains/llm_config/cache.py` | `LLMConfigOverrideCache` — cache in-memory (sync read, async populate) |
| `domains/llm_config/service.py` | `LLMConfigService` — CRUD + merge + audit |
| `domains/llm_config/reasoning_validation.py` | `validate_reasoning_effort` (levant, 422) + `reasoning_effort_matches_widget` (prédicat) — cohérence `reasoning_effort` ↔ `reasoning_widget` |
| `domains/llm_config/router.py` | Endpoints REST admin (`/admin/llm-config/`) |
| `core/llm_config_helper.py` | `get_llm_config_for_agent()` / `merge_config()` / `_reconcile_reasoning_effort()` — défauts code + cache + réconciliation |

### Frontend

| Fichier | Rôle |
|---------|------|
| `types/llm-config.ts` | Interfaces TypeScript (miroir des schemas backend) |
| `hooks/useLLMConfig.ts` | Hook React (queries + mutations) |
| `components/settings/AdminLLMConfigSection.tsx` | Composant admin (providers + types + dialog édition) |
| `components/settings/llm-config/ReasoningWidget.tsx` | Widget reasoning_effort (rendu piloté par `reasoning_widget`) |
| `components/settings/llm-config/reasoningHelpers.ts` | `coerceReasoningEffortForModel` — normalise `reasoning_effort` au changement de modèle |

---

## API Endpoints

Tous les endpoints requièrent le rôle **superuser**.

| Méthode | Path | Description |
|---------|------|-------------|
| `GET` | `/admin/llm-config/providers` | Liste status clés API (masquées) |
| `PUT` | `/admin/llm-config/providers/{provider}` | Met à jour clé API (encrypted) |
| `DELETE` | `/admin/llm-config/providers/{provider}` | Supprime clé API (provider indisponible) |
| `GET` | `/admin/llm-config/types` | Liste tous les LLM types avec config effective |
| `GET` | `/admin/llm-config/types/{llm_type}` | Config d'un LLM type |
| `PUT` | `/admin/llm-config/types/{llm_type}` | Met à jour config (full replace) |
| `POST` | `/admin/llm-config/types/{llm_type}/reset` | Reset vers défauts code |
| `GET` | `/admin/llm-config/metadata/models` | Modèles disponibles par provider (static profiles) |
| `GET` | `/admin/llm-config/providers/ollama/models` | Modèles Ollama installés (discovery dynamique) |

### Dynamic Ollama Model Discovery

L'endpoint `/providers/ollama/models` utilise une discovery en deux phases :
1. `GET /api/tags` — liste tous les modèles installés (noms, tailles, familles)
2. `POST /api/show` × N — interroge les **capabilities réelles** de chaque modèle en parallèle (`tools`, `vision`, `thinking`, `embedding`)

Le champ `source` dans la réponse indique la provenance :
- `"live"` — modèles et capabilities récupérés en temps réel depuis le serveur Ollama
- `"fallback"` — profils par défaut conservateurs (Ollama injoignable). Note v1.19.0+ : la constante `FALLBACK_PROFILES` (~750 lignes) a été supprimée ([ADR-078](../architecture/ADR-078-LLM-Catalogue-DB-Source-Of-Truth.md)) ; les profils servis viennent désormais soit du `ModelCapabilitiesCache` (catalogue DB) si le modèle y est connu, soit de défauts conservateurs Python définis localement dans `model_profiles._get_fallback_profile()`.

Les résultats sont cachés en mémoire pendant 60 secondes (`OLLAMA_MODEL_CACHE_TTL_SECONDS`). Le timeout HTTP est de 5 secondes par requête (`OLLAMA_DISCOVERY_TIMEOUT_SECONDS`). Si `/api/show` échoue pour un modèle spécifique, ses capabilities sont vides (isolation par modèle). Si `/api/tags` échoue, l'endpoint retourne les profils statiques connus (dégradation gracieuse).

Le frontend déclenche ce fetch uniquement quand l'admin sélectionne Ollama comme provider dans le dialog de configuration d'un LLM type (pas au chargement de la page).

### Sémantique PUT (Full Replace)

Chaque PUT remplace **toute** la row d'override. Le frontend envoie l'état complet :
- Un champ `null` = utiliser le défaut code (`LLM_DEFAULTS`)
- Un champ non-null = override appliqué
- Sélectionner un modèle/provider qui rend la forme du `reasoning_effort` courant incompatible le remet à `null` côté frontend avant l'envoi (cf. la section « Cohérence `reasoning_effort` ↔ modèle » ci-dessus) ; le write path le revalide de toute façon contre le modèle effectif.

---

## Cache In-Memory

### Pourquoi un cache in-memory ?

`get_llm()` est **synchrone** — impossible de faire un lookup async Redis/DB. Le cache in-memory (`dict` Python) offre :
- Lecture sync (0μs, dict lookup)
- Peuplé async au startup depuis la DB
- Invalidé directement par le service admin après chaque modification

### Lifecycle

```python
# Startup (lifespan → startup/caches.py::init_config_caches, ADR-123)
await LLMConfigOverrideCache.load_from_db(db)

# Admin modifie une config
await service.update_config(...)
await LLMConfigOverrideCache.invalidate_and_reload(db)  # Automatique

# Runtime (get_llm factory, sync)
override = LLMConfigOverrideCache.get_override("router")  # Dict lookup
api_key = LLMConfigOverrideCache.get_api_key("openai")     # Dict lookup
```

### Multi-Workers (ADR-063)

Cross-worker cache invalidation is handled via Redis Pub/Sub (ADR-063). When `invalidate_and_reload()` is called, it reloads locally then publishes an event to `cache:invalidation` Redis channel. Other workers' subscriber tasks receive the event and call `load_from_db()`. The publisher PID is included to skip self-reload. See `src/infrastructure/cache/invalidation.py`.

---

## Types LLM

> La liste exhaustive et à jour est `LLM_TYPES_REGISTRY` (`src/domains/llm_config/constants.py`) — 56 types au 2026-07. Le tableau ci-dessous donne les catégories principales.

### Catégories

| Catégorie | Types |
|-----------|-------|
| **Pipeline** | `semantic_pivot`, `query_analyzer`, `router`, `planner`, `semantic_validator`, `context_resolver` |
| **Agents Domaine** | `contacts_agent`, `emails_agent`, `calendar_agent`, `drive_agent`, `tasks_agent`, `weather_agent`, `wikipedia_agent`, `perplexity_agent`, `brave_agent`, `web_search_agent`, `web_fetch_agent`, `places_agent`, `routes_agent` |
| **Query & Response** | `query_agent`, `response` |
| **HITL** | `hitl_classifier`, `hitl_question_generator`, `hitl_plan_approval_question_generator` |
| **Memory** | `memory_extraction`, `memory_reference_extraction`, `memory_reference_resolution` |
| **Background** | `interest_extraction`, `interest_content`, `heartbeat_decision`, `heartbeat_message`, `broadcast_translator`, `personality_translation` |
| **Initiative** | `initiative` — Post-execution cross-domain enrichment |
| **MCP ReAct** | `mcp_react_agent` — Iterative sub-agent for regular MCP servers with `iterative_mode` |
| **MCP App (ReAct)** | `mcp_app_react_agent` — Iterative sub-agent for MCP App servers (with interactive widgets like Excalidraw). Auto-selected when `app_resource_uri` present. Defaults to Qwen 3.6-plus. |
| **Specialized** | `voice_comment`, `mcp_description`, `evaluator` |

---

## Sécurité

- **Clés API jamais retournées en clair** : masquage `****...{4 derniers chars}`
- **Encryption at rest** : Fernet (via `encrypt_data()` / `decrypt_data()`)
- **Clés décryptées uniquement** dans le cache in-memory (process memory)
- **Audit trail** : toutes les actions admin logguées via `AdminAuditLog` (IP, user-agent, action, details)
- **Accès superuser only** : `get_current_superuser_session` dependency

---

## Tests

### Backend

```bash
# Tests unitaires
.venv/Scripts/pytest tests/unit/domains/llm_config/ -v

# Tests spécifiques
.venv/Scripts/pytest tests/unit/domains/llm_config/test_constants.py -v  # Registry/defaults consistency
.venv/Scripts/pytest tests/unit/domains/llm_config/test_cache.py -v      # Cache sync reads
.venv/Scripts/pytest tests/unit/domains/llm_config/test_config_helper.py -v  # Config resolution
```

---

## Nettoyage Futur

Les settings classes (`core/config/llm.py`, `agents.py`, etc.) contiennent encore ~270 variables LLM qui sont maintenant redondantes avec `LLM_DEFAULTS`. Le nettoyage complet nécessite de migrer les références dans :
- `bootstrap.py` (logging)
- 14 agent builders (paramètre `llm_model`)
- Services (response_node, semantic_validator, hitl, interests, heartbeat, voice)

Ce nettoyage sera fait dans une itération dédiée pour minimiser les risques de régression.
