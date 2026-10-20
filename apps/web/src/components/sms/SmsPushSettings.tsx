'use client';
import { useCallback, useId } from 'react';
import { MessageSquareText } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useAppConfig } from '@/hooks/useAppConfig';
import { useApplicationAccountQuery } from '@/hooks/useApplicationAccountQuery';
import { useApplicationResourceSync } from '@/hooks/useApplicationResourceSync';
import { useSmsManagement } from '@/hooks/useSmsManagement';
import { capabilityEnabled } from '@/lib/capability-state';
import { Disclosure } from '@/components/ui/disclosure';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { SmsConfirmation } from './SmsConfirmation';
import type { SmsSettings } from '@/types/sms';
import type { Language } from '@/i18n/settings';

function PushControl() {
  const { t } = useTranslation();
  const id = useId();
  const query = useApplicationAccountQuery<SmsSettings>('/sms/settings', 'SmsPushSettings');
  const actions = useSmsManagement();
  const { ownerId, refetch } = query;
  const refresh = useCallback(async () => {
    await refetch();
  }, [refetch]);
  useApplicationResourceSync(ownerId, 'sms', refresh);
  return (
    <div className="space-y-3 py-3" aria-busy={query.loading || actions.busy}>
      {query.data && (
        <div className="flex items-center justify-between gap-4">
          <Label htmlFor={id}>{t('sms.push')}</Label>
          <Switch
            id={id}
            checked={query.data.preferences.push_enabled}
            aria-disabled={actions.busy}
            onCheckedChange={value => {
              if (query.data)
                void actions.propose('sms_preferences.update', {
                  ...query.data.preferences,
                  push_enabled: value,
                });
            }}
          />
        </div>
      )}
      {(query.error || actions.error) && (
        <p role="alert" className="text-sm text-destructive">
          {t('sms.unavailable')}
        </p>
      )}
      {actions.uncertain && (
        <p role="alert" className="text-sm text-destructive">
          {t('sms.unknown_result')}
        </p>
      )}
      <SmsConfirmation actions={actions} />
    </div>
  );
}
export function SmsPushSettings({ lng: _lng }: { lng: Language }) {
  const { t } = useTranslation();
  const { config } = useAppConfig();
  if (!capabilityEnabled(config?.capabilities, 'sms', config?.features.sms_enabled)) return null;
  return (
    <Disclosure
      icon={MessageSquareText}
      title={t('sms.push')}
      description={t('sms.push_hint')}
      surface="nested"
    >
      <PushControl />
    </Disclosure>
  );
}
