"""Pure subject-rarity selection algorithm for interest notifications (ADR-131).

Implements the bench-validated V5 variant (2026-07-18):
1. Group candidate interests by subject label (NULL subject = singleton group).
2. Exclude subjects notified within the subject cooldown window (fail-open:
   if every subject is cooling, ignore the cooldown).
3. Draw a subject with p ~ mean_weight^beta / (1 + recent_count)^gamma.
4. Draw an interest inside the subject with p ~ 1/(1 + recent_count)^intra_gamma
   (or weight-proportional when intra_gamma == 0).

Deliberately pure: no I/O, injected RNG, fully unit-testable. Callers load
candidates, the subject map, and recent notifications from the repository.
"""

import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from src.domains.interests.models import UserInterest

_SOLO_PREFIX = "\x00solo:"  # Non-printable prefix: cannot collide with LLM labels


@dataclass(frozen=True)
class SelectionConfig:
    """Tunables for subject-rarity selection, sourced from Settings.

    Attributes:
        subject_cooldown_hours: Freeze window after a subject is notified.
        subject_rarity_gamma: Subject draw rarity exponent (0 disables rarity).
        subject_weight_beta: Subject draw weight exponent (0 disables weight).
        intra_subject_rarity_gamma: Intra-subject rarity exponent
            (0 falls back to weight-proportional draw).
        lookback_days: Rolling window for rarity counts.
    """

    subject_cooldown_hours: int
    subject_rarity_gamma: float
    subject_weight_beta: float
    intra_subject_rarity_gamma: float
    lookback_days: int

    @classmethod
    def from_settings(cls, settings: Any) -> "SelectionConfig":
        """Build the config from the application Settings object.

        Args:
            settings: The composed application Settings instance.

        Returns:
            A frozen SelectionConfig snapshot of the relevant fields.
        """
        return cls(
            subject_cooldown_hours=settings.interest_subject_cooldown_hours,
            subject_rarity_gamma=settings.interest_subject_rarity_gamma,
            subject_weight_beta=settings.interest_subject_weight_beta,
            intra_subject_rarity_gamma=settings.interest_intra_subject_rarity_gamma,
            lookback_days=settings.interest_rarity_lookback_days,
        )


@dataclass
class SelectionDebug:
    """Diagnostic payload for structured logging and metrics.

    Attributes:
        total_subjects: Subject groups among candidates before cooldown filtering.
        eligible_subjects: Subject groups after cooldown filtering.
        fail_open: True when the cooldown filter emptied the pool and was ignored.
        picked_subject: Chosen subject label ("(solo)" for unclustered singletons).
    """

    total_subjects: int
    eligible_subjects: int
    fail_open: bool
    picked_subject: str


def _subject_key(interest_id: UUID, subject: str | None) -> str:
    """Map a (possibly NULL) subject label to a grouping key.

    NULL subjects (not yet clustered) become singleton groups so unclustered
    interests keep flowing while the clustering job catches up (fail-open).

    Args:
        interest_id: Interest UUID (singleton key material).
        subject: Subject label or None.

    Returns:
        A grouping key, unique per interest when subject is None.
    """
    return subject if subject else f"{_SOLO_PREFIX}{interest_id}"


def _resolve_recent_notifications(
    recent_notifications: list[tuple[UUID | None, datetime]],
    subject_by_interest: dict[UUID, str | None],
    now: datetime,
    config: SelectionConfig,
) -> tuple[dict[str, int], dict[UUID, int], set[str]]:
    """Resolve recent notifications into rarity counts and cooling subjects.

    Args:
        recent_notifications: (interest_id, created_at) pairs; interest_id may
            be None (deleted interests) and is skipped, as are notifications
            whose interest is no longer active (absent from the subject map).
        subject_by_interest: Subject label for every ACTIVE interest.
        now: Timezone-aware current datetime.
        config: Selection tunables (lookback + cooldown windows).

    Returns:
        (per-subject counts, per-interest counts, cooling subject keys).
    """
    lookback_floor = now - timedelta(days=config.lookback_days)
    cooldown_floor = now - timedelta(hours=config.subject_cooldown_hours)
    subject_counts: dict[str, int] = {}
    interest_counts: dict[UUID, int] = {}
    cooling: set[str] = set()
    for interest_id, created_at in recent_notifications:
        if interest_id is None or interest_id not in subject_by_interest:
            continue
        if created_at < lookback_floor:
            continue
        key = _subject_key(interest_id, subject_by_interest[interest_id])
        subject_counts[key] = subject_counts.get(key, 0) + 1
        interest_counts[interest_id] = interest_counts.get(interest_id, 0) + 1
        if created_at >= cooldown_floor:
            cooling.add(key)
    return subject_counts, interest_counts, cooling


def _draw_subject(
    eligible: dict[str, list[tuple["UserInterest", float]]],
    subject_counts: dict[str, int],
    config: SelectionConfig,
    draw: Any,
) -> str:
    """Level 1 draw: p ~ mean_weight^beta / (1 + recent_count)^gamma.

    Args:
        eligible: Candidate groups keyed by subject.
        subject_counts: Recent notification counts per subject key.
        config: Selection tunables.
        draw: RNG providing .choices().

    Returns:
        The picked subject key.
    """
    keys = list(eligible)
    weights: list[float] = []
    for key in keys:
        members = eligible[key]
        mean_weight = sum(w for _, w in members) / len(members)
        rarity = 1.0 / (1.0 + subject_counts.get(key, 0)) ** config.subject_rarity_gamma
        weights.append((mean_weight**config.subject_weight_beta) * rarity)
    picked: str = draw.choices(keys, weights=weights)[0]
    return picked


def _draw_member(
    members: list[tuple["UserInterest", float]],
    interest_counts: dict[UUID, int],
    config: SelectionConfig,
    draw: Any,
) -> "UserInterest":
    """Level 2 draw: intra-subject rarity (V5) or weight-proportional.

    Args:
        members: (interest, weight) pairs of the picked subject.
        interest_counts: Recent notification counts per interest.
        config: Selection tunables.
        draw: RNG providing .choices().

    Returns:
        The selected interest.
    """
    if config.intra_subject_rarity_gamma > 0:
        weights = [
            1.0 / (1.0 + interest_counts.get(i.id, 0)) ** config.intra_subject_rarity_gamma
            for i, _ in members
        ]
    else:
        weights = [w for _, w in members]
    selected: UserInterest = draw.choices(members, weights=weights)[0][0]
    return selected


def select_interest_subject_rarity(
    candidates: list[tuple["UserInterest", float]],
    subject_by_interest: dict[UUID, str | None],
    recent_notifications: list[tuple[UUID | None, datetime]],
    now: datetime,
    config: SelectionConfig,
    rng: random.Random | None = None,
) -> tuple["UserInterest", SelectionDebug] | None:
    """Select an interest using the two-level subject-rarity draw (V5).

    Args:
        candidates: Eligible interests with effective weights (already filtered
            by per-topic cooldown by the caller).
        subject_by_interest: Subject label for every ACTIVE interest of the user
            (not only candidates — a cooling sibling must still freeze its subject).
        recent_notifications: (interest_id, created_at) pairs from the lookback
            window; interest_id may be None (deleted interests) and is skipped.
        now: Timezone-aware current datetime.
        config: Selection tunables.
        rng: Injected RNG for deterministic tests; defaults to the module RNG.

    Returns:
        (selected_interest, debug) or None when candidates is empty.
    """
    if not candidates:
        return None
    draw: random.Random | Any = rng or random

    subject_counts, interest_counts, cooling = _resolve_recent_notifications(
        recent_notifications, subject_by_interest, now, config
    )

    # Group candidates by subject key.
    groups: dict[str, list[tuple[UserInterest, float]]] = {}
    for interest, weight in candidates:
        key = _subject_key(interest.id, subject_by_interest.get(interest.id))
        groups.setdefault(key, []).append((interest, weight))

    eligible = {key: members for key, members in groups.items() if key not in cooling}
    fail_open = not eligible
    if fail_open:
        eligible = groups

    picked_key = _draw_subject(eligible, subject_counts, config, draw)
    selected = _draw_member(eligible[picked_key], interest_counts, config, draw)

    debug = SelectionDebug(
        total_subjects=len(groups),
        eligible_subjects=len(eligible),
        fail_open=fail_open,
        picked_subject="(solo)" if picked_key.startswith(_SOLO_PREFIX) else picked_key,
    )
    return selected, debug
