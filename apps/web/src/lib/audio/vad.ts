/**
 * Voice Activity Detection (VAD) utilities.
 *
 * Provides energy-based speech detection for determining when
 * the user has stopped speaking.
 *
 * Reference: plan zippy-drifting-valley.md (section 2.5)
 */

import { logger } from '@/lib/logger';
import {
  VOICE_MODE_VAD_ENERGY_THRESHOLD,
  VOICE_MODE_VAD_SILENCE_MS,
  VOICE_MODE_MIN_SPEECH_MS,
} from '@/lib/constants';

/**
 * Calculate RMS (Root Mean Square) energy of audio samples.
 *
 * RMS is a good measure of audio "loudness" and is used
 * to detect speech vs. silence.
 *
 * @param samples - Float32 audio samples normalized [-1, 1]
 * @returns RMS energy value (0.0 = silence, 1.0 = max)
 */
export function calculateRmsEnergy(samples: Float32Array): number {
  if (samples.length === 0) return 0;

  let sum = 0;
  for (let i = 0; i < samples.length; i++) {
    sum += samples[i] * samples[i];
  }

  return Math.sqrt(sum / samples.length);
}

/**
 * Voice Activity Detector configuration.
 */
export interface VadConfig {
  /** Energy threshold for speech detection (default: 0.01) */
  energyThreshold?: number;
  /** Silence duration to trigger end of speech (ms, default: 1000) */
  silenceThresholdMs?: number;
  /** Minimum speech duration to be valid (ms, default: 500) */
  minSpeechMs?: number;
  /** Sample rate for timing calculations (default: 16000) */
  sampleRate?: number;
}

/**
 * Voice Activity Detector state.
 */
export interface VadState {
  /** Whether currently detecting speech */
  isSpeaking: boolean;
  /** Duration of current speech (ms) */
  speechDurationMs: number;
  /** Duration of current silence (ms) */
  silenceDurationMs: number;
  /** Total samples processed */
  samplesProcessed: number;
}

/**
 * Voice Activity Detector class.
 *
 * Tracks speech/silence state based on audio energy levels.
 * Emits events when speech starts/ends.
 *
 * Usage:
 * ```ts
 * const vad = new VoiceActivityDetector({
 *   onSpeechStart: () => console.log('Started speaking'),
 *   onSpeechEnd: () => console.log('Stopped speaking'),
 * });
 *
 * // Feed audio samples from AudioWorklet
 * workletNode.port.onmessage = (e) => {
 *   vad.process(new Float32Array(e.data));
 * };
 * ```
 */
export class VoiceActivityDetector {
  private config: Required<VadConfig>;
  private state: VadState;
  private onSpeechStart?: () => void;
  private onSpeechEnd?: () => void;

  constructor(
    config: VadConfig = {},
    callbacks?: {
      onSpeechStart?: () => void;
      onSpeechEnd?: () => void;
    }
  ) {
    this.config = {
      energyThreshold: config.energyThreshold ?? VOICE_MODE_VAD_ENERGY_THRESHOLD,
      silenceThresholdMs: config.silenceThresholdMs ?? VOICE_MODE_VAD_SILENCE_MS,
      minSpeechMs: config.minSpeechMs ?? VOICE_MODE_MIN_SPEECH_MS,
      sampleRate: config.sampleRate ?? 16000,
    };

    this.state = {
      isSpeaking: false,
      speechDurationMs: 0,
      silenceDurationMs: 0,
      samplesProcessed: 0,
    };

    this.onSpeechStart = callbacks?.onSpeechStart;
    this.onSpeechEnd = callbacks?.onSpeechEnd;
  }

  // Debug: log energy levels periodically
  private debugCounter = 0;
  private readonly DEBUG_INTERVAL = 50; // Log every 50 chunks (~1 second at 20ms chunks)

  /**
   * Process audio samples and update VAD state.
   *
   * @param samples - Float32 audio samples
   * @returns Current VAD state
   */
  process(samples: Float32Array): VadState {
    const energy = calculateRmsEnergy(samples);
    const durationMs = (samples.length / this.config.sampleRate) * 1000;
    const isSpeech = energy > this.config.energyThreshold;

    this.state.samplesProcessed += samples.length;

    // Debug logging every ~1 second
    this.debugCounter++;
    if (this.debugCounter >= this.DEBUG_INTERVAL) {
      this.debugCounter = 0;
      logger.debug('vad_energy_level', {
        component: 'VAD',
        energy: Math.round(energy * 10000) / 10000,
        threshold: this.config.energyThreshold,
        isSpeech,
        isSpeaking: this.state.isSpeaking,
        silenceDurationMs: Math.round(this.state.silenceDurationMs),
        speechDurationMs: Math.round(this.state.speechDurationMs),
      });
    }

    if (isSpeech) {
      // Speech detected
      this.state.silenceDurationMs = 0;

      if (!this.state.isSpeaking) {
        // Speech just started
        this.state.isSpeaking = true;
        this.state.speechDurationMs = durationMs;
        logger.info('vad_speech_start', { component: 'VAD', energy });
        this.onSpeechStart?.();
      } else {
        this.state.speechDurationMs += durationMs;
      }
    } else {
      // Silence detected
      if (this.state.isSpeaking) {
        this.state.silenceDurationMs += durationMs;

        // Check if silence threshold reached
        if (this.state.silenceDurationMs >= this.config.silenceThresholdMs) {
          logger.info('vad_silence_threshold_reached', {
            component: 'VAD',
            silenceDurationMs: this.state.silenceDurationMs,
            speechDurationMs: this.state.speechDurationMs,
            minSpeechMs: this.config.minSpeechMs,
          });

          // Check if speech was long enough to be valid
          if (this.state.speechDurationMs >= this.config.minSpeechMs) {
            logger.info('vad_speech_end', {
              component: 'VAD',
              speechDurationMs: this.state.speechDurationMs,
            });
            this.onSpeechEnd?.();
          } else {
            logger.debug('vad_speech_too_short', {
              component: 'VAD',
              speechDurationMs: this.state.speechDurationMs,
              minSpeechMs: this.config.minSpeechMs,
            });
          }

          // Reset state
          this.state.isSpeaking = false;
          this.state.speechDurationMs = 0;
          this.state.silenceDurationMs = 0;
        }
      }
    }

    return { ...this.state };
  }

  /**
   * Get current VAD state.
   */
  getState(): VadState {
    return { ...this.state };
  }

  /**
   * Reset VAD state.
   */
  reset(): void {
    this.state = {
      isSpeaking: false,
      speechDurationMs: 0,
      silenceDurationMs: 0,
      samplesProcessed: 0,
    };
  }

  /**
   * Force end of speech (e.g., when stopping recording).
   */
  forceEnd(): void {
    if (this.state.isSpeaking && this.state.speechDurationMs >= this.config.minSpeechMs) {
      this.onSpeechEnd?.();
    }
    this.reset();
  }
}
