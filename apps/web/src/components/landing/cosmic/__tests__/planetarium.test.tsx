/**
 * Planetarium invariants: the owner-validated composition (8 planets, 3
 * shared ellipses with 2–3 planets each, varied sizes) and the i18n contract
 * (every label key exists in the reference locale).
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { PLANETS, Planetarium } from '../Planetarium';

describe('PLANETS composition', () => {
  it('places 8 planets across 3 ellipses, 2–3 per ellipse', () => {
    expect(PLANETS).toHaveLength(8);
    const byOrbit = new Map<string, number>();
    for (const planet of PLANETS) {
      byOrbit.set(planet.orbit, (byOrbit.get(planet.orbit) ?? 0) + 1);
    }
    expect([...byOrbit.keys()].sort()).toEqual(['in', 'mid', 'out']);
    for (const count of byOrbit.values()) {
      expect(count).toBeGreaterThanOrEqual(2);
      expect(count).toBeLessThanOrEqual(3);
    }
  });

  it('varies planet sizes (owner: "planètes de tailles différentes")', () => {
    const sizes = new Set(PLANETS.map(planet => planet.sizePx));
    expect(sizes.size).toBeGreaterThanOrEqual(5);
    expect(Math.min(...sizes)).toBeGreaterThanOrEqual(8);
    expect(Math.max(...sizes)).toBeLessThanOrEqual(30);
  });

  it('phases planets sharing an ellipse differently (no overlap)', () => {
    const byOrbit = new Map<string, number[]>();
    for (const planet of PLANETS) {
      byOrbit.set(planet.orbit, [...(byOrbit.get(planet.orbit) ?? []), planet.phaseS]);
    }
    for (const phases of byOrbit.values()) {
      expect(new Set(phases).size).toBe(phases.length);
    }
  });

  it('labels every planet with an existing en translation key', () => {
    const en = JSON.parse(
      readFileSync(join(process.cwd(), 'locales/en/translation.json'), 'utf8')
    ) as Record<string, unknown>;
    for (const planet of PLANETS) {
      const value = planet.labelKey
        .split('.')
        .reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], en);
      expect(value, `missing en key ${planet.labelKey}`).toBeTypeOf('string');
    }
  });
});

describe('Planetarium', () => {
  it('renders a decorative subtree with all planets and one ring per ellipse', () => {
    render(<Planetarium />);
    const root = screen.getByTestId('planetarium');
    expect(root).toHaveAttribute('aria-hidden', 'true');
    expect(root.querySelectorAll('.cosmos-pl')).toHaveLength(8);
    expect(root.querySelectorAll('.cosmos-orbit.ringed')).toHaveLength(3);
    expect(root.querySelector('.cosmos-halo')).toBeInTheDocument();
  });
});
