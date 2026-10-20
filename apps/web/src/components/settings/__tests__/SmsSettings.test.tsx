import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { createInstance } from 'i18next';
import { I18nextProvider } from 'react-i18next';
import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';
const { post, get } = vi.hoisted(() => ({ post: vi.fn(), get: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 'owner', timezone: 'Europe/Paris' } }),
}));
vi.mock('@/hooks/useAppConfig', () => ({
  useAppConfig: () => ({
    config: { features: { sms_enabled: true }, capabilities: { sms: { enabled: true } } },
  }),
}));
vi.mock('@/i18n/client', async () => {
  const real = await import('react-i18next');
  return { useTranslation: () => real.useTranslation() };
});
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { post, get },
}));
vi.mock(
  'react-i18next',
  async importOriginal => await importOriginal<typeof import('react-i18next')>()
);
import { SmsSettings } from '../SmsSettings';
const preferences = { ingestion_enabled: true, assistant_enabled: false, push_enabled: true };
const settings = {
  preferences,
  usage: {
    message_count: 2,
    receipt_count: 2,
    logical_bytes: 1024,
    max_logical_bytes: 2048,
    max_receipts: 100,
    last_received_at: null,
  },
  device_deliveries: { sent: 1, pending: 0, sending: 0, failed: 0, unknown: 0, cancelled: 0 },
};
const proposal = {
  command_id: 'df63b582-413f-4fd4-9f63-df30d1d3a4a2',
  operation_id: 'sms_preferences.update',
  content_digest: 'a'.repeat(64),
  before: { sms_preferences: preferences },
  after: { sms_preferences: { ...preferences, assistant_enabled: true } },
  expires_at: '2099-01-01T00:00:00Z',
};
beforeEach(() => {
  vi.clearAllMocks();
  get.mockImplementation(async (path: string) =>
    path === '/sms/settings'
      ? settings
      : path === '/sms/tokens'
        ? { tokens: [], total: 0, as_of: '2026-10-19T00:00:00Z', next_cursor: null }
        : { blocks: [], total: 0, as_of: '2026-10-19T00:00:00Z', next_cursor: null }
  );
});
async function open(language: 'en' | 'fr') {
  const i18n = createInstance();
  await i18n.init({
    lng: language,
    resources: { en: { translation: en }, fr: { translation: fr } },
    interpolation: { escapeValue: false },
  });
  return render(
    <I18nextProvider i18n={i18n}>
      <SmsSettings lng={language} />
    </I18nextProvider>
  );
}
it.each(['en', 'fr'] as const)(
  'requires a reviewed confirmation for assistant consent in %s',
  async language => {
    const copy = language === 'fr' ? fr : en;
    post.mockResolvedValueOnce(proposal).mockResolvedValueOnce({
      outcome: { success: true, phase: 'committed', committed: true },
      secret: null,
    });
    await open(language);
    const toggle = await screen.findByRole('switch', { name: copy.sms.assistant });
    expect(toggle).toHaveAttribute('aria-checked', 'false');
    fireEvent.click(toggle);
    await screen.findByRole('alertdialog');
    expect(post).toHaveBeenCalledTimes(1);
    expect(post).toHaveBeenCalledWith(
      '/sms/commands',
      {
        operation_id: 'sms_preferences.update',
        payload: { ...preferences, assistant_enabled: true },
      },
      undefined
    );
    fireEvent.click(screen.getByRole('button', { name: copy.sms.confirm }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    await act(async () => {});
    expect(screen.getByRole('link', { name: copy.sms.archive })).toHaveAttribute(
      'href',
      `/${language}/dashboard/sms`
    );
  }
);
