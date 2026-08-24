"""The two demoted reasoning columns are gone, not merely ignored (ADR-245).

They discriminated the four stored shapes of ``reasoning_effort``. ADR-245 left
them in place as "descriptive", and the catalogue screen kept offering them for
editing — a field an operator can curate, that nothing reads, is worse than no
field at all. What survives is what the runtime consults:
``reasoning_enum_values`` (the ladder narrowing) and ``reasoning_doc_i18n_key``
(the help text).
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

DROPPED = ("reasoning_widget", "reasoning_budget_range")

#: One name, two meanings, and only one of them is forbidden. The dropped
#: CATALOGUE COLUMN carried a range an operator typed in; this field carries
#: the FAMILY's own bounds -- the ones the validator enforces -- resolved from
#: (provider, model) and published so the admin form cannot offer a budget the
#: API refuses. ``LLMModelMetadata`` already publishes it under that exact
#: name, and giving one resolved value two names across two admin screens is
#: how vocabularies drift apart. The exemption is ONE pair, never a wildcard:
#: any other schema growing the field is still a finding, and the test below
#: asserts the reason this pair is legitimate.
_NOT_THE_COLUMN = frozenset({"ReasoningFamilyResponse.reasoning_budget_range"})


def test_the_orm_no_longer_declares_them() -> None:
    from src.domains.llm.models import LLMModel

    for column in DROPPED:
        assert column not in LLMModel.__table__.columns, column


def test_what_the_runtime_reads_is_still_there() -> None:
    """The deletion must not take the ladder narrowing with it."""
    from src.domains.llm.models import LLMModel

    assert "reasoning_enum_values" in LLMModel.__table__.columns
    assert "reasoning_doc_i18n_key" in LLMModel.__table__.columns
    assert "is_reasoning_model" in LLMModel.__table__.columns


def test_the_widget_enum_type_is_gone() -> None:
    import src.domains.llm.models as models

    assert not hasattr(models, "LLMReasoningWidgetEnum")


def test_the_runtime_profile_no_longer_mirrors_them() -> None:
    from src.infrastructure.llm.model_profiles import ModelProfile

    fields = set(ModelProfile.__dataclass_fields__)
    assert not (fields & set(DROPPED)), fields & set(DROPPED)
    assert "reasoning_enum_values" in fields


def test_the_catalogue_type_module_is_gone() -> None:
    """``core/reasoning_types.py`` held one class, for one column."""
    import importlib

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("src.core.reasoning_types")


@pytest.mark.parametrize("column", DROPPED)
def test_no_schema_still_declares_them(column: str) -> None:
    from src.domains.llm import schemas

    offenders = [
        f"{name}.{column}"
        for name in dir(schemas)
        if isinstance(getattr(schemas, name, None), type)
        and hasattr(getattr(schemas, name), "model_fields")
        and column in getattr(schemas, name).model_fields
        and f"{name}.{column}" not in _NOT_THE_COLUMN
    ]
    assert offenders == [], offenders


def test_the_workbook_neither_carries_nor_excludes_them() -> None:
    """A column that does not exist needs no exclusion reason either."""
    from src.domains.llm.pricing_sheet import EXCLUDED_MODEL_COLUMNS, MODEL_SOURCE_COLUMNS

    for column in DROPPED:
        assert column not in MODEL_SOURCE_COLUMNS
        assert column not in EXCLUDED_MODEL_COLUMNS


def test_the_exempted_field_really_is_the_family_s_bounds_not_the_column() -> None:
    """The exemption above is only legitimate while this stays true.

    A guard that carries an allowlist must assert the REASON for each entry,
    or the entry outlives it: the day someone repurposes this schema to echo a
    curated catalogue value, the name would be back and the guard silent.
    """
    from src.domains.llm.router import _reasoning_family_payload
    from src.infrastructure.llm.reasoning.profiles import resolve_reasoning_profile

    payload = _reasoning_family_payload("anthropic", "claude-opus-4-5")
    family = resolve_reasoning_profile("anthropic", "claude-opus-4-5")

    assert family.budget_range is not None
    assert payload.reasoning_budget_range is not None
    assert (payload.reasoning_budget_range.min, payload.reasoning_budget_range.max) == (
        family.budget_range
    )
    # And it carries no trace of the other dropped column.
    from src.domains.llm.schemas import ReasoningFamilyResponse

    assert "reasoning_widget" not in ReasoningFamilyResponse.model_fields
