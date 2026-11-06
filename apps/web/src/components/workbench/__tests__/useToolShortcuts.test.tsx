/**
 * The tools' keyboard shortcuts (ADR-369, lot 2).
 *
 * One letter acts, so they listen only where a person is not typing, stay out of
 * what a dialog is doing, leave the browser's own chords alone, and can be
 * switched off (WCAG 2.1.4), which the help says and does.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { fireEvent, renderWithProviders, screen } from '@/__tests__/test-utils';

import { ShortcutsHelp } from '../ShortcutsHelp';
import { useToolShortcuts, type ToolShortcut } from '../useToolShortcuts';

const ACTION = vi.fn();
const SHORTCUTS: readonly ToolShortcut[] = [
  { key: 'n', labelKey: 'workbench.shortcuts.new', run: ACTION },
];

function Screen({ shortcuts = SHORTCUTS }: { shortcuts?: readonly ToolShortcut[] }) {
  useToolShortcuts(shortcuts);
  return (
    <>
      <input aria-label="field" />
      <textarea aria-label="area" />
      <div role="dialog" aria-label="window">
        <button type="button">inside</button>
      </div>
      <div contentEditable aria-label="rich" />
    </>
  );
}

function press(key: string, target: Element | Window = window, init: KeyboardEventInit = {}) {
  fireEvent.keyDown(target, { key, ...init });
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
});

afterEach(() => window.localStorage.clear());

describe('useToolShortcuts', () => {
  it('runs what the key names', () => {
    renderWithProviders(<Screen />);

    press('n');

    expect(ACTION).toHaveBeenCalledOnce();
  });

  it('runs nothing for a key held down', () => {
    renderWithProviders(<Screen />);

    press('n', window, { repeat: true });

    expect(ACTION).not.toHaveBeenCalled();
  });

  it.each(['field', 'area', 'rich'])('leaves a person typing in %s alone', name => {
    renderWithProviders(<Screen />);

    press('n', screen.getByLabelText(name));

    expect(ACTION).not.toHaveBeenCalled();
  });

  it('stays out of what a dialog is doing', () => {
    renderWithProviders(<Screen />);

    press('n', screen.getByRole('button', { name: 'inside' }));

    expect(ACTION).not.toHaveBeenCalled();
  });

  it.each([{ ctrlKey: true }, { metaKey: true }, { altKey: true }])(
    'leaves the browser its own chords: %o',
    chord => {
      renderWithProviders(<Screen />);

      press('n', window, chord);

      expect(ACTION).not.toHaveBeenCalled();
    }
  );

  it('takes a key Shift makes, as the keyboard spells it', () => {
    const run = vi.fn();
    renderWithProviders(
      <Screen shortcuts={[{ key: '#', labelKey: 'workbench.shortcuts.trash', run }]} />
    );

    press('#', window, { shiftKey: true });

    expect(run).toHaveBeenCalledOnce();
  });

  it('runs nothing once switched off on this device', () => {
    window.localStorage.setItem('lia_workbench_shortcuts', 'off');
    renderWithProviders(<Screen />);

    press('n');

    expect(ACTION).not.toHaveBeenCalled();
  });

  it('stops listening with its screen', () => {
    const { unmount } = renderWithProviders(<Screen />);

    unmount();
    press('n');

    expect(ACTION).not.toHaveBeenCalled();
  });
});

describe('ShortcutsHelp', () => {
  const help = () => renderWithProviders(<ShortcutsHelp lng="en" shortcuts={SHORTCUTS} />);

  it('opens on « ? » and lists what this tool answers', () => {
    help();

    press('?', window, { shiftKey: true });

    expect(screen.getByRole('dialog')).toHaveTextContent('workbench.shortcuts.new');
  });

  it('opens from its button, a way that needs no letter', async () => {
    const { user } = help();

    await user.click(screen.getByRole('button', { name: 'workbench.shortcuts.title' }));

    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('switches them off, and « ? » with them', async () => {
    const { user } = help();
    await user.click(screen.getByRole('button', { name: 'workbench.shortcuts.title' }));

    await user.click(screen.getByRole('switch', { name: 'workbench.shortcuts.enabled' }));
    await user.keyboard('{Escape}');
    press('?', window, { shiftKey: true });

    expect(window.localStorage.getItem('lia_workbench_shortcuts')).toBe('off');
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('switches them back on', async () => {
    window.localStorage.setItem('lia_workbench_shortcuts', 'off');
    const { user } = help();
    await user.click(screen.getByRole('button', { name: 'workbench.shortcuts.title' }));

    await user.click(screen.getByRole('switch', { name: 'workbench.shortcuts.enabled' }));

    expect(window.localStorage.getItem('lia_workbench_shortcuts')).toBe('on');
  });
});
