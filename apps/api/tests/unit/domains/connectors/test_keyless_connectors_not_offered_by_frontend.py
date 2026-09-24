"""The settings never offer a keyless connector for activation (ADR-307).

``ConnectorType.get_keyless_types`` names the connectors the INSTANCE provides
to every account — no per-account row, nothing for the person to switch on or
off. The web app's ``API_KEY_CONNECTOR_TYPES`` and ``API_KEY_CONNECTORS``
decide what « My connectors » lists and offers to activate. A keyless type
reappearing there would offer a switch the API refuses
(``APIKeyActivationRequest``) and hide a service that always runs, so this
test reads the frontend constants file and refuses any overlap.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.domains.connectors.models import ConnectorType

pytestmark = pytest.mark.unit

_FRONTEND_CONSTANTS = (
    Path(__file__).resolve().parents[5]
    / "web"
    / "src"
    / "components"
    / "settings"
    / "connectors"
    / "constants.ts"
)

_QUOTED = re.compile(r"'([a-z_]+)'")
_ENTRY_TYPE = re.compile(r"type:\s*'([a-z_]+)'")


def _block(source: str, declaration: str, terminator: str) -> str:
    """The text of one exported constant, from its declaration to its end."""
    start = source.index(declaration)
    return source[start : source.index(terminator, start)]


def _frontend_api_key_types() -> tuple[set[str], set[str]]:
    source = _FRONTEND_CONSTANTS.read_text(encoding="utf-8")
    listed = set(
        _QUOTED.findall(_block(source, "export const API_KEY_CONNECTOR_TYPES", "] as const;"))
    )
    offered = set(
        _ENTRY_TYPE.findall(_block(source, "export const API_KEY_CONNECTORS", "] as const;"))
    )
    return listed, offered


def test_the_frontend_lists_are_parsed_and_name_real_types() -> None:
    listed, offered = _frontend_api_key_types()

    assert listed and offered, "constants.ts not parsed — the frontend shape changed"
    # A misspelled type would make the overlap check below vacuous for it.
    assert {ConnectorType(value) for value in listed | offered}


def test_no_keyless_type_is_listed_or_offered_by_my_connectors() -> None:
    listed, offered = _frontend_api_key_types()
    keyless = {connector_type.value for connector_type in ConnectorType.get_keyless_types()}

    assert not listed & keyless
    assert not offered & keyless
