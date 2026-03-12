'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { AudioQueue, type AudioQueueState } from '@/lib/audio-queue';
import { logger } from '@/lib/logger';
import type { VoiceAudioChunk } from '@/types/chat';

/**
 * useVoicePlayback - Hook for managing voice comment playback.
 *
 * Manages the AudioQueue lifecycle and provides methods for:
 * - Handling voice audio chunks from SSE stream
 * - Stopping playback on user interaction
 * - iOS Safari compatibility (suspension handling)
 * - Auto-cleanup on unmount
 *
 * Usage:
 * ```tsx
 * const { handleVoiceChunk, stopPlayback, isPlaying, isEnabled, isSuspended } = useVoicePlayback();
 *
 * // In SSE handler:
 * case 'voice_audio_chunk':
 *   handleVoiceChunk(chunk.content as VoiceAudioChunk);
 *   break;
 *
 * // On new message or interruption:
 * stopPlayback();
 *
 * // On user interaction (helps iOS resume):
 * recordUserInteraction();
 * ```
 */
export function useVoicePlayback() {
  const audioQueueRef = useRef<AudioQueue | null>(null);
  const { user } = useAuth();
  const [isPlaying, setIsPlaying] = useState(false);
  const [isSuspended, setIsSuspended] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  // User's voice preference
  const isEnabled = user?.voice_enabled ?? false;

  /**
   * Configure callbacks on an AudioQueue instance.
   * Extracted to allow reuse when queue is created by warmupAudio().
   */
  const configureQueueCallbacks = useCallback((queue: AudioQueue) => {
    queue.setOnPlaybackComplete(() => {
      setIsPlaying(false);
    });

    queue.setOnError((err) => {
      logger.error('voice_playback_audio_error', err, { component: 'useVoicePlayback' });
      setError(err);
      setIsPlaying(false);
    });

    // Track state changes for iOS suspension handling
    queue.setOnStateChange((state: AudioQueueState) => {
      logger.debug('voice_playback_state_changed', { state, component: 'useVoicePlayback' });
      setIsPlaying(state === 'playing');
      setIsSuspended(state === 'suspended');
      if (state === 'error') {
        setError(new Error('AudioContext error'));
      }
    });
  }, []);

  // Initialize AudioQueue when voice is enabled
  useEffect(() => {
    if (isEnabled) {
      // Create queue if it doesn't exist
      if (!audioQueueRef.current) {
        audioQueueRef.current = new AudioQueue();
      }

      // Always configure callbacks (in case queue was created by warmupAudio)
      configureQueueCallbacks(audioQueueRef.current);
    }

    // Cleanup on unmount or when disabled
    return () => {
      if (audioQueueRef.current) {
        audioQueueRef.current.dispose();
        audioQueueRef.current = null;
      }
    };
  }, [isEnabled, configureQueueCallbacks]);

  /**
   * Handle a voice audio chunk from SSE stream.
   * Enqueues the audio for playback.
   */
  const handleVoiceChunk = useCallback(
    async (chunk: VoiceAudioChunk) => {
      if (!isEnabled || !audioQueueRef.current) {
        return;
      }

      try {
        setIsPlaying(true);
        setError(null);
        await audioQueueRef.current.enqueue(chunk.audio_base64);
      } catch (err) {
        logger.error('voice_playback_enqueue_failed', err as Error, { component: 'useVoicePlayback' });
        setError(err as Error);
      }
    },
    [isEnabled]
  );

  /**
   * Stop all voice playback immediately.
   * Called on user interaction or context change.
   */
  const stopPlayback = useCallback(() => {
    if (audioQueueRef.current) {
      audioQueueRef.current.stop();
      setIsPlaying(false);
    }
  }, []);

  /**
   * Initialize the AudioQueue (must be called after user gesture).
   */
  const initializeAudio = useCallback(async () => {
    if (audioQueueRef.current) {
      await audioQueueRef.current.initialize();
    }
  }, []);

  /**
   * Warm up the audio system for iOS.
   * CRITICAL: Must be called during a user gesture (click/tap).
   * Plays a silent buffer to "unlock" iOS audio system.
   *
   * Call this when:
   * - User enables voice preference
   * - User first interacts after inactivity period
   *
   * @returns true if warmup was successful
   */
  const warmupAudio = useCallback(async (): Promise<boolean> => {
    if (!audioQueueRef.current) {
      // Create queue if it doesn't exist (voice may have just been enabled)
      const queue = new AudioQueue();
      audioQueueRef.current = queue;
    }
    return audioQueueRef.current.warmup();
  }, []);

  /**
   * Record user interaction to help iOS resume suspended audio.
   * Should be called on any user gesture (tap, click, keypress).
   * This helps iOS Safari resume the AudioContext.
   */
  const recordUserInteraction = useCallback(() => {
    if (audioQueueRef.current) {
      audioQueueRef.current.recordUserInteraction();
    }
  }, []);

  /**
   * Resume playback after iOS suspension.
   * Must be called in response to user gesture.
   * Returns true if playback was successfully resumed.
   */
  const resumePlayback = useCallback(async (): Promise<boolean> => {
    if (audioQueueRef.current) {
      const resumed = await audioQueueRef.current.resumePlayback();
      if (resumed) {
        setIsSuspended(false);
      }
      return resumed;
    }
    return false;
  }, []);

  return {
    handleVoiceChunk,
    stopPlayback,
    initializeAudio,
    warmupAudio,
    recordUserInteraction,
    resumePlayback,
    isPlaying,
    isEnabled,
    isSuspended,
    error,
  };
}
