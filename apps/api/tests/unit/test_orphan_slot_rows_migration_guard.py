"""Three override rows whose slot no code declares leave every instance.

ADR-244 took ``router``, ``context_resolver`` and ``mcp_excalidraw`` out of the
reference seed and no migration followed: an instance seeded before it kept the
rows (read on production and on the development instance on 2026-11-11). Nothing
reads them and no screen shows them, so only an extraction finds them again --
regenerating the seed from production had to leave them out by hand.

``27fc835b8d44`` removes them. What this guard holds is that the revision can
never take a row the code reads: every name it retires is declared nowhere, and
the reference seed does not write it back on a fresh install.
"""

from __future__ import annotations

import importlib.util
import re
import typing
from pathlib import Path
from types import ModuleType

import pytest

from src.domains.llm_config.constants import LLM_DEFAULTS, LLM_TYPES_REGISTRY
from src.infrastructure.llm.factory import LLMType

pytestmark = pytest.mark.unit

_API_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION = (
    _API_ROOT / "alembic" / "versions" / "2026_11_11_2200-27fc835b8d44_retire_orphan_slot_rows.py"
)
_CONFIG_SEED = (
    _API_ROOT.parents[1] / "infrastructure" / "database" / "seeds" / "llm_config_seed.sql"
)
_SEEDED_SLOT = re.compile(r"^\s*\(gen_random_uuid\(\),\s*'(?P<slot>[^']+)',", re.M)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("retire_orphan_slot_rows", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIGRATION = _load()


def test_the_migration_chains_after_the_image_slot_row() -> None:
    assert MIGRATION.revision == "27fc835b8d44"
    assert MIGRATION.down_revision == "45cf916cc02f"


def test_it_retires_the_three_rows_the_seed_gave_up() -> None:
    assert sorted(MIGRATION.RETIRED) == ["context_resolver", "mcp_excalidraw", "router"]


@pytest.mark.parametrize("slot", MIGRATION.RETIRED)
def test_no_code_declares_a_retired_name(slot: str) -> None:
    """A name the registry, the defaults or the factory still held would be a
    row an administrator configured, removed under them."""
    assert slot not in LLM_TYPES_REGISTRY
    assert slot not in LLM_DEFAULTS
    assert slot not in typing.get_args(LLMType)


def test_the_reference_seed_does_not_write_them_back() -> None:
    seeded = set(_SEEDED_SLOT.findall(_CONFIG_SEED.read_text(encoding="utf-8")))

    assert seeded, "the seed's rows were not read"
    assert not seeded & set(MIGRATION.RETIRED)


def test_only_the_named_rows_are_removed() -> None:
    """The statement takes the names as one bound list: no pattern, no other table."""
    statement = " ".join(str(MIGRATION.RETIRE_THE_ROWS).split())

    assert statement.startswith("DELETE FROM llm_config_overrides WHERE llm_type IN")
    assert "LIKE" not in statement.upper() and ";" not in statement
