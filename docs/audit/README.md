# LIA — Public Technical Audit Report

> **Latest assessment: 8.4/10** — like-for-like against the July 7 baseline (8.0/10); **8.3/10 across the extended 24-area grid** mapped to ISO/IEC 25010.
> Audited commit: `182f3927` (v1.22.0, 2026-07-09) · Method: adversarial, evidence-based, every finding verified in the code · Security is assessed separately (see [SECURITY.md](../../SECURITY.md)).

LIA's engineering claims are public, so their verification should be too. This report is the detailed backing for every quality figure shown on the [landing page](https://lia.jeyswork.com/), the [/story field report](https://lia.jeyswork.com/story) and the README. It is updated after each audit cycle — including the findings we have not fixed yet.

---

## Why we publish this

Most projects claim quality; few make the claim falsifiable. This repository is open source, its audit reports are published with their open findings, and the sections below include the exact commands to reproduce the core measurements yourself. The score matters less than the loop that produces it: **audit → prioritized remediation → re-audit**, with every fix landing as a versioned release backed by an Architecture Decision Record.

The method is as auditable as the code: the full audit protocol — scope, depth, evidence requirements, scoring discipline, publication pipeline — is versioned in [AUDIT_PROTOCOL.md](./AUDIT_PROTOCOL.md), and the size metrics come from a committed measurement script ([`scripts/audit/measure_sloc.py`](../../scripts/audit/measure_sloc.py)).

## Method

- **Auditor & posture.** The audit is conducted with AI tooling under human direction, in a deliberately adversarial posture — the same method that builds the product is used to attack it. Every negative finding is verified at file level and counter-checked to eliminate false positives before it is recorded; several candidate findings are discarded at that stage in each cycle.
- **Evidence over declarations.** Test suites are *executed* during the audit, not trusted from CI history. Size metrics are measured in **logical SLOC** (tokenizer + AST, excluding docstrings, comments and blank lines), with data modules (i18n tables, configuration) distinguished from logic modules.
- **Market frameworks.** Scoring follows the **ISO/IEC 25010** product-quality characteristics (security excluded — audited separately), structural quality is assessed against the **ISO/IEC 5055 (CISQ)** weakness categories, delivery performance against **DORA** metrics, and accessibility is sampled against **WCAG 2.1**.
- **Nothing accepted from labels.** In the July 9 cycle, all 17 findings of the July 7 register were re-verified in the code before being marked resolved — none was accepted on the basis of a commit message.
- **Figures are pinned to the audited commit.** The repository moves fast (multiple releases per week); running totals elsewhere (README statistics, landing counters) evolve with each release and may legitimately differ from the commit-pinned numbers in this report.

## Scorecard — 24 areas (2026-07-09)

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
| Extensibility | 8.5 | Adding an agent/tool/domain/language is a documented, checklist-driven path — demonstrated by 130+ releases without a core rewrite |
| Robustness | 8.5 | Settings-driven timeouts on 100% of HTTP clients, circuit breakers at connector base classes, typed domain error contract (ADR-114), zero silent exception swallowing (guarded) |
| Optimization | 8.5 | Multi-level caching with documented invalidation and kill-switches, token-count memoization on the hot reducer path, real code-splitting |
| Patterns & practices | 8.5 | Engineering rules are written **and** enforced by blocking checks; deviations are counted, tracked and closed (3 rule classes closed since July 7) |
| Tests | 8.5 | **9,913 backend tests passing when executed by the auditor at the audited commit** (unit + agents, run as CI runs them — see the reproduction note below); frontend state machines (reducers, SSE handlers, stores) locked at **100% coverage thresholds**; an SSE contract-symmetry test pins backend events to frontend handlers |
| Documentation | 8.5 | 110 Architecture Decision Records, 130+ release changelog, 30+ operational runbooks, per-domain technical docs |
| Portability | 8.5 | Fully containerized, amd64+arm64 images, Windows dev / Linux ARM prod reconciled by design |
| Architecture | 8.0 | Structured DDD (31 bounded contexts), central orchestration graph with factored domain agents, cross-worker cache invalidation, scheduler leader election |
| Implementation | 8.0 | Median function size 12 SLOC, 93% function docstring coverage; a known set of oversized core functions is tracked for decomposition (see open worksites) |
| Operability & observability | 8.0 | 20 provisioned dashboards, ~400 metrics, distributed tracing correlated with logs, PII-filtered structured logging, liveness/readiness probes (ADR-115) |
| Scalability | 8.0 | LangGraph checkpoint/store connection pooling (ADR-111) removed the main concurrency bottleneck; detached background runs decouple work from client connections (ADR-117) |
| Compatibility | 8.0 | Versioned API, SSE contract under symmetry test, MCP / CalDAV / IMAP / vCard interoperability |
| Functional suitability | 8.0 | Broad feature surface under three test stages; known gaps are documented decisions, not surprises |
| Performance | 7.0 | Resource efficiency is excellent; **time-to-first-token is the openly acknowledged product weak point** — now instrumented end-to-end, optimization program scheduled |
| Maintainability | 7.0 | Healthy at the median; concentrated debt in a known list of oversized files — the remediation approach (characterization tests, then extraction) is defined |
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

The July 9 re-audit also **found a new defect by executing the suites itself** (a test-isolation issue invisible to CI), which entered the register like any other finding. An audit that never finds anything new is not auditing.

## Open engineering worksites

Published deliberately — a quality claim without its known gaps is marketing, not engineering. All of these items are visible in the open-source repository; this table only adds their prioritization.

| Worksite | Status |
|---|---|
| Real-time alert delivery (Alertmanager reactivation; dashboards and recording rules are live) | Top of the operations wave |
| Hard-shutdown resilience of detached background runs (stream TTL, subscriber bail-out) | Scoped, small |
| Retirement of the legacy streaming path once the detached path has production proof | Criteria being defined |
| Decomposition of the two oversized core functions + CI size ratchet to stop regrowth | Method defined (characterization tests first) |
| Time-to-first-token optimization program | Instrumented; measurement-first lot next |
| Connector HTTP client lifecycle (keep-alive reuse) | Design options under evaluation |
| End-to-end browser smoke suite (chat, HITL, detached-run reattach) | Planned |
| First formal WCAG 2.1 AA pass | Planned |
| DORA completion: incident register for change-failure-rate and MTTR | Planned |
| Test-suite isolation (single-process run of all suites) | Found by this audit; fix pattern known |

## Delivery performance (DORA)

| Metric | Measured | Level |
|---|---|---|
| Deployment frequency | 130+ releases in 10 months; 12 in the 48h remediation wave | Elite |
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

**Transparency note.** If you run the unit and agents suites in a *single* pytest process instead of two, you will currently see 6 test-isolation anomalies (tests that pass when the suites run separately, as CI does). This defect was found by the July 9 audit itself — by executing the suites rather than trusting CI history — and is tracked in the open worksites above. We could have hidden it by only documenting the split commands without comment; publishing it is the point of this report.

## Audit history

| Date | Scope | Score | Register |
|---|---|---|---|
| 2026-07-09 | 24 areas (ISO 25010 grid), commit `182f3927` | **8.4/10** like-for-like · 8.3/10 on 24 areas | 16 open items, prioritized in 4 waves |
| 2026-07-07 | 20 areas, commit `bbde28f1` | 8.0/10 | 17 items → 10 resolved within 48h |

Audits recur after each major remediation wave. Scores can go down as well as up — that is the point of measuring.

---

*Conducted with AI tooling under human direction, in an adversarial posture; every conclusion anchored in evidence that this repository lets you check. Security is deliberately out of scope here and covered by a separate assessment (see [SECURITY.md](../../SECURITY.md)).*
