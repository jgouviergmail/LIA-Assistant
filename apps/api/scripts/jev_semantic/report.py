"""Apply the rule fixed before measuring, decision by decision, and write the evidence.

The rule (approved 2026-10-11, before any paid call): a decision point enters the
plan if, on the INDEPENDENT corpus, at the threshold chosen on the CALIBRATION
corpus, JEV's confident accuracy beats the current mechanism (or the generative
slot where none exists) by at least 3 points — and reaches at least 98 % for d1
and d5 — with at most 10 % abstention and a p95 latency under 600 ms.

    python -m scripts.jev_semantic.report --output /app/.tmp/jev-semantic/report.json
"""

import argparse
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path

from scripts.jev_semantic.metrics import (
    calibration,
    choose_threshold,
    cost_latency,
    multi_label,
    single_label,
    stability,
)

RESULTS = Path("/app/.tmp/jev-semantic")
SAFETY_FLOOR = {"d1": 0.98, "d5": 0.98}
MARGIN = 0.03
MAX_ABSTENTION = 0.10
MAX_P95_MS = 600.0

Row = Mapping[str, object]


def _load(decision: str, variant: str) -> dict[str, list[Row]]:
    """Rows of every file of a decision/variant, keyed by split."""
    out: dict[str, list[Row]] = {"calibration": [], "independent": []}
    for path in sorted(RESULTS.glob(f"{decision}-*-{variant}-*.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        out[str(report["split"])].extend(report["rows"])
    return out


def _engine(rows: Sequence[Row], engine: str) -> list[Row]:
    return [r for r in rows if r["engine"] == engine]


def _first_repeat(rows: Sequence[Row]) -> list[Row]:
    return [r for r in rows if int(r.get("repeat") or 0) == 0]  # type: ignore[arg-type]


def _finite(value: object) -> float | None:
    return None if value is None or (isinstance(value, float) and math.isnan(value)) else float(value)  # type: ignore[arg-type]


def single_decision(decision: str, variant: str, key: str = "answer") -> dict[str, object]:
    """Single-label decision (d1, d2, d5, d3 primary): threshold on calibration, verdict on independent."""
    data = _load(decision, variant)
    cal, ind = data["calibration"], data["independent"]
    if decision == "d3":
        cal = [r for r in cal if r.get("gold")]
        ind = [r for r in ind if r.get("gold")]
    out: dict[str, object] = {"decision": decision, "variant": variant, "key": key}
    baselines: dict[str, dict[str, object]] = {}
    for engine in ("current", "generative"):
        rows = _first_repeat(_engine(ind, engine))
        if rows:
            baselines[engine] = {
                **single_label(rows, key),
                **cost_latency(_engine(ind, engine)),
                "stability": stability(_engine(ind, engine)),
            }
    out["baselines"] = baselines
    reference_name = "current" if "current" in baselines else "generative"
    reference = _finite(baselines.get(reference_name, {}).get("forced_accuracy"))
    floor = SAFETY_FLOOR.get(decision, 0.0)
    target = max(floor, (reference or 0.0) + MARGIN)
    jev_cal = _first_repeat(_engine(cal, "jev"))
    threshold = choose_threshold(jev_cal, target, key) if jev_cal else None
    jev_ind = _engine(ind, "jev")
    applied = threshold if threshold is not None else 0.99
    jev = {
        **single_label(_first_repeat(jev_ind), key, applied),
        "forced": single_label(_first_repeat(jev_ind), key, 0.0)["forced_accuracy"],
        **cost_latency(jev_ind),
        "stability": stability(jev_ind),
        "calibration_buckets": calibration(_first_repeat(jev_ind), key),
        "threshold_from_calibration": threshold,
    }
    out["jev"] = jev
    accuracy = _finite(jev["selective_accuracy"])
    abstention = _finite(jev["abstention"]) or 0.0
    p95 = _finite(jev["latency_ms_p95"]) or float("inf")
    checks = {
        "threshold_found_on_calibration": threshold is not None,
        f"beats_{reference_name}_by_{int(MARGIN * 100)}_points": accuracy is not None
        and reference is not None
        and accuracy >= reference + MARGIN,
        "meets_safety_floor": accuracy is not None and accuracy >= floor,
        "abstention_at_most_10_percent": abstention <= MAX_ABSTENTION,
        "p95_under_600_ms": p95 < MAX_P95_MS,
    }
    out["reference"] = {"engine": reference_name, "accuracy": reference, "target": target}
    out["checks"] = checks
    out["adopt"] = all(checks.values())
    return out


def multi_decision(decision: str, prefix: str, labels: Sequence[str]) -> dict[str, object]:
    """Multi-label view (d3 relevance, d4 entities) on the independent split, thresholds from calibration."""
    data = _load(decision, "default")
    cal, ind = data["calibration"], data["independent"]
    out: dict[str, object] = {"decision": decision, "multi_label": True}
    for engine in ("current", "generative"):
        rows = _first_repeat(_engine(ind, engine))
        if rows:
            out[engine] = multi_label(rows, prefix, labels)
    jev_cal = _first_repeat(_engine(cal, "jev"))
    best = None
    for threshold in (0.0, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95):
        result = multi_label(jev_cal, prefix, labels, threshold)
        score = (_finite(result["exact_set_accuracy"]) or 0.0) * (
            _finite(result["set_coverage"]) or 0.0
        )
        if best is None or score > best[0]:
            best = (score, threshold)
    threshold = best[1] if best else 0.0
    jev_ind = _engine(ind, "jev")
    out["jev"] = {
        **multi_label(_first_repeat(jev_ind), prefix, labels, threshold),
        "forced": multi_label(_first_repeat(jev_ind), prefix, labels, 0.0),
        **cost_latency(jev_ind),
        "stability": stability(jev_ind),
        "threshold_from_calibration": threshold,
    }
    return out


def main(output: Path) -> None:
    """Every decision's verdict in one evidence file."""
    from scripts.jev_semantic.corpus_d4 import LABELS as D4_LABELS

    menu_labels: list[str] = sorted(
        {str(r["gold"]) for rows in _load("d3", "default").values() for r in rows if r.get("gold")}
        | {
            label
            for rows in _load("d3", "default").values()
            for r in rows
            for label in r["required"]  # type: ignore[union-attr]
        }
    )
    report = {
        "rule": {
            "margin_points": MARGIN * 100,
            "safety_floor": SAFETY_FLOOR,
            "max_abstention": MAX_ABSTENTION,
            "max_p95_ms": MAX_P95_MS,
        },
        "d1": single_decision("d1", "default"),
        "d5": single_decision("d5", "default"),
        "d4": multi_decision("d4", "needs_", sorted(D4_LABELS)),
        "d3_primary": single_decision("d3", "default", key="primary"),
        "d3_relevance": multi_decision("d3", "rel_", menu_labels),
        "d2_flat_registry": single_decision("d2", "flat-registry"),
        "d2_flat_aligned": single_decision("d2", "flat-aligned"),
        "d2_hierarchical_aligned": single_decision("d2", "hierarchical-aligned"),
    }
    spend = RESULTS / "spend.json"
    report["spent_eur"] = json.loads(spend.read_text())["spent_eur"] if spend.exists() else None
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8"
    )
    for name, section in report.items():
        if isinstance(section, dict) and "adopt" in section:
            jev = section["jev"]
            print(
                f"{name:<26} adopt={section['adopt']!s:<5} jev_sel={jev['selective_accuracy']!s:.6} "
                f"cov={jev['coverage']!s:.5} ref={section['reference']} p95={jev['latency_ms_p95']}"
            )
    print(f"spent_eur={report['spent_eur']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=RESULTS / "report.json")
    main(parser.parse_args().output)
