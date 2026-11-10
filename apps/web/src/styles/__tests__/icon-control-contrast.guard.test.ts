/** Active and hovered dark controls must preserve their colored icons' useful contours. */
import { describe, expect, it } from 'vitest';

import {
  ACTIVE_ICON_BUTTON_CLASS,
  DARK_ICON_BUTTON_HOVER_CLASS,
} from '@/components/ui/button-variants';
import {
  flex_lia_CircleDollarSign,
  flex_lia_Radio,
  flex_lia_RefreshCw,
} from '@/lib/icons/artwork-flex';
import {
  fluent_arrow_sync,
  fluent_lia_CircleDollarSign,
  fluent_lia_Radio,
} from '@/lib/icons/artwork-fluent';
import type { IconArtwork } from '@/lib/icon-style';
import {
  allPalettes,
  blend,
  contrast,
  css,
  oledPalettes,
  type Palette,
  type Rgb,
} from './contrast-math';

function hex(value: string): Rgb {
  if (!/^#[0-9a-f]{6}$/i.test(value)) throw new Error(`Expected a full sRGB paint: ${value}`);
  const channel = (offset: number) => parseInt(value.slice(offset, offset + 2), 16) / 255;
  return [channel(1), channel(3), channel(5)];
}

/** Read the actual stroke paint, or the native refresh arrow's painted gradient. */
function contours(artwork: IconArtwork): Rgb[] {
  const strokes = [...artwork.body.matchAll(/\bstroke="(#[0-9a-f]{6})"/gi)].map(match =>
    hex(match[1])
  );
  if (strokes.length) return strokes;
  const stops = [...artwork.body.matchAll(/\bstop-color="(#[0-9a-f]{6})"/gi)].map(match =>
    hex(match[1])
  );
  if (stops.length !== 2 || !artwork.body.includes('fill="url(#')) {
    throw new Error('Expected two actual gradient stops on the native refresh arrow');
  }
  // Include intermediate sRGB colors: passing endpoints alone is insufficient.
  return Array.from({ length: 21 }, (_, index) => blend(stops[0], stops[1], index / 20));
}

const homeHex = css.match(
  /html\.dark:not\(\[data-oled\]\) \.dashboard-home\s*\{\s*--color-card:\s*(#[0-9a-f]{6});/i
)?.[1];
if (!homeHex) throw new Error('Missing real Home card surface');
const dark = Object.fromEntries(
  Object.entries(allPalettes()).filter(([name]) => name.endsWith('-dark'))
);
const home: Record<string, Palette> = Object.fromEntries(
  Object.entries(dark).map(([name, palette]) => [
    `home-${name}`,
    { ...palette, card: hex(homeHex) },
  ])
);
const palettes: Record<string, Palette> = { ...dark, ...oledPalettes(), ...home };
const fraction = ACTIVE_ICON_BUTTON_CLASS.match(
  /dark:bg-\[color-mix\(in_srgb,var\(--color-card\)_(\d+)%,black\)\]/
)?.[1];
if (!fraction) throw new Error('Active dark control surface is not the declared card/black mix');
const cardShare = Number(fraction) / 100;
const hoverFraction = DARK_ICON_BUTTON_HOVER_CLASS.match(
  /^dark:hover:bg-\[color-mix\(in_srgb,var\(--color-card\)_(\d+)%,black\)\]$/
)?.[1];
if (!hoverFraction) throw new Error('Dark control hover is not the declared card/black mix');
const hoverCardShare = Number(hoverFraction) / 100;
const artwork = {
  'flex-refresh': flex_lia_RefreshCw,
  'fluent-refresh': fluent_arrow_sync,
  'flex-cost': flex_lia_CircleDollarSign,
  'fluent-cost': fluent_lia_CircleDollarSign,
  'flex-radio': flex_lia_Radio,
  'fluent-radio': fluent_lia_Radio,
};

describe('active colored icon controls', () => {
  for (const [name, palette] of Object.entries(palettes)) {
    it(`${name}: useful contours retain 3:1 against the selected surface`, () => {
      const background = blend(palette.card, [0, 0, 0], cardShare);
      for (const [glyph, source] of Object.entries(artwork)) {
        for (const paint of contours(source))
          expect(contrast(paint, background), glyph).toBeGreaterThanOrEqual(3);
      }
    });

    it(`${name}: inactive refresh retains 3:1 on hover`, () => {
      const background = blend(palette.card, [0, 0, 0], hoverCardShare);
      for (const source of [flex_lia_RefreshCw, fluent_arrow_sync]) {
        for (const paint of contours(source))
          expect(contrast(paint, background)).toBeGreaterThanOrEqual(3);
      }
    });
  }

  it('keeps the dark surface stable on hover and preserves the light recipe', () => {
    const surface = `bg-[color-mix(in_srgb,var(--color-card)_${fraction}%,black)]`;
    expect(ACTIVE_ICON_BUTTON_CLASS.split(' ')).toEqual([
      'border-primary',
      'bg-primary/10',
      'hover:bg-primary/15',
      `dark:${surface}`,
      `dark:hover:${surface}`,
    ]);
  });

  it('detects the prior illuminated surface regression in all three controls', () => {
    // Measured selected-button pixels from the failed dark Home capture.
    const illuminated: Rgb = [11 / 255, 45 / 255, 69 / 255];
    for (const source of [flex_lia_RefreshCw, flex_lia_CircleDollarSign, flex_lia_Radio]) {
      expect(Math.min(...contours(source).map(paint => contrast(paint, illuminated)))).toBeLessThan(
        3
      );
    }
  });

  it('detects the prior inactive refresh hover regression in dark and Home palettes', () => {
    for (const palette of Object.values({ ...dark, ...home })) {
      const oldHover = blend(palette.muted, palette.card, 0.6);
      expect(
        Math.min(...contours(flex_lia_RefreshCw).map(paint => contrast(paint, oldHover)))
      ).toBeLessThan(3);
    }
  });
});
