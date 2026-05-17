# ADR-085: Draft Display Registry — Single Source of Truth for Post-HITL Rendering

**Status**: ✅ IMPLEMENTED (2026-05-17)
**Author**: Claude Opus 4.7 (with `jgouviergmail`)
**Related**: ADR-008 (HITL Pattern), ADR-024 (i18n Architecture), ADR-012 (Data Registry / StandardToolOutput)

---

## Context

### The diagnostic that triggered this ADR

Running `"Supprime tous mes rappels"` against a calendar containing three pending reminders triggered the expected `destructive_confirm` HITL question. After the user confirmed, the chat rendered:

```
✅ 3/3
✅ Action exécutée avec succès
✅ Action exécutée avec succès
✅ Action exécutée avec succès
```

Forensic trace through `_format_draft_execution_result` ([apps/api/src/domains/agents/nodes/response_node.py](../../apps/api/src/domains/agents/nodes/response_node.py)) exposed **four independent sources of per-`DraftType` knowledge** that all had to be kept in sync, and the `REMINDER_DELETE` type — added later — had only been registered in one of them:

| Source of truth | File | Coverage (before fix) | Effect on the reminder bug |
|---|---|---|---|
| `DRAFT_TYPE_EMOJIS` | `src/core/i18n_hitl.py:1098` | 13/16 types | Domain emoji rendered as `""` → no `🔔` prefix |
| `DRAFT_SUCCESS_MESSAGES` | `src/core/i18n_drafts.py:20` | 15/16 types | Fell back to `_default` ("Action exécutée avec succès") for reminders |
| `_DRAFT_RESULT_FIELD_CONFIG` | `src/domains/agents/nodes/response_node.py:521` | **6/16** types — others depended on string-split fallback to base type | No `reminder_delete` entry, no fallback path resolved → empty detail block on single-confirm |
| Hardcoded label-extraction chain in batch loop | `response_node.py:609-623` | 5 fields (`subject/title/name/label_name/event.summary/contact.names[0].displayName`) | Reminders' `content` field was not in the chain → empty label → bland default message used |

The bug was therefore **structurally inevitable** with this design: every new `DraftType` had to thread through four disjoint tables plus an open-coded extraction chain. Adding `REMINDER_DELETE` had only touched one of them, and there was no test or runtime check to catch the gap.

### The broader concern

The user expressed a clear preference: not just patch reminders, but make the design *generic, elegant, and i18n-correct for all 6 supported languages*. The same shape of bug could re-emerge on `file_delete`/`label_delete` (which also had no `_DRAFT_RESULT_FIELD_CONFIG` entry — they survived only because they were never tested in batch mode). The fix had to invert the architectural pressure so that **adding a `DraftType` without registering its rendering becomes structurally impossible**.

Grammatical i18n added a second axis of difficulty. Past-participle agreement in French/Spanish/Italian depends on the noun's gender and number (e.g. `1 rappel supprimé` masculine singular, `3 tâches créées` feminine plural). English and German use invariant participles. Chinese uses a different word order entirely (`已删除 3 个提醒`). Hard-coding `f"{count}/{total}"` had sidestepped this entirely — but `"3/3 rappels supprimés"` is the right answer, and reaching it requires per-language pluralization rules plus per-noun gender metadata.

---

## Decision

Introduce a **single declarative registry** keyed by `DraftType`, with **structural invariants enforced both at startup and in CI**.

### 1. The registry

`apps/api/src/domains/agents/drafts/display.py` defines:

```python
@dataclass(frozen=True)
class DraftDisplayConfig:
    emoji: str                                  # "🔔"
    item_label_fields: tuple[str, ...]          # ("content",)        — priority chain
    item_secondary_datetime_key: str | None     # "trigger_at"        — appended " — 16 mai 14h00"
    detail_fields: tuple[DraftDisplayField, ...]  # rich single-confirm rows
    noun_key: str                                # "reminder"          — keys DRAFT_RESULT_NOUNS
    verb_past_key: str                           # "deleted"           — keys DRAFT_RESULT_VERBS_PAST

DRAFT_DISPLAY_REGISTRY: dict[DraftType, DraftDisplayConfig] = {...}  # 16 entries
```

Dotted notation (`"file.name"`, `"contact.names.0.displayName"`) is supported in `item_label_fields` and `detail_fields.content_key` via a `resolve_nested_value` helper that walks dicts and lists.

### 2. Grammatical i18n

Two new tables in `apps/api/src/core/i18n_drafts.py`:

- `DRAFT_RESULT_NOUNS[language][noun_key] = {"singular": str, "plural": str, "gender": "m"|"f"|None}` — 7 nouns × 6 languages.
- `DRAFT_RESULT_VERBS_PAST[language][verb_past_key]` — a string for invariant languages (en/de/zh-CN), a dict with `m_sing` / `m_plur` / `f_sing` / `f_plur` keys for languages with agreement (fr/es/it).
- `RESULT_HEADER_TEMPLATES[language]` — word-order template per language (Chinese is `已{verb} {count} 个{noun}`, others are `{count} {noun} {verb}`).

A new `get_plural_form(count, language)` encodes the pluralization rule per language (French treats 0 and 1 as singular, English/Spanish/German/Italian treat 1 as singular and everything else as plural, Chinese is invariant).

A new `compose_result_header(success_count, total_count, noun_key, verb_past_key, language)` assembles everything into a localized header. Examples:

```
fr   3/3   reminder deleted  →  "3 rappels supprimés"
fr   1/1   task    created   →  "1 tâche créée"          (feminine singular)
fr   3/3   task    created   →  "3 tâches créées"        (feminine plural)
fr   2/3   email   sent      →  "2/3 emails envoyés"     (partial, agreement on total)
en   3/3   reminder deleted  →  "3 reminders deleted"
de   3/3   event   deleted   →  "3 Termine gelöscht"     (noun changes, participle invariant)
it   3/3   task    created   →  "3 attività create"      (noun invariant, participle agrees)
zh-CN 3/3  reminder deleted  →  "已删除 3 个提醒"        (different word order)
```

### 3. Structural enforcement

`assert_registry_completeness()` raises `AssertionError` if any `DraftType` value is missing from the registry. It is invoked from **two places**:

- **Startup**: `apps/api/src/main.py` lifespan — the application refuses to boot if the registry is incomplete. Sits with the other fail-fast integrity checks (`validate_llm_configuration`, `validate_tool_error_codes`).
- **CI**: `apps/api/tests/unit/domains/agents/drafts/test_display_registry.py` exhaustively parametrizes on `list(DraftType)`, plus per-language parity checks for `noun_key` / `verb_past_key`, plus snapshot tests for `compose_result_header` covering every language and every grammar pattern (masculine/feminine, singular/plural, invariant).

A missing entry, a missing noun, or a missing verb form in any of the 6 languages fails the test.

### 4. Consolidation of legacy tables

- `DRAFT_TYPE_EMOJIS` in `i18n_hitl.py` is **removed**. `HitlMessages.get_draft_emoji()` becomes a one-line wrapper that delegates to `DRAFT_DISPLAY_REGISTRY` via a local import — the three external callsites in `draft_critique.py` are untouched (backwards-compat preserved).
- `_DRAFT_RESULT_FIELD_CONFIG` in `response_node.py` is **removed**. `_format_draft_execution_result` reads `detail_fields` from the registry.
- The hard-coded label-extraction chain in the batch loop is **removed**. The new `_format_batch_result` helper reads `item_label_fields` from the registry.

`DRAFT_SUCCESS_MESSAGES` / `DRAFT_CANCEL_MESSAGES` are **kept** (used by other code paths, e.g. `get_summary` on the Draft model), with the missing `reminder_delete` entry added in all 6 languages.

---

## Alternatives Considered

### Alt 1 — Targeted patch (rejected)

Add a `reminder_delete` entry to the 4 separate tables and extend the label-extraction chain to include `"content"`. **Five-line change** but leaves the structural fragility intact. The next `DraftType` addition will reproduce the bug.

### Alt 2 — Push display methods onto `Draft` / `*DraftInput` (rejected)

OO-purer: each input class declares `get_executed_display(language) -> DisplayPayload`. Rejected because:
- The executor stores `_draft_content` as a raw dict, not the typed input. Reconstructing the typed input from the dict is non-trivial and a layering violation (the rendering happens far from the domain).
- It scatters one concern (display) across 16 classes instead of one table.
- It's harder to enforce exhaustivity at startup — the assertion would need to walk all subclasses.

### Alt 3 — Generate config from i18n_drafts only (rejected)

`DRAFT_SUCCESS_MESSAGES` already has per-type strings — why not derive the display config from them? Rejected because the success messages contain free-form text (`"'{summary}' créé avec succès"`) with no structured slot for emoji, label fields, or detail fields. Trying to retrofit metadata onto these strings would be more painful than a fresh registry.

### Alt 4 — Composite emoji simplification (rejected per user input)

Replacing the existing composite emojis (`🗑️📅`, `📝📅`) with a single emoji per family was considered. Rejected because the composite signals the *action* (delete vs update vs create) at a glance, and backwards-compat with the HITL question cosmetics matters. The registry preserves the existing emoji choices verbatim.

---

## Consequences

### Positive

- **Adding a new `DraftType` is now a one-place change**. Forgetting to register it kills the boot — the test suite kills the PR.
- **All 16 existing types** now render correctly (the legacy state quietly silently degraded `file_delete` / `label_delete` / `reminder_delete` in batch mode; that's fixed).
- **Grammatical i18n is correct in all 6 supported languages**, including French/Spanish/Italian gender agreement and Chinese word order.
- **Backwards-compat preserved**: every public API (`HitlMessages.get_draft_emoji`, `DRAFT_SUCCESS_MESSAGES`, etc.) keeps the same shape and behavior for known types.
- **Telemetry**: when label extraction fails for a row, a `draft_result_format_empty_label` warning is logged with the available draft-content keys, surfacing future schema drift before it reaches the user.

### Trade-offs

- **+~250 lines of new code** (the registry, the new i18n tables, the helpers, the tests). Recouped by ~150 lines of legacy table deletion and ~80 lines of removed conditional rendering in `_format_draft_execution_result`. Net: roughly break-even on LoC, large win on cohesion.
- **Two new i18n tables to maintain** (`DRAFT_RESULT_NOUNS`, `DRAFT_RESULT_VERBS_PAST`). Both are very small (7 nouns × 6 langs, 4 verbs × 6 langs) and the test enforces exhaustivity per language, so drift cannot ship undetected.
- **Local import inside `HitlMessages.get_draft_emoji`** to avoid a top-level cycle between `i18n_hitl` and `drafts.display`. Idiomatic Python and the only callsite is on the warm path of HITL streaming.

---

## Implementation Map

| File | Action | Description |
|---|---|---|
| `apps/api/src/domains/agents/drafts/display.py` | NEW | Registry, helpers (`get_draft_display_config`, `get_draft_emoji`, `resolve_nested_value`), startup assertion |
| `apps/api/src/core/i18n_drafts.py` | MODIFY | `reminder_delete` entries in success/cancel × 6 langs; new `DRAFT_RESULT_NOUNS`, `DRAFT_RESULT_VERBS_PAST`, `RESULT_HEADER_TEMPLATES` tables; new `get_plural_form` and `compose_result_header` helpers |
| `apps/api/src/core/i18n_hitl.py` | MODIFY | Delete `DRAFT_TYPE_EMOJIS`; convert `HitlMessages.get_draft_emoji` into a one-line wrapper |
| `apps/api/src/domains/agents/nodes/response_node.py` | MODIFY | Delete `_DRAFT_RESULT_FIELD_CONFIG`; refactor `_format_draft_execution_result` to read the registry; extract `_format_batch_result` helper |
| `apps/api/src/main.py` | MODIFY | Invoke `assert_registry_completeness()` in the lifespan startup |
| `apps/api/tests/unit/domains/agents/drafts/test_display_registry.py` | NEW | Exhaustive registry tests (~30 cases, parametrized over types and languages) |
| `apps/api/tests/unit/domains/agents/nodes/test_format_draft_execution_result.py` | NEW | End-to-end renderer tests covering batch / single / cancelled / error + per-language headers |

---

## Validation

- ✅ All 16 `DraftType` values registered (asserted at boot and in CI).
- ✅ `compose_result_header` snapshots green for 19 grammar patterns across 6 languages.
- ✅ Empty-label fallback paths logged but never crash.
- ✅ Pre-existing `HitlMessages.get_draft_emoji` callsites in `draft_critique.py` untouched and continuing to work.
- ✅ The original bug scenario (`Supprime tous mes rappels` × 3) now renders `🔔 ✅ 3 rappels supprimés` with each row carrying the reminder content and trigger datetime.

---

## Extension (2026-05-17): unified HITL **pre-confirmation** preview rendering

The initial ADR scope was the **post-execution** result block. The same registry has since been reused to unify the **pre-confirmation** rendering — the bullet list that shows which items the user is about to mutate, displayed by two distinct HITL interactions:

- `DraftCritiqueInteraction._generate_batch_critique` (title: *"Confirmation requise"* / *"Confirmation de suppression"*) — invoked when FOR_EACH produced N drafts and the user must approve the batch.
- `ForEachConfirmationInteraction._build_item_previews_section` (title: *"Confirmation d'opération en masse"*) — invoked when the planner emits a FOR_EACH step whose mutation threshold triggers a confirmation.

### Symptom that motivated the extension

For the same 3-reminder deletion scenario, the two paths produced incoherent rows:

```
# Path A (for_each_confirmation)
Rappel : Médecin le 17 mai 2026 à 19:00         ← no emoji, "le" connector

# Path B (draft_critique batch)
- 🔔 Médecin
  🔔 dimanche 17 mai 2026 à 19:00               ← duplicated 🔔, two lines collapsed by chat UI
                                                  to "🔔 Médecin 🔔 dimanche ..."
```

Diagnosis: Path A built rows from a generic `item_previews: list[dict]` joined with a localized connector (`"le"`/`"on"`/`"el"`/...) declared in `_FOR_EACH_CONFIRM_UI[lang]["item_date_connector"]`. Path B built rows via a 100-line per-`draft_type` if/elif chain in `_extract_batch_item_preview`, with the row emoji injected both as `main_label` prefix and inside the appended `detail_parts`. Plus `_DESTRUCTIVE_CONFIRM_ACTION_TITLES` was missing a `reminder_delete` entry, so Path B fell back to the generic *"Confirmation requise"* title instead of *"Confirmation de suppression"* (same systemic oversight that motivated this ADR — fourth-table-syndrome).

### Decision (extension)

1. **One shared helper** — `src.core.i18n_drafts.format_hitl_item_preview(draft_type, content, language, user_timezone)` — returns the unified row string:

   ```
   {emoji} {Noun_capitalized} : {label} - {datetime_with_day_name}
   ```

   It reads everything from `DRAFT_DISPLAY_REGISTRY`: emoji, `item_label_fields` (with dotted-path resolution via `resolve_nested_value`), `item_secondary_datetime_key`, plus the localized capitalized noun from `DRAFT_RESULT_NOUNS`. The datetime is always rendered with `include_day_name=True` so the weekday is visible.

2. **`DraftCritiqueInteraction._generate_batch_critique`** — replaced the ~100-line per-domain if/elif chain (`_extract_batch_item_preview`) with a single call to `format_hitl_item_preview()`. Defensive 6-field fallback (`subject/summary/title/name/content/label_name`) preserved for unregistered draft types, although the startup assertion makes this branch unreachable.

3. **`ForEachConfirmationInteraction._build_item_previews_section`** — added a `steps` parameter and a static helper `_steps_to_draft_type(steps)` that maps a FOR_EACH `tool_name` to a canonical `DraftType` string (e.g. `cancel_reminder_tool` → `"reminder_delete"`, `update_event_tool` → `"event_update"`, `send_email_tool` → `"email"`). When the mapping resolves, the unified helper is used; otherwise the legacy generic renderer remains (preserved for non-draft domains: places, weather, routes, web_fetch, mcp).

4. **`_DESTRUCTIVE_CONFIRM_ACTION_TITLES`** — added `reminder_delete` entry in all 6 languages (`"Confirmation de suppression"` / `"Confirm deletion"` / `"Confirmar eliminación"` / `"Löschung bestätigen"` / `"Conferma eliminazione"` / `"确认删除"`). Eliminates the generic-title fallback for reminders.

### Tests (extension)

- `apps/api/tests/unit/domains/agents/drafts/test_hitl_item_preview.py` — 119 parametrized cases: regression guard on the duplicated-emoji bug, per-language noun capitalization, per-`DraftType` smoke (16 × 6 languages = 96 cases), edge cases (nested fields, missing label, missing datetime, unknown draft type).
- `apps/api/tests/unit/domains/agents/drafts/test_for_each_draft_type_mapping.py` — 25 cases on the `tool_name` → `draft_type` translation (delete/update/send/create/reply/forward verbs across 7 domains, plus edge cases for unknown domains and empty steps).

### Final rendering for `Supprime tous mes rappels` (both HITL paths converge)

```
⚠️ **Confirmation de suppression**

**Éléments concernés :**
- 🔔 Rappel : Médecin - dimanche 17 mai 2026 à 19:00
- 🔔 Rappel : Ramonage - jeudi 21 mai 2026 à 19:00
- 🔔 Rappel : Alsace - vendredi 22 mai 2026 à 19:00

⚠️ Cette action est irréversible.

**Confirmes-tu cette suppression ?**
```

And every other domain inherits the same shape automatically:

```
📅 Événement : Réunion équipe - lundi 20 mai 2026 à 10:00
📧 Email : Confirmation rdv jeudi - jeudi 16 mai 2026 à 14:00
👤 Contact : Marie Dupont
✅ Tâche : Préparer démo - mardi 20 mai 2026 à 17:00
```

### Backwards-compat (extension)

- `HitlMessages.get_draft_emoji()` unchanged (kept as registry wrapper from the original ADR).
- `format_value_if_iso_datetime` still imported in `for_each_confirmation.py` for the legacy fallback path (places/weather/routes/web_fetch/mcp keep their existing rendering).
- `_FOR_EACH_CONFIRM_UI[lang]["item_date_connector"]` retained for the legacy fallback.
- All existing tests in `tests/unit/domains/agents/` continue to pass without modification.
