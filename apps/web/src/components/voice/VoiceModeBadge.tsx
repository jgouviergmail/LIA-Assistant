'use client';

/**
 * VoiceModeBadge - the chat header's hands-free (voice mode) control.
 *
 * ALWAYS rendered, as an icon alone at every width — the state rides the icon
 * and the colour, the words ride the accessible name and the tooltip:
 * - Off (muted, greyed microphone): a tap turns hands-free mode on.
 * - Unsupported browser (greyed, crossed microphone): disabled, named as such.
 * - On, a long press (500 ms, or holding Space) turns it off; a tap acts on
 *   the current state:
 *   - Initializing (amber spin): the wake-word model still loading
 *   - Listening (green microphone): a tap starts recording — its name says
 *     the phrase while the wake word listens, and « tap » when it cannot
 *   - Recording (green pulse): a tap stops recording
 *   - Processing (green spin): STT in progress, disabled
 *   - Speaking (green audio lines): LIA's answer playing — distinct from
 *     listening by its icon, since no label tells the two apart any more
 *
 * Both transitions persist the preference server-side, the same PATCH the
 * Settings › Voice switch sends, and are announced with that page's own words
 * through a polite status beside the badge — never a toast, which the toaster
 * would stack right over the badge.
 *
 * Accessibility:
 * - aria-label describes what a tap does now
 * - aria-pressed reflects whether hands-free mode is on
 * - the long press has a keyboard equivalent: holding Space (Enter is a tap)
 *
 * Usage:
 * ```tsx
 * <VoiceModeBadge
 *   onTranscription={(text) => sendMessage(text)}
 * />
 * ```
 */

import { useCallback, useRef, useState } from 'react';
import { AudioLines, Mic, MicOff, Loader2 } from 'lucide-react';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useVoiceMode } from '@/hooks/useVoiceMode';
import { useAuth } from '@/hooks/useAuth';
import apiClient from '@/lib/api-client';
import { logger } from '@/lib/logger';
import type { VoiceModeState } from '@/stores/voiceModeStore';

// Long-press duration in milliseconds
const LONG_PRESS_DURATION_MS = 500;

/**
 * What the badge shows: the hook's state, refined by the two situations the
 * hook does not name as a state — a browser that cannot capture, and the
 * wake-word model still loading. `off` covers « enabled but idle » too, which
 * nothing else would offer a way out of.
 */
type BadgePhase = 'unsupported' | 'off' | 'initializing' | Exclude<VoiceModeState, 'idle'>;

function badgePhaseOf(
  isSupported: boolean,
  isEnabled: boolean,
  isInitializing: boolean,
  state: VoiceModeState
): BadgePhase {
  if (!isSupported) return 'unsupported';
  if (!isEnabled || state === 'idle') return 'off';
  if (isInitializing) return 'initializing';
  return state;
}

const ICON_CLASSES = 'h-3.5 w-3.5';

/** One icon per phase: with no visible label, the icon carries the state. */
const PHASE_ICONS: Record<BadgePhase, React.ReactNode> = {
  unsupported: <MicOff className={ICON_CLASSES} />,
  off: <Mic className={ICON_CLASSES} />,
  initializing: <Loader2 className={cn(ICON_CLASSES, 'animate-spin')} />,
  listening: <Mic className={ICON_CLASSES} />,
  recording: <Mic className={ICON_CLASSES} />,
  processing: <Loader2 className={cn(ICON_CLASSES, 'animate-spin')} />,
  speaking: <AudioLines className={ICON_CLASSES} />,
};

/**
 * Off, the badge takes the header's discreet pill tone (the spaces indicator's
 * own classes) — greyed, not hidden; on, the green family it always had.
 */
const DISCREET_CLASSES =
  'border border-border/60 bg-muted/50 text-muted-foreground shadow-sm hover:bg-muted hover:text-foreground';

const PHASE_CLASSES: Record<BadgePhase, string> = {
  unsupported: DISCREET_CLASSES,
  off: DISCREET_CLASSES,
  initializing: 'bg-amber-500 text-white cursor-wait',
  listening: 'bg-green-500 text-white hover:bg-green-600',
  recording: 'bg-green-500 text-white hover:bg-green-600 animate-pulse',
  processing: 'bg-green-500/80 text-white cursor-wait',
  speaking: 'bg-green-600 text-white hover:bg-green-700',
};

/**
 * What a tap does while the mode listens: the phrase to say (and the word that
 * cuts LIA's voice, when the model ships it), or the button alone when no
 * phrase is listening.
 */
function listeningLabelOf(
  t: TFunction,
  listening: boolean,
  phrase: string | null,
  stopWord: string | null
): string {
  if (!listening || !phrase) return t('chat.voice_mode.click_to_speak');
  return stopWord
    ? t('chat.voice_mode.hint_listening_stop', { phrase, stop: stopWord })
    : t('chat.voice_mode.hint_listening', { phrase });
}

/** The badge's accessible name: what a tap does now, or why it cannot. */
function ariaLabelOf(t: TFunction, phase: BadgePhase, listeningLabel: string): string {
  switch (phase) {
    case 'unsupported':
      return t('chat.voice_mode.error_not_supported');
    case 'off':
      return t('chat.voice_mode.enable');
    case 'initializing':
      return t('chat.voice_mode.badge_initializing');
    case 'listening':
      return listeningLabel;
    case 'recording':
      return t('chat.voice_mode.click_to_stop');
    case 'processing':
      return t('chat.voice_mode.processing');
    case 'speaking':
      return t('chat.voice_mode.speaking');
  }
}

// ============================================================================
// Types
// ============================================================================

export interface VoiceModeBadgeProps {
  /** Callback when transcription is received. The optional ``meta`` payload
   *  carries STT cost metadata (set when the backend ran a remote provider). */
  onTranscription: (
    text: string,
    meta?: import('@/lib/voice-input-service').VoiceTranscriptionMeta
  ) => void;
  /** Callback when TTS should start */
  onStartSpeaking?: () => void;
  /** Callback when TTS finishes */
  onStopSpeaking?: () => void;
  /** The person spoke over LIA (her phrase, or the stop word): cut her voice */
  onInterrupt?: () => void;
  /** Disable the badge */
  disabled?: boolean;
  /** Additional CSS classes */
  className?: string;
}

// ============================================================================
// Component
// ============================================================================

export function VoiceModeBadge({
  onTranscription,
  onStartSpeaking,
  onStopSpeaking,
  onInterrupt,
  disabled = false,
  className,
}: VoiceModeBadgeProps) {
  const { t } = useTranslation();
  const { refreshUser } = useAuth();

  /**
   * Get user-friendly error message.
   */
  const getErrorMessage = useCallback(
    (err: Error): string => {
      if (err.message.includes('permission denied') || err.message.includes('Permission denied')) {
        return t('chat.voice_mode.error_permission');
      }
      if (err.message.includes('not supported')) {
        return t('chat.voice_mode.error_not_supported');
      }
      if (err.message.includes('ticket') || err.message.includes('Connection')) {
        return t('chat.voice_mode.error_connection');
      }
      return t('chat.voice_mode.error_generic');
    },
    [t]
  );

  const {
    isEnabled,
    state,
    isRecording,
    isProcessing,
    isSpeaking,
    isListening,
    wakeWordState,
    wakePhrase,
    stopWord,
    enable,
    disable,
    startRecording,
    stopRecording,
    isSupported,
  } = useVoiceMode({
    onTranscription,
    onStartSpeaking,
    onStopSpeaking,
    onInterrupt,
    onError: err => {
      toast.error(getErrorMessage(err));
    },
  });

  // Initializing while the wake-word model loads. Anything else — listening,
  // unavailable (no model, no runtime), paused, a refused microphone — leaves
  // the badge usable: voice mode works tap-to-speak without the phrase, and a
  // badge stuck on « initializing » would say otherwise.
  const isInitializing = isEnabled && isListening && wakeWordState === 'loading';
  const listeningLabel = listeningLabelOf(t, wakeWordState === 'listening', wakePhrase, stopWord);

  const phase = badgePhaseOf(isSupported, isEnabled, isInitializing, state);
  const label = ariaLabelOf(t, phase, listeningLabel);
  const isOn = phase !== 'off' && phase !== 'unsupported';

  // Long-press state (turning hands-free mode OFF)
  const longPressTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [isLongPressing, setIsLongPressing] = useState(false);
  const didLongPressRef = useRef(false);

  /**
   * Sync voice mode preference to server.
   */
  const syncToServer = useCallback(
    async (enabled: boolean) => {
      try {
        await apiClient.patch('/auth/me/voice-mode-preference', {
          voice_mode_enabled: enabled,
        });
        await refreshUser();
      } catch (err) {
        logger.warn('voice_mode_badge_sync_failed', {
          component: 'VoiceModeBadge',
          error: err,
        });
        // Non-blocking - local state still works
      }
    },
    [refreshUser]
  );

  // Both transitions say what happened with the Settings › Voice page's own
  // words, and persist through the same PATCH that page sends. They are
  // ANNOUNCED (a polite status beside the badge), never toasted: the toaster
  // stacks at the top centre, right over this badge, so a toast saying « off »
  // swallowed the very click that turns the mode back on (measured in a real
  // Chromium, 2026-10-01). The badge's colour and icon show the state.
  const [announcement, setAnnouncement] = useState('');

  const turnOn = useCallback(() => {
    enable();
    setAnnouncement(t('settings.voice_mode.enabled_success'));
    void syncToServer(true);
  }, [enable, t, syncToServer]);

  const turnOff = useCallback(() => {
    disable();
    setAnnouncement(t('settings.voice_mode.disabled_success'));
    void syncToServer(false);
  }, [disable, t, syncToServer]);

  /** Cancels a long press not yet fired (release, leave, blur). */
  const cancelLongPress = useCallback(() => {
    setIsLongPressing(false);
    if (longPressTimerRef.current) {
      clearTimeout(longPressTimerRef.current);
      longPressTimerRef.current = null;
    }
  }, []);

  /**
   * Arms the long press. It only ever turns hands-free mode OFF: while the mode
   * is off nothing is armed, and the click that ends the press turns it on.
   */
  const armLongPress = useCallback(() => {
    didLongPressRef.current = false;
    if (!isOn) return;
    cancelLongPress();
    setIsLongPressing(true);
    longPressTimerRef.current = setTimeout(() => {
      longPressTimerRef.current = null;
      didLongPressRef.current = true;
      setIsLongPressing(false);
      turnOff();
    }, LONG_PRESS_DURATION_MS);
  }, [isOn, cancelLongPress, turnOff]);

  /**
   * Handle long-press start (pointer down).
   */
  const handlePressStart = useCallback(
    (e: React.MouseEvent | React.TouchEvent) => {
      // Prevent text selection on mobile
      if ('touches' in e) {
        e.preventDefault();
      }
      armLongPress();
    },
    [armLongPress]
  );

  /**
   * Handle long-press end (pointer up/leave).
   */
  const handlePressEnd = useCallback(
    (e?: React.MouseEvent | React.TouchEvent) => {
      // Prevent text selection on mobile
      if (e && 'touches' in e) {
        e.preventDefault();
      }
      cancelLongPress();
    },
    [cancelLongPress]
  );

  /**
   * The keyboard's long press is holding Space: a button activates on Space's
   * RELEASE, so the click that follows a fired press is swallowed like a
   * pointer's. Enter activates on press, so it stays a tap.
   */
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === ' ' && !e.repeat) armLongPress();
    },
    [armLongPress]
  );

  const handleKeyUp = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === ' ') cancelLongPress();
    },
    [cancelLongPress]
  );

  /**
   * Handle badge click (short tap).
   * Only processes if long-press didn't trigger.
   */
  const handleClick = useCallback(async () => {
    // If long-press triggered, ignore click
    if (didLongPressRef.current) {
      didLongPressRef.current = false;
      return;
    }

    if (phase === 'off') {
      turnOn();
    } else if (state === 'listening') {
      // Start recording
      await startRecording();
    } else if (isRecording) {
      // Stop recording
      stopRecording();
    } else if (isProcessing || isSpeaking) {
      // Show hint that long-press is needed to disable
      toast.info(t('chat.voice_mode.hold_to_disable'));
    }
  }, [
    phase,
    state,
    isRecording,
    isProcessing,
    isSpeaking,
    turnOn,
    startRecording,
    stopRecording,
    t,
  ]);

  const isDisabled = disabled || !isSupported || isProcessing;

  return (
    <>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={handleClick}
        onMouseDown={handlePressStart}
        onMouseUp={handlePressEnd}
        onMouseLeave={handlePressEnd}
        onTouchStart={handlePressStart}
        onTouchEnd={handlePressEnd}
        onKeyDown={handleKeyDown}
        onKeyUp={handleKeyUp}
        onBlur={cancelLongPress}
        disabled={isDisabled}
        aria-label={label}
        aria-pressed={isEnabled}
        // The tooltip adds how to turn the mode off, on its own line so no
        // language has to join two sentences with punctuation of ours.
        title={isOn ? `${label}\n${t('chat.voice_mode.hold_to_disable')}` : label}
        className={cn(
          'px-2 sm:px-3 py-1.5 rounded-full touch-manipulation transition-all duration-200',
          PHASE_CLASSES[phase],
          isLongPressing && 'scale-95 opacity-80',
          className
        )}
      >
        {PHASE_ICONS[phase]}
      </Button>
      <span role="status" className="sr-only">
        {announcement}
      </span>
    </>
  );
}
