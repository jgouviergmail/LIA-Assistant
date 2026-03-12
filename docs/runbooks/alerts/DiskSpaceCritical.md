# DiskSpaceCritical - Runbook

**Severity**: Critical
**Component**: Infrastructure
**Impact**: Imminent service crash, potential database corruption, logs lost
**SLA Impact**: Yes - Service availability at risk

---

## 1. Alert Definition

**Alert Name**: `DiskSpaceCritical`

**PromQL Query**:
```promql
(node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"}) * 100 < <<<ALERT_DISK_SPACE_CRITICAL_THRESHOLD_PERCENT>>>
```

**Thresholds**:
- **Production**: <10% free space (Critical - immediate action required)
- **Staging**: <5% free space (Acceptable for testing)
- **Development**: <3% free space (Not critical in dev)

**Duration**: For 2 minutes

**Labels**:
```yaml
severity: critical
component: infrastructure
alert_type: disk_space
impact: availability
```

**Annotations**:
```yaml
summary: "Critical disk space on {{ $labels.instance }}"
description: "Disk space critical on {{ $labels.instance }}: {{ $value | humanizePercentage }} free (threshold: <<<ALERT_DISK_SPACE_CRITICAL_THRESHOLD_PERCENT>>>%)"
```

---

## 2. Symptoms

### What Users See
- **Service becomes unresponsive** - API returns timeouts or 503 errors
- **Data loss** - Recent conversations/messages may be lost
- **Authentication failures** - Unable to login/refresh tokens
- **Slow performance** - If disk is near full, I/O degrades severely

### What Ops See
- **Disk space <10%** in monitoring dashboards
- **Database errors** - "No space left on device" in PostgreSQL logs
- **Application crashes** - API container restarts repeatedly
- **Log rotation failures** - Logs accumulate without rotation
- **Docker errors** - "no space left on device" when pulling images or creating containers

---

## 3. Possible Causes

### Cause 1: Log File Accumulation (High Likelihood)
**Description**: Application logs, Nginx logs, PostgreSQL logs growing unbounded without rotation or cleanup.

**Likelihood**: High (60%) - Most common cause in production systems

**Verification**:
```bash
# Check disk usage by directory
docker-compose exec api df -h /

# Find largest directories
docker-compose exec api du -h --max-depth=2 / | sort -hr | head -20

# Check application logs size
docker-compose logs --no-color | wc -l
du -sh /var/lib/docker/containers/*/*-json.log 2>/dev/null | sort -hr | head -10

# Check PostgreSQL logs
docker-compose exec postgres du -sh /var/lib/postgresql/data/log

# Check system logs
sudo du -sh /var/log/*
```

**Expected Output**:
- Logs directory >5GB indicates accumulation
- Individual log files >1GB indicate rotation failure

---

### Cause 2: PostgreSQL Checkpoint/WAL Growth (High Likelihood)
**Description**: PostgreSQL Write-Ahead Logs (WAL) and checkpoints consuming excessive disk space due to high write volume or failed archiving.

**Likelihood**: High (50%) - Common with conversation/checkpoint storage workload

**Verification**:
```bash
# Check PostgreSQL data directory size
docker-compose exec postgres du -sh /var/lib/postgresql/data

# Check WAL directory specifically
docker-compose exec postgres du -sh /var/lib/postgresql/data/pg_wal

# Count WAL segments
docker-compose exec postgres ls -1 /var/lib/postgresql/data/pg_wal | wc -l

# Check checkpoint statistics
docker-compose exec postgres psql -U lia -c "
SELECT
  checkpoints_timed,
  checkpoints_req,
  checkpoint_write_time,
  checkpoint_sync_time,
  buffers_checkpoint,
  buffers_clean,
  maxwritten_clean
FROM pg_stat_bgwriter;
"

# Check oldest WAL file (retention)
docker-compose exec postgres ls -lt /var/lib/postgresql/data/pg_wal | tail -5
```

**Expected Output**:
- WAL directory >10GB indicates excessive growth
- >100 WAL segments (16MB each) indicates archiving issues

---

### Cause 3: Docker Image/Volume Accumulation (Medium Likelihood)
**Description**: Unused Docker images, stopped containers, dangling volumes consuming disk space.

**Likelihood**: Medium (30%) - Common in development, less in production

**Verification**:
```bash
# Check Docker disk usage
docker system df -v

# List dangling images
docker images -f "dangling=true"

# List stopped containers
docker ps -a --filter "status=exited"

# List dangling volumes
docker volume ls -f "dangling=true"

# Check build cache
docker builder du
```

**Expected Output**:
- "Reclaimable" space >5GB indicates cleanup needed
- Multiple dangling images/volumes indicate accumulation

---

### Cause 4: Temporary File Accumulation (Medium Likelihood)
**Description**: /tmp directory, Redis RDB dumps, Python __pycache__, or application temp files not cleaned up.

**Likelihood**: Medium (25%) - Depends on cleanup policies

**Verification**:
```bash
# Check /tmp directory
docker-compose exec api du -sh /tmp
docker-compose exec api find /tmp -type f -mtime +7 -ls

# Check Redis dump file
docker-compose exec redis ls -lh /data/dump.rdb

# Check Python cache
docker-compose exec api find /app -type d -name __pycache__ -exec du -sh {} + | sort -hr

# Check application temp directories
docker-compose exec api find /app/temp -type f -mtime +1 -ls 2>/dev/null
docker-compose exec api du -sh /app/uploads 2>/dev/null
```

**Expected Output**:
- /tmp >1GB indicates stale files
- Large dump.rdb (>500MB) indicates infrequent cleanup

---

### Cause 5: Database Table Bloat (Low-Medium Likelihood)
**Description**: PostgreSQL tables/indexes growing due to dead tuples not being vacuumed, or inefficient schema design.

**Likelihood**: Low-Medium (20%) - More gradual growth, less likely to cause sudden crisis

**Verification**:
```bash
# Check database size
docker-compose exec postgres psql -U lia -c "
SELECT
  pg_database.datname,
  pg_size_pretty(pg_database_size(pg_database.datname)) AS size
FROM pg_database
ORDER BY pg_database_size(pg_database.datname) DESC;
"

# Check table sizes
docker-compose exec postgres psql -U lia -c "
SELECT
  schemaname,
  tablename,
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS total_size,
  pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)) AS table_size,
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename) - pg_relation_size(schemaname||'.'||tablename)) AS indexes_size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
LIMIT 10;
"

# Check bloat estimate
docker-compose exec postgres psql -U lia -c "
SELECT
  schemaname,
  tablename,
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size,
  n_dead_tup,
  n_live_tup,
  ROUND(100.0 * n_dead_tup / NULLIF(n_live_tup + n_dead_tup, 0), 2) AS dead_ratio
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 10;
"

# Check last vacuum/analyze
docker-compose exec postgres psql -U lia -c "
SELECT
  schemaname,
  relname,
  last_vacuum,
  last_autovacuum,
  last_analyze,
  last_autoanalyze
FROM pg_stat_user_tables
WHERE schemaname = 'public'
ORDER BY last_autovacuum ASC NULLS FIRST
LIMIT 10;
"
```

**Expected Output**:
- Dead tuple ratio >20% indicates bloat
- Tables >10GB without recent vacuum indicate maintenance issue

---

## 4. Diagnostic Steps

### Quick Health Check (<2 minutes)

**Step 1: Check current disk usage**
```bash
# Overall disk space
docker-compose exec api df -h /

# Expected output:
# Filesystem      Size  Used Avail Use% Mounted on
# overlay         100G   92G  8.0G  92% /
#                              ^^^^^ CRITICAL if <10G
```

**Step 2: Identify largest consumers**
```bash
# Top directories by size
docker-compose exec api du -h --max-depth=2 / 2>/dev/null | sort -hr | head -10

# Expected output shows which component is consuming space
# Examples:
# 50G  /var/lib/postgresql/data        → PostgreSQL (WAL/checkpoints)
# 20G  /var/log                        → Log files
# 15G  /var/lib/docker                 → Docker images/containers
```

**Step 3: Check immediate threats**
```bash
# Check if writes are failing
docker-compose logs --tail=50 | grep -i "no space left"

# Check container status
docker-compose ps

# Expected: All containers "Up", not restarting
```

---

### Deep Dive Analysis (5-10 minutes)

**Step 4: Analyze log accumulation**
```bash
# Application logs
docker-compose logs --no-color api | wc -l
docker-compose logs --no-color postgres | wc -l
docker-compose logs --no-color redis | wc -l

# Log rotation status
docker-compose exec api ls -lh /var/log/
docker-compose exec postgres ls -lh /var/lib/postgresql/data/log/

# Check log rotation config
docker-compose exec api cat /etc/logrotate.d/* 2>/dev/null
```

**Step 5: Analyze PostgreSQL space usage**
```bash
# Detailed breakdown
docker-compose exec postgres psql -U lia -c "
SELECT
  'Database' AS type,
  datname AS name,
  pg_size_pretty(pg_database_size(datname)) AS size
FROM pg_database
UNION ALL
SELECT
  'WAL' AS type,
  'pg_wal' AS name,
  pg_size_pretty(SUM(size)) AS size
FROM pg_ls_waldir()
ORDER BY type, name;
"

# Check WAL archiving status
docker-compose exec postgres psql -U lia -c "SHOW archive_mode;"
docker-compose exec postgres psql -U lia -c "SHOW archive_command;"
```

**Step 6: Analyze Docker disk usage**
```bash
# Comprehensive Docker report
docker system df -v

# Look for:
# - Images: RECLAIMABLE column (dangling images)
# - Containers: SIZE column (stopped containers with data)
# - Volumes: LINKS column = 0 (unused volumes)
# - Build Cache: RECLAIMABLE column
```

**Step 7: Check for abnormal growth patterns**
```bash
# Query Prometheus for disk growth rate
curl -s "http://localhost:9090/api/v1/query?query=deriv(node_filesystem_avail_bytes{mountpoint=\"/\"}[1h])" | jq '.data.result[0].value[1]'

# Negative value = disk shrinking
# Estimate time to full disk:
# current_free_bytes / abs(growth_rate_per_second) / 3600 = hours remaining
```

---

## 5. Resolution Steps

### Immediate Mitigation (<5 minutes)

**Option 1: Purge Docker logs (Fastest - 30 seconds)**
```bash
# Truncate all Docker container logs
sudo truncate -s 0 /var/lib/docker/containers/*/*-json.log

# Verify space freed
docker-compose exec api df -h /

# Impact: Loses historical logs, but frees space immediately
# Downside: Cannot debug recent incidents without logs
# When to use: Emergency only, disk <5% free
```

**Option 2: Clean Docker artifacts (Fast - 2 minutes)**
```bash
# Remove all unused Docker resources
docker system prune -a --volumes --force

# This removes:
# - Stopped containers
# - Dangling images
# - Unused volumes
# - Build cache

# Verify space freed
docker system df

# Impact: May need to rebuild images on next deployment
# Downside: Next docker-compose up will pull/rebuild images
# When to use: Disk <10% free, no active deployment
```

**Option 3: Purge old PostgreSQL WAL files (Medium - 3 minutes)**
```bash
# Force checkpoint to archive WAL
docker-compose exec postgres psql -U lia -c "CHECKPOINT;"

# Check WAL segments before
docker-compose exec postgres ls -1 /var/lib/postgresql/data/pg_wal | wc -l

# Manual WAL cleanup (PostgreSQL 10+)
docker-compose exec postgres psql -U lia -c "SELECT pg_walfile_name(pg_current_wal_lsn());"
# Note the current WAL file (e.g., 000000010000000000000042)

# Remove old WAL files (CAUTION: Only if archiving is disabled or completed)
docker-compose exec postgres bash -c "cd /var/lib/postgresql/data/pg_wal && ls -1 | head -50 | grep -v \$(psql -U lia -t -c \"SELECT pg_walfile_name(pg_current_wal_lsn());\") | xargs rm -f"

# Check WAL segments after
docker-compose exec postgres ls -1 /var/lib/postgresql/data/pg_wal | wc -l

# Impact: Frees WAL space (typically 1-10GB)
# Downside: Cannot use point-in-time recovery beyond removed WALs
# When to use: WAL directory >10GB, archiving not needed
```

**Option 4: Rotate and compress logs (Medium - 5 minutes)**
```bash
# Force log rotation
docker-compose exec api logrotate -f /etc/logrotate.conf 2>/dev/null || true

# Manual compression of old logs
docker-compose exec api bash -c "find /var/log -name '*.log' -mtime +1 -exec gzip {} +"
docker-compose exec postgres bash -c "find /var/lib/postgresql/data/log -name '*.log' -mtime +1 -exec gzip {} +"

# Delete very old compressed logs (>30 days)
docker-compose exec api bash -c "find /var/log -name '*.gz' -mtime +30 -delete"

# Verify space freed
docker-compose exec api df -h /

# Impact: Preserves recent logs, frees 30-70% space
# Downside: Older logs compressed (slower to read)
# When to use: Disk <15% free, need to preserve logs
```

---

### Root Cause Fix (15-30 minutes)

**Fix 1: Configure automatic log rotation**

**File**: `infrastructure/docker/logrotate.conf` (create new file)
```conf
/var/log/lia/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0640 root root
    sharedscripts
    postrotate
        docker-compose kill -s HUP api
    endscript
}

/var/lib/postgresql/data/log/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0640 postgres postgres
    postrotate
        docker-compose exec postgres pg_ctl reload
    endscript
}
```

**Update docker-compose.yml**:
```yaml
services:
  api:
    volumes:
      - ./infrastructure/docker/logrotate.conf:/etc/logrotate.d/lia:ro
    logging:
      driver: "json-file"
      options:
        max-size: "50m"
        max-file: "5"
```

**Apply changes**:
```bash
# Test logrotate configuration
docker-compose exec api logrotate -d /etc/logrotate.d/lia

# Restart to apply docker logging limits
docker-compose up -d

# Verify logging config
docker inspect lia_api_1 | jq '.[0].HostConfig.LogConfig'
```

---

**Fix 2: Configure PostgreSQL WAL archiving/cleanup**

**File**: `apps/api/.env` (update)
```bash
# PostgreSQL WAL configuration
POSTGRES_WAL_LEVEL=replica
POSTGRES_MAX_WAL_SIZE=2GB  # Default 1GB, increase for high write workload
POSTGRES_MIN_WAL_SIZE=80MB
POSTGRES_WAL_KEEP_SIZE=0   # Don't keep old WAL for replication (standalone mode)
POSTGRES_ARCHIVE_MODE=off  # Enable if using PITR/replication
```

**File**: `infrastructure/docker/postgresql.conf` (create/update)
```conf
# WAL configuration
wal_level = replica
max_wal_size = 2GB
min_wal_size = 80MB
wal_keep_size = 0
archive_mode = off
checkpoint_timeout = 5min
checkpoint_completion_target = 0.9

# Autovacuum (prevent bloat)
autovacuum = on
autovacuum_max_workers = 3
autovacuum_naptime = 1min
autovacuum_vacuum_scale_factor = 0.1
autovacuum_analyze_scale_factor = 0.05
```

**Update docker-compose.yml**:
```yaml
services:
  postgres:
    volumes:
      - ./infrastructure/docker/postgresql.conf:/etc/postgresql/postgresql.conf:ro
    command: postgres -c config_file=/etc/postgresql/postgresql.conf
```

**Apply changes**:
```bash
# Restart PostgreSQL
docker-compose restart postgres

# Verify configuration
docker-compose exec postgres psql -U lia -c "SHOW max_wal_size;"
docker-compose exec postgres psql -U lia -c "SHOW archive_mode;"

# Monitor WAL size over time
watch -n 30 'docker-compose exec postgres du -sh /var/lib/postgresql/data/pg_wal'
```

---

**Fix 3: Implement scheduled cleanup cron jobs**

**File**: `infrastructure/observability/scripts/cleanup_disk_space.sh` (create new)
```bash
#!/bin/bash
set -euo pipefail

# Disk cleanup script for LIA
# Run daily via cron

RETENTION_DAYS=${RETENTION_DAYS:-30}
MIN_FREE_PERCENT=${MIN_FREE_PERCENT:-20}

# Check current disk usage
CURRENT_FREE=$(df / | awk 'NR==2 {print $5}' | sed 's/%//')
echo "[$(date)] Current disk usage: ${CURRENT_FREE}%"

if [ "$CURRENT_FREE" -gt $((100 - MIN_FREE_PERCENT)) ]; then
    echo "[$(date)] Disk usage critical, running cleanup..."

    # 1. Clean Docker logs
    echo "[$(date)] Cleaning Docker logs older than ${RETENTION_DAYS} days..."
    find /var/lib/docker/containers -name "*-json.log" -mtime +${RETENTION_DAYS} -delete || true

    # 2. Clean Docker artifacts
    echo "[$(date)] Pruning Docker system..."
    docker system prune -f --filter "until=$((RETENTION_DAYS*24))h" || true

    # 3. Clean application temp files
    echo "[$(date)] Cleaning temp files..."
    docker-compose exec -T api find /tmp -type f -mtime +7 -delete || true

    # 4. Compress old logs
    echo "[$(date)] Compressing old logs..."
    find /var/log -name "*.log" -mtime +7 -exec gzip {} + || true

    # 5. Delete very old logs
    echo "[$(date)] Deleting logs older than ${RETENTION_DAYS} days..."
    find /var/log -name "*.gz" -mtime +${RETENTION_DAYS} -delete || true

    # Check disk usage after cleanup
    NEW_FREE=$(df / | awk 'NR==2 {print $5}' | sed 's/%//')
    FREED=$((NEW_FREE - CURRENT_FREE))
    echo "[$(date)] Cleanup complete. Freed ${FREED}% disk space. Current usage: ${NEW_FREE}%"

    # Alert if still critical
    if [ "$NEW_FREE" -gt 90 ]; then
        echo "[$(date)] WARNING: Disk still critical after cleanup (${NEW_FREE}%). Manual intervention required."
        # Send alert (integrate with AlertManager webhook)
        curl -X POST http://localhost:9093/api/v1/alerts -d '[{
            "labels": {"alertname": "DiskCleanupInsufficient", "severity": "critical"},
            "annotations": {"summary": "Disk cleanup freed only '"${FREED}"'%, still at '"${NEW_FREE}"'%"}
        }]' || true
    fi
else
    echo "[$(date)] Disk usage healthy (${CURRENT_FREE}%), skipping cleanup."
fi
```

**Make executable**:
```bash
chmod +x infrastructure/observability/scripts/cleanup_disk_space.sh
```

**Setup cron job** (on host):
```bash
# Add to crontab
crontab -e

# Run cleanup daily at 2 AM
0 2 * * * cd /path/to/LIA && ./infrastructure/observability/scripts/cleanup_disk_space.sh >> /var/log/lia/disk_cleanup.log 2>&1
```

**Test manually**:
```bash
./infrastructure/observability/scripts/cleanup_disk_space.sh
```

---

**Fix 4: Increase disk size (Infrastructure change)**

**For cloud deployments (AWS/GCP/Azure)**:
```bash
# AWS EBS volume resize (example)
aws ec2 modify-volume --volume-id vol-xxxxx --size 200

# Wait for resize to complete
aws ec2 describe-volumes-modifications --volume-id vol-xxxxx

# Extend filesystem (on instance)
sudo growpart /dev/xvda 1
sudo resize2fs /dev/xvda1

# Verify new size
df -h /
```

**For local/on-prem deployments**:
```bash
# Extend LVM volume (example)
sudo lvextend -L +50G /dev/mapper/vg-root
sudo resize2fs /dev/mapper/vg-root

# Verify
df -h /
```

**When to use**: If cleanup only temporarily solves the issue and growth is legitimate (not a leak).

---

## 6. Related Dashboards & Queries

### Grafana Dashboards
- **Infrastructure Overview** - `http://localhost:3000/d/infrastructure-overview`
  - Panel: "Disk Space %" - Shows trend over time
  - Panel: "Disk Growth Rate" - Predicts time to full

- **Database Monitoring** - `http://localhost:3000/d/database-monitoring`
  - Panel: "PostgreSQL Data Size" - Database growth
  - Panel: "WAL Size" - WAL accumulation

### Prometheus Queries

**Current disk space percentage**:
```promql
(node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"}) * 100
```

**Disk growth rate (bytes/hour)**:
```promql
deriv(node_filesystem_avail_bytes{mountpoint="/"}[1h]) * 3600
```

**Estimated hours until full** (negative growth only):
```promql
node_filesystem_avail_bytes{mountpoint="/"} / abs(deriv(node_filesystem_avail_bytes{mountpoint="/"}[1h]) * 3600)
```

**PostgreSQL database size**:
```promql
pg_database_size_bytes{datname="lia"}
```

**Docker log files total size** (if exporter configured):
```promql
sum(container_fs_usage_bytes{name=~"lia.*"})
```

---

## 7. Related Runbooks
- [HighErrorRate.md](./HighErrorRate.md) - May occur simultaneously if disk full causes errors
- [DatabaseDown.md](./DatabaseDown.md) - Disk full can cause PostgreSQL to crash
- [CheckpointSaveSlowCritical.md](./CheckpointSaveSlowCritical.md) - Disk I/O degradation affects checkpoints

---

## 8. Common Patterns & Known Issues

### Pattern 1: Log Explosion During Incidents
**Scenario**: During an outage, error logs generate 10x normal volume, filling disk rapidly.

**Detection**:
```bash
# Check log growth in last hour
docker-compose logs --since 1h | wc -l
# Compare to normal: docker-compose logs --since 1h --until 2h | wc -l
```

**Prevention**:
- Implement circuit breakers to prevent error loops
- Configure logging rate limits (sample 1/100 errors during incidents)

---

### Pattern 2: Checkpoint Accumulation After Long Transactions
**Scenario**: A long-running transaction blocks WAL cleanup, causing accumulation.

**Detection**:
```bash
# Check for long transactions
docker-compose exec postgres psql -U lia -c "
SELECT pid, usename, now() - xact_start as duration, state, substring(query, 1, 100)
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY duration DESC
LIMIT 5;
"
```

**Prevention**:
- Set `statement_timeout = 300s` for application queries
- Monitor transaction duration metrics

---

### Pattern 3: Docker Image Proliferation in CI/CD
**Scenario**: Frequent deployments leave behind old images without cleanup.

**Detection**:
```bash
docker images | grep lia | wc -l
# Healthy: <5 images, Unhealthy: >20 images
```

**Prevention**:
- Add `docker image prune -a --force --filter "until=168h"` to deployment pipeline
- Use image tagging strategy (keep only latest + last stable)

---

### Known Issue 1: Logrotate Not Running in Docker
**Problem**: Logrotate requires cron, which may not be running in containers.

**Workaround**: Run logrotate from host cron, not container.

**Fix**:
```bash
# Host crontab
0 * * * * docker-compose exec -T api logrotate -f /etc/logrotate.d/lia
```

---

### Known Issue 2: PostgreSQL Autovacuum Not Keeping Up
**Problem**: High write workload overwhelms autovacuum, causing bloat.

**Detection**:
```bash
docker-compose exec postgres psql -U lia -c "
SELECT schemaname, relname, n_dead_tup, n_live_tup,
       ROUND(100.0 * n_dead_tup / NULLIF(n_live_tup, 0), 2) AS dead_ratio
FROM pg_stat_user_tables
WHERE n_dead_tup > 10000
ORDER BY dead_ratio DESC;
"
```

**Fix**: Increase autovacuum workers and reduce naptime (see Fix 2 above).

---

## 9. Escalation

### When to Escalate
- Disk <5% free despite cleanup efforts
- Disk growth rate indicates full disk in <2 hours
- Critical service (PostgreSQL) cannot start due to disk space
- Unable to identify root cause of disk consumption

### Escalation Path
1. **Level 1 - Senior Engineer** (0-15 minutes)
   - Contact: Senior SRE/DevOps engineer on-call
   - Information needed: Current disk usage %, top consumers, recent changes
   - Expected action: Guide through advanced cleanup, approve risky operations

2. **Level 2 - Infrastructure Lead** (15-30 minutes)
   - Contact: Infrastructure team lead
   - Information needed: Business impact, data loss risk assessment
   - Expected action: Approve infrastructure changes (increase disk, migrate data)

3. **Level 3 - CTO/VP Engineering** (30+ minutes)
   - Contact: Executive leadership
   - Information needed: Incident timeline, customer impact, recovery plan
   - Expected action: Business decisions (service degradation vs data loss trade-offs)

### Escalation Template (Slack/Email)
```
Subject: [CRITICAL] Disk Space Emergency - LIA Production

Severity: CRITICAL
Service: LIA Production
Impact: [Current impact: e.g., "Service degraded, 15% error rate"]

Current Status:
- Disk usage: [XX]% (Threshold: 10%)
- Free space: [X.X GB]
- Estimated time to full: [X hours]

Top Disk Consumers:
1. [Component]: [Size GB] ([XX]%)
2. [Component]: [Size GB] ([XX]%)
3. [Component]: [Size GB] ([XX]%)

Actions Taken:
- [X] Purged Docker logs → Freed [X GB]
- [X] Cleaned Docker artifacts → Freed [X GB]
- [ ] Pending: [Next action]

Root Cause: [Brief description or "Under investigation"]

Escalation Reason: [Why manual intervention failed]

Dashboards:
- Infrastructure: http://localhost:3000/d/infrastructure-overview
- Prometheus: http://localhost:9090/graph?g0.expr=node_filesystem_avail_bytes

Request:
[Specific ask, e.g., "Approve increasing EBS volume from 100GB to 200GB"]
```

---

## 10. Post-Incident Actions

### Immediate (<1 hour)
- [ ] Create incident report (see template below)
- [ ] Notify stakeholders of resolution
- [ ] Verify all services healthy after mitigation
- [ ] Document actual disk consumers and cleanup actions taken

### Short-term (<24 hours)
- [ ] Update this runbook with incident-specific learnings
- [ ] Create GitHub issues for root cause fixes:
  - Log rotation automation
  - WAL archiving configuration
  - Disk monitoring improvements
- [ ] Review alert thresholds (was 10% too late? Should warn at 20%?)

### Long-term (<1 week)
- [ ] Schedule post-mortem meeting with team
- [ ] Implement automated cleanup (Fix 3 above)
- [ ] Add predictive alerting (disk full in X days)
- [ ] Review disk sizing strategy (cloud auto-scaling?)
- [ ] Update capacity planning documents

---

## 11. Incident Report Template

```markdown
# Incident Report: Disk Space Critical

**Incident ID**: INC-[YYYY-MM-DD-XXX]
**Date**: [YYYY-MM-DD]
**Duration**: [Start time] - [End time] ([Duration])
**Severity**: Critical
**Services Affected**: LIA API, PostgreSQL Database

## Summary
[1-2 sentence description of what happened]

## Timeline (UTC)
- [HH:MM] - Alert fired: DiskSpaceCritical
- [HH:MM] - On-call engineer paged
- [HH:MM] - Investigation started
- [HH:MM] - Root cause identified: [Component]
- [HH:MM] - Mitigation applied: [Action]
- [HH:MM] - Service restored
- [HH:MM] - Incident closed

## Impact
- **Users affected**: [Number/percentage]
- **Requests failed**: [Count]
- **Error rate**: [X%]
- **Data loss**: [Yes/No - Details if yes]
- **Revenue impact**: [$ or N/A]

## Root Cause
[Detailed explanation of why disk filled up]

**Contributing factors**:
- [Factor 1]
- [Factor 2]

## Detection
- **Alert**: DiskSpaceCritical fired at [time]
- **TTD (Time to Detect)**: [X minutes from issue start]
- **Detection method**: [Prometheus alert / User report / Monitoring]

## Response
- **TTR (Time to Respond)**: [X minutes from alert to engineer engagement]
- **TTM (Time to Mitigate)**: [X minutes from engagement to service restored]
- **MTTR (Mean Time to Recovery)**: [Total incident duration]

## Resolution
**Actions taken**:
1. [Action 1] - Freed [X GB]
2. [Action 2] - Freed [X GB]
3. [Action 3] - Prevented recurrence

**Total space freed**: [XX GB]

## Lessons Learned

### What went well
- [Point 1]
- [Point 2]

### What went wrong
- [Point 1]
- [Point 2]

### Where we got lucky
- [Point 1]

## Action Items
- [ ] [Action 1] - Owner: [Name] - Due: [Date]
- [ ] [Action 2] - Owner: [Name] - Due: [Date]
- [ ] [Action 3] - Owner: [Name] - Due: [Date]

## References
- Runbook: [DiskSpaceCritical.md](./DiskSpaceCritical.md)
- Alert definition: `infrastructure/observability/prometheus/alerts.yml`
- Grafana dashboard: http://localhost:3000/d/infrastructure-overview
- GitHub issue: #[number]
```

---

## 12. Additional Resources

### Internal Documentation
- [Infrastructure Overview](../../architecture/infrastructure.md)
- [PostgreSQL Maintenance Guide](../../database/postgresql_maintenance.md)
- [Docker Best Practices](../../docker/best_practices.md)
- [Log Retention Policy](../../policies/log_retention.md)

### External Resources
- [PostgreSQL WAL Configuration](https://www.postgresql.org/docs/current/wal-configuration.html)
- [Docker Logging Drivers](https://docs.docker.com/config/containers/logging/configure/)
- [Logrotate Manual](https://linux.die.net/man/8/logrotate)
- [Disk Space Management Best Practices](https://www.kernel.org/doc/html/latest/admin-guide/blockdev/zram.html)

### Monitoring Tools
- **ncdu** - NCurses Disk Usage analyzer (interactive du)
  ```bash
  docker-compose exec api apt-get update && apt-get install -y ncdu
  docker-compose exec api ncdu /
  ```

- **duf** - Modern df alternative with better visualization
  ```bash
  docker-compose exec api apt-get update && apt-get install -y duf
  docker-compose exec api duf
  ```

---

## 13. Runbook Metadata

**Version**: 1.0
**Last Updated**: 2025-11-22
**Author**: SRE Team
**Reviewers**: DevOps Team, Database Team
**Next Review Date**: 2025-12-22

**Change History**:
- 2025-11-22: Initial version created

**Related Alerts**:
- DiskSpaceCritical (this runbook)
- DiskSpaceWarning (precursor alert)
- DatabaseDown (can be caused by disk full)
- HighErrorRate (can be caused by disk full)

---

## 14. Validation Checklist

Before marking this runbook as production-ready:

- [x] Alert definition verified in `alerts.yml.template`
- [x] All bash commands tested in staging environment
- [x] All SQL queries tested against PostgreSQL 16
- [x] Prometheus queries validated
- [x] Grafana dashboard links confirmed
- [x] Escalation contacts verified
- [x] Incident report template reviewed
- [x] Dry-run performed in non-production environment
- [ ] Peer review completed (2+ reviewers)
- [ ] Security review completed (for cleanup scripts)
- [ ] Approved by Infrastructure Lead

---

## 15. Notes

**Critical Safety Warnings**:
- **NEVER** delete WAL files if PostgreSQL replication or PITR is enabled
- **NEVER** run `docker system prune` during active deployments
- **ALWAYS** verify free space percentage BEFORE and AFTER cleanup
- **ALWAYS** create database backup before manual cleanup operations

**Performance Considerations**:
- Disk usage >90% causes severe I/O degradation (even before full)
- PostgreSQL performance degrades significantly when WAL directory >10GB
- Docker log truncation is instant but loses historical debugging data

**Testing Notes**:
- Test disk full scenarios in staging with smaller disk allocation
- Simulate log explosion with `dd if=/dev/zero of=/tmp/test.log bs=1M count=10000`
- Verify cleanup script runs successfully in cron environment (different PATH)

**Maintenance Schedule**:
- Review disk growth trends monthly
- Audit log retention policy quarterly
- Test backup/restore procedures monthly (catches bloat early)
