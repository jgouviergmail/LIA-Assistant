'use client';

import { useId, useRef } from 'react';
import { useTranslation } from 'react-i18next';

import { BrickDrawer } from '@/components/maps/BrickDrawer';
import { FunctionalMapOverview } from '@/components/maps/FunctionalMapOverview';
import { useBrickMap } from '@/components/maps/use-brick-map';
import type { Language } from '@/i18n/settings';
import type { BrickMapView } from '@/lib/maps/types';
import '@/styles/maps.css';

/** The living functional map's overview, without its full documentation catalogue. */
export function LandingConstellation({ map, lng }: { map: BrickMapView; lng: Language }) {
  const { t } = useTranslation();
  const titleId = useId();
  const playerRef = useRef<HTMLDivElement>(null);
  const state = useBrickMap(map, playerRef);

  return (
    <section className="lia-maps landing-constellation" aria-labelledby={titleId}>
      <h2 id={titleId} className="sr-only">
        {t('maps.functional.overview_title')}
      </h2>
      <FunctionalMapOverview map={map} state={state} playerRef={playerRef} />
      <BrickDrawer
        map={map}
        brick={state.selected}
        lng={lng}
        onClose={state.close}
        onPlayFlow={state.playFlow}
      />
    </section>
  );
}
