'use client';
import { useId } from 'react';
import { useTranslation } from 'react-i18next';
import { MessageSquareText } from 'lucide-react';
import { TimelineDayGroup } from '@/components/ui/timeline-group';
import { projectSmsDays } from '@/lib/sms/timeline';
import type { SmsMessage } from '@/types/sms';
import type { Language } from '@/i18n/settings';

export function SmsMessageCard({
  message,
  lng,
  timezone,
}: {
  message: SmsMessage;
  lng: Language;
  timezone: string;
}) {
  const { t } = useTranslation();
  const headingId = useId();
  return (
    <article className="min-w-0 space-y-2 p-4 sm:p-5" aria-labelledby={headingId}>
      <div className="flex min-w-0 flex-wrap items-start justify-between gap-2">
        <h3 id={headingId} className="flex min-w-0 items-center gap-2 text-sm font-semibold">
          <MessageSquareText className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
          <span className="break-words">{message.display_name}</span>
        </h3>
        <time dateTime={message.received_at} className="text-xs text-muted-foreground">
          {new Intl.DateTimeFormat(lng, {
            timeZone: timezone,
            dateStyle: 'medium',
            timeStyle: 'short',
          }).format(new Date(message.received_at))}
        </time>
      </div>
      {message.display_name !== message.sender && (
        <p className="break-words text-xs text-muted-foreground">{message.sender}</p>
      )}
      {message.date_kind !== 'received' && (
        <p className="text-xs text-muted-foreground">{t('sms.captured')}</p>
      )}
      <p
        className="whitespace-pre-wrap break-words text-sm leading-relaxed [overflow-wrap:anywhere]"
        dir="auto"
      >
        {message.body}
      </p>
    </article>
  );
}
export function SmsMessageList({
  messages,
  lng,
  timezone,
}: {
  messages: readonly SmsMessage[];
  lng: Language;
  timezone: string;
}) {
  const id = useId();
  return (
    <div className="min-w-0 space-y-6">
      {projectSmsDays(messages, lng, timezone).map(group => (
        <TimelineDayGroup
          key={group.key}
          headingId={`${id}-${group.key}`}
          heading={group.title}
          level={2}
          dayNumber={group.day}
          month={group.month}
        >
          <div className="divide-y divide-border/60">
            {group.messages.map(message => (
              <SmsMessageCard key={message.id} message={message} lng={lng} timezone={timezone} />
            ))}
          </div>
        </TimelineDayGroup>
      ))}
    </div>
  );
}
