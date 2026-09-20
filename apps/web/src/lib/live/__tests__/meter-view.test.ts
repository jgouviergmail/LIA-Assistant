/** The meter's wording (ADR-300 wave 3), computed apart from the band. */
import { describe, expect, it } from 'vitest';

import { EMPTY_METER, accumulateUsage } from '../meter';
import { describeMeter, formatClock } from '../meter-view';
import type { LiveRates } from '../types';

const GEMINI: LiveRates = {
  pricing_unit: 'per_1m_tokens',
  input_unit_price: 0.75,
  output_unit_price: 4.5,
  audio_input_unit_price: 3,
  audio_output_unit_price: 12,
  usd_eur_rate: 0.9,
};
const GPT_LIVE: LiveRates = {
  pricing_unit: 'per_audio_minute',
  input_unit_price: 0.05,
  output_unit_price: 0,
  audio_input_unit_price: null,
  audio_output_unit_price: null,
  usd_eur_rate: 0.9,
};

describe('describeMeter', () => {
  it('a token-billed model: tokens in the locale, the cost with four decimals, the context', () => {
    const meter = accumulateUsage(EMPTY_METER, {
      tokens: {
        textIn: 1029,
        audioIn: 198,
        textOut: 20,
        audioOut: 48,
        thoughts: 115,
        context: 1295,
      },
    });
    const view = describeMeter(meter, GEMINI, 999, null, 'fr');
    expect(view.durationBilled).toBe(false);
    expect(view.tokensIn).toBe('1 227');
    expect(view.tokensOut).toBe('183');
    expect(view.cost).toBe('0,0023 €');
    expect(view.context).toBe('1 295');
  });

  it('the ceiling stands beside the cost when one is set', () => {
    expect(describeMeter(EMPTY_METER, GEMINI, 0, 2, 'fr').cost).toBe('0,0000 € / 2,00 €');
    expect(describeMeter(EMPTY_METER, GEMINI, 0, 2, 'en').cost).toBe('€0.0000 / €2.00');
  });

  it('a cost that needs an undeclared rate is null, never partial', () => {
    const meter = accumulateUsage(EMPTY_METER, {
      tokens: { textIn: 10, audioIn: 5, textOut: 0, audioOut: 0, thoughts: 0, context: 15 },
    });
    const noAudio = { ...GEMINI, audio_input_unit_price: null, audio_output_unit_price: null };
    expect(describeMeter(meter, noAudio, 0, null, 'fr').cost).toBeNull();
  });

  it('a duration-billed model: the clock (the larger of the two counts), the window share', () => {
    let view = describeMeter(EMPTY_METER, GPT_LIVE, 61, null, 'fr');
    expect(view.durationBilled).toBe(true);
    expect(view.clock).toBe('1:01');
    expect(view.cost).toBe('0,0458 €');
    expect(view.context).toBeNull();
    const reported = accumulateUsage(EMPTY_METER, {
      duration: { seconds: 90, contextRatio: 0.123 },
    });
    view = describeMeter(reported, GPT_LIVE, 61, null, 'fr');
    expect(view.clock).toBe('1:30');
    expect(view.context).toBe('12 %');
  });

  it('formatClock pads the seconds', () => {
    expect(formatClock(0)).toBe('0:00');
    expect(formatClock(65)).toBe('1:05');
    expect(formatClock(3600)).toBe('60:00');
  });
});
