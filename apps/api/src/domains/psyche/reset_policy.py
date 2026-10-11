"""Pure source reset transition is shared by actual writes and exact public previews."""

from datetime import UTC, datetime

from src.domains.psyche.constants import RELATIONSHIP_STAGES, RESET_LEVEL_FULL
from src.domains.psyche.engine import PADVector, PsycheEngine
from src.domains.psyche.models import PsycheState


def apply_psyche_reset(state: PsycheState, level: str, baseline: PADVector) -> None:
    state.mood_pleasure = baseline.pleasure
    state.mood_arousal = baseline.arousal
    state.mood_dominance = baseline.dominance
    state.mood_quadrant_since = datetime.now(UTC)
    state.active_emotions = []
    state.last_appraisal = None
    state.drive_curiosity = 0.5
    state.drive_engagement = 0.5
    if level == RESET_LEVEL_FULL:
        state.relationship_stage = RELATIONSHIP_STAGES[0]
        state.relationship_depth = 0.0
        state.relationship_warmth_active = 0.5
        state.relationship_trust = 0.3
        state.relationship_interaction_count = 0
        state.relationship_total_duration_minutes = 0.0
        state.self_efficacy = PsycheEngine.initialize_self_efficacy()
        state.narrative_identity = None
