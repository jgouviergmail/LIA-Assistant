"""Name who produced each attachment, so a person can find their files (ADR-279).

Every file the assistant produced was stored indistinguishably from something
the person uploaded: nothing listed them, nothing let one be downloaded back a
day later, and a conversation reset deleted the lot.

Three columns and a backfill:

- ``origin`` — NOT NULL with a default, so every pre-existing row answers the
  question. The backfill reads the SHAPE each producer stamped: the image tool
  wrote ``generated_<uuid>.png`` and the streaming layer ``browser_<uuid>.jpg``.
  Documents carry no marker of their own — the generator names them after the
  person's request — so they are recovered from the ``generated_documents``
  metadata of the messages that carry their cards, which is the only place that
  link was ever written.
- ``title`` — what the file is CALLED for a person, when its producer knew.
- ``conversation_id`` — a POINTER, ``SET NULL``: a deleted conversation leaves
  the file listed rather than taking it down or blocking the delete.

Revision ID: 39c7e93d85b1
Revises: c6e1523d8222
Create Date: 2026-09-10 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "39c7e93d85b1"
down_revision: str | None = "c6e1523d8222"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ORIGIN_COMMENT = (
    "Who produced the file: upload | generated_image | generated_document | "
    "browser_screenshot (ADR-279). A conversation reset removes uploads alone."
)
_TITLE_COMMENT = "Human-meaningful name of a generated file; NULL = use original_filename."


def upgrade() -> None:
    """Add the three columns, then recover what the producers left behind."""
    op.add_column(
        "attachments",
        sa.Column(
            "origin",
            sa.String(length=30),
            nullable=False,
            server_default="upload",
            comment=_ORIGIN_COMMENT,
        ),
    )
    op.add_column(
        "attachments",
        sa.Column("title", sa.String(length=200), nullable=True, comment=_TITLE_COMMENT),
    )
    op.add_column(
        "attachments",
        sa.Column("conversation_id", sa.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_attachments_conversation_id_conversations",
        "attachments",
        "conversations",
        ["conversation_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_attachments_user_id_origin_created_at",
        "attachments",
        ["user_id", "origin", "created_at"],
    )

    # --- Images: the producers stamped their prefix on the stored filename ---
    op.execute(
        sa.text(
            "UPDATE attachments SET origin = 'generated_image' "
            "WHERE content_type = 'image' AND stored_filename LIKE 'generated\\_%' ESCAPE '\\'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE attachments SET origin = 'browser_screenshot' "
            "WHERE content_type = 'image' AND stored_filename LIKE 'browser\\_%' ESCAPE '\\'"
        )
    )

    # --- Documents: recovered from the cards that point at them --------------
    # `generated_documents` holds `{"url": "/api/v1/attachments/<id>", ...}`;
    # the id is the last path segment. This is the ONLY place the link between a
    # generated document and its row was ever written, and it also gives the
    # conversation and the filename the person saw.
    op.execute(
        sa.text(
            """
            WITH cards AS (
                SELECT
                    m.conversation_id AS conversation_id,
                    (regexp_match(card->>'url', '([0-9a-fA-F-]{36})$'))[1]::uuid
                        AS attachment_id,
                    card->>'filename' AS filename
                FROM conversation_messages AS m
                CROSS JOIN LATERAL jsonb_array_elements(
                    m.message_metadata->'generated_documents'
                ) AS card
                WHERE jsonb_typeof(m.message_metadata->'generated_documents') = 'array'
                  AND card->>'url' ~ '[0-9a-fA-F-]{36}$'
            )
            UPDATE attachments AS a
            SET origin = 'generated_document',
                title = COALESCE(a.title, cards.filename),
                conversation_id = COALESCE(a.conversation_id, cards.conversation_id)
            FROM cards
            WHERE a.id = cards.attachment_id
              AND a.content_type = 'document'
            """
        )
    )

    # --- Images: the same cards carry the alt text and the conversation ------
    op.execute(
        sa.text(
            """
            WITH cards AS (
                SELECT
                    m.conversation_id AS conversation_id,
                    (regexp_match(card->>'url', '([0-9a-fA-F-]{36})$'))[1]::uuid
                        AS attachment_id,
                    card->>'alt' AS alt
                FROM conversation_messages AS m
                CROSS JOIN LATERAL jsonb_array_elements(
                    m.message_metadata->'generated_images'
                ) AS card
                WHERE jsonb_typeof(m.message_metadata->'generated_images') = 'array'
                  AND card->>'url' ~ '[0-9a-fA-F-]{36}$'
            )
            UPDATE attachments AS a
            SET origin = 'generated_image',
                title = COALESCE(a.title, NULLIF(cards.alt, '')),
                conversation_id = COALESCE(a.conversation_id, cards.conversation_id)
            FROM cards
            WHERE a.id = cards.attachment_id
              AND a.content_type = 'image'
            """
        )
    )


def downgrade() -> None:
    """Drop what was added. Every file returns to being an undifferentiated one."""
    op.drop_index("ix_attachments_user_id_origin_created_at", table_name="attachments")
    op.drop_constraint(
        "fk_attachments_conversation_id_conversations", "attachments", type_="foreignkey"
    )
    op.drop_column("attachments", "conversation_id")
    op.drop_column("attachments", "title")
    op.drop_column("attachments", "origin")
