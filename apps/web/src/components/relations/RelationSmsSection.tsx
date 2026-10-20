'use client';
import Link from 'next/link';
import { useAppConfig } from '@/hooks/useAppConfig';
import { capabilityEnabled } from '@/lib/capability-state';
import { MessageSquareText } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/hooks/useAuth';
import { isLanguage, fallbackLng } from '@/i18n/settings';
import { CollapsibleSection, SectionBadge } from './CollapsibleSection';
import { SmsMessageCard } from '@/components/sms/SmsMessageList';
import type { SmsMessage } from '@/types/sms';
export function RelationSmsSection({
  messages,
  total,
  available,
  lng,
}: {
  messages: SmsMessage[];
  total: number;
  available: boolean;
  lng: string;
}) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { config } = useAppConfig();
  if (!capabilityEnabled(config?.capabilities, 'sms', config?.features.sms_enabled)) return null;
  const language = isLanguage(lng) ? lng : fallbackLng;
  return (
    <CollapsibleSection
      icon={MessageSquareText}
      title={t('relations.sms_title')}
      badge={available ? <SectionBadge>{total}</SectionBadge> : undefined}
    >
      {!available ? (
        <p className="text-sm text-muted-foreground">{t('relations.sms_unavailable')}</p>
      ) : (
        <>
          {messages.length === 0 && (
            <p className="text-sm text-muted-foreground">{t('sms.empty')}</p>
          )}
          {messages.map(message => (
            <div key={message.id} className="min-w-0 border-t border-border/40">
              <SmsMessageCard
                message={message}
                lng={language}
                timezone={user?.timezone || 'Europe/Paris'}
              />
              <Link
                className="inline-flex min-h-11 items-center rounded-md px-2 text-sm text-primary underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                href={`/${language}/dashboard/sms?message=${message.id}`}
              >
                {t('relations.sms_open')}
              </Link>
            </div>
          ))}
          {total > messages.length && (
            <p className="mt-2 text-xs text-muted-foreground">
              {t('relations.more_not_shown', { count: total - messages.length })}
            </p>
          )}
        </>
      )}
    </CollapsibleSection>
  );
}

export function RelationSmsSourceNotice({ available }: { available: boolean | undefined }) {
  const { config } = useAppConfig();
  const { t } = useTranslation();
  if (
    available !== false ||
    !capabilityEnabled(config?.capabilities, 'sms', config?.features.sms_enabled)
  )
    return null;
  return (
    <p
      role="status"
      className="mb-3 rounded-md border border-border/50 bg-muted/40 p-3 text-sm text-muted-foreground"
    >
      {t('relations.sms_unavailable')}
    </p>
  );
}
