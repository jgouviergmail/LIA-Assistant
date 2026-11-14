/**
 * No two destinations of the header are drawn alike, in any icon style.
 *
 * On the rail a drawing is all that says where a click leads. Chat and SMS shared
 * ONE drawing in the default style (owner report 2026-11-14): the vendor's
 * `chat_more` has the very geometry of its `chat` — a file name is not evidence of
 * a shape. Each destination's icon is rendered in each style and its drawing
 * compared with the others', paint-server identifiers aside.
 */
import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ICON_STYLES, type IconStyle } from '@/lib/icon-style';
import { IconStyleContext } from '@/lib/icon-style-context';

import { DESTINATION_ICONS } from '../dashboard-nav-icons';

type Segment = keyof typeof DESTINATION_ICONS;

const SEGMENTS = Object.keys(DESTINATION_ICONS) as Segment[];

/** What a destination's icon paints in a style: its geometry and its colours. */
function drawing(segment: Segment, style: IconStyle): string {
  const Icon = DESTINATION_ICONS[segment];
  const { container, unmount } = render(
    <IconStyleContext.Provider value={style}>
      <Icon />
    </IconStyleContext.Provider>
  );
  const svg = container.querySelector('svg');
  if (!svg) throw new Error(`No drawing for the destination « ${segment} »`);
  // A paint server is named after its icon and scoped per instance: the name is not seen.
  const painted = svg.innerHTML.replace(/id="[^"]*"/g, 'id=""').replace(/url\(#[^)]*\)/g, 'url(#)');
  unmount();
  return painted;
}

describe('the header destinations', () => {
  it.each(ICON_STYLES)('are each drawn their own way in the %s style', style => {
    const drawn = SEGMENTS.map(segment => [segment || 'home', drawing(segment, style)] as const);
    const alike = drawn.flatMap(([first, painted], index) =>
      drawn
        .slice(index + 1)
        .filter(([, other]) => other === painted)
        .map(([second]) => `${first} = ${second}`)
    );

    expect(alike).toEqual([]);
  });

  it('draws something for every destination, in every style', () => {
    for (const style of ICON_STYLES)
      for (const segment of SEGMENTS) expect(drawing(segment, style).length).toBeGreaterThan(40);
  });
});
