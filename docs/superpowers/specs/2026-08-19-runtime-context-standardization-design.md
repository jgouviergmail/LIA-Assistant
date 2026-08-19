# Runtime Context Standardization (and the Agent Server verdict) — Design Specification

- **Date**: 2026-08-19
- **Status**: Approved design, pre-implementation
- **ADR**: ADR-231 (to be written in Lot 0; ADR-228 and ADR-230 are taken by parallel workstreams, ADR-229 is the capability map)
- **Origin**: an opportunity study of "LangChain Agent Server v0.13 — AAA and context standardization"
- **Scope**: refute or confirm Agent Server adoption; then standardize the runtime context LIA already half-passes, on OSS LangGraph alone
- **Patterns mirrored**: registry completeness assert (ADR-085), single-chokepoint config construction, shrink-only ratchets, `parse_user_id` normalization replaced by a typed source

---

## 1. Goal

Answer one question with evidence — *should LIA adopt LangChain's Agent Server?* — and
convert the part of that question that survives into shipped work.

The answer splits in two:

1. **Agent Server itself: NO-GO.** Five independent blockers, each verified.
2. **The "context standardization" half: GO, and it needs nothing from Agent Server.**
   `context_schema` and `Runtime[ContextT]` ship in the MIT `langgraph` 1.2.11 already
   installed. LIA *already* passes a `context=` payload that nothing reads.

A third question — exposing LIA over MCP or A2A — was instructed on request and is
resolved in section 7.

---

## 2. Evidence base

Every claim below was produced by reading this repository or by running a simulation
against `apps/api/.venv` (langgraph 1.2.11, langchain 1.3.15, langchain-core 1.5.5).
Ten simulations were run; the harness is throwaway and lives outside the repository.

| Sim | Question | Result |
|---|---|---|
| A | Does runtime context reach nodes and subgraphs without a server? | Yes, both |
| A4 | Is context written into the checkpoint? | **No** — no msgpack round-trip |
| A5 | Resuming an interrupt without re-passing `context`? | **Succeeds silently**, `runtime.context` is `None` |
| B1/B2 | Is a plain dict accepted as context? A missing required field? | Coerced; a missing field raises `TypeError` at invoke time |
| B3 | No `context` at all, with a schema declared? | **Accepted**, context is `None` — silent |
| C1/C2/C3 | Does `get_runtime()` survive `gather`, `to_thread`, `create_task`? | Yes for all three |
| C5 | Five concurrent runs with distinct contexts? | Fully isolated, no leak |
| D | Does in-place mutation of `config["configurable"]` leak? | **No** — LangGraph hands each node a fresh copy |
| E | LIA's exact current shape: `context=` with no `context_schema`? | Accepted; context is an untyped dict; tools still see `None` |
| F | Non-`None` context under a bare `ToolRuntime` annotation? | **Pydantic serializer warning on every tool call**. Clean only with `ToolRuntime[Ctx, ...]` plus a real instance |
| G | Does the annotation form change the LLM-visible schema? | Bare and `Annotated` both hide `runtime`; a bare `ToolRuntime \| None = None` makes the tool unconvertible |
| H | Do the real tools survive schema conversion? | 53 modules, **109 tools, 0 failures, 0 injected-argument leaks** |
| I | What does an `mcp` 2.0.0 server demand for auth? | 401 plus a spec-shaped `WWW-Authenticate` with `resource_metadata`; RFC 9728 metadata served automatically |
| J | Does it mount inside FastAPI and answer? | Yes: 401 / 401 / **200 with the tool list**; two traps found (421 on an unlisted `Host`; metadata unreachable under a mount) |
| K | Is the caller identity isolated under concurrency? | **8 concurrent callers, 8 identities, zero cross-talk**; invalid token rejected 401 |
| L | What could an MCP client do without HITL? | 105 instances / 82 manifests: 63 read-only, 14 draft-based (inert), **4 unguarded direct mutations** |
| M | Does the step-2 intermediate state warn? | All four quadrants measured. `ToolRuntime[Ctx, ...]` + `None` **clean**; + instance **clean**; bare + instance **warns**. The prescribed ordering is the only clean path |
| N | Are live run dependencies copied by LangGraph? | **No.** Object identity of an `asyncio.Queue` and an opaque object is preserved across node, subgraph and tool; a node-side mutation is visible to the caller; the queue received its write |
| O | Does `context_schema` change the graph's public surface? | No. `config_schema` stays non-`None` (the existing assertion keeps passing) and the input JSON schema is unchanged |
| P | Do production checkpoints survive the migration? | **Yes.** A thread interrupted on today's graph resumes on the migrated graph; **rollback also works**; checkpoint key structure identical. But resuming *without* context succeeds **silently** |
| P-bis | Is the context really absent from the checkpoint? | **Yes**, retested with a sentinel never written to state: absent from the latest checkpoint and from all three history entries. (The first attempt was a self-inflicted false positive — the test node had written the value into state.) |
| Q | Is the F6 legacy branch reachable? | **No.** 105 tools inspected: exactly one lacks a `runtime` parameter and it carries no `@auto_save_context`; **zero** declare a `config` parameter. The branch requires both |

---

## 3. Agent Server — the verdict and why

### 3.1 What it actually is

`langgraph-api`: an HTTP runtime with a durable task queue, persisting assistants,
threads, runs, crons and a store, plus A2A and MCP endpoints. It loads *your* graph
into *its* process (`langgraph.json`, key `graphs`, value `./agent.py:graph`), and
`HttpConfig.app` even mounts your own FastAPI inside it.

### 3.2 The five blockers

1. **Licence.** `langgraph-api` is **Elastic License 2.0** (PyPI metadata, and the
   `LICENSE` file inside the `0.13.0rc5` wheel). LIA is **AGPL-3.0-or-later**
   (`LICENSE`, `apps/api/pyproject.toml:5`, both `package.json`). ELv2 adds
   restrictions AGPL section 10 forbids imposing on downstream recipients, and the
   deployment model puts AGPL graph code inside an ELv2 process — a combined work,
   not mere aggregation. This is an owner decision, not a legal opinion, but it is
   structural rather than cosmetic.
2. **Maturity.** v0.13 has **no stable release**: the newest artifact is
   `0.13.0rc5` (2026-08-17); the current stable line is `0.12.6`. LIA's qualified
   release pipeline (ADR-215) cannot ship a release candidate.
3. **Redundancy.** Agent Server's threads, runs, assistants, crons and queue duplicate
   subsystems LIA already owns and has hardened: `conversations` (a 1207-line
   repository, messages, feedback, archives, GDPR export), `background_runner`,
   `scheduled_actions` with `FOR UPDATE SKIP LOCKED`, APScheduler behind leader
   election, `AsyncPostgresStore`, and an SSE stream with keepalive, gates and HITL.
4. **AAA does not transfer.** `langgraph_sdk.Auth` governs exactly five resources
   (runs, threads, crons, assistants, store). It knows nothing of LIA's device
   sessions, step-up re-auth, WebAuthn/TOTP, peers, usage limits, or the roughly 70
   routers in `apps/api/src/api/v1/routes.py`. Adopting it yields two authorization planes, not
   one. `langgraph/runtime.py::ServerInfo` documents the boundary: "None when running
   open-source LangGraph without LangSmith deployments."
5. **Resources.** Production is 17 services on a Raspberry Pi 5 — 3376 MB reserved,
   12736 MB of limits, 8.6 CPU of limits — with the API alone reserving 2 GB. A
   second Python runtime loading the same graph, plus grpcio, protobuf and uvloop,
   does not fit.

### 3.3 The dev-only variant, also rejected

`langgraph dev` for LangGraph Studio is technically possible and licence-defensible
(no distribution). But `build_graph()` depends on the global agent registry that the
whole lifespan initializes, so a `langgraph.json` factory would duplicate the boot
path and have to be kept in sync — to obtain a debugging UI that ADR-209 already
shipped in-house.

### 3.4 What is transposable

Only the idea of a typed runtime context. It is available in MIT LangGraph today.
That is the remainder of this specification.

---

## 4. Defects proven in the existing code

These stand on their own; they are not consequences of any migration.

| # | Defect | Location |
|---|---|---|
| **F1** | `context=context_dict` is a dead payload: passed on both `graph.astream` calls, **read zero times** in `src/`. Its comment claims it feeds `ToolRuntime`, which F2 disproves. | `apps/api/src/domains/agents/services/orchestration/service.py:810`, `:889`, `:903` |
| **F2** | `ToolRuntime.context` is hard-wired to `None` at the only construction chokepoint (shared by pipeline and ReAct) and at one ad-hoc site. The run carries a context; no tool can ever see it. | `apps/api/src/domains/agents/orchestration/parallel_executor.py:1972`, `apps/api/src/domains/agents/services/skill_location_context.py:73` |
| **F3** | No `context_schema` on the graph, so the context is a raw dict with no validation and no MyPy coverage. | `apps/api/src/domains/agents/graph.py:464` |
| **F4** | Three competing context planes: `configurable` (about 25 keys across 43 files), the dead `context=`, and 9 ContextVars plus `_current_runtime`. | `apps/api/src/core/context.py`, `apps/api/src/domains/agents/tools/base.py:112` |
| **F5** | Four private keys (`__deps`, `__browser_context`, `__user_message`, `__side_channel_queue`) travel in an untyped bag — an enforced but unpublished contract, the ADR-184 class. | `apps/api/src/domains/agents/services/orchestration/service.py:758` |
| **F6** | Two dead legacy branches read `config.get("store")` while the value is written at `configurable["store"]` — wrong level, and unreachable anyway: **zero tools** declare a `config: RunnableConfig` parameter. | `apps/api/src/domains/agents/context/decorators.py:141`, `:282` |
| **F7a** | `ReactSubAgentRunner` hardcodes `"fr"` and `"UTC"` fallbacks, where the canonical chokepoint uses `settings.default_language` and `DEFAULT_TIMEZONE`. Direct violation of the i18n and constants-centralization rules. | `apps/api/src/domains/agents/tools/react_runner.py:274-275` |
| **F7b** | The same runner re-projects the parent context by hand, writing 7 keys of which only 6 are inherited from the parent's 17 (the 7th, `__parent_thread_id`, is added). **Latent, not active**: the default sub-agent whitelist is `perplexity_search_tool,brave_search_tool,fetch_web_page_tool`, none of which reads the dropped keys or carries a `context_domain`. The whitelist is `.env`-configurable, so adding a location-aware tool would silently degrade geolocation. | `apps/api/src/domains/agents/tools/react_runner.py:268-280`, `apps/api/src/core/constants.py:4433` |
| **F8** | One identity, two keys, two types. `configurable[user_id]` receives a raw `uuid.UUID` at the chokepoint but a `str` from the parallel executor. `langgraph_user_id` duplicates the same value as a string across **25 read sites**, justified by a comment about LangMem — **`langmem` is not installed**. `parse_user_id` accepting `str \| UUID` exists only to absorb the resulting ambiguity. | `apps/api/src/domains/agents/services/orchestration/service.py:317`, `:760-761`, `apps/api/src/domains/agents/orchestration/parallel_executor.py:1125`, `apps/api/src/domains/agents/tools/runtime_helpers.py:158` |
| **F9** | No CI gate covers the LLM-visible tool schema. `apps/api/tests/unit/domains/agents/tools/test_tool_registry_smoke.py` never calls `convert_to_openai_tool`; **no file in `src/` or `tests/` does**; the three tests using `bind_tools` pass through a fake model that ignores tools. Nothing would catch an injected argument leaking to the LLM, nor a tool becoming unconvertible — a failure mode Sim G proves reachable. | `apps/api/tests/unit/domains/agents/tools/test_tool_registry_smoke.py`, `apps/api/tests/unit/domains/agents/graphs/test_base_agent_builder_invocation.py:54` |
| **F10** | **HITL is enforced in graph nodes, never inside tools.** ReAct interrupts before execution on `manifest.permissions.hitl_required`; the pipeline confirms after execution on the tool's `requires_confirmation` output, and the draft is executed only in `response_node`. Any caller that invokes a tool outside the graph — an MCP client, a sub-agent, a script — gets **no confirmation at all**. Measured: 4 catalogued mutations have neither guard and mutate immediately. This is not a new bug, it is a documented architectural boundary; it becomes a defect the moment tools are exposed outside the graph. | `apps/api/src/domains/agents/nodes/react_nodes.py:712`, `apps/api/src/domains/agents/nodes/response_node.py:2467`, `apps/api/tests/unit/domains/agents/tools/test_hitl_required_consistency.py` |

---

## 5. Rejected findings — do not "fix" these

Recorded so no future session re-opens them.

| Suspicion | Verdict |
|---|---|
| The planner assigning `configurable["oauth_scopes"]` mutates shared state | **Safe.** Sim D: LangGraph copies `configurable` per node. No caller, cross-run, or sibling-branch leak. The value reaches `skill_bypass` because it travels down the planner's own call tree. |
| Eleven bare `runtime: ToolRuntime \| None` signatures break their tools | **False.** All are private underscore-prefixed helpers or methods; none is a `@tool`. Sim H: 109 tools, 0 conversion failures. |
| The 113 `Annotated` versus 39 bare annotation mix is harmful | **False.** Sim G: both forms correctly hide `runtime`. Inelegant, not incorrect. |
| A `RunnableConfig` carrying only `thread_id` starves the context | **False.** Those three sites only call `aget_state` or read a checkpoint; `thread_id` is sufficient. |
| Scheduled actions bypass the chokepoint | **False.** They call `AgentService.stream_chat_response` (`apps/api/src/infrastructure/scheduler/scheduled_action_executor.py:344`). |
| `@auto_save_context` is never applied | **False.** Applied through `connector_tool(context_domain=...)` (`apps/api/src/domains/agents/tools/decorators.py:210`). |
| `__parent_thread_id`, `resolved_person_names`, `node_name` are orphan keys | **False.** All written elsewhere (`apps/api/src/domains/agents/tools/react_runner.py:273`, `apps/api/src/domains/agents/semantic/param_guard.py:128`). |
| LangChain dependencies are stale | **False.** langgraph, langchain, langgraph-checkpoint, langgraph-checkpoint-postgres, langgraph-prebuilt, langgraph-sdk, langchain-anthropic and langchain-google-genai are exactly current. Only `langchain-core` 1.5.5 to 1.5.6 and `langchain-openai` 1.5.1 to 1.5.2 lag. |
| The context leaks into the checkpoint (simulation P5) | **False, and it was my own test's fault.** The value appeared in the blob because the test node wrote it into state. Retested with a sentinel never written: absent everywhere. |
| `@pytest.mark.unit` violates `--strict-markers` (`unit` is absent from `apps/api/pyproject.toml`) | **False.** It is registered at runtime by `apps/api/tests/conftest.py:1206`; 1258 usages collect cleanly. |
| The frontend has a contract on the runtime context | **False.** Every `configurable` hit under `apps/web/` is a JavaScript property descriptor (`Object.defineProperty(..., {configurable: true})`). Lots 0 to 2 are backend-only. |

### Unused LangGraph primitives, evaluated and declined

| Primitive | Why not |
|---|---|
| `RunControl` and `request_drain` | LIA already does better: `drain_chat_producers` with `background_runs_drain_timeout_seconds` (`apps/api/src/infrastructure/startup/shutdown.py:73`) plus a cooperative Redis cancel watcher (`apps/api/src/domains/agents/api/background_runner.py:147`). No observed symptom. |
| `TimeoutPolicy` and `runtime.heartbeat()` | Timeouts already applied at the LLM layer (ADR-220/221) and via `asyncio.wait_for` where needed. `heartbeat` has no consumer outside `TimeoutPolicy`. |
| `CachePolicy`, `defer=True`, `ExecutionInfo`, `TracePolicy` | No measured pain. Adding them is speculative complexity. |

---

## 6. Design — `LiaRuntimeContext`

### 6.1 The contract

A frozen dataclass in a dedicated module (never inside
`apps/api/src/domains/agents/services/orchestration/service.py`, which is frozen at **713 SLOC** — the ratchet
only goes down). It carries the seventeen values the chokepoint builds today (verified by AST over
`RunnableConfig(configurable={...})` at `apps/api/src/domains/agents/services/orchestration/service.py:757`), with two
corrections baked in:

- `user_id: uuid.UUID` is **canonical and unique**. `langgraph_user_id` disappears;
  its 25 read sites read the typed field. This closes F8 at the source and lets
  `parse_user_id` shrink to the boundaries that genuinely receive foreign input.
- The four private keys become named, typed, documented fields — closing F5.

### 6.2 Data flow

The context is built in **one** place (the existing chokepoint) and injected at
**three**: `graph.astream`, `_build_tool_runtime`, `skill_location_context`. Nodes read
it through `Runtime[LiaRuntimeContext]`, tools through
`ToolRuntime[LiaRuntimeContext, ...]`, nested helpers through `get_runtime()`.

`configurable` remains the source of truth until the final migration wave, so every
intermediate state is deployable.

### 6.3 Ordering — not negotiable

Sim F proves that a non-`None` context under a bare `ToolRuntime` annotation emits a
Pydantic serializer warning **on every tool call**. Therefore:

> **Parameterize the 117 signatures before filling the context.**
> The reverse order floods stderr in CI and in production.

Sim B3 proves an absent context yields `None` silently, including on HITL resume.
Therefore the completeness assert lands before any read.

### 6.4 Error handling

A missing or incomplete context fails **loudly** at the first node, following the
ADR-085 doctrine: the app refuses to proceed rather than degrade. There is no fallback
path, because a silent `None` here is exactly the failure mode this work exists to
remove.

---

## 7. MCP and A2A — instructed, then split

### 7.1 A2A: NO-GO, with a reason

A2A is an interoperability protocol between agent systems from *different*
deployments. LIA's `peers` domain is **intra-instance and human-to-human**: discovery,
connection request, accept, decline, blocks, shares, address visibility, and a
**stateless relay** where user A's assistant hands a message to user B's assistant
inside the same database (`apps/api/src/domains/peers/`, `apps/api/src/domains/agents/tools/peers_tools.py:80`). No
cross-deployment agent interoperability exists or is planned. `a2a-sdk` is Apache-2.0
and therefore AGPL-compatible, but its base install adds five runtime dependencies of
which `json-rpc` and `culsans` are absent from the lock — cost with no use case.

### 7.2 MCP server: feasible, but gated by authentication and by HITL

#### What was verified

`mcp` 2.0.0 is **already in the lock** (MIT). `MCPServer.streamable_http_app()` returns a
Starlette app that mounts into the existing FastAPI. Four simulations were run against it:

| Sim | Question | Result |
|---|---|---|
| I | What does the server demand for auth? | With `AuthSettings`, an unauthenticated call gets **401** plus a spec-shaped `WWW-Authenticate: Bearer ... resource_metadata="..."`, and RFC 9728 Protected Resource Metadata is served automatically |
| J | Does it mount inside FastAPI? | Yes — `/health` and `/mcp-server/mcp` coexist; the round trip is 401 / 401 / **200 with the tool list** |
| K | Does the caller identity reach tool code, isolated? | Yes — `get_access_token()` inside a tool; **8 concurrent calls with 8 identities and staggered awaits: zero cross-talk**; an invalid token is rejected 401 |
| L | What could an MCP client actually do? | See the HITL section below |

Two deployment traps were surfaced by the simulations and must be in the plan:

1. **DNS-rebinding protection is on by default.** With an unlisted `Host`, every request
   is rejected **421 Misdirected Request**. Behind the Cloudflare tunnel the allowed
   hosts and origins must be configured explicitly (`TransportSecuritySettings`).
2. **Mounting breaks discovery.** RFC 9728 metadata must live at the origin root
   (`/.well-known/oauth-protected-resource/<path>`). Mounted under `/mcp-server`, it is
   served at `/mcp-server/.well-known/...` where **no client looks** — verified: root
   returns 404, mount path returns 200. LIA's own MCP client proves the expectation, it
   probes `{base_url}/.well-known/oauth-protected-resource`
   (`apps/api/src/infrastructure/mcp/oauth_flow.py:226`). The well-known routes must be
   re-exposed at the root, or the `401` must carry an absolute `resource_metadata` URL
   (Anthropic documents the latter as the reliable path).

#### The blocking constraint is not authentication — it is HITL (F10)

**LIA's human-in-the-loop is enforced in graph nodes, never inside tools.** Two
mechanisms, both outside the tool:

- ReAct interrupts *before* execution on `manifest.permissions.hitl_required`, in
  `react_execute_tools_node`.
- The pipeline confirms *after* execution on the tool's own `requires_confirmation`
  output; the draft is executed later, and only in `response_node`
  (`_execute_draft_if_confirmed`).

An MCP client calls the tool function directly. Neither mechanism runs. Measured over
the real catalogue (105 registered instances, 82 with a manifest):

| Class | Count | Exposure risk |
|---|---|---|
| Read-only | 63 | Safe to expose |
| Mutations, draft-based | 14 | Inert when called directly — they persist a draft, and `response_node` never runs, so nothing is sent or deleted. The draft is orphaned, which is a cleanup concern, not a data-loss one |
| Mutations, `hitl_required` | 0 among mutations (`delegate_to_sub_agent_tool` is the only tool carrying the flag) | — |
| **Mutations with neither guard** | **4** | `create_label_tool`, `update_label_tool`, `remove_labels_tool`, `create_reminder_tool` — these mutate **immediately** and would do so with no confirmation whatsoever |

This is the same lesson already recorded for skill sub-agents: a confirmation that lives
outside the tool does not protect a caller that bypasses the graph. **Phase 1 therefore
exposes read-only tools only.** Writes require re-implementing confirmation *inside* the
tool, which is a separate design.

#### Authentication — the options, and the recommendation

Normative constraints, from the MCP specification and Anthropic's connector
documentation:

- Authorization is **OPTIONAL** for MCP; HTTP transports **SHOULD** conform. STDIO
  transports **SHOULD NOT** use OAuth and retrieve credentials from the environment.
- A server that *does* implement OAuth **MUST** serve RFC 9728 metadata, **MUST**
  validate that the token was issued for it as audience (RFC 8707), **MUST** return 401
  on an invalid token, and **MUST NOT** accept or transit tokens issued elsewhere.
- Claude's `static_headers` mode (fixed bearer or API key) is **beta**, and the
  credential is entered by an **organization administrator and shared by the
  organization**, not per user.

| Option | Works with | Verdict |
|---|---|---|
| **A. STDIO bridge**, credential from the environment | Claude Desktop, Claude Code | Spec-aligned and by far the smallest surface: no PRM, no authorization server, no public exposure. But it requires shipping and packaging a local CLI, and it never reaches claude.ai web |
| **B. HTTP resource server + per-user personal access token** | Claude Code, Claude Desktop, Cursor (custom headers); any scripted client | **Recommended for phase 1.** Per-user identity, revocable, minimal new surface |
| **B'. HTTP + Claude `static_headers`** | claude.ai web | **Refused.** The credential is org-shared, so every user of an organization would act as one LIA identity. Incompatible with per-user personal data |
| **C. Full OAuth 2.1 authorization server inside LIA** | Everything, claude.ai web included | The conformant end state, and LIA's own OAuth *client* (`apps/api/src/infrastructure/mcp/oauth_flow.py`) is a ready-made conformance tester. But it means authorization endpoint, consent screen, token endpoint, S256 PKCE, refresh-token rotation, RFC 8414 metadata, RFC 9728 metadata, CIMD (preferred over DCR), RFC 9207 `iss`, RFC 8707 audience binding, revocation, plus a 10-second discovery/token budget and a 30-second refresh budget. A security subsystem, not a lot |

**Recommendation: B now, C only if claude.ai web support is actually wanted.** Phase 1
deliberately does **not** declare `AuthSettings`, so no Protected Resource Metadata is
published and no OAuth discovery is advertised: a client that requires OAuth simply
cannot connect, which is the correct outcome while the only alternative for that surface
is an org-shared credential. Phase 2 (option C) is purely additive — it adds the metadata
documents and a second accepted credential type, without invalidating phase 1 tokens.

#### Personal access token — the design constraints

- **Hash, do not encrypt, and do not use bcrypt.** The token is
  `secrets.token_urlsafe(32)` — about 258 bits of entropy — so a slow KDF buys nothing
  against brute force, while costing a verification on **every MCP request**. Measured on
  x86 development hardware: `bcrypt.checkpw` **163 ms** versus SHA-256 **0.0004 ms**, a
  ratio of roughly 400 000; a Raspberry Pi 5 is materially slower still. bcrypt also caps
  its input at 72 bytes. Store a SHA-256 digest, compare in constant time, and keep a
  non-secret prefix in clear for identification and for log correlation.
- **Per user, never per organization.** The token carries exactly one `user_id`, and
  `AccessToken.subject` propagates it to tool code — proven isolated under concurrency by
  simulation K.
- **Read-only scope in phase 1**, enforced at the tool-exposure layer, not merely
  advertised. The scope is a filter over the catalogue, so a tool added later is excluded
  by default rather than included by default.
- **Explicit expiry, revocation, and last-used tracking**, with the existing per-user
  rate limiter (`create_user_rate_limiter`) applied to the MCP endpoint.
- **No step-up, MFA, or admin surface is reachable with this credential**, ever. It is
  strictly weaker than a session cookie, never equivalent.
- Anthropic's outbound traffic originates from `160.79.104.0/21`, which is available as
  an additional allowlist control at the tunnel.

#### Decision

**MCP server exposure gets its own specification and its own ADR.** Feasibility, the
authentication design, and the HITL constraint are now established rather than assumed,
but folding a new security surface into a context refactor would leave neither
reviewable. Phase 1 is scoped as: read-only tools, per-user personal access token, no
OAuth metadata, root-mounted well-known paths deferred until phase 2, explicit
transport-security host allowlist.

---

## 8. Lots

Each lot is independently shippable and independently revertible.

### Lot 0 — Decision and guard (about 0.5 day)

- **ADR-231**: Agent Server NO-GO with its five blockers; runtime context GO; section 5
  recorded verbatim so the rejected findings are never "fixed".
- **New guard `test_tool_schema_contract.py`**, closing F9: for every registered tool,
  `convert_to_openai_tool` must succeed, and none of `runtime`, `config`, `state`,
  `store`, `tool_call_id` may appear in the exposed properties. Sim H is its reference
  implementation: 53 modules, 109 tools, 0 failures, 0 leaks.
  *This guard has standalone value and is the non-regression oracle for Lot 2.*

### Lot 1 — Isolated corrections (about 1 day, no dependency on Lot 2)

| Item | Action | Risk |
|---|---|---|
| F6 | Delete the two dead legacy branches in `apps/api/src/domains/agents/context/decorators.py` | None — proven unreachable |
| F7a | Use `settings.default_language` and `DEFAULT_TIMEZONE` in `apps/api/src/domains/agents/tools/react_runner.py` | None — aligns with the chokepoint |
| F1 | Correct the misleading comment at `apps/api/src/domains/agents/services/orchestration/service.py:810` to state the truth: the payload is passed but not yet consumed, pending Lot 2 | None |
| — | Bump `langchain-core` to 1.5.6 **and** `langchain-openai` to 1.5.2 together, then `task deps:lock` | **The two are coupled**: `langchain-openai` 1.5.2 requires `langchain-core>=1.5.6`, so it is both or neither. Every transitive constraint verified satisfied (openai 2.54.0, uuid-utils 0.14.1, tiktoken 0.13.0). **Named risk**: `ChatDeepSeekPatched` overrides `BaseChatOpenAI._get_request_payload`, a **private** method owned by `langchain-openai` — the bump must be gated on the DeepSeek round-trip test, not only on `test_langchain_migration_compat` |

**F1 is deliberately not a deletion.** Per the owner's decision, `context=context_dict`
is **kept as the seed of Lot 2**; Lot 1 only removes the contradiction between the
comment and the code, so no docstring describes behaviour the code does not have during
the interim.

### Lot 2 — `LiaRuntimeContext` (about 4 to 6 days)

Strict sequence; each step green before the next.

1. **Freeze the contract.** Frozen dataclass in a new module. `user_id: uuid.UUID`
   canonical; `langgraph_user_id` removed; the four private keys named and typed.
2. **Parameterize the 117 signatures** to `ToolRuntime[LiaRuntimeContext, ...]` with
   the context still `None` — zero behavioural change. Gate: Lot 0's guard and
   `test_tool_registry_smoke` stay green.
3. **Declare `context_schema`**, fill the context at the three injection points, **and
   land the completeness assert in the SAME commit**. Simulation P3 forces this: a thread
   resumed after the switch but without a context succeeds **silently** with
   `runtime.context is None`. Shipping the switch one deploy ahead of the assert would
   open exactly that window on in-flight HITL conversations. One commit, or neither.
4. *(folded into step 3 — see above)*
5. **Migrate reads in waves** across the 43 files, `configurable` staying authoritative
   until the last wave.
6. **F7b**: `react_runner` derives its context from the parent via
   `dataclasses.replace` instead of re-projecting by hand — removing the bug class
   rather than adding eleven keys.

**Edge cases, each tied to its simulation**

| Edge case | Evidence | Treatment |
|---|---|---|
| Context absent on HITL resume | Sim A5 | Step 4 assert |
| Context not checkpointed | Sim A4 | Nothing that must survive a resume may live there — it belongs in `MessagesState` |
| A dict passed instead of the schema | Sim B1/B2 | Always pass an instance; the `TypeError` on a missing required field is the net |
| Concurrent-run leakage | Sim C5 | Validated, no action |
| `gather`, `to_thread`, `create_task` | Sim C1/C2/C3 | Validated, no action |
| In-place `configurable` mutation | Sim D | **Do not touch** — rejected finding |
| Mass Pydantic warnings | Sim F | Enforced ordering, step 2 before step 3 |
| LLM schema regression | Sim G/H | Lot 0's guard |
| Live production checkpoints across the deploy | Sim P2 | Verified safe: a thread interrupted before the switch resumes after it |
| Rollback after the switch | Sim P4 | Verified safe: a thread started on the migrated graph resumes on the previous one |
| Silent `None` on a resume that follows the switch | Sim P3 | Steps 3 and 4 are one atomic commit |
| Live dependencies (`asyncio.Queue`, connector handles) inside the context | Sim N | Identity preserved end to end — no copy, no serialization |
| Existing `graph.config_schema` assertion | Sim O | Unaffected — stays non-`None` |

**Non-regression**: full `task ci:fast`. The **1015 tests** matching `context` or
`configurable` are in scope; a targeted run is not acceptable evidence.

**Reversibility**: each step is a standalone commit. Step 3 is the only behavioural
switch and is undone by passing `context=None` at the three injection points.

### Lot 3 — MCP server exposure (separate specification)

Instructed in section 7: feasibility proven by simulation, authentication designed,
blast radius measured. It proceeds under its own spec and ADR, scoped as:

- **Read-only tools only** in phase 1 — F10 makes write exposure a separate design.
- **Per-user personal access token**, SHA-256 digest at rest (never bcrypt: 163 ms versus
  0.0004 ms per verification, measured), explicit expiry, revocation, last-used tracking,
  and the existing per-user rate limiter.
- **No OAuth metadata published** in phase 1, so no client is invited into a flow LIA
  cannot yet serve. Phase 2 (a full OAuth 2.1 authorization server) is additive.
- **Claude `static_headers` is refused**: the credential is organization-shared, which is
  incompatible with per-user personal data.
- Explicit `TransportSecuritySettings` host allowlist, and well-known paths served at the
  origin root rather than under the mount.

A2A is refused with its reason recorded.

---

## 9. Out of scope

- Any adoption of `langgraph-api`, in production or in development.
- Replacing LIA's SSE vocabulary (`start`, `chunk`, `end`, `error`, `hitl_required`)
  with the `langchain-protocol` wire format: a full chat-transport rewrite of both ends
  for no user-visible gain.
- The `apps/api/src/core/context.py` ContextVars. They are request-scoped, not run-scoped, and
  merging them into `LiaRuntimeContext` would be a second, distinct migration.
