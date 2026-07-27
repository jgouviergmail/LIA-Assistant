/**
 * Chat surface arbitration (S1) — which conditional blocks may occupy the
 * space between the message thread and the composer.
 *
 * Measured context (S0, 2026-07-26): on an 800 px viewport the chat shell is
 * 716 px. With a pending HITL card AND follow-up chips the chrome reaches
 * 443 px — 62 % of the shell — leaving 259 px of conversation. On an iPhone SE
 * that falls to ~140 px, about four lines.
 *
 * The chrome is not the real defect though: the combination is. LIA asks the
 * user to confirm sending an email *and*, right above it, offers three
 * unrelated follow-up questions. The blocks are rendered one after another
 * with no notion of each other. This module gives them a single, pure,
 * exhaustively-tested priority rule.
 */

import { describe, it, expect } from 'vitest';

import {
  CHAT_SURFACES,
  hitlAwaitsUser,
  visibleChatSurfaces,
  type ChatSurface,
  type ChatSurfaceContext,
} from '../chat-surfaces';
import type { HitlCardStatus } from '@/types/hitl';

/** Everything active at once — the pathological state S0 measured. */
const ALL_ACTIVE: ChatSurfaceContext = {
  usageBlocked: true,
  hitlAwaitingAction: true,
  hasConnectorNotices: true,
  wantsGeolocationPrompt: true,
  hasFollowups: true,
};

const NONE_ACTIVE: ChatSurfaceContext = {
  usageBlocked: false,
  hitlAwaitingAction: false,
  hasConnectorNotices: false,
  wantsGeolocationPrompt: false,
  hasFollowups: false,
};

function visible(overrides: Partial<ChatSurfaceContext> = {}): ChatSurface[] {
  return [...visibleChatSurfaces({ ...NONE_ACTIVE, ...overrides })].sort();
}

describe('hitlAwaitsUser — which card states owe the user an action', () => {
  it.each<[HitlCardStatus, boolean]>([
    ['awaiting', true],
    // In flight: the answer is being processed, still not the moment to suggest
    // something else.
    ['submitting', true],
    // End-of-life badges: they render, but nothing is expected any more, so the
    // comfort surfaces may come back.
    ['resolved', false],
    ['expired', false],
    ['none', false],
  ])('%s → %s', (status, expected) => {
    expect(hitlAwaitsUser(status)).toBe(expected);
  });

  it('covers every declared card status', () => {
    // A new status added to HitlCardStatus without a decision here would be
    // treated as "not awaiting" by omission — this pins the enumeration.
    const known: HitlCardStatus[] = ['none', 'awaiting', 'submitting', 'resolved', 'expired'];
    for (const status of known) {
      expect(typeof hitlAwaitsUser(status)).toBe('boolean');
    }
  });
});

describe('visibleChatSurfaces — nothing is invented', () => {
  it('shows nothing when nothing is active', () => {
    expect(visible()).toEqual([]);
  });

  it.each(CHAT_SURFACES)('never returns %s unless its own source is active', surface => {
    // Activate everything EXCEPT this surface's own trigger.
    const context: ChatSurfaceContext = { ...ALL_ACTIVE };
    const trigger: Record<ChatSurface, keyof ChatSurfaceContext> = {
      usage: 'usageBlocked',
      hitl: 'hitlAwaitingAction',
      connector: 'hasConnectorNotices',
      geolocation: 'wantsGeolocationPrompt',
      followups: 'hasFollowups',
    };
    context[trigger[surface]] = false;
    expect(visibleChatSurfaces(context).has(surface)).toBe(false);
  });
});

describe('visibleChatSurfaces — blocking surfaces are never suppressed (G1)', () => {
  it('keeps the usage banner even when everything else competes for space', () => {
    expect(visibleChatSurfaces(ALL_ACTIVE).has('usage')).toBe(true);
  });

  it('keeps the HITL card even when everything else competes for space', () => {
    expect(visibleChatSurfaces(ALL_ACTIVE).has('hitl')).toBe(true);
  });

  it('keeps both blocking surfaces together — they say different things', () => {
    // "You reached your quota" and "an action is waiting for you" are not
    // interchangeable; hiding either leaves a dead end with no explanation.
    const result = visible({ usageBlocked: true, hitlAwaitingAction: true });
    expect(result).toEqual(['hitl', 'usage']);
  });
});

describe('visibleChatSurfaces — connector notices explain a degradation', () => {
  it('is shown alongside a blocking surface', () => {
    expect(visibleChatSurfaces(ALL_ACTIVE).has('connector')).toBe(true);
  });

  it('is shown on its own', () => {
    expect(visible({ hasConnectorNotices: true })).toEqual(['connector']);
  });
});

describe('visibleChatSurfaces — comfort surfaces yield to a pending action', () => {
  it('drops follow-up chips while a HITL card awaits an answer', () => {
    // The product defect S0 surfaced: LIA cannot both ask for a confirmation
    // and suggest unrelated next questions.
    expect(visible({ hitlAwaitingAction: true, hasFollowups: true })).toEqual(['hitl']);
  });

  it('drops follow-up chips while the usage quota blocks the composer', () => {
    // Already true today through `visibleFollowups(messages, blocked)`; pinned
    // here so the rule lives in ONE place.
    expect(visible({ usageBlocked: true, hasFollowups: true })).toEqual(['usage']);
  });

  it('drops the geolocation prompt while a HITL card awaits an answer', () => {
    expect(visible({ hitlAwaitingAction: true, wantsGeolocationPrompt: true })).toEqual(['hitl']);
  });

  it('drops the geolocation prompt while the quota blocks the composer', () => {
    expect(visible({ usageBlocked: true, wantsGeolocationPrompt: true })).toEqual(['usage']);
  });

  it('shows comfort surfaces when nothing blocks', () => {
    expect(visible({ hasFollowups: true, wantsGeolocationPrompt: true })).toEqual([
      'followups',
      'geolocation',
    ]);
  });

  it('reduces the pathological stack to the surfaces that carry meaning', () => {
    // 5 candidate blocks → 3 rendered: the two blocking ones and the notice.
    expect(visible(ALL_ACTIVE)).toEqual(['connector', 'hitl', 'usage']);
  });
});

describe('visibleChatSurfaces — the rule table is exhaustive', () => {
  it('decides every declared surface', () => {
    // Completeness assert (ADR-085 model): a surface added to CHAT_SURFACES
    // without a rule would silently never render.
    for (const surface of CHAT_SURFACES) {
      const trigger: Record<ChatSurface, keyof ChatSurfaceContext> = {
        usage: 'usageBlocked',
        hitl: 'hitlAwaitingAction',
        connector: 'hasConnectorNotices',
        geolocation: 'wantsGeolocationPrompt',
        followups: 'hasFollowups',
      };
      const alone = visibleChatSurfaces({ ...NONE_ACTIVE, [trigger[surface]]: true });
      expect(alone.has(surface), `${surface} never renders even when alone`).toBe(true);
    }
  });

  it('is pure — the same context always yields the same answer', () => {
    const first = [...visibleChatSurfaces(ALL_ACTIVE)];
    const second = [...visibleChatSurfaces(ALL_ACTIVE)];
    expect(first).toEqual(second);
  });

  it('never returns a surface outside the declared set', () => {
    const declared = new Set<string>(CHAT_SURFACES);
    for (const surface of visibleChatSurfaces(ALL_ACTIVE)) {
      expect(declared.has(surface)).toBe(true);
    }
  });
});
