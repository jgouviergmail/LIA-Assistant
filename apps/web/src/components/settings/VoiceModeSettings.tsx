'use client';

/**
 * VoiceModeSettings — Settings component for Voice Mode (wake word + STT input).
 *
 * Two controls:
 * 1. Toggle to enable/disable voice mode globally. When enabled, the
 *    VoiceModeBadge appears in the chat header.
 * 2. RadioGroup-style picker for the STT backend ("local" Sherpa, free,
 *    or "remote" ElevenLabs Scribe, paid). Visible only when voice mode is
 *    enabled. The "remote" option is disabled when no ElevenLabs API key
 *    is configured by the admin.
 */

import { useState, useEffect } from 'react';
import { Mic, Cloud, Server, AlertTriangle } from 'lucide-react';
import { Switch } from '@/components/ui/switch';
import { InfoBox } from '@/components/ui/info-box';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { useTranslation } from '@/i18n/client';
import { useAuth } from '@/hooks/useAuth';
import { useVoiceModeStore } from '@/stores/voiceModeStore';
import apiClient from '@/lib/api-client';
import { toast } from 'sonner';
import type { BaseSettingsProps } from '@/types/settings';

type SttMode = 'local' | 'remote';

interface VoiceModePreferenceResponse {
  voice_mode_enabled: boolean;
  voice_stt_mode: SttMode;
  stt_remote_available: boolean;
  message?: string;
}

export function VoiceModeSettings({ lng, collapsible = true }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  const { user, refreshUser } = useAuth();
  const { enable: storeEnable, disable: storeDisable } = useVoiceModeStore();
  const [updating, setUpdating] = useState(false);
  const [sttRemoteAvailable, setSttRemoteAvailable] = useState<boolean | null>(null);

  // Sync Zustand store with server preference when server state changes.
  // Zustand ignores same-value updates, so this is safe to call on every render.
  const serverVoiceModeEnabled = user?.voice_mode_enabled ?? false;
  const serverSttMode: SttMode = (user?.voice_stt_mode as SttMode) ?? 'local';

  useEffect(() => {
    if (serverVoiceModeEnabled) {
      storeEnable();
    } else {
      storeDisable();
    }
  }, [serverVoiceModeEnabled, storeEnable, storeDisable]);

  // Probe the backend once on mount to know whether the admin has configured
  // an ElevenLabs API key. Falls back to "available" so the UI doesn't lock
  // the user out on a transient backend error.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const response = await apiClient.get<VoiceModePreferenceResponse>(
          '/auth/me/voice-mode-preference'
        );
        if (!cancelled) {
          setSttRemoteAvailable(response.stt_remote_available);
        }
      } catch {
        if (!cancelled) {
          setSttRemoteAvailable(true);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleToggleEnabled = async (enabled: boolean) => {
    if (!user || updating) return;

    setUpdating(true);
    try {
      await apiClient.patch('/auth/me/voice-mode-preference', {
        voice_mode_enabled: enabled,
      });

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

  const handleSttModeChange = async (newMode: SttMode) => {
    if (!user || updating || newMode === serverSttMode) return;
    if (newMode === 'remote' && sttRemoteAvailable === false) {
      toast.error(t('settings.voice_mode.stt_remote_unavailable_warning'));
      return;
    }

    setUpdating(true);
    try {
      await apiClient.patch('/auth/me/voice-mode-preference', {
        voice_stt_mode: newMode,
      });
      await refreshUser();
      toast.success(t('settings.voice_mode.stt_mode_updated_success'));
    } catch {
      toast.error(t('common.error'));
    } finally {
      setUpdating(false);
    }
  };

  const remoteDisabled = sttRemoteAvailable === false;

  const content = (
    <div className="space-y-4">
      {/* STT backend picker — ALWAYS visible. Applies to both push-to-talk
          (long-press send button) AND the wake-word "voice mode" below. The
          backend resolves the right service per /voice/ticket payload. */}
      <div className="rounded-lg border bg-card p-3 space-y-3">
        <p className="text-sm font-medium">{t('settings.voice_mode.stt_mode_label')}</p>

        <div className="grid gap-2 sm:grid-cols-2">
          <SttModeOption
            icon={<Server className="h-4 w-4" />}
            label={t('settings.voice_mode.stt_mode_local')}
            description={t('settings.voice_mode.stt_mode_local_description')}
            selected={serverSttMode === 'local'}
            disabled={updating}
            onClick={() => handleSttModeChange('local')}
          />
          <SttModeOption
            icon={<Cloud className="h-4 w-4" />}
            label={t('settings.voice_mode.stt_mode_remote')}
            description={t('settings.voice_mode.stt_mode_remote_description')}
            selected={serverSttMode === 'remote'}
            disabled={updating || remoteDisabled}
            onClick={() => handleSttModeChange('remote')}
          />
        </div>

        {remoteDisabled && (
          <div className="flex items-start gap-2 rounded-md bg-amber-500/10 p-2 text-xs text-amber-700 dark:text-amber-300">
            <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
            <span>{t('settings.voice_mode.stt_remote_unavailable_warning')}</span>
          </div>
        )}

        {serverSttMode === 'remote' && !remoteDisabled && (
          <InfoBox>
            <p className="text-xs text-muted-foreground">
              {t('settings.voice_mode.stt_remote_privacy_notice')}
            </p>
          </InfoBox>
        )}
      </div>

      {/* Wake-word voice mode toggle — opt-in for hands-free, uses the STT
          backend selected above. Push-to-talk works regardless of this. */}
      <div className="flex items-center justify-between p-3 rounded-lg border bg-card">
        <div className="flex-1">
          <p className="text-sm font-medium">{t('settings.voice_mode.enable')}</p>
          <p className="text-xs text-muted-foreground">
            {t('settings.voice_mode.enable_description')}
          </p>
        </div>
        <Switch
          checked={user?.voice_mode_enabled ?? false}
          onCheckedChange={handleToggleEnabled}
          disabled={updating}
        />
      </div>

      {/* Generic voice mode info */}
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

interface SttModeOptionProps {
  icon: React.ReactNode;
  label: string;
  description: string;
  selected: boolean;
  disabled: boolean;
  onClick: () => void;
}

function SttModeOption({
  icon,
  label,
  description,
  selected,
  disabled,
  onClick,
}: SttModeOptionProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-pressed={selected}
      className={[
        'flex flex-col items-start gap-1 rounded-md border p-3 text-left transition-colors',
        selected
          ? 'border-primary bg-primary/5 ring-1 ring-primary'
          : 'border-border bg-background hover:bg-muted',
        disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer',
      ].join(' ')}
    >
      <span className="flex items-center gap-2 text-sm font-medium">
        {icon}
        {label}
      </span>
      <span className="text-xs text-muted-foreground">{description}</span>
    </button>
  );
}
