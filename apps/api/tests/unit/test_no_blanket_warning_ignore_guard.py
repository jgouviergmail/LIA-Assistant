"""Guard: every pytest ``filterwarnings`` ignore names the message it silences.

An un-awaited coroutine surfaces as nothing but a ``RuntimeWarning`` (CLAUDE.md:
« any unawaited coroutine … is a test failure »), so an ignore with no message —
``ignore::RuntimeWarning``, ``ignore::Warning``, a bare ``ignore`` — would hide
every such defect at once. An ignore that names its message silences that
message alone.

This rule lived in the F028 asyncpg allowlist guard, which lot 9d removed with
the allowlist it bounded; the rule never depended on asyncpg and stays.
"""

from __future__ import annotations

import tomllib

import pytest

from tests._repo_paths import find_apps_api_root

pytestmark = pytest.mark.unit

_PYPROJECT = find_apps_api_root() / "pyproject.toml"
_FILTERS: list[str] = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))["tool"]["pytest"][
    "ini_options"
]["filterwarnings"]


def _is_blanket_ignore(entry: str) -> bool:
    """True for an ``ignore`` (``action:message:category:module``) naming no message."""
    action, _, rest = entry.partition(":")
    message = rest.split(":", 1)[0]
    return action.strip() == "ignore" and not message.strip()


@pytest.mark.parametrize(
    ("entry", "blanket"),
    [
        ("ignore", True),
        ("ignore::RuntimeWarning", True),
        ("ignore:::RuntimeWarning", True),
        ("ignore::Warning", True),
        ("ignore::DeprecationWarning:some.module", True),
        ("ignore:coroutine 'x' was never awaited:RuntimeWarning", False),
        ("error::RuntimeWarning", False),
    ],
)
def test_the_rule_reads_every_spelling(entry: str, blanket: bool) -> None:
    assert _is_blanket_ignore(entry) is blanket


def test_no_ignore_silences_warnings_wholesale() -> None:
    blankets = [entry for entry in _FILTERS if _is_blanket_ignore(entry)]
    assert blankets == [], (
        "an ignore with no message masks every un-awaited coroutine; name the message "
        f"it silences: {blankets}"
    )
