"""Every JEV threshold is declared once, with its default, bounds and what it judges (ADR-374)."""

from decimal import Decimal

import pytest

from src.domains.llm_config.jev_gates import (
    JEV_GATES,
    OBSERVER_USAGES,
    GateKind,
    GateScope,
    assert_jev_gates_complete,
    confidence_bucket,
    gate,
    gate_defaults,
    judged_scores,
    judgement_bucket,
    passes,
    threshold_refusal,
)
from src.domains.llm_config.jev_registry import JevUsage
from src.infrastructure.llm.typesafe_client import ChoiceAnswer, NoulAnswer, choice_confidence

pytestmark = pytest.mark.unit

# The values shipped before thresholds became settings (requalified on jev-1.14.0,
# 2026-10-26), and the reply margin qualified with its question (lot F, 2026-11-08). A
# default changes only with a paid requalification.
SHIPPED = {
    JevUsage.MEETING_TEMPLATE: {"template": "0.85"},
    JevUsage.RADIO_VERIFICATION: {"line_margin": "0.16"},
    JevUsage.CONSULTATION_PATH: {"path": "0.98"},
    JevUsage.CONSULTATION_BOUNDED: {"path": "0.98"},
    JevUsage.HITL_EXCLUSION: {"item": "0.90", "reference_scope": "0.80"},
    JevUsage.HITL_REJECTION: {"rejection": "0.80"},
    JevUsage.MEMORY_REFERENCE_PRESENCE: {"absence": "0.99"},
    JevUsage.PARAMETER_KIND: {"kind": "0.30"},
    JevUsage.EMAIL_CLASSIFICATION: {
        "category": "0.80",
        "priority": "0.80",
        "alert": "0.80",
        "reply_expected": "0.30",
    },
    JevUsage.EVENT_CLASSIFICATION: {"category": "0.80"},
}


def _choice(choice: str, confidence: float, options: tuple[str, ...]) -> ChoiceAnswer:
    rest = (1 - confidence) / (len(options) - 1)
    return ChoiceAnswer(
        type="choice",
        choice=choice,
        confidence=confidence,
        probabilities={option: confidence if option == choice else rest for option in options},
    )


def test_defaults_equal_shipped_values() -> None:
    declared = {usage: gate_defaults(usage) for usage in JEV_GATES}
    assert declared == {
        usage: {key: Decimal(value) for key, value in gates.items()}
        for usage, gates in SHIPPED.items()
    }


def test_bounds_hold_the_default_and_are_published() -> None:
    for usage, gates in JEV_GATES.items():
        for declared in gates:
            assert declared.minimum <= declared.default <= declared.maximum, (usage, declared.key)
    by_key = {(u, g.key): g for u, gates in JEV_GATES.items() for g in gates}
    assert (
        by_key[(JevUsage.PARAMETER_KIND, "kind")].minimum,
        by_key[(JevUsage.PARAMETER_KIND, "kind")].maximum,
    ) == (Decimal("0.10"), Decimal("1.00"))
    radio = by_key[(JevUsage.RADIO_VERIFICATION, "line_margin")]
    assert (radio.kind, radio.scope, radio.minimum, radio.maximum) == (
        GateKind.MARGIN,
        GateScope.ALL,
        Decimal("0.02"),
        Decimal("0.40"),
    )
    assert by_key[(JevUsage.HITL_EXCLUSION, "item")].scope is GateScope.ALL
    # A reply is expected from p >= 0.70 and not expected up to p <= 0.30: a margin.
    reply = by_key[(JevUsage.EMAIL_CLASSIFICATION, "reply_expected")]
    assert (reply.kind, reply.scope, reply.minimum, reply.maximum) == (
        GateKind.MARGIN,
        GateScope.EACH,
        Decimal("0.05"),
        Decimal("0.50"),
    )
    assert reply.judges("i3_reply", None) and not reply.judges("i3_priority", None)


def test_a_margin_compares_exactly() -> None:
    radio = next(iter(JEV_GATES[JevUsage.RADIO_VERIFICATION]))
    # In floating point 0.82 >= 1 - 0.18 is False (measured 2026-11-06).
    assert 0.82 < 1 - 0.18
    assert passes(radio, 0.82, Decimal("0.18"))
    assert passes(radio, 0.18, Decimal("0.18"))
    assert not passes(radio, 0.5, Decimal("0.18"))
    assert not passes(radio, 0.19, Decimal("0.18"))


def test_a_confidence_threshold_is_inclusive_and_exact() -> None:
    gate = next(iter(JEV_GATES[JevUsage.MEETING_TEMPLATE]))
    assert passes(gate, 0.85, Decimal("0.85"))
    assert not passes(gate, 0.8499999999999999, Decimal("0.85"))


@pytest.mark.parametrize(
    ("value", "refusal"),
    [
        (Decimal("0.80"), None),
        (Decimal("0.8000"), None),
        (Decimal("1"), None),
        (Decimal("0.805"), "precision"),
        (Decimal("0.49"), "out_of_bounds"),
        (Decimal("1.01"), "out_of_bounds"),
        (Decimal("NaN"), "not_finite"),
        (Decimal("Infinity"), "not_finite"),
    ],
)
def test_one_predicate_admits_a_threshold_for_both_doors(
    value: Decimal, refusal: str | None
) -> None:
    """The screen's write and a stored row's read refuse exactly the same values."""
    assert threshold_refusal(gate(JevUsage.EMAIL_CLASSIFICATION, "priority"), value) == refusal


@pytest.mark.parametrize(
    ("usage", "key", "score", "bucket"),
    [
        (JevUsage.EMAIL_CLASSIFICATION, "priority", 0.29, 29),
        (JevUsage.EMAIL_CLASSIFICATION, "priority", 1.0, 100),
        (JevUsage.EMAIL_CLASSIFICATION, "priority", 0.0, 0),
        (JevUsage.EMAIL_CLASSIFICATION, "priority", 0.999, 99),
        # A margin's judgement lands at its distance to a certain answer, rounded up.
        (JevUsage.RADIO_VERIFICATION, "line_margin", 0.0, 0),
        (JevUsage.RADIO_VERIFICATION, "line_margin", 1.0, 0),
        (JevUsage.RADIO_VERIFICATION, "line_margin", 0.84, 16),
        (JevUsage.RADIO_VERIFICATION, "line_margin", 0.155, 16),
        (JevUsage.RADIO_VERIFICATION, "line_margin", 0.5, 50),
        (JevUsage.EMAIL_CLASSIFICATION, "priority", float("nan"), None),
    ],
)
def test_a_judgement_lands_in_its_exact_bucket(
    usage: JevUsage, key: str, score: float, bucket: int | None
) -> None:
    assert judgement_bucket(gate(usage, key), score) == bucket


def test_a_confidence_bucket_is_the_exact_floor_of_its_decimal() -> None:
    """In floating point 0.29 * 100 is 28.999999999999996: the bucket reads the decimal."""
    assert 0.29 * 100 < 29
    assert [confidence_bucket(s) for s in (0.29, 0.57, 1.0, 0.0)] == [29, 57, 100, 0]
    assert confidence_bucket(float("inf")) is None


def test_a_bucket_concludes_exactly_when_its_score_passes() -> None:
    """The share concluded at a threshold is computed from buckets alone, exactly.

    The screen reads the rule « a confidence concludes from bucket t × 100 up, a margin
    up to bucket m × 100 »; it must agree with ``passes`` at every threshold it offers,
    for scores on the hundredth and between them.
    """
    scores = sorted(
        {i / 1000 for i in range(1001)}
        | {i / 100 + delta for i in range(101) for delta in (-1e-9, 1e-9)}
        | {0.8499999999999999, 0.82, 0.18, 0.155, 0.845}
    )
    scores = [s for s in scores if 0.0 <= s <= 1.0]
    for gates in JEV_GATES.values():
        for candidate in gates:
            low, high = int(candidate.minimum * 100), int(candidate.maximum * 100)
            for hundredths in range(low, high + 1):
                threshold = Decimal(hundredths) / 100
                for score in scores:
                    bucket = judgement_bucket(candidate, score)
                    assert bucket is not None
                    concludes = (
                        bucket <= hundredths
                        if candidate.kind is GateKind.MARGIN
                        else bucket >= hundredths
                    )
                    assert concludes == passes(candidate, score, threshold), (
                        candidate.key,
                        score,
                        threshold,
                    )


def test_registry_complete_at_boot() -> None:
    assert_jev_gates_complete()
    assert set(JEV_GATES) == set(JevUsage) - OBSERVER_USAGES
    for gates in JEV_GATES.values():
        keys = [gate.key for gate in gates]
        assert len(keys) == len(set(keys))


def test_each_answer_is_filed_under_the_gate_that_judges_it() -> None:
    category = ("unknown", "professional", "personal", "spam", "phishing_scam")
    priority = ("unknown", "normal", "urgent", "critical")
    answers = {
        "i0_category": _choice("professional", 0.9, category),
        "i0_priority": _choice("critical", 0.95, priority),
        "i1_category": _choice("phishing_scam", 0.7, category),
        "i1_priority": _choice("unknown", 1.0, priority),
    }
    scores = judged_scores(JevUsage.EMAIL_CLASSIFICATION, answers, {})
    # The classification judges the provider's confidence bounded by the concentration.
    expected = [
        ("category", choice_confidence(answers["i0_category"])),
        ("alert", choice_confidence(answers["i0_priority"])),
        ("alert", choice_confidence(answers["i1_category"])),
    ]
    assert sorted(scores) == sorted(expected)
    assert expected[0][1] < 0.9  # bounded: n=5, p=0.9 gives a 0.875 concentration


def test_an_answer_that_cannot_conclude_is_not_a_judgement() -> None:
    options = ("absent", "preserve")
    assert (
        judged_scores(
            JevUsage.MEMORY_REFERENCE_PRESENCE, {"selection": _choice("preserve", 1.0, options)}, {}
        )
        == []
    )
    assert judged_scores(
        JevUsage.MEMORY_REFERENCE_PRESENCE, {"selection": _choice("absent", 0.99, options)}, {}
    ) == [("absence", 0.99)]
    nouls = {"line0": NoulAnswer(type="noul", noul=0.9), "line1": NoulAnswer(type="noul", noul=0.1)}
    assert sorted(judged_scores(JevUsage.RADIO_VERIFICATION, {}, nouls)) == [
        ("line_margin", 0.1),
        ("line_margin", 0.9),
    ]
