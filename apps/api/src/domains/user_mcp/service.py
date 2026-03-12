"""
User MCP Server service for business logic.

Handles CRUD operations, credential encryption, ownership checks,
and pool coordination for per-user MCP servers.

Phase: evolution F2.1 — MCP Per-User
Created: 2026-02-28
"""

import json
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import (
    MCP_USER_DEFAULT_API_KEY_HEADER,
    MCP_USER_MAX_SERVERS_PER_USER_DEFAULT,
)
from src.core.exceptions import ResourceNotFoundError, ValidationError
from src.core.security.utils import decrypt_data, encrypt_data
from src.domains.user_mcp.models import (
    UserMCPAuthType,
    UserMCPServer,
    UserMCPServerStatus,
)
from src.domains.user_mcp.repository import UserMCPServerRepository
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

    async def list_enabled_active(self, user_id: UUID) -> list[UserMCPServer]:
        """List enabled + active MCP servers for a user (chat hot path)."""
        return await self.repository.get_enabled_active_for_user(user_id)

    async def create_server(
        self,
        user_id: UUID,
        data: UserMCPServerCreate,
    ) -> UserMCPServer:
        """
        Create a new user MCP server.

        Validates URL (SSRF prevention), enforces per-user limit,
        and encrypts credentials.

        Raises:
            ValidationError: If user has reached the maximum limit or URL is invalid.
        """
        # Enforce per-user limit
        max_servers = getattr(
            settings, "mcp_user_max_servers_per_user", MCP_USER_MAX_SERVERS_PER_USER_DEFAULT
        )
        count = await self.repository.count_for_user(user_id)
        if count >= max_servers:
            raise ValidationError(f"Maximum of {max_servers} MCP servers per user")

        # Check name uniqueness
        existing = await self.repository.get_by_name_for_user(user_id, data.name)
        if existing:
            raise ValidationError(f"An MCP server named '{data.name}' already exists")

        # SSRF prevention: validate URL
        is_valid, error_msg = await validate_http_endpoint(data.url)
        if not is_valid:
            raise ValidationError(f"Invalid MCP server URL: {error_msg}")

        # Build encrypted credentials
        credentials_encrypted = self._encrypt_credentials(data)

        # Determine initial status
        initial_status = (
            UserMCPServerStatus.AUTH_REQUIRED.value
            if data.auth_type == UserMCPAuthType.OAUTH2
            else UserMCPServerStatus.ACTIVE.value
        )

        # Store OAuth scopes in oauth_metadata if provided
        oauth_metadata = None
        if data.auth_type == UserMCPAuthType.OAUTH2 and data.oauth_scopes:
            oauth_metadata = {"requested_scopes": data.oauth_scopes}

        server = await self.repository.create(
            {
                "user_id": user_id,
                "name": data.name,
                "url": data.url,
                "auth_type": data.auth_type.value,
                "credentials_encrypted": credentials_encrypted,
                "oauth_metadata": oauth_metadata,
                "status": initial_status,
                "is_enabled": True,
                "domain_description": data.domain_description,
                "timeout_seconds": data.timeout_seconds,
                "hitl_required": data.hitl_required,
            }
        )

        logger.info(
            "user_mcp_server_created",
            server_id=str(server.id),
            user_id=str(user_id),
            name=data.name,
            auth_type=data.auth_type.value,
            status=initial_status,
        )

        return server

    async def update_server(
        self,
        server_id: UUID,
        user_id: UUID,
        data: UserMCPServerUpdate,
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
    ) -> None:
        """
        Delete a user MCP server.

        Disconnects from pool BEFORE database deletion.

        Raises:
            ResourceNotFoundError: If server not found or wrong owner.
        """
        server = await self.get_with_ownership_check(server_id, user_id)

        # Disconnect from pool first (releases MCP session)
        await self._disconnect_from_pool(user_id, server_id)

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
    ) -> UserMCPServer:
        """
        Toggle is_enabled for an MCP server.

        When disabling, disconnects from pool.

        Raises:
            ResourceNotFoundError: If server not found or wrong owner.
        """
        server = await self.get_with_ownership_check(server_id, user_id)

        new_enabled = not server.is_enabled
        update_data: dict = {"is_enabled": new_enabled}

        if not new_enabled:
            # Disabling: disconnect from pool
            await self._disconnect_from_pool(user_id, server_id)

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

        server = await self.repository.update(
            server,
            {
                "credentials_encrypted": credentials_encrypted,
                "status": UserMCPServerStatus.AUTH_REQUIRED.value,
            },
        )

        # Disconnect from pool to invalidate cached sessions
        await self._disconnect_from_pool(user_id, server_id)

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

        try:
            auth = build_auth_for_server(server)
            entry = await pool.get_or_connect(
                user_id=user_id,
                server_id=server.id,
                url=server.url,
                auth=auth,
                timeout_seconds=server.timeout_seconds,
            )

            # Build single update dict (avoids multiple flush/refresh roundtrips)
            from src.core.time_utils import now_utc

            update_data: dict = {
                "discovered_tools_cache": entry.tools,
                "status": UserMCPServerStatus.ACTIVE.value,
                "last_connected_at": now_utc(),
                "last_error": None,
            }

            # Auto-generate domain_description if not user-provided
            if not server.domain_description:
                generated_desc = await self._llm_generate_description(
                    tool_list=entry.tools,
                    server_name=server.name,
                )
                update_data["domain_description"] = generated_desc

            # Compute E5 embeddings for semantic scoring (evolution F2.1)
            try:
                from src.domains.agents.services.tool_selector import compute_tool_embeddings

                tool_embeddings = await compute_tool_embeddings(
                    tool_metadata=entry.tools,
                    server_name=server.name,
                )
                if tool_embeddings:
                    update_data["tool_embeddings_cache"] = tool_embeddings
            except Exception:
                logger.warning(
                    "user_mcp_embedding_computation_failed",
                    server_id=str(server_id),
                    exc_info=True,
                )

            # Single DB update (skip ownership check — already verified)
            await self.repository.update(server, update_data)

            logger.info(
                "user_mcp_server_test_success",
                user_id=str(user_id),
                server_id=str(server_id),
                tool_count=len(entry.tools),
            )

            return {
                "success": True,
                "tools": entry.tools,
                "tool_count": len(entry.tools),
                "error": None,
                "domain_description": update_data.get(
                    "domain_description", server.domain_description
                ),
            }

        except Exception as e:
            # Best-effort: update error status in DB (session may be dirty)
            try:
                await self.repository.update(
                    server,
                    {
                        "status": UserMCPServerStatus.ERROR.value,
                        "last_error": str(e),
                    },
                )
            except Exception as status_err:
                logger.debug(
                    "user_mcp_error_status_update_failed",
                    server_id=str(server_id),
                    error=str(status_err),
                )

            logger.warning(
                "user_mcp_server_test_failed",
                user_id=str(user_id),
                server_id=str(server_id),
                error=str(e),
            )

            # Sanitize: only expose exception type, not internal details
            return {
                "success": False,
                "tools": [],
                "tool_count": 0,
                "error": f"Connection failed: {type(e).__name__}",
            }

    async def generate_description(
        self,
        server_id: UUID,
        user_id: UUID,
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

        if not server.discovered_tools_cache:
            raise ValidationError("No tools discovered yet — test connection first")

        # Handle both list and dict cache formats (same pattern as router._server_to_response)
        cache = server.discovered_tools_cache
        tool_list: list[dict] = cache if isinstance(cache, list) else cache.get("tools", [])

        if not tool_list:
            raise ValidationError("No tools discovered yet — test connection first")

        generated_desc = await self._llm_generate_description(
            tool_list=tool_list,
            server_name=server.name,
        )

        # Persist (overwrite any existing description)
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
    ) -> str:
        """Generate an intelligent domain description using an LLM.

        Analyses MCP tool names and descriptions to produce a domain
        description optimized for LLM query routing: the description
        explains *what kind of user queries* this server can handle.

        Falls back to ``auto_generate_server_description()`` if the LLM
        call fails for any reason (network, provider outage, etc.).

        Args:
            tool_list: Discovered tools (list of dicts with "name" / "description").
            server_name: Human-readable server name.

        Returns:
            Generated domain description string.
        """
        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            from src.domains.agents.prompts import load_prompt
            from src.infrastructure.llm import get_llm

            llm = get_llm("mcp_description")

            # Build tool summary for the prompt
            tool_lines: list[str] = []
            for t in tool_list:
                name = t.get("name", "")
                desc = t.get("description", "")
                if name and desc:
                    tool_lines.append(f"- {name}: {desc}")
                elif name:
                    tool_lines.append(f"- {name}")
            tools_text = "\n".join(tool_lines)

            system_prompt = load_prompt("mcp_description_prompt")
            user_prompt = f"Server name: {server_name}\n\nAvailable tools:\n{tools_text}"

            from src.infrastructure.llm.invoke_helpers import (
                enrich_config_with_node_metadata,
            )

            invoke_config = enrich_config_with_node_metadata(None, "mcp_description_generation")
            response = await llm.ainvoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt),
                ],
                config=invoke_config,
            )

            generated = str(response.content).strip()

            # Remove surrounding quotes if present
            if (generated.startswith('"') and generated.endswith('"')) or (
                generated.startswith("'") and generated.endswith("'")
            ):
                generated = generated[1:-1].strip()

            if generated:
                logger.debug(
                    "user_mcp_description_llm_generated",
                    server_name=server_name,
                    description_length=len(generated),
                )
                return generated

        except Exception:
            logger.warning(
                "user_mcp_description_llm_failed",
                server_name=server_name,
                exc_info=True,
            )

        # Fallback to algorithmic generation
        from src.domains.agents.registry.domain_taxonomy import (
            auto_generate_server_description,
        )

        tool_descs = [t.get("description", "") for t in tool_list]
        tool_names = [t.get("name", "") for t in tool_list]
        return auto_generate_server_description(
            tool_descriptions=tool_descs,
            server_name=server_name,
            tool_names=tool_names,
        )

    async def cache_oauth_metadata(
        self,
        server: UserMCPServer,
        metadata: dict,
    ) -> None:
        """Cache OAuth authorization server metadata for future flows."""
        await self.repository.update(server, {"oauth_metadata": metadata})

    async def update_discovered_tools(
        self,
        server_id: UUID,
        user_id: UUID,
        tools_cache: list[dict],
    ) -> None:
        """Update the discovered tools cache for a server."""
        server = await self.get_with_ownership_check(server_id, user_id)
        await self.repository.update(server, {"discovered_tools_cache": tools_cache})

    async def update_tool_embeddings(
        self,
        server_id: UUID,
        user_id: UUID,
        embeddings: dict,
    ) -> None:
        """Update pre-computed E5 tool embeddings cache for a server."""
        server = await self.get_with_ownership_check(server_id, user_id)
        await self.repository.update(server, {"tool_embeddings_cache": embeddings})

    @staticmethod
    async def update_oauth_credentials(
        server_id: UUID,
        encrypted_creds: str,
    ) -> None:
        """
        Update OAuth credentials for a server (called by MCPOAuth2Auth callbacks).

        Uses its own DB session (not request-scoped) for async OAuth callbacks.
        """
        from src.infrastructure.database.session import get_db_context

        async with get_db_context() as db:
            repo = UserMCPServerRepository(db)
            server = await repo.get_by_id(server_id)
            if server:
                await repo.update(
                    server,
                    {
                        "credentials_encrypted": encrypted_creds,
                        "status": UserMCPServerStatus.ACTIVE.value,
                    },
                )
                # Note: no explicit commit — get_db_context() auto-commits on exit

                logger.info(
                    "user_mcp_oauth_credentials_updated",
                    server_id=str(server_id),
                )

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

    async def update_connection_status(
        self,
        server_id: UUID,
        user_id: UUID,
        new_status: str,
        error: str | None = None,
    ) -> None:
        """Update server connection status and error message."""
        from src.core.time_utils import now_utc

        server = await self.get_with_ownership_check(server_id, user_id)
        update_data: dict = {"status": new_status}
        if new_status == UserMCPServerStatus.ACTIVE.value:
            update_data["last_connected_at"] = now_utc()
            update_data["last_error"] = None
        elif error:
            update_data["last_error"] = error
        await self.repository.update(server, update_data)

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
        header_name: str | None = None
        has_credentials = bool(server.credentials_encrypted)
        has_oauth_credentials = False

        if has_credentials:
            creds = self._decrypt_existing_credentials(server)
            if creds:
                header_name = creds.get("header_name")
                has_oauth_credentials = bool(creds.get("client_id"))

        oauth_scopes = (server.oauth_metadata or {}).get("requested_scopes")

        return {
            "header_name": header_name,
            "has_credentials": has_credentials,
            "has_oauth_credentials": has_oauth_credentials,
            "oauth_scopes": oauth_scopes,
        }

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
        except (ValueError, json.JSONDecodeError):
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
                existing.get("header_name", MCP_USER_DEFAULT_API_KEY_HEADER),
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
    async def _disconnect_from_pool(user_id: UUID, server_id: UUID) -> None:
        """Disconnect a server from the user MCP pool (if pool exists)."""
        try:
            from src.infrastructure.mcp.user_pool import get_user_mcp_pool

            pool = get_user_mcp_pool()
            if pool:
                await pool.disconnect(user_id, server_id)
        except Exception:
            # Pool may not be initialized — non-critical
            logger.warning(
                "user_mcp_pool_disconnect_skipped",
                user_id=str(user_id),
                server_id=str(server_id),
                reason="pool_not_available",
            )
