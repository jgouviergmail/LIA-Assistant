/**
 * One search across the tools (ADR-369, lot 13): Ctrl+K or the button opens it, wherever the
 * person stands in the section. It reads four providers, so it starts on Enter and never while
 * they are typing. What each tool found is drawn under its name, a tool with nothing says so, a
 * tool that failed is named, a cut is said and so is a mailbox searched from its inbox alone.
 */
import { fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, waitFor, within } from '@/__tests__/test-utils';
import type {
  GlobalSearch,
  SearchHit,
  WorkbenchAvailability,
  WorkbenchToolId,
} from '@/lib/workbench/types';

const { get, openChat } = vi.hoisted(() => ({ get: vi.fn(), openChat: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { id: 'owner' } }) }));
vi.mock('@/lib/chat-deep-link', () => ({ openChatDeepLink: openChat }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { get },
}));
vi.mock('next/link', () => ({
  default: ({
    href,
    onClick,
    children,
    className,
  }: {
    href: string;
    onClick?: () => void;
    children: React.ReactNode;
    className?: string;
  }) => (
    <a
      href={href}
      className={className}
      onClick={event => {
        event.preventDefault();
        onClick?.();
      }}
    >
      {children}
    </a>
  ),
}));

import { WorkbenchSearch } from '../WorkbenchSearch';

const SEARCH = '/workbench/search';
const HIT: SearchHit = {
  id: 'm1',
  title: 'Budget',
  subtitle: 'Ana',
  mail_folder: 'system:all',
  calendar_id: null,
  day: null,
  is_folder: false,
};
const FOUND: GlobalSearch = {
  results: [
    { tool: 'mail', hits: [HIT], truncated: false, inbox_only: false },
    { tool: 'files', hits: [], truncated: false, inbox_only: false },
  ],
  failed: [],
};

function rail(ready: readonly WorkbenchToolId[]): WorkbenchAvailability {
  const tools: readonly WorkbenchToolId[] = ['mail', 'calendar', 'tasks', 'contacts', 'files'];
  return {
    tools: tools.map(tool => ({
      tool,
      state: ready.includes(tool) ? 'ready' : 'not_connected',
      provider: null,
      features: [],
      bounds: {},
    })),
    limits: {
      page_size: 25,
      bulk_max_items: 50,
      download_max_bytes: 1,
      upload_max_bytes: 1,
      calendar_window_max_events: 500,
      send_undo_seconds: 0,
      draft_autosave_seconds: 0,
      search_max_chars: 40,
      assist_text_max_chars: 8000,
      assist_instruction_max_chars: 500,
    },
  };
}

function mount(ready: readonly WorkbenchToolId[] = ['mail', 'files']) {
  return renderWithProviders(<WorkbenchSearch lng="en" availability={rail(ready)} />);
}

const opener = () => screen.getByRole('button', { name: 'workbench.search.open' });
const box = () => screen.getByRole('searchbox', { name: 'workbench.search.label' });

async function asked(user: ReturnType<typeof mount>['user'], words = 'ana') {
  await user.click(opener());
  await user.type(box(), `${words}{Enter}`);
}

beforeEach(() => {
  vi.clearAllMocks();
  get.mockResolvedValue(FOUND);
});

describe('WorkbenchSearch — opening', () => {
  it('opens from its button, the words ready to be typed', async () => {
    const { user } = mount();

    await user.click(opener());

    expect(box()).toHaveFocus();
    expect(box()).toHaveAttribute('maxlength', '40');
  });

  it.each([
    ['Ctrl+K', { ctrlKey: true }],
    ['Cmd+K', { metaKey: true }],
  ])('opens from %s, and the browser keeps nothing of it', (_, chord) => {
    mount();

    const unhandled = fireEvent.keyDown(window, { key: 'k', ...chord });

    expect(unhandled).toBe(false);
    expect(box()).toBeInTheDocument();
  });

  it('reads the key whatever the case it is typed in', () => {
    mount();

    fireEvent.keyDown(window, { key: 'K', ctrlKey: true });

    expect(box()).toBeInTheDocument();
  });

  it.each([
    ['the letter alone', {}],
    ['with Shift', { ctrlKey: true, shiftKey: true }],
    ['with Alt', { ctrlKey: true, altKey: true }],
  ])('leaves the key alone %s', (_, chord) => {
    mount();

    fireEvent.keyDown(window, { key: 'k', ...chord });

    expect(screen.queryByRole('searchbox')).toBeNull();
  });

  it('leaves the chord to what is being written', () => {
    mount();
    const editor = document.createElement('div');
    editor.setAttribute('contenteditable', 'true');
    document.body.append(editor);

    fireEvent.keyDown(editor, { key: 'k', ctrlKey: true });

    expect(screen.queryByRole('searchbox')).toBeNull();
    editor.remove();
  });

  it('leaves the chord to a dialog already open', () => {
    mount();
    const dialog = document.createElement('div');
    dialog.setAttribute('role', 'dialog');
    const field = dialog.appendChild(document.createElement('input'));
    document.body.append(dialog);

    fireEvent.keyDown(field, { key: 'k', ctrlKey: true });

    expect(screen.queryByRole('searchbox')).toBeNull();
    dialog.remove();
  });

  it('takes the chord from a plain search box of a tool', () => {
    mount();
    const field = document.body.appendChild(document.createElement('input'));

    fireEvent.keyDown(field, { key: 'k', ctrlKey: true });

    expect(box()).toBeInTheDocument();
    field.remove();
  });

  it('is offered nowhere no tool can search, and leaves the chord to the browser', () => {
    mount(['tasks']);

    expect(screen.queryByRole('button', { name: 'workbench.search.open' })).toBeNull();
    expect(fireEvent.keyDown(window, { key: 'k', ctrlKey: true })).toBe(true);
    expect(screen.queryByRole('searchbox')).toBeNull();
  });
});

describe('WorkbenchSearch — asking', () => {
  it('asks nothing while the person types', async () => {
    const { user } = mount();

    await user.click(opener());
    await user.type(box(), 'ana');

    expect(get).not.toHaveBeenCalled();
  });

  it('asks once, on Enter, for the words without their spaces', async () => {
    const { user } = mount();

    await asked(user, '  ana ');

    await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
    expect(get.mock.calls[0]?.[0]).toBe(SEARCH);
    expect(get.mock.calls[0]?.[1]).toMatchObject({ params: { q: 'ana' } });
  });

  it('asks nothing for words that are only spaces', async () => {
    const { user } = mount();

    await asked(user, '   ');

    expect(get).not.toHaveBeenCalled();
  });

  it('keeps the answer on screen when the words are emptied', async () => {
    const { user } = mount();

    await asked(user);
    await screen.findByRole('link', { name: /Budget/ });
    await user.clear(box());
    await user.type(box(), '{Enter}');

    expect(screen.getByRole('link', { name: /Budget/ })).toBeInTheDocument();
  });

  it('reads again when the same words are asked again', async () => {
    const { user } = mount();

    await asked(user);
    await screen.findByRole('link', { name: /Budget/ });
    await user.type(box(), '{Enter}');

    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
  });

  it('asks from its button too', async () => {
    const { user } = mount();

    await user.click(opener());
    await user.type(box(), 'ana');
    await user.click(screen.getByRole('button', { name: 'workbench.search.go' }));

    await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
  });
});

describe('WorkbenchSearch — asking LIA instead', () => {
  const askLia = () => screen.getByRole('button', { name: 'workbench.ask.label' });

  beforeEach(() => window.localStorage.clear());

  it('takes the words typed to the chat, unsent, and searches nothing', async () => {
    const { user } = mount();

    await user.click(opener());
    await user.type(box(), 'what did Ana decide?');
    await user.click(askLia());

    expect(window.localStorage.getItem('lia.chatDraft.owner.main')).toBe('what did Ana decide?');
    expect(openChat).toHaveBeenCalledWith('/en/dashboard/chat');
    expect(get).not.toHaveBeenCalled();
  });

  it('takes nothing there while nothing is typed: it keeps the focus and says it is held', async () => {
    const { user } = mount();

    await user.click(opener());
    await user.click(askLia());

    expect(askLia()).toHaveAttribute('aria-disabled', 'true');
    expect(openChat).not.toHaveBeenCalled();
  });
});

describe('WorkbenchSearch — what it found', () => {
  it('draws each tool under its name, each hit a link to it', async () => {
    const { user } = mount();

    await asked(user);

    const mail = await screen.findByRole('region', { name: 'workbench.tools.mail.label' });
    const link = within(mail).getByRole('link', { name: /Budget/ });
    expect(link).toHaveTextContent('Ana');
    expect(link.getAttribute('href')).toContain('/dashboard/tools/mail?');
    expect(link.getAttribute('href')).toContain('id=m1');
  });

  it('says of a tool that it found nothing', async () => {
    const { user } = mount();

    await asked(user);

    const files = await screen.findByRole('region', { name: 'workbench.tools.files.label' });
    expect(within(files).getByText('workbench.search.none_here')).toBeInTheDocument();
    expect(within(files).queryByRole('link')).toBeNull();
  });

  it('closes on the hit it opens', async () => {
    const { user } = mount();

    await asked(user);
    await user.click(await screen.findByRole('link', { name: /Budget/ }));

    await waitFor(() => expect(screen.queryByRole('searchbox')).toBeNull());
  });

  it('keeps the answer for when the person comes back', async () => {
    const { user } = mount();

    await asked(user);
    await user.click(await screen.findByRole('link', { name: /Budget/ }));
    await waitFor(() => expect(screen.queryByRole('searchbox')).toBeNull());
    await user.click(opener());

    expect(await screen.findByRole('link', { name: /Budget/ })).toBeInTheDocument();
    expect(box()).toHaveValue('ana');
    expect(get).toHaveBeenCalledTimes(1);
  });

  it('names a thing with no name of its own', async () => {
    get.mockResolvedValue({
      ...FOUND,
      results: [{ ...FOUND.results[0], hits: [{ ...HIT, title: '', subtitle: null }] }],
    });
    const { user } = mount();

    await asked(user);

    expect(await screen.findByRole('link', { name: 'workbench.search.untitled' })).toBeVisible();
  });

  it('dates an event, with its year: a search reaches back and forth', async () => {
    get.mockResolvedValue({
      results: [
        {
          tool: 'calendar',
          hits: [
            { ...HIT, title: 'Review', subtitle: 'Room 2', calendar_id: 'c', day: '2027-01-04' },
          ],
          truncated: false,
          inbox_only: false,
        },
      ],
      failed: [],
    });
    const { user } = mount();

    await asked(user);

    const link = await screen.findByRole('link', { name: /Review/ });
    expect(link).toHaveTextContent('Jan 4, 2027');
    expect(link).toHaveTextContent('Room 2');
  });

  it('says a mailbox was searched from its inbox alone', async () => {
    get.mockResolvedValue({
      results: [{ ...FOUND.results[0], inbox_only: true }],
      failed: [],
    });
    const { user } = mount();

    await asked(user);

    expect(await screen.findByText('workbench.search.inbox_only')).toBeInTheDocument();
  });

  it('says nothing of the inbox where the whole mailbox was searched', async () => {
    const { user } = mount();

    await asked(user);

    await screen.findByRole('link', { name: /Budget/ });
    expect(screen.queryByText('workbench.search.inbox_only')).toBeNull();
  });

  it('says a tool holds more, and opens it', async () => {
    get.mockResolvedValue({
      results: [{ ...FOUND.results[0], truncated: true }],
      failed: [],
    });
    const { user } = mount();

    await asked(user);

    const more = await screen.findByRole('link', { name: 'workbench.search.more' });
    expect(more.getAttribute('href')).toMatch(/\/dashboard\/tools\/mail$/);
  });
});

describe('WorkbenchSearch — what it could not say', () => {
  it('names the tools that failed, beside what the others found', async () => {
    get.mockResolvedValue({ ...FOUND, failed: ['contacts', 'files'] });
    const { user } = mount();

    await asked(user);

    const status = await screen.findByRole('status');
    expect(status).toHaveTextContent('workbench.search.failed');
    expect(status).toHaveTextContent('workbench.tools.contacts.label');
    expect(status).toHaveTextContent('workbench.tools.files.label');
    expect(screen.getByRole('link', { name: /Budget/ })).toBeInTheDocument();
  });

  it('says nothing failed when nothing did', async () => {
    const { user } = mount();

    await asked(user);

    await screen.findByRole('link', { name: /Budget/ });
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('says it could not search, and tries again', async () => {
    get.mockRejectedValueOnce(new Error('offline'));
    const { user } = mount();

    await asked(user);

    expect(await screen.findByText('workbench.search.unavailable')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'workbench.states.retry' }));
    expect(await screen.findByRole('link', { name: /Budget/ })).toBeInTheDocument();
  });

  it('says nothing was asked of anyone when no tool answered', async () => {
    get.mockResolvedValue({ results: [], failed: [] });
    const { user } = mount();

    await asked(user);

    expect(await screen.findByText('workbench.search.nowhere')).toBeInTheDocument();
  });
});
