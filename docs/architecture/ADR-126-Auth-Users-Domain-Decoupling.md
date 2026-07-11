# ADR-126: Auth/Users Domain Decoupling — Stable Dependencies for the Identity Domain

**Status**: ✅ IMPLEMENTED (2026-07-11)
**Author**: Claude Code (Fable 5)
**Related**: [ADR-067] Account Lifecycle (deletion cascade precedent — `AccountDeletionService`), [ADR-073] Last-Known Location Persistence (the moved service), [ADR-125](ADR-125-Draft-Preview-Renderer-Extraction.md) (audit-instrument convention: commit the measurement with the remediation), audit cycle 3 register (architecture area).

## Context

Audit cycle 3 introduced domain-level coupling metrics (AST import graph over
`src/domains/*`): afferent coupling Ca, efferent coupling Ce, instability
I = Ce/(Ca+Ce). The measurement surfaced a textbook Stable Dependencies
Principle violation concentrated on **auth**: the most depended-upon domain of
the system (Ca=26) also depended on 14 domains itself (I=0.35), participating
in 11 of the 31 bidirectional import cycles. The root causes, mapped
import-by-import:

- **The `User` ORM model lived in `auth/models.py`.** Every domain touching a
  user (26 of them) imported auth; `User`'s relationship annotations pulled 10
  domains into auth as `TYPE_CHECKING` edges; `users/models.py` re-exported
  `User` *from* auth — while `auth/service.py` imported it back *through*
  `users`, a gratuitous circular indirection.
- **Account-creation provisioning lived in auth** (skill states + usage-limit
  defaults at registration and OAuth creation) — lifecycle logic, duplicating
  the role the users domain already owns for deletion
  (`AccountDeletionService`).
- **Borrowed helpers**: auth imported the private `_haversine_distance` from
  the agents domain, and probed `LLMConfigOverrideCache` from the llm_config
  domain for STT availability.

## Decision

Clarify the boundary — **auth = identity & session flows; users = the User
aggregate, profile and account lifecycle** — and reduce Ce(auth) to ≤3 in
behavior-preserving increments, each gated on the full suites:

1. **Utility promotions (lot 1)**: `haversine_distance` → `src/core/geo_utils.py`
   (pure math; agents keeps a compat alias); provider API-key probe →
   `get_provider_api_key()` in `src/core/llm_config_helper.py` (existing
   core facade, same lazy-import pattern); auth's `User` re-import fixed at
   the source. The audit instrument is committed as
   **`scripts/audit/measure_coupling.py`**: it reproduces the cycle-3 figures
   exactly (all-imports semantics) and adds runtime-only columns — only
   runtime edges can produce circular-import failures, so the SDP assessment
   reads those, while the all-imports series stays comparable across cycles.
2. **Provisioning extraction (lot 2)**: `users/account_provisioning_service.py`
   (`AccountProvisioningService.provision_new_user`), the creation-side
   counterpart of `AccountDeletionService`. The two historical call sites had
   different transaction topologies (registration commits per step; the OAuth
   callback commits once at the end), so the caller chooses via an explicit
   `commit_per_step` flag — behavior preserved exactly, existing auth tests
   pass unmodified (the service keeps lazy imports, so source-level patch
   targets keep working).
3. **Model move (lot 3)**: `class User` moves to `users/models.py` (its
   re-export home), byte-identical (proven by blob comparison against HEAD);
   `user_location_service.py` (profile/location concern) moves to users;
   every importer (~84 source sites + tests) is mechanically migrated to
   `src.domains.users.models`; the transitional auth shim is then deleted.
   Files where `User` is provably annotation-only (AST analysis: annotations
   only, `from __future__ import annotations` present, no FastAPI decorators)
   import it under `TYPE_CHECKING`; FastAPI routers keep runtime imports —
   `Depends` evaluates endpoint annotations at include time.

## Consequences — measured

| Metric (measure_coupling.py) | Before (cycle 3) | After |
|---|---|---|
| Ce(auth) all-imports / runtime | 14 / 6 | **2 / 2** (users, shared) |
| Ca(auth) | 26 | **0** (sole importer left: `api/v1/routes.py`, outside the domain graph) |
| I(auth) | 0.35 | leaf domain (no afferent) |
| Cycles involving auth | 11 of 31 | **0** |
| Total bidirectional cycles, all-imports / runtime-only | 31 / 24 | 32 / 31 — every pair involves the users hub or predates the change |

**The hub cycles relocate; they do not disappear.** The users domain now
legitimately knows the domains whose per-user data it provisions and purges
(runtime, deletion cascade) *and* is imported by them for the `User` type —
so the former `auth↔X` pairs re-form as `users↔X` (19 hub pairs after the
move; the raw total goes 31→32 all-imports). The former auth cycles were
mostly typing-only (TYPE_CHECKING relationship annotations, excluded from
the runtime count); their users↔X successors are runtime on both sides
(routers import `User` for FastAPI dependency evaluation, users purges the
domains' tables), so the runtime-only count rises 24→31. This is the
accepted, explicitly arbitrated trade: an **accidental** hub (identity flows
dragging 14 domains) becomes a **coherent** one (the lifecycle orchestrator,
whose bidirectional knowledge is its documented job) — and the coupling is
now *honestly measured* instead of hidden behind typing edges. No cycle
outside the users hub was created. The runtime/typing split in the
instrument is the lever for future reduction: any new `User` importer that
only needs typing must use `TYPE_CHECKING` (applied where provably safe:
the three annotation-only briefing modules).

- auth is now an identity/session leaf: credentials, OAuth flows, session
  endpoints — nothing else. Its only domain dependencies are `users` (model +
  provisioning + location service) and `shared` (validator mixins).
- `users/models.py` (495 logical SLOC) stays under the 600-SLOC ceiling and
  under the `src.domains.*.models` MyPy override (string relationship refs).
- No DB change: the `users` table never moved; no Alembic migration; model
  registration still flows through `import_all_models()`.
- Living docs updated (AUTHENTICATION.md, LAST_KNOWN_LOCATION runbook,
  GUIDE_TESTING); historical ADRs untouched (dated documents).

**Invariants held**: zero behavior change (no endpoint, no wire contract, no
structlog event, no transaction topology touched); `User` class byte-identical
through the move; full suites green at every lot boundary; Docker boot
verified per lot; no new cycle outside the users hub.
