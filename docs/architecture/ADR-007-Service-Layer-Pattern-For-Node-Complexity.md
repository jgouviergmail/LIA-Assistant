# ADR-007: Service Layer Pattern for Node Complexity Reduction

**Status**: ✅ Accepted and Implemented - SUPERSEDED by Architecture v3
**Date**: 2025-11-16
**Authors**: Claude Code (Sonnet 4.5)
**Related Sessions**: 16, 17, 18 (+ Continuation)

> **Note Architecture v3 (2026-01)**: Les fichiers `planner_node.py` et `router_node.py` references dans cet ADR ont ete remplaces par `planner_node_v3.py` et `router_node_v3.py`.
> L'architecture v3 a pousse plus loin le pattern Service Layer avec les Smart Services :
> - `QueryAnalyzerService` (analyse intent + routing)
> - `SmartPlannerService` (planning single-call)
> - `SmartCatalogueService` (filtrage catalogue)
> Voir [SMART_SERVICES.md](../technical/SMART_SERVICES.md) pour la documentation actuelle.

---

## Context

### Problem Statement

During code quality analysis (Sessions 14-16), we identified critical complexity issues in LangGraph nodes:

| Node | Lines | Cyclomatic Complexity | Status |
|------|-------|----------------------|--------|
| `planner_node()` | 804 | CC 56 | **CRITICAL** |
| `step_executor_node()` | 657 | CC 35 | **HIGH** |
| `hitl_orchestrator` | 456 | CC 25 | **MEDIUM** |
| `parallel_executor` | 402 | CC 22 | **MEDIUM** |

**Key Issues**:
1. **Monolithic functions**: 800+ lines with embedded business logic
2. **High cognitive load**: CC 56 (5.6x over threshold of 10)
3. **Difficult to test**: Tightly coupled logic
4. **Low maintainability**: Changes require understanding 800+ lines
5. **Poor separation of concerns**: Retry loops, validation, error handling all mixed

### Analysis Results

**planner_node() breakdown** (Session 16):
- **Lines 1-100**: Initialization & setup
- **Lines 100-200**: Input preparation (windowing, catalogue loading, context)
- **Lines 200-600**: **Retry loop orchestration** (300+ lines)
  - LLM invocation with retries
  - JSON parsing
  - Pydantic validation
  - Plan validation
  - Retry feedback generation
  - Metrics tracking
- **Lines 600-800**: Response building & error handling

**Root cause**: Business logic (retry orchestration, plan generation) embedded directly in node function instead of being delegated to dedicated services.

---

## Decision

We adopt a **Service Layer Pattern** for complex LangGraph nodes, combined with helper function extraction.

### Core Principles

1. **Nodes = Thin Orchestrators**
   - Nodes should only coordinate flow, not implement business logic
   - Target: <100 lines per node function
   - Target: CC <10 per node function

2. **Service Layer = Business Logic**
   - Extract complex business logic into dedicated service classes
   - Services are stateless (all state passed via parameters)
   - Services return results via clear interfaces (tuples, DTOs)

3. **Helper Functions = Single Responsibility**
   - Extract utility functions for specific concerns (windowing, formatting, etc.)
   - Helpers are pure functions when possible
   - Helpers are independently testable

### Architecture Layers

```
┌─────────────────────────────────────────────────────────────┐
│                     LangGraph Node                          │
│  (Thin Orchestrator, <100 lines, CC <10)                    │
│                                                              │
│  - Initialize (settings, run_id, logging)                   │
│  - Prepare inputs (via helpers)                             │
│  - Delegate to service                                      │
│  - Format response (via helpers)                            │
│  - Handle exceptions (via helpers)                          │
└─────────────────────────────────────────────────────────────┘
                            ↓
        ┌───────────────────┴───────────────────┐
        ↓                                       ↓
┌──────────────────┐                   ┌─────────────────────┐
│  Helper Functions│                   │  Service Classes    │
│  (Utilities)     │                   │  (Business Logic)   │
│                  │                   │                     │
│  - Windowing     │                   │  - PlannerService   │
│  - Formatting    │                   │    • generate_plan()│
│  - Validation    │                   │    • retry loop     │
│  - Error         │                   │    • parsing        │
│    building      │                   │    • validation     │
└──────────────────┘                   └─────────────────────┘
```

---

## Implementation

### Phase 1: Helper Function Extraction (Session 17)

**Target**: Extract 7 helpers from planner_node()

**Results**:
- ✅ 6 helpers extracted (2h)
- ✅ -96 lines from function (-11.9%)
- ✅ CC reduced from 56 → ~46
- ⏸️ Helper #7 deferred to Phase 2 (too complex)

**Key Helpers**:
1. `_extract_user_query()` - Query extraction with validation
2. `_apply_message_windowing()` - Performance optimization
3. `_load_and_format_context()` - Async context loading (**54 lines saved**)
4. `_build_llm_config()` - LLM configuration assembly
5. `_format_planner_error()` - DRY error formatting
6. `_build_planning_prompt()` - Prompt construction

### Phase 2: Service Layer Creation (Session 18)

**Target**: Create PlannerService to extract retry loop (500+ lines)

**Implementation**:

```python
# apps/api/src/domains/agents/services/planner_service.py
class PlannerService:
    """Service for execution plan generation and validation."""

    def __init__(self, registry: AgentRegistry, settings: Settings):
        self.registry = registry
        self.settings = settings
        self.validator = PlanValidator(registry=registry)

    async def generate_plan(
        self,
        user_query: str,
        messages: list[BaseMessage],
        catalogue: dict,
        context_section: str,
        config: RunnableConfig,
        run_id: str,
        user_oauth_scopes: list[str],
    ) -> tuple[ExecutionPlan | None, ValidationResult | None]:
        """
        Generate and validate execution plan with retry loop.

        Returns tuple to make all possible outcomes explicit:
        - (ExecutionPlan, ValidationResult) = Success
        - (ExecutionPlan, ValidationResult with errors) = Validation failed
        - (None, None) = Parsing failed
        """
        # 1. Build prompt
        # 2. Get LLM instance
        # 3. Build LLM config
        # 4. Execute retry loop (lines 154-352)
        # 5. Return results
```

**Results**:
- ✅ PlannerService created (554 lines)
- ✅ -316 lines from function (-44.6%)
- ✅ CC reduced from ~46 → ~20
- ✅ planner_node(): 708 → 392 lines

### Session 18 Continuation: Final Extraction (76 Lines!)

**Target**: Reach <100 lines target

**Additional Helpers**:
9. `_build_success_response()` - Success path response building (100 lines)
10. `_build_validation_failed_response()` + `_build_parsing_failed_response()` - Error responses (91 lines)
11. `_prepare_planner_inputs()` - Input preparation orchestration (52 lines)

**Optimizations**:
- Docstring shortened (59 → 20 lines)
- Comments optimized (~30 lines removed)

**Final Results**:
- ✅ **planner_node(): 76 lines** (from 804, **-90.5%**)
- ✅ **CC: ~8** (from 56, **-85.7%**)
- ✅ **11 helpers + 1 service**
- ✅ **Zero regressions** (38/38 tests passing)

---

## Design Patterns

### 1. Stateless Services

**Pattern**: Services don't maintain request-scoped state

```python
# ❌ BAD: Stateful service
class PlannerService:
    def __init__(self, user_query, messages, ...):
        self.user_query = user_query  # Request state!
        self.messages = messages

    async def generate_plan(self):
        # Uses instance variables
        pass

# ✅ GOOD: Stateless service
class PlannerService:
    def __init__(self, registry, settings):
        self.registry = registry  # Configuration only
        self.settings = settings

    async def generate_plan(self, user_query, messages, ...):
        # All request state via parameters
        pass
```

**Benefits**:
- Thread-safe
- Easier to test (no hidden state)
- Can be singleton/cached
- Clear dependencies

### 2. Tuple Returns for Multiple Outcomes

**Pattern**: Return tuples to make all outcomes explicit

```python
# ✅ GOOD: Explicit outcomes via tuple
async def generate_plan(...) -> tuple[ExecutionPlan | None, ValidationResult | None]:
    """
    Returns:
        (ExecutionPlan, ValidationResult): Success
        (ExecutionPlan, ValidationResult with errors): Validation failed
        (None, None): Parsing failed
    """
    # Caller can pattern match on outcomes
```

**Benefits**:
- No hidden states
- Explicit error handling
- Type-safe
- Better than exceptions for expected failures

### 3. Helper Function Naming Convention

**Pattern**: Prefix with `_` for module-private helpers

```python
# Helper functions (module-private)
def _extract_user_query(messages: list[BaseMessage]) -> str:
    """Extract last user message."""
    pass

def _build_success_response(plan, result, run_id) -> dict:
    """Build success response."""
    pass

# Node function (public)
async def planner_node(state, config) -> dict:
    """Public node entry point."""
    pass
```

**Benefits**:
- Clear visibility (public vs private)
- Prevents accidental imports
- Signals intent (helper vs API)

### 4. Service Method Organization

**Pattern**: One public method + private helpers

```python
class PlannerService:
    # Public API (one main method)
    async def generate_plan(...) -> tuple[...]:
        """Main entry point."""
        prompt = self._build_prompt(...)
        plan = await self._invoke_llm_with_retry(...)
        return plan

    # Private helpers
    def _build_prompt(...):
        pass

    def _parse_response(...):
        pass

    def _validate_plan(...):
        pass
```

**Benefits**:
- Single entry point
- Internal complexity hidden
- Easy to understand API

---

## Consequences

### Positive

1. **Maintainability** ✅
   - planner_node(): 804 → 76 lines (-90.5%)
   - CC: 56 → 8 (-85.7%)
   - Much easier to understand and modify

2. **Testability** ✅
   - Service methods independently testable
   - Helper functions pure and testable
   - Can mock service for node tests

3. **Reusability** ✅
   - Service can be used outside LangGraph
   - Helpers can be reused across nodes
   - Clear interfaces promote reuse

4. **Separation of Concerns** ✅
   - Node = orchestration
   - Service = business logic
   - Helpers = utilities
   - Clear boundaries

5. **Incremental Refactoring** ✅
   - Can extract helpers first (low risk)
   - Then create service (medium risk)
   - Zero regressions at each step

### Negative

1. **More Files** ⚠️
   - Before: 1 file (planner_node.py)
   - After: 2 files (planner_node.py + planner_service.py)
   - **Mitigation**: Better organization, clear responsibilities

2. **Indirection** ⚠️
   - One more layer to navigate
   - **Mitigation**: Clear naming, good documentation, IDE navigation

3. **Test Coverage Gap** ⚠️
   - New service/helpers not yet fully tested
   - **Mitigation**: Add unit tests in follow-up session

### Neutral

1. **File Size**
   - planner_node.py: 1,020 → 850 lines (+helper definitions)
   - planner_service.py: 0 → 554 lines (new)
   - **Total**: Slight increase, but much better organized

---

## Metrics

### Before (Session 16)

| Metric | Value | Status |
|--------|-------|--------|
| planner_node() lines | 804 | ❌ CRITICAL |
| Cyclomatic Complexity | 56 | ❌ 5.6x over threshold |
| Helper functions | 0 | ❌ None |
| Service classes | 0 | ❌ None |
| Testability | Low | ❌ Monolithic |

### After (Session 18 + Continuation)

| Metric | Value | Status |
|--------|-------|--------|
| planner_node() lines | **76** | ✅ **-90.5%** |
| Cyclomatic Complexity | **8** | ✅ Within threshold |
| Helper functions | **11** | ✅ Testable units |
| Service classes | **1 (554 lines)** | ✅ Isolated logic |
| Testability | High | ✅ Independently testable |

### Test Safety

- ✅ **38/38 planner tests passing**
- ✅ **Zero regressions** introduced
- ✅ **Production-ready**

---

## Guidelines for Future Refactoring

### When to Create a Service

Create a service class when:
1. **Complexity**: Business logic > 200 lines
2. **Retry loops**: Complex retry orchestration
3. **State management**: Multi-step workflows with state
4. **Reusability**: Logic could be used outside node context

### When to Create a Helper

Create a helper function when:
1. **Single responsibility**: Clear, focused purpose
2. **Reusability**: Used multiple times or could be
3. **Testability**: Pure logic that can be tested independently
4. **Readability**: Extraction improves main function clarity

### Naming Conventions

**Services**:
- `{Domain}Service` (e.g., PlannerService, ExecutorService)
- Located in `src/domains/agents/services/`

**Helpers**:
- `_verb_noun()` (e.g., `_extract_query()`, `_build_response()`)
- Prefix with `_` for module-private
- Located in same file as node or in `utils/`

### Return Type Guidelines

**For Services**:
- Use tuples for multiple outcomes: `tuple[Result | None, Error | None]`
- Use DTOs/Pydantic models for complex returns
- Document all possible return combinations

**For Helpers**:
- Simple types when possible
- Raise exceptions for unexpected errors
- Return None for "not found" semantics

---

## Examples

### Good: Service Layer

```python
# ✅ GOOD
class PlannerService:
    async def generate_plan(...) -> tuple[ExecutionPlan | None, ValidationResult | None]:
        # 1. Build prompt
        prompt = self._build_prompt(...)

        # 2. Retry loop
        for attempt in range(max_retries):
            plan = await self._invoke_llm(prompt)
            result = self._validate(plan)
            if result.is_valid:
                return plan, result
            prompt = self._add_retry_feedback(prompt, result)

        return plan, result  # Failed after retries
```

### Good: Helper Functions

```python
# ✅ GOOD
def _extract_user_query(messages: list[BaseMessage]) -> str:
    """Extract last user message from conversation."""
    if not messages:
        raise ValueError("No messages provided")

    user_messages = [m for m in reversed(messages) if m.type == "human"]
    if not user_messages:
        raise ValueError("No user message found")

    return user_messages[0].content
```

### Good: Thin Node

```python
# ✅ GOOD: Thin orchestrator
async def planner_node(state, config) -> dict:
    """Generate execution plan (orchestrator only)."""
    # 1. Initialize
    run_id = config.get("metadata", {}).get("run_id")
    settings = get_settings()

    # 2. Prepare inputs
    user_query, messages, catalogue, context, registry = (
        await _prepare_inputs(state, config, settings, run_id)
    )

    # 3. Delegate to service
    service = PlannerService(registry, settings)
    plan, result = await service.generate_plan(...)

    # 4. Build response
    if plan and result.is_valid:
        return _build_success_response(plan, result, run_id)
    elif plan:
        return _build_validation_failed_response(plan, result)
    else:
        return _build_parsing_failed_response(run_id, plan, result)
```

### Bad: Monolithic Node

```python
# ❌ BAD: Everything embedded in node
async def planner_node(state, config) -> dict:
    # 800 lines of:
    # - Input preparation
    # - LLM invocation
    # - Retry loops
    # - JSON parsing
    # - Validation
    # - Response building
    # All mixed together!
```

---

## Related ADRs

- **ADR-006**: Soft Validation for List Operations (validation patterns)
- **ADR-008**: (Future) Testing Strategy for Service Layer

---

## References

### Sessions
- [SESSION_16_FINAL.md](../optim/SESSION_16_FINAL.md) - Initial analysis
- [SESSION_17_SUMMARY.md](../optim/SESSION_17_SUMMARY.md) - Phase 1: Helpers
- [SESSION_18_SUMMARY.md](../optim/SESSION_18_SUMMARY.md) - Phase 2: Service
- [SESSION_18_QUICK_WIN.md](../optim/SESSION_18_QUICK_WIN.md) - Catalogue helper
- [SESSION_18_CONTINUATION_TO_100_LINES.md](../optim/SESSION_18_CONTINUATION_TO_100_LINES.md) - Final extraction

### Code
- [planner_node.py](../../apps/api/src/domains/agents/nodes/planner_node.py) - Refactored node (76 lines)
- [planner_service.py](../../apps/api/src/domains/agents/services/planner_service.py) - Service class (554 lines)

---

**ADR Status**: ✅ **ACCEPTED AND IMPLEMENTED**
**Implementation Date**: 2025-11-16
**Review Date**: (To be scheduled)
**Next Steps**:
1. Apply pattern to step_executor_node (657 lines → <100)
2. Add unit tests for PlannerService
3. Document testing patterns in ADR-008
