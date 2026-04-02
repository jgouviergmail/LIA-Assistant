/**
 * TypeScript interfaces for the Psyche Engine.
 *
 * Defines types for psyche state, settings, expression profile,
 * and SSE metadata used by the frontend mood ring and settings UI.
 *
 * Phase: evolution — Psyche Engine (Iteration 1)
 * Created: 2026-04-01
 */

// =============================================================================
// Mood Labels — canonical set (matches backend MOOD_LABEL_CENTROIDS keys)
// =============================================================================

export type MoodLabel =
  | 'serene'
  | 'curious'
  | 'energized'
  | 'playful'
  | 'reflective'
  | 'agitated'
  | 'melancholic'
  | 'neutral'
  | 'content'
  | 'determined'
  | 'defiant'
  | 'resigned'
  | 'overwhelmed'
  | 'tender';

// =============================================================================
// Relationship Stages
// =============================================================================

export type RelationshipStage = 'ORIENTATION' | 'EXPLORATORY' | 'AFFECTIVE' | 'STABLE';

// =============================================================================
// Lightweight summary (piggybacked on SSE done event)
// =============================================================================

export interface PsycheStateSummary {
  mood_label: MoodLabel;
  mood_color: string; // hex color for mood ring
  mood_pleasure: number; // PAD [-1, +1]
  mood_arousal: number; // PAD [-1, +1]
  mood_dominance: number; // PAD [-1, +1]
  active_emotion: string | null;
  emotion_intensity: number; // [0, 1]
  relationship_stage: RelationshipStage;
}

// =============================================================================
// Full state (from GET /psyche/state)
// =============================================================================

export interface BigFiveTraits {
  openness: number;
  conscientiousness: number;
  extraversion: number;
  agreeableness: number;
  neuroticism: number;
}

export interface SelfEfficacyEntry {
  score: number;
  weight: number;
}

export interface ActiveEmotion {
  name: string;
  intensity: number;
  triggered_at: string;
}

export interface PsycheState {
  id: string;
  user_id: string;

  // Big Five
  trait_openness: number;
  trait_conscientiousness: number;
  trait_extraversion: number;
  trait_agreeableness: number;
  trait_neuroticism: number;

  // Mood
  mood_pleasure: number;
  mood_arousal: number;
  mood_dominance: number;
  mood_label: MoodLabel;
  mood_color: string;

  // Emotions
  active_emotions: ActiveEmotion[];

  // Relationship
  relationship_stage: RelationshipStage;
  relationship_depth: number;
  relationship_warmth_active: number;
  relationship_trust: number;
  relationship_interaction_count: number;

  // Drives
  drive_curiosity: number;
  drive_engagement: number;

  // Self-efficacy
  self_efficacy: Record<string, SelfEfficacyEntry>;

  // Timestamps
  created_at: string;
  updated_at: string;
}

// =============================================================================
// Expression Profile (from GET /psyche/expression)
// =============================================================================

export interface PsycheExpressionProfile {
  mood_label: string;
  mood_intensity: string;
  active_emotions: Array<{ name: string; intensity: number }>;
  relationship_stage: string;
  warmth_label: string;
  drive_curiosity: number;
  drive_engagement: number;
}

// =============================================================================
// Settings (from GET/PATCH /psyche/settings)
// =============================================================================

export interface PsycheSettings {
  psyche_enabled: boolean;
  psyche_display_avatar: boolean;
  psyche_sensitivity: number; // 0-100
  psyche_stability: number; // 0-100
}

export type PsycheSettingsUpdate = Partial<PsycheSettings>;

// =============================================================================
// History (from GET /psyche/history)
// =============================================================================

export interface PsycheHistoryEntry {
  id: string;
  snapshot_type: string;
  mood_pleasure: number;
  mood_arousal: number;
  mood_dominance: number;
  dominant_emotion: string | null;
  relationship_stage: string;
  /** Extended metrics: emotion_intensity, relationship_depth/warmth/trust, drives. */
  trait_snapshot: {
    emotion_intensity?: number;
    relationship_depth?: number;
    relationship_warmth?: number;
    relationship_trust?: number;
    drive_curiosity?: number;
    drive_engagement?: number;
    [key: string]: number | undefined;
  } | null;
  created_at: string;
}
