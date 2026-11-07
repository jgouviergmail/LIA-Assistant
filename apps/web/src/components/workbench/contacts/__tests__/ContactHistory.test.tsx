/**
 * What a contact and the person exchanged (ADR-369, lot 14): four lists a line of which opens in
 * its own tool, and sources that say why they have nothing. « I could not look » is never
 * « nothing found », and meetings nobody named an organiser for are never sorted by a guess.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, waitFor, within } from '@/__tests__/test-utils';
import type { WorkbenchContactHistory } from '@/lib/workbench/types';

const { api, i18n } = vi.hoisted(() => ({
  api: { get: vi.fn() },
  i18n: {
    t: (key: string, values?: Record<string, string | number>) =>
      values ? `${key}(${Object.values(values).join('|')})` : key,
    i18n: { language: 'en' },
  },
}));
vi.mock('@/i18n/client', () => ({ useTranslation: () => i18n }));
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 'owner', timezone: 'Europe/Paris' } }),
}));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: api,
}));

import { ContactHistory } from '../ContactHistory';

const word = (key: string) => `workbench.contacts.history.${key}`;

const MAIL = {
  id: 'm1',
  subject: 'The agenda',
  at: '2026-11-03T09:00:00Z',
};
const MEETING = {
  id: 'e1',
  title: 'Review',
  at: '2026-11-02T09:00:00Z',
  day: '2026-11-02',
  all_day: false,
  calendar_id: 'cal-1',
};

function history(overrides: Partial<WorkbenchContactHistory>): WorkbenchContactHistory {
  return {
    mail: 'used',
    received: [],
    sent: [],
    calendar: 'used',
    organized_by_them: [],
    organized_by_you: [],
    shared: [],
    meetings_window_days: 720,
    meetings_cut: false,
    ...overrides,
  };
}

function panel(addresses: readonly string[] = ['ana@example.org'], name = 'Ana Lima') {
  return renderWithProviders(<ContactHistory lng="en" name={name} addresses={addresses} />);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('ContactHistory — its two panels', () => {
  it('sets each panel’s title on a ground of its own', async () => {
    api.get.mockResolvedValue(history({}));
    panel();

    const mail = await screen.findByRole('region', { name: word('mail') });
    expect(within(mail).getByRole('heading', { level: 4 })).toHaveClass('bg-muted/60');
  });
});

describe('ContactHistory', () => {
  it('asks by the addresses it was given', async () => {
    api.get.mockResolvedValue(history({}));
    panel(['ana@example.org', 'ana@work.example']);

    await screen.findByRole('region', { name: word('title') });

    expect(api.get.mock.calls[0]?.[0]).toBe('/workbench/contacts/history');
    expect(api.get.mock.calls[0]?.[1]).toMatchObject({
      params: { address: ['ana@example.org', 'ana@work.example'] },
    });
  });

  it('asks nothing of a contact with no address', () => {
    panel([]);

    expect(api.get).not.toHaveBeenCalled();
    expect(screen.queryByRole('region', { name: word('title') })).toBeNull();
  });

  it('opens a received mail in the inbox, a sent one in the sent mail', async () => {
    api.get.mockResolvedValue(
      history({ received: [MAIL], sent: [{ ...MAIL, id: 'm2', subject: 'My answer' }] })
    );
    panel();

    const received = await screen.findByRole('link', { name: /The agenda/ });
    const sent = screen.getByRole('link', { name: /My answer/ });

    expect(received).toHaveAttribute(
      'href',
      '/en/dashboard/tools/mail?folder=system%3Ainbox&id=m1'
    );
    expect(sent).toHaveAttribute('href', '/en/dashboard/tools/mail?folder=system%3Asent&id=m2');
  });

  it('opens a meeting on its day, in its calendar', async () => {
    api.get.mockResolvedValue(history({ organized_by_them: [MEETING] }));
    panel();

    expect(await screen.findByRole('link', { name: /Review/ })).toHaveAttribute(
      'href',
      '/en/dashboard/tools/calendar?day=2026-11-02&cal=cal-1&event=e1'
    );
  });

  it('says a line that has no subject or title in the page’s own words', async () => {
    api.get.mockResolvedValue(
      history({
        received: [{ ...MAIL, subject: '' }],
        organized_by_them: [{ ...MEETING, title: '' }],
      })
    );
    panel();

    expect(await screen.findByText('workbench.mail.no_subject')).toBeInTheDocument();
    expect(screen.getByText('workbench.calendar.no_title')).toBeInTheDocument();
  });

  it('names the contact above what they organised', async () => {
    api.get.mockResolvedValue(history({ organized_by_them: [MEETING] }));
    panel();

    expect(await screen.findByText(`${word('by_them')}(Ana Lima)`)).toBeInTheDocument();
  });

  it('says « this contact » of one with no name', async () => {
    api.get.mockResolvedValue(history({}));
    panel(['ana@example.org'], '');

    expect(await screen.findByText(word('by_them_unnamed'))).toBeInTheDocument();
  });

  it('says a list found nothing, each in its words', async () => {
    api.get.mockResolvedValue(history({}));
    panel();

    expect(await screen.findByText(word('no_received'))).toBeInTheDocument();
    expect(screen.getByText(word('no_sent'))).toBeInTheDocument();
    expect(screen.getAllByText(word('no_meeting'))).toHaveLength(2);
  });

  it('says how far back the calendar was read', async () => {
    api.get.mockResolvedValue(history({}));
    panel();

    expect(await screen.findByText(`${word('window')}(24)`)).toBeInTheDocument();
  });

  it('says a window held more than was read', async () => {
    api.get.mockResolvedValue(history({ meetings_cut: true }));
    panel();

    expect(await screen.findByText(new RegExp(word('window_cut')))).toBeInTheDocument();
  });

  it('leaves out the column of a source nobody connected', async () => {
    api.get.mockResolvedValue(history({ mail: 'disabled', organized_by_them: [MEETING] }));
    panel();

    await screen.findByRole('link', { name: /Review/ });

    expect(screen.queryByRole('region', { name: word('mail') })).toBeNull();
    expect(screen.queryByText(word('no_received'))).toBeNull();
  });

  it('shows nothing where no source is connected', async () => {
    api.get.mockResolvedValue(history({ mail: 'disabled', calendar: 'disabled' }));
    panel();

    await waitFor(() => expect(api.get).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryByRole('region', { name: word('title') })).toBeNull());
  });

  it('never reads a mailbox that failed as an empty one', async () => {
    api.get.mockResolvedValue(history({ mail: 'unavailable' }));
    panel();

    const column = await screen.findByRole('region', { name: word('mail') });

    expect(within(column).getByText(word('mail_unavailable'))).toBeInTheDocument();
    expect(within(column).queryByText(word('no_received'))).toBeNull();
  });

  it('never reads a calendar that failed as an empty one', async () => {
    api.get.mockResolvedValue(history({ calendar: 'unavailable' }));
    panel();

    const column = await screen.findByRole('region', { name: word('meetings') });

    expect(within(column).getByText(word('calendar_unavailable'))).toBeInTheDocument();
    expect(within(column).queryByText(word('no_meeting'))).toBeNull();
  });

  it('keeps meetings nobody named an organiser for in one list, sorted by no guess', async () => {
    api.get.mockResolvedValue(history({ shared: [MEETING] }));
    panel();

    expect(await screen.findByText(word('shared'))).toBeInTheDocument();
    expect(screen.queryByText(word('by_you'))).toBeNull();
    expect(screen.queryByText(`${word('by_them')}(Ana Lima)`)).toBeNull();
  });

  it('keeps the two lists beside a shared one when organisers are known', async () => {
    api.get.mockResolvedValue(history({ shared: [MEETING], organized_by_you: [MEETING] }));
    panel();

    expect(await screen.findByText(word('by_you'))).toBeInTheDocument();
    expect(screen.getByText(word('shared'))).toBeInTheDocument();
  });

  it('says it could not read, and reads again on asking', async () => {
    api.get.mockRejectedValueOnce(new Error('down'));
    api.get.mockResolvedValueOnce(history({ received: [MAIL] }));
    const { user } = panel();

    await user.click(await screen.findByRole('button', { name: 'workbench.states.retry' }));

    expect(await screen.findByRole('link', { name: /The agenda/ })).toBeInTheDocument();
  });
});
