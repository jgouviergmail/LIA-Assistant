"""a ticket carries the mode it runs in and what it has cost so far (ADR-276)

Revision ID: 313ab021caa4
Revises: be129cf66564
Create Date: 2026-09-09 06:00:00

Two things a row must carry, both asked for on 2026-09-09:

- **the execution mode**. How LIA executes an instruction nobody is watching —
  the deterministic pipeline or the autonomous ReAct loop — was a DEPLOYMENT
  setting for tickets (``WORKBOARD_RUN_EXECUTION_MODE``) and nothing at all for
  routines, which inherited the service's own « pipeline » default. Neither
  could say what the person wants: two tickets of one account legitimately want
  different modes, and the choice belongs to whoever writes the instruction.
  Both tables gain the column NOT NULL with a server default, so every existing
  row is born in the loop — what a routine firing with nobody there needs.
- **what the ticket has cost since it was created**. The row already carried the
  LAST run's figures; a ticket is run up to ten times, and « what did this cost
  me » is a question about the ticket, not about its last minute. Accumulated at
  settle time by column arithmetic (never SELECT-then-add), in the same
  vocabulary the chat already shows: in, out, cache, Google, euros.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "313ab021caa4"
down_revision = "be129cf66564"
branch_labels = None
depends_on = None

#: Each row's mode, and what it means THERE — the sentences are the models'
#: own, verbatim: a comment is part of what the replay check compares.
_MODE_TABLES = (
    (
        "workboard_tickets",
        "pipeline | react — how LIA runs THIS ticket. The person may change "
        "it at any point of the ticket's life; the next run reads it.",
    ),
    (
        "scheduled_actions",
        "pipeline | react — how this routine executes. The loop by default: "
        "nobody is there to steer a plan when it fires.",
    ),
)

_TOTALS = (
    ("total_tokens_in", sa.Integer(), "0", "Prompt tokens every run of this ticket has spent."),
    ("total_tokens_out", sa.Integer(), "0", "Completion tokens every run has produced."),
    ("total_tokens_cache", sa.Integer(), "0", "Cached prompt tokens every run has read."),
    (
        "total_google_requests",
        sa.Integer(),
        "0",
        "Google API requests every run has made.",
    ),
    (
        "total_cost_eur",
        sa.Numeric(12, 6),
        "0",
        "What this ticket has cost since it was created, run by run.",
    ),
)


def upgrade() -> None:
    for table, comment in _MODE_TABLES:
        op.add_column(
            table,
            sa.Column(
                "execution_mode",
                sa.String(length=10),
                nullable=False,
                server_default="react",
                comment=comment,
            ),
        )
    for name, kind, default, comment in _TOTALS:
        op.add_column(
            "workboard_tickets",
            sa.Column(name, kind, nullable=False, server_default=default, comment=comment),
        )


def downgrade() -> None:
    for name, _kind, _default, _comment in _TOTALS:
        op.drop_column("workboard_tickets", name)
    for table, _comment in _MODE_TABLES:
        op.drop_column(table, "execution_mode")
