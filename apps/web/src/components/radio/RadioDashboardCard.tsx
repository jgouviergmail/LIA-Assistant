'use client';

/**
 * The radio on the dashboard (ADR-324, owner decision Q6): the station's name,
 * what it does, the one command it accepts now — the header's own, so the
 * click that starts it also starts the station's music (the browser's autoplay
 * rule). Nothing renders where the instance does not offer the radio.
 *
 * The name is the one the session on air carries once it names it; tuning
 * in, off air and once the session is over, the listener's own name for it
 * (the one the next session will carry), else their language's.
 */
import { Radio } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { useRadioStationName } from '@/hooks/useRadioStationName';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { useRadioStore } from '@/stores/radioStore';

import { useRadioCommand } from './RadioControl';

// A station illustration, deliberately static: these bars do not claim to
// meter playback or require a second player/audio subscription.
const STATION_WAVE_HEIGHTS = [14, 24, 38, 28, 52, 42, 30, 46, 34, 22, 12];

export function RadioDashboardCard({ lng, enabled }: { lng: Language; enabled: boolean }) {
  const { t } = useTranslation(lng);
  const command = useRadioCommand(enabled);
  // An ended session keeps its name for the bar that says why it ended; the
  // card speaks of the station, which the listener may have renamed since.
  const onAirName = useRadioStore(state =>
    state.view.status === 'ended' ? null : state.view.stationName
  );
  const chosenName = useRadioStationName(enabled);
  if (command === null) return null;
  const name = onAirName ?? chosenName ?? t('radio.station_name');
  return (
    <Card className="min-w-0 overflow-hidden border-primary/15 bg-card shadow-sm">
      <CardContent className="flex flex-col gap-4 bg-gradient-to-r from-primary/5 via-transparent to-transparent p-4 sm:p-6 lg:flex-row lg:items-center">
        <div className="flex min-w-0 flex-1 items-center gap-4 sm:gap-5">
          <div
            className="flex h-16 w-12 shrink-0 items-center justify-center gap-0.5 text-primary"
            aria-hidden="true"
          >
            {STATION_WAVE_HEIGHTS.map((height, index) => (
              <span key={index} className="w-0.5 rounded-full bg-current" style={{ height }} />
            ))}
          </div>
          <div className="min-w-0 space-y-1.5">
            <h2 className="flex items-center gap-2 text-base font-semibold">
              <Radio className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
              <span className="min-w-0 break-words">{name}</span>
            </h2>
            <p className="break-words text-sm leading-relaxed text-muted-foreground">
              {t('radio.page.subtitle')}
            </p>
          </div>
        </div>
        <div className="flex w-full shrink-0 flex-col gap-2 lg:w-48">
          <Button
            onClick={command.run}
            className="h-auto min-h-11 whitespace-normal px-3 py-2"
            aria-pressed={command.onAir}
            aria-busy={command.busy}
            variant={command.onAir ? 'destructive' : 'default'}
            aria-disabled={command.busy || undefined}
          >
            {t(command.onAir ? 'radio.header.stop' : 'radio.header.start')}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
