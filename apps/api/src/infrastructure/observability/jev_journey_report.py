"""Conservative OFF/ON comparisons, requiring explicit pairing and quality review."""

import json
from collections import defaultdict
from collections.abc import Callable, Iterable
from math import ceil
from statistics import median
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class JourneySample(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)

    run_id: str = Field(min_length=1, max_length=255)
    pair_id: str | None = Field(default=None, min_length=1, max_length=255)
    environment: str = Field(min_length=1, max_length=255)
    mode: Literal["off", "on", "unknown"] = "unknown"
    duration_ms: float | None = Field(default=None, ge=0)
    first_useful_ms: float | None = Field(default=None, ge=0)
    cost_eur: float | None = Field(default=None, ge=0)
    quality: Literal["pass", "fail", "unreviewed"] = "unreviewed"
    outcome: Literal["completed", "interrupted", "error", "cancelled"]

    @model_validator(mode="after")
    def timing_order(self) -> Self:
        if (
            self.first_useful_ms is not None
            and self.duration_ms is not None
            and self.first_useful_ms > self.duration_ms
        ):
            raise ValueError("First useful result cannot follow completion")
        return self


def samples_from_logs(lines: Iterable[str], *, environment: str) -> list[JourneySample]:
    """Export only the delivery event's allowlisted numbers, never source content."""
    samples = []
    for line in lines:
        try:
            value = json.loads(line[line.index("{") :])
        except ValueError:
            continue
        if not isinstance(value, dict) or value.get("event") != "chat_delivery_completed":
            continue
        samples.append(
            JourneySample.model_validate(
                {
                    "run_id": value.get("run_id"),
                    "environment": environment,
                    "duration_ms": value.get("duration_ms"),
                    "first_useful_ms": value.get("first_useful_ms"),
                    "cost_eur": value.get("cost_eur"),
                    "outcome": "completed",
                }
            )
        )
    return samples


def _distribution(values: list[float]) -> dict[str, float | int | None]:
    ordered = sorted(values)
    return {
        "count": len(values),
        "p50": median(ordered) if ordered else None,
        "p95": ordered[ceil(len(ordered) * 0.95) - 1] if ordered else None,
    }


def _pairs(samples: list[JourneySample]) -> list[tuple[JourneySample, JourneySample]]:
    seen: set[str] = set()
    groups: dict[tuple[str, str], dict[str, JourneySample]] = defaultdict(dict)
    for sample in samples:
        if sample.run_id in seen:
            raise ValueError("duplicate run")
        seen.add(sample.run_id)
        if sample.pair_id is None or sample.mode == "unknown":
            continue
        group = groups[(sample.pair_id, sample.environment)]
        if sample.mode in group:
            raise ValueError("ambiguous pair: assign a separate pair_id to each repetition")
        group[sample.mode] = sample
    return [(group["off"], group["on"]) for group in groups.values() if set(group) == {"off", "on"}]


def compare_journeys(samples: list[JourneySample]) -> dict[str, object]:
    pairs = _pairs(samples)
    qualified = [
        (off, on)
        for off, on in pairs
        if off.quality == on.quality == "pass" and off.outcome == on.outcome == "completed"
    ]
    result: dict[str, object] = {
        "samples": len(samples),
        "paired": len(pairs),
        "qualified_pairs": len(qualified),
        "quality_failures": sum(s.quality == "fail" for s in samples),
        "unreviewed": sum(s.quality == "unreviewed" for s in samples),
        "incomplete": sum(s.outcome != "completed" for s in samples),
        "scope": "Positive savings favor JEV. Finite reviewed pairs, not a quality guarantee.",
    }
    measures: tuple[tuple[str, Callable[[JourneySample], float | None]], ...] = (
        ("duration", lambda s: s.duration_ms),
        ("first_useful", lambda s: s.first_useful_ms),
        ("cost", lambda s: s.cost_eur),
    )
    for label, read in measures:
        unit = "eur" if label == "cost" else "ms"
        result.update(_metric_report(samples, qualified, label, unit, read))
    return result


def _metric_report(
    samples: list[JourneySample],
    pairs: list[tuple[JourneySample, JourneySample]],
    label: str,
    unit: str,
    read: Callable[[JourneySample], float | None],
) -> dict[str, object]:
    """Report one measured quantity, keeping paired savings separate from cohorts."""
    differences = []
    for off, on in pairs:
        before, after = read(off), read(on)
        if before is not None and after is not None:
            differences.append(before - after)
    result: dict[str, object] = {f"{label}_savings_{unit}": _distribution(differences)}
    for mode in ("off", "on"):
        values = [
            value
            for s in samples
            if s.mode == mode and s.outcome == "completed"
            if (value := read(s)) is not None
        ]
        result[f"{mode}_{label}_{unit}"] = _distribution(values)
    return result
