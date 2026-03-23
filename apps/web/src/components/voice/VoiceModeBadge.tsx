'use client';

/**
 * VoiceModeBadge - Toggle badge for Voice Mode.
 *
 * Visual states:
 * - Inactive (gray): Click to enable voice mode
 * - Active/Listening (green): Waiting for user to speak
 * - Recording (green pulse): Recording user speech
 * - Processing (green spin): STT in progress
 *
 * Accessibility:
 * - aria-label describes current action
 * - aria-pressed indicates toggle state
 * - Keyboard accessible
 *
 * Usage:
 * ```tsx
 * <VoiceModeBadge
 *   onTranscription={(text) => sendMessage(text)}
 * />
 * ```
 *
 * Reference: plan zippy-drifting-valley.md (section 2.1)
 */

import { useCallback, useRef, useState } from 'react';
import { Mic, MicOff, Loader2 } from 'lucide-react';
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

// ============================================================================
// Types
// ============================================================================

export interface VoiceModeBadgeProps {
  /** Callback when transcription is received */
  onTranscription: (text: string) => void;
  /** Callback when TTS should start */
  onStartSpeaking?: () => void;
  /** Callback when TTS finishes */
  onStopSpeaking?: () => void;
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
    isKwsListening,
    isKwsSupported,
    toggle,
    startRecording,
    stopRecording,
    isSupported,
  } = useVoiceMode({
    onTranscription,
    onStartSpeaking,
    onStopSpeaking,
    onError: err => {
      toast.error(getErrorMessage(err));
    },
  });

  // Determine if we're in initialization phase (enabled but KWS mic not yet open).
  // When KWS is not supported (e.g. browser lacks SharedArrayBuffer/WASM), skip
  // the initializing state — voice mode works via tap-to-speak without wake word.
  const isInitializing = isEnabled && isListening && !isKwsListening && isKwsSupported;

  // Long-press state for toggle
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

  /**
   * Handle long-press start (pointer down).
   * Starts a timer that will toggle voice mode after LONG_PRESS_DURATION_MS.
   */
  const handlePressStart = useCallback(
    (e: React.MouseEvent | React.TouchEvent) => {
      // Prevent text selection on mobile
      if ('touches' in e) {
        e.preventDefault();
      }

      didLongPressRef.current = false;
      setIsLongPressing(true);

      longPressTimerRef.current = setTimeout(() => {
        didLongPressRef.current = true;
        setIsLongPressing(false);
        // Toggle voice mode on long-press
        const newEnabled = !isEnabled;
        toggle();
        // Show toast feedback
        if (isEnabled) {
          toast.info(t('chat.voice_mode.disabled_toast'));
        } else {
          toast.info(t('chat.voice_mode.enabled_toast'));
        }
        // Sync to server (non-blocking)
        syncToServer(newEnabled);
      }, LONG_PRESS_DURATION_MS);
    },
    [toggle, isEnabled, t, syncToServer]
  );

  /**
   * Handle long-press end (pointer up/leave).
   * Cancels the timer if not yet triggered.
   */
  const handlePressEnd = useCallback((e?: React.MouseEvent | React.TouchEvent) => {
    // Prevent text selection on mobile
    if (e && 'touches' in e) {
      e.preventDefault();
    }

    setIsLongPressing(false);
    if (longPressTimerRef.current) {
      clearTimeout(longPressTimerRef.current);
      longPressTimerRef.current = null;
    }
  }, []);

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

    if (!isEnabled) {
      // Show hint that long-press is needed to enable
      toast.info(t('chat.voice_mode.hold_to_enable'));
      return;
    }

    // Voice mode is enabled - handle based on current state
    if (state === 'listening') {
      // Start recording
      await startRecording();
    } else if (isRecording) {
      // Stop recording
      stopRecording();
    } else if (isProcessing || isSpeaking) {
      // Show hint that long-press is needed to disable
      toast.info(t('chat.voice_mode.hold_to_disable'));
    }
  }, [isEnabled, state, isRecording, isProcessing, isSpeaking, startRecording, stopRecording, t]);

  /**
   * Get aria-label based on state.
   */
  const getAriaLabel = (currentState: VoiceModeState, enabled: boolean): string => {
    if (!enabled) {
      return t('chat.voice_mode.hold_to_enable');
    }

    // Show initializing state while KWS is loading
    if (isInitializing) {
      return t('chat.voice_mode.badge_initializing');
    }

    switch (currentState) {
      case 'listening':
        return t('chat.voice_mode.click_to_speak');
      case 'recording':
        return t('chat.voice_mode.click_to_stop');
      case 'processing':
        return t('chat.voice_mode.processing');
      case 'speaking':
        return t('chat.voice_mode.speaking');
      default:
        return t('chat.voice_mode.hold_to_enable');
    }
  };

  /**
   * Get icon based on state.
   */
  const getIcon = (currentState: VoiceModeState, enabled: boolean, supported: boolean) => {
    if (!supported) {
      return <MicOff className="h-3.5 w-3.5" />;
    }

    if (!enabled) {
      return <Mic className="h-3.5 w-3.5" />;
    }

    // Show spinner during initialization
    if (isInitializing) {
      return <Loader2 className="h-3.5 w-3.5 animate-spin" />;
    }

    switch (currentState) {
      case 'processing':
        return <Loader2 className="h-3.5 w-3.5 animate-spin" />;
      case 'recording':
      case 'listening':
      case 'speaking':
        return <Mic className="h-3.5 w-3.5" />;
      default:
        return <Mic className="h-3.5 w-3.5" />;
    }
  };

  /**
   * Get badge classes based on state.
   */
  const getBadgeClasses = (currentState: VoiceModeState, enabled: boolean): string => {
    const baseClasses =
      'gap-2 text-[11px] mobile:text-xs font-semibold transition-all duration-200';

    if (!enabled) {
      // Inactive - gray
      return cn(baseClasses, 'bg-muted text-muted-foreground hover:bg-muted/80');
    }

    // Initializing - amber/orange with spinner
    if (isInitializing) {
      return cn(baseClasses, 'bg-amber-500 text-white', 'cursor-wait');
    }

    switch (currentState) {
      case 'recording':
        // Recording - green pulsing
        return cn(baseClasses, 'bg-green-500 text-white hover:bg-green-600', 'animate-pulse');
      case 'processing':
        // Processing - green with spinner
        return cn(baseClasses, 'bg-green-500/80 text-white', 'cursor-wait');
      case 'speaking':
        // Speaking - green solid
        return cn(baseClasses, 'bg-green-600 text-white hover:bg-green-700');
      case 'listening':
        // Listening - green
        return cn(baseClasses, 'bg-green-500 text-white hover:bg-green-600');
      default:
        // Fallback - gray (shouldn't happen normally)
        return cn(baseClasses, 'bg-muted text-muted-foreground');
    }
  };

  /**
   * Get label text.
   */
  const getLabel = (currentState: VoiceModeState, enabled: boolean): string => {
    if (!enabled) {
      return t('chat.voice_mode.badge_inactive');
    }

    // Show initializing state while KWS is loading
    if (isInitializing) {
      return t('chat.voice_mode.badge_initializing');
    }

    switch (currentState) {
      case 'listening':
        return t('chat.voice_mode.badge_listening');
      case 'recording':
        return t('chat.voice_mode.badge_recording');
      case 'processing':
        return t('chat.voice_mode.badge_processing');
      case 'speaking':
        return t('chat.voice_mode.badge_speaking');
      default:
        // Fallback to inactive label (shouldn't happen normally)
        return t('chat.voice_mode.badge_inactive');
    }
  };

  // Hide badge entirely when voice mode is disabled (user can re-enable from Settings)
  if (!isEnabled) {
    return null;
  }

  const isDisabled = disabled || !isSupported || isProcessing;

  return (
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
      disabled={isDisabled}
      aria-label={getAriaLabel(state, isEnabled)}
      aria-pressed={isEnabled}
      title={getAriaLabel(state, isEnabled)}
      className={cn(
        'px-3 py-1.5 rounded-full touch-manipulation',
        getBadgeClasses(state, isEnabled),
        isLongPressing && 'scale-95 opacity-80',
        className
      )}
    >
      {getIcon(state, isEnabled, isSupported)}
      <span className="hidden sm:inline">{getLabel(state, isEnabled)}</span>
    </Button>
  );
}
