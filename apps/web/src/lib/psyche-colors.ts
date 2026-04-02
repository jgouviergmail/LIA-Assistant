/**
 * Mood-to-color mapping for the Psyche Engine mood ring.
 *
 * Colorblind-safe palette: no pure red/green pair.
 * 8 distinct hue regions (sky, violet, amber, pink, teal, orange, indigo, gray).
 * Under deuteranopia/protanopia simulation, all remain distinguishable
 * by both hue angle and luminance difference.
 *
 * Phase: evolution — Psyche Engine (Iteration 1)
 * Created: 2026-04-01
 */

import type { MoodLabel } from '@/types/psyche';

export interface MoodColorConfig {
  /** Tailwind ring class for the mood ring border */
  ringClass: string;
  /** Background class for badges/pills */
  bgClass: string;
  /** Text color class */
  textClass: string;
  /** Hex color value for inline styles */
  hex: string;
  /** Emoji icon for the mood */
  icon: string;
}

export const MOOD_COLORS: Record<MoodLabel, MoodColorConfig> = {
  serene: {
    ringClass: 'ring-sky-400/70',
    bgClass: 'bg-sky-100 dark:bg-sky-900/30',
    textClass: 'text-sky-700 dark:text-sky-300',
    hex: '#38bdf8',
    icon: '😌',
  },
  curious: {
    ringClass: 'ring-violet-400/70',
    bgClass: 'bg-violet-100 dark:bg-violet-900/30',
    textClass: 'text-violet-700 dark:text-violet-300',
    hex: '#a78bfa',
    icon: '🧐',
  },
  energized: {
    ringClass: 'ring-amber-400/70',
    bgClass: 'bg-amber-100 dark:bg-amber-900/30',
    textClass: 'text-amber-700 dark:text-amber-300',
    hex: '#fbbf24',
    icon: '😁',
  },
  playful: {
    ringClass: 'ring-pink-400/70',
    bgClass: 'bg-pink-100 dark:bg-pink-900/30',
    textClass: 'text-pink-700 dark:text-pink-300',
    hex: '#f472b6',
    icon: '😜',
  },
  reflective: {
    ringClass: 'ring-teal-400/70',
    bgClass: 'bg-teal-100 dark:bg-teal-900/30',
    textClass: 'text-teal-700 dark:text-teal-300',
    hex: '#2dd4bf',
    icon: '🤔',
  },
  agitated: {
    ringClass: 'ring-orange-500/70',
    bgClass: 'bg-orange-100 dark:bg-orange-900/30',
    textClass: 'text-orange-700 dark:text-orange-300',
    hex: '#f97316',
    icon: '😟',
  },
  melancholic: {
    ringClass: 'ring-indigo-400/70',
    bgClass: 'bg-indigo-100 dark:bg-indigo-900/30',
    textClass: 'text-indigo-700 dark:text-indigo-300',
    hex: '#818cf8',
    icon: '😞',
  },
  neutral: {
    ringClass: 'ring-gray-400/50',
    bgClass: 'bg-gray-100 dark:bg-gray-800/30',
    textClass: 'text-gray-600 dark:text-gray-400',
    hex: '#9ca3af',
    icon: '😐',
  },
  // --- Iteration 3 additions ---
  content: {
    ringClass: 'ring-emerald-400/70',
    bgClass: 'bg-emerald-100 dark:bg-emerald-900/30',
    textClass: 'text-emerald-700 dark:text-emerald-300',
    hex: '#34d399',
    icon: '😊',
  },
  determined: {
    ringClass: 'ring-red-500/70',
    bgClass: 'bg-red-100 dark:bg-red-900/30',
    textClass: 'text-red-700 dark:text-red-300',
    hex: '#ef4444',
    icon: '😤',
  },
  defiant: {
    ringClass: 'ring-rose-500/70',
    bgClass: 'bg-rose-100 dark:bg-rose-900/30',
    textClass: 'text-rose-700 dark:text-rose-300',
    hex: '#f43f5e',
    icon: '😠',
  },
  resigned: {
    ringClass: 'ring-slate-400/70',
    bgClass: 'bg-slate-100 dark:bg-slate-800/30',
    textClass: 'text-slate-600 dark:text-slate-400',
    hex: '#94a3b8',
    icon: '😔',
  },
  overwhelmed: {
    ringClass: 'ring-purple-500/70',
    bgClass: 'bg-purple-100 dark:bg-purple-900/30',
    textClass: 'text-purple-700 dark:text-purple-300',
    hex: '#a855f7',
    icon: '😵',
  },
  tender: {
    ringClass: 'ring-pink-500/70',
    bgClass: 'bg-pink-100 dark:bg-pink-900/30',
    textClass: 'text-pink-700 dark:text-pink-300',
    hex: '#ec4899',
    icon: '🥰',
  },
};

/**
 * Get mood color config for a given mood label.
 * Falls back to 'neutral' for unknown labels.
 */
export function getMoodColor(label: MoodLabel | string): MoodColorConfig {
  return MOOD_COLORS[label as MoodLabel] ?? MOOD_COLORS.neutral;
}
