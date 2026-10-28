'use client';

import { useRef } from 'react';
import { useTranslation } from 'react-i18next';

import { BrickDrawer } from './BrickDrawer';
import { FlowCards } from './FlowPlayer';
import { FunctionalMapOverview } from './FunctionalMapOverview';
import { MapIcon } from './map-icons';
import { SectionHead } from './SectionHead';
import { useBrickMap } from './use-brick-map';
import type { Language } from '@/i18n/settings';
import type { BrickMapView } from '@/lib/maps/types';

/**
 * The functional map: what LIA does, brick by brick — the constellation and its
 * journeys, the bricks grouped by family, and every journey written out.
 */
export function FunctionalMap({ map, lng }: { map: BrickMapView; lng: Language }) {
  const { t } = useTranslation();
  const playerRef = useRef<HTMLDivElement>(null);
  const state = useBrickMap(map, playerRef);
  const visible = (id: string) => state.matches === null || state.matches.has(id);
  const families = map.families
    .map(family => ({
      family,
      bricks: map.bricks.filter(b => b.family === family.id && visible(b.id)),
    }))
    .filter(entry => entry.bricks.length > 0);

  return (
    <>
      <section className="lm-section" aria-labelledby="lm-overview-title">
        <SectionHead
          id="lm-overview-title"
          kicker={t('maps.common.overview_kicker')}
          title={t('maps.functional.overview_title')}
          text={t('maps.functional.overview_text')}
        />
        <FunctionalMapOverview map={map} state={state} playerRef={playerRef} />
      </section>

      <section className="lm-section" aria-labelledby="lm-families-title">
        <SectionHead
          id="lm-families-title"
          kicker={t('maps.functional.families_kicker')}
          title={t('maps.functional.families_title')}
          text={t('maps.functional.families_text')}
        />
        {families.length ? (
          <div className="lm-families">
            {families.map(({ family, bricks }) => (
              <article
                key={family.id}
                className="lm-family"
                data-tone={family.tone}
                aria-labelledby={`lm-family-${family.id}`}
              >
                <div className="lm-family-head">
                  <span className="lm-badge-ic">
                    <MapIcon name={family.icon} size={20} />
                  </span>
                  <div>
                    <h3 id={`lm-family-${family.id}`}>{family.name}</h3>
                    <p>{family.summary}</p>
                  </div>
                </div>
                <ul className="lm-brick-list">
                  {bricks.map(brick => (
                    <li key={brick.id}>
                      <button
                        type="button"
                        className="lm-brick-row"
                        data-tone={brick.tone}
                        onClick={() => state.select(brick.id)}
                      >
                        <MapIcon name={brick.icon} size={18} />
                        <b>{brick.name}</b>
                        <small>{brick.goal}</small>
                      </button>
                    </li>
                  ))}
                </ul>
              </article>
            ))}
          </div>
        ) : (
          <p className="lm-no-results">{t('maps.common.no_match')}</p>
        )}
      </section>

      <section className="lm-section" aria-labelledby="lm-flows-title">
        <SectionHead
          id="lm-flows-title"
          kicker={t('maps.common.flows_kicker')}
          title={t('maps.functional.flows_title')}
          text={t('maps.functional.flows_text')}
        />
        <FlowCards
          flows={map.flows}
          refs={map.refs}
          page="functional"
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
