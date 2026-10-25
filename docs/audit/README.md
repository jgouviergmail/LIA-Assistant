# LIA — Public Technical Audit Report

> **Latest assessment: 7.9/10** (190/240) across **24 normalized areas** — **V15** (2026-10-25), an audit of the **committed** state of LIA 3.6.0 (commit `3909d87c5`), every score backed by cited sources and checks executed on an isolated export of that commit. The previous cycle, the V14 revision, had scored 7.8/10 (186.5/240).
> Full standalone report (French): [V15](./AUDIT_CODEBASE_2026-10-25_CONSOLIDE_V15.html) · previous: [V14 revision](./AUDIT_CODEBASE_2026-10-22_CONSOLIDE_V14-revision.html) · Method: evidence-based with systematic counter-proofs · **Security is explicitly and entirely out of scope** (covered separately — see [SECURITY.md](../../SECURITY.md)).
>
> ⚖️ **Quality decision: a controlled level, residual debt identified — not an unreserved validation.** One major and six moderate findings are open, three of them P1: the ownership of an uploaded RAG document's processing across a takeover, the identity of each acquisition of the reindex lock, and the total duration of an OAuth refresh against its lease. They must be treated before resumptions, concurrent acquisitions and duration bounds count as fully qualified. The report is published as a technical assessment with its reservations, not as a conformity attestation or a production go-ahead.

LIA's engineering claims are public, so their verification should be too. This report is the summary backing for every quality figure shown on the [landing page](https://lia.jeyswork.com/), the [/story field report](https://lia.jeyswork.com/story) and the README; the complete, self-contained reports (scorecard, evidence register, counter-analysis, worksite prompts, annexes) are versioned next to this file. It is updated after each audit cycle — including the findings we have not fixed yet.

---

## Why we publish this

Most projects claim quality; few make the claim falsifiable. This repository is open source, its audit reports are published with their open worksites, and the sections below include the exact commands to reproduce the core measurements yourself. The score matters less than the loop that produces it: **audit → prioritized remediation → re-audit**, with every fix landing as a versioned release backed by an Architecture Decision Record.

The method is as auditable as the code: the full audit protocol — scope, referentials, evidence requirements, scoring discipline, publication pipeline — is versioned in [AUDIT_PROTOCOL.md](./AUDIT_PROTOCOL.md), and the structural metrics come from committed measurement scripts ([`scripts/audit/`](../../scripts/audit/)).

A published figure that stops matching the latest cycle is itself a finding. The cycles before V14 (V12 and V13, below) were produced and versioned but never carried to the public surfaces, which kept showing V11's 8.3 — including through V13's 7.3. Since then every cycle reaches the public surfaces, whichever way its score moves: the V14 revision lowered it, V15 raises it.

## Scope, referentials and method (V15)

- **Object.** V15 audits one **commit**, not a working tree: `3909d87c5` (LIA 3.6.0, 2026-10-24), frozen by Git reads and exported outside the workspace — 13,419 committed files verified against their blobs, line-ending conversions recorded. Uncommitted work, even staged, is excluded; earlier backend results were reused only after a byte-for-byte reconciliation with the commit. The campaign ran on 2026-10-24 and 2026-10-25. **Absolute exclusion:** any security analysis — vulnerabilities, secrets, authn/authz, cryptography, hardening, SAST/DAST, vulnerable dependencies, threat modeling, intrusion testing. Components carrying those names are judged for their function, structure and reliability only.
- **Referentials.** Product quality: **ISO/IEC 25010:2023** and **ISO/IEC 25040:2024** (security characteristic neutralized). Automated structural quality: **ISO/IEC 5055:2021**. Architecture: **ISO/IEC/IEEE 42010:2022**. Test processes: **ISO/IEC/IEEE 29119-2:2021**. Life-cycle reading: **ISO/IEC/IEEE 12207:2026**. Interaction: **WCAG 2.2 level AA** as the accessibility control grid. Technical contracts read at their source: PostgreSQL 16 SQLSTATE and `NOWAIT` semantics, HTTPX timeouts, Playwright's clock, Python 3.14 subprocess rules. The audit is an internal assessment aligned on industrial referentials; it is **not** an accredited certification, a guarantee of absence of defects, or a WCAG conformity attestation.
- **Process.** Inventory → static gates on the commit (35 controls: Ruff, Black, strict MyPy, ESLint, non-incremental TypeScript, cycles, complexity, size, baselined debts) and the six canonical documentation checks on the commit's exact index → backend suites in every scheduling mode (46,487 unit tests with coverage, 5,344 integration tests, 1,102 agent tests, xdist and sequential combined runs) → migration replay on disposable PostgreSQL (272 revisions, one head) and a dump/restore round trip → 14,114 frontend tests with coverage → 693 browser journeys per engine on Chromium, Firefox and WebKit against an isolated production server with mocked APIs → Prometheus rule tests, a 14-variant Alertmanager matrix, an exact production build of the API image → targeted probes (a stale RAG worker, a slow-drip HTTP response, the causes of PostgreSQL bound errors) → counter-analysis.
- **Qualification rule.** No finding rests solely on a comment, a green baseline, a skipped test, an exit code or a historical observation. A bench limit is not a product defect: the combined backend modes ended on 27 failures caused by the Windows bench (argument decoding, Git decisions, shell paths), requalified separately and never added back into a green total.
- **Scoring.** Each area is set by explicit judgment, in half points, on one published ordinal scale — 9.5–10 exemplary practice; 8.5–9.0 mastered and industrialized; 7.0–8.0 controlled and operational, substantial but bounded debt; 5.5–6.5 fragile; ≤ 5.0 insufficient — from its positive controls, gaps, effects and proof limits, with at least three source proofs per area and no hidden formula turning counters into scores. The global score is the plain mean of the 24 areas: 190 ÷ 24 = **7.9/10**. Finding levels: *major* (a significant risk to a result or to persistence), *moderate* (a bounded reliability or delivery defect, or substantial debt), *minor* (a local inconsistency or a non-blocking improvement). Priorities: P1 first cycle, P2 after the P1s, P3 planned maintenance; no P0. Effort E1 (< half a day) to E5 (beyond two weeks); regression radius R1 (an isolated test or text) to R4 (cross-domain contracts or persistence). The register maps P1 to the H1 horizon (four weeks) and P2/P3 to H2 (the quarter).

## Scorecard — 24 normalized areas (V15, 2026-10-25)

| # | Area | Score | Rev. | Evidence highlights |
|---|------|-------|------|---------------------|
| 1 | Infrastructure | 8.5 | 8.5 | Explicit production topology, budgets and entry points; the exact API build executed, not only read; backups kept apart from the directory a deploy replaces; the native web build did not finish within the bench's envelope |
| 2 | Data & persistence | 7.5 | 7.0 | 272 migrations on one head, full upgrade plus last-revision round trip and metadata diff on a disposable base, an explicit `ondelete` on all 170 foreign keys; the transitions of an uploaded RAG document are not all tied to the attempt that owns them (AC-002) |
| 3 | Configuration & dependencies | 8.5 | 8.5 | Builds consume locked dependencies, settings composed by domain, effective capabilities derived through shared doors; the OAuth refresh lease rests on a duration the code does not bound (AC-029) |
| 4 | Architecture | 7.5 | 7.5 | 59 domain contexts mapped, one lifespan, registries and a differential turn state give the orchestration observable boundaries; 397 runtime edges, 22 reciprocal pairs, one strongly connected component of 53 domains (AC-010, AC-011) |
| 5 | Application design | 8.5 | 8.0 | Shared contracts for reasoning intent, effective capabilities, tool results and the stop decision; abandoned calls closed structurally; an owned lease must hold on every exit, errors and resumptions included |
| 6 | Genericity | 8.5 | 9.0 | Generic repository, filterable catalogues, composed configuration and completeness checks; the reindex lock is a specialized door that does not use the owned-claim primitive yet (AC-005) |
| 7 | Extensibility | 8.5 | 9.0 | Extensions go through declarations and completeness guards; a new capability must reach every consumer — the offline film check fails on two keys added to the catalogue (AC-043) |
| 8 | Implementation | 8.0 | 7.5 | A syntactic census of Python and TypeScript confirms the absence of the idiom families the guards forbid; 167 functions above 100 logical lines, 37 above 200 (AC-010, AC-012, AC-013) |
| 9 | Maintainability | 7.0 | 7.0 | Size, complexity and typing ratchets block regressions; 42 logic files above 600 logical lines, 10 above 1,000, 260 Python functions at CC ≥ 15, oversized central instructions (AC-010, AC-038) |
| 10 | Quality tooling | 8.0 | 7.5 | Ruff, Black, MyPy, TypeScript, ESLint and the cross-cutting guards run, the same Taskfile contract feeds CI; 76 tolerated MyPy module/code pairs (824 diagnostics without them), 119 double assertions frozen, four E2E oracles to correct (AC-012, AC-045 to AC-048) |
| 11 | Patterns & practices | 8.0 | 7.5 | Short sessions, task ownership, durable delivery and serializable state each have a shared door and tests; the RAG upload and the global reindex lock remain identified exceptions (AC-002, AC-005) |
| 12 | Robustness | 7.5 | 6.5 | Real server-side bounds tested, client timeouts, shutdown paths closing their resources; a response delivered in small fragments outlives the computed worst case and the OAuth lease (AC-029), and the bound metric conflates three causes (AC-041) |
| 13 | Reliability | 7.5 | 6.5 | Atomic acquisitions, conditional writes across many jobs, a notification declared durable only once a durable channel took it; a stale upload worker can still finish or reschedule a document another took over, and successive reindex acquisitions are not told apart (AC-002, AC-005, AC-029) |
| 14 | Performance | 7.5 | 8.0 | Time to first token, stream duration, streamed transfers and the differential turn state instrumented or structurally bounded; no loaded benchmark or real model call measures a production latency |
| 15 | Optimization | 8.5 | 8.5 | Caches with invalidation paths, prices read in memory, components loaded on demand; no bundle or first-paint measurement replaces a syntactic count |
| 16 | Scalability | 7.5 | 8.0 | A public connection profile of 128 burst connections for 195 usable, a floor of 28 persistent ones, a boot guard, explicit cross-worker invalidation; the RAG and reindex ownership reserves and the OAuth deadline concern resumptions and concurrent workers |
| 17 | Operability & observability | 8.0 | 6.0 | 32 dashboards, 634 metric definitions and 1,072 expressions inventoried, rules and their timing tested with the production image's Promtool, a 14-variant Alertmanager matrix, a synthetic alert e-mail accepted; one bound alert names three different causes as timeouts (AC-041) |
| 18 | CI/CD & delivery | 8.0 | 8.0 | CI orchestrates the local tasks, parity and version-surface guards green on the frozen export, 363 delivery-artefact tests passing; the native web build is incomplete on the bench and the offline film check has two editorial failures (AC-043) |
| 19 | Tests & assurance | 8.0 | 7.5 | Every mode's results, skips and warnings published, frontend thresholds unchanged, the backend floor held on the union of suites (87.5 % of lines); the chat's initial-position E2E check is not stable and four oracles need a targeted fix (AC-044 to AC-048) |
| 20 | Documentation | 8.0 | 8.0 | 847 Markdown documents, 65 runbooks and 362 ADRs walked by the instruments, the six canonical documentation checks green on the commit's exact index; one budget comment quotes 168 where the code computes 128 (AC-019) |
| 21 | Portability | 7.5 | 8.5 | Containerized Linux recipes, the Windows workstation and both shells' script tests kept apart, image versions and digests recorded; no ARM64 build, native mobile build or physical device executed, two POSIX modules outside the Windows collection |
| 22 | Compatibility | 8.0 | 8.5 | A cross-checked SSE contract, reasoning intent translated to each effective profile, cancellation and timeouts propagated over HTTP; three browser engines told apart, six Firefox video preconditions not acquired on the hermetic bench (AC-048, AC-049) |
| 23 | Functional suitability | 8.0 | 7.5 | Action, consultation and decision kept apart and exposed under deterministic contracts, allowed paths covered without a person or a real provider; job-cycle and total-duration gaps retained because they can alter a result (AC-002) |
| 24 | Usability & accessibility | 7.5 | 8.0 | Field and error association, image alternatives, language, reduced motion and axe journeys checked, six locales at strict parity; the last message is not fully at the bottom in a complete Chromium run, and the keyboard path of the selection actions fails under WebKit (AC-044, AC-049) |

Ten areas went up — observability by two points, robustness and reliability by one — seven went down, by half a point except portability (one point), and seven are unchanged. V15 scores each area by explicit judgment on a published ordinal scale where the revision summed five axes: the « Rev. » column is indicative across that change of method.

## The proof is the loop, not the snapshot

Each cycle starts from the previous register. Between the revision and V15, a remediation wave (2026-10-23) recorded fixes with their proofs; V15 then re-audited the commit that carried them. A fix recorded as *remediated* stays pending until an audit closes it explicitly: V15 observes several of them among its positive controls without issuing closure cards, so the register keeps them pending. The register itself is machine-readable: [`findings_register.json`](findings_register.json) holds every finding under a stable identifier and is verified against each report by `task lint:docs`.

| Finding | Revision (2026-10-22) | Wave (2026-10-23) | V15 (2026-10-25) |
|---|---|---|---|
| AC-002 · Fencing of RAG upload processing | Open, major | Not in the wave (owner decision) | Open, major, P1 — a stale worker's effects on a takeover reproduced |
| AC-003 · Delivery inferred from the absence of an exception | Open, five sites | Remediated — one durable-delivery verdict | Pending closure — durable delivery among V15's positive controls |
| AC-004 · Alertmanager composition and routing | Open, widened | Remediated — one template, optional blocks | Pending closure — the 14-variant matrix passes |
| AC-005 · Reindex lock without an owner | Open | Not in the wave (owner decision) | Open, P1, effort lowered to E2 |
| AC-006 · Panels without a producer | Reopened | Remediated — reverse guard | Pending closure |
| AC-007 · Cancelled tasks not drained | Open | Remediated — join after cancellation | Pending closure — shutdown paths observed closing their resources |
| AC-008 · Hue client lifecycle | Open, minor | Remediated | Pending closure |
| AC-010 · Backend hotspots | Open | Open | Open |
| AC-011 · Reciprocal domain coupling | Open | Open | Open |
| AC-012 · MyPy debt | Open | Dead exemptions removed | Open — 76 tolerated pairs |
| AC-013 · React debt | Open | Open | Open |
| AC-019 · Documentary freshness | Partially closed | — | **Open** — the residue: one stale budget comment |
| AC-023 · Refused rule compilation repeated | Open | Remediated — negative cache | Pending closure |
| AC-027 · Capture bundles in the Docker context | Open | Remediated | Pending closure |
| AC-028 · PostgreSQL wait bounds | New, major | Remediated — bounds on every connection | Pending closure — real server bounds tested |
| AC-029 · OAuth refresh lock | New, moderate | Remediated — one refresh door | **Reopened**, P1 — the total duration is not bounded by the lease |
| AC-030 to AC-037 · Coverage margin, register, test bench, retention, async I/O, templates, test contracts | New | Remediated | Pending closure |
| AC-038 · Oversized central instructions | New | Open | Open |
| AC-039 · Documentation language rule | New | Rule amended, ratchet | **Closed** — the amended rule and its guard hold |
| AC-040 · Interface primitives out of coverage (V14's AC-014) | Open, minor | Remediated | Pending closure |
| AC-041, AC-043 to AC-049 | — | — | **New** — one moderate, seven minor |
| AC-042 · Release fixtures | — | — | **Positive control**, closed — the surfaces fixture validated in the commit |

The counter-analysis works both ways: V15 discards the false positives it probed — a timeout inherited from a library default is a bound, the native Drive and Mail sources do check their owner, a bench failure is not a product defect — and it reopens a remediation that did not cover its whole promise (AC-029).

## Open worksites — 1 major, 7 moderate, 9 minor

Published deliberately — a quality claim without its known gaps is marketing, not engineering. Each worksite in the [V15 report](./AUDIT_CODEBASE_2026-10-25_CONSOLIDE_V15.html) carries its verified facts, reproduction, impact, root cause, counter-verification, recommendation, closure criterion and a ready-to-run resolution prompt.

| # | Worksite | Level · Priority · Effort · Horizon |
|---|---|---|
| AC-002 | Fence the processing of an uploaded RAG document across a takeover | Major · P1 · E4 · H1 |
| AC-005 | Give each acquisition of the global reindex lock its own identity | Moderate · P1 · E2 · H1 |
| AC-029 | Bound the total duration of an OAuth refresh within its lease | Moderate · P1 · E2 · H1 |
| AC-010 | Reduce the logic concentration and the Python complexity still high | Moderate · P2 · E4 · H2 |
| AC-011 | Reduce the runtime coupling between domain contexts | Moderate · P2 · E4 · H2 |
| AC-012 | Work off the explicitly tolerated Python typing debt | Moderate · P2 · E3 · H2 |
| AC-013 | Reduce the React contract debt and make the tests deterministic | Moderate · P2 · E3 · H2 |
| AC-049 | Restore the keyboard path of the selection actions under WebKit | Moderate · P2 · E2 · H2 |
| AC-041 | Tell a timeout, a `NOWAIT` refusal and a cancellation apart in the PostgreSQL bound metric | Minor · P2 · E2 · H2 |
| AC-043 | Realign the offline film guard with the current feature catalogue | Minor · P2 · E1 · H2 |
| AC-044 | Stabilize the end-to-end check of the chat's initial position | Minor · P2 · E2 · H2 |
| AC-045 | Make two geometric oracles robust to Firefox's subpixel precision | Minor · P2 · E1 · H2 |
| AC-046 | Keep the primary failure visible in the media E2E diagnostics | Minor · P2 · E1 · H2 |
| AC-047 | Remove the race between two commands in the E2E clock pause | Minor · P2 · E1 · H2 |
| AC-048 | Tell native preconnects apart in the E2E transport oracle | Minor · P2 · E2 · H2 |
| AC-019 | Realign the connection-budget comment with its source | Minor · P3 · E1 · H2 |
| AC-038 | Make the central agent instructions easier to navigate | Minor · P3 · E2 · H2 |

**Prioritized plan — eight batches, ordered by technical return over load and regression radius** (an index for sequencing, not a financial value; a P1 batch starts in the first cycle whatever its index):
1. **Isolated checks and the budget text** — the offline film contract, two geometric oracles, the media diagnostics, the E2E clock, the budget comment (AC-043, AC-045, AC-046, AC-047, AC-019): about 1.25 days, radius R1.
2. **Owned acquisitions and a time budget** — the reindex lock and the OAuth refresh deadline (AC-005, AC-029), first P1 cycle: about 2 days, R2.
3. **The browser bench's native contract** — mocked resources and native preconnects counted apart, unknown real calls still detected (AC-048): about 1 day, R2.
4. **Signals and browser journeys qualified** — PostgreSQL causes, the chat's initial position, the keyboard menu's lifetime, with no timeout or threshold raised to hide a failure (AC-041, AC-044, AC-049): about 3.5 days, R2.
5. **Navigable instructions** — documentary upkeep with a traceability table of the invariants, no mandatory rule lost (AC-038): about 1 day, R2.
6. **Type boundaries and React tests** — one typed boundary or one React group at a time, baselines lowered only after proof (AC-012, AC-013): about 7 days, R2.
7. **The full RAG attempt cycle** — also a first-cycle P1, analysed and tested under concurrency before any change (AC-002): about 7.5 days, R4.
8. **Hotspots and cross-domain dependencies** — progressive structural upkeep, one responsibility and one pair at a time (AC-010, AC-011): about 15 days, R4.

## Delivery performance (DORA)

V15 infers no delivery cadence from a snapshot: it measures neither deployment frequency nor lead time, change failure rate or time to restore. The latest reading is the V14 revision's (2026-10-22):

| Metric | Measured (2026-10-22) | Reservation |
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

**Interpretation caution** (from the report's own annexes): results describe one committed state, not a permanent property of every version, and say nothing of a remote repository or a deployment; "conformant" means conformant to the executed control, not universal conformity to an entire standard; no load, p95 latency, availability or delivery series was measured; no real LLM, voice, SaaS or connector provider was called and no message reached a person; ARM64 builds, native iOS/Android apps and physical devices were not executed, and browser engines do not stand for real phones; the complete browser runs were not green on any engine (one Chromium failure, eight on Firefox, thirty-four on WebKit), each pattern qualified separately and none counted as a product defect without a cause; the combined backend modes ended on bench failures requalified separately, never added back into a green total; full WCAG conformity is not established; coverage measures execution, not oracle quality; and the total absence of security findings means nothing about security, which is out of scope by design.

## Audit history

| Date | Framework | Score | Register |
|---|---|---|---|
| **2026-10-25** | **V15 — 24 areas, each scored by explicit judgment on a published ordinal scale, on one frozen commit (3.6.0)** (report: [HTML](./AUDIT_CODEBASE_2026-10-25_CONSOLIDE_V15.html)) | **7.9/10** (190/240) | **17 open worksites — 1 major, 7 moderate, 9 minor**, 8 of them new (AC-041, AC-043 to AC-049); AC-029 reopened, AC-039 closed, AC-042 published as a positive control; 17 remediations pending an explicit closure |
| 2026-10-22 | V14 revision — a counter-review of V14 on the same grid (report: [HTML](./AUDIT_CODEBASE_2026-10-22_CONSOLIDE_V14-revision.html)) | 7.8/10 (186.5/240) | 26 open findings — 4 major, 11 moderate, 11 minor, 12 of them new (AC-028 to AC-039); closures proven for 3 V14 findings (1 presumed) and 9 V13 findings (2 partial) |
| 2026-10-22 | V14 — 24-area grid, each area the sum of five 0–2 axes (report: [HTML](./AUDIT_CODEBASE_2026-10-22_CONSOLIDE_V14.html)) | 8.0/10 (192/240) | 16 worksites — 3 major, 11 moderate, 2 minor; V13's scheduler-leadership major closed, its three other majors narrowed and still open |
| 2026-08-02 | V11 — normalized 24-area grid (report: [HTML](./AUDIT_CODEBASE_2026-08-02_CONSOLIDE_V13.html)) | 7.3/10 (174.5/240) | 20 worksites — 4 major, 12 moderate, 4 minor |
| 2026-07-24 | V11 — normalized 24-area grid (report: [HTML](./AUDIT_CODEBASE_2026-07-24_CONSOLIDE_V12.html)) | 8.3/10 (199/240) | 7 moderate worksites — 0 major, 0 minor |
| 2026-07-16 | V11 — normalized 24-area grid, revised method (report: [HTML](./AUDIT_CODEBASE_2026-07-16_CONSOLIDE_V11.html)) | 8.3/10 (199/240) | 7 moderate worksites — 0 major, 0 minor; all previously-open majors/minors closed with executed proof |
| 2026-07-10 | Historical grid (20 areas + 4 exploratory) | 8.5/10 like-for-like · 8.4/10 on 24 areas | 12 open items — 6 of the previous 16 closed, 2 advanced |
| 2026-07-09 | Historical grid | 8.4/10 like-for-like · 8.3/10 on 24 areas | 16 open items, prioritized in 4 waves |
| 2026-07-07 | Historical grid (20 areas) | 8.0/10 | 17 items → 10 resolved within 48h |

Scores across framework revisions are not directly comparable; within a framework they can go down as well as up — that is the point of measuring. V14 kept V11's 24 areas and built each score from five explicit axes, and its revision re-scored those axes on fresh evidence; V15 keeps the 24 areas, scores each one by explicit judgment on a published ordinal scale, and audits a frozen commit rather than a working tree. Audits recur after each major remediation wave.

---

*An internal audit aligned on industrial referentials (ISO/IEC 25010:2023, 25040:2024, 5055:2021; ISO/IEC/IEEE 42010:2022, 12207:2026, 29119-2:2021; WCAG 2.2 AA as a control grid), conducted with AI tooling under human direction, every conclusion anchored in executed evidence that this repository lets you check. It is neither an accredited certification nor a guarantee of absence of defects. Security is deliberately out of scope here and covered by a separate assessment (see [SECURITY.md](../../SECURITY.md)).*
