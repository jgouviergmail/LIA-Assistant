/**
 * The « Tools » mail screen (ADR-369, Task 4.7).
 *
 * The open message rides the address (`?id=`); the arrows walk the list, Enter
 * opens, Escape closes; a selection is trashed and what could not be is said;
 * the open message's read state shows at once and is rolled back when refused;
 * the chips narrow the listing; a message is sent once whatever is pressed
 * twice, and an outcome nobody knows keeps the words and says to look in Sent.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  act,
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
} from '@/lib/workbench/types';

type ShellConfig = Pick<AppConfig, 'capabilities'> & { features: { workbench_enabled?: boolean } };

const { api, nav, toast, media } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() },
  nav: { search: '', push: vi.fn(), replace: vi.fn() },
  toast: { error: vi.fn(), success: vi.fn() },
  media: { desktop: true },
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
vi.mock('sonner', () => ({ toast }));
vi.mock('next/navigation', () => ({
  usePathname: () => '/en/dashboard/tools/mail',
  useRouter: () => ({ push: nav.push, replace: nav.replace, back: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams(nav.search),
}));
vi.mock('@/hooks/useMediaQuery', () => ({ useMediaQuery: () => media.desktop }));
vi.mock('@/hooks/useAppConfig', async importOriginal => ({
  ...(await importOriginal<typeof import('@/hooks/useAppConfig')>()),
  useAppConfig: () => ({
    config: { features: { workbench_enabled: true }, capabilities: {} } satisfies ShellConfig,
    loading: false,
    error: null,
  }),
}));

import { WorkbenchShell } from '../../WorkbenchShell';
import { MailTool } from '../MailTool';

const GMAIL: WorkbenchFeature[] = ['mark_read', 'drafts', 'attachments', 'labels'];

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
      calendar_window_max_events: 500,
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
    { id: 'Label_7', kind: 'user', role: null, name: 'Work' },
  ],
};

let features: WorkbenchFeature[];
let page: { items: MailSummary[]; next_page_token: string | null; skipped: number };
let messages: Record<string, MailMessage>;
/** Each message's original layout, as the server answers it (none by default), or a refusal. */
let htmls: Record<string, MailHtml | Error>;

beforeEach(() => {
  vi.clearAllMocks();
  nav.search = '';
  media.desktop = true;
  features = GMAIL;
  page = { items: [row('m1'), row('m2'), row('m3')], next_page_token: null, skipped: 0 };
  messages = { m1: message('m1'), m2: message('m2', { is_read: false }) };
  htmls = {};
  api.get.mockImplementation((path: string, options?: { params?: { id?: string } }) => {
    if (path === '/workbench') return Promise.resolve(rail('ready', features));
    if (path === '/workbench/mail/folders') return Promise.resolve(FOLDERS);
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

describe('MailTool — the original layout', () => {
  const FRAME = 'workbench.mail.html_frame_title';

  it('draws an HTML message in its frame, and its text on demand', async () => {
    htmls = { m1: { html: '<p>Original of m1</p>', truncated: false } };
    nav.search = 'id=m1';
    const { user } = screenOf();

    const reader = await screen.findByRole('article', { name: 'Subject m1' });
    const frame = await within(reader).findByTitle(FRAME);
    expect(frame.getAttribute('srcdoc')).toContain('<p>Original of m1</p>');
    expect(within(reader).queryByText('Body of m1')).not.toBeInTheDocument();
    expect(within(reader).getByText('workbench.mail.html_notice')).toBeInTheDocument();

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
    api.post.mockResolvedValueOnce({ done: ['m1'], failed: [{ id: 'm2', status: 'failed' }] });
    const { user } = screenOf();

    const boxes = await screen.findAllByRole('checkbox', {
      name: 'workbench.mail.select_message',
    });
    await user.click(boxes[0]!);
    await user.click(boxes[1]!);
    const bar = screen.getByRole('region', { name: 'workbench.mail.selection_region' });
    await user.click(within(bar).getByRole('button', { name: /workbench\.mail\.trash/ }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('workbench.mail.partial'));
    expect(posted('/workbench/mail/trash')).toEqual({ message_ids: ['m1', 'm2'] });
    expect(screen.queryByRole('link', { name: /Subject m1/ })).toBeNull();
    expect(screen.getByRole('link', { name: /Subject m2/ })).toBeInTheDocument();
    expect(
      screen.getAllByRole('checkbox', { name: 'workbench.mail.select_message' })[0]
    ).toBeChecked();
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
