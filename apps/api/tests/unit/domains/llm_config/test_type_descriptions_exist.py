"""Every LLM type's description must actually resolve, in all six languages.

``LLMTypeMetadata.description_key`` points into the frontend locale files, and
nothing checked that the target existed. The failure is silent and entirely
user-visible: the admin screen renders the raw key —
``settings.admin.llmConfig.types.react_agent`` — where a sentence belongs, and
only somebody opening that exact row ever finds out.

Measured 2026-09-07, before this guard: ``react_agent`` — the slot that runs the
ReAct loop, one of the most consequential of the 59 — had no entry in ANY
locale, and had not had one for as long as it existed.

This is the ADR-085 doctrine (a registry keyed by an enum gets a completeness
assert) applied across the file boundary the registry actually spans. The i18n
parity check next door cannot see it: it compares the six locales to each
other, so a key missing from all six is perfectly consistent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.domains.llm_config.constants import LLM_TYPES_REGISTRY
from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

LOCALES = ("en", "fr", "de", "es", "it", "zh")


def _translations(language: str) -> dict[str, object]:
    root: Path = repo_root_or_skip()
    path = root / "apps" / "web" / "locales" / language / "translation.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve(tree: dict[str, object], dotted: str) -> object:
    """Walk a dotted i18n key, returning None as soon as the path breaks."""
    node: object = tree
    for part in dotted.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
        if node is None:
            return None
    return node


@pytest.mark.parametrize("language", LOCALES)
def test_every_llm_type_description_resolves(language: str) -> None:
    """A type whose key resolves to nothing shows the key to an administrator."""
    tree = _translations(language)
    missing = [
        llm_type
        for llm_type, meta in LLM_TYPES_REGISTRY.items()
        if not isinstance(_resolve(tree, meta.description_key), str)
        or not str(_resolve(tree, meta.description_key)).strip()
    ]
    assert not missing, (
        f"{language}: {len(missing)} LLM type(s) whose description_key resolves to "
        f"nothing — the admin screen would render the raw key: {sorted(missing)}"
    )


def test_the_key_is_derived_from_the_type_name() -> None:
    """One shape for all of them, so a typo is a broken key rather than a new one.

    Enforced rather than trusted: a hand-written key that drifts from its type
    still resolves as long as SOMEBODY wrote a translation for the drifted
    name, and the two then diverge quietly for good.
    """
    wrong = {
        llm_type: meta.description_key
        for llm_type, meta in LLM_TYPES_REGISTRY.items()
        if meta.description_key != f"settings.admin.llmConfig.types.{llm_type}"
    }
    assert not wrong, wrong


def test_the_guard_sees_the_registry() -> None:
    """A registry read as empty would make every assertion above vacuous."""
    assert len(LLM_TYPES_REGISTRY) > 50
