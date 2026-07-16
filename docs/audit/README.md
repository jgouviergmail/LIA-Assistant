# LIA — Public Technical Audit Report

> **Latest assessment: 8.3/10** (199/240) across **24 normalized areas** — snapshot of 2026-07-16, released as **v1.25.0**.
> Full standalone report: [AUDIT_CODEBASE_2026-07-16_CONSOLIDE_V11.html](./AUDIT_CODEBASE_2026-07-16_CONSOLIDE_V11.html) · Method: evidence-based with systematic counter-proofs, every score backed by at least three executed evidence points · **Security is explicitly and entirely out of scope** (covered separately — see [SECURITY.md](../../SECURITY.md)).
>
> ⚠️ **The grading framework was fully revised in this cycle** (normalized 24-area grid, anchored scale, arithmetic mean, counter-analysis stage). Scores are **not comparable like-for-like** with pre-revision cycles (8.5/10 on the historical grid): the framework got stricter, not the codebase worse — this cycle closed every previously-open major and minor finding.

LIA's engineering claims are public, so their verification should be too. This report is the summary backing for every quality figure shown on the [landing page](https://lia.jeyswork.com/), the [/story field report](https://lia.jeyswork.com/story) and the README; the complete, self-contained report (scorecard, evidence register, counter-analysis, worksite prompts, annexes) is versioned next to this file. It is updated after each audit cycle — including the findings we have not fixed yet.

---

## Why we publish this

Most projects claim quality; few make the claim falsifiable. This repository is open source, its audit reports are published with their open worksites, and the sections below include the exact commands to reproduce the core measurements yourself. The score matters less than the loop that produces it: **audit → prioritized remediation → re-audit**, with every fix landing as a versioned release backed by an Architecture Decision Record.

The method is as auditable as the code: the full audit protocol — scope, referentials, evidence requirements, scoring discipline, publication pipeline — is versioned in [AUDIT_PROTOCOL.md](./AUDIT_PROTOCOL.md), and the structural metrics come from committed measurement scripts ([`scripts/audit/`](../../scripts/audit/)).

## Scope, referentials and method (V11 framework)

- **Object.** The working tree visible at the cut-off (2026-07-16 09:36 CEST, released as v1.25.0): `apps/api`, `apps/web`, `infrastructure`, `scripts`, `docs`, Taskfile, manifests, lockfiles, Dockerfiles, Compose and CI workflows. **Absolute exclusion:** any security analysis — vulnerabilities, secrets, authn/authz, cryptography, hardening, SAST/DAST, vulnerable dependencies, threat modeling, intrusion testing. No score, finding or prompt takes security into account.
- **Referentials.** Product quality: **ISO/IEC 25010:2023** and **ISO/IEC 25040:2024** (security characteristic neutralized). Architecture: **ISO/IEC/IEEE 42010:2022**. Test processes: **ISO/IEC/IEEE 29119-2:2021**; automated structural quality: **ISO/IEC 5055:2021**. Interaction: **WCAG 2.2 level AA** as the accessibility control grid, complemented by WAI-ARIA practices — no claim of full conformity is made. The audit is an internal assessment aligned on industrial referentials; it is **not** an accredited certification, a guarantee of absence of defects, or a WCAG conformity attestation.
- **Process.** Inventory (bounded contexts, files, functions, tests, migrations, workflows, docs) → static controls (Ruff, Black, MyPy strict, ESLint, clean TypeScript, i18n parity, doc links, cycles, complexity, size, baselined debts) → dynamic controls (backend suites, PostgreSQL/Redis integration, migrations, Vitest with coverage, Playwright/axe, hermetic deployment, production Docker builds) → **counter-proofs** (reactivating skipped tests, Windows execution under SelectorEventLoop, standalone Next.js build, dev-style vs production-artifact distinction, durable-RAG path inspection).
- **Qualification rule.** No finding rests solely on a comment, a green baseline, a skipped test, an exit code or a historical observation. A dedicated counter-analysis stage documents discarded false positives and corrected false negatives.
- **Scoring.** 24 independent scores in 0.5 steps, each backed by **at least three evidence points**; the global score is their plain arithmetic mean (199 ÷ 24 = 8.29 → **8.3/10**). Finding levels: *major* (assurance or an essential user quality significantly compromised), *moderate* (substantial but bounded debt), *minor* (localized, no confirmed functional impact). Effort scale E1 (< half a day) to E5 (> 3 weeks).

## Scorecard — 24 normalized areas (2026-07-16)

| # | Area | Score | Evidence highlights |
|---|------|-------|---------------------|
| 1 | Infrastructure | 8.5 | Production API and Web images built during the audit; Compose topology, readiness, backup/restore documented; deployment harness green incl. 25/25 PowerShell scenarios |
| 2 | Data & persistence | 8.5 | Alembic replays from an empty database (single head, zero drift); 579 main integrations pass against real PostgreSQL/Redis; durable transactional RAG jobs — read continuity during global reindex still incomplete |
| 3 | Configuration & dependencies | 8.5 | Lockfiles consumed by reproducible builds; modular settings, feature flags, env examples; Testcontainers works on Windows without manual override |
| 4 | Architecture | 7.5 | 32 bounded contexts with explicit assembly; pipeline / ReAct / read-only aggregation separated; **31 runtime import cycles** and several strongly-coupled hubs |
| 5 | Application design | 8.5 | Multi-level HITL contracts, bounded LangGraph state, error taxonomies, partial degradation, leases/reapers/durable jobs |
| 6 | Genericity | 8.0 | BaseRepository, validation mixins, abstract clients, LLM factories, connector resolvers, boot-time registry completeness asserts |
| 7 | Extensibility | 8.5 | Agent/tool guides and integration checklists; versioned prompts and feature flags; 6-language parity enforced automatically |
| 8 | Implementation | 7.5 | Ruff/Black/MyPy/ESLint/TypeScript green over 6,145 analyzed backend functions; **347 functions at CC≥15** and 165 above 100 SLOC |
| 9 | Maintainability | 7.0 | Size/complexity/coupling ratchets in place; 40 backend files at ≥800 SLOC; max hotspot 692 SLOC; max frontend complexity 74 |
| 10 | Quality tooling | 9.0 | Static, AST and documentation gates automated; cycle/complexity/MyPy/React/size/coverage ratchets; lint, migrations, integration, E2E, deploy and builds all runnable locally |
| 11 | Patterns & practices | 8.0 | Structured logging and centralized tool contracts; consistent DDD, Pydantic v2, SQLAlchemy v2; **91 MyPy exemption pairs** keep zones outside strict guarantee |
| 12 | Robustness | 8.5 | Timeouts, retries, partial errors and fallbacks covered; migration rollback and job recovery tested; strict suites with zero ResourceWarning or pool leak |
| 13 | Reliability | 8.5 | 10,148 fast unit + 972 agents tests pass; 582 selected integration tests pass; RAG reindex still temporarily interrupts user search |
| 14 | Performance | 7.5 | TTFT, durations and costs instrumented; caches, single-flight and dedicated streaming paths; no full load campaign executed |
| 15 | Optimization | 8.0 | Multi-level caches and concurrent aggregations; economical pipeline mode and in-memory pricing; structural hotspots still limit reasoned optimization |
| 16 | Scalability | 8.5 | PostgreSQL/Redis pools and separated concurrent sessions; 20 concurrent LangGraph invocations and 20 concurrent store cycles pass on Windows; no full capacity campaign |
| 17 | Operability & observability | 8.5 | 2 valid Prometheus rule files, 22 structurally-valid Grafana dashboards, structured logs, probes, business metrics, runbooks |
| 18 | CI/CD & delivery | 9.0 | Production images built from locks; hermetic E2E and migrations wired into the gates; delivery, readiness and rollback covered by the harnesses |
| 19 | Tests & assurance | 8.5 | 11,967 backend tests collected with controlled taxonomy/allowlist; 1,222 frontend tests and 17 Chromium E2E pass; frontend coverage at **35.4%** with 255 instrumented files at zero |
| 20 | Documentation | 8.5 | 0 broken links and 0 stale paths in living documentation; rich index, ADRs, guides, runbooks; historical (non-blocking) debt isolated |
| 21 | Portability | 8.5 | Windows development and Linux images both validated; Playwright in the official glibc image; Testcontainers and concurrent psycopg pools pass under Windows SelectorEventLoop |
| 22 | Compatibility | 8.0 | API versioning and SSE symmetry tests; MCP, CalDAV, IMAP, structured vCard interop; browser validation limited to Chromium |
| 23 | Functional suitability | 8.5 | Broad feature surface, explicitly wired domains; builds, unit, agents, integration, E2E and migrations all pass; real external providers not exercised |
| 24 | Usability & accessibility | 9.0 | 0 static jsx-a11y violations and strict 6-language parity; 17/17 E2E incl. axe, keyboard, 320 px mobile, zoom and dark mode against a standalone build |

## The proof is the loop, not the snapshot

Between the previous cycle (V10, 2026-07-15) and this one — a single remediation wave, shipped as v1.25.0 — **every previously-open major and minor finding was closed and re-verified by executed counter-proof**:

| Finding (previous register) | Resolution — all verifiable in this repository |
|---|---|
| Windows integration bootstrap broken (testcontainers, 420+ silent skips) | Root cause: a transitive wheel clobbering `urllib3`; editor opt-out encoded on all 4 install surfaces + preflight + namespace guard — full PostgreSQL integration campaign now runs on Windows |
| Integration fixtures leaking to the developer database | Process-wide redirection (settings, global engine, LangGraph checkpointer/store pools) + a guard that fails loudly on any dev-DB connection while Testcontainers is active |
| Whole-run freeze at checkpointer init | Root cause: `CREATE INDEX CONCURRENTLY` migrations deadlocking against the per-test transaction — LangGraph tables now provisioned once per session; regression pinned by a bounded test proven red/green |
| Launcher-dependent test verdicts (12 failures under `task`, green under pytest) | Root cause: the task runner exported the entire developer `.env` into test processes — scrubbed before `.env.test` loads; contract proven red under simulated contamination |
| E2E harness instability (dev-server 500s, corrupted webpack cache) + phantom dark-mode WCAG violations | Proof runs moved to the production standalone server (managed CI web server fixed for `output: standalone`); the "dark contrast defect" was an unstyled-page artifact — palette proven clean, **17/17 E2E including dark mode**; a guard now aborts any scan on an unstyled page |
| Production build broken on a fresh install | An undeclared transitive import (`hast-util-sanitize`) replaced by the official `rehype-sanitize` re-export |
| 15 obsolete permanent skips (checkpointer, conversations, PKCE, pool concurrency, LLM config) | All reactivated: assertions realigned on current contracts (PKCE authorization URL, page-scoped `total_count`, reset-without-soft-delete, invocation-boundary metrics callbacks) — **the main integration phase now passes with zero skips** |

The counter-analysis stage works both ways: this cycle *discarded* false positives (the deployment path presumed broken from a read-only inspection; the dark-mode contrast defect) **and** corrected false negatives (skipped PostgreSQL tests reactivated into a full Windows campaign; ratchet-green debts re-counted at their absolute values).

## Open worksites — 7 moderate, 0 major, 0 minor

Published deliberately — a quality claim without its known gaps is marketing, not engineering. Each worksite in the [full report](./AUDIT_CODEBASE_2026-07-16_CONSOLIDE_V11.html) carries its evidence, closure criteria, effort estimate and a ready-to-run resolution prompt.

| # | Worksite | Level · Effort |
|---|---|---|
| AC-001 | RAG reindexation temporarily suspends user search globally (durability is done; read continuity on a stable generation during rebuild is not) | Moderate · E4 |
| AC-002 | Frontend coverage is shallow and concentrated (35.4% statements; 255 of 425 instrumented files at zero) | Moderate · E4 |
| AC-003 | Backend hotspots combine volume and complexity (347 functions CC≥15, max 89; 40 files ≥800 SLOC) | Moderate · E5 |
| AC-004 | 31 runtime import cycles remain tolerated by the baseline | Moderate · E4 |
| AC-005 | 91 MyPy exemption pairs bound the typing guarantee | Moderate · E3 |
| AC-006 | Frontend complexity concentrated in 59 functions (max CC 74) | Moderate · E4 |
| AC-007 | 34 strict-React deviations remain baselined | Moderate · E3 |

**Recommended sequencing** (risk × dependencies × effort): 0–30 days — AC-002, AC-007, start AC-005; 30–90 days — AC-001, AC-006, first AC-003 batches; 90–180 days — AC-003 program, AC-004, MyPy continuation. Continuous: load campaigns, Firefox/WebKit/assistive-technology matrix, DORA series, provider tests on a controlled environment.

## Delivery performance (DORA)

| Metric | Measured | Level |
|---|---|---|
| Deployment frequency | 149 releases in 10 months | Elite |
| Lead time for changes | Under one day (tag-to-production same day) | Elite |
| Change failure rate / MTTR | Not instrumented — no historical series exists, so the audit does not score these as if observed | Open worksite |

## Reproduce it yourself

```bash
# Static gates and ratchets
task lint
cd apps/web && pnpm exec tsc --noEmit --incremental false

# Backend suites (the exhaustive suite is deliberately excluded by repo policy)
task test:backend:unit:fast
task test:backend:agents
task test:backend:integration     # PostgreSQL/Redis via Testcontainers — works on Windows

# Migrations: empty-DB replay, single head, downgrade/upgrade, drift check
task db:migrate:replay-check

# Frontend
cd apps/web && pnpm test:coverage

# E2E (hermetic, official Playwright image, standalone production build)
# see apps/web/e2e/README.md

# Delivery + production images
task test:deploy
task build

# Structural measurements (committed instruments)
apps/api/.venv/Scripts/python scripts/audit/measure_sloc.py apps/api/src
apps/api/.venv/Scripts/python scripts/audit/measure_cc.py --check-ratchet
apps/api/.venv/Scripts/python scripts/audit/measure_coupling.py --check-cycles
apps/api/.venv/Scripts/python scripts/audit/measure_mypy_debt.py --check
```

**Interpretation caution** (from the report's own annexes): results describe the audited snapshot, not a permanent property of all versions; "conformant" means "conformant to the executed control", not universal conformity to an entire standard; no real LLM/OAuth/email providers were called; no sustained load test was run; browsers were Chromium-only; coverage measures execution, not assertion quality; and the total absence of security findings means nothing about security, which is out of scope by design.

## Audit history

| Date | Framework | Score | Register |
|---|---|---|---|
| **2026-07-16** | **V11 — normalized 24-area grid, revised method** (report: [HTML](./AUDIT_CODEBASE_2026-07-16_CONSOLIDE_V11.html)) | **8.3/10** (199/240) | **7 moderate worksites — 0 major, 0 minor**; all previously-open majors/minors closed with executed proof |
| 2026-07-10 | Historical grid (20 areas + 4 exploratory) | 8.5/10 like-for-like · 8.4/10 on 24 areas | 12 open items — 6 of the previous 16 closed, 2 advanced |
| 2026-07-09 | Historical grid | 8.4/10 like-for-like · 8.3/10 on 24 areas | 16 open items, prioritized in 4 waves |
| 2026-07-07 | Historical grid (20 areas) | 8.0/10 | 17 items → 10 resolved within 48h |

Scores across framework revisions are not directly comparable; within a framework they can go down as well as up — that is the point of measuring. Audits recur after each major remediation wave.

---

*An internal audit aligned on industrial referentials (ISO/IEC 25010:2023, 25040:2024, 42010:2022, 29119-2:2021, 5055:2021; WCAG 2.2 AA as a control grid), conducted with AI tooling under human direction, every conclusion anchored in executed evidence that this repository lets you check. It is neither an accredited certification nor a guarantee of absence of defects. Security is deliberately out of scope here and covered by a separate assessment (see [SECURITY.md](../../SECURITY.md)).*
