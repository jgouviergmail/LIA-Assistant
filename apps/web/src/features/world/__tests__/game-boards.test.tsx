import { Activity } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { TicTacToeBoard } from '../games/TicTacToeBoard';
import { FourInRowBoard } from '../games/FourInRowBoard';
import { ReversiBoard } from '../games/ReversiBoard';
import { arcadeFixture } from './fixtures/arcade';

vi.mock('@/i18n/client', () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, unknown>) =>
      key + (values ? JSON.stringify(values) : ''),
  }),
}));

it('navigates a grid by keyboard, sends one coordinate and never mutates an unconfirmed board', () => {
  const game = arcadeFixture();
  Object.freeze(game.position.board);
  const move = vi.fn();
  let current = true;
  render(
    <TicTacToeBoard lng="fr" game={game} onMove={move} blocked={false} isCurrent={() => current} />
  );
  const cells = screen.getAllByRole('gridcell');
  expect(cells[0]).toHaveFocus();
  fireEvent.keyDown(cells[0], { key: 'ArrowRight' });
  expect(cells[1]).toHaveFocus();
  fireEvent.keyDown(cells[1], { key: 'ArrowDown' });
  expect(cells[4]).toHaveFocus();
  fireEvent.click(cells[4]);
  expect(move).toHaveBeenCalledExactlyOnceWith({ game: 'tic_tac_toe', cell: 4 });
  expect(game.position.board).toEqual(Array(9).fill(0));
  current = false;
  fireEvent.click(cells[5]);
  expect(move).toHaveBeenCalledTimes(1);
});

it('takes the keyboard once and never pulls it back to the first cell on a reveal', () => {
  const game = arcadeFixture();
  const board = (mode: 'visible' | 'hidden') => (
    <Activity mode={mode}>
      <TicTacToeBoard
        lng="fr"
        game={game}
        onMove={vi.fn()}
        blocked={false}
        isCurrent={() => true}
      />
    </Activity>
  );
  const view = render(board('visible'));
  const cells = screen.getAllByRole('gridcell');
  expect(cells[0]).toHaveFocus();
  fireEvent.keyDown(cells[0], { key: 'ArrowDown' });
  fireEvent.keyDown(cells[3], { key: 'ArrowRight' });
  expect(cells[4]).toHaveFocus();
  view.rerender(board('hidden'));
  view.rerender(board('visible'));
  expect(cells[0]).not.toHaveFocus();
  expect(cells[4]).toHaveFocus();
  expect(cells[4]).toHaveAttribute('tabindex', '0');
});

it('keeps illegal and out-of-turn cells readable but refuses activation and held-key repetition', () => {
  const game = arcadeFixture();
  game.legal_moves = [];
  const move = vi.fn();
  render(
    <TicTacToeBoard lng="fr" game={game} onMove={move} blocked={false} isCurrent={() => true} />
  );
  const cells = screen.getAllByRole('gridcell');
  expect(cells[0]).toHaveAttribute('aria-disabled', 'true');
  fireEvent.click(cells[0]);
  expect(move).not.toHaveBeenCalled();
  expect(fireEvent.keyDown(cells[0], { key: 'Enter', repeat: true })).toBe(false);
  fireEvent.keyDown(cells[0], { key: 'End' });
  expect(cells[2]).toHaveFocus();
});

it('offers gravity columns rather than accepting a caller-selected drop row', () => {
  const game = arcadeFixture('four_in_row');
  for (let row = 0; row < 6; row++) game.position.board[row * 7] = row % 2 ? 2 : 1;
  game.legal_moves = game.legal_moves.filter(
    move => move.game === 'four_in_row' && move.column !== 0
  );
  const move = vi.fn();
  render(
    <FourInRowBoard lng="fr" game={game} onMove={move} blocked={false} isCurrent={() => true} />
  );
  const columns = screen.getAllByRole('button');
  expect(columns[0]).toHaveAttribute('aria-disabled', 'true');
  fireEvent.click(columns[0]);
  expect(move).not.toHaveBeenCalled();
  fireEvent.keyDown(columns[0], { key: 'ArrowRight' });
  expect(columns[1]).toHaveFocus();
  fireEvent.click(columns[1]);
  expect(move).toHaveBeenCalledExactlyOnceWith({ game: 'four_in_row', column: 1 });
});

it('requires an explicit server-authorized Reversi pass and never passes automatically', () => {
  const game = arcadeFixture('reversi');
  game.position.board.fill(1);
  game.position.board[0] = game.position.board[63] = 0;
  game.position.board[1] = 2;
  game.position.turn = game.your_number = 2;
  game.legal_moves = [{ game: 'reversi', cell: null }];
  const move = vi.fn();
  render(
    <ReversiBoard lng="fr" game={game} onMove={move} blocked={false} isCurrent={() => true} />
  );
  expect(screen.getAllByRole('gridcell')).toHaveLength(64);
  expect(move).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'world.arcade.pass' }));
  expect(move).toHaveBeenCalledExactlyOnceWith({ game: 'reversi', cell: null });
});

it('keeps a focused pass readable while a suspended game refuses all activation', () => {
  const game = arcadeFixture('reversi');
  game.legal_moves = [{ game: 'reversi', cell: null }];
  const move = vi.fn();
  render(<ReversiBoard lng="fr" game={game} onMove={move} blocked isCurrent={() => true} />);
  const pass = screen.getByRole('button', { name: 'world.arcade.pass' });
  pass.focus();
  fireEvent.click(pass);
  expect(pass).toHaveFocus();
  expect(pass).toHaveAttribute('aria-disabled', 'true');
  expect(move).not.toHaveBeenCalled();
});
