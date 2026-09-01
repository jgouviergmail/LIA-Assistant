/**
 * The matter layer — what turns a shape into a thing.
 *
 * Motion is the larger half of "reads as alive", but a flat fill is the single
 * strongest cue that a shape is only a shape. Four cues carry the rest, and
 * each is guarded here because each is exactly the kind of thing a later
 * "simplification" removes without noticing:
 *
 *  - one light source, and a surface falling away from it;
 *  - a rim light on the lit edge, an occlusion on the other;
 *  - TWO catch-lights moving by DIFFERENT amounts (the parallax between them
 *    is what states the thickness of the cornea — equalise them and the eye
 *    goes flat again);
 *  - a highlight that LAGS the eye, because a reflection belongs to the room.
 *
 * All of it is dosed per style: a stroke and an outline have no surface, and
 * lighting them would destroy exactly what they exist for.
 */

import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { createEyeRig } from '@/components/eyes/rig/runtime';
import { EYE_STYLE_IDS, DEFAULT_EYE_STYLE } from '@/components/eyes/eye-styles';

const CSS = readFileSync(join(process.cwd(), 'src/styles/eyes.css'), 'utf8');

/** The declaration block of one style's root rule. */
function styleBlock(id: string): string {
  const start = CSS.indexOf(`[data-style='${id}'] {`);
  expect(start, `no root block for style '${id}'`).toBeGreaterThan(-1);
  return CSS.slice(start, CSS.indexOf('}', start));
}

/** The `--rig-hl-x` multiplier of one catch-light rule. The selector also
 * appears in the shared rule that gives both highlights their common shape,
 * so the search walks on to the block that declares an actual parallax. */
function parallaxFactor(selector: string): number {
  let from = CSS.indexOf(selector);
  while (from > -1) {
    const block = CSS.slice(from, CSS.indexOf('}', from));
    const match = block.match(/translate:\s*calc\(var\(--rig-hl-x, 0\) \* (-?[\d.]+)em\)/);
    if (match) return Number(match[1]);
    from = CSS.indexOf(selector, from + selector.length);
  }
  throw new Error(`no highlight parallax in ${selector}`);
}

describe('volume', () => {
  it('lights the body from one direction instead of filling it flat', () => {
    expect(CSS).toMatch(/background-image:\s*radial-gradient\(/);
    expect(CSS).toMatch(/rgb\(255 255 255 \/ calc\(0\.\d+ \* var\(--matter\)\)\)/);
  });

  it('carries a rim light and a contact occlusion, both INSET', () => {
    const shape = CSS.slice(CSS.indexOf('.lia-eye-shape {'));
    const block = shape.slice(0, shape.indexOf('\n}'));
    expect(block).toContain('inset 0 calc(0.05em * var(--matter))');
    expect(block).toContain('inset 0 calc(-0.07em * var(--matter))');
  });

  it('never uses an OUTER box-shadow anywhere in the sheet', () => {
    // One did, once: an outer glow on the shape streaked a squashed smear
    // across the silhouette on every blink. The halo lives on the unclipped
    // parent as a drop-shadow instead, and shadows on the shape stay inset so
    // the lid clip carries them.
    const outer = [...CSS.matchAll(/box-shadow:\s*([^;]+);/g)]
      .map(match => match[1].trim())
      .filter(value => !value.startsWith('inset'));
    expect(outer).toEqual([]);
  });

  it('is a plain multiplier, so a style switches the whole treatment off', () => {
    const matterUses = CSS.match(/var\(--matter\)/g) ?? [];
    expect(matterUses.length).toBeGreaterThanOrEqual(6);
  });
});

describe('catch-lights', () => {
  it('are two, at two depths', () => {
    const broad = parallaxFactor('.lia-eye-shape::before {');
    const sharp = parallaxFactor('.lia-eye-shape::after {');
    expect(broad).toBeLessThan(0);
    expect(sharp).toBeLessThan(0);
    // The broad one is far more mobile than the deep one: that RATIO is the
    // cornea. Equal factors would move them as one painted decal.
    expect(Math.abs(broad)).toBeGreaterThan(Math.abs(sharp) * 2);
  });

  it('counter-move against the gaze — a reflection belongs to the room', () => {
    expect(parallaxFactor('.lia-eye-shape::before {')).toBeLessThan(0);
  });

  it('LAG the eye they sit on', () => {
    const rig = createEyeRig({
      initial: { expression: 'focused', styleId: 'cozmo', family: 'calm' },
    });
    rig.setGaze({ x: 1, y: 0 });
    for (let frame = 0; frame < 14; frame += 1) rig.step(16);
    // Mid-travel the eye is ahead of its own reflection...
    expect(rig.values().hlX).toBeLessThan(rig.values().gazeX);
    // ...and the reflection does get there.
    for (let frame = 0; frame < 200; frame += 1) rig.step(16);
    expect(rig.values().hlX).toBeCloseTo(1, 2);
  });
});

describe('per-style dosage', () => {
  it('every style states its own dose — adding one cannot forget to', () => {
    EYE_STYLE_IDS.filter(id => id !== DEFAULT_EYE_STYLE).forEach(id => {
      const block = styleBlock(id);
      expect(block, `style '${id}' declares no --matter`).toContain('--matter:');
      expect(block, `style '${id}' declares no --gloss`).toContain('--gloss:');
    });
  });

  it('leaves the stroke and the outline entirely alone', () => {
    ['traits', 'anneaux'].forEach(id => {
      expect(styleBlock(id)).toContain('--matter: 0;');
      expect(styleBlock(id)).toContain('--gloss: 0;');
    });
  });

  it('gives the marble the full treatment', () => {
    expect(styleBlock('billes')).toContain('--matter: 1;');
    expect(styleBlock('billes')).toContain('--gloss: 1;');
  });
});
