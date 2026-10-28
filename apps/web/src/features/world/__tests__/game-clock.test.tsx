import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { GameClock } from '../games/GameClock';
import { WorldGameClient } from '../game-client';
import { worldViewSchema } from '../protocol';
import { compileGameCabinets } from '../game-catalogue';
import { WORLD } from '../definition';

vi.mock('@/i18n/client', () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, unknown>) => `${key}:${String(values?.time)}`,
  }),
}));
const epoch = '11111111-1111-4111-8111-111111111111';
function connectedClient(serverTime: number) {
  const client = new WorldGameClient();
  const channel = client.attach({ active: () => true, send: () => null });
  channel.receive(
    worldViewSchema.parse({
      version: 2,
      type: 'snapshot',
      epoch,
      revision: 1,
      server_time: serverTime,
      receipts: [],
      status: 'active',
      controlling: true,
      ack: 0,
      actors: [],
      you: {
        id: epoch,
        alias: 'Léa',
        position: compileGameCabinets(WORLD)[0].approach,
        facing: 1,
        walking: false,
      },
      position: null,
      offer_until: null,
      idle_until: 1000,
      cabinets: [],
      game: null,
      game_request: null,
    }),
    1,
    performance.now()
  );
  return { client, dispose: channel.dispose };
}
beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});
it('counts down on the server clock, one second at a time, and stops at zero', () => {
  // The server is 3600 s ahead of this page's clock: only its time is read.
  const { client, dispose } = connectedClient(3700);
  const view = render(<GameClock lng="en" client={client} deadline={3742} />);
  expect(screen.getByText('world.arcade.time_left:0:42')).toBeInTheDocument();
  act(() => vi.advanceTimersByTime(1000));
  expect(screen.getByText('world.arcade.time_left:0:41')).toBeInTheDocument();
  act(() => vi.advanceTimersByTime(45_000));
  expect(screen.getByText('world.arcade.time_left:0:00')).toBeInTheDocument();
  view.rerender(<GameClock lng="en" client={client} deadline={3800} />);
  expect(screen.getByText('world.arcade.time_left:0:54')).toBeInTheDocument();
  view.unmount();
  expect(vi.getTimerCount()).toBe(0);
  dispose();
});
it('holds no timer while the page is hidden and resumes on return', () => {
  const { client, dispose } = connectedClient(100);
  const hidden = vi.spyOn(document, 'hidden', 'get').mockReturnValue(false);
  const view = render(<GameClock lng="en" client={client} deadline={160} />);
  expect(screen.getByText('world.arcade.time_left:1:00')).toBeInTheDocument();
  expect(vi.getTimerCount()).toBe(1);
  hidden.mockReturnValue(true);
  act(() => document.dispatchEvent(new Event('visibilitychange')));
  expect(vi.getTimerCount()).toBe(0);
  act(() => vi.advanceTimersByTime(5000));
  expect(screen.getByText('world.arcade.time_left:1:00')).toBeInTheDocument();
  hidden.mockReturnValue(false);
  act(() => document.dispatchEvent(new Event('visibilitychange')));
  expect(vi.getTimerCount()).toBe(1);
  act(() => vi.advanceTimersByTime(1000));
  expect(screen.getByText('world.arcade.time_left:0:54')).toBeInTheDocument();
  view.unmount();
  expect(vi.getTimerCount()).toBe(0);
  dispose();
});
it('renders nothing before the client knows the server time', () => {
  const client = new WorldGameClient();
  const { container, unmount } = render(<GameClock lng="en" client={client} deadline={10} />);
  expect(container).toBeEmptyDOMElement();
  unmount();
  expect(vi.getTimerCount()).toBe(0);
});
