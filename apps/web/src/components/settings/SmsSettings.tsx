'use client';
import Link from 'next/link';
import { Bot, MessageSquareText } from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';
import { useAppConfig } from '@/hooks/useAppConfig';
import { useSmsSettings } from '@/hooks/useSmsSettings';
import { useSmsManagement } from '@/hooks/useSmsManagement';
import { formatFileSize } from '@/lib/format';
import { capabilityEnabled } from '@/lib/capability-state';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { FormSection } from '@/components/ui/form-section';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { SmsTokenSettings } from '@/components/sms/SmsTokenSettings';
import { SmsArchiveManagement } from '@/components/sms/SmsArchiveManagement';
import { SmsConfirmation } from '@/components/sms/SmsConfirmation';
import type { SmsPreferences } from '@/types/sms';

export function SmsSettings({ lng }: { lng: Language }) {
  const { config } = useAppConfig();
  const { user } = useAuth();
  if (!capabilityEnabled(config?.capabilities, 'sms', config?.features.sms_enabled)) return null;
  return <AccountSmsSettings key={user?.id ?? 'signed-out'} lng={lng} />;
}
function AccountSmsSettings({ lng }: { lng: Language }) {
  const { t } = useTranslation(lng, 'translation');
  const { user } = useAuth();
  const data = useSmsSettings();
  const actions = useSmsManagement();
  const settings = data.settings.data;
  const fields: { field: keyof SmsPreferences; label: string; hint?: string }[] = [
    { field: 'ingestion_enabled', label: t('sms.ingestion') },
    { field: 'assistant_enabled', label: t('sms.assistant'), hint: t('sms.assistant_hint') },
    { field: 'push_enabled', label: t('sms.push'), hint: t('sms.push_hint') },
  ];
  return (
    <SettingsSection
      value="sms"
      title={t('sms.title')}
      description={t('sms.description')}
      icon={MessageSquareText}
    >
      <div className="min-w-0 space-y-6" aria-busy={data.settings.loading || actions.busy}>
        <Button asChild variant="outline">
          <Link href={`/${lng}/dashboard/sms`}>{t('sms.archive')}</Link>
        </Button>
        {(data.settings.error || data.tokens.error || data.blocks.error || actions.error) && (
          <p role="alert" className="text-sm text-destructive">
            {t('sms.unavailable')}
          </p>
        )}
        {actions.uncertain && (
          <p role="alert" className="text-sm text-destructive">
            {t('sms.unknown_result')}
          </p>
        )}
        {!settings && data.settings.loading && <p role="status">{t('common.loading')}</p>}
        {settings && (
          <>
            <div className="rounded-xl border bg-muted/20 p-3 text-sm">
              <p className="font-medium">
                {t('sms.usage', { count: settings.usage.message_count })}
              </p>
              <p>
                {t('sms.quota', {
                  used: formatFileSize(settings.usage.logical_bytes),
                  max: formatFileSize(settings.usage.max_logical_bytes),
                })}
              </p>
              <p>
                {t('sms.receipts', {
                  count: settings.usage.receipt_count,
                  max: settings.usage.max_receipts,
                })}
              </p>
              <p>
                {t('sms.deliveries', {
                  ...settings.device_deliveries,
                  pending: settings.device_deliveries.pending + settings.device_deliveries.sending,
                })}
              </p>
            </div>
            <SmsTokenSettings data={data} actions={actions} />
            <FormSection icon={Bot} title={t('sms.assistant')}>
              {fields.map(({ field, label, hint }) => (
                <div
                  key={field}
                  className="flex min-w-0 items-center justify-between gap-4 rounded-lg border p-3"
                >
                  <div className="min-w-0 space-y-1">
                    <Label htmlFor={`sms-${field}`}>{label}</Label>
                    {hint && (
                      <p id={`sms-${field}-hint`} className="text-xs text-muted-foreground">
                        {hint}
                      </p>
                    )}
                  </div>
                  <Switch
                    id={`sms-${field}`}
                    aria-describedby={hint ? `sms-${field}-hint` : undefined}
                    checked={settings.preferences[field]}
                    aria-disabled={actions.busy}
                    onCheckedChange={value => {
                      void actions.propose('sms_preferences.update', {
                        ...settings.preferences,
                        [field]: value,
                      });
                    }}
                  />
                </div>
              ))}
              <p className="text-xs text-muted-foreground">{t('sms.filter_hint')}</p>
            </FormSection>
            <SmsArchiveManagement
              data={data}
              actions={actions}
              timezone={user?.timezone || 'Europe/Paris'}
            />
          </>
        )}
        <Button
          variant="outline"
          onClick={() => {
            void data.refresh().catch(() => {});
          }}
        >
          {t('common.refresh')}
        </Button>
        <SmsConfirmation actions={actions} />
      </div>
    </SettingsSection>
  );
}
