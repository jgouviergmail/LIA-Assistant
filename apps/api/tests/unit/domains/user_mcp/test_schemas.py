"""Tests for UserMCPServer Pydantic schemas validation."""

from datetime import UTC

import pytest
from pydantic import ValidationError

from src.domains.user_mcp.models import UserMCPAuthType, UserMCPServerStatus
from src.domains.user_mcp.schemas import (
    MCPDiscoveredToolResponse,
    UserMCPServerCreate,
    UserMCPServerListResponse,
    UserMCPServerResponse,
    UserMCPServerUpdate,
    UserMCPTestConnectionResponse,
)


class TestUserMCPServerCreate:
    """Tests for UserMCPServerCreate validation."""

    def test_valid_minimal(self) -> None:
        """Should accept minimal valid data with defaults."""
        data = UserMCPServerCreate(
            name="Test Server",
            url="https://mcp.example.com/sse",
        )
        assert data.name == "Test Server"
        assert data.auth_type == UserMCPAuthType.NONE
        assert data.timeout_seconds == 30
        assert data.hitl_required is None

    def test_valid_api_key(self) -> None:
        """Should accept API key auth with required credentials."""
        data = UserMCPServerCreate(
            name="API Server",
            url="https://mcp.example.com/sse",
            auth_type=UserMCPAuthType.API_KEY,
            api_key="sk-test-key-123",
            header_name="X-Custom-Key",
        )
        assert data.api_key == "sk-test-key-123"
        assert data.header_name == "X-Custom-Key"

    def test_valid_bearer(self) -> None:
        """Should accept Bearer auth with token."""
        data = UserMCPServerCreate(
            name="Bearer Server",
            url="https://mcp.example.com/sse",
            auth_type=UserMCPAuthType.BEARER,
            bearer_token="eyJhbGciOiJIUzI1NiJ9.test",
        )
        assert data.bearer_token is not None

    def test_valid_oauth2(self) -> None:
        """Should accept OAuth2 auth without credentials (flow follows)."""
        data = UserMCPServerCreate(
            name="OAuth Server",
            url="https://mcp.example.com/sse",
            auth_type=UserMCPAuthType.OAUTH2,
        )
        assert data.auth_type == UserMCPAuthType.OAUTH2

    def test_valid_oauth2_with_client_id(self) -> None:
        """Should accept OAuth2 with pre-registered client credentials."""
        data = UserMCPServerCreate(
            name="OAuth Server",
            url="https://mcp.example.com/sse",
            auth_type=UserMCPAuthType.OAUTH2,
            oauth_client_id="my-client-id",
            oauth_client_secret="my-client-secret",
        )
        assert data.oauth_client_id == "my-client-id"

    def test_reject_http_url(self) -> None:
        """Should reject non-HTTPS URL."""
        with pytest.raises(ValidationError, match="MCP server URL must use HTTPS"):
            UserMCPServerCreate(
                name="Test",
                url="http://mcp.example.com/sse",
            )

    def test_reject_empty_name(self) -> None:
        """Should reject empty server name."""
        with pytest.raises(ValidationError, match="String should have at least 1 character"):
            UserMCPServerCreate(
                name="",
                url="https://mcp.example.com/sse",
            )

    def test_reject_name_too_long(self) -> None:
        """Should reject name longer than 100 chars."""
        with pytest.raises(ValidationError, match="String should have at most 100 characters"):
            UserMCPServerCreate(
                name="x" * 101,
                url="https://mcp.example.com/sse",
            )

    def test_reject_api_key_without_key(self) -> None:
        """Should reject API key auth without api_key field."""
        with pytest.raises(ValidationError, match="api_key is required"):
            UserMCPServerCreate(
                name="Server",
                url="https://mcp.example.com/sse",
                auth_type=UserMCPAuthType.API_KEY,
            )

    def test_reject_bearer_without_token(self) -> None:
        """Should reject Bearer auth without bearer_token field."""
        with pytest.raises(ValidationError, match="bearer_token is required"):
            UserMCPServerCreate(
                name="Server",
                url="https://mcp.example.com/sse",
                auth_type=UserMCPAuthType.BEARER,
            )

    def test_reject_none_auth_with_credentials(self) -> None:
        """Should reject 'none' auth type when credentials are provided."""
        with pytest.raises(ValidationError, match="should not be provided"):
            UserMCPServerCreate(
                name="Server",
                url="https://mcp.example.com/sse",
                auth_type=UserMCPAuthType.NONE,
                api_key="some-key",
            )

    def test_reject_timeout_too_low(self) -> None:
        """Should reject timeout below 5 seconds."""
        with pytest.raises(ValidationError, match="greater than or equal to 5"):
            UserMCPServerCreate(
                name="Server",
                url="https://mcp.example.com/sse",
                timeout_seconds=2,
            )

    def test_reject_timeout_too_high(self) -> None:
        """Should reject timeout above 120 seconds."""
        with pytest.raises(ValidationError, match="less than or equal to 120"):
            UserMCPServerCreate(
                name="Server",
                url="https://mcp.example.com/sse",
                timeout_seconds=300,
            )

    def test_valid_domain_description(self) -> None:
        """Should accept domain_description within max length."""
        data = UserMCPServerCreate(
            name="Test",
            url="https://mcp.example.com/sse",
            domain_description="Search ML models on HuggingFace Hub",
        )
        assert data.domain_description == "Search ML models on HuggingFace Hub"

    def test_domain_description_nullable(self) -> None:
        """Should accept None domain_description (default)."""
        data = UserMCPServerCreate(
            name="Test",
            url="https://mcp.example.com/sse",
        )
        assert data.domain_description is None

    def test_reject_domain_description_too_long(self) -> None:
        """Should reject domain_description exceeding 500 chars."""
        with pytest.raises(ValidationError, match="String should have at most 500 characters"):
            UserMCPServerCreate(
                name="Test",
                url="https://mcp.example.com/sse",
                domain_description="x" * 501,
            )


class TestUserMCPServerUpdate:
    """Tests for UserMCPServerUpdate partial update schema."""

    def test_empty_update(self) -> None:
        """Should accept empty update (all fields optional)."""
        data = UserMCPServerUpdate()
        assert data.name is None
        assert data.url is None

    def test_partial_name_update(self) -> None:
        """Should accept updating only the name."""
        data = UserMCPServerUpdate(name="New Name")
        assert data.name == "New Name"
        assert data.url is None
        dumped = data.model_dump(exclude_unset=True)
        assert "name" in dumped
        assert "url" not in dumped

    def test_partial_timeout_update(self) -> None:
        """Should accept updating only timeout."""
        data = UserMCPServerUpdate(timeout_seconds=60)
        assert data.timeout_seconds == 60

    def test_reject_invalid_timeout(self) -> None:
        """Should reject invalid timeout in update."""
        with pytest.raises(ValidationError, match="greater than or equal to 5"):
            UserMCPServerUpdate(timeout_seconds=1)

    def test_reject_http_url_in_update(self) -> None:
        """Should reject non-HTTPS URL in update."""
        with pytest.raises(ValidationError, match="MCP server URL must use HTTPS"):
            UserMCPServerUpdate(url="http://mcp.example.com/sse")

    def test_reject_none_auth_with_credentials(self) -> None:
        """Should reject 'none' auth type when credentials are provided in update."""
        with pytest.raises(ValidationError, match="should not be provided"):
            UserMCPServerUpdate(
                auth_type=UserMCPAuthType.NONE,
                api_key="some-key",
            )

    def test_accept_auth_type_change_without_credentials(self) -> None:
        """Should accept changing auth_type without providing new credentials (keep existing)."""
        data = UserMCPServerUpdate(auth_type=UserMCPAuthType.BEARER)
        assert data.auth_type == UserMCPAuthType.BEARER
        assert data.bearer_token is None  # OK — keep existing in service layer

    def test_update_domain_description(self) -> None:
        """Should accept updating domain_description."""
        data = UserMCPServerUpdate(domain_description="Updated description")
        assert data.domain_description == "Updated description"
        dumped = data.model_dump(exclude_unset=True)
        assert "domain_description" in dumped


class TestMCPDiscoveredToolResponse:
    """Tests for MCPDiscoveredToolResponse schema."""

    def test_valid_tool(self) -> None:
        """Should accept valid tool response."""
        tool = MCPDiscoveredToolResponse(
            tool_name="read_file",
            description="Read file contents",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        )
        assert tool.tool_name == "read_file"

    def test_default_empty_schema(self) -> None:
        """Should default to empty input_schema."""
        tool = MCPDiscoveredToolResponse(
            tool_name="ping",
            description="Ping server",
        )
        assert tool.input_schema == {}


class TestUserMCPServerResponse:
    """Tests for UserMCPServerResponse schema."""

    def test_tool_count_from_explicit_value(self) -> None:
        """Should use explicit tool_count (set by router/service, not auto-computed)."""
        from datetime import datetime
        from uuid import uuid4

        tools = [
            MCPDiscoveredToolResponse(tool_name="t1", description="d1"),
            MCPDiscoveredToolResponse(tool_name="t2", description="d2"),
        ]
        response = UserMCPServerResponse(
            id=uuid4(),
            name="Server",
            url="https://example.com",
            auth_type=UserMCPAuthType.NONE,
            status=UserMCPServerStatus.ACTIVE,
            is_enabled=True,
            timeout_seconds=30,
            hitl_required=None,
            tool_count=len(tools),
            tools=tools,
            last_connected_at=None,
            last_error=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        assert response.tool_count == 2


class TestUserMCPTestConnectionResponse:
    """Tests for UserMCPTestConnectionResponse schema."""

    def test_success_response(self) -> None:
        """Should accept successful test response."""
        resp = UserMCPTestConnectionResponse(
            success=True,
            tool_count=3,
            tools=[
                MCPDiscoveredToolResponse(tool_name="t1", description="d1"),
            ],
        )
        assert resp.success is True
        assert resp.error is None

    def test_error_response(self) -> None:
        """Should accept error test response."""
        resp = UserMCPTestConnectionResponse(
            success=False,
            error="Connection refused",
        )
        assert resp.success is False
        assert resp.error == "Connection refused"


class TestUserMCPServerListResponse:
    """Tests for UserMCPServerListResponse schema."""

    def test_empty_list(self) -> None:
        """Should accept empty server list."""
        resp = UserMCPServerListResponse(servers=[], total=0)
        assert resp.total == 0
        assert resp.servers == []
