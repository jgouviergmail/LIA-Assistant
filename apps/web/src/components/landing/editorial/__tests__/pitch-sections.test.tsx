/**
 * The home page's pitch sections, rendered through their real words: the
 * positioning under the hero (its thesis counting the living map's bricks
 * from a floor, never a typed figure), the five arguments in reading order,
 * and the comparison under its own heading.
 */

import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import en from '../../../../../locales/en/translation.json';
import fr from '../../../../../locales/fr/translation.json';

vi.mock('@/i18n', async () => {
  const { createInstance } = await import('i18next');
  const resources = {
    fr: { translation: (await import('../../../../../locales/fr/translation.json')).default },
    en: { translation: (await import('../../../../../locales/en/translation.json')).default },
  };
  const instance = createInstance();
  await instance.init({ lng: 'fr', resources, interpolation: { escapeValue: false } });
  return { initI18next: async (lng: string) => ({ t: instance.getFixedT(lng) }) };
});

import { brickCountFloor } from '../../comparison/brick-floor';
import { ARGUMENT_IDS } from '../../comparison/comparison-data';
import { ComparisonSection } from '../../comparison/ComparisonSection';
import { ArgumentsSection } from '../ArgumentsSection';
import { PositioningSection } from '../PositioningSection';

describe('PositioningSection', () => {
  it('sets the market, then the thesis, with the floor of the living map', async () => {
    render(await PositioningSection({ lng: 'fr' }));
    const words = fr.landing.positioning;
    const section = screen.getByRole('region', { name: words.title });
    expect(section).toHaveAttribute('id', 'positioning');
    expect(within(section).getByRole('heading', { level: 2 })).toHaveTextContent(words.title);
    expect(within(section).getByText(words.market_agents)).toBeInTheDocument();
    expect(within(section).getByText(words.market_cloud)).toBeInTheDocument();
    expect(within(section).getByText(words.thesis_title)).toBeInTheDocument();
    expect(
      within(section).getByText(words.thesis_body.replace('{{count}}', String(brickCountFloor())))
    ).toBeInTheDocument();
  });

  it('stages the two worlds by their marks and the thesis by its figure', async () => {
    render(await PositioningSection({ lng: 'fr' }));
    const words = fr.landing.positioning;
    const section = screen.getByRole('region', { name: words.title });
    const marks = Array.from(section.querySelectorAll('img')).map(image =>
      image.getAttribute('src')
    );
    expect(marks).toEqual([
      '/comparison-icons/openclaw.svg',
      '/comparison-icons/hermes-agent.png',
      '/comparison-icons/meta-muse.svg',
    ]);
    expect(within(section).getByText(`${brickCountFloor()}+`)).toBeInTheDocument();
    expect(within(section).getByText(words.stat_label)).toBeInTheDocument();
  });
});

describe('ArgumentsSection', () => {
  it('reads its five arguments in order, each under its own title', async () => {
    render(await ArgumentsSection({ lng: 'en' }));
    const words = en.landing.arguments;
    const section = screen.getByRole('region', { name: words.title });
    expect(within(section).getByText(words.lede)).toBeInTheDocument();
    expect(
      within(section)
        .getAllByRole('heading', { level: 3 })
        .map(heading => heading.textContent)
    ).toEqual(ARGUMENT_IDS.map(id => words.items[id].title));
    for (const id of ARGUMENT_IDS) {
      expect(within(section).getByText(words.items[id].body)).toBeInTheDocument();
    }
  });

  it('illustrates each argument with a vignette of its own, hidden from assistive technology', async () => {
    render(await ArgumentsSection({ lng: 'fr' }));
    const section = screen.getByRole('region', { name: fr.landing.arguments.title });
    const vignettes = within(section)
      .getAllByRole('article')
      .map(article => article.querySelector('[data-vignette]'));
    expect(vignettes.map(vignette => vignette?.getAttribute('data-vignette'))).toEqual([
      ...ARGUMENT_IDS,
    ]);
    for (const vignette of vignettes) {
      expect(vignette).toHaveAttribute('aria-hidden', 'true');
    }
  });
});

describe('ComparisonSection', () => {
  it('opens the comparison under its own heading', async () => {
    render(await ComparisonSection({ lng: 'fr' }));
    const words = fr.landing.comparison;
    const section = screen.getByRole('region', { name: words.title });
    expect(section).toHaveAttribute('id', 'comparison');
    expect(within(section).getByText(words.lede)).toBeInTheDocument();
    // The explorer is mounted on its first duel (its words are tested with real i18n beside it).
    expect(within(section).getByRole('button', { name: 'OpenClaw' })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
  });
});
