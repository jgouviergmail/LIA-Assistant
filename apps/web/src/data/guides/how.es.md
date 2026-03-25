# LIA — Guía Técnica Completa

> Arquitectura, patrones y decisiones de ingeniería de un asistente IA multi-agente de nueva generación.
>
> Documentación de presentación técnica destinada a arquitectos, ingenieros y expertos técnicos.

**Versión**: 2.1
**Fecha**: 2026-03-25
**Aplicación**: LIA v1.11.5
**Licencia**: AGPL-3.0 (Open Source)

---

## Tabla de contenidos

1. [Contexto y decisiones fundacionales](#1-contexto-y-decisiones-fundacionales)
2. [Stack tecnológico](#2-stack-tecnológico)
3. [Arquitectura backend: Domain-Driven Design](#3-arquitectura-backend--domain-driven-design)
4. [LangGraph: orquestación multi-agente](#4-langgraph--orquestación-multi-agente)
5. [El pipeline de ejecución conversacional](#5-el-pipeline-de-ejecución-conversacional)
6. [El sistema de planificación (ExecutionPlan DSL)](#6-el-sistema-de-planificación-executionplan-dsl)
7. [Smart Services: optimización inteligente](#7-smart-services--optimización-inteligente)
8. [Enrutamiento semántico y embeddings locales](#8-enrutamiento-semántico-y-embeddings-locales)
9. [Human-in-the-Loop: arquitectura de 6 capas](#9-human-in-the-loop--arquitectura-de-6-capas)
10. [Gestión del state y message windowing](#10-gestión-del-state-y-message-windowing)
11. [Sistema de memoria y perfil psicológico](#11-sistema-de-memoria-y-perfil-psicológico)
12. [Infraestructura LLM multi-provider](#12-infraestructura-llm-multi-provider)
13. [Conectores: abstracción multi-proveedor](#13-conectores--abstracción-multi-proveedor)
14. [MCP: Model Context Protocol](#14-mcp--model-context-protocol)
15. [Sistema de voz (STT/TTS)](#15-sistema-de-voz-stttts)
16. [Proactividad: Heartbeat y acciones planificadas](#16-proactividad--heartbeat-y-acciones-planificadas)
17. [RAG Spaces y búsqueda híbrida](#17-rag-spaces-y-búsqueda-híbrida)
18. [Browser Control y Web Fetch](#18-browser-control-y-web-fetch)
19. [Seguridad: defence in depth](#19-seguridad--defence-in-depth)
20. [Observabilidad y monitoreo](#20-observabilidad-y-monitoreo)
21. [Rendimiento: optimizaciones y métricas](#21-rendimiento--optimizaciones-y-métricas)
22. [CI/CD y calidad](#22-cicd-y-calidad)
23. [Patrones de ingeniería transversales](#23-patrones-de-ingeniería-transversales)
24. [Arquitectura de decisiones (ADR)](#24-arquitectura-de-decisiones-adr)
25. [Potencial de evolución y extensibilidad](#25-potencial-de-evolución-y-extensibilidad)

---

## 1. Contexto y decisiones fundacionales

### 1.1. ¿Por qué estas decisiones?

Cada decisión técnica de LIA responde a una restricción concreta. El proyecto apunta a un asistente IA multi-agente **auto-hospedable en hardware modesto** (Raspberry Pi 5, ARM64), con transparencia total, soberanía de datos y soporte multi-proveedor LLM. Estas restricciones han guiado la totalidad del stack.

| Restricción | Consecuencia arquitectural |
|------------|--------------------------|
| Auto-hospedaje ARM64 | Docker multi-arch, embeddings locales E5 (sin dependencia de API), Playwright chromium cross-platform |
| Soberanía de datos | PostgreSQL local (sin SaaS DB), cifrado Fernet en reposo, sesiones Redis locales |
| Multi-proveedor LLM | Factory pattern con 7 adaptadores, configuración por nodo, sin acoplamiento fuerte a un provider |
| Transparencia total | 350+ métricas Prometheus, debug panel integrado, seguimiento token por token |
| Fiabilidad en producción | 59 ADRs, 2 300+ tests, observabilidad nativa, HITL de 6 niveles |
| Costes controlados | Smart Services (89 % de ahorro en tokens), embeddings locales, prompt caching, filtrado de catálogo |

### 1.2. Principios arquitecturales

| Principio | Implementación |
|----------|----------------|
| **Domain-Driven Design** | Bounded contexts en `src/domains/`, agregados explícitos, capas Router/Service/Repository/Model |
| **Hexagonal Architecture** | Ports (protocols Python) y adaptadores (clientes concretos Google/Microsoft/Apple) |
| **Event-Driven** | SSE streaming, ContextVar propagation, fire-and-forget background tasks |
| **Defence in Depth** | 5 capas para los usage limits, 6 niveles HITL, 3 capas anti-alucinación |
| **Feature Flags** | Cada subsistema activable/desactivable (`{FEATURE}_ENABLED`) |
| **Configuration as Code** | Pydantic BaseSettings compuesto via MRO, cadena de prioridad APPLICATION > .ENV > CONSTANT |

### 1.3. Métricas del codebase

| Métrica | Valor |
|----------|--------|
| Tests | 2 300+ (unit, integration, agents, benchmark) |
| Fixtures reutilizables | 170+ |
| Documentos de documentación | 190+ |
| ADRs (Architecture Decision Records) | 59 |
| Métricas Prometheus | 350+ definiciones |
| Dashboards Grafana | 18 |
| Idiomas soportados (i18n) | 6 (fr, en, de, es, it, zh) |

---

## 2. Stack tecnológico

### 2.1. Backend

| Tecnología | Versión | Rol | ¿Por qué esta elección? |
|-------------|---------|------|-------------------|
| Python | 3.12+ | Runtime | Ecosistema ML/IA más rico, async nativo, typing completo |
| FastAPI | 0.135.1 | API REST + SSE | Validación automática Pydantic, docs OpenAPI, async-first, rendimiento |
| LangGraph | 1.1.2 | Orquestación multi-agente | Único framework que ofrece state persistence + ciclos + interrupts (HITL) nativos |
| LangChain Core | 1.2.19 | Abstracciones LLM/tools | Decorador `@tool`, formatos de mensajes, callbacks estandarizados |
| SQLAlchemy | 2.0.48 | ORM async | `Mapped[Type]` + `mapped_column()`, async sessions, `selectinload()` |
| PostgreSQL | 16 + pgvector | Database + vector search | Checkpoints LangGraph nativos, búsqueda semántica HNSW, madurez |
| Redis | 7.3.0 | Cache, sesiones, rate limiting | O(1) ops, sliding window atómico (Lua), SETNX leader election |
| Pydantic | 2.12.5 | Validación + serialización | `ConfigDict`, `field_validator`, composición de settings via MRO |
| structlog | latest | Logging estructurado | JSON output con filtrado PII automático, snake_case events |
| sentence-transformers | 5.0+ | Embeddings locales | E5-small multilingüe (384d), coste API cero, ~50 ms en ARM64 |
| Playwright | latest | Browser automation | Chromium headless, CDP accessibility tree, cross-platform |
| APScheduler | 3.x | Background jobs | Cron/interval triggers, compatible con leader election Redis |

### 2.2. Frontend

| Tecnología | Versión | Rol |
|-------------|---------|------|
| Next.js | 16.1.7 | App Router, SSR, ISR |
| React | 19.2.4 | UI con Server Components |
| TypeScript | 5.9.3 | Tipado estricto |
| TailwindCSS | 4.2.1 | Utility-first CSS |
| TanStack Query | 5.90 | Server state management, cache, mutations |
| Radix UI | v2 | Primitivas UI accesibles |
| react-i18next | 16.5 | i18n (6 idiomas), namespace-based |
| Zod | 3.x | Validación runtime de esquemas debug |

### 2.3. LLM Providers soportados

| Provider | Modelos | Especificidades |
|----------|---------|-------------|
| OpenAI | GPT-5.4, GPT-5.4-mini, GPT-5.x, GPT-4.1-x, o1, o3-mini | Prompt caching nativo, Responses API, reasoning_effort |
| Anthropic | Claude Opus 4.6/4.5/4, Sonnet 4.6/4.5/4, Haiku 4.5 | Extended thinking, prompt caching |
| Google | Gemini 3.1/3/2.5 Pro, Flash 3/2.5/2.0 | Multimodal, TTS HD |
| DeepSeek | V3 (chat), R1 (reasoner) | Coste reducido, reasoning nativo |
| Perplexity | sonar-small/large-128k-online | Search-augmented generation |
| Qwen | qwen3-max, qwen3.5-plus, qwen3.5-flash | Thinking mode, tools + vision (Alibaba Cloud) |
| Ollama | Cualquier modelo local (descubrimiento dinámico) | Coste API cero, auto-hospedado |

**¿Por qué 7 providers?** La elección no es la colección por sí misma. Es una estrategia de resiliencia: cada nodo del pipeline puede asignarse a un provider diferente. Si OpenAI aumenta sus tarifas, el router pasa a DeepSeek. Si Anthropic tiene una caída, la respuesta se redirige a Gemini. La abstracción LLM (`src/infrastructure/llm/factory.py`) utiliza el pattern Factory con `init_chat_model()`, sobrecargado por adaptadores específicos (`ResponsesLLM` para la API Responses de OpenAI, elegibilidad por regex `^(gpt-4\.1|gpt-5|o[1-9])`).

---

## 3. Arquitectura backend: Domain-Driven Design

### 3.1. Estructura de los dominios

```
apps/api/src/
├── core/                         # Núcleo técnico transversal
│   ├── config/                   # 9 módulos Pydantic BaseSettings compuestos via MRO
│   │   ├── __init__.py           # Clase Settings (MRO final)
│   │   ├── agents.py, database.py, llm.py, mcp.py, voice.py, usage_limits.py, ...
│   ├── constants.py              # 1 000+ constantes centralizadas
│   ├── exceptions.py             # Excepciones centralizadas (raise_user_not_found, etc.)
│   └── i18n.py                   # Bridge i18n → settings
│
├── domains/                      # Bounded Contexts (DDD)
│   ├── agents/                   # DOMINIO PRINCIPAL — orquestación LangGraph
│   │   ├── nodes/                # 7+ nodos del grafo
│   │   ├── services/             # Smart Services, HITL, context resolution
│   │   ├── tools/                # Herramientas por dominio (@tool + ToolResponse)
│   │   ├── orchestration/        # ExecutionPlan, parallel executor, validators
│   │   ├── registry/             # AgentRegistry, domain_taxonomy, catalogue
│   │   ├── semantic/             # Semantic router, expansion service
│   │   ├── middleware/           # Memory injection, personality injection
│   │   ├── prompts/v1/           # 57 archivos .txt de prompts versionados
│   │   ├── graphs/               # 15 builders de agentes (uno por dominio)
│   │   ├── context/              # Context store (Data Registry), decorators
│   │   └── models.py             # MessagesState (TypedDict + custom reducer)
│   ├── auth/                     # OAuth 2.1, sesiones BFF, RBAC
│   ├── connectors/               # Abstracción multi-provider (Google/Apple/Microsoft)
│   ├── rag_spaces/               # Upload, chunking, embedding, retrieval híbrido
│   ├── journals/                 # Cuadernos de bitácora introspectivos
│   ├── interests/                # Aprendizaje de centros de interés
│   ├── heartbeat/                # Notificaciones proactivas LLM-driven
│   ├── channels/                 # Multi-canal (Telegram)
│   ├── voice/                    # TTS Factory, STT Sherpa, Wake Word
│   ├── skills/                   # Estándar agentskills.io
│   ├── sub_agents/               # Agentes especializados persistentes
│   ├── usage_limits/             # Cuotas por usuario (5-layer defence)
│   └── ...                       # conversations, reminders, scheduled_actions, users, user_mcp
│
└── infrastructure/               # Capa transversal
    ├── llm/                      # Factory, providers, adapters, embeddings, tracking
    ├── cache/                    # Redis sessions, LLM cache, JSON helpers
    ├── mcp/                      # MCP client pool, auth, SSRF, tool adapters, Excalidraw
    ├── browser/                  # Playwright session pool, CDP, anti-detección
    ├── rate_limiting/            # Redis sliding window distribuido
    ├── scheduler/                # APScheduler, leader election, locks
    └── observability/            # 17+ archivos de métricas Prometheus, tracing OTel
```

### 3.2. Cadena de prioridad de configuración

Un invariante fundamental atraviesa todo el backend. Fue sistemáticamente aplicado en v1.9.4 con ~291 correcciones en ~80 archivos, porque las divergencias entre constantes y la configuración real de producción causaban bugs silenciosos:

```
APPLICATION (Admin UI / DB) > .ENV (settings) > CONSTANT (fallback)
```

**¿Por qué esta cadena?** Las constantes (`src/core/constants.py`) sirven exclusivamente como fallback para los `Field(default=...)` Pydantic y los `server_default=` SQLAlchemy. Un administrador que cambia un modelo LLM desde la interfaz debe ver ese cambio aplicado inmediatamente, sin redespliegue. En runtime, todo el código lee `settings.field_name`, nunca directamente una constante.

### 3.3. Patrones de capas

| Capa | Responsabilidad | Patrón clave |
|--------|---------------|-------------|
| **Router** | Validación HTTP, auth, serialización | `Depends(get_current_active_session)`, `check_resource_ownership()` |
| **Service** | Lógica de negocio, orquestación | Constructor recibe `AsyncSession`, crea repositories, excepciones centralizadas |
| **Repository** | Acceso a datos | Hereda de `BaseRepository[T]`, paginación `tuple[list[T], int]` |
| **Model** | Esquema DB | `Mapped[Type]` + `mapped_column()`, `UUIDMixin`, `TimestampMixin` |
| **Schema** | Validación I/O | Pydantic v2, `Field()` con description, request/response separados |

---

## 4. LangGraph: orquestación multi-agente

### 4.1. ¿Por qué LangGraph? (ADR-001)

La elección de LangGraph en lugar de LangChain solo, CrewAI o AutoGen se basa en tres necesidades innegociables:

1. **State persistence**: `TypedDict` con reducers custom, persistido via PostgreSQL checkpoints — permite reanudar una conversación tras una interrupción HITL
2. **Ciclos e interrupts**: soporte nativo de bucles (rechazo HITL → re-planificación) y del pattern `interrupt()` — sin el cual el HITL de 6 capas sería imposible
3. **Streaming SSE**: integración nativa con callback handlers — crítico para la UX en tiempo real

CrewAI y AutoGen eran más simples de adoptar, pero ninguno de los dos soportaba el pattern interrupt/resume necesario para el HITL a nivel de plan. Esta elección tiene un coste: la curva de aprendizaje es más pronunciada (conceptos de grafos, edges condicionales, state schemas).

### 4.2. El grafo principal

```
                    ┌──────────────────────────────────┐
                    │        Router Node (v3)            │
                    │  Binario : conversation|actionable  │
                    │  Confianza : high > 0.85            │
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

### 4.3. Nodos del grafo

| Nodo | Archivo | Rol | Windowing |
|------|---------|------|-----------|
| Router v3 | `router_node_v3.py` | Clasificación binaria conversation/actionable | 5 turns |
| QueryAnalyzer | `query_analyzer_service.py` | Detección de dominios, extracción de intent | — |
| Planner v3 | `planner_node_v3.py` | Generación ExecutionPlan DSL | 10 turns |
| Semantic Validator | `semantic_validator.py` | Validación de dependencias y coherencia | — |
| Approval Gate | `hitl_dispatch_node.py` | HITL interrupt(), 6 niveles de aprobación | — |
| Task Orchestrator | `task_orchestrator_node.py` | Ejecución paralela, paso de contexto | — |
| Response | `response_node.py` | Síntesis anti-alucinación, 3 capas de guardia | 20 turns |

### 4.4. AgentRegistry y Domain Taxonomy

El `AgentRegistry` centraliza el registro de agentes (`registry.register_agent()` en `main.py`), el catálogo de `ToolManifest`, y la `domain_taxonomy.py` que define cada dominio con su `result_key` y sus alias.

**¿Por qué un registro centralizado?** Sin él, la adición de un agente requería modificar 5+ archivos. Con el registro, un nuevo agente se declara en un solo punto y queda automáticamente disponible para el enrutamiento, la planificación y la ejecución.

### 4.5. Domain Taxonomy

Cada dominio es un `DomainConfig` declarativo: nombre, agentes, `result_key` (clave canónica para referencias `$steps`), `related_domains`, prioridad y enrutabilidad. El `DOMAIN_REGISTRY` es la fuente única de verdad consumida por tres subsistemas: SmartCatalogue (filtrado), expansión semántica (dominios adyacentes) y fase Initiative (prefiltro estructural).

### 4.6. Tool Manifests

Cada tool declara un `ToolManifest` a través de un `ToolManifestBuilder` fluido: parámetros, salidas, perfil de coste, permisos y `semantic_keywords` multilingües para enrutamiento. Los manifiestos son consumidos por el planner (inyección de catálogo), el router semántico (matching por palabras clave) y el builder de agentes (cableado de tools). Ver sección 23 para la arquitectura completa de tools.

---

## 5. El pipeline de ejecución conversacional

### 5.1. Flujo detallado de una petición accionable

1. **Recepción**: Mensaje del usuario → endpoint SSE `/api/v1/chat/stream`
2. **Contexto**: `request_tool_manifests_ctx` ContextVar construido una vez (ADR-061: 3-layer defence)
3. **Router**: Clasificación binaria con scoring de confianza (high > 0.85, medium > 0.65)
4. **QueryAnalyzer**: Identifica los dominios via LLM + validación post-expansión (gate-keeper que filtra los dominios desactivados)
5. **SmartPlanner**: Genera un `ExecutionPlan` (DSL JSON estructurado)
   - Pattern Learning: consulta la caché bayesiana (bypass si confianza > 90 %)
   - Skill detection: los Skills deterministas están protegidos via `_has_potential_skill_match()`
6. **Semantic Validator**: Verifica la coherencia de las dependencias inter-etapas
7. **HITL Dispatch**: Clasifica el nivel de aprobación, `interrupt()` si es necesario
8. **Task Orchestrator**: Ejecuta las etapas en oleadas paralelas via `asyncio.gather()`
   - Filtra las etapas skipped ANTES del gather (ADR-005 — corrige un bug de doble ejecución plan+fallback)
   - Paso de contexto via Data Registry (InMemoryStore)
   - Pattern FOR_EACH para iteraciones en masa
9. **Response Node**: Sintetiza los resultados, inyección de memoria + diarios + RAG
10. **SSE Stream**: Token por token hacia el frontend
11. **Background tasks** (fire-and-forget): extracción de memoria, extracción de diario, detección de intereses

### 5.2. ContextVar: propagación implícita del estado

Un mecanismo crítico es el uso de los `ContextVar` Python para propagar el estado sin parameter threading:

| ContextVar | Rol | ¿Por qué? |
|------------|------|----------|
| `current_tracker` | TrackingContext para el seguimiento de tokens LLM | Evita pasar un tracker a través de 15 capas de funciones |
| `request_tool_manifests_ctx` | Manifiestos de herramientas filtrados por petición | Construido una vez, leído por 7+ consumidores (elimina duplicación ADR-061) |

Este enfoque mantiene un aislamiento por petición en un contexto asyncio sin contaminar las firmas de funciones.

---

## 6. El sistema de planificación (ExecutionPlan DSL)

### 6.1. Estructura del plan

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

**¿Por qué un pattern dedicado?** Las operaciones en masa (enviar un email a 12 contactos) no pueden planificarse como 12 etapas estáticas — el número de elementos es desconocido antes de la ejecución de la etapa anterior. El FOR_EACH resuelve este problema con salvaguardas:
- Umbral HITL: cualquier mutación >= 1 elemento desencadena una aprobación obligatoria
- Límite configurable: `for_each_max` previene las ejecuciones no acotadas
- Referencia dinámica: `$steps.{step_id}.{field}` para los resultados de etapas anteriores

### 6.3. Ejecución paralela en oleadas

El `parallel_executor.py` organiza las etapas en oleadas (DAG):
1. Identifica las etapas sin dependencias no resueltas → oleada siguiente
2. Filtra las etapas skipped (condiciones no cumplidas, ramas fallback) — **antes** de `asyncio.gather()`, no después (ADR-005: corrige un bug que causaba 2x llamadas API y 2x costes)
3. Ejecuta la oleada con aislamiento de error por etapa
4. Alimenta el Data Registry con los resultados
5. Repite hasta la completación del plan

### 6.4. Validador Semántico

Antes de la aprobación HITL, un LLM dedicado (distinto del planner, para evitar el sesgo de autovalidación) inspecciona el plan según 14 tipos de anomalías en cuatro categorías: **Crítico** (capacidad alucinada, dependencia fantasma, ciclo lógico), **Semántico** (desajuste de cardinalidad, desbordamiento/subcubrimiento de alcance, parámetros incorrectos), **Seguridad** (ambigüedad peligrosa, suposición implícita) y **FOR_EACH** (cardinalidad faltante, referencia inválida). Cortocircuito para planes triviales (1 paso), timeout optimista de 1 s.

### 6.5. Validación de Referencias

Las referencias entre pasos (`$steps.get_meetings.events[0].title`) se validan en tiempo de planificación con mensajes de error estructurados: campo inválido, alternativas disponibles y ejemplos corregidos — permitiendo al planner autocorregirse en el retry en lugar de producir fallos silenciosos.

### 6.6. Re-Planner Adaptativo (Panic Mode)

Cuando la ejecución falla, un analizador basado en reglas (sin LLM) clasifica el patrón de fallo (resultados vacíos, fallo parcial, timeout, error de referencia) y selecciona una estrategia de recuperación: retry idéntico, replanificación con alcance ampliado, escalación al usuario o abandono. En **Panic Mode**, el SmartCatalogue se expande para incluir todas las herramientas en un único retry — resolviendo casos donde el filtrado por dominio era demasiado agresivo.

---

## 7. Smart Services: optimización inteligente

### 7.1. El problema resuelto

Sin optimización, el escalado a 10+ dominios hacía explotar los costes: pasar de 3 herramientas (contactos) a 30+ herramientas (10 dominios) multiplicaba por 10 el tamaño del prompt y, por tanto, el coste por petición (ADR-003). Los Smart Services fueron diseñados para llevar este coste al nivel de un sistema mono-dominio.

| Servicio | Rol | Mecanismo | Ganancia medida |
|---------|------|-----------|-------------|
| `QueryAnalyzerService` | Decisión de enrutamiento | Caché LRU (TTL 5 min) | ~35 % cache hit |
| `SmartPlannerService` | Generación de planes | Pattern Learning bayesiano | Bypass > 90 % confianza |
| `SmartCatalogueService` | Filtrado de herramientas | Filtrado por dominio | 96 % reducción tokens |
| `PlanPatternLearner` | Aprendizaje | Scoring bayesiano Beta(2,1) | ~2 300 tokens evitados por replan |

### 7.2. PlanPatternLearner

**Funcionamiento**: Cuando un plan es validado y ejecutado con éxito, su secuencia de herramientas se registra en Redis (hash `plan:patterns:{tool→tool}`, TTL 30 días). Para futuras peticiones, se calcula un score bayesiano: `confianza = (α + éxitos) / (α + β + éxitos + fallos)`. Por encima del 90 %, el plan se reutiliza directamente sin llamada LLM.

**Salvaguardas**: K-anonimidad (mínimo 3 observaciones para sugerencia, 10 para bypass), matching exacto de dominios, máximo 3 patterns inyectados (~45 tokens de overhead), timeout estricto de 5 ms.

**Inicialización**: 50+ golden patterns predefinidos al arranque, cada uno con 20 éxitos simulados (= 95,7 % de confianza inicial).

### 7.3. QueryIntelligence

El QueryAnalyzer produce mucho más que detección de dominios — genera una estructura `QueryIntelligence` profunda: intención inmediata vs objetivo final (`UserGoal`: FIND_INFORMATION, TAKE_ACTION, COMMUNICATE...), intenciones implícitas (ej: "buscar contacto" probablemente significa "enviar algo"), estrategias de fallback anticipadas, indicios de cardinalidad FOR_EACH y puntuaciones de confianza por dominio calibradas por softmax. Esto da al planner una visión más rica que una simple extracción de palabras clave.

### 7.4. Pivote Semántico

Las consultas en cualquier idioma se traducen automáticamente al inglés antes de la comparación de embeddings, mejorando la precisión interlingüística. Caché Redis (TTL 5 min, ~5 ms en hit vs ~500 ms en miss), mediante un LLM rápido.

---

## 8. Enrutamiento semántico y embeddings locales

### 8.1. ¿Por qué embeddings locales? (ADR-049)

El enrutamiento puramente LLM tenía dos problemas: coste (cada petición = una llamada LLM) y precisión (el LLM se equivocaba en los dominios en ~20 % de los casos multi-dominio). Los embeddings locales resuelven ambos:

| Propiedad | Valor |
|-----------|--------|
| Modelo | multilingual-e5-small |
| Dimensiones | 384 |
| Latencia | ~50 ms (ARM64 Pi 5) |
| Coste API | Cero |
| Idiomas | 100+ |
| Ganancia de precisión | +48 % en Q/A matching vs enrutamiento LLM solo |

### 8.2. Semantic Tool Router (ADR-048)

Cada `ToolManifest` posee `semantic_keywords` multilingües. La petición se transforma en embedding, luego se compara por similaridad coseno con **max-pooling** (score = MAX por herramienta, no promedio — evita la dilución semántica). Doble umbral: >= 0.70 = alta confianza, 0.60-0.70 = incertidumbre.

### 8.3. Semantic Expansion

El `expansion_service.py` enriquece los resultados explorando los dominios adyacentes. La validación post-expansión (ADR-061, Layer 1) filtra los dominios desactivados por el administrador — corrigiendo un bug donde el LLM o la expansión podían reintroducir dominios que habían sido desactivados.

---

## 9. Human-in-the-Loop: arquitectura de 6 capas

### 9.1. ¿Por qué a nivel de plan? (Fase 7 → Fase 8)

El enfoque inicial (Fase 7) interrumpía la ejecución **durante** las llamadas de herramientas — cada herramienta sensible generaba una interrupción. La UX era mediocre (pausas inesperadas) y el coste elevado (overhead por herramienta).

La Fase 8 (actual) somete el **plan completo** al usuario **antes** de cualquier ejecución. Una sola interrupción, una visión global, la posibilidad de editar los parámetros. El compromiso: hay que confiar en el planificador para producir un plan fiel.

### 9.2. Los 6 tipos de aprobación

| Tipo | Desencadenante | Mecanismo |
|------|-------------|-----------|
| `PLAN_APPROVAL` | Acciones destructivas | `interrupt()` con PlanSummary |
| `CLARIFICATION` | Ambigüedad detectada | `interrupt()` con pregunta LLM |
| `DRAFT_CRITIQUE` | Borrador de email/event/contact | `interrupt()` con borrador serializado + template markdown |
| `DESTRUCTIVE_CONFIRM` | Eliminación >= 3 elementos | `interrupt()` con advertencia de irreversibilidad |
| `FOR_EACH_CONFIRM` | Mutaciones en masa | `interrupt()` con recuento de operaciones |
| `MODIFIER_REVIEW` | Modificaciones IA sugeridas | `interrupt()` con comparación before/after |

### 9.3. Draft Critique enriquecido

Para los borradores, un prompt dedicado genera una crítica estructurada con templates markdown por dominio, emojis de campos, comparación before/after con strikethrough para las actualizaciones, y advertencias de irreversibilidad. Los resultados post-HITL muestran labels i18n y enlaces clicables.

### 9.4. Clasificación de Respuestas

Cuando el usuario responde a un prompt de aprobación, un clasificador full-LLM (sin regex) categoriza la respuesta en 5 decisiones: **APPROVE**, **REJECT**, **EDIT** (misma acción, parámetros diferentes), **REPLAN** (acción completamente diferente) o **AMBIGUOUS**. Una lógica de degradación previene falsos positivos: un EDIT con parámetros faltantes se degrada a AMBIGUOUS, activando una clarificación.

### 9.5. Compaction Safety

4 condiciones impiden la compactación LLM (resumen de los mensajes antiguos) durante los flujos de aprobación activos. Sin esta protección, un resumen podría eliminar el contexto crítico de una interrupción en curso.

---

## 10. Gestión del state y message windowing

### 10.1. MessagesState y reducer custom

El state LangGraph es un `TypedDict` con un reducer `add_messages_with_truncate` que gestiona el truncation basado en tokens, la validación de las secuencias de mensajes OpenAI, y la deduplicación de los mensajes tool.

### 10.2. ¿Por qué el windowing por nodo? (ADR-007)

**El problema**: una conversación de 50+ mensajes generaba 100k+ tokens de contexto, con una latencia > 10 s para el router y una explosión de los costes.

**La solución**: cada nodo opera sobre una ventana diferente, calibrada según su necesidad real:

| Nodo | Turns | Justificación |
|------|-------|---------------|
| Router | 5 | Decisión rápida, contexto mínimo suficiente |
| Planner | 10 | Necesidad de contexto para planificar, pero no de todo el historial |
| Response | 20 | Contexto rico para síntesis natural |

**Impacto medido**: latencia E2E -50 % (10 s → 5 s), coste -77 % en las conversaciones largas, calidad preservada gracias al Data Registry que almacena los resultados de herramientas independientemente de los mensajes.

### 10.3. Context Compaction

Cuando el número de tokens supera un umbral dinámico (ratio de la context window del modelo de respuesta), se genera un resumen LLM. Los identificadores críticos (UUIDs, URLs, emails) se preservan. Ratio de ahorro: ~60 % por compactación. Comando `/resume` para activación manual.

### 10.4. Checkpointing PostgreSQL

State completo checkpointeado después de cada nodo. P95 save < 50 ms, P95 load < 100 ms, tamaño medio ~15 KB/conversación.

---

## 11. Sistema de memoria y perfil psicológico

### 11.1. Arquitectura

```
AsyncPostgresStore + Semantic Index (pgvector)
├── Namespace: (user_id, "memories")        → Perfil psicológico
├── Namespace: (user_id, "documents", src)  → RAG documental
└── Namespace: (user_id, "context", domain) → Contexto herramientas (Data Registry)
```

### 11.2. Esquema de memoria enriquecido

Cada recuerdo es un documento estructurado con:
- `content`, `category` (preferencia, hecho, personalidad, relación, sensibilidad...)
- `importance` (1-10), `emotional_weight` (-10 a +10)
- `usage_nuance`: cómo utilizar esta información de manera benevolente
- Embedding `text-embedding-3-small` (1536d) via pgvector HNSW

**¿Por qué un peso emocional?** Un asistente que sabe que su madre está enferma pero trata ese hecho como cualquier otro dato es, en el mejor de los casos, torpe y, en el peor, hiriente. El peso emocional permite activar la `DANGER_DIRECTIVE` (prohibición de bromear, minimizar, comparar, banalizar) cuando se toca un tema sensible.

### 11.3. Extracción e inyección

**Extracción**: después de cada conversación, un proceso en background analiza el último mensaje del usuario, adaptado a la personalidad activa. Coste seguido via `TrackingContext`.

**Inyección**: el middleware `memory_injection.py` busca las memorias semánticamente cercanas, construye el perfil psicológico inyectable y activa la `DANGER_DIRECTIVE` si es necesario. Inyección en el prompt del sistema del Response Node.

### 11.4. Búsqueda híbrida BM25 + semántica

Combinación con alpha configurable (por defecto 0.6 semántica / 0.4 BM25). Boost del 10 % cuando ambas señales son fuertes (> 0.5). Fallback gracioso hacia semántica sola si BM25 falla. Rendimiento: 40-90 ms con caché.

### 11.5. Cuadernos de bitácora (Journals)

El asistente mantiene reflexiones introspectivas en cuatro temas (auto-reflexión, observaciones del usuario, ideas/análisis, aprendizajes). Dos desencadenantes: extracción post-conversación + consolidación periódica (4h). Embeddings OpenAI 1536d con `search_hints` (palabras clave LLM en el vocabulario del usuario). Inyección en el prompt del **Response Node y del Planner Node** — este último utiliza `intelligence.original_query` como consulta semántica.

Anti-alucinación UUID: `field_validator`, tabla de referencia de IDs, filtrado por IDs conocidos en extracción y consolidación.

### 11.6. Sistema de intereses

Detección por análisis de las peticiones con evolución bayesiana de los pesos (decay 0.01/día). Notificaciones proactivas multi-fuente (Wikipedia, Perplexity, LLM). Feedback del usuario (thumbs up/down/block) ajusta los pesos.

---

## 12. Infraestructura LLM multi-provider

### 12.1. Factory Pattern

```python
llm = get_llm(provider="openai", model="gpt-5.4", temperature=0.7, streaming=True)
```

El `get_llm()` resuelve la configuración efectiva via `get_llm_config_for_agent(settings, agent_type)` (code defaults → DB admin overrides), instancia el modelo y aplica los adaptadores específicos.

### 12.2. 34 tipos de configuración LLM

Cada nodo del pipeline es configurable independientemente via la Admin UI — sin redespliegue:

| Categoría | Tipos configurables |
|-----------|-------------------|
| Pipeline | router, query_analyzer, planner, semantic_validator, context_resolver |
| Respuesta | response, hitl_question_generator |
| Background | memory_extraction, interest_extraction, journal_extraction, journal_consolidation |
| Agentes | contacts_agent, emails_agent, calendar_agent, browser_agent, etc. |

### 12.3. Token Tracking

El `TrackingContext` sigue cada llamada LLM con `call_type` ("chat"/"embedding"), `sequence` (contador monótono), `duration_ms`, tokens (input/output/cache), y coste calculado desde las tarifas DB. Los trackers comparten un `run_id` para la agregación. El debug panel muestra todas las invocaciones (pipeline + background tasks) en una vista unificada cronológica.

---

## 13. Conectores: abstracción multi-proveedor

### 13.1. Arquitectura por protocolos

```
ConnectorTool (base.py) → ClientRegistry → resolve_client(type) → Protocol
     ├── GoogleGmailClient       implements EmailClientProtocol
     ├── MicrosoftOutlookClient  implements EmailClientProtocol
     ├── AppleEmailClient        implements EmailClientProtocol
     └── PhilipsHueClient        implements SmartHomeClientProtocol
```

**¿Por qué protocolos Python?** El duck typing estructural permite agregar un nuevo provider sin modificar el código invocante. El `ProviderResolver` garantiza que un solo proveedor esté activo por categoría funcional.

### 13.2. Normalizers

Cada provider devuelve datos en su propio formato. Normalizers dedicados (`calendar_normalizer`, `contacts_normalizer`, `email_normalizer`, `tasks_normalizer`) convierten las respuestas específicas de cada provider en modelos de dominio unificados. Agregar un nuevo provider solo requiere implementar el protocolo y su normalizer — el código de llamada permanece sin cambios.

### 13.3. Patrones reutilizables

`BaseOAuthClient` (template method con 3 hooks), `BaseGoogleClient` (paginación via pageToken), `BaseMicrosoftClient` (OData). Circuit breaker, rate limiting Redis distribuido, refresh token con double-check pattern y Redis locking contra el thundering herd.

---

## 14. MCP: Model Context Protocol

### 14.1. Arquitectura

El `MCPClientManager` gestiona el lifecycle de las conexiones (exit stacks), el descubrimiento de herramientas (`session.list_tools()`), y la generación automática de descripción de dominio por LLM. El `ToolAdapter` normaliza las herramientas MCP hacia el formato LangChain `@tool`, con parsing estructurado de las respuestas JSON en items individuales.

### 14.2. Seguridad MCP

HTTPS obligatorio, prevención SSRF (resolución DNS + blocklist IP), cifrado Fernet de credentials, OAuth 2.1 (DCR + PKCE S256), rate limiting Redis por servidor/herramienta, API guard 403 en endpoints proxy para servidores desactivados (ADR-061 Layer 3).

### 14.3. MCP Iterative Mode (ReAct)

Los servidores MCP con `iterative_mode: true` utilizan un agente ReAct dedicado (bucle observe/think/act) en lugar del planner estático. El agente lee primero la documentación del servidor, comprende el formato esperado y luego llama a las herramientas con los parámetros correctos. Particularmente eficaz para servidores con API compleja (ej.: Excalidraw). Activable por servidor en la configuración admin o de usuario. Alimentado por el `ReactSubAgentRunner` genérico (compartido con el browser agent).

---

## 15. Sistema de voz (STT/TTS)

### 15.1. STT

Wake word ("OK Guy") via Sherpa-onnx WASM en el navegador (cero envío externo). Transcripción Whisper Small (99+ idiomas, offline) en el backend via ThreadPoolExecutor. Per-user STT language con caché thread-safe de `OfflineRecognizer` por idioma.

**Optimizaciones de latencia**: reutilización del flujo micro KWS → grabación (~200-800 ms ahorrados), pre-conexión WebSocket, `getUserMedia` + WS paralelizados via `Promise.allSettled`, caché Worklet AudioWorklet.

### 15.2. TTS

Factory pattern: `TTSFactory.create(mode)` con fallback automático HD → Standard. Standard = Edge TTS (gratuito), HD = OpenAI TTS o Gemini TTS (premium).

---

## 16. Proactividad: Heartbeat y acciones planificadas

### 16.1. Heartbeat: arquitectura en 2 fases

**Fase 1 — Decisión** (coste-efectiva, gpt-4.1-mini):
1. `EligibilityChecker`: opt-in, ventana horaria, cooldown (2h global, 30 min por tipo), actividad reciente
2. `ContextAggregator`: 7 fuentes en paralelo (`asyncio.gather`): Calendar, Weather (detección de cambios), Tasks, Emails, Interests, Memories, Journals
3. LLM structured output: `skip` | `notify` con anti-redundancia (historial reciente inyectado)

**Fase 2 — Generación** (si notify): LLM reescribe con personalidad + idioma del usuario. Dispatch multi-canal.

### 16.2. Agent Initiative (ADR-062)

Nodo LangGraph post-ejecución: después de cada turno accionable, la iniciativa analiza los resultados y verifica proactivamente la información cross-domain (read-only). Ejemplos: clima lluvia → verificar calendario para actividades al aire libre, email mencionando una cita → verificar disponibilidad, tarea con deadline → recordar el contexto. 100% prompt-driven (sin lógica hardcoded), pre-filtro estructural (dominios adyacentes), inyección de memoria + centros de interés, campo sugerencia para proponer acciones write. Configurable via `INITIATIVE_ENABLED`, `INITIATIVE_MAX_ITERATIONS`, `INITIATIVE_MAX_ACTIONS`.

### 16.3. Acciones planificadas

APScheduler con leader election Redis (SETNX, TTL 120s, recheck 5s). `FOR UPDATE SKIP LOCKED` para aislamiento. Auto-approve de planes (`plan_approved=True` inyectado en el state). Auto-disable después de 5 fallos consecutivos. Retry en errores transitorios.

---

## 17. RAG Spaces y búsqueda híbrida

### 17.1. Pipeline

Upload → Chunking → Embedding (text-embedding-3-small, 1536d) → pgvector HNSW → Búsqueda híbrida (cosine + BM25 con alpha fusion) → Inyección de contexto en el **Response Node**.

Nota: la inyección RAG se realiza en el nodo de respuesta, no en el planificador. El planner recibe en cambio la inyección de los diarios personales via `build_journal_context()`.

### 17.2. System RAG Spaces (ADR-058)

FAQ integrada (119+ Q/A, 17 secciones) indexada desde `docs/knowledge/`. Detección `is_app_help_query` por QueryAnalyzer, Rule 0 override en RoutingDecider, App Identity Prompt (~200 tokens, lazy loading). SHA-256 staleness detection, auto-indexación al arranque.

---

## 18. Browser Control y Web Fetch

### 18.1. Web Fetch

URL → validación SSRF (DNS + IP blocklist + post-redirect recheck) → readability extraction (fallback full page) → HTML cleaning → Markdown → wrapping `<external_content>` (prevención prompt injection). Caché Redis 10 min.

### 18.2. Browser Control (ADR-059)

Agente ReAct autónomo (Playwright Chromium headless). Session pool Redis-backed con recovery cross-worker. CDP accessibility tree para interacción por elementos. Anti-detección (Chrome UA, webdriver flag remove, locale/timezone dinámicos). Cookie banner auto-dismiss (20+ selectores multilingües). Rate limiting separado read/write (40 cada uno por sesión).

---

## 19. Seguridad: defence in depth

### 19.1. Autenticación BFF (ADR-002)

**¿Por qué BFF en lugar de JWT?** JWT en localStorage = vulnerable a XSS, tamaño 90 % de overhead, revocación imposible. El pattern BFF con HTTP-only cookies + sesiones Redis elimina estos tres problemas. Migración v0.3.0: memoria -90 % (1.2 MB → 120 KB), session lookup P95 < 5 ms, score OWASP B+ → A.

### 19.2. Usage Limits: 5-layer defence in depth

| Capa | Punto de intercepción | ¿Por qué esta capa? |
|--------|---------------------|-----------------------|
| Layer 0 | Chat router (HTTP 429) | Bloquear antes incluso del stream SSE |
| Layer 1 | Agent service (SSE error) | Cubrir las scheduled actions que evitan el router |
| Layer 2 | `invoke_with_instrumentation()` | Guard centralizado que cubre todos los servicios background |
| Layer 3 | Proactive runner | Skip para usuarios bloqueados |
| Layer 4 | Migración `.ainvoke()` directa | Cobertura de las llamadas no centralizadas |

Diseño **fail-open**: los fallos de infraestructura no bloquean a los usuarios.

### 19.3. Prevención de ataques

| Vector | Protección |
|---------|------------|
| XSS | HTTP-only cookies, CSP |
| CSRF | SameSite=Lax |
| SQL Injection | SQLAlchemy ORM (consultas parametrizadas) |
| SSRF | DNS resolution + IP blocklist (Web Fetch, MCP, Browser) |
| Prompt Injection | `<external_content>` safety markers |
| Rate Limiting | Redis sliding window distribuido (Lua atómico) |
| Supply Chain | SHA-pinned GitHub Actions, Dependabot weekly |

---

## 20. Observabilidad y monitoreo

### 20.1. Stack

| Tecnología | Rol |
|-------------|------|
| Prometheus | 350+ métricas custom (RED pattern) |
| Grafana | 18 dashboards production-ready |
| Loki | Logs estructurados JSON agregados |
| Tempo | Trazas distribuidas cross-service (OTLP gRPC) |
| Langfuse | LLM-specific tracing (prompt versions, token usage) |
| structlog | Logging estructurado con PII filtering |

### 20.2. Debug Panel integrado

El debug panel en la interfaz de chat proporciona una introspección en tiempo real por conversación: intent analysis, execution pipeline, LLM pipeline (reconciliación cronológica de todas las llamadas LLM + embedding), contexto/memoria, intelligence (cache hits, pattern learning), diarios (inyección + extracción background), lifecycle timing.

Las métricas debug persisten en `sessionStorage` (50 entradas máx.).

**¿Por qué un debug panel en la UI?** En un ecosistema donde los agentes IA son notoriamente difíciles de depurar (comportamiento no determinista, cadenas de llamadas opacas), hacer las métricas accesibles directamente en la interfaz elimina la fricción de tener que abrir Grafana o leer logs. El operador ve inmediatamente por qué una petición costó caro o por qué el router eligió tal dominio.

---

## 21. Rendimiento: optimizaciones y métricas

### 21.1. Métricas clave (P95)

| Métrica | Valor | SLO |
|----------|--------|-----|
| API Latency | 450 ms | < 500 ms |
| TTFT (Time To First Token) | 380 ms | < 500 ms |
| Router Latency | 800 ms | < 2 s |
| Planner Latency | 2.5 s | < 5 s |
| E5 Embedding (local) | ~50 ms | < 100 ms |
| Checkpoint save | < 50 ms | P95 |
| Redis session lookup | < 5 ms | P95 |

### 21.2. Optimizaciones implementadas

| Optimización | Ganancia medida | Compromiso |
|-------------|-------------|-----------|
| Message Windowing | -50 % latencia, -77 % coste | Pérdida de contexto antiguo (compensado por Data Registry) |
| Smart Catalogue | 96 % reducción tokens | Panic mode necesario si filtrado demasiado agresivo |
| Pattern Learning | 89 % ahorros LLM | Inicialización requerida (golden patterns) |
| Prompt Caching | 90 % descuento | Depende del soporte del provider |
| Local Embeddings | Coste API cero | ~470 MB memoria, 9s carga inicial |
| Parallel Execution | Latencia = max(etapas) | Complejidad de gestión de dependencias |
| Context Compaction | ~60 % por compactación | Pérdida de información (atenuada por preservación de IDs) |

---

## 22. CI/CD y calidad

### 22.1. Pipeline

```
Pre-commit (local)                GitHub Actions CI
========================          =========================
.bak files check                  Lint Backend (Ruff + Black + MyPy strict)
Secrets grep                      Lint Frontend (ESLint + TypeScript)
Ruff + Black + MyPy               Unit tests + coverage (43 %)
Unit tests rápidos                Code Hygiene (i18n, Alembic, .env.example)
Detección patterns críticos       Docker build smoke test
Sync claves i18n                  Secret scan (Gitleaks)
Conflictos migración Alembic      ─────────────────────────
Completitud .env.example          Security workflow (semanal)
ESLint + TypeScript check           CodeQL (Python + JS)
                                    pip-audit + pnpm audit
                                    Trivy filesystem scan
                                    SBOM generation
```

### 22.2. Estándares

| Aspecto | Herramienta | Configuración |
|--------|-------|---------------|
| Formateo Python | Black | line-length=100 |
| Linting Python | Ruff | E, W, F, I, B, C4, UP |
| Type checking | MyPy | strict mode |
| Commits | Conventional Commits | `feat(scope):`, `fix(scope):` |
| Tests | pytest | `asyncio_mode = "auto"` |
| Coverage | 43 % mínimo | Aplicado en CI |

---

## 23. Patrones de ingeniería transversales

### 23.1. Sistema de Tools: arquitectura de 5 capas

El sistema de tools está construido en cinco capas componibles, reduciendo el boilerplate por tool de ~150 líneas a ~8 líneas (reducción del 94 %):

| Capa | Componente | Rol |
|------|-----------|-----|
| 1 | `ConnectorTool[ClientType]` | Base genérica: OAuth auto-refresh, caché de cliente, inyección de dependencias |
| 2 | `@connector_tool` | Meta-decorador componiendo `@tool` + métricas + rate limiting + guardado de contexto |
| 3 | Formatters | `ContactFormatter`, `EmailFormatter`... — normalización de resultados por dominio |
| 4 | `ToolManifest` + Builder | Declaración declarativa: params, salidas, coste, permisos, keywords semánticas |
| 5 | Catalogue Loader | Introspección dinámica, generación de manifiestos, agrupación por dominio |

Los límites de frecuencia son por categoría: Read (20/min), Write (5/min), Expensive (2/5 min). Los tools pueden producir un string (legacy) o un `UnifiedToolOutput` estructurado (modo Data Registry).

### 23.2. Data Registry

El Data Registry (`InMemoryStore`) desacopla los resultados de los tools del historial de mensajes. Los resultados se almacenan por solicitud vía `@auto_save_context` y sobreviven al windowing de mensajes — esto es lo que hace viable el windowing agresivo por nodo (5/10/20 turnos) sin perder el contexto de las salidas de tools. Las referencias entre pasos (`$steps.X.field`) resuelven contra el registry, no contra los mensajes.

### 23.3. Arquitectura de Errores

Todos los tools devuelven `ToolResponse` (éxito) o `ToolErrorModel` (fallo) con un enum `ToolErrorCode` (18+ tipos: INVALID_INPUT, RATE_LIMIT_EXCEEDED, TEMPLATE_EVALUATION_FAILED...) y un flag `recoverability`. En el lado API, raisers de excepciones centralizados (`raise_user_not_found`, `raise_permission_denied`...) reemplazan las HTTPException crudas en todas partes — asegurando contratos de error consistentes.

### 23.4. Sistema de Prompts

57 archivos `.txt` versionados en `src/domains/agents/prompts/v1/`, cargados vía `load_prompt()` con caché LRU (32 entradas). Versiones configurables por variables de entorno.

### 23.5. Activación Centralizada de Componentes (ADR-061)

Sistema de 3 capas que resuelve un problema de duplicación: antes del ADR-061, el filtrado de componentes activados/desactivados estaba disperso en 7+ sitios. Ahora:

| Capa | Mecanismo |
|------|-----------|
| Capa 1 | Gate-keeper de dominio: valida dominios LLM contra `available_domains` |
| Capa 2 | `request_tool_manifests_ctx`: ContextVar construido una vez por solicitud |
| Capa 3 | Guard API 403 en endpoints proxy MCP |

### 23.6. Feature Flags

Cada subsistema opcional está controlado por un flag `{FEATURE}_ENABLED`, verificado al inicio (registro del scheduler), al cableado de rutas y a la entrada de nodos (cortocircuito instantáneo). Esto permite desplegar el codebase completo mientras se activan los subsistemas progresivamente.

---

## 24. Arquitectura de decisiones (ADR)

59 ADRs en formato MADR documentan las decisiones arquitecturales mayores. Algunos ejemplos representativos:

| ADR | Decisión | Problema resuelto | Impacto medido |
|-----|----------|----------------|---------------|
| 001 | LangGraph para orquestación | Necesidad de state persistence + interrupts HITL | Checkpoints P95 < 50 ms |
| 002 | BFF Pattern (JWT → Redis) | JWT vulnerable a XSS, revocación imposible | Memoria -90 %, OWASP A |
| 003 | Filtrado dinámico por dominio | 10x prompt size = 10x coste | 73-83 % reducción catálogo |
| 005 | Filtrado ANTES de asyncio.gather | Plan + fallback ejecutados en paralelo = 2x coste | -50 % coste planes fallback |
| 007 | Message Windowing por nodo | Conversaciones largas = 100k+ tokens | -50 % latencia, -77 % coste |
| 048 | Semantic Tool Router | Enrutamiento LLM impreciso en multi-dominio | +48 % precisión |
| 049 | Local E5 Embeddings | Coste embeddings API + latencia de red | Coste cero, 50 ms local |
| 057 | Personal Journals | Sin continuidad de reflexión entre sesiones | Inyección planner + response |
| 061 | Centralized Component Activation | 7+ sitios de filtrado duplicados | Fuente única, 3 capas |

---

## 25. Potencial de evolución y extensibilidad

### 25.1. Puntos de extensión

| Extensión | Interfaz | Documentación |
|-----------|-----------|---------------|
| Nuevo conector | `OAuthProvider` Protocol + Client Protocol | `GUIDE_CONNECTOR_IMPLEMENTATION.md` + checklist |
| Nuevo agente | `register_agent()` + ToolManifest | `GUIDE_AGENT_CREATION.md` |
| Nueva herramienta | `@tool` + ToolResponse/ToolErrorModel | `GUIDE_TOOL_CREATION.md` |
| Nuevo canal | `BaseChannelSender` + `BaseChannelWebhookHandler` | `NEW_CHANNEL_CHECKLIST.md` |
| Nuevo provider LLM | Adaptador + model profiles | Factory extensible |
| Nueva tarea proactiva | `ProactiveTask` Protocol | `NEW_PROACTIVE_TASK_CHECKLIST.md` |

### 25.2. Escalabilidad

| Dimensión | Estrategia actual | Evolución posible |
|-----------|-------------------|-------------------|
| Horizontal | 4 uvicorn workers + leader election Redis | Kubernetes + HPA |
| Datos | PostgreSQL + pgvector | Sharding, read replicas |
| Caché | Redis single instance | Redis Cluster |
| Observabilidad | Stack completo integrado | Managed Grafana Cloud |

---

## Conclusión

LIA es un ejercicio de ingeniería de software que intenta resolver un problema concreto: construir un asistente IA multi-agente de calidad producción, transparente, seguro y extensible, capaz de funcionar en un Raspberry Pi.

Los 59 ADRs documentan no solo las decisiones tomadas sino también las alternativas rechazadas y los compromisos aceptados. Los 2 300+ tests, el CI/CD completo y el MyPy strict no son métricas de vanidad — son los mecanismos que permiten hacer evolucionar un sistema de esta complejidad sin regresión.

La imbricación de los subsistemas — memoria psicológica, aprendizaje bayesiano, enrutamiento semántico, HITL sistemático, proactividad LLM-driven, diarios introspectivos — crea un sistema donde cada componente refuerza a los demás. El HITL alimenta el pattern learning, que reduce los costes, que permiten más funcionalidades, que generan más datos para la memoria, que mejora las respuestas. Es un círculo virtuoso por diseño, no por accidente.

---

*Documento redactado sobre la base del análisis del código fuente (`apps/api/src/`, `apps/web/src/`), de la documentación técnica (190+ documentos), de los 63 ADRs y del changelog (v1.0 a v1.11.5). Todas las métricas, versiones y patrones citados son verificables en el codebase.*
