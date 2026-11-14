/**
 * TaskSelectionBar — what ticked tasks can become, on one line (ADR-369 amendment 2026-11-11):
 * done as an icon, the rest behind « … », the deletion last. Another list is a place: the lists
 * stand under their own line, and none is offered where there is no other list.
 */
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, within } from '@/__tests__/test-utils';
import type { WorkbenchTaskList } from '@/lib/workbench/types';

import { TaskSelectionBar, type TaskSelectionBarProps } from '../TaskSelectionBar';

const MORE = 'common.more_actions';
const tasks = (key: string) => `workbench.tasks.${key}`;

const TRIP: WorkbenchTaskList = { id: 'l2', title: 'Trip', default: false };
const UNNAMED: WorkbenchTaskList = { id: 'l3', title: '', default: false };

function draw(over: Partial<TaskSelectionBarProps> = {}) {
  const props: TaskSelectionBarProps = {
    lng: 'en',
    count: 2,
    pageState: 'some',
    others: [TRIP, UNNAMED],
    busy: false,
    onSelectAll: vi.fn(),
    onClear: vi.fn(),
    onCompleted: vi.fn(),
    onDelete: vi.fn(),
    onMove: vi.fn(),
    ...over,
  };
  return { ...renderWithProviders(<TaskSelectionBar {...props} />), props };
}

const bar = () => within(screen.getByRole('region', { name: tasks('selection_region') }));

/** The bar's buttons as it draws them, the way out of the selection set aside. */
function drawn(): (string | null)[] {
  return bar()
    .getAllByRole('button')
    .map(button => button.getAttribute('aria-label'))
    .filter(name => name !== tasks('clear_selection'));
}

type User = ReturnType<typeof draw>['user'];

async function listed(user: User): Promise<(string | null)[]> {
  await user.click(bar().getByRole('button', { name: MORE }));
  return (await screen.findAllByRole('menuitem')).map(line => line.textContent);
}

/** Opens the lists a selection can go to, by the keyboard (jsdom lays no pointer path out). */
async function places(user: User): Promise<HTMLElement[]> {
  await listed(user);
  const line = screen.getByRole('menuitem', { name: tasks('move_to_list') });
  line.focus();
  await user.keyboard('{ArrowRight}');
  await screen.findByRole('menuitem', { name: 'Trip' });
  const [, lists] = screen.getAllByRole('menu');
  return within(lists!).getAllByRole('menuitem');
}

describe('TaskSelectionBar', () => {
  it('draws done as an icon, the rest behind « … », the deletion last', async () => {
    const { user } = draw();

    expect(drawn()).toEqual([tasks('complete_selection'), MORE, 'common.delete']);
    expect(await listed(user)).toEqual([tasks('reopen_selection'), tasks('move_to_list')]);
  });

  it('marks what is ticked done, or not done', async () => {
    const { user, props } = draw();

    await user.click(bar().getByRole('button', { name: tasks('complete_selection') }));
    await listed(user);
    await user.click(screen.getByRole('menuitem', { name: tasks('reopen_selection') }));

    expect(vi.mocked(props.onCompleted).mock.calls).toEqual([[true], [false]]);
  });

  it('lists the other lists under their line, and sends the selection to the one chosen', async () => {
    const { user, props } = draw();

    const lists = await places(user);
    expect(lists.map(line => line.textContent)).toEqual(['Trip', tasks('untitled')]);
    lists[0]!.focus();
    await user.keyboard('{Enter}');

    expect(props.onMove).toHaveBeenCalledWith('l2');
  });

  it('offers no other list where there is none: reopening stands in the bar', () => {
    draw({ others: [] });

    expect(drawn()).toEqual([
      tasks('complete_selection'),
      tasks('reopen_selection'),
      'common.delete',
    ]);
  });

  it('deletes through its own door, solid red', async () => {
    const { user, props } = draw();

    const drop = bar().getByRole('button', { name: 'common.delete' });
    await user.click(drop);

    expect(props.onDelete).toHaveBeenCalledTimes(1);
    expect(drop).toHaveClass('bg-destructive');
  });

  it('runs nothing while an act is on its way, and keeps the focus', async () => {
    const { user, props } = draw({ busy: true });

    const done = bar().getByRole('button', { name: tasks('complete_selection') });
    await user.click(done);
    await user.click(bar().getByRole('button', { name: 'common.delete' }));

    expect(props.onCompleted).not.toHaveBeenCalled();
    expect(props.onDelete).not.toHaveBeenCalled();
    expect(done).toHaveAttribute('aria-disabled', 'true');
    expect(done).not.toBeDisabled();
  });

  it('states the count, and empties the selection from the icon beside it', async () => {
    const { user, props } = draw();

    expect(bar().getByText(tasks('selected'))).toBeInTheDocument();
    await user.click(bar().getByRole('button', { name: tasks('clear_selection') }));

    expect(props.onClear).toHaveBeenCalledTimes(1);
  });
});
