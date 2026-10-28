'use client';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n/client';
import { GameMark, pieceLabel, type GameBoardProps } from './GameBoard';
import { useBoardFocus } from './board-focus';
export function FourInRowBoard({ lng, game, blocked, isCurrent, onMove }: GameBoardProps) {
  const { t } = useTranslation(lng);
  const focus = useBoardFocus(7, 7, isCurrent);
  if (game.position.game !== 'four_in_row') return null;
  const legal = new Set(
    game.legal_moves.flatMap(move => (move.game === 'four_in_row' ? [move.column] : []))
  );
  return (
    <div className="mx-auto w-full max-w-80 space-y-2 overflow-x-auto">
      <div
        role="toolbar"
        aria-label={t('world.arcade.choose_column')}
        className="grid min-w-56 grid-cols-7 gap-1"
      >
        {Array.from({ length: 7 }, (_, column) => (
          <Button
            key={column}
            type="button"
            variant="outline"
            ref={node => {
              focus.nodes.current[column] = node;
            }}
            tabIndex={focus.focused === column ? 0 : -1}
            aria-label={t('world.arcade.column', { column: column + 1 })}
            aria-disabled={blocked || !legal.has(column)}
            data-world-game-column={column}
            className="min-h-11 min-w-8 px-0"
            onFocus={() => focus.setFocused(column)}
            onKeyDown={event => focus.keyDown(event, column)}
            onClick={() => {
              if (!blocked && legal.has(column) && isCurrent())
                onMove({ game: 'four_in_row', column });
            }}
          >
            {column + 1}
          </Button>
        ))}
      </div>
      <table className="w-full min-w-56 table-fixed overflow-hidden rounded-lg border border-primary bg-primary/5">
        <caption className="sr-only">{t('world.arcade.board')}</caption>
        <thead className="sr-only">
          <tr>
            {Array.from({ length: 7 }, (_, column) => (
              <th key={column} scope="col">
                {t('world.arcade.column', { column: column + 1 })}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: 6 }, (_, row) => (
            <tr key={row}>
              {Array.from({ length: 7 }, (_, column) => {
                const value = game.position.board[row * 7 + column];
                return (
                  <td
                    key={column}
                    className="border-b border-r border-primary p-0"
                    aria-label={t('world.arcade.cell', {
                      row: row + 1,
                      column: column + 1,
                      piece: pieceLabel(t, 'four_in_row', value),
                    })}
                  >
                    <div className="flex aspect-square min-h-8 items-center justify-center">
                      <GameMark key={value} kind="four_in_row" value={value} />
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
