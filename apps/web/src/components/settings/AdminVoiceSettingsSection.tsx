'use client';

import { toast } from 'sonner';
import { Volume2 } from 'lucide-react';
import { InfoBox } from '@/components/ui/info-box';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { useApiMutation } from '@/hooks/useApiMutation';
import { useApiQuery } from '@/hooks/useApiQuery';
import { useTranslation } from '@/i18n/client';
import { SettingsSection } from '@/components/settings/SettingsSection';

// API endpoint constant to avoid duplication
const VOICE_MODE_ENDPOINT = '/admin/system-settings/voice-mode';

interface VoiceTTSModeResponse {
  mode: 'standard' | 'hd';
  updated_by: string | null;
  updated_at: string | null;
  is_default: boolean;
}

import type { BaseSettingsProps } from '@/types/settings';

export default function AdminVoiceSettingsSection({ lng, collapsible = true }: BaseSettingsProps) {
  const { t } = useTranslation(lng, 'translation');

  // Fetch current voice mode
  const {
    data: voiceMode,
    loading,
    setData,
  } = useApiQuery<VoiceTTSModeResponse>(VOICE_MODE_ENDPOINT, {
    componentName: 'AdminVoiceSettingsSection',
    initialData: {
      mode: 'standard',
      updated_by: null,
      updated_at: null,
      is_default: true,
    },
  });

  // Mutation for updating voice mode
  const { mutate: updateMode, loading: updating } = useApiMutation({
    method: 'PUT',
    componentName: 'AdminVoiceSettingsSection',
  });

  const isHDMode = voiceMode?.mode === 'hd';

  const handleToggle = async (checked: boolean) => {
    const newMode = checked ? 'hd' : 'standard';

    try {
      await updateMode(VOICE_MODE_ENDPOINT, { mode: newMode });

      // Optimistic update
      setData(prev => {
        if (!prev) return prev;
        return {
          ...prev,
          mode: newMode,
          is_default: false,
          updated_at: new Date().toISOString(),
        };
      });
    } catch {
      toast.error(t('settings.admin.voice.error'));
    }
  };

  const content = loading ? (
    <div className="animate-pulse text-muted-foreground py-4">{t('common.loading')}</div>
  ) : (
    <div className="space-y-6">
      {/* Voice Mode Toggle */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between p-4 border border-border rounded-lg">
        <div className="flex-1 space-y-1">
          <Label htmlFor="voice-mode" className="text-base font-medium">
            {t('settings.admin.voice.modeLabel')}
          </Label>
          <div className="text-sm text-muted-foreground">
            {isHDMode ? (
              <span className="text-primary font-medium">
                {t('settings.admin.voice.modes.hd.label')} -{' '}
                {t('settings.admin.voice.modes.hd.description')}
              </span>
            ) : (
              <span className="text-primary font-medium">
                {t('settings.admin.voice.modes.standard.label')} -{' '}
                {t('settings.admin.voice.modes.standard.description')}
              </span>
            )}
          </div>
          {voiceMode?.updated_at && !voiceMode?.is_default && (
            <div className="text-xs text-muted-foreground mt-1">
              {t('settings.admin.voice.lastUpdated')}:{' '}
              {new Date(voiceMode.updated_at).toLocaleString(lng)}
            </div>
          )}
          {voiceMode?.is_default && (
            <div className="text-xs text-muted-foreground mt-1">
              {t('settings.admin.voice.usingDefault')}
            </div>
          )}
        </div>

        <div className="flex items-center gap-3 shrink-0">
          <span className="text-sm text-muted-foreground">
            {t('settings.admin.voice.modes.standard.label')}
          </span>
          <Switch
            id="voice-mode"
            checked={isHDMode}
            onCheckedChange={handleToggle}
            disabled={updating}
            aria-label={t('settings.admin.voice.toggleLabel')}
          />
          <span className="text-sm font-medium text-primary">
            {t('settings.admin.voice.modes.hd.label')}
          </span>
        </div>
      </div>

      {/* Info Box */}
      <div className="p-4 bg-muted/50 rounded-lg space-y-3">
        <div className="text-sm font-medium">{t('settings.admin.voice.modesTitle')}:</div>
        <div className="space-y-2 text-sm text-muted-foreground">
          <div className="flex items-start gap-2">
            <span className="text-primary">●</span>
            <div>
              <span className="font-medium text-foreground">
                {t('settings.admin.voice.modes.standard.label')}
              </span>
              {' - '}
              {t('settings.admin.voice.standardInfo')}
            </div>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-primary">●</span>
            <div>
              <span className="font-medium text-foreground">
                {t('settings.admin.voice.modes.hd.label')}
              </span>
              {' - '}
              {t('settings.admin.voice.hdInfo')}
            </div>
          </div>
        </div>
      </div>

      {/* Impact Notice */}
      <InfoBox className="p-4">
        <div className="text-sm text-muted-foreground">
          <strong className="text-foreground">{t('settings.admin.voice.impactTitle')}:</strong>{' '}
          {t('settings.admin.voice.impactDescription')}
        </div>
      </InfoBox>
    </div>
  );

  return (
    <SettingsSection
      value="admin-voice"
      title={t('settings.admin.voice.title')}
      description={t('settings.admin.voice.description')}
      icon={Volume2}
      collapsible={collapsible}
    >
      {content}
    </SettingsSection>
  );
}
