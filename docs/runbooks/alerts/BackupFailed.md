# BackupFailed - Runbook

**Severity**: critical
**Component**: backup
**Impact**: No direct user impact, but the restore capability (ADR-109) is at risk: the last scheduled pg_dump failed or the sidecar is down. Every hour in this state widens the potential data-loss window.
**SLA Impact**: No (RPO risk instead).

---

## 1. Alert Definition

**Alert Name**: `BackupFailed`

**Prometheus Expression**:
```promql
probe_success{job="blackbox-backup"} == 0
```

blackbox-exporter probes the healthcheck webhook baked into the `prodrigestivill/postgres-backup-local` image (`HEALTHCHECK_PORT`, default 8080). The webhook returns non-200 when the last backup run failed, and the probe fails entirely when the sidecar is down — both must page.

**Firing Duration**: `for: 15m` (tolerates probe blips; a failed nightly dump keeps failing until fixed)

**Labels**: `severity: critical`, `component: backup`, `tier: core`

---

## 2. Symptoms

### What Ops See
- `probe_success{job="blackbox-backup"} == 0` in Prometheus.
- No fresh file in the backup directory (prod: `POSTGRES_BACKUP_HOST_DIR`, default `./backups/postgres`, on the RPi5).

---

## 3. Possible Causes

### Cause 1: Sidecar container down (High Likelihood)
```bash
docker ps -a --filter name=postgres-backup
docker logs --tail 100 lia-postgres-backup-prod
```

### Cause 2: pg_dump failure — auth, disk full, version mismatch (High Likelihood)
```bash
docker logs lia-postgres-backup-prod 2>&1 | grep -iE "error|fatal|failed"
df -h   # DiskSpaceCritical may be inhibiting/accompanying this alert
```
A `POSTGRES_PASSWORD` rotation not propagated to the sidecar env is the classic auth cause.

### Cause 3: Backup directory permissions (Low Likelihood)
The host dir is `chmod 700` (created by deploy.sh); a manual recreation with wrong ownership breaks writes.

---

## 4. Resolution Steps

### Immediate
```bash
docker restart lia-postgres-backup-prod
# Trigger a manual backup right away instead of waiting for the next cron:
docker exec lia-postgres-backup-prod /backup.sh
# Verify a fresh dump appeared:
ls -lht /home/<user>/lia/backups/postgres/daily | head -3
```

### Verify restore capability (after any backup incident)
Follow `docs/runbooks/DATABASE_BACKUP_RESTORE.md` — restore the latest dump into a throwaway container and run the verification queries.

### Post-Recovery Verification
- `probe_success{job="blackbox-backup"} == 1`; alert resolves.
