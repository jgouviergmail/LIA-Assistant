'use client';
import { BarChart3, Bot, MessageSquareText, RefreshCw } from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';
import { useAppConfig } from '@/hooks/useAppConfig';
import { useSmsSettings } from '@/hooks/useSmsSettings';
import { useSmsManagement } from '@/hooks/useSmsManagement';
import { useSmsPreferenceUpdate } from '@/hooks/useSmsPreferenceUpdate';
import { formatFileSize } from '@/lib/format';
import { capabilityEnabled } from '@/lib/capability-state';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { Disclosure } from '@/components/ui/disclosure';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { SmsTokenSettings } from '@/components/sms/SmsTokenSettings';
import { SmsArchiveManagement } from '@/components/sms/SmsArchiveManagement';
import { SmsConfirmation } from '@/components/sms/SmsConfirmation';
import { SmsErasureProvider } from '@/components/sms/SmsErasure';
import { SmsSettingsArchive } from './SmsSettingsArchive';
import type { SmsPreferences } from '@/types/sms';
import { cn } from '@/lib/utils';

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
  const preferenceUpdate = useSmsPreferenceUpdate(data.settings);
  const busy = actions.busy || preferenceUpdate.saving;
  const settings = data.settings.data;
  const fields: { field: keyof SmsPreferences; label: string; hint?: string }[] = [
    { field: 'ingestion_enabled', label: t('sms.ingestion') },
    { field: 'assistant_enabled', label: t('sms.assistant'), hint: t('sms.assistant_hint') },
  ];
  const save = (field: keyof SmsPreferences, value: boolean) => {
    if (!busy) void preferenceUpdate.updatePreference(field, value);
  };
  return (
    <SettingsSection
      value="sms"
      title={t('sms.settings_title')}
      description={t('sms.description')}
      icon={MessageSquareText}
    >
      <div className="min-w-0 space-y-2" aria-busy={data.settings.loading || busy}>
        {(data.settings.error ||
          data.tokens.error ||
          data.blocks.error ||
          actions.error ||
          preferenceUpdate.error) && (
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
            {/* The page's own switch, unfolded at its head like « Activer les
                notifications proactives » on the notifications page: a fold
                around one switch only hid it (owner request 2026-10-21). */}
            <div className="flex items-center justify-between gap-4 pb-4">
              <div className="min-w-0 space-y-0.5">
                <Label htmlFor="sms-push_enabled" className="text-sm font-medium">
                  {t('sms.push')}
                </Label>
                <p id="sms-push_enabled-hint" className="text-xs text-muted-foreground">
                  {t('sms.push_hint')}
                </p>
              </div>
              <Switch
                id="sms-push_enabled"
                aria-describedby="sms-push_enabled-hint"
                checked={settings.preferences.push_enabled}
                aria-disabled={busy}
                onCheckedChange={value => save('push_enabled', value)}
              />
            </div>
            <SmsTokenSettings data={data} actions={actions} />
            <Disclosure icon={Bot} title={t('sms.assistant')} surface="nested">
              <div className="space-y-3 pt-2">
                {fields.map(({ field, label, hint }) => (
                  <div
                    key={field}
                    className="flex min-w-0 items-center justify-between gap-4 rounded-lg border bg-card p-3"
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
                      aria-disabled={busy}
                      onCheckedChange={value => save(field, value)}
                    />
                  </div>
                ))}
                <p className="text-xs text-muted-foreground">{t('sms.filter_hint')}</p>
              </div>
            </Disclosure>
            <Disclosure icon={BarChart3} title={t('sms.stats_title')} defaultOpen surface="nested">
              <div className="space-y-2 pt-2 text-sm">
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
                    pending:
                      settings.device_deliveries.pending + settings.device_deliveries.sending,
                  })}
                </p>
              </div>
            </Disclosure>

            <SmsErasureProvider
              value={{
                busy,
                request: scope => {
                  if ('message_ids' in scope) void actions.eraseMessage(scope.message_ids[0]);
                  else void actions.propose('sms_messages.delete', scope);
                },
              }}
            >
              <SmsSettingsArchive lng={lng} />
            </SmsErasureProvider>

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
          <RefreshCw
            className={cn('h-4 w-4', data.settings.loading && 'motion-safe:animate-spin')}
            aria-hidden="true"
          />
          {t('common.refresh')}
        </Button>
        <SmsConfirmation actions={actions} />
      </div>
    </SettingsSection>
  );
}
