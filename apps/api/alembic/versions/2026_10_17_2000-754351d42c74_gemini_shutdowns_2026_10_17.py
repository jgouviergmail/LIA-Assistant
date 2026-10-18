"""State the shutdown dates Google announced after the 2026-09-26 alignment.

Revision ID: 754351d42c74
Revises: 1ed6c591761a
Create Date: 2026-10-17 20:00:00.000000

Google's deprecations page (ai.google.dev/gemini-api/docs/deprecations, « Last
updated 2026-10-12 », read 2026-10-17) dates six models the catalogue holds
differently from what ``70fd39bf9e8d`` wrote on 2026-09-26:

* the three speech previews (``gemini-3.1-flash-tts-preview``,
  ``gemini-2.5-flash-preview-tts``, ``gemini-2.5-pro-preview-tts``) and two live
  previews (``gemini-3.1-flash-live-preview``,
  ``gemini-2.5-flash-native-audio-preview-12-2025``) now shut down on
  2026-11-17 — the replacements named are the 3.8 speech and live models;
* ``gemini-2.5-flash-image``, dated 2026-10-02 then, now runs until 2027-03-15:
  the old date, already past, made it a retirement candidate for the catalogue
  sync (``field_mapping.is_retired``).

Every other row of the page matches ``vendor_announcements.VENDOR_SHUTDOWNS``,
which now carries these six, the seed bundle the same (a guard holds the three
equal). The rule of ``70fd39bf9e8d`` holds: the shutdown date follows the
vendor on EVERY row, whatever its provenance — it records what the provider
announced — and Google calls these dates the EARLIEST possible shutdown.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import date

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "754351d42c74"
down_revision: str | None = "1ed6c591761a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")

#: What the page announces for the six rows it now dates differently.
SHUTDOWN_DATES: dict[str, date | None] = {
    "gemini-3.1-flash-tts-preview": date(2026, 11, 17),
    "gemini-2.5-flash-preview-tts": date(2026, 11, 17),
    "gemini-2.5-pro-preview-tts": date(2026, 11, 17),
    "gemini-3.1-flash-live-preview": date(2026, 11, 17),
    "gemini-2.5-flash-native-audio-preview-12-2025": date(2026, 11, 17),
    "gemini-2.5-flash-image": date(2027, 3, 15),
}

#: The date is bound twice, so it is typed twice: under asyncpg an untyped
#: parameter read in two contexts is two types (the ADR-305 trap).
ALIGN_SHUTDOWN_DATE = sa.text("""
    UPDATE llm_models
       SET deprecation_date = CAST(:deprecation_date AS date), updated_at = NOW()
     WHERE model_name = :model_name
       AND deprecation_date IS DISTINCT FROM CAST(:deprecation_date AS date)
    """)


def upgrade() -> None:
    """Date each row the way the vendor's page does."""
    bind = op.get_bind()
    dated = sum(
        bind.execute(ALIGN_SHUTDOWN_DATE, {"model_name": name, "deprecation_date": day}).rowcount
        for name, day in SHUTDOWN_DATES.items()
    )
    logger.info("gemini shutdown dates of 2026-10-17: %d rows dated", dated)


def downgrade() -> None:
    """Nothing is restored.

    The dates this migration replaced are the ones Google's page now
    contradicts: re-installing them would be a regression, not a rollback (the
    rule of ``70fd39bf9e8d`` and ``b1c2d3e4f5a6``).
    """
