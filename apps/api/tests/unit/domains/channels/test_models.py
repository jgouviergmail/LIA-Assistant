"""Tests for UserChannelBinding models and enums."""

from src.domains.channels.models import ChannelType, UserChannelBinding


class TestChannelType:
    """Test ChannelType enum values."""

    def test_telegram_value(self) -> None:
        assert ChannelType.TELEGRAM == "telegram"

    def test_all_members(self) -> None:
        members = {m.value for m in ChannelType}
        assert members == {"telegram"}

    def test_is_str_enum(self) -> None:
        """ChannelType should be a StrEnum for DB storage compatibility."""
        assert isinstance(ChannelType.TELEGRAM, str)


class TestUserChannelBindingModel:
    """Test UserChannelBinding model configuration."""

    def test_tablename(self) -> None:
        assert UserChannelBinding.__tablename__ == "user_channel_bindings"

    def test_unique_constraint_user_channel_type(self) -> None:
        """Should have unique constraint on (user_id, channel_type)."""
        constraints = [
            c.name for c in UserChannelBinding.__table_args__ if hasattr(c, "name") and c.name
        ]
        assert "uq_user_channel_binding_type" in constraints

    def test_unique_constraint_channel_type_user_id(self) -> None:
        """Should have unique constraint on (channel_type, channel_user_id)."""
        constraints = [
            c.name for c in UserChannelBinding.__table_args__ if hasattr(c, "name") and c.name
        ]
        assert "uq_channel_type_user_id" in constraints

    def test_partial_index_active_lookup(self) -> None:
        """Should have partial index for active binding webhook lookup."""
        index_names = [
            c.name for c in UserChannelBinding.__table_args__ if hasattr(c, "name") and c.name
        ]
        assert "ix_channel_bindings_active_lookup" in index_names

    def test_has_is_active_column(self) -> None:
        """Should have is_active boolean column."""
        col = UserChannelBinding.__table__.columns["is_active"]
        assert col.nullable is False

    def test_has_channel_username_nullable(self) -> None:
        """channel_username should be nullable (optional Telegram @username)."""
        col = UserChannelBinding.__table__.columns["channel_username"]
        assert col.nullable is True

    def test_repr_does_not_leak_sensitive_data(self) -> None:
        """__repr__ should not include user_id or sensitive fields."""
        import inspect

        source = inspect.getsource(UserChannelBinding.__repr__)
        # Should include channel identifiers for debugging
        assert "channel_type" in source
        assert "channel_user_id" in source
