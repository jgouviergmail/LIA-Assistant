'use client';

import { useMemo, useState } from 'react';
import { Bell, Clock, History, SlidersHorizontal } from 'lucide-react';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useTranslation } from '@/i18n/client';
import { getIntlLocale } from '@/i18n/settings';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { useHeartbeatHistory } from '@/hooks/useHeartbeatHistory';
import { useHeartbeatSettings } from '@/hooks/useHeartbeatSettings';
import { HeartbeatHistory } from '@/components/settings/HeartbeatHistory';
import { HeartbeatSourceSwitches } from '@/components/settings/HeartbeatSourceSwitches';
import { SettingsDisclosure } from '@/components/settings/SettingsDisclosure';
import { WeatherLocationBlock } from '@/components/settings/WeatherLocationBlock';
import { toast } from 'sonner';
import type { BaseSettingsProps } from '@/types/settings';

/**
 * Generate hour options for select (00:00 to 23:00).
 */
function generateHourOptions() {
  return Array.from({ length: 24 }, (_, i) => ({
    value: i.toString(),
    label: `${i.toString().padStart(2, '0')}:00`,
  }));
}

/**
 * HeartbeatSettings component for managing proactive notification preferences.
 *
 * Displays:
 * - Master toggle (enable/disable heartbeat)
 * - Max notifications per day selector
 * - Notification time window (start/end hour)
 * - Push notification toggle (FCM/Telegram vs silent)
 * - Per-source permission switches (what may interrupt the reader)
 */
export function HeartbeatSettings({ lng, collapsible = true }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  const { settings, loading, updating, updateSettings } = useHeartbeatSettings();
  const hourOptions = useMemo(() => generateHourOptions(), []);
  const intlLocale = getIntlLocale(lng);
  // Called BEFORE the early return below — hooks may not sit behind a
  // conditional. Fetching is gated by the argument instead: the history block
  // only renders inside the enabled panel, so an account with the heartbeat
  // off costs no request.
  // Opened by the reader, not on arrival: the history block folds CLOSED, so
  // an account that never opens it costs no request at all. Gating on the
  // disclosure rather than merely hiding the list is the difference between
  // "not shown" and "not fetched".
  const [historyOpen, setHistoryOpen] = useState(false);
  const history = useHeartbeatHistory(Boolean(settings?.heartbeat_enabled) && historyOpen);

  if (!settings) return null;

  const handleToggleEnabled = async () => {
    const newValue = !settings.heartbeat_enabled;
    const result = await updateSettings({ heartbeat_enabled: newValue });
    if (result) {
      toast.success(newValue ? t('heartbeat.enabled_success') : t('heartbeat.disabled_success'));
    } else {
      toast.error(t('heartbeat.settings_error'));
    }
  };

  const handleTogglePush = async () => {
    const newValue = !settings.heartbeat_push_enabled;
    const result = await updateSettings({ heartbeat_push_enabled: newValue });
    if (result) {
      toast.success(t('heartbeat.settings_updated'));
    } else {
      toast.error(t('heartbeat.settings_error'));
    }
  };

  const handleUpdateFrequency = async (field: 'min' | 'max', value: number) => {
    const update =
      field === 'min' ? { heartbeat_min_per_day: value } : { heartbeat_max_per_day: value };
    const result = await updateSettings(update);
    if (result) {
      toast.success(t('heartbeat.settings_updated'));
    } else {
      toast.error(t('heartbeat.settings_error'));
    }
  };

  /**
   * Persist the FULL refusal set.
   *
   * The API replaces it wholesale, so sending a diff would silently re-permit
   * every other source. Optimistic update + revert live in the hook.
   */
  const handleSourcesChange = async (disabled: string[]) => {
    const result = await updateSettings({ heartbeat_disabled_sources: disabled });
    if (result) {
      toast.success(t('heartbeat.settings_updated'));
    } else {
      toast.error(t('heartbeat.settings_error'));
    }
  };

  const handleUpdateHours = async (field: 'start' | 'end', value: number) => {
    const update =
      field === 'start'
        ? { heartbeat_notify_start_hour: value }
        : { heartbeat_notify_end_hour: value };
    const result = await updateSettings(update);
    if (result) {
      toast.success(t('heartbeat.settings_updated'));
    } else {
      toast.error(t('heartbeat.settings_error'));
    }
  };

  const content = (
    <div className="space-y-6">
      {/* Master toggle */}
      <div className="flex items-center justify-between">
        <div className="space-y-0.5">
          <Label htmlFor="heartbeat-enabled" className="text-sm font-medium">
            {t('heartbeat.enable_proactive')}
          </Label>
          <p className="text-xs text-muted-foreground">{t('heartbeat.enable_description')}</p>
        </div>
        <Switch
          id="heartbeat-enabled"
          checked={settings.heartbeat_enabled}
          onCheckedChange={handleToggleEnabled}
          disabled={updating || loading}
        />
      </div>

      {/* Conditional settings panel */}
      {settings.heartbeat_enabled && (
        <div className="space-y-5 pl-1">
          {/* Notification frequency (min - max per day) */}
          <div className="space-y-2">
            <Label className="text-sm">{t('heartbeat.notification_frequency')}</Label>
            <div className="flex items-center gap-2">
              <Select
                value={String(settings.heartbeat_min_per_day)}
                onValueChange={v => handleUpdateFrequency('min', parseInt(v))}
                disabled={updating}
              >
                <SelectTrigger className="w-20">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Array.from({ length: 8 }, (_, i) => i + 1).map(n => (
                    <SelectItem key={n} value={String(n)}>
                      {n}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <span className="text-muted-foreground">-</span>
              <Select
                value={String(settings.heartbeat_max_per_day)}
                onValueChange={v => handleUpdateFrequency('max', parseInt(v))}
                disabled={updating}
              >
                <SelectTrigger className="w-20">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Array.from({ length: 8 }, (_, i) => i + 1).map(n => (
                    <SelectItem key={n} value={String(n)}>
                      {n}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <span className="text-sm text-muted-foreground">{t('heartbeat.per_day')}</span>
            </div>
          </div>

          {/* Notification time window */}
          <div className="space-y-2">
            <Label className="flex items-center gap-2 text-sm">
              <Clock className="h-4 w-4" />
              {t('heartbeat.notification_hours')}
            </Label>
            <div className="flex items-center gap-2">
              <Select
                value={settings.heartbeat_notify_start_hour.toString()}
                onValueChange={v => handleUpdateHours('start', parseInt(v))}
                disabled={updating}
              >
                <SelectTrigger className="w-24">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {hourOptions.map(opt => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <span className="text-muted-foreground">-</span>
              <Select
                value={settings.heartbeat_notify_end_hour.toString()}
                onValueChange={v => handleUpdateHours('end', parseInt(v))}
                disabled={updating}
              >
                <SelectTrigger className="w-24">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {hourOptions.map(opt => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Push notifications toggle */}
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label htmlFor="heartbeat-push" className="text-sm font-medium">
                {t('heartbeat.push_enabled')}
              </Label>
              <p className="text-xs text-muted-foreground">{t('heartbeat.push_description')}</p>
            </div>
            <Switch
              id="heartbeat-push"
              checked={settings.heartbeat_push_enabled}
              onCheckedChange={handleTogglePush}
              disabled={updating || loading}
            />
          </div>

          {/* Per-source permission (ADR-197).
              Replaces the old availability strip, which showed seven
              hard-coded names against the eight the backend computed — health
              signals were never displayed at all — and offered no decision:
              the documented way to stop being interrupted by a source was to
              disconnect its connector, losing the tool with it. */}
          {/* Weather location cascade (Phase 3 — ADR-073) */}
          <div className="space-y-2 border-t pt-4">
            <Label className="text-sm">{t('heartbeat.weather_location.section_label')}</Label>
            <WeatherLocationBlock lng={lng} />
          </div>

          {/* What the configuration above actually produced. The endpoint had
              shipped with the domain and no client ever called it: the panel
              let a reader tune frequency and sources without ever seeing what
              LIA chose to say. */}
          {/* Folded, and folded CLOSED: eleven switches shown at once is a
              wall on a panel where the reader came to change one thing. The
              badge carries how many are refused, so the fold still says
              whether anything was silenced. */}
          <div className="border-t pt-4">
            <SettingsDisclosure
              icon={SlidersHorizontal}
              title={t('heartbeat.sources_permission_title')}
              badge={
                (settings.disabled_sources ?? []).length > 0
                  ? (settings.disabled_sources ?? []).length
                  : undefined
              }
            >
              <p className="mb-2 text-xs text-muted-foreground">
                {t('heartbeat.sources_permission_description')}
              </p>
              <HeartbeatSourceSwitches
                allSources={settings.all_sources ?? []}
                disabledSources={settings.disabled_sources ?? []}
                availableSources={settings.available_sources ?? []}
                sourceDependencies={settings.source_dependencies}
                updating={updating}
                onChange={handleSourcesChange}
              />
            </SettingsDisclosure>
          </div>

          <div className="border-t pt-4">
            <SettingsDisclosure
              icon={History}
              title={t('heartbeat.history.title')}
              onOpenChange={setHistoryOpen}
            >
              <p className="mb-2 text-xs text-muted-foreground">
                {t('heartbeat.history.description')}
              </p>
              <HeartbeatHistory
                notifications={history.notifications}
                total={history.total}
                firstLoad={history.firstLoad}
                loading={history.loading}
                error={history.error}
                locale={intlLocale}
              />
            </SettingsDisclosure>
          </div>
        </div>
      )}
    </div>
  );

  if (!collapsible) {
    return content;
  }

  return (
    <SettingsSection
      value="heartbeat"
      title={t('heartbeat.settings.title')}
      description={t('heartbeat.settings.description')}
      icon={Bell}
    >
      {content}
    </SettingsSection>
  );
}
