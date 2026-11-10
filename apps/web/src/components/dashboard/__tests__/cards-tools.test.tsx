/**
 * The home's cards and the « Tools » (owner, 2026-11-07).
 *
 * Where the instance offers the Tools, a click on an item opens it in its tool, and each card's
 * « More actions » holds at most five acts, direct ones first (a Tools route, a plain link, a
 * reminder: no model), then what LIA does. A direct act that takes the item off the card reads
 * the card again. The operator's switch keeps the chat: `cards-actions.test.tsx` and
 * `cards-intents.test.tsx` are that oracle, unchanged.
 */
import { beforeEach, describe, expect, it, vi, afterEach } from 'vitest';

import { renderWithProviders, screen, waitFor, within } from '@/__tests__/test-utils';
import { takeHandoff, setHandoffOwner } from '@/lib/workbench/handoff';
import type { BriefingWindows, CardSection, SectionData } from '@/types/briefing';

import { AgendaCard } from '../cards/AgendaCard';
import { BirthdaysCard } from '../cards/BirthdaysCard';
import { DocumentsCard } from '../cards/DocumentsCard';
import { MailsCard } from '../cards/MailsCard';
import { SmsCard } from '../cards/SmsCard';
import { TasksCard } from '../cards/TasksCard';
import { openCardActions, runCardAction } from '../cards/__tests__/card-actions-harness';

const seams = vi.hoisted(() => ({
  tools: { offered: true, mail: true as boolean, contacts: true as boolean },
  post: vi.fn(),
  patch: vi.fn(),
  push: vi.fn(),
  openChat: vi.fn(),
  propose: vi.fn(),
  toastError: vi.fn(),
}));

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 'u1', timezone: 'Europe/Paris' } }),
}));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: seams.push }) }));
vi.mock('@/hooks/useLocalizedRouter', () => ({ useLocalizedRouter: () => ({ push: seams.push }) }));
vi.mock('@/lib/chat-deep-link', () => ({
  openChatDeepLink: (href: string) => seams.openChat(href),
}));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { post: seams.post, patch: seams.patch, get: vi.fn() },
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: seams.toastError } }));
vi.mock('../HomeTools', async importOriginal => {
  const real = await importOriginal<typeof import('../HomeTools')>();
  const { useHandoffNavigation } = await import('@/hooks/useHandoff');
  return {
    ...real,
    useHomeTools: () => ({
      offered: seams.tools.offered,
      offers: (kind: string) =>
        seams.tools.offered &&
        (kind === 'compose' ? seams.tools.mail : kind === 'contact' ? seams.tools.contacts : true),
      go: useHandoffNavigation('en', seams.push),
      zone: 'Europe/Paris',
    }),
  };
});
vi.mock('@/i18n/client', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts
        ? `${key}|${Object.entries(opts)
            .map(([k, v]) => `${k}=${v}`)
            .join('|')}`
        : key,
  }),
}));
vi.mock('@/hooks/useSmsManagement', () => ({
  useSmsManagement: () => ({
    propose: seams.propose,
    proposal: null,
    busy: false,
    cancel: vi.fn(),
    confirm: vi.fn(),
  }),
}));
vi.mock('@/components/sms/SmsConfirmation', () => ({ SmsConfirmation: () => null }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts
        ? `${key}|${Object.entries(opts)
            .map(([k, v]) => `${k}=${v}`)
            .join('|')}`
        : key,
    i18n: { language: 'en' },
  }),
}));

function section<T extends SectionData>(data: T): CardSection<T> {
  return {
    status: 'ok',
    data,
    generated_at: '2026-11-07T08:00:00Z',
    error_code: null,
    error_message: null,
    from_cache: false,
    stale_generated_at: null,
    last_attempt_at: null,
  };
}

const onInvalidate = vi.fn();
const cardProps = { isRefreshing: false, onRefresh: vi.fn(), onInvalidate, staggerIndex: 0 };
const WINDOWS: BriefingWindows = {
  birthdays_horizon_days: 7,
  health_window_days: 14,
  agenda_lookahead_hours: 24,
  tasks_horizon_days: 7,
  weather_forecast_days: 5,
};

/** The names of a row's menu, in order. */
async function menuOf(user: Parameters<typeof openCardActions>[0], index = 0) {
  await openCardActions(user, index);
  const names = screen.getAllByRole('menuitem').map(item => item.textContent ?? '');
  return names;
}

beforeEach(() => {
  seams.tools.offered = true;
  seams.tools.mail = true;
  seams.tools.contacts = true;
  vi.clearAllMocks();
  takeHandoff('compose', 'u1');
  takeHandoff('contact', 'u1');
});

describe('agenda', () => {
  const EVENT = {
    id: 'evt1',
    calendar_id: 'primary',
    start_at: '2026-11-08T09:00:00Z',
    title: 'Comité',
    start_local: '10:00',
    end_local: null,
    location: 'Salle B, 12 rue de la Paix',
    conference_url: 'https://meet.google.com/abc',
  };

  it('opens the event in the calendar, on its day', () => {
    renderWithProviders(<AgendaCard {...cardProps} section={section({ events: [EVENT] })} />);

    const href = screen
      .getByRole('link', { name: /open_in\.event\|title=Comité/ })
      .getAttribute('href');
    const query = new URL(href!, 'https://lia.test').searchParams;
    expect(href?.startsWith('/en/dashboard/tools/calendar?')).toBe(true);
    expect([query.get('day'), query.get('cal'), query.get('event')]).toEqual([
      '2026-11-08',
      'primary',
      'evt1',
    ]);
  });

  it('keeps the chat for an event cached before it named its calendar', async () => {
    const { user } = renderWithProviders(
      <AgendaCard {...cardProps} section={section({ events: [{ ...EVENT, calendar_id: null }] })} />
    );

    await user.click(screen.getByRole('button', { name: /intents\.event\|/ }));

    expect(seams.openChat).toHaveBeenCalledWith(expect.stringContaining('/chat?draft='));
  });

  it('holds the way, the call, a reminder, then the preparation', async () => {
    const { user } = renderWithProviders(
      <AgendaCard {...cardProps} section={section({ events: [EVENT] })} />
    );

    const menu = await menuOf(user);

    expect(menu.map(name => name.split('|')[0])).toEqual([
      'dashboard.briefing.home_acts.route',
      'dashboard.briefing.home_acts.join_call',
      'dashboard.briefing.home_acts.remind',
      'dashboard.briefing.intents_exec.event_prepare',
    ]);
    const route = screen.getByRole('menuitem', { name: /home_acts\.route/ });
    expect(route.getAttribute('href')).toContain('https://www.google.com/maps/dir/');
    expect(screen.getByRole('menuitem', { name: /home_acts\.join_call/ })).toHaveAttribute(
      'href',
      'https://meet.google.com/abc'
    );
  });

  it('asks for a reminder in place, worded after the event', async () => {
    const { user } = renderWithProviders(
      <AgendaCard {...cardProps} section={section({ events: [EVENT] })} />
    );

    await runCardAction(user, /home_acts\.remind/);

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByDisplayValue(/remind_words\.event\|title=Comité/)).toBeVisible();
  });
});

describe('mail', () => {
  const MAIL = {
    id: 'm1',
    sender_name: 'Alice',
    sender_email: 'alice@example.com',
    subject: 'Point projet',
    received_local: '09:12',
  };
  const MAILS = section({ total_unread_today: 1, items: [MAIL] });

  it('opens the message in the mail tool', () => {
    renderWithProviders(<MailsCard {...cardProps} section={MAILS} />);

    const href = screen
      .getByRole('link', { name: /open_in\.mail\|subject=Point projet/ })
      .getAttribute('href');
    expect(href).toBe('/en/dashboard/tools/mail?folder=system%3Ainbox&id=m1');
  });

  it('holds five acts, direct ones first', async () => {
    const { user } = renderWithProviders(<MailsCard {...cardProps} section={MAILS} />);

    const menu = await menuOf(user);

    expect(menu.map(name => name.split('|')[0])).toEqual([
      'dashboard.briefing.home_acts.mark_read',
      'dashboard.briefing.home_acts.archive',
      'dashboard.briefing.watch.action',
      'dashboard.briefing.intents_exec.mail_summarize',
      'dashboard.briefing.intents_exec.mail_reply',
    ]);
  });

  it('marks it read through the Tools, then reads the card again', async () => {
    seams.post.mockResolvedValue({ done: ['m1'], failed: [] });
    const { user } = renderWithProviders(<MailsCard {...cardProps} section={MAILS} />);

    await runCardAction(user, /home_acts\.mark_read/);

    await waitFor(() => expect(onInvalidate).toHaveBeenCalledTimes(1));
    expect(seams.post).toHaveBeenCalledWith('/workbench/mail/read-state', {
      message_ids: ['m1'],
      read: true,
    });
  });

  it('archives it through the Tools', async () => {
    seams.post.mockResolvedValue({ done: ['m1'], failed: [], moved: [] });
    const { user } = renderWithProviders(<MailsCard {...cardProps} section={MAILS} />);

    await runCardAction(user, /home_acts\.archive/);

    await waitFor(() => expect(onInvalidate).toHaveBeenCalledTimes(1));
    expect(seams.post).toHaveBeenCalledWith('/workbench/mail/move', {
      message_ids: ['m1'],
      to: 'system:archive',
      origin: 'system:inbox',
    });
  });

  it('says a refused act and leaves the card as it is', async () => {
    seams.post.mockResolvedValue({ done: [], failed: [{ id: 'm1', status: 'gone' }] });
    const { user } = renderWithProviders(<MailsCard {...cardProps} section={MAILS} />);

    await runCardAction(user, /home_acts\.archive/);

    await waitFor(() => expect(seams.toastError).toHaveBeenCalledTimes(1));
    expect(onInvalidate).not.toHaveBeenCalled();
  });

  it('offers no Tools act where the instance keeps the chat', async () => {
    seams.tools.offered = false;
    const { user } = renderWithProviders(<MailsCard {...cardProps} section={MAILS} />);

    const menu = await menuOf(user);

    expect(menu.some(name => name.includes('home_acts.'))).toBe(false);
    expect(screen.getByRole('button', { name: /intents\.mail\|/ })).toBeInTheDocument();
  });
});

describe('tasks', () => {
  const TASK = {
    id: 't1',
    list_id: 'L1',
    title: 'Payer la facture',
    due_date_iso: '2026-11-07',
    days_until_due: 0,
    overdue: false,
  };
  const TASKS = section({ overdue_count: 0, items: [TASK] });

  it('opens the task in its own list', () => {
    renderWithProviders(<TasksCard {...cardProps} section={TASKS} />);

    const href = screen
      .getByRole('link', { name: /open_in\.task\|subject=Payer la facture/ })
      .getAttribute('href');
    expect(href).toBe('/en/dashboard/tools/tasks?list=L1&task=t1');
  });

  it('holds done, tomorrow, a reminder, then LIA’s help', async () => {
    const { user } = renderWithProviders(<TasksCard {...cardProps} section={TASKS} />);

    const menu = await menuOf(user);

    expect(menu.map(name => name.split('|')[0])).toEqual([
      'dashboard.briefing.home_acts.done',
      'dashboard.briefing.home_acts.postpone',
      'dashboard.briefing.home_acts.remind',
      'dashboard.briefing.intents_exec.task_help',
    ]);
  });

  it('marks it done through the Tools, then reads the card again', async () => {
    seams.patch.mockResolvedValue({});
    const { user } = renderWithProviders(<TasksCard {...cardProps} section={TASKS} />);

    await runCardAction(user, /home_acts\.done/);

    await waitFor(() => expect(onInvalidate).toHaveBeenCalledTimes(1));
    expect(seams.patch).toHaveBeenCalledWith('/workbench/tasks', {
      list_id: 'L1',
      task_id: 't1',
      completed: true,
    });
  });

  it('postpones it to the account’s tomorrow', async () => {
    seams.patch.mockResolvedValue({});
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-11-07T23:30:00Z')); // already the 8th in Paris
    const { user } = renderWithProviders(<TasksCard {...cardProps} section={TASKS} />);

    await runCardAction(user, /home_acts\.postpone/);

    await waitFor(() => expect(onInvalidate).toHaveBeenCalledTimes(1));
    expect(seams.patch).toHaveBeenCalledWith('/workbench/tasks', {
      list_id: 'L1',
      task_id: 't1',
      due: '2026-11-09',
    });
    vi.useRealTimers();
  });

  it('never « postpones » to tomorrow a task due later: that would bring it forward', async () => {
    const later = { ...TASK, due_date_iso: '2026-11-12', days_until_due: 5 };
    const { user } = renderWithProviders(
      <TasksCard {...cardProps} section={section({ overdue_count: 0, items: [later] })} />
    );

    const menu = await menuOf(user);

    expect(menu.map(name => name.split('|')[0])).toEqual([
      'dashboard.briefing.home_acts.done',
      'dashboard.briefing.home_acts.remind',
      'dashboard.briefing.intents_exec.task_help',
    ]);
  });

  it('asks LIA to complete it when its list could not be read', async () => {
    const { user } = renderWithProviders(
      <TasksCard
        {...cardProps}
        section={section({ overdue_count: 0, items: [{ ...TASK, list_id: null }] })}
      />
    );

    const menu = await menuOf(user);

    expect(menu.some(name => name.startsWith('dashboard.briefing.home_acts.done'))).toBe(false);
    expect(
      menu.some(name => name.startsWith('dashboard.briefing.intents_exec.task_complete'))
    ).toBe(true);
  });
});

describe('documents', () => {
  const DOC = {
    id: 'f1',
    name: 'Rapport T2.pdf',
    modified_local: 'hier 18:02',
    web_view_link: 'https://drive.example/x',
    mime_type: 'application/pdf',
    path: '',
  };
  const DOCS = section({ provider: 'google_drive', items: [DOC] });

  it('opens the file in the files tool', () => {
    renderWithProviders(<DocumentsCard {...cardProps} section={DOCS} />);

    const href = screen
      .getByRole('link', { name: /open_in\.document\|subject=Rapport T2\.pdf/ })
      .getAttribute('href');
    expect(href).toBe('/en/dashboard/tools/files?file=f1');
  });

  it('holds download, mail, the drive, then LIA', async () => {
    const { user } = renderWithProviders(<DocumentsCard {...cardProps} section={DOCS} />);

    const menu = await menuOf(user);

    expect(menu.map(name => name.split('|')[0])).toEqual([
      'dashboard.briefing.home_acts.download',
      'dashboard.briefing.home_acts.send_by_mail',
      'dashboard.briefing.cards.documents.open_external',
      'dashboard.briefing.intents_exec.document_summarize',
      'dashboard.briefing.intents_exec.document_ask_label',
    ]);
    expect(
      screen.getByRole('menuitem', { name: /home_acts\.download/ }).getAttribute('href')
    ).toContain('/workbench/files/download?id=f1');
  });

  it('hands the file to a new message in the mail tool', async () => {
    const { user } = renderWithProviders(<DocumentsCard {...cardProps} section={DOCS} />);

    await runCardAction(user, /home_acts\.send_by_mail/);

    expect(seams.push).toHaveBeenCalledWith('/en/dashboard/tools/mail');
    expect(takeHandoff('compose', 'u1')).toEqual({
      kind: 'compose',
      to: '',
      file: {
        id: 'f1',
        filename: 'Rapport T2.pdf',
        mime_type: 'application/pdf',
        size: 0,
        origin: 'drive',
        expires_at: null,
      },
    });
  });

  it('offers no mail where no mailbox is connected', async () => {
    seams.tools.mail = false;
    const { user } = renderWithProviders(<DocumentsCard {...cardProps} section={DOCS} />);

    const menu = await menuOf(user);

    expect(menu.some(name => name.startsWith('dashboard.briefing.home_acts.send_by_mail'))).toBe(
      false
    );
  });
});

describe('birthdays', () => {
  const BIRTHDAY = {
    contact_id: 'people/c42',
    contact_name: 'Inès',
    date_iso: '--11-09',
    days_until: 2,
    age_at_next: null,
    email: 'ines@example.org',
    phone: '+33 6 12 34 56 78',
  };
  const BIRTHDAYS = section({ items: [BIRTHDAY] });

  it('opens the contact in the contacts tool', () => {
    renderWithProviders(<BirthdaysCard {...cardProps} windows={WINDOWS} section={BIRTHDAYS} />);

    const href = screen
      .getByRole('link', { name: /open_in\.birthday\|name=Inès/ })
      .getAttribute('href');
    expect(href).toBe('/en/dashboard/tools/contacts?contact=people%2Fc42');
  });

  it('writes, calls, reminds, then lets LIA word the wishes', async () => {
    const { user } = renderWithProviders(
      <BirthdaysCard {...cardProps} windows={WINDOWS} section={BIRTHDAYS} />
    );

    const menu = await menuOf(user);

    expect(menu.map(name => name.split('|')[0])).toEqual([
      'dashboard.briefing.home_acts.write',
      'dashboard.briefing.home_acts.call',
      'dashboard.briefing.home_acts.remind',
      'dashboard.briefing.intents_exec.birthday_message',
    ]);
    const call = screen.getByRole('menuitem', { name: /home_acts\.call/ });
    expect(call).toHaveAttribute('href', 'tel:+33612345678');
    expect(call).not.toHaveAttribute('target');
  });

  it('opens a new message to them in the mail tool', async () => {
    const { user } = renderWithProviders(
      <BirthdaysCard {...cardProps} windows={WINDOWS} section={BIRTHDAYS} />
    );

    await runCardAction(user, /home_acts\.write/);

    expect(seams.push).toHaveBeenCalledWith('/en/dashboard/tools/mail');
    expect(takeHandoff('compose', 'u1')).toEqual({ kind: 'compose', to: 'ines@example.org' });
  });
});

describe('sms', () => {
  const SMS = section({
    timezone: 'Europe/Paris',
    total: 1,
    window_total: 1,
    window_start: '2026-11-06T00:00:00Z',
    as_of: '2026-11-07T08:00:00Z',
    latest_at: '2026-11-07T07:00:00Z',
    items: [
      {
        id: '11111111-1111-4111-8111-111111111111',
        sender: '+33612345678',
        display_name: '+33612345678',
        received_at: '2026-11-07T07:00:00Z',
        date_kind: 'today',
        body_excerpt: 'Ton colis est arrivé',
        body_truncated: false,
      },
    ],
  });

  it('calls, saves, blocks and reminds', async () => {
    const { user } = renderWithProviders(<SmsCard {...cardProps} section={SMS} />);

    const menu = await menuOf(user);

    expect(menu.map(name => name.split('|')[0])).toEqual([
      'dashboard.briefing.home_acts.call',
      'dashboard.briefing.home_acts.add_contact',
      'dashboard.briefing.home_acts.block',
      'dashboard.briefing.home_acts.remind',
    ]);
  });

  it('saves the sender in the contacts tool, number in hand', async () => {
    const { user } = renderWithProviders(<SmsCard {...cardProps} section={SMS} />);

    await runCardAction(user, /home_acts\.add_contact/);

    expect(seams.push).toHaveBeenCalledWith('/en/dashboard/tools/contacts');
    expect(takeHandoff('contact', 'u1')).toEqual({
      kind: 'contact',
      name: '',
      email: '',
      phone: '+33612345678',
    });
  });

  it('blocks only through the reviewed command, which asks first', async () => {
    const { user } = renderWithProviders(<SmsCard {...cardProps} section={SMS} />);

    await runCardAction(user, /home_acts\.block/);

    expect(seams.propose).toHaveBeenCalledWith('sms_sender_block.update', {
      sender: '+33612345678',
      blocked: true,
    });
    expect(seams.post).not.toHaveBeenCalled();
  });

  it('offers no saving for a sender the address book already names', async () => {
    const known = { ...SMS.data!.items![0], display_name: 'Inès Martin' };
    const { user } = renderWithProviders(
      <SmsCard {...cardProps} section={section({ ...SMS.data!, items: [known] })} />
    );

    const menu = await menuOf(user);

    expect(menu.some(name => name.startsWith('dashboard.briefing.home_acts.add_contact'))).toBe(
      false
    );
    expect(menu.some(name => name.startsWith('dashboard.briefing.home_acts.call'))).toBe(true);
  });

  it('offers no saving where no address book is connected', async () => {
    seams.tools.contacts = false;
    const { user } = renderWithProviders(<SmsCard {...cardProps} section={SMS} />);

    const menu = await menuOf(user);

    expect(menu.some(name => name.startsWith('dashboard.briefing.home_acts.add_contact'))).toBe(
      false
    );
  });
});

beforeEach(() => {
  setHandoffOwner(null);
  setHandoffOwner('u1');
});

afterEach(() => setHandoffOwner(null));
