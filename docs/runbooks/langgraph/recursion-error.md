# LangGraphRecursionError - Runbook

**Severity**: critical | **Component**: langgraph | **Impact**: Boucle infinie graph | **SLA Impact**: Oui

---

## 📊 Alert

```promql
sum(rate(langgraph_graph_errors_total{error_type="GraphRecursionError"}[5m])) > 0
```

**Threshold**: ANY occurrence (firing: 2m) | **Meaning**: Graph boucle infinie détectée

---

## 🔍 Symptoms

### What Happens
- Graph exécute >25 iterations (recursion limit)
- LangGraph raise `GraphRecursionError`
- Conversation bloquée indéfiniment
- Logs: "Maximum recursion depth exceeded"

---

## 🎯 Root Causes

### 1. Router → Response → Router Loop (80% des cas)

**Cause**: Conditional edge mal configuré crée loop
```
router (low confidence) → response → router (retry) → response → ...
```

**Diagnostic**:
```bash
# Check router decision distribution
curl -s "http://localhost:9090/api/v1/query?query=sum by (decision)(rate(langgraph_conditional_edges_total{edge_name=\"route_from_router\"}[5m]))" | jq
```

**Fix**: Add recursion guard
```python
# router_node_v3.py
if len(state.get("routing_history", [])) > 3:
    # Force exit to response
    return RouterOutput(next_node="response", ...)
```

---

### 2. Planner → Task_Orchestrator Loop

**Cause**: Planner continue de re-planifier sans succès

**Fix**: Limit re-planning attempts
```python
# planner_node_v3.py
max_planning_attempts = state.get("planning_attempts", 0)
if max_planning_attempts > 2:
    return {STATE_KEY_EXECUTION_PLAN: None}  # Skip planner
```

---

## ✅ Immediate Fix

```bash
# 1. Emergency: Increase recursion limit (temporary)
docker-compose exec api sh -c 'echo "LANGGRAPH_RECURSION_LIMIT=50" >> .env'
docker-compose restart api

# 2. Permanent: Fix conditional edge logic
# Edit src/domains/agents/graph.py
# Add recursion guards in nodes

# 3. Monitor recursion errors stopped
curl -s "http://localhost:9090/api/v1/query?query=rate(langgraph_graph_errors_total{error_type=\"GraphRecursionError\"}[5m])" | jq
```

---

## 📈 Investigation

```bash
# 1. Find conversation_id causing loop
docker-compose logs api --since=10m | grep "GraphRecursionError" | grep -oP 'conversation_id=\K[a-f0-9-]+'

# 2. Analyze routing history for that conversation
docker-compose logs api --since=10m | grep [conversation_id] | grep "routing_history"

# 3. Identify loop pattern
# Look for: router → response → router pattern
```

---

## 🆘 Escalation

**Escalate if**:
- >5 GraphRecursionErrors/minute
- Same conversation_id looping repeatedly
- Unable to identify loop pattern after 10 minutes

---

**Created**: 2025-11-22 | **Version**: 1.0.0
