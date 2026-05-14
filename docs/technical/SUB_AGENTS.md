# Sub-Agents — Technical Documentation

## Overview

The sub-agents subsystem now has a **single execution path** (ADR-083 Phase 2,
2026-05-13): the principal agent's planner decides on the fly to spin up a
temporary expert via `delegate_to_sub_agent_tool`. Each delegation runs as a
**scoped ReAct loop on `ReactSubAgentRunner`** — read-only tools, tight
iteration budget, prompt persona injected through the `{expertise}` slot.

The legacy F6 plumbing (persistent `SubAgent` ORM record, `SubAgentExecutor`
bespoke pipeline, `/sub-agents` REST API, user-defined templates, daily Redis
budget, stale-recovery scheduler, per-user `sub_agents_enabled` preference
column, orphan `SubAgentsSettings.tsx`) was removed in Phase 2 cleanup. The
ephemeral ReAct path is the only consumer.

Sub-agents remain **invisible to the user** — the principal assistant
orchestrates them and presents results through natural conversation messages.

## Architecture

### Domain Structure (DDD)

```
src/domains/sub_agents/
├── __init__.py          # Empty __all__ — domain reduced to two helpers
├── constants.py         # SUBAGENT_DEFAULT_BLOCKED_TOOLS (read-only blocklist)
└── skill_resolver.py    # resolve_tools_for_subagent + is_skill_visible_to_agent
```

The tool itself, its catalogue manifests, its prompt, and its tests live in the
`agents` domain (where the planner / orchestrator and other tools live):

```
src/domains/agents/
├── tools/sub_agent_tools.py                       # delegate_to_sub_agent_tool
├── sub_agents/catalogue_manifests.py              # AgentManifest + ToolManifest
└── prompts/v1/subagent_react_prompt.txt           # ReAct scaffold + {expertise}
```

No DB table, no router, no service, no executor, no token guard, no scheduler
job, no daily-budget Redis key, no synthesis prompt — all removed in Phase 2.

### Planner Integration

Single transversal tool: `delegate_to_sub_agent_tool` — always in the planner
catalogue (force-included via `NormalFilteringStrategy`).

| Tool | Parameters | Description |
|------|-----------|-------------|
| `delegate_to_sub_agent_tool` | `expertise`, `instruction` | Runs a scoped ReAct expert loop (`ReactSubAgentRunner`) |

**How it works:**

1. The planner sees the tool in **every** filtered catalogue. The
   `{sub_agents_section}` of the planner prompt describes when delegation
   makes sense (deep domain expertise needed, independent research streams,
   specialist analysis improves quality) and when it doesn't (simple
   factual queries, CRUD, mutations). No runtime heuristic enforces this
   judgement — see ADR-083 §What was rolled back.
2. At execution time, `parallel_executor._execute_tool_step` re-validates
   the **resolved** `instruction` of `delegate_to_sub_agent_tool` (after
   `$ref` expansion) against `SUBAGENT_INSTRUCTION_MAX_TOKENS_RESOLVED`
   (default 3000 tokens, `.env`-controllable). Over-cap → step fails with
   `INVALID_INPUT`. This is the only structural defense — it kills the
   "shovel raw data via `$steps.X.<payload>`" pattern that caused the
   2026-05-12 incident.
3. `delegate_to_sub_agent_tool` invokes
   `ReactSubAgentRunner("subagent", "subagent_react_prompt").run(...)` — a
   single scoped ReAct loop:
   - `llm_type = "subagent"` (admin-configurable LLM, label *Sub-Agent
     (ReAct)*).
   - `prompt = "subagent_react_prompt"` (scaffold + `{expertise}` slot for the
     persona + read-only constraints).
   - `tools = resolve_tools_for_subagent(...)` (read-only subset of the
     registry — `SUBAGENT_DEFAULT_BLOCKED_TOOLS` + `delegate_to_sub_agent_tool`
     itself, anti-recursion).
   - `recursion_limit = settings.subagent_default_max_iterations`.
4. Multiple delegates with no `depends_on` → **parallel execution** (wave-based
   at the parent level).
5. Results referenced via `$steps.step_N.analysis` for chaining (short
   synthesized text — OK to chain; raw `$steps.step_N.<data>` is what the cap
   of step 2 rejects).

**Depth limit (two guards):**

1. **Primary**: `resolve_tools_for_subagent` excludes
   `delegate_to_sub_agent_tool` itself from a sub-agent's toolset, so a
   sub-agent's ReAct loop cannot even see the delegate tool.
2. **Belt-and-suspenders**: `delegate_to_sub_agent_tool` rejects calls whose
   inbound `session_id`/`thread_id` starts with `subagent_`
   (`DEPTH_LIMIT_EXCEEDED`).

**Catalogue manifest:**
`src/domains/agents/sub_agents/catalogue_manifests.py` (`AgentManifest` +
`ToolManifest` with semantic_keywords for natural discovery). Cost profile
aligned with the rewrite: `est_tokens_in=3000, est_tokens_out=2000,
est_cost_usd=0.02, est_latency_ms=20000`.

### Configuration

Feature flag: `SUB_AGENTS_ENABLED=false` (disabled by default).

All settings are in `src/core/config/agents.py` and documented in
`.env.example`.

| Setting | Default | Description |
|---------|---------|-------------|
| `SUB_AGENTS_ENABLED` | false | Feature flag — gates the entire delegation path globally |
| `SUBAGENT_DEFAULT_MAX_ITERATIONS` | 10 | Reused as `recursion_limit` of the ReAct loop. Range 1-30. LangGraph counts each node visit; ~3-4 tool rounds + synthesis fit in 10. Bumped from 5 (2026-05-14) after observing `GraphRecursionError` when the LLM batched 4-5 parallel searches in pass 1 then ran out of budget for synthesis. |
| `SUBAGENT_INSTRUCTION_MAX_TOKENS_RESOLVED` | 3000 | H2 cap on resolved `instruction` (ADR-083) |
| `SUBAGENT_TOOL_TIMEOUT_SECONDS` | 180.0 | Default timeout for a `delegate_to_sub_agent_tool` step in the parallel executor. Range 30-600. Slower reasoning models or multiple tool rounds push the wall-clock budget above the generic `MAX_TOOL_TIMEOUT_SECONDS` (120), hence a dedicated floor. |
| `SUBAGENT_TOOL_MAX_TIMEOUT_SECONDS` | 300.0 | Hard ceiling for `delegate_to_sub_agent_tool` step timeout, even if the planner requests more. Range 60-900. Lets operators raise the sub-agent budget without touching the application-wide `MAX_TOOL_TIMEOUT_SECONDS`. |
| `SUBAGENT_RESEARCH_TOOLS_WHITELIST` | `brave_search_tool,fetch_web_page_tool` | Comma-separated whitelist of tool names the ReAct sub-agent is allowed to invoke. When non-empty, switches `resolve_tools_for_subagent` to allowlist mode — every tool NOT in this list is filtered out, regardless of the blocklist. Empty string = legacy blocklist-only behavior (~80 tools exposed, observed to cause `GraphRecursionError`). |
| LLM Model | configured via Admin > LLM Configuration > Sub-Agent (ReAct) | `llm_type="subagent"` |

No per-user toggle anymore — Phase 2 dropped `users.sub_agents_enabled`
(Option B). The global feature flag is the only gate.

### Why dedicated timeout + whitelist (2026-05-14)

The generic `MAX_TOOL_TIMEOUT_SECONDS=120` was insufficient for delegated
ReAct loops on slow reasoning models (e.g. deepseek with high reasoning
effort). Raising the global cap would have over-budgeted other tools. The
dedicated pair (`SUBAGENT_TOOL_TIMEOUT_SECONDS` floor +
`SUBAGENT_TOOL_MAX_TIMEOUT_SECONDS` ceiling) wires into
`parallel_executor._execute_step_with_timeout` via a `tool_name ==
"delegate_to_sub_agent_tool"` branch — no impact on other tools.

The whitelist solves a related issue: with ~80 read-only tools exposed
(`SUBAGENT_DEFAULT_BLOCKED_TOOLS` only filters write/HITL tools), the
sub-agent's ReAct loop wastes its recursion budget exploring the catalogue
instead of converging on a synthesis. Restricting to 2-3 sharp research tools
(brave_search + fetch_web_page) keeps the sub-agent focused.

### V1 Constraints

- **Read-only**: Sub-agents cannot perform write operations
  (`SUBAGENT_DEFAULT_BLOCKED_TOOLS` enforced via
  `resolve_tools_for_subagent`).
- **Max depth 1**: Sub-agents cannot spawn other sub-agents (two guards, see
  §Planner Integration).
- **Auto-approve**: HITL on delegation is currently a passthrough
  (`approval_gate_node` always sets `plan_approved=True`). Out of scope of
  ADR-083.

### V1 Known Limitations

**No structural guard against expensive but well-formed delegations.** The
instruction cap (§Planner Integration step 2) only catches the raw-payload
inlining pattern (the original 486 K incident). A plan like
`[get_emails_tool, delegate(persona, "analyse $steps.step_1.<digest>")]`
where the sub-agent then re-fetches per-message bodies in 5–8 ReAct
iterations still processes 200–300 K tokens (mostly cache hits, so cost
stays low but compute and latency don't). Addressing this properly requires
a use-case-driven redesign — deferred to a follow-up. Until then, the
planner LLM's judgement is trusted without runtime backstop on the shape
of delegation plans.

**HITL on delegation is a passthrough** (`approval_gate_node` always
approves) — pre-existing regression from v1.14.5 "HITL streamlining" that
overlooked `delegate_to_sub_agent_tool`. The F6 code for plan-approval
messaging (`_build_approval_request`, `test_approval_gate_fallback.py`)
remains in place but dormant. Re-activation is out of scope of ADR-083.

### Token Tracking

Each sub-agent run goes through `ReactSubAgentRunner`, which forwards the
parent's `TokenTrackingCallback` (from `parent_config.get("callbacks")`) into
the nested `RunnableConfig`. The runner injects
`metadata["node_name_override"] = "sub-agent: <expertise>"`. Inside
`TokenTrackingCallback`, the second handler (line ~450) reads
`md.get("node_name_override")` and attributes tokens to that synthetic node
name in the parent tracker.

No separate `MessageTokenSummary` row, no separate session id, no daily Redis
budget, no manual consolidation — tokens flow into the parent's
`MessageTokenSummary` automatically and the `tool_name` cost appears in the
SSE / debug panel under `"sub-agent: <expertise>"`.

### HITL Rejection Fallback

When a user rejects a plan containing `delegate_to_sub_agent_tool` steps at the
approval gate, the system automatically converts the REJECT into a REPLAN
without sub-agents:

1. **Detection**: `approval_gate_node` checks if the rejected plan has
   sub-agent delegation steps.
2. **Conversion**: Sets `needs_replan=True` + `exclude_sub_agent_tools=True`
   in state.
3. **Catalogue exclusion**: `planner_node_v3` passes `exclude_tools` to
   `SmartPlannerService.plan()`, which post-filters
   `delegate_to_sub_agent_tool` from the catalogue (normal + panic mode).
4. **Cleanup**: Planner clears both flags after generating the new plan
   (single replan cycle).
5. **Result**: User gets a new plan using direct tools (web_search, etc.)
   instead of sub-agents.

Metric tracked: `hitl_plan_decisions{decision="REPLAN_SUB_AGENT_FALLBACK"}`.

### Response Node — Verbatim Delivery Override (2026-05-14)

The `response_node` prompt (`response_system_prompt_base.txt`) carries a
`<SubAgentDeliveryOverride>` block that activates when CURRENT TURN DATA
contains a substantial textual analysis (several thousand chars, markdown
sections, expert voice with cited sources). When the override applies, it
overrides the default `<ResponseGuidelines>` rule "Provide critical analysis
of results — do not list/detail results (handled by cards)" — which was
designed for record-list payloads (emails, events, etc.) and otherwise
compresses the sub-agent's expert output 10× and overlays the assistant's
conversational voice on top.

Under the override:

- The analysis is restituted **VERBATIM** (sections, sources, structure preserved).
- The response node does NOT re-synthesize, paraphrase, or compress.
- It does NOT impose the assistant's `<Personality>` voice on the expert
  output.
- A one-sentence introduction is allowed; 2-3 follow-up suggestions at the
  end remain permitted.

The override is conditional — for list-of-records payloads (the original
intent of `<ResponseGuidelines>`), behavior is unchanged.

### Semantic Validator Exception

The `for_each` cardinality check (Check 1 in `validate_for_each_patterns`)
exempts plans with 2+ explicit `delegate_to_sub_agent_tool` steps — each step
delegates to a different expert, satisfying the "each" cardinality without
`for_each` iteration.

Check 5 (repeated tool consolidation) also exempts `delegate_to_sub_agent_tool`
since explicit delegation to different experts cannot be consolidated into a
`for_each` pattern.

## 2026-05-13 Redesign (ADR-083)

Triggered by the 2026-05-12 incident where the query «résume les 5 derniers
emails envoyés par ma femme» consumed **485 930 tokens (€0.56, ~95 s)**
instead of ~12 K. Root cause: a planner delegation to an ephemeral sub-agent
that re-ran a 3-LLM-call mini-pipeline over a ~114 K-token blob of raw email
HTML inlined via `$steps.step_1.<emails>` reference resolution.

### Phase 1 changes (final state, post-rollback)

1. **Sub-agent execution = `ReactSubAgentRunner` parameterized** instead of
   the bespoke `query_analyzer + SmartPlannerService + execute_plan_parallel
   + synthesis` pipeline. Reuses the same generic runner as
   `browser_task_tool` and `mcp_server_task_tool`. The sub-agent is a single
   scoped ReAct loop with read-only tools (cf. §Planner Integration).

2. **One structural backstop — `SUBAGENT_INSTRUCTION_MAX_TOKENS_RESOLVED`
   (default 3000)**. `parallel_executor._execute_tool_step` re-validates the
   resolved `instruction` of `delegate_to_sub_agent_tool` after `$ref`
   expansion. Over-cap = step error. This kills the original 486 K incident
   pattern (raw HTML email bodies inlined via `$steps.step_1.<emails>`).
   Token estimate via `EstimationTokenCounter` (model-agnostic).

3. **Anti-recursion bug fix**: `resolve_tools_for_subagent` now excludes
   `delegate_to_sub_agent_tool` itself from a sub-agent's toolset (was
   previously absent — latent risk).

4. **LLM type renamed (display only)**: `Sub-Agent` → `Sub-Agent (ReAct)` in
   the admin LLM Config panel. The internal `llm_type` id `subagent` is
   preserved (DB rows, env overrides, `get_llm("subagent")` calls
   unaffected).

### Rolled back (2026-05-14)

Two pieces of Phase 1 were initially shipped and then reverted after
observing they sabotage the dominant use case (apply an expert persona to
data the principal can fetch cheaply):

- The `_build_sub_agents_section` rewrite in the planner prompt (introduced
  a "DO NOT DELEGATE for data retrieval + summarization" rule and a BAD/GOOD
  example forbidding `[fetch, delegate]` — both actively harmful to
  legitimate use cases).
- The `validate_sub_agent_delegation_justified` heuristic in
  `semantic_validator` + the `SUBAGENT_VETO_POINTLESS_ENABLED` setting (used
  `query_intelligence.domains` as its mono-domain signal, but the
  query_analyzer adds incidental domains like "contact" when a person
  reference is in the query — heuristic abstained on the exact pattern it
  was meant to catch).

See ADR-083 §What was rolled back. The "materially better" judgement is now
fully entrusted to the planner LLM, without a runtime backstop on plan
shape. A proper redesign is deferred to a follow-up.

**Effect on the original incident query (`résume mes 5 emails envoyés par
ma femme`)**: structurally protected by the cap — the 114 K raw-body
payload that caused the incident can no longer be inlined into the
sub-agent's `instruction`. Total cost on that specific query depends on
what plan the planner emits (still LLM-non-deterministic), but the
worst-case pathological 486 K pattern is gone.

### Phase 2 cleanup (2026-05-13)

Once Phase 1 confirmed that the ephemeral ReAct path was sufficient on its
own, the legacy F6 plumbing was deleted wholesale (no UI consumer; no
production rows). The cleanup covered both backend, frontend and DB:

- **Backend code removed** — `domains/sub_agents/{router,service,repository,
  executor,token_guard,schemas,models}.py`, the `/sub-agents` REST API,
  `subagent_synthesis_prompt.txt`, the `SubAgent` ORM model and
  registrations (`alembic/env.py`, `infrastructure/database/registry.py`,
  `main.py` lifespan, `tests/conftest.py`), and the stale-recovery scheduler
  job. `delegate_to_sub_agent_tool` no longer touches the DB on its main
  path (no `UserService` / `get_db_context` / `parse_user_id` imports).
- **Configuration trimmed** — 8 obsolete env vars removed
  (`SUBAGENT_MAX_PER_USER`, `SUBAGENT_MAX_CONCURRENT`,
  `SUBAGENT_DEFAULT_TIMEOUT`, `SUBAGENT_MAX_TOKEN_BUDGET`,
  `SUBAGENT_MAX_TOTAL_TOKENS_PER_DAY`,
  `SUBAGENT_MAX_CONSECUTIVE_FAILURES`,
  `SUBAGENT_STALE_RECOVERY_INTERVAL_SECONDS`, `SUBAGENT_MAX_DEPTH`) from
  `core/constants.py`, `core/config/agents.py`, `.env.example` and
  `.env.prod.example`. Only the four surviving variables in §Configuration
  remain.
- **User toggle removed (Option B)** — `users.sub_agents_enabled` column,
  `PATCH /auth/me/sub-agents-preference` endpoint,
  `SubAgentsPreferenceRequest/Response` schemas, the i18n
  `sub_agents_preference_updated` API message, the per-user preference
  check in `delegate_to_sub_agent_tool`, the `sub_agents_enabled` field in
  `apps/web/src/lib/auth.tsx`, and the orphan `SubAgentsSettings.tsx`
  component. Delegation is now gated only by the global
  `SUB_AGENTS_ENABLED` feature flag.
- **i18n** — the entire `sub_agents.{settings,templates}` block was dropped
  from all 6 locales (en, fr, de, es, it, zh). Parity preserved at 5297
  keys per locale.
- **Migrations** — `phase_2_cleanup_001` drops the `sub_agents` table +
  the unused `message_token_summary.parent_run_id` column;
  `phase_2_cleanup_002` drops `users.sub_agents_enabled`.

After Phase 2 there is a single execution path and a single feature gate.

**See also**: ADR-083 in
`docs/architecture/ADR-083-Sub-Agent-Delegation-React.md` for the decision
record; `docs/superpowers/specs/2026-05-13-sub-agent-delegation-redesign-design.md`
for the detailed design;
`docs/superpowers/plans/2026-05-13-sub-agent-delegation-redesign.md` for the
Phase 1 implementation plan;
`docs/superpowers/plans/2026-05-13-sub-agent-phase-2-cleanup.md` for the
Phase 2 cleanup plan.

## Migrations

- `2026_03_16_0001` (`sub_agents_001`): Create `sub_agents` table + indexes
  *(reverted by `phase_2_cleanup_001`)*.
- `2026_03_16_0002` (`sub_agents_002`): Add `parent_run_id` to
  `message_token_summary` *(reverted by `phase_2_cleanup_001` — column was
  never populated)*.
- `sub_agents_003`: Add `users.sub_agents_enabled` *(reverted by
  `phase_2_cleanup_002`)*.
- `phase_2_cleanup_001` (2026-05-13): Drop `sub_agents` table +
  `message_token_summary.parent_run_id`.
- `phase_2_cleanup_002` (2026-05-13): Drop `users.sub_agents_enabled`
  (Option B — global feature flag is now the only gate).
