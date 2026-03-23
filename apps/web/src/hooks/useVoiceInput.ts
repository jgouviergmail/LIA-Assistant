'use client';

/**
 * useVoiceInput - Hook for voice input recording and transcription.
 *
 * Manages the complete voice input lifecycle:
 * - Microphone permission handling
 * - Audio recording with Web Audio API
 * - Real-time streaming to backend via WebSocket
 * - Transcription result handling
 *
 * Usage:
 * ```tsx
 * const {
 *   isRecording,
 *   isConnected,
 *   isProcessing,
 *   error,
 *   startRecording,
 *   stopRecording,
 *   transcription,
 * } = useVoiceInput({
 *   onTranscription: (text) => setMessage(text),
 * });
 *
 * <button onClick={isRecording ? stopRecording : startRecording}>
 *   {isRecording ? 'Stop' : 'Record'}
 * </button>
 * ```
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { logger } from '@/lib/logger';
import { VoiceInputService } from '@/lib/voice-input-service';
import {
  VOICE_INPUT_SAMPLE_RATE,
  VOICE_INPUT_CHUNK_SIZE,
  VOICE_RECORDING_SETUP_TIMEOUT_MS,
} from '@/lib/constants';

// ============================================================================
// Types
// ============================================================================

export type VoiceInputState = 'idle' | 'connecting' | 'recording' | 'processing';

export interface UseVoiceInputOptions {
  /** Callback when transcription is received */
  onTranscription?: (text: string) => void;
  /** Callback when error occurs */
  onError?: (error: Error) => void;
}

export interface UseVoiceInputReturn {
  /** Current voice input state */
  state: VoiceInputState;
  /** Whether currently recording */
  isRecording: boolean;
  /** Whether WebSocket is connected */
  isConnected: boolean;
  /** Whether processing transcription */
  isProcessing: boolean;
  /** Current error (if any) */
  error: Error | null;
  /** Last transcription result */
  transcription: string | null;
  /** Last audio duration in seconds */
  durationSeconds: number | null;
  /** Start recording */
  startRecording: () => Promise<void>;
  /** Stop recording and process */
  stopRecording: () => void;
  /** Check if microphone is supported */
  isSupported: boolean;
}

// ============================================================================
// Hook Implementation
// ============================================================================

export function useVoiceInput(options: UseVoiceInputOptions = {}): UseVoiceInputReturn {
  const { onTranscription, onError } = options;

  // Service and audio refs
  const serviceRef = useRef<VoiceInputService | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);

  // Ref to prevent race conditions on rapid clicks
  const isStartingRef = useRef(false);

  // Ref to signal cancellation when user releases button during async setup
  const cancelledRef = useRef(false);

  // Cached worklet blob URL (created once, reused across recordings)
  const workletUrlRef = useRef<string | null>(null);

  // Pre-warmed VoiceInputService (connected in background for lower latency)
  const prewarmedServiceRef = useRef<VoiceInputService | null>(null);

  // State
  const [state, setState] = useState<VoiceInputState>('idle');
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [transcription, setTranscription] = useState<string | null>(null);
  const [durationSeconds, setDurationSeconds] = useState<number | null>(null);

  // Derived states
  const isRecording = state === 'recording';
  const isProcessing = state === 'processing';

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
    // Disconnect nodes
    if (sourceNodeRef.current) {
      sourceNodeRef.current.disconnect();
      sourceNodeRef.current = null;
    }

    if (workletNodeRef.current) {
      workletNodeRef.current.disconnect();
      workletNodeRef.current = null;
    }

    // Stop media stream tracks
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach(track => track.stop());
      mediaStreamRef.current = null;
    }

    // Close audio context
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {
        // Ignore errors on close
      });
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
   * Handle transcription result from WebSocket.
   */
  const handleTranscription = useCallback(
    (text: string, duration: number) => {
      setTranscription(text);
      setDurationSeconds(duration);
      setState('idle');

      // Clean up service after receiving transcription
      cleanupService();

      logger.info('voice_input_transcription_received', {
        component: 'useVoiceInput',
        text_length: text.length,
        duration_seconds: duration,
      });

      onTranscription?.(text);
    },
    [onTranscription, cleanupService]
  );

  /**
   * Handle connection state change.
   * If connection is lost while processing, reset state with error.
   */
  const handleConnectionChange = useCallback(
    (connected: boolean) => {
      setIsConnected(connected);

      // If connection lost during 'processing', the transcription is lost
      // Reset to idle with an error to unblock the user
      if (!connected) {
        setState(currentState => {
          if (currentState === 'processing') {
            const connectionError = new Error('Connection lost during transcription');

            logger.warn('voice_input_connection_lost_during_processing', {
              component: 'useVoiceInput',
            });

            // Clean up service since we can't recover
            if (serviceRef.current) {
              serviceRef.current.dispose();
              serviceRef.current = null;
            }

            setError(connectionError);
            onError?.(connectionError);
            return 'idle';
          }
          return currentState;
        });
      }
    },
    [onError]
  );

  /**
   * Handle error.
   */
  const handleError = useCallback(
    (err: Error) => {
      setError(err);
      setState('idle');

      logger.error('voice_input_error', err, { component: 'useVoiceInput' });

      onError?.(err);
    },
    [onError]
  );

  /**
   * Get or create AudioWorklet processor script as a cached Blob URL.
   * The worklet code is identical across recordings, so we cache the URL.
   */
  const getOrCreateWorkletUrl = useCallback((): string => {
    if (workletUrlRef.current) return workletUrlRef.current;

    const workletCode = `
      class VoiceInputProcessor extends AudioWorkletProcessor {
        constructor() {
          super();
          this.buffer = [];
          this.chunkSize = ${VOICE_INPUT_CHUNK_SIZE};
        }

        process(inputs) {
          const input = inputs[0];
          if (input.length > 0) {
            const samples = input[0];

            // Accumulate samples
            for (let i = 0; i < samples.length; i++) {
              this.buffer.push(samples[i]);
            }

            // Send chunk when buffer is full
            while (this.buffer.length >= this.chunkSize) {
              const chunk = this.buffer.splice(0, this.chunkSize);

              // Convert Float32 [-1, 1] to Int16 [-32768, 32767]
              const int16Array = new Int16Array(chunk.length);
              for (let i = 0; i < chunk.length; i++) {
                const s = Math.max(-1, Math.min(1, chunk[i]));
                int16Array[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
              }

              this.port.postMessage(int16Array.buffer, [int16Array.buffer]);
            }
          }
          return true;
        }
      }

      registerProcessor('voice-input-processor', VoiceInputProcessor);
    `;

    const blob = new Blob([workletCode], { type: 'application/javascript' });
    workletUrlRef.current = URL.createObjectURL(blob);
    return workletUrlRef.current;
  }, []);

  /**
   * Start recording.
   *
   * Launches getUserMedia and WebSocket connection in parallel for reduced latency.
   * Supports cancellation via cancelledRef (set by stopRecording during 'connecting' state).
   */
  const startRecording = useCallback(async () => {
    if (!isSupported) {
      const err = new Error('Voice input is not supported in this browser');
      handleError(err);
      return;
    }

    // Guard against race conditions (double-click)
    if (isStartingRef.current || state !== 'idle') {
      logger.warn('voice_input_already_active', {
        component: 'useVoiceInput',
        state,
        isStarting: isStartingRef.current,
      });
      return;
    }

    isStartingRef.current = true;
    cancelledRef.current = false;
    setError(null);
    setTranscription(null);
    setDurationSeconds(null);
    setState('connecting');

    try {
      // Clean up any existing service before creating new one (prevents memory leak)
      cleanupService();

      // Step 1: Reuse pre-warmed WS service or create new one
      let service: VoiceInputService;
      const prewarmed = prewarmedServiceRef.current;
      prewarmedServiceRef.current = null;

      if (prewarmed && prewarmed.isConnected) {
        service = prewarmed;
        service.updateCallbacks({
          onTranscription: handleTranscription,
          onConnectionChange: handleConnectionChange,
          onError: handleError,
        });
        logger.debug('voice_input_service_prewarmed', { component: 'useVoiceInput' });
      } else {
        prewarmed?.dispose();
        service = new VoiceInputService({
          onTranscription: handleTranscription,
          onConnectionChange: handleConnectionChange,
          onError: handleError,
        });
      }
      serviceRef.current = service;

      // Step 2: Launch mic (+ WS if not pre-warmed) in parallel with timeout
      const connectIfNeeded = service.isConnected
        ? Promise.resolve()
        : service.connect();

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

      const timeoutPromise = new Promise<never>((_, reject) => {
        setTimeout(
          () => reject(new Error('Voice recording setup timed out')),
          VOICE_RECORDING_SETUP_TIMEOUT_MS,
        );
      });

      const [streamResult, connectResult] = await Promise.race([
        setupPromise,
        timeoutPromise,
      ]) as [PromiseSettledResult<MediaStream>, PromiseSettledResult<void>];

      // Handle partial failures - clean up whatever succeeded
      if (streamResult.status === 'rejected' || connectResult.status === 'rejected') {
        // Explicitly stop stream tracks if mic was obtained but WS failed
        if (streamResult.status === 'fulfilled') {
          streamResult.value.getTracks().forEach(track => track.stop());
        }
        // Service cleanup happens in outer catch via cleanupService()
        const reason =
          streamResult.status === 'rejected'
            ? streamResult.reason
            : (connectResult as PromiseRejectedResult).reason;
        throw reason instanceof Error ? reason : new Error(String(reason));
      }

      // Both succeeded - assign refs
      const stream = streamResult.value;
      mediaStreamRef.current = stream;

      logger.debug('voice_input_mic_and_ws_ready', { component: 'useVoiceInput' });

      // Check if user cancelled during async setup (released button early)
      if (cancelledRef.current) {
        logger.info('voice_input_cancelled_during_setup', { component: 'useVoiceInput' });
        cleanupAudio();
        cleanupService();
        setState('idle');
        return;
      }

      // Step 2: Set up AudioContext with resampling if needed
      const audioContext = new AudioContext({
        sampleRate: VOICE_INPUT_SAMPLE_RATE,
      });
      audioContextRef.current = audioContext;

      // Step 3: Create AudioWorklet (uses cached blob URL)
      await audioContext.audioWorklet.addModule(getOrCreateWorkletUrl());

      const workletNode = new AudioWorkletNode(audioContext, 'voice-input-processor');
      workletNodeRef.current = workletNode;

      // Step 4: Handle audio chunks from worklet
      workletNode.port.onmessage = event => {
        const audioBuffer = event.data as ArrayBuffer;
        service.sendAudio(audioBuffer);
      };

      // Step 5: Connect audio pipeline
      const sourceNode = audioContext.createMediaStreamSource(stream);
      sourceNodeRef.current = sourceNode;
      sourceNode.connect(workletNode);

      // Start recording
      setState('recording');

      logger.info('voice_input_recording_started', { component: 'useVoiceInput' });
    } catch (err) {
      // Clean up on error
      cleanupAudio();
      cleanupService();

      const error = err instanceof Error ? err : new Error(String(err));

      // Provide user-friendly error for permission denied
      if (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError') {
        handleError(new Error('Microphone permission denied'));
      } else {
        handleError(error);
      }
    } finally {
      isStartingRef.current = false;
    }
  }, [
    isSupported,
    state,
    handleTranscription,
    handleConnectionChange,
    handleError,
    getOrCreateWorkletUrl,
    cleanupAudio,
    cleanupService,
  ]);

  /**
   * Stop recording and request transcription, or cancel in-progress startup.
   *
   * Handles multiple states:
   * - 'idle': noop (safe to call unconditionally)
   * - 'connecting': cancel async startup via cancelledRef
   * - 'recording': stop recording and send audio for transcription
   * - 'processing': noop (already processing)
   */
  const stopRecording = useCallback(() => {
    if (state === 'recording') {
      // Normal stop - send audio for transcription
      setState('processing');
      serviceRef.current?.endAudio();
      cleanupAudio();
      logger.info('voice_input_recording_stopped', { component: 'useVoiceInput' });
    } else if (state === 'connecting') {
      // Cancel in-progress startup (user released button before recording started)
      cancelledRef.current = true;
      setState('idle');
      logger.info('voice_input_startup_cancelled', { component: 'useVoiceInput' });
    }
    // 'idle' and 'processing' states: noop
  }, [state, cleanupAudio]);

  // Pre-warm WebSocket connection in background when idle.
  // This acquires a ticket and opens the WS ahead of time so that
  // when the user presses the push-to-talk button, the connection is ready.
  useEffect(() => {
    // Only pre-warm when idle (ready for next recording) and supported
    if (state !== 'idle' || !isSupported) return;

    let isMounted = true;

    const prewarm = async () => {
      // Skip if already pre-warmed
      if (prewarmedServiceRef.current?.isConnected) return;

      // Dispose stale service
      prewarmedServiceRef.current?.dispose();
      prewarmedServiceRef.current = null;

      try {
        const warmService = new VoiceInputService({
          onTranscription: () => {},
          onConnectionChange: () => {},
          onError: () => {},
        });

        await warmService.connect();

        if (isMounted) {
          prewarmedServiceRef.current = warmService;
          logger.debug('voice_input_ws_prewarmed', { component: 'useVoiceInput' });
        } else {
          warmService.dispose();
        }
      } catch {
        // Non-critical — startRecording will create its own connection
        logger.debug('voice_input_ws_prewarm_failed', { component: 'useVoiceInput' });
      }
    };

    prewarm();

    return () => {
      isMounted = false;
    };
  }, [state, isSupported]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      cleanupAudio();
      cleanupService();
      if (prewarmedServiceRef.current) {
        prewarmedServiceRef.current.dispose();
        prewarmedServiceRef.current = null;
      }
      if (workletUrlRef.current) {
        URL.revokeObjectURL(workletUrlRef.current);
        workletUrlRef.current = null;
      }
    };
  }, [cleanupAudio, cleanupService]);

  return {
    state,
    isRecording,
    isConnected,
    isProcessing,
    error,
    transcription,
    durationSeconds,
    startRecording,
    stopRecording,
    isSupported,
  };
}
