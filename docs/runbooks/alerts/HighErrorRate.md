# HighErrorRate - Runbook

**Severity**: critical
**Component**: api
**Impact**: Utilisateurs reçoivent des erreurs HTTP 5xx, fonctionnalités dégradées ou indisponibles
**SLA Impact**: Yes - Breaches availability SLA (99.9% uptime target)

---

## 📊 Alert Definition

**Alert Name**: `HighErrorRate`

**Prometheus Expression**:
```promql
(
  sum(rate(http_requests_total{status=~"5.."}[5m])) by (service)
  /
  sum(rate(http_requests_total[5m])) by (service)
) * 100 > <<< ALERT_API_ERROR_RATE_CRITICAL_PERCENT >>>
```

**Threshold**:
- **Production**: 3% (strictest - early detection)
- **Staging**: 8% (relaxed for testing)
- **Development**: 20% (very relaxed)

**Firing Duration**: `for: 5m`

**Labels**:
- `severity`: critical
- `component`: api
- `service`: [service name from metric]

---

## 🔍 Symptoms

### What Users See
- Pages affichent "500 Internal Server Error"
- Requêtes API échouent avec erreurs serveur
- Fonctionnalités agents (chat, recherche contacts, emails) indisponibles
- Messages d'erreur génériques dans l'interface web
- Timeouts sur certaines opérations

### What Ops See
- Métrique `http_requests_total{status=~"5.."}` en hausse dans Prometheus
- Panel "API Error Rate" rouge dans Grafana
- Logs API contiennent exceptions Python/FastAPI
- AlertManager montre `HighErrorRate` firing
- Slack/Email notifications d'erreurs critiques

---

## 🎯 Possible Causes

### 1. Database Connection Pool Exhaustion

**Likelihood**: **High** (cause #1 la plus fréquente)

**Description**:
Le pool de connexions PostgreSQL est saturé. Nouvelles requêtes ne peuvent pas obtenir de connexion, causant exceptions `TimeoutError` ou `PoolTimeout`. LIA utilise SQLAlchemy avec pool configuré dans `apps/api/src/infrastructure/database.py`.

**How to Verify**:
```bash
# Vérifier nombre connexions actives vs max
docker-compose exec postgres psql -U lia -c "SELECT count(*) as active_connections FROM pg_stat_activity WHERE datname='lia';"

# Vérifier pool config (devrait être visible dans logs)
docker-compose logs api | grep -i "pool" | tail -20

# Vérifier si connections en attente
docker-compose logs api | grep -i "timeout" | grep -i "pool"
```

**Expected Output if This is the Cause**:
```
active_connections
-------------------
                30
(1 row)

# Si active_connections ≈ pool max_size (généralement 10-20), c'est la cause
# Logs montreront: "QueuePool limit of size 10 overflow 10 reached"
```

---

### 2. LLM API Failures (Anthropic Claude)

**Likelihood**: **High**

**Description**:
Anthropic Claude API (clé composant de LIA) retourne erreurs 500/503 ou timeouts. Agents ne peuvent pas générer réponses, causant exceptions non-catchées qui remontent comme erreurs HTTP 500. Vérifier `apps/api/src/infrastructure/llm/anthropic_client.py`.

**How to Verify**:
```bash
# Vérifier métriques LLM API failures
curl -s "http://localhost:9090/api/v1/query?query=llm_api_calls_total{result='failed'}" | jq '.data.result'

# Vérifier logs pour erreurs Anthropic
docker-compose logs api | grep -i "anthropic" | grep -i "error" | tail -20

# Vérifier status Anthropic API
curl -s https://status.anthropic.com/api/v2/status.json | jq '.status.description'
```

**Expected Output if This is the Cause**:
```
# Métriques montreront spike en llm_api_calls_total{result="failed"}
# Logs: "AnthropicAPIError: 503 Service Unavailable"
# Status: "Partial Outage" ou "Major Outage"
```

---

### 3. Unhandled Python Exceptions in Code

**Likelihood**: **Medium**

**Description**:
Bug introduit récemment cause exceptions non-catchées (KeyError, AttributeError, TypeError, etc.). FastAPI middleware convertit automatiquement exceptions non-gérées en 500. Vérifier déploiements récents.

**How to Verify**:
```bash
# Extraire stack traces récentes
docker-compose logs api --since=15m | grep -A 10 "Traceback (most recent call last)"

# Identifier exceptions les plus fréquentes
docker-compose logs api --since=1h | grep "Error" | sed 's/.*Error: //' | sort | uniq -c | sort -rn | head -10

# Vérifier git log pour commits récents
git log --since="1 day ago" --oneline --all
```

**Expected Output if This is the Cause**:
```
# Traceback montrera ligne de code spécifique:
  File "/app/src/domains/agents/nodes/router_node_v3.py", line 142, in route
    context = state["context"]["user_query"]  # KeyError si manquant
KeyError: 'user_query'

# Pattern répétitif du même error
```

---

### 4. Memory Pressure / OOM

**Likelihood**: **Medium**

**Description**:
Conteneur API manque de mémoire. Python garbage collector ralentit ou process killed par OOM killer. Checkpoints LangGraph trop gros en mémoire causant slowdowns/crashes.

**How to Verify**:
```bash
# Vérifier usage mémoire conteneur API
docker stats --no-stream api

# Vérifier OOM kills dans logs système
docker-compose logs api | grep -i "killed"
dmesg | grep -i "out of memory"

# Vérifier taille checkpoints en cours
curl -s "http://localhost:9090/api/v1/query?query=checkpoint_size_bytes" | jq '.data.result'
```

**Expected Output if This is the Cause**:
```
# docker stats montre MEM USAGE proche de LIMIT
CONTAINER  MEM USAGE / LIMIT     MEM %
api        1.95GiB / 2GiB       97.5%

# Logs: "Killed" (OOM killer)
# Checkpoint size > 50KB (anormal)
```

---

### 5. External Dependency Timeout (Redis, OAuth Providers)

**Likelihood**: **Low-Medium**

**Description**:
Redis (rate limiting) ou Google OAuth API timeout ou indisponible. Requêtes bloquent jusqu'à timeout, puis échouent avec 500.

**How to Verify**:
```bash
# Vérifier Redis connectivity
docker-compose exec redis redis-cli ping

# Vérifier latency Redis
docker-compose exec redis redis-cli --latency

# Vérifier logs OAuth errors
docker-compose logs api | grep -i "oauth" | grep -i "error"
```

**Expected Output if This is the Cause**:
```
# Redis down: "(error) NOAUTH Authentication required" ou connection refused
# OAuth: "OAuthProviderError: Request timeout" dans logs
```

---

## 🔧 Diagnostic Steps

### Quick Health Check (< 2 minutes)

**Objectif**: Identifier rapidement quel composant est défaillant.

```bash
# 1. Vérifier tous containers actifs
docker-compose ps

# 2. Vérifier logs API récents pour stack traces
docker-compose logs api --tail=100 | grep -E "(ERROR|Exception|Traceback)" | tail -20

# 3. Vérifier error rate actuelle
curl -s "http://localhost:9090/api/v1/query?query=sum(rate(http_requests_total{status=~\"5..\"}[5m]))*100/sum(rate(http_requests_total[5m]))" | jq '.data.result[0].value[1]'

# 4. Vérifier database connections
docker-compose exec postgres psql -U lia -c "SELECT count(*) FROM pg_stat_activity WHERE datname='lia';"

# 5. Vérifier Redis health
docker-compose exec redis redis-cli ping
```

**Interprétation**:
- Si error rate > 10%: Incident majeur, mitigation immédiate requise
- Si logs montrent exception répétitive: Bug code récent probable
- Si DB connections ≈ max: Pool exhaustion
- Si Redis down: Rate limiting/cache failing
- Si containers restarting: OOM ou crash loop

---

### Deep Dive Investigation (5-10 minutes)

**Objectif**: Identifier cause racine exacte.

#### Step 1: Analyser Distribution Erreurs par Endpoint
```bash
# Erreurs par path
docker-compose logs api --since=15m | grep "\"status\":5" | grep -oP '"path":"[^"]*"' | sort | uniq -c | sort -rn | head -10

# Si un endpoint spécifique domine, investiguer ce endpoint
# Exemple: Si /api/agents/chat représente 80% des erreurs → problème agents
```

---

#### Step 2: Vérifier Corrélations avec Autres Métriques
```bash
# Vérifier si latency élevée aussi (souvent corrélé)
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.99,sum(rate(http_request_duration_seconds_bucket[5m]))by(le))" | jq '.data.result'

# Vérifier LLM failures
curl -s "http://localhost:9090/api/v1/query?query=rate(llm_api_calls_total{result=\"failed\"}[5m])" | jq '.data.result'

# Vérifier memory/CPU
docker stats --no-stream
```

---

#### Step 3: Examiner Stack Traces Détaillés
```bash
# Extraire top 3 exceptions les plus fréquentes avec stack traces
docker-compose logs api --since=30m | awk '/Traceback/,/^[^ ]/' | grep -v "^$" > /tmp/errors.txt
cat /tmp/errors.txt | grep "Error:" | sort | uniq -c | sort -rn | head -3

# Analyser première stack trace complète
head -50 /tmp/errors.txt
```

---

#### Step 4: Vérifier Déploiements Récents
```bash
# Vérifier image Docker utilisée
docker-compose images api

# Vérifier si redéploiement récent
docker inspect lia_api | jq '.[0].State.StartedAt'

# Vérifier commits récents qui pourraient avoir introduit bug
git log --since="2 hours ago" --oneline -- apps/api/
```

---

### Automated Diagnostic Script

Pour gagner du temps, utilisez le script diagnostic automatisé:

```bash
infrastructure/observability/scripts/diagnose_api_errors.sh
```

Ce script exécute automatiquement tous les checks ci-dessus et génère rapport synthétique.

---

## ✅ Resolution Steps

### Immediate Mitigation (Stop the Bleeding)

#### Option A: Restart API Container (fastest - 30 seconds)
```bash
# Restart rapide pour clear memory/connections
docker-compose restart api

# Vérifier logs démarrage
docker-compose logs -f api

# Attendre "Application startup complete"
# Vérifier error rate diminue
curl -s "http://localhost:9090/api/v1/query?query=sum(rate(http_requests_total{status=~\"5..\"}[1m]))*100/sum(rate(http_requests_total[1m]))" | jq '.data.result[0].value[1]'
```

**Pros**: Très rapide, résout pool exhaustion, memory leaks temporaires
**Cons**: Downtime ~20s, ne résout pas bugs code
**Duration**: 30 seconds total

---

#### Option B: Scale Up API Replicas (si disponible)
```bash
# Si multi-replica setup
docker-compose up -d --scale api=3

# Vérifie load balancing fonctionne
docker-compose ps api
```

**Pros**: Pas de downtime, distribue charge
**Cons**: Nécessite setup multi-replica, ne résout pas bug
**Duration**: 1 minute

---

#### Option C: Rollback Déploiement Récent
```bash
# Si deployment récent identifié comme cause
git log --oneline -1  # Note current commit
git checkout [commit_hash_précédent]

# Rebuild et restart
docker-compose build api
docker-compose restart api

# Vérifier logs
docker-compose logs -f api
```

**Pros**: Résout bugs introduits récemment
**Cons**: Downtime ~2min, perd fonctionnalités récentes
**Duration**: 2-3 minutes

---

### Verification After Mitigation

```bash
# 1. Vérifier alert ne fire plus (attendre 5min pour "for: 5m")
watch -n 10 'curl -s http://localhost:9093/api/v2/alerts | jq ".[] | select(.labels.alertname==\"HighErrorRate\") | .status.state"'

# 2. Vérifier error rate revenu à la normale
curl -s "http://localhost:9090/api/v1/query?query=sum(rate(http_requests_total{status=~\"5..\"}[5m]))*100/sum(rate(http_requests_total[5m]))" | jq '.data.result[0].value[1]'

# 3. Vérifier logs ne montrent plus stack traces
docker-compose logs api --tail=50 | grep -c "Traceback"

# 4. Tester endpoints manuellement
curl -i http://localhost:8000/api/health
curl -i http://localhost:8000/api/agents/chat -X POST -H "Content-Type: application/json" -d '{"query":"test"}'
```

**Expected After Successful Mitigation**:
- Error rate < 1%
- Alert status: "inactive" ou absent
- Logs clean (pas de Traceback récent)
- Health check returns 200 OK
- Chat endpoint fonctionne

---

### Root Cause Fix (Permanent Solution)

**Objectif**: Résoudre définitivement pour éviter récurrence.

#### 1. Investigation Approfondie

Si cause = **Pool Exhaustion**:
```bash
# Analyser patterns de connexions
docker-compose exec postgres psql -U lia -c "SELECT state, count(*) FROM pg_stat_activity WHERE datname='lia' GROUP BY state;"

# Identifier queries lentes qui gardent connexions
docker-compose exec postgres psql -U lia -c "SELECT pid, now() - query_start as duration, state, query FROM pg_stat_activity WHERE state != 'idle' AND datname='lia' ORDER BY duration DESC;"
```

**Fix**: Augmenter pool size dans `apps/api/src/infrastructure/database.py`:
```python
# Avant
engine = create_engine(database_url, pool_size=10, max_overflow=20)

# Après
engine = create_engine(database_url, pool_size=20, max_overflow=40)
```

---

Si cause = **LLM API Failures**:
```bash
# Vérifier status Anthropic
curl https://status.anthropic.com/api/v2/status.json

# Vérifier quota usage
docker-compose logs api | grep -i "rate limit"
```

**Fix**: Implémenter retry logic avec backoff dans `apps/api/src/infrastructure/llm/`:
```python
@retry(wait=wait_exponential(multiplier=1, min=4, max=10), stop=stop_after_attempt(3))
async def call_anthropic_api(...):
    ...
```

---

Si cause = **Bug Code**:
```bash
# Identifier fichier/ligne exacte depuis stack trace
# Ajouter error handling approprié

# Exemple: KeyError dans router_node_v3.py
# Fix: Ajouter validation
```

**Fix**: Add defensive code + tests
```python
# Avant
context = state["context"]["user_query"]  # KeyError si manquant

# Après
context = state.get("context", {}).get("user_query")
if context is None:
    logger.error("Missing user_query in state")
    raise ValueError("Invalid state: user_query required")
```

---

#### 2. Testing

```bash
# Tests unitaires pour fix
cd apps/api
pytest tests/unit/[module_fixé] -v

# Tests intégration
pytest tests/integration/test_api.py -v

# Load test pour valider pool size
# (si fix = augmentation pool)
ab -n 1000 -c 50 http://localhost:8000/api/health
```

---

#### 3. Deployment

```bash
# Build nouvelle image
docker-compose build api

# Deploy avec zero-downtime (si multi-replica)
docker-compose up -d --no-deps --scale api=2 api

# Ou restart simple
docker-compose restart api
```

---

#### 4. Monitoring Post-Fix

**Surveiller pendant 24-48h**:
- Error rate reste < 1%
- Pool connections n'atteint pas max
- Pas de nouveaux patterns d'erreurs
- Latency reste normale

```bash
# Setup watch sur métriques clés
watch -n 60 'echo "Error Rate:" && curl -s "http://localhost:9090/api/v1/query?query=sum(rate(http_requests_total{status=~\"5..\"}[5m]))*100/sum(rate(http_requests_total[5m]))" | jq -r ".data.result[0].value[1]" && echo "DB Connections:" && docker-compose exec postgres psql -U lia -tc "SELECT count(*) FROM pg_stat_activity WHERE datname=\"lia\";"'
```

---

## 📈 Related Dashboards & Queries

### Grafana Dashboards
- **API Overview**: `http://localhost:3000/d/api-overview`
  - Panel: "Error Rate by Endpoint"
  - Panel: "HTTP Status Codes Distribution"
- **Database Monitoring**: `http://localhost:3000/d/postgresql`
  - Panel: "Active Connections"
  - Panel: "Slow Queries"

### Prometheus Queries
```promql
# Error rate par endpoint
sum(rate(http_requests_total{status=~"5.."}[5m])) by (path) * 100 /
sum(rate(http_requests_total[5m])) by (path)

# Top 5 endpoints avec le plus d'erreurs
topk(5, sum(rate(http_requests_total{status=~"5.."}[5m])) by (path))

# Ratio erreurs/total sur 24h
sum(increase(http_requests_total{status=~"5.."}[24h])) /
sum(increase(http_requests_total[24h]))
```

### Logs Queries
```bash
# Erreurs par type dans dernière heure
docker-compose logs api --since=1h | grep -oP '\w+Error:' | sort | uniq -c | sort -rn

# Erreurs avec context (10 lignes avant/après)
docker-compose logs api | grep -B 10 -A 10 "ERROR"
```

---

## 📚 Related Runbooks

- **[CriticalLatencyP99](./CriticalLatencyP99.md)** - Souvent corrélé (errors causent latency)
- **[CriticalDatabaseConnections](./CriticalDatabaseConnections.md)** - Cause fréquente de HighErrorRate
- **[LLMAPIFailureRateHigh](./LLMAPIFailureRateHigh.md)** - LLM failures → API errors
- **[ContainerDown](./ContainerDown.md)** - Si mitigation échoue, container peut crash

---

## 🔄 Common Patterns & Known Issues

### Pattern 1: Monday Morning Spike
**Description**: Error rate spike tous les lundis 9h-10h (retour weekend, batch processes)
**Resolution**: Pre-warm caches dimanche soir, scale up preventive lundi matin
**Prevention**: Scheduled scaling + cache warming cron job

### Pattern 2: Post-Deployment Regression
**Description**: Error rate spike dans 15min après déploiement nouveau code
**Resolution**: Rollback immédiat si error rate > 5% post-deploy
**Prevention**: Canary deployments, feature flags, meilleure test coverage

### Known Issue 1: LangGraph State Serialization Errors
**Symptom**: `TypeError: Object of type X is not JSON serializable` dans checkpoints
**Workaround**: Restart API, puis fix data models pour être serializable
**Tracking**: GitHub issue #[TODO]

### Known Issue 2: Anthropic Rate Limits During Peak Hours
**Symptom**: `RateLimitError` en masse 14h-16h (US peak hours)
**Workaround**: Implement request queuing avec backoff
**Tracking**: GitHub issue #[TODO]

---

## 🆘 Escalation

### When to Escalate

Escalader immédiatement si:
- [ ] Error rate > 20% pendant 10+ minutes
- [ ] Mitigation n'a pas réduit error rate après 2 tentatives
- [ ] Impact > 100 utilisateurs actifs
- [ ] Suspicion de data corruption ou security breach
- [ ] Perte de données conversations en cours
- [ ] Root cause inconnue après 30min investigation

### Escalation Path

**Level 1 - Senior Backend Engineer** (0-15min):
- **Contact**: Lead Backend Dev
- **Slack**: #backend-oncall
- **Escalate if**: Cannot identify root cause in 15min

**Level 2 - Tech Lead / Architect** (15-30min):
- **Contact**: Tech Lead
- **Slack**: #incidents-critical
- **Phone**: [On-call rotation number]
- **Escalate if**: Cannot mitigate in 30min or architectural decision needed

**Level 3 - CTO** (30min+):
- **Contact**: CTO
- **Email**: cto@lia.com
- **Phone**: [Emergency number]
- **Escalate if**: Major outage >30min, data loss, security breach, or need business decision (rollback prod feature)

### Escalation Template Message

```
🚨 ALERT ESCALATION - HighErrorRate 🚨

Alert: HighErrorRate
Severity: CRITICAL
Duration: [X] minutes
Current Error Rate: [Y]%

Impact:
- [X] active users affected
- [List impacted features]

Actions Taken:
- [Timestamp] Restarted API container - no improvement
- [Timestamp] Checked DB connections - pool at 95%
- [Timestamp] Attempted pool size increase - pending redeploy

Current Status: Error rate still at [Y]%, trending [up/down/stable]

Root Cause: [Suspected cause or "Unknown - investigating"]

Need: [Immediate assistance / Architectural decision / Business approval for rollback]

Dashboards:
- Grafana: http://localhost:3000/d/api-overview
- Prometheus: http://localhost:9090/alerts

Next Steps: [What you plan to do next]
```

---

## 📝 Post-Incident Actions

### Immediate (< 1h après résolution)

- [ ] Créer incident report dans GitHub issues avec label `incident`
- [ ] Notifier #general sur Slack de la résolution
- [ ] Documenter timeline exacte dans incident report
- [ ] Capturer logs/métriques période incident pour analyse
  ```bash
  docker-compose logs api --since="[incident_start]" --until="[incident_end]" > incident_logs_$(date +%Y%m%d_%H%M).txt
  ```

### Short-Term (< 24h après résolution)

- [ ] Mettre à jour ce runbook si gaps/learnings identifiés
- [ ] Créer GitHub issues pour permanent fixes (si workaround utilisé)
- [ ] Review alert threshold si false positive (trop sensible)
- [ ] Ajouter monitoring pour gaps découverts (blind spots)
- [ ] Partager learnings avec équipe dans Slack #engineering

### Long-Term (< 1 semaine après résolution)

- [ ] Post-mortem meeting avec équipe (format blameless)
- [ ] Documentation complète des root causes et fixes
- [ ] Implementation de tous les action items du post-mortem
- [ ] Update architecture docs si nécessaire
- [ ] Review et amélioration test coverage pour prévenir récurrence

---

## 📋 Incident Report Template

```markdown
# Incident Report - HighErrorRate - [Date]

## Summary
[Résumé 2-3 lignes: Quoi, impact, durée, résolution]

## Timeline
- **09:15** - Alert HighErrorRate fired (error rate: 8%)
- **09:17** - On-call engineer acknowledged alert
- **09:20** - Investigation started: checked logs, found DB pool exhaustion
- **09:25** - Mitigation: Restarted API container
- **09:27** - Error rate dropped to 2%
- **09:35** - Alert resolved (error rate: 0.5%)
- **10:00** - Root cause fix deployed (increased pool size)

## Impact
- **Users Affected**: ~50 concurrent users (15% of active users)
- **Duration**: 20 minutes (09:15-09:35)
- **Features Impacted**: Agent chat, contact search
- **Revenue Impact**: Minimal (no conversions lost)
- **SLA Impact**: Yes - 20min downtime breaches 99.9% monthly SLA

## Root Cause
Database connection pool (size: 10) was exhausted due to:
1. Increased traffic from new marketing campaign (+40% users)
2. Slow queries on contacts table (missing index on email field)
3. Connection leak in OAuth callback code (connections not properly closed)

## Resolution
**Immediate**: Restarted API container (cleared stuck connections)
**Permanent**:
1. Increased pool size from 10 to 20 (config change)
2. Added index on contacts.email (migration deployed)
3. Fixed connection leak in OAuth code (PR #[X] merged)

## Action Items
- [x] Increase DB pool size - Owner: Backend Team - Done: 2025-11-22
- [x] Add missing index - Owner: DB Team - Done: 2025-11-22
- [ ] Fix OAuth connection leak - Owner: Auth Team - Due: 2025-11-25
- [ ] Add monitoring for pool utilization - Owner: SRE - Due: 2025-11-30
- [ ] Load testing with higher traffic - Owner: QA - Due: 2025-12-05

## Prevention
- **Monitoring**: Added alert for DB pool >70% utilization (early warning)
- **Testing**: Added load tests simulating 2x traffic
- **Code**: Implemented connection pooling best practices across codebase
- **Process**: All DB queries now reviewed for indexing before merge

## Lessons Learned
- Need better capacity planning for marketing campaigns
- Missing indexes cause cascading failures (slow query → pool exhaustion → errors)
- Faster incident response possible with better runbooks (this one!)
```

---

## 🔗 Additional Resources

### Documentation
- [LIA Architecture Overview](../../architecture/OVERVIEW.md)
- [FastAPI Error Handling Guide](https://fastapi.tiangolo.com/tutorial/handling-errors/)
- [SQLAlchemy Connection Pooling](https://docs.sqlalchemy.org/en/20/core/pooling.html)

### Code References
- API Error Handlers: `apps/api/src/main.py` (exception handlers)
- Database Config: `apps/api/src/infrastructure/database.py` (pool config)
- LLM Client: `apps/api/src/infrastructure/llm/anthropic_client.py` (error handling)

### External Resources
- [Google SRE Book - Handling Overload](https://sre.google/sre-book/handling-overload/)
- [Prometheus Best Practices - Alerting](https://prometheus.io/docs/practices/alerting/)

---

## 📅 Runbook Metadata

**Created**: 2025-11-22
**Last Updated**: 2025-11-22
**Maintainer**: Backend Team
**Version**: 1.0
**Related GitHub Issues**: #31 (Phase 1.3 - Runbooks)

**Changelog**:
- **2025-11-22**: Initial creation (Phase 1.3)

---

## ✅ Runbook Validation Checklist

- [x] Alert definition verified against alerts.yml.template
- [ ] All bash commands tested and functional (**TODO**: Test in real environment)
- [ ] Links to dashboards validated (**TODO**: Create actual dashboards)
- [ ] Escalation path confirmed with team (**TODO**: Get real contacts)
- [ ] At least 1 dry-run of runbook performed (**TODO**: Schedule dry-run)
- [ ] Review by 2+ team members (**TODO**: Peer review)
- [ ] Message templates tested (**TODO**: Test Slack integration)

---

**Note**: Ce runbook sera mis à jour après chaque incident HighErrorRate pour rester pertinent et refléter learnings réels.
