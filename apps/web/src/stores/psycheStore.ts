/**
 * Zustand store for live psyche state.
 *
 * Fed by two sources:
 * 1. Initial load: GET /psyche/state → updateFromFullState()
 * 2. SSE done events: psyche_state in metadata → updateFromSSE()
 *
 * Consumed by:
 * - ChatMessageList → fallback psyche state for AssistantAvatar
 * - PsycheStateSummary (settings page)
 *
 * No persistence needed — state comes from server on each page load.
 *
 * Phase: evolution — Psyche Engine (Iteration 2)
 * Created: 2026-04-01
 */

import { create } from 'zustand';

import type { MoodLabel, PsycheState, PsycheStateSummary, RelationshipStage } from '@/types/psyche';

interface PsycheStoreState {
  // Live mood state
  moodLabel: MoodLabel;
  moodColor: string;
  moodPleasure: number;
  moodArousal: number;
  moodDominance: number;
  activeEmotion: string | null;
  emotionIntensity: number;
  relationshipStage: RelationshipStage;
  lastUpdated: string | null;

  // Full server state snapshot (for traits, drives, etc.)
  fullState: PsycheState | null;

  // Display preference (synced with server on load)
  displayAvatar: boolean;

  // Whether psyche is enabled for this user
  enabled: boolean;

  // Actions
  updateFromSSE: (summary: PsycheStateSummary) => void;
  updateFromFullState: (state: PsycheState) => void;
  setDisplayAvatar: (show: boolean) => void;
  setEnabled: (enabled: boolean) => void;
  reset: () => void;
}

const INITIAL_STATE = {
  moodLabel: 'neutral' as MoodLabel,
  moodColor: '#9ca3af',
  moodPleasure: 0,
  moodArousal: 0,
  moodDominance: 0,
  activeEmotion: null,
  emotionIntensity: 0,
  relationshipStage: 'ORIENTATION' as RelationshipStage,
  lastUpdated: null,
  fullState: null as PsycheState | null,
  displayAvatar: true,
  enabled: false,
};

export const usePsycheStore = create<PsycheStoreState>(set => ({
  ...INITIAL_STATE,

  updateFromSSE: (summary: PsycheStateSummary) =>
    set({
      moodLabel: summary.mood_label,
      moodColor: summary.mood_color,
      moodPleasure: summary.mood_pleasure,
      moodArousal: summary.mood_arousal,
      moodDominance: summary.mood_dominance,
      activeEmotion: summary.active_emotion,
      emotionIntensity: summary.emotion_intensity,
      relationshipStage: summary.relationship_stage,
      lastUpdated: new Date().toISOString(),
    }),

  updateFromFullState: (state: PsycheState) => {
    // Sort a COPY to avoid mutating React Query cached data (BUG-4 fix)
    const sorted = [...state.active_emotions].sort((a, b) => b.intensity - a.intensity);
    const topEmotion = sorted[0] ?? null;
    set({
      moodLabel: state.mood_label,
      moodColor: state.mood_color,
      moodPleasure: state.mood_pleasure,
      moodArousal: state.mood_arousal,
      moodDominance: state.mood_dominance,
      activeEmotion: topEmotion?.name ?? null,
      emotionIntensity: topEmotion?.intensity ?? 0,
      relationshipStage: state.relationship_stage,
      lastUpdated: state.updated_at,
      fullState: state,
    });
  },

  setDisplayAvatar: (show: boolean) => set({ displayAvatar: show }),
  setEnabled: (enabled: boolean) => set({ enabled }),
  reset: () => set(INITIAL_STATE),
}));
