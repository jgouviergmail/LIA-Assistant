"""The flow remembers which surface started it.

An OAuth callback has to decide where to send the user, and by the time it runs
the browser that started the flow is long gone. The only thing that survives is
the state token the provider echoes back — so what the flow knew at the start
has to be written into it.

That happens in exactly one place: ``initiate_flow`` builds every state payload
in this codebase, for all twelve connectors and for sign-in. Marking it there
means a new connector inherits the behaviour without its author knowing this
file exists — which is the point, because the alternative fails silently, one
connector at a time.

The absence of the marker is asserted just as hard as its presence: a browser
flow must not carry a field that would later send its user to a `lia://` link
nothing on a desktop can open.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from src.core.native_client import native_client_scope
from src.core.oauth.flow_handler import NATIVE_FLOW_METADATA_KEY, OAuthFlowHandler

pytestmark = pytest.mark.unit


def _handler() -> tuple[OAuthFlowHandler, Mock]:
    provider = Mock()
    provider.provider_name = "google"
    provider.client_id = "client"
    provider.redirect_uri = "https://api.test/callback"
    provider.scopes = ["email"]
    provider.authorization_endpoint = "https://accounts.example/auth"

    session_service = Mock()
    session_service.store_oauth_state = AsyncMock()
    return OAuthFlowHandler(provider, session_service), session_service


def _stored(session_service: Mock) -> dict[str, object]:
    return session_service.store_oauth_state.await_args.args[1]


class TestNativeFlow:
    async def test_a_shell_flow_is_marked(self) -> None:
        handler, session_service = _handler()

        with native_client_scope(True):
            await handler.initiate_flow(metadata={"user_id": "u1"})

        assert _stored(session_service)[NATIVE_FLOW_METADATA_KEY] is True

    async def test_the_marker_sits_beside_the_caller_s_own_metadata(self) -> None:
        handler, session_service = _handler()

        with native_client_scope(True):
            await handler.initiate_flow(metadata={"user_id": "u1", "connector_type": "gmail"})

        stored = _stored(session_service)
        # Merged, not replacing: the callback still needs the user id it peeks
        # for, and the connector type it reports back.
        assert stored["user_id"] == "u1"
        assert stored["connector_type"] == "gmail"
        assert stored[NATIVE_FLOW_METADATA_KEY] is True

    async def test_it_works_with_no_metadata_at_all(self) -> None:
        handler, session_service = _handler()

        with native_client_scope(True):
            await handler.initiate_flow()

        assert _stored(session_service)[NATIVE_FLOW_METADATA_KEY] is True


class TestBrowserFlow:
    async def test_a_browser_flow_carries_no_marker(self) -> None:
        handler, session_service = _handler()

        with native_client_scope(False):
            await handler.initiate_flow(metadata={"user_id": "u1"})

        # Not `False` — absent. A browser flow that carried the field would be
        # one wrong truthiness check away from redirecting a desktop user to a
        # `lia://` link their machine cannot open.
        assert NATIVE_FLOW_METADATA_KEY not in _stored(session_service)

    async def test_the_pkce_material_is_untouched_either_way(self) -> None:
        handler, session_service = _handler()

        with native_client_scope(True):
            await handler.initiate_flow()

        stored = _stored(session_service)
        assert stored["provider"] == "google"
        assert stored["code_verifier"]
