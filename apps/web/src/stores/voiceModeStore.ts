'use client';

/**
 * Zustand store for Voice Mode state management.
 *
 * Manages global voice mode state across the application:
 * - Voice mode enabled/disabled toggle
 * - Current voice state (idle, listening, recording, processing, speaking)
 * - The time of the last wake-word detection (the detector's own state lives
 *   in `useWakeWord`, read by the one component that shows it)
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
  | 'idle' // Voice mode disabled, text input mode
  | 'listening' // Listening for wake word
  | 'recording' // Wake word detected, recording user speech
  | 'processing' // Processing speech (STT + LLM)
  | 'speaking'; // TTS playing response

/**
 * Voice mode store state interface.
 */
export interface VoiceModeStore {
  // State
  /** Whether voice mode is enabled (persisted) */
  isEnabled: boolean;
  /** Current voice mode state */
  state: VoiceModeState;
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
    (
      set: (
        partial: Partial<VoiceModeStore> | ((state: VoiceModeStore) => Partial<VoiceModeStore>)
      ) => void
    ) => ({
      // Initial state
      isEnabled: false,
      state: 'idle' as VoiceModeState,
      error: null,
      lastWakeWordTime: null,

      // Actions
      enable: () => set({ isEnabled: true, state: 'listening', error: null }),

      disable: () => set({ isEnabled: false, state: 'idle', error: null }),

      toggle: () =>
        set((s: VoiceModeStore) => ({
          isEnabled: !s.isEnabled,
          state: !s.isEnabled ? 'listening' : 'idle',
          error: null,
        })),

      setState: (newState: VoiceModeState) => set({ state: newState }),

      setError: (err: Error | null) =>
        set((s: VoiceModeStore) => ({
          error: err,
          // On error, go back to listening if enabled, else idle. Clearing
          // the error (err = null) must leave the state machine untouched —
          // an explicit `state: undefined` would be copied by Object.assign
          // in zustand's setState and corrupt the state key.
          ...(err ? { state: s.isEnabled ? 'listening' : 'idle' } : {}),
        })),

      recordWakeWord: () => set({ lastWakeWordTime: Date.now() }),

      reset: () =>
        set({
          state: 'idle',
          error: null,
          lastWakeWordTime: null,
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
