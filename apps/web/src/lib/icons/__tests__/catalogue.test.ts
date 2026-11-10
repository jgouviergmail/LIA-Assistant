import { execFileSync } from 'node:child_process';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import * as flex from '../artwork-flex';
import * as fluent from '../artwork-fluent';
import {
  colorHue,
  contrast,
  hasDifferentHues,
  parseArtwork,
  reachableColors,
} from './catalogue-paints';

const REPO_ROOT = path.resolve(__dirname, '../../../../../..');

describe('application icon catalogue', () => {
  it.each([flex.flex_cog_flat, fluent.fluent_settings])(
    'colors a gear and its contrasting hub',
    artwork => {
      const document = parseArtwork(artwork.body);
      expect(document.querySelector('circle[stroke="#E6A632"]')).not.toBeNull();
      expect(hasDifferentHues(reachableColors(document))).toBe(true);
    }
  );

  it.each([flex.flex_recycle_bin_3_flat, flex.flex_broken_link_1_flat])(
    'retains destructive red as a visible paint',
    artwork => {
      expect(
        reachableColors(parseArtwork(artwork.body)).some(color => {
          const hue = colorHue(color);
          return hue !== null && (hue >= 330 || hue <= 15);
        })
      ).toBe(true);
    }
  );

  it('does not mistake unused paint servers, transparent paint or neutral shading for multicolor artwork', () => {
    for (const body of [
      '<defs><linearGradient id="unused"><stop stop-color="#2875B5"/><stop offset="1" stop-color="#965BC2"/></linearGradient></defs><path fill="#2875B5" d="M0 0h24v24H0z"/>',
      '<rect width="24" height="24" fill="#2875B5"/><circle r="4" fill="#965BC2" opacity="0"/>',
      '<rect width="24" height="24" fill="#2875B5"/><circle r="4" fill="#ffffff"/>',
    ])
      expect(hasDifferentHues(reachableColors(parseArtwork(body)))).toBe(false);
  });

  it.each(Object.entries({ ...fluent, ...flex }))(
    '%s reaches two distinct chromatic paints',
    (_name, artwork) => {
      expect(hasDifferentHues(reachableColors(parseArtwork(artwork.body)))).toBe(true);
    }
  );

  it.each([
    flex.flex_check_square_flat,
    flex.flex_help_chat_1_flat,
    flex.flex_warranty_badge_highlight_flat,
  ])('keeps native foreground details distinct from their colored surface', artwork => {
    const colors = [...new Set(reachableColors(parseArtwork(artwork.body)))];
    expect(colors).toHaveLength(2);
    expect(contrast(colors[0], colors[1])).toBeGreaterThanOrEqual(3);
  });

  it.each([fluent.fluent_warning, fluent.fluent_error_circle, fluent.fluent_question_circle])(
    'retains neutral contrasting native punctuation',
    artwork => {
      const colors = reachableColors(parseArtwork(artwork.body));
      expect(colors.some(color => /^#(?:fff(?:fff)?|fdfdfd|212121|4a4a4a)$/i.test(color))).toBe(
        true
      );
    }
  );

  it('covers every runtime import and reproduces the reviewed vendor geometry', () => {
    expect(() =>
      execFileSync(process.execPath, ['scripts/icons/generate.mjs', '--check'], {
        cwd: REPO_ROOT,
        stdio: 'pipe',
      })
    ).not.toThrow();
  }, 30_000);

  it('proves that direct imports and namespace imports cannot evade the census', () => {
    expect(() =>
      execFileSync(process.execPath, ['--test', 'scripts/icons/source-inventory.test.mjs'], {
        cwd: REPO_ROOT,
        stdio: 'pipe',
      })
    ).not.toThrow();
  }, 30_000);

  it('preserves native paint luminance and rejects flattened contrast', () => {
    expect(() =>
      execFileSync(process.execPath, ['--test', 'scripts/icons/native-chromatic.test.mjs'], {
        cwd: REPO_ROOT,
        stdio: 'pipe',
      })
    ).not.toThrow();
  }, 30_000);

  it.each(Object.entries({ ...fluent, ...flex }))(
    '%s contains only self-contained SVG artwork',
    (_name, artwork) => {
      const document = new DOMParser().parseFromString(
        `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${artwork.viewBox}">${artwork.body}</svg>`,
        'image/svg+xml'
      );
      expect(document.querySelector('parsererror')).toBeNull();
      expect(document.querySelector('script, foreignObject, image, a, style')).toBeNull();
      const ids = [...document.querySelectorAll('[id]')].map(element => element.id);
      expect(new Set(ids).size).toBe(ids.length);
      for (const element of document.querySelectorAll('*')) {
        for (const attribute of element.attributes) {
          if (attribute.name === 'xmlns') {
            expect(attribute.value).toBe('http://www.w3.org/2000/svg');
            continue;
          }
          expect(attribute.name).not.toMatch(/^on/i);
          expect(attribute.value).not.toMatch(/(?:https?:|javascript:|data:)/i);
          if (attribute.name === 'style') {
            expect(attribute.value).toMatch(
              /^fill:light-dark\(#[\dA-Fa-f]{6},color-mix\(in srgb,#[\dA-Fa-f]{6} 68%,white\)\)$/
            );
            expect(element.getAttribute('fill')).toMatch(/^#[\dA-Fa-f]{6}$/);
          }
          if (attribute.localName === 'href') {
            expect(attribute.value).toMatch(/^#/);
            expect(ids).toContain(attribute.value.slice(1));
          }
          for (const reference of attribute.value.matchAll(/url\(#([^)]+)\)/g)) {
            expect(ids).toContain(reference[1]);
          }
        }
      }
    }
  );
});
