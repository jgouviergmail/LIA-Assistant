'use client';
import Link from 'next/link';
import { useAppConfig } from '@/hooks/useAppConfig';
import { capabilityEnabled } from '@/lib/capability-state';
import { MessageSquareText } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/hooks/useAuth';
import { Badge } from '@/components/ui/badge';
import { directionTone } from '@/lib/status-tone';
import { isLanguage, fallbackLng } from '@/i18n/settings';
import { CollapsibleSection, SectionBadge, SectionRow, SectionRows } from './CollapsibleSection';
import { RelationWhen } from './RelationWhen';
import { SmsMessageCard } from '@/components/sms/SmsMessageList';
import { settingsSectionHref } from '@/lib/settings-sections';
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
          <SectionRows>
            {messages.map(message => (
              <SectionRow key={message.id} className="py-1.5">
                <Link
                  className="-mx-2 block min-w-0 rounded-md transition-colors hover:bg-primary/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  href={`${settingsSectionHref(language, 'sms')}&message=${encodeURIComponent(message.id)}`}
                >
                  {/* Titled like every row of the card — when, no icon (owner
                      request 2026-10-21): the section already names the person. */}
                  <SmsMessageCard
                    message={message}
                    lng={language}
                    timezone={user?.timezone || 'Europe/Paris'}
                    className="space-y-1.5 px-2 py-1.5 sm:px-2 sm:py-1.5"
                    title={
                      // Every SMS here was RECEIVED (the phone relays what it
                      // got): the direction badge leads, as on the e-mails.
                      <>
                        <Badge variant={directionTone('received')} size="sm">
                          {t('relations.peer_message_received')}
                        </Badge>
                        <RelationWhen start={message.received_at} />
                      </>
                    }
                  />
                </Link>
              </SectionRow>
            ))}
          </SectionRows>
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
      className="mb-3 rounded-md border border-border bg-muted/40 p-3 text-sm text-muted-foreground"
    >
      {t('relations.sms_unavailable')}
    </p>
  );
}
