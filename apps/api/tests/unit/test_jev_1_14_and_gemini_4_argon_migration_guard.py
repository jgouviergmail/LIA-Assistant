"""The Jev 1.14/Argon migration and fresh-install seed carry identical rows.

Argon deliberately uses Google's definitive Standard tariff rather than the
promotion through 2026-11-30. Jev retains the native decision contract, without
the provider's opt-in experimental vision or long context. Sources checked
2026-10-25: https://docs.typesafe.ai/models and
https://ai.google.dev/gemini-api/docs/pricing#gemini-4-argon.

Real PostgreSQL replay covers SQL execution; this guard prevents the two
delivery surfaces and their independently verified vendor values from drifting.
"""

from __future__ import annotations

import importlib.util
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from types import ModuleType

import pytest
from sqlalchemy.sql.elements import TextClause

from tests.unit.infrastructure.llm.reasoning.test_family_coverage import (
    _catalogue_rows,
    _split_values,
)

pytestmark = pytest.mark.unit

_API_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION = (
    _API_ROOT
    / "alembic"
    / "versions"
    / "2026_10_25_1200-8e4c20f65b91_seed_jev_1_14_and_gemini_4_argon.py"
)
_SEED = _API_ROOT.parents[1] / "infrastructure/database/seeds/llm_pricing_seed.sql"
_MODELS = {"jev-1.14.0", "gemini-4-argon"}
_PUBLISHED_PRICES = {
    "jev-1.14.0": (Decimal("0.042"), None, Decimal("0")),
    "gemini-4-argon": (Decimal("4"), Decimal("0.20"), Decimal("20")),
}
_SEED_TARIFF = re.compile(
    r"^\s*\('(?P<model>[^']+)',\s*(?P<input>[0-9.]+),\s*(?P<cached>NULL|[0-9.]+),\s*"
    r"(?P<output>[0-9.]+),\s*'(?P<unit>[a-z_0-9]+)',\s*'(?P<effective>[^']+)',\s*(?P<active>true|false)\)",
    re.M,
)
_MIGRATED_TARIFF = re.compile(
    r"\('(?P<model>[^']+)',\s*(?P<input>[0-9.]+),\s*"
    r"(?P<cached>NULL(?:::numeric)?|[0-9.]+),\s*(?P<output>[0-9.]+)\)"
)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("seed_jev_1_14_and_gemini_4_argon", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _cell(value: str) -> str:
    return value.strip().removesuffix("::jsonb").strip("'")


def _migration_rows(module: ModuleType) -> dict[str, dict[str, str]]:
    sql = str(module.INSERT_MODELS)
    header, values = sql.split(") VALUES", 1)
    columns = _split_values(header.split("INSERT INTO llm_models (", 1)[1])[3:]
    rows = {}
    for match in re.finditer(
        r"\(gen_random_uuid\(\),\s*NOW\(\),\s*NOW\(\),(.*?)\)\s*(?:,|ON CONFLICT)",
        values,
        re.S,
    ):
        fields = _split_values(match.group(1))
        row = dict(zip(columns, (_cell(value) for value in fields), strict=True))
        rows[row["model_name"]] = row
    assert set(rows) == _MODELS, "the guard must parse both complete catalogue rows"
    return rows


def _price(value: str) -> Decimal | None:
    return None if value.startswith("NULL") else Decimal(value)


def test_migration_revision_and_effective_date_are_pinned() -> None:
    module = _load()
    assert module.revision == "8e4c20f65b91"
    assert module.down_revision == "3cb24a85d3f5"
    assert module.EFFECTIVE_FROM == "2026-10-25T00:00:00+00:00"
    assert module.EFFECTIVE_FROM_AT == datetime.fromisoformat(module.EFFECTIVE_FROM)


def test_every_migrated_catalogue_field_equals_its_seed_field() -> None:
    seed_rows = {row["model_name"]: row for row in _catalogue_rows()}
    for name, migrated in _migration_rows(_load()).items():
        row = dict(migrated)
        assert row.pop("capability_provenance") == "verified"
        assert row == {column: _cell(value) for column, value in seed_rows[name].items()}, name
    seed = " ".join(_SEED.read_text(encoding="utf-8").split())
    assert (
        "SET capability_provenance = 'verified' "
        "WHERE model_name IN ('jev-1.14.0', 'gemini-4-argon') "
        "AND model_name IN (SELECT model_name FROM _lia_inserted_models) "
        "AND capability_provenance = 'declared'"
    ) in seed
    assert "ON CONFLICT (model_name) DO NOTHING RETURNING model_name" in seed


def test_jev_keeps_the_native_decision_contract_and_default_context() -> None:
    row = _migration_rows(_load())["jev-1.14.0"]
    assert row["provider"] == "typesafe"
    assert row["kind"] == "decision"
    assert (row["max_input_tokens"], row["max_output_tokens"]) == ("32000", "1")
    assert row["is_active"] == "true"
    assert row["is_reasoning_model"] == "false"
    assert row["reasoning_enum_values"] == row["reasoning_doc_i18n_key"] == "NULL"
    assert all(value == "false" for column, value in row.items() if column.startswith("supports_"))


def test_argon_has_the_synchronous_limits_and_supported_chat_capabilities() -> None:
    row = _migration_rows(_load())["gemini-4-argon"]
    assert row["provider"] == "gemini"
    assert row["kind"] == "chat"
    assert (row["max_input_tokens"], row["max_output_tokens"]) == ("1048576", "65536")
    for column in (
        "supports_tools",
        "supports_structured_output",
        "supports_streaming",
        "supports_vision",
        "is_reasoning_model",
        "is_active",
    ):
        assert row[column] == "true", column
    for column in (
        "supports_strict_mode",
        "supports_temperature",
        "supports_top_p",
        "supports_frequency_penalty",
        "supports_presence_penalty",
    ):
        assert row[column] == "false", column
    assert row["reasoning_enum_values"] == '["low", "medium", "high"]'


def test_tariffs_equal_the_seed_and_the_definitive_vendor_prices() -> None:
    module = _load()
    tariff = str(module.INSERT_TARIFFS)
    migrated = {
        match["model"]: tuple(_price(match[key]) for key in ("input", "cached", "output"))
        for match in _MIGRATED_TARIFF.finditer(tariff)
    }
    assert migrated == _PUBLISHED_PRICES
    assert "'per_1m_tokens', CAST(:effective_from AS timestamptz), true" in tariff
    seed = _SEED.read_text(encoding="utf-8")
    dated = {
        match["model"]: match
        for match in _SEED_TARIFF.finditer(seed)
        if match["model"] in _MODELS and match["effective"] == module.EFFECTIVE_FROM
    }
    assert set(dated) == _MODELS
    for name, expected in _PUBLISHED_PRICES.items():
        row = dated[name]
        assert tuple(_price(row[key]) for key in ("input", "cached", "output")) == expected
        assert row["unit"] == "per_1m_tokens"
        assert row["active"] == "true"


def test_upgrade_only_adds_missing_rows_and_preserves_administered_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load()
    executed: list[tuple[TextClause, dict[str, datetime] | None]] = []

    class RecordingConnection:
        def execute(self, statement: TextClause, params: dict[str, datetime] | None = None) -> None:
            executed.append((statement, params))

    monkeypatch.setattr(module.op, "get_bind", RecordingConnection)
    module.upgrade()
    module.downgrade()  # An additive downgrade must preserve even a pre-existing tariff.
    assert executed == [
        (module.INSERT_MODELS, None),
        (module.INSERT_TARIFFS, {"effective_from": module.EFFECTIVE_FROM_AT}),
    ]
    model_sql = " ".join(str(module.INSERT_MODELS).split())
    assert model_sql.endswith("ON CONFLICT (model_name) DO NOTHING")
    tariff_sql = " ".join(str(module.INSERT_TARIFFS).split())
    assert (
        "WHERE NOT EXISTS ( SELECT 1 FROM llm_model_pricing p "
        "WHERE p.model_id = m.id AND p.is_active )"
    ) in tariff_sql
    assert tariff_sql.split("ON CONFLICT (model_id, effective_from) DO UPDATE", 1)[1].strip() == (
        "SET is_active = true, updated_at = NOW()"
    )
    for statement, _params in executed:
        insert = str(statement).split("ON CONFLICT", 1)[0]
        assert not re.search(r"\b(?:UPDATE|DELETE|TRUNCATE)\b|llm_config_overrides", insert, re.I)
