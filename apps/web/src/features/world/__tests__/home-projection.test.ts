import { describe, expect, it } from 'vitest';
import { WORLD } from '../definition';
import { compileNavigation } from '../navigation';
import { skinHomeProps } from '../home-projection';
import { previewHome } from '../home-preview';
import type { HomeView } from '../home-protocol';

describe('private home colours', () => {
  it('previews an explicit palette or the account theme without a source-derived decoration', () => {
    const view: HomeView = {
      owner_id: '4a34f89f-f180-4ec6-9f8f-cdd15eec7e65',
      needs_reset: false,
      preferences: { version: 1, revision: 1, palette: 'auto' },
      decoration: { palette: 'teal', automatic_palette: 'sage' },
    };
    expect(previewHome(view, { palette: 'auto' })).toEqual({ palette: 'sage' });
    expect(previewHome(view, { palette: 'amber' })).toEqual({ palette: 'amber' });
  });
  it('changes only owner artwork and leaves all collision footprints unchanged', () => {
    const props = skinHomeProps(WORLD, { palette: 'sage' });
    expect(compileNavigation({ ...WORLD, props }).blocked).toEqual(
      compileNavigation(WORLD).blocked
    );
    const home = WORLD.zones.find(zone => zone.id === 'home');
    if (!home) throw new Error('Missing home');
    for (const [index, prop] of props.entries()) {
      if (
        prop.x >= home.x &&
        prop.x < home.x + home.width &&
        prop.y >= home.y &&
        prop.y < home.y + home.height
      )
        expect(prop.tone).toBe('sage');
      else expect(prop).toBe(WORLD.props[index]);
    }
    expect(skinHomeProps(WORLD, null)).toBe(WORLD.props);
  });
});
