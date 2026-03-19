'use client';

/**
 * SubAgentsSettings - Settings component for sub-agent delegation preference.
 *
 * Provides a toggle to enable/disable sub-agent delegation for the user.
 * When enabled, the principal assistant can delegate tasks to specialized
 * sub-agents (research, analysis, writing, etc.).
 *
 * Phase: F6 — Persistent Specialized Sub-Agents
 */

import { useState } from 'react';
import { Bot } from 'lucide-react';
import { Switch } from '@/components/ui/switch';
import { InfoBox } from '@/components/ui/info-box';
import { SettingsSection } from './SettingsSection';
import { useTranslation } from '@/i18n/client';
import { useAuth } from '@/hooks/useAuth';
import apiClient from '@/lib/api-client';
import { toast } from 'sonner';
import type { BaseSettingsProps } from '@/types/settings';

export function SubAgentsSettings({ lng, collapsible = true }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  const { user, refreshUser } = useAuth();
  const [updating, setUpdating] = useState(false);

  const handleToggle = async (enabled: boolean) => {
    if (!user || updating) return;

    setUpdating(true);
    try {
      await apiClient.patch('/auth/me/sub-agents-preference', {
        sub_agents_enabled: enabled,
      });

      await refreshUser();
      toast.success(
        enabled
          ? t('sub_agents.settings.enabled_success')
          : t('sub_agents.settings.disabled_success')
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
      <div className="flex items-center justify-between p-3 rounded-lg border bg-card">
        <div className="flex-1">
          <p className="text-sm font-medium">{t('sub_agents.settings.enable_toggle')}</p>
          <p className="text-xs text-muted-foreground">
            {t('sub_agents.settings.enable_description')}
          </p>
        </div>
        <Switch
          checked={user?.sub_agents_enabled ?? true}
          onCheckedChange={handleToggle}
          disabled={updating}
        />
      </div>

      {/* Info */}
      <InfoBox>
        <p className="text-xs text-muted-foreground">{t('sub_agents.settings.info')}</p>
      </InfoBox>
    </div>
  );

  if (!collapsible) return content;

  return (
    <SettingsSection
      value="sub-agents"
      title={t('sub_agents.settings.title')}
      description={t('sub_agents.settings.description')}
      icon={Bot}
    >
      {content}
    </SettingsSection>
  );
}
