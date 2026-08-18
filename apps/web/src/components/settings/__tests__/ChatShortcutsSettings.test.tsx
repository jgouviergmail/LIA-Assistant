/**
 * ChatShortcutsSettings — CRUD of the user's own /shortcuts (SLASH admin lot).
 *
 * What must hold:
 *  - the pure validator refuses exactly what the backend refuses PLUS the
 *    frontend-owned reserved ids (statics) — the one rule the server cannot
 *    know;
 *  - refusals surface as inline role=alert text, and nothing is saved;
 *  - adding and removing go through the full-replace `save`;
 *  - at capacity the form yields to a plain explanation.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

const { useChatShortcuts, save } = vi.hoisted(() => ({
  useChatShortcuts: vi.fn(),
  save: vi.fn(),
}));

vi.mock('@/hooks/useChatShortcuts', () => ({ useChatShortcuts }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { validateShortcutId } from '@/lib/slash-commands';

import { ChatShortcutsSettings } from '../ChatShortcutsSettings';

function hookValue(overrides: Record<string, unknown> = {}) {
  return {
    shortcuts: [{ id: 'meteo', text: 'Quelle est la météo ?' }],
    maxCount: 3,
    loading: false,
    error: false,
    save,
    saving: false,
    ...overrides,
  };
}

beforeEach(() => {
  save.mockReset();
  save.mockResolvedValue(true);
});

const MAX_ID = 32;

/** Render with the default single-shortcut hook value. */
function useChatShortcutsMock() {
  useChatShortcuts.mockReturnValue(hookValue());
  renderWithProviders(<ChatShortcutsSettings lng="fr" />);
}

describe('validateShortcutId (pure)', () => {
  it('accepts a fresh valid slug', () => {
    expect(validateShortcutId('meteo-eze', ['other'], MAX_ID)).toBeNull();
  });

  it.each(['Meteo', '-x', 'x-', 'a b', 'é', 'a:b'])('refuses malformed id %s', id => {
    expect(validateShortcutId(id, [], MAX_ID)).toBe('invalid_id');
  });

  it('refuses an id over the length cap', () => {
    expect(validateShortcutId('x'.repeat(MAX_ID + 1), [], MAX_ID)).toBe('invalid_id');
  });

  it('refuses the static command ids — the registry the backend does not know', () => {
    expect(validateShortcutId('weather', [], MAX_ID)).toBe('reserved');
    expect(validateShortcutId('resume', [], MAX_ID)).toBe('reserved');
  });

  it('refuses an id the user already has', () => {
    expect(validateShortcutId('mine', ['mine'], MAX_ID)).toBe('duplicate');
  });
});

describe('ChatShortcutsSettings', () => {
  it('lists the existing shortcuts with a named remove button', () => {
    useChatShortcuts.mockReturnValue(hookValue());
    renderWithProviders(<ChatShortcutsSettings lng="fr" />);

    expect(screen.getByText('/meteo')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'settings.chat_shortcuts.remove' })
    ).toBeInTheDocument();
  });

  it('adds a shortcut through the full-replace save', async () => {
    useChatShortcuts.mockReturnValue(hookValue());
    const { user } = renderWithProviders(<ChatShortcutsSettings lng="fr" />);

    await user.type(screen.getByLabelText('settings.chat_shortcuts.id_label'), 'courses');
    await user.type(
      screen.getByLabelText('settings.chat_shortcuts.text_label'),
      'Ajoute à ma liste de courses : '
    );
    await user.click(screen.getByRole('button', { name: 'settings.chat_shortcuts.add' }));

    expect(save).toHaveBeenCalledWith([
      { id: 'meteo', text: 'Quelle est la météo ?' },
      { id: 'courses', text: 'Ajoute à ma liste de courses :' },
    ]);
  });

  it('refuses a reserved id inline and saves nothing', async () => {
    useChatShortcuts.mockReturnValue(hookValue());
    const { user } = renderWithProviders(<ChatShortcutsSettings lng="fr" />);

    await user.type(screen.getByLabelText('settings.chat_shortcuts.id_label'), 'weather');
    await user.type(screen.getByLabelText('settings.chat_shortcuts.text_label'), 'x');
    await user.click(screen.getByRole('button', { name: 'settings.chat_shortcuts.add' }));

    expect(screen.getByRole('alert')).toHaveTextContent('settings.chat_shortcuts.error_reserved');
    expect(save).not.toHaveBeenCalled();
  });

  it('removes a shortcut through the full-replace save', async () => {
    useChatShortcuts.mockReturnValue(hookValue());
    const { user } = renderWithProviders(<ChatShortcutsSettings lng="fr" />);

    await user.click(screen.getByRole('button', { name: 'settings.chat_shortcuts.remove' }));

    expect(save).toHaveBeenCalledWith([]);
  });

  it('parks focus on the section after a removal — never on <body>', async () => {
    // The delete button vanishes with its row, so without a deliberate
    // destination the browser drops focus to <body> and a keyboard user
    // restarts from the top of the settings page. A focus oracle, not a
    // snapshot: this regression is invisible to rendered-output assertions.
    useChatShortcuts.mockReturnValue(hookValue());
    const { user } = renderWithProviders(<ChatShortcutsSettings lng="fr" />);

    await user.click(screen.getByRole('button', { name: 'settings.chat_shortcuts.remove' }));

    expect(document.activeElement).not.toBe(document.body);
  });

  it('colour-codes the row actions: delete carries its red at rest', () => {
    // The passkeys pattern (ADR-207): the destructive row action is tinted
    // before the pointer reaches it — a colour revealed only on hover is not
    // a code.
    useChatShortcutsMock();
    const remove = screen.getByRole('button', { name: 'settings.chat_shortcuts.remove' });
    const edit = screen.getByRole('button', { name: 'settings.chat_shortcuts.edit' });
    expect(remove.className).toContain('text-destructive');
    expect(edit.className).not.toContain('text-destructive');
  });

  it('replaces the form with an explanation at capacity', () => {
    useChatShortcuts.mockReturnValue(
      hookValue({
        shortcuts: [
          { id: 'a', text: '1' },
          { id: 'b', text: '2' },
          { id: 'c', text: '3' },
        ],
      })
    );
    renderWithProviders(<ChatShortcutsSettings lng="fr" />);

    expect(screen.getByRole('status')).toHaveTextContent('settings.chat_shortcuts.limit_reached');
    expect(
      screen.queryByRole('button', { name: 'settings.chat_shortcuts.add' })
    ).not.toBeInTheDocument();
  });
});

describe('ChatShortcutsSettings — editing an existing shortcut', () => {
  /** Enter edit mode on the single seeded shortcut. */
  async function openEditor() {
    useChatShortcuts.mockReturnValue(hookValue());
    const rendered = renderWithProviders(<ChatShortcutsSettings lng="fr" />);
    await rendered.user.click(screen.getByRole('button', { name: 'settings.chat_shortcuts.edit' }));
    return rendered;
  }

  it('opens an editor pre-filled with the current values', async () => {
    await openEditor();

    expect(
      screen.getByRole('textbox', { name: 'settings.chat_shortcuts.edit_id_label' })
    ).toHaveValue('meteo');
    expect(
      screen.getByRole('textbox', { name: 'settings.chat_shortcuts.edit_text_label' })
    ).toHaveValue('Quelle est la météo ?');
  });

  it('saves the edited text through the full-replace save', async () => {
    const { user } = await openEditor();

    const text = screen.getByRole('textbox', { name: 'settings.chat_shortcuts.edit_text_label' });
    await user.clear(text);
    await user.type(text, 'Météo à Paris ?');
    await user.click(screen.getByRole('button', { name: /settings.chat_shortcuts.save/ }));

    expect(save).toHaveBeenCalledWith([{ id: 'meteo', text: 'Météo à Paris ?' }]);
  });

  it('renames the shortcut when the id changes', async () => {
    const { user } = await openEditor();

    const id = screen.getByRole('textbox', { name: 'settings.chat_shortcuts.edit_id_label' });
    await user.clear(id);
    await user.type(id, 'meteo-maison');
    await user.click(screen.getByRole('button', { name: /settings.chat_shortcuts.save/ }));

    expect(save).toHaveBeenCalledWith([{ id: 'meteo-maison', text: 'Quelle est la météo ?' }]);
  });

  it('does not collide with itself when only the text changes', async () => {
    // The duplicate check must exclude the shortcut under edit, or saving an
    // untouched id would be refused as a duplicate of itself.
    const { user } = await openEditor();

    const text = screen.getByRole('textbox', { name: 'settings.chat_shortcuts.edit_text_label' });
    await user.type(text, ' bis');
    await user.click(screen.getByRole('button', { name: /settings.chat_shortcuts.save/ }));

    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(save).toHaveBeenCalled();
  });

  it('refuses a rename onto another existing shortcut', async () => {
    useChatShortcuts.mockReturnValue(
      hookValue({
        shortcuts: [
          { id: 'meteo', text: 'A' },
          { id: 'courses', text: 'B' },
        ],
      })
    );
    const { user } = renderWithProviders(<ChatShortcutsSettings lng="fr" />);
    await user.click(screen.getAllByRole('button', { name: 'settings.chat_shortcuts.edit' })[0]!);

    const id = screen.getByRole('textbox', { name: 'settings.chat_shortcuts.edit_id_label' });
    await user.clear(id);
    await user.type(id, 'courses');
    await user.click(screen.getByRole('button', { name: /settings.chat_shortcuts.save/ }));

    expect(screen.getByRole('alert')).toHaveTextContent('error_duplicate');
    expect(save).not.toHaveBeenCalled();
  });

  it('refuses a rename onto a reserved static command', async () => {
    const { user } = await openEditor();

    const id = screen.getByRole('textbox', { name: 'settings.chat_shortcuts.edit_id_label' });
    await user.clear(id);
    await user.type(id, 'weather');
    await user.click(screen.getByRole('button', { name: /settings.chat_shortcuts.save/ }));

    expect(screen.getByRole('alert')).toHaveTextContent('error_reserved');
    expect(save).not.toHaveBeenCalled();
  });

  it('cancels without saving and restores the read row', async () => {
    const { user } = await openEditor();

    const text = screen.getByRole('textbox', { name: 'settings.chat_shortcuts.edit_text_label' });
    await user.clear(text);
    await user.type(text, 'jeté');
    await user.click(screen.getByRole('button', { name: /settings.chat_shortcuts.cancel/ }));

    expect(save).not.toHaveBeenCalled();
    expect(
      screen.getByRole('button', { name: 'settings.chat_shortcuts.edit' })
    ).toBeInTheDocument();
  });

  it('blocks saving an emptied field', async () => {
    const { user } = await openEditor();

    await user.clear(
      screen.getByRole('textbox', { name: 'settings.chat_shortcuts.edit_text_label' })
    );

    expect(screen.getByRole('button', { name: /settings.chat_shortcuts.save/ })).toBeDisabled();
  });
});
