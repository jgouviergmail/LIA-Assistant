import { readFileSync } from 'node:fs';
import path from 'node:path';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { WORLD } from '@/features/world/definition';
import { WORLD_PLACE_IDS, WorldPlaces } from '../WorldPlaces';

const LANGUAGES = ['en', 'fr', 'de', 'es', 'it', 'zh'] as const;

describe('WorldPlaces', () => {
  it('presents every authored place exactly once, without an invented room', () => {
    expect([...WORLD_PLACE_IDS].sort()).toEqual(WORLD.zones.map(zone => zone.id).sort());
    expect(new Set(WORLD_PLACE_IDS).size).toBe(WORLD_PLACE_IDS.length);
  });

  it.each(LANGUAGES)('uses native place names and complete local descriptions in %s', language => {
    const copy = JSON.parse(
      readFileSync(path.join(process.cwd(), 'locales', language, 'translation.json'), 'utf8')
    );
    const t = (key: string): string =>
      key.split('.').reduce((value, part) => value?.[part], copy) ?? key;
    const { container } = render(<WorldPlaces t={t} />);
    expect(screen.getByRole('heading', { level: 3 })).toHaveTextContent(
      copy.landing.world_places.title
    );
    expect(container.querySelectorAll('dt')).toHaveLength(WORLD.zones.length);
    expect(Object.keys(copy.landing.world_places.places).sort()).toEqual(
      [...WORLD_PLACE_IDS].sort()
    );
    for (const id of WORLD_PLACE_IDS) {
      expect(screen.getByText(copy.world.zones[id])).toBeVisible();
      expect(screen.getByText(copy.landing.world_places.places[id])).toBeVisible();
    }
    expect(container.textContent).not.toContain('landing.');
    expect(container.textContent).not.toContain('undefined');
  });
});
