"""Typed weather context snapshots, shared by both provider paths."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class WeatherForecastItem(BaseModel):
    model_config = ConfigDict(strict=True)

    location: str | dict[str, object]
    date: str | None = None
    description: str | None = None
    temperature: str | None = None
    temp_min: str | None = None
    temp_max: str | None = None
    temp_day: str | None = None
    humidity: str | None = None
    wind_speed: str | None = None
    wind_direction: str | None = None
    pressure: str | None = None
    visibility: str | None = None
    clouds: str | None = None
    sunrise: str | None = None
    sunset: str | None = None
    feels_like: str | None = None
    type: Literal["current", "forecast", "hourly"] | None = None
    temp: str | float | dict[str, object] | None = None
    hourly: list[dict[str, object]] | None = None
    interval: str | None = None
    wind_gust: str | None = None
    uv_index: float | None = None
    precipitation_probability: str | None = None
    rain_amount: str | None = None
    snow_amount: str | None = None
    dew_point: str | None = None
    heat_index: str | None = None
    wind_chill: str | None = None
    observation_time: str | None = None
    timezone: str | None = None
    source: Literal["google_weather", "openweathermap"] | None = None
    icon: str | None = None
