"""Negative protocol corpus; no authority is inferred from a client field."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.domains.world.authority import Authority, Identity, Limits
from src.domains.world.schemas import COMMAND_ADAPTER, AuthFrame, TicketRequest, WorldState

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("consent", [False, 1, "true", None])
def test_world_visibility_requires_an_explicit_boolean_choice(consent: object) -> None:
    with pytest.raises(ValidationError):
        TicketRequest.model_validate({"alias": "Visitor", "consent": consent})


@pytest.mark.parametrize("alias", [" ", "a\nforged", "trusted\u202ealias"])
def test_aliases_reject_controls_and_bidirectional_spoofing(alias: str) -> None:
    with pytest.raises(ValidationError):
        TicketRequest.model_validate({"alias": alias, "consent": True})


def test_alias_normalization_preserves_the_chosen_unicode_identity() -> None:
    with pytest.deprecated_call():
        assert TicketRequest(alias="  Léa  ", consent=True).alias == "Léa"


def test_authentication_rejects_a_client_selected_account() -> None:
    with pytest.raises(ValidationError):
        AuthFrame.model_validate(
            {
                "type": "authenticate",
                "version": 1,
                "scene": "lia-campus:1",
                "ticket": str(uuid4()),
                "user_id": str(uuid4()),
            }
        )


@pytest.mark.parametrize("version", [True, 1.0, "1", 2])
def test_protocol_version_is_an_integer_literal_not_a_coercible_value(version: object) -> None:
    with pytest.raises(ValidationError):
        AuthFrame.model_validate(
            {
                "type": "authenticate",
                "version": version,
                "scene": "lia-campus:1",
                "ticket": "v" * 43,
            }
        )


def test_normalization_cannot_expand_an_alias_beyond_the_public_bound() -> None:
    # U+0344 expands to two combining marks under NFC.
    with pytest.raises(ValidationError):
        TicketRequest(alias="\u0344" * 24, consent=True)


@pytest.mark.parametrize(
    "extra", [{"owner_id": "other"}, {"position": {"x": 10, "y": 10}}, {"type": "tool"}]
)
def test_commands_cannot_supply_an_actor_coordinate_or_business_dispatch(
    extra: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        COMMAND_ADAPTER.validate_python(
            {
                "type": "move",
                "version": 1,
                "seq": 1,
                "epoch": str(uuid4()),
                "dx": 0,
                "dy": 0,
                **extra,
            }
        )


def test_reconnect_rotates_the_controller_and_never_renews_the_predecessor() -> None:
    authority, state = Authority(Limits()), WorldState()
    identity = Identity(str(uuid4()), "Player", "en", "browser-a")
    authority.join(state, identity, "old-token", 100)
    assert authority.resume(state, identity, "old-token", "new-token", 101)
    assert not authority.resume(state, identity, "old-token", "third-token", 102)
    authority.heartbeat(state, identity.account_id, "old-token", 500, visible=True, active=True)
    assert state.actors[identity.account_id].expires_at == 146


def test_another_browser_cannot_silently_resume_an_existing_controller() -> None:
    authority, state = Authority(Limits()), WorldState()
    original = Identity(str(uuid4()), "Player", "en", "browser-a")
    authority.join(state, original, "token", 100)
    different = Identity(original.account_id, "Player", "en", "browser-b")
    assert not authority.resume(state, different, "token", "new-token", 101)


def test_duplicate_tab_cannot_accept_or_release_another_tabs_queue_offer() -> None:
    authority, state = Authority(Limits(capacity=1)), WorldState()
    first, queued = Identity(str(uuid4()), "First", "en"), Identity(str(uuid4()), "Queued", "en")
    authority.join(state, first, "first", 100)
    authority.join(state, queued, "queued-tab", 100)
    authority.leave(state, queued.account_id, "other-tab")
    assert len(state.queue) == 1
    authority.leave(state, first.account_id, "first")
    authority.join(state, queued, "other-tab", 101)
    assert queued.account_id not in state.actors
    authority.join(state, queued, "queued-tab", 101)
    assert queued.account_id in state.actors


def test_movement_cannot_revive_an_idle_expired_participant() -> None:
    authority = Authority(Limits(idle_seconds=60, lease_seconds=120))
    state, identity = WorldState(), Identity(str(uuid4()), "Player", "en")
    authority.join(state, identity, "controller", 100)
    assert not authority.move(state, identity.account_id, "controller", 1, 1, 0, 161)
    assert state.actors[identity.account_id].seq == 0
