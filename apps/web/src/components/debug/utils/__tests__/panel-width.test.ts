/**
 * How wide the debug panel may be (owner request 2026-09-24): it encroaches on
 * the conversation as it widens, and the conversation always keeps its floor.
 */

import { describe, expect, it } from 'vitest';

import { DEBUG_PANEL_CHAT_MIN_WIDTH, DEBUG_PANEL_GAP, DEBUG_PANEL_WIDTH_MIN } from '../constants';
import { debugPanelBounds } from '../panel-width';

describe('debugPanelBounds', () => {
  it('leaves the conversation its floor and the gap', () => {
    const bounds = debugPanelBounds(1600);
    expect(bounds.min).toBe(DEBUG_PANEL_WIDTH_MIN);
    expect(bounds.max).toBe(1600 - DEBUG_PANEL_CHAT_MIN_WIDTH - DEBUG_PANEL_GAP);
  });

  it('never offers less room than the minimum, however narrow the row', () => {
    expect(debugPanelBounds(500)).toEqual({
      min: DEBUG_PANEL_WIDTH_MIN,
      max: DEBUG_PANEL_WIDTH_MIN,
    });
    // Not measured yet.
    expect(debugPanelBounds(0).max).toBe(DEBUG_PANEL_WIDTH_MIN);
  });
});
