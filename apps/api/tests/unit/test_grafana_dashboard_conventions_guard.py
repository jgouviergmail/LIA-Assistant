"""Guard: every Grafana dashboard follows the owner's conventions (2026-10-03).

Two rules the owner asked for, held here so that a dashboard added later
follows them too:

- **The default range is seven days**, except the logs & traces dashboard, which
  opens on four hours. A seven-day dashboard refreshes every five minutes: left
  at thirty seconds it would re-run every panel over a week twice a minute on
  the Raspberry Pi that serves it.
- **Every dashboard links to the others the same way**: one dropdown listing
  every dashboard tagged ``lia``, identical on all of them. Before, twenty-eight
  dashboards drew a row of thirty buttons, one a dropdown, and two nothing. The
  link does not carry the time range (``keepTime: false``): each dashboard opens
  on its own default — carried, a week would open the logs dashboard on a week
  of logs.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

REPO_ROOT = repo_root_or_skip()
DASHBOARDS = REPO_ROOT / "infrastructure" / "observability" / "grafana" / "dashboards"

#: The dashboards read over hours rather than days (uid → default range).
SHORT_RANGE = {"06-logs-traces": "now-4h"}
DEFAULT_RANGE = "now-7d"
WEEK_REFRESH = "5m"
LINK = {
    "title": "LIA dashboards",
    "type": "dashboards",
    "tags": ["lia"],
    "asDropdown": True,
    "includeVars": False,
    "keepTime": False,
    "targetBlank": False,
    "icon": "external link",
    "tooltip": "",
    "url": "",
}


def _dashboards() -> list[tuple[str, dict[str, Any]]]:
    paths = sorted(DASHBOARDS.glob("*.json"))
    assert paths, f"no dashboard under {DASHBOARDS} — the guard reads the wrong directory"
    return [(path.name, json.loads(path.read_text(encoding="utf-8"))) for path in paths]


def test_every_dashboard_opens_on_its_default_range() -> None:
    wrong = {
        name: dashboard.get("time")
        for name, dashboard in _dashboards()
        if dashboard.get("time")
        != {"from": SHORT_RANGE.get(dashboard["uid"], DEFAULT_RANGE), "to": "now"}
    }

    assert not wrong, f"dashboard(s) not opening on their default range: {wrong}"


def test_a_week_long_dashboard_refreshes_every_five_minutes() -> None:
    wrong = {
        name: dashboard.get("refresh")
        for name, dashboard in _dashboards()
        if dashboard["uid"] not in SHORT_RANGE and dashboard.get("refresh") != WEEK_REFRESH
    }

    assert not wrong, f"seven-day dashboard(s) refreshing at another pace: {wrong}"


def test_every_dashboard_links_to_the_others_the_same_way() -> None:
    wrong = [name for name, dashboard in _dashboards() if dashboard.get("links") != [LINK]]

    assert not wrong, f"dashboard(s) whose links differ from the shared dropdown: {wrong}"


def test_every_dashboard_is_listed_in_the_dropdown() -> None:
    missing = [name for name, dashboard in _dashboards() if "lia" not in dashboard.get("tags", [])]

    assert not missing, f"dashboard(s) the shared dropdown cannot list (no `lia` tag): {missing}"


def test_the_short_range_names_existing_dashboards() -> None:
    uids = {dashboard["uid"] for _, dashboard in _dashboards()}

    assert set(SHORT_RANGE) <= uids, f"unknown uid(s) in SHORT_RANGE: {set(SHORT_RANGE) - uids}"
