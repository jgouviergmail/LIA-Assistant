/**
 * BudgetBar — one drawing for "how much of the allowance is gone".
 *
 * Two copies of this markup existed (iterations, then tool time), and the
 * second arrived without the first one's warning line. These tests pin the
 * behaviour the single component now guarantees for both callers.
 */

import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BudgetBar } from '../BudgetBar';

describe('BudgetBar', () => {
  it('fills proportionally below the bound', () => {
    render(<BudgetBar value={3} max={12} exhaustedLabel="spent" />);

    expect(screen.getByTestId('budget-bar-fill')).toHaveStyle({ width: '25%' });
    expect(screen.queryByText('spent')).not.toBeInTheDocument();
  });

  it('warns once the bound is reached', () => {
    render(<BudgetBar value={12} max={12} exhaustedLabel="ceiling reached" />);

    expect(screen.getByText('ceiling reached')).toBeInTheDocument();
  });

  it('warns when the bound is exceeded, and never overfills', () => {
    render(<BudgetBar value={30} max={12} exhaustedLabel="ceiling reached" />);

    expect(screen.getByTestId('budget-bar-fill')).toHaveStyle({ width: '100%' });
    expect(screen.getByText('ceiling reached')).toBeInTheDocument();
  });

  it('names what it measures when two bars sit together', () => {
    // Two anonymous bars stacked under one metric list are a guessing game:
    // the ReAct panel draws iterations AND tool time, and they read the same.
    render(<BudgetBar value={3} max={12} label="Iterations" exhaustedLabel="spent" />);

    expect(screen.getByText('Iterations')).toBeInTheDocument();
  });

  it('stays label-free when the caller has no second bar to disambiguate', () => {
    const { container } = render(<BudgetBar value={3} max={12} exhaustedLabel="spent" />);

    expect(container.textContent).toBe('');
  });

  it('renders nothing without a published bound', () => {
    // ADR-184: a bar scaled against an invented bound tells the reader
    // something the system never enforced.
    const { container } = render(<BudgetBar value={5} max={0} exhaustedLabel="spent" />);

    expect(container).toBeEmptyDOMElement();
  });

  it('never renders a negative fill', () => {
    render(<BudgetBar value={-4} max={10} exhaustedLabel="spent" />);

    expect(screen.getByTestId('budget-bar-fill')).toHaveStyle({ width: '0%' });
  });
});
