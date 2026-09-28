"""Align the Gemini catalogue on what Google's own site and API state.

Revision ID: 70fd39bf9e8d
Revises: 7b3e9d1f5c2a
Create Date: 2026-09-26 18:00:00.000000

Owner rule of 2026-09-26: the Gemini site is the reference. Read and measured
that day:

* each model page under ai.google.dev/gemini-api/docs/models/<name> — input
  and output token limits, function calling, structured outputs, image input,
  thinking, text in and audio out for the speech models — for the sixteen
  models the pricing page lists;
* the thinking guide (ai.google.dev/gemini-api/docs/thinking) — the levels
  each model accepts (Gemini 2.5 included: low, medium, high);
* the deprecations page (ai.google.dev/gemini-api/docs/deprecations) — the
  announced shutdown dates, for every model it lists. The vendored registry had
  stamped 2026-10-20 on the three Gemini 2.5 chat models, which Google says
  « will continue to be served until further notice »;
* the API's own model list (``GET /v1beta/models``, free) — which names it
  still serves. Google calls a shutdown date the EARLIEST possible one: only
  the list proves a model gone, and it still served three models whose date is
  past (``gemini-3.1-flash-lite-preview``, ``gemini-3-pro-image-preview``,
  ``gemini-embedding-2-preview``), which therefore stay.

Rules, all about not overriding a human decision (ADR-244):

* a model of the sixteen the catalogue lacks is inserted, ``verified`` — a
  fresh install otherwise got the seed's row as ``declared``, whose window the
  runtime refuses to trust;
* its capabilities are rewritten only on a row no human curated (``declared``
  or ``imported``), which then becomes ``verified``; a ``verified`` row stands;
* the shutdown date follows the vendor on EVERY row, whatever its provenance:
  it records what the provider announced (``sync_diff.CORRECTABLE_FIELDS``);
* a model the API no longer serves is deactivated with its tariff — unless a
  slot is configured on it, since deactivating a referenced model is the trap
  ADR-244 names. That includes ``gemini-3.1-flash-preview-tts``, a name the API
  never served (the model is ``gemini-3.1-flash-tts-preview``);
* the two Google embedding models the seed filed under ``openai`` are filed
  under ``gemini``.

The seed bundle carries the same values (a guard test holds the two equal);
the sampling flags are the seed's — no page states them per model.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "70fd39bf9e8d"
down_revision: str | None = "7b3e9d1f5c2a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# print() raises UnicodeEncodeError under a CP1252 Windows console (audit F047).
logger = logging.getLogger("alembic.runtime.migration")

PROVENANCE = "verified"

_FULL_LADDER = ["minimal", "low", "medium", "high"]
_NO_MINIMAL = ["low", "medium", "high"]


def _chat(
    sampling: tuple[bool, bool, bool, bool], ladder: list[str], doc_key: str | None
) -> dict[str, Any]:
    """A Gemini chat row: every model page states the same limits and abilities.

    Args:
        sampling: The seed's temperature, top_p, frequency and presence flags.
        ladder: The thinking levels the guide lists for the model.
        doc_key: The seed's reasoning documentation key.

    Returns:
        One full catalogue row, column names the seed's.
    """
    temperature, top_p, frequency, presence = sampling
    return {
        "provider": "gemini",
        "max_input_tokens": 1_048_576,
        "max_output_tokens": 65_536,
        "supports_tools": True,
        "supports_structured_output": True,
        "supports_strict_mode": False,
        "supports_streaming": True,
        "supports_vision": True,
        "is_reasoning_model": True,
        "supports_temperature": temperature,
        "supports_top_p": top_p,
        "supports_frequency_penalty": frequency,
        "supports_presence_penalty": presence,
        "kind": "chat",
        "reasoning_enum_values": ladder,
        "reasoning_doc_i18n_key": doc_key,
        "is_active": True,
    }


#: A Gemini speech row: text in, audio out, no tool, no schema, no thinking.
_SPEECH: dict[str, Any] = {
    "provider": "gemini",
    "max_input_tokens": 8_192,
    "max_output_tokens": 16_384,
    "supports_tools": False,
    "supports_structured_output": False,
    "supports_strict_mode": False,
    "supports_streaming": True,
    "supports_vision": False,
    "is_reasoning_model": False,
    "supports_temperature": False,
    "supports_top_p": False,
    "supports_frequency_penalty": False,
    "supports_presence_penalty": False,
    "kind": "tts",
    "reasoning_enum_values": None,
    "reasoning_doc_i18n_key": None,
    "is_active": True,
}
#: The sampling flags of the seed: no penalty up to Gemini 3.1, all four from 3.5.
_NO_PENALTY = (True, True, False, False)
_ALL_SAMPLING = (True, True, True, True)

#: The sixteen models the pricing page lists, one full seed row each. The
#: ladders are the thinking guide's, except gemini-3.1-flash-lite which that
#: guide omits (its preview's, corroborated by langchain-google-genai).
CATALOGUE: dict[str, dict[str, Any]] = {
    "gemini-3.8-flash": _chat(_ALL_SAMPLING, _NO_MINIMAL, None),
    "gemini-3.7-flash": _chat(_ALL_SAMPLING, _NO_MINIMAL, None),
    "gemini-3.6-flash": _chat(_ALL_SAMPLING, _FULL_LADDER, None),
    "gemini-3.5-flash": _chat(_ALL_SAMPLING, _FULL_LADDER, None),
    "gemini-3.5-flash-lite": _chat(_ALL_SAMPLING, _FULL_LADDER, None),
    "gemini-3.1-flash-lite": _chat(_NO_PENALTY, _FULL_LADDER, None),
    "gemini-3.1-pro-preview": _chat(_NO_PENALTY, _NO_MINIMAL, "gemini_3_x_pro"),
    "gemini-3-flash-preview": _chat(_NO_PENALTY, _FULL_LADDER, "gemini_3_x_flash"),
    "gemini-2.5-pro": _chat(_NO_PENALTY, _NO_MINIMAL, "gemini_2_5_pro"),
    "gemini-2.5-flash": _chat(_NO_PENALTY, _NO_MINIMAL, "gemini_2_5"),
    "gemini-2.5-flash-lite": _chat(_NO_PENALTY, _NO_MINIMAL, "gemini_2_5_lite"),
    "gemini-3.8-flash-tts": _SPEECH,
    "gemini-3.8-flash-lite-tts": _SPEECH,
    "gemini-3.1-flash-tts-preview": _SPEECH,
    "gemini-2.5-flash-preview-tts": _SPEECH,
    "gemini-2.5-pro-preview-tts": _SPEECH,
}

#: The capability columns a curated row keeps and an uncurated one takes.
CAPABILITY_COLUMNS: tuple[str, ...] = (
    "max_input_tokens",
    "max_output_tokens",
    "supports_tools",
    "supports_structured_output",
    "supports_vision",
    "is_reasoning_model",
    "kind",
    "reasoning_enum_values",
)

#: The deprecations page, for every model it lists that the catalogue may hold
#: (``None``: listed, no shutdown announced). Two names as the API spells them:
#: the page writes « gemini-2.5-flash-preview-09-25 » and « embedding-2-preview ».
SHUTDOWN_DATES: dict[str, date | None] = {
    "gemini-3.8-flash": None,
    "gemini-3.8-flash-tts": None,
    "gemini-3.8-flash-lite-tts": None,
    "gemini-3.8-live": None,
    "gemini-3.8-live-extended-thinking": None,
    "gemini-3.7-flash": None,
    "gemini-3.6-flash": None,
    "gemini-3.5-flash": None,
    "gemini-3.5-flash-lite": None,
    "gemini-3.1-flash-lite": date(2027, 5, 7),
    "gemini-3.1-flash-lite-preview": date(2026, 5, 25),
    "gemini-3.1-flash-tts-preview": None,
    "gemini-3.1-flash-live-preview": None,
    "gemini-3.1-pro-preview": None,
    "gemini-3-flash-preview": None,
    "gemini-3-pro-preview": date(2026, 3, 9),
    "gemini-3-pro-image-preview": date(2026, 6, 25),
    "gemini-2.5-pro": None,
    "gemini-2.5-pro-preview-tts": None,
    "gemini-2.5-flash": None,
    "gemini-2.5-flash-preview-tts": None,
    "gemini-2.5-flash-preview-09-2025": date(2026, 2, 17),
    "gemini-2.5-flash-image": date(2026, 10, 2),
    "gemini-2.5-flash-image-preview": date(2026, 1, 15),
    "gemini-2.5-flash-lite": None,
    "gemini-2.5-flash-lite-preview-09-2025": date(2026, 3, 31),
    "gemini-2.5-flash-native-audio-preview-12-2025": None,
    "gemini-2.0-flash": date(2026, 6, 1),
    "gemini-2.0-flash-001": date(2026, 6, 1),
    "gemini-2.0-flash-lite": date(2026, 6, 1),
    "gemini-2.0-flash-lite-001": date(2026, 6, 1),
    "gemini-2.0-flash-live-001": date(2025, 12, 9),
    "gemini-2.0-flash-preview-image-generation": date(2025, 11, 14),
    "gemini-embedding-2": None,
    "gemini-embedding-2-preview": date(2026, 8, 10),
    "gemini-embedding-001": date(2028, 5, 14),
    "text-embedding-004": date(2026, 1, 14),
    "embedding-001": date(2025, 10, 30),
}

#: Catalogue models absent from the API's own list (``GET /v1beta/models``,
#: measured 2026-09-26). Each but two is past its announced shutdown; the
#: experimental ``gemini-2.0-flash-exp`` was never on the page, and
#: ``gemini-3.1-flash-preview-tts`` is a name the API never served.
NOT_SERVED: tuple[str, ...] = (
    "gemini-2.0-flash",
    "gemini-2.0-flash-001",
    "gemini-2.0-flash-exp",
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash-lite-001",
    "gemini-2.0-flash-live-001",
    "gemini-2.0-flash-preview-image-generation",
    "gemini-2.5-flash-image-preview",
    "gemini-2.5-flash-lite-preview-09-2025",
    "gemini-2.5-flash-preview-09-2025",
    "gemini-3-pro-preview",
    "gemini-3.1-flash-preview-tts",
    "text-embedding-004",
    "embedding-001",
)

#: Google's embedding models the seed filed under another provider.
GOOGLE_EMBEDDINGS: tuple[str, ...] = ("text-embedding-004", "embedding-001")

#: ``id`` and the timestamps are written explicitly: the ORM declares only
#: client-side defaults for them, so a schema built from the models (the
#: integration tests') has no server default to fall back on.
INSERT_MODEL = sa.text("""
    INSERT INTO llm_models (
        id, created_at, updated_at,
        provider, model_name, max_input_tokens, max_output_tokens,
        supports_tools, supports_structured_output, supports_strict_mode,
        supports_streaming, supports_vision, is_reasoning_model,
        supports_temperature, supports_top_p, supports_frequency_penalty,
        supports_presence_penalty, kind, reasoning_enum_values,
        reasoning_doc_i18n_key, is_active, capability_provenance
    ) VALUES (
        gen_random_uuid(), NOW(), NOW(),
        :provider, :model_name, :max_input_tokens, :max_output_tokens,
        :supports_tools, :supports_structured_output, :supports_strict_mode,
        :supports_streaming, :supports_vision, :is_reasoning_model,
        :supports_temperature, :supports_top_p, :supports_frequency_penalty,
        :supports_presence_penalty, CAST(:kind AS llm_model_kind_enum),
        CAST(:reasoning_enum_values AS jsonb), :reasoning_doc_i18n_key, :is_active,
        CAST(:capability_provenance AS llm_capability_provenance_enum)
    )
    ON CONFLICT (model_name) DO NOTHING
    """)

ALIGN_CAPABILITIES = sa.text("""
    UPDATE llm_models
       SET max_input_tokens = :max_input_tokens,
           max_output_tokens = :max_output_tokens,
           supports_tools = :supports_tools,
           supports_structured_output = :supports_structured_output,
           supports_vision = :supports_vision,
           is_reasoning_model = :is_reasoning_model,
           kind = CAST(:kind AS llm_model_kind_enum),
           reasoning_enum_values = CAST(:reasoning_enum_values AS jsonb),
           capability_provenance = CAST(:capability_provenance AS llm_capability_provenance_enum),
           updated_at = NOW()
     WHERE model_name = :model_name
       AND capability_provenance <> CAST(:capability_provenance AS llm_capability_provenance_enum)
    """)

#: The date is bound twice, so it is typed twice: under asyncpg an untyped
#: parameter read in two contexts is two types (the ADR-305 trap).
ALIGN_SHUTDOWN_DATE = sa.text("""
    UPDATE llm_models
       SET deprecation_date = CAST(:deprecation_date AS date), updated_at = NOW()
     WHERE model_name = :model_name
       AND deprecation_date IS DISTINCT FROM CAST(:deprecation_date AS date)
    """)

DEACTIVATE_NOT_SERVED = sa.text("""
    UPDATE llm_models m
       SET is_active = false, updated_at = NOW()
     WHERE m.model_name = :model_name
       AND m.is_active
       AND NOT EXISTS (SELECT 1 FROM llm_config_overrides o WHERE o.model = m.model_name)
    """)

RETIRE_NOT_SERVED_TARIFF = sa.text("""
    UPDATE llm_model_pricing p
       SET is_active = false, updated_at = NOW()
      FROM llm_models m
     WHERE m.id = p.model_id
       AND m.model_name = :model_name
       AND NOT m.is_active
       AND p.is_active
    """)

FILE_UNDER_GEMINI = sa.text("""
    UPDATE llm_models
       SET provider = 'gemini', updated_at = NOW()
     WHERE model_name = :model_name
       AND provider <> 'gemini'
    """)


def model_params(model_name: str) -> dict[str, Any]:
    """The bind parameters of one catalogue row (insert and alignment alike).

    Args:
        model_name: A key of :data:`CATALOGUE`.

    Returns:
        The row with its ladder serialised, its name and its provenance added.
    """
    row = CATALOGUE[model_name]
    ladder = row["reasoning_enum_values"]
    return {
        **row,
        "model_name": model_name,
        "reasoning_enum_values": None if ladder is None else json.dumps(ladder),
        "capability_provenance": PROVENANCE,
    }


def upgrade() -> None:
    """Insert, align, date, retire and refile — each where Google's evidence says so."""
    bind = op.get_bind()
    inserted = sum(bind.execute(INSERT_MODEL, model_params(name)).rowcount for name in CATALOGUE)
    aligned = sum(
        bind.execute(ALIGN_CAPABILITIES, model_params(name)).rowcount for name in CATALOGUE
    )
    dated = sum(
        bind.execute(ALIGN_SHUTDOWN_DATE, {"model_name": name, "deprecation_date": day}).rowcount
        for name, day in SHUTDOWN_DATES.items()
    )
    retired = 0
    for name in NOT_SERVED:
        retired += bind.execute(DEACTIVATE_NOT_SERVED, {"model_name": name}).rowcount
        bind.execute(RETIRE_NOT_SERVED_TARIFF, {"model_name": name})
    refiled = sum(
        bind.execute(FILE_UNDER_GEMINI, {"model_name": name}).rowcount for name in GOOGLE_EMBEDDINGS
    )
    logger.info(
        "gemini catalogue aligned on google: %d inserted, %d curated, %d dated, "
        "%d deactivated, %d refiled",
        inserted,
        aligned,
        dated,
        retired,
        refiled,
    )


def downgrade() -> None:
    """Nothing is restored.

    The values this migration replaced are the ones Google's pages and API
    contradict: re-installing a shutdown date the vendor never announced, a
    token limit it does not state, or a model it no longer serves would be a
    regression, not a rollback (the rule of ``b1c2d3e4f5a6``). A row it
    inserted stays: a slot may have been configured on it since.
    """
