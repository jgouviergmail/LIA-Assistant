'use client';

/**
 * The live session's meter, in the middle of the band (ADR-300 wave 3,
 * owner request): what the session is costing the person on THEIR key,
 * counted in the browser from the provider's own reports and priced by the
 * tariff the API published at the start. Indicative, never recorded, never
 * on the closing card — a display is not an accounting.
 *
 * The chat meter's vocabulary (🟠 IN · 🟢 OUT · euros), so the two read
 * alike, plus the context size: the tokens a token-billed model re-bills on
 * every turn, the share of its window a duration-billed one reports. A cost
 * that needs a rate nobody declared reads as unavailable, never as a partial
 * figure (ADR-185). The wording is `describeMeter`'s, tested without React.
 *
 * Drawn under the last caption (owner placement 2026-09-19), set off from
 * the words by a lateral bar AND a clear gap above (`mt-2`: glued to the
 * caption, the figures read as part of the exchange) — on a line of its own
 * at every width.
 */
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { fallbackLng, type Language } from '@/i18n/settings';
import { describeMeter, formatClock } from '@/lib/live/meter-view';
import { useLiveStore } from '@/stores/liveStore';

/** Whole seconds since `since`, ticking every second; 0 while `since` is null. */
function useElapsedSeconds(since: number | null): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (since === null) return undefined;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [since]);
  return since === null ? 0 : Math.max(0, Math.floor((now - since) / 1000));
}

export function LiveMeter() {
  const { t, i18n } = useTranslation();
  const locale = (i18n.language?.split('-')[0] as Language) || fallbackLng;
  const rates = useLiveStore(state => state.rates);
  const budgetEur = useLiveStore(state => state.budgetEur);
  const meter = useLiveStore(state => state.meter);
  const liveSince = useLiveStore(state => state.liveSince);
  const vendorBilled = useLiveStore(state => state.vendorBilled);
  const durationBilled = rates === null ? vendorBilled : rates.pricing_unit !== 'per_1m_tokens';
  const elapsed = useElapsedSeconds(durationBilled ? liveSince : null);
  if (rates === null) {
    // A vendor-billed session (ElevenLabs Agents, on the person's key): the
    // platform prices nothing of it — the clock alone, and the vendor's own
    // bill once the session ended (owner rule 2026-09-20).
    if (!vendorBilled) return null;
    return (
      <div
        data-testid="live-meter"
        className="mt-2 border-l-2 border-primary/30 pl-2 text-muted-foreground tabular-nums"
        title={t('live.meter.vendor_hint')}
      >
        <span>⏱ {formatClock(elapsed)}</span>
        {' · '}
        <span className="italic">{t('live.meter.vendor_billed')}</span>
        <span className="sr-only"> — {t('live.meter.vendor_hint')}</span>
      </div>
    );
  }

  const view = describeMeter(meter, rates, elapsed, budgetEur, locale);
  return (
    <div
      data-testid="live-meter"
      className="mt-2 border-l-2 border-primary/30 pl-2 text-muted-foreground tabular-nums"
      title={t('live.meter.hint')}
    >
      {view.durationBilled ? (
        <span>⏱ {view.clock}</span>
      ) : (
        <>
          <span className="text-orange-500">🟠 {view.tokensIn} IN</span>{' '}
          <span className="text-green-600">🟢 {view.tokensOut} OUT</span>
        </>
      )}
      {' · '}
      {view.cost === null ? (
        <span className="italic">{t('live.meter.cost_unavailable')}</span>
      ) : (
        <span className="font-semibold text-foreground">{view.cost}</span>
      )}
      {view.context !== null && (
        <>
          {' · '}
          <span>{t('live.meter.context', { value: view.context })}</span>
        </>
      )}
      <span className="sr-only"> — {t('live.meter.hint')}</span>
    </div>
  );
}
