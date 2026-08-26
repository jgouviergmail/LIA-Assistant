"""
Links that hand control back to a native shell.

The published apps register a custom scheme, and every flow that leaves for a
system browser comes home through it. There are two such flows — provider
sign-in and connector authorization — and they differ only in the host they
address, which is how the shell decides where to put the user.

The hosts are an enum rather than free strings on purpose: the shell has a
matching map, and a value on one side without a counterpart on the other fails
at the worst possible moment — after the user has already left the app, given
the provider their password, and come back to nothing. A guard reads both.

App Links and Universal Links are deliberately not used. They pin domains at
build time, and one published app serves every self-hosted server. The custom
scheme is therefore assumed interceptable, and nothing on it is a credential
by itself: the sign-in code is worthless without the verifier the WebView kept,
and the connector link carries only what the settings page will display.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from urllib.parse import urlencode

from src.core.config import settings


class NativeDeepLinkHost(StrEnum):
    """Where a deep link asks the shell to take the user.

    Attributes:
        AUTH_CALLBACK: A provider sign-in came back; the shell opens the page
            that spends the handoff code.
        CONNECTOR_CALLBACK: A connector was authorized; the shell opens the
            settings page that reports it.
        MCP_CALLBACK: A user-added MCP server was authorized. It lands on the
            same page as a connector, and still gets its own host: the two
            report different outcomes, and a shared host would make the shell's
            map a lie about which flow came home.
    """

    AUTH_CALLBACK = "auth-callback"
    CONNECTOR_CALLBACK = "connector-callback"
    MCP_CALLBACK = "mcp-callback"


def build_deep_link(host: NativeDeepLinkHost, params: Mapping[str, str]) -> str:
    """
    Build a link the shell will intercept.

    Args:
        host: Which flow is coming home.
        params: Query parameters, already meaningful to the destination page.

    Returns:
        A URL on the configured custom scheme.

    Raises:
        ValueError: When no parameters are given. A link with no outcome
            reaches the app looking like a success and leaves the user on a
            page with nothing to say.
    """
    if not params:
        raise ValueError(f"a {host.value} deep link needs at least one parameter")

    return f"{settings.native_app_scheme}://{host.value}?{urlencode(dict(params))}"
