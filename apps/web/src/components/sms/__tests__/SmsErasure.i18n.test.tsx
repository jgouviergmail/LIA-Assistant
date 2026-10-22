import { fireEvent, render, screen } from '@testing-library/react';
import { createInstance } from 'i18next';
import { I18nextProvider } from 'react-i18next';
import { expect, it, vi } from 'vitest';
import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';
import { SmsEraseButton, SmsErasureProvider } from '../SmsErasure';

vi.mock(
  'react-i18next',
  async importOriginal => await importOriginal<typeof import('react-i18next')>()
);

it.each(['en', 'fr'] as const)(
  'names the destructive control in %s and only requests review',
  async language => {
    const i18n = createInstance();
    await i18n.init({
      lng: language,
      resources: { en: { translation: en }, fr: { translation: fr } },
      interpolation: { escapeValue: false },
    });
    const request = vi.fn();
    render(
      <I18nextProvider i18n={i18n}>
        <SmsErasureProvider value={{ busy: false, request }}>
          <SmsEraseButton kind="sender" target="Alice" scope={() => ({ sender_id: 'source-id' })} />
        </SmsErasureProvider>
      </I18nextProvider>
    );
    const copy = language === 'fr' ? fr : en;
    fireEvent.click(screen.getByRole('button', { name: `${copy.sms.erase_sender} · Alice` }));
    expect(request).toHaveBeenCalledExactlyOnceWith({ sender_id: 'source-id' });
  }
);

it.each(['en', 'fr'] as const)('names the icon-only single SMS action in %s', async language => {
  const i18n = createInstance();
  await i18n.init({
    lng: language,
    resources: { en: { translation: en }, fr: { translation: fr } },
  });
  render(
    <I18nextProvider i18n={i18n}>
      <SmsErasureProvider value={{ busy: false, request: vi.fn() }}>
        <SmsEraseButton kind="message" target="Alice" scope={() => ({ message_ids: ['id'] })} />
      </SmsErasureProvider>
    </I18nextProvider>
  );
  const copy = language === 'fr' ? fr : en;
  const button = screen.getByRole('button', { name: `${copy.sms.erase_message} · Alice` });
  expect(button).toHaveTextContent(/^$/);
  expect(button).toHaveAttribute('title', copy.sms.erase_message);
});
