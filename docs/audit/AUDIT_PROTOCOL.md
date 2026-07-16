# 360° Technical Audit — Protocol

> This document makes the audit **reproducible**: same scope, same depth, same evidence
> requirements, same scoring discipline, same publication pipeline — every cycle.
> The public results live in [docs/audit/README.md](./README.md). Security is out of scope
> here and covered by a separate assessment (see [SECURITY.md](../../SECURITY.md)).

The protocol is written for an AI auditor operating under human direction (the same way the
codebase is built — see the [/story field report](https://lia.jeyswork.com/story)), but every
step is executable by a human reviewer. A new audit cycle is triggered by a single request:
*"run the 360° audit and update the public report"*.

---

## 1. Non-negotiable invariants

1. **Pin the baseline first.** `git rev-parse HEAD`, confirm branch and a clean working tree,
   and record commit + version in every output. Never audit "the repo" — audit a commit.
   (Lesson learned: an early audit cycle certified findings against a stale branch.)
2. **Evidence only.** No finding is recorded from a commit message, a doc, or memory of a
   previous cycle. Every claim — positive or negative — is verified in the code of the
   audited commit, with file paths (and line numbers in the internal report).
3. **Counter-verification.** Every negative finding gets an explicit false-positive check
   (multi-line declarations, delegating wrappers, guards living elsewhere, intentional and
   documented behavior). Discarded candidates are worth mentioning in the internal report.
4. **Execute, don't trust — and cross the execution modes.** Test suites are run during the
   audit: separate invocations (the CI way), a combined single-process run under parallel
   scheduling (xdist), AND a combined strictly-sequential run. Record exact
   pass/skip/fail counts per mode. Lesson learned (2026-07-10): parallel scheduling masked
   an order-dependent isolation failure that sequential collection exposed — one mode is
   never enough.
5. **Logical SLOC only.** All size metrics come from
   [`scripts/audit/measure_sloc.py`](../../scripts/audit/measure_sloc.py) (tokenize + AST,
   docstrings/comments/blanks excluded). Raw line counts are never used for scoring.
   Data modules (i18n tables, configuration, constants — see the script's exemption list)
   are reported separately from logic modules. File sizes are frozen by a CI ratchet
   (`apps/api/tests/unit/test_file_size_ratchet_guard.py`, same SLOC semantics and
   exemptions): each audit cycle runs `task ratchet:update` so the caps follow the
   extractions — caps only go down, never up.
6. **Register continuity.** Findings carry stable IDs across cycles (historically `R-…`,
   `F-…`; `AC-…` since the V11 framework). Each new cycle starts by re-verifying every open
   item of the previous register in the code before marking it resolved / partial / open.
   Resolved items cite their proof (ADR, release, file). Since V11 every finding also
   carries a level (major / moderate / minor), an effort estimate (E1–E5) and a
   self-contained resolution prompt executable by a coding AI.
7. **Inline audit.** The audit is conducted in a single analysis context (no delegation of
   judgment); scripts may compute, but conclusions are drawn from directly examined evidence.

## 2. Scope — the 24 areas

Grouped by the ISO/IEC 25010 characteristic they inform. For each area the protocol fixes
the **minimum evidence set** — an audit that skips one of these checks is not comparable.

| # | Area | Minimum evidence set |
|---|------|----------------------|
| 1 | Infrastructure | Compose/prod topology, resource limits vs annotations, image builds (multi-stage, pinning, arch), entrypoints, backup service & restore path |
| 2 | Data & persistence | FK `ondelete` coverage (count), migration chain single-head (recompute, don't trust CI), upsert/locking patterns, session lifecycle, JSONB/mutation guards |
| 3 | Configuration & dependencies | Lockfile presence & consumption by prod build, pin policy, settings surface vs .env examples, feature flags |
| 4 | Architecture | Domain map + LOC distribution, cross-domain import graph (cycles, private-symbol imports), state-object size/typing, orchestration wiring |
| 5 | Design | HITL/interrupt contracts, execution-mode economics, novel-subsystem de-risking (POC evidence), error-handling design (taxonomies, partial failure) |
| 6 | Genericity | Base-class leverage (repos, clients, builders, mixins), registry + boot-time completeness asserts, factory patterns |
| 7 | Extensibility | Add-an-agent/tool/domain/language paths (guides + checklists), release cadence as empirical evidence |
| 8 | Implementation | Function-size distribution (SLOC), docstring coverage, idiom violations (naive datetimes, prints, sync-on-async, raw HTTP exceptions) — counted, not sampled |
| 9 | Maintainability | God-file inventory (logic vs data), growth since last cycle (the ratchet question), dead-code posture, TODO/FIXME count |
| 10 | Quality tooling | Typing strictness both languages, linters, AST guards inventory (run them), escape-hatch counts (`type: ignore`, `noqa`, `any`) |
| 11 | Patterns & practices | Each written engineering rule vs its enforcement reality — list deviations with counts |
| 12 | Robustness | Timeout coverage on HTTP clients (verify multi-line), circuit breakers placement, swallowed exceptions, cancellation/shutdown paths |
| 13 | Reliability | Suite execution results, guard tests, round-trip serialization tests, idempotence of scheduled jobs, lock correctness (leader election, zombie-safety) |
| 14 | Performance | TTFT / per-stage instrumentation existence and values if measurable, known baselines, hot-path costs (reducers, caches) |
| 15 | Optimization | Cache inventory (levels, invalidation, kill-switches), memoizations, code-splitting reality (verify imports, not claims) |
| 16 | Scalability | Connection strategies (pools vs single), multi-worker correctness (leader election, cross-worker invalidation, multiprocess metrics), stated scale target |
| 17 | Operability & observability | Dashboards/metrics/runbooks counts, **alert delivery chain end-to-end** (rules loaded? manager deployed? contact points?), probes, log hygiene (PII) |
| 18 | CI/CD & delivery | Pipeline stages vs test tree (what never runs?), gates & ratchets, action pinning, release automation |
| 19 | Tests | Executed counts per stage, coverage gates & thresholds (locked?), skip analysis (why, how many), e2e reality, isolation (single-process combined run) |
| 20 | Documentation | ADR count & index coherence, freshness drift (announced vs actual counts), runbooks, doc-code contradictions |
| 21 | Portability | Arch/OS matrix (dev vs prod), containerization completeness, install path reproducibility |
| 22 | Compatibility | API versioning & deprecation handling, wire-contract tests (SSE symmetry), interop standards (MCP, CalDAV, IMAP, vCard) |
| 23 | Functional suitability | Feature surface vs test coverage per stage, documented functional gaps (are they decisions or surprises?) |
| 24 | Usability & accessibility | ARIA/focus/reduced-motion/lang signals (counted), alt coverage, i18n parity, formal WCAG pass status |

**Referentials (V11).** Product quality: ISO/IEC 25010:2023 with the ISO/IEC 25040:2024
evaluation framework (security characteristic neutralized). Architecture: ISO/IEC/IEEE
42010:2022. Test processes: ISO/IEC/IEEE 29119-2:2021; automated structural quality:
ISO/IEC 5055:2021 via the guard/metric inventory. Interaction: WCAG 2.2 level AA as the
control grid (WAI-ARIA practices; no full-conformity claim). DORA metrics are reported only
where an observed series exists (deployment frequency and lead time from git; CFR and MTTR
await the incident register — never scored as if observed). The audit is an internal
assessment aligned on these referentials — it claims no accreditation or certification.

## 3. Scoring discipline (V11)

- Scale 0–10 per area, in 0.5 steps. Anchors: **9.5–10** exemplary practice, broad proof,
  negligible residuals; **8.5–9.0** mastered and industrialized, explicit limits or low
  debt; **7.0–8.0** controlled and operational, substantial but bounded debt; **5.5–6.5**
  fragile, incomplete proof or significant recurring defects; **≤5.0** insufficient or
  undemonstrated on essential qualities. A score without at least three cited evidence
  points is invalid.
- The **global score** is the plain arithmetic mean of the 24 normalized areas (no implicit
  weighting, security excluded), rounded to one decimal. The pre-V11 cycles used a
  20-area like-for-like average: **scores across framework revisions are not comparable**
  and the public history table must label the framework of each row.
- A dedicated **counter-analysis section** records discarded false positives and corrected
  false negatives (e.g. artifacts of a degraded dev server, or skipped tests whose
  reactivation was the counter-proof).
- Scores may go down. A regression (e.g. a file that regrew, a gate that was lowered) is
  reported as such, never absorbed silently. Green ratchets prove non-regression only —
  absolute debt values are what gets scored.

## 4. Outputs

1. **Standalone report** (HTML, versioned under `docs/audit/AUDIT_CODEBASE_<date>_CONSOLIDE_V<n>.html`):
   opinion and global score, scope/exclusions, referentials and method, application view,
   24-area scorecard, executed-evidence register, positive controls, worksites with levels
   (major/moderate/minor), efforts (E1–E5) and AI resolution prompts, counter-analysis,
   prioritization horizons, publication-fitness statement and annexes (test methodology,
   scoring scale, quantitative inventory, limits, reproduction commands, references).
2. **Public summary** — [docs/audit/README.md](./README.md), updated in place (it is a
   showcase document, not a changelog), linking to the standalone report. Structure is
   fixed: score banner · why we publish · scope/referentials/method · 24-area scorecard
   with evidence highlights · the improvement loop table (finding → resolution) · open
   worksites with sequencing · DORA · reproduce-it-yourself (with interpretation cautions) ·
   audit history (framework-labeled) · auditor note. **Public-content rule:** open findings
   are phrased as prioritized worksites; no exploitation-oriented detail, no internal line
   numbers — everything stated must be visible in the repository anyway.
3. **Register** carried to the next cycle (IDs, statuses, proofs).

## 5. Publication pipeline (the "update everything" checklist)

Execute in this order — the figures rule is *constants first, then texts*:

1. `docs/audit/README.md` — refresh scores, loop table, worksites, history row, audited
   commit. Keep the section structure fixed.
2. `apps/web/src/components/landing/constants.ts` — `auditScore`, `auditAreas`
   (single source of truth; update the provenance comment).
3. `apps/web/locales/{en,fr,de,es,it,zh}/translation.json` —
   `landing.proof.audit_value` (respect locale decimal separators: comma for fr/de/es/it,
   dot for en/zh — e.g. `8,5/10` vs `8.5/10`) and any other audit-related keys. The pre-commit hook enforces
   6-locale key parity.
4. `README.md` — four touchpoints: the audit badge in the header badge block, the figure in
   the "Built by an AI" table, the row in the Tests → Statistics table, the mention in the
   Performance note. All link to `docs/audit/README.md`.
5. `apps/web/src/data/guides/story.{en,fr,de,es,it,zh}.md` — the audit figures appear in the
   opening paragraph, the numbers table and the audit section; keep the six versions in sync.
6. `docs/INDEX.md` — verify the audit entry is present and current.
7. **Validation before handing over:** i18n parity check (the CI script), TypeScript +
   ESLint + vitest run inside the `lia-web-dev` container, `python scripts/audit/measure_sloc.py`
   runs clean, and `python scripts/audit/doc_audit.py` reports **0 LIVING broken links**
   (it exits non-zero otherwise; remaining LIVING stale code paths must all be deliberate
   placeholders or annotated examples). No git actions — the human owns commits
   and releases.

## 6. Widen or deepen — every cycle

Re-measuring the same evidence eventually finds nothing. Each cycle must add at least one of:
- **a new instrument** on an existing area (examples already in use: logical SLOC → cyclomatic
  complexity; import lists → coupling/instability metrics; a11y signal counts → Lighthouse);
- **a new exploratory area**, scored but kept out of the like-for-like average for one cycle
  (entered the basket so far: portability/compatibility/functional suitability/usability at
  cycle 2; FinOps and privacy engineering at cycle 3);
- **a new probe** for an assumed-covered blind spot (example: client-side error telemetry,
  which server-side observability scores never looked at).
New instruments should be committed as scripts under `scripts/audit/` so the next cycle
reproduces them (measure_sloc.py, measure_cc.py, measure_coupling.py and doc_audit.py exist —
the latter audits documentation drift: broken relative links and stale code-path references,
classified LIVING/HISTORICAL/ROADMAP; introduced after the 2026-07-11 full docs realignment).
Caveat: the cycle-3 CC figures came from an ad-hoc uncommitted counter —
measure_cc.py (strict AST counting, ~6% below that scale, identical ranking) is the
committed instrument from cycle 4 on; do not compare figures across instruments.
Coupling caveat: measure_coupling.py reproduces the cycle-3 Ca/Ce/I figures exactly
(same all-imports semantics, `TYPE_CHECKING` included) and adds runtime-only columns
(`_rt`); the Stable Dependencies assessment reads the runtime columns — only runtime
edges can produce circular-import failures — while the all-imports figures keep the
historical series comparable.

## 7. Cadence

An audit cycle runs after each major remediation wave or feature release, and at most a few
weeks apart while the register has open items. The history table in the public report is the
commitment device: a stale table is itself a finding.
