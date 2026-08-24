"""One slot vocabulary, named identically everywhere it is named.

Four places declare slots — ``LLM_TYPES_REGISTRY``, ``LLM_DEFAULTS``, the
``LLMType`` Literal and ``llm_config_seed.sql`` — and nothing forced them to
agree. They did not: ``mcp_excalidraw`` had a seed row and no registry entry,
and ``router`` / ``context_resolver`` had registry entries, defaults, seed rows,
six translations each and no ``get_llm()`` caller at all.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import get_args

import pytest

from src.core.llm_config_helper import _resolve_canonical_type
from src.domains.llm_config.constants import LLM_DEFAULTS, LLM_TYPES_REGISTRY
from src.domains.llm_config.install_contract import CURRENT_CORE_LLM_TYPES

pytestmark = pytest.mark.unit

_SEED = (
    Path(__file__).resolve().parents[3].parent
    / "infrastructure"
    / "database"
    / "seeds"
    / "llm_config_seed.sql"
)
_CONFIG_ROW = re.compile(r"^\s*\(gen_random_uuid\(\),\s*'([^']+)',", re.MULTILINE)

#: Slots the ``LLMType`` Literal was never given. Shrink-only: entries come out
#: as the Literal is completed, and none may be added. The Literal is not a type
#: guard — ``pyproject.toml`` disables ``arg-type`` for
#: ``src.domains.agents.nodes.*`` — so the gap is documented debt, not a defect.
LITERAL_GAP: frozenset[str] = frozenset(
    {
        "health_agent",
        "hue_agent",
        "image_generation",
        "vision_analysis",
        "voice_transcription",
        "voice_tts",
    }
)


def _seed_slots() -> set[str]:
    return set(_CONFIG_ROW.findall(_SEED.read_text(encoding="utf-8")))


def _literal_slots() -> set[str]:
    from src.infrastructure.llm.factory import LLMType

    return {_resolve_canonical_type(name) for name in get_args(LLMType)}


def test_the_parser_finds_rows() -> None:
    """A regex that matched nothing would make this guard vacuously green."""
    assert len(_seed_slots()) >= 30


def test_registry_and_defaults_declare_the_same_slots() -> None:
    assert set(LLM_TYPES_REGISTRY) == set(LLM_DEFAULTS)


def test_no_seed_row_is_an_orphan() -> None:
    orphans = sorted(_seed_slots() - set(LLM_TYPES_REGISTRY))
    assert orphans == [], f"seed rows for slots that do not exist: {orphans}"


def test_the_install_contract_names_real_slots() -> None:
    unknown = sorted(set(CURRENT_CORE_LLM_TYPES) - set(LLM_TYPES_REGISTRY))
    assert unknown == [], f"CURRENT_CORE_LLM_TYPES names removed slots: {unknown}"


def test_the_literal_names_only_real_slots() -> None:
    """Zero phantoms — this is what catches a removal the Literal forgot.

    Compared through ``_resolve_canonical_type`` because the Literal carries
    seven singular aliases (``contact_agent`` for ``contacts_agent`` and its
    siblings) that the helper resolves.
    """
    phantom = sorted(_literal_slots() - set(LLM_TYPES_REGISTRY))
    assert phantom == [], f"the LLMType Literal names slots that do not exist: {phantom}"


def test_the_literal_gap_is_shrink_only() -> None:
    missing = set(LLM_TYPES_REGISTRY) - _literal_slots()
    new = sorted(missing - LITERAL_GAP)
    assert new == [], f"a new slot skipped the LLMType Literal: {new}"
    assert len(LITERAL_GAP) <= 6, "LITERAL_GAP is shrink-only"
