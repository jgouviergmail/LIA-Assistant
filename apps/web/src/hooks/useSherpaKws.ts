'use client';

/**
 * useSherpaKws - Hook for Sherpa-onnx Wake Word Detection.
 *
 * Manages the complete wake word detection lifecycle using Whisper STT:
 * - WASM module loading from local files
 * - VAD + Whisper STT initialization
 * - Audio processing for wake word detection
 * - Automatic cleanup on unmount
 *
 * Architecture:
 * - VAD (Voice Activity Detection) detects speech segments
 * - Whisper STT transcribes each segment
 * - Wake word is detected by checking transcription for configured keywords
 *
 * Prerequisites:
 * - COOP/COEP headers for SharedArrayBuffer
 * - WASM files in /public/models/sherpa-wasm/
 * - Whisper model in /public/models/whisper-small/
 * - keywords.txt in /public/models/
 *
 * Usage:
 * ```tsx
 * const { isReady, isLoading, error, processAudio } = useSherpaKws({
 *   onKeywordDetected: (keyword, transcription) => {
 *     console.log('Wake word detected:', keyword);
 *     console.log('Full transcription:', transcription);
 *     startRecording();
 *   },
 * });
 * ```
 *
 * Reference: plan zippy-drifting-valley.md (section 2.5.1)
 * Created: 2026-02-01
 * Updated: 2026-02-01 - Migrated from KWS to Whisper STT for French support
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { logger } from '@/lib/logger';
import {
  initSherpaKws,
  isSherpaKwsSupported,
  getConfiguredWakeWords,
  type SherpaKwsInstance,
  type WakeWordResult,
} from '@/lib/audio/sherpaKws';

// ============================================================================
// Types
// ============================================================================

export interface UseSherpaKwsOptions {
  /**
   * Callback when wake word is detected.
   *
   * @param keyword The detected wake word
   * @param transcription The full transcription of the speech segment
   * @param durationSeconds Duration of the audio segment
   */
  onKeywordDetected: (keyword: string, transcription: string, durationSeconds: number) => void;
  /** Enable/disable wake word detection (default: true when mounted) */
  enabled?: boolean;
  /** Callback on error */
  onError?: (error: Error) => void;
}

export interface UseSherpaKwsReturn {
  /** Wake word detector is initialized and ready for audio processing */
  isReady: boolean;
  /** Detector is currently loading (WASM + model) */
  isLoading: boolean;
  /** Initialization error (if any) */
  error: Error | null;
  /** Whether wake word detection is supported in this environment */
  isSupported: boolean;
  /** Process audio samples for wake word detection */
  processAudio: (samples: Float32Array) => void;
  /** Reset detector state (call after handling wake word) */
  reset: () => void;
  /** Get configured wake words */
  getWakeWords: () => string[];
}

// ============================================================================
// Hook Implementation
// ============================================================================

export function useSherpaKws({
  onKeywordDetected,
  enabled = true,
  onError,
}: UseSherpaKwsOptions): UseSherpaKwsReturn {
  // Refs for detector resources (persist across renders)
  const detectorRef = useRef<SherpaKwsInstance | null>(null);
  const isInitializingRef = useRef(false);

  // State
  const [isReady, setIsReady] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  // Check browser support (memoized)
  const isSupported = isSherpaKwsSupported();

  /**
   * Initialize wake word detector on mount (when enabled).
   *
   * Handles:
   * - WASM module loading from local files
   * - VAD + Whisper initialization
   * - Cleanup on unmount or disable
   */
  useEffect(() => {
    // Skip if not enabled or not supported
    if (!enabled || !isSupported) {
      return;
    }

    // Prevent duplicate initialization
    if (isInitializingRef.current) {
      return;
    }

    let isMounted = true;
    isInitializingRef.current = true;
    setIsLoading(true);
    setError(null);

    const initialize = async () => {
      try {
        logger.info('sherpa_kws_hook_initializing', { component: 'useSherpaKws' });

        const detector = await initSherpaKws();

        if (!isMounted) {
          // Component unmounted during init - cleanup
          detector.free?.();
          return;
        }

        detectorRef.current = detector;

        setIsReady(true);
        setIsLoading(false);
        isInitializingRef.current = false;

        logger.info('sherpa_kws_hook_ready', {
          component: 'useSherpaKws',
          wakeWords: detector.getWakeWords(),
        });
      } catch (err) {
        if (!isMounted) return;

        const error = err instanceof Error ? err : new Error(String(err));
        setError(error);
        setIsLoading(false);
        isInitializingRef.current = false;

        logger.error('sherpa_kws_hook_init_failed', error, {
          component: 'useSherpaKws',
        });

        onError?.(error);
      }
    };

    initialize();

    // Cleanup on unmount or when disabled
    return () => {
      isMounted = false;

      // Free detector
      if (detectorRef.current) {
        detectorRef.current.free?.();
        detectorRef.current = null;
      }

      setIsReady(false);
      isInitializingRef.current = false;

      logger.debug('sherpa_kws_hook_cleanup', { component: 'useSherpaKws' });
    };
  }, [enabled, isSupported, onError]);

  /**
   * Process audio samples for wake word detection.
   *
   * Call this with audio chunks from AudioWorklet (16kHz, Float32).
   * Detection uses VAD + Whisper STT to transcribe and check for wake words.
   *
   * @param samples - Audio samples (Float32Array, normalized [-1, 1])
   */
  const processAudio = useCallback(
    (samples: Float32Array) => {
      const detector = detectorRef.current;

      // Skip if not ready
      if (!detector) {
        return;
      }

      try {
        // Process audio and check for wake word
        const result: WakeWordResult | null = detector.processAudio(samples);

        if (result?.keyword) {
          logger.info('sherpa_kws_keyword_detected', {
            keyword: result.keyword,
            transcription: result.text,
            durationSeconds: result.durationSeconds,
            component: 'useSherpaKws',
          });

          // Notify callback with detected wake word
          onKeywordDetected(result.keyword, result.text, result.durationSeconds);
        }
      } catch (err) {
        const error = err instanceof Error ? err : new Error(String(err));
        logger.error('sherpa_kws_process_error', error, {
          component: 'useSherpaKws',
        });
        // Don't throw - just log and continue
      }
    },
    [onKeywordDetected]
  );

  /**
   * Reset detector state for new detection cycle.
   *
   * Call this after handling a wake word detection if you want to
   * immediately start listening for the next wake word.
   */
  const reset = useCallback(() => {
    const detector = detectorRef.current;

    if (detector) {
      detector.reset();
      logger.debug('sherpa_kws_detector_reset', { component: 'useSherpaKws' });
    }
  }, []);

  /**
   * Get configured wake words.
   */
  const getWakeWords = useCallback(() => {
    const detector = detectorRef.current;
    if (detector) {
      return detector.getWakeWords();
    }
    return getConfiguredWakeWords();
  }, []);

  return {
    isReady,
    isLoading,
    error,
    isSupported,
    processAudio,
    reset,
    getWakeWords,
  };
}
