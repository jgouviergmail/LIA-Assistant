"""Change user_interests uniqueness to include category

Revision ID: change_interest_uniqueness_001
Revises: add_user_onboarding_completed_001
Create Date: 2026-01-30 00:00:00.000000

This migration modifies the uniqueness constraint for user interests:
- Before: UNIQUE(user_id, topic) - a topic is globally unique per user
- After: UNIQUE(user_id, topic, category) - a topic can exist in different categories

This allows users to have the same topic in different categories, e.g.:
- "Python" in Technology (programming language)
- "Python" in Nature (snake species)
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "change_interest_uniqueness_001"
down_revision: str | None = "add_onboarding_completed_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Change uniqueness constraint from (user_id, topic) to (user_id, topic, category).
    """
    # Drop old constraint
    op.drop_constraint("uq_user_interests_user_topic", "user_interests", type_="unique")

    # Create new constraint including category
    op.create_unique_constraint(
        "uq_user_interests_user_topic_category",
        "user_interests",
        ["user_id", "topic", "category"],
    )


def downgrade() -> None:
    """
    Revert to original uniqueness constraint (user_id, topic).

    WARNING: This may fail if there are duplicate topics across categories.
    """
    # Drop new constraint
    op.drop_constraint("uq_user_interests_user_topic_category", "user_interests", type_="unique")

    # Restore old constraint
    op.create_unique_constraint(
        "uq_user_interests_user_topic",
        "user_interests",
        ["user_id", "topic"],
    )
