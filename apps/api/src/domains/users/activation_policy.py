"""A retiring or erased account cannot be reactivated through any identity door."""

from src.domains.users.account_cleanup import cleanup_pending
from src.domains.users.models import User


def assert_activation_allowed(user: User, *, requested: bool = True) -> None:
    """Read freshly locked lifecycle fields before an activation or verification write."""
    if requested and (user.deletion_started_at is not None or user.is_deleted):
        raise cleanup_pending()
