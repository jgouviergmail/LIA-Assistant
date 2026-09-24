'use client';

import { useRef } from 'react';
import { useTranslation } from 'react-i18next';

import { BrickDrawer } from './BrickDrawer';
import { BrickSearch } from './BrickSearch';
import { FamilyLegend } from './FamilyLegend';
import { FlowCards, FlowPlayerCard } from './FlowPlayer';
import { LayersBoard } from './LayersBoard';
import { SectionHead } from './SectionHead';
import { useBrickMap } from './use-brick-map';
import type { Language } from '@/i18n/settings';
import type { BrickMapView } from '@/lib/maps/types';

/**
 * The technical map: how LIA is built, layer by layer — the layers and their
 * links, the journeys through them, and every journey written out.
 */
export function TechnicalMap({ map, lng }: { map: BrickMapView; lng: Language }) {
  const { t } = useTranslation();
  const playerRef = useRef<HTMLDivElement>(null);
  const state = useBrickMap(map, playerRef);

  return (
    <>
      <section className="lm-section" aria-labelledby="lm-overview-title">
        <SectionHead
          id="lm-overview-title"
          kicker={t('maps.common.overview_kicker')}
          title={t('maps.technical.overview_title')}
          text={t('maps.technical.overview_text')}
        />
        <div className="lm-overview">
          <div className="lm-stage">
            <BrickSearch
              value={state.query}
              placeholder={t('maps.technical.search_placeholder')}
              onChange={state.search}
              onSubmit={state.openFirstMatch}
            />
            <LayersBoard
              layers={map.families}
              bricks={map.bricks}
              highlight={state.highlight}
              flow={state.player.active}
              onHover={state.hover}
              onSelect={state.select}
            />
          </div>
          <div className="lm-side">
            <FlowPlayerCard
              ref={playerRef}
              flows={map.flows}
              player={state.player}
              refs={map.refs}
            />
            <FamilyLegend
              kind="technical"
              families={map.families}
              selected={state.family}
              onToggle={state.toggleFamily}
            />
          </div>
        </div>
      </section>

      <section className="lm-section" aria-labelledby="lm-flows-title">
        <SectionHead
          id="lm-flows-title"
          kicker={t('maps.common.flows_kicker')}
          title={t('maps.technical.flows_title')}
          text={t('maps.technical.flows_text')}
        />
        <FlowCards
          flows={map.flows}
          refs={map.refs}
          page="technical"
          lng={lng}
          onReplay={state.playFlow}
        />
      </section>

      <BrickDrawer
        map={map}
        brick={state.selected}
        lng={lng}
        onClose={state.close}
        onPlayFlow={state.playFlow}
      />
    </>
  );
}
