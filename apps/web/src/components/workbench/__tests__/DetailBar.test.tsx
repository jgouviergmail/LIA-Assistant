/**
 * The bar of a detail (ADR-369): the way out, then what can be done, in icons, as a message's
 * reader draws them (owner, 2026-11-06). What is less common waits behind « … », and a « … » of
 * one is no menu: its act stands in the bar. An act that must be told where opens its own list.
 * Every bar ends on the same two acts: the deletion, then the question to LIA.
 */
import { CalendarArrowUp, Pencil, Sparkles, Trash2 } from '@/lib/icons';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, waitFor, within } from '@/__tests__/test-utils';

const { width } = vi.hoisted(() => ({ width: { desktop: false } }));
vi.mock('@/hooks/useMediaQuery', () => ({ useMediaQuery: () => width.desktop }));

import { DetailBar, actIf, askAct, type DetailAct } from '../DetailBar';

const EDIT: DetailAct = { label: 'Edit', icon: Pencil, onSelect: vi.fn() };
const LATER: DetailAct = { label: 'Later', icon: Sparkles, onSelect: vi.fn(), more: true };
const DROP: DetailAct = { label: 'Drop', icon: Trash2, onSelect: vi.fn(), danger: true };

/** An act that goes somewhere, the places it can go named one by one. */
function moving(...places: readonly string[]) {
  const onPlace = vi.fn();
  const act: DetailAct = {
    label: 'Move',
    icon: CalendarArrowUp,
    choices: places.map(place => ({
      label: place,
      icon: CalendarArrowUp,
      onSelect: () => onPlace(place),
    })),
  };
  return { act, onPlace };
}

function draw(acts?: readonly DetailAct[], onClose = vi.fn()) {
  const rendered = renderWithProviders(
    <DetailBar lng="en" closeLabel="Close" backLabel="Files" onClose={onClose} acts={acts} />
  );
  return { ...rendered, onClose };
}

const MORE = 'common.more_actions';

/** The bar's acts, the way out set aside. */
function acts(): (string | null)[] {
  return within(screen.getByTestId('detail-acts'))
    .getAllByRole('button')
    .map(act => act.getAttribute('aria-label'));
}

describe('DetailBar', () => {
  it('leads with the way out', async () => {
    const { user, onClose } = draw([EDIT]);

    await user.click(screen.getByRole('button', { name: 'Files' }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('draws the way out alone while the thing is being read', () => {
    draw();

    expect(screen.getByRole('button', { name: 'Files' })).toBeInTheDocument();
    expect(screen.queryByTestId('detail-acts')).toBeNull();
  });

  it('draws an act as an icon, named for the ear and for a pointer', async () => {
    const onSelect = vi.fn();
    const { user } = draw([{ ...EDIT, onSelect }]);

    const act = screen.getByRole('button', { name: 'Edit' });
    await user.click(act);

    expect(act).toHaveAttribute('title', 'Edit');
    expect(act).toHaveTextContent('');
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it('keeps a deletion in the colour of what cannot be taken lightly', () => {
    draw([DROP]);

    expect(screen.getByRole('button', { name: 'Drop' })).toHaveClass('text-destructive');
  });

  it('keeps that colour behind « … »', async () => {
    const { user } = draw([LATER, { ...DROP, more: true }]);

    await user.click(screen.getByRole('button', { name: MORE }));

    expect(await screen.findByRole('menuitem', { name: 'Drop' })).toHaveClass('text-destructive');
  });

  it('holds what is less common behind « … », in the order given', async () => {
    const { user } = draw([EDIT, { ...LATER, label: 'Rename' }, LATER]);

    expect(screen.queryByRole('button', { name: 'Rename' })).toBeNull();
    await user.click(screen.getByRole('button', { name: MORE }));

    const items = await screen.findAllByRole('menuitem');
    expect(items.map(item => item.textContent)).toEqual(['Rename', 'Later']);
  });

  it('runs what the menu holds', async () => {
    const onSelect = vi.fn();
    const { user } = draw([
      { ...LATER, label: 'Rename', onSelect },
      LATER,
    ]);

    await user.click(screen.getByRole('button', { name: MORE }));
    await user.click(await screen.findByRole('menuitem', { name: 'Rename' }));

    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it('runs nothing for an act held back behind « … »', async () => {
    const onSelect = vi.fn();
    const { user } = draw([{ ...LATER, onSelect, held: true }, { ...LATER, label: 'Sooner' }]);

    await user.click(screen.getByRole('button', { name: MORE }));
    const held = await screen.findByRole('menuitem', { name: 'Later' });
    await user.click(held);

    expect(held).toHaveAttribute('aria-disabled', 'true');
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('opens no menu for one act: it stands in the bar', () => {
    draw([EDIT, LATER]);

    expect(screen.getByRole('button', { name: 'Later' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: MORE })).toBeNull();
  });

  it('follows a link in a tab that cannot reach back', () => {
    draw([{ label: 'Open', icon: Pencil, href: 'https://example.org/a', external: true }]);

    const link = screen.getByRole('link', { name: 'Open' });

    expect(link).toHaveAttribute('href', 'https://example.org/a');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    expect(link).toHaveAttribute('title', 'Open');
  });

  it('downloads from the page when the link stays in it', () => {
    draw([{ label: 'Export', icon: Pencil, href: '/api/contacts.vcf' }]);

    expect(screen.getByRole('link', { name: 'Export' })).not.toHaveAttribute('target');
  });

  it('follows a link from the menu too', async () => {
    const { user } = draw([
      { label: 'Export', icon: Pencil, href: '/api/contacts.vcf', more: true },
      LATER,
    ]);

    await user.click(screen.getByRole('button', { name: MORE }));

    expect(await screen.findByRole('menuitem', { name: 'Export' })).toHaveAttribute(
      'href',
      '/api/contacts.vcf'
    );
  });

  it('submits a form it stands outside of', () => {
    draw([{ label: 'Save', icon: Pencil, form: 'the-form' }]);

    const save = screen.getByRole('button', { name: 'Save' });

    expect(save).toHaveAttribute('type', 'submit');
    expect(save).toHaveAttribute('form', 'the-form');
  });

  it('says an act is on its way and refuses a second one', async () => {
    const onSelect = vi.fn();
    const { user } = draw([{ ...EDIT, onSelect, busy: true }]);

    const act = screen.getByRole('button', { name: 'Edit' });
    await user.click(act);

    expect(act).toHaveAttribute('aria-busy', 'true');
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('keeps the focus on an act held back, and runs nothing', async () => {
    const onSelect = vi.fn();
    const { user } = draw([{ ...EDIT, onSelect, held: true }]);

    const act = screen.getByRole('button', { name: 'Edit' });
    await user.click(act);

    expect(act).toHaveAttribute('aria-disabled', 'true');
    expect(act).not.toBeDisabled();
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('draws the way out alone while there is nothing to act on', () => {
    draw();

    expect(within(screen.getByTestId('detail-bar')).getAllByRole('button')).toHaveLength(1);
  });
});

describe('DetailBar — how every bar ends', () => {
  const ask = askAct('Ask', vi.fn());

  it('ends on the deletion, then the question, whatever order a tool declares', () => {
    draw([ask, DROP, EDIT]);

    expect(acts()).toEqual(['Edit', 'Drop', 'Ask']);
  });

  it('stands « … » before them', () => {
    draw([ask, DROP, { ...LATER, label: 'Rename' }, EDIT, LATER]);

    expect(acts()).toEqual(['Edit', MORE, 'Drop', 'Ask']);
  });

  it('stands an act alone in « … » before them too', () => {
    draw([DROP, LATER, ask]);

    expect(acts()).toEqual(['Later', 'Drop', 'Ask']);
  });

  it('ends on the question where nothing can be deleted', () => {
    draw([ask, EDIT]);

    expect(acts()).toEqual(['Edit', 'Ask']);
  });

  it('keeps its own place for a deletion held behind « … »', async () => {
    const { user } = draw([ask, EDIT, { ...DROP, more: true }, LATER]);

    expect(acts()).toEqual(['Edit', MORE, 'Ask']);
    await user.click(screen.getByRole('button', { name: MORE }));

    expect(await screen.findByRole('menuitem', { name: 'Drop' })).toBeInTheDocument();
  });

  it('asks LIA on a press', async () => {
    const onSelect = vi.fn();
    const { user } = draw([askAct('Ask', onSelect)]);

    await user.click(screen.getByRole('button', { name: 'Ask' }));

    expect(onSelect).toHaveBeenCalledTimes(1);
  });
});

describe('DetailBar — an act that must be told where', () => {
  it('draws it as an icon, named for the ear and for a pointer', () => {
    draw([moving('Team', 'Family').act]);

    const act = screen.getByRole('button', { name: 'Move' });

    expect(act).toHaveAttribute('title', 'Move');
    expect(act).toHaveTextContent('');
    expect(act).toHaveAttribute('aria-haspopup', 'menu');
  });

  it('lists where it can go, in the order given, and goes where it is told', async () => {
    const { act, onPlace } = moving('Team', 'Family');
    const { user } = draw([act]);

    await user.click(screen.getByRole('button', { name: 'Move' }));
    const items = await screen.findAllByRole('menuitem');
    expect(items.map(item => item.textContent)).toEqual(['Team', 'Family']);
    await user.click(items[1]!);

    expect(onPlace).toHaveBeenCalledTimes(1);
    expect(onPlace).toHaveBeenCalledWith('Family');
  });

  it('shows its one place before going there: a press never goes somewhere unread', async () => {
    const { act, onPlace } = moving('Team');
    const { user } = draw([act]);

    await user.click(screen.getByRole('button', { name: 'Move' }));

    expect(await screen.findByRole('menuitem', { name: 'Team' })).toBeInTheDocument();
    expect(onPlace).not.toHaveBeenCalled();
  });

  it('stands at its place in the order, before « … »', async () => {
    const { user } = draw([
      EDIT,
      moving('Team').act,
      DROP,
      { ...LATER, label: 'Rename' },
      LATER,
    ]);

    expect(acts()).toEqual(['Edit', 'Move', MORE, 'Drop']);
    await user.click(screen.getByRole('button', { name: MORE }));

    const items = await screen.findAllByRole('menuitem');
    expect(items.map(item => item.textContent)).toEqual(['Rename', 'Later']);
  });

  it('opens from the keyboard, and hands the focus back to its icon', async () => {
    const { act, onPlace } = moving('Team');
    const { user } = draw([act]);
    const icon = screen.getByRole('button', { name: 'Move' });

    icon.focus();
    await user.keyboard('{Enter}');
    expect(await screen.findByRole('menuitem', { name: 'Team' })).toBeInTheDocument();
    await user.keyboard('{Escape}');

    await waitFor(() => expect(icon).toHaveFocus());
    expect(screen.queryByRole('menuitem', { name: 'Team' })).toBeNull();
    expect(onPlace).not.toHaveBeenCalled();
  });

  it('goes where the keyboard picks', async () => {
    const { act, onPlace } = moving('Team', 'Family');
    const { user } = draw([act]);

    screen.getByRole('button', { name: 'Move' }).focus();
    await user.keyboard('{Enter}');
    await screen.findByRole('menuitem', { name: 'Team' });
    await user.keyboard('{ArrowDown}{Enter}');

    await waitFor(() => expect(onPlace).toHaveBeenCalledWith('Family'));
    expect(onPlace).toHaveBeenCalledTimes(1);
  });
});

describe('DetailBar — what LIA can do here, under the question', () => {
  const SUM_UP = { label: 'Sum it up', icon: Pencil, onSelect: vi.fn() };

  it('stays one press while the question is all there is', async () => {
    const onAsk = vi.fn();
    const { user } = draw([askAct('Ask', onAsk, { lines: [] })]);

    await user.click(screen.getByRole('button', { name: 'Ask' }));

    expect(onAsk).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('adds no icon to the bar: the same one opens the list, still last', async () => {
    const { user } = draw([askAct('Ask', vi.fn(), { lines: [SUM_UP] }), DROP, EDIT]);

    expect(acts()).toEqual(['Edit', 'Drop', 'Ask']);
    await user.click(screen.getByRole('button', { name: 'Ask' }));

    const items = await screen.findAllByRole('menuitem');
    expect(items.map(item => item.textContent)).toEqual(['Sum it up', 'Ask']);
  });

  it('runs a line, and the question from its own line', async () => {
    const onAsk = vi.fn();
    const onSelect = vi.fn();
    const { user } = draw([askAct('Ask', onAsk, { lines: [{ ...SUM_UP, onSelect }] })]);

    await user.click(screen.getByRole('button', { name: 'Ask' }));
    await user.click(await screen.findByRole('menuitem', { name: 'Sum it up' }));
    await user.click(screen.getByRole('button', { name: 'Ask' }));
    await user.click(await screen.findByRole('menuitem', { name: 'Ask' }));

    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onAsk).toHaveBeenCalledTimes(1);
  });

  it('sets the question apart from what runs here', async () => {
    const { user } = draw([askAct('Ask', vi.fn(), { lines: [SUM_UP] })]);

    await user.click(screen.getByRole('button', { name: 'Ask' }));

    expect(await screen.findByRole('separator')).toBeInTheDocument();
  });

  it('keeps a ready-made question beside the question: both go to the chat', async () => {
    const ready = { ...SUM_UP, label: 'Find related', asks: true, ruled: true };
    const { user } = draw([askAct('Ask', vi.fn(), { lines: [SUM_UP, ready] })]);

    await user.click(screen.getByRole('button', { name: 'Ask' }));

    expect(await screen.findAllByRole('separator')).toHaveLength(1);
  });

  it('sets a line apart where the tool says a group starts', async () => {
    const { user } = draw([
      askAct('Ask', vi.fn(), {
        lines: [SUM_UP, { ...SUM_UP, label: 'Remind me', ruled: true }],
      }),
    ]);

    await user.click(screen.getByRole('button', { name: 'Ask' }));

    expect(await screen.findAllByRole('separator')).toHaveLength(2);
  });

  it('says on its one icon that a line is on its way, and still opens', async () => {
    const { user } = draw([askAct('Ask', vi.fn(), { lines: [SUM_UP], busy: true })]);

    const icon = screen.getByRole('button', { name: 'Ask' });
    expect(icon).toHaveAttribute('aria-busy', 'true');
    await user.click(icon);

    expect(await screen.findByRole('menuitem', { name: 'Sum it up' })).toBeInTheDocument();
  });
});

describe('actIf', () => {
  it('leaves an act out on its condition', () => {
    expect(actIf(false, EDIT)).toEqual([]);
    expect(actIf(true, EDIT)).toEqual([EDIT]);
  });
});
