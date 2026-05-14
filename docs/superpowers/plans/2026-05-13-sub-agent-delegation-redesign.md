# Sub-Agent Delegation Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewire `delegate_to_sub_agent_tool` (planner's ephemeral sub-agent delegation) onto the existing `ReactSubAgentRunner`, add a structural veto against pointless delegations, and put a hard size cap on the sub-agent's `instruction` after `$ref` resolution — so a query like « résume mes 5 derniers emails » stops consuming ~486 K tokens (~0,56 €) and is handled by the main pipeline in ~12 K tokens.

**Architecture:** A sub-agent stops being a mini-pipeline that re-plans (`SubAgentExecutor` with `_analyze_instruction` + `SmartPlannerService.plan` + `_synthesize_results`) and becomes a parameterized ReAct loop (`ReactSubAgentRunner("subagent", "subagent_react_prompt")` + read-only tools + tight `recursion_limit`). The planner is steered (prompt + structural veto in `semantic_validator`) to only delegate when an expert persona materially helps. A post-resolution token cap on `instruction` of `delegate_to_sub_agent_tool` blocks the « shovel raw data » pattern. HITL passthrough unchanged. Persistent sub-agents (REST `/sub-agents`, templates) untouched (dead UI plumbing — Phase 2 will likely just delete it).

**Tech Stack:** FastAPI, LangGraph 1.0, LangChain 1.0, Pydantic v2, SQLAlchemy v2, pytest (`asyncio_mode = "auto"`), structlog, ruff/black/mypy strict.

**Spec:** [`2026-05-13-sub-agent-delegation-redesign-design.md`](../specs/2026-05-13-sub-agent-delegation-redesign-design.md). Hypotheses **H1/H2/H3** referenced in the spec drive every task here.

**Preconditions verified before writing this plan:**
- `ReactSubAgentRunner` (`apps/api/src/domains/agents/tools/react_runner.py`) is generic, used by `browser_task_tool` and `mcp_server_task_tool`. ✓
- `TokenTrackingCallback` reads `metadata["node_name_override"]` (cf. `apps/api/src/infrastructure/observability/callbacks.py:450`) → sub-agent token attribution will land under the chosen `display_name`. ✓
- `EstimationTokenCounter` (`apps/api/src/infrastructure/llm/providers/token_counter.py:198`) provides a provider-agnostic `count(text, model)` (≈ `len(text) // 4`) — used for the instruction cap (we don't yet know the sub-agent model when validating). ✓
- F6 replan path is alive: `STATE_KEY_NEEDS_REPLAN`, `STATE_KEY_EXCLUDE_SUB_AGENT_TOOLS`, `route_from_semantic_validator` → `planner` when `needs_replan=True`, `planner_node_v3` clears `needs_replan` after, `_build_sub_agents_section` honors `exclude_sub_agents_from_prompt` ContextVar. ✓
- Approval gate is a passthrough (HITL out of scope). ✓
- Persistent sub-agent UI is an orphan (`SubAgentsSettings.tsx` not rendered anywhere; no frontend hits `/sub-agents`). ✓

---

## Task 1: Foundation — settings, constants, and `.env`

**Files:**
- Modify: `apps/api/src/core/constants.py` — append the new default constant.
- Modify: `apps/api/src/core/config/agents.py` — append the two new Settings fields.
- Modify: `.env.example` — add the two env vars (documented).
- Modify: `.env.prod.example` — add the two env vars.
- Test: `apps/api/tests/unit/core/config/test_agents_settings.py` (create if missing — otherwise extend the existing `test_settings_*.py` for agents).

- [ ] **Step 1: Locate existing subagent constants and confirm insertion point**

Run: `Grep tool — pattern "SUBAGENT_MAX_TOKEN_BUDGET_DEFAULT" in apps/api/src/core/constants.py`
Expected: one match around line 3297 (`SUBAGENT_MAX_TOKEN_BUDGET_DEFAULT = 50000`).

- [ ] **Step 2: Add the two new default constants in `core/constants.py`**

Insert immediately after `SUBAGENT_MAX_TOTAL_TOKENS_PER_DAY_DEFAULT = 500000` (around line 3298):

```python
# Hard cap (tokens) on `delegate_to_sub_agent_tool.instruction` AFTER $ref resolution.
# Blocks the "shovel raw data via $steps.X.<payload> into instruction" anti-pattern.
SUBAGENT_INSTRUCTION_MAX_TOKENS_RESOLVED_DEFAULT = 3000

# Feature flag: semantic_validator veto on pointless sub-agent delegations
# (single delegate step, single domain, no fan-out → presumed not to satisfy H1).
SUBAGENT_VETO_POINTLESS_ENABLED_DEFAULT = True
```

- [ ] **Step 3: Add the two new Settings fields in `config/agents.py`**

After the existing `subagent_max_total_tokens_per_day` field (around line 2820), insert:

```python
    subagent_instruction_max_tokens_resolved: int = Field(
        default=SUBAGENT_INSTRUCTION_MAX_TOKENS_RESOLVED_DEFAULT,
        ge=500,
        le=20000,
        description=(
            "Hard cap (tokens) on the resolved `instruction` of "
            "`delegate_to_sub_agent_tool` after $ref expansion. "
            "Above this, the step fails with INVALID_INPUT — prevents "
            "the planner from shoveling raw data payloads into a sub-agent."
        ),
    )
    subagent_veto_pointless_enabled: bool = Field(
        default=SUBAGENT_VETO_POINTLESS_ENABLED_DEFAULT,
        description=(
            "When True, the semantic_validator vetoes plans that delegate "
            "to a sub-agent without H1 justification (mono-domain, single "
            "delegate step, no fan-out) and triggers a re-plan without "
            "delegation. Kill-switch for the heuristic."
        ),
    )
```

Also extend the imports at the top of `config/agents.py` to include the two new defaults:

```python
from src.core.constants import (
    ...,
    SUBAGENT_INSTRUCTION_MAX_TOKENS_RESOLVED_DEFAULT,
    SUBAGENT_VETO_POINTLESS_ENABLED_DEFAULT,
    ...,
)
```

- [ ] **Step 4: Add documented entries to `.env.example`**

Locate the `# Sub-Agents` block (near the other `SUBAGENT_*` lines). Append:

```bash
# Hard cap (tokens) on the resolved `instruction` of delegate_to_sub_agent_tool
# after $ref expansion. Blocks "shovel raw data via $steps.X" — keeps sub-agent
# briefs as task statements, not data payloads. Default: 3000.
SUBAGENT_INSTRUCTION_MAX_TOKENS_RESOLVED=3000

# Feature flag: semantic_validator vetoes pointless sub-agent delegations
# (mono-domain, single delegate step, no fan-out → presumed not to satisfy H1).
# Set to false to disable the heuristic without redeploying. Default: true.
SUBAGENT_VETO_POINTLESS_ENABLED=true
```

- [ ] **Step 5: Replicate in `.env.prod.example`**

Same two blocks as Step 4, appended to the prod example file (no `.env.min.prod` change — these are optional with defaults).

- [ ] **Step 6: Write a failing settings sanity test**

Create or extend `apps/api/tests/unit/core/config/test_subagent_settings.py`:

```python
"""Sanity tests for the new sub-agent settings introduced for the ReAct redesign."""

import pytest


@pytest.mark.unit
def test_instruction_cap_default_is_3000():
    from src.core.config import settings

    assert settings.subagent_instruction_max_tokens_resolved == 3000


@pytest.mark.unit
def test_veto_pointless_default_is_true():
    from src.core.config import settings

    assert settings.subagent_veto_pointless_enabled is True
```

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/core/config/test_subagent_settings.py -v`
Expected: PASS (defaults take effect because no env var override in test env).

- [ ] **Step 7: Run mypy + ruff on touched files**

Run: `cd apps/api && .venv/Scripts/mypy src/core/constants.py src/core/config/agents.py && .venv/Scripts/ruff check src/core/constants.py src/core/config/agents.py`
Expected: no errors.

- [ ] **Step 8: Commit**

```bash
git add apps/api/src/core/constants.py apps/api/src/core/config/agents.py .env.example .env.prod.example apps/api/tests/unit/core/config/test_subagent_settings.py
git commit -m "feat(sub_agents): add settings for instruction cap and veto kill-switch

- SUBAGENT_INSTRUCTION_MAX_TOKENS_RESOLVED (default 3000): hard cap on
  delegate_to_sub_agent_tool.instruction after \$ref expansion.
- SUBAGENT_VETO_POINTLESS_ENABLED (default true): kill-switch for the
  upcoming semantic_validator veto on pointless delegations.

Foundation for the sub-agent delegation redesign (spec
docs/superpowers/specs/2026-05-13-sub-agent-delegation-redesign-design.md)."
```

---

## Task 2: Create the new ReAct prompt and register it

**Files:**
- Create: `apps/api/src/domains/agents/prompts/v1/subagent_react_prompt.txt`
- Modify: `apps/api/src/domains/agents/prompts/prompt_loader.py` — add `"subagent_react_prompt"` to the `PromptName` Literal.
- Test: `apps/api/tests/unit/domains/agents/prompts/test_subagent_react_prompt.py` (create).

- [ ] **Step 1: Write a failing test that the prompt loads with the required slots**

Create `apps/api/tests/unit/domains/agents/prompts/test_subagent_react_prompt.py`:

```python
"""Validate the subagent_react_prompt is loadable and contains the required slots."""

import pytest


@pytest.mark.unit
def test_subagent_react_prompt_loads_and_has_expertise_slot():
    from src.domains.agents.prompts.prompt_loader import load_prompt

    prompt = load_prompt("subagent_react_prompt")
    assert prompt, "subagent_react_prompt must not be empty"
    assert "{expertise}" in prompt, "must expose an {expertise} slot for the persona"
    assert "{current_datetime}" in prompt, "must expose {current_datetime} (injected by ReactSubAgentRunner)"


@pytest.mark.unit
def test_subagent_react_prompt_states_read_only_and_no_delegation():
    from src.domains.agents.prompts.prompt_loader import load_prompt

    prompt = load_prompt("subagent_react_prompt").lower()
    assert "read-only" in prompt or "read only" in prompt
    assert "delegate" in prompt  # mentions the no-delegation rule
```

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents/prompts/test_subagent_react_prompt.py -v`
Expected: FAIL (file does not exist + `"subagent_react_prompt"` is not in `PromptName` Literal).

- [ ] **Step 2: Create the prompt file**

Create `apps/api/src/domains/agents/prompts/v1/subagent_react_prompt.txt` with exactly:

```
You are a focused expert sub-agent assisting the principal assistant. Your role is strictly limited to ONE unitary expert task.

Current datetime: {current_datetime}

# Your expertise and directives
{expertise}

# Operating rules
- You have access to READ-ONLY tools (search, retrieve, analyze). You MUST NOT attempt any write, create, update, delete, or send operation. If a tool you'd normally pick is unavailable, that means it has been filtered out — do not work around it.
- You CANNOT delegate to another sub-agent. There is no `delegate_to_sub_agent_tool` in your toolset.
- Use the tools iteratively to gather what you need, reason about it, then produce a concise factual analytical text:
  - No greetings, no decorative formatting, no markdown headers unless they genuinely help.
  - Include all relevant data points (numbers, dates, names, URLs, prices) — but no filler, no padding.
  - If a tool returns an error, note what information is missing rather than fabricating.
  - Respond in the SAME LANGUAGE as the task you were given.
- Do not add suggestions, next steps, or disclaimers. Your output is consumed by another AI, not by the end user.
- When you have enough information, produce your final answer DIRECTLY (stop calling tools).
```

- [ ] **Step 3: Register the prompt in the `PromptName` Literal**

Open `apps/api/src/domains/agents/prompts/prompt_loader.py`. Locate the `PromptName = Literal[...]` block (around line 67). Add `"subagent_react_prompt",` in alphabetical position (after `"subagent_synthesis_prompt"` if present, or wherever the file's alphabetical convention dictates — match the surrounding pattern).

Example diff context:

```python
PromptName = Literal[
    ...
    "subagent_react_prompt",   # ← NEW
    "subagent_synthesis_prompt",  # kept (used by legacy SubAgentExecutor)
    ...
]
```

- [ ] **Step 4: Run the test — should pass**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents/prompts/test_subagent_react_prompt.py -v`
Expected: PASS.

- [ ] **Step 5: Mypy on prompt_loader.py**

Run: `cd apps/api && .venv/Scripts/mypy src/domains/agents/prompts/prompt_loader.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/domains/agents/prompts/v1/subagent_react_prompt.txt apps/api/src/domains/agents/prompts/prompt_loader.py apps/api/tests/unit/domains/agents/prompts/test_subagent_react_prompt.py
git commit -m "feat(sub_agents): add subagent_react_prompt scaffold

ReAct loop prompt for the new sub-agent execution path: persona slot
({expertise}), read-only constraint, no-delegation rule, output style
(concise factual text for consumption by the principal assistant)."
```

---

## Task 3: Bug fix — exclude `delegate_to_sub_agent_tool` from a sub-agent's own toolset

The function `resolve_tools_for_subagent` already excludes `list_sub_agents_tool`, `execute_sub_agent_tool`, `create_sub_agent_tool`, `get_sub_agent_results_tool` (anti-recursion) but NOT `delegate_to_sub_agent_tool` itself — latent bug. Fix it now so it can't be undone by Task 4's changes.

**Files:**
- Modify: `apps/api/src/domains/sub_agents/skill_resolver.py:34-45` (the `sub_agent_tool_names` set inside `resolve_tools_for_subagent`).
- Test: `apps/api/tests/unit/domains/sub_agents/test_skill_resolver.py` (create or extend).

- [ ] **Step 1: Write a failing test**

Create or extend `apps/api/tests/unit/domains/sub_agents/test_skill_resolver.py`:

```python
"""Anti-recursion: a sub-agent's toolset must never contain delegate_to_sub_agent_tool."""

from types import SimpleNamespace

import pytest


@pytest.mark.unit
def test_resolve_tools_for_subagent_excludes_delegate_tool():
    from src.domains.sub_agents.skill_resolver import resolve_tools_for_subagent

    fake_tools = [
        SimpleNamespace(name="delegate_to_sub_agent_tool"),
        SimpleNamespace(name="get_emails_tool"),
        SimpleNamespace(name="search_wikipedia_tool"),
    ]

    filtered = resolve_tools_for_subagent(
        allowed_tools=[],
        blocked_tools=[],
        all_tools=fake_tools,
    )
    filtered_names = {t.name for t in filtered}

    assert "delegate_to_sub_agent_tool" not in filtered_names, (
        "anti-recursion: sub-agents must never see delegate_to_sub_agent_tool"
    )
    # Other read-only tools still pass through.
    assert "get_emails_tool" in filtered_names
    assert "search_wikipedia_tool" in filtered_names
```

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/sub_agents/test_skill_resolver.py::test_resolve_tools_for_subagent_excludes_delegate_tool -v`
Expected: FAIL (current set does not include `delegate_to_sub_agent_tool`).

- [ ] **Step 2: Fix the exclusion set**

Edit `apps/api/src/domains/sub_agents/skill_resolver.py`. At the top of `resolve_tools_for_subagent`:

Before:
```python
    # Sub-agent tools are always excluded to prevent recursive spawning
    sub_agent_tool_names = {
        "list_sub_agents_tool",
        "execute_sub_agent_tool",
        "create_sub_agent_tool",
        "get_sub_agent_results_tool",
    }
```

After (use the shared constant rather than a raw string):
```python
    # Sub-agent tools are always excluded to prevent recursive spawning.
    # `delegate_to_sub_agent_tool` is the one a sub-agent's planner/ReAct loop
    # would be most tempted to call — anti-recursion depends on this exclusion.
    from src.core.constants import TOOL_NAME_DELEGATE_SUB_AGENT

    sub_agent_tool_names = {
        "list_sub_agents_tool",
        "execute_sub_agent_tool",
        "create_sub_agent_tool",
        "get_sub_agent_results_tool",
        TOOL_NAME_DELEGATE_SUB_AGENT,
    }
```

- [ ] **Step 3: Re-run the test — should pass**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/sub_agents/test_skill_resolver.py -v`
Expected: PASS.

- [ ] **Step 4: Lint**

Run: `cd apps/api && .venv/Scripts/ruff check src/domains/sub_agents/skill_resolver.py && .venv/Scripts/mypy src/domains/sub_agents/skill_resolver.py`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/domains/sub_agents/skill_resolver.py apps/api/tests/unit/domains/sub_agents/test_skill_resolver.py
git commit -m "fix(sub_agents): exclude delegate_to_sub_agent_tool from sub-agent toolset

Latent anti-recursion bug: the sub_agent_tool_names exclusion set listed
list/execute/create/get_results variants but not delegate_to_sub_agent_tool
itself. A sub-agent could theoretically receive the delegate tool in its
toolset. Add TOOL_NAME_DELEGATE_SUB_AGENT to the set."
```

---

## Task 4: Rewrite `delegate_to_sub_agent_tool` onto `ReactSubAgentRunner`

**Files:**
- Modify: `apps/api/src/domains/agents/tools/sub_agent_tools.py` — replace the body of `delegate_to_sub_agent_tool` (~270 lines → ~80 lines).
- Modify: `apps/api/tests/unit/domains/sub_agents/test_sub_agent_tools.py` — add behavior tests; the existing definition/manifest tests stay.

This is the biggest change. We do it strict TDD: tests first, then rewrite.

- [ ] **Step 1: Write the new behavior tests (failing)**

Append to `apps/api/tests/unit/domains/sub_agents/test_sub_agent_tools.py`:

```python
"""Behavior tests for the redesigned delegate_to_sub_agent_tool (ReAct runner)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class _FakeRuntime:
    """Minimal ToolRuntime stand-in for the tool's `runtime` arg."""

    def __init__(self, user_id: str = "00000000-0000-0000-0000-000000000001",
                 session_id: str = "session_abc", thread_id: str = "thread_abc"):
        self.config = {
            "configurable": {
                "user_id": user_id,
                "session_id": session_id,
                "thread_id": thread_id,
                "user_timezone": "Europe/Paris",
                "user_language": "fr",
                "__deps": None,
            },
            "metadata": {},
            "callbacks": [],
        }
        self.store = None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delegate_invokes_react_runner_with_correct_args():
    """The tool must call ReactSubAgentRunner('subagent', 'subagent_react_prompt').run(...) with task=instruction and the expertise injected via prompt_vars."""
    from src.domains.agents.tools.sub_agent_tools import delegate_to_sub_agent_tool

    runner_mock = MagicMock()
    runner_mock.run = AsyncMock(return_value=SimpleNamespace(
        final_message="Analysis of 5 emails: …",
        messages=[],
        accumulated_registry={},
        iteration_count=2,
        duration_ms=1234,
    ))

    user = SimpleNamespace(sub_agents_enabled=True)

    with patch(
        "src.domains.agents.tools.sub_agent_tools.ReactSubAgentRunner",
        return_value=runner_mock,
    ) as runner_ctor, patch(
        "src.domains.agents.tools.sub_agent_tools.UserService"
    ) as user_service_ctor:
        user_service_ctor.return_value.get_user_by_id = AsyncMock(return_value=user)

        result = await delegate_to_sub_agent_tool.ainvoke(
            {
                "expertise": "expert comptable specialise en analyse de tresorerie",
                "instruction": "Analyse les flux Q1 et identifie les anomalies.",
            },
            config={"configurable": {"runtime": _FakeRuntime()}},
        )

    # Constructor: correct LLM type + prompt
    runner_ctor.assert_called_once_with("subagent", "subagent_react_prompt")
    # run(): task is the instruction, expertise goes via prompt_vars, thread isolation, display_name with expertise prefix.
    run_kwargs = runner_mock.run.await_args.kwargs
    assert run_kwargs["task"] == "Analyse les flux Q1 et identifie les anomalies."
    assert run_kwargs["prompt_vars"] == {"expertise": "expert comptable specialise en analyse de tresorerie"}
    assert run_kwargs["thread_prefix"] == "subagent"
    assert run_kwargs["display_name"].startswith("sub-agent: ")
    # recursion_limit pulled from settings.
    from src.core.config import settings
    assert run_kwargs["recursion_limit"] == settings.subagent_default_max_iterations
    # Output mapping: final_message → structured_data["analysis"].
    assert result.success is True
    assert result.structured_data["analysis"].startswith("Analysis of 5 emails")
    assert result.structured_data["expertise"] == "expert comptable specialise en analyse de tresorerie"
    assert result.structured_data["type"] == "sub_agent_analysis"
    assert result.metadata["iteration_count"] == 2
    assert result.metadata["duration_ms"] == 1234


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delegate_returns_failure_when_runner_signals_error():
    """If ReactSubAgentRunner.run returns a final_message starting with 'Error:', the tool surfaces a UnifiedToolOutput.failure."""
    from src.domains.agents.tools.sub_agent_tools import delegate_to_sub_agent_tool

    runner_mock = MagicMock()
    runner_mock.run = AsyncMock(return_value=SimpleNamespace(
        final_message="Error: GraphRecursionError: limit reached",
        messages=[], accumulated_registry={}, iteration_count=5, duration_ms=9999,
    ))
    user = SimpleNamespace(sub_agents_enabled=True)

    with patch(
        "src.domains.agents.tools.sub_agent_tools.ReactSubAgentRunner",
        return_value=runner_mock,
    ), patch(
        "src.domains.agents.tools.sub_agent_tools.UserService"
    ) as user_service_ctor:
        user_service_ctor.return_value.get_user_by_id = AsyncMock(return_value=user)

        result = await delegate_to_sub_agent_tool.ainvoke(
            {"expertise": "x", "instruction": "y"},
            config={"configurable": {"runtime": _FakeRuntime()}},
        )

    assert result.success is False
    assert "Error" in (result.message or "") or "Error" in str(result)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delegate_blocked_when_user_pref_disabled():
    """User with sub_agents_enabled=False receives FEATURE_DISABLED, no runner call."""
    from src.domains.agents.tools.sub_agent_tools import delegate_to_sub_agent_tool

    user = SimpleNamespace(sub_agents_enabled=False)
    runner_mock = MagicMock()
    runner_mock.run = AsyncMock()

    with patch(
        "src.domains.agents.tools.sub_agent_tools.ReactSubAgentRunner",
        return_value=runner_mock,
    ), patch(
        "src.domains.agents.tools.sub_agent_tools.UserService"
    ) as user_service_ctor:
        user_service_ctor.return_value.get_user_by_id = AsyncMock(return_value=user)

        result = await delegate_to_sub_agent_tool.ainvoke(
            {"expertise": "x", "instruction": "y"},
            config={"configurable": {"runtime": _FakeRuntime()}},
        )

    assert result.success is False
    runner_mock.run.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delegate_blocked_when_already_inside_subagent():
    """Depth guard: a runtime whose session_id starts with 'subagent_' is blocked."""
    from src.domains.agents.tools.sub_agent_tools import delegate_to_sub_agent_tool

    rt = _FakeRuntime(session_id="subagent_abc")

    result = await delegate_to_sub_agent_tool.ainvoke(
        {"expertise": "x", "instruction": "y"},
        config={"configurable": {"runtime": rt}},
    )
    assert result.success is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delegate_does_not_create_orm_record_or_call_redis_budget():
    """The redesigned tool must NOT touch SubAgentService.create nor the Redis daily budget."""
    from src.domains.agents.tools.sub_agent_tools import delegate_to_sub_agent_tool

    runner_mock = MagicMock()
    runner_mock.run = AsyncMock(return_value=SimpleNamespace(
        final_message="ok", messages=[], accumulated_registry={}, iteration_count=1, duration_ms=10,
    ))
    user = SimpleNamespace(sub_agents_enabled=True)

    with patch(
        "src.domains.agents.tools.sub_agent_tools.ReactSubAgentRunner",
        return_value=runner_mock,
    ), patch(
        "src.domains.agents.tools.sub_agent_tools.UserService"
    ) as user_service_ctor, patch(
        "src.domains.agents.tools.sub_agent_tools.SubAgentService",
        create=True,  # ← if accidentally imported, would be a mock; we'll assert no call
    ) as subagent_service_ctor, patch(
        "src.infrastructure.cache.redis.get_redis_cache",
        create=True,
    ) as redis_mock:
        user_service_ctor.return_value.get_user_by_id = AsyncMock(return_value=user)

        await delegate_to_sub_agent_tool.ainvoke(
            {"expertise": "x", "instruction": "y"},
            config={"configurable": {"runtime": _FakeRuntime()}},
        )

    # SubAgentService must not be instantiated at all.
    subagent_service_ctor.assert_not_called()
    # Redis must not be touched for daily budget.
    redis_mock.assert_not_called()
```

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/sub_agents/test_sub_agent_tools.py -v -k "test_delegate_"`
Expected: tests FAIL (the current tool body still uses `SubAgentExecutor`, creates ORM records, etc.).

- [ ] **Step 2: Read the current body, then rewrite it**

Open `apps/api/src/domains/agents/tools/sub_agent_tools.py`. Replace **the entire body** of `delegate_to_sub_agent_tool` (from line ~85 `config = validate_runtime_config(...)` to the end of the function before `except` at ~265) with the version below. Keep the `@tool`, `@track_tool_metrics` decorators and the signature unchanged. Update imports as needed.

Replace the function body with:

```python
    config = validate_runtime_config(runtime, "delegate_to_sub_agent_tool")
    if isinstance(config, UnifiedToolOutput):
        return config

    try:
        # Depth check: prevent sub-agent from spawning sub-sub-agents.
        # ReactSubAgentRunner uses thread_prefix="subagent" → nested thread_id
        # starts with "subagent_". We also accept legacy session_id prefix.
        if (config.session_id and config.session_id.startswith("subagent_")) or (
            (config.thread_id or "").startswith("subagent_")
        ):
            return UnifiedToolOutput.failure(
                message="Sub-agents cannot delegate to other sub-agents (depth limit reached).",
                error_code="DEPTH_LIMIT_EXCEEDED",
            )

        user_id = parse_user_id(config.user_id)

        # User preference check (lightweight, short-lived DB session).
        from src.infrastructure.database.session import get_db_context
        from src.domains.users.service import UserService

        async with get_db_context() as db:
            user_service = UserService(db)
            user_obj = await user_service.get_user_by_id(user_id)
            if user_obj and not getattr(user_obj, "sub_agents_enabled", True):
                return UnifiedToolOutput.failure(
                    message=(
                        "Sub-agents are disabled in your preferences. "
                        "Enable them in Settings to use this feature."
                    ),
                    error_code="FEATURE_DISABLED",
                )

        # Build read-only toolset for the sub-agent.
        from src.domains.agents.registry import get_global_registry
        from src.domains.sub_agents.constants import SUBAGENT_DEFAULT_BLOCKED_TOOLS
        from src.domains.sub_agents.skill_resolver import resolve_tools_for_subagent

        all_tools = get_global_registry().get_all_tool_instances()
        read_only_tools = resolve_tools_for_subagent(
            allowed_tools=[],
            blocked_tools=SUBAGENT_DEFAULT_BLOCKED_TOOLS,
            all_tools=all_tools,
        )

        # Execute via the existing generic ReAct runner.
        from src.core.config import settings
        from src.domains.agents.tools.react_runner import ReactSubAgentRunner

        runner = ReactSubAgentRunner("subagent", "subagent_react_prompt")
        react_result = await runner.run(
            task=instruction,
            tools=read_only_tools,
            prompt_vars={"expertise": expertise},
            parent_runtime=runtime,
            thread_prefix="subagent",
            recursion_limit=settings.subagent_default_max_iterations,
            display_name=f"sub-agent: {expertise[:40]}",
        )

        # Map the runner's result to a UnifiedToolOutput.
        final = react_result.final_message or ""
        if final.startswith("Error:"):
            return UnifiedToolOutput.failure(
                message=(
                    f"Sub-agent '{expertise[:60]}' did not complete: {final[:300]}"
                ),
                error_code="EXECUTION_FAILED",
                metadata={
                    "expertise": expertise,
                    "duration_ms": react_result.duration_ms,
                    "iteration_count": react_result.iteration_count,
                },
            )

        _MAX_SUMMARY_LENGTH = 200
        summary = (
            final[:_MAX_SUMMARY_LENGTH] + "..."
            if len(final) > _MAX_SUMMARY_LENGTH
            else final
        )

        return UnifiedToolOutput.action_success(
            message=summary,
            structured_data={
                "analysis": final,
                "expertise": expertise,
                "type": "sub_agent_analysis",
            },
            metadata={
                "expertise": expertise,
                "duration_ms": react_result.duration_ms,
                "iteration_count": react_result.iteration_count,
            },
        )

    except Exception as e:
        return handle_tool_exception(
            e,
            "delegate_to_sub_agent_tool",
            {"expertise": expertise, "instruction": instruction[:100]},
        )
```

Also update the imports at the top of the file: remove the now-unused imports (`SubAgentCreate`, `SubAgentService`, `SubAgentExecutor`, `SubAgentRepository`, `SubAgentCreatedBy`, `uuid4`, `MessageTokenSummary`, `Decimal`, `get_cached_usd_eur_rate`, `select`, `current_tracker`, `structlog` if no longer needed) and add the new ones above.

Check: the function signature `async def delegate_to_sub_agent_tool(expertise, instruction, runtime)` is unchanged. The decorators `@tool` and `@track_tool_metrics` are unchanged.

- [ ] **Step 3: Verify the global registry exposes `get_all_tool_instances` (or use the right accessor)**

Run: `Grep tool — pattern "def get_all_tool_instances\\|def get_all_tools" in apps/api/src/domains/agents/registry/`
Expected: a method that returns `list[BaseTool]`. If the name is different (e.g., `get_all_tools()`, `tool_instances`, etc.), adapt the call in Step 2. If no such accessor exists, fall back to building it from the per-tool registry — but verify first; the registry almost certainly has one already used by other consumers.

- [ ] **Step 4: Run the new behavior tests — should pass**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/sub_agents/test_sub_agent_tools.py -v`
Expected: PASS (both old definition tests and new behavior tests).

- [ ] **Step 5: Run mypy + ruff + black**

Run: `cd apps/api && .venv/Scripts/mypy src/domains/agents/tools/sub_agent_tools.py && .venv/Scripts/ruff check src/domains/agents/tools/sub_agent_tools.py && .venv/Scripts/black --check src/domains/agents/tools/sub_agent_tools.py`
Expected: no errors. (If black wants to reformat, run without `--check` then re-add.)

- [ ] **Step 6: Smoke-test in Docker dev**

Per project rules (CLAUDE.md « Dev Container Pitfalls » + memory `feedback_verify_runtime`): never declare done without verifying app startup in the dev container.

Run:
```bash
task dev:detach
docker logs lia-api-dev --tail 60
```
Expected: container healthy, no import errors, no NameError at import of `sub_agent_tools.py`. Then `task stop` (or leave it up if you'll exercise the next tasks against it).

- [ ] **Step 7: Commit**

```bash
git add apps/api/src/domains/agents/tools/sub_agent_tools.py apps/api/tests/unit/domains/sub_agents/test_sub_agent_tools.py
git commit -m "refactor(sub_agents): rewrite delegate_to_sub_agent_tool onto ReactSubAgentRunner

Replace the bespoke SubAgentExecutor pipeline (analyse → SmartPlanner →
synthese — 3 LLM calls per delegation) with the existing generic
ReactSubAgentRunner('subagent', 'subagent_react_prompt'). The sub-agent
becomes a single scoped ReAct loop over a read-only toolset, with
recursion_limit = settings.subagent_default_max_iterations.

Removed for the ephemeral path: ORM record creation/cleanup, Redis daily
budget check, manual parent-tracker token consolidation. Token attribution
flows automatically via TokenTrackingCallback + node_name_override.

SubAgentExecutor is no longer reachable from delegate_to_sub_agent_tool
but is preserved for the (dormant) /sub-agents REST path."
```

---

## Task 5: Rewrite `_build_sub_agents_section` (planner prompt — H1)

**Files:**
- Modify: `apps/api/src/domains/agents/services/smart_planner_service.py:953-1003` — replace the function body.
- Test: extend `apps/api/tests/unit/domains/agents/services/test_smart_planner_prompt_sections.py` (create if missing, or add to wherever `_build_sub_agents_section` is tested today — search first).

- [ ] **Step 1: Locate existing tests of `_build_sub_agents_section`**

Run: `Grep tool — pattern "_build_sub_agents_section\\|sub_agents_section" in apps/api/tests/`
Expected: `tests/unit/domains/sub_agents/test_f6_prompt_suppression.py` (and possibly others). Read what they assert.

- [ ] **Step 2: Write the failing tests for H1 wording**

Append to (or create) `apps/api/tests/unit/domains/agents/services/test_smart_planner_prompt_sections.py`:

```python
"""Validate the rewritten {sub_agents_section} for H1 enforcement."""

import pytest


@pytest.mark.unit
def test_sub_agents_section_states_h1_decision_test(monkeypatch):
    """The section must articulate the H1 test (expert persona materially better)."""
    monkeypatch.setattr(
        "src.core.config.get_settings",
        lambda: type("S", (), {"sub_agents_enabled": True})(),
    )
    from src.domains.agents.services.smart_planner_service import SmartPlannerService

    section = SmartPlannerService._build_sub_agents_section()

    lo = section.lower()
    assert "materially better" in lo, "must state the H1 'materially better' decision test"
    assert "do not delegate" in lo or "do not paste raw data" in lo


@pytest.mark.unit
def test_sub_agents_section_no_longer_mentions_timeout_seconds(monkeypatch):
    """Regression: timeout_seconds was a hallucinated param the planner kept emitting."""
    monkeypatch.setattr(
        "src.core.config.get_settings",
        lambda: type("S", (), {"sub_agents_enabled": True})(),
    )
    from src.domains.agents.services.smart_planner_service import SmartPlannerService

    section = SmartPlannerService._build_sub_agents_section()

    assert "timeout_seconds" not in section


@pytest.mark.unit
def test_sub_agents_section_returns_empty_when_disabled(monkeypatch):
    monkeypatch.setattr(
        "src.core.config.get_settings",
        lambda: type("S", (), {"sub_agents_enabled": False})(),
    )
    from src.domains.agents.services.smart_planner_service import SmartPlannerService

    assert SmartPlannerService._build_sub_agents_section() == ""
```

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents/services/test_smart_planner_prompt_sections.py -v`
Expected: FAIL (current section uses different wording, still contains `timeout_seconds`).

- [ ] **Step 3: Replace the function body**

Edit `apps/api/src/domains/agents/services/smart_planner_service.py`, function `_build_sub_agents_section`. Keep the early-return guards (`sub_agents_enabled`, `exclude_sub_agents_from_prompt` ContextVar) unchanged. Replace the `return ("…")` block with:

```python
        return (
            "SUB-AGENT DELEGATION (Optional Advanced Capability):\n"
            "You may delegate a task to an ephemeral expert sub-agent via "
            "`delegate_to_sub_agent_tool`. Use it ONLY when the test below is satisfied.\n\n"
            "DECISION TEST — delegate IFF:\n"
            "A specialized expert persona, given a focused prompt and read-only tools, "
            "would produce a MATERIALLY BETTER answer than you handling the task yourself "
            "with your normal tools.\n"
            "Examples where delegation helps: deep accounting/legal/technical analysis, "
            "multi-source comparison with cross-referencing, independent parallel research "
            "tracks (fan-out to 2+ different experts).\n\n"
            "DO NOT DELEGATE for:\n"
            "- Fetching and summarizing data (emails, calendar, contacts, files) — "
            "  do it yourself with the relevant tool + your response.\n"
            "- Simple factual lookups, standard CRUD operations, single-tool tasks.\n"
            "- Tasks requiring user confirmation (sub-agents are read-only and have no HITL).\n\n"
            "HOW TO USE delegate_to_sub_agent_tool:\n"
            "- `expertise`: specialist role/directives "
            "(e.g. 'expert comptable specialise en analyse de tresorerie').\n"
            "- `instruction`: a clear TASK STATEMENT — what to analyze, what sources to use, "
            "  what output format. DO NOT PASTE RAW DATA HERE. The sub-agent has its own "
            "  read-only tools and fetches what it needs.\n"
            "- Independent sub-agents (fan-out research) → leave `depends_on` empty; "
            "  they run in parallel.\n"
            "- Chaining sub-agent → sub-agent: reference `$steps.step_N.analysis` "
            "  (short synthesized text, OK).\n"
            "- Never reference raw tool outputs (`$steps.step_N.<data>`) inside `instruction` — "
            "  the resolved string is hard-capped and oversized payloads are rejected.\n"
            "- Handle mutations (send_email, create_event, ...) YOURSELF after sub-agent results.\n\n"
            "ANTI-PATTERN — AVOID DUPLICATING WORK:\n"
            "- BAD: step_1=get_emails_tool, step_2=delegate(expert, "
            "instruction='analyse $steps.step_1.data')\n"
            "- GOOD: step_1=delegate(expert, instruction='analyse the last N emails matching "
            "<criteria> and produce <output>')\n"
            "- The sub-agent has tool access — it does its own fetching.\n"
        )
```

- [ ] **Step 4: Re-run the new tests + the existing prompt-suppression regression**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents/services/test_smart_planner_prompt_sections.py tests/unit/domains/sub_agents/test_f6_prompt_suppression.py -v`
Expected: ALL PASS.

- [ ] **Step 5: Lint + types**

Run: `cd apps/api && .venv/Scripts/ruff check src/domains/agents/services/smart_planner_service.py && .venv/Scripts/black --check src/domains/agents/services/smart_planner_service.py && .venv/Scripts/mypy src/domains/agents/services/smart_planner_service.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/domains/agents/services/smart_planner_service.py apps/api/tests/unit/domains/agents/services/test_smart_planner_prompt_sections.py
git commit -m "feat(planner): rewrite {sub_agents_section} for H1 decision test

Replace the vague 'when to delegate' prose with a crisp 'materially
better' decision test. Add explicit DO-NOT-DELEGATE list (data
fetching/summarization, CRUD, simple lookups). Remove the hallucinated
timeout_seconds directive (not a tool parameter — was stripped at exec
time). State that raw \$steps.X.<data> in instruction will be rejected
(matches Task 7's post-resolution cap)."
```

---

## Task 6: Veto in `semantic_validator` for pointless delegations

**Files:**
- Modify: `apps/api/src/domains/agents/orchestration/semantic_validator.py` — add a `SemanticIssueType.POINTLESS_SUB_AGENT_DELEGATION` enum member, a new validator function `validate_sub_agent_delegation_justified(plan, query_intelligence) -> tuple[bool, str | None, SemanticIssueType | None]`, and call it from `validate_execution_plan` after `validate_for_each_patterns`.
- Modify: `apps/api/src/domains/agents/nodes/semantic_validator_node.py` — when the issue type is `POINTLESS_SUB_AGENT_DELEGATION`, set both `STATE_KEY_NEEDS_REPLAN=True` and `STATE_KEY_EXCLUDE_SUB_AGENT_TOOLS=True` in `state_updates`.
- Test: `apps/api/tests/unit/domains/agents/orchestration/test_semantic_validator_pointless_delegation.py` (create).

- [ ] **Step 1: Write the failing veto tests**

Create `apps/api/tests/unit/domains/agents/orchestration/test_semantic_validator_pointless_delegation.py`:

```python
"""Veto on pointless sub-agent delegation (H1 backstop)."""

from types import SimpleNamespace

import pytest


def _plan_with_steps(*tool_names: str):
    """Build a minimal ExecutionPlan with the listed tools (no dependencies)."""
    from src.domains.agents.orchestration.plan_schemas import ExecutionPlan, ExecutionStep

    steps = [
        ExecutionStep(
            step_id=f"step_{i + 1}",
            tool_name=name,
            agent_name=f"{name.split('_')[0]}_agent",
            description=f"call {name}",
            parameters={"expertise": "x", "instruction": "y"} if name == "delegate_to_sub_agent_tool" else {},
        )
        for i, name in enumerate(tool_names)
    ]
    return ExecutionPlan(plan_id="t", steps=steps)


def _qi(primary_domain: str = "email", secondary=None):
    return SimpleNamespace(
        primary_domain=primary_domain,
        domains=[primary_domain] + (secondary or []),
        for_each_detected=False,
        for_each_collection_key=None,
        cardinality_magnitude=None,
    )


@pytest.mark.unit
def test_veto_triggers_on_fetch_then_delegate_mono_domain(monkeypatch):
    """The exact pattern that exploded: [get_emails, delegate] mono-domain → veto."""
    monkeypatch.setattr(
        "src.core.config.get_settings",
        lambda: SimpleNamespace(
            subagent_veto_pointless_enabled=True,
            planner_max_replans=2,
            for_each_max_hard_limit=20,
        ),
    )
    from src.domains.agents.orchestration.semantic_validator import (
        SemanticIssueType,
        validate_sub_agent_delegation_justified,
    )

    plan = _plan_with_steps("get_emails_tool", "delegate_to_sub_agent_tool")
    is_valid, feedback, issue = validate_sub_agent_delegation_justified(plan, _qi("email"))

    assert is_valid is False
    assert issue == SemanticIssueType.POINTLESS_SUB_AGENT_DELEGATION
    assert feedback and "delegate" in feedback.lower()


@pytest.mark.unit
def test_veto_does_not_trigger_on_fan_out(monkeypatch):
    """Two parallel delegates to different experts → presumed legit fan-out."""
    monkeypatch.setattr(
        "src.core.config.get_settings",
        lambda: SimpleNamespace(subagent_veto_pointless_enabled=True),
    )
    from src.domains.agents.orchestration.semantic_validator import (
        validate_sub_agent_delegation_justified,
    )

    plan = _plan_with_steps("delegate_to_sub_agent_tool", "delegate_to_sub_agent_tool")
    is_valid, _, _ = validate_sub_agent_delegation_justified(plan, _qi("research"))
    assert is_valid is True


@pytest.mark.unit
def test_veto_does_not_trigger_on_multi_domain(monkeypatch):
    monkeypatch.setattr(
        "src.core.config.get_settings",
        lambda: SimpleNamespace(subagent_veto_pointless_enabled=True),
    )
    from src.domains.agents.orchestration.semantic_validator import (
        validate_sub_agent_delegation_justified,
    )

    plan = _plan_with_steps("get_emails_tool", "delegate_to_sub_agent_tool")
    is_valid, _, _ = validate_sub_agent_delegation_justified(
        plan, _qi("email", secondary=["calendar"])
    )
    assert is_valid is True


@pytest.mark.unit
def test_veto_short_circuits_when_kill_switch_off(monkeypatch):
    """Setting SUBAGENT_VETO_POINTLESS_ENABLED=false disables the heuristic entirely."""
    monkeypatch.setattr(
        "src.core.config.get_settings",
        lambda: SimpleNamespace(subagent_veto_pointless_enabled=False),
    )
    from src.domains.agents.orchestration.semantic_validator import (
        validate_sub_agent_delegation_justified,
    )

    plan = _plan_with_steps("get_emails_tool", "delegate_to_sub_agent_tool")
    is_valid, _, _ = validate_sub_agent_delegation_justified(plan, _qi("email"))
    assert is_valid is True


@pytest.mark.unit
def test_veto_does_not_trigger_when_no_delegate_step(monkeypatch):
    monkeypatch.setattr(
        "src.core.config.get_settings",
        lambda: SimpleNamespace(subagent_veto_pointless_enabled=True),
    )
    from src.domains.agents.orchestration.semantic_validator import (
        validate_sub_agent_delegation_justified,
    )

    plan = _plan_with_steps("get_emails_tool", "send_email_tool")
    is_valid, _, _ = validate_sub_agent_delegation_justified(plan, _qi("email"))
    assert is_valid is True
```

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents/orchestration/test_semantic_validator_pointless_delegation.py -v`
Expected: FAIL (function and enum member do not exist).

- [ ] **Step 2: Add the `SemanticIssueType` enum member**

Edit `apps/api/src/domains/agents/orchestration/semantic_validator.py`. Inside the `class SemanticIssueType(str, Enum)` (around line 65), add:

```python
    POINTLESS_SUB_AGENT_DELEGATION = "pointless_sub_agent_delegation"  # H1: single delegate step, mono-domain, no fan-out
```

- [ ] **Step 3: Add the `validate_sub_agent_delegation_justified` function**

In the same file, near `validate_for_each_patterns` (around line 561), add:

```python
def validate_sub_agent_delegation_justified(
    plan: "ExecutionPlan",
    query_intelligence: Any,
) -> tuple[bool, str | None, SemanticIssueType | None]:
    """Veto pointless sub-agent delegations (H1 backstop).

    Heuristic: the delegation is presumed NOT to satisfy H1 ("an expert prompt
    would produce a materially better answer than the assistant doing it itself")
    when ALL of the following hold:
    - exactly 1 `delegate_to_sub_agent_tool` step (no fan-out);
    - the query is mono-domain (a single non-trivial domain — sub_agent pseudo-domains aside);
    - no other substantive work in the plan (i.e. the delegate is the only/main step,
      possibly preceded by a single data-fetch step that the planner added to feed it).

    Returns (is_valid, feedback, issue_type). is_valid=False triggers the
    semantic_validator_node to set needs_replan=True + exclude_sub_agent_tools=True.

    Honors the SUBAGENT_VETO_POINTLESS_ENABLED kill-switch.
    """
    from src.core.config import get_settings

    settings = get_settings()
    if not getattr(settings, "subagent_veto_pointless_enabled", True):
        return True, None, None

    delegate_steps = [s for s in plan.steps if s.tool_name == TOOL_NAME_DELEGATE_SUB_AGENT]
    if len(delegate_steps) != 1:
        # Zero delegations → nothing to veto. Two+ → presumed fan-out, legit.
        return True, None, None

    # Mono-domain check (ignore None / empty / pseudo "sub_agent" entries).
    domains = getattr(query_intelligence, "domains", None) or []
    real_domains = [d for d in domains if d and d != "sub_agent"]
    if len(set(real_domains)) > 1:
        return True, None, None

    # The delegate step is the only/main substantive step?
    # We allow up to one auxiliary step (typically the fetch the planner added).
    substantive_steps = [
        s for s in plan.steps
        if s.tool_name and s.tool_name != TOOL_NAME_DELEGATE_SUB_AGENT
    ]
    if len(substantive_steps) > 1:
        # Real multi-step work alongside the delegation → presumed legit.
        return True, None, None

    feedback = (
        "POINTLESS_SUB_AGENT_DELEGATION: the plan delegates a mono-domain "
        "single-tool task to a sub-agent. A specialized expert persona is "
        "unlikely to produce a materially better answer than the assistant "
        "handling the task directly. Re-plan without delegation: fetch the "
        "data with the relevant tool, then synthesize in the response."
    )
    return False, feedback, SemanticIssueType.POINTLESS_SUB_AGENT_DELEGATION
```

Ensure `TOOL_NAME_DELEGATE_SUB_AGENT` is imported at the top of the file (it already is, used by `validate_for_each_patterns` Check 1).

- [ ] **Step 4: Wire the new check into `validate_execution_plan`**

Still in `semantic_validator.py`. Find the call to `validate_for_each_patterns` (around line 1376). Immediately AFTER its handling block (after the `if not for_each_valid and for_each_issue:` block returns), add:

```python
        # =====================================================================
        # SUB-AGENT DELEGATION JUSTIFICATION (H1 backstop)
        # =====================================================================
        sa_valid, sa_feedback, sa_issue = validate_sub_agent_delegation_justified(
            plan=plan,
            query_intelligence=query_intelligence,
        )
        if not sa_valid and sa_issue:
            logger.warning(
                "semantic_validation_pointless_sub_agent_delegation",
                step_count=len(plan.steps),
                domains=getattr(query_intelligence, "domains", None),
                duration_ms=int((time.time() - start_time) * 1000),
            )
            return SemanticValidationResult(
                is_valid=False,
                issues=[
                    SemanticIssue(
                        issue_type=sa_issue,
                        description="Sub-agent delegation not justified by H1",
                        suggested_fix=sa_feedback or "Re-plan without delegation",
                        severity="medium",
                    )
                ],
                confidence=1.0,
                requires_clarification=False,
                clarification_questions=[],
                validation_duration_seconds=time.time() - start_time,
                criticality=CriticalityLevel.MEDIUM,
            )
```

- [ ] **Step 5: Update `semantic_validator_node` to set the replan flags on this issue type**

Edit `apps/api/src/domains/agents/nodes/semantic_validator_node.py`. Find where `state_updates` is built when `validation_result.is_valid is False` (around line 323). After that line, add:

```python
        # H1 veto: pointless sub-agent delegation → replan with sub-agent tools excluded.
        if any(
            issue.issue_type == SemanticIssueType.POINTLESS_SUB_AGENT_DELEGATION
            for issue in validation_result.issues
        ):
            from src.domains.agents.constants import (
                STATE_KEY_EXCLUDE_SUB_AGENT_TOOLS,
                STATE_KEY_NEEDS_REPLAN,
            )

            state_updates[STATE_KEY_NEEDS_REPLAN] = True
            state_updates[STATE_KEY_EXCLUDE_SUB_AGENT_TOOLS] = True
            logger.info(
                "semantic_validator_vetoed_sub_agent_delegation",
                plan_id=execution_plan.plan_id if execution_plan else None,
            )
```

Ensure `SemanticIssueType` is imported at the top of `semantic_validator_node.py` (it likely is via the validator imports — verify).

- [ ] **Step 6: Run veto tests — should pass**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents/orchestration/test_semantic_validator_pointless_delegation.py -v`
Expected: PASS.

- [ ] **Step 7: Run the broader semantic_validator test suite to catch regressions**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents/orchestration/ -v -k "validator or semantic"`
Expected: all PASS.

- [ ] **Step 8: Lint + types**

Run: `cd apps/api && .venv/Scripts/ruff check src/domains/agents/orchestration/semantic_validator.py src/domains/agents/nodes/semantic_validator_node.py && .venv/Scripts/black --check src/domains/agents/orchestration/semantic_validator.py src/domains/agents/nodes/semantic_validator_node.py && .venv/Scripts/mypy src/domains/agents/orchestration/semantic_validator.py src/domains/agents/nodes/semantic_validator_node.py`
Expected: no errors.

- [ ] **Step 9: Commit**

```bash
git add apps/api/src/domains/agents/orchestration/semantic_validator.py apps/api/src/domains/agents/nodes/semantic_validator_node.py apps/api/tests/unit/domains/agents/orchestration/test_semantic_validator_pointless_delegation.py
git commit -m "feat(semantic_validator): veto pointless sub-agent delegations (H1)

Add validate_sub_agent_delegation_justified() and a new
SemanticIssueType.POINTLESS_SUB_AGENT_DELEGATION. When the heuristic
triggers (1 delegate step, mono-domain, no fan-out, no other substantive
work), the validator marks the plan invalid and the node sets
needs_replan=True + exclude_sub_agent_tools=True → the existing F6 replan
path generates a new plan without delegation.

Honors SUBAGENT_VETO_POINTLESS_ENABLED (default true) — flip to false in
.env to disable the heuristic in prod without redeploying."
```

---

## Task 7: Post-resolution `instruction` cap in `parallel_executor`

**Files:**
- Modify: `apps/api/src/domains/agents/orchestration/parallel_executor.py:2275-2280` (right after `_resolve_step_references`).
- Test: `apps/api/tests/unit/domains/agents/orchestration/test_parallel_executor_instruction_cap.py` (create).

- [ ] **Step 1: Write the failing tests**

Create `apps/api/tests/unit/domains/agents/orchestration/test_parallel_executor_instruction_cap.py`:

```python
"""Post-resolution cap on delegate_to_sub_agent_tool.instruction."""

from unittest.mock import MagicMock, patch

import pytest


def _delegate_step_with_resolved_instruction(text: str):
    """Build a TOOL step that, after $ref resolution, has the given instruction value."""
    from src.domains.agents.orchestration.plan_schemas import ExecutionStep

    return ExecutionStep(
        step_id="step_1",
        tool_name="delegate_to_sub_agent_tool",
        agent_name="sub_agent_agent",
        description="delegate",
        # Use the literal value — resolution is a no-op for plain strings.
        parameters={"expertise": "x", "instruction": text},
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_oversized_resolved_instruction_returns_invalid_input(monkeypatch):
    """An instruction whose post-resolution token estimate exceeds the cap → INVALID_INPUT."""
    monkeypatch.setattr(
        "src.core.config.get_settings",
        lambda: MagicMock(subagent_instruction_max_tokens_resolved=100),
    )
    from src.domains.agents.orchestration.parallel_executor import _execute_tool_step

    # ~4 chars per token → 100 tokens ≈ 400 chars. We blow past it.
    huge_text = "x " * 10_000  # ~20000 chars ≈ ~5000 tokens

    step = _delegate_step_with_resolved_instruction(huge_text)

    result = await _execute_tool_step(
        step=step,
        completed_steps={},
        config={"configurable": {"user_id": "00000000-0000-0000-0000-000000000001"}},
        wave_id=0,
        store=None,
    )

    assert result.success is False
    from src.domains.agents.tools.common import ToolErrorCode

    assert result.error_code == ToolErrorCode.INVALID_INPUT
    assert "instruction" in (result.error or "").lower()
    assert "tokens" in (result.error or "").lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_under_cap_instruction_passes_through(monkeypatch):
    """Below the cap → the step proceeds to normal tool invocation (mocked)."""
    monkeypatch.setattr(
        "src.core.config.get_settings",
        lambda: MagicMock(subagent_instruction_max_tokens_resolved=3000),
    )
    from src.domains.agents.orchestration import parallel_executor

    step = _delegate_step_with_resolved_instruction("Analyse last 5 emails from Hua.")

    # Patch the downstream pieces so the step gets past the cap and reaches
    # the actual tool call (which we don't care about here).
    with patch.object(
        parallel_executor, "_get_tool_manifest_for_step",
        return_value=(MagicMock(), None),
    ), patch.object(
        parallel_executor, "_validate_required_params", return_value=(True, None),
    ), patch.object(
        parallel_executor, "_coerce_args_to_schema", side_effect=lambda a, s: a,
    ):
        # Below the cap; the cap check must NOT short-circuit.
        # We deliberately let the call fail later (no real tool); we only assert
        # that the failure is NOT the cap error.
        result = await parallel_executor._execute_tool_step(
            step=step,
            completed_steps={},
            config={"configurable": {"user_id": "00000000-0000-0000-0000-000000000001"}},
            wave_id=0,
            store=None,
        )

    if result.success is False:
        assert "instruction" not in (result.error or "").lower() or "tokens" not in (result.error or "").lower()
```

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents/orchestration/test_parallel_executor_instruction_cap.py -v`
Expected: FAIL (no cap check exists yet).

- [ ] **Step 2: Add the cap check in `_execute_tool_step`**

Edit `apps/api/src/domains/agents/orchestration/parallel_executor.py`. Find the block after `_resolve_step_references` (around line 2275-2280). Add the cap check IMMEDIATELY after the `if error_result: return error_result` line, BEFORE the manifest lookup.

Insert:

```python
    # ------------------------------------------------------------------
    # H2 backstop: post-resolution cap on delegate_to_sub_agent_tool.instruction.
    # The manifest's max_length=5000 chars only constrains the TEMPLATE
    # ("…$steps.X.…", ~50 chars). After $ref expansion, raw payloads can
    # explode the string (incident 2026-05-12: 114K tokens). Re-validate
    # the resolved value here — the only place where the actual size is known.
    # ------------------------------------------------------------------
    from src.core.constants import TOOL_NAME_DELEGATE_SUB_AGENT

    if step.tool_name == TOOL_NAME_DELEGATE_SUB_AGENT:
        from src.core.config import get_settings
        from src.domains.agents.tools.common import ToolErrorCode
        from src.infrastructure.llm.providers.token_counter import EstimationTokenCounter

        instruction_value = resolved_args.get("instruction") or ""
        if isinstance(instruction_value, str) and instruction_value:
            token_estimate = EstimationTokenCounter().count(instruction_value, model="any")
            cap = get_settings().subagent_instruction_max_tokens_resolved
            if token_estimate > cap:
                logger.warning(
                    "subagent_instruction_oversized_after_resolution",
                    step_id=step.step_id,
                    token_estimate=token_estimate,
                    cap=cap,
                    sample=instruction_value[:200],
                )
                execution_time_ms = int((time.time() - start_time) * 1000)
                return StepResult(
                    step_id=step.step_id,
                    step_type=StepType.TOOL,
                    tool_name=step.tool_name,
                    args=resolved_args,
                    success=False,
                    error=(
                        f"Sub-agent instruction too large after reference "
                        f"resolution ({token_estimate} tokens > cap {cap}) — "
                        f"likely a $steps reference to a raw payload. "
                        f"Pass a task statement, not data; the sub-agent will "
                        f"fetch what it needs with its own tools."
                    ),
                    error_code=ToolErrorCode.INVALID_INPUT,
                    execution_time_ms=execution_time_ms,
                    wave_id=wave_id,
                )
```

(Verify the file's existing imports — `StepResult`, `StepType`, `logger`, `time` are all already imported at the top of `parallel_executor.py`.)

- [ ] **Step 3: Re-run the cap tests — should pass**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents/orchestration/test_parallel_executor_instruction_cap.py -v`
Expected: PASS.

- [ ] **Step 4: Run broader executor regression**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents/orchestration/ -v`
Expected: all PASS.

- [ ] **Step 5: Lint + types**

Run: `cd apps/api && .venv/Scripts/ruff check src/domains/agents/orchestration/parallel_executor.py && .venv/Scripts/black --check src/domains/agents/orchestration/parallel_executor.py && .venv/Scripts/mypy src/domains/agents/orchestration/parallel_executor.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/domains/agents/orchestration/parallel_executor.py apps/api/tests/unit/domains/agents/orchestration/test_parallel_executor_instruction_cap.py
git commit -m "feat(parallel_executor): cap delegate_to_sub_agent_tool.instruction post-resolution

After _resolve_step_references, if the resolved instruction of a
delegate_to_sub_agent_tool step exceeds SUBAGENT_INSTRUCTION_MAX_TOKENS_RESOLVED
(default 3000 tokens), the step fails with INVALID_INPUT and a clear
message pointing at the raw-payload \$ref anti-pattern.

Kills the 'inline \$steps.step_N.<emails-html>' bug at the only point
where the resolved size is actually known. No restriction on depends_on
or on smaller \$refs (e.g. \$steps.step_N.analysis chaining)."
```

---

## Task 8: LLM type label rename + i18n description

**Files:**
- Modify: `apps/api/src/domains/llm_config/constants.py:428-435` — `display_name` of `"subagent"`.
- Modify: `apps/web/locales/en/translation.json` — `settings.admin.llmConfig.types.subagent` description.
- Modify: `apps/web/locales/fr/translation.json` — idem.
- Modify: `apps/web/locales/de/translation.json` — idem.
- Modify: `apps/web/locales/es/translation.json` — idem.
- Modify: `apps/web/locales/it/translation.json` — idem.
- Modify: `apps/web/locales/zh/translation.json` — idem.
- Test: `apps/api/tests/unit/domains/llm_config/test_llm_types_registry.py` (extend if exists, otherwise create).

- [ ] **Step 1: Write the failing test**

Create or append to `apps/api/tests/unit/domains/llm_config/test_llm_types_registry.py`:

```python
"""Sub-agent LLM type label reflects its ReAct nature."""

import pytest


@pytest.mark.unit
def test_subagent_display_name_signals_react():
    from src.domains.llm_config.constants import LLM_TYPES_REGISTRY

    meta = LLM_TYPES_REGISTRY["subagent"]
    assert meta.display_name == "Sub-Agent (ReAct)"
    # The llm_type id MUST NOT change (DB/config compatibility).
    assert meta.llm_type == "subagent"
```

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/llm_config/test_llm_types_registry.py -v -k subagent`
Expected: FAIL (current `display_name == "Sub-Agent"`).

- [ ] **Step 2: Update the registry entry**

Edit `apps/api/src/domains/llm_config/constants.py`. Locate the `"subagent": LLMTypeMetadata(...)` entry (around line 428). Change:

Before:
```python
        display_name="Sub-Agent",
```

After:
```python
        display_name="Sub-Agent (ReAct)",
```

- [ ] **Step 3: Update the i18n description in the 6 locales**

For each of `en, fr, de, es, it, zh`:

- Open `apps/web/locales/<lang>/translation.json`.
- Find the key path `settings > admin > llmConfig > types > subagent`.
- Replace the value with a translation of: « Runs a scoped ReAct loop (read-only tools, tight iteration & token budget) for the principal assistant's expert delegations. »

Suggested values (review for tone consistency with neighbouring keys):
- **en**: `"Runs a scoped ReAct loop (read-only tools, tight iteration & token budget) for the principal assistant's expert delegations"`
- **fr**: `"Boucle ReAct cadrée (outils read-only, budget d'itérations et de tokens serré) pour les délégations expertes de l'assistant principal"`
- **de**: `"Eingegrenzte ReAct-Schleife (schreibgeschützte Tools, enges Iterations- und Token-Budget) für die expertenmäßigen Delegationen des Hauptassistenten"`
- **es**: `"Bucle ReAct acotado (herramientas de solo lectura, presupuesto ajustado de iteraciones y tokens) para las delegaciones expertas del asistente principal"`
- **it**: `"Loop ReAct circoscritto (strumenti read-only, budget di iterazioni e token contenuto) per le deleghe esperte dell'assistente principale"`
- **zh**: `"为主助手的专家委派运行受限的 ReAct 循环（只读工具，严格的迭代与 token 预算）"`

The i18n pre-commit hook enforces strict key parity vs `en`. No keys are added/removed here — only the values change. Parity remains intact.

- [ ] **Step 4: Run the registry test + the i18n parity script**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/llm_config/test_llm_types_registry.py -v -k subagent`
Expected: PASS.

If a frontend test exists for the locale files, run it too. Otherwise rely on the pre-commit hook (Task 8 Step 7).

- [ ] **Step 5: Lint backend**

Run: `cd apps/api && .venv/Scripts/ruff check src/domains/llm_config/constants.py && .venv/Scripts/mypy src/domains/llm_config/constants.py`
Expected: no errors.

- [ ] **Step 6: Verify frontend renders (Docker dev)**

Open the admin LLM Config panel in the dev frontend (the panel that lists all LLM types). Confirm the entry now reads « Sub-Agent (ReAct) » with the new description in your current UI language. Per CLAUDE.md « Never test locally » + memory `feedback_never_test_local`, this verification is done through the Docker dev container (`task dev:detach` if not running, then browse via the dev URL).

- [ ] **Step 7: Pre-commit hook regression**

Run: `task pre-commit` (host-side: black, ruff, mypy, fast tests, eslint, tsc, i18n parity).
Expected: all checks pass — especially the i18n parity check (no keys added/removed).

- [ ] **Step 8: Commit**

```bash
git add apps/api/src/domains/llm_config/constants.py apps/web/locales/en/translation.json apps/web/locales/fr/translation.json apps/web/locales/de/translation.json apps/web/locales/es/translation.json apps/web/locales/it/translation.json apps/web/locales/zh/translation.json apps/api/tests/unit/domains/llm_config/test_llm_types_registry.py
git commit -m "feat(llm_config): rename Sub-Agent label to 'Sub-Agent (ReAct)'

Display name only — the internal llm_type 'subagent' is unchanged (DB
rows, config overrides, code references all keep working). Description
updated in all 6 locales to reflect the scoped ReAct loop (read-only
tools, tight iteration & token budget) the type now drives."
```

---

## Task 9: Update the catalogue manifest

**Files:**
- Modify: `apps/api/src/domains/agents/sub_agents/catalogue_manifests.py` — update the description of `delegate_to_sub_agent_catalogue_manifest` and the `instruction` parameter description; lower the cost profile estimate to a realistic value.
- Test: update existing `apps/api/tests/unit/domains/sub_agents/test_sub_agent_tools.py::TestCatalogueManifest` if any assertions become stale (notably `test_tool_manifest_cost_profile`).

- [ ] **Step 1: Read the current manifest description and identify what to change**

Open `apps/api/src/domains/agents/sub_agents/catalogue_manifests.py`. The key elements:
- Top-level `_DESCRIPTION` constant (sub-agent's tool description in the catalogue).
- `ParameterSchema(name="instruction", ..., description="...")` — currently includes « Can reference results from previous steps via $steps.step_N.field. ».
- `CostProfile(est_tokens_in=2000, ...)` — already optimistic (was wildly off in practice).

- [ ] **Step 2: Update `_DESCRIPTION`**

Replace the existing `_DESCRIPTION` with:

```python
_DESCRIPTION = (
    "**Tool: delegate_to_sub_agent_tool** — "
    "Delegate a UNITARY expert task to an ephemeral specialized sub-agent (ReAct loop, read-only tools).\n"
    "**Use IFF**: an expert persona with a focused prompt would produce a "
    "MATERIALLY BETTER answer than the assistant handling the task directly "
    "(deep analysis, multi-source comparison, parallel research tracks via fan-out).\n"
    "**DO NOT USE for**: data fetching/summarization, simple lookups, CRUD, "
    "or single-tool tasks (do those yourself).\n"
    "**Output**: the sub-agent's analytical text in `analysis`."
)
```

- [ ] **Step 3: Update the `instruction` parameter description**

In the `parameters=[...]` list, replace the `instruction` `description` with:

```python
            description=(
                "Clear TASK STATEMENT for the sub-agent — what to analyze, what "
                "sources to use, what output format. DO NOT paste raw data; the "
                "sub-agent has its own read-only tools and fetches what it needs. "
                "May contain `$steps.step_N.analysis` for sub-agent → sub-agent "
                "chaining (short text). Never reference raw tool outputs "
                "(`$steps.step_N.<data>`) — the resolved instruction is hard-capped "
                "and oversized payloads are rejected."
            ),
```

- [ ] **Step 4: Lower the cost profile to realistic numbers**

Replace the `cost=CostProfile(...)` with:

```python
    cost=CostProfile(
        est_tokens_in=3000,
        est_tokens_out=2000,
        est_cost_usd=0.02,
        est_latency_ms=20000,
    ),
```

(The new path = ~recursion_limit×1 LLM call typical, instruction capped at ~3K tokens.)

- [ ] **Step 5: Update the cost-profile test if it asserts stale numbers**

Open `apps/api/tests/unit/domains/sub_agents/test_sub_agent_tools.py`. The `test_tool_manifest_cost_profile` likely checks `est_tokens_in == 2000` or similar. Update the expected values to match the new profile (3000 in, 2000 out, 0.02 usd, 20000 ms).

- [ ] **Step 6: Run manifest tests**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/sub_agents/test_sub_agent_tools.py::TestCatalogueManifest -v`
Expected: PASS.

- [ ] **Step 7: Lint + types**

Run: `cd apps/api && .venv/Scripts/ruff check src/domains/agents/sub_agents/catalogue_manifests.py && .venv/Scripts/mypy src/domains/agents/sub_agents/catalogue_manifests.py`
Expected: no errors.

- [ ] **Step 8: Commit**

```bash
git add apps/api/src/domains/agents/sub_agents/catalogue_manifests.py apps/api/tests/unit/domains/sub_agents/test_sub_agent_tools.py
git commit -m "feat(sub_agents): update delegate manifest description and cost profile

Reflect the new contract:
- Description: 'UNITARY expert task', 'IFF an expert persona would be
  materially better', do-not-use list.
- instruction param: explicit ban on raw \$ref payloads + reminder that
  sub-agent → sub-agent chaining via \$steps.X.analysis is OK.
- Cost profile: est_tokens_in 2000→3000 (realistic with capped
  instruction), est_tokens_out 4000→2000 (single ReAct loop, not 3 LLM
  calls), est_cost_usd 0.05→0.02, est_latency_ms 30000→20000."
```

---

## Task 10: Documentation — `SUB_AGENTS.md` rewrite + ADR-083

**Files:**
- Modify: `docs/technical/SUB_AGENTS.md` — rewrite the sections impacted (Architecture, Planner Integration, Token Tracking, V1 Known Limitations).
- Create: `docs/architecture/ADR-083-Sub-Agent-Delegation-React.md`.
- Modify: `docs/architecture/ADR_INDEX.md` — add ADR-083 entry.
- Modify: `docs/INDEX.md` — add a pointer to the new ADR.

- [ ] **Step 1: Rewrite `docs/technical/SUB_AGENTS.md` — Overview & Architecture**

Replace the « Overview » paragraph with one that distinguishes the two paths:

> Sub-agents now have TWO entry points: (A) **ephemeral delegation by the planner** (`delegate_to_sub_agent_tool`) — a scoped ReAct loop via `ReactSubAgentRunner` over read-only tools, with `recursion_limit = subagent_default_max_iterations` and a post-resolution token cap on `instruction`. This is the primary, supported usage. (B) **persistent user-defined sub-agents** (REST `/sub-agents`, templates, `POST /sub-agents/{id}/execute`) — runs on the legacy `SubAgentExecutor`. The frontend does not currently expose any UI for path (B); it is dormant and is a candidate for removal in a future cleanup.

Under « Planner Integration », update « How it works » to:

> 1. The planner sees `delegate_to_sub_agent_tool` in every filtered catalogue.
> 2. The planner prompt's `{sub_agents_section}` articulates the H1 decision test (« delegate IFF an expert persona is materially better »).
> 3. The `semantic_validator` runs `validate_sub_agent_delegation_justified` and vetoes pointless delegations (mono-domain, single delegate step, no fan-out) → `needs_replan=True` + `exclude_sub_agent_tools=True` → planner regenerates without delegation. Honors `SUBAGENT_VETO_POINTLESS_ENABLED` (default true).
> 4. At execution time, `parallel_executor` re-validates the **resolved** `instruction` against `SUBAGENT_INSTRUCTION_MAX_TOKENS_RESOLVED` (default 3000) → over-cap = step error.
> 5. The tool body invokes `ReactSubAgentRunner("subagent", "subagent_react_prompt").run(...)` — single scoped loop, read-only tools, tight `recursion_limit`. Token attribution flows into the parent tracker via `node_name_override`.

Under « Token Tracking », replace the section with:

> **Ephemeral path (planner)**: tokens flow into the parent `TokenTrackingCallback` automatically via the `metadata["node_name_override"] = "sub-agent: <expertise>"` mechanism (handled by `ReactSubAgentRunner`). No separate `MessageTokenSummary`, no manual consolidation. The per-execution cost cap is `recursion_limit × max_tokens_per_call` (≈ `subagent_default_max_iterations × 10000` by default).
>
> **Persistent path (`/sub-agents/{id}/execute`)**: unchanged — `SubAgentExecutor` writes a separate `MessageTokenSummary` keyed on the sub-agent session_id, and the daily Redis budget `subagent_max_total_tokens_per_day` still applies.

Under « V1 Known Limitations », keep #1 (« Token guard Level 2 not wired ») but add a note:

> Note: in the ephemeral planner-delegation path (post-refactor 2026-05-13), the per-execution cost is bounded by `recursion_limit` and the LLM's per-call `max_tokens` — the dedicated `SubAgentTokenGuard` callback is not necessary for that path. `SubAgentTokenGuard` remains dormant; it is a candidate for wiring on the persistent path if and when that path is kept.

Also add (anywhere it fits in the « Architecture » or a new « 2026-05-13 redesign » subsection):

> The HITL approval flow (`approval_gate_node`) is currently a passthrough (legacy from v1.14.5 « approval gate passthrough » — predates sub-agent delegation's manifest `hitl_required=True`). Re-activating HITL on delegated plans is out of scope of this redesign; it is gated by the rarity provided by H1 (no agacement) and would be revisited in a follow-up if needed.

- [ ] **Step 2: Create the ADR**

Create `docs/architecture/ADR-083-Sub-Agent-Delegation-React.md`:

```markdown
# ADR-083 — Sub-Agent Delegation as a Parameterized ReAct Loop

- **Status:** Accepted
- **Date:** 2026-05-13
- **Context incident:** 2026-05-12 — request `50855ec2-…` consumed 485 930 tokens
  (€0,56) for « résume mes 5 derniers emails de ma femme ». Root cause: a planner
  delegation to an ephemeral sub-agent re-ran a 3-LLM-call mini-pipeline over a
  ~114 K-token blob of raw email HTML that had been inlined via `$steps.step_1.…`
  reference resolution.

## Decision

The ephemeral planner-delegation path (`delegate_to_sub_agent_tool`) is rewired
onto the existing generic `ReactSubAgentRunner`. The bespoke `SubAgentExecutor`
mini-pipeline (`_analyze_instruction` → `SmartPlannerService.plan` →
`execute_plan_parallel` → `_synthesize_results`) is no longer used by the planner
path. (It remains in place for the persistent `/sub-agents/{id}/execute` path,
which is dormant and a candidate for removal — Phase 2.)

Three structural backstops complete the design:

1. **H1 — when to delegate**: `semantic_validator` adds a check
   `validate_sub_agent_delegation_justified` that vetoes plans where a single
   `delegate_to_sub_agent_tool` step is the only/main work on a mono-domain
   query with no fan-out. The veto triggers the existing F6 replan path
   (`needs_replan=True` + `exclude_sub_agent_tools=True`). Honors a kill-switch
   `SUBAGENT_VETO_POINTLESS_ENABLED` (default true).
2. **H2 — what reaches the sub-agent**: `parallel_executor._execute_tool_step`
   re-validates the resolved `instruction` of `delegate_to_sub_agent_tool` (after
   `$ref` expansion) against `SUBAGENT_INSTRUCTION_MAX_TOKENS_RESOLVED` (default
   3000 tokens). Over-cap → step fails with `INVALID_INPUT`. No restriction on
   `depends_on` or on chaining `$steps.X.analysis` (small text).
3. **H3 — what a sub-agent IS**: a single scoped ReAct loop, prompt
   `subagent_react_prompt` with a `{expertise}` slot, read-only toolset (the
   `resolve_tools_for_subagent` exclusion set is fixed to include
   `delegate_to_sub_agent_tool` itself — anti-recursion bug fix).

The `subagent` LLM type is preserved (config compatibility) and only its admin
display label is renamed « Sub-Agent (ReAct) » (mirroring `mcp_react_agent` =
« MCP Iterative (ReAct) »). The HITL approval flow remains passthrough — out
of scope.

## Consequences

**Positive**:
- The incident scenario (« résume mes emails ») is routed back to the main
  pipeline (`get_emails_tool` + `response_node`), ~12 K tokens.
- Any legitimate delegation that survives the H1 veto runs as a single bounded
  ReAct loop. Worst-case is bounded by `recursion_limit` (= `subagent_default_max_iterations`,
  default 5 — possibly bumped to 8-10 in a follow-up) × the LLM's per-call
  `max_tokens` (10 K) → a few tens of K tokens, not 450 K.
- The runtime path uses code already battle-tested by `browser_task_tool` and
  `mcp_server_task_tool` — less surface, fewer bugs.

**Negative / accepted**:
- Two execution paths coexist temporarily (`ReactSubAgentRunner` for ephemerals,
  `SubAgentExecutor` for the dormant persistent API). Tracked for Phase 2.
- The H1 veto is heuristic-based and may produce false positives. Mitigated by
  the kill-switch (`SUBAGENT_VETO_POINTLESS_ENABLED`) and a telemetry log
  (`semantic_validator_vetoed_sub_agent_delegation`) for observation.
- HITL on delegation remains broken (legacy passthrough). Acceptable because
  H1 makes delegations rare; revisit if/when needed.

## Related

- Spec: [`2026-05-13-sub-agent-delegation-redesign-design.md`](../superpowers/specs/2026-05-13-sub-agent-delegation-redesign-design.md)
- Plan: [`2026-05-13-sub-agent-delegation-redesign.md`](../superpowers/plans/2026-05-13-sub-agent-delegation-redesign.md)
- Prior: ADR-062 (Initiative Phase + MCP ReAct — origin of `ReactSubAgentRunner`),
  Phase F6 (Persistent Specialized Sub-Agents — origin of the now-dormant
  persistent API).
```

- [ ] **Step 3: Add the ADR entry to the index**

Open `docs/architecture/ADR_INDEX.md`. Add a line for ADR-083 following the existing format (alphabetical or chronological — match the file's pattern).

- [ ] **Step 4: Add a pointer in `docs/INDEX.md`**

Open `docs/INDEX.md`. Find where ADRs are listed (or where architectural decisions are surfaced). Add a one-liner pointing to ADR-083 with a short blurb.

- [ ] **Step 5: Run docs link/format checks if any**

Per CLAUDE.md, no specific docs linter is mandated. Skim the rendered markdown in VSCode preview to confirm formatting. If a docs lint task exists (`task docs:lint` or similar — check `Taskfile.yml`), run it.

- [ ] **Step 6: Commit**

```bash
git add docs/technical/SUB_AGENTS.md docs/architecture/ADR-083-Sub-Agent-Delegation-React.md docs/architecture/ADR_INDEX.md docs/INDEX.md
git commit -m "docs: ADR-083 + SUB_AGENTS.md update for the ReAct delegation redesign

ADR-083 captures the decision to rewire the ephemeral planner delegation
onto ReactSubAgentRunner, with H1 veto + H2 instruction cap as
structural backstops. SUB_AGENTS.md now distinguishes ephemeral (ReAct)
vs persistent (legacy SubAgentExecutor — dormant) paths and reflects the
new token tracking flow."
```

---

## Final validation

After all 10 tasks are committed:

- [ ] **Run the full unit test suite**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit -v -m unit -q`
Expected: all PASS.

- [ ] **Run the agent-specific tests**

Run: `task test:backend:agents`
Expected: all PASS.

- [ ] **Run `task pre-commit`**

Run: `task pre-commit`
Expected: format + lint + fast unit tests + i18n parity — all pass.

- [ ] **End-to-end smoke test in Docker dev**

1. `task dev:detach` (if not already running).
2. From the chat UI, send: « fais moi un résumé des 5 derniers emails ».
3. Observe the SSE / debug panel: the response must use `get_emails_tool` + `response_node`. No `subagent:` node in the token breakdown. Total tokens < 30 K.
4. Tail logs: `docker logs lia-api-dev | grep -E "semantic_validator_vetoed_sub_agent_delegation|subagent_instruction_oversized_after_resolution|sub-agent:"`. The veto event SHOULD appear; the cap event SHOULD NOT (because the veto prevents the delegation from being scheduled). If the user explicitly asks something multi-track expert-y (e.g., « analyse comparée des 3 derniers contrats que j'ai signés et signale les risques juridiques »), a legit delegation can fire; verify it stays under tens of K tokens.

If anything fails, do NOT advance to the next task or claim « done » — debug and fix at the root cause (CLAUDE.md « Never work around problems »).

---

## Self-review

Spec coverage:
- §4.1 (rewrite `delegate_to_sub_agent_tool`) → Task 4. ✓
- §4.2 (new prompt + PromptName) → Task 2. ✓
- §4.3.1 (planner prompt H1 wording) → Task 5. ✓
- §4.3.2 (`semantic_validator` veto + kill-switch) → Tasks 1 (settings) + 6 (logic). ✓
- §4.4 (`instruction` cap post-resolution) → Tasks 1 (settings) + 7 (logic). ✓
- §4.5 (no token guard callback in Phase 1) → not implemented (matches spec). ✓
- §4.6 (remove `timeout_seconds` from prompt) → covered by Task 5 (full rewrite of `_build_sub_agents_section`). ✓
- §4.7 (label rename + i18n) → Task 8. ✓
- §4.8 (`recursion_limit` from `subagent_default_max_iterations`) → Task 4 (used in the rewrite). ✓
- §5 (file inventory) → enumerated across tasks. ✓
- §5 « bug latent » (exclude `delegate_to_sub_agent_tool` from `resolve_tools_for_subagent`) → Task 3. ✓
- §5 manifest description update → Task 9. ✓
- §5 docs + ADR → Task 10. ✓
- §6 (Phase 1 does not touch `SubAgentExecutor` / persistent path) → respected throughout. ✓
- §8 (HITL out of scope) → respected. ✓
- §11 open points: cap value (3000), iteration default (5), veto conservatism, Phase 1/2 split — all reflected in defaults & spec; revisit in follow-up if observation shows issues.

Placeholder scan: no « TBD », « TODO », « implement appropriate X », « similar to Task N » without repeating the code. Every step shows the actual content.

Type consistency:
- `ReactSubAgentRunner("subagent", "subagent_react_prompt")` used consistently.
- `recursion_limit = settings.subagent_default_max_iterations` everywhere it appears.
- `SUBAGENT_INSTRUCTION_MAX_TOKENS_RESOLVED` (constant name) and `subagent_instruction_max_tokens_resolved` (settings field) match.
- `SemanticIssueType.POINTLESS_SUB_AGENT_DELEGATION` value used in both validator and node.

---

## Execution

**Plan complete and saved to `docs/superpowers/plans/2026-05-13-sub-agent-delegation-redesign.md`.** Two execution options:

**1. Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — execute tasks in this session via `executing-plans`, batch execution with checkpoints for review.

Which approach?
