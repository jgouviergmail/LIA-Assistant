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

import { resolveInitialComposition, resolveInitialMessage } from '../chat-initial-message';
import type { CardCompositionDraft } from '@/types/card-actions';

it('uses only the owner draft in embedded chat, never private host URL content', () => {
  const query = new URLSearchParams('draft=host-only');
  expect(resolveInitialMessage(query, 'owner draft', 'host intent', true)).toBe('owner draft');
  expect(resolveInitialMessage(query, undefined, 'host intent', true)).toBeUndefined();
});

it('accepts an explicitly chosen embedded draft without allowing it to change ordinary URL priority', () => {
  const query = new URLSearchParams('draft=host-only');
  expect(
    resolveInitialMessage(query, 'stored', 'host intent', true, 'explicit native action')
  ).toBe('explicit native action');
  expect(resolveInitialMessage(query, 'stored', '', false, 'embedded only')).toBe('host-only');
});

describe('resolveInitialMessage', () => {
  it('cannot carry an older email action into a newly chosen world task', () => {
    const old: CardCompositionDraft = {
      text: 'Old reply',
      label: 'Private email',
      selection: {
        version: 1,
        message_id: 'message',
        run_id: 'run',
        registry_id: 'old-target',
        action: 'reply',
      },
    };
    expect(resolveInitialComposition(old, true, 'New agenda task')).toBeUndefined();
    expect(resolveInitialComposition(old, false, 'Ignored')).toBe(old);
    expect(resolveInitialComposition(old, true, undefined)).toBe(old);
  });
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
