# ReAct Initiative Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the Initiative phase (proactive cross-domain read-only enrichment, ADR-062) to the ReAct execution mode (ADR-070) by routing the ReAct nominal path through the existing `initiative_node`, gated by a dedicated flag, with the ReAct answer preserved and proactive findings woven into the prose.

**Architecture:** Reuse `initiative_node` unchanged (validated: it already tolerates ReAct-shaped state — `query_intelligence.domains`, `current_turn_registry`, and per-request tool manifests are all populated in ReAct). Insert it on the ReAct **nominal** path via a new conditional edge `route_from_react_finalize` (the ReAct **draft** path stays untouched → zero regression). Fix the `response_node` guard that would otherwise drop the ReAct answer when Initiative also writes `agent_results`. Add a light prose-weaving directive so the proactive findings (already passed to the response LLM via `data_for_filtering`) are narrated.

**Tech Stack:** Python 3.12, LangGraph 1.x (conditional edges), Pydantic v2 settings, pytest (`@pytest.mark.unit`, `asyncio_mode=auto`), structlog, Prometheus.

---

## Context & validated facts

- ReAct nominal path ends `finalize → response` ([graph.py:773](../../../apps/api/src/domains/agents/graph.py#L773)).
- ReAct **draft** path `execute_tools → draft_critique → initiative → response` **already routes through `initiative_node` today** ([graph.py:702](../../../apps/api/src/domains/agents/graph.py#L702)). Left strictly unchanged.
- `initiative_node` reads executed domains from `query_intelligence.domains` ([initiative_node.py:167](../../../apps/api/src/domains/agents/nodes/initiative_node.py#L167)) — populated in ReAct by the router ([router_node_v3.py:298](../../../apps/api/src/domains/agents/nodes/router_node_v3.py#L298)).
- Pre-filter manifests: ContextVar set at the common request entry ([service.py:740](../../../apps/api/src/domains/agents/api/service.py#L740)), already consumed by ReAct ([react_tool_selector.py:68](../../../apps/api/src/domains/agents/services/react_tool_selector.py#L68)).
- `current_turn_registry` populated by ReAct `execute_tools` ([react_nodes.py:588-590](../../../apps/api/src/domains/agents/nodes/react_nodes.py#L588)).
- **CRITICAL regression:** `response_node` injects the ReAct answer only `if not state.get(STATE_KEY_AGENT_RESULTS)` ([response_node.py:1229](../../../apps/api/src/domains/agents/nodes/response_node.py#L1229)); `agent_results` has **no reducer** ([models.py:170](../../../apps/api/src/domains/agents/models.py#L170)). If Initiative acts it writes `{turn}:initiative` first → the guard fails → the ReAct answer is dropped. Must merge, not gate.
- Findings reach the response LLM as text via `data_for_filtering` (from `current_turn_registry`, [response_node.py:1416](../../../apps/api/src/domains/agents/nodes/response_node.py#L1416)). Suggestion injected mode-agnostically ([response_node.py:2217](../../../apps/api/src/domains/agents/nodes/response_node.py#L2217)).
- **Recursion-limit (VERIFIED):** ReAct uses `react_agent_max_iterations * 2 + 15` ([service.py:1301-1302](../../../apps/api/src/domains/agents/services/orchestration/service.py#L1301)). The `+15` covers setup + finalize + response + the extra `initiative` super-step. No change needed.

## Design decisions (locked)

- **Prose:** findings woven + suggestion (directive injection; data already flows via `data_for_filtering`).
- **Flag:** dedicated `INITIATIVE_REACT_ENABLED`, default **`False`** (ship dark). Nominal-path gate lives in `route_from_react_finalize`; the draft path is NOT gated → default-off changes nothing vs today.
- **Skill:** Initiative runs even if a skill-tool was used in ReAct (no extra skip).

> Per CLAUDE.md the user controls git. The `Commit` steps are for whoever executes; do not run them without the user's explicit go-ahead.

---

### Task 1: Configuration flag `INITIATIVE_REACT_ENABLED`

**Files:** `apps/api/src/core/constants.py:2268`, `apps/api/src/core/config/agents.py:121-123,3002`, `apps/api/.env.example`, `apps/api/.env.prod.example`

- [ ] **Step 1 — Add the default constant** (constants.py, after line 2268):

```python
# ReAct-mode Initiative (ADR-070): gate the nominal ReAct path through the
# Initiative node independently of the pipeline. Default off → ship dark; the
# ReAct draft path (already wired to initiative) is unaffected by this flag.
INITIATIVE_REACT_ENABLED_DEFAULT = False
```

- [ ] **Step 2 — Import in settings** (config/agents.py, lines 121-123, alphabetical):

```python
    INITIATIVE_ENABLED_DEFAULT,
    INITIATIVE_MAX_ACTIONS_PER_ITERATION_DEFAULT,
    INITIATIVE_MAX_ITERATIONS_DEFAULT,
    INITIATIVE_REACT_ENABLED_DEFAULT,
```

- [ ] **Step 3 — Add field** (config/agents.py, after `initiative_max_actions`, line 3002):

```python
    initiative_react_enabled: bool = Field(
        default=INITIATIVE_REACT_ENABLED_DEFAULT,
        description=(
            "Enable the Initiative phase on the ReAct nominal path "
            "(react_finalize → initiative → response). Independent of the pipeline "
            "Initiative; the ReAct draft path is never gated by this flag."
        ),
    )
```

- [ ] **Step 4 — Document env var** (.env.example + .env.prod.example):

```dotenv
# Enable Initiative enrichment on the ReAct nominal path (ADR-070). Default off.
INITIATIVE_REACT_ENABLED=false
```

- [ ] **Step 5 — Verify:** `cd apps/api && .venv/Scripts/python -c "from src.core.config import settings; print(settings.initiative_react_enabled)"` → `False`

---

### Task 2: Nominal-path gate — `route_from_react_finalize` + wiring

**Files:** `routing.py` (new fn after `route_from_react_execute_tools`), `graph.py:742-745,773`, `tests/unit/domains/agents/nodes/test_routing_react_initiative.py`

- [ ] **Step 1 — Failing tests** (`test_routing_react_initiative.py`):

```python
"""Unit tests for ReAct → Initiative routing (ADR-070)."""

from __future__ import annotations

import pytest

from src.core.config import settings
from src.domains.agents.nodes.routing import (
    route_from_initiative,
    route_from_react_finalize,
)


@pytest.mark.unit
class TestRouteFromReactFinalize:
    def test_routes_to_initiative_when_both_flags_on(self, monkeypatch):
        monkeypatch.setattr(settings, "initiative_enabled", True)
        monkeypatch.setattr(settings, "initiative_react_enabled", True)
        assert route_from_react_finalize({}) == "initiative"

    def test_routes_to_response_when_react_flag_off(self, monkeypatch):
        monkeypatch.setattr(settings, "initiative_enabled", True)
        monkeypatch.setattr(settings, "initiative_react_enabled", False)
        assert route_from_react_finalize({}) == "response"

    def test_routes_to_response_when_initiative_globally_off(self, monkeypatch):
        monkeypatch.setattr(settings, "initiative_enabled", False)
        monkeypatch.setattr(settings, "initiative_react_enabled", True)
        assert route_from_react_finalize({}) == "response"


@pytest.mark.unit
class TestRouteFromInitiativeReactAware:
    def test_react_always_proceeds_to_response_even_after_actions(self, monkeypatch):
        monkeypatch.setattr(settings, "initiative_enabled", True)
        monkeypatch.setattr(settings, "initiative_max_iterations", 1)
        state = {
            "execution_mode": "react",
            "initiative_iteration": 1,
            "initiative_results": [{"actions_executed": 2}],
        }
        assert route_from_initiative(state) == "response"
```

- [ ] **Step 2 — Run, expect FAIL** (`ImportError: route_from_react_finalize`):
`cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents/nodes/test_routing_react_initiative.py -v`

- [ ] **Step 3 — Implement `route_from_react_finalize`** (routing.py, after `route_from_react_execute_tools`):

```python
def route_from_react_finalize(
    state: MessagesState,
) -> Literal["initiative", "response"]:
    """Route after ReAct finalize: optional Initiative enrichment, then response.

    The nominal ReAct path (the LLM stopped calling tools) lands here. When both the
    global Initiative phase and its ReAct-specific flag are enabled, route through
    NODE_INITIATIVE so the autonomous answer is enriched with proactive cross-domain
    read-only findings (ADR-062 parity for ReAct). Otherwise proceed straight to
    response — preserving the pre-feature behaviour exactly.

    The ReAct *draft* path (execute_tools -> draft_critique -> initiative) is wired
    independently and is intentionally NOT gated here, so this edge introduces zero
    change to draft turns.

    Args:
        state: Current graph state.

    Returns:
        ``"initiative"`` when ReAct-Initiative is enabled, else ``"response"``.
    """
    from src.core.config import settings
    from src.core.constants import NODE_INITIATIVE

    if settings.initiative_enabled and settings.initiative_react_enabled:
        langgraph_conditional_edges_total.labels(
            edge_name="route_from_react_finalize", decision=NODE_INITIATIVE,
        ).inc()
        return NODE_INITIATIVE

    langgraph_conditional_edges_total.labels(
        edge_name="route_from_react_finalize", decision=NODE_RESPONSE,
    ).inc()
    return NODE_RESPONSE
```

- [ ] **Step 4 — React-awareness in `route_from_initiative`** (after `if not settings.initiative_enabled: return NODE_RESPONSE`, lines 653-654):

```python
    # ReAct mode (ADR-070): single post-finalize enrichment pass — there is no
    # orchestrator loop to re-evaluate against, so always proceed to response
    # (never loop back to initiative, regardless of actions_executed).
    if state.get("execution_mode") == "react":
        langgraph_conditional_edges_total.labels(
            edge_name="route_from_initiative", decision=NODE_RESPONSE,
        ).inc()
        return NODE_RESPONSE
```

- [ ] **Step 5 — Run, expect PASS** (5 tests).

- [ ] **Step 6 — Wire conditional edge** (graph.py import 742-745 add `route_from_react_finalize`; replace line 773):

```python
    # ADR-070 + ADR-062: nominal ReAct path may pass through Initiative for proactive
    # read-only enrichment (gated by INITIATIVE_REACT_ENABLED). The draft path keeps
    # its own independent edge into NODE_INITIATIVE, so this does not affect drafts.
    graph.add_conditional_edges(
        NODE_REACT_FINALIZE,
        route_from_react_finalize,
        {NODE_INITIATIVE: NODE_INITIATIVE, NODE_RESPONSE: NODE_RESPONSE},
    )
```

- [ ] **Step 7 — Verify graph compiles:** `cd apps/api && .venv/Scripts/python -c "from src.domains.agents.graph import build_graph; print('graph builds')"`

---

### Task 3: Fix the ReAct-answer-drop regression (merge, not gate) — CRITICAL

**Files:** `response_node.py` (helper + lines 1228-1235), `tests/unit/domains/agents/nodes/test_response_node_react_merge.py`

- [ ] **Step 1 — Failing test** (`test_response_node_react_merge.py`):

```python
"""Regression test: the ReAct answer must survive when Initiative also wrote
agent_results (ADR-070)."""

from __future__ import annotations

import pytest

from src.domains.agents.nodes.response_node import _merge_react_synthesis_result


@pytest.mark.unit
class TestMergeReactSynthesisResult:
    def test_injects_react_entry_into_empty_results(self):
        merged = _merge_react_synthesis_result(None, "the answer", 4, {"item_1": object()})
        assert merged["4:react_agent"]["data"]["react_synthesis"] == "the answer"

    def test_preserves_initiative_entry_and_adds_react(self):
        existing = {"4:initiative": {"status": "success", "data": {"x": 1}}}
        merged = _merge_react_synthesis_result(existing, "the answer", 4, {})
        assert "4:initiative" in merged and "4:react_agent" in merged

    def test_idempotent_on_react_key(self):
        existing = {"4:react_agent": {"data": {"react_synthesis": "first"}}}
        merged = _merge_react_synthesis_result(existing, "second", 4, {})
        assert merged["4:react_agent"]["data"]["react_synthesis"] == "first"

    def test_does_not_mutate_input(self):
        existing = {"4:initiative": {"status": "success"}}
        _merge_react_synthesis_result(existing, "answer", 4, {})
        assert "4:react_agent" not in existing
```

- [ ] **Step 2 — Run, expect FAIL** (`ImportError`).

- [ ] **Step 3 — Add helper** (response_node.py, module-level near other helpers):

```python
def _merge_react_synthesis_result(
    agent_results: dict[str, Any] | None,
    react_message: str,
    current_turn: int,
    current_registry: dict[str, Any],
) -> dict[str, Any]:
    """Merge the ReAct final answer into agent_results without overwriting entries.

    The ReAct answer is keyed ``{turn}:react_agent``. When the Initiative node ran on
    the ReAct nominal path (react_finalize -> initiative -> response), it has already
    written ``{turn}:initiative`` into agent_results; a plain ``if not agent_results``
    guard would then skip the ReAct answer entirely, dropping the user-facing reply.
    This merge is idempotent on the react key, so graph re-entry never duplicates it.

    Args:
        agent_results: Existing agent_results map (possibly populated by Initiative).
        react_message: The ReAct loop's final answer text.
        current_turn: Current turn id (for the composite key).
        current_registry: Registry items for this turn (drives HTML cards / display).

    Returns:
        A new dict containing every existing entry plus the ``{turn}:react_agent`` one.
    """
    merged = dict(agent_results or {})
    react_key = f"{current_turn}:react_agent"
    if react_key not in merged:
        merged[react_key] = {
            "data": {"react_synthesis": react_message},
            "registry_updates": current_registry,
        }
    return merged
```

- [ ] **Step 4 — Replace guard with merge** (lines 1228-1235):

```python
            current_registry = state.get("current_turn_registry") or state.get("registry") or {}
            # Merge (not gate): the Initiative node may have written {turn}:initiative
            # before us on the ReAct nominal path. A plain "if not agent_results" guard
            # would drop the ReAct answer; merging preserves both (ADR-070).
            state[STATE_KEY_AGENT_RESULTS] = _merge_react_synthesis_result(
                state.get(STATE_KEY_AGENT_RESULTS), react_message, current_turn, current_registry,
            )
```

- [ ] **Step 5 — Run, expect PASS** (4 tests).

- [ ] **Step 6 — No-regression:** `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents/formatters/test_agent_results_react_synthesis.py -v` → 4 PASS.

---

### Task 4: Prose weaving of proactive findings (ReAct only)

**Files:** `response_node.py` (after the `<InitiativeSuggestion>` block, line 2227)

- [ ] **Step 1 — Add directive**:

```python
        # ADR-070: in ReAct mode the agent's answer is delivered as authoritative
        # (the response LLM is told not to re-derive). When the Initiative node
        # gathered proactive read-only findings AFTER that answer was written, they
        # would otherwise surface only as orphan cards. The findings are already in
        # the prompt via `data_for_filtering`; this directive invites weaving them in.
        # Gated to ReAct + Initiative-acted to keep zero impact elsewhere.
        from src.core.constants import STATE_KEY_INITIATIVE_RESULTS

        _initiative_results = state.get(STATE_KEY_INITIATIVE_RESULTS) or []
        _initiative_acted = any(r.get("actions_executed", 0) > 0 for r in _initiative_results)
        if (
            state.get("execution_mode") == "react"
            and _initiative_acted
            and react_result
            and react_result.get("final_message")
        ):
            base_system_prompt += (
                "\n\n<ProactiveFindings>\n"
                "Beyond the direct answer, additional proactive read-only findings were "
                "gathered this turn (present in the current turn data). Weave the relevant "
                "ones naturally into your reply as a helpful complement — do not list them "
                "mechanically and never expose how they were obtained.\n"
                "</ProactiveFindings>"
            )
```

*(`react_result` is in scope from the passthrough block at line 1220; if not, re-read `react_result = state.get("react_agent_result")` before the condition.)*

- [ ] **Step 2 — Verify import:** `cd apps/api && .venv/Scripts/python -c "import src.domains.agents.nodes.response_node; print('ok')"`

---

### Task 5: Observability — `execution_mode` on Initiative logs

**Files:** `initiative_node.py`

- [ ] Capture `execution_mode = state.get("execution_mode", "pipeline")` after `run_id` (line 490); add `execution_mode=execution_mode` to `logger.info("initiative_prefilter", ...)` (543) and `logger.info("initiative_decision", ...)` (610).

---

### Task 6: Integration test — ReAct + Initiative

**Files:** `tests/integration/domains/agents/test_react_initiative_flow.py`

```python
"""Integration: ReAct nominal path through Initiative (ADR-070)."""

from __future__ import annotations

import pytest

from src.core.config import settings
from src.domains.agents.formatters.agent_results import format_agent_results_for_prompt
from src.domains.agents.nodes.response_node import _merge_react_synthesis_result
from src.domains.agents.nodes.routing import route_from_react_finalize


@pytest.mark.integration
class TestReactInitiativeFlow:
    def test_flag_on_routes_into_initiative(self, monkeypatch):
        monkeypatch.setattr(settings, "initiative_enabled", True)
        monkeypatch.setattr(settings, "initiative_react_enabled", True)
        assert route_from_react_finalize({"execution_mode": "react"}) == "initiative"

    def test_flag_off_skips_initiative(self, monkeypatch):
        monkeypatch.setattr(settings, "initiative_enabled", True)
        monkeypatch.setattr(settings, "initiative_react_enabled", False)
        assert route_from_react_finalize({"execution_mode": "react"}) == "response"

    def test_answer_and_findings_coexist(self):
        after_initiative = {"4:initiative": {"status": "success", "data": {"weather": "18C"}}}
        merged = _merge_react_synthesis_result(after_initiative, "Your meeting is at 3pm.", 4, {})
        summary = format_agent_results_for_prompt(merged, current_turn_id=4)
        assert "Your meeting is at 3pm." in summary
```

---

### Task 7: Runtime verification (no regression)

- [ ] **Step 1 — Fast unit suite:** `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents/nodes/ tests/unit/domains/agents/formatters/ -q`
- [ ] **Step 2 — Recursion-limit:** VERIFIED — `react_agent_max_iterations*2 + 15` ([service.py:1301](../../../apps/api/src/domains/agents/services/orchestration/service.py#L1301)); `+15` covers the extra `initiative` node. No change.
- [ ] **Step 3 — Docker (CLAUDE.md):** `task dev:detach`; ReAct query with `INITIATIVE_REACT_ENABLED=true`; confirm logs `initiative_prefilter ... execution_mode=react` then `response_node_react_passthrough`; answer present AND findings/cards visible; `task stop`.
- [ ] **Step 4 — Lint:** `task lint:backend`.

---

### Task 8: Documentation

- [ ] Amend ADR-070 (new `route_from_react_finalize` edge, `INITIATIVE_REACT_ENABLED` flag default off, merge fix, prose directive, explicit non-change to draft path); amend ADR-062 (two ReAct entry points); update `docs/architecture/ADR_INDEX.md`, `docs/INDEX.md`, and the ReAct Mermaid flow in `docs/architecture_langraph.md` (`react_finalize → {initiative | response}`).

---

## Zero-regression guarantees

- **Flag off (default)** → `route_from_react_finalize` returns `response` → byte-identical to today's `finalize → response`.
- **Draft path untouched** (independent edge, not gated).
- **Merge fix ReAct-only** (guarded by `react_agent_result.final_message`); pipeline `agent_results` never carries a `react_agent` key.
- **Prose directive** gated to `execution_mode=="react"` + Initiative-acted.
- **Recursion-limit** headroom (`+15`) verified sufficient.
