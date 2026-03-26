# LIA — Guida Tecnica Completa

> Architettura, pattern e decisioni ingegneristiche di un assistente IA multi-agente di nuova generazione.
>
> Documentazione di presentazione tecnica destinata ad architetti, ingegneri ed esperti tecnici.

**Versione**: 2.1
**Data**: 2026-03-25
**Applicazione**: LIA v1.12.0
**Licenza**: AGPL-3.0 (Open Source)

---

## Indice

1. [Contesto e scelte fondanti](#1-contesto-e-scelte-fondanti)
2. [Stack tecnologico](#2-stack-tecnologico)
3. [Architettura backend: Domain-Driven Design](#3-architettura-backend--domain-driven-design)
4. [LangGraph: orchestrazione multi-agente](#4-langgraph--orchestrazione-multi-agente)
5. [La pipeline di esecuzione conversazionale](#5-la-pipeline-di-esecuzione-conversazionale)
6. [Il sistema di pianificazione (ExecutionPlan DSL)](#6-il-sistema-di-pianificazione-executionplan-dsl)
7. [Smart Services: ottimizzazione intelligente](#7-smart-services--ottimizzazione-intelligente)
8. [Routing semantico ed embeddings locali](#8-routing-semantico-ed-embeddings-locali)
9. [Human-in-the-Loop: architettura a 6 livelli](#9-human-in-the-loop--architettura-a-6-livelli)
10. [Gestione dello state e message windowing](#10-gestione-dello-state-e-message-windowing)
11. [Sistema di memoria e profilo psicologico](#11-sistema-di-memoria-e-profilo-psicologico)
12. [Infrastruttura LLM multi-provider](#12-infrastruttura-llm-multi-provider)
13. [Connettori: astrazione multi-fornitore](#13-connettori--astrazione-multi-fornitore)
14. [MCP: Model Context Protocol](#14-mcp--model-context-protocol)
15. [Sistema vocale (STT/TTS)](#15-sistema-vocale-stttts)
16. [Proattività: Heartbeat e azioni pianificate](#16-proattività--heartbeat-e-azioni-pianificate)
17. [RAG Spaces e ricerca ibrida](#17-rag-spaces-e-ricerca-ibrida)
18. [Browser Control e Web Fetch](#18-browser-control-e-web-fetch)
19. [Sicurezza: defence in depth](#19-sicurezza--defence-in-depth)
20. [Osservabilità e monitoring](#20-osservabilità-e-monitoring)
21. [Performance: ottimizzazioni e metriche](#21-performance--ottimizzazioni-e-metriche)
22. [CI/CD e qualità](#22-cicd-e-qualità)
23. [Pattern di ingegneria trasversali](#23-pattern-di-ingegneria-trasversali)
24. [Architettura delle decisioni (ADR)](#24-architettura-delle-decisioni-adr)
25. [Potenziale di evoluzione ed estensibilità](#25-potenziale-di-evoluzione-ed-estensibilità)

---

## 1. Contesto e scelte fondanti

### 1.1. Perché queste scelte?

Ogni decisione tecnica di LIA risponde a un vincolo concreto. Il progetto mira a un assistente IA multi-agente **auto-ospitabile su hardware modesto** (Raspberry Pi 5, ARM64), con totale trasparenza, sovranità sui dati e supporto multi-fornitore LLM. Questi vincoli hanno guidato l'intero stack.

| Vincolo | Conseguenza architetturale |
|---------|--------------------------|
| Auto-hosting ARM64 | Docker multi-arch, embeddings locali E5 (nessuna dipendenza API), Playwright chromium cross-platform |
| Sovranità dei dati | PostgreSQL locale (nessun SaaS DB), crittografia Fernet a riposo, sessioni Redis locali |
| Multi-fornitore LLM | Factory pattern con 7 adattatori, configurazione per nodo, nessun accoppiamento forte a un provider |
| Trasparenza totale | 350+ metriche Prometheus, debug panel integrato, tracciamento token per token |
| Affidabilità in produzione | 59 ADR, 2 300+ test, osservabilità nativa, HITL a 6 livelli |
| Costi controllati | Smart Services (89% di risparmio token), embeddings locali, prompt caching, filtraggio del catalogo |

### 1.2. Principi architetturali

| Principio | Implementazione |
|-----------|----------------|
| **Domain-Driven Design** | Bounded context in `src/domains/`, aggregati espliciti, livelli Router/Service/Repository/Model |
| **Hexagonal Architecture** | Porte (protocol Python) e adattatori (client concreti Google/Microsoft/Apple) |
| **Event-Driven** | SSE streaming, propagazione ContextVar, background task fire-and-forget |
| **Defence in Depth** | 5 livelli per gli usage limits, 6 livelli HITL, 3 livelli anti-allucinazione |
| **Feature Flags** | Ogni sottosistema attivabile/disattivabile (`{FEATURE}_ENABLED`) |
| **Configuration as Code** | Pydantic BaseSettings composto via MRO, catena di priorità APPLICATION > .ENV > CONSTANT |

### 1.3. Metriche del codebase

| Metrica | Valore |
|---------|--------|
| Test | 2 300+ (unit, integration, agents, benchmark) |
| Fixture riutilizzabili | 170+ |
| Documenti di documentazione | 190+ |
| ADR (Architecture Decision Record) | 59 |
| Metriche Prometheus | 350+ definizioni |
| Dashboard Grafana | 18 |
| Lingue supportate (i18n) | 6 (fr, en, de, es, it, zh) |

---

## 2. Stack tecnologico

### 2.1. Backend

| Tecnologia | Versione | Ruolo | Perché questa scelta |
|------------|----------|-------|---------------------|
| Python | 3.12+ | Runtime | Ecosistema ML/IA più ricco, async nativo, typing completo |
| FastAPI | 0.135.1 | API REST + SSE | Validazione automatica Pydantic, doc OpenAPI, async-first, performance |
| LangGraph | 1.1.2 | Orchestrazione multi-agente | Unico framework con state persistence + cicli + interrupt (HITL) nativi |
| LangChain Core | 1.2.19 | Astrazioni LLM/tools | Decoratore `@tool`, formati messaggi, callback standardizzati |
| SQLAlchemy | 2.0.48 | ORM async | `Mapped[Type]` + `mapped_column()`, sessioni async, `selectinload()` |
| PostgreSQL | 16 + pgvector | Database + vector search | Checkpoint LangGraph nativi, ricerca semantica HNSW, maturità |
| Redis | 7.3.0 | Cache, sessioni, rate limiting | Operazioni O(1), sliding window atomica (Lua), SETNX leader election |
| Pydantic | 2.12.5 | Validazione + serializzazione | `ConfigDict`, `field_validator`, composizione settings via MRO |
| structlog | latest | Logging strutturato | Output JSON con filtraggio PII automatico, eventi snake_case |
| sentence-transformers | 5.0+ | Embeddings locali | E5-small multilingue (384d), zero costo API, ~50 ms su ARM64 |
| Playwright | latest | Browser automation | Chromium headless, CDP accessibility tree, cross-platform |
| APScheduler | 3.x | Background job | Trigger cron/interval, compatibile con leader election Redis |

### 2.2. Frontend

| Tecnologia | Versione | Ruolo |
|------------|----------|-------|
| Next.js | 16.1.7 | App Router, SSR, ISR |
| React | 19.2.4 | UI con Server Components |
| TypeScript | 5.9.3 | Tipizzazione strict |
| TailwindCSS | 4.2.1 | Utility-first CSS |
| TanStack Query | 5.90 | Server state management, cache, mutation |
| Radix UI | v2 | Primitive UI accessibili |
| react-i18next | 16.5 | i18n (6 lingue), namespace-based |
| Zod | 3.x | Validazione runtime degli schemi debug |

### 2.3. LLM Provider supportati

| Provider | Modelli | Specificità |
|----------|---------|-------------|
| OpenAI | GPT-5.4, GPT-5.4-mini, GPT-5.x, GPT-4.1-x, o1, o3-mini | Prompt caching nativo, Responses API, reasoning_effort |
| Anthropic | Claude Opus 4.6/4.5/4, Sonnet 4.6/4.5/4, Haiku 4.5 | Extended thinking, prompt caching |
| Google | Gemini 3.1/3/2.5 Pro, Flash 3/2.5/2.0 | Multimodale, TTS HD |
| DeepSeek | V3 (chat), R1 (reasoner) | Costo ridotto, reasoning nativo |
| Perplexity | sonar-small/large-128k-online | Search-augmented generation |
| Qwen | qwen3-max, qwen3.5-plus, qwen3.5-flash | Thinking mode, tools + vision (Alibaba Cloud) |
| Ollama | Qualsiasi modello locale (scoperta dinamica) | Zero costo API, auto-ospitato |

**Perché 7 provider?** La scelta non è la collezione fine a sé stessa. È una strategia di resilienza: ogni nodo della pipeline può essere assegnato a un provider diverso. Se OpenAI aumenta le tariffe, il router passa a DeepSeek. Se Anthropic ha un'interruzione, la risposta viene dirottata su Gemini. L'astrazione LLM (`src/infrastructure/llm/factory.py`) utilizza il pattern Factory con `init_chat_model()`, sovrascritto da adattatori specifici (`ResponsesLLM` per l'API Responses di OpenAI, eleggibilità tramite regex `^(gpt-4\.1|gpt-5|o[1-9])`).

---

## 3. Architettura backend: Domain-Driven Design

### 3.1. Struttura dei domini

```
apps/api/src/
├── core/                         # Nucleo tecnico trasversale
│   ├── config/                   # 9 moduli Pydantic BaseSettings composti via MRO
│   │   ├── __init__.py           # Classe Settings (MRO finale)
│   │   ├── agents.py, database.py, llm.py, mcp.py, voice.py, usage_limits.py, ...
│   ├── constants.py              # 1 000+ costanti centralizzate
│   ├── exceptions.py             # Eccezioni centralizzate (raise_user_not_found, ecc.)
│   └── i18n.py                   # Bridge i18n → settings
│
├── domains/                      # Bounded Context (DDD)
│   ├── agents/                   # DOMINIO PRINCIPALE — orchestrazione LangGraph
│   │   ├── nodes/                # 7+ nodi del grafo
│   │   ├── services/             # Smart Services, HITL, context resolution
│   │   ├── tools/                # Strumenti per dominio (@tool + ToolResponse)
│   │   ├── orchestration/        # ExecutionPlan, parallel executor, validator
│   │   ├── registry/             # AgentRegistry, domain_taxonomy, catalogue
│   │   ├── semantic/             # Semantic router, expansion service
│   │   ├── middleware/           # Memory injection, personality injection
│   │   ├── prompts/v1/           # 57 file .txt di prompt versionati
│   │   ├── graphs/               # 15 builder di agenti (uno per dominio)
│   │   ├── context/              # Context store (Data Registry), decorator
│   │   └── models.py             # MessagesState (TypedDict + custom reducer)
│   ├── auth/                     # OAuth 2.1, sessioni BFF, RBAC
│   ├── connectors/               # Astrazione multi-provider (Google/Apple/Microsoft)
│   ├── rag_spaces/               # Upload, chunking, embedding, retrieval ibrido
│   ├── journals/                 # Diari di bordo introspettivi
│   ├── interests/                # Apprendimento dei centri di interesse
│   ├── heartbeat/                # Notifiche proattive LLM-driven
│   ├── channels/                 # Multi-canale (Telegram)
│   ├── voice/                    # TTS Factory, STT Sherpa, Wake Word
│   ├── skills/                   # Standard agentskills.io
│   ├── sub_agents/               # Agenti specializzati persistenti
│   ├── usage_limits/             # Quote per utente (5-layer defence)
│   └── ...                       # conversations, reminders, scheduled_actions, users, user_mcp
│
└── infrastructure/               # Livello trasversale
    ├── llm/                      # Factory, provider, adapter, embeddings, tracking
    ├── cache/                    # Redis sessions, LLM cache, JSON helper
    ├── mcp/                      # MCP client pool, auth, SSRF, tool adapter, Excalidraw
    ├── browser/                  # Playwright session pool, CDP, anti-rilevamento
    ├── rate_limiting/            # Redis sliding window distribuito
    ├── scheduler/                # APScheduler, leader election, lock
    └── observability/            # 17+ file di metriche Prometheus, tracing OTel
```

### 3.2. Catena di priorità della configurazione

Un invariante fondamentale attraversa l'intero backend. È stato sistematicamente applicato nella v1.9.4 con ~291 correzioni su ~80 file, poiché le divergenze tra costanti e configurazione reale di produzione causavano bug silenti:

```
APPLICATION (Admin UI / DB) > .ENV (settings) > CONSTANT (fallback)
```

**Perché questa catena?** Le costanti (`src/core/constants.py`) servono esclusivamente come fallback per i `Field(default=...)` Pydantic e i `server_default=` SQLAlchemy. Un amministratore che modifica un modello LLM dall'interfaccia deve vedere il cambiamento applicato immediatamente, senza ridistribuzione. A runtime, tutto il codice legge `settings.field_name`, mai direttamente una costante.

### 3.3. Pattern dei livelli

| Livello | Responsabilità | Pattern chiave |
|---------|---------------|-------------|
| **Router** | Validazione HTTP, auth, serializzazione | `Depends(get_current_active_session)`, `check_resource_ownership()` |
| **Service** | Logica di business, orchestrazione | Il costruttore riceve `AsyncSession`, crea repository, eccezioni centralizzate |
| **Repository** | Accesso dati | Eredita `BaseRepository[T]`, paginazione `tuple[list[T], int]` |
| **Model** | Schema DB | `Mapped[Type]` + `mapped_column()`, `UUIDMixin`, `TimestampMixin` |
| **Schema** | Validazione I/O | Pydantic v2, `Field()` con descrizione, request/response separati |

---

## 4. LangGraph: orchestrazione multi-agente

### 4.1. Perché LangGraph? (ADR-001)

La scelta di LangGraph piuttosto che LangChain da solo, CrewAI o AutoGen si basa su tre requisiti non negoziabili:

1. **State persistence**: `TypedDict` con reducer custom, persistito tramite checkpoint PostgreSQL — permette di riprendere una conversazione dopo un'interruzione HITL
2. **Cicli e interrupt**: supporto nativo dei loop (rifiuto HITL → ri-pianificazione) e del pattern `interrupt()` — senza il quale il HITL a 6 livelli sarebbe impossibile
3. **Streaming SSE**: integrazione nativa con callback handler — critica per l'UX in tempo reale

CrewAI e AutoGen erano più semplici da apprendere, ma nessuno dei due supportava il pattern interrupt/resume necessario per il HITL a livello di piano. Questa scelta ha un costo: la curva di apprendimento è più ripida (concetti di grafi, edge condizionali, state schema).

### 4.2. Il grafo principale

```
                    ┌──────────────────────────────────┐
                    │        Router Node (v3)            │
                    │  Binario : conversation|actionable  │
                    │  Confiance : high > 0.85            │
                    └──────┬──────────┬─────────────────┘
                           │          │
              conversation │          │ actionable
                           │          │
                    ┌──────▼──┐  ┌───▼───────────────────┐
                    │ Response │  │  QueryAnalyzer          │
                    │  Node    │  │  + SmartPlanner          │
                    └──────────┘  └───┬───────────────────┘
                                      │
                                ┌─────▼───────────────────┐
                                │  Semantic Validator       │
                                └─────┬───────────────────┘
                                      │
                                ┌─────▼───────────────────┐
                                │   Approval Gate           │
                                │   (HITL interrupt)        │
                                └─────┬───────────────────┘
                                      │
                                ┌─────▼───────────────────┐
                                │  Task Orchestrator        │
                                │  (parallel executor)      │
                                └─────┬───────────────────┘
                                      │
                    ┌─────────────────▼────────────────────┐
                    │      15 Domain Agents                  │
                    │  + MCP dynamic agents                  │
                    │  + Sub-agent delegation                │
                    └─────────────────┬────────────────────┘
                                      │
                                ┌─────▼───────────────────┐
                                │   Response Node           │
                                │  (anti-hallucination)     │
                                └───────────────────────────┘
```

### 4.3. Nodi del grafo

| Nodo | File | Ruolo | Windowing |
|------|------|-------|-----------|
| Router v3 | `router_node_v3.py` | Classificazione binaria conversation/actionable | 5 turn |
| QueryAnalyzer | `query_analyzer_service.py` | Rilevamento dei domini, estrazione di intent | — |
| Planner v3 | `planner_node_v3.py` | Generazione ExecutionPlan DSL | 10 turn |
| Semantic Validator | `semantic_validator.py` | Validazione delle dipendenze e coerenza | — |
| Approval Gate | `hitl_dispatch_node.py` | HITL interrupt(), 6 livelli di approvazione | — |
| Task Orchestrator | `task_orchestrator_node.py` | Esecuzione parallela, passaggio di contesto | — |
| Response | `response_node.py` | Sintesi anti-allucinazione, 3 livelli di guardia | 20 turn |

### 4.4. AgentRegistry e Domain Taxonomy

L'`AgentRegistry` centralizza la registrazione degli agenti (`registry.register_agent()` in `main.py`), il catalogo dei `ToolManifest` e la `domain_taxonomy.py` che definisce ogni dominio con il suo `result_key` e i relativi alias.

**Perché un registro centralizzato?** Senza di esso, l'aggiunta di un agente richiedeva la modifica di 5+ file. Con il registro, un nuovo agente si dichiara in un singolo punto ed è automaticamente disponibile per il routing, la pianificazione e l'esecuzione.

### 4.5. Domain Taxonomy

Ogni dominio è un `DomainConfig` dichiarativo: nome, agenti, `result_key` (chiave canonica per i riferimenti `$steps`), `related_domains`, priorità e instradabilità. Il `DOMAIN_REGISTRY` è l'unica fonte di verità consumata da tre sottosistemi: SmartCatalogue (filtraggio), espansione semantica (domini adiacenti) e fase Initiative (pre-filtro strutturale).

### 4.6. Tool Manifests

Ogni tool dichiara un `ToolManifest` tramite un `ToolManifestBuilder` fluido: parametri, output, profilo di costo, permessi e `semantic_keywords` multilingue per il routing. I manifesti sono consumati dal planner (iniezione catalogo), dal router semantico (matching per parole chiave) e dall'agent builder (cablaggio dei tool). Vedi sezione 23 per l'architettura completa dei tool.

---

## 5. La pipeline di esecuzione conversazionale

### 5.1. Flusso dettagliato di una richiesta azionabile

1. **Ricezione**: Messaggio utente → endpoint SSE `/api/v1/chat/stream`
2. **Contesto**: `request_tool_manifests_ctx` ContextVar costruito una volta (ADR-061: 3-layer defence)
3. **Router**: Classificazione binaria con scoring di confidenza (high > 0.85, medium > 0.65)
4. **QueryAnalyzer**: Identifica i domini tramite LLM + validazione post-espansione (gate-keeper che filtra i domini disattivati)
5. **SmartPlanner**: Genera un `ExecutionPlan` (DSL JSON strutturato)
   - Pattern Learning: consulta la cache bayesiana (bypass se confidenza > 90%)
   - Skill detection: le Skill deterministiche sono protette tramite `_has_potential_skill_match()`
6. **Semantic Validator**: Verifica la coerenza delle dipendenze inter-step
7. **HITL Dispatch**: Classifica il livello di approvazione, `interrupt()` se necessario
8. **Task Orchestrator**: Esegue gli step in ondate parallele tramite `asyncio.gather()`
   - Filtra gli step skipped PRIMA del gather (ADR-005 — corregge un bug di doppia esecuzione plan+fallback)
   - Passaggio di contesto tramite Data Registry (InMemoryStore)
   - Pattern FOR_EACH per iterazioni di massa
9. **Response Node**: Sintetizza i risultati, iniezione memoria + diari + RAG
10. **SSE Stream**: Token per token verso il frontend
11. **Background task** (fire-and-forget): estrazione memoria, estrazione diario, rilevamento interessi

### 5.2. ContextVar: propagazione implicita dello stato

Un meccanismo critico è l'utilizzo dei `ContextVar` Python per propagare lo stato senza parameter threading:

| ContextVar | Ruolo | Perché |
|------------|-------|--------|
| `current_tracker` | TrackingContext per il tracciamento token LLM | Evita di passare un tracker attraverso 15 livelli di funzioni |
| `request_tool_manifests_ctx` | Manifesti degli strumenti filtrati per richiesta | Costruito una volta, letto da 7+ consumatori (elimina duplicazione ADR-061) |

Questo approccio mantiene un isolamento per richiesta in un contesto asyncio senza inquinare le firme delle funzioni.

---

## 6. Il sistema di pianificazione (ExecutionPlan DSL)

### 6.1. Struttura del piano

```python
ExecutionPlan(
    steps=[
        ExecutionStep(
            step_id="get_meetings",
            tool_name="get_events",
            parameters={"date": "tomorrow"},
            dependencies=[]
        ),
        ExecutionStep(
            step_id="send_reminders",
            tool_name="send_email",
            parameters={"subject": "Rappel réunion"},
            dependencies=["get_meetings"],
            for_each="$steps.get_meetings.events",
            for_each_max=10
        )
    ]
)
```

### 6.2. Pattern FOR_EACH

**Perché un pattern dedicato?** Le operazioni di massa (inviare un'email a 12 contatti) non possono essere pianificate come 12 step statici — il numero di elementi è sconosciuto prima dell'esecuzione dello step precedente. Il FOR_EACH risolve questo problema con le seguenti salvaguardie:
- Soglia HITL: qualsiasi mutazione >= 1 elemento attiva un'approvazione obbligatoria
- Limite configurabile: `for_each_max` previene esecuzioni non delimitate
- Riferimento dinamico: `$steps.{step_id}.{field}` per i risultati degli step precedenti

### 6.3. Esecuzione parallela a ondate

Il `parallel_executor.py` organizza gli step in ondate (DAG):
1. Identifica gli step senza dipendenze non risolte → ondata successiva
2. Filtra gli step skipped (condizioni non soddisfatte, branch fallback) — **prima** di `asyncio.gather()`, non dopo (ADR-005: corregge un bug che causava 2x chiamate API e 2x costi)
3. Esegue l'ondata con isolamento degli errori per step
4. Alimenta il Data Registry con i risultati
5. Ripete fino al completamento del piano

### 6.4. Validatore Semantico

Prima dell'approvazione HITL, un LLM dedicato (distinto dal planner, per evitare il bias di autovalidazione) ispeziona il piano secondo 14 tipi di anomalie in quattro categorie: **Critico** (capacità allucinata, dipendenza fantasma, ciclo logico), **Semantico** (disallineamento di cardinalità, overflow/underflow di scope, parametri errati), **Sicurezza** (ambiguità pericolosa, assunzione implicita) e **FOR_EACH** (cardinalità mancante, riferimento invalido). Cortocircuito per piani banali (1 step), timeout ottimistico di 1 s.

### 6.5. Validazione dei Riferimenti

I riferimenti tra step (`$steps.get_meetings.events[0].title`) vengono validati al momento della pianificazione con messaggi di errore strutturati: campo invalido, alternative disponibili ed esempi corretti — permettendo al planner di autocorreggersi nel retry invece di produrre fallimenti silenziosi.

### 6.6. Re-Planner Adattivo (Panic Mode)

In caso di fallimento dell'esecuzione, un analizzatore rule-based (senza LLM) classifica il pattern di fallimento (risultati vuoti, fallimento parziale, timeout, errore di riferimento) e seleziona una strategia di recovery: retry identico, replan con scope ampliato, escalation all'utente o abort. In **Panic Mode**, il SmartCatalogue si espande per includere tutti i tool in un unico retry — risolvendo i casi in cui il filtraggio per dominio era troppo aggressivo.

---

## 7. Smart Services: ottimizzazione intelligente

### 7.1. Il problema risolto

Senza ottimizzazione, lo scaling a 10+ domini faceva esplodere i costi: passare da 3 strumenti (contatti) a 30+ strumenti (10 domini) moltiplicava per 10 la dimensione del prompt e quindi il costo per richiesta (ADR-003). Gli Smart Services sono stati concepiti per riportare questo costo al livello di un sistema mono-dominio.

| Servizio | Ruolo | Meccanismo | Guadagno misurato |
|----------|-------|-----------|-------------------|
| `QueryAnalyzerService` | Decisione di routing | Cache LRU (TTL 5 min) | ~35% cache hit |
| `SmartPlannerService` | Generazione di piani | Pattern Learning bayesiano | Bypass > 90% confidenza |
| `SmartCatalogueService` | Filtraggio strumenti | Filtraggio per dominio | 96% riduzione token |
| `PlanPatternLearner` | Apprendimento | Scoring bayesiano Beta(2,1) | ~2 300 token evitati per replan |

### 7.2. PlanPatternLearner

**Funzionamento**: Quando un piano è validato ed eseguito con successo, la sua sequenza di strumenti viene registrata in Redis (hash `plan:patterns:{tool→tool}`, TTL 30 giorni). Per le richieste future, viene calcolato un punteggio bayesiano: `confidenza = (α + successi) / (α + β + successi + fallimenti)`. Al di sopra del 90%, il piano viene riutilizzato direttamente senza chiamata LLM.

**Salvaguardie**: K-anonimato (minimo 3 osservazioni per suggerimento, 10 per bypass), matching esatto dei domini, massimo 3 pattern iniettati (~45 token di overhead), timeout rigoroso di 5 ms.

**Inizializzazione**: 50+ golden pattern predefiniti all'avvio, ciascuno con 20 successi simulati (= 95,7% di confidenza iniziale).

### 7.3. QueryIntelligence

Il QueryAnalyzer produce molto più della rilevazione di domini — genera una struttura `QueryIntelligence` profonda: intento immediato vs obiettivo finale (`UserGoal`: FIND_INFORMATION, TAKE_ACTION, COMMUNICATE...), intenti impliciti (es: "trovare contatto" probabilmente significa "inviare qualcosa"), strategie di fallback anticipate, indizi di cardinalità FOR_EACH e punteggi di confidenza per dominio calibrati con softmax. Questo dà al planner una visione più ricca della semplice estrazione di parole chiave.

### 7.4. Pivot Semantico

Le query in qualsiasi lingua vengono automaticamente tradotte in inglese prima del confronto di embedding, migliorando la precisione cross-linguistica. Cache Redis (TTL 5 min, ~5 ms in hit vs ~500 ms in miss), tramite un LLM veloce.

---

## 8. Routing semantico ed embeddings locali

### 8.1. Perché embeddings locali? (ADR-049)

Il routing puramente LLM presentava due problemi: costo (ogni richiesta = una chiamata LLM) e precisione (il LLM si sbagliava sui domini nel ~20% dei casi multi-dominio). Gli embeddings locali risolvono entrambi:

| Proprietà | Valore |
|-----------|--------|
| Modello | multilingual-e5-small |
| Dimensioni | 384 |
| Latenza | ~50 ms (ARM64 Pi 5) |
| Costo API | Zero |
| Lingue | 100+ |
| Guadagno precisione | +48% su Q/A matching vs routing LLM da solo |

### 8.2. Semantic Tool Router (ADR-048)

Ogni `ToolManifest` possiede dei `semantic_keywords` multilingue. La richiesta viene trasformata in embedding, poi confrontata per similarità coseno con **max-pooling** (punteggio = MAX per strumento, non media — evita la diluizione semantica). Doppia soglia: >= 0.70 = alta confidenza, 0.60-0.70 = incertezza.

### 8.3. Semantic Expansion

L'`expansion_service.py` arricchisce i risultati esplorando i domini adiacenti. La validazione post-espansione (ADR-061, Layer 1) filtra i domini disattivati dall'amministratore — correggendo un bug in cui il LLM o l'espansione potevano reintrodurre domini che erano stati disattivati.

---

## 9. Human-in-the-Loop: architettura a 6 livelli

### 9.1. Perché a livello di piano? (Fase 7 → Fase 8)

L'approccio iniziale (Fase 7) interrompeva l'esecuzione **durante** le chiamate degli strumenti — ogni strumento sensibile generava un'interruzione. L'UX era mediocre (pause inattese) e il costo elevato (overhead per strumento).

La Fase 8 (attuale) sottopone il **piano completo** all'utente **prima** di qualsiasi esecuzione. Una singola interruzione, una visione globale, la possibilità di modificare i parametri. Il compromesso: bisogna fidarsi del pianificatore per produrre un piano fedele.

### 9.2. I 6 tipi di approvazione

| Tipo | Trigger | Meccanismo |
|------|---------|-----------|
| `PLAN_APPROVAL` | Azioni distruttive | `interrupt()` con PlanSummary |
| `CLARIFICATION` | Ambiguità rilevata | `interrupt()` con domanda LLM |
| `DRAFT_CRITIQUE` | Bozza email/evento/contatto | `interrupt()` con bozza serializzata + template markdown |
| `DESTRUCTIVE_CONFIRM` | Eliminazione >= 3 elementi | `interrupt()` con avviso di irreversibilità |
| `FOR_EACH_CONFIRM` | Mutazioni di massa | `interrupt()` con conteggio operazioni |
| `MODIFIER_REVIEW` | Modifiche IA suggerite | `interrupt()` con confronto before/after |

### 9.3. Draft Critique arricchito

Per le bozze, un prompt dedicato genera una critica strutturata con template markdown per dominio, emoji dei campi, confronto before/after con strikethrough per gli aggiornamenti e avvisi di irreversibilità. I risultati post-HITL mostrano label i18n e link cliccabili.

### 9.4. Classificazione delle Risposte

Quando l'utente risponde a un prompt di approvazione, un classificatore full-LLM (non regex) categorizza la risposta in 5 decisioni: **APPROVE**, **REJECT**, **EDIT** (stessa azione, parametri diversi), **REPLAN** (azione completamente diversa) o **AMBIGUOUS**. Una logica di degradazione previene i falsi positivi: un EDIT con parametri mancanti viene degradato ad AMBIGUOUS, attivando una richiesta di chiarimento.

### 9.5. Compaction Safety

4 condizioni impediscono la compaction LLM (riassunto dei messaggi precedenti) durante i flussi di approvazione attivi. Senza questa protezione, un riassunto potrebbe eliminare il contesto critico di un'interruzione in corso.

---

## 10. Gestione dello state e message windowing

### 10.1. MessagesState e reducer custom

Lo state LangGraph è un `TypedDict` con un reducer `add_messages_with_truncate` che gestisce il truncation basato sui token, la validazione delle sequenze di messaggi OpenAI e la deduplicazione dei messaggi tool.

### 10.2. Perché il windowing per nodo? (ADR-007)

**Il problema**: una conversazione di 50+ messaggi generava 100k+ token di contesto, con una latenza > 10 s per il router e un'esplosione dei costi.

**La soluzione**: ogni nodo opera su una finestra diversa, calibrata sul suo reale fabbisogno:

| Nodo | Turn | Giustificazione |
|------|------|-----------------|
| Router | 5 | Decisione rapida, contesto minimo sufficiente |
| Planner | 10 | Necessità di contesto per pianificare, ma non dell'intero storico |
| Response | 20 | Contesto ricco per una sintesi naturale |

**Impatto misurato**: latenza E2E -50% (10 s → 5 s), costo -77% sulle conversazioni lunghe, qualità preservata grazie al Data Registry che memorizza i risultati degli strumenti indipendentemente dai messaggi.

### 10.3. Context Compaction

Quando il numero di token supera una soglia dinamica (rapporto della context window del modello di risposta), viene generato un riassunto LLM. Gli identificatori critici (UUID, URL, email) vengono preservati. Rapporto di risparmio: ~60% per compaction. Comando `/resume` per attivazione manuale.

### 10.4. Checkpointing PostgreSQL

State completo sottoposto a checkpoint dopo ogni nodo. P95 save < 50 ms, P95 load < 100 ms, dimensione media ~15 KB/conversazione.

---

## 11. Sistema di memoria e profilo psicologico

### 11.1. Architettura

```
AsyncPostgresStore + Semantic Index (pgvector)
├── Namespace: (user_id, "memories")        → Profilo psicologico
├── Namespace: (user_id, "documents", src)  → RAG documentale
└── Namespace: (user_id, "context", domain) → Contesto strumenti (Data Registry)
```

### 11.2. Schema di memoria arricchito

Ogni ricordo è un documento strutturato con:
- `content`, `category` (preferenza, fatto, personalità, relazione, sensibilità...)
- `importance` (1-10), `emotional_weight` (da -10 a +10)
- `usage_nuance`: come utilizzare questa informazione in modo empatico
- Embedding `text-embedding-3-small` (1536d) via pgvector HNSW

**Perché un peso emotivo?** Un assistente che sa che vostra madre è malata ma tratta questo fatto come un qualsiasi dato è nel migliore dei casi maldestro, nel peggiore offensivo. Il peso emotivo consente di attivare la `DANGER_DIRECTIVE` (divieto di scherzare, minimizzare, confrontare, banalizzare) quando viene toccato un argomento sensibile.

### 11.3. Estrazione e iniezione

**Estrazione**: dopo ogni conversazione, un processo in background analizza l'ultimo messaggio dell'utente, adattato alla personalità attiva. Costo tracciato tramite `TrackingContext`.

**Iniezione**: il middleware `memory_injection.py` ricerca le memorie semanticamente vicine, costruisce il profilo psicologico iniettabile e attiva la `DANGER_DIRECTIVE` se necessario. Iniezione nel prompt di sistema del Response Node.

### 11.4. Ricerca ibrida BM25 + semantica

Combinazione con alpha configurabile (default 0.6 semantica / 0.4 BM25). Boost del 10% quando entrambi i segnali sono forti (> 0.5). Fallback grazioso verso semantica sola se BM25 fallisce. Performance: 40-90 ms con cache.

### 11.5. Diari di bordo (Journals)

L'assistente tiene riflessioni introspettive su quattro temi (auto-riflessione, osservazioni sull'utente, idee/analisi, apprendimenti). Due trigger: estrazione post-conversazione + consolidamento periodico (4h). Embeddings OpenAI 1536d con `search_hints` (parole chiave LLM nel vocabolario dell'utente). Iniezione nel prompt del **Response Node e del Planner Node** — quest'ultimo utilizza `intelligence.original_query` come query semantica.

Anti-allucinazione UUID: `field_validator`, tabella di riferimento ID, filtraggio per ID noti nell'estrazione e nel consolidamento.

### 11.6. Sistema di interessi

Rilevamento tramite analisi delle richieste con evoluzione bayesiana dei pesi (decay 0.01/giorno). Notifiche proattive multi-sorgente (Wikipedia, Perplexity, LLM). Feedback utente (thumbs up/down/block) regola i pesi.

---

## 12. Infrastruttura LLM multi-provider

### 12.1. Factory Pattern

```python
llm = get_llm(provider="openai", model="gpt-5.4", temperature=0.7, streaming=True)
```

Il `get_llm()` risolve la configurazione effettiva tramite `get_llm_config_for_agent(settings, agent_type)` (code defaults → DB admin overrides), istanzia il modello e applica gli adattatori specifici.

### 12.2. 34 tipi di configurazione LLM

Ogni nodo della pipeline è configurabile indipendentemente tramite l'Admin UI — senza ridistribuzione:

| Categoria | Tipi configurabili |
|-----------|-------------------|
| Pipeline | router, query_analyzer, planner, semantic_validator, context_resolver |
| Risposta | response, hitl_question_generator |
| Background | memory_extraction, interest_extraction, journal_extraction, journal_consolidation |
| Agenti | contacts_agent, emails_agent, calendar_agent, browser_agent, ecc. |

### 12.3. Token Tracking

Il `TrackingContext` traccia ogni chiamata LLM con `call_type` ("chat"/"embedding"), `sequence` (contatore monotono), `duration_ms`, token (input/output/cache) e costo calcolato dalle tariffe DB. I tracker condividono un `run_id` per l'aggregazione. Il debug panel mostra tutte le invocazioni (pipeline + background task) in una vista unificata cronologica.

---

## 13. Connettori: astrazione multi-fornitore

### 13.1. Architettura a protocolli

```
ConnectorTool (base.py) → ClientRegistry → resolve_client(type) → Protocol
     ├── GoogleGmailClient       implements EmailClientProtocol
     ├── MicrosoftOutlookClient  implements EmailClientProtocol
     ├── AppleEmailClient        implements EmailClientProtocol
     └── PhilipsHueClient        implements SmartHomeClientProtocol
```

**Perché i protocol Python?** Il duck typing strutturale permette di aggiungere un nuovo provider senza modificare il codice chiamante. Il `ProviderResolver` garantisce che un solo fornitore sia attivo per categoria funzionale.

### 13.2. Normalizer

Ogni provider restituisce dati nel proprio formato. Normalizer dedicati (`calendar_normalizer`, `contacts_normalizer`, `email_normalizer`, `tasks_normalizer`) convertono le risposte specifiche di ogni provider in modelli di dominio unificati. Aggiungere un nuovo provider richiede solo l'implementazione del protocollo e del suo normalizer — il codice chiamante rimane invariato.

### 13.3. Pattern riutilizzabili

`BaseOAuthClient` (template method con 3 hook), `BaseGoogleClient` (paginazione tramite pageToken), `BaseMicrosoftClient` (OData). Circuit breaker, rate limiting Redis distribuito, refresh token con double-check pattern e Redis locking contro il thundering herd.

---

## 14. MCP: Model Context Protocol

### 14.1. Architettura

Il `MCPClientManager` gestisce il lifecycle delle connessioni (exit stack), la scoperta degli strumenti (`session.list_tools()`), e la generazione automatica della descrizione di dominio tramite LLM. Il `ToolAdapter` normalizza gli strumenti MCP verso il formato LangChain `@tool`, con parsing strutturato delle risposte JSON in item individuali.

### 14.2. Sicurezza MCP

HTTPS obbligatorio, prevenzione SSRF (risoluzione DNS + blocklist IP), crittografia Fernet delle credenziali, OAuth 2.1 (DCR + PKCE S256), rate limiting Redis per server/strumento, API guard 403 sugli endpoint proxy per server disattivati (ADR-061 Layer 3).

### 14.3. MCP Iterative Mode (ReAct)

I server MCP con `iterative_mode: true` utilizzano un agente ReAct dedicato (ciclo observe/think/act) al posto del planner statico. L'agente legge prima la documentazione del server, comprende il formato atteso, poi chiama gli strumenti con i parametri corretti. Particolarmente efficace per i server con API complesse (es.: Excalidraw). Attivabile per server nella configurazione admin o utente. Alimentato dal `ReactSubAgentRunner` generico (condiviso con il browser agent).

---

## 15. Sistema vocale (STT/TTS)

### 15.1. STT

Wake word ("OK Guy") tramite Sherpa-onnx WASM nel browser (zero invio esterno). Trascrizione Whisper Small (99+ lingue, offline) lato backend tramite ThreadPoolExecutor. Lingua STT per utente con cache thread-safe di `OfflineRecognizer` per lingua.

**Ottimizzazioni latenza**: riutilizzo del flusso microfono KWS → registrazione (~200-800 ms risparmiati), pre-connessione WebSocket, `getUserMedia` + WS parallelizzati tramite `Promise.allSettled`, cache Worklet AudioWorklet.

### 15.2. TTS

Factory pattern: `TTSFactory.create(mode)` con fallback automatico HD → Standard. Standard = Edge TTS (gratuito), HD = OpenAI TTS o Gemini TTS (premium).

---

## 16. Proattività: Heartbeat e azioni pianificate

### 16.1. Heartbeat: architettura in 2 fasi

**Fase 1 — Decisione** (costo-efficiente, gpt-4.1-mini):
1. `EligibilityChecker`: opt-in, finestra oraria, cooldown (2h globale, 30 min per tipo), attività recente
2. `ContextAggregator`: 7 sorgenti in parallelo (`asyncio.gather`): Calendar, Weather (rilevamento cambiamenti), Tasks, Emails, Interests, Memories, Journals
3. LLM structured output: `skip` | `notify` con anti-ridondanza (storico recente iniettato)

**Fase 2 — Generazione** (se notify): LLM riscrive con personalità + lingua utente. Dispatch multi-canale.

### 16.2. Agent Initiative (ADR-062)

Nodo LangGraph post-esecuzione: dopo ogni turno azionabile, l'iniziativa analizza i risultati e verifica proattivamente le informazioni cross-domain (read-only). Esempi: meteo pioggia → verificare calendario per attività outdoor, email che menziona un appuntamento → verificare disponibilità, scadenza task → ricordare il contesto. 100% prompt-driven (nessuna logica hardcoded), pre-filtro strutturale (domini adiacenti), iniezione memoria + centri di interesse, campo suggestion per proporre azioni write. Configurabile tramite `INITIATIVE_ENABLED`, `INITIATIVE_MAX_ITERATIONS`, `INITIATIVE_MAX_ACTIONS`.

### 16.3. Azioni pianificate

APScheduler con leader election Redis (SETNX, TTL 120s, recheck 5s). `FOR UPDATE SKIP LOCKED` per isolamento. Auto-approvazione dei piani (`plan_approved=True` iniettato nello state). Auto-disattivazione dopo 5 fallimenti consecutivi. Retry su errori transitori.

---

## 17. RAG Spaces e ricerca ibrida

### 17.1. Pipeline

Upload → Chunking → Embedding (text-embedding-3-small, 1536d) → pgvector HNSW → Ricerca ibrida (cosine + BM25 con alpha fusion) → Iniezione contesto nel **Response Node**.

Nota: l'iniezione RAG avviene nel nodo di risposta, non nel pianificatore. Il planner riceve invece l'iniezione dei diari personali tramite `build_journal_context()`.

### 17.2. System RAG Spaces (ADR-058)

FAQ integrata (119+ Q/A, 17 sezioni) indicizzata da `docs/knowledge/`. Rilevamento `is_app_help_query` da QueryAnalyzer, Rule 0 override in RoutingDecider, App Identity Prompt (~200 token, lazy loading). Rilevamento obsolescenza SHA-256, auto-indicizzazione all'avvio.

---

## 18. Browser Control e Web Fetch

### 18.1. Web Fetch

URL → validazione SSRF (DNS + IP blocklist + post-redirect recheck) → estrazione readability (fallback full page) → HTML cleaning → Markdown → wrapping `<external_content>` (prevenzione prompt injection). Cache Redis 10 min.

### 18.2. Browser Control (ADR-059)

Agente ReAct autonomo (Playwright Chromium headless). Session pool Redis-backed con recovery cross-worker. CDP accessibility tree per interazione tramite elementi. Anti-rilevamento (Chrome UA, rimozione flag webdriver, locale/timezone dinamici). Cookie banner auto-dismiss (20+ selettori multilingue). Rate limiting separato read/write (40 ciascuno per sessione).

---

## 19. Sicurezza: defence in depth

### 19.1. Autenticazione BFF (ADR-002)

**Perché BFF piuttosto che JWT?** JWT in localStorage = vulnerabile XSS, overhead del 90% sulla dimensione, revoca impossibile. Il pattern BFF con cookie HTTP-only + sessioni Redis elimina questi tre problemi. Migrazione v0.3.0: memoria -90% (1.2 MB → 120 KB), session lookup P95 < 5 ms, punteggio OWASP B+ → A.

### 19.2. Usage Limits: 5-layer defence in depth

| Livello | Punto di intercettazione | Perché questo livello |
|---------|-------------------------|----------------------|
| Layer 0 | Chat router (HTTP 429) | Bloccare prima ancora dello stream SSE |
| Layer 1 | Agent service (SSE error) | Coprire le scheduled action che bypassano il router |
| Layer 2 | `invoke_with_instrumentation()` | Guard centralizzato che copre tutti i servizi in background |
| Layer 3 | Proactive runner | Skip per utenti bloccati |
| Layer 4 | Migrazione `.ainvoke()` diretta | Copertura delle chiamate non centralizzate |

Design **fail-open**: i fallimenti dell'infrastruttura non bloccano gli utenti.

### 19.3. Prevenzione degli attacchi

| Vettore | Protezione |
|---------|------------|
| XSS | Cookie HTTP-only, CSP |
| CSRF | SameSite=Lax |
| SQL Injection | SQLAlchemy ORM (query parametrizzate) |
| SSRF | Risoluzione DNS + IP blocklist (Web Fetch, MCP, Browser) |
| Prompt Injection | Marker di sicurezza `<external_content>` |
| Rate Limiting | Redis sliding window distribuito (Lua atomico) |
| Supply Chain | SHA-pinned GitHub Actions, Dependabot settimanale |

---

## 20. Osservabilità e monitoring

### 20.1. Stack

| Tecnologia | Ruolo |
|------------|-------|
| Prometheus | 350+ metriche custom (RED pattern) |
| Grafana | 18 dashboard production-ready |
| Loki | Log strutturati JSON aggregati |
| Tempo | Trace distribuite cross-service (OTLP gRPC) |
| Langfuse | Tracing specifico LLM (versioni prompt, utilizzo token) |
| structlog | Logging strutturato con filtraggio PII |

### 20.2. Debug Panel integrato

Il debug panel nell'interfaccia chat fornisce un'introspezione in tempo reale per conversazione: intent analysis, execution pipeline, LLM pipeline (riconciliazione cronologica di tutte le chiamate LLM + embedding), contesto/memoria, intelligence (cache hit, pattern learning), diari (iniezione + estrazione in background), lifecycle timing.

Le metriche debug persistono in `sessionStorage` (50 voci massime).

**Perché un debug panel nell'UI?** In un ecosistema dove gli agenti IA sono notoriamente difficili da debuggare (comportamento non deterministico, catene di chiamate opache), rendere le metriche accessibili direttamente nell'interfaccia elimina la frizione di dover aprire Grafana o leggere i log. L'operatore vede immediatamente perché una richiesta è costata cara o perché il router ha scelto un determinato dominio.

---

## 21. Performance: ottimizzazioni e metriche

### 21.1. Metriche chiave (P95)

| Metrica | Valore | SLO |
|---------|--------|-----|
| API Latency | 450 ms | < 500 ms |
| TTFT (Time To First Token) | 380 ms | < 500 ms |
| Router Latency | 800 ms | < 2 s |
| Planner Latency | 2.5 s | < 5 s |
| E5 Embedding (locale) | ~50 ms | < 100 ms |
| Checkpoint save | < 50 ms | P95 |
| Redis session lookup | < 5 ms | P95 |

### 21.2. Ottimizzazioni implementate

| Ottimizzazione | Guadagno misurato | Compromesso |
|----------------|-------------------|-------------|
| Message Windowing | -50% latenza, -77% costo | Perdita di contesto precedente (compensata dal Data Registry) |
| Smart Catalogue | 96% riduzione token | Panic mode necessario se filtraggio troppo aggressivo |
| Pattern Learning | 89% risparmi LLM | Inizializzazione richiesta (golden pattern) |
| Prompt Caching | 90% sconto | Dipende dal supporto del provider |
| Local Embeddings | Zero costo API | ~470 MB memoria, 9s caricamento iniziale |
| Parallel Execution | Latenza = max(step) | Complessità di gestione delle dipendenze |
| Context Compaction | ~60% per compaction | Perdita di informazioni (attenuata dalla preservazione degli ID) |

---

## 22. CI/CD e qualità

### 22.1. Pipeline

```
Pre-commit (locale)               GitHub Actions CI
========================          =========================
.bak files check                  Lint Backend (Ruff + Black + MyPy strict)
Secrets grep                      Lint Frontend (ESLint + TypeScript)
Ruff + Black + MyPy               Unit tests + coverage (43 %)
Unit tests rapidi                 Code Hygiene (i18n, Alembic, .env.example)
Rilevamento pattern critici       Docker build smoke test
Sync chiavi i18n                  Secret scan (Gitleaks)
Conflitti migrazione Alembic      ─────────────────────────
Completezza .env.example          Security workflow (settimanale)
ESLint + TypeScript check           CodeQL (Python + JS)
                                    pip-audit + pnpm audit
                                    Trivy filesystem scan
                                    SBOM generation
```

### 22.2. Standard

| Aspetto | Strumento | Configurazione |
|---------|-----------|---------------|
| Formattazione Python | Black | line-length=100 |
| Linting Python | Ruff | E, W, F, I, B, C4, UP |
| Type checking | MyPy | strict mode |
| Commit | Conventional Commits | `feat(scope):`, `fix(scope):` |
| Test | pytest | `asyncio_mode = "auto"` |
| Coverage | 43% minimo | Applicato in CI |

---

## 23. Pattern di ingegneria trasversali

### 23.1. Sistema di Tool: architettura a 5 livelli

Il sistema di tool è costruito in cinque livelli componibili, riducendo il boilerplate per tool da ~150 righe a ~8 righe (riduzione del 94%):

| Livello | Componente | Ruolo |
|---------|-----------|------|
| 1 | `ConnectorTool[ClientType]` | Base generica: OAuth auto-refresh, cache client, dependency injection |
| 2 | `@connector_tool` | Meta-decoratore che compone `@tool` + metriche + rate limiting + salvataggio contesto |
| 3 | Formatter | `ContactFormatter`, `EmailFormatter`... — normalizzazione risultati per dominio |
| 4 | `ToolManifest` + Builder | Dichiarazione dichiarativa: parametri, output, costi, permessi, keyword semantiche |
| 5 | Catalogue Loader | Introspezione dinamica, generazione manifesti, raggruppamento per dominio |

I limiti di frequenza sono per categoria: Read (20/min), Write (5/min), Expensive (2/5 min). I tool possono produrre una stringa (legacy) o un `UnifiedToolOutput` strutturato (modalità Data Registry).

### 23.2. Data Registry

Il Data Registry (`InMemoryStore`) disaccoppia i risultati dei tool dalla cronologia dei messaggi. I risultati vengono memorizzati per richiesta tramite `@auto_save_context` e sopravvivono al windowing dei messaggi — questo è ciò che rende praticabile il windowing aggressivo per nodo (5/10/20 turni) senza perdere il contesto delle uscite dei tool. I riferimenti tra step (`$steps.X.field`) risolvono contro il registry, non contro i messaggi.

### 23.3. Architettura degli Errori

Tutti i tool restituiscono `ToolResponse` (successo) o `ToolErrorModel` (fallimento) con un enum `ToolErrorCode` (18+ tipi: INVALID_INPUT, RATE_LIMIT_EXCEEDED, TEMPLATE_EVALUATION_FAILED...) e un flag `recoverability`. Lato API, raiser di eccezioni centralizzati (`raise_user_not_found`, `raise_permission_denied`...) sostituiscono ovunque le HTTPException grezze — garantendo contratti di errore coerenti.

### 23.4. Sistema di Prompt

57 file `.txt` versionati in `src/domains/agents/prompts/v1/`, caricati tramite `load_prompt()` con cache LRU (32 voci). Versioni configurabili tramite variabili d'ambiente.

### 23.5. Attivazione Centralizzata dei Componenti (ADR-061)

Sistema a 3 livelli che risolve un problema di duplicazione: prima dell'ADR-061, il filtraggio dei componenti attivati/disattivati era disperso in 7+ punti. Ora:

| Livello | Meccanismo |
|---------|-----------|
| Livello 1 | Gate-keeper di dominio: valida i domini LLM contro `available_domains` |
| Livello 2 | `request_tool_manifests_ctx`: ContextVar costruito una volta per richiesta |
| Livello 3 | Guard API 403 sugli endpoint proxy MCP |

### 23.6. Feature Flag

Ogni sottosistema opzionale è controllato da un flag `{FEATURE}_ENABLED`, verificato all'avvio (registrazione scheduler), al cablaggio delle rotte e all'ingresso dei nodi (cortocircuito istantaneo). Questo permette di distribuire il codebase completo attivando progressivamente i sottosistemi.

---

## 24. Architettura delle decisioni (ADR)

59 ADR in formato MADR documentano le decisioni architetturali principali. Alcuni esempi rappresentativi:

| ADR | Decisione | Problema risolto | Impatto misurato |
|-----|-----------|-----------------|-----------------|
| 001 | LangGraph per orchestrazione | Necessità di state persistence + interrupt HITL | Checkpoint P95 < 50 ms |
| 002 | BFF Pattern (JWT → Redis) | JWT vulnerabile XSS, revoca impossibile | Memoria -90%, OWASP A |
| 003 | Filtraggio dinamico per dominio | 10x dimensione prompt = 10x costo | 73-83% riduzione catalogo |
| 005 | Filtraggio PRIMA di asyncio.gather | Plan + fallback eseguiti in parallelo = 2x costo | -50% costo plan fallback |
| 007 | Message Windowing per nodo | Conversazioni lunghe = 100k+ token | -50% latenza, -77% costo |
| 048 | Semantic Tool Router | Routing LLM impreciso su multi-dominio | +48% precisione |
| 049 | Local E5 Embeddings | Costo embeddings API + latenza di rete | Zero costo, 50 ms locale |
| 057 | Personal Journals | Nessuna continuità di riflessione tra sessioni | Iniezione planner + response |
| 061 | Centralized Component Activation | 7+ punti di filtraggio duplicati | Sorgente unica, 3 livelli |

---

## 25. Potenziale di evoluzione ed estensibilità

### 25.1. Punti di estensione

| Estensione | Interfaccia | Documentazione |
|------------|-----------|---------------|
| Nuovo connettore | `OAuthProvider` Protocol + Client Protocol | `GUIDE_CONNECTOR_IMPLEMENTATION.md` + checklist |
| Nuovo agente | `register_agent()` + ToolManifest | `GUIDE_AGENT_CREATION.md` |
| Nuovo strumento | `@tool` + ToolResponse/ToolErrorModel | `GUIDE_TOOL_CREATION.md` |
| Nuovo canale | `BaseChannelSender` + `BaseChannelWebhookHandler` | `NEW_CHANNEL_CHECKLIST.md` |
| Nuovo provider LLM | Adattatore + model profiles | Factory estensibile |
| Nuovo task proattivo | `ProactiveTask` Protocol | `NEW_PROACTIVE_TASK_CHECKLIST.md` |

### 25.2. Scalabilità

| Dimensione | Strategia attuale | Evoluzione possibile |
|------------|-------------------|---------------------|
| Orizzontale | 4 uvicorn worker + leader election Redis | Kubernetes + HPA |
| Dati | PostgreSQL + pgvector | Sharding, read replica |
| Cache | Redis singola istanza | Redis Cluster |
| Osservabilità | Stack completo integrato | Managed Grafana Cloud |

---

## Conclusione

LIA è un esercizio di ingegneria del software che cerca di risolvere un problema concreto: costruire un assistente IA multi-agente di qualità produttiva, trasparente, sicuro ed estensibile, capace di funzionare su un Raspberry Pi.

I 59 ADR documentano non solo le decisioni prese, ma anche le alternative scartate e i compromessi accettati. I 2 300+ test, la CI/CD completa e il MyPy strict non sono metriche di vanità — sono i meccanismi che permettono di far evolvere un sistema di questa complessità senza regressioni.

L'intreccio dei sottosistemi — memoria psicologica, apprendimento bayesiano, routing semantico, HITL sistematico, proattività LLM-driven, diari introspettivi — crea un sistema in cui ogni componente rafforza gli altri. Il HITL alimenta il pattern learning, che riduce i costi, che permettono più funzionalità, che generano più dati per la memoria, che migliora le risposte. È un circolo virtuoso per design, non per caso.

---

*Documento redatto sulla base dell'analisi del codice sorgente (`apps/api/src/`, `apps/web/src/`), della documentazione tecnica (190+ documenti), dei 63 ADR e del changelog (v1.0 a v1.12.0). Tutte le metriche, versioni e pattern citati sono verificabili nel codebase.*
