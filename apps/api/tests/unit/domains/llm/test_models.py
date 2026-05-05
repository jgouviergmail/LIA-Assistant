"""Unit tests for LLMModel and LLMModelPricing SQLAlchemy classes."""

import pytest

from src.domains.llm.models import LLMModel, LLMModelPricing


@pytest.mark.unit
def test_llm_model_has_required_columns() -> None:
    """LLMModel exposes provider + 8 capability columns + model_name + is_active."""
    cols = {c.name for c in LLMModel.__table__.columns}
    assert "provider" in cols
    assert "model_name" in cols
    assert "max_input_tokens" in cols
    assert "max_output_tokens" in cols
    assert "supports_tools" in cols
    assert "supports_structured_output" in cols
    assert "supports_strict_mode" in cols
    assert "supports_streaming" in cols
    assert "supports_vision" in cols
    assert "is_reasoning_model" in cols
    assert "is_active" in cols


@pytest.mark.unit
def test_llm_model_inherits_uuid_and_timestamp_mixins() -> None:
    """LLMModel inherits UUIDMixin (id) and TimestampMixin (created_at/updated_at)."""
    cols = {c.name for c in LLMModel.__table__.columns}
    assert "id" in cols
    assert "created_at" in cols
    assert "updated_at" in cols


@pytest.mark.unit
def test_llm_model_name_is_unique() -> None:
    """model_name carries a UNIQUE constraint at the column level."""
    col = LLMModel.__table__.columns["model_name"]
    assert col.unique is True


@pytest.mark.unit
def test_llm_model_pricing_has_model_id_fk() -> None:
    """LLMModelPricing.model_id is an FK to llm_models.id with ON DELETE RESTRICT."""
    cols = {c.name for c in LLMModelPricing.__table__.columns}
    assert "model_id" in cols

    fks = LLMModelPricing.__table__.columns["model_id"].foreign_keys
    assert len(fks) == 1
    fk = next(iter(fks))
    assert fk.column.table.name == "llm_models"
    assert fk.ondelete == "RESTRICT"


@pytest.mark.unit
def test_llm_model_pricing_model_id_is_not_null() -> None:
    """model_id is NOT NULL after migration #3 (every pricing row points to a model)."""
    col = LLMModelPricing.__table__.columns["model_id"]
    assert col.nullable is False


@pytest.mark.unit
def test_llm_model_pricing_no_longer_has_model_name_column() -> None:
    """The legacy model_name column is dropped — recover it via JOIN on llm_models."""
    cols = {c.name for c in LLMModelPricing.__table__.columns}
    assert "model_name" not in cols


@pytest.mark.unit
def test_llm_model_provider_uses_postgres_enum() -> None:
    """provider column uses the shared llm_provider_enum PG enum."""
    col = LLMModel.__table__.columns["provider"]
    assert col.type.__class__.__name__ in {"Enum", "ENUM"}
    enum_name = getattr(col.type, "name", None)
    assert enum_name == "llm_provider_enum"
