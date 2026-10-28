import { render, screen, fireEvent } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';
import { TicTacToeBoard } from '../games/TicTacToeBoard';
import { FourInRowBoard } from '../games/FourInRowBoard';
import { ReversiBoard } from '../games/ReversiBoard';
import { arcadeFixture } from './fixtures/arcade';

vi.mock('@/i18n/client', () => ({
  useTranslation: (lng: string) => ({
    t: (key: string, values?: Record<string, unknown>) => {
      let value: unknown = lng === 'fr' ? fr : en;
      for (const part of key.split('.')) {
        if (!value || typeof value !== 'object' || !(part in value))
          throw new Error('Missing translation: ' + key);
        value = Reflect.get(value, part);
      }
      if (typeof value !== 'string') throw new Error('Non-text translation');
      return value.replace(/{{(\w+)}}/g, (_, name: string) => String(values?.[name] ?? ''));
    },
  }),
}));

it.each(['fr', 'en'] as const)(
  'gives all game coordinates a translated accessible name in %s',
  lng => {
    const words = (lng === 'fr' ? fr : en).world.arcade;
    const first = words.cell
      .replace('{{row}}', '1')
      .replace('{{column}}', '1')
      .replace('{{piece}}', words.empty);
    const ui = render(
      <TicTacToeBoard
        lng={lng}
        game={arcadeFixture()}
        blocked={false}
        isCurrent={() => true}
        onMove={() => {}}
      />
    );
    expect(screen.getByRole('grid', { name: words.games.tic_tac_toe.title })).toBeInTheDocument();
    expect(screen.getByRole('gridcell', { name: first })).toBeInTheDocument();
    ui.rerender(
      <FourInRowBoard
        lng={lng}
        game={arcadeFixture('four_in_row')}
        blocked={false}
        isCurrent={() => true}
        onMove={() => {}}
      />
    );
    expect(
      screen.getByRole('button', { name: words.column.replace('{{column}}', '1') })
    ).toBeInTheDocument();
    const game = arcadeFixture('reversi');
    game.legal_moves = [{ game: 'reversi', cell: null }];
    const move = vi.fn();
    ui.rerender(
      <ReversiBoard lng={lng} game={game} blocked={false} isCurrent={() => true} onMove={move} />
    );
    fireEvent.click(screen.getByRole('button', { name: words.pass }));
    expect(move).toHaveBeenCalledExactlyOnceWith({ game: 'reversi', cell: null });
  }
);
