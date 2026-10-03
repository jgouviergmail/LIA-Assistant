/**
 * Contrast guard for the public cosmos pages (WCAG 1.4.3 AA, 4.5:1).
 *
 * `design-contrast.guard.test.ts` reads the application's OKLCH tokens; the
 * cosmos scope paints its own — hex inks over a sky, a nebula's glow, the
 * footer's glass and the landing's attention canvas — and none of them was
 * checked. Measured on 2026-10-03 after the lot that revealed the nebula and
 * deepened the light sky: the light muted ink fell to 4.4:1 on the footer's
 * glass and 3.5:1 under the canvas's strokes, while every guard stayed green.
 *
 * The backgrounds are composed here the way the browser stacks them, from the
 * values `globals.css` declares (the sky, the glow at its peak, the glass's
 * veil) and the canvas palette `lib/landing/attention-background.ts` draws
 * with. Both inks — body and muted — must hold 4.5:1 on every one, in both
 * themes.
 */

import { describe, expect, it } from 'vitest';

import { type Rgb, blend, contrast, css } from './contrast-math';

const AA = 4.5;

/** A declared colour and its alpha (1 for an opaque hex). */
interface Paint {
  rgb: Rgb;
  alpha: number;
}

function parsePaint(value: string): Paint {
  const hex = value.match(/^#([0-9a-f]{6})$/i);
  if (hex) {
    const n = Number.parseInt(hex[1], 16);
    return { rgb: [(n >> 16) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255], alpha: 1 };
  }
  const rgba = value.match(/^rgba\(\s*(\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\s*\)$/);
  if (rgba) {
    return {
      rgb: [Number(rgba[1]) / 255, Number(rgba[2]) / 255, Number(rgba[3]) / 255],
      alpha: Number(rgba[4]),
    };
  }
  throw new Error(`unparsed colour: ${value}`);
}

/**
 * Every `--cosmos-*` declaration of the blocks whose selector is exactly
 * `selector`, in source order (a later block wins, like the cascade).
 */
function tokens(selector: string): Record<string, string> {
  const found: Record<string, string> = {};
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const blocks = css.matchAll(new RegExp(`(?:^|\\n)${escaped}\\s*\\{([^}]*)\\}`, 'g'));
  for (const block of blocks) {
    for (const decl of block[1].matchAll(/(--cosmos-[\w-]+)\s*:\s*([^;]+);/g)) {
      found[decl[1]] = decl[2].trim();
    }
  }
  return found;
}

const DARK = tokens('.cosmos');
const LIGHT = { ...DARK, ...tokens('html:not(.dark) .cosmos') };

/**
 * The canvas's densest lasting mark behind copy: the query's nearest link,
 * violet at 0.34 × the latent intensity (0.5), × 1.25 in the dark theme — the
 * values `lib/landing/attention-background.ts` draws with, at rest. The beat's
 * lift (only while the visitor plays the video with its sound) is a passing
 * pulse, not a ground, and is not modelled.
 */
const CANVAS_VIOLET: Record<'light' | 'dark', Rgb> = {
  light: [124 / 255, 92 / 255, 246 / 255],
  dark: [184 / 255, 164 / 255, 255 / 255],
};
const CANVAS_LINK_ALPHA: Record<'light' | 'dark', number> = {
  light: 0.34 * 0.5,
  dark: 0.34 * 0.5 * 1.25,
};

/** A token's value, following `var(--cosmos-…)` references within the scope. */
function resolve(t: Record<string, string>, name: string): string {
  const value = t[name];
  const ref = value?.match(/^var\((--cosmos-[\w-]+)\)$/);
  return ref ? resolve(t, ref[1]) : value;
}

function grounds(theme: 'light' | 'dark'): Record<string, Rgb> {
  const t = theme === 'light' ? LIGHT : DARK;
  const ground = parsePaint(resolve(t, '--cosmos-bg')).rgb;
  const sky = parsePaint(resolve(t, '--cosmos-sky')).rgb;
  const glow = parsePaint(resolve(t, '--cosmos-glow-violet'));
  const veil = parsePaint(resolve(t, '--cosmos-footer-veil'));
  const glowing = blend(glow.rgb, sky, glow.alpha);
  return {
    ground,
    sky,
    'nebula glow at its peak': glowing,
    'footer glass over the glow': blend(veil.rgb, glowing, veil.alpha),
    'canvas link over the glow': blend(CANVAS_VIOLET[theme], glowing, CANVAS_LINK_ALPHA[theme]),
  };
}

describe('cosmos contrast', () => {
  it('reads every token it composes', () => {
    for (const theme of [LIGHT, DARK]) {
      for (const name of [
        '--cosmos-bg',
        '--cosmos-ink',
        '--cosmos-mut',
        '--cosmos-glow-violet',
        '--cosmos-footer-veil',
      ]) {
        expect(theme[name], name).toBeDefined();
      }
    }
    // The light sky is a declared shade, deeper than the ground.
    expect(LIGHT['--cosmos-sky']).toMatch(/^#/);
  });

  for (const theme of ['light', 'dark'] as const) {
    for (const ink of ['--cosmos-ink', '--cosmos-mut'] as const) {
      it(`${theme}: ${ink} holds AA on every ground it is read over`, () => {
        const fg = parsePaint(resolve(theme === 'light' ? LIGHT : DARK, ink)).rgb;
        const failing = Object.entries(grounds(theme))
          .map(([name, bg]) => [name, contrast(fg, bg)] as const)
          .filter(([, ratio]) => ratio < AA)
          .map(([name, ratio]) => `${name}: ${ratio.toFixed(2)}:1`);
        expect(failing).toEqual([]);
      });
    }
  }
});
