/**
 * The boundary between the rig and the stylesheet, enforced.
 *
 * The whole design rests on one rule — "TS owns what MOVES, CSS owns what is
 * DRAWN" — and a rule nobody can break by accident is worth more than a rule
 * written in a comment. Four checks:
 *
 *  1. no stylesheet DECLARES a `--rig-*` property (it would silently outrank
 *     the rig on any element below it, which is exactly the class of bug that
 *     turned all six styles into Cozmo in 2026-08);
 *  2. every `--rig-*` the stylesheet READS is a real channel;
 *  3. every fallback matches its channel's rest value — those fallbacks are
 *     what renders the neutral pose before the first frame, and drift there
 *     is invisible until someone loads the page with JS disabled;
 *  4. no `transition` on a property the rig writes every frame, and every
 *     channel is actually consumed (a channel nothing reads is dead weight).
 *
 * The sheet is read from disk on purpose: a `?raw` CSS import comes back
 * EMPTY under vitest, which would make every assertion here vacuously true.
 */

import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { CHANNELS, CHANNEL_KEYS, formatChannel } from '@/components/eyes/rig/channels';
import { STYLE_LID_MODE } from '@/components/eyes/rig/poses';
import { EYE_STYLE_IDS } from '@/components/eyes/eye-styles';

const CSS = readFileSync(join(process.cwd(), 'src/styles/eyes.css'), 'utf8');

/** Properties the rig writes every frame: a transition on one of them chases
 * a moving target and fights the springs. */
const RIG_OWNED_PROPERTIES = ['transform', 'clip-path', 'border-radius', 'all'];

/** Strip comments so a documented counter-example is never read as code. */
const CODE = CSS.replace(/\/\*[\s\S]*?\*\//g, '');

describe('eyes.css × rig boundary', () => {
  it('never declares a `--rig-*` property', () => {
    const declarations = CODE.match(/--rig-[a-z0-9-]+\s*:/g) ?? [];
    expect(declarations).toEqual([]);
  });

  it('only reads channels that exist', () => {
    const known = new Set(CHANNEL_KEYS.map(key => CHANNELS[key].cssVar));
    const referenced = [...CODE.matchAll(/var\(\s*(--rig-[a-z0-9-]+)/g)].map(match => match[1]);
    expect(referenced.length).toBeGreaterThan(0);
    [...new Set(referenced)].forEach(name => expect(known.has(name)).toBe(true));
  });

  it("falls back to each channel's rest value, exactly", () => {
    const restByVar = new Map(
      CHANNEL_KEYS.map(key => [CHANNELS[key].cssVar, formatChannel(key, CHANNELS[key].rest)])
    );
    const uses = [...CODE.matchAll(/var\(\s*(--rig-[a-z0-9-]+)\s*,\s*([^)]+?)\s*\)/g)];
    expect(uses.length).toBeGreaterThan(0);
    const drifted = uses
      .filter(([, name, fallback]) => fallback !== restByVar.get(name))
      .map(([, name, fallback]) => `${name}: ${fallback} != ${restByVar.get(name)}`);
    expect(drifted).toEqual([]);
  });

  it('gives every `--rig-*` reference a fallback (no bare read)', () => {
    const bare = [...CODE.matchAll(/var\(\s*(--rig-[a-z0-9-]+)\s*\)/g)].map(match => match[1]);
    expect(bare).toEqual([]);
  });

  it('consumes every channel the rig publishes', () => {
    const referenced = new Set(
      [...CODE.matchAll(/var\(\s*(--rig-[a-z0-9-]+)/g)].map(match => match[1])
    );
    const orphans = CHANNEL_KEYS.filter(
      key => !CHANNELS[key].internal && !referenced.has(CHANNELS[key].cssVar)
    );
    expect(orphans).toEqual([]);
  });

  it('holds INTERNAL channels to account too — one nothing reads is dead', () => {
    // An internal channel escapes the "must be drawn" rule because the rig
    // reads it to compute something else. That exemption is only honest if
    // the reading actually exists.
    const runtime = readFileSync(join(process.cwd(), 'src/components/eyes/rig/runtime.ts'), 'utf8');
    const internal = CHANNEL_KEYS.filter(key => CHANNELS[key].internal);
    expect(internal.length).toBeGreaterThan(0);
    internal.forEach(key => {
      expect({ key, read: runtime.includes(`.${key}`) }).toEqual({ key, read: true });
    });
  });

  it('agrees with the pose tables on WHICH styles squash instead of clipping', () => {
    // Two halves of one decision: the rig folds the sustained lids into a
    // squash for these styles, and the stylesheet does the same for the blink.
    // Drift between them would give a style a squashed blink and a clipped
    // squint — or the reverse, which is what broke the ring in the browser.
    const squashing = EYE_STYLE_IDS.filter(id => STYLE_LID_MODE[id] === 'squash').sort();
    const rule = CODE.slice(
      CODE.indexOf('.lia-eye-blink {', CODE.indexOf('clip-path: none')) - 400
    );
    const declared = [...CODE.matchAll(/\[data-style='([a-z]+)'\] \.lia-eye-blink/g)]
      .map(match => match[1])
      .sort();
    expect(rule.length).toBeGreaterThan(0);
    expect([...new Set(declared)]).toEqual(squashing);
  });

  it('declares its base tokens BEFORE any style block (source order decides)', () => {
    // `.lia-eyes` and `[data-style='x']` match the SAME element with the SAME
    // specificity (0,1,0), so nothing but source order makes a style's
    // `--matter` / `--gloss` / geometry win over the defaults. Move the base
    // block below them and every style silently reverts — with no error
    // anywhere. This is the same class as the 2026-08 radius inheritance bug.
    const base = CODE.indexOf('.lia-eyes {');
    const firstStyle = CODE.indexOf("[data-style='");
    expect(base).toBeGreaterThan(-1);
    expect(firstStyle).toBeGreaterThan(-1);
    expect(base).toBeLessThan(firstStyle);
  });

  it('never transitions a property the rig writes', () => {
    const transitions = [...CODE.matchAll(/transition\s*:\s*([^;}]+)/g)].map(match =>
      match[1].toLowerCase()
    );
    const offenders = transitions.filter(
      declaration =>
        declaration.trim() !== 'none !important' &&
        RIG_OWNED_PROPERTIES.some(property => declaration.includes(property))
    );
    expect(offenders).toEqual([]);
  });
});
