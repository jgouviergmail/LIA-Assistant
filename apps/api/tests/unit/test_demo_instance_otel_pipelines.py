"""Every signal the demonstrator's API exports must have somewhere to land.

The application configures an OTLP span exporter unconditionally
(``configure_tracing`` in ``main.py``, no feature flag), and the demonstrator
points ``OTEL_EXPORTER_OTLP_ENDPOINT`` at its own collector. That collector
declared a ``metrics`` pipeline only, so its gRPC server accepted the
connection but never registered the trace service: every batch came back
``StatusCode.UNIMPLEMENTED`` and landed in the logs as an error
(measured in production 2026-08-21T20:51Z).

The rule this guard pins is not "traces must be stored" — the demonstrator
deliberately keeps no trace backend. It is that a receiver which accepts a
signal must say what becomes of it. Dropping is a legitimate answer; silence
that surfaces as a recurring error is not.
"""

from __future__ import annotations

from typing import Any

import pytest
import yaml

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

REPO_ROOT = repo_root_or_skip()
COLLECTOR = REPO_ROOT / "infrastructure" / "demo-instance" / "otel-collector.yaml"
ENV_TEMPLATE = REPO_ROOT / ".env.demo-instance.prod.example"


def _config() -> dict[str, Any]:
    parsed = yaml.safe_load(COLLECTOR.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict), f"{COLLECTOR} must parse to a mapping"
    return parsed


def test_the_demonstrator_points_its_api_at_this_collector() -> None:
    """The premise of the whole guard: without this line it pins nothing."""
    body = ENV_TEMPLATE.read_text(encoding="utf-8")
    assert "OTEL_EXPORTER_OTLP_ENDPOINT=http://demo-instance-otel:4317" in body


def test_the_api_exports_spans_with_no_flag_to_turn_them_off() -> None:
    """Anchored on the source: the exporter is wired unconditionally."""
    tracing = (
        REPO_ROOT / "apps" / "api" / "src" / "infrastructure" / "observability" / "tracing.py"
    ).read_text(encoding="utf-8")
    assert "OTLPSpanExporter" in tracing
    assert "BatchSpanProcessor" in tracing


def test_every_accepted_signal_has_a_pipeline() -> None:
    """A pipeline per signal the OTLP receiver can be sent — traces included."""
    pipelines = _config()["service"]["pipelines"]
    assert "metrics" in pipelines, "metrics pipeline disappeared"
    assert "traces" in pipelines, (
        "the API exports spans to this collector; without a traces pipeline "
        "gRPC answers UNIMPLEMENTED on every batch"
    )


def test_the_traces_pipeline_reads_from_otlp_and_states_its_disposal() -> None:
    config = _config()
    traces = config["service"]["pipelines"]["traces"]
    assert traces["receivers"] == ["otlp"]
    exporters = traces["exporters"]
    assert exporters, "a pipeline with no exporter fails the collector at boot"
    for name in exporters:
        assert name in config["exporters"], f"{name} used by traces but never defined"
