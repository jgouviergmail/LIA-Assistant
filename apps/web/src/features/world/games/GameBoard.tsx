'use client';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { GameKind } from '../game-catalogue';
import type { GameMove, GameView } from '../game-protocol';
import { useBoardFocus } from './board-focus';

export interface GameBoardProps {
  lng: Language;
  game: GameView;
  blocked: boolean;
  isCurrent(): boolean;
  onMove(move: GameMove): void;
}
type GameText = (key: string, values?: Record<string, unknown>) => string;
export function pieceLabel(t: GameText, kind: GameKind, value: number): string {
  return t(
    value === 0 ? 'world.arcade.empty' : `world.arcade.games.${kind}.${value === 1 ? 'one' : 'two'}`
  );
}
export function GameMark({ kind, value }: { kind: GameKind; value: number }) {
  if (!value) return null;
  const animation =
    'motion-safe:animate-in motion-safe:fade-in motion-safe:zoom-in-75 motion-safe:duration-150';
  if (kind === 'tic_tac_toe')
    return (
      <span
        aria-hidden="true"
        data-world-piece={value}
        className={`text-3xl font-bold text-primary sm:text-4xl ${animation}`}
      >
        {value === 1 ? '×' : '○'}
      </span>
    );
  const color =
    kind === 'reversi'
      ? value === 1
        ? 'border-slate-400 bg-black'
        : 'border-slate-600 bg-white'
      : value === 1
        ? 'border-primary bg-primary'
        : 'border-primary bg-background';
  return (
    <span
      aria-hidden="true"
      data-world-piece={value}
      className={`flex size-5 items-center justify-center rounded-full border-2 sm:size-7 ${color} ${animation}`}
    >
      {kind === 'four_in_row' && value === 2 && (
        <span className="size-1.5 rounded-full bg-primary" />
      )}
    </span>
  );
}
export function GameCellGrid({ lng, game, blocked, isCurrent, onMove }: GameBoardProps) {
  const { t } = useTranslation(lng);
  const kind = game.position.game;
  const columns = kind === 'tic_tac_toe' ? 3 : 8;
  const focus = useBoardFocus(game.position.board.length, columns, isCurrent);
  if (kind === 'four_in_row') return null;
  const legal = new Set(
    game.legal_moves.flatMap(move =>
      move.game !== 'four_in_row' && move.cell !== null ? [move.cell] : []
    )
  );
  return (
    <div className="max-w-full overflow-x-auto">
      <div
        role="grid"
        aria-label={t(`world.arcade.games.${kind}.title`)}
        aria-rowcount={columns}
        aria-colcount={columns}
        aria-busy={blocked}
        className="mx-auto w-full max-w-80 overflow-hidden rounded-lg border border-primary bg-primary/5"
        style={{ minWidth: columns * 32 + 2 }}
      >
        {Array.from({ length: columns }, (_, row) => (
          <div
            role="row"
            aria-rowindex={row + 1}
            key={row}
            className="grid"
            style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
          >
            {Array.from({ length: columns }, (_, column) => {
              const index = row * columns + column;
              const value = game.position.board[index];
              const enabled = !blocked && legal.has(index);
              return (
                <Button
                  key={index}
                  type="button"
                  variant="ghost"
                  role="gridcell"
                  aria-colindex={column + 1}
                  ref={node => {
                    focus.nodes.current[index] = node;
                  }}
                  tabIndex={focus.focused === index ? 0 : -1}
                  aria-label={t('world.arcade.cell', {
                    row: row + 1,
                    column: column + 1,
                    piece: pieceLabel(t, kind, value),
                  })}
                  aria-disabled={!enabled}
                  data-world-game-cell={index}
                  className="aspect-square h-auto min-h-8 min-w-8 rounded-none border-b border-r border-primary p-0 aria-disabled:cursor-default aria-disabled:hover:bg-transparent"
                  onFocus={() => focus.setFocused(index)}
                  onKeyDown={event => focus.keyDown(event, index)}
                  onClick={() => {
                    if (enabled && isCurrent()) onMove({ game: kind, cell: index });
                  }}
                >
                  <GameMark key={value} kind={kind} value={value} />
                  {!value && enabled && (
                    <span aria-hidden="true" className="size-1 rounded-full bg-primary/40" />
                  )}
                </Button>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}
