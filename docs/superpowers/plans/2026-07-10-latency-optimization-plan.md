# Latency Optimization Plan (TTFT lot)

**Status**: R1 + R2 implemented and validated (n=5, 0 errors); R3 implemented, ships dark (see §7); S1 + validator-robustness mini-lot pending separate arbitration
**Created**: 2026-07-10 (repatriated from the out-of-repo pre-spec of 2026-05-30)
**Owner lot**: measure → quantified shortlist → arbitration → iterative implementation → validation
**Constraint**: zero visible functional change (same responses, same SSE events); feature flag per optimization when risk justifies it; no service refactoring (R2-05 is a separate lot).

---

## 1. Context and objective

Measured production baseline (RPi5, 2026-06, ReAct mode, `deepseek-v4-flash` + `gpt-5.2` initiative):

| Metric | Value |
|---|---|
| TTFT (time to first token) | 16–57 s |
| Total turn duration | 28–66 s |
| p95 per node — initiative | 15.3 s |
| p95 per node — response | 12.8 s |
| p95 per node — query_analyzer | 12.0 s |
| Prompt cache hit rate | 43.8 % |

Structural cause in pipeline mode: a cascade of **sequential LLM calls before the first streamed token**:

```
compaction (pass-through) → router_v3 ─┬─ semantic_pivot (LLM, Redis-cached 300s)
                                       ├─ memory: broad search (embedding) ∥ reference extraction (LLM)
                                       │        └─ (if references) targeted searches + resolution (LLM)
                                       ├─ query_analyzer (LLM, structured output)
                                       ├─ context resolution (Store, non-LLM)
                                       └─ tool scoring (embeddings)
        → planner (LLM) → semantic_validator (LLM, bypassed if ≤1 step)
        → approval_gate (pass-through) → task_orchestrator (tools)
        → initiative (LLM) → response (LLM — FIRST STREAMED TOKEN)
```

ReAct mode: `router → react_setup → react_call_model (LLM×N) ↔ react_execute_tools → react_finalize → [initiative] → response (LLM reformulation — first token)`.

Conversational turns: `compaction → router (2–4 LLM calls) → response`. The response node fetches its context bundle (user-message embedding + memory/RAG/journal/portrait/psyche lookups) **inline** on this path — the prefetch overlap (`services/response_context.py`) only triggers on turns that traverse the initiative node.

## 2. Instrumentation (holes filled by this lot)

What existed per node before this lot: `agent_node_duration_seconds{node_name}` on 6 nodes only (approval_gate, hitl_dispatch, for_each_confirm, task_orchestrator, initiative, response); `router_latency_seconds` (unlabelled, buckets capped at 2 s); `semantic_validation_duration_seconds` (capped at 5 s); `sse_time_to_first_token_seconds` (capped at 5 s — every prod observation landed in +Inf); `llm_api_latency_seconds{model,node_name}` via callback.

Filled (surgical, 2026-07-10):

1. **`langgraph_stage_duration_seconds{stage, execution_mode, turn_kind}`** (new, `metrics_langgraph.py`) — wall-clock per graph stage measured between consecutive `updates` stream events at the SSE chokepoint in `StreamingService.stream_sse_chunks`. Includes checkpoint writes and inter-node overhead (unlike `agent_node_duration_seconds`, which times the node body only — the difference isolates checkpoint/scheduling cost). Labels: `execution_mode` ∈ {pipeline, react}, `turn_kind` ∈ {conversation, action, hitl_resume, unknown}. Durations are buffered during the stream and flushed at end-of-turn / HITL interrupt, once the labels are resolved.
2. **`graph_stage_durations` structured log** (INFO, one line per turn, durations only — PII-safe) — the reliable per-turn breakdown in Loki for multi-worker deployments where in-process Prometheus histograms are not aggregated.
3. **`agent_node_duration_seconds`** now also observed on `router_v3`, `planner_v3`, `react_setup`, `react_call_model`, `react_execute_tools`, `react_finalize` (duration only — execution counters unchanged to avoid double counting).
4. **Bucket ranges resized to the RPi5 reality** (p95 was uncomputable, everything in +Inf): `sse_time_to_first_token_seconds` → up to 90 s, `sse_streaming_duration_seconds` → up to 180 s, `router_latency_seconds` → up to 30 s, `agent_node_duration_seconds` → up to 120 s, `semantic_validation_duration_seconds` → up to 30 s (its configured timeout is 20 s).

## 3. Reproducible protocol

`scripts/perf/measure_ttft.py` — the official before/after instrument of this lot.

- 13 scenario types × N iterations (official runs: 5), symmetric across both execution modes: conversational ×2, single-domain action (wikipedia — pure tool path) in pipeline AND react, multi-domain action in pipeline AND react, HITL draft + resume in pipeline AND react (reminder-cancel draft — the only OAuth-free draft trigger; reminder creation is direct, no confirmation), and the **skill path isolated as its own scenario** in both modes (`skill_weather_*`: weather queries activate the system skill `weather-dashboard` — mixing it with the pure tool path makes percentiles uninterpretable).
- OAuth-free domains only (wikipedia, weather, reminder draft) so a dedicated perf user without connectors works. The perf user must be activated once: `UPDATE users SET is_active=true, is_verified=true WHERE email='<perf-email>';`
- Client-side truth: TTFT (first `token` / `hitl_question_token` SSE event) + total duration. Server-side truth: before/after `/metrics` deltas of `langgraph_stage_duration_seconds` (per stage), `agent_node_duration_seconds` (node body) and `llm_api_latency_seconds` (LLM share per call site). Valid on the single-worker dev API.
- Query variants per iteration bust the exact-match caches (semantic pivot Redis, TTL 300 s); `--no-cache-bust` measures the warm path.
- Run: `apps/api/.venv/Scripts/python scripts/perf/measure_ttft.py --email <perf-email> --password <pwd> [--register] [--iterations 3]`

Percentiles are nearest-rank; with the default 3 iterations p95 ≈ max — use ≥5 iterations for a finer p95.

## 4. Dev baseline (before) — systemic run 2026-07-10 (n=5)

Environment: dev Docker (Windows host), single worker, real LLM providers, dedicated perf user (no OAuth connectors), **13 scenarios × 5 iterations (65 requests, 0 errors)**, cache-busting variants, symmetric pipeline/react coverage, skill path isolated. Raw data: `scripts/perf/results/baseline_dev_systemic.json` (not committed — table below is the reference "before").

| scenario | mode | kind | TTFT p50 | TTFT p95 | total p50 | total p95 |
|---|---|---|---|---|---|---|
| conv_greeting | pipeline | conversation | 5.46 s | 7.57 s | 10.44 s | 15.70 s |
| conv_knowledge | pipeline | conversation | 6.17 s | 7.08 s | 9.59 s | 11.65 s |
| action_wiki | pipeline | action single | 8.14 s | 11.32 s | 17.67 s | 24.83 s |
| skill_weather_pipeline¹ | pipeline | skill | 15.28 s | 18.75 s | 17.31 s | 19.93 s |
| action_multi² | pipeline | action multi | 15.21 s | 16.65 s | 24.29 s | 26.76 s |
| hitl_draft³ | pipeline | HITL trigger | 18.80 s | 22.00 s | 19.96 s | 23.45 s |
| hitl_resume | pipeline | HITL resume | 2.00 s | 2.01 s | 2.03 s | 2.03 s |
| react_conv | react | conversation | 5.10 s | 7.52 s | 10.73 s | 11.13 s |
| react_wiki | react | action single | 17.51 s | 24.67 s | 28.61 s | 35.86 s |
| skill_weather_react¹ | react | skill | 26.73 s | 31.63 s | 28.17 s | 32.64 s |
| react_hitl_draft³ | react | HITL trigger | 10.39 s | 12.53 s | 11.43 s | 14.08 s |
| react_hitl_resume | react | HITL resume | 1.99 s | 2.19 s | 2.01 s | 2.22 s |
| react_multi | react | action multi | 23.09 s | 26.38 s | 32.62 s | 43.85 s |

¹ Weather queries activate the **system skill `weather-dashboard`** → `ReactSubAgentRunner` generates the full answer in isolation and the response node takes its fast-path: the sub-agent output is **not streamed** (response pre-first-token 5–12.7 s on skill iterations vs ~1 s everywhere else). Skill activation is itself variable (2/10 skill iterations did not fire it). The weather tool returns in 0–2 ms for the perf user (no per-user OpenWeatherMap connector) — surrounding timings remain valid.
² 1/5 action_multi iterations was hijacked by the weather skill (multi query contains "quel temps fait-il") — visible as a 10.2 s pre-first-token outlier; the p50 is unaffected.
³ **Pipeline vs ReAct on the same mutation** (cancel a reminder): pipeline pays planner 4.1 s + semantic_validator 8.5 s (with intermittent auto-replan — see §5bis robustness finding) = TTFT 18.8 s; ReAct calls the tool directly in its loop = TTFT 10.4 s. The +8.4 s delta is the pipeline mutation-path overhead, not the tool.

## 5. Where the seconds go — measured map (dev p50)

**Universal invariant — the router costs 3.9–5.8 s on 100 % of graph turns** (11/13 scenarios; only the two resume scenarios skip it). Internal decomposition (LLM sites, n=55 across all scenarios, systemic run):

| Router sub-step | p50 | Notes |
|---|---|---|
| semantic_pivot (LLM) | 1.04 s | runs FIRST, blocks everything; Redis exact-match cache measured **0 hit / 37 miss** |
| memory phase | ~1.1–1.5 s | broad search (embedding) ∥ reference-extraction LLM (1.13 s); + targeted search + resolution LLM when references found |
| query_analyzer (LLM) | 2.94 s | structured output; also returns its own `english_query` |
| residual (tool scoring embeddings, context resolution, expansion) | ~0.3–0.7 s | tool scoring feeds the planner catalogue filtering (NOT debug-only — the router comment is misleading, doc-bug to fix) |

**Per-turn-kind decomposition (stage p50):**

- **conversation** (TTFT ~5–5.9 s): router 4.0–4.9 + response pre-first-token ~0.9–1.1 (context bundle fetched inline + prompt build + LLM first chunk).
- **action single** (TTFT ~7.8 s): + planner 2.1 + orchestrator 0.2 (wikipedia real call). Initiative skipped when plan trivially empty, else 2.1–2.9 s ON the TTFT path.
- **action multi** (TTFT ~16.6 s): + semantic_validator 3.1 + orchestrator 2.3 + initiative 2.8.
- **HITL trigger** (TTFT ~17.4 s): router 5.4 + planner 4.2 + **semantic_validator 8.0** + draft question 1.7. The validator is the single biggest stage on this path.
- **HITL resume** (TTFT 1.7 s): hitl_classifier LLM 1.64 s; graph resume itself ~30 ms. Healthy.
- **ReAct action** (TTFT 23–31 s): router ~5 + ReAct loop 11.7–21.6 (multiple LLM passes) + initiative 2.4–2.9 + response reformulation (streams, pre-token ~0.8–1).
- **response pre-first-token ≈ 0.8–1.1 s on every scenario** — context bundle (~0.3 s inline for a light user; prefetch already overlaps it on turns that traverse initiative) + prompt assembly + LLM connection.
- **Checkpoint/inter-node overhead**: stage-vs-node-body delta measured 3–8 ms per node in dev — negligible here; the new histogram makes it measurable on the RPi5 (prime suspect for the dev→prod gap).
- Instrumentation residual: the ReAct loop's LLM calls do not appear in `llm_api_latency_seconds` (reasoning-stream path) — loop cost is visible via the `react_call_model` stage only.

Background (post-response, NOT on TTFT): interest/memory/journal extraction ~0.7–1.9 s each — already async.

## 5bis. Systemic view — the whole assistant, not just interactive chat

**Every entry path that traverses the LangGraph graph** (verified in code) shares the same critical path, so a router/response-prep lever applies to all of them:

| Entry path | Goes through the graph? | Latency-sensitive? | Notes |
|---|---|---|---|
| Interactive chat (SSE) | yes (`router.py` → `stream_chat_response`) | **yes (TTFT)** | measured baseline |
| HITL resume (same endpoint) | yes (resume at interrupted node) | yes | router/planner NOT re-run — already lean (1.7 s) |
| Voice mode | same chat flow + TTS side-channel | **yes (TTFA)** | every TTFT second gained propagates to time-to-first-audio (progressive sentence streaming starts on first sentences) |
| Background runs (ADR-117 detached producer) | yes (same `stream_chat_response`) | yes on reattach | levers apply unchanged |
| Scheduled actions | yes (`scheduled_action_executor.py:203`, `auto_approve_plan=True`) | no (no user waiting) | still benefits: R3 removes one LLM call per run (cost), R1 shortens executor timeout pressure |
| Channels — Telegram (`inbound_handler.py:220`) | yes | **yes** (user waits on Telegram) | full lever coverage |
| Heartbeat proactive messages | **no** (direct `get_llm()` calls) | no | out of scope |
| Today briefing | **no** (asyncio.gather fetchers, own pattern) | own budget | out of scope |
| Skill ReAct sub-agent | nested inside response node | yes | S1 target — affects BOTH modes (skills activate via planner route, response route AND ReAct `activate_skill_tool`) |

**Stage × path matrix (who pays what, dev p50, systemic run n=5):**

| Stage | pipe conv | pipe action | pipe multi | pipe HITL | react conv | react action | react HITL | resume (2 modes) |
|---|---|---|---|---|---|---|---|---|
| router (pivot+mémoire+analyzer) | 4.4–5.0 | 5.0 | 4.8 | 5.8 | 3.9 | 5.3–5.7 | 5.4 | — |
| planner | — | 1.9 | 2.2 | 4.1 (replan) | — | — | — | — |
| semantic_validator | — | (bypass) | 2.9 | **8.5** | — | — | — | — |
| ReAct loop (call_model) | — | — | — | — | — | 9.7–11.5 | 4.6 | — |
| task_orchestrator / execute_tools | — | 0.2 | 0.2–2.3 | ~0 | — | 0.5 | ~0 | — |
| initiative | — | 0–2.7¹ | 2.7¹ | — | — | 2.7–2.9² | — | — |
| response pre-first-token | 1.0–1.2 | 1.0 | 0.8 | 0.4³ | 1.2 | 1.0–1.2 | 0.4³ | 2.0 (classifier 1.9) |
| skill sub-agent (when active) | +5 to +12.7 (blocking) | idem | (hijack 1/5) | — | idem | idem | — | — |

¹ `INITIATIVE_ENABLED` default true — on the TTFT path of every pipeline action turn (prod p95 was 15.3 s).
² Dev only: `INITIATIVE_REACT_ENABLED` default **false** — verify the prod `.env` before extrapolating react prod TTFT.
³ HITL trigger's response is the streamed draft question (1.7 s LLM), not the response node.

**Systemic classification of the levers:**

- **Universal (100 % of graph turns, both modes, all entry paths)**: R1 (router pivot ∥ memory), R3 (drop pivot). The router is the only stage paid by *every* turn of *every* kind on *every* graph entry path — this is why they rank first.
- **Near-universal**: R2 (response bundle prefetch at router entry) — benefits every turn whose bundle is not already overlapped: conversation (both modes), react action in prod (initiative off by default ⇒ always inline today), HITL resume. Pipeline action turns already overlap it via initiative.
- **Path-specific, big magnitude**: S1 (skill sub-agent streaming) — both modes, only skill turns; −8 to −11 s each.
- **Product-decision options (quantified here, NOT in this lot's default shortlist — they change functional behavior)**: initiative on the TTFT path (2.1–2.9 s dev / 15.3 s p95 prod on every pipeline action turn); semantic_validator (3.1–8.0 s when it fires — the 8 s on a 2-step reminder-cancel plan looks anomalous and deserves its own investigation before any redesign).
- **Instrumentation residuals** (noted for follow-up): ReAct loop LLM calls absent from `llm_api_latency_seconds` (reasoning-stream path); the first stage of each turn carries checkpoint-load overhead (negligible in dev, will matter on RPi5); the "for Debug Panel" comment on router tool-scoring is a doc-bug (scores feed planner catalogue filtering).
- **Robustness finding with latency impact** (separate mini-lot, behavior-affecting): the semantic validator's structured output fails intermittently (`StructuredOutputError: no parsable payload` — 4 occurrences in the measurement window) and validations judged invalid trigger **auto-replan loops**: the turn then pays planner + validator TWICE (observed on the reminder-cancel HITL path: planner 4.2 s, validator 8.0 s). p95 spikes on mutation paths are replan loops, not slow single calls — fix the validator's structured-output reliability (model/prompt config) before optimizing around it.

## 6. Quantified shortlist (pending arbitration)

| # | Optimization | Estimated TTFT gain (dev p50) | Scope | Risk | Flag |
|---|---|---|---|---|---|
| **R1** | Router: run semantic pivot ∥ memory resolution (`asyncio.gather`) — memory embeds the ORIGINAL query (verified in `memory_resolver.py`), the pivot does not depend on it | **−0.8 to −0.9 s** | ALL turns (conv, action, react, HITL trigger) | Low — data independence verified; same results, same order | Not needed (iso-behavior) |
| **R2** | Start the response-context prefetch at router entry for ALL turns (the 5 QI-independent injections; `_inject_system_rag` stays inline — it reads `is_app_help_query` which only exists post-analyzer) | −0.3 s dev; **−0.5 to −1.5 s expected in prod** — an *extrapolation*, not a measurement (real user: memories + RAG + journals + psyche on RPi5; the dev perf user has none) | conversation (both modes) + **react action turns in prod** (`INITIATIVE_REACT_ENABLED` off by default ⇒ their bundle is always inline today) — pipeline action turns already overlap via initiative | Low — existing infra + existing kill-switch (`RESPONSE_CONTEXT_PREFETCH_ENABLED`) | Existing |
| **R3** | Remove the semantic pivot LLM call: pass the original query to the analyzer and use the `english_query` it already returns (field exists in `QueryAnalysisOutput`) | ~~−0.8 s~~ → **measured ≈ 0 after R1** (not additive: R1 already hides the pivot under the longer memory branch); residual value = −1 LLM call/turn (cost) | ALL turns | Medium — domain-detection quality with non-English input to validate (A/B verdict: zero drift on the protocol corpus — see §7) | YES (`SEMANTIC_PIVOT_ENABLED`, ships dark) |
| **S1** | Stream the skill ReAct sub-agent output (today: blocking fast-path, answer arrives as one block after up to ~12 s) | −8 to −11 s on skill turns | turns activating a scripted skill (e.g. weather-dashboard) | Medium (runner isolation) — effort L | YES |

**Rejected / deferred by the data:**

- *(d) query_analyzer semantic cache*: the only existing LLM cache (pivot) measured **0 hit / 37 miss**; analyzer inputs embed history + memory facts and never repeat → dead end as-is.
- *Skip router tool-scoring for non-debug users*: the scores feed the planner catalogue filtering (`catalogue/strategies/normal_filtering.py:118`) — behavior change, excluded. Follow-up: fix the misleading "for Debug Panel" comment in `router_node_v3.py`.
- *(c) early response streaming*: tokens already stream during generation on every path except S1.
- *semantic_validator (3.1–8.0 s) and initiative (2.1–2.9 s)*: major TTFT contributors on action/HITL paths, but removing or deferring them changes functional behavior → product decision, separate lot.
- *Checkpoint overhead*: 3–8 ms in dev, not actionable here; re-evaluate in prod with `langgraph_stage_duration_seconds` − `agent_node_duration_seconds`.

**Recommendation**: implement **R1 + R2** (low risk, iso-behavior, ≈ −1.1 to −1.2 s dev on conversational TTFT, more in prod), then **R3 under flag** with domain-detection A/B validation. S1 is the big-ticket option for skill turns — separate arbitration given effort L.

## 7. Decisions and follow-up

| Date | Decision | Before → after (protocol) |
|---|---|---|
| 2026-07-10 | Instrumentation lot + protocol v2 (13 scenarios, skill isolated, HITL in both modes) + systemic dev baseline n=5 (§4) | baseline recorded |
| 2026-07-10 | Arbitration: **R1 + R2 approved, R3 approved under flag (ships dark)**; S1 and the validator-robustness mini-lot deferred to separate arbitrations | — |
| 2026-07-10 | **R1 implemented** — semantic pivot runs concurrently with the memory-resolution phase (`asyncio.Task` created in `router_node_v3`, awaited by `analyze_full` after its memory gather; task cancelled best-effort on failure). Iso-behavior: memory still embeds the original query, analyzer still receives the pivot English. | Router stage p50: **−0.28 to −1.74 s across all 11 router-traversing scenarios (median ≈ −1.1 s)**, n=5, 0 errors (`after_R1.json`). TTFT down on all 13 scenarios. |
| 2026-07-10 | **R2 implemented** — response-context prefetch starts at router entry (`RESPONSE_CONTEXT_PREFETCH_AT_ROUTER_ENABLED`, default true, requires the existing global kill-switch). The QI-dependent system-RAG injection is deferred (`ResponseContextBundle.system_rag_deferred`) and resolved inline by the response node via `fetch_app_knowledge_context` with the fresh intelligence. Registry keyed on the METADATA run_id (same source as initiative/response). | Response pre-first-token p50 on conversation/react turns: **−0.1 to −0.27 s** (dev perf user has a light bundle: no memories/RAG/journals — the prod gain on the real user's bundle is the target, to be confirmed post-deploy via `langgraph_stage_duration_seconds`), n=5, 0 errors, `prefetch_hit` verified on conversation turns (`after_R2.json`). |
| 2026-07-10 | **R3 implemented, ships dark** — `SEMANTIC_PIVOT_ENABLED` (default true = historical behaviour). When false: no pivot LLM call; the analyzer receives the original query and its own `english_query` output feeds the downstream English pattern-matching (FOR_EACH heuristics, context resolution, goal inference). | A/B n=5 pivot OFF (`after_R3_pivot_off.json`), 0 errors. **Latency: ≈ 0 gain — R1 and R3 are NOT additive**: R1 already runs the pivot concurrently with the memory phase, which is the longer branch (~1.0–1.5 s vs ~0.9–1.0 s), so `max(pivot, memory)` is unchanged when the pivot disappears (router deltas ±0.3 s ≈ noise). **Quality: zero drift** — intent/domains/route distributions identical ON (135 turns) vs OFF (117 turns) on the French protocol corpus (6 query families). Residual value of flipping the flag = cost only (−1 nano-LLM call/turn). Recommendation: keep dark; flip in prod only as a cost decision, after a broader-corpus check (the protocol corpus does not cover person references, MCP domains or non-French languages). |
