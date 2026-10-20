'use client';
import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/hooks/useAuth';
import { useApplicationAccountQuery } from '@/hooks/useApplicationAccountQuery';
import { SmsMessageCard } from './SmsMessageList';
import type { SmsMessage } from '@/types/sms';
import type { Language } from '@/i18n/settings';
export function SmsFocusedMessage({ messageId, lng }: { messageId: string; lng: Language }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { data, error } = useApplicationAccountQuery<SmsMessage>(
    `/sms/${encodeURIComponent(messageId)}`,
    'SmsFocusedMessage'
  );
  const focus = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (data) focus.current?.focus();
  }, [data]);
  if (error)
    return (
      <p role="alert" className="text-sm text-destructive">
        {t('sms.unavailable')}
      </p>
    );
  return (
    <div
      ref={focus}
      tabIndex={-1}
      className="rounded-xl border border-primary/30 bg-card outline-offset-4"
      aria-label={t('sms.title')}
    >
      {data ? (
        <SmsMessageCard message={data} lng={lng} timezone={user?.timezone || 'Europe/Paris'} />
      ) : (
        <p role="status" className="p-4">
          {t('common.loading')}
        </p>
      )}
    </div>
  );
}
