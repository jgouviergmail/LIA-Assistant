/**
 * The voice LIA speaks with, as a level read off the sound itself (ADR-294,
 * follow-up of 2026-11-13).
 *
 * ONE door: every voice output taps its sound here — the chat's voice comments
 * (`AudioQueue`), the live session's player (`PcmStreamPlayer`), the remote
 * voice of a WebRTC session (`RoutedLivePlayer`'s own sink, on the player's
 * context) — and the face reads one level (`voiceLevel`), so a mouth opens on
 * what is heard rather than on syllables it makes up. A tap is a PARALLEL
 * branch to an analyser: the sound path is untouched, and a sound that cannot
 * be tapped still plays — the face then speaks on its own, as before.
 *
 * The level is the sound's RMS in dBFS over a short window, mapped from
 * `VOICE_FLOOR_DB` (nothing) to `VOICE_CEILING_DB` (a full voice); with several
 * voices at once, the loudest. It is read as the sound REACHES THE EAR when the face
 * SHOWS it: an analyser sees what the graph renders, which the person hears the
 * context's latency later (a few tens of milliseconds on speakers, a few hundred on
 * a wireless headset), and the face shows what it reads `VOICE_LEAD_MS` later; so a
 * tap holds that much sound and reads the latency back less that lead, never a sound
 * not rendered yet. A context that is not running feeds its analyser nothing,
 * whatever the speakers play: its tap is not heard, never read as a silence; neither
 * is a tap that has heard no sound at all, not even one too soft to open the mouth,
 * while the face listened for `VOICE_BLIND_AFTER_MS`. A voice that plays sounds
 * sooner, so that tap is blind, and the face speaks on its own rather than with its
 * mouth shut. Read on demand, on the face's own frame: nothing here runs on a clock.
 */
import { logger } from '@/lib/logger';

/**
 * Below this the mouth is shut: the soft tail of a syllable, a breath, a consonant
 * with no voice. Measured on two real voices (2026-11-13): at -45 the mouth stayed
 * open 60 % of the time and marked 2.3 syllables a second out of 3.6 to 3.9; at -35,
 * with the rig's quicker envelope, 46 % and 3.2.
 */
export const VOICE_FLOOR_DB = -35;
/** At this, a voice is at its fullest: speech rarely goes above. */
export const VOICE_CEILING_DB = -12;
/** A short window, about a frame of speech: a syllable is a few of them. */
const TAP_WINDOW = 512;
/** The furthest back a tap reads: a wireless headset, with room to spare. */
const VOICE_LATENCY_MAX_S = 0.4;
/** The most an analyser may hold (the Web Audio bound on `fftSize`). */
const TAP_HOLD_MAX = 32_768;
/**
 * How long the face takes to show what it reads (its envelope, its spring, its next
 * frame): a tap reads the sound the person will hear by then, as far as the sound is
 * already rendered. Measured on two real voices: the drawn opening followed the heard
 * sound by 45 to 60 ms without it.
 */
export const VOICE_LEAD_MS = 60;
/** Above this an analyser hears a sound, however soft: a blind one reads zeros, far below. */
const VOICE_HEARD_DB = -70;
/** A voice that plays sounds within this much listening: a tap that heard nothing is blind. */
export const VOICE_BLIND_AFTER_MS = 1500;
/** Between two reads, at most this much counts as listening: a pause between speeches does not. */
const TAP_READ_GAP_MAX_MS = 100;

/** What a tap needs of an analyser (an `AnalyserNode` is one). */
export interface AnalyserLike {
  fftSize: number;
  smoothingTimeConstant: number;
  getFloatTimeDomainData(array: Float32Array<ArrayBuffer>): void;
  disconnect(): void;
}

/**
 * What a tap needs of the node the voice leaves through (an `AudioNode` is one):
 * its context makes the analyser, and the node connects to the kind it made —
 * an `AnalyserNode` for a real node, which only connects to another node.
 */
export interface TappableNode<Analyser extends AnalyserLike = AnalyserLike> {
  readonly context: {
    readonly state: AudioContextState;
    readonly sampleRate: number;
    /** From the graph to the device (an `AudioContext` says it; another context does not). */
    readonly baseLatency?: number;
    /** From the device to the ear, as far as the browser knows it. */
    readonly outputLatency?: number;
    createAnalyser(): Analyser;
  };
  connect(destination: NoInfer<Analyser>): unknown;
  disconnect(destination: NoInfer<Analyser>): void;
}

interface Tap {
  readonly context: TappableNode['context'];
  readonly analyser: AnalyserLike;
  readonly samples: Float32Array<ArrayBuffer>;
  /** Whether the tap ever heard a sound: one that did is trusted through every silence. */
  heard: boolean;
  /** How long the face listened to it while it heard nothing. */
  silentMs: number;
  /** When it was last read, while it heard nothing. */
  readAt: number | null;
}

/** As much sound as a tap must hold to read back to the furthest ear it serves. */
function holdFor(sampleRate: number): number {
  let size = TAP_WINDOW;
  while (size < TAP_WINDOW + VOICE_LATENCY_MAX_S * sampleRate && size < TAP_HOLD_MAX) size *= 2;
  return size;
}

/**
 * How long the sound takes from the analyser to the ear, as the context says it; 0
 * when it says no number. A tap never reads further back than it holds.
 */
function latencyOf(context: Tap['context']): number {
  const latency = (context.baseLatency ?? 0) + (context.outputLatency ?? 0);
  return Number.isFinite(latency) ? latency : 0;
}

function unavailable(error: unknown): () => void {
  // The voice plays all the same; the face speaks on its own.
  logger.debug('voice_tap_unavailable', {
    errorType: error instanceof Error ? error.name : typeof error,
  });
  return () => undefined;
}

const taps = new Set<Tap>();

/**
 * Taps a voice's sound for the face. Returns its release, to call when that voice
 * stops: it disconnects the analyser alone, once, and never throws.
 */
export function tapVoice<Analyser extends AnalyserLike>(node: TappableNode<Analyser>): () => void {
  let analyser: Analyser;
  let tap: Tap;
  try {
    analyser = node.context.createAnalyser();
    analyser.fftSize = holdFor(node.context.sampleRate);
    analyser.smoothingTimeConstant = 0;
    node.connect(analyser);
    tap = {
      context: node.context,
      analyser,
      samples: new Float32Array(new ArrayBuffer(analyser.fftSize * 4)),
      heard: false,
      silentMs: 0,
      readAt: null,
    };
  } catch (error) {
    return unavailable(error);
  }
  taps.add(tap);
  let released = false;
  return () => {
    if (released) return;
    released = true;
    taps.delete(tap);
    try {
      node.disconnect(analyser);
      analyser.disconnect();
    } catch {
      // Already torn down with its context: nothing left to let go of.
    }
  };
}

/**
 * Taps a voice another sink plays (the remote stream of a WebRTC session, heard
 * through its own element) on a context its caller LENDS: one created and
 * resumed on the person's gesture, where a context made when the stream arrives
 * could stay suspended (iOS). The stream keeps playing through its element.
 */
export function tapVoiceStream<Stream, Analyser extends AnalyserLike>(
  context: { createMediaStreamSource(stream: Stream): TappableNode<Analyser> },
  stream: Stream
): () => void {
  let source: TappableNode<Analyser>;
  try {
    source = context.createMediaStreamSource(stream);
  } catch (error) {
    return unavailable(error);
  }
  return tapVoice(source);
}

/**
 * How loud, in dBFS, one tap's voice is as the person hears it when the face shows
 * it: the window rendered the context's latency ago, less `VOICE_LEAD_MS`, never a
 * sound not rendered yet. Null for an analyser that cannot be read or a reading that
 * is no number. Never a throw: it is read on the face's frame.
 */
function decibelsOf(tap: Tap): number | null {
  try {
    tap.analyser.getFloatTimeDomainData(tap.samples);
  } catch {
    // An engine without float time-domain data: this voice is not heard.
    return null;
  }
  const length = tap.samples.length;
  const ahead = Math.max(0, latencyOf(tap.context) - VOICE_LEAD_MS / 1000);
  const back = Math.min(Math.round(ahead * tap.context.sampleRate), length - TAP_WINDOW);
  let sum = 0;
  for (let index = length - back - TAP_WINDOW; index < length - back; index++)
    sum += tap.samples[index] * tap.samples[index];
  const rms = Math.sqrt(sum / TAP_WINDOW);
  return Number.isFinite(rms) ? 20 * Math.log10(Math.max(rms, 1e-7)) : null;
}

/** A voice's loudness as an opening: from silence (0) to a full voice (1). */
function levelFor(decibels: number): number {
  return Math.min(
    1,
    Math.max(0, (decibels - VOICE_FLOOR_DB) / (VOICE_CEILING_DB - VOICE_FLOOR_DB))
  );
}

/**
 * How loud the voice LIA is speaking with is right now, from 0 to 1 — the
 * loudest when several play — or `null` when no voice is heard (none tapped, none
 * on a running context, none that reads as a number, none that heard any sound in
 * `VOICE_BLIND_AFTER_MS` of listening): the face then makes up its own speech.
 * Never anything else, and never a throw: the rig reads it as it comes.
 */
export function voiceLevel(): number | null {
  let loudest: number | null = null;
  for (const tap of taps) {
    const decibels = tap.context.state === 'running' ? decibelsOf(tap) : null;
    if (decibels !== null && !isBlind(tap, decibels))
      loudest = Math.max(loudest ?? 0, levelFor(decibels));
  }
  return loudest;
}

/**
 * Whether a tap is blind: read while the face listened for `VOICE_BLIND_AFTER_MS`
 * and no sound heard at all, not even one too soft to open the mouth. Only the
 * listening counts, the time between two reads up to a long frame, so a pause
 * between two speeches never makes a tap blind.
 */
function isBlind(tap: Tap, decibels: number): boolean {
  if (tap.heard || decibels > VOICE_HEARD_DB) {
    tap.heard = true;
    return false;
  }
  const now = performance.now();
  tap.silentMs += tap.readAt === null ? 0 : Math.min(TAP_READ_GAP_MAX_MS, now - tap.readAt);
  tap.readAt = now;
  return tap.silentMs >= VOICE_BLIND_AFTER_MS;
}
