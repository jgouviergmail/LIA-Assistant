import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { createInstance } from 'i18next';
import { I18nextProvider } from 'react-i18next';
import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';
const { post, get, patch, location } = vi.hoisted(() => ({
  post: vi.fn(),
  get: vi.fn(),
  patch: vi.fn(),
  location: { search: '' },
}));
vi.mock('next/navigation', () => ({ useSearchParams: () => new URLSearchParams(location.search) }));
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
const message = {
  id: 'df63b582-413f-4fd4-9f63-df30d1d3a4a2',
  sender: 'Camille',
  display_name: 'Camille',
  identity_source: 'raw',
  identity_state: 'unresolved',
  relation_key: null,
  body: 'Rendez-vous demain',
  received_at: '2026-10-19T12:00:00Z',
  date_kind: 'received',
  origin: 'iphone',
};
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
  location.search = '';
  post.mockResolvedValue({
    items: [message],
    total: 1,
    revision: 1,
    as_of: '2026-10-19T13:00:00Z',
    next_cursor: null,
  });
  savedPreferences = { ...preferences };
  get.mockImplementation(async (path: string) =>
    path === '/sms/settings'
      ? { ...settings, preferences: savedPreferences }
      : path === `/sms/${message.id}`
        ? message
        : path === '/sms/senders'
          ? {
              items: [{ ...message, total: 1, latest_at: message.received_at }],
              total: 1,
              as_of: '2026-10-19T13:00:00Z',
              revision: 1,
              next_cursor: null,
            }
          : path === '/sms/tokens'
            ? { tokens: [], total: 0, as_of: '2026-10-19T00:00:00Z', next_cursor: null }
            : { blocks: [], total: 0, as_of: '2026-10-19T00:00:00Z', next_cursor: null }
  );
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

it.each(['en', 'fr'] as const)(
  'shows statistics and folds setup and management in %s',
  async language => {
    const copy = language === 'fr' ? fr : en;
    await open(language);
    expect(await screen.findByText(copy.sms.usage.replace('{{count}}', '2'))).toBeVisible();
    for (const title of [copy.sms.api, copy.sms.assistant, copy.sms.blocked, copy.sms.management]) {
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
  }
);

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
    expect(post.mock.calls.every(call => call[0] === '/sms/search')).toBe(true);
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
  'consults messages below statistics, open by default in %s',
  async language => {
    const copy = language === 'fr' ? fr : en;
    await open(language);
    await screen.findByText(message.display_name);
    const archive = screen
      .getByText(copy.sms.archive, { selector: 'summary span' })
      .closest('details');
    const statistics = screen
      .getByText(copy.healthMetrics.stats.title, { selector: 'summary span' })
      .closest('details');
    expect(archive).toHaveAttribute('open');
    expect(statistics?.nextElementSibling).toBe(archive);
    expect(within(archive!).getByRole('searchbox', { name: copy.sms.search })).toBeVisible();
    expect(screen.queryByRole('link', { name: copy.sms.archive })).not.toBeInTheDocument();
    unfold(message.display_name);
    expect(await screen.findByText(message.body)).toBeVisible();
    archive!.open = false;
    fireEvent(archive!, new Event('toggle'));
    expect(screen.queryByText(message.body)).not.toBeInTheDocument();
    unfold(copy.sms.archive);
    await screen.findByText(message.display_name);
    unfold(message.display_name);
    expect(await screen.findByText(message.body)).toBeVisible();
  }
);

it('preserves focused notification messages inside the settings archive', async () => {
  location.search = `section=sms&message=${message.id}`;
  await open('fr');
  await waitFor(() =>
    expect(get.mock.calls.some(call => call[0] === `/sms/${message.id}`)).toBe(true)
  );
  const focused = await screen.findByLabelText(fr.sms.title, { selector: 'div[tabindex="-1"]' });
  expect(within(focused).getByText(message.body)).toBeVisible();
  await waitFor(() => expect(focused).toHaveFocus());
});

it('does not read an invalid focused message id', async () => {
  location.search = 'section=sms&message=invalid-private-value';
  await open('en');
  expect(await screen.findByText(message.display_name)).toBeVisible();
  expect(get.mock.calls.some(call => call[0].includes('invalid-private-value'))).toBe(false);
});

it('erases one SMS without a visible reload: the sender stays open and takes the focus', async () => {
  // Owner report 2026-10-21: deleting an SMS reloaded the archive in view —
  // the lists emptied to « loading », open senders closed and the focus fell
  // to the page. The views now re-read in place.
  const command = '6b0f7f0c-6f0b-4c8c-9a3f-1d5d2c7a0e11';
  const freshPage = Promise.withResolvers<unknown>();
  const freshSenders = Promise.withResolvers<unknown>();
  let erased = false;
  post.mockImplementation(async (path: string) => {
    if (path === '/sms/commands')
      return {
        command_id: command,
        operation_id: 'sms_messages.delete',
        content_digest: 'a'.repeat(64),
        before: {
          sms_messages_to_delete: {
            count: 1,
            all_messages: false,
            sender_id: null,
            from_ts: null,
            to_ts: null,
            message_ids: [message.id],
          },
        },
        after: {},
        expires_at: new Date(Date.now() + 600_000).toISOString(),
      };
    if (path === `/sms/commands/${command}/confirm`) {
      erased = true;
      return { outcome: { success: true, committed: true, phase: 'committed' }, secret: null };
    }
    if (erased) return freshPage.promise;
    return {
      items: [message],
      total: 1,
      revision: 1,
      as_of: message.received_at,
      next_cursor: null,
    };
  });
  const served = get.getMockImplementation();
  get.mockImplementation(async (path: string) =>
    erased && path === '/sms/senders' ? freshSenders.promise : served?.(path)
  );
  await open('fr');
  await screen.findByText(message.display_name);
  const sender = unfold(message.display_name);
  const erase = await within(sender).findByRole('button', {
    name: new RegExp(fr.sms.erase_message),
  });
  erase.focus();
  fireEvent.click(erase);
  await waitFor(() => expect(erased).toBe(true));

  // While the source is re-read, what was on screen stays on screen.
  expect(sender.isConnected).toBe(true);
  expect(sender).toHaveAttribute('open');
  expect(within(sender).getByText(message.body)).toBeVisible();
  expect(within(sender).queryByRole('status')).toBeNull();

  await act(async () => {
    freshSenders.resolve({
      items: [{ ...message, total: 1, latest_at: message.received_at }],
      total: 1,
      as_of: '2026-10-19T13:00:00Z',
      revision: 2,
      next_cursor: null,
    });
    freshPage.resolve({
      items: [],
      total: 0,
      revision: 2,
      as_of: message.received_at,
      next_cursor: null,
    });
  });
  await waitFor(() => expect(within(sender).queryByText(message.body)).not.toBeInTheDocument());
  // The very same sender element, still open: nothing was unmounted.
  expect(sender.isConnected).toBe(true);
  expect(sender).toHaveAttribute('open');
  await waitFor(() => expect(sender.querySelector('summary')).toHaveFocus());
});
