"""Consent to every sensitive topic where nobody chose yet (owner decision 2026-10-21).

A new account now consents to the operator's default topics
(``DISCUSSION_DEFAULT_SENSITIVE_TOPICS``, every topic unless configured otherwise).
A row nobody ever edited (``revision = 0``) still carries the former default, no
topic at all: it receives the shipped default — the five topics — which the person
withdraws one by one in the settings. A row its owner edited keeps its topics, an
empty list included: an empty list may be a refusal, and consent to a sensitive
topic is never inferred from one (measured on production 2026-10-21: one row, edited,
already naming its topics — the migration changes nothing there).

The downgrade cannot tell a migrated row from one a person set to the same five
topics since, so it changes nothing.

Revision ID: 6b2c4e8f0a17
Revises: 3d8e6f1a9c42
"""

import sqlalchemy as sa
from alembic import op

revision = "6b2c4e8f0a17"
down_revision = "3d8e6f1a9c42"
branch_labels = None
depends_on = None

SHIPPED_DEFAULT = '["health", "relationships", "finances", "grief", "intimacy"]'
#: Module-level so the integration test proves this very statement.
BACKFILL_STATEMENT = (
    "UPDATE discussion_preferences SET sensitive_topics = CAST(:topics AS jsonb) "
    "WHERE sensitive_topics = '[]'::jsonb AND revision = 0"
)


def upgrade() -> None:
    op.execute(sa.text(BACKFILL_STATEMENT).bindparams(topics=SHIPPED_DEFAULT))


def downgrade() -> None:
    """Nothing to undo: a migrated row cannot be told from a deliberate choice."""
