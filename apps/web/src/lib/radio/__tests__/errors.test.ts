/**
 * A refusal the radio's API names is told in its own words, its bound quoted (ADR-324).
 *
 * Driven with the real `ApiError` — the shape both HTTP clients throw — so a
 * change to the envelope breaks here, never in front of a listener.
 */
import { describe, expect, it } from 'vitest';

import { ApiError } from '@/lib/api-client';
import {
  BUDGET_REACHED,
  RADIO_START_REFUSALS,
  isStartRefusal,
  radioRefusalOf,
  sourceLookupRefusalOf,
  startRefusalOf,
} from '@/lib/radio/errors';

function refused(detail: unknown, status = 422): ApiError {
  return new ApiError('irrelevant', status, { detail });
}

describe('radioRefusalOf — the sentence of a coded refusal', () => {
  it.each([
    ...RADIO_START_REFUSALS.filter(code => code !== BUDGET_REACHED),
    'radio_voice_unknown',
    'radio_personality_unknown',
  ])('tells %s in its own words', code => {
    expect(radioRefusalOf(refused({ code }, 503))).toEqual({ key: `radio.errors.${code}` });
  });

  it('quotes the longest timer the instance allows', () => {
    expect(radioRefusalOf(refused({ code: 'radio_timer_too_long', max_minutes: 240 }))).toEqual({
      key: 'radio.errors.radio_timer_too_long',
      values: { max: 240 },
    });
  });

  it('counts the sites a listener may add (the sentence is plural-aware)', () => {
    expect(radioRefusalOf(refused({ code: 'radio_source_limit', max_sources: 1 }, 409))).toEqual({
      key: 'radio.errors.radio_source_limit',
      values: { count: 1 },
    });
  });

  it('tells a site with no feed by what looking for it found', () => {
    expect(radioRefusalOf(refused({ code: 'radio_source_refused', outcome: 'forbidden' }))).toEqual(
      { key: 'radio.settings.sites.outcome.forbidden' }
    );
  });

  it('says nothing it cannot say truthfully — the caller keeps its own sentence', () => {
    // A bound missing beside its code: no sentence quotes a number nobody sent.
    expect(radioRefusalOf(refused({ code: 'radio_timer_too_long' }))).toBeNull();
    // « found » is not a refusal, and an outcome this build does not know has no sentence.
    expect(radioRefusalOf(refused({ code: 'radio_source_refused', outcome: 'found' }))).toBeNull();
    expect(radioRefusalOf(refused({ code: 'radio_source_refused', outcome: 'later' }))).toBeNull();
    // Another domain's code, a plain detail, a network failure.
    expect(radioRefusalOf(refused({ code: 'drive_folder_nested' }, 409))).toBeNull();
    expect(radioRefusalOf(refused('Not found', 404))).toBeNull();
    expect(radioRefusalOf(new Error('network'))).toBeNull();
    // A write never meets the radio's budget: only a start is refused on it, with its facts.
    expect(radioRefusalOf(refused({ code: BUDGET_REACHED, max_eur: 2 }, 429))).toBeNull();
  });
});

describe('sourceLookupRefusalOf — a site lookup refused by the rate limit', () => {
  it('names HTTP 429 instead of saying the site could not be checked', () => {
    expect(sourceLookupRefusalOf(refused({ error: 'rate_limit_exceeded' }, 429))).toEqual({
      key: 'radio.settings.sites.rate_limited',
    });
    expect(sourceLookupRefusalOf(new Error('network'))).toBeNull();
  });
});

describe('startRefusalOf — why a start was refused, and what its sentence quotes', () => {
  it('reads the budget a start past it quotes: the bound, and when it lifts', () => {
    const error = refused(
      { code: BUDGET_REACHED, max_eur: 2, lifts_at: '2026-09-27T21:00:00+00:00' },
      429
    );
    expect(startRefusalOf(error)).toEqual({
      code: BUDGET_REACHED,
      budget: { maxEur: 2, liftsAt: '2026-09-27T21:00:00+00:00' },
    });
  });

  it('names the other start refusals with nothing beside them', () => {
    expect(startRefusalOf(refused({ code: 'radio_no_voice' }, 503))).toEqual({
      code: 'radio_no_voice',
      budget: null,
    });
  });

  it('quotes nothing it was not sent — the caller says its own sentence', () => {
    expect(startRefusalOf(refused({ code: BUDGET_REACHED, max_eur: 2 }, 429))).toBeNull();
    expect(
      startRefusalOf(refused({ code: BUDGET_REACHED, max_eur: '2', lifts_at: 'x' }, 429))
    ).toBeNull();
    expect(startRefusalOf(refused({ code: 'radio_voice_unknown' }))).toBeNull();
    expect(startRefusalOf(new Error('network'))).toBeNull();
  });
});

describe('isStartRefusal', () => {
  it('knows the start refusals and nothing else', () => {
    expect(isStartRefusal('radio_instance_full')).toBe(true);
    expect(isStartRefusal('radio_voice_unknown')).toBe(false);
    expect(isStartRefusal(undefined)).toBe(false);
  });
});
