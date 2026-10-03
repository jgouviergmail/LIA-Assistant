import { fireEvent, screen } from '@testing-library/react';
import { createInstance } from 'i18next';
import { I18nextProvider, initReactI18next } from 'react-i18next';
import { describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/__tests__/test-utils';
import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';
import { GeneratedDocumentPreview } from '../GeneratedDocumentPreview';

vi.mock('react-i18next', async importOriginal => importOriginal<typeof import('react-i18next')>());

describe('localized PDF preview controls', () => {
  it.each([
    { language: 'en', firstPage: 'First page of source.pdf', retry: 'Retry' },
    { language: 'fr', firstPage: 'Première page de source.pdf', retry: 'Réessayer' },
  ])('names the source and recovery in $language using real resources', async sample => {
    const i18n = createInstance();
    await i18n.use(initReactI18next).init({
      lng: sample.language,
      fallbackLng: false,
      resources: { en: { translation: en }, fr: { translation: fr } },
      interpolation: { escapeValue: false },
    });
    renderWithProviders(
      <I18nextProvider i18n={i18n}>
        <GeneratedDocumentPreview
          url="/api/v1/attachments/00000000-0000-4000-8000-00000000d001"
          docType="pdf"
          filename="source.pdf"
        />
      </I18nextProvider>
    );
    const source = screen.getByRole('button', { name: sample.firstPage });
    source.focus();
    fireEvent.error(screen.getByRole('img', { name: sample.firstPage }));
    const recovery = screen.getByRole('button', { name: sample.retry });
    expect(recovery).toHaveFocus();
    fireEvent.click(recovery);
    expect(screen.getByRole('button', { name: sample.firstPage })).toHaveFocus();
  });
});
