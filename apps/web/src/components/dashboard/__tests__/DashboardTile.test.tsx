/**
 * One tile material for the whole dashboard: a SOLID card ground (the page
 * ground is the cosmos, which a translucent tile would let through), the
 * theme's wash and orb painted under the content, never over it.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { DASHBOARD_TILE_FRAME, DashboardTile, TILE_ICON_BADGE } from '../DashboardTile';

describe('DashboardTile', () => {
  it('paints a solid ground, whatever the theme', () => {
    expect(DASHBOARD_TILE_FRAME.split(' ')).toContain('bg-card');
    expect(DASHBOARD_TILE_FRAME).not.toMatch(/bg-card\/\d+|backdrop-blur/);
  });

  it('draws the content above its decorative layers', () => {
    render(
      <DashboardTile data-testid="tile" contentClassName="p-4">
        <p>figure</p>
      </DashboardTile>
    );
    const tile = screen.getByTestId('tile');
    const layers = Array.from(tile.children);
    // The wash and the orb first, hidden from assistive technology…
    expect(layers.slice(0, 2).every(el => el.getAttribute('aria-hidden') === 'true')).toBe(true);
    // …then the content, positioned so it paints over them.
    const content = layers[2];
    expect(content).toHaveClass('relative', 'p-4');
    expect(content).toHaveTextContent('figure');
  });

  it('tints its icon badge with the theme primary', () => {
    expect(TILE_ICON_BADGE.split(' ')).toEqual(
      expect.arrayContaining(['bg-primary/10', 'text-primary', 'ring-primary/20'])
    );
  });
});
