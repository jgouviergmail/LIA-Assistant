'use client';

/**
 * The header actions the Alerts hub and the Activity timeline share: the way
 * across to the other view, the actions journal and a refresh — in the same
 * place and at the same height on both pages (owner request 2026-10-21). Two
 * views of one subject, each drawing its own toolbar, read as two subjects.
 *
 * The switch is the solid control, a hub shortcut (ADR-207); the journal and
 * the refresh are its secondaries. A switch to the timeline exists only while
 * the instance serves the timeline (ADR-061): it is absent, never greyed out.
 */

import Link from 'next/link';
import { Bell, ClipboardList, History, RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

/** One height for the three controls — the touch target the tallest needs. */
const CONTROL_CLASS = 'min-h-11 w-full sm:w-auto';

/** The page the actions sit on; the switch leads to the other one. */
export type AlertsView = 'hub' | 'activity';

export function AlertsViewActions({
  lng,
  view,
  switchable,
  busy,
  onRefresh,
  onOpenJournal,
}: {
  lng: string;
  view: AlertsView;
  /** False when the other view is not served on this instance. */
  switchable: boolean;
  /** A read is in flight: the refresh spins and ignores a second press. */
  busy: boolean;
  onRefresh: () => void;
  onOpenJournal?: () => void;
}) {
  const { t } = useTranslation();
  const other =
    view === 'hub'
      ? { href: `/${lng}/dashboard/activity`, Icon: History, label: t('activity.hub_cta') }
      : { href: `/${lng}/dashboard/notifications`, Icon: Bell, label: t('activity.hub_back') };

  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
      {switchable && (
        <Button asChild size="sm" className={CONTROL_CLASS}>
          <Link href={other.href}>
            <other.Icon className="h-4 w-4" aria-hidden="true" />
            {other.label}
          </Link>
        </Button>
      )}
      {/* ADR-263: the timeline tells the STORY of LIA's proactive work and the
          hub what reached the reader; the journal is the RECORD of what its
          capabilities actually did. A reader asking "what did LIA do?" lands
          on either page, so the record is one press away from both. */}
      {onOpenJournal ? (
        <Button variant="outline" size="sm" className={CONTROL_CLASS} onClick={onOpenJournal}>
          <ClipboardList className="h-4 w-4" aria-hidden="true" />
          {t('effects.journal.title')}
        </Button>
      ) : (
        <Button asChild variant="outline" size="sm" className={CONTROL_CLASS}>
          <Link href={`/${lng}/dashboard/actions`}>
            <ClipboardList className="h-4 w-4" aria-hidden="true" />
            {t('effects.journal.title')}
          </Link>
        </Button>
      )}
      <Button
        type="button"
        variant="outline"
        size="sm"
        className={CONTROL_CLASS}
        aria-disabled={busy || undefined}
        onClick={() => {
          // The guard, not the attribute, refuses the second read: a control
          // disabled while it holds focus blurs and leaves the tab order.
          if (!busy) onRefresh();
        }}
      >
        <RefreshCw className={cn('h-4 w-4', busy && 'animate-spin')} aria-hidden="true" />
        {t('common.refresh')}
      </Button>
    </div>
  );
}
