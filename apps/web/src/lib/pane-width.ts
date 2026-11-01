/**
 * How wide a pane a person sizes by hand may be — pure, so a drag, the keyboard
 * and a narrower window all obey one rule (the debug panel, the « Tools » panes).
 *
 * A stored width the current layout cannot hold is CLAMPED for display and kept
 * as stored, so it comes back when the room does.
 */

/** How wide a pane may be, in whole pixels. */
export interface PaneBounds {
  min: number;
  max: number;
}

/** A width inside the bounds, in whole pixels. */
export function clampPaneWidth(width: number, bounds: PaneBounds): number {
  return Math.round(Math.min(bounds.max, Math.max(bounds.min, width)));
}
