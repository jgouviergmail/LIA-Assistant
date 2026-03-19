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
import { VOICE_INPUT_SAMPLE_RATE, VOICE_INPUT_CHUNK_SIZE } from '@/lib/constants';

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
   * Create AudioWorklet processor script as a Blob URL.
   * This allows us to create the worklet inline without a separate file.
   */
  const createWorkletScript = useCallback((): string => {
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
    return URL.createObjectURL(blob);
  }, []);

  /**
   * Start recording.
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
    setError(null);
    setTranscription(null);
    setDurationSeconds(null);
    setState('connecting');

    try {
      // Clean up any existing service before creating new one (prevents memory leak)
      cleanupService();

      // Step 1: Request microphone permission
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: VOICE_INPUT_SAMPLE_RATE,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      mediaStreamRef.current = stream;

      logger.debug('voice_input_mic_granted', { component: 'useVoiceInput' });

      // Step 2: Create VoiceInputService and connect
      const service = new VoiceInputService({
        onTranscription: handleTranscription,
        onConnectionChange: handleConnectionChange,
        onError: handleError,
      });
      serviceRef.current = service;

      await service.connect();

      // Step 3: Set up AudioContext with resampling if needed
      const audioContext = new AudioContext({
        sampleRate: VOICE_INPUT_SAMPLE_RATE,
      });
      audioContextRef.current = audioContext;

      // Step 4: Create AudioWorklet
      const workletUrl = createWorkletScript();
      await audioContext.audioWorklet.addModule(workletUrl);
      URL.revokeObjectURL(workletUrl);

      const workletNode = new AudioWorkletNode(audioContext, 'voice-input-processor');
      workletNodeRef.current = workletNode;

      // Step 5: Handle audio chunks from worklet
      workletNode.port.onmessage = event => {
        const audioBuffer = event.data as ArrayBuffer;
        service.sendAudio(audioBuffer);
      };

      // Step 6: Connect audio pipeline
      const sourceNode = audioContext.createMediaStreamSource(stream);
      sourceNodeRef.current = sourceNode;
      sourceNode.connect(workletNode);

      // Start recording
      setState('recording');
      isStartingRef.current = false;

      logger.info('voice_input_recording_started', { component: 'useVoiceInput' });
    } catch (err) {
      isStartingRef.current = false;

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
    }
  }, [
    isSupported,
    state,
    handleTranscription,
    handleConnectionChange,
    handleError,
    createWorkletScript,
    cleanupAudio,
    cleanupService,
  ]);

  /**
   * Stop recording and request transcription.
   */
  const stopRecording = useCallback(() => {
    if (state !== 'recording') {
      return;
    }

    setState('processing');

    // Signal end of audio
    serviceRef.current?.endAudio();

    // Clean up audio resources (service cleaned up after transcription)
    cleanupAudio();

    logger.info('voice_input_recording_stopped', { component: 'useVoiceInput' });
  }, [state, cleanupAudio]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      cleanupAudio();
      cleanupService();
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
