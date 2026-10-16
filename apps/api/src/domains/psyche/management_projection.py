"""The UI and native reader compile the same observed expression without creating state."""

from src.domains.psyche.engine import PsycheEngine
from src.domains.psyche.models import PsycheState
from src.domains.psyche.schemas import PsycheExpressionResponse, PsycheStateResponse


def project_psyche_state(
    state: PsycheState,
) -> tuple[PsycheStateResponse, PsycheExpressionResponse]:
    profile = PsycheEngine.compile_expression_profile(
        mood_p=state.mood_pleasure,
        mood_a=state.mood_arousal,
        mood_d=state.mood_dominance,
        emotions=state.active_emotions or [],
        stage=state.relationship_stage,
        warmth=state.relationship_warmth_active,
        drive_curiosity=state.drive_curiosity,
        drive_engagement=state.drive_engagement,
    )
    response = PsycheStateResponse.model_validate(
        {
            name: getattr(state, name)
            for name in PsycheStateResponse.model_fields
            if name not in {"mood_label", "mood_color", "efficacy_profile"}
        }
    )
    response.mood_label = profile.mood_label
    response.mood_color = PsycheEngine.mood_to_color(profile.mood_label)
    expression = PsycheExpressionResponse(
        mood_label=profile.mood_label,
        mood_intensity=profile.mood_intensity,
        active_emotions=[
            {"name": name, "intensity": intensity} for name, intensity in profile.active_emotions
        ],
        relationship_stage=profile.relationship_stage,
        warmth_label=profile.warmth_label,
        drive_curiosity=profile.drive_curiosity,
        drive_engagement=profile.drive_engagement,
    )
    return response, expression
