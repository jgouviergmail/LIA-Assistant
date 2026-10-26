"""Small fixed-floor collision authority compiled from the authored client map."""

import math
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domains.world.schemas import Position


class ZoneBounds(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, allow_inf_nan=False)
    id: str = Field(
        description="Authored zone identifier used for private-home boundaries and labels."
    )
    x: float = Field(ge=0, description="Horizontal ground coordinate in authored world tiles.")
    y: float = Field(ge=0, description="Vertical ground coordinate in authored world tiles.")
    width: float = Field(
        gt=0, description="Authored ground-space width of this floor or zone, in tiles."
    )
    height: float = Field(
        gt=0,
        description="Authored ground-space height of this floor or zone, in tiles.",
    )


class MovementSpeeds(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, allow_inf_nan=False)
    walk: float = Field(
        gt=0,
        le=10,
        description="Authoritative walking speed in ground tiles per second.",
    )
    run: float = Field(
        gt=0,
        le=10,
        description="Authoritative running speed in ground tiles per second.",
    )

    @model_validator(mode="after")
    def ordered(self) -> MovementSpeeds:
        """Reject an authored run speed below the corresponding walking speed."""
        if self.run < self.walk:
            raise ValueError("world_run_speed_below_walk")
        return self


class Geometry(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)
    id: str = Field(
        min_length=1,
        max_length=64,
        description="Authored scene identity, paired with its version for compatibility.",
    )
    version: int = Field(ge=1, description="Explicit supported wire or preference schema version.")
    width: int = Field(
        ge=1,
        le=128,
        description="Authored ground-space width of this floor or zone, in tiles.",
    )
    height: int = Field(
        ge=1,
        le=128,
        description="Authored ground-space height of this floor or zone, in tiles.",
    )
    spawn: Position = Field(
        description="Authored walkable arrival origin in ground tile coordinates."
    )
    movement: MovementSpeeds = Field(
        description="Authoritative authored walking and running speeds."
    )
    zones: list[ZoneBounds] = Field(
        max_length=32,
        description="Bounded authored ground-space zones for privacy and scene interactions.",
    )


class PoseSlot(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, allow_inf_nan=False)
    id: str = Field(
        min_length=1,
        max_length=96,
        description="Unique authored furniture pose slot identifier.",
    )
    prop: str = Field(description="Identifier of the authored furniture providing this pose slot.")
    kind: Literal["sit", "lie"] = Field(
        description="Authored posture kind; sitting and lying use different contact geometry."
    )
    position: Position = Field(description="Ground position in authored world coordinates.")
    approach: Position = Field(
        description="Authored ground position used to approach or leave this furniture slot."
    )
    facing: int = Field(
        ge=0,
        le=3,
        description="Authored isometric facing index used by the public actor renderer.",
    )
    elevation: float = Field(
        ge=0, le=2, description="Authored furniture contact height in world units."
    )


class FloorCatalogue(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    world: Geometry = Field(
        description="Trusted authored scene geometry shared with client navigation."
    )
    blocked: list[Literal[0, 1]] = Field(
        description="Row-major collision bitmap; one zero/one entry per authored ground tile."
    )
    poses: list[PoseSlot] = Field(
        max_length=128,
        description="Bounded authored sit/lie slots derived from the same scene as client navigation.",
    )

    @model_validator(mode="after")
    def valid_grid(self) -> FloorCatalogue:
        """Reject a collision bitmap whose cell count differs from the authored floor dimensions."""
        if len(self.blocked) != self.world.width * self.world.height:
            raise ValueError("world_grid_size")
        return self


_CATALOGUE = FloorCatalogue.model_validate_json(
    (Path(__file__).parent / "assets" / "campus-v1.json").read_text()
)
WORLD = _CATALOGUE.world
SCENE = f"{WORLD.id}:{WORLD.version}"
_BLOCKED = _CATALOGUE.blocked
POSE_SLOTS = {slot.id: slot for slot in _CATALOGUE.poses}
_HOME = next(zone for zone in WORLD.zones if zone.id == "home")
RADIUS = 0.22


def arrival(occupied: Iterable[Position]) -> Position:
    """Bounded walkable arrival search; players never materialize on top of each other."""
    positions = tuple(occupied)
    offsets = sorted(
        ((x * 2.0, y * 2.0) for x in range(-2, 3) for y in range(-2, 3)),
        key=lambda offset: (math.hypot(*offset), offset),
    )
    for dx, dy in offsets:
        x, y = WORLD.spawn["x"] + dx, WORLD.spawn["y"] + dy
        if fits(x, y) and all(math.hypot(x - p["x"], y - p["y"]) >= 1.6 for p in positions):
            return {"x": x, "y": y}
    raise ValueError("world_arrival_unavailable")


def private_home(point: Position) -> bool:
    """Return whether a ground position lies inside the private home zone."""
    return bool(
        _HOME.x <= point["x"] < _HOME.x + _HOME.width
        and _HOME.y <= point["y"] < _HOME.y + _HOME.height
    )


def fits(x: float, y: float) -> bool:
    """Check the actor's corner footprint against map boundaries and solid cells."""
    for dx in (-RADIUS, RADIUS):
        for dy in (-RADIUS, RADIUS):
            px, py = x + dx, y + dy
            if not (0 <= px < WORLD.width and 0 <= py < WORLD.height):
                return False
            if _BLOCKED[math.floor(py) * WORLD.width + math.floor(px)]:
                return False
    return True


def move(position: Position, dx: float, dy: float) -> Position:
    """Advance in bounded collision substeps, sliding independently along each walkable axis."""
    x, y = position["x"], position["y"]
    steps = max(1, math.ceil(math.hypot(dx, dy) / 0.12))
    for _ in range(steps):
        if fits(x + dx / steps, y):
            x += dx / steps
        if fits(x, y + dy / steps):
            y += dy / steps
    return {"x": x, "y": y}
