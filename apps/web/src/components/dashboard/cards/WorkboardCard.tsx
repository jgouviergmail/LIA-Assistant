'use client';

import Link from 'next/link';
import { LayoutGrid } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Badge } from '@/components/ui/badge';
import { fallbackLng, getIntlLocale, isLanguage, type Language } from '@/i18n/settings';
import { formatNumber } from '@/lib/format';
import { lifecycleTone } from '@/lib/status-tone';
import { cn } from '@/lib/utils';
import { boardHref } from '@/lib/workboard/filters-url';
import { CLOSED_STATUSES, TICKET_STATUSES, type TicketStatus } from '@/types/workboard';
import type { CardSection, WorkboardData } from '@/types/briefing';
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
 * What on the person's board needs them: four EXACT counts (ADR-185) — waiting
 * on them, held by LIA, late, open — each a link into the board already
 * narrowed to the set it counts, then the first tickets waiting on them, each a
 * link to the ticket itself. Read-only: the board owns the writes, and a second
 * place to move a ticket would be a second place to get the rights wrong.
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
  key: string;
  label: string;
  value: number;
  href: string;
  /** Ink of a non-zero value: something to act on reads in its tone. */
  tone?: string;
}

function WorkboardContent({ data, lng }: { data: WorkboardData; lng: string }) {
  const { t } = useTranslation();
  const language: Language = isLanguage(lng) ? lng : fallbackLng;
  const locale = getIntlLocale(language);
  // The « needs me » set has no board filter of its own (it spans a column
  // AND a due date), so it opens the whole board, as the settings tile does.
  const figures: Figure[] = [
    {
      key: 'needs_me',
      label: t('settings.workboard.tile_needs_me'),
      value: data.needs_me,
      href: boardHref(lng),
      tone: 'text-primary',
    },
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
  const more = data.needs_me - data.items.length;

  return (
    <div className="@container flex flex-col gap-3">
      <ul
        aria-label={t('settings.workboard.glance')}
        className="grid grid-cols-2 gap-1.5 @min-[19rem]:grid-cols-4"
      >
        {figures.map(figure => (
          <li key={figure.key}>
            <Link
              href={figure.href}
              className={cn(
                'flex min-h-11 h-full flex-col items-center justify-center rounded-lg border border-border/50 bg-background/60 px-1 py-1.5 text-center transition-colors hover:bg-muted/60',
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

      {data.needs_me === 0 ? (
        <p className="text-sm text-muted-foreground italic">
          {t('settings.workboard.nothing_waiting')}
        </p>
      ) : (
        <div>
          <ul aria-label={t('settings.workboard.tile_needs_me')} className="space-y-0.5">
            {data.items.map(ticket => (
              <li key={ticket.id}>
                <Link
                  href={`/${lng}/dashboard/workboard/${ticket.id}`}
                  className={cn(
                    '-mx-1.5 flex min-h-10 items-center gap-2 rounded-md px-1.5 py-1 text-sm hover:bg-muted/60',
                    FOCUS
                  )}
                >
                  <span className="min-w-0 flex-1 truncate font-medium text-foreground/90">
                    {ticket.title}
                  </span>
                  {ticket.overdue ? (
                    <Badge variant="destructive" className="shrink-0">
                      {t('workboard.card.overdue')}
                    </Badge>
                  ) : (
                    <Badge variant={lifecycleTone(ticket.status)} className="shrink-0">
                      {t(`workboard.columns.${ticket.status}`)}
                    </Badge>
                  )}
                  {ticket.due_at && !ticket.overdue && (
                    <span className="hidden shrink-0 text-xs text-muted-foreground tabular-nums @min-[19rem]:inline">
                      {new Intl.DateTimeFormat(locale, { dateStyle: 'short' }).format(
                        new Date(ticket.due_at)
                      )}
                    </span>
                  )}
                </Link>
              </li>
            ))}
          </ul>
          {more > 0 && (
            <Link
              href={boardHref(lng)}
              className={cn(
                'mt-1 inline-flex min-h-10 items-center rounded-sm text-xs font-medium text-primary hover:underline',
                FOCUS
              )}
            >
              {t('dashboard.briefing.cards.workboard.more', { count: more })}
            </Link>
          )}
        </div>
      )}
    </div>
  );
}
