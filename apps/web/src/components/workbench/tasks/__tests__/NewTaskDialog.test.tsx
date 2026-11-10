/**
 * A task handed by another tool, reviewed whole before it exists (owner, 2026-11-07): every value
 * LIA read stands in the form, the list it names is chosen, what the provider keeps no word for is
 * not offered, and one key covers a submission until the task is made.
 */

import { describe, expect, it, vi } from 'vitest';

import { act, fireEvent, renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import type { NewTaskBody } from '@/hooks/useWorkbenchTasks';
import type {
  WorkbenchFeature,
  WorkbenchTaskList,
  WorkbenchToolAvailability,
} from '@/lib/workbench/types';

import { NewTaskDialog, type NewTaskFields } from '../NewTaskDialog';

const GOOGLE: WorkbenchFeature[] = ['list_management', 'subtasks', 'due_date_only', 'task_order'];
const TO_DO: WorkbenchFeature[] = ['list_management', 'task_steps', 'task_details'];
const LISTS: WorkbenchTaskList[] = [
  { id: 'l1', title: 'Home', default: true },
  { id: 'l2', title: 'Work', default: false },
];
const HANDED: NewTaskFields = {
  title: 'Send the signed quote to Paul',
  notes: 'Paul asks for the signed quote before Friday.\nReference: Q-2291.',
  due: '2026-11-13',
  listName: 'work',
  importance: 'high',
};

function toolWith(features: WorkbenchFeature[]): WorkbenchToolAvailability {
  return {
    tool: 'tasks',
    state: 'ready',
    provider: features === TO_DO ? 'microsoft_tasks' : 'google_tasks',
    features,
    bounds: { title_max_chars: 255, notes_max_chars: 8192 },
  };
}

function dialog(
  overrides: { features?: WorkbenchFeature[]; initial?: NewTaskFields } = {},
  onCreate: (body: NewTaskBody) => Promise<void> = vi.fn().mockResolvedValue(undefined)
) {
  const onClose = vi.fn();
  const view = renderWithProviders(
    <NewTaskDialog
      lng="en"
      tool={toolWith(overrides.features ?? TO_DO)}
      lists={LISTS}
      listId="l1"
      today="2026-11-07"
      zone="Europe/Paris"
      initial={overrides.initial ?? HANDED}
      onCreate={onCreate}
      onClose={onClose}
    />
  );
  return { ...view, onCreate, onClose };
}

const ADD = 'workbench.tasks.add';

describe('NewTaskDialog', () => {
  it('claims a submission before another submit event in the same frame', async () => {
    let finish = () => {};
    const waiting = new Promise<void>(resolve => {
      finish = resolve;
    });
    const onCreate = vi.fn(() => waiting);
    dialog({}, onCreate);
    const form = screen.getByLabelText('workbench.tasks.title').closest('form');
    if (!form) throw new Error('Expected the native task form');
    act(() => {
      fireEvent.submit(form);
      fireEvent.submit(form);
    });
    expect(onCreate).toHaveBeenCalledOnce();
    await act(async () => finish());
  });
  it('opens on every value it was handed, the list it names chosen', () => {
    dialog();

    expect(screen.getByLabelText('workbench.tasks.title')).toHaveValue(HANDED.title);
    expect(screen.getByLabelText('workbench.tasks.notes')).toHaveValue(HANDED.notes);
    expect(screen.getByLabelText('workbench.tasks.due')).toHaveValue('2026-11-13');
    expect(screen.getByLabelText('workbench.tasks.list_label')).toHaveValue('l2');
    expect(screen.getByLabelText('workbench.tasks.importance')).toHaveValue('high');
  });

  it('adds what the form holds, in the list chosen', async () => {
    const { user, onCreate } = dialog();

    await user.click(screen.getByRole('button', { name: ADD }));

    await waitFor(() => expect(onCreate).toHaveBeenCalledTimes(1));
    const body = vi.mocked(onCreate).mock.calls[0][0];
    expect(body).toMatchObject({
      title: HANDED.title,
      notes: HANDED.notes,
      due: '2026-11-13',
      list_id: 'l2',
      importance: 'high',
    });
    expect(body.idempotency_key).toMatch(/^[0-9a-f-]{36}$/);
  });

  it('leaves a task in the open list when no list of the person has the name read', () => {
    dialog({ initial: { ...HANDED, listName: 'Garden' } });

    expect(screen.getByLabelText('workbench.tasks.list_label')).toHaveValue('l1');
  });

  it('offers no importance, reminder or repetition where the provider keeps none', async () => {
    const { user, onCreate } = dialog({ features: GOOGLE });

    expect(screen.queryByLabelText('workbench.tasks.importance')).toBeNull();
    expect(screen.queryByLabelText('workbench.tasks.reminder')).toBeNull();
    await user.click(screen.getByRole('button', { name: ADD }));

    await waitFor(() => expect(onCreate).toHaveBeenCalled());
    expect(vi.mocked(onCreate).mock.calls[0][0]).not.toHaveProperty('importance');
  });

  it('sends a reminder on the account clock', async () => {
    const { user, onCreate } = dialog();

    fireEvent.change(screen.getByLabelText('workbench.tasks.reminder'), {
      target: { value: '2026-11-13T09:00' },
    });
    fireEvent.blur(screen.getByLabelText('workbench.tasks.reminder'));
    await user.click(screen.getByRole('button', { name: ADD }));

    await waitFor(() => expect(onCreate).toHaveBeenCalled());
    expect(vi.mocked(onCreate).mock.calls[0][0].reminder).toBe('2026-11-13T08:00:00.000Z');
  });

  it('keeps a reminder typed and sent with Enter, before its field was left', async () => {
    const { onCreate } = dialog();
    const reminder = screen.getByLabelText('workbench.tasks.reminder');

    fireEvent.change(reminder, { target: { value: '2026-11-13T09:00' } });
    fireEvent.submit(reminder.closest('form') as HTMLFormElement);

    await waitFor(() => expect(onCreate).toHaveBeenCalled());
    expect(vi.mocked(onCreate).mock.calls[0][0].reminder).toBe('2026-11-13T08:00:00.000Z');
  });

  it('adds nothing without a title', async () => {
    const { user, onCreate } = dialog({ initial: { ...HANDED, title: '  ' } });

    await user.click(screen.getByRole('button', { name: ADD }));

    expect(screen.getByText('workbench.tasks.title_required')).toBeInTheDocument();
    expect(onCreate).not.toHaveBeenCalled();
  });

  it('keeps the form and its key when the provider refuses, so a second try is the same act', async () => {
    const onCreate = vi
      .fn<(body: NewTaskBody) => Promise<void>>()
      .mockRejectedValueOnce(new Error('refused'))
      .mockResolvedValueOnce(undefined);
    const { user, onClose } = dialog({}, onCreate);

    await user.click(screen.getByRole('button', { name: ADD }));
    await waitFor(() => expect(onCreate).toHaveBeenCalledTimes(1));
    expect(screen.getByLabelText('workbench.tasks.title')).toHaveValue(HANDED.title);
    expect(onClose).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: ADD }));

    await waitFor(() => expect(onCreate).toHaveBeenCalledTimes(2));
    expect(onCreate.mock.calls[1][0].idempotency_key).toBe(
      onCreate.mock.calls[0][0].idempotency_key
    );
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
  });

  it('creates nothing when the person cancels', async () => {
    const { user, onCreate, onClose } = dialog();

    await user.click(screen.getByRole('button', { name: 'common.cancel' }));

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(onCreate).not.toHaveBeenCalled();
  });

  it('offers the days at hand, and no date at all', async () => {
    const { user } = dialog();

    await user.click(screen.getByRole('button', { name: 'workbench.tasks.due_tomorrow' }));
    expect(screen.getByLabelText('workbench.tasks.due')).toHaveValue('2026-11-08');
    await user.click(screen.getByRole('button', { name: 'workbench.tasks.due_none' }));

    expect(screen.getByLabelText('workbench.tasks.due')).toHaveValue('');
  });
});
