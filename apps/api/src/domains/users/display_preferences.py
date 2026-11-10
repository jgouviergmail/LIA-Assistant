"""Cross-field validation for the person's display schedule under a row lock."""

from src.core.exceptions import raise_invalid_input
from src.core.i18n_api_messages import APIMessages
from src.domains.users.models import User
from src.domains.users.schemas import UserUpdate

_SCHEDULE_FIELDS = frozenset({"theme_light_start_minute", "theme_dark_start_minute"})


def requires_preference_lock(data: UserUpdate, *, comparing: bool) -> bool:
    """Partial schedules and compare-and-set writes read a fresh locked account."""
    return comparing or bool(_SCHEDULE_FIELDS & data.model_fields_set)


def validate_display_patch(user: User, data: UserUpdate) -> None:
    """Refuse an empty civil-time interval after merging the locked current row.

    Args:
        user: Account read under the preference row lock.
        data: Validated, possibly partial profile update.

    Raises:
        ValidationError: When the merged interval has equal boundaries.
    """
    if not _SCHEDULE_FIELDS & data.model_fields_set:
        return
    light = data.theme_light_start_minute
    dark = data.theme_dark_start_minute
    if (light if light is not None else user.theme_light_start_minute) == (
        dark if dark is not None else user.theme_dark_start_minute
    ):
        raise_invalid_input(APIMessages.theme_schedule_boundaries_must_differ())
