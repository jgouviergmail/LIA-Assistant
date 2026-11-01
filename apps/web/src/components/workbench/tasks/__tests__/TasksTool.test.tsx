/**
 * The « Tools » tasks screen (ADR-369, Task 6.2): the lists and the tasks of
 * the open one; « Load more » exactly when the provider has more; subtasks
 * under their parent; an empty list names the way out; a completion shows at
 * once and, refused, is rolled back with the refusal's own sentence.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { fireEvent, renderWithProviders, screen, waitFor, within } from '@/__tests__/test-utils';
import type { AppConfig } from '@/hooks/useAppConfig';
import { ApiError } from '@/lib/api-client';
import type {
  WorkbenchAvailability,
  WorkbenchTask,
  WorkbenchToolState,
} from '@/lib/workbench/types';

type ShellConfig = Pick<AppConfig, 'capabilities'> & { features: { workbench_enabled?: boolean } };

const { api, nav, toast, media } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
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
  usePathname: () => '/en/dashboard/tools/tasks',
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
import { TasksTool } from '../TasksTool';

function rail(state: WorkbenchToolState = 'ready'): WorkbenchAvailability {
  return {
    tools: [
      {
        tool: 'tasks',
        state,
        provider: state === 'ready' ? 'google_tasks' : null,
        features: state === 'ready' ? ['list_management', 'subtasks', 'due_date_only'] : [],
        bounds: state === 'ready' ? { title_max_chars: 1024, notes_max_chars: 8192 } : {},
      },
    ],
    limits: {
      page_size: 25,
      bulk_max_items: 50,
      download_max_bytes: 1,
      calendar_window_max_events: 500,
    },
  };
}

function task(id: string, overrides: Partial<WorkbenchTask> = {}): WorkbenchTask {
  return {
    id,
    title: `Task ${id}`,
    notes: null,
    completed: false,
    due: null,
    parent: null,
    position: null,
    ...overrides,
  };
}

let tasksPage: { items: WorkbenchTask[]; next_page_token: string | null };

beforeEach(() => {
  vi.clearAllMocks();
  nav.search = '';
  media.desktop = true;
  tasksPage = { items: [task('t1'), task('t2')], next_page_token: null };
  api.get.mockImplementation((path: string) => {
    if (path === '/workbench') return Promise.resolve(rail());
    if (path === '/workbench/tasks/lists') {
      return Promise.resolve({
        items: [
          { id: 'l1', title: 'Home' },
          { id: 'l2', title: 'Trip' },
        ],
        next_page_token: null,
      });
    }
    return Promise.resolve(tasksPage);
  });
});

function tool() {
  return (
    <WorkbenchShell lng="en">
      <TasksTool lng="en" />
    </WorkbenchShell>
  );
}

function screenOf() {
  return renderWithProviders(tool());
}

describe('TasksTool', () => {
  it('opens the first list and shows its tasks', async () => {
    screenOf();

    expect(await screen.findByText('Task t1')).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('/workbench/tasks', {
      params: { list_id: 'l1', show_completed: false },
      signal: expect.any(AbortSignal),
    });
    const lists = screen.getByRole('navigation', { name: 'workbench.tasks.lists_title' });
    expect(within(lists).getByRole('link', { name: 'Home' })).toHaveAttribute(
      'aria-current',
      'page'
    );
  });

  it('opens the list the address names', async () => {
    nav.search = 'list=l2';
    screenOf();

    await screen.findByText('Task t1');
    expect(api.get).toHaveBeenCalledWith('/workbench/tasks', {
      params: { list_id: 'l2', show_completed: false },
      signal: expect.any(AbortSignal),
    });
  });

  it('offers « Load more » exactly when the provider has more', async () => {
    tasksPage = { items: [task('t1')], next_page_token: 'p2' };
    const { unmount } = screenOf();
    expect(
      await screen.findByRole('button', { name: 'workbench.tasks.load_more' })
    ).toBeInTheDocument();
    unmount();

    tasksPage = { items: [task('t1')], next_page_token: null };
    screenOf();
    await screen.findByText('Task t1');
    expect(screen.queryByRole('button', { name: 'workbench.tasks.load_more' })).toBeNull();
  });

  it('puts a subtask under its parent', async () => {
    tasksPage = {
      items: [task('parent'), task('child', { parent: 'parent' }), task('other')],
      next_page_token: null,
    };
    screenOf();

    const child = await screen.findByText('Task child');
    const parentRow = screen.getByText('Task parent').closest('li');
    expect(parentRow).not.toBeNull();
    expect(parentRow?.contains(child)).toBe(true);
    expect(screen.getByText('Task other').closest('li')?.contains(child)).toBe(false);
  });

  it('names the way out of an empty list: the field to add a task', async () => {
    tasksPage = { items: [], next_page_token: null };
    const { user } = screenOf();

    await user.click(await screen.findByRole('button', { name: 'workbench.tasks.add_first' }));

    expect(screen.getByRole('textbox', { name: 'workbench.tasks.new_task' })).toHaveFocus();
  });

  it('rolls a refused completion back and says why, in the refusal’s words', async () => {
    api.patch.mockRejectedValueOnce(
      new ApiError('refused', 502, { detail: { code: 'provider_unavailable' } })
    );
    const { user } = screenOf();

    const [box] = await screen.findAllByRole('checkbox', { name: 'workbench.tasks.complete' });
    await user.click(box!);

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('workbench.errors.provider_unavailable')
    );
    expect(
      screen.getAllByRole('checkbox', { name: 'workbench.tasks.complete' })[0]
    ).not.toBeChecked();
  });

  it('gives the focus back to the task when its detail closes', async () => {
    nav.search = 'list=l1&task=t1';
    const { rerender } = screenOf();
    await screen.findByRole('complementary', { name: 'workbench.tasks.detail_title' });

    nav.search = 'list=l1';
    rerender(tool());

    await waitFor(() => expect(screen.getByRole('link', { name: /Task t1/ })).toHaveFocus());
  });

  it('below lg, hands the focus to the detail that replaces the list', async () => {
    media.desktop = false;
    nav.search = 'list=l1&task=t1';
    screenOf();

    const back = await screen.findByRole('button', { name: 'workbench.tasks.back_to_list' });
    await waitFor(() => expect(back).toHaveFocus());
  });

  it('says what to do when no tasks service is connected', async () => {
    api.get.mockImplementation((path: string) =>
      path === '/workbench'
        ? Promise.resolve(rail('not_connected'))
        : Promise.reject(new Error('no'))
    );
    screenOf();

    expect(await screen.findByText('workbench.states.not_connected_title')).toBeInTheDocument();
    expect(api.get).not.toHaveBeenCalledWith('/workbench/tasks/lists', expect.anything());
  });
});

describe('TasksTool — panes sized by hand', () => {
  it('names its separator and drives the pane it sits beside, back to the layout on Enter', async () => {
    screenOf();
    const separator = await screen.findByRole('separator', { name: 'workbench.panes.tasks_lists' });
    const pane = document.getElementById(separator.getAttribute('aria-controls') ?? '');

    expect(pane).toHaveAccessibleName('workbench.tasks.lists_title');
    fireEvent.keyDown(separator, { key: 'End' });
    expect(pane?.style.getPropertyValue('--pane-w')).toMatch(/^\d+px$/);
    fireEvent.keyDown(separator, { key: 'Enter' });
    expect(pane?.style.getPropertyValue('--pane-w')).toBe('');
  });
});
