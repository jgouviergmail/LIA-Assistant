"""Unit tests for the plugin-facing extensions of the user MCP domain (ADR-225).

Three additive behaviors, all defaulting to the exact pre-existing semantics:

- ``create_server`` can persist an Agent Plugins provenance (``plugin_id``)
  and the plugin's fixed non-secret headers (``extra_headers``);
- ``delete_server`` refuses to delete a plugin-owned server unless the caller
  is the group uninstall (arbitrage F);
- the ephemeral connection pool forwards ``extra_headers`` as httpx client
  default headers — auth-generated headers keep precedence (§7.2.1), which
  is httpx's native behavior (auth flows run after request construction).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.exceptions import ValidationError
from src.domains.user_mcp.models import UserMCPAuthType
from src.domains.user_mcp.schemas import UserMCPServerCreate
from src.domains.user_mcp.service import UserMCPServerService

pytestmark = pytest.mark.unit

_PLUGIN = uuid4()
_HEADERS = {"X-Tenant": "public-tenant"}


@pytest.fixture
def service():
    svc = UserMCPServerService(AsyncMock())
    svc.repository = AsyncMock()
    svc.repository.get_by_name_for_user = AsyncMock(return_value=None)
    svc.repository.count_for_user = AsyncMock(return_value=0)
    svc.repository.create = AsyncMock(return_value=MagicMock())
    return svc


def _create_data() -> UserMCPServerCreate:
    return UserMCPServerCreate(
        name="plugin:deployment-api",
        url="https://deploy.example.com/mcp",
        auth_type=UserMCPAuthType.NONE,
    )


class TestCreateServerProvenance:
    @pytest.mark.asyncio
    @patch("src.domains.user_mcp.service.validate_http_endpoint", new_callable=AsyncMock)
    async def test_plugin_creation_persists_provenance_and_headers(
        self, mock_validate, service
    ) -> None:
        mock_validate.return_value = (True, None)

        await service.create_server(
            uuid4(), _create_data(), plugin_id=_PLUGIN, extra_headers=_HEADERS
        )

        row = service.repository.create.call_args[0][0]
        assert row["plugin_id"] == _PLUGIN
        assert row["extra_headers"] == _HEADERS

    @pytest.mark.asyncio
    @patch("src.domains.user_mcp.service.validate_http_endpoint", new_callable=AsyncMock)
    async def test_manual_creation_defaults_stay_null(self, mock_validate, service) -> None:
        mock_validate.return_value = (True, None)

        await service.create_server(uuid4(), _create_data())

        row = service.repository.create.call_args[0][0]
        assert row["plugin_id"] is None
        assert row["extra_headers"] is None


class TestDeleteServerLock:
    """Arbitrage F: plugin components leave through the plugin uninstall."""

    def _owned_server(self, user_id):
        server = MagicMock()
        server.id = uuid4()
        server.user_id = user_id
        server.name = "plugin:api"
        server.plugin_id = _PLUGIN
        return server

    @pytest.mark.asyncio
    async def test_plugin_owned_server_deletion_is_blocked(self, service) -> None:
        user_id = uuid4()
        server = self._owned_server(user_id)
        service.repository.get_by_id = AsyncMock(return_value=server)

        with pytest.raises(ValidationError):
            await service.delete_server(server.id, user_id)
        service.repository.delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_group_uninstall_bypasses_the_lock(self, service) -> None:
        user_id = uuid4()
        server = self._owned_server(user_id)
        service.repository.get_by_id = AsyncMock(return_value=server)
        service._disconnect_from_pool = AsyncMock()

        await service.delete_server(server.id, user_id, allow_plugin_owned=True)

        service.repository.delete.assert_awaited_once_with(server)

    @pytest.mark.asyncio
    async def test_manual_server_deletion_still_works(self, service) -> None:
        user_id = uuid4()
        server = self._owned_server(user_id)
        server.plugin_id = None
        service.repository.get_by_id = AsyncMock(return_value=server)
        service._disconnect_from_pool = AsyncMock()

        await service.delete_server(server.id, user_id)

        service.repository.delete.assert_awaited_once_with(server)


class TestPoolExtraHeaders:
    @pytest.mark.asyncio
    async def test_ephemeral_client_applies_extra_headers(self) -> None:
        from src.infrastructure.mcp import user_pool

        http_client = AsyncMock()
        mcp_client = AsyncMock()
        with (
            patch.object(user_pool.httpx2, "AsyncClient", return_value=http_client) as http_cls,
            patch.object(user_pool, "Client", return_value=mcp_client),
            patch.object(user_pool, "streamable_http_client"),
        ):
            async with user_pool._ephemeral_client(
                "https://x.example/mcp", auth=None, extra_headers=_HEADERS
            ):
                pass

        assert http_cls.call_args.kwargs["headers"] == _HEADERS

    @pytest.mark.asyncio
    async def test_ephemeral_client_without_headers_passes_none(self) -> None:
        from src.infrastructure.mcp import user_pool

        with (
            patch.object(user_pool.httpx2, "AsyncClient", return_value=AsyncMock()) as http_cls,
            patch.object(user_pool, "Client", return_value=AsyncMock()),
            patch.object(user_pool, "streamable_http_client"),
        ):
            async with user_pool._ephemeral_client("https://x.example/mcp", auth=None):
                pass

        assert http_cls.call_args.kwargs["headers"] is None

    @pytest.mark.asyncio
    async def test_get_or_connect_stores_and_forwards_extra_headers(self) -> None:
        from src.infrastructure.mcp.user_pool import UserMCPClientPool

        pool = UserMCPClientPool()
        pool._discover_tools = AsyncMock(return_value=([], None))

        entry = await pool.get_or_connect(
            user_id=uuid4(),
            server_id=uuid4(),
            url="https://x.example/mcp",
            auth=None,
            timeout_seconds=30,
            extra_headers=_HEADERS,
        )

        assert entry.extra_headers == _HEADERS
        assert pool._discover_tools.await_args.kwargs.get("extra_headers") == _HEADERS
