/**
 * The « Tools » files screen (ADR-369, Task 8.2).
 *
 * A folder opens in the list and a shortcut opens what it points at; the
 * breadcrumb is the open folder's own detail; a search runs on Enter across
 * Drive and says so. A Google document downloads once per format through the
 * API's own origin, a file past the ceiling is said instead of offered, « Open
 * in Drive » opens a tab that cannot reach back, and the trash asks first.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { fireEvent, renderWithProviders, screen, waitFor, within } from '@/__tests__/test-utils';
import type { AppConfig } from '@/hooks/useAppConfig';
import type {
  WorkbenchAvailability,
  WorkbenchDriveItem,
  WorkbenchFileDetail,
} from '@/lib/workbench/types';

type ShellConfig = Pick<AppConfig, 'capabilities'> & { features: { workbench_enabled?: boolean } };

const { api, nav } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() },
  nav: { search: '', push: vi.fn(), replace: vi.fn() },
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
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
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

function rail(): WorkbenchAvailability {
  return {
    tools: [
      { tool: 'files', state: 'ready', provider: 'google_drive', features: ['export'], bounds: {} },
    ],
    limits: {
      page_size: 25,
      bulk_max_items: 50,
      download_max_bytes: CEILING,
      calendar_window_max_events: 500,
    },
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  nav.search = '';
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
  api.get.mockImplementation((path: string, options?: { params?: { id?: string } }) => {
    if (path === '/workbench') return Promise.resolve(rail());
    if (path === '/workbench/files') return Promise.resolve(page);
    if (path === '/workbench/files/file') {
      return Promise.resolve(details[options?.params?.id ?? '']);
    }
    return Promise.resolve({});
  });
  api.post.mockResolvedValue({ done: ['p1'], failed: [] });
});

function screenOf() {
  return renderWithProviders(
    <WorkbenchShell lng="en">
      <FilesTool lng="en" />
    </WorkbenchShell>
  );
}

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

describe('FilesTool — the open file', () => {
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
