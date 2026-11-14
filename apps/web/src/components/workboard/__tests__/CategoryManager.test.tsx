/**
 * Administering the categories of a board.
 *
 * The dialog writes through the three verbs of `useWorkboardCategories`; the
 * tests hand it a stand-in for that hook's result and read what a person sees
 * and what is asked of the server. What they hold:
 *
 * - a name is written when the field is LEFT or Enter is pressed, never on
 *   every key, and a refused name gives the stored one back;
 * - the order moves one place at a time, by the POSITION the server is asked
 *   for, and the edges do nothing rather than vanish;
 * - a deletion states the EXACT number of tickets it sends back to the
 *   unfiled lane, and dismissal is never consent;
 * - the cap the server enforces is the cap the dialog shows, and it explains
 *   itself instead of sending a create that will be refused;
 * - every write that changed the lanes tells the page, which re-reads them.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { toast } from 'sonner';

import { renderWithProviders, screen, waitFor, within } from '@/__tests__/test-utils';
import { CategoryManager, type CategorySource } from '@/components/workboard/CategoryManager';
import type { CategoryRow } from '@/types/workboard';

// The suite's `t` drops the values; a category is told apart by its NAME.
const i18n = vi.hoisted(() => ({
  t: (key: string, values?: Record<string, unknown>) =>
    values ? `${key} ${JSON.stringify(values)}` : key,
  i18n: { language: 'fr' },
}));
vi.mock('react-i18next', () => ({ useTranslation: () => i18n }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const ME = 'me';

function category(id: string, name: string, position: number, ticket_count = 0): CategoryRow {
  return { id, owner_user_id: ME, name, position, ticket_count };
}

const HOME = category('home', 'Maison', 0, 3);
const WORK = category('work', 'Travail', 1, 0);
const HEALTH = category('health', 'Santé', 2, 1);

const OK = { ok: true, errorCode: null };

function source(overrides: Partial<CategorySource> = {}): CategorySource {
  return {
    own: [HOME, WORK, HEALTH],
    maxCategories: 20,
    nameMaxChars: 40,
    firstLoad: false,
    error: false,
    create: vi.fn().mockResolvedValue(OK),
    update: vi.fn().mockResolvedValue(OK),
    remove: vi.fn().mockResolvedValue({ ...OK, released: 0 }),
    ...overrides,
  };
}

const onChanged = vi.fn();
const onClose = vi.fn();

function managerElement(from: CategorySource) {
  return <CategoryManager open source={from} onClose={onClose} onChanged={onChanged} />;
}

function render(from: CategorySource = source()) {
  return { from, ...renderWithProviders(managerElement(from)) };
}

const nameField = (name: string) =>
  screen.getByRole('textbox', { name: `workboard.categories.name_label {"name":"${name}"}` });
const newField = () => screen.getByRole('textbox', { name: 'workboard.categories.new_label' });
const rowNames = () =>
  screen
    .getAllByRole('textbox', { name: /workboard\.categories\.name_label/ })
    .map(field => (field as HTMLInputElement).value);

beforeEach(() => {
  vi.clearAllMocks();
});

describe('what the dialog shows', () => {
  it('lists the reader’s categories in their order, each with its exact count', () => {
    render();

    expect(rowNames()).toEqual(['Maison', 'Travail', 'Santé']);
    const rows = screen.getAllByRole('listitem');
    expect(rows[0]).toHaveTextContent('workboard.board.column_count {"count":3}');
    expect(rows[1]).toHaveTextContent('workboard.board.column_count {"count":0}');
  });

  it('states how many categories are used out of the cap the server enforces', () => {
    render();

    expect(screen.getByText('workboard.categories.capacity {"used":3,"max":20}')).toBeVisible();
  });

  it('says there is none yet, and still offers to add one', () => {
    render(source({ own: [] }));

    expect(screen.getByText('workboard.categories.empty')).toBeVisible();
    expect(newField()).toBeInTheDocument();
  });

  it('does not show an empty list while the first answer is on its way', () => {
    render(source({ own: [], firstLoad: true, maxCategories: undefined }));

    expect(screen.queryByText('workboard.categories.empty')).toBeNull();
    expect(screen.queryByText(/workboard\.categories\.capacity/)).toBeNull();
  });

  it('says the list could not be read rather than « none yet »', () => {
    render(source({ own: [], error: true, maxCategories: undefined }));

    expect(screen.getByText('workboard.load_error')).toBeVisible();
    expect(screen.queryByText('workboard.categories.empty')).toBeNull();
  });
});

describe('adding a category', () => {
  it('creates it on Enter, empties the field and keeps the cursor in it', async () => {
    const { user, from } = render();

    await user.type(newField(), '  Jardin  {Enter}');

    expect(from.create).toHaveBeenCalledWith({ name: 'Jardin' });
    await waitFor(() => expect(newField()).toHaveValue(''));
    expect(newField()).toHaveFocus();
    expect(toast.success).toHaveBeenCalledWith('workboard.categories.created');
    expect(onChanged).toHaveBeenCalledTimes(1);
  });

  it('creates it from the button too', async () => {
    const { user, from } = render();

    await user.type(newField(), 'Jardin');
    await user.click(screen.getByRole('button', { name: 'workboard.categories.add' }));

    expect(from.create).toHaveBeenCalledWith({ name: 'Jardin' });
  });

  it('sends nothing for a blank name', async () => {
    const { user, from } = render();

    await user.type(newField(), '   {Enter}');
    await user.click(screen.getByRole('button', { name: 'workboard.categories.add' }));

    expect(from.create).not.toHaveBeenCalled();
  });

  it('says why a refused name was refused, and keeps what was typed', async () => {
    const create = vi
      .fn()
      .mockResolvedValue({ ok: false, errorCode: 'workboard_category_name_taken' });
    const { user } = render(source({ create }));

    await user.type(newField(), 'maison{Enter}');

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('workboard.errors.category_name_taken')
    );
    expect(newField()).toHaveValue('maison');
    expect(onChanged).not.toHaveBeenCalled();
  });

  it('explains the cap instead of sending a create the server would refuse', async () => {
    const { user, from } = render(source({ maxCategories: 3 }));

    const add = screen.getByRole('button', { name: 'workboard.categories.add' });
    // Stated, never removed: a disabled button would drop out of the tab order
    // and take the explanation with it.
    expect(add).toHaveAttribute('aria-disabled', 'true');
    expect(add).toBeEnabled();
    await user.type(newField(), 'Jardin{Enter}');

    expect(from.create).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalledWith('workboard.errors.too_many_categories');
    expect(newField()).toHaveValue('Jardin');
  });

  it('never lets a name grow past the length the server accepts', () => {
    render(source({ nameMaxChars: 12 }));

    expect(newField()).toHaveAttribute('maxlength', '12');
    expect(nameField('Maison')).toHaveAttribute('maxlength', '12');
  });
});

describe('renaming a category', () => {
  it('writes the name when the field is left, never on each key', async () => {
    const { user, from } = render();

    await user.clear(nameField('Maison'));
    await user.type(nameField('Maison'), 'Foyer');
    expect(from.update).not.toHaveBeenCalled();
    await user.tab();

    expect(from.update).toHaveBeenCalledTimes(1);
    expect(from.update).toHaveBeenCalledWith('home', { name: 'Foyer' });
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('workboard.categories.renamed'));
    expect(onChanged).toHaveBeenCalledTimes(1);
  });

  it('writes it on Enter, once — leaving the field afterwards sends nothing more', async () => {
    const { user, from } = render();

    await user.type(nameField('Travail'), ' perso{Enter}');
    await user.tab();

    expect(from.update).toHaveBeenCalledTimes(1);
    expect(from.update).toHaveBeenCalledWith('work', { name: 'Travail perso' });
  });

  it('sends nothing for a name left as it was, or blanked', async () => {
    const { user, from } = render();

    await user.click(nameField('Maison'));
    await user.tab();
    await user.clear(nameField('Travail'));
    await user.tab();

    expect(from.update).not.toHaveBeenCalled();
    // A blanked name is not a rename: the stored one comes back.
    expect(rowNames()).toEqual(['Maison', 'Travail', 'Santé']);
  });

  it('gives the stored name back when the server refuses the new one', async () => {
    const update = vi
      .fn()
      .mockResolvedValue({ ok: false, errorCode: 'workboard_category_name_taken' });
    const { user } = render(source({ update }));

    await user.clear(nameField('Maison'));
    await user.type(nameField('Maison'), 'Travail{Enter}');

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('workboard.errors.category_name_taken')
    );
    expect(rowNames()).toEqual(['Maison', 'Travail', 'Santé']);
    expect(onChanged).not.toHaveBeenCalled();
  });
});

describe('reordering', () => {
  const up = (name: string) =>
    screen.getByRole('button', { name: `workboard.categories.move_up {"name":"${name}"}` });
  const down = (name: string) =>
    screen.getByRole('button', { name: `workboard.categories.move_down {"name":"${name}"}` });

  it('asks the server for the place one step away', async () => {
    const { user, from } = render();

    await user.click(down('Maison'));
    expect(from.update).toHaveBeenLastCalledWith('home', { position: 1 });

    await user.click(up('Santé'));
    expect(from.update).toHaveBeenLastCalledWith('health', { position: 1 });
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(2));
  });

  it('does nothing at either end, and says so without removing the control', async () => {
    const { user, from } = render();

    expect(up('Maison')).toHaveAttribute('aria-disabled', 'true');
    expect(down('Santé')).toHaveAttribute('aria-disabled', 'true');
    expect(up('Maison')).toBeEnabled();
    await user.click(up('Maison'));
    await user.click(down('Santé'));

    expect(from.update).not.toHaveBeenCalled();
  });

  it('keeps the cursor on the control of the category that moved', async () => {
    const from = source();
    const { user, rerender } = renderWithProviders(managerElement(from));

    await user.click(down('Maison'));
    // The list is re-read in its new order.
    rerender(managerElement({ ...from, own: [WORK, { ...HOME, position: 1 }, HEALTH] }));

    expect(rowNames()).toEqual(['Travail', 'Maison', 'Santé']);
    expect(down('Maison')).toHaveFocus();
  });

  it('sends the writes one at a time, in the order they were asked', async () => {
    const calls: string[] = [];
    let release: (() => void) | undefined;
    const update = vi.fn((id: string) => {
      calls.push(`start ${id}`);
      return new Promise<{ ok: boolean; errorCode: null }>(resolve => {
        release = () => {
          calls.push(`end ${id}`);
          resolve(OK);
        };
      });
    });
    const { user } = render(source({ update }));

    await user.click(down('Maison'));
    await user.click(up('Santé'));
    // The second write waits for the first: two moves computed from the same
    // list must not race each other on the server.
    expect(calls).toEqual(['start home']);
    release?.();
    await waitFor(() => expect(calls).toEqual(['start home', 'end home', 'start health']));
  });
});

describe('deleting a category', () => {
  const remove = (name: string) =>
    screen.getByRole('button', { name: `workboard.categories.delete {"name":"${name}"}` });

  it('states the exact number of tickets it sends back, and deletes on confirmation', async () => {
    const { user, from } = render();

    await user.click(remove('Maison'));
    const question = await screen.findByRole('alertdialog');
    expect(question).toHaveTextContent('workboard.categories.delete_confirm_title');
    expect(question).toHaveTextContent(
      'workboard.categories.delete_confirm_body {"name":"Maison","count":3}'
    );
    expect(from.remove).not.toHaveBeenCalled();

    await user.click(within(question).getByRole('button', { name: 'workboard.card.delete' }));

    await waitFor(() => expect(from.remove).toHaveBeenCalledWith('home'));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('workboard.categories.deleted'));
    expect(onChanged).toHaveBeenCalledTimes(1);
  });

  it('says a category holds nothing rather than « 0 tickets go back »', async () => {
    const { user } = render();

    await user.click(remove('Travail'));

    expect(await screen.findByRole('alertdialog')).toHaveTextContent(
      'workboard.categories.delete_confirm_body_empty {"name":"Travail"}'
    );
  });

  it('deletes nothing when the question is dismissed', async () => {
    const { user, from } = render();

    await user.click(remove('Maison'));
    await screen.findByRole('alertdialog');
    await user.keyboard('{Escape}');

    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull());
    expect(from.remove).not.toHaveBeenCalled();
    expect(onChanged).not.toHaveBeenCalled();
  });

  it('says why a refused deletion was refused', async () => {
    const refuse = vi.fn().mockResolvedValue({ ok: false, errorCode: 'workboard_not_found' });
    const { user } = render(source({ remove: refuse }));

    await user.click(remove('Maison'));
    const question = await screen.findByRole('alertdialog');
    await user.click(within(question).getByRole('button', { name: 'workboard.card.delete' }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('workboard.errors.not_found'));
    expect(onChanged).not.toHaveBeenCalled();
  });
});

describe('closing', () => {
  it('closes from its own button', async () => {
    const { user } = render();

    await user.click(screen.getByRole('button', { name: 'workboard.actions.close' }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
