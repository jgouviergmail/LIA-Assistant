"""A browser document address is routing data, never authentication or role authority."""

from uuid import UUID

APPLICATION_DEVICE_HEADER = "X-Lia-Device-ID"


def parse_application_device_id(value: str | None) -> UUID | None:
    if value is None or len(value) != 36:
        return None
    try:
        parsed = UUID(value)
    except ValueError:
        return None
    return parsed if str(parsed) == value.lower() else None
