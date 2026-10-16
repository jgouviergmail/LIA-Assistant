"""The pilot changes work only with a relevant present gap and qualified history."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.domains.psyche.efficacy_contracts import EfficacyPolicy, EfficacyProfile

pytestmark = pytest.mark.unit


def _profile(
    *,
    successes: int = 0,
    failures: int = 0,
    unhelpful: int = 0,
    helpful: int = 0,
    partial: int = 0,
    unknown: int = 0,
    enabled: bool = True,
) -> EfficacyProfile:
    from src.domains.psyche.efficacy_contracts import EfficacyEpisodeView, EfficacyObservation
    from src.domains.psyche.efficacy_scoring import build_profile

    episodes = []
    for index, (verdict, feedback) in enumerate(
        [("success", None)] * successes
        + [("failure", None)] * failures
        + [("unknown", "unhelpful")] * unhelpful
        + [("unknown", "helpful")] * helpful
        + [("partial", None)] * partial
        + [("unknown", None)] * unknown
    ):
        episodes.append(
            EfficacyEpisodeView.model_validate(
                {
                    "run_id": f"run-{index}",
                    "message_id": uuid4(),
                    "terminal_at": datetime(2026, 10, 16, tzinfo=UTC),
                    "feedback": feedback,
                    "observations": (
                        EfficacyObservation.model_validate(
                            {
                                "domain": "technical",
                                "verdict": verdict,
                                "reason": "insufficient_evidence",
                            }
                        ),
                    ),
                }
            )
        )
    return build_profile(
        episodes, now=datetime(2026, 10, 16, tzinfo=UTC), influence_enabled=enabled
    )


def _choose(
    profile: EfficacyProfile,
    *,
    current_gap: bool = False,
    ambiguous: bool = False,
    can_verify: bool = True,
    budget_available: bool = True,
) -> EfficacyPolicy:
    from src.domains.psyche.efficacy_policy import choose_policy

    return choose_policy(
        profile,
        ("technical",),
        current_gap=current_gap,
        ambiguous=ambiguous,
        can_verify=can_verify,
        budget_available=budget_available,
    )


def test_cold_start_and_four_failures_do_not_create_a_pilot_intervention() -> None:
    assert _choose(_profile(), current_gap=True).action == "none"
    assert _choose(_profile(failures=4), current_gap=True).action == "none"


def test_weak_history_with_a_present_gap_selects_available_verification() -> None:
    policy = _choose(_profile(failures=5), current_gap=True)
    assert policy.action == "verify"
    assert policy.domains == ("technical",)


@pytest.mark.parametrize(
    "can_verify,budget_available", [(False, True), (True, False), (False, False)]
)
def test_unavailable_verification_has_an_explicit_limit(
    can_verify: bool, budget_available: bool
) -> None:
    assert (
        _choose(
            _profile(failures=5),
            current_gap=True,
            can_verify=can_verify,
            budget_available=budget_available,
        ).action
        == "state_limit"
    )


def test_qualified_poor_utility_can_clarify_an_existing_ambiguity_only() -> None:
    profile = _profile(unhelpful=5)
    assert _choose(profile, ambiguous=True).action == "clarify"
    assert _choose(profile).action == "none"
    assert _choose(profile, current_gap=True).action == "none"


def test_utility_feedback_never_establishes_factual_success() -> None:
    assert _choose(_profile(helpful=6, failures=5), current_gap=True).action == "verify"
    assert _choose(_profile(unhelpful=6, successes=5), current_gap=True).action == "none"


def test_present_complete_evidence_is_not_undermined_by_weak_history() -> None:
    assert _choose(_profile(failures=20)).action == "none"


def test_pilot_off_ignores_history_without_changing_profile() -> None:
    assert (
        _choose(
            _profile(failures=20, unhelpful=20, enabled=False), current_gap=True, ambiguous=True
        ).action
        == "none"
    )


def test_other_domain_experience_cannot_affect_this_question() -> None:
    from src.domains.psyche.efficacy_policy import choose_policy

    assert (
        choose_policy(
            _profile(failures=8),
            ("social",),
            current_gap=True,
            ambiguous=False,
            can_verify=True,
            budget_available=True,
        ).action
        == "none"
    )


def test_equal_history_is_not_classified_as_poor() -> None:
    assert _choose(_profile(failures=3, successes=3), current_gap=True).action == "none"


def test_rendered_policy_is_bounded_and_contains_no_private_scores() -> None:
    from src.domains.psyche.efficacy_policy import render_policy

    for policy in (
        _choose(_profile()),
        _choose(_profile(failures=5), current_gap=True),
        _choose(_profile(unhelpful=5), ambiguous=True),
        _choose(_profile(failures=5), current_gap=True, can_verify=False),
    ):
        rendered = render_policy(policy)
        assert len(rendered.encode("utf-8")) <= 360
        assert "0.14" not in rendered
        assert "run-" not in rendered


def test_longest_policy_stays_within_its_actual_token_budget() -> None:
    import tiktoken

    from src.domains.psyche.efficacy_contracts import EfficacyPolicy
    from src.domains.psyche.efficacy_policy import render_policy

    policy = EfficacyPolicy.model_validate(
        {
            "action": "state_limit",
            "domains": ["emotional_support", "organization"],
            "reason": "verification_unavailable",
        }
    )
    assert len(tiktoken.get_encoding("cl100k_base").encode(render_policy(policy))) <= 120


def test_repeated_partial_coverage_can_request_a_bounded_check_without_fake_failure() -> None:
    profile = _profile(partial=5)
    domain = next(entry for entry in profile.domains if entry.domain == "technical")
    assert domain.result_count == 0
    assert domain.result_score is None
    assert _choose(profile, current_gap=True).action == "verify"
    assert _choose(profile).action == "none"
    assert _choose(_profile(partial=5, enabled=False), current_gap=True).action == "none"


@pytest.mark.parametrize(
    "partial,unknown,successes,expected",
    [(4, 0, 0, "none"), (0, 5, 0, "none"), (5, 0, 5, "none"), (5, 0, 4, "verify")],
)
def test_partial_history_requires_five_observations_and_more_partial_than_complete(
    partial: int, unknown: int, successes: int, expected: str
) -> None:
    assert (
        _choose(
            _profile(partial=partial, unknown=unknown, successes=successes), current_gap=True
        ).action
        == expected
    )


def test_partial_history_cannot_request_an_unavailable_check() -> None:
    profile = _profile(partial=5)
    assert _choose(profile, current_gap=True, can_verify=False).action == "state_limit"
    assert _choose(profile, current_gap=True, budget_available=False).action == "state_limit"
