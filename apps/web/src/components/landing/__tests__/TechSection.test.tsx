/**
 * The engineering steps of the home page (« La fluidité se construit. »), read
 * through their real words: each step opens on its icon beside its own title —
 * a step number there said nothing (owner, 2026-11-15) — then its body and
 * what it brings.
 */

import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import fr from '../../../../locales/fr/translation.json';

vi.mock('@/i18n', async () => {
  const { createInstance } = await import('i18next');
  const translation = (await import('../../../../locales/fr/translation.json')).default;
  const instance = createInstance();
  await instance.init({
    lng: 'fr',
    resources: { fr: { translation } },
    interpolation: { escapeValue: false },
  });
  return { initI18next: async () => ({ t: instance.getFixedT('fr') }) };
});

import { TechSection } from '../TechSection';

const STEPS = ['context', 'plan', 'verify', 'control'] as const;

describe('TechSection engineering steps', () => {
  it('opens each step on its icon beside its title, with no step number', async () => {
    render(await TechSection({ lng: 'fr' }));
    const words = fr.landing.engineering;
    const section = screen.getByRole('region', { name: words.title });
    const titles = within(section)
      .getAllByRole('heading', { level: 3 })
      .filter(heading => STEPS.some(step => heading.textContent === words[`${step}_title`]));
    expect(titles.map(title => title.textContent)).toEqual(
      STEPS.map(step => words[`${step}_title`])
    );
    for (const [index, title] of titles.entries()) {
      const row = title.parentElement as HTMLElement;
      // The title shares the icon's row, where the number used to stand; the body follows below.
      expect(row.querySelector('svg')).not.toBeNull();
      expect(within(row).queryByText(words[`${STEPS[index]}_body`])).not.toBeInTheDocument();
      expect(within(row).queryByText(String(index + 1))).not.toBeInTheDocument();
      const step = title.closest('li') as HTMLElement;
      expect(within(step).getByText(words[`${STEPS[index]}_body`])).toBeInTheDocument();
      expect(within(step).getByText(words[`${STEPS[index]}_gain`])).toBeInTheDocument();
    }
  });
});
