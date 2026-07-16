# ADR-094: Remove Dead Per-Node Message-Windowing Helpers

**Status**: ✅ IMPLEMENTED (2026-07-03)
**Author**: Claude Code (Fable 5)
**Related**: [ADR-007](ADR-007-Service-Layer-Pattern-For-Node-Complexity.md), [MESSAGE_WINDOWING_STRATEGY.md](../technical/MESSAGE_WINDOWING_STRATEGY.md), [ADR-022](ADR-022-LangGraph-State-Checkpointing.md) (state-level truncation)

## Context

The 2026-07 codebase audit (wave 2) found a fully self-contained **dead
micro-subsystem** in `domains/agents/utils/message_windowing.py`:

- `get_router_windowed_messages()`, `get_planner_windowed_messages()` and
  `get_orchestrator_windowed_messages()` had **no call site** anywhere in
  `src/` (verified by exhaustive grep). The router node reads
  `state[STATE_KEY_MESSAGES]` directly; the planner and task orchestrator
  likewise never called their helper.
- The three settings that fed them —
  `router_message_window_size`, `planner_message_window_size`,
  `orchestrator_message_window_size` — were consumed **only** by those dead
  helpers (transitively dead), along with their constants
  (`*_MESSAGE_WINDOW_SIZE_DEFAULT`) and `.env.example` / `.env.prod.example`
  entries.
- Their only remaining consumers were **tests** — coverage that proved the
  helpers "worked" while nothing in production used them (fake coverage).

This is exactly the failure mode CLAUDE.md's dead-code rule targets: *"an
unwired subsystem with settings/i18n/tests attached costs maintenance on
every change and fakes coverage. Wire it or remove it — record the decision
in a short ADR."*

Token growth on the router/planner/orchestrator LLM calls is **already
bounded** by the state-level `add_messages_with_truncate` reducer
(token-based truncation + windowing at checkpoint time), so the per-node
helpers were an *additional* optimization layer that was designed but never
connected.

## Decision

**Remove** the three dead helpers, their three settings, their constants and
their `.env` entries, plus the tests that only exercised them.

**Keep** what is alive:

- `get_windowed_messages()` — the core function, called by `react_nodes.py`
  with `settings.react_agent_history_window_turns`.
- `get_response_windowed_messages()` — called by `response_node.py`.
- `response_message_window_size` / `RESPONSE_MESSAGE_WINDOW_SIZE_DEFAULT` and
  `default_message_window_size` / `DEFAULT_MESSAGE_WINDOW_SIZE` (the live
  response window and the public function's `None`-fallback default).

Removing the settings is safe: the `Settings` model uses `extra="ignore"`, so
any lingering `ROUTER_MESSAGE_WINDOW_SIZE` etc. in an operator's `.env` is a
harmless no-op (it already was — the value was never read).

## Consequences

- **No behavioral change.** These helpers were never wired; the graph's
  message flow is identical.
- Deliberate per-node history windowing for router/planner/orchestrator (a
  real latency lever) is **deferred to the latency-optimization effort**, to
  be reintroduced *with benchmarks proving no routing/planning quality
  regression* rather than as unused scaffolding.
- The windowing test suite now covers only live surface
  (`get_windowed_messages`, `get_response_windowed_messages`,
  `extract_last_user_message`).

## Alternative considered — wire the helpers

Connecting router/planner/orchestrator to their helpers would trim tokens on
those calls, but it changes the context the routing/planning LLMs see and
must be validated against decision quality (a wrong route or a truncated plan
is worse than a few extra tokens). That is a deliberate performance change
owned by the latency effort, not a cleanup — hence *remove now, reintroduce
intentionally later*.
