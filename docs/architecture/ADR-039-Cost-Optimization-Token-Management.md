# ADR-039: Cost Optimization & Token Management

**Status**: ✅ IMPLEMENTED (2025-12-28) - Enhanced by Architecture v3
**Deciders**: Équipe architecture LIA
**Technical Story**: LLM cost tracking, token management, and budget optimization
**Related Documentation**: `docs/technical/COST_MANAGEMENT.md`
**Related ADRs**: ADR-048 (Semantic Router)

> **Note Architecture v3 (2026-01)**: Les references a `router_node.py` et `planner_node.py` dans cet ADR concernent les fichiers v3 (`router_node_v3.py`, `planner_node_v3.py`).
> L'optimisation des tokens a ete poussee plus loin avec le `SmartCatalogueService` (89% token savings).
> Voir [SMART_SERVICES.md](../technical/SMART_SERVICES.md) pour la documentation actuelle.

---

## Context and Problem Statement

L'application LLM nécessitait une gestion rigoureuse des coûts :

1. **Token Counting** : Comptage précis par provider
2. **Cost Tracking** : Suivi temps réel USD/EUR
3. **Budget Management** : Alertes et limites de dépenses
4. **Cache Optimization** : Réduction appels API coûteux
5. **Catalogue Optimization** : Réduction du catalogue d'outils (40K → 4K tokens)

**Question** : Comment optimiser les coûts LLM tout en maintenant la qualité ?

---

## Decision Drivers

### Must-Have (Non-Negotiable):

1. **Multi-Provider Token Counting** : tiktoken + provider SDKs
2. **Real-Time Cost Metrics** : Prometheus `llm_cost_total`
3. **LLM Response Caching** : Redis pour température=0
4. **Progressive Token Reduction** : Fallback par seuils
5. **Semantic Domain/Tool Selection** : Filtrage intelligent du catalogue

### Nice-to-Have:

- Cost-based HITL triggers
- Historical pricing tracking
- Currency conversion (USD → EUR)

---

## Decision Outcome

**Chosen option**: "**Tiktoken + Redis Caching + Progressive Degradation + Prometheus Metrics**"

### Architecture Overview

```mermaid
graph TB
    subgraph "TOKEN COUNTING"
        TIKTOKEN[tiktoken<br/>o200k_base, cl100k_base]
        ANTHROPIC[Anthropic SDK<br/>count_tokens()]
        FALLBACK[Character Estimate<br/>~4 chars/token]
    end

    subgraph "COST TRACKING"
        PRICING[AsyncPricingService<br/>Database-backed]
        METRICS[Prometheus Metrics<br/>llm_cost_total, llm_tokens_consumed]
        CURRENCY[CurrencyExchangeRate<br/>USD → EUR daily sync]
    end

    subgraph "OPTIMIZATION"
        CACHE[Redis LLM Cache<br/>temperature=0 only]
        WINDOWING[Message Windowing<br/>Router:5, Planner:4, Response:20]
        DEGRADATION[Progressive Degradation<br/>Token thresholds]
    end

    subgraph "BUDGET CONTROL"
        HITL[CostThresholdStrategy<br/>$1.00 threshold]
        PROFILES[ModelProfile<br/>nano/mini/full tiers]
    end

    TIKTOKEN --> PRICING
    ANTHROPIC --> PRICING
    PRICING --> METRICS
    METRICS --> CURRENCY
    CACHE --> DEGRADATION
    WINDOWING --> DEGRADATION
    HITL --> PROFILES

    style CACHE fill:#4CAF50,stroke:#2E7D32,color:#fff
    style PRICING fill:#2196F3,stroke:#1565C0,color:#fff
    style DEGRADATION fill:#FF9800,stroke:#F57C00,color:#fff
```

### Token Counting Implementation

```python
# apps/api/src/infrastructure/llm/providers/token_counter.py

class TokenCounter(Protocol):
    def count_tokens(self, text: str) -> int: ...

class OpenAITokenCounter:
    """Uses tiktoken with model-specific encodings."""

    ENCODING_MAP = {
        "gpt-4.1": "o200k_base",
        "gpt-4.1-mini": "o200k_base",
        "gpt-4.1-nano": "o200k_base",
        "gpt-4": "cl100k_base",
        "gpt-3.5-turbo": "cl100k_base",
    }

    def __init__(self, model: str):
        encoding_name = self.ENCODING_MAP.get(model, "o200k_base")
        self.encoding = tiktoken.get_encoding(encoding_name)

    def count_tokens(self, text: str) -> int:
        return len(self.encoding.encode(text))

class AnthropicTokenCounter:
    """Uses official Anthropic SDK."""

    def __init__(self, client: Anthropic):
        self.client = client

    def count_tokens(self, text: str) -> int:
        return self.client.count_tokens(text)

class FallbackTokenCounter:
    """Character-based estimation (~4 chars per token)."""

    def count_tokens(self, text: str) -> int:
        return len(text) // 4
```

### Cost Tracking Metrics

```python
# apps/api/src/infrastructure/observability/metrics_agents.py

# Token consumption by model and node
llm_tokens_consumed_total = Counter(
    "llm_tokens_consumed_total",
    "Total tokens consumed",
    ["model", "node_name", "token_type"],  # prompt, completion, cached
)

# Cost in USD/EUR by model and node
llm_cost_total = Counter(
    "llm_cost_total",
    "Total LLM cost",
    ["model", "node_name", "currency"],  # usd, eur
)

# API call tracking
llm_api_calls_total = Counter(
    "llm_api_calls_total",
    "Total LLM API calls",
    ["model", "node_name", "status"],  # success, error
)

# Latency histogram
llm_api_latency_seconds = Histogram(
    "llm_api_latency_seconds",
    "LLM API latency",
    ["model", "node_name"],
    buckets=[0.5, 1, 2, 5, 10, 30, 60],
)
```

### Database-Backed Pricing

```python
# apps/api/src/domains/llm/pricing_service.py

class AsyncPricingService:
    """Pricing service with TTL caching."""

    def __init__(self, db: AsyncSession, cache_ttl_seconds: int = 3600):
        self.db = db
        self.cache_ttl = cache_ttl_seconds
        self._cache: dict[str, tuple[ModelPrice, float]] = {}

    async def get_active_model_price(self, model_name: str) -> ModelPrice | None:
        """Get current pricing for model (cached)."""
        normalized = self._normalize_model_name(model_name)

        # Check cache
        if normalized in self._cache:
            price, cached_at = self._cache[normalized]
            if time.time() - cached_at < self.cache_ttl:
                return price

        # Query database
        price = await self._query_price(normalized)
        if price:
            self._cache[normalized] = (price, time.time())
        return price

    async def calculate_token_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int = 0,
    ) -> tuple[Decimal, Decimal]:
        """Calculate cost in USD and EUR."""
        price = await self.get_active_model_price(model)
        if not price:
            return Decimal("0"), Decimal("0")

        cost_usd = (
            (Decimal(input_tokens) / 1_000_000) * price.input_price_per_1m_tokens
            + (Decimal(cached_tokens) / 1_000_000) * (price.cached_input_price_per_1m_tokens or price.input_price_per_1m_tokens * Decimal("0.5"))
            + (Decimal(output_tokens) / 1_000_000) * price.output_price_per_1m_tokens
        )

        exchange_rate = await self._get_exchange_rate("USD", "EUR")
        cost_eur = cost_usd * exchange_rate

        return cost_usd, cost_eur

    def _normalize_model_name(self, model: str) -> str:
        """Strip date suffixes: gpt-4.1-mini-2025-04-14 → gpt-4.1-mini"""
        return re.sub(r"-\d{4}-\d{2}-\d{2}$", "", model)
```

### LLM Response Caching

```python
# apps/api/src/infrastructure/cache/llm_cache.py

class LLMCache:
    """Redis-based LLM response cache (deterministic calls only)."""

    VERSION = "v2"
    DEFAULT_TTL = 300  # 5 minutes

    def __init__(self, redis: Redis, ttl: int = DEFAULT_TTL):
        self.redis = redis
        self.ttl = ttl

    async def get(self, func_name: str, args: tuple, kwargs: dict) -> str | None:
        """Get cached response if exists."""
        key = self._make_key(func_name, args, kwargs)
        cached = await self.redis.get(key)

        if cached:
            llm_cache_hits_total.labels(
                func_name=func_name,
                format_version=self.VERSION,
            ).inc()
            return self._deserialize(cached)

        llm_cache_misses_total.labels(func_name=func_name).inc()
        return None

    async def set(
        self,
        func_name: str,
        args: tuple,
        kwargs: dict,
        response: str,
        usage_metadata: dict | None = None,
    ) -> None:
        """Cache response with metadata."""
        key = self._make_key(func_name, args, kwargs)
        value = {
            "version": self.VERSION,
            "cached_at": datetime.utcnow().isoformat(),
            "response": response,
            "usage_metadata": usage_metadata,
        }
        await self.redis.setex(key, self.ttl, json.dumps(value))

    def _make_key(self, func_name: str, args: tuple, kwargs: dict) -> str:
        """SHA256 hash of function + arguments."""
        content = f"{func_name}:{args}:{sorted(kwargs.items())}"
        hash_value = hashlib.sha256(content.encode()).hexdigest()[:16]
        return f"llm_cache:{func_name}:{hash_value}"

# Decorator for easy caching
def cached_llm_call(ttl: int = 300):
    """Cache decorator for deterministic LLM calls (temperature=0)."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Only cache if temperature=0
            if kwargs.get("temperature", 1.0) != 0.0:
                return await func(*args, **kwargs)

            cache = get_llm_cache()
            cached = await cache.get(func.__name__, args, kwargs)
            if cached:
                return cached

            result = await func(*args, **kwargs)
            await cache.set(func.__name__, args, kwargs, result)
            return result
        return wrapper
    return decorator
```

### Progressive Token Degradation

```python
# apps/api/src/domains/agents/services/planner/catalogue_optimizer.py

# Token thresholds for progressive degradation
TOKEN_THRESHOLDS = {
    "SAFE": 80_000,      # 62% of 128k → Full catalogue
    "WARNING": 100_000,  # 78% of 128k → Filter to detected domains
    "CRITICAL": 110_000, # 86% of 128k → Reduce descriptions
    "MAX": 120_000,      # 94% of 128k → Emergency fallback
}

class CatalogueOptimizer:
    """Progressive catalogue degradation based on token count."""

    def get_optimized_catalogue(
        self,
        full_catalogue: list[ToolManifest],
        detected_domains: list[str],
        current_tokens: int,
    ) -> tuple[list[ToolManifest], str]:
        """Return optimized catalogue and fallback level."""

        if current_tokens < TOKEN_THRESHOLDS["SAFE"]:
            return full_catalogue, "full_catalogue"

        if current_tokens < TOKEN_THRESHOLDS["WARNING"]:
            filtered = [t for t in full_catalogue if t.domain in detected_domains]
            return filtered, "filtered_catalogue"

        if current_tokens < TOKEN_THRESHOLDS["CRITICAL"]:
            filtered = self._reduce_descriptions(full_catalogue, detected_domains)
            return filtered, "reduced_descriptions"

        if current_tokens < TOKEN_THRESHOLDS["MAX"]:
            primary = detected_domains[0] if detected_domains else "contacts"
            filtered = [t for t in full_catalogue if t.domain == primary]
            return filtered, "primary_domain_only"

        # Emergency: minimal tools
        return self._emergency_fallback(full_catalogue), "emergency_fallback"

    def _reduce_descriptions(
        self,
        catalogue: list[ToolManifest],
        domains: list[str],
    ) -> list[ToolManifest]:
        """Replace full descriptions with minimal summaries."""
        return [
            t.model_copy(update={"description": t.description[:100] + "..."})
            for t in catalogue
            if t.domain in domains
        ]
```

### Semantic Domain & Tool Selection (Primary Optimization)

**This is the most impactful optimization: 80-90% token reduction!**

```
BEFORE (Full Catalogue):
    11 domains × ~3.5K tokens/domain = ~40K tokens per request

AFTER (Two-Level Semantic Selection):
    Query: "mes derniers emails"

    Level 1 - SemanticDomainSelector:
        → emails (score: 0.92) ✓
        → contacts (score: 0.45) ✗
        → calendar (score: 0.32) ✗
        Result: 1 domain

    Level 2 - SemanticToolSelector:
        → search_emails_tool (score: 0.89) ✓
        → get_email_tool (score: 0.72) ✓
        → reply_email_tool (score: 0.58) ✗
        Result: 2 tools

    Token count: ~4K tokens (90% reduction!)
```

#### SemanticDomainSelector

```python
# apps/api/src/domains/agents/services/semantic_domain_selector.py

# Thresholds for domain selection
DEFAULT_DOMAIN_HARD_THRESHOLD = 0.75  # High confidence
DEFAULT_DOMAIN_SOFT_THRESHOLD = 0.65  # Medium confidence
DEFAULT_MAX_DOMAINS = 5

class SemanticDomainSelector:
    """
    Selects domains using OpenAI text-embedding-3-small with max-pooling.

    Key features:
    - Max-pooling: MAX(sim(query, keyword_i)) per domain
    - Double threshold: 0.75 (high) / 0.65 (medium)
    - OpenAI text-embedding-3-small (1536 dims)
    - Startup caching: all domain keyword embeddings cached once
    """

    async def select_domains(
        self,
        query: str,
        max_results: int = 5,
    ) -> DomainSelectionResult:
        """
        Select domains matching query via semantic similarity.

        Returns:
            DomainSelectionResult with selected domains, scores, and uncertainty flag
        """
        query_embedding = await self._embeddings.aembed_query(query)

        scores = {}
        for domain_name, keyword_embeddings in self._domain_keyword_embeddings.items():
            # Max-pooling: best keyword wins
            max_score = max(
                self._cosine_similarity(query_embedding, kw_emb)
                for kw_emb in keyword_embeddings
            )
            scores[domain_name] = max_score

        # Filter by threshold and sort
        selected = [
            DomainMatch(name=name, score=score, confidence="high" if score >= 0.75 else "medium")
            for name, score in sorted(scores.items(), key=lambda x: x[1], reverse=True)
            if score >= self._soft_threshold
        ][:max_results]

        return DomainSelectionResult(
            selected_domains=selected,
            has_uncertainty=any(d.confidence == "medium" for d in selected),
        )
```

#### SemanticToolSelector

```python
# apps/api/src/domains/agents/services/tool_selector.py

# Thresholds for tool selection (slightly lower than domains)
DEFAULT_HARD_THRESHOLD = 0.70  # High confidence
DEFAULT_SOFT_THRESHOLD = 0.60  # Medium confidence
DEFAULT_MAX_TOOLS = 8

class SemanticToolSelector:
    """
    Selects tools using OpenAI text-embedding-3-small with max-pooling.

    Key features:
    - Max-pooling: MAX(sim(query, keyword_i)) per tool
    - Double threshold: 0.70 (high) / 0.60 (medium)
    - OpenAI text-embedding-3-small (1536 dims)
    - Filters to tools within selected domains only
    """

    async def select_tools(
        self,
        query: str,
        available_tools: list[ToolManifest] | None = None,
        max_results: int = 8,
    ) -> ToolSelectionResult:
        """Select tools matching query within available tools."""
        # ... similar to domain selection but at tool level
```

#### Integration Flow

```python
# In router_node.py / planner_node.py

async def route_and_plan(state: AgentState):
    query = state.messages[-1].content

    # Level 1: Domain selection
    domain_selector = await get_domain_selector()
    domain_result = await domain_selector.select_domains(query)
    # domains = ["emails"] for "mes derniers emails"

    # Level 2: Tool selection (within domains)
    tool_selector = await get_tool_selector()
    registry = get_global_registry()
    domain_tools = registry.get_tools_for_domains(domain_result.domain_names)

    tool_result = await tool_selector.select_tools(
        query=query,
        available_tools=domain_tools,
    )

    # Build filtered catalogue
    filtered_catalogue = registry.export_for_prompt_filtered(
        domains=domain_result.domain_names,
        tool_names=tool_result.tool_names,
    )

    logger.info(
        "catalogue_optimized",
        domains=domain_result.domain_names,
        tool_count=len(tool_result.selected_tools),
        token_reduction="~90%",
    )
```

#### Domain Keywords Configuration

```python
# apps/api/src/domains/agents/registry/domain_taxonomy.py

DOMAIN_REGISTRY = {
    "emails": DomainConfig(
        name="emails",
        keywords=[
            "email", "emails", "mail", "gmail", "message",
            "inbox", "sent", "draft", "unread", "starred",
            "send", "compose", "reply", "forward",
        ],
        is_routable=True,
    ),
    "reminder": DomainConfig(
        name="reminder",
        keywords=[
            "rappel", "rappelle", "rappelle-moi",
            "remind", "reminder", "notify", "alert",
            "dans", "à", "demain", "ce soir",
        ],
        priority=9,  # High priority to override similar domains
        is_routable=True,
    ),
    # Non-routable domains (always auto-loaded)
    "context": DomainConfig(
        name="context",
        is_routable=False,  # Internal utilities
    ),
}
```

See [ADR-048: Semantic Router](ADR-048-Semantic-Tool-Router.md) for complete details.

### Message Windowing Strategy

```python
# apps/api/src/domains/agents/models.py

def add_messages_with_truncate(
    left: list[BaseMessage],
    right: list[BaseMessage] | BaseMessage,
) -> list[BaseMessage]:
    """
    Custom reducer with token-based truncation.

    Strategy:
    1. add_messages() - Handle RemoveMessage instances
    2. trim_messages() - Truncate by tokens (max_tokens_history)
    3. Fallback - Limit by count (max_messages_history)
    4. Validate - Remove orphan ToolMessages
    """
    # Step 1: Merge messages
    combined = add_messages(left, right if isinstance(right, list) else [right])

    # Step 2: Token-based truncation
    try:
        encoding = tiktoken.get_encoding("o200k_base")
        truncated = trim_messages(
            combined,
            max_tokens=settings.max_tokens_history,  # 100k default
            token_counter=lambda msgs: sum(
                len(encoding.encode(m.content or "")) for m in msgs
            ),
            strategy="last",  # Keep most recent
            include_system=True,
        )
    except Exception:
        # Fallback: count-based truncation
        truncated = combined[-settings.max_messages_history:]

    # Step 3: Validate (remove orphan ToolMessages)
    return remove_orphan_tool_messages(truncated)

# Node-specific window sizes
WINDOW_SIZES = {
    "router_node": 5,      # Fast routing decisions
    "planner_node": 4,     # Optimized 2025-12-19
    "response_node": 20,   # Rich context for synthesis
}
```

### Model Cost Profiles

```python
# apps/api/src/infrastructure/llm/model_profiles.py

@dataclass(frozen=True)
class ModelProfile:
    max_input_tokens: int
    max_output_tokens: int
    cost_per_1m_input: float              # USD
    cost_per_1m_cached_input: float | None = None  # USD (prompt caching)
    cost_per_1m_output: float             # USD
    is_reasoning_model: bool = False
    supports_streaming: bool = True
    supports_tools: bool = True
    supports_vision: bool = False

# Cost tiers
MODEL_PROFILES = {
    # OpenAI - Nano (Budget tier: 80% cost reduction)
    "gpt-4.1-nano": ModelProfile(
        max_input_tokens=128_000,
        max_output_tokens=16_384,
        cost_per_1m_input=0.10,
        cost_per_1m_output=0.40,
    ),
    # OpenAI - Mini (Balanced: 70% of full cost)
    "gpt-4.1-mini": ModelProfile(
        max_input_tokens=128_000,
        max_output_tokens=16_384,
        cost_per_1m_input=0.40,
        cost_per_1m_output=1.60,
    ),
    # OpenAI - Full (Unrestricted)
    "gpt-4.1": ModelProfile(
        max_input_tokens=128_000,
        max_output_tokens=16_384,
        cost_per_1m_input=2.00,
        cost_per_1m_output=8.00,
    ),
    # DeepSeek (Very cost-effective)
    "deepseek-chat": ModelProfile(
        max_input_tokens=64_000,
        max_output_tokens=8_192,
        cost_per_1m_input=0.14,
        cost_per_1m_output=0.28,
    ),
    # Ollama (Local = free)
    "ollama-default": ModelProfile(
        max_input_tokens=32_000,
        max_output_tokens=4_096,
        cost_per_1m_input=0.00,
        cost_per_1m_output=0.00,
    ),
}
```

### Cost-Based HITL Triggers

```python
# apps/api/src/domains/agents/services/approval/strategies.py

class CostThresholdStrategy(ApprovalStrategy):
    """Requires HITL approval if plan cost exceeds threshold."""

    def __init__(self, threshold_usd: float = 1.0):
        self.threshold_usd = threshold_usd

    def requires_approval(
        self,
        plan: ExecutionPlan,
        context: ApprovalContext,
    ) -> tuple[bool, str | None]:
        estimated_cost = self._estimate_plan_cost(plan)

        if estimated_cost > self.threshold_usd:
            return True, f"Estimated cost ${estimated_cost:.2f} exceeds ${self.threshold_usd:.2f} threshold"

        return False, None

    def _estimate_plan_cost(self, plan: ExecutionPlan) -> float:
        """Sum estimated costs from tool manifests."""
        total = 0.0
        for step in plan.steps:
            manifest = get_tool_manifest(step.tool_name)
            if manifest and manifest.cost_profile:
                total += manifest.cost_profile.estimated_cost_usd
        return total
```

### Cost Optimization Hierarchy

| Strategy | Token Reduction | Cost Impact | Performance |
|----------|----------------|-------------|-------------|
| **Semantic Domain/Tool Selection** | **80-90%** | **Primary savings** | +50ms (embedding) |
| **LLM Response Caching** | 100% (cache hit) | Variable | +400x faster |
| **Message Windowing** | 60% | Proportional | Minimal |
| **Model Selection** (nano vs full) | - | 80% cost | Slight quality |
| **Progressive Degradation** | 50-90% | Emergency | Graceful |
| **HITL Budget Approval** | Variable | User-controlled | Manual |

**Key insight**: Semantic domain/tool selection is the **primary optimization** because it runs on every request and reduces the context window by 80-90% before any LLM call.

### Consequences

**Positive**:
- ✅ **Multi-Provider Token Counting** : tiktoken + Anthropic SDK
- ✅ **Real-Time Cost Metrics** : Prometheus integration
- ✅ **LLM Response Caching** : 400x faster, 100% cost reduction
- ✅ **Semantic Domain/Tool Selection** : 80-90% token reduction per request
- ✅ **Progressive Degradation** : Graceful token reduction
- ✅ **Cost-Based HITL** : User approval for expensive operations
- ✅ **Database-Backed Pricing** : Historical tracking, currency conversion
- ✅ **Low-Cost Embeddings** : OpenAI text-embedding-3-small for semantic selection (~$0.02/1M tokens)

**Negative**:
- ⚠️ Cache only for temperature=0 (deterministic)
- ⚠️ Pricing requires daily currency sync
- ⚠️ Embedding API cost (~$0.02/1M tokens for OpenAI text-embedding-3-small)

---

## Validation

**Acceptance Criteria**:
- [x] ✅ tiktoken integration for OpenAI models
- [x] ✅ Anthropic SDK token counting
- [x] ✅ Prometheus metrics (llm_cost_total, llm_tokens_consumed)
- [x] ✅ Redis LLM cache with TTL
- [x] ✅ Progressive token degradation (4 levels)
- [x] ✅ Message windowing per node
- [x] ✅ Cost-based HITL approval strategy
- [x] ✅ Database pricing with currency conversion
- [x] ✅ SemanticDomainSelector with max-pooling (0.75/0.65 thresholds)
- [x] ✅ SemanticToolSelector with max-pooling (0.70/0.60 thresholds)
- [x] ✅ 80-90% token reduction measured in production

---

## Related Decisions

- [ADR-048: Semantic Router (Domains & Tools)](ADR-048-Semantic-Tool-Router.md) - Complete semantic selection architecture
- [ADR-019: Agent Manifest Catalogue System](ADR-019-Agent-Manifest-Catalogue-System.md) - Provides semantic_keywords
- [ADR-049: Local E5 Embeddings](ADR-049-Local-E5-Embeddings.md) - Historical: superseded by OpenAI text-embedding-3-small (v1.14.0)

---

## References

### Source Code
- **Token Counter**: `apps/api/src/infrastructure/llm/providers/token_counter.py`
- **Pricing Service**: `apps/api/src/domains/llm/pricing_service.py`
- **LLM Cache**: `apps/api/src/infrastructure/cache/llm_cache.py`
- **Model Profiles**: `apps/api/src/infrastructure/llm/model_profiles.py`
- **Metrics**: `apps/api/src/infrastructure/observability/metrics_agents.py`
- **Approval Strategies**: `apps/api/src/domains/agents/services/approval/strategies.py`
- **SemanticDomainSelector**: `apps/api/src/domains/agents/services/semantic_domain_selector.py`
- **SemanticToolSelector**: `apps/api/src/domains/agents/services/tool_selector.py`
- **Domain Taxonomy**: `apps/api/src/domains/agents/registry/domain_taxonomy.py`

---

**Fin de ADR-039** - Cost Optimization & Token Management Decision Record.
