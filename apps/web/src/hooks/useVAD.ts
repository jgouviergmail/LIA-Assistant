'use client';

/**
 * useVAD - Hook for Voice Activity Detection.
 *
 * Wraps VoiceActivityDetector in a React hook with proper lifecycle management.
 * Detects when the user starts and stops speaking based on audio energy levels.
 *
 * Usage:
 * ```tsx
 * const { isActive, process, reset } = useVAD({
 *   onSpeechStart: () => console.log('Started speaking'),
 *   onSpeechEnd: () => console.log('Stopped speaking'),
 * });
 * ```
 */

import { useCallback, useRef, useState } from 'react';
import { VoiceActivityDetector, type VadConfig, type VadState } from '@/lib/audio/vad';

// ============================================================================
// Types
// ============================================================================

export interface UseVADOptions extends VadConfig {
  /** Callback when speech starts */
  onSpeechStart?: () => void;
  /** Callback when speech ends (after silence threshold) */
  onSpeechEnd?: () => void;
}

export interface UseVADReturn {
  /** Whether VAD is currently detecting speech */
  isSpeaking: boolean;
  /** Current speech duration in milliseconds */
  speechDurationMs: number;
  /** Current silence duration in milliseconds */
  silenceDurationMs: number;
  /** Process audio samples */
  process: (samples: Float32Array) => VadState;
  /** Reset VAD state */
  reset: () => void;
  /** Force end of speech */
  forceEnd: () => void;
}

// ============================================================================
// Hook Implementation
// ============================================================================

export function useVAD(options: UseVADOptions = {}): UseVADReturn {
  const { onSpeechStart, onSpeechEnd, ...config } = options;

  // State for React re-renders
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [speechDurationMs, setSpeechDurationMs] = useState(0);
  const [silenceDurationMs, setSilenceDurationMs] = useState(0);

  // VAD instance ref
  const vadRef = useRef<VoiceActivityDetector | null>(null);

  // Initialize VAD lazily
  const getVad = useCallback((): VoiceActivityDetector => {
    if (!vadRef.current) {
      vadRef.current = new VoiceActivityDetector(config, {
        onSpeechStart: () => {
          setIsSpeaking(true);
          onSpeechStart?.();
        },
        onSpeechEnd: () => {
          setIsSpeaking(false);
          setSpeechDurationMs(0);
          setSilenceDurationMs(0);
          onSpeechEnd?.();
        },
      });
    }
    return vadRef.current;
  }, [config, onSpeechStart, onSpeechEnd]);

  // Process audio samples
  const process = useCallback(
    (samples: Float32Array): VadState => {
      const vad = getVad();
      const state = vad.process(samples);

      // Update React state (batched by React)
      setIsSpeaking(state.isSpeaking);
      setSpeechDurationMs(state.speechDurationMs);
      setSilenceDurationMs(state.silenceDurationMs);

      return state;
    },
    [getVad]
  );

  // Reset VAD state
  const reset = useCallback(() => {
    vadRef.current?.reset();
    setIsSpeaking(false);
    setSpeechDurationMs(0);
    setSilenceDurationMs(0);
  }, []);

  // Force end of speech
  const forceEnd = useCallback(() => {
    vadRef.current?.forceEnd();
    setIsSpeaking(false);
    setSpeechDurationMs(0);
    setSilenceDurationMs(0);
  }, []);

  return {
    isSpeaking,
    speechDurationMs,
    silenceDurationMs,
    process,
    reset,
    forceEnd,
  };
}
