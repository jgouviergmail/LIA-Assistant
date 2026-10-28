import { expect, it } from 'vitest';
import { conversationFocusOffset, WORLD_CONVERSATION_WIDTH } from '../conversation-layout';
it('centers following characters in the exposed desktop area at every allowed zoom', () => {
  for (const zoom of [0.55, 0.95, 1.8]) {
    const offset = conversationFocusOffset(1280, zoom, true);
    expect(1280 / 2 - offset * zoom).toBeCloseTo((1280 - WORLD_CONVERSATION_WIDTH) / 2);
  }
});
it('does not offset full-width phone panels, closed conversations or invalid geometry', () => {
  for (const [width, zoom, open] of [
    [390, 0.95, true],
    [1280, 1, false],
    [NaN, 1, true],
    [1280, 0, true],
    [1280, Infinity, true],
    [1280, Number.MIN_VALUE, true],
  ] as const)
    expect(conversationFocusOffset(width, zoom, open)).toBe(0);
});
