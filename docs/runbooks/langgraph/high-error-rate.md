# LangGraphHighErrorRate - Runbook

**Severity**: critical | **Component**: langgraph | **Impact**: Erreurs fréquentes | **SLA Impact**: Oui

---

## 📊 Alert

```promql
sum(rate(langgraph_graph_executions_total{status="error"}[5m])) > 0.5
```

**Threshold**: >0.5 errors/s (firing: 5m) | **Target**: <0.1 errors/s

---

## 🔍 Quick Diagnostic

```bash
# 1. Top error types
curl -s "http://localhost:9090/api/v1/query?query=topk(5,sum by (error_type)(rate(langgraph_graph_errors_total[5m])))" | jq '.data.result[] | {error: .metric.error_type, rate: .value[1]}'

# 2. Recent errors in logs
docker-compose logs api --tail=100 | grep -i "error" | tail -20

# 3. Error rate trend
curl -s "http://localhost:9090/api/v1/query?query=sum(rate(langgraph_graph_executions_total{status=\"error\"}[1m]))" | jq '.data.result[0].value[1]'
```

---

## 🎯 Common Error Types & Fixes

### ValidationError (Pydantic Schema)
**Cause**: Invalid LLM output format
**Fix**: Add retry with explicit format instructions
```python
# prompts/router_system_prompt.txt
"IMPORTANT: Return ONLY valid JSON matching exact schema"
```

### KeyError (Missing State Key)
**Cause**: Node expects key not yet set
**Fix**: Add default values
```python
state.get(STATE_KEY_ROUTING_HISTORY, [])  # Not state[STATE_KEY_ROUTING_HISTORY]
```

### LLMAPIError (Provider Timeout)
**Cause**: LLM provider slow/unavailable
**Fix**: Increase timeout + retry
```python
LLM_TIMEOUT_SECONDS = 120  # Was 60
```

---

## ✅ Immediate Fix

```bash
# Restart API (clears stuck states)
docker-compose restart api

# Verify error rate dropped
sleep 30
curl -s "http://localhost:9090/api/v1/query?query=sum(rate(langgraph_graph_executions_total{status=\"error\"}[1m]))" | jq
```

---

## 📈 Dashboard
**11 - LangGraph Framework** → "Graph Errors by Type" panel

---

**Created**: 2025-11-22 | **Version**: 1.0.0
