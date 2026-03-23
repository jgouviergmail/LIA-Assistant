/**
 * Ready chime — short synthesized audio cue for wake word acknowledgment.
 *
 * Plays a brief two-tone chime (ascending major third) to signal that the
 * app has detected the wake word and is ready to receive a voice command.
 * Uses Web Audio API oscillators — no external audio file needed.
 *
 * iOS compatibility:
 * - AudioContext is created once and reused (avoids per-play creation limits)
 * - Works because voice mode is activated via user gesture (long-press on badge),
 *   which unlocks the AudioContext for subsequent non-gesture playback
 *
 * Reference: Web Audio API OscillatorNode
 */

import { logger } from '@/lib/logger';

/** Frequency of first tone: C5 musical note (Hz). */
const CHIME_TONE1_HZ = 523.25;

/** Frequency of second tone: E5 musical note — ascending major third (Hz). */
const CHIME_TONE2_HZ = 659.25;

/** Chime volume (0.0–1.0). Kept low to be a subtle cue, not startling. */
const CHIME_VOLUME = 0.15;

/** Total chime duration in seconds. */
const CHIME_DURATION_S = 0.25;

// Shared AudioContext for chime playback (created lazily, reused)
let chimeContext: AudioContext | null = null;

/**
 * Play a short ascending two-tone chime (~250ms).
 *
 * Safe to call from any context — silently fails if AudioContext
 * is unavailable or suspended (e.g. before user interaction on iOS).
 */
export function playReadyChime(): void {
  try {
    // Create or reuse AudioContext
    if (!chimeContext || chimeContext.state === 'closed') {
      chimeContext = new AudioContext();
    }

    // Resume if suspended (iOS may suspend between uses)
    if (chimeContext.state === 'suspended') {
      chimeContext.resume().catch(() => {
        // Can't resume without user gesture — skip chime silently
      });
    }

    const ctx = chimeContext;
    const now = ctx.currentTime;

    // Create gain node for volume envelope
    const gainNode = ctx.createGain();
    gainNode.connect(ctx.destination);
    gainNode.gain.setValueAtTime(0, now);
    // Fade in
    gainNode.gain.linearRampToValueAtTime(CHIME_VOLUME, now + 0.02);
    // Sustain briefly then fade out
    gainNode.gain.setValueAtTime(CHIME_VOLUME, now + 0.1);
    gainNode.gain.exponentialRampToValueAtTime(0.001, now + CHIME_DURATION_S);

    // Tone 1: C5 — 0ms to 120ms
    const osc1 = ctx.createOscillator();
    osc1.type = 'sine';
    osc1.frequency.setValueAtTime(CHIME_TONE1_HZ, now);
    osc1.connect(gainNode);
    osc1.start(now);
    osc1.stop(now + 0.12);

    // Tone 2: E5 — 80ms to 250ms (overlaps slightly for smooth transition)
    const gain2 = ctx.createGain();
    gain2.connect(ctx.destination);
    gain2.gain.setValueAtTime(0, now + 0.08);
    gain2.gain.linearRampToValueAtTime(CHIME_VOLUME, now + 0.1);
    gain2.gain.setValueAtTime(CHIME_VOLUME, now + 0.15);
    gain2.gain.exponentialRampToValueAtTime(0.001, now + CHIME_DURATION_S);

    const osc2 = ctx.createOscillator();
    osc2.type = 'sine';
    osc2.frequency.setValueAtTime(CHIME_TONE2_HZ, now + 0.08);
    osc2.connect(gain2);
    osc2.start(now + 0.08);
    osc2.stop(now + CHIME_DURATION_S);

    logger.debug('ready_chime_played', { component: 'readyChime' });
  } catch (err) {
    // Non-critical — chime is UX enhancement, not functional requirement
    logger.debug('ready_chime_failed', {
      component: 'readyChime',
      error: String(err),
    });
  }
}
