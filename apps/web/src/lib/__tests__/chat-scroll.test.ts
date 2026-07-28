/**
 * chat-scroll (UXR Lot 3, A3) — the pure decision layer of the reading
 * invariant: follow-vs-stay decisions, the scroll-UI reducer (away flag +
 * "new responses" badge), and the bottom-distance measure. The geometry
 * behavior itself is proven in the hermetic e2e package (jsdom performs no
 * layout — see the pinned rationale in ChatMessageList.test.tsx).
 */

import { describe, it, expect } from 'vitest';

import {
  SCROLL_FOLLOW_THRESHOLD_PX,
  SCROLL_UI_INITIAL,
  decideFollow,
  distanceToBottom,
  isScrollerAtBottom,
  scrollUiReducer,
  type ScrollUiState,
} from '../chat-scroll';

describe('distanceToBottom', () => {
  it('measures the gap between the viewport bottom and the content bottom', () => {
    expect(distanceToBottom({ scrollHeight: 2000, scrollTop: 500, clientHeight: 800 })).toBe(700);
  });

  it('is zero when pinned at the bottom', () => {
    expect(distanceToBottom({ scrollHeight: 2000, scrollTop: 1200, clientHeight: 800 })).toBe(0);
  });
});

describe('isScrollerAtBottom — growth-compensated measurement', () => {
  it('discounts the growth a large token batch just committed', () => {
    // Reader was pinned (distance 0); ONE commit grew the content by 400px.
    // Raw distance now reads 400 (> threshold) — but the reader never moved.
    const el = { scrollHeight: 2400, scrollTop: 1200, clientHeight: 800 };
    expect(isScrollerAtBottom(el, 2000)).toBe(true);
  });

  it('still sees a genuinely away reader through the growth', () => {
    const el = { scrollHeight: 2400, scrollTop: 100, clientHeight: 800 };
    expect(isScrollerAtBottom(el, 2000)).toBe(false);
  });

  it('never lets shrinkage fake an at-bottom reader (growth clamped at 0)', () => {
    const el = { scrollHeight: 1600, scrollTop: 100, clientHeight: 800 };
    expect(isScrollerAtBottom(el, 2000)).toBe(false);
  });

  it('treats a missing scroller or first measure as at bottom', () => {
    expect(isScrollerAtBottom(null)).toBe(true);
    expect(
      isScrollerAtBottom({ scrollHeight: 2000, scrollTop: 1200, clientHeight: 800 }, null)
    ).toBe(true);
  });
});

describe('decideFollow — the reading invariant', () => {
  it('always follows an own send, even while away', () => {
    expect(decideFollow({ atBottom: false, isNewOwnMessage: true })).toBe('follow');
  });

  it('follows streaming growth while the reader sits at the bottom', () => {
    expect(decideFollow({ atBottom: true, isNewOwnMessage: false })).toBe('follow');
  });

  it('NEVER yanks a reader who scrolled away (stream, proactive, completion)', () => {
    expect(decideFollow({ atBottom: false, isNewOwnMessage: false })).toBe('stay');
  });
});

describe('scrollUiReducer — away flag + badge', () => {
  const away = (n = 0): ScrollUiState => ({ away: true, newWhileAway: n });

  it('raises the away flag past the threshold and keeps identity below it', () => {
    const s1 = scrollUiReducer(SCROLL_UI_INITIAL, {
      type: 'distance',
      distance: SCROLL_FOLLOW_THRESHOLD_PX + 1,
    });
    expect(s1).toEqual(away(0));

    // Same state again → SAME reference (no re-render per scroll event).
    expect(scrollUiReducer(s1, { type: 'distance', distance: 9999 })).toBe(s1);
    expect(scrollUiReducer(SCROLL_UI_INITIAL, { type: 'distance', distance: 10 })).toBe(
      SCROLL_UI_INITIAL
    );
  });

  it('counts new responses only while away', () => {
    expect(scrollUiReducer(away(0), { type: 'new-assistant-message' })).toEqual(away(1));
    expect(scrollUiReducer(away(1), { type: 'new-assistant-message' })).toEqual(away(2));
    expect(scrollUiReducer(SCROLL_UI_INITIAL, { type: 'new-assistant-message' })).toBe(
      SCROLL_UI_INITIAL
    );
  });

  it('clears the badge when the reader reaches the bottom by scrolling', () => {
    expect(scrollUiReducer(away(3), { type: 'distance', distance: 0 })).toEqual(SCROLL_UI_INITIAL);
  });

  it('clears everything on an explicit jump (button click / own send)', () => {
    expect(scrollUiReducer(away(2), { type: 'jumped-to-bottom' })).toEqual(SCROLL_UI_INITIAL);
    expect(scrollUiReducer(SCROLL_UI_INITIAL, { type: 'jumped-to-bottom' })).toBe(
      SCROLL_UI_INITIAL
    );
  });
});
