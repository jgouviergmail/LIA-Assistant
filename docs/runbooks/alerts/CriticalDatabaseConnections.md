# CriticalDatabaseConnections - Runbook

**Severity**: critical
**Component**: postgresql
**Impact**: Nouvelles requêtes échouent, service outage imminent, erreurs cascading dans API
**SLA Impact**: Yes - Breaches availability SLA, causes HighErrorRate alert

---

## 📊 Alert Definition

**Alert Name**: `CriticalDatabaseConnections`

**Prometheus Expression**:
```promql
(
  pg_stat_database_numbackends{datname="lia"}
  /
  pg_settings_max_connections
) * 100 > <<< ALERT_DB_CONNECTIONS_CRITICAL_PERCENT >>>
```

**Threshold**:
- **Production**: 85% (strict - early warning before saturation)
- **Staging**: 95% (relaxed - test environment tolerance)
- **Development**: 98% (very relaxed - local dev setup)

**Firing Duration**: `for: 2m`

**Labels**:
- `severity`: critical
- `component`: postgresql
- `datname`: lia

**Related Alert**: `HighDatabaseConnections` (warning at lower threshold)

---

## 🔍 Symptoms

### What Users See
- Erreurs "500 Internal Server Error" sur toutes les requêtes
- Timeouts lors du chargement de pages
- Fonctionnalités complètement indisponibles
- Messages "Service temporarily unavailable"
- Impossible de créer nouvelles conversations
- Recherche contacts/emails ne fonctionne pas

### What Ops See
- Métrique `pg_stat_database_numbackends` proche de `pg_settings_max_connections`
- Alert `CriticalDatabaseConnections` firing dans AlertManager
- Alert `HighErrorRate` co-firing (causé par DB connection failures)
- Logs API: `sqlalchemy.exc.TimeoutError: QueuePool limit exceeded`
- Logs API: `psycopg2.OperationalError: FATAL: sorry, too many clients already`
- Grafana panel "DB Connections" en rouge
- Prometheus query montre utilisation >85% connections

---

## 🎯 Possible Causes

### 1. Connection Pool Saturation (Application Level)

**Likelihood**: **High** (cause #1 la plus fréquente)

**Description**:
SQLAlchemy connection pool dans l'API est mal configuré (pool trop petit) ou épuisé par des connexions qui ne sont pas releasées correctement. Configuration pool dans `apps/api/src/infrastructure/database.py`. Par défaut SQLAlchemy: `pool_size=5, max_overflow=10` = max 15 connections.

**How to Verify**:
```bash
# 1. Vérifier config pool actuelle dans logs API au démarrage
docker-compose logs api | grep -i "pool_size\|max_overflow" | tail -5

# 2. Compter connexions actives vs max_connections PostgreSQL
docker-compose exec postgres psql -U lia -c "
SELECT
  (SELECT count(*) FROM pg_stat_activity WHERE datname='lia') as active,
  (SELECT setting::int FROM pg_settings WHERE name='max_connections') as max_connections,
  round(100.0 * (SELECT count(*) FROM pg_stat_activity WHERE datname='lia') /
        (SELECT setting::int FROM pg_settings WHERE name='max_connections'), 2) as pct_used;
"

# 3. Vérifier état connexions (idle vs active)
docker-compose exec postgres psql -U lia -c "
SELECT state, count(*)
FROM pg_stat_activity
WHERE datname='lia'
GROUP BY state
ORDER BY count(*) DESC;
"
```

**Expected Output if This is the Cause**:
```
 active | max_connections | pct_used
--------+-----------------+----------
     85 |             100 |    85.00
(1 row)

   state    | count
------------+-------
 idle       |    60
 active     |    20
 idle in transaction | 5    ← PROBLÈME: connexions bloquées
(3 rows)
```

**Interpretation**:
- `pct_used` >85%: Alert firing
- Beaucoup de connexions `idle in transaction`: Transactions non-committées qui bloquent connexions
- Pool saturation si `active` connections ≈ pool_size configuré dans API

---

### 2. Connection Leaks (Code Bugs)

**Likelihood**: **High**

**Description**:
Code ne ferme pas correctement les connexions après usage. Souvent causé par:
- Exceptions non-catchées qui skip `finally` blocks
- Context managers (`with session:`) mal utilisés
- Queries dans loops sans proper cleanup
- LangGraph checkpoints qui gardent sessions ouvertes

**How to Verify**:
```bash
# 1. Identifier queries/processus qui gardent connexions longtemps
docker-compose exec postgres psql -U lia -c "
SELECT
  pid,
  usename,
  application_name,
  state,
  now() - state_change as duration,
  wait_event_type,
  query
FROM pg_stat_activity
WHERE datname='lia'
  AND state != 'idle'
ORDER BY state_change ASC
LIMIT 20;
"

# 2. Chercher pattern de connexions qui restent "idle in transaction" longtemps
docker-compose exec postgres psql -U lia -c "
SELECT
  pid,
  now() - state_change as idle_duration,
  state,
  query
FROM pg_stat_activity
WHERE datname='lia'
  AND state = 'idle in transaction'
  AND now() - state_change > interval '5 minutes'
ORDER BY state_change ASC;
"

# 3. Vérifier logs API pour exceptions non-gérées
docker-compose logs api --since=30m | grep -B 5 "Exception\|Error" | grep -A 3 "session\|connection"
```

**Expected Output if This is the Cause**:
```
# Connexions idle in transaction depuis 10+ minutes
 pid  | idle_duration | state              | query
------+---------------+--------------------+------------------
 1234 | 00:15:32      | idle in transaction| SELECT * FROM...
 5678 | 00:12:18      | idle in transaction| UPDATE...

# Pattern dans logs API
ERROR: Exception in checkpoint save
  File "state.py", line 123
  # session non-fermée si exception ici
```

---

### 3. Slow Queries Blocking Connections

**Likelihood**: **Medium-High**

**Description**:
Queries lentes (missing indexes, full table scans, N+1 queries) gardent connexions occupées longtemps. Pendant ce temps, pool se vide et nouvelles requêtes timeout.

**How to Verify**:
```bash
# 1. Identifier top 10 queries les plus lentes actuellement actives
docker-compose exec postgres psql -U lia -c "
SELECT
  pid,
  now() - query_start as duration,
  state,
  substring(query, 1, 100) as query_preview
FROM pg_stat_activity
WHERE datname='lia'
  AND state = 'active'
  AND query NOT LIKE '%pg_stat_activity%'
ORDER BY query_start ASC
LIMIT 10;
"

# 2. Vérifier si locks/waits bloquent queries
docker-compose exec postgres psql -U lia -c "
SELECT
  blocked_locks.pid AS blocked_pid,
  blocked_activity.usename AS blocked_user,
  blocking_locks.pid AS blocking_pid,
  blocking_activity.usename AS blocking_user,
  blocked_activity.query AS blocked_statement
FROM pg_catalog.pg_locks blocked_locks
JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid
JOIN pg_catalog.pg_locks blocking_locks ON blocking_locks.locktype = blocked_locks.locktype
  AND blocking_locks.database IS NOT DISTINCT FROM blocked_locks.database
  AND blocking_locks.relation IS NOT DISTINCT FROM blocked_locks.relation
  AND blocking_locks.page IS NOT DISTINCT FROM blocked_locks.page
  AND blocking_locks.tuple IS NOT DISTINCT FROM blocked_locks.tuple
  AND blocking_locks.virtualxid IS NOT DISTINCT FROM blocked_locks.virtualxid
  AND blocking_locks.transactionid IS NOT DISTINCT FROM blocked_locks.transactionid
  AND blocking_locks.classid IS NOT DISTINCT FROM blocked_locks.classid
  AND blocking_locks.objid IS NOT DISTINCT FROM blocked_locks.objid
  AND blocking_locks.objsubid IS NOT DISTINCT FROM blocked_locks.objsubid
  AND blocking_locks.pid != blocked_locks.pid
JOIN pg_catalog.pg_stat_activity blocking_activity ON blocking_activity.pid = blocking_locks.pid
WHERE NOT blocked_locks.granted;
"

# 3. Vérifier pg_stat_statements pour queries fréquentes et lentes
docker-compose exec postgres psql -U lia -c "
SELECT
  calls,
  mean_exec_time,
  max_exec_time,
  substring(query, 1, 100) as query_preview
FROM pg_stat_statements
WHERE dbid = (SELECT oid FROM pg_database WHERE datname='lia')
ORDER BY mean_exec_time DESC
LIMIT 10;
"
```

**Expected Output if This is the Cause**:
```
# Query bloquée depuis 5+ minutes
 pid  | duration  | state  | query_preview
------+-----------+--------+------------------------------------------
 9876 | 00:05:32  | active | SELECT * FROM conversations WHERE user_id IN (SELECT...)

# Locks bloquants
 blocked_pid | blocked_user | blocking_pid | blocking_user
-------------+--------------+--------------+--------------
        1234 | lia   |         5678 | lia
```

---

### 4. Traffic Spike / DDoS Attack

**Likelihood**: **Medium**

**Description**:
Spike soudain de trafic légitime (marketing campaign, viral post) ou attaque DDoS épuise rapidement le pool de connexions. Chaque requête API = 1+ connexions DB.

**How to Verify**:
```bash
# 1. Vérifier request rate API sur dernière heure
curl -s "http://localhost:9090/api/v1/query?query=rate(http_requests_total[5m])*60" | jq '.data.result[0].value[1]'

# 2. Comparer avec baseline normal
curl -s "http://localhost:9090/api/v1/query?query=avg_over_time(rate(http_requests_total[5m])[1h:5m])*60" | jq '.data.result[0].value[1]'

# 3. Vérifier nombre de users actifs concurrents
curl -s "http://localhost:9090/api/v1/query?query=conversation_active_users_total" | jq '.data.result[0].value[1]'

# 4. Analyser logs Nginx/API pour top IPs
docker-compose logs api --since=15m | grep -oP '"client_ip":"[^"]*"' | sort | uniq -c | sort -rn | head -20
```

**Expected Output if This is the Cause**:
```
# Request rate actuel: 150 req/min
"150.5"

# Baseline normal: 40 req/min
"42.3"

# Spike de 3.5x le trafic normal

# Top IP fait 40% des requêtes (potentiel DDoS)
    120 "client_ip":"203.0.113.45"
     30 "client_ip":"198.51.100.23"
```

---

### 5. PostgreSQL max_connections Configuration Too Low

**Likelihood**: **Low-Medium**

**Description**:
Configuration `max_connections` PostgreSQL trop basse pour la charge réelle. Par défaut PostgreSQL = 100 connections. Avec multi-replicas API (3 instances × pool 15) = besoin 45+ connections minimum.

**How to Verify**:
```bash
# 1. Vérifier max_connections actuel
docker-compose exec postgres psql -U lia -c "SHOW max_connections;"

# 2. Vérifier nombre d'instances API actives
docker-compose ps api | grep -c "Up"

# 3. Calculer besoin théorique
# Formula: (API instances × pool_size × max_overflow) + buffer
# Ex: (3 instances × 5 pool × 10 overflow) + 20 buffer = 170 connections needed

# 4. Vérifier shared_buffers (corrélé avec max_connections)
docker-compose exec postgres psql -U lia -c "SHOW shared_buffers;"
```

**Expected Output if This is the Cause**:
```
 max_connections
-----------------
             100
(1 row)

# 3 instances API running
# Need: 3 × 15 = 45 minimum
# Current: 100 (too low if other services connect too)
```

---

## 🔧 Diagnostic Steps

### Quick Health Check (< 2 minutes)

**Objectif**: Identifier rapidement la saturation et l'urgence.

```bash
# 1. Vérifier utilisation connexions actuelle
docker-compose exec postgres psql -U lia -c "SELECT count(*) as active, (SELECT setting::int FROM pg_settings WHERE name='max_connections') as max FROM pg_stat_activity WHERE datname='lia';"

# 2. Vérifier état connexions (combien idle vs active)
docker-compose exec postgres psql -U lia -c "SELECT state, count(*) FROM pg_stat_activity WHERE datname='lia' GROUP BY state;"

# 3. Vérifier logs API pour erreurs connexion
docker-compose logs api --tail=50 | grep -i "pool\|connection" | grep -i "error\|timeout"

# 4. Vérifier si HighErrorRate co-firing
curl -s http://localhost:9093/api/v2/alerts | jq '.[] | select(.labels.alertname=="HighErrorRate") | .status.state'

# 5. Quick check traffic spike
curl -s "http://localhost:9090/api/v1/query?query=rate(http_requests_total[5m])" | jq '.data.result[0].value[1]'
```

**Interprétation**:
- Si >90% utilisé: **CRITIQUE** - mitigation immédiate requise
- Si beaucoup `idle in transaction`: Connection leaks probable
- Si HighErrorRate firing aussi: Impact utilisateurs direct
- Si traffic spike 3x+ normal: DDoS ou campaign viral

---

### Deep Dive Investigation (5-10 minutes)

**Objectif**: Identifier cause racine exacte.

#### Step 1: Analyser Distribution des Connexions
```bash
# Connexions par application/user
docker-compose exec postgres psql -U lia -c "
SELECT
  application_name,
  usename,
  state,
  count(*) as conn_count
FROM pg_stat_activity
WHERE datname='lia'
GROUP BY application_name, usename, state
ORDER BY conn_count DESC;
"

# Identifier si une app/user monopolise connexions
```

---

#### Step 2: Identifier Long-Running Transactions
```bash
# Transactions actives depuis >5min
docker-compose exec postgres psql -U lia -c "
SELECT
  pid,
  usename,
  application_name,
  state,
  now() - xact_start as xact_duration,
  now() - query_start as query_duration,
  substring(query, 1, 200) as query
FROM pg_stat_activity
WHERE datname='lia'
  AND xact_start IS NOT NULL
  AND now() - xact_start > interval '5 minutes'
ORDER BY xact_start ASC;
"

# Ces transactions bloquent des connexions
```

---

#### Step 3: Vérifier Slow Queries Impact
```bash
# Top slow queries actuellement running
docker-compose exec postgres psql -U lia -c "
SELECT
  pid,
  now() - query_start as duration,
  state,
  wait_event_type,
  wait_event,
  substring(query, 1, 150) as query
FROM pg_stat_activity
WHERE datname='lia'
  AND state = 'active'
  AND query NOT LIKE '%pg_stat_activity%'
ORDER BY query_start ASC
LIMIT 15;
"
```

---

#### Step 4: Analyser Code Paths Récents
```bash
# Vérifier si déploiement récent
docker inspect lia_api | jq '.[0].State.StartedAt'

# Vérifier commits récents qui touchent DB queries
git log --since="4 hours ago" --oneline -- apps/api/src/domains apps/api/src/infrastructure/database.py

# Chercher pattern dans logs API
docker-compose logs api --since=1h | grep -i "sqlalchemy\|psycopg2" | grep -i "error" | tail -30
```

---

### Automated Diagnostic Script

```bash
infrastructure/observability/scripts/diagnose_db_connections.sh
```

Ce script exécute tous les checks ci-dessus et génère rapport.

---

## ✅ Resolution Steps

### Immediate Mitigation (Stop the Bleeding)

#### Option A: Kill Idle/Long-Running Connections (30 seconds)

**Use When**: Beaucoup de connexions `idle in transaction` ou long-running queries identifiées.

```bash
# 1. Identifier PIDs à killer (idle in transaction >5min)
docker-compose exec postgres psql -U lia -c "
SELECT pid, state, now() - state_change as duration
FROM pg_stat_activity
WHERE datname='lia'
  AND state = 'idle in transaction'
  AND now() - state_change > interval '5 minutes'
ORDER BY state_change ASC;
"

# 2. Kill ces connexions (remplacer PID1, PID2, etc.)
docker-compose exec postgres psql -U lia -c "
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname='lia'
  AND state = 'idle in transaction'
  AND now() - state_change > interval '5 minutes';
"

# 3. Vérifier utilisation diminue
docker-compose exec postgres psql -U lia -c "SELECT count(*) FROM pg_stat_activity WHERE datname='lia';"
```

**Pros**: Très rapide, libère immédiatement connexions bloquées
**Cons**: Peut causer rollback transactions en cours, erreurs temporaires pour users
**Duration**: 30 seconds
**Risk**: Low (transactions perdues sont probablement déjà timeout côté user)

---

#### Option B: Restart API Container (1 minute)

**Use When**: Option A insuffisante ou pool leak au niveau application.

```bash
# 1. Restart graceful (stop puis start)
docker-compose restart api

# 2. Monitorer logs démarrage
docker-compose logs -f api | grep -i "startup\|pool"

# 3. Vérifier connexions DB diminuent
watch -n 2 'docker-compose exec postgres psql -U lia -tc "SELECT count(*) FROM pg_stat_activity WHERE datname=\"lia\";"'

# 4. Attendre "Application startup complete" dans logs
```

**Pros**: Reset complet pool application, résout leaks temporaires
**Cons**: Downtime API ~20-30s, users voient erreurs temporaires
**Duration**: 1 minute total
**Risk**: Medium (service interruption brève)

---

#### Option C: Increase max_connections Temporarily (2 minutes)

**Use When**: Traffic spike légitime identifié, besoin de capacity immédiate.

```bash
# 1. Backup config actuelle
docker-compose exec postgres psql -U lia -c "SHOW max_connections;" > /tmp/max_conn_backup.txt

# 2. Increase max_connections (requires PostgreSQL restart)
# Éditer postgresql.conf
docker-compose exec postgres sh -c "echo 'max_connections = 200' >> /var/lib/postgresql/data/postgresql.conf"

# 3. Restart PostgreSQL (ATTENTION: downtime)
docker-compose restart postgres

# 4. Vérifier nouvelle config
docker-compose exec postgres psql -U lia -c "SHOW max_connections;"

# 5. Restart API pour reconnecter
docker-compose restart api
```

**Pros**: Augmente capacity immédiatement
**Cons**: Requires PostgreSQL restart (downtime ~1min), consomme plus RAM
**Duration**: 2-3 minutes
**Risk**: High (service interruption, impact mémoire)

**WARNING**: Valider que serveur a assez RAM avant d'augmenter max_connections.
Formula RAM: `max_connections × work_mem` doit rester < RAM disponible.

---

### Verification After Mitigation

```bash
# 1. Vérifier alert cleared (attendre 2min pour "for: 2m")
watch -n 10 'curl -s http://localhost:9093/api/v2/alerts | jq ".[] | select(.labels.alertname==\"CriticalDatabaseConnections\") | .status.state"'

# 2. Vérifier utilisation connexions normale
docker-compose exec postgres psql -U lia -c "
SELECT
  count(*) as active,
  (SELECT setting::int FROM pg_settings WHERE name='max_connections') as max,
  round(100.0 * count(*) / (SELECT setting::int FROM pg_settings WHERE name='max_connections'), 2) as pct
FROM pg_stat_activity
WHERE datname='lia';
"

# 3. Vérifier plus de "idle in transaction" longues
docker-compose exec postgres psql -U lia -c "SELECT count(*) FROM pg_stat_activity WHERE datname='lia' AND state='idle in transaction' AND now()-state_change > interval '1 minute';"

# 4. Vérifier HighErrorRate cleared aussi
curl -s "http://localhost:9090/api/v1/query?query=sum(rate(http_requests_total{status=~\"5..\"}[5m]))*100/sum(rate(http_requests_total[5m]))" | jq '.data.result[0].value[1]'

# 5. Test fonctionnel API
curl -i http://localhost:8000/api/health
```

**Expected After Success**:
- Connection usage < 70%
- Alert status: "inactive"
- Pas de connexions idle >1min
- Error rate < 1%
- Health check returns 200 OK

---

### Root Cause Fix (Permanent Solution)

#### If Cause = Pool Configuration Too Small

**Fix**: Augmenter pool size dans `apps/api/src/infrastructure/database.py`:

```python
# Avant
engine = create_async_engine(
    database_url,
    pool_size=5,           # Trop petit
    max_overflow=10,
    pool_timeout=30
)

# Après (basé sur charge réelle)
engine = create_async_engine(
    database_url,
    pool_size=20,          # 4x augmentation
    max_overflow=40,       # Permet bursts
    pool_timeout=30,
    pool_pre_ping=True,    # Vérifie connexions vivantes
    pool_recycle=3600      # Recycle après 1h
)
```

**Testing**:
```bash
# Rebuild et redeploy
docker-compose build api
docker-compose up -d api

# Load test pour valider
ab -n 1000 -c 50 http://localhost:8000/api/health

# Monitor connexions pendant load test
watch -n 1 'docker-compose exec postgres psql -U lia -tc "SELECT count(*) FROM pg_stat_activity WHERE datname=\"lia\";"'
```

---

#### If Cause = Connection Leaks

**Investigation**:
```bash
# Identifier fichiers suspects dans stack traces
docker-compose logs api --since=2h | awk '/Traceback/,/^[^ ]/' | grep "File " | sort | uniq -c | sort -rn | head -10
```

**Fix Example** (checkpoint save leak):
```python
# Avant (leak potentiel)
async def save_checkpoint(state):
    session = get_session()
    checkpoint = serialize(state)
    session.add(Checkpoint(data=checkpoint))
    session.commit()
    # session jamais fermée si exception!

# Après (proper cleanup)
async def save_checkpoint(state):
    async with get_session() as session:  # Auto-close
        checkpoint = serialize(state)
        session.add(Checkpoint(data=checkpoint))
        await session.commit()
    # session toujours fermée, même si exception
```

**Testing**:
```bash
# Tests unitaires avec connection counting
pytest tests/unit/infrastructure/test_database.py -v --count-connections

# Integration test sous charge
pytest tests/integration/test_checkpoint_save.py -v --repeat=100
```

---

#### If Cause = Slow Queries

**Fix**: Ajouter indexes manquants.

**Identify Missing Indexes**:
```bash
docker-compose exec postgres psql -U lia -c "
SELECT schemaname, tablename, attname, n_distinct, correlation
FROM pg_stats
WHERE schemaname = 'public'
  AND n_distinct > 100
  AND correlation < 0.1
ORDER BY n_distinct DESC;
"
```

**Add Indexes**:
```sql
-- Migration file: add_indexes_connections_optimization.sql
CREATE INDEX CONCURRENTLY idx_conversations_user_id ON conversations(user_id);
CREATE INDEX CONCURRENTLY idx_checkpoints_conversation_id ON checkpoints(conversation_id);
CREATE INDEX CONCURRENTLY idx_messages_created_at ON messages(created_at DESC);

-- CONCURRENTLY = no table lock, production safe
```

**Deploy**:
```bash
# Apply migration
docker-compose exec postgres psql -U lia -f /path/to/migration.sql

# Verify indexes created
docker-compose exec postgres psql -U lia -c "\d+ conversations"
```

---

#### If Cause = max_connections Too Low

**Permanent Fix**: Update postgresql.conf dans docker-compose.

**docker-compose.yml**:
```yaml
postgres:
  image: postgres:15
  command:
    - "postgres"
    - "-c"
    - "max_connections=200"        # Augmenté de 100
    - "-c"
    - "shared_buffers=512MB"       # Augmenté proportionnellement
  environment:
    POSTGRES_USER: lia
    POSTGRES_PASSWORD: ${DB_PASSWORD}
  volumes:
    - postgres_data:/var/lib/postgresql/data
```

**Deploy**:
```bash
docker-compose down postgres
docker-compose up -d postgres

# Verify
docker-compose exec postgres psql -U lia -c "SHOW max_connections; SHOW shared_buffers;"
```

---

#### Monitoring Post-Fix

**Surveiller 48-72h**:
```bash
# Dashboard Grafana: Database Connections panel
# Vérifier:
# - Utilization reste <70% en normal, <85% en peak
# - Pas de spike soudains
# - Ratio idle/active stable
# - Pas de "idle in transaction" >1min

# Query Prometheus pour alerting
curl -s "http://localhost:9090/api/v1/query?query=(pg_stat_database_numbackends{datname=\"lia\"}/pg_settings_max_connections)*100" | jq '.data.result[0].value[1]'
```

---

## 📈 Related Dashboards & Queries

### Grafana Dashboards
- **PostgreSQL Monitoring**: `http://localhost:3000/d/postgresql`
  - Panel: "Active Connections by State"
  - Panel: "Connection Pool Utilization %"
  - Panel: "Long-Running Queries"
- **API Overview**: `http://localhost:3000/d/api-overview`
  - Panel: "Database Errors"

### Prometheus Queries
```promql
# Connection utilization percentage
(pg_stat_database_numbackends{datname="lia"} / pg_settings_max_connections) * 100

# Connection growth rate
rate(pg_stat_database_numbackends{datname="lia"}[5m])

# Connections by state
pg_stat_activity_count{datname="lia", state="active"}
pg_stat_activity_count{datname="lia", state="idle"}
pg_stat_activity_count{datname="lia", state="idle in transaction"}
```

### PostgreSQL Diagnostic Queries
```sql
-- Full connection analysis
SELECT
  datname,
  usename,
  application_name,
  client_addr,
  state,
  count(*) as connections,
  max(now() - state_change) as max_idle_time
FROM pg_stat_activity
WHERE datname = 'lia'
GROUP BY datname, usename, application_name, client_addr, state
ORDER BY connections DESC;

-- Transaction age distribution
SELECT
  CASE
    WHEN now() - xact_start < interval '1 minute' THEN '< 1min'
    WHEN now() - xact_start < interval '5 minutes' THEN '1-5min'
    WHEN now() - xact_start < interval '15 minutes' THEN '5-15min'
    ELSE '> 15min'
  END as age_bucket,
  count(*) as transactions
FROM pg_stat_activity
WHERE datname = 'lia' AND xact_start IS NOT NULL
GROUP BY age_bucket
ORDER BY age_bucket;
```

---

## 📚 Related Runbooks

- **[HighErrorRate](./HighErrorRate.md)** - Souvent co-fire (DB errors → API errors)
- **[HighDatabaseConnections](./HighDatabaseConnections.md)** - Warning précurseur (70% threshold)
- **[DatabaseDown](./DatabaseDown.md)** - Escalation si mitigation échoue
- **[SlowQueries](./SlowQueries.md)** - Cause fréquente de connection saturation

---

## 🔄 Common Patterns & Known Issues

### Pattern 1: Post-Deployment Connection Spike
**Description**: Déploiement nouveau code → toutes instances API reconnectent simultanément
**Resolution**: Stagger restarts (restart instances une par une)
**Prevention**: Rolling deployment strategy, connection pool pre-warming

### Pattern 2: Checkpoint Save Storms
**Description**: Batch de checkpoints LangGraph sauvés simultanément → spike connexions
**Resolution**: Implement checkpoint save queue avec rate limiting
**Prevention**: Spread checkpoint saves over time, async background workers

### Pattern 3: Marketing Campaign Traffic Spikes
**Description**: Email campaign → 10x users simultanés → connection exhaustion
**Resolution**: Pre-scale pool before campaign, use connection pooler (PgBouncer)
**Prevention**: Coordinate avec marketing, scheduled scaling, PgBouncer entre API et PostgreSQL

### Known Issue 1: SQLAlchemy Pool Timeout Cascade
**Symptom**: Une query timeout → pool wait timeout → cascade failures
**Workaround**: Augmenter `pool_timeout` à 60s, add circuit breaker
**Tracking**: GitHub issue #[TODO]

### Known Issue 2: Idle in Transaction from LangGraph
**Symptom**: LangGraph interrupt humain → transaction reste ouverte des heures
**Workaround**: Periodic cleanup job kill idle transactions >30min
**Tracking**: GitHub issue #[TODO]

---

## 🆘 Escalation

### When to Escalate

Escalader immédiatement si:
- [ ] Utilization >95% pendant 5+ minutes
- [ ] Mitigation (kill connections, restart) n'a pas fonctionné
- [ ] PostgreSQL lui-même devient unresponsive
- [ ] Data corruption suspectée (rollbacks massifs)
- [ ] Impact >200 utilisateurs actifs
- [ ] Root cause inconnue après 20min investigation

### Escalation Path

**Level 1 - Senior Backend Engineer** (0-15min):
- **Contact**: Backend Lead
- **Slack**: #backend-critical
- **Escalate if**: Cannot identify cause in 15min

**Level 2 - Database Administrator / SRE** (15-30min):
- **Contact**: DBA On-call
- **Slack**: #infrastructure-critical
- **Phone**: [DBA on-call number]
- **Escalate if**: Need PostgreSQL-level intervention (config changes, replication issues)

**Level 3 - CTO** (30min+):
- **Contact**: CTO
- **Email**: cto@lia.com
- **Phone**: [Emergency]
- **Escalate if**: Need business decision (scale infrastructure, budget approval for bigger DB instance)

### Escalation Template

```
🚨 ESCALATION - CriticalDatabaseConnections 🚨

Alert: CriticalDatabaseConnections
Severity: CRITICAL
Duration: [X] minutes
Current Utilization: [Y]% ([Z] connections / [MAX] max)

Impact:
- [X] active users affected
- API error rate: [Y]%
- Features down: [list]

Actions Taken:
- [Time] Killed idle in transaction connections - utilization dropped to [X]%
- [Time] Restarted API container - no significant improvement
- [Time] Identified [X] slow queries running 10+ minutes

Current Status: Utilization [X]%, trending [up/down/stable]

Root Cause: [Suspected or "Unknown - investigating"]

Need: [DBA expertise / Infrastructure scaling / Business approval]

Dashboards:
- PostgreSQL: http://localhost:3000/d/postgresql
- Prometheus: http://localhost:9090/graph?g0.expr=(pg_stat_database_numbackends%7Bdatname%3D%22lia%22%7D%2Fpg_settings_max_connections)*100

Next Steps: [What you plan to do]
```

---

## 📝 Post-Incident Actions

### Immediate (< 1h)
- [ ] Create incident report GitHub issue
- [ ] Notify stakeholders résolution
- [ ] Document exact timeline
- [ ] Capture query logs période incident
  ```bash
  docker-compose exec postgres psql -U lia -c "\copy (SELECT * FROM pg_stat_activity_history WHERE time >= '[incident_start]' AND time <= '[incident_end]') TO '/tmp/incident_queries.csv' CSV HEADER;"
  ```

### Short-Term (< 24h)
- [ ] Update runbook avec learnings
- [ ] Create issues pour permanent fixes
- [ ] Review pool configuration across all environments
- [ ] Add monitoring pour early warning (connection growth rate)
- [ ] Share post-mortem draft avec équipe

### Long-Term (< 1 week)
- [ ] Post-mortem meeting blameless
- [ ] Implement tous les action items
- [ ] Consider PgBouncer deployment (connection pooler externe)
- [ ] Load testing pour valider capacity
- [ ] Update capacity planning docs

---

## 🔗 Additional Resources

### Documentation
- [PostgreSQL Connection Pooling](https://www.postgresql.org/docs/current/runtime-config-connection.html)
- [SQLAlchemy Engine Configuration](https://docs.sqlalchemy.org/en/20/core/engines.html)
- [PgBouncer - Lightweight Connection Pooler](https://www.pgbouncer.org/)

### Code References
- Database Config: `apps/api/src/infrastructure/database.py`
- Connection Pool Settings: Search `create_engine` ou `create_async_engine`
- Checkpoint Save: `apps/api/src/domains/agents/graph.py`

### External Resources
- [Postgres Performance Tuning](https://wiki.postgresql.org/wiki/Performance_Optimization)
- [SQLAlchemy Best Practices](https://docs.sqlalchemy.org/en/20/core/pooling.html#dealing-with-disconnects)

---

## 📅 Runbook Metadata

**Created**: 2025-11-22
**Last Updated**: 2025-11-22
**Maintainer**: Backend Team + DBA
**Version**: 1.0
**Related GitHub Issues**: #31 (Phase 1.3 - Runbooks)

**Changelog**:
- **2025-11-22**: Initial creation

---

## ✅ Runbook Validation Checklist

- [x] Alert definition verified
- [ ] SQL queries tested (**TODO**: Test in staging)
- [ ] Mitigation steps validated (**TODO**: Dry-run in staging)
- [ ] Escalation path confirmed (**TODO**: Get real DBA contacts)
- [ ] Dashboard links functional (**TODO**: Create dashboards)
- [ ] Peer reviewed (**TODO**: Review by DBA team)
- [ ] Incident simulation performed (**TODO**: Schedule chaos engineering test)

---

**Note**: Ce runbook doit être testé en staging avec simulation de connection saturation avant usage production.
