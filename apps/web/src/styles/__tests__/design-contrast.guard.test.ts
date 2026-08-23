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

import {
  type Palette,
  type Rgb,
  allPalettes,
  blend,
  contrast,
  css as cssSource,
  oklchToSrgb,
  oledPalettes,
} from './contrast-math';

const palettes = { ...allPalettes(), ...oledPalettes() };

/**
 * Tailwind's cyan ramp, copied verbatim from `tailwindcss/theme.css`.
 *
 * The skill badge is the product's one remaining FIXED-palette chrome element:
 * cyan is the skill signal, in the chat and in the landing mockup alike, and it
 * deliberately does not follow the user's accent. `badge.tsx` records why the
 * other fixed variants were removed — they "ignore the five colour themes and
 * sit outside the contrast guard, which reads `--color-*` pairs only". This
 * block closes that hole for the one variant that legitimately stays fixed.
 */
const CYAN: Record<number, Rgb> = {
  400: oklchToSrgb(0.789, 0.154, 211.53),
  500: oklchToSrgb(0.715, 0.143, 215.221),
  600: oklchToSrgb(0.609, 0.126, 221.723),
  800: oklchToSrgb(0.45, 0.085, 224.283),
};

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
  // Dimmed text (`text-<token>/NN`) is NOT checked here: this matrix describes
  // pairs the UI actually produces, and no opacity below 100 survives in the
  // source. The invariant that keeps it that way — with the safe floor derived
  // from these same palettes rather than hardcoded — lives in
  // `text-opacity.guard.test.ts`.
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

  /**
   * The skill badge (`SkillBadge`): cyan text on a `cyan-500/20` wash over the
   * assistant bubble, whose ground is the `card` token of the active palette.
   * Light and dark need DIFFERENT ramp steps — a single value cannot clear AA
   * on both a near-white and a near-black card, which is exactly how the
   * original `text-cyan-400` shipped at 1.39:1 in light mode.
   */
  describe('skill badge (fixed cyan palette, all themes × modes)', () => {
    for (const [name, palette] of Object.entries(palettes)) {
      const isDark = !name.endsWith('-light');
      const step = isDark ? 400 : 800;
      it(`${name}: cyan-${step} on cyan-500/20 over card meets AA`, () => {
        const ground = blend(CYAN[500], palette['card'], 0.2);
        const ratio = contrast(CYAN[step], ground);
        expect(ratio, `cyan-${step} on the badge wash in ${name}: ${ratio.toFixed(2)}`).toBeGreaterThanOrEqual(AA);
      });
    }
  });

  /**
   * The sheen is a contrast parameter, not decoration: `.badge-glimmer` sweeps
   * a cyan band across a badge whose own text is cyan, so the WORST moment for
   * the reader is the band's peak — not the badge at rest. The alpha is read
   * out of `globals.css` rather than restated here, so loosening the CSS fails
   * this test instead of quietly dimming the label.
   */
  it('skill badge stays AA at the peak of the glimmer sheen', () => {
    const literal = /\.badge-glimmer\s*\{[^}]*rgb\(34 211 238 \/ ([\d.]+)\)/.exec(cssSource);
    expect(literal, '.badge-glimmer cyan sheen literal not found in globals.css').not.toBeNull();
    const alpha = Number(literal![1]);
    // rgb(34 211 238) — the sheen's own colour, as written in the stylesheet.
    const sheen: Rgb = [34 / 255, 211 / 255, 238 / 255];

    const failures: string[] = [];
    for (const [name, palette] of Object.entries(palettes)) {
      const wash = blend(CYAN[500], palette['card'], 0.2);
      const peak = blend(sheen, wash, alpha);
      const step = name.endsWith('-light') ? 800 : 400;
      const ratio = contrast(CYAN[step], peak);
      if (ratio < AA) failures.push(`${name}: ${ratio.toFixed(2)} < ${AA}`);
    }
    expect(failures, `\nglimmer peak contrast failures (alpha ${alpha}):\n  ${failures.join('\n  ')}\n`).toEqual(
      []
    );
  });

  /**
   * Reduced motion must not merely stop the sheen: `animation: none` leaves the
   * gradient at its INITIAL position, which parks the bright band on the label.
   * The stop must also move it to the animation's end position.
   */
  it('parks the glimmer off the badge under prefers-reduced-motion', () => {
    const endPosition = /@keyframes badge-glimmer[\s\S]*?100%\s*\{\s*background-position:\s*([^;]+);/.exec(
      cssSource
    );
    expect(endPosition, 'badge-glimmer 100% keyframe not found').not.toBeNull();

    // Scoping a regex "inside the reduced-motion media query" is unreliable —
    // globals.css has several such blocks, and a lazy match walks into the
    // ordinary rule instead. Identify the stop rule by what it DOES: the
    // `.badge-glimmer` block that switches the animation off.
    const stopRule = [...cssSource.matchAll(/\.badge-glimmer\s*\{([^}]*)\}/g)]
      .map(m => m[1].replace(/\s+/g, ' '))
      .find(body => /animation:\s*none/.test(body));

    expect(stopRule, '.badge-glimmer has no rule that stops its animation').toBeDefined();
    expect(stopRule).toContain(`background-position: ${endPosition![1].trim()}`);
  });

  /**
   * Selected text: `foreground` over the accent-tinted selection ground.
   *
   * The alpha is read out of `globals.css` rather than restated, so darkening
   * the highlight fails here instead of quietly making selected text harder to
   * read than unselected text.
   */
  it('selected text stays AA on the accent-tinted highlight', () => {
    const literal =
      /::selection\s*\{[^}]*color-mix\(in oklch, var\(--color-primary\) (\d+)%/.exec(cssSource);
    expect(literal, '::selection primary mix not found in globals.css').not.toBeNull();
    const alpha = Number(literal![1]) / 100;

    const failures: string[] = [];
    for (const [name, palette] of Object.entries(palettes)) {
      const ground = blend(palette['primary'], palette['background'], alpha);
      const ratio = contrast(palette['foreground'], ground);
      if (ratio < AA) failures.push(`${name}: ${ratio.toFixed(2)} < ${AA}`);
    }
    expect(
      failures,
      `\nselection contrast failures (primary/${literal![1]}):\n  ${failures.join('\n  ')}\n`
    ).toEqual([]);
  });

  it('parses all 15 palettes with the full token set', () => {
    // 5 accents x {light, dark, oled}. OLED palettes are merged onto their dark
    // base, so they must expose the FULL token set even though the CSS block
    // only overrides six neutrals.
    expect(Object.keys(palettes)).toHaveLength(15);
    for (const [name, palette] of Object.entries(palettes)) {
      for (const t of ['background', 'foreground', 'primary', 'muted-foreground', 'ring']) {
        expect(palette[t], `token --color-${t} missing in ${name}`).toBeDefined();
      }
    }
  });
});
