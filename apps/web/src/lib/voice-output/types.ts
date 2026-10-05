/** Outputs own playback only; provider connections and borrowed tracks outlive a phrase. */
export interface DecodedAudioOutput {
  /** Hands one decoded clip to the output: resolves once ACCEPTED, not once heard. */
  play(buffer: AudioBuffer, signal: AbortSignal, onAudible: () => void): Promise<void>;
  /** No clip follows: drains what was handed over, then resolves. */
  end(): Promise<void>;
}
export interface VoiceUtterance {
  source: 'comments' | 'live';
  id: string;
}
export const VOICE_ENCODED_MAX_BYTES = 2 * 1024 * 1024;
export const AVATAR_PCM_SAMPLE_RATE = 16000;
export const AVATAR_PCM_MAX_BACKLOG_BYTES = AVATAR_PCM_SAMPLE_RATE * 2 * 5;
export const AVATAR_PCM_PACKET_BYTES = 6000;
/**
 * How far ahead of the remote playout a decoded clip may be pushed, in seconds.
 * The provider buffers what it receives (its reference client forwards whole
 * TTS chunks unpaced); a packet held back to the sample clock left it ~85 ms
 * of lead and every jitter starved it into silence frames. Four seconds absorb
 * a throttled background tab and keep an interruption's SKIP cheap.
 */
export const AVATAR_PCM_LEAD_MAX_SECONDS = 4;
/** Synchronous Live bursts may queue a response locally, never unbounded audio. */
export const LIVE_PCM_MAX_QUEUED_SECONDS = 30;
/**
 * A transport refusing every packet this long is dead for this phrase. The
 * socket's own close/error events are the primary signal; this is the net. A
 * slow uplink draining the backlog bound at 1 Mbit/s needs ~1.3 s, which must
 * not read as a stall.
 */
export const AVATAR_PCM_SEND_STALL_MS = 4000;
/** Live PCM: no chunk for this long means the provider paused — the held partial packet leaves. */
export const LIVE_PCM_TAIL_HOLD_MS = 150;
/**
 * Live PCM: no chunk for this long, output drained, means the production is
 * over. ElevenLabs over WebSocket emits no audio EOF at all (`agent_response`
 * PRECEDES its audio chunks), so the drain is the only boundary every
 * transport shares; a provider's own EOF only shortens the wait.
 */
export const LIVE_PCM_PRODUCTION_HOLD_MS = 700;
/** Comments: with no `voice_complete`, an empty queue ends the avatar phrase after this hold. */
export const VOICE_RUN_END_HOLD_MS = 1500;
