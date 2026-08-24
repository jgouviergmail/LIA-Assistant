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

### `reasoning_effort` ↔ modèle : une intention, une coercition (ADR-245, v1.32.0)

Il n'y a plus qu'**une** forme stockée — `{"level": ..., "budget_tokens": ..., "exclude_from_output": ...}` (`core/reasoning_intent.py`) — et **une** échelle, ordinale et indépendante du fournisseur : `provider_default < none < minimal < low < medium < high < xhigh < max`. Ce qu'un modèle donné accepte n'est plus une colonne mais un **profil dérivé** de son couple (fournisseur, modèle) par `resolve_reasoning_profile` (`apps/api/src/infrastructure/llm/reasoning/profiles.py`), que `llm_models.reasoning_enum_values` peut **restreindre**, jamais élargir.

La question « changer de modèle laisse-t-il une valeur incompatible ? » a donc changé de nature : rien ne lève plus à l'instanciation, et les deux garde-fous qui *abandonnaient* la valeur sont partis avec les constructeurs typés qu'ils protégeaient. Il reste trois couches, avec trois rôles distincts :

0. **Écran Tarification LLM** (`components/settings/AdminLLMPricingSection.tsx`) — c'est là qu'on écrit la restriction, et le formulaire n'offre que ce que la famille propose : `GET /admin/llm/reasoning-family` résout `(fournisseur, modèle)` avec la **même** fonction que le traducteur et le validateur, et rend l'échelle en cases à cocher. Décocher est la seule chose que la colonne sache exprimer ; tout coché stocke `null`. Un modèle qu'aucune règle ne reconnaît est annoncé comme tel — sa colonne ne serait pas lue, et lui apprendre une nouvelle API de raisonnement est un changement de **code**.
1. **Frontend** (`components/settings/llm-config/reasoningHelpers.ts`) — deux prédicats, délibérément séparés : `reasoningEffortMatchesModel` décide ce qu'un **changement de modèle** conserve, `reasoningEffortIsVisible` décide ce qu'une **sauvegarde** envoie. Les confondre effaçait l'override entier — niveau compris — sur un budget hors bornes saisi dans un champ affiché à l'écran.
2. **Write path** (`LLMConfigService.update_config` → `validate_reasoning_effort`) — **rejette** en `422`, parce qu'un humain est là pour corriger. La validation interroge `resolve_reasoning_profile`, c'est-à-dire exactement la fonction qu'utilise le traducteur : validateur et traducteur ne peuvent plus diverger.
3. **Runtime** (`kwargs_for` → `coerce`) — **corrige** au lieu de refuser, sur un chemin sans humain. Le niveau se déplace vers le plus proche que le modèle propose ; les égalités tranchent **vers le haut**, `none` n'est jamais une cible, et c'est `can_disable` — pas l'appartenance à l'échelle — qui gouverne l'extinction. Chaque déplacement est compté (`llm_reasoning_coerced_total{model,from_level,to_level}`) et journalisé : ce n'est pas une erreur, mais le modèle ne fait pas ce que l'administrateur a demandé.

### Héritage du défaut au changement de modèle

Le merge (`merge_config`) **hérite** désormais simplement la valeur. Les deux abandons qu'il pratiquait ont été mesurés faux dans les deux sens :

- abandonner effaçait un effort choisi par l'administrateur. Mesuré le 2026-07-27 : les trois extracteurs de fond (mémoire, centres d'intérêt, journaux) tournaient **sans aucun bloc de raisonnement**, parce que l'interface n'envoie pas un champ égal au défaut du type et que la colonne stockait alors `NULL`. Un réglage incapable d'exprimer sa propre valeur par défaut est un réglage cassé ;
- et abandonner un `level="none"` hérité sur un modèle dont le défaut est « raisonnement actif » **allumait** silencieusement le raisonnement — l'inverse de ce que l'opérateur avait écrit, et facturé comme tel.

Ce que l'abandon protégeait — ne pas planter à l'instanciation — n'existe plus : `kwargs_for` ne lève jamais, et un modèle inconnu ne résout aucune famille, donc ne produit aucun kwarg.


### Plancher « thinking × budget » (ADR-179, v1.26.4)

Les tokens de raisonnement sont facturés **dans la fenêtre de complétion**
(`max_tokens`) : un raisonnement substantiel au-dessus d'un petit budget rend
la réponse tronquée ou vide (incident prod 2026-07-29 : `telephony_synthesis`
basculé sur deepseek-v4-flash effort `high` au-dessus d'un défaut de 600
tokens — chaque synthèse échouait). `validate_thinking_token_budget`
(`domains/llm_config/reasoning_validation.py`) rejette en `422`
(`thinking_budget_below_floor`) toute sauvegarde dont le raisonnement
**consomme le budget** — une forme, donc une règle : tout ce qui est au-dessus
de la bande légère (`provider_default`, `none`, `minimal`, `low`) est lourd, et
un budget de tokens explicite l'est quelle que soit sa taille — et
dont le `max_tokens` **effectif** (override fusionné sur les défauts via le
même `merge_config` que le runtime — laisser le champ vide hérite du défaut)
est sous `LLM_THINKING_MAX_TOKENS_FLOOR` (défaut 4000, `.env`). Appliqué au
chemin d'écriture admin **et** au boot sur `LLM_DEFAULTS` (fail-fast). Côté
UI, le toast de sauvegarde surface les `422` structurées : message localisé
avec les chiffres interpolés pour ce type d'erreur, `msg` backend en
description pour les autres (`structuredErrorDetail`,
`components/settings/llm-config/configDialogHelpers.ts`).

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
> **Admin UI — DB-driven sampling matrix (v1.20.1+)** : la fenêtre Configuration LLM ne calcule plus la visibilité des sliders via une regex côté frontend. Chaque modèle de `llm_models` porte 4 colonnes booléennes (`supports_temperature`, `supports_top_p`, `supports_frequency_penalty`, `supports_presence_penalty`) qui drivent **paramètre par paramètre** l'affichage des sliders. Le widget de raisonnement, lui, n'est plus déclaré : il est **dérivé** du profil résolu que publie `/llm-config/metadata` (famille, échelle acceptée, extinction possible, budget exprimable et ses bornes, exclusion du raisonnement de la réponse). Le catalogue n'y garde qu'un mot : `reasoning_enum_values`, qui **restreint** l'échelle d'un modèle sans jamais l'élargir (ADR-245, v1.32.0 — les colonnes `reasoning_widget` et `reasoning_budget_range` sont supprimées). Le `ProviderAdapter` reste l'autorité finale (philosophie A : "raw truth"), mais l'admin n'a plus aucune chance de saisir une valeur que l'API rejetterait.
>
> Pour la matrice complète par modèle, voir [LLM_PROVIDER_CONSTRAINTS.md](./LLM_PROVIDER_CONSTRAINTS.md). Pour la saisie de l'identité de raisonnement dans l'admin Tarification, voir [LLM_REASONING_IDENTITY.md](./LLM_REASONING_IDENTITY.md).

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
| `domains/llm_config/reasoning_validation.py` | `validate_reasoning_effort` (levant, 422) — interroge `resolve_reasoning_profile`, la fonction qu'utilise aussi le traducteur |
| `domains/llm_config/router.py` | Endpoints REST admin (`/admin/llm-config/`) |
| `core/llm_config_helper.py` | `get_llm_config_for_agent()` / `merge_config()` — défauts code + cache ; `reasoning_effort` est simplement hérité (ADR-245) |

### Frontend

| Fichier | Rôle |
|---------|------|
| `types/llm-config.ts` | Interfaces TypeScript (miroir des schemas backend) |
| `hooks/useLLMConfig.ts` | Hook React (queries + mutations) |
| `components/settings/AdminLLMConfigSection.tsx` | Composant admin (providers + types + dialog édition) |
| `components/settings/llm-config/ReasoningWidget.tsx` | Widget `reasoning_effort` (rendu piloté par le profil résolu publié par l'API) |
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
