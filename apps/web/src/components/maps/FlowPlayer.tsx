'use client';

import { Pause, Play, Route, StepBack, StepForward, X } from 'lucide-react';
import { forwardRef } from 'react';
import { useTranslation } from 'react-i18next';

import { MapIcon } from './map-icons';
import { BrickChip } from './MapLink';
import type { Language } from '@/i18n/settings';
import type { FlowPlayer as FlowPlayerState } from '@/lib/maps/use-flow-player';
import type { BrickRef, FlowView, MapPage } from '@/lib/maps/types';
import { cn } from '@/lib/utils';

/**
 * The side panel that plays a journey on the map: pick a scenario, and its
 * steps light up one at a time. Every control is a native button with a
 * translated name; the step counter is announced politely.
 */
export const FlowPlayerCard = forwardRef<
  HTMLDivElement,
  {
    flows: readonly FlowView[];
    player: FlowPlayerState;
    refs: Readonly<Record<string, BrickRef>>;
  }
>(function FlowPlayerCard({ flows, player, refs }, ref) {
  const { t } = useTranslation();
  const active = player.active;
  return (
    <div className="lm-card" ref={ref}>
      <h3>
        <Route aria-hidden="true" width={18} height={18} className="lm-ic" />
        {t('maps.player.title')}
      </h3>
      <p className="lm-sub">{t('maps.player.text')}</p>
      {active && (
        <div className="lm-player">
          <p className="lm-sub">{active.flow.summary}</p>
          <div className="lm-player-controls">
            <button
              type="button"
              className="lm-icon-btn"
              aria-label={t('maps.player.previous')}
              onClick={() => player.goTo(player.step - 1)}
            >
              <StepBack aria-hidden="true" width={16} height={16} />
            </button>
            <button
              type="button"
              className="lm-icon-btn"
              aria-label={player.playing ? t('maps.player.pause') : t('maps.player.play')}
              onClick={player.togglePlay}
            >
              {player.playing ? (
                <Pause aria-hidden="true" width={16} height={16} />
              ) : (
                <Play aria-hidden="true" width={16} height={16} />
              )}
            </button>
            <button
              type="button"
              className="lm-icon-btn"
              aria-label={t('maps.player.next')}
              onClick={() => player.goTo(player.step + 1)}
            >
              <StepForward aria-hidden="true" width={16} height={16} />
            </button>
            <button
              type="button"
              className="lm-icon-btn"
              aria-label={t('maps.player.quit')}
              onClick={player.clear}
            >
              <X aria-hidden="true" width={16} height={16} />
            </button>
            <span className="lm-count" aria-live="polite">
              {t('maps.player.step', {
                current: player.step + 1,
                total: active.flow.steps.length,
              })}
            </span>
          </div>
          <ol className="lm-steps">
            {active.flow.steps.map((step, index) => (
              <li key={`${step.brick}-${index}`}>
                <button
                  type="button"
                  className={cn('lm-step', index < player.step && 'is-done')}
                  aria-current={index === player.step ? 'step' : undefined}
                  onClick={() => player.goTo(index)}
                >
                  <span className="lm-num" aria-hidden="true">
                    {index + 1}
                  </span>
                  <span className="lm-step-text">
                    <b>{refs[step.brick]?.name ?? step.brick}</b>
                    <span>{step.text}</span>
                  </span>
                </button>
              </li>
            ))}
          </ol>
        </div>
      )}
      <ul className="lm-flow-list" aria-label={t('maps.player.flows_label')}>
        {flows.map((flow, index) => (
          <li key={flow.id}>
            <button
              type="button"
              className="lm-flow-btn"
              aria-pressed={player.index === index}
              onClick={() => player.toggleFlow(index)}
            >
              <MapIcon name={flow.icon} size={16} />
              <span>{flow.name}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
});

/**
 * Every journey written out, step by step, each step naming its brick — the
 * readable version of what the player animates, with a button to replay it.
 */
export function FlowCards({
  flows,
  refs,
  page,
  lng,
  onReplay,
}: {
  flows: readonly FlowView[];
  refs: Readonly<Record<string, BrickRef>>;
  page: MapPage;
  lng: Language;
  onReplay: (id: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="lm-flows-grid">
      {flows.map(flow => (
        <article key={flow.id} className="lm-flow-card" aria-labelledby={`lm-flow-${flow.id}`}>
          <h3 id={`lm-flow-${flow.id}`}>
            <span className="lm-badge-ic" data-tone="blue">
              <MapIcon name={flow.icon} size={18} />
            </span>
            {flow.name}
          </h3>
          <p>{flow.summary}</p>
          <ol>
            {flow.steps.map((step, index) => {
              const brick = refs[step.brick];
              return (
                <li key={`${step.brick}-${index}`}>
                  <span className="lm-num" aria-hidden="true">
                    {index + 1}
                  </span>
                  <div>
                    {brick && <BrickChip brick={brick} from={page} lng={lng} />}
                    <div>{step.text}</div>
                  </div>
                </li>
              );
            })}
          </ol>
          <button type="button" className="lm-linkish" onClick={() => onReplay(flow.id)}>
            <Play aria-hidden="true" width={14} height={14} />
            {t('maps.player.replay')}
          </button>
        </article>
      ))}
    </div>
  );
}
