"""What an update does to a personal MCP server's credentials and status (credential_transition).

The rule: a different authentication type starts from nothing; a static secret is required when
the type becomes one; OAuth tokens survive only while the type, the client, the scopes and the
address stay the ones they were issued for; a type change gets the status creation would give.
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

from src.core.constants import MCP_USER_DEFAULT_API_KEY_HEADER
from src.core.exceptions import ValidationError
from src.domains.user_mcp.credential_transition import (
    KEEP_STORED,
    CredentialUpdate,
    awaits_oauth_authorization,
    credential_columns,
    metadata_with_scopes,
    metadata_without_discovery,
    plan_credential_update,
    touches_credentials,
)
from src.domains.user_mcp.models import UserMCPAuthType, UserMCPServer, UserMCPServerStatus

TOKENS = {
    "access_token": "tok-abc",
    "refresh_token": "ref-xyz",
    "expires_at": 1_800_000_000,
    "token_type": "Bearer",
    "scope": "openid profile",
}
CLIENT = {"client_id": "client-1", "client_secret": "secret-1", "issuer": "https://auth.example"}


def _server(
    auth_type: UserMCPAuthType,
    *,
    status: UserMCPServerStatus = UserMCPServerStatus.ACTIVE,
    scopes: str | None = None,
    required_header_name: str | None = None,
) -> UserMCPServer:
    return UserMCPServer(
        id=uuid4(),
        user_id=uuid4(),
        name="Notes",
        url="https://notes.example/mcp",
        auth_type=auth_type.value,
        status=status.value,
        oauth_metadata={"requested_scopes": scopes} if scopes else None,
        required_header_name=required_header_name,
    )


class TestTypeChange:
    """A different authentication type starts from nothing."""

    def test_none_to_oauth_awaits_authorization_with_no_credentials(self) -> None:
        planned = plan_credential_update(
            _server(UserMCPAuthType.NONE), {}, {"auth_type": UserMCPAuthType.OAUTH2}
        )
        assert planned == CredentialUpdate(
            None, UserMCPServerStatus.AUTH_REQUIRED, True, forgets_discovery=True
        )

    def test_api_key_never_becomes_oauth_credentials(self) -> None:
        stored = {"header_name": "X-API-Key", "api_key": "sk-123"}
        planned = plan_credential_update(
            _server(UserMCPAuthType.API_KEY, status=UserMCPServerStatus.ERROR),
            stored,
            {"auth_type": UserMCPAuthType.OAUTH2},
        )
        assert planned.credentials is None
        assert planned.status is UserMCPServerStatus.AUTH_REQUIRED
        assert planned.clears_last_error
        assert planned.forgets_discovery

    def test_oauth_client_given_with_the_switch_is_kept(self) -> None:
        planned = plan_credential_update(
            _server(UserMCPAuthType.NONE),
            {},
            {
                "auth_type": UserMCPAuthType.OAUTH2,
                "oauth_client_id": "client-9",
                "oauth_client_secret": "secret-9",
            },
        )
        assert planned.credentials == {"client_id": "client-9", "client_secret": "secret-9"}
        assert planned.status is UserMCPServerStatus.AUTH_REQUIRED

    def test_oauth_tokens_never_outlive_a_switch_to_api_key(self) -> None:
        planned = plan_credential_update(
            _server(UserMCPAuthType.OAUTH2),
            {**CLIENT, **TOKENS},
            {"auth_type": UserMCPAuthType.API_KEY, "api_key": "sk-new"},
        )
        assert planned.credentials == {
            "header_name": MCP_USER_DEFAULT_API_KEY_HEADER,
            "api_key": "sk-new",
        }
        assert planned.status is UserMCPServerStatus.ACTIVE
        assert planned.clears_last_error

    @pytest.mark.parametrize(
        ("source", "target"),
        [
            (UserMCPAuthType.OAUTH2, UserMCPAuthType.API_KEY),
            (UserMCPAuthType.API_KEY, UserMCPAuthType.BEARER),
            (UserMCPAuthType.BEARER, UserMCPAuthType.API_KEY),
            (UserMCPAuthType.NONE, UserMCPAuthType.BEARER),
        ],
    )
    def test_a_static_type_requires_its_secret(
        self, source: UserMCPAuthType, target: UserMCPAuthType
    ) -> None:
        stored = {"api_key": "sk-123", "token": "tok-123", **TOKENS}
        with pytest.raises(ValidationError):
            plan_credential_update(_server(source), stored, {"auth_type": target})

    def test_switch_to_none_clears_everything(self) -> None:
        planned = plan_credential_update(
            _server(UserMCPAuthType.BEARER, status=UserMCPServerStatus.ERROR),
            {"token": "tok-123"},
            {"auth_type": UserMCPAuthType.NONE},
        )
        assert planned == CredentialUpdate(None, UserMCPServerStatus.ACTIVE, True)

    def test_a_received_copy_keeps_its_required_header(self) -> None:
        planned = plan_credential_update(
            _server(UserMCPAuthType.NONE, required_header_name="X-Service-Key"),
            {},
            {"auth_type": UserMCPAuthType.API_KEY, "api_key": "sk-1"},
        )
        assert planned.credentials == {"header_name": "X-Service-Key", "api_key": "sk-1"}


class TestStaticSameType:
    """An update within a static type merges, and leaves status and verdict alone."""

    def test_header_only_keeps_the_stored_key(self) -> None:
        planned = plan_credential_update(
            _server(UserMCPAuthType.API_KEY, status=UserMCPServerStatus.ERROR),
            {"header_name": "X-API-Key", "api_key": "sk-123"},
            {"header_name": "X-Hf-Token"},
        )
        assert planned == CredentialUpdate(
            {"header_name": "X-Hf-Token", "api_key": "sk-123"}, None, False
        )

    def test_new_key_keeps_the_stored_header(self) -> None:
        planned = plan_credential_update(
            _server(UserMCPAuthType.API_KEY),
            {"header_name": "X-Custom", "api_key": "old"},
            {"api_key": "new"},
        )
        assert planned.credentials == {"header_name": "X-Custom", "api_key": "new"}

    def test_nothing_to_store_keeps_the_stored_ciphertext(self) -> None:
        planned = plan_credential_update(
            _server(UserMCPAuthType.API_KEY), {}, {"header_name": "X-Custom"}
        )
        assert planned == CredentialUpdate(KEEP_STORED, None, False)

    def test_new_bearer_token(self) -> None:
        planned = plan_credential_update(
            _server(UserMCPAuthType.BEARER), {"token": "old"}, {"bearer_token": "new"}
        )
        assert planned == CredentialUpdate({"token": "new"}, None, False)

    def test_unchanged_type_named_again_changes_nothing(self) -> None:
        planned = plan_credential_update(
            _server(UserMCPAuthType.BEARER),
            {"token": "tok"},
            {"auth_type": UserMCPAuthType.BEARER},
        )
        assert planned == CredentialUpdate({"token": "tok"}, None, False)


class TestOAuthSameType:
    """OAuth tokens survive only what they were issued for."""

    def test_a_new_secret_for_the_same_client_keeps_the_tokens(self) -> None:
        planned = plan_credential_update(
            _server(UserMCPAuthType.OAUTH2),
            {**CLIENT, **TOKENS},
            {"oauth_client_secret": "secret-2"},
        )
        assert planned == CredentialUpdate(
            {**CLIENT, **TOKENS, "client_secret": "secret-2"}, None, False
        )

    def test_another_client_drops_tokens_secret_and_issuer(self) -> None:
        planned = plan_credential_update(
            _server(UserMCPAuthType.OAUTH2),
            {**CLIENT, **TOKENS},
            {"oauth_client_id": "client-2"},
        )
        assert planned == CredentialUpdate(
            {"client_id": "client-2"}, UserMCPServerStatus.AUTH_REQUIRED, True
        )

    def test_another_address_keeps_the_client_drops_the_tokens_and_rediscovers(self) -> None:
        planned = plan_credential_update(
            _server(UserMCPAuthType.OAUTH2),
            {**CLIENT, **TOKENS},
            {"url": "https://other.example/mcp"},
        )
        assert planned == CredentialUpdate(
            CLIENT, UserMCPServerStatus.AUTH_REQUIRED, True, forgets_discovery=True
        )

    def test_other_scopes_drop_the_tokens_and_keep_the_discovery(self) -> None:
        planned = plan_credential_update(
            _server(UserMCPAuthType.OAUTH2, scopes="read"),
            {**CLIENT, **TOKENS},
            {"oauth_scopes": "read write"},
        )
        assert planned.credentials == CLIENT
        assert planned.status is UserMCPServerStatus.AUTH_REQUIRED
        assert not planned.forgets_discovery

    def test_the_same_scopes_change_nothing(self) -> None:
        planned = plan_credential_update(
            _server(UserMCPAuthType.OAUTH2, scopes="read"),
            {**CLIENT, **TOKENS},
            {"oauth_scopes": "read"},
        )
        assert planned == CredentialUpdate(KEEP_STORED, None, False)

    def test_the_same_address_changes_nothing(self) -> None:
        server = _server(UserMCPAuthType.OAUTH2)
        planned = plan_credential_update(server, {**CLIENT, **TOKENS}, {"url": server.url})
        assert planned == CredentialUpdate(KEEP_STORED, None, False)

    def test_no_client_left_clears_the_credentials(self) -> None:
        planned = plan_credential_update(
            _server(UserMCPAuthType.OAUTH2),
            dict(TOKENS),
            {"url": "https://other.example/mcp"},
        )
        assert planned == CredentialUpdate(
            None, UserMCPServerStatus.AUTH_REQUIRED, True, forgets_discovery=True
        )


class TestMetadataWithoutDiscovery:
    """A new address forgets the endpoints found for the old one, never the person's scopes."""

    def test_keeps_only_the_requested_scopes(self) -> None:
        stored = {
            "issuer": "https://auth.example",
            "authorization_endpoint": "https://auth.example/authorize",
            "token_endpoint": "https://auth.example/token",
            "requested_scopes": "read write",
        }
        assert metadata_without_discovery(stored) == {"requested_scopes": "read write"}

    @pytest.mark.parametrize("stored", [None, {}, {"token_endpoint": "https://auth.example/token"}])
    def test_nothing_left_is_none(self, stored: dict[str, object] | None) -> None:
        assert metadata_without_discovery(stored) is None


def _seal(plaintext: str) -> str:
    """Stand-in for ``encrypt_data``: the columns must carry what it returns."""
    return f"sealed:{plaintext}"


class TestCredentialColumns:
    """The columns an update writes are the decision, encrypted, and nothing more."""

    def test_switch_to_oauth_awaits_authorization_with_nothing_stored(self) -> None:
        columns = credential_columns(
            _server(UserMCPAuthType.NONE), {}, {"auth_type": UserMCPAuthType.OAUTH2}, encrypt=_seal
        )
        assert columns == {
            "credentials_encrypted": None,
            "status": UserMCPServerStatus.AUTH_REQUIRED.value,
            "last_error": None,
            "auth_type": UserMCPAuthType.OAUTH2.value,
        }

    def test_a_new_secret_is_stored_encrypted(self) -> None:
        columns = credential_columns(
            _server(UserMCPAuthType.API_KEY),
            {"header_name": "X-Key", "api_key": "old"},
            {"api_key": "new"},
            encrypt=_seal,
        )
        assert columns == {
            "credentials_encrypted": _seal(json.dumps({"header_name": "X-Key", "api_key": "new"}))
        }

    def test_nothing_new_to_store_writes_only_the_named_type(self) -> None:
        columns = credential_columns(
            _server(UserMCPAuthType.API_KEY),
            {},
            {"auth_type": UserMCPAuthType.API_KEY},
            encrypt=_seal,
        )
        assert columns == {"auth_type": UserMCPAuthType.API_KEY.value}

    def test_another_address_keeps_the_client_and_the_scopes_only(self) -> None:
        columns = credential_columns(
            _server(UserMCPAuthType.OAUTH2, scopes="read"),
            {**CLIENT, **TOKENS},
            {"url": "https://other.example/mcp"},
            encrypt=_seal,
        )
        assert columns == {
            "credentials_encrypted": _seal(json.dumps(CLIENT)),
            "status": UserMCPServerStatus.AUTH_REQUIRED.value,
            "last_error": None,
            "oauth_metadata": {"requested_scopes": "read"},
        }

    def test_a_server_becoming_oauth_finds_its_discovery_again(self) -> None:
        # Left by an earlier OAuth period, then the address changed under another type: the
        # flow would reuse these endpoints as they stand.
        server = _server(UserMCPAuthType.API_KEY)
        server.oauth_metadata = {
            "issuer": "https://auth.old.example",
            "authorization_endpoint": "https://auth.old.example/authorize",
            "token_endpoint": "https://auth.old.example/token",
            "requested_scopes": "read",
        }
        columns = credential_columns(
            server,
            {"header_name": "X-Key", "api_key": "sk-1"},
            {"auth_type": UserMCPAuthType.OAUTH2},
            encrypt=_seal,
        )
        assert columns["oauth_metadata"] == {"requested_scopes": "read"}
        assert columns["credentials_encrypted"] is None
        assert columns["status"] == UserMCPServerStatus.AUTH_REQUIRED.value

    def test_a_static_type_without_its_secret_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            credential_columns(
                _server(UserMCPAuthType.NONE),
                {},
                {"auth_type": UserMCPAuthType.BEARER},
                encrypt=_seal,
            )


class TestMetadataWithScopes:
    """The person's scopes are set over the metadata in a new dict, or cleared."""

    def test_sets_the_scopes_in_a_new_dict(self) -> None:
        stored = {"issuer": "https://auth.example", "requested_scopes": "read"}
        merged = metadata_with_scopes(stored, "read write")
        assert merged == {"issuer": "https://auth.example", "requested_scopes": "read write"}
        assert merged is not stored
        assert stored["requested_scopes"] == "read"

    def test_none_clears_the_scopes(self) -> None:
        stored = {"issuer": "https://auth.example", "requested_scopes": "read"}
        assert metadata_with_scopes(stored, None) == {"issuer": "https://auth.example"}

    def test_from_nothing(self) -> None:
        assert metadata_with_scopes(None, "read") == {"requested_scopes": "read"}


class TestTouchesCredentials:
    """Which updates run the decision at all."""

    @pytest.mark.parametrize(
        ("auth_type", "update", "expected"),
        [
            (UserMCPAuthType.NONE, {"name": "Renamed"}, False),
            (UserMCPAuthType.API_KEY, {"url": "https://x.example/mcp"}, False),
            (UserMCPAuthType.OAUTH2, {"url": "https://x.example/mcp"}, True),
            (UserMCPAuthType.OAUTH2, {"oauth_scopes": "read"}, True),
            (UserMCPAuthType.OAUTH2, {"timeout_seconds": 60}, False),
            (UserMCPAuthType.NONE, {"auth_type": UserMCPAuthType.NONE}, True),
            (UserMCPAuthType.API_KEY, {"header_name": "X-Key"}, True),
            (
                UserMCPAuthType.NONE,
                {"url": "https://x.example/mcp", "auth_type": UserMCPAuthType.OAUTH2},
                True,
            ),
        ],
    )
    def test_decision_runs_when_credentials_can_change(
        self, auth_type: UserMCPAuthType, update: dict[str, object], expected: bool
    ) -> None:
        assert touches_credentials(_server(auth_type), update) is expected


class TestAwaitsOAuthAuthorization:
    """An OAuth server is reachable only with a token and outside ``auth_required``."""

    @pytest.mark.parametrize(
        ("auth_type", "status", "stored", "expected"),
        [
            (UserMCPAuthType.OAUTH2, UserMCPServerStatus.ERROR, {}, True),
            (UserMCPAuthType.OAUTH2, UserMCPServerStatus.ACTIVE, dict(CLIENT), True),
            (UserMCPAuthType.OAUTH2, UserMCPServerStatus.ACTIVE, {**CLIENT, **TOKENS}, False),
            (
                UserMCPAuthType.OAUTH2,
                UserMCPServerStatus.AUTH_REQUIRED,
                {**CLIENT, **TOKENS},
                True,
            ),
            (UserMCPAuthType.API_KEY, UserMCPServerStatus.ERROR, {}, False),
            (UserMCPAuthType.NONE, UserMCPServerStatus.ACTIVE, {}, False),
        ],
    )
    def test_awaits_authorization(
        self,
        auth_type: UserMCPAuthType,
        status: UserMCPServerStatus,
        stored: dict[str, object],
        expected: bool,
    ) -> None:
        assert awaits_oauth_authorization(_server(auth_type, status=status), stored) is expected
