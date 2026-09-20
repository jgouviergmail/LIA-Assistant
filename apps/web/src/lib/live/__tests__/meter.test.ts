/**
 * The live meter (ADR-300 wave 3): the provider's own reports, folded and
 * priced by the declared tariff — a cost that is a claim or nothing.
 */
import { describe, expect, it } from 'vitest';

import {
  EMPTY_METER,
  accumulateUsage,
  geminiUsageReport,
  meterCost,
  meterTotals,
  openaiUsageReport,
} from '../meter';
import type { LiveRates } from '../types';

const GEMINI_RATES: LiveRates = {
  pricing_unit: 'per_1m_tokens',
  input_unit_price: 0.75,
  output_unit_price: 4.5,
  audio_input_unit_price: 3,
  audio_output_unit_price: 12,
  usd_eur_rate: 0.9,
};
const GPT_LIVE_RATES: LiveRates = {
  pricing_unit: 'per_audio_minute',
  input_unit_price: 0.05,
  output_unit_price: 0,
  audio_input_unit_price: null,
  audio_output_unit_price: null,
  usd_eur_rate: 0.9,
};

/** A frame measured on a real session (2026-09-19): the first turn. */
const FRAME_1 = {
  promptTokenCount: 1227,
  responseTokenCount: 68,
  totalTokenCount: 1295,
  promptTokensDetails: [
    { modality: 'TEXT', tokenCount: 974 },
    { modality: 'AUDIO', tokenCount: 198 },
  ],
  responseTokensDetails: [{ modality: 'AUDIO', tokenCount: 48 }],
  thoughtsTokenCount: 115,
};
const FRAME_2 = {
  promptTokenCount: 1342,
  responseTokenCount: 160,
  totalTokenCount: 1502,
  promptTokensDetails: [
    { modality: 'TEXT', tokenCount: 1021 },
    { modality: 'AUDIO', tokenCount: 246 },
  ],
  responseTokensDetails: [{ modality: 'AUDIO', tokenCount: 160 }],
  thoughtsTokenCount: 72,
};

describe('geminiUsageReport', () => {
  it('reads a measured frame by modality, the unattributed prompt tokens as text', () => {
    const report = geminiUsageReport(FRAME_1);
    // 1227 prompt − 198 audio = 1029 text (974 listed + 55 unattributed).
    expect(report?.tokens).toEqual({
      textIn: 1029,
      audioIn: 198,
      textOut: 20,
      audioOut: 48,
      thoughts: 115,
      context: 1295,
    });
  });

  it('returns null on an empty or foreign frame', () => {
    expect(geminiUsageReport({})).toBeNull();
    expect(geminiUsageReport(null)).toBeNull();
    expect(geminiUsageReport('x')).toBeNull();
  });
});

describe('openaiUsageReport', () => {
  it('reads the seconds and the bounded window ratio', () => {
    expect(
      openaiUsageReport({
        type: 'session.usage.updated',
        usage: { seconds: 8 },
        context_window: { usage_ratio: 0.12 },
      })
    ).toEqual({ duration: { seconds: 8, contextRatio: 0.12 } });
    expect(openaiUsageReport({ usage: { seconds: 8 } })).toEqual({
      duration: { seconds: 8, contextRatio: null },
    });
    expect(
      openaiUsageReport({ context_window: { usage_ratio: 1.4 } })?.duration?.contextRatio
    ).toBe(1);
  });

  it('returns null when the event carries neither', () => {
    expect(openaiUsageReport({ type: 'session.usage.updated' })).toBeNull();
  });
});

describe('accumulateUsage', () => {
  it('adds tokens across turns and keeps the last context', () => {
    let meter = accumulateUsage(EMPTY_METER, geminiUsageReport(FRAME_1)!);
    meter = accumulateUsage(meter, geminiUsageReport(FRAME_2)!);
    expect(meter.reports).toBe(2);
    expect(meter.textIn).toBe(1029 + 1096);
    expect(meter.audioIn).toBe(198 + 246);
    expect(meter.audioOut).toBe(48 + 160);
    expect(meter.thoughts).toBe(115 + 72);
    expect(meter.context).toBe(1502);
    expect(meterTotals(meter)).toEqual({ tokensIn: 2569, tokensOut: 20 + 48 + 160 + 187 });
  });

  it('replaces a duration and never moves it back', () => {
    let meter = accumulateUsage(EMPTY_METER, { duration: { seconds: 30, contextRatio: 0.1 } });
    meter = accumulateUsage(meter, { duration: { seconds: 12, contextRatio: null } });
    expect(meter.seconds).toBe(30);
    expect(meter.contextRatio).toBe(0.1);
  });
});

describe('meterCost', () => {
  it('prices a token-billed session by modality, thoughts at the text output rate', () => {
    const meter = accumulateUsage(EMPTY_METER, geminiUsageReport(FRAME_1)!);
    const cost = meterCost(meter, GEMINI_RATES);
    const usd = (1029 * 0.75 + 198 * 3 + (20 + 115) * 4.5 + 48 * 12) / 1_000_000;
    expect(cost?.usd).toBeCloseTo(usd, 12);
    expect(cost?.eur).toBeCloseTo(usd * 0.9, 12);
  });

  it('is unavailable — never partial — when audio was used and no audio rate is declared', () => {
    const meter = accumulateUsage(EMPTY_METER, geminiUsageReport(FRAME_1)!);
    const noAudio = {
      ...GEMINI_RATES,
      audio_input_unit_price: null,
      audio_output_unit_price: null,
    };
    expect(meterCost(meter, noAudio)).toBeNull();
    // Text only: the text rates suffice.
    const textOnly = accumulateUsage(EMPTY_METER, {
      tokens: { textIn: 100, audioIn: 0, textOut: 10, audioOut: 0, thoughts: 0, context: 110 },
    });
    expect(meterCost(textOnly, noAudio)?.usd).toBeCloseTo((100 * 0.75 + 10 * 4.5) / 1_000_000, 12);
  });

  it('prices a minute-billed session by the seconds it is handed, else the reported ones', () => {
    const meter = accumulateUsage(EMPTY_METER, { duration: { seconds: 90, contextRatio: null } });
    expect(meterCost(meter, GPT_LIVE_RATES)?.usd).toBeCloseTo(0.075, 12);
    expect(meterCost(meter, GPT_LIVE_RATES, 120)?.usd).toBeCloseTo(0.1, 12);
    expect(meterCost(EMPTY_METER, GPT_LIVE_RATES, 60)?.eur).toBeCloseTo(0.045, 12);
    expect(
      meterCost(EMPTY_METER, { ...GPT_LIVE_RATES, pricing_unit: 'per_audio_hour' }, 3600)?.usd
    ).toBeCloseTo(0.05, 12);
  });

  it('starts at zero', () => {
    expect(meterCost(EMPTY_METER, GEMINI_RATES)).toEqual({ usd: 0, eur: 0 });
  });
});
