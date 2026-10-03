"""Provider calendar dates retain their supplied precision and local calendar day."""

from typing import TypeGuard

from src.core.i18n_dates import get_month_name
from src.core.time_utils import parse_datetime
from src.domains.agents.display.components.base import RenderContext, format_date


def provider_date(value: object, ctx: RenderContext) -> str:
    if not isinstance(value, dict):
        return ""
    year, month, day = value.get("year"), value.get("month"), value.get("day", 0)
    if not (_integer(year, 9999) and _integer(month, 12) and _integer(day, 31)):
        return ""
    if year == 0 or month == 0:
        return ""
    if day == 0:
        return f"{get_month_name(month, ctx.language)} {year}"
    instant = parse_datetime(f"{year:04d}-{month:02d}-{day:02d}T00:00:00Z")
    return format_date(instant, ctx.language, "UTC") if instant else ""


def _integer(value: object, upper: int) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= upper
