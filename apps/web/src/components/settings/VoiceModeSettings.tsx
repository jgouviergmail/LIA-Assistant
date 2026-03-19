'use client';

/**
 * VoiceModeSettings - Settings component for Voice Mode (wake word + STT input).
 *
 * Provides a toggle to enable/disable voice mode globally.
 * When enabled, the VoiceModeBadge appears in the chat header.
 *
 * Reference: plan zippy-drifting-valley.md (section 2.3)
 */

import { useState, useEffect } from 'react';
import { Mic } from 'lucide-react';
import { Switch } from '@/components/ui/switch';
import { InfoBox } from '@/components/ui/info-box';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { useTranslation } from '@/i18n/client';
import { useAuth } from '@/hooks/useAuth';
import { useVoiceModeStore } from '@/stores/voiceModeStore';
import apiClient from '@/lib/api-client';
import { toast } from 'sonner';
import type { BaseSettingsProps } from '@/types/settings';

export function VoiceModeSettings({ lng, collapsible = true }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  const { user, refreshUser } = useAuth();
  const { enable: storeEnable, disable: storeDisable } = useVoiceModeStore();
  const [updating, setUpdating] = useState(false);

  // Sync Zustand store with server preference when server state changes
  // Zustand ignores same-value updates, so this is safe to call on every render
  const serverVoiceModeEnabled = user?.voice_mode_enabled ?? false;
  useEffect(() => {
    if (serverVoiceModeEnabled) {
      storeEnable();
    } else {
      storeDisable();
    }
  }, [serverVoiceModeEnabled, storeEnable, storeDisable]);

  /**
   * Handle voice mode toggle.
   */
  const handleToggle = async (enabled: boolean) => {
    if (!user || updating) return;

    setUpdating(true);
    try {
      await apiClient.patch('/auth/me/voice-mode-preference', {
        voice_mode_enabled: enabled,
      });

      // Sync Zustand store with new state
      if (enabled) {
        storeEnable();
      } else {
        storeDisable();
      }

      await refreshUser();
      toast.success(
        enabled
          ? t('settings.voice_mode.enabled_success')
          : t('settings.voice_mode.disabled_success')
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
          <p className="text-sm font-medium">{t('settings.voice_mode.enable')}</p>
          <p className="text-xs text-muted-foreground">
            {t('settings.voice_mode.enable_description')}
          </p>
        </div>
        <Switch
          checked={user?.voice_mode_enabled ?? false}
          onCheckedChange={handleToggle}
          disabled={updating}
        />
      </div>

      {/* Info */}
      <InfoBox>
        <p className="text-xs text-muted-foreground">{t('settings.voice_mode.info')}</p>
        <p className="text-xs text-muted-foreground mt-2">
          {t('settings.voice_mode.experimental_note')}
        </p>
      </InfoBox>
    </div>
  );

  if (!collapsible) {
    return content;
  }

  return (
    <SettingsSection
      value="voice-mode"
      title={t('settings.voice_mode.title')}
      description={t('settings.voice_mode.description')}
      icon={Mic}
    >
      {content}
    </SettingsSection>
  );
}
