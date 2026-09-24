'use client';

import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import {
  CONSTELLATION_CENTER,
  CONSTELLATION_SIZE,
  flowBadges,
  flowPath,
  layoutConstellation,
} from '@/lib/maps/constellation';
import { edgeKey, type Highlight } from '@/lib/maps/highlight';
import type { BrickView, FamilyView, FlowView } from '@/lib/maps/types';
import { cn } from '@/lib/utils';

/** The one gradient a journey is drawn with (a single constellation per page). */
const FLOW_GRADIENT_ID = 'lm-flow-gradient';

/**
 * The functional map's overview: every brick on one circle, grouped by family,
 * its dependencies drawn as curves. A node is a focusable button — hovering or
 * focusing it traces its links, activating it opens its detail — and a journey
 * being played is drawn over the web with its step numbers.
 */
export function Constellation({
  bricks,
  families,
  highlight,
  flow,
  animate,
  onHover,
  onSelect,
}: {
  bricks: readonly BrickView[];
  families: readonly FamilyView[];
  highlight: Highlight;
  flow: FlowView | null;
  animate: boolean;
  onHover: (id: string | null) => void;
  onSelect: (id: string) => void;
}) {
  const { t } = useTranslation();
  const layout = useMemo(() => layoutConstellation(families, bricks), [families, bricks]);
  const familyById = useMemo(() => new Map(families.map(f => [f.id, f])), [families]);
  const steps = useMemo(() => flow?.steps.map(s => s.brick) ?? [], [flow]);
  const path = useMemo(() => (steps.length ? flowPath(steps, layout.nodes) : ''), [steps, layout]);
  const badges = useMemo(() => flowBadges(steps, layout.nodes), [steps, layout]);

  return (
    <svg
      className={cn('lm-constellation', highlight.active && 'is-focus')}
      viewBox={`0 0 ${CONSTELLATION_SIZE} ${CONSTELLATION_SIZE}`}
      role="group"
      aria-label={t('maps.functional.constellation_label')}
    >
      <defs>
        <linearGradient id={FLOW_GRADIENT_ID} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#4f8dfd" />
          <stop offset="0.55" stopColor="#8b5cf6" />
          <stop offset="1" stopColor="#38d4f5" />
        </linearGradient>
      </defs>
      <g aria-hidden="true">
        {layout.arcs.map(arc => (
          <path
            key={arc.family}
            className="lm-arc"
            data-tone={familyById.get(arc.family)?.tone}
            d={arc.d}
          />
        ))}
      </g>
      <g aria-hidden="true">
        {layout.edges.map(edge => {
          const key = edgeKey(edge.from, edge.to);
          return (
            <path
              key={key}
              className={cn(
                'lm-edge',
                highlight.out.has(key) && 'is-out',
                highlight.in.has(key) && 'is-in'
              )}
              d={edge.d}
            />
          );
        })}
      </g>
      {path && (
        <path
          aria-hidden="true"
          className={cn('lm-flowpath', animate && 'is-animated')}
          stroke={`url(#${FLOW_GRADIENT_ID})`}
          d={path}
        />
      )}
      <g className="lm-core" aria-hidden="true">
        <text className="lm-core-name" x={CONSTELLATION_CENTER} y={CONSTELLATION_CENTER - 6}>
          LIA
        </text>
        <text x={CONSTELLATION_CENTER} y={CONSTELLATION_CENTER + 30}>
          {`${t('maps.stats.bricks', { count: bricks.length, value: bricks.length })} · ${t('maps.stats.families', { count: families.length, value: families.length })}`}
        </text>
      </g>
      <g>
        {bricks.map(brick => {
          const node = layout.nodes.get(brick.id);
          if (!node) return null;
          const family = familyById.get(brick.family);
          return (
            <g
              key={brick.id}
              className={cn(
                'lm-node',
                highlight.on.has(brick.id) && 'is-on',
                highlight.near.has(brick.id) && 'is-near'
              )}
              data-tone={brick.tone}
              data-brick={brick.id}
              role="button"
              tabIndex={0}
              aria-label={`${brick.name} — ${family?.name ?? ''}`}
              transform={`translate(${node.x} ${node.y})`}
              onMouseEnter={() => onHover(brick.id)}
              onMouseLeave={() => onHover(null)}
              onFocus={() => onHover(brick.id)}
              onBlur={() => onHover(null)}
              onClick={() => onSelect(brick.id)}
              onKeyDown={event => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  onSelect(brick.id);
                }
              }}
            >
              <circle r={7} />
              <text
                x={node.labelLeft ? -16 : 16}
                textAnchor={node.labelLeft ? 'end' : 'start'}
                transform={`rotate(${node.labelRotation})`}
              >
                {brick.name}
              </text>
            </g>
          );
        })}
      </g>
      {badges.length > 0 && (
        <g aria-hidden="true">
          {badges.map(badge => (
            <g
              key={badge.id}
              className={cn('lm-badge', badge.id === highlight.current && 'is-current')}
              transform={`translate(${badge.x} ${badge.y})`}
            >
              <circle r={12} />
              <text>{badge.label}</text>
            </g>
          ))}
        </g>
      )}
    </svg>
  );
}
