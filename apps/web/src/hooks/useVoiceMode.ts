'use client';

/**
 * useVoiceMode - Main orchestration hook for Voice Mode.
 *
 * Manages the complete voice mode lifecycle:
 * 1. Wake word detection via Sherpa-onnx KWS ("OK" - universal)
 * 2. Audio recording with VAD
 * 3. WebSocket streaming for STT
 * 4. Transcription callback
 *
 * State Machine:
 * - idle: Voice mode disabled, text input active
 * - listening: Listening for wake word via KWS
 * - recording: Recording user speech with VAD
 * - processing: STT transcription in progress
 * - speaking: TTS playing response (managed externally)
 *
 * Flow:
 * 1. User enables voice mode → state = "listening"
 * 2. User says "OK" → KWS detects → state = "recording"
 * 3. User speaks → VAD detects end of speech → state = "processing"
 * 4. STT transcribes → callback triggered → state = "speaking"
 * 5. TTS plays response → onTtsComplete() → state = "listening"
 *
 * Usage:
 * ```tsx
 * const {
 *   isEnabled,
 *   state,
 *   enable,
 *   disable,
 *   startRecording,
 *   stopRecording,
 * } = useVoiceMode({
 *   onTranscription: (text) => sendMessage(text),
 * });
 * ```
 *
 * Reference: plan zippy-drifting-valley.md (section 2.2)
 */

import { useCallback, useEffect, useRef } from 'react';
import { logger } from '@/lib/logger';
import { VoiceInputService } from '@/lib/voice-input-service';
import { VoiceActivityDetector } from '@/lib/audio/vad';
import { playReadyChime } from '@/lib/audio/ready-chime';
import { useSherpaKws } from '@/hooks/useSherpaKws';
import { isSherpaKwsSupported } from '@/lib/audio/sherpaKws';
import { useVoiceModeStore, type VoiceModeState } from '@/stores/voiceModeStore';
import { useMeetingIsCapturing } from '@/stores/meetingRecorderStore';
import {
  VOICE_INPUT_SAMPLE_RATE,
  VOICE_INPUT_CHUNK_SIZE,
  VOICE_MODE_MAX_RECORDING_SECONDS,
  VOICE_RECORDING_SETUP_TIMEOUT_MS,
} from '@/lib/constants';

// ============================================================================
// Types
// ============================================================================

export interface UseVoiceModeOptions {
  /** Callback when transcription is received. The optional ``meta`` payload
   *  carries STT cost metadata (set when the backend ran a remote provider). */
  onTranscription?: (
    text: string,
    meta?: import('@/lib/voice-input-service').VoiceTranscriptionMeta
  ) => void;
  /** Callback when TTS should start playing */
  onStartSpeaking?: () => void;
  /** Callback when TTS finishes playing */
  onStopSpeaking?: () => void;
  /** Callback on error */
  onError?: (error: Error) => void;
  /** Callback when wake word is detected (before recording starts) */
  onWakeWordDetected?: (keyword: string) => void;
}

export interface UseVoiceModeReturn {
  /** Whether voice mode is enabled */
  isEnabled: boolean;
  /** Current voice mode state */
  state: VoiceModeState;
  /** Whether currently recording */
  isRecording: boolean;
  /** Whether processing transcription */
  isProcessing: boolean;
  /** Whether TTS is playing */
  isSpeaking: boolean;
  /** Whether listening for wake word */
  isListening: boolean;
  /** Whether KWS is loading */
  isKwsLoading: boolean;
  /** Whether KWS is ready */
  isKwsReady: boolean;
  /** Whether KWS microphone is actively listening */
  isKwsListening: boolean;
  /** Current error (if any) */
  error: Error | null;
  /** Enable voice mode */
  enable: () => void;
  /** Disable voice mode */
  disable: () => void;
  /** Toggle voice mode */
  toggle: () => void;
  /** Start recording (manual trigger or wake word) */
  startRecording: () => Promise<void>;
  /** Stop recording and process */
  stopRecording: () => void;
  /** Signal that TTS has finished */
  onTtsComplete: () => void;
  /** Check if microphone is supported */
  isSupported: boolean;
  /** Check if KWS (wake word) is supported */
  isKwsSupported: boolean;
}

// ============================================================================
// Hook Implementation
// ============================================================================

export function useVoiceMode(options: UseVoiceModeOptions = {}): UseVoiceModeReturn {
  const { onTranscription, onStartSpeaking, onStopSpeaking, onError, onWakeWordDetected } = options;
  // ADR-258: one microphone owner at a time — the wake-word detector and its
  // listening loop pause while a meeting records, and resume by themselves.
  const meetingCapturing = useMeetingIsCapturing();

  // Store state
  const {
    isEnabled,
    state,
    error,
    enable: storeEnable,
    disable: storeDisable,
    setState,
    setError,
    setKwsReady,
    setKwsLoading,
    setKwsListening,
    isKwsReady,
    isKwsLoading,
    isKwsListening,
    reset,
    recordWakeWord,
  } = useVoiceModeStore();

  // Refs for recording audio resources
  const serviceRef = useRef<VoiceInputService | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const vadRef = useRef<VoiceActivityDetector | null>(null);
  const recordingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isStartingRef = useRef(false);

  // Refs for KWS listening audio resources (separate from recording)
  const kwsAudioContextRef = useRef<AudioContext | null>(null);
  const kwsMediaStreamRef = useRef<MediaStream | null>(null);
  const kwsWorkletNodeRef = useRef<AudioWorkletNode | null>(null);
  const kwsSourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);

  // Ref to hold handleSpeechEnd callback to avoid stale closure in VAD
  const handleSpeechEndRef = useRef<(() => void) | null>(null);

  // Tracks whether current recording was triggered by wake word (for audio chime)
  const wakeWordTriggeredRef = useRef(false);

  // Pre-warmed VoiceInputService (connected during listening state for lower latency)
  const prewarmedServiceRef = useRef<VoiceInputService | null>(null);

  // Derived states
  const isRecording = state === 'recording';
  const isProcessing = state === 'processing';
  const isSpeaking = state === 'speaking';
  const isListening = state === 'listening';

  // Check browser support
  const isSupported =
    typeof navigator !== 'undefined' &&
    typeof navigator.mediaDevices !== 'undefined' &&
    typeof navigator.mediaDevices.getUserMedia !== 'undefined' &&
    typeof AudioContext !== 'undefined';

  // Check KWS support
  const isKwsSupported = isSherpaKwsSupported();

  /**
   * Clean up audio resources.
   */
  const cleanupAudio = useCallback(() => {
    // Clear recording timeout
    if (recordingTimeoutRef.current) {
      clearTimeout(recordingTimeoutRef.current);
      recordingTimeoutRef.current = null;
    }

    // Reset VAD
    vadRef.current?.reset();

    // Disconnect audio nodes
    if (sourceNodeRef.current) {
      sourceNodeRef.current.disconnect();
      sourceNodeRef.current = null;
    }

    if (workletNodeRef.current) {
      workletNodeRef.current.disconnect();
      workletNodeRef.current = null;
    }

    // Stop media stream
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach(track => track.stop());
      mediaStreamRef.current = null;
    }

    // Close audio context
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }
  }, []);

  /**
   * Clean up WebSocket service.
   */
  const cleanupService = useCallback(() => {
    if (serviceRef.current) {
      serviceRef.current.dispose();
      serviceRef.current = null;
    }
  }, []);

  /**
   * Clean up KWS audio resources (separate from recording).
   */
  const cleanupKwsAudio = useCallback(() => {
    // Mark KWS as no longer listening
    setKwsListening(false);

    // Disconnect KWS audio nodes
    if (kwsSourceNodeRef.current) {
      kwsSourceNodeRef.current.disconnect();
      kwsSourceNodeRef.current = null;
    }

    if (kwsWorkletNodeRef.current) {
      kwsWorkletNodeRef.current.disconnect();
      kwsWorkletNodeRef.current = null;
    }

    // Stop KWS media stream
    if (kwsMediaStreamRef.current) {
      kwsMediaStreamRef.current.getTracks().forEach(track => track.stop());
      kwsMediaStreamRef.current = null;
    }

    // Close KWS audio context
    if (kwsAudioContextRef.current) {
      kwsAudioContextRef.current.close().catch(() => {});
      kwsAudioContextRef.current = null;
    }
  }, [setKwsListening]);

  /**
   * Pause KWS audio but KEEP the media stream alive for reuse by recording.
   * Disconnects audio nodes and closes AudioContext, but does NOT stop the
   * MediaStream tracks. The caller is responsible for stopping or reusing the stream.
   *
   * Returns the preserved MediaStream (or null if none was active).
   */
  const pauseKwsAudioAndStealStream = useCallback((): MediaStream | null => {
    setKwsListening(false);

    // Disconnect KWS audio nodes
    if (kwsSourceNodeRef.current) {
      kwsSourceNodeRef.current.disconnect();
      kwsSourceNodeRef.current = null;
    }

    if (kwsWorkletNodeRef.current) {
      kwsWorkletNodeRef.current.disconnect();
      kwsWorkletNodeRef.current = null;
    }

    // Take ownership of the media stream (do NOT stop tracks)
    const stream = kwsMediaStreamRef.current;
    kwsMediaStreamRef.current = null;

    // Close KWS audio context
    if (kwsAudioContextRef.current) {
      kwsAudioContextRef.current.close().catch(() => {});
      kwsAudioContextRef.current = null;
    }

    return stream;
  }, [setKwsListening]);

  /**
   * Create AudioWorklet processor script for KWS.
   */
  const createKwsWorkletScript = useCallback((): string => {
    const workletCode = `
      class KwsProcessor extends AudioWorkletProcessor {
        constructor() {
          super();
          this.buffer = [];
          // ~100ms chunks at 16kHz = 1600 samples
          this.chunkSize = 1600;
        }

        process(inputs) {
          const input = inputs[0];
          if (input && input.length > 0) {
            const samples = input[0];

            for (let i = 0; i < samples.length; i++) {
              this.buffer.push(samples[i]);
            }

            while (this.buffer.length >= this.chunkSize) {
              const chunk = this.buffer.splice(0, this.chunkSize);
              const float32 = new Float32Array(chunk);
              this.port.postMessage({ samples: float32.buffer }, [float32.buffer]);
            }
          }
          return true;
        }
      }

      registerProcessor('kws-processor', KwsProcessor);
    `;

    const blob = new Blob([workletCode], { type: 'application/javascript' });
    return URL.createObjectURL(blob);
  }, []);

  /**
   * Handle transcription result.
   */
  const handleTranscription = useCallback(
    (
      text: string,
      duration: number,
      meta?: import('@/lib/voice-input-service').VoiceTranscriptionMeta
    ) => {
      logger.info('voice_mode_transcription_received', {
        component: 'useVoiceMode',
        text_length: text.length,
        duration_seconds: duration,
        stt_provider: meta?.stt_provider ?? null,
        stt_cost_eur: meta?.stt_cost_eur ?? null,
      });

      // Clean up service
      cleanupService();

      if (text.trim()) {
        // Send transcription to parent
        onTranscription?.(text, meta);

        // If TTS callbacks are provided, go to speaking state and wait for onTtsComplete
        // Otherwise, skip speaking and go directly back to listening
        if (onStartSpeaking) {
          setState('speaking');
          onStartSpeaking();
        } else {
          // No TTS - go back to listening immediately
          logger.info('voice_mode_returning_to_listening', {
            component: 'useVoiceMode',
            reason: 'no_tts_callback',
          });
          setState('listening');
        }
      } else {
        // Empty transcription - go back to listening
        logger.info('voice_mode_returning_to_listening', {
          component: 'useVoiceMode',
          reason: 'empty_transcription',
        });
        setState('listening');
      }
    },
    [cleanupService, setState, onStartSpeaking, onTranscription]
  );

  /**
   * Handle WebSocket connection change.
   */
  const handleConnectionChange = useCallback(
    (connected: boolean) => {
      // The WebSocket service holds this callback from startRecording time —
      // read the CURRENT machine state from the store, not the render-time
      // closure: a stale `state` (still 'listening' when wired) silently
      // swallowed connection drops during 'processing', leaving the UI stuck.
      if (!connected && useVoiceModeStore.getState().state === 'processing') {
        const err = new Error('Connection lost during transcription');
        logger.warn('voice_mode_connection_lost', { component: 'useVoiceMode' });
        // setError also drives the state transition (listening while enabled,
        // idle otherwise) — no explicit setState needed.
        setError(err);
        onError?.(err);
        cleanupService();
      }
    },
    [setError, onError, cleanupService]
  );

  /**
   * Handle error.
   */
  const handleError = useCallback(
    (err: Error) => {
      logger.error('voice_mode_error', err, { component: 'useVoiceMode' });
      // setError also drives the state transition: back to 'listening' while
      // enabled, 'idle' otherwise — a trailing setState('listening') here
      // used to leave the inconsistent pair state='listening'/isEnabled=false.
      setError(err);
      onError?.(err);
      cleanupAudio();
      cleanupService();
    },
    [setError, onError, cleanupAudio, cleanupService]
  );

  /**
   * Ref to hold startRecording function for KWS callback.
   * This avoids circular dependency between handleKeywordDetected and startRecording.
   */
  const startRecordingRef = useRef<((existingStream?: MediaStream) => Promise<void>) | null>(null);

  /**
   * Handle wake word detection from KWS.
   * Triggered when user says "OK" (universal wake word).
   *
   * Optimization: transfers the KWS microphone stream to the recording pipeline
   * instead of stopping it and acquiring a new one (saves ~200-800ms getUserMedia).
   */
  const handleKeywordDetected = useCallback(
    (keyword: string) => {
      // Ignore wake word if not in listening state (safety check)
      if (state !== 'listening') {
        logger.debug('voice_mode_wake_word_ignored', {
          component: 'useVoiceMode',
          keyword,
          reason: 'not_listening',
          currentState: state,
        });
        return;
      }

      logger.info('voice_mode_wake_word_detected', {
        component: 'useVoiceMode',
        keyword,
      });

      // Record wake word event in store
      recordWakeWord();

      // Mark as wake-word-triggered so startRecording plays the ready chime
      wakeWordTriggeredRef.current = true;

      // Notify callback
      onWakeWordDetected?.(keyword);

      // Pause KWS but keep the mic stream alive for reuse
      const reusableStream = pauseKwsAudioAndStealStream();

      // Start recording, passing the existing stream to skip getUserMedia
      startRecordingRef.current?.(reusableStream ?? undefined);
    },
    [state, recordWakeWord, onWakeWordDetected, pauseKwsAudioAndStealStream]
  );

  /**
   * Handle KWS initialization status changes.
   */
  const handleKwsError = useCallback(
    (err: Error) => {
      logger.error('voice_mode_kws_error', err, { component: 'useVoiceMode' });
      // Don't fail completely - KWS is optional, manual trigger still works
      setKwsReady(false);
      setKwsLoading(false);
    },
    [setKwsReady, setKwsLoading]
  );

  // Initialize Sherpa KWS (wake word detection)
  // Keep detector alive while voice mode is enabled (not just during listening)
  // This avoids expensive re-initialization on every recording cycle
  const {
    isReady: kwsIsReady,
    isLoading: kwsIsLoading,
    processAudio: kwsProcessAudio,
  } = useSherpaKws({
    onKeywordDetected: handleKeywordDetected,
    enabled: isEnabled && isKwsSupported && !meetingCapturing,
    onError: handleKwsError,
  });

  // Sync KWS state to store
  useEffect(() => {
    setKwsReady(kwsIsReady);
    setKwsLoading(kwsIsLoading);
  }, [kwsIsReady, kwsIsLoading, setKwsReady, setKwsLoading]);

  /**
   * Cached recording worklet blob URL (created once, reused across recordings).
   */
  const recordingWorkletUrlRef = useRef<string | null>(null);

  /**
   * Get or create AudioWorklet processor script as a cached Blob URL.
   */
  const getOrCreateRecordingWorkletUrl = useCallback((): string => {
    if (recordingWorkletUrlRef.current) return recordingWorkletUrlRef.current;

    const workletCode = `
      class VoiceModeProcessor extends AudioWorkletProcessor {
        constructor() {
          super();
          this.buffer = [];
          this.chunkSize = ${VOICE_INPUT_CHUNK_SIZE};
        }

        process(inputs) {
          const input = inputs[0];
          if (input.length > 0) {
            const samples = input[0];

            for (let i = 0; i < samples.length; i++) {
              this.buffer.push(samples[i]);
            }

            while (this.buffer.length >= this.chunkSize) {
              const chunk = this.buffer.splice(0, this.chunkSize);

              // Send Float32 for VAD
              const float32 = new Float32Array(chunk);

              // Convert to Int16 for WebSocket
              const int16Array = new Int16Array(chunk.length);
              for (let i = 0; i < chunk.length; i++) {
                const s = Math.max(-1, Math.min(1, chunk[i]));
                int16Array[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
              }

              this.port.postMessage({
                float32: float32.buffer,
                int16: int16Array.buffer,
              }, [float32.buffer, int16Array.buffer]);
            }
          }
          return true;
        }
      }

      registerProcessor('voice-mode-processor', VoiceModeProcessor);
    `;

    const blob = new Blob([workletCode], { type: 'application/javascript' });
    recordingWorkletUrlRef.current = URL.createObjectURL(blob);
    return recordingWorkletUrlRef.current;
  }, []);

  /**
   * Handle speech end (VAD detected silence).
   */
  const handleSpeechEnd = useCallback(() => {
    logger.debug('voice_mode_speech_end_callback', {
      component: 'useVoiceMode',
      currentState: state,
    });

    if (state !== 'recording') {
      logger.debug('voice_mode_speech_end_ignored', {
        component: 'useVoiceMode',
        reason: 'not_recording',
        currentState: state,
      });
      return;
    }

    logger.info('voice_mode_speech_end_detected', { component: 'useVoiceMode' });

    setState('processing');
    serviceRef.current?.endAudio();
    cleanupAudio();
  }, [state, setState, cleanupAudio]);

  // Keep handleSpeechEnd ref updated to avoid stale closure in VAD callback
  useEffect(() => {
    handleSpeechEndRef.current = handleSpeechEnd;
  }, [handleSpeechEnd]);

  /**
   * Ref to hold stopRecording for the max-duration timeout in startRecording.
   * Same pattern as startRecordingRef: breaks the forward reference
   * (stopRecording is declared after startRecording) and guarantees the
   * timeout calls the CURRENT instance — a closure would capture the
   * instance from the creation render, whose captured `state` predates
   * 'recording', making its `state !== 'recording'` guard a no-op.
   */
  const stopRecordingRef = useRef<(() => void) | null>(null);

  /**
   * Start recording.
   *
   * Optimizations:
   * - Accepts an existing MediaStream to skip getUserMedia (~200-800ms saved
   *   when wake word transfers the KWS mic stream)
   * - Parallelizes getUserMedia + WS connect via Promise.allSettled
   * - Uses cached worklet blob URL (avoids Blob creation each time)
   *
   * @param existingStream Optional MediaStream to reuse (from KWS wake word flow)
   */
  const startRecording = useCallback(
    async (existingStream?: MediaStream) => {
      if (!isSupported) {
        handleError(new Error('Voice input is not supported in this browser'));
        return;
      }

      if (isStartingRef.current || state === 'recording' || state === 'processing') {
        return;
      }

      isStartingRef.current = true;
      let setupTimeoutId: ReturnType<typeof setTimeout> | undefined;

      try {
        cleanupService();
        cleanupAudio();

        // Step 1: Reuse pre-warmed WS service or create new one
        let service: VoiceInputService;
        const prewarmed = prewarmedServiceRef.current;
        prewarmedServiceRef.current = null; // Take ownership

        if (prewarmed && prewarmed.isConnected) {
          // Reuse pre-warmed service — WS already connected, skip ticket + handshake
          service = prewarmed;
          // Re-wire callbacks (they may reference stale closures from pre-warm time)
          service.updateCallbacks({
            onTranscription: handleTranscription,
            onConnectionChange: handleConnectionChange,
            onError: handleError,
          });
          logger.debug('voice_mode_service_prewarmed', { component: 'useVoiceMode' });
        } else {
          // Dispose stale pre-warmed service if any
          prewarmed?.dispose();
          service = new VoiceInputService({
            onTranscription: handleTranscription,
            onConnectionChange: handleConnectionChange,
            onError: handleError,
          });
        }
        serviceRef.current = service;

        // Step 2: Get mic + connect WS (with timeout protection)
        const timeoutPromise = new Promise<never>((_, reject) => {
          setupTimeoutId = setTimeout(
            () => reject(new Error('Voice recording setup timed out')),
            VOICE_RECORDING_SETUP_TIMEOUT_MS
          );
        });
        // Not every path races against this promise (the wake-word flow with
        // a reused stream and a pre-warmed WS skips both races) — without a
        // default handler its rejection fired as an unhandled rejection
        // ~10s after every such recording. The timer itself is disarmed in
        // the finally block once setup ends.
        timeoutPromise.catch(() => {});

        let stream: MediaStream;

        if (existingStream && existingStream.active) {
          // Reuse KWS mic stream (wake word flow) — skip getUserMedia entirely
          stream = existingStream;
          if (!service.isConnected) {
            await Promise.race([service.connect(), timeoutPromise]);
          }

          logger.debug('voice_mode_stream_reused', { component: 'useVoiceMode' });
        } else {
          // Stop the passed stream if it's inactive (safety)
          if (existingStream) {
            existingStream.getTracks().forEach(track => track.stop());
          }

          // Launch mic (+ WS connect if not pre-warmed) in parallel with timeout
          const connectIfNeeded = service.isConnected ? Promise.resolve() : service.connect();

          const setupPromise = Promise.allSettled([
            navigator.mediaDevices.getUserMedia({
              audio: {
                sampleRate: VOICE_INPUT_SAMPLE_RATE,
                channelCount: 1,
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
              },
            }),
            connectIfNeeded,
          ]);

          const [streamResult, connectResult] = (await Promise.race([
            setupPromise,
            timeoutPromise,
          ])) as [PromiseSettledResult<MediaStream>, PromiseSettledResult<void>];

          // Handle partial failures
          if (streamResult.status === 'rejected' || connectResult.status === 'rejected') {
            if (streamResult.status === 'fulfilled') {
              streamResult.value.getTracks().forEach(track => track.stop());
            }
            const reason =
              streamResult.status === 'rejected'
                ? streamResult.reason
                : (connectResult as PromiseRejectedResult).reason;
            throw reason instanceof Error ? reason : new Error(String(reason));
          }

          stream = streamResult.value;
        }

        mediaStreamRef.current = stream;

        // Step 3: Create AudioContext
        const audioContext = new AudioContext({
          sampleRate: VOICE_INPUT_SAMPLE_RATE,
        });
        audioContextRef.current = audioContext;

        // Step 4: Create VAD
        vadRef.current = new VoiceActivityDetector(
          {},
          { onSpeechEnd: () => handleSpeechEndRef.current?.() }
        );

        // Step 5: Create AudioWorklet (uses cached blob URL)
        await audioContext.audioWorklet.addModule(getOrCreateRecordingWorkletUrl());

        const workletNode = new AudioWorkletNode(audioContext, 'voice-mode-processor');
        workletNodeRef.current = workletNode;

        // Step 6: Handle audio chunks
        workletNode.port.onmessage = event => {
          const { float32, int16 } = event.data;

          // Process with VAD
          vadRef.current?.process(new Float32Array(float32));

          // Send to WebSocket
          service.sendAudio(int16);
        };

        // Step 7: Connect audio pipeline
        const sourceNode = audioContext.createMediaStreamSource(stream);
        sourceNodeRef.current = sourceNode;
        sourceNode.connect(workletNode);

        // Step 8: Set max recording timeout
        recordingTimeoutRef.current = setTimeout(() => {
          logger.info('voice_mode_max_duration_reached', { component: 'useVoiceMode' });
          stopRecordingRef.current?.();
        }, VOICE_MODE_MAX_RECORDING_SECONDS * 1000);

        setState('recording');

        // Play ready chime when recording starts after wake word detection
        // (not on manual tap — tap has instant visual feedback, no delay to signal)
        if (wakeWordTriggeredRef.current) {
          wakeWordTriggeredRef.current = false;
          playReadyChime();
        }

        logger.info('voice_mode_recording_started', { component: 'useVoiceMode' });
      } catch (err) {
        const error = err instanceof Error ? err : new Error(String(err));

        if (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError') {
          handleError(new Error('Microphone permission denied'));
        } else {
          handleError(error);
        }
      } finally {
        if (setupTimeoutId !== undefined) {
          clearTimeout(setupTimeoutId);
        }
        isStartingRef.current = false;
      }
    },
    [
      isSupported,
      state,
      cleanupService,
      cleanupAudio,
      handleTranscription,
      handleConnectionChange,
      handleError,
      getOrCreateRecordingWorkletUrl,
      setState,
    ]
  );

  /**
   * Stop recording manually.
   */
  const stopRecording = useCallback(() => {
    if (state !== 'recording') return;

    logger.info('voice_mode_recording_stopped', { component: 'useVoiceMode' });

    setState('processing');
    vadRef.current?.forceEnd();
    serviceRef.current?.endAudio();
    cleanupAudio();
  }, [state, setState, cleanupAudio]);

  // Keep stopRecording ref updated for the max-duration timeout in startRecording
  useEffect(() => {
    stopRecordingRef.current = stopRecording;
  }, [stopRecording]);

  /**
   * Called when TTS finishes playing.
   */
  const onTtsComplete = useCallback(() => {
    logger.debug('voice_mode_tts_complete', { component: 'useVoiceMode' });
    onStopSpeaking?.();

    if (isEnabled) {
      setState('listening');
    } else {
      reset();
    }
  }, [isEnabled, setState, reset, onStopSpeaking]);

  /**
   * Enable voice mode.
   */
  const enable = useCallback(() => {
    if (!isSupported) {
      const err = new Error('Voice input is not supported');
      setError(err);
      onError?.(err);
      return;
    }

    storeEnable();
    logger.info('voice_mode_enabled', { component: 'useVoiceMode' });
  }, [isSupported, storeEnable, setError, onError]);

  /**
   * Disable voice mode.
   */
  const disable = useCallback(() => {
    cleanupAudio();
    cleanupKwsAudio();
    cleanupService();
    // Dispose pre-warmed service
    if (prewarmedServiceRef.current) {
      prewarmedServiceRef.current.dispose();
      prewarmedServiceRef.current = null;
    }
    storeDisable();
    logger.info('voice_mode_disabled', { component: 'useVoiceMode' });
  }, [cleanupAudio, cleanupKwsAudio, cleanupService, storeDisable]);

  /**
   * Toggle voice mode.
   */
  const toggle = useCallback(() => {
    if (isEnabled) {
      disable();
    } else {
      enable();
    }
  }, [isEnabled, enable, disable]);

  // Set startRecording ref for handleKeywordDetected callback
  useEffect(() => {
    startRecordingRef.current = startRecording;
  }, [startRecording]);

  /**
   * Start KWS listening when in "listening" state.
   * Opens microphone and feeds audio to Sherpa KWS for wake word detection.
   */
  useEffect(() => {
    // Only start KWS listening when enabled, in listening state, and KWS is ready
    if (!isEnabled || meetingCapturing || state !== 'listening' || !kwsIsReady || !isKwsSupported) {
      logger.debug('voice_mode_kws_effect_skip', {
        component: 'useVoiceMode',
        isEnabled,
        meetingCapturing,
        state,
        kwsIsReady,
        isKwsSupported,
      });
      return;
    }

    logger.info('voice_mode_kws_effect_starting', {
      component: 'useVoiceMode',
      state,
      kwsIsReady,
    });

    let isMounted = true;

    const startKwsListening = async () => {
      try {
        // Get microphone for KWS
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            sampleRate: VOICE_INPUT_SAMPLE_RATE,
            channelCount: 1,
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
          },
        });

        if (!isMounted) {
          stream.getTracks().forEach(track => track.stop());
          return;
        }

        kwsMediaStreamRef.current = stream;

        // Create AudioContext
        const audioContext = new AudioContext({
          sampleRate: VOICE_INPUT_SAMPLE_RATE,
        });
        kwsAudioContextRef.current = audioContext;

        // Create AudioWorklet for KWS
        const workletUrl = createKwsWorkletScript();
        await audioContext.audioWorklet.addModule(workletUrl);
        URL.revokeObjectURL(workletUrl);

        if (!isMounted) {
          audioContext.close();
          stream.getTracks().forEach(track => track.stop());
          return;
        }

        const workletNode = new AudioWorkletNode(audioContext, 'kws-processor');
        kwsWorkletNodeRef.current = workletNode;

        // Handle audio chunks - feed to KWS
        workletNode.port.onmessage = event => {
          const { samples } = event.data;
          kwsProcessAudio(new Float32Array(samples));
        };

        // Connect audio pipeline
        const sourceNode = audioContext.createMediaStreamSource(stream);
        kwsSourceNodeRef.current = sourceNode;
        sourceNode.connect(workletNode);

        // Mark KWS as actively listening (mic is open and processing)
        setKwsListening(true);
        logger.info('voice_mode_kws_listening_started', { component: 'useVoiceMode' });

        // Pre-warm WebSocket service in background for lower recording latency.
        // When wake word is detected, the WS is already connected — saves ~100-300ms.
        // Non-blocking: if it fails, startRecording will create a new connection.
        try {
          if (!prewarmedServiceRef.current || !prewarmedServiceRef.current.isConnected) {
            prewarmedServiceRef.current?.dispose();
            const warmService = new VoiceInputService({
              onTranscription: () => {}, // Placeholder — will be rewired in startRecording
              onConnectionChange: () => {},
              onError: () => {},
            });
            await warmService.connect();
            if (isMounted) {
              prewarmedServiceRef.current = warmService;
              logger.debug('voice_mode_ws_prewarmed', { component: 'useVoiceMode' });
            } else {
              warmService.dispose();
            }
          }
        } catch {
          // Non-critical — startRecording will create its own connection
          logger.debug('voice_mode_ws_prewarm_failed', { component: 'useVoiceMode' });
        }
      } catch (err) {
        if (!isMounted) return;

        const error = err instanceof Error ? err : new Error(String(err));
        logger.error('voice_mode_kws_listening_failed', error, { component: 'useVoiceMode' });
        // Don't fail completely - manual trigger still works
      }
    };

    startKwsListening();

    return () => {
      isMounted = false;
      cleanupKwsAudio();
      // Dispose pre-warmed service when leaving listening state
      if (prewarmedServiceRef.current) {
        prewarmedServiceRef.current.dispose();
        prewarmedServiceRef.current = null;
      }
    };
  }, [
    isEnabled,
    meetingCapturing,
    state,
    kwsIsReady,
    isKwsSupported,
    createKwsWorkletScript,
    kwsProcessAudio,
    cleanupKwsAudio,
    setKwsListening,
  ]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      cleanupAudio();
      cleanupKwsAudio();
      cleanupService();
      if (recordingWorkletUrlRef.current) {
        URL.revokeObjectURL(recordingWorkletUrlRef.current);
        recordingWorkletUrlRef.current = null;
      }
    };
  }, [cleanupAudio, cleanupKwsAudio, cleanupService]);

  return {
    isEnabled,
    state,
    isRecording,
    isProcessing,
    isSpeaking,
    isListening,
    isKwsLoading,
    isKwsReady,
    isKwsListening,
    error,
    enable,
    disable,
    toggle,
    startRecording,
    stopRecording,
    onTtsComplete,
    isSupported,
    isKwsSupported,
  };
}
