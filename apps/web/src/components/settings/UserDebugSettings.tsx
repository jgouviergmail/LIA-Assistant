'use client';

import { useState } from 'react';
import { Bug } from 'lucide-react';
import { Switch } from '@/components/ui/switch';
import { InfoBox } from '@/components/ui/info-box';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { useTranslation } from '@/i18n/client';
import { useAuth } from '@/hooks/useAuth';
import apiClient from '@/lib/api-client';
import { toast } from 'sonner';

import type { BaseSettingsProps } from '@/types/settings';

export function UserDebugSettings({ lng, collapsible = true }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  const { user, refreshUser } = useAuth();
  const [updating, setUpdating] = useState(false);

  const handleToggle = async (enabled: boolean) => {
    if (!user || updating) return;

    setUpdating(true);
    try {
      await apiClient.patch('/auth/me/debug-panel-preference', {
        debug_panel_enabled: enabled,
      });

      await refreshUser();
      toast.success(
        enabled
          ? t('settings.preferences.debug.enabledSuccess')
          : t('settings.preferences.debug.disabledSuccess')
      );
    } catch {
      toast.error(t('common.error'));
    } finally {
      setUpdating(false);
    }
  };

  const content = (
    <div className="space-y-4">
      {/* Toggle */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between p-3 rounded-lg border bg-card">
        <div className="flex-1">
          <p className="text-sm font-medium">{t('settings.preferences.debug.enable')}</p>
          <p className="text-xs text-muted-foreground">
            {t('settings.preferences.debug.enableDescription')}
          </p>
        </div>
        <Switch
          className="shrink-0"
          checked={user?.debug_panel_enabled ?? false}
          onCheckedChange={handleToggle}
          disabled={updating}
        />
      </div>

      {/* Info */}
      <InfoBox>
        <p className="text-xs text-muted-foreground">
          {t('settings.preferences.debug.info')}
        </p>
      </InfoBox>
    </div>
  );

  if (!collapsible) {
    return content;
  }

  return (
    <SettingsSection
      value="debug-panel"
      title={t('settings.preferences.debug.title')}
      description={t('settings.preferences.debug.description')}
      icon={Bug}
    >
      {content}
    </SettingsSection>
  );
}
