/**
 * Select — the closed-trigger contract of the shadcn wrapper (combobox role,
 * placeholder, disabled passthrough), and the `busy` mode a list takes while its
 * own choice is being saved.
 *
 * A busy list must never be `disabled`: the browser throws the keyboard focus of a
 * trigger that becomes disabled to `<body>` (measured 2026-11-13). jsdom does not
 * apply that rule, so the focus itself is proven in a real browser
 * (`e2e/smoke/save-keeps-focus.spec.ts`); here, what the wrapper decides.
 */

import { useState } from 'react';
import { describe, it, expect, vi } from 'vitest';

import { renderWithProviders, screen, userEvent } from '@/__tests__/test-utils';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '../select';

function build(props: { disabled?: boolean; defaultValue?: string } = {}) {
  return (
    <Select disabled={props.disabled} defaultValue={props.defaultValue}>
      <SelectTrigger aria-label="Fruit">
        <SelectValue placeholder="Pick a fruit" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="apple">Apple</SelectItem>
        <SelectItem value="banana">Banana</SelectItem>
      </SelectContent>
    </Select>
  );
}

describe('Select (closed trigger)', () => {
  it('renders the trigger as a combobox labelled and collapsed', () => {
    renderWithProviders(build());
    const trigger = screen.getByRole('combobox', { name: 'Fruit' });
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
  });

  it('shows the placeholder when nothing is selected', () => {
    renderWithProviders(build());
    expect(screen.getByText('Pick a fruit')).toBeInTheDocument();
  });

  it('disables the trigger when the select is disabled', () => {
    renderWithProviders(build({ disabled: true }));
    expect(screen.getByRole('combobox', { name: 'Fruit' })).toBeDisabled();
  });

});

function busyList(busy: boolean, onValueChange = vi.fn()) {
  return (
    <Select value="apple" onValueChange={onValueChange} busy={busy}>
      <SelectTrigger aria-label="Fruit">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="apple">Apple</SelectItem>
        <SelectItem value="banana">Banana</SelectItem>
      </SelectContent>
    </Select>
  );
}

/** A list that saves its own choice: busy from the choice until the save answers. */
function SavingList({ save }: { save: (value: string) => Promise<void> }) {
  const [value, setValue] = useState('apple');
  const [saving, setSaving] = useState(false);
  return (
    <Select
      value={value}
      busy={saving}
      onValueChange={async next => {
        setSaving(true);
        await save(next);
        setValue(next);
        setSaving(false);
      }}
    >
      <SelectTrigger aria-label="Fruit">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="apple">Apple</SelectItem>
        <SelectItem value="banana">Banana</SelectItem>
      </SelectContent>
    </Select>
  );
}

describe('Select (busy while its own choice is saved)', () => {
  it('stays focusable and says it is busy, never disabled', () => {
    renderWithProviders(busyList(true));
    const trigger = screen.getByRole('combobox', { name: 'Fruit' });
    expect(trigger).not.toBeDisabled();
    expect(trigger).toHaveAttribute('aria-busy', 'true');
    expect(trigger).toHaveAttribute('aria-disabled', 'true');
    trigger.focus();
    expect(trigger).toHaveFocus();
  });

  it('does not open, by pointer or by keyboard, and ignores a typed choice', async () => {
    const onValueChange = vi.fn();
    renderWithProviders(busyList(true, onValueChange));
    const trigger = screen.getByRole('combobox', { name: 'Fruit' });
    await userEvent.click(trigger);
    trigger.focus();
    await userEvent.keyboard('{Enter}{ArrowDown}b');
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('listbox')).toBeNull();
    expect(onValueChange).not.toHaveBeenCalled();
  });

  it('opens and chooses as any list once nothing is being saved', async () => {
    const onValueChange = vi.fn();
    renderWithProviders(busyList(false, onValueChange));
    const trigger = screen.getByRole('combobox', { name: 'Fruit' });
    expect(trigger).not.toHaveAttribute('aria-busy');
    expect(trigger).not.toHaveAttribute('aria-disabled');
    await userEvent.click(trigger);
    await userEvent.click(await screen.findByRole('option', { name: 'Banana' }));
    expect(onValueChange).toHaveBeenCalledWith('banana');
  });

  it('keeps its trigger enabled through the save its choice started', async () => {
    let answer!: () => void;
    const save = vi.fn(() => new Promise<void>(resolve => (answer = resolve)));
    renderWithProviders(<SavingList save={save} />);
    const trigger = screen.getByRole('combobox', { name: 'Fruit' });
    await userEvent.click(trigger);
    await userEvent.click(await screen.findByRole('option', { name: 'Banana' }));

    expect(save).toHaveBeenCalledWith('banana');
    expect(trigger).toHaveAttribute('aria-busy', 'true');
    expect(trigger).not.toBeDisabled();

    answer();
    await screen.findByText('Banana');
    expect(trigger).not.toHaveAttribute('aria-busy');
  });
});
