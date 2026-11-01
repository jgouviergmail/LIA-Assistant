import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { createInstance } from 'i18next';
import { I18nextProvider } from 'react-i18next';
import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';
const { post, get, patch } = vi.hoisted(() => ({
  post: vi.fn(),
  get: vi.fn(),
  patch: vi.fn(),
}));
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
  default: { post, get, patch },
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
let savedPreferences = { ...preferences };
beforeEach(() => {
  vi.clearAllMocks();
  savedPreferences = { ...preferences };
  // The settings read how SMS reach LIA, and nothing else.
  get.mockImplementation(async (path: string) => {
    if (path === '/sms/settings') return { ...settings, preferences: savedPreferences };
    if (path === '/sms/tokens')
      return { tokens: [], total: 0, as_of: '2026-10-19T00:00:00Z', next_cursor: null };
    throw new Error(`unexpected read: ${path}`);
  });
  patch.mockImplementation(
    async (_path: string, change: { field: keyof typeof preferences; value: boolean }) => {
      savedPreferences = { ...savedPreferences, [change.field]: change.value };
      return savedPreferences;
    }
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
function unfold(title: string) {
  const details = screen.getByText(title, { selector: 'summary span' }).closest('details');
  if (!details) throw new Error(`Missing disclosure: ${title}`);
  details.open = true;
  fireEvent(details, new Event('toggle'));
  return details;
}

it.each(['en', 'fr'] as const)('shows statistics and folds the setup in %s', async language => {
  const copy = language === 'fr' ? fr : en;
  await open(language);
  expect(await screen.findByText(copy.sms.usage.replace('{{count}}', '2'))).toBeVisible();
  for (const title of [copy.sms.api, copy.sms.assistant]) {
    expect(
      screen.getByText(title, { selector: 'summary span' }).closest('details')
    ).not.toHaveAttribute('open');
  }
  // Folded, the only switch left is the page's own push switch, at its head.
  expect(screen.getAllByRole('switch')).toEqual([
    screen.getByRole('switch', { name: copy.sms.push }),
  ]);
  expect(screen.queryByRole('button', { name: copy.sms.create_token })).not.toBeInTheDocument();
  const api = unfold(copy.sms.api);
  const assistant = unfold(copy.sms.assistant);
  expect(api).toHaveAttribute('open');
  expect(assistant).toHaveAttribute('open');
  expect(screen.getByRole('button', { name: copy.sms.create_token })).toBeVisible();
  expect(screen.getByRole('switch', { name: copy.sms.assistant })).toBeVisible();
});

it.each(['ingestion_enabled', 'assistant_enabled', 'push_enabled'] as const)(
  'saves %s directly without an approval dialog or unrelated preference writes',
  async field => {
    await open('fr');
    await screen.findByText(fr.sms.usage.replace('{{count}}', '2'));
    unfold(fr.sms.assistant);
    const labels = {
      ingestion_enabled: fr.sms.ingestion,
      assistant_enabled: fr.sms.assistant,
      push_enabled: fr.sms.push,
    };
    const toggle = screen.getByRole('switch', { name: labels[field] });
    toggle.focus();
    fireEvent.click(toggle);
    await waitFor(() =>
      expect(toggle).toHaveAttribute('aria-checked', String(!preferences[field]))
    );
    expect(patch).toHaveBeenCalledExactlyOnceWith(
      '/sms/preferences',
      { field, value: !preferences[field] },
      undefined
    );
    expect(post).not.toHaveBeenCalled();
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(toggle).toHaveFocus();
    expect(screen.queryByRole('link', { name: fr.sms.archive })).not.toBeInTheDocument();
  }
);

it.each(['en', 'fr'] as const)(
  'puts the immediate push switch at the head of the page, unfolded, in %s',
  async language => {
    const copy = language === 'fr' ? fr : en;
    await open(language);
    const push = await screen.findByRole('switch', { name: copy.sms.push });
    // Like « enable proactive notifications »: never inside a fold, and
    // above every block of the page.
    expect(push.closest('details')).toBeNull();
    expect(push).toHaveAccessibleDescription(copy.sms.push_hint);
    const firstFold = document.querySelector('details');
    if (!firstFold) throw new Error('the page has no fold');
    expect(push.compareDocumentPosition(firstFold) & Node.DOCUMENT_POSITION_FOLLOWING).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING
    );
    // The assistant fold no longer repeats it.
    const assistant = unfold(copy.sms.assistant);
    expect(within(assistant).queryByRole('switch', { name: copy.sms.push })).toBeNull();
  }
);

it('keeps the previous value and allows retry when saving a parameter fails', async () => {
  patch.mockRejectedValueOnce(new Error('network'));
  await open('en');
  await screen.findByText(en.sms.usage.replace('{{count}}', '2'));
  unfold(en.sms.assistant);
  const toggle = screen.getByRole('switch', { name: en.sms.assistant });
  toggle.focus();
  fireEvent.click(toggle);
  expect(await screen.findByRole('alert')).toHaveTextContent(en.sms.unavailable);
  expect(toggle).toHaveAttribute('aria-checked', 'false');
  expect(toggle).toHaveFocus();
  await waitFor(() => expect(toggle).toHaveAttribute('aria-disabled', 'false'));
  fireEvent.click(toggle);
  await waitFor(() => expect(toggle).toHaveAttribute('aria-checked', 'true'));
  expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
});

it.each(['en', 'fr'] as const)(
  'leaves the SMS themselves to their own page in %s: no archive, no blocked senders, no erasure',
  async language => {
    const copy = language === 'fr' ? fr : en;
    await open(language);
    await screen.findByText(copy.sms.usage.replace('{{count}}', '2'));

    for (const title of [copy.sms.archive, copy.sms.blocked, copy.sms.management]) {
      expect(screen.queryByText(title, { selector: 'summary span' })).toBeNull();
    }
    expect(screen.queryByRole('searchbox')).toBeNull();
    expect(new Set(get.mock.calls.map(call => call[0]))).toEqual(
      new Set(['/sms/settings', '/sms/tokens'])
    );
    expect(post).not.toHaveBeenCalled();
    expect(screen.queryByRole('alert')).toBeNull();
  }
);
