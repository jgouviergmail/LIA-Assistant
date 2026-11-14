/**
 * What a directed look lands on.
 *
 * The engine names the THING the face looks at, the screen declares where that
 * thing is, and this module turns the one into the other. A direction written
 * in the engine points at the same place wherever the person parked the face:
 * the text is below a face docked in the header and beside one parked next to
 * the thread.
 *
 * One declaration, one reader: `gazeTargetProps` is what a screen spreads on
 * the element, `locateGazeTarget` is the only code that looks for it. The one
 * thing no screen can decorate — a toast, which the toaster renders — is
 * declared here, beside the attribute, so the reader stays one.
 */

import { clampGazeAxis, type Gaze } from './expression-engine';

/** The things a screen may declare: the answer being written, the field the
 * person types in, and where a notification shows. */
export type GazeTarget = 'answer' | 'input' | 'notification';

export const GAZE_TARGET_ATTRIBUTE = 'data-eyes-target';

/**
 * How each target is found. A notification is also the toast in front of the
 * toaster (`components/ui/toaster.tsx`), unless it is on its way out; a page
 * with no toast declares where it shows one (the companion presence).
 */
const DECLARED: Record<GazeTarget, string> = {
  answer: `[${GAZE_TARGET_ATTRIBUTE}="answer"]`,
  input: `[${GAZE_TARGET_ATTRIBUTE}="input"]`,
  notification:
    `[${GAZE_TARGET_ATTRIBUTE}="notification"], ` +
    '[data-sonner-toast][data-front="true"]:not([data-removed="true"])',
};

/** Where a target is looked at: an answer at its END, where the next words
 * appear; a field or a notification in its middle. */
const READ_AT: Record<GazeTarget, 'end' | 'middle'> = {
  answer: 'end',
  input: 'middle',
  notification: 'middle',
};

/** How often a held look re-reads where its target is: text grows, a page
 * scrolls, a face is dragged. Two rectangles read, a few times a second. */
export const GAZE_TARGET_REFRESH_MS = 400;

export interface ScreenPoint {
  x: number;
  y: number;
}

export interface ViewportSize {
  width: number;
  height: number;
}

/** Declare an element as a thing the face may look at. */
export function gazeTargetProps(
  target: GazeTarget
): Record<typeof GAZE_TARGET_ATTRIBUTE, GazeTarget> {
  return { [GAZE_TARGET_ATTRIBUTE]: target };
}

/**
 * Direction from the face to a point of the screen. Half a viewport is a full
 * deflection: the scale the cursor parallax has always used, so a look at a
 * thing and a look at the cursor read as the same eyes.
 */
export function gazeToward(
  face: Pick<DOMRect, 'left' | 'top' | 'width' | 'height'>,
  point: ScreenPoint,
  viewport: ViewportSize
): Gaze {
  return {
    x: clampGazeAxis((point.x - (face.left + face.width / 2)) / (viewport.width / 2)),
    y: clampGazeAxis((point.y - (face.top + face.height / 2)) / (viewport.height / 2)),
  };
}

/**
 * Where the screen says a target is, or null when it declares none.
 *
 * An answer is read at its END, where the next words appear, a field or a
 * notification in its middle, and the point is kept on screen: an answer
 * longer than the window is still being written at the bottom of what the
 * person sees. The LAST declaration wins: a thread holds the newest thing
 * last, and the toaster comes after the page it notifies.
 */
export function locateGazeTarget(
  target: GazeTarget,
  viewport: ViewportSize,
  root: ParentNode = document
): ScreenPoint | null {
  const declared = root.querySelectorAll(DECLARED[target]);
  const element = declared[declared.length - 1];
  if (!element) return null;
  const rect = element.getBoundingClientRect();
  if (rect.width === 0 && rect.height === 0) return null;
  const y = READ_AT[target] === 'end' ? rect.bottom : rect.top + rect.height / 2;
  return {
    x: Math.min(viewport.width, Math.max(0, rect.left + rect.width / 2)),
    y: Math.min(viewport.height, Math.max(0, y)),
  };
}
