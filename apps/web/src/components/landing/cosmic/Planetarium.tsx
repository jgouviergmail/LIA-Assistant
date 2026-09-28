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
import styles from './Planetarium.module.css';

type Orbit = 'out' | 'mid' | 'in';
type PlanetSurface = 'ocean' | 'banded' | 'rocky' | 'ice';

export interface PlanetSpec {
  orbit: Orbit;
  /** Negative animation-delay phasing the planet along its shared ellipse. */
  phaseS: number;
  sizePx: number;
  color: string;
  highlight: string;
  surface: PlanetSurface;
  hasRing?: boolean;
  labelKey: string;
}

/** 8 major features on 3 ellipses, with distinct mineral, ocean and gas surfaces. */
export const PLANETS: readonly PlanetSpec[] = [
  {
    orbit: 'out',
    phaseS: 0,
    sizePx: 28,
    color: '#397edc',
    highlight: '#90e5ba',
    surface: 'ocean',
    labelKey: 'landing.cosmos.planet.maison',
  },
  {
    orbit: 'out',
    phaseS: -28,
    sizePx: 20,
    color: '#db9d55',
    highlight: '#ffe7bb',
    surface: 'banded',
    hasRing: true,
    labelKey: 'landing.cosmos.planet.emails',
  },
  {
    orbit: 'out',
    phaseS: -56,
    sizePx: 13,
    color: '#d96b63',
    highlight: '#ffc4a4',
    surface: 'rocky',
    labelKey: 'landing.cosmos.planet.agenda',
  },
  {
    orbit: 'mid',
    phaseS: -8,
    sizePx: 24,
    color: '#a385e9',
    highlight: '#e1d4ff',
    surface: 'ice',
    hasRing: true,
    labelKey: 'landing.cosmos.planet.memoire',
  },
  {
    orbit: 'mid',
    phaseS: -27,
    sizePx: 17,
    color: '#db77aa',
    highlight: '#ffdae8',
    surface: 'banded',
    labelKey: 'landing.cosmos.planet.voix',
  },
  {
    orbit: 'mid',
    phaseS: -46,
    sizePx: 11,
    color: '#39ae8c',
    highlight: '#b3ead0',
    surface: 'ocean',
    labelKey: 'landing.cosmos.planet.veille',
  },
  {
    orbit: 'in',
    phaseS: -5,
    sizePx: 16,
    color: '#40bcda',
    highlight: '#d5f7ff',
    surface: 'ice',
    labelKey: 'landing.cosmos.planet.skills',
  },
  {
    orbit: 'in',
    phaseS: -24,
    sizePx: 10,
    color: '#e6a072',
    highlight: '#ffe4c5',
    surface: 'rocky',
    labelKey: 'landing.cosmos.planet.briefing',
  },
] as const;

const SPHERE_LIGHT =
  'radial-gradient(circle at 30% 25%, #ffffffa6, transparent 38%, #000000b3 94%)';
const SURFACES: Record<PlanetSurface, string> = {
  ocean: `${SPHERE_LIGHT}, radial-gradient(ellipse at 32% 58%, var(--highlight) 0 19%, transparent 24%), radial-gradient(ellipse at 72% 30%, var(--highlight) 0 13%, transparent 19%), linear-gradient(var(--c), var(--c))`,
  banded: `${SPHERE_LIGHT}, repeating-linear-gradient(168deg, var(--c) 0 12%, var(--highlight) 15% 20%, var(--c) 25% 32%)`,
  rocky: `${SPHERE_LIGHT}, radial-gradient(circle at 65% 60%, #0004 0 12%, transparent 16%), radial-gradient(circle at 32% 38%, var(--highlight) 0 12%, transparent 18%), linear-gradient(var(--c), var(--c))`,
  ice: `${SPHERE_LIGHT}, linear-gradient(125deg, var(--highlight) 5%, var(--c) 35%, var(--highlight) 43%, var(--c) 56%, var(--highlight) 68%, var(--c) 78%)`,
};

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
                  <span
                    className={styles.planetFrame}
                    style={
                      {
                        '--s': `${planet.sizePx}px`,
                        '--c': planet.color,
                        '--highlight': planet.highlight,
                      } as CSSProperties
                    }
                  >
                    <i
                      className="cosmos-pl"
                      style={{ backgroundImage: SURFACES[planet.surface] }}
                    />
                    {planet.hasRing && <span className={styles.planetRing} />}
                  </span>
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
