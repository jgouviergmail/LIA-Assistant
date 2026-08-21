"""Guards on the alerting core — the file Prometheus actually loads (ADR-119).

Written after a security alert shipped in v1.25.20 that could never fire. It was
added to ``alerts.yml``, which is BOTH a generated artifact (``prepare_config.sh``
re-renders it from ``alerts.yml.template``, silently discarding hand edits) AND
commented out of ``prometheus.yml``'s ``rule_files``. Documentation, CHANGELOG
and ADR all claimed the control existed. Every test was green, because no test
looked at whether an alert was reachable at all.

These guards close that class:

* an edit to the rendered core file that is not in its template is caught;
* an alert whose runbook link points nowhere is caught;
* an alert with no promtool test case is caught;
* a threshold declared for one environment but not the others is caught, which
  would otherwise only surface as a ``StrictUndefined`` crash at deploy time on
  whichever environment was forgotten.

They do NOT re-test what promtool already covers (firing behaviour, rendered
annotations) — that suite runs in the ``observability`` CI job.
"""

from __future__ import annotations

from typing import Any

import pytest
import yaml
from dotenv import dotenv_values
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from tests._repo_paths import repo_root_or_skip

REPO_ROOT = repo_root_or_skip()
PROMETHEUS_DIR = REPO_ROOT / "infrastructure" / "observability" / "prometheus"
CORE_TEMPLATE = PROMETHEUS_DIR / "alerts-core.yml.template"
CORE_RENDERED = PROMETHEUS_DIR / "alerts-core.yml"
PROMTOOL_TESTS = PROMETHEUS_DIR / "tests" / "alerts_core_test.yml"
THRESHOLDS_DIR = PROMETHEUS_DIR / "thresholds"
ENVIRONMENTS = ("production", "staging", "development")

# The environment whose thresholds are committed as the rendered artifact.
# prepare_config.sh renders per-environment at deploy time; the file in git is
# the production render, and the promtool suite asserts production values.
RENDERED_ENVIRONMENT = "production"


def _render(environment: str) -> str:
    """Render the core template exactly as ``prepare_config.sh`` does.

    Args:
        environment: Threshold set to render with.

    Returns:
        The rendered YAML text, newline-normalised.
    """
    env = Environment(
        loader=FileSystemLoader(str(CORE_TEMPLATE.parent)),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        variable_start_string="<<<",
        variable_end_string=">>>",
    )
    values = dotenv_values(THRESHOLDS_DIR / f"{environment}.env")
    rendered = env.get_template(CORE_TEMPLATE.name).render(**values)
    return rendered.replace("\r\n", "\n")


def _core_alerts() -> list[dict[str, Any]]:
    """Every alert rule in the rendered core file.

    Returns:
        The alert rule mappings, across all groups.
    """
    parsed = yaml.safe_load(CORE_RENDERED.read_text(encoding="utf-8"))
    return [rule for group in parsed["groups"] for rule in group["rules"] if "alert" in rule]


def _alert_names() -> list[str]:
    """Alert names in the rendered core file, in declaration order."""
    return [rule["alert"] for rule in _core_alerts()]


class TestRenderedCoreMatchesItsTemplate:
    """The committed artifact must be the template's output, never a hand edit."""

    def test_rendered_file_is_the_production_render_of_the_template(self):
        """A hand edit to alerts-core.yml would be erased by the next deploy.

        ``prepare_config.sh`` overwrites this file from the template on every
        run. An alert added only to the rendered side therefore exists until
        someone deploys, and silently disappears afterwards — while the docs
        keep claiming it. Compared newline-normalised: the renderer writes with
        the platform's line ending, so CRLF/LF is not a meaningful difference.
        """
        expected = _render(RENDERED_ENVIRONMENT)
        actual = CORE_RENDERED.read_text(encoding="utf-8").replace("\r\n", "\n")

        assert actual == expected, (
            "alerts-core.yml is not the production render of alerts-core.yml.template. "
            "Edit the TEMPLATE, then run ./prepare_config.sh production."
        )

    def test_no_unsubstituted_template_delimiter_survives(self):
        """A typo'd variable name must not ship as literal text.

        StrictUndefined catches an unknown variable, but a malformed delimiter
        (``<<<VAR>>`` and the like) renders as-is and Prometheus would reject
        the rule file at load time — after deployment.
        """
        content = CORE_RENDERED.read_text(encoding="utf-8")

        assert "<<<" not in content
        assert ">>>" not in content


class TestEveryCoreAlertIsWiredEndToEnd:
    """An alert is only real if it is reachable, documented and tested."""

    def test_the_core_file_is_the_one_prometheus_loads(self):
        """Guards against alerts landing in a rule file nobody loads.

        ``alerts.yml`` and ``alert_rules.yml`` are rendered but commented out
        of ``rule_files`` (ADR-119: their legacy thresholds are corrupted). An
        alert added there is dead on arrival — the mistake this suite exists
        for.
        """
        config = yaml.safe_load((PROMETHEUS_DIR / "prometheus.yml").read_text(encoding="utf-8"))

        assert "alerts-core.yml" in config["rule_files"]
        assert "alerts.yml" not in config["rule_files"]
        assert "alert_rules.yml" not in config["rule_files"]

    @pytest.mark.parametrize("rule", _core_alerts(), ids=_alert_names())
    def test_alert_links_to_a_runbook_that_exists(self, rule: dict[str, Any]):
        """Every core alert points an on-call operator at a real document."""
        runbook = rule.get("annotations", {}).get("runbook")

        assert runbook, f"{rule['alert']} carries no runbook annotation"
        assert (REPO_ROOT / runbook).is_file(), f"{rule['alert']} links to a missing {runbook}"

    @pytest.mark.parametrize("rule", _core_alerts(), ids=_alert_names())
    def test_alert_carries_the_core_tier_and_a_known_severity(self, rule: dict[str, Any]):
        """`tier: core` is what Alertmanager routes on; severity drives urgency."""
        labels = rule.get("labels", {})

        assert labels.get("tier") == "core", f"{rule['alert']} is not labelled tier: core"
        assert labels.get("severity") in {
            "critical",
            "warning",
        }, f"{rule['alert']} has severity {labels.get('severity')!r}"

    @pytest.mark.parametrize("name", _alert_names())
    def test_alert_has_at_least_one_promtool_case(self, name: str):
        """Adding an alert without a test case must not be possible.

        The promtool suite is what proves an expression fires on the series it
        claims to watch and that its description quotes the threshold it
        actually uses. An untested alert is an assertion about production that
        nobody has ever checked.
        """
        suite = yaml.safe_load(PROMTOOL_TESTS.read_text(encoding="utf-8"))
        tested = {
            case["alertname"]
            for block in suite["tests"]
            for case in block.get("alert_rule_test", [])
        }

        assert name in tested, f"{name} has no case in tests/alerts_core_test.yml"


class TestThresholdParityAcrossEnvironments:
    """A threshold missing from one environment breaks that environment only."""

    def test_every_environment_declares_the_same_core_thresholds(self):
        """StrictUndefined turns a forgotten key into a deploy-time crash.

        The failure is asymmetric and therefore easy to miss: rendering with
        production thresholds succeeds locally while staging or development
        aborts ``prepare_config.sh``, which stops the whole config preparation.
        """
        keys = {
            environment: {
                k
                for k in dotenv_values(THRESHOLDS_DIR / f"{environment}.env")
                if k.startswith("ALERT_CORE_")
            }
            for environment in ENVIRONMENTS
        }
        reference = keys[RENDERED_ENVIRONMENT]

        for environment in ENVIRONMENTS:
            assert keys[environment] == reference, (
                f"{environment}.env core thresholds differ from {RENDERED_ENVIRONMENT}.env: "
                f"missing={sorted(reference - keys[environment])}, "
                f"extra={sorted(keys[environment] - reference)}"
            )

    @pytest.mark.parametrize("environment", ENVIRONMENTS)
    def test_template_renders_for_every_environment(self, environment: str):
        """Each environment's threshold set must actually satisfy the template."""
        rendered = _render(environment)

        assert yaml.safe_load(rendered)["groups"], f"{environment} rendered no alert groups"
