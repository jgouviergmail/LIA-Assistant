/**
 * The live session's indicative meter (ADR-300 wave 3).
 *
 * The session runs on the PERSON's own key: the platform records, accounts
 * and bills nothing of it. What a person watching a session may still see is
 * what it is costing THEM — counted here, in the browser, from the
 * provider's own usage reports multiplied by the tariff the API published at
 * the start (`LiveRates`, the administrator's declaration under LLM pricing).
 * Nothing of this leaves the page: not persisted, not on the closing card.
 *
 * Two billing shapes, one meter:
 *  - a token-billed model (Gemini Live) reports, per model turn, the prompt
 *    it re-billed — the WHOLE context, by modality — its response by
 *    modality, and its thinking tokens (billed at the text output rate);
 *  - a duration-billed model (GPT-Live) reports the session's seconds and how
 *    much of its context window is used.
 *
 * The cost is a CLAIM (ADR-185): it is computed only when every rate the
 * usage needs is declared, and reads as unavailable otherwise — never as a
 * partial figure that would under-report.
 */

import type { LiveRates, LiveUsageReport } from './types';

export interface LiveMeter {
  /** Cumulative tokens, by modality (token-billed models). */
  textIn: number;
  audioIn: number;
  textOut: number;
  audioOut: number;
  /** Thinking tokens, billed at the text output rate. */
  thoughts: number;
  /** The context size at the last report (tokens), or null before any. */
  context: number | null;
  /** The provider's own count of the session's seconds (duration-billed models). */
  seconds: number | null;
  /** The share of the context window in use at the last report, 0..1, or null. */
  contextRatio: number | null;
  /** How many reports were folded in. */
  reports: number;
}

export const EMPTY_METER: LiveMeter = {
  textIn: 0,
  audioIn: 0,
  textOut: 0,
  audioOut: 0,
  thoughts: 0,
  context: null,
  seconds: null,
  contextRatio: null,
  reports: 0,
};

/** Fold one provider report into the meter: tokens ADD, a duration REPLACES. */
export function accumulateUsage(meter: LiveMeter, report: LiveUsageReport): LiveMeter {
  const next: LiveMeter = { ...meter, reports: meter.reports + 1 };
  if (report.tokens) {
    const t = report.tokens;
    next.textIn += t.textIn;
    next.audioIn += t.audioIn;
    next.textOut += t.textOut;
    next.audioOut += t.audioOut;
    next.thoughts += t.thoughts;
    next.context = t.context;
  }
  if (report.duration) {
    // The provider's count is cumulative; a late frame never moves it back.
    next.seconds = Math.max(meter.seconds ?? 0, report.duration.seconds);
    if (report.duration.contextRatio !== null) next.contextRatio = report.duration.contextRatio;
  }
  return next;
}

export interface LiveCost {
  usd: number;
  eur: number;
}

const MILLION = 1_000_000;

/**
 * The cost of what the meter holds, or null when a needed rate is missing.
 *
 * @param meter The usage so far.
 * @param rates The model's declared tariff.
 * @param seconds For a duration-billed model: the seconds to bill (the
 *   provider's own count when it reported one, else the elapsed time).
 */
export function meterCost(meter: LiveMeter, rates: LiveRates, seconds?: number): LiveCost | null {
  let usd: number;
  if (rates.pricing_unit === 'per_1m_tokens') {
    const needsAudio = meter.audioIn > 0 || meter.audioOut > 0;
    if (
      needsAudio &&
      (rates.audio_input_unit_price === null || rates.audio_output_unit_price === null)
    ) {
      return null;
    }
    usd =
      (meter.textIn * rates.input_unit_price +
        meter.audioIn * (rates.audio_input_unit_price ?? 0) +
        (meter.textOut + meter.thoughts) * rates.output_unit_price +
        meter.audioOut * (rates.audio_output_unit_price ?? 0)) /
      MILLION;
  } else {
    const billed = Math.max(0, seconds ?? meter.seconds ?? 0);
    const perSecond =
      rates.pricing_unit === 'per_audio_minute'
        ? rates.input_unit_price / 60
        : rates.input_unit_price / 3600;
    usd = billed * perSecond;
  }
  return { usd, eur: usd * rates.usd_eur_rate };
}

/** Total tokens in and out, the two figures the chat meter also names. */
export function meterTotals(meter: LiveMeter): { tokensIn: number; tokensOut: number } {
  return {
    tokensIn: meter.textIn + meter.audioIn,
    tokensOut: meter.textOut + meter.audioOut + meter.thoughts,
  };
}

/**
 * The token report of one Gemini `usageMetadata` frame (measured 2026-09-19 on
 * a real session: `promptTokenCount`, `responseTokenCount`, `totalTokenCount`,
 * `promptTokensDetails` / `responseTokensDetails` as `[{modality, tokenCount}]`,
 * `thoughtsTokenCount`). Tokens the details leave unattributed are counted as
 * TEXT: the declarations and the system instruction are text, and text is the
 * cheaper rate — the meter never over-reports on a guess.
 */
export function geminiUsageReport(raw: unknown): LiveUsageReport | null {
  if (typeof raw !== 'object' || raw === null) return null;
  const frame = raw as Record<string, unknown>;
  const prompt = numberOf(frame.promptTokenCount);
  const response = numberOf(frame.responseTokenCount);
  const total = numberOf(frame.totalTokenCount);
  if (prompt === 0 && response === 0 && total === 0) return null;
  const promptAudio = modalityCount(frame.promptTokensDetails, 'AUDIO');
  const responseAudio = modalityCount(frame.responseTokensDetails, 'AUDIO');
  return {
    tokens: {
      textIn: Math.max(0, prompt - promptAudio),
      audioIn: promptAudio,
      textOut: Math.max(0, response - responseAudio),
      audioOut: responseAudio,
      thoughts: numberOf(frame.thoughtsTokenCount),
      context: total || prompt + response,
    },
  };
}

/**
 * The duration report of one GPT-Live `session.usage.updated` event
 * (`usage.seconds`, `context_window.usage_ratio`).
 */
export function openaiUsageReport(raw: unknown): LiveUsageReport | null {
  if (typeof raw !== 'object' || raw === null) return null;
  const event = raw as Record<string, unknown>;
  const usage = event.usage as Record<string, unknown> | undefined;
  const window = event.context_window as Record<string, unknown> | undefined;
  const seconds = usage ? numberOf(usage.seconds) : 0;
  const ratio = window && typeof window.usage_ratio === 'number' ? window.usage_ratio : null;
  if (!usage && ratio === null) return null;
  return {
    duration: {
      seconds,
      contextRatio: ratio === null ? null : Math.min(1, Math.max(0, ratio)),
    },
  };
}

function numberOf(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

function modalityCount(details: unknown, modality: string): number {
  if (!Array.isArray(details)) return 0;
  let count = 0;
  for (const entry of details) {
    if (typeof entry !== 'object' || entry === null) continue;
    const row = entry as Record<string, unknown>;
    if (row.modality === modality) count += numberOf(row.tokenCount);
  }
  return count;
}
