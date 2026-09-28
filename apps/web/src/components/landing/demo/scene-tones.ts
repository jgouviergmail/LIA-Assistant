import type { ProductSceneId } from './scenes';

/** A stable visual cue from the scene picker to its result and chapter. */
export const SCENE_TONES = {
  decision: {
    text: 'text-sky-800 dark:text-sky-300',
    surface: 'bg-sky-500/10',
    border: 'border-sky-600/35 dark:border-sky-400/35',
    fill: 'bg-sky-500 dark:bg-sky-400',
  },
  day: {
    text: 'text-rose-800 dark:text-rose-300',
    surface: 'bg-rose-500/10',
    border: 'border-rose-600/35 dark:border-rose-400/35',
    fill: 'bg-rose-500 dark:bg-rose-400',
  },
  watch: {
    text: 'text-amber-800 dark:text-amber-300',
    surface: 'bg-amber-500/10',
    border: 'border-amber-600/35 dark:border-amber-400/35',
    fill: 'bg-amber-500 dark:bg-amber-400',
  },
  call: {
    text: 'text-emerald-800 dark:text-emerald-300',
    surface: 'bg-emerald-500/10',
    border: 'border-emerald-600/35 dark:border-emerald-400/35',
    fill: 'bg-emerald-500 dark:bg-emerald-400',
  },
  research: {
    text: 'text-violet-800 dark:text-violet-300',
    surface: 'bg-violet-500/10',
    border: 'border-violet-600/35 dark:border-violet-400/35',
    fill: 'bg-violet-500 dark:bg-violet-400',
  },
  relay: {
    text: 'text-teal-800 dark:text-teal-300',
    surface: 'bg-teal-500/10',
    border: 'border-teal-600/35 dark:border-teal-400/35',
    fill: 'bg-teal-500 dark:bg-teal-400',
  },
} satisfies Record<ProductSceneId, { text: string; surface: string; border: string; fill: string }>;
