# MCP confirmation strategy — implementation plan

> **For agentic workers:** executed INLINE by the main session (owner directive: no
> subagent), with superpowers:executing-plans and superpowers:test-driven-development. Steps
> use checkbox (`- [ ]`) syntax. Nothing is committed (owner directive): a task ends on its
> ledger line in `.superpowers/sdd/2026-10-30-mcp-confirmation-strategy/progress.md`.

**Goal:** the person decides, sees and predicts when LIA asks before an MCP tool — account,
server, tool — in Pipeline and ReAct, and who drives each server.

**Architecture:** one pure resolution (`infrastructure/mcp/confirmation.py`) feeds the
manifest builder a run uses; the synthesis (`domains/user_mcp/behavior.py`) runs the same
resolution and builder and reads the same predicates; per-tool choices live in their own
table; an approval in advance is ONE manifest fact read by `requires_confirmation` and the
gate.

**Tech stack:** FastAPI, SQLAlchemy 2 / Alembic, Pydantic 2, LangGraph; Next.js 16 / React 19,
vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-30-mcp-confirmation-strategy-design.md`

## Global constraints

- CLAUDE.md (backend and `apps/web/CLAUDE.md`) and the memory directives apply; inline only.
- Six languages for every visible string (`lia-i18n` skill: script FILES, byte-safe, no
  heredoc); no language literal in Python (ADR-323).
- Modules near their size cap receive calls, not logic: `infrastructure/mcp/user_context.py`
  (502/600), `infrastructure/mcp/registration.py` (501/600), `domains/user_mcp/service.py`
  (559/600), `domains/users/models.py` (560/600), `domains/agents/effects/runtime.py` (571/600).
- No new import cycle; no function at CC ≥ 15; MyPy strict; ratchets only go down.
- Migrations chain on head `c7e2a9f4b1d3`, one head, downgrade written, `task db:migrate:replay-check`.
- Integration tests on the host with testcontainers, never inside `lia-api-dev`;
  `TEST_REDIS_URL` on `127.0.0.1`.
- Proofs on Docker dev with the proof account `six-needs.proof@proof-lia.dev` only.
- Routes live under the existing prefix `/mcp/servers`; the settings section token is
  `mcp-servers`.

## Review focus

1. A catalogue that is empty or being revalidated: the synthesis says "unknown", never
   "asks nothing" (Task 2).
2. A tool renamed between two runs: its choice does not follow the new name (Task 4).
3. An MCP App server or `MCP_REACT_ENABLED` off: the page offers only what the selector
   does (Tasks 1, 3).
4. Instance defaults changed by the operator: every "currently" follows (Tasks 1, 3).
5. A loosening reached in two steps: each step's alert lists what IT removes (Tasks 2, 3).

---

### Task 0 — Real proof of the iterative path (D10, H1-H5, H8)

**Files:** harness copied to `.superpowers/sdd/2026-10-30-mcp-confirmation-strategy/proof_iterative.py`
from the session scratchpad's `proof_full_turn.py`; no product file unless a defect.

- [ ] Copy the harness; add mode `iterative` (server row `iterative_mode=True`) with
  scenarios: Pipeline, ReAct with `react_mcp_expand_iterative_enabled` True, ReAct with it
  False — each with `hitl_required` False (a destructive call) and True (one confirmed
  task); plus one turn where a delegated sub-agent meets a tool that must ask (H8).
- [ ] Hard stop at 0.5 USD read from `token_usage_logs`; expected ≈ 0.2 USD.
- [ ] Run, read every `PROOF|` line; ledger H1-H5 and H8 as observed facts.
- [ ] A defect: systematic-debugging, a RED test, the fix, GREEN, ledgered — before Task 1.

### Task 1 — The resolution (D1, D2, D4, D9)

**Files:**
- Create `apps/api/src/infrastructure/mcp/confirmation.py`
- Create `apps/api/src/domains/users/mcp_confirmation_columns.py` (`MCPConfirmationColumns`)
- Create migration `apps/api/alembic/versions/2026_10_30_1800-<rev>_mcp_confirmation_strategy.py`
  (`users.mcp_hitl_required` bool NULL, `user_mcp_servers.react_expand_iterative` bool NULL)
- Modify `domains/users/models.py` (mixin), `domains/users/schemas.py` (`UserUpdate`),
  `domains/agents/application/preference_fields.py`, `core/i18n_application.py` (labels ×6),
  `domains/user_mcp/models.py`, `schemas.py`, `projection.py`, `repository.py`, `router.py`
  (list), `domains/agents/registry/catalogue.py` (`ToolManifest.react_expand`),
  `infrastructure/mcp/registration.py`, `user_context.py`,
  `domains/agents/services/react_tool_selector.py`, env templates (D9 wording).

**Interfaces (produced):**
```python
class ConfirmationSource(StrEnum): SERVER, ACCOUNT, INSTANCE
@dataclass(frozen=True) class ServerConfirmation: always: bool; source: ConfirmationSource
def resolve_server_confirmation(server_value: bool | None, account_value: bool | None) -> ServerConfirmation
def effective_react_expand(server_value: bool | None) -> bool
class ConfirmationReason(StrEnum): SERVER_ALWAYS, ACCOUNT_ALWAYS, INSTANCE_ALWAYS,
    DECLARED_DESTRUCTIVE, DECLARED_MODIFYING, DECLARED_ADDITIVE, DECLARED_READ_ONLY, NOT_DECLARED
def declaration_reason(annotations: object) -> ConfirmationReason
# repository
async def account_confirmation(db, user_id: UUID) -> bool | None
# list response
class UserMCPDefaults(BaseModel): confirmation_instance: bool; confirmation_account: bool | None;
    confirmation_effective: bool; react_direct_tools_default: bool; dedicated_agents_available: bool
```
`ToolManifest.react_expand: bool | None = None` — set on every MCP task manifest (personal and
administrator) from `effective_react_expand`; the selector expands iff `react_expand is True`.

- [ ] RED `tests/unit/infrastructure/mcp/test_confirmation_resolution.py`: precedence
  (server > account > instance, each `None` falls through; `source` names the level);
  `effective_react_expand` (value, else the flag); `declaration_reason` agrees with
  `declared_tool_category` on every annotation combination; one-reader guards — only
  `confirmation.py` (and `startup/integrations.py` for the administrator, `core/config`)
  read `mcp_hitl_required`; only `confirmation.py` reads `react_mcp_expand_iterative_enabled`.
- [ ] RED registration: `_register_prepared` passes the account value; an iterative task
  manifest carries `react_expand`; the administrator's too; the selector expands on
  `react_expand` (True, False, None) and never reads the flag.
- [ ] RED API: `UserUpdate.mcp_hitl_required` strict bool, explicit null resets; the list
  response publishes `UserMCPDefaults`; `react_expand_iterative` in update/response, null
  resets; a peer/library copy writes neither (`service.create_server` offline path).
- [ ] GREEN, then migration + `task db:migrate:replay-check`; `PreferenceField` entry
  (`mcp-servers`), labels ×6; env templates state the defaults; demonstrator files.
- [ ] Gates: targeted suites, `task test:backend:unit:fast`, `task lint:backend`; cold review;
  ledger.

### Task 2 — The synthesis engine (D5)

**Files:** create `apps/api/src/domains/user_mcp/behavior.py`, `behavior_schemas.py`; modify
`router.py` (3 routes, `/strategy/preview` declared before `/{server_id}`); extract the
selector's expansion decision into a pure function both read.

**Interfaces (produced):**
```python
class Driver(StrEnum): DIRECT, DEDICATED_AGENT
class QuestionFlow(StrEnum): IN_LOOP, CARD_AFTER_TASK, BEFORE_TASK, TURN_ENDS_ON_CARD
class ModeBehavior(BaseModel): driver: Driver; before_task: bool; per_call: QuestionFlow | None
class ToolBehavior(BaseModel): tool_name: str; title: str | None; asks_pipeline: bool;
    asks_react: bool; reason: ConfirmationReason; approved_in_advance: bool
class ServerBehavior(BaseModel): confirmation: ServerConfirmation-like; pipeline: ModeBehavior;
    react: ModeBehavior; unattended_refused: list[str]; notes: list[BehaviorNote]; tools: list[ToolBehavior]
class QuestionLoss(BaseModel): server_id: UUID; server_name: str; tool_name: str | None; mode: str
def describe_server_behavior(server: BehaviorInputs, account_value: bool | None, tools: Sequence[Mapping]) -> ServerBehavior
def questions_lost(before: ServerBehavior, after: ServerBehavior) -> list[QuestionLoss]
GET  /mcp/servers/{server_id}/behavior                 -> ServerBehavior
POST /mcp/servers/{server_id}/behavior/preview         -> {behavior, questions_lost}
POST /mcp/servers/strategy/preview                     -> {questions_lost}
```
The flows per (mode, driver) follow the facts Task 0 ledgered (H1-H5); `BehaviorNote` is a
closed vocabulary (`tools_unknown`, `mcp_app`, `dedicated_agents_off`, `choice_suspended`,
`server_overrides_account`).

- [ ] RED matrix test `tests/unit/domains/user_mcp/test_behavior_matrix.py`: for every
  (server, account, instance) × shape × declaration × `MCP_REACT_ENABLED` × MCP App, the
  synthesis's per-tool asks equal `requires_confirmation` of the manifest the registration
  builder makes, and its driver equals the selector's decision function.
- [ ] RED `questions_lost`: a loosening at each level is listed; a tightening lists nothing;
  two steps each list their own loss (review focus 5); unknown catalogue → `tools_unknown`,
  never an empty "asks nothing".
- [ ] RED routes: ownership (another account's server → 404), preview writes nothing,
  candidates tri-state (absent = unchanged, null = inherit), strategy preview spans all the
  person's servers.
- [ ] GREEN; gates; cold review; ledger.

### Task 3 — The page (§ 1-4, 6)

**Files:** create `apps/web/src/components/settings/MCPConfirmationStrategy.tsx`,
`MCPServerBehaviorFields.tsx` (confirmation + driver selects), `MCPServerBehaviorPanel.tsx`,
`MCPConfirmationLooseningDialog.tsx`, hook `src/hooks/useMCPServerBehavior.ts`; modify
`useUserMCPServers.ts` (types, `defaults`), `lib/mcp-server-form.ts` (form state: confirmation
tri-state, driver), `MCPServerFormFields.tsx` (switch replaced), `MCPServerCard.tsx` (a
"what it will do" action; opened panel for a disabled received copy),
`MCPServersSettings.tsx` (strategy section; tested saved server shows the panel instead of
the bare list); locales ×6 (`settings.mcp.confirmation.*`, `settings.mcp.driver.*`,
`settings.mcp.behavior.*`); e2e journey `e2e/smoke/mcp-confirmation-strategy.spec.ts`.

- [ ] RED vitest: the strategy section states the instance default it follows; each server
  select offers only what `defaults` allow; a change with `questions_lost` opens the alert
  and applies only on confirm; cancel restores; the panel renders reasons from the API; a
  server-chosen name renders as text; the form sends the driver's shape only when changed.
- [ ] GREEN; locales by script (byte-safe); a11y (labels, keyboard, focus); mobile-first.
- [ ] Gates: `task test:frontend`, `task lint:frontend`, `task lint:i18n`, e2e journey (build
  alone); cold review; ledger.

### Task 4 — Per-tool choices (D6, H7)

**Files:** create model `domains/user_mcp/tool_choices.py` (`UserMCPToolChoice`: server_id FK
CASCADE, tool_name, choice `always|never`, declaration_fingerprint, timestamps; unique
(server_id, tool_name)) registered in `import_all_models`; migration; repository functions;
route `PUT /mcp/servers/{server_id}/tool-confirmations` (body `{tool_name, choice|null}`,
refuses a tool absent from the catalogue); extend `confirmation.py`
(`ToolChoice`, `declaration_fingerprint(tool) -> str` over normalised annotations + input
schema, `resolve_tool_confirmation(...) -> ToolConfirmation(hitl_required, approved_in_advance, reason, suspended)`,
reasons `TOOL_ALWAYS`, `TOOL_NEVER`); `ToolManifest.approved_in_advance: bool = False`;
`confirmation_rule.requires_confirmation` (guard clause); `effects/preapproval.py` (approval
in advance → approved scope, kind `standing_choice`, ref server id) ahead of the routine's;
`user_context.py` passes choices; synthesis shows choices; UI per-tool select + alert.

- [ ] RED: *always* → hitl + `confirm`; *never* on a declared-destructive tool → no hitl,
  `confirm`, `approved_in_advance`; *never* on read/undeclared → unchanged; a changed
  annotation or input schema suspends (`suspended=True`, levels below apply); description
  change does not; a renamed tool's choice applies to nothing; loop does not ask; gate
  approves with `standing_choice`; unattended run executes and records; guard: every reader
  deciding to ask from a manifest goes through `requires_confirmation`.
- [ ] RED integration (PostgreSQL): two writes on two tools both persist; cascade on server
  delete; a copy carries no row.
- [ ] GREEN; gates; cold review; ledger.

### Task 4b — A dedicated agent is asked before its task (owner decision 2026-10-31)

**Files:** `domains/agents/registry/confirmation_rule.py` (`task_requires_confirmation`),
`infrastructure/mcp/user_context.py` and `admin_registration.py` (the task manifest asks
when one of its individuals would ask), `domains/user_mcp/behavior.py` (before the task =
the same predicate; a question before the task counts as asked; per call: none for a
dedicated agent; `TURN_ENDS_ON_CARD` retired), the web panel and its vocabulary, the six
locales, the matrix test.

- [ ] RED: a declarations server with a destructive tool registers a task that asks; a
  server whose tools ask nothing registers a task that does not; a « never » tool does not
  make the task ask, an « always » tool does; admin servers alike; the synthesis says
  « before the task, covers its calls » in both modes and both strategies; direct→dedicated
  under « always » loses nothing; the matrix holds `before_task == requires_confirmation(task)`.
- [ ] GREEN; gates; cold review; ledger. The real proof (Pipeline and ReAct, declarations,
  dedicated agent: one question, the task completes) runs at Task 7 after a budget is
  approved.

### Task 4c — Per-tool choices in the form; « never » in the warning colour

**Files:** `MCPServerFormDialog` (the live panel's per-tool selectors feed the form's
candidates; the save writes the choices after the server, one alert for both),
`MCPServerBehaviorPanel` (the warning colour on a « never » row), tests, e2e journey.

- [ ] RED: a choice made in the form is previewed with the form's other candidates, alerts
  once, and is written only on save; cancelling writes nothing; a « never » row carries the
  warning token and its words.
- [ ] GREEN; gates; cold review; ledger.

### Task 5 — The assistant (D7)

**Files:** `domains/user_mcp/personal_configuration.py` (tighten-only set replaces
API-only; shape judged by `questions_lost`), the personal-MCP configuration input/rendering
(`always_ask_tools`), the preferences operation (only `true` for `mcp_hitl_required`),
`infrastructure/mcp/personal_metadata_contract.py` + `management_projection.py` (read
surface), refusal sentences ×6, the contract guard test.

- [ ] RED: `hitl_required` false/null refused, true accepted; `mcp_hitl_required` false/null
  refused through `preferences.update`; a shape change that loses questions refused, one
  that loses none accepted; checked at the write against the replaced state; per-tool
  *always* accepted, *never* refused; read surface carries the new values.
- [ ] GREEN; gates; cold review; ledger.

### Task 6 — Documentation

New ADR (next free number at writing), ADR-263 amendment, `ADR_INDEX`, `MCP_INTEGRATION.md`,
`GUIDE_MCP_INTEGRATION.md`, FAQ ×6 (`mcp_servers` q6, q11 + two new; `skills` q15;
`scheduled_actions` q14), living maps ×6 + `task docs:maps`, env templates + demonstrator
files, one CLAUDE.md line, `task docs:sync-agents`, `task release:sync-counts` if counts move.

- [ ] `task lint:docs` (preview when unstaged), `task lint:i18n`; cold review; ledger.

### Task 7 — Closing

- [ ] `task lint`, `task test:backend:unit:fast`, integration suites touched, `task test:frontend`,
  `task test:frontend:coverage`, e2e (alone), `task ci:fast`.
- [ ] Closing proof on Docker dev (proof account): the page, a loosening alert, a *never*
  tool run unasked and recorded, a suspended choice; spend ledgered.
- [ ] Exhaustive cold review of every touched file; final self-evaluation; memory updated.
