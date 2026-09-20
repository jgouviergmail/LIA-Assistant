'use client';

/**
 * The voice icon of the header: the spoken-replies toggle — and, when the
 * live mode is offered to this account (ADR-299, wave 2 spec A1), a menu
 * with entries drawn alike, an icon before each: the spoken replies (a
 * checkbox), « Live session (<provider>) », named after the provider the
 * sessions open on (ADR-300; owner decision 2026-09-19), and — where the
 * chosen model's wire carries a tool schema — « Direct live session
 * (<provider>) », the phone's own line in the browser (ADR-300 wave 4). One
 * icon for the voices, and they are EXCLUSIVE (owner decision 2026-09-19): starting
 * a session switches the spoken replies off without a word, the checkbox is
 * refused while a session is open, and the icon shows whichever voice is
 * on — the live waveform while a session runs, the speaker otherwise. The
 * toast that greets a live session is the banner's, on the session's own
 * `live` status, because a click is a request and the session opens a
 * second later — or not at all (a refused microphone).
 *
 * Starting a session from here: the chat page owns the session (it holds the
 * chat's doors), so the menu asks through the store and, off the chat page,
 * navigates there — the client-side navigation keeps the click's activation,
 * which the audio context needs.
 */

import * as React from 'react';
import { AudioLines, Radio, Volume2, VolumeX } from 'lucide-react';
import { usePathname } from 'next/navigation';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { useAuth } from '@/hooks/useAuth';
import { useLiveAvailability } from '@/hooks/useLiveAvailability';
import { useLocalizedRouter } from '@/hooks/useLocalizedRouter';
import { useVoicePlayback } from '@/hooks/useVoicePlayback';
import { useTranslation } from '@/i18n/client';
import { type Language } from '@/i18n/settings';
import apiClient from '@/lib/api-client';
import { liveProviderLabel } from '@/lib/live/providers';
import { isSessionOpen } from '@/lib/live/session-machine';
import type { LiveSessionMode } from '@/lib/live/types';
import { logger } from '@/lib/logger';
import { useLiveStore } from '@/stores/liveStore';
import { useMeetingIsCapturing } from '@/stores/meetingRecorderStore';

interface VoiceToggleProps {
  lng?: Language;
}

const ICON = 'h-[1.2rem] w-[1.2rem]';
const TRIGGER = 'w-11 h-11 px-0 max-[380px]:w-9 max-[380px]:h-9';

/** The spoken-replies preference: the PATCH, the audio warmup, the refresh, the toasts. */
function useSpokenRepliesToggle(lng: Language) {
  const { user, refreshUser } = useAuth();
  const { warmupAudio } = useVoicePlayback();
  const { t } = useTranslation(lng);
  const [isLoading, setIsLoading] = React.useState(false);
  const isEnabled = user?.voice_enabled ?? false;

  const toggle = async () => {
    if (!user || isLoading) return;
    const newState = !user.voice_enabled;
    setIsLoading(true);
    try {
      await apiClient.patch('/auth/me/voice-preference', { voice_enabled: newState });
      // iOS FIX: warm the audio system up during the user gesture (click),
      // which satisfies the autoplay policy; a silent buffer unlocks playback.
      if (newState) {
        warmupAudio().catch(err => {
          logger.warn('voice_toggle_warmup_failed', { error: err, component: 'VoiceToggle' });
        });
      }
      await refreshUser();
      toast.success(newState ? t('voice.toggle.enabled') : t('voice.toggle.disabled'));
    } catch (error) {
      logger.error('voice_preference_update_failed', error as Error, { component: 'VoiceToggle' });
      toast.error(t('common.error'));
    } finally {
      setIsLoading(false);
    }
  };

  /** The spoken replies off, without a toast: the live session takes the voice. */
  const disableQuietly = async () => {
    if (!user?.voice_enabled) return;
    try {
      await apiClient.patch('/auth/me/voice-preference', { voice_enabled: false });
      await refreshUser();
    } catch (error) {
      // The session still opens; the API silences the replies on a delegated turn anyway.
      logger.warn('voice_preference_off_for_live_failed', {
        error: error as Error,
        component: 'VoiceToggle',
      });
    }
  };

  return { user, isEnabled, isLoading, toggle, disableQuietly };
}

function VoiceIcon({
  isEnabled,
  isLoading,
  liveOpen = false,
}: {
  isEnabled: boolean;
  isLoading: boolean;
  liveOpen?: boolean;
}) {
  if (isLoading) return <LoadingSpinner className={ICON} />;
  if (liveOpen) return <AudioLines className={`${ICON} text-primary transition-all`} />;
  if (isEnabled) return <Volume2 className={`${ICON} text-primary transition-all`} />;
  return <VolumeX className={`${ICON} text-muted-foreground transition-all`} />;
}

/** The chat page is where a session lives; anywhere else, the menu navigates there first. */
function useOnChatPage(): boolean {
  const pathname = usePathname();
  return /\/dashboard\/chat\/?$/.test(pathname ?? '');
}

/** Why the live entry is refused right now, or null. */
function useLiveEntryReason(lng: Language): string | null {
  const { t } = useTranslation(lng);
  const liveOpen = useLiveStore(state => isSessionOpen(state.status));
  const meetingCapturing = useMeetingIsCapturing();
  if (liveOpen) return t('voice.toggle.live_busy');
  if (meetingCapturing) return t('voice.toggle.live_meeting');
  return null;
}

/** The trigger's tooltip: the live session first, then the spoken replies. */
function triggerTitle(t: (key: string) => string, liveOpen: boolean, isEnabled: boolean) {
  if (liveOpen) return t('voice.toggle.live_active');
  return isEnabled ? t('voice.toggle.tooltip_enabled') : t('voice.toggle.tooltip_disabled');
}

interface LiveMenuProps {
  lng: Language;
  state: ReturnType<typeof useSpokenRepliesToggle>;
  /** The provider the sessions open on, named on the entry. */
  provider: string;
  /** The chosen model can hold a DIRECT session: the third entry is drawn. */
  directTools: boolean;
}

/** The voices in one menu: the spoken replies, a live session, a direct one where it can run. */
function LiveMenu({ lng, state, provider, directTools }: LiveMenuProps) {
  const { t } = useTranslation(lng);
  const onChatPage = useOnChatPage();
  const router = useLocalizedRouter();
  const liveReason = useLiveEntryReason(lng);
  const liveOpen = useLiveStore(state => isSessionOpen(state.status));

  const startLive = (mode: LiveSessionMode) => {
    // Exclusive voices: the spoken replies go off, then the session is asked for.
    void state.disableQuietly();
    useLiveStore.getState().requestStart(mode);
    if (!onChatPage) router.push('/dashboard/chat');
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className={TRIGGER}
          disabled={!state.user}
          aria-label={t('voice.toggle.menu')}
          title={triggerTitle(t, liveOpen, state.isEnabled)}
        >
          <VoiceIcon isEnabled={state.isEnabled} isLoading={state.isLoading} liveOpen={liveOpen} />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuCheckboxItem
          checked={state.isEnabled}
          disabled={state.isLoading || liveOpen}
          onSelect={() => void state.toggle()}
          title={liveOpen ? t('voice.toggle.comments_live_busy') : undefined}
          className="gap-2"
        >
          <Volume2 aria-hidden="true" className="h-4 w-4 shrink-0" />
          {t('voice.toggle.comments')}
          {liveOpen && <span className="sr-only"> — {t('voice.toggle.comments_live_busy')}</span>}
        </DropdownMenuCheckboxItem>
        <DropdownMenuItem
          inset
          disabled={liveReason !== null}
          onSelect={() => startLive('delegated')}
          title={liveReason ?? undefined}
        >
          <AudioLines aria-hidden="true" />
          {t('voice.toggle.live_start', { provider: liveProviderLabel(provider) })}
          {liveReason && <span className="sr-only"> — {liveReason}</span>}
        </DropdownMenuItem>
        {directTools && (
          <DropdownMenuItem
            inset
            disabled={liveReason !== null}
            onSelect={() => startLive('direct')}
            title={liveReason ?? undefined}
          >
            <Radio aria-hidden="true" />
            {t('voice.toggle.live_direct_start', { provider: liveProviderLabel(provider) })}
            {liveReason && <span className="sr-only"> — {liveReason}</span>}
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function VoiceToggle({ lng = 'fr' }: VoiceToggleProps) {
  const { t } = useTranslation(lng);
  const state = useSpokenRepliesToggle(lng);
  const live = useLiveAvailability();
  const [mounted, setMounted] = React.useState(false);

  // Avoid hydration mismatch
  React.useEffect(() => {
    setMounted(true);
  }, []);

  // Show placeholder during SSR
  if (!mounted) {
    return (
      <Button variant="ghost" size="sm" className={TRIGGER}>
        <Volume2 className={ICON} />
        <span className="sr-only">{t('voice.toggle.enable')}</span>
      </Button>
    );
  }

  if (live.available && live.provider !== null) {
    return (
      <LiveMenu lng={lng} state={state} provider={live.provider} directTools={live.directTools} />
    );
  }

  const label = state.isEnabled ? t('voice.toggle.disable') : t('voice.toggle.enable');
  return (
    <Button
      variant="ghost"
      size="sm"
      className={TRIGGER}
      onClick={() => void state.toggle()}
      disabled={state.isLoading || !state.user}
      aria-label={label}
      title={
        state.isEnabled ? t('voice.toggle.tooltip_enabled') : t('voice.toggle.tooltip_disabled')
      }
    >
      <VoiceIcon isEnabled={state.isEnabled} isLoading={state.isLoading} />
      <span className="sr-only">{label}</span>
    </Button>
  );
}
