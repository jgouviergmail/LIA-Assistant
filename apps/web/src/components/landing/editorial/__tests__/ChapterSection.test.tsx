import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createInstance } from 'i18next';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import en from '../../../../../locales/en/translation.json';
import fr from '../../../../../locales/fr/translation.json';
import { ChapterSection } from '../ChapterSection';
import { CHAPTERS } from '../chapters-data';
import type { Translate } from '../FeatureCatalog';

beforeEach(() => {
  // Exercise the native chapter, including its reveal and disclosures, in
  // reduced motion so no layout observer is needed in the DOM environment.
  vi.stubGlobal(
    'matchMedia',
    vi.fn(
      (query: string): MediaQueryList => ({
        matches: query === '(prefers-reduced-motion: reduce)',
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(() => true),
      })
    )
  );
});

describe.each(['en', 'fr'] as const)('ChapterSection reading order (%s)', language => {
  it.each([false, true])(
    'keeps one introduction, proof and explanation in keyboard order (reverse: %s)',
    async reverse => {
      const i18n = createInstance();
      await i18n.init({
        lng: language,
        resources: { en: { translation: en }, fr: { translation: fr } },
      });
      const t: Translate = (key, options) => i18n.t(key, options);
      const chapter = CHAPTERS[0];
      const user = userEvent.setup();
      render(
        <ChapterSection
          t={t}
          chapter={chapter}
          reverse={reverse}
          visual={<button type="button">Inspect the proof</button>}
          catalogExtra={<p>Extra chapter guidance</p>}
        />
      );

      const title = screen.getByRole('heading', {
        level: 2,
        name: t(`landing.chapters.${chapter.key}.title`),
      });
      const proof = screen.getByRole('button', { name: 'Inspect the proof' });
      const benefit = screen.getByText(t(`landing.chapters.${chapter.key}.b1_t`));
      expect(title.compareDocumentPosition(proof) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
      expect(
        proof.compareDocumentPosition(benefit) & Node.DOCUMENT_POSITION_FOLLOWING
      ).toBeTruthy();
      expect(screen.getAllByRole('heading', { level: 2 })).toHaveLength(1);
      expect(screen.getAllByRole('button', { name: 'Inspect the proof' })).toHaveLength(1);
      expect(screen.getAllByText(t(`landing.chapters.${chapter.key}.b1_t`))).toHaveLength(1);

      await user.tab();
      expect(proof).toHaveFocus();
      await user.tab();
      expect(screen.getByText(t('landing.editorial.mechanism_label'))).toHaveFocus();
      await user.tab();
      const catalog = screen.getByRole('button', {
        name: name => name.startsWith(t('landing.chapters.catalog_label')),
      });
      expect(catalog).toHaveFocus();
      expect(catalog).toHaveAttribute('aria-expanded', 'false');
      await user.click(catalog);
      expect(catalog).toHaveAttribute('aria-expanded', 'true');
      expect(screen.getByText('Extra chapter guidance')).toBeVisible();
    }
  );
});
