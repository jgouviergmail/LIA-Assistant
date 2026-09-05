"""The parameters actually SENT to each model (ADR-263, lot 7).

No new table, on purpose. ``token_usage_logs`` is already the per-call
inference log — one row per LLM call, keyed by the same ``run_id`` the three
registers use, already carrying the model, the configured slot, the latency and
the outcome. A fourth register would have duplicated it.

What was missing is the answer to « with what settings ». LIA holds three
different answers and only one is true: ``llm_config_overrides`` is the mutable
CONFIGURATION, the resolved ``LLMAgentConfig`` is what LIA DECIDED (ADR-245 may
coerce it afterwards), and LangChain's ``invocation_params`` is what was SENT.
These columns hold the third.

Normalised to ONE vocabulary, from a probe of the real adapters: the output cap
is spelled ``max_completion_tokens`` (OpenAI), ``max_tokens`` (Anthropic) and
``max_output_tokens`` (Google), and reasoning has three shapes. Recording the
provider's spelling would give one concept three names.

Nullable with NO backfill, exactly like the ADR-244 observation columns: they
describe calls made after this migration, and inventing history would be worse
than admitting its absence. No index either — these columns are read as part of
a row already found by ``run_id`` or by a period, never searched on their own.

Revision ID: f3c4d5e6a7b8
Revises: e2b3c4d5f6a7
Create Date: 2026-09-04 23:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f3c4d5e6a7b8"
down_revision: str | None = "e2b3c4d5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


#: name -> (type, comment). One declaration, read by both directions.
_COLUMNS: tuple[tuple[str, sa.types.TypeEngine, str], ...] = (
    (
        "provider",
        sa.String(length=40),
        "Client family that answered, as LIA names it (ADR-263 lot 7)",
    ),
    (
        "temperature",
        sa.Float(),
        "Temperature as SENT; NULL when the call set none — 0.0 is a value",
    ),
    ("top_p", sa.Float(), "top_p as sent"),
    (
        "max_output_tokens",
        sa.Integer(),
        "Output cap as sent, whatever the provider calls it",
    ),
    (
        "reasoning_level",
        sa.String(length=20),
        "ADR-245's ladder vocabulary, never a provider spelling",
    ),
    (
        "reasoning_budget_tokens",
        sa.Integer(),
        "Thinking budget as sent, when one was set",
    ),
    (
        "params_digest",
        sa.String(length=64),
        "Digest over EVERY allowlisted parameter, so « was anything else set? » "
        "stays answerable when the readable columns cannot say",
    ),
)


def upgrade() -> None:
    """Add the inference-parameter columns."""
    for name, column_type, comment in _COLUMNS:
        op.add_column(
            "token_usage_logs",
            sa.Column(name, column_type, nullable=True, comment=comment),
        )


def downgrade() -> None:
    """Drop them. Nothing else read them."""
    for name, _, _ in reversed(_COLUMNS):
        op.drop_column("token_usage_logs", name)
