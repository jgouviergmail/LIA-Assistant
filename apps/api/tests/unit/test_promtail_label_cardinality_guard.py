"""Loki labels must stay bounded, and the structured payload must survive.

Every label a Promtail pipeline promotes multiplies the number of STREAMS Loki
keeps in memory: streams are the cartesian product of label values. Promoting a
field with an open value set is therefore not "more searchable", it is a slow
out-of-memory.

Measured on the production instance, 2026-08-05::

    /loki/api/v1/label/event/values   -> 1416 distinct values
    /loki/api/v1/label/logger/values  ->  140
    /loki/api/v1/label/trace_id/values->  107   (one per request: unbounded)
    loki_ingester_memory_streams       ->  771 and climbing

with four kernel OOM kills of the Loki container over the audited week — two of
them triggered by a single 7-day query, i.e. the tool collapsed at the exact
moment it was needed. Those fields stay perfectly queryable through ``| json``,
which filters at read time without creating a stream.

The second rule concerns the ``output`` stage. ``output: source: message``
REPLACES the log line with the content of one field, so every structlog entry
that carries a ``message`` key reached Loki stripped of its JSON — the audit
first read those lines as stray ``print()`` calls in the code. A pipeline may
not destroy the payload it transports.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pytest
import yaml

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

REPO_ROOT = repo_root_or_skip()
PROMTAIL_CONFIG = (
    REPO_ROOT / "infrastructure" / "observability" / "promtail" / "promtail-config.yml"
)

# Fields whose value set is open (or per-request) and that must never become a
# Loki label, with the measured cardinality that settles the question.
FORBIDDEN_LABELS: dict[str, str] = {
    "event": "1416 distinct values in production",
    "logger": "140 distinct values, and it grows with every new module",
    "trace_id": "one value per request — unbounded by construction",
    "node_name": "one per graph node, and it feeds the same explosion",
    "intention": "router taxonomy, better filtered at read time",
    "error_type": "open set: every exception class that ever surfaces",
}

# Labels whose value set is small, closed and useful for stream selection.
ALLOWED_LABELS = frozenset({"level", "job"})


def _pipeline_stages() -> list[dict[str, Any]]:
    config = yaml.safe_load(PROMTAIL_CONFIG.read_text(encoding="utf-8"))
    stages: list[dict[str, Any]] = []
    for scrape in config.get("scrape_configs") or []:
        stages.extend(scrape.get("pipeline_stages") or [])
    return stages


def _declared_labels() -> dict[str, Any]:
    declared: dict[str, Any] = {}
    for stage in _pipeline_stages():
        if "labels" in stage and isinstance(stage["labels"], dict):
            declared.update(stage["labels"])
    return declared


class TestLabelCardinalityStaysBounded:
    """A label is a stream multiplier, not a search field."""

    def test_the_config_is_readable(self) -> None:
        """Guards that silently find nothing are worse than no guards."""
        assert PROMTAIL_CONFIG.is_file(), f"{PROMTAIL_CONFIG} not found"
        assert _pipeline_stages(), "no pipeline stage parsed — the assertions below would be void"

    @pytest.mark.parametrize(("field", "reason"), sorted(FORBIDDEN_LABELS.items()))
    def test_high_cardinality_field_is_not_a_label(self, field: str, reason: str) -> None:
        declared = _declared_labels()

        assert field not in declared, (
            f"'{field}' is promoted to a Loki label ({reason}). Every value creates a "
            f"stream; production reached 771 streams and Loki was OOM-killed four times "
            f'in a week. Filter it at read time instead: `{{container="lia-api-prod"}} '
            f'| json | {field}="..."`.'
        )

    def test_every_declared_label_is_explicitly_allowed(self) -> None:
        """A new label must be a decision, not a reflex."""
        unexpected = sorted(set(_declared_labels()) - ALLOWED_LABELS)

        assert not unexpected, (
            f"labels promoted without being on the bounded allowlist: {unexpected}. "
            f"Add them to ALLOWED_LABELS only if their value set is small and CLOSED; "
            f"otherwise query them with `| json`."
        )


class TestThePayloadSurvivesThePipeline:
    """What Loki stores must remain what the application emitted."""

    def test_no_output_stage_replaces_the_line(self) -> None:
        outputs = [stage["output"] for stage in _pipeline_stages() if "output" in stage]

        assert not outputs, (
            f"an `output` stage rewrites the log line ({outputs}): every entry carrying "
            f"that field reaches Loki stripped of its JSON, so `| json` cannot parse it "
            f"and the audit trail reads as unstructured text. Drop the stage and let the "
            f"original line through."
        )


class TestDashboardsQueryWhatPromtailActuallyIndexes:
    """A panel selecting on a non-label silently returns nothing.

    A Loki stream selector may only name labels the pipeline promotes. Query a
    field that is no longer a label and Loki does not error — it matches no
    stream and the panel goes quiet, which is the worst failure mode for a
    dashboard: it looks healthy.

    The forbidden set is DERIVED from the pipeline above rather than restated, so
    demoting a label and forgetting a panel fails here instead of in production.
    """

    DASHBOARDS = REPO_ROOT / "infrastructure" / "observability" / "grafana" / "dashboards"

    @staticmethod
    def _expressions(payload: Any) -> list[str]:
        found: list[str] = []

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                if isinstance(node.get("expr"), str):
                    found.append(node["expr"])
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        walk(payload)
        return found

    def test_no_panel_selects_a_stream_by_a_demoted_field(self) -> None:
        promoted = set(_declared_labels()) | {"job"}
        offenders: list[str] = []

        for dashboard in sorted(self.DASHBOARDS.glob("*.json")):
            payload = json.loads(dashboard.read_text(encoding="utf-8"))
            for expression in self._expressions(payload):
                for selector in re.findall(r"\{[^{}]*\}", expression):
                    # Only Loki stream selectors — Prometheus series selectors
                    # legitimately carry metric labels such as node_name.
                    if not re.search(r"\b(job|container)\s*=", selector):
                        continue
                    for field in FORBIDDEN_LABELS:
                        if field in promoted:
                            continue
                        if re.search(rf'(?<![\w_]){field}\s*=~?\s*"', selector):
                            offenders.append(f"{dashboard.name}: [{field}] {expression[:90]}")

        assert not offenders, (
            "dashboard panels select Loki streams by a field that is no longer a label — "
            "they will match nothing and display an empty graph without any error:\n  "
            + "\n  ".join(offenders)
            + '\nMove the field after the parser: `{job="api"} |= "value" | json | field="value"`.'
        )
