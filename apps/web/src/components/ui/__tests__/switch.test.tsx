/**
 * Switch — the `busy` mode a switch takes while its own change (or its section's) is saved.
 *
 * A busy switch must never be `disabled`: the browser throws the keyboard focus of a
 * control that becomes disabled to `<body>` (measured 2026-11-13). jsdom does not apply
 * that rule, so the focus itself is proven in a real browser
 * (`e2e/smoke/save-keeps-focus.spec.ts`); here, what the wrapper decides.
 */

import { useState } from 'react';
import { describe, it, expect, vi } from 'vitest';

import { renderWithProviders, screen, userEvent } from '@/__tests__/test-utils';
import { Switch } from '../switch';

/** A switch that saves its own change: busy from the toggle until the save answers. */
function SavingSwitch({ save }: { save: (value: boolean) => Promise<void> }) {
  const [checked, setChecked] = useState(false);
  const [saving, setSaving] = useState(false);
  return (
    <Switch
      aria-label="Notifications"
      checked={checked}
      busy={saving}
      onCheckedChange={async value => {
        setSaving(true);
        await save(value);
        setChecked(value);
        setSaving(false);
      }}
    />
  );
}

describe('Switch (busy while a save is on its way)', () => {
  it('stays focusable and says it is busy, never disabled', () => {
    renderWithProviders(<Switch aria-label="Notifications" checked={false} busy />);
    const toggle = screen.getByRole('switch', { name: 'Notifications' });
    expect(toggle).not.toBeDisabled();
    expect(toggle).toHaveAttribute('aria-busy', 'true');
    expect(toggle).toHaveAttribute('aria-disabled', 'true');
    toggle.focus();
    expect(toggle).toHaveFocus();
  });

  it('ignores a toggle by pointer or by keyboard, and still runs the caller’s click', async () => {
    const onCheckedChange = vi.fn();
    const onClick = vi.fn();
    renderWithProviders(
      <Switch
        aria-label="Notifications"
        checked={false}
        busy
        onCheckedChange={onCheckedChange}
        onClick={onClick}
      />
    );
    const toggle = screen.getByRole('switch', { name: 'Notifications' });
    await userEvent.click(toggle);
    toggle.focus();
    await userEvent.keyboard(' ');
    expect(onCheckedChange).not.toHaveBeenCalled();
    expect(toggle).toHaveAttribute('aria-checked', 'false');
    expect(onClick).toHaveBeenCalledTimes(2);
  });

  it('toggles as any switch once nothing is being saved', async () => {
    const onCheckedChange = vi.fn();
    renderWithProviders(
      <Switch aria-label="Notifications" checked={false} onCheckedChange={onCheckedChange} />
    );
    const toggle = screen.getByRole('switch', { name: 'Notifications' });
    expect(toggle).not.toHaveAttribute('aria-busy');
    expect(toggle).not.toHaveAttribute('aria-disabled');
    await userEvent.click(toggle);
    expect(onCheckedChange).toHaveBeenCalledWith(true);
  });

  it('keeps its own disabled for what cannot be switched at all', () => {
    renderWithProviders(<Switch aria-label="Notifications" checked={false} disabled />);
    expect(screen.getByRole('switch', { name: 'Notifications' })).toBeDisabled();
  });

  it('stays enabled through the save its toggle started', async () => {
    let answer!: () => void;
    const save = vi.fn(() => new Promise<void>(resolve => (answer = resolve)));
    renderWithProviders(<SavingSwitch save={save} />);
    const toggle = screen.getByRole('switch', { name: 'Notifications' });
    await userEvent.click(toggle);

    expect(save).toHaveBeenCalledWith(true);
    expect(toggle).toHaveAttribute('aria-busy', 'true');
    expect(toggle).not.toBeDisabled();
    await userEvent.click(toggle);
    expect(save).toHaveBeenCalledTimes(1);

    answer();
    await vi.waitFor(() => expect(toggle).toHaveAttribute('aria-checked', 'true'));
    expect(toggle).not.toHaveAttribute('aria-busy');
  });
});
