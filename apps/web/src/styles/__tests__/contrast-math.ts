/**
 * Shared colour math for the design-system contrast guards.
 *
 * Extracted from `design-contrast.guard.test.ts` when a second guard
 * (`text-opacity.guard.test.ts`) needed the same OKLCH → sRGB → WCAG chain.
 * One implementation, so the two guards can never disagree about what a ratio
 * is — a divergence here would be invisible and would make one of them lie.
 *
 * Not a test file (no `.test.` segment) so vitest does not collect it, and it
 * lives under `__tests__/` so it stays out of the coverage perimeter.
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

export type Rgb = [number, number, number];
export type Palette = Record<string, Rgb>;

/** OKLCH → linear sRGB → gamma-encoded sRGB, the browser's own transform. */
export function oklchToSrgb(L: number, C: number, H: number): Rgb {
  const h = (H * Math.PI) / 180;
  const a = C * Math.cos(h);
  const b = C * Math.sin(h);
  const l_ = L + 0.3963377774 * a + 0.2158037573 * b;
  const m_ = L - 0.1055613458 * a - 0.0638541728 * b;
  const s_ = L - 0.0894841775 * a - 1.291485548 * b;
  const l = l_ ** 3;
  const m = m_ ** 3;
  const s = s_ ** 3;
  const r = +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s;
  const g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s;
  const bl = -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s;
  const enc = (x: number) => {
    const v = Math.max(0, Math.min(1, x));
    return v <= 0.0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055;
  };
  return [enc(r), enc(g), enc(bl)];
}

export function luminance([r, g, b]: Rgb): number {
  const lin = (c: number) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

export function contrast(fg: Rgb, bg: Rgb): number {
  const [l1, l2] = [luminance(fg), luminance(bg)].sort((a, b) => b - a);
  return (l1 + 0.05) / (l2 + 0.05);
}

/** Alpha-composite `top` at `alpha` over an opaque `bottom` (sRGB, like the browser). */
export function blend(top: Rgb, bottom: Rgb, alpha: number): Rgb {
  return [0, 1, 2].map(i => alpha * top[i] + (1 - alpha) * bottom[i]) as Rgb;
}

// --- globals.css token extraction --------------------------------------------

export const css = readFileSync(resolve(__dirname, '../globals.css'), 'utf-8');

/** Extract `--color-*: oklch(...)` declarations from the block opening at `startIndex`. */
export function extractBlock(source: string, startIndex: number): Palette {
  const open = source.indexOf('{', startIndex);
  let depth = 1;
  let i = open + 1;
  while (depth > 0 && i < source.length) {
    if (source[i] === '{') depth++;
    if (source[i] === '}') depth--;
    i++;
  }
  const body = source.slice(open + 1, i - 1);
  const tokens: Palette = {};
  const re = /--color-([a-z-]+):\s*oklch\(([\d.]+)%\s+([\d.]+)\s+([\d.]+)\)/g;
  for (const m of body.matchAll(re)) {
    tokens[m[1]] = oklchToSrgb(Number(m[2]) / 100, Number(m[3]), Number(m[4]));
  }
  return tokens;
}

/**
 * Resolve one selector's token block out of `globals.css`.
 *
 * Throws rather than returning an empty palette: a selector that stops matching
 * (renamed, reformatted) must fail loudly, never silently guard nothing.
 */
export function paletteFor(selector: string | RegExp): Palette {
  const idx = typeof selector === 'string' ? css.indexOf(selector) : css.search(selector);
  if (idx < 0) throw new Error(`selector ${selector} not found in globals.css`);
  return extractBlock(css, idx);
}

/** The five accent themes that layer on top of the default palette. */
export const ACCENT_THEMES = ['ocean', 'forest', 'sunset', 'slate'] as const;

/** Every shipped light/dark palette, keyed `<theme>-<mode>`. */
export function allPalettes(): Record<string, Palette> {
  const palettes: Record<string, Palette> = {
    'default-light': paletteFor('@theme {'),
    'default-dark': paletteFor(/\.dark \{/),
  };
  for (const t of ACCENT_THEMES) {
    palettes[`${t}-light`] = paletteFor(`[data-theme='${t}'] {`);
    palettes[`${t}-dark`] = paletteFor(`[data-theme='${t}'].dark {`);
  }
  return palettes;
}

/**
 * The OLED palettes, keyed `<theme>-oled`.
 *
 * OLED is a REFINEMENT of dark, not a mode beside it: one `html.dark[data-oled]`
 * block overrides the six neutral surfaces and nothing else, so each of the five
 * accents keeps its own `primary` / `success` / `warning` / `destructive`, and
 * `border` / `input` stay on the dark values (which read BETTER against absolute
 * black than against the dark ground: 1.66 vs 1.48).
 *
 * Merging the override onto the dark base is not a convenience — it is what the
 * cascade actually computes. Measuring the override block alone would report a
 * dozen "missing tokens" that the browser resolves perfectly well.
 */
export function oledPalettes(): Record<string, Palette> {
  const base = allPalettes();
  const override = paletteFor(/html\.dark\[data-oled\] \{/);
  const out: Record<string, Palette> = {
    'default-oled': { ...base['default-dark'], ...override },
  };
  for (const t of ACCENT_THEMES) {
    out[`${t}-oled`] = { ...base[`${t}-dark`], ...override };
  }
  return out;
}
