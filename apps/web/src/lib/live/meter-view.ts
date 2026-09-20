/**
 * What the banner's meter SAYS, computed apart from the component (ADR-300
 * wave 3): the cost line (with the ceiling beside it when one is set, or the
 * word for an unavailable cost), the context figure (tokens for a
 * token-billed model, a percentage of the window for a duration-billed one)
 * and the clock. Pure, so the wording is tested without React.
 */
import type { Language } from '@/i18n/settings';
import { formatEuro, formatNumber } from '@/lib/format';

import { meterCost, meterTotals, type LiveMeter } from './meter';
import type { LiveRates } from './types';

export interface LiveMeterView {
  /** A duration-billed model shows its clock, a token-billed one its tokens. */
  durationBilled: boolean;
  /** The seconds billed so far (duration-billed): the provider's count or the clock, whichever is larger. */
  seconds: number;
  clock: string;
  tokensIn: string;
  tokensOut: string;
  /** The cost, with the ceiling beside it; null when a needed rate is not declared. */
  cost: string | null;
  /** The context size (tokens) or the window's share (percent), null before any report. */
  context: string | null;
}

/** `m:ss` of whole seconds. */
export function formatClock(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return `${minutes}:${rest.toString().padStart(2, '0')}`;
}

/**
 * Describe the meter for the band.
 *
 * @param meter The provider's reports, folded.
 * @param rates The model's declared tariff.
 * @param elapsed Seconds since the session went live (the clock).
 * @param budgetEur The connector's ceiling, or null.
 * @param locale The person's locale, for the figures.
 */
export function describeMeter(
  meter: LiveMeter,
  rates: LiveRates,
  elapsed: number,
  budgetEur: number | null,
  locale: Language
): LiveMeterView {
  const durationBilled = rates.pricing_unit !== 'per_1m_tokens';
  // A duration-billed model: the wall clock ticks every second, the
  // provider's own count corrects it upward when it arrives.
  const seconds = durationBilled ? Math.max(meter.seconds ?? 0, elapsed) : 0;
  const cost = meterCost(meter, rates, durationBilled ? seconds : undefined);
  const totals = meterTotals(meter);
  return {
    durationBilled,
    seconds,
    clock: formatClock(seconds),
    tokensIn: formatNumber(totals.tokensIn, locale),
    tokensOut: formatNumber(totals.tokensOut, locale),
    cost: cost === null ? null : costLine(cost.eur, budgetEur, locale),
    context: contextFigure(meter, durationBilled, locale),
  };
}

/** « 0,0450 € », or « 0,0450 € / 2,00 € » beside the ceiling the person set. */
function costLine(eur: number, budgetEur: number | null, locale: Language): string {
  const spent = formatEuro(eur, 4, locale);
  return budgetEur === null ? spent : `${spent} / ${formatEuro(budgetEur, 2, locale)}`;
}

function contextFigure(meter: LiveMeter, durationBilled: boolean, locale: Language): string | null {
  if (durationBilled) {
    return meter.contextRatio === null ? null : `${Math.round(meter.contextRatio * 100)} %`;
  }
  return meter.context === null ? null : formatNumber(meter.context, locale);
}
