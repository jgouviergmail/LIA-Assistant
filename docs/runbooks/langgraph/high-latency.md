# LangGraphHighLatencyP95 - Runbook

**Severity**: critical
**Component**: langgraph
**Impact**: Conversations lentes - mauvaise expérience utilisateur
**SLA Impact**: Oui - Latency SLA (>30s)

---

## 📊 Alert Definition

**Alert Name**: `LangGraphHighLatencyP95`

**Prometheus Expression**:
```promql
histogram_quantile(0.95,
  sum(rate(langgraph_graph_duration_seconds_bucket[5m])) by (le)
) > 30
```

**Thresholds**:
- **Critical**: P95 > 30s (firing: 5m)
- **Warning**: P95 > 10s (firing: 10m)
- **Target**: P95 < 5s

---

## 🔍 Symptoms

### What Users See
- Interface "thinking..." pendant >30 secondes
- Timeout messages
- Frustration utilisateur

### What Ops See
- Dashboard panel "Graph P95 Latency" rouge
- `langgraph_graph_duration_seconds` P95 > 30s
- Logs montrant slow responses

---

## 🎯 Top Causes & Quick Fixes

### 1. LLM API Slow Responses (90% des cas)

**Verify**:
```bash
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95,rate(llm_api_duration_seconds_bucket[5m]))" | jq '.data.result[0].value[1]'
```

**Fix**: Attendre stabilisation provider OU switch model plus rapide
```python
# Emergency: Switch to faster model
OPENAI_MODEL = "gpt-3.5-turbo"  # Instead of gpt-4
```

---

### 2. SubGraph ReAct Loops Inefficients

**Verify**:
```bash
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95,sum by (le,agent_name)(rate(langgraph_subgraph_duration_seconds_bucket[5m])))" | jq '.data.result'
```

**Fix**: Reduce max iterations
```python
# agents/graphs/base_agent_builder.py
MAX_ITERATIONS = 5  # Was 15
```

---

### 3. Database Slow Queries

**Verify**:
```bash
docker-compose exec postgresql psql -U lia -c "SELECT query, mean_exec_time FROM pg_stat_statements WHERE mean_exec_time > 1000 ORDER BY mean_exec_time DESC LIMIT 10;"
```

**Fix**: Add missing indexes OU optimize queries

---

## 🔧 Quick Diagnostic

```bash
# 1. Check P95 by component
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95,rate(langgraph_graph_duration_seconds_bucket[5m]))" | jq

# 2. Check SubGraph latencies
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95,sum by (agent_name)(rate(langgraph_subgraph_duration_seconds_bucket[5m])))" | jq

# 3. Check LLM latencies
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95,rate(llm_api_duration_seconds_bucket[5m]))" | jq
```

---

## ✅ Immediate Mitigation

### Option A: Switch to Faster LLM Model
```bash
# Update config
docker-compose exec api sh -c 'sed -i "s/gpt-4-turbo/gpt-3.5-turbo/g" .env'
docker-compose restart api
```

**Duration**: 30s
**Impact**: Réduit qualité réponses mais accélère drastiquement

---

### Option B: Reduce Parallel Execution
```bash
# Limit concurrent agent executions
docker-compose exec api sh -c 'echo "MAX_PARALLEL_AGENTS=1" >> .env'
docker-compose restart api
```

**Duration**: 30s
**Impact**: Séquentialise au lieu de paralléliser (plus stable mais potentiellement plus lent)

---

## 📈 Related Dashboards

- **11 - LangGraph Framework**: Section 1 "Graph Latency Distribution"
- Panel: "Graph P95 Latency (s)"
- Panel: "SubGraph Duration by Agent - P95"

---

## 📚 Related Runbooks

- [subgraph-high-latency.md](./subgraph-high-latency.md) - Si SubGraphs lents
- [performance-degraded.md](./performance-degraded.md) - Alert composite

---

**Created**: 2025-11-22
**Version**: 1.0.0
