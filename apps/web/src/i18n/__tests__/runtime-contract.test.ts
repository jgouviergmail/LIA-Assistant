/** Real i18next contracts for LIA's catalogues and untrusted locale inputs. */

import { createInstance } from 'i18next';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { initI18next, translationBundle, validateLanguage } from '@/i18n';
import { isTranslationTree, type TranslationTree } from '../scoped-translations';
import { getTranslation } from '../server';
import type { TextTranslator } from '../types';
import {
  cookieName,
  defaultNS,
  fallbackLng,
  getLocaleCookie,
  getOptions,
  isLanguage,
  languages,
} from '../settings';

vi.unmock('react-i18next');

// The advisory's inherited names plus path, markup and overlong inputs.
const UNTRUSTED_LOCALES = [
  ...Object.getOwnPropertyNames(Object.prototype),
  'constructor-US',
  '../en',
  'en/../fr',
  '<img src=x onerror=alert(1)>',
  'x'.repeat(129),
];

afterEach(() => {
  document.cookie = `${cookieName}=; path=/; max-age=0`;
});

/** Find the catalogue's intentional blanks without hardcoding their count. */
function emptyKeys(tree: TranslationTree, prefix = ''): string[] {
  return Object.entries(tree).flatMap(([key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    if (value === '') return [path];
    return isTranslationTree(value) ? emptyKeys(value, path) : [];
  });
}

describe('real catalogue translation semantics', () => {
  it.each(languages)(
    '%s preserves intentional blanks, including prefixed and object reads',
    async lng => {
      const catalogue = translationBundle(lng);
      const blanks = emptyKeys(catalogue);
      // These two visible surfaces intentionally render no subtitle or particle.
      expect(blanks).toEqual(
        expect.arrayContaining(['chat.page.subtitle', 'landing.hero.title_line2_before'])
      );

      const instance = await initI18next(lng);
      expect(instance.language).toBe(lng);
      for (const key of blanks) {
        expect(instance.t(key), `${lng}: ${key}`).toBe('');
      }
      expect(catalogue).toHaveProperty('chat.page', instance.t('chat.page'));

      const { t } = await getTranslation(lng, defaultNS, { keyPrefix: 'chat.page' });
      expect(t('subtitle')).toBe('');
    }
  );

  it('keeps the declared French fallback and React interpolation without double escaping', async () => {
    const instance = createInstance();
    await instance.init({
      ...getOptions('de'),
      resources: {
        [fallbackLng]: { [defaultNS]: { plain: 'Ready', fallback: '{{value}} / {{date}}' } },
      },
    });
    const translate: TextTranslator = instance.t;
    expect(translate('plain')).toBe('Ready');
    expect(translate('plain', {})).toBe(translate('plain'));
    expect(translate('fallback', { value: 'R&D', date: '16/11/2026' })).toBe('R&D / 16/11/2026');
  });
});

describe('untrusted locale boundaries', () => {
  it.each([...UNTRUSTED_LOCALES, '', 'pt', 'zh-CN', 'FR', 'en=de'])(
    'rejects %j as an account locale and shares the validated French server instance',
    async raw => {
      expect(isLanguage(raw)).toBe(false);
      expect(validateLanguage(raw)).toBe(fallbackLng);
      document.cookie = `${cookieName}=${raw}; path=/`;
      expect(getLocaleCookie()).toBeNull();

      const fallback = await initI18next(fallbackLng);
      expect(await initI18next(raw)).toBe(fallback);
      expect(fallback.language).toBe(fallbackLng);
    }
  );

  it.each(UNTRUSTED_LOCALES)(
    'the shared i18next options refuse %j even without the URL validator',
    async raw => {
      const instance = createInstance();
      await instance.init({
        ...getOptions(),
        lng: raw,
        resources: { [fallbackLng]: { [defaultNS]: { probe: 'Ready' } } },
      });
      expect(instance.language).toBe(fallbackLng);
      expect(instance.t('probe')).toBe('Ready');
    }
  );
});
