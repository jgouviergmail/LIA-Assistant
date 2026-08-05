/**
 * resolveInitialMessage — what the chat composer opens with.
 *
 * Extracted from the chat page (ADR-210) so the priority is a tested contract:
 * the `?draft=` deep link wins (onboarding volet B / briefing intents), then a
 * REPLAYED intent (a consumed `?intent=` resurrected by the browser — shown as
 * a draft so the arrival stays visible instead of silently doing nothing),
 * then the persisted per-user draft (UXR Lot 2, A7). Never auto-sent.
 */

import { describe, it, expect } from 'vitest';

import { resolveInitialMessage } from '../chat-initial-message';

describe('resolveInitialMessage', () => {
  it('prefers the ?draft= deep link over everything', () => {
    const params = new URLSearchParams('draft=from-url');
    expect(resolveInitialMessage(params, 'stored', 'replayed')).toBe('from-url');
  });

  it('shows a replayed intent over the stored draft — the arrival must be visible', () => {
    expect(resolveInitialMessage(new URLSearchParams(), 'stored', 'replayed')).toBe('replayed');
  });

  it('falls back to the persisted draft', () => {
    expect(resolveInitialMessage(new URLSearchParams(), 'stored', '')).toBe('stored');
  });

  it('returns undefined when nothing applies — the input keeps its default state', () => {
    expect(resolveInitialMessage(new URLSearchParams(), undefined, '')).toBeUndefined();
    expect(resolveInitialMessage(null, undefined, '')).toBeUndefined();
  });

  it('ignores a blank ?draft=', () => {
    const params = new URLSearchParams('draft=%20%20');
    expect(resolveInitialMessage(params, 'stored', '')).toBe('stored');
  });
});
