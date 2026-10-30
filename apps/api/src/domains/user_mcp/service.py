"""
User MCP Server service for business logic.

Handles CRUD operations, credential encryption, ownership checks,
and pool coordination for per-user MCP servers.

Phase: evolution F2.1 — MCP Per-User
Created: 2026-02-28
"""

import json
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import MCP_USER_DEFAULT_API_KEY_HEADER
from src.core.exceptions import ResourceNotFoundError, ValidationError
from src.core.security.utils import decrypt_data, encrypt_data
from src.domains.user_mcp.description_generation import generate_domain_description
from src.domains.user_mcp.installation import OfflineMCPInstallation, check_creation_constraints
from src.domains.user_mcp.models import (
    UserMCPAuthType,
    UserMCPServer,
    UserMCPServerStatus,
)
from src.domains.user_mcp.repository import UserMCPServerRepository
from src.domains.user_mcp.response_metadata import build_response_metadata
from src.domains.user_mcp.schemas import UserMCPServerCreate, UserMCPServerUpdate
from src.infrastructure.mcp.security import validate_http_endpoint
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class UserMCPServerService:
    """Service for user MCP server management business logic."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repository = UserMCPServerRepository(db)

    async def get_with_ownership_check(
        self,
        server_id: UUID,
        user_id: UUID,
    ) -> UserMCPServer:
        """
        Get MCP server with ownership verification.

        Raises:
            ResourceNotFoundError: If server doesn't exist or belongs to another user.
        """
        server = await self.repository.get_by_id(server_id)
        if not server or server.user_id != user_id:
            raise ResourceNotFoundError("user_mcp_server", str(server_id))
        return server

    async def list_servers(self, user_id: UUID) -> list[UserMCPServer]:
        """List all MCP servers for a user."""
        return await self.repository.get_all_for_user(user_id)

    async def create_server(
        self,
        user_id: UUID,
        data: UserMCPServerCreate,
        *,
        plugin_id: UUID | None = None,
        extra_headers: dict[str, str] | None = None,
        before_write: Callable[[AsyncSession], Awaitable[None]] | None = None,
        offline_install: OfflineMCPInstallation | None = None,
    ) -> UserMCPServer:
        """
        Create a new user MCP server.

        Validates URL (SSRF prevention), enforces per-user limit,
        and encrypts credentials.

        Args:
            user_id: Owner of the server.
            data: Creation payload (public API schema).
            plugin_id: Agent Plugins provenance (ADR-225); None = manual.
            extra_headers: Fixed non-secret HTTP headers from a plugin's
                mcp.json (§7.2.1) — never settable through the public API.

        Raises:
            ValidationError: If user has reached the maximum limit or URL is invalid.
        """
        await self._check_creation_constraints(user_id, data.name)

        await self._validate_creation_endpoint(data.url, offline_install)

        # Build encrypted credentials
        credentials_encrypted = self._encrypt_credentials(data) if offline_install is None else None
        auth_type = offline_install.auth_type if offline_install else data.auth_type

        # Determine initial status
        initial_status = (
            UserMCPServerStatus.AUTH_REQUIRED.value
            if auth_type == UserMCPAuthType.OAUTH2
            else UserMCPServerStatus.ACTIVE.value
        )
        if offline_install is not None:
            initial_status = offline_install.status

        # Store OAuth scopes in oauth_metadata if provided
        oauth_metadata = None
        oauth_scopes = offline_install.oauth_scopes if offline_install else data.oauth_scopes
        if auth_type == UserMCPAuthType.OAUTH2 and oauth_scopes:
            oauth_metadata = {"requested_scopes": oauth_scopes}

        # DNS/network validation precedes the shared account lock. The early
        # checks above are only a fast refusal, never the final quota decision.
        await self.repository.lock_owner_for_creation(user_id)
        if before_write is not None:
            await before_write(self.db)
        await self._check_creation_constraints(user_id, data.name)
        server = await self.repository.create(
            {
                "user_id": user_id,
                "name": data.name,
                "url": data.url,
                "auth_type": auth_type.value,
                "credentials_encrypted": credentials_encrypted,
                "oauth_metadata": oauth_metadata,
                "status": initial_status,
                "is_enabled": offline_install is None,
                "domain_description": data.domain_description,
                "timeout_seconds": data.timeout_seconds,
                "hitl_required": (data.hitl_required if offline_install is None else None),
                "iterative_mode": data.iterative_mode,
                "plugin_id": plugin_id,
                "extra_headers": extra_headers,
                "required_header_name": (
                    offline_install.credential_header if offline_install else None
                ),
            }
        )

        logger.info(
            "user_mcp_server_created",
            server_id=str(server.id),
            user_id=str(user_id),
            name=data.name,
            auth_type=auth_type.value,
            status=initial_status,
        )

        return server

    async def _validate_creation_endpoint(
        self, url: str, offline: OfflineMCPInstallation | None
    ) -> None:
        if offline is not None and offline.endpoint is not None and offline.endpoint.url == url:
            return
        is_valid, error_msg = await validate_http_endpoint(url)
        if not is_valid:
            raise ValidationError(f"Invalid MCP server URL: {error_msg}")

    async def _check_creation_constraints(self, user_id: UUID, name: str) -> None:
        await check_creation_constraints(self.repository, user_id, name)

    async def update_server(
        self,
        server_id: UUID,
        user_id: UUID,
        data: UserMCPServerUpdate,
        *,
        before_write: Callable[[AsyncSession], Awaitable[None]] | None = None,
    ) -> UserMCPServer:
        """
        Update a user MCP server.

        If URL or credentials change, disconnects from pool to force reconnection.

        Raises:
            ResourceNotFoundError: If server not found or wrong owner.
        """
        server = await self.get_with_ownership_check(server_id, user_id)

        update_data = data.model_dump(exclude_unset=True)
        if not update_data:
            return server

        # Check name uniqueness if name is being changed
        if "name" in update_data and update_data["name"] != server.name:
            existing = await self.repository.get_by_name_for_user(user_id, update_data["name"])
            if existing:
                raise ValidationError(f"An MCP server named '{update_data['name']}' already exists")

        # Track if connection-affecting fields changed
        needs_reconnect = False

        # Validate new URL if provided
        if "url" in update_data:
            is_valid, error_msg = await validate_http_endpoint(update_data["url"])
            if not is_valid:
                raise ValidationError(f"Invalid MCP server URL: {error_msg}")
            needs_reconnect = True

        # Handle credential updates
        credential_fields = {
            "api_key",
            "header_name",
            "bearer_token",
            "auth_type",
            "oauth_client_id",
            "oauth_client_secret",
        }
        if credential_fields & set(update_data.keys()):
            needs_reconnect = True

            # Re-encrypt credentials if auth-related fields changed
            auth_type = update_data.get("auth_type", server.auth_type)
            if isinstance(auth_type, UserMCPAuthType):
                auth_type = auth_type.value

            credentials_encrypted = self._encrypt_credentials_from_update(
                update_data, auth_type, server
            )
            update_data["credentials_encrypted"] = credentials_encrypted

            if "auth_type" in update_data:
                update_data["auth_type"] = auth_type

        # Handle OAuth scopes update (stored in oauth_metadata JSONB)
        if "oauth_scopes" in update_data:
            oauth_scopes = update_data.pop("oauth_scopes")
            current_meta = dict(server.oauth_metadata or {})
            if oauth_scopes is not None:
                current_meta["requested_scopes"] = oauth_scopes
            else:
                # Explicitly clear scopes when set to None
                current_meta.pop("requested_scopes", None)
            update_data["oauth_metadata"] = current_meta
            needs_reconnect = True

        # Remove credential fields from update_data (not in model)
        for field in (
            "api_key",
            "header_name",
            "bearer_token",
            "oauth_client_id",
            "oauth_client_secret",
        ):
            update_data.pop(field, None)

        if before_write is not None:
            await before_write(self.db)
        server = await self.repository.update(server, update_data)

        # Disconnect from pool if connection-affecting fields changed
        if needs_reconnect:
            await self._disconnect_from_pool(user_id, server_id)

        logger.info(
            "user_mcp_server_updated",
            server_id=str(server_id),
            user_id=str(user_id),
            updated_fields=list(update_data.keys()),
            needs_reconnect=needs_reconnect,
        )

        return server

    async def delete_server(
        self,
        server_id: UUID,
        user_id: UUID,
        *,
        allow_plugin_owned: bool = False,
        before_write: Callable[[AsyncSession], Awaitable[None]] | None = None,
    ) -> None:
        """
        Delete a user MCP server.

        Disconnects from pool BEFORE database deletion.

        Args:
            server_id: Server to delete.
            user_id: Requesting owner.
            allow_plugin_owned: True only for the plugin group uninstall
                (ADR-225 arbitrage F) — individual deletion of a plugin's
                server is refused so the plugin never gets silently amputated.

        Raises:
            ResourceNotFoundError: If server not found or wrong owner.
            ValidationError: If the server belongs to an installed plugin and
                the caller is not the group uninstall.
        """
        server = await self.get_with_ownership_check(server_id, user_id)

        if server.plugin_id is not None and not allow_plugin_owned:
            # ADR-225 arbitrage F: a plugin's server leaves through the plugin
            # uninstall — never silently amputate an installed plugin.
            raise ValidationError(
                f"The MCP server '{server.name}' belongs to an installed "
                "plugin — uninstall the plugin instead"
            )

        # Disconnect from pool first (releases MCP session)
        await self._disconnect_from_pool(user_id, server_id)

        if before_write is not None:
            await before_write(self.db)
        await self.repository.delete(server)

        logger.info(
            "user_mcp_server_deleted",
            server_id=str(server_id),
            user_id=str(user_id),
        )

    async def toggle_server(
        self,
        server_id: UUID,
        user_id: UUID,
        *,
        enabled: bool | None = None,
        before_write: Callable[[AsyncSession], Awaitable[None]] | None = None,
    ) -> UserMCPServer:
        """
        Toggle is_enabled for an MCP server.

        When disabling, disconnects from pool.

        Raises:
            ResourceNotFoundError: If server not found or wrong owner.
        """
        server = await self.get_with_ownership_check(server_id, user_id)

        new_enabled = not server.is_enabled if enabled is None else enabled
        if new_enabled and server.status != UserMCPServerStatus.ACTIVE.value:
            raise ValidationError("user_mcp_validation_required")
        update_data: dict = {"is_enabled": new_enabled}

        if not new_enabled:
            # Disabling: disconnect from pool
            await self._disconnect_from_pool(user_id, server_id)

        if before_write is not None:
            await before_write(self.db)
        server = await self.repository.update(server, update_data)

        logger.info(
            "user_mcp_server_toggled",
            server_id=str(server_id),
            user_id=str(user_id),
            is_enabled=new_enabled,
        )

        return server

    async def disconnect_oauth(
        self,
        server_id: UUID,
        user_id: UUID,
        *,
        before_write: Callable[[AsyncSession], Awaitable[None]] | None = None,
    ) -> UserMCPServer:
        """
        Disconnect OAuth: purge tokens while preserving client credentials.

        Clears access_token, refresh_token, etc. from the encrypted credentials
        blob, sets status to auth_required, and disconnects from pool.

        Raises:
            ResourceNotFoundError: If server not found or wrong owner.
            ValidationError: If server auth_type is not oauth2.
        """
        server = await self.get_with_ownership_check(server_id, user_id)

        if server.auth_type != UserMCPAuthType.OAUTH2.value:
            raise ValidationError("Server auth_type must be 'oauth2' to disconnect OAuth")

        # Decrypt, strip tokens, keep client credentials
        existing = self._decrypt_existing_credentials(server)
        client_creds: dict = {}
        if existing.get("client_id"):
            client_creds["client_id"] = existing["client_id"]
        if existing.get("client_secret"):
            client_creds["client_secret"] = existing["client_secret"]

        # Re-encrypt with only client credentials (or None if no client creds)
        credentials_encrypted = encrypt_data(json.dumps(client_creds)) if client_creds else None

        if before_write is not None:
            await before_write(self.db)
        server = await self.repository.update(
            server,
            {
                "credentials_encrypted": credentials_encrypted,
                "status": UserMCPServerStatus.AUTH_REQUIRED.value,
            },
        )

        # Disconnect from pool to invalidate cached sessions
        await self._disconnect_from_pool(user_id, server_id, strict=before_write is not None)

        logger.info(
            "user_mcp_oauth_disconnected",
            server_id=str(server_id),
            user_id=str(user_id),
            had_client_credentials=bool(client_creds),
        )

        return server

    async def test_connection(
        self,
        server_id: UUID,
        user_id: UUID,
        *,
        before_connect: Callable[[AsyncSession], Awaitable[None]] | None = None,
        before_write: Callable[[AsyncSession], Awaitable[None]] | None = None,
    ) -> dict:
        """Test connection to a user MCP server and discover tools.

        Handles pool access, tool discovery, embedding computation,
        and status updates.

        Returns:
            Dict with keys: success, tools (list[dict]), tool_count, error (str|None).

        Raises:
            ResourceNotFoundError: If server not found or wrong owner.
        """
        server = await self.get_with_ownership_check(server_id, user_id)

        from src.infrastructure.mcp.auth import build_auth_for_server
        from src.infrastructure.mcp.user_pool import get_user_mcp_pool

        pool = get_user_mcp_pool()
        if pool is None:
            return {
                "success": False,
                "tools": [],
                "tool_count": 0,
                "error": "MCP user pool not initialized",
            }

        if before_connect is not None:
            await before_connect(self.db)

        from src.domains.user_mcp.catalogue_publication import probe_update_data

        try:
            auth = build_auth_for_server(server)
            entry = await pool.get_or_connect(
                user_id=user_id,
                server_id=server.id,
                url=server.url,
                auth=auth,
                timeout_seconds=server.timeout_seconds,
                extra_headers=server.extra_headers,
                force_refresh=True,
            )

            # One update: status, the version-2 snapshot, description and vectors.
            # The pool reserved the generation BEFORE the discovery: a slower,
            # older one never overwrites it.
            update_data = await probe_update_data(
                self, server, entry, user_id=user_id, generation=entry.generation
            )

            logger.info(
                "user_mcp_server_test_success",
                user_id=str(user_id),
                server_id=str(server_id),
                tool_count=len(entry.tools),
            )

            result = {
                "success": True,
                "tools": entry.tools,
                "tool_count": len(entry.tools),
                "error": None,
                "domain_description": update_data.get(
                    "domain_description", server.domain_description
                ),
            }

        except Exception as e:
            update_data = {
                "status": UserMCPServerStatus.ERROR.value,
                "last_error": str(e),
            }
            logger.warning(
                "user_mcp_server_test_failed",
                user_id=str(user_id),
                server_id=str(server_id),
                error_type=type(e).__name__,
            )

            # Sanitize: only expose exception type, not internal details
            result = {
                "success": False,
                "tools": [],
                "tool_count": 0,
                "error": f"Connection failed: {type(e).__name__}",
            }

        # Fresh authority/CAS failures must propagate, including failed probes.
        if before_write is not None:
            await before_write(self.db)
        try:
            await self.repository.update(server, update_data)
        except Exception as error:
            if before_write is not None:
                raise
            logger.warning("user_mcp_probe_persistence_failed", server_id=str(server_id))
            return {
                "success": False,
                "tools": [],
                "tool_count": 0,
                "error": f"Connection failed: {type(error).__name__}",
            }
        return result

    async def generate_description(
        self,
        server_id: UUID,
        user_id: UUID,
        *,
        before_generate: Callable[[AsyncSession], Awaitable[None]] | None = None,
        before_write: Callable[[AsyncSession], Awaitable[None]] | None = None,
    ) -> dict:
        """Force-(re)generate domain_description from cached discovered tools.

        Uses the tool cache from the last test_connection() — no network call
        to the MCP server.  An LLM call generates an intelligent, routing-
        optimized description.  Overwrites any existing description.

        Returns:
            Dict with keys: domain_description (str), tool_count (int).

        Raises:
            ResourceNotFoundError: If server not found or wrong owner.
            ValidationError: If no tools cache available.
        """
        server = await self.get_with_ownership_check(server_id, user_id)

        from src.infrastructure.mcp.catalogue_snapshot import parse_catalogue_snapshot

        # Every shape the column ever held (snapshot, legacy list or dict), one parser.
        tool_list = [dict(t) for t in parse_catalogue_snapshot(server.discovered_tools_cache).tools]
        if not tool_list:
            raise ValidationError("No tools discovered yet — test connection first")

        server_name, account_scoped, server_owner = (
            server.name,
            server.auth_type != UserMCPAuthType.NONE.value,
            server.user_id,
        )
        if before_generate is not None:
            await before_generate(self.db)
        generated_desc = await self._llm_generate_description(
            tool_list=tool_list,
            server_name=server_name,
            account_scoped=account_scoped,
            user_id=server_owner,
        )

        # Persist (overwrite any existing description)
        if before_write is not None:
            await before_write(self.db)
        await self.repository.update(server, {"domain_description": generated_desc})

        logger.info(
            "user_mcp_description_generated",
            server_id=str(server_id),
            user_id=str(user_id),
            description_length=len(generated_desc),
        )

        return {
            "domain_description": generated_desc,
            "tool_count": len(tool_list),
        }

    # ------------------------------------------------------------------
    # LLM-based domain description generation
    # ------------------------------------------------------------------

    async def _llm_generate_description(
        self,
        tool_list: list[dict],
        server_name: str,
        account_scoped: bool = False,
        user_id: UUID | None = None,
    ) -> str:
        """Describe this server for the router (see ``description_generation``).

        Args:
            tool_list: Discovered tools.
            server_name: Human-readable server name.
            account_scoped: True when the credential is the user's own.
            user_id: Account to bill the generation to.

        Returns:
            The generated domain description.
        """
        return await generate_domain_description(
            tool_list=tool_list,
            server_name=server_name,
            account_scoped=account_scoped,
            user_id=user_id,
        )

    async def cache_oauth_metadata(
        self,
        server: UserMCPServer,
        metadata: dict,
    ) -> None:
        """Cache OAuth authorization server metadata for future flows."""
        await self.repository.update(server, {"oauth_metadata": metadata})

    async def update_tool_embeddings(
        self,
        server_id: UUID,
        user_id: UUID,
        embeddings: dict,
    ) -> None:
        """Update pre-computed E5 tool embeddings cache for a server."""
        server = await self.get_with_ownership_check(server_id, user_id)
        await self.repository.update(server, {"tool_embeddings_cache": embeddings})

    async def set_owned_oauth_credentials(
        self,
        server_id: UUID,
        user_id: UUID,
        encrypted_creds: str,
        *,
        before_write: Callable[[AsyncSession], Awaitable[None]] | None = None,
    ) -> UserMCPServer:
        """Persist under the caller's transaction and optional fresh authority/CAS guard."""
        from src.domains.user_mcp.oauth_credentials import persist_oauth_credentials

        server = await self.get_with_ownership_check(server_id, user_id)
        if before_write is not None:
            await before_write(self.db)
        await persist_oauth_credentials(self.repository, server, encrypted_creds)
        return server

    @staticmethod
    async def update_oauth_credentials(
        server_id: UUID,
        encrypted_creds: str,
    ) -> None:
        """
        Update OAuth credentials for a server (called by MCPOAuth2Auth callbacks).

        Uses its own DB session (not request-scoped) for async OAuth callbacks.
        """
        from src.domains.user_mcp.oauth_credentials import persist_oauth_credentials
        from src.infrastructure.database.session import get_db_context

        async with get_db_context() as db:
            repo = UserMCPServerRepository(db)
            server = await repo.get_by_id(server_id)
            if server:
                await persist_oauth_credentials(repo, server, encrypted_creds)
                # Note: no explicit commit — get_db_context() auto-commits on exit

    @staticmethod
    async def mark_auth_required(server_id: UUID) -> None:
        """
        Mark a server as requiring re-authentication (OAuth token expired).

        Uses its own DB session for async callbacks.
        """
        from src.infrastructure.database.session import get_db_context

        async with get_db_context() as db:
            repo = UserMCPServerRepository(db)
            server = await repo.get_by_id(server_id)
            if server:
                await repo.update(
                    server,
                    {"status": UserMCPServerStatus.AUTH_REQUIRED.value},
                )
                # Note: no explicit commit — get_db_context() auto-commits on exit

                logger.warning(
                    "user_mcp_server_auth_required",
                    server_id=str(server_id),
                    reason="oauth_token_refresh_failed",
                )

    def get_decrypted_credentials(self, server: UserMCPServer) -> dict | None:
        """Decrypt and return server credentials. Returns None on failure.

        Public wrapper around _decrypt_existing_credentials with logging.
        """
        creds = self._decrypt_existing_credentials(server)
        if not creds and server.credentials_encrypted:
            logger.error(
                "user_mcp_credentials_decrypt_failed",
                server_id=str(server.id),
            )
            return None
        return creds or None

    def build_response_metadata(
        self,
        server: UserMCPServer,
    ) -> dict:
        """Extract non-sensitive display metadata from a server's encrypted credentials.

        Returns a dict with keys: header_name, has_credentials, has_oauth_credentials, oauth_scopes.
        """
        credentials = (
            self._decrypt_existing_credentials(server) if server.credentials_encrypted else None
        )
        return build_response_metadata(server, credentials)

    # =========================================================================
    # Private helpers
    # =========================================================================

    @staticmethod
    def _encrypt_credentials(data: UserMCPServerCreate) -> str | None:
        """Encrypt credentials based on auth_type."""
        if data.auth_type == UserMCPAuthType.API_KEY:
            creds = {
                "header_name": data.header_name or MCP_USER_DEFAULT_API_KEY_HEADER,
                "api_key": data.api_key,
            }
            return encrypt_data(json.dumps(creds))
        elif data.auth_type == UserMCPAuthType.BEARER:
            creds = {"token": data.bearer_token}
            return encrypt_data(json.dumps(creds))
        elif data.auth_type == UserMCPAuthType.OAUTH2:
            # OAuth credentials stored after callback, not at creation
            if data.oauth_client_id:
                creds = {
                    "client_id": data.oauth_client_id,
                    "client_secret": data.oauth_client_secret,
                }
                return encrypt_data(json.dumps(creds))
            return None
        return None

    @staticmethod
    def _decrypt_existing_credentials(server: UserMCPServer) -> dict[str, Any]:
        """Decrypt existing server credentials, returning empty dict on failure."""
        if not server.credentials_encrypted:
            return {}
        try:
            result: dict[str, Any] = json.loads(decrypt_data(server.credentials_encrypted))
            return result
        except ValueError, json.JSONDecodeError:
            return {}

    @classmethod
    def _encrypt_credentials_from_update(
        cls,
        update_data: dict,
        auth_type: str,
        server: UserMCPServer,
    ) -> str | None:
        """Re-encrypt credentials from partial update data, merging with existing."""
        if auth_type == UserMCPAuthType.API_KEY.value:
            # Merge: decrypt existing → overlay new values → re-encrypt
            existing = cls._decrypt_existing_credentials(server)
            api_key = update_data.get("api_key") or existing.get("api_key")
            header_name = update_data.get(
                "header_name",
                existing.get(
                    "header_name",
                    server.required_header_name or MCP_USER_DEFAULT_API_KEY_HEADER,
                ),
            )
            if api_key:
                return encrypt_data(
                    json.dumps(
                        {
                            "header_name": header_name,
                            "api_key": api_key,
                        }
                    )
                )
            # No api_key available (switching from none/oauth without providing key)
            return server.credentials_encrypted
        elif auth_type == UserMCPAuthType.BEARER.value:
            existing = cls._decrypt_existing_credentials(server)
            bearer_token = update_data.get("bearer_token") or existing.get("token")
            if bearer_token:
                return encrypt_data(json.dumps({"token": bearer_token}))
            return server.credentials_encrypted
        elif auth_type == UserMCPAuthType.OAUTH2.value:
            # Merge: update client_id/client_secret while preserving OAuth tokens
            existing = cls._decrypt_existing_credentials(server)
            client_id = update_data.get("oauth_client_id") or existing.get("client_id")
            client_secret = update_data.get("oauth_client_secret") or existing.get("client_secret")
            if client_id:
                # Preserve existing OAuth tokens (access_token, refresh_token, etc.)
                creds = dict(existing)
                creds["client_id"] = client_id
                creds["client_secret"] = client_secret or ""
                return encrypt_data(json.dumps(creds))
            return server.credentials_encrypted
        elif auth_type == UserMCPAuthType.NONE.value:
            return None
        return server.credentials_encrypted

    @staticmethod
    async def _disconnect_from_pool(
        user_id: UUID, server_id: UUID, *, strict: bool = False
    ) -> None:
        """Disconnect a server from the user MCP pool (if pool exists)."""
        try:
            from src.infrastructure.mcp.user_pool import get_user_mcp_pool

            pool = get_user_mcp_pool()
            if pool:
                await pool.disconnect(user_id, server_id)
        except Exception:
            if strict:
                raise
            # Pool may not be initialized — non-critical
            logger.warning(
                "user_mcp_pool_disconnect_skipped",
                user_id=str(user_id),
                server_id=str(server_id),
                reason="pool_not_available",
            )
