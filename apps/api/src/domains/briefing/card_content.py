"""Displayable content on each typed home card."""

from src.domains.briefing.schemas import SmsData, WorkboardData


def _has_content(data: object) -> bool:
    """Return True if the data payload has at least one displayable item."""
    if data is None:
        return False
    # The workboard card is counts first: an open board with nothing in the
    # « needs me » page still has something to say. Only a board with no open
    # ticket at all is the empty state.
    if isinstance(data, SmsData):
        return data.total > 0
    if isinstance(data, WorkboardData):
        return data.open_total > 0 or data.needs_me > 0
    for attr in ("events", "items"):
        value = getattr(data, attr, None)
        if value is not None:
            return len(value) > 0
    # ForYouData (P15): three optional sub-blocks — content when any is filled.
    if hasattr(data, "open_loops"):
        return bool(
            getattr(data, "open_loops", None)
            or getattr(data, "recent_automations", None)
            or getattr(data, "next_automation", None)
        )
    # Non-list payloads (e.g. WeatherData) — assume present means content.
    return True
