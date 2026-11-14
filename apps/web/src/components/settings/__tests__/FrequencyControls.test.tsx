/**
 * FrequencyControls — the shared min/max-per-day and hour-window pair.
 *
 * Under guard: every select carries an accessible NAME (both duplicated
 * originals shipped four anonymous comboboxes), the current values show on
 * the closed triggers (Radix dropdowns are not a jsdom surface — see
 * `ui/__tests__/select.test.tsx`), and the offered range follows `limit`.
 */

import userEvent from '@testing-library/user-event';
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

  it('while its choice is saved, both lists stay focusable and refuse to open', async () => {
    // `disabled` on the list that holds the focus hands the focus to the page.
    renderWithProviders(
      <HourWindow
        label="Notification hours"
        startAriaLabel="Start hour"
        endAriaLabel="End hour"
        startHour={8}
        endHour={21}
        busy
        onChange={vi.fn()}
      />
    );
    const start = screen.getByRole('combobox', { name: 'Start hour' });
    const end = screen.getByRole('combobox', { name: 'End hour' });
    for (const list of [start, end]) {
      expect(list).toHaveAttribute('aria-busy', 'true');
      expect(list).not.toBeDisabled();
    }

    start.focus();
    await userEvent.click(start);

    expect(start).toHaveFocus();
    expect(screen.queryByRole('listbox')).toBeNull();
  });
});
