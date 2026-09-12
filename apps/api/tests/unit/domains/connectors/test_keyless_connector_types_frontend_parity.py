"""The keyless connector list has ONE declaration, and the frontend mirrors it.

``ConnectorType.get_keyless_types`` decides which connectors a new account
starts with; ``API_KEY_CONNECTORS`` in the web app decides which connectors
are offered with a one-click button (``requiresKey: false``). Two lists that
must name the same five types, in two languages, are a drift waiting to
happen — this test reads the frontend constants file and refuses any
difference in either direction.
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

# One entry of API_KEY_CONNECTORS: "type: 'x', ... requiresKey: <bool>" — the
# icon and colour lines in between are skipped by the non-greedy match.
_ENTRY = re.compile(r"type:\s*'([a-z_]+)',[^}]*?requiresKey:\s*(true|false)", re.DOTALL)


def test_frontend_one_click_connectors_equal_the_backend_keyless_types() -> None:
    source = _FRONTEND_CONSTANTS.read_text(encoding="utf-8")
    start = source.index("export const API_KEY_CONNECTORS")
    end = source.index("] as const;", start)
    entries = dict(_ENTRY.findall(source[start:end]))

    assert entries, "API_KEY_CONNECTORS not parsed — the frontend shape changed, update the reader"
    frontend_keyless = {ConnectorType(t) for t, requires in entries.items() if requires == "false"}

    assert frontend_keyless == ConnectorType.get_keyless_types()
