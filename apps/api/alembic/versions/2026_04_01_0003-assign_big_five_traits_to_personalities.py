"""Assign Big Five personality traits and PAD overrides to all 14 personalities.

Psyche Engine Iteration 3: without these traits, all personalities behave
identically (default 0.5 on all axes). This migration enables personality-
specific emotional reactivity, contagion strength, and recovery speed.

Also syncs existing psyche_states records with their user's personality traits.

Revision ID: psyche_traits_001
Revises: psyche_avatar_001
Create Date: 2026-04-01 20:00:00.000000+00:00
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "psyche_traits_001"
down_revision: str | None = "psyche_avatar_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Personality UUID → (O, C, E, A, N, pad_p, pad_a, pad_d)
# pad_* = None means no override (computed from Mehrabian mapping)
PERSONALITY_TRAITS: list[
    tuple[str, float, float, float, float, float, float | None, float | None, float | None]
] = [
    # (id, O, C, E, A, N, pad_p, pad_a, pad_d)
    ("7b769b3b-d5e5-4929-90ed-54e72941005d", 0.70, 0.55, 0.45, 0.25, 0.45, None, None, None),  # Cynique
    ("23266ad8-b419-4594-9b3c-28f7a580bfd9", 0.50, 0.50, 0.50, 0.50, 0.50, None, None, None),  # Normal
    ("0a25b00f-89f9-4180-bda1-fb0561f519c0", 0.60, 0.30, 0.20, 0.55, 0.85, -0.20, None, None),  # Dépressif
    ("6274e825-d4c3-4f6c-86d7-ac5e7629c2e4", 0.65, 0.40, 0.85, 0.70, 0.30, None, 0.35, None),  # Enthousiaste
    ("ceaf6e6c-0ef3-4ae4-b85b-c6f834f5fd54", 0.55, 0.50, 0.70, 0.85, 0.35, None, None, None),  # Ami
    ("6b7aeed0-37a5-4992-9fae-203b02534761", 0.90, 0.65, 0.35, 0.60, 0.40, None, -0.25, None),  # Philosophe
    ("f30d019a-05a7-4326-adbf-64f1bb007ce9", 0.55, 0.35, 0.80, 0.40, 0.50, None, None, None),  # Influenceur
    ("3ed44d2b-5898-4190-b9a7-80fc8bf9678b", 0.70, 0.80, 0.55, 0.65, 0.25, None, None, None),  # Professeur
    ("c3bb2155-984a-4414-b441-7f8a265dc535", 0.75, 0.25, 0.60, 0.80, 0.15, 0.20, -0.20, None),  # Rasta
    ("cdab692d-7df0-40fe-a87c-9e67c452117b", 0.40, 0.20, 0.55, 0.20, 0.60, None, None, 0.25),  # Adolescent
    ("d8576bd9-d698-4944-bd92-bc76edf4a003", 0.50, 0.90, 0.30, 0.55, 0.10, None, None, 0.30),  # JARVIS
    ("cea2a505-c932-4834-93e4-9d8f6e76b1dd", 0.65, 0.70, 0.75, 0.45, 0.35, None, 0.15, None),  # Haipai
    ("ef2ec97b-cffc-4c3c-a4ae-1381670b701f", 0.30, 0.35, 0.90, 0.15, 0.55, 0.15, None, 0.40),  # Trump
    ("8d3c8cac-8f69-443e-9dfe-15e883a7c1b8", 0.65, 0.40, 0.50, 0.20, 0.50, None, None, None),  # Antagoniste
]


def upgrade() -> None:
    """Assign Big Five traits + PAD overrides to all 14 personalities."""
    conn = op.get_bind()

    for pid, o, c, e, a, n, pad_p, pad_a, pad_d in PERSONALITY_TRAITS:
        conn.execute(
            text(
                "UPDATE personalities SET "
                "trait_openness = :o, trait_conscientiousness = :c, "
                "trait_extraversion = :e, trait_agreeableness = :a, "
                "trait_neuroticism = :n, "
                "pad_pleasure_override = :pad_p, "
                "pad_arousal_override = :pad_a, "
                "pad_dominance_override = :pad_d "
                "WHERE id = :pid"
            ),
            {"pid": pid, "o": o, "c": c, "e": e, "a": a, "n": n, "pad_p": pad_p, "pad_a": pad_a, "pad_d": pad_d},
        )

    # Sync existing psyche_states with their user's personality traits
    conn.execute(
        text(
            "UPDATE psyche_states ps SET "
            "trait_openness = p.trait_openness, "
            "trait_conscientiousness = p.trait_conscientiousness, "
            "trait_extraversion = p.trait_extraversion, "
            "trait_agreeableness = p.trait_agreeableness, "
            "trait_neuroticism = p.trait_neuroticism "
            "FROM users u "
            "JOIN personalities p ON u.personality_id = p.id "
            "WHERE ps.user_id = u.id "
            "AND p.trait_openness IS NOT NULL"
        )
    )


def downgrade() -> None:
    """Reset all personality traits to NULL (revert to defaults)."""
    conn = op.get_bind()
    conn.execute(
        text(
            "UPDATE personalities SET "
            "trait_openness = NULL, trait_conscientiousness = NULL, "
            "trait_extraversion = NULL, trait_agreeableness = NULL, "
            "trait_neuroticism = NULL, "
            "pad_pleasure_override = NULL, pad_arousal_override = NULL, "
            "pad_dominance_override = NULL"
        )
    )
