"""A world projection carries only declared art, never owner preference metadata."""

from src.domains.world.authority import Authority, Identity, Limits
from src.domains.world.avatar import AvatarAppearance
from src.domains.world.schemas import WorldState


def test_public_appearance_round_trips_and_respects_the_existing_block_filter() -> None:
    authority = Authority(Limits())
    state = WorldState()
    first = AvatarAppearance(hair="long", outfit="dress", hair_color="violet")
    second = AvatarAppearance(hair="bald", headwear="hat")
    authority.join(
        state, Identity("account-one", "One", "fr", "PRIVATE_BINDING", first), "controller-one", 1
    )
    authority.join(
        state, Identity("account-two", "Two", "en", "PRIVATE_BINDING", second), "controller-two", 1
    )
    restored = WorldState.model_validate_json(state.model_dump_json())
    view = authority.project(restored, "account-one", set(), 1, "controller-one")
    assert view.you is not None and view.you.appearance == first
    assert len(view.actors) == 1 and view.actors[0].appearance == second
    for private in [
        "PRIVATE_BINDING",
        "controller-one",
        "account-one",
        "world_avatar_preferences",
        "owner_id",
    ]:
        assert private not in view.model_dump_json()
    hidden = authority.project(restored, "account-one", {"account-two"}, 1, "controller-one")
    assert hidden.actors == []
