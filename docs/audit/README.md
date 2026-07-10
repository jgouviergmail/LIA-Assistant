# LIA — Public Technical Audit Report

> **Latest assessment: 8.5/10** — like-for-like on the historical 20 areas (trajectory 8.0 → 8.4 → 8.5); **8.4/10 across the extended 24-area grid** mapped to ISO/IEC 25010.
> Audited commit: `1b3a0ebc` (v1.23.7, 2026-07-10) · Method: adversarial, evidence-based, every finding verified in the code · Security is assessed separately (see [SECURITY.md](../../SECURITY.md)).

LIA's engineering claims are public, so their verification should be too. This report is the detailed backing for every quality figure shown on the [landing page](https://lia.jeyswork.com/), the [/story field report](https://lia.jeyswork.com/story) and the README. It is updated after each audit cycle — including the findings we have not fixed yet.

---

## Why we publish this

Most projects claim quality; few make the claim falsifiable. This repository is open source, its audit reports are published with their open findings, and the sections below include the exact commands to reproduce the core measurements yourself. The score matters less than the loop that produces it: **audit → prioritized remediation → re-audit**, with every fix landing as a versioned release backed by an Architecture Decision Record.

The method is as auditable as the code: the full audit protocol — scope, depth, evidence requirements, scoring discipline, publication pipeline — is versioned in [AUDIT_PROTOCOL.md](./AUDIT_PROTOCOL.md), and the size metrics come from a committed measurement script ([`scripts/audit/measure_sloc.py`](../../scripts/audit/measure_sloc.py)).

## Method

- **Auditor & posture.** The audit is conducted with AI tooling under human direction, in a deliberately adversarial posture — the same method that builds the product is used to attack it. Every negative finding is verified at file level and counter-checked to eliminate false positives before it is recorded; several candidate findings are discarded at that stage in each cycle.
- **Evidence over declarations.** Test suites are *executed* during the audit, not trusted from CI history. Size metrics are measured in **logical SLOC** (tokenizer + AST, excluding docstrings, comments and blank lines), with data modules (i18n tables, configuration) distinguished from logic modules.
- **Market frameworks.** Scoring follows the **ISO/IEC 25010** product-quality characteristics (security excluded — audited separately), structural quality is assessed against the **ISO/IEC 5055 (CISQ)** weakness categories, delivery performance against **DORA** metrics, and accessibility is sampled against **WCAG 2.1**.
- **Nothing accepted from labels.** Every cycle re-verifies each finding of the previous register in the code before marking it resolved — never on the basis of a commit message (July 10 cycle: 16 items re-verified, 6 closed with proof).
- **Figures are pinned to the audited commit.** The repository moves fast (multiple releases per week); running totals elsewhere (README statistics, landing counters) evolve with each release and may legitimately differ from the commit-pinned numbers in this report.

## Scorecard — 24 areas (2026-07-10)

| Area | Score | Evidence highlights |
|---|---|---|
| Infrastructure | 9.0 | Resource-capped compose with measured limits, automated PostgreSQL backups with **tested restore drill** (ADR-109), reproducible Python builds with hash pinning (ADR-112), multi-arch images |
| Data & persistence | 9.0 | 100% of foreign keys carry `ondelete`, single-head migration chain enforced in CI, server-side atomic upserts, `FOR UPDATE SKIP LOCKED` consumers |
| Design | 9.0 | Dual execution modes (deterministic pipeline vs autonomous agent, 4–8× token spread), 6-level human-in-the-loop with replay-safe contract, new subsystems de-risked by POC before build (ADR-117) |
| Reliability | 9.0 | Test suite rehabilitated end-to-end (ADR-113), integration stage gated in CI, connection-pool gain proven by a committed benchmark |
| Quality tooling | 9.0 | Strict typing on both languages, 4 custom AST guards (JSONB mutation, naive datetimes, empty except blocks, cap constants), double coverage ratchet (backend gate + frontend thresholds) |
| CI/CD & delivery | 9.0 | SHA-pinned actions, real PostgreSQL/Redis services in CI, integration job, CodeQL/Trivy/SBOM chain active |
| Configuration & dependencies | 8.5 | Lockfile with `--require-hashes` consumed by the production build, settings-driven everything (700+ documented variables) |
| Genericity | 8.5 | Generic base classes across repositories/connectors/agents, registries with boot-time completeness asserts — the app refuses to start on a missing entry |
| Extensibility | 8.5 | Adding an agent/tool/domain/language is a documented, checklist-driven path — demonstrated by 140+ releases without a core rewrite |
| Robustness | 9.0 | Settings-driven timeouts on 100% of HTTP clients, circuit breakers at connector base classes, typed domain error contract (ADR-114), zero silent exception swallowing (guarded), and hard-shutdown resilience of detached runs (stream safety-TTL, orphan-run detection with grace period, atomic listener accounting) |
| Optimization | 8.5 | Multi-level caching with documented invalidation and kill-switches, token-count memoization on the hot reducer path, real code-splitting |
| Patterns & practices | 8.5 | Engineering rules are written **and** enforced by blocking checks; deviations are counted, tracked and closed (3 rule classes closed since July 7) |
| Tests | 8.5 | **10,066 backend tests passing when executed by the auditor at the audited commit — in a single pytest process** (5 of the 6 test-isolation anomalies found by the previous cycle are fixed; one order-dependent case remains under strictly sequential collection and is tracked in the worksites); frontend state machines (reducers, SSE handlers, stores) locked at **100% coverage thresholds**; an SSE contract-symmetry test pins backend events to frontend handlers |
| Documentation | 8.5 | 116 Architecture Decision Records, 140+ release changelog, 30+ operational runbooks, per-domain technical docs |
| Portability | 8.5 | Fully containerized, amd64+arm64 images, Windows dev / Linux ARM prod reconciled by design |
| Architecture | 8.0 | Structured DDD (31 bounded contexts), central orchestration graph with factored domain agents, cross-worker cache invalidation, scheduler leader election |
| Implementation | 8.0 | Median function size 12 SLOC, 93% function docstring coverage; the two largest functions were decomposed this cycle (boot sequence: 768 → 89 lines; SSE core: −35%), the remaining oversized set is tracked under the CI size ratchet |
| Operability & observability | 9.0 | **Live alert delivery**: a 13-alert vital core wired to Alertmanager e-mail, thresholds env-templated with descriptions bound to the same variables, every alert annotated with its runbook (ADR-119) — plus 20 dashboards, ~400 metrics, correlated tracing, PII-filtered logging, split probes (ADR-115) |
| Scalability | 8.0 | LangGraph checkpoint/store connection pooling (ADR-111) removed the main concurrency bottleneck; detached background runs decouple work from client connections (ADR-117) |
| Compatibility | 8.0 | Versioned API, SSE contract under symmetry test, MCP / CalDAV / IMAP / vCard interoperability |
| Functional suitability | 8.0 | Broad feature surface under three test stages; known gaps are documented decisions, not surprises |
| Performance | 7.5 | Resource efficiency is excellent; time-to-first-token — the openly acknowledged product weak point — is now instrumented **and measurably improving**: the first two optimization lots shipped and validated (−1.1 s on every request from the router lot alone); the remaining lots are scoped in the committed latency plan |
| Maintainability | 7.5 | Healthy at the median, and file growth is now **mechanically blocked**: a CI ratchet freezes every logical file's size (caps can only go down). The decomposition of the known oversized files has started (startup sequence extracted to modules, voice coordination extracted from the SSE core: −35%) |
| Usability & accessibility | 7.0 | Solid baseline (ARIA labelling, reduced-motion, keyboard focus, 6-language parity enforced in CI); first formal WCAG pass scheduled |

## The proof is the loop, not the snapshot

Between the July 7 and July 9 audits — 48 hours — **10 of 17 open findings were resolved, each shipped as a versioned release with its own ADR**, then re-verified in the code by the follow-up audit:

| Finding (July 7) | Resolution | ADR |
|---|---|---|
| No versioned database backups | Scheduled backups + rotation + tested restore drill | ADR-109 |
| LangGraph single-connection bottleneck | Connection pooling, sized against a documented budget, gain benchmarked | ADR-111 |
| No Python lockfile | Hash-pinned reproducible builds | ADR-112 |
| Test-suite quarantine & missing integration gate | Suite rehabilitation, integration CI job, coverage ratchet raised | ADR-113 |
| Raw HTTP exceptions in connector clients | Typed domain error contract, API contract byte-identical | ADR-114 |
| Dead liveness contract | Separate liveness/readiness probes | ADR-115 |
| Near-absent frontend tests | Test foundation: state machines at 100% locked thresholds, SSE symmetry test | ADR-116 |
| Naive datetimes (9 sites) | All fixed + CI guard extended to prevent recurrence | — |
| 193 empty exception handlers | All eliminated + AST guard added | — |
| Documentation drift (compose comments, probes) | Corrected in the same wave | — |

Between July 9 and July 10 — seven releases — the loop ran again: **six more findings closed, each with its proof**:

| Finding (July 9) | Resolution | Reference |
|---|---|---|
| Real-time alert delivery disabled | 13-alert vital core wired to Alertmanager (env-templated thresholds, runbook-annotated), proven end-to-end | ADR-119 |
| Hard-shutdown gap on detached runs | Stream safety-TTL during the run, orphan detection with grace period in the SSE relay, atomic listener accounting | v1.23.x |
| Oversized boot sequence | Lifespan decomposed into 7 startup modules — 768 → 89 lines, ordering documented | ADR-123 |
| No guard against file regrowth | CI size ratchet on logical SLOC — caps only ever go down | v1.23.x |
| Last tool-policy gap (image generation, DevOps CLI) | Tool-layer rate limiting completed | v1.23.4 |
| Test-suite isolation defect (found by the previous audit) | 5 of 6 anomalies fixed — the combined single-process run is green under parallel scheduling; one order-dependent residue tracked | v1.23.x |

Two more moved substantially: the SSE core shrank by 35% (voice coordination extracted, ADR-122) and the first two latency lots shipped with measured gains (−1.1 s TTFT on every request).

The July 9 re-audit also **found a new defect by executing the suites itself** (a test-isolation issue invisible to CI), which entered the register like any other finding. An audit that never finds anything new is not auditing.

## Open engineering worksites

Published deliberately — a quality claim without its known gaps is marketing, not engineering. All of these items are visible in the open-source repository; this table only adds their prioritization.

| Worksite | Status |
|---|---|
| Latency: the remaining optimization lots (skill-turn streaming, validator robustness) | Next product wave — plan committed in the repo |
| Retirement of the legacy streaming path once the detached path has production proof | Criteria being defined |
| Continued decomposition of the remaining oversized modules (under the CI size ratchet) | Ongoing — one extraction per release |
| Connector HTTP client lifecycle (keep-alive reuse) | Design options under evaluation |
| End-to-end browser smoke suite (chat, HITL, detached-run reattach) | Planned |
| Reducing the agents-suite skips (deterministic fake-LLM tier) | Strategy validated |
| Last order-dependent test-isolation case (sequential single-process collection) | 5 of 6 fixed; root cause pattern known |
| Documentation freshness automation (announced counts vs actual — drifted twice in two cycles) | Priority small fix |
| First formal WCAG 2.1 AA pass | Planned |
| DORA completion: incident register for change-failure-rate and MTTR | Planned |
| Recalibration of the legacy alert set (the vital core is live; the long tail is deliberately off until re-thresholded) | Scoped by ADR-119 |

## Delivery performance (DORA)

| Metric | Measured | Level |
|---|---|---|
| Deployment frequency | 141 releases in 10 months; 8 in the 24h following the last audit | Elite |
| Lead time for changes | Under one day (tag-to-production same day) | Elite |
| Change failure rate / MTTR | Not yet instrumented — incident register is an open worksite above | In progress |

## Reproduce it yourself

```bash
# Backend suites (the numbers in this report were produced by running these,
# as separate invocations — the same way CI runs them)
cd apps/api
pytest tests/unit   -m "not integration and not slow and not e2e and not benchmark and not multiprocess" --no-cov
pytest tests/agents -m "not slow and not e2e and not benchmark and not multiprocess" --no-cov
pytest tests/integration          # requires PostgreSQL + Redis (docker compose dev)

# The custom AST guards that make the engineering rules non-negotiable
pytest tests/unit/test_jsonb_mutation_guard.py tests/unit/test_no_hardcoded_timezone_guard.py \
       tests/unit/test_no_empty_except_guard.py tests/unit/test_max_items_cap_guard.py -v

# Frontend suites and locked coverage thresholds
cd apps/web && pnpm test -- --coverage

# Migration-chain integrity, i18n parity, hygiene checks: see .github/workflows/ci.yml
```

**Transparency note.** The July 9 audit found 6 test-isolation anomalies when running the unit and agents suites in a *single* pytest process (they passed when run separately, as CI does). We published that defect instead of hiding it behind split commands — and five of the six were fixed within a day: as of the July 10 audit, the combined single-process run is green under parallel scheduling (10,066 tests, xdist); one order-dependent case still fails under strictly sequential collection and stays on the public worksite list until closed. One residual quirk remains: one performance test asserts an absolute wall-clock threshold and can flake on a saturated machine (it passes in 0.2 s on a quiet one); its migration to the repo's calibrated-baseline pattern is in the worksites.

## Audit history

| Date | Scope | Score | Register |
|---|---|---|---|
| 2026-07-10 | 24 areas, commit `1b3a0ebc` (v1.23.7) | **8.5/10** like-for-like · 8.4/10 on 24 areas | 12 open items — 6 of the previous 16 closed, 2 advanced |
| 2026-07-09 | 24 areas (ISO 25010 grid), commit `182f3927` | 8.4/10 like-for-like · 8.3/10 on 24 areas | 16 open items, prioritized in 4 waves |
| 2026-07-07 | 20 areas, commit `bbde28f1` | 8.0/10 | 17 items → 10 resolved within 48h |

Audits recur after each major remediation wave. Scores can go down as well as up — that is the point of measuring.

---

*Conducted with AI tooling under human direction, in an adversarial posture; every conclusion anchored in evidence that this repository lets you check. Security is deliberately out of scope here and covered by a separate assessment (see [SECURITY.md](../../SECURITY.md)).*
