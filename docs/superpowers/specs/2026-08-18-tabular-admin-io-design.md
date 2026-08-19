# Tabular Admin Import/Export — Design Specification

- **Date**: 2026-08-18
- **Status**: Approved design, pre-implementation
- **ADR**: ADR-228 (to be written in Lot 0)
- **Scope**: a generic spreadsheet import/export foundation, with LLM model + pricing administration as its single consumer
- **Patterns mirrored**: `PluginImportReport` (never-silent per-item report), `document_generation/sanitize.py` (`neutralize_formula`), `SectionToolbar` (ADR-208), registry completeness asserts (ADR-085)

## 1. Goal

Replace row-by-row manual administration of the LLM catalogue and its prices with a
round-trip through a structured Excel workbook:

1. **Export** every model with every characteristic and its current tariff.
2. **Edit** offline — add, modify, deactivate — helped by dropdown lists fed by
   referential sheets, plus an in-file usage notice.
3. **Import** the file back, with a mandatory preview and all-or-nothing application.

The mechanism is built as a reusable foundation so other administration screens
(Google API pricing, image generation pricing) can be declined from it later by
writing a declaration, not an implementation.

## 2. Verified foundations

Every row below was measured, not assumed. Probes ran against the dev database,
the production database (read-only), and **real Microsoft Excel** installed on the
development workstation.

| Fact | Evidence |
|---|---|
| `openpyxl 3.1.5` is already a runtime dependency | `requirements.txt:162` (RAG text extraction) — no new dependency |
| Cross-sheet dropdowns work via defined names **and** direct references | Written, reopened in Excel: `Type=3`, `Formula1='=LST_PROVIDER'`, `InCellDropdown=True` |
| Excel opens the generated file without repair | Prototype **and** real-scale (124 models): no repair dialog, no repair log |
| Excel-saved files stay readable by our parser | Edited in Excel then reopened: 7 validations, hidden referential sheet, hidden technical row, protection and freeze panes all survived |
| A formula typed in Excel returns as a string | `'=0.1+0.2'` — so formulas are rejectable deterministically |
| A price typed as text returns as text | `'0,7'` — coercion is mandatory, not theoretical |
| `max_row` is inflated by pre-formatting | 500 for 4 data rows — no count may ever be derived from it |
| `data_only=True` returns `None` on a never-opened-by-Excel file | Parser must use `data_only=False` |
| `DECIMAL(10,6)` round-trips losslessly through float | Verified to `9999.999999`; openpyxl writes `%.15g`, absorbing binary artefacts |
| Full-scale round-trip fidelity | 124 real models: **0 parse errors, 0 fidelity gaps**, 16 KB, 31 ms write / 22 ms read → synchronous processing, no background job |
| **Idempotence** — an untouched export, re-imported, changes nothing | 27-column workbook built from real data: 0 creations, 0 capability/tariff/window changes, 0 (de)activations, **124 unchanged, 0 errors** |
| **Sensitivity** — a hand-edited file yields exactly the expected plan | 5 injected edits → 5 detected and correctly classified (1 creation, 1 capability, 1 price, 1 window removal, 1 deactivation), 120 unchanged, **no false positive, no false negative** |
| The 27-column contract holds in Excel | 5 sheets, 27 columns, **0 locking discrepancies** (6 editable columns unlocked, 5 read-only locked), 6 working dropdowns incl. `reasoning_template`; a real write is accepted on an editable cell and refused on a read-only one |
| Partial unique indexes install on real data | After collapsing identical duplicates, both indexes create successfully |
| Existing write paths survive the constraint | `create_currency_rate`, `sync_currency_rates`, `LLMModelService.update` all pass; SQL order verified (UPDATE before INSERT) |
| The constraint actually bites | A naive bulk insert without deactivation is blocked with `IntegrityError` |

### 2.1 Two openpyxl traps that must stay pinned by tests

- **`sheetProtection` booleans are inverted.** `ws.protection.sheet = True` alone emits
  `insertRows="1" autoFilter="1" sort="1" formatCells="1"`, where `1` means *blocked*.
  It would forbid inserting a row — i.e. forbid **adding a model**, a core requirement.
  Each must be explicitly set to `False`. Verified in Excel: `AllowInsertingRows: True`.
- **`showDropDown` is inverted.** `showDropDown=True` **hides** the in-cell arrow.
  A well-meaning "fix" of this boolean would silently remove every dropdown.
  A test asserts the emitted XML, never the intuition.

### 2.2 Sheet protection and collapsible column groups are incompatible

Column outlining works in the file (`OutlineLevel=2`, blocks pre-collapsed), but a
protected sheet opens with `EnableOutlining = False`: the outline symbols are inert,
and the property cannot be persisted without VBA (excluded — we ship macro-free
`.xlsx`). **Decision: keep protection, drop collapsible groups.** Column count is
managed by deliberate block ordering, a colour-coded label row, frozen key column,
autofilter, and calibrated widths. This is a reversible trade-off, recorded here.

## 3. Pre-existing defects that this work must not build upon

Five defects were found while validating the design. None was introduced by it; three
make the export semantically impossible, and two make it dishonest.

### F1 — "The" active tariff is neither unique nor deterministic

No `UNIQUE(model_id) WHERE is_active` constraint exists, and four read paths select
without `ORDER BY`: `pricing_cache.refresh_from_database` (dict overwrite — last row
wins), `AsyncPricingService._query_model_pricing`, `LLMModelService._get_active_pricing`,
`get_active_currency_rate`.

Measured in dev: 96 of 114 active models carry ≥2 active tariffs. Runtime probe on
`gemini-2.5-flash-preview-tts`, same database, same instant:

```
cache path              -> 0.30 / 2.50
AsyncPricingService     -> 0.50 / 10.00      (factor 4 on output)
scribe_v2               -> cache keeps per_1m_tokens, .first() keeps per_audio_hour
```

Production carries **0 duplicates** — the risk is latent there, not materialised.
Root cause: `llm_pricing_seed.sql` inserts with `ON CONFLICT (model_id, effective_from)
DO NOTHING` without deactivating pre-existing active rows, and `create_currency_rate`
deactivates only `.first()` of N.

**This is not history-keeping.** History already works and does not use `is_active`:
`get_model_price_at_date` orders by `effective_from DESC` and ignores the flag entirely.
`is_active` designates the *current* tariff, and `LLMModelService.update` explicitly sets
`current.is_active = False` before inserting. Volumes confirm it: 248 rows, **206 active**,
only 42 historical.

### F2 — Active models with no active tariff are billed zero, silently

`get_cached_cost_usd_eur` returns `(0.0, 0.0)` on a cache miss. Production: **9 active
models** with no tariff — 4 are local Ollama models (zero is legitimate), but 5 are paid
(2 dated Claude models, 3 Perplexity models).

### F3 — The pricing cache is keyed by raw name and read by normalised name

`refresh_from_database` stores `models[pricing.model.model_name]` (raw), while
`get_cached_cost_usd_eur` looks up `normalize_model_name(model)`. Measured **in production**:

```
gpt-4o-2024-05-13   own tariff  : 5.00 / 15.00
                    tariff applied : 2.50 / 10.00   (gpt-4o's)
```

A factor-2 under-billing on input and 1.5 on output, today. Its own tariff row is
unreachable by any path. `claude-3-5-haiku-20241022` and `claude-3-5-sonnet-20241022`
normalise to names that do not exist → billed zero. Models suffixed `-09-2025` are
**not** affected (the `-MMDD` strip is guarded to `tts-` prefixed names).

Without a fix, the export would display a price the system does not apply.

### F4 — A cached price cannot be cleared to NULL

`ModelPriceUpdate(cached_input_unit_price=None).model_dump(exclude_unset=True,
exclude_none=True)` yields `{}`. 73 of 206 active rows have this field NULL. An admin
emptying that cell would see the old value silently preserved — the exact trap ADR-223
documented for `time_slots` ("omitted = inherit, `[]` = clear, never null").

### F5 — The update contract cannot express `is_active`, `provider`, `effective_from`, `effort_values`

`deactivate` exists; **no reactivation path exists anywhere**. `provider` is absent from
`_CAPABILITY_FIELDS`. There is no scheduled-tariff capability.

### Treatment (arbitrated by the owner)

| Defect | Treatment |
|---|---|
| F1 | **Lot 0**, extended to `currency_exchange_rates` |
| F2 | Surfaced as a read-only diagnostic column in the export |
| F3 | **Lot 0**: exact-name lookup first, normalised-name fallback, on both read paths |
| F4 | Lot 1: explicit clear semantics in the import service |
| F5 | Lot 1: build reactivation; the other three become read-only columns |

Currency rates are **not** carried by the workbook: `USD→EUR` is fed daily at 03:00 UTC
by `sync_currency_rates` from `api.frankfurter.dev/v1` (ECB data), so a manual entry
would be overwritten. `EUR→USD` and `USD→USD` are read by no code path — dead data,
deactivated by the Lot 0 migration.

## 4. Lot 0 — the prerequisite migration

Alembic revision, `down_revision = "5d6e7f8a9b0c"`.

**Collapse only what is provably identical.** A migration never invents a price.

| Table | Identical duplicates (auto-collapsed) | Divergent (human arbitration) |
|---|---|---|
| `llm_model_pricing` | 92 | **4** |
| `currency_exchange_rates` | 2 pairs | 0 |

**Why automatic selection is forbidden**: the intuitive "keep the most recent
`effective_from`" rule was tested against the 4 divergent cases and is **wrong in 4 out
of 4**, verified against production:

| Model | Production (authority) | "Most recent" | |
|---|---|---|---|
| gemini-2.5-flash-preview-tts | 0.30 / 2.50 | 0.50 / 10.00 | wrong |
| gemini-2.5-pro-preview-tts | 1.25 / 10.00 | 1.00 / 20.00 | wrong |
| scribe_v1 | `per_audio_hour` | `per_1m_tokens` | wrong **unit** |
| scribe_v2 | `per_audio_hour` | `per_1m_tokens` | wrong **unit** |

Steps:

1. A pre-flight audit script lists divergent duplicates with every candidate row.
   Resolution is explicit and recorded; for the 4 dev cases it is alignment on the
   production values above.
2. The migration collapses strictly identical duplicates (lossless), and **aborts with
   the list** if any divergent duplicate remains. It never chooses.
3. `CREATE UNIQUE INDEX ... ON llm_model_pricing (model_id) WHERE is_active`
   and `... ON currency_exchange_rates (from_currency, to_currency) WHERE is_active`.
4. Deterministic `ORDER BY effective_from DESC, id DESC` on the four read paths.
5. F3 fix: try the exact model name first, fall back to the normalised name, on both
   `pricing_cache` and `AsyncPricingService`. The documented intent (a dated model
   inherits its base model's tariff) is preserved; an explicit per-version tariff is
   finally honoured.
6. `create_currency_rate`: replace `.first()` with a bulk deactivation and add an
   **explicit `flush()`**. The current UPDATE-before-INSERT ordering was verified in the
   emitted SQL, but the invariant must not rest on undocumented unit-of-work ordering.
7. `llm_pricing_seed.sql`: deactivate before inserting.
8. `tests/helpers/llm_helpers.py`: deactivate the previous active row. No existing test
   creates two active tariffs for one model (verified), so no test-suite fallout expected.

In production the collapse is a no-op (0 duplicates measured).

## 5. Architecture

### Layer A — the generic foundation, `src/infrastructure/tabular_io/`

Imports no domain module, so it adds no cycle (F009 ratchet).

| Module | Responsibility |
|---|---|
| `spec.py` | `WorkbookSpec`, `SheetSpec`, `ColumnSpec`, `ColumnKind` (`text`/`integer`/`decimal`/`boolean`/`enum`/`enum_list`/`time_hhmm`), `ReferentialList`, per-column `editable` flag |
| `writer.py` | `build_workbook(spec, data, lang) -> bytes` — notice, referentials, dropdowns, protection, formats, freeze, autofilter |
| `reader.py` | `parse_workbook(spec, content) -> ParsedWorkbook` — zip guards, key-based column resolution, typed coercion, cell-located errors |
| `report.py` | `CellIssue`, `IssueCode`, `SheetParseResult` — codes and parameters, never pre-translated strings |

### Layer B — the domain declaration, `src/domains/llm/pricing_sheet.py`

Declares the sheets and builds referential lists **from the enums**
(`LLMProviderEnum`, `LLMModelKindEnum`, `PricingUnitEnum`), never from the values
present in the data — otherwise a provider never used yet would be missing from the
dropdown. A test pins this.

### Layer C — the application service, `src/domains/llm/pricing_import_service.py`

Diff → typed `ChangePlan` → transactional application through `LLMModelService`.
Where the existing contract cannot express an operation (F4 clear, F5 reactivation),
the service is **extended**, never bypassed.

Declining to another administration later = writing a Layer B declaration and a Layer C
applier. Layer A does not move.

## 6. The workbook

| Sheet | Content |
|---|---|
| **Notice** | Usage guide in the admin's language: what is editable, `is_active` semantics, price format, what is never deleted |
| **Modèles** | One row per model — full characteristic matrix (§6.1) |
| **Plages horaires** | One row per UTC window: `model_name`, `start_utc`, `end_utc`, three prices |
| **Référentiels** | Hidden and locked; feeds the dropdowns |
| **Métadonnées** | Schema version, per-row fingerprints, export timestamp, author |

Row 1 carries invariant technical keys (hidden); row 2 carries translated labels; data
starts at row 3. **Columns are resolved by key, never by position** — reordering or
hiding columns in Excel is harmless, and changing UI language between export and import
changes nothing.

### 6.1 Column coverage — the completeness rule

The earlier prototype exported 16 columns against a real schema of 24 + 11. The gap was
invisible to the first fidelity test because that test compared the extraction to
**itself** — a circular oracle. The corrected rule:

> Every business column of `llm_models` and `llm_model_pricing` is either exported, or
> excluded with a written reason. A test derives the column list from the model metadata
> and fails when a column is neither covered nor declared excluded.

This mirrors the boot-time registry completeness asserts (ADR-085): a column added
tomorrow reddens CI until it is handled.

| Block | Columns | Editable |
|---|---|---|
| Identity | `model_name` (key), `provider`, `kind` | yes (`provider` at creation only) |
| State | `is_active` | yes — deactivation **and** reactivation |
| Capabilities | `max_input_tokens`, `max_output_tokens`, `supports_tools`, `supports_structured_output`, `supports_strict_mode`, `supports_streaming`, `supports_vision` | yes |
| Sampling | `supports_temperature`, `supports_top_p`, `supports_frequency_penalty`, `supports_presence_penalty` | yes |
| Reasoning | `reasoning_template` (dropdown), `reasoning_shape` (read-only summary of widget + enum values + budget range), `reasoning_doc_i18n_key`, `effort_values` (read-only) | template + doc key |
| Pricing | `pricing_unit`, `input_unit_price`, `cached_input_unit_price`, `output_unit_price`, `effective_from` (read-only) | prices + unit |
| Time slots | `time_slots_mode`, `time_slots_summary` (read-only) | mode |
| Diagnostics | `statut` (read-only) | no |

Excluded with reason: `id`, `model_id`, `created_at`, `updated_at` (technical identity
and audit timestamps, meaningless to edit).

`reasoning_template` covers only 4 of the reasoning fields, and it is **not total**:
`deepseek-reasoner` matches none of the 16 templates, which are built from active models
only. Hence the read-only `reasoning_shape` column — the file stays complete and
self-describing, and an unmatched model is flagged rather than mis-assigned.

### 6.2 Making the tariff legible — the DeepSeek lesson

Owner review of the prototype reported "the DeepSeek time slots are missing". The data
was present (4 rows in the Plages sheet), but the main sheet showed only the base prices
`0.22 / 0.66` with a discreet `time_slots_mode = windows` lost among 16 columns. A
reader concludes "flat pricing". The information existed where the eye does not look.

Consequences for the design:

- `time_slots_summary` is a read-only column stating the reality in place:
  `2 fenêtres : 01:00–04:00, 06:00–10:00`.
- When a row is windowed, the base price labels read **"hors plage"**, so the number is
  never mistaken for the only price.
- `time_slots_mode` **exports the actual state** (`flat` or `windows`), never `inherit`.
  A file must say what *is*; `inherit` remains accepted as an input value meaning
  "leave untouched".
- `statut` names, in plain words, what the diagnostics found: `aucun tarif actif`,
  `plusieurs tarifs actifs`, `facturé sous <autre nom>`.

## 7. Import rules

1. **Key = `model_name`.** Absent in database → creation; present → update.
2. **A row absent from the file changes nothing.** Never a deletion.
3. **`is_active = FAUX`** deactivates (soft delete, cost history preserved);
   **`TRUE` on an inactive model** reactivates.
4. **Tariff written only on a real change.** Identical prices, unit and windows → no
   write at all. Otherwise a new active version is inserted and the previous one becomes
   history (its end being, implicitly, the new one's `effective_from`). Without this
   rule a 124-row import would create 124 useless versions.
5. **An emptied cached-price cell means NULL**, expressed explicitly by the import
   service (F4).
6. **Time slots** follow `time_slots_mode`: `windows` (the Plages sheet is authoritative),
   `flat` (clear — the `[]` of ADR-223), `inherit` (untouched).
7. **All or nothing.** One transaction; any blocking error writes nothing.
8. **Preview is mandatory.** `dry_run=true` returns the full plan — creations,
   field-by-field before→after modifications, deactivations, reactivations, unchanged
   rows, errors. Application recomputes the plan and refuses if it differs from the
   previewed one, plus an idempotency key against double submission — so a preview is
   never a lie.
9. **Per-row optimistic lock.** Only rows changed underneath the admin are refused, not
   the whole file.
10. **A `provider` change on an existing model is reported as an error**, never silently
    dropped.
11. A pre-import snapshot of the current state is attached to the report, as the
    revert path.

## 8. Robustness and security

| Guard | Defect it closes |
|---|---|
| `data_only=False` + rejection of every formula cell | Cached values absent from a never-opened file |
| Fully-empty rows skipped; no count derived from `max_row` | `max_row` = 500 for 4 data rows |
| `Decimal(str(float))`, refusal beyond 6 decimals | `DECIMAL(10,6)` domain |
| Coercion: decimal comma, non-breaking space, padding, case, localised booleans | Cells really read as `'0,7'`, `' gpt-4.1 '` |
| **An empty string and `None` are the same value** for text columns, on both sides | Measured at 27 columns: a written `""` comes back as an empty cell, i.e. `None` — 122 spurious differences until normalised. Left unhandled on an editable text column, clearing a cell would report a phantom change |
| Size cap **and** uncompressed-size cap, bounded chunked read | `BadZipFile`; 20× compression ratio on realistic content |
| `neutralize_formula` on export | Formula injection into a file opened by a third party |
| Superuser only, rate limit, `AdminAuditLog` entry, cache invalidation after import | Existing admin contract |

Sheet protection carries **no password**: it is bypassed in seconds and would only create
false confidence and admin friction. It guards against accidental edits — verified in
Excel: a locked header rejects writes, unlocked data cells accept them.

## 9. API surface

- `GET /admin/llm/pricing/export.xlsx` → the workbook.
- `POST /admin/llm/pricing/import?dry_run=true|false` (multipart) → `PricingImportReport`.

Report codes are structured (`IssueCode` + parameters) and translated client-side, per
the frontend contract.

## 10. Frontend

A dedicated `AdminPricingSheetPanel` component — `AdminLLMPricingSection.tsx` is already
1624 lines and receives no structural addition. Its header bar is currently hand-rolled
(two raw `<Button>` in a flex) and must migrate to `SectionToolbar` (ADR-208): adding
Export and Import as two more raw buttons would stack four buttons on phones. Primary =
add model; pinned = export; folded = import and cache reload.

The preview screen is the heart of the experience: grouping by change nature
(creations / tariff changes / deactivations / reactivations / unchanged / errors),
collapsed by default with counts, only changed fields shown as before→after, errors
first with sheet and cell coordinates, and an honest degraded layout on phones.

Six-locale key parity, `useLLMPricingSheet.ts` hook, FormData upload following
`usePlugins.ts`.

## 11. Testing strategy

- **Foundation**: round-trip, emitted-XML assertions for the two inverted openpyxl flags,
  coercions, empty rows, reordered/missing/extra columns, invalid zip, caps.
- **Completeness guard**: every business column covered or declared excluded (§6.1).
- **Domain**: the eleven import rules, dry-run ≡ application, atomicity on error,
  optimistic lock, reactivation, the three time-slot modes, NULL clearing.
- **Lot 0**: migration replay, collapse of identical duplicates, abort on divergent ones,
  the three existing write paths under the constraint, F3 resolution on dated names.
- **Router**: superuser guard, headers, error taxonomy.
- **Frontend**: report rendering, keyboard path, a11y, i18n.

## 12. Known limitations, stated in the Notice

- `provider` cannot change on an existing model; `effective_from` is not editable
  (no scheduled tariffs); `effort_values` is read-only (no API path).
- A brand-new reasoning family cannot be created from the spreadsheet — custom mode
  stays in the admin dialog. The import rejects it explicitly rather than guessing.
- Only Microsoft Excel on Windows has been validated. LibreOffice, Google Sheets and
  Excel for Mac use standard OOXML constructs and should behave identically, but this
  has not been measured.
- Collapsible column groups are unavailable while the sheet is protected (§2.2).
