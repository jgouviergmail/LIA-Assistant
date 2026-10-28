import type { GameView } from '../game-protocol';
type GameText = (key: string, values?: Record<string, unknown>) => string;
/** A named opponent's alias, or null for the computer, which has sentences of its own. */
function opponentAlias(game: GameView, number: number, t: GameText): string | null {
  if (game.computer) return null;
  return (
    game.players.find(player => player.number === number)?.alias ?? t('world.arcade.other_player')
  );
}
function finishedStatus(game: GameView, t: GameText): string {
  if (game.winner !== null) {
    if (game.winner === game.your_number) return t('world.arcade.won');
    const player = opponentAlias(game, game.winner, t);
    return player === null
      ? t('world.arcade.computer_won')
      : t('world.arcade.other_won', { player });
  }
  return t('world.arcade.ended.' + (game.reason ?? 'unavailable'));
}
export function gameStatus(game: GameView, t: GameText): string {
  if (game.phase === 'finished') return finishedStatus(game, t);
  if (game.needs_rejoin) return t('world.arcade.resume_hint');
  if (game.paused) return t('world.arcade.paused');
  if (game.phase === 'waiting') return t('world.arcade.waiting');
  if (game.position.turn === game.your_number) return t('world.arcade.your_turn');
  const player = opponentAlias(game, game.position.turn, t);
  return player === null
    ? t('world.arcade.computer_turn')
    : t('world.arcade.other_turn', { player });
}
/** The instant the visible countdown runs to: a reconnection window first, then the round's own. */
export function clockDeadline(game: GameView): number {
  return game.reconnect_until ?? (game.phase === 'waiting' ? game.expires_at : game.turn_until);
}
