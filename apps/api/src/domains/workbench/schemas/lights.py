"""What the lights routes take and answer (ADR-369).

A light says what it can do — dimming, colour, a colour temperature and the
range its own bridge publishes (ADR-184: the page offers no value the lamp
refuses). A room holds the lights its devices own; it is on while one of them
is. A change names what it changes; a colour (``#rrggbb``) and a temperature
are two ways to set one lamp's light and are never sent together.
"""

from __future__ import annotations

from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from src.domains.workbench.ids import ProviderId

#: An sRGB colour as a native colour input gives it.
ColourHex = Annotated[str | None, StringConstraints(pattern=r"^#[0-9a-fA-F]{6}$")]


class LightView(BaseModel):
    """One lamp, and what it can do."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="The bridge's id of the light.")
    name: str = Field(description="Its name on the bridge.")
    room_id: str | None = Field(description="The room its device belongs to, if any.")
    on: bool = Field(description="Whether it is on.")
    brightness: float | None = Field(description="0-100; None when it cannot be dimmed.")
    supports_color: bool = Field(description="Whether it takes a colour.")
    color_hex: str | None = Field(description="Its current colour, drawn at full luminance.")
    mirek: int | None = Field(description="Its colour temperature; None when it has none.")
    mirek_min: int | None = Field(description="The coolest temperature it takes (mirek).")
    mirek_max: int | None = Field(description="The warmest temperature it takes (mirek).")


class RoomView(BaseModel):
    """One room of the bridge."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="The bridge's id of the room.")
    name: str = Field(description="Its name.")
    light_ids: list[str] = Field(description="The lights its devices own, in bridge order.")
    on: bool = Field(description="Whether one of its lights is on.")


class SceneView(BaseModel):
    """One scene of the bridge."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="The bridge's id of the scene.")
    name: str = Field(description="Its name.")
    room_id: str | None = Field(description="The room or zone it belongs to.")
    active: bool = Field(description="Whether it is the one shown now.")


class LightsView(BaseModel):
    """The bridge, read once."""

    rooms: list[RoomView] = Field(description="Its rooms.")
    lights: list[LightView] = Field(description="Its lights.")
    scenes: list[SceneView] = Field(description="Its scenes.")


class LightChange(BaseModel):
    """What changes on one lamp: a field left out is kept."""

    model_config = ConfigDict(extra="forbid")

    light_id: ProviderId = Field(description="The lamp.")
    on: bool | None = Field(default=None, description="On, or off.")
    brightness: float | None = Field(default=None, ge=0, le=100, description="0-100.")
    color_hex: ColourHex = Field(default=None, description="A colour, #rrggbb.")
    mirek: int | None = Field(
        default=None, ge=1, le=1000, description="A colour temperature, within the lamp's range."
    )

    @model_validator(mode="after")
    def _one_change_at_least(self) -> Self:
        if all(value is None for value in (self.on, self.brightness, self.color_hex, self.mirek)):
            raise ValueError("a change names at least one field")
        if self.color_hex is not None and self.mirek is not None:
            raise ValueError("a colour and a temperature are two ways to set one light")
        return self


class RoomChange(BaseModel):
    """What changes on every light of one room."""

    model_config = ConfigDict(extra="forbid")

    room_id: ProviderId = Field(description="The room.")
    on: bool | None = Field(default=None, description="On, or off.")
    brightness: float | None = Field(default=None, ge=0, le=100, description="0-100.")

    @model_validator(mode="after")
    def _one_change_at_least(self) -> Self:
        if self.on is None and self.brightness is None:
            raise ValueError("a change names at least one field")
        return self


class SceneRecall(BaseModel):
    """A scene to show."""

    model_config = ConfigDict(extra="forbid")

    scene_id: ProviderId = Field(description="The scene.")
