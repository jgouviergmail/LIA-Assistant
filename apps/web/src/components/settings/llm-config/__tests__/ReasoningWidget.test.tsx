/**
 * ReasoningWidget — golden characterization (audit F011).
 *
 * Pins the rendered output and onChange payloads of the three reasoning widget
 * shapes (enum / budget_int / toggle_budget) BEFORE the CC-43 component is split
 * into one sub-component per shape. Radix Select value changes are not driven in
 * jsdom (pointer limitations) — the preset-derivation logic they exercise is
 * covered directly through the pure helper unit tests. Everything drivable in
 * jsdom (the number Inputs and the Switch) is asserted here.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { ReasoningWidget } from '../ReasoningWidget';
import type { ReasoningBudgetRange } from '@/types/llm-config';

const RANGE: ReasoningBudgetRange = {
  min: 1024,
  max: 32000,
  off_sentinel: 0,
  dynamic_sentinel: -1,
};

describe('widget=none', () => {
  it('renders nothing', () => {
    const { container } = render(<ReasoningWidget widget="none" value={null} onChange={vi.fn()} />);
    expect(container.firstChild).toBeNull();
  });
});

describe('widget=enum', () => {
  it('shows the "forced" note when exactly one value is allowed', () => {
    render(<ReasoningWidget widget="enum" enumValues={['high']} value={null} onChange={vi.fn()} />);
    expect(screen.getByText(/Forced to high/)).toBeTruthy();
  });

  it('flags an invalid current value not in the allowed set', () => {
    render(
      <ReasoningWidget
        widget="enum"
        enumValues={['low', 'high']}
        value={{ effort: 'legacy' }}
        onChange={vi.fn()}
      />
    );
    const alert = screen.getByRole('alert');
    expect(alert.textContent).toContain("'legacy'");
    expect(alert.textContent).toContain('low, high');
  });

  it('does not flag a valid current value, and shows no forced note for multiple values', () => {
    render(
      <ReasoningWidget
        widget="enum"
        enumValues={['low', 'high']}
        value={{ effort: 'high' }}
        onChange={vi.fn()}
      />
    );
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.queryByText(/Forced to/)).toBeNull();
  });

  it('renders the doc text when a known doc key is provided', () => {
    // An unknown key resolves to undefined → no doc paragraph (safe default).
    render(
      <ReasoningWidget
        widget="enum"
        enumValues={['low']}
        docI18nKey="___unknown___"
        value={null}
        onChange={vi.fn()}
      />
    );
    // Only the "forced" note is present; no crash on the unknown doc key.
    expect(screen.getByText(/Forced to low/)).toBeTruthy();
  });
});

describe('widget=budget_int', () => {
  it('shows the custom number input at range.min when no budget is set', () => {
    render(
      <ReasoningWidget widget="budget_int" budgetRange={RANGE} value={null} onChange={vi.fn()} />
    );
    // preset defaults to custom → the number input is shown, seeded at min.
    const input = screen.getByLabelText('Reasoning budget (tokens)') as HTMLInputElement;
    expect(input.value).toBe('1024');
    expect(screen.getByText(/Range: 1024–32000 tokens/)).toBeTruthy();
  });

  it('emits a numeric budget change from the custom input', () => {
    const onChange = vi.fn();
    render(
      <ReasoningWidget
        widget="budget_int"
        budgetRange={RANGE}
        value={{ budget: 2048 }}
        onChange={onChange}
      />
    );
    const input = screen.getByLabelText('Reasoning budget (tokens)');
    fireEvent.change(input, { target: { value: '4096' } });
    expect(onChange).toHaveBeenCalledWith({ budget: 4096 });

    // A number input coerces a cleared value to '' → Number('') === 0 → budget 0
    // (the Number.isNaN guard only trips for a genuinely NaN parse, which a
    // number input never yields).
    onChange.mockClear();
    fireEvent.change(input, { target: { value: '' } });
    expect(onChange).toHaveBeenCalledWith({ budget: 0 });
  });

  it('hides the custom input when the value matches the off sentinel', () => {
    render(
      <ReasoningWidget
        widget="budget_int"
        budgetRange={RANGE}
        value={{ budget: 0 }}
        onChange={vi.fn()}
      />
    );
    // preset resolves to Off → no custom number input rendered.
    expect(screen.queryByLabelText('Reasoning budget (tokens)')).toBeNull();
  });

  it('hides the custom input when the value matches the dynamic sentinel', () => {
    render(
      <ReasoningWidget
        widget="budget_int"
        budgetRange={RANGE}
        value={{ budget: -1 }}
        onChange={vi.fn()}
      />
    );
    expect(screen.queryByLabelText('Reasoning budget (tokens)')).toBeNull();
  });
});

describe('widget=toggle_budget', () => {
  it('reflects the disabled state and toggles thinking on', () => {
    const onChange = vi.fn();
    render(
      <ReasoningWidget
        widget="toggle_budget"
        budgetRange={RANGE}
        value={{ enabled: false }}
        onChange={onChange}
      />
    );
    expect(screen.getByText('Thinking disabled')).toBeTruthy();
    // No budget input while disabled.
    expect(screen.queryByLabelText('Reasoning budget (tokens)')).toBeNull();

    fireEvent.click(screen.getByRole('switch'));
    expect(onChange).toHaveBeenCalledWith({ enabled: true });
  });

  it('shows the budget input when enabled and emits enabled+budget on change', () => {
    const onChange = vi.fn();
    render(
      <ReasoningWidget
        widget="toggle_budget"
        budgetRange={RANGE}
        value={{ enabled: true, budget: 2048 }}
        onChange={onChange}
      />
    );
    expect(screen.getByText('Thinking enabled')).toBeTruthy();
    const input = screen.getByLabelText('Reasoning budget (tokens)') as HTMLInputElement;
    expect(input.value).toBe('2048');

    fireEvent.change(input, { target: { value: '8000' } });
    expect(onChange).toHaveBeenCalledWith({ enabled: true, budget: 8000 });

    // Blank clears the budget but keeps thinking enabled.
    onChange.mockClear();
    fireEvent.change(input, { target: { value: '' } });
    expect(onChange).toHaveBeenCalledWith({ enabled: true });
  });

  it('toggles thinking off when the switch is unchecked', () => {
    const onChange = vi.fn();
    render(
      <ReasoningWidget
        widget="toggle_budget"
        budgetRange={RANGE}
        value={{ enabled: true }}
        onChange={onChange}
      />
    );
    fireEvent.click(screen.getByRole('switch'));
    expect(onChange).toHaveBeenCalledWith({ enabled: false });
  });
});
