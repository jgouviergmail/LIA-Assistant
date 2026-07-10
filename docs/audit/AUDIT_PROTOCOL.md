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
4. **Execute, don't trust.** Test suites are run during the audit — unit and agents suites
   at minimum, invoked the way CI invokes them (separate processes). Record exact
   pass/skip/fail counts and durations.
5. **Logical SLOC only.** All size metrics come from
   [`scripts/audit/measure_sloc.py`](../../scripts/audit/measure_sloc.py) (tokenize + AST,
   docstrings/comments/blanks excluded). Raw line counts are never used for scoring.
   Data modules (i18n tables, configuration, constants — see the script's exemption list)
   are reported separately from logic modules. File sizes are frozen by a CI ratchet
   (`apps/api/tests/unit/test_file_size_ratchet_guard.py`, same SLOC semantics and
   exemptions): each audit cycle runs `task ratchet:update` so the caps follow the
   extractions — caps only go down, never up.
6. **Register continuity.** Findings carry stable IDs across cycles (`R-…`, `R2-…`, `R3-…`).
   Each new cycle starts by re-verifying every open item of the previous register in the
   code before marking it resolved / partial / open. Resolved items cite their proof
   (ADR, release, file).
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

**Cross-framework mapping** reported every cycle: ISO/IEC 25010 characteristics (security
excluded), ISO/IEC 5055 (CISQ) structural-weakness coverage via the guard inventory, DORA
four metrics (deployment frequency and lead time from git; CFR and MTTR from the incident
register once it exists), WCAG 2.1 sampling for area 24.

## 3. Scoring discipline

- Scale 0–10 per area, in 0.5 steps. Anchors: **9+** exemplary with proof (would cite as
  reference); **8–8.5** strong, deviations counted and bounded; **7–7.5** solid with a known
  structural debt; **6–6.5** significant debt, remediation not yet structured; **≤5**
  systemic weakness. A score without at least three cited evidence points is invalid.
- The **global score** is the plain average over the 20 historical areas (like-for-like
  continuity with previous cycles) — the 24-area average is reported alongside.
- Scores may go down. A regression (e.g. a file that regrew, a gate that was lowered) is
  reported as such, never absorbed silently.

## 4. Outputs

1. **Internal report** (full depth, file:line references, per-finding criticality S/M/L +
   effort, remediation prompts ready to execute). Not published as-is.
2. **Public report** — [docs/audit/README.md](./README.md), updated in place (it is a
   showcase document, not a changelog). Structure is fixed: score banner (like-for-like +
   24-area) · why we publish · method · 24-area scorecard with evidence highlights ·
   the improvement loop table (finding → resolution → ADR) · open worksites · DORA ·
   reproduce-it-yourself (including the transparency notes on known reproduction caveats) ·
   audit history · auditor note. **Public-content rule:** open findings are phrased as
   prioritized worksites; no exploitation-oriented detail, no internal line numbers —
   everything stated must be visible in the repository anyway.
3. **Register** carried to the next cycle (IDs, statuses, proofs).

## 5. Publication pipeline (the "update everything" checklist)

Execute in this order — the figures rule is *constants first, then texts*:

1. `docs/audit/README.md` — refresh scores, loop table, worksites, history row, audited
   commit. Keep the section structure fixed.
2. `apps/web/src/components/landing/constants.ts` — `auditScore`, `auditAreas`
   (single source of truth; update the provenance comment).
3. `apps/web/locales/{en,fr,de,es,it,zh}/translation.json` —
   `landing.proof.audit_value` (respect locale decimal separators: `8,4/10` for fr/de/es/it,
   `8.4/10` for en/zh) and any other audit-related keys. The pre-commit hook enforces
   6-locale key parity.
4. `README.md` — four touchpoints: the audit badge in the header badge block, the figure in
   the "Built by an AI" table, the row in the Tests → Statistics table, the mention in the
   Performance note. All link to `docs/audit/README.md`.
5. `apps/web/src/data/guides/story.{en,fr,de,es,it,zh}.md` — the audit figures appear in the
   opening paragraph, the numbers table and the audit section; keep the six versions in sync.
6. `docs/INDEX.md` — verify the audit entry is present and current.
7. **Validation before handing over:** i18n parity check (the CI script), TypeScript +
   ESLint + vitest run inside the `lia-web-dev` container, `python scripts/audit/measure_sloc.py`
   runs clean, every markdown link added resolves. No git actions — the human owns commits
   and releases.

## 6. Cadence

An audit cycle runs after each major remediation wave or feature release, and at most a few
weeks apart while the register has open items. The history table in the public report is the
commitment device: a stale table is itself a finding.
