# Chat and dashboard latency — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans, **strictly inline — no
> sub-agent** (owner rule). Steps use checkbox (`- [ ]`) syntax. **No `git add`, no commit**
> (owner rule): every « commit » step of the usual template is replaced by « record the lot's file
> list » for the exhaustive review.

**Goal:** Bound and shorten the wait before the first useful content, in the chat and on the
dashboard, without losing a capability, a confirmation, a right check or a billed euro.

**Architecture:**
- **Chat.** The chat turn commits its setup and archives the message *before* preparing personal
  MCP servers. The servers are prepared in parallel under one ceiling, from a persisted,
  fingerprinted catalogue revalidated in the background and verified at use.
- **Dashboard.** First it stops re-collecting (sequencing, attempt markers, owner liveness). Then it
  becomes progressive over plain HTTP, joined into one act by a signed token.

**Tech Stack:** FastAPI, asyncio, PostgreSQL JSONB, Redis claims (`infrastructure/locks/redis_claim.py`),
Next.js 16 / React 19 hooks (`useApplicationAccountQuery`), Sonner, vitest, Playwright, Prometheus/Grafana.

**Spec:** [2026-10-21 analysis](../specs/2026-10-21-chat-dashboard-latency-analysis.md). Test IDs
(C*, M*, N*, D*, W*, S*, O*, X*) refer to its §8. All paths are relative to the repository root.

## Global Constraints

- **Gates.**
  - Q1 (ADR-338 amendment) was accepted and confirmed on 2026-10-22 **for this case only** — the
    catalogue of personal MCP servers used to prepare a turn.
  - Q2 is answered (a): at the ceiling, the turn continues without the cold server, says so, and
    the discovery finishes in the background.
  - Every other lot can start.
- **`read_me`** is fetched only at real use (owner decision, 2026-10-22; spec A15).
- **Re-verified on 2026-10-28** against HEAD `5e76b633c` (spec §0bis). Three coordination rules
  follow:
  - the frontend half of D1 and all of D3 start only once the staged « LIA World » lot, which
    rewrites `apps/web/src/hooks/useBriefing.ts`, is committed;
  - S1 is written together with the pending Drive push lot (a per-call read budget in the same
    `BaseOAuthClient._make_request`), never beside it;
  - every production figure is re-measured (P0) before a gain is claimed, because the 20/10 figures
    were taken during a documented Internet outage.
- **Measured on 2026-10-28** (spec §0ter). Production was measured read-only over 7 days; the rest
  was simulated with the real code or proven at runtime. Every « before » figure below comes from
  there, and every lot's gain is checked against it. The measurements added three findings:
  - E11, embeddings recomputed on the critical path: new lot M6;
  - E12, the shared-flight waiter only accepts a complete bundle: lot D1;
  - E13, SMS read three times per page: lot D1.

  They also turned E2 into lot S2, gated by Q3.
- **Mechanisms, not models.** Reason by mechanism and slot; no setting, test or branch names a model
  or a provider (owner rule).
- **New settings and their defaults:**

  | Setting | Default |
  |---|---|
  | `MCP_USER_PREPARATION_CONCURRENCY` | 4 |
  | `MCP_USER_DISCOVERY_TIMEOUT_SECONDS` | 15, applied as `min(this, server.timeout_seconds)` |
  | `MCP_USER_PREPARATION_CEILING_SECONDS` | 20 |
  | `MCP_USER_SLOW_PREPARATION_NOTICE_SECONDS` | 10 |
  | `MCP_USER_CATALOGUE_REVALIDATE_AFTER_SECONDS` | 900 |
  | `BRIEFING_SHARED_BUILD_MAX_WAIT_SECONDS` | 60 |
  | `BRIEFING_SECTION_ATTEMPT_MARKER_SECONDS` | 120 |
  | `BRIEFING_TEXT_CACHE_TTL_SECONDS` | 300 |
  | `BRIEFING_ACT_TOKEN_TTL_SECONDS` | 600 |
  | `BRIEFING_SECTION_CONCURRENCY` | 4 (D2, client side; published by the initial response) |
  | `MCP_USER_EMBEDDING_INLINE_MAX_TOOLS` | 8 (M6) |

- **Settings surfaces.** Every setting has:
  - its default in `apps/api/src/core/constants.py`;
  - a `Field(ge=…, le=…, description=…)` in its config module;
  - lines in `.env.example`, `.env.prod.example`, `.env.demo-instance.example`,
    `.env.demo-instance.prod.example`, `.env.demo-instance` and `.env.demo-instance.prod`.
  - `.env.min.prod` is not touched.
- **Ratchets are shrink-only:** file size (`apps/api/tests/unit/file_size_baseline.json`, cap 600),
  backend CC (`apps/api/.cc-baseline.json`: `over` 260, `max` 77 on 2026-10-28), and the front-end a11y,
  react-hooks and complexity ratchets.
  - Every addition to a file within 15 lines of its cap starts with an extraction in the same lot.
  - No new function at CC ≥ 15; no hotspot grows.
  - Measure with `apps/api/.venv/Scripts/python scripts/audit/measure_cc.py --check-ratchet`.
- **Database and Redis.**
  - No new table, no migration, no in-place JSONB mutation (new dict on every write).
  - Redis keys are built by their domain builder, and their family is declared in
    `apps/api/src/infrastructure/cache/key_families.py`.
- **Network and retries.**
  - No new dependency; no session open across a network wait (ADR-304).
  - No automatic retry added anywhere, and no relaunch of a paid generation whose outcome is
    unknown.
- **Spend.** Every spend keeps both ceilings (ADR-272): `spend_blocked` or `enforce_usage_limit`,
  and attribution. Only the owner of an operation bills.
- **State.** Nothing progress-related enters `MessagesState`, checkpoints, messages or memories.
- **Front end and i18n.**
  - Backend payloads carry structured data and label keys.
  - Six locales with strict parity, and FAQ entries in six languages for user-visible behaviour.
- **Metrics.** Every new metric is referenced by a Grafana panel expression (metric-coverage
  ratchet) and uses bounded labels only.
- **Tests and proofs.**
  - Unit tests on the host with `apps/api/.venv/Scripts/pytest … --no-cov`.
  - Integration tests on the host with testcontainers and `-m integration --no-cov`, never inside
    `lia-api-dev`. The whole integration suite runs through `task test:backend:integration`, with a
    disposable `TEST_REDIS_URL` on base 15.
  - Coverage gates: `task test:backend:coverage`, then `task test:backend:diff-coverage` (every
    changed line of `apps/api/src` covered at the floor).
  - New settings pass the env-template parity guard (`test_env_template_parity_guard.py`): a
    template states the code's default, omits the key, or says why it differs.
  - New async code passes Ruff `ASYNC2` (no blocking call on the loop).
  - Runtime proofs in Docker dev, on the proof account, never the owner's.
  - After any change to `apps/api/src/domains/agents/api/service.py` or a symbol it calls: grep the
    patches in `apps/api/tests/agents/` and run `task test:backend:agents`.
- **Shared working tree.**
  - Re-read each file immediately before editing it.
  - Edit only the lot's lines; never run a global formatter; preserve other agents' uncommitted
    changes.
  - Exhaustive cold adversarial review of every file of the lot's diff at the end of each lot
    (owner rule).

## Lots, order and estimates

Sizes:
- **S**: ≤ 5 files, < 200 production lines.
- **M**: 5–10 files or 200–500 lines.
- **L**: > 10 files, > 500 lines, or the chat or dashboard critical path.

Durations are my own continuous inline work in this repository: the code is the short part, and
most of the time goes to the gates (30–45 min a pass, often two passes), the runtime proof and the
exhaustive review. They exclude what lengthens the calendar without being my time: the owner's
validation between lots, an authorization, and the commit of the staged « LIA World » lot.

The last column is the « before » measured on 2026-10-28 (spec §0ter), then the expected effect.
An expected effect is a target to prove at the lot's runtime proof, never a claim.

| Order | Lot | Size | Estimate | Depends on | Measured before → expected |
|---|---|---|---|---|---|
| 1 | P0 harness and dev baseline (production measured on 2026-10-28) | S | 0.5–1 h | — | — |
| 2 | C1 pre-graph commit and archive-first (closes R18) | M, critical path | 2.5–3.5 h | P0 | 1 connection idle in transaction for the whole preparation (p95 19 s) → 0 |
| 3 | O1 journey metrics (backend) | S | 1–1.5 h | P0 | The SLI misses the preparation; 2.9 % of turns unobserved → both observed |
| 4 | W1 weather and environment clients | S | 1–1.5 h | P0 | Weather p50 5.0 s (8 requests, sequential fresh connections at 672 ms) → about 1.2–1.6 s |
| 5 | D1 dashboard stops re-collecting — backend half (with re-claim, lease fence and one SMS read) | M | 3.5–4.5 h | P0 | A missing section costs every waiter 10 s, then N reads; SMS read 3× per page; a push during a read can cache a stale section → 0 extra wait, 1 read, never stale |
| 6 | M6 tool embeddings off the critical path (E11) | S–M | 2–3 h | — | 31 recomputes, 131 s in 7 days, up to 16.4 s per turn → 0 s on the turn |
| 7 | M1 catalogue snapshot (canonical order, server TTL and scope, cursor pagination E7, generation fence) | M | 2.5–4 h | — | 48 % of turns cold, 32 % of quick follow-ups → cold only on a server's first use |
| 8 | M1b `read_me` and server `instructions` at real use | M | 2.5–3.5 h | M1 | No latency effect measured (0 of 314); fixes E9, E10; adds the protocol's own guidance channel |
| 9 | M2 parallel preparation and revalidation | L | 4–6 h | C1, M1, M1b, M6 | Cold p95 19.2 s, 37 turns > 10 s a week → p95 about 8.5 s, about 4 (before M1 and M6) |
| 10 | M3 verification at use | S–M | 1.5–2 h | M2 | — |
| 11 | M4 notices (backend) | M | 2–2.5 h | C1, M2 | — |
| 12 | M5 notices (frontend) | M | 2–3 h | M4 | — |
| 13 | D2 progressive dashboard (backend) | L | 4–6 h | D1 | Fast card waits p95 4.4 s for the slowest → 0 |
| 14 | D1 frontend half: synthesis after the cards | S | 0.5–1 h | LIA World committed | 92 % of `/synthesis` find an incomplete bundle → about 0 |
| 15 | D3 progressive dashboard (frontend) | L | 3–5 h | D2, LIA World committed | — |
| 16 | S1 safe retries on Google, Microsoft and Apple, with provider idempotency and the Drive per-call budget (optional) | M | 2.5–3.5 h | — | Proven by simulation: 1 POST → 3 events (Google); same mechanism in Microsoft and Apple; 0 on a write in 7 days → 1 event |
| 17 | S2 LLM client retries after an unknown outcome (E2) | S–M | 2–3 h | Q3 answered | Timeout → 3 requests (Gemini: 6 on 429 or 5xx, 34 s) → per Q3 |
| 18 | O2 client timings and panels | S–M | 1.5–2 h | O1, D3 | — |
| 19 | Q docs, FAQ, ADRs, final qualification | M | 3–4 h | all | — |

Total: about 42–61 h of my work, plus W1b (optional, 1.5–2 h, decided after W1's measurement) and
Q4 (an owner trade-off, no lot unless chosen). N1 (network re-measurement) is done: 968 DNS
timeouts in 7 days, 17 % of the slow MCP connections (spec §0ter H9). Its two levers stay with the
owner. The 2026-10-28 state-of-the-art review (spec §0quater) changed M1, M1b, M2, M6, D1, D2, S1
and S2; it confirmed A1, A3, C1 and W1.

## Review Focus

1. **A server renamed or edited between two turns.** Aliases and prefixes come from the current
   rows; a snapshot whose configuration fingerprint no longer matches is a miss. M2 adds
   `test_renamed_server_keeps_prefix_from_current_row`.
2. **An OAuth token expired while the catalogue is hydrated without network.** The first call runs
   the existing refresh flow and its failure becomes `AUTH_REQUIRED`, never a silent empty
   catalogue. M2 adds `test_hydrated_oauth_server_refreshes_on_first_call`.
3. **A server at `mcp_max_tools_per_server` with large schemas.** The snapshot parses once per
   worker per fingerprint, and the turn cost does not grow with the number of turns. M2 adds
   `test_snapshot_parsed_once_per_fingerprint`.
4. **Local midnight or a DST change between the initial request and a section request.** The act's
   context digest changes and the client restarts cleanly. D2 adds
   `test_section_request_after_local_midnight_is_409`.
5. **Reconnection and replay after a « slow » notice.** The toast is not raised again once its
   terminal phase was seen. M5 adds the vitest `does not re-raise a settled server notice on
   replay`.

---

### Task P0: Baseline and harness

**Files:** none modified. Artefacts go to `.tmp/latency-20261021/` (gitignored); never credentials
or message content.

- [ ] **Step 1: Snapshot the working tree of the files this plan touches.** Run
  `git status --short` and `git diff --stat` on each path listed in the tasks. Save the SHA-256 of
  each file to `baseline-files.txt` so concurrent edits are visible before each lot.
- [ ] **Step 2: Run the sentinel suites.**
  - Command, from `apps/api/`:
    `.venv/Scripts/pytest tests/unit/domains/briefing tests/unit/infrastructure/mcp tests/unit/domains/user_mcp/test_user_context.py tests/unit/infrastructure/utils/test_shared_flight.py tests/unit/infrastructure/utils/test_single_flight.py -q --no-cov`.
  - Expected: all pass. Record the counts, skips and duration.
- [ ] **Step 3: Run `task test:backend:agents`.** Expected: green, counts recorded.
- [ ] **Step 4: Runtime baseline in Docker dev, on the proof account.**
  - Configure 2 personal MCP servers on the proof account, one of them a local stub that sleeps
    before answering `list_tools`.
  - Record, cold and warm: `user_mcp_session_ready` delay from `new_service_architecture_starting`,
    `ttft` and `first_answer_token_ms` from the logs.
  - For the dashboard: `briefing_cards_built` count and `duration_ms` per load (cold, warm, one
    failing section).
  - Write medians with sample sizes to `baseline.md`.
- [x] **Step 4b: Production re-measurement, read-only — done on 2026-10-28** (spec §0ter; scripts
  and hashed outputs in `.tmp/latency-20261028/`). Re-run the same scripts after deployment to
  measure each gain in production with the same instruments.
- [ ] **Step 5: Measure CC and SLOC of every function and file in spec §6.5** and keep them as the
  « before » of each lot.

### Task O1: Journey metrics in the backend (before the changes, to measure them)

**Files:**
- Modify:
  - `apps/api/src/infrastructure/observability/metrics_agents.py` — add
    `chat_journey_first_token_seconds` (buckets 0.25 … 300) and
    `chat_journey_unanswered_seconds{outcome}`.
  - `apps/api/src/domains/agents/services/streaming/latency_sli.py` — two new door functions.
  - `apps/api/src/domains/agents/services/streaming/journey_timing.py` — observe at the first
    answer token; `close(outcome)`.
  - `apps/api/src/domains/agents/api/service.py` — call `close` in the two existing `finally`
    blocks, around `:1550` and `:1582`; at most 4 lines.
  - `infrastructure/observability/grafana/dashboards/01-app-overview.json` — journey p50/p95 panel
    and unanswered-by-outcome panel.
- Test: `apps/api/tests/unit/domains/agents/services/streaming/test_journey_sli.py`.

**Interfaces:**
- Produces:
  - `observe_journey_first_token(seconds: float) -> None`.
  - `observe_journey_unanswered(outcome: Literal["cancelled", "error", "interrupted"], seconds: float) -> None`.
  - `JourneyTiming.close(outcome: Literal["answered", "cancelled", "error", "interrupted"]) -> None`,
    idempotent.
  - All observations are gated by `a_person_is_waiting()`.

- [ ] **Step 1: Write the failing tests.** They must fail on the missing functions.
  - `test_first_answer_token_observed_once`: two token chunks give one observation, with a value
    equal to the injected clock difference.
  - `test_unanswered_cancel_observed_with_outcome`: `close("cancelled")` before any token gives one
    observation labelled `cancelled`.
  - `test_nothing_observed_when_nobody_waits`: inside `awaited_by_a_person(False)`, zero
    observations.
  - `test_progress_chunk_is_not_a_first_token`: an `execution_step` chunk gives no observation.
- [ ] **Step 2: Implement the door functions and `JourneyTiming.close`.** Wire `close` in the two
  `finally` blocks.
- [ ] **Step 3: Run the tests.** `.venv/Scripts/pytest tests/unit/domains/agents/services/streaming -q --no-cov`
  must pass, and `task test:backend:agents` must be green.
- [ ] **Step 4: Run `.venv/Scripts/pytest tests/unit/test_metric_coverage_ratchet_guard.py --no-cov`.**
  Expected: green, with the baseline unchanged.
- [ ] **Step 5: Record the lot's files and run the exhaustive review.**

### Task D1: Dashboard — stop re-collecting

**Files:**
- Create: `apps/api/src/domains/briefing/section_outcomes.py` — the post-read persistence extracted
  from `_section`: cache write, last-good write, stale attach, attempt marker.
- Modify:
  - `apps/api/src/domains/briefing/service.py` — `_section` delegates; SLOC must go **down** from
    598.
  - `cache_keys.py` — `attempt_marker_key`.
  - `cached_cards.py` — completeness readers see markers.
  - `cache_state.py` — classify by provenance.
  - `constants.py`, `apps/api/src/core/config/briefing.py`, `apps/api/src/core/constants.py` — the
    two `BRIEFING_*` settings of this lot.
  - `apps/api/src/infrastructure/utils/shared_flight.py` — opt-in owner liveness, polling
    backoff, and one re-claim when the owner releases without a published result (E12).
  - `apps/api/src/domains/briefing/llm.py` and `sms_context.py` — the text build reads SMS once,
    with messages, and serves both prompts from that read (E13). The SMS signal check
    (`sms_signal_current`) stays per prompt.
  - The lease fence (E5; Facebook memcache leases, spec §0quater):
    - `apps/api/src/domains/push_channels/cache_invalidation.py` bumps a per-section generation
      key next to its delete;
    - `section_outcomes.py` reads the generation before the live fetch and writes the section only
      if it is unchanged, in one Redis script;
    - a push that lands during a read therefore leaves the section missing, never stale.
    - The generation key joins the `briefing:v2` family. A Redis failure falls back to today's
      write, which is the floor.
  - `apps/web/src/hooks/useBriefing.ts` — the text read is enabled once the cards settle, and
    `refetchAll` reads the cards then the text.
  - The six `.env*` files.
- Test:
  - `apps/api/tests/unit/domains/briefing/test_attempt_markers.py`;
  - `apps/api/tests/unit/infrastructure/utils/test_shared_flight_liveness.py`;
  - `apps/api/tests/integration/infrastructure/test_shared_flight_two_processes.py` (`integration`
    marker);
  - `apps/web/src/hooks/__tests__/useBriefing.sequencing.test.tsx`.

**Interfaces:**
- Produces:
  - `attempt_marker_key(*, user_id: UUID | str, language: str, section: str) -> str`, under the
    `briefing:v2` family (it follows that family by longest-prefix matching, so no new family).
  - `run_shared_flight(key, *, build, read_shared, wait_budget_s, claim_ttl_s=CLAIM_TTL_SECONDS, owner_liveness: bool = False) -> SharedFlightResult[T]`.
    With liveness, the owner runs `build` inside `held_claim` and the waiter builds only when the
    claim key is gone without a result, or after `wait_budget_s`.
  - `classify_cache_state(outcomes: Iterable[tuple[CardSection, bool]]) -> str`, which reads
    `section.from_cache` and no longer takes a clock.

- [ ] **Step 1: Write the failing backend tests.**
  - `test_failed_live_read_writes_attempt_marker`: the marker holds the ERROR section with its
    stale copy, and its TTL equals the setting.
  - `test_completeness_reader_treats_marker_as_settled`: `cached_cards_bundle` returns no missing
    section for a section that has only a marker.
  - `test_synthesis_does_not_rebuild_after_attempted_failure`: `build_text` with a marker calls
    `build_cards` zero times.
  - `test_cards_route_ignores_marker`: `_section` with only a marker performs one live fetch.
  - `test_success_deletes_marker`.
  - `test_live_build_slower_than_old_threshold_is_cold`: a fetch of 2 s with `from_cache=False`
    gives `cold`.
- [ ] **Step 2: Write the failing liveness tests** (fake Redis with claim semantics).
  - `test_waiter_keeps_waiting_while_owner_holds_claim`: the owner is blocked on an event past the
    old 10 s budget (injected clock); the waiter receives the published result and `build` is
    called once.
  - `test_waiter_builds_when_claim_disappears`: the owner dies (claim deleted, no result) and the
    waiter builds once.
  - `test_owner_claim_is_renewed_during_build`: the claim TTL is refreshed at least once during a
    build longer than the TTL.
  - `test_poll_interval_backs_off_to_cap`: the observed sleeps grow from 0.02 to 0.25 and stay
    there.
  - `test_default_mode_unchanged`: the existing `test_shared_flight.py` stays green, unmodified.
  - `test_release_without_result_is_reclaimed_by_one_waiter` (E12, spec D11).
    - Three waiters; the owner releases while one section is missing.
    - Exactly one waiter claims again and builds; the two others receive its result.
    - `build` is called twice in total, not four times.
- [ ] **Step 2a: Write the failing fence tests** (E5).
  - `test_push_during_read_drops_the_write`: generation bumped between read and write gives no
    cache write; the section stays missing; the next read is live.
  - `test_write_without_push_commits`.
  - `test_redis_down_writes_as_today`.
- [ ] **Step 2b: Write the failing SMS test** (E13, spec D12).
  - `test_text_build_reads_sms_once`: one live SMS read for the greeting and the synthesis
    together.
  - `test_sms_revoked_between_prompts_drops_text`: the D10 consent behaviour is kept.
- [ ] **Step 2c: Port the 2026-10-28 simulation into the integration test.**
  - Source: `.tmp/latency-20261028/sim_shared_flight.py`, with four processes, the real service and
    real Redis base 15.
  - Its three scenarios become the assertions of
    `test_shared_flight_two_processes.py`:
    - nominal: the waiters finish within 0.5 s of the owner;
    - one failed section: one read of it in total, no 10 s wait;
    - mails invalidated by a push at the owner's end: one extra mail read, no 10 s wait.
- [ ] **Step 3: Write the failing frontend tests — frontend half, executed only once the staged
  « LIA World » lot is committed** (it rewrites this hook: `useBriefing(enabled)`, `autoFetch: false`
  on the text query, `textUnavailable`). The initial text read at `useBriefing.ts:114-127` becomes
  « after the cards settle ».
  - `synthesis read starts only after the cards read resolves`: request order with fake
    `apiClient`.
  - `synthesis read still runs after a cards error`.
  - `refetchAll reads cards then text`.
  - The existing SMS barrier and invalidation tests stay green.
- [ ] **Step 4: Implement.**
  - Extract `section_outcomes.py` first and re-run the existing briefing suite green before adding
    the marker.
  - `BriefingService._gather_once_per_deployment` passes `owner_liveness=True` and
    `wait_budget_s=settings.briefing_shared_build_max_wait_seconds`.
  - The three other callers of `run_shared_flight` stay untouched.
- [ ] **Step 5: Run the tests.**
  - `.venv/Scripts/pytest tests/unit/domains/briefing tests/unit/infrastructure/utils -q --no-cov`.
  - `.venv/Scripts/pytest tests/integration/infrastructure/test_shared_flight_two_processes.py -m integration --no-cov`.
  - `task test:frontend`.
  - Expected: all pass.
- [ ] **Step 6: Run the ratchets.** `measure_cc.py --check-ratchet` and the file-size guard must be
  green, and the `briefing/service.py` SLOC must be lower than 598.
- [ ] **Step 7: Runtime proof in Docker dev.**
  - One cold load gives exactly one `briefing_cards_built` and one live read per section.
  - With an induced failure on one section, `/synthesis` triggers no second read.
  - One page load records one `briefing:sms` read for the text build instead of two.
  - Record the lot's files and run the exhaustive review.

### Task W1: Weather and environment clients — one connection setup per host per card

**Files:**
- Modify:
  - `apps/api/src/domains/connectors/clients/google_weather_client.py` — a lazy per-instance
    `httpx.AsyncClient` with the same timeout, limits and `source_http_hooks(self.user_id)`;
    `close()` closes it.
  - `apps/api/src/domains/connectors/clients/google_environment_client.py` — the same.
  - `apps/api/src/domains/agents/tools/weather_environment_enrichment.py` — close the environment
    client in `finally`.
  - `apps/api/src/domains/briefing/fetchers.py` — run the extras inside the existing `gather`,
    wrapped so that a failure still yields `None`.
- Test: `apps/api/tests/unit/domains/connectors/clients/test_weather_client_pooling.py`;
  `apps/api/tests/unit/domains/briefing/test_weather_environment_enrichment.py` (extend).

- [ ] **Step 1: Write the failing tests.**
  - `test_one_http_client_per_instance_across_pages`: current conditions plus five forecast pages
    construct `httpx.AsyncClient` once (patched constructor counter).
  - `test_close_releases_and_next_use_reopens`.
  - `test_hooks_bound_to_instance_owner`: the read-budget claim is charged to the instance's
    account.
  - `test_extras_start_before_weather_finishes`: the extras are held on an event while the weather
    calls start.
  - `test_extras_failure_keeps_weather_card`.
- [ ] **Step 2: Implement.** Check that every owner listed in spec §2.4 still closes its client: the
  briefing fetcher, the heartbeat aggregator, discussion weather, and `ToolDependencies.aclose`.
- [ ] **Step 3: Run the tests.**
  `.venv/Scripts/pytest tests/unit/domains/connectors tests/unit/domains/briefing -q --no-cov`
  passes, with no `ResourceWarning` and no unclosed transport in the output.
- [ ] **Step 4: Runtime proof.** On a cold load in Docker dev, the weather `duration_ms` before and
  after, with sample sizes. Record the lot's files and run the exhaustive review.

### Task W1b (optional, after W1's measurement): daily forecast in one call

**Facts.**
- Google Weather caps `forecast.hours.lookup` at 24 records per page. The card asks for 120 h, so
  it pays 5 sequential billed pages.
- `forecast.days.lookup` returns up to 10 days in one page (official reference, spec §0quater).
- The card shows 5 daily summaries (min, max, precipitation) and a 24 h alert horizon
  (`briefing/formatters.py:85-106`).

**Proposal.**
- Read the 5 daily summaries from 1 daily call, plus 1 hourly page for the 24 h alert.
- This takes 8 → 5 billed requests per live read (−37 %). The forecast becomes 2 parallel requests
  instead of 5 sequential ones.

**What it costs.**
- The weather clients are deliberately OpenWeatherMap-shaped (`fetchers.py`: both providers are
  normalised to one shape).
- A provider-native daily path is a second shape, so the OpenWeatherMap path must keep producing the
  same card, guarded by a parity test.
- The daily minimum and maximum would come from the provider instead of LIA's aggregation of
  3-hour slots, so the displayed values can differ.

Decided after W1 has been measured: if W1 already brings the card near 1.2 s, the gain left is the
billing (3 requests per read).

### Task C1: Chat turn — commit and archive before the MCP preparation

**Files:**
- Create: `apps/api/src/domains/agents/api/turn_preparation.py` — the state load, attachments
  injection and archive-first extracted from `_stream_with_new_services`.
- Modify: `apps/api/src/domains/agents/api/service.py` — the new order: setup reads, state,
  attachments, archive-first, message count, `await db.commit()`, MCP preparation (still sequential
  in this lot), turn catalogue, streaming setup, the existing commit, graph.
  - Pre-graph phase observations through `observe_pre_graph_phase`, a door added to
    `latency_sli.py` with `chat_pre_graph_phase_seconds{phase}` and a panel in dashboard 01.
- Test:
  - `apps/api/tests/agents/test_agent_service_stream_characterization.py` — update patch targets
    only if a symbol moved;
  - `apps/api/tests/unit/domains/agents/api/test_turn_preparation_order.py`.

**Interfaces:**
- Produces:
  - `TurnStateRequest`, a frozen dataclass of today's `load_or_create_state` and archive arguments.
  - `async def prepare_turn_state(request: TurnStateRequest, *, db: AsyncSession, orchestration_service: OrchestrationService, conv_service: ConversationService) -> PreparedTurnState`
    with `state` and `archived_user_msg_id`. It raises `HitlDecisionStaleError` as today.
  - `observe_pre_graph_phase(phase: Literal["conversation", "state", "archive", "mcp", "catalogue"], seconds: float) -> None`.

- [ ] **Step 1: Write the failing tests.**
  - `test_archive_first_precedes_mcp_preparation`: in the call order recorded on fakes,
    `archive_message` comes before `setup_user_mcp_tools`.
  - `test_setup_transaction_committed_before_mcp_preparation`: `db.commit` is awaited before the
    first MCP await.
  - `test_stale_hitl_decision_skips_mcp_preparation`: `setup_user_mcp_tools` is never called and
    the stale chunks are emitted.
  - `test_archive_happens_once_on_hitl_resumption`.
- [ ] **Step 2: Implement the extraction, then the re-order.** `setup_user_mcp_tools` keeps its
  signature and its module path, so the characterization patch target stays valid.
- [ ] **Step 3: Run the tests.**
  - `grep -rn "patch(\"src.domains.agents.api" apps/api/tests/agents/`, and update any patch whose
    symbol moved.
  - `task test:backend:agents` and
    `.venv/Scripts/pytest tests/unit/domains/agents/api -q --no-cov` must pass.
- [ ] **Step 4: Run the ratchets.** The CC of `_stream_with_new_services` must be strictly lower
  than 66, the `service.py` SLOC strictly lower than 978, and `measure_cc.py --check-ratchet` green.
- [ ] **Step 5: Runtime proof in Docker dev (tests X1 and R18).**
  - With the stub MCP server sleeping 20 s, query `pg_stat_activity` (`state`, `xact_start`) during
    the wait: no backend of the turn may be `idle in transaction`.
  - R18:
    - set `DATABASE_IDLE_IN_TRANSACTION_TIMEOUT_MS=5000` on dev for the proof only, with the stub
      sleeping 10 s;
    - before the change, the turn fails on its first statement after the preparation, and
      `db_bound_reached_total{bound="idle_in_transaction_timeout"}` increments;
    - after it, the turn answers and the counter stays still;
    - restore the dev value afterwards.
  - The person's message appears in another tab before the reply starts.
  - Record the lot's files and run the exhaustive review.

### Task M6: Tool embeddings off the critical path (E11, with E8)

**Measured (spec §0ter H5).**
- 31 recomputes in 7 days, 131 s on the turn's critical path, 1.4–16.4 s each, always
  `catalogue_changed`.
- One 6-tool server whose tool count never changed recomputed on 21 of its 46 discoveries.
- Cause: the envelope's fingerprint is `canonical_fingerprint(tools)` over the **ordered** list, so
  any reordering or any one changed tool invalidates every vector.
- Telling order from content apart would mean contacting the person's server. The fix covers both.

**Files:**
- Modify:
  - `apps/api/src/domains/agents/services/tool_embeddings_envelope.py`:
    - per-tool identity `tool_identity(tool) -> str`, the hash of the **exact text LIA embeds** for
      the tool, under the embedding model key. This is LangChain `CacheBackedEmbeddings`' keying
      (spec §0quater): a change in how LIA composes that text invalidates the vector too;
    - an order-insensitive catalogue fingerprint;
    - `reusable_vectors(envelope, tools) -> (kept, missing)`.
  - `apps/api/src/infrastructure/mcp/user_context.py` (`_usable_tool_embeddings`, `:110-145`).
    - It embeds only the missing tools, under the existing gates (E8: `spend_blocked` and the
      account ceiling, as the out-of-turn paths do).
    - It writes a new envelope (a new dict).
    - Past `MCP_USER_EMBEDDING_INLINE_MAX_TOOLS` missing tools, it serves the turn with the kept
      vectors and finishes in the background, under a claim. A tool without a vector stays offered
      exactly as on today's failure path (`return {}`), so nothing is withdrawn from the model.
  - `apps/api/src/domains/agents/services/tool_vectors.py` (`ServerVectorCache`, `:160`) — the
    process key uses the order-insensitive fingerprint.
  - Settings surfaces for `MCP_USER_EMBEDDING_INLINE_MAX_TOOLS` (default 8). Every surface of the
    Global Constraints applies.
- Test:
  - `apps/api/tests/unit/domains/agents/services/test_tool_embeddings_envelope.py` (extend);
  - `apps/api/tests/unit/infrastructure/mcp/test_usable_tool_embeddings.py`.

- [ ] **Step 0: Check that a tool without a vector stays offered.** Read how the ReAct selector
  (ADR-293) and the planner catalogue treat it. If a missing vector can drop a tool, the background
  path is not taken: the lot keeps the incremental on-path computation only, and says so.
- [ ] **Step 1: Write the failing tests** (spec M12).
  - `test_reordered_catalogue_reuses_every_vector`: zero embedding calls.
  - `test_one_changed_tool_embeds_one`: one call, carrying one text.
  - `test_new_tools_beyond_inline_cap_served_without_waiting`: the turn returns at once, and one
    background job embeds the rest.
  - `test_spend_blocked_keeps_previous_vectors`: zero calls, and the previous vectors are served
    (E8).
  - `test_envelope_written_as_new_dict`.
  - `test_legacy_envelope_recomputed_once`: the first read after deployment recomputes once, then
    hits.
- [ ] **Step 2: Implement, then run the tests.**
  `.venv/Scripts/pytest tests/unit/domains/agents/services tests/unit/infrastructure/mcp -q --no-cov`
  passes, and the CC and file-size checks are green.
- [ ] **Step 3: Runtime proof in Docker dev.** On the proof account, a stub server returns its tools
  in a random order: zero recomputes over 10 cold discoveries. Then one tool description changes:
  one embedding text.
- [ ] **Step 4: Record the lot's files and run the exhaustive review.**

### Task M1: Personal MCP catalogue snapshot

**Files:**
- Create:
  - `apps/api/src/infrastructure/mcp/catalogue_snapshot.py`
  - `apps/api/src/domains/user_mcp/catalogue_publication.py` — the CAS writer, plus
    `test_connection`'s update-data building moved out of `service.py`.
- Modify:
  - `apps/api/src/domains/user_mcp/service.py` — must shrink from 596 SLOC.
  - `apps/api/src/domains/user_mcp/projection.py` and `generate_description` — read through the
    parser.
  - `apps/api/src/infrastructure/mcp/user_catalogue.py` — sources `stored+snapshot | snapshot`,
    wording « Declared capabilities: ».
  - `apps/api/src/domains/user_mcp/models.py` — the column docstrings now state what they hold.
- Test:
  - `apps/api/tests/unit/infrastructure/mcp/test_catalogue_snapshot.py`
  - `apps/api/tests/unit/domains/user_mcp/test_catalogue_publication.py`
  - `apps/api/tests/integration/domains/user_mcp/test_catalogue_jsonb_roundtrip.py`

**Interfaces:**
- Produces:
  - `CatalogueSnapshot`, frozen: `version: Literal[2]`, `discovered_at: datetime` (UTC),
    `configuration_fingerprint: str`, `catalogue_fingerprint: str`,
    `tools: tuple[Mapping[str, JsonValue], ...]`, `reference_content: str | None` (≤ 50 000 chars),
    `generation: int` (monotonic, reserved before the discovery starts),
    `server_ttl_ms: int | None` and `cache_scope: Literal["public", "private"] | None` (MCP
    2026-07-28 caching hints, `None` from a legacy server), and
    `server_instructions: str | None` (from the handshake, bounded like the reference).
  - **State of the art applied (spec §0quater):**
    - `tools` are stored in canonical order (sorted by name). The MCP spec asks servers for a
      deterministic order because clients cache the list and LLM prompt caches depend on it.
    - The revalidation horizon is `server_ttl_ms` when the server gives one, and
      `MCP_USER_CATALOGUE_REVALIDATE_AFTER_SECONDS` otherwise.
    - A `private` list is keyed by its authorization context. The spec says such a cache *« MUST NOT
      be shared across authorization contexts »*, so a changed grant or account is a miss.
    - Discovery follows `nextCursor` (MCP: *« clients MUST NOT assume a fixed page size »*). Like the
      OpenAI Agents SDK and langchain-mcp-adapters, it guards against a repeated cursor and caps the
      pages; it stops at `mcp_max_tools_per_server` and logs the truncation. This fixes E7.
  - `parse_catalogue_snapshot(raw: object) -> CatalogueSnapshotRead`, where
    `CatalogueSnapshotRead = ValidSnapshot | LegacySnapshot | InvalidSnapshot` and the first two
    expose `.tools`.
  - `snapshot_to_jsonb(snapshot: CatalogueSnapshot) -> dict[str, JsonValue]`.
  - `snapshot_routes(read: CatalogueSnapshotRead, *, configuration_fingerprint: str) -> bool`.
  - `async def publish_catalogue_if_current(*, user_id: UUID, server_id: UUID, snapshot: CatalogueSnapshot, tool_embeddings: Mapping[str, JsonValue] | None) -> PublicationOutcome`,
    where `PublicationOutcome = Literal["published", "configuration_changed", "inactive", "missing"]`.
    It locks the row in a short session, recomputes `connection_fingerprint` from the row, and
    writes a new dict.

- [ ] **Step 1: Write the failing tests.**
  - `test_parse_matrix`:
    - `None` → `InvalidSnapshot`;
    - a legacy list → `LegacySnapshot` with its tools;
    - a legacy dict → `LegacySnapshot`;
    - a valid v2 → `ValidSnapshot`;
    - version 3 → `InvalidSnapshot`;
    - malformed tools → `InvalidSnapshot`;
    - more than `mcp_max_tools_per_server` tools → `InvalidSnapshot`.
  - `test_roundtrip_every_field`: `parse(snapshot_to_jsonb(s)) == s`, over every field.
  - `test_snapshot_routes_only_when_fingerprint_matches`.
  - `test_legacy_never_routes`.
  - `test_publication_refused_after_url_edit` (integration, real PostgreSQL).
  - `test_publication_refused_when_inactive`.
  - `test_test_connection_writes_v2_envelope`.
  - `test_projection_reads_legacy_and_v2`.
  - `test_snapshot_source_and_wording`: `describe_user_server` on a snapshot returns a `snapshot`
    source and « Declared capabilities: ».
  - `test_tools_stored_in_canonical_order`: two discoveries returning the same tools in different
    orders give the same `catalogue_fingerprint`.
  - `test_older_generation_never_overwrites_newer` (integration): a discovery reserved first and
    published last is refused (LibreChat's monotonic ticket, the MCP SDK's generation bump).
  - `test_server_ttl_drives_revalidation_horizon`, `test_legacy_server_uses_setting`.
  - `test_private_scope_keyed_by_authorization_context`.
  - `test_discovery_follows_cursor_with_guards`: three pages, a repeated cursor, the page cap, and
    the per-server cap, each with its own outcome.
- [ ] **Step 2: Implement the parser, the writer and the readers.** Run the existing
  `tests/unit/infrastructure/mcp` and `tests/unit/domains/user_mcp` suites green.
- [ ] **Step 3: Run the tests.**
  - `.venv/Scripts/pytest tests/unit/infrastructure/mcp tests/unit/domains/user_mcp -q --no-cov`.
  - `.venv/Scripts/pytest tests/integration/domains/user_mcp/test_catalogue_jsonb_roundtrip.py -m integration --no-cov`.
  - Expected: all pass.
- [ ] **Step 4: Run the ratchets** (`user_mcp/service.py` SLOC < 596), then record the lot's files
  and run the exhaustive review.

### Task M1b: `read_me` at real use (spec A15, §5.5b; fixes E9 and E10)

**Files:**
- Create: `apps/api/src/infrastructure/mcp/reference_content.py` — the async collector for the
  planner, the bounded fetch and the publication into the snapshot.
- Modify:
  - `apps/api/src/infrastructure/mcp/user_pool.py` — `_discover_tools` stops calling `read_me`
    (CC must go down from 17); `fetch_reference(user_id, server_id, timeout_seconds)` uses one
    ephemeral session.
  - `apps/api/src/infrastructure/mcp/user_context.py` — a standard server's `read_me` is registered
    with `execution_modes={"react"}` instead of being dropped.
  - `apps/api/src/domains/agents/services/planner/mcp_reference.py` — user references resolved
    through `ctx.server_domains` and the collector; the admin path is unchanged.
  - The planner call site of `build_mcp_reference` — awaits the collector before building.
  - `apps/api/src/infrastructure/observability/metrics_mcp.py` —
    `mcp_user_reference_fetches_total{outcome}`, with its panel in the MCP Grafana dashboard.
  - The server's `instructions` from the MCP handshake (the protocol's own channel for guidance;
    VS Code caches it too) follow the same path as the reference.
    - They are captured at discovery, which costs no extra round trip, unlike `read_me`.
    - They are stored in the snapshot (M1) and injected only for a selected server's domain.
    - Step 0 checks that the installed `mcp` 2.2.0 `Client` exposes them after its dual-era
      handshake. If it does not, this item is dropped and the reason recorded.
- Test:
  - `apps/api/tests/unit/infrastructure/mcp/test_reference_content.py`
  - `apps/api/tests/unit/domains/agents/services/planner/test_mcp_reference_exact_domains.py`

**Interfaces:**
- Consumes (from M1): `CatalogueSnapshot.has_reference_tool`, `reference_content`,
  `reference_fetched_at`, `publish_catalogue_if_current`.
- Produces: `async def collect_user_references(selected_domains: Sequence[str], *, now: datetime) -> dict[str, str]`,
  keyed by server name, iterative servers excluded. It never raises: a failed fetch yields no entry
  and is counted in `mcp_user_reference_fetches_total{outcome}`.

- [ ] **Step 1: Write the failing tests** (M10, M11).
  - `test_discovery_never_calls_read_me`: `list_tools` only, zero `call_tool`.
  - `test_reference_fetched_once_when_domain_selected`.
  - `test_reference_not_fetched_when_domain_not_selected`.
  - `test_aged_reference_served_then_refreshed`.
  - `test_fetch_failure_plans_without_reference`.
  - `test_react_catalogue_offers_read_me_pipeline_does_not`.
  - `test_reference_found_for_slugified_names`: « My Notion », « GitHub-Perso », a `_2` collision.
  - `test_iterative_server_unchanged`.
- [ ] **Step 2: Implement.** Check first, at the manifest builder, that `build_mcp_tool_manifest`
  accepts `execution_modes`. If it does not, extend its signature in the same lot, typed and with
  every existing caller passing the current default.
- [ ] **Step 3: Run the tests.**
  - `.venv/Scripts/pytest tests/unit/infrastructure/mcp tests/unit/domains/agents/services/planner -q --no-cov`.
  - `task test:backend:agents`.
  - `measure_cc.py --check-ratchet`: `_discover_tools` must be lower than 17 and the ratchet green.
- [ ] **Step 4: Runtime proof in Docker dev** with a proof-account server exposing `read_me`.
  - A pipeline turn about that server injects the reference after one fetch; a second turn does not
    fetch again.
  - A ReAct turn can call `read_me`.
  - Record the lot's files and run the exhaustive review.

### Task M2: Parallel preparation, hydration, ceiling and background revalidation

**Files:**
- Create:
  - `apps/api/src/infrastructure/mcp/user_preparation.py`
  - `apps/api/src/infrastructure/mcp/catalogue_revalidation.py`
- Modify:
  - `apps/api/src/infrastructure/mcp/user_context.py`:
    - `setup_user_mcp_tools` delegates to `prepare_user_servers` and assembles in the parent;
    - `_usable_tool_embeddings` is reused as M6 left it (incremental, gated, off the critical path).
  - `apps/api/src/infrastructure/mcp/user_pool.py`:
    - `hydrate`;
    - a semaphore attribute;
    - `catalogue_verified` on `PoolEntry`;
    - the dedicated discovery timeout in `get_or_connect`.
  - Config and constants: `apps/api/src/core/config/mcp.py` and `apps/api/src/core/constants.py`
    get the five `MCP_USER_*` settings, and the `MCP_USER_POOL_TTL_SECONDS` comment is corrected to
    idle eviction. The six env files are updated.
  - `apps/api/src/infrastructure/cache/key_families.py` — `mcp:catalogue` (`USER_RUNTIME`).
  - Metrics: `apps/api/src/infrastructure/observability/metrics_mcp.py` gets
    `mcp_user_server_preparation_seconds{source,outcome}` and
    `mcp_user_catalogue_revalidations_total{outcome}`, each with a panel in the MCP Grafana
    dashboard.
- Test:
  - `apps/api/tests/unit/infrastructure/mcp/test_user_preparation.py`
  - `apps/api/tests/unit/infrastructure/mcp/test_catalogue_revalidation.py`
  - `apps/api/tests/integration/infrastructure/mcp/test_revalidation_claim.py`
  - `apps/api/tests/unit/domains/user_mcp/test_user_context.py` — kept green, with its patch
    targets unchanged.

**Interfaces:**
- Consumes (from M1): `parse_catalogue_snapshot`, `snapshot_routes`, `publish_catalogue_if_current`.
- Produces:
  - `PreparationEvent`, frozen: `server_id: UUID`, `server_name: str`,
    `phase: Literal["queued", "discovering", "embeddings", "ready", "failed", "timed_out", "slow"]`,
    `elapsed_s: float`.
  - `ServerPreparation`, frozen: `server_id: UUID`,
    `outcome: Literal["ready", "paused", "failed", "timed_out", "deferred"]`,
    `source: Literal["catalogue", "network"] | None`, `entry: PoolEntry | None`,
    `embeddings: Mapping[str, Any]`, `duration_s: float`.
  - `async def prepare_user_servers(user_id: UUID, servers: Sequence[UserMCPServer], pool: UserMCPClientPool, *, on_event: Callable[[PreparationEvent], None] | None, ceiling_s: float) -> list[ServerPreparation]`,
    in the input order.
  - `UserMCPClientPool.hydrate(*, user_id: UUID, server_id: UUID, url: str, auth: httpx2.Auth, timeout_seconds: int, extra_headers: dict[str, str] | None, snapshot: CatalogueSnapshot, verified: bool) -> PoolEntry`,
    with no I/O.
  - `schedule_catalogue_revalidation(user_id: UUID, server_id: UUID) -> None`: fire-and-forget
    through `safe_fire_and_forget`, claim `mcp:catalogue:revalidate:{user}:{server}`.

- [ ] **Step 1: Write the failing tests** (events, barriers, injected clock — never a duration
  alone).
  - `test_servers_prepared_concurrently` (M3): two servers held on events are both entered before
    either is released.
  - `test_semaphore_bounds_network_preparations` (M3): five cold servers show at most four entered
    at once.
  - `test_one_failure_keeps_other_servers` (M3).
  - `test_warm_catalogue_needs_no_network` (M4): a valid snapshot gives zero `_discover_tools`
    calls and manifests identical to a discovered run, in order and fingerprint.
  - `test_aged_snapshot_served_and_revalidation_scheduled` (Q1).
  - `test_paused_server_not_offered`.
  - `test_ceiling_continues_without_cold_server` (Q2 answered (a)): the outcome is `deferred`, the
    child keeps running and publishes afterwards, and the next turn hydrates it.
  - `test_discovery_timeout_is_dedicated`: a server with a 120 s tool timeout is bounded by 15 s at
    discovery.
  - `test_child_never_sets_contextvar`: after preparation, `user_mcp_tools_ctx` is set only by the
    parent.
  - The embedding gate tests live in M6 (`test_spend_blocked_keeps_previous_vectors`).
  - `test_revalidation_single_flight_across_workers` (integration, Redis): two schedulers give one
    discovery.
  - `test_revalidation_refused_after_edit` (integration, PostgreSQL).
  - `test_late_older_revalidation_never_overwrites_newer` (integration).
    - Two revalidations reserve generations 7 and 8.
    - Generation 7 finishes last and is refused.
    - This is the stale-publication fence of LibreChat and of the MCP SDK cache (spec §0quater).
  - `test_failures_isolated_not_gathered`: a raising server does not cancel its siblings.
    langchain-mcp-adapters' bare `gather` is the counter-example.
  - `test_evicted_entry_rehydrated` (M9).
  - Review Focus 1–3.
- [ ] **Step 2: Implement** the semaphore, the children, the parent assembly in server-name order,
  hydration, revalidation and the metrics.
- [ ] **Step 3: Run the tests.**
  - `.venv/Scripts/pytest tests/unit/infrastructure/mcp tests/unit/domains/user_mcp -q --no-cov`.
  - The integration files, with `-m integration --no-cov`.
  - `task test:backend:agents`.
  - Expected: all pass.
- [ ] **Step 4: Runtime proof in Docker dev.**
  - A warm turn logs no `user_mcp_pool_connected` and preparation `source="catalogue"`.
  - A cold turn with the slow stub is bounded by the ceiling.
  - `pg_stat_activity` shows no transaction held during preparation.
  - Record the lot's files and run the exhaustive review.

### Task M3: Verification at use

**Files:**
- Modify:
  - `apps/api/src/infrastructure/mcp/user_pool.py` — `call_tool` verifies inside the same ephemeral
    session when `entry.catalogue_verified` is false.
  - `apps/api/src/infrastructure/mcp/rate_limit.py`, next to `MCPToolExecutionError` —
    `MCPDeclarationChangedError(reason: Literal["changed", "missing"])`.
  - `apps/api/src/infrastructure/mcp/user_tool_adapter.py` — map it to
    `UnifiedToolOutput.failure(error_code="CONFLICT", metadata={"reason": …})`, following the
    `RATE_LIMIT_EXCEEDED` branch at `:415-431`.
  - Metrics: `mcp_user_declaration_checks_total{outcome}`, with a panel.
- Test: `apps/api/tests/unit/infrastructure/mcp/test_declaration_check.py`.

- [ ] **Step 1: Write the failing tests** (M5, M6).
  - `test_verified_entry_calls_without_listing`.
  - `test_unverified_identical_calls_and_marks_verified`.
  - `test_compatible_change_calls_and_schedules_revalidation`: an added optional parameter or a new
    description still sends the call.
  - `test_incompatible_change_refuses_without_calling`: a new required parameter, a removed
    parameter or a changed type gives zero `call_tool` on the session, `CONFLICT` with reason
    `incompatible`, and a revalidation scheduled.
  - `test_newly_destructive_annotation_refuses`: reason `tightened`.
  - `test_missing_tool_refuses`: reason `missing`.
  - `test_react_confirmation_identical_after_hydration` (M6).
- [ ] **Step 2: Implement.**
  - The arguments are validated with `build_args_schema(current_input_schema)`
    (`infrastructure/mcp/tool_adapter.py:112`), never with a direct `jsonschema` import, which is
    only a transitive dependency.
  - The helper `_call_with_declaration_check` keeps `_execute_call_ephemeral` under CC 15.
- [ ] **Step 3: Run the tests** —
  `.venv/Scripts/pytest tests/unit/infrastructure/mcp -q --no-cov` and `task test:backend:agents`
  pass. Then record the lot's files and run the exhaustive review.

### Task M4: Preparation notices (backend)

**Files:**
- Modify:
  - `apps/api/src/domains/agents/api/turn_preparation.py` — add
    `iter_mcp_preparation(user_id, *, run_id, interactive) -> AsyncIterator[ChatStreamChunk | PreparedUserMCP]`.
  - `apps/api/src/domains/agents/api/service.py` — yield its chunks, then install the context.
  - `apps/api/src/domains/agents/api/schemas.py` — `MCPPreparationNotice`, a Pydantic model with a
    `Field` description on every field, validated into the `execution_step` metadata.
- Test: `apps/api/tests/unit/domains/agents/api/test_mcp_preparation_notices.py` and the
  characterization suite.

**Interfaces:**
- Produces: `execution_step` metadata with
  - `step_type="mcp_preparation"`;
  - `i18n_key` ∈ {`chat.progress.preparing_applications`, `chat.mcp_preparation.slow`,
    `chat.mcp_preparation.deferred`, `chat.mcp_preparation.ready`, `chat.mcp_preparation.failed`};
  - `server_key`, `server_name`, `phase`, `elapsed_ms`.

- [ ] **Step 1: Write the failing tests.**
  - `test_warm_turn_emits_no_notice` (N1).
  - `test_slow_notice_emitted_at_threshold_before_graph` (N1, injected clock).
  - `test_terminal_phase_follows_slow` (N1).
  - `test_no_notice_on_channel_routine_phone_or_voice` (N2).
  - `test_notices_never_archived_nor_in_state` (N4).
  - `test_notice_is_not_first_token` (O1).
- [ ] **Step 2: Implement.** The preparation runs as a task; the generator drains its event queue
  and yields; the context is installed after the final result.
- [ ] **Step 3: Run the tests.** `task test:backend:agents` and the unit file pass. Then record the
  lot's files and run the exhaustive review.

### Task M5: Preparation notices (frontend; the « deferred » text follows Q2 (a))

**Files:**
- Create:
  - `apps/web/src/lib/sse-handlers/mcp-preparation.ts`
  - `apps/web/src/lib/sse-handlers/__tests__/mcp-preparation.test.ts`
  - `apps/web/e2e/smoke/chat-mcp-preparation.spec.ts`
- Modify:
  - `apps/web/src/lib/sse-handlers/handlers.ts` — route the `mcp_preparation` subtype;
  - the progress step through the existing accumulator;
  - `apps/web/locales/{en,fr,de,es,it,zh}/translation.json` — keys of M4; `zh` duplicates `_one`
    where plural.

- [ ] **Step 1: Write the failing tests** (N3, N4).
  - `raises one toast per server per run and updates it on its terminal phase`.
  - `does not re-raise a settled server notice on replay` (Review Focus 5).
  - `groups more than three slow servers`.
  - `renders a hostile, long or RTL name as text`.
  - `clears on account switch`.
  - Accessible name and polite announcement in `en` and `fr`.
- [ ] **Step 2: Implement** with `components/ui/toaster.tsx`: no action button, `role="status"`, no
  focus steal.
- [ ] **Step 3: Run the tests.**
  - `task test:frontend`, `task lint:frontend`, `task lint:i18n` and
    `pnpm exec tsc --noEmit --incremental false` (from `apps/web`) pass.
  - Then `task test:e2e -- chat-mcp-preparation` (hermetic, mocked SSE).
- [ ] **Step 4: Visual check in Docker dev** — narrow screen, desktop, 200 % zoom, reduced motion,
  both themes. Record the lot's files and run the exhaustive review.

### Task D2: Progressive dashboard (backend)

**Files:**
- Create:
  - `apps/api/src/domains/briefing/act_token.py`
  - `apps/api/src/domains/briefing/progressive.py`
  - `apps/api/src/domains/briefing/text_cache.py`
  - `apps/api/src/domains/briefing/progressive_router.py`
- Modify:
  - `apps/api/src/domains/briefing/schemas.py` — `CardStatus.PENDING`, `BriefingInitialResponse`,
    `SectionResponse`, `BriefingTextRequest`, `BriefingTextResponse`.
  - `apps/api/src/api/v1/routes.py` — include the router.
  - `apps/api/src/domains/briefing/service.py` — expose one-plan reads through the D1 extraction;
    SLOC stays ≤ the value after D1.
  - Config and env — the two remaining `BRIEFING_*` settings.
- Test:
  - `apps/api/tests/unit/domains/briefing/test_act_token.py`
  - `test_progressive_initial.py`
  - `test_progressive_section.py`
  - `test_text_cache.py`
  - `apps/api/tests/integration/domains/briefing/test_progressive_act_spend.py`

**Interfaces:**
- Produces:
  - `sign_act(*, act_id: str, user_id: UUID, context_digest: str, expires_at: datetime) -> str`.
  - `verify_act(token: str, *, user_id: UUID, context_digest: str, now: datetime) -> ActCheck`,
    where `ActCheck = Literal["valid", "foreign", "expired", "context_changed", "malformed"]`.
    The HMAC uses `settings.secret_key`, following `connectors/media_attribution.py`.
  - `briefing_context_digest(user: User, hidden: frozenset[str], language: str, tz: ZoneInfo, local_day: date) -> str`.
  - Routes, with the contracts of spec §5.8:
    - `GET /briefing/cards/initial`
    - `GET /briefing/sections/{name}`
    - `POST /briefing/text`
    - `POST /briefing/sections/{name}/refresh`
  - `text_fingerprint(projected: str, statuses: Mapping[str, str], windows: BriefingWindows, slot_config_digest: str, prompt_version: str, sms_witness: str | None) -> str`.
- **Request budget** (spec §0quater, on Grafana's per-panel model and its concurrency limit):
  - the initial response carries every cached or local section;
  - only the slow external sources get their own `GET /briefing/sections/{name}`;
  - the client opens at most `BRIEFING_SECTION_CONCURRENCY` (default 4) at a time, so a browser on
    HTTP/1.1 (6 connections per host, one held by the SSE stream) never queues the page.
  - P0 records the protocol the production browser actually uses behind Cloudflare.

- [ ] **Step 1: Write the failing tests** (D4–D8, D10, X2, X3).
  - `test_act_roundtrip_and_tamper`: valid, foreign account, expired, changed context, flipped
    byte.
  - `test_initial_returns_cached_local_and_pending`: no live fetch for a cache miss; nothing
    `not_configured` while pending.
  - `test_section_reads_exactly_one_source`.
  - `test_section_under_act_records_once`: two sections of one act give one decision row
    (`record_decision_once`) and consultations under the act's run id.
  - `test_section_request_after_local_midnight_is_409` (Review Focus 4).
  - `test_text_reads_caches_only`: zero fetchers called.
  - `test_text_generated_once_per_fingerprint`: two concurrent calls give one slot invocation; the
    second answer is `reused`.
  - `test_text_lost_lease_is_uncertain_and_not_relaunched`.
  - `test_text_spend_blocked_returns_fallback_greeting`.
  - `test_sms_witness_change_drops_cached_text`.
  - `test_act_spend_flushes_add_up` (integration, PostgreSQL).
- [ ] **Step 2: Implement.** The routes use `PrivateApplicationInputRoute` and `no-store`;
  authentication holds no transaction across the reads (U1 proof in Step 4).
- [ ] **Step 3: Run the tests.**
  - `.venv/Scripts/pytest tests/unit/domains/briefing -q --no-cov`.
  - The integration file, with `-m integration --no-cov`.
  - Existing route tests stay green.
- [ ] **Step 4: Runtime proof in Docker dev.**
  - Initial response time with a cold weather cache.
  - `pg_stat_activity` during a slow section: no `idle in transaction`.
  - Record the lot's files and run the exhaustive review.
- [ ] **Step 5 (optional, spec E6): the synthesis states unavailable sections.**
  - The next version of `briefing_synthesis_prompt` gets an `{unavailable_sections}` placeholder,
    produced by `generate_synthesis`. `test_prompt_placeholders_are_produced.py` must stay green.
  - The line is bounded: section names only, no error text.
  - Test `test_failed_section_is_named_unavailable_in_prompt`.
  - The version bump goes through `briefing_synthesis_prompt_version`.

### Task D3: Progressive dashboard (frontend)

Starts only once the staged « LIA World » lot is committed: it rewrites `useBriefing.ts`, and this
task delegates from that hook API (`useBriefing(enabled)`, `textUnavailable`), not from the
2026-10-21 one.

**Files:**
- Create:
  - `apps/web/src/hooks/useBriefingProgressive.ts` — initial read, pending section reads and the
    text read, each under `useApplicationAccountLifetime` guards and revisions.
  - `apps/web/src/hooks/__tests__/useBriefingProgressive.test.tsx`
  - `apps/web/e2e/smoke/briefing-progressive.spec.ts`
- Modify:
  - `apps/web/src/hooks/useBriefing.ts` — delegate, keeping its public result shape.
  - `apps/web/src/types/briefing.ts` — `'pending'`.
  - `apps/web/src/components/dashboard/BriefingCard.tsx` — a pending skeleton of the card's
    geometry.
  - `TodayBriefing.tsx` — the grid renders per card; one `LoadingAnnouncement`.
  - The six locales.

- [ ] **Step 1: Write the failing tests** (D6, D9, D10).
  - `renders a local card while the weather read is still pending`.
  - `a pending card never shows the setup hint`.
  - `ignores a late section response after refresh`.
  - `ignores responses after logout and login`.
  - `double press on refresh sends one request`.
  - `sms signal drops text and hides sms items during a progressive load`.
  - `refreshing one card sends one section request and no text request`.
  - `text read starts once every pending section settled`.
- [ ] **Step 2: Implement.** Never unmount on refresh (`aria-busy`); `aria-disabled` plus a guard on
  busy controls.
- [ ] **Step 3: Run the gates.**
  - `task test:frontend`, `task lint:frontend`, `task lint:i18n` and
    `pnpm exec tsc --noEmit --incremental false` pass.
  - `task test:e2e -- briefing-progressive` passes.
  - The a11y, react-hooks and complexity ratchets stay green, with no baseline raised.
- [ ] **Step 4: Visual check in Docker dev** — mobile, desktop, zoom, themes, reduced motion. Record
  the lot's files and run the exhaustive review.

### Task S1 (optional): Safe retries for non-idempotent connector requests — three providers

Written together with the pending Drive push lot of 2026-10-26: `list_changes` gets the existing
« bulk read » budget through a per-call `timeout` in the same `_make_request`. One change to that
method, one review, one test file; the file is at 550/600 logical lines and `_make_request` at CC 29.

**Scope widened on 2026-10-28** (provider parity, spec §0quater). The resend exists in three
places, not one:
- `BaseOAuthClient._make_request`, used by Google (`:862`);
- `BaseMicrosoftClient`'s own `_make_request` (`base_microsoft_client.py:248`, three attempts on
  any `httpx.RequestError`, any method);
- Apple's `_execute_with_retry` (`base_apple_client.py:161`), which retries any exception. The
  installed `caldav` 3.3.1 mints a **new** UID on every `save_event` call, so a resent Apple create
  is a second event with another UID.

The policy follows the libraries and the providers (spec §0quater):
- **Never blindly resend after the request may have been sent.** `httpcore` retries only
  `ConnectError` and `ConnectTimeout`, and `urllib3` excludes `POST` by default.
- **Use the provider's own idempotency where it exists**, with keys derived from the effect
  register's `idempotency_key` (ADR-263), so a resend is the same act:
  - Microsoft Graph: `transactionId` on the event, which the provider documents for exactly this
    case;
  - Apple CalDAV: a `uid` fixed before the retry loop, so a resend targets the same object;
  - Google Calendar: a client-chosen `id` (base32hex). Google states that collisions are not
    guaranteed to be detected at creation, so after a read timeout the client **reconciles by
    `GET`** instead of resending.
- Gmail and Outlook mail send have no idempotency, and are never resent after sending.

**Files:**
- Create: `apps/api/src/domains/connectors/clients/retry_policy.py`.
- Modify:
  - `apps/api/src/domains/connectors/clients/base_oauth_client.py` — the `RequestError` branch
    (`:862`) asks the policy, and a per-call `timeout` parameter is added. The CC of
    `_make_request` must not grow (29).
  - `base_microsoft_client.py` (`:248`) asks the same policy.
  - `base_apple_client.py`: `_execute_with_retry` takes the operation's idempotency class.
  - The three calendar clients' `create_event` take an optional `idempotency_key: str | None`; the
    calendar tool passes the effect's key.
- Test:
  - `apps/api/tests/unit/domains/connectors/clients/test_retry_policy.py`;
  - one parity test file over the three providers.

**Interfaces:**
- Produces:
  - `may_resend(method: str, error: httpx.RequestError) -> bool`. True for idempotent methods; for
    POST, true only for `ConnectError`, `ConnectTimeout` and `PoolTimeout`.
  - `provider_idempotency_id(idempotency_key: str, provider: Literal["google", "microsoft", "apple"]) -> str`,
    in each provider's alphabet; base32hex for Google.

- [ ] **Step 0: Check what each `create_event` call site can pass.**
  - Whether the effect register's `idempotency_key` reaches the calendar tool at call time
    (ADR-263 claim).
  - Whether Apple's `save_event` accepts a caller `uid`.

  If either is missing, the lot keeps « no resend after send » for that provider and says so.
- [ ] **Step 1: Write the failing tests** (S1).
  - `test_post_connect_timeout_resent`.
  - `test_post_read_timeout_not_resent`: one attempt, typed failure.
  - `test_get_read_timeout_resent_as_today`.
  - `test_google_create_read_timeout_reconciled_by_get`: one event, success reported.
  - `test_graph_create_carries_transaction_id`.
  - `test_apple_create_resend_keeps_uid`.
  - Parity: the same scenario on the three providers yields at most one event and the same
    outcome.
- [ ] **Step 2: Implement, then run the tests** —
  `.venv/Scripts/pytest tests/unit/domains/connectors -q --no-cov` passes, and the CC check is
  green. Record the lot's files and run the exhaustive review.

**Measured (spec §0ter E4).**
- Simulation with the real `GoogleCalendarClient.create_event` against a server that creates the
  event and then answers after the read timeout: **3 events created**, and the caller sees
  `ExternalServiceError` after 6.2 s.
- Production over 7 days: 37 transport retries, all on reads (none within 60 s of an effect).
- The step-1 tests reuse that simulation as their oracle.

### Task S2: LLM client retries after an unknown outcome (E2; starts once Q3 is answered)

**Measured (spec §0ter E2).** The clients built by `ProviderAdapter.create_llm`, per family:

| Family | `max_retries` | Requests after a timeout | After a 500 or a 429 |
|---|---|---|---|
| OpenAI-wire (OpenAI, DeepSeek, Perplexity, Qwen) | 2 | 3 | 3 |
| Anthropic | 2 | 3 | 3 |
| Gemini | 6 | 1 | 6 (34 s) |
| Ollama | none | 1 | 1 |

Production: 2 timeouts in 30 days. The owner's rule says that a generation whose outcome is unknown
is never relaunched automatically.

**Files** (for the recommended option, Q3 (a)):
- Create: `apps/api/src/infrastructure/llm/providers/retry_policy.py` — one declared policy:
  - never relaunch after a timeout;
  - at most `LLM_TRANSIENT_RETRY_MAX` (default 2) relaunches after a 429, a 5xx, or a connection
    failure before the request was sent;
  - a stream is never relaunched once its first byte has arrived.
- Modify: `apps/api/src/infrastructure/llm/providers/adapter.py` — every family receives the
  policy, through the one seam each SDK offers (Step 0). A guard test holds every `ProviderType`
  member to it, like `test_reasoning_seam_guard.py`.
- Test: `apps/api/tests/unit/infrastructure/llm/providers/test_retry_policy.py`, which reuses the
  local-server simulation of 2026-10-28 (`.tmp/latency-20261028/sdk_retry_sim*.py`) with its DNS
  guard.

**State of the art (spec §0quater).**
- The installed OpenAI and Anthropic SDKs send **no idempotency key**
  (`_idempotency_header = None`), so no provider can de-duplicate their retries.
- Both SDKs obey a server's `x-should-retry` and refuse a `Retry-After` above their cap. The policy
  keeps both.
- Gemini's `max_retries` is `HttpRetryOptions.attempts`, *« including the original request »*, with
  configurable `http_status_codes`. The policy states **relaunches**, and each family translates
  them into its own unit.
- AWS Builders' Library: retry at one layer only. A connector or middleware layer above the client
  never relaunches a model call.

- [ ] **Step 0: For each SDK, find where it decides to retry, and record it in the test module's
  docstring.**
  - For the OpenAI-wire and Anthropic SDKs, the timeout branch is separate from `_should_retry`:
    either `max_retries=0` plus the policy around the client, or a client subclass.
  - For Gemini: `HttpRetryOptions(attempts=1 + relaunches, http_status_codes=…)`.
  - Ollama has nothing to change.
  - Choose the smallest seam that every family can share.
- [ ] **Step 1: Write the failing tests** (spec S2). For every family, with the local server:
  - a timeout gives 1 request;
  - a 429 or a 500 gives at most 3 requests;
  - a connection refused gives at most 3 requests;
  - a stream cut after its first chunk gives 1 request.
- [ ] **Step 2: Implement, then run the tests, `task test:backend:agents` and the LLM provider
  suites.** Each failure keeps its typed error, so `failure_kind` stays the same in
  `token_usage_logs`.
- [ ] **Step 3: Document the decision in an ADR-221 amendment.** It covers the per-attempt timeout,
  which no longer multiplies, and the relaunch policy. Record the lot's files and run the exhaustive
  review.

### Task O2: Client timings and observability wiring

**Files:**
- Modify:
  - `apps/web/src/lib/product-telemetry.ts` — the events `chat_first_token`,
    `dashboard_first_card`, `dashboard_all_cards` and `dashboard_text`; each value is a duration in
    seconds, with no content.
  - The chat stream handler where the first token is rendered, and `useBriefingProgressive`.
  - `apps/api/src/domains/product/router.py` — allowlist of the four names.
  - Grafana dashboards 01 and 26 — panels.
- Test: the frontend emitter tests and the backend allowlist tests.

- [ ] **Step 1: Write the failing tests.**
  - `emits chat_first_token once per turn and never for a progress step`.
  - `emits dashboard timings once per load`.
  - The backend refuses an unknown name.
- [ ] **Step 2: Implement, then run the gates.** Front-end gates, then
  `.venv/Scripts/pytest tests/unit/domains/product -q --no-cov` and the metric-coverage guard green.
- [ ] **Step 3: Document the SLI boundary change.** Add an ADR-119 amendment: the journey metric
  runs in parallel, and `SSELatencyP95High` migrates only after two weeks of observation. Record
  the lot's files and run the exhaustive review.

### Task N1: Network re-measurement — done on 2026-10-28

Spec §0ter H9:
- 968 `[resolver]` timeouts in 7 days (41–239 a day), all towards Google's public resolvers;
- present in 4 of the 24 MCP connections above 4 s, and in none of the 290 faster ones.

The two levers stay with the owner: Ethernet, and the deferred host DNS cache. Nothing is applied in
production.

### Task Q: Documentation, settings surfaces and final qualification

- [ ] **Step 1: ADRs.**
  - Write the new ADR (catalogue snapshot, served while revalidated, verified at use). It amends
    ADR-338 §2/§7 for personal MCP servers' turn preparation only (Q1, confirmed 2026-10-22).
  - Add amendments to ADR-271 (attempt markers; one act across requests), ADR-304 (pre-graph
    commit) and ADR-119 (journey SLI).
  - Update `docs/architecture/ADR_INDEX.md`.
  - Living maps: history entry and six-language text, `task docs:maps`.
- [ ] **Step 2: Technical documentation and FAQ.**
  - `docs/technical/BRIEFING_DOMAIN.md` and the MCP technical documentation.
  - FAQ in six languages (`faq.sections.*`): why a reply can wait for an application, what the
    notice means, how the dashboard fills.
  - `docs/knowledge`.
  - `CLAUDE.md`: at most one 2–4 line rule per new systemic rule, then `task docs:sync-agents`.
- [ ] **Step 3: Settings surfaces.** Check the six env files and the four demonstrator files for
  every new setting (spec §6.4), then run `task lint:hygiene`.
- [ ] **Step 4: Gates.**
  - `task lint` (it includes the ratchets, docs, i18n and CI parity), `task test:markers`,
    `task test:backend:unit:coverage`, `task test:backend:integration` (disposable
    `TEST_REDIS_URL` on base 15), `task test:backend:coverage` then
    `task test:backend:diff-coverage`, `task test:frontend:coverage`, `task test:e2e`.
  - Then `task ci:fast`.
  - Then `task lint:docs:preview` while nothing is staged.
- [ ] **Step 5: Final runtime proof in Docker dev** (X4).
  - Measure cold and warm chat turns and cold and warm dashboards, against the P0 baseline:
    medians, tails and sample sizes.
  - Count duplicated reads, generations and embedding calls (expected 0).
- [ ] **Step 6: Final exhaustive cold review.** Review every file of every lot plus the ignored
  `.env` files and check `git ls-files --eol`. Then report: passed, failed and skipped tests,
  unverified environments, and residual risks.

## Traceability

| Spec decision | Lots |
|---|---|
| A1, A2 | M1, M2 |
| A3 | M3 |
| A4, A5 | M2 |
| A6 | C1 |
| A7 | M4, M5 |
| A8, E5, E12, E13 | D1 |
| A9, A10 | D2, D3 |
| A11 | W1, W1b (optional) |
| E7, catalogue order, `ttlMs` and `cacheScope` (§0quater) | M1 |
| Q4 (open) | — (a lot only if (b) is chosen) |
| A12 | O1, O2 |
| A13 | N1 (done) |
| E2 (Q3) | S2 |
| E4 | S1 |
| E8, E11 | M6 |
| A15, E9, E10 | M1b |
