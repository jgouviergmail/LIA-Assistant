// @vitest-environment node
/**
 * chat-reducer — SSR branches of the sessionStorage helpers.
 *
 * Runs in the node environment (no `window`) to cover the
 * `typeof window === 'undefined'` guards of createInitialState and
 * persistDebugMetricsHistory.
 */

import { describe, it, expect } from 'vitest';

import { createInitialState, persistDebugMetricsHistory } from '@/reducers/chat-reducer';
import { initialChatState } from '@/types/chat-state';

describe('chat-reducer helpers — SSR (no window)', () => {
  it('createInitialState returns the pristine state without touching storage', () => {
    expect(typeof window).toBe('undefined');

    const state = createInitialState();

    expect(state).toEqual(initialChatState);
  });

  it('persistDebugMetricsHistory is a silent no-op', () => {
    expect(() => persistDebugMetricsHistory([])).not.toThrow();
  });
});
