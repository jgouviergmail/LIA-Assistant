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

- **Settings surfaces.** Every setting has:
  - its default in `apps/api/src/core/constants.py`;
  - a `Field(ge=…, le=…, description=…)` in its config module;
  - lines in `.env.example`, `.env.prod.example`, `.env.demo-instance.example`,
    `.env.demo-instance.prod.example`, `.env.demo-instance` and `.env.demo-instance.prod`.
  - `.env.min.prod` is not touched.
- **Ratchets are shrink-only:** file size (`apps/api/tests/unit/file_size_baseline.json`, cap 600),
  backend CC (`apps/api/.cc-baseline.json`: `over` 263, `max` 77), and the front-end a11y,
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
    `lia-api-dev`.
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

Durations are focused inline work including tests, ratchets, the runtime proof and the exhaustive
review. They exclude waiting for an authorization or an owner answer.

| Order | Lot | Size | Estimate | Depends on |
|---|---|---|---|---|
| 1 | P0 baseline and harness | S | 1–2 h | — |
| 2 | O1 journey metrics (backend) | S | 2–3 h | P0 |
| 3 | D1 dashboard stops re-collecting | M | 5–7 h | P0 |
| 4 | W1 weather and environment clients | S | 2–3 h | P0 |
| 5 | S1 safe retries (optional) | S | 1–2 h | — |
| 6 | C1 pre-graph commit and archive-first | M (critical path) | 5–7 h | O1 |
| 7 | M1 catalogue snapshot | M | 4–6 h | — |
| 8 | M1b `read_me` at real use | M | 4–5 h | M1 |
| 9 | M2 parallel preparation and revalidation | L | 10–14 h | C1, M1, M1b |
| 10 | M3 verification at use | S–M | 3–4 h | M2 |
| 11 | M4 notices (backend) | M | 4–5 h | C1, M2 |
| 12 | M5 notices (frontend) | M | 4–6 h | M4 |
| 13 | D2 progressive dashboard (backend) | L | 10–14 h | D1 |
| 14 | D3 progressive dashboard (frontend) | L | 8–12 h | D2 |
| 15 | O2 client timings and panels | S–M | 3–4 h | O1, D3 |
| 16 | N1 network diagnosis | S (no code) | 2–3 h | owner authorization |
| 17 | Q docs, FAQ, ADRs, final qualification | M | 6–10 h | all |

Total: about 75–110 h.

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
  - `apps/api/src/infrastructure/utils/shared_flight.py` — opt-in owner liveness and polling
    backoff.
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
- [ ] **Step 3: Write the failing frontend tests.**
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
- [ ] **Step 5: Runtime proof in Docker dev (test X1).**
  - With the stub MCP server sleeping 20 s, query `pg_stat_activity` (`state`, `xact_start`) during
    the wait: no backend of the turn may be `idle in transaction`.
  - The person's message appears in another tab before the reply starts.
  - Record the lot's files and run the exhaustive review.

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
    `tools: tuple[Mapping[str, JsonValue], ...]`, `reference_content: str | None` (≤ 50 000 chars).
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
    - `_usable_tool_embeddings`'s recompute goes through `spend_blocked`, `enforce_usage_limit` and
      the embedding attribution context, with unchanged inputs.
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
  - `test_recompute_skipped_when_spend_blocked`: zero embedding calls and tools still registered.
  - `test_revalidation_single_flight_across_workers` (integration, Redis): two schedulers give one
    discovery.
  - `test_revalidation_refused_after_edit` (integration, PostgreSQL).
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

### Task S1 (optional): Safe retries for non-idempotent connector requests

**Files:**
- Create: `apps/api/src/domains/connectors/clients/retry_policy.py`.
- Modify: `apps/api/src/domains/connectors/clients/base_oauth_client.py` — the `RequestError` branch
  asks the policy; the CC of `_make_request` must not grow (29).
- Test: `apps/api/tests/unit/domains/connectors/clients/test_retry_policy.py`.

**Interfaces:**
- Produces: `may_resend(method: str, error: httpx.RequestError) -> bool`. True for idempotent
  methods; for POST, true only for `ConnectError`, `ConnectTimeout` and `PoolTimeout`.

- [ ] **Step 1: Write the failing tests** (S1).
  - `test_post_connect_timeout_resent`.
  - `test_post_read_timeout_not_resent`: one attempt, typed failure.
  - `test_get_read_timeout_resent_as_today`.
- [ ] **Step 2: Implement, then run the tests** —
  `.venv/Scripts/pytest tests/unit/domains/connectors -q --no-cov` passes, and the CC check is
  green. Record the lot's files and run the exhaustive review.

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

### Task N1: Network diagnosis and remediation proposal (no code; production needs authorization)

- [ ] **Step 1: Ask the owner for the read-only production window** (SSH through
  `scripts/deploy/deploy.local.ps1`; never print the host).
- [ ] **Step 2: Run the protocol of spec §5.12.**
  - 200 `getaddrinfo` per host, `AF_UNSPEC` and `AF_INET`, in the container and on the host.
  - `dig` against the gateway, 1.1.1.1 and 8.8.8.8.
  - Ten-minute loss series.
  - Wi-Fi link statistics.
  - `docker version`.
  - Write `network-diagnosis.md`, with the distributions, not the means only.
- [ ] **Step 3: Propose one remediation with its rollback** (caching resolver, upstreams, resolver
  options or wired link) and test it on dev first. Apply nothing in production without explicit
  approval.

### Task Q: Documentation, settings surfaces and final qualification

- [ ] **Step 1: ADRs.**
  - Write the new ADR (catalogue snapshot, served while revalidated, verified at use; amends
    ADR-338 §2/§7 if Q1 is accepted).
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
    `task test:backend:unit:coverage`, `task test:frontend:coverage`, `task test:e2e`.
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
| A8 | D1 |
| A9, A10 | D2, D3 |
| A11 | W1 |
| A12 | O1, O2 |
| A13 | N1 |
| E4 | S1 |
| E8 | M2 |
| A15, E9, E10 | M1b |
