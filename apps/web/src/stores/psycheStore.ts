/**
 * Zustand store for live psyche state.
 *
 * Fed by two sources:
 * 1. Initial load: GET /psyche/state → updateFromFullState()
 * 2. SSE done events: psyche_state in metadata → updateFromSSE()
 *
 * Consumed by:
 * - ChatMessage → `messageAvatarPsyche`: a message's mood, its own or the live one
 * - CompanionPresence → `liveAvatarPsyche`: the companion's live mood
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
  ownerId: string | null;
  bindOwner: (ownerId: string | null) => void;
  clearObservedState: () => void;
  // Live mood state
  moodLabel: MoodLabel;
  moodColor: string;
  moodPleasure: number;
  moodArousal: number;
  moodDominance: number;
  activeEmotion: string | null;
  emotionIntensity: number;
  driveCuriosity: number;
  driveEngagement: number;
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
  ownerId: null,
  moodLabel: 'neutral' as MoodLabel,
  moodColor: '#9ca3af',
  moodPleasure: 0,
  moodArousal: 0,
  moodDominance: 0,
  activeEmotion: null,
  emotionIntensity: 0,
  driveCuriosity: 0.5,
  driveEngagement: 0.5,
  relationshipStage: 'ORIENTATION' as RelationshipStage,
  lastUpdated: null,
  fullState: null as PsycheState | null,
  displayAvatar: true,
  enabled: false,
};

export const usePsycheStore = create<PsycheStoreState>(set => ({
  ...INITIAL_STATE,
  bindOwner: ownerId =>
    set(previous => (previous.ownerId === ownerId ? previous : { ...INITIAL_STATE, ownerId })),
  clearObservedState: () =>
    set(previous => ({
      ...INITIAL_STATE,
      ownerId: previous.ownerId,
      enabled: previous.enabled,
      displayAvatar: previous.displayAvatar,
    })),

  updateFromSSE: (summary: PsycheStateSummary) =>
    set(previous => ({
      driveCuriosity: summary.drive_curiosity ?? previous.driveCuriosity,
      driveEngagement: summary.drive_engagement ?? previous.driveEngagement,
      moodLabel: summary.mood_label,
      moodColor: summary.mood_color,
      moodPleasure: summary.mood_pleasure,
      moodArousal: summary.mood_arousal,
      moodDominance: summary.mood_dominance,
      activeEmotion: summary.active_emotion,
      emotionIntensity: summary.emotion_intensity,
      relationshipStage: summary.relationship_stage,
      lastUpdated: new Date().toISOString(),
    })),

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
      driveCuriosity: state.drive_curiosity,
      driveEngagement: state.drive_engagement,
    });
  },

  setDisplayAvatar: (show: boolean) => set({ displayAvatar: show }),
  setEnabled: (enabled: boolean) => set({ enabled }),
  reset: () => set(INITIAL_STATE),
}));

/** What an avatar reads from the store: the live mood and the two switches. */
type AvatarPsycheSource = Pick<
  PsycheStoreState,
  | 'enabled'
  | 'displayAvatar'
  | 'moodLabel'
  | 'moodColor'
  | 'moodPleasure'
  | 'moodArousal'
  | 'moodDominance'
  | 'activeEmotion'
  | 'emotionIntensity'
  | 'relationshipStage'
>;

/** The live mood an avatar may show: none while the psyche is off or the avatar hidden. */
export function liveAvatarPsyche(state: AvatarPsycheSource): PsycheStateSummary | null {
  if (!state.enabled || !state.displayAvatar) return null;
  return {
    mood_label: state.moodLabel,
    mood_color: state.moodColor,
    mood_pleasure: state.moodPleasure,
    mood_arousal: state.moodArousal,
    mood_dominance: state.moodDominance,
    active_emotion: state.activeEmotion,
    emotion_intensity: state.emotionIntensity,
    relationship_stage: state.relationshipStage,
  };
}

/** The mood a message's avatar shows, and whether it is the live one. */
export interface MessageAvatarPsyche {
  psycheState: PsycheStateSummary | null;
  live: boolean;
}

/**
 * The mood a message's avatar shows: the snapshot its answer was stored with,
 * else the live mood. « Show emotional avatar » governs both — it used to gate
 * the live mood alone, so every finished answer kept showing its mood with the
 * switch off.
 */
export function messageAvatarPsyche(
  state: AvatarPsycheSource,
  snapshot: PsycheStateSummary | undefined
): MessageAvatarPsyche {
  if (!state.displayAvatar) return { psycheState: null, live: false };
  if (snapshot) return { psycheState: snapshot, live: false };
  const live = liveAvatarPsyche(state);
  return { psycheState: live, live: live !== null };
}
