"""Unit tests for skills domain models."""

from src.domains.skills.models import Skill, UserSkillState


class TestSkillModel:
    """Tests for the Skill SQLAlchemy model."""

    def test_repr(self):
        """Skill repr includes key fields."""
        skill = Skill(name="test-skill", is_system=True, admin_enabled=True, description="Test")
        r = repr(skill)
        assert "test-skill" in r
        assert "is_system=True" in r
        assert "admin_enabled=True" in r

    def test_defaults(self):
        """Skill defaults are correct (column defaults apply at DB level, not Python init)."""
        skill = Skill(name="x", is_system=True, admin_enabled=True, description="d")
        assert skill.is_system is True
        assert skill.admin_enabled is True
        assert skill.owner_id is None
        assert skill.descriptions is None


class TestUserSkillStateModel:
    """Tests for the UserSkillState SQLAlchemy model."""

    def test_repr(self):
        """UserSkillState repr includes key fields."""
        import uuid

        uid = uuid.uuid4()
        sid = uuid.uuid4()
        state = UserSkillState(user_id=uid, skill_id=sid, is_active=True)
        r = repr(state)
        assert str(uid) in r
        assert "is_active=True" in r

    def test_default_is_active(self):
        """is_active defaults to True (column default applies at DB level)."""
        import uuid

        state = UserSkillState(user_id=uuid.uuid4(), skill_id=uuid.uuid4(), is_active=True)
        assert state.is_active is True
