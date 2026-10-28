import { afterEach, expect, it, vi } from 'vitest';
import {
  WorldGameClient,
  GAME_COMMAND_TIMEOUT_MS,
  observeGame,
  type GamePort,
} from '../game-client';
import { worldViewSchema } from '../protocol';
import type { GameIntent } from '../game-protocol';
import { compileGameCabinets } from '../game-catalogue';
import { WORLD } from '../definition';

const epoch = '11111111-1111-4111-8111-111111111111';
const round = '22222222-2222-4222-8222-222222222222';
const cabinet = 'arcade-tic-tac-toe';
const approach = compileGameCabinets(WORLD)[0].approach;
const sessions = new Set<() => void>();
afterEach(() => {
  sessions.forEach(dispose => dispose());
  sessions.clear();
});
function snapshot(revision = 1) {
  return worldViewSchema.parse({
    version: 2,
    type: 'snapshot',
    epoch,
    revision,
    server_time: 100,
    receipts: [],
    status: 'active',
    controlling: true,
    ack: 0,
    actors: [],
    you: { id: epoch, alias: 'Léa', position: approach, facing: 1, walking: false },
    position: null,
    offer_until: null,
    idle_until: 1000,
    cabinets: [{ cabinet, availability: 'empty', round_id: null, revision: 0 }],
    game: null,
    game_request: null,
  });
}
function playing(revision = 2) {
  return worldViewSchema.parse({
    ...snapshot(revision),
    cabinets: [{ cabinet, availability: 'joinable', round_id: round, revision: 0 }],
    game: {
      cabinet,
      round_id: round,
      revision: 0,
      phase: 'playing_computer',
      computer: true,
      position: { game: 'tic_tac_toe', board: Array(9).fill(0), turn: 1, result: 'playing' },
      players: [{ id: epoch, alias: 'Léa', number: 1 }],
      your_number: 1,
      needs_rejoin: false,
      paused: false,
      turn_until: 220,
      expires_at: 1300,
      reconnect_until: null,
      pending: null,
      legal_moves: [{ game: 'tic_tac_toe', cell: 0 }],
      reason: null,
      winner: null,
      rematch_ready: [],
    },
  });
}
function setup() {
  const sent: GameIntent[] = [];
  const port: GamePort = {
    active: () => true,
    send: intent => {
      sent.push(intent);
      return { seq: sent.length, epoch, stream: 1 };
    },
  };
  const client = new WorldGameClient();
  const channel = client.attach(port);
  sessions.add(channel.dispose);
  channel.receive(snapshot(), 1, 0);
  return { client, sent, detach: channel.dispose, port, channel };
}

it('keeps one pending operation and requires its exact game-kind, action and sequence receipt', () => {
  const { client, sent, channel } = setup();
  expect(
    client.request(observeGame(client.getSnapshot(), cabinet), 'start_computer', undefined, 0)
  ).toBe(true);
  expect(client.request(observeGame(client.getSnapshot(), cabinet), 'wait', undefined, 1)).toBe(
    false
  );
  expect(sent).toHaveLength(1);
  channel.receive(
    { ...playing(), receipts: [{ seq: 1, kind: 'move', result: 'accepted' }] },
    1,
    100
  );
  expect(client.getSnapshot().pending).not.toBeNull();
  // The right kind is not enough: another sequence, or another action, answers nothing.
  const outcome = (action_id: string) =>
    ({ action_id, result: 'accepted', round_id: round, revision: 0 }) as const;
  channel.receive(
    { ...playing(), receipts: [{ seq: 2, kind: 'game', outcome: outcome(sent[0].action_id) }] },
    1,
    120
  );
  expect(client.getSnapshot().pending).not.toBeNull();
  channel.receive(
    {
      ...playing(),
      receipts: [
        { seq: 1, kind: 'game', outcome: outcome('99999999-9999-4999-8999-999999999999') },
      ],
    },
    1,
    140
  );
  expect(client.getSnapshot().pending).not.toBeNull();
  expect(client.getSnapshot().outcome).toBeNull();
  channel.receive(
    {
      ...playing(3),
      receipts: [
        {
          seq: 1,
          kind: 'game',
          outcome: {
            action_id: sent[0].action_id,
            result: 'accepted',
            round_id: round,
            revision: 0,
          },
        },
      ],
    },
    1,
    200
  );
  expect(client.getSnapshot().pending).toBeNull();
  expect(client.getSnapshot().game?.round_id).toBe(round);
});

it('never silently replays uncertain input and accepts only deliberate legal current-board moves', () => {
  const { client, sent, channel } = setup();
  channel.receive(playing(), 1, 0);
  expect(
    client.request(
      observeGame(client.getSnapshot(), cabinet),
      'move',
      { game: 'tic_tac_toe', cell: 1 },
      1
    )
  ).toBe(false);
  expect(
    client.request(
      observeGame(client.getSnapshot(), cabinet),
      'move',
      { game: 'tic_tac_toe', cell: 0 },
      2
    )
  ).toBe(true);
  client.tick(GAME_COMMAND_TIMEOUT_MS + 3);
  expect(client.getSnapshot().pending?.uncertain).toBe(true);
  expect(sent).toHaveLength(1);
  client.resynchronize();
  expect(client.getSnapshot().pending).toBeNull();
  expect(sent).toHaveLength(1);
});

it('rejects out-of-order scene and match frames and clears old private data on a generation change', () => {
  const { client, channel } = setup();
  const current = playing(5);
  if (!current.game) throw new Error('fixture');
  current.game.revision = 3;
  channel.receive(current, 1, 100);
  const stable = client.getSnapshot().game;
  channel.receive(playing(4), 1, 200);
  channel.receive(playing(6), 1, 300);
  expect(client.getSnapshot().game).toBe(stable);
  channel.receive({ ...snapshot(7), controlling: false, cabinets: [] }, 1, 400);
  expect(client.getSnapshot().game).toBeNull();
  channel.receive(current, 0, 500);
  expect(client.getSnapshot().game).toBeNull();
});

it('publishes stable snapshots for identical data and fences an old attachment cleanup', () => {
  const { client, detach, channel } = setup();
  channel.receive(playing(), 1, 0);
  const first = client.getSnapshot();
  const notify = vi.fn();
  const unsubscribe = client.subscribe(notify);
  channel.receive(playing(3), 1, 100);
  expect(client.getSnapshot()).toBe(first);
  expect(notify).not.toHaveBeenCalled();
  const successor = client.attach({ active: () => true, send: () => null });
  successor.receive(playing(), 1, 200);
  channel.receive(snapshot(99), 1, 300);
  channel.suspend('ended');
  detach();
  expect(client.getSnapshot().game).not.toBeNull();
  unsubscribe();
});

it('withdraws an active game once without duplicate departure commands', () => {
  const { client, sent, channel } = setup();
  channel.receive(playing(), 1, 0);
  expect(client.request(observeGame(client.getSnapshot(), cabinet), 'rematch', undefined, 0)).toBe(
    false
  );
  client.close(cabinet);
  expect(sent.filter(intent => intent.action === 'leave')).toHaveLength(1);
  channel.receive(playing(3), 1, 200);
  client.close(cabinet);
  expect(sent.filter(intent => intent.action === 'leave')).toHaveLength(1);
});

it('waits for an in-flight acceptance then withdraws its fresh human round without replaying acceptance', () => {
  const { client, sent, channel } = setup();
  const offered = playing();
  if (!offered.game) throw new Error('fixture');
  offered.game.pending = {
    id: '33333333-3333-4333-8333-333333333333',
    alias: 'Sam',
    expires_at: 120,
  };
  channel.receive(offered, 1, 0);
  expect(client.request(observeGame(client.getSnapshot(), cabinet), 'accept', undefined, 0)).toBe(
    true
  );
  client.close(cabinet, 1);
  expect(sent).toHaveLength(1);
  channel.receive({ ...offered, revision: 3 }, 1, 2);
  expect(sent).toHaveLength(1);
  const joined = playing(4);
  if (!joined.game) throw new Error('fixture');
  const next = '44444444-4444-4444-8444-444444444444';
  joined.game = {
    ...joined.game,
    round_id: next,
    phase: 'playing_human',
    computer: false,
    players: [...joined.game.players, { id: offered.game.pending.id, alias: 'Sam', number: 2 }],
  };
  joined.receipts = [
    {
      seq: 1,
      kind: 'game',
      outcome: { action_id: sent[0].action_id, result: 'accepted', round_id: next, revision: 0 },
    },
  ];
  channel.receive(joined, 1, 3);
  expect(sent.map(intent => intent.action)).toEqual(['accept', 'leave']);
  expect(sent[1].round_id).toBe(next);
});

it('removes private boards even if a noncontrolling frame incorrectly carries a payload', () => {
  const { client, channel } = setup();
  channel.receive(playing(), 1, 0);
  channel.receive({ ...playing(3), controlling: false }, 1, 100);
  expect(client.getSnapshot().game).toBeNull();
  expect(client.getSnapshot().cabinets).toEqual([]);
});

it('fences the board and invitation actually rendered instead of consenting to a newer unseen state', () => {
  const { client, channel, sent } = setup();
  const offered = playing();
  if (!offered.game) throw new Error('fixture');
  offered.game.pending = {
    id: '33333333-3333-4333-8333-333333333333',
    alias: 'Sam',
    expires_at: 120,
  };
  channel.receive(offered, 1, 0);
  const seen = observeGame(client.getSnapshot(), cabinet);
  const replaced = playing(3);
  if (!replaced.game) throw new Error('fixture');
  replaced.game.revision = 2;
  replaced.game.pending = {
    id: '55555555-5555-4555-8555-555555555555',
    alias: 'Alex',
    expires_at: 121,
  };
  channel.receive(replaced, 1, 100);
  expect(client.request(seen, 'accept', undefined, 101)).toBe(false);
  expect(client.request(seen, 'move', { game: 'tic_tac_toe', cell: 0 }, 102)).toBe(false);
  expect(sent).toHaveLength(0);
  expect(client.request(observeGame(client.getSnapshot(), cabinet), 'accept', undefined, 103)).toBe(
    true
  );
});

it('disables unavailable, remote, paused and superseded interactions without a local board mutation', () => {
  const { client, sent, channel } = setup();
  channel.receive(playing(), 1, 0);
  const before = client.getSnapshot().game?.position;
  const remote = playing(3);
  if (!remote.you || !remote.game) throw new Error('fixture');
  remote.you.position = { x: 1, y: 1 };
  channel.receive(remote, 1, 100);
  expect(
    client.request(
      observeGame(client.getSnapshot(), cabinet),
      'move',
      { game: 'tic_tac_toe', cell: 0 },
      101
    )
  ).toBe(false);
  // A paused round keeps its legal moves on screen but accepts none of them.
  const paused = playing(4);
  if (!paused.game) throw new Error('fixture');
  paused.game.paused = true;
  channel.receive(paused, 1, 150);
  expect(client.getSnapshot().game?.legal_moves).toHaveLength(1);
  expect(
    client.request(
      observeGame(client.getSnapshot(), cabinet),
      'move',
      { game: 'tic_tac_toe', cell: 0 },
      151
    )
  ).toBe(false);
  expect(client.canRequest(observeGame(client.getSnapshot(), cabinet), 'leave')).toBe(true);
  channel.suspend('reconnecting');
  expect(client.request(observeGame(client.getSnapshot(), cabinet), 'wait', undefined, 200)).toBe(
    false
  );
  expect(sent).toHaveLength(0);
  expect(client.getSnapshot().game?.position).toEqual(before);
  channel.suspend('ended');
  expect(client.getSnapshot().game).toBeNull();
});

it('fences rendered consent across transport generations but permits unrelated scene revisions', () => {
  const { client, channel, sent } = setup();
  channel.receive(playing(), 1, 0);
  const old = observeGame(client.getSnapshot(), cabinet);
  channel.receive(playing(100), 1, 100);
  expect(client.canRequest(old, 'move', { game: 'tic_tac_toe', cell: 0 })).toBe(true);
  channel.receive(playing(101), 2, 200);
  expect(client.request(old, 'move', { game: 'tic_tac_toe', cell: 0 })).toBe(false);
  expect(sent).toHaveLength(0);
});

it('settles a departure from an authoritative membership withdrawal even when its receipt was lost', () => {
  const { client, channel, sent } = setup();
  channel.receive(playing(), 1, 0);
  client.close(cabinet, 1);
  channel.receive(snapshot(3), 1, 2);
  expect(client.getSnapshot().pending).toBeNull();
  expect(client.canRequest(observeGame(client.getSnapshot(), cabinet), 'wait')).toBe(true);
  expect(sent).toHaveLength(1);
});

it('does not replay a refused departure and allows a deliberate fresh departure', () => {
  const { client, channel, sent } = setup();
  channel.receive(playing(), 1, 0);
  client.close(cabinet, 1);
  channel.receive(
    {
      ...playing(3),
      receipts: [
        {
          seq: 1,
          kind: 'game',
          outcome: {
            action_id: sent[0].action_id,
            result: 'rate_limited',
            round_id: round,
            revision: 0,
          },
        },
      ],
    },
    1,
    2
  );
  expect(sent).toHaveLength(1);
  expect(
    client.canRequest(observeGame(client.getSnapshot(), cabinet), 'move', {
      game: 'tic_tac_toe',
      cell: 0,
    })
  ).toBe(true);
  client.close(cabinet, 1001);
  expect(sent.map(intent => intent.action)).toEqual(['leave', 'leave']);
});

it('waits for authoritative processing before closing an uncertain acceptance into its fresh round', () => {
  const { client, channel, sent } = setup();
  const offered = playing();
  if (!offered.game) throw new Error('fixture');
  offered.game.pending = {
    id: '33333333-3333-4333-8333-333333333333',
    alias: 'Sam',
    expires_at: 120,
  };
  channel.receive(offered, 1, 0);
  expect(client.request(observeGame(client.getSnapshot(), cabinet), 'accept', undefined, 1)).toBe(
    true
  );
  client.close(cabinet, 2);
  client.tick(6000);
  expect(sent.map(intent => intent.action)).toEqual(['accept']);
  const next = '44444444-4444-4444-8444-444444444444';
  channel.receive(
    { ...offered, revision: 3, ack: 1, game: { ...offered.game, round_id: next, pending: null } },
    1,
    6001
  );
  expect(sent.map(intent => intent.action)).toEqual(['accept', 'leave']);
  expect(sent[1].round_id).toBe(next);
});

it('marks an unanswered initial choice uncertain without needing another snapshot and cancels its timer on teardown', () => {
  vi.useFakeTimers();
  const { client, sent, detach } = setup();
  try {
    expect(client.request(observeGame(client.getSnapshot(), cabinet), 'start_computer')).toBe(true);
    vi.advanceTimersByTime(GAME_COMMAND_TIMEOUT_MS);
    expect(client.getSnapshot().pending?.uncertain).toBe(true);
    expect(sent).toHaveLength(1);
    client.resynchronize();
    expect(client.request(observeGame(client.getSnapshot(), cabinet), 'wait')).toBe(true);
    expect(vi.getTimerCount()).toBe(1);
    detach();
    expect(vi.getTimerCount()).toBe(0);
    vi.advanceTimersByTime(GAME_COMMAND_TIMEOUT_MS * 2);
    expect(client.getSnapshot().pending).toBeNull();
    expect(sent).toHaveLength(2);
  } finally {
    detach();
    vi.useRealTimers();
  }
});

it('offers rejoin on a finished table that needs it and a rematch only once it is resumed', () => {
  const { client, sent, channel } = setup();
  const finished = playing(3);
  if (!finished.game) throw new Error('fixture');
  finished.game.phase = 'finished';
  finished.game.reason = 'draw';
  finished.game.needs_rejoin = true;
  finished.game.legal_moves = [];
  channel.receive(finished, 1, 10);
  const seen = observeGame(client.getSnapshot(), cabinet);
  expect(client.canRequest(seen, 'rejoin')).toBe(true);
  expect(client.canRequest(seen, 'rematch')).toBe(false);
  expect(client.request(seen, 'rematch', undefined, 11)).toBe(false);
  expect(client.request(seen, 'rejoin', undefined, 12)).toBe(true);
  channel.receive(
    {
      ...finished,
      revision: 4,
      ack: 1,
      game: { ...finished.game, revision: 1, needs_rejoin: false },
      receipts: [
        {
          seq: 1,
          kind: 'game',
          outcome: {
            action_id: sent[0].action_id,
            result: 'accepted',
            round_id: round,
            revision: 1,
          },
        },
      ],
    },
    1,
    20
  );
  const resumed = observeGame(client.getSnapshot(), cabinet);
  expect(client.canRequest(resumed, 'rejoin')).toBe(false);
  expect(client.canRequest(resumed, 'rematch')).toBe(true);
  expect(sent.map(intent => intent.action)).toEqual(['rejoin']);
});
