"""Where a connector authorization sends the user back to.

Ten callbacks built this redirect by hand, each with its own f-string. That is
ten places to remember when the destination changes — and the native shells
made it change. Here it is one function, and the ten callbacks call it.

The property that matters is the branch: a flow started in a shell must come
home to the shell. A user who authorized Gmail from the app and lands on the
web settings page in Safari has not failed, exactly — the connector IS
connected — but the app they were using is still sitting on the old screen,
with no sign anything happened.

Failure branches the same way, and that is not symmetry for its own sake: the
stranded-in-a-browser outcome is *worse* on the error path, because there is no
connector to find later and nothing to explain what went wrong.
"""

from __future__ import annotations

import uuid

import pytest

from src.domains.connectors.oauth_return import (
    connector_error_return,
    connector_success_return,
)

pytestmark = pytest.mark.unit

CONNECTOR_ID = uuid.uuid4()


class TestBrowser:
    def test_success_goes_to_the_settings_page(self) -> None:
        response = connector_success_return(
            is_native=False, connector_type="gmail", connector_id=CONNECTOR_ID
        )

        location = response.headers["location"]
        assert "/dashboard/settings?" in location
        assert "connector_added=true" in location
        assert f"connector_id={CONNECTOR_ID}" in location
        assert "connector_type=gmail" in location

    def test_failure_goes_to_the_same_page_with_a_code(self) -> None:
        response = connector_error_return(is_native=False, error_code="access_denied")

        location = response.headers["location"]
        assert "/dashboard/settings?" in location
        assert "connector_error=access_denied" in location

    def test_both_redirect_rather_than_render(self) -> None:
        # The provider sent the browser here; anything but a redirect leaves
        # the user looking at raw JSON on an API host.
        assert (
            connector_success_return(
                is_native=False, connector_type="gmail", connector_id=CONNECTOR_ID
            ).status_code
            == 302
        )
        assert connector_error_return(is_native=False, error_code="x").status_code == 302


class TestNativeShell:
    def test_success_comes_home_to_the_app(self) -> None:
        response = connector_success_return(
            is_native=True, connector_type="gmail", connector_id=CONNECTOR_ID
        )

        location = response.headers["location"]
        assert location.startswith("lia://connector-callback?")
        assert "connector_added=true" in location
        assert "connector_type=gmail" in location

    def test_failure_comes_home_too(self) -> None:
        response = connector_error_return(is_native=True, error_code="access_denied")

        location = response.headers["location"]
        # Stranding the user is worse here than on success: there is no
        # connector to find later, and nothing on screen to explain why.
        assert location.startswith("lia://connector-callback?")
        assert "connector_error=access_denied" in location

    def test_the_web_origin_never_appears_in_a_deep_link(self) -> None:
        response = connector_success_return(
            is_native=True, connector_type="gmail", connector_id=CONNECTOR_ID
        )

        # The shell appends the query to ITS OWN server's origin. Carrying an
        # absolute URL would let whoever intercepts the scheme choose where the
        # WebView goes next.
        assert "http" not in response.headers["location"]


class TestTheQueryIsTheSameOnBothSurfaces:
    @pytest.mark.parametrize("field", ["connector_added=true", "connector_type=gmail"])
    def test_success_carries_identical_parameters(self, field: str) -> None:
        web = connector_success_return(
            is_native=False, connector_type="gmail", connector_id=CONNECTOR_ID
        ).headers["location"]
        native = connector_success_return(
            is_native=True, connector_type="gmail", connector_id=CONNECTOR_ID
        ).headers["location"]

        # The settings page reads the same query either way. Letting the two
        # drift would mean the shell shows a different outcome than the web for
        # the same event, and only one of them would ever be tested.
        assert field in web
        assert field in native

    def test_failure_carries_identical_parameters(self) -> None:
        web = connector_error_return(is_native=False, error_code="access_denied").headers[
            "location"
        ]
        native = connector_error_return(is_native=True, error_code="access_denied").headers[
            "location"
        ]

        assert "connector_error=access_denied" in web
        assert "connector_error=access_denied" in native


class TestNativeMeansExplicitlyTrue:
    """A truthy value is not a native flow.

    These callbacks are also called directly by unit tests, where an unfilled
    `Depends(...)` default arrives as the dependency OBJECT rather than a bool —
    and a `Depends` is truthy. Read loosely, every such test, and any future
    direct caller, would take the deep-link path while running in a browser.

    Found by an existing MCP test doing exactly that, which is why the check is
    an identity comparison and why it is pinned here.
    """

    @pytest.mark.parametrize("value", [object(), "yes", 1, [1]])
    def test_only_the_boolean_true_produces_a_deep_link(self, value: object) -> None:
        response = connector_success_return(
            is_native=value,  # type: ignore[arg-type]
            connector_type="gmail",
            connector_id=CONNECTOR_ID,
        )

        assert response.headers["location"].startswith("http")

    def test_and_true_still_does(self) -> None:
        response = connector_success_return(
            is_native=True, connector_type="gmail", connector_id=CONNECTOR_ID
        )

        assert response.headers["location"].startswith("lia://")
