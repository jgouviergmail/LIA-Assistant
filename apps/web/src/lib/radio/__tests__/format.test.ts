import { describe, expect, it } from 'vitest';

import { IDLE_RADIO_VIEW } from '@/stores/radioStore';

import type { RadioView } from '../controller';
import {
  airingSegment,
  currentLineIndex,
  minutesLeft,
  radioCost,
  radioCostEstimate,
  radioEstimateMessage,
  radioStatusMessage,
  webUrl,
} from '../format';
import type { RadioSegment } from '../types';

const NOW = Date.parse('2026-09-26T08:00:00Z');

describe('radioCost', () => {
  it('says nothing it does not know', () => {
    expect(radioCost(null, 'fr')).toBeNull();
  });

  it('shows fractions of a cent in the listener’s locale', () => {
    expect(radioCost(0.0042, 'fr')).toBe('0,0042 €');
    expect(radioCost(0.0042, 'en')).toBe('€0.0042');
  });
});

describe('airingSegment', () => {
  const segment: RadioSegment = {
    seq: 1,
    format: 'bulletin',
    mood: 'news',
    title: 'The nine o’clock news',
    duration_s: 60,
    transcript: [],
  };

  it('is the programme the station plays or holds on pause', () => {
    const playing: RadioView = { ...IDLE_RADIO_VIEW, status: 'playing', current: segment };
    expect(airingSegment(playing)).toBe(segment);
    expect(airingSegment({ ...playing, status: 'paused' })).toBe(segment);
  });

  it('is nothing between two programmes, while signing off or once over', () => {
    for (const status of ['waiting', 'starting', 'ending', 'ended'] as const) {
      expect(airingSegment({ ...IDLE_RADIO_VIEW, status, current: segment })).toBeNull();
    }
  });
});

describe('radioCostEstimate', () => {
  it('says an estimate with two significant digits: a guess, never false precision', () => {
    expect(radioCostEstimate(0.05123, 'fr')).toBe('0,051 €');
    expect(radioCostEstimate(0.3, 'fr')).toBe('0,30 €');
    expect(radioCostEstimate(1.234, 'en')).toBe('€1.2');
    expect(radioCostEstimate(12.3, 'en')).toBe('€12');
  });

  it('keeps two significant digits when the rounding carries into a new digit', () => {
    expect(radioCostEstimate(0.0995, 'fr')).toBe('0,10 €');
    expect(radioCostEstimate(9.96, 'en')).toBe('€10');
  });

  it('never rounds a tiny amount to nothing, nor spends more than four decimals on it', () => {
    expect(radioCostEstimate(0.00042, 'fr')).toBe('0,0004 €');
    expect(radioCostEstimate(0, 'fr')).toBe('0,00 €');
  });
});

describe('radioEstimateMessage', () => {
  const on = (changes: Partial<RadioView>): RadioView => ({
    ...IDLE_RADIO_VIEW,
    status: 'playing',
    ...changes,
  });

  it('prices the listening the timer planned', () => {
    const view = on({
      stopAt: '2026-09-26T08:30:00Z',
      costEstimateEur: 0.05123,
      costEstimateS: 1800,
    });
    expect(radioEstimateMessage(view, 'fr')).toEqual({
      key: 'radio.banner.estimate',
      values: { cost: '0,051 €', minutes: 30 },
    });
  });

  it('prices an hour when no timer stops the station', () => {
    const view = on({ stopAt: null, costEstimateEur: 0.12, costEstimateS: 3600 });
    expect(radioEstimateMessage(view, 'fr')).toEqual({
      key: 'radio.banner.estimate_hourly',
      values: { cost: '0,12 €' },
    });
  });

  it('says nothing before an estimate exists, or once the station is off', () => {
    expect(radioEstimateMessage(on({ costEstimateEur: null }), 'fr')).toBeNull();
    const ended = on({ status: 'ended', costEstimateEur: 0.1, costEstimateS: 1800 });
    expect(radioEstimateMessage(ended, 'fr')).toBeNull();
  });
});

describe('minutesLeft', () => {
  it('rounds up: twenty seconds left is one minute left, never none', () => {
    expect(minutesLeft('2026-09-26T08:00:20Z', NOW)).toBe(1);
    expect(minutesLeft('2026-09-26T08:30:00Z', NOW)).toBe(30);
  });

  it('is zero once the stop has passed, and absent without a timer', () => {
    expect(minutesLeft('2026-09-26T07:59:00Z', NOW)).toBe(0);
    expect(minutesLeft(null, NOW)).toBeNull();
    expect(minutesLeft('not an instant', NOW)).toBeNull();
  });
});

describe('currentLineIndex', () => {
  const offsets = [2.5, 6, 11.2];

  it('is the music before the first line', () => {
    expect(currentLineIndex(offsets, 1)).toBe(-1);
  });

  it('is the last line that has started', () => {
    expect(currentLineIndex(offsets, 2.5)).toBe(0);
    expect(currentLineIndex(offsets, 10)).toBe(1);
    expect(currentLineIndex(offsets, 40)).toBe(2);
  });
});

describe('webUrl', () => {
  it('keeps a web address', () => {
    expect(webUrl('https://news.example/a?b=1')).toBe('https://news.example/a?b=1');
  });

  it('never turns another scheme, or nonsense, into a link', () => {
    expect(webUrl('javascript:alert(1)')).toBeNull();
    expect(webUrl('data:text/html,<b>x</b>')).toBeNull();
    expect(webUrl('not a url')).toBeNull();
    expect(webUrl(null)).toBeNull();
  });
});

describe('radioStatusMessage', () => {
  const view = (changes: Partial<RadioView>): RadioView => ({ ...IDLE_RADIO_VIEW, ...changes });

  it('says an error before anything else', () => {
    expect(radioStatusMessage(view({ status: 'ended', error: 'start_failed' }), 'fr')).toEqual({
      key: 'radio.errors.start_failed',
    });
  });

  it('quotes the budget a start was refused at, and when it lifts, in the listener’s locale', () => {
    const message = radioStatusMessage(
      view({
        status: 'ended',
        error: 'radio_budget_reached',
        // Midday UTC: a Sunday on every clock from UTC-11 to UTC+11.
        refusedBudget: { maxEur: 2, liftsAt: '2026-09-27T12:00:00Z' },
      }),
      'fr'
    );
    expect(message.key).toBe('radio.errors.radio_budget_reached');
    expect(message.values?.max).toBe('2,00 €');
    expect(String(message.values?.lifts)).toContain('dimanche');
  });

  it('quotes no budget it does not know', () => {
    expect(
      radioStatusMessage(view({ status: 'ended', error: 'radio_budget_reached' }), 'fr')
    ).toEqual({ key: 'radio.errors.start_failed' });
  });

  it('says why a session ended, and never a reason it does not know', () => {
    expect(radioStatusMessage(view({ status: 'ended', endReason: 'budget' }), 'fr')).toEqual({
      key: 'radio.end_reason.budget',
    });
    expect(radioStatusMessage(view({ status: 'ended', endReason: 'solar_flare' }), 'fr')).toEqual({
      key: 'radio.end_reason.other',
    });
  });

  it('announces how long the first voice should take', () => {
    expect(radioStatusMessage(view({ status: 'starting', startupEstimateS: 14.4 }), 'fr')).toEqual({
      key: 'radio.banner.starting_eta',
      values: { seconds: 14 },
    });
    expect(radioStatusMessage(view({ status: 'starting' }), 'fr')).toEqual({
      key: 'radio.banner.starting',
    });
  });

  it('otherwise names the state', () => {
    expect(radioStatusMessage(view({ status: 'waiting' }), 'fr')).toEqual({
      key: 'radio.banner.waiting',
    });
  });
});
