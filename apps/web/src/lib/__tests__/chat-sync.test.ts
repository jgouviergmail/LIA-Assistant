/**
 * ChatSyncController — keeping the thread in step without reloading it (ADR-320).
 *
 * Driven without React: every dependency is a fake the test controls, the read
 * of the newest page a promise the test resolves when it wants to.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ChatSyncController, SYNC_RETRY_WHILE_BUSY_MS, type ChatSyncDeps } from '@/lib/chat-sync';
import type { Message } from '@/types/chat';

interface Page {
  messages: Message[];
}

const AT = new Date('2026-09-25T10:00:00Z');

function historyRow(id: string, minute = 0): Message {
  return {
    id,
    role: 'assistant',
    content: id,
    timestamp: new Date(AT.getTime() + minute * 60_000),
    metadata: { message_db_id: id },
  };
}

/** A read the test settles when it chooses. */
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const flush = () => new Promise(resolve => setTimeout(resolve, 0));

function harness(overrides: Partial<ChatSyncDeps<Page>> = {}) {
  const state = { blocked: false, busy: false, thread: [historyRow('a')] };
  const reads: Array<ReturnType<typeof deferred<Page>>> = [];
  const timers: Array<() => void> = [];
  const deps: ChatSyncDeps<Page> = {
    enabled: () => true,
    blocked: () => state.blocked,
    readerBusy: () => state.busy,
    messages: () => state.thread,
    readNewestPage: vi.fn(() => {
      const read = deferred<Page>();
      reads.push(read);
      return read.promise;
    }),
    mergeServerPage: vi.fn(),
    onPageReplaced: vi.fn(),
    onReset: vi.fn(),
    setTimer: vi.fn((callback: () => void) => {
      timers.push(callback);
      return timers.length;
    }),
    clearTimer: vi.fn(),
    ...overrides,
  };
  return { state, reads, timers, deps, sync: new ChatSyncController(deps) };
}

let h: ReturnType<typeof harness>;

beforeEach(() => {
  h = harness();
});

describe('ChatSyncController — asks coalesce', () => {
  it('reads once per ask when nothing overlaps', async () => {
    h.sync.request('signal');
    h.reads[0].resolve({ messages: [historyRow('a'), historyRow('b', 1)] });
    await flush();

    expect(h.deps.readNewestPage).toHaveBeenCalledTimes(1);
    expect(h.deps.mergeServerPage).toHaveBeenCalledWith([historyRow('a'), historyRow('b', 1)]);
  });

  it('turns ten asks during one read into ONE more read after it', async () => {
    h.sync.request('signal');
    for (let i = 0; i < 10; i += 1) h.sync.request('signal');
    expect(h.deps.readNewestPage).toHaveBeenCalledTimes(1);

    h.reads[0].resolve({ messages: [historyRow('a')] });
    await flush();
    expect(h.deps.readNewestPage).toHaveBeenCalledTimes(2);

    h.reads[1].resolve({ messages: [historyRow('a')] });
    await flush();
    expect(h.deps.readNewestPage).toHaveBeenCalledTimes(2);
  });
});

describe('ChatSyncController — a busy thread is never touched', () => {
  it('waits while a turn streams, and runs once the thread is free', async () => {
    h.state.blocked = true;
    h.sync.request('signal');
    expect(h.deps.readNewestPage).not.toHaveBeenCalled();

    h.state.blocked = false;
    h.sync.resume();
    h.reads[0].resolve({ messages: [historyRow('a')] });
    await flush();

    expect(h.deps.mergeServerPage).toHaveBeenCalledTimes(1);
  });

  it('does not merge a page read while a turn started, and reads it again after', async () => {
    h.sync.request('signal');
    h.state.blocked = true; // the person sent a message during the read
    h.reads[0].resolve({ messages: [historyRow('a')] });
    await flush();
    expect(h.deps.mergeServerPage).not.toHaveBeenCalled();

    h.state.blocked = false;
    h.sync.resume();
    expect(h.deps.readNewestPage).toHaveBeenCalledTimes(2);
  });

  it('looks again later while the reader holds a selection, then merges', async () => {
    h.state.busy = true;
    h.sync.request('signal');
    expect(h.deps.readNewestPage).not.toHaveBeenCalled();
    expect(h.deps.setTimer).toHaveBeenCalledWith(expect.any(Function), SYNC_RETRY_WHILE_BUSY_MS);

    h.state.busy = false;
    h.timers[0]();
    h.reads[0].resolve({ messages: [historyRow('a')] });
    await flush();

    expect(h.deps.mergeServerPage).toHaveBeenCalledTimes(1);
  });

  it('does nothing while resume() has nothing asked', () => {
    h.sync.resume();

    expect(h.deps.readNewestPage).not.toHaveBeenCalled();
  });
});

describe('ChatSyncController — a failed read is not an empty conversation', () => {
  it('merges nothing and does not retry in a loop', async () => {
    h.sync.request('signal');
    h.reads[0].reject(new Error('network'));
    await flush();

    expect(h.deps.mergeServerPage).not.toHaveBeenCalled();
    expect(h.deps.readNewestPage).toHaveBeenCalledTimes(1);

    h.sync.request('visible'); // the next ask reads again
    expect(h.deps.readNewestPage).toHaveBeenCalledTimes(2);
  });
});

describe('ChatSyncController — a reset announced by the server', () => {
  it('empties the thread, but only once it is free', () => {
    h.state.blocked = true;
    h.sync.requestReset();
    expect(h.deps.onReset).not.toHaveBeenCalled();

    h.state.blocked = false;
    h.sync.resume();

    expect(h.deps.onReset).toHaveBeenCalledTimes(1);
  });
});

describe('ChatSyncController — more than a page arrived while away', () => {
  it('lets pagination restart from the page', async () => {
    h.state.thread = [historyRow('old', 0)];
    const page = { messages: [historyRow('n1', 10), historyRow('n2', 11)] };

    h.sync.request('reconnected');
    h.reads[0].resolve(page);
    await flush();

    expect(h.deps.onPageReplaced).toHaveBeenCalledWith(page);
  });
});

describe('ChatSyncController — dispose', () => {
  it('drops a read in flight and every ask after it', async () => {
    h.sync.request('signal');
    h.sync.dispose();
    h.reads[0].resolve({ messages: [historyRow('a'), historyRow('b', 1)] });
    await flush();
    h.sync.request('signal');

    expect(h.deps.mergeServerPage).not.toHaveBeenCalled();
    expect(h.deps.readNewestPage).toHaveBeenCalledTimes(1);
  });
});
