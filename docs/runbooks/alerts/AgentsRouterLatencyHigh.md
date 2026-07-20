# AgentsRouterLatencyHigh - Runbook

**Severity**: Warning
**Component**: Agents
**Impact**: Delayed agent routing, slower user responses
**SLA Impact**: Potential - If latency compounds with other delays

---

## 1. Alert Definition

**Alert Name**: `AgentsRouterLatencyHigh`

**PromQL Query**:
```promql
histogram_quantile(0.95, rate(router_latency_seconds_bucket[5m])) > <<<ALERT_AGENTS_ROUTER_LATENCY_P95_WARNING_SECONDS>>>
```

**Thresholds**:
- **Production**: P95 >2 seconds (Warning - routing should be <1s)
- **Staging**: P95 >5 seconds
- **Development**: P95 >10 seconds

**Duration**: For 5 minutes

**Labels**:
```yaml
severity: warning
component: agents
alert_type: performance
impact: latency
```

**Annotations**:
```yaml
summary: "Agent router latency high: P95={{ $value }}s"
description: "Router is taking {{ $value }}s at P95 (threshold: <<<ALERT_AGENTS_ROUTER_LATENCY_P95_WARNING_SECONDS>>>s)"
```

---

## 2. Symptoms

### What Users See
- Slower response times to initial queries
- Longer wait before streaming starts
- "Thinking..." indicator lasting >3 seconds

### What Ops See
- `router_latency_seconds` P95 >2s in Prometheus
- Router node taking >1s in traces
- Increased task orchestrator queue depth

---

## 3. Possible Causes

### Cause 1: LLM API Latency for Routing Decision (High Likelihood)
**Description**: Router calls LLM to classify intent, LLM API is slow.

**Likelihood**: High (60%)

**Verification**:
```bash
# Check LLM latency
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95,rate(llm_api_latency_seconds_bucket{operation=\"router\"}[5m]))" | jq '.data.result[0].value[1]'

# Check router LLM calls
docker-compose logs api | grep "router_node" | grep "llm_call"
```

---

### Cause 2: Complex Intent Classification Logic (Medium Likelihood)
**Description**: Router performs multiple LLM calls or heavy processing.

**Likelihood**: Medium (30%)

**Verification**:
```bash
# Check router traces
curl -s "http://localhost:9090/api/v1/query?query=rate(router_decisions_total[5m])" | jq '.data.result'

# Should be ~1 call per route, >2 indicates complexity
```

---

### Cause 3: Database Query in Router Path (Low-Medium Likelihood)
**Description**: Router fetches context from database synchronously.

**Likelihood**: Low-Medium (20%)

**Verification**:
```bash
# Check for DB queries in router code
grep -n "session.query" apps/api/src/domains/agents/nodes/router_node_v3.py

# Check DB latency
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95,rate(db_query_duration_seconds_bucket[5m]))" | jq '.data.result[0].value[1]'
```

---

## 4. Resolution Steps

### Immediate Mitigation

**Option 1: Use faster LLM model for routing**

**Ou changer le modele du router** (verifie 2026-07-20) : **pas dans le `.env`**.
Il n'existe pas de variable `ROUTER_MODEL`. Les modeles par type de LLM sont
configures **en base** (`LLM_TYPES_REGISTRY`, `src/domains/llm_config/`) et se
modifient depuis l'administration LLM. Editer un `.env` ici n'aurait aucun effet.

**Restart**:
```bash
docker-compose restart api
```

---

**Option 2: Implement caching for common intents**

**File**: `apps/api/src/domains/agents/nodes/router_node_v3.py`
```python
from functools import lru_cache

@lru_cache(maxsize=1000)
def classify_intent_cached(user_message: str) -> str:
    # Cache based on message hash
    return classify_intent(user_message)
```

---

### Root Cause Fix

**Fix 1: Optimize routing prompt to reduce LLM tokens**

**File**: `apps/api/src/domains/agents/prompts/v1/query_analyzer_prompt.txt` (routing lives in QueryAnalyzerService)
- Reduce prompt length (fewer examples)
- Use more structured output (JSON schema)
- Keep dynamic content below the `--- DYNAMIC CONTEXT ---` marker (prompt-cache prefix)

---

**Fix 2: Implement parallel context loading**

```python
import asyncio

async def route_with_context(state):
    # Load context in parallel with routing
    context_task = asyncio.create_task(load_user_context(state))
    route_task = asyncio.create_task(classify_intent(state["message"]))

    route, context = await asyncio.gather(route_task, context_task)
    return route
```

---

## 5. Related Dashboards & Queries

### Prometheus Queries

**Router latency P95**:
```promql
histogram_quantile(0.95, rate(router_latency_seconds_bucket[5m]))
```

**Router LLM call rate**:
```promql
rate(router_decisions_total[5m])
```

---

## 6. Related Runbooks
- [CriticalLatencyP99.md](./CriticalLatencyP99.md) - Overall API latency
- [LLMAPIFailureRateHigh.md](./LLMAPIFailureRateHigh.md) - LLM API issues

---

## 7. Runbook Metadata

**Version**: 1.0
**Last Updated**: 2025-11-22
**Author**: SRE Team
