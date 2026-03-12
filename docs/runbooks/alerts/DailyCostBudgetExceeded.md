# DailyCostBudgetExceeded - Runbook

**Severity**: Warning
**Component**: LLM
**Impact**: Budget overrun, potential financial impact
**SLA Impact**: No - Performance unaffected, financial only

---

## 1. Alert Definition

**Alert Name**: `DailyCostBudgetExceeded`

**PromQL Query**:
```promql
sum(increase(llm_cost_total{currency="USD"}[24h])) > <<<ALERT_LLM_DAILY_COST_BUDGET_USD>>>
```

**Thresholds**:
- **Production**: >$100/day (Warning - review spending)
- **Staging**: >$20/day
- **Development**: >$5/day

**Duration**: N/A (evaluated daily)

**Labels**:
```yaml
severity: warning
component: llm
alert_type: cost
impact: financial
```

**Annotations**:
```yaml
summary: "Daily LLM cost budget exceeded: ${{ $value }}"
description: "LLM costs reached ${{ $value }} in 24h (budget: $<<<ALERT_LLM_DAILY_COST_BUDGET_USD>>>)"
```

---

## 2. Symptoms

### What Users See
- No visible impact (service operates normally)
- Potentially rate-limited if emergency cost controls activated

### What Ops See
- `llm_cost_total` metric exceeding budget threshold
- Spike in token consumption
- Higher than expected API usage

---

## 3. Possible Causes

### Cause 1: Traffic Spike (Legitimate Usage Increase) (High Likelihood)
**Likelihood**: High (50%) - Normal business growth

**Verification**:
```bash
# Check request volume trend
curl -s "http://localhost:9090/api/v1/query?query=sum(rate(http_requests_total{path=~\"/api/agents.*\"}[1h]))" | jq '.data.result[0].value[1]'

# Compare to yesterday
curl -s "http://localhost:9090/api/v1/query?query=sum(rate(http_requests_total{path=~\"/api/agents.*\"}[1h] offset 24h))" | jq '.data.result[0].value[1]'

# Check active users
docker-compose exec postgres psql -U lia -c "
SELECT COUNT(DISTINCT user_id) FROM conversations WHERE created_at > NOW() - INTERVAL '24 hours';
"
```

---

### Cause 2: Inefficient Prompts (Excessive Token Usage) (Medium Likelihood)
**Likelihood**: Medium (30%) - Common after prompt changes

**Verification**:
```bash
# Check average tokens per request
curl -s "http://localhost:9090/api/v1/query?query=sum(rate(llm_tokens_consumed_total[1h]))/sum(rate(llm_api_calls_total[1h]))" | jq '.data.result[0].value[1]'

# Check token breakdown by type
curl -s "http://localhost:9090/api/v1/query?query=sum by (type) (increase(llm_tokens_consumed_total[24h]))" | jq -r '.data.result[] | "\(.metric.type): \(.value[1])"'

# Examine recent prompt changes
git log --since="7 days ago" --oneline -- apps/api/src/domains/agents/prompts/
```

---

### Cause 3: LLM Cache Miss Rate High (Medium Likelihood)
**Likelihood**: Medium (25%) - Reduces cost savings from caching

**Verification**:
```bash
# Check cache hit rate
curl -s "http://localhost:9090/api/v1/query?query=(sum(rate(llm_cache_hits_total[1h]))/sum(rate(llm_cache_requests_total[1h])))*100" | jq '.data.result[0].value[1]'

# Should be >60%, <40% indicates poor caching

# Check cache size
docker-compose exec postgres psql -U lia -c "SELECT COUNT(*) FROM llm_cache;"
```

---

### Cause 4: Model Selection Too Expensive (Low-Medium Likelihood)
**Likelihood**: Low-Medium (20%) - Using Opus instead of Sonnet/Haiku

**Verification**:
```bash
# Check cost by model
curl -s "http://localhost:9090/api/v1/query?query=sum by (model) (increase(llm_cost_total[24h]))" | jq -r '.data.result[] | "\(.metric.model): $\(.value[1])"'

# Check model selection logic
grep -n "model.*opus\|model.*sonnet\|model.*haiku" apps/api/src/domains/agents/ -r
```

---

## 4. Diagnostic Steps

### Quick Health Check (<2 minutes)

**Step 1: Check current 24h spending**
```bash
curl -s "http://localhost:9090/api/v1/query?query=sum(increase(llm_cost_total{currency=\"USD\"}[24h]))" | jq '.data.result[0].value[1]'
```

**Step 2: Identify top cost drivers**
```bash
# By model
curl -s "http://localhost:9090/api/v1/query?query=sum by (model) (increase(llm_cost_total[24h]))" | jq -r '.data.result[] | "\(.metric.model): $\(.value[1])"'

# By agent type
curl -s "http://localhost:9090/api/v1/query?query=sum by (agent) (increase(llm_cost_total[24h]))" | jq -r '.data.result[] | "\(.metric.agent): $\(.value[1])"'
```

---

### Deep Dive Analysis (5-10 minutes)

**Step 3: Analyze token consumption patterns**
```bash
# Input vs output tokens
curl -s "http://localhost:9090/api/v1/query?query=sum by (type) (increase(llm_tokens_consumed_total[24h]))" | jq -r '.data.result[] | "\(.metric.type): \(.value[1])"'

# High input_tokens = Large prompts/context
# High output_tokens = Long responses
```

**Step 4: Check for API abuse or anomalies**
```bash
# Requests per user (top 10)
docker-compose exec postgres psql -U lia -c "
SELECT
  user_id,
  COUNT(*) as request_count,
  SUM(input_tokens + output_tokens) as total_tokens
FROM llm_api_calls
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY user_id
ORDER BY total_tokens DESC
LIMIT 10;
"

# Suspicious: Single user with >50% of total tokens
```

**Step 5: Review recent deployments**
```bash
# Check if cost spike correlates with deployment
git log --since="7 days ago" --format="%h %ai %s" | head -10

# Check deployment dates
docker-compose logs api | grep "Application started" | tail -5
```

---

## 5. Resolution Steps

### Immediate Mitigation

**Option 1: Enable emergency cost controls (rate limiting)**

**File**: `apps/api/.env`
```bash
# Temporarily reduce rate limits
LLM_RATE_LIMIT_PER_MINUTE=50  # Reduce from 100
LLM_RATE_LIMIT_BURST=10       # Reduce from 20
```

**Restart**:
```bash
docker-compose restart api
```

---

**Option 2: Switch to cheaper model tier**

**File**: `apps/api/.env`
```bash
# Use Haiku instead of Sonnet for non-critical operations
DEFAULT_LLM_MODEL=claude-3-haiku-20240307
ROUTER_MODEL=claude-3-haiku-20240307

# Keep Sonnet only for final responses
RESPONSE_MODEL=claude-3-sonnet-20240229
```

**Restart**:
```bash
docker-compose restart api
```

---

**Option 3: Increase cache TTL to improve hit rate**

**File**: `apps/api/.env`
```bash
# Extend cache TTL from 1h to 24h
LLM_CACHE_TTL_SECONDS=86400
```

---

### Root Cause Fix

**Fix 1: Optimize prompts to reduce token usage**

**Audit prompt sizes**:
```bash
# Find largest prompts
find apps/api/src/domains/agents/prompts -type f -exec wc -w {} + | sort -nr | head -10
```

**Optimize techniques**:
- Remove verbose examples, keep 1-2 concise ones
- Use shorter system prompts
- Implement dynamic context windowing (only include relevant history)

**File**: `apps/api/src/domains/agents/context/prompts.py`
```python
def build_context_window(messages: list, max_tokens: int = 4000) -> list:
    """Keep only recent messages within token budget"""
    from tiktoken import encoding_for_model

    enc = encoding_for_model("claude-3-sonnet-20240229")
    total_tokens = 0
    context = []

    # Reverse iteration (newest first)
    for msg in reversed(messages):
        msg_tokens = len(enc.encode(msg["content"]))
        if total_tokens + msg_tokens > max_tokens:
            break
        context.insert(0, msg)
        total_tokens += msg_tokens

    return context
```

---

**Fix 2: Implement tiered model selection**

**File**: `apps/api/src/domains/agents/services/model_selector.py`
```python
from enum import Enum

class TaskComplexity(Enum):
    SIMPLE = "simple"      # Haiku
    MODERATE = "moderate"  # Sonnet
    COMPLEX = "complex"    # Opus

def select_model(task_complexity: TaskComplexity) -> str:
    """Choose cheapest model that meets requirements"""
    model_map = {
        TaskComplexity.SIMPLE: "claude-3-haiku-20240307",      # $0.25/$1.25 per 1M tokens
        TaskComplexity.MODERATE: "claude-3-sonnet-20240229",  # $3/$15 per 1M tokens
        TaskComplexity.COMPLEX: "claude-3-opus-20240229",     # $15/$75 per 1M tokens
    }
    return model_map[task_complexity]

# Usage in router
model = select_model(TaskComplexity.SIMPLE)  # Router is simple classification
```

---

**Fix 3: Implement user-level cost tracking and quotas**

**File**: `apps/api/src/infrastructure/llm/cost_tracker.py`
```python
from sqlalchemy import Column, Integer, Float, String, Date
from src.infrastructure.database import Base

class UserLLMCost(Base):
    __tablename__ = "user_llm_costs"

    user_id = Column(String, primary_key=True)
    date = Column(Date, primary_key=True)
    total_cost_usd = Column(Float, default=0.0)
    total_tokens = Column(Integer, default=0)

async def track_user_cost(user_id: str, cost: float, tokens: int):
    """Track per-user daily costs"""
    today = datetime.utcnow().date()

    result = await session.execute(
        select(UserLLMCost).where(
            UserLLMCost.user_id == user_id,
            UserLLMCost.date == today
        )
    )
    record = result.scalar_one_or_none()

    if record:
        record.total_cost_usd += cost
        record.total_tokens += tokens
    else:
        record = UserLLMCost(
            user_id=user_id,
            date=today,
            total_cost_usd=cost,
            total_tokens=tokens
        )
        session.add(record)

    await session.commit()

    # Check quota
    if record.total_cost_usd > USER_DAILY_QUOTA_USD:
        raise QuotaExceededError(f"User {user_id} exceeded daily quota")
```

---

**Fix 4: Implement prompt caching (Anthropic feature)**

**File**: `apps/api/src/infrastructure/llm/client.py`
```python
from anthropic import Anthropic

client = Anthropic(api_key=settings.anthropic_api_key)

async def call_with_prompt_caching(system_prompt: str, user_message: str):
    """Use Anthropic prompt caching to reduce costs"""
    response = await client.messages.create(
        model="claude-3-sonnet-20240229",
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"}  # Cache this prompt
            }
        ],
        messages=[{"role": "user", "content": user_message}]
    )

    # Cached prompts cost 90% less on subsequent calls
    return response
```

---

## 6. Related Dashboards & Queries

### Grafana Dashboards
- **LLM Cost Monitoring** - `http://localhost:3000/d/llm-costs`
  - Panel: "Daily Cost Trend"
  - Panel: "Cost by Model"
  - Panel: "Cost by Agent"

### Prometheus Queries

**24h total cost**:
```promql
sum(increase(llm_cost_total{currency="USD"}[24h]))
```

**Cost rate ($/hour)**:
```promql
sum(rate(llm_cost_total{currency="USD"}[1h])) * 3600
```

**Average cost per request**:
```promql
sum(increase(llm_cost_total[24h])) / sum(increase(llm_api_calls_total[24h]))
```

**Token consumption by type**:
```promql
sum by (type) (increase(llm_tokens_consumed_total[24h]))
```

---

## 7. Related Runbooks
- [LLMAPIFailureRateHigh.md](./LLMAPIFailureRateHigh.md) - LLM API issues
- None specific (cost monitoring is isolated)

---

## 8. Common Patterns

### Pattern 1: Weekly Cost Spike (Monday Morning)
**Scenario**: Users return after weekend, backlog of conversations processed.

**Detection**: Costs spike 2-3x on Monday 9-11am.

**Prevention**: Budget alert threshold account for weekly patterns (use P95, not average).

---

### Pattern 2: Viral Feature Drives Unexpected Usage
**Scenario**: New feature unexpectedly popular, 10x normal usage.

**Detection**: Sudden user growth correlates with cost spike.

**Response**: Celebrate success, request budget increase, optimize feature prompts.

---

## 9. Escalation

### When to Escalate
- Daily cost >2x budget for 3 consecutive days
- Evidence of API abuse (single user >50% of cost)
- Budget exhausted (risk of service shutdown)

### Escalation Path
1. **Level 1 - Product Lead** (0-2 hours) - Approve temporary budget increase
2. **Level 2 - CFO** (2-24 hours) - Major budget revision
3. **Level 3 - CEO** (24+ hours) - Strategic decision on pricing/features

---

## 10. Post-Incident Actions

### Immediate (<4 hours)
- [ ] Document cost spike cause
- [ ] Implement immediate cost controls
- [ ] Notify finance team

### Short-term (<1 week)
- [ ] Optimize high-cost prompts
- [ ] Implement per-user quotas
- [ ] Review model selection strategy

### Long-term (<1 month)
- [ ] Update budget forecasts
- [ ] Implement predictive cost alerting
- [ ] Consider usage-based pricing for users

---

## 11. Runbook Metadata

**Version**: 1.0
**Last Updated**: 2025-11-22
**Author**: SRE Team
