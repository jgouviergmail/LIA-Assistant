'use client';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n/client';
import { GameCellGrid, type GameBoardProps } from './GameBoard';
export function ReversiBoard(props: GameBoardProps) {
  const { t } = useTranslation(props.lng);
  if (props.game.position.game !== 'reversi') return null;
  const pass = props.game.legal_moves.some(move => move.game === 'reversi' && move.cell === null);
  return (
    <div className="space-y-3">
      <GameCellGrid {...props} />
      {pass && (
        <div className="flex justify-center">
          <Button
            className="min-h-11"
            aria-disabled={props.blocked}
            onClick={() => {
              if (!props.blocked && props.isCurrent())
                props.onMove({ game: 'reversi', cell: null });
            }}
          >
            {t('world.arcade.pass')}
          </Button>
        </div>
      )}
    </div>
  );
}
