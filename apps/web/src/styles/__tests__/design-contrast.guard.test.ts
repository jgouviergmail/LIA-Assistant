/**
 * Design-system contrast guard (audit AC-002).
 *
 * Parses the OKLCH theme tokens straight out of `globals.css` and verifies the
 * WCAG 2.x AA contrast of every real token pairing the UI produces — for the
 * 5 themes × light/dark — including the states axe cannot see in a static
 * scan: hover (`bg-primary/90` over card), soft tints (`bg-primary/15 text-primary`
 * nav items, `bg-destructive/10..20 text-destructive` alerts/toasts) and the
 * focus ring. Any palette edit that drops a pair below AA fails here, in unit
 * tests, before a browser scan ever runs.
 *
 * The pair matrix mirrors actual component usage:
 *  - button.tsx variants (solid + `/90` hover, soft `/15` tint + border),
 *  - alert.tsx / toaster.tsx (`text-success|destructive` on `/10../20` tints),
 *  - dashboard nav (`bg-primary/15 text-primary`),
 *  - body/muted text on background, card, muted, secondary, accent.
 *
 * Thresholds: 4.5:1 for normal text (WCAG 1.4.3 AA), 3:1 for the non-text
 * focus ring against the page background (WCAG 1.4.11).
 */

import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

type Rgb = [number, number, number];
type Palette = Record<string, Rgb>;

// --- OKLCH -> sRGB -> WCAG relative luminance --------------------------------

function oklchToSrgb(L: number, C: number, H: number): Rgb {
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

function luminance([r, g, b]: Rgb): number {
  const lin = (c: number) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

function contrast(fg: Rgb, bg: Rgb): number {
  const [l1, l2] = [luminance(fg), luminance(bg)].sort((a, b) => b - a);
  return (l1 + 0.05) / (l2 + 0.05);
}

/** Alpha-composite `top` at `alpha` over an opaque `bottom` (sRGB space, like the browser). */
function blend(top: Rgb, bottom: Rgb, alpha: number): Rgb {
  return [0, 1, 2].map(i => alpha * top[i] + (1 - alpha) * bottom[i]) as Rgb;
}

// --- globals.css token extraction --------------------------------------------

const css = readFileSync(resolve(__dirname, '../globals.css'), 'utf-8');

/** Extract `--color-*: oklch(...)` declarations from one selector block. */
function extractBlock(startIndex: number): Record<string, Rgb> {
  const open = css.indexOf('{', startIndex);
  let depth = 1;
  let i = open + 1;
  while (depth > 0 && i < css.length) {
    if (css[i] === '{') depth++;
    if (css[i] === '}') depth--;
    i++;
  }
  const body = css.slice(open + 1, i - 1);
  const tokens: Record<string, Rgb> = {};
  const re = /--color-([a-z-]+):\s*oklch\(([\d.]+)%\s+([\d.]+)\s+([\d.]+)\)/g;
  for (const m of body.matchAll(re)) {
    tokens[m[1]] = oklchToSrgb(Number(m[2]) / 100, Number(m[3]), Number(m[4]));
  }
  return tokens;
}

function paletteFor(selector: string | RegExp): Palette {
  const idx = typeof selector === 'string' ? css.indexOf(selector) : css.search(selector);
  expect(idx, `selector ${selector} not found in globals.css`).toBeGreaterThan(-1);
  return extractBlock(idx);
}

const THEMES = ['ocean', 'forest', 'sunset', 'slate'] as const;

const palettes: Record<string, Palette> = {
  'default-light': paletteFor('@theme {'),
  'default-dark': paletteFor(/\.dark \{/),
};
for (const t of THEMES) {
  palettes[`${t}-light`] = paletteFor(`[data-theme='${t}'] {`);
  palettes[`${t}-dark`] = paletteFor(`[data-theme='${t}'].dark {`);
}

// --- The pair matrix ----------------------------------------------------------

interface Check {
  label: string;
  fg: (p: Palette) => Rgb;
  bg: (p: Palette) => Rgb;
  min: number;
}

const AA = 4.5;
const NON_TEXT = 3;

const CHECKS: Check[] = [
  // Body text on every neutral surface it sits on.
  {
    label: 'foreground on background',
    fg: p => p['foreground'],
    bg: p => p['background'],
    min: AA,
  },
  { label: 'card-foreground on card', fg: p => p['card-foreground'], bg: p => p['card'], min: AA },
  {
    label: 'popover-foreground on popover',
    fg: p => p['popover-foreground'],
    bg: p => p['popover'],
    min: AA,
  },
  {
    label: 'secondary-foreground on secondary',
    fg: p => p['secondary-foreground'],
    bg: p => p['secondary'],
    min: AA,
  },
  {
    label: 'accent-foreground on accent',
    fg: p => p['accent-foreground'],
    bg: p => p['accent'],
    min: AA,
  },
  // Muted text on every surface it is used on (worst: the muted tint itself).
  {
    label: 'muted-foreground on background',
    fg: p => p['muted-foreground'],
    bg: p => p['background'],
    min: AA,
  },
  {
    label: 'muted-foreground on card',
    fg: p => p['muted-foreground'],
    bg: p => p['card'],
    min: AA,
  },
  {
    label: 'muted-foreground on muted',
    fg: p => p['muted-foreground'],
    bg: p => p['muted'],
    min: AA,
  },
  // Primary as text (links, outline/link buttons, icons-with-text).
  { label: 'primary on background', fg: p => p['primary'], bg: p => p['background'], min: AA },
  { label: 'primary on card', fg: p => p['primary'], bg: p => p['card'], min: AA },
  // Signature nav/soft pattern: primary text on its own 15% tint over background.
  {
    label: 'primary on primary/15 tint',
    fg: p => p['primary'],
    bg: p => blend(p['primary'], p['background'], 0.15),
    min: AA,
  },
  // Solid primary button + its /90 hover over the lightest underlay (card).
  {
    label: 'primary-foreground on primary',
    fg: p => p['primary-foreground'],
    bg: p => p['primary'],
    min: AA,
  },
  {
    label: 'primary-foreground on primary/90 hover',
    fg: p => p['primary-foreground'],
    bg: p => blend(p['primary'], p['card'], 0.9),
    min: AA,
  },
  // Destructive as text (form errors, alerts) + alert/toast self-tints up to /20.
  {
    label: 'destructive on background',
    fg: p => p['destructive'],
    bg: p => p['background'],
    min: AA,
  },
  { label: 'destructive on card', fg: p => p['destructive'], bg: p => p['card'], min: AA },
  {
    label: 'destructive on destructive/20 tint',
    fg: p => p['destructive'],
    bg: p => blend(p['destructive'], p['background'], 0.2),
    min: AA,
  },
  {
    label: 'destructive-foreground on destructive',
    fg: p => p['destructive-foreground'],
    bg: p => p['destructive'],
    min: AA,
  },
  {
    label: 'destructive-foreground on destructive/90 hover',
    fg: p => p['destructive-foreground'],
    bg: p => blend(p['destructive'], p['card'], 0.9),
    min: AA,
  },
  // Success as text (alerts, toasts) + self-tints, and the solid success button.
  { label: 'success on background', fg: p => p['success'], bg: p => p['background'], min: AA },
  {
    label: 'success on success/20 tint',
    fg: p => p['success'],
    bg: p => blend(p['success'], p['background'], 0.2),
    min: AA,
  },
  {
    label: 'success-foreground on success',
    fg: p => p['success-foreground'],
    bg: p => p['success'],
    min: AA,
  },
  {
    label: 'success-foreground on success/90 hover',
    fg: p => p['success-foreground'],
    bg: p => blend(p['success'], p['card'], 0.9),
    min: AA,
  },
  // Warning as text (alerts, badges, soft buttons) + its self-tints, and the
  // solid warning button (warning-foreground text).
  { label: 'warning on background', fg: p => p['warning'], bg: p => p['background'], min: AA },
  {
    label: 'warning on warning/20 tint',
    fg: p => p['warning'],
    bg: p => blend(p['warning'], p['background'], 0.2),
    min: AA,
  },
  {
    label: 'warning-foreground on warning',
    fg: p => p['warning-foreground'],
    bg: p => p['warning'],
    min: AA,
  },
  {
    label: 'warning-foreground on warning/90 hover',
    fg: p => p['warning-foreground'],
    bg: p => blend(p['warning'], p['card'], 0.9),
    min: AA,
  },
  // Ghost button hover: accent-foreground on accent/50 over background.
  {
    label: 'accent-foreground on accent/50 hover',
    fg: p => p['accent-foreground'],
    bg: p => blend(p['accent'], p['background'], 0.5),
    min: AA,
  },
  // Focus ring is a non-text indicator against the page background.
  {
    label: 'ring vs background (non-text)',
    fg: p => p['ring'],
    bg: p => p['background'],
    min: NON_TEXT,
  },
];

// --- Assertions ----------------------------------------------------------------

describe('design-system contrast guard (WCAG AA, all themes × modes)', () => {
  for (const [name, palette] of Object.entries(palettes)) {
    it(`${name}: every token pair meets its WCAG threshold`, () => {
      const failures: string[] = [];
      for (const check of CHECKS) {
        const fg = check.fg(palette);
        const bg = check.bg(palette);
        if (!fg || !bg) {
          failures.push(`${check.label}: token missing in ${name}`);
          continue;
        }
        const ratio = contrast(fg, bg);
        if (ratio < check.min) {
          failures.push(`${check.label}: ${ratio.toFixed(2)} < ${check.min}`);
        }
      }
      expect(failures, `\n${name} contrast failures:\n  ${failures.join('\n  ')}\n`).toEqual([]);
    });
  }

  it('parses all 10 palettes with the full token set', () => {
    expect(Object.keys(palettes)).toHaveLength(10);
    for (const [name, palette] of Object.entries(palettes)) {
      for (const t of ['background', 'foreground', 'primary', 'muted-foreground', 'ring']) {
        expect(palette[t], `token --color-${t} missing in ${name}`).toBeDefined();
      }
    }
  });
});
