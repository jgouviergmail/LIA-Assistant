"""The silence that closes an alert incident outlasts every firing alert's.

Alertmanager re-delivers a FIRING alert to the LIA webhook every
``repeat_interval`` of its route; each delivery touches ``last_seen_at``. The
self-check closes an alert incident absent from Alertmanager only once it has
been silent longer than that (``reconcile_alert_incidents``). A silence shorter
than two repeat intervals could close an alert that is still firing while
Alertmanager restarts — so the default is held to it, from the fragment itself.

A restarted Alertmanager lists nothing until Prometheus re-sends what is firing,
which it does at a rule evaluation once its resend delay has passed. The
warm-up during which the listing is not believed is held to several of those
periods, from the Prometheus configuration itself.
"""

from __future__ import annotations

import re

import pytest

from src.core.constants import (
    ALERTMANAGER_WARMUP_SECONDS,
    DIAGNOSTICS_INCIDENT_SILENCE_CLOSE_SECONDS_DEFAULT,
)
from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

REPO_ROOT = repo_root_or_skip()
FRAGMENT = (
    REPO_ROOT / "infrastructure" / "observability" / "alertmanager" / "lia-webhook-route.fragment"
)
PROMETHEUS_CONFIG = REPO_ROOT / "infrastructure" / "observability" / "prometheus" / "prometheus.yml"
#: Prometheus' ``--rules.alert.resend-delay`` default: no compose file overrides it.
PROMETHEUS_DEFAULT_RESEND_DELAY_SECONDS = 60
_UNITS = {"s": 1, "m": 60, "h": 3600}


def _duration_seconds(text: str, key: str) -> int:
    match = re.search(rf"^\s*{key}:\s*(\d+)([smh])\b", text, re.M)
    assert match, f"no {key} declared"
    return int(match.group(1)) * _UNITS[match.group(2)]


def _repeat_interval_seconds() -> int:
    return _duration_seconds(FRAGMENT.read_text(encoding="utf-8"), "repeat_interval")


def test_the_default_silence_is_at_least_two_repeat_intervals() -> None:
    assert DIAGNOSTICS_INCIDENT_SILENCE_CLOSE_SECONDS_DEFAULT >= 2 * _repeat_interval_seconds()


def test_the_warmup_outlasts_several_resends_of_what_is_firing() -> None:
    evaluation = _duration_seconds(
        PROMETHEUS_CONFIG.read_text(encoding="utf-8"), "evaluation_interval"
    )
    resend_period = max(PROMETHEUS_DEFAULT_RESEND_DELAY_SECONDS, evaluation)

    assert ALERTMANAGER_WARMUP_SECONDS >= 3 * resend_period
