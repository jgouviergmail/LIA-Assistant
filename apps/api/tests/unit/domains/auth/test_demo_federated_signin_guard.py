"""Federated sign-in is closed on a public demonstrator.

Lot 2 made the terms mandatory — on the registration path. Sign in with
Google is a DIFFERENT path: ``_find_or_create_google_user`` creates the
account straight from the provider's user info, so a visitor arriving that
way accepts nothing, and the document telling them the instance is wiped
every night and must never hold real data is the one they never read.

Three things go wrong at once on that route:

- the terms are bypassed (owner arbitration 6: valid email AND terms);
- a real Google identity lands on a public, nightly-wiped instance;
- it spends the operator's OAuth client on strangers.

Connector linking was closed in lot 2 by exactly the same reasoning. This is
the sibling case that the connectors guard could not see, because it only
ever watched ``/connectors``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


def _request(path: str) -> MagicMock:
    request = MagicMock()
    request.url.path = path
    return request


def _demo_mode(enabled: bool) -> object:
    fake = MagicMock()
    fake.demo_mode_enabled = enabled
    fake.demo_terms_version = "2026-08-06"
    return fake


class TestClassification:
    """A provider sign-in is recognised by shape, not by a hard-coded list."""

    @pytest.mark.parametrize(
        "path",
        [
            "/api/v1/auth/google/login",
            "/api/v1/auth/google/callback",
            # The next provider is covered the day it is mounted — the whole
            # point of classifying the shape instead of listing Google.
            "/api/v1/auth/apple/login",
            "/api/v1/auth/microsoft/callback",
        ],
    )
    def test_provider_sign_in_paths_are_recognised(self, path: str) -> None:
        from src.core.demo_mode import is_federated_signin_path

        assert is_federated_signin_path(path) is True

    @pytest.mark.parametrize(
        "path",
        [
            # Password sign-in: the demonstrator's ONLY way in, must survive.
            "/api/v1/auth/login",
            "/api/v1/auth/logout",
            "/api/v1/auth/register",
            "/api/v1/auth/verify-email",
            "/api/v1/auth/me",
            # A deeper route that merely ends in a familiar word.
            "/api/v1/auth/step-up/webauthn/verify",
        ],
    )
    def test_the_visitor_journey_is_not_caught(self, path: str) -> None:
        from src.core.demo_mode import is_federated_signin_path

        assert is_federated_signin_path(path) is False


class TestEnforcement:
    async def test_provider_sign_in_is_refused_in_demo_mode(self) -> None:
        from src.core.demo_mode import forbid_federated_signin_in_demo
        from src.core.exceptions import AuthorizationError

        with patch("src.core.demo_mode.settings", _demo_mode(True)):
            with pytest.raises(AuthorizationError):
                await forbid_federated_signin_in_demo(_request("/api/v1/auth/google/login"))

    async def test_password_sign_in_still_works_in_demo_mode(self) -> None:
        from src.core.demo_mode import forbid_federated_signin_in_demo

        with patch("src.core.demo_mode.settings", _demo_mode(True)):
            assert await forbid_federated_signin_in_demo(_request("/api/v1/auth/login")) is None

    async def test_nothing_is_refused_outside_demo_mode(self) -> None:
        from src.core.demo_mode import forbid_federated_signin_in_demo

        with patch("src.core.demo_mode.settings", _demo_mode(False)):
            assert (
                await forbid_federated_signin_in_demo(_request("/api/v1/auth/google/login")) is None
            )


class TestWiring:
    def test_the_guard_is_mounted_on_the_auth_router(self) -> None:
        from src.core.demo_mode import forbid_federated_signin_in_demo
        from src.domains.auth.router import router

        mounted = {
            getattr(dependency.dependency, "__name__", "")
            for dependency in getattr(router, "dependencies", [])
        }
        assert forbid_federated_signin_in_demo.__name__ in mounted

    async def test_every_federated_route_of_the_real_router_is_refused(self) -> None:
        """Census: walk the router, not a list somebody remembered to update."""
        from src.core.demo_mode import (
            forbid_federated_signin_in_demo,
            is_federated_signin_path,
        )
        from src.core.exceptions import AuthorizationError
        from src.domains.auth.router import router

        federated = [
            "/api/v1/auth" + str(getattr(route, "path", ""))
            for route in router.routes
            if is_federated_signin_path("/api/v1/auth" + str(getattr(route, "path", "")))
        ]
        assert federated, "the auth router must still expose provider sign-in to guard"

        with patch("src.core.demo_mode.settings", _demo_mode(True)):
            for path in federated:
                with pytest.raises(AuthorizationError):
                    await forbid_federated_signin_in_demo(_request(path))


class TestTheInterfaceIsTold:
    """A refused button is a broken button — the front must not draw it.

    Closing the route without telling the interface leaves a visitor a
    "Sign in with Google" button that answers 404. The instance already
    publishes its authentication capabilities on ``/auth/features``; this
    rides that channel rather than inventing a second one.
    """

    async def test_features_hide_provider_sign_in_in_demo_mode(self) -> None:
        from src.domains.auth.router import auth_features

        with patch("src.domains.auth.router.settings", _demo_mode(True)):
            features = await auth_features()

        assert features.federated_signin_enabled is False

    async def test_features_announce_the_terms_requirement_in_demo_mode(self) -> None:
        """The server refuses without them; the form must be able to ask.

        Measured 2026-08-06: every registration through the interface failed
        on `terms_accepted` because the form had no box, while the API path
        worked — the requirement was enforced and unpublished.
        """
        from src.domains.auth.router import auth_features

        fake = _demo_mode(True)
        fake.demo_terms_version = "2026-08-06"
        with patch("src.domains.auth.router.settings", fake):
            features = await auth_features()

        assert features.terms_required is True
        assert features.terms_version == "2026-08-06"

    async def test_features_ask_for_nothing_outside_demo_mode(self) -> None:
        from src.domains.auth.router import auth_features

        with patch("src.domains.auth.router.settings", _demo_mode(False)):
            features = await auth_features()

        assert features.terms_required is False

    async def test_features_announce_provider_sign_in_normally(self) -> None:
        from src.domains.auth.router import auth_features

        with patch("src.domains.auth.router.settings", _demo_mode(False)):
            features = await auth_features()

        assert features.federated_signin_enabled is True


class TestConnectorGuardKeepsWorking:
    """The connector guard moved to the shared module; its contract holds."""

    async def test_account_linking_is_still_refused(self) -> None:
        from src.core.demo_mode import forbid_account_linking_in_demo
        from src.core.exceptions import AuthorizationError

        with patch("src.core.demo_mode.settings", _demo_mode(True)):
            with pytest.raises(AuthorizationError):
                await forbid_account_linking_in_demo(_request("/api/v1/connectors/gmail/authorize"))
