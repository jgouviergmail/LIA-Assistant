"""Two catalogue rows an existing instance held apart from the reference seed, and why.

``43891b5db14c`` corrects what no earlier door could reach, because every door
that writes a catalogue row inserts it only where the model is unknown:

* ``gemini-2.5-flash-native-audio-preview-09-2025`` is a speech-to-speech model.
  The row existed before the live models were declared, with the ``audio`` kind
  the transcription slot requires -- so the slot offered a bidirectional model.
  The seed says ``realtime``, a kind no slot requires;
* ``deepseek-flash``, where an administrator created the row by hand before its
  migration, declares neither its ladder nor its documentation key.

The values are the seed's, and the correction touches only the value an
instance was left with: a kind, a ladder or a key an administrator chose stands.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

from src.core.reasoning_profiles import resolve_reasoning_profile
from src.domains.llm_config.constants import LLM_TYPES_REGISTRY
from tests.unit.infrastructure.llm.reasoning.test_family_coverage import _catalogue_rows

pytestmark = pytest.mark.unit

_API_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION = (
    _API_ROOT / "alembic" / "versions" / "2026_11_11_1900-43891b5db14c_align_two_catalogue_rows.py"
)

LIVE_MODEL = "gemini-2.5-flash-native-audio-preview-09-2025"
DEEPSEEK_MODEL = "deepseek-flash"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("align_two_catalogue_rows", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seed_row(model_name: str) -> dict[str, str]:
    return next(row for row in _catalogue_rows() if row["model_name"] == model_name)


def test_the_migration_chains_after_the_fable_5_2_migration() -> None:
    module = _load()
    assert module.revision == "43891b5db14c"
    assert module.down_revision == "5cccb7a8d77f"


def test_the_live_model_takes_the_kind_the_seed_declares() -> None:
    module = _load()
    assert module.LIVE_MODEL == LIVE_MODEL
    assert module.KIND == _seed_row(LIVE_MODEL)["kind"]
    assert module.KIND != module.STALE_KIND


def test_the_stale_kind_is_the_one_the_transcription_slot_requires() -> None:
    """Why the row had to move: with it, the slot offered a model that cannot transcribe."""
    module = _load()
    assert LLM_TYPES_REGISTRY["voice_transcription"].required_kind.value == module.STALE_KIND


def test_no_slot_requires_the_kind_the_live_model_takes() -> None:
    """A live model is the person's own session, never a slot's model."""
    module = _load()
    requiring = [
        slot for slot, meta in LLM_TYPES_REGISTRY.items() if meta.required_kind.value == module.KIND
    ]
    assert requiring == []


def test_only_a_row_still_carrying_the_stale_kind_is_moved() -> None:
    """A kind an administrator chose stands."""
    statement = " ".join(str(_load().FIX_KIND).split())
    assert "WHERE model_name = :model_name AND kind = CAST(:stale AS llm_model_kind_enum)" in (
        statement
    )


def test_deepseek_flash_takes_the_declaration_the_seed_carries() -> None:
    module = _load()
    seed_row = _seed_row(DEEPSEEK_MODEL)
    assert module.DEEPSEEK_MODEL == DEEPSEEK_MODEL
    assert f"{json.dumps(module.LADDER)}'::jsonb" == seed_row["reasoning_enum_values"]
    assert module.DOC_KEY == seed_row["reasoning_doc_i18n_key"]


def test_filling_the_ladder_changes_no_depth_the_model_can_be_asked_for() -> None:
    """An undeclared ladder already resolved to the family's: the row only says it now."""
    module = _load()
    assert tuple(module.LADDER) == resolve_reasoning_profile("deepseek", DEEPSEEK_MODEL).levels


def test_only_an_empty_declaration_is_filled() -> None:
    """Both spellings of « nothing declared » -- SQL NULL and the JSON null a
    hand-made row carries -- and nothing else: a narrowed ladder is an
    administrator's, and so is a documentation key."""
    module = _load()
    ladder = " ".join(str(module.FILL_LADDER).split())
    assert "AND (reasoning_enum_values IS NULL OR reasoning_enum_values = 'null'::jsonb)" in ladder
    doc_key = " ".join(str(module.FILL_DOC_KEY).split())
    assert "AND reasoning_doc_i18n_key IS NULL" in doc_key
