"""Observability config (Grafana dashboards + Prometheus rules) stays valid (F025).

Runs the portable structural validator against the real
``infrastructure/observability`` tree and pins its detection logic. Deep
``promtool`` validation is layered on in the CI ``observability`` job; this
guard keeps the JSON/YAML/uid/PromQL-bracket invariants green in the unit
suite so a broken dashboard cannot merge unnoticed.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from tests._repo_paths import repo_root_or_skip

REPO_ROOT = repo_root_or_skip()
VALIDATOR_PATH = REPO_ROOT / "scripts" / "observability" / "validate_observability.py"


def _load_validator():
    if not VALIDATOR_PATH.exists():
        pytest.skip("guard needs the full repository checkout (scripts/observability/).")
    spec = importlib.util.spec_from_file_location("validate_observability", VALIDATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_observability_config_is_valid() -> None:
    """The real dashboards + rules pass structural validation (exit 0)."""
    assert _load_validator().main() == 0


def test_bracket_balancer_flags_unbalanced_promql() -> None:
    """The PromQL bracket check accepts balanced exprs (incl. Grafana vars) and rejects broken ones."""
    balanced = _load_validator()._brackets_balanced
    assert balanced('sum(rate(http_requests_total{endpoint=~"$endpoint"}[$__rate_interval]))')
    assert balanced("rate(x[5m]) > {{ threshold }}")  # Jinja-templated alert rule
    assert not balanced("sum(rate(http_requests_total[5m])")  # missing )
    assert not balanced("foo{bar='baz'")  # missing }


def test_validator_detects_a_broken_dashboard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dashboard with an empty panel expr and no uid must fail validation."""
    validator = _load_validator()
    dash_dir = tmp_path / "dashboards"
    dash_dir.mkdir()
    (dash_dir / "bad.json").write_text(
        '{"title": "Bad", "panels": [{"targets": [{"expr": "  "}]}]}', encoding="utf-8"
    )
    monkeypatch.setattr(validator, "DASHBOARD_DIR", dash_dir)
    monkeypatch.setattr(validator, "PROM_DIR", tmp_path / "none")
    assert validator.main() == 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
