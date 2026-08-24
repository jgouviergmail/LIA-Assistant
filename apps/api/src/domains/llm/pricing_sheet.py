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

from collections.abc import Mapping
from decimal import Decimal

from src.domains.llm.models import (
    LLMModelKindEnum,
    LLMProviderEnum,
    PricingUnitEnum,
)
from src.infrastructure.tabular_io.spec import ColumnSpec, SheetSpec, WorkbookSpec

#: Bumped whenever the columns change in a way an older file cannot satisfy.
#: v2 replaced the ``reasoning_template`` dropdown with the two columns the
#: runtime actually reads (``is_reasoning_model``, ``reasoning_enum_values``):
#: a file written against v1 names a column that no longer exists and offers no
#: way to express the ladder, so it cannot be read back.
SCHEMA_VERSION = 2

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
    # The reasoning identity is written HERE, in the two columns the runtime
    # actually reads. It used to go through a `reasoning_template` dropdown --
    # "copy the shape of that other model" -- because the sheet had no other
    # way to express it. That indirection cost more than it saved once ADR-245
    # reduced the shape to a ladder: a template groups models by their STORED
    # ladder, not by family, so copying one across families silently removed
    # depths; and creating a model that does not reason at all still required
    # picking a template, because the plan refused a row without one.
    #
    # `reasoning_enum_values` NARROWS what the family accepts, it never widens
    # it -- the import refuses a level the family does not offer and names the
    # ones it does, which is what the admin form's checkboxes guarantee by
    # construction. `reasoning_shape` stays read-only next to it: it prints the
    # RESOLVED family and ladder, so the legal values are on screen while the
    # cell is being typed.
    _column("is_reasoning_model", "boolean", "reasoning", width=13),
    _column("reasoning_enum_values", "text", "reasoning", width=30),
    _column("reasoning_shape", "text", "reasoning", editable=False, width=34),
    _column("reasoning_doc_i18n_key", "text", "reasoning", width=22),
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
    "is_reasoning_model": "reasoning",
    "reasoning_enum_values": "reasoning",
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
    "capability_provenance": (
        "derived, never typed: the service stamps 'verified' when this very "
        "workbook changes a registry-owned capability, and the catalogue sync "
        "stamps 'imported'. A hand-written value would claim a verification "
        "nobody performed (ADR-244)"
    ),
    "deprecation_date": (
        "published by the provider and carried by the vendored registry "
        "snapshot; an edited value would be overwritten by the next "
        "`task llm:catalogue:sync` (ADR-244)"
    ),
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


def build_pricing_workbook_spec() -> WorkbookSpec:
    """Build the workbook declaration.

    It takes no data any more. The one referential that carried some was
    ``TEMPLATE``, the list of models a reasoning shape could be copied from;
    the sheet now writes the ladder itself, so every referential here is a
    closed enum the code owns.

    Returns:
        The declaration the writer and the reader both consume.
    """
    return WorkbookSpec(
        sheets=(MODELS_SHEET, SLOTS_SHEET),
        referentials={
            "PROVIDER": tuple(member.value for member in LLMProviderEnum),
            "KIND": tuple(member.value for member in LLMModelKindEnum),
            "UNIT": tuple(member.value for member in PricingUnitEnum),
            "SLOTMODE": TIME_SLOT_MODES,
        },
        schema_version=SCHEMA_VERSION,
    )
