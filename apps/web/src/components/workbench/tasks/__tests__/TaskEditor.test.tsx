/**
 * One task edited by hand (ADR-369): only what changed is sent, a title is
 * required, emptying the due date removes it, a refusal keeps what was typed,
 * deleting asks first, and where the provider has subtasks a top-level task
 * lists them, ticks them and takes a new one.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  answerConfirmDialog,
  fireEvent,
  renderWithProviders,
  screen,
  waitFor,
  within,
} from '@/__tests__/test-utils';
import type { WorkbenchFeature, WorkbenchTask } from '@/lib/workbench/types';

const { width } = vi.hoisted(() => ({ width: { desktop: false } }));
vi.mock('@/hooks/useMediaQuery', () => ({ useMediaQuery: () => width.desktop }));

import { TaskEditor } from '../TaskEditor';

const TASK: WorkbenchTask = {
  id: 't1',
  title: 'Buy milk',
  notes: null,
  completed: false,
  due: '2026-11-03',
  parent: null,
  position: null,
  steps: [],
  importance: null,
  reminder: null,
  repeat: null,
};

describe('the links of its notes', () => {
  it('can be followed, though the notes stay a text area', async () => {
    editor({ task: { ...TASK, notes: 'Compare on https://shop.example.org/milk first.' } });

    const link = screen.getByRole('link', { name: 'https://shop.example.org/milk' });

    expect(link).toHaveAttribute('href', 'https://shop.example.org/milk');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('follow what is typed', () => {
    editor();
    expect(screen.queryByRole('list', { name: 'workbench.tasks.notes_links' })).toBeNull();

    fireEvent.change(screen.getByLabelText('workbench.tasks.notes'), {
      target: { value: 'www.example.org' },
    });

    expect(screen.getByRole('link', { name: 'www.example.org' })).toHaveAttribute(
      'href',
      'https://www.example.org/'
    );
  });
});

function editor({
  task = TASK,
  subtasks = [],
  features = ['subtasks'],
  pending = new Set<string>(),
  focusOnOpen = false,
  today = '2026-11-04',
}: {
  task?: WorkbenchTask;
  subtasks?: WorkbenchTask[];
  features?: WorkbenchFeature[];
  pending?: Set<string>;
  focusOnOpen?: boolean;
  today?: string;
} = {}) {
  const props = {
    onSave: vi.fn().mockResolvedValue(undefined),
    onToggle: vi.fn(),
    onDelete: vi.fn().mockResolvedValue(undefined),
    onAddSubtask: vi.fn().mockResolvedValue(undefined),
    onClose: vi.fn(),
    onAsk: vi.fn(),
  };
  const rendered = renderWithProviders(
    <TaskEditor
      lng="en"
      task={task}
      subtasks={subtasks}
      tool={{
        tool: 'tasks',
        state: 'ready',
        provider: 'google_tasks',
        features,
        bounds: { title_max_chars: 1024, notes_max_chars: 8192 },
      }}
      pending={pending}
      focusOnOpen={focusOnOpen}
      today={today}
      {...props}
    />
  );
  return { ...rendered, ...props };
}

const save = () => screen.getByRole('button', { name: 'common.save' });

describe('TaskEditor — editing', () => {
  it('draws the way back on a finished task, never the tick', () => {
    editor({ task: { ...TASK, completed: true } });

    const act = screen.getByRole('button', { name: 'workbench.tasks.reopen_action' });

    expect(act.querySelector('.lucide-rotate-ccw')).not.toBeNull();
    expect(act.querySelector('.lucide-check')).toBeNull();
  });

  it('sends only what changed, the title trimmed', async () => {
    const { user, onSave } = editor();
    const title = screen.getByLabelText('workbench.tasks.title');

    await user.clear(title);
    await user.type(title, '  Buy oat milk  ');
    await user.click(save());

    expect(onSave).toHaveBeenCalledWith(TASK, { title: 'Buy oat milk' });
  });

  it('removes the due date when it is emptied, and writes notes as typed', async () => {
    const { user, onSave } = editor();

    fireEvent.change(screen.getByLabelText('workbench.tasks.due'), { target: { value: '' } });
    await user.type(screen.getByLabelText('workbench.tasks.notes'), 'oat, not cow');
    await user.click(save());

    expect(onSave).toHaveBeenCalledWith(TASK, { due: null, notes: 'oat, not cow' });
  });

  it('sends nothing when nothing changed, or when only the spaces around the title did', async () => {
    const { user, onSave } = editor();

    await user.click(save());
    await user.type(screen.getByLabelText('workbench.tasks.title'), '   ');
    await user.click(save());

    expect(onSave).not.toHaveBeenCalled();
  });

  it('requires a title, saying so, and sends nothing without one', async () => {
    const { user, onSave } = editor();

    await user.clear(screen.getByLabelText('workbench.tasks.title'));
    expect(screen.getByText('workbench.tasks.title_required')).toBeInTheDocument();
    await user.click(save());

    expect(onSave).not.toHaveBeenCalled();
  });

  it('saves once at a time, and keeps what was typed when refused', async () => {
    let refuse: (reason: Error) => void = () => undefined;
    const { user, onSave } = editor();
    onSave.mockImplementationOnce(() => new Promise<void>((_, reject) => (refuse = reject)));
    const notes = screen.getByLabelText('workbench.tasks.notes');

    await user.type(notes, 'oat');
    await user.click(save());
    fireEvent.submit(notes.closest('form') as HTMLFormElement);
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(save()).toHaveAttribute('aria-busy', 'true');
    refuse(new Error('refused'));

    await waitFor(() => expect(save()).not.toHaveAttribute('aria-busy'));
    expect(notes).toHaveValue('oat');
    await user.click(save());
    expect(onSave).toHaveBeenCalledTimes(2);
  });

  it('says a provider keeps a day without a time, only where it does', () => {
    const dated = editor({ features: ['due_date_only'] });
    expect(screen.getByText('workbench.tasks.due_date_only')).toBeInTheDocument();
    dated.unmount();

    editor({ features: [] });
    expect(screen.queryByText('workbench.tasks.due_date_only')).toBeNull();
  });
});

describe('TaskEditor — saved as it is written', () => {
  it('saves a field when the person leaves it', async () => {
    const { onSave } = editor();

    const title = screen.getByLabelText('workbench.tasks.title');
    fireEvent.change(title, { target: { value: 'Buy oat milk' } });
    fireEvent.blur(title);

    await waitFor(() => expect(onSave).toHaveBeenCalledWith(TASK, { title: 'Buy oat milk' }));
    expect(await screen.findByText('workbench.tasks.saved')).toBeInTheDocument();
  });

  it('saves nothing when nothing changed', () => {
    const { onSave } = editor();

    fireEvent.blur(screen.getByLabelText('workbench.tasks.title'));

    expect(onSave).not.toHaveBeenCalled();
  });

  it('never saves a task left without a title', () => {
    const { onSave } = editor();

    const title = screen.getByLabelText('workbench.tasks.title');
    fireEvent.change(title, { target: { value: '   ' } });
    fireEvent.blur(title);

    expect(onSave).not.toHaveBeenCalled();
  });

  it('puts back a title restored while the new one is on its way', async () => {
    let answer: () => void = () => undefined;
    const { onSave } = editor();
    onSave.mockImplementationOnce(() => new Promise<void>(resolve => (answer = resolve)));
    const title = screen.getByLabelText('workbench.tasks.title');

    fireEvent.change(title, { target: { value: 'Buy oat milk' } });
    fireEvent.blur(title);
    fireEvent.change(title, { target: { value: 'Buy milk' } });
    fireEvent.blur(title);
    expect(onSave).toHaveBeenCalledTimes(1);
    answer();

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(2));
    expect(onSave).toHaveBeenLastCalledWith(TASK, { title: 'Buy milk' });
  });

  it('measures a change against what it saved, however late the list follows', async () => {
    const { onSave } = editor();
    const title = screen.getByLabelText('workbench.tasks.title');

    fireEvent.change(title, { target: { value: 'Buy oat milk' } });
    fireEvent.blur(title);
    await screen.findByText('workbench.tasks.saved');
    fireEvent.blur(title);

    expect(onSave).toHaveBeenCalledTimes(1);
  });

  it('never asks again by itself for what was just refused', async () => {
    let refuse: (reason: Error) => void = () => undefined;
    const { onSave } = editor();
    onSave.mockImplementationOnce(() => new Promise<void>((_, reject) => (refuse = reject)));
    const title = screen.getByLabelText('workbench.tasks.title');

    fireEvent.change(title, { target: { value: 'Buy oat milk' } });
    fireEvent.blur(title);
    fireEvent.click(save());
    refuse(new Error('refused'));

    await waitFor(() => expect(save()).not.toHaveAttribute('aria-busy'));
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(title).toHaveValue('Buy oat milk');
  });

  it('sends what a refusal left, with what was written behind it', async () => {
    let refuse: (reason: Error) => void = () => undefined;
    const { onSave } = editor();
    onSave.mockImplementationOnce(() => new Promise<void>((_, reject) => (refuse = reject)));
    const title = screen.getByLabelText('workbench.tasks.title');
    const notes = screen.getByLabelText('workbench.tasks.notes');

    fireEvent.change(title, { target: { value: 'Buy oat milk' } });
    fireEvent.blur(title);
    fireEvent.change(notes, { target: { value: 'the blue one' } });
    fireEvent.blur(notes);
    refuse(new Error('refused'));

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(2));
    expect(onSave).toHaveBeenLastCalledWith(TASK, {
      title: 'Buy oat milk',
      notes: 'the blue one',
    });
  });

  it('sends nothing when what was refused is undone', async () => {
    let refuse: (reason: Error) => void = () => undefined;
    const { onSave } = editor();
    onSave.mockImplementationOnce(() => new Promise<void>((_, reject) => (refuse = reject)));
    const title = screen.getByLabelText('workbench.tasks.title');

    fireEvent.change(title, { target: { value: 'Buy oat milk' } });
    fireEvent.blur(title);
    fireEvent.change(title, { target: { value: 'Buy milk' } });
    fireEvent.blur(title);
    refuse(new Error('refused'));

    await waitFor(() => expect(save()).not.toHaveAttribute('aria-busy'));
    expect(onSave).toHaveBeenCalledTimes(1);
  });
});

describe('TaskEditor — due dates at hand', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-11-04T10:00:00Z'));
  });
  afterEach(() => vi.useRealTimers());

  it('sets today, tomorrow and next week from the account’s day, and saves it', async () => {
    const { onSave } = editor({ today: '2026-11-04' });

    fireEvent.click(screen.getByRole('button', { name: 'workbench.tasks.due_tomorrow' }));

    expect(screen.getByLabelText('workbench.tasks.due')).toHaveValue('2026-11-05');
    await waitFor(() => expect(onSave).toHaveBeenCalledWith(TASK, { due: '2026-11-05' }));
  });

  it('saves a date pressed while the last change is on its way', async () => {
    let answer: () => void = () => undefined;
    const { onSave } = editor({ today: '2026-11-04' });
    onSave.mockImplementationOnce(() => new Promise<void>(resolve => (answer = resolve)));
    const title = screen.getByLabelText('workbench.tasks.title');

    fireEvent.change(title, { target: { value: 'Buy oat milk' } });
    fireEvent.blur(title);
    fireEvent.click(screen.getByRole('button', { name: 'workbench.tasks.due_tomorrow' }));
    expect(onSave).toHaveBeenCalledTimes(1);
    answer();

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(2));
    expect(onSave).toHaveBeenLastCalledWith(TASK, { due: '2026-11-05' });
  });

  it('asks once for one gesture: leaving a field by pressing « Save »', async () => {
    let answer: () => void = () => undefined;
    const { onSave } = editor({ today: '2026-11-04' });
    onSave.mockImplementationOnce(() => new Promise<void>(resolve => (answer = resolve)));
    const title = screen.getByLabelText('workbench.tasks.title');

    fireEvent.change(title, { target: { value: 'Buy oat milk' } });
    fireEvent.blur(title);
    fireEvent.click(save());
    answer();

    await waitFor(() => expect(screen.getByText('workbench.tasks.saved')).toBeInTheDocument());
    expect(onSave).toHaveBeenCalledTimes(1);
  });

  it('takes the date away', async () => {
    const { onSave } = editor({ today: '2026-11-04' });

    fireEvent.click(screen.getByRole('button', { name: 'workbench.tasks.due_none' }));

    await waitFor(() => expect(onSave).toHaveBeenCalledWith(TASK, { due: null }));
  });

  it('takes back a date undone while it is on its way', async () => {
    let answer: () => void = () => undefined;
    const undated = { ...TASK, due: null };
    const { onSave } = editor({ task: undated, today: '2026-11-04' });
    onSave.mockImplementationOnce(() => new Promise<void>(resolve => (answer = resolve)));

    fireEvent.click(screen.getByRole('button', { name: 'workbench.tasks.due_tomorrow' }));
    fireEvent.click(screen.getByRole('button', { name: 'workbench.tasks.due_none' }));
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText('workbench.tasks.due')).toHaveValue('');
    answer();

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(2));
    expect(onSave).toHaveBeenLastCalledWith(undated, { due: null });
  });
});

describe('TaskEditor — acts', () => {
  it('marks a task done or reopens it, never while its last change is on its way', async () => {
    const open = editor();
    await open.user.click(screen.getByRole('button', { name: 'workbench.tasks.mark_done' }));
    expect(open.onToggle).toHaveBeenCalledWith(TASK, true);
    open.unmount();

    const done = { ...TASK, completed: true };
    const reopened = editor({ task: done });
    await reopened.user.click(
      screen.getByRole('button', { name: 'workbench.tasks.reopen_action' })
    );
    expect(reopened.onToggle).toHaveBeenCalledWith(done, false);
    reopened.unmount();

    const busy = editor({ pending: new Set(['t1']) });
    await busy.user.click(screen.getByRole('button', { name: 'workbench.tasks.mark_done' }));
    expect(busy.onToggle).not.toHaveBeenCalled();
  });

  it('asks before deleting, and deletes nothing when the answer is no', async () => {
    const { user, onDelete } = editor();

    await user.click(screen.getByRole('button', { name: 'common.delete' }));
    await answerConfirmDialog(user, false);
    expect(onDelete).not.toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: 'common.delete' }));
    await answerConfirmDialog(user, true);
    await waitFor(() => expect(onDelete).toHaveBeenCalledWith(TASK));
  });

  it('says where it goes back to, and takes the focus when it replaces the list', async () => {
    const { user, onClose } = editor({ focusOnOpen: true });
    const back = screen.getByRole('button', { name: 'workbench.tools.tasks.label' });

    expect(back).toHaveFocus();
    await user.click(back);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('closes with a cross beside the list', async () => {
    width.desktop = true;
    const { user, onClose } = editor();

    await user.click(screen.getByRole('button', { name: 'workbench.tasks.close_detail' }));

    expect(onClose).toHaveBeenCalledTimes(1);
    width.desktop = false;
  });

  it('offers its acts in its bar, as an open event does', () => {
    editor();

    const acts = within(screen.getByTestId('detail-acts'))
      .getAllByRole('button')
      .map(button => button.getAttribute('aria-label'));

    expect(acts).toEqual([
      'common.save',
      'workbench.tasks.mark_done',
      'common.delete',
      'workbench.ask.label',
    ]);
    expect(screen.getByRole('button', { name: 'common.delete' })).toHaveClass('text-destructive');
  });

  it('submits the form from the bar it stands outside of', async () => {
    const { user, onSave } = editor();
    fireEvent.change(screen.getByLabelText('workbench.tasks.notes'), {
      target: { value: 'Whole milk' },
    });

    await user.click(save());

    await waitFor(() => expect(onSave).toHaveBeenCalledWith(TASK, { notes: 'Whole milk' }));
  });

  it('holds its act back while the task is on its way', async () => {
    const { user, onToggle } = editor({ pending: new Set(['t1']) });

    const done = screen.getByRole('button', { name: 'workbench.tasks.mark_done' });
    await user.click(done);

    expect(done).toHaveAttribute('aria-disabled', 'true');
    expect(onToggle).not.toHaveBeenCalled();
  });
});

describe('TaskEditor — subtasks', () => {
  const SUBTASKS: WorkbenchTask[] = [
    { ...TASK, id: 's1', title: 'Check the fridge', parent: 't1' },
    { ...TASK, id: 's2', title: '', parent: 't1', completed: true },
  ];

  it('lists a top-level task’s subtasks, ticks one, never a pending one', async () => {
    const { user, onToggle } = editor({ subtasks: SUBTASKS, pending: new Set(['s2']) });
    const section = screen.getByRole('region', { name: 'workbench.tasks.subtasks_title' });
    const [first, second] = within(section).getAllByRole('checkbox');

    expect(section).toHaveTextContent('Check the fridge');
    expect(section).toHaveTextContent('workbench.tasks.untitled');
    expect(second).toBeChecked();
    await user.click(first);
    await user.click(second);

    expect(onToggle).toHaveBeenCalledTimes(1);
    expect(onToggle).toHaveBeenCalledWith(SUBTASKS[0], true);
  });

  it('adds a subtask under the open task', async () => {
    const { user, onAddSubtask } = editor();

    await user.type(screen.getByLabelText('workbench.tasks.new_subtask'), 'Oat milk{Enter}');

    expect(onAddSubtask).toHaveBeenCalledWith(TASK, 'Oat milk', expect.any(String));
  });

  it('offers no subtasks where the provider has none, nor under a subtask', () => {
    const none = editor({ features: [] });
    expect(screen.queryByRole('region', { name: 'workbench.tasks.subtasks_title' })).toBeNull();
    none.unmount();

    editor({ task: { ...TASK, parent: 'p1' } });
    expect(screen.queryByRole('region', { name: 'workbench.tasks.subtasks_title' })).toBeNull();
  });
});
