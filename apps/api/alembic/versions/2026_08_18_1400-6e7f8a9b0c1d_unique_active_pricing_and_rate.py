"""Make the active tariff unique per model, and the active rate unique per pair.

Both tables carried an implicit invariant that nothing enforced: *exactly one
row is active at a time*. ``LLMModelService.update`` respects it, but the seed
inserted with ``ON CONFLICT DO NOTHING`` without retiring the previous row, and
the admin currency route deactivated only the first of N. The result, measured
in the development database on 2026-08-18: 96 of 114 active models carried two
or three active tariffs, and the two read paths disagreed on the price — a
factor 4 on ``gemini-2.5-flash-preview-tts`` and a *unit* change on
``scribe_v2`` (audio hour vs million tokens).

This migration collapses only what it can collapse **without inventing a
price**: duplicates whose priced fields are strictly identical. When two active
rows genuinely disagree, it stops and names them. The "keep the most recent"
heuristic was tested against the four real divergent cases and is wrong in four
of four — production, the authority, holds the *older* values.

Production carried zero duplicates when measured, so the collapse is a no-op
there and only the indexes are created.

Revision ID: 6e7f8a9b0c1d
Revises: 5d6e7f8a9b0c
Create Date: 2026-08-18 14:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text as sa_text
from sqlalchemy.engine import Connection

# revision identifiers, used by Alembic.
revision: str = "6e7f8a9b0c1d"
down_revision: str | None = "5d6e7f8a9b0c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


#: Active pricing rows that disagree on at least one priced field. These are
#: never resolved automatically — a migration must not choose a price.
DETECT_DIVERGENT_PRICING_SQL = """
SELECT m.model_name,
       count(*) AS active_rows,
       count(DISTINCT (p.input_unit_price, p.cached_input_unit_price,
                       p.output_unit_price, p.pricing_unit, p.time_slots)) AS distinct_shapes
FROM llm_model_pricing p
JOIN llm_models m ON m.id = p.model_id
WHERE p.is_active
GROUP BY m.model_name
HAVING count(DISTINCT (p.input_unit_price, p.cached_input_unit_price,
                       p.output_unit_price, p.pricing_unit, p.time_slots)) > 1
ORDER BY m.model_name
"""

#: Retire every active duplicate but the most recent, for models whose active
#: rows are strictly identical. No information is lost: the survivors carry the
#: same priced fields, and the retired rows remain as history.
COLLAPSE_IDENTICAL_PRICING_SQL = """
WITH identical AS (
    SELECT model_id
    FROM llm_model_pricing
    WHERE is_active
    GROUP BY model_id
    HAVING count(*) > 1
       AND count(DISTINCT (input_unit_price, cached_input_unit_price,
                           output_unit_price, pricing_unit, time_slots)) = 1
),
survivors AS (
    SELECT DISTINCT ON (p.model_id) p.id
    FROM llm_model_pricing p
    JOIN identical i ON i.model_id = p.model_id
    WHERE p.is_active
    ORDER BY p.model_id, p.effective_from DESC, p.id DESC
)
UPDATE llm_model_pricing p
SET is_active = false
FROM identical i
WHERE p.model_id = i.model_id
  AND p.is_active
  AND p.id NOT IN (SELECT id FROM survivors)
"""

#: Exchange-rate pairs whose active rows disagree on the rate itself.
DETECT_DIVERGENT_RATES_SQL = """
SELECT from_currency, to_currency, count(*) AS active_rows,
       count(DISTINCT rate) AS distinct_rates
FROM currency_exchange_rates
WHERE is_active
GROUP BY from_currency, to_currency
HAVING count(DISTINCT rate) > 1
ORDER BY from_currency, to_currency
"""

COLLAPSE_IDENTICAL_RATES_SQL = """
WITH identical AS (
    SELECT from_currency, to_currency
    FROM currency_exchange_rates
    WHERE is_active
    GROUP BY from_currency, to_currency
    HAVING count(*) > 1 AND count(DISTINCT rate) = 1
),
survivors AS (
    SELECT DISTINCT ON (c.from_currency, c.to_currency) c.id
    FROM currency_exchange_rates c
    JOIN identical i
      ON i.from_currency = c.from_currency AND i.to_currency = c.to_currency
    WHERE c.is_active
    ORDER BY c.from_currency, c.to_currency, c.effective_from DESC, c.id DESC
)
UPDATE currency_exchange_rates c
SET is_active = false
FROM identical i
WHERE c.from_currency = i.from_currency
  AND c.to_currency = i.to_currency
  AND c.is_active
  AND c.id NOT IN (SELECT id FROM survivors)
"""

#: Only USD->EUR is ever read (``get_active_currency_rate`` is called with that
#: pair alone). The other pairs are manual leftovers that no code path consults;
#: leaving them active would keep dead rows under a fresh uniqueness constraint.
DEACTIVATE_UNREAD_RATE_PAIRS_SQL = """
UPDATE currency_exchange_rates
SET is_active = false
WHERE is_active
  AND NOT (from_currency = 'USD' AND to_currency = 'EUR')
"""


def _abort_on_divergence(bind: Connection) -> None:
    """Stop the migration when two active rows disagree on a price.

    Raises:
        RuntimeError: listing every unresolved model or currency pair, with the
            query to inspect them. Resolution is a human decision: pick the row
            that reflects what the provider actually bills, deactivate the
            others, then run the migration again.
    """
    divergent_models = list(bind.execute(sa_text(DETECT_DIVERGENT_PRICING_SQL)))
    divergent_rates = list(bind.execute(sa_text(DETECT_DIVERGENT_RATES_SQL)))

    if not divergent_models and not divergent_rates:
        return

    lines = [
        "Cannot enforce a single active tariff: some rows disagree on the price.",
        "A migration must never choose between two prices — resolve them first.",
        "",
    ]
    if divergent_models:
        lines.append("Models with divergent active tariffs:")
        lines += [
            f"  - {row[0]} ({row[1]} active rows, {row[2]} distinct price shapes)"
            for row in divergent_models
        ]
        lines += [
            "",
            "Inspect them with:",
            "  SELECT m.model_name, p.id, p.input_unit_price, p.cached_input_unit_price,",
            "         p.output_unit_price, p.pricing_unit, p.time_slots, p.effective_from",
            "  FROM llm_model_pricing p JOIN llm_models m ON m.id = p.model_id",
            "  WHERE p.is_active AND m.model_name IN (...)",
            "  ORDER BY m.model_name, p.effective_from DESC;",
            "",
            "Then deactivate the rows that do NOT reflect the provider's billing:",
            "  UPDATE llm_model_pricing SET is_active = false WHERE id IN (...);",
        ]
    if divergent_rates:
        lines.append("Currency pairs with divergent active rates:")
        lines += [f"  - {row[0]}->{row[1]} ({row[2]} active rows)" for row in divergent_rates]
    raise RuntimeError("\n".join(lines))


def upgrade() -> None:
    """Collapse safe duplicates, refuse unsafe ones, then constrain both tables."""
    bind = op.get_bind()

    bind.execute(sa_text(COLLAPSE_IDENTICAL_PRICING_SQL))
    bind.execute(sa_text(COLLAPSE_IDENTICAL_RATES_SQL))
    bind.execute(sa_text(DEACTIVATE_UNREAD_RATE_PAIRS_SQL))

    # Runs AFTER the collapse: only genuinely conflicting rows can remain.
    _abort_on_divergence(bind)

    op.execute(
        "CREATE UNIQUE INDEX uq_llm_model_pricing_active "
        "ON llm_model_pricing (model_id) WHERE is_active"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_currency_rate_active "
        "ON currency_exchange_rates (from_currency, to_currency) WHERE is_active"
    )


def downgrade() -> None:
    """Drop both indexes.

    The collapse is deliberately not reverted: reactivating rows known to be
    duplicates would restore the very defect this migration removes, and the
    retired rows remain readable as history.
    """
    op.execute("DROP INDEX IF EXISTS uq_currency_rate_active")
    op.execute("DROP INDEX IF EXISTS uq_llm_model_pricing_active")
