"""Closed efficacy boundaries reject malformed and unbounded evidence."""

from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

pytestmark = pytest.mark.unit


def test_observation_rejects_unknown_domain_verdict_and_free_text_reason() -> None:
    from src.domains.psyche.efficacy_contracts import EfficacyObservation

    for update in ({"domain": "email"}, {"verdict": "probably"}, {"reason": "the user is John"}):
        data = {"domain": "technical", "verdict": "success", "reason": "goal_satisfied"} | update
        with pytest.raises(ValidationError):
            EfficacyObservation.model_validate(data)


def _episode_data() -> dict[str, object]:
    from src.domains.psyche.efficacy_contracts import EfficacyEpoch

    return {
        "epoch": EfficacyEpoch(state_id=uuid4(), generation=uuid4()),
        "run_id": "run-1",
        "message_id": uuid4(),
        "terminal_at": datetime(2026, 10, 16, tzinfo=UTC),
        "observations": (
            {"domain": "technical", "verdict": "success", "reason": "goal_satisfied"},
        ),
        "config_fingerprint": "a" * 64,
    }


def test_episode_rejects_duplicate_and_excess_domains() -> None:
    from src.domains.psyche.efficacy_contracts import EfficacyEpisodeInput

    data = _episode_data()
    for domains in (("technical", "technical"), ("technical", "planning", "social")):
        data["observations"] = tuple(
            {"domain": d, "verdict": "unknown", "reason": "insufficient_evidence"} for d in domains
        )
        with pytest.raises(ValidationError):
            EfficacyEpisodeInput.model_validate(data)


def test_episode_requires_bounded_nonempty_identifiers_and_aware_time() -> None:
    from src.domains.psyche.efficacy_contracts import EfficacyEpisodeInput

    for update in (
        {"run_id": ""},
        {"run_id": "x" * 129},
        {"run_id": 42},
        {"config_fingerprint": "not-a-digest"},
        {"terminal_at": datetime(2026, 10, 16)},
    ):
        with pytest.raises(ValidationError):
            EfficacyEpisodeInput.model_validate(_episode_data() | update)


def test_episode_normalizes_timezone_and_is_immutable() -> None:
    from src.domains.psyche.efficacy_contracts import EfficacyEpisodeInput

    data = _episode_data() | {
        "terminal_at": datetime(2026, 10, 16, 2, tzinfo=timezone(timedelta(hours=2)))
    }
    episode = EfficacyEpisodeInput.model_validate(data)
    assert episode.terminal_at == datetime(2026, 10, 16, tzinfo=UTC)
    assert episode.terminal_at.tzinfo is UTC
    with pytest.raises(ValidationError):
        episode.run_id = "changed"


def test_profile_refuses_nonfinite_scores_and_incoherent_counts() -> None:
    from src.domains.psyche.efficacy_contracts import EfficacyDomainProfile

    data = {
        "domain": "technical",
        "status": "learning",
        "results": {"success": 1},
        "feedback": {},
        "result_count": 1,
        "feedback_count": 0,
        "result_score": 2 / 3,
        "feedback_score": None,
        "last_observed_at": datetime(2026, 10, 16, tzinfo=UTC),
    }
    for update in (
        {"result_score": float("nan")},
        {"result_score": float("inf")},
        {"result_score": 1.1},
        {"result_count": True},
        {"result_count": 2},
        {"feedback_count": -1},
        {"result_score": None},
    ):
        with pytest.raises(ValidationError):
            EfficacyDomainProfile.model_validate(data | update)


def test_policy_cannot_describe_an_action_with_no_relevant_domain() -> None:
    from src.domains.psyche.efficacy_contracts import EfficacyPolicy

    with pytest.raises(ValidationError):
        EfficacyPolicy(action="verify", reason="verification_needed")


def test_policy_cannot_claim_an_action_with_a_contradictory_reason() -> None:
    from src.domains.psyche.efficacy_contracts import EfficacyPolicy

    with pytest.raises(ValidationError):
        EfficacyPolicy(action="verify", domains=("technical",), reason="no_adjustment")
