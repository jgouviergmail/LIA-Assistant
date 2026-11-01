"""Every refusal the workbench API sends can be read, in the six languages (ADR-369).

The web tells a refusal by its ``detail.code`` (``apps/web/src/lib/workbench/errors.ts``).
A code the API sends that the web does not list, or a sentence one locale lacks,
is a refusal the reader cannot read: the generic « something went wrong » in its
place. The pair is pinned here, where the vocabulary is defined (Task 1.2 ruling:
moved to the frontend lot, so the test was never red in a tree another session
tests too).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, get_args

import pytest

from src.domains.workbench.errors import WORKBENCH_CODES
from src.domains.workbench.features import WorkbenchFeature, WorkbenchTool
from src.domains.workbench.idempotency import SubmissionOutcome
from src.domains.workbench.schemas.common import ToolState, WorkbenchLimits

pytestmark = pytest.mark.unit

LOCALES = ("en", "fr", "de", "es", "it", "zh")
_WEB = Path(__file__).resolve().parents[5] / "web"
_ERRORS_MODULE = _WEB / "src" / "lib" / "workbench" / "errors.ts"
_TYPES_MODULE = _WEB / "src" / "lib" / "workbench" / "types.ts"

#: The richer sentences ``errors.ts`` chooses when the API sends a figure,
#: with the placeholder each one quotes.
_ENRICHED: dict[str, str | None] = {
    "provider_rate_limited_wait": "seconds",
    "provider_unavailable_wait": "seconds",
    "too_large_bounded": "megabytes",
    "invalid_recipient_at": "position",
    "not_supported_by_provider_bounded": "bound",
    **{f"already_submitted_{outcome.value}": None for outcome in SubmissionOutcome},
}


def _translations(locale: str) -> dict[str, Any]:
    raw = (_WEB / "locales" / locale / "translation.json").read_text(encoding="utf-8")
    return dict(json.loads(raw))


def _sentence(tree: dict[str, Any], key: str) -> str:
    node: object = tree.get("workbench", {}).get("errors", {})
    return str(node.get(key) or "").strip() if isinstance(node, dict) else ""


def test_the_web_lists_exactly_the_codes_the_api_sends() -> None:
    source = _ERRORS_MODULE.read_text(encoding="utf-8")
    block = re.search(r"WORKBENCH_ERROR_CODES = \[(.*?)\] as const", source, re.DOTALL)
    assert block is not None, "lib/workbench/errors.ts no longer declares WORKBENCH_ERROR_CODES"
    assert set(re.findall(r"'([a-z_]+)'", block.group(1))) == set(WORKBENCH_CODES)


@pytest.mark.parametrize("locale", LOCALES)
def test_every_refusal_has_its_sentence(locale: str) -> None:
    tree = _translations(locale)
    missing = [code for code in sorted(WORKBENCH_CODES) if not _sentence(tree, code)]
    assert not missing, f"{locale}: refusals the API sends and nobody can read: {missing}"


@pytest.mark.parametrize("locale", LOCALES)
def test_every_richer_sentence_quotes_its_figure(locale: str) -> None:
    tree = _translations(locale)
    wrong = [
        key
        for key, placeholder in _ENRICHED.items()
        if not _sentence(tree, key)
        or (placeholder is not None and f"{{{{{placeholder}}}}}" not in _sentence(tree, key))
    ]
    assert not wrong, f"{locale}: richer sentences missing or not quoting their figure: {wrong}"


def _union(name: str) -> set[str]:
    """The string members of ``export type <name> = 'a' | 'b' …;`` in types.ts."""
    source = _TYPES_MODULE.read_text(encoding="utf-8")
    block = re.search(rf"export type {name} =(.*?);", source, re.DOTALL)
    assert block is not None, f"lib/workbench/types.ts no longer declares {name}"
    return set(re.findall(r"'([a-z_]+)'", block.group(1)))


def test_the_web_reads_the_rail_in_the_api_s_vocabulary() -> None:
    """A gesture renamed on one side would vanish from the screens in silence."""
    assert _union("WorkbenchToolId") == {tool.value for tool in WorkbenchTool}
    assert _union("WorkbenchToolState") == set(get_args(ToolState))
    assert _union("WorkbenchFeature") == {feature.value for feature in WorkbenchFeature}


def test_the_web_reads_every_published_limit() -> None:
    source = _TYPES_MODULE.read_text(encoding="utf-8")
    block = re.search(r"export interface WorkbenchLimits \{(.*?)\}", source, re.DOTALL)
    assert block is not None, "lib/workbench/types.ts no longer declares WorkbenchLimits"
    assert set(re.findall(r"([a-z_]+): number;", block.group(1))) == set(
        WorkbenchLimits.model_fields
    )
