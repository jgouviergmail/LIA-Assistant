'use client';

/**
 * Page-level binding of the guided showroom to the credential-less emitter.
 *
 * This is the ONLY place the missions meet telemetry: the mission component
 * stays pure/injectable for tests, and the guided branch never renders
 * TrackView — trackProductEvent would attach the session cookie the
 * showroom contract forbids. `demo_viewed` fires once per page mount
 * (StrictMode-safe), whatever mission the visitor picks.
 *
 * The picker owns which mission is mounted; a keyed remount gives every
 * mission a fresh state machine and per-run event guards. The picker is
 * deliberately WIDER than a mission (max-w-5xl vs max-w-2xl): six cards
 * need browsing room, a running mission needs reading width.
 */

import { useEffect, useRef, useState } from 'react';
import { ArrowLeft } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { HonestyStrip } from '@/components/showroom/HonestyStrip';
import { MissionPicker } from '@/components/showroom/MissionPicker';
import { ShowroomMission } from '@/components/showroom/ShowroomMission';
import { getShowroomMission, SHOWROOM_MISSIONS } from '@/components/showroom/missions';
import type { ShowroomMissionId } from '@/components/showroom/types';
import { Button } from '@/components/ui/button';
import { trackShowroomEvent } from '@/lib/product-telemetry';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';
import type { Language } from '@/i18n/settings';

export function GuidedShowroom({ lng }: { lng: string }) {
  const { t } = useTranslation();
  const [missionId, setMissionId] = useState<ShowroomMissionId | null>(null);
  const viewedRef = useRef(false);

  useEffect(() => {
    if (viewedRef.current) return;
    viewedRef.current = true;
    trackShowroomEvent('demo_viewed');
  }, []);

  if (missionId !== null) {
    return (
      <ShowroomMission
        key={missionId}
        def={getShowroomMission(missionId)}
        onEvent={trackShowroomEvent}
        onChangeMission={() => setMissionId(null)}
      />
    );
  }

  return (
    <div className="mx-auto w-full max-w-5xl space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold text-foreground">{t('showroom.title')}</h2>
        {/* Plain <a>, not <Link>: /demo skips auth hydration (lib/auth.tsx),
            so leaving it must be a full navigation — a client-side transition
            would carry the unhydrated null session onto the landing. */}
        <Button asChild type="button" variant="ghost" size="sm">
          <a href={buildLocalizedPath('/', lng as Language)} data-testid="showroom-back-home">
            <ArrowLeft className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
            {t('showroom.back_home')}
          </a>
        </Button>
      </div>
      <HonestyStrip />
      <MissionPicker missions={SHOWROOM_MISSIONS} onSelect={setMissionId} />
    </div>
  );
}
