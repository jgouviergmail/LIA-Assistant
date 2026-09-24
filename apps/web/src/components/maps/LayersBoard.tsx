'use client';

import { useEffect, useMemo, useRef } from 'react';

import { MapIcon } from './map-icons';
import { connectorPath, connectorSegments, type Box } from '@/lib/maps/connectors';
import { stepNumbers, type Highlight } from '@/lib/maps/highlight';
import type { BrickView, FamilyView, FlowView } from '@/lib/maps/types';
import { cn } from '@/lib/utils';

const SVG_NS = 'http://www.w3.org/2000/svg';
const FLOW_GRADIENT_ID = 'lm-tflow-gradient';

/**
 * The technical map's overview: the layers of the system, from the screen to
 * the database, each brick a button. Its links are drawn in an overlay the
 * effect owns: they depend on where the bricks landed after the layout, so they
 * are measured, and redrawn whenever the board is resized.
 */
export function LayersBoard({
  layers,
  bricks,
  highlight,
  flow,
  onHover,
  onSelect,
}: {
  layers: readonly FamilyView[];
  bricks: readonly BrickView[];
  highlight: Highlight;
  flow: { flow: FlowView; step: number } | null;
  onHover: (id: string | null) => void;
  onSelect: (id: string) => void;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const linksRef = useRef<SVGGElement>(null);
  const badges = useMemo(() => (flow ? stepNumbers(flow.flow) : null), [flow]);
  const segments = useMemo(
    () =>
      connectorSegments(
        highlight.out,
        highlight.in,
        flow ? { steps: flow.flow.steps.map(s => s.brick), step: flow.step } : null
      ),
    [highlight, flow]
  );

  useEffect(() => {
    const host = hostRef.current;
    const links = linksRef.current;
    if (!host || !links) return undefined;
    const draw = () => {
      const frame = host.getBoundingClientRect();
      const boxOf = (id: string): Box | null => {
        const el = host.querySelector<HTMLElement>(`[data-brick="${id}"]`);
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return { x: r.left - frame.left, y: r.top - frame.top, w: r.width, h: r.height };
      };
      const paths = segments.flatMap(segment => {
        const from = boxOf(segment.from);
        const to = boxOf(segment.to);
        if (!from || !to) return [];
        const path = document.createElementNS(SVG_NS, 'path');
        path.setAttribute('d', connectorPath(from, to));
        if (segment.kind === 'flow') {
          path.setAttribute('class', 'lm-flow is-animated');
          path.setAttribute('stroke', `url(#${FLOW_GRADIENT_ID})`);
        } else {
          path.setAttribute('class', segment.kind === 'out' ? 'lm-out' : 'lm-in');
        }
        return [path];
      });
      links.replaceChildren(...paths);
    };
    draw();
    if (typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(draw);
    observer.observe(host);
    return () => observer.disconnect();
  }, [segments]);

  return (
    <div className={cn('lm-layers', highlight.active && 'is-focus')} ref={hostRef}>
      <svg className="lm-links-layer" aria-hidden="true">
        <defs>
          <linearGradient id={FLOW_GRADIENT_ID} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#4f8dfd" />
            <stop offset="0.55" stopColor="#8b5cf6" />
            <stop offset="1" stopColor="#38d4f5" />
          </linearGradient>
        </defs>
        <g ref={linksRef} />
      </svg>
      {layers.map(layer => (
        <section
          key={layer.id}
          className="lm-layer"
          data-tone={layer.tone}
          aria-labelledby={`lm-layer-${layer.id}`}
        >
          <div className="lm-layer-head">
            <span className="lm-badge-ic">
              <MapIcon name={layer.icon} size={18} />
            </span>
            <div>
              <h3 id={`lm-layer-${layer.id}`}>{layer.name}</h3>
              <p>{layer.summary}</p>
            </div>
          </div>
          <ul className="lm-layer-bricks">
            {bricks
              .filter(brick => brick.family === layer.id)
              .map(brick => {
                const badge = badges?.get(brick.id);
                return (
                  <li key={brick.id}>
                    <button
                      type="button"
                      className={cn(
                        'lm-tbrick',
                        highlight.on.has(brick.id) && 'is-on',
                        highlight.near.has(brick.id) && 'is-near'
                      )}
                      data-tone={brick.tone}
                      data-brick={brick.id}
                      onMouseEnter={() => onHover(brick.id)}
                      onMouseLeave={() => onHover(null)}
                      onFocus={() => onHover(brick.id)}
                      onBlur={() => onHover(null)}
                      onClick={() => onSelect(brick.id)}
                    >
                      <MapIcon name={brick.icon} size={16} />
                      <span>{brick.name}</span>
                      {badge && (
                        <span
                          className={cn(
                            'lm-stepbadge',
                            brick.id === highlight.current && 'is-current'
                          )}
                          aria-hidden="true"
                        >
                          {badge}
                        </span>
                      )}
                    </button>
                  </li>
                );
              })}
          </ul>
        </section>
      ))}
    </div>
  );
}
