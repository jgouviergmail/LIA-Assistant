'use client';
import { useCallback, useState } from 'react';
import { MessageSquareText } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useSmsArchive } from '@/hooks/useSmsArchive';
import { Button } from '@/components/ui/button';
import { Disclosure } from '@/components/ui/disclosure';
import { SmsMessageList } from './SmsMessageList';
import { SmsEraseButton } from './SmsErasure';
import type { SmsMessage, SmsSender } from '@/types/sms';
import type { Language } from '@/i18n/settings';

function SenderMessages({
  sender,
  lng,
  timezone,
}: {
  sender: SmsSender;
  lng: Language;
  timezone: string;
}) {
  const { t } = useTranslation();
  const [cursor, setCursor] = useState<string | undefined>();
  const resetCursor = useCallback(() => setCursor(undefined), []);
  const list = useSmsArchive({ sender_id: sender.id, cursor, limit: 20 }, true, resetCursor);
  return (
    <div className="space-y-3 py-3" aria-busy={list.loading}>
      <SmsEraseButton
        kind="sender"
        target={sender.display_name}
        scope={() => ({ sender_id: sender.id })}
      />
      {list.loading && !list.data && <p role="status">{t('common.loading')}</p>}
      {list.error && (
        <p role="alert" className="text-sm text-destructive">
          {t('sms.unavailable')}
        </p>
      )}
      {list.data && (
        <SmsMessageList
          messages={list.data.items}
          lng={lng}
          timezone={timezone}
          surface="background"
        />
      )}
      <div className="flex flex-wrap gap-2">
        {cursor && (
          <Button variant="outline" onClick={() => setCursor(undefined)}>
            {t('common.previous')}
          </Button>
        )}
        {list.data?.next_cursor && (
          <Button variant="outline" onClick={() => setCursor(list.data?.next_cursor ?? undefined)}>
            {t('sms.load_more')}
          </Button>
        )}
      </div>
    </div>
  );
}
export function SmsSenderThreads({
  senders,
  lng,
  timezone,
}: {
  senders: readonly SmsSender[];
  lng: Language;
  timezone: string;
}) {
  return (
    <div className="space-y-3">
      {senders.map(sender => (
        <Disclosure
          key={sender.id}
          icon={MessageSquareText}
          title={sender.display_name}
          description={sender.display_name !== sender.sender ? sender.sender : undefined}
          badge={sender.total}
        >
          <SenderMessages sender={sender} lng={lng} timezone={timezone} />
        </Disclosure>
      ))}
    </div>
  );
}
/** Filtered sender groups describe this bounded search page, never a global total. */
export function SmsSearchGroups({
  messages,
  lng,
  timezone,
}: {
  messages: readonly SmsMessage[];
  lng: Language;
  timezone: string;
}) {
  const { t } = useTranslation();
  const groups = new Map<string, SmsMessage[]>();
  for (const message of messages) {
    const group = groups.get(message.sender) ?? [];
    group.push(message);
    groups.set(message.sender, group);
  }
  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">{t('sms.page_groups')}</p>
      {[...groups].map(([sender, items]) => (
        <Disclosure
          key={sender}
          icon={MessageSquareText}
          title={items[0]?.display_name ?? sender}
          badge={items.length}
          defaultOpen
        >
          <div className="py-3">
            {items[0] && (
              <SmsEraseButton
                kind="sender"
                target={sender}
                scope={() => ({ sender_id: items[0].id })}
              />
            )}
            <SmsMessageList messages={items} lng={lng} timezone={timezone} surface="background" />
          </div>
        </Disclosure>
      ))}
    </div>
  );
}
