/**
 * NativeSelect — the platform's list, drawn as a field: its label wired as `Input`'s is, its error
 * said and attached, and with neither the control alone for a line that holds it beside another.
 */
import { describe, expect, it, vi } from 'vitest';

import { fireEvent, renderWithProviders, screen } from '@/__tests__/test-utils';

import { NativeSelect } from '../native-select';

const CHOICES = (
  <>
    <option value="a">One</option>
    <option value="b">Two</option>
  </>
);

describe('NativeSelect', () => {
  it('is named by its label, as a field is', () => {
    renderWithProviders(<NativeSelect label="Calendar">{CHOICES}</NativeSelect>);

    expect(screen.getByRole('combobox', { name: 'Calendar' })).toBeInTheDocument();
  });

  it('reports the choice the person made', () => {
    const chosen = vi.fn();
    renderWithProviders(
      <NativeSelect
        label="Calendar"
        defaultValue="a"
        onChange={event => chosen(event.target.value)}
      >
        {CHOICES}
      </NativeSelect>
    );

    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'b' } });

    expect(chosen).toHaveBeenCalledWith('b');
  });

  it('says a refusal and attaches it to the control', () => {
    renderWithProviders(
      <NativeSelect label="Calendar" error="Pick one">
        {CHOICES}
      </NativeSelect>
    );

    const control = screen.getByRole('combobox');
    expect(control).toHaveAttribute('aria-invalid', 'true');
    expect(control).toHaveAccessibleDescription('Pick one');
  });

  it('is the control alone without a label, for a line it shares', () => {
    const { container } = renderWithProviders(
      <NativeSelect aria-label="Kind" className="w-auto">
        {CHOICES}
      </NativeSelect>
    );

    expect(container.querySelector('select')?.parentElement).toBe(container);
    expect(screen.getByRole('combobox', { name: 'Kind' })).toHaveClass('w-auto');
  });
});
