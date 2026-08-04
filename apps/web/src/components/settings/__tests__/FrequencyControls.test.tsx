/**
 * FrequencyControls — the shared min/max-per-day and hour-window pair.
 *
 * Under guard: every select carries an accessible NAME (both duplicated
 * originals shipped four anonymous comboboxes), the current values show on
 * the closed triggers (Radix dropdowns are not a jsdom surface — see
 * `ui/__tests__/select.test.tsx`), and the offered range follows `limit`.
 */

import { describe, it, expect, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { HourWindow, MinMaxPerDay } from '../FrequencyControls';

describe('MinMaxPerDay', () => {
  function setup(over: Partial<Parameters<typeof MinMaxPerDay>[0]> = {}) {
    const onChange = vi.fn();
    renderWithProviders(
      <MinMaxPerDay
        label="Frequency"
        perDayLabel="per day"
        minAriaLabel="Minimum per day"
        maxAriaLabel="Maximum per day"
        min={1}
        max={3}
        limit={8}
        onChange={onChange}
        {...over}
      />
    );
    return { onChange };
  }

  it('names both selects and shows the current values', () => {
    setup();
    expect(screen.getByRole('combobox', { name: 'Minimum per day' })).toHaveTextContent('1');
    expect(screen.getByRole('combobox', { name: 'Maximum per day' })).toHaveTextContent('3');
    expect(screen.getByText('per day')).toBeInTheDocument();
  });

  it('disables both selects together', () => {
    setup({ disabled: true });
    expect(screen.getByRole('combobox', { name: 'Minimum per day' })).toBeDisabled();
    expect(screen.getByRole('combobox', { name: 'Maximum per day' })).toBeDisabled();
  });
});

describe('HourWindow', () => {
  it('names both selects and shows the current window as HH:00', () => {
    renderWithProviders(
      <HourWindow
        label="Notification hours"
        startAriaLabel="Start hour"
        endAriaLabel="End hour"
        startHour={8}
        endHour={21}
        onChange={vi.fn()}
      />
    );
    expect(screen.getByRole('combobox', { name: 'Start hour' })).toHaveTextContent('08:00');
    expect(screen.getByRole('combobox', { name: 'End hour' })).toHaveTextContent('21:00');
  });
});
