"""The web translates every code the ntfy API can say, and no code the API never says (ADR-391).

The API names a publication's outcome (``NtfyOutcome``) and a refusal of the settings
(``ntfy_errors``) and never translates them; ``ntfy-labels.ts`` is the one place the web turns a
code into words. Held equal here, in order: a code added on one side and forgotten on the other
reads as the generic sentence for a person who deserved the precise one.
"""

from __future__ import annotations

import re

import pytest

from src.domains.notifications.ntfy_errors import REFUSAL_CODES
from src.infrastructure.external.ntfy_client import NtfyOutcome
from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

LABELS = (
    repo_root_or_skip()
    / "apps"
    / "web"
    / "src"
    / "components"
    / "settings"
    / "ntfy"
    / "ntfy-labels.ts"
)


def _web_list(name: str) -> list[str]:
    """The string literals of one exported ``as const`` array of the labels module."""
    source = LABELS.read_text(encoding="utf-8")
    match = re.search(rf"export const {name} = \[(.*?)\] as const", source, re.DOTALL)
    assert match, f"{name} is no longer an exported `as const` array of {LABELS.name}"
    return re.findall(r"'([^']+)'", match.group(1))


def test_every_outcome_the_api_reports_is_translated() -> None:
    assert _web_list("NTFY_OUTCOMES") == [outcome.value for outcome in NtfyOutcome]


def test_every_refusal_the_settings_can_answer_is_translated() -> None:
    assert _web_list("NTFY_REFUSALS") == list(REFUSAL_CODES)
