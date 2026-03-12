"""Tests for UserMCPServer models and enums."""

from src.domains.user_mcp.models import (
    UserMCPAuthType,
    UserMCPServer,
    UserMCPServerStatus,
)


class TestUserMCPAuthType:
    """Test UserMCPAuthType enum values."""

    def test_none_value(self) -> None:
        assert UserMCPAuthType.NONE == "none"

    def test_api_key_value(self) -> None:
        assert UserMCPAuthType.API_KEY == "api_key"

    def test_bearer_value(self) -> None:
        assert UserMCPAuthType.BEARER == "bearer"

    def test_oauth2_value(self) -> None:
        assert UserMCPAuthType.OAUTH2 == "oauth2"

    def test_all_members(self) -> None:
        members = {m.value for m in UserMCPAuthType}
        assert members == {"none", "api_key", "bearer", "oauth2"}


class TestUserMCPServerStatus:
    """Test UserMCPServerStatus enum values."""

    def test_active_value(self) -> None:
        assert UserMCPServerStatus.ACTIVE == "active"

    def test_inactive_value(self) -> None:
        assert UserMCPServerStatus.INACTIVE == "inactive"

    def test_auth_required_value(self) -> None:
        assert UserMCPServerStatus.AUTH_REQUIRED == "auth_required"

    def test_error_value(self) -> None:
        assert UserMCPServerStatus.ERROR == "error"

    def test_all_members(self) -> None:
        members = {m.value for m in UserMCPServerStatus}
        assert members == {"active", "inactive", "auth_required", "error"}


class TestUserMCPServerModel:
    """Test UserMCPServer model configuration."""

    def test_tablename(self) -> None:
        assert UserMCPServer.__tablename__ == "user_mcp_servers"

    def test_repr_format(self) -> None:
        """Should produce a readable repr format without credentials."""
        # Verify the __repr__ template doesn't leak credentials
        import inspect

        source = inspect.getsource(UserMCPServer.__repr__)
        assert "credentials" not in source.lower()
        assert "name" in source

    def test_unique_constraint_name(self) -> None:
        """Should have unique constraint on (user_id, name)."""
        constraints = [
            c.name for c in UserMCPServer.__table_args__ if hasattr(c, "name") and c.name
        ]
        assert "uq_user_mcp_server_name" in constraints

    def test_partial_index_exists(self) -> None:
        """Should have partial index for enabled + active servers."""
        index_names = [
            c.name for c in UserMCPServer.__table_args__ if hasattr(c, "name") and c.name
        ]
        assert "ix_user_mcp_servers_user_enabled" in index_names

    def test_has_domain_description_column(self) -> None:
        """Should have domain_description column (nullable Text)."""
        col = UserMCPServer.__table__.columns["domain_description"]
        assert col.nullable is True

    def test_has_tool_embeddings_cache_column(self) -> None:
        """Should have tool_embeddings_cache column (nullable JSONB)."""
        col = UserMCPServer.__table__.columns["tool_embeddings_cache"]
        assert col.nullable is True
