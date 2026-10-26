import { WORLD } from '../definition';
import { StrictMode } from 'react';
import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useWorldSession } from '../useWorldSession';

const mutation = vi.hoisted(() => ({ mutate: vi.fn() }));
vi.mock('@/hooks/useApiMutation', () => ({ useApiMutation: () => mutation }));

class Socket extends EventTarget {
  static OPEN = 1;
  static instances: Socket[] = [];
  readyState = 0;
  bufferedAmount = 0;
  sent: string[] = [];
  send(frame: string) {
    this.sent.push(frame);
  }
  constructor(readonly url: string) {
    super();
    Socket.instances.push(this);
  }
  close() {
    this.readyState = 3;
  }
}
interface Ticket {
  account_id: string;
  version: number;
  ticket: string;
}
interface Pending {
  signal: AbortSignal;
  resolve(ticket: Ticket): void;
}
let pending: Pending[];
const owner = '11111111-1111-4111-8111-111111111111';
const peer = '22222222-2222-4222-8222-222222222222';
const ticket = (account_id: string): Ticket => ({ account_id, version: 1, ticket: 't'.repeat(43) });
async function flushSetup() {
  await act(async () => {
    await Promise.resolve();
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal('WebSocket', Socket);
  Socket.instances = [];
  pending = [];
  mutation.mutate
    .mockReset()
    .mockImplementation(
      (_url, _body, options: { signal: AbortSignal }) =>
        new Promise<Ticket>(resolve => pending.push({ signal: options.signal, resolve }))
    );
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('world account lifetime at the API boundary', () => {
  it('publishes social identities without rerendering for movement-only frames', async () => {
    const { result, unmount } = renderHook(() => useWorldSession(owner, 'Owner'));
    expect(result.current.active).toBe(false);
    expect(result.current.recovering).toBe(false);
    await flushSetup();
    await act(async () => pending[0].resolve(ticket(owner)));
    const socket = Socket.instances[0];
    socket.readyState = 1;
    const frame = (value: unknown) =>
      socket.dispatchEvent(new MessageEvent('message', { data: JSON.stringify(value) }));
    const snapshot = {
      type: 'snapshot',
      version: 1,
      epoch: owner,
      revision: 1,
      status: 'active',
      actors: [{ id: peer, alias: 'Peer', facing: 1, walking: false, position: { x: 30, y: 30 } }],
      you: { id: owner, alias: 'Owner', facing: 1, walking: false, position: { x: 34.5, y: 30.5 } },
      ack: 0,
      position: null,
      offer_until: null,
      idle_until: 1000,
      controlling: true,
    };
    act(() => {
      frame({
        type: 'ready',
        version: 1,
        scene: `${WORLD.id}:${WORLD.version}`,
        resume: 'c'.repeat(43),
      });
      frame(snapshot);
    });
    expect(result.current.presentation.participants).toEqual([{ id: peer, alias: 'Peer' }]);
    expect(result.current.active).toBe(true);
    expect(result.current.recovering).toBe(false);
    const presentation = result.current.presentation;
    act(() =>
      frame({
        ...snapshot,
        revision: 2,
        actors: [{ ...snapshot.actors[0], position: { x: 31, y: 30 } }],
      })
    );
    expect(result.current.presentation).toBe(presentation);
    expect(result.current.mailboxScope()).toEqual({ epoch: owner, controller: 'c'.repeat(43) });
    act(() => socket.dispatchEvent(new CloseEvent('close', { code: 1013 })));
    expect(result.current.active).toBe(false);
    expect(result.current.recovering).toBe(true);
    expect(result.current.mailboxScope()).toBeNull();
    unmount();
  });
  it('does not retain private authority when an initial connection failed before admission', async () => {
    const { result, unmount } = renderHook(() => useWorldSession(owner, 'Owner'));
    await flushSetup();
    await act(async () => pending[0].resolve(ticket(owner)));
    act(() => Socket.instances[0].dispatchEvent(new Event('error')));
    expect(result.current.active).toBe(false);
    expect(result.current.recovering).toBe(false);
    expect(result.current.mailboxScope()).toBeNull();
    unmount();
  });
  it('aborts admission on teardown and ignores a response that arrives afterwards', async () => {
    const { unmount } = renderHook(() => useWorldSession(owner, 'Owner'));
    await flushSetup();
    expect(pending).toHaveLength(1);
    unmount();
    expect(pending[0].signal.aborted).toBe(true);
    await act(async () => pending[0].resolve(ticket(owner)));
    expect(Socket.instances).toHaveLength(0);
    expect(vi.getTimerCount()).toBe(0);
  });
  it('cannot open an old account socket after switching accounts', async () => {
    const { rerender, unmount } = renderHook(({ id }) => useWorldSession(id, 'Alias'), {
      initialProps: { id: owner },
    });
    await flushSetup();
    rerender({ id: peer });
    await flushSetup();
    expect(pending).toHaveLength(2);
    expect(pending[0].signal.aborted).toBe(true);
    await act(async () => pending[0].resolve(ticket(owner)));
    expect(Socket.instances).toHaveLength(0);
    await act(async () => pending[1].resolve(ticket(peer)));
    expect(Socket.instances).toHaveLength(1);
    expect(Socket.instances[0].url).not.toContain('ticket');
    unmount();
    expect(Socket.instances[0].readyState).toBe(3);
    expect(vi.getTimerCount()).toBe(0);
  });
  it('refuses a ticket minted for a different browser account', async () => {
    const { result, unmount } = renderHook(() => useWorldSession(owner, 'Owner'));
    await flushSetup();
    await act(async () => pending[0].resolve(ticket(peer)));
    expect(Socket.instances).toHaveLength(0);
    expect(result.current.presentation.connection).toBe('reconnecting');
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
  it('owns only the live StrictMode setup and releases its socket and timers', async () => {
    const { unmount } = renderHook(() => useWorldSession(owner, 'Owner'), { wrapper: StrictMode });
    await flushSetup();
    expect(pending).toHaveLength(1);
    await act(async () => {
      pending[0].resolve(ticket(owner));
    });
    expect(Socket.instances).toHaveLength(1);
    unmount();
    expect(Socket.instances[0].readyState).toBe(3);
    expect(vi.getTimerCount()).toBe(0);
  });
  it('does not mint any ticket when the route is left before its setup starts', async () => {
    const { unmount } = renderHook(() => useWorldSession(owner, 'Owner'));
    unmount();
    await flushSetup();
    expect(mutation.mutate).not.toHaveBeenCalled();
    expect(Socket.instances).toHaveLength(0);
    expect(vi.getTimerCount()).toBe(0);
  });
});

it('opens a linked seat only after its own server acknowledgment and never on reconnect replay', async () => {
  const opened = vi.fn();
  const { result, unmount } = renderHook(() => useWorldSession(owner, 'Owner', opened));
  await flushSetup();
  await act(async () => pending[0].resolve(ticket(owner)));
  const socket = Socket.instances[0];
  socket.readyState = 1;
  const slot = (await import('../pose-slots')).compilePoseSlots(WORLD)[0];
  const frame = (v: unknown) =>
    socket.dispatchEvent(new MessageEvent('message', { data: JSON.stringify(v) }));
  const view = {
    type: 'snapshot',
    version: 1,
    epoch: owner,
    revision: 1,
    status: 'active',
    actors: [],
    you: {
      id: owner,
      alias: 'Owner',
      facing: 1,
      walking: false,
      position: slot.approach,
      pose: null,
    },
    ack: 0,
    position: null,
    offer_until: null,
    idle_until: 1000,
    controlling: true,
  };
  act(() => {
    frame({
      type: 'ready',
      version: 1,
      scene: WORLD.id + ':' + WORLD.version,
      resume: 'c'.repeat(43),
    });
    frame(view);
  });
  expect(result.current.pose.request(slot.id)).toBe(true);
  expect(opened).not.toHaveBeenCalled();
  act(() =>
    frame({
      ...view,
      revision: 2,
      ack: 1,
      pose_result: 'accepted',
      you: { ...view.you, position: slot.position, pose: slot.id },
    })
  );
  expect(opened).toHaveBeenCalledExactlyOnceWith(slot.id);
  act(() =>
    frame({
      ...view,
      revision: 3,
      ack: 1,
      pose_result: 'accepted',
      you: { ...view.you, position: slot.position, pose: slot.id },
    })
  );
  expect(opened).toHaveBeenCalledTimes(1);
  unmount();
});
