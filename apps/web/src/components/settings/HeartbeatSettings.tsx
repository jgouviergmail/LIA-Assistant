'use client';

import { useState } from 'react';
import { Bell, Clock, Gauge, History, SlidersHorizontal } from 'lucide-react';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { useTranslation } from '@/i18n/client';
import { getIntlLocale } from '@/i18n/settings';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { HourWindow, MinMaxPerDay } from '@/components/settings/FrequencyControls';
import { useHeartbeatHistory } from '@/hooks/useHeartbeatHistory';
import { useHeartbeatSettings } from '@/hooks/useHeartbeatSettings';
import { HeartbeatHistory } from '@/components/settings/HeartbeatHistory';
import { HeartbeatSourceSwitches } from '@/components/settings/HeartbeatSourceSwitches';
import { SettingsDisclosure } from '@/components/settings/SettingsDisclosure';
import { toast } from 'sonner';
import type { BaseSettingsProps } from '@/types/settings';

/**
 * HeartbeatSettings component for managing proactive notification preferences.
 *
 * Displays:
 * - Master toggle (enable/disable heartbeat)
 * - Notification time window (start/end hour), then min/max per day
 * - Per-source permission switches (what may interrupt the reader)
 *
 * The location opt-in lives on the Google Places connector (generalized
 * 2026-08-16) — proactive jobs read the same cascade as every other feature.
 *
 * No push toggle: push delivery follows the global notification opt-in
 * (owner arbitration 2026-08-05).
 */
export function HeartbeatSettings({ lng, collapsible = true }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  const { settings, loading, updating, updateSettings } = useHeartbeatSettings();
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
          {/* Shared with Interests (FrequencyControls): one implementation of
              the hour-window and min/max pair, with named selects — the four
              inline copies here were anonymous comboboxes. Window FIRST, then
              frequency (owner arbitration 2026-08-05): "when may LIA speak"
              frames "how often". No push toggle any more — push follows the
              global notification opt-in automatically; a second per-feature
              gate was a duplicate that could silently mute the heartbeat. */}
          <HourWindow
            label={
              <>
                <Clock className="h-4 w-4 text-primary" aria-hidden="true" />
                {t('heartbeat.notification_hours')}
              </>
            }
            startAriaLabel={t('common.start_hour_label')}
            endAriaLabel={t('common.end_hour_label')}
            startHour={settings.heartbeat_notify_start_hour}
            endHour={settings.heartbeat_notify_end_hour}
            disabled={updating}
            onChange={handleUpdateHours}
          />

          <MinMaxPerDay
            label={
              <>
                <Gauge className="h-4 w-4 text-primary" aria-hidden="true" />
                {t('heartbeat.notification_frequency')}
              </>
            }
            perDayLabel={t('heartbeat.per_day')}
            minAriaLabel={t('common.min_per_day_label')}
            maxAriaLabel={t('common.max_per_day_label')}
            min={settings.heartbeat_min_per_day}
            max={settings.heartbeat_max_per_day}
            limit={8}
            disabled={updating}
            onChange={handleUpdateFrequency}
          />

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
