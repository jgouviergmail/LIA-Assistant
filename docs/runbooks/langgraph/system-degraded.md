# LangGraphSystemDegraded - Runbook

**Severity**: critical | **Component**: langgraph | **Impact**: INCIDENT MAJEUR | **SLA Impact**: Oui

---

## 📊 Alert (Composite)

```promql
(
  (sum(rate(langgraph_graph_executions_total{status="success"}[5m])) /
   sum(rate(langgraph_graph_executions_total[5m]))) * 100 < 90
)
and
(
  histogram_quantile(0.95, rate(langgraph_graph_duration_seconds_bucket[5m])) > 20
)
```

**Meaning**: SUCCESS RATE <90% ET LATENCY P95 >20s **simultanément**

**This is a MAJOR INCIDENT** - Multiple systems failing

---

## 🚨 IMMEDIATE ACTIONS

### 1. Escalate Immediately (< 2 minutes)

```bash
# Alert on-call + team lead
# Post to #incidents-critical Slack channel
```

**Template**:
```
🚨 MAJOR INCIDENT - LangGraph System Degraded 🚨

Success Rate: [XX]% (threshold: 90%)
P95 Latency: [XX]s (threshold: 20s)
Duration: [XX] minutes

ESCALATION REQUIRED
Dashboard: http://localhost:3000/d/langgraph-framework-observability
```

---

### 2. Quick Health Check (< 3 minutes)

```bash
# 1. All services up?
docker-compose ps

# 2. LLM provider status
curl -s https://status.openai.com/api/v2/status.json | jq '.status.description'

# 3. Database alive?
docker-compose exec postgresql pg_isready

# 4. Redis alive?
docker-compose exec redis redis-cli ping

# 5. Related alerts firing?
curl -s http://localhost:9093/api/v2/alerts | jq '.[] | select(.status.state=="firing") | .labels.alertname'
```

---

## 🎯 Root Cause Patterns

### Pattern A: External Dependency Failure (60%)

**Indicators**:
- LLM API errors high
- Database slow queries
- Redis connection errors

**Action**: Wait for dependency recovery OU implement circuit breaker

---

### Pattern B: Resource Exhaustion (30%)

**Indicators**:
- CPU >90%
- Memory >90%
- DB connections maxed

**Action**: Scale up resources OU restart containers

---

### Pattern C: Code Bug Deploy (10%)

**Indicators**:
- Incident started after deploy
- Specific error type dominating

**Action**: Immediate rollback

---

## ✅ Mitigation Priority Order

### Priority 1: Rollback Recent Deploy

```bash
# If deploy within last 2 hours
git log --oneline --since="2 hours ago"
git checkout [previous-stable-commit]
docker-compose build api
docker-compose up -d api
```

---

### Priority 2: Restart All Services

```bash
docker-compose restart api postgresql redis
sleep 60

# Verify recovery
curl -s "http://localhost:9090/api/v1/query?query=(sum(rate(langgraph_graph_executions_total{status=\"success\"}[1m]))/sum(rate(langgraph_graph_executions_total[1m])))*100" | jq
```

---

### Priority 3: Enable Degraded Mode

```bash
# Disable expensive features
docker-compose exec api sh -c 'echo "TOOL_APPROVAL_ENABLED=false" >> .env'
docker-compose exec api sh -c 'echo "PARALLEL_EXECUTION_ENABLED=false" >> .env'
docker-compose restart api
```

---

## 📈 Post-Incident

**MANDATORY**:
- [ ] Create incident report
- [ ] Post-mortem meeting within 24h
- [ ] Update runbooks with learnings
- [ ] Implement prevention measures

---

**Created**: 2025-11-22 | **Version**: 1.0.0
