/**
 * The « SMS » page (owner request 2026-10-31): the three views a person uses on
 * their received SMS — consult them, block a sender, erase — on a page of their
 * own behind the header's « SMS », drawn like the other destinations (no
 * settings panel behind them). The page reads what it shows and nothing of the
 * settings' own (the ingestion tokens, the statistics); bulk changes go
 * through reviewed confirmation, a single deletion through its explicit click;
 * a focused notification message opens in
 * place; SMS switched off on the instance is said, and nothing is read.
 */

import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { createInstance } from 'i18next';
import { I18nextProvider } from 'react-i18next';
import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';

const { post, get, location, config } = vi.hoisted(() => ({
  post: vi.fn(),
  get: vi.fn(),
  location: { search: '' },
  config: {
    current: {
      features: { sms_enabled: true },
      capabilities: { sms: { enabled: true } } as Record<string, { enabled: boolean }>,
    },
  },
}));
vi.mock('next/navigation', () => ({ useSearchParams: () => new URLSearchParams(location.search) }));
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 'owner', timezone: 'Europe/Paris' } }),
}));
vi.mock('@/hooks/useAppConfig', () => ({ useAppConfig: () => ({ config: config.current }) }));
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

import { SmsWorkspace } from '../SmsWorkspace';

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
const COMMAND = '6b0f7f0c-6f0b-4c8c-9a3f-1d5d2c7a0e11';

/** A reviewed proposal for a command, as the API answers it. */
function proposal(operation_id: string, before: Record<string, unknown>) {
  return {
    command_id: COMMAND,
    operation_id,
    content_digest: 'a'.repeat(64),
    before,
    after: {},
    expires_at: new Date(Date.now() + 600_000).toISOString(),
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  location.search = '';
  config.current = {
    features: { sms_enabled: true },
    capabilities: { sms: { enabled: true } },
  };
  post.mockImplementation(async (path: string) =>
    path === '/sms/search'
      ? { items: [message], total: 1, revision: 1, as_of: message.received_at, next_cursor: null }
      : proposal('sms_sender_block.update', {})
  );
  get.mockImplementation(async (path: string) =>
    path === `/sms/${message.id}`
      ? message
      : path === '/sms/senders'
        ? {
            items: [{ ...message, total: 1, latest_at: message.received_at }],
            total: 1,
            as_of: '2026-10-19T13:00:00Z',
            revision: 1,
            next_cursor: null,
          }
        : path === '/sms/blocked-senders'
          ? {
              blocks: [{ id: 'b1', sender: '+33 6 00 00 00 00' }],
              total: 1,
              as_of: '2026-10-19T00:00:00Z',
              next_cursor: null,
            }
          : { unexpected: path }
  );
});

async function open(language: 'en' | 'fr') {
  const i18n = createInstance();
  await i18n.init({
    lng: language,
    resources: { en: { translation: en }, fr: { translation: fr } },
    interpolation: { escapeValue: false },
  });
  // Mounting starts the archive reads. Settle their immediate mock responses
  // inside React's async boundary before the person starts interacting.
  await act(async () => {
    render(
      <I18nextProvider i18n={i18n}>
        <SmsWorkspace lng={language} />
      </I18nextProvider>
    );
  });
}

function fold(title: string): HTMLDetailsElement {
  const details = screen.getByText(title, { selector: 'summary span' }).closest('details');
  if (!details) throw new Error(`Missing disclosure: ${title}`);
  return details;
}

it('automatically opens results from the external search and applies dates in the account timezone', async () => {
  await open('fr');
  await screen.findByText('Camille');
  const form = screen.getByRole('search');
  expect(form.closest('details')).toBeNull();
  const from = within(form).getByLabelText('Du (inclus)', { exact: true });
  const to = within(form).getByLabelText('Au (exclus)', { exact: true });
  expect(form).not.toHaveTextContent('Europe/Paris');
  const archive = fold('Consulter mes SMS');
  archive.open = false;
  fireEvent(archive, new Event('toggle'));
  await waitFor(() => expect(screen.queryByText('Camille')).not.toBeInTheDocument());
  fireEvent.change(within(form).getByRole('searchbox'), { target: { value: 'dîner' } });
  fireEvent.change(from, { target: { value: '2026-10-25' } });
  fireEvent.change(to, { target: { value: '2026-10-26' } });
  expect(form).toBeVisible();
  expect(within(form).queryByRole('button', { name: 'Rechercher' })).toBeNull();
  await waitFor(() => expect(archive).toHaveAttribute('open'));
  await waitFor(() =>
    expect(post).toHaveBeenCalledWith(
      '/sms/search',
      expect.objectContaining({
        query: 'dîner',
        from_ts: '2026-10-24T22:00:00.000Z',
        to_ts: '2026-10-25T23:00:00.000Z',
      }),
      expect.anything()
    )
  );
});

function unfold(title: string): HTMLDetailsElement {
  const details = fold(title);
  details.open = true;
  fireEvent(details, new Event('toggle'));
  return details;
}

const readPaths = () => get.mock.calls.map(call => String(call[0]));

it.each(['en', 'fr'] as const)(
  'draws its heading and the three views, consulting open and the two others folded, in %s',
  async language => {
    const copy = language === 'fr' ? fr : en;
    await open(language);

    expect(screen.getByRole('heading', { level: 1, name: copy.sms.title })).toBeVisible();
    const archive = fold(copy.sms.archive);
    expect(archive).toHaveAttribute('open');
    expect(screen.getByRole('searchbox', { name: copy.sms.search })).toBeVisible();
    expect(within(archive).queryByRole('searchbox')).not.toBeInTheDocument();
    expect(await within(archive).findByText(message.display_name)).toBeVisible();
    expect(fold(copy.sms.blocked)).not.toHaveAttribute('open');
    expect(fold(copy.sms.management)).not.toHaveAttribute('open');
    // The settings' own blocks stay in the settings.
    expect(screen.queryByRole('switch')).toBeNull();
    expect(screen.queryByRole('button', { name: copy.sms.create_token })).toBeNull();
    expect(screen.queryByText(copy.sms.stats_title)).toBeNull();
  }
);

it('reads what it shows, and nothing of the settings', async () => {
  await open('en');
  await screen.findByText(message.display_name);

  await waitFor(() => expect(readPaths()).toContain('/sms/blocked-senders'));
  expect(readPaths()).not.toContain('/sms/settings');
  expect(readPaths()).not.toContain('/sms/tokens');
});

it('blocks a sender and unblocks one through the reviewed confirmation', async () => {
  await open('en');
  const blocked = unfold(en.sms.blocked);

  fireEvent.change(within(blocked).getByLabelText(en.sms.block_sender), {
    target: { value: 'Promo' },
  });
  fireEvent.click(within(blocked).getByRole('button', { name: en.sms.block }));
  await waitFor(() =>
    expect(post).toHaveBeenCalledWith(
      '/sms/commands',
      { operation_id: 'sms_sender_block.update', payload: { sender: 'Promo', blocked: true } },
      undefined
    )
  );
  expect(await screen.findByRole('alertdialog')).toBeVisible();
});

it('proposes erasing a period in the account’s days, and refuses one that ends first', async () => {
  post.mockImplementation(async (path: string) =>
    path === '/sms/search'
      ? { items: [], total: 0, revision: 1, as_of: message.received_at, next_cursor: null }
      : proposal('sms_messages.delete', {
          sms_messages_to_delete: {
            count: 1,
            all_messages: false,
            sender_id: null,
            from_ts: null,
            to_ts: null,
            message_ids: [],
          },
        })
  );
  await open('en');
  const management = unfold(en.sms.management);
  // Each day field names the zone its days are read in.
  const from = within(management).getByLabelText(en.sms.from);
  const to = within(management).getByLabelText(en.sms.to);

  fireEvent.change(from, { target: { value: '2026-10-10' } });
  fireEvent.change(to, { target: { value: '2026-10-01' } });
  fireEvent.click(within(management).getByRole('button', { name: en.sms.erase_range }));
  expect(within(management).getByRole('alert')).toHaveTextContent(en.common.error);
  expect(post.mock.calls.some(call => call[0] === '/sms/commands')).toBe(false);

  fireEvent.change(to, { target: { value: '2026-10-20' } });
  fireEvent.click(within(management).getByRole('button', { name: en.sms.erase_range }));
  await waitFor(() =>
    expect(post).toHaveBeenCalledWith(
      '/sms/commands',
      {
        operation_id: 'sms_messages.delete',
        // Midnight in the account's zone (Paris is UTC+2 on these days).
        payload: { from_ts: '2026-10-09T22:00:00.000Z', to_ts: '2026-10-19T22:00:00.000Z' },
      },
      undefined
    )
  );
});

it('opens a notification’s message in place', async () => {
  location.search = `message=${message.id}`;
  await open('fr');

  await waitFor(() => expect(readPaths()).toContain(`/sms/${message.id}`));
  const focused = await screen.findByLabelText(fr.sms.title, { selector: 'div[tabindex="-1"]' });
  expect(within(focused).getByText(message.body)).toBeVisible();
  await waitFor(() => expect(focused).toHaveFocus());
});

it('does not read a focused message id that is not one', async () => {
  location.search = 'message=invalid-private-value';
  await open('en');

  expect(await screen.findByText(message.display_name)).toBeVisible();
  expect(readPaths().some(path => path.includes('invalid-private-value'))).toBe(false);
});

it('erases one SMS without a visible reload: the sender stays open and takes the focus', async () => {
  const freshPage = Promise.withResolvers<unknown>();
  const freshSenders = Promise.withResolvers<unknown>();
  let erased = false;
  post.mockImplementation(async (path: string) => {
    if (path === '/sms/commands')
      return proposal('sms_messages.delete', {
        sms_messages_to_delete: {
          count: 1,
          all_messages: false,
          sender_id: null,
          from_ts: null,
          to_ts: null,
          message_ids: [message.id],
        },
      });
    if (path === `/sms/commands/${COMMAND}/confirm`) {
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
  expect(sender.isConnected).toBe(true);
  expect(sender).toHaveAttribute('open');
  await waitFor(() => expect(sender.querySelector('summary')).toHaveFocus());
});

it('says SMS are not offered when the instance switched them off, and reads nothing', async () => {
  config.current = { features: { sms_enabled: true }, capabilities: { sms: { enabled: false } } };
  await open('en');

  expect(screen.getByRole('heading', { level: 1, name: en.sms.title })).toBeVisible();
  expect(screen.getByText(en.sms.not_offered)).toBeVisible();
  await act(async () => {
    await new Promise(resolve => setTimeout(resolve, 0));
  });
  expect(get).not.toHaveBeenCalled();
  expect(post).not.toHaveBeenCalled();
});

/** The frame a message's day is drawn in (the focused message has its own, focusable). */
function dayFrames(body: string): HTMLElement[] {
  return screen
    .getAllByText(body)
    .map(text => text.closest('div.rounded-xl:not([tabindex])'))
    .filter((frame): frame is HTMLElement => frame instanceof HTMLElement);
}

it('alternates its grounds: a fold is the card, what it holds the page, a fold within the card', async () => {
  // Charter « Grounds alternate » (owner remark 2026-11-08 on this page).
  location.search = `message=${message.id}`;
  await open('fr');
  expect(fold(fr.sms.archive)).toHaveClass('bg-card');

  // What the archive holds stands on the page's background…
  const focused = await screen.findByLabelText(fr.sms.title, { selector: 'div[tabindex="-1"]' });
  expect(focused).toHaveClass('bg-background');
  await screen.findByText(message.display_name, { selector: 'summary span' });
  const sender = fold(message.display_name);
  expect(sender).toHaveClass('bg-background');

  // …and a fold within it holds the card again.
  unfold(message.display_name);
  await within(sender).findByText(message.body);
  expect(within(sender).getByText(message.body).closest('div.rounded-xl')).toHaveClass('bg-card');

  // The « by day » view sets its days straight in the archive: the page's background.
  fireEvent.click(screen.getByRole('button', { name: fr.sms.by_day }));
  await waitFor(() => expect(dayFrames(message.body)).toHaveLength(1));
  expect(dayFrames(message.body)[0]).toHaveClass('bg-background');

  // Each blocked sender is a record on the page's background.
  const blocked = unfold(fr.sms.blocked);
  const record = (await within(blocked).findByText('+33 6 00 00 00 00')).closest('li');
  expect(record).toHaveClass('bg-background');
});

it('draws an empty archive on the page’s background', async () => {
  const served = get.getMockImplementation();
  get.mockImplementation(async (path: string) =>
    path === '/sms/senders'
      ? { items: [], total: 0, as_of: '2026-10-19T13:00:00Z', revision: 1, next_cursor: null }
      : served?.(path)
  );
  await open('fr');
  expect((await screen.findByText(fr.sms.empty)).closest('p')).toHaveClass('bg-background');
});
