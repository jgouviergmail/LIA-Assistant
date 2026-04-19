# ADR-074: `structured_data` Contract for Tool Outputs

**Date**: 2026-04-19
**Status**: Accepted
**Context**: Formalize the `UnifiedToolOutput.structured_data` contract so that every tool exposes queryable domain data in a consistent, chainable format — enabling deterministic plans (`$steps.<step_id>.<key>`), skill scripts, and Jinja2 template resolution without relying on the legacy `result["data"]` fallback.

## Context

The `UnifiedToolOutput` model (see [apps/api/src/domains/agents/tools/output.py](../../apps/api/src/domains/agents/tools/output.py)) carries four distinct fields that were historically conflated in the codebase:

| Field | Audience | Purpose |
|---|---|---|
| `message` | LLM | Compact, token-efficient summary |
| `registry_updates` | Frontend (SSE) | Rich `RegistryItem` payloads used by UI cards and reference resolution |
| `structured_data` | Orchestration layer + skill scripts | Flat, queryable entities exposed to `$steps.<step_id>.<key>` chaining |
| `metadata` | Observability | Debug / telemetry (cache flags, execution time, counts, etc.) — **not queryable** |

Two systemic issues triggered this ADR:

1. **Anti-pattern** — Several tools (notably `brave_tools.py` prior to this change) smuggled domain data into `metadata`, which is semantically reserved for debug/observability and never consumed by the orchestration layer. The practice leaked structured data into a non-queryable bucket, breaking `$steps.<step_id>.braves` chaining.
2. **Silent reliance on registry reconstruction** — The parallel executor reconstructs `completed_steps[step_id]` by iterating `registry_updates` and grouping items by `meta.domain`. This is an implementation detail of the executor — every tool that wanted stable chaining still had to accept opaque behavior dependent on whether `meta.domain` was set. Tools **without** `registry_updates` (e.g. Philips Hue rooms/scenes, action confirmations) produced no queryable data at all, making skill plans impossible on these domains.

The skill layer ([ADR-070](ADR-070-ReAct-Execution-Mode.md)) amplified the problem: a deterministic plan step template such as `parameters: {forecasts: "$steps.get_weather.forecasts"}` silently failed whenever the upstream tool had not exposed `forecasts` in `structured_data`.

## Decision

Promote `structured_data` to **the single, explicit contract** through which tools expose business entities to downstream consumers. Every tool must:

1. Populate `structured_data` with a flat, queryable dict aligned with the conventions below.
2. Restrict `metadata` to debug / observability fields (never domain entities).
3. Keep `registry_updates` as the UI-oriented channel (SSE, ref resolution), independent from `structured_data` concerns.

### Canonical shape

```python
structured_data = {
    "<plural_domain_key>": [<entity_dict>, ...],  # plural, snake_case
    "count": N,                                    # always present when a list is exposed
    # optional search/context metadata (propagated for chaining)
    "query": "...",
    "operation": "search" | "list" | "details" | ...,
    "from_cache": bool,
    "user_timezone": "Europe/Paris",
    # domain-specific extras
    ...
}
```

**Rules**:

1. **Plural key aligned with `REGISTRY_TYPE_TO_KEY`** — `contacts`, `emails`, `events`, `tasks`, `files`, `places`, `weathers`, `rooms`, `scenes`, `braves`, etc. Canonical mapping lives in `apps/api/src/domains/agents/tools/output.py`.
2. **Flat** — No `{"data": {"items": [...]}}` nesting. Jinja2 templates must reach entities in one hop: `{{ steps.search.contacts[0].name }}`.
3. **`count` is mandatory when exposing a list** — simplifies templates and avoids redundant `len(...)` calls.
4. **`None` metadata values are stripped** — the helper `ToolOutputMixin._build_items_structured_data` filters them automatically.
5. **Action tools** (reminders, control, confirmations) expose their action payload (`action`, `success`, resource ids) — enabling skills and plans to assert on the outcome.

### Helper: `ToolOutputMixin._build_items_structured_data`

A single private helper centralizes the pattern. All `build_*_output` methods and the `create_tool_formatter` factory route through it, guaranteeing the same output shape.

```python
@staticmethod
def _build_items_structured_data(
    items: list[dict[str, Any]],
    plural_key: str,
    **extra: Any,
) -> dict[str, Any]:
    return {
        plural_key: [dict(item) for item in items],  # shallow snapshot
        "count": len(items),
        **{k: v for k, v in extra.items() if v is not None},
    }
```

### Coexistence with registry reconstruction

The parallel executor ([apps/api/src/domains/agents/orchestration/parallel_executor.py](../../apps/api/src/domains/agents/orchestration/parallel_executor.py)) continues to reconstruct a `structured_data` dict from `registry_updates` grouped by `meta.domain`. Tool-provided `structured_data` is then merged **without overwriting** the registry-derived keys:

```python
# parallel_executor (simplified)
structured_data = reconstruct_from_registry(registry_updates)  # meta.domain → payloads
if tool_output.structured_data:
    for k, v in tool_output.structured_data.items():
        structured_data.setdefault(k, v)  # registry wins on conflict (keeps _registry_id)
```

This coexistence is intentional:

- Registry reconstruction adds `_registry_id` to each payload for FOR_EACH correlation — this is preserved.
- Tool-provided `structured_data` adds search metadata (`query`, `count`, `operation`, `user_timezone`) and covers domains without registry items (Hue rooms/scenes, brave results when registry creation is skipped, action confirmations).

### Scope of the migration

All helpers in `apps/api/src/domains/agents/tools/mixins.py` now expose `structured_data` explicitly:

- `build_contacts_output`
- `build_emails_output`
- `build_events_output`
- `build_tasks_output`
- `build_files_output`
- `build_places_output`
- `build_weather_output`
- `build_standard_output` (accepts a `plural_key` override, defaults to `REGISTRY_TYPE_TO_KEY`)
- `create_tool_formatter` (factory)

Per-tool corrections removed the anti-pattern of domain data in `metadata`:

- `brave_tools.py` — `braves` moved from `metadata` to `structured_data`.
- `hue_tools.py` — 6 tools (`ListHueLightsTool`, `ListHueRoomsTool`, `ListHueScenesTool`, `ControlHueLightTool`, `ControlHueRoomTool`, `ActivateHueSceneTool`) now expose their domain data / action payload via `structured_data`.

## Consequences

### Positive

- **Skill scripts receive a stable, documented contract**. `$steps.<step_id>.<plural_key>` is guaranteed by the tool contract, not by registry reconstruction implementation details.
- **Deterministic plans chain reliably across all domains**. No more invisible dependencies on `meta.domain` set/unset.
- **`metadata` regains its proper role** — debug/observability only. Prometheus exporters, cache inspectors and log pipelines can safely assume `metadata` does not leak arbitrary domain payloads.
- **Single source of truth for the contract** — the `_build_items_structured_data` helper enforces the shape; tests live in `tests/unit/domains/agents/tools/test_mixins_structured_data.py` and `test_brave_hue_structured_data.py`.
- **Compatible with the existing registry reconstruction path** — no change needed in `parallel_executor.py`. Legacy behavior preserved.

### Negative / accepted trade-offs

- **Some key duplication between registry and structured_data** (e.g. both expose `contacts`). The executor deduplicates gracefully (registry wins). The redundancy is explicit, documented, and costs essentially zero (shallow list copy).
- **Tests that relied on the absence of `structured_data` keys** in `UnifiedToolOutput.metadata` must be updated. The affected surface is small (brave was the only production anti-pattern).

### Risks mitigated

- `test_standard_tool_output_structured_data.py::test_structured_data_priority_over_registry` continues to pass: the executor-level merge preserves registry-derived payloads on key conflicts.
- `get_step_output()` on `UnifiedToolOutput` / `StandardToolOutput` (used only in tests today) keeps its Priority 1 → 2 → 3 fallback logic unchanged.

## Follow-ups

1. Document the contract in [docs/technical/SKILLS_INTEGRATION.md](../technical/SKILLS_INTEGRATION.md) under "Tool output contract for skill scripts".
2. Extend [docs/guides/GUIDE_TOOL_CREATION.md](../guides/GUIDE_TOOL_CREATION.md) with a checklist item: "Expose queryable data via `structured_data`, not `metadata`".
3. Optional: emit a one-time warning in `parallel_executor._merge_step_result` when a tool's `metadata` contains a known domain plural key — a heuristic tripwire for future regressions.

## References

- [apps/api/src/domains/agents/tools/output.py](../../apps/api/src/domains/agents/tools/output.py) — `UnifiedToolOutput`, `REGISTRY_TYPE_TO_KEY`
- [apps/api/src/domains/agents/tools/mixins.py](../../apps/api/src/domains/agents/tools/mixins.py) — `ToolOutputMixin`, `_build_items_structured_data`
- [apps/api/src/domains/agents/orchestration/parallel_executor.py](../../apps/api/src/domains/agents/orchestration/parallel_executor.py) — merge gentle (~L2675) and `completed_steps` assignment (~L3025)
- [ADR-070](ADR-070-ReAct-Execution-Mode.md) — Skill ReAct execution mode (upstream consumer)
- [ADR-071](ADR-071-Skill-Semantic-Identification.md) — Skill semantic identification
