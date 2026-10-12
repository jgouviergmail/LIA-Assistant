/** One continuous, editable product journey. Times follow Sunsetter's measured
 * attacks; the action itself retains readable holds between the accents. */
export const PRODUCT_STORY_DURATION = 24;
export const PRODUCT_STORY_FPS = 30;
export const PRODUCT_STORY_FRAMES = PRODUCT_STORY_DURATION * PRODUCT_STORY_FPS;

export const STORY_TIMING = {
  enter: 0.133,
  typeRequest: 0.548,
  submitRequest: 2.085,
  response: 2.601,
  responseReady: 4.134,
  sourcesLift: 4.648,
  sourceRows: [5.135, 5.674, 6.19],
  clarity: 6.701,
  dates: 7.215,
  datesReady: 8.234,
  sourcesReturn: 9.781,
  calloutLift: 10.294,
  calloutReturn: 12.336,
  approval: 12.857,
  draftReady: 13.882,
  approvalLift: 14.394,
  confirm: 17.468,
  approvalReturn: 17.987,
  confirmedMessage: 18.489,
  result: 19.012,
  exit: 20.542,
  finale: 21.063,
} as const;

export const STORY_REVIEW_SECONDS = [4, 9, 14, 19] as const;

export function frameAt(seconds: number, fps = PRODUCT_STORY_FPS): number {
  return Math.round(seconds * fps);
}

export function unitProgress(seconds: number, from: number, to: number): number {
  if (to <= from) return seconds >= to ? 1 : 0;
  return Math.max(0, Math.min(1, (seconds - from) / (to - from)));
}

/** Smooth camera/element paths, no wall clock or CSS animation dependency. */
export function easeProgress(seconds: number, from: number, to: number): number {
  const t = unitProgress(seconds, from, to);
  return t * t * (3 - 2 * t);
}

export function liftedProgress(seconds: number, from: number, until: number, duration = 0.24): number {
  return easeProgress(seconds, from, from + duration) *
    (1 - easeProgress(seconds, until, until + duration));
}

export function storyAct(seconds: number): 'context' | 'clarity' | 'approval' | 'finale' {
  if (seconds >= STORY_TIMING.finale) return 'finale';
  if (seconds >= STORY_TIMING.approval) return 'approval';
  if (seconds >= STORY_TIMING.clarity) return 'clarity';
  return 'context';
}
