# Tabular Admin Import/Export — Implementation Plan

> **For agentic workers:** this plan is executed **inline, without subagents** (owner directive). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give administrators a round-trip through a structured Excel workbook to read and bulk-edit the whole LLM model catalogue and its tariffs, on a generic foundation reusable by other administration screens.

**Architecture:** Three layers — a domain-agnostic spreadsheet engine in `src/infrastructure/tabular_io/` (declarative sheet spec, writer, reader, issue report), a declaration in `src/domains/llm/pricing_sheet.py`, and an application service `src/domains/llm/pricing_import_service.py` that diffs the parsed workbook against the database and applies the plan through `LLMModelService`. A prerequisite lot (Lot 0) makes "the active tariff" unique and deterministic, and repairs two live billing defects, because the export has no meaning without it.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Pydantic 2, Alembic, openpyxl 3.1.5 (already a runtime dependency), Next.js 16 / React 19 / vitest.

**Spec:** `docs/superpowers/specs/2026-08-18-tabular-admin-io-design.md`

## Global Constraints

- **Reuse before writing.** `neutralize_formula` (`domains/document_generation/sanitize.py`), `PluginImportReport` shape, `SectionToolbar` (ADR-208), `useApiQuery`/`useApiMutation`, `AdminAuditLog`, `_invalidate_caches`. The zip-budget guard is **extracted and shared**, never duplicated.
- **600 logical SLOC** cap per file (`scripts/audit/measure_sloc.py` semantics); cyclomatic complexity **< 15** per function.
- **MyPy strict**, full type hints, Google-style docstrings, module docstring on every file. Documentation and comments in **English**.
- **structlog only**, never `print()`. No PII at INFO.
- **No raw `HTTPException`** — centralized raisers. Tools/reports return codes, never pre-translated strings.
- **i18n: 6 locales** (en, fr, de, es, it, zh), strict key parity enforced by the pre-commit hook. `zh` duplicates `_one`/`_other`.
- **Timezone-aware UTC** only (`datetime.now(UTC)`).
- **No JSONB in-place mutation** — always reassign a new dict.
- **Ratchets are shrink-only**; raise floors after improving, never to absorb a regression.
- **Never `--no-verify`.** No git action without explicit owner request.
- Prices are `DECIMAL(10,6)`; **max 6 decimals**, values `>= 0`.
- Referential lists are built **from the enums**, never from the values present in the data.
- Empty string and `None` are **the same value** for text columns, on both write and read.

---

## Lot 0 — Determinism and billing correctness

Prerequisite: without a unique active tariff, "export the tariff" has no referent. Two live billing defects are repaired here because the export would otherwise display prices the system does not apply.

### Task 0.1: Deterministic resolution of the active tariff

**Files:**
- Modify: `apps/api/src/infrastructure/cache/pricing_cache.py` (`refresh_from_database`)
- Modify: `apps/api/src/domains/llm/pricing_service.py` (`_query_model_pricing`, `get_active_currency_rate` → `_query_currency_rate`)
- Modify: `apps/api/src/domains/llm/service.py` (`_get_active_pricing`)
- Test: `apps/api/tests/unit/domains/llm/test_pricing_resolution.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: the invariant "when several active rows exist, the one with the greatest `(effective_from, id)` wins" — Lot 0.4 relies on it to pick the survivor.

- [ ] **Step 1: Write the failing tests**

Two models with two active pricing rows each; assert every read path returns the most recent one, and that the four paths agree with each other.

- [ ] **Step 2: Run and verify they fail**

`cd apps/api && .venv/Scripts/pytest tests/unit/domains/llm/test_pricing_resolution.py -v`

- [ ] **Step 3: Add `ORDER BY effective_from DESC, id DESC` to the four queries**

- [ ] **Step 4: Run the tests, then the whole llm suite**

`.venv/Scripts/pytest tests/unit/domains/llm -v`

### Task 0.2: Exact-name-first tariff lookup (defect F3)

**Files:**
- Modify: `apps/api/src/infrastructure/cache/pricing_cache.py` (`get_cached_cost_usd_eur`, `get_cached_cost_audio_usd_eur`)
- Modify: `apps/api/src/domains/llm/pricing_service.py` (`_query_model_pricing`)
- Test: `apps/api/tests/unit/domains/llm/test_pricing_resolution.py`

**Interfaces:**
- Produces: `resolve_priced_name(raw: str, has: Callable[[str], bool]) -> str | None` — a single shared helper so both paths cannot diverge again.

Measured defect: the cache is keyed by the raw `model_name` but read by `normalize_model_name(...)`. In production `gpt-4o-2024-05-13` owns a 5.00/15.00 tariff yet is billed 2.50/10.00 (`gpt-4o`'s).

- [ ] **Step 1: Write the failing tests** — a dated model with its own tariff bills its own price; a dated model without one falls back to the base model; a model with neither yields zero.
- [ ] **Step 2: Run and verify failure**
- [ ] **Step 3: Implement the shared helper and use it on both paths**
- [ ] **Step 4: Run tests + `test_pricing_cost_computation.py` for non-regression**

### Task 0.3: `create_currency_rate` deactivates every active row

**Files:**
- Modify: `apps/api/src/domains/llm/router.py:613-635`
- Test: `apps/api/tests/unit/domains/llm/test_router.py`

Root cause of the duplicate rates: `.scalars().first()` deactivates only one of N. Replace with a bulk `update(...).values(is_active=False)` followed by an **explicit `flush()`**, so the invariant never rests on undocumented unit-of-work ordering.

- [ ] **Step 1: Failing test** — three active rows for one pair; creating a fourth leaves exactly one active.
- [ ] **Step 2: Verify failure**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Verify pass**

### Task 0.4: Migration — collapse, guard, constrain

**Files:**
- Create: `apps/api/alembic/versions/2026_08_18_1400-6e7f8a9b0c1d_unique_active_pricing_and_rate.py`
- Create: `apps/api/tests/unit/domains/llm/test_active_uniqueness_migration.py`

`down_revision = "5d6e7f8a9b0c"`.

`upgrade()`:
1. Collapse **strictly identical** duplicates only — same `(input, cached_input, output, pricing_unit, time_slots)` for pricing; same `rate` for currency. Keep the greatest `(effective_from, id)`, flip the others to `is_active = false`.
2. **Abort** with a listing if any divergent duplicate remains. The migration never chooses between different prices — verified: the intuitive "most recent" rule is wrong in 4 of 4 real cases.
3. Deactivate the dead currency pairs read by no code path (`EUR→USD`, `USD→USD`).
4. `CREATE UNIQUE INDEX uq_llm_model_pricing_active ON llm_model_pricing (model_id) WHERE is_active;`
5. `CREATE UNIQUE INDEX uq_currency_rate_active ON currency_exchange_rates (from_currency, to_currency) WHERE is_active;`

`downgrade()` drops both indexes (the collapse is not reverted — reactivating known-duplicate rows would restore the defect).

- [ ] **Step 1: Write the tests** — identical duplicates collapse losslessly; a divergent duplicate raises; the index rejects a second active row; `LLMModelService.update` still passes under the constraint.
- [ ] **Step 2: Verify failure**
- [ ] **Step 3: Write the migration**
- [ ] **Step 4: Run tests + `task db:migrate:replay-check`**

### Task 0.5: Close the sources of duplication

**Files:**
- Modify: `infrastructure/database/seeds/llm_pricing_seed.sql`
- Modify: `apps/api/tests/helpers/llm_helpers.py`

The seed inserts with `ON CONFLICT (model_id, effective_from) DO NOTHING` without deactivating pre-existing active rows; the test helpers create an active row unconditionally. Both must deactivate first, or the constraint added in 0.4 turns them into failures.

- [ ] **Step 1: Add a deactivating statement before the pricing INSERT in the seed**
- [ ] **Step 2: Make `create_llm_pricing_async` / `create_llm_pricing_entry` deactivate the model's active row first**
- [ ] **Step 3: Run the integration suites that use them**
- [ ] **Step 4: Re-seed the dev database and check `statut` diagnostics**

---

## Lot 1 — The generic foundation

### Task 1.1: Extract the shared zip-budget guard (factorisation)

**Files:**
- Create: `apps/api/src/infrastructure/archives/zip_budget.py`
- Modify: `apps/api/src/domains/plugins/staging.py` (`_enforce_zip_budgets` delegates)
- Test: `apps/api/tests/unit/infrastructure/archives/test_zip_budget.py` (create)

**Interfaces:**
- Produces:
  ```python
  class ZipBudgetExceeded(ValueError):
      reason: Literal["too_many_files", "decompressed_too_large"]
      limit: int
      measured: int

  def enforce_zip_budgets(
      infos: Sequence[zipfile.ZipInfo], *, max_files: int, max_decompressed_bytes: int
  ) -> None
  ```

Plugins keep their own message translation by catching `ZipBudgetExceeded`; behaviour is unchanged, the guard has one implementation.

- [ ] **Step 1: Failing tests** — under budget passes; too many members raises with `reason="too_many_files"`; oversized decompressed raises.
- [ ] **Step 2: Verify failure**
- [ ] **Step 3: Implement and make plugins delegate**
- [ ] **Step 4: Run plugin tests for non-regression**

### Task 1.2: Declarative sheet specification

**Files:**
- Create: `apps/api/src/infrastructure/tabular_io/__init__.py`
- Create: `apps/api/src/infrastructure/tabular_io/spec.py`
- Test: `apps/api/tests/unit/infrastructure/tabular_io/test_spec.py`

**Interfaces:**
- Produces:
  ```python
  ColumnKind = Literal["text", "integer", "decimal", "boolean", "enum", "enum_list", "time_hhmm"]

  @dataclass(frozen=True)
  class ColumnSpec:
      key: str; label_key: str; kind: ColumnKind
      editable: bool = True; required: bool = False
      referential: str | None = None; decimals: int | None = None
      minimum: Decimal | None = None; block: str = "default"; width: int = 18

  @dataclass(frozen=True)
  class SheetSpec:
      name: str; title_key: str; columns: tuple[ColumnSpec, ...]; key_column: str

  @dataclass(frozen=True)
  class WorkbookSpec:
      sheets: tuple[SheetSpec, ...]
      referentials: Mapping[str, tuple[str, ...]]
      notice_lines_key: str; schema_version: int
  ```

- [ ] **Step 1: Failing tests** — a spec rejects a duplicate column key, an unknown referential, a `key_column` absent from the columns.
- [ ] **Step 2: Verify failure**
- [ ] **Step 3: Implement with `__post_init__` validation**
- [ ] **Step 4: Verify pass**

### Task 1.3: Workbook writer

**Files:**
- Create: `apps/api/src/infrastructure/tabular_io/writer.py`
- Test: `apps/api/tests/unit/infrastructure/tabular_io/test_writer.py`

**Interfaces:**
- Produces: `build_workbook(spec: WorkbookSpec, data: Mapping[str, Sequence[Mapping[str, Any]]], *, notice: Sequence[str], metadata: Mapping[str, str], labels: Mapping[str, str]) -> bytes`

Two inverted openpyxl behaviours must be pinned by assertions on the **emitted XML**, not by intuition:
- `sheetProtection` booleans mean "blocked" when `1`; `autoFilter`, `sort`, `insertRows`, `deleteRows`, `formatCells`, `formatColumns`, `formatRows` must all be written `0` or adding a model becomes impossible.
- `showDropDown="1"` **hides** the in-cell arrow; it must be written `0`.

- [ ] **Step 1: Failing tests** — emitted XML carries `insertRows="0"` and `showDropDown="0"`; read-only columns are locked and editable ones unlocked; row 1 carries technical keys and is hidden; referential sheet hidden; freeze panes on the key column; `neutralize_formula` applied to text values; empty string written as an empty cell.
- [ ] **Step 2: Verify failure**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Verify pass**

### Task 1.4: Workbook reader

**Files:**
- Create: `apps/api/src/infrastructure/tabular_io/report.py`
- Create: `apps/api/src/infrastructure/tabular_io/reader.py`
- Test: `apps/api/tests/unit/infrastructure/tabular_io/test_reader.py`

**Interfaces:**
- Produces:
  ```python
  class IssueCode(str, Enum):
      NOT_A_WORKBOOK = "not_a_workbook"; SHEET_MISSING = "sheet_missing"
      COLUMN_MISSING = "column_missing"; FORMULA_REJECTED = "formula_rejected"
      NOT_A_NUMBER = "not_a_number"; TOO_MANY_DECIMALS = "too_many_decimals"
      OUT_OF_RANGE = "out_of_range"; NOT_A_BOOLEAN = "not_a_boolean"
      VALUE_NOT_IN_REFERENTIAL = "value_not_in_referential"; KEY_MISSING = "key_missing"
      DUPLICATE_KEY = "duplicate_key"; TOO_MANY_ROWS = "too_many_rows"
      SCHEMA_VERSION_MISMATCH = "schema_version_mismatch"

  @dataclass(frozen=True)
  class CellIssue:
      code: IssueCode; sheet: str; cell: str | None; column: str | None
      params: Mapping[str, str]

  def parse_workbook(spec: WorkbookSpec, content: bytes, *, max_rows: int,
                     max_files: int, max_decompressed_bytes: int) -> ParsedWorkbook
  ```

Behaviours pinned by tests, each traced to a measured trap:
- loads with `data_only=False`; any cell starting with `=` is `FORMULA_REJECTED` (verified: Excel returns the formula as a string)
- fully-empty rows skipped; **no count derived from `max_row`** (verified: 500 for 4 data rows)
- columns resolved by technical key — reordering, hiding or adding columns is harmless
- coercion: decimal comma, non-breaking space, surrounding spaces, case, localised booleans (verified: cells really return `'0,7'`)
- `""` and `None` are the same value (verified: 122 phantom differences otherwise)
- more than `decimals` decimals → `TOO_MANY_DECIMALS`; negative → `OUT_OF_RANGE`
- non-xlsx payload → `NOT_A_WORKBOOK` (`BadZipFile`); budgets via `enforce_zip_budgets`

- [ ] **Step 1: Write the failing tests (one per behaviour above)**
- [ ] **Step 2: Verify failure**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Verify pass**

---

## Lot 2 — Domain declaration and import service

### Task 2.1: The LLM pricing sheet declaration

**Files:**
- Create: `apps/api/src/domains/llm/pricing_sheet.py`
- Test: `apps/api/tests/unit/domains/llm/test_pricing_sheet.py`

27 columns per spec §6.1, in blocks: identity, state, capabilities, sampling, reasoning, pricing, time slots, diagnostics. Referentials built from `LLMProviderEnum`, `LLMModelKindEnum`, `PricingUnitEnum` and the reasoning templates.

**Completeness guard** (spec §6.1, doctrine of ADR-085): a test walks `LLMModel.__table__.columns` and `LLMModelPricing.__table__.columns` and fails when a column is neither exported nor listed in an `EXCLUDED_COLUMNS` mapping carrying a written reason.

- [ ] **Step 1: Failing tests** — completeness guard; referentials equal the enum values, not the values present in data.
- [ ] **Step 2: Verify failure**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Verify pass**

### Task 2.2: Export row builder

**Files:**
- Create: `apps/api/src/domains/llm/pricing_sheet_rows.py`
- Test: `apps/api/tests/unit/domains/llm/test_pricing_sheet_rows.py`

**Interfaces:**
- Produces: `async def build_export_rows(db: AsyncSession) -> ExportPayload` with `models`, `slots`, `fingerprints`.

Derived read-only columns: `reasoning_shape`, `time_slots_summary` (`"2 fenêtres : 01:00–04:00, 06:00–10:00"`), `effective_from`, and `statut` naming the diagnostics in order of severity — `aucun tarif actif`, `N tarifs actifs`, `facturé sous <autre nom>`, `ok`. `time_slots_mode` exports the **actual state** (`flat` / `windows`), never `inherit`.

- [ ] **Step 1: Failing tests** — the four `statut` values; the windowed summary; a model without a tariff exports empty prices and its status; `reasoning_template` falls back to a marker when no template matches (verified: `deepseek-reasoner`).
- [ ] **Step 2: Verify failure**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Verify pass**

### Task 2.3: The diff engine

**Files:**
- Create: `apps/api/src/domains/llm/pricing_change_plan.py`
- Test: `apps/api/tests/unit/domains/llm/test_pricing_change_plan.py`

**Interfaces:**
- Produces:
  ```python
  @dataclass(frozen=True)
  class FieldChange: field: str; before: str | None; after: str | None
  @dataclass(frozen=True)
  class ModelChange:
      model_name: str
      action: Literal["create", "update", "deactivate", "reactivate", "unchanged"]
      fields: tuple[FieldChange, ...]; slots_before: int; slots_after: int
  @dataclass(frozen=True)
  class ChangePlan:
      changes: tuple[ModelChange, ...]; issues: tuple[CellIssue, ...]
      def fingerprint(self) -> str  # stable hash, guards preview → apply coherence
  ```

Two properties proven by simulation on the real catalogue and now pinned as tests:
- **idempotence** — an untouched export re-imported yields every row `unchanged` and zero issue (measured: 124/124)
- **sensitivity** — five injected edits yield exactly five changes, correctly classified, no false positive or negative

Rules: read-only columns ignored; a row absent from the file produces nothing; a `provider` change on an existing model is an issue, never a silent drop.

- [ ] **Step 1: Write the failing tests, including the two properties above**
- [ ] **Step 2: Verify failure**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Verify pass**

### Task 2.4: Service extensions — reactivation and explicit clearing

**Files:**
- Modify: `apps/api/src/domains/llm/service.py`
- Modify: `apps/api/src/domains/llm/schemas.py`
- Test: `apps/api/tests/unit/domains/llm/test_service.py`

Two capabilities the current contract cannot express, both measured:
- **Reactivation**: `deactivate` exists, nothing reverses it. Add `async def reactivate(self, model_name: str) -> tuple[LLMModel, LLMModelPricing | None]` which flips the model active and reactivates its most recent pricing row, or reports that none exists.
- **Explicit clearing**: `ModelPriceUpdate(cached_input_unit_price=None)` dumps to `{}` because of `exclude_none=True`. Add a `PricingClear` sentinel set carried alongside the payload so "empty cell" reaches the write path — same doctrine as ADR-223's `[]` for `time_slots`.

- [ ] **Step 1: Failing tests** — reactivate an inactive model; reactivate one with no pricing row; clear a cached price to NULL and read it back as NULL.
- [ ] **Step 2: Verify failure**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Verify pass**

### Task 2.5: Transactional application

**Files:**
- Create: `apps/api/src/domains/llm/pricing_import_service.py`
- Test: `apps/api/tests/unit/domains/llm/test_pricing_import_service.py`

**Interfaces:**
- Produces: `async def apply(self, plan: ChangePlan, *, actor_id: UUID) -> ImportOutcome`

All-or-nothing in one transaction, through `LLMModelService` only. A tariff is written **only on a real change** — otherwise a 124-row import would create 124 useless versions. Ends with `AdminAuditLog` and `_invalidate_caches`.

- [ ] **Step 1: Failing tests** — a plan with one blocking issue writes nothing; an unchanged plan writes nothing at all (no new pricing row); a price change creates exactly one new active row and deactivates the previous; the audit entry and cache invalidation happen once.
- [ ] **Step 2: Verify failure**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Verify pass**

---

## Lot 3 — API surface

### Task 3.1: Export endpoint

**Files:**
- Modify: `apps/api/src/domains/llm/router.py`
- Test: `apps/api/tests/unit/domains/llm/test_router.py`

`GET /admin/llm/pricing/export.xlsx` — superuser only, `StreamingResponse`, RFC 5987 filename, notice and labels resolved in the admin's language.

- [ ] **Step 1: Failing tests** — 403 for a non-superuser; correct content type and disposition; the returned bytes parse back to the catalogue.
- [ ] **Step 2–4: Verify failure, implement, verify pass**

### Task 3.2: Import endpoint

**Files:**
- Modify: `apps/api/src/domains/llm/router.py`
- Create: `apps/api/src/domains/llm/pricing_sheet_schemas.py`
- Test: `apps/api/tests/unit/domains/llm/test_router.py`

`POST /admin/llm/pricing/import?dry_run=true|false` — multipart, size cap read in bounded chunks, superuser only, rate limited.

- [ ] **Step 1: Failing tests** — `dry_run=true` writes nothing and returns the plan; applying with a plan fingerprint that no longer matches is refused; a per-row fingerprint mismatch refuses only that row; a replayed idempotency key returns the first outcome without re-applying; a non-xlsx payload returns `NOT_A_WORKBOOK`; an oversized payload is refused before parsing.
- [ ] **Step 2–4: Verify failure, implement, verify pass**

---

## Lot 4 — Frontend

### Task 4.1: Hook and actions

**Files:**
- Create: `apps/web/src/hooks/useLLMPricingSheet.ts`
- Modify: `apps/web/src/lib/actions/settings-actions.ts`
- Test: `apps/web/src/hooks/__tests__/useLLMPricingSheet.test.ts`

Export via `window.open` (the memory/interests/journals pattern); import via `FormData` following `usePlugins.ts`.

- [ ] **Step 1–4: failing test, verify, implement, verify**

### Task 4.2: Bring the section header to ADR-208

**Files:**
- Modify: `apps/web/src/components/settings/AdminLLMPricingSection.tsx:512-528`
- Test: `apps/web/src/components/settings/__tests__/AdminLLMPricingSection.test.tsx`

The header is hand-rolled (two raw `<Button>` in a flex): adding Export and Import would stack four buttons on phones. Migrate to `SectionToolbar` — primary "add model", pinned "export", folded "import" and "reload cache".

- [ ] **Step 1–4: failing test on the rendered roles and names, verify, implement, verify**

### Task 4.3: Import dialog and change preview

**Files:**
- Create: `apps/web/src/components/settings/AdminPricingSheetDialog.tsx`
- Test: `apps/web/src/components/settings/__tests__/AdminPricingSheetDialog.test.tsx`

A dedicated component — `AdminLLMPricingSection.tsx` is already 1624 lines and takes no structural addition. Two steps: choose file → preview → apply. The preview groups by change nature with counts, collapses unchanged rows, shows only changed fields as before→after, lists issues first with sheet and cell coordinates, and degrades honestly on phones (cards instead of a wide table). `<Button isLoading>` while applying; `aria-busy` on refresh, never an unmount; `aria-disabled` plus a handler guard rather than `disabled` on a focused control.

- [ ] **Step 1–4: failing tests (roles, names, keyboard, empty/error/loading states), verify, implement, verify**

### Task 4.4: Six-locale strings

**Files:**
- Modify: `apps/web/locales/{en,fr,de,es,it,zh}/translation.json`
- Modify: `apps/web/src/lib/settings-search.ts` (search lexicon)

Every `IssueCode` gets a message key; `zh` duplicates plural values.

- [ ] **Step 1: Add the keys to `en`, then the five others**
- [ ] **Step 2: `task lint:i18n`**
- [ ] **Step 3: Update the settings search lexicon and its token count test**
- [ ] **Step 4: `task test:frontend`**

---

## Lot 5 — Documentation, release, deployment

- [ ] Technical documentation `docs/technical/TABULAR_ADMIN_IO.md`, ADR-228, `docs/INDEX.md` and `docs/architecture/ADR_INDEX.md`
- [ ] README (features and metrics), CHANGELOG, application FAQ changelog (end-user/admin wording only), `docs/knowledge/` regenerated from the FAQ
- [ ] Landing pages — features, metrics, Technique (a presentation of design and implementation, **not** a changelog), Story, Philosophie, Encore + — in the 6 locales
- [ ] Version bump to **v1.30.11** everywhere (code, docs, README, CHANGELOG, landing with date and time)
- [ ] `task lint`, `task ci:fast`, ratchets raised after measurement
- [ ] Commit and push (owner request), then `task deploy:prod`, `task demo:prod:down`, `task demo:prod:up`, `task demo:prod:verify`, then the v1.30.11 release

---

## Self-review

**Spec coverage** — §3 defects F1→F5: Lot 0.1 (F1 determinism), 0.2 (F3), 0.3 + 0.4 + 0.5 (F1 root causes and constraint), 2.4 (F4 and F5). §4 migration: 0.4. §5 architecture: 1.2→1.4 (layer A), 2.1→2.2 (layer B), 2.3→2.5 (layer C). §6 workbook: 1.3, 2.1, 2.2. §6.1 completeness guard: 2.1. §6.2 tariff legibility: 2.2. §7 the eleven import rules: 2.3 (rules 1, 2, 3, 4, 6, 10), 2.5 (4, 7), 3.2 (8, 9, 11), 2.4 (5). §8 guards: 1.1, 1.4, 3.2. §9 API: 3.1, 3.2. §10 frontend: 4.1→4.4. §11 tests: distributed across every task. §12 limitations: documented in Lot 5.

**Type consistency** — `ChangePlan.fingerprint()` (2.3) is consumed by 3.2; `enforce_zip_budgets` (1.1) by 1.4; `parse_workbook` (1.4) by 3.2; `build_export_rows` (2.2) by 3.1; `reactivate` (2.4) by 2.5.
