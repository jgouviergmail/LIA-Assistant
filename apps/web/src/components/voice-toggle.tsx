'use client';

import * as React from 'react';
import { Volume2, VolumeX } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { useAuth } from '@/hooks/useAuth';
import { useVoicePlayback } from '@/hooks/useVoicePlayback';
import apiClient from '@/lib/api-client';
import { logger } from '@/lib/logger';
import { toast } from 'sonner';
import { useTranslation } from '@/i18n/client';
import { type Language } from '@/i18n/settings';

interface VoiceToggleProps {
  lng?: Language;
}

export function VoiceToggle({ lng = 'fr' }: VoiceToggleProps) {
  const { user, refreshUser } = useAuth();
  const { warmupAudio } = useVoicePlayback();
  const { t } = useTranslation(lng);
  const [mounted, setMounted] = React.useState(false);
  const [isLoading, setIsLoading] = React.useState(false);

  // Avoid hydration mismatch
  React.useEffect(() => {
    setMounted(true);
  }, []);

  const handleToggle = async () => {
    if (!user || isLoading) return;

    const newState = !user.voice_enabled;
    setIsLoading(true);

    try {
      await apiClient.patch('/auth/me/voice-preference', {
        voice_enabled: newState,
      });

      // iOS FIX: Warmup audio system when enabling voice
      // This is called during user gesture (click) which satisfies iOS autoplay policy
      // Playing a silent buffer "unlocks" the audio system for future playback
      if (newState) {
        warmupAudio().catch(err => {
          logger.warn('voice_toggle_warmup_failed', { error: err, component: 'VoiceToggle' });
          // Non-blocking - audio may still work on next interaction
        });
      }

      // Refresh user to get updated state
      await refreshUser();

      toast.success(newState ? t('voice.toggle.enabled') : t('voice.toggle.disabled'));
    } catch (error) {
      logger.error('voice_preference_update_failed', error as Error, { component: 'VoiceToggle' });
      toast.error(t('common.error'));
    } finally {
      setIsLoading(false);
    }
  };

  // Show placeholder during SSR
  if (!mounted) {
    return (
      <Button variant="ghost" size="sm" className="w-11 h-11 px-0">
        <Volume2 className="h-[1.2rem] w-[1.2rem]" />
        <span className="sr-only">{t('voice.toggle.enable')}</span>
      </Button>
    );
  }

  const isEnabled = user?.voice_enabled ?? false;

  return (
    <Button
      variant="ghost"
      size="sm"
      className="w-11 h-11 px-0"
      onClick={handleToggle}
      disabled={isLoading || !user}
      aria-label={isEnabled ? t('voice.toggle.disable') : t('voice.toggle.enable')}
      title={isEnabled ? t('voice.toggle.tooltip_enabled') : t('voice.toggle.tooltip_disabled')}
    >
      {isLoading ? (
        <LoadingSpinner className="h-[1.2rem] w-[1.2rem]" />
      ) : isEnabled ? (
        <Volume2 className="h-[1.2rem] w-[1.2rem] text-primary transition-all" />
      ) : (
        <VolumeX className="h-[1.2rem] w-[1.2rem] text-muted-foreground transition-all" />
      )}
      <span className="sr-only">
        {isEnabled ? t('voice.toggle.disable') : t('voice.toggle.enable')}
      </span>
    </Button>
  );
}
