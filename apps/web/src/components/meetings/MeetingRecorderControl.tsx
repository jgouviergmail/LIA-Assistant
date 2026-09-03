'use client';

/**
 * The recording controls outside the composer (ADR-259, owner decision 1).
 *
 * - `MeetingRecorderControl`: the header toggle from `lg` up — the shape of the
 *   voice and execution-mode toggles next to it. Record when idle; while a
 *   meeting is live it pulses red, shows the elapsed time where the row has
 *   room (`xl`) and stops on click.
 * - `useMeetingRecorderMenuAction`: the same two commands as a menu entry for
 *   the logo menu below `lg`, plus the live state that turns the trigger red.
 * - `RecorderAwareMobileNavMenu`: the logo menu wired to that hook, so the
 *   layout — rendered above the provider — needs no knowledge of the recorder.
 *
 * Neither renders where the recorder is not offered (no provider, no support).
 */

import { Disc } from 'lucide-react';

import {
  MobileNavMenu,
  type MobileNavAction,
  type MobileNavMenuProps,
} from '@/components/dashboard/MobileNavMenu';
import { useMeetingRecorderContext } from '@/components/meetings/MeetingRecorderProvider';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { formatElapsed } from '@/lib/meetings/format';
import { cn } from '@/lib/utils';
import { useMeetingRecorderStore, type MeetingRecorderPhase } from '@/stores/meetingRecorderStore';

/** Phases during which a click would race the controller. */
const BUSY_PHASES: readonly MeetingRecorderPhase[] = ['starting', 'stopping', 'processing'];

interface RecorderCommand {
  /** True while a meeting exists: the command is Stop. */
  live: boolean;
  busy: boolean;
  run: () => void;
}

/** The one command the recorder accepts now, or `null` where it is not offered. */
function useRecorderCommand(): RecorderCommand | null {
  const recorder = useMeetingRecorderContext();
  if (recorder === null || !recorder.isSupported) return null;
  const busy = BUSY_PHASES.includes(recorder.phase);
  const live = recorder.isLive;
  return {
    live,
    busy,
    run: () => {
      if (busy) return;
      void (live ? recorder.stop() : recorder.start());
    },
  };
}

export interface MeetingRecorderMenuBits {
  action: MobileNavAction;
  live: { label: string } | null;
}

/** The logo-menu entry and the live trigger state, or `null` where not offered. */
export function useMeetingRecorderMenuAction(lng: Language): MeetingRecorderMenuBits | null {
  const { t } = useTranslation(lng);
  const command = useRecorderCommand();
  if (command === null) return null;
  return {
    action: {
      label: t(command.live ? 'meetings.header.stop' : 'meetings.header.record'),
      icon: Disc,
      tone: command.live ? 'destructive' : 'default',
      disabled: command.busy,
      onSelect: command.run,
    },
    live: command.live ? { label: t('meetings.header.live_label') } : null,
  };
}

export function MeetingRecorderControl({ lng }: { lng: Language }) {
  const { t } = useTranslation(lng);
  const command = useRecorderCommand();
  // A zustand selector: this control re-renders once a second while live,
  // never at the level meter's cadence (the reason the context omits both).
  const elapsedSeconds = useMeetingRecorderStore(s => s.elapsedSeconds);
  if (command === null) return null;
  const label = t(command.live ? 'meetings.header.stop' : 'meetings.header.record');
  return (
    <Button
      variant="ghost"
      size="sm"
      className={cn(
        'h-11 w-11 px-0 max-[380px]:h-9 max-[380px]:w-9',
        command.live && 'xl:w-auto xl:gap-1 xl:px-2'
      )}
      onClick={command.run}
      aria-pressed={command.live}
      aria-disabled={command.busy}
      aria-label={label}
      title={label}
    >
      <Disc
        className={cn('h-[1.2rem] w-[1.2rem]', command.live && 'text-destructive animate-pulse')}
        aria-hidden="true"
        data-testid={command.live ? 'header-recording-dot' : undefined}
      />
      {command.live && (
        <span className="hidden text-xs tabular-nums xl:inline">
          {formatElapsed(elapsedSeconds)}
        </span>
      )}
    </Button>
  );
}

type RecorderAwareMobileNavMenuProps = Omit<MobileNavMenuProps, 'action' | 'live'> & {
  lng: Language;
};

/** The logo menu with the recorder entry when the instance offers recording. */
export function RecorderAwareMobileNavMenu({ lng, ...props }: RecorderAwareMobileNavMenuProps) {
  const bits = useMeetingRecorderMenuAction(lng);
  return <MobileNavMenu {...props} action={bits?.action} live={bits?.live ?? undefined} />;
}
