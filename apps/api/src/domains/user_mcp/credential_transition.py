"""What an update of a personal MCP server does to its credentials and its status.

One decision for every writer of ``UserMCPServerService.update_server``, the settings form
and the assistant's private form alike (2026-11-13):

- A different authentication type starts from nothing: no secret of the previous type is
  carried over (an API key never becomes OAuth credentials, OAuth tokens never outlive the
  switch), and a static secret is required when the type becomes one.
- An OAuth server keeps its tokens only while the type, the client, the requested scopes and
  the address they were issued for stay the same. Otherwise it keeps its client registration
  (unless the client itself changes) and awaits a new authorization, as a server created
  with OAuth does.
- The discovery cached in ``oauth_metadata`` (endpoints and issuer) is found again when an
  OAuth server gets a new address, and when a server becomes OAuth: the address may have
  changed while it used another type, and the flow reuses a cached discovery as it stands.
  The scopes the person asked for stay.
- A server whose type changes gets the status creation would give it (``auth_required`` for
  OAuth, ``active`` otherwise), and an OAuth server awaiting a new authorization gets
  ``auth_required``. Either way the verdict of a previous test (``last_error``), which was
  about the credentials it tested, goes with them. Any other update leaves both as they are.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final

from src.core.constants import MCP_USER_DEFAULT_API_KEY_HEADER
from src.core.exceptions import ValidationError
from src.domains.user_mcp.models import UserMCPAuthType, UserMCPServer, UserMCPServerStatus

#: Update fields that can change what a server authenticates with, whatever its type.
CREDENTIAL_UPDATE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "auth_type",
        "api_key",
        "header_name",
        "bearer_token",
        "oauth_client_id",
        "oauth_client_secret",
    }
)
#: Update fields that invalidate OAuth tokens: they were issued for one address and scopes.
_OAUTH_GRANT_FIELDS: Final[frozenset[str]] = frozenset({"url", "oauth_scopes"})
#: What an OAuth client registration is; anything else in the blob was granted to it.
_OAUTH_CLIENT_FIELDS: Final[tuple[str, ...]] = ("client_id", "client_secret", "issuer")
#: Where an update's client fields are stored in the credentials blob.
_OAUTH_CLIENT_UPDATE_FIELDS: Final[tuple[tuple[str, str], ...]] = (
    ("client_id", "oauth_client_id"),
    ("client_secret", "oauth_client_secret"),
)


class _KeepStored:
    """Sentinel type: the stored ciphertext is left untouched."""


#: The update has nothing new to store: keep the ciphertext as it is (even unreadable).
KEEP_STORED: Final = _KeepStored()


@dataclass(frozen=True, slots=True)
class CredentialUpdate:
    """The decided effect of an update on a server's credentials.

    Attributes:
        credentials: Plaintext credentials to encrypt and store, ``None`` to clear them, or
            ``KEEP_STORED`` to leave the stored ciphertext untouched.
        status: The status to store, or ``None`` to leave the stored one.
        clears_last_error: Whether the previous test verdict no longer applies.
        forgets_discovery: Whether the cached OAuth discovery (endpoints, issuer) may belong
            to another address and must be found again; the requested scopes stay.
    """

    credentials: dict[str, object] | None | _KeepStored
    status: UserMCPServerStatus | None
    clears_last_error: bool
    forgets_discovery: bool = False


def touches_credentials(server: UserMCPServer, update_data: Mapping[str, object]) -> bool:
    """Whether an update can change what the server authenticates with.

    Args:
        server: The stored server row.
        update_data: The fields the update sets (``model_dump(exclude_unset=True)``).

    Returns:
        True when the credential decision must run for this update.
    """
    if CREDENTIAL_UPDATE_FIELDS & update_data.keys():
        return True
    return _target_type(server, update_data) is UserMCPAuthType.OAUTH2 and bool(
        _OAUTH_GRANT_FIELDS & update_data.keys()
    )


def plan_credential_update(
    server: UserMCPServer,
    stored: Mapping[str, object],
    update_data: Mapping[str, object],
) -> CredentialUpdate:
    """Decide what an update does to the credentials and the status of a server.

    Args:
        server: The stored server row (its type, address, status and OAuth metadata).
        stored: The decrypted stored credentials (empty when absent or unreadable).
        update_data: The fields the update sets (``model_dump(exclude_unset=True)``).

    Returns:
        The credentials, status and test verdict to store.

    Raises:
        ValidationError: When the type becomes a static secret type without its secret.
    """
    target = _target_type(server, update_data)
    type_changed = target.value != server.auth_type
    previous: Mapping[str, object] = {} if type_changed else stored
    if target is UserMCPAuthType.OAUTH2:
        return _oauth_update(server, previous, update_data, type_changed=type_changed)
    status = UserMCPServerStatus.ACTIVE if type_changed else None
    if target is UserMCPAuthType.NONE:
        return CredentialUpdate(None, status, clears_last_error=type_changed)
    credentials = _static_credentials(server, target, previous, update_data)
    if credentials is None:
        if type_changed:
            raise ValidationError(
                f"Switching a server to '{target.value}' authentication requires its secret"
            )
        return CredentialUpdate(KEEP_STORED, None, clears_last_error=False)
    return CredentialUpdate(credentials, status, clears_last_error=type_changed)


def awaits_oauth_authorization(server: UserMCPServer, stored: Mapping[str, object]) -> bool:
    """Whether an OAuth server can only be reached after the person authorizes it.

    Args:
        server: The stored server row.
        stored: The decrypted stored credentials (empty when absent or unreadable).

    Returns:
        True for an OAuth server marked ``auth_required`` or holding no access token.
    """
    if server.auth_type != UserMCPAuthType.OAUTH2.value:
        return False
    return server.status == UserMCPServerStatus.AUTH_REQUIRED.value or not stored.get(
        "access_token"
    )


def metadata_without_discovery(metadata: Mapping[str, object] | None) -> dict[str, object] | None:
    """The OAuth metadata a server keeps when its discovery must be found again.

    The endpoints and the issuer were discovered from the previous address; the scopes
    the person asked for are theirs and stay.

    Args:
        metadata: The stored ``oauth_metadata``.

    Returns:
        A new dict holding only ``requested_scopes``, or ``None`` when there are none.
    """
    scopes = (metadata or {}).get("requested_scopes")
    return {"requested_scopes": scopes} if scopes else None


def credential_columns(
    server: UserMCPServer,
    stored: Mapping[str, object],
    update_data: Mapping[str, object],
    *,
    encrypt: Callable[[str], str],
) -> dict[str, object]:
    """The columns an update writes for what it does to the credentials and the status.

    Args:
        server: The stored server row.
        stored: The decrypted stored credentials (empty when absent or unreadable).
        update_data: The fields the update sets (``model_dump(exclude_unset=True)``).
        encrypt: How a plaintext credentials blob is stored (``encrypt_data``).

    Returns:
        A new dict of column values to merge into the update: ``credentials_encrypted``
        unless the stored ciphertext stays, ``status`` and ``last_error`` when they change,
        ``oauth_metadata`` when a cached discovery must be found again, ``auth_type`` when
        named.

    Raises:
        ValidationError: When the type becomes a static secret type without its secret.
    """
    planned = plan_credential_update(server, stored, update_data)
    columns: dict[str, object] = {}
    if planned.credentials is not KEEP_STORED:
        columns["credentials_encrypted"] = (
            encrypt(json.dumps(planned.credentials)) if planned.credentials else None
        )
    if planned.status is not None:
        columns["status"] = planned.status.value
    if planned.clears_last_error:
        columns["last_error"] = None
    if planned.forgets_discovery and server.oauth_metadata:
        columns["oauth_metadata"] = metadata_without_discovery(server.oauth_metadata)
    if "auth_type" in update_data:
        columns["auth_type"] = _target_type(server, update_data).value
    return columns


def metadata_with_scopes(
    metadata: Mapping[str, object] | None, scopes: object
) -> dict[str, object]:
    """The OAuth metadata once the person sets the scopes they ask for.

    Args:
        metadata: The OAuth metadata the update starts from (stored, or already decided).
        scopes: The requested scopes; ``None`` clears them.

    Returns:
        A new dict (a JSONB column is never mutated in place).
    """
    merged = dict(metadata or {})
    if scopes is None:
        merged.pop("requested_scopes", None)
    else:
        merged["requested_scopes"] = scopes
    return merged


def _target_type(server: UserMCPServer, update_data: Mapping[str, object]) -> UserMCPAuthType:
    return UserMCPAuthType(update_data.get("auth_type") or server.auth_type)


def _static_credentials(
    server: UserMCPServer,
    target: UserMCPAuthType,
    previous: Mapping[str, object],
    update_data: Mapping[str, object],
) -> dict[str, object] | None:
    if target is UserMCPAuthType.BEARER:
        token = update_data.get("bearer_token") or previous.get("token")
        return {"token": token} if token else None
    api_key = update_data.get("api_key") or previous.get("api_key")
    if not api_key:
        return None
    header_name = (
        update_data.get("header_name")
        or previous.get("header_name")
        or server.required_header_name
        or MCP_USER_DEFAULT_API_KEY_HEADER
    )
    return {"header_name": header_name, "api_key": api_key}


def _oauth_update(
    server: UserMCPServer,
    previous: Mapping[str, object],
    update_data: Mapping[str, object],
    *,
    type_changed: bool,
) -> CredentialUpdate:
    client_changed = _client_changed(previous, update_data)
    url_changed = _url_changed(server, update_data)
    if not (type_changed or client_changed or url_changed or _scopes_changed(server, update_data)):
        return _same_grant_update(previous, update_data)
    client = _registration(previous, update_data, keep=not client_changed)
    return CredentialUpdate(
        client or None,
        UserMCPServerStatus.AUTH_REQUIRED,
        clears_last_error=True,
        forgets_discovery=url_changed or type_changed,
    )


def _client_changed(previous: Mapping[str, object], update_data: Mapping[str, object]) -> bool:
    new_client = update_data.get("oauth_client_id")
    return bool(new_client) and new_client != previous.get("client_id")


def _url_changed(server: UserMCPServer, update_data: Mapping[str, object]) -> bool:
    return "url" in update_data and update_data["url"] != server.url


def _scopes_changed(server: UserMCPServer, update_data: Mapping[str, object]) -> bool:
    if "oauth_scopes" not in update_data:
        return False
    stored_scopes = (server.oauth_metadata or {}).get("requested_scopes") or None
    return (update_data["oauth_scopes"] or None) != stored_scopes


def _same_grant_update(
    previous: Mapping[str, object], update_data: Mapping[str, object]
) -> CredentialUpdate:
    """The tokens still apply: only a new client secret is stored beside them."""
    new_secret = update_data.get("oauth_client_secret")
    if not new_secret:
        return CredentialUpdate(KEEP_STORED, None, clears_last_error=False)
    return CredentialUpdate(
        {**previous, "client_secret": new_secret}, None, clears_last_error=False
    )


def _registration(
    previous: Mapping[str, object], update_data: Mapping[str, object], *, keep: bool
) -> dict[str, object]:
    """The client registration a new authorization starts from (the update's values win)."""
    client = {
        field: previous[field] for field in _OAUTH_CLIENT_FIELDS if keep and previous.get(field)
    }
    for stored_key, update_field in _OAUTH_CLIENT_UPDATE_FIELDS:
        if update_data.get(update_field):
            client[stored_key] = update_data[update_field]
    return client
