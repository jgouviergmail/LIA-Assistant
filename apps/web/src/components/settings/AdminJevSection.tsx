'use client';

import { useRef, useState } from 'react';
import Link from 'next/link';
import { Workflow } from 'lucide-react';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { Button } from '@/components/ui/button';
import { InfoBox } from '@/components/ui/info-box';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { useApiMutation } from '@/hooks/useApiMutation';
import { useApiQuery } from '@/hooks/useApiQuery';
import { useTranslation } from '@/i18n/client';
import { settingsSectionHref } from '@/lib/settings-sections';
import type { JevSettings, JevToggleUpdate, JevUsage } from '@/types/jev';
import type { BaseSettingsProps } from '@/types/settings';

const ENDPOINT = '/admin/llm-config/jev';
const PREFIX = 'settings.admin.jev';

function RoutingSwitch({
  id,
  label,
  description,
  checked,
  busy,
  onChange,
}: {
  id: string;
  label: string;
  description: string;
  checked: boolean;
  busy: boolean;
  onChange: (enabled: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-lg border border-border p-4">
      <div className="min-w-0 space-y-1">
        <Label htmlFor={id} className="cursor-pointer text-sm font-medium">
          {label}
        </Label>
        <p id={`${id}-help`} className="text-sm text-muted-foreground">
          {description}
        </p>
      </div>
      <Switch
        id={id}
        checked={checked}
        aria-disabled={busy}
        aria-describedby={`${id}-help`}
        onCheckedChange={next => {
          if (!busy) onChange(next);
        }}
        className="shrink-0"
      />
    </div>
  );
}

export default function AdminJevSection({ lng }: BaseSettingsProps) {
  const { t } = useTranslation(lng, 'translation');
  const { data, loading, error, setData, refetch } = useApiQuery<JevSettings>(ENDPOINT, {
    componentName: 'AdminJevSection',
  });
  const { mutate, loading: saving } = useApiMutation<JevToggleUpdate, JevSettings>({
    method: 'PATCH',
    componentName: 'AdminJevSection',
  });
  const inFlight = useRef(false);
  const [saveError, setSaveError] = useState(false);
  const [saved, setSaved] = useState(false);
  const busy = saving || loading;

  const toggle = async (usage: JevUsage | null, enabled: boolean) => {
    if (inFlight.current || busy) return;
    inFlight.current = true;
    setSaveError(false);
    setSaved(false);
    try {
      const response = await mutate(ENDPOINT, { usage, enabled });
      if (response) {
        setData(response);
        setSaved(true);
      } else {
        setSaveError(true);
      }
    } catch {
      setSaveError(true);
    } finally {
      inFlight.current = false;
    }
  };

  return (
    <SettingsSection
      value="admin-jev"
      title={t('settings.admin.jev.title')}
      description={t('settings.admin.jev.description')}
      icon={Workflow}
    >
      <div className="space-y-4" aria-busy={busy}>
        {!data && loading && (
          <p role="status" className="animate-pulse text-sm text-muted-foreground">
            {t('common.loading')}
          </p>
        )}
        {error && (
          <InfoBox role="alert" variant="error">
            {t(`${PREFIX}.loadError`)}
          </InfoBox>
        )}
        {saveError && (
          <InfoBox role="alert" variant="error">
            {t(`${PREFIX}.saveError`)}
          </InfoBox>
        )}
        {data && (
          <>
            <RoutingSwitch
              id="jev-global"
              label={t(`${PREFIX}.globalLabel`)}
              description={t(`${PREFIX}.globalHelp`)}
              checked={data.enabled}
              busy={busy}
              onChange={enabled => void toggle(null, enabled)}
            />
            {data.usages.map(item => (
              <div key={item.usage} className="space-y-2">
                <RoutingSwitch
                  id={`jev-${item.usage}`}
                  label={t(item.label_key)}
                  checked={item.enabled}
                  description={t(`${PREFIX}.${item.effective ? 'active' : 'existing'}`)}
                  busy={busy}
                  onChange={enabled => void toggle(item.usage, enabled)}
                />
                <p className="px-1 text-sm text-muted-foreground">
                  {t(`${PREFIX}.usageHelp.${item.usage}`)}
                </p>
                {item.readiness !== 'ready' && (
                  <p className="px-1 text-sm text-muted-foreground">
                    {t(`${PREFIX}.readiness.${item.readiness}`)}
                  </p>
                )}
              </div>
            ))}
            <InfoBox className="text-sm text-muted-foreground">
              {t(`${PREFIX}.fallbackHelp`)}
            </InfoBox>
          </>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" asChild>
            <Link href={settingsSectionHref(lng, 'admin-llm-config')}>
              {t(`${PREFIX}.configure`)}
            </Link>
          </Button>
          <Button
            variant="ghost"
            aria-disabled={busy}
            onClick={() => {
              if (!busy) void refetch();
            }}
          >
            {t(`${PREFIX}.refresh`)}
          </Button>
        </div>
        {saved && (
          <p role="status" className="text-sm text-muted-foreground">
            {t(`${PREFIX}.saved`)}
          </p>
        )}
      </div>
    </SettingsSection>
  );
}
