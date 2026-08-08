'use client';

import { useTranslation } from 'react-i18next';
import {
  ArrowLeft,
  ArrowUpRight,
  BatteryLow,
  CalendarClock,
  CalendarX,
  Gauge,
  Link2Off,
  Mail,
  PackageOpen,
  ShieldAlert,
  Timer,
} from 'lucide-react';

import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';
import type { Language } from '@/i18n/settings';

/**
 * Anonymous read of whether a demonstrator link should be shown.
 *
 * Deliberately NOT `useApiQuery`: that hook goes through `apiClient`, which
 * forces `credentials: 'include'` by BFF contract and refuses a caller
 * override. This component renders on `/demo`, whose honesty strip states
 * "no connected account" — sending the visitor's session cookie to learn
 * whether a public link exists would make that displayed claim false. Same
 * credential-less contract, and same reason, as `trackShowroomEvent`.
 *
 * The showroom's zero-API oracle allows this ONE endpoint explicitly (see
 * `e2e/smoke/public-demo-showroom.spec.ts`): it is a read-only, enum-shaped,
 * cookie-less public read, and nothing about the visitor travels with it.
 */
const PUBLIC_DEMO_LINK_ENDPOINT = '/api/v1/product/public-demo-link';

interface PublicDemoLink {
  enabled: boolean;
  url: string | null;
}

interface LiveDemoInvitationProps {
  lng: string;
}

/**
 * Invitation to the live demonstrator — limitations first, link last.
 *
 * The reading order is the design: a visitor must know what the instance is
 * (and is not) BEFORE reaching it. Putting the button after the list is not
 * decoration; it is the commitment being kept.
 *
 * It sits next to the guided missions rather than on a page of its own: the
 * guided experience remains the base, the live instance is the complement,
 * and the choice happens in one place.
 */
export function LiveDemoInvitation({ lng }: LiveDemoInvitationProps) {
  const { t } = useTranslation();
  const [data, setData] = useState<PublicDemoLink | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    // Cookie-less by contract: apiClient cannot omit credentials (BFF), and
    // this page promises that no connected account is involved. See the
    // constant's docstring above.
    fetch(`${process.env.NEXT_PUBLIC_API_URL || ''}${PUBLIC_DEMO_LINK_ENDPOINT}`, {
      credentials: 'omit',
      signal: controller.signal,
    })
      .then(response => (response.ok ? (response.json() as Promise<PublicDemoLink>) : null))
      .then(payload => setData(payload))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, []);

  // Nothing while unknown: a block that appears late would push the guided
  // missions down under the reader's eyes.
  if (loading || !data?.enabled || !data.url) return null;

  // Order is the message. "It is a reduced edition" comes first: a visitor
  // who meets a missing feature without being told decides the product is
  // unfinished, and no later sentence takes that back.
  const limits = [
    { key: 'reduced_edition', icon: PackageOpen },
    { key: 'degraded_performance', icon: Timer },
    { key: 'ephemeral', icon: CalendarClock },
    { key: 'no_sensitive_data', icon: ShieldAlert },
    { key: 'no_connectors', icon: Link2Off },
    { key: 'account_quota', icon: Gauge },
    { key: 'daily_capacity', icon: BatteryLow },
    { key: 'availability', icon: CalendarX },
    { key: 'email_required', icon: Mail },
  ] as const;

  return (
    <section
      className="mx-auto w-full max-w-5xl rounded-xl border border-border bg-muted/20 p-5 sm:p-6"
      aria-labelledby="live-demo-invitation-title"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2
          id="live-demo-invitation-title"
          className="flex items-center gap-2 text-lg font-semibold"
        >
          <ArrowUpRight className="h-5 w-5 text-primary" aria-hidden="true" />
          {t('showroom.live_invitation.title')}
        </h2>
        {/* Same way out as the guided missions: a visitor who lands here and
            changes their mind must not have to use the browser's back button.
            A plain anchor, like its twin — a client-side push would carry the
            unhydrated null session onto the landing. */}
        <Button asChild type="button" variant="ghost" size="sm">
          <a
            href={buildLocalizedPath('/', lng as Language)}
            data-testid="live-invitation-back-home"
          >
            <ArrowLeft className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
            {t('showroom.back_home')}
          </a>
        </Button>
      </div>

      <p className="mt-2 text-sm text-muted-foreground">
        {t('showroom.live_invitation.intro')}
      </p>

      <ul className="mt-4 grid gap-2.5 sm:grid-cols-2 sm:gap-x-8">
        {limits.map(({ key, icon: Icon }) => (
          <li key={key} className="flex items-start gap-2.5 text-sm">
            <Icon className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
            <span>{t(`showroom.live_invitation.limits.${key}`)}</span>
          </li>
        ))}
      </ul>

      <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <a
          href={buildLocalizedPath('/terms', lng as Language)}
          className="text-xs text-muted-foreground underline underline-offset-4 hover:text-foreground"
        >
          {t('showroom.live_invitation.terms_link')}
        </a>
        <Button asChild className="sm:w-auto">
          <a
            href={data.url}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={t('showroom.live_invitation.cta')}
          >
            {t('showroom.live_invitation.cta')}
            <ArrowUpRight className="ml-1.5 h-4 w-4" aria-hidden="true" />
          </a>
        </Button>
      </div>
    </section>
  );
}
