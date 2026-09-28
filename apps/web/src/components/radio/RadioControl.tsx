'use client';

/**
 * The radio's header control (ADR-324): the station on and off from any page.
 *
 * - `RadioControl`: the header toggle from `lg` up, the shape of the recorder's
 *   and the voice toggles beside it. Off: « Start the radio » — the click
 *   itself starts the station's music, which is what lets every segment after
 *   it play (the browser's autoplay rule). On air: « Stop the radio ».
 * - `useRadioMenuAction`: the same command as an entry of the logo menu below
 *   `lg`, where the header has no width for another control (the recorder's
 *   measured constraint, ADR-259).
 *
 * - `useRadioCommand`: that one command, for any other surface that offers it
 *   (the dashboard's card).
 *
 * None renders where the instance does not offer the radio.
 */

import { Radio } from 'lucide-react';

import type { MobileNavAction } from '@/components/dashboard/MobileNavMenu';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { isOnAir } from '@/lib/radio/machine';
import { radioPlayer } from '@/lib/radio/player';
import { cn } from '@/lib/utils';
import { useRadioStore } from '@/stores/radioStore';

export interface RadioCommand {
  /** True while a session runs: the command is Stop. */
  onAir: boolean;
  /** The station is signing off: a click would race the stop in flight. */
  busy: boolean;
  run: () => void;
}

/** The one command the radio accepts now, or `null` where it is not offered. */
export function useRadioCommand(enabled: boolean): RadioCommand | null {
  const status = useRadioStore(state => state.view.status);
  if (!enabled) return null;
  // Signing off is still « on air » for the listener: the command stays Stop,
  // unavailable until the farewell has been decided.
  const busy = status === 'ending';
  const onAir = isOnAir(status) || busy;
  return {
    onAir,
    busy,
    run: () => {
      if (busy) return;
      const player = radioPlayer();
      void (onAir ? player.stop() : player.start());
    },
  };
}

/** The logo-menu entry, or `null` where the radio is not offered. */
export function useRadioMenuAction(lng: Language, enabled: boolean): MobileNavAction | null {
  const { t } = useTranslation(lng);
  const command = useRadioCommand(enabled);
  if (command === null) return null;
  return {
    label: t(command.onAir ? 'radio.header.stop' : 'radio.header.start'),
    icon: Radio,
    tone: command.onAir ? 'destructive' : 'default',
    disabled: command.busy,
    onSelect: command.run,
  };
}

export function RadioControl({ lng, enabled }: { lng: Language; enabled: boolean }) {
  const { t } = useTranslation(lng);
  const command = useRadioCommand(enabled);
  if (command === null) return null;
  const label = t(command.onAir ? 'radio.header.stop' : 'radio.header.start');
  return (
    <Button
      variant="ghost"
      size="sm"
      className="h-11 w-11 px-0 max-[380px]:h-9 max-[380px]:w-9"
      onClick={command.run}
      aria-pressed={command.onAir}
      aria-disabled={command.busy}
      aria-label={label}
      title={label}
    >
      <Radio
        className={cn(
          'h-[1.2rem] w-[1.2rem]',
          command.onAir && 'text-primary motion-safe:animate-pulse'
        )}
        aria-hidden="true"
      />
    </Button>
  );
}
