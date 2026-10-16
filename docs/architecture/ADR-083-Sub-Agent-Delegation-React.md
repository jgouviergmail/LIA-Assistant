# ADR-083: Sub-Agent Delegation as a Parameterized ReAct Loop

**Status**: ✅ IMPLEMENTED (2026-05-13)
**Author**: Claude Opus 4.7 (with `jgouviergmail`)
**Related**: ADR-062 (Initiative Phase + MCP ReAct — origin of `ReactSubAgentRunner`), ADR-070 (ReAct Execution Mode), F6 Phase (Persistent Specialized Sub-Agents — origin of the persistent API removed in Phase 2)
**Spec**: `docs/superpowers/specs/2026-05-13-sub-agent-delegation-redesign-design.md`
**Plans**: `docs/superpowers/plans/2026-05-13-sub-agent-delegation-redesign.md` (Phase 1),
`docs/superpowers/plans/2026-05-13-sub-agent-phase-2-cleanup.md` (Phase 2)

## Context

### The incident (2026-05-12)

The query «fais moi un résumé des 5 derniers emails envoyés par ma femme» consumed **485 930 tokens (€0.56, ~95 s)** on prod (`request_id 50855ec2-…`). Token breakdown:

| Scope | prompt tokens |
|---|---|
| Main pipeline (`semantic_pivot`, `memory_ref`, `query_analyzer`, `planner`, `semantic_validator`, `initiative`, `response`, …) | ~28 000 |
| **`subagent:assistant de synthèse d'emails` node** | **~457 000** |

Inside the sub-agent, three LLM calls each received massive prompts:

| Internal call | model | prompt tokens |
|---|---|---|
| `_analyze_instruction` → `analyze_query(query = expertise + "\n\n" + instruction)` | gpt-5.2 | **115 196** |
| `SmartPlannerService.plan(intelligence=qi)` | gpt-5.2 | **225 253** |
| `_synthesize_results` (template + `{instruction}`) | deepseek-v4-flash | **115 090** |

### Root cause (chain)

1. The **principal planner** produced a 2-step plan: `step_1=get_emails_tool` (fetched 4 emails into the data registry), `step_2=delegate_to_sub_agent_tool(expertise="assistant de synthèse d'emails…", instruction="…$steps.step_1.<field>…")`.
2. At execution, `ReferenceResolver._resolve_embedded_references` → `_format_resolved_value` called `str(resolved_value)` on the full list of email dicts **without any size bound** (the `max_length=5000` chars on the manifest only constrained the *template*, not the resolved value). The resolved `instruction` came out at **~114 K tokens** (~450 KB of raw HTML email bodies + headers).
3. `delegate_to_sub_agent_tool` passed that 114 K-token `instruction` to `SubAgentExecutor.execute()`, which ran its **bespoke mini-pipeline**: `_analyze_instruction → SmartPlannerService.plan → execute_plan_parallel → _synthesize_results`. The 114 K-token blob was **re-injected** into each of the three internal LLM calls (the analyser saw `expertise + instruction`; the planner saw `qi.original_query = instruction` + `__user_message = instruction` from the config; the synthesis saw `{instruction}` in its prompt template).
4. The sub-agent also **re-fetched the emails** (`get_emails_tool`) — it could not "see" that the data was already pasted into its instruction.

### Five structural gaps that allowed this

The delegation contract was articulated in prose (in the planner prompt's `{sub_agents_section}` and the manifest description), but **nothing enforced it structurally**:

1. **When to delegate**: planner's free choice, guided only by prose; no backstop.
2. **What reaches the sub-agent**: `instruction.max_length=5000` chars enforced **before** `$ref` resolution; resolver did `str(resolved_value)` unbounded after.
3. **Spend cap per execution**: `SubAgentTokenGuard` (file + tests) was never wired into `SubAgentExecutor` (the doc admitted it). `subagent_max_token_budget=50000` was therefore ignored.
4. **Pipeline overhead**: even a well-formed delegation cost 3 LLM calls (2 on the expensive model) of pure pipeline overhead before the actual task.
5. **HITL on delegation**: `delegate_to_sub_agent_tool.permissions.hitl_required = True` was declared, but `approval_gate_node` was hardcoded to always set `plan_approved=True` since v1.14.5 ("HITL streamlining"). The F6 code preparing the approval message (`_build_approval_request` "Enrich reasons for sub-agent delegation plans") was dead.

## Decision

Rewire the **ephemeral planner-delegation path** (`delegate_to_sub_agent_tool`) onto the existing generic `ReactSubAgentRunner` (ADR-062). Apply one defensive structural backstop (instruction size cap). Delete the legacy persistent `SubAgentExecutor` plumbing wholesale once the new path is in place (Phase 2). **Hold back on prescriptive "when-to-delegate" enforcement** (planner prompt anti-pattern guidance + heuristic veto) — initial Phase 1 attempts were rolled back as misaligned with the dominant use case (see §What was rolled back).

### Working hypotheses (used to frame the design, NOT all enforced in code)

- **H1**: A delegation only makes sense if a specialized expert persona would produce a **materially better** answer than the principal assistant doing the task itself. *Intent only — no robust code enforcement shipped (the heuristic attempted was rolled back).*
- **H2**: A plan may contain dependencies between sub-agents. The danger is the *size of the payload* injected into `instruction` after `$ref` resolution, not the topology. *Enforced by the post-resolution cap.*
- **H3**: A sub-agent = a single unitary expert task, not a re-planning mini-agent. The principal agent decomposes; the sub-agent executes. *Encoded in the prompt scaffold + tool filtering, not as a runtime check.*

### What shipped (and stays)

1. **Sub-agent execution rewired to `ReactSubAgentRunner`** (`delegate_to_sub_agent_tool`, ~270 → ~180 lines):
   - `llm_type="subagent"` (display label *Sub-Agent (ReAct)*), `prompt="subagent_react_prompt"`, tools = read-only subset, `recursion_limit = settings.subagent_default_max_iterations`, `display_name="sub-agent: <expertise>"`.
   - No more ephemeral `SubAgent` ORM record creation/cleanup. No more daily Redis budget on this path. No more manual token consolidation — `TokenTrackingCallback` reads `metadata["node_name_override"]` (`callbacks.py:450`) and attributes tokens to the parent tracker automatically.
   - Anti-recursion bug fix: `resolve_tools_for_subagent` now excludes `delegate_to_sub_agent_tool` itself from the sub-agent's toolset (was absent — latent risk).

2. **H2 instruction size cap** (the one structural defense that shipped): `parallel_executor._execute_tool_step` re-validates the resolved `instruction` against `SUBAGENT_INSTRUCTION_MAX_TOKENS_RESOLVED=3000` (`.env`-controllable) AFTER `$ref` resolution. Over-cap → step fails with `INVALID_INPUT` and a clear error message. Token estimate via `EstimationTokenCounter` (model-agnostic). **This is what kills the original 486 K incident pattern** (raw email bodies inlined via `$steps.X.<emails>`). It does NOT prevent expensive but well-formed delegations (see §Open design problem).

3. **Pipeline overhead reduced**: the sub-agent's `query_analyzer + SmartPlannerService + synthesis` chain is no longer in the path. A single ReAct loop, bounded by `recursion_limit`.

4. **Persistent path deleted (Phase 2)**: legacy `SubAgentExecutor`, `/sub-agents` REST API, `SubAgent` ORM table, daily budget, stale-recovery scheduler, user toggle — all removed. See §Phase 2 completion below.

### What was rolled back (2026-05-14)

Two pieces of Phase 1 were reverted after a closer look at the actual use-case space showed them mis-targeted. The codebase no longer carries them.

- **Planner prompt anti-pattern guidance** (the `_build_sub_agents_section` rewrite). The new prose introduced "DO NOT DELEGATE for data retrieval + summarization" and a BAD/GOOD example forbidding `[fetch, delegate]`. This actively sabotages the dominant use case ("apply an expert persona to data the principal can fetch cheaply"), which legitimately wants `[fetch, delegate(persona, digest)]`. The planner was either confused into over-specifying queries (e.g. adding `label:INBOX` that excluded archived results) or skipping delegation entirely. Reverted to the prior prose.
- **Veto heuristic in `semantic_validator`** (`validate_sub_agent_delegation_justified` + `POINTLESS_SUB_AGENT_DELEGATION` issue type + `SUBAGENT_VETO_POINTLESS_ENABLED` setting). The heuristic used `query_intelligence.domains` as its mono-domain signal, but the query_analyzer adds incidental domains (e.g. mentioning "ma femme" → `["email", "contact"]` even when the plan only uses email tools). The heuristic therefore abstained exactly on the cases it was supposed to catch (planner emitting `[fetch_email, delegate(persona, $ref)]`) while occasionally firing on legitimate cases. The right signal is the **shape of the plan executed**, not the declared intent of the query — that redesign is deferred to a follow-up.

The `SUBAGENT_VETO_POINTLESS_ENABLED` environment variable is removed. Tests covering the rolled-back pieces (`test_semantic_validator_pointless_delegation.py`, `test_f6_prompt_suppression.py`) are deleted.

### Open design problem (deferred)

The instruction cap defends against one specific pathological pattern (raw payload inlined via `$ref`). It does NOT address the more common cost driver observed in functional testing: a well-formed `[fetch_metadata, delegate(persona, instruction)]` plan where the sub-agent then refetches per-message bodies via `get_email_details_tool` over 5–8 ReAct iterations. Each iteration loads a ~28 K-token scaffold (system prompt + 86 read-only tool descriptions). Total ~250 K tokens processed, most cache-hit so cheap (€0.04) but still expensive in absolute compute and latency.

A proper redesign — based on a real use-case taxonomy (expert-cadrage on fetched data vs. fan-out research vs. autonomous exploration vs. pure expertise) — is the subject of a separate follow-up design loop. Until then, delegation behaves as it did before the incident: it works, it can be costly on certain plans, and the only hard guard is the size cap on resolved instructions.

### Out of scope

- **HITL on delegation**: `approval_gate_node` stays a passthrough — pre-existing regression from v1.14.5 left in place. Re-activation is a separate concern.

## Consequences

### Positive

- The exact 486 K-token / €0.56 / 95 s incident pattern (raw email bodies inlined via `$steps.X.<emails>` reference resolution into a 114 K-token instruction) is structurally prevented by the post-resolution cap. The `$ref` resolver can no longer ship arbitrarily large payloads into a sub-agent's `instruction`.
- The ephemeral execution path now reuses code battle-tested by `browser_task_tool` and `mcp_server_task_tool` (`ReactSubAgentRunner`) — less surface area, fewer bugs.
- Token attribution per sub-agent appears in the debug panel under `"sub-agent: <expertise>"` automatically (via `node_name_override`) — no separate `MessageTokenSummary` row, no manual consolidation.
- The codebase carries a single execution path and a single feature gate (`SUB_AGENTS_ENABLED`) after Phase 2 cleanup.

### Negative / accepted

- **No structural guard against high-cost-but-well-formed delegations.** The cap only catches the raw-payload pattern. A plan like `[get_emails_tool(metadata-only), delegate(persona, "analyse $steps.step_1.<digest>")]` passes the cap, the sub-agent then re-fetches bodies in 5–8 ReAct iterations, and total processed tokens reach 200–300 K (mostly cache hits, so cost stays low but compute and latency don't). Cf. §Open design problem.
- **Phase 1 over-promised a "materially better" enforcement that was never delivered in a robust form.** The veto heuristic and the prompt anti-pattern guidance were rolled back. The system trusts the planner LLM to make reasonable delegation decisions without runtime backstop, exactly as before the incident — but with the size cap as the only hard guard.
- **HITL on delegation remains a passthrough** — pre-existing regression from v1.14.5; out of scope here.

### Phase 2 completion (2026-05-13)

Once Phase 1 confirmed that the ephemeral ReAct path was sufficient on its own — the planner self-corrects under H1 and the cap kills the raw-payload pattern at its source — the legacy F6 plumbing was deleted wholesale the same day. Precondition audit on prod: `sub_agents` table at 0 rows, `users.sub_agents_enabled` was the default `true` for 100% of users (no observable user intent to opt out), no UI consumer for any of the persistent surface. Plan: `docs/superpowers/plans/2026-05-13-sub-agent-phase-2-cleanup.md`.

**Backend code removed**: `domains/sub_agents/{router,service,repository,executor,token_guard,schemas,models}.py`, the `/sub-agents` REST API, `subagent_synthesis_prompt.txt`, the `SubAgent` ORM model and all its registrations (`alembic/env.py`, `infrastructure/database/registry.py`, `main.py` lifespan, `tests/conftest.py`), and the stale-recovery scheduler job. `delegate_to_sub_agent_tool` no longer touches the DB on its main path (no `UserService` / `get_db_context` / `parse_user_id` imports).

**Configuration trimmed**: 8 obsolete env vars removed (`SUBAGENT_MAX_PER_USER`, `SUBAGENT_MAX_CONCURRENT`, `SUBAGENT_DEFAULT_TIMEOUT`, `SUBAGENT_MAX_TOKEN_BUDGET`, `SUBAGENT_MAX_TOTAL_TOKENS_PER_DAY`, `SUBAGENT_MAX_CONSECUTIVE_FAILURES`, `SUBAGENT_STALE_RECOVERY_INTERVAL_SECONDS`, `SUBAGENT_MAX_DEPTH`) from `core/constants.py`, `core/config/agents.py`, `.env.example` and `.env.prod.example`. Combined with the rollback of `SUBAGENT_VETO_POINTLESS_ENABLED` (see §What was rolled back), only three sub-agent env vars remain: `SUB_AGENTS_ENABLED`, `SUBAGENT_DEFAULT_MAX_ITERATIONS`, `SUBAGENT_INSTRUCTION_MAX_TOKENS_RESOLVED`.

**User toggle removed (Option B)**: `users.sub_agents_enabled` column, `PATCH /auth/me/sub-agents-preference` endpoint, `SubAgentsPreferenceRequest/Response` schemas, the i18n `sub_agents_preference_updated` API message, the per-user preference check in `delegate_to_sub_agent_tool`, the `sub_agents_enabled` field in `apps/web/src/lib/auth.tsx`, and the orphan `SubAgentsSettings.tsx` component. Delegation is now gated only by the global `SUB_AGENTS_ENABLED` feature flag.

**i18n**: the entire `sub_agents.{settings,templates}` block was dropped from all 6 locales (en, fr, de, es, it, zh). Parity preserved at 5297 keys per locale.

**Migrations**: `phase_2_cleanup_001` drops the `sub_agents` table + the unused `message_token_summary.parent_run_id` column; `phase_2_cleanup_002` drops `users.sub_agents_enabled`.

After Phase 2 there is **a single execution path** (`delegate_to_sub_agent_tool` → `ReactSubAgentRunner`) and **a single feature gate** (`SUB_AGENTS_ENABLED`). The two negative trade-offs originally listed above — "two engines coexist temporarily" and "Phase 2 candidate" disclaimers throughout the codebase — are resolved.

## Implementation

Shipped along checkpoints A-J on branch `feat/sub-agent-react-redesign`:

| Checkpoint | Phase | What ships |
|---|---|---|
| **A** | 1 | Rewrite of `delegate_to_sub_agent_tool` onto `ReactSubAgentRunner` + anti-recursion fix in `resolve_tools_for_subagent` + `subagent_react_prompt.txt` scaffold + `SUBAGENT_DEFAULT_MAX_ITERATIONS` reused as `recursion_limit`. |
| **C** | 1 | H2 post-resolution `instruction` cap (`SUBAGENT_INSTRUCTION_MAX_TOKENS_RESOLVED=3000`). |
| **D** | 1 | LLM type label renamed `Sub-Agent (ReAct)` (6 locales) + manifest description/cost profile aligned with rewrite. |
| **F+G** | 2 | REST router + executor + scheduler + obsolete settings/constants/env vars/tests removed; Alembic migration `phase_2_cleanup_001` drops `sub_agents` table + unused `message_token_summary.parent_run_id`. |
| **H** | 2 | Option B: user toggle removed (component, endpoint, schemas, ORM column, migration `phase_2_cleanup_002`, preference check); i18n `sub_agents.{settings,templates}` block stripped from 6 locales. |
| **J** | rollback (2026-05-14) | Veto + planner prompt anti-pattern guidance removed (`validate_sub_agent_delegation_justified`, `SUBAGENT_VETO_POINTLESS_ENABLED`, `_build_sub_agents_section` rewrite, related tests). See §What was rolled back. |

Note: original checkpoints B (H1 prompt rewrite + veto) and E/I (claimed-shipped docs) are superseded by J. The codebase no longer carries the veto or the rewritten prompt section.

Ruff/black/mypy strict clean, i18n parity preserved across all 6 locales (5297 keys). Functional validation in Docker dev: container restart healthy after each checkpoint AND after the rollback.

## Related env vars (`.env`-controllable)

- `SUB_AGENTS_ENABLED` (default `true`) — feature flag for the whole subsystem.
- `SUBAGENT_DEFAULT_MAX_ITERATIONS` (default `SUBAGENT_DEFAULT_MAX_ITERATIONS_DEFAULT` in `core/constants.py`) — reused as the ReAct loop's `recursion_limit`.
- `SUBAGENT_INSTRUCTION_MAX_TOKENS_RESOLVED` (default `SUBAGENT_INSTRUCTION_MAX_TOKENS_RESOLVED_DEFAULT` in `core/constants.py`) — H2 cap on the `instruction` of `delegate_to_sub_agent_tool`, enforced by the tool itself since the amendment below.

## Amendment 2026-10-13 — both modes are told the same facts, and the tool holds the cap

The planner read the manifest — « the sub-agent has NO user-data tools » — while
the ReAct loop, which binds the `@tool` schema and never the manifest (ADR-310),
read « the sub-agent has its own read-only tools and fetches what it needs ». The
expert's tools are the configured whitelist (web research by default), so a ReAct
turn could delegate « analyse my last e-mails » to an expert that could not read
one. And the cap on `instruction` was checked by the pipeline executor alone,
after reference resolution: a ReAct delegation had no bound at all.

1. **One set of facts, in each mode's words** (`domains/sub_agents/instruction_contract.py`):
   `expert_reach()` names the expert's tools from the whitelist and says it cannot
   read the user's data — a claim made only while the whitelist stays within the
   research tools LIA ships (its default): an operator who names another tool gets
   the list without the claim, since a prompt states what the code holds (ADR-284);
   `instruction_description(in_plan=...)` adds how the data is
   handed over — `$steps.step_N.<field>` references in a plan, the facts written
   in by a loop — and, for the loop only, the cap: the planner's delegation
   section already publishes it (one authority, prompt audit 2026-09-12).
2. **The tool enforces the cap** (`sub_agent_tools._oversized_instruction`),
   `INVALID_INPUT` naming the estimate and the cap, before any model runs. In a
   plan the references are resolved by the time the tool runs, so the executor's
   own check was removed rather than kept as a second implementation. The
   delegation is `mutation_policy="read"`: no confirmation precedes it in a plan;
   in ReAct the cost pause (`hitl_required`) still comes first, so an oversized
   instruction is refused after the person accepted the cost — a rare safety net,
   since a loop writes its instruction itself.

Guards: `test_sub_agent_instruction.py` (same reach in both, cap and tools stated to
the loop, refusal before the runner, a run under the cap), and the delegation
section's own `TestManifestAgreesWithTheSection`.


## Amendment 2026-10-13 (b) — a sub-loop's budget end is a closing pass, never an answer of LangGraph's

Production, 2026-10-13: a delegated expert ran nine rounds of searches (most of its
page reads refused: rate limit, network, 403), and its tenth answer — the model
still asking for a page — was REPLACED by the prebuilt agent's own sentence,
« Sorry, need more steps to process this request. » (47 characters). The runner took
it for the answer, the delegation reported it as a success, and the principal
answered « no sub-agent delivered an expert analysis ». Measured on the installed
`create_react_agent` (langgraph-prebuilt 1.1.0) with a model that never concludes:
`recursion_limit` counts graph STEPS, so `SUBAGENT_DEFAULT_MAX_ITERATIONS=20` buys 10
model calls and 9 tool rounds, the last call's answer substituted; an ODD limit raises
`GraphRecursionError` instead (`SKILLS_REACT_RECURSION_LIMIT` is 25). Two runs of the
runner in sixteen over seven days of production ended on the sentence (this one,
and a browser task). The same runner serves the browser agent, the MCP iterative
tasks and the skill runner, whose answer is shown to the person verbatim.

1. **The last call writes** (`tools/react_runner_closing.py`): the runner uses
   native `create_agent` and model middleware. Once fewer than
   `CLOSING_BELOW_REMAINING_STEPS` (3) steps remain, the call gets NO tool and the
   loop's history flattened into one message after the unchanged system prompt —
   the task, every call with its arguments, every result wrapped as external
   content (a tool output moved into a user message would otherwise read with the
   asker's authority), and a versioned directive (`react_runner_closing_prompt.txt`,
   scaffolds in `react_runner_closing_lines.txt`). A request carrying neither tool
   definitions nor tool blocks is one every provider accepts. If the reply still
   proposes a call, the middleware empties it before dispatch: no extra tool
   runs, no promise is reported as an answer. Billed usage and the provider's
   truncation verdict survive. The same guard applies to a run with no tools.
   Nothing is
   cut from the log: the closing call reads what the previous call read. It
   REPLACES the call LangGraph threw away — no extra model call; on the tenth
   call above, about 17 K input tokens move from cached to uncached.
2. **What a limit buys is one arithmetic** (`tools/react_runner_budget.py`):
   `model_calls_for(R)` = R//2, `tool_rounds_for(R)` = R//2 − 1, for even and odd
   limits alike. A limit of 1 can never end and, below 4, no tool round fits
   before the closing pass: `subagent_default_max_iterations` refuses 1 (`ge=2` —
   an expert may answer from its instruction alone), the acting loops refuse
   less than one round (`browser_react_max_iterations` and
   `mcp_react_max_iterations`, `ge=4`; a limit of 3 used to run one round and
   then raise). Their descriptions say STEPS rather than iterations.
3. **The result says how the run ended**: `SubAgentOutcome` (`answered`, `empty`,
   `error`) plus `closed_on_budget`, `truncated` (the provider's own verdict,
   `is_output_truncated` — kept on an EMPTY run too, where a thinking model spent
   its output budget before writing a word, ADR-285, and said so to the reader)
   and `failure_kind` (`classify_llm_error`), counted by
   `subagent_outcomes_total{agent_name,outcome}` (dashboard 19) and logged on
   `react_sub_agent_complete`.
4. **Every reader reads the outcome, never the text** (ADR-303): the `"Error: …"`
   sentinel is gone — a failed run carries no text, since an exception's text can
   quote the request — and the five readers map the outcome once each:
   the delegation answers a failure coded by the failure's kind
   (`failure_code_of`: a limit or a timeout reads « retry later », a configuration
   error does not) and an answer whose partial travels in its own fields
   (`budget_exhausted`, `output_truncated` — `partial_fields`); the browser task
   and the MCP task say how many steps ran and, for MCP, keep the widgets the loop
   produced before it failed (it acted: hiding them would hide a real effect); the
   MCP zero-iteration retry replays an ANSWER only, never a provider failure; the
   skill runner counts a failure it caught as `error`, never as « no tool called ».

5. **The expert and its planner are told what runs** (ADR-284, ADR-184): the
   planner's delegation section published the step limit as « at most N model
   calls » — twice the calls the loop allows — and now publishes
   `model_calls_for(limit)`; the expert's prompt listed two tools whatever its
   whitelist bound, set « 1 to 3 rounds » in prose against a budget it never
   stated, and now receives the tools it is bound to after the read-only filter
   (`research_tools`) and `max_tool_rounds`, with the closing pass announced. The
   closing directive treats the WHOLE research block as a record, never an
   instruction: the model's own notes and call arguments move into a user message
   there, and a page can have steered them. It
   is also told that a source or tool that refused it — a rate limit, a page too
   large, a connector the person never activated — stays refused for the task; a
   directive, which nothing enforces. Both values sit before the cache marker:
   one per deployment.

The managed step allowance is private to state, omitted from native agent IO;
`RemainingStepsManager` remains its final annotation, as LangGraph requires.
The middleware wraps the existing model node and adds no graph step. Native
compiler tests preserve both parities, contexts, callbacks and store propagation;
deprecation warnings are treated as errors. These are scripted-model graph
proofs, not new paid-provider qualification.

Guards: `test_react_runner_closing.py` drives the REAL native agent graph — every
earlier runner test patched it away — and was proven by mutation: without the
closing pass 13 of its cases fail, the production case first; at LangGraph's own
threshold (2) exactly the four odd limits fail. Measured on dev with DeepSeek on the
proof account (0.0071 € for two runs): a limit of 6 ran two rounds, the refused
tools were not called again, and the closing pass wrote a 6 477-character
deliverable naming each source that failed and why.

Known and written: the closing pass rests on `create_react_agent`'s dynamic model
and its managed `remaining_steps`. That function is deprecated since LangGraph 1.0
(removal announced for 2.0, in favour of `langchain.agents.create_agent`): the
migration must carry the closing pass over — a model-call middleware choosing a
tool-less call on the last step — and keep these tests driving the real loop.
