"""Verdicts of the realignment, under a rule fixed before any paid call (2026-10-11).

For each usage, the shipped question runs at its shipped threshold. The aligned
candidate's threshold is chosen on the CALIBRATION split: the one that keeps the
wrong shortcuts at or below the shipped question's count on that split and
maximises the coverage (ties: the stricter threshold). On the HOLDOUT split, both
repetitions pooled, the candidate replaces the shipped question iff it takes no
more wrong shortcuts AND covers at least as much. The reversed-option twin of the
shipped question measures Choice's first-option bias at the shipped threshold.

    python -m scripts.jev_alignment.evaluate

The ``threshold is None`` branches encode the questions as SHIPPED BEFORE the
realignment (2026-10-11): the evidence in
``docs/superpowers/qualification/jev-semantic-2026-10-11/alignment.json`` was
measured against them. The four adopted candidates now ship; re-running this
comparison afterwards measures a candidate against itself for those usages.
"""

import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from statistics import median
from typing import Any

OUT = Path("/app/.tmp/jev-alignment")
Row = Mapping[str, Any]
PROBABILITIES = tuple(round(0.01 * i, 2) for i in range(1, 100))
CONFIDENCES = tuple(round(0.5 + 0.01 * i, 2) for i in range(50)) + (0.995, 0.999)


def _label(row: Row, key: str) -> str | None:
    return (row.get("labels") or {}).get(key)


def _conf(row: Row, key: str) -> float:
    return float((row.get("confidence") or {}).get(key, 0.0))


def _p(row: Row, key: str) -> float | None:
    value = (row.get("confidence") or {}).get(f"{key}__p")
    return None if value is None else float(value)


# Every decision answers (shortcut_taken, correct_when_taken) for one row.
Decision = Callable[[Row], tuple[bool, bool]]


def _single(shortcut: Callable[[Row], bool], allowed: Callable[[Row], bool]) -> Decision:
    def decide(row: Row) -> tuple[bool, bool]:
        taken = shortcut(row)
        return taken, taken and allowed(row)

    return decide


def memory(threshold: float | None) -> Decision:
    allowed = lambda r: r["gold"]["absent"]  # noqa: E731
    if threshold is None:
        return _single(
            lambda r: _label(r, "selection") == "absent" and _conf(r, "selection") >= 0.99, allowed
        )
    return _single(lambda r: (_p(r, "needs_identity") is not None and _p(r, "needs_identity") <= threshold), allowed)  # type: ignore[operator]


def rejection(threshold: float | None) -> Decision:
    allowed = lambda r: r["gold"]["reject"]  # noqa: E731
    if threshold is None:
        return _single(
            lambda r: _label(r, "selection") == "reject_all" and _conf(r, "selection") >= 0.99,
            allowed,
        )
    return _single(lambda r: (_p(r, "refuses_all") is not None and _p(r, "refuses_all") >= threshold), allowed)  # type: ignore[operator]


def initiative(threshold: float | None) -> Decision:
    allowed = lambda r: not r["gold"]["utility"]  # noqa: E731
    if threshold is None:
        return _single(
            lambda r: _label(r, "selection") == "no_utility" and _conf(r, "selection") >= 0.85,
            allowed,
        )
    return _single(lambda r: (_p(r, "has_utility") is not None and _p(r, "has_utility") <= threshold), allowed)  # type: ignore[operator]


def consultation(threshold: float | None) -> Decision:
    def decide(row: Row) -> tuple[bool, bool]:
        shipped = 0.97 if row["gold"]["bounded"] else 0.99
        choice = _label(row, "selection")
        taken = choice not in (None, "other") and _conf(row, "selection") >= (
            shipped if threshold is None else threshold
        )
        return taken, taken and choice == row["gold"]["expected"]

    return decide


def radio(threshold: float | None) -> Decision:
    def decide(row: Row) -> tuple[bool, bool]:
        keys = row["keys"]
        if any(_label(row, k) is None for k in keys):
            return False, False
        if threshold is None:
            taken = all(
                _conf(row, k) >= 0.95 and _label(row, k) in {"supported", "unsupported"}
                for k in keys
            )
            predicted = sorted(k for k in keys if _label(row, k) == "unsupported")
        else:
            ps = {k: _p(row, k) for k in keys}
            taken = all(
                p is not None and (p <= threshold or p >= 1 - threshold) for p in ps.values()
            )
            predicted = sorted(k for k, p in ps.items() if p is not None and p >= 1 - threshold)
        return taken, taken and predicted == row["gold"]["unsupported"]

    return decide


def exclusion(params: tuple[float, float] | None) -> Decision:
    def decide(row: Row) -> tuple[bool, bool]:
        keys = [k for k in row["keys"] if k.startswith("item_")]
        if any(_label(row, k) is None for k in keys) or _label(row, "reference_scope") is None:
            return False, False
        if params is None:
            firm = all(
                _conf(row, k) >= 0.99 and _label(row, k) in {"keep", "exclude"} for k in keys
            )
            scope = (
                _label(row, "reference_scope") == "clear" and _conf(row, "reference_scope") >= 0.80
            )
        else:
            item_t, scope_t = params
            firm = all(
                _conf(row, k) >= item_t and _label(row, k) in {"keep", "exclude"} for k in keys
            )
            p = _p(row, "reference_scope")
            scope = p is not None and p >= scope_t
        taken = firm and scope
        keep = [i for i, k in enumerate(keys) if _label(row, k) == "keep"]
        return taken, taken and keep == row["gold"]["keep"]

    return decide


def collection_items(row: Row, threshold: float | None) -> Iterable[tuple[bool, bool, bool]]:
    """Per item: (opportunity, taken, correct)."""
    cut = 0.95 if threshold is None else threshold
    for key in row["keys"]:
        gold = row["gold"][key]
        choice = _label(row, key)
        taken = choice in {"match", "non_match"} and _conf(row, key) >= cut
        yield gold in {"match", "non_match"}, taken, taken and choice == gold


# ------------------------------------------------------------------ scoring
def _opportunity(usage: str, row: Row) -> bool:
    gold = row["gold"]
    return {
        "memory_presence": lambda: gold["absent"],
        "hitl_rejection": lambda: gold["reject"],
        "initiative": lambda: not gold["utility"],
        "consultation": lambda: gold["expected"] != "other",
        "radio": lambda: True,
        "hitl_exclusion": lambda: gold["keep"] is not None,
    }[usage]()


def score(usage: str, rows: Sequence[Row], param: Any) -> dict[str, Any]:
    """Wrong shortcuts, correct shortcuts and coverage of the opportunities."""
    if usage == "collections":
        triples = [t for row in rows for t in collection_items(row, param)]
        opportunities = sum(o for o, _, _ in triples)
        taken = sum(t for _, t, _ in triples)
        correct = sum(c for _, _, c in triples)
    else:
        decide = DECISIONS[usage](param)
        results = [(decide(row), _opportunity(usage, row)) for row in rows]
        opportunities = sum(o for _, o in results)
        taken = sum(t for (t, _), _ in results)
        correct = sum(c for (_, c), _ in results)
    return {
        "judged": len(rows),
        "opportunities": opportunities,
        "shortcuts": taken,
        "wrong": taken - correct,
        "correct": correct,
        "coverage": correct / opportunities if opportunities else None,
    }


DECISIONS: dict[str, Callable[[Any], Decision]] = {
    "memory_presence": memory,
    "hitl_rejection": rejection,
    "initiative": initiative,
    "consultation": consultation,
    "radio": radio,
    "hitl_exclusion": exclusion,
}


def grid(usage: str) -> list[Any]:
    if usage in {"memory_presence", "initiative"}:
        return [round(0.01 * i, 2) for i in range(1, 51)]
    if usage == "hitl_rejection":
        return [round(0.5 + 0.01 * i, 2) for i in range(50)]
    if usage == "radio":
        return [round(0.01 * i, 2) for i in range(1, 31)]
    if usage == "hitl_exclusion":
        return [(t, s) for t in CONFIDENCES for s in (0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99)]
    return list(CONFIDENCES)


def _strictness(usage: str, param: Any) -> float:
    """Larger means stricter (fewer shortcuts), to break ties conservatively."""
    if usage in {"memory_presence", "initiative", "radio"}:
        return -float(param)
    if usage == "hitl_exclusion":
        return float(param[0]) + float(param[1])
    return float(param)


def choose(usage: str, calibration: Sequence[Row], allowed_wrong: int) -> Any:
    best: tuple[float, float, Any] | None = None
    for param in grid(usage):
        result = score(usage, calibration, param)
        if result["wrong"] > allowed_wrong:
            continue
        key = (result["coverage"] or 0.0, _strictness(usage, param), param)
        if best is None or key[:2] > best[:2]:
            best = key
    return None if best is None else best[2]


def _rows(usage: str) -> list[Row]:
    path = OUT / f"rows-{usage}.json"
    return json.loads(path.read_text(encoding="utf-8"))["rows"] if path.exists() else []


def _cost(rows: Sequence[Row]) -> dict[str, Any]:
    latencies = sorted(float(r["latency_ms"]) for r in rows if r.get("latency_ms"))
    return {
        "calls": len(rows),
        "errors": sum(1 for r in rows if r.get("error")),
        "input_tokens": sum(int(r.get("input_tokens") or 0) for r in rows),
        "latency_ms_median": median(latencies) if latencies else None,
        "latency_ms_p95": (
            latencies[min(len(latencies) - 1, int(0.95 * len(latencies)))] if latencies else None
        ),
    }


def flips(current: Sequence[Row], reversed_rows: Sequence[Row]) -> dict[str, Any]:
    """Answers that change when only the option order changes (same state, same repeat)."""
    index = {(r["id"], r["repeat"]): r for r in reversed_rows}
    compared = changed = 0
    for row in current:
        twin = index.get((row["id"], row["repeat"]))
        if twin is None:
            continue
        for key in row["keys"]:
            a, b = _label(row, key), _label(twin, key)
            if a is not None and b is not None:
                compared += 1
                changed += a != b
    return {
        "answers_compared": compared,
        "answers_changed": changed,
        "rate": changed / compared if compared else None,
    }


def evaluate(usage: str) -> dict[str, Any] | None:
    rows = _rows(usage)
    if not rows:
        return None
    by = {
        (v, s): [r for r in rows if r["variant"] == v and r["split"] == s]
        for v in ("current", "current_rev", "candidate")
        for s in ("calibration", "holdout")
    }
    shipped_cal = score(usage, by[("current", "calibration")], None)
    param = choose(usage, by[("candidate", "calibration")], shipped_cal["wrong"])
    shipped = score(usage, by[("current", "holdout")], None)
    reversed_ = score(usage, by[("current_rev", "holdout")], None)
    candidate = score(usage, by[("candidate", "holdout")], param) if param is not None else None
    adopt = (
        candidate is not None
        and candidate["wrong"] <= shipped["wrong"]
        and (candidate["coverage"] or 0.0) >= (shipped["coverage"] or 0.0)
    )
    return {
        "usage": usage,
        "shipped_holdout": shipped,
        "shipped_calibration": shipped_cal,
        "reversed_options_holdout": reversed_,
        "order_flips": flips(
            [r for r in rows if r["variant"] == "current"],
            [r for r in rows if r["variant"] == "current_rev"],
        ),
        "candidate_threshold_from_calibration": param,
        "candidate_holdout": candidate,
        "candidate_calibration": (
            score(usage, by[("candidate", "calibration")], param) if param is not None else None
        ),
        "adopt_candidate": adopt,
        "cost": {
            v: _cost([r for r in rows if r["variant"] == v])
            for v in ("current", "current_rev", "candidate")
        },
    }


def main() -> None:
    report = {}
    for usage in (
        "memory_presence",
        "hitl_rejection",
        "initiative",
        "consultation",
        "radio",
        "collections",
        "hitl_exclusion",
    ):
        result = evaluate(usage)
        if result is None:
            continue
        report[usage] = result
        s, r, c = (
            result["shipped_holdout"],
            result["reversed_options_holdout"],
            result["candidate_holdout"],
        )
        print(
            f"{usage:<16} shipped wrong={s['wrong']} cov={s['coverage']} | reversed wrong={r['wrong']} cov={r['coverage']} "
            f"flips={result['order_flips']['rate']} | candidate@{result['candidate_threshold_from_calibration']} "
            f"wrong={c and c['wrong']} cov={c and c['coverage']} | adopt={result['adopt_candidate']}"
        )
    spend = OUT / "spend.json"
    report["spent_eur"] = json.loads(spend.read_text())["spent_eur"] if spend.exists() else None
    (OUT / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8"
    )
    print(f"spent_eur={report['spent_eur']}")


if __name__ == "__main__":
    main()
