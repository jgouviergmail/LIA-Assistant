import { expect, it } from 'vitest';
import { clockDeadline, gameStatus } from '../games/game-status';
import { arcadeFixture } from './fixtures/arcade';
import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';

function translator(locale: typeof en) {
  return (key: string, values?: Record<string, unknown>) => {
    let value: unknown = locale;
    for (const segment of key.split('.'))
      value =
        value && typeof value === 'object' && segment in value
          ? Reflect.get(value, segment)
          : undefined;
    if (typeof value !== 'string') return key;
    return value.replace('{{player}}', String(values?.player));
  };
}
it.each([en, fr])(
  'uses authoritative outcomes and localized participant names without deriving winners from pixels',
  locale => {
    const translate = translator(locale);
    const game = arcadeFixture();
    game.position.board = [1, 1, 1, 2, 2, 0, 0, 0, 0];
    game.phase = 'finished';
    game.reason = 'unavailable';
    expect(gameStatus(game, translate)).toBe(locale.world.arcade.ended.unavailable);
    game.reason = 'win';
    game.winner = 1;
    expect(gameStatus(game, translate)).toBe(locale.world.arcade.won);
    game.winner = 2;
    expect(gameStatus(game, translate)).toBe(
      locale.world.arcade.other_won.replace('{{player}}', 'Sam')
    );
    game.players = game.players.slice(0, 1);
    expect(gameStatus(game, translate)).toBe(
      locale.world.arcade.other_won.replace('{{player}}', locale.world.arcade.other_player)
    );
    game.computer = true;
    // The computer has sentences of its own: its name is never pasted into a player's slot.
    expect(gameStatus(game, translate)).toBe(locale.world.arcade.computer_won);
    game.phase = 'playing_computer';
    game.winner = null;
    game.position.turn = 2;
    expect(gameStatus(game, translate)).toBe(locale.world.arcade.computer_turn);
    game.position.turn = 1;
    expect(gameStatus(game, translate)).toBe(locale.world.arcade.your_turn);
  }
);
it('runs the clock to a reconnection window first, then the waiting or turn deadline', () => {
  const game = arcadeFixture();
  game.reconnect_until = null;
  game.expires_at = 1300;
  game.turn_until = 220;
  game.phase = 'waiting';
  expect(clockDeadline(game)).toBe(1300);
  game.phase = 'playing_human';
  expect(clockDeadline(game)).toBe(220);
  game.reconnect_until = 140;
  expect(clockDeadline(game)).toBe(140);
  game.phase = 'waiting';
  expect(clockDeadline(game)).toBe(140);
});
