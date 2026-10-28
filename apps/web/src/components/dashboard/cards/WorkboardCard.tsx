'use client';

import { DashboardLink as Link } from '../DashboardNavigation';
import { CalendarClock, CircleHelp, LayoutGrid } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Badge } from '@/components/ui/badge';
import { fallbackLng, getIntlLocale, isLanguage, type Language } from '@/i18n/settings';
import { formatNumber } from '@/lib/format';
import { lifecycleTone } from '@/lib/status-tone';
import { cn } from '@/lib/utils';
import { boardHref } from '@/lib/workboard/filters-url';
import { CLOSED_STATUSES, TICKET_STATUSES, type TicketStatus } from '@/types/workboard';
import type {
  CardSection,
  WorkboardData,
  WorkboardPreviews,
  WorkboardTicketItem,
} from '@/types/briefing';
import { BriefingCard } from '../BriefingCard';

interface WorkboardCardProps {
  section: CardSection<WorkboardData>;
  isRefreshing: boolean;
  onRefresh: () => void;
  staggerIndex?: number;
}

/** The open columns, derived so the « open » link matches the « open » count. */
const OPEN_STATUSES: TicketStatus[] = TICKET_STATUSES.filter(
  status => !CLOSED_STATUSES.includes(status)
);

const FOCUS = 'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring';

/**
 * Workboard card (ADR-276 on the dashboard).
 *
 * What is on the person's board: five EXACT counts (ADR-185) — what they hold
 * (« my tickets », never a ticket LIA or a peer holds, late or not — owner
 * request 2026-10-21), held by LIA, held by peers, late, open — each a link
 * into the board narrowed to the set it counts, then two tickets from each
 * set, each a link to the ticket itself. Read-only: the board owns the writes,
 * and a second place to move a ticket would be a second place to get the
 * rights wrong.
 *
 * Hidden (`not_configured`) when the instance switched the workboard off; the
 * empty state is a board with no open ticket at all.
 */
export function WorkboardCard({
  section,
  isRefreshing,
  onRefresh,
  staggerIndex,
}: WorkboardCardProps) {
  const { i18n } = useTranslation();
  const lng = (i18n.language || 'fr').split('-')[0];
  return (
    <BriefingCard<WorkboardData>
      titleKey="dashboard.briefing.cards.workboard.title"
      icon={<LayoutGrid className="h-5 w-5" />}
      tone="orange"
      section={section}
      isRefreshing={isRefreshing}
      onRefresh={onRefresh}
      emptyStateKey="dashboard.briefing.cards.workboard.empty"
      renderContent={data => <WorkboardContent data={data} lng={lng} />}
      staggerIndex={staggerIndex}
    />
  );
}

interface Figure {
  key: keyof WorkboardPreviews;
  label: string;
  value: number;
  href: string;
  /** Ink of a non-zero value: something to act on reads in its tone. */
  tone?: string;
}

function WorkboardContent({ data, lng }: { data: WorkboardData; lng: string }) {
  const { t } = useTranslation();
  const language: Language = isLanguage(lng) ? lng : fallbackLng;
  const figures: Figure[] = [
    {
      key: 'held_by_lia',
      label: t('settings.workboard.tile_lia'),
      value: data.held_by_lia,
      href: boardHref(lng, { assignee: 'lia', status: OPEN_STATUSES }),
    },
    {
      key: 'overdue',
      label: t('settings.workboard.tile_overdue'),
      value: data.overdue,
      href: boardHref(lng, { overdue: true }),
      tone: 'text-destructive',
    },
    {
      key: 'open_total',
      label: t('dashboard.briefing.cards.workboard.tile_open'),
      value: data.open_total,
      href: boardHref(lng, { status: OPEN_STATUSES }),
    },
  ];
  // Old cached bundles have no peer aggregate: absence cannot mean zero.
  if (data.held_by_peers != null) {
    figures.splice(1, 0, {
      key: 'held_by_peers',
      label: t('dashboard.briefing.cards.workboard.held_by_peers'),
      value: data.held_by_peers,
      href: boardHref(lng, { assignee: 'peer', status: OPEN_STATUSES }),
    });
  }
  // Nor a « my tickets » count: a cache predating it shows no tile rather than
  // a zero nobody counted. It leads — the person's own work first.
  if (data.held_by_me != null) {
    figures.unshift({
      key: 'held_by_me',
      label: t('settings.workboard.tile_mine'),
      value: data.held_by_me,
      href: boardHref(lng, { assignee: 'me', status: OPEN_STATUSES }),
      tone: 'text-primary',
    });
  }

  return (
    <div className="@container flex flex-col gap-3">
      <ul
        aria-label={t('settings.workboard.glance')}
        className={cn(
          'grid grid-cols-2 gap-1.5',
          figures.length === 5 ? '@min-[19rem]:grid-cols-5' : '@min-[19rem]:grid-cols-4'
        )}
      >
        {figures.map(figure => (
          <li key={figure.key}>
            <Link
              href={figure.href}
              className={cn(
                'flex min-h-11 h-full flex-col items-center justify-start rounded-lg border border-border bg-background/60 [:where(html.dark[data-oled])_&]:bg-transparent px-1 py-1.5 text-center transition-colors hover:bg-muted/60',
                FOCUS
              )}
            >
              <span
                className={cn(
                  'text-lg font-semibold leading-none tabular-nums',
                  figure.value > 0 && figure.tone
                )}
              >
                {formatNumber(figure.value, language)}
              </span>
              <span className="mt-1 text-px-11 leading-tight text-muted-foreground break-words">
                {figure.label}
              </span>
            </Link>
          </li>
        ))}
      </ul>

      {data.previews && <GroupedTickets figures={figures} groups={data.previews} lng={lng} />}
      {data.needs_me === 0 && (
        <p className="text-sm text-muted-foreground italic">
          {t('settings.workboard.nothing_waiting')}
        </p>
      )}
    </div>
  );
}

function GroupedTickets({
  figures,
  groups,
  lng,
}: {
  figures: Figure[];
  groups: WorkboardPreviews;
  lng: string;
}) {
  return (
    <div className="space-y-3 border-t border-border pt-4">
      {figures.map(figure => {
        // At most two per set, as the server bounds them; a group a cached
        // bundle predates reads empty.
        const tickets = (groups[figure.key] ?? []).slice(0, 2);
        if (tickets.length === 0) return null;
        return (
          <section key={figure.key} className="space-y-1">
            <h4 className="flex items-center gap-2 text-xs font-medium text-foreground/90">
              <LayoutGrid className="h-3.5 w-3.5 shrink-0 text-primary" aria-hidden="true" />
              {figure.label}
            </h4>
            <TicketList label={figure.label} tickets={tickets} lng={lng} />
          </section>
        );
      })}
    </div>
  );
}

function TicketList({
  label,
  tickets,
  lng,
}: {
  label: string;
  tickets: WorkboardTicketItem[];
  lng: string;
}) {
  const { t } = useTranslation();
  const locale = getIntlLocale(isLanguage(lng) ? lng : fallbackLng);
  return (
    <ul aria-label={label}>
      {tickets.map(ticket => (
        <li key={ticket.id} className="border-b border-border py-1 last:border-0">
          <Link
            href={`/${lng}/dashboard/workboard/${encodeURIComponent(ticket.id)}`}
            prefetch={false}
            className={cn(
              'flex min-h-11 flex-col items-start gap-1 rounded-md px-2 py-1 text-sm hover:bg-muted/60',
              FOCUS
            )}
          >
            <span className="line-clamp-2 break-words font-semibold text-foreground/90">
              {ticket.title}
            </span>
            <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
              <span className="flex items-center gap-1.5 text-orange-700 dark:text-orange-300">
                <CircleHelp className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                <Badge variant={ticket.overdue ? 'destructive' : lifecycleTone(ticket.status)}>
                  {t(
                    ticket.overdue ? 'workboard.card.overdue' : `workboard.columns.${ticket.status}`
                  )}
                </Badge>
              </span>
              {ticket.due_at && !ticket.overdue && (
                <span className="flex items-center gap-1.5 tabular-nums">
                  <CalendarClock className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                  <time dateTime={ticket.due_at}>
                    {new Intl.DateTimeFormat(locale, { dateStyle: 'short' }).format(
                      new Date(ticket.due_at)
                    )}
                  </time>
                </span>
              )}
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
