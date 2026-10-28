"""Trusted semantic cabinets compiled from the same authored furniture as the client."""

from pathlib import Path
from typing import get_args

from pydantic import Field, model_validator

from src.domains.world.game_models import CabinetId as CabinetId
from src.domains.world.game_models import GameKind
from src.domains.world.schemas import Position
from src.domains.world.wire_models import StrictModel, VersionedModel


class GameCabinet(StrictModel):
    id: CabinetId = Field(
        description="Stable authored cabinet identity, independent of coordinates."
    )
    prop: str = Field(
        min_length=1,
        max_length=96,
        description="Existing physical arcade prop identity used by scene picking.",
    )
    game: GameKind = Field(
        description="The unique deterministic rule family assigned to this cabinet."
    )
    approach: Position = Field(
        description="Authored walkable front approach shared with client interactions."
    )


class GameCatalogue(VersionedModel):
    cabinets: tuple[GameCabinet, ...] = Field(
        min_length=3,
        max_length=3,
        description="Complete bounded one-to-one cabinet/rule inventory.",
    )

    @model_validator(mode="after")
    def complete(self) -> GameCatalogue:
        """Refuse duplicate or missing identities/rules before this authority starts."""
        if (
            {cabinet.id for cabinet in self.cabinets} != set(get_args(CabinetId))
            or {cabinet.game for cabinet in self.cabinets} != set(get_args(GameKind))
            or len({cabinet.prop for cabinet in self.cabinets}) != 3
            or any(
                cabinet.id != "arcade-" + cabinet.game.replace("_", "-")
                for cabinet in self.cabinets
            )
        ):
            raise ValueError("world_arcade_binding")
        return self


_CATALOGUE = GameCatalogue.model_validate_json(
    (Path(__file__).parent / "assets" / "games-v1.json").read_text(encoding="utf-8")
)
CABINETS: dict[CabinetId, GameCabinet] = {cabinet.id: cabinet for cabinet in _CATALOGUE.cabinets}
