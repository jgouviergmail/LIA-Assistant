/**
 * The « Tools » mail screen (ADR-369, Task 4.7).
 *
 * The open message rides the address (`?id=`); the arrows walk the list, Enter
 * opens, Escape closes; a selection is trashed and what could not be is said;
 * the open message's read state shows at once and is rolled back when refused;
 * the chips narrow the listing; a message is sent once whatever is pressed
 * twice, and an outcome nobody knows keeps the words and says to look in Sent.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  act,
  answerConfirmDialog,
  fireEvent,
  renderWithProviders,
  screen,
  waitFor,
  within,
} from '@/__tests__/test-utils';
import type { AppConfig } from '@/hooks/useAppConfig';
import { ApiError } from '@/lib/api-client';
import type {
  MailHtml,
  MailMessage,
  MailSummary,
  WorkbenchAvailability,
  WorkbenchFeature,
  WorkbenchToolState,
  WorkbenchToolId,
} from '@/lib/workbench/types';

type ShellConfig = Pick<AppConfig, 'capabilities'> & { features: { workbench_enabled?: boolean } };

const { api, nav, toast, media, openChat, instance } = vi.hoisted(() => ({
  openChat: vi.fn(),
  instance: { assists: false },
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() },
  nav: { search: '', push: vi.fn(), replace: vi.fn() },
  toast: { error: vi.fn(), success: vi.fn() },
  media: { desktop: true, sideBySide: false, androidShell: false, frameLinks: false },
}));
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 'owner', timezone: 'Europe/Paris' } }),
}));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: api,
}));
vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), error: vi.fn(), warn: vi.fn(), info: vi.fn() },
}));
vi.mock('@/lib/native/shell', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/native/shell')>()),
  isAndroidShell: () => media.androidShell,
  shellCapability: () => Promise.resolve(media.frameLinks),
}));
vi.mock('sonner', () => ({ toast }));
vi.mock('@/lib/chat-deep-link', () => ({ openChatDeepLink: openChat }));
vi.mock('next/navigation', () => ({
  usePathname: () => '/en/dashboard/tools/mail',
  useRouter: () => ({ push: nav.push, replace: nav.replace, back: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams(nav.search),
}));
vi.mock('@/hooks/useMediaQuery', () => ({
  useMediaQuery: (query: string) =>
    query === '(min-width: 1280px)' ? media.sideBySide : media.desktop,
}));
vi.mock('@/hooks/useAppConfig', async importOriginal => ({
  ...(await importOriginal<typeof import('@/hooks/useAppConfig')>()),
  useAppConfig: () => ({
    config: {
      features: { workbench_enabled: true },
      capabilities: { tool_assists: { enabled: instance.assists, family: 'work' } },
    } satisfies ShellConfig,
    loading: false,
    error: null,
  }),
}));

import { handOff, takeHandoff } from '@/lib/workbench/handoff';

import { MAIL_READ_DWELL_MS } from '@/lib/workbench/mail';

import { WorkbenchShell } from '../../WorkbenchShell';
import { MailTool } from '../MailTool';

const GMAIL: WorkbenchFeature[] = ['mark_read', 'drafts', 'attachments', 'labels'];
const OUTLOOK: WorkbenchFeature[] = [
  'mark_read',
  'drafts',
  'attachments',
  'folder_management',
  'permanent_delete',
];
const MOVED = { done: ['m1'], failed: [], moved: [{ id: 'm1', new_id: 'n1' }] };

function rail(
  state: WorkbenchToolState = 'ready',
  features: WorkbenchFeature[] = GMAIL
): WorkbenchAvailability {
  const ready = state === 'ready';
  return {
    tools: [
      {
        tool: 'mail',
        state,
        provider: ready ? 'google_gmail' : null,
        features: ready ? features : [],
        bounds: ready
          ? {
              search_max_chars: 500,
              assist_text_max_chars: 8000,
              assist_instruction_max_chars: 500,
              recipients_max: 100,
              recipient_max_chars: 320,
              subject_max_chars: 998,
              body_max_chars: 100000,
              attachments_max: 10,
              attachments_max_bytes: 26214400,
              recipient_query_min_chars: 2,
            }
          : {},
      },
    ],
    limits: {
      page_size: 25,
      bulk_max_items: 50,
      download_max_bytes: 26214400,
      upload_max_bytes: 26214400,
      calendar_window_max_events: 500,
      send_undo_seconds: 0,
      draft_autosave_seconds: 0,
      search_max_chars: 500,
      assist_text_max_chars: 8000,
      assist_instruction_max_chars: 500,
    },
  };
}

function row(id: string, overrides: Partial<MailSummary> = {}): MailSummary {
  return {
    id,
    thread_id: id,
    sender: { name: `Sender ${id}`, address: `${id}@example.org` },
    subject: `Subject ${id}`,
    snippet: `Snippet ${id}`,
    received_at: '2026-10-30T08:00:00Z',
    is_read: true,
    is_starred: false,
    has_attachments: false,
    label_ids: [],
    ...overrides,
  };
}

function message(id: string, overrides: Partial<MailMessage> = {}): MailMessage {
  const { snippet: _snippet, ...summary } = row(id);
  return {
    ...summary,
    reply_to: [],
    to: [{ name: '', address: 'me@example.org' }],
    cc: [],
    body: `Body of ${id}`,
    attachments: [],
    ...overrides,
  };
}

const FOLDERS = {
  folders: [
    { id: 'system:inbox', kind: 'system', role: 'inbox', name: null },
    { id: 'system:sent', kind: 'system', role: 'sent', name: null },
    { id: 'system:drafts', kind: 'system', role: 'drafts', name: null },
    { id: 'system:spam', kind: 'system', role: 'spam', name: null },
    { id: 'system:trash', kind: 'system', role: 'trash', name: null },
    { id: 'Label_7', kind: 'user', role: null, name: 'Work' },
  ],
};
const WITH_ARCHIVE = {
  folders: [
    ...FOLDERS.folders.slice(0, 3),
    { id: 'system:archive', kind: 'system', role: 'archive', name: null },
    ...FOLDERS.folders.slice(3),
  ],
};

let features: WorkbenchFeature[];
let folders: typeof FOLDERS;
let unread: { counts: Record<string, number>; truncated: boolean };
let page: { items: MailSummary[]; next_page_token: string | null; skipped: number };
let messages: Record<string, MailMessage>;
/** Each message's original layout, as the server answers it (none by default), or a refusal. */
let htmls: Record<string, MailHtml | Error>;
let inlineAnswer: { images: { cid: string; data_url: string }[]; skipped: number };
const NO_WAY = { web_url: null as string | null, mail_to: null as string | null, one_click: false };
let leaving: typeof NO_WAY;
let conversation: { items: MailSummary[]; truncated: boolean } | Error;

beforeEach(() => {
  vi.clearAllMocks();
  instance.assists = false;
  nav.search = '';
  media.desktop = true;
  media.sideBySide = false;
  media.androidShell = false;
  media.frameLinks = false;
  features = GMAIL;
  folders = FOLDERS;
  unread = { counts: {}, truncated: false };
  page = { items: [row('m1'), row('m2'), row('m3')], next_page_token: null, skipped: 0 };
  messages = { m1: message('m1'), m2: message('m2', { is_read: false }) };
  htmls = {};
  inlineAnswer = { images: [], skipped: 0 };
  leaving = NO_WAY;
  conversation = { items: [], truncated: false };
  window.localStorage.clear();
  api.get.mockImplementation((path: string, options?: { params?: { id?: string } }) => {
    if (path === '/workbench/mail/conversation' && conversation instanceof Error) {
      return Promise.reject(conversation);
    }
    if (path in fixedAnswers()) return Promise.resolve(fixedAnswers()[path]);
    if (path === '/workbench/mail/message') {
      return Promise.resolve(messages[options?.params?.id ?? '']);
    }
    if (path === '/workbench/mail/message/html') {
      const answer = htmls[options?.params?.id ?? ''] ?? { html: null, truncated: false };
      return answer instanceof Error ? Promise.reject(answer) : Promise.resolve(answer);
    }
    return Promise.resolve(page);
  });
});

/** What the screen reads that names no message. */
function fixedAnswers(): Record<string, unknown> {
  return {
    '/workbench': rail('ready', features),
    '/workbench/mail/message/images': inlineAnswer,
    '/workbench/mail/reply-recipients': { to: [], cc: [] },
    '/workbench/mail/signature': { text: '', block: '' },
    '/workbench/mail/conversation': conversation,
    '/workbench/mail/message/unsubscribe': leaving,
    '/workbench/mail/folders': folders,
    '/workbench/mail/counts': unread,
  };
}

function tool() {
  return (
    <WorkbenchShell lng="en">
      <MailTool lng="en" />
    </WorkbenchShell>
  );
}

function screenOf() {
  return renderWithProviders(tool());
}

/** The body last posted to a path (the mutation's plumbing is not the contract). */
function posted(path: string): unknown {
  return api.post.mock.calls.filter(([called]) => called === path).at(-1)?.[1];
}

function postsTo(path: string): number {
  return api.post.mock.calls.filter(([called]) => called === path).length;
}

/** A POST the test answers by hand. */
function deferred<T>(): {
  promise: Promise<T>;
  answer: (value: T) => void;
  refuse: (e: unknown) => void;
} {
  let answer!: (value: T) => void;
  let refuse!: (error: unknown) => void;
  const promise = new Promise<T>((resolve, reject) => {
    answer = resolve;
    refuse = reject;
  });
  return { promise, answer, refuse };
}

describe('MailTool — the list and the reader', () => {
  it('lists the inbox and opens the message the address names', async () => {
    nav.search = 'id=m1';
    screenOf();

    const reader = await screen.findByRole('article', { name: 'Subject m1' });
    expect(within(reader).getByText('Body of m1')).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('/workbench/mail/messages', {
      params: { folder: 'system:inbox' },
      signal: expect.any(AbortSignal),
    });
    expect(api.get).toHaveBeenCalledWith('/workbench/mail/message', {
      params: { id: 'm1' },
      signal: expect.any(AbortSignal),
    });
  });

  it('re-reads what it shows when the person asks', async () => {
    const { user } = screenOf();
    await screen.findByRole('button', { name: 'workbench.states.refresh' });
    api.get.mockClear();

    await user.click(screen.getByRole('button', { name: 'workbench.states.refresh' }));

    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/workbench/mail/messages', expect.anything())
    );
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/workbench/mail/folders', expect.anything())
    );
  });

  it('opens a message by pushing it on the address, so « back » closes it', async () => {
    const { user } = screenOf();

    await user.click(await screen.findByRole('link', { name: /Subject m2/ }));

    expect(nav.push).toHaveBeenCalledWith('/en/dashboard/tools/mail?id=m2', { scroll: false });
  });

  it('walks the list with the arrows and opens the message in focus with Enter', async () => {
    const { user } = screenOf();
    const first = await screen.findByRole('link', { name: /Subject m1/ });

    first.focus();
    await user.keyboard('{ArrowDown}');
    expect(screen.getByRole('link', { name: /Subject m2/ })).toHaveFocus();
    await user.keyboard('{End}');
    expect(screen.getByRole('link', { name: /Subject m3/ })).toHaveFocus();
    await user.keyboard('{Home}{Enter}');

    expect(nav.push).toHaveBeenCalledWith('/en/dashboard/tools/mail?id=m1', { scroll: false });
  });

  it('closes the reader with Escape, keeping the folder', async () => {
    nav.search = 'folder=Label_7&id=m1';
    const { user } = screenOf();
    const reader = await screen.findByRole('article', { name: 'Subject m1' });

    within(reader).getByRole('button', { name: 'workbench.mail.trash' }).focus();
    await user.keyboard('{Escape}');

    expect(nav.replace).toHaveBeenCalledWith('/en/dashboard/tools/mail?folder=Label_7', {
      scroll: false,
    });
  });

  it('marks an unread message read after a look, never at a glance', async () => {
    api.post.mockResolvedValue({ done: ['m2'], failed: [] });
    nav.search = 'id=m2';
    screenOf();
    await screen.findByRole('article', { name: 'Subject m2' });

    expect(postsTo('/workbench/mail/read-state')).toBe(0);
    await waitFor(() => expect(postsTo('/workbench/mail/read-state')).toBe(1), { timeout: 3000 });
    expect(posted('/workbench/mail/read-state')).toEqual({ message_ids: ['m2'], read: true });
  });

  it('marks the open message unread at once and rolls it back when refused', async () => {
    const answer = deferred<unknown>();
    api.post.mockReturnValueOnce(answer.promise);
    nav.search = 'id=m1';
    const { user } = screenOf();
    const reader = await screen.findByRole('article', { name: 'Subject m1' });

    await user.click(within(reader).getByRole('button', { name: 'workbench.mail.mark_unread' }));
    expect(
      within(reader).getByRole('button', { name: 'workbench.mail.mark_read' }),
      'shown at once'
    ).toBeInTheDocument();

    await act(async () =>
      answer.refuse(new ApiError('refused', 502, { detail: { code: 'provider_unavailable' } }))
    );
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('workbench.errors.provider_unavailable')
    );
    expect(
      within(reader).getByRole('button', { name: 'workbench.mail.mark_unread' }),
      'rolled back'
    ).toBeInTheDocument();
  });
});

describe('MailTool — the person’s folders', () => {
  const NESTED = {
    folders: [
      ...FOLDERS.folders,
      { id: 'Work/Clients', kind: 'user', role: null, name: 'Work/Clients' },
      { id: 'Work/Clients/Acme', kind: 'user', role: null, name: 'Work/Clients/Acme' },
    ],
  };

  function foldersAnswer(answer: unknown) {
    const read = api.get.getMockImplementation();
    api.get.mockImplementation((path: string, options?: unknown) =>
      path === '/workbench/mail/folders' ? Promise.resolve(answer) : read?.(path, options)
    );
  }

  it('sets a folder under its parent, its whole path named for the ear', async () => {
    foldersAnswer(NESTED);
    screenOf();

    const nested = await screen.findByRole('link', { name: 'Work/Clients/Acme' });

    expect(nested).toHaveTextContent(/^Acme$/);
    expect(nested.style.paddingInlineStart).not.toBe('');
    expect(screen.getByRole('link', { name: 'Work' }).style.paddingInlineStart).toBe('');
  });

  async function phoneList() {
    media.desktop = false;
    const rendered = screenOf();
    await rendered.user.click(
      await screen.findByRole('combobox', { name: 'workbench.mail.folder' })
    );
    return { ...rendered, options: await screen.findAllByRole('option') };
  }

  it('keeps the phone’s list in the same order, each told whole', async () => {
    foldersAnswer({ folders: [...NESTED.folders].reverse() });
    const { options } = await phoneList();

    expect(options.slice(-3)).toEqual([
      screen.getByRole('option', { name: 'Work' }),
      screen.getByRole('option', { name: 'Work/Clients' }),
      screen.getByRole('option', { name: 'Work/Clients/Acme' }),
    ]);
  });

  it('draws the phone’s folder from its place, under the title of the person’s own', async () => {
    foldersAnswer(NESTED);
    await phoneList();

    const own = screen.getByRole('group', { name: 'workbench.mail.labels_title' });
    const nested = within(own).getByRole('option', { name: 'Work/Clients/Acme' });

    expect(nested).toHaveTextContent(/Acme/);
    expect(nested.style.paddingInlineStart).not.toBe('');
    expect(within(own).getByRole('option', { name: 'Work' }).style.paddingInlineStart).toBe('');
    expect(within(own).queryByRole('option', { name: /inbox/ })).toBeNull();
  });

  it('shows the phone what a folder leaves unread, and tells it whole', async () => {
    unread = { counts: { 'system:inbox': 3 }, truncated: false };
    foldersAnswer(NESTED);
    await phoneList();

    const inbox = screen.getByRole('option', { name: 'workbench.mail.folder_unread' });

    expect(within(inbox).getByText('3')).toHaveAttribute('aria-hidden', 'true');
  });

  it('opens the folder the phone picks, and states the open one', async () => {
    nav.search = 'folder=Label_7';
    foldersAnswer(NESTED);
    const { user } = await phoneList();

    expect(screen.getByRole('option', { name: 'Work' })).toHaveAttribute('aria-selected', 'true');
    await user.click(screen.getByRole('option', { name: 'Work/Clients' }));

    expect(nav.replace).toHaveBeenCalledWith('/en/dashboard/tools/mail?folder=Work%2FClients', {
      scroll: false,
    });
  });

  it('says « folder » on the phone when the open one is not listed', async () => {
    nav.search = 'folder=gone';
    foldersAnswer(NESTED);
    media.desktop = false;
    screenOf();

    expect(
      await screen.findByRole('combobox', { name: 'workbench.mail.folder' })
    ).toHaveTextContent('workbench.mail.folder');
  });

  it('says a mailbox holds more folders than were read', async () => {
    foldersAnswer({ ...NESTED, truncated: true });
    screenOf();

    // Once beside the messages, once under the phone's list: CSS shows one of the two.
    expect(await screen.findAllByText('workbench.mail.folders_truncated')).toHaveLength(2);
  });

  it('says nothing of the kind when all were read', async () => {
    foldersAnswer({ ...NESTED, truncated: false });
    screenOf();

    await screen.findByRole('link', { name: 'Work/Clients/Acme' });
    expect(screen.queryByText('workbench.mail.folders_truncated')).toBeNull();
  });
});

describe('MailTool — the conversation of a message', () => {
  const reads = () =>
    api.get.mock.calls.filter(([path]) => path === '/workbench/mail/conversation');
  const opener = () => screen.findByRole('button', { name: 'workbench.mail.conversation_count' });

  it('is read once the message landed, from that message', async () => {
    nav.search = 'id=m1';
    conversation = { items: [row('m0'), row('m1')], truncated: false };

    screenOf();

    await opener();
    expect(reads()).toHaveLength(1);
    expect(reads()[0][1]).toMatchObject({ params: { id: 'm1' } });
  });

  it('opens another of its messages in the place of this one', async () => {
    nav.search = 'id=m1';
    conversation = { items: [row('m0'), row('m1')], truncated: false };
    const { user } = screenOf();

    await user.click(await opener());
    const list = screen.getByRole('list', { name: 'workbench.mail.conversation_title' });
    await user.click(within(list).getByRole('link', { name: /Sender m0/ }));

    expect(nav.replace).toHaveBeenCalledWith(expect.stringContaining('id=m0'), { scroll: false });
    expect(nav.push).not.toHaveBeenCalled();
  });

  it('says nothing of a message alone', async () => {
    nav.search = 'id=m1';
    conversation = { items: [row('m1')], truncated: false };

    screenOf();

    await waitFor(() => expect(reads()).toHaveLength(1));
    expect(
      screen.queryByRole('button', { name: 'workbench.mail.conversation_count' })
    ).not.toBeInTheDocument();
  });

  it('never holds the message up: a failure stays beside it', async () => {
    nav.search = 'id=m1';
    conversation = new Error('unread');

    screenOf();

    expect(await screen.findByText('workbench.mail.conversation_failed')).toBeInTheDocument();
    expect(screen.getByText('Body of m1')).toBeInTheDocument();
  });

  it('is not read for a list with nothing open', async () => {
    screenOf();

    await screen.findByRole('link', { name: /Sender m1/ });
    expect(reads()).toHaveLength(0);
  });

  it('is read again once a reply left', async () => {
    nav.search = 'id=m1';
    conversation = { items: [row('m0'), row('m1')], truncated: false };
    api.post.mockResolvedValue({ id: 's1', thread_id: 't1' });
    const answers = api.get.getMockImplementation();
    api.get.mockImplementation((path: string, options?: { params?: { id?: string } }) =>
      path === '/workbench/mail/reply-recipients'
        ? Promise.resolve({ to: [{ name: '', address: 'ana@example.org' }], cc: [] })
        : answers?.(path, options)
    );
    const { user } = screenOf();
    await opener();

    const reader = screen.getByRole('article', { name: 'Subject m1' });
    await user.click(within(reader).getAllByRole('button', { name: 'workbench.mail.reply' })[0]!);
    const dialog = await screen.findByRole('dialog');
    await user.type(
      within(dialog).getByRole('textbox', { name: 'workbench.mail.compose.body' }),
      'Thanks'
    );
    await user.click(
      within(dialog).getByRole('button', { name: /workbench\.mail\.compose\.send/ })
    );

    await waitFor(() => expect(reads()).toHaveLength(2));
  });

  it('is read again with the rest of the screen', async () => {
    nav.search = 'id=m1';
    conversation = { items: [row('m0'), row('m1')], truncated: false };
    const { user } = screenOf();
    await opener();

    await user.click(screen.getByRole('button', { name: 'workbench.states.refresh' }));

    await waitFor(() => expect(reads()).toHaveLength(2));
  });
});

describe('MailTool — a list by conversation', () => {
  const grouping = () =>
    screen.findByRole('button', { name: 'workbench.mail.group_conversations' });

  function threads() {
    page = {
      items: [row('m3', { thread_id: 't1' }), row('m2'), row('m1', { thread_id: 't1' })],
      next_page_token: null,
      skipped: 0,
    };
  }

  async function grouped() {
    threads();
    const view = screenOf();
    await view.user.click(await grouping());
    return view;
  }

  const lines = () => screen.getAllByRole('checkbox', { name: 'workbench.mail.select_message' });

  it('is no way of drawing the drafts', async () => {
    nav.search = 'folder=system%3Adrafts';
    page = { items: [], next_page_token: null, skipped: 0 };

    screenOf();

    await screen.findByRole('button', { name: 'workbench.mail.compact_list' });
    expect(
      screen.queryByRole('button', { name: 'workbench.mail.group_conversations' })
    ).not.toBeInTheDocument();
  });

  it('lets go of a selection when the lines are drawn another way', async () => {
    threads();
    const { user } = screenOf();
    await waitFor(() => expect(lines()).toHaveLength(3));
    await user.click(lines()[0]);
    expect(
      screen.getByRole('region', { name: 'workbench.mail.selection_region' })
    ).toBeInTheDocument();

    await user.click(await grouping());

    await waitFor(() => expect(lines()).toHaveLength(2));
    expect(
      screen.queryByRole('region', { name: 'workbench.mail.selection_region' })
    ).not.toBeInTheDocument();
  });

  it('starts flat', async () => {
    threads();

    screenOf();

    expect(await grouping()).toHaveAttribute('aria-pressed', 'false');
    await waitFor(() => expect(lines()).toHaveLength(3));
  });

  it('draws a conversation as one line, marked, under its newest message', async () => {
    await grouped();

    await waitFor(() => expect(lines()).toHaveLength(2));
    expect(screen.queryByRole('link', { name: /Sender m1/ })).not.toBeInTheDocument();
    expect(screen.getAllByRole('img', { name: 'workbench.mail.in_conversation' })).toHaveLength(1);
  });

  it('is remembered on this device', async () => {
    await grouped();

    expect(window.localStorage.getItem('lia_workbench_mail_grouping')).toBe('grouped');
    expect(await grouping()).toHaveAttribute('aria-pressed', 'true');
  });

  it('ticks a line and sends every message loaded under it', async () => {
    const { user } = await grouped();
    api.post.mockResolvedValue({
      done: ['m3', 'm1'],
      failed: [],
      moved: [
        { id: 'm3', new_id: null },
        { id: 'm1', new_id: null },
      ],
    });

    await waitFor(() => expect(lines()).toHaveLength(2));
    await user.click(lines()[0]);
    const bar = screen.getByRole('region', { name: 'workbench.mail.selection_region' });
    await user.click(within(bar).getByRole('button', { name: /workbench\.mail\.trash/ }));

    await waitFor(() =>
      expect(posted('/workbench/mail/move')).toMatchObject({ message_ids: ['m3', 'm1'] })
    );
  });

  it('marks every message of a line from its row', async () => {
    const { user } = await grouped();
    api.post.mockResolvedValue({ done: ['m3', 'm1'], failed: [] });

    await waitFor(() => expect(lines()).toHaveLength(2));
    await user.click(screen.getAllByRole('button', { name: 'workbench.mail.row_mark_unread' })[0]);

    await waitFor(() =>
      expect(posted('/workbench/mail/read-state')).toEqual({
        message_ids: ['m3', 'm1'],
        read: false,
      })
    );
  });

  it('stars the newest message of a line, and takes every star off', async () => {
    page = {
      items: [
        row('m3', { thread_id: 't1' }),
        row('m1', { thread_id: 't1', is_starred: true }),
        row('m2', { thread_id: 't2' }),
        row('m0', { thread_id: 't2' }),
      ],
      next_page_token: null,
      skipped: 0,
    };
    const { user } = screenOf();
    await user.click(await grouping());
    api.post.mockResolvedValue({ done: [], failed: [] });
    await waitFor(() => expect(lines()).toHaveLength(2));

    await user.click(screen.getByRole('button', { name: 'workbench.mail.row_star' }));
    await waitFor(() =>
      expect(posted('/workbench/mail/star')).toEqual({ message_ids: ['m2'], starred: true })
    );

    await user.click(screen.getAllByRole('button', { name: 'workbench.mail.row_unstar' })[0]);
    await waitFor(() =>
      expect(posted('/workbench/mail/star')).toEqual({
        message_ids: ['m3', 'm1'],
        starred: false,
      })
    );
  });

  it('shows the open message on its line, whichever message of it is open', async () => {
    nav.search = 'id=m1';
    messages = { ...messages, m1: message('m1') };
    threads();
    window.localStorage.setItem('lia_workbench_mail_grouping', 'grouped');

    screenOf();

    expect(await screen.findByRole('link', { name: /Sender m3/ })).toHaveAttribute(
      'aria-current',
      'true'
    );
  });

  it('walks from line to line', async () => {
    nav.search = 'id=m1';
    threads();
    window.localStorage.setItem('lia_workbench_mail_grouping', 'grouped');
    const { user } = screenOf();
    await screen.findByText('Body of m1');

    await user.keyboard('j');

    expect(nav.replace).toHaveBeenCalledWith(expect.stringContaining('id=m2'), { scroll: false });
  });
});

describe('MailTool — the original layout', () => {
  const FRAME = 'workbench.mail.html_frame_title';

  it('holds the words, the images and the colours on one line', async () => {
    htmls = {
      m1: { html: '<img src="https://tracker.example/p.gif"><p>Original</p>', truncated: false },
    };
    nav.search = 'id=m1';
    screenOf();

    const reader = await screen.findByRole('article', { name: 'Subject m1' });
    const images = await within(reader).findByRole('button', {
      name: 'workbench.mail.show_images',
    });

    expect(
      within(reader).getByRole('button', { name: 'workbench.mail.show_text' }).parentElement
    ).toBe(images.parentElement);
  });

  it('offers the answers above the message, under it, and where a phone’s page ends', async () => {
    const answers = ['workbench.mail.reply', 'workbench.mail.reply_all', 'workbench.mail.forward'];
    nav.search = 'id=m1';
    const { user } = screenOf();

    const reader = await screen.findByRole('article', { name: 'Subject m1' });
    const [above, ending] = within(reader).getAllByRole('group', {
      name: 'workbench.mail.answer_bar',
    });
    const under = within(reader).getByRole('navigation', { name: 'workbench.mail.answer_bar' });
    const body = within(reader).getByText('Body of m1');

    expect(
      within(above)
        .getAllByRole('button')
        .map(button => button.textContent)
    ).toEqual(answers);
    expect(
      within(under)
        .getAllByRole('button')
        .map(button => button.textContent)
    ).toEqual(answers);
    expect(
      within(ending)
        .getAllByRole('button')
        .map(button => button.textContent)
    ).toEqual(answers);
    expect(above.compareDocumentPosition(body) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(ending.compareDocumentPosition(body) & Node.DOCUMENT_POSITION_PRECEDING).toBeTruthy();

    await user.click(within(above).getByRole('button', { name: 'workbench.mail.forward' }));
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
  });

  it('draws an HTML message in its frame, and its text on demand', async () => {
    htmls = { m1: { html: '<p>Original of m1</p>', truncated: false } };
    nav.search = 'id=m1';
    const { user } = screenOf();

    const reader = await screen.findByRole('article', { name: 'Subject m1' });
    const frame = await within(reader).findByTitle(FRAME);
    expect(frame.getAttribute('srcdoc')).toContain('<p>Original of m1</p>');
    expect(within(reader).queryByText('Body of m1')).not.toBeInTheDocument();

    await user.click(within(reader).getByRole('button', { name: 'workbench.mail.show_text' }));
    expect(within(reader).getByText('Body of m1')).toBeInTheDocument();
    expect(within(reader).queryByTitle(FRAME)).not.toBeInTheDocument();

    await user.click(within(reader).getByRole('button', { name: 'workbench.mail.show_original' }));
    expect(within(reader).getByTitle(FRAME)).toBeInTheDocument();
  });

  it('shows a message without HTML as its text, in the theme', async () => {
    nav.search = 'id=m1';
    screenOf();

    const reader = await screen.findByRole('article', { name: 'Subject m1' });
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/workbench/mail/message/html', {
        params: { id: 'm1' },
        signal: expect.any(AbortSignal),
      })
    );
    expect(within(reader).getByText('Body of m1')).toBeInTheDocument();
    expect(within(reader).queryByTitle(FRAME)).not.toBeInTheDocument();
    expect(
      within(reader).queryByRole('button', { name: 'workbench.mail.show_text' })
    ).not.toBeInTheDocument();
  });

  it('lets the text view follow its links, the written one drawn by its host', async () => {
    messages = {
      m1: message('m1', {
        body: 'Read [link](https://click.example.org/a?b=1) or https://example.org/b.',
      }),
    };
    nav.search = 'id=m1';
    screenOf();

    const reader = await screen.findByRole('article', { name: 'Subject m1' });
    expect(within(reader).getByRole('link', { name: 'click.example.org' })).toHaveAttribute(
      'href',
      'https://click.example.org/a?b=1'
    );
    expect(within(reader).getByRole('link', { name: 'https://example.org/b' })).toHaveAttribute(
      'href',
      'https://example.org/b'
    );
    expect(within(reader).queryByText(/\[link\]/)).not.toBeInTheDocument();
  });

  it('keeps the images asked for across the two views, for this message alone', async () => {
    htmls = { m1: { html: '<img src="https://www.example.org/a.png">', truncated: false } };
    nav.search = 'id=m1';
    const { user, rerender } = screenOf();

    const reader = await screen.findByRole('article', { name: 'Subject m1' });
    await user.click(
      await within(reader).findByRole('button', { name: 'workbench.mail.show_images' })
    );
    expect(within(reader).getByTitle(FRAME).getAttribute('srcdoc')).toContain(
      'img-src https: data:'
    );

    await user.click(within(reader).getByRole('button', { name: 'workbench.mail.show_text' }));
    await user.click(within(reader).getByRole('button', { name: 'workbench.mail.show_original' }));
    expect(within(reader).getByTitle(FRAME).getAttribute('srcdoc')).toContain(
      'img-src https: data:'
    );

    htmls = { m2: { html: '<img src="https://www.example.org/b.png">', truncated: false } };
    nav.search = 'id=m2';
    rerender(tool());

    const next = await screen.findByRole('article', { name: 'Subject m2' });
    const frame = await within(next).findByTitle(FRAME);
    expect(frame.getAttribute('srcdoc')).not.toContain('https: data:');
    expect(within(next).getByRole('button', { name: 'workbench.mail.show_images' })).toBeVisible();
  });

  it('says where the links open in the Android app, whose frame cannot open a tab', async () => {
    media.androidShell = true;
    htmls = { m1: { html: '<a href="https://www.example.org/a">Read</a>', truncated: false } };
    nav.search = 'id=m1';
    screenOf();

    const reader = await screen.findByRole('article', { name: 'Subject m1' });
    await within(reader).findByTitle(FRAME);

    expect(within(reader).getByText('workbench.mail.links_in_text')).toBeVisible();
  });

  it('says nothing of the kind to a shell that opens them', async () => {
    media.androidShell = true;
    media.frameLinks = true;
    htmls = { m1: { html: '<a href="https://www.example.org/a">Read</a>', truncated: false } };
    nav.search = 'id=m1';
    screenOf();

    const reader = await screen.findByRole('article', { name: 'Subject m1' });
    await within(reader).findByTitle(FRAME);

    await waitFor(() =>
      expect(within(reader).queryByText('workbench.mail.links_in_text')).toBeNull()
    );
  });

  it('says nothing of the kind in a browser', async () => {
    htmls = { m1: { html: '<a href="https://www.example.org/a">Read</a>', truncated: false } };
    nav.search = 'id=m1';
    screenOf();

    const reader = await screen.findByRole('article', { name: 'Subject m1' });
    await within(reader).findByTitle(FRAME);

    expect(within(reader).queryByText('workbench.mail.links_in_text')).toBeNull();
  });

  it('says a long layout is cut', async () => {
    htmls = { m1: { html: '<p>Start of m1</p>', truncated: true } };
    nav.search = 'id=m1';
    screenOf();

    const reader = await screen.findByRole('article', { name: 'Subject m1' });
    await within(reader).findByTitle(FRAME);
    expect(within(reader).getByText('workbench.mail.html_truncated')).toBeInTheDocument();
  });

  it('keeps the text and says so when the layout cannot be read', async () => {
    htmls = { m1: new ApiError('down', 503, { detail: { code: 'provider_unavailable' } }) };
    nav.search = 'id=m1';
    screenOf();

    const reader = await screen.findByRole('article', { name: 'Subject m1' });
    expect(await within(reader).findByText('workbench.mail.html_failed')).toBeInTheDocument();
    expect(within(reader).getByText('Body of m1')).toBeInTheDocument();
  });
});

describe('MailTool — selection, search and chips', () => {
  it('trashes a selection and says what could not be, keeping it listed and selected', async () => {
    api.post.mockResolvedValueOnce({
      done: ['m1'],
      failed: [{ id: 'm2', status: 'failed' }],
      moved: [{ id: 'm1', new_id: 'n1' }],
    });
    const { user } = screenOf();

    const boxes = await screen.findAllByRole('checkbox', {
      name: 'workbench.mail.select_message',
    });
    await user.click(boxes[0]!);
    await user.click(boxes[1]!);
    const bar = screen.getByRole('region', { name: 'workbench.mail.selection_region' });
    await user.click(within(bar).getByRole('button', { name: /workbench\.mail\.trash/ }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('workbench.mail.partial'));
    expect(posted('/workbench/mail/move')).toEqual({
      message_ids: ['m1', 'm2'],
      to: 'system:trash',
      origin: 'system:inbox',
    });
    expect(screen.queryByRole('link', { name: /Subject m1/ })).toBeNull();
    expect(screen.getByRole('link', { name: /Subject m2/ })).toBeInTheDocument();
    expect(
      screen.getAllByRole('checkbox', { name: 'workbench.mail.select_message' })[0]
    ).toBeChecked();
  });

  it('says each act of the selection in a short word', async () => {
    const { user } = screenOf();

    const boxes = await screen.findAllByRole('checkbox', {
      name: 'workbench.mail.select_message',
    });
    await user.click(boxes[0]!);
    const bar = within(screen.getByRole('region', { name: 'workbench.mail.selection_region' }));

    for (const key of ['bar_read', 'bar_unread', 'bar_star', 'bar_spam']) {
      expect(bar.getByRole('button', { name: `workbench.mail.${key}` })).toBeInTheDocument();
    }
  });

  it('narrows the listing with a chip, and offers the attachment chip only where it filters', async () => {
    const { user, unmount } = screenOf();

    await user.click(await screen.findByRole('button', { name: 'workbench.mail.chip_unread' }));

    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/workbench/mail/messages', {
        params: { folder: 'system:inbox', unread: true },
        signal: expect.any(AbortSignal),
      })
    );
    expect(screen.queryByRole('button', { name: /workbench\.mail\.chip_attachments/ })).toBeNull();
    unmount();

    features = [...GMAIL, 'attachment_filter'];
    screenOf();
    expect(
      await screen.findByRole('button', { name: /workbench\.mail\.chip_attachments/ })
    ).toBeInTheDocument();
  });

  it('searches the words when Enter is pressed, never on every key', async () => {
    const { user } = screenOf();
    const box = await screen.findByRole('searchbox', { name: 'workbench.mail.search_label' });

    await user.type(box, 'budget');
    expect(api.get).not.toHaveBeenCalledWith(
      '/workbench/mail/messages',
      expect.objectContaining({
        params: expect.objectContaining({ q: 'b' }),
      })
    );
    await user.keyboard('{Enter}');

    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/workbench/mail/messages', {
        params: { folder: 'system:inbox', q: 'budget' },
        signal: expect.any(AbortSignal),
      })
    );
  });
});

describe('MailTool — acts on a row', () => {
  const firstRow = async () => {
    const link = await screen.findByRole('link', { name: /Subject m1/ });
    const item = link.closest('li');
    if (!item) throw new Error('no row');
    return within(item);
  };

  it('marks a row unread from the row itself, without opening it', async () => {
    api.post.mockResolvedValue({ done: ['m1'], failed: [] });
    const { user } = screenOf();

    await user.click(
      (await firstRow()).getByRole('button', {
        name: 'workbench.mail.row_mark_unread',
      })
    );

    await waitFor(() =>
      expect(posted('/workbench/mail/read-state')).toEqual({ message_ids: ['m1'], read: false })
    );
    expect(nav.push).not.toHaveBeenCalled();
  });

  it('offers « read » on an unread row', async () => {
    page = { items: [row('m1', { is_read: false })], next_page_token: null, skipped: 0 };
    screenOf();

    expect(
      (await firstRow()).getByRole('button', { name: 'workbench.mail.row_mark_read' })
    ).toBeInTheDocument();
  });

  it('trashes a row from the row itself, and closes it when it is the open one', async () => {
    nav.search = 'id=m1';
    api.post.mockResolvedValue(MOVED);
    const { user } = screenOf();

    await user.click((await firstRow()).getByRole('button', { name: 'workbench.mail.row_trash' }));

    await waitFor(() =>
      expect(posted('/workbench/mail/move')).toEqual({
        message_ids: ['m1'],
        to: 'system:trash',
        origin: 'system:inbox',
      })
    );
    await waitFor(() => expect(screen.queryByRole('link', { name: /Subject m1/ })).toBeNull());
    expect(nav.replace).toHaveBeenCalled();
  });
});

describe('MailTool — a selection the listing lost', () => {
  it('says nothing of what is no longer on screen', async () => {
    const { user } = screenOf();
    const boxes = await screen.findAllByRole('checkbox', {
      name: 'workbench.mail.select_message',
    });
    await user.click(boxes[1]!);
    page = { items: [row('m1')], next_page_token: null, skipped: 0 };

    await user.click(screen.getByRole('button', { name: 'workbench.states.refresh' }));

    await waitFor(() =>
      expect(
        screen.queryByRole('region', { name: 'workbench.mail.selection_region' })
      ).not.toBeInTheDocument()
    );
  });
});

describe('MailTool — a range of messages', () => {
  it('selects the messages between the last one ticked and the one ticked with Shift', async () => {
    page = {
      items: [row('m1'), row('m2'), row('m3'), row('m4')],
      next_page_token: null,
      skipped: 0,
    };
    const { user } = screenOf();
    const boxes = await screen.findAllByRole('checkbox', {
      name: 'workbench.mail.select_message',
    });

    await user.click(boxes[0]!);
    await user.keyboard('{Shift>}');
    await user.click(boxes[2]!);
    await user.keyboard('{/Shift}');

    expect(boxes.map(box => (box as HTMLInputElement).checked)).toEqual([true, true, true, false]);
  });
});

describe('MailTool — after a message goes to the trash', () => {
  it('opens the next one on a large screen', async () => {
    nav.search = 'id=m1';
    api.post.mockResolvedValue(MOVED);
    const { user } = screenOf();
    const reader = await screen.findByRole('article');

    await user.click(await within(reader).findByRole('button', { name: /workbench\.mail\.trash/ }));

    await waitFor(() =>
      expect(nav.replace).toHaveBeenCalledWith('/en/dashboard/tools/mail?id=m2', { scroll: false })
    );
  });

  it('goes back to the list on a phone', async () => {
    media.desktop = false;
    nav.search = 'id=m1';
    api.post.mockResolvedValue(MOVED);
    const { user } = screenOf();
    const reader = await screen.findByRole('article');

    await user.click(await within(reader).findByRole('button', { name: /workbench\.mail\.trash/ }));

    await waitFor(() =>
      expect(nav.replace).toHaveBeenCalledWith('/en/dashboard/tools/mail', { scroll: false })
    );
  });
});

describe('MailTool — sorting', () => {
  const firstRow = async () => {
    const link = await screen.findByRole('link', { name: /Subject m1/ });
    return within(link.closest('li')!);
  };

  it('archives from the inbox, and comes back by the toast', async () => {
    api.post.mockResolvedValue(MOVED);
    const { user } = screenOf();

    await user.click(
      (await firstRow()).getByRole('button', { name: 'workbench.mail.row_archive' })
    );

    await waitFor(() =>
      expect(posted('/workbench/mail/move')).toEqual({
        message_ids: ['m1'],
        to: 'system:archive',
        origin: 'system:inbox',
      })
    );
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    const undo = vi.mocked(toast.success).mock.lastCall?.[1]?.action as
      | { onClick: () => void }
      | undefined;
    undo?.onClick();

    await waitFor(() =>
      expect(posted('/workbench/mail/move')).toEqual({
        message_ids: ['n1'],
        to: 'system:inbox',
        origin: 'system:archive',
      })
    );
  });

  it('stars a row, and a row says what it carries', async () => {
    page = {
      items: [row('m1', { has_attachments: true }), row('m2')],
      next_page_token: null,
      skipped: 0,
    };
    api.post.mockResolvedValue({ done: ['m1'], failed: [] });
    const { user } = screenOf();
    const first = await firstRow();

    expect(first.getByRole('img', { name: 'workbench.mail.has_attachments' })).toBeInTheDocument();
    await user.click(first.getByRole('button', { name: 'workbench.mail.row_star' }));

    await waitFor(() =>
      expect(posted('/workbench/mail/star')).toEqual({ message_ids: ['m1'], starred: true })
    );
    expect(await first.findByRole('img', { name: 'workbench.mail.starred' })).toBeInTheDocument();
  });

  it('moves through the picker, which offers neither what is listed nor a view', async () => {
    api.post.mockResolvedValue(MOVED);
    const { user } = screenOf();

    await user.click((await firstRow()).getByRole('button', { name: 'workbench.mail.row_move' }));
    const picker = await screen.findByRole('dialog', { name: 'workbench.mail.move_title' });

    expect(within(picker).queryByRole('button', { name: /folders\.inbox/ })).toBeNull();
    expect(within(picker).queryByRole('button', { name: /folders\.sent/ })).toBeNull();
    await user.click(within(picker).getByRole('button', { name: 'Work' }));

    await waitFor(() =>
      expect(posted('/workbench/mail/move')).toEqual({
        message_ids: ['m1'],
        to: 'Label_7',
        origin: 'system:inbox',
      })
    );
    expect(screen.queryByRole('dialog', { name: 'workbench.mail.move_title' })).toBeNull();
  });

  it('offers no archive from a label where the mailbox has no archive folder', async () => {
    nav.search = 'folder=Label_7';
    screenOf();

    const first = await firstRow();

    expect(first.queryByRole('button', { name: 'workbench.mail.row_archive' })).toBeNull();
    expect(first.getByRole('button', { name: 'workbench.mail.row_move' })).toBeInTheDocument();
  });

  it('archives from a folder where the mailbox has an archive folder', async () => {
    features = OUTLOOK;
    folders = WITH_ARCHIVE;
    nav.search = 'folder=Label_7';
    screenOf();

    expect(
      (await firstRow()).getByRole('button', { name: 'workbench.mail.row_archive' })
    ).toBeInTheDocument();
  });

  it('in the spam, a message is said not to be one', async () => {
    nav.search = 'folder=system%3Aspam';
    api.post.mockResolvedValue(MOVED);
    const { user } = screenOf();

    await user.click(
      (await firstRow()).getByRole('button', { name: 'workbench.mail.row_not_spam' })
    );

    await waitFor(() =>
      expect(posted('/workbench/mail/move')).toEqual({
        message_ids: ['m1'],
        to: 'system:inbox',
        origin: 'system:spam',
      })
    );
  });

  it('in the trash, a message is restored and nothing goes to the trash', async () => {
    nav.search = 'folder=system%3Atrash';
    api.post.mockResolvedValue(MOVED);
    const { user } = screenOf();
    const first = await firstRow();

    expect(first.queryByRole('button', { name: 'workbench.mail.row_trash' })).toBeNull();
    await user.click(first.getByRole('button', { name: 'workbench.mail.row_restore' }));

    await waitFor(() =>
      expect(posted('/workbench/mail/move')).toEqual({
        message_ids: ['m1'],
        to: 'system:inbox',
        origin: 'system:trash',
      })
    );
  });

  it('asks before deleting for good, and sends nothing on a refusal', async () => {
    features = OUTLOOK;
    nav.search = 'folder=system%3Atrash';
    api.post.mockResolvedValue({ done: ['m1'], failed: [] });
    const { user } = screenOf();

    await user.click(
      (await firstRow()).getByRole('button', { name: 'workbench.mail.row_delete_forever' })
    );
    const asked = await screen.findByRole('alertdialog');
    await user.click(within(asked).getByRole('button', { name: /cancel/i }));

    expect(postsTo('/workbench/mail/delete-forever')).toBe(0);

    await user.click(
      (await firstRow()).getByRole('button', { name: 'workbench.mail.row_delete_forever' })
    );
    const again = await screen.findByRole('alertdialog');
    await user.click(within(again).getByRole('button', { name: 'workbench.mail.delete_forever' }));

    await waitFor(() =>
      expect(posted('/workbench/mail/delete-forever')).toEqual({ message_ids: ['m1'] })
    );
  });

  it('empties the trash after asking, and says what remains', async () => {
    features = OUTLOOK;
    nav.search = 'folder=system%3Atrash';
    api.post.mockResolvedValue({ deleted: 200, remaining: true });
    const { user } = screenOf();

    await user.click(await screen.findByRole('button', { name: 'workbench.mail.empty_trash' }));
    const asked = await screen.findByRole('alertdialog');
    await user.click(within(asked).getByRole('button', { name: 'workbench.mail.empty_trash' }));

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('workbench.mail.emptied_more'));
  });

  it('says what a mailbox that deletes by itself does with its trash', async () => {
    nav.search = 'folder=system%3Atrash';
    screenOf();

    expect(await screen.findByText('workbench.mail.trash_auto_note')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'workbench.mail.empty_trash' })).toBeNull();
  });

  it('draws what each folder leaves unread, on the pane and on the pill', async () => {
    unread = { counts: { 'system:inbox': 3 }, truncated: false };
    screenOf();

    expect(
      await screen.findByRole('link', { name: 'workbench.mail.folder_unread' })
    ).toBeInTheDocument();
    expect(await screen.findByText('workbench.rail.unread')).toBeInTheDocument();
  });

  it('draws no figure for a folder with nothing unread', async () => {
    unread = { counts: { 'system:inbox': 0 }, truncated: false };
    screenOf();

    await firstRow();

    expect(screen.queryByText('workbench.rail.unread')).toBeNull();
    expect(screen.queryByRole('link', { name: 'workbench.mail.folder_unread' })).toBeNull();
  });
});

describe('MailTool — the header below lg', () => {
  it('says « New email » in words, and offers the selection by its name', async () => {
    media.desktop = false;
    screenOf();

    const [header] = await screen.findAllByRole('button', { name: 'workbench.mail.new_message' });

    expect(header?.querySelector('.sr-only')).toBeNull();
    expect(screen.getByRole('button', { name: 'workbench.mail.select' })).toBeInTheDocument();
  });
});

describe('MailTool — the composer', () => {
  async function opened() {
    const rendered = screenOf();
    // The header's (below lg) and the pane's (from lg): CSS shows one, jsdom has both.
    const [compose] = await screen.findAllByRole('button', { name: 'workbench.mail.new_message' });
    await rendered.user.click(compose!);
    const dialog = await screen.findByRole('dialog', {
      name: 'workbench.mail.compose.title_new',
    });
    await rendered.user.type(
      within(dialog).getByRole('combobox', { name: 'workbench.mail.compose.to' }),
      'ana@example.org'
    );
    await rendered.user.type(
      within(dialog).getByRole('textbox', { name: 'workbench.mail.compose.body' }),
      'Hello Ana'
    );
    return { ...rendered, dialog };
  }

  it('sends once whatever is pressed twice, then closes and says it left', async () => {
    const sent = deferred<unknown>();
    api.post.mockReturnValueOnce(sent.promise);
    const { user, dialog } = await opened();
    const send = within(dialog).getByRole('button', { name: /workbench\.mail\.compose\.send/ });

    await user.click(send);
    await user.click(send);
    // Enter in a field submits the form past the button's own guard.
    await user.type(
      within(dialog).getByRole('textbox', { name: 'workbench.mail.compose.subject' }),
      'Hi{Enter}'
    );
    expect(postsTo('/workbench/mail/send')).toBe(1);

    await act(async () => sent.answer({ id: 's1', thread_id: 't1' }));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('workbench.mail.sent'));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(posted('/workbench/mail/send')).toMatchObject({
      to: ['ana@example.org'],
      body: 'Hello Ana',
      idempotency_key: expect.any(String),
    });
  });

  it('keeps the words when nobody knows whether it left, says to look in Sent, sends nothing more', async () => {
    api.post.mockRejectedValueOnce(
      new ApiError('lost', 504, { detail: { code: 'outcome_unknown' } })
    );
    const { user, dialog } = await opened();
    const send = within(dialog).getByRole('button', { name: /workbench\.mail\.compose\.send/ });

    await user.click(send);

    expect(await within(dialog).findByText('workbench.mail.compose.unknown')).toBeInTheDocument();
    expect(
      within(dialog).getByRole('textbox', { name: 'workbench.mail.compose.body' })
    ).toHaveValue('Hello Ana');
    await user.click(send);
    expect(postsTo('/workbench/mail/send')).toBe(1);
  });

  it('puts a recipient the server could not read under its own field', async () => {
    api.post.mockRejectedValueOnce(
      new ApiError('refused', 422, {
        detail: { code: 'invalid_recipient', field: 'to', index: 0 },
      })
    );
    const { user, dialog } = await opened();

    await user.click(
      within(dialog).getByRole('button', { name: /workbench\.mail\.compose\.send/ })
    );

    const to = within(dialog).getByRole('combobox', { name: 'workbench.mail.compose.to' });
    await waitFor(() =>
      expect(to).toHaveAccessibleDescription('workbench.errors.invalid_recipient_at')
    );
  });
});

describe('MailTool — the images a message carries', () => {
  const PNG = 'data:image/png;base64,iVBORw0KGgo=';

  it('reads them apart, once its layout names them, and draws them', async () => {
    nav.search = 'id=m1';
    htmls.m1 = { html: '<img src="cid:logo@x">', truncated: false };
    inlineAnswer = { images: [{ cid: 'logo@x', data_url: PNG }], skipped: 0 };
    screenOf();

    const frame = await screen.findByTitle('workbench.mail.html_frame_title');

    await waitFor(() => expect(frame.getAttribute('srcdoc')).toContain(PNG));
    expect(
      api.get.mock.calls.find(([path]) => path === '/workbench/mail/message/images')?.[1]
    ).toMatchObject({ params: { message_id: 'm1', cid: ['logo@x'] } });
  });

  it('asks for nothing when its layout names none', async () => {
    nav.search = 'id=m1';
    htmls.m1 = { html: '<p>Hello</p>', truncated: false };
    screenOf();

    await screen.findByTitle('workbench.mail.html_frame_title');

    expect(api.get.mock.calls.some(([path]) => path === '/workbench/mail/message/images')).toBe(
      false
    );
  });

  it('says what it could not read', async () => {
    nav.search = 'id=m1';
    htmls.m1 = { html: '<img src="cid:logo@x">', truncated: false };
    const answered = api.get.getMockImplementation();
    api.get.mockImplementation((path: string, options?: { params?: { id?: string } }) =>
      path === '/workbench/mail/message/images'
        ? Promise.reject(new Error('gone'))
        : answered?.(path, options)
    );
    screenOf();

    expect(await screen.findByText('workbench.mail.inline_skipped')).toBeInTheDocument();
  });

  it('says what it left out', async () => {
    nav.search = 'id=m1';
    htmls.m1 = { html: '<img src="cid:logo@x">', truncated: false };
    inlineAnswer = { images: [], skipped: 2 };
    screenOf();

    expect(await screen.findByText('workbench.mail.inline_skipped')).toBeInTheDocument();
  });
});

describe('MailTool — leaving a mailing list', () => {
  const opened = async (ways: Partial<typeof NO_WAY>) => {
    leaving = { ...NO_WAY, ...ways };
    nav.search = 'id=m1';
    const rendered = screenOf();
    await screen.findByRole('heading', { name: 'Subject m1' });
    return rendered;
  };

  it('offers nothing on a message that names no way out', async () => {
    await opened({});

    expect(screen.queryByRole('button', { name: 'workbench.mail.unsubscribe' })).toBeNull();
    expect(screen.queryByRole('link', { name: 'workbench.mail.unsubscribe' })).toBeNull();
  });

  it('asks first, then posts by the message, never by an address from the page', async () => {
    api.post.mockResolvedValue(undefined);
    const { user } = await opened({ web_url: 'https://example.org/leave', one_click: true });

    await user.click(await screen.findByRole('button', { name: 'workbench.mail.unsubscribe' }));
    await answerConfirmDialog(user, true);

    await waitFor(() =>
      expect(posted('/workbench/mail/unsubscribe')).toEqual({ message_id: 'm1' })
    );
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('workbench.mail.unsubscribed'));
  });

  it('sends nothing when the person says no', async () => {
    const { user } = await opened({ web_url: 'https://example.org/leave', one_click: true });

    await user.click(await screen.findByRole('button', { name: 'workbench.mail.unsubscribe' }));
    await answerConfirmDialog(user, false);

    expect(postsTo('/workbench/mail/unsubscribe')).toBe(0);
  });

  it('falls back on the sender’s page when the one click is refused', async () => {
    api.post.mockRejectedValue(new Error('refused'));
    const { user } = await opened({ web_url: 'https://example.org/leave', one_click: true });

    await user.click(await screen.findByRole('button', { name: 'workbench.mail.unsubscribe' }));
    await answerConfirmDialog(user, true);

    const link = await screen.findByRole('link', { name: 'workbench.mail.unsubscribe' });
    expect(link).toHaveAttribute('href', 'https://example.org/leave');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('opens the sender’s page where it promises no one click', async () => {
    await opened({ web_url: 'https://example.org/leave' });

    expect(await screen.findByRole('link', { name: 'workbench.mail.unsubscribe' })).toHaveAttribute(
      'target',
      '_blank'
    );
  });

  it('writes to the list where it names an address alone', async () => {
    const { user } = await opened({ mail_to: 'leave@example.org?subject=stop' });

    await user.click(await screen.findByRole('button', { name: 'workbench.mail.unsubscribe' }));

    expect(await screen.findByRole('combobox', { name: 'workbench.mail.compose.to' })).toHaveValue(
      'leave@example.org'
    );
    expect(screen.getByRole('textbox', { name: 'workbench.mail.compose.subject' })).toHaveValue(
      'stop'
    );
  });
});

describe('MailTool — printing a message', () => {
  afterEach(() => document.querySelectorAll('iframe[data-print]').forEach(frame => frame.remove()));

  it('offers it from the reader, in a browser', async () => {
    nav.search = 'id=m1';
    const { user } = screenOf();

    await user.click(await screen.findByRole('button', { name: 'workbench.mail.more_actions' }));

    expect(
      await screen.findByRole('menuitem', { name: 'workbench.mail.print' })
    ).toBeInTheDocument();
  });

  it('offers nothing of the kind in the Android app, which has no printer dialog', async () => {
    media.androidShell = true;
    nav.search = 'id=m1';
    const { user } = screenOf();

    await user.click(await screen.findByRole('button', { name: 'workbench.mail.more_actions' }));

    await screen.findByRole('menuitem', { name: 'workbench.mail.archive' });
    expect(screen.queryByRole('menuitem', { name: 'workbench.mail.print' })).toBeNull();
  });
});

/** The rail with these tools ready beside the mailbox. */
function answerRail(tools: readonly WorkbenchToolId[]) {
  const base = rail('ready', features);
  const others = tools.map(tool => ({ ...base.tools[0]!, tool }));
  const reader = api.get.getMockImplementation();
  api.get.mockImplementation((path: string, options?: { params?: { id?: string } }) =>
    path === '/workbench'
      ? Promise.resolve({ ...base, tools: [...base.tools, ...others] })
      : reader?.(path, options)
  );
}

describe('MailTool — from a message to the other tools', () => {
  const opened = async (tools: WorkbenchToolId[]) => {
    answerRail(tools);
    nav.search = 'id=m1';
    const rendered = screenOf();
    await rendered.user.click(
      await screen.findByRole('button', { name: 'workbench.mail.more_actions' })
    );
    return rendered;
  };

  afterEach(() => {
    takeHandoff('task');
    takeHandoff('event');
    takeHandoff('contact');
  });

  it('turns the message into a task, pointing back at it', async () => {
    const { user } = await opened(['tasks']);

    await user.click(await screen.findByRole('menuitem', { name: 'workbench.mail.to_task' }));

    expect(nav.push).toHaveBeenCalledWith('/en/dashboard/tools/tasks');
    const handed = takeHandoff('task');
    expect(handed?.title).toBe('Subject m1');
    expect(handed?.notes).toContain('/en/dashboard/tools/mail?id=m1');
  });

  it('turns the message into an event', async () => {
    const { user } = await opened(['calendar']);

    await user.click(await screen.findByRole('menuitem', { name: 'workbench.mail.to_event' }));

    expect(nav.push).toHaveBeenCalledWith('/en/dashboard/tools/calendar');
    expect(takeHandoff('event')?.summary).toBe('Subject m1');
  });

  it('saves the sender as a contact', async () => {
    const { user } = await opened(['contacts']);

    await user.click(await screen.findByRole('menuitem', { name: 'workbench.mail.to_contact' }));

    expect(nav.push).toHaveBeenCalledWith('/en/dashboard/tools/contacts');
    expect(takeHandoff('contact')).toEqual({
      kind: 'contact',
      name: 'Sender m1',
      email: 'm1@example.org',
    });
  });

  it('offers no way to a tool that is not ready', async () => {
    await opened([]);

    await screen.findByRole('menuitem', { name: 'workbench.mail.archive' });
    expect(screen.queryByRole('menuitem', { name: 'workbench.mail.to_task' })).toBeNull();
    expect(screen.queryByRole('menuitem', { name: 'workbench.mail.to_event' })).toBeNull();
    expect(screen.queryByRole('menuitem', { name: 'workbench.mail.to_contact' })).toBeNull();
  });

  it('offers no « … » where it would list nothing', async () => {
    answerRail([]);
    media.androidShell = true;
    nav.search = 'folder=system%3Atrash&id=m1';
    screenOf();

    await screen.findByRole('article', { name: 'Subject m1' });

    expect(screen.getByRole('button', { name: 'workbench.ask.label' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'workbench.mail.more_actions' })).toBeNull();
  });

  it('hands the message to the chat outside the address, nothing sent', async () => {
    answerRail([]);
    nav.search = 'id=m1';
    const { user } = screenOf();

    await user.click(await screen.findByRole('button', { name: 'workbench.ask.label' }));
    await user.click(await screen.findByRole('menuitem', { name: 'workbench.ask.label' }));

    expect(openChat).toHaveBeenCalledWith('/en/dashboard/chat');
    expect(nav.push).not.toHaveBeenCalled();
    expect(window.localStorage.getItem('lia.chatDraft.owner')).toBe('workbench.ask.mail');
    expect(api.post).not.toHaveBeenCalled();
  });

  it('hands a ready-made question to the chat, nothing sent', async () => {
    answerRail([]);
    nav.search = 'id=m1';
    const { user } = screenOf();

    await user.click(await screen.findByRole('button', { name: 'workbench.ask.label' }));
    await user.click(await screen.findByRole('menuitem', { name: 'workbench.ask.ready.mail' }));

    expect(openChat).toHaveBeenCalledWith('/en/dashboard/chat');
    expect(window.localStorage.getItem('lia.chatDraft.owner')).toBe(
      'workbench.ask.ready.mail_words'
    );
    expect(api.post).not.toHaveBeenCalled();
  });

  it('opens « Remind me » on who wrote and what about, from the same list', async () => {
    answerRail([]);
    nav.search = 'id=m1';
    const { user } = screenOf();

    await user.click(await screen.findByRole('button', { name: 'workbench.ask.label' }));
    await user.click(await screen.findByRole('menuitem', { name: 'workbench.assist.remind.line' }));

    expect(await screen.findByLabelText('workbench.assist.remind.what')).toHaveValue(
      'workbench.assist.remind.words.mail'
    );
  });
});

describe('MailTool — the bar of a message', () => {
  const opened = async () => {
    const rendered = screenOf();
    await screen.findByRole('article', { name: 'Subject m1' });
    return rendered;
  };
  const acts = () =>
    within(screen.getByTestId('reader-acts'))
      .getAllByRole('button')
      .map(act => act.getAttribute('aria-label'));
  const more = () => screen.findByRole('button', { name: 'workbench.mail.more_actions' });

  beforeEach(() => {
    nav.search = 'id=m1';
  });

  it('ends on the trash, then the question to LIA, « … » before them', async () => {
    await opened();

    expect(acts().slice(-3)).toEqual([
      'workbench.mail.more_actions',
      'workbench.mail.trash',
      'workbench.ask.label',
    ]);
  });

  it('holds archiving, moving and reporting spam behind « … », at every width', async () => {
    const { user } = await opened();

    expect(acts()).not.toContain('workbench.mail.archive');
    expect(acts()).not.toContain('workbench.mail.move_to');
    expect(acts()).not.toContain('workbench.mail.report_spam');
    await user.click(await more());

    const items = await screen.findAllByRole('menuitem');
    expect(items.slice(0, 3).map(item => item.textContent)).toEqual([
      'workbench.mail.archive',
      'workbench.mail.move_to',
      'workbench.mail.report_spam',
    ]);
    expect(items.map(item => item.textContent)).not.toContain('workbench.ask.label');
    items.forEach(item => expect(item).not.toHaveClass('sm:hidden'));
  });

  it('archives from « … »', async () => {
    api.post.mockResolvedValue(MOVED);
    const { user } = await opened();

    await user.click(await more());
    await user.click(await screen.findByRole('menuitem', { name: 'workbench.mail.archive' }));

    await waitFor(() =>
      expect(posted('/workbench/mail/move')).toEqual({
        message_ids: ['m1'],
        to: 'system:archive',
        origin: 'system:inbox',
      })
    );
  });

  it('asks for a folder from « … »', async () => {
    const { user } = await opened();

    await user.click(await more());
    await user.click(await screen.findByRole('menuitem', { name: 'workbench.mail.move_to' }));

    expect(await screen.findByRole('dialog')).toBeInTheDocument();
  });

  it('reports spam from « … »', async () => {
    api.post.mockResolvedValue(MOVED);
    const { user } = await opened();

    await user.click(await more());
    await user.click(await screen.findByRole('menuitem', { name: 'workbench.mail.report_spam' }));

    await waitFor(() =>
      expect(posted('/workbench/mail/move')).toEqual({
        message_ids: ['m1'],
        to: 'system:spam',
        origin: 'system:inbox',
      })
    );
  });

  it('keeps the way back in the bar, and ends on the deletion for good', async () => {
    features = OUTLOOK;
    nav.search = 'folder=system:trash&id=m1';
    await opened();

    expect(acts().slice(-4)).toEqual([
      'workbench.mail.restore',
      'workbench.mail.more_actions',
      'workbench.mail.delete_forever',
      'workbench.ask.label',
    ]);
  });

  it('says the act behind « … » is on its way, and refuses a second one', async () => {
    const running = deferred<typeof MOVED>();
    api.post.mockReturnValue(running.promise);
    const { user } = await opened();

    await user.click(await more());
    await user.click(await screen.findByRole('menuitem', { name: 'workbench.mail.archive' }));

    await waitFor(async () => expect(await more()).toHaveAttribute('aria-busy', 'true'));
    await user.click(await more());
    await user.click(await screen.findByRole('menuitem', { name: 'workbench.mail.report_spam' }));
    expect(postsTo('/workbench/mail/move')).toBe(1);
    running.answer(MOVED);
    await waitFor(async () => expect(await more()).not.toHaveAttribute('aria-busy', 'true'));
  });
});

describe('MailTool — a large screen opens on the newest message', () => {
  const follow = (href: string) => {
    nav.search = href.split('?')[1] ?? '';
  };

  beforeEach(() => {
    media.sideBySide = true;
  });

  it('shows it beside the list, and the address stays what the person asked', async () => {
    screenOf();

    const reader = await screen.findByRole('article', { name: 'Subject m1' });

    expect(within(reader).getByText('Body of m1')).toBeInTheDocument();
    expect(nav.push).not.toHaveBeenCalled();
    expect(nav.replace).not.toHaveBeenCalled();
  });

  it('leaves it unread: nobody opened it', async () => {
    page = { items: [row('m2', { is_read: false }), row('m1')], next_page_token: null, skipped: 0 };
    screenOf();

    await screen.findByRole('article', { name: 'Subject m2' });
    await new Promise(resolve => setTimeout(resolve, MAIL_READ_DWELL_MS + 300));

    expect(postsTo('/workbench/mail/read-state')).toBe(0);
  });

  it('marks it read once the person opens it themselves', async () => {
    page = { items: [row('m2', { is_read: false }), row('m1')], next_page_token: null, skipped: 0 };
    api.post.mockResolvedValue({ done: ['m2'], failed: [] });
    nav.push.mockImplementation(follow);
    const { user, rerender } = screenOf();
    await screen.findByRole('article', { name: 'Subject m2' });

    await user.click(await screen.findByRole('link', { name: /Subject m2/ }));
    rerender(tool());

    await waitFor(() => expect(postsTo('/workbench/mail/read-state')).toBe(1), { timeout: 3000 });
    expect(posted('/workbench/mail/read-state')).toEqual({ message_ids: ['m2'], read: true });
  });

  it('stays closed once the person closes it', async () => {
    const { user, rerender } = screenOf();
    const reader = await screen.findByRole('article', { name: 'Subject m1' });

    await user.click(within(reader).getByRole('button', { name: 'workbench.mail.close_message' }));

    await waitFor(() => expect(screen.queryByRole('article')).toBeNull());
    rerender(tool());
    expect(screen.queryByRole('article')).toBeNull();
    expect(nav.replace).not.toHaveBeenCalled();
  });

  it('gives its row the focus back when it closes', async () => {
    const { user } = screenOf();
    await screen.findByRole('article', { name: 'Subject m1' });

    await user.keyboard('{Escape}');
    fireEvent.keyDown(screen.getByRole('article', { name: 'Subject m1' }), { key: 'Escape' });

    await waitFor(() => expect(screen.getByRole('link', { name: /Subject m1/ })).toHaveFocus());
  });

  it('opens nothing over the message the address names', async () => {
    nav.search = 'id=m2';
    screenOf();

    await screen.findByRole('article', { name: 'Subject m2' });

    expect(api.get).not.toHaveBeenCalledWith('/workbench/mail/message', {
      params: { id: 'm1' },
      signal: expect.any(AbortSignal),
    });
  });

  it('opens nothing in another folder', async () => {
    nav.search = 'folder=system:sent';
    screenOf();

    await screen.findByRole('link', { name: /Subject m1/ });

    expect(screen.queryByRole('article')).toBeNull();
  });

  it('opens nothing below the width that holds the list and the reader side by side', async () => {
    media.sideBySide = false;
    screenOf();

    await screen.findByRole('link', { name: /Subject m1/ });

    expect(screen.queryByRole('article')).toBeNull();
  });

  it('opens nothing in an empty inbox', async () => {
    page = { items: [], next_page_token: null, skipped: 0 };
    screenOf();

    await screen.findByRole('button', { name: 'workbench.states.refresh' });
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/workbench/mail/messages', expect.anything())
    );

    expect(screen.queryByRole('article')).toBeNull();
  });
});

describe('MailTool — its keys', () => {
  const press = (key: string) => fireEvent.keyDown(window, { key });

  it('opens a new message on « c »', async () => {
    screenOf();
    await screen.findByRole('link', { name: /Subject m1/ });

    press('c');

    expect(
      await screen.findByRole('dialog', { name: 'workbench.mail.compose.title_new' })
    ).toBeInTheDocument();
  });

  it('opens the first message on « j », so « back » closes it', async () => {
    screenOf();
    await screen.findByRole('link', { name: /Subject m1/ });

    press('j');

    expect(nav.push).toHaveBeenCalledWith('/en/dashboard/tools/mail?id=m1', { scroll: false });
  });

  it('walks from one message to the next keeping one « back »', async () => {
    nav.search = 'id=m1';
    screenOf();
    await screen.findByRole('article');
    await screen.findByRole('link', { name: /Subject m2/ });

    press('j');

    expect(nav.replace).toHaveBeenCalledWith('/en/dashboard/tools/mail?id=m2', { scroll: false });
    expect(nav.push).not.toHaveBeenCalled();
  });

  it('stops at the end of the list', async () => {
    nav.search = 'id=m3';
    messages.m3 = message('m3');
    screenOf();
    await screen.findByRole('article');

    press('j');

    expect(nav.replace).not.toHaveBeenCalled();
  });

  it('asks nothing of « r » with no message open', async () => {
    screenOf();
    await screen.findByRole('link', { name: /Subject m1/ });

    press('r');
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('replies to the open message on « r »', async () => {
    nav.search = 'id=m1';
    screenOf();
    await screen.findByRole('heading', { name: 'Subject m1' });

    press('r');

    expect(
      await screen.findByRole('dialog', { name: 'workbench.mail.compose.title_reply' })
    ).toBeInTheDocument();
  });
});

describe('MailTool — what LIA does on a message', () => {
  const SUMMARY_PATH = '/tool-assists/mail/summary';
  const REPLY_PATH = '/tool-assists/mail/reply';
  const ANSWER = {
    gist: 'Ana asks for the budget.',
    key_points: ['Due Friday'],
    actions: ['Send the budget'],
    category: 'work',
    importance: 'high',
    usage: { tokens_in: 90, tokens_out: 30, tokens_cache: 0, cost_eur: 0.001, model_name: 'm' },
  };
  const line = (name: string) => screen.findByRole('menuitem', { name });

  async function opened(ready: readonly WorkbenchToolId[] = []) {
    instance.assists = true;
    answerRail(ready);
    nav.search = 'id=m1';
    api.post.mockImplementation((path: string) =>
      Promise.resolve(path === REPLY_PATH ? { text: 'Dear Ana, yes.', usage: null } : ANSWER)
    );
    const rendered = screenOf();
    await rendered.user.click(await screen.findByRole('button', { name: 'workbench.ask.label' }));
    return rendered;
  }

  it('asks nothing of a model until a line is pressed', async () => {
    await opened();

    await line('workbench.assist.mail.summary');

    expect(api.post).not.toHaveBeenCalled();
  });

  it('offers no line of a model where the instance withholds it', async () => {
    answerRail([]);
    nav.search = 'id=m1';
    const { user } = screenOf();

    await user.click(await screen.findByRole('button', { name: 'workbench.ask.label' }));

    expect(await line('workbench.assist.remind.line')).toBeInTheDocument();
    expect(screen.queryByRole('menuitem', { name: 'workbench.assist.mail.summary' })).toBeNull();
  });

  it('sums the message up in the reader, by its id, with what it cost', async () => {
    const { user } = await opened();

    await user.click(await line('workbench.assist.mail.summary'));

    expect(await screen.findByText('Ana asks for the budget.')).toBeInTheDocument();
    expect(screen.getByText('Due Friday')).toBeInTheDocument();
    expect(posted(SUMMARY_PATH)).toEqual({ message_id: 'm1' });
    expect(screen.getByText(/common\.llm_usage\.tokens/)).toBeInTheDocument();
  });

  it('leaves the message whole under the answer', async () => {
    const { user } = await opened();

    await user.click(await line('workbench.assist.mail.summary'));
    await screen.findByText('Ana asks for the budget.');

    expect(screen.getByRole('heading', { name: 'Subject m1' })).toBeInTheDocument();
    expect(screen.getByText('Body of m1')).toBeInTheDocument();
  });

  it('closes the answer, and the reader is as it was', async () => {
    const { user } = await opened();

    await user.click(await line('workbench.assist.mail.summary'));
    await screen.findByText('Ana asks for the budget.');
    await user.click(screen.getByRole('button', { name: 'workbench.assist.close' }));

    expect(screen.queryByText('Ana asks for the budget.')).toBeNull();
  });

  it('makes a task of an action it found, pointing back at the message', async () => {
    const { user } = await opened(['tasks']);

    await user.click(await line('workbench.assist.mail.summary'));
    await user.click(
      await screen.findByRole('button', { name: 'workbench.assist.mail.to_task' })
    );

    expect(nav.push).toHaveBeenCalledWith('/en/dashboard/tools/tasks');
    const handed = takeHandoff('task');
    expect(handed?.title).toBe('Send the budget');
    expect(handed?.notes).toContain('/en/dashboard/tools/mail?id=m1');
  });

  it('opens the calendar on the event it read, the message linked: nothing is created', async () => {
    const { user } = await opened(['calendar']);
    const proposal = {
      summary: 'Lunch with Ana',
      start_date: '2026-11-05',
      start_time: '12:00',
      end_date: null,
      end_time: null,
      all_day: false,
      location: '',
      description: 'At the usual place',
      attendees: [],
      repeat: 'none',
    };
    api.post.mockResolvedValueOnce({ event: proposal, usage: null });

    await user.click(await line('workbench.assist.mail.to_event'));

    await waitFor(() => expect(nav.push).toHaveBeenCalledWith('/en/dashboard/tools/calendar'));
    const handed = takeHandoff('event');
    expect(handed?.summary).toBe('Lunch with Ana');
    expect(handed?.proposal?.start_date).toBe('2026-11-05');
    expect(handed?.description).toContain('At the usual place');
    expect(handed?.description).toContain('/en/dashboard/tools/mail?id=m1');
    expect(posted('/tool-assists/mail/event')).toEqual({ message_id: 'm1' });
  });

  it('opens the tasks on what it read, its day kept', async () => {
    const { user } = await opened(['tasks']);
    api.post.mockResolvedValueOnce({
      task: { title: 'Send the budget', notes: '', due: '2026-11-06', list_name: null },
      usage: null,
    });

    await user.click(await line('workbench.assist.mail.to_task_line'));

    await waitFor(() => expect(nav.push).toHaveBeenCalledWith('/en/dashboard/tools/tasks'));
    const handed = takeHandoff('task');
    expect(handed?.title).toBe('Send the budget');
    expect(handed?.due).toBe('2026-11-06');
  });

  it('says it found no event, and goes nowhere', async () => {
    const { user } = await opened(['calendar']);
    api.post.mockRejectedValueOnce(
      new ApiError('no', 422, { detail: { code: 'assist_not_found' } })
    );

    await user.click(await line('workbench.assist.mail.to_event'));

    expect(await screen.findByRole('alert')).toHaveTextContent('workbench.errors.assist_not_found');
    expect(nav.push).not.toHaveBeenCalled();
  });

  it('offers no event where no calendar is ready', async () => {
    await opened();

    await line('workbench.assist.mail.summary');

    expect(screen.queryByRole('menuitem', { name: 'workbench.assist.mail.to_event' })).toBeNull();
  });

  it('offers no task where no tasks tool is ready', async () => {
    const { user } = await opened();

    await user.click(await line('workbench.assist.mail.summary'));
    await screen.findByText('Send the budget');

    expect(screen.queryByRole('button', { name: 'workbench.assist.mail.to_task' })).toBeNull();
  });

  it('tells a refusal in the reader, and leaves the message alone', async () => {
    const { user } = await opened();
    api.post.mockRejectedValueOnce(new ApiError('no', 429, { detail: { code: 'assist_quota' } }));

    await user.click(await line('workbench.assist.mail.summary'));

    expect(await screen.findByRole('alert')).toHaveTextContent('workbench.errors.assist_quota');
    expect(screen.getByText('Body of m1')).toBeInTheDocument();
  });

  it('opens the reply with LIA’s proposal, and writes nothing until the person says so', async () => {
    const { user } = await opened();

    await user.click(await line('workbench.assist.mail.reply'));

    expect(await screen.findByText('Dear Ana, yes.')).toBeInTheDocument();
    expect(posted(REPLY_PATH)).toEqual({ message_id: 'm1', instruction: null });
    // The proposal stands in a dialog over the composer, which it hides from the ear meanwhile.
    expect(
      screen.getByRole('textbox', { name: 'workbench.mail.compose.body', hidden: true })
    ).toHaveValue('');
  });

  it('puts the proposal in the reply when the person takes it, and sends nothing', async () => {
    const { user } = await opened();

    await user.click(await line('workbench.assist.mail.reply'));
    await user.click(await screen.findByRole('button', { name: 'workbench.assist.writing.use' }));

    expect(
      await screen.findByRole('textbox', { name: 'workbench.mail.compose.body' })
    ).toHaveValue('Dear Ana, yes.');
    expect(api.post).toHaveBeenCalledTimes(1);
  });
});

describe('MailTool — what another tool hands it', () => {
  it('opens a new message to the address it was given', async () => {
    handOff({ kind: 'compose', to: 'ana@example.org' });
    screenOf();

    const to = await screen.findByRole('combobox', { name: 'workbench.mail.compose.to' });

    expect(to).toHaveValue('ana@example.org');
  });
});

describe('MailTool — a file of the drive', () => {
  it('opens a new message carrying the file it was given', async () => {
    handOff({
      kind: 'compose',
      to: '',
      file: {
        id: 'f1',
        filename: 'Report.pdf',
        mime_type: 'application/pdf',
        size: 3,
        origin: 'drive',
        expires_at: null,
      },
    });
    screenOf();

    const dialog = await screen.findByRole('dialog', {
      name: 'workbench.mail.compose.title_new',
    });

    expect(within(dialog).getByText('Report.pdf')).toBeInTheDocument();
  });
});

describe('MailTool — unavailable', () => {
  it('says what to do when no mailbox is connected', async () => {
    api.get.mockImplementation((path: string) =>
      path === '/workbench'
        ? Promise.resolve(rail('not_connected'))
        : Promise.reject(new Error('no'))
    );
    screenOf();

    expect(await screen.findByText('workbench.states.not_connected_title')).toBeInTheDocument();
    expect(api.get).not.toHaveBeenCalledWith('/workbench/mail/folders', expect.anything());
  });
});

describe('MailTool — panes sized by hand', () => {
  it('names its separator and drives the pane it sits beside, back to the layout on Enter', async () => {
    screenOf();
    const separator = await screen.findByRole('separator', {
      name: 'workbench.panes.mail_folders',
    });
    const pane = document.getElementById(separator.getAttribute('aria-controls') ?? '');

    expect(pane).toHaveAccessibleName('workbench.mail.folders_title');
    fireEvent.keyDown(separator, { key: 'End' });
    expect(pane?.style.getPropertyValue('--pane-w')).toMatch(/^\d+px$/);
    fireEvent.keyDown(separator, { key: 'Enter' });
    expect(pane?.style.getPropertyValue('--pane-w')).toBe('');
  });
});
