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
    <Card>
      <CardContent className="flex flex-col gap-4 p-4 sm:flex-row sm:items-center sm:p-6">
        <div className="flex min-w-0 flex-1 items-start gap-3">
          <div className="flex shrink-0 rounded-lg bg-primary/10 p-2">
            <Radio className="h-5 w-5 text-primary" aria-hidden="true" />
          </div>
          <div className="min-w-0 space-y-1">
            <h2 className="text-base font-semibold">{name}</h2>
            <p className="text-sm text-muted-foreground">{t('radio.page.subtitle')}</p>
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <Button
            onClick={command.run}
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
