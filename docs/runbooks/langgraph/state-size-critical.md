# LangGraphStateSizeCritical - Runbook

**Severity**: critical | **Component**: langgraph | **Impact**: Performance checkpoint dégradée | **SLA Impact**: Non

---

## 📊 Alert

```promql
histogram_quantile(0.95,
  sum(rate(langgraph_state_size_bytes_bucket[5m])) by (le, node_name)
) > 1048576  # 1MB
```

**Threshold**: P95 > 1MB (firing: 10m) | **Target**: P95 < 500KB

---

## 🔍 Why This Matters

**LangGraph checkpoint performance degrades >1MB**:
- Slow Redis save/restore
- Memory pressure
- Serialization overhead

---

## 🎯 Common Causes

### 1. Messages List Growth (90% des cas)

**Problem**: `state["messages"]` accumule sans cleanup

**Diagnostic**:
```bash
# Check messages count in state
docker-compose logs api --since=10m | grep "state_size_bytes.*messages" | tail -10
```

**Fix**: Aggressive cleanup
```python
# constants.py
MAX_MESSAGES_IN_STATE = 20  # Was 50

# response_node.py
state["messages"] = state["messages"][-MAX_MESSAGES_IN_STATE:]
```

---

### 2. Agent Results Accumulation

**Problem**: `agent_results` dict keeps growing

**Fix**: Already implemented cleanup, verify limits
```python
# task_orchestrator_node.py
MAX_AGENT_RESULTS = 10  # Verify this is applied
```

---

### 3. Large Tool Outputs

**Problem**: Tools return huge payloads (email bodies, contact lists)

**Fix**: Truncate tool outputs
```python
# tools/emails_tools.py
def truncate_email_body(body: str, max_chars: int = 500) -> str:
    return body[:max_chars] + "..." if len(body) > max_chars else body
```

---

## ✅ Immediate Fix

```bash
# 1. Check which node has bloated state
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95,sum by (node_name)(rate(langgraph_state_size_bytes_bucket[5m])))" | jq '.data.result[] | {node: .metric.node_name, size: .value[1]}'

# 2. Temporary: Reduce message history
docker-compose exec api sh -c 'echo "MAX_MESSAGES_IN_STATE=10" >> .env'
docker-compose restart api

# 3. Monitor state size dropped
sleep 60
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95,rate(langgraph_state_size_bytes_bucket[5m]))/1024" | jq
```

---

## 📈 Dashboard

**11 - LangGraph Framework** → Section 3 "State Management"
- Panel: "P95 State Size (KB)"
- Panel: "State Size by Node - P95"

---

## 🔄 Prevention

```python
# Implement state cleanup policy in every node
def _cleanup_state(state: MessagesState) -> dict:
    return {
        "messages": state["messages"][-20:],  # Keep last 20
        "agent_results": cleanup_dict_by_turn_id(state["agent_results"], max_results=10),
        "routing_history": state["routing_history"][-5:],  # Keep last 5
    }
```

---

**Created**: 2025-11-22 | **Version**: 1.0.0
