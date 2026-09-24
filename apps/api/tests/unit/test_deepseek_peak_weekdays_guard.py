"""Guard: the seed bundle's DeepSeek windows are what the weekday migration writes.

Production never replays the bundle — migration ``e4a7c2f9b1d6`` is what an
upgraded instance gets — while a fresh install and the demonstrator (rebuilt
from the bundle at every boot) get the bundle. If the two drifted, a Saturday
call at 02:00 UTC would cost twice as much depending on how the instance was
born. The migration's SQL itself runs on a real PostgreSQL in
``tests/integration/test_deepseek_peak_weekdays_migration.py``.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from src.domains.llm.pricing_time_slots import (
    TimeSlotPrice,
    canonical_weekdays,
    validate_time_slot_list,
)
from tests.unit.infrastructure.llm.reasoning.test_family_coverage import _catalogue_rows

pytestmark = pytest.mark.unit

_API_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION = (
    _API_ROOT / "alembic" / "versions" / "2026_09_23_1200-e4a7c2f9b1d6_deepseek_peak_weekdays.py"
)
_SEED = _API_ROOT.parents[1] / "infrastructure" / "database" / "seeds" / "llm_pricing_seed.sql"

#: One windowed-tariff block of the bundle: its windows and the model they price.
_WINDOWS_BLOCK = re.compile(
    r"time_slots = '(?P<slots>\[.*?\])'::jsonb\s+FROM llm_models m\s+"
    r"WHERE m\.id = p\.model_id AND m\.model_name = '(?P<model>[^']+)' AND p\.is_active;",
    re.S,
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("deepseek_peak_weekdays", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _bundle_windows() -> list[tuple[str, list[dict[str, Any]]]]:
    seed = _SEED.read_text(encoding="utf-8")
    return [(m.group("model"), json.loads(m.group("slots"))) for m in _WINDOWS_BLOCK.finditer(seed)]


def test_the_migration_chains_after_the_oauth_grants_head() -> None:
    module = _load_migration()
    assert module.revision == "e4a7c2f9b1d6"
    assert module.down_revision == "d8b6c4e2f0a1"


def test_the_migration_writes_the_one_spelling_the_application_reads() -> None:
    """A non-canonical list would read as an edit in every later diff."""
    weekdays = _load_migration().WEEKDAYS
    assert canonical_weekdays(weekdays) == weekdays


def test_every_deepseek_vendor_window_of_the_bundle_is_weekday_only() -> None:
    migration = _load_migration()
    providers = {row["model_name"]: row["provider"] for row in _catalogue_rows()}
    deepseek = [
        (model, slots)
        for model, slots in _bundle_windows()
        if providers.get(model) == migration.PROVIDER
    ]

    # flash, v4-flash and v4-pro: a parser matching nothing would prove nothing.
    assert len(deepseek) >= 3, deepseek
    for model, slots in deepseek:
        for slot in slots:
            if (slot["start_utc"], slot["end_utc"]) in migration.VENDOR_WINDOWS:
                assert slot.get("weekdays") == migration.WEEKDAYS, model


def test_every_windowed_tariff_of_the_bundle_passes_the_admin_schema() -> None:
    """What the bundle stores is what the admin API would have accepted."""
    blocks = _bundle_windows()
    assert blocks
    for model, slots in blocks:
        parsed = [TimeSlotPrice.model_validate(slot) for slot in slots]
        validate_time_slot_list(parsed)
        assert [slot.weekdays for slot in parsed] == [slot.get("weekdays") for slot in slots], model
