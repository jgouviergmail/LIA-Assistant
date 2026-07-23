/**
 * chat-scroll — pure decision layer of the chat reading invariant
 * (UXR Lot 3, A3).
 *
 * The invariant: a streaming answer (or a proactive/detached-run arrival)
 * never yanks a reader who scrolled away from the bottom of the thread; an
 * OWN send always jumps so the user sees their message. Geometry is measured
 * live at decision time by the caller (`ChatMessageList`) — never cached —
 * because content grows without scroll events (lazy code blocks, images).
 *
 * jsdom performs no layout, so the geometry behavior itself is proven in the
 * hermetic e2e package (`e2e/smoke/chat-scroll-follow.spec.ts`); this module
 * keeps every branch of the decision unit-testable.
 */

/** Distance from the bottom past which the reader counts as "away". */
export const SCROLL_FOLLOW_THRESHOLD_PX = 150;

/** The subset of scroll geometry the decisions need. */
export interface ScrollBox {
  scrollHeight: number;
  scrollTop: number;
  clientHeight: number;
}

/** Gap between the viewport bottom and the content bottom, in px. */
export function distanceToBottom(el: ScrollBox): number {
  return el.scrollHeight - el.scrollTop - el.clientHeight;
}

/**
 * "Was the reader at the bottom BEFORE this batch's growth?" — effects run
 * after the DOM commit, so a large token batch (fast model, resumed stream)
 * has already grown `scrollHeight` when the measurement happens; the raw
 * distance then reads as "away" for a reader who never moved (e2e-caught).
 * The growth since the previous turn is discounted. Null scroller = at bottom.
 */
export function isScrollerAtBottom(
  el: ScrollBox | null,
  prevScrollHeight?: number | null
): boolean {
  if (!el) return true;
  const growth = prevScrollHeight != null ? Math.max(0, el.scrollHeight - prevScrollHeight) : 0;
  return distanceToBottom(el) - growth <= SCROLL_FOLLOW_THRESHOLD_PX;
}

export type FollowDecision = 'follow' | 'stay';

/**
 * Decide whether the list may scroll to the bottom on a messages update.
 *
 * - An own send (`isNewOwnMessage`) always follows — the user must see it.
 * - Otherwise the reader's position rules: at bottom → follow the stream;
 *   away → stay (the invariant).
 *
 * Own-send detection is an EXPLICIT SIGNAL from the page (a send tick), never
 * a data diff. Both inference attempts failed against the real engine
 * (hermetic e2e): the last-entry role check missed the batched
 * `SEND_MESSAGE`+`STREAM_START` render, and a last-user-id comparison
 * false-fired when the post-`done` history reload swapped optimistic client
 * ids for server ids — yanking the reader it was supposed to protect.
 */
export function decideFollow(params: {
  atBottom: boolean;
  isNewOwnMessage: boolean;
}): FollowDecision {
  return params.isNewOwnMessage || params.atBottom ? 'follow' : 'stay';
}

/** Scroll-UI state: floating-button visibility + "new responses" badge. */
export interface ScrollUiState {
  /** True while the reader is further than the threshold from the bottom. */
  away: boolean;
  /** Responses that arrived or completed while the reader was away. */
  newWhileAway: number;
}

export const SCROLL_UI_INITIAL: ScrollUiState = { away: false, newWhileAway: 0 };

export type ScrollUiEvent =
  | { type: 'distance'; distance: number }
  | { type: 'new-assistant-message' }
  | { type: 'jumped-to-bottom' };

/**
 * Reducer for the scroll UI. Identity-stable when nothing changes so the
 * rAF-throttled scroll listener never causes render churn.
 */
export function scrollUiReducer(state: ScrollUiState, event: ScrollUiEvent): ScrollUiState {
  switch (event.type) {
    case 'distance': {
      const nowAway = event.distance > SCROLL_FOLLOW_THRESHOLD_PX;
      if (nowAway === state.away && (nowAway || state.newWhileAway === 0)) return state;
      return { away: nowAway, newWhileAway: nowAway ? state.newWhileAway : 0 };
    }
    case 'new-assistant-message':
      return state.away ? { away: true, newWhileAway: state.newWhileAway + 1 } : state;
    case 'jumped-to-bottom':
      return state.away || state.newWhileAway > 0 ? SCROLL_UI_INITIAL : state;
  }
}

/**
 * Instant jump to the bottom of a scroller. The chat container carries the
 * `scroll-smooth` class, which animates even a plain `scrollTop` assignment —
 * neutralised here with an inline `scroll-behavior: auto` for the duration of
 * the jump (single source; also used by the initial-pin loop).
 */
export function pinToBottom(el: HTMLElement): void {
  const style = el.style;
  const previous = style.getPropertyValue('scroll-behavior');
  style.setProperty('scroll-behavior', 'auto');
  el.scrollTop = el.scrollHeight;
  if (previous) style.setProperty('scroll-behavior', previous);
  else style.removeProperty('scroll-behavior');
}
