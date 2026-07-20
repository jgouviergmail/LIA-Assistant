# LLM Providers - Guide de Configuration

**Statut** : Actif
**Derniere mise a jour** : 2026-05-05 (v1.19.1 — DeepSeek V4 + base URLs paramétrables)
**Fichiers sources** : `apps/api/src/core/config/llm.py`, `apps/api/src/core/config/agents.py`, `apps/api/src/infrastructure/llm/providers/adapter.py`, `apps/api/src/infrastructure/llm/providers/_deepseek_patched.py`

---

## Table des matieres

1. [Vue d'ensemble](#vue-densemble)
2. [Providers supportes](#providers-supportes)
3. [Modeles par provider](#modeles-par-provider)
4. [Parametres de configuration .env](#parametres-de-configuration-env)
5. [Parametres par provider : compatibilite](#parametres-par-provider--compatibilite)
6. [Configuration avancee (PROVIDER_CONFIG)](#configuration-avancee-provider_config)
7. [LLM Types (composants configurables)](#llm-types-composants-configurables)
8. [Fallback et resilience](#fallback-et-resilience)
9. [Contraintes et incompatibilites](#contraintes-et-incompatibilites)
10. [Exemples de configuration](#exemples-de-configuration)

---

## Vue d'ensemble

Chaque composant LLM du pipeline (router, planner, response, agents, etc.) est configurable independamment. Il existe deux mécanismes de configuration :

**1. Admin UI (recommandé — sans redémarrage)** : Settings > Administration > LLM Configuration. Overrides stockés en DB, effectifs immédiatement. Voir [LLM_CONFIG_ADMIN.md](./LLM_CONFIG_ADMIN.md).

**2. Variables d'environnement (fallback)** : Chaque type LLM peut être configuré via `.env` selon le pattern ci-dessous. Les valeurs `.env` sont les defaults code si aucun override DB n'existe.

```
{LLM_TYPE}_LLM_PROVIDER=<provider>
{LLM_TYPE}_LLM_MODEL=<model_name>
{LLM_TYPE}_LLM_TEMPERATURE=<float>
{LLM_TYPE}_LLM_TOP_P=<float>
{LLM_TYPE}_LLM_FREQUENCY_PENALTY=<float>
{LLM_TYPE}_LLM_PRESENCE_PENALTY=<float>
{LLM_TYPE}_LLM_MAX_TOKENS=<int>
{LLM_TYPE}_LLM_REASONING_EFFORT=<none|minimal|low|medium|high>
{LLM_TYPE}_LLM_PROVIDER_CONFIG=<JSON>
```

> **Note** : Les clés per-agent LLM ne sont pas incluses dans `.env.example` — la configuration via Admin UI est préférable. Les valeurs defaults code sont définies dans `LLM_DEFAULTS` (`domains/llm_config/constants.py`).

**Flux** : `LLM_DEFAULTS` (code) → DB override (Admin UI) → Config effective → `ProviderAdapter.create_llm()` → `BaseChatModel`

---

## Providers supportes

| Provider | Valeur `.env` | Cle API requise | SDK LangChain | Notes |
|----------|---------------|-----------------|---------------|-------|
| **OpenAI** | `openai` | `OPENAI_API_KEY` | `langchain-openai` | Provider principal. Responses API pour cache ameliore |
| **Anthropic** | `anthropic` | `ANTHROPIC_API_KEY` | `langchain-anthropic` | Prompt caching automatique (beta header) |
| **DeepSeek** | `deepseek` | `DEEPSEEK_API_KEY` | `langchain-deepseek` | API compatible OpenAI. Thinking mode via model name |
| **Gemini** | `gemini` | `GOOGLE_GEMINI_API_KEY` | `langchain-google-genai` | Google AI. Parametrage different des autres |
| **Qwen** | `qwen` | `QWEN_API_KEY` | `langchain-openai` (compat) | Alibaba Cloud. DashScope OpenAI-compatible API |
| **Ollama** | `ollama` | _(aucune)_ | `langchain-openai` (compat) | Deploiement local. `OLLAMA_BASE_URL` requis |
| **Perplexity** | `perplexity` | `PERPLEXITY_API_KEY` | `langchain-openai` (compat) | Search-augmented. Pas de tools/structured output |

### Ou vivent les cles API

> **La base de donnees est la source de verite, pas le `.env`.** Depuis la
> migration `2026_03_08_0002-migrate_env_keys_to_db.py`, la table chiffree
> `provider_api_keys` (`src/domains/llm_config/models.py` — *"sole source of
> truth"*) porte les cles des providers, saisies via l'administration LLM.
> `ANTHROPIC_API_KEY`, `DEEPSEEK_API_KEY` et `QWEN_API_KEY` ne sont plus lus
> depuis l'environnement et **sont absents de `.env.example`** : les definir
> n'a aucun effet. La colonne « Cle API requise » du tableau ci-dessus nomme
> donc l'entree attendue **en base**, pas une variable d'environnement.

Restent dans le `.env` les cles qui servent hors du chat (voir `.env.example`) :

```bash
OPENAI_API_KEY=sk-...                   # embeddings et usages hors chat
GOOGLE_GEMINI_API_KEY=AI...
PERPLEXITY_API_KEY=pplx-...
OLLAMA_BASE_URL=http://localhost:11434  # URL du serveur Ollama local (pas une cle)
```

---

## Modeles par provider

### OpenAI

| Modele (valeur `.env`) | Context | Max Output | Type | Prix (input/output $/1M) |
|------------------------|---------|------------|------|--------------------------|
| `gpt-4.1` | 1M | 32K | Standard | $2.00 / $8.00 |
| `gpt-4.1-mini` | 1M | 16K | Standard | $0.40 / $1.60 |
| `gpt-4.1-nano` | 1M | 16K | Standard | $0.10 / $0.40 |
| `gpt-4o` | 128K | 16K | Standard | $2.50 / $10.00 |
| `gpt-4o-mini` | 128K | 16K | Standard | $0.15 / $0.60 |
| `gpt-5` | 1M | 65K | **Reasoning** | $1.25 / $10.00 |
| `gpt-5-mini` | 1M | 16K | **Reasoning** | $0.25 / $2.00 |
| `gpt-5-nano` | 1M | 16K | **Reasoning** | $0.05 / $0.40 |
| `gpt-5.1` | 1M | 65K | **Reasoning** | $1.25 / $10.00 |
| `gpt-5.2` | 1M | 65K | **Reasoning** | $1.75 / $14.00 |
| `gpt-5.4` | 1M | 65K | **Reasoning** | $2.50 / $15.00 |
| `gpt-5.4-mini` | 1M | 16K | **Reasoning** | $0.75 / $4.50 |
| `o4-mini` | 200K | 100K | **Reasoning** | $1.10 / $4.40 |
| `o3` | 200K | 100K | **Reasoning** | $2.00 / $8.00 |
| `o3-mini` | 200K | 100K | **Reasoning** | $1.10 / $4.40 |
| `o1` | 200K | 100K | **Reasoning** | $15.00 / $60.00 |
| `o1-mini` | 128K | 65K | **Reasoning** | $1.10 / $4.40 |

**Modeles de reasoning** (detectes par regex `^(o[0-9](-.*)?|gpt-5(-.*)?)`) :
- `temperature` est **automatiquement omis** (doit etre 1.0 ou absent)
- `top_p`, `frequency_penalty`, `presence_penalty` sont **automatiquement retires**
- `reasoning_effort` est supporte : `none`, `minimal`, `low`, `medium`, `high`

### Anthropic

| Modele (valeur `.env`) | Context | Max Output | Prix (input/output $/1M) |
|------------------------|---------|------------|--------------------------|
| `claude-opus-4-6` | 200K | 32K | $5.00 / $25.00 |
| `claude-opus-4-5` | 200K | 32K | $5.00 / $25.00 |
| `claude-opus-4` | 200K | 32K | $15.00 / $75.00 |
| `claude-sonnet-4-6` | 200K | 64K | $3.00 / $15.00 |
| `claude-sonnet-4-5` ou `claude-sonnet-4-5-20250514` | 200K | 64K | $3.00 / $15.00 |
| `claude-sonnet-4` | 200K | 64K | $3.00 / $15.00 |
| `claude-haiku-4-5` ou `claude-haiku-4-5-20251001` | 200K | 8K | $1.00 / $5.00 |
| `claude-3-5-sonnet-20241022` | 200K | 8K | $3.00 / $15.00 |
| `claude-3-5-haiku-20241022` | 200K | 8K | $0.80 / $4.00 |

**Notes Anthropic** :
- Prompt caching est **active automatiquement** via le header `anthropic-beta: prompt-caching-2024-07-31`
- `top_p`, `frequency_penalty`, `presence_penalty` sont **automatiquement retires** (non supportes)
- Extended Thinking (mode raisonnement) : via `PROVIDER_CONFIG` (voir section Configuration avancee)

### DeepSeek

| Modele (valeur `.env`) | Context | Max Output | Type | Prix (input/output $/1M) | Cache hit |
|------------------------|---------|------------|------|--------------------------|-----------|
| `deepseek-chat` | 128K | 8K | Standard (V3.2) | $0.28 / $0.42 | $0.028 |
| `deepseek-reasoner` | 128K | 64K | **Thinking** (V3.2) | $0.28 / $0.42 | $0.028 |

**Distinction thinking / non-thinking** : uniquement par le **nom du modele** dans `.env` :
```bash
# Non-thinking (standard)
RESPONSE_LLM_PROVIDER=deepseek
RESPONSE_LLM_MODEL=deepseek-chat

# Thinking (raisonnement)
PLANNER_LLM_PROVIDER=deepseek
PLANNER_LLM_MODEL=deepseek-reasoner
```

**Contraintes `deepseek-reasoner`** :
- Pas de support tools -> **interdit** pour les agents domain (contacts, email, calendar, etc.)
- Pas de structured output -> **warning** pour router/planner (JSON mode fallback)
- `reasoning_effort` est **ignore** (parametre OpenAI uniquement)

### Gemini

| Modele (valeur `.env`) | Context | Max Output | Prix (input/output $/1M) |
|------------------------|---------|------------|--------------------------|
| `gemini-3.1-pro-preview` | 1M | 65K | $2.00 / $12.00 |
| `gemini-3-pro-preview` | 1M | 65K | $2.00 / $12.00 |
| `gemini-3-flash-preview` | 1M | 65K | $0.50 / $3.00 |
| `gemini-2.5-pro` | 1M | 65K | $1.25 / $10.00 |
| `gemini-2.5-flash` | 1M | 65K | $0.30 / $2.50 |
| `gemini-2.5-flash-lite` | 1M | 65K | $0.10 / $0.40 |
| `gemini-2.0-flash` | 1M | 8K | $0.10 / $0.40 |
| `gemini-2.0-flash-lite` | 1M | 8K | $0.075 / $0.30 |

**Notes Gemini** :
- `frequency_penalty`, `presence_penalty` sont **automatiquement retires** (non supportes)
- `reasoning_effort` est **ignore** (parametre OpenAI uniquement)
- Le parametre `max_tokens` est mappe vers `max_output_tokens` de l'API Gemini

### Qwen (Alibaba Cloud)

| Modele (valeur config) | Context | Notes |
|------------------------|---------|-------|
| `qwen3-max` | 262K | Thinking only (pas de tools, pas de vision) |
| `qwen3.6-plus` | 1M | Tools + Vision + Thinking, latest generation |
| `qwen3.5-plus` | 1M | Tools + Vision + Thinking |
| `qwen3.5-flash` | 1M | Tools + Vision + Thinking, cout reduit |

**Notes Qwen** :
- Endpoint international : `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`
- Thinking mode : `enable_thinking` + `thinking_budget` via `extra_body`
- Implicit cache automatique (>=256 tokens, pas de flag necessaire)
- `frequency_penalty` non supporte (utiliser `presence_penalty`)
- Prix (international) : qwen3.5-flash $0.10/$0.40, qwen3.5-plus $0.40/$2.40, qwen3.6-plus $0.60/$3.60, qwen3-max $1.20/$6.00

### Ollama (local)

Modeles courants (le nom depend de ce qui est installe localement) :

| Modele (valeur `.env`) | Context | Notes |
|------------------------|---------|-------|
| `llama3.1` | 128K | Supports tools + JSON mode |
| `llama3.2` | 128K | Supports vision |
| `mistral` | 32K | Supports tools |
| `qwen2.5` | 128K | Supports tools |
| _(tout modele Ollama)_ | Variable | Capacites dependantes du modele |

**Notes Ollama** :
- Cout : **$0** (execution locale)
- API key factice (`"ollama"`) injectee automatiquement
- `OLLAMA_BASE_URL` configure l'endpoint (defaut : `http://localhost:11434`)
- Les capacites (tools, structured output) dependent du modele choisi
- **Dynamic discovery** : l'admin UI liste automatiquement les modeles installes via `GET /api/tags` + `POST /api/show` (capabilities reelles par modele, cache 60s, timeout 5s, fallback sur profils statiques)

### Perplexity (search-augmented)

| Modele (valeur `.env`) | Context | Notes |
|------------------------|---------|-------|
| `llama-3.1-sonar-small-128k-online` | 127K | $0.20 / $0.20 |
| `llama-3.1-sonar-large-128k-online` | 127K | $1.00 / $1.00 |
| _(tout modele Perplexity)_ | ~127K | Search-augmented |

**Notes Perplexity** :
- **Pas de tool calling** ni de structured output
- Chaque requete inclut une recherche web automatique
- API compatible OpenAI avec `base_url=https://api.perplexity.ai`

---

## Parametres de configuration .env

### Parametres standards (par LLM type)

| Parametre | Type | Range | Default | Description |
|-----------|------|-------|---------|-------------|
| `{TYPE}_LLM_PROVIDER` | string | `openai\|anthropic\|deepseek\|gemini\|ollama\|perplexity` | `openai` | Provider LLM |
| `{TYPE}_LLM_MODEL` | string | _(voir tableaux ci-dessus)_ | _(varie)_ | Nom exact du modele |
| `{TYPE}_LLM_TEMPERATURE` | float | 0.0 - 2.0 | _(varie)_ | Creativite (0=deterministe) |
| `{TYPE}_LLM_TOP_P` | float | 0.0 - 1.0 | 1.0 | Nucleus sampling |
| `{TYPE}_LLM_FREQUENCY_PENALTY` | float | -2.0 - 2.0 | 0.0 | Penalite de repetition |
| `{TYPE}_LLM_PRESENCE_PENALTY` | float | -2.0 - 2.0 | 0.0 | Penalite de presence |
| `{TYPE}_LLM_MAX_TOKENS` | int | > 0 | _(varie)_ | Tokens max en sortie |
| `{TYPE}_LLM_REASONING_EFFORT` | string | `none\|minimal\|low\|medium\|high` | _(vide)_ | Effort de raisonnement |
| `{TYPE}_LLM_PROVIDER_CONFIG` | JSON | _(objet JSON)_ | `{}` | Config avancee provider |

---

## Parametres par provider : compatibilite

Le `ProviderAdapter` filtre automatiquement les parametres non supportes pour eviter les erreurs API. Voici la matrice de compatibilite :

| Parametre | OpenAI standard | OpenAI reasoning | Anthropic | DeepSeek | Gemini | Ollama | Perplexity |
|-----------|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| `temperature` | Oui | **Omis** (force 1.0) | Oui | Oui | Oui | Oui | Oui |
| `top_p` | Oui | **Retire** | **Retire** (1) | Oui | Oui | Oui | Oui |
| `frequency_penalty` | Oui | **Retire** | **Retire** | Oui | **Retire** | Oui | Oui |
| `presence_penalty` | Oui | **Retire** | **Retire** | Oui | **Retire** | Oui | Oui |
| `max_tokens` | Oui (cap auto) | Oui | Oui | Oui (cap auto) | Oui (-> `max_output_tokens`) | Oui | Oui |
| `reasoning_effort` | **Ignore** | **Oui** | **Mappe** -> `effort` (2) | **Ignore** | **Mappe** -> `thinking_level` (3) | **Ignore** | **Ignore** |
| `provider_config` | Oui | Oui | Oui | Oui | Oui | Oui | Oui |

> **(1)** Anthropic : `top_p` est retire car Claude 4.5+ rejette `temperature` + `top_p` ensemble.
>
> **(2)** Anthropic : `reasoning_effort` est mappe vers le parametre natif `effort` de ChatAnthropic. Mapping : `minimal`/`low` -> `low`, `medium` -> `medium`, `high` -> `high`. Valeur `none` = ignore.
>
> **(3)** Gemini : `reasoning_effort` est mappe vers `thinking_level` de ChatGoogleGenerativeAI. Mapping : `low`/`medium` -> `low`, `high` -> `high`. Valeurs `none`/`minimal` = ignore.

### Caps automatiques de max_tokens

| Provider | Modele | Limite max_tokens |
|----------|--------|-------------------|
| OpenAI | `*mini*` ou `*nano*` | 16 384 |
| OpenAI | autres | 32 768 |
| DeepSeek | `deepseek-chat` | 8 192 |
| DeepSeek | `deepseek-reasoner` | 64 000 |

> Si `MAX_TOKENS` dans le `.env` depasse la limite, la valeur est automatiquement plafonnee avec un warning dans les logs.

---

## Configuration avancee (PROVIDER_CONFIG)

Le parametre `{TYPE}_LLM_PROVIDER_CONFIG` permet de passer des options specifiques au provider en JSON. Ces options sont mergees dans les kwargs du constructeur LLM.

### Anthropic : Extended Thinking

```bash
PLANNER_LLM_PROVIDER=anthropic
PLANNER_LLM_MODEL=claude-sonnet-4-5
PLANNER_LLM_PROVIDER_CONFIG={"thinking": {"type": "enabled", "budget_tokens": 10000}}
```

### Ollama : parametres specifiques

```bash
RESPONSE_LLM_PROVIDER=ollama
RESPONSE_LLM_MODEL=llama3.2
RESPONSE_LLM_PROVIDER_CONFIG={"num_predict": 2048, "num_ctx": 8192}
```

### Gemini : safety settings

```bash
RESPONSE_LLM_PROVIDER=gemini
RESPONSE_LLM_MODEL=gemini-2.5-flash
RESPONSE_LLM_PROVIDER_CONFIG={"safety_settings": [{"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"}]}
```

> **Note** : Le `PROVIDER_CONFIG` est un mecanisme pass-through. Les options valides dependent du SDK LangChain de chaque provider. Consultez la documentation LangChain du provider concerne.

---

## LLM Types (composants configurables)

Chaque composant du pipeline a sa propre configuration LLM independante :

### Pipeline principal

| LLM Type | Role | Besoin tools | Besoin structured output | Temperature recommandee |
|----------------------------|------|:---:|:---:|:-:|
| `ROUTER` | Classification de la requete | Non | Oui | 0.0 |
| `QUERY_ANALYZER` | Analyse semantique | Non | Oui | 0.0 |
| `SEMANTIC_VALIDATOR` | Validation du plan | Non | Oui | 0.0 |
| `PLANNER` | Generation du plan d'execution | Non | Oui | 0.0 |
| `RESPONSE` | Synthese de la reponse finale | Non | Non | 0.7 |
| `QUERY_AGENT` | Agent de requete generique | Oui | Non | 0.0 |
| `EVALUATOR` | Evaluation de la qualite | Non | Oui | 0.0 |

### Agents domaine (tool-using)

| LLM Type | Domaine | Temperature recommandee |
|----------------------------|---------|:-:|
| `CONTACTS_AGENT` | Google Contacts | 0.0 |
| `EMAILS_AGENT` | Gmail | 0.0 |
| `CALENDAR_AGENT` | Google Calendar | 0.0 |
| `DRIVE_AGENT` | Google Drive | 0.0 |
| `TASKS_AGENT` | Google Tasks | 0.0 |
| `WEATHER_AGENT` | Meteo | 0.0 |
| `WIKIPEDIA_AGENT` | Wikipedia | 0.0 |
| `PERPLEXITY_AGENT` | Recherche Perplexity | 0.0 |
| `BRAVE_AGENT` | Recherche Brave | 0.0 |
| `WEB_SEARCH_AGENT` | Recherche web | 0.3 |
| `WEB_FETCH_AGENT` | Extraction web | 0.3 |
| `PLACES_AGENT` | Google Places | 0.0 |
| `ROUTES_AGENT` | Google Routes | 0.0 |

> **Contrainte** : Les agents domaine utilisent des tools. Ils sont **incompatibles** avec `deepseek-reasoner`, les modeles Perplexity, et potentiellement certains modeles Ollama.

### Services auxiliaires

| LLM Type | Role | Config dans |
|----------------------------|------|-------------|
| `HITL_CLASSIFIER` | Classification HITL | `agents.py` |
| `HITL_QUESTION_GENERATOR` | Generation questions HITL | `agents.py` |
| `HITL_PLAN_APPROVAL_QUESTION` | Questions approbation plan | `agents.py` |
| `SEMANTIC_PIVOT` | Traduction query -> EN | `agents.py` |
| `CONTEXT_RESOLVER` | Resolution de contexte | `llm.py` |
| `MEMORY_EXTRACTION` | Extraction de memories | `agents.py` |
| `MEMORY_REFERENCE_RESOLUTION` | Resolution refs memoire | `agents.py` |
| `INTEREST_EXTRACTION` | Extraction centres d'interet | `llm.py` |
| `INTEREST_CONTENT` | Generation contenu interets | `llm.py` |
| `VOICE` | Commentaires vocaux | `voice.py` |
| `BROADCAST_TRANSLATOR` | Traduction broadcast | `agents.py` |
| `MCP_DESCRIPTION` | Description auto serveurs MCP | `mcp.py` |
| `MCP_EXCALIDRAW` | Generation diagrammes | `mcp.py` |
| `HEARTBEAT_DECISION` | Decision notification proactive | `agents.py` |
| `HEARTBEAT_MESSAGE` | Redaction message proactif | `agents.py` |

---

## Fallback et resilience

### ModelFallbackMiddleware

En cas d'echec du provider principal, le systeme bascule automatiquement sur les modeles de fallback :

```bash
# Liste ordonnee de fallback (CSV)
FALLBACK_MODELS=claude-sonnet-4-5,deepseek-chat
```

Le middleware detecte automatiquement le provider a partir du nom du modele et tente chaque fallback dans l'ordre.

### Responses API (OpenAI)

Les modeles OpenAI eligibles utilisent automatiquement la Responses API pour un cache ameliore (40-80%). En cas d'echec, fallback transparent vers Chat Completions.

L'eligibilite est determinee par le pattern regex `^(gpt-4\.1|gpt-5|o[1-9])`, ce qui rend la liste **auto-extensible** pour les futurs modeles de ces familles sans modification de code. Les modeles legacy (`gpt-4o`, `gpt-4-turbo`, `gpt-3.5`) ne sont **pas** eligibles et continuent d'utiliser Chat Completions.

---

## Contraintes et incompatibilites

### Matrice de compatibilite provider / fonctionnalite

| Fonctionnalite | OpenAI | Anthropic | DeepSeek chat | DeepSeek reasoner | Gemini | Ollama | Perplexity |
|----------------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Tool calling | Oui | Oui | Oui | **Non** | Oui | Modele-dep. | **Non** |
| Structured output | Oui | Oui | Oui | **Non** | Oui | **Non** (JSON fallback) | **Non** |
| Streaming | Oui | Oui | Oui | Oui | Oui | Oui | Oui |
| Vision | Oui | Oui | Non | Non | Oui | Modele-dep. | Non |
| Prompt caching | Responses API | Beta header | Cache hit natif | Cache hit natif | Non | Non | Non |
| Reasoning effort | Oui (o/gpt-5) | Non (via PROVIDER_CONFIG) | Non | Non | Non | Non | Non |

### Regles de validation automatiques

1. **`deepseek-reasoner`** + agent domaine -> **Erreur** (ValueError) : pas de tools
2. **`deepseek-reasoner`** + router/planner -> **Warning** : pas de structured output
3. **Ollama/Perplexity** + agent domaine -> **Warning** : support tools non garanti
4. **Reasoning model OpenAI** + `temperature != 1.0` -> temperature **omis** automatiquement
5. **Reasoning model OpenAI** + `top_p`/`frequency_penalty`/`presence_penalty` -> **retires** automatiquement
6. **`gpt-5.4` et versions ulterieures** (`/v1/chat/completions`) + function tools -> `reasoning_effort` **omis** automatiquement par l'adapter. L'API OpenAI ne supporte pas `reasoning_effort` simultanement avec des function tools sur ces modeles. Les appels sans tools conservent `reasoning_effort` normalement.

---

## Exemples de configuration

### Configuration full OpenAI (optimisee cout)

```bash
ROUTER_LLM_PROVIDER=openai
ROUTER_LLM_MODEL=gpt-4.1-nano
ROUTER_LLM_TEMPERATURE=0.0
ROUTER_LLM_MAX_TOKENS=300

PLANNER_LLM_PROVIDER=openai
PLANNER_LLM_MODEL=gpt-4.1-mini
PLANNER_LLM_TEMPERATURE=0.0
PLANNER_LLM_MAX_TOKENS=10000

RESPONSE_LLM_PROVIDER=openai
RESPONSE_LLM_MODEL=gpt-4.1-mini
RESPONSE_LLM_TEMPERATURE=0.7
RESPONSE_LLM_MAX_TOKENS=8000

# Agents domaine : nano pour les taches simples
CONTACTS_AGENT_LLM_PROVIDER=openai
CONTACTS_AGENT_LLM_MODEL=gpt-4.1-nano
```

### Configuration hybride OpenAI + Anthropic

```bash
# Planner : Claude pour le raisonnement complexe
PLANNER_LLM_PROVIDER=anthropic
PLANNER_LLM_MODEL=claude-sonnet-4-5
PLANNER_LLM_TEMPERATURE=0.0
PLANNER_LLM_MAX_TOKENS=10000

# Response : Claude pour la qualite de redaction
RESPONSE_LLM_PROVIDER=anthropic
RESPONSE_LLM_MODEL=claude-sonnet-4-5
RESPONSE_LLM_TEMPERATURE=0.7
RESPONSE_LLM_MAX_TOKENS=8000

# Router + Agents : OpenAI pour le cout
ROUTER_LLM_PROVIDER=openai
ROUTER_LLM_MODEL=gpt-4.1-nano
CONTACTS_AGENT_LLM_PROVIDER=openai
CONTACTS_AGENT_LLM_MODEL=gpt-4.1-nano
```

### Configuration avec reasoning (GPT-5)

```bash
PLANNER_LLM_PROVIDER=openai
PLANNER_LLM_MODEL=gpt-5
PLANNER_LLM_REASONING_EFFORT=medium
# temperature, top_p, frequency_penalty, presence_penalty sont ignores automatiquement
PLANNER_LLM_MAX_TOKENS=10000
```

### Configuration DeepSeek (budget minimal)

```bash
ROUTER_LLM_PROVIDER=deepseek
ROUTER_LLM_MODEL=deepseek-chat
ROUTER_LLM_TEMPERATURE=0.0

PLANNER_LLM_PROVIDER=deepseek
PLANNER_LLM_MODEL=deepseek-chat       # Pas deepseek-reasoner (pas de structured output)
PLANNER_LLM_TEMPERATURE=0.0

RESPONSE_LLM_PROVIDER=deepseek
RESPONSE_LLM_MODEL=deepseek-chat
RESPONSE_LLM_TEMPERATURE=0.7

# Agents domaine : OBLIGATOIREMENT deepseek-chat (pas reasoner)
CONTACTS_AGENT_LLM_PROVIDER=deepseek
CONTACTS_AGENT_LLM_MODEL=deepseek-chat
```

### Configuration Gemini (gratuit pour faible volume)

```bash
ROUTER_LLM_PROVIDER=gemini
ROUTER_LLM_MODEL=gemini-2.0-flash-lite
ROUTER_LLM_TEMPERATURE=0.0

RESPONSE_LLM_PROVIDER=gemini
RESPONSE_LLM_MODEL=gemini-2.5-flash
RESPONSE_LLM_TEMPERATURE=0.7

# Note : frequency_penalty, presence_penalty seront ignores
```

### Configuration Anthropic avec Extended Thinking

```bash
PLANNER_LLM_PROVIDER=anthropic
PLANNER_LLM_MODEL=claude-sonnet-4-5
PLANNER_LLM_TEMPERATURE=0.0
PLANNER_LLM_MAX_TOKENS=10000
PLANNER_LLM_PROVIDER_CONFIG={"thinking": {"type": "enabled", "budget_tokens": 10000}}
```

### Configuration locale Ollama

```bash
OLLAMA_BASE_URL=http://localhost:11434

RESPONSE_LLM_PROVIDER=ollama
RESPONSE_LLM_MODEL=llama3.2
RESPONSE_LLM_TEMPERATURE=0.7
RESPONSE_LLM_MAX_TOKENS=4096
RESPONSE_LLM_PROVIDER_CONFIG={"num_predict": 2048}
```

---

## Annexes

### Architecture du ProviderAdapter

```
get_llm(llm_type)
  |
  v
LLMAgentConfig (from settings)
  |
  v
ProviderAdapter.create_llm()
  |
  +-- provider == "deepseek" --> _create_deepseek_llm() [ChatDeepSeek]
  +-- provider == "gemini"   --> _create_gemini_llm() [ChatGoogleGenerativeAI]
  +-- provider == "openai" && Responses API eligible --> _create_openai_responses_llm() [ResponsesLLM]
  |     ResponsesLLM delegates tool schema conversion to convert_to_openai_function() (LangChain),
  |     which correctly filters InjectedToolArg parameters from tool signatures before submission.
  +-- provider == "openai"    --> _prepare_provider_config() --> init_chat_model() [ChatOpenAI]
  +-- provider == "anthropic" --> _prepare_provider_config() --> init_chat_model() [ChatAnthropic]
  +-- provider == "ollama"    --> _prepare_provider_config(base_url=OLLAMA_URL) --> init_chat_model() [ChatOpenAI compat]
  +-- provider == "perplexity"--> _prepare_provider_config(base_url=perplexity) --> init_chat_model() [ChatOpenAI compat]
```

### Fichiers source

| Fichier | Contenu |
|---------|---------|
| `apps/api/src/core/config/llm.py` | `LLMSettings` : cles API, context windows, config par LLM type (domaine agents) |
| `apps/api/src/core/config/agents.py` | `AgentsSettings` : config par LLM type (HITL, planner, memory, etc.) |
| `apps/api/src/core/config/voice.py` | `VoiceSettings` : config LLM voix |
| `apps/api/src/core/config/mcp.py` | `MCPSettings` : config LLM MCP (description, Excalidraw) |
| `apps/api/src/core/llm_agent_config.py` | `LLMAgentConfig` : Pydantic model de config par agent |
| `apps/api/src/infrastructure/llm/factory.py` | `get_llm()` : factory avec merge settings + override |
| `apps/api/src/infrastructure/llm/providers/adapter.py` | `ProviderAdapter` : creation instances, filtrage params, helper `_get_base_url(provider)` (env-first resolution) |
| `apps/api/src/infrastructure/llm/providers/_deepseek_patched.py` | `ChatDeepSeekPatched` : sous-classe locale qui round-trip `reasoning_content` entre tours (workaround de l'upstream `langchain-deepseek==1.0.1`, v1.19.1+). Voir section dédiée plus bas. |
| `apps/api/src/infrastructure/llm/model_profiles.py` | `get_model_profile()` lit depuis `ModelCapabilitiesCache`. La constante `FALLBACK_PROFILES` (~750 lignes) a été supprimée en v1.19.0 ([ADR-078](../architecture/ADR-078-LLM-Catalogue-DB-Source-Of-Truth.md)) au profit du catalogue DB. |
| `apps/api/src/infrastructure/llm/model_capabilities_cache.py` | `ModelCapabilitiesCache` : singleton chargé au boot depuis la table `llm_models`, invalidé cross-worker via Pub/Sub (ADR-063). Source de vérité pour `is_reasoning_model`, capabilities, provider. |
| `apps/api/src/core/constants.py` | `REASONING_MODELS_PATTERN` : regex de fallback (utilisée uniquement pour les modèles absents du cache). En v1.19.0, le flag `is_reasoning_model` du catalogue est désormais authoritative. |

---

## Provider base URLs paramétrables (v1.19.1+)

Trois providers exposent un **endpoint OpenAI-compatible** qui peut nécessiter d'être surchargé selon le déploiement (région différente, gateway compatible auto-hébergé, mock de test, redirection à travers un proxy d'entreprise). Le pattern est uniforme : variable d'environnement ``{PROVIDER}_BASE_URL``, fallback sur l'endpoint officiel documenté du fournisseur.

| Provider | Variable d'env | Default fallback | Cas d'usage |
|----------|----------------|------------------|-------------|
| Ollama | `OLLAMA_BASE_URL` | `http://host.docker.internal:11434/v1` | Self-hosted local, déploiement Docker, gateway centralisé |
| Perplexity | `PERPLEXITY_BASE_URL` | `https://api.perplexity.ai` | Proxy d'entreprise, mock de test |
| Qwen | `QWEN_BASE_URL` | `https://dashscope-us.aliyuncs.com/compatible-mode/v1` | Bascule régionale us → cn (`https://dashscope.aliyuncs.com/compatible-mode/v1`), gateway compatible |

La résolution se fait via le helper ``_get_base_url(provider)`` dans ``providers/adapter.py`` : la variable d'env vide ou non définie retombe silencieusement sur le default ; une URL non-vide est utilisée telle quelle et un log structuré ``provider_base_url_from_env`` est émis pour la traçabilité.

DeepSeek, OpenAI, Anthropic, Gemini : URL gérées par leurs SDK respectifs (LangChain partner packages). Pas d'override LIA-side, mais les SDK exposent eux-mêmes ``base_url`` / ``api_base`` paramétrables si besoin (voir leur documentation respective).

---

## DeepSeek V4 — patch local du round-trip `reasoning_content` (v1.19.1+)

### Le bug

Avec l'arrivée de la famille DeepSeek V4 en mai 2026, l'API DeepSeek impose une nouvelle contrainte sur le mode thinking : **le champ ``reasoning_content`` produit par le modèle au tour N doit être renvoyé tel quel dans le payload du tour N+1** lorsqu'il s'agit d'un flow multi-tours avec tools. À défaut, l'API rejette la seconde requête :

```
openai.BadRequestError: Error code: 400 - {
    'error': {
        'message': 'The reasoning_content in the thinking mode must be passed back to the API.',
        'type': 'invalid_request_error',
    }
}
```

### Pourquoi `langchain-deepseek==1.0.1` ne le fait pas

Le ``ChatDeepSeek`` upstream (version 1.0.1, sortie le 2025-11-13, latest sur PyPI au 2026-05-05) hérite de ``BaseChatOpenAI``. Le path ``_get_request_payload`` y délègue à ``_convert_message_to_dict`` qui **drop** silencieusement les ``additional_kwargs`` lors de la sérialisation. Côté lecture (réponse → AIMessage) le package extrait correctement ``reasoning_content`` dans ``additional_kwargs``, mais côté écriture (AIMessage → payload du tour suivant), rien ne le ré-injecte.

Six PRs upstream tentent ce fix sur six mois ; aucune n'a été mergée :

- [PR #37179](https://github.com/langchain-ai/langchain/pull/37179) — fermée par bot pour assignment manquant (mai 2026)
- [PR #37065](https://github.com/langchain-ai/langchain/pull/37065) — closed (avril 2026)
- [PR #34199](https://github.com/langchain-ai/langchain/pull/34199) — closed pour V3.2 thinking (déc. 2025)
- [PR #35094](https://github.com/langchain-ai/langchain/pull/35094), [#34516](https://github.com/langchain-ai/langchain/pull/34516), [#34177](https://github.com/langchain-ai/langchain/pull/34177) — open, sans review depuis février 2026

Issue de référence côté communauté : [#37178](https://github.com/langchain-ai/langchain/issues/37178) (ouverte le 2026-05-04, encore sans réponse de mainteneur au moment de la v1.19.1).

### Notre fix

Module ``apps/api/src/infrastructure/llm/providers/_deepseek_patched.py`` — sous-classe ``ChatDeepSeekPatched(ChatDeepSeek)`` qui override ``_get_request_payload`` :

```python
class ChatDeepSeekPatched(ChatDeepSeek):
    def _get_request_payload(self, input_, *, stop=None, **kwargs):
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)

        # Re-resolve original messages: the parent's _convert_message_to_dict
        # drops additional_kwargs, so we still need access to them.
        original_messages = self._convert_input(input_).to_messages()
        reasoning_contents = [
            msg.additional_kwargs.get("reasoning_content")
            for msg in original_messages
            if isinstance(msg, AIMessage)
        ]

        # Walk the payload's assistant messages in order; inject the matching
        # reasoning_content if it exists.
        ai_idx = 0
        for message in payload["messages"]:
            if message["role"] == "assistant":
                if (
                    ai_idx < len(reasoning_contents)
                    and reasoning_contents[ai_idx] is not None
                ):
                    message["reasoning_content"] = reasoning_contents[ai_idx]
                ai_idx += 1

        return payload
```

L'override est ported directement de PR #37179 (28 lignes ajoutées / 11 supprimées dans la PR upstream candidate ; on en garde l'essence sans la partie Azure-specific qui n'est pas pertinente pour LIA).

### Application unconditionnelle

``_create_deepseek_llm`` instancie ``ChatDeepSeekPatched`` pour **tous** les modèles DeepSeek (V3 et V4, thinking on et off). Pour les modèles qui ne produisent jamais de ``reasoning_content`` (V3 ``deepseek-chat`` sans thinking), le tableau ``reasoning_contents`` reste vide et l'override est un no-op total. Aucune régression, aucune branche conditionnelle nécessaire.

### Critères de suppression

Quand `langchain-deepseek` (ou la nouvelle stack `langchain-openai` qui pourrait absorber le fix) ship une release avec round-trip natif :

1. Bumper `requirements.txt` vers la version qui contient le fix.
2. Vérifier que les 7 tests `TestChatDeepSeekPatchedRoundTrip` (et les 6 tests `TestIsV4ThinkingEnabledDetection` qui dépendent de `ChatDeepSeekPatched.extra_body`) passent encore avec ``ChatDeepSeek`` directement (suppression de l'instanciation patched).
3. Supprimer ``_deepseek_patched.py``, le replace par ``from langchain_deepseek import ChatDeepSeek`` direct dans ``adapter.py``.
4. Adapter les tests pour viser ``ChatDeepSeek`` natif.
5. Cette section de docs peut alors être archivée — laisser un pointer "Patch removed in vX.Y, see CHANGELOG".

Pas urgent — le patch est petit (~50 lignes), bien testé (13 tests dédiés), et n'impacte ni les performances ni les autres providers.
