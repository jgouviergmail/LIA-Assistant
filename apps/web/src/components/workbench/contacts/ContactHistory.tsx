'use client';

/**
 * ContactHistory — what a contact and the person exchanged (ADR-369, lot 14).
 *
 * The latest mail each way and the latest meetings each organised, side by side where its own
 * column has the room: a panel per source, a rubrique per list, each cut from the next by a line,
 * its rows drawn plain (owner, 2026-11-06: a rule between two of them got in the way of reading),
 * telling when as the mail list does. Each line opens in its own tool. A source says why it
 * has nothing: no connector leaves its column out, a read that failed says so, and neither is ever
 * shown as nothing found. Meetings whose organiser nobody named stand in one list rather than in a
 * guessed one, and how far back the calendar was read is said: a window is not the whole calendar.
 *
 * Since 2026-11-07 the contact's numbers are asked too: the calls LIA placed to them open in the
 * calls list, saying how each went, and the texts they sent open on the SMS page, each showing how
 * it begins. A contact with numbers alone has exchanges; a source the contact gave nothing to look
 * under, or that nothing feeds, leaves its column out, and a bound that hid older records is said.
 */
import {
  ArrowDownLeft,
  ArrowUpRight,
  CalendarCheck,
  CalendarDays,
  History,
  Mail,
  MessageSquareText,
  PhoneOutgoing,
  UserRound,
  Users,
  type LucideIcon,
} from '@/lib/icons';
import Link from 'next/link';
import type { ReactNode } from 'react';

import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { useAuth } from '@/hooks/useAuth';
import { useWorkbenchItem } from '@/hooks/useWorkbenchItem';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { formatNumber } from '@/lib/format';
import {
  historyCallHref,
  historyDay,
  historyMailHref,
  historyMeetingHref,
  historyTextHref,
} from '@/lib/workbench/contacts';
import type {
  ContactHistoryCall,
  ContactHistoryMail,
  ContactHistoryMeeting,
  ContactHistorySource,
  ContactHistoryText,
  WorkbenchContactHistory,
} from '@/lib/workbench/types';

const HISTORY_PATH = '/workbench/contacts/history';
const DAYS_PER_MONTH = 30;

export interface ContactHistoryProps {
  lng: Language;
  /** How the contact is named; empty when it has no name. */
  name: string;
  /** Its addresses, within the published bound. */
  addresses: readonly string[];
  /** Its numbers, within the published bound. */
  phones: readonly string[];
}

interface Line {
  key: string;
  label: string;
  /** A word beside the label: how a call went. */
  note?: string;
  when: string | null;
  href: string;
}

/**
 * Whether a source has a column: one that was read, or failed. One nothing feeds, or nobody asked,
 * has nothing to say, and neither has one the answer does not name.
 */
function shown(source: ContactHistorySource | undefined): boolean {
  return source === 'used' || source === 'unavailable';
}

function Lines({
  icon: Icon,
  title,
  empty,
  lines,
}: {
  icon: LucideIcon;
  title: string;
  empty: string;
  lines: readonly Line[];
}) {
  return (
    <div className="space-y-1 px-3 py-2.5">
      <h5 className="flex items-center gap-1.5 text-xs font-semibold">
        <Icon className="h-3.5 w-3.5 shrink-0 text-primary" aria-hidden="true" />
        <span className="min-w-0 truncate">{title}</span>
      </h5>
      {lines.length === 0 ? (
        <p className="py-1 text-sm text-muted-foreground">{empty}</p>
      ) : (
        <ul>
          {lines.map(line => (
            <li key={line.key}>
              <Link
                href={line.href}
                title={line.label}
                className="-mx-1 flex min-h-9 items-center gap-3 rounded-md px-1 text-sm transition-colors hover:bg-primary/10 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <span className="min-w-0 flex-1 truncate">{line.label}</span>
                {line.note && (
                  <span className="shrink-0 text-xs text-muted-foreground">{line.note}</span>
                )}
                {line.when && (
                  <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                    {line.when}
                  </span>
                )}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Column({
  icon: Icon,
  title,
  children,
}: {
  icon: LucideIcon;
  title: string;
  children: ReactNode;
}) {
  return (
    <section aria-label={title} className="min-w-0 rounded-lg border bg-card">
      <h4 className="flex items-center gap-2 rounded-t-lg border-b bg-muted/60 px-3 py-2 text-sm font-semibold">
        <Icon className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
        {title}
      </h4>
      <div className="divide-y">{children}</div>
    </section>
  );
}

/** The words of the history, and a line's day, in the reader's zone and language. */
interface Reading {
  word: (key: string, values?: Record<string, string | number>) => string;
  /** A count in the reader's own writing. */
  count: (value: number) => string;
  mailLines: (rows: readonly ContactHistoryMail[], sent: boolean) => Line[];
  meetingLines: (rows: readonly ContactHistoryMeeting[]) => Line[];
  callLines: (rows: readonly ContactHistoryCall[]) => Line[];
  textLines: (rows: readonly ContactHistoryText[]) => Line[];
}

function MailColumn({
  item,
  reading: { word, mailLines },
}: {
  item: WorkbenchContactHistory;
  reading: Reading;
}) {
  return (
    <Column icon={Mail} title={word('mail')}>
      {item.mail === 'unavailable' ? (
        <p className="p-3 text-sm text-muted-foreground">{word('mail_unavailable')}</p>
      ) : (
        <>
          <Lines
            icon={ArrowDownLeft}
            title={word('received')}
            empty={word('no_received')}
            lines={mailLines(item.received, false)}
          />
          <Lines
            icon={ArrowUpRight}
            title={word('sent')}
            empty={word('no_sent')}
            lines={mailLines(item.sent, true)}
          />
        </>
      )}
    </Column>
  );
}

function MeetingColumn({
  item,
  name,
  reading: { word, meetingLines },
}: {
  item: WorkbenchContactHistory;
  name: string;
  reading: Reading;
}) {
  if (item.calendar === 'unavailable') {
    return (
      <Column icon={CalendarDays} title={word('meetings')}>
        <p className="p-3 text-sm text-muted-foreground">{word('calendar_unavailable')}</p>
      </Column>
    );
  }
  // With no organiser named at all, two empty lists would claim what nobody knows.
  const unsorted =
    item.shared.length > 0 &&
    item.organized_by_them.length === 0 &&
    item.organized_by_you.length === 0;
  return (
    <Column icon={CalendarDays} title={word('meetings')}>
      {!unsorted && (
        <>
          <Lines
            icon={UserRound}
            title={name ? word('by_them', { name }) : word('by_them_unnamed')}
            empty={word('no_meeting')}
            lines={meetingLines(item.organized_by_them)}
          />
          <Lines
            icon={CalendarCheck}
            title={word('by_you')}
            empty={word('no_meeting')}
            lines={meetingLines(item.organized_by_you)}
          />
        </>
      )}
      {item.shared.length > 0 && (
        <Lines
          icon={Users}
          title={word('shared')}
          empty={word('no_meeting')}
          lines={meetingLines(item.shared)}
        />
      )}
      <p className="px-3 py-2 text-xs text-muted-foreground">
        {word('window', { months: Math.round(item.meetings_window_days / DAYS_PER_MONTH) })}
        {item.meetings_cut && ` ${word('window_cut')}`}
      </p>
    </Column>
  );
}

/** The calls LIA placed to the contact's numbers: never the person's own calls. */
function CallsColumn({
  item,
  reading: { word, count, callLines },
}: {
  item: WorkbenchContactHistory;
  reading: Reading;
}) {
  return (
    <Column icon={PhoneOutgoing} title={word('calls')}>
      {item.telephony === 'unavailable' ? (
        <p className="p-3 text-sm text-muted-foreground">{word('calls_unavailable')}</p>
      ) : (
        <>
          <Lines
            icon={PhoneOutgoing}
            title={word('placed')}
            empty={word('no_call')}
            lines={callLines(item.calls)}
          />
          {item.calls_cut && (
            <p className="px-3 py-2 text-xs text-muted-foreground">
              {word('calls_cut', { calls: count(item.calls_window) })}
            </p>
          )}
        </>
      )}
    </Column>
  );
}

/** The texts the contact's numbers sent the person. */
function TextsColumn({
  item,
  reading: { word, count, textLines },
}: {
  item: WorkbenchContactHistory;
  reading: Reading;
}) {
  return (
    <Column icon={MessageSquareText} title={word('texts')}>
      {item.sms === 'unavailable' ? (
        <p className="p-3 text-sm text-muted-foreground">{word('texts_unavailable')}</p>
      ) : (
        <>
          <Lines
            icon={ArrowDownLeft}
            title={word('texts_received')}
            empty={word('no_text')}
            lines={textLines(item.texts)}
          />
          {item.texts_cut && (
            <p className="px-3 py-2 text-xs text-muted-foreground">
              {word('texts_cut', { senders: count(item.texts_window) })}
            </p>
          )}
        </>
      )}
    </Column>
  );
}

export function ContactHistory({ lng, name, addresses, phones }: ContactHistoryProps) {
  const { t } = useTranslation(lng);
  const { user } = useAuth();
  const zone = user?.timezone;
  const asked = addresses.length > 0 || phones.length > 0;
  const { item, loading, refresh } = useWorkbenchItem<WorkbenchContactHistory>(
    asked ? HISTORY_PATH : null,
    { address: addresses, phone: phones }
  );
  const word = (key: string, values?: Record<string, string | number>) =>
    t(`workbench.contacts.history.${key}`, values);

  if (!asked) return null;
  if (loading) return <Skeleton className="h-40 w-full" />;
  if (!item) {
    return (
      <p className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
        {word('failed')}
        <Button variant="link" size="sm" className="h-auto p-0" onClick={() => void refresh()}>
          {t('workbench.states.retry')}
        </Button>
      </p>
    );
  }
  if (![item.mail, item.calendar, item.telephony, item.sms].some(shown)) return null;

  const reading: Reading = {
    word,
    count: value => formatNumber(value, lng),
    mailLines: (rows, sent) =>
      rows.map(row => ({
        key: row.id,
        label: row.subject || t('workbench.mail.no_subject'),
        // What happened next in its conversation (ADR-379), in the mail tool's own words.
        note: row.reply ? t(`workbench.mail.${row.reply}`) : undefined,
        when: historyDay(row, new Date(), zone, lng),
        href: historyMailHref(row.id, sent, lng),
      })),
    meetingLines: rows =>
      rows.map(row => ({
        key: row.id,
        label: row.title || t('workbench.calendar.no_title'),
        when: historyDay(row, new Date(), zone, lng),
        href: historyMeetingHref(row, lng),
      })),
    callLines: rows =>
      rows.map(row => ({
        key: row.id,
        label: row.purpose || word('call_no_purpose'),
        note: row.outcome
          ? t(`settings.telephony.calls.outcome.${row.outcome}`)
          : t(`settings.telephony.calls.status.${row.status}`),
        when: historyDay(row, new Date(), zone, lng),
        href: historyCallHref(row.id, lng),
      })),
    textLines: rows =>
      rows.map(row => ({
        key: row.id,
        label: row.truncated ? `${row.excerpt}…` : row.excerpt,
        when: historyDay(row, new Date(), zone, lng),
        href: historyTextHref(row.id, lng),
      })),
  };

  return (
    <section aria-label={word('title')} className="@container min-w-0 space-y-2">
      <h3 className="flex items-center gap-2 text-sm font-semibold">
        <History className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
        {word('title')}
      </h3>
      <div className="grid items-start gap-3 @2xl:grid-cols-2">
        {shown(item.mail) && <MailColumn item={item} reading={reading} />}
        {shown(item.calendar) && <MeetingColumn item={item} name={name} reading={reading} />}
        {shown(item.telephony) && <CallsColumn item={item} reading={reading} />}
        {shown(item.sms) && <TextsColumn item={item} reading={reading} />}
      </div>
    </section>
  );
}
