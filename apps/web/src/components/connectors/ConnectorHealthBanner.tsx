/**
 * Persistent, in-flow notice that a connector needs re-authorization.
 *
 * The modal (`ConnectorHealthAlert`) is the ATTENTION surface: it interrupts
 * once, then stays quiet for hours (4 h localStorage dedup) and only returns
 * when the set of broken connectors changes. That is the right behaviour for
 * an interruption and the wrong one for a STATE — a user who dismisses it, or
 * who simply was not looking, has nothing left telling them a capability is
 * down until they happen to open the connectors settings.
 *
 * Measured on 2026-07-30: five Google connectors sat in ERROR for a full day
 * while their owner believed everything worked ("le calendrier est bien
 * connecté"). Someone else's assistant was reading his shared calendar and
 * getting nothing, and the diagnosis went the wrong way for an hour.
 *
 * So this banner is deliberately NOT dismissible: it describes a condition the
 * user must fix, it disappears by itself the moment they reconnect, and it
 * stays one slim line that never blocks the page. Together the two surfaces
 * cover both jobs — the modal says "look now", the banner says "still broken".
 *
 * Presentational on purpose (the `ErrorConnectorCard` precedent): the health
 * hook polls, so a second consumer would be a second poll of
 * `/connectors/health` on every interval. `ConnectorHealthAlert` owns the one
 * instance and hands the state down.
 */

'use client';

import { useEffect, useRef } from 'react';
import Link from 'next/link';
import { AlertTriangle } from 'lucide-react';
import type { ConnectorHealthItem } from '@/hooks/useConnectorHealth';
import type { Language } from '@/i18n/settings';
import { Button } from '@/components/ui/button';
import { settingsSectionHref } from '@/lib/settings-sections';

/**
 * Height this banner currently occupies, published on the document root.
 *
 * The chat shell is locked to the dynamic viewport minus a constant for the
 * chrome above it. A banner inserted in that flow without telling it would push
 * the composer below the fold — the constant cannot know about a block that did
 * not exist when it was written. Publishing the MEASURED height (it wraps to
 * two lines on narrow screens) keeps that arithmetic true, and the `0px`
 * fallback means every consumer behaves exactly as before while no banner is
 * mounted.
 */
const BANNER_HEIGHT_VAR = '--connector-banner-h';

interface ConnectorHealthBannerProps {
  /** Connectors in ERROR; the banner renders nothing when empty. */
  connectors: ConnectorHealthItem[];
  /** Active locale — every route in this app is localized. */
  lng: Language;
  /** Translator from the owning container, so there is one i18n instance. */
  t: (key: string, options?: Record<string, unknown>) => string;
  /** True while an OAuth redirect is in flight. */
  reconnecting: boolean;
  /** Starts the reconnection for the single broken connector. */
  onReconnect: (connectorId: string, authorizeUrl: string) => void;
}

export function ConnectorHealthBanner({
  connectors,
  lng,
  t,
  reconnecting,
  onReconnect,
}: ConnectorHealthBannerProps) {
  const bannerRef = useRef<HTMLDivElement>(null);
  const visible = connectors.length > 0;

  // Declared before the early return: hook order must not depend on state.
  useEffect(() => {
    const element = bannerRef.current;
    const root = document.documentElement;
    // jsdom has no ResizeObserver; the variable simply stays unset, which is
    // the same as absent — the consumers' fallback is `0px`.
    if (!element || typeof ResizeObserver === 'undefined') {
      return;
    }
    const observer = new ResizeObserver(() => {
      root.style.setProperty(BANNER_HEIGHT_VAR, `${element.offsetHeight}px`);
    });
    observer.observe(element);
    return () => {
      observer.disconnect();
      // Reconnecting removes the banner: the height it claimed must go with it.
      root.style.removeProperty(BANNER_HEIGHT_VAR);
    };
  }, [visible]);

  if (!visible) {
    return null;
  }

  const single = connectors.length === 1 ? connectors[0] : null;

  return (
    // `status` (polite), not `alert`: the condition can last hours, so it must
    // not preempt whatever a screen-reader user is currently reading. The
    // region carries its own translated name so it is identifiable out of
    // context.
    <div
      ref={bannerRef}
      role="status"
      aria-label={t('settings.connectors.health.banner_label')}
      className="w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-3"
    >
      <div className="flex flex-col gap-2 rounded-lg border border-destructive/25 bg-destructive/10 px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
        <p className="flex items-start gap-2 text-sm text-foreground sm:items-center">
          <AlertTriangle
            aria-hidden="true"
            className="mt-0.5 h-4 w-4 shrink-0 text-destructive sm:mt-0"
          />
          <span>
            {single
              ? t('settings.connectors.health.banner_one', { name: single.display_name })
              : // `total`, never `count`: i18next treats `count` as a plural
                // selector and would look up `banner_many_one`/`_other`, which
                // do not exist. This branch only renders from two upwards, so
                // a fixed plural wording is always the grammatical one.
                t('settings.connectors.health.banner_many', { total: connectors.length })}
          </span>
        </p>
        {single ? (
          <Button
            size="sm"
            variant="outline"
            className="w-full shrink-0 sm:w-auto"
            disabled={reconnecting}
            onClick={() => onReconnect(single.id, single.authorize_url)}
          >
            {reconnecting
              ? t('settings.connectors.health.reconnecting')
              : t('settings.connectors.health.reconnect')}
          </Button>
        ) : (
          // Several broken at once: one reconnection per provider is needed,
          // so the banner sends to the page that lists them instead of
          // arbitrarily picking one.
          <Button asChild size="sm" variant="outline" className="w-full shrink-0 sm:w-auto">
            <Link href={settingsSectionHref(lng, 'connectors')}>
              {t('settings.connectors.health.banner_manage')}
            </Link>
          </Button>
        )}
      </div>
    </div>
  );
}
