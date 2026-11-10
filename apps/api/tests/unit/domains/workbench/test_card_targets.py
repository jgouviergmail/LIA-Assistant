"""A card opens only the same source, never a guessed current provider record."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from src.core.config import settings
from src.core.content_source import content_source_binding
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.preferences.owner_defaults import OwnerContainer
from src.domains.workbench import card_opening, clients
from src.domains.workbench.card_targets import (
    CARD_TOKEN_MAX_CHARS,
    CARD_TOOLS,
    CardTargetKind,
    CardToolTarget,
    SignedCardTarget,
    read_card_target,
    sign_card_target,
)
from src.domains.workbench.errors import NOT_CONNECTED, refuse
from src.domains.workbench.features import WorkbenchTool

pytestmark = pytest.mark.unit


@dataclass
class Credentials:
    account_binding: str = "grant-a"
    apple_id: str | None = None
    bridge_id: str | None = None


@dataclass
class Client:
    credentials: Credentials


def _envelope() -> SignedCardTarget:
    return SignedCardTarget(
        target=CardToolTarget(kind=CardTargetKind.EVENT, item_id="evt/+?=", container_id="cal/@x"),
        provider=ConnectorType.GOOGLE_CALENDAR,
        source_binding=content_source_binding(Client(Credentials())),
    )


def test_the_signature_binds_every_field_and_the_lia_account_and_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = uuid4()
    envelope = _envelope()
    token = sign_card_target(envelope, user)
    assert read_card_target(token, user) == envelope
    assert read_card_target(token, uuid4()) is None
    assert read_card_target("x" + token[1:], user) is None
    assert read_card_target(token + ".", user) is None
    monkeypatch.setattr(settings, "secret_key", "another-instance-secret")
    assert read_card_target(token, user) is None


@pytest.mark.parametrize(
    "token",
    ["", "untrusted", "x.y", "à.b", "a" * (CARD_TOKEN_MAX_CHARS + 1)],
    ids=["empty", "unsigned", "bad-signature", "unicode", "over-limit"],
)
def test_malformed_envelopes_fail_closed(token: str) -> None:
    assert read_card_target(token, uuid4()) is None


@pytest.mark.parametrize("kind", [CardTargetKind.EVENT, CardTargetKind.TASK])
def test_scoped_ids_cannot_fall_back_to_the_current_default(kind: CardTargetKind) -> None:
    with pytest.raises(ValidationError):
        CardToolTarget(kind=kind, item_id="same-id-in-several-containers")
    with pytest.raises(ValidationError):
        CardToolTarget(kind=kind, item_id="id", container_id="not an opaque provider ID")


def test_provider_family_and_route_vocabulary_are_checked() -> None:
    with pytest.raises(ValidationError):
        SignedCardTarget(
            target=CardToolTarget(kind=CardTargetKind.CONTACT, item_id="people/123"),
            provider=ConnectorType.GOOGLE_DRIVE,
            source_binding="a" * 64,
        )
    with pytest.raises(ValidationError):
        CardToolTarget(kind=CardTargetKind.FILE, item_id="file", day="2026-11-08")
    with pytest.raises(ValidationError):
        CardToolTarget(
            kind=CardTargetKind.EVENT, item_id="evt", container_id="cal", day="2026-02-30"
        )
    with pytest.raises(ValidationError):
        CardToolTarget(kind=CardTargetKind.EMAIL, item_id="id", is_folder=True)
    assert set(CARD_TOOLS) == set(CardTargetKind)


def test_the_source_identity_is_stable_across_refresh_and_opaque() -> None:
    apple = Client(Credentials(account_binding="", apple_id="owner@example.test"))
    hue = Client(Credentials(account_binding="", bridge_id="bridge-1"))
    assert content_source_binding(apple) and "owner" not in content_source_binding(apple)
    assert content_source_binding(hue) != content_source_binding(apple)
    assert content_source_binding(hue) != content_source_binding(
        Client(Credentials(account_binding="", bridge_id="bridge-2"))
    )
    assert content_source_binding(Client(Credentials(account_binding=""))) == ""


@pytest.mark.parametrize(
    "binding,provider,expected",
    [
        ("grant-a", ConnectorType.GOOGLE_CALENDAR, None),
        ("grant-b", ConnectorType.GOOGLE_CALENDAR, "source_changed"),
        ("grant-a", ConnectorType.MICROSOFT_CALENDAR, "source_changed"),
        ("", ConnectorType.GOOGLE_CALENDAR, "source_changed"),
    ],
)
async def test_opening_checks_current_source_and_closes_client(
    binding: str, provider: ConnectorType, expected: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = uuid4()
    closed = []

    @asynccontextmanager
    async def door(
        tool: WorkbenchTool, user_id: UUID, *, fresh: bool = False
    ) -> AsyncIterator[ActiveClient]:
        assert tool == WorkbenchTool.CALENDAR and user_id == user and fresh
        try:
            yield ActiveClient(Client(Credentials(binding)), provider, None)
        finally:
            closed.append(True)

    monkeypatch.setattr(card_opening, "open_tool_client", door)
    result = await card_opening.open_card_target(sign_card_target(_envelope(), user), user)
    assert result.available is (expected is None)
    assert result.reason == expected
    assert result.target == (_envelope().target if expected is None else None)
    assert closed == [True]


@pytest.mark.parametrize("timeout", [False, True])
async def test_disconnection_or_timeout_has_no_external_fallback(
    timeout: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    @asynccontextmanager
    async def door(
        tool: WorkbenchTool, user_id: UUID, *, fresh: bool = False
    ) -> AsyncIterator[ActiveClient]:
        if timeout:
            raise TimeoutError
        refuse(NOT_CONNECTED)
        yield  # pragma: no cover - async-context-manager protocol; refusal never yields

    monkeypatch.setattr(card_opening, "open_tool_client", door)
    user = uuid4()
    result = await card_opening.open_card_target(sign_card_target(_envelope(), user), user)
    assert result.model_dump() == {"available": False, "target": None, "reason": "unavailable"}


async def test_invalid_proof_never_reads_current_connectors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("A forged token must be refused before any source lookup")

    monkeypatch.setattr(card_opening, "open_tool_client", forbidden)
    result = await card_opening.open_card_target("forged", uuid4())
    assert result.reason == "historical"


async def test_click_admission_bypasses_provider_resolution_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @asynccontextmanager
    async def door(
        category: str,
        user_id: UUID,
        *,
        container: OwnerContainer | None = None,
        fresh: bool = False,
    ) -> AsyncIterator[ActiveClient]:
        assert fresh and category == "calendar" and container is None
        yield ActiveClient(Client(Credentials()), ConnectorType.GOOGLE_CALENDAR, None)

    monkeypatch.setattr(clients, "open_active_client", door)
    async with clients.open_tool_client(WorkbenchTool.CALENDAR, uuid4(), fresh=True) as opened:
        assert content_source_binding(opened.client)
