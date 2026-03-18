'use client';

import { useMemo } from 'react';
import { Bell, Calendar, Clock, CloudSun, Brain, Mail, Sparkles, ListChecks } from 'lucide-react';
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
import { SettingsSection } from '@/components/settings/SettingsSection';
import { useHeartbeatSettings } from '@/hooks/useHeartbeatSettings';
import { toast } from 'sonner';
import type { BaseSettingsProps } from '@/types/settings';

/**
 * Source icon mapping for available sources display.
 */
const SOURCE_ICONS: Record<string, typeof Calendar> = {
  calendar: Calendar,
  emails: Mail,
  tasks: ListChecks,
  weather: CloudSun,
  interests: Sparkles,
  memories: Brain,
};

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
 * - Available data sources indicator
 */
export function HeartbeatSettings({ lng, collapsible = true }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  const { settings, loading, updating, updateSettings } = useHeartbeatSettings();
  const hourOptions = useMemo(() => generateHourOptions(), []);

  if (!settings) return null;

  const handleToggleEnabled = async () => {
    const newValue = !settings.heartbeat_enabled;
    const result = await updateSettings({ heartbeat_enabled: newValue });
    if (result) {
      toast.success(
        newValue ? t('heartbeat.enabled_success') : t('heartbeat.disabled_success')
      );
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
    const update = field === 'min'
      ? { heartbeat_min_per_day: value }
      : { heartbeat_max_per_day: value };
    const result = await updateSettings(update);
    if (result) {
      toast.success(t('heartbeat.settings_updated'));
    } else {
      toast.error(t('heartbeat.settings_error'));
    }
  };

  const handleUpdateHours = async (field: 'start' | 'end', value: number) => {
    const update = field === 'start'
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
          <p className="text-xs text-muted-foreground">
            {t('heartbeat.enable_description')}
          </p>
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
                onValueChange={(v) => handleUpdateFrequency('min', parseInt(v))}
                disabled={updating}
              >
                <SelectTrigger className="w-20">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Array.from({ length: 8 }, (_, i) => i + 1).map((n) => (
                    <SelectItem key={n} value={String(n)}>
                      {n}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <span className="text-muted-foreground">-</span>
              <Select
                value={String(settings.heartbeat_max_per_day)}
                onValueChange={(v) => handleUpdateFrequency('max', parseInt(v))}
                disabled={updating}
              >
                <SelectTrigger className="w-20">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Array.from({ length: 8 }, (_, i) => i + 1).map((n) => (
                    <SelectItem key={n} value={String(n)}>
                      {n}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <span className="text-sm text-muted-foreground">
                {t('heartbeat.per_day')}
              </span>
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
                onValueChange={(v) => handleUpdateHours('start', parseInt(v))}
                disabled={updating}
              >
                <SelectTrigger className="w-24">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {hourOptions.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <span className="text-muted-foreground">-</span>
              <Select
                value={settings.heartbeat_notify_end_hour.toString()}
                onValueChange={(v) => handleUpdateHours('end', parseInt(v))}
                disabled={updating}
              >
                <SelectTrigger className="w-24">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {hourOptions.map((opt) => (
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
              <p className="text-xs text-muted-foreground">
                {t('heartbeat.push_description')}
              </p>
            </div>
            <Switch
              id="heartbeat-push"
              checked={settings.heartbeat_push_enabled}
              onCheckedChange={handleTogglePush}
              disabled={updating || loading}
            />
          </div>

          {/* Available sources indicator */}
          <div className="space-y-2">
            <Label className="text-sm">{t('heartbeat.available_sources')}</Label>
            <div className="flex flex-wrap gap-2">
              {(['calendar', 'emails', 'tasks', 'weather', 'interests', 'memories'] as const).map((source) => {
                const isConnected = settings.available_sources.includes(source);
                const Icon = SOURCE_ICONS[source] || Brain;
                return (
                  <div
                    key={source}
                    className={`flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors ${
                      isConnected
                        ? 'bg-primary/10 text-primary'
                        : 'bg-muted text-muted-foreground opacity-50'
                    }`}
                  >
                    <Icon className="h-3.5 w-3.5" />
                    <span>{t(`heartbeat.source_${source}`)}</span>
                    {isConnected && (
                      <span className="h-1.5 w-1.5 rounded-full bg-green-500" />
                    )}
                  </div>
                );
              })}
            </div>
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
