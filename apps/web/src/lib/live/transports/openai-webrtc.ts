/**
 * GPT-Live over WebRTC (ADR-299, wave 2 spec A9 and A11).
 *
 * The browser holds the peer connection and the audio tracks; the SDP offer
 * is exchanged by OUR API on the person's key (`POST /live/sessions/{id}/offer`,
 * handed in as `exchangeOffer` — no ephemeral token exists for GPT-Live,
 * documented). Events travel on the `oai-events` data channel, created BEFORE
 * the offer as the reference asks. What the wire offers and does not:
 *
 *  - the delegation is the model's own act: `session.delegation.created`
 *    carries an id and an `offset_ms`, never the request — the request is
 *    COMPOSED from the input transcript (`RequestComposer`), after a short
 *    grace for the fragments still in flight;
 *  - a result goes back as `session.commentary.append` (spoken) or
 *    `session.thinking.append` (silent), each append under the documented
 *    500-token bound, so a long answer is split into several appends;
 *  - no speaking, turn or interruption event exists: the assistant's
 *    transcript deltas ARE its speech, so a quiet transcript ends the
 *    utterance (`onSpeakingChange(false)` + `onTurnComplete`), and a person's
 *    words while it speaks are an interruption;
 *  - the microphone is told with `session.input_audio.mute` / `unmute`;
 *  - no resumption (a fork is a new session): a dropped connection is
 *    reported closed and the controller ends the session;
 *  - `session.usage.updated` (the session's seconds, the context window's
 *    ratio) feeds the banner's indicative meter and nothing else: the
 *    seconds are the person's own, counted in the browser, recorded nowhere
 *    (owner rule amended 2026-09-19: a live display is not an accounting).
 */
import type { LiveTransport } from '../transport';
import { openaiUsageReport } from '../meter';
import { RequestComposer } from '../request-composer';
import { charTokenCost, estimateTokens } from '../delegation';
import type {
  LiveConnectOptions,
  LiveDelivery,
  LiveTransportAudio,
  LiveTransportEvents,
} from '../types';

/** Native ownership: the tracks carry the audio; the rates are the WebRTC defaults (Opus, 48 kHz). */
export const OPENAI_LIVE_AUDIO: LiveTransportAudio = {
  ownership: 'native',
  inputRate: 48000,
  outputRate: 48000,
  chunkMs: 20,
};

export const OPENAI_EVENTS_CHANNEL = 'oai-events';
/** The documented bound of one `*.append` (tokens); our estimate is rough, hence the margin. */
export const OPENAI_LIVE_APPEND_MAX_TOKENS = 500;
const APPEND_SAFETY = 0.8;
/** Fragments of the request may still be in flight when the delegation event lands. */
export const OPENAI_COMPOSE_GRACE_MS = 400;
/** The assistant's transcript quiet for this long = its utterance ended. */
export const OPENAI_SPEAKING_QUIET_MS = 1500;
/** How long the offer waits for ICE gathering to complete (the reference's own bound). */
export const OPENAI_ICE_GATHERING_TIMEOUT_MS = 10_000;
/** How long `close()` waits for `session.closed` before tearing the connection down. */
export const OPENAI_CLOSE_WAIT_MS = 3000;
/** How long an open channel may stay silent before `session.started` (measured 2026-09-19: 113 ms after open). */
export const OPENAI_STARTED_TIMEOUT_MS = 10_000;

type Json = Record<string, unknown>;

function asRecord(value: unknown): Json | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Json)
    : null;
}

function numberOf(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

/** `text` cut into appends the provider accepts, at word boundaries when possible. */
export function splitForAppend(
  text: string,
  maxTokens: number = OPENAI_LIVE_APPEND_MAX_TOKENS
): string[] {
  const budget = Math.max(1, Math.floor(maxTokens * APPEND_SAFETY));
  const parts: string[] = [];
  let rest = text.trim();
  while (rest && estimateTokens(rest) > budget) {
    let cut = 0;
    let tokens = 0;
    for (const char of rest) {
      const cost = charTokenCost(char);
      if (tokens + cost > budget) break;
      tokens += cost;
      cut += char.length;
    }
    const space = rest.lastIndexOf(' ', cut);
    const at = space > 0 ? space : cut;
    parts.push(rest.slice(0, at).trim());
    rest = rest.slice(at).trim();
  }
  if (rest) parts.push(rest);
  return parts;
}

/** Wait for the peer connection's ICE gathering, bounded (the reference's own pattern). */
function waitForIceGathering(pc: RTCPeerConnection, timeoutMs: number): Promise<void> {
  if (pc.iceGatheringState === 'complete') return Promise.resolve();
  return new Promise(resolve => {
    const timer = setTimeout(done, timeoutMs);
    function done() {
      clearTimeout(timer);
      pc.removeEventListener('icegatheringstatechange', check);
      resolve();
    }
    function check() {
      if (pc.iceGatheringState === 'complete') done();
    }
    pc.addEventListener('icegatheringstatechange', check);
  });
}

export class OpenAiLiveTransport implements LiveTransport {
  readonly audio = OPENAI_LIVE_AUDIO;
  private pc: RTCPeerConnection | null = null;
  private channel: RTCDataChannel | null = null;
  private events: LiveTransportEvents = {};
  private remoteAudio: HTMLAudioElement | null = null;
  private readonly composer = new RequestComposer();
  private lastDelegationId: string | null = null;
  private speaking = false;
  private speakingTimer: ReturnType<typeof setTimeout> | null = null;
  private closedResolvers: Array<() => void> = [];
  private startedResolver: (() => void) | null = null;
  private eventSeq = 0;

  get isOpen(): boolean {
    return this.channel?.readyState === 'open';
  }

  async connect(options: LiveConnectOptions, events: LiveTransportEvents): Promise<void> {
    this.events = events;
    const Peer = globalThis.RTCPeerConnection;
    if (typeof Peer !== 'function') throw new Error('unsupported_browser');
    const exchange = options.exchangeOffer;
    if (!exchange) throw new Error('live_offer_exchange_missing');
    const pc = new Peer();
    this.pc = pc;
    pc.ontrack = event => this.attachRemote(event.streams[0]);
    pc.onconnectionstatechange = () => {
      if (this.pc !== pc) return;
      if (pc.connectionState === 'failed' || pc.connectionState === 'closed') {
        this.teardown();
        this.events.onClosed?.(1006, pc.connectionState);
      }
    };
    for (const track of options.microphone?.getAudioTracks() ?? []) {
      pc.addTrack(track, options.microphone as MediaStream);
    }
    const started = new Promise<void>(resolve => {
      this.startedResolver = resolve;
    });
    const ready = this.openChannel(pc);
    try {
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      await waitForIceGathering(pc, OPENAI_ICE_GATHERING_TIMEOUT_MS);
      const sdp = pc.localDescription?.sdp ?? offer.sdp ?? '';
      const answer = await exchange(options.credential, sdp);
      await pc.setRemoteDescription({ type: 'answer', sdp: answer });
      await ready;
    } catch (error) {
      // A refused exchange (a burnt nonce, a provider refusal) leaves no
      // half-open peer connection holding the microphone track.
      this.teardown();
      throw error;
    }
    // Measured 2026-09-19 in a real Chromium: `session.started` follows the
    // channel's open on the channel itself (undocumented for WebRTC) — the
    // session is open when the provider SAYS so, bounded.
    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(
        () => reject(new Error('live_session_not_started')),
        OPENAI_STARTED_TIMEOUT_MS
      );
      void started.then(() => {
        clearTimeout(timer);
        resolve();
      });
    });
    this.events.onReady?.();
  }

  /** The events channel, created before the offer; resolves once open, rejects on a close before that. */
  private openChannel(pc: RTCPeerConnection): Promise<void> {
    const channel = pc.createDataChannel(OPENAI_EVENTS_CHANNEL);
    this.channel = channel;
    return new Promise((resolve, reject) => {
      let settled = false;
      channel.onopen = () => {
        settled = true;
        resolve();
      };
      channel.onclose = () => {
        if (!settled) {
          settled = true;
          reject(new Error('live_channel_closed'));
        }
        if (this.channel === channel) this.onChannelClosed();
      };
      channel.onerror = () => {
        const error = new Error('live_channel_error');
        if (!settled) {
          settled = true;
          reject(error);
        }
        this.events.onError?.(error);
      };
      channel.onmessage = event => this.receive(String(event.data));
    });
  }

  private attachRemote(stream: MediaStream | undefined): void {
    if (!stream || typeof Audio !== 'function') return;
    const element = new Audio();
    element.autoplay = true;
    element.srcObject = stream;
    void element.play().catch(() => undefined);
    this.remoteAudio = element;
  }

  private receive(raw: string): void {
    let event: Json | null;
    try {
      event = asRecord(JSON.parse(raw));
    } catch (error) {
      this.events.onError?.(error instanceof Error ? error : new Error('live_bad_frame'));
      return;
    }
    if (!event) return;
    const kind = String(event.type ?? '');
    if (kind === 'session.started') this.startedResolver?.();
    else if (kind === 'session.input_transcript.delta') this.onInputDelta(event);
    else if (kind === 'session.output_transcript.delta') this.onOutputDelta(event);
    else if (kind === 'session.delegation.created') this.onDelegationCreated(event);
    else if (kind === 'session.closed') this.onSessionClosed(event);
    else if (kind === 'session.usage.updated') this.onUsage(event);
    else if (kind === 'error') this.onProviderError(event);
  }

  private onUsage(event: Json): void {
    const report = openaiUsageReport(event);
    if (report) this.events.onUsage?.(report);
  }

  private onInputDelta(event: Json): void {
    const text = typeof event.delta === 'string' ? event.delta : '';
    if (!text) return;
    this.composer.record(text, numberOf(event.start_ms), numberOf(event.end_ms));
    // Words while the assistant speaks: the person interrupted it.
    if (this.speaking) this.events.onInterrupted?.();
    this.events.onTranscript?.('user', text);
  }

  private onOutputDelta(event: Json): void {
    const text = typeof event.delta === 'string' ? event.delta : '';
    if (!text) return;
    this.events.onTranscript?.('assistant', text);
    this.pulseSpeaking();
  }

  /** The transcript IS the speech: it opens the utterance, its quiet closes it. */
  private pulseSpeaking(): void {
    if (!this.speaking) {
      this.speaking = true;
      this.events.onSpeakingChange?.(true);
    }
    if (this.speakingTimer) clearTimeout(this.speakingTimer);
    this.speakingTimer = setTimeout(() => this.endSpeaking(), OPENAI_SPEAKING_QUIET_MS);
  }

  private endSpeaking(): void {
    this.speakingTimer = null;
    if (!this.speaking) return;
    this.speaking = false;
    this.events.onSpeakingChange?.(false);
    this.events.onTurnComplete?.();
  }

  private onDelegationCreated(event: Json): void {
    const delegation = asRecord(event.delegation);
    const id = String(delegation?.id ?? '');
    if (!id) return;
    const offsetMs = numberOf(event.offset_ms);
    this.lastDelegationId = id;
    // A short grace: the fragments of the request may still be in flight.
    setTimeout(() => {
      if (this.channel === null) return;
      const request = this.composer.compose(offsetMs || Number.MAX_SAFE_INTEGER);
      this.events.onDelegation?.([{ id, request }]);
    }, OPENAI_COMPOSE_GRACE_MS);
  }

  private onSessionClosed(event: Json): void {
    const reason = String(event.reason ?? '');
    const resolvers = this.closedResolvers;
    this.closedResolvers = [];
    for (const resolve of resolvers) resolve();
    this.teardown();
    this.events.onClosed?.(1000, reason);
  }

  private onProviderError(event: Json): void {
    const error = asRecord(event.error);
    const code = String(error?.code ?? 'error');
    const message = String(error?.message ?? '');
    this.events.onError?.(new Error(`${code}: ${message}`));
  }

  private onChannelClosed(): void {
    // A channel closing without `session.closed`: the connection dropped.
    if (this.pc === null) return;
    this.teardown();
    this.events.onClosed?.(1006, 'channel_closed');
  }

  private send(event: Json): void {
    const channel = this.channel;
    if (!channel || channel.readyState !== 'open') return;
    this.eventSeq += 1;
    channel.send(JSON.stringify({ event_id: `lia_${this.eventSeq}`, ...event }));
  }

  sendAudio(_pcm16: ArrayBuffer): void {
    // Native ownership: the microphone track carries the audio.
  }

  /** A late answer is spoken as commentary on the delegation it answers. */
  sendText(text: string): void {
    this.append('session.commentary.append', text, this.lastDelegationId);
  }

  answerDelegation(
    id: string,
    result: string,
    delivery: LiveDelivery,
    note: string | null = null
  ): void {
    const kind = delivery === 'silent' ? 'session.thinking.append' : 'session.commentary.append';
    // This wire has no field for a note: it is a SILENT append before the
    // spoken one, on the same delegation — the mandate says what it is.
    if (note && delivery !== 'silent') this.append('session.thinking.append', note, id);
    this.append(kind, result, id);
  }

  private append(kind: string, content: string, delegationId: string | null): void {
    for (const part of splitForAppend(content)) {
      this.send({ type: kind, delegation_id: delegationId, content: part });
    }
  }

  setInputActive(on: boolean): void {
    this.send({ type: on ? 'session.input_audio.unmute' : 'session.input_audio.mute' });
  }

  async close(): Promise<void> {
    if (this.isOpen) {
      const closed = new Promise<void>(resolve => this.closedResolvers.push(resolve));
      this.send({ type: 'session.close' });
      await Promise.race([
        closed,
        new Promise<void>(resolve => setTimeout(resolve, OPENAI_CLOSE_WAIT_MS)),
      ]);
    }
    this.teardown();
  }

  private teardown(): void {
    if (this.speakingTimer) clearTimeout(this.speakingTimer);
    this.speakingTimer = null;
    this.speaking = false;
    this.startedResolver = null;
    const channel = this.channel;
    this.channel = null;
    if (channel) {
      channel.onmessage = null;
      channel.onclose = null;
      channel.onerror = null;
      if (channel.readyState === 'open' || channel.readyState === 'connecting') channel.close();
    }
    const pc = this.pc;
    this.pc = null;
    if (pc) {
      pc.ontrack = null;
      pc.onconnectionstatechange = null;
      pc.close();
    }
    if (this.remoteAudio) {
      this.remoteAudio.pause();
      this.remoteAudio.srcObject = null;
      this.remoteAudio = null;
    }
  }
}
