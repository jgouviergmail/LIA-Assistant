# LLM Configuration Admin

> Administration dynamique des configurations LLM via interface web, sans redémarrage serveur.

**Version**: 1.0
**Date**: 2026-03-08
**Statut**: Implémenté

---

## Vue d'Ensemble

Le système d'administration LLM permet de gérer dynamiquement :
1. **Clés API des providers** (OpenAI, Anthropic, Gemini, DeepSeek, Perplexity, Ollama)
2. **Configuration de chaque type LLM** (34 types : provider, model, temperature, etc.)

Les changements sont effectifs **immédiatement** via un cache in-memory, sans redémarrage.

### Principe Architectural : Code = Source de Vérité

Les valeurs de paramétrage LLM sont définies dans des **constantes code** (`LLM_DEFAULTS` dans `domains/llm_config/constants.py`). Ces valeurs éprouvées en production servent de baseline. La base de données stocke uniquement les **overrides** (modifications par l'administrateur).

```
Flux de résolution :
  LLM_DEFAULTS (code) → DB override (admin UI) → Config effective

Bouton "Réinitialiser" :
  Supprime l'override DB → retour aux constantes code
```

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

### Résolution Clé API

| Source | Rôle | Priorité |
|--------|------|----------|
| DB (Fernet encrypted) | Admin UI, source principale | 1 (prioritaire) |
| `.env` (variable d'environnement) | Fallback pour compatibilité | 2 (si DB vide) |

> **Note**: La résolution API key utilise le DB en priorité, avec fallback `.env`. La migration `llm_config_002` a importé les clés `.env` existantes en DB. `_require_api_key()` dans `adapter.py` lève `ValueError` si aucune des deux sources n'a de clé.

### Contraintes Provider (filtrage automatique dans `adapter.py`)

| Provider | temperature | top_p | frequency_penalty | presence_penalty | reasoning_effort | Notes |
|----------|:-----------:|:-----:|:-----------------:|:----------------:|:----------------:|-------|
| **OpenAI** (standard) | 0-2.0 | 0-1.0 | -2 à 2 | -2 à 2 | — | Tous paramètres supportés |
| **OpenAI** (standard: gpt-4o, gpt-4.1, etc.) | 0-2.0 | 0-1.0 | -2 à 2 | -2 à 2 | — | Tous paramètres supportés |
| **OpenAI** (reasoning: o-series, gpt-5, gpt-5-mini/nano) | **omis** | **omis** | **omis** | **omis** | varies¹ | `REASONING_MODELS_PATTERN` |
| **OpenAI** (gpt-5.1/5.2 + effort=none) | 0-2.0 | 0-1.0 | **omis** | **omis** | incl. `none` | Sampling params réactivés |
| **Anthropic** (claude-3-7+, claude-4.x) | 0-**1.0** (cappé) | **omis** (conflit temp+top_p) | **omis** | **omis** | low/medium/high (→ `effort`) | |
| **Anthropic** (claude-3-5-sonnet) | 0-**1.0** (cappé) | **omis** | **omis** | **omis** | — | Pas de thinking |
| **Gemini** (2.5-flash, 2.5-pro, 3+) | 0-2.0 | 0-1.0 | **omis** | **omis** | low/high (→ `thinking_level`) | medium→low |
| **Gemini** (2.0-flash, *-lite) | 0-2.0 | 0-1.0 | **omis** | **omis** | — | Pas de thinking |
| **DeepSeek** (chat V3) | 0-2.0 | 0-1.0 | 0-2.0 | 0-2.0 | — | max_tokens cap 8192 |
| **DeepSeek** (reasoner R1) | **omis** | **omis** | **omis** | **omis** | — | Pas de tools, cap 64000 |
| **Perplexity** | 0-2.0 | 0-1.0 | 1.0-2.0³ | -2 à 2 | — | freq_penalty multiplicatif |
| **Ollama** | 0-2.0 | 0-1.0 | ~² | ~² | — | Model-dependent |

¹ reasoning_effort par modèle : o1-mini (non supporté), o1/o3/o4-mini (low/medium/high), gpt-5/5-mini (minimal/low/medium/high), gpt-5.1 (none/low/medium/high), gpt-5.2 (none/minimal/low/medium/high/xhigh)
² Ollama: freq/pres penalty mappés en interne vers `repeat_penalty`
³ Perplexity: `frequency_penalty` utilise une plage multiplicative (1.0=pas de pénalité, 2.0=maximum), différent de l'additive OpenAI

> Les paramètres **omis** sont automatiquement filtrés par `ProviderAdapter` avant l'appel API. L'Admin UI cache également les champs non supportés via `getModelConstraints()`.
>
> Pour la matrice complète par modèle, voir [LLM_PROVIDER_CONSTRAINTS.md](./LLM_PROVIDER_CONSTRAINTS.md).

---

## Fichiers Clés

### Backend

| Fichier | Rôle |
|---------|------|
| `domains/llm_config/constants.py` | `LLM_TYPES_REGISTRY` (metadata 34 types) + `LLM_DEFAULTS` (configs par défaut) |
| `domains/llm_config/models.py` | Tables `provider_api_keys` + `llm_config_overrides` |
| `domains/llm_config/schemas.py` | Schemas Pydantic (request/response) |
| `domains/llm_config/cache.py` | `LLMConfigOverrideCache` — cache in-memory (sync read, async populate) |
| `domains/llm_config/service.py` | `LLMConfigService` — CRUD + merge + audit |
| `domains/llm_config/router.py` | Endpoints REST admin (`/admin/llm-config/`) |
| `core/llm_config_helper.py` | `get_llm_config_for_agent()` — lit `LLM_DEFAULTS` + cache |

### Frontend

| Fichier | Rôle |
|---------|------|
| `types/llm-config.ts` | Interfaces TypeScript (miroir des schemas backend) |
| `hooks/useLLMConfig.ts` | Hook React (queries + mutations) |
| `components/settings/AdminLLMConfigSection.tsx` | Composant admin (providers + types + dialog édition) |

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
| `GET` | `/admin/llm-config/metadata/models` | Modèles disponibles par provider |

### Sémantique PUT (Full Replace)

Chaque PUT remplace **toute** la row d'override. Le frontend envoie l'état complet :
- Un champ `null` = utiliser le défaut code (`LLM_DEFAULTS`)
- Un champ non-null = override appliqué

---

## Cache In-Memory

### Pourquoi un cache in-memory ?

`get_llm()` est **synchrone** — impossible de faire un lookup async Redis/DB. Le cache in-memory (`dict` Python) offre :
- Lecture sync (0μs, dict lookup)
- Peuplé async au startup depuis la DB
- Invalidé directement par le service admin après chaque modification

### Lifecycle

```python
# Startup (main.py lifespan)
await LLMConfigOverrideCache.load_from_db(db)

# Admin modifie une config
await service.update_config(...)
await LLMConfigOverrideCache.invalidate_and_reload(db)  # Automatique

# Runtime (get_llm factory, sync)
override = LLMConfigOverrideCache.get_override("router")  # Dict lookup
api_key = LLMConfigOverrideCache.get_api_key("openai")     # Dict lookup
```

### Multi-Workers (futur)

Pour un déploiement multi-workers, ajouter un compteur Redis `sys:llm_config:version` comme signal de refresh inter-process. Non nécessaire pour single-worker (Raspberry Pi).

---

## 34 Types LLM

### Catégories

| Catégorie | Types |
|-----------|-------|
| **Pipeline** | `semantic_pivot`, `query_analyzer`, `router`, `planner`, `semantic_validator`, `context_resolver` |
| **Agents Domaine** | `contacts_agent`, `emails_agent`, `calendar_agent`, `drive_agent`, `tasks_agent`, `weather_agent`, `wikipedia_agent`, `perplexity_agent`, `brave_agent`, `web_search_agent`, `web_fetch_agent`, `places_agent`, `routes_agent` |
| **Query & Response** | `query_agent`, `response` |
| **HITL** | `hitl_classifier`, `hitl_question_generator`, `hitl_plan_approval_question_generator` |
| **Memory** | `memory_extraction`, `memory_reference_resolution` |
| **Background** | `interest_extraction`, `interest_content`, `heartbeat_decision`, `heartbeat_message`, `broadcast_translator` |
| **Specialized** | `voice_comment`, `mcp_description`, `mcp_excalidraw`, `evaluator` |

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
