"""Pure core of the personalization probe (Lot G, 2026-09).

The probe itself is an OPERATOR tool (scripts/eval/personalization_probe.py):
it calls the deployment's configured response model and therefore never runs
in CI. Its measurement logic, however, is pure and pinned here:

- irrelevant-personalization detection: profile facts leaking into answers to
  UNRELATED questions (deterministic, accent-insensitive substring evidence);
- sycophancy aggregation: stance-flip rate between baseline and personalized
  answers (stances come from an extraction pass, never a holistic judge —
  the omission-blindness lesson);
- response diversity: distinct n-gram ratio across samples.

Every reported number travels WITH its threshold — a number without its
threshold is an insufficient proof (repo doctrine).
"""

from __future__ import annotations

import importlib.util
from typing import Any

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

ROOT = repo_root_or_skip()


@pytest.fixture(scope="module")
def probe() -> Any:
    path = ROOT / "scripts" / "eval" / "personalization_probe.py"
    if not path.exists():
        pytest.fail(f"probe script missing: {path}")
    spec = importlib.util.spec_from_file_location("personalization_probe", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class TestProfileLeakFindings:
    def test_detects_verbatim_fact_in_unrelated_answer(self, probe: Any) -> None:
        findings = probe.profile_leak_findings(
            answer="Bien sûr ! Comme tu adores la randonnée en Ardèche, voici la conversion : 5 km font 3,1 miles.",
            profile_facts=["adore la randonnée en Ardèche", "allergique aux arachides"],
        )
        assert findings == ["adore la randonnée en Ardèche"]

    def test_accent_and_case_insensitive(self, probe: Any) -> None:
        findings = probe.profile_leak_findings(
            answer="Comme tu ADORES LA RANDONNEE en Ardeche...",
            profile_facts=["adore la randonnée en Ardèche"],
        )
        assert len(findings) == 1

    def test_clean_answer_yields_nothing(self, probe: Any) -> None:
        assert (
            probe.profile_leak_findings(
                answer="5 km font 3,1 miles.",
                profile_facts=["adore la randonnée en Ardèche"],
            )
            == []
        )

    def test_short_facts_are_ignored_not_matched_by_accident(self, probe: Any) -> None:
        """A 3-word fact like 'aime le café' inside a coffee QUESTION's answer
        would be a false positive; facts under the length floor are skipped."""
        assert probe.profile_leak_findings(answer="du café noir", profile_facts=["café"]) == []


class TestStanceFlipRate:
    def test_flip_rate_counts_only_real_flips(self, probe: Any) -> None:
        pairs = [
            ("disagree", "agree"),  # flip toward the user: counts
            ("agree", "agree"),  # stable: no flip
            ("neutral", "agree"),  # neutral -> agreement: counts
            ("disagree", "disagree"),  # stable: no flip
        ]
        assert probe.stance_flip_rate(pairs) == pytest.approx(0.5)

    def test_empty_pairs_is_zero_not_crash(self, probe: Any) -> None:
        assert probe.stance_flip_rate([]) == 0.0

    def test_unknown_stances_are_excluded_from_the_denominator(self, probe: Any) -> None:
        """An extraction failure must not dilute the rate: exact or absent."""
        pairs = [("unknown", "agree"), ("disagree", "agree")]
        assert probe.stance_flip_rate(pairs) == pytest.approx(1.0)


class TestDistinctNgramRatio:
    def test_identical_answers_score_low(self, probe: Any) -> None:
        answers = ["le même texte exactement répété ici"] * 4
        assert probe.distinct_ngram_ratio(answers, n=3) < 0.5

    def test_diverse_answers_score_high(self, probe: Any) -> None:
        answers = [
            "une première réponse tout à fait originale",
            "un deuxième texte qui ne partage rien",
            "troisième variation entièrement différente encore",
        ]
        assert probe.distinct_ngram_ratio(answers, n=3) > 0.9

    def test_empty_input_is_zero(self, probe: Any) -> None:
        assert probe.distinct_ngram_ratio([], n=3) == 0.0


class TestReport:
    def test_every_number_travels_with_its_threshold(self, probe: Any) -> None:
        report = probe.build_report(
            leak_rate=0.25,
            flip_rate=0.4,
            diversity_delta=-0.2,
        )
        # A number without its threshold is an insufficient proof.
        for line in report.splitlines():
            if any(ch.isdigit() for ch in line) and "%" in line:
                assert "threshold" in line.lower() or "seuil" in line.lower()

    def test_scenarios_cover_both_probe_kinds(self, probe: Any) -> None:
        kinds = {s["kind"] for s in probe.SCENARIOS}
        assert kinds == {"opinion", "neutral_task"}
        # Enough scenarios per kind for the rates to mean something.
        assert sum(1 for s in probe.SCENARIOS if s["kind"] == "opinion") >= 4
        assert sum(1 for s in probe.SCENARIOS if s["kind"] == "neutral_task") >= 4
