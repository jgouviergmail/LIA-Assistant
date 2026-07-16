/**
 * Select — the closed-trigger contract of the shadcn wrapper (combobox role,
 * placeholder, disabled passthrough).
 *
 * Radix Select's open/portal interaction relies on pointer capture and layout
 * APIs that jsdom does not implement, so the meaningful, non-flaky surface here
 * is our thin wrapper's rendering of the trigger and value — not Radix's
 * dropdown behaviour.
 */

import { describe, it, expect } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
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
