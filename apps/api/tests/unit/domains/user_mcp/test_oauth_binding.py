"""What an OAuth consent is bound to (oauth_binding): the row's type, address, client, scopes.

A consent finished after the row changed must not land on it; one finished on the same row
must, whatever the discovery cached meanwhile (the flow writes it during the consent).
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

from src.core.security.utils import encrypt_data
from src.domains.user_mcp.models import UserMCPAuthType, UserMCPServer, UserMCPServerStatus
from src.domains.user_mcp.oauth_binding import authorization_binding, stored_client_id


def _server(
    *,
    auth_type: UserMCPAuthType = UserMCPAuthType.OAUTH2,
    url: str = "https://notes.example/mcp",
    metadata: dict[str, object] | None = None,
    credentials: str | None = None,
) -> UserMCPServer:
    return UserMCPServer(
        id=uuid4(),
        user_id=uuid4(),
        name="Notes",
        url=url,
        auth_type=auth_type.value,
        status=UserMCPServerStatus.AUTH_REQUIRED.value,
        oauth_metadata=metadata,
        credentials_encrypted=credentials,
    )


BASE = authorization_binding(_server(metadata={"requested_scopes": "read"}), "client-1")


class TestAuthorizationBinding:
    def test_the_same_row_has_the_same_binding_whatever_its_discovery(self) -> None:
        discovered = {
            "requested_scopes": "read",
            "issuer": "https://auth.example",
            "token_endpoint": "https://auth.example/token",
        }
        assert authorization_binding(_server(metadata=discovered), "client-1") == BASE

    @pytest.mark.parametrize(
        ("server", "client"),
        [
            (
                _server(auth_type=UserMCPAuthType.API_KEY, metadata={"requested_scopes": "read"}),
                "client-1",
            ),
            (
                _server(url="https://other.example/mcp", metadata={"requested_scopes": "read"}),
                "client-1",
            ),
            (_server(metadata={"requested_scopes": "read"}), "client-2"),
            (_server(metadata={"requested_scopes": "read write"}), "client-1"),
        ],
        ids=["type", "address", "client", "scopes"],
    )
    def test_any_change_the_consent_depends_on_changes_it(
        self, server: UserMCPServer, client: str
    ) -> None:
        assert authorization_binding(server, client) != BASE

    def test_no_scopes_and_no_client_read_alike_however_spelled(self) -> None:
        assert authorization_binding(_server(metadata={"requested_scopes": ""}), "") == (
            authorization_binding(_server(metadata=None), None)
        )


class TestStoredClientId:
    def test_reads_the_stored_client(self) -> None:
        sealed = encrypt_data(json.dumps({"client_id": "client-1", "access_token": "tok"}))
        assert stored_client_id(_server(credentials=sealed)) == "client-1"

    @pytest.mark.parametrize(
        "credentials",
        [None, encrypt_data(json.dumps({"access_token": "tok"})), "not-a-ciphertext"],
        ids=["absent", "no-client", "unreadable"],
    )
    def test_no_readable_client_is_none(self, credentials: str | None) -> None:
        assert stored_client_id(_server(credentials=credentials)) is None
