"""A passive, location-free projection of weather the briefing already obtained."""

from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.domains.briefing.constants import SECTION_WEATHER_TTL_SECONDS
from src.domains.briefing.schemas import CardSection, CardStatus, WeatherData


class CompanionWeather(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    temperature_c: float = Field(ge=-100, le=65)
    condition_code: str = Field(min_length=1, max_length=32)
    wind_speed_kmh: float | None = Field(default=None, ge=0, le=500)
    observed_at: datetime
    expires_at: datetime


class CompanionEnvironment(BaseModel):
    timezone: str
    weather: CompanionWeather | None = None


def project_weather(section: CardSection | None, now: datetime) -> CompanionWeather | None:
    """Never turn stale fallback data or a forecast into present conditions."""
    if section is None or section.status != CardStatus.OK:
        return None
    if not isinstance(section.data, WeatherData) or section.generated_at.tzinfo is None:
        return None
    age = (now - section.generated_at).total_seconds()
    if not 0 <= age < SECTION_WEATHER_TTL_SECONDS:
        return None
    data = section.data
    try:
        return CompanionWeather(
            temperature_c=data.temperature_c,
            condition_code=data.condition_code,
            wind_speed_kmh=data.wind_speed_kmh,
            observed_at=section.generated_at,
            expires_at=section.generated_at + timedelta(seconds=SECTION_WEATHER_TTL_SECONDS),
        )
    except ValidationError:
        return None
