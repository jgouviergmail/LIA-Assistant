# LIA — Public Technical Audit Report

> **Latest assessment: 7.8/10** (186.5/240) across **24 normalized areas** — the **V14 revision**, a counter-review of the V14 report of the same day (2026-10-22): every finding and every score confronted with the current code, fresh executions and the V13 register, and amended where the evidence required it. V14 had scored 8.0/10 (192/240).
> Full standalone reports (French): [revision](./AUDIT_CODEBASE_2026-10-22_CONSOLIDE_V14-revision.html) · [V14](./AUDIT_CODEBASE_2026-10-22_CONSOLIDE_V14.html) · Method: evidence-based with systematic counter-proofs, every score backed by cited sources and executed checks · **Security is explicitly and entirely out of scope** (covered separately — see [SECURITY.md](../../SECURITY.md)).
>
> ⚖️ **Quality decision: general validation not granted.** Four major findings are open — three of them for 81 days, across 86 releases; the backend coverage gate has no margin left; and the revision did not replay the browser suite under its own control. The report is published as a technical assessment with its reservations, not as a conformity attestation or a production go-ahead.

LIA's engineering claims are public, so their verification should be too. This report is the summary backing for every quality figure shown on the [landing page](https://lia.jeyswork.com/), the [/story field report](https://lia.jeyswork.com/story) and the README; the complete, self-contained reports (scorecard, evidence register, counter-analysis, worksite prompts, annexes) are versioned next to this file. It is updated after each audit cycle — including the findings we have not fixed yet.

---

## Why we publish this

Most projects claim quality; few make the claim falsifiable. This repository is open source, its audit reports are published with their open worksites, and the sections below include the exact commands to reproduce the core measurements yourself. The score matters less than the loop that produces it: **audit → prioritized remediation → re-audit**, with every fix landing as a versioned release backed by an Architecture Decision Record.

The method is as auditable as the code: the full audit protocol — scope, referentials, evidence requirements, scoring discipline, publication pipeline — is versioned in [AUDIT_PROTOCOL.md](./AUDIT_PROTOCOL.md), and the structural metrics come from committed measurement scripts ([`scripts/audit/`](../../scripts/audit/)).

A published figure that stops matching the latest cycle is itself a finding. The cycles before V14 (V12 and V13, below) were produced and versioned but never carried to the public surfaces, which kept showing V11's 8.3 — including through V13's 7.3. The same rule now applies to V14 itself: its counter-review lowered the score, and the public surfaces carry the revised figure.

## Scope, referentials and method (V14 and its revision)

- **Object.** V14 assessed the working tree visible at its cut-off (2026-10-22, closing capture 08:19 UTC): commit `89d10bc97` plus the uncommitted v3.4.0 release preparation — 12,480 unique text paths across `apps/api`, `apps/web`, `infrastructure`, `scripts`, `docs`, Taskfile, manifests, lockfiles, Dockerfiles, Compose and CI workflows. The revision re-read the same day's tree at two fingerprinted snapshots (08:53 and 09:28 UTC, about 13,280 files each, the concurrent release work included) and re-verified every source V14 cited: 86 of 89 were unchanged, the three that changed being those of findings closed since. **Absolute exclusion:** any security analysis — vulnerabilities, secrets, authn/authz, cryptography, hardening, SAST/DAST, vulnerable dependencies, threat modeling, intrusion testing. No score, finding or prompt takes security into account.
- **Referentials.** Product quality: **ISO/IEC 25010:2023** and **ISO/IEC 25040:2024** (security characteristic neutralized). Architecture: **ISO/IEC/IEEE 42010:2022**. Life-cycle reading: **ISO/IEC/IEEE 12207:2026**. Test processes: **ISO/IEC/IEEE 29119-2:2021**; automated structural quality: **ISO/IEC 5055:2021**. Interaction: **WCAG 2.2 level AA** as the accessibility control grid — no claim of full conformity is made. The audit is an internal assessment aligned on industrial referentials; it is **not** an accredited certification, a guarantee of absence of defects, or a WCAG conformity attestation.
- **Process.** V14: inventory → static gates (Ruff, Black, MyPy strict, ESLint, non-incremental TypeScript, i18n parity, documentation drift, cycles, complexity, size, baselined debts) → backend suites in three scheduling modes → integration and migration replay on disposable PostgreSQL/Redis → production Docker builds → hermetic Playwright journeys on an isolated production server, native media prerequisites included → targeted probes → counter-analysis. The revision then ran its own fresh executions — 45,852 backend unit tests and 13,919 frontend tests, frontend coverage at 87.8 %, static gates, ratchet baselines, Git series — and new instruments (Ruff's async rules, template values against code defaults, a documentation language census, panel-to-producer resolution).
- **Qualification rule.** No finding rests solely on a comment, a green baseline, a skipped test, an exit code or a historical observation. A dedicated counter-analysis stage documents discarded false positives and corrected false negatives; a test broken before its oracle is never counted as a pass or a product defect.
- **Scoring.** Each area is the sum of five axes scored 0–2 in half points — **C**ontract/structure, **I**mplementation, fresh **V**erification, **G**uard/prevention, **E**xploitation/evolution — so every area score answers the same five questions. The global score is the plain arithmetic mean of the 24 areas: 186.5 ÷ 24 = **7.8/10**. Finding levels: *major* (an essential contract or operational chain is incorrect), *moderate* (a bounded defect or significant debt), *minor* (a limited gap with no demonstrated business failure). Priorities: P1 before a general qualification, P2 planned risk reduction, P3 opportunistic. Effort E1 (< half a day) to E5 (multi-batch programme); horizons H0 (within a week), H1 (two to four weeks), H2 (the quarter).

## Scorecard — 24 normalized areas (revision of 2026-10-22)

| # | Area | Score | V14 | Evidence highlights |
|---|------|-------|-----|---------------------|
| 1 | Infrastructure | 8.5 | 8.5 | Explicit containerized topology, base images pinned by version and digest, resource limits and health probes declared, documented restore procedure; a timed restore and the ARM image not executed; the web Docker context does not exclude capture bundles (AC-027) |
| 2 | Data & persistence | 7.0 | 7.5 | Linear single-head migration chain, typed SQLAlchemy 2 ORM, partial-index upserts on literal predicates, JSONB guards; the fencing of an ordinary RAG upload is still incomplete (AC-002), PostgreSQL bounds neither lock waits nor idle transactions despite a production lock-up of that class documented in the repository (AC-028), and the proactive-discussion execution tables have no retention or growth gauge (AC-034) |
| 3 | Configuration & dependencies | 8.5 | 9.0 | Modular settings, synchronized manifests and lockfiles, an orphan dependency removed, pinned versions; 50 environment-template values differ from the code's defaults, nine of them inverted switches, and only their presence is checked (AC-036) |
| 4 | Architecture | 7.5 | 7.5 | 59 domains, one lifespan orchestration point, Pipeline, ReAct and direct aggregations kept apart; 22 reciprocal runtime pairs concentrated on `users` and `agents`, with local imports still used as a workaround (AC-011) |
| 5 | Application design | 8.0 | 8.5 | Typed tool contracts, a taxonomy of errors, a declared turn reset, one door for post-commit notices; the notification dispatch — « at least one channel », an ephemeral SSE included, a failure returned as a value — is reused by five callers that write a durable state (AC-003) |
| 6 | Genericity | 9.0 | 9.0 | Generic repository, LLM factories, domain and draft registries validated at import |
| 7 | Extensibility | 9.0 | 9.0 | Tool and agent creation guides, declarative registries, version surfaces declared once and checked in CI; reciprocal coupling slows transverse changes (AC-011) |
| 8 | Implementation | 7.5 | 7.5 | Homogeneous async and UTC idioms, modern Pydantic 2 and SQLAlchemy 2 APIs, no unreferenced asyncio task; very heavy complexity tails (AC-010) and 16 blocking disk operations or active waits inside async functions (AC-035) |
| 9 | Maintainability | 7.0 | 7.0 | Size, complexity, coupling and typing ratchets active and trending down since V13 (functions at CC ≥ 15: 342 → 263, maximum 87 → 77); absolute debt still high (AC-010, AC-013) |
| 10 | Quality tooling | 7.5 | 8.0 | Ruff, Black, strict MyPy, ESLint and non-incremental `tsc` green, backend and frontend ratchets; blind spots: 859 MyPy diagnostics masked, six exemption codes that no longer fire (AC-012), untyped backend tests, no async lint rules, no panel-to-producer guard, no template value check |
| 11 | Patterns & practices | 7.5 | 8.0 | Precise written rules and many AST guards, not applied everywhere: ownerless locks set then deleted unconditionally (reindex and OAuth refresh — AC-005, AC-029), durable states written without an explicit result (AC-003), local imports |
| 12 | Robustness | 6.5 | 7.0 | Circuit breakers and targeted HTTP and SQL timeouts; shutdown does not join cancelled tasks (AC-007), no systemic PostgreSQL wait bound (AC-028), temporary Hue clients left open (AC-008) |
| 13 | Reliability | 6.5 | 7.0 | Transactions, recovery and checkpoints widely tested, scheduler leadership owner-conditioned, the October Workboard lock-up fixed and guarded; ownership and delivery counter-examples persist and widen — five delivery sites including the incident alert (AC-003), the OAuth refresh lock (AC-029), V13 majors open for 81 days |
| 14 | Performance | 8.0 | 8.0 | Differential graph input, linear flatteners under guard, intra- and inter-process coalescing; no load or production latency measured during the audit |
| 15 | Optimization | 8.5 | 8.5 | Per-source caches, inter-process coalescing, reserved spend budgets; a semantically refused rule compilation is paid again on every tick (AC-023) |
| 16 | Scalability | 8.0 | 8.0 | Connection budget computed for every worker with a fast failure, Prometheus multiprocess mode, token-owned Redis claims; multi-worker correctness of RAG leases and the reindex lock still open (AC-002, AC-005); no capacity figure measured |
| 17 | Operability & observability | 6.0 | 7.0 | 627 metrics (93.8 % referenced), 32 dashboards, 86 recording rules and 32 validated alerts, 60 runbooks; the alerting chain stays inconsistent — specialized routes shadowed in the default e-mail template too (AC-004), four panels with no producer (AC-006, reopened), an incident alert marked notified without a delivery (AC-003) |
| 18 | CI/CD & delivery | 8.0 | 8.5 | Thin CI calling the Taskfile tasks, controlled parity, hermetic delivery and installation; no job or test timeouts (AC-033), backend coverage margin down to 0.66 point (AC-030), audit register not yet tooled (AC-031) |
| 19 | Tests & assurance | 7.5 | 7.5 | Fresh green executions, 87.8 % frontend coverage, the latest complete browser run observed green, regression tests for the two fixed usage defects; assurance weakened by the eroded backend margin, missing timeouts and two tests that never ran (AC-030, AC-033, AC-037) |
| 20 | Documentation | 8.0 | 9.0 | 359 ADRs, living links, cited paths and facts controlled, generated AGENTS mirror, living maps; values restated outside the controlled patterns drift — wrong test thresholds in the testing guide (AC-032), the language rule unapplied to a third of the corpus (AC-039), an oversized governance document (AC-038), a discontinuous audit register (AC-031) |
| 21 | Portability | 8.5 | 8.5 | Windows for development, containerized Linux, multi-arch builds planned, delivery and installation tested hermetically; ARM, native mobile and a restore not executed; the canonical coverage command is not reproducible on Windows (AC-033) |
| 22 | Compatibility | 8.5 | 8.5 | `/v1` API, shared SSE vocabulary checked by a symmetry test, IMAP identifiers normalized, recent frameworks pinned; SSE payloads cast without validation on the client (AC-037) |
| 23 | Functional suitability | 7.5 | 8.0 | Very broad functional surface and complete registries, the two V14 usage defects fixed; a user-visible claim can be wrong — a peer message announced « delivered » to its sender without a proven delivery (AC-003) |
| 24 | Usability & accessibility | 8.0 | 7.0 | Six languages at strict parity, translated labels, jsx-a11y ratchet at zero, axe journeys; the SMS focus and the settings search defects of V14 fixed and tested; no formal campaign with assistive technologies |

Eleven areas went down — nine by half a point, documentation and observability by a full point — and usability went up by one.

## The proof is the loop, not the snapshot

Each cycle starts by re-verifying the previous register in the code. The revision publishes what V14 had left out: the status of every V13 finding, and its age.

| Finding | V13 (2026-08-02) | V14 (2026-10-22) | Revision (2026-10-22) |
|---|---|---|---|
| AC-001 · Scheduler leadership | Open, major | Closed, not published as such | **Closed** — renewal and release conditioned on the owner |
| AC-002 · Fencing of RAG jobs | Open, major | Open, major | Open, major — 81 days |
| AC-003 · Delivery inferred from the absence of an exception | Open, major | Open, two sites | Open, **five sites** — 81 days |
| AC-004 · Alertmanager composition and routing | Open, major | Open, major | Open, **widened** to the default e-mail template — 81 days |
| AC-005 · Reindex lock without an owner | Open | Open, moderate | Open — 81 days |
| AC-006 · Dashboard panels without a producer | Open | Absent, no status | **Reopened** — four panels |
| AC-007 · Cancelled tasks not drained | Open | Open, moderate | Open — 81 days |
| AC-008 · Hue client lifecycle | Open | Open, moderate | Open, **lowered to minor** |
| AC-009 · Non-deterministic xdist gate | Open | Absent, no status | **Closed** — fresh eight-worker run |
| AC-010 · Backend hotspots | Open | Open | Open, improving |
| AC-011 · Reciprocal domain coupling | Open | Open | Open, refined |
| AC-012 · MyPy debt | Open | Open | Open, an immediate gain identified |
| AC-013 · React debt | Open | Open | Open, improving |
| AC-014 · Coverage presented per file (V13) / excluded primitives (V14) | Open | Identifier reused for another subject | V13 item closed; V14 item open, lowered to minor |
| AC-015 · Proof lane for voice and Web Audio | Open | Resolved in fact | **Closed** |
| AC-016 · Dialog name hard-coded in French | Open | Resolved in fact | **Closed** |
| AC-017 · Non-immutable rebuild | Open | Absent, no status | **Partially closed** — images pinned by digest |
| AC-018 · CI guards liable to drift | Open | Absent, no status | **Closed** |
| AC-019 · Documentary freshness | Open | Absent, no status | **Partially closed** — residue carried by AC-032 |
| AC-020 · Orphaned SlowAPI dependency | Open | Absent, no status | **Closed** |
| AC-021 · E2E oracles behind decided interactions | — | Open, moderate | **Presumed closed** — a controlled replay must confirm it |
| AC-023 · Refused rule compilation repeated | — | Open, moderate | Open |
| AC-024 · Focus after a grouped SMS deletion | — | Open, moderate | **Closed** — unit tests replayed |
| AC-025 · Natural vocabulary in the settings search | — | Open, minor | **Closed** — multilingual matcher tests |
| AC-027 · Capture bundles in the Docker context | — | Open, minor | Open |
| AC-028 to AC-039 | — | — | **New** |

The counter-analysis works both ways: the revision confirmed V14's discarded false positives, kept its real defects, and found three things V14 had not said — that the majors do not close (three of them classed « before the next sensitive deployment » in August), that two defects are wider than described, and that significant risks were missing (database wait bounds, the OAuth refresh lock, the coverage margin).

## Open worksites — 4 major, 11 moderate, 11 minor

Published deliberately — a quality claim without its known gaps is marketing, not engineering. Each worksite in the [revision report](./AUDIT_CODEBASE_2026-10-22_CONSOLIDE_V14-revision.html) carries its verified facts, impact, root cause, counter-verification, recommendation and a ready-to-run resolution prompt.

| # | Worksite | Level · Priority · Effort · Horizon |
|---|---|---|
| AC-002 | Fence the processing of an uploaded RAG document end to end | Major · P1 · E4 · H1 |
| AC-003 | Infer no « delivered » state from the absence of an exception, on all five callers | Major · P1 · E3 · H0 |
| AC-004 | Compose Alertmanager from the configured channels and make the specialized routes reachable | Major · P1 · E3 · H1 |
| AC-028 | Bound lock waits and idle transactions on the PostgreSQL side | Major · P1 · E2 · H0 |
| AC-005 | Give the global reindex lock an owner | Moderate · P1 · E3 · H1 |
| AC-007 | Wait for cancelled tasks to finish before closing their resources | Moderate · P1 · E2 · H0 |
| AC-029 | Give the OAuth refresh lock an owner and a lease covering its critical section | Moderate · P1 · E2 · H0 |
| AC-030 | Stop the erosion of backend coverage (0.66-point margin) | Moderate · P1 · E3 · H1 |
| AC-031 | Close the improvement loop: a continuous register, finding ages and deadlines | Moderate · P1 · E1 · H0 |
| AC-006 | Resolve every panel to a real producer and decide on the dormant alert rules | Moderate · P2 · E2 · H1 |
| AC-010 | Reduce the absolute complexity of the central orchestration points | Moderate · P2 · E5 · H2 |
| AC-011 | Undo the reciprocal dependencies of the `users` and `agents` hubs | Moderate · P2 · E4 · H2 |
| AC-012 | Work off the neutralized MyPy diagnostics, starting with the dead exemptions | Moderate · P2 · E4 · H0 then H2 |
| AC-013 | Reduce React Hooks debt and complex components | Moderate · P2 · E4 · H2 |
| AC-023 | Bound the paid repetition of a semantically refused rule compilation | Moderate · P2 · E3 · H1 |
| AC-008 | Close the Hue clients created for a connection test | Minor · P2 · E1 · H0 |
| AC-014 | Bring the interface primitives that became behavioural back into coverage | Minor · P2 · E2 · H2 |
| AC-027 | Keep capture bundles out of the production Docker context | Minor · P2 · E1 · H0 |
| AC-032 | Realign the documentation of test thresholds and doctrines on their source | Minor · P2 · E1 · H1 |
| AC-033 | Make the test bench reliable: timeouts, a robust timing oracle, tests that actually run | Minor · P2 · E2 · H1 |
| AC-034 | Give the proactive-discussion execution tables a retention or a growth measure | Minor · P3 · E2 · H2 |
| AC-035 | Move blocking disk I/O out of async functions and tool the rule | Minor · P3 · E2 · H2 |
| AC-036 | Align the environment templates on the code's defaults or justify each gap | Minor · P3 · E2 · H2 |
| AC-037 | Make test code respect production contracts | Minor · P3 · E3 · H2 |
| AC-038 | Bring `CLAUDE.md` (and its `AGENTS.md` mirror) back to rules and pointers | Minor · P3 · E2 · H2 |
| AC-039 | Apply or amend the documentation language rule | Minor · P3 · E4 · H2 |

**Prioritized plan.**
- **H0 — within a week:** tool the findings register (AC-031) as the prerequisite for tracking the rest; measure then set the PostgreSQL bounds (AC-028); one durable delivery door with its guard for the five sites (AC-003); the OAuth refresh lock on the owned-claim primitive (AC-029) and a join after cancellation (AC-007); remove the six dead MyPy codes and twelve unused ignores (AC-012, first step); exclude capture bundles (AC-027) and close the Hue clients (AC-008). Projected, if every closure is proven: 188.5/240, 7.9.
- **H1 — two to four weeks:** close the remaining V13 defects and restore assurance — RAG upload fencing and the reindex lock (AC-002, AC-005), Alertmanager by fragments with a routing matrix (AC-004), a diff coverage gate with tests for the new domains (AC-030), the panel-to-producer guard (AC-006), test and job timeouts (AC-033), the threshold documentation (AC-032), a negative cache for refused compilations (AC-023), and a controlled browser replay to close AC-021. Projected: 193/240, 8.0.
- **H2 — the quarter:** structural debt in measured batches — one hotspot per batch (AC-010), the administrative read model out of `users` then the `agents` pairs (AC-011), typing and test contracts (AC-012, AC-013, AC-014, AC-037), retention or gauges (AC-034), async rules (AC-035), template parity (AC-036), documentary governance (AC-038, AC-039).

## Delivery performance (DORA)

| Metric | Measured | Reservation |
|---|---|---|
| Release frequency (deployment proxy) | 86 release tags after the V13 capture (87 since 2026-08-02); 19 over the last 30 days, 6 over the last 14 | A release is not a deployment; deployments are not traced in Git |
| Lead time, commit → tag | Median 1.7 h · p90 20.2 h · maximum 8.3 days (329 commits) | Under-estimates the real delay: work stays uncommitted for days before its commit |
| Change failure rate | Not observable | No production incident register is read by the audit |
| Time to restore | Not observable | The October incident is documented in a test, without exploitable detection and recovery timestamps |

## Reproduce it yourself

```bash
# From the repository root, environment installed from the lockfiles
task lint:backend
task lint:frontend
task lint:i18n
task lint:hygiene
task lint:lockfiles
task lint:ci-parity
task lint:docs
task lint:docs:preview
task test:markers
task test:backend:unit:fast
task test:backend:unit:coverage
task test:backend:agents
task test:frontend:coverage
task test:deploy
task test:install:hermetic
task test:alerts

# DISPOSABLE PostgreSQL/Redis explicitly designated — never an application database
task test:backend:integration
task db:migrate:replay-check

# Additional combination, from apps/api, same selection in both modes
.venv/Scripts/pytest tests/unit tests/agents --no-cov -m "not integration and not slow and not e2e and not benchmark and not multiprocess" -n 8 --dist loadscope
.venv/Scripts/pytest tests/unit tests/agents --no-cov -m "not integration and not slow and not e2e and not benchmark and not multiprocess"

# Frontend runtime and builds in Docker only; E2E on an isolated production server
# with mocked APIs — see apps/web/e2e/README.md
# Never task test:backend:exhaustive; no deploy:prod or demo deployment.

# Structural measurements (committed instruments)
apps/api/.venv/Scripts/python scripts/audit/measure_sloc.py apps/api/src
apps/api/.venv/Scripts/python scripts/audit/measure_cc.py --check-ratchet
apps/api/.venv/Scripts/python scripts/audit/measure_coupling.py --check-cycles
apps/api/.venv/Scripts/python scripts/audit/measure_mypy_debt.py --check
apps/api/.venv/Scripts/python scripts/audit/measure_metric_coverage.py
```

**Interpretation caution** (from the reports' own annexes): results describe dated snapshots — uncommitted release work included — not a permanent property of every version; "conformant" means conformant to the executed control, not universal conformity to an entire standard; no sustained multi-user load, memory stress or production latency series was run; no full disaster recovery with a timed restore; ARM64 builds, native iOS/Android apps, physical devices and audible audio were not executed; no real LLM, voice, SaaS or connector provider was called; full WCAG conformity is not established; DORA series are proxies read from Git; coverage measures execution, not oracle quality; and the total absence of security findings means nothing about security, which is out of scope by design.

## Audit history

| Date | Framework | Score | Register |
|---|---|---|---|
| **2026-10-22** | **V14 revision — a counter-review of V14 on the same grid** (report: [HTML](./AUDIT_CODEBASE_2026-10-22_CONSOLIDE_V14-revision.html)) | **7.8/10** (186.5/240) | **26 open findings — 4 major, 11 moderate, 11 minor**, 12 of them new (AC-028 to AC-039); closures proven for 3 V14 findings (1 presumed) and 9 V13 findings (2 partial) |
| 2026-10-22 | V14 — 24-area grid, each area the sum of five 0–2 axes (report: [HTML](./AUDIT_CODEBASE_2026-10-22_CONSOLIDE_V14.html)) | 8.0/10 (192/240) | 16 worksites — 3 major, 11 moderate, 2 minor; V13's scheduler-leadership major closed, its three other majors narrowed and still open |
| 2026-08-02 | V11 — normalized 24-area grid (report: [HTML](./AUDIT_CODEBASE_2026-08-02_CONSOLIDE_V13.html)) | 7.3/10 (174.5/240) | 20 worksites — 4 major, 12 moderate, 4 minor |
| 2026-07-24 | V11 — normalized 24-area grid (report: [HTML](./AUDIT_CODEBASE_2026-07-24_CONSOLIDE_V12.html)) | 8.3/10 (199/240) | 7 moderate worksites — 0 major, 0 minor |
| 2026-07-16 | V11 — normalized 24-area grid, revised method (report: [HTML](./AUDIT_CODEBASE_2026-07-16_CONSOLIDE_V11.html)) | 8.3/10 (199/240) | 7 moderate worksites — 0 major, 0 minor; all previously-open majors/minors closed with executed proof |
| 2026-07-10 | Historical grid (20 areas + 4 exploratory) | 8.5/10 like-for-like · 8.4/10 on 24 areas | 12 open items — 6 of the previous 16 closed, 2 advanced |
| 2026-07-09 | Historical grid | 8.4/10 like-for-like · 8.3/10 on 24 areas | 16 open items, prioritized in 4 waves |
| 2026-07-07 | Historical grid (20 areas) | 8.0/10 | 17 items → 10 resolved within 48h |

Scores across framework revisions are not directly comparable; within a framework they can go down as well as up — that is the point of measuring, and the V14 revision is that point made twice on the same day. V14 keeps V11's 24 areas and anchors and builds each area score from five explicit axes; its revision keeps the grid and re-scores each axis on fresh evidence. Audits recur after each major remediation wave.

---

*An internal audit aligned on industrial referentials (ISO/IEC 25010:2023, 25040:2024, 5055:2021; ISO/IEC/IEEE 42010:2022, 12207:2026, 29119-2:2021; WCAG 2.2 AA as a control grid), conducted with AI tooling under human direction, every conclusion anchored in executed evidence that this repository lets you check. It is neither an accredited certification nor a guarantee of absence of defects. Security is deliberately out of scope here and covered by a separate assessment (see [SECURITY.md](../../SECURITY.md)).*
