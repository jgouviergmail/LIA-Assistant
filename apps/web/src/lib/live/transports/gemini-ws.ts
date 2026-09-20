/**
 * Gemini Live API over a raw WebSocket (ADR-299, spec A2 and A12).
 *
 * The protocol is the documented one and nothing more: one `setup` frame
 * first, then `realtimeInput` / `clientContent` / `toolResponse` out, and the
 * server's `serverContent` / `toolCall` / `toolCallCancellation` / `goAway` /
 * `sessionResumptionUpdate` in. No SDK: the messages are short JSON, and a
 * second provider will not share them anyway.
 *
 * Measured 2026-09-18: an ephemeral token is accepted ONLY by the
 * `…Constrained` method with the token in the `access_token` query — the
 * plain method answers 1008 and a `key=` query answers 1007. And the
 * provider's frames are BINARY: under the browser's default `binaryType` they
 * arrive as `Blob`, which a text reader turns into `"[object Blob]"` — no
 * `setupComplete` ever seen, « Connecting… » for ever (Docker dev, a real
 * Chromium). The socket asks for `ArrayBuffer`s and decodes them itself,
 * synchronously, so the frames keep their order.
 *
 * Input activity follows the Live API best practices: the detection is
 * always automatic (a live session has no held button), and a paused
 * microphone sends `audioStreamEnd` so the server flushes what it cached.
 */
import { arrayBufferToBase64, base64ToArrayBuffer } from '../base64';
import { geminiUsageReport } from '../meter';
import { closeWords } from '../session-machine';
import type { LiveTransport } from '../transport';
import type {
  LiveConnectOptions,
  LiveDelegation,
  LiveDelivery,
  LiveInteractionStatus,
  LiveTransportAudio,
  LiveTransportEvents,
} from '../types';

export const GEMINI_LIVE_WS_URL =
  'wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContentConstrained';

/** 16 kHz in, 24 kHz out, 40 ms chunks — the documented rates and the top of the 20-40 ms range. */
export const GEMINI_LIVE_AUDIO: LiveTransportAudio = {
  ownership: 'pcm',
  inputRate: 16000,
  outputRate: 24000,
  chunkMs: 40,
};

const INPUT_MIME = `audio/pcm;rate=${GEMINI_LIVE_AUDIO.inputRate}`;

/** The provider's word for each delivery mode of a function response. */
const SCHEDULING: Record<LiveDelivery, 'INTERRUPT' | 'WHEN_IDLE' | 'SILENT'> = {
  now: 'INTERRUPT',
  when_idle: 'WHEN_IDLE',
  silent: 'SILENT',
};

type Json = Record<string, unknown>;

const FRAME_DECODER = new TextDecoder();

/** The text of a frame, whether the socket handed a string or bytes. */
function frameText(data: unknown): string {
  if (typeof data === 'string') return data;
  if (data instanceof ArrayBuffer) return FRAME_DECODER.decode(data);
  if (ArrayBuffer.isView(data)) return FRAME_DECODER.decode(data);
  throw new Error('live_bad_frame');
}

function asRecord(value: unknown): Json | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Json)
    : null;
}

/** The base64 audio of every inline part of a model turn, in order. */
function audioParts(content: Json): string[] {
  const modelTurn = asRecord(content.modelTurn);
  const parts = modelTurn && Array.isArray(modelTurn.parts) ? modelTurn.parts : [];
  const out: string[] = [];
  for (const raw of parts) {
    const inline = asRecord(asRecord(raw)?.inlineData);
    if (inline && typeof inline.data === 'string') out.push(inline.data);
  }
  return out;
}

/** The text of a transcription fragment, or null when the frame carries none. */
function transcriptText(raw: unknown): string | null {
  const fragment = asRecord(raw);
  return fragment && typeof fragment.text === 'string' && fragment.text ? fragment.text : null;
}

/**
 * `interactionStatus` as the reference documents it (an object) or as the
 * cookbook reads it (a string); anything else is not a status.
 */
function interactionStatus(raw: unknown): LiveInteractionStatus | null {
  if (raw === undefined || raw === null) return null;
  const record = asRecord(raw);
  const word = typeof raw === 'string' ? raw : (record?.status ?? record?.state);
  if (word === 'IN_PROGRESS') return 'in_progress';
  if (word === 'IDLE') return 'idle';
  return null;
}

/**
 * The delegations of a `toolCall` frame; every call's NAME is remembered so
 * the response can carry it back (the seam speaks ids, the wire wants names).
 * The call itself travels too: a DIRECT session reads the tool's name and
 * arguments where a delegated one reads the request (ADR-300 wave 4).
 */
function delegationsOf(rawCalls: unknown[], names: Map<string, string>): LiveDelegation[] {
  const delegations: LiveDelegation[] = [];
  for (const raw of rawCalls) {
    const call = asRecord(raw);
    if (!call) continue;
    const id = String(call.id ?? '');
    const name = String(call.name ?? '');
    names.set(id, name);
    const args = asRecord(call.args) ?? {};
    const request = args.request;
    delegations.push({
      id,
      request: typeof request === 'string' ? request : null,
      call: { name, args },
    });
  }
  return delegations;
}

/** `"12s"` / `"1.5s"` → milliseconds; anything unreadable → 0. */
function durationToMs(raw: unknown): number {
  if (typeof raw !== 'string') return 0;
  const seconds = Number.parseFloat(raw.replace(/s$/, ''));
  return Number.isFinite(seconds) ? Math.max(0, Math.round(seconds * 1000)) : 0;
}

export class GeminiLiveTransport implements LiveTransport {
  readonly audio = GEMINI_LIVE_AUDIO;
  private socket: WebSocket | null = null;
  private events: LiveTransportEvents = {};
  /** The function name of each pending call: the response must carry it back. */
  private readonly callNames = new Map<string, string>();
  private schedulingAccepted = true;

  get isOpen(): boolean {
    return this.socket?.readyState === WebSocket.OPEN;
  }

  connect(options: LiveConnectOptions, events: LiveTransportEvents): Promise<void> {
    this.events = events;
    this.schedulingAccepted = options.capabilities.delivery_scheduling;
    const setup: Json = { ...options.setup };
    if (options.resumptionHandle) {
      setup.sessionResumption = { handle: options.resumptionHandle };
    }
    return new Promise((resolve, reject) => {
      let settled = false;
      const socket = new WebSocket(
        `${GEMINI_LIVE_WS_URL}?access_token=${encodeURIComponent(options.credential)}`
      );
      // Bytes, not Blobs: a Blob is read asynchronously and its frames could
      // be handled out of order; an ArrayBuffer is decoded on the spot.
      socket.binaryType = 'arraybuffer';
      this.socket = socket;
      socket.onopen = () => socket.send(JSON.stringify({ setup }));
      socket.onerror = () => {
        // An error before the setup is ALWAYS followed by a close carrying
        // the code (1006 for a refused handshake): the connect settles there,
        // so the API's log names the code and the reason, never a bare word.
        this.events.onError?.(new Error('live_socket_error'));
      };
      socket.onclose = event => {
        if (this.socket === socket) this.socket = null;
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
          message = asRecord(JSON.parse(frameText(event.data)));
        } catch (error) {
          this.events.onError?.(error instanceof Error ? error : new Error('live_bad_frame'));
          return;
        }
        if (!message) return;
        if ('setupComplete' in message && !settled) {
          settled = true;
          this.events.onReady?.();
          resolve();
        }
        this.dispatch(message);
      };
    });
  }

  private dispatch(message: Json): void {
    const content = asRecord(message.serverContent);
    if (content) {
      this.dispatchMedia(content);
      this.dispatchSignals(content);
    }
    this.dispatchDelegations(message);
    this.dispatchSession(message);
  }

  /** Audio and transcripts of a server content frame. */
  private dispatchMedia(content: Json): void {
    for (const data of audioParts(content)) this.events.onAudio?.(base64ToArrayBuffer(data));
    const input = transcriptText(content.inputTranscription);
    if (input) this.events.onTranscript?.('user', input);
    const output = transcriptText(content.outputTranscription);
    if (output) this.events.onTranscript?.('assistant', output);
  }

  /** The turn, generation and interaction signals of a server content frame. */
  private dispatchSignals(content: Json): void {
    if (content.interrupted === true) this.events.onInterrupted?.();
    if (content.generationComplete === true) this.events.onGenerationComplete?.();
    if (content.turnComplete === true) this.events.onTurnComplete?.();
    const status = interactionStatus(content.interactionStatus);
    if (status) this.events.onInteractionStatus?.(status);
  }

  /** Function calls become delegations; cancellations forget their names. */
  private dispatchDelegations(message: Json): void {
    const toolCall = asRecord(message.toolCall);
    if (toolCall && Array.isArray(toolCall.functionCalls)) {
      const delegations = delegationsOf(toolCall.functionCalls, this.callNames);
      if (delegations.length > 0) this.events.onDelegation?.(delegations);
    }
    const cancellation = asRecord(message.toolCallCancellation);
    if (cancellation && Array.isArray(cancellation.ids)) {
      const ids = cancellation.ids.map(String);
      for (const id of ids) this.callNames.delete(id);
      this.events.onDelegationCancelled?.(ids);
    }
  }

  /** goAway, the resumption handle and the turn's usage. */
  private dispatchSession(message: Json): void {
    const goAway = asRecord(message.goAway);
    if (goAway) this.events.onGoAway?.(durationToMs(goAway.timeLeft));
    const usage = geminiUsageReport(message.usageMetadata);
    if (usage) this.events.onUsage?.(usage);
    const resumption = asRecord(message.sessionResumptionUpdate);
    if (resumption && typeof resumption.newHandle === 'string' && resumption.newHandle) {
      this.events.onResumption?.(resumption.newHandle, resumption.resumable === true);
    }
  }

  private send(payload: Json): void {
    if (!this.socket || !this.isOpen) return;
    this.socket.send(JSON.stringify(payload));
  }

  sendAudio(pcm16: ArrayBuffer): void {
    this.send({
      realtimeInput: { audio: { mimeType: INPUT_MIME, data: arrayBufferToBase64(pcm16) } },
    });
  }

  sendText(text: string): void {
    this.send({
      clientContent: { turns: [{ role: 'user', parts: [{ text }] }], turnComplete: true },
    });
  }

  answerDelegation(
    id: string,
    result: string,
    delivery: LiveDelivery,
    note: string | null = null
  ): void {
    const name = this.callNames.get(id) ?? '';
    this.callNames.delete(id);
    // The note rides the function response as its own field: the mandate
    // names it (`tone`) and says never to read it aloud.
    const response: Json = { id, name, response: note ? { result, tone: note } : { result } };
    // Extended Thinking refuses a scheduling (documented): the capability says.
    if (this.schedulingAccepted) response.scheduling = SCHEDULING[delivery];
    this.send({ toolResponse: { functionResponses: [response] } });
  }

  setInputActive(on: boolean): void {
    // A paused microphone flushes the server's cached audio; an active one says nothing.
    if (!on) this.send({ realtimeInput: { audioStreamEnd: true } });
  }

  async close(): Promise<void> {
    const socket = this.socket;
    this.socket = null;
    this.callNames.clear();
    if (socket && socket.readyState !== WebSocket.CLOSED) socket.close(1000, '');
  }
}
