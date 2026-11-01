/**
 * How wide the debug panel may be — pure, so the drag, the keyboard and a
 * narrower window all obey one rule (clamped by `lib/pane-width`).
 *
 * The panel encroaches on the conversation as the person widens it, and the
 * conversation always keeps `DEBUG_PANEL_CHAT_MIN_WIDTH`. A stored width the
 * current window cannot hold is CLAMPED for display and kept as stored, so it
 * comes back when the room does.
 */

import type { PaneBounds } from '@/lib/pane-width';

import { DEBUG_PANEL_CHAT_MIN_WIDTH, DEBUG_PANEL_GAP, DEBUG_PANEL_WIDTH_MIN } from './constants';

/**
 * The bounds inside a layout of a given width.
 *
 * @param containerWidth - The row holding the conversation and the panel; 0
 *   while it has not been measured (the maximum is then the minimum's floor).
 */
export function debugPanelBounds(containerWidth: number): PaneBounds {
  const room = Math.floor(containerWidth - DEBUG_PANEL_CHAT_MIN_WIDTH - DEBUG_PANEL_GAP);
  return { min: DEBUG_PANEL_WIDTH_MIN, max: Math.max(DEBUG_PANEL_WIDTH_MIN, room) };
}
