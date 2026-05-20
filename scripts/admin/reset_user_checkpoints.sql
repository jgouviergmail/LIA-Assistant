-- =============================================================================
-- Emergency: wipe LangGraph checkpoints for a single thread (= conversation_id)
-- =============================================================================
--
-- Use case: a user's conversation is stuck on a checkpoint state that prevents
-- progress (eg. a pre-v2 hang where compaction wrote a partial state). After
-- the v2 hardening (Day 1+2 of the compaction plan), this should rarely be
-- needed, but it remains the fastest recovery path if state integrity is lost.
--
-- Usage:
--   psql "$DATABASE_URL" \
--     -v thread_id="'08dfb351-5336-42c8-92a9-ee46c6e7f0d0'" \
--     -f scripts/admin/reset_user_checkpoints.sql
--
-- Or via Docker on prod (RPi5):
--   docker exec -i lia-postgres-prod \
--     psql -U lia -d lia \
--     -v thread_id="'<user-uuid>'" \
--     < /path/to/reset_user_checkpoints.sql
--
-- NOTE: thread_id is set by the orchestration service to `str(conversation_id)`
-- (see apps/api/src/domains/agents/services/orchestration/service.py:870) which
-- in LIA equals the user's UUID (one conversation per user). Quote the value
-- as a SQL literal string ('...').
--
-- Safety: wrapped in a transaction; runs a COUNT to show the user what was
-- left behind. Does NOT touch business tables (messages, conversations) — only
-- LangGraph's checkpoint blobs.

\if :{?thread_id}
\else
  \echo '------------------------------------------------------------------------'
  \echo 'ERROR: missing thread_id'
  \echo '------------------------------------------------------------------------'
  \echo 'Usage:'
  \echo '  psql -v thread_id="''<uuid>''" -f reset_user_checkpoints.sql'
  \echo ''
  \echo 'Example:'
  \echo '  psql -v thread_id="''08dfb351-5336-42c8-92a9-ee46c6e7f0d0''" \\'
  \echo '       -f scripts/admin/reset_user_checkpoints.sql'
  \echo '------------------------------------------------------------------------'
  \quit
\endif

\echo 'Resetting LangGraph checkpoints for thread_id =' :thread_id

BEGIN;

-- Show what will be deleted (for the operator's audit trail).
SELECT
  (SELECT COUNT(*) FROM checkpoint_writes WHERE thread_id = :thread_id) AS writes_before,
  (SELECT COUNT(*) FROM checkpoint_blobs  WHERE thread_id = :thread_id) AS blobs_before,
  (SELECT COUNT(*) FROM checkpoints       WHERE thread_id = :thread_id) AS checkpoints_before;

-- Order matters: writes & blobs reference checkpoints, so delete leaves first.
DELETE FROM checkpoint_writes WHERE thread_id = :thread_id;
DELETE FROM checkpoint_blobs  WHERE thread_id = :thread_id;
DELETE FROM checkpoints       WHERE thread_id = :thread_id;

-- Confirm cleanup.
SELECT
  (SELECT COUNT(*) FROM checkpoint_writes WHERE thread_id = :thread_id) AS writes_after,
  (SELECT COUNT(*) FROM checkpoint_blobs  WHERE thread_id = :thread_id) AS blobs_after,
  (SELECT COUNT(*) FROM checkpoints       WHERE thread_id = :thread_id) AS checkpoints_after;

COMMIT;

\echo 'Done. The user can now start a fresh conversation turn.'
