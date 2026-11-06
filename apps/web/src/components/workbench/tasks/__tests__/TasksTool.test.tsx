/**
 * The « Tools » tasks screen (ADR-369, Task 6.2): the lists and the tasks of
 * the open one; « Load more » exactly when the provider has more; subtasks
 * under their parent; an empty list names the way out; a completion shows at
 * once and, refused, is rolled back with the refusal's own sentence.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
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
  DueTasks,
  WorkbenchAvailability,
  WorkbenchFeature,
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

import { handOff } from '@/lib/workbench/handoff';

import { WorkbenchShell } from '../../WorkbenchShell';
import { TasksTool } from '../TasksTool';

const GOOGLE: WorkbenchFeature[] = ['list_management', 'subtasks', 'due_date_only', 'task_order'];
const TO_DO: WorkbenchFeature[] = ['list_management', 'task_steps', 'task_details'];

function rail(state: WorkbenchToolState = 'ready'): WorkbenchAvailability {
  return {
    tools: [
      {
        tool: 'tasks',
        state,
        provider: state === 'ready' ? 'google_tasks' : null,
        features: state === 'ready' ? features : [],
        bounds: state === 'ready' ? { title_max_chars: 1024, notes_max_chars: 8192 } : {},
      },
    ],
    limits: {
      page_size: 25,
      bulk_max_items: 50,
      download_max_bytes: 1,
      upload_max_bytes: 1,
      calendar_window_max_events: 500,
      send_undo_seconds: 0,
      draft_autosave_seconds: 0,
      search_max_chars: 500,
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
    steps: [],
    importance: null,
    reminder: null,
    repeat: null,
    ...overrides,
  };
}

let tasksPage: { items: WorkbenchTask[]; next_page_token: string | null };
let defaultList: string | null;
let features: WorkbenchFeature[];
let viewAnswer: DueTasks | Error;

beforeEach(() => {
  vi.clearAllMocks();
  nav.search = '';
  media.desktop = true;
  tasksPage = { items: [task('t1'), task('t2')], next_page_token: null };
  defaultList = null;
  features = GOOGLE;
  viewAnswer = { tasks: [], truncated: false, failed: [] };
  api.get.mockImplementation((path: string) => {
    if (path === '/workbench') return Promise.resolve(rail());
    if (path === '/workbench/tasks/view') {
      return viewAnswer instanceof Error ? Promise.reject(viewAnswer) : Promise.resolve(viewAnswer);
    }
    if (path === '/workbench/tasks/lists') {
      return Promise.resolve({
        items: [
          { id: 'l1', title: 'Home', default: false },
          { id: 'l2', title: 'Trip', default: defaultList === 'l2' },
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

describe('TasksTool — what another tool hands it', () => {
  it('holds the title for the person to confirm, and sends the notes with it', async () => {
    handOff({ kind: 'task', title: 'Answer Ana', notes: 'https://lia.example/mail?id=m1' });
    const { user } = screenOf();

    const field = await screen.findByRole('textbox', { name: 'workbench.tasks.new_task' });
    expect(field).toHaveValue('Answer Ana');
    await user.type(field, '{Enter}');

    await waitFor(() => expect(api.post).toHaveBeenCalled());
    expect(api.post.mock.calls[0][1]).toMatchObject({
      title: 'Answer Ana',
      notes: 'https://lia.example/mail?id=m1',
    });
  });
});

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

  it('re-reads what it shows when the person asks', async () => {
    const { user } = screenOf();
    await screen.findByText('Task t1');
    api.get.mockClear();

    await user.click(screen.getByRole('button', { name: 'workbench.states.refresh' }));

    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/workbench/tasks/lists', expect.anything())
    );
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/workbench/tasks', expect.anything())
    );
  });

  it('opens the list the settings chose, when the address names none', async () => {
    defaultList = 'l2';
    screenOf();

    await screen.findByText('Task t1');
    expect(api.get).toHaveBeenCalledWith('/workbench/tasks', {
      params: { list_id: 'l2', show_completed: false },
      signal: expect.any(AbortSignal),
    });
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

const due = (id: string, day: string) => ({ id, list_id: 'l2', title: `Due ${id}`, due: day });
const posted = (path: string) => api.post.mock.calls.filter(([called]) => called === path).at(-1);
const patched = (path: string) =>
  api.patch.mock.calls.filter(([called]) => called === path).at(-1)?.[1];

describe('TasksTool — the views across the lists', () => {
  const pane = () => screen.findByRole('navigation', { name: 'workbench.tasks.lists_title' });

  it('offers them beside the lists, each on the address', async () => {
    screenOf();

    const link = within(await pane()).getByRole('link', {
      name: 'workbench.tasks.views.overdue',
    });
    expect(link).toHaveAttribute('href', expect.stringContaining('view=overdue'));
  });

  it("reads one for the day, naming each task's list and how many", async () => {
    nav.search = 'view=today';
    viewAnswer = { tasks: [due('d1', '2026-11-05')], truncated: false, failed: [] };

    screenOf();

    const row = await screen.findByRole('link', { name: /Due d1/ });
    expect(row).toHaveTextContent('Trip');
    expect(row).toHaveAttribute('href', expect.stringContaining('list=l2'));
    expect(row).toHaveAttribute('href', expect.stringContaining('task=d1'));
    expect(screen.getByText('workbench.tasks.to_do')).toBeInTheDocument();
  });

  it('marks the view as the open place, no list being open', async () => {
    nav.search = 'view=today';

    screenOf();

    const lists = await pane();
    expect(
      within(lists).getByRole('link', { name: 'workbench.tasks.views.today' })
    ).toHaveAttribute('aria-current', 'page');
    expect(await within(lists).findByRole('link', { name: 'Home' })).not.toHaveAttribute(
      'aria-current'
    );
  });

  it('reads no list under it', async () => {
    nav.search = 'view=today';

    screenOf();

    await screen.findByRole('heading', { name: 'workbench.tasks.views.today' });
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/workbench/tasks/lists', expect.anything())
    );
    expect(api.get).not.toHaveBeenCalledWith('/workbench/tasks', expect.anything());
  });

  it('takes away the figure and says so when a list could not be read', async () => {
    nav.search = 'view=overdue';
    viewAnswer = { tasks: [due('d1', '2026-11-01')], truncated: false, failed: ['l1'] };

    screenOf();

    expect(await screen.findByText('workbench.tasks.view_partial')).toBeInTheDocument();
    expect(screen.queryByText('workbench.tasks.to_do')).not.toBeInTheDocument();
  });

  it('takes away the figure when a view was cut', async () => {
    nav.search = 'view=overdue';
    viewAnswer = { tasks: [due('d1', '2026-11-01')], truncated: true, failed: [] };

    screenOf();

    await screen.findByRole('heading', { name: 'workbench.tasks.views.overdue' });
    await screen.findByText('Due d1');
    expect(screen.queryByText('workbench.tasks.to_do')).not.toBeInTheDocument();
  });

  it('says a view with nothing in it', async () => {
    nav.search = 'view=upcoming';

    screenOf();

    expect(await screen.findByText('workbench.tasks.view_empty.upcoming')).toBeInTheDocument();
  });

  it('says a read that failed, with a way to try again', async () => {
    nav.search = 'view=today';
    viewAnswer = new Error('unread');

    screenOf();

    expect(await screen.findByText('workbench.tasks.failed')).toBeInTheDocument();
  });

  it('ticks a task in its own list and reads the view again', async () => {
    nav.search = 'view=today';
    viewAnswer = { tasks: [due('d1', '2026-11-05')], truncated: false, failed: [] };
    api.patch.mockResolvedValue(task('d1', { completed: true }));
    const { user } = screenOf();

    await user.click(await screen.findByRole('checkbox', { name: 'workbench.tasks.complete' }));

    await waitFor(() =>
      expect(patched('/workbench/tasks')).toEqual({ list_id: 'l2', task_id: 'd1', completed: true })
    );
    await waitFor(() =>
      expect(
        api.get.mock.calls.filter(([path]) => path === '/workbench/tasks/view').length
      ).toBeGreaterThan(1)
    );
  });

  it('ignores a view nobody named', async () => {
    nav.search = 'view=someday';

    screenOf();

    expect(await screen.findByText('Task t1')).toBeInTheDocument();
  });
});

describe('TasksTool — a list', () => {
  async function menu(user: Awaited<ReturnType<typeof screenOf>>['user']) {
    await user.click(await screen.findByRole('button', { name: 'workbench.tasks.list_actions' }));
  }

  it('is renamed by name, what it was given first', async () => {
    api.patch.mockResolvedValue({ id: 'l1', title: 'House', default: false });
    const { user } = screenOf();
    await screen.findByText('Task t1');
    await menu(user);

    await user.click(await screen.findByRole('menuitem', { name: 'workbench.tasks.rename_list' }));
    const dialog = await screen.findByRole('dialog');
    const field = within(dialog).getByRole('textbox', { name: 'workbench.tasks.new_list_name' });
    expect(field).toHaveValue('Home');
    await user.clear(field);
    await user.type(field, 'House{Enter}');

    await waitFor(() =>
      expect(patched('/workbench/tasks/lists')).toEqual({ list_id: 'l1', title: 'House' })
    );
    expect(
      await within(
        screen.getByRole('navigation', { name: 'workbench.tasks.lists_title' })
      ).findByRole('link', { name: 'House' })
    ).toBeInTheDocument();
  });

  it('lets go of what is done, after a question', async () => {
    api.post.mockResolvedValue({ deleted: 2, remaining: false });
    const { user } = screenOf();
    await screen.findByText('Task t1');
    await menu(user);

    await user.click(
      await screen.findByRole('menuitem', { name: 'workbench.tasks.clear_completed' })
    );
    await answerConfirmDialog(user);

    await waitFor(() =>
      expect(posted('/workbench/tasks/clear-completed')?.[1]).toEqual({ list_id: 'l1' })
    );
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('workbench.tasks.cleared'));
  });

  it('asks nothing of the provider when the person says no', async () => {
    const { user } = screenOf();
    await screen.findByText('Task t1');
    await menu(user);

    await user.click(
      await screen.findByRole('menuitem', { name: 'workbench.tasks.clear_completed' })
    );
    await answerConfirmDialog(user, false);

    expect(api.post).not.toHaveBeenCalled();
  });

  it('says when more done tasks remain than one click takes', async () => {
    api.post.mockResolvedValue({ deleted: 200, remaining: true });
    const { user } = screenOf();
    await screen.findByText('Task t1');
    await menu(user);

    await user.click(
      await screen.findByRole('menuitem', { name: 'workbench.tasks.clear_completed' })
    );
    await answerConfirmDialog(user);

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('workbench.tasks.cleared_more'));
  });
});

describe('TasksTool — a selection', () => {
  async function selecting() {
    const view = screenOf();
    await screen.findByText('Task t1');
    await view.user.click(screen.getByRole('button', { name: 'workbench.tasks.select' }));
    return view;
  }
  const bar = () => screen.getByRole('region', { name: 'workbench.tasks.selection_region' });

  it('asks for it, in place of the ticks that complete', async () => {
    await selecting();

    expect(screen.getAllByRole('checkbox', { name: 'workbench.tasks.select_task' })).toHaveLength(
      2
    );
    expect(
      screen.queryByRole('checkbox', { name: 'workbench.tasks.complete' })
    ).not.toBeInTheDocument();
  });

  it('marks what is ticked done, each answered', async () => {
    api.post.mockResolvedValue({ done: ['t1'], failed: [] });
    const { user } = await selecting();

    await user.click(screen.getAllByRole('checkbox', { name: 'workbench.tasks.select_task' })[0]);
    await user.click(
      within(bar()).getByRole('button', { name: 'workbench.tasks.complete_selection' })
    );

    await waitFor(() =>
      expect(posted('/workbench/tasks/selection/completed')?.[1]).toEqual({
        list_id: 'l1',
        task_ids: ['t1'],
        completed: true,
      })
    );
  });

  it('deletes after a question, and only what went leaves', async () => {
    api.post.mockResolvedValue({ done: ['t1'], failed: [{ id: 't2', status: 'failed' }] });
    const { user } = await selecting();
    const ticks = screen.getAllByRole('checkbox', { name: 'workbench.tasks.select_task' });
    await user.click(ticks[0]);
    await user.click(ticks[1]);

    await user.click(within(bar()).getByRole('button', { name: 'common.delete' }));
    await answerConfirmDialog(user);

    await waitFor(() => expect(screen.queryByText('Task t1')).not.toBeInTheDocument());
    expect(screen.getByText('Task t2')).toBeInTheDocument();
    expect(toast.error).toHaveBeenCalledWith('workbench.tasks.partial');
    expect(screen.getByRole('checkbox', { name: 'workbench.tasks.select_task' })).toBeChecked();
  });

  it('sends what is ticked to another list, which it leaves', async () => {
    api.post.mockResolvedValue({
      done: ['t1'],
      failed: [],
      moved: [{ id: 't1', new_id: 'n1' }],
    });
    const { user } = await selecting();
    await user.click(screen.getAllByRole('checkbox', { name: 'workbench.tasks.select_task' })[0]);

    await user.selectOptions(
      within(bar()).getByRole('combobox', { name: 'workbench.tasks.move_to_list' }),
      'l2'
    );

    await waitFor(() =>
      expect(posted('/workbench/tasks/selection/move')?.[1]).toEqual({
        list_id: 'l1',
        task_ids: ['t1'],
        destination_list_id: 'l2',
      })
    );
    await waitFor(() => expect(screen.queryByText('Task t1')).not.toBeInTheDocument());
  });

  it('says a task left in both lists in its own words', async () => {
    api.post.mockResolvedValue({
      done: [],
      failed: [{ id: 't1', status: 'task_left_behind' }],
      moved: [],
    });
    const { user } = await selecting();
    await user.click(screen.getAllByRole('checkbox', { name: 'workbench.tasks.select_task' })[0]);

    await user.selectOptions(
      within(bar()).getByRole('combobox', { name: 'workbench.tasks.move_to_list' }),
      'l2'
    );

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('workbench.errors.task_left_behind')
    );
  });
});

describe('TasksTool — what the provider keeps', () => {
  const opened = (overrides: Partial<WorkbenchTask> = {}) => {
    nav.search = 'list=l1&task=t1';
    tasksPage = { items: [task('t1', overrides), task('t2')], next_page_token: null };
    return screenOf();
  };

  it("offers To Do's steps and details, never Google's order", async () => {
    features = TO_DO;
    opened();

    expect(await screen.findByLabelText('workbench.tasks.importance')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'workbench.tasks.steps_title' })).toBeDefined();
    expect(
      screen.queryByRole('button', { name: 'workbench.tasks.move_down' })
    ).not.toBeInTheDocument();
  });

  it("offers Google's order, never To Do's details", async () => {
    opened();

    expect(
      await screen.findByRole('button', { name: 'workbench.tasks.move_down' })
    ).toBeInTheDocument();
    expect(screen.queryByLabelText('workbench.tasks.importance')).not.toBeInTheDocument();
  });

  it('sends a task down behind its neighbour', async () => {
    api.post.mockResolvedValue(task('t1'));
    const { user } = opened();

    await user.click(await screen.findByRole('button', { name: 'workbench.tasks.move_down' }));

    await waitFor(() =>
      expect(posted('/workbench/tasks/place')?.[1]).toEqual({
        list_id: 'l1',
        task_id: 't1',
        after: 't2',
      })
    );
  });

  it('keeps the first task where it is when it is asked up', async () => {
    const { user } = opened();

    await user.click(await screen.findByRole('button', { name: 'workbench.tasks.move_up' }));

    expect(api.post).not.toHaveBeenCalled();
  });

  it('adds a step, ticks it and takes it away', async () => {
    features = TO_DO;
    api.post.mockResolvedValue({ id: 's1', title: 'Pack', checked: false });
    api.patch.mockResolvedValue({ id: 's1', title: 'Pack', checked: true });
    api.delete.mockResolvedValue(undefined);
    const { user } = opened();

    await user.type(
      await screen.findByRole('textbox', { name: 'workbench.tasks.new_step' }),
      'Pack{Enter}'
    );
    await waitFor(() =>
      expect(posted('/workbench/tasks/steps')?.[1]).toMatchObject({
        list_id: 'l1',
        task_id: 't1',
        title: 'Pack',
        idempotency_key: expect.any(String),
      })
    );

    const steps = screen.getByRole('region', { name: 'workbench.tasks.steps_title' });
    await user.click(await within(steps).findByRole('checkbox'));
    await waitFor(() =>
      expect(patched('/workbench/tasks/steps')).toEqual({
        list_id: 'l1',
        task_id: 't1',
        step_id: 's1',
        checked: true,
      })
    );

    await user.click(within(steps).getByRole('button', { name: 'workbench.tasks.remove_step' }));
    await waitFor(() => expect(within(steps).queryByRole('checkbox')).not.toBeInTheDocument());
  });

  it('saves an importance as it is picked', async () => {
    features = TO_DO;
    api.patch.mockResolvedValue(task('t1', { importance: 'high' }));
    const { user } = opened({ importance: 'normal' });

    await user.selectOptions(await screen.findByLabelText('workbench.tasks.importance'), 'high');

    await waitFor(() =>
      expect(patched('/workbench/tasks')).toEqual({
        list_id: 'l1',
        task_id: 't1',
        importance: 'high',
      })
    );
  });

  it("writes a reminder on the account's clock", async () => {
    features = TO_DO;
    api.patch.mockResolvedValue(task('t1'));
    opened();

    const field = await screen.findByLabelText('workbench.tasks.reminder');
    fireEvent.change(field, { target: { value: '2027-01-10T10:00' } });
    fireEvent.blur(field);

    await waitFor(() =>
      expect(patched('/workbench/tasks')).toEqual({
        list_id: 'l1',
        task_id: 't1',
        reminder: '2027-01-10T09:00:00.000Z',
      })
    );
  });

  it('takes a reminder off when the field is emptied', async () => {
    features = TO_DO;
    api.patch.mockResolvedValue(task('t1'));
    opened({ reminder: '2027-01-10T09:00:00Z' });

    const field = await screen.findByLabelText('workbench.tasks.reminder');
    fireEvent.change(field, { target: { value: '' } });
    fireEvent.blur(field);

    await waitFor(() =>
      expect(patched('/workbench/tasks')).toEqual({ list_id: 'l1', task_id: 't1', reminder: null })
    );
  });

  it('asks nothing when a reminder was left as it was', async () => {
    features = TO_DO;
    opened({ reminder: '2027-01-10T09:00:00.000Z' });

    fireEvent.blur(await screen.findByLabelText('workbench.tasks.reminder'));

    expect(api.patch).not.toHaveBeenCalled();
  });

  it('waits for a due day before a repetition', async () => {
    features = TO_DO;
    opened();

    expect(await screen.findByLabelText('workbench.tasks.repeat')).toBeDisabled();
    expect(screen.getByText('workbench.tasks.repeat_needs_due')).toBeInTheDocument();
  });

  it('saves a repetition, and takes it off', async () => {
    features = TO_DO;
    api.patch.mockResolvedValue(task('t1', { due: '2027-01-11', repeat: 'weekly' }));
    const { user } = opened({ due: '2027-01-11' });

    const field = await screen.findByLabelText('workbench.tasks.repeat');
    await user.selectOptions(field, 'weekly');
    await waitFor(() =>
      expect(patched('/workbench/tasks')).toEqual({
        list_id: 'l1',
        task_id: 't1',
        repeat: 'weekly',
      })
    );

    await user.selectOptions(field, '');
    await waitFor(() =>
      expect(patched('/workbench/tasks')).toEqual({ list_id: 'l1', task_id: 't1', repeat: null })
    );
  });

  it('names a repetition it cannot say, and leaves it', async () => {
    features = TO_DO;
    opened({ due: '2027-01-11', repeat: 'custom' });

    expect(await screen.findByLabelText('workbench.tasks.repeat')).toHaveValue('custom');
  });

  it('sends a task to another list and closes it', async () => {
    api.post.mockResolvedValue({ done: ['t1'], failed: [], moved: [{ id: 't1', new_id: 't1' }] });
    const { user } = opened();

    await user.selectOptions(
      await screen.findByRole('combobox', { name: 'workbench.tasks.move_to_list' }),
      'l2'
    );

    await waitFor(() =>
      expect(posted('/workbench/tasks/selection/move')?.[1]).toEqual({
        list_id: 'l1',
        task_ids: ['t1'],
        destination_list_id: 'l2',
      })
    );
    await waitFor(() => expect(nav.replace).toHaveBeenCalled());
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
