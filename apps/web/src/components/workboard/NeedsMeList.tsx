'use client';
/**
 * The tickets that need THIS person (ADR-276) — the hub's workboard section.
 *
 * A ticket is here for one of two reasons: LIA stopped a run waiting for an
 * answer, or something on the board is past its due date. Both are decisions to
 * take, which is what the notifications hub is for — never a count of
 * everything the account owns.
 *
 * Read-only, and every row is a LINK to the ticket: the board owns the writes,
 * and a second place to change a status would be a second place to get the
 * rights wrong.
 */
import Link from 'next/link';
import { LayoutGrid } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Badge } from '@/components/ui/badge';
import { getIntlLocale, type Language } from '@/i18n/settings';
import { lifecycleTone } from '@/lib/status-tone';
import { isOverdue } from '@/lib/workboard/display';
import type { TicketRow } from '@/types/workboard';

export interface NeedsMeListProps {
  tickets: readonly TicketRow[];
  lng: Language;
}

export function NeedsMeList({ tickets, lng }: NeedsMeListProps) {
  const { t } = useTranslation();
  const locale = getIntlLocale(lng);

  return (
    <ul className="space-y-2">
      {tickets.map(ticket => (
        <li key={ticket.id}>
          <Link
            href={`/${lng}/dashboard/workboard/${ticket.id}`}
            className="flex flex-wrap items-center gap-2 rounded-lg border border-border/50 p-2 text-sm hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <LayoutGrid className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
            <span className="min-w-0 flex-1 truncate">{ticket.title}</span>
            <Badge variant={lifecycleTone(ticket.status)}>
              {t(`workboard.columns.${ticket.status}`)}
            </Badge>
            {isOverdue(ticket) && (
              <Badge variant="destructive">{t('workboard.card.overdue')}</Badge>
            )}
            {ticket.due_at && !isOverdue(ticket) && (
              <span className="text-xs text-muted-foreground">
                {t('workboard.card.due', {
                  date: new Intl.DateTimeFormat(locale, { dateStyle: 'short' }).format(
                    new Date(ticket.due_at)
                  ),
                })}
              </span>
            )}
          </Link>
        </li>
      ))}
    </ul>
  );
}
