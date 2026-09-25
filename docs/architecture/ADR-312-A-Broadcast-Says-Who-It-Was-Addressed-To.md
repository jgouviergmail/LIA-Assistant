# ADR-312 — A broadcast says who it was addressed to, and the administrator reads what was sent

**Status**: accepted — 2026-09-24 (owner request: under the broadcast form, the paginated history of what was sent — date, recipients, expiry)
**Amends**: the admin broadcast feature (`domains/notifications`), ADR-185 (exact totals), ADR-184 (published bounds)

## Context

The administrator could send a broadcast to every active account or to a selection,
and could never read back what had been sent. Writing the history exposed three
defects, all measured on the code before anything was changed:

- **A targeted broadcast was stored without its recipients.** SSE and FCM reached the
  chosen accounts at send time, and `GET /notifications/broadcasts/unread` then served
  the same broadcast to EVERY account at its next sign-in: the unread listing had
  nothing to filter on.
- **An empty selection meant everyone.** `user_ids=[]` took the « all users » branch —
  the one input that should address nobody addressed the whole instance.
- **FCM tokens were read one account at a time** (N+1 queries per language group).

A history also needs what the row never kept: who a targeted broadcast went to.

## Decision

1. **The audience is part of the broadcast.** `admin_broadcasts.audience` (`all` |
   `selected`, NOT NULL, default `all`) and `admin_broadcast_recipients` (one row per
   addressed account, both foreign keys CASCADE, unique pair). The audience is RESOLVED
   before the row is written (Archive-First keeps its order: persist, then send), and a
   selection addressing no active account is refused (400) rather than widened.
2. **The unread listing filters on it**: a `selected` broadcast reaches only its
   recipients' unread list (`EXISTS` on the recipients table).
3. **The backfill reads what the send route always wrote** into the admin audit log
   (`admin_broadcast_sent`, `details.is_targeted`, `details.target_user_ids`): a
   targeted broadcast becomes `selected` with one recipient row per listed account that
   still exists. A malformed or missing audit leaves the row as what it effectively
   was — `all` — and never aborts the upgrade (migration `a19e985e4ce5`, idempotent).
4. **`GET /notifications/admin/broadcasts`** (superuser) serves one page and its EXACT
   total (ADR-185), each row with its audience, a bounded sample of recipients plus
   their exact count, the expiry instant AND the delay the admin chose (recovered by
   rounding: only the instant is stored), and its read receipts. The page size is
   bounded and published (ADR-184); the whole page costs four queries whatever its size.
   The message is shown as written — reading the history never triggers the lazy
   translation the recipients' listing performs.
5. **FCM tokens are read once per language group**, chunked under the `IN` bound, and
   **all of them before the first network call** (ADR-304): they are read with the
   audience, so the commit that writes the broadcast ends the only read transaction.
   The delivery used to read a group's tokens between two pushes, holding the request's
   transaction open while FCM answered, group after group. Measured on Docker dev with
   `pg_stat_activity` during a simulated push: one backend `idle in transaction` in the
   old order (the probe's positive control), none after.
6. **The web form refreshes the history after a send** (`usePagedSection` gained a
   `refreshKey`), with the empty, loading and error states of every paged section.

## Consequences

- A targeted broadcast now stays targeted for its whole life — at send time, at the
  next sign-in, and in the history.
- The recipients table is purged with either account and exported with the
  recipient's archive (`user_data_map`, account deletion, export builder).
- Proven on real PostgreSQL (`tests/integration/domains/notifications/`): the backfill
  over well-formed, malformed and dangling audits, the unread filtering, the history's
  totals and samples.
