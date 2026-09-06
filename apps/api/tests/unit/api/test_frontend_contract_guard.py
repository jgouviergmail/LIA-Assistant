"""The browser's view of a routine matches the schema the API serves.

Measured 2026-09-06: lot 2A removed three fields from
``ScheduledActionResponse`` and the frontend suite stayed green — 7 404 tests,
none of which could see it. The mocks fabricate the payload and the TypeScript
interface is written by hand, so neither side was checked against the other.

A vitest test cannot do this: TypeScript types are erased at runtime. Python
reads the interface as SOURCE and compares its fields to the schema, the same
way `settings-sections.test.ts` parses components to validate a table.
"""

import re
from pathlib import Path

import pytest

from src.domains.scheduled_actions.schemas import ScheduledActionResponse

HOOK = Path(__file__).resolve().parents[4] / "web" / "src" / "hooks" / "useScheduledActions.ts"

#: Fields the browser deliberately ignores. Each entry is a decision, not an
#: oversight, so the list is short and justified.
NOT_RENDERED: frozenset[str] = frozenset(
    {
        "user_id",  # the session already scopes every read
        "condition_config",  # the studio edits it through its own flattened form
    }
)


def _declared_fields(source: str, interface: str) -> set[str]:
    """The field names of one exported TypeScript interface.

    Args:
        source: The file's text.
        interface: The interface name.

    Returns:
        Every property name it declares, optional ones included.

    Raises:
        AssertionError: When the interface is absent — a rename must fail here
            rather than silently checking nothing.
    """
    match = re.search(r"export interface " + interface + r"\s*\{(.*?)\n\}", source, re.S)
    assert match, f"interface {interface} not found in {HOOK.name}"
    body = match.group(1)
    return {m.group(1) for m in re.finditer(r"^\s{2}(\w+)\??:", body, re.M)}


@pytest.fixture(scope="module")
def hook_source() -> str:
    assert HOOK.is_file(), f"{HOOK} not found"
    return HOOK.read_text(encoding="utf-8")


def test_the_browser_declares_every_field_the_api_serves(hook_source: str) -> None:
    served = set(ScheduledActionResponse.model_json_schema()["properties"])
    declared = _declared_fields(hook_source, "ScheduledAction")
    missing = served - declared - NOT_RENDERED
    assert missing == set(), (
        "the API serves fields the browser does not declare, so a payload "
        f"change would go unnoticed: {sorted(missing)}"
    )


def test_the_browser_declares_nothing_the_api_stopped_serving(hook_source: str) -> None:
    served = set(ScheduledActionResponse.model_json_schema()["properties"])
    declared = _declared_fields(hook_source, "ScheduledAction")
    stale = declared - served
    assert stale == set(), (
        "the browser reads fields the API no longer serves — exactly the break "
        f"that stayed green across 7 404 frontend tests: {sorted(stale)}"
    )


def test_the_write_payloads_agree_too(hook_source: str) -> None:
    for schema, interface in (
        ("ScheduledActionCreate", "ScheduledActionCreate"),
        ("ScheduledActionUpdate", "ScheduledActionUpdate"),
    ):
        from src.domains.scheduled_actions import schemas as module

        served = set(getattr(module, schema).model_json_schema()["properties"])
        declared = _declared_fields(hook_source, interface)
        assert declared <= served, (
            f"{interface} sends fields {schema} does not accept: " f"{sorted(declared - served)}"
        )
