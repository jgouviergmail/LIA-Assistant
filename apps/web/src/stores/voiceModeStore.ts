'use client';

/**
 * Zustand store for Voice Mode state management.
 *
 * Manages global voice mode state across the application:
 * - Voice mode enabled/disabled toggle
 * - Current voice state (idle, listening, recording, processing, speaking)
 * - Wake word detection status
 * - Error handling
 *
 * Persists enabled preference to localStorage.
 *
 * Reference: plan zippy-drifting-valley.md (section 2.2)
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { VOICE_MODE_ENABLED_KEY } from '@/lib/constants';

// ============================================================================
// Types
// ============================================================================

/**
 * Voice mode states following the state machine pattern.
 *
 * State transitions:
 * - idle → listening (user enables voice mode)
 * - listening → recording (wake word detected)
 * - recording → processing (VAD detects end of speech)
 * - processing → speaking (transcription + LLM complete, TTS playing)
 * - speaking → listening (TTS complete, back to wake word detection)
 * - any → idle (user disables voice mode or error)
 */
export type VoiceModeState =
  | 'idle'       // Voice mode disabled, text input mode
  | 'listening'  // Listening for wake word
  | 'recording'  // Wake word detected, recording user speech
  | 'processing' // Processing speech (STT + LLM)
  | 'speaking';  // TTS playing response

/**
 * Voice mode store state interface.
 */
export interface VoiceModeStore {
  // State
  /** Whether voice mode is enabled (persisted) */
  isEnabled: boolean;
  /** Current voice mode state */
  state: VoiceModeState;
  /** Whether KWS (Keyword Spotting) is ready */
  isKwsReady: boolean;
  /** Whether KWS is loading */
  isKwsLoading: boolean;
  /** Whether KWS microphone is actively listening (mic open + processing) */
  isKwsListening: boolean;
  /** Last error (if any) */
  error: Error | null;
  /** Last detected wake word timestamp */
  lastWakeWordTime: number | null;

  // Actions
  /** Enable voice mode */
  enable: () => void;
  /** Disable voice mode */
  disable: () => void;
  /** Toggle voice mode */
  toggle: () => void;
  /** Set current state */
  setState: (state: VoiceModeState) => void;
  /** Set KWS ready status */
  setKwsReady: (ready: boolean) => void;
  /** Set KWS loading status */
  setKwsLoading: (loading: boolean) => void;
  /** Set KWS listening status (mic actually open) */
  setKwsListening: (listening: boolean) => void;
  /** Set error */
  setError: (error: Error | null) => void;
  /** Record wake word detection */
  recordWakeWord: () => void;
  /** Reset to idle state */
  reset: () => void;
}

// ============================================================================
// Store Implementation
// ============================================================================

/**
 * Zustand store for voice mode.
 *
 * Uses persist middleware to save enabled preference to localStorage.
 *
 * Usage:
 * ```tsx
 * const { isEnabled, state, enable, disable } = useVoiceModeStore();
 * ```
 */
export const useVoiceModeStore = create<VoiceModeStore>()(
  persist(
    (set: (partial: Partial<VoiceModeStore> | ((state: VoiceModeStore) => Partial<VoiceModeStore>)) => void) => ({
      // Initial state
      isEnabled: false,
      state: 'idle' as VoiceModeState,
      isKwsReady: false,
      isKwsLoading: false,
      isKwsListening: false,
      error: null,
      lastWakeWordTime: null,

      // Actions
      enable: () => set({ isEnabled: true, state: 'listening', error: null }),

      disable: () => set({ isEnabled: false, state: 'idle', error: null, isKwsListening: false }),

      toggle: () =>
        set((s: VoiceModeStore) => ({
          isEnabled: !s.isEnabled,
          state: !s.isEnabled ? 'listening' : 'idle',
          error: null,
        })),

      setState: (newState: VoiceModeState) => set({ state: newState }),

      setKwsReady: (ready: boolean) => set({ isKwsReady: ready }),

      setKwsLoading: (loading: boolean) => set({ isKwsLoading: loading }),

      setKwsListening: (listening: boolean) => set({ isKwsListening: listening }),

      setError: (err: Error | null) =>
        set({
          error: err,
          // On error, go back to listening if enabled, else idle
          state: err ? 'listening' : undefined,
        }),

      recordWakeWord: () => set({ lastWakeWordTime: Date.now() }),

      reset: () =>
        set({
          state: 'idle',
          error: null,
          lastWakeWordTime: null,
          isKwsListening: false,
        }),
    }),
    {
      name: VOICE_MODE_ENABLED_KEY,
      // Only persist isEnabled, not transient state
      partialize: (s: VoiceModeStore) => ({ isEnabled: s.isEnabled }),
      // Merge rehydrated state with current state
      // If isEnabled is restored as true, set state to 'listening' (not 'idle')
      merge: (persistedState, currentState) => {
        const persisted = persistedState as Partial<VoiceModeStore>;
        return {
          ...currentState,
          isEnabled: persisted.isEnabled ?? currentState.isEnabled,
          // Sync state with isEnabled on rehydration
          state: persisted.isEnabled ? 'listening' : currentState.state,
        };
      },
    }
  )
);
