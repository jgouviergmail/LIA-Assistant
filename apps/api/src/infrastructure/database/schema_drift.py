"""Shared Alembic drift configuration and the structural-drift gate (audit F042).

Single source of truth for what autogenerate / ``alembic check`` must ignore,
imported by both ``alembic/env.py`` and the structural-drift guard so the two can
never diverge.

The gate distinguishes STRUCTURAL drift (tables, columns, types, nullability,
indexes, constraints, **and column/table comments**) — which must fail CI —
from the single COSMETIC difference deliberately tolerated:

* server defaults are migration-managed here (models use Python ``default=``),
  so autogenerate comparing them yields only false positives.

Column and table comments used to be tolerated too, but they are now reconciled
against the models by migration ``58ac1d6c32e0`` (audit F042), so ``alembic
check`` is naturally green *without masking*: a new, unexpected comment drift is
detected like any other schema change. This is why there is no comment-stripping
autogenerate hook — the honest source of truth is the migrated database itself.

Some indexes are additionally un-round-trippable by autogenerate (pgvector HNSW,
covering ``INCLUDE``, partial ``WHERE``, and ``DESC``-ordered expression
indexes): reflection cannot be matched back to the ORM declaration, so they are
excluded by name. Excluding a *round-trippable* object would hide genuine drift,
so these sets are kept minimal and every entry is justified.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection

# Tables created and OWNED AT RUNTIME (LangGraph checkpointer + store, embedding
# migration marker): absent from Base.metadata by design.
RUNTIME_MANAGED_TABLES = {
    "checkpoints",
    "checkpoint_writes",
    "checkpoint_blobs",
    "checkpoint_migrations",
    "store",
    "store_vectors",
    "store_migrations",
    "vector_migrations",
}

# One-shot migration BRIDGE tables (``CREATE TABLE _legacy_* AS SELECT ...`` to
# snapshot data before a destructive column drop, read once by a startup
# back-fill and left in place). Dropping them via a migration would risk losing
# the snapshot before the back-fill runs on a migrated-but-never-booted
# deployment; excluding them keeps a from-scratch replay drift-free. Consumed by
# ``domains/skills/preference_service.py::_apply_legacy_disabled_skills``.
MIGRATION_BRIDGE_TABLES = {
    "_legacy_disabled_skills",
    "_legacy_system_disabled_skills",
}

# Indexes created (and owned) by raw SQL / DESC-ordered ops in migrations that
# Alembic autogenerate cannot faithfully round-trip. The B-tree indexes that CAN
# be expressed and compared live in each model's ``__table_args__`` instead.
RUNTIME_MANAGED_INDEXES = {
    # pgvector HNSW (raw SQL, recreated on dimension change / reindex).
    "ix_rag_chunks_embedding",
    "ix_memories_embedding_cosine",
    "ix_memories_keyword_embedding_cosine",
    "ix_journal_entries_embedding_cosine",
    "ix_journal_entries_keyword_embedding_cosine",
    # Covering index (INCLUDE columns).
    "ix_token_usage_logs_model_node_covering",
    # Partial indexes (WHERE predicate).
    "ix_reminders_pending_trigger",
    "ix_reminders_processing",
    "ix_user_interests_active",
    "ix_user_fcm_tokens_user_active",
    # Partial UNIQUE indexes (WHERE predicate).
    "uq_rag_spaces_user_name",
    "uq_rag_spaces_system_name",
    # DESC-ordered expression indexes: reflected as an opaque UnaryExpression that
    # autogenerate cannot match to the model's ``postgresql_ops={... : "DESC"}``,
    # so they are compared out even though they are declared in the ORM.
    "ix_conversation_messages_conv_created",
    "ix_token_usage_logs_created_at",
    "ix_token_usage_logs_lifetime_aggregation",
}

# Autogenerate operation names that are cosmetic and tolerated by the gate.
# Only server defaults remain cosmetic (models use Python ``default=``, so
# ``compare_server_default`` is off); column/table comments are now part of the
# contract (reconciled by migration 58ac1d6c32e0) and must surface as drift.
COSMETIC_DIFF_OPS = {
    "modify_default",
}


def include_object(
    obj: Any, name: str | None, type_: str, reflected: bool, compare_to: Any
) -> bool:
    """Exclude runtime-/bridge-/raw-SQL-managed objects from autogenerate.

    Unlike ``include_name`` (reflection-only), this is consulted for BOTH the
    reflected schema and the ORM metadata, so an excluded index that is also
    declared in a model (e.g. a DESC-ordered index) is dropped from both sides
    and never surfaces as a phantom add/drop.
    """
    if type_ == "table":
        return name not in RUNTIME_MANAGED_TABLES and name not in MIGRATION_BRIDGE_TABLES
    if type_ == "index":
        return name not in RUNTIME_MANAGED_INDEXES
    return True


def _op_name(op: Any) -> str | None:
    """Return the autogenerate operation name (first tuple element), if any."""
    if isinstance(op, (tuple, list)) and op and isinstance(op[0], str):
        return op[0]
    return None


def structural_diffs(connection: Connection) -> list[Any]:
    """Compute the STRUCTURAL model↔schema diffs against a live connection.

    Cosmetic ops (``COSMETIC_DIFF_OPS``) and excluded objects (``include_name``)
    are filtered out; the remaining operations indicate real drift that a
    migration must resolve.

    Args:
        connection: An open SQLAlchemy connection to a migrated database.

    Returns:
        The list of structural autogenerate operations (empty when in sync).
    """
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from src.infrastructure.database.models import Base
    from src.infrastructure.database.registry import import_all_models

    import_all_models()
    context = MigrationContext.configure(
        connection,
        opts={
            "compare_type": True,
            "compare_server_default": False,
            "include_object": include_object,
            "target_metadata": Base.metadata,
        },
    )
    structural: list[Any] = []
    for diff in compare_metadata(context, Base.metadata):
        ops = diff if isinstance(diff, list) else [diff]
        for op in ops:
            name = _op_name(op)
            if name is not None and name not in COSMETIC_DIFF_OPS:
                structural.append(op)
    return structural
