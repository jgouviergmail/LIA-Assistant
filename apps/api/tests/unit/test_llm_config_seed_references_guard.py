"""Every model the configuration seed names must exist in the catalogue seed.

The two files are extracted separately from production, so nothing forced them
to agree. They did not: ``llm_config_seed.sql`` pinned the ``image_generation``
slot to ``gpt-image-2`` and ``image_generation_pricing_seed.sql`` priced it,
while ``llm_pricing_seed.sql`` never created its ``llm_models`` row. A fresh
install therefore booted with a slot naming a model the catalogue did not
carry: ``ModelCapabilitiesCache.get`` answered ``None`` and the runtime silently
fell back to ``CONSERVATIVE_DEFAULT``, whose ``is_reasoning_model=False`` makes
the adapter send sampling parameters to a reasoning model.

``verify_reference_seeds.sql`` could not catch it — its postconditions were
cardinalities only, and it did not even count ``llm_models``. Both the SQL
postcondition and this guard were added with the fix (ADR-244, Lot 0a); this
one fails in the same commit as the drift, offline, in the fast unit suite.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src.core.reasoning_intent import LEVELS

pytestmark = pytest.mark.unit

_SEEDS = Path(__file__).resolve().parents[3].parent / "infrastructure" / "database" / "seeds"
_CONFIG_SEED = _SEEDS / "llm_config_seed.sql"
_CATALOGUE_SEED = _SEEDS / "llm_pricing_seed.sql"

#: ``(gen_random_uuid(), '<slot>', <provider|NULL>, <model|NULL>, ...``
_CONFIG_ROW = re.compile(
    r"^\s*\(gen_random_uuid\(\),\s*'([^']+)',\s*(NULL|'[^']*'),\s*(NULL|'[^']*'),",
    re.MULTILINE,
)
#: ``    ('<provider>', '<model_name>', <int>, ...`` in the llm_models INSERT
_CATALOGUE_ROW = re.compile(r"^\s*\('([a-z]+)',\s*'([^']+)',\s*\d+,", re.MULTILINE)


def _configured_models() -> dict[str, str]:
    """Return ``{slot: model}`` for every configuration row that pins a model."""
    text = _CONFIG_SEED.read_text(encoding="utf-8")
    found = {}
    for slot, _provider, model in _CONFIG_ROW.findall(text):
        if model != "NULL":
            found[slot] = model.strip("'")
    return found


def _catalogue_models() -> set[str]:
    text = _CATALOGUE_SEED.read_text(encoding="utf-8")
    return {model for _provider, model in _CATALOGUE_ROW.findall(text)}


def test_the_parsers_actually_find_rows() -> None:
    """A regex that matches nothing would make this guard vacuously green."""
    configured, catalogue = _configured_models(), _catalogue_models()
    assert len(configured) >= 30, f"only {len(configured)} configured slots parsed"
    assert len(catalogue) >= 120, f"only {len(catalogue)} catalogue rows parsed"


def test_every_configured_model_has_a_catalogue_row() -> None:
    catalogue = _catalogue_models()
    orphans = sorted(
        f"{slot} -> {model}"
        for slot, model in _configured_models().items()
        if model not in catalogue
    )
    assert orphans == [], (
        "these configuration-seed slots name a model with no llm_models row in "
        f"llm_pricing_seed.sql: {orphans}"
    )


def test_every_code_default_has_a_catalogue_row() -> None:
    """The code defaults must be reachable on a reference install too.

    ``FALLBACK_MODELS_DEFAULT`` was the live counter-example: it named
    ``claude-sonnet-4-5``, absent from the catalogue entirely, and
    ``deepseek-chat``, deactivated — so the failover chain had no reachable
    target and nothing said so. Both registries knew those names, which is why
    the deprecation guard could not catch it: the question is not "does the
    model exist in the world" but "does this deployment carry a row for it".
    """
    from src.core.constants import FALLBACK_MODELS_DEFAULT, SUMMARIZATION_MODEL_DEFAULT
    from src.domains.llm_config.constants import LLM_DEFAULTS

    catalogue = _catalogue_models()
    named = {config.model for config in LLM_DEFAULTS.values() if config.model}
    named.add(SUMMARIZATION_MODEL_DEFAULT)
    named.update(part.strip() for part in FALLBACK_MODELS_DEFAULT.split(",") if part.strip())

    missing = sorted(model for model in named if model not in catalogue)
    assert missing == [], (
        "these code defaults name a model with no llm_models row in "
        f"llm_pricing_seed.sql: {missing}"
    )


def test_every_seeded_reasoning_value_is_already_an_intent() -> None:
    """A fresh install must not carry a shape the migration would have to fix.

    The seeds are extracted from production by hand, and the extraction that
    produced this file predates ADR-245: it carried ``{"effort": "off"}`` on 21
    slots. Left alone, every fresh install and every demo boot (tmpfs, rebuilt
    from these seeds) would start with rows in a shape the code only reads
    through a compatibility shim -- a shim whose whole purpose is to be
    temporary. The next extraction must not silently reintroduce them.
    """
    from src.core.reasoning_intent import ReasoningIntent, is_intent_shape

    stored = re.findall(r"'(\{[^']*\})'::jsonb", _CONFIG_SEED.read_text(encoding="utf-8"))
    reasoning = [json.loads(raw) for raw in stored if "level" in raw or "effort" in raw]
    assert len(reasoning) >= 25, f"only {len(reasoning)} reasoning payloads parsed"

    legacy = [payload for payload in reasoning if not is_intent_shape(payload)]
    assert legacy == [], f"llm_config_seed.sql still carries pre-ADR-245 shapes: {legacy}"

    for payload in reasoning:
        intent = ReasoningIntent(**payload)
        assert intent.level in LEVELS, payload


def test_the_configuration_seed_no_longer_writes_the_dropped_effort_column() -> None:
    """``llm_config_overrides.effort`` was dropped with the second channel.

    An INSERT naming it would abort the whole reference bundle -- and the demo
    rebuilds from that bundle at every boot, so the failure would be a blank
    instance rather than a bad row.
    """
    text = _CONFIG_SEED.read_text(encoding="utf-8")
    insert = text[text.index("INSERT INTO llm_config_overrides") : text.index("VALUES")]
    assert " effort" not in insert and "(effort" not in insert, insert
    assert "effort = EXCLUDED.effort" not in text


def test_no_catalogue_row_declares_a_level_outside_the_ladder() -> None:
    """``reasoning_enum_values`` is the ONE catalogue value the runtime reads.

    It narrows the family's ladder, so it must speak the ladder's vocabulary.
    Four rows declared ``off`` — the pre-ADR-245 sentinel — and the narrowing
    silently dropped it: ``("none","high","max") ∩ {"off","high","max"}`` is
    ``("high","max")``, a ladder with no off switch. Nothing broke only because
    ``can_disable`` governs the off switch and put it back; the row was still
    declaring a level that does not exist, and the admin catalogue displayed it.
    """
    from src.core.reasoning_intent import LEVELS

    text = _CATALOGUE_SEED.read_text(encoding="utf-8")
    declared = re.findall(r"'(\[[^\]]*\])'::jsonb", text)
    ladders = [json.loads(raw) for raw in declared if raw.startswith('["')]
    assert len(ladders) >= 15, f"only {len(ladders)} ladders parsed — the regex stopped matching"

    unknown = sorted({level for ladder in ladders for level in ladder if level not in LEVELS})
    assert unknown == [], f"llm_pricing_seed.sql declares levels off the ladder: {unknown}"
