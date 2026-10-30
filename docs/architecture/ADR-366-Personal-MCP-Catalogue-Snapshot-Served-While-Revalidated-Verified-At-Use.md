# ADR-366 — A personal MCP catalogue is a snapshot: served while it is revalidated, verified at use

**Status**: Accepted, 2026-10-28.
**Date**: 2026-10-28

**Amends**:
[ADR-338](ADR-338-Live-MCP-Contracts-And-Exact-Callable-Identity.md) §2 and §7 for the turn
preparation of PERSONAL MCP servers only (owner decision Q1, confirmed 2026-10-22): a turn no
longer discovers a personal server's catalogue live when a valid snapshot exists; the exact
callable identity is still checked, at the moment of the call.
[ADR-260](ADR-260-Redis-Key-Families-Scope-And-Reset-Purge.md) gains one `USER_RUNTIME` family,
`mcp:catalogue` (the revalidation and `read_me` claims).

## Context

Measured in production over seven days (spec 2026-10-21 §0ter, H1–H5), outside the 20/10 outage:

- 48 % of chat turns discovered at least one personal MCP server before the graph started; those
  turns waited p50 3.9 s, p95 19.2 s, at most 32.8 s. Turns without a discovery: p95 0.74 s.
- The catalogue cache was per worker: 32 % of the follow-ups within fifteen minutes were cold again,
  on another worker or after the pool's idle eviction.
- Discoveries ran one server after another; replaying the measured per-server durations in parallel
  took the cold p95 from 19.2 s to 8.5 s.
- Tool embeddings were recomputed on the turn's critical path whenever the ordered tool list changed
  (31 recomputes, 1.4–16.4 s each).

The person waits for none of this when it is told; they waited for all of it in silence.

## Decision

**1. The catalogue is a snapshot on the account's own row** (`catalogue_snapshot.py`, version 2):
the tools in canonical order, a generation reserved before the discovery, the configuration and
catalogue fingerprints, the server's cache hints, whether it offers a reference tool. It is
published by compare-and-set on the generation (`domains/user_mcp/catalogue_publication.py`): an older discovery
never replaces a newer one, and a publication keeps the reference the row already holds.

**2. One pool door decides memory, snapshot or network** (`UserMCPClientPool.get_or_connect`): a
warm entry of the same configuration and a generation at least the row's is served; otherwise the
row's snapshot is hydrated (the failure pause and the cooling still gate it); otherwise the server
is discovered under a process-wide bound of concurrent discoveries and
`MCP_USER_DISCOVERY_TIMEOUT_SECONDS`.

**3. A snapshot past its age is served while it is revalidated** (Q1). Its age is the server's own
`ttlMs` when it gives a positive one — capped at a day — and
`MCP_USER_CATALOGUE_REVALIDATE_AFTER_SECONDS` otherwise: an mcp 2.x server that declared no hint
sends an explicit `0` (measured), which is the SDK's default and reads as no hint. Past that age the
entry is verified at use (§5); the background revalidation waits for the LARGER of that age and the
setting, so a short `ttlMs` never rediscovers a server on every turn. One worker claims the revalidation in
Redis (`mcp:catalogue:revalidate:{user}:{server}`, owner token); the turn never waits for it; its
outcome is counted (`mcp_user_catalogue_revalidations_total`). Without the cache, nothing is
revalidated and the snapshot keeps serving.

**4. Servers are prepared in parallel under a ceiling** (`user_preparation.prepare_user_servers`):
a server still preparing at `MCP_USER_PREPARATION_CEILING_SECONDS` is left out of THIS turn —
deferred, never cancelled: its discovery finishes and publishes for the next one (Q2 (a)).

**5. A call verifies the declaration it relies on** (`declaration_check.py`, at use): the server's
current listing in the same session; a tool now missing, an argument the current schema rejects, or
a tightened declaration refuses the call before it is sent (`MCPDeclarationChangedError`, typed
`CONFLICT`); a compatible change sends the call. The entry is marked verified only when the WHOLE
listing equals the catalogue it holds, and a revalidation is scheduled whenever it does not — the
called tool's verdict speaks for that tool alone (fresh review 2026-10-29: calling one unchanged
tool verified the server, and a tool that had become destructive was then called unchecked). A call
carries the catalogue and the declaration its adapter was built from (`built_from`, `declaration`):
when the pool's entry is no longer that catalogue — a revalidation replaced it mid-turn — the call
is checked against its own declaration even on a verified entry.

**6. `read_me` is fetched at real use** (`reference_content.py`): when the planner or the loop
actually needs a server's reference, once per server across workers (`mcp:catalogue:reference`
claim), remembered per worker on failure, refreshed in the background — never at discovery, where
0 of 314 discoveries carried any.

**7. The person is told** (M4/M5): a server still preparing after a short delay raises a polite,
closable notice naming it; a server left out at the ceiling turns that notice into « not used for
this message »; past three slow servers ONE grouped notice speaks for them and still names them
(the first three, then how many others — owner request 2026-10-29: « which one? »); a run that ends
closes the notices it still shows; nothing is shown on a channel that cannot draw it, nor for a
warm turn. The generic progress step reuses the existing step vocabulary.

**8. Embeddings leave the critical path** (M6): a vector's identity covers only the texts it embeds,
order-free and per tool; only a new or changed tool is embedded — on the turn that first meets it,
in one batch, because a tool without a vector can fall out of the planner's catalogue — while every
unchanged tool keeps its vector.

## Consequences

- A warm or snapshot-served turn of an unchanged catalogue waits for no network before the graph;
  measured on Docker dev,
  a cold turn on another worker hydrated the snapshot in 0.01 s with no discovery.
- A catalogue can be stale for one turn: the call-time verification is what keeps it honest, and it
  refuses rather than sends against a declaration the server withdrew.
- `user_mcp_session` (no production reader) is kept as the wrapper spec §5.1 describes.
- Handshake `instructions` reach the pipeline planner with the reference; the ReAct loop does not
  inject them (it reads the reference through the read_me tool).

## What this does NOT solve

- A server that is slow on EVERY call stays slow at use; only its discovery left the turn.
- DNS failover on the production host (spec H9) is infrastructure, outside this decision.

## Verification

- `apps/api/tests/unit/infrastructure/mcp/test_catalogue_snapshot.py`, `test_user_preparation.py`,
  `test_catalogue_revalidation.py`, `test_declaration_check.py`, `test_reference_content.py`.
- `apps/api/tests/integration/infrastructure/mcp_catalogue/test_revalidation_claim.py` (two actors, real Redis).
- `apps/api/tests/unit/domains/agents/api/test_mcp_preparation_notices.py`; web `mcp-preparation.test.ts`,
  `mcp-preparation.a11y.test.tsx`; e2e `smoke/chat-mcp-preparation.spec.ts`.
- Runtime proofs on Docker dev, proof account, zero spend, a local stub server: cold, warm,
  hydrated, slow-at-the-ceiling, identical/compatible/incompatible declarations, notices.

## Implementation references

`apps/api/src/infrastructure/mcp/` (`catalogue_snapshot.py`, `pool_catalogue.py`, `user_pool.py`, `user_preparation.py`, `catalogue_revalidation.py`,
`declaration_check.py`, `reference_content.py`, `server_vectors.py`),
`apps/api/src/domains/user_mcp/catalogue_publication.py`,
`apps/api/src/domains/agents/api/turn_preparation.py`, `apps/web/src/lib/sse-handlers/mcp-preparation.ts`.
Spec: `docs/superpowers/specs/2026-10-21-chat-dashboard-latency-analysis.md` §5.1–§5.6.
