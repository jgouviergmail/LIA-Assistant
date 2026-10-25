"""The production API's health grace must cover its measured boot on the Pi.

``docker compose up --wait`` fails a deploy as soon as the API turns
unhealthy, and Docker only counts failed probes once ``start_period`` is over.
Measured on production on 2026-10-25 (v3.7.0, a deploy applying one
migration): 2 min 22 s from container start to the last uvicorn worker ready
(migrations done at +68 s, workers ready from +126 s to +142 s). With a 60 s
grace the probes landing on the workers' last seconds of startup made the
container unhealthy, ``up --wait`` failed a deploy that had in fact succeeded,
and the readiness gate after it never ran.

The grace is held above that measurement. It costs nothing on a healthy boot —
the first passing probe ends it — and a boot that hangs still turns unhealthy
right after it.
"""

from __future__ import annotations

import re

import pytest
import yaml

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

COMPOSE_PROD = repo_root_or_skip() / "docker-compose.prod.yml"

#: Container start to the last worker ready, on the Pi 5, with a migration.
MEASURED_BOOT_SECONDS = 142

_DURATION = re.compile(r"^(?:(?P<m>\d+)m)?(?:(?P<s>\d+)s)?$")


def _seconds(value: str) -> int:
    """A compose duration (``90s``, ``3m``, ``2m30s``) in seconds."""
    match = _DURATION.match(value.strip())
    assert match and (match["m"] or match["s"]), f"unreadable compose duration {value!r}"
    return int(match["m"] or 0) * 60 + int(match["s"] or 0)


def test_the_seconds_reader_reads_every_compose_shape() -> None:
    assert _seconds("180s") == 180
    assert _seconds("3m") == 180
    assert _seconds("2m30s") == 150


def test_the_api_grace_covers_the_measured_boot() -> None:
    healthcheck = yaml.safe_load(COMPOSE_PROD.read_text(encoding="utf-8"))["services"]["api"][
        "healthcheck"
    ]

    assert _seconds(healthcheck["start_period"]) >= MEASURED_BOOT_SECONDS, (
        "the API's start_period no longer covers its measured boot on the Pi: "
        "`up --wait` would fail a deploy that succeeds"
    )
