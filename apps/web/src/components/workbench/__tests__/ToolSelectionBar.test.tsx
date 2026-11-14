/**
 * ToolSelectionBar — what a selection can become, on one line (ADR-369 amendment 2026-11-11).
 *
 * A tool says what it offers and the bar draws it: the acts used most as icons while the bar holds
 * them, the rest behind « … », the deletion last. Where the room runs out the icons join the list
 * instead of taking a line, and come back with the room. A « … » of one is never opened, and an
 * act that must be told where lists its places.
 */
import { Archive, FolderInput, MailCheck, MailOpen, Pencil, Star, Tag, Trash2 } from '@/lib/icons';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { act, renderWithProviders, screen, within } from '@/__tests__/test-utils';
import { DropdownMenuItem } from '@/components/ui/dropdown-menu';

import {
  ToolSelectionBar,
  type SelectionAct,
  type ToolSelectionBarProps,
} from '../ToolSelectionBar';

const MORE = 'common.more_actions';
const OUT = 'Clear the selection';

/** What each press ran, by the act's name. */
const ran = vi.fn<(id: string) => void>();

function plain(id: string, icon: SelectionAct['icon'], extra: Partial<SelectionAct> = {}) {
  return { id, label: id, icon, onSelect: () => ran(id), ...extra } satisfies SelectionAct;
}

const READ = plain('Mark read', MailCheck, { quick: true });
const ARCHIVE = plain('Archive', Archive, { quick: true });
const UNREAD = plain('Mark unread', MailOpen);
const STAR = plain('Follow up', Star);
const TRASH = plain('Delete', Trash2, { danger: true });
/** An act that must be told where: its places are its lines. */
const LABELS: SelectionAct = {
  id: 'Labels',
  label: 'Labels',
  icon: Tag,
  lines: <DropdownMenuItem onSelect={() => ran('Labels: Work')}>Work</DropdownMenuItem>,
};
const MAIL = [READ, ARCHIVE, UNREAD, STAR, TRASH];

function props(over: Partial<ToolSelectionBarProps> = {}): ToolSelectionBarProps {
  return {
    lng: 'en',
    regionLabel: 'Selected messages',
    countLabel: '3 selected',
    selectAllLabel: 'Select the page',
    clearLabel: OUT,
    pageState: 'some',
    onSelectAll: vi.fn(),
    onClear: vi.fn(),
    acts: MAIL,
    ...over,
  };
}

function draw(over: Partial<ToolSelectionBarProps> = {}) {
  return renderWithProviders(<ToolSelectionBar {...props(over)} />);
}

const bar = () => within(screen.getByRole('region', { name: 'Selected messages' }));

/** The bar's buttons as it draws them, the way out set aside. */
function drawn(): (string | null)[] {
  return bar()
    .getAllByRole('button')
    .map(button => button.getAttribute('aria-label'))
    .filter(name => name !== OUT);
}

async function listed(user: ReturnType<typeof draw>['user']): Promise<(string | null)[]> {
  await user.click(bar().getByRole('button', { name: MORE }));
  return (await screen.findAllByRole('menuitem')).map(line => line.textContent);
}

/** The room the bar has; what it draws takes its own: 10 a letter of the count, 40 a button. */
const layout = { room: 0 };
/** What each observer of the page would be told, were its bar resized. */
const observers: (() => void)[] = [];

/** Lays the bar out as a browser would: it overflows once what it draws no longer fits the room. */
function layOut(room: number) {
  layout.room = room;
  const isBar = (node: Element) => node.getAttribute('role') === 'region';
  vi.spyOn(Element.prototype, 'clientWidth', 'get').mockImplementation(function (this: Element) {
    return isBar(this) ? layout.room : 0;
  });
  vi.spyOn(Element.prototype, 'scrollWidth', 'get').mockImplementation(function (this: Element) {
    if (!isBar(this)) return 0;
    const count = this.querySelector('label')?.textContent?.length ?? 0;
    const taken = 10 * count + 40 * this.querySelectorAll('button').length;
    return Math.max(layout.room, taken);
  });
  class Observer implements ResizeObserver {
    constructor(callback: ResizeObserverCallback) {
      observers.push(() => callback([], this));
    }
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  vi.stubGlobal('ResizeObserver', Observer);
}

/** The bar's room changes, as a pane dragged wider or narrower. */
function resize(room: number) {
  layout.room = room;
  act(() => {
    for (const tell of observers) tell();
  });
}

afterEach(() => {
  ran.mockClear();
  observers.length = 0;
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('ToolSelectionBar', () => {
  it('stands what is used most in the bar, the rest behind « … », the deletion last', async () => {
    const { user } = draw();

    expect(drawn()).toEqual(['Mark read', 'Archive', MORE, 'Delete']);
    expect(await listed(user)).toEqual(['Mark unread', 'Follow up']);
  });

  it('runs an act from the bar and from the list', async () => {
    const { user } = draw();

    await user.click(bar().getByRole('button', { name: 'Archive' }));
    await user.click(bar().getByRole('button', { name: MORE }));
    await user.click(await screen.findByRole('menuitem', { name: 'Follow up' }));
    await user.click(bar().getByRole('button', { name: 'Delete' }));

    expect(ran.mock.calls.map(([id]) => id)).toEqual(['Archive', 'Follow up', 'Delete']);
  });

  it('names each icon for the ear and for a pointer', () => {
    draw();

    for (const name of ['Mark read', 'Archive', MORE, 'Delete']) {
      expect(bar().getByRole('button', { name })).toHaveAttribute('title', name);
    }
  });

  it('never opens a « … » of one: its act stands in the bar', () => {
    draw({ acts: [plain('Move', FolderInput, { quick: true }), plain('Rename', Pencil), TRASH] });

    expect(drawn()).toEqual(['Move', 'Rename', 'Delete']);
  });

  // By the keyboard: jsdom lays nothing out, so a pointer crossing from a line to its places
  // leaves the list on the way. The pointer's own crossing is played in a browser (e2e).
  it('lists the places of an act that must be told where, under its line', async () => {
    const { user } = draw({ acts: [...MAIL, LABELS] });

    expect(await listed(user)).toEqual(['Mark unread', 'Follow up', 'Labels']);
    screen.getByRole('menuitem', { name: 'Labels' }).focus();
    await user.keyboard('{ArrowRight}');
    expect(await screen.findByRole('menuitem', { name: 'Work' })).toHaveFocus();
    await user.keyboard('{Enter}');

    expect(ran).toHaveBeenCalledWith('Labels: Work');
  });

  it('opens the places under the act’s own icon where it stands alone', async () => {
    const { user } = draw({ acts: [READ, LABELS, TRASH] });

    expect(drawn()).toEqual(['Mark read', 'Labels', 'Delete']);
    await user.click(bar().getByRole('button', { name: 'Labels' }));
    await user.click(await screen.findByRole('menuitem', { name: 'Work' }));

    expect(ran).toHaveBeenCalledWith('Labels: Work');
  });

  it('runs nothing while held, and leaves the focus where it is', async () => {
    const { user } = draw({ held: true });

    const read = bar().getByRole('button', { name: 'Mark read' });
    await user.click(read);
    await user.click(bar().getByRole('button', { name: 'Delete' }));

    expect(ran).not.toHaveBeenCalled();
    expect(read).toHaveAttribute('aria-disabled', 'true');
    expect(read).not.toBeDisabled();
    expect(await listed(user)).toEqual(['Mark unread', 'Follow up']);
    await user.click(screen.getByRole('menuitem', { name: 'Follow up' }));
    expect(ran).not.toHaveBeenCalled();
  });

  it('says an act on its way on the control that holds it', () => {
    draw({ acts: [READ, ARCHIVE, UNREAD, { ...STAR, busy: true }, { ...TRASH, busy: true }] });

    expect(bar().getByRole('button', { name: MORE })).toHaveAttribute('aria-busy', 'true');
    expect(bar().getByRole('button', { name: 'Delete' })).toHaveAttribute('aria-busy', 'true');
    expect(bar().getByRole('button', { name: 'Archive' })).not.toHaveAttribute('aria-busy');
  });

  it('says what holds the acts back, under the bar', () => {
    draw({ held: true, note: 'At most 50 messages at once' });

    expect(screen.getByRole('status')).toHaveTextContent('At most 50 messages at once');
  });

  it('empties the selection from the icon beside the count', async () => {
    const onClear = vi.fn();
    const { user } = draw({ onClear });

    await user.click(bar().getByRole('button', { name: OUT }));

    expect(onClear).toHaveBeenCalledTimes(1);
  });
});

describe('ToolSelectionBar — where the room runs out', () => {
  // « 3 selected » takes 100: the bar whole takes 300 (five buttons), folded 220 (three).
  it('folds what is used most into the list instead of taking a line', async () => {
    layOut(280);
    const { user } = draw();

    expect(drawn()).toEqual([MORE, 'Delete']);
    expect(await listed(user)).toEqual(['Mark read', 'Archive', 'Mark unread', 'Follow up']);
  });

  it('keeps the bar whole where it fits', () => {
    layOut(300);
    draw();

    expect(drawn()).toEqual(['Mark read', 'Archive', MORE, 'Delete']);
  });

  it('draws the icons again once the room is back, and folds them when it goes', () => {
    layOut(280);
    draw();
    expect(drawn()).toEqual([MORE, 'Delete']);

    resize(400);
    expect(drawn()).toEqual(['Mark read', 'Archive', MORE, 'Delete']);

    resize(280);
    expect(drawn()).toEqual([MORE, 'Delete']);
  });

  it('measures again when what it offers changes', () => {
    layOut(280);
    const { rerender } = draw();
    expect(drawn()).toEqual([MORE, 'Delete']);

    // Four buttons take 260: what folded a moment ago fits whole.
    rerender(<ToolSelectionBar {...props({ acts: [READ, ARCHIVE, TRASH] })} />);

    expect(drawn()).toEqual(['Mark read', 'Archive', 'Delete']);
  });

  it('measures again when the count takes another room', () => {
    const acts = [READ, ARCHIVE, TRASH];
    layOut(265);
    const { rerender } = draw({ acts });
    expect(drawn()).toEqual(['Mark read', 'Archive', 'Delete']);

    // Two letters more, and the four buttons take 280.
    rerender(<ToolSelectionBar {...props({ acts, countLabel: '120 selected' })} />);
    expect(drawn()).toEqual([MORE, 'Delete']);

    rerender(<ToolSelectionBar {...props({ acts })} />);
    expect(drawn()).toEqual(['Mark read', 'Archive', 'Delete']);
  });

  it('opens no « … » of one where the room runs out either', () => {
    layOut(200);
    draw({ acts: [plain('Move', FolderInput, { quick: true }), TRASH] });

    expect(drawn()).toEqual(['Move', 'Delete']);
  });
});
