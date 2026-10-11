/**
 * Eye-style registry — the generic contract that makes adding a style cheap
 * AND safe: one id in the registry, one scoped CSS block, six locale entries.
 * The completeness checks below turn any missing piece into a red test
 * (registry doctrine: silent fallbacks are how features die invisibly).
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, it, expect } from 'vitest';

import {
  EYE_STYLE_IDS,
  HYBRID_EYE_STYLE_IDS,
  RIG_EYE_STYLE_IDS,
  EYE_STYLE_RENDERERS,
  DEFAULT_EYE_STYLE,
  DEFAULT_RIG_EYE_STYLE,
  isValidEyeStyle,
  isRigEyeStyle,
} from '@/components/eyes/eye-styles';
import { STYLE_GEOMETRY } from '@/components/eyes/rig/poses';
import enTranslations from '../../../../locales/en/translation.json';
import frTranslations from '../../../../locales/fr/translation.json';
import deTranslations from '../../../../locales/de/translation.json';
import esTranslations from '../../../../locales/es/translation.json';
import itTranslations from '../../../../locales/it/translation.json';
import zhTranslations from '../../../../locales/zh/translation.json';

/** Read the sheet raw from disk INSIDE the test (vitest's CSS pipeline
 * empties `?raw` imports, and a top-level read turns any hiccup into an
 * unreadable collection error). cwd is `apps/web` for every vitest pool. */
function readEyesCss(): string {
  return readFileSync(join(process.cwd(), 'src', 'styles', 'eyes.css'), 'utf8');
}

describe('eye-style registry', () => {
  it('selects Bip for new installations through the hybrid renderer', () => {
    expect(DEFAULT_EYE_STYLE).toBe('bip');
    expect(EYE_STYLE_RENDERERS[DEFAULT_EYE_STYLE]).toBe('hybrid');
  });

  it('retains separate native geometry for raw rig hosts', () => {
    expect(RIG_EYE_STYLE_IDS).toContain(DEFAULT_RIG_EYE_STYLE);
    expect(isRigEyeStyle(DEFAULT_RIG_EYE_STYLE)).toBe(true);
    expect(isRigEyeStyle(DEFAULT_EYE_STYLE)).toBe(false);
    expect(STYLE_GEOMETRY[DEFAULT_RIG_EYE_STYLE]).toBeDefined();
  });

  it.each(['moss', 'lumen', 'nimbo', 'orbit', 'bip', 'boulon', 'oscar'])(
    'accepts the %s companion without adding a dummy native geometry',
    id => {
      expect(isValidEyeStyle(id)).toBe(true);
      expect(EYE_STYLE_IDS).toContain(id);
      expect(RIG_EYE_STYLE_IDS).not.toContain(id);
      expect(Object.keys(STYLE_GEOMETRY)).not.toContain(id);
    }
  );

  it('names every hybrid companion and both variants in all six locales', () => {
    for (const translations of [
      enTranslations,
      frTranslations,
      deTranslations,
      esTranslations,
      itTranslations,
      zhTranslations,
    ]) {
      for (const id of HYBRID_EYE_STYLE_IDS) {
        expect(translations.eyes.styles[id].name).toBeTruthy();
        expect(translations.eyes.styles[id].description).toBeTruthy();
      }
      expect(translations.eyes.variants.female).toBeTruthy();
      expect(translations.eyes.variants.male).toBeTruthy();
    }
  });
  it('has unique ids and contains the default', () => {
    expect(new Set(EYE_STYLE_IDS).size).toBe(EYE_STYLE_IDS.length);
    expect(EYE_STYLE_IDS).toContain(DEFAULT_EYE_STYLE);
    expect(EYE_STYLE_IDS).toHaveLength(15);
    expect(HYBRID_EYE_STYLE_IDS).toEqual([
      'spirit',
      'moss',
      'lumen',
      'nimbo',
      'orbit',
      'bip',
      'boulon',
      'oscar',
    ]);
  });

  it('validates ids strictly', () => {
    expect(isValidEyeStyle('spirit')).toBe(true);
    expect(isValidEyeStyle('smiley')).toBe(true);
    expect(isValidEyeStyle(DEFAULT_EYE_STYLE)).toBe(true);
    expect(isValidEyeStyle('not-a-style')).toBe(false);
    expect(isValidEyeStyle(undefined)).toBe(false);
  });

  it('every native style ships its geometry and the hybrid composes an existing native skin', () => {
    for (const id of RIG_EYE_STYLE_IDS) {
      expect(STYLE_GEOMETRY[id], `missing rig geometry for style '${id}'`).toBeDefined();
      expect(isRigEyeStyle(id)).toBe(true);
    }
    expect(Object.keys(STYLE_GEOMETRY).sort()).toEqual([...RIG_EYE_STYLE_IDS].sort());
    expect(EYE_STYLE_RENDERERS.spirit).toBe('hybrid');
    expect(isRigEyeStyle('spirit')).toBe(false);
    expect(Object.keys(EYE_STYLE_RENDERERS).sort()).toEqual([...EYE_STYLE_IDS].sort());
  });

  it('native skins declare scoped CSS and hybrid characters share the actual body-and-face recipe', () => {
    const eyesCss = readEyesCss();
    for (const id of RIG_EYE_STYLE_IDS) {
      if (id === 'cozmo') continue; // Cozmo owns the base sheet, independent of the user default
      expect(eyesCss, `missing CSS block for style '${id}'`).toContain(`[data-style='${id}']`);
    }
    expect(eyesCss).toContain('.lia-spirit-companion .lia-head::before');
    expect(eyesCss).toContain('.lia-spirit-companion .lia-raster-face-mask');
    for (const id of HYBRID_EYE_STYLE_IDS) {
      expect(EYE_STYLE_RENDERERS[id]).toBe('hybrid');
      expect(isRigEyeStyle(id)).toBe(false);
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
    const en = (
      enTranslations as {
        eyes: { styles: Record<string, Record<string, string>> };
      }
    ).eyes.styles;
    const fr = (
      frTranslations as {
        eyes: { styles: Record<string, Record<string, string>> };
      }
    ).eyes.styles;
    for (const id of EYE_STYLE_IDS) {
      expect(en[id]?.name, `en name for '${id}'`).toBeTruthy();
      expect(en[id]?.description, `en description for '${id}'`).toBeTruthy();
      expect(fr[id]?.name, `fr name for '${id}'`).toBeTruthy();
      expect(fr[id]?.description, `fr description for '${id}'`).toBeTruthy();
    }
  });
});
