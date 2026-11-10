import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import * as original from 'lucide-react';
import * as icons from '@/lib/icons';
import { ICON_STYLES } from '@/lib/icon-style';
import { IconStyleContext } from '@/lib/icon-style-context';
import {
  hasDifferentHues,
  parseArtwork,
  reachableColors,
} from '@/lib/icons/__tests__/catalogue-paints';

// A related illustration is not an equivalent action. The colored complement
// retains its meaningful source geometry, independently of the manifest.
const EXACT_COMPLEMENTS = [
  ['fluent', 'ThumbsUp'],
  ['fluent', 'ThumbsDown'],
  ['fluent', 'Bookmark'],
  ['fluent', 'Eye'],
  ['fluent', 'Map'],
  ['fluent', 'Brain'],
  ['fluent', 'Cpu'],
  ['fluent', 'KeyRound'],
  ['fluent', 'Reply'],
  ['fluent', 'ReplyAll'],
  ['fluent', 'MailOpen'],
  ['fluent', 'Phone'],
  ['fluent', 'PhoneCall'],
  ['fluent', 'Sun'],
  ['fluent', 'Sparkles'],
  ['fluent', 'Palette'],
  ['fluent', 'Server'],
  ['fluent', 'Stethoscope'],
  ['fluent', 'Dumbbell'],
  ['fluent', 'ClipboardPaste'],
  ['fluent', 'CircleDollarSign'],
  ['flex', 'Eye'],
  ['flex', 'Bookmark'],
  ['flex', 'Radio'],
  ['flex', 'Disc'],
  ['flex', 'Eclipse'],
  ['flex', 'CircleDollarSign'],
  ['flex', 'List'],
  ['flex', 'ListPlus'],
  ['flex', 'LayoutList'],
  ['flex', 'Hash'],
  ['flex', 'Nfc'],
  ['flex', 'Footprints'],
  ['flex', 'Repeat'],
  ['flex', 'Clock'],
  ['flex', 'CalendarClock'],
  ['flex', 'ListMusic'],
  ['flex', 'Server'],
  ['flex', 'Stethoscope'],
  ['flex', 'ClipboardPaste'],
] as const;

const GEOMETRY_ATTRIBUTES = [
  'd',
  'x',
  'y',
  'width',
  'height',
  'rx',
  'ry',
  'cx',
  'cy',
  'r',
  'points',
  'x1',
  'x2',
  'y1',
  'y2',
];

function geometrySignatures(element: HTMLElement | SVGElement): Set<string> {
  return new Set(
    [...element.querySelectorAll('path,circle,rect,ellipse,line,polyline,polygon')]
      .filter(shape => !shape.closest('defs'))
      .map(shape =>
        JSON.stringify([
          shape.tagName,
          GEOMETRY_ATTRIBUTES.flatMap(name =>
            shape.hasAttribute(name) ? [[name, shape.getAttribute(name)]] : []
          ),
        ])
      )
  );
}

describe('semantically exact multicolor complements', () => {
  it.each(EXACT_COMPLEMENTS)(
    '%s preserves the meaningful %s geometry in colored artwork',
    (style, name) => {
      const SharedIcon = icons[name];
      const OriginalIcon = original[name];
      const { getByTestId } = render(
        <IconStyleContext.Provider value={style}>
          <SharedIcon data-testid="shared" />
          <OriginalIcon data-testid="original" />
        </IconStyleContext.Provider>
      );
      const shared = getByTestId('shared');
      expect(shared).toHaveAttribute('data-icon-style', style);
      const paintedShapes = geometrySignatures(shared);
      for (const signature of geometrySignatures(getByTestId('original'))) {
        expect(paintedShapes).toContain(signature);
      }
      expect(hasDifferentHues(reachableColors(parseArtwork(shared.innerHTML)))).toBe(true);
    }
  );

  it.each(ICON_STYLES)('keeps dark and OLED destinations distinct in %s', style => {
    const { getByTestId } = render(
      <IconStyleContext.Provider value={style}>
        <icons.Moon data-testid="dark" />
        <icons.Eclipse data-testid="oled" />
      </IconStyleContext.Provider>
    );
    expect(getByTestId('dark').innerHTML).not.toBe(getByTestId('oled').innerHTML);
  });

  it.each(['fluent', 'flex'] as const)(
    'draws toggle handles above their enclosing surface in %s',
    style => {
      const { getByTestId } = render(
        <IconStyleContext.Provider value={style}>
          <icons.ToggleLeft data-testid="off" />
          <icons.ToggleRight data-testid="on" />
        </IconStyleContext.Provider>
      );
      for (const [name, center] of [
        ['off', '9'],
        ['on', '15'],
      ]) {
        const svg = getByTestId(name);
        const surface = svg.querySelector('rect[stroke="none"]');
        const handle = svg.querySelector(`circle[cx="${center}"][stroke="none"]`);
        expect(surface).not.toBeNull();
        expect(handle).not.toBeNull();
        expect(surface!.compareDocumentPosition(handle!)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
      }
    }
  );
});
