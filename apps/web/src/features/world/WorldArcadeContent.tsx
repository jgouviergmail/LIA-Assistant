'use client';
import { memo, useCallback } from 'react';
import { Bot, Play, RotateCcw, UsersRound } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { ArcadeSnapshot, GameObservation, WorldGameClient } from './game-client';
import type { CabinetId } from './game-catalogue';
import type { GameAction, GameMove, GameView } from './game-protocol';
import { GameMark, type GameBoardProps } from './games/GameBoard';
import { GameClock } from './games/GameClock';
import { clockDeadline, gameStatus } from './games/game-status';
import { TicTacToeBoard } from './games/TicTacToeBoard';
import { FourInRowBoard } from './games/FourInRowBoard';
import { ReversiBoard } from './games/ReversiBoard';

export interface ArcadeContext {
  lng: Language;
  cabinet: CabinetId;
  client: WorldGameClient;
  state: ArcadeSnapshot;
  observed: GameObservation | null;
  isCurrent(): boolean;
  perform(action: GameAction, move?: GameMove): void;
  leave(): void;
}
export function WorldArcadeContent(context: ArcadeContext) {
  const { state, lng, client, leave } = context;
  const { t } = useTranslation(lng);
  if (state.request)
    return (
      <div className="space-y-2">
        <p role="status">{t('world.arcade.requested')}</p>
        <GameClock lng={lng} client={client} deadline={state.request.expires_at} />
        <div>
          <Button className="min-h-11" variant="outline" onClick={leave}>
            {t('world.arcade.cancel_request')}
          </Button>
        </div>
      </div>
    );
  if (!state.game) return <ArcadeLobby {...context} />;
  return (
    <>
      <GameSummary game={state.game} lng={lng} client={client} />
      <GameInvitation {...context} game={state.game} />
      <GamePlay {...context} game={state.game} />
    </>
  );
}
function GameSummary({
  game,
  lng,
  client,
}: {
  game: GameView;
  lng: Language;
  client: WorldGameClient;
}) {
  const { t } = useTranslation(lng);
  const kind = game.position.game;
  return (
    <div className="space-y-2">
      <p role="status" className="font-medium">
        {gameStatus(game, t)}
        <span className="sr-only">
          {' '}
          {t('world.arcade.progress', {
            count: game.position.board.filter(value => value !== 0).length,
          })}
        </span>
      </p>
      <div className="flex flex-wrap gap-3">
        {game.players.map(player => (
          <span key={player.id} className="inline-flex min-w-0 items-center gap-1.5 text-sm">
            <GameMark kind={kind} value={player.number} />
            <span className="break-words">
              {player.number === game.your_number ? t('world.arcade.you') : player.alias}
            </span>
          </span>
        ))}
        {game.computer && (
          <span className="inline-flex items-center gap-1.5 text-sm">
            <GameMark kind={kind} value={3 - game.your_number} />
            {t('world.arcade.computer_name')}
          </span>
        )}
      </div>
      {game.phase !== 'finished' && (
        <GameClock lng={lng} client={client} deadline={clockDeadline(game)} />
      )}
    </div>
  );
}
function GameInvitation({
  game,
  lng,
  client,
  observed,
  perform,
}: ArcadeContext & { game: GameView }) {
  const { t } = useTranslation(lng);
  if (!game.pending) return null;
  return (
    <div className="space-y-3 rounded-lg border p-3">
      <p>{t('world.arcade.invitation', { player: game.pending.alias })}</p>
      <p className="text-sm text-muted-foreground">{t('world.arcade.fresh_board')}</p>
      <div className="flex flex-wrap gap-2">
        <Button
          className="min-h-11"
          aria-disabled={!client.canRequest(observed, 'accept')}
          onClick={() => perform('accept')}
        >
          {t('world.arcade.accept', { player: game.pending.alias })}
        </Button>
        <Button
          className="min-h-11"
          variant="outline"
          aria-disabled={!client.canRequest(observed, 'decline')}
          onClick={() => perform('decline')}
        >
          {t('world.arcade.decline')}
        </Button>
      </div>
    </div>
  );
}
function GamePlay(context: ArcadeContext & { game: GameView }) {
  const { game, client, observed, perform, lng, state, isCurrent } = context;
  const { t } = useTranslation(lng);
  const onMove = useCallback((move: GameMove) => perform('move', move), [perform]);
  const resume = (
    <Button
      className="min-h-11"
      aria-disabled={!client.canRequest(observed, 'rejoin')}
      onClick={() => perform('rejoin')}
    >
      <Play className="size-4" aria-hidden="true" />
      {t('world.arcade.resume')}
    </Button>
  );
  if (game.needs_rejoin && game.phase !== 'finished') return resume;
  if (game.phase === 'waiting') return <ArcadeLobby {...context} />;
  if (game.phase === 'empty') return <p role="status">{t('world.arcade.unavailable')}</p>;
  return (
    <>
      <ArcadeBoard
        key={game.round_id}
        lng={lng}
        game={game}
        blocked={state.pending !== null || game.paused || game.phase === 'finished'}
        isCurrent={isCurrent}
        onMove={onMove}
      />
      {game.phase === 'finished' &&
        // A finished table still shows its result; who must rejoin resumes before a rematch.
        (game.needs_rejoin ? (
          <div className="flex justify-center">{resume}</div>
        ) : (
          <Rematch
            game={game}
            lng={lng}
            available={client.canRequest(observed, 'rematch')}
            pending={state.pending !== null}
            onRequest={() => perform('rematch')}
          />
        ))}
    </>
  );
}
function ArcadeLobby({ state, client, observed, cabinet, perform, lng }: ArcadeContext) {
  const { t } = useTranslation(lng);
  const hint = state.cabinets.find(item => item.cabinet === cabinet);
  if (!hint) return <p role="status">{t('world.arcade.unavailable')}</p>;
  if (!state.game && hint.availability === 'full')
    return <p role="status">{t('world.arcade.occupied')}</p>;
  if (!state.game && hint.availability === 'joinable')
    return (
      <div className="space-y-3">
        <p>{t('world.arcade.join_hint')}</p>
        <Button
          className="min-h-11"
          aria-disabled={!client.canRequest(observed, 'request')}
          onClick={() => perform('request')}
        >
          <UsersRound className="size-4" aria-hidden="true" />
          {t('world.arcade.join')}
        </Button>
      </div>
    );
  return (
    <div className="space-y-3">
      {!state.nearby.includes(cabinet) && (
        <p role="status" className="text-sm">
          {t('world.arcade.approach')}
        </p>
      )}
      <div className="flex flex-wrap justify-center gap-2">
        <Button
          className="min-h-11"
          aria-disabled={!client.canRequest(observed, 'start_computer')}
          onClick={() => perform('start_computer')}
        >
          <Bot className="size-4" aria-hidden="true" />
          {t('world.arcade.computer')}
        </Button>
        {!state.game && (
          <Button
            className="min-h-11"
            variant="outline"
            aria-disabled={!client.canRequest(observed, 'wait')}
            onClick={() => perform('wait')}
          >
            <UsersRound className="size-4" aria-hidden="true" />
            {t('world.arcade.wait')}
          </Button>
        )}
      </div>
    </div>
  );
}
const ArcadeBoard = memo(function ArcadeBoard(props: GameBoardProps) {
  switch (props.game.position.game) {
    case 'tic_tac_toe':
      return <TicTacToeBoard {...props} />;
    case 'four_in_row':
      return <FourInRowBoard {...props} />;
    case 'reversi':
      return <ReversiBoard {...props} />;
  }
});
function Rematch({
  game,
  lng,
  available,
  pending,
  onRequest,
}: {
  game: GameView;
  lng: Language;
  available: boolean;
  pending: boolean;
  onRequest(): void;
}) {
  const { t } = useTranslation(lng);
  if (!game.computer && game.players.length !== 2) return null;
  const selected = game.rematch_ready.includes(game.your_number);
  return (
    <div className="flex justify-center">
      <Button
        className="min-h-11"
        aria-pressed={selected}
        aria-disabled={pending || (!selected && !available)}
        onClick={() => {
          if (!selected) onRequest();
        }}
      >
        <RotateCcw className="size-4" aria-hidden="true" />
        {t(selected ? 'world.arcade.rematch_requested' : 'world.arcade.rematch')}
      </Button>
    </div>
  );
}
