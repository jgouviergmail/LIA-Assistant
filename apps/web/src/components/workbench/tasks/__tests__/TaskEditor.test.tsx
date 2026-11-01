/**
 * One task edited by hand (ADR-369): only what changed is sent, a title is
 * required, emptying the due date removes it, a refusal keeps what was typed,
 * deleting asks first, and where the provider has subtasks a top-level task
 * lists them, ticks them and takes a new one.
 */

import { describe, expect, it, vi } from 'vitest';

import {
  answerConfirmDialog,
  fireEvent,
  renderWithProviders,
  screen,
  waitFor,
  within,
} from '@/__tests__/test-utils';
import type { WorkbenchFeature, WorkbenchTask } from '@/lib/workbench/types';

import { TaskEditor } from '../TaskEditor';

const TASK: WorkbenchTask = {
  id: 't1',
  title: 'Buy milk',
  notes: null,
  completed: false,
  due: '2026-11-03',
  parent: null,
  position: null,
};

function editor({
  task = TASK,
  subtasks = [],
  features = ['subtasks'],
  pending = new Set<string>(),
  focusOnOpen = false,
}: {
  task?: WorkbenchTask;
  subtasks?: WorkbenchTask[];
  features?: WorkbenchFeature[];
  pending?: Set<string>;
  focusOnOpen?: boolean;
} = {}) {
  const props = {
    onSave: vi.fn().mockResolvedValue(undefined),
    onToggle: vi.fn(),
    onDelete: vi.fn().mockResolvedValue(undefined),
    onAddSubtask: vi.fn().mockResolvedValue(undefined),
    onClose: vi.fn(),
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
      {...props}
    />
  );
  return { ...rendered, ...props };
}

const save = () => screen.getByRole('button', { name: 'common.save' });

describe('TaskEditor — editing', () => {
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
    onSave.mockImplementationOnce(
      () => new Promise<void>((_, reject) => (refuse = reject))
    );
    const notes = screen.getByLabelText('workbench.tasks.notes');

    await user.type(notes, 'oat');
    await user.click(save());
    fireEvent.submit(notes.closest('form') as HTMLFormElement);
    expect(onSave).toHaveBeenCalledTimes(1);
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

describe('TaskEditor — acts', () => {
  it('marks a task done or reopens it, never while its last change is on its way', async () => {
    const open = editor();
    await open.user.click(screen.getByRole('button', { name: 'workbench.tasks.mark_done' }));
    expect(open.onToggle).toHaveBeenCalledWith(TASK, true);
    open.unmount();

    const done = { ...TASK, completed: true };
    const reopened = editor({ task: done });
    await reopened.user.click(screen.getByRole('button', { name: 'workbench.tasks.reopen_action' }));
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

  it('closes from either way out, and takes the focus when it replaces the list', async () => {
    const { user, onClose } = editor({ focusOnOpen: true });
    const back = screen.getByRole('button', { name: 'workbench.tasks.back_to_list' });

    expect(back).toHaveFocus();
    await user.click(back);
    await user.click(screen.getByRole('button', { name: 'workbench.tasks.close_detail' }));
    expect(onClose).toHaveBeenCalledTimes(2);
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
