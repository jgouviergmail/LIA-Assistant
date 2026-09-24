"""DeepSeek bills its peak windows Monday to Friday: the windows learn their days.

Revision ID: e4a7c2f9b1d6
Revises: d8b6c4e2f0a1
Create Date: 2026-09-23 12:00:00.000000

The vendor's pricing page (api-docs.deepseek.com/quick_start/pricing, read
2026-09-23): « Peak hours are 01:00 - 04:00 and 06:00 - 10:00 UTC, Monday
through Friday, excluding Chinese public holidays » — « All other hours are
off-peak, including weekends ». Time slots had no day (ADR-223), so every
weekend call inside those hours was priced at peak: twice what the vendor
bills, and twice what it takes from the account and instance ceilings.

Slots now carry ``weekdays`` (ADR-223 amendment, 2026-09-23). This migration
adds Monday-Friday to the vendor's two windows on every DeepSeek tariff that
carries them — ``deepseek-flash``, ``deepseek-v4-flash`` and
``deepseek-v4-pro`` on the instances measured, the last one entered through
the admin UI, which is why the rule keys on the PROVIDER rather than a list
of names that had already missed it:

- only the ACTIVE tariff, in place: the vendor never billed a weekend at
  peak, so the row gains accuracy; a superseded row stays the history it is;
- only the windows whose hours are the vendor's and that carry no day yet —
  a window an administrator reshaped is theirs, and a second run changes
  nothing;
- Chinese public holidays stay out (owner decision 2026-09-23): no calendar,
  those days remain priced at peak.

Production never replays the seed bundle, so what an upgraded instance gets
travels here; a guard test holds the bundle's windows equal to this rule.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e4a7c2f9b1d6"
down_revision: str | None = "d8b6c4e2f0a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# print() raises UnicodeEncodeError under a CP1252 Windows console (audit F047).
logger = logging.getLogger("alembic.runtime.migration")

#: The provider whose peak windows are weekday-only.
PROVIDER = "deepseek"
#: The vendor's peak windows, UTC ``(start, end)``.
VENDOR_WINDOWS: tuple[tuple[str, str], ...] = (("01:00", "04:00"), ("06:00", "10:00"))
#: Monday to Friday, as ISO weekdays (``pricing_time_slots`` semantics).
WEEKDAYS: list[int] = [1, 2, 3, 4, 5]

_IS_VENDOR_WINDOW = "(slot->>'start_utc', slot->>'end_utc') IN ({})".format(
    ", ".join(f"(:start_{index}, :end_{index})" for index in range(len(VENDOR_WINDOWS)))
)

#: Monday-Friday onto every vendor window that names no day, on the active
#: DeepSeek tariffs. The EXISTS keeps a re-run from touching a row it already
#: settled, so ``updated_at`` only moves where a window did.
ADD_WEEKDAYS = sa.text(f"""
    UPDATE llm_model_pricing p
       SET time_slots = (
               SELECT jsonb_agg(
                          CASE
                              WHEN slot->'weekdays' IS NULL AND {_IS_VENDOR_WINDOW}
                              THEN slot || jsonb_build_object('weekdays', CAST(:weekdays AS jsonb))
                              ELSE slot
                          END
                          ORDER BY position)
                 FROM jsonb_array_elements(p.time_slots) WITH ORDINALITY AS t(slot, position)
           ),
           updated_at = NOW()
      FROM llm_models m
     WHERE m.id = p.model_id
       AND CAST(m.provider AS text) = :provider
       AND p.is_active
       AND jsonb_typeof(p.time_slots) = 'array'
       AND EXISTS (
               SELECT 1 FROM jsonb_array_elements(p.time_slots) AS s(slot)
                WHERE slot->'weekdays' IS NULL AND {_IS_VENDOR_WINDOW}
           )
    """)

#: The inverse of a new column, not of this rule: EVERY day of every window,
#: whoever wrote it. The revision before this one reads no ``weekdays`` — its
#: ``TimeSlotPrice`` forbids unknown keys, so one day left behind (an
#: administrator's since the upgrade included) fails its admin listing — and its
#: pricing ignored the days anyway, so taking them back changes no price there.
REMOVE_WEEKDAYS = sa.text("""
    UPDATE llm_model_pricing p
       SET time_slots = (
               SELECT jsonb_agg(slot - 'weekdays' ORDER BY position)
                 FROM jsonb_array_elements(p.time_slots) WITH ORDINALITY AS t(slot, position)
           ),
           updated_at = NOW()
     WHERE jsonb_typeof(p.time_slots) = 'array'
       AND EXISTS (
               SELECT 1 FROM jsonb_array_elements(p.time_slots) AS s(slot)
                WHERE slot->'weekdays' IS NOT NULL
           )
    """)


def statement_params() -> dict[str, str]:
    """The bind parameters the upgrade statement takes."""
    params = {"provider": PROVIDER, "weekdays": json.dumps(WEEKDAYS)}
    for index, (start, end) in enumerate(VENDOR_WINDOWS):
        params[f"start_{index}"] = start
        params[f"end_{index}"] = end
    return params


def upgrade() -> None:
    """Give the vendor's peak windows their weekdays on the active DeepSeek tariffs."""
    settled = op.get_bind().execute(ADD_WEEKDAYS, statement_params()).rowcount
    logger.info("deepseek peak weekdays: %d active tariffs settled", settled)


def downgrade() -> None:
    """Take every weekday back: the previous revision cannot read one."""
    rewritten = op.get_bind().execute(REMOVE_WEEKDAYS).rowcount
    logger.info("deepseek peak weekdays: days removed from %d tariffs", rewritten)
