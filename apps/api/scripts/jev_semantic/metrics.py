"""Metrics for the qualification: accuracy, selectivity, calibration, stability, latency, cost."""

import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence

Row = Mapping[str, object]
THRESHOLDS: tuple[float, ...] = tuple(round(0.30 + 0.01 * i, 2) for i in range(70))


def percentile(values: Sequence[float], q: float) -> float | None:
    """Nearest-rank percentile; None for an empty sample."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, math.ceil(q * len(ordered)) - 1))]


def _correct(row: Row, key: str, lenient: bool) -> bool:
    label = (row.get("labels") or {}).get(key)  # type: ignore[union-attr]
    accepted = set(row["accepted"]) | (set(row["lenient"]) if lenient else set())  # type: ignore[arg-type]
    return label in accepted


def _confident(row: Row, key: str, threshold: float) -> bool:
    if (row.get("labels") or {}).get(key) is None:  # type: ignore[union-attr]
        return False
    confidence = (row.get("confidence") or {}).get(key)  # type: ignore[union-attr]
    return confidence is None or float(confidence) >= threshold


def single_label(
    rows: Sequence[Row], key: str = "answer", threshold: float = 0.0
) -> dict[str, object]:
    """Forced and selective accuracy, per-class precision/recall, confusion, by family."""
    answered = [r for r in rows if (r.get("labels") or {}).get(key) is not None]  # type: ignore[union-attr]
    covered = [r for r in rows if _confident(r, key, threshold)]
    strict = sum(_correct(r, key, False) for r in answered)
    covered_strict = sum(_correct(r, key, False) for r in covered)
    covered_lenient = sum(_correct(r, key, True) for r in covered)
    per_class: dict[str, dict[str, float]] = {}
    gold_counts = Counter(str(r["gold"]) for r in rows)
    predicted_counts = Counter(str((r.get("labels") or {}).get(key)) for r in covered)  # type: ignore[union-attr]
    for label in sorted(set(gold_counts) | set(predicted_counts) - {"None"}):
        tp = sum(
            1 for r in covered if (r.get("labels") or {}).get(key) == label and _correct(r, key, False)  # type: ignore[union-attr]
        )
        per_class[label] = {
            "precision": tp / predicted_counts[label] if predicted_counts[label] else float("nan"),
            "recall_of_gold": (
                sum(1 for r in covered if r["gold"] == label and _correct(r, key, False))
                / gold_counts[label]
                if gold_counts[label]
                else float("nan")
            ),
            "gold": gold_counts[label],
        }
    confusion: dict[str, Counter[str]] = defaultdict(Counter)
    for r in rows:
        confusion[str(r["gold"])][str((r.get("labels") or {}).get(key))] += 1  # type: ignore[union-attr]
    families: dict[str, dict[str, float]] = {}
    for family in sorted({str(r["family"]) for r in rows}):
        members = [r for r in rows if r["family"] == family]
        fam_covered = [r for r in members if _confident(r, key, threshold)]
        families[family] = {
            "cases": len(members),
            "coverage": len(fam_covered) / len(members),
            "selective_accuracy": (
                sum(_correct(r, key, False) for r in fam_covered) / len(fam_covered)
                if fam_covered
                else float("nan")
            ),
        }
    return {
        "cases": len(rows),
        "errors": sum(1 for r in rows if r.get("error")),
        "forced_accuracy": strict / len(rows) if rows else float("nan"),
        "threshold": threshold,
        "coverage": len(covered) / len(rows) if rows else float("nan"),
        "abstention": 1 - len(covered) / len(rows) if rows else float("nan"),
        "selective_accuracy": covered_strict / len(covered) if covered else float("nan"),
        "selective_accuracy_lenient": covered_lenient / len(covered) if covered else float("nan"),
        "per_class": per_class,
        "confusion": {gold: dict(row) for gold, row in confusion.items()},
        "families": families,
    }


def choose_threshold(rows: Sequence[Row], target: float, key: str = "answer") -> float | None:
    """The lowest threshold reaching ``target`` selective accuracy on CALIBRATION rows.

    The lowest such threshold maximises coverage. None when no threshold reaches
    the target (the decision point then fails its rule without being re-tuned).
    """
    for threshold in THRESHOLDS:
        result = single_label(rows, key, threshold)
        covered = float(result["coverage"])  # type: ignore[arg-type]
        accuracy = float(result["selective_accuracy"])  # type: ignore[arg-type]
        if covered > 0 and not math.isnan(accuracy) and accuracy >= target:
            return threshold
    return None


def calibration(rows: Sequence[Row], key: str = "answer") -> list[dict[str, float]]:
    """Accuracy per declared-confidence bucket (a concentration is not a probability)."""
    buckets: dict[float, list[bool]] = defaultdict(list)
    for r in rows:
        confidence = (r.get("confidence") or {}).get(key)  # type: ignore[union-attr]
        if confidence is None:
            continue
        bucket = min(0.9, math.floor(float(confidence) * 10) / 10)
        buckets[bucket].append(_correct(r, key, False))
    return [
        {"from": b, "to": round(b + 0.1, 1), "cases": len(v), "accuracy": sum(v) / len(v)}
        for b, v in sorted(buckets.items())
    ]


def multi_label(
    rows: Sequence[Row], prefix: str, labels: Iterable[str], threshold: float = 0.0
) -> dict[str, object]:
    """Per-label precision/recall and exact-set accuracy for yes/no question families."""
    labels = list(labels)
    per_label: dict[str, dict[str, float]] = {}
    exact = covered_sets = 0
    for r in rows:
        answers = r.get("labels") or {}
        confidences = r.get("confidence") or {}
        keys = [f"{prefix}{label}" for label in labels]
        if all(k in answers for k in keys) and all(  # type: ignore[operator]
            confidences.get(k) is None or float(confidences[k]) >= threshold for k in keys  # type: ignore[union-attr,index]
        ):
            covered_sets += 1
            chosen = {label for label in labels if answers.get(f"{prefix}{label}") == "yes"}  # type: ignore[union-attr]
            if set(r["required"]) <= chosen <= set(r["required"]) | set(r["optional"]):  # type: ignore[arg-type]
                exact += 1
    for label in labels:
        key = f"{prefix}{label}"
        scored = [r for r in rows if key in (r.get("labels") or {})]  # type: ignore[operator]
        predicted_yes = [r for r in scored if r["labels"][key] == "yes"]  # type: ignore[index]
        tp = [r for r in predicted_yes if label in set(r["required"]) | set(r["optional"])]  # type: ignore[arg-type]
        gold_yes = [r for r in scored if label in set(r["required"])]  # type: ignore[arg-type]
        found = [r for r in gold_yes if r["labels"][key] == "yes"]  # type: ignore[index]
        per_label[label] = {
            "precision": len(tp) / len(predicted_yes) if predicted_yes else float("nan"),
            "recall": len(found) / len(gold_yes) if gold_yes else float("nan"),
            "gold_yes": len(gold_yes),
        }
    return {
        "cases": len(rows),
        "threshold": threshold,
        "set_coverage": covered_sets / len(rows) if rows else float("nan"),
        "exact_set_accuracy": exact / covered_sets if covered_sets else float("nan"),
        "per_label": per_label,
    }


def stability(rows: Sequence[Row]) -> float | None:
    """Share of cases whose answers are identical across repetitions."""
    by_case: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        by_case[str(r["id"])].append(repr(sorted((r.get("labels") or {}).items())))  # type: ignore[union-attr]
    repeated = [answers for answers in by_case.values() if len(answers) > 1]
    if not repeated:
        return None
    return sum(1 for answers in repeated if len(set(answers)) == 1) / len(repeated)


def cost_latency(rows: Sequence[Row]) -> dict[str, object]:
    """Latency percentiles per decision and cost totals."""
    latencies = [float(r["latency_ms"]) for r in rows if r.get("latency_ms")]  # type: ignore[arg-type]
    costs = [float(r.get("cost_eur") or 0.0) for r in rows]  # type: ignore[arg-type]
    return {
        "decisions": len(rows),
        "latency_ms_p50": percentile(latencies, 0.50),
        "latency_ms_p95": percentile(latencies, 0.95),
        "latency_ms_p99": percentile(latencies, 0.99),
        "cost_eur_total": sum(costs),
        "cost_eur_per_decision": sum(costs) / len(costs) if costs else None,
        "calls": sum(int(r.get("calls") or 0) for r in rows),  # type: ignore[arg-type]
    }
