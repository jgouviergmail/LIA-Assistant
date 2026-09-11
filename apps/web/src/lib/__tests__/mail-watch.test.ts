/**
 * What a « Watch » chip actually posts (ADR-281, lot 5).
 *
 * The shape is composed in one module rather than inside the card, so it can
 * be pinned here field by field — including the two traps it was written to
 * avoid: a query taken from the drifting subject instead of the stable sender,
 * and an end date computed through UTC, which names tomorrow for half of every
 * day in any zone ahead of it.
 */

import { describe, expect, it } from 'vitest';
import {
  MAIL_WATCH_DAYS,
  MAIL_WATCH_HOURS,
  buildMailWatch,
  canWatch,
  existingWatchFor,
  watchEndDate,
  watchQueryFor,
  type WatchCandidate,
} from '../mail-watch';

const MAIL = { sender_email: 'marie@acme.fr', sender_name: 'Marie Dupont' };

function build(overrides: Partial<Parameters<typeof buildMailWatch>[0]> = {}) {
  return buildMailWatch({
    mail: MAIL,
    title: 'Veille : Marie Dupont',
    actionPrompt: 'Préviens-moi de la réponse.',
    now: new Date(2026, 8, 11, 21, 30),
    ...overrides,
  });
}

describe('who is being awaited', () => {
  it('is the address, the stable identity', () => {
    expect(watchQueryFor(MAIL)).toBe('marie@acme.fr');
  });

  it('falls back to the display name when no address came through', () => {
    expect(watchQueryFor({ sender_email: null, sender_name: 'Marie Dupont' })).toBe('Marie Dupont');
  });

  it('is never the subject', () => {
    // A subject drifts through Re: and Fwd: and is shared by unrelated threads.
    expect(watchQueryFor(MAIL)).not.toContain('devis');
  });

  it('is trimmed of surrounding spaces', () => {
    expect(watchQueryFor({ sender_email: '  marie@acme.fr  ', sender_name: null })).toBe(
      'marie@acme.fr'
    );
  });

  it('is capped at what the API accepts', () => {
    const long = `${'a'.repeat(200)}@acme.fr`;
    expect(watchQueryFor({ sender_email: long, sender_name: null })).toHaveLength(120);
  });
});

describe('whether a watch can be offered', () => {
  it('yes when a sender came through', () => {
    expect(canWatch(MAIL)).toBe(true);
  });

  it('no when neither an address nor a name did', () => {
    expect(canWatch({ sender_email: null, sender_name: null })).toBe(false);
  });

  it('no when what came through is too short for the API', () => {
    expect(canWatch({ sender_email: 'a', sender_name: null })).toBe(false);
  });

  it('and building one anyway refuses rather than posting a 422', () => {
    expect(() => build({ mail: { sender_email: null, sender_name: null } })).toThrow();
  });
});

describe('when the watch ends', () => {
  it('counts calendar days from the local day', () => {
    expect(watchEndDate(new Date(2026, 8, 11, 10, 0))).toBe('2026-09-25');
  });

  it('reads the LOCAL evening, not the UTC tomorrow', () => {
    // `toISOString()` on 23:30 in any zone ahead of UTC names the next day,
    // which would end every watch created after dinner a day early.
    expect(watchEndDate(new Date(2026, 8, 11, 23, 30))).toBe('2026-09-25');
  });

  it('crosses a month boundary', () => {
    expect(watchEndDate(new Date(2026, 8, 25, 8, 0))).toBe('2026-10-09');
  });

  it('crosses a year boundary', () => {
    expect(watchEndDate(new Date(2026, 11, 28, 8, 0))).toBe('2027-01-11');
  });

  it('pads single-digit months and days', () => {
    expect(watchEndDate(new Date(2026, 0, 1, 8, 0), 0)).toBe('2026-01-01');
  });
});

describe('the payload', () => {
  it('is a condition routine on a mail match', () => {
    const payload = build();
    expect(payload.trigger_kind).toBe('condition');
    expect(payload.condition_config).toEqual({ type: 'mail_match', query: 'marie@acme.fr' });
  });

  it('carries the translated wording untouched', () => {
    const payload = build();
    expect(payload.title).toBe('Veille : Marie Dupont');
    expect(payload.action_prompt).toBe('Préviens-moi de la réponse.');
  });

  it('ends through the recurrence, never through a field of its own', () => {
    const payload = build();
    expect(payload.recurrence.end).toEqual({ kind: 'on_date', on_date: '2026-09-25' });
    expect(payload).not.toHaveProperty('expires_at');
  });

  it('anchors on the day it is created, so the series starts at once', () => {
    expect(build().recurrence.anchor_date).toBe('2026-09-11');
  });

  it('evaluates twice a day as the fallback for an account with no push', () => {
    const payload = build();
    expect(payload.recurrence.times).toEqual({
      mode: 'at',
      at: MAIL_WATCH_HOURS.map(hour => ({ hour, minute: 0 })),
    });
  });

  it('stays far under the twelve-a-day a routine may ask', () => {
    expect(MAIL_WATCH_HOURS.length).toBeLessThanOrEqual(12);
  });

  it('lives two working weeks', () => {
    expect(MAIL_WATCH_DAYS).toBe(14);
  });
});

describe('a watch that already exists', () => {
  function routine(overrides: Partial<WatchCandidate> = {}): WatchCandidate {
    return {
      is_enabled: true,
      trigger_kind: 'condition',
      condition_config: { type: 'mail_match', query: 'marie@acme.fr' },
      ...overrides,
    };
  }

  it('is found when it waits for the same person', () => {
    expect(existingWatchFor([routine()], 'marie@acme.fr')).toBeDefined();
  });

  it('is found whatever the casing or the surrounding spaces', () => {
    expect(existingWatchFor([routine()], '  MARIE@ACME.FR ')).toBeDefined();
  });

  it('is not found when it waits for somebody else', () => {
    expect(existingWatchFor([routine()], 'bob@acme.fr')).toBeUndefined();
  });

  it('ignores a routine the person paused', () => {
    // Pausing is a decision to stop being told; a fresh watch is the answer.
    expect(existingWatchFor([routine({ is_enabled: false })], 'marie@acme.fr')).toBeUndefined();
  });

  it('ignores a routine that is not a condition at all', () => {
    const timed = routine({ trigger_kind: 'time', condition_config: null });
    expect(existingWatchFor([timed], 'marie@acme.fr')).toBeUndefined();
  });

  it('ignores a condition of another type', () => {
    const weather = routine({ condition_config: { type: 'weather_change' } });
    expect(existingWatchFor([weather], 'marie@acme.fr')).toBeUndefined();
  });

  it('finds nothing in an empty account', () => {
    expect(existingWatchFor([], 'marie@acme.fr')).toBeUndefined();
  });

  it('never matches on an empty query', () => {
    const empty = routine({ condition_config: { type: 'mail_match', query: '' } });
    expect(existingWatchFor([empty], '')).toBeUndefined();
  });
});
