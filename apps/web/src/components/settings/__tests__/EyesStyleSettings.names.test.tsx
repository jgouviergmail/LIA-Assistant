import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { EyesStyleSettings } from '../EyesStyleSettings';
import { HYBRID_EYE_STYLE_IDS } from '@/components/eyes/eye-styles';
import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';
import de from '../../../../locales/de/translation.json';
import es from '../../../../locales/es/translation.json';
import itTranslations from '../../../../locales/it/translation.json';
import zh from '../../../../locales/zh/translation.json';

const translations = { en, fr, de, es, it: itTranslations, zh };
function eyesDictionary(lng: string) {
  switch (lng) {
    case 'fr':
      return fr.eyes;
    case 'de':
      return de.eyes;
    case 'es':
      return es.eyes;
    case 'it':
      return itTranslations.eyes;
    case 'zh':
      return zh.eyes;
    default:
      return en.eyes;
  }
}

vi.mock('@/i18n/client', () => ({
  useTranslation: (lng: string) => ({
    t: (key: string) => {
      const dictionary = eyesDictionary(lng);
      const labels: Record<string, string> = Object.fromEntries(
        Object.entries(dictionary.styles).map(([id, value]) => [
          `eyes.styles.${id}.name`,
          value.name,
        ])
      );
      labels['eyes.variants.female'] = dictionary.variants.female;
      labels['eyes.variants.male'] = dictionary.variants.male;
      return labels[key] ?? key;
    },
  }),
}));

afterEach(cleanup);

describe('the gendered options accessible names and variant captions', () => {
  it.each(['en', 'fr', 'de', 'es', 'it', 'zh'] as const)('announces its actual %s label', lng => {
    render(<EyesStyleSettings lng={lng} />);
    const dictionary = translations[lng].eyes;
    for (const id of ['smiley', ...HYBRID_EYE_STYLE_IDS] as const) {
      const name = dictionary.styles[id].name;
      const option = screen.getByRole('button', { name });
      expect(option).toHaveAccessibleName(name);
      expect(option).toHaveTextContent(dictionary.variants.female);
      expect(option).toHaveTextContent(dictionary.variants.male);
    }
  });
});
