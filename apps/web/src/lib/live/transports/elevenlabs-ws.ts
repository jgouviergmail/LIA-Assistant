/**
 * ElevenLabs Agents over a raw WebSocket (ADR-300 wave 4).
 *
 * The wire is the one the official `@elevenlabs/client` 1.25.0 speaks, read
 * from its source and measured on a real agent (2026-09-19, a real Chromium
 * on the built bundle): the credential is a
 * SIGNED URL the API minted on the person's key, opened on the `convai`
 * subprotocol; the first frame out is the initiation the API rendered (LIA's
 * prompt over the agent's), the first frame in is the conversation's
 * metadata, which names the agent's OUTPUT audio format — the player follows
 * it, the microphone captures at the 16 kHz the API's probe required.
 *
 * Frames out: `user_audio_chunk` (base64 PCM), `client_tool_result`, `pong`,
 * `user_message` (a text turn). Frames in: `audio`, `user_transcript`,
 * `agent_response` (the agent's WHOLE reply, so it closes the turn),
 * `interruption` (drop every audio event up to its id), `client_tool_call`,
 * `ping`, `error`. No resumption, no usage report (a minute-billed tariff
 * runs on the clock), no delivery scheduling: the seam's capabilities say so.
 */
import { arrayBufferToBase64, base64ToArrayBuffer } from '../base64';
import { closeWords } from '../session-machine';
import type { LiveTransport } from '../transport';
import type {
  LiveConnectOptions,
  LiveDelegation,
  LiveDelivery,
  LiveTransportAudio,
  LiveTransportEvents,
} from '../types';

/** The subprotocol the provider negotiates (the SDK's `MAIN_PROTOCOL`). */
export const ELEVENLABS_WS_SUBPROTOCOL = 'convai';
/** The metadata frame that opens a conversation. */
export const ELEVENLABS_METADATA_TYPE = 'conversation_initiation_metadata';
/**
 * How long `close()` waits for the provider's close event before moving on.
 * The vendor states the conversation's bill once the close HANDSHAKE is done
 * (measured 2026-09-20: `in-progress` and no cost while the close frame
 * lands, the bill 0.3 s after the handshake) — `/end` posted before it read
 * no bill, and two sessions in a row showed the person nothing.
 */
export const ELEVENLABS_CLOSE_WAIT_MS = 2000;

/** 16 kHz in (the probe required it), the agent's own rate out (read from the metadata). */
export const ELEVENLABS_LIVE_AUDIO: LiveTransportAudio = {
  ownership: 'pcm',
  inputRate: 16000,
  outputRate: 16000,
  chunkMs: 40,
};

type Json = Record<string, unknown>;

function asRecord(value: unknown): Json | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Json)
    : null;
}

/** The sample rate a `pcm_<rate>` format names, or null for anything else. */
export function outputRateOf(format: unknown): number | null {
  if (typeof format !== 'string' || !format.startsWith('pcm_')) return null;
  const rate = Number.parseInt(format.slice('pcm_'.length), 10);
  return Number.isFinite(rate) && rate > 0 ? rate : null;
}

/** A non-empty string field of an event record, or null. */
function textOf(event: unknown, field: string): string | null {
  const value = asRecord(event)?.[field];
  return typeof value === 'string' && value ? value : null;
}

/** A client tool call as a delegation: the call itself travels for a direct session. */
function delegationOf(call: Json): LiveDelegation {
  const args = asRecord(call.parameters) ?? {};
  const request = args.request;
  return {
    id: String(call.tool_call_id ?? ''),
    request: typeof request === 'string' ? request : null,
    call: { name: String(call.tool_name ?? ''), args },
  };
}

export class ElevenLabsLiveTransport implements LiveTransport {
  private currentAudio: LiveTransportAudio = ELEVENLABS_LIVE_AUDIO;
  private socket: WebSocket | null = null;
  private events: LiveTransportEvents = {};
  /** Whoever awaits `close()`: settled by the socket's own close event. */
  private closedResolvers: Array<() => void> = [];
  /** Audio events up to this id were interrupted: dropped rather than played. */
  private interruptedUpTo = -1;

  get audio(): LiveTransportAudio {
    return this.currentAudio;
  }

  get isOpen(): boolean {
    return this.socket?.readyState === WebSocket.OPEN;
  }

  connect(options: LiveConnectOptions, events: LiveTransportEvents): Promise<void> {
    this.events = events;
    this.interruptedUpTo = -1;
    return new Promise((resolve, reject) => {
      let settled = false;
      const socket = new WebSocket(options.credential, [ELEVENLABS_WS_SUBPROTOCOL]);
      socket.binaryType = 'arraybuffer';
      this.socket = socket;
      socket.onopen = () => socket.send(JSON.stringify(options.setup));
      socket.onerror = () => {
        // An error before the setup is ALWAYS followed by a close carrying
        // the code (1006 for a refused handshake): the connect settles there,
        // so the API's log names the code and the reason, never a bare word.
        this.events.onError?.(new Error('live_socket_error'));
      };
      socket.onclose = event => {
        if (this.socket === socket) this.socket = null;
        this.settleClosed();
        if (!settled) {
          // A close BEFORE the setup is the connect's own failure: the
          // rejection carries the code and reason, and `onClosed` is not
          // raised — raised, the session read « closed by the provider »
          // about a socket that never opened (measured 2026-09-19).
          settled = true;
          reject(new Error(closeWords(event.code, event.reason)));
          return;
        }
        this.events.onClosed?.(event.code, event.reason);
      };
      socket.onmessage = event => {
        let message: Json | null;
        try {
          const raw = event.data;
          const text = typeof raw === 'string' ? raw : new TextDecoder().decode(raw);
          message = asRecord(JSON.parse(text));
        } catch (error) {
          this.events.onError?.(error instanceof Error ? error : new Error('live_bad_frame'));
          return;
        }
        if (!message) return;
        if (message.type === ELEVENLABS_METADATA_TYPE && !settled) {
          settled = true;
          this.readMetadata(message);
          this.events.onReady?.();
          resolve();
          return;
        }
        this.dispatch(message);
      };
    });
  }

  /**
   * The agent's output rate, from the conversation's metadata — and the
   * conversation's own id, which the end hands the API so the vendor's bill
   * is read under it (shown, never recorded).
   */
  private readMetadata(message: Json): void {
    const metadata = asRecord(message.conversation_initiation_metadata_event);
    const rate = outputRateOf(metadata?.agent_output_audio_format);
    if (rate !== null) this.currentAudio = { ...ELEVENLABS_LIVE_AUDIO, outputRate: rate };
    const conversationId = metadata?.conversation_id;
    if (typeof conversationId === 'string' && conversationId) {
      this.events.onProviderConversation?.(conversationId);
    }
  }

  /** One handler per frame type the SDK reads; anything else is not for us. */
  private readonly handlers: Record<string, (message: Json) => void> = {
    audio: message => this.dispatchAudio(message),
    user_transcript: message => {
      const text = textOf(message.user_transcription_event, 'user_transcript');
      if (text) this.events.onTranscript?.('user', text);
    },
    agent_response: message => {
      // The agent's WHOLE reply: the text of the turn, and its end.
      const text = textOf(message.agent_response_event, 'agent_response');
      if (text) this.events.onTranscript?.('assistant', text);
      this.events.onTurnComplete?.();
    },
    interruption: message => {
      const id = Number(asRecord(message.interruption_event)?.event_id);
      if (Number.isFinite(id)) this.interruptedUpTo = Math.max(this.interruptedUpTo, id);
      this.events.onInterrupted?.();
    },
    client_tool_call: message => {
      const call = asRecord(message.client_tool_call);
      if (call) this.events.onDelegation?.([delegationOf(call)]);
    },
    ping: message => {
      this.send({ type: 'pong', event_id: asRecord(message.ping_event)?.event_id });
    },
    error: message => {
      const words = typeof message.message === 'string' ? message.message : 'live_provider_error';
      this.events.onError?.(new Error(words));
    },
  };

  private dispatch(message: Json): void {
    const type = message.type;
    // `hasOwn`: a frame typed `toString` must never reach the prototype's.
    if (typeof type !== 'string' || !Object.hasOwn(this.handlers, type)) return;
    this.handlers[type](message);
  }

  /** One audio event: played unless an interruption already covered its id. */
  private dispatchAudio(message: Json): void {
    const event = asRecord(message.audio_event);
    const data = event?.audio_base_64;
    if (typeof data !== 'string' || !data) return;
    const id = Number(event?.event_id);
    if (Number.isFinite(id) && id <= this.interruptedUpTo) return;
    this.events.onAudio?.(base64ToArrayBuffer(data));
  }

  private send(payload: Json): void {
    if (!this.socket || !this.isOpen) return;
    this.socket.send(JSON.stringify(payload));
  }

  sendAudio(pcm16: ArrayBuffer): void {
    this.send({ user_audio_chunk: arrayBufferToBase64(pcm16) });
  }

  sendText(text: string): void {
    this.send({ type: 'user_message', text });
  }

  answerDelegation(
    id: string,
    result: string,
    _delivery: LiveDelivery,
    note: string | null = null
  ): void {
    // The result is a string on this wire: the delivery note rides beside
    // it as a field of one JSON string the mandate names (`tone`).
    const payload = note ? JSON.stringify({ result, tone: note }) : result;
    this.send({ type: 'client_tool_result', tool_call_id: id, result: payload, is_error: false });
  }

  setInputActive(_on: boolean): void {
    // The provider detects the person's activity itself; nothing to tell it.
  }

  async close(): Promise<void> {
    const socket = this.socket;
    this.socket = null;
    if (!socket || socket.readyState === WebSocket.CLOSED) return;
    // Wait for the handshake, bounded: the vendor's bill is stated after it.
    const closed = new Promise<void>(resolve => this.closedResolvers.push(resolve));
    socket.close(1000, '');
    await Promise.race([
      closed,
      new Promise<void>(resolve => setTimeout(resolve, ELEVENLABS_CLOSE_WAIT_MS)),
    ]);
  }

  private settleClosed(): void {
    const resolvers = this.closedResolvers;
    this.closedResolvers = [];
    for (const resolve of resolvers) resolve();
  }
}
