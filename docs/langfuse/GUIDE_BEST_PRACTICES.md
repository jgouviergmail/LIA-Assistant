# Langfuse Best Practices - Guide Production 2025

**Version**: 1.0.0
**Phase**: 4.3 - Langfuse Documentation
**Date**: 2025-11-23
**Status**: Production Ready ✅

---

## 📋 Table des Matières

1. [Cardinality Management](#cardinality-management)
2. [Sampling Strategy](#sampling-strategy)
3. [Performance Optimization](#performance-optimization)
4. [Security & Privacy](#security--privacy)
5. [Monitoring & Alerting](#monitoring--alerting)

---

## Cardinality Management

### Problème: Explosion Time Series Prometheus

**Définition Cardinality**: Nombre de combinaisons uniques de labels

**Example Mauvais**:
```python
# ❌ DON'T DO THIS
langfuse_prompt_version_usage.labels(
    prompt_id="router",
    version="2",
    user_id=user.id,           # 10K users
    conversation_id=conv.id,   # 100K conversations
    timestamp=datetime.now()   # Infinite!
).inc()

# Cardinality = 8 prompts × 3 versions × 10K users × 100K conversations
#             = 24 BILLION time series! 💥 Prometheus crash
```

**Example Bon**:
```python
# ✅ DO THIS
langfuse_prompt_version_usage.labels(
    prompt_id="router_system_v6",
    version="2"
).inc()

# Cardinality = 8 prompts × 3 versions = 24 time series ✅

# Track user/conversation in Langfuse trace (not Prometheus)
langfuse.trace(
    name="router_execution",
    user_id=user.id,
    session_id=conv.id,
    metadata={"prompt_version": "2"}
)
```

### Règles d'Or Cardinality

| Label Type | Cardinality | Prometheus? | Langfuse? |
|------------|-------------|-------------|-----------|
| **prompt_id** | ~8 | ✅ YES | ✅ YES |
| **version** | 2-5 per prompt | ✅ YES | ✅ YES |
| **model** | ~5 (gpt4, claude, etc.) | ✅ YES | ✅ YES |
| **agent_type** | ~5 (router, planner, etc.) | ✅ YES | ✅ YES |
| **metric_name** | ~6 (hallucination, relevance, etc.) | ✅ YES | ✅ YES |
| **user_id** | 10K-1M | ❌ NO | ✅ YES |
| **conversation_id** | 100K-10M | ❌ NO | ✅ YES |
| **timestamp** | Infinite | ❌ NO | ✅ YES |

**Cardinality Limits**:
- **Safe**: <100 time series per metric
- **Warning**: 100-1000 time series
- **Danger**: >1000 time series (Prometheus performance impact)
- **Critical**: >10K time series (Prometheus crash risk)

**Validation**:
```python
# Calculate cardinality before deploying
def calculate_cardinality(labels: dict) -> int:
    """
    Estimate time series cardinality.

    Example:
        labels = {
            "prompt_id": 8,      # 8 different prompts
            "version": 3,        # 3 versions per prompt
            "model": 5           # 5 models
        }
        # Cardinality = 8 × 3 × 5 = 120 time series (acceptable)
    """
    cardinality = 1
    for label_name, label_values in labels.items():
        cardinality *= label_values

    if cardinality > 1000:
        raise ValueError(
            f"Cardinality too high: {cardinality} time series! "
            f"Reduce label combinations or use Langfuse traces instead of Prometheus."
        )

    return cardinality
```

---

## Sampling Strategy

### Problème: Coût Évaluation LLM

**Scénario**: 10K conversations/day, évaluer 100% avec GPT-4 = $100/day = **$3K/month** 💸

### Solution: Sampling Intelligent

**Configuration**:
```python
# apps/api/src/core/config.py
class Settings(BaseSettings):
    # Sample rates by environment
    evaluation_sample_rate_dev: float = 1.0      # 100% (testing)
    evaluation_sample_rate_staging: float = 0.3  # 30%
    evaluation_sample_rate_prod: float = 0.1     # 10%

    # Smart sampling rules
    evaluation_always_if_user_flagged: bool = True
    evaluation_always_if_high_risk: bool = True  # Long responses, factual queries

    # Cost limits
    evaluation_max_cost_per_day: float = 10.0  # $10/day budget
```

**Implementation**:
```python
def should_evaluate(conversation: Conversation, environment: str) -> bool:
    # 1. Always evaluate if user flagged conversation
    if conversation.user_flagged:
        return True

    # 2. Always evaluate high-risk conversations
    if is_high_risk(conversation):
        return True  # Long response, factual query, GeneralAgent

    # 3. Check daily budget
    if get_evaluation_cost_today() > settings.evaluation_max_cost_per_day:
        return False

    # 4. Sample based on environment
    sample_rate = {
        "dev": 1.0,
        "staging": 0.3,
        "prod": 0.1
    }[environment]

    return random.random() < sample_rate

def is_high_risk(conversation: Conversation) -> bool:
    """High-risk = more likely to hallucinate."""
    return (
        len(conversation.response) > 500 or  # Long response
        "Quel est" in conversation.query or   # Factual question
        "Combien" in conversation.query or
        conversation.agent_type == "GeneralAgent"
    )
```

**Cost Analysis**:
- 10K conversations/day × 10% sample + 5% high-risk flagged = 1.5K evaluations
- 1.5K × $0.01/eval = **$15/day** = **$450/month** (vs $3K without sampling) ✅

---

## Performance Optimization

### 1. Async Instrumentation (Non-Blocking)

**❌ Bad** (blocks request):
```python
async def router_node(state):
    response = await llm_client.invoke(...)

    # Blocking evaluation (adds 500ms latency!)
    hallucination_score = await hallucination_eval.evaluate(...)

    return {"response": response}
```

**✅ Good** (background task):
```python
async def router_node(state):
    response = await llm_client.invoke(...)

    # Fire-and-forget background task
    asyncio.create_task(
        evaluate_in_background(state, response)
    )

    return {"response": response}  # No latency impact!

async def evaluate_in_background(state, response):
    try:
        score = await hallucination_eval.evaluate(...)
        # Store in database for later analysis
    except Exception as e:
        logger.error("background_evaluation_failed", error=str(e))
        # Don't fail request if evaluation fails
```

### 2. Evaluation Caching

**Cache Results** (avoid re-evaluating same content):
```python
from hashlib import sha256

@lru_cache(maxsize=10000)
async def evaluate_with_cache(query: str, response: str, metric: str) -> float:
    cache_key = sha256(f"{query}|{response}|{metric}".encode()).hexdigest()

    # Check Redis cache
    cached = await redis.get(f"eval:{cache_key}")
    if cached:
        return float(cached)

    # Evaluate if not cached
    score = await evaluator.evaluate(query, response)

    # Cache for 7 days
    await redis.setex(f"eval:{cache_key}", ttl=7*24*3600, value=score)

    return score
```

**Benefits**: 30% cache hit rate = 30% cost savings ✅

### 3. Batch Processing

**Process Evaluations in Batches** (reduce API calls):
```python
async def evaluate_batch(conversations: list[Conversation]) -> list[float]:
    """
    Evaluate multiple conversations in single GPT-4 call.

    Cost: 1 API call instead of N
    """
    eval_prompt = f"""
Évalue hallucination pour chaque conversation (0.0-1.0):

{chr(10).join([
    f"Conversation {i}: Q={c.query} R={c.response}"
    for i, c in enumerate(conversations)
])}

Réponds FORMAT JSON: {{"0": 0.3, "1": 0.7, ...}}
"""

    result = await openai_client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": eval_prompt}],
        response_format={"type": "json_object"}
    )

    scores = json.loads(result.choices[0].message.content)
    return [scores[str(i)] for i in range(len(conversations))]
```

---

## Security & Privacy

### 1. PII Filtering (GDPR Compliance)

**Problème**: Envoyer données users à Langfuse/OpenAI = risque GDPR

**Solution**: PII Filter (déjà implémenté LIA)

```python
from src.infrastructure.observability.pii_filter import redact_pii

# Before sending to Langfuse/evaluators
query_redacted = redact_pii(query)
response_redacted = redact_pii(response)

langfuse.trace(
    name="conversation",
    input=query_redacted,    # "Envoie email à ***@***" (email masked)
    output=response_redacted
)
```

**PII Patterns Masked**:
- Emails: `user@example.com` → `***@***`
- Phone: `+33612345678` → `+33***`
- Credit Card: `1234-5678-9012-3456` → `****-****-****-3456`
- SSN: `123-45-6789` → `***-**-6789`

### 2. Access Control

**Langfuse Projects Isolation**:
- `lia-prod`: Production data (restricted access)
- `lia-staging`: Staging data (team access)
- `lia-dev`: Development data (full access)

**API Keys Rotation**: Every 90 days

**Audit Logging**: All Langfuse access logged (who, when, what)

---

## Monitoring & Alerting

### Key Alerts

#### 1. Cardinality Explosion

```yaml
- alert: PrometheusCardinalityHigh
  expr: |
    count(langfuse_prompt_version_usage) > 1000
  for: 5m
  annotations:
    summary: "Prometheus cardinality too high (>1000 time series)"
    description: "Check for high-cardinality labels (user_id, conversation_id)"
```

#### 2. Evaluation Cost Overrun

```yaml
- alert: EvaluationCostExceeded
  expr: |
    sum(evaluation_cost_total) > 10.0  # $10/day
  for: 1h
  annotations:
    summary: "Evaluation cost budget exceeded"
    description: "Daily cost: ${{ $value | humanize }}"
```

#### 3. Quality Degradation

```yaml
- alert: HallucinationRateHigh
  expr: |
    histogram_quantile(0.95,
        rate(langfuse_evaluation_score_bucket{metric_name="hallucination"}[10m])
    ) > 0.7
  for: 10m
  annotations:
    summary: "High hallucination rate (P95 > 0.7)"
    runbook_url: "/runbooks/langfuse/high-hallucination"
```

---

## Checklist Production Readiness

### Before Deploying Langfuse to Production

- [ ] **Cardinality validated**: <100 time series per metric
- [ ] **Sampling configured**: 10% in prod, cost budget set
- [ ] **PII filtering enabled**: redact_pii() applied
- [ ] **Caching implemented**: Redis cache for evaluations
- [ ] **Async instrumentation**: Background tasks, no request blocking
- [ ] **Alerts configured**: Cardinality, cost, quality degradation
- [ ] **Access control**: Separate prod/staging/dev projects
- [ ] **API keys rotated**: 90-day rotation policy
- [ ] **Cost monitoring**: Dashboard tracking daily/monthly costs
- [ ] **Runbooks created**: Incident response procedures

---

## Références

- [Prometheus Best Practices - Cardinality](https://prometheus.io/docs/practices/naming/#labels)
- [Langfuse Privacy & Security](https://langfuse.com/docs/data-security-privacy)
- [GDPR Compliance Guide](https://gdpr.eu/)
- [Guide Prompt Versioning](./GUIDE_PROMPT_VERSIONING.md)
- [Guide Evaluation Scores](./GUIDE_EVALUATION_SCORES.md)
- [Guide A/B Testing](./GUIDE_AB_TESTING.md)
- [README Observability](../readme/README_OBSERVABILITY.md)

---

**Document**: GUIDE_BEST_PRACTICES.md
**Version**: 1.0.0
**Created**: 2025-11-23
**Status**: ✅ Production Ready
