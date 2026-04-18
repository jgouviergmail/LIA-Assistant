# ADR-072: Tool Context Manager — Two-Keys Simplification

**Date**: 2026-04-18
**Status**: Accepted
**Context**: Eliminate legacy DETAILS cache in Tool Context Manager, simplify to two-keys design (`list` + `current`).

## Context

The Tool Context Manager (TCM) was designed with three Store keys per domain:

- `list`: last search/list results (overwrite)
- `details`: accumulated detail views (LRU merge, max 10, dedup by `primary_id_field`)
- `current`: single focused item (demonstrative/pronoun references)

This architecture dates back to v1 when unified tools did not exist:

- **Search tools** (`search_contacts_tool`) returned partial summaries (id + name)
- **Detail tools** (`get_contact_details_tool`) returned full payload

The DETAILS cache existed to accumulate "fully hydrated" items across detail fetches, so a search (summaries) followed by multiple detail fetches built a working set of full records.

### What changed

**Architecture v2.0** (2026-01) introduced unified tools (`get_events_tool`, `get_contacts_tool`, `get_tasks_tool`, `get_emails_tool`):

- Always return **full details** whether queried by text (search) or by ID (direct fetch)
- Same payload shape regardless of mode

This invalidated the distinction that justified DETAILS.

### Evidence that DETAILS was redundant

Systemic audit of `manager.get_details()` callers in `apps/api/src/` (excluding `manager.py` itself):

| Caller | Usage |
|---|---|
| `calendar_tools._resolve_calendar_id_from_context` | **Fallback** after `get_list()` empty |
| `hitl/parameter_enrichment.resolve_display_label_from_context` | **Fallback** after `get_list()` empty |

**Zero call sites use DETAILS as a primary source.** Neither the `ContextResolutionService`, nor the `resolve_reference` tool, nor the planner, nor the router ever read DETAILS. The two fallback sites read the same payload shape that LIST contains — redundant.

### Bugs caused by the DETAILS layer

**Bug 1 — Double auto_save + DETAILS pollution**

The decorator `@auto_save_context` saved tool results on tool return. The parallel executor's `_auto_save_wave_contexts` saved them again after the wave completed. Both paths called `manager.auto_save()`.

When unified tool `get_events_tool(query="…")` returned `context_save_mode=LIST`:

1. Decorator called `auto_save(explicit_mode=LIST)` → saved to `list` key ✓
2. Parallel executor called `auto_save` with `dynamic_mode=None` (not propagated from UnifiedToolOutput) + `manifest.context_save_mode=None` (staged removal)
3. `classify_save_mode("get_events", …)` matched `"get"` keyword → returned DETAILS
4. Second save wrote the same payload to the `details` key (pollution)

**Bug 2 — `save_details` cannot identify newly created items**

After a HITL-confirmed create/update (e.g., `execute_event_draft`), the result dict carries `event_id` (not `id`). `_set_current_item_after_execution` called `save_details`, which tried to dedupe by `primary_id_field = "id"` per the events domain definition. The lookup failed → `save_details_missing_primary_id` warning, item not indexed, and the current_item fallback resolved to `indexed_items[-1]` (a stale item from a previous search).

**Bug 3 — `current_item` not updated after linguistic evocation**

Observed scenario (production logs, 2026-04-18):

1. User creates `test 3` via HITL → `current_item = test 3`
2. User updates `test 3` via HITL → `current_item = test 3` (still)
3. User asks `"c'était quoi le premier rdv renvoyé ?"` → resolver returns `[test 1]` in `ResolvedContext` for the response, **but `current_item` stays on `test 3`** (no hook to propagate the evocation)
4. User says `"supprime ce rdv"` → demonstrative resolver looks up `current_item` → returns `test 3` → delete draft targets `test 3` instead of `test 1`

Root cause: the `ContextResolutionService` was read-only with respect to TCM. Successful ordinal/demonstrative/pronoun resolutions did not propagate to `current_item`. The invariant *"current = last item manipulated, searched, or evoked"* was violated for the "evoked" branch.

All three bugs stem from structural gaps in TCM authority, not incidental code errors.

## Decision

**Remove DETAILS entirely.** Replace with a two-keys design:

- `list`: result of the last bulk operation for this domain (overwrite). Auto-manages `current`.
- `current`: single focused item, set by direct fetches, creates, and updates.

### Write rules

| Operation | Save mode | Effect |
|---|---|---|
| Search/list (`get_X_tool(query=…)`) | `LIST` | overwrite `list`, auto-manage `current` |
| Direct fetch by ID single (`get_X_tool(id=…)`) | `CURRENT` | set `current`, do **not** touch `list` |
| Direct fetch by ID batch (`get_X_tool(ids=[…])`) | `CURRENT` | clear `current`, do **not** touch `list` |
| Create via HITL | `_sync_tcm_after_draft_execution` → `set_current_item` | item becomes current (list untouched) |
| Update via HITL | `_sync_tcm_after_draft_execution` → `set_current_item` + `update_item_in_list` | item becomes current AND replaces in place in list (index preserved) |
| Delete via HITL | `_sync_tcm_after_draft_execution` → `remove_item_from_list` (+ `clear_current_item` safety net) | item removed from list with reindex, current cleared if it was the deleted item |
| **Reference resolution** (ordinal/demonstrative/pronoun) | `set_current_item()` / `clear_current_item()` via resolver | 1 resolved → set ; N>1 resolved → clear |
| MCP or legacy tools | `manifest.context_save_mode` or default `LIST` | no behavior regression |

### Invariant for `current_item`

> **`current_item` must always hold the last item manipulated, searched, or evoked by the user.**

"Evoked" covers any successful linguistic reference — ordinals (`"le 2e"`),
demonstratives (`"ce rdv"`), and pronouns (`"lui"`). Because the bug
*"supprime ce rdv after 'c'était quoi le premier rdv ?'"* was traced to the
resolver returning a correctly-resolved `ResolvedContext` while `current_item`
remained on a stale post-HITL value, the resolver now owns the side-effect of
keeping `current_item` consistent with the latest evocation. This follows the
same rule as `save_list`:

- `len(resolved_items) == 1` → `set_current_item(resolved_items[0])`
- `len(resolved_items) > 1`  → `clear_current_item` (multi-evocation, ambiguous)
- `len(resolved_items) == 0` → no-op (resolution failed, keep existing focus)

Rationale for *why the LLM is not responsible for this write path*: updating
`current_item` is event-driven state management (the event — "user evoked item X"
— is already structurally known once the resolver completes). The LLM participates
optimally upstream, in **detecting** the reference via `ContextReferenceOutput`
(semantic parsing is NLP territory). Down-shifting the update decision to another
LLM call would duplicate authority on a deterministic rule, add latency/cost, and
introduce new failure modes (hallucinated focus) with zero semantic benefit.

### Simplified `ContextSaveMode` enum

```python
class ContextSaveMode(str, Enum):
    LIST = "list"       # overwrite list + auto-manage current
    CURRENT = "current" # set current only, never touch list
    NONE = "none"       # skip
```

### Simplified `classify_save_mode`

```python
def classify_save_mode(tool_name, result_count, explicit_mode=None):
    return explicit_mode if explicit_mode is not None else ContextSaveMode.LIST
```

(No more tool-name heuristics; tools opt in explicitly via `UnifiedToolOutput.context_save_mode`.)

### Bug 1 mechanism (double save)

Fixed by a sentinel flag on `UnifiedToolOutput.tool_metadata`:

1. Decorator sets `tool_metadata["_tcm_saved"] = True` after `manager.auto_save()` returns.
2. `_execute_tool` propagates `_tcm_saved` into `ToolExecutionResult.result` dict.
3. `_auto_save_wave_contexts` checks `result_data.get("_tcm_saved")` and skips the duplicate save.

Non-decorated tools (MCP) still flow through `_auto_save_wave_contexts` with `manifest.context_save_mode`.

### Bug 2 mechanism (primary_id_field mismatch)

Fixed at the source by replacing `save_details([item])` with `set_current_item(item)` in `_set_current_item_after_execution`. `set_current_item` stores the item dict as-is — no `primary_id_field` lookup at the write path.

### Bug 3 mechanism (stale current after linguistic evocation)

Fixed by making `ContextResolutionService._resolve_llm_detected_reference` a **writer** of `current_item` (not just a reader). A new private helper `_update_current_after_resolution()` is invoked before each successful `ResolvedContext` return:

- `len(resolved_items) == 1` → `set_current_item(resolved_items[0])`
- `len(resolved_items) > 1`  → `clear_current_item`
- `len(resolved_items) == 0` → no-op

Failures are caught and logged — this side-effect never blocks the response path.

This closes the last authority gap: every TCM write is now owned by the layer that knows the event occurred (tool execution, HITL execute, or reference resolution).

### 2026-04 follow-up — Post-HITL list maintenance (create / update / delete)

The first version of the ADR left two edge cases uncovered: HITL **update** did not propagate changes into the LIST (only CURRENT), and HITL **delete** did not remove the item from the LIST (nor clear CURRENT if it matched). Both led to stale LIST entries surfacing on subsequent ordinal references.

Fixed by unifying the post-execution TCM maintenance behind a single dispatcher `_sync_tcm_after_draft_execution(draft_type, draft_content, result_data, config, run_id)` in `draft_executor.py`:

| Draft family | TCM writes |
|---|---|
| `event` / `contact` / `task` / `email(|_reply|_forward)` (create) | `set_current_item(merged_item)` — LIST untouched |
| `*_update` | `set_current_item(merged_item)` + `update_item_in_list(item_id, merged_item)` (no-op if not in LIST, preserves index) |
| `*_delete` | `remove_item_from_list(item_id)` (reindex + clear current on match) + safety-net `clear_current_item` if the deleted item was current but not in LIST (direct-fetch flow) |

`manager.update_item_in_list(user_id, session_id, domain, item_id, updated_item, store)` is the new symmetrical helper to `remove_item_from_list`: same semantics (matching on `ContextTypeRegistry.primary_id_field`, index preservation, no side effects on CURRENT), but replaces the payload in place.

### 2026-04 follow-up — `turn_type` convention unification

`QueryIntelligence.turn_type` emits UPPERCASE composite values (`"ACTION"`, `"REFERENCE_PURE"`, `"REFERENCE_ACTION"`). The router wrote these verbatim into `state[STATE_KEY_TURN_TYPE]`. Consumers compared against lowercase constants (`TURN_TYPE_REFERENCE = "reference"`), so every reference turn fell through the comparison. Concretely: `resolved_context` was never fed into `agent_results_summary` in `response_node`, and reference turns appeared "conversational" to the LLM, which produced ungrounded responses (e.g. misinterpreting *"renvoyé"* as *"postponed"* instead of *"returned by search"*).

Fixed by:

1. New `src/domains/agents/utils/turn_type.py` with case-tolerant helpers `is_reference_turn`, `is_action_turn`, `is_conversational_turn`, and `normalize_turn_type`. All accept the UPPERCASE legacy form and the composite variants.
2. `router_node_v3` writes `normalize_turn_type(intelligence.turn_type)` → state always holds the canonical lowercase form.
3. All consumers (`response_node`, `registry_filtering`) migrated from raw `==` comparisons to the helpers.

Canonical form from now on: lowercase, one of `{action, reference, reference_pure, reference_action, conversational}`. External sources (LLM output, legacy code) are tolerated through the helpers.

### 2026-04 follow-up — HITL update template: two-blocks structure

The `hitl_draft_critique_prompt.txt` for `*_update` draft types was reworked from one implicit "unmodified fields shown normally" directive into two explicit labelled blocks:

- **`{L_Modifications}`** — only the fields that actually changed, rendered as `~~old~~ → **new**`.
- **`{L_Full_post_update}`** — the complete item AFTER the change, used as a post-update snapshot.

Labels are provided per-language via `HitlMessages.get_draft_update_labels(language)` and injected into the prompt before LLM invocation. An explicit anti-pattern clause forbids the LLM from inventing labels such as *"unchanged"*, *"inchangé"*, *"autres détails inchangés"* — which previously contradicted themselves by listing values that had just been modified.

## Alternatives considered

1. **Keep DETAILS, propagate `context_save_mode` through `ToolExecutionResult`**: fixes only Bug 1 (double save routing) but keeps the LRU complexity, `primary_id_field` dedup, and Bug 2. Rejected — addresses symptoms, not root cause.

2. **Unify LIST and DETAILS into a single merged cache**: breaks the "search preserved after detail fetch" invariant (scenario S2) — `get_X_tool(id=)` would overwrite the search list. Rejected.

3. **Auto-detect decorator via tool introspection**: brittle, slower, harder to test. Rejected in favor of the explicit `_tcm_saved` flag.

## Consequences

### Positive

- **~200 lines of code removed**: `save_details`, `get_details`, `ToolContextDetails`, LRU merge, primary_id dedup at write, 2 fallback readers, obsolete tests
- **2 classes of bugs structurally eliminated**: double save pollution, primary_id mismatch on create/update
- **Simpler mental model**: 2 keys, 1 classification rule, explicit opt-in via tool output
- **No manifests duplication**: `context_save_mode` removed from manifests (staged), single source of truth = tool output
- **No migration required**: legacy `"details"` keys in the Store remain readable but unused; overwritten when next search hits the domain

### Negative / trade-offs

- **No LRU cache of previously-viewed items**: if a user viewed a detail for an item that is not in the current LIST, a subsequent HITL parameter enrichment can't look up its display label via DETAILS. Mitigated by a secondary lookup via `current_item`. Acceptable: planner always resolves IDs from context (LIST) first.

- **Tests rewritten**: `test_save_details_current_management.py`, `test_get_contact_details_save_mode.py`, `test_multi_keys_store_pattern.py` deleted. New coverage: `test_auto_save_current_mode.py`, `test_draft_executor_current_item.py`.

## Migration

- No database migration. Legacy `"details"` Store keys are orphaned — ignored on read, never rewritten. The debug script `scripts/debug/debug_store_state.py` flags their presence but does not treat it as an error.

- No API break for consumers of `ToolContextManager`. Removed methods (`save_details`, `get_details`) were not called from outside TCM internals or the two fallback readers (now refactored).

## Files changed

Source :
- `apps/api/src/domains/agents/context/schemas.py` — `ContextSaveMode` réduit à `{LIST, CURRENT, NONE}`, `ToolContextDetails` supprimé.
- `apps/api/src/domains/agents/context/manager.py` — `save_details` / `get_details` supprimés, branche CURRENT câblée dans `auto_save`, `classify_save_mode` simplifié, nouvelles méthodes `remove_item_from_list` + `update_item_in_list`.
- `apps/api/src/domains/agents/context/access.py` — nouveau helper `get_tcm_session()` + dataclass `TcmSession`.
- `apps/api/src/domains/agents/context/decorators.py` — propagation `_tcm_saved` via `tool_metadata`, priorité au `context_save_mode` du tool.
- `apps/api/src/domains/agents/context/__init__.py` — retrait export `ToolContextDetails`.
- `apps/api/src/domains/agents/orchestration/parallel_executor.py` — skip auto-save si `_tcm_saved`, propagation dans `ToolExecutionResult.result`.
- `apps/api/src/domains/agents/services/draft_executor.py` — dispatcher `_sync_tcm_after_draft_execution` + handlers `_sync_create`/`_sync_update`/`_sync_delete`, tables canoniques `_DRAFT_TYPE_TO_TCM_DOMAIN` + `_DOMAIN_ID_KEYS`.
- `apps/api/src/domains/agents/services/context_resolution_service.py` — `_update_current_after_resolution` ; écriture de `current_item` après résolution réussie.
- `apps/api/src/domains/agents/services/hitl/interactions/draft_critique.py` — injection des labels i18n `{L_Modifications}` / `{L_Full_post_update}`.
- `apps/api/src/domains/agents/services/hitl/parameter_enrichment.py` — suppression du fallback DETAILS, lookup sur LIST + CURRENT.
- `apps/api/src/domains/agents/nodes/router_node_v3.py` — normalisation `turn_type` via `normalize_turn_type()` à l'écriture.
- `apps/api/src/domains/agents/nodes/response_node.py` — migration vers `is_reference_turn()` / `is_action_turn()` / `is_conversational_turn()`.
- `apps/api/src/domains/agents/utils/registry_filtering.py` — migration vers `is_reference_turn()`.
- `apps/api/src/domains/agents/utils/turn_type.py` — nouveau module helper (comparaisons case-tolerant).
- `apps/api/src/domains/agents/tools/{calendar,google_contacts,tasks,emails}_tools.py` — `context_save_mode = CURRENT` sur ID fetch, retrait des décorateurs `@auto_save_context` redondants sur les tools legacy.
- `apps/api/src/domains/agents/tools/output.py` — `UnifiedToolOutput.context_save_mode` documenté.
- `apps/api/src/core/i18n_hitl.py` — dictionnaire `_DRAFT_UPDATE_BLOCK_LABELS` 6 langues + méthode `get_draft_update_labels()`.
- `apps/api/src/domains/agents/prompts/v1/hitl_draft_critique_prompt.txt` — templates update reformulés en 2 blocs labellisés.

Tests :
- `apps/api/tests/unit/domains/agents/context/test_auto_save_current_mode.py` — nouveau.
- `apps/api/tests/unit/domains/agents/context/test_update_item_in_list.py` — nouveau.
- `apps/api/tests/unit/domains/agents/services/test_draft_executor_current_item.py` — nouveau.
- `apps/api/tests/unit/domains/agents/services/test_draft_executor_tcm_sync.py` — nouveau.
- `apps/api/tests/unit/domains/agents/services/test_reference_resolution_updates_current_item.py` — nouveau.
- `apps/api/tests/unit/domains/agents/utils/test_turn_type.py` — nouveau.
- `apps/api/tests/agents/test_context_manager_expanded.py` — suppressions des tests DETAILS + ajout tests CURRENT mode.
- `apps/api/tests/agents/test_context_cleanup_on_reset.py` — passe sur 2 clés au lieu de 3.
- `apps/api/tests/agents/test_get_contact_details_save_mode.py`, `test_multi_keys_store_pattern.py`, `test_save_details_current_management.py` — **supprimés** (devenus sans objet).

Docs :
- `docs/ARCHITECTURE_AGENT.md` — section 16 (TCM) rewritten pour 2 clés.
- `docs/architecture/ADR-030-Context-Resolution-Follow-up.md` — note follow-up 2026-04.
- `docs/architecture/ADR_INDEX.md` — entrée ADR-072.
- `docs/INDEX.md` — compteur ADR mis à jour.
- `docs/technical/AGENT_MANIFEST.md` — `context_save_mode` valeurs LIST/CURRENT/NONE.
- `docs/readme/README_TESTS_AGENTS.md` — suppression référence au test obsolète.
- `apps/api/scripts/debug/debug_store_state.py` — flag des clés `details` legacy résiduelles sans les traiter comme erreur.

## References

- ADR-012 — Data Registry / StandardToolOutput Pattern (superseded read-path coupling)
- ADR-016 — ContextTypeRegistry (still in use, `primary_id_field` remains meaningful for `remove_item_from_list`)
- ADR-030 — Context Resolution Follow-up (complementary)
