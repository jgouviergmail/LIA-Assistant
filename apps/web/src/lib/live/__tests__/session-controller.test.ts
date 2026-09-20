/**
 * LiveSessionController — the orchestration, with every I/O faked.
 *
 *  - start: config → mint → transport.connect with the setup verbatim → mic →
 *    status live, push-to-talk starts muted;
 *  - a user transcript then an assistant transcript then turnComplete → POST
 *    turns and two appended messages carrying the server's ids;
 *  - a tool call → bridge → chat sendMessage with the spoken words → toolResponse
 *    sent, the delegated turn archives nothing of its own;
 *  - interrupted → player.flush; audio → player.enqueue;
 *  - goAway → a FRESH credential is asked (measured: a used token cannot
 *    reconnect) and connect rides the last handle; a stale socket's close is
 *    ignored;
 *  - a close without a handle ends as provider_closed; too many attempts end as
 *    resumption_failed;
 *  - idle → idle_timeout; hidden past the grace → hidden; the cap → expired;
 *  - a refused mint names its code; a refused microphone ends as mic_denied;
 *  - end → transport closed, mic stopped, POST end, summary appended, and a
 *    second end is a no-op.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { LIVE_GO_AWAY_MARGIN_MS } from '@/lib/constants';
import { useLiveStore } from '@/stores/liveStore';

import {
  LiveSessionController,
  type LiveApi,
  type LiveControllerDeps,
} from '../session-controller';
import type { LiveTransport } from '../transport';
import type {
  LiveConnectOptions,
  LiveSessionStart,
  LiveTransportAudio,
  LiveTransportEvents,
} from '../types';

const SESSION = 'a'.repeat(32);
const START: LiveSessionStart = {
  session_id: SESSION,
  provider: 'gemini',
  model: 'm',
  mode: 'delegated',
  expires_at: new Date(Date.now() + 10 * 60_000).toISOString(),
  capabilities: {
    async_delegation: true,
    delivery_scheduling: true,
    reports_idle: false,
    cancels_on_interruption: true,
    configurable_vad: true,
    resumes: true,
    thinking: false,
    direct_tools: true,
    portal_voice: false,
    vendor_billed: false,
  },
  run_id: `live_session_${SESSION}`,
  credential: 'tok-1',
  credential_expires_at: new Date(Date.now() + 30 * 60_000).toISOString(),
  connect_deadline_at: new Date(Date.now() + 60_000).toISOString(),
  connection: 'token',
  session_max_minutes: 10,
  idle_timeout_seconds: 10,
  setup: { model: 'models/m' },
  preferences: {
    interruptions: true,
    end_of_speech: 'normal',
    result_delivery: 'interrupt',
  },
  delegation_tool_name: 'send_to_lia',
  delegation_timeout_seconds: 90,
  delegation_result_max_tokens: 600,
  turn_text_max_chars: 4000,
  rates: {
    pricing_unit: 'per_1m_tokens',
    input_unit_price: 0.75,
    output_unit_price: 4.5,
    audio_input_unit_price: 3,
    audio_output_unit_price: 12,
    usd_eur_rate: 0.9,
  },
  session_budget_eur: null,
};
const CONFIG = {
  session_max_minutes: 10,
  extension_minutes: 10,
  extension_prompt_seconds: 60,
  connect_window_seconds: 60,
  idle_timeout_seconds: 10,
  hidden_grace_seconds: 20,
  delegation_timeout_seconds: 90,
  delegation_result_max_tokens: 600,
  delegation_tool_name: 'send_to_lia',
  turn_text_max_chars: 4000,
  delegation_lines: { timed_out: 'T', result_cut: 'C', superseded: 'X', empty_request: 'E' },
  direct_lines: { lookup_failed: 'F' },
  tone_lines: { warm: 'W' },
};

const PCM_AUDIO: LiveTransportAudio = {
  ownership: 'pcm',
  inputRate: 16000,
  outputRate: 24000,
  chunkMs: 40,
};

class FakeTransport implements LiveTransport {
  isOpen = false;
  audio: LiveTransportAudio = PCM_AUDIO;
  events: LiveTransportEvents = {};
  connects: Array<{
    credential: string;
    setup: Record<string, unknown>;
    handle?: string | null;
    microphone?: MediaStream | null;
  }> = [];
  /** The exchange door of the last connect (an offer connection), if any. */
  exchange: LiveConnectOptions['exchangeOffer'];
  sent: Array<{ kind: string; args: unknown[] }> = [];
  closes = 0;
  ack = true;
  async connect(options: LiveConnectOptions, events: LiveTransportEvents): Promise<void> {
    this.connects.push({
      credential: options.credential,
      setup: options.setup,
      handle: options.resumptionHandle,
      microphone: options.microphone,
    });
    this.exchange = options.exchangeOffer;
    this.events = events;
    if (!this.ack) throw new Error('live_socket_closed_1006');
    this.isOpen = true;
    events.onReady?.();
  }
  sendAudio(pcm16: ArrayBuffer) {
    this.sent.push({ kind: 'audio', args: [pcm16] });
  }
  sendText(text: string) {
    this.sent.push({ kind: 'text', args: [text] });
  }
  answerDelegation(id: string, result: string, delivery: string, note?: string | null) {
    this.sent.push({ kind: 'answer', args: [id, result, delivery, note ?? null] });
  }
  setInputActive(on: boolean) {
    this.sent.push({ kind: 'input', args: [on] });
  }
  async close() {
    this.closes += 1;
    this.isOpen = false;
  }
}

/**
 * A typed API client over two plain fakes: the generic signature of `LiveApi`
 * is honoured by a passthrough, so the test asserts on `post`'s calls and
 * decides its answers per URL.
 */
function fakeApi(
  post: (url: string, body?: unknown) => Promise<unknown>,
  get: (url: string) => Promise<unknown> = async () => CONFIG
): LiveApi {
  return {
    async get<T>(url: string): Promise<T> {
      return (await get(url)) as T;
    },
    async post<T>(url: string, body?: unknown): Promise<T> {
      return (await post(url, body)) as T;
    },
  };
}

function build(overrides: Partial<LiveControllerDeps> = {}) {
  const transport = new FakeTransport();
  const player = {
    warmup: vi.fn(async () => {}),
    enqueue: vi.fn(),
    flush: vi.fn(),
    dispose: vi.fn(),
    onSpeakingChange: vi.fn(),
    isSpeaking: false,
  };
  const stream = { id: 'mic-stream' } as unknown as MediaStream;
  const mic = { stream, mute: vi.fn(), stop: vi.fn(async () => {}) };
  let micChunk: ((pcm: ArrayBuffer) => void) | null = null;
  const post = vi.fn(async (url: string, _body?: unknown): Promise<unknown> => {
    if (url === '/live/sessions') return START;
    if (url.endsWith('/credential')) return { ...START, credential: 'tok-2', setup: START.setup };
    if (url.endsWith('/turns')) return { user_message_id: 'u1', assistant_message_id: 'a1' };
    if (url.endsWith('/end'))
      return {
        summary_message_id: 's1',
        duration_seconds: 10,
        delegations: 1,
        voice_turns: 1,
        extensions: 2,
        usage: {
          tokens_in: 1,
          tokens_out: 2,
          tokens_cache: 0,
          cost_eur: 0.01,
          google_api_requests: 0,
        },
      };
    return {};
  });
  const chat = {
    sendMessage: vi.fn(async () => {}),
    stop: vi.fn(async () => {}),
    appendMessage: vi.fn(),
    readAnswer: async () => ({ text: 'answer', pendingQuestion: null }),
  };
  const deps: LiveControllerDeps = {
    api: fakeApi(post),
    createTransport: () => transport,
    createPlayer: () => player,
    startMic: vi.fn(async options => {
      micChunk = options.onChunk;
      return mic;
    }),
    isSupported: () => true,
    chat,
    ...overrides,
  };
  const controller = new LiveSessionController(deps);
  return { controller, transport, player, mic, post, chat, deps, stream, chunk: () => micChunk };
}

describe('LiveSessionController', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    useLiveStore.getState().reset();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('hands an offer connection the exchange door and the microphone stream, a token one neither', async () => {
    // GPT-Live (wave 2 A9): the transport carries the audio itself and the
    // API exchanges its SDP on the person's key, once per credential.
    const offered = { ...START, provider: 'openai', connection: 'offer' as const, setup: {} };
    const h = build({
      api: fakeApi(async (url: string, body?: unknown) => {
        if (url === '/live/sessions') return offered;
        if (url.endsWith('/offer')) {
          expect(body).toEqual({ credential: 'tok-1', sdp: 'v=0 offer' });
          return { sdp: 'v=0 answer' };
        }
        return {};
      }),
    });
    h.transport.audio = { ownership: 'native', inputRate: 48000, outputRate: 48000, chunkMs: 20 };
    await h.controller.start();
    expect(h.transport.connects[0].microphone).toBe(h.stream);
    expect(h.deps.startMic).toHaveBeenCalledWith(expect.objectContaining({ pcm: false }));
    expect(h.transport.exchange).toBeDefined();
    await expect(h.transport.exchange?.('tok-1', 'v=0 offer')).resolves.toBe('v=0 answer');
    await h.controller.end();

    const token = build();
    await token.controller.start();
    expect(token.transport.exchange).toBeUndefined();
    await token.controller.end();
  });

  it('starts, archives a voice turn, delegates, reconnects on goAway and ends', async () => {
    const h = build();
    await h.controller.start();
    expect(h.transport.connects[0]).toEqual({
      credential: 'tok-1',
      setup: { model: 'models/m' },
      handle: null,
      microphone: null,
    });
    expect(useLiveStore.getState().status).toBe('live');
    expect(useLiveStore.getState().sessionId).toBe(SESSION);
    // The microphone is sized from the transport's declared audio: 40 ms at 16 kHz.
    expect(h.deps.startMic).toHaveBeenCalledWith(
      expect.objectContaining({ sampleRate: 16000, chunkSamples: 640, pcm: true })
    );
    h.chunk()?.(new Int16Array(4).buffer);
    expect(h.transport.sent[0].kind).toBe('audio');

    // A voice-only exchange.
    h.transport.events.onTranscript?.('user', 'hello');
    expect(useLiveStore.getState().voiceState).toBe('recording');
    h.transport.events.onAudio?.(new Int16Array(2).buffer);
    expect(h.player.enqueue).toHaveBeenCalledWith(expect.any(ArrayBuffer), 24000);
    h.transport.events.onTranscript?.('assistant', 'hi ');
    h.transport.events.onTranscript?.('assistant', 'there');
    h.transport.events.onTurnComplete?.();
    await vi.advanceTimersByTimeAsync(10);
    expect(h.post).toHaveBeenCalledWith(
      `/live/sessions/${SESSION}/turns`,
      expect.objectContaining({ user_text: 'hello', assistant_text: 'hi there' })
    );
    expect(h.chat.appendMessage).toHaveBeenCalledTimes(2);
    expect(h.chat.appendMessage.mock.calls[0][0]).toMatchObject({
      id: 'u1',
      role: 'user',
      content: 'hello',
      metadata: { type: 'live_turn', live_session_id: SESSION },
    });
    expect(useLiveStore.getState().captions.map(c => c.text)).toEqual(['hello', 'hi there']);

    // A delegated turn.
    h.transport.events.onTranscript?.('user', 'what is on my agenda');
    await h.transport.events.onDelegation?.([{ id: 'c1', request: 'agenda?' }]);
    expect(h.chat.sendMessage).toHaveBeenCalledWith('agenda?', {
      live_session_id: SESSION,
      spoken_text: 'what is on my agenda',
    });
    expect(h.transport.sent.at(-1)).toEqual({
      kind: 'answer',
      args: ['c1', 'answer', 'now', null],
    });
    expect(useLiveStore.getState().delegating).toBe(false);
    h.transport.events.onTurnComplete?.();
    await vi.advanceTimersByTimeAsync(10);
    expect(h.post.mock.calls.filter(([url]) => String(url).endsWith('/turns'))).toHaveLength(1);

    h.transport.events.onInterrupted?.();
    expect(h.player.flush).toHaveBeenCalledTimes(1);

    // goAway: a fresh credential, the last handle, the old socket's close ignored.
    h.transport.events.onResumption?.('h1', true);
    const staleEvents = h.transport.events;
    h.transport.events.onGoAway?.(LIVE_GO_AWAY_MARGIN_MS + 500);
    expect(useLiveStore.getState().timeLeftMs).toBe(LIVE_GO_AWAY_MARGIN_MS + 500);
    await vi.advanceTimersByTimeAsync(600);
    expect(h.post).toHaveBeenCalledWith(`/live/sessions/${SESSION}/credential`, {});
    expect(h.transport.connects[1]).toEqual({
      credential: 'tok-2',
      setup: { model: 'models/m' },
      handle: 'h1',
      microphone: null,
    });
    expect(useLiveStore.getState().status).toBe('live');
    staleEvents.onClosed?.(1000, '');
    expect(useLiveStore.getState().status).toBe('live');

    await h.controller.end('ended');
    expect(h.transport.closes).toBeGreaterThanOrEqual(2);
    expect(h.mic.stop).toHaveBeenCalledTimes(1);
    expect(h.player.dispose).toHaveBeenCalledTimes(1);
    expect(h.post).toHaveBeenCalledWith(`/live/sessions/${SESSION}/end`, {
      outcome: 'ended',
      detail: null,
      provider_conversation_id: null,
    });
    const summary = h.chat.appendMessage.mock.calls.at(-1)?.[0];
    // The row drawn at once carries what the archived one does — the mode
    // and the extensions included — so the card reads the same before a reload.
    expect(summary).toMatchObject({
      id: 's1',
      role: 'assistant',
      metadata: {
        type: 'live_session_summary',
        live_session_id: SESSION,
        live_summary: {
          outcome: 'ended',
          delegations: 1,
          voice_turns: 1,
          extensions: 2,
          mode: 'delegated',
        },
      },
      costEur: 0.01,
    });
    expect(useLiveStore.getState()).toMatchObject({ status: 'ended', outcome: 'ended' });
    await h.controller.end('ended');
    expect(h.post.mock.calls.filter(([url]) => String(url).endsWith('/end'))).toHaveLength(1);
  });

  it('starts with the microphone open and toggleMute tells the transport', async () => {
    const h = build();
    await h.controller.start();
    expect(h.mic.mute).not.toHaveBeenCalled();
    expect(useLiveStore.getState().muted).toBe(false);
    h.controller.toggleMute();
    expect(h.mic.mute).toHaveBeenLastCalledWith(true);
    expect(useLiveStore.getState().muted).toBe(true);
    h.controller.toggleMute();
    expect(h.mic.mute).toHaveBeenLastCalledWith(false);
    // The transport is told, so a paused microphone flushes the provider's cache.
    const inputs = h.transport.sent.filter(s => s.kind === 'input').map(s => s.args[0]);
    expect(inputs).toEqual([false, true]);
  });

  it('archives on the provider idle signal, not per utterance, when the model reports it', async () => {
    // Extended Thinking: turnComplete comes once per spoken utterance while
    // the task goes on; only interactionStatus IDLE ends the exchange.
    const post = vi.fn(async (url: string): Promise<unknown> => {
      if (url === '/live/sessions') {
        return { ...START, capabilities: { ...START.capabilities, reports_idle: true } };
      }
      if (url.endsWith('/turns')) return { user_message_id: 'u1', assistant_message_id: 'a1' };
      return {};
    });
    const h = build({ api: fakeApi(post) });
    await h.controller.start();
    h.transport.events.onTranscript?.('user', 'hello');
    h.transport.events.onInteractionStatus?.('in_progress');
    expect(useLiveStore.getState().voiceState).toBe('processing');
    h.transport.events.onTranscript?.('assistant', 'one moment ');
    h.transport.events.onTurnComplete?.();
    await vi.advanceTimersByTimeAsync(10);
    expect(post.mock.calls.filter(([url]) => String(url).endsWith('/turns'))).toHaveLength(0);
    h.transport.events.onTranscript?.('assistant', 'done');
    h.transport.events.onInteractionStatus?.('idle');
    await vi.advanceTimersByTimeAsync(10);
    expect(post).toHaveBeenCalledWith(
      `/live/sessions/${SESSION}/turns`,
      expect.objectContaining({ user_text: 'hello', assistant_text: 'one moment done' })
    );
    expect(useLiveStore.getState().voiceState).toBe('idle');
  });

  it('hands the microphone stream to a transport that owns the audio natively', async () => {
    // GPT-Live over WebRTC: the transport carries the tracks; the controller
    // still opens the microphone ONCE (ADR-258) and plays nothing itself.
    const h = build();
    h.transport.audio = { ownership: 'native', inputRate: 24000, outputRate: 24000, chunkMs: 20 };
    await h.controller.start();
    expect(h.deps.startMic).toHaveBeenCalledWith(
      expect.objectContaining({ sampleRate: 24000, pcm: false })
    );
    expect(h.transport.connects[0].microphone).toBe(h.stream);
    h.transport.events.onSpeakingChange?.(true);
    expect(useLiveStore.getState().voiceState).toBe('speaking');
    h.transport.events.onSpeakingChange?.(false);
    expect(useLiveStore.getState().voiceState).toBe('idle');
    expect(h.player.enqueue).not.toHaveBeenCalled();
  });

  it('ends as provider_closed without a handle and as resumption_failed after the attempts', async () => {
    const h = build();
    await h.controller.start();
    h.transport.events.onClosed?.(1006, 'gone');
    await vi.advanceTimersByTimeAsync(10);
    expect(useLiveStore.getState().outcome).toBe('provider_closed');
    // The provider's own word travels to the API's log with the outcome: an
    // outcome alone left a session that died in five seconds unexplained.
    expect(h.post).toHaveBeenCalledWith(`/live/sessions/${SESSION}/end`, {
      outcome: 'provider_closed',
      detail: 'close 1006: gone',
      provider_conversation_id: null,
    });

    useLiveStore.getState().reset();
    const g = build();
    await g.controller.start();
    g.transport.events.onResumption?.('h1', true);
    g.transport.ack = false;
    g.transport.events.onClosed?.(1006, 'gone');
    await vi.advanceTimersByTimeAsync(10);
    expect(useLiveStore.getState().outcome).toBe('resumption_failed');
    expect(g.transport.connects.length).toBeGreaterThan(1);
  });

  it('ends on idle, on a hidden page past the grace, and at the cap', async () => {
    const h = build();
    await h.controller.start();
    await vi.advanceTimersByTimeAsync(CONFIG.idle_timeout_seconds * 1000 + 1);
    expect(useLiveStore.getState().outcome).toBe('idle_timeout');

    useLiveStore.getState().reset();
    // A long idle bound here: the hidden grace, not the silence, is under test.
    const g = build({
      api: fakeApi(async url =>
        url === '/live/sessions' ? { ...START, idle_timeout_seconds: 300 } : {}
      ),
    });
    await g.controller.start();
    g.controller.pageHidden(true);
    await vi.advanceTimersByTimeAsync(CONFIG.hidden_grace_seconds * 1000 - 1);
    g.controller.pageHidden(false);
    await vi.advanceTimersByTimeAsync(5_000);
    expect(useLiveStore.getState().status).toBe('live');
    g.controller.pageHidden(true);
    await vi.advanceTimersByTimeAsync(CONFIG.hidden_grace_seconds * 1000 + 1);
    expect(useLiveStore.getState().outcome).toBe('hidden');

    useLiveStore.getState().reset();
    const soon = new Date(Date.now() + 2_000).toISOString();
    const k = build({
      api: fakeApi(async url => (url === '/live/sessions' ? { ...START, expires_at: soon } : {})),
    });
    await k.controller.start();
    await vi.advanceTimersByTimeAsync(2_100);
    expect(useLiveStore.getState().outcome).toBe('expired');
  });

  it("the silence clock is the MODEL's, not the instance's, and 0 never ends a session on silence", async () => {
    // Owner decision 2026-09-19: each model of a connector keeps its own
    // silence timeout; the start hands it over and the config's is not read.
    const h = build({
      api: fakeApi(async url =>
        url === '/live/sessions' ? { ...START, idle_timeout_seconds: 30 } : {}
      ),
    });
    await h.controller.start();
    await vi.advanceTimersByTimeAsync(CONFIG.idle_timeout_seconds * 1000 + 1);
    expect(useLiveStore.getState().status).toBe('live');
    await vi.advanceTimersByTimeAsync(20_000);
    expect(useLiveStore.getState().outcome).toBe('idle_timeout');

    useLiveStore.getState().reset();
    const g = build({
      api: fakeApi(async url =>
        url === '/live/sessions' ? { ...START, idle_timeout_seconds: 0 } : {}
      ),
    });
    await g.controller.start();
    // Well past any silence bound, short of the cap: nothing ends it.
    await vi.advanceTimersByTimeAsync(8 * 60_000);
    expect(useLiveStore.getState().status).toBe('live');
    expect(useLiveStore.getState().idleCountdownSeconds).toBeNull();
  });

  it('counts silence only while nobody speaks, works or processes', async () => {
    const h = build();
    await h.controller.start();
    const idleMs = CONFIG.idle_timeout_seconds * 1000;
    // LIA speaking holds the clock.
    h.player.isSpeaking = true;
    h.player.onSpeakingChange.mock.calls[0][0](true);
    await vi.advanceTimersByTimeAsync(idleMs * 3);
    expect(useLiveStore.getState().status).toBe('live');
    h.player.isSpeaking = false;
    h.player.onSpeakingChange.mock.calls[0][0](false);
    // A delegation holds it.
    let finish: () => void = () => {};
    h.chat.sendMessage.mockImplementationOnce(
      () =>
        new Promise<void>(resolve => {
          finish = resolve;
        })
    );
    const pending = h.transport.events.onDelegation?.([{ id: 'c1', request: 'x' }]);
    await vi.advanceTimersByTimeAsync(idleMs * 3);
    expect(useLiveStore.getState().status).toBe('live');
    finish();
    await pending;
    // The provider processing holds it.
    h.transport.events.onInteractionStatus?.('in_progress');
    await vi.advanceTimersByTimeAsync(idleMs * 3);
    expect(useLiveStore.getState().status).toBe('live');
    h.transport.events.onInteractionStatus?.('idle');
    // Nobody: the last stretch is announced, then the session ends.
    await vi.advanceTimersByTimeAsync(idleMs - 3_000);
    expect(useLiveStore.getState().idleCountdownSeconds).toBe(3);
    h.transport.events.onTranscript?.('user', 'still here');
    expect(useLiveStore.getState().idleCountdownSeconds).toBeNull();
    await vi.advanceTimersByTimeAsync(idleMs + 10);
    expect(useLiveStore.getState().outcome).toBe('idle_timeout');
  });

  it('offers the extension before the cap, extends on the word and reconnects on the new credential', async () => {
    const expiresAt = Date.now() + 90_000;
    const post = vi.fn(async (url: string): Promise<unknown> => {
      if (url === '/live/sessions')
        return { ...START, expires_at: new Date(expiresAt).toISOString() };
      if (url.endsWith('/extend')) {
        return {
          expires_at: new Date(expiresAt + 10 * 60_000).toISOString(),
          extensions: 1,
          credential: { ...START, credential: 'tok-3' },
        };
      }
      if (url.endsWith('/end'))
        return {
          summary_message_id: 's1',
          duration_seconds: 1,
          delegations: 0,
          voice_turns: 0,
          extensions: 1,
          usage: null,
        };
      return {};
    });
    const h = build({ api: fakeApi(post) });
    await h.controller.start();
    h.transport.events.onResumption?.('h1', true);
    // Keep the silence clock quiet: the person is talking now and then.
    const talk = setInterval(() => h.transport.events.onTranscript?.('user', 'hm'), 4_000);
    await vi.advanceTimersByTimeAsync(30_000 - 10);
    expect(useLiveStore.getState().extensionOffered).toBe(false);
    await vi.advanceTimersByTimeAsync(20);
    expect(useLiveStore.getState().extensionOffered).toBe(true);
    expect(await h.controller.extend()).toBe(true);
    expect(post).toHaveBeenCalledWith(`/live/sessions/${SESSION}/extend`, {});
    expect(useLiveStore.getState().extensionOffered).toBe(false);
    expect(useLiveStore.getState().extensions).toBe(1);
    expect(useLiveStore.getState().expiresAt).toBe(expiresAt + 10 * 60_000);
    // The fresh credential was ridden at once, on the handle.
    expect(h.transport.connects.at(-1)).toMatchObject({ credential: 'tok-3', handle: 'h1' });
    expect(useLiveStore.getState().status).toBe('live');
    // The session runs past the old cap.
    await vi.advanceTimersByTimeAsync(120_000);
    expect(useLiveStore.getState().status).toBe('live');
    clearInterval(talk);
  });

  it('an unlimited cap rolls on by extension slices in silence, no dialog ever offered', async () => {
    // 0 = no limit (owner decision 2026-09-19): the credential still carries a
    // cap (a provider token cannot outlive its expiry), so the client renews it
    // at the prompt instant without asking anybody.
    const expiresAt = Date.now() + 90_000;
    const post = vi.fn(async (url: string): Promise<unknown> => {
      if (url === '/live/sessions')
        return {
          ...START,
          session_max_minutes: 0,
          expires_at: new Date(expiresAt).toISOString(),
        };
      if (url.endsWith('/extend')) {
        return {
          expires_at: new Date(expiresAt + 10 * 60_000).toISOString(),
          extensions: 1,
          credential: { ...START, credential: 'tok-3' },
        };
      }
      return {};
    });
    const h = build({ api: fakeApi(post) });
    await h.controller.start();
    h.transport.events.onResumption?.('h1', true);
    const talk = setInterval(() => h.transport.events.onTranscript?.('user', 'hm'), 4_000);
    await vi.advanceTimersByTimeAsync(30_000 + 10);
    expect(useLiveStore.getState().extensionOffered).toBe(false);
    expect(post).toHaveBeenCalledWith(`/live/sessions/${SESSION}/extend`, {});
    expect(useLiveStore.getState().extensions).toBe(1);
    expect(useLiveStore.getState().expiresAt).toBe(expiresAt + 10 * 60_000);
    expect(h.transport.connects.at(-1)).toMatchObject({ credential: 'tok-3', handle: 'h1' });
    await vi.advanceTimersByTimeAsync(120_000);
    expect(useLiveStore.getState().status).toBe('live');
    clearInterval(talk);
  });

  it('ends at the cap when the offer is declined, and a refused extension returns false', async () => {
    const expiresAt = Date.now() + 70_000;
    const refused = Object.assign(new Error('expired'), {
      status: 409,
      data: { detail: { code: 'session_expired', message: 'expired' } },
    });
    const post = vi.fn(async (url: string): Promise<unknown> => {
      if (url === '/live/sessions')
        return { ...START, expires_at: new Date(expiresAt).toISOString() };
      if (url.endsWith('/extend')) throw refused;
      return {};
    });
    const h = build({ api: fakeApi(post) });
    await h.controller.start();
    const talk = setInterval(() => h.transport.events.onTranscript?.('user', 'hm'), 4_000);
    await vi.advanceTimersByTimeAsync(10_050);
    expect(useLiveStore.getState().extensionOffered).toBe(true);
    h.controller.declineExtension();
    expect(useLiveStore.getState().extensionOffered).toBe(false);
    expect(await h.controller.extend()).toBe(false);
    expect(useLiveStore.getState().status).toBe('live');
    await vi.advanceTimersByTimeAsync(60_000);
    expect(useLiveStore.getState().outcome).toBe('expired');
    clearInterval(talk);
  });

  it('names a refused mint by its code and a refused microphone as mic_denied', async () => {
    const refused = Object.assign(new Error('Activate a Live connector first.'), {
      status: 409,
      data: { detail: { code: 'connector_missing', message: 'Activate a Live connector first.' } },
    });
    const h = build({ api: fakeApi(async () => Promise.reject(refused)) });
    await h.controller.start();
    expect(useLiveStore.getState()).toMatchObject({
      status: 'ended',
      outcome: 'error',
      error: 'connector_missing',
    });
    expect(h.transport.connects).toHaveLength(0);
    expect(h.player.dispose).toHaveBeenCalledTimes(1);

    useLiveStore.getState().reset();
    const denied = Object.assign(new Error('denied'), { name: 'NotAllowedError' });
    const g = build({ startMic: vi.fn(async () => Promise.reject(denied)) });
    await g.controller.start();
    expect(useLiveStore.getState().outcome).toBe('mic_denied');
    expect(g.post).toHaveBeenCalledWith(
      `/live/sessions/${SESSION}/end`,
      expect.objectContaining({ outcome: 'mic_denied' })
    );
    // The microphone is opened BEFORE the connection (a native transport
    // needs the track in its offer): a refusal never opens a socket.
    expect(g.transport.connects).toHaveLength(0);
  });

  it('a delegation arriving while one runs replaces it: the chat is stopped, the old call closed silently', async () => {
    let finishFirst: () => void = () => {};
    const sendMessage = vi
      .fn()
      .mockImplementationOnce(
        () =>
          new Promise<void>(resolve => {
            finishFirst = resolve;
          })
      )
      .mockImplementation(async () => {});
    const stop = vi.fn(async () => finishFirst());
    const h = build({
      chat: {
        sendMessage,
        stop,
        appendMessage: vi.fn(),
        readAnswer: async () => ({
          text: 'tuesday: sunny',
          pendingQuestion: null,
          register: 'warm',
        }),
      },
    });
    await h.controller.start();
    const first = h.transport.events.onDelegation?.([{ id: 'c1', request: 'weather monday' }]);
    const second = h.transport.events.onDelegation?.([{ id: 'c2', request: 'weather tuesday' }]);
    await first;
    await second;
    expect(stop).toHaveBeenCalledTimes(1);
    const answers = h.transport.sent.filter(s => s.kind === 'answer').map(s => s.args);
    // The answer travels with the note of the register it wore (ADR-253),
    // mapped through the config's own lines; a silent close carries none.
    expect(answers).toEqual([
      ['c1', 'X', 'silent', null],
      ['c2', 'tuesday: sunny', 'now', 'W'],
    ]);
    expect(useLiveStore.getState().delegating).toBe(false);
  });

  it('speaks a late answer as text and keeps the tool cancellation', async () => {
    const h = build({
      chat: {
        sendMessage: vi.fn(() => new Promise<void>(() => {})),
        stop: vi.fn(async () => {}),
        appendMessage: vi.fn(),
        readAnswer: async () => ({ text: 'late', pendingQuestion: null }),
      },
    });
    await h.controller.start();
    const pending = h.transport.events.onDelegation?.([{ id: 'c1', request: 'x' }]);
    expect(useLiveStore.getState().delegating).toBe(true);
    expect(useLiveStore.getState().voiceState).toBe('processing');
    h.transport.events.onDelegationCancelled?.(['c1']);
    await vi.advanceTimersByTimeAsync(START.delegation_timeout_seconds * 1000 + 1);
    await pending;
    expect(h.transport.sent.some(s => s.kind === 'answer')).toBe(false);
  });

  it('stops saying LIA is working once a turn that outlived its wait ends', async () => {
    let finish: () => void = () => {};
    const h = build({
      chat: {
        sendMessage: vi.fn(
          () =>
            new Promise<void>(resolve => {
              finish = resolve;
            })
        ),
        stop: vi.fn(async () => {}),
        appendMessage: vi.fn(),
        readAnswer: async () => ({ text: 'late answer', pendingQuestion: null }),
      },
    });
    await h.controller.start();
    const pending = h.transport.events.onDelegation?.([{ id: 'c1', request: 'x' }]);
    await vi.advanceTimersByTimeAsync(START.delegation_timeout_seconds * 1000 + 1);
    await pending;
    // The voice was told to wait; the banner still says LIA is working.
    expect(h.transport.sent.at(-1)?.args[1]).toBe('T');
    expect(useLiveStore.getState().delegating).toBe(true);
    finish();
    await vi.advanceTimersByTimeAsync(10);
    // The turn ended: the late answer is spoken and the banner is idle again.
    expect(h.transport.sent.at(-1)).toEqual({ kind: 'text', args: ['late answer'] });
    expect(useLiveStore.getState().delegating).toBe(false);
    expect(useLiveStore.getState().voiceState).toBe('idle');
  });

  it('ignores a stale socket resumption handle and cancellation', async () => {
    const h = build();
    await h.controller.start();
    h.transport.events.onResumption?.('h1', true);
    const stale = h.transport.events;
    h.transport.events.onGoAway?.(0);
    await vi.advanceTimersByTimeAsync(10);
    expect(h.transport.connects[1].handle).toBe('h1');
    stale.onResumption?.('h-old', true);
    h.transport.events.onGoAway?.(0);
    await vi.advanceTimersByTimeAsync(10);
    // The reconnection rides the FRESH socket's last handle, never the stale one.
    expect(h.transport.connects[2].handle).toBe('h1');
  });

  it('publishes the rates at the start and folds the provider usage into the meter (ADR-300 wave 3)', async () => {
    const h = build();
    await h.controller.start();
    const state = useLiveStore.getState();
    expect(state.rates).toEqual(START.rates);
    expect(state.liveSince).not.toBeNull();
    const liveSince = state.liveSince;
    h.transport.events.onUsage?.({
      tokens: { textIn: 100, audioIn: 20, textOut: 10, audioOut: 5, thoughts: 3, context: 138 },
    });
    h.transport.events.onUsage?.({
      tokens: { textIn: 120, audioIn: 25, textOut: 12, audioOut: 8, thoughts: 0, context: 165 },
    });
    expect(useLiveStore.getState().meter).toMatchObject({
      textIn: 220,
      audioIn: 45,
      textOut: 22,
      audioOut: 13,
      thoughts: 3,
      context: 165,
      reports: 2,
    });
    // A reconnection keeps the clock: the meter's origin is the FIRST live instant.
    const stale = h.transport.events;
    h.transport.events.onGoAway?.(0);
    await vi.advanceTimersByTimeAsync(10);
    expect(useLiveStore.getState().liveSince).toBe(liveSince);
    // A stale socket's late report is ignored.
    stale.onUsage?.({
      tokens: { textIn: 999, audioIn: 0, textOut: 0, audioOut: 0, thoughts: 0, context: 999 },
    });
    expect(useLiveStore.getState().meter.textIn).toBe(220);
  });

  /** A start answering with THIS session (the ceiling, the rates), the rest as usual. */
  function startingWith(start: LiveSessionStart) {
    const post = vi.fn(async (url: string): Promise<unknown> => {
      if (url === '/live/sessions') return start;
      if (url.endsWith('/end'))
        return {
          summary_message_id: 's1',
          duration_seconds: 10,
          delegations: 0,
          voice_turns: 0,
          usage: null,
        };
      return {};
    });
    return { h: build({ api: fakeApi(post) }), post };
  }

  it('ends the session at the spend ceiling the connector set, on a usage report (ADR-300 wave 3)', async () => {
    const { h, post } = startingWith({ ...START, session_budget_eur: 0.001 });
    await h.controller.start();
    // (500 000 × 0.75 + 20 000 × 12) / 1e6 × 0.9 ≈ 0,55 € ≥ 0,001 €
    h.transport.events.onUsage?.({
      tokens: {
        textIn: 500_000,
        audioIn: 0,
        textOut: 0,
        audioOut: 20_000,
        thoughts: 0,
        context: 1,
      },
    });
    await vi.advanceTimersByTimeAsync(10);
    expect(useLiveStore.getState()).toMatchObject({ status: 'ended', outcome: 'budget_reached' });
    expect(post).toHaveBeenCalledWith(
      `/live/sessions/${START.session_id}/end`,
      expect.objectContaining({ outcome: 'budget_reached' })
    );
  });

  it('ends a minute-billed session at its ceiling by the clock, without any provider report', async () => {
    const rates = {
      pricing_unit: 'per_audio_minute' as const,
      input_unit_price: 0.6,
      output_unit_price: 0,
      audio_input_unit_price: null,
      audio_output_unit_price: null,
      usd_eur_rate: 1,
    };
    // 0.6 $/min = 0.01 €/s at parity: a 0.05 € ceiling is reached after 5 s.
    const { h } = startingWith({ ...START, rates, session_budget_eur: 0.05 });
    await h.controller.start();
    await vi.advanceTimersByTimeAsync(4_000);
    expect(useLiveStore.getState().status).toBe('live');
    await vi.advanceTimersByTimeAsync(1_500);
    expect(useLiveStore.getState()).toMatchObject({ status: 'ended', outcome: 'budget_reached' });
  });

  it('closes the books when the provider the API named has no transport here', async () => {
    // Minted and claimed server-side: the record must not wait for its TTL.
    const h = build({
      createTransport: () => {
        throw new Error('live_provider_unsupported:nope');
      },
    });
    await h.controller.start();
    expect(h.post).toHaveBeenCalledWith(
      `/live/sessions/${SESSION}/end`,
      expect.objectContaining({ outcome: 'error' })
    );
    expect(useLiveStore.getState()).toMatchObject({ status: 'ended', outcome: 'error' });
    expect(useLiveStore.getState().error).toContain('live_provider_unsupported');
  });

  it('refuses an unsupported browser before any request leaves', async () => {
    const h = build({ isSupported: () => false });
    await h.controller.start();
    expect(h.post).not.toHaveBeenCalled();
    expect(h.transport.connects).toEqual([]);
    expect(useLiveStore.getState().status).toBe('ended');
    expect(useLiveStore.getState().outcome).toBe('error');
    expect(useLiveStore.getState().error).toBe('unsupported_browser');
  });

  it('closes the books even when the microphone refuses to stop', async () => {
    const h = build();
    h.mic.stop.mockRejectedValueOnce(new Error('device gone'));
    await h.controller.start();
    await h.controller.end('ended');
    expect(h.post).toHaveBeenCalledWith(`/live/sessions/${SESSION}/end`, {
      outcome: 'ended',
      detail: null,
      provider_conversation_id: null,
    });
    expect(useLiveStore.getState().status).toBe('ended');
  });

  it('closes itself as superseded when the API no longer holds the session', async () => {
    // A newer tab took the account's slot: this one must not keep talking as
    // if it were the session. The first refused archive names it.
    const gone = Object.assign(new Error('not found'), { status: 404 });
    const post = vi.fn(async (url: string): Promise<unknown> => {
      if (url === '/live/sessions') return START;
      throw gone;
    });
    const h = build({ api: fakeApi(post) });
    await h.controller.start();
    h.transport.events.onTranscript?.('user', 'hello');
    h.transport.events.onTurnComplete?.();
    await vi.advanceTimersByTimeAsync(10);
    expect(useLiveStore.getState()).toMatchObject({ status: 'ended', outcome: 'superseded' });
    expect(h.transport.closes).toBeGreaterThan(0);
    expect(h.mic.stop).toHaveBeenCalledTimes(1);
  });

  it('a DIRECT session posts its mode, never builds the bridge, and answers every tool call through the API (ADR-300 wave 4)', async () => {
    const tools: unknown[] = [];
    const turns: unknown[] = [];
    const h = build({
      api: fakeApi(async (url: string, body?: unknown) => {
        if (url === '/live/sessions') {
          expect(body).toEqual({ mode: 'direct' });
          return { ...START, mode: 'direct' };
        }
        if (url.endsWith('/tools')) {
          tools.push(body);
          const name = (body as { name: string }).name;
          if (name === 'send_email_tool') return { text: 'refused', ok: false };
          return { text: 'Two events tomorrow.', ok: true };
        }
        if (url.endsWith('/turns')) {
          turns.push(body);
          // A DIRECT session's door keeps the turn and answers no row id.
          return { user_message_id: null, assistant_message_id: null };
        }
        if (url.endsWith('/end'))
          return {
            summary_message_id: 's-direct',
            duration_seconds: 1,
            delegations: 0,
            voice_turns: 0,
            extensions: 0,
            usage: null,
          };
        return {};
      }),
    });
    await h.controller.start('direct');
    expect(useLiveStore.getState().status).toBe('live');
    expect(useLiveStore.getState().mode).toBe('direct');

    // A lookup: the banner says LIA is working while it runs, the result goes
    // back on the same call id, spoken at once; nothing reaches the chat.
    h.transport.events.onTranscript?.('user', 'what is on my agenda tomorrow');
    const lookup = h.transport.events.onDelegation?.([
      {
        id: 'c1',
        request: null,
        call: { name: 'get_events_tool', args: { query: 'tomorrow' } },
      },
    ]);
    expect(useLiveStore.getState().delegating).toBe(true);
    expect(useLiveStore.getState().voiceState).toBe('processing');
    await lookup;
    expect(tools).toEqual([{ name: 'get_events_tool', arguments: { query: 'tomorrow' } }]);
    expect(h.transport.sent.at(-1)).toEqual({
      kind: 'answer',
      args: ['c1', 'Two events tomorrow.', 'now', null],
    });
    expect(useLiveStore.getState().delegating).toBe(false);
    expect(h.chat.sendMessage).not.toHaveBeenCalled();

    // A refusal is a sentence the voice says, handed back the same way.
    await h.transport.events.onDelegation?.([
      { id: 'c2', request: null, call: { name: 'send_email_tool', args: {} } },
    ]);
    expect(h.transport.sent.at(-1)).toEqual({
      kind: 'answer',
      args: ['c2', 'refused', 'now', null],
    });

    // A direct session archives NO row of the exchange: its turns are handed
    // to the record through the same door (ADR-301), which answers no id —
    // nothing reaches the thread, the captions live in the banner alone
    // until the end, when the words become the person's own turn.
    h.transport.events.onTranscript?.('assistant', 'You have two events.');
    h.transport.events.onTurnComplete?.();
    await vi.advanceTimersByTimeAsync(10);
    expect(turns).toHaveLength(1);
    expect(turns[0]).toMatchObject({
      user_text: 'what is on my agenda tomorrow',
      assistant_text: 'You have two events.',
    });
    expect(h.chat.appendMessage).not.toHaveBeenCalled();
    expect(h.chat.appendMessage).not.toHaveBeenCalled();
    expect(useLiveStore.getState().captions.map(c => c.text)).toEqual([
      'what is on my agenda tomorrow',
      'You have two events.',
    ]);
    await h.controller.end();
    // The closing card names its mode: the card draws no exchange count for it.
    expect(h.chat.appendMessage.mock.calls.at(-1)?.[0]).toMatchObject({
      metadata: { type: 'live_session_summary', live_summary: { mode: 'direct' } },
    });
  });

  it('a DIRECT session answers the browser-held line when the tool door cannot be reached, and closes when the session is gone', async () => {
    let fail: 'network' | 'gone' = 'network';
    const h = build({
      api: fakeApi(async (url: string) => {
        if (url === '/live/sessions') return { ...START, mode: 'direct' };
        if (url.endsWith('/tools')) {
          if (fail === 'gone') throw Object.assign(new Error('gone'), { status: 404 });
          throw new Error('network');
        }
        if (url.endsWith('/end')) return { summary_message_id: null, duration_seconds: 1 };
        return {};
      }),
    });
    await h.controller.start('direct');
    await h.transport.events.onDelegation?.([
      { id: 'c1', request: null, call: { name: 'get_events_tool', args: {} } },
    ]);
    expect(h.transport.sent.at(-1)).toEqual({ kind: 'answer', args: ['c1', 'F', 'now', null] });
    expect(useLiveStore.getState().delegating).toBe(false);
    expect(useLiveStore.getState().status).toBe('live');
    fail = 'gone';
    await h.transport.events.onDelegation?.([
      { id: 'c2', request: null, call: { name: 'get_events_tool', args: {} } },
    ]);
    await vi.advanceTimersByTimeAsync(10);
    expect(useLiveStore.getState().status).toBe('ended');
    expect(useLiveStore.getState().outcome).toBe('superseded');
  });

  it('a delegated session posts its mode too', async () => {
    const h = build();
    await h.controller.start();
    expect(h.post).toHaveBeenCalledWith('/live/sessions', { mode: 'delegated' });
    expect(useLiveStore.getState().mode).toBe('delegated');
    await h.controller.end();
  });

  it('refuses to start twice and ignores a second start while live', async () => {
    const h = build();
    await h.controller.start();
    await h.controller.start();
    expect(h.post.mock.calls.filter(([url]) => url === '/live/sessions')).toHaveLength(1);
  });

  it("hands the provider's conversation id to the end and publishes the vendor's bill (owner request 2026-09-20)", async () => {
    const bill = {
      provider: 'elevenlabs',
      cost_usd: 0.1234,
      credits: 12,
      llm_credits: 4,
      call_credits: 8,
      platform_credits: 0,
      llm_model: 'gemini-3.6-flash',
      tts_model: 'eleven_v3_conversational',
      duration_seconds: 95,
    };
    const h = build();
    const plain = h.post.getMockImplementation()!;
    h.post.mockImplementation(async (url: string, body?: unknown) => {
      const answer = (await plain(url, body)) as Record<string, unknown>;
      return url.endsWith('/end') ? { ...answer, vendor_bill: bill } : answer;
    });
    await h.controller.start();
    h.transport.events.onProviderConversation?.('conv_42');
    await h.controller.end('ended');
    expect(h.post).toHaveBeenCalledWith(`/live/sessions/${SESSION}/end`, {
      outcome: 'ended',
      detail: null,
      provider_conversation_id: 'conv_42',
    });
    // Shown to the person (the banner tells it once), never on the card.
    expect(useLiveStore.getState().vendorBill).toEqual(bill);
    const summary = h.chat.appendMessage.mock.calls.at(-1)?.[0];
    expect(JSON.stringify(summary)).not.toContain('0.1234');
  });
});
