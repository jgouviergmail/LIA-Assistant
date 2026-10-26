"""Appearance refresh is monotonic and cannot create another participant."""

from src.domains.world.authority import Authority, Identity, Limits
from src.domains.world.avatar import AvatarAppearance, AvatarPreferences
from src.domains.world.avatar_presence import apply_appearance
from src.domains.world.schemas import WorldState


def test_late_save_cannot_overwrite_a_newer_public_style_or_create_an_actor() -> None:
    state = WorldState()
    authority = Authority(Limits())
    latest = AvatarPreferences(revision=2, appearance=AvatarAppearance(hair="bald"))
    apply_appearance(state, "owner", latest)
    assert state.actors == {}
    authority.join(state, Identity("owner", "LIA name", "fr"), "controller", 1)
    original_id = state.actors["owner"].public_id
    apply_appearance(state, "owner", latest)
    apply_appearance(
        state, "owner", AvatarPreferences(revision=1, appearance=AvatarAppearance(hair="long"))
    )
    actor = state.actors["owner"]
    assert actor.appearance == latest.appearance and actor.appearance_revision == 2
    assert (
        actor.public_id == original_id
        and actor.controller == "controller"
        and actor.alias == "LIA name"
    )
    assert (
        "appearance_revision"
        not in authority.project(state, "owner", set(), 1, "controller").model_dump_json()
    )
