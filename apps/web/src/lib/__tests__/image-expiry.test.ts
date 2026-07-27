/**
 * Expiry of AI-generated images (N2).
 *
 * The rule has to be honest at both ends: it must warn in time, and it must
 * stay silent when it does not know. A UI that invents "24 h" from a hardcoded
 * constant would eventually lie (the TTL is configurable), and one that renders
 * an unparsed date would print "Invalid Date" next to the picture.
 */

import { describe, it, expect } from 'vitest';

import { classifyImageExpiry, EXPIRY_SOON_HOURS } from '../image-expiry';

const NOW = new Date('2026-07-26T12:00:00Z');

/** An ISO instant `hours` away from NOW. */
function inHours(hours: number): string {
  return new Date(NOW.getTime() + hours * 3_600_000).toISOString();
}

describe('classifyImageExpiry', () => {
  it('says nothing without a deadline', () => {
    // History predating N2 carries no `expires_at`; silence beats a guess.
    expect(classifyImageExpiry(undefined, NOW)).toEqual({ kind: 'unknown' });
    expect(classifyImageExpiry(null, NOW)).toEqual({ kind: 'unknown' });
    expect(classifyImageExpiry('', NOW)).toEqual({ kind: 'unknown' });
  });

  it('says nothing on an unparseable deadline', () => {
    // Rendering `new Date('not-a-date')` would print "Invalid Date" on screen.
    expect(classifyImageExpiry('not-a-date', NOW)).toEqual({ kind: 'unknown' });
  });

  it('reports a comfortable deadline', () => {
    const result = classifyImageExpiry(inHours(20), NOW);
    expect(result.kind).toBe('later');
    if (result.kind === 'later') {
      expect(result.at.toISOString()).toBe(inHours(20));
    }
  });

  it('escalates as the deadline approaches', () => {
    const result = classifyImageExpiry(inHours(3), NOW);
    expect(result.kind).toBe('soon');
    if (result.kind === 'soon') expect(result.hoursLeft).toBe(3);
  });

  it('treats the threshold itself as urgent', () => {
    // A boundary that flips the wrong way would leave the last hours quiet.
    const result = classifyImageExpiry(inHours(EXPIRY_SOON_HOURS), NOW);
    expect(result.kind).toBe('soon');
  });

  it('is comfortable just past the threshold', () => {
    expect(classifyImageExpiry(inHours(EXPIRY_SOON_HOURS + 0.5), NOW).kind).toBe('later');
  });

  it('rounds up so the last minutes still count as an hour', () => {
    // 30 minutes left must read "1 hour", never "0 hours".
    const result = classifyImageExpiry(inHours(0.5), NOW);
    expect(result.kind).toBe('soon');
    if (result.kind === 'soon') expect(result.hoursLeft).toBe(1);
  });

  it('reports an elapsed deadline as expired', () => {
    expect(classifyImageExpiry(inHours(-1), NOW)).toEqual({ kind: 'expired' });
  });

  it('treats the exact instant as expired', () => {
    expect(classifyImageExpiry(NOW.toISOString(), NOW)).toEqual({ kind: 'expired' });
  });

  it('is pure — no hidden clock', () => {
    // The reference instant is injected; the same inputs must always agree.
    const iso = inHours(10);
    expect(classifyImageExpiry(iso, NOW)).toEqual(classifyImageExpiry(iso, NOW));
  });

  it('handles a non-UTC offset without drifting', () => {
    // 14:00+02:00 is 12:00Z — the same instant as NOW, hence expired.
    expect(classifyImageExpiry('2026-07-26T14:00:00+02:00', NOW)).toEqual({ kind: 'expired' });
  });
});
