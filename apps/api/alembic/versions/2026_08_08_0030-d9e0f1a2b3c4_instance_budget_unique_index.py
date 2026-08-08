"""Instance budget: one UNIQUE index on utc_day, not a constraint plus a plain one.

``b665290a2fb4`` created BOTH a ``UniqueConstraint`` and a non-unique index on
``instance_daily_budget.utc_day``, while the model declares the column with
``unique=True, index=True`` — which SQLAlchemy renders as a single UNIQUE
index. Uniqueness was enforced either way, so nothing was broken at runtime;
what broke is the from-scratch replay gate, which compares STRUCTURE and
reported the difference as drift.

Corrective rather than an amendment of ``b665290a2fb4``: that revision has
already been applied to running databases (the maintainer's development
instance, the demonstrator), and rewriting an applied migration would leave
them silently diverged from a fresh install. This one converges both.

The two objects are swapped inside one transaction: dropping the constraint
first would leave a window with no uniqueness guarantee at all, and this table
is the spend ledger — the one place where a lost UPSERT conflict means a
double-counted euro.

Revision ID: d9e0f1a2b3c4
Revises: c7d1e93a4f10
Create Date: 2026-08-08 00:30:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d9e0f1a2b3c4"
down_revision: str | None = "c7d1e93a4f10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "instance_daily_budget"
_INDEX = "ix_instance_daily_budget_utc_day"
_CONSTRAINT = "uq_instance_daily_budget_utc_day"


def upgrade() -> None:
    """Replace the constraint + plain index with a single unique index."""
    # Unique index FIRST: uniqueness is never unenforced, not even briefly.
    op.drop_index(_INDEX, table_name=_TABLE)
    op.create_index(_INDEX, _TABLE, ["utc_day"], unique=True)
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="unique")


def downgrade() -> None:
    """Restore the constraint + plain index shape of ``b665290a2fb4``."""
    op.create_unique_constraint(_CONSTRAINT, _TABLE, ["utc_day"])
    op.drop_index(_INDEX, table_name=_TABLE)
    op.create_index(_INDEX, _TABLE, ["utc_day"])
