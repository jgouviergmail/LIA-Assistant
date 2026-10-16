"""Pure bounded aggregation of canonical episodes; no legacy score conversion."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

from src.domains.psyche.constants import (
    EFFICACY_MAX_EPISODES,
    EFFICACY_MIN_SAMPLES,
    EFFICACY_WINDOW_DAYS,
    EfficacyDomain,
)
from src.domains.psyche.efficacy_contracts import (
    EfficacyDomainProfile,
    EfficacyEpisodeView,
    EfficacyFeedback,
    EfficacyFeedbackCounts,
    EfficacyObservation,
    EfficacyProfile,
    EfficacyResultCounts,
    EfficacyVerdict,
)


def _active_episodes(
    episodes: Sequence[EfficacyEpisodeView], now: datetime, window_days: int
) -> tuple[EfficacyEpisodeView, ...]:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Current time must be timezone-aware")
    if type(window_days) is not int or not 1 <= window_days <= EFFICACY_WINDOW_DAYS:
        raise ValueError("Window must be an integer within the pilot retention bound")
    now = now.astimezone(UTC)
    cutoff = now - timedelta(days=window_days)
    unique: dict[str, EfficacyEpisodeView] = {}
    message_runs: dict[UUID, str] = {}
    for episode in episodes:
        if not cutoff <= episode.terminal_at <= now:
            continue
        previous = unique.get(episode.run_id)
        if previous is not None and previous != episode:
            raise ValueError("Conflicting canonical episode delivery")
        previous_run = message_runs.get(episode.message_id)
        if previous_run is not None and previous_run != episode.run_id:
            raise ValueError("Conflicting run identity for a canonical message")
        unique[episode.run_id] = episode
        message_runs[episode.message_id] = episode.run_id
    ordered = sorted(unique.values(), key=lambda episode: (episode.terminal_at, episode.message_id))
    return tuple(ordered[-EFFICACY_MAX_EPISODES:])


def _index(positive: int, negative: int) -> float | None:
    # A symmetric Beta(1,1) prior smooths each named axis, never the unknowns.
    return (positive + 1) / (positive + negative + 2) if positive + negative else None


def _result_counts(
    observations: Sequence[tuple[EfficacyEpisodeView, EfficacyObservation]],
) -> EfficacyResultCounts:
    counts = Counter(item.verdict for _, item in observations)
    return EfficacyResultCounts(
        success=counts[EfficacyVerdict.SUCCESS],
        failure=counts[EfficacyVerdict.FAILURE],
        partial=counts[EfficacyVerdict.PARTIAL],
        unknown=counts[EfficacyVerdict.UNKNOWN],
    )


def _domain_profile(
    domain: EfficacyDomain, episodes: Sequence[EfficacyEpisodeView]
) -> EfficacyDomainProfile:
    observations = [
        (episode, observation)
        for episode in episodes
        for observation in episode.observations
        if observation.domain == domain
    ]
    results = _result_counts(observations)
    feedback = [
        episode.feedback
        for episode, _ in observations
        if len(episode.observations) == 1 and episode.feedback is not None
    ]
    helpful = feedback.count(EfficacyFeedback.HELPFUL)
    unhelpful = feedback.count(EfficacyFeedback.UNHELPFUL)
    result_count = results.success + results.failure
    feedback_count = helpful + unhelpful
    count = max(result_count, feedback_count)
    status = "observed" if count >= EFFICACY_MIN_SAMPLES else "learning" if count else "unobserved"
    observed_dates = [
        episode.terminal_at
        for episode, observation in observations
        if observation.verdict != EfficacyVerdict.EXCLUDED or episode.feedback is not None
    ]
    return EfficacyDomainProfile(
        domain=domain,
        status=status,
        results=results,
        feedback=EfficacyFeedbackCounts(helpful=helpful, unhelpful=unhelpful),
        result_count=result_count,
        feedback_count=feedback_count,
        result_score=_index(results.success, results.failure),
        feedback_score=_index(helpful, unhelpful),
        last_observed_at=max(observed_dates, default=None),
    )


def build_profile(
    episodes: Sequence[EfficacyEpisodeView],
    *,
    now: datetime,
    window_days: int = EFFICACY_WINDOW_DAYS,
    collection_enabled: bool = True,
    influence_enabled: bool = True,
) -> EfficacyProfile:
    """Project at most 500 private episodes without mixing result and usefulness."""
    active = _active_episodes(episodes, now, window_days)
    return EfficacyProfile(
        window_days=window_days,
        collection_enabled=collection_enabled,
        influence_enabled=influence_enabled,
        unassigned_feedback_count=sum(
            episode.feedback is not None and len(episode.observations) != 1 for episode in active
        ),
        domains=tuple(_domain_profile(domain, active) for domain in EfficacyDomain),
    )
