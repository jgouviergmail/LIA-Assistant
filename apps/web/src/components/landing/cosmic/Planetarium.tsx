'use client';

/**
 * The hero planetarium: LIA (the chat mockup) at the center, her major
 * features orbiting as planets of different sizes on three tilted ellipses —
 * the product's "she orchestrates your emails, calendar, home" made literal.
 *
 * Decorative for AT (`aria-hidden`): the hero copy already names the domains
 * accessibly. Motion is pure CSS (orbit spin + counter-rotation keeps labels
 * upright; the tilted plane is compensated in `.cosmos-pl-body`), so the
 * global reduced-motion kill-switch freezes it without JS.
 */

import type { CSSProperties } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';

type Orbit = 'out' | 'mid' | 'in';

export interface PlanetSpec {
  orbit: Orbit;
  /** Negative animation-delay phasing the planet along its shared ellipse. */
  phaseS: number;
  sizePx: number;
  color: string;
  labelKey: string;
}

/** 8 major features on 3 ellipses (2–3 per ellipse), sizes 10–26 px. */
export const PLANETS: readonly PlanetSpec[] = [
  { orbit: 'out', phaseS: 0, sizePx: 26, color: '#4f8dfd', labelKey: 'landing.cosmos.planet.maison' },
  { orbit: 'out', phaseS: -28, sizePx: 18, color: '#38d4f5', labelKey: 'landing.cosmos.planet.emails' },
  { orbit: 'out', phaseS: -56, sizePx: 12, color: '#8b5cf6', labelKey: 'landing.cosmos.planet.agenda' },
  { orbit: 'mid', phaseS: -8, sizePx: 22, color: '#8b5cf6', labelKey: 'landing.cosmos.planet.memoire' },
  { orbit: 'mid', phaseS: -27, sizePx: 15, color: '#4f8dfd', labelKey: 'landing.cosmos.planet.voix' },
  { orbit: 'mid', phaseS: -46, sizePx: 11, color: '#38d4f5', labelKey: 'landing.cosmos.planet.veille' },
  { orbit: 'in', phaseS: -5, sizePx: 16, color: '#38d4f5', labelKey: 'landing.cosmos.planet.skills' },
  { orbit: 'in', phaseS: -24, sizePx: 10, color: '#4f8dfd', labelKey: 'landing.cosmos.planet.briefing' },
] as const;

const ORBIT_TRAILS: Record<Orbit, string> = {
  out: 'var(--cosmos-glow-blue)',
  mid: 'var(--cosmos-glow-violet)',
  in: 'var(--cosmos-glow-cyan)',
};

export function Planetarium() {
  const { t } = useTranslation();
  const firstOfOrbit = new Set<Orbit>();

  return (
    <div aria-hidden="true" data-testid="planetarium" className="pointer-events-none">
      <div className="cosmos-halo" />
      <div className="cosmos-orbits">
        {PLANETS.map(planet => {
          const ringed = !firstOfOrbit.has(planet.orbit);
          firstOfOrbit.add(planet.orbit);
          return (
            <div
              key={planet.labelKey}
              className={cn('cosmos-orbit', `o-${planet.orbit}`, ringed && 'ringed')}
              style={
                {
                  '--ph': `${planet.phaseS}s`,
                  '--trail': ORBIT_TRAILS[planet.orbit],
                } as CSSProperties
              }
            >
              <span className="cosmos-sat" style={{ '--ph': `${planet.phaseS}s` } as CSSProperties}>
                <span className="cosmos-pl-body">
                  <i
                    className="cosmos-pl"
                    style={{ '--s': `${planet.sizePx}px`, '--c': planet.color } as CSSProperties}
                  />
                  <em>{t(planet.labelKey)}</em>
                </span>
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
