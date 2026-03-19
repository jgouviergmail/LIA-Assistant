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
import { useSherpaKws } from '@/hooks/useSherpaKws';
import { isSherpaKwsSupported } from '@/lib/audio/sherpaKws';
import { useVoiceModeStore, type VoiceModeState } from '@/stores/voiceModeStore';
import {
  VOICE_INPUT_SAMPLE_RATE,
  VOICE_INPUT_CHUNK_SIZE,
  VOICE_MODE_MAX_RECORDING_SECONDS,
} from '@/lib/constants';

// ============================================================================
// Types
// ============================================================================

export interface UseVoiceModeOptions {
  /** Callback when transcription is received */
  onTranscription?: (text: string) => void;
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
    (text: string, duration: number) => {
      logger.info('voice_mode_transcription_received', {
        component: 'useVoiceMode',
        text_length: text.length,
        duration_seconds: duration,
      });

      // Clean up service
      cleanupService();

      if (text.trim()) {
        // Send transcription to parent
        onTranscription?.(text);

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
      if (!connected && state === 'processing') {
        const err = new Error('Connection lost during transcription');
        logger.warn('voice_mode_connection_lost', { component: 'useVoiceMode' });
        setError(err);
        onError?.(err);
        cleanupService();
        setState('listening');
      }
    },
    [state, setError, onError, cleanupService, setState]
  );

  /**
   * Handle error.
   */
  const handleError = useCallback(
    (err: Error) => {
      logger.error('voice_mode_error', err, { component: 'useVoiceMode' });
      setError(err);
      onError?.(err);
      cleanupAudio();
      cleanupService();
      setState('listening');
    },
    [setError, onError, cleanupAudio, cleanupService, setState]
  );

  /**
   * Ref to hold startRecording function for KWS callback.
   * This avoids circular dependency between handleKeywordDetected and startRecording.
   */
  const startRecordingRef = useRef<(() => Promise<void>) | null>(null);

  /**
   * Handle wake word detection from KWS.
   * Triggered when user says "OK" (universal wake word).
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

      // Notify callback
      onWakeWordDetected?.(keyword);

      // Stop KWS audio and start recording
      cleanupKwsAudio();

      // Start recording via ref (set after startRecording is defined)
      startRecordingRef.current?.();
    },
    [state, recordWakeWord, onWakeWordDetected, cleanupKwsAudio]
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
    enabled: isEnabled && isKwsSupported,
    onError: handleKwsError,
  });

  // Sync KWS state to store
  useEffect(() => {
    setKwsReady(kwsIsReady);
    setKwsLoading(kwsIsLoading);
  }, [kwsIsReady, kwsIsLoading, setKwsReady, setKwsLoading]);

  /**
   * Create AudioWorklet processor script.
   */
  const createWorkletScript = useCallback((): string => {
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
    return URL.createObjectURL(blob);
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
   * Start recording.
   */
  const startRecording = useCallback(async () => {
    if (!isSupported) {
      handleError(new Error('Voice input is not supported in this browser'));
      return;
    }

    if (isStartingRef.current || state === 'recording' || state === 'processing') {
      return;
    }

    isStartingRef.current = true;

    try {
      cleanupService();
      cleanupAudio();

      // Step 1: Get microphone
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

      // Step 2: Create WebSocket service
      const service = new VoiceInputService({
        onTranscription: handleTranscription,
        onConnectionChange: handleConnectionChange,
        onError: handleError,
      });
      serviceRef.current = service;
      await service.connect();

      // Step 3: Create AudioContext
      const audioContext = new AudioContext({
        sampleRate: VOICE_INPUT_SAMPLE_RATE,
      });
      audioContextRef.current = audioContext;

      // Step 4: Create VAD
      // Use ref wrapper to avoid stale closure issue - VAD captures the callback at creation
      // time but we need it to always call the latest handleSpeechEnd
      vadRef.current = new VoiceActivityDetector(
        {},
        { onSpeechEnd: () => handleSpeechEndRef.current?.() }
      );

      // Step 5: Create AudioWorklet
      const workletUrl = createWorkletScript();
      await audioContext.audioWorklet.addModule(workletUrl);
      URL.revokeObjectURL(workletUrl);

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
        stopRecording();
      }, VOICE_MODE_MAX_RECORDING_SECONDS * 1000);

      setState('recording');
      isStartingRef.current = false;

      logger.info('voice_mode_recording_started', { component: 'useVoiceMode' });
    } catch (err) {
      isStartingRef.current = false;
      const error = err instanceof Error ? err : new Error(String(err));

      if (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError') {
        handleError(new Error('Microphone permission denied'));
      } else {
        handleError(error);
      }
    }
    // stopRecording is intentionally omitted - it's defined after this callback
    // and captured at runtime via closure when setTimeout executes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    isSupported,
    state,
    cleanupService,
    cleanupAudio,
    handleTranscription,
    handleConnectionChange,
    handleError,
    createWorkletScript,
    setState,
  ]);

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
    if (!isEnabled || state !== 'listening' || !kwsIsReady || !isKwsSupported) {
      logger.debug('voice_mode_kws_effect_skip', {
        component: 'useVoiceMode',
        isEnabled,
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
    };
  }, [
    isEnabled,
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
