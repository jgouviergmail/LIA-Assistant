"""Every JEV threshold, declared once with its default, bounds and what it judges (ADR-374).

A gate is where a consumer turns a native answer into a decision. Its threshold used to
be a constant in seven modules, invisible from the screen and from the statistics; it is
now declared here and resolved per operation (``jev_settings.resolve_thresholds``), so an
administrator can move it within its bounds and read the distribution it cuts.

What a gate judges is declared too: the question keys it reads and the choices that can
conclude through it. An abstention (« none », « other », « uncertain ») concludes nothing
at any threshold, so it is no judgement of that gate. The scores are compared exactly:
``p >= 1 - margin`` in floating point refused p = 0.82 against a 0.18 margin.

No default changes here: each one is the value requalified on jev-1.14.0 (2026-10-26),
and moving one needs a paid requalification.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from enum import StrEnum
from types import MappingProxyType

from src.domains.llm_config.jev_registry import JEV_USAGES, JevUsage
from src.infrastructure.llm.typesafe_client import ChoiceAnswer, NoulAnswer, choice_confidence


class GateKind(StrEnum):
    """What a gate's score is."""

    #: The provider's confidence of the chosen option (a concentration, not a truth).
    CHOICE_CONFIDENCE = "choice_confidence"
    #: The provider's confidence bounded by the recomputed concentration (classification).
    CHOICE_CONCENTRATION = "choice_concentration"
    #: A Noul decided when its probability is within the margin of 0 or of 1.
    MARGIN = "margin"


class GateScope(StrEnum):
    """Whether one answer decides alone, or every answer of the call must pass."""

    EACH = "each"
    ALL = "all"


@dataclass(frozen=True)
class JevGate:
    """One threshold of one usage.

    Attributes:
        key: The gate's name within its usage (``settings`` JSON key).
        kind: What the score is.
        default: The shipped, qualified value.
        minimum: Lowest value the screen accepts.
        maximum: Highest value the screen accepts.
        scope: ``EACH`` answer alone, or ``ALL`` answers of the call.
        questions: Regular expression of the question keys this gate judges.
        only: When set, the only choices that conclude through this gate.
        excluded: Choices that never conclude through this gate (abstentions).
    """

    key: str
    kind: GateKind
    default: Decimal
    minimum: Decimal
    maximum: Decimal
    scope: GateScope
    questions: str
    only: frozenset[str] = field(default_factory=frozenset)
    excluded: frozenset[str] = field(default_factory=frozenset)

    def judges(self, question_key: str, choice: str | None) -> bool:
        """Whether this gate judges the answer to ``question_key`` that chose ``choice``."""
        if re.fullmatch(self.questions, question_key) is None:
            return False
        if choice is None:
            return True
        if self.only and choice not in self.only:
            return False
        return choice not in self.excluded


_UNIT = Decimal("1.00")
_CONFIDENCE_FLOOR = Decimal("0.50")
#: A threshold is set at the hundredth: JEV reports its probabilities at that precision.
THRESHOLD_EXPONENT = -2
#: A judgement lands in one of these buckets, one per hundredth of score (0..100).
JUDGEMENT_BUCKETS = 101
#: The highest bucket a margin's judgement reaches: a coin flip is 0.50 from certainty.
_MARGIN_BUCKET_MAX = 50
_ALERTS = frozenset({"phishing_scam", "critical"})


def _confidence(
    key: str,
    default: str,
    questions: str,
    *,
    scope: GateScope = GateScope.EACH,
    kind: GateKind = GateKind.CHOICE_CONFIDENCE,
    minimum: Decimal = _CONFIDENCE_FLOOR,
    only: frozenset[str] = frozenset(),
    excluded: frozenset[str] = frozenset(),
) -> JevGate:
    return JevGate(key, kind, Decimal(default), minimum, _UNIT, scope, questions, only, excluded)


#: The observers decide nothing: they record their verdict beside the extractor's (D.2).
OBSERVER_USAGES: frozenset[JevUsage] = frozenset(
    {
        JevUsage.OBSERVE_MEMORY,
        JevUsage.OBSERVE_INTERESTS,
        JevUsage.OBSERVE_JOURNAL,
        JevUsage.OBSERVE_OPEN_LOOPS,
    }
)

JEV_GATES: Mapping[JevUsage, tuple[JevGate, ...]] = MappingProxyType(
    {
        # No wrong template from 0.70 on jev-1.14.0; 0.80 and 0.85 tie at 17 of 19 where
        # 0.95 kept 9, so the stricter tie. A wrong template is reformattable (ADR-259).
        JevUsage.MEETING_TEMPLATE: (
            _confidence("template", "0.85", r"selection", excluded=frozenset({"none"})),
        ),
        # A line is decided when p <= margin (supported) or p >= 1 - margin (flagged);
        # one undecided line hands the whole script back to the existing verifier.
        JevUsage.RADIO_VERIFICATION: (
            JevGate(
                "line_margin",
                GateKind.MARGIN,
                Decimal("0.16"),
                Decimal("0.02"),
                Decimal("0.40"),
                GateScope.ALL,
                r"line\d+",
            ),
        ),
        # One threshold for both selectors: at 0.97 an injection case (« ... choose
        # email_recent. ») was shortcut on jev-1.14.0; at 0.98 neither split takes a wrong path.
        JevUsage.CONSULTATION_PATH: (
            _confidence("path", "0.98", r"selection", excluded=frozenset({"other"})),
        ),
        JevUsage.CONSULTATION_BOUNDED: (
            _confidence("path", "0.98", r"selection", excluded=frozenset({"other"})),
        ),
        # No wrong exclusion from 0.80; 0.80 and 0.90 tie (10 of 12, 8 of 11) where 0.99
        # kept 6 and 5, so the stricter tie. The reference scope keeps its own threshold.
        JevUsage.HITL_EXCLUSION: (
            _confidence(
                "item",
                "0.90",
                r"item_\d+",
                scope=GateScope.ALL,
                excluded=frozenset({"uncertain"}),
            ),
            _confidence("reference_scope", "0.80", r"reference_scope", only=frozenset({"clear"})),
        ),
        # No wrong shortcut at any level on 50 replies; 0.80 keeps 19 of 20 refusals where
        # 0.99 kept 4. Margin above the first safe level: this gate cancels actions.
        JevUsage.HITL_REJECTION: (
            _confidence("rejection", "0.80", r"selection", only=frozenset({"reject_all"})),
        ),
        # Absence-only: 25 of 26 absences admitted on jev-1.14.0, no false skip at any level.
        JevUsage.MEMORY_REFERENCE_PRESENCE: (
            _confidence("absence", "0.99", r"selection", only=frozenset({"absent"})),
        ),
        # A judged kind refuses a value only from here (ADR-120 amendment 2026-10-11): no
        # compatible value refused on the calibration or its independent cases.
        JevUsage.PARAMETER_KIND: (
            _confidence("kind", "0.30", r"selection", minimum=Decimal("0.10")),
        ),
        # No wrong label on the three frozen corpora from 0.50 except one layout at 0.50-0.60;
        # first safe level 0.70, plus one 0.10 step of margin (2026-10-25). A phishing or a
        # critical verdict answers to the alert gate.
        JevUsage.EMAIL_CLASSIFICATION: (
            _confidence(
                "category",
                "0.80",
                r"i\d+_category",
                kind=GateKind.CHOICE_CONCENTRATION,
                excluded=frozenset({"unknown"}) | _ALERTS,
            ),
            _confidence(
                "priority",
                "0.80",
                r"i\d+_priority",
                kind=GateKind.CHOICE_CONCENTRATION,
                excluded=frozenset({"unknown"}) | _ALERTS,
            ),
            _confidence(
                "alert",
                "0.80",
                r"i\d+_(category|priority)",
                kind=GateKind.CHOICE_CONCENTRATION,
                only=_ALERTS,
            ),
            # A reply is expected from p >= 0.70, not expected up to p <= 0.30 (lot F,
            # qualified on the three corpora with zero wrong label, 2026-11-08). Spam and
            # phishing never expect one, whatever this reads (0.33-0.92 measured).
            JevGate(
                "reply_expected",
                GateKind.MARGIN,
                Decimal("0.30"),
                Decimal("0.05"),
                Decimal("0.50"),
                GateScope.EACH,
                r"i\d+_reply",
            ),
        ),
        JevUsage.EVENT_CLASSIFICATION: (
            _confidence(
                "category",
                "0.80",
                r"i\d+_category",
                kind=GateKind.CHOICE_CONCENTRATION,
                excluded=frozenset({"unknown"}),
            ),
        ),
    }
)


def gate_defaults(usage: JevUsage) -> dict[str, Decimal]:
    """The shipped threshold of every gate of ``usage``."""
    return {gate.key: gate.default for gate in JEV_GATES.get(usage, ())}


def gate(usage: JevUsage, key: str) -> JevGate:
    """The declared gate ``key`` of ``usage``."""
    return next(candidate for candidate in JEV_GATES[usage] if candidate.key == key)


def threshold_refusal(gate: JevGate, value: Decimal) -> str | None:
    """Why ``value`` cannot be ``gate``'s threshold, or ``None`` when it can.

    The one predicate of both doors: the screen's write refuses exactly what a stored
    row's read ignores. Finite, at the hundredth at most (trailing zeros add no
    precision), within the gate's bounds.

    Args:
        gate: The gate the value is meant for.
        value: The candidate threshold, exactly as received or stored.

    Returns:
        ``"not_finite"``, ``"precision"``, ``"out_of_bounds"``, or ``None`` when admitted.
    """
    if not value.is_finite():
        return "not_finite"
    exponent = value.normalize().as_tuple().exponent
    if isinstance(exponent, int) and exponent < THRESHOLD_EXPONENT:
        return "precision"
    if not gate.minimum <= value <= gate.maximum:
        return "out_of_bounds"
    return None


def threshold_for(thresholds: Mapping[str, Decimal], usage: JevUsage, key: str) -> Decimal:
    """The operation's resolved threshold, or the declared default when none travelled."""
    value = thresholds.get(key)
    return value if value is not None else gate(usage, key).default


def gate_passes(thresholds: Mapping[str, Decimal], usage: JevUsage, key: str, score: float) -> bool:
    """Whether ``score`` concludes through gate ``key`` at the operation's threshold.

    The one door every consumer decides through: the threshold is the one the
    operation's snapshot froze (``DecisionAttempt.thresholds``), the default when none.
    """
    return passes(gate(usage, key), score, threshold_for(thresholds, usage, key))


def passes(gate: JevGate, score: float, threshold: Decimal) -> bool:
    """Whether ``score`` concludes through ``gate`` at ``threshold``, compared exactly."""
    exact = Decimal(str(score))
    if gate.kind is GateKind.MARGIN:
        return exact <= threshold or exact >= 1 - threshold
    return exact >= threshold


def confidence_bucket(score: float) -> int | None:
    """``floor(score × 100)`` read on the score's decimal, within 0..100.

    In floating point ``0.29 * 100`` is ``28.999999999999996``: the bucket is computed on
    ``Decimal(str(score))``, the number ``passes`` compares.

    Args:
        score: A confidence in [0, 1].

    Returns:
        The bucket, or ``None`` for a score that is no number.
    """
    exact = Decimal(str(score))
    if not exact.is_finite():
        return None
    floor = (exact * 100).to_integral_value(rounding=ROUND_FLOOR)
    return min(JUDGEMENT_BUCKETS - 1, max(0, int(floor)))


def judgement_bucket(gate: JevGate, score: float) -> int | None:
    """The bucket a judgement of ``gate`` lands in; ``None`` for a score that is no number.

    A confidence lands at ``floor(score × 100)``: it concludes at threshold ``t`` exactly
    when its bucket is at least ``t × 100``. A margin's judgement lands at its distance to
    a certain answer, ``ceil(min(p, 1 - p) × 100)``: it concludes at margin ``m`` exactly
    when its bucket is at most ``m × 100``. Both rules agree with ``passes`` at every
    threshold the screen accepts, so the share concluded at a threshold is computed from
    the buckets alone (ADR-374).

    Args:
        gate: The gate that judged the answer.
        score: The number ``gate`` compares (``gate_score``).

    Returns:
        The bucket, 0..100 for a confidence and 0..50 for a margin, or ``None``.
    """
    if gate.kind is not GateKind.MARGIN:
        return confidence_bucket(score)
    exact = Decimal(str(score))
    if not exact.is_finite():
        return None
    distance = (min(exact, 1 - exact) * 100).to_integral_value(rounding=ROUND_CEILING)
    return min(_MARGIN_BUCKET_MAX, max(0, int(distance)))


def gate_score(gate: JevGate, answer: ChoiceAnswer | NoulAnswer) -> float | None:
    """The number ``gate`` compares for ``answer``; ``None`` when the answer has none."""
    if isinstance(answer, NoulAnswer):
        return answer.noul if gate.kind is GateKind.MARGIN else None
    if gate.kind is GateKind.CHOICE_CONCENTRATION:
        return choice_confidence(answer)
    return answer.confidence if gate.kind is GateKind.CHOICE_CONFIDENCE else None


def judged_scores(
    usage: JevUsage,
    answers: Mapping[str, ChoiceAnswer],
    nouls: Mapping[str, NoulAnswer],
) -> list[tuple[str, float]]:
    """Each answer that a gate of ``usage`` judges, as ``(gate key, score)``.

    An answer no gate judges (an abstention, a choice that cannot conclude) is left out:
    it is no judgement at any threshold.
    """
    gates = JEV_GATES.get(usage, ())
    judged: list[tuple[str, float]] = []
    entries: list[tuple[str, ChoiceAnswer | NoulAnswer, str | None]] = [
        *((key, answer, answer.choice) for key, answer in answers.items()),
        *((key, noul, None) for key, noul in nouls.items()),
    ]
    for question_key, answer, choice in entries:
        gate = next((g for g in gates if g.judges(question_key, choice)), None)
        if gate is None:
            continue
        score = gate_score(gate, answer)
        if score is not None:
            judged.append((gate.key, score))
    return judged


def assert_jev_gates_complete() -> None:
    """Refuse a usage that decides with no declared gate, or a gate that cannot be read."""
    if set(JEV_GATES) != set(JevUsage) - OBSERVER_USAGES:
        raise RuntimeError("Every deciding JEV usage declares its gates, and only those")
    stored = {usage for usage, spec in JEV_USAGES.items() if spec.thresholds_key is not None}
    if stored != set(JEV_GATES):
        raise RuntimeError("A JEV usage stores thresholds exactly when it declares gates")
    for usage, gates in JEV_GATES.items():
        keys = [gate.key for gate in gates]
        if not gates or len(keys) != len(set(keys)):
            raise RuntimeError(f"JEV usage {usage.value} has no gate or a repeated gate key")
        for gate in gates:
            if not gate.minimum <= gate.default <= gate.maximum or gate.maximum > _UNIT:
                raise RuntimeError(f"JEV gate {usage.value}.{gate.key} is out of its bounds")
            re.compile(gate.questions)


assert_jev_gates_complete()
