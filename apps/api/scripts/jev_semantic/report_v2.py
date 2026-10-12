"""Version 2's verdicts under the SAME rule as version 1 (fixed 2026-10-11, before any paid call).

Single-label decisions: at the threshold chosen on calibration, the independent
corpus's confident accuracy beats the current mechanism by 3 points (98 % floor for
d1/d5), with at most 10 % abstention and p95 under 600 ms. Multi-label decisions
(Noul sets) transpose it: the decision cut-point is chosen on calibration, the exact
set accuracy on the independent corpus beats the reference by 3 points, nothing
abstains, p95 under 600 ms. d5 is also compared with the planned typed guard
(Lot B) under PERFECT typing — the question the plan actually asks.

    python -m scripts.jev_semantic.report_v2 --output /app/.tmp/jev-semantic/report_v2.json
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
from scripts.jev_semantic.report import MARGIN, MAX_ABSTENTION, MAX_P95_MS, RESULTS, SAFETY_FLOOR

Row = Mapping[str, object]
CUTS: tuple[float, ...] = tuple(round(0.05 * i, 2) for i in range(1, 20))


def _load(decision: str, variant: str) -> dict[str, list[Row]]:
    out: dict[str, list[Row]] = {"calibration": [], "independent": []}
    for path in sorted(RESULTS.glob(f"{decision}-*-{variant}-*.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        if report.get("variant") == variant:
            out[str(report["split"])].extend(report["rows"])
    return out


def _engine(rows: Sequence[Row], engine: str, first_only: bool = True) -> list[Row]:
    return [r for r in rows if r["engine"] == engine and (not first_only or int(r.get("repeat") or 0) == 0)]  # type: ignore[arg-type]


def _num(value: object) -> float | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return float(value)  # type: ignore[arg-type]


def single(decision: str, variant: str, key: str, gold_only: bool = False) -> dict[str, object]:
    """A single-label verdict; the reference is ``current`` where it exists."""
    data = _load(decision, variant)
    cal, ind = data["calibration"], data["independent"]
    if gold_only:
        cal = [r for r in cal if r.get("gold")]
        ind = [r for r in ind if r.get("gold")]
    out: dict[str, object] = {"decision": decision, "variant": variant, "key": key}
    others: dict[str, object] = {}
    for engine in ("current", "lot_b", "generative"):
        rows = _engine(ind, engine)
        if rows:
            others[engine] = {
                **single_label(rows, key),
                **cost_latency(_engine(ind, engine, False)),
            }
    out["baselines"] = others
    reference_name = "current" if "current" in others else "generative"
    reference = _num(others.get(reference_name, {}).get("forced_accuracy"))  # type: ignore[union-attr]
    floor = SAFETY_FLOOR.get(decision, 0.0)
    target = max(floor, (reference or 0.0) + MARGIN)
    threshold = choose_threshold(_engine(cal, "jev"), target, key)
    applied = threshold if threshold is not None else 0.99
    jev_rows = _engine(ind, "jev")
    jev = {
        **single_label(jev_rows, key, applied),
        "forced": single_label(jev_rows, key, 0.0)["forced_accuracy"],
        **cost_latency(_engine(ind, "jev", False)),
        "stability": stability(_engine(ind, "jev", False)),
        "calibration_buckets": calibration(jev_rows, key),
        "threshold_from_calibration": threshold,
    }
    out["jev"] = jev
    accuracy = _num(jev["selective_accuracy"])
    abstention = _num(jev["abstention"]) or 0.0
    p95 = _num(jev["latency_ms_p95"]) or float("inf")
    checks = {
        "threshold_found_on_calibration": threshold is not None,
        f"beats_{reference_name}_by_3_points": accuracy is not None
        and reference is not None
        and accuracy >= reference + MARGIN,
        "meets_safety_floor": accuracy is not None and accuracy >= floor,
        "abstention_at_most_10_percent": abstention <= MAX_ABSTENTION,
        "p95_under_600_ms": p95 < MAX_P95_MS,
    }
    out["reference"] = {"engine": reference_name, "accuracy": reference, "target": target}
    out["checks"] = checks
    out["adopt"] = all(checks.values())
    if "lot_b" in others:
        lot_b = _num(others["lot_b"]["forced_accuracy"])  # type: ignore[index]
        out["vs_planned_guard"] = {
            "lot_b_forced_accuracy": lot_b,
            "jev_selective_accuracy": accuracy,
            "jev_beats_lot_b_by_3_points": accuracy is not None
            and lot_b is not None
            and accuracy >= lot_b + MARGIN,
        }
    return out


def _cut(rows: Sequence[Row], prefix: str, labels: Sequence[str], cut: float) -> list[Row]:
    """Rows relabelled from the Noul probability at ``cut`` (rows without one unchanged)."""
    out = []
    for r in rows:
        confidence = r.get("confidence") or {}
        answers = dict(r.get("labels") or {})  # type: ignore[call-overload]
        for label in labels:
            p = confidence.get(f"{prefix}{label}__p")  # type: ignore[union-attr]
            if p is not None:
                answers[f"{prefix}{label}"] = "yes" if float(p) >= cut else "no"
        out.append({**r, "labels": answers, "confidence": {}})
    return out


def multi(decision: str, variant: str, prefix: str, labels: Sequence[str]) -> dict[str, object]:
    """A Noul set: cut-point from calibration, exact-set accuracy on the independent corpus."""
    data = _load(decision, variant)
    cal, ind = data["calibration"], data["independent"]
    best: tuple[float, float] | None = None
    for cut in CUTS:
        score = (
            _num(
                multi_label(_cut(_engine(cal, "jev"), prefix, labels, cut), prefix, labels)[
                    "exact_set_accuracy"
                ]
            )
            or 0.0
        )
        if best is None or score > best[0]:
            best = (score, cut)
    cut = best[1] if best else 0.5
    out: dict[str, object] = {"decision": decision, "variant": variant, "cut_from_calibration": cut}
    for engine in ("current", "generative"):
        rows = _engine(ind, engine)
        if rows:
            out[engine] = {
                **multi_label(rows, prefix, labels),
                **cost_latency(_engine(ind, engine, False)),
            }
    jev_rows = _engine(ind, "jev")
    out["jev"] = {
        **multi_label(_cut(jev_rows, prefix, labels, cut), prefix, labels),
        "at_half": multi_label(_cut(jev_rows, prefix, labels, 0.5), prefix, labels)[
            "exact_set_accuracy"
        ],
        **cost_latency(_engine(ind, "jev", False)),
        "stability": stability(_engine(ind, "jev", False)),
    }
    reference_name = "current" if "current" in out and decision == "d3" else "generative"
    reference = _num(out.get(reference_name, {}).get("exact_set_accuracy"))  # type: ignore[union-attr]
    accuracy = _num(out["jev"]["exact_set_accuracy"])  # type: ignore[index]
    p95 = _num(out["jev"]["latency_ms_p95"]) or float("inf")  # type: ignore[index]
    out["reference"] = {"engine": reference_name, "exact_set_accuracy": reference}
    out["checks"] = {
        f"beats_{reference_name}_by_3_points": accuracy is not None
        and reference is not None
        and accuracy >= reference + MARGIN,
        "p95_under_600_ms": p95 < MAX_P95_MS,
    }
    out["adopt"] = all(out["checks"].values())  # type: ignore[union-attr]
    return out


def order_bias() -> dict[str, object]:
    """d1: the same cases with the options reversed — agreement and accuracy each way."""
    forward = {r["id"]: r for r in _engine(_load("d1", "v2")["independent"], "jev")}
    reverse = {r["id"]: r for r in _engine(_load("d1", "v2rev")["independent"], "jev")}
    common = sorted(set(forward) & set(reverse))
    agree = sum(1 for i in common if (forward[i]["labels"] or {}).get("answer") == (reverse[i]["labels"] or {}).get("answer"))  # type: ignore[union-attr]
    return {
        "cases": len(common),
        "agreement": agree / len(common) if common else None,
        "forward": single_label([forward[i] for i in common], "answer"),
        "reverse": single_label([reverse[i] for i in common], "answer"),
    }


def d2_fallback(variant: str, threshold: float | None) -> dict[str, object]:
    """d2: below the threshold, answer the chosen type's category (scored leniently)."""
    rows = _engine(_load("d2", variant)["independent"], "jev")
    cut = threshold if threshold is not None else 0.99
    correct = 0
    for r in rows:
        labels = r.get("labels") or {}
        confidence = (r.get("confidence") or {}).get("answer")  # type: ignore[union-attr]
        accepted = set(r["accepted"])  # type: ignore[arg-type]
        lenient = accepted | set(r["lenient"])  # type: ignore[arg-type]
        if confidence is not None and float(confidence) >= cut:
            correct += labels.get("answer") in accepted  # type: ignore[union-attr]
        else:
            correct += labels.get("answer_parent") in lenient  # type: ignore[union-attr]
    return {
        "threshold": cut,
        "cases": len(rows),
        "accuracy_with_category_fallback": correct / len(rows) if rows else None,
    }


def main(output: Path) -> None:
    """Every version 2 verdict in one evidence file."""
    from scripts.jev_semantic.corpus_d4 import LABELS as D4_LABELS

    d3_labels = sorted(
        {str(label) for rows in _load("d3", "v2").values() for r in rows for label in r["required"]}  # type: ignore[union-attr]
        | {str(r["gold"]) for rows in _load("d3", "v2").values() for r in rows if r.get("gold")}
    )
    menu_path = RESULTS / "menu_labels.json"
    if menu_path.exists():
        d3_labels = json.loads(menu_path.read_text())
    d2 = single("d2", "v2", "answer")
    report = {
        "d1_v2": single("d1", "v2", "answer"),
        "d1_order_bias": order_bias(),
        "d5_kind": single("d5", "v2", "kind_verdict"),
        "d5_noul": single("d5", "v2", "noul_verdict"),
        "d5_both": single("d5", "v2", "both_verdict"),
        "d3_primary": single("d3", "v2", "primary", gold_only=True),
        "d3_relevance": multi("d3", "v2", "rel_", d3_labels),
        "d4": multi("d4", "v2", "needs_", sorted(D4_LABELS)),
        "d2_flat": d2,
        "d2_fallback": d2_fallback("v2", d2["jev"]["threshold_from_calibration"]),  # type: ignore[index]
    }
    # Version 2 kept its own ledger so it could run beside version 1.
    report["spent_eur"] = {
        name: json.loads((RESULTS / name).read_text())["spent_eur"]
        for name in ("spend.json", "spend_v2.json")
        if (RESULTS / name).exists()
    }
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8"
    )
    for name, section in report.items():
        if isinstance(section, dict) and "adopt" in section:
            print(f"{name:<14} adopt={section['adopt']!s:<5} checks={section['checks']}")
    print(json.dumps(report["d1_order_bias"]["agreement"]), "order agreement")  # type: ignore[index]
    print(f"spent_eur={report['spent_eur']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=RESULTS / "report_v2.json")
    main(parser.parse_args().output)
