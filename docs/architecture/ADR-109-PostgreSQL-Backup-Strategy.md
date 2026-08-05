# ADR-109: PostgreSQL Backup Strategy — pg_dump Sidecar with Tested Restore

**Status**: ✅ IMPLEMENTED (2026-07-08)
**Author**: Claude Code (Fable 5)
**Related**: [ADR-093](ADR-093-Security-Hardening-Proxy-XSS.md) (prod port posture), runbook [DATABASE_BACKUP_RESTORE.md](../runbooks/DATABASE_BACKUP_RESTORE.md)

## Context

The 2026-07-07 360° audit found **no PostgreSQL backup tooling versioned in the
repository**: no scheduled `pg_dump`, no retention policy, no restore runbook.
Production runs on a single Raspberry Pi 5 (`docker-compose.prod.yml`, service
`postgres`, image `pgvector/pgvector:pg16`, volume `postgres_data`) and the
database holds encrypted personal data, LangGraph checkpoints, memories,
journals and billing records. RPO was therefore **undefined** — the single
worst operational risk of the product. A backup that has never been restored
is not a backup; the decision had to include a *tested, documented* restore.

## Decision

Add a **`postgres-backup` sidecar** based on
**`prodrigestivill/postgres-backup-local:16-alpine`** to both compose files,
with every parameter `.env`-driven (section `[80] DATABASE BACKUP`), a
dedicated storage target, a verification script that performs a real restore,
and Taskfile entry points (`backup:now`, `backup:verify`).

Key choices, each with its evidence or rationale:

1. **Sidecar over a custom cron + pg_dump script.** The image natively
   provides exactly the required retention model (`BACKUP_KEEP_DAYS/WEEKS/
   MONTHS` → `daily/`, `weekly/`, `monthly/`, `last/`), cron scheduling,
   a baked-in container healthcheck, and a single-command manual trigger
   (`/backup.sh`). A custom script would re-implement ~200 lines of rotation,
   locking and error handling with zero added capability. Verified before
   adoption: manifest publishes `linux/arm64` (RPi5 OK); embedded client is
   `pg_dump 16.10`, matching the `pg16` server major; the `HEALTHCHECK` is in
   the image config (`curl -f http://localhost:$HEALTHCHECK_PORT/`).
2. **Explicit `POSTGRES_EXTRA_OPTS` — never image defaults.** Set to
   `-Z6 --clean --if-exists`: full database (no schema filter), gzip 6, and
   self-cleaning statements so a restore is one command into either a fresh
   throwaway container or the live database. Some upstream examples ship a
   `--schema=public` filter; pinning the options in our compose closes that
   class of silent under-backup.
3. **Prod storage = host bind mount** (`POSTGRES_BACKUP_HOST_DIR`, default
   `../lia-data/postgres-backups`, `chmod 700` created by the generated
   `deploy.sh` *before* `up`, so Docker never auto-creates it 755). The default
   resolves **outside the deployed directory**, which is not cosmetic: it was
   `./backups/postgres` until 2026-08-05, i.e. inside the tree every deployment
   replaces, so each deploy erased every dump taken since the previous one — the
   directory was measured empty and stamped at the exact deploy time. Retention
   was effectively zero while the sidecar reported success. `deploy.sh` now warns
   when the configured value sits inside the deployed tree. A bind (not a named
   volume) keeps dumps directly reachable for the planned off-site `rclone`
   sync and host-level permission control. **Dev storage = named volume**
   (`postgres_backups`): the image's rotation uses hardlinks/symlinks, which
   are unreliable on Windows bind mounts. The verification script reads dumps
   via `docker cp`, making the storage type transparent.
4. **Schedule evaluated in UTC by default** (`POSTGRES_BACKUP_TZ=Etc/UTC`,
   overridable) — consistent with the project-wide no-hardcoded-timezone rule.
5. **No application Settings module.** The `POSTGRES_BACKUP_*` variables are
   consumed by docker-compose alone (same pattern as `GRAFANA_ADMIN_USER`).
   The parameterizable-in-`.env` project rule is honored without widening the
   API config surface.
6. **Verification is a first-class artifact.**
   `infrastructure/docker/backup/verify-backup.sh` (shipped to the Pi — the
   `infrastructure/docker/` tree is part of the PROD bundle) restores the
   latest dump into a throwaway `pgvector/pgvector:pg16` container and
   compares `alembic_version`, public-table count, and row counts of three
   reference tables against the live source. Live row-count drift is WARN;
   SQL errors, schema mismatch or an empty restored table are FAIL.
7. **Resource envelope on the Pi**: `0.25 CPU / 128M` limit (idle it is a
   cron loop; during a dump, pg_dump + gzip stream with bounded memory) —
   same gabarit as the other small sidecars (exporters).

## Alternatives considered

- **Custom cron service + hand-written pg_dump script** — rejected: strictly
  more code to maintain for the same runtime footprint (see 1).
- **Host cron on the Pi (outside compose)** — rejected: not versioned with the
  stack, invisible to `docker ps`/Portainer/healthchecks, breaks the
  everything-in-the-repo operating model.
- **WAL archiving / PITR (wal-g, pgBackRest)** — rejected *for now*: superior
  RPO but a much heavier operational surface (archive management, S3 target,
  restore complexity) than a single-user product needs today. The pg_dump
  RPO (24 h default, `.env`-tunable) is accepted and now *defined*, which is
  the point of this ADR.

## Consequences

- RPO drops from **undefined** to **≤ 24 h** (tunable); RTO is minutes with a
  documented, drilled, single-command restore.
- ~18 compressed dumps at steady state (7d + 4w + 6m + last); disk covered by
  the existing DiskSpaceCritical alert.
- Restore procedure includes the systemic aftermath: alembic revision check
  against deployed code, Redis FLUSHALL (sessions/caches built against
  pre-restore state), API/web restart — see runbook.
- Known gaps, accepted and tracked for **phase 2** (to be costed separately):
  off-site encrypted `rclone` copy (dumps currently share the NVMe with the
  database — no disk-failure protection), `attachments_data`/`skills_data`
  volumes not covered, no push alerting on backup failure (webhook hooks
  available in the image if wanted).

## Verification (2026-07-08)

**Dev**: real backup triggered via the sidecar; restore into a throwaway
`pgvector/pgvector:pg16` container via `task backup:verify`: 0 SQL errors,
`alembic_version` identical to `alembic heads` (repo) and to the live source,
public-table count identical, row counts on `users`, `conversations`,
`conversation_messages` identical. `docker compose -f docker-compose.prod.yml
config` renders without error.

**Production (post-deploy drill, same day)**: sidecar `healthy` on the Pi,
backup directory created `drwx------` by `deploy.sh`, real ~119 MB dump
produced with full three-tier rotation, then `verify-backup.sh` run against
the live production database: restore with 0 SQL errors, `alembic_version`
MATCH, 55/55 public tables, identical row counts (111 users / 5 conversations
/ 453 messages). The backup chain is proven end-to-end in both environments.
