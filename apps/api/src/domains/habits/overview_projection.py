"""The management UI and native readers share the source profile and overview projection."""

from src.core.config import settings
from src.domains.habits.candidates import RecurrenceCandidate
from src.domains.habits.models import ProfileVerdict, UserHabitProfile
from src.domains.habits.rhythm import RhythmProfile, RhythmThresholds, effective_presence_bar
from src.domains.habits.schemas import (
    HabitResponse,
    HabitsCandidateSchema,
    HabitsOverviewResponse,
    HabitsProfileClassSchema,
    HabitsProfileSchema,
    HabitsStreakSchema,
    HabitWindowSchema,
)
from src.domains.habits.streaks import StreakSummary
from src.domains.users.models import User


def profile_to_schema(profile: UserHabitProfile | None) -> HabitsProfileSchema:
    """Stored profile row → API schema (pre-first-run shape when None)."""
    required = {
        "weekday": settings.habits_min_neff_weekday,
        "weekend": settings.habits_min_neff_weekend,
    }
    thresholds = RhythmThresholds.from_settings(settings)
    if profile is None:
        return HabitsProfileSchema(
            computed_at=None,
            weekday=HabitsProfileClassSchema(
                verdict=ProfileVerdict.INSUFFICIENT,
                windows=[],
                n_eff=0.0,
                required_n_eff=required["weekday"],
                effective_presence_min=effective_presence_bar(0.0, thresholds),
            ),
            weekend=HabitsProfileClassSchema(
                verdict=ProfileVerdict.INSUFFICIENT,
                windows=[],
                n_eff=0.0,
                required_n_eff=required["weekend"],
                effective_presence_min=effective_presence_bar(0.0, thresholds),
            ),
            active_days_fraction=0.0,
            sparse=False,
        )
    parsed = RhythmProfile.from_payload(profile.payload)

    def _class(name: str) -> HabitsProfileClassSchema:
        rhythm = getattr(parsed, name)
        return HabitsProfileClassSchema(
            verdict=ProfileVerdict(rhythm.verdict),
            windows=[
                HabitWindowSchema(start_hour=w.start_hour, end_hour=w.end_hour, presence=w.presence)
                for w in rhythm.windows
            ],
            n_eff=rhythm.n_eff,
            required_n_eff=required[name],
            effective_presence_min=effective_presence_bar(rhythm.n_eff, thresholds),
            bin_presence=list(rhythm.bin_presence),
        )

    return HabitsProfileSchema(
        computed_at=profile.computed_at,
        weekday=_class("weekday"),
        weekend=_class("weekend"),
        active_days_fraction=parsed.active_days_fraction,
        sparse=parsed.sparse,
    )


def build_overview_response(
    current_user: User,
    profile: UserHabitProfile | None,
    streak: StreakSummary,
    habits: list[HabitResponse],
    candidates: list[RecurrenceCandidate],
    candidates_more: int,
) -> HabitsOverviewResponse:
    """Project the same public values, published thresholds and advisory candidates."""
    return HabitsOverviewResponse(
        habits_enabled=current_user.habits_enabled,
        profile=profile_to_schema(profile),
        streak=HabitsStreakSchema(
            current=streak.current,
            longest=streak.longest,
            milestone_reached=streak.milestone_reached,
            next_milestone=streak.next_milestone,
        ),
        habits=[HabitResponse.model_validate(h) for h in habits],
        candidates=[
            HabitsCandidateSchema(
                key=c.key,
                observed_days=c.observed_days,
                required_days=c.required_days,
                origin=c.origin,
            )
            for c in candidates
        ],
        candidates_more=candidates_more,
        chat_suggestions_enabled=bool(settings.recurrence_suggestion_enabled),
    )
