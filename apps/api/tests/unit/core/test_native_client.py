"""Knowing that a request came from a native shell.

An OAuth flow started in a shell must come back to the shell. The callback
learns that from the flow's stored state, and the state is written by
``OAuthFlowHandler.initiate_flow`` — which has no ``Request`` to read a header
from, and is reached through twelve different service methods.

Threading a boolean through those twelve would be twelve chances to forget one,
and forgetting one is silent: that single connector strands its user in a
browser the app cannot reach. So the fact travels as request-scoped context,
the way the codebase already carries per-request values that must not become
attributes on a shared object.

What matters, and what is pinned here: the default is FALSE. A missing header,
an unrecognised value, a background task with no request at all — every one of
them must read as "a browser", because sending a browser user to a `lia://`
link shows them nothing at all.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from src.core.native_client import (
    NATIVE_CLIENT_HEADER,
    detect_native_client,
    is_native_client,
    native_client_scope,
)

pytestmark = pytest.mark.unit


def _request(headers: dict[str, str] | None = None) -> Mock:
    request = Mock()
    request.headers = headers or {}
    return request


class TestDefault:
    def test_nothing_declared_means_a_browser(self) -> None:
        assert is_native_client() is False

    async def test_a_request_without_the_header_is_a_browser(self) -> None:
        await detect_native_client(_request())

        assert is_native_client() is False

    @pytest.mark.parametrize("value", ["", "0", "false", "no", "maybe"])
    async def test_anything_but_an_affirmative_is_a_browser(self, value: str) -> None:
        await detect_native_client(_request({NATIVE_CLIENT_HEADER: value}))

        # Fail towards the browser: a `lia://` redirect shows a browser user
        # nothing at all, while a web redirect merely inconveniences a shell.
        assert is_native_client() is False


class TestDetection:
    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "True"])
    async def test_an_affirmative_header_is_a_shell(self, value: str) -> None:
        with native_client_scope(False):
            await detect_native_client(_request({NATIVE_CLIENT_HEADER: value}))

            assert is_native_client() is True

    async def test_the_header_name_is_case_insensitive(self) -> None:
        # Starlette lowercases header names; a Mock does not, so this pins the
        # lookup rather than the framework.
        with native_client_scope(False):
            await detect_native_client(_request({NATIVE_CLIENT_HEADER.lower(): "1"}))

            assert is_native_client() is True


class TestIsolation:
    async def test_one_request_does_not_leak_into_the_next(self) -> None:
        with native_client_scope(True):
            assert is_native_client() is True

        # A singleton attribute would have carried this to the next user's
        # request; a context variable cannot.
        assert is_native_client() is False

    def test_the_scope_restores_what_it_found(self) -> None:
        with native_client_scope(True):
            with native_client_scope(False):
                assert is_native_client() is False
            assert is_native_client() is True
