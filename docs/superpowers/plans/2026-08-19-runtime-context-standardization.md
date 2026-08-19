# Runtime Context Standardization — Implementation Plan (Lots 0–2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace LIA's untyped `config["configurable"]` bag with a typed, validated `LiaRuntimeContext`, after first closing the CI gap that would let the migration break tools silently.

**Architecture:** Three lots, each independently shippable and revertible. Lot 0 adds the missing schema guard and records the Agent Server decision. Lot 1 removes proven-dead code and two rule violations. Lot 2 introduces the frozen context dataclass, parameterizes every tool signature *before* filling the context (a Pydantic-warning ordering proven by simulation), then flips the graph and the completeness assert in a single atomic commit.

**Tech Stack:** Python 3.12, LangGraph 1.2.11, LangChain 1.3.15, Pydantic 2.13, pytest, MyPy strict.

**Spec:** `docs/superpowers/specs/2026-08-19-runtime-context-standardization-design.md`

## Global Constraints

- **Backend only.** Verified: every `configurable` occurrence under `apps/web/` is a JavaScript property descriptor. No frontend, UX or responsive surface is touched by lots 0–2.
- **Ordering is not negotiable.** Simulation M: a non-`None` context under a bare `ToolRuntime` annotation emits a Pydantic serializer warning on *every* tool call. Parameterize signatures first, fill the context second.
- **Lot 2 steps 3 and 4 are ONE commit.** Simulation P3: a thread resumed after the schema switch but without a context succeeds silently with `runtime.context is None`.
- **File-size ratchet is shrink-only.** `services/orchestration/service.py` is frozen at 713 SLOC, `orchestration/parallel_executor.py` at 2174. New files must stay under 600 logical SLOC. Never raise a cap; run `task ratchet:update` after shrinking.
- **Coverage floor 66%**, shrink-only. Raise it after the work if measured coverage allows a ≥2-point margin.
- **Markers:** new tests live under `apps/api/tests/unit/`, carry `@pytest.mark.unit` (registered at runtime by `apps/api/tests/conftest.py:1206`), and no deselecting marker — this satisfies the F006 marker-coverage gate.
- **Documentation in English; ADRs in French** (30 of 31 recent ADRs are French).
- **No git actions.** Steps that say "commit" are recorded for the owner; the executor does not run git commands.
- **Reuse over reinvention:** the schema guard consumes `ensure_tools_loaded()` + `get_all_tools()` from `src/domains/agents/tools/tool_registry.py`, not a bespoke registry walk.

---

### Task 1: Tool-schema contract guard (Lot 0)

Closes F9. Today nothing in CI converts a tool to its LLM-facing schema, so an injected argument leaking to the model, or a tool becoming unconvertible, would ship unnoticed. Simulation G proved the failure mode is reachable: a bare `runtime: ToolRuntime | None = None` annotation makes `convert_to_openai_tool` raise.

**Files:**
- Create: `apps/api/tests/unit/domains/agents/tools/test_tool_schema_contract.py`

**Interfaces:**
- Consumes: `ensure_tools_loaded()`, `get_all_tools()` from `src.domains.agents.tools.tool_registry`.
- Produces: nothing importable. It is the regression oracle every later task runs.

- [ ] **Step 1: Write the failing test**

```python
"""Contract: every registered tool converts to an LLM-facing schema, and none leaks
an injected argument to the model.

Why this exists (audit F9): ``test_tool_registry_smoke`` imports and invokes every
tool, but never converts one to an OpenAI tool schema — and no other file in
``src/`` or ``tests/`` calls ``convert_to_openai_tool`` either. The three tests
using ``bind_tools`` pass through a fake model that ignores its ``tools`` argument.
So two failure modes were invisible to CI:

1. An injected argument (``runtime``, ``config``, ``state``, ``store``,
   ``tool_call_id``) surfacing in the schema sent to the model — wasted tokens and
   an invitation to hallucinate a value for it.
2. A tool that cannot be converted at all. Measured: a bare
   ``runtime: ToolRuntime | None = None`` annotation raises
   ``PydanticInvalidForJsonSchema`` because ``ToolRuntime`` carries a callable
   field, while ``Annotated[ToolRuntime | None, InjectedToolArg] = None`` is fine.
   Such a tool cannot be bound to any model.

This guard is also the non-regression oracle for the runtime-context migration,
which parameterizes 117 tool signatures.
"""

import warnings

import pytest
from langchain_core.utils.function_calling import convert_to_openai_tool

from src.domains.agents.tools.tool_registry import ensure_tools_loaded, get_all_tools

# Arguments the tool-execution layer injects. None may ever reach the model.
INJECTED_ARGUMENT_NAMES: frozenset[str] = frozenset(
    {"runtime", "config", "state", "store", "tool_call_id"}
)


@pytest.fixture(scope="module")
def registered_tools() -> dict:
    """Every auto-registered tool, loaded once for the module."""
    ensure_tools_loaded()
    tools = get_all_tools()
    assert tools, "the tool registry is empty — ensure_tools_loaded() did nothing"
    return tools


@pytest.mark.unit
def test_every_tool_converts_to_an_openai_schema(registered_tools: dict) -> None:
    """A tool that cannot be converted cannot be bound to any model."""
    failures: list[str] = []
    for name, tool in sorted(registered_tools.items()):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                convert_to_openai_tool(tool)
        except Exception as exc:  # noqa: BLE001 - we report every failure at once
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
    assert not failures, (
        "These tools cannot be converted to an OpenAI tool schema, so they cannot "
        "be bound to a model. A bare `runtime: ToolRuntime | None = None` is the "
        "known cause — use `Annotated[ToolRuntime | None, InjectedToolArg] = None`.\n"
        + "\n".join(failures)
    )


@pytest.mark.unit
def test_no_injected_argument_reaches_the_model(registered_tools: dict) -> None:
    """Injected arguments are runtime plumbing; the model must never see them."""
    leaks: list[str] = []
    for name, tool in sorted(registered_tools.items()):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            schema = convert_to_openai_tool(tool)
        properties = set((schema["function"].get("parameters") or {}).get("properties", {}))
        leaked = properties & INJECTED_ARGUMENT_NAMES
        if leaked:
            leaks.append(f"{name}: {sorted(leaked)}")
    assert not leaks, (
        "These tools expose injected arguments to the model. Annotate them with "
        "`InjectedToolArg`, or type the parameter `ToolRuntime` so the tool layer "
        "recognises and strips it.\n" + "\n".join(leaks)
    )


@pytest.mark.unit
def test_the_guard_actually_inspects_a_meaningful_number_of_tools(
    registered_tools: dict,
) -> None:
    """A guard that silently inspects nothing is worse than no guard.

    The floor is deliberately well below the measured count (105 on 2026-08-19) so
    that removing a tool family does not fail this test for the wrong reason, while
    a registry that fails to load still does.
    """
    assert len(registered_tools) >= 80, (
        f"only {len(registered_tools)} tools registered — the registry did not load "
        "properly, so the two contract tests above proved nothing"
    )
```

- [ ] **Step 2: Run the test to verify it passes against today's tree**

Run: `cd apps/api && .venv/Scripts/python -m pytest tests/unit/domains/agents/tools/test_tool_schema_contract.py -v --no-cov -p no:cacheprovider`
Expected: 3 PASSED. This guard is written green on purpose — it protects an invariant that currently holds (simulation H: 109 instances, 0 failures, 0 leaks). Its value is preventing Lot 2 from breaking it.

- [ ] **Step 3: Prove the guard actually bites**

Temporarily add this tool to the bottom of the test file, re-run, confirm both contract tests FAIL, then delete it:

```python
# TEMPORARY — mutation test, delete after observing the failure
from typing import Annotated  # noqa: E402
from langchain.tools import ToolRuntime  # noqa: E402
from langchain_core.tools import tool  # noqa: E402


@tool
async def _canary_unconvertible(x: str, runtime: ToolRuntime | None = None) -> str:
    """Canary."""
    return "x"


@tool
async def _canary_leaky(x: str, config: dict | None = None) -> str:
    """Canary."""
    return "x"


@pytest.mark.unit
def test_canary(registered_tools: dict) -> None:
    tools = {**registered_tools, "_canary_unconvertible": _canary_unconvertible,
             "_canary_leaky": _canary_leaky}
    test_every_tool_converts_to_an_openai_schema(tools)
    test_no_injected_argument_reaches_the_model(tools)
```

Run: `cd apps/api && .venv/Scripts/python -m pytest tests/unit/domains/agents/tools/test_tool_schema_contract.py::test_canary -v --no-cov -p no:cacheprovider`
Expected: FAIL, naming `_canary_unconvertible` (PydanticInvalidForJsonSchema). Then delete the canary block and re-run the file: 3 PASSED.

- [ ] **Step 4: Verify the marker gate**

Run: `cd apps/api && .venv/Scripts/python ../../scripts/audit/check_test_marker_coverage.py`
Expected: exit 0 — the new file is under `tests/unit/` with no deselecting marker, so it runs in the `unit` CI job.

- [ ] **Step 5: Verify the file-size ratchet**

Run: `cd apps/api && .venv/Scripts/python -m pytest tests/unit/test_file_size_ratchet_guard.py -q --no-cov -p no:cacheprovider`
Expected: PASSED.

- [ ] **Step 6: Commit** (owner action)

```
test(agents): garde de contrat sur le schéma d'outil exposé au LLM (F9)
```

---

### Task 2: ADR-231 and index (Lot 0)

Records the Agent Server NO-GO with its five blockers, the runtime-context GO, and — critically — the rejected findings, so no future session "fixes" a non-problem.

**Files:**
- Create: `docs/architecture/ADR-231-Contexte-Runtime-Type.md`
- Modify: `docs/architecture/ADR_INDEX.md` (append an entry after ADR-229)
- Modify: `CLAUDE.md` (the ADR count line under "Useful Documentation Pointers")

**Interfaces:**
- Consumes: the spec at `docs/superpowers/specs/2026-08-19-runtime-context-standardization-design.md`.
- Produces: the decision record every later task cites.

- [ ] **Step 1: Write the ADR**

French, matching the ADR-229 shape: `**Statut**`, `**Date**`, `**Décideurs**`, `## Contexte`, `## Décision`, `## Alternatives écartées`, `## Conséquences`. It must contain, at minimum:

- The five Agent Server blockers with their evidence (ELv2 versus AGPL-3.0; `0.13.0rc5` with no stable release; redundancy with `conversations`/`background_runner`/`scheduled_actions`; `langgraph_sdk.Auth` covering only five resources; 17 production services on a Raspberry Pi 5).
- The dev-only Studio variant and why it is also refused.
- The runtime-context GO, with the non-negotiable ordering and the reason (simulation M).
- A **« Ne pas corriger »** section listing every rejected finding from spec section 5, each with its refutation — in particular the planner's in-place `configurable["oauth_scopes"]` assignment, which is safe because LangGraph hands each node a fresh copy.
- Lot 3 (MCP exposure) recorded as deferred by owner decision, with its blocking constraint (F10: HITL lives in graph nodes, so a direct tool call bypasses every confirmation).

- [ ] **Step 2: Append the index entry**

Follow the ADR-229 entry shape in `docs/architecture/ADR_INDEX.md`: a `### ADR-231 : …` heading, a `**Fichier**:` line, and a `**Décision** :` paragraph.

- [ ] **Step 3: Update the ADR count in CLAUDE.md**

The line currently reads `ADR index (227 ADR files, ADR-229 latest — ADR-008 has no separate file; ADR-228 is reserved by a parallel workstream)`. Recount the files and update both the count and the "latest" marker to ADR-231, keeping the two existing parentheticals.

Run to recount: `ls docs/architecture/ADR-*.md | wc -l`

- [ ] **Step 4: Verify documentation drift**

Run: `task lint:docs`
Expected: exit 0, and LIVING broken links / stale code paths both 0.

- [ ] **Step 5: Commit** (owner action)

```
docs(adr): ADR-231 — Agent Server NO-GO, contexte runtime typé GO
```

---

### Task 3: Remove the unreachable legacy branches (Lot 1, F6)

`auto_save_context` has two branches that read `config.get("store")` while the value is written at `configurable["store"]` — the wrong nesting level, so they would always yield `None`. They are unreachable anyway: simulation Q inspected 105 tools and found exactly one without a `runtime` parameter (`local_query_engine_tool`, which carries no `@auto_save_context`) and **zero** with a `config` parameter.

The branches are not deleted blindly: their fail-safe intent ("never break the tool") is preserved by an explicit guard on the missing runtime.

**Files:**
- Modify: `apps/api/src/domains/agents/context/decorators.py:136-141` and `:266-282`
- Test: `apps/api/tests/unit/domains/agents/tools/test_decorators.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: no signature change. Behaviour is identical on every reachable path.

- [ ] **Step 1: Write the failing test**

Append to `apps/api/tests/unit/domains/agents/tools/test_decorators.py`:

```python
@pytest.mark.unit
async def test_auto_save_skips_loudly_when_no_runtime_is_injected() -> None:
    """A tool invoked without a ToolRuntime must skip auto-save, not crash.

    The pre-existing code fell back to ``config.get("store")`` — the wrong nesting
    level, since LIA writes the store at ``configurable["store"]`` — so the
    fallback could only ever yield None. It was also unreachable: no tool declares
    a ``config`` parameter. The replacement keeps the fail-safe contract with an
    explicit guard instead of a fallback that reads a key nobody writes.
    """
    from src.domains.agents.context.decorators import auto_save_context
    from src.domains.agents.tools.output import UnifiedToolOutput

    @auto_save_context("contacts")
    async def _tool_without_runtime() -> UnifiedToolOutput:
        return UnifiedToolOutput.action_success(message="ok")

    result = await _tool_without_runtime()

    assert isinstance(result, UnifiedToolOutput)
    assert result.success is True
```

- [ ] **Step 2: Run it to see the current behaviour**

Run: `cd apps/api && .venv/Scripts/python -m pytest tests/unit/domains/agents/tools/test_decorators.py -k no_runtime -v --no-cov -p no:cacheprovider`
Record whether it passes or fails today. It documents the contract either way; the point of the task is that it must still pass after the branches are replaced.

- [ ] **Step 3: Replace the first branch** (`decorators.py`, the `UnifiedToolOutput` path)

Replace:

```python
                    # Support ToolRuntime passed positionally or via kwarg
                    runtime = kwargs.get("runtime")
                    if not runtime:
                        from src.domains.agents.tools.runtime_helpers import ToolRuntime

                        runtime = next((arg for arg in args if isinstance(arg, ToolRuntime)), None)

                    if runtime:
                        config = runtime.config
                        store = runtime.store
                    else:
                        # Legacy: config + store passed explicitly
                        config = kwargs.get("config")
                        store = config.get("store") if config else None
```

with:

```python
                    # Support ToolRuntime passed positionally or via kwarg
                    runtime = kwargs.get("runtime")
                    if not runtime:
                        from src.domains.agents.tools.runtime_helpers import ToolRuntime

                        runtime = next((arg for arg in args if isinstance(arg, ToolRuntime)), None)

                    # No runtime means the tool was called outside the agent layer.
                    # The former fallback read ``config["store"]``, a level above
                    # where LIA writes it (``configurable["store"]``), so it could
                    # only ever yield None — and no tool declares a ``config``
                    # parameter, making the branch unreachable. Skipping is the
                    # honest behaviour, and auto-save must never break the tool.
                    if not runtime:
                        logger.warning(
                            "auto_save_skipped_missing_runtime",
                            context_type=context_type,
                            tool_name=func.__name__,
                        )
                        return tool_result

                    config = runtime.config
                    store = runtime.store
```

- [ ] **Step 4: Replace the second branch** (`decorators.py`, the JSON-string path)

Replace:

```python
                # Support both ToolRuntime (new) and config+store (legacy)
                runtime = kwargs.get("runtime")

                if runtime:
                    # ToolRuntime pattern (LangChain v1.0 new pattern)
                    config = runtime.config
                    store = runtime.store
                else:
                    # Legacy pattern (config + store separately)
                    config = kwargs.get("config")
                    if not config:
                        logger.warning(
                            "auto_save_skipped_missing_config_and_runtime",
                            context_type=context_type,
                            tool_name=func.__name__,
                        )
                        return result_json

                    # Extract store from config (injected by LangGraph)
                    store = config.get("store")
```

with:

```python
                # The ToolRuntime is the only supported injection path (see the
                # UnifiedToolOutput branch above for why the config+store fallback
                # was removed).
                runtime = kwargs.get("runtime")
                if not runtime:
                    logger.warning(
                        "auto_save_skipped_missing_runtime",
                        context_type=context_type,
                        tool_name=func.__name__,
                    )
                    return result_json

                config = runtime.config
                store = runtime.store
```

- [ ] **Step 5: Run the decorator tests and the schema guard**

Run: `cd apps/api && .venv/Scripts/python -m pytest tests/unit/domains/agents/tools/test_decorators.py tests/unit/domains/agents/tools/test_tool_schema_contract.py tests/unit/domains/agents/tools/test_tool_registry_smoke.py -v --no-cov -p no:cacheprovider`
Expected: all PASSED.

- [ ] **Step 6: Commit** (owner action)

```
refactor(agents): supprime la branche legacy morte d'auto_save_context (F6)
```

---

### Task 4: Canonical language and timezone fallbacks in the ReAct sub-runner (Lot 1, F7a)

`ReactSubAgentRunner` hardcodes `"fr"` and `"UTC"` where the canonical chokepoint uses `settings.default_language` and `DEFAULT_TIMEZONE`. CLAUDE.md forbids inline language literals "including fallbacks and parameter defaults", and requires constants to be centralized.

**Files:**
- Modify: `apps/api/src/domains/agents/tools/react_runner.py:274-275`
- Test: `apps/api/tests/unit/domains/agents/tools/test_react_runner_context.py` (create)

**Interfaces:**
- Consumes: `settings.default_language`, `src.core.constants.DEFAULT_TIMEZONE`.
- Produces: no signature change.

- [ ] **Step 1: Write the failing test**

```python
"""The ReAct sub-runner must not invent a language or a timezone.

CLAUDE.md forbids inline language literals anywhere in Python, fallbacks and
parameter defaults included, and requires defaults to come from settings or from
``core.constants``. The canonical chokepoint
(``services/orchestration/service.py``) already reads
``settings.default_language`` and ``DEFAULT_TIMEZONE``; this runner deviated with
``"fr"`` and ``"UTC"`` literals, so a sub-agent could answer in French to a German
user whenever the parent configurable lacked the key.
"""

import ast
from pathlib import Path

import pytest

RUNNER = Path("src/domains/agents/tools/react_runner.py")


@pytest.mark.unit
def test_no_hardcoded_language_or_timezone_literal_in_the_sub_runner() -> None:
    tree = ast.parse(RUNNER.read_text(encoding="utf-8"))
    forbidden = {"fr", "en", "de", "es", "it", "zh", "zh-CN", "UTC", "Europe/Paris"}
    offenders = [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value in forbidden
    ]
    assert not offenders, (
        "Hardcoded language/timezone literal(s) in the ReAct sub-runner: "
        f"{offenders}. Read settings.default_language and DEFAULT_TIMEZONE instead."
    )
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd apps/api && .venv/Scripts/python -m pytest tests/unit/domains/agents/tools/test_react_runner_context.py -v --no-cov -p no:cacheprovider`
Expected: FAIL, naming lines 274 and 275 with values `UTC` and `fr`.

- [ ] **Step 3: Apply the fix**

In `react_runner.py`, replace:

```python
                    "user_timezone": parent_configurable.get("user_timezone", "UTC"),
                    "user_language": parent_configurable.get("user_language", "fr"),
```

with:

```python
                    "user_timezone": parent_configurable.get(
                        "user_timezone", DEFAULT_TIMEZONE
                    ),
                    "user_language": parent_configurable.get(
                        "user_language", settings.default_language
                    ),
```

Add the imports at module level, in the existing stdlib → third-party → local order:

```python
from src.core.config import settings
from src.core.constants import DEFAULT_TIMEZONE
```

If `settings` or `DEFAULT_TIMEZONE` is already imported in this module, do not duplicate the import. Check first with:
`grep -n "^from src.core" src/domains/agents/tools/react_runner.py`

- [ ] **Step 4: Run the test and the sub-runner suite**

Run: `cd apps/api && .venv/Scripts/python -m pytest tests/unit/domains/agents/tools/test_react_runner_context.py -v --no-cov -p no:cacheprovider`
Expected: PASSED.

Run: `cd apps/api && .venv/Scripts/python -m pytest tests/ -k "react" -q --no-cov -p no:cacheprovider`
Expected: no new failures versus the baseline captured in Task 0 of the execution log.

- [ ] **Step 5: Commit** (owner action)

```
fix(agents): le sous-runner ReAct lit la langue et le fuseau canoniques (F7a)
```

---

### Task 5: Truthful comment on the retained context payload (Lot 1, F1)

Owner decision: `context=context_dict` is **kept** as the seed of Lot 2 rather than deleted. Until Lot 2 lands, its comment must not claim a behaviour the code does not have — CLAUDE.md treats a docstring describing behaviour the code lacks as a bug.

**Files:**
- Modify: `apps/api/src/domains/agents/services/orchestration/service.py:810`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing. Comment-only change.

- [ ] **Step 1: Apply the change**

Replace:

```python
        # Build context dict for ToolRuntime
```

with:

```python
        # Runtime context passed to graph.astream(context=...).
        #
        # It is NOT yet consumed: nothing reads runtime.context, and
        # ``_build_tool_runtime`` hard-codes ``context=None``, so no tool can see
        # it. Kept deliberately as the seed of the typed LiaRuntimeContext
        # migration (ADR-231); the previous comment claimed it fed ToolRuntime,
        # which was false.
```

- [ ] **Step 2: Verify nothing else asserts the old comment**

Run: `cd apps/api && grep -rn "Build context dict" src/ tests/`
Expected: no results.

- [ ] **Step 3: Run the orchestration tests**

Run: `cd apps/api && .venv/Scripts/python -m pytest tests/ -k "orchestration" -q --no-cov -p no:cacheprovider`
Expected: no new failures.

- [ ] **Step 4: Commit** (owner action)

```
docs(agents): le commentaire du contexte runtime dit ce que le code fait (F1)
```

---

### Task 6: Coupled dependency bump (Lot 1)

`langchain-openai` 1.5.2 requires `langchain-core>=1.5.6`: both or neither. Every transitive constraint was verified satisfied (openai 2.54.0 ⊂ `<4.0.0,>=2.45.0`; uuid-utils 0.14.1 ⊂ `<1.0,>=0.12.0`; tiktoken 0.13.0 ⊂ `<1.0.0,>=0.7.0`).

**Named risk:** `ChatDeepSeekPatched` overrides `BaseChatOpenAI._get_request_payload`, a **private** method owned by `langchain-openai`. The bump must be gated on the DeepSeek round-trip test, not only on `test_langchain_migration_compat`.

**Files:**
- Modify: `apps/api/requirements.txt:110` and `:113`
- Modify: `apps/api/requirements.lock.txt` (generated)

- [ ] **Step 1: Capture the DeepSeek baseline before touching anything**

Run: `cd apps/api && .venv/Scripts/python -m pytest tests/ -k "deepseek" -v --no-cov -p no:cacheprovider`
Record the result. If this is red before the bump, stop and report — the gate is meaningless otherwise.

- [ ] **Step 2: Edit both manifest lines together**

In `requirements.txt`, change `langchain-core==1.5.5` to `langchain-core==1.5.6` and `langchain-openai==1.5.1` to `langchain-openai==1.5.2`, preserving each trailing comment and appending the coupling reason:

```
langchain-core==1.5.6  # >=1.5.6 required by langchain-openai 1.5.2 (coupled bump)
```

- [ ] **Step 3: Regenerate the lockfiles**

Run: `task deps:lock`
Expected: `requirements.lock.txt` updated. Commit the manifest and the lock together — CI enforces it (ADR-112).

- [ ] **Step 4: Reinstall and run the three gates**

Run: `cd apps/api && .venv/Scripts/python -m pip install -r requirements.lock.txt --quiet`

Run: `cd apps/api && .venv/Scripts/python -m pytest tests/unit/test_langchain_migration_compat.py -v --no-cov -p no:cacheprovider`
Expected: 55 PASSED.

Run: `cd apps/api && .venv/Scripts/python -m pytest tests/ -k "deepseek" -v --no-cov -p no:cacheprovider`
Expected: same result as the Step 1 baseline.

Run: `cd apps/api && .venv/Scripts/python -m pytest tests/unit/domains/agents/tools/test_tool_schema_contract.py -v --no-cov -p no:cacheprovider`
Expected: 3 PASSED.

- [ ] **Step 5: Verify lockfile parity**

Run: `task lint:lockfiles`
Expected: exit 0.

- [ ] **Step 6: Commit** (owner action)

```
chore(deps): langchain-core 1.5.6 + langchain-openai 1.5.2 (montée couplée)
```

---

### Task 7: The `LiaRuntimeContext` contract (Lot 2, step 1)

A frozen dataclass in its own module. It carries the seventeen values the chokepoint builds today (verified by AST over `RunnableConfig(configurable={...})` at `service.py:757`), with two corrections baked in: `user_id` is a single canonical `uuid.UUID`, and the four private keys become named typed fields.

Simulation N proved LangGraph preserves object identity through node, subgraph and tool with no copy or serialization, so live dependencies (`asyncio.Queue`, the tool dependency container) are safe as fields. Simulation A4 proved the context is never checkpointed, so nothing that must survive a resume may live here.

**Files:**
- Create: `apps/api/src/domains/agents/context/runtime_context.py`
- Test: `apps/api/tests/unit/domains/agents/context/test_runtime_context.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `LiaRuntimeContext` (frozen dataclass), `assert_runtime_context(value: object) -> LiaRuntimeContext` used by Task 10's node assert, and `current_runtime_context() -> LiaRuntimeContext` (added in Task 10) used by both `ToolRuntime` construction sites.

- [ ] **Step 1: Write the failing test**

```python
"""Contract tests for the typed runtime context.

The context replaces an untyped 17-key ``config["configurable"]`` bag whose
``user_id`` arrived as a ``uuid.UUID`` from one writer and a ``str`` from another
— the ambiguity ``parse_user_id(str | UUID)`` exists to absorb. Freezing the
identity type here is the point of the migration, so it is tested first.
"""

import dataclasses
import uuid

import pytest

from src.domains.agents.context.runtime_context import (
    LiaRuntimeContext,
    assert_runtime_context,
)


@pytest.mark.unit
def test_context_is_frozen() -> None:
    ctx = LiaRuntimeContext(user_id=uuid.uuid4(), thread_id="t", conversation_id="c")
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.user_id = uuid.uuid4()  # type: ignore[misc]


@pytest.mark.unit
def test_user_id_is_a_uuid_not_a_string() -> None:
    uid = uuid.uuid4()
    ctx = LiaRuntimeContext(user_id=uid, thread_id="t", conversation_id="c")
    assert ctx.user_id == uid
    assert isinstance(ctx.user_id, uuid.UUID)


@pytest.mark.unit
def test_required_fields_have_no_default() -> None:
    """A context missing an identity must fail at construction, loudly."""
    with pytest.raises(TypeError):
        LiaRuntimeContext()  # type: ignore[call-arg]


@pytest.mark.unit
def test_assert_runtime_context_rejects_none() -> None:
    """Simulation B3: an absent context yields None silently. This is the net."""
    with pytest.raises(RuntimeError, match="runtime context"):
        assert_runtime_context(None)


@pytest.mark.unit
def test_assert_runtime_context_rejects_a_raw_dict() -> None:
    """The pre-migration shape was an untyped dict; it must not pass silently."""
    with pytest.raises(RuntimeError, match="runtime context"):
        assert_runtime_context({"user_id": "u"})


@pytest.mark.unit
def test_assert_runtime_context_returns_a_valid_context_unchanged() -> None:
    ctx = LiaRuntimeContext(user_id=uuid.uuid4(), thread_id="t", conversation_id="c")
    assert assert_runtime_context(ctx) is ctx


@pytest.mark.unit
def test_live_dependencies_keep_their_identity() -> None:
    """Simulation N: LangGraph does not copy the context, so live objects are safe."""
    import asyncio

    queue: asyncio.Queue = asyncio.Queue()
    ctx = LiaRuntimeContext(
        user_id=uuid.uuid4(), thread_id="t", conversation_id="c", side_channel_queue=queue
    )
    assert ctx.side_channel_queue is queue
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd apps/api && .venv/Scripts/python -m pytest tests/unit/domains/agents/context/test_runtime_context.py -v --no-cov -p no:cacheprovider`
Expected: FAIL with `ModuleNotFoundError: src.domains.agents.context.runtime_context`.

- [ ] **Step 3: Write the module**

Create `apps/api/src/domains/agents/context/runtime_context.py` with a module docstring explaining why the context exists and what may not live in it (nothing that must survive an interrupt resume — it is not checkpointed), then the frozen dataclass with the seventeen fields and the assert helper.

Field mapping, from `service.py:757` (left) to the dataclass (right):

| `configurable` key | field | type |
|---|---|---|
| `thread_id` | `thread_id` | `str` |
| `user_id` | `user_id` | `uuid.UUID` |
| `langgraph_user_id` | *(removed — duplicate of `user_id`)* | — |
| `store` | `store` | `BaseStore \| None` |
| `user_memory_enabled` | `memory_enabled` | `bool` |
| `user_journals_enabled` | `journals_enabled` | `bool` |
| `user_psyche_enabled` | `psyche_enabled` | `bool` |
| `user_display_mode` | `display_mode` | `str` |
| `user_execution_mode` | `execution_mode` | `str` |
| `is_automated_source` | `is_automated_source` | `bool` |
| `__deps` | `deps` | `ToolDependencies \| None` |
| `__browser_context` | `browser_context` | `dict[str, Any] \| None` |
| `__user_message` | `user_message` | `str` |
| `__side_channel_queue` | `side_channel_queue` | `asyncio.Queue \| None` |
| `user_timezone` | `timezone` | `str` |
| `user_language` | `language` | `str` |
| `user_display_name` | `display_name` | `str \| None` |
| *(added)* | `conversation_id` | `str` |

Required fields (no default): `user_id`, `thread_id`, `conversation_id`. Every other field carries a default consistent with today's chokepoint (`settings.default_language`, `DEFAULT_TIMEZONE`, `False` for the flags). Use `TYPE_CHECKING` imports for `BaseStore` and `ToolDependencies` to avoid an import cycle.

`assert_runtime_context` raises `RuntimeError` with a message naming the injection point to fix, following the ADR-085 doctrine: refuse to proceed rather than degrade.

- [ ] **Step 4: Run the tests**

Run: `cd apps/api && .venv/Scripts/python -m pytest tests/unit/domains/agents/context/test_runtime_context.py -v --no-cov -p no:cacheprovider`
Expected: 7 PASSED.

- [ ] **Step 5: Type-check and size-check**

Run: `cd apps/api && .venv/Scripts/mypy src/domains/agents/context/runtime_context.py`
Expected: no issues.

Run: `cd /d/Developpement/LIA && python scripts/audit/measure_sloc.py | grep runtime_context`
Expected: well under 600 SLOC, or absent from the listing (which only prints large files).

- [ ] **Step 6: Commit** (owner action)

```
feat(agents): contrat LiaRuntimeContext typé et gelé (ADR-231)
```

---

### Task 8: Parameterize the tool signatures (Lot 2, step 2)

The 117 `ToolRuntime` annotations become `ToolRuntime[LiaRuntimeContext, Any]`. **The context is still `None` at this point**, so this task changes no behaviour at all — simulation M1 proved the parameterized annotation with a `None` context emits no warning. It is a prerequisite: simulation M4 proved that filling the context under a bare annotation warns on every tool call.

**Files:**
- Modify: 35 files under `apps/api/src/domains/agents/tools/` (the 113 `Annotated[ToolRuntime, ...]` sites, the 4 `Annotated[ToolRuntime | None, ...]` sites) plus `apps/api/src/domains/agents/services/skill_location_context.py:71`
- Test: `apps/api/tests/unit/domains/agents/tools/test_tool_runtime_annotation_guard.py` (create)

**Interfaces:**
- Consumes: `LiaRuntimeContext` from Task 7.
- Produces: no signature change visible to callers; `runtime.context` becomes typed for MyPy.

- [ ] **Step 1: Write the failing guard**

```python
"""Every ToolRuntime annotation must be parameterized with LiaRuntimeContext.

Measured before the migration (simulation F): a non-None context under a BARE
``ToolRuntime`` annotation makes Pydantic emit
``PydanticSerializationUnexpectedValue`` on EVERY tool call, because the tool's
schema expects ``context: None``. Parameterizing removes the warning and gives
MyPy the real type. This guard makes the bare form fail CI so the two can never
drift apart again.
"""

import ast
from pathlib import Path

import pytest

ROOTS = (Path("src/domains/agents/tools"), Path("src/domains/agents/services"))


def _bare_tool_runtime_annotations() -> list[str]:
    """Yield 'file:line' for every unparameterized ToolRuntime annotation."""
    offenders: list[str] = []
    for root in ROOTS:
        for path in sorted(root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.arg) or node.annotation is None:
                    continue
                if _mentions_bare_tool_runtime(node.annotation):
                    offenders.append(f"{path.as_posix()}:{node.lineno}")
    return offenders


def _mentions_bare_tool_runtime(node: ast.expr) -> bool:
    """True when ToolRuntime appears without a subscript in this annotation."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Subscript):
            value = sub.value
            if isinstance(value, ast.Name) and value.id == "ToolRuntime":
                return False  # parameterized here
        if isinstance(sub, ast.Name) and sub.id == "ToolRuntime":
            parent_subscripted = any(
                isinstance(p, ast.Subscript)
                and isinstance(p.value, ast.Name)
                and p.value.id == "ToolRuntime"
                for p in ast.walk(node)
            )
            if not parent_subscripted:
                return True
    return False


@pytest.mark.unit
def test_no_bare_tool_runtime_annotation() -> None:
    offenders = _bare_tool_runtime_annotations()
    assert not offenders, (
        "Bare `ToolRuntime` annotation(s) found. Use "
        "`ToolRuntime[LiaRuntimeContext, Any]` — a bare annotation makes Pydantic "
        "warn on every tool call once the runtime context is populated.\n"
        + "\n".join(offenders)
    )
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd apps/api && .venv/Scripts/python -m pytest tests/unit/domains/agents/tools/test_tool_runtime_annotation_guard.py -v --no-cov -p no:cacheprovider`
Expected: FAIL listing roughly 117 offenders.

- [ ] **Step 3: Rewrite the annotations**

Apply mechanically, file by file, in this order (largest first so a mistake surfaces early): `emails_tools.py`, `google_contacts_tools.py`, `calendar_tools.py`, `routes_tools.py`, then the rest.

- `runtime: Annotated[ToolRuntime, InjectedToolArg]` → `runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg]`
- `runtime: Annotated[ToolRuntime | None, InjectedToolArg] = None` → `runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any] | None, InjectedToolArg] = None`
- `runtime: ToolRuntime` (bare parameter, not in `Annotated`) → `runtime: ToolRuntime[LiaRuntimeContext, Any]`
- `runtime: ToolRuntime | None` → `runtime: ToolRuntime[LiaRuntimeContext, Any] | None`

Each touched file gains, in the local import block:

```python
from src.domains.agents.context.runtime_context import LiaRuntimeContext
```

Watch for an import cycle: `runtime_context.py` must not import from `tools/`. Task 7's `TYPE_CHECKING` guard on `ToolDependencies` is what prevents it.

- [ ] **Step 4: Run the guard, the schema contract and the smoke test**

Run: `cd apps/api && .venv/Scripts/python -m pytest tests/unit/domains/agents/tools/test_tool_runtime_annotation_guard.py tests/unit/domains/agents/tools/test_tool_schema_contract.py tests/unit/domains/agents/tools/test_tool_registry_smoke.py -v --no-cov -p no:cacheprovider`
Expected: all PASSED. The schema contract passing is the proof that parameterizing changed nothing the model can see.

- [ ] **Step 5: Type-check and lint**

Run: `cd apps/api && .venv/Scripts/mypy src/domains/agents/tools/ src/domains/agents/services/skill_location_context.py`
Expected: no new errors versus the pre-task baseline.

Run: `task lint:backend`
Expected: exit 0.

- [ ] **Step 6: Full backend unit suite**

Run: `task test:backend:unit:fast`
Expected: no new failures. **No Pydantic serializer warning must appear** — simulation M1 says none should, since the context is still `None`.

- [ ] **Step 7: Commit** (owner action)

```
refactor(agents): paramètre les 117 annotations ToolRuntime (sans changement de comportement)
```

---

### Task 9: Build the context at the chokepoint (Lot 2, step 3a)

The context is constructed in exactly one place. Because `services/orchestration/service.py` is frozen at 713 SLOC and may only shrink, the construction lives in its own module and the service calls it.

**Files:**
- Create: `apps/api/src/domains/agents/context/runtime_context_builder.py`
- Modify: `apps/api/src/domains/agents/services/orchestration/service.py` (replace the `context_dict` literal with a call)
- Test: `apps/api/tests/unit/domains/agents/context/test_runtime_context_builder.py` (create)

**Interfaces:**
- Consumes: `LiaRuntimeContext` from Task 7.
- Produces: `build_runtime_context(...) -> LiaRuntimeContext`, consumed by Task 10.

- [ ] **Step 1: Write the failing test**

```python
"""The builder is the single source of the runtime context.

Every field must come from the same values the ``configurable`` bag receives at
``services/orchestration/service.py:757``, so the two planes cannot disagree
during the migration waves.
"""

import asyncio
import uuid

import pytest

from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.context.runtime_context_builder import build_runtime_context


@pytest.mark.unit
def test_builder_returns_a_typed_context_with_a_uuid_user_id() -> None:
    uid = uuid.uuid4()
    ctx = build_runtime_context(
        user_id=uid,
        conversation_id=uuid.uuid4(),
        user_language="de",
        user_timezone="Europe/Berlin",
    )
    assert isinstance(ctx, LiaRuntimeContext)
    assert ctx.user_id == uid
    assert isinstance(ctx.user_id, uuid.UUID)
    assert ctx.language == "de"
    assert ctx.timezone == "Europe/Berlin"


@pytest.mark.unit
def test_thread_id_mirrors_the_conversation_id() -> None:
    """LangGraph's thread_id IS the conversation id — the chokepoint sets both."""
    cid = uuid.uuid4()
    ctx = build_runtime_context(user_id=uuid.uuid4(), conversation_id=cid)
    assert ctx.thread_id == str(cid)
    assert ctx.conversation_id == str(cid)


@pytest.mark.unit
def test_live_dependencies_are_passed_by_reference_not_copied() -> None:
    queue: asyncio.Queue = asyncio.Queue()
    sentinel = object()
    ctx = build_runtime_context(
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        side_channel_queue=queue,
        deps=sentinel,
    )
    assert ctx.side_channel_queue is queue
    assert ctx.deps is sentinel


@pytest.mark.unit
def test_defaults_come_from_settings_not_from_literals() -> None:
    from src.core.config import settings
    from src.core.constants import DEFAULT_TIMEZONE

    ctx = build_runtime_context(user_id=uuid.uuid4(), conversation_id=uuid.uuid4())
    assert ctx.language == settings.default_language
    assert ctx.timezone == DEFAULT_TIMEZONE
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd apps/api && .venv/Scripts/python -m pytest tests/unit/domains/agents/context/test_runtime_context_builder.py -v --no-cov -p no:cacheprovider`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the builder, then call it from the service**

`build_runtime_context` takes the same values the `RunnableConfig(configurable={...})` literal receives, with `user_id: uuid.UUID` and `conversation_id: uuid.UUID` required and everything else keyword-optional. It returns a `LiaRuntimeContext`.

In `service.py`, replace the `context_dict` literal with:

```python
        runtime_context = build_runtime_context(
            user_id=user_id,
            conversation_id=conversation_id,
            user_language=user_language,
            user_timezone=user_timezone,
            display_mode=user_display_mode,
            execution_mode=user_execution_mode,
            memory_enabled=user_memory_enabled,
            journals_enabled=user_journals_enabled,
            psyche_enabled=user_psyche_enabled,
            is_automated_source=is_automated_source,
            display_name=state.get("user_display_name"),
            store=memory_store,
            deps=tool_deps,
            browser_context=browser_context,
            user_message=user_message,
            side_channel_queue=side_channel_queue,
        )
```

and pass `context=runtime_context` at both `graph.astream` call sites, replacing `context=context_dict`.

`configurable` is left **untouched** in this task: it remains the source of truth until the last migration wave.

- [ ] **Step 4: Run the builder tests and the orchestration suite**

Run: `cd apps/api && .venv/Scripts/python -m pytest tests/unit/domains/agents/context/ -v --no-cov -p no:cacheprovider`
Expected: all PASSED.

Run: `cd apps/api && .venv/Scripts/python -m pytest tests/ -k "orchestration or stream" -q --no-cov -p no:cacheprovider`
Expected: no new failures.

- [ ] **Step 5: Verify the ratchet did not move the wrong way**

Run: `cd /d/Developpement/LIA && python scripts/audit/measure_sloc.py | grep "orchestration.service.py"`
Expected: at or below 713. If the service grew, move more of the construction into the builder module until it does not.

Run: `cd apps/api && .venv/Scripts/python -m pytest tests/unit/test_file_size_ratchet_guard.py -q --no-cov -p no:cacheprovider`
Expected: PASSED.

- [ ] **Step 6: Commit** (owner action)

```
feat(agents): construit le contexte runtime typé au point unique (ADR-231)
```

---

### Task 10: Flip the graph and land the assert — one commit (Lot 2, step 3b + 4)

This is the single behavioural switch. Simulation P3 proved that a thread resumed after the switch but without a context succeeds **silently** with `runtime.context is None`, so the completeness assert must ship in the **same** commit. Simulation P2 proved a thread interrupted before the switch resumes cleanly after it; simulation P4 proved the rollback direction works too.

**Files:**
- Modify: `apps/api/src/domains/agents/graph.py:464` (declare `context_schema`)
- Modify: `apps/api/src/domains/agents/orchestration/parallel_executor.py:1968-1976` (fill `context=`)
- Modify: `apps/api/src/domains/agents/services/skill_location_context.py:71` (fill `context=`)
- Modify: the graph's first node, to call `assert_runtime_context`
- Test: `apps/api/tests/unit/domains/agents/context/test_runtime_context_switch.py` (create)

**Interfaces:**
- Consumes: `LiaRuntimeContext`, `assert_runtime_context`, `build_runtime_context`.
- Produces: `runtime.context` populated for every node, subgraph and tool.

- [ ] **Step 1: Write the failing tests**

```python
"""The behavioural switch: context_schema declared, context populated, absence loud.

Simulation P3 measured the trap this guards: with context_schema declared but no
context passed, a resumed run succeeds silently and every node reads None. The
assert turns that into a loud failure, and it must ship in the same commit as the
switch — never one deploy later.
"""

import uuid

import pytest

from src.domains.agents.context.runtime_context import (
    LiaRuntimeContext,
    assert_runtime_context,
)


@pytest.mark.unit
async def test_graph_declares_the_context_schema() -> None:
    from src.domains.agents.graph import build_graph

    graph, _store = await build_graph()
    assert graph.context_schema is LiaRuntimeContext


@pytest.mark.unit
async def test_graph_keeps_a_non_none_config_schema() -> None:
    """Simulation O: declaring context_schema must not change the public surface.

    ``tests/agents/test_graph_build.py`` asserts ``graph.config_schema is not None``.
    """
    from src.domains.agents.graph import build_graph

    graph, _store = await build_graph()
    assert graph.config_schema is not None


@pytest.mark.unit
async def test_tool_runtime_carries_the_context_from_inside_a_run() -> None:
    """``_build_tool_runtime`` hard-coded ``context=None``; it must not any more.

    It is exercised through a real graph run and an ``asyncio.gather`` fan-out,
    because that is where it actually executes — simulation R showed the ContextVar
    crosses that boundary, and a test that called it directly would prove nothing
    about the real call path.
    """
    import asyncio

    from langchain_core.runnables import RunnableConfig
    from langgraph.graph import END, START, StateGraph
    from typing_extensions import TypedDict

    from src.domains.agents.orchestration.parallel_executor import _build_tool_runtime

    class _St(TypedDict, total=False):
        out: str

    def _fake_tool_needing_runtime(runtime: object) -> None: ...

    class _Tool:
        name = "fake"
        func = _fake_tool_needing_runtime

    seen: dict = {}

    async def node(state: _St, config: RunnableConfig) -> _St:
        async def worker() -> None:
            seen["args"] = _build_tool_runtime(_Tool(), {}, config, store=None)

        await asyncio.gather(worker())
        return {}

    ctx = LiaRuntimeContext(user_id=uuid.uuid4(), thread_id="t", conversation_id="c")
    g = StateGraph(_St, context_schema=LiaRuntimeContext)
    g.add_node("n", node)
    g.add_edge(START, "n")
    g.add_edge("n", END)
    await g.compile().ainvoke(
        {}, config={"configurable": {"thread_id": "t"}}, context=ctx
    )

    assert seen["args"]["runtime"].context is ctx


@pytest.mark.unit
def test_current_runtime_context_raises_outside_a_run() -> None:
    """Simulation R: outside a graph run the read must fail loudly, not return None."""
    from src.domains.agents.context.runtime_context import current_runtime_context

    with pytest.raises(RuntimeError):
        current_runtime_context()


@pytest.mark.unit
def test_absent_context_fails_loudly() -> None:
    with pytest.raises(RuntimeError, match="runtime context"):
        assert_runtime_context(None)
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd apps/api && .venv/Scripts/python -m pytest tests/unit/domains/agents/context/test_runtime_context_switch.py -v --no-cov -p no:cacheprovider`
Expected: FAIL on the schema and the tool-runtime assertions.

- [ ] **Step 3: Declare the schema**

In `graph.py`, change `graph = StateGraph(MessagesState)` to
`graph = StateGraph(MessagesState, context_schema=LiaRuntimeContext)`.

- [ ] **Step 4: Propagate into `_build_tool_runtime`**

Simulation R settled how. `get_runtime()` reads a ContextVar, and that ContextVar
survives `asyncio.gather`, `asyncio.to_thread`, `asyncio.create_task`, and even a
fire-and-forget task awaited after the run returned. The parallel executor runs
inside a node, behind `asyncio.gather` — so it can read the context directly. **No
new `configurable` key is needed**, which matters: carrying run context in that bag
is precisely what this work removes.

Outside a graph run, `get_runtime()` raises
`RuntimeError: Called get_config outside of a runnable context` — loud, never
silent. That is the ADR-085 behaviour we want, so it is not caught here.

Add to `apps/api/src/domains/agents/context/runtime_context.py`:

```python
def current_runtime_context() -> LiaRuntimeContext:
    """Read the run-scoped context from anywhere inside a graph run.

    Backed by a ContextVar, so it crosses ``asyncio.gather``, ``to_thread`` and
    ``create_task`` — verified before relying on it, because the parallel executor
    reads it from inside a ``gather`` fan-out.

    Raises:
        RuntimeError: outside a graph run. Deliberately not caught: a missing
            context must fail loudly rather than degrade (ADR-085).
    """
    return get_runtime(LiaRuntimeContext).context
```

Then in `parallel_executor.py`:

```python
        runtime = ToolRuntime(
            state=None,  # Not available in worker context
            config=config,
            # The executor runs inside a node, behind asyncio.gather; the
            # run-scoped context crosses that boundary via its ContextVar.
            context=current_runtime_context(),
            store=store,  # Passed explicitly from execute_plan_parallel()
            stream_writer=NullStreamWriter(),  # Session 22: module-level NullStreamWriter
            tool_call_id=None,  # No tool call ID outside graph
        )
```

Update the surrounding comment, which currently claims `context: Not available in
worker context` — CLAUDE.md treats a docstring contradicting the code as a bug.

Apply the same change at `skill_location_context.py:71`. It is reached from
`response_node.py:1671`, i.e. from inside a graph node, so the same call is valid
there.

- [ ] **Step 5: Land the assert in the first node**

The first node reached by every run calls `assert_runtime_context(runtime.context)` before any other work, so a missing context fails at the entry rather than deep inside a tool.

- [ ] **Step 6: Run the switch tests, then the full agents suite**

Run: `cd apps/api && .venv/Scripts/python -m pytest tests/unit/domains/agents/context/ -v --no-cov -p no:cacheprovider`
Expected: all PASSED.

Run: `task test:backend:agents`
Expected: no new failures.

Run: `task test:backend:unit:fast`
Expected: no new failures, **and no Pydantic serializer warning** — Task 8 parameterized every annotation, so simulation M2 says none should appear.

- [ ] **Step 7: Commit** (owner action)

```
feat(agents): bascule le graphe sur LiaRuntimeContext + assert de complétude (ADR-231)
```

---

### Task 11: Migrate the reads, wave by wave (Lot 2, step 5)

43 files read `configurable`. Each wave replaces reads with `runtime.context` for one coherent group and is independently deployable, because `configurable` stays populated until the last wave.

**Files:**
- Create: `apps/api/tests/unit/domains/agents/context/test_configurable_reader_ratchet.py`
- Create: `apps/api/tests/unit/domains/agents/context/configurable_readers_allowlist.json`
- Modify: one wave per group, in this order:

1. `apps/api/src/domains/agents/tools/runtime_helpers.py` (`validate_runtime_config` — the chokepoint 117 tools go through)
2. `apps/api/src/domains/agents/tools/` (the remaining direct readers)
3. `apps/api/src/domains/agents/nodes/`
4. `apps/api/src/domains/agents/services/` and `apps/api/src/domains/agents/orchestration/`
5. `apps/api/src/domains/agents/context/` and everything left

**Interfaces:**
- Consumes: `LiaRuntimeContext` from Task 7.
- Produces: `langgraph_user_id` fully removed; `user_id` is a `uuid.UUID` everywhere inside the graph.

- [ ] **Step 1: Write the failing guard**

```python
"""No production code may read the runtime context out of ``configurable``.

The bag carried 17 keys across 43 files, with ``user_id`` arriving as a
``uuid.UUID`` from the chokepoint and a ``str`` from the parallel executor, plus a
``langgraph_user_id`` duplicate justified by a LangMem integration that is not
installed. This guard is the ratchet that keeps the migrated readers migrated.

The allowlist is SHRINK-ONLY: entries are removed as waves land, never added.
"""

import ast
import json
from pathlib import Path

import pytest

ALLOWLIST_PATH = Path("tests/unit/domains/agents/context/configurable_readers_allowlist.json")
MIGRATED_KEYS = frozenset({
    "user_id", "langgraph_user_id", "user_language", "user_timezone",
    "user_display_mode", "user_execution_mode", "user_memory_enabled",
    "user_journals_enabled", "user_psyche_enabled", "user_display_name",
    "is_automated_source", "__deps", "__browser_context", "__user_message",
    "__side_channel_queue", "store",
})


def _readers() -> dict[str, list[str]]:
    """Map file -> sorted migrated keys it still reads from configurable."""
    found: dict[str, set[str]] = {}
    for path in sorted(Path("src").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if "configurable" not in text:
            continue
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr == "get"):
                continue
            if not node.args or not isinstance(node.args[0], ast.Constant):
                continue
            key = node.args[0].value
            if key in MIGRATED_KEYS and "configurable" in ast.dump(func.value):
                found.setdefault(path.as_posix(), set()).add(key)
    return {k: sorted(v) for k, v in found.items()}


@pytest.mark.unit
def test_no_unallowlisted_configurable_reader() -> None:
    allowed = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))["files"]
    actual = _readers()
    new = {f: keys for f, keys in actual.items() if f not in allowed}
    assert not new, (
        "New reader(s) of the runtime context via `configurable`. Read "
        "`runtime.context` instead.\n" + json.dumps(new, indent=2)
    )


@pytest.mark.unit
def test_allowlist_has_no_stale_entry() -> None:
    """Shrink-only: a migrated file must be removed from the allowlist."""
    allowed = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))["files"]
    actual = _readers()
    stale = sorted(set(allowed) - set(actual))
    assert not stale, (
        "These files no longer read the context from `configurable` — remove them "
        f"from the allowlist:\n{stale}"
    )
```

- [ ] **Step 2: Seed the allowlist from the current tree**

Run:
```
cd apps/api && .venv/Scripts/python -c "import json,sys; sys.path.insert(0,'tests/unit/domains/agents/context'); from test_configurable_reader_ratchet import _readers; json.dump({'_doc':'Shrink-only ratchet: files still reading the runtime context out of configurable. Entries are REMOVED as migration waves land, never added. Doctrine: ADR-231.','files':sorted(_readers())}, open('tests/unit/domains/agents/context/configurable_readers_allowlist.json','w'), indent=1)"
```

- [ ] **Step 3: Run the guard**

Run: `cd apps/api && .venv/Scripts/python -m pytest tests/unit/domains/agents/context/test_configurable_reader_ratchet.py -v --no-cov -p no:cacheprovider`
Expected: 2 PASSED.

- [ ] **Step 4: Migrate wave 1 — `validate_runtime_config`**

Rewrite it to read `runtime.context` and return a `ValidatedRuntimeConfig` whose `user_id` is a `uuid.UUID`. Keep the structured `configuration_error` return for a missing context: this helper runs inside tools, where raising would surface as an unhandled programming error rather than a tool error.

Then remove the file from the allowlist and re-run the guard; `test_allowlist_has_no_stale_entry` proves the wave actually landed.

- [ ] **Step 5: Run the affected suites after each wave**

Run: `task test:backend:unit:fast`
Run: `task test:backend:agents`
Expected after every wave: no new failures.

- [ ] **Step 6: Repeat steps 4–5 for waves 2 to 5**

After the last wave the allowlist contains only files that legitimately read non-migrated keys (`thread_id`, `run_id`, `node_name`, `turn_id`, `oauth_scopes`, `resolved_person_names`, `__parent_thread_id`). Those stay in `configurable`: they are LangGraph plumbing or node-local, not run context.

- [ ] **Step 7: Remove `langgraph_user_id` from the chokepoint**

Once no file reads it, delete the key from the `RunnableConfig(configurable={...})` literal and delete its stale LangMem comment.

Run: `cd apps/api && grep -rn "langgraph_user_id" src/ tests/`
Expected: no results.

- [ ] **Step 8: Commit per wave** (owner action)

```
refactor(agents): vague N — lit le contexte typé au lieu de configurable (ADR-231)
```

---

### Task 12: The sub-runner derives its context (Lot 2, step 6, F7b)

`ReactSubAgentRunner` re-projects the parent context by hand, writing 7 keys of which only 6 are inherited from the parent's 17. Latent today — the default whitelist is `perplexity_search_tool,brave_search_tool,fetch_web_page_tool`, none of which reads the 11 dropped keys — but the whitelist is `.env`-configurable, so adding a location-aware tool would silently degrade geolocation. Deriving removes the bug class instead of adding eleven keys.

**Files:**
- Modify: `apps/api/src/domains/agents/tools/react_runner.py:267-280`
- Test: `apps/api/tests/unit/domains/agents/tools/test_react_runner_context.py` (extend Task 4's file)

**Interfaces:**
- Consumes: `LiaRuntimeContext` from Task 7.
- Produces: a sub-run context that cannot silently lose a field.

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.unit
def test_sub_runner_context_inherits_every_parent_field() -> None:
    """Deriving beats re-projecting: a new field must not need a code change here.

    The hand-written projection kept 6 of the parent's 17 keys. Any field added to
    LiaRuntimeContext later would have been silently dropped for every sub-agent.
    """
    import dataclasses
    import uuid

    from src.domains.agents.context.runtime_context import LiaRuntimeContext
    from src.domains.agents.tools.react_runner import derive_sub_agent_context

    parent = LiaRuntimeContext(
        user_id=uuid.uuid4(),
        thread_id="parent-thread",
        conversation_id="conv",
        language="de",
        timezone="Europe/Berlin",
        browser_context={"lat": 1.0, "lon": 2.0},
        user_message="original",
        display_name="Alice",
    )

    child = derive_sub_agent_context(parent, thread_id="react_sub")

    assert child.thread_id == "react_sub"
    for field in dataclasses.fields(LiaRuntimeContext):
        if field.name == "thread_id":
            continue
        assert getattr(child, field.name) == getattr(parent, field.name), (
            f"field {field.name!r} was lost when deriving the sub-agent context"
        )
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd apps/api && .venv/Scripts/python -m pytest tests/unit/domains/agents/tools/test_react_runner_context.py -v --no-cov -p no:cacheprovider`
Expected: FAIL with `ImportError: cannot import name 'derive_sub_agent_context'`.

- [ ] **Step 3: Implement the derivation**

```python
def derive_sub_agent_context(
    parent: LiaRuntimeContext, *, thread_id: str
) -> LiaRuntimeContext:
    """Derive a sub-agent context from its parent, changing only the thread.

    Replaces a hand-written projection that kept 6 of 17 fields: any field added
    to ``LiaRuntimeContext`` was silently dropped for every sub-agent. Deriving
    makes the default "inherit", so a new field is carried without touching this
    function.
    """
    return dataclasses.replace(parent, thread_id=thread_id)
```

Use it in `_run`, keeping `__parent_thread_id` in `configurable` (it is thread plumbing, not run context, and `browser_tools.py:122` reads it deliberately).

- [ ] **Step 4: Run the tests**

Run: `cd apps/api && .venv/Scripts/python -m pytest tests/unit/domains/agents/tools/test_react_runner_context.py -v --no-cov -p no:cacheprovider`
Expected: all PASSED.

Run: `cd apps/api && .venv/Scripts/python -m pytest tests/ -k "react or sub_agent" -q --no-cov -p no:cacheprovider`
Expected: no new failures.

- [ ] **Step 5: Commit** (owner action)

```
fix(agents): le sous-runner ReAct dérive son contexte au lieu de le reprojeter (F7b)
```

---

### Task 13: Full verification and ratchets

**Files:**
- Modify: `apps/api/tests/unit/file_size_baseline.json` (only if a frozen file shrank)
- Modify: `apps/api/pyproject.toml` (coverage floor, only if the measured margin allows)

- [ ] **Step 1: Run every static gate**

Run: `task lint`
Expected: exit 0.

- [ ] **Step 2: Run the full backend unit suite with coverage**

Run: `task test:backend:unit:coverage`
Expected: pass, coverage at or above 66%. Record the measured figure.

- [ ] **Step 3: Run the agents suite**

Run: `task test:backend:agents`
Expected: no failures.

- [ ] **Step 4: Run every service-free CI gate**

Run: `task ci:fast`
Expected: exit 0. This is the acceptance gate for the whole programme — a targeted run is not acceptable evidence.

- [ ] **Step 5: Lower the file-size ratchet if anything shrank**

Run: `task ratchet:update`
Then inspect the diff on `apps/api/tests/unit/file_size_baseline.json`: caps may only go **down**. If any cap rose, revert and fix the file instead.

- [ ] **Step 6: Raise the coverage floor if the margin allows**

If the figure from Step 2 exceeds 68%, raise `--cov-fail-under` in `apps/api/pyproject.toml:239` to `measured - 2`, rounded down. Never raise it closer than two points to the measured value.

Run: `task test:backend:unit:coverage`
Expected: still passes at the new floor.

- [ ] **Step 7: Update the documentation**

- `docs/INDEX.md`: add ADR-231 if the index lists ADRs individually.
- `docs/ARCHITECTURE_AGENT.md` and `docs/ARCHITECTURE_LANGRAPH.md`: describe the runtime context as the typed run-scoped plane, and `configurable` as LangGraph plumbing only.
- `docs/guides/GUIDE_TOOL_CREATION.md`: a new tool annotates `runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg]` and reads `runtime.context`, never `config["configurable"]`.

Run: `task lint:docs`
Expected: exit 0.

- [ ] **Step 8: Commit** (owner action)

```
chore(agents): ratchets et documentation après la standardisation du contexte (ADR-231)
```
