import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { WorldLink } from '../shared-link';
import { parseWorldFrame } from '../protocol';

const EPOCH = '4010c2c2-4bd0-4d21-9c08-b4502db25d72';
const SCENE = 'lia-campus:1';
export function view() {
  return {
    type: 'snapshot',
    version: 1,
    epoch: EPOCH,
    revision: 1,
    status: 'active',
    actors: [],
    you: { id: EPOCH, alias: 'Léa', position: { x: 34.5, y: 30.5 }, facing: 1, walking: false },
    ack: 0,
    position: null,
    offer_until: null,
    idle_until: 1000,
    controlling: true,
  };
}
class Socket extends EventTarget {
  static OPEN = 1;
  static sockets: Socket[] = [];
  readyState = 0;
  sent: string[] = [];
  constructor(readonly url: string) {
    super();
    Socket.sockets.push(this);
  }
  send(value: string) {
    this.sent.push(value);
  }
  open() {
    this.readyState = 1;
    this.dispatchEvent(new Event('open'));
  }
  frame(value: unknown) {
    this.dispatchEvent(new MessageEvent('message', { data: JSON.stringify(value) }));
  }
  close(code = 1000) {
    this.readyState = 3;
    this.dispatchEvent(new CloseEvent('close', { code }));
  }
}
beforeEach(() => {
  vi.useFakeTimers();
  Socket.sockets = [];
  vi.stubGlobal('WebSocket', Socket);
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function setup(ticket = vi.fn(async (_signal: AbortSignal) => 't'.repeat(43))) {
  const onStatus = vi.fn();
  const link = new WorldLink({
    url: 'ws://world.invalid/api/v1/world/ws',
    scene: SCENE,
    ticket,
    onStatus,
  });
  return { link, ticket, onStatus };
}
async function connect(link: WorldLink) {
  link.start();
  await Promise.resolve();
  const socket = Socket.sockets.at(-1)!;
  socket.open();
  socket.frame({ type: 'ready', version: 1, scene: SCENE, resume: 'r'.repeat(43) });
  socket.frame(view());
  return socket;
}

describe('bounded server projections', () => {
  it('refuses malformed versions, extra private fields and non-finite coordinates', () => {
    for (const frame of [
      { ...view(), version: true },
      { ...view(), account_id: 'private' },
      { ...view(), you: { ...view().you, position: { x: Infinity, y: 0 } } },
      { ...view(), actors: Array.from({ length: 11 }, () => view().you) },
    ])
      expect(() => parseWorldFrame(JSON.stringify(frame))).toThrow();
    expect(() => parseWorldFrame('x'.repeat(20000))).toThrow();
  });
  it('accepts international aliases by Unicode code points', () => {
    expect(
      parseWorldFrame(JSON.stringify({ ...view(), you: { ...view().you, alias: '🌿'.repeat(24) } }))
        .type
    ).toBe('snapshot');
  });
});

describe('world connection ownership', () => {
  it('exposes a private mailbox scope only to a fresh controlling world tab', async () => {
    const { link } = setup();
    expect(link.mailboxScope()).toBeNull();
    const socket = await connect(link);
    expect(link.mailboxScope()).toEqual({ epoch: EPOCH, controller: 'r'.repeat(43) });
    socket.frame({ ...view(), revision: 2, controlling: false });
    expect(link.mailboxScope()).toBeNull();
    socket.frame({ ...view(), revision: 3 });
    await vi.advanceTimersByTimeAsync(2100);
    expect(link.mailboxScope()).toBeNull();
    link.stop();
    expect(link.mailboxScope()).toBeNull();
  });
  it('renews activity only for explicit interaction, at a bounded rate, and never from the queue', async () => {
    const { link } = setup();
    const socket = await connect(link);
    link.activity();
    link.activity();
    expect(socket.sent.filter(value => JSON.parse(value).active === true)).toHaveLength(1);
    socket.frame({ ...view(), revision: 2, status: 'waiting', you: null, actors: [], position: 1 });
    await vi.advanceTimersByTimeAsync(1500);
    link.activity();
    expect(socket.sent.filter(value => JSON.parse(value).active === true)).toHaveLength(1);
    link.stop();
  });
  it('makes no request before explicit admission and never puts credentials in a URL', async () => {
    const { link, ticket } = setup();
    expect(ticket).not.toHaveBeenCalled();
    const socket = await connect(link);
    expect(socket.url).not.toContain('ticket');
    expect(JSON.parse(socket.sent[0])).toEqual({
      type: 'authenticate',
      version: 1,
      scene: SCENE,
      ticket: 't'.repeat(43),
      resume: null,
    });
    expect(link.motion({ x: 1, y: 0 })).toBe(1);
    expect(JSON.parse(socket.sent.at(-1)!)).toEqual({
      type: 'move',
      version: 1,
      epoch: EPOCH,
      seq: 1,
      dx: 1,
      dy: 0,
    });
    link.stop();
  });
  it('ignores a ticket resolved after account disposal', async () => {
    let resolve!: (token: string) => void;
    const { link } = setup(
      vi.fn(
        () =>
          new Promise<string>(done => {
            resolve = done;
          })
      )
    );
    link.start();
    link.stop();
    resolve('t'.repeat(43));
    await Promise.resolve();
    expect(Socket.sockets).toHaveLength(0);
    expect(vi.getTimerCount()).toBe(0);
  });
  it('rekeys the controller on reconnect and fences late messages from the old socket', async () => {
    const { link } = setup();
    const old = await connect(link);
    old.close(1006);
    expect(link.motion({ x: 1, y: 0 })).toBeNull();
    await vi.advanceTimersByTimeAsync(500);
    const resumed = Socket.sockets.at(-1)!;
    resumed.open();
    expect(JSON.parse(resumed.sent[0]).resume).toBe('r'.repeat(43));
    resumed.frame({ type: 'ready', version: 1, scene: SCENE, resume: 's'.repeat(43) });
    resumed.frame({ ...view(), revision: 2 });
    old.frame({ ...view(), revision: 100, controlling: false });
    expect(link.view?.revision).toBe(2);
    expect(link.motion({ x: 0, y: 1 })).toBe(1);
    link.stop();
  });
  it('does not simulate or send movement from a queue or duplicate controller', async () => {
    const { link } = setup();
    const socket = await connect(link);
    socket.frame({ ...view(), revision: 2, status: 'waiting', you: null, actors: [], position: 1 });
    expect(link.motion({ x: 1, y: 0 })).toBeNull();
    socket.frame({ ...view(), revision: 3, controlling: false });
    expect(link.motion({ x: 1, y: 0 })).toBeNull();
    link.control('takeover');
    expect(JSON.parse(socket.sent.at(-1)!).type).toBe('takeover');
    link.stop();
  });
  it('fails closed on a revoked session and on malformed server data', async () => {
    const { link } = setup();
    const socket = await connect(link);
    socket.close(4401);
    await vi.advanceTimersByTimeAsync(30000);
    expect(Socket.sockets).toHaveLength(1);
    expect(link.view).toBeNull();
    link.stop();
    const other = setup();
    const otherSocket = await connect(other.link);
    otherSocket.frame({ ...view(), owner_id: 'secret' });
    expect(other.link.view).toBeNull();
    other.link.stop();
  });
  it('freezes stale authority, bounds retries and releases every timer at teardown', async () => {
    const { link } = setup();
    await connect(link);
    await vi.advanceTimersByTimeAsync(2100);
    expect(link.motion({ x: 1, y: 0 })).toBeNull();
    await vi.advanceTimersByTimeAsync(120000);
    expect(Socket.sockets.length).toBeLessThanOrEqual(5);
    link.stop();
    expect(vi.getTimerCount()).toBe(0);
  });
  it('supports the setup-cleanup-setup lifecycle of React StrictMode', async () => {
    const { link } = setup();
    link.start();
    link.stop();
    await Promise.resolve();
    await connect(link);
    expect(link.motion({ x: 1, y: 0 })).toBe(1);
    link.stop();
  });
  it('refuses authority for a different authored collision scene', async () => {
    const { link, onStatus } = setup();
    link.start();
    await Promise.resolve();
    const socket = Socket.sockets.at(-1)!;
    socket.open();
    socket.frame({
      type: 'ready',
      version: 1,
      scene: 'lia-campus:obsolete',
      resume: 'r'.repeat(43),
    });
    socket.frame(view());
    expect(link.canMove).toBe(false);
    expect(onStatus).toHaveBeenLastCalledWith('unavailable');
    expect(vi.getTimerCount()).toBe(0);
  });
});
