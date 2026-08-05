# PostgreSQL Backup & Restore — Production Runbook

> Automated pg_dump backups of the LIA production database (Raspberry Pi 5),
> with a tested restore procedure. Decision record: [ADR-109](../architecture/ADR-109-PostgreSQL-Backup-Strategy.md).

**Version**: 1.0
**Date**: 2026-07-08
**Statut**: ✅ Complète

---

## Overview

| Property | Value |
|----------|-------|
| **Mechanism** | `prodrigestivill/postgres-backup-local:16-alpine` sidecar (`postgres-backup` service, both compose files) |
| **What is backed up** | The full `${POSTGRES_DB}` database (schema + data, no schema filter) via `pg_dump` 16 |
| **Format** | Plain SQL, gzip level 6, `--clean --if-exists` (self-cleaning restore) |
| **Schedule** | `POSTGRES_BACKUP_SCHEDULE` (default `@daily`, evaluated in `POSTGRES_BACKUP_TZ`, default UTC) |
| **Rotation** | `daily/` × `POSTGRES_BACKUP_KEEP_DAYS` (7) · `weekly/` × 4 · `monthly/` × 6 + `last/` |
| **Location (prod)** | Host bind mount `POSTGRES_BACKUP_HOST_DIR` (default `../lia-data/postgres-backups`, chmod 700, created by `deploy.sh`). It resolves **outside** the deployed directory on purpose: the previous default `./backups/postgres` sat inside the tree each deployment replaces, so every deploy erased every dump (measured 2026-08-05). `deploy.sh` warns if the configured value is inside the deployed tree. |
| **Location (dev)** | Named volume `postgres_backups` (Windows bind mounts break the image's hardlink/symlink rotation) |
| **RPO** | = backup interval (default **24 h**) |
| **RTO** | Minutes (single-command restore; see below) |
| **Healthcheck** | Baked into the image: `curl -f http://localhost:8080/` against its internal webhook server |

All knobs live in `.env` section **[80] DATABASE BACKUP** — no hardcoded values.
These variables are consumed by docker-compose only; the API has no Settings module for them (deliberate, ADR-109).

Dumps contain personal data (PII columns are Fernet-encrypted by the app, but schema
and non-encrypted columns are readable). Treat every dump as sensitive: keep the
directory `chmod 700`, never copy a dump to an unencrypted off-site target.

---

## Manual backup

```bash
# Dev (default)
task backup:now

# Prod (on the Pi, from the PROD directory)
task backup:now COMPOSE_FILE=docker-compose.prod.yml
# or without Task:
docker exec lia-postgres-backup-prod /backup.sh
```

The dump lands in `/backups/last/<db>-<YYYYMMDD-HHmmss>.sql.gz` inside the sidecar
(and therefore in `POSTGRES_BACKUP_HOST_DIR` on the prod host).

### List available backups

```bash
# Prod: directly on the host
ls -lR ./backups/postgres

# Dev (named volume): through the sidecar
docker exec lia-postgres-backup-dev sh -c 'ls -lR /backups'
```

### Fallback source: pre-deploy snapshots

**Check this whenever `./backups/postgres` looks empty or unexpectedly recent.**

`deploy-prod.ps1` copies the entire production directory to
`~/lia-backups/backup-<timestamp>/` before each deployment (`cp -r`, step 5). Those
snapshots therefore contain a **full copy of the backup tree as it was at deploy
time**, including `daily/`, `weekly/`, `monthly/` and `last/`.

That makes them a second, independent restore source — and it has already
mattered: on 2026-07-24 the live `~/lia/backups/postgres` was found empty (the
directory itself had been recreated at 18:27), while a complete dump from 02:23
the same day was still sitting in `~/lia-backups/backup-2026-07-24_022316/`.
Nothing in this runbook pointed there, so the operator would have concluded no
restore point existed.

```bash
# Newest dump across ALL sources, live tree and snapshots alike
find ~/lia/backups ~/lia-backups -name '*.sql.gz' \
  -printf '%TY-%Tm-%Td %TH:%TM  %10s  %p\n' 2>/dev/null | sort -r | head

# Recover a dump from a snapshot into the live tree
cp ~/lia-backups/backup-<timestamp>/backups/postgres/daily/lia-<date>.sql.gz \
   ~/lia/backups/postgres/daily/
```

Two caveats before relying on it:

- Snapshot retention is driven by the deploy cadence, not by
  `BACKUP_KEEP_DAYS`/`WEEKS`/`MONTHS` — an infrequently deployed period leaves no
  new snapshot.
- A snapshot is only as fresh as the last deployment. Treat it as a safety net,
  never as the primary RPO.

If the live tree is empty, restore the safety net immediately rather than waiting
for the `@daily` schedule — a manual run costs one command:

```bash
docker exec lia-postgres-backup-prod /backup.sh
```

---

## Integrity verification (restore drill)

Runs the **real proof**: copies the latest dump out of the sidecar, restores it into
a **throwaway** `pgvector/pgvector:pg16` container (the live database is never touched),
then compares `alembic_version`, the public-schema table count, and row counts of
3 reference tables. Exit 0 = PASS.

```bash
# Dev
task backup:verify

# Prod (on the Pi)
BACKUP_CONTAINER=lia-postgres-backup-prod SOURCE_CONTAINER=lia-postgres-prod task backup:verify
# or, if Task is not installed on the Pi (same script, shipped in the PROD bundle):
BACKUP_CONTAINER=lia-postgres-backup-prod SOURCE_CONTAINER=lia-postgres-prod \
  bash infrastructure/docker/backup/verify-backup.sh
```

Overridables (env): `BACKUP_FILE` (verify a specific dump), `VERIFY_TABLES`,
`VERIFY_IMAGE`. Row-count differences on a **live** database are reported as `WARN`
(writes since the dump); `FAIL` is reserved for SQL errors, schema mismatch, or a
restored table that is empty while the source is not.

Run this drill **after every schema migration deploy** and at least monthly.

---

## Full restore

### A. Into a throwaway container (inspection / partial recovery)

```bash
BACKUPFILE=./backups/postgres/last/lia-20260708-030000.sql.gz

docker run -d --name lia-restore-tmp \
  -e POSTGRES_USER=<user> -e POSTGRES_DB=lia -e POSTGRES_HOST_AUTH_METHOD=trust \
  pgvector/pgvector:pg16
# wait for: docker exec lia-restore-tmp pg_isready

gunzip -c "$BACKUPFILE" | docker exec -i lia-restore-tmp psql -U <user> -d lia
```

Then `docker exec -it lia-restore-tmp psql -U <user> -d lia` to inspect or COPY out
specific rows. Remove with `docker rm -f lia-restore-tmp`.

### B. Into production (disaster recovery)

> ⚠️ Destructive: the dump carries `--clean --if-exists` and will DROP and recreate
> every object it contains. Stop the application first.

```bash
cd /home/<user>/lia   # compose directory on the Pi (deploy target)

# 1. Stop everything that writes to the DB (postgres itself stays up)
docker compose -f docker-compose.prod.yml stop api web

# 2. Restore (single command — self-cleaning dump)
gunzip -c ./backups/postgres/last/<dump>.sql.gz \
  | docker exec -i lia-postgres-prod psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"

# 3. Check schema revision vs the deployed code (informational)
docker exec lia-postgres-prod psql -tA -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c 'SELECT version_num FROM alembic_version'
# If the dump predates the deployed code, no manual action is needed: the API
# entrypoint (apps/api/docker-entrypoint.sh) runs `alembic upgrade head` on
# every start, so step 5 below applies the missing migrations automatically.

# 4. Flush Redis (sessions + caches may reference post-dump state; users re-login)
docker exec lia-redis-prod redis-cli -a "$REDIS_PASSWORD" FLUSHALL

# 5. Restart
docker compose -f docker-compose.prod.yml start api web
curl -f https://lia-back.jeyswork.com/health
```

Step 4 matters: LangGraph checkpoints live in PostgreSQL (restored consistently),
but Redis holds sessions, rate-limit counters and caches built against the
pre-restore database. Flushing avoids serving stale cross-references; the cost is
one re-login for every user.

### If the whole `postgres_data` volume is lost

```bash
docker compose -f docker-compose.prod.yml up -d postgres   # fresh, empty PGDATA
# postgres-init.sql runs automatically (extensions), then restore as in B.2-B.5
```

---

## Monitoring & disk usage

- The sidecar is `unhealthy` in `docker ps` if its internal webhook server dies —
  it also appears in Portainer and cAdvisor (Dashboard 03) like any container.
- Backup runs and failures are visible in its logs (collected by Promtail → Loki):
  `docker logs lia-postgres-backup-prod`.
- Worst-case disk: (7 + 4 + 6 + last) ≈ 18 compressed dumps. First prod dump measured
  at ~119 MB (2026-07-08) → steady state ≈ 2-3 GB; the existing
  [DiskSpaceCritical](alerts/DiskSpaceCritical.md) alert covers the NVMe globally.
- Cosmetic: the sidecar image inherits `VOLUME /var/lib/postgresql/data` from the
  postgres base image, so each recreate leaves a small anonymous Docker volume
  behind. Harmless (a few MB); cleaned by the usual `docker volume prune`.

## Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| Sidecar `unhealthy` | `docker logs lia-postgres-backup-prod`. Usually bad credentials after a password rotation → recreate the service (`docker compose up -d postgres-backup`). |
| `password authentication failed` | `.env` `POSTGRES_PASSWORD` drifted from the value inside `postgres_data`. Align `.env`, recreate the sidecar. |
| Empty `/backups/last` | Schedule hasn't fired yet (check `POSTGRES_BACKUP_TZ`) — trigger `task backup:now` and re-check. |
| `verify-backup.sh` FAIL on alembic mismatch | The dump predates the last migration. Expected right after a deploy; re-run after the next scheduled backup. Any other case: investigate before trusting backups. |
| Rotation errors on dev/Windows | Expected on bind mounts (hardlinks). Dev uses the `postgres_backups` named volume precisely for this — don't switch it to a bind. |

## Known limitations (phase 2 — deliberately out of scope, see ADR-109)

1. **No off-site copy yet**: dumps live on the same NVMe as the database. An
   encrypted `rclone` sync is the planned phase 2 — until then, a disk failure
   destroys both. The bind-mount layout was chosen to make that sync trivial.
   Encryption options (on-site rclone-crypt copy, age-at-dump, device-level
   LUKS) were analyzed and deliberately deferred — see
   [ADR-110](../architecture/ADR-110-Backup-Encryption-Options.md).
2. **Database only**: the `attachments_data` and `skills_data` volumes (file
   attachments, user skills) are not covered.
3. **No PITR**: pg_dump snapshots only — recovery granularity is the schedule
   interval, not WAL-level.
4. ~~**No push alert on backup failure**~~ — closed by ADR-119 (2026-07): the
   `BackupFailed` alert probes the sidecar's healthcheck webhook via
   blackbox-exporter and emails the administrator after 15 minutes of failure
   (runbook: [BackupFailed.md](alerts/BackupFailed.md)).
