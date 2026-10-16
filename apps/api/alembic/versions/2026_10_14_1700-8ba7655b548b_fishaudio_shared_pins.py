"""Pin public Fish Audio voices once, for every voice slot (ADR-345 amendment 2026-10-14).

Revision ID: 8ba7655b548b
Revises: a9326a120b55
Create Date: 2026-10-14 17:00:00.000000

The pins lived in each TTS slot's ``provider_config.pinned_voices``: a voice
pinned for the chat was not offered to the radio. They become ONE list
(``fishaudio_pinned_voices``). The upgrade moves what the two slots held — the
chat's first, each id once, at most the published ceiling — under the
administrator who last saved the slot, then removes the key nothing reads any
more. The downgrade writes the list back into both slots.

Self-contained on purpose: the id rule and the ceiling are the values of this
release, written here rather than imported, so a later change cannot rewrite
what this migration did. A slot's JSON is written back the way the admin form
writes it (keys sorted, no spaces), so no setting reads as modified.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "8ba7655b548b"
down_revision: str | None = "a9326a120b55"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_VOICE_ID_COMMENT = "The vendor's public model id (32 lowercase hexadecimal characters)."
_PINNED_BY_COMMENT = "The administrator who pinned it; NULL once their account is gone."

#: The voice slots that held pins, in the order their pins are kept.
_SLOTS = ("voice_tts", "radio_voice")
_VOICE_ID = re.compile(r"[0-9a-f]{32}")
_PINS_MAX = 20
_KEY = "pinned_voices"

_SELECT_SLOTS = sa.text(
    "SELECT llm_type, provider_config, updated_by FROM llm_config_overrides "
    "WHERE llm_type IN ('voice_tts', 'radio_voice')"
)
_UPDATE_SLOT = sa.text(
    "UPDATE llm_config_overrides SET provider_config = :config WHERE llm_type = :slot"
)


def _config(raw: str | None) -> dict[str, Any] | None:
    """A slot's ``provider_config`` as an object, or ``None`` when it holds none."""
    try:
        parsed = json.loads(raw) if raw else None
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _serialised(config: dict[str, Any]) -> str:
    """The JSON the admin form writes: keys sorted at every level, no spaces."""
    return json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def upgrade() -> None:
    """Create the shared list, move the slots' pins into it, drop the key from the slots."""
    op.create_table(
        "fishaudio_pinned_voices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "voice_id",
            sa.String(32),
            nullable=False,
            unique=True,
            comment=_VOICE_ID_COMMENT,
        ),
        sa.Column(
            "pinned_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            comment=_PINNED_BY_COMMENT,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    bind = op.get_bind()
    rows = sorted(bind.execute(_SELECT_SLOTS), key=lambda row: _SLOTS.index(row.llm_type))
    moved: dict[str, Any] = {}
    for row in rows:
        config = _config(row.provider_config)
        if config is None or _KEY not in config:
            continue
        pins = config.pop(_KEY)
        for pin in pins if isinstance(pins, list) else []:
            fresh = isinstance(pin, str) and _VOICE_ID.fullmatch(pin) and pin not in moved
            if fresh and len(moved) < _PINS_MAX:
                moved[pin] = row.updated_by
        bind.execute(_UPDATE_SLOT, {"config": _serialised(config), "slot": row.llm_type})
    # A microsecond apart, so the shared list keeps the slots' order.
    now = datetime.now(UTC)
    for order, (voice_id, pinned_by) in enumerate(moved.items()):
        bind.execute(
            sa.text(
                "INSERT INTO fishaudio_pinned_voices "
                "(id, voice_id, pinned_by, created_at, updated_at) "
                "VALUES (:id, :voice_id, :pinned_by, :created_at, :created_at)"
            ),
            {
                "id": uuid.uuid4(),
                "voice_id": voice_id,
                "pinned_by": pinned_by,
                "created_at": now + timedelta(microseconds=order),
            },
        )


def downgrade() -> None:
    """Write the shared list back into both slots, then drop it."""
    bind = op.get_bind()
    pins = [
        row.voice_id
        for row in bind.execute(
            sa.text("SELECT voice_id FROM fishaudio_pinned_voices ORDER BY created_at, id")
        )
    ]
    if pins:
        for row in list(bind.execute(_SELECT_SLOTS)):
            config = _config(row.provider_config)
            if config is None:
                continue
            config[_KEY] = pins
            bind.execute(_UPDATE_SLOT, {"config": _serialised(config), "slot": row.llm_type})
    op.drop_table("fishaudio_pinned_voices")
