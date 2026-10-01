/**
 * LiveStandby — the live standby's policy (ADR-329), with the wire, the API
 * and the wake word faked.
 *
 *  - enter: the wire closed first (nothing bills from here), then the API told
 *    with the closed connection's conversation id; the store asleep with its
 *    bound; the wake word listening in the person's language;
 *  - a standby the API refuses ends the session; a gone record is superseded;
 *  - the bound ends the session as expired, never before, and a wake clears it;
 *  - wake: the wake word paused before the request; on success the store
 *    connecting, the wire opened on the kept handle, the cap armed, and the
 *    chime only for the phrase;
 *  - a provider refusal is retried once without the handle on a fresh
 *    credential, then the session goes back to sleep (`wake_failed`);
 *  - the refusal matrix: 404 superseded, `session_awake` ends, `session_expired`
 *    offers the extension (granted, it wakes), anything else stays asleep,
 *    says so and listens again;
 *  - the wake word listens only on a visible page, and degrades to the button.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import type { Language } from '@/i18n/settings';
import type { WakeListenerState } from '@/lib/audio/wake-word/listener';
import { useLiveStore } from '@/stores/liveStore';

import {
  LiveStandby,
  type LiveWakeListener,
  type LiveWakeListenerOptions,
  type StandbyWire,
} from '../standby';
import type { LiveCredential } from '../types';

const SESSION = 'b'.repeat(32);
const NOW = Date.parse('2026-10-01T08:00:00Z');
const DEADLINE_MS = 8 * 3600 * 1000;

const CREDENTIAL: LiveCredential = {
  credential: 'tok-wake',
  credential_expires_at: new Date(NOW + 30 * 60_000).toISOString(),
  connect_deadline_at: new Date(NOW + 60_000).toISOString(),
  connection: 'token',
  setup: { model: 'models/m', at: 'wake' },
};

function apiError(status: number, code?: string): Error {
  return Object.assign(new Error(code ?? 'failed'), {
    status,
    ...(code ? { data: { detail: { code, message: code } } } : {}),
  });
}

class FakeListener implements LiveWakeListener {
  phrase: string | null = null;
  listens: Language[] = [];
  pauses = 0;
  disposed = false;
  refuse = false;
  constructor(readonly options: LiveWakeListenerOptions) {}
  async listen(language: Language): Promise<WakeListenerState> {
    this.listens.push(language);
    if (this.refuse) throw Object.assign(new Error('denied'), { name: 'NotAllowedError' });
    this.phrase = 'Dis LIA';
    this.options.onStateChange('listening');
    return 'listening';
  }
  async pause(): Promise<void> {
    this.pauses += 1;
    this.options.onStateChange('idle');
  }
  async dispose(): Promise<void> {
    this.disposed = true;
  }
}

interface Harness {
  standby: LiveStandby;
  wire: StandbyWire & {
    close: ReturnType<typeof vi.fn>;
    open: ReturnType<typeof vi.fn>;
    end: ReturnType<typeof vi.fn>;
    armExpiry: ReturnType<typeof vi.fn>;
    forgetConversation: ReturnType<typeof vi.fn>;
  };
  post: ReturnType<typeof vi.fn>;
  listener: () => FakeListener | null;
  chime: ReturnType<typeof vi.fn>;
}

function build(
  answer: (url: string, body?: unknown) => Promise<unknown> = async () => ({}),
  options: { listener?: boolean; language?: Language | null; refuse?: boolean } = {}
): Harness {
  let listener: FakeListener | null = null;
  const post = vi.fn(async (url: string, body?: unknown): Promise<unknown> => {
    if (url.endsWith('/standby')) {
      const fromAnswer = await answer(url, body);
      return {
        standby_since: new Date(Date.now()).toISOString(),
        awake_seconds: 60,
        standby_deadline_at: new Date(Date.now() + DEADLINE_MS).toISOString(),
        relay: null,
        ...(fromAnswer as object),
      };
    }
    if (url.endsWith('/wake')) {
      const fromAnswer = await answer(url, body);
      return {
        credential: CREDENTIAL,
        expires_at: new Date(Date.now() + 9 * 60_000).toISOString(),
        extensions: 0,
        ...(fromAnswer as object),
      };
    }
    if (url.endsWith('/credential')) {
      await answer(url, body);
      return { ...CREDENTIAL, credential: 'tok-fresh' };
    }
    return answer(url, body);
  });
  const wire = {
    close: vi.fn(async () => true),
    conversationId: () => 'conv_1',
    forgetConversation: vi.fn(),
    open: vi.fn(async () => {
      useLiveStore.getState().apply('setup_complete');
      return true;
    }),
    armExpiry: vi.fn(),
    end: vi.fn(async () => {
      useLiveStore.getState().apply('end');
    }),
  };
  const chime = vi.fn();
  const standby = new LiveStandby(
    {
      api: {
        async post<T>(url: string, body?: unknown): Promise<T> {
          return (await post(url, body)) as T;
        },
      },
      createWakeListener:
        options.listener === false
          ? () => null
          : listenerOptions => {
              listener = new FakeListener(listenerOptions);
              listener.refuse = options.refuse ?? false;
              return listener;
            },
      wakeLanguage: () => (options.language === undefined ? 'fr' : options.language),
      chime,
    },
    wire
  );
  return { standby, wire, post, listener: () => listener, chime };
}

function live(): void {
  const store = useLiveStore.getState();
  store.begin(SESSION);
  store.apply('minted');
  store.apply('setup_complete');
  store.markLive(Date.now());
}

async function asleep(h: Harness): Promise<void> {
  live();
  await h.standby.enter(SESSION, 'idle');
  await vi.advanceTimersByTimeAsync(0);
}

describe('LiveStandby', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
    useLiveStore.getState().reset();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('closes the wire, tells the API, sleeps with its bound and listens for the phrase', async () => {
    const h = build();
    live();
    await h.standby.enter(SESSION, 'idle');
    await vi.advanceTimersByTimeAsync(0);
    // The wire closed BEFORE the request: nothing bills from the decision on.
    expect(h.wire.close.mock.invocationCallOrder[0]).toBeLessThan(
      h.post.mock.invocationCallOrder[0]
    );
    expect(h.post).toHaveBeenCalledWith(`/live/sessions/${SESSION}/standby`, {
      reason: 'idle',
      provider_conversation_id: 'conv_1',
    });
    expect(h.wire.forgetConversation).toHaveBeenCalledTimes(1);
    const state = useLiveStore.getState();
    expect(state.status).toBe('standby');
    expect(state.standbys).toBe(1);
    expect(state.standbyDeadline).toBe(NOW + DEADLINE_MS);
    expect(h.listener()?.listens).toEqual(['fr']);
    expect(state.wakeWordState).toBe('listening');
    expect(state.wakePhrase).toBe('Dis LIA');
  });

  it('sleeps only a live session, once at a time', async () => {
    const h = build();
    await h.standby.enter(SESSION, 'manual');
    expect(h.wire.close).not.toHaveBeenCalled();

    live();
    let release: () => void = () => {};
    h.wire.close.mockImplementationOnce(
      () =>
        new Promise<boolean>(resolve => {
          release = () => resolve(true);
        })
    );
    const first = h.standby.enter(SESSION, 'manual');
    await h.standby.enter(SESSION, 'idle');
    release();
    await first;
    expect(h.wire.close).toHaveBeenCalledTimes(1);
    expect(h.post).toHaveBeenCalledTimes(1);
  });

  it('asks nothing of the API when the session went away while its wire closed', async () => {
    const h = build();
    live();
    h.wire.close.mockResolvedValueOnce(false);
    await h.standby.enter(SESSION, 'idle');
    expect(h.post).not.toHaveBeenCalled();
    expect(useLiveStore.getState().status).toBe('live');
  });

  it('ends the session when the API refuses the standby, superseded when the record is gone', async () => {
    const h = build(async () => {
      throw apiError(503, 'live_unavailable');
    });
    live();
    await h.standby.enter(SESSION, 'idle');
    expect(h.wire.end).toHaveBeenCalledWith('error', 'live_unavailable');
    expect(h.wire.forgetConversation).not.toHaveBeenCalled();
    expect(h.listener()).toBeNull();

    useLiveStore.getState().reset();
    const g = build(async () => {
      throw apiError(404);
    });
    live();
    await g.standby.enter(SESSION, 'idle');
    expect(g.wire.end).toHaveBeenCalledWith('superseded', null);
  });

  it('drops a standby answer that arrives after the session ended', async () => {
    let answer: () => void = () => {};
    const h = build(
      url =>
        new Promise(resolve => {
          if (url.endsWith('/standby')) answer = () => resolve({});
        })
    );
    live();
    const entering = h.standby.enter(SESSION, 'idle');
    await vi.advanceTimersByTimeAsync(0);
    useLiveStore.getState().apply('end');
    answer();
    await entering;
    expect(useLiveStore.getState().status).toBe('ending');
    expect(h.listener()).toBeNull();
  });

  it('a slow answer for an ended session never sleeps, wakes or ends the next one', async () => {
    let answer: (fail: boolean) => void = () => {};
    const h = build(
      url =>
        new Promise((resolve, reject) => {
          if (url.endsWith('/standby')) {
            answer = fail => (fail ? reject(apiError(503, 'live_unavailable')) : resolve({}));
          } else resolve({});
        })
    );
    live();
    const entering = h.standby.enter(SESSION, 'idle');
    await vi.advanceTimersByTimeAsync(0);
    // The person ended it, then opened another session, live before the answer came.
    useLiveStore.getState().apply('end');
    const next = 'c'.repeat(32);
    useLiveStore.getState().begin(next);
    useLiveStore.getState().apply('minted');
    useLiveStore.getState().apply('setup_complete');
    answer(true);
    await entering;
    expect(h.wire.end).not.toHaveBeenCalled();
    expect(useLiveStore.getState()).toMatchObject({ sessionId: next, status: 'live', standbys: 0 });

    // A wake answered for an ended session opens nothing on the next one.
    useLiveStore.getState().reset();
    let woke: () => void = () => {};
    const g = build(
      url =>
        new Promise(resolve => {
          if (url.endsWith('/wake')) woke = () => resolve({});
          else resolve({});
        })
    );
    await asleep(g);
    const waking = g.standby.wake(SESSION, 'manual');
    await vi.advanceTimersByTimeAsync(0);
    useLiveStore.getState().apply('end');
    useLiveStore.getState().begin(next);
    useLiveStore.getState().apply('minted');
    useLiveStore.getState().apply('setup_complete');
    useLiveStore.getState().enterStandby({ at: Date.now(), deadline: Date.now() + 1_000 });
    woke();
    await waking;
    expect(g.wire.open).not.toHaveBeenCalled();
    expect(useLiveStore.getState()).toMatchObject({ sessionId: next, status: 'standby' });
  });

  it('ends the session as expired at its bound, not before', async () => {
    const h = build();
    await asleep(h);
    await vi.advanceTimersByTimeAsync(DEADLINE_MS - 1);
    expect(h.wire.end).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(2);
    expect(h.wire.end).toHaveBeenCalledWith('expired');
  });

  it('wakes on the button: the phrase paused first, a new connection on the kept handle, the cap armed, no chime', async () => {
    const h = build();
    await asleep(h);
    await h.standby.wake(SESSION, 'manual');
    const listener = h.listener();
    expect(listener?.pauses).toBe(1);
    expect(h.post).toHaveBeenLastCalledWith(`/live/sessions/${SESSION}/wake`, {
      reason: 'manual',
    });
    expect(h.wire.open).toHaveBeenCalledWith(CREDENTIAL, true);
    expect(h.wire.armExpiry).toHaveBeenCalledWith(new Date(NOW + 9 * 60_000).toISOString(), 0);
    expect(useLiveStore.getState().status).toBe('live');
    expect(useLiveStore.getState().standbySince).toBeNull();
    expect(h.chime).not.toHaveBeenCalled();
    // The bound no longer runs once awake.
    await vi.advanceTimersByTimeAsync(DEADLINE_MS + 1);
    expect(h.wire.end).not.toHaveBeenCalled();
  });

  it('wakes on the phrase and chimes once the provider is ready', async () => {
    const h = build();
    await asleep(h);
    h.wire.open.mockImplementationOnce(async () => {
      expect(h.chime).not.toHaveBeenCalled();
      useLiveStore.getState().apply('setup_complete');
      return true;
    });
    h.listener()?.options.onDetected();
    await vi.advanceTimersByTimeAsync(0);
    expect(h.post).toHaveBeenLastCalledWith(`/live/sessions/${SESSION}/wake`, {
      reason: 'wake_word',
    });
    expect(h.chime).toHaveBeenCalledTimes(1);
  });

  it('ignores a wake while awake, and a second wake while one runs', async () => {
    const h = build();
    live();
    await h.standby.wake(SESSION, 'manual');
    expect(h.post).not.toHaveBeenCalled();

    await h.standby.enter(SESSION, 'idle');
    let answer: () => void = () => {};
    const g = h;
    g.post.mockImplementationOnce(
      () =>
        new Promise(resolve => {
          answer = () =>
            resolve({
              credential: CREDENTIAL,
              expires_at: new Date(NOW + 60_000).toISOString(),
              extensions: 0,
            });
        })
    );
    const first = g.standby.wake(SESSION, 'manual');
    await g.standby.wake(SESSION, 'wake_word');
    answer();
    await first;
    expect(g.post.mock.calls.filter(([url]) => String(url).endsWith('/wake'))).toHaveLength(1);
  });

  it('retries a refused connection once without the handle, on a fresh credential', async () => {
    const h = build();
    await asleep(h);
    h.wire.open.mockRejectedValueOnce(new Error('live_socket_closed_1008'));
    await h.standby.wake(SESSION, 'manual');
    expect(h.post).toHaveBeenCalledWith(`/live/sessions/${SESSION}/credential`, {});
    expect(h.wire.open.mock.calls).toEqual([
      [CREDENTIAL, true],
      [{ ...CREDENTIAL, credential: 'tok-fresh' }, false],
    ]);
    expect(useLiveStore.getState().status).toBe('live');
  });

  it('goes back to sleep when the provider refuses the wake twice, and says so', async () => {
    const h = build();
    await asleep(h);
    h.wire.open.mockRejectedValue(new Error('live_socket_closed_1011'));
    await h.standby.wake(SESSION, 'wake_word');
    await vi.advanceTimersByTimeAsync(0);
    expect(h.post).toHaveBeenLastCalledWith(`/live/sessions/${SESSION}/standby`, {
      reason: 'wake_failed',
      provider_conversation_id: 'conv_1',
    });
    const state = useLiveStore.getState();
    expect(state.status).toBe('standby');
    expect(state.standbys).toBe(2);
    expect(state.wakeRefusal).toEqual({ code: null });
    // Listening again for the next try, and no chime for a wake that failed.
    expect(h.listener()?.listens).toEqual(['fr', 'fr']);
    expect(h.chime).not.toHaveBeenCalled();
    expect(h.wire.end).not.toHaveBeenCalled();
  });

  it('a session gone while it woke is superseded; one that ended meanwhile is left alone', async () => {
    const h = build(async url => {
      if (url.endsWith('/credential')) throw apiError(404);
      return {};
    });
    await asleep(h);
    h.wire.open.mockRejectedValueOnce(new Error('live_socket_closed_1006'));
    await h.standby.wake(SESSION, 'manual');
    expect(h.wire.end).toHaveBeenCalledWith('superseded');

    useLiveStore.getState().reset();
    let answer: () => void = () => {};
    const g = build(
      url =>
        new Promise(resolve => {
          if (url.endsWith('/wake')) answer = () => resolve({});
          else resolve({});
        })
    );
    await asleep(g);
    const waking = g.standby.wake(SESSION, 'manual');
    await vi.advanceTimersByTimeAsync(0);
    useLiveStore.getState().apply('end');
    answer();
    await waking;
    expect(g.wire.open).not.toHaveBeenCalled();
    expect(useLiveStore.getState().status).toBe('ending');
  });

  it.each([
    ['a gone record', apiError(404), 'superseded', null],
    ['an awake record', apiError(409, 'session_awake'), 'error', 'session_awake'],
  ])('ends the session on %s', async (_label, error, outcome, code) => {
    const h = build(async url => {
      if (url.endsWith('/wake')) throw error;
      return {};
    });
    await asleep(h);
    await h.standby.wake(SESSION, 'manual');
    expect(h.wire.end).toHaveBeenCalledWith(outcome, ...(code === null ? [] : [code]));
    expect(h.wire.open).not.toHaveBeenCalled();
  });

  it.each([
    ['a rate limit', apiError(429, 'live_mint_rate_limited'), 'live_mint_rate_limited'],
    ['a busy instance', apiError(409, 'live_instance_busy'), 'live_instance_busy'],
    ['the network', new TypeError('Failed to fetch'), null],
  ])('stays asleep on %s, says so and listens again', async (_label, error, code) => {
    const h = build(async url => {
      if (url.endsWith('/wake')) throw error;
      return {};
    });
    await asleep(h);
    await h.standby.wake(SESSION, 'wake_word');
    await vi.advanceTimersByTimeAsync(0);
    const state = useLiveStore.getState();
    expect(state.status).toBe('standby');
    expect(state.wakeRefusal).toEqual({ code });
    expect(h.listener()?.listens).toEqual(['fr', 'fr']);
    expect(h.wire.end).not.toHaveBeenCalled();
    // The bound still runs.
    await vi.advanceTimersByTimeAsync(DEADLINE_MS);
    expect(h.wire.end).toHaveBeenCalledWith('expired');
  });

  it('offers the extension when the cap is spent, and wakes once it is granted', async () => {
    let expired = true;
    const h = build(async url => {
      if (url.endsWith('/wake') && expired) {
        expired = false;
        throw apiError(409, 'session_expired');
      }
      return {};
    });
    await asleep(h);
    await h.standby.wake(SESSION, 'wake_word');
    expect(useLiveStore.getState().extensionOffered).toBe(true);
    expect(useLiveStore.getState().status).toBe('standby');
    expect(h.wire.open).not.toHaveBeenCalled();
    await h.standby.extended(SESSION);
    expect(h.wire.open).toHaveBeenCalledTimes(1);
    expect(h.chime).toHaveBeenCalledTimes(1);
    // Granted once: a later extension wakes nothing more.
    await h.standby.extended(SESSION);
    expect(h.wire.open).toHaveBeenCalledTimes(1);
  });

  it('listens only on a visible page', async () => {
    const h = build();
    h.standby.pageHidden(true);
    await asleep(h);
    // Asleep on a hidden page: nothing listens until the page is back.
    expect(h.listener()).toBeNull();
    h.standby.pageHidden(false);
    await vi.advanceTimersByTimeAsync(0);
    expect(h.listener()?.listens).toEqual(['fr']);
    h.standby.pageHidden(true);
    await vi.advanceTimersByTimeAsync(0);
    expect(h.listener()?.pauses).toBe(1);
    h.standby.pageHidden(false);
    await vi.advanceTimersByTimeAsync(0);
    expect(h.listener()?.listens).toEqual(['fr', 'fr']);
  });

  it('a page change while awake touches no wake word', async () => {
    const h = build();
    live();
    h.standby.pageHidden(true);
    h.standby.pageHidden(false);
    expect(h.listener()).toBeNull();
  });

  it.each([
    ['a browser without the runtime', { listener: false }],
    ['a language with no phrase', { language: null }],
  ] as const)('degrades to the button on %s', async (_label, options) => {
    const h = build(undefined, options);
    await asleep(h);
    expect(useLiveStore.getState().wakeWordState).toBe('unavailable');
    expect(useLiveStore.getState().wakePhrase).toBeNull();
    await h.standby.wake(SESSION, 'manual');
    expect(useLiveStore.getState().status).toBe('live');
  });

  it('degrades to the button when the microphone is refused to the wake word', async () => {
    const h = build(undefined, { refuse: true });
    await asleep(h);
    expect(h.listener()?.listens).toEqual(['fr']);
    expect(useLiveStore.getState().wakeWordState).toBe('unavailable');
    expect(useLiveStore.getState().status).toBe('standby');
  });

  it('disposes the wake word and the bound at the end', async () => {
    const h = build();
    await asleep(h);
    h.standby.dispose();
    expect(h.listener()?.disposed).toBe(true);
    await vi.advanceTimersByTimeAsync(DEADLINE_MS + 1);
    expect(h.wire.end).not.toHaveBeenCalled();
  });
});
