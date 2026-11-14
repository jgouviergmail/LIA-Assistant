/**
 * The « Tools » tasks screen (ADR-369, Task 6.2): the lists and the tasks of
 * the open one; « Load more » exactly when the provider has more; subtasks
 * under their parent; an empty list names the way out; a completion shows at
 * once and, refused, is rolled back with the refusal's own sentence.
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
import type {
  ViewTasks,
  WorkbenchAvailability,
  WorkbenchFeature,
  WorkbenchTask,
  WorkbenchToolState,
} from '@/lib/workbench/types';

type ShellConfig = Pick<AppConfig, 'capabilities'> & { features: { workbench_enabled?: boolean } };

const { api, nav, toast, media, instance } = vi.hoisted(() => ({
  instance: { assists: false },
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  nav: { search: '', push: vi.fn(), replace: vi.fn() },
  toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }),
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
    config: {
      features: { workbench_enabled: true },
      capabilities: { tool_assists: { enabled: instance.assists, family: 'work' } },
    } satisfies ShellConfig,
    loading: false,
    error: null,
  }),
}));

import { addDays } from '@/lib/workbench/calendar/zoned';
import { handOff, setHandoffOwner } from '@/lib/workbench/handoff';
import { dayIn } from '@/lib/workbench/tasks';

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
      assist_text_max_chars: 8000,
      assist_instruction_max_chars: 500,
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
let viewAnswer: ViewTasks | Error;

beforeEach(() => {
  vi.clearAllMocks();
  nav.replace.mockReset();
  instance.assists = false;
  // A list is on screen unless a test says otherwise: an address naming nothing opens on
  // « All tasks » (owner, 2026-11-10), which the tests of the opening name themselves.
  nav.search = 'list=l1';
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

describe('TasksTool — a sentence LIA reads', () => {
  const FIELD = 'workbench.tasks.new_task';
  const READ = 'workbench.assist.tasks.from_words';
  const ANSWER = {
    task: { title: 'Call the plumber', notes: '', due: '2026-11-06', list_name: 'Trip' },
    usage: { tokens_in: 90, tokens_out: 9, tokens_cache: 0, cost_eur: 0.001, model_name: 'm' },
  };

  beforeEach(() => {
    instance.assists = true;
    api.post.mockImplementation((path: string) =>
      Promise.resolve(path.startsWith('/tool-assists') ? ANSWER : task('t9'))
    );
  });

  it('offers nothing while nothing is typed, and nothing where the instance withholds it', async () => {
    const { user } = screenOf();

    const field = await screen.findByRole('textbox', { name: FIELD });
    expect(screen.queryByRole('button', { name: READ })).toBeNull();
    await user.type(field, 'Call');

    expect(screen.getByRole('button', { name: READ })).toBeInTheDocument();
  });

  it('never offers it on a closed instance', async () => {
    instance.assists = false;
    const { user } = screenOf();

    await user.type(await screen.findByRole('textbox', { name: FIELD }), 'Call');

    expect(screen.queryByRole('button', { name: READ })).toBeNull();
  });

  it('leaves what the person typed while it read', async () => {
    let answer: (value: unknown) => void = () => undefined;
    api.post.mockImplementation((path: string) =>
      path.startsWith('/tool-assists')
        ? new Promise(resolve => {
            answer = resolve;
          })
        : Promise.resolve(task('t9'))
    );
    const { user } = screenOf();
    const field = await screen.findByRole('textbox', { name: FIELD });

    await user.type(field, 'call the plumber');
    await user.click(screen.getByRole('button', { name: READ }));
    await user.type(field, ' today');
    await act(async () => answer(ANSWER));

    expect(field).toHaveValue('call the plumber today');
  });

  it('keeps the title in the field and the day beside it: nothing is added yet', async () => {
    const { user } = screenOf();
    const field = await screen.findByRole('textbox', { name: FIELD });

    await user.type(field, 'call the plumber friday, trip list');
    await user.click(screen.getByRole('button', { name: READ }));

    await waitFor(() => expect(field).toHaveValue('Call the plumber'));
    expect(screen.getByText(/ · Trip/)).toBeInTheDocument();
    expect(api.post.mock.calls.map(([path]) => path)).toEqual(['/tool-assists/tasks/from-words']);
    expect(api.post.mock.calls[0][1]).toEqual({
      sentence: 'call the plumber friday, trip list',
      lists: ['Home', 'Trip'],
    });
  });

  it('adds a task typed by hand to the list on screen', async () => {
    const { user } = screenOf();
    const field = await screen.findByRole('textbox', { name: FIELD });

    await user.type(field, 'Call the plumber');
    await user.click(screen.getByRole('button', { name: 'workbench.tasks.add' }));

    await waitFor(() =>
      expect(posted('/workbench/tasks')?.[1]).toMatchObject({
        title: 'Call the plumber',
        list_id: 'l1',
      })
    );
  });

  it('adds it with its day and in the list it named, once the person presses', async () => {
    const { user } = screenOf();
    const field = await screen.findByRole('textbox', { name: FIELD });

    await user.type(field, 'call the plumber friday');
    await user.click(screen.getByRole('button', { name: READ }));
    await waitFor(() => expect(field).toHaveValue('Call the plumber'));
    await user.click(screen.getByRole('button', { name: 'workbench.tasks.add' }));

    await waitFor(() =>
      expect(posted('/workbench/tasks')?.[1]).toMatchObject({
        title: 'Call the plumber',
        due: '2026-11-06',
        list_id: 'l2',
      })
    );
  });

  it('leaves out what LIA read when the person says so', async () => {
    const { user } = screenOf();
    const field = await screen.findByRole('textbox', { name: FIELD });

    await user.type(field, 'call the plumber friday');
    await user.click(screen.getByRole('button', { name: READ }));
    await user.click(
      await screen.findByRole('button', { name: 'workbench.assist.tasks.drop_read' })
    );
    await user.click(screen.getByRole('button', { name: 'workbench.tasks.add' }));

    await waitFor(() => expect(posted('/workbench/tasks')).toBeDefined());
    expect(posted('/workbench/tasks')?.[1]).not.toHaveProperty('due', '2026-11-06');
  });

  it('tells a refusal and keeps what was typed', async () => {
    api.post.mockRejectedValueOnce(
      new ApiError('no', 422, { detail: { code: 'assist_not_found' } })
    );
    const { user } = screenOf();
    const field = await screen.findByRole('textbox', { name: FIELD });

    await user.type(field, 'hello');
    await user.click(screen.getByRole('button', { name: READ }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('workbench.errors.assist_not_found')
    );
    expect(field).toHaveValue('hello');
  });
});

describe('TasksTool — the steps LIA proposes', () => {
  const STEPS = 'workbench.assist.tasks.steps';
  const ADD = 'workbench.assist.tasks.add_steps';
  const ANSWER = { steps: ['Pack', 'Label'], usage: null };

  async function opened() {
    instance.assists = true;
    nav.search = 'list=l1&task=t1';
    api.post.mockImplementation((path: string) =>
      Promise.resolve(path === '/tool-assists/tasks/steps' ? ANSWER : task('t9'))
    );
    const rendered = screenOf();
    await rendered.user.click(await screen.findByRole('button', { name: 'workbench.ask.label' }));
    return rendered;
  }

  it('reads the task as the form holds it, and adds nothing by itself', async () => {
    const { user } = await opened();

    await user.click(await screen.findByRole('menuitem', { name: STEPS }));

    expect(await screen.findByText('Pack')).toBeInTheDocument();
    expect(posted('/tool-assists/tasks/steps')?.[1]).toEqual({ title: 'Task t1', notes: null });
    expect(api.post.mock.calls.map(([path]) => path)).toEqual(['/tool-assists/tasks/steps']);
  });

  it('adds what it proposed as subtasks, in order, when the person presses', async () => {
    const { user } = await opened();

    await user.click(await screen.findByRole('menuitem', { name: STEPS }));
    await user.click(await screen.findByRole('button', { name: ADD }));

    await waitFor(() =>
      expect(api.post.mock.calls.filter(([path]) => path === '/workbench/tasks')).toHaveLength(2)
    );
    const made = api.post.mock.calls.filter(([path]) => path === '/workbench/tasks');
    expect(made.map(([, body]) => body.title)).toEqual(['Pack', 'Label']);
    expect(made[0][1]).toMatchObject({ parent: 't1' });
    expect(made[0][1].idempotency_key).not.toBe(made[1][1].idempotency_key);
    await waitFor(() => expect(screen.queryByText('Pack')).toBeNull());
  });

  it('goes on from where a refusal stopped it, adding nothing twice', async () => {
    const { user } = await opened();
    let refused = false;
    api.post.mockImplementation((path: string, body: { title?: string }) => {
      if (path === '/tool-assists/tasks/steps') return Promise.resolve(ANSWER);
      if (body.title === 'Label' && !refused) {
        refused = true;
        return Promise.reject(new Error('down'));
      }
      return Promise.resolve(task('t9'));
    });

    await user.click(await screen.findByRole('menuitem', { name: STEPS }));
    await user.click(await screen.findByRole('button', { name: ADD }));
    await waitFor(() => expect(screen.queryByText('Pack')).toBeNull());
    expect(screen.getByText('Label')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: ADD }));

    await waitFor(() => expect(screen.queryByText('Label')).toBeNull());
    const made = api.post.mock.calls.filter(([path]) => path === '/workbench/tasks');
    expect(made.map(([, body]) => body.title)).toEqual(['Pack', 'Label', 'Label']);
    expect(made[1][1].idempotency_key).toBe(made[2][1].idempotency_key);
  });

  it('offers no steps where the task cannot hold any', async () => {
    tasksPage = { items: [task('t1', { parent: 't0' })], next_page_token: null };
    instance.assists = true;
    nav.search = 'list=l1&task=t1';
    const { user } = screenOf();

    await user.click(await screen.findByRole('button', { name: 'workbench.ask.label' }));

    await screen.findByRole('menuitem', { name: 'workbench.assist.remind.line' });
    expect(screen.queryByRole('menuitem', { name: STEPS })).toBeNull();
  });
});

describe('TasksTool — what another tool hands it', () => {
  const HANDED = {
    kind: 'task',
    title: 'Answer Ana',
    notes: 'Ana asks for the budget.\nhttps://lia.example/mail?id=m1',
    due: '2026-11-13',
    list_name: 'trip',
    importance: 'high',
  } as const;

  it('opens a form on everything handed, and adds it to the list LIA named', async () => {
    handOff('owner', HANDED);
    api.post.mockResolvedValue(task('t9'));
    const { user } = screenOf();

    const form = await screen.findByRole('dialog', { name: 'workbench.tasks.new_task' });
    expect(within(form).getByLabelText('workbench.tasks.title')).toHaveValue('Answer Ana');
    expect(within(form).getByLabelText('workbench.tasks.notes')).toHaveValue(HANDED.notes);
    await user.click(within(form).getByRole('button', { name: 'workbench.tasks.add' }));

    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    const body = api.post.mock.calls[0][1];
    expect(body).toMatchObject({
      title: 'Answer Ana',
      notes: HANDED.notes,
      due: '2026-11-13',
      list_id: 'l2',
    });
    expect(body).not.toHaveProperty('importance');
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(toast.success).toHaveBeenCalledWith('workbench.tasks.added_to');
    expect(screen.getByRole('textbox', { name: 'workbench.tasks.new_task' })).toHaveValue('');
  });

  it('keeps what To Do keeps: the importance LIA read', async () => {
    features = TO_DO;
    handOff('owner', { ...HANDED, list_name: null });
    api.post.mockResolvedValue(task('t9'));
    const { user } = screenOf();

    const form = await screen.findByRole('dialog', { name: 'workbench.tasks.new_task' });
    await user.click(within(form).getByRole('button', { name: 'workbench.tasks.add' }));

    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    expect(api.post.mock.calls[0][1]).toMatchObject({ list_id: 'l1', importance: 'high' });
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('arriving on « all tasks », says where it went and reads the view again', async () => {
    // Another tool sends the person to the screen's bare address, which opens on every list:
    // no list is on screen, so the task's list is always said, and its row must appear.
    nav.search = '';
    handOff('owner', { ...HANDED, list_name: null });
    api.post.mockResolvedValue(task('t9'));
    const viewReads = () =>
      api.get.mock.calls.filter(([path]) => path === '/workbench/tasks/view').length;
    const { user } = screenOf();

    const form = await screen.findByRole('dialog', { name: 'workbench.tasks.new_task' });
    const before = viewReads();
    await user.click(within(form).getByRole('button', { name: 'workbench.tasks.add' }));

    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    expect(api.post.mock.calls[0][1]).toMatchObject({ title: 'Answer Ana', list_id: 'l1' });
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('workbench.tasks.added_to'));
    await waitFor(() => expect(viewReads()).toBeGreaterThan(before));
  });

  it('makes nothing when the person cancels', async () => {
    handOff('owner', HANDED);
    const { user } = screenOf();

    const form = await screen.findByRole('dialog', { name: 'workbench.tasks.new_task' });
    await user.click(within(form).getByRole('button', { name: 'common.cancel' }));

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(api.post).not.toHaveBeenCalled();
  });
});

describe('TasksTool', () => {
  it('opens on « all tasks » when the address names nothing', async () => {
    nav.search = '';
    viewAnswer = {
      tasks: [{ id: 'd1', list_id: 'l2', title: 'Due d1', due: null }],
      truncated: false,
      failed: [],
    };

    screenOf();

    expect(await screen.findByText('Due d1')).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('/workbench/tasks/view', {
      params: { view: 'all' },
      signal: expect.any(AbortSignal),
    });
    const lists = screen.getByRole('navigation', { name: 'workbench.tasks.lists_title' });
    expect(within(lists).getByRole('link', { name: 'workbench.tasks.views.all' })).toHaveAttribute(
      'aria-current',
      'page'
    );
    // The default list is where a new task goes, not where the screen starts: it is not read.
    expect(api.get.mock.calls.filter(([path]) => path === '/workbench/tasks')).toEqual([]);
  });

  it('opens the list the address names and shows its tasks', async () => {
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

  it('looks for a task named alone in the list the settings chose', async () => {
    // Nothing says where else it lives: the one case the default list is still read for.
    defaultList = 'l2';
    nav.search = 'task=t1';
    screenOf();

    await screen.findByText('Task t1');
    expect(api.get).toHaveBeenCalledWith('/workbench/tasks', {
      params: { list_id: 'l2', show_completed: false },
      signal: expect.any(AbortSignal),
    });
    // That list is the place on screen, not « all tasks » with the task beside it.
    const lists = screen.getByRole('navigation', { name: 'workbench.tasks.lists_title' });
    expect(within(lists).getByRole('link', { name: 'Trip' })).toHaveAttribute(
      'aria-current',
      'page'
    );
    expect(api.get.mock.calls.filter(([path]) => path === '/workbench/tasks/view')).toEqual([]);
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

    const back = await screen.findByRole('button', { name: 'workbench.tools.tasks.label' });
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

  it('opens on « all tasks » for a view nobody named', async () => {
    nav.search = 'view=someday';

    screenOf();

    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/workbench/tasks/view', {
        params: { view: 'all' },
        signal: expect.any(AbortSignal),
      })
    );
    expect(screen.queryByText('Task t1')).toBeNull();
  });
});

describe('TasksTool — every list together (2026-11-10)', () => {
  const pane = () => screen.findByRole('navigation', { name: 'workbench.tasks.lists_title' });
  const viewReads = () =>
    api.get.mock.calls.filter(([path]) => path === '/workbench/tasks/view').length;
  /** A day of the account's calendar, counted from its today. */
  const day = (offset: number) => addDays(dayIn('Europe/Paris', new Date()), offset);
  const row = (id: string, list: string, dueDay: string | null) => ({
    id,
    list_id: list,
    title: `Due ${id}`,
    due: dueDay,
  });
  const whole = (...tasks: ReturnType<typeof row>[]): ViewTasks => ({
    tasks,
    truncated: false,
    failed: [],
  });
  const addressOf = (href: string | null | undefined) =>
    Object.fromEntries(new URL(href ?? '', 'http://lia.test').searchParams);
  const stretch = (part: string) =>
    screen.getByRole('region', { name: new RegExp(`workbench\\.tasks\\.views\\.${part}`) });

  it('heads the views with the three together, and the lists with « all tasks »', async () => {
    screenOf();

    const lists = await pane();
    await within(lists).findByRole('link', { name: 'Trip' });
    expect(
      within(lists)
        .getAllByRole('link')
        .map(link => link.textContent)
    ).toEqual([
      'workbench.tasks.views.timeline',
      'workbench.tasks.views.today',
      'workbench.tasks.views.overdue',
      'workbench.tasks.views.upcoming',
      'workbench.tasks.views.all',
      'Home',
      'Trip',
    ]);
    expect(
      addressOf(
        within(lists)
          .getByRole('link', { name: 'workbench.tasks.views.timeline' })
          .getAttribute('href')
      )
    ).toEqual({ view: 'timeline' });
    expect(
      addressOf(
        within(lists).getByRole('link', { name: 'workbench.tasks.views.all' }).getAttribute('href')
      )
    ).toEqual({ view: 'all' });
  });

  it('marks « all tasks » as the open place among the lists, and reads it', async () => {
    nav.search = 'view=all';

    screenOf();

    const lists = await pane();
    expect(within(lists).getByRole('link', { name: 'workbench.tasks.views.all' })).toHaveAttribute(
      'aria-current',
      'page'
    );
    expect(await within(lists).findByRole('link', { name: 'Home' })).not.toHaveAttribute(
      'aria-current'
    );
    expect(api.get).toHaveBeenCalledWith(
      '/workbench/tasks/view',
      expect.objectContaining({ params: { view: 'all' } })
    );
    expect(api.get).not.toHaveBeenCalledWith('/workbench/tasks', expect.anything());
  });

  it('shows every open task with its list in a badge, the undated without a day', async () => {
    nav.search = 'view=all';
    viewAnswer = whole(row('d1', 'l2', day(-1)), row('d2', 'l1', null));

    screenOf();

    const dated = await screen.findByRole('link', { name: /Due d1/ });
    const undated = screen.getByRole('link', { name: /Due d2/ });
    // The badge names what it is to a screen reader, before the list's own name.
    expect(within(dated).getByTitle('Trip')).toHaveTextContent('workbench.tasks.list_label Trip');
    expect(within(undated).getByTitle('Home')).toHaveTextContent('workbench.tasks.list_label Home');
    // A late day SAYS it is late; a task without a day carries no chip at all.
    expect(within(dated).getByText('workbench.tasks.overdue')).toBeInTheDocument();
    expect(undated).not.toHaveTextContent(/workbench\.tasks\.(today|overdue)/);
    expect(undated.textContent).toBe('Due d2workbench.tasks.list_label Home');
    expect(screen.getByText('workbench.tasks.to_do')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { level: 3 })).toBeNull();
  });

  it('draws a task whose list was not read without a badge, never with a wrong one', async () => {
    nav.search = 'view=all';
    viewAnswer = whole(row('d1', 'elsewhere', null));

    screenOf();

    const link = await screen.findByRole('link', { name: /Due d1/ });
    expect(link).not.toHaveTextContent('workbench.tasks.list_label');
  });

  it('reads today’s as today in every view, in the warning that a list’s row gives it', async () => {
    nav.search = 'view=today';
    viewAnswer = whole(row('d1', 'l2', day(0)));

    screenOf();

    const link = await screen.findByRole('link', { name: /Due d1/ });
    expect(within(link).getByText('workbench.tasks.today')).toBeInTheDocument();
  });

  it('cuts the timeline into what is late, today and the days ahead, each counted', async () => {
    nav.search = 'view=timeline';
    viewAnswer = whole(
      row('late', 'l1', day(-3)),
      row('now', 'l2', day(0)),
      row('soon', 'l1', day(2)),
      row('next', 'l2', day(5))
    );

    screenOf();

    await screen.findByText('Due late');
    expect(
      screen.getAllByRole('heading', { level: 3 }).map(heading => heading.textContent)
    ).toEqual([
      expect.stringContaining('workbench.tasks.views.overdue'),
      expect.stringContaining('workbench.tasks.views.today'),
      expect.stringContaining('workbench.tasks.views.upcoming'),
    ]);
    const named = (part: string) =>
      within(stretch(part))
        .getAllByRole('link')
        .map(link => link.getAttribute('href'))
        .map(href => addressOf(href).task);
    expect(named('overdue')).toEqual(['late']);
    expect(named('today')).toEqual(['now']);
    expect(named('upcoming')).toEqual(['soon', 'next']);
    // The whole, then each stretch: every figure is of what is on screen, read whole.
    expect(screen.getAllByText('workbench.tasks.to_do')).toHaveLength(4);
    expect(within(stretch('today')).getByTitle('Trip')).toBeInTheDocument();
  });

  it('draws no stretch that holds nothing, and counts none when a list is unread', async () => {
    nav.search = 'view=timeline';
    viewAnswer = { tasks: [row('now', 'l2', day(0))], truncated: false, failed: ['l1'] };

    screenOf();

    await screen.findByText('Due now');
    expect(screen.getAllByRole('heading', { level: 3 })).toHaveLength(1);
    expect(screen.queryByText('workbench.tasks.to_do')).not.toBeInTheDocument();
    expect(screen.getByText('workbench.tasks.view_partial')).toBeInTheDocument();
  });

  it.each(['timeline', 'all'])('says a « %s » with nothing in it', async view => {
    nav.search = `view=${view}`;

    screenOf();

    expect(await screen.findByText(`workbench.tasks.view_empty.${view}`)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { level: 3 })).toBeNull();
  });

  it('opens a task beside the view: the address keeps the view and names its list', async () => {
    nav.search = 'view=all';
    viewAnswer = whole(row('d1', 'l2', null));

    screenOf();

    const link = await screen.findByRole('link', { name: /Due d1/ });
    expect(addressOf(link.getAttribute('href'))).toEqual({ view: 'all', list: 'l2', task: 'd1' });
  });

  it('keeps the view on screen beside the open task, read in its own list', async () => {
    nav.search = 'view=all&list=l2&task=d1';
    viewAnswer = whole(row('d1', 'l2', null), row('d2', 'l1', null));
    tasksPage = { items: [task('d1', { title: 'Due d1' })], next_page_token: null };

    screenOf();

    const detail = await screen.findByRole('complementary', {
      name: 'workbench.tasks.detail_title',
    });
    expect(within(detail).getByDisplayValue('Due d1')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'workbench.tasks.views.all' })).toBeInTheDocument();
    expect(await screen.findByRole('link', { name: /Due d1/ })).toHaveAttribute(
      'aria-current',
      'true'
    );
    expect(screen.getByRole('link', { name: /Due d2/ })).not.toHaveAttribute('aria-current');
    expect(api.get).toHaveBeenCalledWith(
      '/workbench/tasks',
      expect.objectContaining({ params: { list_id: 'l2', show_completed: false } })
    );
    // The list's own rows never stand in the view's place.
    expect(screen.queryByRole('textbox', { name: 'workbench.tasks.new_task' })).toBeNull();
  });

  it('marks the open task by its list too: a namesake of another list is not it', async () => {
    nav.search = 'view=all&list=l2&task=d1';
    viewAnswer = whole(row('d1', 'l1', null), row('d1', 'l2', null));
    tasksPage = { items: [task('d1')], next_page_token: null };

    screenOf();

    await screen.findByRole('complementary', { name: 'workbench.tasks.detail_title' });
    const marked = (await screen.findAllByRole('link', { name: /Due d1/ })).filter(
      link => link.getAttribute('aria-current') === 'true'
    );
    expect(marked.map(link => addressOf(link.getAttribute('href')).list)).toEqual(['l2']);
  });

  it('comes back to the view when the detail closes, not to the task’s list', async () => {
    nav.search = 'view=timeline&list=l2&task=d1';
    viewAnswer = whole(row('d1', 'l2', day(0)));
    tasksPage = { items: [task('d1')], next_page_token: null };
    const { user } = screenOf();

    await user.click(await screen.findByRole('button', { name: 'workbench.tasks.close_detail' }));

    expect(addressOf(nav.replace.mock.calls.at(-1)?.[0])).toEqual({ view: 'timeline' });
  });

  it('gives the focus back to the task’s row in the view when its detail closes', async () => {
    nav.search = 'view=all&list=l2&task=d1';
    viewAnswer = whole(row('d1', 'l2', null));
    tasksPage = { items: [task('d1')], next_page_token: null };
    const { rerender } = screenOf();
    await screen.findByRole('complementary', { name: 'workbench.tasks.detail_title' });
    await screen.findByRole('link', { name: /Due d1/ });

    nav.search = 'view=all';
    rerender(tool());

    await waitFor(() => expect(screen.getByRole('link', { name: /Due d1/ })).toHaveFocus());
  });

  it('gives it to the view’s title when the task left the view', async () => {
    nav.search = 'view=all&list=l2&task=d1';
    viewAnswer = whole(row('d2', 'l1', null));
    tasksPage = { items: [task('d1')], next_page_token: null };
    const { rerender } = screenOf();
    await screen.findByRole('complementary', { name: 'workbench.tasks.detail_title' });
    await screen.findByRole('link', { name: /Due d2/ });

    nav.search = 'view=all';
    rerender(tool());

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'workbench.tasks.views.all' })).toHaveFocus()
    );
  });

  it('reads the view again once the detail changed what a row shows', async () => {
    nav.search = 'view=all&list=l2&task=d1';
    viewAnswer = whole(row('d1', 'l2', null));
    tasksPage = { items: [task('d1', { title: 'Due d1' })], next_page_token: null };
    api.patch.mockResolvedValue(task('d1', { title: 'Renamed' }));
    const { user } = screenOf();
    const title = await screen.findByLabelText('workbench.tasks.title');
    await screen.findByRole('link', { name: /Due d1/ });
    const before = viewReads();

    await user.clear(title);
    await user.type(title, 'Renamed');
    await user.click(screen.getByRole('button', { name: 'common.save' }));

    await waitFor(() =>
      expect(patched('/workbench/tasks')).toEqual({
        list_id: 'l2',
        task_id: 'd1',
        title: 'Renamed',
      })
    );
    await waitFor(() => expect(viewReads()).toBe(before + 1));
  });

  it('reads nothing again for a change no row shows', async () => {
    features = TO_DO;
    nav.search = 'view=all&list=l2&task=d1';
    viewAnswer = whole(row('d1', 'l2', null));
    tasksPage = { items: [task('d1', { importance: 'normal' })], next_page_token: null };
    api.patch.mockResolvedValue(task('d1', { importance: 'high' }));
    const { user } = screenOf();
    await screen.findByRole('link', { name: /Due d1/ });
    const before = viewReads();

    await user.selectOptions(await screen.findByLabelText('workbench.tasks.importance'), 'high');

    await waitFor(() =>
      expect(patched('/workbench/tasks')).toEqual({
        list_id: 'l2',
        task_id: 'd1',
        importance: 'high',
      })
    );
    expect(await screen.findByLabelText('workbench.tasks.importance')).toHaveValue('high');
    expect(viewReads()).toBe(before);
  });

  it('leaves the view as it is when the change was refused', async () => {
    nav.search = 'view=all&list=l2&task=d1';
    viewAnswer = whole(row('d1', 'l2', null));
    tasksPage = { items: [task('d1', { title: 'Due d1' })], next_page_token: null };
    api.patch.mockRejectedValue(
      new ApiError('refused', 502, { detail: { code: 'provider_unavailable' } })
    );
    const { user } = screenOf();
    const title = await screen.findByLabelText('workbench.tasks.title');
    await screen.findByRole('link', { name: /Due d1/ });
    const before = viewReads();

    await user.type(title, ' again');
    await user.click(screen.getByRole('button', { name: 'common.save' }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('workbench.errors.provider_unavailable')
    );
    expect(viewReads()).toBe(before);
  });

  it('ticking in the view the task open beside it shows it done in its detail too', async () => {
    nav.search = 'view=all&list=l2&task=d1';
    viewAnswer = whole(row('d1', 'l2', null));
    tasksPage = { items: [task('d1', { title: 'Due d1' })], next_page_token: null };
    api.patch.mockResolvedValue(task('d1', { title: 'Due d1', completed: true }));
    const { user } = screenOf();
    const detail = await screen.findByRole('complementary', {
      name: 'workbench.tasks.detail_title',
    });
    const link = await screen.findByRole('link', { name: /Due d1/ });
    expect(
      within(detail).getByRole('button', { name: 'workbench.tasks.mark_done' })
    ).toBeInTheDocument();

    await user.click(
      within(link.closest('li')!).getByRole('checkbox', { name: 'workbench.tasks.complete' })
    );

    expect(
      await within(detail).findByRole('button', { name: 'workbench.tasks.reopen_action' })
    ).toBeInTheDocument();
    expect(patched('/workbench/tasks')).toEqual({ list_id: 'l2', task_id: 'd1', completed: true });
  });

  it('ticking a task of another list leaves the open task’s detail as it is', async () => {
    nav.search = 'view=all&list=l2&task=d1';
    viewAnswer = whole(row('d1', 'l2', null), row('d1', 'l1', null));
    tasksPage = { items: [task('d1', { title: 'Due d1' })], next_page_token: null };
    api.patch.mockResolvedValue(task('d1', { title: 'Due d1', completed: true }));
    const { user } = screenOf();
    const detail = await screen.findByRole('complementary', {
      name: 'workbench.tasks.detail_title',
    });
    const namesake = (await screen.findAllByRole('link', { name: /Due d1/ })).find(link =>
      link.getAttribute('href')?.includes('list=l1')
    )!;
    const before = viewReads();

    await user.click(
      within(namesake.closest('li')!).getByRole('checkbox', { name: 'workbench.tasks.complete' })
    );

    await waitFor(() => expect(viewReads()).toBe(before + 1));
    expect(patched('/workbench/tasks')).toEqual({ list_id: 'l1', task_id: 'd1', completed: true });
    expect(
      within(detail).getByRole('button', { name: 'workbench.tasks.mark_done' })
    ).toBeInTheDocument();
  });

  it('below lg, names both in the select: the three together a view, « all tasks » a list', async () => {
    media.desktop = false;
    const { user } = screenOf();

    const select = await screen.findByRole('combobox', { name: 'workbench.tasks.list_label' });
    await within(select).findByRole('option', { name: 'Trip' });
    const group = (name: string) =>
      within(within(select).getByRole('group', { name }))
        .getAllByRole('option')
        .map(option => option.textContent);
    expect(group('workbench.tasks.views_title')).toEqual([
      'workbench.tasks.views.timeline',
      'workbench.tasks.views.today',
      'workbench.tasks.views.overdue',
      'workbench.tasks.views.upcoming',
    ]);
    expect(group('workbench.tasks.lists_title')).toEqual([
      'workbench.tasks.views.all',
      'Home',
      'Trip',
    ]);

    await user.selectOptions(select, 'workbench.tasks.views.all');
    expect(addressOf(nav.replace.mock.calls.at(-1)?.[0])).toEqual({ view: 'all' });
    await user.selectOptions(select, 'workbench.tasks.views.timeline');
    expect(addressOf(nav.replace.mock.calls.at(-1)?.[0])).toEqual({ view: 'timeline' });
  });

  it('below lg, shows the select on the view it is on', async () => {
    media.desktop = false;
    nav.search = 'view=all';

    screenOf();

    const select = await screen.findByRole('combobox', { name: 'workbench.tasks.list_label' });
    expect(
      within(select).getByRole<HTMLOptionElement>('option', { name: 'workbench.tasks.views.all' })
        .selected
    ).toBe(true);
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
  /** Sends what is ticked to a list, from « … », by the keyboard (jsdom lays no pointer path). */
  async function sendTo(user: Awaited<ReturnType<typeof selecting>>['user'], list: string) {
    await user.click(within(bar()).getByRole('button', { name: 'common.more_actions' }));
    (await screen.findByRole('menuitem', { name: 'workbench.tasks.move_to_list' })).focus();
    await user.keyboard('{ArrowRight}');
    (await screen.findByRole('menuitem', { name: list })).focus();
    await user.keyboard('{Enter}');
  }

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

    await sendTo(user, 'Trip');

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

    await sendTo(user, 'Trip');

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
    await nav.replace.withImplementation(
      (href: string) => {
        // Closing the detail must update the URL that useSearchParams reads.
        nav.search = new URL(href, window.location.origin).searchParams.toString();
      },
      async () => {
        api.post.mockResolvedValue({
          done: ['t1'],
          failed: [],
          moved: [{ id: 't1', new_id: 't1' }],
        });
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
        await waitFor(() =>
          expect(nav.replace).toHaveBeenCalledWith('/en/dashboard/tools/tasks?list=l1', {
            scroll: false,
          })
        );
        expect(
          screen.queryByRole('complementary', { name: 'workbench.tasks.detail_title' })
        ).not.toBeInTheDocument();
        expect(screen.queryByRole('link', { name: /Task t1/ })).not.toBeInTheDocument();
        expect(screen.getByRole('link', { name: /Task t2/ })).toBeInTheDocument();
        expect(api.get).not.toHaveBeenCalledWith('/workbench/tasks/task', expect.anything());
      }
    );
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

describe('TasksTool — a task the home opens (2026-11-07)', () => {
  /** The list read as usual; the one task its first page does not hold, read alone. */
  function aloneAnswers(answer: () => Promise<unknown>) {
    const listed = api.get.getMockImplementation()!;
    api.get.mockImplementation((path: string, options?: unknown) =>
      path === '/workbench/tasks/task' ? answer() : listed(path, options)
    );
  }

  it('opens a task its list’s first page does not hold, and an act reaches it', async () => {
    nav.search = 'list=l1&task=t9';
    aloneAnswers(() => Promise.resolve(task('t9', { title: 'Pay rent' })));
    api.patch.mockResolvedValue(task('t9', { title: 'Pay rent', completed: true }));
    const { user } = screenOf();

    const detail = await screen.findByRole('complementary', {
      name: 'workbench.tasks.detail_title',
    });
    expect(within(detail).getByDisplayValue('Pay rent')).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith(
      '/workbench/tasks/task',
      expect.objectContaining({ params: { list_id: 'l1', task_id: 't9' } })
    );
    // Kept with the list's own tasks: done from its row like any other.
    const row = screen.getByRole('link', { name: /Pay rent/ }).closest('li')!;
    await user.click(within(row).getByRole('checkbox', { name: 'workbench.tasks.complete' }));
    await waitFor(() =>
      expect(patched('/workbench/tasks')).toEqual({ list_id: 'l1', task_id: 't9', completed: true })
    );
  });

  it('says a task that is gone, and opens nothing', async () => {
    nav.search = 'list=l1&task=gone';
    aloneAnswers(() =>
      Promise.reject(new ApiError('gone', 404, { detail: { code: 'item_gone' } }))
    );
    screenOf();

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('workbench.errors.item_gone'));
    expect(
      screen.queryByRole('complementary', { name: 'workbench.tasks.detail_title' })
    ).toBeNull();
  });

  it('reads nothing alone for a task the page holds', async () => {
    nav.search = 'list=l1&task=t1';
    screenOf();

    await screen.findByRole('complementary', { name: 'workbench.tasks.detail_title' });
    expect(api.get).not.toHaveBeenCalledWith('/workbench/tasks/task', expect.anything());
  });
});

beforeEach(() => {
  setHandoffOwner(null);
  setHandoffOwner('owner');
});

afterEach(() => setHandoffOwner(null));
