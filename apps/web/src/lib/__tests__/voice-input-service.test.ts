/**
 * VoiceInputService — the WebSocket audio channel behind push-to-talk.
 *
 * Authentication follows the BFF pattern: a short-lived ticket is fetched over
 * the authenticated REST endpoint, then passed in the socket URL — the session
 * cookie never reaches the WebSocket. What is pinned here:
 *
 *  - the ticket is acquired **once per connection** and URL-encoded into the
 *    socket URL, and the scheme follows the page (`https` → `wss`);
 *  - an **unexpected** close reconnects with the configured backoff, while a
 *    clean or user-initiated close does not — a service that reconnects after
 *    the user hung up would reopen the microphone channel behind their back;
 *  - `disconnect()` cancels a pending reconnect, and `dispose()` makes the
 *    instance permanently inert;
 *  - a malformed frame is logged, never thrown: the socket must survive one bad
 *    message.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const { post } = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock('@/lib/api-client', async importOriginal => {
  const actual = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...actual, apiClient: { post } };
});
vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

import { VoiceInputService, type VoiceInputServiceConfig } from '../voice-input-service';
import {
  VOICE_INPUT_HEARTBEAT_INTERVAL_MS,
  VOICE_INPUT_WS_RECONNECT_DELAYS,
} from '@/lib/constants';

/** A controllable WebSocket: the test decides when it opens, fails or closes. */
class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  static readonly OPEN = 1;
  static readonly CLOSED = 3;

  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: ((event: { code: number; reason: string; wasClean: boolean }) => void) | null = null;
  onerror: (() => void) | null = null;
  readyState = 0;
  sent: unknown[] = [];
  closedWith: { code?: number; reason?: string } | null = null;

  constructor(readonly url: string) {
    FakeWebSocket.instances.push(this);
  }

  send(data: unknown) {
    this.sent.push(data);
  }

  close(code?: number, reason?: string) {
    this.closedWith = { code, reason };
    this.readyState = FakeWebSocket.CLOSED;
  }

  /** Completes the handshake. */
  open() {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.();
  }

  emit(payload: unknown) {
    this.onmessage?.({ data: typeof payload === 'string' ? payload : JSON.stringify(payload) });
  }

  fail() {
    this.onerror?.();
  }

  /** Server-side close. `wasClean` false + code ≠ 1000 is what triggers a retry. */
  serverClose(code = 1006, wasClean = false) {
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.({ code, reason: '', wasClean });
  }
}

const socket = (index = -1) =>
  index < 0
    ? FakeWebSocket.instances[FakeWebSocket.instances.length - 1]
    : FakeWebSocket.instances[index];

const onTranscription = vi.fn();
const onConnectionChange = vi.fn();
const onError = vi.fn();

function service(over: Partial<VoiceInputServiceConfig> = {}) {
  return new VoiceInputService({ onTranscription, onConnectionChange, onError, ...over });
}

/** Connects a service and completes the handshake. */
async function connected(over: Partial<VoiceInputServiceConfig> = {}) {
  const svc = service(over);
  const connecting = svc.connect();
  await vi.waitFor(() => expect(FakeWebSocket.instances.length).toBeGreaterThan(0));
  socket().open();
  await connecting;
  return svc;
}

beforeEach(() => {
  vi.clearAllMocks();
  FakeWebSocket.instances = [];
  post.mockResolvedValue({ ticket: 'tkt-123', expires_in: 60 });
  vi.stubGlobal('WebSocket', FakeWebSocket);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('VoiceInputService — connecting', () => {
  it('acquires a ticket and carries it in the socket URL', async () => {
    await connected();

    expect(post).toHaveBeenCalledWith('/voice/ticket');
    expect(socket().url).toContain('/api/v1/voice/ws/audio?ticket=tkt-123');
  });

  it('url-encodes a ticket that needs it', async () => {
    post.mockResolvedValue({ ticket: 'a b/c+d', expires_in: 60 });
    await connected();

    expect(socket().url).toContain('ticket=a%20b%2Fc%2Bd');
    expect(socket().url).not.toContain('a b/c');
  });

  it('derives a secure socket scheme from a secure page', async () => {
    await connected();

    // jsdom serves the tests over http; the branch must still produce ws://…
    // and never mix schemes.
    expect(socket().url).toMatch(/^wss?:\/\//);
  });

  it('announces the connection and reports it as connected', async () => {
    const svc = await connected();

    expect(onConnectionChange).toHaveBeenCalledWith(true);
    expect(svc.isConnected).toBe(true);
  });

  it('does not ask for a second ticket while already connected', async () => {
    const svc = await connected();
    post.mockClear();

    await svc.connect();

    expect(post).not.toHaveBeenCalled();
    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it('reports a refused ticket and opens no socket', async () => {
    post.mockRejectedValue(new Error('403 voice disabled'));
    const svc = service();

    await expect(svc.connect()).rejects.toThrow(/Failed to acquire WebSocket ticket/);
    expect(onError).toHaveBeenCalledWith(expect.any(Error));
    expect(FakeWebSocket.instances).toHaveLength(0);
  });

  it('reports a socket that fails to open', async () => {
    const svc = service();
    const connecting = svc.connect();
    await vi.waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));

    socket().fail();

    await expect(connecting).rejects.toThrow('WebSocket connection error');
    expect(onError).toHaveBeenCalledWith(
      expect.objectContaining({ message: expect.stringContaining('WebSocket') })
    );
  });

  it('refuses to work once disposed', async () => {
    const svc = await connected();
    svc.dispose();

    await expect(svc.connect()).rejects.toThrow(/disposed/);
  });
});

describe('VoiceInputService — incoming frames', () => {
  it('hands a transcription over with its cost metadata', async () => {
    await connected();

    socket().emit({
      type: 'transcription',
      text: 'bonjour LIA',
      duration_seconds: 2.5,
      stt_provider: 'elevenlabs',
      stt_cost_usd: 0.002,
      stt_cost_eur: 0.0018,
    });

    expect(onTranscription).toHaveBeenCalledWith('bonjour LIA', 2.5, {
      stt_provider: 'elevenlabs',
      stt_audio_duration_seconds: 2.5,
      stt_cost_usd: 0.002,
      stt_cost_eur: 0.0018,
    });
  });

  it('normalises a local transcription to explicit nulls', async () => {
    await connected();

    // Sherpa (local) sends no provider and no cost: the consumer must receive
    // nulls, not undefined, so "free" is distinguishable from "unknown".
    socket().emit({ type: 'transcription', text: 'salut', duration_seconds: 1 });

    expect(onTranscription).toHaveBeenCalledWith('salut', 1, {
      stt_provider: null,
      stt_audio_duration_seconds: 1,
      stt_cost_usd: null,
      stt_cost_eur: null,
    });
  });

  it('ignores a heartbeat answer', async () => {
    await connected();

    socket().emit({ type: 'pong' });

    expect(onTranscription).not.toHaveBeenCalled();
  });

  it('survives a frame it cannot parse', async () => {
    await connected();

    expect(() => socket().emit('{not json')).not.toThrow();
    expect(onTranscription).not.toHaveBeenCalled();
  });
});

describe('VoiceInputService — heartbeat', () => {
  beforeEach(() => vi.useFakeTimers());

  it('pings on the configured cadence while connected', async () => {
    await connected();

    vi.advanceTimersByTime(VOICE_INPUT_HEARTBEAT_INTERVAL_MS);
    expect(socket().sent).toContain('PING');

    vi.advanceTimersByTime(VOICE_INPUT_HEARTBEAT_INTERVAL_MS);
    expect(socket().sent.filter(s => s === 'PING')).toHaveLength(2);
  });

  it('stops pinging once disconnected', async () => {
    const svc = await connected();

    svc.disconnect();
    vi.advanceTimersByTime(VOICE_INPUT_HEARTBEAT_INTERVAL_MS * 3);

    expect(socket().sent).not.toContain('PING');
  });
});

describe('VoiceInputService — reconnection', () => {
  beforeEach(() => vi.useFakeTimers());

  it('retries after an unexpected close, on the configured delay', async () => {
    await connected();

    socket().serverClose(1006, false);
    expect(onConnectionChange).toHaveBeenLastCalledWith(false);
    expect(FakeWebSocket.instances).toHaveLength(1);

    await vi.advanceTimersByTimeAsync(VOICE_INPUT_WS_RECONNECT_DELAYS[0]);

    expect(FakeWebSocket.instances).toHaveLength(2);
  });

  it.each([
    ['a clean close', 1006, true],
    ['a normal close', 1000, false],
  ])('does not retry after %s', async (_label, code, wasClean) => {
    await connected();

    socket().serverClose(code, wasClean);
    await vi.advanceTimersByTimeAsync(VOICE_INPUT_WS_RECONNECT_DELAYS[0] * 4);

    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it('gives up after the configured number of attempts', async () => {
    await connected();

    // Each retry must ALSO fail (never reach `onopen`), otherwise the budget is
    // reset — see the test below.
    socket().serverClose(1006, false);
    for (const delay of VOICE_INPUT_WS_RECONNECT_DELAYS) {
      await vi.advanceTimersByTimeAsync(delay);
      socket().serverClose(1006, false);
    }

    const expected = 1 + VOICE_INPUT_WS_RECONNECT_DELAYS.length;
    expect(FakeWebSocket.instances).toHaveLength(expected);

    // Budget exhausted: waiting longer opens nothing more.
    await vi.advanceTimersByTimeAsync(60_000);
    expect(FakeWebSocket.instances).toHaveLength(expected);
  });

  it('starts the budget over once a retry actually succeeds', async () => {
    await connected();

    // Burn every attempt but the last, then let one land.
    socket().serverClose(1006, false);
    for (const delay of VOICE_INPUT_WS_RECONNECT_DELAYS.slice(0, -1)) {
      await vi.advanceTimersByTimeAsync(delay);
      socket().serverClose(1006, false);
    }
    await vi.advanceTimersByTimeAsync(VOICE_INPUT_WS_RECONNECT_DELAYS.at(-1)!);
    socket().open();
    const afterRecovery = FakeWebSocket.instances.length;

    // A later drop is treated as a first failure again: short delay, not
    // exhaustion. A service that kept counting would give up on a connection
    // that has been healthy for hours.
    socket().serverClose(1006, false);
    await vi.advanceTimersByTimeAsync(VOICE_INPUT_WS_RECONNECT_DELAYS[0]);

    expect(FakeWebSocket.instances).toHaveLength(afterRecovery + 1);
  });

  it('cancels a pending retry when the user hangs up', async () => {
    const svc = await connected();

    socket().serverClose(1006, false);
    svc.disconnect();
    await vi.advanceTimersByTimeAsync(60_000);

    // Reopening the microphone channel after the user hung up would be the bug.
    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it('never retries once disposed', async () => {
    const svc = await connected();

    svc.dispose();
    socket().serverClose(1006, false);
    await vi.advanceTimersByTimeAsync(60_000);

    expect(FakeWebSocket.instances).toHaveLength(1);
  });
});

describe('VoiceInputService — sending', () => {
  it('streams audio and signals the end', async () => {
    const svc = await connected();
    const chunk = new ArrayBuffer(8);

    svc.sendAudio(chunk);
    svc.endAudio();

    expect(socket().sent[0]).toBe(chunk);
    expect(socket().sent[1]).toBe('END');
  });

  it.each([
    ['audio', (svc: VoiceInputService) => svc.sendAudio(new ArrayBuffer(4))],
    ['the end marker', (svc: VoiceInputService) => svc.endAudio()],
  ])('drops %s when the socket is not open', async (_label, send) => {
    const svc = await connected();
    svc.disconnect();

    expect(() => send(svc)).not.toThrow();
    expect(socket().sent).toHaveLength(0);
  });
});

describe('VoiceInputService — teardown', () => {
  it('closes the socket with a normal code', async () => {
    const svc = await connected();

    svc.disconnect();

    expect(socket().closedWith).toMatchObject({ code: 1000 });
    expect(svc.isConnected).toBe(false);
  });

  it('can be disconnected twice without complaining', async () => {
    const svc = await connected();

    svc.disconnect();
    expect(() => svc.disconnect()).not.toThrow();
  });

  it('closes the socket when disposed', async () => {
    const svc = await connected();

    svc.dispose();

    expect(socket().closedWith).toMatchObject({ code: 1000 });
  });
});

describe('VoiceInputService — callbacks', () => {
  it('routes to the callbacks swapped in after construction', async () => {
    const svc = await connected();
    const later = vi.fn();

    svc.updateCallbacks({ onTranscription: later });
    socket().emit({ type: 'transcription', text: 'après', duration_seconds: 1 });

    expect(later).toHaveBeenCalledWith('après', 1, expect.any(Object));
    expect(onTranscription).not.toHaveBeenCalled();
  });
});
