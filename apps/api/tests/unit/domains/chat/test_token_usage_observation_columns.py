"""The four facts a model policy needs to judge a model, and their index."""

from __future__ import annotations

from src.domains.chat.models import TokenUsageLog

OBSERVATION_COLUMNS = ("latency_ms", "status", "failure_kind", "llm_type")


def test_the_columns_exist_and_are_nullable() -> None:
    """Nullable with no backfill: history is admitted absent, never invented."""
    columns = TokenUsageLog.__table__.columns
    for name in OBSERVATION_COLUMNS:
        assert name in columns, name
        assert columns[name].nullable is True, name


def test_failure_kind_fits_every_taxonomy_member() -> None:
    """A new failure kind must not silently overflow the column."""
    from src.infrastructure.observability.error_taxonomy import LLM_FAILURE_KINDS

    length = TokenUsageLog.__table__.columns["failure_kind"].type.length
    assert length is not None
    assert all(len(kind) <= length for kind in LLM_FAILURE_KINDS)


def test_llm_type_fits_every_slot_name() -> None:
    from src.domains.llm_config.constants import LLM_TYPES_REGISTRY

    length = TokenUsageLog.__table__.columns["llm_type"].type.length
    assert length is not None
    assert all(len(slot) <= length for slot in LLM_TYPES_REGISTRY)


def test_the_controller_window_index_is_declared() -> None:
    """The aggregate groups by SLOT — never by node_name (unbounded)."""
    index = next(
        (
            i
            for i in TokenUsageLog.__table__.indexes
            if i.name == "ix_token_usage_logs_controller_window"
        ),
        None,
    )
    assert index is not None
    columns = [c.name if hasattr(c, "name") else str(c) for c in index.expressions]
    assert columns[:2] == ["llm_type", "model_name"]
    assert "node_name" not in columns


def test_the_lifetime_index_is_untouched() -> None:
    names = {index.name for index in TokenUsageLog.__table__.indexes}
    assert "ix_token_usage_logs_lifetime_aggregation" in names
