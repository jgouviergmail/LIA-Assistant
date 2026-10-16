"""A reset invalidates background evidence without erasing a soft reset's learning."""

from uuid import uuid4

from src.domains.psyche.engine import PADVector
from src.domains.psyche.models import PsycheState
from src.domains.psyche.reset_policy import apply_psyche_reset


def test_full_reset_changes_efficacy_generation_and_discards_projection() -> None:
    generation = uuid4()
    state = PsycheState(user_id=uuid4())
    state.efficacy_generation = generation
    state.efficacy_profile = {"private": "aggregate"}
    apply_psyche_reset(state, "full", PADVector(0.0, 0.0, 0.0))
    assert state.efficacy_generation != generation
    assert state.efficacy_profile is None


def test_soft_reset_preserves_efficacy_generation_and_projection() -> None:
    generation = uuid4()
    state = PsycheState(user_id=uuid4())
    state.efficacy_generation = generation
    state.efficacy_profile = {"version": 1}
    apply_psyche_reset(state, "soft", PADVector(0.0, 0.0, 0.0))
    assert state.efficacy_generation == generation
    assert state.efficacy_profile == {"version": 1}
