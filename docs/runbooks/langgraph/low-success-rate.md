# LangGraphLowSuccessRate - Runbook

**Severity**: critical
**Component**: langgraph
**Impact**: Échec massif des conversations utilisateur - expérience dégradée
**SLA Impact**: Oui - Availability SLA (<95%)

---

## 📊 Alert Definition

**Alert Name**: `LangGraphLowSuccessRate`

**Prometheus Expression**:
```promql
(
  sum(rate(langgraph_graph_executions_total{status="success"}[5m]))
  /
  sum(rate(langgraph_graph_executions_total[5m]))
) * 100 < 90
```

**Threshold**:
- **Critical**: <90% success rate
- **Warning**: <95% success rate
- **Target**: >98% success rate

**Firing Duration**: `for: 5m`

**Labels**:
- `severity`: critical
- `component`: langgraph
- `priority`: p1
- `phase`: 2.5

---

## 🔍 Symptoms

### What Users See
- Conversations qui échouent avec erreur "Une erreur s'est produite"
- Réponses incomplètes ou tronquées
- Timeout sur requêtes longues
- Interface bloquée sur "Chargement..."

### What Ops See
- Graph success rate < 90% dans dashboard Grafana
- Metric `langgraph_graph_executions_total{status="error"}` élevée
- Logs API remplis d'exceptions LangGraph
- Panel "Graph Success Rate" rouge dans dashboard 11

---

## 🎯 Possible Causes

### 1. LLM API Failures (OpenAI/Anthropic Down)

**Likelihood**: High

**Description**:
Le provider LLM (OpenAI, Anthropic) connaît une panne ou un rate limiting sévère. Cela affecte tous les nodes du graph qui appellent le LLM (router, planner, response, agents).

**How to Verify**:
```bash
# Check LLM API call success rate
curl -s "http://localhost:9090/api/v1/query?query=rate(llm_api_calls_total{status=\"success\"}[5m])/rate(llm_api_calls_total[5m])*100" | jq '.data.result[0].value[1]'

# Check LLM errors in logs
docker-compose logs api --since=10m | grep -i "llm.*error\|openai.*error\|anthropic.*error"

# Check external status
curl -s https://status.openai.com/api/v2/status.json | jq '.status.description'
```

**Expected Output if This is the Cause**:
```
LLM success rate < 80%
Logs: "APIConnectionError: Connection to OpenAI failed"
OpenAI status: "Major Outage"
```

---

### 2. Database Connection Pool Exhaustion

**Likelihood**: Medium

**Description**:
Pool de connexions PostgreSQL saturé, empêchant les nodes d'accéder aux données (conversations, user context, checkpoints).

**How to Verify**:
```bash
# Check DB connection pool utilization
curl -s "http://localhost:9090/api/v1/query?query=(pg_stat_database_numbackends/pg_settings_max_connections)*100" | jq '.data.result[0].value[1]'

# Check DB connection errors
docker-compose logs api --since=10m | grep -i "database.*connection\|pool.*exhausted"

# Check active connections
docker-compose exec postgresql psql -U lia -c "SELECT count(*) FROM pg_stat_activity WHERE state='active';"
```

**Expected Output if This is the Cause**:
```
DB pool utilization > 95%
Logs: "psycopg2.pool.PoolError: connection pool exhausted"
Active connections: 95/100
```

---

### 3. Node Crashes / Exceptions in Graph Logic

**Likelihood**: High

**Description**:
Bugs dans les nodes (router_node, planner_node, etc.) causant des exceptions non catchées qui font crasher le graph.

**How to Verify**:
```bash
# Check error types distribution
curl -s "http://localhost:9090/api/v1/query?query=topk(5,sum by (error_type)(rate(langgraph_graph_errors_total[5m])))" | jq '.data.result'

# Check specific node failures
docker-compose logs api --since=10m | grep -E "router_node.*error|planner_node.*error|task_orchestrator.*error"

# Check Python tracebacks
docker-compose logs api --since=10m | grep -A 20 "Traceback"
```

**Expected Output if This is the Cause**:
```
Top error_type: "KeyError", "AttributeError", "ValidationError"
Logs: "KeyError: 'routing_history' at planner_node_v3.py:156"
Traceback shows specific code location
```

---

### 4. State Corruption / Checkpoint Failures

**Likelihood**: Low

**Description**:
Checkpoints LangGraph corrompus ou Redis indisponible, empêchant le graph de sauvegarder/restaurer son état.

**How to Verify**:
```bash
# Check Redis availability
curl -s "http://localhost:9090/api/v1/query?query=up{job=\"redis\"}" | jq '.data.result[0].value[1]'

# Check checkpoint save errors
docker-compose logs api --since=10m | grep -i "checkpoint.*error\|redis.*error"

# Test Redis connectivity
docker-compose exec redis redis-cli ping
```

**Expected Output if This is the Cause**:
```
Redis up: 0 (down)
Logs: "ConnectionError: Error connecting to Redis"
Redis ping: PONG (should work if Redis is up)
```

---

## 🔧 Diagnostic Steps

### Quick Health Check (< 2 minutes)

```bash
# 1. Check all services status
docker-compose ps

# 2. Check recent errors
docker-compose logs api --tail=100 | grep -i error | head -20

# 3. Check graph success rate trend
curl -s "http://localhost:9090/api/v1/query?query=(sum(rate(langgraph_graph_executions_total{status=\"success\"}[1m]))/sum(rate(langgraph_graph_executions_total[1m])))*100" | jq '.data.result[0].value[1]'
```

**Interprétation**:
- Si Redis/PostgreSQL down → Restart containers
- Si LLM errors dominants → Vérifier status OpenAI/Anthropic
- Si success rate 0% → Incident majeur, escalate immédiatement
- Si success rate 70-89% → Continuer investigation

---

### Deep Dive Investigation (5-10 minutes)

#### Step 1: Identifier les Error Types Dominants

```bash
# Top 5 error types par fréquence
curl -s "http://localhost:9090/api/v1/query?query=topk(5,sum by (error_type)(rate(langgraph_graph_errors_total[5m])))" | jq '.data.result[] | {error_type: .metric.error_type, rate: .value[1]}'
```

**What to Look For**:
- `GraphRecursionError`: Boucle infinie dans graph
- `ValidationError`: Problème schema Pydantic
- `KeyError`: State key manquant
- `LLMAPIError`: Problème provider LLM

---

#### Step 2: Analyser Distribution des Failures par Node

```bash
# Check quel node fail le plus
docker-compose logs api --since=10m | grep -E "router_node|planner_node|task_orchestrator|response_node|approval_gate" | grep -i error | awk '{print $5}' | sort | uniq -c | sort -rn
```

---

#### Step 3: Vérifier Corrélations avec Autres Alertes

```bash
# Check si d'autres alerts firing (cause commune)
curl -s http://localhost:9093/api/v2/alerts | jq '.[] | select(.status.state=="firing") | .labels.alertname'
```

**Corrélations communes**:
- `LangGraphHighLatencyP95` + `LangGraphLowSuccessRate` → LLM provider slow
- `DatabaseDown` + `LangGraphLowSuccessRate` → DB issue
- `LangGraphRecursionError` + `LangGraphLowSuccessRate` → Graph logic bug

---

### Automated Diagnostic Script

```bash
# Diagnostic complet automatisé
cd infrastructure/observability/scripts
./diagnose_langgraph.sh --component=graph-execution --verbose
```

---

## ✅ Resolution Steps

### Immediate Mitigation (Stop the Bleeding)

#### Option A: Restart API Containers (Low Risk)

```bash
# Restart API containers (conserve state Redis/PostgreSQL)
docker-compose restart api

# Wait 30s and verify
sleep 30
curl -s "http://localhost:9090/api/v1/query?query=(sum(rate(langgraph_graph_executions_total{status=\"success\"}[1m]))/sum(rate(langgraph_graph_executions_total[1m])))*100" | jq '.data.result[0].value[1]'
```

**Pros**: Rapide (30s), résout souvent les memory leaks/connections stuck
**Cons**: Downtime 30s, perd conversations en cours (non-checkpointed)
**Duration**: 30 secondes

---

#### Option B: Rollback to Previous Version (Medium Risk)

```bash
# Si déploiement récent causant le problème
cd /path/to/lia
git log --oneline -5  # Identifier commit stable précédent
git checkout [stable-commit-hash]
docker-compose build api
docker-compose up -d api

# Verify
sleep 60
curl -s "http://localhost:9090/api/v1/query?query=(sum(rate(langgraph_graph_executions_total{status=\"success\"}[1m]))/sum(rate(langgraph_graph_executions_total[1m])))*100" | jq '.data.result[0].value[1]'
```

**Pros**: Revient à version stable connue
**Cons**: Perd nouvelles features, downtime ~2min
**Duration**: 2-3 minutes

---

#### Option C: Disable Problematic Node (High Risk - Use Only if Identified)

Si un node spécifique cause 100% des failures:

```bash
# Example: Si router_node fail systématiquement, bypass via config
# ATTENTION: Only if router is the root cause
docker-compose exec api sh -c 'echo "ROUTER_FALLBACK_ENABLED=true" >> .env'
docker-compose restart api
```

**Pros**: Isole le problème
**Cons**: Réduit fonctionnalités, peut causer autres effets de bord
**Duration**: 1 minute

---

### Verification After Mitigation

```bash
# 1. Verify alert stopped firing
curl -s http://localhost:9093/api/v2/alerts | jq '.[] | select(.labels.alertname=="LangGraphLowSuccessRate") | .status.state'
# Expected: "inactive" ou absent

# 2. Verify success rate back to normal
curl -s "http://localhost:9090/api/v1/query?query=(sum(rate(langgraph_graph_executions_total{status=\"success\"}[5m]))/sum(rate(langgraph_graph_executions_total[5m])))*100" | jq '.data.result[0].value[1]'
# Expected: >95%

# 3. Verify no more errors in logs
docker-compose logs api --tail=50 | grep -i error | wc -l
# Expected: 0 ou très peu

# 4. Test avec vraie requête utilisateur
curl -X POST http://localhost:8000/api/v1/conversations \
  -H "Authorization: Bearer [token]" \
  -H "Content-Type: application/json" \
  -d '{"message": "Test après mitigation"}'
# Expected: 200 OK avec réponse
```

---

### Root Cause Fix (Permanent Solution)

#### 1. Investigation Approfondie

```bash
# Capturer logs détaillés période incident
docker-compose logs api --since=30m > /tmp/incident_logs.txt

# Analyser patterns
cat /tmp/incident_logs.txt | grep -E "error|exception|failed" | awk '{print $5, $6, $7}' | sort | uniq -c | sort -rn | head -20
```

#### 2. Identification Root Cause

Questions à se poser:
- [ ] Le problème est-il apparu après un déploiement? → Rollback ou fix code
- [ ] Y a-t-il eu un pic de traffic? → Scaling issue
- [ ] Un service externe est-il down? → Ajout retry logic + circuit breaker
- [ ] Logs montrent-ils une erreur récurrente spécifique? → Fix bug code

#### 3. Implementation du Fix

Selon root cause identifiée:

**Cas A - Bug Code**:
```bash
# Créer fix
cd apps/api/src/domains/agents/nodes
# Fix bug dans node concerné
git add [files]
git commit -m "fix(langgraph): [description bug]"

# Test local
pytest tests/unit/infrastructure/observability/test_metrics_langgraph_execution.py -v

# Deploy
docker-compose build api
docker-compose up -d api
```

**Cas B - LLM Provider Reliability**:
```python
# Ajouter retry logic + circuit breaker dans llm_factory.py
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10)
)
async def get_llm(...):
    # Existing code
```

**Cas C - Database Connection Pool**:
```python
# Augmenter pool size dans database.py
SQLALCHEMY_POOL_SIZE = 50  # Was 20
SQLALCHEMY_MAX_OVERFLOW = 100  # Was 50
```

#### 4. Testing

```bash
# Test unitaires
pytest tests/unit/infrastructure/observability/test_metrics_langgraph_execution.py -v

# Test end-to-end
./scripts/test_conversation_flow.sh

# Load test (si scaling issue)
cd load_tests
locust -f test_conversations.py --host=http://localhost:8000 --users=100 --spawn-rate=10
```

#### 5. Deployment

```bash
# Build nouvelle image
docker-compose build api

# Deploy avec health check
docker-compose up -d api
sleep 30
curl http://localhost:8000/health

# Monitor success rate 15 minutes
watch -n 10 'curl -s "http://localhost:9090/api/v1/query?query=(sum(rate(langgraph_graph_executions_total{status=\"success\"}[5m]))/sum(rate(langgraph_graph_executions_total[5m])))*100" | jq ".data.result[0].value[1]"'
```

#### 6. Monitoring Post-Fix

Surveiller pendant **24 heures**:
- Graph success rate (target: >98%)
- P95 latency (target: <10s)
- Error rate (target: <0.1/s)
- Aucune alerte related firing

---

## 📈 Related Dashboards & Queries

### Grafana Dashboards
- **11 - LangGraph Framework Observability**: `http://localhost:3000/d/langgraph-framework-observability`
  - Panel: "Graph Success Rate (%)"
  - Panel: "Graph Executions by Status"
  - Panel: "Graph Errors by Type"

### Prometheus Queries

```promql
# Success rate dernières 30 minutes (trend)
(
  sum(rate(langgraph_graph_executions_total{status="success"}[30m]))
  /
  sum(rate(langgraph_graph_executions_total[30m]))
) * 100

# Error rate par type
sum by (error_type) (rate(langgraph_graph_errors_total[5m]))

# Corrélation success rate vs latency
(
  sum(rate(langgraph_graph_executions_total{status="success"}[5m]))
  /
  sum(rate(langgraph_graph_executions_total[5m]))
) * 100
and
histogram_quantile(0.95, rate(langgraph_graph_duration_seconds_bucket[5m]))
```

### Logs Queries

```bash
# Errors par node (dernières 30 minutes)
docker-compose logs api --since=30m | grep -E "router_node|planner_node|task_orchestrator|response_node" | grep -i error

# Top exceptions
docker-compose logs api --since=30m | grep "Traceback" -A 10 | grep "raise" | sort | uniq -c | sort -rn
```

---

## 📚 Related Runbooks

- **LangGraphHighLatencyP95**: [high-latency.md](./high-latency.md) - Souvent corrélé
- **LangGraphHighErrorRate**: [high-error-rate.md](./high-error-rate.md) - Même root cause
- **LangGraphSystemDegraded**: [system-degraded.md](./system-degraded.md) - Alert composite

---

## 🔄 Common Patterns & Known Issues

### Pattern 1: LLM Provider Transient Failures
**Description**: OpenAI/Anthropic ont micro-outages fréquents (1-2 min)
**Resolution**: Retry logic automatique résout (no action needed)
**Prevention**: Circuit breaker déjà implémenté

### Pattern 2: Database Connection Leaks
**Description**: Connexions non fermées après exceptions
**Resolution**: Restart API containers
**Prevention**: Code review pour ensure proper connection cleanup dans `finally` blocks

### Known Issue 1: GraphRecursionError sur Router Fallback Loop
**Symptom**: Router → Response → Router loop infini
**Workaround**: Redémarrer API (reset graph state)
**Tracking**: GitHub issue #2456
**Fix**: PR #2489 (conditional edge fix)

---

## 🆘 Escalation

### When to Escalate

Escalader immédiatement si:
- [x] Success rate < 50% pendant >5 minutes
- [x] Mitigation (restart) n'a pas fonctionné après 2 tentatives
- [x] Impact utilisateurs > 100 conversations failed/minute
- [x] Multiple related alerts firing (SystemDegraded)
- [x] Suspicion d'attaque DoS
- [x] GraphRecursionError récurrent (boucle infinie)

### Escalation Path

**Level 1 - On-Call Engineer** (0-15min):
- Slack: `#ops-alerts` (auto-notification)
- PagerDuty: Auto-page on-call

**Level 2 - Team Lead** (15-30min):
- Slack: `#incidents-critical`
- Phone: +33 X XX XX XX XX

**Level 3 - CTO** (30min+):
- Email: cto@lia.com
- Phone: Emergency contact

### Escalation Template Message

```
🚨 ALERT ESCALATION - LangGraph Low Success Rate 🚨

Alert: LangGraphLowSuccessRate
Severity: CRITICAL
Success Rate: [XX]% (threshold: 90%)
Duration: [XX] minutes
Impact: [XX] failed conversations/minute

Actions Taken:
- ✅ Restarted API containers (no improvement)
- ✅ Checked LLM provider status (normal)
- ✅ Analyzed logs (root cause: [description])

Current Status: Degraded - Success rate still at [XX]%

Need: [Senior engineer assistance / Rollback authorization / etc.]

Dashboard: http://localhost:3000/d/langgraph-framework-observability
Logs: /tmp/incident_logs.txt
```

---

## 📝 Post-Incident Actions

### Immediate (< 1h après résolution)
- [ ] Créer incident report dans Jira
- [ ] Notifier stakeholders résolution (Slack `#announcements`)
- [ ] Documenter timeline incident
- [ ] Capturer logs/métriques pour post-mortem (archiver dans S3)

### Short-Term (< 24h après résolution)
- [ ] Mettre à jour ce runbook avec learnings
- [ ] Créer GitHub issue pour fix permanent (si workaround utilisé)
- [ ] Review alert threshold (si false positive)
- [ ] Ajouter monitoring blind spot découvert

### Long-Term (< 1 semaine après résolution)
- [ ] Post-mortem meeting avec équipe
- [ ] Documentation learnings dans docs/incidents/
- [ ] Implementation action items post-mortem
- [ ] Update architecture doc si nécessaire

---

## 📅 Runbook Metadata

**Created**: 2025-11-22
**Last Updated**: 2025-11-22
**Maintainer**: Équipe Observability
**Version**: 1.0.0
**Related GitHub Issues**: Phase 2.5 - LangGraph Observability

**Changelog**:
- **2025-11-22**: Création initiale runbook (Phase 2.5 P1)

---

**Note**: Ce runbook doit être mis à jour après chaque incident pour rester pertinent.
