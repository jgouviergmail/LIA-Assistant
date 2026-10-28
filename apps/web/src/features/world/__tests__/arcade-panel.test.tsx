import { Activity } from 'react';
import { act, cleanup, fireEvent, render, renderHook, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { WorldArcadePanel } from '../WorldArcadePanel';
import { WorldGameClient } from '../game-client';
import { worldViewSchema } from '../protocol';
import { WORLD } from '../definition';
import { compileGameCabinets } from '../game-catalogue';
import type { GameIntent, GameView } from '../game-protocol';
import { arcadeFixture } from './fixtures/arcade';
import { useWorldArcadeActivity } from '../useWorldArcadeActivity';
import type { WorldActivityEntry } from '../useWorldActivityState';
const sessions = new Set<() => void>();
afterEach(() => {
  // Unmount first: disposing a client publishes, and a mounted panel would re-render.
  cleanup();
  sessions.forEach(dispose => dispose());
  sessions.clear();
});

const lifetime = vi.hoisted(() => {
  const state = { current: true, isCurrent: () => state.current };
  return state;
});
// The transport stays active independently: an account fence must hold on its own.
const transport = { active: true };
vi.mock('@/hooks/useApplicationAccountLifetime', () => ({
  useApplicationAccountLifetime: () => ({ isCurrent: lifetime.isCurrent }),
}));
vi.mock('@/i18n/client', () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, unknown>) =>
      key + (values ? JSON.stringify(values) : ''),
  }),
}));
function setup(game: GameView | null = null) {
  lifetime.current = true;
  transport.active = true;
  const cabinet = compileGameCabinets(WORLD).find(
    item => item.id === (game?.cabinet ?? 'arcade-tic-tac-toe')
  );
  if (!cabinet) throw new Error('Unknown cabinet');
  const client = new WorldGameClient();
  const sent: GameIntent[] = [];
  const channel = client.attach({
    active: () => transport.active,
    send: intent => {
      sent.push(intent);
      return { seq: sent.length, epoch: '99999999-9999-4999-8999-999999999999', stream: 1 };
    },
  });
  sessions.add(channel.dispose);
  const frame = worldViewSchema.parse({
    version: 2,
    type: 'snapshot',
    epoch: '99999999-9999-4999-8999-999999999999',
    revision: 1,
    server_time: 100,
    receipts: [],
    status: 'active',
    controlling: true,
    ack: 0,
    actors: [],
    you: {
      id: '22222222-2222-4222-8222-222222222222',
      alias: 'Alex',
      position: cabinet.approach,
      facing: 1,
      walking: false,
    },
    position: null,
    offer_until: null,
    idle_until: 1000,
    game_request: null,
    game,
    cabinets: [
      {
        cabinet: cabinet.id,
        // Only a joinable cabinet carries a round fence; a full one never does.
        availability: game ? 'full' : 'empty',
        round_id: null,
        revision: 0,
      },
    ],
  });
  channel.receive(frame, 1, performance.now());
  const close = vi.fn();
  const ui = render(
    <WorldArcadePanel
      lng="fr"
      ownerId="owner"
      cabinet={cabinet.id}
      client={client}
      onClose={close}
    />
  );
  return { client, sent, channel, frame, close, ui };
}

it('requires an explicit opponent choice and sends no game action merely by opening a cabinet', () => {
  const { sent } = setup();
  expect(sent).toHaveLength(0);
  fireEvent.click(screen.getByRole('button', { name: 'world.arcade.computer' }));
  expect(sent).toHaveLength(1);
  expect(sent[0].action).toBe('start_computer');
  expect(screen.queryByRole('grid')).not.toBeInTheDocument();
});

it('makes the host consent explicit and warns that accepting starts a fresh board', () => {
  const game = arcadeFixture();
  game.phase = 'playing_computer';
  game.computer = true;
  game.players = game.players.slice(0, 1);
  game.pending = { id: '33333333-3333-4333-8333-333333333333', alias: 'Sam', expires_at: 120 };
  const { sent } = setup(game);
  expect(screen.getByText('world.arcade.fresh_board')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /^world.arcade.accept/ }));
  expect(sent[0]).toMatchObject({
    action: 'accept',
    round_id: game.round_id,
    expected_revision: game.revision,
  });
});

it('withdraws a private board when policy removes it and never infers a win from board pixels', () => {
  const game = arcadeFixture();
  game.phase = 'finished';
  game.reason = 'unavailable';
  game.winner = null;
  game.position.board = [1, 1, 1, 2, 2, 0, 0, 0, 0];
  game.position.result = 'one';
  game.position.turn = 2;
  game.legal_moves = [];
  const { channel, frame } = setup(game);
  expect(screen.getByText('world.arcade.ended.unavailable')).toBeInTheDocument();
  expect(screen.queryByText('world.arcade.won')).not.toBeInTheDocument();
  act(() =>
    channel.receive({ ...frame, revision: 2, game: null, cabinets: [] }, 1, performance.now())
  );
  expect(screen.queryByRole('grid')).not.toBeInTheDocument();
  expect(screen.getByText('world.arcade.unavailable')).toBeInTheDocument();
});

it('fences account loss before a stale visible button can start an interaction', () => {
  const { sent, client } = setup();
  lifetime.current = false;
  expect(transport.active).toBe(true);
  expect(client.available()).toBe(true);
  fireEvent.click(screen.getByRole('button', { name: 'world.arcade.computer' }));
  expect(sent).toHaveLength(0);
});
it('fences account loss before a stale Leave or Check the game can act', () => {
  const game = arcadeFixture();
  const { client, sent, close } = setup(game);
  fireEvent.click(screen.getByRole('gridcell', { name: /"row":1,"column":1/ }));
  expect(sent).toHaveLength(1);
  const pending = client.getSnapshot().pending;
  if (!pending) throw new Error('No pending move');
  act(() => client.tick(pending.startedAt + 5001));
  lifetime.current = false;
  fireEvent.click(screen.getByRole('button', { name: 'world.arcade.leave' }));
  fireEvent.click(screen.getByRole('button', { name: 'world.arcade.resynchronize' }));
  expect(sent).toHaveLength(1);
  expect(close).not.toHaveBeenCalled();
  expect(client.getSnapshot().pending?.uncertain).toBe(true);
});
it('keeps an aria-disabled choice inert and reports only a game that moved past the board shown', () => {
  const game = arcadeFixture();
  game.legal_moves = [{ game: 'tic_tac_toe', cell: 4 }];
  const { client, sent, channel, frame } = setup(game);
  const blocked = screen.getByRole('gridcell', { name: /"row":1,"column":1/ });
  expect(blocked).toHaveAttribute('aria-disabled', 'true');
  fireEvent.click(blocked);
  expect(sent).toHaveLength(0);
  expect(screen.queryByText('world.arcade.changed')).not.toBeInTheDocument();
  // The click lands while the client holds a newer revision the panel has not rendered yet.
  const legal = screen.getByRole('gridcell', { name: /"row":2,"column":2/ });
  act(() => {
    channel.receive({ ...frame, revision: 2, game: { ...game, revision: 1 } }, 1);
    fireEvent.click(legal);
  });
  expect(client.getSnapshot().game?.revision).toBe(1);
  expect(sent).toHaveLength(0);
  expect(screen.getByText('world.arcade.changed')).toHaveAttribute('role', 'status');
});

it('preserves the focused choice while pending, reports a refusal and allows deliberate recovery', () => {
  const { sent, channel, frame } = setup();
  const choice = screen.getByRole('button', { name: 'world.arcade.computer' });
  choice.focus();
  fireEvent.click(choice);
  expect(choice).toHaveFocus();
  expect(choice).toHaveAttribute('aria-disabled', 'true');
  fireEvent.click(choice);
  expect(sent).toHaveLength(1);
  act(() =>
    channel.receive(
      {
        ...frame,
        revision: 2,
        receipts: [
          {
            seq: 1,
            kind: 'game',
            outcome: {
              action_id: sent[0].action_id,
              result: 'rate_limited',
              round_id: null,
              revision: 0,
            },
          },
        ],
      },
      1
    )
  );
  expect(screen.getByRole('status')).toHaveTextContent('world.arcade.feedback.rate_limited');
  fireEvent.click(choice);
  expect(sent).toHaveLength(2);
});

it('never retries an uncertain command until the owner explicitly checks the current game', () => {
  const { client, sent } = setup();
  fireEvent.click(screen.getByRole('button', { name: 'world.arcade.computer' }));
  const pending = client.getSnapshot().pending;
  if (!pending) throw new Error('No pending choice');
  act(() => client.tick(pending.startedAt + 5001));
  expect(screen.getByText('world.arcade.uncertain')).toBeInTheDocument();
  expect(sent).toHaveLength(1);
  fireEvent.click(screen.getByRole('button', { name: 'world.arcade.resynchronize' }));
  expect(client.getSnapshot().pending).toBeNull();
  expect(sent).toHaveLength(1);
});

it('allows a waiting host to choose the computer and withdraws an unaccepted guest request', () => {
  const game = arcadeFixture();
  game.phase = 'waiting';
  game.players = game.players.slice(0, 1);
  game.legal_moves = [];
  const { sent, channel, frame, close } = setup(game);
  fireEvent.click(screen.getByRole('button', { name: 'world.arcade.computer' }));
  expect(sent[0].action).toBe('start_computer');
  act(() =>
    channel.receive(
      {
        ...frame,
        revision: 2,
        game: null,
        game_request: {
          cabinet: game.cabinet,
          round_id: game.round_id,
          revision: 2,
          expires_at: 120,
        },
      },
      2
    )
  );
  expect(screen.getByText('world.arcade.requested')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'world.arcade.cancel_request' }));
  expect(sent.at(-1)?.action).toBe('leave');
  expect(close).toHaveBeenCalledOnce();
});

it('requires deliberate rejoin and both human rematch choices, with no speculative new board', () => {
  const game = arcadeFixture();
  game.needs_rejoin = true;
  game.paused = true;
  game.legal_moves = [];
  const { sent, channel, frame } = setup(game);
  expect(screen.queryByRole('grid')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'world.arcade.resume' }));
  expect(sent[0].action).toBe('rejoin');
  const finished = {
    ...game,
    revision: 3,
    needs_rejoin: false,
    paused: false,
    phase: 'finished' as const,
    reason: 'draw' as const,
  };
  act(() => channel.receive({ ...frame, revision: 3, game: finished }, 2));
  const replay = screen.getByRole('button', { name: 'world.arcade.rematch' });
  replay.focus();
  fireEvent.click(replay);
  expect(replay).toHaveFocus();
  expect(sent.at(-1)?.action).toBe('rematch');
  expect(screen.getByText('world.arcade.ended.draw')).toHaveAttribute('role', 'status');
  const action = sent.at(-1);
  if (!action) throw new Error('No rematch');
  act(() =>
    channel.receive(
      {
        ...frame,
        revision: 4,
        game: { ...finished, revision: 4, rematch_ready: [1] },
        receipts: [
          {
            seq: 2,
            kind: 'game',
            outcome: {
              action_id: action.action_id,
              result: 'accepted',
              round_id: game.round_id,
              revision: 4,
            },
          },
        ],
      },
      2
    )
  );
  expect(screen.getByRole('button', { name: 'world.arcade.rematch_requested' })).toHaveAttribute(
    'aria-pressed',
    'true'
  );
  expect(screen.getByRole('grid')).toBeInTheDocument();
});

it.each(['four_in_row', 'reversi'] as const)(
  'renders %s only from its typed native cabinet projection',
  kind => {
    const game = arcadeFixture(kind);
    const { sent } = setup(game);
    expect(screen.getByRole(kind === 'reversi' ? 'grid' : 'table')).toBeInTheDocument();
    expect(sent).toEqual([]);
  }
);

it('withdraws exactly once on native navigation and never on initial panel mounting', () => {
  const game = arcadeFixture();
  const { client, sent } = setup(game);
  const hook = renderHook(
    ({ entry }: { entry: WorldActivityEntry }) => useWorldArcadeActivity(client, entry, key => key),
    { initialProps: { entry: { selection: 'world-arcade', cabinet: game.cabinet } } }
  );
  expect(sent).toHaveLength(0);
  hook.rerender({ entry: { selection: null, cabinet: undefined } });
  expect(sent.filter(intent => intent.action === 'leave')).toHaveLength(1);
  hook.unmount();
  expect(sent.filter(intent => intent.action === 'leave')).toHaveLength(1);
});

it('keeps a requester outside the private board until the host actually accepts', () => {
  const { channel, frame, sent } = setup();
  const round = '11111111-1111-4111-8111-111111111111';
  act(() =>
    channel.receive(
      {
        ...frame,
        revision: 2,
        cabinets: [
          { cabinet: 'arcade-tic-tac-toe', availability: 'joinable', round_id: round, revision: 1 },
        ],
      },
      1
    )
  );
  expect(screen.queryByRole('grid')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'world.arcade.join' }));
  expect(sent[0]).toMatchObject({ action: 'request', round_id: round });
  expect(screen.queryByRole('grid')).not.toBeInTheDocument();
});

it('withdraws a board during transport loss and offers a deliberate departure from another cabinet', () => {
  const game = arcadeFixture();
  const { channel, ui, client, sent } = setup(game);
  act(() => channel.suspend('reconnecting'));
  expect(screen.queryByRole('grid')).not.toBeInTheDocument();
  expect(screen.getByText('world.arcade.unavailable')).toBeInTheDocument();
  // A new current transport may retain membership but must not display it in another cabinet.
  const frame = worldViewSchema.parse({
    version: 2,
    type: 'snapshot',
    epoch: '99999999-9999-4999-8999-999999999999',
    revision: 5,
    server_time: 100,
    receipts: [],
    status: 'active',
    controlling: true,
    ack: 0,
    actors: [],
    you: {
      id: '22222222-2222-4222-8222-222222222222',
      alias: 'Alex',
      position: { x: 1, y: 1 },
      facing: 1,
      walking: false,
    },
    position: null,
    offer_until: null,
    idle_until: 1000,
    game,
    cabinets: [{ cabinet: game.cabinet, availability: 'full', round_id: null, revision: 0 }],
  });
  act(() => channel.receive(frame, 2));
  ui.rerender(
    <WorldArcadePanel
      lng="fr"
      ownerId="owner"
      cabinet="arcade-reversi"
      client={client}
      onClose={() => {}}
    />
  );
  expect(screen.getByText('world.arcade.elsewhere')).toBeInTheDocument();
  expect(screen.queryByRole('grid')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'world.arcade.leave_other_cabinet' }));
  expect(sent[0].action).toBe('leave');
});
it('sends no game action when a private board is hidden and revealed again', () => {
  const game = arcadeFixture();
  const { client, sent, ui } = setup(game);
  const panel = (mode: 'visible' | 'hidden') => (
    <Activity mode={mode}>
      <WorldArcadePanel
        lng="fr"
        ownerId="owner"
        cabinet={game.cabinet}
        client={client}
        onClose={() => {}}
      />
    </Activity>
  );
  ui.unmount();
  const view = render(panel('visible'));
  const focused = screen.getByRole('gridcell', { name: /"row":2,"column":2/ });
  act(() => focused.focus());
  for (const mode of ['hidden', 'visible', 'hidden', 'visible'] as const)
    view.rerender(panel(mode));
  expect(sent).toEqual([]);
  expect(screen.getByRole('grid')).toBeInTheDocument();
  expect(focused).toHaveFocus();
});
it('lets a rotated controller resume a finished table on its result screen, then rematch', () => {
  const game = arcadeFixture();
  game.phase = 'finished';
  game.reason = 'draw';
  game.needs_rejoin = true;
  game.legal_moves = [];
  const { sent, channel, frame } = setup(game);
  expect(screen.getByText('world.arcade.ended.draw')).toHaveAttribute('role', 'status');
  expect(screen.getByRole('grid')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'world.arcade.rematch' })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'world.arcade.resume' }));
  expect(sent.map(intent => intent.action)).toEqual(['rejoin']);
  act(() =>
    channel.receive(
      {
        ...frame,
        revision: 2,
        ack: 1,
        game: { ...game, revision: 1, needs_rejoin: false },
        receipts: [
          {
            seq: 1,
            kind: 'game',
            outcome: {
              action_id: sent[0].action_id,
              result: 'accepted',
              round_id: game.round_id,
              revision: 1,
            },
          },
        ],
      },
      1
    )
  );
  expect(screen.queryByRole('button', { name: 'world.arcade.resume' })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'world.arcade.rematch' }));
  expect(sent.map(intent => intent.action)).toEqual(['rejoin', 'rematch']);
});
