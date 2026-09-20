/**
 * ElevenLabsLiveTransport — the SDK's wire (ADR-300 wave 4), nothing else.
 *
 *  - the credential IS the socket's URL (a signed URL), opened on the `convai`
 *    subprotocol, and the initiation the API rendered is the FIRST frame;
 *  - the metadata frame opens the session and names the agent's OUTPUT rate,
 *    which the transport's audio contract follows;
 *  - audio events are decoded to raw PCM, and those an interruption covered
 *    are dropped; `user_transcript` and `agent_response` are reported, the
 *    latter closing the turn; a client tool call is a delegation carrying the
 *    call; a ping is answered with its pong;
 *  - a delegation answer is a `client_tool_result`, the delivery note riding
 *    beside the result in one JSON string;
 *  - a malformed frame is reported as an error, never thrown;
 *  - a close before the metadata rejects the connect promise once.
 */
import { describe, it, expect, vi, beforeEach, afterEach, type Mock } from 'vitest';

import { arrayBufferToBase64 } from '../base64';
import {
  ELEVENLABS_CLOSE_WAIT_MS,
  ELEVENLABS_LIVE_AUDIO,
  ELEVENLABS_WS_SUBPROTOCOL,
  ElevenLabsLiveTransport,
  outputRateOf,
} from '../transports/elevenlabs-ws';
import type { LiveConnectOptions, LiveModelCapabilities, LiveTransportEvents } from '../types';

const CAPABILITIES: LiveModelCapabilities = {
  async_delegation: false,
  delivery_scheduling: false,
  reports_idle: false,
  cancels_on_interruption: false,
  configurable_vad: false,
  resumes: false,
  thinking: false,
  direct_tools: true,
  portal_voice: true,
  vendor_billed: true,
};

const SIGNED = 'wss://api.elevenlabs.io/v1/convai/conversation?agent_id=a&conversation_signature=s';
const SETUP = {
  type: 'conversation_initiation_client_data',
  conversation_config_override: { agent: { prompt: { prompt: 'mandate' } } },
};

function options(overrides: Partial<LiveConnectOptions> = {}): LiveConnectOptions {
  return { credential: SIGNED, setup: SETUP, capabilities: CAPABILITIES, ...overrides };
}

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string | ArrayBuffer }) => void) | null = null;
  binaryType: 'blob' | 'arraybuffer' = 'blob';
  onclose: ((event: { code: number; reason: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  readyState = 0;
  sent: string[] = [];
  constructor(
    readonly url: string,
    readonly protocols?: string[]
  ) {
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

const METADATA = {
  type: 'conversation_initiation_metadata',
  conversation_initiation_metadata_event: {
    conversation_id: 'conv_1',
    agent_output_audio_format: 'pcm_24000',
    user_input_audio_format: 'pcm_16000',
  },
};

describe('ElevenLabsLiveTransport', () => {
  it("names the provider's own conversation from the metadata (the end reads the vendor's bill under it)", async () => {
    const { ev } = await connected();
    expect(ev.onProviderConversation).toHaveBeenCalledWith('conv_1');
  });

  it('names no conversation when the metadata carries none', async () => {
    const { ev } = await connected({
      type: 'conversation_initiation_metadata',
      conversation_initiation_metadata_event: { agent_output_audio_format: 'pcm_24000' },
    });
    expect(ev.onProviderConversation).not.toHaveBeenCalled();
  });

  const realWebSocket = globalThis.WebSocket;
  beforeEach(() => {
    FakeWebSocket.instances = [];
    (globalThis as { WebSocket: unknown }).WebSocket = FakeWebSocket;
  });
  afterEach(() => {
    (globalThis as { WebSocket: unknown }).WebSocket = realWebSocket;
  });

  async function connected(metadata: unknown = METADATA) {
    const transport = new ElevenLabsLiveTransport();
    const ev = events();
    const pending = transport.connect(options(), ev);
    const socket = FakeWebSocket.instances[0];
    socket.open();
    socket.emit(metadata);
    await pending;
    return { transport, socket, ev };
  }

  it('opens the signed URL on the convai subprotocol, sends the initiation first, reads the output rate', async () => {
    const { transport, socket, ev } = await connected();
    expect(socket.url).toBe(SIGNED);
    expect(socket.protocols).toEqual([ELEVENLABS_WS_SUBPROTOCOL]);
    expect(socket.binaryType).toBe('arraybuffer');
    expect(JSON.parse(socket.sent[0])).toEqual(SETUP);
    expect(ev.onReady).toHaveBeenCalledTimes(1);
    expect(transport.isOpen).toBe(true);
    // The agent's own output rate; the input stays what LIA captures at.
    expect(transport.audio).toEqual({ ...ELEVENLABS_LIVE_AUDIO, outputRate: 24000 });
  });

  it('keeps the default rate when the metadata names no PCM format', async () => {
    const { transport } = await connected({
      type: 'conversation_initiation_metadata',
      conversation_initiation_metadata_event: { conversation_id: 'c' },
    });
    expect(transport.audio.outputRate).toBe(ELEVENLABS_LIVE_AUDIO.outputRate);
    expect(outputRateOf('pcm_44100')).toBe(44100);
    expect(outputRateOf('ulaw_8000')).toBeNull();
    expect(outputRateOf(undefined)).toBeNull();
  });

  it('decodes audio, drops what an interruption covered, reports transcripts and the turn end', async () => {
    const { socket, ev } = await connected();
    const pcm = new Int16Array([1, -1, 2]).buffer;
    socket.emit({
      type: 'audio',
      audio_event: { audio_base_64: arrayBufferToBase64(pcm), event_id: 3 },
    });
    expect(ev.onAudio).toHaveBeenCalledTimes(1);
    expect(new Int16Array(ev.onAudio.mock.calls[0][0])).toEqual(new Int16Array([1, -1, 2]));
    socket.emit({ type: 'interruption', interruption_event: { event_id: 5 } });
    expect(ev.onInterrupted).toHaveBeenCalledTimes(1);
    socket.emit({
      type: 'audio',
      audio_event: { audio_base_64: arrayBufferToBase64(pcm), event_id: 4 },
    });
    socket.emit({
      type: 'audio',
      audio_event: { audio_base_64: arrayBufferToBase64(pcm), event_id: 6 },
    });
    expect(ev.onAudio).toHaveBeenCalledTimes(2);
    socket.emit({
      type: 'user_transcript',
      user_transcription_event: { user_transcript: 'quoi demain ?' },
    });
    expect(ev.onTranscript).toHaveBeenLastCalledWith('user', 'quoi demain ?');
    expect(ev.onTurnComplete).not.toHaveBeenCalled();
    socket.emit({
      type: 'agent_response',
      agent_response_event: { agent_response: 'Deux réunions.' },
    });
    expect(ev.onTranscript).toHaveBeenLastCalledWith('assistant', 'Deux réunions.');
    expect(ev.onTurnComplete).toHaveBeenCalledTimes(1);
  });

  it('answers a ping, reports a client tool call as a delegation carrying the call', async () => {
    const { socket, ev } = await connected();
    socket.emit({ type: 'ping', ping_event: { event_id: 42, ping_ms: 10 } });
    expect(JSON.parse(socket.sent.at(-1)!)).toEqual({ type: 'pong', event_id: 42 });
    socket.emit({
      type: 'client_tool_call',
      client_tool_call: {
        tool_name: 'send_to_lia',
        tool_call_id: 'call_1',
        parameters: { request: 'Quoi demain ?' },
      },
    });
    expect(ev.onDelegation).toHaveBeenCalledWith([
      {
        id: 'call_1',
        request: 'Quoi demain ?',
        call: { name: 'send_to_lia', args: { request: 'Quoi demain ?' } },
      },
    ]);
    socket.emit({
      type: 'client_tool_call',
      client_tool_call: { tool_name: 'get_events_tool', tool_call_id: 'call_2', parameters: {} },
    });
    expect(ev.onDelegation).toHaveBeenLastCalledWith([
      { id: 'call_2', request: null, call: { name: 'get_events_tool', args: {} } },
    ]);
  });

  it('sends audio chunks, a text turn and a tool result with the note beside it', async () => {
    const { transport, socket } = await connected();
    const pcm = new Int16Array([7, 8]).buffer;
    transport.sendAudio(pcm);
    expect(JSON.parse(socket.sent.at(-1)!)).toEqual({ user_audio_chunk: arrayBufferToBase64(pcm) });
    transport.sendText('late answer');
    expect(JSON.parse(socket.sent.at(-1)!)).toEqual({ type: 'user_message', text: 'late answer' });
    transport.answerDelegation('call_1', 'Two meetings.', 'now');
    expect(JSON.parse(socket.sent.at(-1)!)).toEqual({
      type: 'client_tool_result',
      tool_call_id: 'call_1',
      result: 'Two meetings.',
      is_error: false,
    });
    transport.answerDelegation('call_2', 'Two meetings.', 'now', 'LIA said this warmly.');
    const last = JSON.parse(socket.sent.at(-1)!);
    expect(JSON.parse(last.result)).toEqual({
      result: 'Two meetings.',
      tone: 'LIA said this warmly.',
    });
    // Nothing to tell the provider about the microphone; the close is a plain 1000.
    const before = socket.sent.length;
    transport.setInputActive(false);
    expect(socket.sent).toHaveLength(before);
    await transport.close();
    expect(socket.readyState).toBe(FakeWebSocket.CLOSED);
    expect(transport.isOpen).toBe(false);
  });

  it('close() waits for the close handshake, so /end is posted once the vendor can state the bill', async () => {
    // Measured 2026-09-20 on the real API: the conversation reads
    // `in-progress` with no cost while the close frame lands, and the bill
    // is stated 0.3 s after the handshake — two sessions showed nothing.
    const { transport, socket, ev } = await connected();
    // A real socket fires `close` LATER: the fake defers it to the test.
    socket.close = () => {
      socket.readyState = FakeWebSocket.CLOSING;
    };
    let resolved = false;
    const closing = transport.close().then(() => {
      resolved = true;
    });
    await Promise.resolve();
    expect(socket.readyState).toBe(FakeWebSocket.CLOSING);
    expect(resolved).toBe(false);
    socket.readyState = FakeWebSocket.CLOSED;
    socket.onclose?.({ code: 1000, reason: '' });
    await closing;
    expect(resolved).toBe(true);
    // The provider's close of a session the person ended is still reported
    // (the controller has moved on: a stale generation ignores it).
    expect(ev.onClosed).toHaveBeenCalledWith(1000, '');
  });

  it('close() gives up on a provider that never answers the close, after a bound', async () => {
    vi.useFakeTimers();
    try {
      const { transport, socket } = await connected();
      socket.close = () => {
        socket.readyState = FakeWebSocket.CLOSING;
      };
      let resolved = false;
      const closing = transport.close().then(() => {
        resolved = true;
      });
      await vi.advanceTimersByTimeAsync(ELEVENLABS_CLOSE_WAIT_MS - 1);
      expect(resolved).toBe(false);
      await vi.advanceTimersByTimeAsync(1);
      await closing;
      expect(resolved).toBe(true);
      expect(transport.isOpen).toBe(false);
    } finally {
      vi.useRealTimers();
    }
  });

  it('reports a provider error and a malformed frame without throwing', async () => {
    const { socket, ev } = await connected();
    socket.emit({ type: 'error', message: 'override not allowed', code: 1008 });
    expect(ev.onError).toHaveBeenCalledWith(new Error('override not allowed'));
    socket.onmessage?.({ data: 'not json' });
    expect(ev.onError).toHaveBeenCalledTimes(2);
  });

  it('rejects the connect once on a close before the metadata, and reports the close', async () => {
    const transport = new ElevenLabsLiveTransport();
    const ev = events();
    const pending = transport.connect(options(), ev);
    const socket = FakeWebSocket.instances[0];
    socket.open();
    socket.onerror?.();
    socket.close(1008, 'invalid signature');
    await expect(pending).rejects.toThrow('live_socket_closed_1008: invalid signature');
    // Not a provider close of an open session: the connect failed, and says so.
    expect(ev.onClosed).not.toHaveBeenCalled();
    expect(ev.onError).toHaveBeenCalledTimes(1);
    expect(ev.onReady).not.toHaveBeenCalled();
  });
});
