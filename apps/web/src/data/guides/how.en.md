# LIA — Complete Technical Guide

> Architecture, patterns and engineering decisions of a next-generation multi-agent AI assistant.
>
> Technical presentation documentation for architects, engineers and technical experts.

**Version**: 2.0
**Date**: 2026-03-24
**Application**: LIA v1.11.3
**License**: AGPL-3.0 (Open Source)

---

## Table of Contents

1. [Context and founding choices](#1-context-and-founding-choices)
2. [Technology stack](#2-technology-stack)
3. [Backend architecture: Domain-Driven Design](#3-backend-architecture--domain-driven-design)
4. [LangGraph: multi-agent orchestration](#4-langgraph--multi-agent-orchestration)
5. [The conversational execution pipeline](#5-the-conversational-execution-pipeline)
6. [The planning system (ExecutionPlan DSL)](#6-the-planning-system-executionplan-dsl)
7. [Smart Services: intelligent optimization](#7-smart-services--intelligent-optimization)
8. [Semantic routing and local embeddings](#8-semantic-routing-and-local-embeddings)
9. [Human-in-the-Loop: 6-layer architecture](#9-human-in-the-loop--6-layer-architecture)
10. [State management and message windowing](#10-state-management-and-message-windowing)
11. [Memory system and psychological profile](#11-memory-system-and-psychological-profile)
12. [Multi-provider LLM infrastructure](#12-multi-provider-llm-infrastructure)
13. [Connectors: multi-provider abstraction](#13-connectors--multi-provider-abstraction)
14. [MCP: Model Context Protocol](#14-mcp--model-context-protocol)
15. [Voice system (STT/TTS)](#15-voice-system-stttts)
16. [Proactivity: Heartbeat and scheduled actions](#16-proactivity--heartbeat-and-scheduled-actions)
17. [RAG Spaces and hybrid search](#17-rag-spaces-and-hybrid-search)
18. [Browser Control and Web Fetch](#18-browser-control-and-web-fetch)
19. [Security: defence in depth](#19-security--defence-in-depth)
20. [Observability and monitoring](#20-observability-and-monitoring)
21. [Performance: optimizations and metrics](#21-performance--optimizations-and-metrics)
22. [CI/CD and quality](#22-cicd-and-quality)
23. [Cross-cutting engineering patterns](#23-cross-cutting-engineering-patterns)
24. [Architecture Decision Records (ADR)](#24-architecture-decision-records-adr)
25. [Evolution potential and extensibility](#25-evolution-potential-and-extensibility)

---

## 1. Context and founding choices

### 1.1. Why these choices?

Every technical decision in LIA addresses a concrete constraint. The project aims to be a multi-agent AI assistant **self-hostable on modest hardware** (Raspberry Pi 5, ARM64), with full transparency, data sovereignty, and multi-provider LLM support. These constraints have guided the entire stack.

| Constraint | Architectural consequence |
|------------|--------------------------|
| ARM64 self-hosting | Multi-arch Docker, local E5 embeddings (no API dependency), Playwright chromium cross-platform |
| Data sovereignty | Local PostgreSQL (no SaaS DB), Fernet encryption at rest, local Redis sessions |
| Multi-provider LLM | Factory pattern with 7 adapters, per-node configuration, no tight coupling to any provider |
| Full transparency | 350+ Prometheus metrics, embedded debug panel, token-by-token tracking |
| Production reliability | 59 ADRs, 2,300+ tests, native observability, 6-level HITL |
| Cost control | Smart Services (89% token savings), local embeddings, prompt caching, catalogue filtering |

### 1.2. Architectural principles

| Principle | Implementation |
|-----------|----------------|
| **Domain-Driven Design** | Bounded contexts in `src/domains/`, explicit aggregates, Router/Service/Repository/Model layers |
| **Hexagonal Architecture** | Ports (Python protocols) and adapters (concrete Google/Microsoft/Apple clients) |
| **Event-Driven** | SSE streaming, ContextVar propagation, fire-and-forget background tasks |
| **Defence in Depth** | 5 layers for usage limits, 6 HITL levels, 3 anti-hallucination layers |
| **Feature Flags** | Each subsystem toggleable (`{FEATURE}_ENABLED`) |
| **Configuration as Code** | Pydantic BaseSettings composed via MRO, priority chain APPLICATION > .ENV > CONSTANT |

### 1.3. Codebase metrics

| Metric | Value |
|--------|-------|
| Tests | 2,300+ (unit, integration, agents, benchmark) |
| Reusable fixtures | 170+ |
| Documentation documents | 190+ |
| ADRs (Architecture Decision Records) | 59 |
| Prometheus metrics | 350+ definitions |
| Grafana dashboards | 18 |
| Supported languages (i18n) | 6 (fr, en, de, es, it, zh) |

---

## 2. Technology stack

### 2.1. Backend

| Technology | Version | Role | Why this choice |
|------------|---------|------|-----------------|
| Python | 3.12+ | Runtime | Richest ML/AI ecosystem, native async, complete typing |
| FastAPI | 0.135.1 | REST API + SSE | Auto Pydantic validation, OpenAPI docs, async-first, performance |
| LangGraph | 1.1.2 | Multi-agent orchestration | Only framework offering native state persistence + cycles + interrupts (HITL) |
| LangChain Core | 1.2.19 | LLM/tools abstractions | `@tool` decorator, message formats, standardized callbacks |
| SQLAlchemy | 2.0.48 | Async ORM | `Mapped[Type]` + `mapped_column()`, async sessions, `selectinload()` |
| PostgreSQL | 16 + pgvector | Database + vector search | Native LangGraph checkpoints, HNSW semantic search, maturity |
| Redis | 7.3.0 | Cache, sessions, rate limiting | O(1) ops, atomic sliding window (Lua), SETNX leader election |
| Pydantic | 2.12.5 | Validation + serialization | `ConfigDict`, `field_validator`, settings composition via MRO |
| structlog | latest | Structured logging | JSON output with automatic PII filtering, snake_case events |
| sentence-transformers | 5.0+ | Local embeddings | Multilingual E5-small (384d), zero API cost, ~50 ms on ARM64 |
| Playwright | latest | Browser automation | Headless Chromium, CDP accessibility tree, cross-platform |
| APScheduler | 3.x | Background jobs | Cron/interval triggers, compatible with Redis leader election |

### 2.2. Frontend

| Technology | Version | Role |
|------------|---------|------|
| Next.js | 16.1.7 | App Router, SSR, ISR |
| React | 19.2.4 | UI with Server Components |
| TypeScript | 5.9.3 | Strict typing |
| TailwindCSS | 4.2.1 | Utility-first CSS |
| TanStack Query | 5.90 | Server state management, cache, mutations |
| Radix UI | v2 | Accessible UI primitives |
| react-i18next | 16.5 | i18n (6 languages), namespace-based |
| Zod | 3.x | Runtime validation of debug schemas |

### 2.3. Supported LLM Providers

| Provider | Models | Specifics |
|----------|--------|-----------|
| OpenAI | GPT-5.4, GPT-5.4-mini, GPT-5.x, GPT-4.1-x, o1, o3-mini | Native prompt caching, Responses API, reasoning_effort |
| Anthropic | Claude Opus 4.6/4.5/4, Sonnet 4.6/4.5/4, Haiku 4.5 | Extended thinking, prompt caching |
| Google | Gemini 3.1/3/2.5 Pro, Flash 3/2.5/2.0 | Multimodal, HD TTS |
| DeepSeek | V3 (chat), R1 (reasoner) | Reduced cost, native reasoning |
| Perplexity | sonar-small/large-128k-online | Search-augmented generation |
| Qwen | qwen3-max, qwen3.5-plus, qwen3.5-flash | Thinking mode, tools + vision (Alibaba Cloud) |
| Ollama | Any local model (dynamic discovery) | Zero API cost, self-hosted |

**Why 7 providers?** The choice is not collection for its own sake. It is a resilience strategy: each pipeline node can be assigned to a different provider. If OpenAI raises its prices, the router switches to DeepSeek. If Anthropic has an outage, the response falls back to Gemini. The LLM abstraction (`src/infrastructure/llm/factory.py`) uses the Factory pattern with `init_chat_model()`, overridden by specific adapters (`ResponsesLLM` for the OpenAI Responses API, eligibility by regex `^(gpt-4\.1|gpt-5|o[1-9])`).

---

## 3. Backend architecture: Domain-Driven Design

### 3.1. Domain structure

```
apps/api/src/
├── core/                         # Cross-cutting technical core
│   ├── config/                   # 9 Pydantic BaseSettings modules composed via MRO
│   │   ├── __init__.py           # Settings class (final MRO)
│   │   ├── agents.py, database.py, llm.py, mcp.py, voice.py, usage_limits.py, ...
│   ├── constants.py              # 1,000+ centralized constants
│   ├── exceptions.py             # Centralized exceptions (raise_user_not_found, etc.)
│   └── i18n.py                   # i18n → settings bridge
│
├── domains/                      # Bounded Contexts (DDD)
│   ├── agents/                   # MAIN DOMAIN — LangGraph orchestration
│   │   ├── nodes/                # 7+ graph nodes
│   │   ├── services/             # Smart Services, HITL, context resolution
│   │   ├── tools/                # Tools by domain (@tool + ToolResponse)
│   │   ├── orchestration/        # ExecutionPlan, parallel executor, validators
│   │   ├── registry/             # AgentRegistry, domain_taxonomy, catalogue
│   │   ├── semantic/             # Semantic router, expansion service
│   │   ├── middleware/           # Memory injection, personality injection
│   │   ├── prompts/v1/           # 57 versioned .txt prompt files
│   │   ├── graphs/               # 15 agent builders (one per domain)
│   │   ├── context/              # Context store (Data Registry), decorators
│   │   └── models.py             # MessagesState (TypedDict + custom reducer)
│   ├── auth/                     # OAuth 2.1, BFF sessions, RBAC
│   ├── connectors/               # Multi-provider abstraction (Google/Apple/Microsoft)
│   ├── rag_spaces/               # Upload, chunking, embedding, hybrid retrieval
│   ├── journals/                 # Introspective journals
│   ├── interests/                # Interest learning
│   ├── heartbeat/                # LLM-driven proactive notifications
│   ├── channels/                 # Multi-channel (Telegram)
│   ├── voice/                    # TTS Factory, STT Sherpa, Wake Word
│   ├── skills/                   # agentskills.io standard
│   ├── sub_agents/               # Persistent specialized agents
│   ├── usage_limits/             # Per-user quotas (5-layer defence)
│   └── ...                       # conversations, reminders, scheduled_actions, users, user_mcp
│
└── infrastructure/               # Cross-cutting layer
    ├── llm/                      # Factory, providers, adapters, embeddings, tracking
    ├── cache/                    # Redis sessions, LLM cache, JSON helpers
    ├── mcp/                      # MCP client pool, auth, SSRF, tool adapters, Excalidraw
    ├── browser/                  # Playwright session pool, CDP, anti-detection
    ├── rate_limiting/            # Distributed Redis sliding window
    ├── scheduler/                # APScheduler, leader election, locks
    └── observability/            # 17+ Prometheus metrics files, OTel tracing
```

### 3.2. Configuration priority chain

A fundamental invariant permeates the entire backend. It was systematically enforced in v1.9.4 with ~291 corrections across ~80 files, because divergences between constants and actual production configuration were causing silent bugs:

```
APPLICATION (Admin UI / DB) > .ENV (settings) > CONSTANT (fallback)
```

**Why this chain?** Constants (`src/core/constants.py`) serve exclusively as fallbacks for Pydantic `Field(default=...)` and SQLAlchemy `server_default=`. An administrator who changes an LLM model from the interface must see that change take effect immediately, without redeployment. At runtime, all code reads `settings.field_name`, never a constant directly.

### 3.3. Layer patterns

| Layer | Responsibility | Key pattern |
|-------|---------------|-------------|
| **Router** | HTTP validation, auth, serialization | `Depends(get_current_active_session)`, `check_resource_ownership()` |
| **Service** | Business logic, orchestration | Constructor receives `AsyncSession`, creates repositories, centralized exceptions |
| **Repository** | Data access | Inherits `BaseRepository[T]`, pagination `tuple[list[T], int]` |
| **Model** | DB schema | `Mapped[Type]` + `mapped_column()`, `UUIDMixin`, `TimestampMixin` |
| **Schema** | I/O validation | Pydantic v2, `Field()` with description, separate request/response |

---

## 4. LangGraph: multi-agent orchestration

### 4.1. Why LangGraph? (ADR-001)

The choice of LangGraph over LangChain alone, CrewAI, or AutoGen is based on three non-negotiable requirements:

1. **State persistence**: `TypedDict` with custom reducers, persisted via PostgreSQL checkpoints — allows resuming a conversation after HITL interruption
2. **Cycles and interrupts**: native support for loops (HITL rejection → re-planning) and the `interrupt()` pattern — without which the 6-layer HITL would be impossible
3. **SSE Streaming**: native integration with callback handlers — critical for real-time UX

CrewAI and AutoGen were easier to get started with, but neither supported the interrupt/resume pattern required for plan-level HITL. This choice has a cost: the learning curve is steeper (graph concepts, conditional edges, state schemas).

### 4.2. The main graph

```
                    ┌──────────────────────────────────┐
                    │        Router Node (v3)            │
                    │  Binary: conversation|actionable   │
                    │  Confidence: high > 0.85           │
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

### 4.3. Graph nodes

| Node | File | Role | Windowing |
|------|------|------|-----------|
| Router v3 | `router_node_v3.py` | Binary classification conversation/actionable | 5 turns |
| QueryAnalyzer | `query_analyzer_service.py` | Domain detection, intent extraction | — |
| Planner v3 | `planner_node_v3.py` | ExecutionPlan DSL generation | 10 turns |
| Semantic Validator | `semantic_validator.py` | Dependency validation and coherence | — |
| Approval Gate | `hitl_dispatch_node.py` | HITL interrupt(), 6 approval levels | — |
| Task Orchestrator | `task_orchestrator_node.py` | Parallel execution, context passing | — |
| Response | `response_node.py` | Anti-hallucination synthesis, 3 guard layers | 20 turns |

### 4.4. AgentRegistry and Domain Taxonomy

The `AgentRegistry` centralizes agent registration (`registry.register_agent()` in `main.py`), the `ToolManifest` catalogue, and the `domain_taxonomy.py` which defines each domain with its `result_key` and aliases.

**Why a centralized registry?** Without it, adding an agent required modifying 5+ files. With the registry, a new agent declares itself at a single point and is automatically available for routing, planning, and execution.

---

## 5. The conversational execution pipeline

### 5.1. Detailed flow of an actionable request

1. **Reception**: User message → SSE endpoint `/api/v1/chat/stream`
2. **Context**: `request_tool_manifests_ctx` ContextVar built once (ADR-061: 3-layer defence)
3. **Router**: Binary classification with confidence scoring (high > 0.85, medium > 0.65)
4. **QueryAnalyzer**: Identifies domains via LLM + post-expansion validation (gate-keeper that filters disabled domains)
5. **SmartPlanner**: Generates an `ExecutionPlan` (structured JSON DSL)
   - Pattern Learning: consults the Bayesian cache (bypass if confidence > 90%)
   - Skill detection: deterministic Skills are protected via `_has_potential_skill_match()`
6. **Semantic Validator**: Verifies inter-step dependency coherence
7. **HITL Dispatch**: Classifies the approval level, `interrupt()` if necessary
8. **Task Orchestrator**: Executes steps in parallel waves via `asyncio.gather()`
   - Filters skipped steps BEFORE gather (ADR-005 — fixes a bug causing double execution plan+fallback)
   - Context passing via Data Registry (InMemoryStore)
   - FOR_EACH pattern for bulk iterations
9. **Response Node**: Synthesizes results, memory + journals + RAG injection
10. **SSE Stream**: Token by token to the frontend
11. **Background tasks** (fire-and-forget): memory extraction, journal extraction, interest detection

### 5.2. ContextVar: implicit state propagation

A critical mechanism is the use of Python `ContextVar` to propagate state without parameter threading:

| ContextVar | Role | Why |
|------------|------|-----|
| `current_tracker` | TrackingContext for LLM token tracking | Avoids passing a tracker through 15 layers of functions |
| `request_tool_manifests_ctx` | Per-request filtered tool manifests | Built once, read by 7+ consumers (eliminates duplication ADR-061) |

This approach maintains per-request isolation in an asyncio context without polluting function signatures.

---

## 6. The planning system (ExecutionPlan DSL)

### 6.1. Plan structure

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

### 6.2. FOR_EACH pattern

**Why a dedicated pattern?** Bulk operations (sending an email to 12 contacts) cannot be planned as 12 static steps — the number of elements is unknown before executing the previous step. FOR_EACH solves this problem with safeguards:
- HITL threshold: any mutation >= 1 element triggers mandatory approval
- Configurable limit: `for_each_max` prevents unbounded executions
- Dynamic reference: `$steps.{step_id}.{field}` for previous step results

### 6.3. Parallel execution in waves

The `parallel_executor.py` organizes steps into waves (DAG):
1. Identifies steps with no unresolved dependencies → next wave
2. Filters skipped steps (unmet conditions, fallback branches) — **before** `asyncio.gather()`, not after (ADR-005: fixes a bug that caused 2x API calls and 2x costs)
3. Executes the wave with per-step error isolation
4. Feeds the Data Registry with results
5. Repeats until plan completion

---

## 7. Smart Services: intelligent optimization

### 7.1. The problem solved

Without optimization, scaling to 10+ domains caused costs to explode: going from 3 tools (contacts) to 30+ tools (10 domains) multiplied prompt size by 10x and therefore cost per request by 10x (ADR-003). Smart Services were designed to bring this cost back to mono-domain system levels.

| Service | Role | Mechanism | Measured gain |
|---------|------|-----------|---------------|
| `QueryAnalyzerService` | Routing decision | LRU cache (TTL 5 min) | ~35% cache hit |
| `SmartPlannerService` | Plan generation | Bayesian Pattern Learning | Bypass > 90% confidence |
| `SmartCatalogueService` | Tool filtering | Domain-based filtering | 96% token reduction |
| `PlanPatternLearner` | Learning | Bayesian scoring Beta(2,1) | ~2,300 tokens saved per replan |

### 7.2. PlanPatternLearner

**How it works**: When a plan is validated and executed successfully, its tool sequence is stored in Redis (hash `plan:patterns:{tool→tool}`, TTL 30 days). For future requests, a Bayesian score is calculated: `confidence = (α + successes) / (α + β + successes + failures)`. Above 90%, the plan is reused directly without an LLM call.

**Safeguards**: K-anonymity (minimum 3 observations for suggestion, 10 for bypass), exact domain matching, maximum 3 injected patterns (~45 tokens overhead), strict 5 ms timeout.

**Bootstrapping**: 50+ predefined golden patterns at startup, each with 20 simulated successes (= 95.7% initial confidence).

---

## 8. Semantic routing and local embeddings

### 8.1. Why local embeddings? (ADR-049)

Purely LLM-based routing had two problems: cost (each request = one LLM call) and accuracy (the LLM was wrong about domains in ~20% of multi-domain cases). Local embeddings solve both:

| Property | Value |
|----------|-------|
| Model | multilingual-e5-small |
| Dimensions | 384 |
| Latency | ~50 ms (ARM64 Pi 5) |
| API cost | Zero |
| Languages | 100+ |
| Accuracy gain | +48% on Q/A matching vs LLM-only routing |

### 8.2. Semantic Tool Router (ADR-048)

Each `ToolManifest` has multilingual `semantic_keywords`. The query is transformed into an embedding, then compared by cosine similarity with **max-pooling** (score = MAX per tool, not average — avoids semantic dilution). Dual threshold: >= 0.70 = high confidence, 0.60-0.70 = uncertainty.

### 8.3. Semantic Expansion

The `expansion_service.py` enriches results by exploring adjacent domains. Post-expansion validation (ADR-061, Layer 1) filters domains disabled by the administrator — fixing a bug where the LLM or expansion could reintroduce domains that had been disabled.

---

## 9. Human-in-the-Loop: 6-layer architecture

### 9.1. Why at the plan level? (Phase 7 → Phase 8)

The initial approach (Phase 7) interrupted execution **during** tool calls — each sensitive tool generated an interruption. The UX was poor (unexpected pauses) and the cost was high (per-tool overhead).

Phase 8 (current) submits the **complete plan** to the user **before** any execution. A single interruption, a global view, the ability to edit parameters. The trade-off: the planner must be trusted to produce a faithful plan.

### 9.2. The 6 approval types

| Type | Trigger | Mechanism |
|------|---------|-----------|
| `PLAN_APPROVAL` | Destructive actions | `interrupt()` with PlanSummary |
| `CLARIFICATION` | Ambiguity detected | `interrupt()` with LLM question |
| `DRAFT_CRITIQUE` | Email/event/contact draft | `interrupt()` with serialized draft + markdown template |
| `DESTRUCTIVE_CONFIRM` | Deletion >= 3 elements | `interrupt()` with irreversibility warning |
| `FOR_EACH_CONFIRM` | Bulk mutations | `interrupt()` with operation count |
| `MODIFIER_REVIEW` | AI-suggested modifications | `interrupt()` with before/after comparison |

### 9.3. Enriched Draft Critique

For drafts, a dedicated prompt generates a structured critique with per-domain markdown templates, field emojis, before/after comparison with strikethrough for updates, and irreversibility warnings. Post-HITL results display i18n labels and clickable links.

### 9.4. Compaction Safety

4 conditions prevent LLM compaction (summarization of old messages) during active approval flows. Without this protection, a summary could delete the critical context of an ongoing interruption.

---

## 10. State management and message windowing

### 10.1. MessagesState and custom reducer

The LangGraph state is a `TypedDict` with an `add_messages_with_truncate` reducer that handles token-based truncation, OpenAI message sequence validation, and tool message deduplication.

### 10.2. Why per-node windowing? (ADR-007)

**The problem**: a conversation of 50+ messages generated 100k+ tokens of context, with latency > 10 s for the router and exploding costs.

**The solution**: each node operates on a different window, calibrated to its actual need:

| Node | Turns | Justification |
|------|-------|---------------|
| Router | 5 | Fast decision, minimal context suffices |
| Planner | 10 | Needs context for planning, but not the entire history |
| Response | 20 | Rich context for natural synthesis |

**Measured impact**: E2E latency -50% (10 s → 5 s), cost -77% on long conversations, quality preserved thanks to the Data Registry which stores tool results independently from messages.

### 10.3. Context Compaction

When the token count exceeds a dynamic threshold (ratio of the response model's context window), an LLM summary is generated. Critical identifiers (UUIDs, URLs, emails) are preserved. Savings ratio: ~60% per compaction. `/resume` command for manual triggering.

### 10.4. PostgreSQL Checkpointing

Full state checkpointed after each node. P95 save < 50 ms, P95 load < 100 ms, average size ~15 KB/conversation.

---

## 11. Memory system and psychological profile

### 11.1. Architecture

```
AsyncPostgresStore + Semantic Index (pgvector)
├── Namespace: (user_id, "memories")        → Psychological profile
├── Namespace: (user_id, "documents", src)  → Document RAG
└── Namespace: (user_id, "context", domain) → Tool context (Data Registry)
```

### 11.2. Enriched memory schema

Each memory is a structured document with:
- `content`, `category` (preference, fact, personality, relationship, sensitivity...)
- `importance` (1-10), `emotional_weight` (-10 to +10)
- `usage_nuance`: how to use this information in a caring manner
- Embedding `text-embedding-3-small` (1536d) via pgvector HNSW

**Why an emotional weight?** An assistant that knows your mother is ill but treats this fact like any other piece of data is at best clumsy, at worst hurtful. The emotional weight enables the `DANGER_DIRECTIVE` (prohibition on joking, minimizing, comparing, trivializing) when a sensitive subject is touched upon.

### 11.3. Extraction and injection

**Extraction**: after each conversation, a background process analyzes the last user message, adapted to the active personality. Cost tracked via `TrackingContext`.

**Injection**: the `memory_injection.py` middleware searches for semantically close memories, builds the injectable psychological profile, and activates the `DANGER_DIRECTIVE` if necessary. Injected into the Response Node's system prompt.

### 11.4. Hybrid search BM25 + semantic

Combination with configurable alpha (default 0.6 semantic / 0.4 BM25). 10% boost when both signals are strong (> 0.5). Graceful fallback to semantic only if BM25 fails. Performance: 40-90 ms with cache.

### 11.5. Journals

The assistant maintains introspective reflections across four themes (self-reflection, user observations, ideas/analyses, learnings). Two triggers: post-conversation extraction + periodic consolidation (4h). OpenAI 1536d embeddings with `search_hints` (LLM keywords in the user's vocabulary). Injected into the **Response Node and Planner Node** prompt — the latter uses `intelligence.original_query` as the semantic query.

Anti-hallucination UUID: `field_validator`, reference ID table, filtering by known IDs in extraction and consolidation.

### 11.6. Interest system

Detection through query analysis with Bayesian weight evolution (decay 0.01/day). Multi-source proactive notifications (Wikipedia, Perplexity, LLM). User feedback (thumbs up/down/block) adjusts weights.

---

## 12. Multi-provider LLM infrastructure

### 12.1. Factory Pattern

```python
llm = get_llm(provider="openai", model="gpt-5.4", temperature=0.7, streaming=True)
```

`get_llm()` resolves the effective configuration via `get_llm_config_for_agent(settings, agent_type)` (code defaults → DB admin overrides), instantiates the model, and applies specific adapters.

### 12.2. 34 LLM configuration types

Each pipeline node is independently configurable via the Admin UI — without redeployment:

| Category | Configurable types |
|----------|-------------------|
| Pipeline | router, query_analyzer, planner, semantic_validator, context_resolver |
| Response | response, hitl_question_generator |
| Background | memory_extraction, interest_extraction, journal_extraction, journal_consolidation |
| Agents | contacts_agent, emails_agent, calendar_agent, browser_agent, etc. |

### 12.3. Token Tracking

The `TrackingContext` tracks each LLM call with `call_type` ("chat"/"embedding"), `sequence` (monotonic counter), `duration_ms`, tokens (input/output/cache), and cost calculated from DB pricing. Trackers share a `run_id` for aggregation. The debug panel displays all invocations (pipeline + background tasks) in a unified chronological view.

---

## 13. Connectors: multi-provider abstraction

### 13.1. Protocol-based architecture

```
ConnectorTool (base.py) → ClientRegistry → resolve_client(type) → Protocol
     ├── GoogleGmailClient       implements EmailClientProtocol
     ├── MicrosoftOutlookClient  implements EmailClientProtocol
     ├── AppleEmailClient        implements EmailClientProtocol
     └── PhilipsHueClient        implements SmartHomeClientProtocol
```

**Why Python protocols?** Structural duck typing allows adding a new provider without modifying calling code. The `ProviderResolver` guarantees that only one provider is active per functional category.

### 13.2. Reusable patterns

`BaseOAuthClient` (template method with 3 hooks), `BaseGoogleClient` (pagination via pageToken), `BaseMicrosoftClient` (OData). Circuit breaker, distributed Redis rate limiting, refresh token with double-check pattern and Redis locking against thundering herd.

---

## 14. MCP: Model Context Protocol

### 14.1. Architecture

The `MCPClientManager` manages connection lifecycle (exit stacks), tool discovery (`session.list_tools()`), and automatic LLM-based domain description generation. The `ToolAdapter` normalizes MCP tools to the LangChain `@tool` format, with structured parsing of JSON responses into individual items.

### 14.2. MCP Security

Mandatory HTTPS, SSRF prevention (DNS resolution + IP blocklist), Fernet credential encryption, OAuth 2.1 (DCR + PKCE S256), Redis rate limiting per server/tool, API guard 403 on proxy endpoints for disabled servers (ADR-061 Layer 3).

### 14.3. MCP Iterative Mode (ReAct)

MCP servers with `iterative_mode: true` use a dedicated ReAct agent (observe/think/act loop) instead of the static planner. The agent first reads the server documentation, understands the expected format, then calls tools with the correct parameters. Particularly effective for servers with complex APIs (e.g., Excalidraw). Togglable per server in admin or user configuration. Powered by the generic `ReactSubAgentRunner` (shared with the browser agent).

---

## 15. Voice system (STT/TTS)

### 15.1. STT

Wake word ("OK Guy") via Sherpa-onnx WASM in the browser (zero external transmission). Whisper Small transcription (99+ languages, offline) server-side via ThreadPoolExecutor. Per-user STT language with thread-safe `OfflineRecognizer` cache per language.

**Latency optimizations**: KWS → recording microphone stream reuse (~200-800 ms saved), WebSocket pre-connection, `getUserMedia` + WS parallelized via `Promise.allSettled`, AudioWorklet Worklet cache.

### 15.2. TTS

Factory pattern: `TTSFactory.create(mode)` with automatic HD → Standard fallback. Standard = Edge TTS (free), HD = OpenAI TTS or Gemini TTS (premium).

---

## 16. Proactivity: Heartbeat and scheduled actions

### 16.1. Heartbeat: 2-phase architecture

**Phase 1 — Decision** (cost-effective, gpt-4.1-mini):
1. `EligibilityChecker`: opt-in, time window, cooldown (2h global, 30 min per type), recent activity
2. `ContextAggregator`: 7 sources in parallel (`asyncio.gather`): Calendar, Weather (change detection), Tasks, Emails, Interests, Memories, Journals
3. LLM structured output: `skip` | `notify` with anti-redundancy (recent history injected)

**Phase 2 — Generation** (if notify): LLM rewrites with personality + user language. Multi-channel dispatch.

### 16.2. Agent Initiative (ADR-062)

Post-execution LangGraph node: after each actionable turn, the initiative analyzes results and proactively checks cross-domain information (read-only). Examples: rain weather → check calendar for outdoor activities, email mentioning a meeting → check availability, task deadline → recall context. 100% prompt-driven (no hardcoded logic), structural pre-filter (adjacent domains), memory + interest injection, suggestion field for proposing write actions. Configurable via `INITIATIVE_ENABLED`, `INITIATIVE_MAX_ITERATIONS`, `INITIATIVE_MAX_ACTIONS`.

### 16.3. Scheduled actions

APScheduler with Redis leader election (SETNX, TTL 120s, recheck 5s). `FOR UPDATE SKIP LOCKED` for isolation. Auto-approve of plans (`plan_approved=True` injected into state). Auto-disable after 5 consecutive failures. Retry on transient errors.

---

## 17. RAG Spaces and hybrid search

### 17.1. Pipeline

Upload → Chunking → Embedding (text-embedding-3-small, 1536d) → pgvector HNSW → Hybrid search (cosine + BM25 with alpha fusion) → Context injection in the **Response Node**.

Note: RAG injection is done in the response node, not in the planner. The planner however receives personal journal injection via `build_journal_context()`.

### 17.2. System RAG Spaces (ADR-058)

Built-in FAQ (119+ Q/A, 17 sections) indexed from `docs/knowledge/`. `is_app_help_query` detection by QueryAnalyzer, Rule 0 override in RoutingDecider, App Identity Prompt (~200 tokens, lazy loading). SHA-256 staleness detection, auto-indexation at startup.

---

## 18. Browser Control and Web Fetch

### 18.1. Web Fetch

URL → SSRF validation (DNS + IP blocklist + post-redirect recheck) → readability extraction (fallback full page) → HTML cleaning → Markdown → `<external_content>` wrapping (prompt injection prevention). Redis cache 10 min.

### 18.2. Browser Control (ADR-059)

Autonomous ReAct agent (headless Playwright Chromium). Redis-backed session pool with cross-worker recovery. CDP accessibility tree for element-based interaction. Anti-detection (Chrome UA, webdriver flag removal, dynamic locale/timezone). Cookie banner auto-dismiss (20+ multilingual selectors). Separate read/write rate limiting (40 each per session).

---

## 19. Security: defence in depth

### 19.1. BFF Authentication (ADR-002)

**Why BFF instead of JWT?** JWT in localStorage = XSS vulnerable, 90% size overhead, revocation impossible. The BFF pattern with HTTP-only cookies + Redis sessions eliminates all three problems. v0.3.0 migration: memory -90% (1.2 MB → 120 KB), session lookup P95 < 5 ms, OWASP score B+ → A.

### 19.2. Usage Limits: 5-layer defence in depth

| Layer | Interception point | Why this layer |
|-------|-------------------|----------------|
| Layer 0 | Chat router (HTTP 429) | Block before even starting the SSE stream |
| Layer 1 | Agent service (SSE error) | Cover scheduled actions that bypass the router |
| Layer 2 | `invoke_with_instrumentation()` | Centralized guard covering all background services |
| Layer 3 | Proactive runner | Skip for blocked users |
| Layer 4 | Direct `.ainvoke()` migration | Coverage for non-centralized calls |

**Fail-open** design: infrastructure failures do not block users.

### 19.3. Attack prevention

| Vector | Protection |
|--------|------------|
| XSS | HTTP-only cookies, CSP |
| CSRF | SameSite=Lax |
| SQL Injection | SQLAlchemy ORM (parameterized queries) |
| SSRF | DNS resolution + IP blocklist (Web Fetch, MCP, Browser) |
| Prompt Injection | `<external_content>` safety markers |
| Rate Limiting | Distributed Redis sliding window (atomic Lua) |
| Supply Chain | SHA-pinned GitHub Actions, Dependabot weekly |

---

## 20. Observability and monitoring

### 20.1. Stack

| Technology | Role |
|------------|------|
| Prometheus | 350+ custom metrics (RED pattern) |
| Grafana | 18 production-ready dashboards |
| Loki | Aggregated structured JSON logs |
| Tempo | Cross-service distributed traces (OTLP gRPC) |
| Langfuse | LLM-specific tracing (prompt versions, token usage) |
| structlog | Structured logging with PII filtering |

### 20.2. Embedded Debug Panel

The debug panel in the chat interface provides real-time per-conversation introspection: intent analysis, execution pipeline, LLM pipeline (chronological reconciliation of all LLM + embedding calls), context/memory, intelligence (cache hits, pattern learning), journals (injection + background extraction), lifecycle timing.

Debug metrics persist in `sessionStorage` (50 entries max).

**Why a debug panel in the UI?** In an ecosystem where AI agents are notoriously difficult to debug (non-deterministic behavior, opaque call chains), making metrics accessible directly in the interface eliminates the friction of having to open Grafana or read logs. The operator immediately sees why a request was expensive or why the router chose a particular domain.

---

## 21. Performance: optimizations and metrics

### 21.1. Key metrics (P95)

| Metric | Value | SLO |
|--------|-------|-----|
| API Latency | 450 ms | < 500 ms |
| TTFT (Time To First Token) | 380 ms | < 500 ms |
| Router Latency | 800 ms | < 2 s |
| Planner Latency | 2.5 s | < 5 s |
| E5 Embedding (local) | ~50 ms | < 100 ms |
| Checkpoint save | < 50 ms | P95 |
| Redis session lookup | < 5 ms | P95 |

### 21.2. Implemented optimizations

| Optimization | Measured gain | Trade-off |
|-------------|---------------|-----------|
| Message Windowing | -50% latency, -77% cost | Loss of old context (compensated by Data Registry) |
| Smart Catalogue | 96% token reduction | Panic mode needed if filtering too aggressive |
| Pattern Learning | 89% LLM savings | Bootstrapping required (golden patterns) |
| Prompt Caching | 90% discount | Depends on provider support |
| Local Embeddings | Zero API cost | ~470 MB memory, 9s initial loading |
| Parallel Execution | Latency = max(steps) | Dependency management complexity |
| Context Compaction | ~60% per compaction | Information loss (mitigated by ID preservation) |

---

## 22. CI/CD and quality

### 22.1. Pipeline

```
Pre-commit (local)                GitHub Actions CI
========================          =========================
.bak files check                  Lint Backend (Ruff + Black + MyPy strict)
Secrets grep                      Lint Frontend (ESLint + TypeScript)
Ruff + Black + MyPy               Unit tests + coverage (43%)
Fast unit tests                   Code Hygiene (i18n, Alembic, .env.example)
Critical pattern detection        Docker build smoke test
i18n key sync                     Secret scan (Gitleaks)
Alembic migration conflicts       ─────────────────────────
.env.example completeness         Security workflow (weekly)
ESLint + TypeScript check           CodeQL (Python + JS)
                                    pip-audit + pnpm audit
                                    Trivy filesystem scan
                                    SBOM generation
```

### 22.2. Standards

| Aspect | Tool | Configuration |
|--------|------|---------------|
| Python formatting | Black | line-length=100 |
| Python linting | Ruff | E, W, F, I, B, C4, UP |
| Type checking | MyPy | strict mode |
| Commits | Conventional Commits | `feat(scope):`, `fix(scope):` |
| Tests | pytest | `asyncio_mode = "auto"` |
| Coverage | 43% minimum | Enforced in CI |

---

## 23. Cross-cutting engineering patterns

### 23.1. Tool System

```python
@tool
async def my_tool(param: str) -> dict:
    try:
        result = await do_something(param)
        return ToolResponse(success=True, data=result).model_dump()
    except Exception as e:
        return ToolErrorModel.from_exception(e, context={"tool": "my_tool"}).to_response()
```

`@connector_tool` for credential injection, `@auto_save_context` for Data Registry persistence.

### 23.2. Prompt System

57 versioned `.txt` files in `src/domains/agents/prompts/v1/`, loaded via `load_prompt()` with LRU cache (32 entries). Versions configurable via environment variables.

### 23.3. Centralized Component Activation (ADR-061)

3-layer system solving a duplication problem: before ADR-061, filtering of enabled/disabled components was scattered across 7+ sites. Now:

| Layer | Mechanism |
|-------|-----------|
| Layer 1 | Domain gate-keeper: validates LLM-output domains against `available_domains` |
| Layer 2 | `request_tool_manifests_ctx`: ContextVar built once per request |
| Layer 3 | API guard 403 on MCP proxy endpoints |

---

## 24. Architecture Decision Records (ADR)

59 ADRs in MADR format document the major architectural decisions. Some representative examples:

| ADR | Decision | Problem solved | Measured impact |
|-----|----------|----------------|-----------------|
| 001 | LangGraph for orchestration | Need for state persistence + HITL interrupts | Checkpoints P95 < 50 ms |
| 002 | BFF Pattern (JWT → Redis) | JWT XSS vulnerable, revocation impossible | Memory -90%, OWASP A |
| 003 | Dynamic filtering by domain | 10x prompt size = 10x cost | 73-83% catalogue reduction |
| 005 | Filtering BEFORE asyncio.gather | Plan + fallback executed in parallel = 2x cost | -50% fallback plan cost |
| 007 | Per-node Message Windowing | Long conversations = 100k+ tokens | -50% latency, -77% cost |
| 048 | Semantic Tool Router | Imprecise LLM routing on multi-domain | +48% accuracy |
| 049 | Local E5 Embeddings | API embedding cost + network latency | Zero cost, 50 ms local |
| 057 | Personal Journals | No continuity of reflection between sessions | Planner + response injection |
| 061 | Centralized Component Activation | 7+ duplicated filtering sites | Single source, 3 layers |

---

## 25. Evolution potential and extensibility

### 25.1. Extension points

| Extension | Interface | Documentation |
|-----------|-----------|---------------|
| New connector | `OAuthProvider` Protocol + Client Protocol | `GUIDE_CONNECTOR_IMPLEMENTATION.md` + checklist |
| New agent | `register_agent()` + ToolManifest | `GUIDE_AGENT_CREATION.md` |
| New tool | `@tool` + ToolResponse/ToolErrorModel | `GUIDE_TOOL_CREATION.md` |
| New channel | `BaseChannelSender` + `BaseChannelWebhookHandler` | `NEW_CHANNEL_CHECKLIST.md` |
| New LLM provider | Adapter + model profiles | Extensible Factory |
| New proactive task | `ProactiveTask` Protocol | `NEW_PROACTIVE_TASK_CHECKLIST.md` |

### 25.2. Scalability

| Dimension | Current strategy | Possible evolution |
|-----------|-----------------|-------------------|
| Horizontal | 4 uvicorn workers + Redis leader election | Kubernetes + HPA |
| Data | PostgreSQL + pgvector | Sharding, read replicas |
| Cache | Redis single instance | Redis Cluster |
| Observability | Full embedded stack | Managed Grafana Cloud |

---

## Conclusion

LIA is a software engineering exercise that attempts to solve a concrete problem: building a production-quality, transparent, secure, and extensible multi-agent AI assistant capable of running on a Raspberry Pi.

The 59 ADRs document not only the decisions made but also the rejected alternatives and accepted trade-offs. The 2,300+ tests, complete CI/CD, and strict MyPy are not vanity metrics — they are the mechanisms that allow evolving a system of this complexity without regression.

The interweaving of subsystems — psychological memory, Bayesian learning, semantic routing, systematic HITL, LLM-driven proactivity, introspective journals — creates a system where each component reinforces the others. HITL feeds pattern learning, which reduces costs, which enables more features, which generate more data for memory, which improves responses. This is a virtuous circle by design, not by accident.

---

*Document written based on analysis of the source code (`apps/api/src/`, `apps/web/src/`), technical documentation (190+ documents), 63 ADRs, and the changelog (v1.0 to v1.11.3). All metrics, versions, and patterns cited are verifiable in the codebase.*
