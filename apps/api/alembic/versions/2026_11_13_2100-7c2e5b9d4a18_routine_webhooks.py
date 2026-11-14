"""A signed call starts a routine.

Revision ID: 7c2e5b9d4a18
Revises: a696c8a365f2

A routine gains a third clock: another system's call to its own address, signed with
its own secret (ADR-386). ``scheduled_actions.webhook_key`` is the address's key and
``webhook_secret`` the HMAC secret, encrypted at rest; both are set exactly when the
routine runs on that clock. ``routine_webhook_deliveries`` keeps each accepted call
until a run serves it, its body encrypted and erased once served.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "7c2e5b9d4a18"
down_revision: str | Sequence[str] | None = "a696c8a365f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ONE_CLOCK_BEFORE = (
    "(trigger_kind = 'time' AND recurrence IS NOT NULL AND condition_config IS NULL)"
    " OR (trigger_kind = 'condition' AND recurrence IS NULL"
    " AND condition_config IS NOT NULL)"
)
_ONE_CLOCK_AFTER = (
    _ONE_CLOCK_BEFORE + " OR (trigger_kind = 'webhook' AND recurrence IS NULL"
    " AND condition_config IS NULL)"
)
_ADDRESS = (
    "(trigger_kind = 'webhook') = (webhook_key IS NOT NULL AND webhook_secret IS NOT NULL)"
)


def upgrade() -> None:
    """Give a routine an address and keep the calls it accepts."""
    op.add_column(
        "scheduled_actions",
        sa.Column(
            "webhook_key",
            sa.String(length=64),
            nullable=True,
            comment="WEBHOOK kind only: the key of its address. NULL otherwise.",
        ),
    )
    op.add_column(
        "scheduled_actions",
        sa.Column(
            "webhook_secret",
            sa.Text(),
            nullable=True,
            comment="WEBHOOK kind only: its HMAC secret, encrypted. NULL otherwise.",
        ),
    )
    op.create_unique_constraint(
        "uq_scheduled_actions_webhook_key", "scheduled_actions", ["webhook_key"]
    )
    op.drop_constraint("ck_scheduled_actions_one_clock", "scheduled_actions", type_="check")
    op.create_check_constraint(
        "ck_scheduled_actions_one_clock", "scheduled_actions", _ONE_CLOCK_AFTER
    )
    op.create_check_constraint(
        "ck_scheduled_actions_webhook_address", "scheduled_actions", _ADDRESS
    )
    op.alter_column(
        "scheduled_actions",
        "trigger_kind",
        comment=(
            "time = runs on its recurrence; condition = checked by the system (ADR-322); "
            "webhook = started by a signed call to its address (ADR-386)"
        ),
        existing_type=sa.String(length=20),
        existing_nullable=False,
        existing_server_default="time",
    )

    op.create_table(
        "routine_webhook_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "scheduled_action_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="The routine called. Dies with it.",
        ),
        sa.Column(
            "delivery_id",
            sa.String(length=200),
            nullable=True,
            comment="The sender's own id for this delivery, when it gives one.",
        ),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="When the call was accepted (UTC).",
        ),
        sa.Column(
            "content_type",
            sa.String(length=255),
            nullable=True,
            comment="The media type the sender declared, when it declared one.",
        ),
        sa.Column(
            "body_bytes",
            sa.Integer(),
            nullable=False,
            comment="Size of the body as received, in bytes.",
        ),
        sa.Column(
            "body",
            sa.Text(),
            nullable=True,
            comment="The body read as text, encrypted; erased once served.",
        ),
        sa.Column(
            "status",
            sa.String(length=10),
            server_default="pending",
            nullable=False,
            comment="pending = waiting for a run; served = read by a run that answered.",
        ),
        sa.Column(
            "served_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When a run that answered served it (UTC).",
        ),
        sa.ForeignKeyConstraint(
            ["scheduled_action_id"], ["scheduled_actions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('pending', 'served')", name="ck_routine_webhook_deliveries_status"
        ),
        sa.CheckConstraint(
            "(status = 'served') = (served_at IS NOT NULL)",
            name="ck_routine_webhook_deliveries_served_at",
        ),
        sa.CheckConstraint(
            "status = 'pending' OR body IS NULL",
            name="ck_routine_webhook_deliveries_served_body",
        ),
    )
    op.create_index(
        "uq_routine_webhook_deliveries_delivery",
        "routine_webhook_deliveries",
        ["scheduled_action_id", "delivery_id"],
        unique=True,
        postgresql_where=sa.text("delivery_id IS NOT NULL"),
    )
    op.create_index(
        "ix_routine_webhook_deliveries_pending",
        "routine_webhook_deliveries",
        ["scheduled_action_id", "received_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "ix_routine_webhook_deliveries_served",
        "routine_webhook_deliveries",
        ["served_at"],
        postgresql_where=sa.text("status = 'served'"),
    )


def downgrade() -> None:
    """Forget the calls, then the routines that ran on them, then the clock."""
    op.drop_index("ix_routine_webhook_deliveries_served", table_name="routine_webhook_deliveries")
    op.drop_index("ix_routine_webhook_deliveries_pending", table_name="routine_webhook_deliveries")
    op.drop_index(
        "uq_routine_webhook_deliveries_delivery", table_name="routine_webhook_deliveries"
    )
    op.drop_table("routine_webhook_deliveries")
    # A webhook routine has no clock the older schema can state: it cannot be
    # kept under the former CHECK, so it goes with its clock.
    op.execute("DELETE FROM scheduled_actions WHERE trigger_kind = 'webhook'")
    op.alter_column(
        "scheduled_actions",
        "trigger_kind",
        comment="time = runs on its recurrence; condition = checked by the system (ADR-322)",
        existing_type=sa.String(length=20),
        existing_nullable=False,
        existing_server_default="time",
    )
    op.drop_constraint("ck_scheduled_actions_webhook_address", "scheduled_actions", type_="check")
    op.drop_constraint("ck_scheduled_actions_one_clock", "scheduled_actions", type_="check")
    op.create_check_constraint(
        "ck_scheduled_actions_one_clock", "scheduled_actions", _ONE_CLOCK_BEFORE
    )
    op.drop_constraint("uq_scheduled_actions_webhook_key", "scheduled_actions", type_="unique")
    op.drop_column("scheduled_actions", "webhook_secret")
    op.drop_column("scheduled_actions", "webhook_key")
