'use client';

/**
 * VoiceOverlay - Full-screen overlay for voice mode.
 *
 * Displayed when voice mode is active, replacing the text input.
 * Shows visual feedback based on current state:
 * - Listening: Pulsing waves, "Tap to speak" instruction
 * - Recording: Active waves, recording indicator
 * - Processing: Spinner, processing message
 * - Speaking: Speaker icon, speaking indicator
 *
 * Usage:
 * ```tsx
 * <VoiceOverlay
 *   isEnabled={isVoiceModeEnabled}
 *   state={voiceModeState}
 *   onTap={startRecording}
 *   onDisable={disableVoiceMode}
 * />
 * ```
 *
 * Reference: plan zippy-drifting-valley.md (section 2.1)
 */

import { Mic, Volume2, Loader2, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { VoiceModeState } from '@/stores/voiceModeStore';

// ============================================================================
// Types
// ============================================================================

export interface VoiceOverlayProps {
  /** Whether voice mode is enabled */
  isEnabled: boolean;
  /** Current voice mode state */
  state: VoiceModeState;
  /** Callback when overlay is tapped (to start recording) */
  onTap: () => void;
  /** Callback when stop button is clicked (during recording) */
  onStop: () => void;
  /** Callback to disable voice mode */
  onDisable: () => void;
  /** Additional CSS classes */
  className?: string;
}

// ============================================================================
// Component
// ============================================================================

export function VoiceOverlay({
  isEnabled,
  state,
  onTap,
  onStop,
  onDisable,
  className,
}: VoiceOverlayProps) {
  const { t } = useTranslation();

  // Don't render if not enabled or in idle state
  if (!isEnabled || state === 'idle') {
    return null;
  }

  /**
   * Get instruction text based on state.
   */
  const getInstruction = (): string => {
    switch (state) {
      case 'listening':
        return t('chat.voice_mode.instruction_listening');
      case 'recording':
        return t('chat.voice_mode.instruction_recording');
      case 'processing':
        return t('chat.voice_mode.instruction_processing');
      case 'speaking':
        return t('chat.voice_mode.instruction_speaking');
      default:
        return '';
    }
  };

  /**
   * Get icon based on state.
   */
  const getIcon = () => {
    switch (state) {
      case 'processing':
        return <Loader2 className="h-16 w-16 animate-spin text-primary" />;
      case 'speaking':
        return <Volume2 className="h-16 w-16 text-green-500 animate-pulse" />;
      case 'recording':
      case 'listening':
      default:
        return <Mic className="h-16 w-16 text-primary" />;
    }
  };

  /**
   * Handle overlay click.
   */
  const handleClick = () => {
    if (state === 'listening') {
      onTap();
    } else if (state === 'recording') {
      onStop();
    }
  };

  const isClickable = state === 'listening' || state === 'recording';

  return (
    <div
      className={cn(
        'relative flex flex-col items-center justify-center',
        'py-8 px-4',
        'bg-card rounded-lg border',
        isClickable && 'cursor-pointer',
        className
      )}
      onClick={isClickable ? handleClick : undefined}
      role={isClickable ? 'button' : undefined}
      tabIndex={isClickable ? 0 : undefined}
      onKeyDown={
        isClickable
          ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                handleClick();
              }
            }
          : undefined
      }
      aria-label={getInstruction()}
    >
      {/* Close button */}
      <Button
        type="button"
        variant="ghost"
        size="icon"
        onClick={(e) => {
          e.stopPropagation();
          onDisable();
        }}
        className="absolute top-2 right-2 h-8 w-8"
        aria-label={t('chat.voice_mode.disable')}
      >
        <X className="h-4 w-4" />
      </Button>

      {/* Animated background waves */}
      <div className="relative mb-6">
        {/* Outer wave */}
        {(state === 'listening' || state === 'recording') && (
          <div
            className={cn(
              'absolute inset-0 rounded-full',
              'bg-primary/10',
              state === 'recording' ? 'animate-ping' : 'animate-pulse',
              'scale-[2]'
            )}
          />
        )}

        {/* Middle wave */}
        {state === 'recording' && (
          <div
            className={cn(
              'absolute inset-0 rounded-full',
              'bg-primary/20',
              'animate-ping animation-delay-150',
              'scale-[1.5]'
            )}
          />
        )}

        {/* Icon container */}
        <div
          className={cn(
            'relative flex items-center justify-center',
            'h-24 w-24 rounded-full',
            state === 'recording' && 'bg-red-500/10',
            state === 'listening' && 'bg-primary/10',
            state === 'processing' && 'bg-muted',
            state === 'speaking' && 'bg-green-500/10'
          )}
        >
          {getIcon()}
        </div>
      </div>

      {/* Instruction text */}
      <p
        className={cn(
          'text-center text-muted-foreground',
          state === 'recording' && 'text-red-600 font-medium'
        )}
      >
        {getInstruction()}
      </p>

      {/* Recording indicator */}
      {state === 'recording' && (
        <div className="mt-4 flex items-center gap-2 text-red-500">
          <span className="relative flex h-3 w-3">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-3 w-3 bg-red-500" />
          </span>
          <span className="text-sm font-medium">{t('chat.voice_mode.recording')}</span>
        </div>
      )}

      {/* Hint for listening state */}
      {state === 'listening' && (
        <p className="mt-4 text-xs text-muted-foreground">
          {t('chat.voice_mode.hint_tap_to_speak')}
        </p>
      )}
    </div>
  );
}
