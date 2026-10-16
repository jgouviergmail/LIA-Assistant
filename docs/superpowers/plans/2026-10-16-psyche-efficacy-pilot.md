# Psyche efficacy pilot — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. The user has already authorized implementation and subagent execution.

**Goal:** Replace the conversation-only proxy with owner-private domain evidence and bounded, testable guidance before planning/ReAct and final response; remove the obsolete explanatory comment.

**Architecture:** Pure contracts, aggregation and policy; PostgreSQL episode ledger fenced by PsycheState generation; adapters for current terminal streaming output and canonical message feedback. The same policy is consumed by planner, ReAct and response. No online judge, no new dependency, no extra tool authority or quota.

**Tech Stack:** Existing Python/FastAPI/SQLAlchemy/Alembic/Pydantic, Next/React/TypeScript, pytest/PostgreSQL, Vitest/Playwright.

**Spec:** ../specs/2026-10-16-psyche-efficacy-pilot-design.md

## Global constraints

- Work only in C:/Users/jgouv/.codex/worktrees/ui-accueil/lia-ui-accueil, branch codex/ui-accueil. Preserve the 59 previously staged delivery files and the 883 staged files in D:. Never use stash/reset/clean or write any .env; no push or production operation.
- Docker only from D:; use an isolated disposable database for integration/migration proof. Shared dev runtime changes require a concrete validated delivery and coordination.
- Seven canonical cognitive domains, at most two assigned to an episode. Result and usefulness axes never pooled. Unknown, partial and excluded remain distinct; human refusal, quota/provider failure and opaque data do not become competence failures.
- Default pilot window 90 days, cap 500 active episodes, minimum 5 independent scorable observations before a history-derived stance. These are bounded pilot settings, not calibrated probabilities. Current facts, user instructions and mandatory checks override history.
- Episode identity is a logical run plus canonical final answer; transports/retries/HITL do not create extra experience. Feedback from provisional/HITL/notification/session rows is not competence evidence.
- Feedback revision replaces its active contribution. Owner lock precedes reads; episode and projection updates are atomic. Reset generation and retention watermark prevent old tasks/replays resurrecting evidence.
- No old scores converted into invented evidence. Keep legacy self_efficacy read-compatible, stop the old appraisal writer and legacy confidence guidance, publish a separate typed efficacy_profile.
- Collection/influence have separate kill switches, additionally gated by existing platform/user Psyche permissions. No new per-turn judge; no model promotion, permission change or second recovery loop.
- Strict types, no new CC >=15, shrink-only ratchets. Behavioral targeted tests before product changes; empirical PostgreSQL/browser checks and cold adversarial review before delivery.

## Review focus

1. Feedback races with terminal recording and changes thumbs_up → thumbs_down → thumbs_up: one current contribution, no accidental factual reward.
2. Purge/full reset or expiry during HITL: no stale write or active policy from the old generation; no lazy recreation by a delayed task.
3. Physical eviction before the time window expires: a replay cannot reinsert the old episode or refresh its age.
4. Mixed domains, raw tool success, empty retrieval and provider failure: no inflated or misattributed mastery.
5. Router checkpoint is pre-run and message feedback accepts non-terminal rows: consume current streamed deltas and enforce canonical terminal eligibility.

## Shared interfaces (freeze before cross-module integration)

New pure module: src/domains/psyche/efficacy_contracts.py. Use frozen Pydantic models, bounded enums/lists and aware UTC datetimes. Domain vocabulary must derive from the single seven-domain authority in psyche/constants.py.

~~~python
class EfficacyEpoch(BaseModel):
    state_id: UUID
    generation: UUID

class EfficacyObservation(BaseModel):
    domain: EfficacyDomain
    verdict: Literal['success', 'failure', 'partial', 'unknown', 'excluded']
    reason: str  # validated closed vocabulary, no user text

class EfficacyEpisodeInput(BaseModel):
    epoch: EfficacyEpoch
    run_id: str
    message_id: UUID
    terminal_at: datetime
    observations: tuple[EfficacyObservation, ...]  # max two, unique domains
    config_fingerprint: str

class EfficacyPolicy(BaseModel):
    action: Literal['none', 'verify', 'clarify', 'state_limit']
    domains: tuple[EfficacyDomain, ...]
    reason: str
~~~

API efficacy_profile JSON shape:
~~~json
{"version":1,"window_days":90,"collection_enabled":true,"influence_enabled":true,"unassigned_feedback_count":0,"domains":[{"domain":"technical","status":"unobserved","results":{"success":0,"failure":0,"partial":0,"unknown":0},"feedback":{"helpful":0,"unhelpful":0},"result_count":0,"feedback_count":0,"result_score":null,"feedback_score":null,"last_observed_at":null}]}
~~~
All seven domain entries always present; score fields are smoothed indices of their named axis, never truth probability. Observed means minimum sample criterion, not proven expertise. Legacy/absent v2 data renders unknown, not a fabricated meter.

## Task 1 — Pure evidence contracts, aggregation and policy

**Files:** Create efficacy_contracts.py, efficacy_scoring.py, efficacy_policy.py and matching unit tests under tests/unit/domains/psyche/. Extend constants.py only to establish one canonical domain vocabulary. Own no existing agent integration files.

**Consumes:** approved spec and shared JSON contract. **Produces:** EfficacyEpoch, EfficacyObservation, EfficacyEpisodeInput, EfficacyProfile, EfficacyPolicy and a typed episode view consumed by aggregation.

- [ ] Write failing behavior tests for all seven domains, strict/finite values, duplicate/unknown domains, stale/future timestamps, separate axes, cold start, five-sample gate, ambiguity/current gap/budget interactions and contradictory current evidence.
- [ ] Watch red, then implement pure functions: build_profile(episodes, now, window_days, collection_enabled, influence_enabled) and choose_policy(profile, domains, current_gap, ambiguous, can_verify, budget_available).
- [ ] Make unknown/excluded neutral. Do not invent partial=0.5. Utility can influence clarification only; cannot establish facts. With no relevant gap/ambiguity return action none even for weak history.
- [ ] Example behavioral assertion:
~~~python
assert choose_policy(profile_with_poor_feedback, domains, current_gap=False,
                     ambiguous=False, can_verify=True, budget_available=True).action == 'none'
~~~
- [ ] Verify complete domain projection, no current-input mutation, deterministic results and <=120-token bounded policy rendering. Run scoped Ruff/Black/MyPy and tests.

## Task 2 — Durable private episodes and generation fences

**Files:** Create efficacy_models.py, efficacy_repository.py; extend psyche/models.py with generation, projection and eviction boundary; migration after b62a8d193f04; registry import; unit/integration tests. Own reset persistence hooks in reset_policy.py/repository.py only after root coordination.

**Consumes:** Task 1 models. **Produces:** EfficacyRepository.capture_epoch(user_id), read_profile(user_id, now), record_episode(user_id, episode, now, feedback=None, replace_feedback=False), apply_feedback(user_id, message_id, verdict, now), invalidate/reset helpers. Flush only; caller owns transaction. Repository never creates PsycheState for a late writer.

- [ ] Write failing PostgreSQL tests for owner isolation, concurrent independent sessions, duplicate recording, feedback before/after finalizer, feedback reversals, stale epoch, reset/purge, expiration and cap eviction replay.
- [ ] Example invariant:
~~~python
await repo.record_episode(owner, episode, now=now)
await repo.record_episode(owner, episode, now=now)
assert (await repo.read_profile(owner, now=now)).domains[0].result_count == 1
~~~
- [ ] Add one bounded active episode record per owner/generation/run. Canonical message/time must match an existing record; a conflicting retry is refused, not rewritten as a fresh sample. Keep no raw texts/tool arguments.
- [ ] Lock owner then state before reading. Retain active feedback independently of terminal re-delivery. Recompute the bounded projection in the same transaction. Add chronological eviction watermark and use canonical terminal time at both write and read.
- [ ] Prove migration upgrade/downgrade and model consistency on an isolated target; do not backfill any learning evidence from legacy score/weight.

## Task 3 — Honest experience UI and comment removal

**Files:** Frontend Psyche types, new PsycheEfficacy component, PsycheStateSummary integration, six translation files and focused unit/browser fixtures. Own only frontend files in this task.

**Consumes:** efficacy_profile JSON contract. **Produces:** accessible seven-domain view showing unknown/learning/observed, distinct verified-result and helpfulness counts/indices, date and collection state.

- [ ] Write failing tests: no invented 50% from absent/legacy profile, all seven labels, two axes not fused, mixed-domain feedback not spread, owner state changes, and readable mobile expanded content.
- [ ] Remove the requested efficacyExplanation paragraph and its now-unused locale keys. Do not write a test that merely snapshots its CSS or repeats the exact removal.
- [ ] Display percentage only with the named evidence basis; unavailable values stay unknown. Reuse existing Disclosure/meter primitives and neutral label semantics. Keep sections initially folded on mobile.
- [ ] Run focused Vitest, scoped ESLint/TypeScript and prepare hermetic desktop/mobile smoke assertions without triggering real LLM calls.

## Task 4 — Terminal proof and feedback integration

**Files:** Root owns new agents/services/efficacy_evidence.py, psyche/efficacy_service.py and composition/adapters; narrowly modify agents/api/service.py, archive metadata, streaming delta capture, conversations feedback port/router/startup registration, config settings, schemas/router/projection, account reset boundaries.

**Consumes:** Task 1 and Task 2. **Produces:** one canonical metadata envelope on an ordinary final archived assistant answer; best-effort post-archive recorder; owner-transactional feedback consumer; typed API profile.

- [ ] Write failing tests of current terminal deltas vs old checkpoint, canonical final answer filtering, attributable vs provider failures, empty valid result, partial/unknown and previous-turn leakage.
- [ ] Obtain capabilities and epoch at the current user turn; serialize only minimal generation/policy context. Archive compact proof observations and immutable provenance on the final row. No metadata on HITL questions/provisional/session/automated messages.
- [ ] Terminal recording uses the final streamed GoalCoverage, never AgentResult.SUCCESS or HTTP status. Preserve current root run identity and reject actor mismatch.
- [ ] Feedback validates the judged final message and source envelope; persist contribution in the existing owner transaction, including feedback arriving before the delayed recorder. Preserve journal/product semantics; no new endpoint or model call.
- [ ] Stop the old emotional_support efficacy update and old score-derived confidence injection without disabling emotion/relationship appraisal. Soft reset keeps evidence; full reset changes generation; purge deletes evidence via state ownership.
- [ ] Ensure master/user feature gates apply at collection AND influence, with granular typed errors and bounded low-cardinality diagnostics.

## Task 5 — Shared policy before planner/ReAct and during response

**Files:** Root owns QueryIntelligence declaration/serialization/reconstruction, query analysis schema/prompt mapping, router projection, planner context, react_context and response context. New versioned prompt text lives in agents/prompts/v1 and is registered in the loader. No prompt strings embedded in business code.

- [ ] Write red tests for seven-domain attribution using declared structured analysis; no fragile keyword classifier. Test unknown, mixed objectives and at most two domains.
- [ ] Round-trip snapshot through msgpack/HITL; revalidate generation and validity after interruption. No private scores/raw evidence in checkpoints, no new independently-reset MessagesState accumulator.
- [ ] Read one bounded profile; choose one shared policy. Mount it for both planner and ReAct before decision and for final synthesis independent of PAD.
- [ ] Require actual evidence for any claimed check. Existing coverage/recovery and budgets remain authoritative; no new loop or mandatory check for every new user.
- [ ] Test OFF/ON against fixed cases: ambiguity, missing evidence, high history with contradictory present result, weak history with complete current evidence, no budget/tool, legitimate refusal, and technical operation unavailable in pipeline mode.

## Task 6 — Whole-pilot qualification and review

- [ ] Run all new pure/behavior suites plus affected existing Psyche, feedback, QueryIntelligence, planner, ReAct and archive tests. Run PostgreSQL independent-session/reset/replay/migration cases on disposable infrastructure only.
- [ ] Run targeted front/E2E, six-locale parity, type/lint/ratchet checks; shrink baselines only after measured improvement. No suppressed warnings or raised baselines.
- [ ] Cold adversarial review by a non-author across storage, security, scope/permissions, prompt injection, privacy, concurrent reset/feedback, clocks, budgets and account switching. Fix root causes and repeat only affected checks.
- [ ] Produce OFF/ON probe/corpus evidence with costs and limits. No claim of broad real-world improvement based solely on synthetic tests. Document operator/user kill switches and functional rollback.
- [ ] Snapshot validated sources. Before any preview copy, recheck D index/HEAD/protected files and parallel worktree overlap, back up exact preimages and verify byte hashes. No shared dev migration or restart until isolated validation is green and the operation is explicitly scoped.
- [ ] Stop after delivery of this pilot, awaiting user validation before another UI lot. No push or production deployment.