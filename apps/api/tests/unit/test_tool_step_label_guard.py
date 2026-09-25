"""Every tool the catalogue can show has its progress wording (v1.47.4).

While a turn runs, the chat names each step from ``execution.steps.<i18n_key>``
— the key a tool's manifest declares in ``DisplayMetadata``. A key with no
wording is not an error anywhere: the step silently falls back to a generic
« thinking… », and the person cannot see what LIA is doing. Measured on
2026-09-25: 24 of the 115 tool keys had none, among them the e-mail to oneself
(ADR-314), the whole workboard and every health tool — while a public blog
article stated that every catalogue tool had its wording.

The keys are read from the SOURCE, not from a loaded catalogue: a tool
registered behind a feature flag the test environment leaves off would
otherwise escape the check. The other five locales mirror ``en`` key for key
(``task lint:i18n``), so the reference locale is the one read here.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

REPO_ROOT = Path(__file__).resolve().parents[4]
SOURCE_ROOT = REPO_ROOT / "apps/api/src"
REFERENCE_LOCALE = REPO_ROOT / "apps/web/locales/en/translation.json"


def _tool_display_keys() -> dict[str, str]:
    """``i18n_key`` → first declaring file, for every tool-category display."""
    keys: dict[str, str] = {}
    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name != "DisplayMetadata":
                continue
            arguments = {keyword.arg: keyword.value for keyword in node.keywords}
            category, key = arguments.get("category"), arguments.get("i18n_key")
            if (
                isinstance(category, ast.Constant)
                and category.value == "tool"
                and isinstance(key, ast.Constant)
                and isinstance(key.value, str)
            ):
                keys.setdefault(key.value, str(path.relative_to(REPO_ROOT)))
    return keys


def _has_wording(steps: dict[str, object], key: str) -> bool:
    """A dotted key resolves through nested objects, as i18next reads it."""
    node: object = steps
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    return isinstance(node, str) and bool(node.strip())


def test_the_scan_sees_the_catalogue() -> None:
    """A scan that found nothing would pass vacuously."""
    assert len(_tool_display_keys()) >= 100


def test_every_tool_display_key_has_its_progress_wording() -> None:
    steps = json.loads(REFERENCE_LOCALE.read_text(encoding="utf-8"))["execution"]["steps"]

    missing = {
        key: origin for key, origin in _tool_display_keys().items() if not _has_wording(steps, key)
    }

    assert missing == {}, (
        "tools with no `execution.steps` wording in the six locales — the chat would "
        f"show a generic step instead of what LIA is doing: {missing}"
    )
