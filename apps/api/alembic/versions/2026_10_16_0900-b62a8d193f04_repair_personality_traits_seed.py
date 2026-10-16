"""Repair stock personality traits lost by the reference seed.

The seed reinserted its stock rows without OCEAN/PAD columns after the original
trait migration. Restore the last published profiles only where ALL eight
columns remain absent. Any explicit administrator value, including zero, wins.
Only neutral state copies of the profiles repaired by THIS execution are aligned;
their mood, relationship, efficacy, emotions and history are never rewritten.

Revision ID: b62a8d193f04
Revises: 7f428c3e0a19
"""

from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision: str = "b62a8d193f04"
down_revision: str | None = "7f428c3e0a19"
branch_labels: None = None
depends_on: None = None

# Frozen from psyche_traits_001 (2026_04_01_0003), not the older initial mapping.
# Identity is UUID AND code: a renamed/replaced administrator profile is not stock.
PERSONALITY_PROFILES = (
    (
        "7b769b3b-d5e5-4929-90ed-54e72941005d",
        "cynic",
        0.70,
        0.55,
        0.45,
        0.25,
        0.45,
        None,
        None,
        None,
    ),
    (
        "23266ad8-b419-4594-9b3c-28f7a580bfd9",
        "normal",
        0.50,
        0.50,
        0.50,
        0.50,
        0.50,
        None,
        None,
        None,
    ),
    (
        "0a25b00f-89f9-4180-bda1-fb0561f519c0",
        "depressed",
        0.60,
        0.30,
        0.20,
        0.55,
        0.85,
        -0.20,
        None,
        None,
    ),
    (
        "6274e825-d4c3-4f6c-86d7-ac5e7629c2e4",
        "enthusiastic",
        0.65,
        0.40,
        0.85,
        0.70,
        0.30,
        None,
        0.35,
        None,
    ),
    (
        "ceaf6e6c-0ef3-4ae4-b85b-c6f834f5fd54",
        "friend",
        0.55,
        0.50,
        0.70,
        0.85,
        0.35,
        None,
        None,
        None,
    ),
    (
        "6b7aeed0-37a5-4992-9fae-203b02534761",
        "philosopher",
        0.90,
        0.65,
        0.35,
        0.60,
        0.40,
        None,
        -0.25,
        None,
    ),
    (
        "f30d019a-05a7-4326-adbf-64f1bb007ce9",
        "influencer",
        0.55,
        0.35,
        0.80,
        0.40,
        0.50,
        None,
        None,
        None,
    ),
    (
        "3ed44d2b-5898-4190-b9a7-80fc8bf9678b",
        "professor",
        0.70,
        0.80,
        0.55,
        0.65,
        0.25,
        None,
        None,
        None,
    ),
    (
        "c3bb2155-984a-4414-b441-7f8a265dc535",
        "rasta",
        0.75,
        0.25,
        0.60,
        0.80,
        0.15,
        0.20,
        -0.20,
        None,
    ),
    (
        "cdab692d-7df0-40fe-a87c-9e67c452117b",
        "teenager",
        0.40,
        0.20,
        0.55,
        0.20,
        0.60,
        None,
        None,
        0.25,
    ),
    (
        "d8576bd9-d698-4944-bd92-bc76edf4a003",
        "jarvis",
        0.50,
        0.90,
        0.30,
        0.55,
        0.10,
        None,
        None,
        0.30,
    ),
    (
        "cea2a505-c932-4834-93e4-9d8f6e76b1dd",
        "haipai",
        0.65,
        0.70,
        0.75,
        0.45,
        0.35,
        None,
        0.15,
        None,
    ),
    (
        "ef2ec97b-cffc-4c3c-a4ae-1381670b701f",
        "trump",
        0.30,
        0.35,
        0.90,
        0.15,
        0.55,
        0.15,
        None,
        0.40,
    ),
    (
        "61178ee5-76e1-4984-a983-0f451dc74305",
        "antagonist",
        0.65,
        0.40,
        0.50,
        0.20,
        0.50,
        None,
        None,
        None,
    ),
)
# The reference export replaced this one stock UUID after psyche_traits_001.
# Keep both published identities bounded by their original code.
LEGACY_PROFILES = (
    (
        "8d3c8cac-8f69-443e-9dfe-15e883a7c1b8",
        "antagonist",
        0.65,
        0.40,
        0.50,
        0.20,
        0.50,
        None,
        None,
        None,
    ),
)
TRAITS = (
    "trait_openness",
    "trait_conscientiousness",
    "trait_extraversion",
    "trait_agreeableness",
    "trait_neuroticism",
)
PADS = ("pad_pleasure_override", "pad_arousal_override", "pad_dominance_override")


def upgrade() -> None:
    bind = op.get_bind()
    profiles = sa.table(
        "personalities",
        sa.column("id", sa.Uuid),
        sa.column("code", sa.String),
        sa.column("is_default", sa.Boolean),
        *(sa.column(name, sa.Float) for name in (*TRAITS, *PADS)),
    )
    repaired: list[UUID] = []
    for identifier, code, *values in (*PERSONALITY_PROFILES, *LEGACY_PROFILES):
        result = bind.execute(
            profiles.update()
            .where(
                profiles.c.id == UUID(identifier),
                profiles.c.code == code,
                *(profiles.c[name].is_(None) for name in (*TRAITS, *PADS)),
            )
            .values(dict(zip((*TRAITS, *PADS), values, strict=True)))
            .returning(profiles.c.id)
        ).scalar_one_or_none()
        if result is not None:
            repaired.append(result)
    if not repaired:
        return

    users = sa.table("users", sa.column("id", sa.Uuid), sa.column("personality_id", sa.Uuid))
    states = sa.table(
        "psyche_states",
        sa.column("user_id", sa.Uuid),
        *(sa.column(name, sa.Float) for name in TRAITS),
    )
    # The service falls back to the instance default when no selected row exists.
    # Correlation is explicit so both subqueries retain their own profile table.
    selected = (
        sa.select(profiles.c.id)
        .where(profiles.c.id == users.c.personality_id)
        .correlate(users)
        .scalar_subquery()
    )
    default = (
        sa.select(profiles.c.id)
        .where(profiles.c.is_default.is_(True))
        .correlate(None)
        .scalar_subquery()
    )
    effective = (
        sa.select(users.c.id.label("user_id"), *(profiles.c[name] for name in TRAITS))
        .select_from(users.join(profiles, profiles.c.id == sa.func.coalesce(selected, default)))
        .where(profiles.c.id.in_(repaired))
        .cte("repaired_effective_profiles")
    )
    bind.execute(
        states.update()
        .where(
            states.c.user_id == effective.c.user_id,
            *(states.c[name] == 0.5 for name in TRAITS),
        )
        .values({name: effective.c[name] for name in TRAITS})
    )


def downgrade() -> None:
    """Data repair is retained: losing traits again cannot safely restore old intent.

    Removing a repaired value could erase a later administrator edit; this
    additive data migration therefore has no destructive downgrade.
    """
