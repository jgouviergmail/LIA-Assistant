# ADR-125: Draft Preview Renderer Extraction — Dispatch Table out of the Models Module

**Status**: ✅ IMPLEMENTED (2026-07-11)
**Author**: Claude Code (Fable 5)
**Related**: [ADR-122](ADR-122-AgentService-Stream-Decomposition-B2.md) (method precedent — characterization-first decomposition), [ADR-085] Draft Display Registry (boot-time completeness assert pattern), file-size ratchet guard (`test_file_size_ratchet_guard.py`)

## Context

`Draft.get_detailed_preview` (`apps/api/src/domains/agents/drafts/models.py`)
renders the detailed HITL confirmation preview embedded verbatim in the
frontend confirmation cards. The 2026-07 audit cycle 3 re-ranked
decomposition targets by **cyclomatic complexity** and surfaced it at CC ≈ 93
— a 295-raw-line, 14-branch `elif` cascade over the 16 `DraftType` values,
concentrated in a **models** module (data structures + heavy presentation
logic: a double fault). Off the SSE critical path (two callers, both in
`drafts/service.py`, signature preserved), it was selected as extraction #2
of the complexity-reduction series by (CC × SLOC) / risk.

## Method (Feathers, characterization-first — ADR-122 precedent)

A golden-master net was written and verified green **before** any cut:
`tests/unit/domains/agents/drafts/test_detailed_preview_characterization.py`
— 63 tests (59 golden cases + 4 behavioral) pinning the EXACT output string
(full-string equality, byte-identical: the frontend cards render it
verbatim). Coverage: every `DraftType` (guarded by a net-completeness test),
every rendering branch (key fallbacks `from`/`from_addr`/`?`,
`filename`/`name`/`?` attachments, timed vs all-day events, `✏️`
modified-field marks vs values preserved from
`current_event`/`current_contact`/`current_task`, sublabel truncation
boundary at 5), **mixed modified/preserved cases on every update type**
(all-new/all-preserved pairs alone would let condition cross-wiring pass),
all 6 languages, timezone conversion, default-argument binding, and the
unknown-type fallback to `get_summary`. The net passed **identically,
unmodified**, after the extraction.

## Decision

Extract the renderer into a dedicated presentation module,
**`drafts/preview_renderer.py`**, replacing the `if`-cascade with a
**dispatch table** (`_PREVIEW_RENDERERS: dict[DraftType, _PreviewRenderer]`,
one small function per type; EMAIL and EMAIL_REPLY share
`_render_email_send`, `_render_email_forward` reuses it and appends
attachments). Three shared helpers (`_updated_row`, `_updated_datetime_row`,
`_first_item_value`) factor the recurring "modified ✏️ or preserved" pattern
of the update types — without them a verbatim move would have left
`_render_event_update`/`_render_contact_update` at CC 16–17; the output
stays byte-identical, proven by the net.

- `Draft.get_detailed_preview` becomes a 2-line delegate (function-local
  import to break the module cycle, same lazy-import style as the
  pre-existing `time_utils` import).
- **Boot-time completeness assert** (`assert_preview_renderer_completeness`)
  wired in `startup/registries.py::run_failfast_validations` right after the
  display-registry check (ADR-085 pattern: the app refuses to boot on a
  missing entry) + mirror unit test
  (`test_preview_renderer_registry.py`). The `get_summary` fallback for
  unregistered types is kept as defense in depth. The existing
  `assert_registry_completeness` (display registry) is untouched.

**Invariants held**: output byte-identical (golden net green unmodified); no
LangGraph state key added or touched; no structlog event renamed (one NEW
event added: `draft_preview_renderer_incomplete`, boot failure path only);
no opportunistic extraction outside the validated perimeter (`get_summary`,
CC 25, stays in `models.py` — next seam candidate).

**Numbers**: `models.py` 803 → **579 logical SLOC** — below the global
600-SLOC ceiling, so the file **leaves the frozen-size registry entirely**
(`task ratchet:update`, 55 frozen files remain); `preview_renderer.py`
**303 SLOC** (under the cap). Per-function CC after extraction: **max 9**
(`_render_event_update`), measured with the strictest AST counting —
if/elif, ternaries, loops, except/with, boolean operators, comprehensions,
else blocks all counted.

## Pinned observations — fixed as follow-up in the same delivery

During the extraction, three questionable behaviors were pinned as-is
(`PINNED CURRENT BEHAVIOR` markers) so the cut itself stayed byte-identical.
They were then fixed as **separate, deliberate behavior changes** in this
same delivery, with the golden table regenerated and the old/new tables
diffed to prove surgicality (exactly 3 goldens changed, 2 pinning cases
added, the 56 others byte-identical):

1. **Localized `no_subject`**: a subject-less email delete rendered the
   hardcoded French `"(sans objet)"` whatever the user language (systemic
   i18n rule violation). The French default was baked in at FIVE layers
   (tool header extraction, tool → draft call, `create_email_delete_draft`
   default, `EmailDeleteDraftInput` field default, renderer default). All
   five now store/pass the raw truth (`""`); the localized fallback is a new
   `no_subject` key in `DRAFT_PREVIEW_LABELS` (6 languages) applied at
   render time only. The execution message reuses the pre-existing
   subject-less variant of `APIMessages.email_moved_to_trash`.
2. **Forward body `None`** rendered the literal string `"None"` — now
   renders empty, exactly like an empty-string body.
3. **Fully-empty reminder delete** rendered an empty string — now renders
   the `"?"` fallback line, consistent with every other delete type.

## Note on the CC instrument

The cycle-3 CC figures were produced by an instrument not committed to the
repository, and no single mechanical counting rule reproduces all five
published reference figures exactly (best AST variant: 88 vs 93 on this
function, same ranking). Validation therefore used the strictest
reproducible AST counting with a target of ≤ 10 per extracted function —
comfortably under 15 on any scale. That counter is now committed as
**`scripts/audit/measure_cc.py`** (closing the audit-protocol "complexity
instrument due" item); the protocol documents that cross-instrument figures
must not be compared across cycles.

## Consequences

- `models.py` is a data/lifecycle module again; the preview logic is
  independently testable and extending it for a new `DraftType` is a
  registered function + a golden case, enforced twice (boot assert + net
  completeness test).
- The characterization harness (case table + golden generation from the
  live implementation) is reusable for the next seams of the series
  (`get_summary`, `planner_node_v3`, `_handle_execution_plan`).
