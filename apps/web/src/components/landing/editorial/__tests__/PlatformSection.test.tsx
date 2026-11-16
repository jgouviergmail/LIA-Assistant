/**
 * The platform section's evidence, read through its real words: the four
 * proofs and the business base are tiles (owner, 2026-11-15: « des tuiles
 * serait plus lisible »), each opened by its icon beside its own title, its
 * text below.
 */

import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import fr from '../../../../../locales/fr/translation.json';

vi.mock('@/i18n', async () => {
  const { createInstance } = await import('i18next');
  const translation = (await import('../../../../../locales/fr/translation.json')).default;
  const instance = createInstance();
  await instance.init({
    lng: 'fr',
    resources: { fr: { translation } },
    interpolation: { escapeValue: false },
  });
  return { initI18next: async () => ({ t: instance.getFixedT('fr') }) };
});

import { PlatformSection } from '../PlatformSection';

describe('PlatformSection tiles', () => {
  it('opens every proof and the business base on an icon beside the title', async () => {
    render(await PlatformSection({ lng: 'fr' }));
    const words = fr.landing.platform;
    const section = screen.getByRole('region', { name: words.title });
    const tiles = [
      [words.accounts.title, words.accounts.body],
      [words.models.title, words.models.body],
      [words.monitoring.title, words.monitoring.body],
      [words.alerts.title, words.alerts.body],
      [words.business_title, words.business_body],
    ] as const;
    for (const [title, body] of tiles) {
      const heading = within(section).getByRole('heading', { level: 3, name: title });
      const row = heading.parentElement as HTMLElement;
      expect(row.querySelector('svg')).not.toBeNull();
      expect(within(row).queryByText(body)).not.toBeInTheDocument();
      expect(heading.closest('article')).toHaveTextContent(body);
    }
  });
});
