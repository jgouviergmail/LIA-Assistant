"""Declaration of the LLM catalogue workbook (ADR-228).

This module says *what* the workbook contains; the generic foundation
(``infrastructure/tabular_io``) knows *how* to write and read it. Declining the
mechanism to another administration screen means writing a module like this one
— no format code.

Two rules govern the content, both learned the hard way:

- **Completeness is guarded, not remembered.** The per-table ``*_SOURCE_COLUMNS``
  and ``EXCLUDED_*`` maps together cover every column of ``llm_models`` and
  ``llm_model_pricing``; ``test_pricing_sheet.py`` fails when the schema grows a
  column that is neither. A first version of this workbook silently omitted 11
  business columns.
- **Referentials come from the enums**, never from the values present in the
  data — otherwise a provider that exists but has never been used would be
  missing from its own dropdown.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal

from src.domains.llm.models import (
    LLMModelKindEnum,
    LLMProviderEnum,
    LLMReasoningWidgetEnum,
    PricingUnitEnum,
)
from src.infrastructure.tabular_io.spec import ColumnSpec, SheetSpec, WorkbookSpec

#: Bumped whenever the columns change in a way an older file cannot satisfy.
SCHEMA_VERSION = 1

#: Marker written in ``reasoning_template`` when a model's reasoning shape
#: matches none of the existing templates. Reasoning templates are built from
#: *active* models, so an inactive one can legitimately match nothing
#: (``deepseek-reasoner``, measured 2026-08-18).
CUSTOM_TEMPLATE_MARKER = "(custom)"

#: Hidden column carrying each row's fingerprint, for the per-row optimistic lock.
FINGERPRINT_COLUMN = "row_fingerprint"

#: Time-slot intent. The export always writes the actual state — ``flat`` or
#: ``windows`` — never ``inherit``: a file must say what *is*. ``inherit`` stays
#: accepted on import, meaning "leave the windows untouched".
TIME_SLOT_MODES: tuple[str, ...] = ("flat", "windows", "inherit")

_PRICE_SCALE = 6
_ZERO = Decimal("0")


def _column(
    key: str,
    kind: str,
    block: str,
    *,
    editable: bool = True,
    required: bool = False,
    referential: str | None = None,
    decimals: int | None = None,
    minimum: Decimal | None = None,
    width: int = 18,
    hidden: bool = False,
) -> ColumnSpec:
    """Build a column whose label key follows the workbook's i18n convention."""
    return ColumnSpec(
        key=key,
        label_key=f"settings.admin.llm.sheet.column.{key}",
        kind=kind,  # type: ignore[arg-type]
        block=block,
        editable=editable,
        required=required,
        referential=referential,
        decimals=decimals,
        minimum=minimum,
        width=width,
        hidden=hidden,
    )


_MODEL_COLUMNS: tuple[ColumnSpec, ...] = (
    # --- identity ---------------------------------------------------------
    _column("model_name", "text", "identity", required=True, width=34),
    _column("provider", "enum", "identity", referential="PROVIDER", width=16),
    _column("kind", "enum", "identity", referential="KIND", width=14),
    # --- state ------------------------------------------------------------
    _column("is_active", "boolean", "state", width=10),
    # --- capabilities -----------------------------------------------------
    _column("max_input_tokens", "integer", "capabilities", minimum=_ZERO, width=16),
    _column("max_output_tokens", "integer", "capabilities", minimum=_ZERO, width=16),
    _column("supports_tools", "boolean", "capabilities", width=12),
    _column("supports_structured_output", "boolean", "capabilities", width=14),
    _column("supports_strict_mode", "boolean", "capabilities", width=12),
    _column("supports_streaming", "boolean", "capabilities", width=12),
    _column("supports_vision", "boolean", "capabilities", width=12),
    # --- sampling ---------------------------------------------------------
    _column("supports_temperature", "boolean", "sampling", width=13),
    _column("supports_top_p", "boolean", "sampling", width=12),
    _column("supports_frequency_penalty", "boolean", "sampling", width=13),
    _column("supports_presence_penalty", "boolean", "sampling", width=13),
    # --- reasoning --------------------------------------------------------
    # One editable dropdown replaces four fragile fields: the template mechanism
    # is already the admin dialog's default mode, and the service copies the
    # whole reasoning shape from it. The read-only summary keeps the file
    # self-describing for the models the templates cannot express.
    _column("reasoning_template", "enum", "reasoning", referential="TEMPLATE", width=26),
    _column("reasoning_shape", "text", "reasoning", editable=False, width=34),
    _column("reasoning_doc_i18n_key", "text", "reasoning", width=22),
    _column("effort_values", "text", "reasoning", editable=False, width=16),
    # --- pricing ----------------------------------------------------------
    _column("pricing_unit", "enum", "pricing", referential="UNIT", width=18),
    _column(
        "input_unit_price", "decimal", "pricing", decimals=_PRICE_SCALE, minimum=_ZERO, width=15
    ),
    _column(
        "cached_input_unit_price",
        "decimal",
        "pricing",
        decimals=_PRICE_SCALE,
        minimum=_ZERO,
        width=15,
    ),
    _column(
        "output_unit_price", "decimal", "pricing", decimals=_PRICE_SCALE, minimum=_ZERO, width=15
    ),
    _column("effective_from", "text", "pricing", editable=False, width=22),
    # --- time slots -------------------------------------------------------
    _column("time_slots_mode", "enum", "slots", referential="SLOTMODE", width=14),
    _column("time_slots_summary", "text", "slots", editable=False, width=38),
    # --- diagnostics ------------------------------------------------------
    # Surfaces what the runtime would actually do: a model with no active
    # tariff is billed zero in silence, and a duplicated one is non-deterministic.
    _column("statut", "text", "diagnostics", editable=False, width=26),
    # Hidden, read-only, and not a domain value: the export stamps each row with
    # a hash of its editable cells, and the import compares it to the current
    # state. Only the rows that moved underneath the administrator are refused —
    # a single global check would reject a whole file because a colleague
    # touched one unrelated model.
    _column(FINGERPRINT_COLUMN, "text", "diagnostics", editable=False, width=18, hidden=True),
)

MODELS_SHEET = SheetSpec(
    name="Modeles",
    title_key="settings.admin.llm.sheet.models",
    columns=_MODEL_COLUMNS,
    key_column="model_name",
)

_SLOT_COLUMNS: tuple[ColumnSpec, ...] = (
    _column("model_name", "text", "identity", required=True, width=34),
    _column("start_utc", "time_hhmm", "slots", width=12),
    _column("end_utc", "time_hhmm", "slots", width=12),
    _column(
        "input_unit_price", "decimal", "pricing", decimals=_PRICE_SCALE, minimum=_ZERO, width=15
    ),
    _column(
        "cached_input_unit_price",
        "decimal",
        "pricing",
        decimals=_PRICE_SCALE,
        minimum=_ZERO,
        width=15,
    ),
    _column(
        "output_unit_price", "decimal", "pricing", decimals=_PRICE_SCALE, minimum=_ZERO, width=15
    ),
)

SLOTS_SHEET = SheetSpec(
    name="Plages horaires",
    title_key="settings.admin.llm.sheet.slots",
    columns=_SLOT_COLUMNS,
    key_column="model_name",
    # A model owns several windows, so its name groups rows rather than
    # identifying them. Declaring it unique made every windowed model come back
    # as a duplicate — caught by simulating a real export.
    key_is_unique=False,
)

#: Columns of ``llm_models`` the workbook carries, directly or through a derived
#: column. Read by the completeness guard; the value says how it is carried.
#:
#: Kept per table on purpose: ``is_active`` exists on BOTH tables with different
#: meanings, so a single flat map would let one table's coverage vouch for the
#: other's — the guard would stop guarding.
MODEL_SOURCE_COLUMNS: Mapping[str, str] = {
    # carried verbatim
    "model_name": "identity",
    "provider": "identity",
    "kind": "identity",
    "is_active": "state",
    "max_input_tokens": "capabilities",
    "max_output_tokens": "capabilities",
    "supports_tools": "capabilities",
    "supports_structured_output": "capabilities",
    "supports_strict_mode": "capabilities",
    "supports_streaming": "capabilities",
    "supports_vision": "capabilities",
    "supports_temperature": "sampling",
    "supports_top_p": "sampling",
    "supports_frequency_penalty": "sampling",
    "supports_presence_penalty": "sampling",
    "reasoning_doc_i18n_key": "reasoning",
    # llm_models — carried through the reasoning template and its summary
    "is_reasoning_model": "reasoning_template + reasoning_shape",
    "reasoning_widget": "reasoning_template + reasoning_shape",
    "reasoning_enum_values": "reasoning_template + reasoning_shape",
    "reasoning_budget_range": "reasoning_template + reasoning_shape",
    "effort_values": "effort_values (read-only)",
}

#: Columns of ``llm_model_pricing`` the workbook carries.
PRICING_SOURCE_COLUMNS: Mapping[str, str] = {
    "pricing_unit": "pricing",
    "input_unit_price": "pricing",
    "cached_input_unit_price": "pricing",
    "output_unit_price": "pricing",
    "effective_from": "effective_from (read-only)",
    "time_slots": "time_slots_mode + the time-slot sheet",
}

#: Columns of ``llm_models`` deliberately left out, each with its reason.
EXCLUDED_MODEL_COLUMNS: Mapping[str, str] = {
    "id": "surrogate key; rows are identified by model_name",
    "created_at": "audit timestamp, set by the database and meaningless to edit",
    "updated_at": "audit timestamp, set by the database and meaningless to edit",
}

#: Columns of ``llm_model_pricing`` deliberately left out, each with its reason.
EXCLUDED_PRICING_COLUMNS: Mapping[str, str] = {
    "id": "surrogate key of a versioned row; a tariff is identified by its model",
    "model_id": "foreign key resolved from model_name",
    "created_at": "audit timestamp, set by the database and meaningless to edit",
    "updated_at": "audit timestamp, set by the database and meaningless to edit",
    "is_active": (
        "the tariff's own flag is an internal versioning detail: the workbook "
        "exposes the model's is_active, and superseding a tariff is what an "
        "edited price means"
    ),
}


def build_pricing_workbook_spec(templates: Sequence[str] = ()) -> WorkbookSpec:
    """Build the workbook declaration.

    Args:
        templates: Model names usable as a reasoning template, from
            ``LLMModelService.list_templates``. Supplied by the caller because
            they are data, not schema. The custom marker is always appended so
            the dropdown can express "matches no template" and is never empty.

    Returns:
        The declaration the writer and the reader both consume.
    """
    template_values = tuple(templates) + (CUSTOM_TEMPLATE_MARKER,)
    return WorkbookSpec(
        sheets=(MODELS_SHEET, SLOTS_SHEET),
        referentials={
            "PROVIDER": tuple(member.value for member in LLMProviderEnum),
            "KIND": tuple(member.value for member in LLMModelKindEnum),
            "UNIT": tuple(member.value for member in PricingUnitEnum),
            "WIDGET": tuple(member.value for member in LLMReasoningWidgetEnum),
            "SLOTMODE": TIME_SLOT_MODES,
            "TEMPLATE": template_values,
        },
        schema_version=SCHEMA_VERSION,
    )
