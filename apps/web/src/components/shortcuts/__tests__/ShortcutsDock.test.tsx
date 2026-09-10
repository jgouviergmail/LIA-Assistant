/**
 * ShortcutsDock (ADR-277) — one link per pinned section the account can
 * open, nothing without one, folds and moves like the eyes.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

const account = vi.hoisted(() => ({
  user: null as null | { id: string; is_superuser: boolean; settings_shortcuts?: string[] },
}));
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: account.user, refreshUser: vi.fn() }),
}));

import { ShortcutsDock } from '@/components/shortcuts/ShortcutsDock';
import { SHORTCUTS_DOCK_PREFS_KEY } from '@/lib/constants';
import { useShortcutsDockStore } from '@/stores/shortcutsDockStore';

const dock = () => screen.getByRole('navigation', { name: 'shortcuts_dock.label' });

beforeEach(() => {
  localStorage.removeItem(SHORTCUTS_DOCK_PREFS_KEY);
  useShortcutsDockStore.getState().reset();
  account.user = { id: 'me', is_superuser: false, settings_shortcuts: ['theme', 'font'] };
});

describe('ShortcutsDock', () => {
  it('renders nothing without a pinned section', () => {
    account.user = { id: 'me', is_superuser: false, settings_shortcuts: [] };
    const { container } = render(<ShortcutsDock lng="fr" />);

    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing for a visitor', () => {
    account.user = null;
    const { container } = render(<ShortcutsDock lng="fr" />);

    expect(container).toBeEmptyDOMElement();
  });

  it('draws one link per known pinned section, in order, to its deep link', () => {
    account.user = {
      id: 'me',
      is_superuser: false,
      settings_shortcuts: ['theme', 'gone-section', 'font', 'my-shortcuts'],
    };
    render(<ShortcutsDock lng="fr" />);

    const links = screen.getAllByRole('link');
    expect(links.map(link => link.getAttribute('href'))).toEqual([
      '/fr/dashboard/settings?section=theme',
      '/fr/dashboard/settings?section=font',
    ]);
    // Named after the section, for a reader who cannot see the icon.
    expect(links[0]).toHaveAccessibleName('settings.theme.title');
  });

  it('drops an administration section for a non-superuser and keeps it for one', () => {
    account.user = { id: 'me', is_superuser: false, settings_shortcuts: ['admin-users', 'theme'] };
    const { unmount } = render(<ShortcutsDock lng="fr" />);
    expect(screen.getAllByRole('link')).toHaveLength(1);
    unmount();

    account.user = { id: 'me', is_superuser: true, settings_shortcuts: ['admin-users', 'theme'] };
    render(<ShortcutsDock lng="fr" />);
    expect(screen.getAllByRole('link')).toHaveLength(2);
  });

  it('folds into a restore button, and unfolds', () => {
    render(<ShortcutsDock lng="fr" />);

    fireEvent.click(screen.getByRole('button', { name: 'shortcuts_dock.minimize' }));

    expect(screen.queryByRole('navigation')).toBeNull();
    expect(useShortcutsDockStore.getState().minimized).toBe(true);

    fireEvent.click(screen.getByRole('button', { name: 'shortcuts_dock.restore' }));

    expect(dock()).toBeInTheDocument();
    expect(useShortcutsDockStore.getState().minimized).toBe(false);
  });

  it('a drag commits the spot to the device store', () => {
    render(<ShortcutsDock lng="fr" />);
    const surface = dock();

    fireEvent.pointerDown(surface, { pointerId: 1, clientX: 100, clientY: 100 });
    fireEvent.pointerMove(surface, { pointerId: 1, clientX: 160, clientY: 140 });
    fireEvent.pointerUp(surface, { pointerId: 1, clientX: 160, clientY: 140 });

    const { position } = useShortcutsDockStore.getState();
    expect(position).not.toBeNull();
    expect(position?.xPct).toBeCloseTo((60 / window.innerWidth) * 100, 5);
    expect(position?.yPct).toBeCloseTo((40 / window.innerHeight) * 100, 5);
  });

  it('is movable by the keyboard from the capsule itself', () => {
    render(<ShortcutsDock lng="fr" />);

    fireEvent.keyDown(dock(), { key: 'ArrowLeft' });

    // Already at the left edge in jsdom's layout: clamped, never negative.
    expect(useShortcutsDockStore.getState().position).toEqual({ xPct: 0, yPct: 0 });
  });
});

describe('ShortcutsDock — folded, it still moves (2026-09-10)', () => {
  it('the fold button sits above the first shortcut', () => {
    render(<ShortcutsDock lng="fr" />);

    const fold = screen.getByRole('button', { name: 'shortcuts_dock.minimize' });
    const first = screen.getAllByRole('link')[0];
    expect(fold.compareDocumentPosition(first) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('the folded dock can be dragged, and the drop does not unfold it', () => {
    useShortcutsDockStore.getState().setMinimized(true);
    render(<ShortcutsDock lng="fr" />);
    const dot = screen.getByRole('button', { name: 'shortcuts_dock.restore' });

    fireEvent.pointerDown(dot, { pointerId: 1, clientX: 100, clientY: 100 });
    fireEvent.pointerMove(dot, { pointerId: 1, clientX: 160, clientY: 140 });
    fireEvent.pointerUp(dot, { pointerId: 1, clientX: 160, clientY: 140 });
    fireEvent.click(dot);

    expect(useShortcutsDockStore.getState().position).not.toBeNull();
    expect(useShortcutsDockStore.getState().minimized).toBe(true);
  });

  it('a plain click on the folded dock unfolds it', () => {
    useShortcutsDockStore.getState().setMinimized(true);
    render(<ShortcutsDock lng="fr" />);

    fireEvent.click(screen.getByRole('button', { name: 'shortcuts_dock.restore' }));

    expect(useShortcutsDockStore.getState().minimized).toBe(false);
  });
});

describe('ShortcutsDock — it unfolds towards the room it has (2026-09-10)', () => {
  it("grows upward from the lower half, its foot where the button's foot was", () => {
    useShortcutsDockStore.getState().setPosition({ xPct: 90, yPct: 80 });
    useShortcutsDockStore.getState().setMinimized(true);
    render(<ShortcutsDock lng="fr" />);

    fireEvent.click(screen.getByRole('button', { name: 'shortcuts_dock.restore' }));

    const capsule = dock();
    expect(capsule.style.bottom).toMatch(/^calc\((100% - 80%|20%) - 44px\)$/);
    expect(capsule.style.top).toBe('');
    // The stored spot is untouched: folding again puts the button back.
    expect(useShortcutsDockStore.getState().position).toEqual({ xPct: 90, yPct: 80 });
  });

  it('grows downward from the upper half', () => {
    useShortcutsDockStore.getState().setPosition({ xPct: 90, yPct: 20 });
    useShortcutsDockStore.getState().setMinimized(true);
    render(<ShortcutsDock lng="fr" />);

    fireEvent.click(screen.getByRole('button', { name: 'shortcuts_dock.restore' }));

    expect(dock().style.top).toBe('20%');
    expect(dock().style.bottom).toBe('');
  });

  it('a capsule grown upward and then dragged stays where it was dropped', () => {
    useShortcutsDockStore.getState().setPosition({ xPct: 90, yPct: 80 });
    useShortcutsDockStore.getState().setMinimized(true);
    render(<ShortcutsDock lng="fr" />);
    fireEvent.click(screen.getByRole('button', { name: 'shortcuts_dock.restore' }));
    const capsule = dock();

    fireEvent.pointerDown(capsule, { pointerId: 1, clientX: 100, clientY: 100 });
    fireEvent.pointerMove(capsule, { pointerId: 1, clientX: 160, clientY: 140 });
    fireEvent.pointerUp(capsule, { pointerId: 1, clientX: 160, clientY: 140 });

    // Committed as a TOP — the capsule's real one — and drawn from it.
    expect(dock().style.top).not.toBe('');
    expect(dock().style.bottom).toBe('');
  });
});
