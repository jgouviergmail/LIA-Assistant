"""The case shape shared by the five decision corpora."""

from dataclasses import dataclass, field
from typing import Literal

Decision = Literal["d1", "d2", "d3", "d4", "d5"]
Split = Literal["calibration", "independent"]
SPLITS: tuple[Split, ...] = ("calibration", "independent")


@dataclass(frozen=True)
class Case:
    """One judged input and what an independent author accepts as correct.

    Single-label decisions (d1, d2, d5) read ``gold``/``accepted``/``lenient``;
    multi-label decisions (d3 relevance, d4) read ``required``/``optional``;
    d3 also reads ``gold`` as the expected primary domain.

    Attributes:
        id: Stable identifier.
        decision: Decision point.
        split: ``calibration`` (questions may be tuned on it) or ``independent``.
        language: Language of the user text.
        family: Edge-case family, for per-family reporting.
        state: What every engine sees, verbatim.
        gold: The designated answer (per-class metrics, confusion matrix).
        accepted: Every answer counted correct in strict scoring (contains ``gold``).
        lenient: Extra answers counted correct in lenient scoring (ancestors).
        required: Multi-label: labels that must be selected.
        optional: Multi-label: labels that may be selected without penalty.
    """

    id: str
    decision: Decision
    split: Split
    language: str
    family: str
    state: dict[str, object]
    gold: str | None = None
    accepted: frozenset[str] = frozenset()
    lenient: frozenset[str] = frozenset()
    required: frozenset[str] = frozenset()
    optional: frozenset[str] = frozenset()
    meta: dict[str, object] = field(default_factory=dict)


def single(
    decision: Decision,
    split: Split,
    index: int,
    language: str,
    family: str,
    state: dict[str, object],
    gold: str,
    also: tuple[str, ...] = (),
    lenient: tuple[str, ...] = (),
    **meta: object,
) -> Case:
    """Build a single-label case whose accepted set is ``gold`` plus ``also``."""
    return Case(
        id=f"{decision}-{split[:3]}-{index:03d}",
        decision=decision,
        split=split,
        language=language,
        family=family,
        state=state,
        gold=gold,
        accepted=frozenset((gold, *also)),
        lenient=frozenset(lenient),
        meta=dict(meta),
    )


def validate(cases: tuple[Case, ...], vocabulary: frozenset[str]) -> None:
    """Refuse a corpus whose labels fall outside the decision's vocabulary or whose ids repeat."""
    ids = [case.id for case in cases]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise ValueError(f"duplicate case ids: {sorted(duplicates)}")
    for case in cases:
        labels = case.accepted | case.lenient | case.required | case.optional
        unknown = labels - vocabulary
        if unknown:
            raise ValueError(f"{case.id}: labels outside the vocabulary: {sorted(unknown)}")
        if case.accepted and case.gold not in case.accepted:
            raise ValueError(f"{case.id}: gold not accepted")
