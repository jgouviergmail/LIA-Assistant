"""Guard: no observability component reports usage to its vendor.

Loki, Tempo, Grafana and Alloy each send anonymous usage statistics to Grafana
Labs unless told not to. The operator of a self-hosted assistant never asked
for that connection, so every one of them is told: three in their own
configuration files, Alloy on its command line — it reads a Promtail-format
file, which has no such setting. Replacing Promtail by Alloy (dependency
programme, lot 6g) is how the fourth arrived, reporting by default.
"""

from __future__ import annotations

import configparser
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

ROOT = repo_root_or_skip()
OBSERVABILITY = ROOT / "infrastructure" / "observability"
COMPOSE_FILES = sorted(ROOT.glob("docker-compose*.yml"))


def _yaml(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data


def _services(image_prefix: str) -> list[tuple[str, dict[str, Any]]]:
    """Every compose service running an image of this repository."""
    found: list[tuple[str, dict[str, Any]]] = []
    for compose in COMPOSE_FILES:
        for name, service in (_yaml(compose).get("services") or {}).items():
            if str(service.get("image", "")).startswith(image_prefix):
                found.append((f"{compose.name}:{name}", service))
    return found


def _environment(service: dict[str, Any]) -> dict[str, str]:
    raw = service.get("environment") or {}
    if isinstance(raw, dict):
        return {str(key): str(value) for key, value in raw.items()}
    return dict(str(entry).partition("=")[::2] for entry in raw)


def test_loki_reports_nothing() -> None:
    config = _yaml(OBSERVABILITY / "loki" / "loki-config.yml")
    assert config["analytics"]["reporting_enabled"] is False


def test_tempo_reports_nothing() -> None:
    config = _yaml(OBSERVABILITY / "tempo" / "tempo.yml")
    assert config["usage_report"]["reporting_enabled"] is False


def test_grafana_reports_nothing_and_no_compose_overrides_it() -> None:
    ini = configparser.ConfigParser(interpolation=None)
    ini.read(OBSERVABILITY / "grafana" / "grafana.ini", encoding="utf-8")
    assert ini.getboolean("analytics", "reporting_enabled") is False

    grafanas = _services("grafana/grafana:")
    assert grafanas, "no Grafana service found: the override check would see nothing"
    for where, service in grafanas:
        override = _environment(service).get("GF_ANALYTICS_REPORTING_ENABLED", "false")
        assert override.lower() == "false", where


def test_every_alloy_runs_with_reporting_disabled() -> None:
    alloys = _services("grafana/alloy:")
    assert alloys, "no Alloy service found: the guard would check nothing"
    for where, service in alloys:
        assert "--disable-reporting" in (service.get("command") or []), where
