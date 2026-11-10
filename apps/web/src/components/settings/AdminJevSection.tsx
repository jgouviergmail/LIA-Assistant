'use client';

import { useRef, useState } from 'react';
import Link from 'next/link';
import { SlidersHorizontal, Workflow } from '@/lib/icons';
import { JevGateThresholds } from '@/components/settings/JevGateThresholds';
import { JevUsageStatisticsPanel } from '@/components/settings/JevUsageStatisticsPanel';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Disclosure } from '@/components/ui/disclosure';
import { InfoBox } from '@/components/ui/info-box';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { useApiMutation } from '@/hooks/useApiMutation';
import { useApiQuery } from '@/hooks/useApiQuery';
import { JEV_STATISTICS_WINDOW_DAYS, useJevStatistics } from '@/hooks/useJevStatistics';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { settingsSectionHref } from '@/lib/settings-sections';
import type {
  JevSettings,
  JevThresholdUpdate,
  JevToggleUpdate,
  JevUsage,
  JevUsageStatistics,
  JevUsageStatus,
} from '@/types/jev';
import type { BaseSettingsProps } from '@/types/settings';

const ENDPOINT = '/admin/llm-config/jev';
const THRESHOLDS_ENDPOINT = `${ENDPOINT}/thresholds`;
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
    <div className="flex items-center justify-between gap-4 rounded-lg border border-border bg-background p-4">
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

/** One usage: its switch, what it does, its thresholds and its window of statistics. */
function JevUsageBlock({
  lng,
  item,
  busy,
  statistics,
  statisticsFailed,
  onToggle,
  onMoveThresholds,
}: {
  lng: Language;
  item: JevUsageStatus;
  busy: boolean;
  statistics: JevUsageStatistics | undefined;
  statisticsFailed: boolean;
  onToggle: (usage: JevUsage, enabled: boolean) => void;
  onMoveThresholds: (usage: JevUsage, values: Record<string, number>) => Promise<void>;
}) {
  const { t } = useTranslation(lng, 'translation');
  const usageLabel = t(item.label_key);
  return (
    <div className="space-y-2">
      <RoutingSwitch
        id={`jev-${item.usage}`}
        label={usageLabel}
        checked={item.enabled}
        description={t(`${PREFIX}.${item.effective ? 'active' : 'existing'}`)}
        busy={busy}
        onChange={enabled => onToggle(item.usage, enabled)}
      />
      <p className="px-1 text-sm text-muted-foreground">{t(`${PREFIX}.usageHelp.${item.usage}`)}</p>
      {item.readiness !== 'ready' && (
        <p className="px-1 text-sm text-muted-foreground">
          {t(`${PREFIX}.readiness.${item.readiness}`)}
        </p>
      )}
      {item.gates.length > 0 && (
        <Disclosure
          icon={SlidersHorizontal}
          title={t(`${PREFIX}.thresholds.toggle`, { usage: usageLabel })}
          titleClassName="whitespace-normal break-words"
          meta={
            item.qualified ? undefined : (
              <Badge variant="warning">{t(`${PREFIX}.thresholds.outsideRecord`)}</Badge>
            )
          }
          surface="nested"
        >
          <div className="space-y-3">
            <p className="text-xs leading-relaxed text-muted-foreground">
              {t(`${PREFIX}.thresholds.help`)}
            </p>
            <JevGateThresholds
              lng={lng}
              usage={item.usage}
              gates={item.gates}
              statistics={statistics?.gates}
              busy={busy}
              onCommit={values => onMoveThresholds(item.usage, values)}
            />
          </div>
        </Disclosure>
      )}
      <JevUsageStatisticsPanel
        lng={lng}
        usageLabel={usageLabel}
        days={JEV_STATISTICS_WINDOW_DAYS}
        statistics={statistics}
        failed={statisticsFailed}
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
  const { mutate: mutateThresholds, loading: savingThresholds } = useApiMutation<
    JevThresholdUpdate,
    JevSettings
  >({ method: 'PATCH', componentName: 'AdminJevSection' });
  const statistics = useJevStatistics();
  const inFlight = useRef(false);
  const [saveError, setSaveError] = useState(false);
  const [saved, setSaved] = useState(false);
  const busy = saving || savingThresholds || loading;

  /** One write at a time, whichever control asked: the server serializes them too. */
  const save = async (send: () => Promise<JevSettings | undefined>) => {
    if (inFlight.current || busy) return;
    inFlight.current = true;
    setSaveError(false);
    setSaved(false);
    try {
      const response = await send();
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
  const toggle = (usage: JevUsage | null, enabled: boolean) =>
    save(() => mutate(ENDPOINT, { usage, enabled }));
  const moveThresholds = (usage: JevUsage, values: Record<string, number>) =>
    save(() => mutateThresholds(THRESHOLDS_ENDPOINT, { usage, values }));

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
              <JevUsageBlock
                key={item.usage}
                lng={lng}
                item={item}
                busy={busy}
                statistics={statistics.data?.usages.find(entry => entry.usage === item.usage)}
                statisticsFailed={Boolean(statistics.error)}
                onToggle={(usage, enabled) => void toggle(usage, enabled)}
                onMoveThresholds={moveThresholds}
              />
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
              if (busy) return;
              void refetch();
              void statistics.refetch();
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
