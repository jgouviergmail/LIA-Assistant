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
    renderWithProviders(<ChatShortcutsSettings lng="fr" collapsible={false} />);

    expect(screen.getByText('/meteo')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'settings.chat_shortcuts.remove' })
    ).toBeInTheDocument();
  });

  it('adds a shortcut through the full-replace save', async () => {
    useChatShortcuts.mockReturnValue(hookValue());
    const { user } = renderWithProviders(<ChatShortcutsSettings lng="fr" collapsible={false} />);

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
    const { user } = renderWithProviders(<ChatShortcutsSettings lng="fr" collapsible={false} />);

    await user.type(screen.getByLabelText('settings.chat_shortcuts.id_label'), 'weather');
    await user.type(screen.getByLabelText('settings.chat_shortcuts.text_label'), 'x');
    await user.click(screen.getByRole('button', { name: 'settings.chat_shortcuts.add' }));

    expect(screen.getByRole('alert')).toHaveTextContent('settings.chat_shortcuts.error_reserved');
    expect(save).not.toHaveBeenCalled();
  });

  it('removes a shortcut through the full-replace save', async () => {
    useChatShortcuts.mockReturnValue(hookValue());
    const { user } = renderWithProviders(<ChatShortcutsSettings lng="fr" collapsible={false} />);

    await user.click(screen.getByRole('button', { name: 'settings.chat_shortcuts.remove' }));

    expect(save).toHaveBeenCalledWith([]);
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
    renderWithProviders(<ChatShortcutsSettings lng="fr" collapsible={false} />);

    expect(screen.getByRole('status')).toHaveTextContent('settings.chat_shortcuts.limit_reached');
    expect(
      screen.queryByRole('button', { name: 'settings.chat_shortcuts.add' })
    ).not.toBeInTheDocument();
  });
});
