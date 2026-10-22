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
  const dueDate = (iso: string) =>
    new Intl.DateTimeFormat(locale, { dateStyle: 'short' }).format(new Date(iso));

  return (
    <ul className="divide-y divide-border">
      {tickets.map(ticket => (
        <li key={ticket.id}>
          <Link
            href={`/${lng}/dashboard/workboard/${ticket.id}`}
            className="flex min-w-0 flex-col items-start gap-2 rounded-lg py-3 text-sm hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <span className="flex flex-wrap items-center gap-2">
              <Badge variant={lifecycleTone(ticket.status)}>
                {t(`workboard.columns.${ticket.status}`)}
              </Badge>
              {/* Late, the badge names the date it was due (owner request
                  2026-10-21): « en retard » alone said nothing of how late. */}
              {ticket.due_at && isOverdue(ticket) && (
                <Badge variant="destructive">
                  {t('workboard.card.overdue_due', { date: dueDate(ticket.due_at) })}
                </Badge>
              )}
              {ticket.due_at && !isOverdue(ticket) && (
                <span className="text-xs text-muted-foreground">
                  {t('workboard.card.due', { date: dueDate(ticket.due_at) })}
                </span>
              )}
            </span>
            <span className="min-w-0 break-words leading-relaxed">{ticket.title}</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
