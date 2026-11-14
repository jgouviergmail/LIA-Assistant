/**
 * The mark under a note the person added to the answer in progress (ADR-385).
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import { createInstance } from 'i18next';

import { TurnNoteMark } from '../TurnNoteMark';
import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';

const i18n = createInstance();
await i18n.init({
  lng: 'en',
  interpolation: { escapeValue: false },
  resources: { en: { translation: en }, fr: { translation: fr } },
});
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: i18n.t, i18n }) }));

describe('TurnNoteMark', () => {
  it('says the message was added to the answer in progress', async () => {
    await i18n.changeLanguage('en');
    render(<TurnNoteMark metadata={{ turn_note: true }} />);
    const mark = screen.getByRole('img', { name: 'Added to the answer in progress' });
    expect(mark).toHaveAttribute('title', 'Added to the answer in progress');
  });

  it('says it in French too', async () => {
    await i18n.changeLanguage('fr');
    render(<TurnNoteMark metadata={{ turn_note: true }} />);
    expect(screen.getByRole('img', { name: 'Ajouté à la réponse en cours' })).toBeInTheDocument();
    await i18n.changeLanguage('en');
  });

  it.each([undefined, {}, { turn_note: false }, { turn_note: 'true' }])(
    'marks nothing else (%o)',
    metadata => {
      const { container } = render(<TurnNoteMark metadata={metadata} />);
      expect(container).toBeEmptyDOMElement();
    }
  );
});
