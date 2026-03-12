# ADR-020: Triple-Layer Observability Stack

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Deciders**: Équipe architecture LIA
**Technical Story**: Phase 6 - Production-Ready Observability
**Related Documentation**: `docs/technical/OBSERVABILITY.md`

---

## Context and Problem Statement

L'application LLM-based nécessitait une observabilité complète à plusieurs niveaux :

1. **Métriques temps réel** : Latence, tokens, coûts, erreurs
2. **Distributed Tracing** : Traçabilité requêtes multi-services
3. **LLM-Specific** : Prompts, completions, évaluations, A/B testing

**Problème** : Aucun outil unique ne couvre tous ces besoins.

**Question** : Comment implémenter une observabilité complète sans créer un single point of failure ?

---

## Decision Drivers

### Must-Have (Non-Negotiable):

1. **Independence** : Chaque layer fonctionne indépendamment
2. **Graceful Degradation** : App continue si un layer tombe
3. **Low Overhead** : < 5% latency impact
4. **LLM-Specific** : Token tracking, prompt versioning, evaluation scores

### Nice-to-Have:

- Exemplars linking (Prometheus → Tempo)
- Dashboard auto-generated
- Subgraph tracing hierarchy

---

## Decision Outcome

**Chosen option**: "**Triple-Layer Stack: Prometheus + OpenTelemetry + Langfuse**"

### Architecture Overview

```mermaid
graph TB
    subgraph "LAYER 1: PROMETHEUS"
        PM[PrometheusMiddleware] --> M1[http_requests_total]
        PM --> M2[http_request_duration_seconds]
        MA[MetricsAgents] --> M3[llm_tokens_consumed_total]
        MA --> M4[llm_cost_total]
        MA --> M5[llm_api_latency_seconds]
        ML[MetricsLangfuse] --> M6[langfuse_trace_depth]
        ML --> M7[langfuse_agent_handoffs]
    end

    subgraph "LAYER 2: OPENTELEMETRY"
        FI[FastAPIInstrumentor] --> SP[HTTP Spans]
        TN[@trace_node decorator] --> NS[Node Spans]
        NS --> ATTR[Attributes:<br/>node_name, model, run_id]
        SP --> OTLP[OTLP Exporter]
        NS --> OTLP
        OTLP --> TEMPO[Tempo Backend]
    end

    subgraph "LAYER 3: LANGFUSE"
        CF[CallbackFactory] --> CH[CallbackHandler<br/>Singleton]
        CH --> TR[Traces:<br/>prompt, completion, tokens]
        CH --> EV[Evaluations:<br/>relevance, hallucination]
        CH --> PV[Prompt Versions]
        CH --> SS[Session/User Context]
    end

    subgraph "INTEGRATION"
        REQ[HTTP Request] --> PM
        REQ --> FI
        REQ --> GRAPH[LangGraph Execution]
        GRAPH --> TN
        GRAPH --> CH
    end

    style PM fill:#E91E63,stroke:#880E4F,color:#fff
    style FI fill:#9C27B0,stroke:#4A148C,color:#fff
    style CF fill:#4CAF50,stroke:#2E7D32,color:#fff
```

### Layer 1: Prometheus Metrics

```python
# apps/api/src/infrastructure/observability/metrics.py

# HTTP Metrics
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
)

class PrometheusMiddleware(BaseHTTPMiddleware):
    """Middleware to collect Prometheus metrics for HTTP requests."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path == "/metrics":
            return await call_next(request)

        method = request.method
        endpoint = request.url.path

        http_requests_in_progress.labels(method=method, endpoint=endpoint).inc()

        try:
            with http_request_duration_seconds.labels(
                method=method, endpoint=endpoint
            ).time():
                response = await call_next(request)

            http_requests_total.labels(
                method=method, endpoint=endpoint, status=response.status_code
            ).inc()

            return response
        finally:
            http_requests_in_progress.labels(method=method, endpoint=endpoint).dec()
```

### LLM-Specific Metrics

```python
# apps/api/src/infrastructure/observability/metrics_agents.py

llm_tokens_consumed_total = Counter(
    "llm_tokens_consumed_total",
    "Total tokens consumed by LLM calls",
    ["model", "node", "provider"],
)

llm_api_latency_seconds = Histogram(
    "llm_api_latency_seconds",
    "LLM API call latency in seconds",
    ["model", "node"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
)

llm_cost_total = Counter(
    "llm_cost_total",
    "Total estimated cost of LLM calls in USD",
    ["model", "node"],
)
```

### Langfuse-Specific Metrics

```python
# apps/api/src/infrastructure/observability/metrics_langfuse.py

# Prompt Versioning (Phase 3.1.2)
langfuse_prompt_version_usage = Counter(
    "langfuse_prompt_version_usage",
    "Prompt version usage from PromptRegistry",
    ["prompt_id", "version"],
)

# Evaluation Scores (Phase 3.1.3)
langfuse_evaluation_score = Histogram(
    "langfuse_evaluation_score",
    "LLM output evaluation scores",
    ["metric_name"],
    buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)

# Multi-Agent Handoff (Phase 3.1.5.3)
langfuse_agent_handoffs = Counter(
    "langfuse_agent_handoffs",
    "Agent handoff transitions",
    ["source_agent", "target_agent"],
)

# Total: ~173 Prometheus series (low cardinality)
```

### Layer 2: OpenTelemetry

```python
# apps/api/src/infrastructure/observability/tracing.py

def configure_tracing(app: FastAPI) -> None:
    """Configure OpenTelemetry tracing for FastAPI application."""

    # Create resource with service information
    resource = Resource.create({
        "service.name": settings.otel_service_name,
        "service.version": "0.1.0",
        "deployment.environment": settings.environment,
    })

    # Create tracer provider
    tracer_provider = TracerProvider(resource=resource)

    # Create OTLP exporter (exports to Tempo)
    otlp_exporter = OTLPSpanExporter(
        endpoint=settings.otel_exporter_otlp_endpoint,
        insecure=not settings.is_production,
    )

    # Add batch span processor for efficiency
    tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

    # Set global tracer provider
    trace.set_tracer_provider(tracer_provider)

    # Instrument FastAPI automatically
    FastAPIInstrumentor.instrument_app(app, excluded_urls=excluded)


def trace_node(node_name: str, llm_model: str | None = None) -> Callable:
    """Decorator for tracing LangGraph nodes with OpenTelemetry."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            tracer = trace.get_tracer(__name__)

            with tracer.start_as_current_span(f"langgraph.node.{node_name}") as span:
                span.set_attribute("langgraph.node.name", node_name)

                if llm_model:
                    span.set_attribute("langgraph.llm.model", llm_model)

                try:
                    result = await func(*args, **kwargs)
                    return result
                except Exception as e:
                    span.set_attribute("error", True)
                    span.set_attribute("error.type", type(e).__name__)
                    raise

        return wrapper
    return decorator
```

### Layer 3: Langfuse (LLM Observability)

```python
# apps/api/src/infrastructure/llm/callback_factory.py

class CallbackFactory:
    """
    Production-grade factory for Langfuse callbacks.

    SDK v3.9+ Best Practice: Singleton handler for application lifetime.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._enabled = settings.langfuse_enabled
        self._handler: Any | None = None

        if not self._enabled:
            return

        # Export configuration to environment (Langfuse SDK reads from os.environ)
        self._export_config_to_environment()

        # Initialize singleton CallbackHandler
        self._initialize_handler()

    def _initialize_handler(self) -> None:
        """Initialize singleton CallbackHandler for application lifetime."""
        from langfuse.langchain import CallbackHandler
        self._handler = CallbackHandler()  # Reads config from os.environ

    def create_callbacks(self) -> list[Any]:
        """Return singleton handler (no parameters in v3.9+)."""
        if not self._enabled or not self._handler:
            return []
        return [self._handler]

    def flush(self) -> None:
        """Flush all pending traces to Langfuse server."""
        if self._handler and hasattr(self._handler, "client"):
            self._handler.client.flush()
```

### RunnableConfig-Based Instrumentation

```python
# apps/api/src/infrastructure/llm/instrumentation.py

def create_instrumented_config(
    llm_type: str,
    session_id: str | None = None,
    user_id: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    trace_name: str | None = None,
    subgraph_name: str | None = None,
    depth: int = 0,
    base_config: RunnableConfig | None = None,
) -> RunnableConfig:
    """
    Create instrumented RunnableConfig with Langfuse callbacks.

    2025 Best Practice: Metadata-driven context propagation.
    """
    config: RunnableConfig = dict(base_config) if base_config else {}

    # Auto-enrich metadata with observability context
    enriched_metadata = {
        "llm_type": llm_type,
        "langfuse_session_id": session_id,
        "langfuse_user_id": user_id,
        "langfuse_tags": tags or [llm_type],
        "langfuse_trace_name": trace_name or f"{llm_type}_call",
        "langfuse_trace_depth": depth,
        **(metadata or {}),
    }

    if subgraph_name:
        enriched_metadata["langfuse_subgraph_name"] = subgraph_name

    config["metadata"] = enriched_metadata

    # Get callbacks from factory
    factory = get_callback_factory()
    if factory and factory.is_enabled():
        callbacks = factory.create_callbacks()
        config["callbacks"] = callbacks

    return config


def create_subgraph_config(
    llm_type: str,
    parent_config: RunnableConfig,
    subgraph_name: str,
) -> RunnableConfig:
    """
    Create config for subgraph with automatic parent trace context propagation.

    Increments depth and propagates session_id, user_id, trace_id.
    """
    parent_metadata = parent_config.get("metadata", {})
    parent_depth = parent_metadata.get("langfuse_trace_depth", 0)

    return create_instrumented_config(
        llm_type=llm_type,
        session_id=parent_metadata.get("langfuse_session_id"),
        user_id=parent_metadata.get("langfuse_user_id"),
        subgraph_name=subgraph_name,
        depth=parent_depth + 1,
        base_config=parent_config,
    )
```

### Configuration

```python
# apps/api/src/core/config/observability.py

class ObservabilitySettings(BaseSettings):
    # Prometheus
    prometheus_metrics_port: int = Field(default=9090)

    # OpenTelemetry
    otel_exporter_otlp_endpoint: str = Field(default="http://localhost:4317")
    otel_service_name: str = Field(default="lia-api")

    # Langfuse - LLM Observability
    langfuse_enabled: bool = Field(default=True)
    langfuse_host: str = Field(default="http://langfuse-web:3000")
    langfuse_public_key: str = Field(default="")
    langfuse_secret_key: str = Field(default="")
    langfuse_release: str = Field(default="development")
    langfuse_sample_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    langfuse_flush_interval: int = Field(default=5, ge=1)
```

### Request Flow Integration

```
HTTP Request
    │
    ├─→ PrometheusMiddleware (Layer 1)
    │   └─→ http_requests_total++, duration tracking
    │
    ├─→ FastAPIInstrumentor (Layer 2)
    │   └─→ Creates HTTP span with attributes
    │
    └─→ LangGraph Execution
        │
        ├─→ Router Node
        │   ├─→ @trace_node("router") → OTEL span
        │   └─→ LLM.invoke(config=create_instrumented_config(...))
        │       ├─→ Langfuse captures: prompt, completion, tokens
        │       └─→ MetricsCallback: llm_tokens_consumed_total++
        │
        ├─→ Planner Node (similar flow)
        │
        └─→ Subgraph Invocation
            └─→ create_subgraph_config(parent_config)
                └─→ Hierarchical trace: Parent → Child (depth+1)
```

### Consequences

**Positive**:
- ✅ **Independent Layers** : Chaque layer fonctionne seul
- ✅ **Graceful Degradation** : App continue si Langfuse/Tempo down
- ✅ **Low Cardinality** : ~173 Prometheus series (Grafana-friendly)
- ✅ **Subgraph Hierarchy** : Trace depth tracking for nested agents
- ✅ **Cost Tracking** : Token + USD estimation per call
- ✅ **Singleton Pattern** : Efficient callback handler reuse

**Negative**:
- ⚠️ Triple configuration (3 backends to maintain)
- ⚠️ Callback deduplication needed (Phase 2.1.3 fix)

---

## Validation

**Acceptance Criteria**:
- [x] ✅ Prometheus metrics avec PrometheusMiddleware
- [x] ✅ OpenTelemetry avec OTLP exporter + @trace_node
- [x] ✅ Langfuse CallbackFactory singleton pattern
- [x] ✅ create_instrumented_config avec metadata propagation
- [x] ✅ Subgraph tracing avec depth tracking
- [x] ✅ Graceful degradation si layer indisponible

---

## Monitoring Stack Endpoints

| Component | Endpoint | Port | Purpose |
|-----------|----------|------|---------|
| FastAPI Docs | `http://api:8000/docs` | 8000 | API documentation |
| Prometheus Metrics | `http://api:8000/metrics` | 8000 | Scrape endpoint |
| Prometheus UI | `http://prometheus:9090` | 9090 | Query metrics |
| Grafana | `http://grafana:3000` | 3000 | Dashboards |
| Tempo | `http://tempo:3200` | 3200 | Distributed traces |
| Langfuse | `http://langfuse-web:3000` | 3000 | LLM observability |

---

## References

### Source Code
- **PrometheusMiddleware**: `apps/api/src/infrastructure/observability/metrics.py`
- **OTEL Tracing**: `apps/api/src/infrastructure/observability/tracing.py`
- **Langfuse Factory**: `apps/api/src/infrastructure/llm/callback_factory.py`
- **Instrumentation**: `apps/api/src/infrastructure/llm/instrumentation.py`
- **Config**: `apps/api/src/core/config/observability.py`
- **Metrics Langfuse**: `apps/api/src/infrastructure/observability/metrics_langfuse.py`

---

**Fin de ADR-020** - Triple-Layer Observability Stack Decision Record.
