/**
 * What a contact and the person exchanged (ADR-369, lot 14): four lists a line of which opens in
 * its own tool, and sources that say why they have nothing. « I could not look » is never
 * « nothing found », and meetings nobody named an organiser for are never sorted by a guess.
 * Since 2026-11-07 the contact's numbers are asked too: the calls LIA placed open in the calls
 * list, the texts they sent on the SMS page, and a contact with numbers alone has exchanges.
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
    telephony: 'not_requested',
    calls: [],
    calls_window: 500,
    calls_cut: false,
    sms: 'not_requested',
    texts: [],
    texts_window: 2000,
    texts_cut: false,
    ...overrides,
  };
}

const CALL = {
  id: 'c1',
  at: '2026-11-04T10:00:00Z',
  status: 'completed' as const,
  outcome: 'objective_met' as const,
  seconds: 93.5,
  purpose: 'Move the appointment',
};
const TEXT = {
  id: 't1',
  at: '2026-11-05T08:00:00Z',
  excerpt: 'Call me back',
  truncated: false,
};

function panel(
  addresses: readonly string[] = ['ana@example.org'],
  name = 'Ana Lima',
  phones: readonly string[] = []
) {
  return renderWithProviders(
    <ContactHistory lng="en" name={name} addresses={addresses} phones={phones} />
  );
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

  it('asks nothing of a contact with neither address nor number', () => {
    panel([]);

    expect(api.get).not.toHaveBeenCalled();
    expect(screen.queryByRole('region', { name: word('title') })).toBeNull();
  });

  it('asks by the numbers it was given, a contact with numbers alone included', async () => {
    api.get.mockResolvedValue(
      history({ mail: 'not_requested', calendar: 'not_requested', telephony: 'used' })
    );
    panel([], 'Ana Lima', ['06 12 34 56 78', '+33 1 40 00 00 00']);

    await screen.findByRole('region', { name: word('calls') });

    expect(api.get.mock.calls[0]?.[1]).toMatchObject({
      params: { phone: ['06 12 34 56 78', '+33 1 40 00 00 00'] },
    });
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

  it('says beside a mail what happened next in its conversation (ADR-379)', async () => {
    api.get.mockResolvedValue(
      history({
        received: [
          { ...MAIL, reply: 'answered' },
          { ...MAIL, id: 'm3', subject: 'Still open' },
        ],
        sent: [{ ...MAIL, id: 'm2', subject: 'My question', reply: 'reply_received' }],
      })
    );
    panel();

    const answered = await screen.findByRole('link', { name: /The agenda/ });
    expect(within(answered).getByText('workbench.mail.answered')).toBeInTheDocument();
    const replied = screen.getByRole('link', { name: /My question/ });
    expect(within(replied).getByText('workbench.mail.reply_received')).toBeInTheDocument();
    const open = screen.getByRole('link', { name: /Still open/ });
    expect(within(open).queryByText(/workbench\.mail\.(answered|reply_received)/)).toBeNull();
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

  it('opens a call LIA placed in the calls list, saying how it went', async () => {
    api.get.mockResolvedValue(history({ telephony: 'used', calls: [CALL] }));
    panel();

    const line = await screen.findByRole('link', { name: /Move the appointment/ });

    expect(line).toHaveAttribute('href', '/en/dashboard/settings?section=telephony-calls&call=c1');
    expect(line).toHaveTextContent('settings.telephony.calls.outcome.objective_met');
  });

  it('says how a call with no outcome ended, and one with no purpose in its own words', async () => {
    api.get.mockResolvedValue(
      history({
        telephony: 'used',
        calls: [{ ...CALL, outcome: null, status: 'no_answer', purpose: '' }],
      })
    );
    panel();

    const line = await screen.findByRole('link', { name: new RegExp(word('call_no_purpose')) });

    expect(line).toHaveTextContent('settings.telephony.calls.status.no_answer');
  });

  it('opens a text on the SMS page, showing how it begins', async () => {
    api.get.mockResolvedValue(
      history({
        sms: 'used',
        texts: [TEXT, { ...TEXT, id: 't2', excerpt: 'Long', truncated: true }],
      })
    );
    panel();

    const line = await screen.findByRole('link', { name: /Call me back/ });

    expect(line).toHaveAttribute('href', '/en/dashboard/sms?message=t1');
    expect(screen.getByRole('link', { name: /Long…/ })).toHaveAttribute(
      'href',
      '/en/dashboard/sms?message=t2'
    );
  });

  it('says a phone record found nothing, each in its words', async () => {
    api.get.mockResolvedValue(history({ telephony: 'used', sms: 'used' }));
    panel();

    expect(await screen.findByText(word('no_call'))).toBeInTheDocument();
    expect(screen.getByText(word('no_text'))).toBeInTheDocument();
  });

  it('never reads a phone record that failed as an empty one', async () => {
    api.get.mockResolvedValue(history({ telephony: 'unavailable', sms: 'unavailable' }));
    panel();

    const calls = await screen.findByRole('region', { name: word('calls') });
    const texts = screen.getByRole('region', { name: word('texts') });

    expect(within(calls).getByText(word('calls_unavailable'))).toBeInTheDocument();
    expect(within(calls).queryByText(word('no_call'))).toBeNull();
    expect(within(texts).getByText(word('texts_unavailable'))).toBeInTheDocument();
    expect(within(texts).queryByText(word('no_text'))).toBeNull();
  });

  it('says how far it read when its bound hid older calls or senders', async () => {
    api.get.mockResolvedValue(
      history({ telephony: 'used', calls_cut: true, sms: 'used', texts_cut: true })
    );
    panel();

    expect(await screen.findByText(`${word('calls_cut')}(500)`)).toBeInTheDocument();
    expect(screen.getByText(`${word('texts_cut')}(2,000)`)).toBeInTheDocument();
  });

  it('claims no cut of a whole read', async () => {
    api.get.mockResolvedValue(history({ telephony: 'used', sms: 'used' }));
    panel();

    await screen.findByText(word('no_call'));

    expect(screen.queryByText(new RegExp(word('calls_cut')))).toBeNull();
    expect(screen.queryByText(new RegExp(word('texts_cut')))).toBeNull();
  });

  it('leaves out a phone record nobody asked or nothing feeds', async () => {
    api.get.mockResolvedValue(history({ telephony: 'disabled', sms: 'not_requested' }));
    panel();

    await screen.findByRole('region', { name: word('mail') });

    expect(screen.queryByRole('region', { name: word('calls') })).toBeNull();
    expect(screen.queryByRole('region', { name: word('texts') })).toBeNull();
  });

  it('shows nothing where no source has anything to say', async () => {
    api.get.mockResolvedValue(
      history({
        mail: 'not_requested',
        calendar: 'not_requested',
        telephony: 'disabled',
        sms: 'disabled',
      })
    );
    panel([], 'Ana Lima', ['06 12 34 56 78']);

    await waitFor(() => expect(api.get).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryByRole('region', { name: word('title') })).toBeNull());
  });

  it('says it could not read, and reads again on asking', async () => {
    api.get.mockRejectedValueOnce(new Error('down'));
    api.get.mockResolvedValueOnce(history({ received: [MAIL] }));
    const { user } = panel();

    await user.click(await screen.findByRole('button', { name: 'workbench.states.retry' }));

    expect(await screen.findByRole('link', { name: /The agenda/ })).toBeInTheDocument();
  });
});
