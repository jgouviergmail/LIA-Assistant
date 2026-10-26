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
  await i18n.init({
    lng: language,
    resources: { [language]: { translation: languages[language] } },
  });
  return (key: string, options?: Record<string, unknown>) => i18n.t(key, options);
}

describe('FeatureCatalog', () => {
  it.each(['en', 'fr'] as const)(
    'keeps the World and peer capabilities in their own readable catalogs in %s',
    async language => {
      const t = await translator(language);
      const chapter = CHAPTERS.find(item => item.id === 'world');
      if (!chapter) throw new Error('Missing shared-world chapter');
      const user = userEvent.setup();
      const { container, unmount } = render(<FeatureCatalog t={t} featureKeys={chapter.catalog} />);
      expect(screen.getByRole('tabpanel')).toHaveAccessibleName(t('landing.features.world.title'));
      await user.click(screen.getByRole('tab', { name: t('landing.features.world_audio.title') }));
      expect(screen.getByRole('tabpanel')).toHaveTextContent(
        t('landing.catalog_explorer.feature_examples.world_audio.result')
      );
      expect(screen.queryByRole('tab', { name: t('landing.features.peers.title') })).toBeNull();
      expect(container.textContent).not.toContain('landing.');
      expect(container.textContent).not.toContain('undefined');
      unmount();
      const connections = CHAPTERS.find(item => item.id === 'connect');
      if (!connections) throw new Error('Missing connection chapter');
      render(<FeatureCatalog t={t} featureKeys={connections.catalog} />);
      expect(screen.getByRole('tabpanel')).toHaveAccessibleName(t('landing.features.peers.title'));
      expect(screen.queryByRole('tab', { name: t('landing.features.world.title') })).toBeNull();
    }
  );

  it('preserves every full description and title while showing one readable detail', async () => {
    const t = await translator('en');
    const featureKeys = CHAPTERS[0].catalog;
    render(<FeatureCatalog t={t} featureKeys={featureKeys} />);

    expect(screen.getAllByRole('tab')).toHaveLength(featureKeys.length);
    expect(screen.getAllByRole('tabpanel', { hidden: true })).toHaveLength(featureKeys.length);
    expect(screen.getAllByRole('tabpanel')).toHaveLength(1);
    expect(screen.getByRole('tabpanel')).toHaveAccessibleName(
      t(`landing.features.${featureKeys[0]}.title`)
    );
    const example = featureKeys[0];
    expect(
      within(screen.getByRole('tabpanel')).getByText(t('landing.catalog_explorer.example_label'))
    ).toBeVisible();
    expect(
      within(screen.getByRole('tabpanel')).getByText(
        t(`landing.catalog_explorer.feature_examples.${example}.request`)
      )
    ).toBeVisible();
    expect(
      within(screen.getByRole('tabpanel')).getByText(t('landing.catalog_explorer.result_label'))
    ).toBeVisible();
    expect(
      within(screen.getByRole('tabpanel')).getByText(
        t(`landing.catalog_explorer.feature_examples.${example}.result`)
      )
    ).toBeVisible();
    for (const key of featureKeys) {
      const descriptionKey = ['meetings', 'live_voice', 'telephony'].includes(key)
        ? `landing.home_feature_descriptions.${key}`
        : `landing.features.${key}.description`;
      expect(screen.getByText(t(descriptionKey))).toBeInTheDocument();
    }
    expect(screen.queryByText(t('landing.features.meetings.description'))).not.toBeInTheDocument();
  });

  it.each(['en', 'fr'] as const)(
    'names the index and navigation in %s and changes the selected detail',
    async language => {
      const t = await translator(language);
      const user = userEvent.setup();
      render(<FeatureCatalog t={t} featureKeys={['multi_agent', 'telephony', 'live_voice']} />);

      const indexName = language === 'fr' ? 'Explore les capacités' : 'Explore the capabilities';
      const nextName = language === 'fr' ? 'Capacité suivante' : 'Next capability';
      expect(screen.getByRole('tablist', { name: indexName })).toBeInTheDocument();
      const next = screen.getByRole('button', { name: nextName });
      await user.click(next);
      expect(next).toHaveFocus();
      expect(screen.getByRole('tabpanel')).toHaveAccessibleName(
        t('landing.features.telephony.title')
      );
      expect(
        within(screen.getByRole('tabpanel')).getByText(
          t('landing.catalog_explorer.feature_examples.telephony.request')
        )
      ).toBeVisible();
      expect(
        within(screen.getByRole('tabpanel')).getByText(
          t('landing.catalog_explorer.feature_examples.telephony.result')
        )
      ).toBeVisible();
      expect(
        screen.getByText(t('landing.catalog_explorer.position', { current: 2, total: 3 }))
      ).toBeVisible();
      await user.click(
        screen.getByRole('button', { name: t('landing.catalog_explorer.previous') })
      );
      expect(screen.getByRole('tabpanel')).toHaveAccessibleName(
        t('landing.features.multi_agent.title')
      );
    }
  );

  it('keeps budget controls, owner callbacks and theme settings tied to their own examples', async () => {
    const user = userEvent.setup();
    const featureKeys = ['usage_limits', 'telephony_callback', 'themes'];
    const resolvedKeys: string[] = [];
    const t = (key: string) => {
      resolvedKeys.push(key);
      return key;
    };
    render(<FeatureCatalog t={t} featureKeys={featureKeys} />);

    for (const feature of featureKeys) {
      await user.click(screen.getByRole('tab', { name: `landing.features.${feature}.title` }));
      const panel = within(screen.getByRole('tabpanel'));
      expect(
        panel.getByText(`landing.catalog_explorer.feature_examples.${feature}.request`)
      ).toBeVisible();
      expect(
        panel.getByText(`landing.catalog_explorer.feature_examples.${feature}.result`)
      ).toBeVisible();
      for (const other of featureKeys.filter(candidate => candidate !== feature)) {
        expect(
          panel.queryByText(`landing.catalog_explorer.feature_examples.${other}.request`)
        ).not.toBeInTheDocument();
      }
    }

    expect(resolvedKeys.some(key => key.startsWith('landing.catalog_explorer.examples.'))).toBe(
      false
    );
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

  it.each(['en', 'fr', 'de', 'es', 'it', 'zh'])(
    'has every explorer label, scene caption and feature-specific example in %s',
    language => {
      const locale: {
        landing: {
          catalog_explorer?: {
            browse: string;
            hint: string;
            previous: string;
            next: string;
            position: string;
            example_label: string;
            result_label: string;
            scenes: Record<string, string>;
            examples: Record<string, { request: string; result: string }>;
            feature_examples: Record<string, { request: string; result: string }>;
          };
          home_feature_descriptions: { meetings: string };
        };
      } = JSON.parse(
        readFileSync(path.join(process.cwd(), 'locales', language, 'translation.json'), 'utf8')
      );
      const copy = locale.landing.catalog_explorer;
      expect(copy).toBeDefined();
      if (!copy) throw new Error(`Missing explorer copy: ${language}`);
      for (const key of [
        'browse',
        'hint',
        'previous',
        'next',
        'position',
        'example_label',
        'result_label',
      ] as const) {
        expect(copy[key], `${language}:${key}`).toBeTruthy();
      }
      expect(copy.position).toContain('{{current}}');
      expect(copy.position).toContain('{{total}}');
      for (const scene of new Set(Object.values(FEATURE_SCENES))) {
        expect(
          typeof copy.scenes === 'object' && copy.scenes[scene],
          `${language}:${scene}`
        ).toBeTruthy();
      }
      expect(Object.keys(copy.feature_examples ?? {}).sort()).toEqual(
        [...REQUIRED_FEATURE_KEYS].sort()
      );
      for (const feature of REQUIRED_FEATURE_KEYS) {
        for (const field of ['request', 'result'] as const) {
          const value = copy.feature_examples[feature]?.[field];
          expect(typeof value, `${language}:${feature}:${field}`).toBe('string');
          expect(value?.trim(), `${language}:${feature}:${field}`).toBeTruthy();
        }
      }
      const distinctFeatures = ['usage_limits', 'telephony_callback', 'themes'];
      for (const field of ['request', 'result'] as const) {
        expect(
          new Set(distinctFeatures.map(feature => copy.feature_examples[feature]?.[field])).size
        ).toBe(distinctFeatures.length);
      }
      expect(locale.landing.home_feature_descriptions.meetings.trim()).toBeTruthy();
    }
  );

  it('keeps selection valid when the catalog changes and renders an empty catalog safely', () => {
    const props: FeatureExplorerProps = {
      items: [
        {
          id: 'memory',
          title: 'Memory',
          description: 'Remembered context',
          sceneLabel: 'Context',
          positionLabel: '1 of 2',
          exampleRequest: 'Remember my preference',
          exampleResult: 'An editable memory',
        },
        {
          id: 'telephony',
          title: 'Calls',
          description: 'Calls on your behalf',
          sceneLabel: 'Summary',
          positionLabel: '2 of 2',
          exampleRequest: 'Prepare a call',
          exampleResult: 'A proposal to approve',
        },
      ],
      labels: {
        browse: 'Explore',
        hint: 'Choose',
        previous: 'Previous',
        next: 'Next',
        example: 'Example request',
        result: 'Expected result',
      },
    };
    const { rerender } = render(<FeatureExplorer {...props} />);
    rerender(<FeatureExplorer {...props} items={[props.items[1]]} />);
    expect(screen.getByRole('tabpanel', { name: 'Calls' })).toBeVisible();
    rerender(<FeatureExplorer {...props} items={[]} />);
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument();
  });
});
