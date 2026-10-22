# LIA — Public Technical Audit Report

> **Latest assessment: 8.0/10** (192/240) across **24 normalized areas** — dated snapshot of 2026-10-22, the v3.4.0 preparation (commit `89d10bc97` plus its uncommitted release work, closing manifest captured at 08:19 UTC).
> Full standalone report (French): [AUDIT_CODEBASE_2026-10-22_CONSOLIDE_V14.html](./AUDIT_CODEBASE_2026-10-22_CONSOLIDE_V14.html) · Method: evidence-based with systematic counter-proofs, every score backed by at least three cited sources and executed checks · **Security is explicitly and entirely out of scope** (covered separately — see [SECURITY.md](../../SECURITY.md)).
>
> ⚖️ **Quality decision at the snapshot: general validation not granted.** Browser journeys failed on the measured state — most of them test oracles lagging behind decided interface changes, a few reproducing real interface defects — and the full frontend coverage was not replayed after the late corrections. The report is published as a technical assessment with its reservations, not as a conformity attestation or a production go-ahead. What v3.4.0 fixed since is listed below, marked *pending re-audit*.

LIA's engineering claims are public, so their verification should be too. This report is the summary backing for every quality figure shown on the [landing page](https://lia.jeyswork.com/), the [/story field report](https://lia.jeyswork.com/story) and the README; the complete, self-contained report (scorecard, evidence register, counter-analysis, worksite prompts, annexes) is versioned next to this file. It is updated after each audit cycle — including the findings we have not fixed yet.

---

## Why we publish this

Most projects claim quality; few make the claim falsifiable. This repository is open source, its audit reports are published with their open worksites, and the sections below include the exact commands to reproduce the core measurements yourself. The score matters less than the loop that produces it: **audit → prioritized remediation → re-audit**, with every fix landing as a versioned release backed by an Architecture Decision Record.

The method is as auditable as the code: the full audit protocol — scope, referentials, evidence requirements, scoring discipline, publication pipeline — is versioned in [AUDIT_PROTOCOL.md](./AUDIT_PROTOCOL.md), and the structural metrics come from committed measurement scripts ([`scripts/audit/`](../../scripts/audit/)).

A published figure that stops matching the latest cycle is itself a finding. The two cycles before this one (V12 and V13, below) were produced and versioned but never carried to the public surfaces, which kept showing V11's 8.3 — including through V13's 7.3. This publication closes that gap: every cycle is listed in the history, drops included.

## Scope, referentials and method (V14)

- **Object.** The working tree visible at the cut-off (2026-10-22, closing capture 08:19 UTC): commit `89d10bc97` plus the uncommitted v3.4.0 release preparation — 12,480 unique text paths inventoried across `apps/api`, `apps/web`, `infrastructure`, `scripts`, `docs`, Taskfile, manifests, lockfiles, Dockerfiles, Compose and CI workflows. Changes made during the audit were reconciled by fingerprint and the affected checks replayed. **Absolute exclusion:** any security analysis — vulnerabilities, secrets, authn/authz, cryptography, hardening, SAST/DAST, vulnerable dependencies, threat modeling, intrusion testing. No score, finding or prompt takes security into account.
- **Referentials.** Product quality: **ISO/IEC 25010:2023** and **ISO/IEC 25040:2024** (security characteristic neutralized). Architecture: **ISO/IEC/IEEE 42010:2022**. Life-cycle reading: **ISO/IEC/IEEE 12207:2026**. Test processes: **ISO/IEC/IEEE 29119-2:2021**; automated structural quality: **ISO/IEC 5055:2021**. Interaction: **WCAG 2.2 level AA** as the accessibility control grid — no claim of full conformity is made. The audit is an internal assessment aligned on industrial referentials; it is **not** an accredited certification, a guarantee of absence of defects, or a WCAG conformity attestation.
- **Process.** Inventory → static gates (Ruff, Black, MyPy strict, ESLint, non-incremental TypeScript, i18n parity, documentation drift, cycles, complexity, size, baselined debts) → backend suites in three scheduling modes (the CI invocation, a combined xdist run, a combined strictly sequential run) → integration and migration replay on disposable PostgreSQL/Redis → production Docker builds (API and web) → hermetic Playwright journeys on an isolated production server, native media prerequisites included → targeted probes (a returned delivery failure, a two-session job takeover, task cancellation, the alerting channel matrix, a repeated semantic refusal) → counter-analysis.
- **Qualification rule.** No finding rests solely on a comment, a green baseline, a skipped test, an exit code or a historical observation. A dedicated counter-analysis stage documents discarded false positives and corrected false negatives; a test broken before its oracle is never counted as a pass or a product defect.
- **Scoring.** Each area is the sum of five axes scored 0–2 in half points — **C**ontract/structure, **I**mplementation, fresh **V**erification, **G**uard/prevention, **E**xploitation/evolution — so every area score answers the same five questions. The global score is the plain arithmetic mean of the 24 areas: 192 ÷ 24 = **8.0/10**. Finding levels: *major* (an essential contract or operational chain is incorrect), *moderate* (a bounded defect or significant debt), *minor* (a limited gap with no demonstrated business failure). Priorities: P1 before a general qualification, P2 planned risk reduction. Effort E1 (< half a day) to E5 (multi-batch programme).

## Scorecard — 24 normalized areas (2026-10-22)

| # | Area | Score | Evidence highlights |
|---|------|-------|---------------------|
| 1 | Infrastructure | 8.5 | Explicit containerized topology, pinned images, declared resources and backup; native production builds verified; full disaster recovery and ARM builds not qualified in this cycle |
| 2 | Data & persistence | 7.5 | 170 foreign keys declare an explicit `ondelete`; migration chain and schema replayed from an empty database; the finalization of an ordinary RAG upload does not fully protect a new lease owner (AC-002) |
| 3 | Configuration & dependencies | 9.0 | Modular settings, coherent manifests and lockfiles, frozen installation, models downloaded against their fingerprints; no bit-for-bit reproducibility proof for system packages |
| 4 | Architecture | 7.5 | 59 domains with a visible central composition; 22 domain pairs import each other at runtime — an architectural measure, not a count of failing import cycles (AC-011) |
| 5 | Application design | 8.5 | Typed tool contracts, distinct Pipeline and ReAct modes, explicit budgets and recovery; a negative result returned as a value must be handled as rigorously as an exception (AC-003) |
| 6 | Genericity | 9.0 | Shared repositories and factories, generic repository, multi-provider LLM factory, domain taxonomy validated at load |
| 7 | Extensibility | 9.0 | Documented agent and tool creation paths, declarative registries, generated version surfaces |
| 8 | Implementation | 7.5 | Async and UTC idioms largely homogeneous (841 timezone-aware `datetime.now` calls, no naive form); 170 functions above 100 logical SLOC and 263 at cyclomatic complexity ≥ 15 (AC-010) |
| 9 | Maintainability | 7.0 | Useful ratchets but substantial absolute debt: 42 logic files above 600 SLOC, maximum complexity 77 (AC-010, AC-011, AC-013) |
| 10 | Quality tooling | 8.0 | Ruff, Black, MyPy, ESLint and non-incremental `tsc` all runnable; strict MyPy carries 89 neutralized module/code pairs over 489 sources (AC-012) |
| 11 | Patterns & practices | 8.0 | Written rules tied to many AST guards; lock ownership, delivery results and asynchronous draining still bypassed on concrete paths (AC-002, AC-003, AC-005, AC-007) |
| 12 | Robustness | 7.0 | Structured timeouts and circuit breakers; two connection-test paths leave a client unclosed, and task draining returns before cancellation completes (AC-007, AC-008) |
| 13 | Reliability | 7.0 | Scheduler leadership now owner-conditioned; transactions and recovery widely tested; deterministic counter-examples remain on RAG leases and phone delivery acknowledgement (AC-002, AC-003, AC-005) |
| 14 | Performance | 8.0 | Instrumentation, bounded projections, budgets and growth tests present; no user latency or production load capacity was measured during this audit |
| 15 | Optimization | 8.5 | Per-source caches, cross-process single-flight, context versions and cost budgets explicit; invalidations tested (AC-023) |
| 16 | Scalability | 8.0 | Connection budget computed for every worker with a fast failure in production when exceeded; Prometheus multiprocess mode tested; no horizontal-scale or load figure claimed |
| 17 | Operability & observability | 7.0 | 627 metrics, 32 dashboards and 60 runbooks inventoried, alert rules valid; the Alertmanager configuration fails for several optional channel combinations and its routing tree masks business routes (AC-004) |
| 18 | CI/CD & delivery | 8.5 | Thin CI on the Taskfile, explicit gates, hermetic delivery and installation executed; browser gaps prevented declaring every gate green at the snapshot (AC-021, AC-027) |
| 19 | Tests & assurance | 7.5 | Large corpus, marker-coverage guard, coverage floors and real hermetic journeys; oracle quality and the coverage denominator of primitives that became interactive still to improve (AC-014, AC-021) |
| 20 | Documentation | 9.0 | 359 ADR files; living links, quoted versions and thresholds controlled; AGENTS mirror conformant; generated maps and guide dates reconciled on the closing content |
| 21 | Portability | 8.5 | Windows and Linux covered by complementary runs; Unix installation and delivery hermetically tested; ARM builds, native mobile apps and a full restore not executed |
| 22 | Compatibility | 8.5 | `/v1` API, shared SSE vocabulary and provider normalizers visible and tested; transport doubles prove local contracts, not the current state of every external provider |
| 23 | Functional suitability | 8.0 | Broad functional surface, registries and per-domain scenarios; Pipeline, ReAct, notifications, documents and connectors told apart; a failed notification could still be recorded as delivered (AC-003) |
| 24 | Usability & accessibility | 7.0 | Six languages, accessibility controls and reduced motion, no native image without explicit `alt`; a grouped SMS deletion lost keyboard focus and a natural search missed its destination (AC-024, AC-025 — fixed in v3.4.0, pending re-audit) |

## The proof is the loop, not the snapshot

Each cycle starts by re-verifying the previous register in the code. Between V13 (2026-08-02) and this cycle:

| Finding (V13 register) | Status in V14 |
|---|---|
| AC-001 · Scheduler leadership not protected by its owner (major) | **Closed** — renewal and release are conditioned on the owner, and leadership pauses when its lease is lost |
| AC-002 · Incomplete fencing of RAG jobs and reapers (major) | **Narrowed, still open (major)** — the native sources hold their own lease guards; the finalization of an ordinary upload is the remaining path |
| AC-003 · Phone notification marked delivered after a total failure (major) | Still open (major) — reproduced by a returned-failure probe |
| AC-004 · Alertmanager generation and routing vs the documented contract (major) | Still open (major) — the channel matrix passes with no channel, e-mail only and every channel; three partial combinations fail |
| AC-005 · Ownerless RAG reindex lock (moderate) | Still open (moderate) |
| AC-006 · Two Product dashboard panels without metrics (moderate) | Not carried into the V14 register |
| AC-007 · Cancelled tasks not drained before resources close (moderate) | Still open (moderate) |
| AC-008 · Philips Hue client lifecycle (moderate) | **Narrowed** — the client now exposes `close()` and its owners call it; two temporary connection-test paths still do not |
| AC-009 · Non-deterministic fast xdist gate (moderate) | Not carried into the V14 register |
| AC-010 · Backend hotspots (moderate) | Still open — 263 functions at CC ≥ 15 (342 at V13), maximum 77 (87) |
| AC-011 · Bidirectional coupling at domain boundaries (moderate) | Still open — 22 reciprocal runtime pairs (25 at V13) |
| AC-012 · Typed debt hidden by MyPy exemptions (moderate) | Still open — 89 pairs (90 at V13); 859 diagnostics when only those exemptions are lifted |
| AC-013 · Frontend structural debt and deferred React rules (moderate) | Still open — 30 React Hooks deviations over 25 files, 39 complexity violations over 38 files, maximum 46 |
| AC-014 · Frontend coverage presented as per-file (moderate) | **Reframed** — thresholds are confirmed global and per-glob, no per-file claim remains; the V14 item is about fourteen excluded primitives that became interactive |
| AC-015 · No realistic proof lane for low-level voice/Web Audio (moderate) | **Closed** — a native-media wrapper (PulseAudio, local STUN, Xvfb/Mesa) runs the canonical PWA and speaking-avatar journeys without simulated audio or video |
| AC-016 · Generic dialog accessible name hard-coded in French (minor) | **Closed** — the dialog close control is translated |
| AC-017 · Non-immutable rebuild and indirect frontend dependency (moderate) | **Closed** — pinned images, production builds from the lockfiles |
| AC-018 · CI guards liable to drift (minor) | Not carried into the V14 register |
| AC-019 · Incomplete documentary semantic freshness (minor) | **Closed** — quoted versions and thresholds are checked against their sources by `task lint:docs` |
| AC-020 · Orphaned SlowAPI dependency (minor) | Not carried into the V14 register |

The counter-analysis works both ways. This cycle *discarded* false positives — a delivery path presumed broken from a secondary script, 22 reciprocal domain pairs read as 22 import failures, a badge "misaligned" by 9 px that was its own padding, ten media failures that were missing bench prerequisites — **and** kept real defects that could have been excused as stale tests: the SMS focus loss and the missed search destination were reproduced on the product itself, not on an outdated locator.

**Remediation in flight, between cycles.** The table above is the 2026-10-22 snapshot and is left untouched — only a re-audit closes a worksite. For transparency on what v3.4.0 already changed:

| Worksite | Status at v3.4.0 (2026-10-22) |
|---|---|
| AC-021 | **Remediated, pending re-audit.** Every journey the audit qualified as a lagging oracle was realigned on the decided interface while keeping its business oracle — reflow and axe, the right subject and no request for a prefill, focus and requests: always-open Home rubriques, the contact card's address and e-mail as links beside the address-book actions, a share confirmed by its toast once the dialog closes, two discussion-context panels, an SMS sender leading its words, call rows titled like mail, a badge measured by its pill. The Position layout is now read in one frame, and the relationship fixtures answer the connectors read the card makes. On a fresh production build the complete hermetic suite then passes: 690 of 691 journeys on two workers with no retry, the one skip being the HMR isolation check that only applies to the development server. |
| AC-024 | **Remediated, pending re-audit.** The erase button records where the focus returns for every scope — message, sender, day — so once the refresh removes the group, the focus lands on the archive's own disclosure, never on a control the person chose meanwhile. Unit tests prove both cases (red before the fix, green after); the six canonical journeys pass. |
| AC-025 | **Remediated, pending re-audit.** The three shortened administration titles (users, limits, usage export) keep their former full names as search keywords, in all six languages: « administration des utilisateurs » finds the users pane again. Matcher tests on the real catalogues pin it in six languages (red on the previous keywords), and the browser journey picks the right pane. |

## Open worksites — 3 major, 11 moderate, 2 minor

Published deliberately — a quality claim without its known gaps is marketing, not engineering. Each worksite in the [full report](./AUDIT_CODEBASE_2026-10-22_CONSOLIDE_V14.html) carries its verified fact, impact, root cause, counter-verification, recommendation and a ready-to-run resolution prompt.

| # | Worksite | Level · Priority · Effort |
|---|---|---|
| AC-002 | Protect the end of RAG processing against a former owner after a takeover | Major · P1 · E4 |
| AC-003 | Condition the phone delivery acknowledgement on an explicit result | Major · P1 · E3 |
| AC-004 | Compose and validate every advertised Alertmanager channel combination, routing included | Major · P1 · E3 |
| AC-005 | Give the global RAG reindex lock an owner | Moderate · P1 · E3 |
| AC-007 | Wait for cancelled tasks to finish before closing their resources | Moderate · P1 · E2 |
| AC-008 | Close the Hue clients on both connection-test paths | Moderate · P2 · E2 |
| AC-010 | Reduce the absolute complexity of central hotspots | Moderate · P2 · E5 |
| AC-011 | Reduce reciprocal dependencies between domains | Moderate · P2 · E4 |
| AC-012 | Work off the neutralized MyPy diagnostics in coherent batches | Moderate · P2 · E4 |
| AC-013 | Reduce React Hooks debt and complex components | Moderate · P2 · E4 |
| AC-014 | Bring primitives that became interactive back into the coverage measure | Moderate · P2 · E2 |
| AC-021 | Realign the E2E oracles on the interactions actually decided | Moderate · P1 · E3 — *remediated in v3.4.0, pending re-audit* |
| AC-023 | Bound the repetition of a semantically refused rule compilation | Moderate · P2 · E3 |
| AC-024 | Restore focus after a grouped SMS deletion | Moderate · P2 · E2 — *remediated in v3.4.0, pending re-audit* |
| AC-025 | Keep natural vocabulary in the settings search | Minor · P2 · E1 — *remediated in v3.4.0, pending re-audit* |
| AC-027 | Keep capture bundles out of the production Docker context | Minor · P2 · E1 |

**Recommended sequencing** (risk × dependencies × effort): before a general qualification — AC-002, AC-003 and AC-004, durable states and the channel matrix, with counter-examples written before any change; assurance before a qualified delivery — AC-021; a short reliability and usability batch — AC-005, AC-007, AC-008, AC-024, AC-025; a measured debt programme — AC-010 to AC-014, one hotspot or boundary per batch, then AC-023 with a bounded refusal policy, absolute metrics checked rather than the green of the ratchets alone. AC-027 is an independent build-hygiene batch.

## Delivery performance (DORA)

| Metric | Measured | Level |
|---|---|---|
| Deployment frequency | Not scored — no observed deployment series; the release cadence (285 versions in the CHANGELOG) is a fact, not converted into a DORA level | — |
| Lead time for changes | Not scored — not derived from commit volume | — |
| Change failure rate / MTTR | Not instrumented — no incident series exists, so the audit does not score these as if observed | Open |

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

**Interpretation caution** (from the report's own annexes): results describe a dated snapshot — uncommitted release work included — not a permanent property of every version; "conformant" means conformant to the executed control, not universal conformity to an entire standard; no sustained multi-user load, memory stress or production latency series was run; no full disaster recovery with a timed restore; ARM64 builds, native iOS/Android apps, physical devices and audible audio were not executed; no real LLM, voice, SaaS or connector provider was called; full WCAG conformity is not established; DORA series are not observed; coverage measures execution, not oracle quality; and the total absence of security findings means nothing about security, which is out of scope by design.

## Audit history

| Date | Framework | Score | Register |
|---|---|---|---|
| **2026-10-22** | **V14 — 24-area grid, each area the sum of five 0–2 axes** (report: [HTML](./AUDIT_CODEBASE_2026-10-22_CONSOLIDE_V14.html)) | **8.0/10** (192/240) | **16 worksites — 3 major, 11 moderate, 2 minor**; V13's scheduler-leadership major closed, its three other majors narrowed and still open |
| 2026-08-02 | V11 — normalized 24-area grid (report: [HTML](./AUDIT_CODEBASE_2026-08-02_CONSOLIDE_V13.html)) | 7.3/10 (174.5/240) | 20 worksites — 4 major, 12 moderate, 4 minor |
| 2026-07-24 | V11 — normalized 24-area grid (report: [HTML](./AUDIT_CODEBASE_2026-07-24_CONSOLIDE_V12.html)) | 8.3/10 (199/240) | 7 moderate worksites — 0 major, 0 minor |
| 2026-07-16 | V11 — normalized 24-area grid, revised method (report: [HTML](./AUDIT_CODEBASE_2026-07-16_CONSOLIDE_V11.html)) | 8.3/10 (199/240) | 7 moderate worksites — 0 major, 0 minor; all previously-open majors/minors closed with executed proof |
| 2026-07-10 | Historical grid (20 areas + 4 exploratory) | 8.5/10 like-for-like · 8.4/10 on 24 areas | 12 open items — 6 of the previous 16 closed, 2 advanced |
| 2026-07-09 | Historical grid | 8.4/10 like-for-like · 8.3/10 on 24 areas | 16 open items, prioritized in 4 waves |
| 2026-07-07 | Historical grid (20 areas) | 8.0/10 | 17 items → 10 resolved within 48h |

Scores across framework revisions are not directly comparable; within a framework they can go down as well as up — that is the point of measuring. V14 keeps V11's 24 areas and anchors and builds each area score from five explicit axes. Audits recur after each major remediation wave.

---

*An internal audit aligned on industrial referentials (ISO/IEC 25010:2023, 25040:2024, 5055:2021; ISO/IEC/IEEE 42010:2022, 12207:2026, 29119-2:2021; WCAG 2.2 AA as a control grid), conducted with AI tooling under human direction, every conclusion anchored in executed evidence that this repository lets you check. It is neither an accredited certification nor a guarantee of absence of defects. Security is deliberately out of scope here and covered by a separate assessment (see [SECURITY.md](../../SECURITY.md)).*
