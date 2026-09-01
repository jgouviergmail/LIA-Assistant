/**
 * Eye-style registry — the generic contract that makes adding a style cheap
 * AND safe: one id in the registry, one scoped CSS block, six locale entries.
 * The completeness checks below turn any missing piece into a red test
 * (registry doctrine: silent fallbacks are how features die invisibly).
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, it, expect } from 'vitest';

import { EYE_STYLE_IDS, DEFAULT_EYE_STYLE, isValidEyeStyle } from '@/components/eyes/eye-styles';
import { STYLE_GEOMETRY } from '@/components/eyes/rig/poses';
import enTranslations from '../../../../locales/en/translation.json';
import frTranslations from '../../../../locales/fr/translation.json';

/** Read the sheet raw from disk INSIDE the test (vitest's CSS pipeline
 * empties `?raw` imports, and a top-level read turns any hiccup into an
 * unreadable collection error). cwd is `apps/web` for every vitest pool. */
function readEyesCss(): string {
  return readFileSync(join(process.cwd(), 'src', 'styles', 'eyes.css'), 'utf8');
}

describe('eye-style registry', () => {
  it('has unique ids and contains the default', () => {
    expect(new Set(EYE_STYLE_IDS).size).toBe(EYE_STYLE_IDS.length);
    expect(EYE_STYLE_IDS).toContain(DEFAULT_EYE_STYLE);
    expect(EYE_STYLE_IDS.length).toBeGreaterThanOrEqual(6);
  });

  it('validates ids strictly', () => {
    expect(isValidEyeStyle(DEFAULT_EYE_STYLE)).toBe(true);
    expect(isValidEyeStyle('not-a-style')).toBe(false);
    expect(isValidEyeStyle(undefined)).toBe(false);
  });

  it('every style ships its pose geometry (the rig half of the contract)', () => {
    // Adding a style now costs FOUR things, not three: an id, a scoped CSS
    // block (what is drawn), an entry in the rig's style geometry (what is
    // moved) and six locale entries. This closes the half the CSS check
    // cannot see.
    for (const id of EYE_STYLE_IDS) {
      expect(STYLE_GEOMETRY[id], `missing rig geometry for style '${id}'`).toBeDefined();
    }
  });

  it('every non-default style ships its scoped CSS recipe block', () => {
    const eyesCss = readEyesCss();
    for (const id of EYE_STYLE_IDS) {
      if (id === DEFAULT_EYE_STYLE) continue; // the default IS the base sheet
      expect(eyesCss, `missing CSS block for style '${id}'`).toContain(`[data-style='${id}']`);
    }
  });

  it('the stylesheet declares no silhouette radius at all any more', () => {
    // A radius declared by an un-scoped `[data-expression=...] .lia-eye` rule
    // out-inherits the silhouette every style sets on the root (the nearest
    // custom-property definition wins), silently turning every style into the
    // default one. Shipped exactly that way on 2026-08-21: in production the
    // psyche-driven idle (tender/bored/focused...) rendered ALL six styles as
    // Cozmo rectangles. Radii are rig channels now, so the door is closed on
    // both sides: this check keeps the CSS one shut, and its twin in
    // `rig/__tests__/poses.test.ts` keeps the pose tables from re-opening it.
    const eyesCss = readEyesCss();
    const offenders: string[] = [];
    for (const block of eyesCss.split('}')) {
      const hasRadius = /--r(?:v)?-(?:top|bot)\s*:/.test(block);
      const selector = block.slice(0, block.indexOf('{')).trim();
      if (
        hasRadius &&
        selector.includes('[data-expression=') &&
        !selector.includes('[data-style=')
      ) {
        offenders.push(selector.replace(/\s+/g, ' '));
      }
    }
    expect(offenders, 'radius in un-scoped expression recipe').toEqual([]);
  });

  it('every style ships its localized name and description (en + fr)', () => {
    const en = (enTranslations as { eyes: { styles: Record<string, Record<string, string>> } }).eyes
      .styles;
    const fr = (frTranslations as { eyes: { styles: Record<string, Record<string, string>> } }).eyes
      .styles;
    for (const id of EYE_STYLE_IDS) {
      expect(en[id]?.name, `en name for '${id}'`).toBeTruthy();
      expect(en[id]?.description, `en description for '${id}'`).toBeTruthy();
      expect(fr[id]?.name, `fr name for '${id}'`).toBeTruthy();
      expect(fr[id]?.description, `fr description for '${id}'`).toBeTruthy();
    }
  });
});
