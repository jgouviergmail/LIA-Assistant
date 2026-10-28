'use client';
import { GameCellGrid, type GameBoardProps } from './GameBoard';
export function TicTacToeBoard(props: GameBoardProps) {
  return props.game.position.game === 'tic_tac_toe' ? <GameCellGrid {...props} /> : null;
}
