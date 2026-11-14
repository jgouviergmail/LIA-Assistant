import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import * as original from 'lucide-react';
import * as icons from '@/lib/icons';
import { ICON_STYLES } from '@/lib/icon-style';
import { IconStyleContext } from '@/lib/icon-style-context';
import {
  colorHue,
  hasDifferentHues,
  parseArtwork,
  reachableColors,
} from '@/lib/icons/__tests__/catalogue-paints';

const COLORED_STYLES = ['fluent', 'flex'] as const;

/** The colors a shape is filled with, through its gradient when it has one. */
function fillColors(svg: Element, shape: Element): string[] {
  const fill = shape.getAttribute('fill') ?? '';
  const id = fill.match(/^url\(#([^)]+)\)$/)?.[1];
  if (!id) return [fill];
  return [...svg.querySelectorAll(`[id="${id}"] stop`)].map(
    stop => stop.getAttribute('stop-color') ?? ''
  );
}

function isRed(color: string): boolean {
  const hue = colorHue(color);
  return hue !== null && (hue >= 345 || hue <= 15);
}

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

  it.each(COLORED_STYLES)(
    'draws the recording dot red inside the ring its caller colors in %s',
    style => {
      const { getByTestId } = render(
        <IconStyleContext.Provider value={style}>
          <icons.Disc data-testid="record" />
        </IconStyleContext.Provider>
      );
      const svg = getByTestId('record');
      const ring = svg.querySelector('circle[cx="12"][cy="12"][r="10"]');
      expect(ring).toHaveAttribute('stroke', 'currentColor');
      expect(ring).toHaveAttribute('fill', 'none');
      const filled = [...svg.querySelectorAll('circle')].filter(
        circle => circle.getAttribute('fill') !== 'none'
      );
      // One dot, and nothing of the former disc's violet face or yellow hub.
      expect(filled).toHaveLength(1);
      expect(filled[0]).toHaveAttribute('cx', '12');
      expect(filled[0]).toHaveAttribute('cy', '12');
      const colors = fillColors(svg, filled[0]);
      expect(colors.length).toBeGreaterThan(0);
      expect(colors.every(isRed)).toBe(true);
    }
  );

  it('keeps the broadcast glyph for the radio set in the line style', () => {
    const { getByTestId } = render(
      <IconStyleContext.Provider value="lucide">
        <icons.RadioSet data-testid="set" />
        <original.Radio data-testid="broadcast" />
      </IconStyleContext.Provider>
    );
    const set = getByTestId('set');
    expect(set).toHaveAttribute('data-icon-style', 'lucide');
    expect(set).toHaveAttribute('data-icon-name', 'RadioSet');
    expect(geometrySignatures(set)).toEqual(geometrySignatures(getByTestId('broadcast')));
  });

  it.each(COLORED_STYLES)('draws the set itself, not a broadcast, in %s', style => {
    const { getByTestId } = render(
      <IconStyleContext.Provider value={style}>
        <icons.RadioSet data-testid="set" />
        <icons.Radio data-testid="broadcast" />
      </IconStyleContext.Provider>
    );
    const set = getByTestId('set');
    expect(set).toHaveAttribute('data-icon-style', style);
    expect(set).toHaveAttribute('data-icon-name', 'RadioSet');
    // A cabinet, and none of the arcs the live and signal marks keep.
    expect(set.querySelector('rect[rx]')).not.toBeNull();
    const drawn = geometrySignatures(set);
    for (const signature of geometrySignatures(getByTestId('broadcast'))) {
      expect(drawn).not.toContain(signature);
    }
    expect(hasDifferentHues(reachableColors(parseArtwork(set.innerHTML)))).toBe(true);
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
