'use client';

/**
 * useVoiceMode - Main orchestration hook for Voice Mode.
 *
 * Manages the complete voice mode lifecycle:
 * 1. Wake word detection in the person's language (`useWakeWord`, ADR-329)
 * 2. Audio recording with VAD
 * 3. WebSocket streaming for STT
 * 4. Transcription callback
 *
 * State Machine:
 * - idle: Voice mode disabled, text input active
 * - listening: Listening for the wake phrase
 * - recording: Recording user speech with VAD
 * - processing: STT transcription in progress
 * - speaking: TTS playing response (managed externally)
 *
 * Flow:
 * 1. User enables voice mode → state = "listening"
 * 2. User says the phrase (« Dis LIA ») → detected → state = "recording"
 * 3. User speaks → VAD detects end of speech → state = "processing"
 * 4. STT transcribes → callback triggered → state = "speaking"
 * 5. TTS plays response → onTtsComplete() → state = "listening"
 *
 * While LIA reads an answer aloud, the person may talk over her: the phrase
 * cuts her voice and records the next request, the stop word (« Stop ») cuts
 * her voice and nothing else — no recording, no transcription, no message
 * (`onInterrupt`, ADR-329 amendment 2026-10-01).
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
import { useTranslation } from 'react-i18next';
import { logger } from '@/lib/logger';
import { VoiceInputService } from '@/lib/voice-input-service';
import { VoiceActivityDetector } from '@/lib/audio/vad';
import { playReadyChime } from '@/lib/audio/ready-chime';
import { useWakeWord } from '@/hooks/useWakeWord';
import type { WakeCommand } from '@/lib/audio/wake-word/commands';
import type { WakeListenerState } from '@/lib/audio/wake-word/listener';
import { stopWordOf } from '@/lib/audio/wake-word/phrases';
import { useVoiceModeStore, type VoiceModeState } from '@/stores/voiceModeStore';
import { useLiveHoldsMicrophone } from '@/stores/liveStore';
import { useRadioHoldsAudio } from '@/stores/radioStore';
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
  /** The person spoke over LIA — her phrase, before the recording opens, or the
   *  stop word: the chat cuts her voice (she stops, the person is heard). */
  onInterrupt?: () => void;
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
  /** The wake word's own state: its model loading, its microphone listening, or unavailable */
  wakeWordState: WakeListenerState;
  /** The phrase the loaded model listens for (null until one is loaded) */
  wakePhrase: string | null;
  /** The word that cuts LIA's voice, when the loaded model ships it (null otherwise) */
  stopWord: string | null;
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
}

// ============================================================================
// Recording microphone
// ============================================================================

/** Stop a stream nobody will record from (a handed one included): no microphone left live. */
function releaseStream(stream: MediaStream | undefined): void {
  stream?.getTracks().forEach(track => track.stop());
}

/**
 * The recording's microphone, with the WebSocket connected.
 *
 * A live stream handed over (the wake word's) is used as is — no permission
 * round trip, ~200-800 ms saved — and only the connection is awaited. An
 * inactive one is released. Otherwise the microphone and the connection are
 * asked for in parallel, raced against the setup timeout; a partial success is
 * undone (an acquired stream is stopped) and the first failure is thrown.
 *
 * @param handed A stream handed over by the wake word, if any.
 * @param service The recording's WebSocket service.
 * @param timeout Rejects once the setup took too long.
 * @returns The stream to record from.
 */
async function acquireRecordingStream(
  handed: MediaStream | undefined,
  service: VoiceInputService,
  timeout: Promise<never>
): Promise<MediaStream> {
  if (handed?.active) {
    if (!service.isConnected) {
      try {
        await Promise.race([service.connect(), timeout]);
      } catch (error) {
        releaseStream(handed);
        throw error;
      }
    }
    logger.debug('voice_mode_stream_reused', { component: 'useVoiceMode' });
    return handed;
  }
  // An inactive stream handed over is released (safety).
  releaseStream(handed);

  const connectIfNeeded = service.isConnected ? Promise.resolve() : service.connect();
  const setup = Promise.allSettled([
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
  const [streamResult, connectResult] = (await Promise.race([setup, timeout])) as [
    PromiseSettledResult<MediaStream>,
    PromiseSettledResult<void>,
  ];
  if (streamResult.status === 'fulfilled' && connectResult.status === 'fulfilled') {
    return streamResult.value;
  }
  if (streamResult.status === 'fulfilled') {
    streamResult.value.getTracks().forEach(track => track.stop());
  }
  const reason =
    streamResult.status === 'rejected'
      ? streamResult.reason
      : (connectResult as PromiseRejectedResult).reason;
  throw reason instanceof Error ? reason : new Error(String(reason));
}

// ============================================================================
// Hook Implementation
// ============================================================================

export function useVoiceMode(options: UseVoiceModeOptions = {}): UseVoiceModeReturn {
  const { onTranscription, onStartSpeaking, onStopSpeaking, onError, onInterrupt } = options;
  const { i18n } = useTranslation();
  // ADR-258: one microphone owner at a time — the wake-word detector and its
  // listening loop pause while a meeting records or a live session runs
  // (ADR-299), and resume by themselves. The radio (ADR-324) holds the
  // SPEAKERS, not the microphone — but a wake word its host says must never
  // wake the assistant, so the detector stands aside for it too.
  const meetingCapturing = useMeetingIsCapturing();
  const liveCapturing = useLiveHoldsMicrophone();
  const radioOnAir = useRadioHoldsAudio();
  const microphoneTaken = meetingCapturing || liveCapturing || radioOnAir;

  // Store state
  const {
    isEnabled,
    state,
    error,
    enable: storeEnable,
    disable: storeDisable,
    setState,
    setError,
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
   * Ref to hold startRecording for the wake-word detection handler.
   * This avoids circular dependency between handleWakeWordDetected and startRecording.
   */
  const startRecordingRef = useRef<((existingStream?: MediaStream) => Promise<void>) | null>(null);

  /**
   * The wake word's live stream, handed to the recording that follows a
   * detection (or a tap while it listens): no second permission round trip,
   * ~200-800 ms saved. Read through a ref because the detection handler is
   * declared before the hook that owns the stream.
   */
  const wakeHandOffRef = useRef<() => Promise<MediaStream | null>>(async () => null);

  /**
   * Handle a wake-word detection: the detector's microphone becomes the
   * recording's.
   */
  const handleWakeWordDetected = useCallback(async () => {
    // Ignore a detection outside the listening state (safety check)
    if (state !== 'listening') {
      logger.debug('voice_mode_wake_word_ignored', {
        component: 'useVoiceMode',
        reason: 'not_listening',
        currentState: state,
      });
      return;
    }

    logger.info('voice_mode_wake_word_detected', { component: 'useVoiceMode' });
    onInterrupt?.();
    recordWakeWord();
    // Mark as wake-word-triggered so startRecording plays the ready chime
    wakeWordTriggeredRef.current = true;
    const stream = await wakeHandOffRef.current();
    startRecordingRef.current?.(stream ?? undefined);
  }, [state, recordWakeWord, onInterrupt]);

  /** A spoken command: « Stop » cuts LIA's voice and is never a request of its own. */
  const handleCommand = useCallback(
    (command: WakeCommand) => {
      logger.info('voice_mode_command_heard', { component: 'useVoiceMode', command });
      onInterrupt?.();
    },
    [onInterrupt]
  );

  // The wake word listens only while the mode waits for the person, and stands
  // aside while another feature holds the microphone (ADR-258).
  const wake = useWakeWord({
    language: i18n.language,
    enabled: isEnabled && !microphoneTaken && state === 'listening',
    onDetected: handleWakeWordDetected,
    onCommand: handleCommand,
  });
  const wakeHandOff = wake.handOff;
  const wakeAvailable = wake.state !== 'unavailable';

  useEffect(() => {
    wakeHandOffRef.current = wakeHandOff;
  }, [wakeHandOff]);

  useEffect(() => {
    // Push-to-talk still works: a refused microphone only loses the phrase.
    if (wake.error) {
      logger.warn('voice_mode_wake_word_microphone_failed', {
        component: 'useVoiceMode',
        error: wake.error.name,
      });
    }
  }, [wake.error]);

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
   *   when the wake word hands its mic stream over)
   * - Parallelizes getUserMedia + WS connect via Promise.allSettled
   * - Uses cached worklet blob URL (avoids Blob creation each time)
   *
   * @param existingStream Optional MediaStream to reuse (from the wake-word flow)
   */
  const startRecording = useCallback(
    async (existingStream?: MediaStream) => {
      if (!isSupported) {
        releaseStream(existingStream);
        handleError(new Error('Voice input is not supported in this browser'));
        return;
      }

      if (isStartingRef.current || state === 'recording' || state === 'processing') {
        // A stream handed for a start that will not happen is no one's: stop it.
        releaseStream(existingStream);
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

        // A tap while the wake word listens takes its live stream too.
        const handed = existingStream ?? (await wakeHandOffRef.current()) ?? undefined;
        const stream = await acquireRecordingStream(handed, service, timeoutPromise);

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
    cleanupService();
    // Dispose pre-warmed service
    if (prewarmedServiceRef.current) {
      prewarmedServiceRef.current.dispose();
      prewarmedServiceRef.current = null;
    }
    storeDisable();
    logger.info('voice_mode_disabled', { component: 'useVoiceMode' });
  }, [cleanupAudio, cleanupService, storeDisable]);

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

  // Set startRecording ref for the wake-word detection handler
  useEffect(() => {
    startRecordingRef.current = startRecording;
  }, [startRecording]);

  /**
   * Pre-warm the WebSocket service while the wake word waits: when the phrase
   * is detected, the WS is already connected — saves ~100-300 ms. Keyed on the
   * MODE's state, not the detector's: the detection hands the microphone over
   * (the detector goes idle) before the recording takes this service, and a
   * cleanup on that change would dispose it in between.
   */
  useEffect(() => {
    if (!isEnabled || microphoneTaken || state !== 'listening' || !wakeAvailable) return;

    let isMounted = true;
    const prewarm = async () => {
      try {
        if (!prewarmedServiceRef.current || !prewarmedServiceRef.current.isConnected) {
          prewarmedServiceRef.current?.dispose();
          const warmService = new VoiceInputService({
            onTranscription: () => {}, // Placeholder — rewired in startRecording
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
    };
    void prewarm();

    return () => {
      isMounted = false;
      // Dispose the pre-warmed service when leaving the listening state
      if (prewarmedServiceRef.current) {
        prewarmedServiceRef.current.dispose();
        prewarmedServiceRef.current = null;
      }
    };
  }, [isEnabled, microphoneTaken, state, wakeAvailable]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      cleanupAudio();
      cleanupService();
      if (recordingWorkletUrlRef.current) {
        URL.revokeObjectURL(recordingWorkletUrlRef.current);
        recordingWorkletUrlRef.current = null;
      }
    };
  }, [cleanupAudio, cleanupService]);

  return {
    isEnabled,
    state,
    isRecording,
    isProcessing,
    isSpeaking,
    isListening,
    wakeWordState: wake.state,
    wakePhrase: wake.phrase,
    stopWord: wake.commands.includes('stop') ? stopWordOf(i18n.language) : null,
    error,
    enable,
    disable,
    toggle,
    startRecording,
    stopRecording,
    onTtsComplete,
    isSupported,
  };
}
