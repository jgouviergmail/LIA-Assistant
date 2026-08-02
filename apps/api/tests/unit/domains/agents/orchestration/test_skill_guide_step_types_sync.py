"""Sync guard: the skill-authoring guide and the ``StepType`` enum (ADR-195).

The guide shown in the settings modal tells users which ``step_type`` values a
plan step may take. Nothing checked that list against the enum, and it had
drifted: it advertised ``PARALLEL`` and ``RESPONSE`` — neither of which exists —
while omitting ``REPLAN`` and ``HUMAN``. A user following it wrote a skill the
runtime rejects, and the guide was the reason.

Same doctrine as ``test_html_directive_css_sync``: when a user-facing surface
publishes a backend vocabulary, the pair is a contract, and a contract that
nothing verifies drifts. Runs as a plain unit test — the backend CI job checks
out the whole monorepo, so the locale file is always present.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src.domains.agents.orchestration.plan_schemas import StepType

pytestmark = [pytest.mark.unit]

#: The locales carrying the guide. `en` is the parity reference, but the value
#: is prose in each language, so every one of them can drift on its own.
_LOCALES = ("en", "fr", "es", "de", "it", "zh")

#: Where the guide labels live inside the translation file.
_KEY_PATH = ("settings", "skills", "guide_modal_plan_field_step_type")


def _repo_root() -> Path:
    """Walk up from this file to the repository root (Taskfile.yml marker)."""
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "Taskfile.yml").exists():
            return parent
    raise AssertionError("repository root (Taskfile.yml) not found")


def _guide_label(locale: str) -> str:
    """The `step_type` line of the guide, in one language."""
    path = _repo_root() / "apps" / "web" / "locales" / locale / "translation.json"
    node: object = json.loads(path.read_text(encoding="utf-8"))
    for key in _KEY_PATH:
        assert isinstance(node, dict) and key in node, f"{locale}: missing {'.'.join(_KEY_PATH)}"
        node = node[key]
    assert isinstance(node, str)
    return node


def _advertised_types(label: str) -> set[str]:
    """The UPPERCASE identifiers the label presents as step types.

    Extracted by pattern rather than by splitting on spaces: the sentence
    differs per language and Chinese separates with full-width punctuation
    (``：``, ``（``, ``、``) that no ``split()`` treats as a delimiter. The
    vocabulary itself is ASCII in every locale, which is what makes this
    comparable across the six.
    """
    return set(re.findall(r"[A-Z][A-Z_]{2,}", label))


@pytest.mark.parametrize("locale", _LOCALES)
class TestGuideAdvertisesOnlyRealStepTypes:
    def test_no_invented_step_type_is_advertised(self, locale: str) -> None:
        real = {step_type.value for step_type in StepType}
        invented = _advertised_types(_guide_label(locale)) - real

        assert not invented, (
            f"{locale}: the guide advertises {sorted(invented)}, which StepType does not "
            f"accept. A skill written from it is rejected at runtime, and the guide is "
            f"the reason. Valid values: {sorted(real)}."
        )

    def test_every_real_step_type_is_documented(self, locale: str) -> None:
        """Omitting a value hides a capability the runtime already supports."""
        missing = {step_type.value for step_type in StepType} - _advertised_types(
            _guide_label(locale)
        )

        assert not missing, f"{locale}: the guide never mentions {sorted(missing)}"
