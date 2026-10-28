'use client';

import type { RefObject } from 'react';
import { useTranslation } from 'react-i18next';

import { BrickSearch } from './BrickSearch';
import { Constellation } from './Constellation';
import { FamilyLegend } from './FamilyLegend';
import { FlowPlayerCard } from './FlowPlayer';
import type { BrickMapState } from './use-brick-map';
import type { BrickMapView } from '@/lib/maps/types';

/** The same interactive overview on the living map and the public landing. */
export function FunctionalMapOverview({
  map,
  state,
  playerRef,
}: {
  map: BrickMapView;
  state: BrickMapState;
  playerRef: RefObject<HTMLDivElement | null>;
}) {
  const { t } = useTranslation();

  return (
    <div className="lm-overview lm-overview--functional">
      <div className="lm-side">
        <FamilyLegend
          kind="functional"
          families={map.families}
          selected={state.family}
          onToggle={state.toggleFamily}
        />
      </div>
      <div className="lm-stage">
        <BrickSearch
          value={state.query}
          placeholder={t('maps.functional.search_placeholder')}
          onChange={state.search}
          onSubmit={state.openFirstMatch}
        />
        <div
          className="lm-scroll-x"
          role="region"
          tabIndex={0}
          aria-label={t('maps.functional.constellation_label')}
        >
          <Constellation
            bricks={map.bricks}
            families={map.families}
            highlight={state.highlight}
            flow={state.player.active?.flow ?? null}
            animate
            onHover={state.hover}
            onSelect={state.select}
          />
        </div>
      </div>
      <div className="lm-side">
        <FlowPlayerCard ref={playerRef} flows={map.flows} player={state.player} refs={map.refs} />
      </div>
    </div>
  );
}
