'use client';
import { useId, type ReactNode } from 'react';
import { MessageSquareText } from 'lucide-react';
import { TimelineDayGroup } from '@/components/ui/timeline-group';
import { projectSmsDays } from '@/lib/sms/timeline';
import { cn } from '@/lib/utils';
import { SmsEraseButton, smsDayEraseScope } from './SmsErasure';
import type { SmsMessage } from '@/types/sms';
import type { Language } from '@/i18n/settings';

export function SmsMessageCard({
  message,
  lng,
  timezone,
  className,
  title,
}: {
  message: SmsMessage;
  lng: Language;
  timezone: string;
  /** Padding override, for a host that already frames the message as a row. */
  className?: string;
  /**
   * The host's own title line, in place of the sender and date header: a
   * relationship's section already names the person, so its rows are titled
   * by WHEN, like every other row of that card (owner request 2026-10-21).
   */
  title?: ReactNode;
}) {
  const headingId = useId();
  return (
    <article className={cn('min-w-0 space-y-2 p-4 sm:p-5', className)} aria-labelledby={headingId}>
      {title ? (
        <h3 id={headingId} className="flex min-w-0 flex-wrap items-baseline gap-2">
          {title}
        </h3>
      ) : (
        <>
          <div className="flex min-w-0 flex-wrap items-center justify-between gap-x-3 gap-y-1">
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
        </>
      )}
      {/* The delete control sits in the bottom-right corner, on the body's last
          line: stacked under the date it made the header three times taller
          than its title and pushed the message away from its sender. */}
      <div className="flex min-w-0 items-end gap-2">
        <p
          className="min-w-0 flex-1 whitespace-pre-wrap break-words text-sm leading-relaxed [overflow-wrap:anywhere]"
          dir="auto"
        >
          {message.body}
        </p>
        <SmsEraseButton
          kind="message"
          target={message.display_name}
          scope={() => ({ message_ids: [message.id] })}
          className="-my-1.5 shrink-0"
        />
      </div>
    </article>
  );
}
export function SmsMessageList({
  messages,
  lng,
  timezone,
  eraseDays = false,
  surface,
}: {
  messages: readonly SmsMessage[];
  lng: Language;
  timezone: string;
  eraseDays?: boolean;
  /** `background` inside a card-coloured fold, so the days still alternate with it. */
  surface?: 'card' | 'background';
}) {
  const id = useId();
  return (
    <div className="min-w-0 space-y-6">
      {projectSmsDays(messages, lng, timezone).map(group => (
        <TimelineDayGroup
          key={group.key}
          headingId={`${id}-${group.key}`}
          heading={
            <span className="flex min-w-0 flex-wrap items-center gap-3">
              <span>{group.title}</span>
              {eraseDays && (
                <SmsEraseButton
                  kind="day"
                  target={group.title}
                  scope={() => smsDayEraseScope(group.key, timezone)}
                />
              )}
            </span>
          }
          level={2}
          dayNumber={group.day}
          month={group.month}
          surface={surface}
        >
          <div className="divide-y divide-border">
            {group.messages.map(message => (
              <SmsMessageCard key={message.id} message={message} lng={lng} timezone={timezone} />
            ))}
          </div>
        </TimelineDayGroup>
      ))}
    </div>
  );
}
