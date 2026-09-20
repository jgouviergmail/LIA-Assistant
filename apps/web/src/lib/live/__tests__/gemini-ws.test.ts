/**
 * GeminiLiveTransport — the documented JSON messages, nothing else.
 *
 *  - the token travels as `access_token` in the query of the CONSTRAINED
 *    method (measured 2026-09-18: the plain method refuses a token with 1008),
 *    and the setup is the FIRST frame;
 *  - a resumption handle rides `sessionResumption.handle` in that setup;
 *  - audio parts are decoded to raw PCM; transcripts, tool calls, cancellation,
 *    goAway (a "12s" duration), interruption and resumption updates are reported;
 *  - a delegation answer carries `id`, `name`, `response.result` and the
 *    `scheduling` the delivery mode maps to — omitted where the model refuses it;
 *  - a paused microphone tells the provider `audioStreamEnd` (the detection is
 *    always automatic: no held button, no manual markers);
 *  - `interactionStatus` and `generationComplete` are reported;
 *  - a malformed frame is reported as an error, never thrown;
 *  - a close before `setupComplete` rejects the connect promise once.
 */
import { describe, it, expect, vi, beforeEach, afterEach, type Mock } from 'vitest';

import { arrayBufferToBase64 } from '../base64';
import { GeminiLiveTransport, GEMINI_LIVE_WS_URL } from '../transports/gemini-ws';
import type { LiveConnectOptions, LiveModelCapabilities, LiveTransportEvents } from '../types';

const CAPABILITIES: LiveModelCapabilities = {
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
};

function options(overrides: Partial<LiveConnectOptions> = {}): LiveConnectOptions {
  return {
    credential: 'tok/1',
    setup: { model: 'models/m' },
    resumptionHandle: null,
    capabilities: CAPABILITIES,
    ...overrides,
  };
}

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string | ArrayBuffer | Blob }) => void) | null = null;
  binaryType: 'blob' | 'arraybuffer' = 'blob';
  onclose: ((event: { code: number; reason: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  readyState = 0;
  sent: string[] = [];
  constructor(readonly url: string) {
    FakeWebSocket.instances.push(this);
  }
  send(data: string) {
    this.sent.push(data);
  }
  close(code?: number, reason?: string) {
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.({ code: code ?? 1000, reason: reason ?? '' });
  }
  open() {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.();
  }
  emit(payload: unknown) {
    this.onmessage?.({ data: JSON.stringify(payload) });
  }
  /** The provider's frames are BINARY (measured 2026-09-18): the browser hands bytes, not text. */
  emitBinary(payload: unknown) {
    // Built on the page's own ArrayBuffer: under jsdom, Node's TextEncoder
    // hands a buffer of ANOTHER realm, which `instanceof ArrayBuffer` refuses.
    const bytes = new TextEncoder().encode(JSON.stringify(payload));
    const data = new ArrayBuffer(bytes.byteLength);
    new Uint8Array(data).set(bytes);
    this.onmessage?.({ data });
  }
}

type Handler<K extends keyof LiveTransportEvents> = NonNullable<LiveTransportEvents[K]>;
type EventMocks = { [K in keyof LiveTransportEvents]-?: Mock<Handler<K>> };

function events(): EventMocks {
  return {
    onReady: vi.fn<Handler<'onReady'>>(),
    onUsage: vi.fn<Handler<'onUsage'>>(),
    onAudio: vi.fn<Handler<'onAudio'>>(),
    onSpeakingChange: vi.fn<Handler<'onSpeakingChange'>>(),
    onTranscript: vi.fn<Handler<'onTranscript'>>(),
    onTurnComplete: vi.fn<Handler<'onTurnComplete'>>(),
    onGenerationComplete: vi.fn<Handler<'onGenerationComplete'>>(),
    onInteractionStatus: vi.fn<Handler<'onInteractionStatus'>>(),
    onInterrupted: vi.fn<Handler<'onInterrupted'>>(),
    onDelegation: vi.fn<Handler<'onDelegation'>>(),
    onDelegationCancelled: vi.fn<Handler<'onDelegationCancelled'>>(),
    onGoAway: vi.fn<Handler<'onGoAway'>>(),
    onResumption: vi.fn<Handler<'onResumption'>>(),
    onProviderConversation: vi.fn<Handler<'onProviderConversation'>>(),
    onClosed: vi.fn<Handler<'onClosed'>>(),
    onError: vi.fn<Handler<'onError'>>(),
  };
}

describe('GeminiLiveTransport', () => {
  const realWebSocket = globalThis.WebSocket;
  beforeEach(() => {
    FakeWebSocket.instances = [];
    (globalThis as { WebSocket: unknown }).WebSocket = FakeWebSocket;
  });
  afterEach(() => {
    (globalThis as { WebSocket: unknown }).WebSocket = realWebSocket;
  });

  async function connected(overrides: Partial<LiveConnectOptions> = {}) {
    const transport = new GeminiLiveTransport();
    const ev = events();
    const pending = transport.connect(options(overrides), ev);
    const socket = FakeWebSocket.instances[0];
    socket.open();
    socket.emit({ setupComplete: {} });
    await pending;
    return { transport, socket, ev };
  }

  it('opens on the constrained method with the token and sends the setup first', async () => {
    const { socket, ev, transport } = await connected();
    expect(GEMINI_LIVE_WS_URL).toMatch(/BidiGenerateContentConstrained$/);
    expect(socket.url).toBe(`${GEMINI_LIVE_WS_URL}?access_token=tok%2F1`);
    expect(JSON.parse(socket.sent[0])).toEqual({ setup: { model: 'models/m' } });
    expect(ev.onReady).toHaveBeenCalledTimes(1);
    expect(transport.isOpen).toBe(true);
  });

  it('declares its audio: PCM it hands over, 16 kHz in, 24 kHz out, 40 ms chunks', () => {
    // The Live API best practices ask for 20-40 ms chunks and a 16 kHz input;
    // the controller sizes the microphone and the player from THIS, never
    // from a constant of its own (a second provider streams 24 kHz both ways).
    expect(new GeminiLiveTransport().audio).toEqual({
      ownership: 'pcm',
      inputRate: 16000,
      outputRate: 24000,
      chunkMs: 40,
    });
  });

  it('reads the binary frames the provider actually sends', async () => {
    // Measured on Docker dev 2026-09-18: every frame from the provider arrives
    // as a binary message (a Blob under the default binaryType), so a text-only
    // reader never saw `setupComplete` and the banner said « Connecting… »
    // for ever. The transport asks for ArrayBuffers and decodes them itself.
    const transport = new GeminiLiveTransport();
    const ev = events();
    const pending = transport.connect(options({ credential: 't' }), ev);
    const socket = FakeWebSocket.instances[0];
    expect(socket.binaryType).toBe('arraybuffer');
    socket.open();
    socket.emitBinary({ setupComplete: {} });
    await pending;
    socket.emitBinary({ serverContent: { outputTranscription: { text: 'héllo' } } });
    expect(ev.onReady).toHaveBeenCalledTimes(1);
    expect(ev.onTranscript).toHaveBeenCalledWith('assistant', 'héllo');
    expect(ev.onError).not.toHaveBeenCalled();
  });

  it('rides the resumption handle in the setup without touching the caller setup', async () => {
    const setup = { model: 'models/m' };
    const transport = new GeminiLiveTransport();
    const pending = transport.connect(
      options({ credential: 't', setup, resumptionHandle: 'h1' }),
      events()
    );
    const socket = FakeWebSocket.instances[0];
    socket.open();
    socket.emit({ setupComplete: {} });
    await pending;
    expect(JSON.parse(socket.sent[0]).setup.sessionResumption).toEqual({ handle: 'h1' });
    expect(setup).toEqual({ model: 'models/m' });
  });

  it('reports audio, transcripts, turn completion and interruption', async () => {
    const { socket, ev } = await connected();
    const pcm = new Int16Array([1, -1]).buffer;
    socket.emit({
      serverContent: {
        modelTurn: {
          parts: [
            { inlineData: { mimeType: 'audio/pcm;rate=24000', data: arrayBufferToBase64(pcm) } },
          ],
        },
        outputTranscription: { text: 'hello' },
      },
    });
    socket.emit({ serverContent: { inputTranscription: { text: 'hi' }, turnComplete: true } });
    socket.emit({ serverContent: { interrupted: true } });
    socket.emit({ serverContent: { generationComplete: true } });
    expect(new Int16Array(ev.onAudio.mock.calls[0][0])).toEqual(new Int16Array([1, -1]));
    expect(ev.onTranscript).toHaveBeenCalledWith('assistant', 'hello');
    expect(ev.onTranscript).toHaveBeenCalledWith('user', 'hi');
    expect(ev.onTurnComplete).toHaveBeenCalledTimes(1);
    expect(ev.onInterrupted).toHaveBeenCalledTimes(1);
    expect(ev.onGenerationComplete).toHaveBeenCalledTimes(1);
  });

  it('reports the interaction status in either documented shape', async () => {
    // Extended Thinking says when its task is done; the field is documented
    // as an object on serverContent, the cookbook reads it as a string.
    const { socket, ev } = await connected();
    socket.emit({ serverContent: { interactionStatus: 'IN_PROGRESS' } });
    socket.emit({ serverContent: { interactionStatus: { status: 'IDLE' } } });
    socket.emit({ serverContent: { interactionStatus: { state: 'IN_PROGRESS' } } });
    socket.emit({ serverContent: { interactionStatus: 'SOMETHING_NEW' } });
    expect(ev.onInteractionStatus.mock.calls.map(c => c[0])).toEqual([
      'in_progress',
      'idle',
      'in_progress',
    ]);
  });

  it('reports delegations by id and request, cancellations, goAway and resumption', async () => {
    const { socket, ev } = await connected();
    socket.emit({
      toolCall: {
        functionCalls: [
          { id: 'c1', name: 'send_to_lia', args: { request: 'x' } },
          { id: 'c2', name: 'send_to_lia', args: {} },
        ],
      },
    });
    socket.emit({ toolCallCancellation: { ids: ['c1'] } });
    socket.emit({ goAway: { timeLeft: '12s' } });
    socket.emit({ sessionResumptionUpdate: { newHandle: 'h2', resumable: true } });
    socket.emit({ sessionResumptionUpdate: { newHandle: '', resumable: true } });
    // The call itself travels with the delegation: a DIRECT session reads the
    // tool's name and arguments where a delegated one reads the request.
    expect(ev.onDelegation).toHaveBeenCalledWith([
      { id: 'c1', request: 'x', call: { name: 'send_to_lia', args: { request: 'x' } } },
      { id: 'c2', request: null, call: { name: 'send_to_lia', args: {} } },
    ]);
    expect(ev.onDelegationCancelled).toHaveBeenCalledWith(['c1']);
    expect(ev.onGoAway).toHaveBeenCalledWith(12000);
    expect(ev.onResumption).toHaveBeenCalledTimes(1);
    expect(ev.onResumption).toHaveBeenCalledWith('h2', true);
  });

  it('sends audio, text and delegation answers in the documented shapes', async () => {
    const { transport, socket } = await connected();
    socket.emit({
      toolCall: { functionCalls: [{ id: 'c1', name: 'send_to_lia', args: { request: 'x' } }] },
    });
    transport.sendAudio(new Int16Array([5]).buffer);
    transport.sendText('late result');
    transport.answerDelegation('c1', 'two meetings', 'when_idle', 'LIA said this warmly.');
    const [, audio, text, tool] = socket.sent.map(s => JSON.parse(s));
    expect(audio.realtimeInput.audio.mimeType).toBe('audio/pcm;rate=16000');
    expect(text.clientContent).toEqual({
      turns: [{ role: 'user', parts: [{ text: 'late result' }] }],
      turnComplete: true,
    });
    // The function NAME travels back: it was remembered from the call.
    // The delivery note rides the response as its own field (the mandate names it).
    expect(tool.toolResponse.functionResponses[0]).toEqual({
      id: 'c1',
      name: 'send_to_lia',
      response: { result: 'two meetings', tone: 'LIA said this warmly.' },
      scheduling: 'WHEN_IDLE',
    });
  });

  it('omits the scheduling where the model refuses it (Extended Thinking)', async () => {
    const { transport, socket } = await connected({
      capabilities: { ...CAPABILITIES, delivery_scheduling: false },
    });
    socket.emit({
      toolCall: { functionCalls: [{ id: 'c1', name: 'send_to_lia', args: { request: 'x' } }] },
    });
    transport.answerDelegation('c1', 'done', 'now');
    const tool = JSON.parse(socket.sent.at(-1) ?? '{}');
    expect(tool.toolResponse.functionResponses[0]).toEqual({
      id: 'c1',
      name: 'send_to_lia',
      response: { result: 'done' },
    });
  });

  it('tells a paused microphone the documented way: a stream end, nothing when active', async () => {
    // Automatic VAD: a paused microphone flushes the server's cached audio
    // (audioStreamEnd); an active one says nothing.
    const auto = await connected();
    auto.transport.setInputActive(true);
    auto.transport.setInputActive(false);
    expect(auto.socket.sent.slice(1).map(s => JSON.parse(s))).toEqual([
      { realtimeInput: { audioStreamEnd: true } },
    ]);
  });

  it('reports a usageMetadata frame as a token report, by modality (ADR-300 wave 3)', async () => {
    const { socket, ev } = await connected();
    socket.emitBinary({
      usageMetadata: {
        promptTokenCount: 1227,
        responseTokenCount: 68,
        totalTokenCount: 1295,
        promptTokensDetails: [
          { modality: 'TEXT', tokenCount: 974 },
          { modality: 'AUDIO', tokenCount: 198 },
        ],
        responseTokensDetails: [{ modality: 'AUDIO', tokenCount: 48 }],
        thoughtsTokenCount: 115,
      },
    });
    expect(ev.onUsage).toHaveBeenCalledWith({
      tokens: {
        textIn: 1029,
        audioIn: 198,
        textOut: 20,
        audioOut: 48,
        thoughts: 115,
        context: 1295,
      },
    });
    // A frame without usage reports nothing.
    socket.emitBinary({ serverContent: { turnComplete: true } });
    expect(ev.onUsage).toHaveBeenCalledTimes(1);
  });

  it('drops what is sent on a closed socket instead of throwing', async () => {
    const { transport, socket } = await connected();
    await transport.close();
    transport.sendText('after');
    expect(socket.sent).toHaveLength(1);
  });

  it('reports a malformed frame as an error and a close with its code', async () => {
    const { socket, ev, transport } = await connected();
    socket.onmessage?.({ data: '{not json' });
    expect(ev.onError).toHaveBeenCalledTimes(1);
    await transport.close();
    expect(ev.onClosed).toHaveBeenCalledWith(1000, '');
    expect(transport.isOpen).toBe(false);
  });

  it('rejects the connect promise on a close before setupComplete, once', async () => {
    const transport = new GeminiLiveTransport();
    const ev = events();
    const pending = transport.connect(options({ credential: 't', setup: {} }), ev);
    const socket = FakeWebSocket.instances[0];
    socket.open();
    socket.onerror?.();
    socket.close(1008, 'refused');
    // The close that follows the error names the code AND the reason — as the
    // connect's own failure, never as a provider close of an open session.
    await expect(pending).rejects.toThrow('live_socket_closed_1008: refused');
    expect(ev.onClosed).not.toHaveBeenCalled();
    expect(ev.onError).toHaveBeenCalledTimes(1);
  });
});
