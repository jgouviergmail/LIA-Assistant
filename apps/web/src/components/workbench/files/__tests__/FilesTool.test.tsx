/**
 * The « Tools » files screen (ADR-369, Task 8.2).
 *
 * A folder opens in the list and a shortcut opens what it points at; the
 * breadcrumb is the open folder's own detail; a search runs on Enter across
 * Drive and says so. A Google document downloads once per format through the
 * API's own origin, a file past the ceiling is said instead of offered, « Open
 * in Drive » opens a tab that cannot reach back, and the trash asks first.
 */

import { beforeEach, describe, expect, it, vi, afterEach } from 'vitest';

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
import { takeHandoff, setHandoffOwner } from '@/lib/workbench/handoff';
import { FileSendStopped } from '@/lib/workbench/upload';
import type {
  WorkbenchAvailability,
  WorkbenchDriveItem,
  WorkbenchFeature,
  WorkbenchFileDetail,
  WorkbenchFileSharing,
} from '@/lib/workbench/types';

type ShellConfig = Pick<AppConfig, 'capabilities'> & { features: { workbench_enabled?: boolean } };

const { api, nav, sendFile, shell, toast } = vi.hoisted(() => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    getResponse: vi.fn(),
    getBlob: vi.fn(),
  },
  shell: { android: false },
  nav: { search: '', push: vi.fn(), replace: vi.fn() },
  sendFile: vi.fn(),
  toast: { error: vi.fn(), success: vi.fn() },
}));
vi.mock('@/lib/workbench/upload', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/workbench/upload')>()),
  sendFile,
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
vi.mock('@/lib/native/shell', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/native/shell')>()),
  isAndroidShell: () => shell.android,
}));
vi.mock('next/navigation', () => ({
  usePathname: () => '/en/dashboard/tools/files',
  useRouter: () => ({ push: nav.push, replace: nav.replace, back: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams(nav.search),
}));
vi.mock('@/hooks/useMediaQuery', () => ({ useMediaQuery: () => true }));
vi.mock('@/hooks/useAppConfig', async importOriginal => ({
  ...(await importOriginal<typeof import('@/hooks/useAppConfig')>()),
  useAppConfig: () => ({
    config: { features: { workbench_enabled: true }, capabilities: {} } satisfies ShellConfig,
    loading: false,
    error: null,
  }),
}));

import { WorkbenchShell } from '../../WorkbenchShell';
import { FilesTool } from '../FilesTool';

const BASE = '/en/dashboard/tools/files';
const CEILING = 1000;

function item(overrides: Partial<WorkbenchDriveItem>): WorkbenchDriveItem {
  return {
    id: 'p1',
    name: 'Budget.pdf',
    kind: 'file',
    mime_type: 'application/pdf',
    modified_at: '2026-10-30T09:15:00Z',
    size: 200,
    web_url: 'https://drive.google.com/file/d/p1/view',
    target_id: null,
    target_kind: null,
    formats: [],
    downloadable: true,
    starred: false,
    previewable: true,
    editable: false,
    ...overrides,
  };
}

function detail(overrides: Partial<WorkbenchFileDetail>): WorkbenchFileDetail {
  return {
    ...item({}),
    owners: ['Ana Lima'],
    description: null,
    created_at: null,
    ancestors: [],
    in_my_drive: true,
    ancestors_truncated: false,
    ...overrides,
  };
}

let page: { items: WorkbenchDriveItem[]; next_page_token: string | null };
let details: Record<string, WorkbenchFileDetail>;
let bulkMax: number;
let features: WorkbenchFeature[];
let mailReady: boolean;
let quota: { used: number; total: number | null } | null;
let sharing: WorkbenchFileSharing;

function rail(): WorkbenchAvailability {
  return {
    tools: [
      {
        tool: 'files',
        state: 'ready',
        provider: 'google_drive',
        features,
        bounds: { file_name_max_chars: 200 },
      },
      ...(mailReady
        ? [
            {
              tool: 'mail' as const,
              state: 'ready' as const,
              provider: 'google_gmail',
              features: [],
              bounds: {},
            },
          ]
        : []),
    ],
    limits: {
      page_size: 25,
      bulk_max_items: bulkMax,
      download_max_bytes: CEILING,
      upload_max_bytes: CEILING,
      calendar_window_max_events: 500,
      send_undo_seconds: 0,
      draft_autosave_seconds: 0,
      search_max_chars: 500,
      assist_text_max_chars: 8000,
      assist_instruction_max_chars: 500,
    },
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  nav.search = '';
  bulkMax = 50;
  features = ['export', 'file_views'];
  mailReady = false;
  takeHandoff('compose', 'owner');
  page = {
    items: [
      item({ id: 'd1', name: 'Projects', kind: 'folder', mime_type: 'folder', size: null }),
      item({ id: 's1', name: 'Plan', kind: 'shortcut', target_id: 'f9', target_kind: 'file' }),
      item({}),
    ],
    next_page_token: null,
  };
  details = {
    p1: detail({}),
    d2: detail({
      id: 'd2',
      name: 'Q4',
      kind: 'folder',
      ancestors: [{ id: 'd1', name: 'Projects' }],
    }),
  };
  quota = { used: 3000, total: 10000 };
  sharing = {
    people: [
      { id: 'p0', email: 'me@x.org', name: 'Me', role: 'owner' },
      { id: 'p1', email: 'ana@x.org', name: null, role: 'reader' },
    ],
    link: null,
  };
  api.get.mockImplementation((path: string, options?: { params?: { id?: string } }) => {
    if (path === '/workbench') return Promise.resolve(rail());
    if (path === '/workbench/files/sharing') return Promise.resolve(sharing);
    if (path === '/workbench/files/quota') {
      return quota ? Promise.resolve(quota) : Promise.reject(new Error('down'));
    }
    if (path === '/workbench/files') return Promise.resolve(page);
    if (path === '/workbench/files/file') {
      return Promise.resolve(details[options?.params?.id ?? '']);
    }
    return Promise.resolve({});
  });
  api.post.mockResolvedValue({ done: ['p1'], failed: [] });
  api.patch.mockResolvedValue(item({}));
  api.getResponse.mockRejectedValue(
    new ApiError('none', 422, { detail: { code: 'not_supported_by_provider' } })
  );
});

function screenOf() {
  return renderWithProviders(
    <WorkbenchShell lng="en">
      <FilesTool lng="en" />
    </WorkbenchShell>
  );
}

/** The door to what a file offers beyond its bar. */
const MORE = 'common.more_actions';

function listCalls(): Array<Record<string, unknown>> {
  return api.get.mock.calls
    .filter(([path]) => path === '/workbench/files')
    .map(([, options]) => (options as { params: Record<string, unknown> }).params);
}

describe('FilesTool — the list', () => {
  it('opens a folder in the list and a shortcut where it points', async () => {
    screenOf();

    const folder = await screen.findByRole('link', { name: /Projects/ });
    expect(folder.getAttribute('href')).toBe(`${BASE}?folder=d1`);
    expect(screen.getByRole('link', { name: /Plan/ }).getAttribute('href')).toBe(`${BASE}?file=f9`);
    expect(screen.getByRole('link', { name: /Budget\.pdf/ }).getAttribute('href')).toBe(
      `${BASE}?file=p1`
    );
  });

  it('re-reads what it shows when the person asks', async () => {
    const { user } = screenOf();
    await screen.findByRole('button', { name: 'workbench.states.refresh' });
    api.get.mockClear();

    await user.click(screen.getByRole('button', { name: 'workbench.states.refresh' }));

    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/workbench/files', expect.anything())
    );
  });

  it('searches on Enter across Drive, never on every key, and says so', async () => {
    const { user } = screenOf();
    await screen.findByRole('link', { name: /Projects/ });
    const box = screen.getByRole('searchbox', { name: 'workbench.files.search_label' });

    await user.type(box, 'budget');
    expect(listCalls().every(params => !('q' in params))).toBe(true);
    await user.click(screen.getByRole('checkbox', { name: 'workbench.files.full_text' }));
    await user.keyboard('{Enter}');

    await waitFor(() => expect(listCalls().at(-1)).toEqual({ q: 'budget', full_text: 'true' }));
    expect(screen.getByRole('status')).toHaveTextContent('workbench.files.results');
    expect(screen.queryByRole('navigation', { name: 'workbench.files.breadcrumb' })).toBeNull();
  });

  it('tells the root lists no shared drives, and a folder says nothing of it', async () => {
    features = [];
    screenOf();
    expect(await screen.findByText('workbench.files.shared_drives')).toBeInTheDocument();
  });

  it('draws the open folder’s breadcrumb from its own detail', async () => {
    nav.search = 'folder=d2';
    screenOf();

    const crumbs = await screen.findByRole('navigation', { name: 'workbench.files.breadcrumb' });
    await within(crumbs).findByText('Q4');
    expect(
      within(crumbs).getByRole('link', { name: 'workbench.files.my_drive' }).getAttribute('href')
    ).toBe(BASE);
    expect(within(crumbs).getByRole('link', { name: 'Projects' }).getAttribute('href')).toBe(
      `${BASE}?folder=d1`
    );
    expect(within(crumbs).getByText('Q4').getAttribute('aria-current')).toBe('page');
    expect(listCalls().at(-1)).toEqual({ folder_id: 'd2' });
    expect(screen.queryByText('workbench.files.shared_drives')).toBeNull();
  });
});

describe('FilesTool — the order of a folder', () => {
  it('asks Drive for the order chosen, the listing being paged', async () => {
    const { user } = screenOf();
    await screen.findByRole('link', { name: /Budget.pdf/ });

    await user.selectOptions(
      screen.getByRole('combobox', { name: 'workbench.files.sort_label' }),
      'modified'
    );

    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith(
        '/workbench/files',
        expect.objectContaining({ params: expect.objectContaining({ order: 'modified' }) })
      )
    );
  });

  it('asks nothing of the kind by default', async () => {
    screenOf();
    await screen.findByRole('link', { name: /Budget.pdf/ });

    const [, options] = api.get.mock.calls.find(([path]) => path === '/workbench/files') ?? [];
    expect(options.params).not.toHaveProperty('order');
  });

  it('offers no order during a search, Drive refusing it there', async () => {
    const { user } = screenOf();
    await screen.findByRole('link', { name: /Budget.pdf/ });

    await user.type(
      screen.getByRole('searchbox', { name: 'workbench.files.search_label' }),
      'budget{Enter}'
    );

    await waitFor(() =>
      expect(screen.queryByRole('combobox', { name: 'workbench.files.sort_label' })).toBeNull()
    );
  });
});

describe('FilesTool — several items at once', () => {
  const boxes = () => screen.findAllByRole('checkbox', { name: 'workbench.files.select_item' });

  it('trashes the items ticked after one question, and says what could not be', async () => {
    api.post.mockResolvedValue({ done: ['p1'], failed: [{ id: 'd1', status: 'failed' }] });
    const { user } = screenOf();
    const [folder, , file] = await boxes();

    await user.click(folder!);
    await user.click(file!);
    const bar = screen.getByRole('region', { name: 'workbench.files.selection_region' });
    await user.click(within(bar).getByRole('button', { name: /workbench\.files\.trash/ }));
    await answerConfirmDialog(user, true);

    await waitFor(() => expect(api.post).toHaveBeenCalled());
    expect(api.post.mock.calls[0].slice(0, 2)).toEqual([
      '/workbench/files/trash',
      { file_ids: ['d1', 'p1'] },
    ]);
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('workbench.files.partial'));
    expect((await boxes()).map(box => (box as HTMLInputElement).checked)).toEqual([
      true,
      false,
      false,
    ]);
  });

  it('sends nothing past the published bound, and says so', async () => {
    bulkMax = 1;
    const { user } = screenOf();
    const [folder, shortcut] = await boxes();
    await user.click(folder!);
    await user.click(shortcut!);

    expect(screen.getByText('workbench.files.over_bulk')).toBeInTheDocument();
    const bar = screen.getByRole('region', { name: 'workbench.files.selection_region' });
    await user.click(within(bar).getByRole('button', { name: /workbench\.files\.trash/ }));

    expect(api.post).not.toHaveBeenCalled();
  });
});

describe('FilesTool — the open file', () => {
  it('says a link it could not copy', async () => {
    nav.search = 'file=p1';
    const { user } = screenOf();
    vi.spyOn(navigator.clipboard, 'writeText').mockRejectedValue(new Error('refused'));

    await user.click(await screen.findByRole('button', { name: 'workbench.files.copy_link' }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('workbench.files.failed'));
  });

  it('copies the file’s link, and says so', async () => {
    nav.search = 'file=p1';
    const { user } = screenOf();
    const writeText = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue(undefined);

    await user.click(await screen.findByRole('button', { name: 'workbench.files.copy_link' }));

    expect(writeText).toHaveBeenCalledWith('https://drive.google.com/file/d/p1/view');
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('workbench.files.link_copied'));
  });

  it('downloads a Google document once per format, through the API’s origin', async () => {
    details.g1 = detail({ id: 'g1', name: 'Notes', size: null, formats: ['pdf', 'docx'] });
    nav.search = 'file=g1';
    screenOf();

    const article = await screen.findByRole('article', { name: 'Notes' });
    const links = within(article).getAllByRole('link', { name: /workbench\.files\.download_as/ });
    expect(links.map(link => link.getAttribute('href'))).toEqual([
      expect.stringMatching(/\/workbench\/files\/download\?id=g1&format=pdf$/),
      expect.stringMatching(/\/workbench\/files\/download\?id=g1&format=docx$/),
    ]);
    expect(links.every(link => link.getAttribute('rel') === 'noopener noreferrer')).toBe(true);
  });

  it('says a file past the ceiling instead of offering it', async () => {
    details.p1 = detail({ size: CEILING + 1 });
    nav.search = 'file=p1';
    screenOf();

    const article = await screen.findByRole('article', { name: 'Budget.pdf' });
    expect(within(article).getByText('workbench.files.too_large')).toBeInTheDocument();
    expect(within(article).queryByRole('link', { name: /workbench\.files\.download/ })).toBeNull();
  });

  it('lets an address its description holds be followed', async () => {
    nav.search = 'file=p1';
    details.p1 = { ...details.p1!, description: 'Source: https://data.example.org/set' };
    screenOf();

    expect(
      await screen.findByRole('link', { name: 'https://data.example.org/set' })
    ).toHaveAttribute('href', 'https://data.example.org/set');
  });

  it('holds what is used most in the bar and the rest behind « … »', async () => {
    nav.search = 'file=p1';
    const { user } = screenOf();

    await screen.findByRole('link', { name: 'workbench.files.open_in_drive' });
    const bar = within(screen.getByTestId('detail-acts'));

    expect(
      [...bar.getAllByRole('link'), ...bar.getAllByRole('button')].map(act =>
        act.getAttribute('aria-label')
      )
    ).toEqual([
      'workbench.files.open_in_drive',
      'workbench.files.copy_link',
      'workbench.files.move',
      'workbench.files.share',
      MORE,
      'workbench.files.trash',
      'workbench.ask.label',
    ]);
    expect(bar.getByRole('button', { name: 'workbench.files.trash' })).toHaveClass(
      'text-destructive'
    );
    await user.click(bar.getByRole('button', { name: MORE }));
    const items = await screen.findAllByRole('menuitem');
    expect(items.map(item => item.textContent)).toEqual([
      'workbench.files.rename',
      'workbench.files.copy',
    ]);
  });

  it('stands sending by mail beside moving and sharing, where a mail can leave', async () => {
    mailReady = true;
    nav.search = 'file=p1';
    screenOf();

    const bar = within(await screen.findByTestId('detail-acts'));

    expect(bar.getAllByRole('button').map(act => act.getAttribute('aria-label'))).toEqual([
      'workbench.files.copy_link',
      'workbench.files.move',
      'workbench.files.share',
      'workbench.files.send_by_mail',
      MORE,
      'workbench.files.trash',
      'workbench.ask.label',
    ]);
  });

  it('offers neither to open nor to copy a link the drive did not give', async () => {
    details.p1 = detail({ web_url: null });
    nav.search = 'file=p1';
    screenOf();

    const bar = within(await screen.findByTestId('detail-acts'));

    expect(bar.queryByRole('link')).toBeNull();
    expect(bar.getAllByRole('button').map(act => act.getAttribute('aria-label'))).toEqual([
      'workbench.files.move',
      'workbench.files.share',
      MORE,
      'workbench.files.trash',
      'workbench.ask.label',
    ]);
  });

  it('offers no copy of a folder', async () => {
    nav.search = 'file=d2';
    screenOf();

    const bar = within(await screen.findByTestId('detail-acts'));

    expect(bar.getByRole('button', { name: 'workbench.files.rename' })).toBeInTheDocument();
    expect(bar.queryByRole('button', { name: 'workbench.files.copy' })).toBeNull();
    expect(bar.queryByRole('button', { name: MORE })).toBeNull();
  });

  it('opens Drive in a tab that cannot reach back', async () => {
    nav.search = 'file=p1';
    screenOf();

    const open = await screen.findByRole('link', { name: 'workbench.files.open_in_drive' });
    expect(open.getAttribute('href')).toBe('https://drive.google.com/file/d/p1/view');
    expect([open.getAttribute('target'), open.getAttribute('rel')]).toEqual([
      '_blank',
      'noopener noreferrer',
    ]);
  });

  it('says « folder » in the bar and tells a new folder whole', async () => {
    screenOf();

    const folder = await screen.findByRole('button', { name: 'workbench.files.new_folder' });

    expect(folder).toHaveTextContent('workbench.files.folder_short');
  });

  it('trashes after a confirmation, then closes the file', async () => {
    nav.search = 'folder=d2&file=p1';
    const { user } = screenOf();
    await user.click(await screen.findByRole('button', { name: 'workbench.files.trash' }));
    expect(api.post).not.toHaveBeenCalled();

    const dialog = await screen.findByRole('alertdialog');
    await user.click(within(dialog).getByRole('button', { name: 'workbench.files.trash' }));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        '/workbench/files/trash',
        { file_ids: ['p1'] },
        undefined
      )
    );
    await waitFor(() =>
      expect(nav.replace).toHaveBeenCalledWith(`${BASE}?folder=d2`, { scroll: false })
    );
  });

  it('trashes nothing when the confirmation is declined', async () => {
    nav.search = 'file=p1';
    const { user } = screenOf();
    await user.click(await screen.findByRole('button', { name: 'workbench.files.trash' }));

    const dialog = await screen.findByRole('alertdialog');
    await user.click(within(dialog).getByRole('button', { name: 'common.cancel' }));

    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull());
    expect(api.post).not.toHaveBeenCalled();
    expect(nav.replace).not.toHaveBeenCalled();
  });
});

describe('FilesTool — a new folder', () => {
  const open = async (user: ReturnType<typeof screenOf>['user']) => {
    await user.click(await screen.findByRole('button', { name: 'workbench.files.new_folder' }));
    return screen.findByRole('dialog', { name: 'workbench.files.new_folder' });
  };

  it('goes where the list stands, once per submission, and the list reads it', async () => {
    nav.search = 'folder=d2';
    api.post.mockResolvedValue(item({ id: 'n1', name: 'Trips', kind: 'folder' }));
    const { user } = screenOf();
    const dialog = await open(user);
    await user.type(within(dialog).getByRole('textbox'), '  Trips ');
    api.get.mockClear();

    await user.click(within(dialog).getByRole('button', { name: 'workbench.files.create' }));

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('workbench.files.folder_made'));
    const [path, body] = api.post.mock.calls[0] as [string, Record<string, unknown>];
    expect(path).toBe('/workbench/files/folders');
    expect(body).toMatchObject({ name: 'Trips', folder_id: 'd2' });
    expect(body.idempotency_key).toEqual(expect.any(String));
    expect(listCalls().length).toBeGreaterThan(0);
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('says a name taken and keeps what was typed', async () => {
    api.post.mockRejectedValue(new ApiError('taken', 409, { detail: { code: 'name_taken' } }));
    const { user } = screenOf();
    const dialog = await open(user);
    await user.type(within(dialog).getByRole('textbox'), 'Trips');

    await user.click(within(dialog).getByRole('button', { name: 'workbench.files.create' }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('workbench.errors.name_taken'));
    expect(within(dialog).getByRole('textbox')).toHaveValue('Trips');
  });

  it('takes one name, never a path, and sends nothing', async () => {
    const { user } = screenOf();
    const dialog = await open(user);
    await user.type(within(dialog).getByRole('textbox'), 'a/b');

    expect(within(dialog).getByText('workbench.files.name_is_one')).toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: 'workbench.files.create' }));

    expect(api.post).not.toHaveBeenCalled();
  });

  it('holds the published bound', async () => {
    const { user } = screenOf();
    const dialog = await open(user);

    expect(within(dialog).getByRole('textbox')).toHaveAttribute('maxlength', '200');
  });

  it('is not offered during a search, which stands nowhere', async () => {
    const { user } = screenOf();
    await user.type(await screen.findByRole('searchbox'), 'budget{Enter}');

    await screen.findByRole('status');
    expect(screen.queryByRole('button', { name: 'workbench.files.new_folder' })).toBeNull();
  });
});

describe('FilesTool — organising the open file', () => {
  const act = async (user: ReturnType<typeof screenOf>['user'], name: string) => {
    await user.click(await screen.findByRole('button', { name: MORE }));
    await user.click(await screen.findByRole('menuitem', { name }));
    return screen.findByRole('dialog');
  };
  const moveDialog = async (user: ReturnType<typeof screenOf>['user']) => {
    await user.click(await screen.findByRole('button', { name: 'workbench.files.move' }));
    return screen.findByRole('dialog');
  };

  beforeEach(() => {
    nav.search = 'file=p1';
  });

  it('renames it from its own name, and reads it again', async () => {
    const { user } = screenOf();
    const dialog = await act(user, 'workbench.files.rename');
    const field = within(dialog).getByRole('textbox');
    expect(field).toHaveValue('Budget.pdf');
    await user.clear(field);
    await user.type(field, 'Budget 2026.pdf');
    api.get.mockClear();

    await user.click(within(dialog).getByRole('button', { name: 'workbench.files.rename' }));

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('workbench.files.renamed'));
    expect(api.patch.mock.calls[0].slice(0, 2)).toEqual([
      '/workbench/files/file',
      { file_id: 'p1', name: 'Budget 2026.pdf' },
    ]);
    expect(api.get.mock.calls.map(([path]) => path)).toContain('/workbench/files/file');
  });

  it('asks nothing when the name did not change', async () => {
    const { user } = screenOf();
    const dialog = await act(user, 'workbench.files.rename');

    await user.click(within(dialog).getByRole('button', { name: 'workbench.files.rename' }));

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(api.patch).not.toHaveBeenCalled();
  });

  it('moves it to a folder walked to, offering folders alone', async () => {
    const { user } = screenOf();
    const dialog = await moveDialog(user);
    const walk = within(dialog);

    expect(await walk.findByRole('button', { name: 'Projects' })).toBeInTheDocument();
    expect(walk.queryByRole('button', { name: 'Budget.pdf' })).toBeNull();
    await user.click(walk.getByRole('button', { name: 'Projects' }));
    await waitFor(() => expect(listCalls().at(-1)).toMatchObject({ folder_id: 'd1' }));

    await user.click(walk.getByRole('button', { name: 'workbench.files.move_here' }));

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('workbench.files.moved'));
    expect(api.post.mock.calls[0].slice(0, 2)).toEqual([
      '/workbench/files/move',
      { file_ids: ['p1'], folder_id: 'd1' },
    ]);
  });

  it('starts where the file sits, walks back up, and the top of the drive is a place', async () => {
    details.p1 = detail({ ancestors: [{ id: 'd2', name: 'Other' }] });
    const { user } = screenOf();
    const dialog = await moveDialog(user);
    const walk = within(dialog);
    await waitFor(() => expect(listCalls().at(-1)).toMatchObject({ folder_id: 'd2' }));
    expect(walk.getByRole('button', { name: 'workbench.files.move_here' })).toBeDisabled();

    await user.click(walk.getByRole('button', { name: 'workbench.files.folder_up' }));
    await user.click(walk.getByRole('button', { name: 'workbench.files.move_here' }));

    await waitFor(() => expect(api.post).toHaveBeenCalled());
    expect(api.post.mock.calls[0].slice(0, 2)).toEqual([
      '/workbench/files/move',
      { file_ids: ['p1'], folder_id: null },
    ]);
  });

  it('cannot move it where it already sits', async () => {
    const { user } = screenOf();
    const dialog = await moveDialog(user);

    expect(
      within(dialog).getByRole('button', { name: 'workbench.files.move_here' })
    ).toBeDisabled();
  });

  it('says a folder that cannot be read, and reads it again on demand', async () => {
    const { user } = screenOf();
    await screen.findByRole('button', { name: MORE });
    api.get.mockRejectedValueOnce(new ApiError('down', 502, { detail: {} }));
    const dialog = await moveDialog(user);

    await user.click(await within(dialog).findByRole('button', { name: 'workbench.states.retry' }));

    expect(await within(dialog).findByRole('button', { name: 'Projects' })).toBeInTheDocument();
  });

  it('says there is no folder here rather than an empty box', async () => {
    page = { items: [item({})], next_page_token: null };
    const { user } = screenOf();
    const dialog = await moveDialog(user);

    expect(await within(dialog).findByText('workbench.files.no_folders')).toBeInTheDocument();
  });

  it('reads on for folders past the first page', async () => {
    page = { items: [item({})], next_page_token: 'next' };
    const { user } = screenOf();
    const dialog = await moveDialog(user);
    const more = await within(dialog).findByRole('button', { name: 'workbench.files.more' });
    expect(within(dialog).queryByText('workbench.files.no_folders')).toBeNull();
    page = {
      items: [item({ id: 'd9', name: 'Late', kind: 'folder', mime_type: 'folder' })],
      next_page_token: null,
    };

    await user.click(more);

    expect(await within(dialog).findByRole('button', { name: 'Late' })).toBeInTheDocument();
  });

  it('copies it under the name asked, and says the copy', async () => {
    api.post.mockResolvedValue({ item: item({ id: 'c1' }) });
    const { user } = screenOf();
    const dialog = await act(user, 'workbench.files.copy');
    const field = within(dialog).getByRole('textbox');
    await user.clear(field);
    await user.type(field, 'Mine.pdf');
    await user.click(await within(dialog).findByRole('button', { name: 'Projects' }));

    await user.click(within(dialog).getByRole('button', { name: 'workbench.files.copy_here' }));

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('workbench.files.copied'));
    const [path, body] = api.post.mock.calls[0] as [string, Record<string, unknown>];
    expect(path).toBe('/workbench/files/copy');
    expect(body).toMatchObject({ file_id: 'p1', folder_id: 'd1', name: 'Mine.pdf' });
    expect(body.idempotency_key).toEqual(expect.any(String));
  });

  it('copies where the file sits by default, the name the only change', async () => {
    details.p1 = detail({ ancestors: [{ id: 'd2', name: 'Other' }] });
    api.post.mockResolvedValue({ item: item({ id: 'c1' }) });
    const { user } = screenOf();
    const dialog = await act(user, 'workbench.files.copy');

    expect(within(dialog).getByRole('textbox')).toHaveValue('workbench.files.copy_name');
    await user.click(within(dialog).getByRole('button', { name: 'workbench.files.copy_here' }));

    await waitFor(() => expect(api.post).toHaveBeenCalled());
    expect(api.post.mock.calls[0][1]).toMatchObject({ folder_id: 'd2' });
  });

  it('says a copy the provider finishes later as under way, never as done', async () => {
    api.post.mockResolvedValue({ item: null });
    const { user } = screenOf();
    const dialog = await act(user, 'workbench.files.copy');

    await user.click(within(dialog).getByRole('button', { name: 'workbench.files.copy_here' }));

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('workbench.files.copying'));
    expect(toast.success).not.toHaveBeenCalledWith('workbench.files.copied');
  });

  it('keeps the walk open on a refusal, in the refusal’s own words', async () => {
    api.post.mockRejectedValue(new ApiError('taken', 409, { detail: { code: 'name_taken' } }));
    const { user } = screenOf();
    const dialog = await act(user, 'workbench.files.copy');

    await user.click(within(dialog).getByRole('button', { name: 'workbench.files.copy_here' }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('workbench.errors.name_taken'));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });
});

describe('FilesTool — organising what is ticked', () => {
  const boxes = () => screen.findAllByRole('checkbox', { name: 'workbench.files.select_item' });
  const bar = () => screen.getByRole('region', { name: 'workbench.files.selection_region' });

  it('never offers a folder ticked as the place it goes', async () => {
    const { user } = screenOf();
    const [folder] = await boxes();
    await user.click(folder!);

    await user.click(within(bar()).getByRole('button', { name: 'workbench.files.move' }));

    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText('workbench.files.no_folders')).toBeInTheDocument();
    expect(within(dialog).queryByRole('button', { name: 'Projects' })).toBeNull();
  });

  it('moves them together, each answered, and leaves ticked what stayed', async () => {
    page = {
      items: [
        item({ id: 'd1', name: 'Projects', kind: 'folder', mime_type: 'folder', size: null }),
        item({ id: 'p2', name: 'Plan.pdf' }),
        item({}),
      ],
      next_page_token: null,
    };
    api.post.mockResolvedValue({ done: ['p1'], failed: [{ id: 'p2', status: 'failed' }] });
    const { user } = screenOf();
    const [, second, third] = await boxes();
    await user.click(second!);
    await user.click(third!);
    await user.click(within(bar()).getByRole('button', { name: 'workbench.files.move' }));
    const dialog = await screen.findByRole('dialog');

    await user.click(await within(dialog).findByRole('button', { name: 'Projects' }));
    await user.click(within(dialog).getByRole('button', { name: 'workbench.files.move_here' }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('workbench.files.partial'));
    expect(api.post.mock.calls[0].slice(0, 2)).toEqual([
      '/workbench/files/move',
      { file_ids: ['p2', 'p1'], folder_id: 'd1' },
    ]);
    expect((await boxes()).map(box => (box as HTMLInputElement).checked)).toEqual([
      false,
      true,
      false,
    ]);
  });

  it('says a name the folder already holds, and lets another folder be chosen', async () => {
    api.post.mockResolvedValue({ done: [], failed: [{ id: 'p1', status: 'name_taken' }] });
    const { user } = screenOf();
    const [, , file] = await boxes();
    await user.click(file!);
    await user.click(within(bar()).getByRole('button', { name: 'workbench.files.move' }));
    const dialog = await screen.findByRole('dialog');

    await user.click(await within(dialog).findByRole('button', { name: 'Projects' }));
    await user.click(within(dialog).getByRole('button', { name: 'workbench.files.move_here' }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('workbench.errors.name_taken'));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('asks nothing past the published bound', async () => {
    bulkMax = 1;
    const { user } = screenOf();
    const [first, second] = await boxes();
    await user.click(first!);
    await user.click(second!);

    await user.click(within(bar()).getByRole('button', { name: 'workbench.files.move' }));

    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('renames a folder ticked alone, which opens nowhere else', async () => {
    const { user } = screenOf();
    const [folder] = await boxes();
    await user.click(folder!);

    await user.click(within(bar()).getByRole('button', { name: 'workbench.files.rename' }));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByRole('textbox')).toHaveValue('Projects');
  });

  it('renames one item at a time', async () => {
    const { user } = screenOf();
    const [first, second] = await boxes();
    await user.click(first!);
    await user.click(second!);

    expect(within(bar()).queryByRole('button', { name: 'workbench.files.rename' })).toBeNull();
  });

  it('copies a file ticked alone, and no folder: Drive copies none', async () => {
    const { user } = screenOf();
    const [folder, , file] = await boxes();
    await user.click(folder!);
    // A folder takes a rename alone, which stands in the bar: a copy beside it would open « … ».
    expect(
      within(bar()).getByRole('button', { name: 'workbench.files.rename' })
    ).toBeInTheDocument();
    expect(within(bar()).queryByRole('button', { name: MORE })).toBeNull();

    await user.click(folder!);
    await user.click(file!);

    // What one file takes waits behind « … », the move standing in the bar.
    await user.click(within(bar()).getByRole('button', { name: MORE }));
    expect((await screen.findAllByRole('menuitem')).map(line => line.textContent)).toEqual([
      'workbench.files.rename',
      'workbench.files.copy',
    ]);
  });
});

describe('FilesTool — the drive’s views', () => {
  const views = () => screen.findByRole('navigation', { name: 'workbench.files.views' });

  it('offers them where the drive keeps them, the drive itself first', async () => {
    screenOf();

    const links = within(await views()).getAllByRole('link');

    expect(links.map(link => link.getAttribute('href'))).toEqual([
      BASE,
      `${BASE}?view=recent`,
      `${BASE}?view=starred`,
      `${BASE}?view=shared`,
      `${BASE}?view=trash`,
      `${BASE}?view=drives`,
    ]);
  });

  it('offers none on a drive that keeps none', async () => {
    features = [];
    screenOf();

    await screen.findByRole('button', { name: 'workbench.files.new_folder' });
    expect(screen.queryByRole('navigation', { name: 'workbench.files.views' })).toBeNull();
  });

  it('reads the view the address names, and says which it is', async () => {
    nav.search = 'view=shared';
    screenOf();

    await waitFor(() => expect(listCalls().at(-1)).toMatchObject({ view: 'shared' }));
    const current = within(await views()).getByRole('link', { current: 'page' });
    expect(current).toHaveAttribute('href', `${BASE}?view=shared`);
  });

  it('ignores a view nobody offers', async () => {
    nav.search = 'view=everything';
    screenOf();

    await screen.findByRole('button', { name: 'workbench.files.new_folder' });
    expect(listCalls().at(-1)).toEqual({});
  });

  it('ignores a view the drive does not keep, its address kept from another', async () => {
    nav.search = 'view=recent';
    features = [];
    screenOf();

    await screen.findByRole('button', { name: 'workbench.files.new_folder' });
    expect(listCalls().at(-1)).toEqual({});
  });

  it('stands nowhere: nothing is created or sent there, and nothing is ordered', async () => {
    nav.search = 'view=recent';
    screenOf();

    await views();
    await waitFor(() => expect(listCalls().length).toBeGreaterThan(0));
    expect(screen.queryByRole('button', { name: 'workbench.files.new_folder' })).toBeNull();
    expect(screen.queryByLabelText('workbench.files.send_files')).toBeNull();
    expect(screen.queryByRole('combobox', { name: 'workbench.files.sort_label' })).toBeNull();
  });

  it('keeps the view when a file opens and when it closes', async () => {
    nav.search = 'view=starred';
    screenOf();

    const link = await screen.findByRole('link', { name: /Budget\.pdf/ });
    expect(link).toHaveAttribute('href', `${BASE}?view=starred&file=p1`);
  });

  it('leaves the view when a folder opens', async () => {
    nav.search = 'view=starred';
    screenOf();

    const link = await screen.findByRole('link', { name: /Projects/ });
    expect(link).toHaveAttribute('href', `${BASE}?folder=d1`);
  });

  it('lets a search take over the view, and gives it back', async () => {
    nav.search = 'view=recent';
    const { user } = screenOf();
    await views();

    await user.type(screen.getByRole('searchbox'), 'budget{Enter}');

    await waitFor(() => expect(listCalls().at(-1)).toMatchObject({ q: 'budget' }));
    expect(listCalls().at(-1)).not.toHaveProperty('view');
  });
});

describe('FilesTool — a star', () => {
  const star = (name: string) => screen.findByRole('button', { name });

  it('is set from the row, and the row says it', async () => {
    api.patch.mockResolvedValue(item({ starred: true }));
    const { user } = screenOf();
    const [first] = await screen.findAllByRole('button', { name: 'workbench.files.star' });

    await user.click(first!);

    expect(api.patch.mock.calls[0].slice(0, 2)).toEqual([
      '/workbench/files/star',
      { file_id: 'd1', starred: true },
    ]);
    expect(await star('workbench.files.unstar')).toHaveAttribute('aria-pressed', 'true');
  });

  it('shows on what carries one, and takes it back', async () => {
    page = { items: [item({ starred: true })], next_page_token: null };
    api.patch.mockResolvedValue(item({ starred: false }));
    const { user } = screenOf();
    const button = await star('workbench.files.unstar');
    expect(button).toHaveAttribute('aria-pressed', 'true');

    await user.click(button);

    expect(api.patch.mock.calls[0][1]).toEqual({ file_id: 'p1', starred: false });
    expect(await star('workbench.files.star')).toHaveAttribute('aria-pressed', 'false');
  });

  it('takes the row away from the starred view once its star is gone', async () => {
    nav.search = 'view=starred';
    page = { items: [item({ starred: true })], next_page_token: null };
    api.patch.mockResolvedValue(item({ starred: false }));
    const { user } = screenOf();

    await user.click(await star('workbench.files.unstar'));

    await waitFor(() => expect(screen.queryByRole('link', { name: /Budget\.pdf/ })).toBeNull());
  });

  it('says a refusal, and leaves the row as it was', async () => {
    page = { items: [item({})], next_page_token: null };
    api.patch.mockRejectedValue(
      new ApiError('down', 502, { detail: { code: 'provider_unavailable' } })
    );
    const { user } = screenOf();

    await user.click(await star('workbench.files.star'));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('workbench.errors.provider_unavailable')
    );
    expect(await star('workbench.files.star')).toHaveAttribute('aria-pressed', 'false');
  });

  it('is not offered on a drive that keeps none', async () => {
    features = [];
    screenOf();

    await screen.findByRole('link', { name: /Budget\.pdf/ });
    expect(screen.queryByRole('button', { name: 'workbench.files.star' })).toBeNull();
  });
});

describe('FilesTool — a shared drive', () => {
  it('opens like a folder', async () => {
    nav.search = 'view=drives';
    page = {
      items: [item({ id: 's1', name: 'Team', kind: 'folder', mime_type: 'folder', size: null })],
      next_page_token: null,
    };
    screenOf();

    const link = await screen.findByRole('link', { name: /Team/ });
    expect(link).toHaveAttribute('href', `${BASE}?folder=s1`);
  });

  it('says it is not listed where the drive offers no view of it', async () => {
    features = [];
    screenOf();

    expect(await screen.findByText('workbench.files.shared_drives')).toBeInTheDocument();
  });

  it('says nothing of the kind where it is listed', async () => {
    screenOf();

    await screen.findByRole('navigation', { name: 'workbench.files.views' });
    expect(screen.queryByText('workbench.files.shared_drives')).toBeNull();
  });
});

describe('FilesTool — the quota', () => {
  it('says what is used of what, at the top of the drive', async () => {
    screenOf();

    expect(await screen.findByText('workbench.files.quota')).toBeInTheDocument();
    const bar = screen.getByRole('progressbar', { name: 'workbench.files.quota_label' });
    expect(bar).toHaveAttribute('value', '3000');
    expect(bar).toHaveAttribute('max', '10000');
  });

  it('says what is used of an unlimited drive, with no bar', async () => {
    quota = { used: 3000, total: null };
    screenOf();

    expect(await screen.findByText('workbench.files.quota_used')).toBeInTheDocument();
    expect(screen.queryByRole('progressbar')).toBeNull();
  });

  it('says nothing when it cannot be read', async () => {
    quota = null;
    screenOf();

    await screen.findByRole('link', { name: /Budget\.pdf/ });
    await waitFor(() =>
      expect(api.get.mock.calls.map(([path]) => path)).toContain('/workbench/files/quota')
    );
    expect(screen.queryByText('workbench.files.quota')).toBeNull();
  });

  it('is not read inside a folder', async () => {
    nav.search = 'folder=d2';
    screenOf();

    await screen.findByRole('link', { name: /Budget\.pdf/ });
    expect(api.get.mock.calls.map(([path]) => path)).not.toContain('/workbench/files/quota');
  });
});

describe('FilesTool — who a file is shared with', () => {
  const opened = async (user: ReturnType<typeof screenOf>['user']) => {
    await user.click(await screen.findByRole('button', { name: 'workbench.files.share' }));
    return screen.findByRole('dialog');
  };

  beforeEach(() => {
    nav.search = 'file=p1';
    api.post.mockResolvedValue(undefined);
  });

  it('says who reaches it and what they may do', async () => {
    const { user } = screenOf();
    const dialog = await opened(user);

    expect(await within(dialog).findByText('ana@x.org')).toBeInTheDocument();
    expect(within(dialog).getByText('Me')).toBeInTheDocument();
    expect(within(dialog).getByText('workbench.files.role_owner')).toBeInTheDocument();
    expect(
      within(within(dialog).getByRole('list')).getByText('workbench.files.role_reader')
    ).toBeInTheDocument();
  });

  it('gives a person access, reads it again, and empties the field', async () => {
    const { user } = screenOf();
    const dialog = await opened(user);
    const field = within(dialog).getByRole('textbox', { name: 'workbench.files.share_email' });
    await user.type(field, ' bob@x.org ');
    await user.selectOptions(
      within(dialog).getByRole('combobox', { name: 'workbench.files.share_role' }),
      'writer'
    );
    api.get.mockClear();

    await user.click(within(dialog).getByRole('button', { name: 'workbench.files.share_send' }));

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('workbench.files.shared'));
    const [path, body] = api.post.mock.calls[0] as [string, Record<string, unknown>];
    expect(path).toBe('/workbench/files/sharing');
    expect(body).toMatchObject({ file_id: 'p1', email: 'bob@x.org', role: 'writer' });
    expect(body.idempotency_key).toEqual(expect.any(String));
    expect(api.get.mock.calls.map(([called]) => called)).toContain('/workbench/files/sharing');
    await waitFor(() => expect(field).toHaveValue(''));
  });

  it('gives each submission its key, a refused one keeping its own', async () => {
    api.post.mockRejectedValueOnce(
      new ApiError('no', 422, { detail: { code: 'provider_refused' } })
    );
    const { user } = screenOf();
    const dialog = await opened(user);
    const field = within(dialog).getByRole('textbox', { name: 'workbench.files.share_email' });
    const send = within(dialog).getByRole('button', { name: 'workbench.files.share_send' });
    await user.type(field, 'bob@x.org');

    await user.click(send);
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('workbench.errors.provider_refused')
    );
    expect(field).toHaveValue('bob@x.org');
    await user.click(send);
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(field).toHaveValue(''));
    await user.type(field, 'carla@x.org');
    await user.click(send);
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(3));

    const keys = api.post.mock.calls.map(
      ([, body]) => (body as { idempotency_key: string }).idempotency_key
    );
    expect(keys[0]).toBe(keys[1]);
    expect(keys[2]).not.toBe(keys[1]);
  });

  it('sends nothing without an address', async () => {
    const { user } = screenOf();
    const dialog = await opened(user);

    await user.click(within(dialog).getByRole('button', { name: 'workbench.files.share_send' }));

    expect(api.post).not.toHaveBeenCalled();
  });

  it('takes an access back, and never the owner’s', async () => {
    const { user } = screenOf();
    const dialog = await opened(user);
    await within(dialog).findByText('ana@x.org');

    const removals = within(dialog).getAllByRole('button', {
      name: 'workbench.files.share_remove',
    });
    expect(removals).toHaveLength(1);
    await user.click(removals[0]!);

    await waitFor(() => expect(api.post).toHaveBeenCalled());
    expect(api.post.mock.calls[0].slice(0, 2)).toEqual([
      '/workbench/files/sharing/remove',
      { file_id: 'p1', permission_id: 'p1' },
    ]);
  });

  it('opens a link anyone can follow, and says it does', async () => {
    api.post.mockResolvedValue({ id: 'l1', url: 'https://d.example/f1' });
    const { user } = screenOf();
    const dialog = await opened(user);
    await within(dialog).findByText('ana@x.org');

    await user.click(within(dialog).getByRole('button', { name: 'workbench.files.link_open' }));

    await waitFor(() => expect(api.post).toHaveBeenCalled());
    expect(api.post.mock.calls[0].slice(0, 2)).toEqual([
      '/workbench/files/sharing/link',
      { file_id: 'p1' },
    ]);
  });

  it('shows the link that exists, to copy or to close', async () => {
    sharing = { ...sharing, link: { id: 'l1', url: 'https://d.example/f1' } };
    const { user } = screenOf();
    const dialog = await opened(user);
    await within(dialog).findByText('workbench.files.link_on');

    await user.click(within(dialog).getByRole('button', { name: 'workbench.files.link_close' }));

    await waitFor(() => expect(api.post).toHaveBeenCalled());
    expect(api.post.mock.calls[0].slice(0, 2)).toEqual([
      '/workbench/files/sharing/remove',
      { file_id: 'p1', permission_id: 'l1' },
    ]);
  });

  it('says a sharing it cannot read, and offers to read it again', async () => {
    const { user } = screenOf();
    await screen.findByRole('button', { name: MORE });
    const reads = api.get.getMockImplementation();
    api.get.mockImplementation((path: string, options?: { params?: { id?: string } }) =>
      path === '/workbench/files/sharing'
        ? Promise.reject(new ApiError('down', 502, { detail: {} }))
        : reads?.(path, options)
    );
    const dialog = await opened(user);

    expect(
      await within(dialog).findByRole('button', { name: 'workbench.states.retry' })
    ).toBeInTheDocument();
  });
});

describe('FilesTool — a file going out by mail', () => {
  beforeEach(() => {
    nav.search = 'file=p1';
    mailReady = true;
  });

  it('opens the mail with it, carried by the page', async () => {
    const { user } = screenOf();

    await user.click(await screen.findByRole('button', { name: 'workbench.files.send_by_mail' }));

    expect(nav.push).toHaveBeenCalledWith('/en/dashboard/tools/mail');
    expect(takeHandoff('compose', 'owner')).toEqual({
      kind: 'compose',
      to: '',
      file: {
        id: 'p1',
        filename: 'Budget.pdf',
        mime_type: 'application/pdf',
        size: 200,
        origin: 'drive',
        expires_at: null,
      },
    });
  });

  it('is not offered without a mail to go to', async () => {
    mailReady = false;
    screenOf();

    await screen.findByRole('button', { name: 'workbench.files.share' });
    expect(screen.queryByRole('button', { name: 'workbench.files.send_by_mail' })).toBeNull();
  });

  it('is not offered for what cannot be read', async () => {
    details.p1 = detail({ downloadable: false });
    screenOf();

    await screen.findByRole('button', { name: 'workbench.files.share' });
    expect(screen.queryByRole('button', { name: 'workbench.files.send_by_mail' })).toBeNull();
  });

  it('is not offered past what can be read', async () => {
    details.p1 = detail({ size: CEILING + 1 });
    screenOf();

    await screen.findByRole('button', { name: 'workbench.files.share' });
    expect(screen.queryByRole('button', { name: 'workbench.files.send_by_mail' })).toBeNull();
  });
});

describe('FilesTool — a preview', () => {
  const answered = (body: string, type: string, cut = false) =>
    new Response(body, {
      headers: { 'Content-Type': type, 'X-Preview-Truncated': String(cut) },
    });

  beforeEach(() => {
    nav.search = 'file=p1';
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:shown') }));
    URL.revokeObjectURL = vi.fn();
  });

  it('shows an image, named as the file is', async () => {
    api.getResponse.mockResolvedValue(answered('png', 'image/png'));
    screenOf();

    const image = await screen.findByRole('img', { name: 'Budget.pdf' });

    expect(image).toHaveAttribute('src', 'blob:shown');
    const [path, options] = api.getResponse.mock.calls[0] as [
      string,
      { params: { id: string }; signal: AbortSignal },
    ];
    expect(path).toBe('/workbench/files/preview');
    expect(options.params).toEqual({ id: 'p1' });
    expect(options.signal).toBeInstanceOf(AbortSignal);
  });

  it('shows an excerpt, and says it is one', async () => {
    api.getResponse.mockResolvedValue(answered('Hello there', 'text/plain', true));
    screenOf();

    expect(await screen.findByText('Hello there')).toBeInTheDocument();
    expect(screen.getByText('workbench.files.preview_cut')).toBeInTheDocument();
  });

  it('says nothing of a whole text being cut', async () => {
    api.getResponse.mockResolvedValue(answered('Hello there', 'text/plain'));
    screenOf();

    await screen.findByText('Hello there');
    expect(screen.queryByText('workbench.files.preview_cut')).toBeNull();
  });

  it('shows no preview when none can be made, and the file stays usable', async () => {
    screenOf();

    await screen.findByRole('button', { name: MORE });
    await waitFor(() => expect(api.getResponse).toHaveBeenCalled());
    expect(screen.queryByRole('img')).toBeNull();
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('lays a table out, each sheet a click away', async () => {
    const sheets = {
      sheets: [
        {
          name: 'Budget',
          rows: [
            ['Item', 'Cost'],
            ['Rent', '700'],
          ],
          cut: false,
        },
        { name: 'Team', rows: [['Ana']], cut: false },
      ],
    };
    api.getResponse.mockResolvedValue(answered(JSON.stringify(sheets), 'application/json'));
    const { user } = screenOf();

    expect(await screen.findByRole('cell', { name: 'Rent' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Team' }));

    expect(screen.getByRole('cell', { name: 'Ana' })).toBeInTheDocument();
    expect(screen.queryByRole('cell', { name: 'Rent' })).toBeNull();
  });

  it('names no sheet of a table that has only one', async () => {
    const sheets = { sheets: [{ name: '', rows: [['a', 'b']], cut: false }] };
    api.getResponse.mockResolvedValue(answered(JSON.stringify(sheets), 'application/json'));
    screenOf();

    await screen.findByRole('cell', { name: 'a' });

    expect(screen.queryByRole('group', { name: 'workbench.files.sheets' })).toBeNull();
  });

  it('says a sheet holds nothing', async () => {
    const sheets = { sheets: [{ name: 'Empty', rows: [], cut: false }] };
    api.getResponse.mockResolvedValue(answered(JSON.stringify(sheets), 'application/json'));
    screenOf();

    expect(await screen.findByText('workbench.files.sheet_empty')).toBeInTheDocument();
  });

  it('says a table is only the beginning', async () => {
    const sheets = { sheets: [{ name: 'Long', rows: [['a']], cut: true }] };
    api.getResponse.mockResolvedValue(answered(JSON.stringify(sheets), 'application/json', true));
    screenOf();

    expect(await screen.findByText('workbench.files.preview_cut')).toBeInTheDocument();
  });

  it('enlarges what it shows without reading it again', async () => {
    api.getResponse.mockResolvedValue(answered('Hello there', 'text/plain'));
    const { user } = screenOf();
    await screen.findByText('Hello there');

    await user.click(screen.getByRole('button', { name: 'workbench.files.preview_enlarge' }));

    const window = await screen.findByRole('dialog');
    expect(within(window).getByText('Hello there')).toBeInTheDocument();
    expect(api.getResponse).toHaveBeenCalledTimes(1);
  });

  it('says a reading that failed, and reads again on the reader’s word', async () => {
    api.getResponse.mockRejectedValueOnce(new Error('gone'));
    api.getResponse.mockResolvedValue(answered('Hello there', 'text/plain'));
    const { user } = screenOf();

    const again = await screen.findByRole('button', { name: 'workbench.files.retry' });
    expect(screen.queryByRole('button', { name: 'workbench.files.preview_enlarge' })).toBeNull();
    await user.click(again);

    expect(await screen.findByText('Hello there')).toBeInTheDocument();
  });

  it('stays silent about a file there is nothing to show of: its downloads stay', async () => {
    screenOf();

    await screen.findByRole('button', { name: MORE });

    await waitFor(() => expect(api.getResponse).toHaveBeenCalled());
    expect(screen.queryByText('workbench.files.reading_failed')).toBeNull();
    expect(screen.queryByRole('button', { name: 'workbench.files.preview_enlarge' })).toBeNull();
  });

  it('asks nothing of what cannot be shown', async () => {
    details.p1 = detail({ previewable: false });
    screenOf();

    await screen.findByRole('button', { name: MORE });
    expect(api.getResponse).not.toHaveBeenCalled();
  });

  it('asks for a Google document through its formats', async () => {
    details.p1 = detail({ mime_type: 'application/vnd.google-apps.document', formats: ['pdf'] });
    api.getResponse.mockResolvedValue(answered('png', 'image/png'));
    screenOf();

    expect(await screen.findByRole('img', { name: 'Budget.pdf' })).toBeInTheDocument();
  });

  it('lets the image go when the file closes', async () => {
    api.getResponse.mockResolvedValue(answered('png', 'image/png'));
    const { unmount } = screenOf();
    await screen.findByRole('img', { name: 'Budget.pdf' });

    unmount();

    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:shown');
  });
});

describe('FilesTool — the trash', () => {
  const boxes = () => screen.findAllByRole('checkbox', { name: 'workbench.files.select_item' });
  const bar = () => screen.getByRole('region', { name: 'workbench.files.selection_region' });
  const undoOf = (call: unknown[] | undefined) =>
    (call?.[1] as { action: { label: string; onClick: () => void } }).action;

  it('offers to undo what it just put there, on any drive', async () => {
    features = [];
    nav.search = 'file=p1';
    const { user } = screenOf();
    await user.click(await screen.findByRole('button', { name: 'workbench.files.trash' }));
    await answerConfirmDialog(user, true);
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    const action = undoOf(toast.success.mock.calls[0]);
    expect(action.label).toBe('workbench.files.undo');
    api.post.mockClear();
    api.post.mockResolvedValue({ done: ['p1'], failed: [] });

    await act(async () => action.onClick());

    await waitFor(() => expect(api.post).toHaveBeenCalled());
    expect(api.post.mock.calls[0].slice(0, 2)).toEqual([
      '/workbench/files/restore',
      { file_ids: ['p1'] },
    ]);
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('workbench.files.restored'));
  });

  it('undoes a whole selection, what could not be undone said', async () => {
    api.post.mockResolvedValue({ done: ['p1', 'd1'], failed: [] });
    const { user } = screenOf();
    const [folder, , file] = await boxes();
    await user.click(folder!);
    await user.click(file!);
    await user.click(within(bar()).getByRole('button', { name: /workbench\.files\.trash/ }));
    await answerConfirmDialog(user, true);
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    const action = undoOf(toast.success.mock.calls[0]);
    api.post.mockClear();
    api.post.mockRejectedValue(new ApiError('no', 422, { detail: { code: 'provider_refused' } }));

    await act(async () => action.onClick());

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('workbench.errors.provider_refused')
    );
    expect(api.post.mock.calls[0][1]).toEqual({ file_ids: ['d1', 'p1'] });
  });

  it('leaves alone what was ticked since, when an act is undone later', async () => {
    api.post.mockResolvedValue({ done: ['p1'], failed: [] });
    const { user } = screenOf();
    const [, shortcut, file] = await boxes();
    await user.click(file!);
    await user.click(within(bar()).getByRole('button', { name: /workbench\.files\.trash/ }));
    await answerConfirmDialog(user, true);
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    const action = undoOf(toast.success.mock.calls[0]);
    await user.click(shortcut!);

    await act(async () => action.onClick());

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('workbench.files.restored'));
    expect((await boxes()).map(box => (box as HTMLInputElement).checked)).toEqual([
      false,
      true,
      false,
    ]);
  });

  describe('its view', () => {
    beforeEach(() => {
      nav.search = 'view=trash';
    });

    it('never offers to delete for good what a search found alive', async () => {
      const { user } = screenOf();
      await user.type(await screen.findByRole('searchbox'), 'budget{Enter}');
      await screen.findByRole('status');

      const [, , file] = await boxes();
      await user.click(file!);

      expect(
        within(bar()).queryByRole('button', { name: 'workbench.files.delete_forever' })
      ).toBeNull();
      expect(
        within(bar()).getByRole('button', { name: /workbench\.files\.trash/ })
      ).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'workbench.files.empty_trash' })).toBeNull();
    });

    it('offers no star: what is there is on its way out', async () => {
      screenOf();

      await screen.findByRole('link', { name: /Budget\.pdf/ });
      expect(screen.queryByRole('button', { name: 'workbench.files.star' })).toBeNull();
    });

    it('opens a folder as an item: what it held is not listed anywhere', async () => {
      screenOf();

      const link = await screen.findByRole('link', { name: /Projects/ });
      expect(link).toHaveAttribute('href', `${BASE}?view=trash&file=d1`);
    });

    it('restores what is ticked, and offers nothing else of the living', async () => {
      const { user } = screenOf();
      const [, , file] = await boxes();
      await user.click(file!);

      expect(within(bar()).queryByRole('button', { name: 'workbench.files.move' })).toBeNull();
      expect(within(bar()).queryByRole('button', { name: 'workbench.files.rename' })).toBeNull();
      expect(within(bar()).queryByRole('button', { name: 'workbench.files.trash' })).toBeNull();
      await user.click(within(bar()).getByRole('button', { name: 'workbench.files.restore' }));

      await waitFor(() => expect(toast.success).toHaveBeenCalledWith('workbench.files.restored'));
      expect(api.post.mock.calls[0].slice(0, 2)).toEqual([
        '/workbench/files/restore',
        { file_ids: ['p1'] },
      ]);
      expect((await boxes()).map(box => (box as HTMLInputElement).checked)).toEqual([
        false,
        false,
        false,
      ]);
    });

    it('deletes for good after one question, each answered', async () => {
      api.post.mockResolvedValue({ done: ['p1'], failed: [{ id: 'd1', status: 'failed' }] });
      const { user } = screenOf();
      const [folder, , file] = await boxes();
      await user.click(folder!);
      await user.click(file!);

      await user.click(
        within(bar()).getByRole('button', { name: 'workbench.files.delete_forever' })
      );
      await answerConfirmDialog(user, true);

      await waitFor(() => expect(toast.error).toHaveBeenCalledWith('workbench.files.partial'));
      expect(api.post.mock.calls[0].slice(0, 2)).toEqual([
        '/workbench/files/delete',
        { file_ids: ['d1', 'p1'] },
      ]);
    });

    it('deletes nothing when the question is declined', async () => {
      const { user } = screenOf();
      const [, , file] = await boxes();
      await user.click(file!);

      await user.click(
        within(bar()).getByRole('button', { name: 'workbench.files.delete_forever' })
      );
      await answerConfirmDialog(user, false);

      await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull());
      expect(api.post).not.toHaveBeenCalled();
    });

    it('empties after one question, and reads the list again', async () => {
      api.post.mockResolvedValue(undefined);
      const { user } = screenOf();
      await user.click(await screen.findByRole('button', { name: 'workbench.files.empty_trash' }));
      api.get.mockClear();

      await answerConfirmDialog(user, true);

      await waitFor(() => expect(toast.success).toHaveBeenCalledWith('workbench.files.emptied'));
      expect(api.post.mock.calls[0][0]).toBe('/workbench/files/trash/empty');
      expect(listCalls().length).toBeGreaterThan(0);
    });

    it('empties nothing when the question is declined', async () => {
      const { user } = screenOf();
      await user.click(await screen.findByRole('button', { name: 'workbench.files.empty_trash' }));

      await answerConfirmDialog(user, false);

      await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull());
      expect(api.post).not.toHaveBeenCalled();
    });

    it('says what stopped the emptying', async () => {
      api.post.mockRejectedValue(
        new ApiError('no', 502, { detail: { code: 'provider_unavailable' } })
      );
      const { user } = screenOf();
      await user.click(await screen.findByRole('button', { name: 'workbench.files.empty_trash' }));

      await answerConfirmDialog(user, true);

      await waitFor(() =>
        expect(toast.error).toHaveBeenCalledWith('workbench.errors.provider_unavailable')
      );
    });

    it('opens a file with what the trash allows, and nothing else', async () => {
      nav.search = 'view=trash&file=p1';
      const { user } = screenOf();
      // By its file's name: the pane exists from the first render, empty while the file is read.
      const detail = await screen.findByRole('article', { name: 'Budget.pdf' });
      expect(within(detail).queryByRole('button', { name: MORE })).toBeNull();
      expect(within(detail).queryByRole('button', { name: 'workbench.files.trash' })).toBeNull();
      expect(
        within(detail).getByRole('button', { name: 'workbench.files.delete_forever' })
      ).toHaveClass('text-destructive');

      await user.click(within(detail).getByRole('button', { name: 'workbench.files.restore' }));

      await waitFor(() => expect(toast.success).toHaveBeenCalledWith('workbench.files.restored'));
      expect(nav.replace).toHaveBeenCalledWith(`${BASE}?view=trash`, { scroll: false });
    });

    it('deletes an open file for good after one question, then closes it', async () => {
      nav.search = 'view=trash&file=p1';
      const { user } = screenOf();
      const detail = await screen.findByRole('article', { name: 'Budget.pdf' });

      await user.click(
        within(detail).getByRole('button', { name: 'workbench.files.delete_forever' })
      );
      await answerConfirmDialog(user, true);

      await waitFor(() => expect(toast.success).toHaveBeenCalledWith('workbench.files.deleted'));
      expect(nav.replace).toHaveBeenCalledWith(`${BASE}?view=trash`, { scroll: false });
    });
  });
});

describe('FilesTool — files sent to the drive', () => {
  const chooser = () => screen.getByLabelText('workbench.files.send_files');
  const named = (name: string, size = 10) =>
    Object.defineProperty(new File(['x'], name, { type: 'text/plain' }), 'size', { value: size });
  const formOf = (call: number) => sendFile.mock.calls[call]?.[1] as FormData;

  beforeEach(() => {
    sendFile.mockResolvedValue(item({ id: 'u1' }));
  });

  it('sends what is chosen to the folder the list stands in, and reads it again', async () => {
    nav.search = 'folder=d2';
    const { user } = screenOf();
    await screen.findByRole('button', { name: 'workbench.files.new_folder' });
    api.get.mockClear();

    await user.upload(chooser(), named('Notes.txt'));

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('workbench.files.sent'));
    expect(sendFile.mock.calls[0]?.[0]).toBe('/workbench/files/upload');
    const form = formOf(0);
    expect(form.get('name')).toBe('Notes.txt');
    expect(form.get('folder_id')).toBe('d2');
    expect(form.get('idempotency_key')).toEqual(expect.any(String));
    expect((form.get('file') as File).name).toBe('Notes.txt');
    expect(listCalls().length).toBeGreaterThan(0);
  });

  it('names no folder at the top of the drive', async () => {
    const { user } = screenOf();
    await screen.findByRole('button', { name: 'workbench.files.new_folder' });

    await user.upload(chooser(), named('Notes.txt'));

    await waitFor(() => expect(sendFile).toHaveBeenCalled());
    expect(formOf(0).has('folder_id')).toBe(false);
  });

  it('sends one file at a time, each under its own submission', async () => {
    let finish: (value: unknown) => void = () => undefined;
    sendFile.mockReturnValueOnce(new Promise(resolve => (finish = resolve)));
    const { user } = screenOf();
    await screen.findByRole('button', { name: 'workbench.files.new_folder' });

    await user.upload(chooser(), [named('a.txt'), named('b.txt')]);

    await waitFor(() => expect(sendFile).toHaveBeenCalledTimes(1));
    finish(item({}));
    await waitFor(() => expect(sendFile).toHaveBeenCalledTimes(2));
    expect(formOf(0).get('idempotency_key')).not.toBe(formOf(1).get('idempotency_key'));
  });

  it('shows what is on its way, and how far', async () => {
    let progress: (percent: number) => void = () => undefined;
    let finish: (value: unknown) => void = () => undefined;
    sendFile.mockImplementationOnce((_path, _form, onProgress: (percent: number) => void) => {
      progress = onProgress;
      return new Promise(resolve => (finish = resolve));
    });
    const { user } = screenOf();
    await screen.findByRole('button', { name: 'workbench.files.new_folder' });

    await user.upload(chooser(), named('a.txt'));
    await screen.findByText('workbench.files.sending');
    act(() => progress(40));

    const bar = () =>
      screen.queryByRole('progressbar', { name: 'workbench.files.sending_progress' });
    await waitFor(() => expect(bar()).toHaveAttribute('value', '40'));
    await act(async () => finish(item({})));
    await waitFor(() => expect(bar()).toBeNull());
  });

  it('says a file past the published ceiling and sends the others', async () => {
    const { user } = screenOf();
    await screen.findByRole('button', { name: 'workbench.files.new_folder' });

    await user.upload(chooser(), [named('huge.bin', CEILING + 1), named('ok.txt', CEILING)]);

    await waitFor(() => expect(sendFile).toHaveBeenCalledTimes(1));
    expect(formOf(0).get('name')).toBe('ok.txt');
    expect(toast.error).toHaveBeenCalledWith('workbench.files.send_too_large');
  });

  it('says a refusal in its own words', async () => {
    sendFile.mockRejectedValue(new ApiError('taken', 409, { detail: { code: 'name_taken' } }));
    const { user } = screenOf();
    await screen.findByRole('button', { name: 'workbench.files.new_folder' });

    await user.upload(chooser(), named('a.txt'));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('workbench.errors.name_taken'));
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('counts what went and what did not, and goes on after a failure', async () => {
    sendFile.mockRejectedValueOnce(new Error('lost'));
    const { user } = screenOf();
    await screen.findByRole('button', { name: 'workbench.files.new_folder' });

    await user.upload(chooser(), [named('a.txt'), named('b.txt')]);

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('workbench.files.sent_partial'));
    expect(sendFile).toHaveBeenCalledTimes(2);
  });

  it('stops on demand: what waits is never sent, and what went is said', async () => {
    const stops: AbortSignal[] = [];
    sendFile.mockImplementationOnce(
      (_path, _form, _progress, signal: AbortSignal) =>
        new Promise((_resolve, reject) => {
          stops.push(signal);
          signal.addEventListener('abort', () => reject(new FileSendStopped()));
        })
    );
    const { user } = screenOf();
    await screen.findByRole('button', { name: 'workbench.files.new_folder' });
    await user.upload(chooser(), [named('a.txt'), named('b.txt')]);
    const reads = listCalls().length;

    await user.click(await screen.findByRole('button', { name: 'workbench.files.stop_sending' }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('workbench.files.send_stopped'));
    expect(sendFile).toHaveBeenCalledTimes(1);
    expect(listCalls().length).toBeGreaterThan(reads);
  });

  it('forgets what waited when stopped: the next file leaves alone', async () => {
    sendFile.mockImplementationOnce(
      (_path, _form, _progress, signal: AbortSignal) =>
        new Promise((_resolve, reject) => {
          signal.addEventListener('abort', () => reject(new FileSendStopped()));
        })
    );
    const { user } = screenOf();
    await screen.findByRole('button', { name: 'workbench.files.new_folder' });
    await user.upload(chooser(), [named('a.txt'), named('b.txt')]);
    await user.click(await screen.findByRole('button', { name: 'workbench.files.stop_sending' }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('workbench.files.send_stopped'));

    await user.upload(chooser(), named('c.txt'));

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('workbench.files.sent'));
    expect(sendFile.mock.calls.map(([, form]) => (form as FormData).get('name'))).toEqual([
      'a.txt',
      'c.txt',
    ]);
  });

  it('takes what is dropped on the list, the same way', async () => {
    screenOf();
    const pane = await screen.findByTestId('files-drop');
    const files = [named('a.txt')];
    const dataTransfer = { types: ['Files'], files, items: [] };

    fireEvent.dragOver(pane, { dataTransfer });
    expect(await screen.findByText('workbench.files.drop_here')).toBeInTheDocument();
    fireEvent.drop(pane, { dataTransfer });

    await waitFor(() => expect(sendFile).toHaveBeenCalledTimes(1));
    expect(screen.queryByText('workbench.files.drop_here')).toBeNull();
  });

  it('says a folder dropped: only files are sent', async () => {
    screenOf();
    const pane = await screen.findByTestId('files-drop');
    const dataTransfer = {
      types: ['Files'],
      files: [named('Photos', 0), named('a.txt')],
      items: [
        { webkitGetAsEntry: () => ({ isDirectory: true }) },
        { webkitGetAsEntry: () => ({ isDirectory: false }) },
      ],
    };

    fireEvent.drop(pane, { dataTransfer });

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('workbench.files.send_no_folders')
    );
    await waitFor(() => expect(sendFile).toHaveBeenCalledTimes(1));
    expect(formOf(0).get('name')).toBe('a.txt');
  });

  it('ignores what is dragged but is no file, a selection of text for one', async () => {
    screenOf();
    const pane = await screen.findByTestId('files-drop');

    fireEvent.dragOver(pane, { dataTransfer: { types: ['text/plain'], files: [], items: [] } });

    expect(screen.queryByText('workbench.files.drop_here')).toBeNull();
  });

  it('takes nothing during a search, which stands nowhere', async () => {
    const { user } = screenOf();
    await user.type(await screen.findByRole('searchbox'), 'budget{Enter}');
    await screen.findByRole('status');
    const pane = screen.getByTestId('files-drop');
    const dataTransfer = { types: ['Files'], files: [named('a.txt')], items: [] };

    fireEvent.dragOver(pane, { dataTransfer });
    fireEvent.drop(pane, { dataTransfer });

    expect(screen.queryByLabelText('workbench.files.send_files')).toBeNull();
    expect(sendFile).not.toHaveBeenCalled();
  });
});

describe('FilesTool — panes sized by hand', () => {
  it('names its separator and drives the pane it sits beside, back to the layout on Enter', async () => {
    screenOf();
    const separator = await screen.findByRole('separator', { name: 'workbench.panes.files_list' });
    const pane = document.getElementById(separator.getAttribute('aria-controls') ?? '');

    expect(within(pane as HTMLElement).getByRole('searchbox')).toBeInTheDocument();
    fireEvent.keyDown(separator, { key: 'End' });
    expect(pane?.style.getPropertyValue('--pane-w')).toMatch(/^\d+px$/);
    fireEvent.keyDown(separator, { key: 'Enter' });
    expect(pane?.style.getPropertyValue('--pane-w')).toBe('');
  });
});

describe('FilesTool — a text changed by hand', () => {
  const edited = { text: 'Hello', tag: 'tag-1' };
  const reads = () => api.get.mock.calls.filter(([path]) => path === '/workbench/files/text');
  const shown = api.get.getMockImplementation;

  beforeEach(() => {
    nav.search = 'file=p1';
    details.p1 = detail({ editable: true, previewable: false, mime_type: 'text/plain' });
    const answer = shown();
    api.get.mockImplementation((path: string, config?: unknown) =>
      path === '/workbench/files/text' ? Promise.resolve(edited) : answer?.(path, config)
    );
    api.put.mockResolvedValue(item({}));
  });

  const open = async () => {
    const rendered = screenOf();
    await rendered.user.click(await screen.findByRole('button', { name: MORE }));
    await rendered.user.click(
      await screen.findByRole('menuitem', { name: 'workbench.files.edit_text' })
    );
    const field = await screen.findByRole('textbox', { name: 'workbench.files.text_field' });
    return { ...rendered, field };
  };

  it('offers nothing for what is no text held whole', async () => {
    details.p1 = detail({ editable: false, previewable: false });
    const { user } = screenOf();

    await user.click(await screen.findByRole('button', { name: MORE }));

    await screen.findByRole('menuitem', { name: 'workbench.files.rename' });
    expect(screen.queryByRole('menuitem', { name: 'workbench.files.edit_text' })).toBeNull();
  });

  it('asks the drive only once the person opens it', async () => {
    const { user } = screenOf();

    await user.click(await screen.findByRole('button', { name: MORE }));
    await screen.findByRole('menuitem', { name: 'workbench.files.edit_text' });

    expect(reads()).toEqual([]);
  });

  it('writes the words back on the version they were read at', async () => {
    const { user, field } = await open();
    expect(field).toHaveValue('Hello');

    await user.clear(field);
    await user.type(field, 'Bye');
    await user.click(screen.getByRole('button', { name: 'workbench.files.text_save' }));

    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith('/workbench/files/text', {
        id: 'p1',
        text: 'Bye',
        tag: 'tag-1',
      })
    );
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('workbench.files.text_saved'));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('reads the file and its list again once written', async () => {
    const { user, field } = await open();
    const reads = (path: string) => api.get.mock.calls.filter(([asked]) => asked === path).length;
    const file = reads('/workbench/files/file');
    const list = reads('/workbench/files');

    await user.type(field, '!');
    await user.click(screen.getByRole('button', { name: 'workbench.files.text_save' }));

    await waitFor(() => expect(reads('/workbench/files/file')).toBe(file + 1));
    await waitFor(() => expect(reads('/workbench/files')).toBe(list + 1));
  });

  it('saves nothing that did not change', async () => {
    await open();

    expect(screen.getByRole('button', { name: 'workbench.files.text_save' })).toBeDisabled();
  });

  it('keeps the words typed when the file changed meanwhile, and offers the current one', async () => {
    api.put.mockRejectedValue(new ApiError('refused', 409, { detail: { code: 'conflict' } }));
    const { user, field } = await open();

    await user.type(field, ' world');
    await user.click(screen.getByRole('button', { name: 'workbench.files.text_save' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('workbench.errors.conflict');
    expect(field).toHaveValue('Hello world');

    await user.click(screen.getByRole('button', { name: 'workbench.files.text_reload' }));

    await waitFor(() => expect(field).toHaveValue('Hello'));
    expect(screen.queryByRole('alert')).toBeNull();
    expect(reads()).toHaveLength(2);
  });

  it('offers no other version for any other refusal', async () => {
    api.put.mockRejectedValue(new ApiError('refused', 423, { detail: { code: 'file_locked' } }));
    const { user, field } = await open();

    await user.type(field, '!');
    await user.click(screen.getByRole('button', { name: 'workbench.files.text_save' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('workbench.errors.file_locked');
    expect(screen.queryByRole('button', { name: 'workbench.files.text_reload' })).toBeNull();
  });

  it('says a refusal nobody named in its own words', async () => {
    api.put.mockRejectedValue(new Error('lost'));
    const { user, field } = await open();

    await user.type(field, '!');
    await user.click(screen.getByRole('button', { name: 'workbench.files.text_save' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('workbench.files.text_save_failed');
  });

  it('leaves at once when nothing changed', async () => {
    const { user } = await open();

    await user.click(screen.getByRole('button', { name: 'common.cancel' }));

    expect(screen.queryByRole('textbox', { name: 'workbench.files.text_field' })).toBeNull();
  });

  it('asks before leaving words unsaved, and stays on a no', async () => {
    const { user, field } = await open();
    await user.type(field, '!');

    await user.click(screen.getByRole('button', { name: 'common.cancel' }));
    await answerConfirmDialog(user, false);

    expect(field).toHaveValue('Hello!');
  });

  it('leaves on a yes, and writes nothing', async () => {
    const { user, field } = await open();
    await user.type(field, '!');

    await user.click(screen.getByRole('button', { name: 'common.cancel' }));
    await answerConfirmDialog(user, true);

    await waitFor(() =>
      expect(screen.queryByRole('textbox', { name: 'workbench.files.text_field' })).toBeNull()
    );
    expect(api.put).not.toHaveBeenCalled();
  });

  it('says no more of a failed read once a new one answered', async () => {
    const answer = api.get.getMockImplementation();
    let failing = false;
    api.get.mockImplementation((path: string, config?: unknown) => {
      if (path !== '/workbench/files/text') return answer?.(path, config);
      return failing ? Promise.reject(new Error('gone')) : Promise.resolve(edited);
    });
    api.put.mockRejectedValue(new ApiError('refused', 409, { detail: { code: 'conflict' } }));
    const { user, field } = await open();

    await user.type(field, '!');
    await user.click(screen.getByRole('button', { name: 'workbench.files.text_save' }));
    failing = true;
    await user.click(await screen.findByRole('button', { name: 'workbench.files.text_reload' }));
    await screen.findByText('workbench.files.text_read_failed');
    failing = false;
    await user.click(screen.getByRole('button', { name: 'workbench.files.text_reload' }));

    await waitFor(() => expect(screen.queryByText('workbench.files.text_read_failed')).toBeNull());
  });

  it('says what it could not read, with nothing to type in', async () => {
    const answer = api.get.getMockImplementation();
    api.get.mockImplementation((path: string, config?: unknown) =>
      path === '/workbench/files/text' ? Promise.reject(new Error('gone')) : answer?.(path, config)
    );
    const { user } = screenOf();

    await user.click(await screen.findByRole('button', { name: MORE }));
    await user.click(await screen.findByRole('menuitem', { name: 'workbench.files.edit_text' }));

    expect(await screen.findByText('workbench.files.text_read_failed')).toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: 'workbench.files.text_field' })).toBeNull();
  });
});

beforeEach(() => {
  setHandoffOwner(null);
  setHandoffOwner('owner');
});

afterEach(() => setHandoffOwner(null));
