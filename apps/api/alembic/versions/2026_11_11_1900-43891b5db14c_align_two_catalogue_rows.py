"""Align two catalogue rows an existing instance held apart from the reference seed.

Revision ID: 43891b5db14c
Revises: 5cccb7a8d77f
Create Date: 2026-11-11 19:00:00.000000

Every door that writes a catalogue row -- the seed bundle and the migrations
that carry it -- inserts the row only where the model is unknown, so a row that
existed before its declaration kept what it had. Two were found on 2026-11-11,
reading production against the bundle:

* ``gemini-2.5-flash-native-audio-preview-09-2025`` is a speech-to-speech model.
  Its row dates from the first Gemini tariffs and carries the ``audio`` kind,
  which the transcription slot requires: the slot offered a bidirectional model
  that cannot transcribe. ``f1a3c5e7b9d2`` declared the live models
  ``realtime`` -- a kind no slot requires -- and never reached this row, on any
  instance. Only a row still carrying ``audio`` is moved: a kind an
  administrator chose stands. Its token limits are left as they are.
* ``deepseek-flash`` declares neither its ladder nor its documentation key
  where an administrator created the row by hand before ``e9b5d7f3a2c4``
  (production, 2026-09-11). An undeclared ladder already resolves to the
  family's, so filling it changes no depth the model can be asked for: the row
  only says what it does, and the administration screen shows the family's
  help again. Each field is filled only where it is empty -- SQL NULL, or the
  JSON null such a row carries -- and a narrowed ladder or a key an
  administrator chose stands.

The values are the seed bundle's; a guard test holds them equal.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "43891b5db14c"
down_revision: str | None = "5cccb7a8d77f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# print() raises UnicodeEncodeError under a CP1252 Windows console (audit F047).
logger = logging.getLogger("alembic.runtime.migration")

LIVE_MODEL = "gemini-2.5-flash-native-audio-preview-09-2025"
#: The kind the row was left with: the one the transcription slot requires.
STALE_KIND = "audio"
#: The kind of a speech-to-speech model, required by no slot.
KIND = "realtime"

DEEPSEEK_MODEL = "deepseek-flash"
#: The family's documented ladder and its documentation key -- the seed's row.
LADDER: list[str] = ["none", "low", "high", "max"]
DOC_KEY = "deepseek_v4"

#: Every value carries its type: asyncpg reads a parameter once per statement (ADR-305).
FIX_KIND = sa.text("""
    UPDATE llm_models
       SET kind = CAST(:kind AS llm_model_kind_enum), updated_at = NOW()
     WHERE model_name = :model_name
       AND kind = CAST(:stale AS llm_model_kind_enum)
    """)

FILL_LADDER = sa.text("""
    UPDATE llm_models
       SET reasoning_enum_values = CAST(:ladder AS jsonb), updated_at = NOW()
     WHERE model_name = :model_name
       AND (reasoning_enum_values IS NULL OR reasoning_enum_values = 'null'::jsonb)
    """)

FILL_DOC_KEY = sa.text("""
    UPDATE llm_models
       SET reasoning_doc_i18n_key = :doc_key, updated_at = NOW()
     WHERE model_name = :model_name
       AND reasoning_doc_i18n_key IS NULL
    """)


def kind_params() -> dict[str, Any]:
    """The bind parameters of the kind correction."""
    return {"model_name": LIVE_MODEL, "kind": KIND, "stale": STALE_KIND}


def ladder_params() -> dict[str, Any]:
    """The bind parameters of the ladder declaration."""
    return {"model_name": DEEPSEEK_MODEL, "ladder": json.dumps(LADDER)}


def doc_key_params() -> dict[str, Any]:
    """The bind parameters of the documentation key."""
    return {"model_name": DEEPSEEK_MODEL, "doc_key": DOC_KEY}


def upgrade() -> None:
    """Move the live model out of the transcription kind; declare what deepseek-flash does."""
    bind = op.get_bind()
    moved = bind.execute(FIX_KIND, kind_params()).rowcount
    declared = bind.execute(FILL_LADDER, ladder_params()).rowcount
    documented = bind.execute(FILL_DOC_KEY, doc_key_params()).rowcount
    logger.info(
        "catalogue alignment: %d kind corrected, %d ladder declared, %d documentation key set",
        moved,
        declared,
        documented,
    )


def downgrade() -> None:
    """Nothing is undone.

    Restoring ``audio`` would offer a live model to the transcription slot
    again, and an emptied ladder would resolve to the very values removed: the
    state before this revision was a defect, not a version of the data.
    """
