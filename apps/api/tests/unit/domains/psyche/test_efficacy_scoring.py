"""Evidence aggregation behavior; legacy neutral scores are not observations."""

from collections.abc import Sequence
from datetime import UTC, datetime

import pytest

from src.domains.psyche.efficacy_contracts import (
    EfficacyDomainProfile,
    EfficacyEpisodeView,
    EfficacyProfile,
)

pytestmark = pytest.mark.unit


def test_cold_start_has_seven_unknown_domains_and_no_invented_score() -> None:
    from src.domains.psyche.efficacy_scoring import build_profile

    profile = build_profile([], now=datetime(2026, 10, 16, tzinfo=UTC))

    assert [entry.domain.value for entry in profile.domains] == [
        "planning",
        "information",
        "emotional_support",
        "creativity",
        "technical",
        "social",
        "organization",
    ]
    assert {entry.status for entry in profile.domains} == {"unobserved"}
    assert all(entry.result_score is None for entry in profile.domains)
    assert all(entry.feedback_score is None for entry in profile.domains)


def _episode(
    index: int,
    *,
    verdict: str = "success",
    feedback: str | None = None,
    domains: tuple[str, ...] = ("technical",),
    days: int = 0,
) -> EfficacyEpisodeView:
    from datetime import timedelta
    from uuid import NAMESPACE_URL, uuid5

    from src.domains.psyche.efficacy_contracts import EfficacyEpisodeView, EfficacyObservation

    return EfficacyEpisodeView.model_validate(
        {
            "run_id": f"run-{index}",
            "message_id": uuid5(NAMESPACE_URL, f"message-{index}"),
            "terminal_at": datetime(2026, 10, 16, tzinfo=UTC) - timedelta(days=days),
            "observations": tuple(
                EfficacyObservation.model_validate(
                    {
                        "domain": d,
                        "verdict": verdict,
                        "reason": (
                            "goal_satisfied" if verdict == "success" else "insufficient_evidence"
                        ),
                    }
                )
                for d in domains
            ),
            "feedback": feedback,
        }
    )


def _profile(
    episodes: Sequence[EfficacyEpisodeView],
    *,
    collection_enabled: bool = True,
    influence_enabled: bool = True,
) -> EfficacyProfile:
    from src.domains.psyche.efficacy_scoring import build_profile

    return build_profile(
        episodes,
        now=datetime(2026, 10, 16, tzinfo=UTC),
        collection_enabled=collection_enabled,
        influence_enabled=influence_enabled,
    )


def _technical(profile: EfficacyProfile) -> EfficacyDomainProfile:
    return next(entry for entry in profile.domains if entry.domain == "technical")


def test_successes_and_failures_do_not_absorb_utility_or_partial_evidence() -> None:
    episodes = [
        _episode(1),
        _episode(2, verdict="failure", feedback="helpful"),
        _episode(3, verdict="partial"),
        _episode(4, verdict="unknown"),
        _episode(5, verdict="excluded", feedback="unhelpful"),
    ]
    result = _technical(_profile(episodes))
    assert result.results.model_dump() == {"success": 1, "failure": 1, "partial": 1, "unknown": 1}
    assert result.feedback.model_dump() == {"helpful": 1, "unhelpful": 1}
    assert result.result_count == 2
    assert result.feedback_count == 2
    assert result.result_score == 0.5
    assert result.feedback_score == 0.5
    assert result.status == "learning"


def test_partial_and_unknown_only_do_not_manufacture_a_score() -> None:
    result = _technical(_profile([_episode(1, verdict="partial"), _episode(2, verdict="unknown")]))
    assert result.result_score is None
    assert result.status == "unobserved"


def test_five_independent_scorable_episodes_qualify_an_axis() -> None:
    before = _technical(_profile([_episode(i) for i in range(4)]))
    after = _technical(_profile([_episode(i) for i in range(5)]))
    assert before.status == "learning"
    assert after.status == "observed"
    assert after.result_score == pytest.approx(6 / 7)


def test_feedback_cannot_score_both_domains_of_a_mixed_episode() -> None:
    profile = _profile([_episode(1, domains=("technical", "planning"), feedback="helpful")])
    assert profile.unassigned_feedback_count == 1
    assert sum(entry.feedback_count for entry in profile.domains) == 0
    assert sum(entry.result_count for entry in profile.domains) == 2


def test_feedback_without_assigned_domain_stays_unassigned() -> None:
    profile = _profile([_episode(1, domains=(), feedback="helpful")])
    assert profile.unassigned_feedback_count == 1
    assert sum(entry.result_count for entry in profile.domains) == 0


def test_expired_and_future_events_do_not_influence_present_experience() -> None:
    profile = _profile([_episode(1, days=91), _episode(2, days=-1), _episode(3, days=90)])
    assert _technical(profile).result_count == 1
    assert _technical(profile).last_observed_at == datetime(2026, 7, 18, tzinfo=UTC)


def test_duplicate_delivery_cannot_reach_sample_threshold_or_change_age() -> None:
    episode = _episode(1)
    profile = _profile([episode] * 20)
    assert _technical(profile).result_count == 1
    assert _technical(profile).status == "learning"


def test_conflicting_duplicate_is_refused_instead_of_silently_rewarded() -> None:
    with pytest.raises(ValueError, match="Conflicting"):
        _profile([_episode(1), _episode(1, verdict="failure")])


def test_quantity_cap_keeps_latest_canonical_episodes() -> None:
    profile = _profile(
        [_episode(0, verdict="failure", days=2)] + [_episode(i) for i in range(1, 501)]
    )
    result = _technical(profile)
    assert result.result_count == 500
    assert result.results.failure == 0


def test_aggregation_is_deterministic_and_does_not_mutate_inputs() -> None:
    episodes = [_episode(1, feedback="helpful"), _episode(2, days=1)]
    before = [entry.model_dump(mode="json") for entry in episodes]
    assert _profile(episodes) == _profile(list(reversed(episodes)))
    assert [entry.model_dump(mode="json") for entry in episodes] == before


def test_disabled_collection_does_not_erase_existing_experience() -> None:
    profile = _profile([_episode(1)], collection_enabled=False, influence_enabled=False)
    assert _technical(profile).result_count == 1
    assert not profile.collection_enabled
    assert not profile.influence_enabled


def test_naive_current_time_is_refused() -> None:
    from src.domains.psyche.efficacy_scoring import build_profile

    with pytest.raises(ValueError, match="aware"):
        build_profile([], now=datetime(2026, 10, 16))


@pytest.mark.parametrize(
    "domain",
    [
        "planning",
        "information",
        "emotional_support",
        "creativity",
        "technical",
        "social",
        "organization",
    ],
)
def test_each_cognitive_domain_receives_only_its_own_proof(domain: str) -> None:
    profile = _profile([_episode(1, domains=(domain,))])
    assert sum(entry.result_count for entry in profile.domains) == 1
    assert next(entry for entry in profile.domains if entry.domain == domain).result_count == 1


def test_canonical_message_cannot_be_counted_again_under_a_different_run() -> None:
    episode = _episode(1)
    conflicting = episode.model_copy(update={"run_id": "transport-retry"})
    with pytest.raises(ValueError, match="Conflicting"):
        _profile([episode, conflicting])


def test_projection_round_trips_as_json_without_new_observations() -> None:
    profile = _profile([_episode(1, feedback="helpful")])
    assert EfficacyProfile.model_validate_json(profile.model_dump_json()) == profile
