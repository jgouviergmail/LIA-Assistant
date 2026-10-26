"""Human text never escapes the actor/session pair that explicitly sent it."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.domains.world.authority import Authority, Identity, Limits
from src.domains.world.messages import MessageRequest, MessageScope, message_pair
from src.domains.world.schemas import WorldState

pytestmark = pytest.mark.unit


def request(text: str) -> MessageRequest:
    return MessageRequest(
        id=str(uuid4()),
        epoch=str(uuid4()),
        controller="controller-token-at-least-sixteen",
        recipient=str(uuid4()),
        created_at=100.0,
        text=text,
        translation_consent=True,
    )


@pytest.mark.parametrize("text", ["", " \n\t", "x" * 1001, "a\x00b", "x\u202ey", "\ud800"])
def test_rejects_empty_oversized_and_hidden_control_text(text: str) -> None:
    with pytest.raises(ValidationError):
        request(text)


@pytest.mark.parametrize(
    "text", ["Bonjour\n朋友", "👩‍💻", "می‌روم", "<img src=x onerror=alert(1)>"]
)
def test_accepts_literal_multilingual_text_without_executing_or_rewriting_markup(text: str) -> None:
    assert request(text).text == text


def pair_fixture() -> tuple[WorldState, Identity, Identity, MessageScope]:
    state = WorldState()
    sender, recipient = [
        Identity(str(uuid4()), name, language, name)
        for name, language in [("A", "fr"), ("B", "en")]
    ]
    authority = Authority(Limits())
    authority.join(state, sender, "controller-token-at-least-sixteen", 100.0)
    authority.join(state, recipient, "other-controller-at-least-sixteen", 100.0)
    scope = MessageScope(
        account=sender.account_id,
        binding=sender.binding,
        controller="controller-token-at-least-sixteen",
        epoch=state.epoch,
        eligible=frozenset(state.actors),
        blocked=frozenset(),
        idle_seconds=600,
    )
    return state, sender, recipient, scope


def test_resolves_only_the_visible_public_actor_not_an_account_identifier() -> None:
    state, sender, recipient, scope = pair_fixture()
    target = state.actors[recipient.account_id]
    own, other = message_pair(state, scope, target.public_id, 101.0)
    assert own.account_id == sender.account_id and other.account_id == recipient.account_id
    with pytest.raises(ValueError, match="world_message_unavailable"):
        message_pair(state, scope, recipient.account_id, 101.0)


@pytest.mark.parametrize(
    "invalid",
    [
        "epoch",
        "controller",
        "binding",
        "blocked",
        "ineligible",
        "lease",
        "idle",
        "recipient-home",
        "sender-home",
        "self",
    ],
)
def test_every_authority_boundary_fails_closed(invalid: str) -> None:
    from dataclasses import replace

    from src.domains.world.collision import WORLD

    state, sender, recipient, scope = pair_fixture()
    target = state.actors[recipient.account_id]
    if invalid in {"epoch", "controller", "binding"}:
        scope = replace(scope, **{invalid: "forged"})
    if invalid == "blocked":
        scope = replace(scope, blocked=frozenset({recipient.account_id}))
    if invalid == "ineligible":
        scope = replace(scope, eligible=frozenset({sender.account_id}))
    if invalid == "lease":
        target.expires_at = 100.0
    if invalid == "idle":
        target.activity_at = -600.0
    if invalid.endswith("-home"):
        home = next(zone for zone in WORLD.zones if zone.id == "home")
        actor = target if invalid == "recipient-home" else state.actors[sender.account_id]
        actor.position = {"x": home.x + 2.0, "y": home.y + 2.0}
    public_id = state.actors[sender.account_id].public_id if invalid == "self" else target.public_id
    with pytest.raises(ValueError, match="world_message_unavailable"):
        message_pair(state, scope, public_id, 101.0)


def test_freshness_is_checked_against_server_time_in_both_directions() -> None:
    payload = request("hello")
    payload.require_fresh(130.0)
    for now in (99.0 - 5.0, 161.0):
        with pytest.raises(ValueError, match="world_message_expired"):
            payload.require_fresh(now)
