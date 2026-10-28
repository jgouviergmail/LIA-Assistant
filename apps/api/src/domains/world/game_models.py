"""Closed immutable rule positions and moves; clients never submit a board or score."""

from typing import Annotated, Literal

from pydantic import ConfigDict, Field

from src.domains.world.wire_models import StrictModel

GameKind = Literal["tic_tac_toe", "four_in_row", "reversi"]
CabinetId = Literal["arcade-tic-tac-toe", "arcade-four-in-row", "arcade-reversi"]
GameResult = Literal["playing", "draw", "one", "two"]
Cell = Annotated[int, Field(strict=True, ge=0, le=2)]
Player = Annotated[int, Field(strict=True, ge=1, le=2)]
OptionalPlayer = Annotated[int | None, Field(strict=True, ge=1, le=2)]


class ImmutableGameModel(StrictModel):
    model_config = ConfigDict(frozen=True)


class PositionBase(ImmutableGameModel):
    turn: Player = Field(
        default=1, description="Player owning the next legal turn, including a forced pass."
    )
    result: GameResult = Field(
        default="playing", description="Rule-derived result; never accepted from a player command."
    )


class TicTacToePosition(PositionBase):
    game: Literal["tic_tac_toe"] = Field(
        default="tic_tac_toe", description="Closed rule family discriminator."
    )
    board: tuple[Cell, ...] = Field(
        default=(0,) * 9,
        min_length=9,
        max_length=9,
        description="Immutable row-major three-by-three cells; zero empty, one/two players.",
    )


class FourInRowPosition(PositionBase):
    game: Literal["four_in_row"] = Field(
        default="four_in_row", description="Closed rule family discriminator."
    )
    board: tuple[Cell, ...] = Field(
        default=(0,) * 42,
        min_length=42,
        max_length=42,
        description="Immutable six-row, seven-column gravity board, top row first.",
    )


class ReversiPosition(PositionBase):
    game: Literal["reversi"] = Field(
        default="reversi", description="Closed rule family discriminator."
    )
    board: tuple[Cell, ...] = Field(
        min_length=64,
        max_length=64,
        description="Immutable eight-by-eight row-major discs; zero denotes an empty cell.",
    )


class TicTacToeMove(ImmutableGameModel):
    game: Literal["tic_tac_toe"] = Field(
        default="tic_tac_toe", description="Move belongs exclusively to the three-by-three game."
    )
    cell: int = Field(ge=0, le=8, description="Zero-based row-major empty destination cell.")


class FourInRowMove(ImmutableGameModel):
    game: Literal["four_in_row"] = Field(
        default="four_in_row", description="Move belongs exclusively to the gravity game."
    )
    column: int = Field(
        ge=0,
        le=6,
        description="Zero-based destination column; the server chooses its lowest empty cell.",
    )


class ReversiMove(ImmutableGameModel):
    game: Literal["reversi"] = Field(
        default="reversi", description="Move belongs exclusively to the disc-capture game."
    )
    cell: int | None = Field(
        ge=0,
        le=63,
        description="Zero-based capture destination; null is an explicit forced pass only.",
    )


PositionValue = TicTacToePosition | FourInRowPosition | ReversiPosition
MoveValue = TicTacToeMove | FourInRowMove | ReversiMove
GamePosition = Annotated[PositionValue, Field(discriminator="game")]
OptionalGamePosition = Annotated[PositionValue | None, Field(discriminator="game")]
GameMove = Annotated[MoveValue, Field(discriminator="game")]
OptionalGameMove = Annotated[MoveValue | None, Field(discriminator="game")]
