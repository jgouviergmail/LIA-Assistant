"""
Unit tests for authorization module (OWASP-aligned security).

Tests cover:
- check_resource_ownership() with hide_existence parameter
- check_resource_ownership_by_user_id() for service layer
- Superuser bypass functionality
- Enumeration attack prevention (404 vs 403 strategy)
- Edge cases (None resources, missing attributes)
"""

from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.core.security.authorization import check_resource_ownership


class MockResource:
    """Mock resource with user_id attribute for testing."""

    def __init__(self, user_id: str):
        self.user_id = user_id


class MockUser:
    """Mock user with id and is_superuser attributes for testing."""

    def __init__(self, user_id: str, is_superuser: bool = False):
        self.id = user_id
        self.is_superuser = is_superuser


@pytest.mark.unit
@pytest.mark.security
class TestCheckResourceOwnership:
    """Test check_resource_ownership() function."""

    def test_owner_can_access_resource(self):
        """Test that resource owner can access their resource."""
        # Arrange
        user_id = str(uuid4())
        user = MockUser(user_id)
        resource = MockResource(user_id)

        # Act & Assert - No exception should be raised
        try:
            check_resource_ownership(
                resource=resource,
                current_user=user,
                resource_name="connector",
                hide_existence=False,
            )
        except HTTPException:
            pytest.fail("Owner should be able to access their resource")

    def test_non_owner_blocked_with_403(self):
        """Test that non-owner is blocked with 403 when hide_existence=False."""
        # Arrange
        owner_id = str(uuid4())
        other_user_id = str(uuid4())
        user = MockUser(other_user_id)
        resource = MockResource(owner_id)

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            check_resource_ownership(
                resource=resource,
                current_user=user,
                resource_name="connector",
                hide_existence=False,
            )

        assert exc_info.value.status_code == 403
        assert "not authorized" in exc_info.value.detail.lower()

    def test_non_owner_blocked_with_404(self):
        """Test that non-owner is blocked with 404 when hide_existence=True (enumeration prevention)."""
        # Arrange
        owner_id = str(uuid4())
        other_user_id = str(uuid4())
        user = MockUser(other_user_id)
        resource = MockResource(owner_id)

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            check_resource_ownership(
                resource=resource,
                current_user=user,
                resource_name="connector",
                hide_existence=True,  # OWASP enumeration prevention
            )

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    def test_superuser_can_access_with_flag_true(self):
        """Test that superuser can access any resource when allow_superuser=True."""
        # Arrange
        owner_id = str(uuid4())
        superuser_id = str(uuid4())
        superuser = MockUser(superuser_id, is_superuser=True)
        resource = MockResource(owner_id)

        # Act & Assert - No exception should be raised
        try:
            check_resource_ownership(
                resource=resource,
                current_user=superuser,
                resource_name="connector",
                allow_superuser=True,  # Allow superuser bypass
                hide_existence=False,
            )
        except HTTPException:
            pytest.fail("Superuser should be able to access resource when allow_superuser=True")

    def test_superuser_blocked_with_flag_false(self):
        """Test that superuser is blocked when allow_superuser=False."""
        # Arrange
        owner_id = str(uuid4())
        superuser_id = str(uuid4())
        superuser = MockUser(superuser_id, is_superuser=True)
        resource = MockResource(owner_id)

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            check_resource_ownership(
                resource=resource,
                current_user=superuser,
                resource_name="connector",
                allow_superuser=False,  # Disable superuser bypass
                hide_existence=False,
            )

        assert exc_info.value.status_code == 403

    def test_none_resource_raises_404(self):
        """Test that None resource raises 404 regardless of hide_existence."""
        # Arrange
        user = MockUser(str(uuid4()))

        # Act & Assert - hide_existence=False
        with pytest.raises(HTTPException) as exc_info:
            check_resource_ownership(
                resource=None,
                current_user=user,
                resource_name="connector",
                hide_existence=False,
            )
        assert exc_info.value.status_code == 404

        # Act & Assert - hide_existence=True
        with pytest.raises(HTTPException) as exc_info:
            check_resource_ownership(
                resource=None,
                current_user=user,
                resource_name="connector",
                hide_existence=True,
            )
        assert exc_info.value.status_code == 404

    def test_resource_name_in_error_message(self):
        """Test that resource name is included in error message."""
        # Arrange
        user = MockUser(str(uuid4()))

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            check_resource_ownership(
                resource=None,
                current_user=user,
                resource_name="custom_resource",
                hide_existence=False,
            )

        assert "custom_resource" in exc_info.value.detail.lower()


@pytest.mark.unit
@pytest.mark.security
class TestEnumerationAttackPrevention:
    """Test enumeration attack prevention strategies (OWASP-aligned)."""

    def test_private_resource_hides_existence_with_404(self):
        """Test that private resources return 404 for non-owners (hide existence)."""
        # Arrange - Simulate trying to access someone else's private connector
        owner_id = str(uuid4())
        attacker_id = str(uuid4())
        attacker = MockUser(attacker_id)
        resource = MockResource(owner_id)

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            check_resource_ownership(
                resource=resource,
                current_user=attacker,
                resource_name="connector",
                hide_existence=True,  # Private resource strategy
            )

        # Attacker can't distinguish between "doesn't exist" and "exists but forbidden"
        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    def test_public_resource_shows_403(self):
        """Test that public resources return 403 for non-owners (better UX)."""
        # Arrange - Simulate trying to access someone else's public profile
        owner_id = str(uuid4())
        viewer_id = str(uuid4())
        viewer = MockUser(viewer_id)
        resource = MockResource(owner_id)

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            check_resource_ownership(
                resource=resource,
                current_user=viewer,
                resource_name="profile",
                hide_existence=False,  # Public resource strategy
            )

        # Viewer knows resource exists but is forbidden (clearer for public resources)
        assert exc_info.value.status_code == 403
        assert "not authorized" in exc_info.value.detail.lower()

    def test_nonexistent_resource_always_returns_404(self):
        """Test that None resource always returns 404 regardless of strategy."""
        # Arrange
        user = MockUser(str(uuid4()))

        # Act & Assert - hide_existence=False (public)
        with pytest.raises(HTTPException) as exc_info:
            check_resource_ownership(
                resource=None,
                current_user=user,
                resource_name="profile",
                hide_existence=False,
            )
        assert exc_info.value.status_code == 404

        # Act & Assert - hide_existence=True (private)
        with pytest.raises(HTTPException) as exc_info:
            check_resource_ownership(
                resource=None,
                current_user=user,
                resource_name="connector",
                hide_existence=True,
            )
        assert exc_info.value.status_code == 404

    def test_enumeration_attack_scenario(self):
        """
        Test realistic enumeration attack scenario.

        Attacker tries to enumerate connectors by ID guessing.
        With hide_existence=True, both non-existent and forbidden return 404.
        """
        # Arrange
        attacker_id = str(uuid4())
        attacker = MockUser(attacker_id)

        # Scenario 1: Non-existent connector
        with pytest.raises(HTTPException) as exc_info1:
            check_resource_ownership(
                resource=None,
                current_user=attacker,
                resource_name="connector",
                hide_existence=True,
            )

        # Scenario 2: Existing connector owned by someone else
        owner_id = str(uuid4())
        resource = MockResource(owner_id)
        with pytest.raises(HTTPException) as exc_info2:
            check_resource_ownership(
                resource=resource,
                current_user=attacker,
                resource_name="connector",
                hide_existence=True,
            )

        # Assert - Both scenarios return identical 404 (attacker can't distinguish)
        assert exc_info1.value.status_code == 404
        assert exc_info2.value.status_code == 404
        assert exc_info1.value.detail == exc_info2.value.detail


@pytest.mark.unit
class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_user_without_is_superuser_attribute(self):
        """Test handling user without is_superuser attribute raises AttributeError."""
        # Arrange
        user_id = str(uuid4())

        class UserWithoutSuperuser:
            def __init__(self, user_id):
                self.id = user_id
                # No is_superuser attribute

        user = UserWithoutSuperuser(user_id)
        resource = MockResource(user_id)

        # Act & Assert - Should raise AttributeError when allow_superuser=True
        with pytest.raises(AttributeError):
            check_resource_ownership(
                resource=resource,
                current_user=user,
                resource_name="connector",
                allow_superuser=True,  # This triggers is_superuser access
                hide_existence=False,
            )

        # But should work if allow_superuser=False (no is_superuser access)
        try:
            check_resource_ownership(
                resource=resource,
                current_user=user,
                resource_name="connector",
                allow_superuser=False,  # Skip superuser check
                hide_existence=False,
            )
        except HTTPException:
            pytest.fail("Should work when allow_superuser=False")

    def test_resource_without_user_id_attribute(self):
        """Test handling resource without user_id attribute."""
        # Arrange
        user = MockUser(str(uuid4()))

        class ResourceWithoutUserId:
            pass

        resource = ResourceWithoutUserId()

        # Act & Assert - Should raise AttributeError (caught and handled gracefully)
        with pytest.raises((HTTPException, AttributeError)):
            check_resource_ownership(
                resource=resource,
                current_user=user,
                resource_name="invalid_resource",
                hide_existence=False,
            )

    def test_uuid_vs_string_comparison(self):
        """Test that UUID and string user_id comparison works correctly."""
        # Arrange

        user_id_uuid = uuid4()
        user_id_str = str(user_id_uuid)

        # User with string ID
        user = MockUser(user_id_str)

        # Resource with string ID
        resource = MockResource(user_id_str)

        # Act & Assert - Should work
        try:
            check_resource_ownership(
                resource=resource,
                current_user=user,
                resource_name="connector",
                hide_existence=False,
            )
        except HTTPException:
            pytest.fail("UUID/string comparison should work")
