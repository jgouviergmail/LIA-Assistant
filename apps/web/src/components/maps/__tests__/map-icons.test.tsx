/**
 * Every icon the map data names resolves to a Lucide component: an unknown name
 * would otherwise render nothing, in silence.
 */

import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import functional from '@/data/maps/functional.json';
import history from '@/data/maps/history.json';
import technical from '@/data/maps/technical.json';

import { MAP_ICONS, MapIcon } from '../map-icons';

describe('map icons', () => {
  it('knows every icon the data names, and nothing it does not', () => {
    const named = new Set<string>([
      ...functional.groups.map(x => x.icon),
      ...functional.bricks.map(x => x.icon),
      ...functional.flows.map(x => x.icon),
      ...technical.layers.map(x => x.icon),
      ...technical.bricks.map(x => x.icon),
      ...technical.flows.map(x => x.icon),
      ...history.themes.map(x => x.icon),
    ]);
    expect([...named].filter(name => !MAP_ICONS[name])).toEqual([]);
    expect(Object.keys(MAP_ICONS).filter(name => !named.has(name))).toEqual([]);
  });

  it('draws a known icon, hidden from assistive technology, and nothing for an unknown one', () => {
    const { container, rerender } = render(<MapIcon name="brain" size={20} />);
    const svg = container.querySelector('svg');
    expect(svg).toHaveAttribute('aria-hidden', 'true');
    expect(svg).toHaveAttribute('width', '20');
    rerender(<MapIcon name="no-such-icon" />);
    expect(container.querySelector('svg')).toBeNull();
  });
});
