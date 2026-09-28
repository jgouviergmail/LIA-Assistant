import { readFileSync } from 'node:fs';
import path from 'node:path';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createInstance } from 'i18next';
import { describe, expect, it } from 'vitest';
import en from '../../../../../locales/en/translation.json';
import fr from '../../../../../locales/fr/translation.json';
import { FeatureCatalog } from '../FeatureCatalog';
import { FeatureExplorer, type FeatureExplorerProps } from '../FeatureExplorer';
import { FEATURE_SCENES } from '../FeatureScenes';
import { CHAPTERS, REQUIRED_FEATURE_KEYS } from '../chapters-data';

const languages = { en, fr };

async function translator(language: keyof typeof languages) {
  const i18n = createInstance();
  await i18n.init({ lng: language, resources: { [language]: { translation: languages[language] } } });
  return (key: string, options?: Record<string, unknown>) => i18n.t(key, options);
}

describe('FeatureCatalog', () => {
  it('preserves every full description and title while showing one readable detail', async () => {
    const t = await translator('en');
    const featureKeys = CHAPTERS[0].catalog;
    render(<FeatureCatalog t={t} featureKeys={featureKeys} />);

    expect(screen.getAllByRole('tab')).toHaveLength(featureKeys.length);
    expect(screen.getAllByRole('tabpanel', { hidden: true })).toHaveLength(featureKeys.length);
    expect(screen.getAllByRole('tabpanel')).toHaveLength(1);
    expect(screen.getByRole('tabpanel')).toHaveAccessibleName(t(`landing.features.${featureKeys[0]}.title`));
    for (const key of featureKeys) {
      expect(screen.getByText(t(`landing.features.${key}.description`))).toBeInTheDocument();
    }
  });

  it.each(['en', 'fr'] as const)('names the index and navigation in %s and changes the selected detail', async language => {
    const t = await translator(language);
    const user = userEvent.setup();
    render(<FeatureCatalog t={t} featureKeys={['multi_agent', 'telephony', 'live_voice']} />);

    const indexName = language === 'fr' ? 'Explore les capacités' : 'Explore the capabilities';
    const nextName = language === 'fr' ? 'Capacité suivante' : 'Next capability';
    expect(screen.getByRole('tablist', { name: indexName })).toBeInTheDocument();
    const next = screen.getByRole('button', { name: nextName });
    await user.click(next);
    expect(next).toHaveFocus();
    expect(screen.getByRole('tabpanel')).toHaveAccessibleName(t('landing.features.telephony.title'));
    expect(screen.getByText(t('landing.catalog_explorer.position', { current: 2, total: 3 }))).toBeVisible();
    await user.click(screen.getByRole('button', { name: t('landing.catalog_explorer.previous') }));
    expect(screen.getByRole('tabpanel')).toHaveAccessibleName(t('landing.features.multi_agent.title'));
  });

  it('supports roving keyboard selection, two-column movement, and focusing the full description', async () => {
    const t = await translator('en');
    const user = userEvent.setup();
    render(<FeatureCatalog t={t} featureKeys={CHAPTERS[0].catalog} />);
    const tabs = screen.getAllByRole('tab');

    tabs[0].focus();
    await user.keyboard('{ArrowRight}');
    expect(tabs[1]).toHaveFocus();
    expect(tabs[1]).toHaveAttribute('aria-selected', 'true');
    await user.keyboard('{ArrowDown}');
    expect(tabs[3]).toHaveFocus();
    await user.keyboard('{ArrowUp}{ArrowLeft}');
    expect(tabs[0]).toHaveFocus();
    await user.keyboard('{ArrowLeft}');
    expect(tabs.at(-1)).toHaveFocus();
    await user.keyboard('{Home}');
    expect(tabs[0]).toHaveFocus();
    await user.keyboard('{End}');
    expect(tabs.at(-1)).toHaveFocus();
    expect(tabs.filter(tab => tab.getAttribute('tabindex') === '0')).toHaveLength(1);

    await user.tab();
    const panel = screen.getByRole('tabpanel');
    expect(panel).toHaveFocus();
    expect(within(panel).getByRole('heading')).toHaveTextContent(tabs.at(-1)?.textContent ?? '');
  });

  it('gives every existing capability an explicit result illustration', () => {
    expect(Object.keys(FEATURE_SCENES).sort()).toEqual([...REQUIRED_FEATURE_KEYS].sort());
  });

  it.each(['en', 'fr', 'de', 'es', 'it', 'zh'])('has every explorer label and scene caption in %s', language => {
    const locale: {
      landing: { catalog_explorer?: Record<string, string | Record<string, string>> };
    } = JSON.parse(readFileSync(path.join(process.cwd(), 'locales', language, 'translation.json'), 'utf8'));
    const copy = locale.landing.catalog_explorer;
    expect(copy).toBeDefined();
    for (const key of ['browse', 'hint', 'previous', 'next', 'position']) {
      expect(copy?.[key], `${language}:${key}`).toBeTruthy();
    }
    expect(copy?.position).toContain('{{current}}');
    expect(copy?.position).toContain('{{total}}');
    for (const scene of new Set(Object.values(FEATURE_SCENES))) {
      expect(typeof copy?.scenes === 'object' && copy.scenes[scene], `${language}:${scene}`).toBeTruthy();
    }
  });

  it('keeps selection valid when the catalog changes and renders an empty catalog safely', () => {
    const props: FeatureExplorerProps = {
      items: [
        { id: 'memory', title: 'Memory', description: 'Remembered context', sceneLabel: 'Context', positionLabel: '1 of 2' },
        { id: 'telephony', title: 'Calls', description: 'Calls on your behalf', sceneLabel: 'Summary', positionLabel: '2 of 2' },
      ],
      labels: { browse: 'Explore', hint: 'Choose', previous: 'Previous', next: 'Next' },
    };
    const { rerender } = render(<FeatureExplorer {...props} />);
    rerender(<FeatureExplorer {...props} items={[props.items[1]]} />);
    expect(screen.getByRole('tabpanel', { name: 'Calls' })).toBeVisible();
    rerender(<FeatureExplorer {...props} items={[]} />);
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument();
  });
});
